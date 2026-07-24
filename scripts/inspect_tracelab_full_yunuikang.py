#!/usr/bin/env python3
"""Inspect the FULL (uncapped) normalized TraceLab trace to decide cap policy.

STEP 0 of PLAN 2026-07-23 (tracelab-uncapped-2x5090). GPU-free.

Reads the canonical per-turn JSONL produced by prep_tracelab_yunuikang.py with
NO --max-input-tokens and NO --cap-tool-s (i.e. tracelab_trace_full.jsonl).

Reports, so the cap policy + max-model-len can be chosen on evidence:
  1. per-PROGRAM (session) peak input-token distribution  -> fit denominator (ctx)
  2. per-STEP (turn) input-token distribution
  3. tool_duration_s distribution + fraction of turns above 30/300/3600 s
  4. how many sessions / turns a 32768 input cap would DROP (capping-artifact size)
"""
import argparse
import json
import statistics
from collections import defaultdict


def pct(sorted_vals, q):
    if not sorted_vals:
        return None
    i = min(len(sorted_vals) - 1, int(round(q * (len(sorted_vals) - 1))))
    return sorted_vals[i]


def dist(vals):
    """min/median/mean/p95/p99/max over a list of numbers."""
    if not vals:
        return None
    s = sorted(vals)
    return {
        "n": len(s),
        "min": s[0],
        "median": statistics.median(s),
        "mean": round(statistics.mean(s), 2),
        "p95": pct(s, 0.95),
        "p99": pct(s, 0.99),
        "max": s[-1],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp",
                    default="/home/yunuikang/yunuikang_work/scratch/traces/tracelab_trace_full.jsonl")
    ap.add_argument("--input-cap", type=int, default=32768,
                    help="hypothetical per-turn input cap to measure drop rate")
    args = ap.parse_args()

    by_sess = defaultdict(list)   # session_id -> list of turn dicts
    step_inputs = []              # every turn's input_tokens
    tool_s = []                   # every turn's tool_duration_s
    n_turns = 0
    with open(args.inp, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            by_sess[r["session_id"]].append(r)
            step_inputs.append(int(r["input_tokens"]))
            tool_s.append(float(r["tool_duration_s"]))
            n_turns += 1

    # per-program (session) aggregates
    peak_input = []               # max input_tokens per session  (= ctx / fit denom)
    turns_per_session = []
    for sid, rs in by_sess.items():
        peak_input.append(max(int(r["input_tokens"]) for r in rs))
        turns_per_session.append(len(rs))

    # tool tail fractions
    def frac_above(thr):
        c = sum(1 for t in tool_s if t > thr)
        return {"count": c, "frac": round(c / len(tool_s), 6)} if tool_s else None

    # capping-artifact: sessions/turns a per-turn input cap would drop
    # (prep drops the WHOLE session if ANY turn's input exceeds the cap)
    cap = args.input_cap
    dropped_sessions = 0
    dropped_turns = 0
    for sid, rs in by_sess.items():
        if max(int(r["input_tokens"]) for r in rs) > cap:
            dropped_sessions += 1
            dropped_turns += len(rs)

    # cap sweep: for candidate max-model-len values, how much survives and what
    # is the fit denominator (median/p95 peak input) AMONG SURVIVORS.
    # A session survives only if its peak input <= cap (prep is session-level).
    sess_peaks = [(sid, max(int(r["input_tokens"]) for r in rs), len(rs))
                  for sid, rs in by_sess.items()]
    cap_sweep = {}
    for c in [32768, 40960, 65536, 98304, 131072, 262144]:
        surv = [(p, nt) for (_sid, p, nt) in sess_peaks if p <= c]
        surv_peaks = [p for (p, _nt) in surv]
        surv_turns = sum(nt for (_p, nt) in surv)
        cap_sweep[str(c)] = {
            "surv_sessions": len(surv),
            "surv_sessions_frac": round(len(surv) / len(by_sess), 4),
            "surv_turns": surv_turns,
            "surv_turns_frac": round(surv_turns / n_turns, 4),
            "surv_peak_median__ctx_for_fit": statistics.median(surv_peaks) if surv_peaks else None,
            "surv_peak_p95": pct(sorted(surv_peaks), 0.95) if surv_peaks else None,
        }

    out = {
        "input_file": args.inp,
        "cap_sweep__mml_candidates": cap_sweep,
        "totals": {
            "sessions": len(by_sess),
            "turns": n_turns,
        },
        "turns_per_session": dist(turns_per_session),
        "peak_input_per_program__FIT_DENOM": dist(peak_input),
        "step_input_per_turn": dist(step_inputs),
        "tool_duration_s": dist(tool_s),
        "tool_tail": {
            ">30s": frac_above(30),
            ">300s": frac_above(300),
            ">3600s (multi-hour)": frac_above(3600),
        },
        "input_cap_%d_drop" % cap: {
            "dropped_sessions": dropped_sessions,
            "dropped_sessions_frac": round(dropped_sessions / len(by_sess), 6),
            "dropped_turns": dropped_turns,
            "dropped_turns_frac": round(dropped_turns / n_turns, 6),
            "note": "prep drops whole session if ANY turn input > cap (session-level fit filter)",
        },
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
