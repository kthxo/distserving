#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Directional-agreement figure: ThunderAgent throughput vs vLLM baseline — paper vs ours.
Paper numbers (verbatim from ThunderAgent.pdf Fig 4, speedup vs vLLM):
  SWEAgent-GLM4.6 2.65 · OpenHands-GLM4.6 3.58 · HLE-Qwen3-8B 1.48 · SWEAgent-235B 3.02 ·
  OpenHands-235B 2.43 · ScienceAgent-GLM4.6 1.24   (overall 1.48-3.58x vs vLLM; §5.2)
Ours (Pro6000 TP2, Qwen3-32B; tr vs default=vLLM, at fit-exceeding C, from TP2_RESULTS):
  SWE C=64: 0.051/0.024 = 2.13x (+113%) · TraceLab C=32: 0.073/0.039 = 1.87x (+87%)
Message = DIRECTION agrees (all >1x); absolute magnitudes/HW NOT comparable (see slide caveat).
English labels only (no Korean font in mpl).
Output: figures/tp2_paper_trend.png
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({"font.size": 10.5, "axes.titlesize": 12, "axes.titleweight": "bold"})
PRED = "#2f6db0"   # predictable / decode-heavy
STOC = "#e08a1e"   # stochastic
OURS = "#2E7D46"   # ours

fig, ax = plt.subplots(1, 2, figsize=(7.4, 3.5), gridspec_kw={"width_ratios": [3, 1.35]})

# --- Panel A: paper Fig4 speedup vs vLLM ---
labels = ["SWE\nGLM4.6", "OpenH\nGLM4.6", "SWE\n235B", "OpenH\n235B", "HLE\n8B", "Sci\nGLM4.6"]
vals   = [2.65, 3.58, 3.02, 2.43, 1.48, 1.24]
cols   = [PRED, PRED, PRED, PRED, STOC, STOC]
b = ax[0].bar(range(6), vals, color=cols, width=0.72)
ax[0].axhline(1.0, ls="--", lw=1.2, color="#888")
ax[0].set_xticks(range(6)); ax[0].set_xticklabels(labels, fontsize=8.5)
ax[0].set_ylabel("throughput speedup vs vLLM")
ax[0].set_title("Paper (Fig 4) — H100 / 5090", fontsize=11)
ax[0].set_ylim(0, 4.1)
for r, v in zip(b, vals):
    ax[0].text(r.get_x()+r.get_width()/2, v+0.06, f"{v:.2f}x", ha="center", va="bottom", fontsize=8.5, fontweight="bold")
ax[0].text(0.02, 0.94, "predictable (decode-heavy)", transform=ax[0].transAxes, fontsize=8, color=PRED, fontweight="bold")
ax[0].text(0.02, 0.87, "stochastic", transform=ax[0].transAxes, fontsize=8, color=STOC, fontweight="bold")

# --- Panel B: ours (tr / default) at fit-exceeding C ---
olabels = ["SWE\nC=64", "TraceLab\nC=32"]
ovals   = [2.13, 1.87]
b2 = ax[1].bar(range(2), ovals, color=OURS, width=0.6)
ax[1].axhline(1.0, ls="--", lw=1.2, color="#888")
ax[1].set_xticks(range(2)); ax[1].set_xticklabels(olabels, fontsize=8.5)
ax[1].set_ylabel("tr / default (=vLLM)")
ax[1].set_title("Ours — Pro6000 TP2 / 32B", fontsize=11)
ax[1].set_ylim(0, 4.1)
for r, v, pct in zip(b2, ovals, ["+113%", "+87%"]):
    ax[1].text(r.get_x()+r.get_width()/2, v+0.06, f"{v:.2f}x", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax[1].text(r.get_x()+r.get_width()/2, v/2, pct, ha="center", va="center", fontsize=9, color="white", fontweight="bold", rotation=90)

fig.suptitle("Direction agreement: ThunderAgent > vLLM baseline throughput  (magnitudes/HW not comparable)",
             fontsize=11.5, fontweight="bold", y=1.03)
fig.tight_layout()
out = "/home/yunuikang/yunuikang_work/distserving/figures/tp2_paper_trend.png"
fig.savefig(out, dpi=150, bbox_inches="tight")
print("SAVED:", out)
