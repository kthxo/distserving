#!/usr/bin/env python3
"""MORI replay driver — fixed 1-hour closed-loop over SGLang HiCache.

EXTENDS `trace_replay_driver_yunuikang.py` (imports its machinery; that file is
NOT modified). It adds ONLY the four gaps identified in PLAN §D-1b:

  1. Fixed wall-clock window (`--duration-s`, default 3600): C persistent workers
     each pull the next session from a PER-CYCLE-SHUFFLED cycling corpus and run
     it to completion, repeating until the deadline. Replaces the base
     run-to-completion `asyncio.gather` over a fixed program list. This is the
     paper §6.1 protocol (closed-loop slot, immediately start a new trace when one
     completes, fixed 1h).
  2. TTFT mean/p50/p95 aggregation over the steady window (base captures per-turn
     `ttft_s` via `--stream` but never aggregates it).
  3. SGLang `/metrics` parsing (base parsed vLLM metric names). HiCache
     offload/reload counter names are unknown until STEP1 → exposed via
     `--hicache-metrics` (comma list) as an extension point.
  4. Cycling-generator gates: per-cycle shuffle, unique-session coverage, and a
     cache-hit-rate timeseries used to check the hit rate does NOT rise
     monotonically across cycles (guards against artificial prefix-cache warm).

Reused verbatim from the base (no reinvention): Padder (tokenizer sizing),
_chat_once (streaming + TTFT capture), run_program (per-session context
accumulation + `sleep(tool_duration)` tool bubble + `/programs/release`),
load_trace, _stats.
"""
import argparse
import asyncio
import json
import os
import random
import re
import statistics
import sys
import time
from collections import defaultdict
from typing import Dict, List, Optional

# Import the reusable machinery from the base driver (same scripts/ directory).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trace_replay_driver_yunuikang import (  # noqa: E402
    Padder, _chat_once, run_program, load_trace, _stats,
)

# --------------------------------------------------------------------------
# 3. SGLang metrics (base parsed vLLM names)
# --------------------------------------------------------------------------
SGLANG_GAUGES = [
    "sglang:cache_hit_rate", "sglang:token_usage", "sglang:num_used_tokens",
    "sglang:num_running_reqs", "sglang:num_queue_reqs",
]
SGLANG_COUNTERS = ["sglang:prompt_tokens_total", "sglang:generation_tokens_total"]


def _parse_sglang(text: str, extra_names: List[str]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for name in SGLANG_GAUGES + SGLANG_COUNTERS + extra_names:
        tot = 0.0
        found = False
        for m in re.finditer(
            rf"^{re.escape(name)}(?:{{[^}}]*}})?\s+([0-9.eE+-]+)$", text, re.MULTILINE
        ):
            try:
                tot += float(m.group(1))
                found = True
            except ValueError:
                pass
        if found:
            out[name] = tot
    return out


async def _fetch_sglang(client, backend_urls: List[str], extra: List[str]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for url in backend_urls:
        try:
            r = await client.get(f"{url}/metrics", timeout=10)
            out[url] = _parse_sglang(r.text, extra) if r.status_code == 200 else {}
        except Exception:
            out[url] = {}
    return out


def _agg(samples: Dict[str, Dict[str, float]], key: str) -> Optional[float]:
    vals = [m[key] for m in samples.values() if key in m]
    if not vals:
        return None
    # gauges: mean across backends; counters: sum. cache_hit_rate is a gauge.
    if key in SGLANG_COUNTERS:
        return sum(vals)
    return statistics.mean(vals)


# --------------------------------------------------------------------------
# 1+4. cycling corpus (per-cycle shuffle) + coverage gate
# --------------------------------------------------------------------------
def corpus_cycler(sessions, seed: int):
    """Infinite generator of (program_id, turns, seed, base_sid, cycle).
    Each cycle reshuffles the session order (so repeated corpus passes do not
    replay in the same order → prefix cache is not artificially warmed)."""
    rng = random.Random(seed)
    n = len(sessions)
    cycle = 0
    while True:
        order = list(range(n))
        rng.shuffle(order)
        for idx in order:
            sid, turns = sessions[idx]
            yield (f"{sid}#c{cycle}", turns, idx * 1000 + cycle, sid, cycle)
        cycle += 1


async def _worker(client, args, padder, gen, sem, results, trace, deadline, cyc):
    while time.perf_counter() < deadline:
        pid, turns, seed, base_sid, cycle = next(gen)
        cyc["seen"].add(base_sid)
        cyc["max_cycle"] = max(cyc["max_cycle"], cycle)
        cyc["started"] += 1
        await run_program(client, args, padder, pid, turns, seed, sem, results, trace)


async def _metric_sampler(client, backends, interval, extra, series, stop):
    while not stop.is_set():
        s = await _fetch_sglang(client, backends, extra)
        series.append((time.perf_counter(), _agg(s, "sglang:cache_hit_rate")))
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


# --------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------
async def main_async(args) -> dict:
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.tokenizer)
    padder = Padder(tok)
    sessions = load_trace(args.trace)
    extra = [s.strip() for s in args.hicache_metrics.split(",") if s.strip()]
    backends = [u.strip() for u in args.backends.split(",") if u.strip()]

    results: List[dict] = []
    trace: List[dict] = []
    cyc = {"seen": set(), "max_cycle": 0, "started": 0}

    if args.dry_run:
        # validate payload/token-match over ONE corpus pass (no duration, no HTTP)
        gen = corpus_cycler(sessions, args.seed)
        sem = asyncio.Semaphore(args.concurrency)
        for _ in range(len(sessions)):
            pid, turns, seed, base_sid, cycle = next(gen)
            cyc["seen"].add(base_sid)
            await run_program(None, args, padder, pid, turns, seed, sem, results, trace)
        return summarize(args, backends, sessions, results, trace, 0.0, cyc, [])

    import httpx
    limits = httpx.Limits(max_connections=None, max_keepalive_connections=None)
    async with httpx.AsyncClient(limits=limits) as client:
        m_before = await _fetch_sglang(client, backends, extra)
        series: list = []
        stop = asyncio.Event()
        sampler = asyncio.create_task(
            _metric_sampler(client, backends, args.metric_interval, extra, series, stop))

        gen = corpus_cycler(sessions, args.seed)
        sem = asyncio.Semaphore(args.concurrency)
        wall0 = time.perf_counter()
        deadline = wall0 + args.duration_s
        workers = [
            asyncio.create_task(
                _worker(client, args, padder, gen, sem, results, trace, deadline, cyc))
            for _ in range(args.concurrency)
        ]
        await asyncio.gather(*workers)
        wall = time.perf_counter() - wall0

        stop.set()
        await sampler
        m_after = await _fetch_sglang(client, backends, extra)

    return summarize(args, backends, sessions, results, trace, wall, cyc, series,
                     m_before=m_before, m_after=m_after, extra=extra)


def summarize(args, backends, sessions, results, trace, wall, cyc, series,
              m_before=None, m_after=None, extra=None) -> dict:
    m_before = m_before or {}
    m_after = m_after or {}
    extra = extra or []
    ok = [r for r in results if r.get("ok")]
    fail = [r for r in results if not r.get("ok")]

    # steady window: drop first/last warmup_frac of completed programs by finish order
    steady = ok
    if not args.dry_run and ok and args.warmup_frac > 0:
        so = sorted(ok, key=lambda r: r.get("finished_at", 0))
        k = int(len(so) * args.warmup_frac)
        steady = so[k:len(so) - k] if len(so) - 2 * k >= 1 else so
    steady_pids = {r["program_id"] for r in steady}

    # steady wall = span of steady program finishes
    if steady:
        fin = [r["finished_at"] for r in steady]
        steady_wall = (max(fin) - min(fin)) if len(fin) > 1 else wall
    else:
        steady_wall = wall

    steady_completion = sum(r["completion_tokens"] for r in steady)
    steady_turns = sum(r.get("turns_done", 0) for r in steady)

    # 2. TTFT aggregation over steady programs' turns
    ttfts = [t["ttft_s"] for t in trace
             if t.get("ttft_s") is not None and t.get("program_id") in steady_pids]
    ttft_stats = _stats(ttfts)

    # 4. cycling gate
    hit_series = [(t, v) for t, v in series if v is not None]
    hit_vals = [v for _, v in hit_series]
    monotonic_up = (len(hit_vals) >= 3 and all(
        hit_vals[i] <= hit_vals[i + 1] + 1e-9 for i in range(len(hit_vals) - 1)))
    n_corpus = len(sessions)

    summary = {
        "run_tag": args.run_tag, "router": args.router, "system": args.system,
        "trace": os.path.basename(args.trace), "concurrency": args.concurrency,
        "duration_s": args.duration_s, "hicache_ratio": args.hicache_ratio,
        "dry_run": args.dry_run, "backends": backends,
        "completed_programs": len(ok), "failed_programs": len(fail), "wall_s": wall,
        "corpus_sessions": n_corpus,
        # --- headline metrics (paper §6.2) ---
        "steady_programs": len(steady),
        "output_throughput_tok_s": (steady_completion / steady_wall) if steady_wall else None,
        "step_throughput_req_s": (steady_turns / steady_wall) if steady_wall else None,
        "ttft_mean_s": ttft_stats["mean"] if ttft_stats else None,
        "ttft_p50_s": ttft_stats["median"] if ttft_stats else None,
        "ttft_p95_s": ttft_stats["p95"] if ttft_stats else None,
        "ttft_n": ttft_stats["n"] if ttft_stats else 0,
        "steady_wall_s": steady_wall,
        "steady_completion_tokens": steady_completion, "steady_turns": steady_turns,
        # --- cycling gate (§D-1) ---
        "cycling_gate": {
            "cycles_completed": cyc["max_cycle"],
            "programs_started": cyc["started"],
            "unique_sessions_seen": len(cyc["seen"]),
            "coverage_frac": (len(cyc["seen"]) / n_corpus) if n_corpus else None,
            "hit_rate_samples": len(hit_vals),
            "hit_rate_first": hit_vals[0] if hit_vals else None,
            "hit_rate_last": hit_vals[-1] if hit_vals else None,
            "hit_rate_monotonic_rising": monotonic_up,   # True = SUSPICIOUS (artificial warm)
        },
    }
    if not args.dry_run:
        def cdelta(key):
            return (_agg(m_after, key) or 0) - (_agg(m_before, key) or 0)
        summary["sglang_metrics"] = {
            "prompt_tokens_total_delta": cdelta("sglang:prompt_tokens_total"),
            "generation_tokens_total_delta": cdelta("sglang:generation_tokens_total"),
            "cache_hit_rate_last": _agg(m_after, "sglang:cache_hit_rate"),
            "hicache_extra": {k: _agg(m_after, k) for k in extra},
        }
    if fail:
        summary["sample_error"] = fail[0].get("error")

    # dry-run token-match diagnostics
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
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="MORI fixed-window replay driver (extends base)")
    ap.add_argument("--trace", required=True)
    ap.add_argument("--base-url", default="http://localhost:9000")
    ap.add_argument("--router-url", default="http://localhost:9000")
    ap.add_argument("--backends", default="http://localhost:8100")
    ap.add_argument("--model", default="Qwen/Qwen3-8B")
    ap.add_argument("--tokenizer", default="Qwen/Qwen3-8B")
    ap.add_argument("--router", default="mori", help="label only: default|tr|mori")
    ap.add_argument("--system", default="MORI", help="label: SMG|TA|TA+O|MORI")
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--duration-s", type=float, default=3600.0, help="fixed wall-clock window (paper: 1h)")
    ap.add_argument("--warmup-frac", type=float, default=0.2)
    ap.add_argument("--hicache-ratio", type=float, default=0.0, help="label only (0=off)")
    ap.add_argument("--metric-interval", type=float, default=15.0, help="sec between /metrics samples")
    ap.add_argument("--hicache-metrics", default="",
                    help="comma list of extra SGLang metric names (HiCache offload/reload; TBD STEP1)")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--stream", action="store_true", default=True, help="TTFT capture (on by default)")
    ap.add_argument("--no-stream", dest="stream", action="store_false")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run-tag", default="mori")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    summary = asyncio.run(main_async(args))
    line = json.dumps(summary, ensure_ascii=False)
    print(line)
    if args.out:
        with open(args.out, "a", encoding="utf-8") as f:
            f.write(line + "\n")


if __name__ == "__main__":
    main()
