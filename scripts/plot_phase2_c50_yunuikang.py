#!/usr/bin/env python3
"""Phase 2 C=50 pivot 그림 — r 스윕 결과.

A: MORI÷TA+O 비 (3지표) vs r — 1.0 교차 여부
B: 절대 goodput MORI vs TA+O vs r — **정반대 추세**가 핵심
C: MORI 스래싱 3종 (%) vs r — 용량은 풀렸는데 스래싱은 안 풀림

dataviz: dual-axis 금지(패널 분리) · 고정 팔레트 · 계열 2개↑ legend+직접라벨.
데이터는 analyze_phase2_c50 이 만든 JSON만 읽는다.
"""
import argparse
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Noto Sans CJK KR"
plt.rcParams["axes.unicode_minus"] = False

MORI, TAO = "#C0392B", "#2E5EAA"
OK, BAD, INK, MUTE, GRID = "#1E7D4F", "#C0392B", "#1A1A2E", "#6B6B7B", "#DDE1E8"
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
    if title: ax.set_title(title, color=INK, fontsize=10.5, fontweight="bold", pad=8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="/home/yunuikang/yunuikang_work/scratch/mori/phase2_c50_summary.json")
    args = ap.parse_args()
    D = json.load(open(args.json))
    C = D["cells"]
    rs = [2, 3, 4]
    g = lambda sys_, r, k: C[f"{sys_}_r{r}_C50"][k]

    fig, axes = plt.subplots(1, 3, figsize=(13.0, 3.35))

    # ---- A: 비율 ----
    ax = axes[0]
    series = [("goodput @5s", "gp", MORI, "-o"), ("엔진 thr", "eng", MUTE, "--s"),
              ("드라이버(편향)", "drv", "#B87A1E", ":^")]
    ax.axhspan(1.0, 1.35, color=WIN_BG, zorder=0)
    ax.axhspan(0.4, 1.0, color=LOSE_BG, zorder=0)
    for lab, k, col, mk in series:
        ys = [g("MORI", r, k) / g("TAO", r, k) for r in rs]
        ax.plot(rs, ys, mk, color=col, lw=2.2 if k == "gp" else 1.6,
                ms=8 if k == "gp" else 6, markeredgecolor="white", markeredgewidth=1.2,
                zorder=4 if k == "gp" else 3, label=lab)
        if k == "gp":
            for r, v in zip(rs, ys):
                ax.annotate(f"{v:.2f}×", (r, v), textcoords="offset points", xytext=(0, 11),
                            ha="center", fontsize=9.5, color=INK, fontweight="bold")
    ax.axhline(1.0, color=INK, lw=1.4, ls="--", zorder=2)
    ax.set_xticks(rs); ax.set_ylim(0.35, 1.35); ax.set_xlim(1.85, 4.25)
    ax.text(4.22, 1.16, "MORI 우위", fontsize=8.5, color=OK, fontweight="bold", ha="right")
    ax.text(4.22, 0.90, "MORI 열세", fontsize=8.5, color=BAD, fontweight="bold", ha="right")
    style(ax, ylab="MORI ÷ TA+O", xlab="CPU tier r",
          title="A. 비율 — r을 올려도 1.0 위로 안 감\n(오히려 r=2가 최선)")
    ax.legend(frameon=False, fontsize=8, loc="lower left")

    # ---- B: 절대 goodput (정반대 추세) ----
    ax = axes[1]
    for sys_, col, lab in (("MORI", MORI, "MORI"), ("TAO", TAO, "TA+O")):
        ys = [g(sys_, r, "gp") for r in rs]
        ax.plot(rs, ys, "-o", color=col, lw=2.4, ms=8,
                markeredgecolor="white", markeredgewidth=1.3, label=lab)
        for r, v in zip(rs, ys):
            # 위/아래는 그 r에서 누가 높은지로 결정 (겹침 방지)
            up = v >= g("TAO" if sys_ == "MORI" else "MORI", r, "gp")
            ax.annotate(f"{v:.1f}", (r, v), textcoords="offset points",
                        xytext=(0, 11 if up else -17), ha="center",
                        fontsize=9, color=col, fontweight="bold")
    ax.set_xticks(rs); ax.set_ylim(12.5, 28.5); ax.set_xlim(1.85, 4.25)
    style(ax, ylab="goodput @SLO 5s (tok/s)", xlab="CPU tier r",
          title="B. ★ 정반대 추세\nr↑ 에 TA+O는 개선, MORI는 악화")
    ax.legend(frameon=False, fontsize=8.5, loc="lower left")
    ax.text(3.0, 27.4, "TA+O ↑ 개선", fontsize=8.5, color=TAO, ha="center", fontweight="bold")
    ax.text(3.5, 14.2, "MORI ↓ 악화", fontsize=8.5, color=MORI, ha="center", fontweight="bold")

    # ---- C: MORI 스래싱 3종 + Waiting ----
    ax = axes[2]
    for lab, k, col, mk, scale in (("ping-pong %", "pingpong", MORI, "-o", 1),
                                   ("pause 점유 %", "pause_share", "#6E4B9E", "-s", 1),
                                   ("prefix hit ×100", "hit", TAO, "-^", 100)):
        ys = [g("MORI", r, k) * scale for r in rs]
        ax.plot(rs, ys, mk, color=col, lw=2, ms=7,
                markeredgecolor="white", markeredgewidth=1.2, label=lab)
    ax.set_xticks(rs); ax.set_ylim(48, 116); ax.set_xlim(1.85, 4.25)
    for r in rs:
        ax.annotate(f"Waiting 축출\n{int(g('MORI', r, 'evict'))}건", (r, 52), ha="center",
                    fontsize=8, color=OK, fontweight="bold")
    style(ax, ylab="%", xlab="CPU tier r",
          title="C. 용량은 풀렸는데 스래싱은 그대로\n(Waiting 11→2→1 인데 ping-pong·pause 유지)")
    ax.legend(frameon=False, fontsize=8, loc="upper center", ncol=3,
              handlelength=1.4, columnspacing=1.0, borderpad=0.1)

    fig.suptitle("Phase 2 C=50 pivot — r 스윕은 MORI를 구조하지 못했다  ·  fit=8.10 · oversub 6.18×   [측정]",
                 fontsize=11, color=MUTE, y=1.05)
    os.makedirs(FIG, exist_ok=True)
    p = os.path.join(FIG, "mori_phase2_c50_yunuikang.png")
    fig.savefig(p, dpi=200, bbox_inches="tight", facecolor="white")
    print("wrote", p)

    # ---- 덱용 단일 패널 (헤드라인: 정반대 추세) ----
    f2, ax = plt.subplots(figsize=(5.6, 3.5))
    for sys_, col, lab in (("MORI", MORI, "MORI"), ("TAO", TAO, "TA+O (베이스라인)")):
        ys = [g(sys_, r, "gp") for r in rs]
        ax.plot(rs, ys, "-o", color=col, lw=2.8, ms=10,
                markeredgecolor="white", markeredgewidth=1.5, label=lab)
        for r, v in zip(rs, ys):
            up = v >= g("TAO" if sys_ == "MORI" else "MORI", r, "gp")
            ax.annotate(f"{v:.1f}", (r, v), textcoords="offset points",
                        xytext=(0, 13 if up else -20), ha="center",
                        fontsize=11.5, color=col, fontweight="bold")
    ax.set_xticks(rs)
    ax.set_xticklabels([f"r={r}\nMORI Waiting 축출 {int(g('MORI', r, 'evict'))}건" for r in rs],
                       fontsize=10)
    ax.set_ylim(12, 30); ax.set_xlim(1.8, 4.3)
    style(ax, ylab="goodput @SLO 5s (tok/s)", xlab="CPU tier 배수 r  (= DRAM 손잡이)")
    ax.legend(frameon=False, fontsize=10, loc="upper left", bbox_to_anchor=(0.0, 0.99))
    ax.text(3.05, 27.6, "TA+O ↑ 개선", fontsize=10.5, color=TAO, ha="center", fontweight="bold")
    ax.text(3.55, 14.6, "MORI ↓ 악화", fontsize=10.5, color=MORI, ha="center", fontweight="bold")
    p2 = os.path.join(FIG, "mori_phase2_c50_deck_yunuikang.png")
    f2.savefig(p2, dpi=200, bbox_inches="tight", facecolor="white")
    print("wrote", p2)
    print("\n비율 (MORI÷TA+O):")
    for r in rs:
        print(f"  r={r}: goodput {g('MORI',r,'gp')/g('TAO',r,'gp'):.2f}x · "
              f"엔진 {g('MORI',r,'eng')/g('TAO',r,'eng'):.2f}x · "
              f"MORI Waiting {int(g('MORI',r,'evict'))}건")


if __name__ == "__main__":
    main()
