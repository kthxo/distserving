#!/usr/bin/env python3
"""Phase 2 v2 그림 — C_crit(r) 예측 vs 실측.

지표는 **불편향 엔진 steady-window**(key="eng")를 기본으로 쓴다.
드라이버 throughput은 완료-경계 편향이 있어 패널 A에 점선 보조계열로만 표시한다.

패널 A: C=32 고정, r 스윕 → MORI/TA+O 비 (1.0 교차가 dial② 확정선)
패널 B: r=4 고정, C 스윕 → 붕괴 임계가 C_crit=40.5 근처인가
패널 C: (r, C) 격자에서 예측(수용률 = (1+r)·fit / C)과 실측 비를 겹쳐 봄

dataviz 규칙: dual-axis 금지(패널 분리), 고정 순서 팔레트, 계열 2개↑면 legend+직접라벨.
데이터는 analyze_phase2 가 만든 JSON만 읽는다 (하드코딩 없음).
"""
import argparse
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Noto Sans CJK KR"
plt.rcParams["axes.unicode_minus"] = False

MORI, TAO, OK, BAD = "#C0392B", "#2E5EAA", "#1E7D4F", "#C0392B"
MUTE2 = "#6B6B7B"
INK, MUTE, GRID = "#1A1A2E", "#6B6B7B", "#DDE1E8"
WIN_BG, LOSE_BG = "#E7F3EC", "#FBE9E7"
FIG = "/home/yunuikang/yunuikang_work/distserving/figures"


def style(ax, ylab=None, xlab=None, title=None):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTE, labelsize=9, length=3)
    ax.grid(axis="y", color=GRID, lw=0.7, alpha=0.9)
    ax.set_axisbelow(True)
    if ylab: ax.set_ylabel(ylab, color=MUTE, fontsize=9.5)
    if xlab: ax.set_xlabel(xlab, color=MUTE, fontsize=9.5)
    if title: ax.set_title(title, color=INK, fontsize=11, fontweight="bold", pad=8)


def mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="/home/yunuikang/yunuikang_work/scratch/mori/phase2_v2_summary.json")
    args = ap.parse_args()
    D = json.load(open(args.json))
    FIT = D["fit"]
    cells = D["cells"]

    def pick(sys_, r, C, key="eng"):
        return mean([v[key] for v in cells.values() if v["sys"] == sys_ and v["r"] == r and v["C"] == C])

    fig, axes = plt.subplots(1, 3, figsize=(13.0, 3.3))

    # ---- 패널 A: C=32, r 스윕 ----
    ax = axes[0]
    rs, ratios, crits = [], [], []
    for r in (2, 3, 4):
        m, t = pick("MORI", r, 32), pick("TAO", r, 32)
        if m and t:
            rs.append(r); ratios.append(m / t); crits.append((1 + r) * FIT)
    if rs:
        ax.axhspan(1.0, max(1.6, max(ratios) * 1.15), color=WIN_BG, zorder=0)
        ax.axhspan(min(0.3, min(ratios) * 0.85), 1.0, color=LOSE_BG, zorder=0)
        ax.plot(rs, ratios, "-o", color=MORI, lw=2.2, ms=8,
                markeredgecolor="white", markeredgewidth=1.4, zorder=3,
                label="MORI ÷ TA+O (엔진, 불편향)")
        dr = [(pick("MORI", r, 32, "drv") or 0) / (pick("TAO", r, 32, "drv") or 1) for r in rs]
        if any(dr):
            ax.plot(rs, dr, "--s", color=MUTE2, lw=1.5, ms=6, alpha=0.85, zorder=2,
                    label="(참고) 드라이버 — 완료경계 편향")
        ax.axhline(1.0, color=INK, lw=1.4, ls="--", zorder=2)
        for r, v, c in zip(rs, ratios, crits):
            ax.annotate(f"{v:.2f}×", (r, v), textcoords="offset points", xytext=(0, 11),
                        ha="center", fontsize=9, color=INK, fontweight="bold")
            ax.annotate(f"C_crit {c:.1f}", (r, v), textcoords="offset points", xytext=(0, -18),
                        ha="center", fontsize=8, color=MUTE)
        ax.set_xticks(rs)
        ax.text(rs[0], 1.03, "MORI 우위", fontsize=8.5, color=OK, fontweight="bold")
        ax.text(rs[0], 0.94, "MORI 열세", fontsize=8.5, color=BAD, fontweight="bold")
    style(ax, ylab="MORI ÷ TA+O (엔진 steady-window)", xlab="CPU tier r",
          title="A. C=32 고정 · r 스윕\n(1.0 교차 = dial② 확정)")
    ax.legend(frameon=False, fontsize=8.5, loc="lower right")

    # ---- 패널 B: r=4, C 스윕 ----
    ax = axes[1]
    Cs, rat = [], []
    for C in (32, 40, 48):
        m, t = pick("MORI", 4, C), pick("TAO", 4, C)
        if m and t:
            Cs.append(C); rat.append(m / t)
    crit4 = 5 * FIT
    if Cs:
        ax.axhline(1.0, color=INK, lw=1.4, ls="--", zorder=2)
        ax.axvline(crit4, color=OK, lw=1.6, ls=":", zorder=2)
        ax.plot(Cs, rat, "-o", color=MORI, lw=2.2, ms=8,
                markeredgecolor="white", markeredgewidth=1.4, zorder=3, label="MORI ÷ TA+O")
        for C, v in zip(Cs, rat):
            ax.annotate(f"{v:.2f}×", (C, v), textcoords="offset points", xytext=(0, 11),
                        ha="center", fontsize=9, color=INK, fontweight="bold")
        ax.annotate(f"예측 임계\nC_crit={crit4:.1f}", (crit4, max(rat)), textcoords="offset points",
                    xytext=(8, -6), fontsize=8.5, color=OK, fontweight="bold")
        ax.set_xticks(Cs)
    style(ax, ylab="MORI ÷ TA+O", xlab="동시성 C  (r=4 고정)",
          title="B. r=4 고정 · C 스윕\n(임계가 예측 위치인가)")
    ax.legend(frameon=False, fontsize=8.5, loc="lower left")

    # ---- 패널 C: 수용률(예측) vs 실측 비 ----
    ax = axes[2]
    xs, ys, labs = [], [], []
    for v in cells.values():
        if v["sys"] != "MORI":
            continue
        t = pick("TAO", v["r"], v["C"])
        if not t:
            continue
        if not v.get("eng"):
            continue
        cover = (1 + v["r"]) * FIT / v["C"]          # GPU+CPU ÷ 워크셋
        xs.append(cover); ys.append(v["eng"] / t); labs.append(f"r{v['r']}C{v['C']}")
    if xs:
        ax.axvline(1.0, color=OK, lw=1.5, ls=":", zorder=2)
        ax.axhline(1.0, color=INK, lw=1.4, ls="--", zorder=2)
        ax.scatter(xs, ys, s=70, color=MORI, edgecolor="white", linewidth=1.4, zorder=3)
        seen = set()
        for x, y, l in zip(xs, ys, labs):
            if l in seen:
                continue
            seen.add(l)
            ax.annotate(l, (x, y), textcoords="offset points", xytext=(6, 5),
                        fontsize=8, color=INK)
        ax.text(1.02, min(ys) if ys else 0.5, "수용률 100%\n(GPU+CPU = 워크셋)",
                fontsize=8, color=OK, fontweight="bold")
    style(ax, ylab="MORI ÷ TA+O", xlab="수용률 = (1+r)·fit ÷ C",
          title="C. 가설의 한 장 요약\n수용률>1 이면 MORI 우위여야")

    fig.suptitle(f"Phase 2 — dial② 격리 검증 (goguma6 5090, fit={FIT:.2f})   [측정]",
                 fontsize=11.5, color=MUTE, y=1.04)
    os.makedirs(FIG, exist_ok=True)
    p = os.path.join(FIG, "mori_phase2_rsweep_yunuikang.png")
    fig.savefig(p, dpi=200, bbox_inches="tight", facecolor="white")
    print("wrote", p)


if __name__ == "__main__":
    main()
