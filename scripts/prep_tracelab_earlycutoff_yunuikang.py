#!/usr/bin/env python3
"""EARLY-CUTOFF normalization of the full TraceLab trace (STEP 2 of PLAN 2026-07-23).

DIFFERENT from prep_tracelab_yunuikang.py --max-input-tokens, which DROPS a whole
session if any turn exceeds the cap (session-drop = capping artifact). Here we
instead keep EVERY session (100% inclusion) and TRUNCATE each session at the step
right before its accumulated context (input_tokens) would exceed the limit L.
No content editing, no summarization — the kept turns are the original prefix.

  limit L  = min(model_window 131072, 0.8 * C_total)   (from STEP 1)
  tool>300 = clamped to 300 s (value only, turn NOT removed): heavy-tail + turn
             order preserved, only the 42.8h outlier wall-clock blowup removed.

Input : the canonical per-turn JSONL from prep_tracelab_yunuikang.py run with NO
        cap (tracelab_trace_full.jsonl). Read-only — original is not modified.
Output: same schema {session_id,turn,input_tokens,output_tokens,tool_duration_s[,cached_tokens]}
        with turns re-indexed 0..n-1 per (truncated) session + a sidecar .meta.json
        carrying early-cut statistics.
"""
import argparse
import json
import os
import statistics
from collections import defaultdict


def pct(s, q):
    if not s:
        return None
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


def dist(vals):
    if not vals:
        return None
    s = sorted(vals)
    return {"n": len(s), "min": s[0], "median": statistics.median(s),
            "mean": round(statistics.mean(s), 2), "p95": pct(s, 0.95),
            "p99": pct(s, 0.99), "max": s[-1]}


def early_cutoff(sessions, limit, cap_tool_s):
    """Truncate each session at the step before input_tokens exceeds `limit`.

    A session whose VERY FIRST turn already exceeds `limit` cannot be served
    (a single request > max_model_len is rejected by vLLM) and content editing
    is forbidden -> it is DROPPED and counted separately (this bounds the
    "100% inclusion" claim honestly). Turns with non-positive input_tokens
    (e.g. human-turn rows) are dropped first, mirroring prep_tracelab's invariant.
    Returns (out_records, stats)."""
    out = []
    n_sess_total = len(sessions)
    n_sess_cut = 0
    n_sess_dropped_overflow = 0
    turns_before = 0
    turns_after = 0
    turns_dropped = 0
    tool_clamped = 0
    for sid, rs in sessions.items():
        rs = sorted(rs, key=lambda r: r["turn"])
        rs = [r for r in rs if int(r.get("input_tokens", 0) or 0) > 0]  # drop non-positive
        if not rs:
            continue
        turns_before += len(rs)
        # keep the prefix while accumulated input stays within the limit
        kept = [r for r in rs if int(r["input_tokens"]) <= limit]
        if not kept:                                   # even turn 0 exceeds L -> cannot serve
            n_sess_dropped_overflow += 1
            turns_dropped += len(rs)
            continue
        if len(kept) < len(rs):
            n_sess_cut += 1
            turns_dropped += len(rs) - len(kept)
        turns_after += len(kept)
        recs = []
        for i, r in enumerate(kept):
            td = float(r.get("tool_duration_s", 0.0) or 0.0)
            if cap_tool_s > 0 and td > cap_tool_s:
                td = cap_tool_s
                tool_clamped += 1
            rec = {"session_id": sid, "turn": i,
                   "input_tokens": int(r["input_tokens"]),
                   "output_tokens": int(r.get("output_tokens", 0) or 0),
                   "tool_duration_s": round(td, 3)}
            if "cached_tokens" in r:
                rec["cached_tokens"] = int(r["cached_tokens"])
            recs.append(rec)
        if recs:
            recs[-1]["tool_duration_s"] = 0.0           # no trailing tool wait
        out.extend(recs)
    n_sess_kept = n_sess_total - n_sess_dropped_overflow
    stats = {
        "sessions_total": n_sess_total,
        "sessions_kept": n_sess_kept,                   # served (first turn fits L)
        "sessions_dropped_first_turn_overflow": n_sess_dropped_overflow,
        "inclusion_rate": round(n_sess_kept / n_sess_total, 4) if n_sess_total else None,
        "sessions_truncated": n_sess_cut,               # kept but cut mid-session
        "session_truncation_rate": round(n_sess_cut / n_sess_kept, 4) if n_sess_kept else None,
        "turns_before": turns_before,
        "turns_after": turns_after,
        "turns_dropped": turns_dropped,
        "turn_drop_rate": round(turns_dropped / turns_before, 4) if turns_before else None,
        "tool_values_clamped": tool_clamped,
    }
    return out, stats


def validate(recs):
    errs = []
    req = ("session_id", "turn", "input_tokens", "output_tokens", "tool_duration_s")
    last = {}
    for i, r in enumerate(recs):
        for k in req:
            if k not in r:
                errs.append(f"rec {i}: missing {k}")
        if r.get("tool_duration_s", 0) < 0:
            errs.append(f"rec {i}: negative tool_duration_s")
        if r.get("input_tokens", 0) <= 0:
            errs.append(f"rec {i}: non-positive input_tokens")
        sid = r.get("session_id")
        if sid in last and r["turn"] != last[sid] + 1:
            errs.append(f"session {sid}: turn not monotonic at {r['turn']}")
        last[sid] = r.get("turn", -1)
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp",
                    default="/home/yunuikang/yunuikang_work/scratch/traces/tracelab_trace_full.jsonl",
                    help="canonical per-turn JSONL (uncapped full trace); read-only")
    ap.add_argument("--out",
                    default="/home/yunuikang/yunuikang_work/scratch/traces/tracelab_earlycutoff_128k_yunuikang.jsonl")
    ap.add_argument("--limit", type=int, default=131072,
                    help="early-cutoff limit L = min(128k, 0.8*C_total); truncate "
                         "each session before input_tokens exceeds this")
    ap.add_argument("--cap-tool-s", type=float, default=300.0,
                    help="clamp tool_duration_s to at most this (value only, turn kept)")
    args = ap.parse_args()

    sessions = defaultdict(list)
    with open(args.inp, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            sessions[r["session_id"]].append(r)

    # pre-cut distributions (for the "distribution preserved" report)
    peak_before = [max(int(t["input_tokens"]) for t in rs) for rs in sessions.values()]

    recs, stats = early_cutoff(sessions, args.limit, args.cap_tool_s)
    errs = validate(recs)

    # post-cut distributions
    by_sess = defaultdict(list)
    for r in recs:
        by_sess[r["session_id"]].append(r)
    peak_after = [max(int(t["input_tokens"]) for t in rs) for rs in by_sess.values()]

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    meta = {
        "source": args.inp, "limit": args.limit, "cap_tool_s": args.cap_tool_s,
        "mode": "early-cutoff (per-session prefix truncation; first-turn-overflow sessions dropped)",
        "early_cut": stats,
        "peak_input_before": dist(peak_before),
        "peak_input_after": dist(peak_after),
        "tool_duration_after": dist([r["tool_duration_s"] for r in recs]),
        "input_tokens_after": dist([r["input_tokens"] for r in recs]),
        "schema_ok": not errs, "violations": errs[:10],
    }
    with open(args.out.rsplit(".", 1)[0] + ".meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(json.dumps({"out": args.out, "schema_ok": not errs, "meta": meta},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
