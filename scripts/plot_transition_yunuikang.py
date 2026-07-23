#!/usr/bin/env python3
"""STEP 5 — Transition point figure: wall/p95/hit/GPU vs fit×d.

Reads main sweep results + pilot data, produces a 4-panel figure showing
where the optimal policy flips from default(f=∞) to tr(f=1).

작성: 강윤의 · 2026-07-20
"""
import json
import math
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

SWEEP_FILE = "scratch/step5/main_sweep/sweep_results.jsonl"
PILOT_D01 = "scratch/step5/pilot/pilot_results.jsonl"
PILOT_D02 = "scratch/step5/pilot_d02/pilot_results.jsonl"
PILOT_D05 = "scratch/step5/pilot_d05/pilot_results.jsonl"
OUT_FIG = "figures/step5_transition_yunuikang.png"

FIT = 95936 / 20150


def load_jsonl(path):
    results = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(json.loads(line))
    return results


def mean(vals):
    return sum(vals) / len(vals) if vals else 0


def std(vals):
    m = mean(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals)) if len(vals) > 1 else 0


def main():
    # 1. Load main sweep
    sweep = load_jsonl(SWEEP_FILE)

    # Group by (fitd, C, policy)
    groups = defaultdict(list)
    for r in sweep:
        pol = "tr" if r["f"] < 1000 else "def"
        key = (r["fitd"], r["C"], pol)
        groups[key].append(r)

    # 2. Load pilot data (convert to fitd)
    pilot_points = []

    # d=0.1 pilot → fitd ≈ 0.476
    for r in load_jsonl(PILOT_D01):
        pol = "tr" if r["f"] < 1000 else "def"
        fd = r.get("duty", 0.1) * FIT
        r["fitd"] = round(fd, 3)
        pilot_points.append((fd, r["C"], pol, r))

    # d=0.2 pilot → fitd ≈ 0.952
    for r in load_jsonl(PILOT_D02):
        pol = "tr" if r["f"] < 1000 else "def"
        fd = r.get("duty", 0.2) * FIT
        r["fitd"] = round(fd, 3)
        pilot_points.append((fd, r["C"], pol, r))

    # d=0.5 pilot → fitd ≈ 2.381
    for r in load_jsonl(PILOT_D05):
        pol = "tr" if r["f"] < 1000 else "def"
        fd = r.get("duty", 0.5) * FIT
        r["fitd"] = round(fd, 3)
        pilot_points.append((fd, r["C"], pol, r))

    # Get pilot f=1 and f=inf only
    pilot_groups = defaultdict(list)
    for fd, C, pol, r in pilot_points:
        if r["f"] == 1.0 or r["f"] >= 1000:
            pilot_groups[(round(fd, 2), C, pol)].append(r)

    # 3. Compute aggregated stats for main sweep (C=10 only for clarity)
    fitd_vals = sorted(set(k[0] for k in groups))

    # For C=10
    tr_wall, def_wall = [], []
    tr_p95, def_p95 = [], []
    tr_hit, tr_gpu, def_gpu = [], [], []
    tr_wall_std, def_wall_std = [], []
    tr_p95_std, def_p95_std = [], []
    tr_fail_rate = []

    # Also C=20 for overlay
    tr_wall_c20, def_wall_c20 = [], []

    for fd in fitd_vals:
        for C, tw, dw, tw_s, dw_s, tp, dp, tp_s, dp_s, th, tg, dg, tf, twc, dwc in [
            (10, tr_wall, def_wall, tr_wall_std, def_wall_std,
             tr_p95, def_p95, tr_p95_std, def_p95_std,
             tr_hit, tr_gpu, def_gpu, tr_fail_rate, None, None),
            (20, None, None, None, None, None, None, None, None,
             None, None, None, None, tr_wall_c20, def_wall_c20),
        ]:
            tr_key = (fd, C, "tr")
            def_key = (fd, C, "def")
            if tr_key in groups and def_key in groups:
                tr_rs = groups[tr_key]
                def_rs = groups[def_key]
                if C == 10:
                    tw.append(mean([r["wall_s"] for r in tr_rs]))
                    dw.append(mean([r["wall_s"] for r in def_rs]))
                    tw_s.append(std([r["wall_s"] for r in tr_rs]))
                    dw_s.append(std([r["wall_s"] for r in def_rs]))
                    tp.append(mean([r.get("latency_p95_s") or 0 for r in tr_rs]))
                    dp.append(mean([r.get("latency_p95_s") or 0 for r in def_rs]))
                    tp_s.append(std([r.get("latency_p95_s") or 0 for r in tr_rs]))
                    dp_s.append(std([r.get("latency_p95_s") or 0 for r in def_rs]))
                    th.append(mean([r.get("TRUE_hit_rate") or 0 for r in tr_rs]))
                    tg.append(mean([r.get("gpu_util_mean") or 0 for r in tr_rs]))
                    dg.append(mean([r.get("gpu_util_mean") or 0 for r in def_rs]))
                    tf.append(sum(r.get("failed", 0) for r in tr_rs) /
                              sum(r.get("completed", 0) + r.get("failed", 0) for r in tr_rs))
                else:
                    twc.append(mean([r["wall_s"] for r in tr_rs]))
                    dwc.append(mean([r["wall_s"] for r in def_rs]))

    # Compute wall ratio
    wall_ratio_c10 = [d / t for t, d in zip(tr_wall, def_wall)]
    wall_ratio_c20 = [d / t for t, d in zip(tr_wall_c20, def_wall_c20)]

    # Pilot points for overlay (f=1 and f=inf, C=10)
    pilot_fds = []
    pilot_wall_ratio = []
    pilot_p95_tr = []
    pilot_p95_def = []
    for fd_round in sorted(set(round(fd, 2) for fd, _, _, _ in pilot_points)):
        tr_key = (fd_round, 10, "tr")
        def_key = (fd_round, 10, "def")
        if tr_key in pilot_groups and def_key in pilot_groups:
            tr_rs = pilot_groups[tr_key]
            def_rs = pilot_groups[def_key]
            tw = mean([r["wall_s"] for r in tr_rs])
            dw = mean([r["wall_s"] for r in def_rs])
            if tw > 0:
                pilot_fds.append(fd_round)
                pilot_wall_ratio.append(dw / tw)
                pilot_p95_tr.append(mean([r.get("latency_p95_s") or 0 for r in tr_rs]))
                pilot_p95_def.append(mean([r.get("latency_p95_s") or 0 for r in def_rs]))

    # 4. Plot
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("STEP 5: Transition Point — tr(f=1) vs default(f=∞)\n"
                 "5090/Qwen3-8B, C_total=95,936, C=10(2×fit), REPEAT=3",
                 fontsize=13, fontweight="bold")

    # (a) Wall time ratio
    ax = axes[0, 0]
    ax.errorbar(fitd_vals, wall_ratio_c10, fmt="o-", color="tab:blue",
                label="C=10 (2×fit)", markersize=7, capsize=3, linewidth=2)
    ax.plot(fitd_vals, wall_ratio_c20, "s--", color="tab:orange",
            label="C=20 (4×fit)", markersize=6, linewidth=1.5)
    # Pilot overlay
    ax.plot(pilot_fds, pilot_wall_ratio, "D", color="tab:green",
            markersize=9, label="Pilot (d=0.1/0.2/0.5)", zorder=5,
            markeredgecolor="black", markeredgewidth=0.8)
    # 4090 TraceLab point: fd=0.46, default won → ratio < 1
    ax.plot(0.46, 0.66, "*", color="tab:red", markersize=14,
            label="4090/TraceLab (P1)", zorder=5,
            markeredgecolor="black", markeredgewidth=0.8)
    ax.axhline(1.0, color="gray", linestyle=":", linewidth=1, alpha=0.7)
    ax.set_ylabel("Wall ratio (def / tr)\n>1 = tr wins", fontsize=11)
    ax.set_xlabel("fit × d", fontsize=11)
    ax.set_title("(a) Wall Time Ratio", fontsize=12)
    ax.legend(fontsize=9, loc="upper left")
    ax.grid(True, alpha=0.3)
    # Find transition point via linear interpolation
    for i in range(len(wall_ratio_c10) - 1):
        if wall_ratio_c10[i] < 1.0 and wall_ratio_c10[i + 1] > 1.0:
            # Linear interpolation
            x0, y0 = fitd_vals[i], wall_ratio_c10[i]
            x1, y1 = fitd_vals[i + 1], wall_ratio_c10[i + 1]
            x_cross = x0 + (1.0 - y0) * (x1 - x0) / (y1 - y0)
            ax.axvline(x_cross, color="tab:red", linestyle="--", alpha=0.5,
                       linewidth=1.5)
            ax.annotate(f"fit×d*≈{x_cross:.2f}", xy=(x_cross, 1.0),
                        xytext=(x_cross + 0.05, 0.9),
                        fontsize=10, color="tab:red", fontweight="bold",
                        arrowprops=dict(arrowstyle="->", color="tab:red"))
            break

    # (b) p95 latency
    ax = axes[0, 1]
    ax.errorbar(fitd_vals, tr_p95, yerr=tr_p95_std, fmt="o-", color="tab:blue",
                label="tr (f=1)", markersize=7, capsize=3, linewidth=2)
    ax.errorbar(fitd_vals, def_p95, yerr=def_p95_std, fmt="s-", color="tab:orange",
                label="default (f=∞)", markersize=6, capsize=3, linewidth=2)
    # Pilot overlay
    ax.plot(pilot_fds, pilot_p95_tr, "D", color="tab:blue",
            markersize=9, zorder=5, markeredgecolor="black",
            markeredgewidth=0.8, alpha=0.5)
    ax.plot(pilot_fds, pilot_p95_def, "D", color="tab:orange",
            markersize=9, zorder=5, markeredgecolor="black",
            markeredgewidth=0.8, alpha=0.5)
    ax.set_ylabel("p95 Latency (s)", fontsize=11)
    ax.set_xlabel("fit × d", fontsize=11)
    ax.set_title("(b) Tail Latency (p95)", fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # (c) TRUE hit rate + failure rate
    ax = axes[1, 0]
    ax2 = ax.twinx()
    l1, = ax.plot(fitd_vals, [h * 100 for h in tr_hit], "o-", color="tab:blue",
                  markersize=7, linewidth=2, label="TRUE cache hit (tr)")
    l2, = ax2.plot(fitd_vals, [f * 100 for f in tr_fail_rate], "x--",
                   color="tab:red", markersize=8, linewidth=1.5,
                   label="Program failure rate (tr)")
    ax.set_ylabel("TRUE Cache Hit Rate (%)", fontsize=11, color="tab:blue")
    ax2.set_ylabel("Failure Rate (%)", fontsize=11, color="tab:red")
    ax.set_xlabel("fit × d", fontsize=11)
    ax.set_title("(c) Cache Hit & Failure Rate (tr only)", fontsize=12)
    ax.set_ylim(70, 100)
    ax2.set_ylim(-1, 20)
    lines = [l1, l2]
    ax.legend(lines, [l.get_label() for l in lines], fontsize=9, loc="lower left")
    ax.grid(True, alpha=0.3)

    # (d) GPU utilization
    ax = axes[1, 1]
    ax.plot(fitd_vals, tr_gpu, "o-", color="tab:blue",
            markersize=7, linewidth=2, label="tr (f=1)")
    ax.plot(fitd_vals, def_gpu, "s-", color="tab:orange",
            markersize=6, linewidth=2, label="default (f=∞)")
    ax.set_ylabel("GPU Utilization (%)", fontsize=11)
    ax.set_xlabel("fit × d", fontsize=11)
    ax.set_title("(d) GPU Utilization", fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 100)

    plt.tight_layout()
    os.makedirs(os.path.dirname(OUT_FIG), exist_ok=True)
    fig.savefig(OUT_FIG, dpi=150, bbox_inches="tight")
    print(f"Figure saved to {OUT_FIG}")

    # 5. Print transition point summary
    print("\n=== TRANSITION POINT ANALYSIS ===")
    print(f"Wall time crossover (C=10): fit×d* ≈ {x_cross:.2f}")
    print(f"  fd=0.60: def wins by {(1-wall_ratio_c10[1])*100:.1f}%")
    print(f"  fd=0.65: tr wins by {(wall_ratio_c10[2]-1)*100:.1f}%")


if __name__ == "__main__":
    main()
