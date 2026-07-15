#!/usr/bin/env python3
"""Synthetic agentic workload driver for ThunderAgent reproduction.

Simulates many concurrent multi-turn "programs" (agents). Each program:
  - has a unique program_id (so ThunderAgent keeps its KV cache / routing sticky)
  - shares a long system prompt (to induce prefix-cache reuse)
  - loops: reasoning (chat completion) -> tool call (sleep, GPU idle bubble)
    -> append tool result -> next turn
  - releases the program at the end (POST /programs/release)

Runs ONE (router, concurrency) setting and writes a JSON summary. Sweep over
concurrency / router mode is done by the caller (see run_sweep_yunuikang.sh).

Measures: per-program latency, throughput (programs/s, completion tok/s), and
KV prefix-cache hit-rate delta pulled from each vLLM backend's /metrics.
"""
import argparse
import asyncio
import json
import re
import statistics
import time
import uuid
from typing import Dict, List, Optional

import httpx

SHARED_SYSTEM_PROMPT = (
    "You are a meticulous research assistant operating inside an automated "
    "agent loop. Follow instructions exactly, think step by step, and keep "
    "answers concise. You may receive tool results between turns; incorporate "
    "them faithfully. Never fabricate sources. " * 8
)  # ~ few hundred tokens, identical across programs -> prefix-cache friendly

TURN_QUESTIONS = [
    "Summarize the tradeoff between KV-cache locality and load balancing in one sentence.",
    "Given the previous tool output, list two follow-up checks in under 15 words.",
    "State one risk of evicting a paused program's KV cache.",
    "In two words, name the failure mode when cache is thrashed.",
    "Give a one-line takeaway.",
]


def _parse_prefix_cache(metrics_text: str) -> Dict[str, float]:
    """Extract vLLM prefix-cache hit/query counters (summed over label sets)."""
    def _sum(metric: str) -> float:
        total = 0.0
        for m in re.finditer(rf"^{re.escape(metric)}(?:{{[^}}]*}})?\s+([0-9.eE+-]+)$",
                             metrics_text, re.MULTILINE):
            try:
                total += float(m.group(1))
            except ValueError:
                pass
        return total
    return {
        "queries": _sum("vllm:prefix_cache_queries_total"),
        "hits": _sum("vllm:prefix_cache_hits_total"),
        "preemptions": _sum("vllm:num_preemptions_total"),
    }


def _unique_filler(idx: int, ntok: int) -> str:
    """A long, program-UNIQUE text block (~ntok tokens) placed after the shared
    system prompt so it is NOT deduplicated by prefix caching -> forces distinct
    per-program KV and lets us pressure total KV capacity."""
    if ntok <= 0:
        return ""
    base = idx * 100003 + 7
    body = " ".join(str((base + i) % 100000) for i in range(ntok))
    return f"[DOC-{idx}] Reference material, read carefully: {body}\n\n"


async def _fetch_metrics(client: httpx.AsyncClient, backend_urls: List[str]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for url in backend_urls:
        try:
            r = await client.get(f"{url}/metrics", timeout=10)
            out[url] = _parse_prefix_cache(r.text) if r.status_code == 200 else {}
        except Exception:
            out[url] = {}
    return out


async def _chat_once(client: httpx.AsyncClient, args, payload: dict):
    """One chat completion. Returns (content, usage, ttft_s, turn_latency_s).

    Non-streaming: ttft_s is None (can't observe first-token time).
    Streaming (--stream): capture time-to-first-token client-side and request
    usage in the final chunk via stream_options.include_usage."""
    t0 = time.perf_counter()
    if not args.stream:
        r = await client.post(f"{args.base_url}/v1/chat/completions", json=payload, timeout=900)
        r.raise_for_status()
        data = r.json()
        turn_latency = time.perf_counter() - t0
        content = data["choices"][0]["message"]["content"] or ""
        return content, (data.get("usage") or {}), None, turn_latency

    payload = {**payload, "stream": True, "stream_options": {"include_usage": True}}
    content_parts: List[str] = []
    usage: Dict[str, float] = {}
    ttft: Optional[float] = None
    async with client.stream("POST", f"{args.base_url}/v1/chat/completions",
                             json=payload, timeout=900) as r:
        r.raise_for_status()
        async for raw in r.aiter_lines():
            if not raw or not raw.startswith("data:"):
                continue
            chunk = raw[len("data:"):].strip()
            if chunk == "[DONE]":
                break
            try:
                obj = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            choices = obj.get("choices") or []
            if choices:
                delta = (choices[0].get("delta") or {}).get("content")
                if delta:
                    if ttft is None:            # first token -> TTFT (~prefill)
                        ttft = time.perf_counter() - t0
                    content_parts.append(delta)
            if obj.get("usage"):
                usage = obj["usage"]
    turn_latency = time.perf_counter() - t0
    return "".join(content_parts), usage, ttft, turn_latency


async def run_program(client: httpx.AsyncClient, args, idx: int, sem: asyncio.Semaphore,
                      results: List[dict], trace: List[dict]) -> None:
    async with sem:
        program_id = f"{args.run_id}:{idx}"
        messages = [
            {"role": "system", "content": SHARED_SYSTEM_PROMPT},
            {"role": "user", "content": _unique_filler(idx, args.ctx_tokens)
             + TURN_QUESTIONS[0] + " /no_think"},
        ]
        prog_start = time.perf_counter()
        turn_latencies: List[float] = []
        completion_tokens = 0
        turns_done = 0
        peak_seq_tokens = 0          # max (prompt+completion) reached -> KV peak
        ok = True
        for t in range(args.turns):
            payload = {
                "model": args.model,
                "messages": messages,
                "max_tokens": args.max_tokens,
                "temperature": 0,
                "program_id": program_id,
            }
            try:
                msg, usage, ttft, turn_latency = await _chat_once(client, args, payload)
            except Exception as e:
                ok = False
                results.append({"program_id": program_id, "ok": False, "error": str(e)[:200]})
                break
            turn_latencies.append(turn_latency)
            turns_done += 1
            ptok = int(usage.get("prompt_tokens") or 0)
            ctok = int(usage.get("completion_tokens") or 0)
            completion_tokens += ctok
            seq_tokens = ptok + ctok          # sequence length after this turn == KV footprint
            peak_seq_tokens = max(peak_seq_tokens, seq_tokens)
            decode = (turn_latency - ttft) if (ttft is not None) else None
            trace.append({
                "program_id": program_id, "turn": t,
                "prompt_tokens": ptok, "completion_tokens": ctok,
                "seq_tokens": seq_tokens,
                "turn_latency_s": turn_latency,
                "ttft_s": ttft, "decode_s": decode,
                "tool_sleep_s": (args.tool_sleep if t < args.turns - 1 else 0.0),
            })
            # append assistant reply + a synthetic tool result, then next turn
            messages.append({"role": "assistant", "content": msg})
            if t < args.turns - 1:
                await asyncio.sleep(args.tool_sleep)  # simulate tool call (GPU idle bubble)
                tool_result = f"[tool_result #{t}] value={idx * 7 + t}. "
                q = TURN_QUESTIONS[(t + 1) % len(TURN_QUESTIONS)]
                messages.append({"role": "user", "content": tool_result + q + " /no_think"})
        prog_latency = time.perf_counter() - prog_start
        # release the program
        try:
            await client.post(f"{args.router_url}/programs/release",
                              json={"program_id": program_id}, timeout=10)
        except Exception:
            pass
        if ok:
            results.append({
                "program_id": program_id, "ok": True,
                "program_latency_s": prog_latency,
                "turn_latencies_s": turn_latencies,
                "completion_tokens": completion_tokens,
                "turns_done": turns_done,
                "peak_seq_tokens": peak_seq_tokens,
            })


async def main_async(args) -> dict:
    limits = httpx.Limits(max_connections=None, max_keepalive_connections=None)
    async with httpx.AsyncClient(limits=limits) as client:
        backends = [u.strip() for u in args.backends.split(",") if u.strip()]
        m_before = await _fetch_metrics(client, backends)
        sem = asyncio.Semaphore(args.concurrency)
        results: List[dict] = []
        trace: List[dict] = []
        wall0 = time.perf_counter()
        await asyncio.gather(*[
            run_program(client, args, i, sem, results, trace)
            for i in range(args.num_programs)
        ])
        wall = time.perf_counter() - wall0
        m_after = await _fetch_metrics(client, backends)

    ok = [r for r in results if r.get("ok")]
    fail = [r for r in results if not r.get("ok")]
    lat = sorted(r["program_latency_s"] for r in ok)
    tot_completion = sum(r["completion_tokens"] for r in ok)

    def pct(p: float) -> Optional[float]:
        if not lat:
            return None
        k = min(len(lat) - 1, int(round(p / 100 * (len(lat) - 1))))
        return lat[k]

    # prefix cache hit-rate delta across backends
    hits = sum(m_after.get(u, {}).get("hits", 0) - m_before.get(u, {}).get("hits", 0) for u in backends)
    queries = sum(m_after.get(u, {}).get("queries", 0) - m_before.get(u, {}).get("queries", 0) for u in backends)
    hit_rate = (hits / queries) if queries else None
    preemptions = sum(m_after.get(u, {}).get("preemptions", 0) - m_before.get(u, {}).get("preemptions", 0) for u in backends)

    summary = {
        "run_id": args.run_id,
        "router": args.router,
        "concurrency": args.concurrency,
        "num_programs": args.num_programs,
        "turns": args.turns,
        "tool_sleep_s": args.tool_sleep,
        "max_tokens": args.max_tokens,
        "ctx_tokens": args.ctx_tokens,
        "backends": backends,
        "completed": len(ok),
        "failed": len(fail),
        "wall_s": wall,
        "throughput_programs_per_s": (len(ok) / wall) if wall else None,
        "throughput_completion_tok_per_s": (tot_completion / wall) if wall else None,
        "latency_mean_s": statistics.mean(lat) if lat else None,
        "latency_p50_s": pct(50),
        "latency_p95_s": pct(95),
        "latency_max_s": max(lat) if lat else None,
        "prefix_cache_hits_delta": hits,
        "prefix_cache_queries_delta": queries,
        "prefix_cache_hit_rate": hit_rate,
        "num_preemptions_delta": preemptions,
    }
    if fail:
        summary["sample_error"] = fail[0].get("error")

    # --- workload characterization aggregates (from per-turn trace) ---
    if trace:
        def _stats(vals):
            vals = [v for v in vals if v is not None]
            if not vals:
                return None
            s = sorted(vals)
            return {
                "n": len(s), "min": s[0], "max": s[-1],
                "mean": statistics.mean(s), "median": statistics.median(s),
                "p95": s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))],
            }
        summary["char"] = {
            "prompt_tokens": _stats([r["prompt_tokens"] for r in trace]),
            "completion_tokens": _stats([r["completion_tokens"] for r in trace]),
            "seq_tokens": _stats([r["seq_tokens"] for r in trace]),
            "ttft_s": _stats([r["ttft_s"] for r in trace]),
            "decode_s": _stats([r["decode_s"] for r in trace]),
            "turn_latency_s": _stats([r["turn_latency_s"] for r in trace]),
            "program_lifetime_s": _stats([r["program_latency_s"] for r in ok]),
            "peak_seq_tokens": _stats([r["peak_seq_tokens"] for r in ok]),
            "turns_done": _stats([r["turns_done"] for r in ok]),
        }
    if args.trace_out and trace:
        with open(args.trace_out, "w", encoding="utf-8") as f:
            for r in trace:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        # sibling per-program file (lifetime / turns / peak KV footprint)
        prog_path = args.trace_out.rsplit(".", 1)[0] + ".prog.jsonl"
        with open(prog_path, "w", encoding="utf-8") as f:
            for r in ok:
                f.write(json.dumps({
                    "program_id": r["program_id"],
                    "program_latency_s": r["program_latency_s"],
                    "turns_done": r["turns_done"],
                    "completion_tokens": r["completion_tokens"],
                    "peak_seq_tokens": r["peak_seq_tokens"],
                }, ensure_ascii=False) + "\n")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:9000")
    ap.add_argument("--router-url", default="http://localhost:9000")
    ap.add_argument("--backends", default="http://localhost:8000,http://localhost:8001",
                    help="vLLM backend URLs for /metrics scraping (comma-separated)")
    ap.add_argument("--model", default="Qwen/Qwen3-8B")
    ap.add_argument("--router", default="tr", help="label only: tr|default (for the summary)")
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--num-programs", type=int, default=64)
    ap.add_argument("--turns", type=int, default=4)
    ap.add_argument("--tool-sleep", type=float, default=0.5)
    ap.add_argument("--max-tokens", type=int, default=128)
    ap.add_argument("--ctx-tokens", type=int, default=0,
                    help="approx unique filler tokens per program (KV pressure)")
    ap.add_argument("--out", default="")
    ap.add_argument("--trace-out", default="",
                    help="write per-turn JSONL records here (characterization)")
    ap.add_argument("--stream", action="store_true",
                    help="use streaming to capture TTFT (~prefill) per turn")
    ap.add_argument("--run-id", default="")
    args = ap.parse_args()
    if not args.run_id:
        args.run_id = f"wl-{args.router}-c{args.concurrency}-{uuid.uuid4().hex[:6]}"

    summary = asyncio.run(main_async(args))
    line = json.dumps(summary, ensure_ascii=False)
    print(line)
    if args.out:
        with open(args.out, "a", encoding="utf-8") as f:
            f.write(line + "\n")


if __name__ == "__main__":
    main()
