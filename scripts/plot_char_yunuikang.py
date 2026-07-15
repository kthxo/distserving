#!/usr/bin/env python3
"""Workload characterization plots for the ThunderAgent synthetic benchmark.

Reads per-turn JSONL traces produced by workload_driver_yunuikang.py --trace-out
and draws 4 PNGs:
  1) char_tokens.png        input / output token distributions
  2) char_lifetime.png      per-program lifetime distribution
  3) char_turn_breakdown.png per-turn prefill(TTFT)/decode/tool split (clean, c=1)
  4) char_kv.png            KV footprint growth + GPU-capacity fit

All token counts come from the OpenAI `usage` field (measured). Prefill/decode
are the streaming-TTFT approximation (prefill ~= TTFT, decode = latency - TTFT);
use the low-concurrency (c=1) trace so queueing does not contaminate them.
KV bytes/token and GPU fit are computed from the real Qwen3-8B config + the KV
pool size vLLM reported at startup (measured).

Usage:
  plot_char_yunuikang.py --load scratch/char_trace.jsonl \
      --clean scratch/char_trace_c1.jsonl --outdir figures
"""
import argparse
import json
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# --- real constants (measured / computed from config) ---
KV_BYTES_PER_TOKEN = 2 * 36 * 8 * 128 * 2      # K,V x layers x kv_heads x head_dim x bf16 = 147456 B (144 KiB)
GIB = 1024 ** 3
POOL_4090_TOKENS = 43888                        # vLLM startup log, 24GB@util0.92, max_model_len 32768
POOL_4090_GIB = POOL_4090_TOKENS * KV_BYTES_PER_TOKEN / GIB   # == 6.03 GiB (cross-check)
# 5090 (32GB) ESTIMATE: non-KV footprint (weights+activation+overhead) held fixed
NONKV_GIB = 24 * 0.92 - POOL_4090_GIB
POOL_5090_GIB = 32 * 0.92 - NONKV_GIB
POOL_5090_TOKENS = int(POOL_5090_GIB * GIB / KV_BYTES_PER_TOKEN)

BLUE = "#2E5A87"
LIGHT = "#7FA8CC"
ORANGE = "#D08C3A"
GREEN = "#4E8C6A"


def load(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def by_program(rows):
    prog = defaultdict(list)
    for r in rows:
        prog[r["program_id"]].append(r)
    for v in prog.values():
        v.sort(key=lambda r: r["turn"])
    return prog


def by_turn(rows, key):
    d = defaultdict(list)
    for r in rows:
        if r.get(key) is not None:
            d[r["turn"]].append(r[key])
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--load", required=True, help="under-load trace (e.g. c=8)")
    ap.add_argument("--clean", required=True, help="low-concurrency trace (e.g. c=1) for prefill/decode")
    ap.add_argument("--outdir", default="figures")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    rows = load(args.load)
    clean = load(args.clean)
    prog = by_program(rows)
    written = []

    # ---------- 1) token distributions ----------
    prompt = [r["prompt_tokens"] for r in rows]
    compl = [r["completion_tokens"] for r in rows]
    out_per_prog = [sum(t["completion_tokens"] for t in ts) for ts in prog.values()]
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.8))
    ax[0].hist(prompt, bins=25, color=BLUE, edgecolor="white")
    ax[0].set_title(f"Input tokens per turn\n(mean {sum(prompt)/len(prompt):.0f})", fontsize=10)
    ax[0].set_xlabel("prompt_tokens"); ax[0].set_ylabel("# turns")
    ax[1].hist(compl, bins=25, color=ORANGE, edgecolor="white")
    ax[1].set_title(f"Output tokens per turn\n(mean {sum(compl)/len(compl):.1f})", fontsize=10)
    ax[1].set_xlabel("completion_tokens"); ax[1].set_ylabel("# turns")
    ax[2].hist(out_per_prog, bins=15, color=GREEN, edgecolor="white")
    ax[2].set_title(f"Output tokens per program\n(mean {sum(out_per_prog)/len(out_per_prog):.0f})", fontsize=10)
    ax[2].set_xlabel("total completion_tokens"); ax[2].set_ylabel("# programs")
    fig.suptitle("Workload token distribution  (Qwen3-8B, ctx=3000 filler, measured from usage)", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    p = os.path.join(args.outdir, "char_tokens.png"); fig.savefig(p, dpi=150); plt.close(fig); written.append(p)

    # ---------- 2) program lifetime ----------
    life = [sum(t["turn_latency_s"] for t in ts) + sum(t["tool_sleep_s"] for t in ts) for ts in prog.values()]
    turns = [len(ts) for ts in prog.values()]
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    ax.hist(life, bins=15, color=BLUE, edgecolor="white")
    ax.axvline(sum(life)/len(life), color=ORANGE, ls="--", lw=2,
               label=f"mean {sum(life)/len(life):.1f}s")
    ax.set_xlabel("program lifetime (s)  =  Σ turn latency + Σ tool time")
    ax.set_ylabel("# programs")
    ax.set_title(f"Task (program) lifetime distribution\n{len(prog)} programs, "
                 f"{turns[0]} turns each (fixed) — under load c=8", fontsize=10)
    ax.legend(); ax.grid(True, alpha=0.3)
    fig.tight_layout()
    p = os.path.join(args.outdir, "char_lifetime.png"); fig.savefig(p, dpi=150); plt.close(fig); written.append(p)

    # ---------- 3) per-turn prefill/decode/tool (clean, c=1) ----------
    tt = by_turn(clean, "ttft_s"); dt = by_turn(clean, "decode_s")
    tl = by_turn(clean, "tool_sleep_s")
    turn_ids = sorted(tt.keys())
    mean = lambda xs: sum(xs) / len(xs) if xs else 0.0
    pref = [mean(tt[i]) for i in turn_ids]
    dec = [mean(dt[i]) for i in turn_ids]
    tool = [mean(tl[i]) for i in turn_ids]
    fig, ax = plt.subplots(figsize=(6.8, 4.4))
    x = range(len(turn_ids))
    b1 = ax.bar(x, pref, color=BLUE, label="prefill (~TTFT)")
    b2 = ax.bar(x, dec, bottom=pref, color=LIGHT, label="decode")
    b3 = ax.bar(x, tool, bottom=[p + d for p, d in zip(pref, dec)], color=ORANGE, label="tool (sleep)")
    ax.set_xticks(list(x)); ax.set_xticklabels([f"turn {i}" for i in turn_ids])
    ax.set_ylabel("time (s)")
    ax.set_title("Per-turn time breakdown  (clean, c=1 → no queueing)\n"
                 "prefill ~= TTFT, decode = latency − TTFT, tool = sleep", fontsize=10)
    ax.legend(); ax.grid(True, axis="y", alpha=0.3)
    for i in x:
        tot = pref[i] + dec[i] + tool[i]
        ax.text(i, tot + 0.1, f"{tot:.1f}s", ha="center", fontsize=8)
    fig.tight_layout()
    p = os.path.join(args.outdir, "char_turn_breakdown.png"); fig.savefig(p, dpi=150); plt.close(fig); written.append(p)

    # ---------- 4) KV footprint growth + capacity fit ----------
    seq_by_turn = by_turn(rows, "seq_tokens")
    turn_ids2 = sorted(seq_by_turn.keys())
    seq_mean = [mean(seq_by_turn[i]) for i in turn_ids2]
    seq_min = [min(seq_by_turn[i]) for i in turn_ids2]
    seq_max = [max(seq_by_turn[i]) for i in turn_ids2]
    peak = [max(t["seq_tokens"] for t in ts) for ts in prog.values()]
    peak_mean = sum(peak) / len(peak)

    fig, ax = plt.subplots(1, 2, figsize=(12.5, 4.4))
    # (a) growth over turns
    ax[0].plot(turn_ids2, seq_mean, "o-", color=BLUE, lw=2, label="mean seq length")
    ax[0].fill_between(turn_ids2, seq_min, seq_max, color=LIGHT, alpha=0.4, label="min–max")
    ax[0].set_xlabel("turn"); ax[0].set_ylabel("KV footprint (tokens)")
    ax[0].set_xticks(turn_ids2)
    ax[0].set_title("KV cache growth within a program\n(sequence length after each turn)", fontsize=10)
    ax[0].legend(); ax[0].grid(True, alpha=0.3)
    secax = ax[0].secondary_yaxis('right', functions=(
        lambda t: t * KV_BYTES_PER_TOKEN / GIB, lambda g: g * GIB / KV_BYTES_PER_TOKEN))
    secax.set_ylabel("KV (GiB)")
    # (b) capacity fit
    peak_gib = peak_mean * KV_BYTES_PER_TOKEN / GIB
    fit_4090 = POOL_4090_TOKENS / peak_mean
    fit_5090 = POOL_5090_TOKENS / peak_mean
    labels = ["1 program\n(peak)", "4090 pool\n(measured)", "5090 pool\n(est.)"]
    vals = [peak_gib, POOL_4090_GIB, POOL_5090_GIB]
    colors = [GREEN, BLUE, ORANGE]
    bars = ax[1].bar(labels, vals, color=colors, edgecolor="white")
    ax[1].set_ylabel("KV memory (GiB)")
    ax[1].set_title(f"KV capacity: only ~{fit_4090:.1f} programs fit on a 4090\n"
                    f"(1 program ≈ {peak_mean:.0f} tok ≈ {peak_gib:.2f} GiB)", fontsize=10)
    ax[1].grid(True, axis="y", alpha=0.3)
    ax[1].text(1, POOL_4090_GIB + 0.15, f"{POOL_4090_TOKENS:,} tok\n≈{fit_4090:.1f} progs", ha="center", fontsize=8)
    ax[1].text(2, POOL_5090_GIB + 0.15, f"~{POOL_5090_TOKENS:,} tok\n≈{fit_5090:.1f} progs", ha="center", fontsize=8)
    ax[1].text(0, peak_gib + 0.15, f"{peak_mean:.0f} tok", ha="center", fontsize=8)
    fig.tight_layout()
    p = os.path.join(args.outdir, "char_kv.png"); fig.savefig(p, dpi=150); plt.close(fig); written.append(p)

    print("KV bytes/token =", KV_BYTES_PER_TOKEN, f"({KV_BYTES_PER_TOKEN/1024:.0f} KiB)")
    print(f"4090 pool = {POOL_4090_TOKENS:,} tok = {POOL_4090_GIB:.2f} GiB  -> {fit_4090:.2f} programs")
    print(f"5090 pool (est) = {POOL_5090_TOKENS:,} tok = {POOL_5090_GIB:.2f} GiB -> {fit_5090:.2f} programs")
    print(f"peak seq/program = {peak_mean:.0f} tok = {peak_gib:.2f} GiB")
    print("wrote:"); [print(" ", w) for w in written]


if __name__ == "__main__":
    main()
