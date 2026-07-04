#!/usr/bin/env python3
"""Phase F (homo-hetero, 4090+5090) plots from run_hetero_sweep output.

Reads homo_hetero_{tr,default}.jsonl (per-backend metrics) and draws, vs concurrency:
  1) global throughput: tr vs default
  2) PER-BACKEND KV prefix-cache hit rate: {tr,default} x {4090,5090}  <- key panel
  3) PER-BACKEND reprefill (prefix-cache queries, M): the small-GPU-thrash signal
  4) PER-BACKEND peak KV usage
"""
import argparse
import json
import os
from collections import defaultdict
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load_agg(path):
    rows = [json.loads(l) for l in open(path)]
    by = defaultdict(list)
    for r in rows:
        by[r["concurrency"]].append(r)
    cs = sorted(by)
    def series(fn):
        return [statistics.mean(fn(x) for x in by[c]) for c in cs]
    return cs, by, series


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tr", required=True)
    ap.add_argument("--default", dest="default_", required=True)
    ap.add_argument("--outdir", default="figures")
    ap.add_argument("--tag", default="homo_hetero")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    cs, tr, trs = load_agg(args.tr)
    _, df, dfs = load_agg(args.default_)
    written = []

    def save(fig, name):
        out = os.path.join(args.outdir, f"{args.tag}_{name}.png")
        fig.tight_layout(); fig.savefig(out, dpi=150); plt.close(fig); written.append(out)

    # 1) global throughput tr vs default
    fig, ax = plt.subplots(figsize=(6.2, 4.2))
    ax.plot(cs, trs(lambda x: x["throughput_programs_per_s"]), "o-", label="tr (ThunderAgent)", lw=2)
    ax.plot(cs, dfs(lambda x: x["throughput_programs_per_s"]), "s--", label="default", lw=2)
    ax.set_xlabel("concurrency"); ax.set_ylabel("throughput (programs/s)")
    ax.set_title("Throughput vs concurrency  —  4090+5090 hetero\n(higher = better)", fontsize=10)
    ax.grid(alpha=0.3); ax.legend(); save(fig, "throughput")

    # 2) per-backend hit rate (key panel): 4 lines
    fig, ax = plt.subplots(figsize=(6.6, 4.4))
    ax.plot(cs, trs(lambda x: x["per_backend"]["4090"]["hit_rate"] or 0), "o-", color="tab:blue", label="tr · 4090", lw=2)
    ax.plot(cs, trs(lambda x: x["per_backend"]["5090"]["hit_rate"] or 0), "o-", color="tab:cyan", label="tr · 5090", lw=2)
    ax.plot(cs, dfs(lambda x: x["per_backend"]["4090"]["hit_rate"] or 0), "s--", color="tab:red", label="default · 4090", lw=2)
    ax.plot(cs, dfs(lambda x: x["per_backend"]["5090"]["hit_rate"] or 0), "s--", color="tab:orange", label="default · 5090", lw=2)
    ax.set_xlabel("concurrency"); ax.set_ylabel("KV prefix-cache hit rate"); ax.set_ylim(0, 1)
    ax.set_title("Per-backend KV hit rate  —  4090 vs 5090\n(tr keeps both ~0.67; default's 4090 collapses)", fontsize=10)
    ax.grid(alpha=0.3); ax.legend(fontsize=8); save(fig, "perbackend_hitrate")

    # 3) per-backend reprefill (queries, millions)
    fig, ax = plt.subplots(figsize=(6.6, 4.4))
    ax.plot(cs, trs(lambda x: x["per_backend"]["4090"]["queries_delta"]/1e6), "o-", color="tab:blue", label="tr · 4090", lw=2)
    ax.plot(cs, trs(lambda x: x["per_backend"]["5090"]["queries_delta"]/1e6), "o-", color="tab:cyan", label="tr · 5090", lw=2)
    ax.plot(cs, dfs(lambda x: x["per_backend"]["4090"]["queries_delta"]/1e6), "s--", color="tab:red", label="default · 4090", lw=2)
    ax.plot(cs, dfs(lambda x: x["per_backend"]["5090"]["queries_delta"]/1e6), "s--", color="tab:orange", label="default · 5090", lw=2)
    ax.set_xlabel("concurrency"); ax.set_ylabel("prefix-cache queries (millions)")
    ax.set_title("Per-backend reprefill load  —  4090 vs 5090\n(default hammers the small 4090 ~4x)", fontsize=10)
    ax.grid(alpha=0.3); ax.legend(fontsize=8); save(fig, "perbackend_reprefill")

    # 4) per-backend peak KV usage
    fig, ax = plt.subplots(figsize=(6.6, 4.4))
    ax.plot(cs, trs(lambda x: x["per_backend"]["4090"]["kv_usage_peak"]), "o-", color="tab:blue", label="tr · 4090", lw=2)
    ax.plot(cs, trs(lambda x: x["per_backend"]["5090"]["kv_usage_peak"]), "o-", color="tab:cyan", label="tr · 5090", lw=2)
    ax.plot(cs, dfs(lambda x: x["per_backend"]["4090"]["kv_usage_peak"]), "s--", color="tab:red", label="default · 4090", lw=2)
    ax.plot(cs, dfs(lambda x: x["per_backend"]["5090"]["kv_usage_peak"]), "s--", color="tab:orange", label="default · 5090", lw=2)
    ax.set_xlabel("concurrency"); ax.set_ylabel("peak KV cache usage"); ax.set_ylim(0, 1.05)
    ax.set_title("Per-backend peak KV usage  —  4090 vs 5090", fontsize=10)
    ax.grid(alpha=0.3); ax.legend(fontsize=8); save(fig, "perbackend_kv_usage")

    print("wrote:")
    for w in written:
        print(" ", w)


if __name__ == "__main__":
    main()
