#!/usr/bin/env python3
"""Plot tr-vs-default sweep results into 3 PNGs for the meeting deck.

Reads two JSONL files (one per router) produced by workload_driver_yunuikang.py
and draws, vs concurrency:
  1) throughput (programs/s)
  2) p95 latency (s)
  3) KV prefix-cache hit rate   <- the key thrashing signal

Usage:
  plot_results_yunuikang.py --tr thrash_tr.jsonl --default thrash_default.jsonl \
     --outdir figures --tag thrash --title "KV pressure (ctx=3000)"
"""
import argparse
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    rows.sort(key=lambda d: d["concurrency"])
    return rows


def series(rows, key):
    xs = [d["concurrency"] for d in rows if d.get(key) is not None]
    ys = [d[key] for d in rows if d.get(key) is not None]
    return xs, ys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tr", required=True)
    ap.add_argument("--default", dest="default_", required=True)
    ap.add_argument("--outdir", default="figures")
    ap.add_argument("--tag", default="thrash")
    ap.add_argument("--title", default="")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    tr, df = load(args.tr), load(args.default_)
    suffix = f"  —  {args.title}" if args.title else ""

    panels = [
        ("throughput_programs_per_s", "Throughput (programs/s)", "throughput", "higher = better"),
        ("latency_p95_s", "p95 latency (s)", "p95_latency", "lower = better"),
        ("prefix_cache_hit_rate", "KV prefix-cache hit rate", "hit_rate", "higher = better"),
    ]
    written = []
    for key, ylabel, fname, note in panels:
        fig, ax = plt.subplots(figsize=(6.2, 4.2))
        for rows, label, style in ((tr, "tr (ThunderAgent)", "o-"), (df, "default", "s--")):
            xs, ys = series(rows, key)
            ax.plot(xs, ys, style, label=label, linewidth=2, markersize=6)
        ax.set_xlabel("concurrency (simultaneous programs)")
        ax.set_ylabel(ylabel)
        ax.set_title(f"{ylabel} vs concurrency{suffix}\n({note})", fontsize=10)
        ax.grid(True, alpha=0.3)
        ax.legend()
        if key == "prefix_cache_hit_rate":
            ax.set_ylim(0, 1)
        fig.tight_layout()
        out = os.path.join(args.outdir, f"{args.tag}_{fname}.png")
        fig.savefig(out, dpi=150)
        plt.close(fig)
        written.append(out)
    print("wrote:")
    for w in written:
        print(" ", w)


if __name__ == "__main__":
    main()
