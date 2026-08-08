#!/usr/bin/env python3
"""F4 — Phase 2 C 곡선 4종 (덱의 본체 그림).

x = C{20,40,80} · y = goodput@5s · 계열 SMG/TA/TA+O/MORI.
SMG가 C40에서 0.21로 절벽 붕괴해 선형축이면 나머지 3종이 뭉갠다
→ **로그축 금지·이중축 금지** 대신 **패널 분리**: 좌 = 전체(로그), 우 = 3종 확대(선형).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plot_h200_lib_yunuikang import (  # noqa: E402
    phase2, style, save, SYS_COLOR, SYS_LABEL, SYS_ORDER, INK, MUTE, BAD)
import matplotlib.pyplot as plt  # noqa: E402

CS = [20, 40, 80]
OVER = {20: "1.00×", 40: "2.00×", 80: "4.00×"}


def main():
    P = phase2()
    g = lambda s, c: P[(s, c)]["goodput_5s"]
    fig, axes = plt.subplots(1, 2, figsize=(11.6, 3.9),
                             gridspec_kw={"width_ratios": [1.0, 1.05]})

    # ---------- 좌: 4종 전체 (로그축) ----------
    ax = axes[0]
    for s in SYS_ORDER:
        ys = [max(g(s, c), 0.008) for c in CS]     # log 축용 floor (SMG C80 = 0.00)
        ax.plot(CS, ys, "-o", color=SYS_COLOR[s], lw=2.4, ms=8,
                markeredgecolor="white", markeredgewidth=1.3, label=SYS_LABEL[s])
    ax.set_yscale("log")
    ax.set_xticks(CS)
    ax.set_xticklabels([f"C={c}\n{OVER[c]}" for c in CS], fontsize=9.5)
    ax.set_ylim(0.006, 600)
    style(ax, ylab="goodput @SLO 5s (tok/s, 로그축)", xlab="동시성 C  (아래는 oversub)",
          title="A. 4종 전체 — SMG는 압박이 오면 0으로")
    ax.legend(frameon=False, fontsize=9, loc="center left")
    ax.annotate("SMG 158.07 → 0.21 → 0.00\n(admission control 없음)",
                xy=(41, 0.30), xytext=(45, 2.2), fontsize=8.5, color=SYS_COLOR["SMG"],
                fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=SYS_COLOR["SMG"], lw=1.2))
    ax.text(0.98, 0.96, "SMG C80 의 0.00 은 로그축 표시를 위해 하단에 고정",
            transform=ax.transAxes, fontsize=7.5, color=MUTE, ha="right", va="top")

    # ---------- 우: 3종 확대 (선형) ----------
    ax = axes[1]
    for s in ("TA", "TAO", "MORI"):
        ys = [g(s, c) for c in CS]
        ax.plot(CS, ys, "-o", color=SYS_COLOR[s], lw=2.6, ms=9,
                markeredgecolor="white", markeredgewidth=1.4, label=SYS_LABEL[s])
        for c, v in zip(CS, ys):
            up = s == "MORI" or (s == "TA" and c == 20)
            ax.annotate(f"{v:.1f}", (c, v), textcoords="offset points",
                        xytext=(0, 12 if up else -18), ha="center",
                        fontsize=9, color=SYS_COLOR[s], fontweight="bold")
    ax.set_xticks(CS)
    ax.set_xticklabels([f"C={c}\n{OVER[c]}" for c in CS], fontsize=9.5)
    ax.set_ylim(147, 228)
    style(ax, ylab="goodput @SLO 5s (tok/s)", xlab="동시성 C  (아래는 oversub)",
          title="B. ★ 3종 확대 — MORI가 전 C에서 1등,\nC가 오를수록 격차 확대")
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    # MORI−TA+O 격차: 두 선 사이 중점에 표기 (하단 행 없이)
    for c in CS:
        mid = (g("MORI", c) + g("TAO", c)) / 2
        d = (g("MORI", c) / g("TAO", c) - 1) * 100
        ax.annotate(f"+{d:.1f}%", (c, mid), textcoords="offset points", xytext=(16, -3),
                    ha="left", fontsize=9.5, color=BAD, fontweight="bold")
        ax.plot([c, c], [g("TAO", c), g("MORI", c)], color=BAD, lw=1.0, alpha=0.45, zorder=1)

    fig.suptitle("H200 Phase 2 · 7B · fit 20 · r=2 · 60분 · 12/12셀 · n=1(반복 없음, run 변동 ~15%)   [측정]",
                 fontsize=10, color=MUTE, y=1.04)
    save(fig, "mori_h200_f4_curve_yunuikang")

    print(f"\n{'C':>4} {'SMG':>8} {'TA':>8} {'TA+O':>8} {'MORI':>8}  MORI/TAO")
    for c in CS:
        print(f"{c:4d} {g('SMG',c):8.2f} {g('TA',c):8.2f} {g('TAO',c):8.2f} "
              f"{g('MORI',c):8.2f}  {g('MORI',c)/g('TAO',c):.4f}")


if __name__ == "__main__":
    main()
