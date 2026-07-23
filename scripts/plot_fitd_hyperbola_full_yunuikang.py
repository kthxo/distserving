# -*- coding: utf-8 -*-
"""STEP2 fit x d hyperbola, extended with the two newly-measured workloads:
   Science (P2, Pro6000x1, d=0.989 fit=16.2) and HLE (P3, Pro6000x1 8B, d=0.82 fit=34.5).
Faithful to figures/step2_fitd_hyperbola_yunuikang.png (2D: x=d linear, y=fit log,
boundary fit x d = 1). English labels (matches original). Numbers verbatim from logs.
HLE is drawn as the honest exception: in the tr-dominant zone by fit x d, but tr loses
on throughput because its always-on tail collapses the true GPU utilization.
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

RED_Z = "#FBE4E1"; BLUE_Z = "#E5EDFB"
RED = "#E8776B"; BLUE = "#6E93D6"; GRAYST = "#9AA0A6"
NEWG = "#2E8B4F"; AMBER = "#C77B12"; RED_X = "#D8382B"; INK = "#1A1A2E"

fig, ax = plt.subplots(figsize=(12.2, 8.0), dpi=120)
XMIN, XMAX = 0.05, 1.08
YMIN, YMAX = 0.8, 520

# hyperbola fit = 1/d  (fit x d = 1)
xs = np.linspace(XMIN, XMAX, 400)
ys = 1.0 / xs
ax.set_yscale("log"); ax.set_xlim(XMIN, XMAX); ax.set_ylim(YMIN, YMAX)

# zone fills: below hyperbola = tradeoff(red), above = tr-dominant(blue)
ax.fill_between(xs, YMIN, np.clip(ys, YMIN, YMAX), color=RED_Z, zorder=0)
ax.fill_between(xs, np.clip(ys, YMIN, YMAX), YMAX, color=BLUE_Z, zorder=0)
ax.plot(xs, ys, color="k", lw=2.6, zorder=4)

# ---- measured cells (original 6) ----
# (d, fit, marker, facecolor, label, dx, dy, ha)
cells = [
    (0.196, 2.35, "*", RED,  "RTX 4090/TraceLab",   0.02,  -0.16, "left"),
    (0.196, 4.77, "D", RED,  "RTX 5090/TraceLab",   0.02,   0.0,  "left"),
    (0.289, 24.5, "*", BLUE, "Pro6000 x2/TraceLab", 0.02,   0.0,  "left"),
    (0.996, 5.56, "*", BLUE, "RTX 4090/SWE",        -0.02,  0.0,  "right"),
    (0.996, 11.0, "D", BLUE, "RTX 5090/SWE",        -0.02,  0.0,  "right"),
    (0.996, 57.9, "*", BLUE, "Pro6000 x2/SWE",      -0.02,  0.0,  "right"),
]
for d, fit, mk, fc, lab, dx, dy, ha in cells:
    sz = 540 if mk == "*" else 260
    ax.scatter([d], [fit], marker=mk, s=sz, c=fc, edgecolors="k",
               linewidths=1.3, zorder=6)
    ax.annotate(lab, (d + dx, fit * (1 + dy)), ha=ha, va="center",
                fontsize=10, color=INK)

# ---- NEW: Science (P2) — prediction holds, tr wins ----
ax.scatter([0.989], [16.2], marker="p", s=520, c=NEWG, edgecolors="k",
           linewidths=1.6, zorder=7)
ax.annotate("Science/Pro6000x1\n(P2: tr +227%)", (0.975, 16.2 * 1.34),
            ha="right", va="bottom", fontsize=10, fontweight="bold", color=NEWG)

# ---- NEW: HLE (P3) — tr-dominant by fit x d BUT throughput exception ----
ax.scatter([0.82], [34.5], marker="D", s=430, facecolors="none",
           edgecolors=AMBER, linewidths=3.0, zorder=7)
ax.scatter([0.82], [34.5], marker="x", s=150, c=RED_X, linewidths=2.6, zorder=8)
ax.annotate("HLE/Pro6000x1 8B\n(P3: tr hit +28% / thr LOSS)", (0.80, 34.5 * 1.30),
            ha="right", va="bottom", fontsize=10, fontweight="bold", color=AMBER)

# zone titles
ax.text(0.62, 150, "tr-DOMINANT zone\n(fit x d >= 1)", color="#3A6BC0",
        fontsize=13, fontweight="bold", ha="center")
ax.text(0.28, 1.15, "TRADEOFF zone\n(fit x d < 1: idle<->recompute)", color="#C0392B",
        fontsize=12, fontweight="bold", ha="center")

ax.set_xlabel("d  (duty = reasoning / (reasoning + tool))", fontsize=13)
ax.set_ylabel("fit = C_total / ctx   (max thrash-free residents, log)", fontsize=13)
ax.set_title("STEP 2 - fit x d boundary: tradeoff zone across measured cells\n"
             "(+ P2 Science, P3 HLE now measured; HLE = throughput exception)",
             fontsize=13.5)
ax.grid(True, which="both", ls=":", lw=0.5, color="#CCCCCC", zorder=1)

leg = [
    Line2D([0],[0], marker="*", color="w", markerfacecolor=GRAYST, markeredgecolor="k",
           markersize=17, label="measured cells (win/loss verified)"),
    Line2D([0],[0], marker="D", color="w", markerfacecolor=GRAYST, markeredgecolor="k",
           markersize=11, label="5090 measured"),
    Line2D([0],[0], marker="p", color="w", markerfacecolor=NEWG, markeredgecolor="k",
           markersize=15, label="P2 Science (new, tr wins)"),
    Line2D([0],[0], marker="D", color="w", markerfacecolor="none", markeredgecolor=AMBER,
           markeredgewidth=2.5, markersize=13, label="P3 HLE (tr-zone but thr LOSS: always-on tail)"),
    Line2D([0],[0], color="k", lw=2.4, label="fit x d = 1 boundary"),
]
ax.legend(handles=leg, loc="upper right", fontsize=9.5, framealpha=0.95)

plt.tight_layout()
out = "/home/yunuikang/yunuikang_work/distserving/figures/fitd_hyperbola_full_yunuikang.png"
plt.savefig(out, dpi=120, bbox_inches="tight", facecolor="white")
print("saved:", out)
