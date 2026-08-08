#!/usr/bin/env python3
"""F6 — TTFT 페널티: 네 조건 전부에서 MORI가 진다 (유일한 구조적 약점).

5090(8B·TP2) · H200 7B · H200 8B · H200 Phase2 C80 — 하드웨어·모델·셀길이·fit 이
전부 달라도 **방향이 한 번도 안 뒤집힌다.** 배율만 1.13~4.09× 로 흔들린다.
원인 지목: 승격이 5초 tick 에서만 일어난다(scheduler/router.py:746-753).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plot_h200_lib_yunuikang import (  # noqa: E402
    phase1, phase2, style, save, INK, MUTE, BAD, OK, WIN_BG, LOSE_BG)
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# 5090 앵커 [측정, H200_RESULTS §3.2·§3.4]
A5090_P50, A5090_P95 = 4.09, 3.31


def main():
    p7, p8, P2 = phase1("h200_phase1"), phase1("h200_phase1_8b"), phase2()
    conds = [
        ("5090 C80\n8B · TP2 · fit 8.1", A5090_P50, A5090_P95, "#4A4A63"),
        ("H200 F1\n7B · TP1 · fit 8.1", p7["MORI"]["ttft_p50_s"] / p7["TAO"]["ttft_p50_s"],
         p7["MORI"]["ttft_p95_s"] / p7["TAO"]["ttft_p95_s"], BAD),
        ("H200 F1\n8B · TP1 · fit 8.1", p8["MORI"]["ttft_p50_s"] / p8["TAO"]["ttft_p50_s"],
         p8["MORI"]["ttft_p95_s"] / p8["TAO"]["ttft_p95_s"], BAD),
        ("H200 Phase 2\n7B · TP1 · fit 20 · C80",
         P2[("MORI", 80)]["ttft_p50_s"] / P2[("TAO", 80)]["ttft_p50_s"],
         P2[("MORI", 80)]["ttft_p95_s"] / P2[("TAO", 80)]["ttft_p95_s"], BAD),
    ]
    xs, w = np.arange(len(conds)), 0.34
    fig, ax = plt.subplots(figsize=(10.4, 4.2))
    ax.axhspan(0, 1.0, color=WIN_BG, zorder=0)
    ax.axhspan(1.0, 5.0, color=LOSE_BG, zorder=0)

    for k, (lab, key) in enumerate((("TTFT p50", 1), ("TTFT p95 (꼬리)", 2))):
        pos = xs + (k - 0.5) * w
        vals = [c[key] for c in conds]
        cols = [c[3] for c in conds]
        ax.bar(pos, vals, w, color=cols, edgecolor="white", lw=1.3,
               hatch=None if k == 0 else "///", zorder=3)
        for xi, v in zip(pos, vals):
            ax.annotate(f"{v:.2f}×", (xi, v), textcoords="offset points", xytext=(0, 6),
                        ha="center", fontsize=10, fontweight="bold", color=INK, zorder=4)
    ax.axhline(1.0, color=INK, lw=1.8, ls="--", zorder=5)
    ax.set_xticks(xs); ax.set_xticklabels([c[0] for c in conds], fontsize=9)
    ax.set_ylim(0, 5.0); ax.set_xlim(-0.62, len(conds) - 0.38)
    style(ax, ylab="MORI ÷ TA+O   (TTFT — 낮을수록 좋다)",
          title="네 조건 전부에서 MORI의 TTFT가 나쁘다 — 방향이 한 번도 안 뒤집힌다")

    ax.text(-0.55, 4.62, "민 = p50 · 빗금 = p95(꼬리)", fontsize=9, color=MUTE)
    ax.text(1.45, 4.35,
            "★ 원인 지목: 승격이 5초 tick 에서만 일어난다\n"
            "     (scheduler/router.py:746-753)\n"
            "     H200 8B p95 66.7 s ≈ 13 tick × 5 s 로 정합   [추론]",
            fontsize=9, color=INK, fontweight="bold", va="top",
            bbox=dict(boxstyle="round,pad=0.45", facecolor="white",
                      edgecolor="#DDE1E8", linewidth=1.0))
    ax.text(0.0, -0.20, "파선 1.0 = 동률 · 위 = MORI 가 느리다(네 조건 전부 위). "
                        "goodput 은 MORI 가 이겼다(P2) — 진 것은 TTFT 뿐이다. "
                        "n=1(반복 없음, run 변동 ~15%)   [측정]",
            transform=ax.transAxes, fontsize=8, color=MUTE)
    save(fig, "mori_h200_f6_ttft_yunuikang")
    for lab, a, b, _ in conds:
        print(f"{lab.splitlines()[0]:16} p50 {a:.2f}x  p95 {b:.2f}x")


if __name__ == "__main__":
    main()
