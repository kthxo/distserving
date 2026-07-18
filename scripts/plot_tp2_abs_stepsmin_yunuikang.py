#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Absolute throughput comparison in matched units (steps/min), paper vs ours.
1 step = one reasoning+acting turn (paper definition). Absolute values NOT directly
comparable (HW/model/concurrency differ) — shown for magnitude/units transparency.

OURS (Pro6000 TP2, Qwen3-32B; computed = throughput_programs_per_s x turns_per_program x 60,
turns/program identical for tr & default under deterministic replay; 3-run mean):
  SWE (=mini-SWEAgent):  C16 def134.0/tr133.1 · C32 def145.5/tr143.4 · C64 def27.2/tr56.3
  TraceLab (our own):    C16 def43.2/tr43.2 · C32 def12.6/tr23.7 · C64 def11.5/tr21.1
PAPER (steps/min, Table 7, 2xH100 GLM-4.5-fp8 mini-SWEAgent @144 concurrent):
  vLLM 375 -> +local 602 -> +global (full ThunderAgent) 672   (Fig 4 peaks: SWE~400, OpenH~200,
  Sci~60, HLE~8 step/min axes; speedup 1.24-3.58x vs vLLM)
Output: figures/tp2_abs_stepsmin.png  (English labels; no Korean mpl font)
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({"font.size": 10.5, "axes.titlesize": 11.5, "axes.titleweight": "bold"})
DEF = "#8c9099"   # default / vLLM (baseline gray)
TR  = "#2E7D46"   # tr / ThunderAgent (green)
PAP = "#27458c"   # paper ThunderAgent (blue)

fig, ax = plt.subplots(1, 3, figsize=(11.6, 3.4), gridspec_kw={"width_ratios": [1.15, 1.15, 1.0]})
Cs = ["C=16", "C=32", "C=64"]; x = np.arange(3); w = 0.38

def grouped(a, defv, trv, title, ymax, note):
    a.bar(x - w/2, defv, w, color=DEF, label="default (=vLLM)")
    a.bar(x + w/2, trv,  w, color=TR,  label="tr (ThunderAgent)")
    a.set_xticks(x); a.set_xticklabels(Cs)
    a.set_ylabel("throughput (steps/min)")
    a.set_title(title); a.set_ylim(0, ymax)
    for xi, v in zip(x - w/2, defv):
        a.text(xi, v + ymax*0.015, f"{v:.0f}", ha="center", va="bottom", fontsize=8.5, color="#555", fontweight="bold")
    for xi, v in zip(x + w/2, trv):
        a.text(xi, v + ymax*0.015, f"{v:.0f}", ha="center", va="bottom", fontsize=8.5, color=TR, fontweight="bold")
    a.text(0.5, -0.26, note, transform=a.transAxes, ha="center", fontsize=8, style="italic", color="#444")

# Panel 1: SWE (ours)
grouped(ax[0], [134, 146, 27], [133, 143, 56],
        "Ours: SWE (mini-SWEAgent)\nQwen3-32B / Pro6000 TP2", 170,
        "C=64: tr 56 vs def 27  (+107%)")
ax[0].legend(fontsize=8.5, loc="upper right", framealpha=0.9)

# Panel 2: TraceLab (ours)
grouped(ax[1], [43, 13, 12], [43, 24, 21],
        "Ours: TraceLab (our own workload)\nQwen3-32B / Pro6000 TP2", 55,
        "C=32: tr 24 vs def 13  (+88%)")

# Panel 3: paper mini-SWEAgent (Table 7)
comp = ["vLLM", "+local", "TA\n(full)"]
vals = [375, 602, 672]
cols = [DEF, "#5b7fc0", PAP]
b = ax[2].bar(range(3), vals, color=cols, width=0.62)
ax[2].set_xticks(range(3)); ax[2].set_xticklabels(comp, fontsize=9)
ax[2].set_ylabel("throughput (steps/min)")
ax[2].set_title("Paper: mini-SWEAgent (Table 7)\nGLM-4.5-fp8 / 2xH100, C=144", fontsize=11)
ax[2].set_ylim(0, 760)
for r, v, m in zip(b, vals, ["", "1.61x", "1.79x"]):
    ax[2].text(r.get_x()+r.get_width()/2, v+10, f"{v}", ha="center", va="bottom", fontsize=9, fontweight="bold")
    if m: ax[2].text(r.get_x()+r.get_width()/2, v/2, m, ha="center", va="center", fontsize=9, color="white", fontweight="bold")
ax[2].text(0.5, -0.26, "vs vLLM (paper §G.4)", transform=ax[2].transAxes, ha="center", fontsize=8, style="italic", color="#444")

fig.suptitle("Absolute throughput in matched units (steps/min)  —  paper vs ours  "
             "(HW/model/concurrency differ; magnitude only)",
             fontsize=11.5, fontweight="bold", y=1.04)
fig.tight_layout()
fig.subplots_adjust(bottom=0.24, top=0.80)
out = "/home/yunuikang/yunuikang_work/distserving/figures/tp2_abs_stepsmin.png"
fig.savefig(out, dpi=150, bbox_inches="tight")
print("SAVED:", out)
