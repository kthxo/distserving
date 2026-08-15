#!/usr/bin/env python3
"""plot_traces3_cdf_yunuikang.py — 3종 TraceLab 트레이스 분포 오버레이 (READ-ONLY).

입력: char_traces3_yunuikang.py --npz 로 저장한 raw 배열 (.npz)
출력: figures/trace3_context_cdf_yunuikang.png
      figures/trace3_tool_cdf_yunuikang.png
      figures/trace3_turns_hist_yunuikang.png
      figures/trace3_panels_yunuikang.png   (1x3 통합)

수치 출처: 지어낸 값 없음. 전부 npz 의 실측 배열에서 직접 계산.
palette: dataviz 스킬 validate_palette.js 6검사 전항 PASS
  ("#4A7FD0,#1E9E74,#B8860B", light, surface #fcfcfb;
   최악 인접쌍 protan ΔE 9.0 / normal ΔE 17.3)
  + 2차 인코딩(시리즈별 마커 + 직접 라벨)로 색 단독 의존 제거.
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = os.path.dirname(os.path.abspath(__file__))
_TTF = os.path.join(HERE, "NanumGothic_yunuikang.ttf")
if os.path.exists(_TTF):
    font_manager.fontManager.addfont(_TTF)
    plt.rcParams["font.family"] = font_manager.FontProperties(fname=_TTF).get_name()
plt.rcParams["axes.unicode_minus"] = False   # NanumGothic 에 U+2212 없음

INK, MUTED, GRID, SURF = "#1f2430", "#6B7280", "#DFE3EA", "#FCFCFB"

# label -> (표시명, 색, 마커)  — 고정 순서, 순환 금지
SERIES = [
    ("full",   "원본 full (cap 없음)",      "#4A7FD0", "o"),
    ("trackM", "Track M (현재 사용)",        "#1E9E74", "s"),
    ("fit32k", "fit32k (7월 초 컷)",         "#B8860B", "^"),
]

FLOOR = 1e-3   # log 축 하한 (tool_s=0 은 이 위치에 쌓임)


def style(ax, xlab, ylab, title=None, grid_axis="both"):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9, length=3)
    ax.set_xlabel(xlab, color=INK, fontsize=10)
    ax.set_ylabel(ylab, color=INK, fontsize=10)
    if title:
        ax.set_title(title, color=INK, fontsize=11.5, pad=10, loc="left")
    ax.grid(True, axis=grid_axis, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.set_facecolor(SURF)


def logticks(ax):
    """NanumGothic 에 U+2212(마이너스)가 없어 log 눈금 라벨을 수동 지정."""
    lo, hi = ax.get_xlim()
    e0, e1 = int(np.floor(np.log10(lo))), int(np.ceil(np.log10(hi)))
    ticks, labs = [], []
    for e in range(e0, e1 + 1):
        v = 10.0 ** e
        if not (lo <= v <= hi):
            continue
        ticks.append(v)
        if e < 0:
            labs.append(("0." + "0" * (-e - 1) + "1"))
        elif e < 4:
            labs.append(f"{int(v):,}")
        else:
            labs.append(f"{int(v)//1000:,}k")
    ax.set_xticks(ticks)
    ax.set_xticklabels(labs)
    ax.set_xticks([], minor=True)


def cdf_xy(v, floor=None):
    a = np.sort(np.asarray(v, float))
    if floor is not None:
        a = np.clip(a, floor, None)
    y = np.arange(1, a.size + 1) / a.size
    return a, y


def draw_cdf(ax, data, key, xlab, title, floor=None, marker_qs=(0.25, 0.5, 0.9)):
    for lab, name, col, mk in SERIES:
        v = data.get(f"{lab}__{key}")
        if v is None:
            continue
        x, y = cdf_xy(v, floor)
        ax.plot(x, y, color=col, lw=2.0, label=name, zorder=3, solid_capstyle="round")
        # 2차 인코딩: 분위 지점 마커
        idx = [min(int(q * len(x)), len(x) - 1) for q in marker_qs]
        ax.plot(x[idx], y[idx], linestyle="none", marker=mk, ms=8, color=col,
                markeredgecolor="white", markeredgewidth=1.2, zorder=4)
    ax.set_xscale("log")
    ax.set_ylim(0, 1.05)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0", "25", "50", "75", "100"])
    ax.axhline(0.5, color=MUTED, lw=0.8, ls=(0, (4, 4)), zorder=1)
    logticks(ax)
    style(ax, xlab, "누적 비율 (%)", title)


def draw_turns_hist(ax, data):
    # turn 은 정수: log 빈 폭이 1 미만이면 빈 칸이 생겨 빗살 아티팩트가 난다.
    # 정수 경계로 유일화해 모든 빈이 최소 1턴을 덮게 한다.
    bins = np.unique(np.round(np.logspace(0, np.log10(8000), 34)).astype(int))
    bins = np.append(bins, bins[-1] + 1).astype(float)
    for lab, name, col, mk in SERIES:
        v = data.get(f"{lab}__turns_per_session")
        if v is None:
            continue
        h, e = np.histogram(np.clip(v, 1, None), bins=bins)
        frac = 100.0 * h / h.sum()
        ctr = np.sqrt(e[:-1] * e[1:])
        ax.step(e[:-1], frac, where="post", color=col, lw=2.0, label=name, zorder=3)
        pk = int(np.argmax(frac))
        ax.plot([ctr[pk]], [frac[pk]], linestyle="none", marker=mk, ms=8, color=col,
                markeredgecolor="white", markeredgewidth=1.2, zorder=4)
    ax.set_xscale("log")
    logticks(ax)
    style(ax, "세션당 turn 수 (log)", "세션 비율 (%)", "세션당 turn 수 분포")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz", required=True)
    ap.add_argument("--outdir", default=os.path.join(os.path.dirname(HERE), "figures"))
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    d = np.load(args.npz)

    def save(fig, name):
        p = os.path.join(args.outdir, name)
        fig.savefig(p, dpi=200, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        print("[ok]", p)

    specs = [
        ("context", lambda ax: draw_cdf(ax, d, "input", "per-turn input_tokens (컨텍스트, log)",
                                        "컨텍스트 길이 CDF"),
         "trace3_context_cdf_yunuikang.png"),
        ("tool", lambda ax: draw_cdf(ax, d, "tool", "tool_duration_s (log, 0 은 1 ms 위치)",
                                     "툴콜 duration CDF", FLOOR),
         "trace3_tool_cdf_yunuikang.png"),
        ("turns", lambda ax: draw_turns_hist(ax, d), "trace3_turns_hist_yunuikang.png"),
    ]

    # 개별 단일 패널
    for _k, fn, name in specs:
        fig, ax = plt.subplots(figsize=(6.4, 4.4))
        fn(ax)
        ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="best")
        save(fig, name)

    # 1x3 통합
    fig, axes = plt.subplots(1, 3, figsize=(16.2, 4.6))
    for (_k, fn, _n), ax in zip(specs, axes):
        fn(ax)
    axes[0].legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper left")
    fig.suptitle("TraceLab 3종 트레이스 분포 비교: 원본 / Track M / fit32k",
                 color=INK, fontsize=13, x=0.005, ha="left", y=1.04)
    fig.tight_layout()
    save(fig, "trace3_panels_yunuikang.png")


if __name__ == "__main__":
    main()
