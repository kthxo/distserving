#!/usr/bin/env python3
"""Trace replay driver for ThunderAgent (dataset-agnostic).

Reads a canonical trace (JSONL, one line = one turn; see EXPERIMENT_PLAN §2):

    {"session_id":"s1","turn":0,"input_tokens":14558,"output_tokens":29,"tool_duration_s":0.41}

and replays the recorded load deterministically against the ThunderAgent proxy.

Design (Level 1 = "counts" replay):
  * One session == one program (unique program_id -> sticky KV / routing).
  * Turns of a session are ordered by `turn`; the context is *accumulated*
    (each turn appends the previous assistant reply + a synthetic tool result),
    so within-session prefix sharing is reproduced like a real agent rollout.
  * For turn t we pad the current user message with SESSION-UNIQUE filler tokens
    so the total prompt token count matches `input_tokens[t]`. Because this
    driver uses the SAME tokenizer + chat template as the vLLM backend, the
    locally-counted prompt length equals the server's `prompt_tokens`.
  * `max_tokens = output_tokens[t]`, `temperature=0`, `extra_body.program_id`.
  * After each turn: `await asyncio.sleep(tool_duration_s)` (tool-call bubble).
  * On session end: `POST /programs/release`.
  * closed-loop concurrency C via asyncio.Semaphore(C); if there are fewer
    sessions than requested programs, sessions are reused with a run-suffix.

Reuses the metrics/streaming/summary machinery of workload_driver_yunuikang.py.

Modes:
  * live  (default): sends requests to the proxy, scrapes backend /metrics.
  * --dry-run       : no HTTP; builds every payload and reports token-match
                      accuracy + total offered load (for offline validation).
"""
import argparse
import asyncio
import json
import random
import re
import statistics
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

# httpx only needed for live mode; import lazily so --dry-run works without a server.


# ----------------------------- trace loading --------------------------------

def load_trace(path: str) -> "OrderedSessions":
    """Load canonical JSONL trace, grouped by session_id, turns sorted by `turn`."""
    sessions: Dict[str, List[dict]] = defaultdict(list)
    with open(path, "r", encoding="utf-8") as f:
        for ln, raw in enumerate(f, 1):
            raw = raw.strip()
            if not raw:
                continue
            obj = json.loads(raw)
            for k in ("session_id", "turn", "input_tokens", "output_tokens"):
                if k not in obj:
                    raise ValueError(f"line {ln}: missing field '{k}'")
            sessions[str(obj["session_id"])].append(obj)
    ordered: List[Tuple[str, List[dict]]] = []
    for sid, turns in sessions.items():
        turns.sort(key=lambda r: r["turn"])
        ordered.append((sid, turns))
    # deterministic session order (by session_id) so runs are reproducible
    ordered.sort(key=lambda kv: kv[0])
    return ordered


# ----------------------------- tokenizer helpers ----------------------------

SHARED_SYSTEM_PROMPT = (
    "You are a meticulous autonomous coding agent operating inside a tool loop. "
    "Follow instructions exactly, think step by step, and keep answers concise. "
    "You receive tool results between turns; incorporate them faithfully. "
    "Never fabricate sources. " * 6
)  # identical across sessions -> shared prefix cache


class Padder:
    """Builds messages whose total prompt token count matches a target, using
    session-unique filler tokens (so filler is not prefix-cache-deduplicated)."""

    def __init__(self, tokenizer):
        self.tok = tokenizer
        # a pool of "safe" mid-vocab token ids to draw filler from (avoid the
        # low special-token range and the very top of the vocab)
        vs = getattr(tokenizer, "vocab_size", 100000) or 100000
        self.lo, self.hi = 1000, min(vs, 100000)

    def count(self, messages: List[dict]) -> int:
        enc = self.tok.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True)
        # apply_chat_template may return a list of ids or a BatchEncoding
        if isinstance(enc, dict) or hasattr(enc, "input_ids"):
            return len(enc["input_ids"])
        return len(enc)

    def _filler_text(self, seed: int, ntok: int) -> str:
        if ntok <= 0:
            return ""
        rng = random.Random(seed)
        ids = [rng.randrange(self.lo, self.hi) for _ in range(ntok)]
        return self.tok.decode(ids)

    def build_user(self, base_messages: List[dict], user_core: str,
                   target_tokens: int, seed: int) -> Tuple[dict, int]:
        """Return (user_message, achieved_prompt_tokens). `base_messages` are the
        already-accumulated prior messages (system + past turns). The returned
        user message = [filler]+user_core, sized so that
        count(base_messages+[user]) ~= target_tokens."""
        user_msg = {"role": "user", "content": user_core}
        cur = self.count(base_messages + [user_msg])
        need = target_tokens - cur
        if need <= 0:
            return user_msg, cur           # already >= target (context saturated)
        # first estimate: filler with `need` tokens, then correct up to 3 rounds
        filler_ntok = need
        for _ in range(4):
            filler = self._filler_text(seed, filler_ntok)
            user_msg = {"role": "user", "content": filler + "\n\n" + user_core}
            got = self.count(base_messages + [user_msg])
            diff = target_tokens - got
            if abs(diff) <= 1 or filler_ntok <= 0:
                break
            filler_ntok = max(0, filler_ntok + diff)   # ~1 filler-token per prompt-token
        return user_msg, got


# ----------------------------- metrics (reused) -----------------------------

def _parse_prefix_cache(metrics_text: str) -> Dict[str, float]:
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
        "prompt_tokens": _sum("vllm:prompt_tokens_total"),
    }


async def _fetch_metrics(client, backend_urls: List[str]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for url in backend_urls:
        try:
            r = await client.get(f"{url}/metrics", timeout=10)
            out[url] = _parse_prefix_cache(r.text) if r.status_code == 200 else {}
        except Exception:
            out[url] = {}
    return out


# ----------------------------- one chat turn --------------------------------

async def _chat_once(client, base_url: str, payload: dict, stream: bool):
    """One chat completion -> (content, usage, ttft_s, turn_latency_s)."""
    t0 = time.perf_counter()
    if not stream:
        r = await client.post(f"{base_url}/v1/chat/completions", json=payload, timeout=1200)
        r.raise_for_status()
        data = r.json()
        turn_latency = time.perf_counter() - t0
        content = data["choices"][0]["message"]["content"] or ""
        return content, (data.get("usage") or {}), None, turn_latency

    payload = {**payload, "stream": True, "stream_options": {"include_usage": True}}
    content_parts: List[str] = []
    usage: Dict[str, float] = {}
    ttft: Optional[float] = None
    async with client.stream("POST", f"{base_url}/v1/chat/completions",
                             json=payload, timeout=1200) as r:
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
                    if ttft is None:
                        ttft = time.perf_counter() - t0
                    content_parts.append(delta)
            if obj.get("usage"):
                usage = obj["usage"]
    turn_latency = time.perf_counter() - t0
    return "".join(content_parts), usage, ttft, turn_latency


# ----------------------------- one program (session) ------------------------

TURN_PROMPT = "Continue the task using the tool output above; be concise. /no_think"


async def run_program(client, args, padder: Padder, program_id: str,
                      turns: List[dict], seed: int, sem: asyncio.Semaphore,
                      results: List[dict], trace: List[dict]) -> None:
    async with sem:
        messages: List[dict] = [{"role": "system", "content": SHARED_SYSTEM_PROMPT}]
        prog_start = time.perf_counter()
        turn_latencies: List[float] = []
        completion_tokens = 0
        turns_done = 0
        peak_seq_tokens = 0
        offered_input_tokens = 0        # sum of achieved prompt tokens (offered load)
        token_match_err = 0             # sum |target - achieved| over turns
        ok = True
        for rec in turns:
            target_in = int(rec["input_tokens"])
            out_tok = max(1, int(rec["output_tokens"]))
            tool_s = float(rec.get("tool_duration_s") or 0.0)
            core = f"[turn {rec['turn']}] {TURN_PROMPT}"
            # size the user message to hit target input_tokens
            user_msg, achieved = padder.build_user(messages, core, target_in, seed + rec["turn"])
            messages.append(user_msg)
            offered_input_tokens += achieved
            token_match_err += abs(target_in - achieved)
            peak_seq_tokens = max(peak_seq_tokens, achieved + out_tok)

            payload = {
                "model": args.model,
                "messages": messages,
                "max_tokens": out_tok,
                "temperature": 0,
                "program_id": program_id,
            }

            if args.dry_run:
                # simulate an assistant reply of out_tok filler tokens so the next
                # turn's accumulated context is realistic; no HTTP.
                fake = padder._filler_text(seed * 31 + rec["turn"], out_tok)
                messages.append({"role": "assistant", "content": fake})
                completion_tokens += out_tok
                turns_done += 1
                trace.append({"program_id": program_id, "turn": rec["turn"],
                              "target_input_tokens": target_in,
                              "achieved_prompt_tokens": achieved,
                              "output_tokens": out_tok, "tool_duration_s": tool_s})
                continue

            try:
                msg, usage, ttft, turn_latency = await _chat_once(
                    client, args.base_url, payload, args.stream)
            except Exception as e:
                ok = False
                results.append({"program_id": program_id, "ok": False, "error": str(e)[:200]})
                break
            turn_latencies.append(turn_latency)
            turns_done += 1
            ptok = int(usage.get("prompt_tokens") or achieved)
            ctok = int(usage.get("completion_tokens") or 0)
            completion_tokens += ctok
            seq_tokens = ptok + ctok
            peak_seq_tokens = max(peak_seq_tokens, seq_tokens)
            decode = (turn_latency - ttft) if (ttft is not None) else None
            trace.append({
                "program_id": program_id, "turn": rec["turn"],
                "target_input_tokens": target_in,
                "achieved_prompt_tokens": achieved,
                "server_prompt_tokens": ptok, "completion_tokens": ctok,
                "seq_tokens": seq_tokens, "turn_latency_s": turn_latency,
                "ttft_s": ttft, "decode_s": decode, "tool_duration_s": tool_s,
            })
            messages.append({"role": "assistant", "content": msg})
            if tool_s > 0:
                await asyncio.sleep(tool_s)   # tool-call bubble

        # still holding the semaphore slot: finalize + release the program so
        # the program's lifetime (incl. release) counts toward closed-loop C.
        prog_latency = time.perf_counter() - prog_start
        if not args.dry_run:
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
                "offered_input_tokens": offered_input_tokens,
                "token_match_err": token_match_err,
                "finished_at": time.perf_counter(),
            })


# ----------------------------- orchestration --------------------------------

def build_program_list(sessions, num_programs: Optional[int]):
    """Return list of (program_id, turns, seed). If num_programs > #sessions,
    reuse sessions with a run suffix to keep program_id unique."""
    n_sess = len(sessions)
    total = num_programs if num_programs else n_sess
    progs = []
    for i in range(total):
        sess_idx = i % n_sess
        sid, turns = sessions[sess_idx]
        run_idx = i // n_sess
        pid = f"{sid}#{run_idx}"
        # deterministic, program-unique seed (no PYTHONHASHSEED dependence):
        # sess_idx keeps within-session filler stable; run_idx makes reused
        # sessions distinct so their KV is not deduplicated.
        seed = sess_idx * 1000 + run_idx
        progs.append((pid, turns, seed))
    return progs


async def main_async(args) -> dict:
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.tokenizer)
    padder = Padder(tok)
    sessions = load_trace(args.trace)
    progs = build_program_list(sessions, args.num_programs or None)

    backends = [u.strip() for u in args.backends.split(",") if u.strip()]
    results: List[dict] = []
    trace: List[dict] = []

    if args.dry_run:
        sem = asyncio.Semaphore(args.concurrency)
        wall0 = time.perf_counter()
        await asyncio.gather(*[
            run_program(None, args, padder, pid, turns, seed, sem, results, trace)
            for (pid, turns, seed) in progs
        ])
        wall = time.perf_counter() - wall0
        m_before = m_after = {}
    else:
        import httpx
        limits = httpx.Limits(max_connections=None, max_keepalive_connections=None)
        async with httpx.AsyncClient(limits=limits) as client:
            m_before = await _fetch_metrics(client, backends)
            sem = asyncio.Semaphore(args.concurrency)
            wall0 = time.perf_counter()
            await asyncio.gather(*[
                run_program(client, args, padder, pid, turns, seed, sem, results, trace)
                for (pid, turns, seed) in progs
            ])
            wall = time.perf_counter() - wall0
            m_after = await _fetch_metrics(client, backends)

    return summarize(args, backends, progs, results, trace, wall, m_before, m_after)


def _stats(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    s = sorted(vals)
    return {"n": len(s), "min": s[0], "max": s[-1],
            "mean": statistics.mean(s), "median": statistics.median(s),
            "p95": s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]}


def summarize(args, backends, progs, results, trace, wall, m_before, m_after) -> dict:
    ok = [r for r in results if r.get("ok")]
    fail = [r for r in results if not r.get("ok")]

    # steady-state: drop first/last warmup_frac of completions (by finish order)
    steady = ok
    if not args.dry_run and ok and args.warmup_frac > 0:
        so = sorted(ok, key=lambda r: r.get("finished_at", 0))
        k = int(len(so) * args.warmup_frac)
        steady = so[k:len(so) - k] if len(so) - 2 * k >= 1 else so

    lat = sorted(r["program_latency_s"] for r in steady) if not args.dry_run else []

    def pct(p):
        if not lat:
            return None
        return lat[min(len(lat) - 1, int(round(p / 100 * (len(lat) - 1))))]

    def _delta(key):
        return sum(m_after.get(u, {}).get(key, 0) - m_before.get(u, {}).get(key, 0)
                   for u in backends)
    hits, queries = _delta("hits"), _delta("queries")
    hit_rate = (hits / queries) if queries else None

    summary = {
        "run_tag": args.run_tag, "router": args.router, "trace": args.trace,
        "concurrency": args.concurrency, "num_programs": len(progs),
        "num_sessions_in_trace": len({p[0].split('#')[0] for p in progs}),
        "dry_run": args.dry_run, "backends": backends,
        "completed": len(ok), "failed": len(fail), "wall_s": wall,
        # offered load (deterministic; identical across router modes)
        "total_turns_offered": sum(len(t) for _, t, _ in progs),
        "total_offered_input_tokens": sum(r.get("offered_input_tokens", 0) for r in results),
        "total_completion_tokens": sum(r.get("completion_tokens", 0) for r in ok),
        "token_match_abs_err": sum(r.get("token_match_err", 0) for r in results),
    }
    if not args.dry_run:
        tot_completion = sum(r["completion_tokens"] for r in steady)
        # throughput from steady window wall time
        if steady:
            fin = [r["finished_at"] for r in steady]
            steady_wall = max(fin) - min(fin) if len(fin) > 1 else wall
        else:
            steady_wall = wall
        summary.update({
            "steady_programs": len(steady),
            "throughput_programs_per_s": (len(steady) / steady_wall) if steady_wall else None,
            "throughput_completion_tok_per_s": (tot_completion / steady_wall) if steady_wall else None,
            "latency_mean_s": statistics.mean(lat) if lat else None,
            "latency_p50_s": pct(50), "latency_p95_s": pct(95),
            "latency_max_s": max(lat) if lat else None,
            "prefix_cache_hits_delta": hits, "prefix_cache_queries_delta": queries,
            "prefix_cache_hit_rate": hit_rate,
            "num_preemptions_delta": _delta("preemptions"),
            "prompt_tokens_total_delta": _delta("prompt_tokens"),
            "per_backend_query_delta": {u: m_after.get(u, {}).get("queries", 0)
                                        - m_before.get(u, {}).get("queries", 0) for u in backends},
        })
    if fail:
        summary["sample_error"] = fail[0].get("error")

    # token-match diagnostics (dry-run validation)
    tgt = [r.get("target_input_tokens") for r in trace]
    ach = [r.get("achieved_prompt_tokens") for r in trace]
    errs = [abs(a - t) for t, a in zip(tgt, ach) if t is not None and a is not None]
    summary["token_match"] = {
        "turns": len(errs),
        "mean_abs_err": statistics.mean(errs) if errs else None,
        "max_abs_err": max(errs) if errs else None,
        "within_1pct": (sum(1 for t, a in zip(tgt, ach)
                            if t and abs(a - t) <= max(1, 0.01 * t)) / len(errs)) if errs else None,
    }
    if args.trace_out and trace:
        with open(args.trace_out, "w", encoding="utf-8") as f:
            for r in trace:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", required=True, help="canonical JSONL trace path")
    ap.add_argument("--base-url", default="http://localhost:9000")
    ap.add_argument("--router-url", default="http://localhost:9000")
    ap.add_argument("--backends", default="http://localhost:8000,http://localhost:8001")
    ap.add_argument("--model", default="Qwen/Qwen3-8B")
    ap.add_argument("--tokenizer", default="Qwen/Qwen3-8B")
    ap.add_argument("--router", default="tr", help="label only: tr|default")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--num-programs", type=int, default=0,
                    help="0 = one program per session; >#sessions reuses sessions")
    ap.add_argument("--warmup-frac", type=float, default=0.1)
    ap.add_argument("--stream", action="store_true", help="capture TTFT per turn")
    ap.add_argument("--dry-run", action="store_true",
                    help="no HTTP; validate payload construction + offered load")
    ap.add_argument("--run-tag", default="replay")
    ap.add_argument("--out", default="")
    ap.add_argument("--trace-out", default="")
    args = ap.parse_args()

    summary = asyncio.run(main_async(args))
    line = json.dumps(summary, ensure_ascii=False)
    print(line)
    if args.out:
        with open(args.out, "a", encoding="utf-8") as f:
            f.write(line + "\n")


if __name__ == "__main__":
    main()
