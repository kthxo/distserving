#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Workload characterization figure (P1 measured: TraceLab vs SWE).
All numbers taken verbatim from logs/2026-07-16_TP2_RESULTS_yunuikang.md:
  TraceLab (c=1 duty profile, 25 prog / 87 turns):  input mean 18,684 · output mean 54.8 ·
    tool mean 6.87s (median 0.54, max 30 cap) · d=0.289 · turns/prog≈3.5
  SWE (recording, 58 sessions / 1088 turns):        input median 7,897 · output median 854 ·
    tool median 0.15s · turns/session median 16 (max 40) · d=0.996 · clip 13.8%
  fit = KV pool(456,944) / input  → TraceLab≈25 (collapse C=32), SWE≈58 (collapse C=64)
English labels only (no Korean font in mpl); consistent with existing tp2_*.png.
Output: figures/tp2_workload_char.png
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({"font.size": 11, "axes.titlesize": 12, "axes.titleweight": "bold"})

TL = "#2f6db0"   # TraceLab (prefill-heavy)
SW = "#e08a1e"   # SWE (decode-heavy)

fig, ax = plt.subplots(1, 3, figsize=(11.6, 3.5))

# --- Panel 1: input vs output tokens per turn (log) ---
labels = ["input", "output"]
x = np.arange(2); w = 0.36
tl_vals = [18684, 54.8]
sw_vals = [7897, 854]
ax[0].bar(x - w/2, tl_vals, w, color=TL, label="TraceLab")
ax[0].bar(x + w/2, sw_vals, w, color=SW, label="SWE")
ax[0].set_yscale("log")
ax[0].set_xticks(x); ax[0].set_xticklabels(labels)
ax[0].set_ylabel("tokens / turn (log)")
ax[0].set_title("Token profile: prefill- vs decode-heavy")
for xi, v in zip(x - w/2, tl_vals):
    ax[0].text(xi, v*1.15, f"{v:,.0f}" if v >= 100 else f"{v:.0f}", ha="center", va="bottom", fontsize=8.5, color=TL, fontweight="bold")
for xi, v in zip(x + w/2, sw_vals):
    ax[0].text(xi, v*1.15, f"{v:,.0f}", ha="center", va="bottom", fontsize=8.5, color=SW, fontweight="bold")
ax[0].set_ylim(10, 60000)
ax[0].legend(fontsize=9, loc="upper right")
# in/out ratio annotation
ax[0].text(0.5, 0.03, "in/out ratio:  TraceLab ~341x   vs   SWE ~9x",
           transform=ax[0].transAxes, ha="center", fontsize=8.5, style="italic", color="#444")

# --- Panel 2: duty cycle d ---
names = ["TraceLab", "SWE"]
d_vals = [0.289, 0.996]
cols = [TL, SW]
b = ax[1].bar(names, d_vals, color=cols, width=0.55)
ax[1].set_ylim(0, 1.12)
ax[1].set_ylabel("duty  d = reasoning / (reasoning+tool)")
ax[1].set_title("Duty cycle (compute fraction)")
ax[1].axhline(1.0, ls="--", lw=1, color="#999")
for rect, v, nd in zip(b, d_vals, ["NEED 1/d=3.45", "NEED 1/d=1.0"]):
    ax[1].text(rect.get_x()+rect.get_width()/2, v+0.02, f"{v:.3f}", ha="center", va="bottom", fontweight="bold")
    ax[1].text(rect.get_x()+rect.get_width()/2, 0.05, nd, ha="center", va="bottom", fontsize=8, color="white", fontweight="bold")
ax[1].text(0.5, -0.22, "tool: TL mean 6.87s (med 0.54) vs SWE med 0.15s",
           transform=ax[1].transAxes, ha="center", fontsize=8.5, style="italic", color="#444")

# --- Panel 3: fit = KV pool / input  ->  collapse C ---
fit_vals = [24.5, 57.9]
b2 = ax[2].bar(names, fit_vals, color=cols, width=0.55)
ax[2].set_ylabel("fit = KV pool (456,944) / input")
ax[2].set_title("Programs that fit  →  default-collapse C")
ax[2].set_ylim(0, 70)
for rect, v, cc in zip(b2, fit_vals, ["default\ncollapse\n@ C=32", "default\ncollapse\n@ C=64"]):
    ax[2].text(rect.get_x()+rect.get_width()/2, v+1.2, f"~{v:.0f}", ha="center", va="bottom", fontweight="bold")
    ax[2].text(rect.get_x()+rect.get_width()/2, v-2.0, cc, ha="center", va="top", fontsize=9.5, color="white", fontweight="bold", linespacing=1.25)
ax[2].text(0.5, -0.22, "same HW (KV pool fixed); only program size differs",
           transform=ax[2].transAxes, ha="center", fontsize=8.5, style="italic", color="#444")

fig.suptitle("Workload characterization (P1 measured):  TraceLab (prefill-heavy)  vs  SWE (decode-heavy)",
             fontsize=12.5, fontweight="bold", y=1.02)
fig.tight_layout()
fig.subplots_adjust(bottom=0.20, top=0.86)
out = "/home/yunuikang/yunuikang_work/distserving/figures/tp2_workload_char.png"
fig.savefig(out, dpi=150, bbox_inches="tight")
print("SAVED:", out)
