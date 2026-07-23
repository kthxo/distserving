# -*- coding: utf-8 -*-
"""fit x d regime map with the two previously-pending workloads now measured:
   Science (P2, fit x d = 16.0, tr +227%) and HLE (P3, fit x d ~= 28, tr-zone
   but throughput 패 - the honest exception). Style follows figures/그림1.png.
   Numbers are verbatim from the P2/P3 logs. NanumGothic lacks x/-/*/> glyphs -> ASCII-safe.
"""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.patches import Patch

for cand in ["/home/yunuikang/yunuikang_work/distserving/scripts/NanumGothic_yunuikang.ttf",
             "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"]:
    if os.path.exists(cand):
        fm.fontManager.addfont(cand)
        plt.rcParams["font.family"] = fm.FontProperties(fname=cand).get_name()
        break
plt.rcParams["axes.unicode_minus"] = False   # use ASCII hyphen, not U+2212

ORANGE_Z = "#FCEFE1"; BLUE_Z = "#EAF2FB"
RED = "#D8382B"; GREEN = "#2E8B4F"; ORANGE = "#F0A020"; BLUE = "#3AA0E8"
RED_DASH = "#E8433A"; AMBER = "#C77B12"; INK = "#1A1A2E"; GRAY = "#6B6B7B"
DEF_ORANGE = "#E8933A"; TR_BLUE = "#5AA5DE"

fig, ax = plt.subplots(figsize=(15.0, 7.2), dpi=120)
FD = 0.62
XMIN, XMAX = 0.09, 150

ax.axvspan(XMIN, FD, color=ORANGE_Z, zorder=0)
ax.axvspan(FD, XMAX, color=BLUE_Z, zorder=0)
ax.axvline(FD, color=RED_DASH, ls="--", lw=2.6, zorder=5)
ax.set_xscale("log"); ax.set_xlim(XMIN, XMAX); ax.set_ylim(0.15, 4.15)

Y_REAL, Y_SYN, Y_NEW = 3.30, 2.20, 1.05

# ---- helper: marker + header(above, x-nudged) + value(below, y-staggered) ----
def pt(x, y, mk, col, header, hx, val, vcol, vy, hollow=False, ring=None):
    if hollow:
        ax.scatter([x], [y], marker=mk, s=480, facecolors="none",
                   edgecolors=col, linewidths=3.0, zorder=7)
        if ring:
            ax.scatter([x], [y], marker="X", s=140, c=ring, linewidths=0, zorder=8)
    else:
        ax.scatter([x], [y], marker=mk, s=440, c=col, edgecolors="k",
                   linewidths=1.3, zorder=6)
    ax.annotate(header, (hx, y + 0.44), ha="center", va="bottom",
                fontsize=11, fontweight="bold", color=INK)
    ax.annotate(val, (hx, y + vy), ha="center", va="top",
                fontsize=10.5, fontweight="bold", color=vcol)

# ---------------- 실제 워크로드 (measured 4 cells) ----------------
pt(0.46, Y_REAL, "v", RED,   "4090/TraceLab", 0.46, "def 승 -34%", RED, -0.30)
pt(5.54, Y_REAL, "^", GREEN, "4090/SWE",      4.1,  "tr 승 +78%",  GREEN, -0.30)
pt(7.07, Y_REAL, "s", GREEN, "Pro6000/TraceLab", 10.5, "tr 승 +87%", GREEN, -0.58)
pt(57.6, Y_REAL, "s", GREEN, "Pro6000/SWE",   57.6, "tr 승 +113%", GREEN, -0.30)

# ---------------- 합성 스윕 (3 diamonds near boundary) ----------------
ax.annotate("합성 duty 스윕 (E2E 고정)", (0.62, Y_SYN + 0.52), ha="center",
            va="bottom", fontsize=11, fontweight="bold", color=INK)
for x, col in [(0.50, ORANGE), (0.65, GREEN), (0.90, BLUE)]:
    ax.scatter([x], [Y_SYN], marker="D", s=340, c=col, edgecolors="k",
               linewidths=1.1, zorder=6)
ax.annotate("fd=0.50\ndef +12%", (0.44, Y_SYN - 0.28), ha="center", va="top",
            fontsize=9.5, fontweight="bold", color=DEF_ORANGE)
ax.annotate("fd=0.65*\ntr +2%", (0.65, Y_SYN - 0.66), ha="center", va="top",
            fontsize=9.5, fontweight="bold", color=GREEN)
ax.annotate("fd=0.90\ntr +24%", (1.02, Y_SYN - 0.28), ha="center", va="top",
            fontsize=9.5, fontweight="bold", color=TR_BLUE)

# ---------------- 신규 측정 (P2 Science, P3 HLE) - now real ----------------
# Science: fit x d = 16.0 -> tr wins big (prediction holds)
pt(16.0, Y_NEW, "s", GREEN, "Science (P2)", 13.0, "tr 승 +227%", GREEN, -0.30)
ax.annotate("Pro6000x1 - 희소 tail - U 포화", (13.0, Y_NEW - 0.60), ha="center",
            va="top", fontsize=8.8, color=GRAY)
# HLE: fit x d ~= 28 -> tr-zone BUT throughput 패 (exception)
ax.scatter([28.0], [Y_NEW], marker="D", s=500, facecolors="none",
           edgecolors=AMBER, linewidths=3.0, zorder=7)
ax.scatter([28.0], [Y_NEW], marker="x", s=150, c=RED, linewidths=2.6, zorder=8)
ax.annotate("HLE (P3) - 예외", (40.0, Y_NEW + 0.44), ha="center", va="bottom",
            fontsize=11, fontweight="bold", color=AMBER)
ax.annotate("tr hit +28% / thr 패 -2~8%", (40.0, Y_NEW - 0.30), ha="center",
            va="top", fontsize=10, fontweight="bold", color=AMBER)
ax.annotate("Pro6000x1(8B) - 상시 tail - 진짜 U 0.64~0.71", (40.0, Y_NEW - 0.60),
            ha="center", va="top", fontsize=8.8, color=RED)

# ---------------- zone titles / boundary label ----------------
ax.text(0.155, 3.98, "default 영역", fontsize=17, fontweight="bold", color=DEF_ORANGE)
ax.text(22, 3.98, "tr 영역", fontsize=17, fontweight="bold", color=TR_BLUE)
ax.annotate("fd*=0.62", (FD, 4.06), ha="center", va="center", fontsize=14,
            fontweight="bold", color=RED_DASH,
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=RED_DASH, lw=1.8))

for y, txt in [(Y_REAL, "실제\n워크로드"), (Y_SYN, "합성\n스윕"), (Y_NEW, "신규 측정\n(P2-P3)")]:
    ax.text(XMIN * 1.02, y, txt, ha="left", va="center", fontsize=11,
            fontweight="bold", color=GRAY)

ticks = [0.1, 0.5, 1.0, 5, 10, 50, 100]
ax.set_xticks(ticks); ax.set_xticklabels([str(t) for t in ticks],
                                         fontsize=12.5, fontweight="bold")
ax.set_xlabel("fit x d   (log scale)", fontsize=16, fontweight="bold", labelpad=8)
ax.tick_params(axis="y", left=False, labelleft=False)
for sp in ["top", "right", "left"]:
    ax.spines[sp].set_visible(False)
ax.spines["bottom"].set_linewidth(2.0)
for y in (Y_REAL, Y_SYN, Y_NEW):
    ax.plot([XMIN, XMAX], [y - 0.02, y - 0.02], ls=":", lw=0.6, color="#CCCCCC", zorder=1)

# summary box
ax.text(1.15, 0.42,
        "fd < 0.62: default 승   |   fd > 0.62: tr 승   -   실제 5셀 + 합성 84점 정합\n"
        "단 HLE는 tr 영역이나 상시 tail로 진짜 U 붕괴 -> throughput 예외 (예측=hit 방어, 실측 throughput 패)",
        ha="center", va="center", fontsize=11, fontweight="bold", color=GREEN,
        bbox=dict(boxstyle="round,pad=0.5", fc="#F0F8F2", ec=GREEN, lw=1.8))

leg = [Patch(fc=GREEN, ec="k", label="tr 승 (예측 적중)"),
       Patch(fc=RED, ec="k", label="default 승"),
       Patch(fc="none", ec=AMBER, label="tr 영역이나 throughput 패 (HLE 예외)")]
ax.legend(handles=leg, loc="upper center", bbox_to_anchor=(0.5, -0.16),
          ncol=3, fontsize=10.5, frameon=False)

plt.tight_layout()
out = "/home/yunuikang/yunuikang_work/distserving/figures/regime_map_full_yunuikang.png"
plt.savefig(out, dpi=120, bbox_inches="tight", facecolor="white")
print("saved:", out)
