#!/usr/bin/env python3
"""두 가지 붕괴 원인 다이어그램 — 왜 r 스윕이 둘을 가르는가.

좌: tier 파이프라인에 두 누수 지점(①CPU 용량 부족 ②GPU 슬롯 경쟁)을 표시
우: r을 올리면 **CPU 상자만** 커지고 GPU 슬롯(fit)은 그대로임을 시각화
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle, FancyBboxPatch

plt.rcParams["font.family"] = "Noto Sans CJK KR"
plt.rcParams["axes.unicode_minus"] = False

GPU_C, CPU_C, WAIT_C = "#2E5EAA", "#1E7D4F", "#6E4B9E"
BAD, INK, MUTE, GRID = "#C0392B", "#1A1A2E", "#6B6B7B", "#DDE1E8"
FIG = "/home/yunuikang/yunuikang_work/distserving/figures"


def box(ax, x, y, w, h, fc, txt, sub=None, fs=10, tc="white"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4",
                                facecolor=fc, edgecolor="none", zorder=3))
    ax.text(x + w / 2, y + h * (0.62 if sub else 0.5), txt, ha="center", va="center",
            color=tc, fontsize=fs, fontweight="bold", zorder=4)
    if sub:
        ax.text(x + w / 2, y + h * 0.26, sub, ha="center", va="center",
                color=tc, fontsize=fs - 1.8, zorder=4)


def arrow(ax, p1, p2, color, lw=2.0, style="-|>", ls="-"):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=14,
                                 color=color, lw=lw, linestyle=ls, zorder=2))


def main():
    fig, axes = plt.subplots(1, 2, figsize=(12.9, 3.35),
                             gridspec_kw={"width_ratios": [1.62, 1.0]})

    # ================= 좌: 파이프라인 + 두 누수 =================
    ax = axes[0]; ax.set_xlim(0, 100); ax.set_ylim(0, 78); ax.axis("off")
    ax.text(0, 74, "C=50 프로그램이 GPU 8칸을 두고 돈다", fontsize=11, fontweight="bold", color=INK)

    ROW = 50            # 박스 행 y (높이 13)
    box(ax, 1, ROW, 16, 13, "#4A4A63", "대기 42개", "(C=50 − fit 8)", fs=9.5)
    ax.add_patch(FancyBboxPatch((24, ROW - 1), 25, 15, boxstyle="round,pad=0.4",
                                facecolor="white", edgecolor=GPU_C, linewidth=2, zorder=3))
    ax.text(36.5, ROW + 11, "GPU — fit ≈ 8칸", ha="center", fontsize=10,
            fontweight="bold", color=GPU_C, zorder=4)
    for i in range(8):
        ax.add_patch(Rectangle((26 + i * 2.8, ROW + 2), 2.2, 6, facecolor=GPU_C,
                               edgecolor="none", zorder=4))
    ax.text(36.5, ROW - 5.5, "이 8개만 inference 가능", ha="center", fontsize=8.5, color=MUTE)

    box(ax, 58, ROW, 19, 13, CPU_C, "CPU tier", "크기 = r × GPU풀", fs=10)
    box(ax, 84, ROW, 15, 13, WAIT_C, "Waiting", "KV 폐기", fs=10)

    arrow(ax, (17.5, ROW + 6.5), (23.5, ROW + 6.5), MUTE)
    arrow(ax, (49.5, ROW + 9.5), (57.5, ROW + 9.5), BAD)
    arrow(ax, (57.5, ROW + 3.5), (49.5, ROW + 3.5), GPU_C)
    ax.text(53.5, ROW + 15.2, "demote", ha="center", fontsize=8, color=BAD, fontweight="bold")
    ax.text(53.5, ROW - 2.4, "promote", ha="center", fontsize=8, color=GPU_C, fontweight="bold")
    arrow(ax, (77.5, ROW + 6.5), (83.5, ROW + 6.5), BAD)
    ax.text(80.5, ROW + 15.2, "가득 차면", ha="center", fontsize=7.5, color=BAD)

    # ② — GPU⇄CPU 회전 자체
    ax.text(53.5, ROW + 20.5, "②", fontsize=13, fontweight="bold", color=BAD, ha="center")

    # ① — Waiting → full recompute (아래로 크게 우회)
    ax.add_patch(FancyArrowPatch((91, ROW - 1.5), (30, ROW - 9), arrowstyle="-|>",
                                 mutation_scale=14, color=BAD, lw=2.2, linestyle="--",
                                 connectionstyle="arc3,rad=-0.30", zorder=1))
    ax.text(92, ROW - 8, "①", fontsize=13, fontweight="bold", color=BAD, ha="center")

    ax.text(36.5, 26, "①  CPU tier 용량 부족  →  KV 폐기 → full recompute",
            ha="center", fontsize=9, color=BAD, fontweight="bold")
    ax.text(36.5, 15, "②  GPU 슬롯 경쟁  →  ping-pong · cache 붕괴 · pause",
            ha="center", fontsize=9, color=BAD, fontweight="bold")

    # ================= 우: r을 올리면 무엇이 변하나 =================
    ax = axes[1]; ax.set_xlim(0, 100); ax.set_ylim(0, 78); ax.axis("off")
    ax.text(0, 74, "r을 올리면 — CPU 상자만 커진다", fontsize=11, fontweight="bold", color=INK)
    for r, yy in ((2, 50), (4, 24)):
        ax.text(0, yy + 6, f"r = {r}", fontsize=10, fontweight="bold", color=INK)
        ax.add_patch(FancyBboxPatch((13, yy), 25, 11, boxstyle="round,pad=0.3",
                                    facecolor="white", edgecolor=GPU_C, linewidth=2, zorder=3))
        for k in range(8):
            ax.add_patch(Rectangle((15 + k * 2.8, yy + 3), 2.2, 5, facecolor=GPU_C,
                                   edgecolor="none", zorder=4))
        ax.text(25.5, yy + 9.4, "fit = 8칸", ha="center", fontsize=8,
                color=GPU_C, fontweight="bold")
        w = 10.5 * r
        ax.add_patch(FancyBboxPatch((44, yy), w, 11, boxstyle="round,pad=0.3",
                                    facecolor=CPU_C, edgecolor="none", zorder=3))
        ax.text(44 + w / 2, yy + 5.5, f"CPU tier {r}×", ha="center", va="center",
                color="white", fontsize=9, fontweight="bold", zorder=4)
    arrow(ax, (55, 47), (55, 38), CPU_C, lw=2.2)
    ax.text(57, 41, "커짐", fontsize=8.5, color=CPU_C, fontweight="bold")
    arrow(ax, (25.5, 47), (25.5, 38), GPU_C, lw=2.2, ls=":")
    ax.text(27.5, 41, "그대로", fontsize=8.5, color=GPU_C, fontweight="bold")
    ax.text(0, 8, "→ ①은 r로 고쳐진다.  ②는 r로 못 고친다.", fontsize=9.5,
            color=INK, fontweight="bold")
    ax.text(0, 2.5, "   ②를 고치려면 HBM↑ → GPU풀↑ → fit↑  (= H200)", fontsize=9.5,
            color=BAD, fontweight="bold")

    os.makedirs(FIG, exist_ok=True)
    p = os.path.join(FIG, "mori_phase2_two_causes_yunuikang.png")
    fig.savefig(p, dpi=200, bbox_inches="tight", facecolor="white")
    print("wrote", p)


if __name__ == "__main__":
    main()
