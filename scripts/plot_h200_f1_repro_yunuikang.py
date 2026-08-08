#!/usr/bin/env python3
"""F1 — fit 가설 반증: 5090 붕괴가 H200에서 재현되지 않았다.

같은 oversub 9.88× · r=2 · GPU풀 262k tok 인데 MORI÷TA+O 가 뒤집혔다.
사전 등록 임계선 0.60(≤이면 재현)과 5090 앵커 0.45 를 같이 그린다.
주지표(드라이버)·부지표(엔진) 둘 다 표시 — 판정이 AND 라서 둘 다 보여야 한다.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plot_h200_lib_yunuikang import (  # noqa: E402
    phase1, style, save, INK, MUTE, OK, BAD, WIN_BG, LOSE_BG)
import matplotlib.pyplot as plt  # noqa: E402

THR = 0.60
ANCHOR = 0.45          # 5090 C80 [측정] MORI÷TA+O (드라이버)


def main():
    p7, p8 = phase1("h200_phase1"), phase1("h200_phase1_8b")
    drv7 = p7["MORI"]["ratio_driver_mori_over_tao"]
    eng7 = p7["MORI"]["ratio_engine_mori_over_tao"]
    drv8 = p8["MORI"]["ratio_driver_mori_over_tao"]
    eng8 = p8["MORI"]["ratio_engine_mori_over_tao"]

    fig, ax = plt.subplots(figsize=(9.4, 4.2))
    ax.axhspan(0, THR, color=WIN_BG, zorder=0)
    ax.axhspan(THR, 1.75, color=LOSE_BG, zorder=0)

    groups = [
        ("5090 C80\nQwen3-8B · TP2\n〔앵커〕", [("드라이버", ANCHOR)], "#4A4A63"),
        ("H200 F1\nQwen2.5-7B · TP1\n30분", [("드라이버", drv7), ("엔진", eng7)], BAD),
        ("H200 F1\nQwen3-8B · TP1\n60분", [("드라이버", drv8), ("엔진", eng8)], BAD),
    ]
    x, xt, xl = 0, [], []
    for gname, bars, col in groups:
        xs = [x + i * 0.62 for i in range(len(bars))]
        for (bname, v), xi in zip(bars, xs):
            hatch = None if bname == "드라이버" else "///"
            ax.bar(xi, v, width=0.52, color=col, edgecolor="white", linewidth=1.4,
                   hatch=hatch, zorder=3)
            ax.annotate(f"{v:.3f}", (xi, v), textcoords="offset points", xytext=(0, 6),
                        ha="center", fontsize=11, fontweight="bold", color=INK, zorder=4)
            ax.annotate(bname, (xi, 0.03), ha="center", fontsize=8.5, color="white",
                        fontweight="bold", zorder=4)
        xt.append(sum(xs) / len(xs)); xl.append(gname)
        x = xs[-1] + 1.15

    ax.axhline(THR, color=INK, lw=1.8, ls="--", zorder=5)
    ax.axhline(1.0, color=MUTE, lw=1.0, ls=":", zorder=5)
    ax.set_xticks(xt); ax.set_xticklabels(xl, fontsize=9.5)
    ax.set_ylim(0, 1.95); ax.set_xlim(-0.55, x - 0.6)
    style(ax, ylab="MORI ÷ TA+O  (throughput)",
          title="같은 oversub 9.88× · r=2 · GPU풀 262k tok — 그런데 결과가 뒤집혔다")

    # 임계선 설명은 5090 막대 위 빈 공간(좌측)에 둔다
    ax.text(-0.45, THR + 0.05, "사전 등록 임계 0.60 — 이 선 **아래**여야 “5090 붕괴 재현”".replace("**", ""),
            ha="left", fontsize=9, color=INK, fontweight="bold")
    ax.text(-0.45, 1.03, "1.0 = 동률", ha="left", fontsize=8.5, color=MUTE)
    ax.text(-0.45, 1.82, "판정: NOT_REPRODUCED  (4개 지표 전부 임계 초과)",
            fontsize=11.5, color=BAD, fontweight="bold")
    ax.text(-0.45, 1.69, "→ fit(HBM)은 5090 붕괴의 원인이 아니다",
            fontsize=10, color=INK, fontweight="bold")
    ax.text(0.0, -0.20, "빗금 = 엔진 steady 지표(부) · 민 = 드라이버 지표(주). 판정은 두 지표 AND. "
                        "n=1(반복 없음, run 변동 ~15%)   [측정]",
            transform=ax.transAxes, fontsize=8, color=MUTE)
    save(fig, "mori_h200_f1_repro_yunuikang")
    print(f"7B drv={drv7:.4f} eng={eng7:.4f} · 8B drv={drv8:.4f} eng={eng8:.4f} · 앵커 {ANCHOR}")


if __name__ == "__main__":
    main()
