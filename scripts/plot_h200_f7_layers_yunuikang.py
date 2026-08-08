#!/usr/bin/env python3
"""F7 — 층위 분해: 4종을 다 돌려야 보이는 것.

SMG→TA(스케줄러) · TA→TA+O(오프로딩) · TA+O→MORI(MORI 정책) 세 층위가
압박(C)에 비례해 값을 낸다. C=20에서는 앞 두 층이 마이너스(관리 비용만).

SMG→TA 는 C40에서 0.21→157.42 (+74,867%) 라 % 로 그리면 축이 망가진다
→ **왼쪽 패널은 절대값 누적(층위가 쌓이는 그림), 오른쪽은 % (SMG→TA 제외)**.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plot_h200_lib_yunuikang import (  # noqa: E402
    phase2, style, save, SYS_COLOR, INK, MUTE, BAD, OK)
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

CS = [20, 40, 80]


def main():
    P = phase2()
    g = lambda s, c: P[(s, c)]["goodput_5s"]
    fig, axes = plt.subplots(1, 2, figsize=(12.2, 4.0),
                             gridspec_kw={"width_ratios": [1.25, 1.0]})

    # ---------- 좌: 절대값 누적 ----------
    ax = axes[0]
    w, xs = 0.62, np.arange(len(CS))
    base = [g("SMG", c) for c in CS]
    sched = [g("TA", c) - g("SMG", c) for c in CS]
    offl = [g("TAO", c) - g("TA", c) for c in CS]
    pol = [g("MORI", c) - g("TAO", c) for c in CS]

    ax.bar(xs, base, w, color=SYS_COLOR["SMG"], edgecolor="white", lw=1.4, label="SMG (기본)")
    b1 = np.array(base)
    ax.bar(xs, sched, w, bottom=b1, color=SYS_COLOR["TA"], edgecolor="white", lw=1.4,
           label="+ 스케줄러 (SMG→TA)")
    b2 = b1 + np.array(sched)
    ax.bar(xs, offl, w, bottom=b2, color=SYS_COLOR["TAO"], edgecolor="white", lw=1.4,
           label="+ 오프로딩 (TA→TA+O)")
    b3 = b2 + np.array(offl)
    ax.bar(xs, pol, w, bottom=b3, color=SYS_COLOR["MORI"], edgecolor="white", lw=1.4,
           label="+ MORI 정책 (TA+O→MORI)")

    for i, c in enumerate(CS):
        ax.annotate(f"{g('MORI', c):.1f}", (i, g("MORI", c)), textcoords="offset points",
                    xytext=(0, 7), ha="center", fontsize=11, fontweight="bold", color=INK)
        if base[i] < 5:
            ax.annotate(f"SMG {base[i]:.2f}", (i, 4), ha="center", fontsize=8,
                        color=SYS_COLOR["SMG"], fontweight="bold")
    ax.set_xticks(xs)
    ax.set_xticklabels([f"C={c}\noversub {c/20:.2f}×" for c in CS], fontsize=9.5)
    ax.set_ylim(0, 268)
    style(ax, ylab="goodput @SLO 5s (tok/s)", xlab="동시성 C",
          title="A. 층위가 쌓여 최종 성능을 만든다")
    ax.legend(frameon=False, fontsize=8.2, loc="upper center", ncol=2,
              columnspacing=1.0, handlelength=1.3, borderpad=0.1)

    # ---------- 우: 층위별 기여율 (%) ----------
    ax = axes[1]
    layers = [("오프로딩\n(TA→TA+O)", SYS_COLOR["TAO"],
               [(g("TAO", c) / g("TA", c) - 1) * 100 for c in CS]),
              ("MORI 정책\n(TA+O→MORI)", SYS_COLOR["MORI"],
               [(g("MORI", c) / g("TAO", c) - 1) * 100 for c in CS])]
    w2 = 0.34
    for k, (name, col, vals) in enumerate(layers):
        pos = xs + (k - 0.5) * w2
        ax.bar(pos, vals, w2, color=col, edgecolor="white", lw=1.3, label=name)
        for xi, v in zip(pos, vals):
            ax.annotate(f"{v:+.1f}%", (xi, v), textcoords="offset points",
                        xytext=(0, 5 if v >= 0 else -14), ha="center",
                        fontsize=9.5, fontweight="bold", color=INK)
    ax.axhline(0, color=INK, lw=1.2)
    ax.set_xticks(xs); ax.set_xticklabels([f"C={c}" for c in CS], fontsize=9.5)
    ax.set_ylim(-4.5, 21)
    style(ax, ylab="goodput 증가율 (%)",
          title="B. ★ 압박이 커질수록 값을 낸다\n(C=20 에선 관리 비용만)")
    ax.legend(frameon=False, fontsize=8.5, loc="upper left")
    ax.text(0.0, -0.15, "스케줄러 층(SMG→TA)은 C40에서 0.21→157.42 (+74,867%) 이라\n이 축에 못 그린다 → 좌측 패널 참조",
            transform=ax.transAxes, fontsize=7.8, color=MUTE, ha="left", va="top")

    fig.suptitle("H200 Phase 2 · fit 20 · r=2 · 60분 · n=1(run 변동 ~15%)   [측정]",
                 fontsize=10, color=MUTE, y=1.03)
    save(fig, "mori_h200_f7_layers_yunuikang")
    for c in CS:
        print(f"C={c}: SMG→TA {g('TA',c)-g('SMG',c):+8.2f} · TA→TAO {(g('TAO',c)/g('TA',c)-1)*100:+6.1f}% · "
              f"TAO→MORI {(g('MORI',c)/g('TAO',c)-1)*100:+6.1f}%")


if __name__ == "__main__":
    main()
