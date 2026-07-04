#!/usr/bin/env python3
"""TraceLab workload characterization (mirrors §10 homo-homo synthetic method).

Panels (figures/char_tracelab_*.png), each overlaying the homo-homo synthetic
reference (logs/2026-07-02_EXPERIMENT_LOG_yunuikang.md §10) for contrast:
  1) tokens        : per-turn input & output token histograms
  2) kv            : per-session peak KV (GiB) hist vs 4090/5090 pool lines
  3) lifetime      : per-session lifetime distribution        (needs --profile-trace)
  4) turn_breakdown: per-turn-index prefill(TTFT)/decode/tool (needs --profile-trace)

Inputs:
  --trace          canonical tracelab jsonl (tokens + KV, per-turn)
  --profile-trace  driver --trace-out from a c=1 --stream run (ttft_s/decode_s/turn_latency_s)
  --tool-from-trace  (for lifetime) add per-turn tool_duration_s from --trace
"""
import argparse
import json
import os
import statistics
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

KIB_PER_TOK_GIB = 144 / 1024 / 1024        # 144 KiB/token -> GiB/token (Qwen3-8B)
POOL_4090_GIB, POOL_5090_GIB = 6.03, 12.23
# homo-homo synthetic reference (§10)
HOMO = dict(input_mean=14558, output_mean=28.6, tool_s=0.4, peak_gib=2.01,
            lifetime_s=63.8, prefill_cold=1.82, prefill_warm=0.13, decode_s=0.5)


def load(path):
    return [json.loads(l) for l in open(path)]


def med_p95(v):
    s = sorted(v)
    return statistics.median(s), s[min(len(s) - 1, int(0.95 * (len(s) - 1)))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", required=True)
    ap.add_argument("--profile-trace", default="")
    ap.add_argument("--outdir", default="figures")
    ap.add_argument("--tag", default="char_tracelab")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    rows = load(args.trace)
    sess = defaultdict(list)
    for r in rows:
        sess[r["session_id"]].append(r)
    written = []

    def save(fig, name):
        out = os.path.join(args.outdir, f"{args.tag}_{name}.png")
        fig.tight_layout(); fig.savefig(out, dpi=150); plt.close(fig); written.append(out)

    # 1) tokens
    IN = [r["input_tokens"] for r in rows]
    OUT = [r["output_tokens"] for r in rows]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4))
    a1.hist(IN, bins=40, color="tab:blue", alpha=0.8)
    im, ip = med_p95(IN)
    a1.axvline(im, color="k", ls="-", lw=1.5, label=f"median {im:,.0f}")
    a1.axvline(HOMO["input_mean"], color="tab:red", ls="--", lw=2, label=f"homo synth ~{HOMO['input_mean']:,}")
    a1.set_title(f"input tokens / turn  (median {im:,.0f}, p95 {ip:,.0f})", fontsize=10)
    a1.set_xlabel("input tokens"); a1.legend(fontsize=8)
    a2.hist(OUT, bins=40, color="tab:green", alpha=0.8)
    om, op = med_p95(OUT)
    a2.axvline(om, color="k", ls="-", lw=1.5, label=f"median {om:,.0f}")
    a2.axvline(HOMO["output_mean"], color="tab:red", ls="--", lw=2, label=f"homo synth ~{HOMO['output_mean']:.0f}")
    a2.set_title(f"output tokens / turn  (median {om:,.0f}, p95 {op:,.0f})", fontsize=10)
    a2.set_xlabel("output tokens"); a2.set_yscale("log"); a2.legend(fontsize=8)
    fig.suptitle("TraceLab per-turn token distribution vs homo-homo synthetic", fontsize=11)
    save(fig, "tokens")

    # 2) kv: per-session peak KV (GiB)
    peak = [max(r["input_tokens"] for r in v) * KIB_PER_TOK_GIB for v in sess.values()]
    pm, pp = med_p95(peak)
    fig, ax = plt.subplots(figsize=(7, 4.4))
    ax.hist(peak, bins=40, color="tab:purple", alpha=0.8)
    ax.axvline(POOL_4090_GIB, color="tab:red", ls="-", lw=2, label=f"4090 KV pool {POOL_4090_GIB} GiB")
    ax.axvline(POOL_5090_GIB, color="tab:orange", ls="-", lw=2, label=f"5090 KV pool {POOL_5090_GIB} GiB")
    ax.axvline(HOMO["peak_gib"], color="k", ls="--", lw=1.5, label=f"homo synth peak {HOMO['peak_gib']} GiB")
    ax.set_title(f"Per-program peak KV footprint  (median {pm:.2f} GiB, p95 {pp:.2f})\n"
                 f"→ 4090 pool holds ~{POOL_4090_GIB/pm:.1f} programs; 5090 ~{POOL_5090_GIB/pm:.1f}", fontsize=10)
    ax.set_xlabel("peak KV per program (GiB)"); ax.set_ylabel("sessions"); ax.legend(fontsize=8)
    save(fig, "kv")

    # 3+4) profile-based panels
    if args.profile_trace and os.path.exists(args.profile_trace):
        prof = load(args.profile_trace)
        pbyp = defaultdict(list)
        for r in prof:
            pbyp[r["program_id"]].append(r)
        # tool per (program_id, turn) from canonical trace, matched by session
        tool_by = {}
        for r in rows:
            tool_by[(r["session_id"], r["turn"])] = r["tool_duration_s"]

        # lifetime = sum(turn_latency measured) + sum(tool from trace)
        lifes = []
        for pid, ts in pbyp.items():
            sid = pid.split("#")[0]
            comp = sum(t.get("turn_latency_s") or 0 for t in ts)
            tool = sum(tool_by.get((sid, t["turn"]), 0) for t in ts)
            lifes.append(comp + tool)
        lm, lp = med_p95(lifes)
        fig, ax = plt.subplots(figsize=(7, 4.2))
        ax.hist(lifes, bins=30, color="teal", alpha=0.8)
        ax.axvline(lm, color="k", lw=1.5, label=f"median {lm:.1f}s")
        ax.axvline(HOMO["lifetime_s"], color="tab:red", ls="--", lw=2, label=f"homo synth ~{HOMO['lifetime_s']}s (c=8)")
        ax.set_title(f"Per-program lifetime  (median {lm:.1f}s, p95 {lp:.1f}s)\n"
                     f"= measured compute + tool_duration (c=1)", fontsize=10)
        ax.set_xlabel("program lifetime (s)"); ax.set_ylabel("programs"); ax.legend(fontsize=8)
        save(fig, "lifetime")

        # turn breakdown by turn index: prefill(ttft), decode, tool
        by_turn = defaultdict(lambda: {"prefill": [], "decode": [], "tool": []})
        for pid, ts in pbyp.items():
            sid = pid.split("#")[0]
            for t in ts:
                ti = t["turn"]
                if t.get("ttft_s") is not None:
                    by_turn[ti]["prefill"].append(t["ttft_s"])
                if t.get("decode_s") is not None:
                    by_turn[ti]["decode"].append(t["decode_s"])
                by_turn[ti]["tool"].append(tool_by.get((sid, ti), 0))
        turns = sorted(k for k in by_turn if k <= 7)
        pf = [statistics.mean(by_turn[t]["prefill"]) if by_turn[t]["prefill"] else 0 for t in turns]
        dc = [statistics.mean(by_turn[t]["decode"]) if by_turn[t]["decode"] else 0 for t in turns]
        tl = [statistics.mean(by_turn[t]["tool"]) if by_turn[t]["tool"] else 0 for t in turns]
        fig, ax = plt.subplots(figsize=(7.5, 4.4))
        ax.bar(turns, pf, label="prefill (TTFT)", color="tab:blue")
        ax.bar(turns, dc, bottom=pf, label="decode", color="tab:green")
        ax.bar(turns, tl, bottom=[p + d for p, d in zip(pf, dc)], label="tool", color="tab:orange")
        ax.set_xlabel("turn index"); ax.set_ylabel("mean seconds")
        ax.set_title("Per-turn time breakdown (c=1): prefill / decode / tool\n"
                     f"(homo synth §10: turn0 prefill {HOMO['prefill_cold']}s cold, warm {HOMO['prefill_warm']}s)",
                     fontsize=10)
        ax.legend(fontsize=8)
        save(fig, "turn_breakdown")

    print("wrote:")
    for w in written:
        print(" ", w)


if __name__ == "__main__":
    main()
