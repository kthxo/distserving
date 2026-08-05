#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""논문 Fig.3 툴콜 분포 매칭 현황 — 백분위 프로파일 + long-time-share 위치도.

수치 출처(지어낸 값 0개):
  논문 target : MORI.pdf Fig.3 (n=16,886) — P50 1,096ms / P90 2,034ms /
                P99 19,980ms / P99.95 83,626ms, 2s 임계 short/long 87/13,
                long time-share 58% (MORI.pdf p.4 Fig.3 · §3.3 본문 직접 대조).
  내 trace    : plans/2026-07-30_PLAN_mori-on-thunderagent-goguma6_yunuikang.md
                §C-4 측정표 (원본 gz per-call n=431,905 / human-wait gap n=33,501).

palette: dataviz 스킬 validate_palette.js --pairs all 6검사 전항 PASS
  ("#8557C7,#C0392B,#B8860B,#1E9E74", light, surface #fcfcfb)
secondary encoding: 계열별 마커 + 직접 라벨(색만으로 식별하지 않음).
Output: figures/mori_fig3_match_yunuikang.png
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = os.path.dirname(os.path.abspath(__file__))
FIGDIR = os.path.join(os.path.dirname(HERE), "figures")
FONT_TTF = os.path.join(HERE, "NanumGothic_yunuikang.ttf")
OUT = os.path.join(FIGDIR, "mori_fig3_match_yunuikang.png")

if os.path.exists(FONT_TTF):
    font_manager.fontManager.addfont(FONT_TTF)
    plt.rcParams["font.family"] = font_manager.FontProperties(fname=FONT_TTF).get_name()
plt.rcParams["axes.unicode_minus"] = False

INK, MUTED, GRID, SURF = "#1f2430", "#6B7280", "#DFE3EA", "#FCFCFB"
PAPER, PRIMARY, TOOLS, SWE = "#8557C7", "#C0392B", "#B8860B", "#1E9E74"

# (label, color, marker, [P50,P90,P99,P99.95], long-time-share %)
SERIES = [
    ("논문 target (Fig.3)",        PAPER,   "o", [1.096, 2.034, 19.98, 83.63],   58.0),
    ("full: tools만",              TOOLS,   "D", [0.196, 8.17, 180.0, 1938.0],   98.2),
    ("full: +human-wait (primary)", PRIMARY, "s", [0.240, 30.0, 955.7, 27284.0], 99.7),
    ("swebench",                   SWE,     "^", [0.227, 0.643, 2.46, 30.0],     29.9),
]
XS = [0, 1, 2, 3]
XLAB = ["P50", "P90", "P99", "P99.95"]


def main():
    os.makedirs(FIGDIR, exist_ok=True)
    fig, (axL, axR) = plt.subplots(
        1, 2, figsize=(11.6, 4.3), dpi=200,
        gridspec_kw={"width_ratios": [1.42, 1.0], "wspace": 0.30})
    fig.patch.set_facecolor(SURF)

    # ── (a) 백분위 프로파일 ────────────────────────────────────────────
    axL.set_facecolor(SURF)
    for label, col, mk, ys, _ in SERIES:
        axL.plot(XS, ys, color=col, lw=2.0, marker=mk, ms=7.5,
                 mec=SURF, mew=1.5, label=label, zorder=3)
    # 논문 P50과 우리 P50의 격차만 직접 라벨 (핵심 진단)
    axL.annotate("논문 1.10s", xy=(0, 1.096), xytext=(6, 12),
                 textcoords="offset points", fontsize=9.5, color=PAPER,
                 fontweight="bold", zorder=4)
    axL.annotate("우리 0.20s (-82%)", xy=(0, 0.196), xytext=(13, -3),
                 textcoords="offset points", fontsize=9.5, color=TOOLS,
                 fontweight="bold", zorder=4)

    axL.set_yscale("log")
    axL.set_yticks([0.1, 1, 10, 100, 1000, 10000])
    axL.set_yticklabels(["0.1", "1", "10", "100", "1,000", "10,000"])
    axL.minorticks_off()
    axL.set_xticks(XS); axL.set_xticklabels(XLAB, fontsize=11, color=INK)
    axL.set_xlim(-0.22, 3.3)
    axL.set_ylabel("툴콜 지연 (s, 로그축)", fontsize=10.5, color=INK)
    axL.set_title("(a) 백분위 프로파일: 논문 target 대비",
                  fontsize=12, color=INK, pad=9, loc="left")
    axL.grid(axis="y", color=GRID, lw=0.8, zorder=0); axL.set_axisbelow(True)
    for sp in ("top", "right"):
        axL.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        axL.spines[sp].set_color(GRID)
    axL.tick_params(colors=MUTED, labelsize=9.5)
    axL.legend(loc="upper left", fontsize=9, frameon=False, labelcolor=INK,
               handlelength=2.0)

    # ── (b) long-time-share 위치도 ────────────────────────────────────
    axR.set_facecolor(SURF)
    order = [SERIES[3], SERIES[0], SERIES[1], SERIES[2]]  # 29.9 → 58 → 98.2 → 99.7
    ypos = list(range(len(order)))[::-1]
    for y, (label, col, mk, _, share) in zip(ypos, order):
        axR.plot([0, share], [y, y], color=col, lw=2.4, zorder=2,
                 solid_capstyle="round")
        axR.plot([share], [y], marker=mk, ms=10, color=col, mec=SURF,
                 mew=1.5, zorder=3)
        axR.annotate(f"{share}%", xy=(share, y), xytext=(9, 0),
                     textcoords="offset points", va="center", fontsize=10,
                     color=INK, fontweight="bold", zorder=4)
    axR.axvline(58.0, color=PAPER, ls=(0, (4, 3)), lw=1.6, zorder=1)
    axR.text(58.0, len(order) - 0.42, "  논문 58%", color=PAPER, fontsize=9.5,
             fontweight="bold", va="top")

    axR.set_yticks(ypos)
    axR.set_yticklabels([o[0] for o in order], fontsize=9.5, color=INK)
    axR.set_xlim(0, 122); axR.set_ylim(-0.6, len(order) - 0.35)
    axR.set_xticks([0, 25, 50, 75, 100])
    axR.set_xticklabels(["0", "25", "50", "75", "100"])
    axR.set_title("(b) long(>2s) 콜의 tool-time 점유율 (%)\n"
                  "    논문 58%는 우리 두 극단 사이에 있다",
                  fontsize=12, color=INK, pad=9, loc="left")
    axR.grid(axis="x", color=GRID, lw=0.8, zorder=0); axR.set_axisbelow(True)
    for sp in ("top", "right", "left"):
        axR.spines[sp].set_visible(False)
    axR.spines["bottom"].set_color(GRID)
    axR.tick_params(colors=MUTED, labelsize=9.5, left=False)

    fig.text(0.008, 0.012,
             "논문 target = MORI.pdf Fig.3 / 3.3절 (직접 대조)    "
             "내 trace = 계획서 goguma6판 C-4 측정표 (원본 gz per-call)    "
             "/ 진단: tail이 아니라 short 콜이 너무 짧아 long-share가 구조적으로 초과",
             fontsize=8.5, color=MUTED)

    fig.tight_layout(rect=(0, 0.10, 1, 1))
    fig.savefig(OUT, facecolor=SURF)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
