#!/usr/bin/env python3
"""tr pause의 heavy tail + 데드락 재현 타임라인.

  figures/vllm_pause_heavy_tail.png     expC tr pause 분포: p50=0 인데 mean=18.5 (꼬리가 만든 평균)
  figures/vllm_deadlock_timeline.png    2026-07-17 재현된 tr 데드락 (GPU 0%, 261s 무진행)
"""
import csv
import glob
import os

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

EXPC = "/home/yunuikang/yunuikang_work/scratch/expC"
VP = "/home/yunuikang/yunuikang_work/scratch/vprof"
FIG = "/home/yunuikang/yunuikang_work/distserving/figures"


def fig_tail():
    rows = list(csv.DictReader(open(f"{EXPC}/prof_tr_ts1.0/step_profiles.csv")))
    p = np.array([float(r["pause_s"]) for r in rows])
    d = list(csv.DictReader(open(f"{EXPC}/prof_default_ts1.0/step_profiles.csv")))
    pd_ = np.array([float(r["pause_s"]) for r in d])

    fig, ax = plt.subplots(1, 2, figsize=(12.6, 4.7))
    # left: CCDF
    xs = np.sort(p)
    ccdf = 1.0 - np.arange(len(xs)) / len(xs)
    ax[0].step(xs, ccdf, color="#8e44ad", lw=1.8, label=f"tr pause_s (n={len(p)})")
    for i, (q, c) in enumerate([(50, "#27ae60"), (75, "#f39c12"), (95, "#e67e22"), (99, "#c0392b")]):
        v = np.percentile(p, q)
        ax[0].axvline(max(v, 1e-3), color=c, ls="--", lw=1.1, alpha=.85)
        ax[0].annotate(f"p{q} = {v:.1f}s", xy=(max(v, 1e-3), 10 ** (-0.35 - i * 0.55)),
                       xytext=(6, 0), textcoords="offset points",
                       color=c, fontsize=9.5, weight="bold", va="center")
    ax[0].axvline(p.mean(), color="k", ls="-", lw=2.2)
    ax[0].annotate(f"mean = {p.mean():.1f}s\n(made by the tail)", xy=(p.mean(), 0.62),
                   xytext=(-96, 0), textcoords="offset points", fontsize=9.5, weight="bold",
                   arrowprops=dict(arrowstyle="->", lw=1.1))
    ax[0].set_xscale("symlog", linthresh=0.01); ax[0].set_yscale("log")
    ax[0].set_xlabel("pause_s per step (log)"); ax[0].set_ylabel("P(pause > x)  (log)")
    ax[0].set_title("expC tr: pause is NOT a smooth per-step tax\n"
                    "median = 0.00s, but mean = 18.5s — a few catastrophic stalls dominate", fontsize=10.5)
    ax[0].legend(fontsize=9); ax[0].grid(alpha=.25, which="both")

    # right: bar of fraction above thresholds
    thr = [1, 10, 30, 60, 120, 300, 600]
    frac = [100 * (p > t).mean() for t in thr]
    ax[1].bar([str(t) for t in thr], frac, color="#8e44ad")
    for i, f in enumerate(frac):
        ax[1].text(i, f + .25, f"{f:.1f}%", ha="center", fontsize=9.5, weight="bold")
    ax[1].set_xlabel("pause_s threshold (s)"); ax[1].set_ylabel("% of tr steps above threshold")
    ax[1].set_title(f"only {100*(p>1).mean():.0f}% of steps pause >1s,  but {100*(p>300).mean():.1f}% stall >300s\n"
                    f"max = {p.max():.0f}s   (default: mean {pd_.mean():.2f}s, max {pd_.max():.2f}s)", fontsize=10.5)
    ax[1].grid(alpha=.25, axis="y")
    fig.suptitle("tr's 18.5 s/step 'pause tax' is a HEAVY TAIL, not a steady cost", fontsize=12.5, weight="bold")
    fig.tight_layout()
    o = f"{FIG}/vllm_pause_heavy_tail.png"
    fig.savefig(o, dpi=150); plt.close(fig); print("wrote", o)


def fig_deadlock():
    cands = [(f"{VP}/DEADLOCK_sample_tr_stream.csv", "tr + --stream"),
             (f"{VP}/sample_tr_nostream_c16.csv", "tr, no --stream")]
    cands = [(f, l) for f, l in cands if os.path.exists(f)]
    if not cands:
        print("no deadlock samples"); return
    fig, axes = plt.subplots(len(cands), 1, figsize=(12.4, 3.1 * len(cands)), squeeze=False)
    for ax, (f, lab) in zip(axes[:, 0], cands):
        rows = list(csv.DictReader(open(f)))
        g = lambda k: np.array([float(r[k] or 0) for r in rows])
        t = g("t")
        nrr = g("b0_nrr") + g("b1_nrr")
        reas = g("b0_reasoning") + g("b1_reasoning")
        act = g("b0_acting") + g("b1_acting")
        pau = g("paused_total")
        util = (g("gpu2_util") + g("gpu3_util")) / 2
        ax.fill_between(t, 0, nrr, step="mid", color="#c0392b", alpha=.9, label="vLLM nrr (GPU batch)")
        ax.plot(t, reas, color="#2e86ab", lw=1.1, label="proxy REASONING")
        ax.plot(t, act, color="#27ae60", lw=1.1, label="proxy ACTING")
        ax.plot(t, pau, color="#8e44ad", lw=1.6, label="paused_total (global queue)")
        ax.plot(t, util / 10, color="#f39c12", lw=1.0, alpha=.8, label="nvidia-smi util /10")
        idx = np.where(reas > 0)[0]
        if len(idx):
            stall = t[idx[-1]]
            ax.axvspan(stall, t[-1], color="red", alpha=.10)
            ax.annotate(f"DEADLOCK: {t[-1]-stall:.0f}s with reasoning=0, nrr=0, GPU 0%",
                        xy=((stall + t[-1]) / 2, 14), ha="center", fontsize=10.5, weight="bold", color="#c0392b")
        ax.set_title(f"{lab}  (C=16, NPROG=32, 2x4090)", fontsize=11)
        ax.set_ylabel("count"); ax.set_ylim(0, 20); ax.grid(alpha=.25)
        ax.legend(fontsize=7.5, ncol=5, loc="upper left")
    axes[-1, 0].set_xlabel("time (s)")
    fig.suptitle("Reproduced 2026-07-17: tr scheduler deadlocks — ACTING tokens (active=40,671 of C_total=43,888) "
                 "block resume of 18 paused programs", fontsize=11.5, weight="bold")
    fig.tight_layout()
    o = f"{FIG}/vllm_deadlock_timeline.png"
    fig.savefig(o, dpi=150); plt.close(fig); print("wrote", o)


if __name__ == "__main__":
    fig_tail(); fig_deadlock()
