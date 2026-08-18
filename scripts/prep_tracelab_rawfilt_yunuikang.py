#!/usr/bin/env python3
"""STEP 1 preprocessing for the MORI raw-log steady-state experiment.

PLAN: plans/2026-08-15_PLAN_rawlog-steadystate-mori-tp1_yunuikang.md  §3

WHAT THIS DOES
    base  = Track M primary (`tracelab_moriM_L64k_yunuikang.jsonl`) -- already
            turn-windowed to L=64k with tool/human-wait clamped at CAP_HARD=300s.
    filter= drop the WHOLE session if its replay wall >= --threshold-s (1800s).
    out   = `tracelab_rawfilt_yunuikang.jsonl` (+ .meta.json with the stats).

WHY THE BASE IS TRACK M, NOT THE ORIGINAL FULL TRACE
    The original full trace has per-turn input median ~124k tok, which exceeds the
    model context 71,680.  Re-windowing here would duplicate (and could diverge
    from) `prep_tracelab_mori_yunuikang.py`.  We take Track M as-is and only drop
    sessions.  Session internals are NEVER cut -- the session is the KV-locality
    unit (input_tokens accumulates monotonically across turns within a session).

SESSION WALL DEFINITION
    Identical to the `denom` of the iota computation in
    `prep_tracelab_mori_yunuikang.py:267` so the two scripts agree:

        wall = T_acting + T_reason
        T_acting = sum(tool_duration_s)                          [emitted per turn]
        T_reason = sum( (input_tokens - cached_tokens)/8000      REASON_PREFILL
                        + output_tokens/152 )                     REASON_DECODE

    T_reason is a PROXY (no timestamps exist in the trace); it is not measured
    serving time.  The proxy constants are imported from the upstream prep script
    so they cannot drift.

GUARDRAILS
    * Reads Track M read-only.  Writes only NEW `*_yunuikang` files.
    * CPU only, no GPU, no engine.
    * Does not modify the original trace or any existing script.
"""
import argparse
import hashlib
import json
import os
import sys
from collections import OrderedDict

import numpy as np

# reuse the upstream proxy constants verbatim (single source of truth)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prep_tracelab_mori_yunuikang import REASON_PREFILL, REASON_DECODE  # noqa: E402

TRACE_DIR = "/home/yunuikang/yunuikang_work/scratch/traces/"
DEFAULT_IN = TRACE_DIR + "tracelab_moriM_L64k_yunuikang.jsonl"
DEFAULT_OUT = TRACE_DIR + "tracelab_rawfilt_yunuikang.jsonl"
PS = [1, 5, 10, 25, 50, 75, 90, 95, 99]


def dist(a):
    """Percentile summary of a 1-D array (floats rounded for readability)."""
    a = np.asarray(a, float)
    if a.size == 0:
        return {"n": 0}
    d = {"n": int(a.size), "mean": round(float(a.mean()), 3),
         "min": round(float(a.min()), 3), "max": round(float(a.max()), 3)}
    for p in PS:
        d[f"p{p}"] = round(float(np.percentile(a, p)), 3)
    return d


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_sessions(path):
    """session_id -> list of turn records, in file order.  Session order preserved
    (Track M interleaves by iota-tercile; dropping must not reshuffle)."""
    sess = OrderedDict()
    n_rows = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            sess.setdefault(r["session_id"], []).append(r)
            n_rows += 1
    return sess, n_rows


def session_stats(turns):
    """Per-session aggregates used by the filter and the reported distributions."""
    t_acting = 0.0
    t_reason = 0.0
    peak_ctx = 0
    for r in turns:
        t_acting += float(r["tool_duration_s"])
        unc = max(int(r["input_tokens"]) - int(r["cached_tokens"]), 0)
        t_reason += unc / REASON_PREFILL + int(r["output_tokens"]) / REASON_DECODE
        peak_ctx = max(peak_ctx, int(r["input_tokens"]))
    return {"n_turns": len(turns),
            "t_acting_s": t_acting,
            "t_reason_s": t_reason,
            "wall_s": t_acting + t_reason,
            "peak_ctx_tokens": peak_ctx}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=DEFAULT_IN)
    ap.add_argument("--out", dest="out", default=DEFAULT_OUT)
    ap.add_argument("--threshold-s", type=float, default=1800.0,
                    help="drop the session if wall >= this (default 1800 = 30 min)")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute + print stats, write nothing")
    args = ap.parse_args()

    print(f"[0] in={args.inp}", flush=True)
    print(f"    threshold={args.threshold_s}s  "
          f"proxy: uncached/{REASON_PREFILL:.0f} + output/{REASON_DECODE:.0f}", flush=True)

    sess, n_rows_in = load_sessions(args.inp)
    print(f"[1] loaded sessions={len(sess)} turns={n_rows_in}", flush=True)

    stats = {sid: session_stats(t) for sid, t in sess.items()}
    keep = [sid for sid in sess if stats[sid]["wall_s"] < args.threshold_s]
    drop = [sid for sid in sess if stats[sid]["wall_s"] >= args.threshold_s]

    n_turns_keep = sum(stats[s]["n_turns"] for s in keep)
    n_turns_drop = sum(stats[s]["n_turns"] for s in drop)

    # per-turn input_tokens over the KEPT sessions -> this is s_ctx
    kept_inputs = np.array([int(r["input_tokens"]) for s in keep for r in sess[s]], dtype=np.int64)
    all_inputs = np.array([int(r["input_tokens"]) for s in sess for r in sess[s]], dtype=np.int64)
    s_ctx = int(np.median(kept_inputs)) if kept_inputs.size else 0

    report = {
        "input_file": args.inp,
        "input_sha256": sha256(args.inp),
        "threshold_s": args.threshold_s,
        "wall_definition": "sum(tool_duration_s) + sum((input-cached)/%.0f + output/%.0f)"
                           % (REASON_PREFILL, REASON_DECODE),
        "before": {"sessions": len(sess), "turns": n_rows_in},
        "dropped": {"sessions": len(drop), "turns": n_turns_drop},
        "after": {"sessions": len(keep), "turns": n_turns_keep},
        "retention": {
            "sessions_pct": round(100.0 * len(keep) / max(len(sess), 1), 3),
            "turns_pct": round(100.0 * n_turns_keep / max(n_rows_in, 1), 3),
        },
        "s_ctx_tokens": s_ctx,
        "s_ctx_note": "per-turn input_tokens median over KEPT sessions (= fit denominator)",
        "per_turn_input_tokens": {
            "kept": dist(kept_inputs),
            "all_before_filter": dist(all_inputs),
        },
        "session_peak_ctx_tokens": {
            "kept": dist([stats[s]["peak_ctx_tokens"] for s in keep]),
            "dropped": dist([stats[s]["peak_ctx_tokens"] for s in drop]),
        },
        "session_wall_s": {
            "kept": dist([stats[s]["wall_s"] for s in keep]),
            "dropped": dist([stats[s]["wall_s"] for s in drop]),
            "all_before_filter": dist([stats[s]["wall_s"] for s in sess]),
        },
        "session_t_acting_s_kept": dist([stats[s]["t_acting_s"] for s in keep]),
        "session_t_reason_s_kept": dist([stats[s]["t_reason_s"] for s in keep]),
        "session_turns_kept": dist([stats[s]["n_turns"] for s in keep]),
    }

    print("\n########## FILTER STATS ##########")
    print(json.dumps({k: report[k] for k in
                      ("before", "dropped", "after", "retention", "s_ctx_tokens")}, indent=2))
    print("\nper-turn input_tokens (kept)      :", json.dumps(report["per_turn_input_tokens"]["kept"]))
    print("per-turn input_tokens (before)    :", json.dumps(report["per_turn_input_tokens"]["all_before_filter"]))
    print("session peak ctx tokens (kept)    :", json.dumps(report["session_peak_ctx_tokens"]["kept"]))
    print("session peak ctx tokens (dropped) :", json.dumps(report["session_peak_ctx_tokens"]["dropped"]))
    print("session wall_s (kept)             :", json.dumps(report["session_wall_s"]["kept"]))
    print("session wall_s (dropped)          :", json.dumps(report["session_wall_s"]["dropped"]))
    print("session wall_s (before filter)    :", json.dumps(report["session_wall_s"]["all_before_filter"]))
    print("session turns (kept)              :", json.dumps(report["session_turns_kept"]))

    if args.dry_run:
        print("\n[dry-run] nothing written")
        return

    with open(args.out, "w") as f:
        for sid in keep:
            for i, r in enumerate(sess[sid]):
                # re-emit verbatim; `turn` is already 0..n-1 and sessions are not cut,
                # so indices are unchanged.  assert rather than silently renumber.
                assert int(r["turn"]) == i, f"non-contiguous turn in {sid}"
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    report["output_file"] = args.out
    report["output_sha256"] = sha256(args.out)
    meta = os.path.splitext(args.out)[0] + ".meta.json"
    with open(meta, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\noutputs:\n  {args.out}\n  {meta}")
    print(f"  out sha256 = {report['output_sha256']}")


if __name__ == "__main__":
    main()
