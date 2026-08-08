#!/usr/bin/env python3
"""F3 — 소거 사슬 다이어그램: 무엇을 지웠고 무엇이 남았나.

개념 그림이므로 matplotlib patches 로 직접 그린다(DECK_STYLE §5).
핵심: 하드웨어 축은 **소거로 도달**했을 뿐 **직접 조작한 적이 없고**, 그 안이 미분리다.
"원인은 인터커넥트"라고 쓰면 과장이다 (ANALYSIS §7.4-4).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plot_h200_lib_yunuikang import save, INK, MUTE, BAD, OK, AMBER  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch  # noqa: E402

GRID = "#DDE1E8"


def box(ax, x, y, w, h, fc, ec, title, sub, tc=INK, ts=10.5, ss=8.8):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.5",
                                facecolor=fc, edgecolor=ec, linewidth=1.8, zorder=3))
    ax.text(x + w / 2, y + h * 0.66, title, ha="center", va="center",
            color=tc, fontsize=ts, fontweight="bold", zorder=4)
    ax.text(x + w / 2, y + h * 0.27, sub, ha="center", va="center",
            color=tc, fontsize=ss, zorder=4)


def main():
    fig, ax = plt.subplots(figsize=(12.4, 4.3))
    ax.set_xlim(0, 100); ax.set_ylim(0, 62); ax.axis("off")

    ax.text(0, 58.5, "붕괴 원인 후보를 하나씩 지워 왔다 — 그리고 자원 축이 소진됐다",
            fontsize=12.5, color=INK, fontweight="bold")

    Y, H, W = 30, 15, 20.5
    steps = [
        (0.5, "① 코드 오류", "A 17/17 PASS · B 실동작 확인", "#EDEDF2", GRID, "지움"),
        (25.5, "② CPU 용량 (r/DRAM)", "5090: r 2→4, Waiting 11→1\n인데 goodput 1.05→0.66×", "#EDEDF2", GRID, "지움"),
        (50.5, "③ GPU 슬롯 (fit/HBM)", "H200: oversub 9.88× 에서\n붕괴 미재현 (1.405 · 1.080)", "#EDEDF2", GRID, "지움"),
    ]
    for x, t, s, fc, ec, tag in steps:
        box(ax, x, Y, W, H, fc, ec, t, s, tc=MUTE)
        ax.plot([x + 2, x + W - 2], [Y + H * 0.52, Y + H * 0.52], color=BAD, lw=2.0, zorder=5)
        ax.text(x + W / 2, Y - 3.4, f"{tag}", ha="center", fontsize=10,
                color=BAD, fontweight="bold")

    # 남은 것
    x4 = 75.5
    box(ax, x4, Y, 24, H, "#FBE9E7", BAD,
        "④ 하드웨어 축", "GPU 세대·대역폭 + TP2\n+ SYS·cross-NUMA", tc=INK)
    ax.text(x4 + 12, Y - 3.4, "▲ 남았다 — 그러나 미분리", ha="center", fontsize=10,
            color=BAD, fontweight="bold")

    for x in (21.5, 46.5, 71.5):
        ax.add_patch(FancyArrowPatch((x, Y + H / 2), (x + 3.6, Y + H / 2),
                                     arrowstyle="-|>", mutation_scale=15,
                                     color=MUTE, lw=1.8, zorder=2))

    # 경고 박스
    ax.add_patch(FancyBboxPatch((0.5, 3.5), 99, 17, boxstyle="round,pad=0.5",
                                facecolor="#FFFBEA", edgecolor=AMBER, linewidth=1.6, zorder=3))
    ax.text(2.5, 16.8, "▲  이것은 개입이 아니라 소거다", fontsize=11,
            color=INK, fontweight="bold", zorder=4)
    ax.text(2.5, 11.6,
            "fit 과 모델/KV밀도를 지웠을 뿐, 하드웨어 축을 **직접 조작한 적이 없다.**  "
            "④ 안의 세 요인은 이번 실험에서 분리되지 않았다.".replace("**", ""),
            fontsize=9.8, color=INK, zorder=4)
    ax.text(2.5, 7.0,
            "→ “원인은 인터커넥트다” 라고 말할 수 없다.   정확한 표현: "
            "“하드웨어 축(GPU세대·대역폭 + TP + cross-NUMA 묶음), 그 안은 미분리”",
            fontsize=9.8, color=BAD, fontweight="bold", zorder=4)

    ax.text(100, 0.2, "가르려면: 5090 에서 TP1 재실행 또는 H200 2장 TP2 — 이 머신(H200 1장)에서는 불가   [측정→추론]",
            ha="right", fontsize=8.2, color=MUTE)
    save(fig, "mori_h200_f3_chain_yunuikang")


if __name__ == "__main__":
    main()
