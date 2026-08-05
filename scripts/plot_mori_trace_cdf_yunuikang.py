#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""툴콜 지연 백분위 프로파일 — 논문(MORI Fig.3) vs 내 trace 4종.

수치 출처(지어낸 값 없음):
  논문  : MORI 논문 Fig.3/§3.3 (n=16,886). plans/2026-07-30_PLAN_mori-on-thunderagent_yunuikang.md §C-1
          대조표에 원문 대조된 값만 사용 (P50 1,096ms / P90 2,034ms / P99 19,980ms).
  내 trace: 같은 계획서 §C-1 실측표 (tracelab_trace_full / earlycutoff_128k / earlycutoff_40k / swebench).

palette: dataviz 스킬 validate_palette.js 6검사 전항 PASS
  ("#4A7FD0,#1E9E74,#B8860B,#C0392B,#8557C7", light, surface #fcfcfb)
tritan 분리도가 낮으므로 secondary encoding(계열별 마커 + 직접 라벨)을 함께 준다.
Output: figures/mori_trace_pctile_yunuikang.png
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = os.path.dirname(os.path.abspath(__file__))
FIGDIR = os.path.join(os.path.dirname(HERE), "figures")
FONT_TTF = os.path.join(HERE, "NanumGothic_yunuikang.ttf")
OUT = os.path.join(FIGDIR, "mori_trace_pctile_yunuikang.png")

if os.path.exists(FONT_TTF):
    font_manager.fontManager.addfont(FONT_TTF)
    plt.rcParams["font.family"] = font_manager.FontProperties(fname=FONT_TTF).get_name()
plt.rcParams["axes.unicode_minus"] = False

INK   = "#1f2430"
MUTED = "#6B7280"
GRID  = "#DFE3EA"
SURF  = "#FCFCFB"

# (label, color, marker, [P50, P90, P99] in seconds, source-tag, P99 직접라벨 여부)
# 직접 라벨은 선택적으로만 (전 계열에 붙이면 P99에서 180/150/129가 겹친다).
# 겹치는 3계열의 정확값은 슬라이드 표에 그대로 있다.
SERIES = [
    ("논문 Claude Code (Fig.3, n=16,886)", "#8557C7", "o", [1.096, 2.034, 19.980], "[P]", True),
    ("TraceLab full (n=357,161)",          "#4A7FD0", "s", [0.169, 10.008, 180.883], "[M]", True),
    ("ec128k (cap 300s)",                  "#1E9E74", "^", [0.155, 7.060, 150.800], "[M]", False),
    ("ec40k (cap 300s)",                   "#B8860B", "D", [0.092, 4.800, 129.400], "[M]", False),
    ("swebench (cap 30s)",                 "#C0392B", "v", [0.227, 0.641, 2.420],   "[M]", True),
]
XS = [0, 1, 2]
XLAB = ["P50", "P90", "P99"]


def main():
    os.makedirs(FIGDIR, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9.2, 5.0), dpi=200)
    fig.patch.set_facecolor(SURF)
    ax.set_facecolor(SURF)

    for label, col, mk, ys, tag, do_label in SERIES:
        ax.plot(XS, ys, color=col, lw=2.0, marker=mk, ms=8,
                mec=SURF, mew=1.6, label=f"{label} {tag}", zorder=3)
        if do_label:  # 선택적 직접 라벨(secondary encoding): 오른쪽 끝 P99
            ax.annotate(f"{ys[2]:,.1f}s", xy=(2, ys[2]), xytext=(9, 0),
                        textcoords="offset points", va="center", ha="left",
                        fontsize=10, color=INK, zorder=4)

    ax.set_yscale("log")
    # 로그 눈금 라벨을 직접 지정 (NanumGothic에 U+2212 글리프가 없어 10^-1이 깨짐)
    ax.set_yticks([0.1, 1, 10, 100])
    ax.set_yticklabels(["0.1", "1", "10", "100"])
    ax.minorticks_off()
    ax.set_xticks(XS)
    ax.set_xticklabels(XLAB, fontsize=12, color=INK)
    ax.set_xlim(-0.18, 2.62)
    ax.set_ylabel("툴콜 지연 (s, 로그축)", fontsize=11.5, color=INK)
    ax.set_title("툴콜 지연 백분위 프로파일: 논문 trace vs 내 trace 4종",
                 fontsize=13.5, color=INK, pad=12, loc="left")

    ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=10)

    leg = ax.legend(loc="upper left", fontsize=9.5, frameon=False,
                    labelcolor=INK, handlelength=2.2)
    leg.set_zorder(5)

    fig.text(0.012, 0.015,
             "[P] 논문 Fig.3 / 3.3절 (계획서 C-1 원문 대조)    "
             "[M] 내 실측 (계획서 C-1 실측표)    "
             "/ 논문은 P50이 우리보다 6.5배 길고, 우리 trace는 P99 tail이 9배 무겁다",
             fontsize=8.5, color=MUTED)

    fig.tight_layout(rect=(0, 0.035, 1, 1))
    fig.savefig(OUT, facecolor=SURF)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
