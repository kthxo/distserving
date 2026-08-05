#!/usr/bin/env python3
"""Phase 2 개념도 — fit / oversub / r 과 "용량 vs 워크셋" 을 한 장으로.

왼쪽: 개념 정의 (GPU 슬롯 fit, 초과분 oversub, CPU tier r)
오른쪽: (C, r) 조합별 용량 스택 vs 워크셋 — 수용률이 100%를 넘는지가 판정선
수치는 전부 [측정] 또는 [측정]에서 유도.
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

plt.rcParams["font.family"] = "Noto Sans CJK KR"
plt.rcParams["axes.unicode_minus"] = False

POOL, CTX = 262144, 32376          # [측정] --max-total-tokens / Track M ctx median
FIT = POOL / CTX                   # 8.10
EFF = 0.73                         # [측정] C32에서 실제 상주 / 명목 = 758,905 / 1,036,032

GPU_C, CPU_C, OVER = "#2E5EAA", "#1E7D4F", "#C0392B"
INK, MUTE, GRID = "#1A1A2E", "#6B6B7B", "#DDE1E8"
WIN, LOSE = "#E7F3EC", "#FBE9E7"
FIG = "/home/yunuikang/yunuikang_work/distserving/figures"


def main():
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 3.5),
                             gridspec_kw={"width_ratios": [1.0, 1.55]})

    # ---------------- 좌: 개념 ----------------
    ax = axes[0]; ax.set_xlim(0, 100); ax.set_ylim(0, 104); ax.axis("off")
    ax.text(0, 95, "세 개념", fontsize=12, fontweight="bold", color=INK)

    # GPU 슬롯 (fit개)
    ax.text(0, 84, f"fit = GPU풀 ÷ 컨텍스트 = {POOL:,} ÷ {CTX:,} = {FIT:.2f}",
            fontsize=9.5, color=INK)
    ax.text(0, 77, "→ GPU에 동시에 올릴 수 있는 프로그램 수", fontsize=8.5, color=MUTE)
    for i in range(8):
        ax.add_patch(Rectangle((i * 8.6, 62), 7.6, 9, facecolor=GPU_C, edgecolor="none"))
    ax.add_patch(Rectangle((8 * 8.6, 62), 7.6 * 0.1, 9, facecolor=GPU_C, edgecolor="none"))
    ax.text(72, 65.5, "≈ 8.1칸", fontsize=8.5, color=GPU_C, fontweight="bold")

    # oversub
    ax.text(0, 52, f"oversub = C ÷ fit", fontsize=9.5, color=INK)
    ax.text(0, 45, "→ 자리보다 몇 배 많은 프로그램이 들어오나", fontsize=8.5, color=MUTE)
    ax.text(0, 37, f"C=32 → {32/FIT:.2f}×      C=50 → {50/FIT:.2f}×",
            fontsize=9.5, color=OVER, fontweight="bold")

    # r
    ax.text(0, 27, "r = CPU tier 배수  (CPU tier = r × GPU풀)", fontsize=9.5, color=INK)
    ax.text(0, 20, "→ GPU에서 밀린 KV를 몇 칸이나 받아두나", fontsize=8.5, color=MUTE)
    ax.text(0, 11, "수용률 = (1+r)×fit ÷ C        (100% 미만이면 Waiting으로 넘침)",
            fontsize=9.5, color=INK, fontweight="bold")
    ax.text(0, 3, f"명목 워크셋은 실제보다 크다 — 실측 보정계수 {EFF} [측정, C32]",
            fontsize=8.5, color=MUTE, style="italic")

    # ---------------- 우: 용량 스택 vs 워크셋 ----------------
    ax = axes[1]
    combos = [("C=32, r=2\n(원래 격자)", 32, 2), ("C=50, r=2", 50, 2),
              ("C=50, r=3", 50, 3), ("C=50, r=4", 50, 4)]
    y = list(range(len(combos)))[::-1]
    for (lab, C, r), yy in zip(combos, y):
        eff_ws = EFF * C * CTX
        gpu, cpu = POOL, r * POOL
        cov = (gpu + cpu) / eff_ws
        ax.barh(yy, gpu / 1e6, 0.52, color=GPU_C, zorder=3)
        ax.barh(yy, cpu / 1e6, 0.52, left=gpu / 1e6, color=CPU_C, zorder=3,
                edgecolor="white", linewidth=1.6)
        ax.plot([eff_ws / 1e6, eff_ws / 1e6], [yy - 0.33, yy + 0.33],
                color=OVER, lw=2.6, zorder=5)
        col = "#1E7D4F" if cov >= 1 else OVER
        ax.text((gpu + cpu) / 1e6 + 0.04, yy, f"수용률  {cov:.0%}",
                va="center", fontsize=9.5, color=col, fontweight="bold")
        ax.text(-0.06, yy, lab, va="center", ha="right", fontsize=8.8, color=INK)
    ax.axvspan(0, 0, color=WIN)
    ax.set_yticks([]); ax.set_ylim(-0.7, len(combos) - 0.3)
    ax.set_xlim(0, 1.52)
    ax.set_xlabel("토큰 (백만)", color=MUTE, fontsize=9.5)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTE, labelsize=9)
    ax.grid(axis="x", color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    from matplotlib.lines import Line2D
    ax.legend(handles=[
        Rectangle((0, 0), 1, 1, fc=GPU_C, label="GPU 풀 (262,144 tok)"),
        Rectangle((0, 0), 1, 1, fc=CPU_C, label="CPU tier = r × GPU 풀"),
        Line2D([0], [0], color=OVER, lw=2.6, label="실효 워크셋 (0.73 × C × ctx)"),
    ], frameon=False, fontsize=8.2, loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=3)
    ax.set_title("용량(GPU+CPU) 이 워크셋을 담는가 — 100% 넘으면 Waiting 안 넘침",
                 color=INK, fontsize=10.5, fontweight="bold", pad=30)

    os.makedirs(FIG, exist_ok=True)
    p = os.path.join(FIG, "mori_phase2_concept_yunuikang.png")
    fig.savefig(p, dpi=200, bbox_inches="tight", facecolor="white")
    print("wrote", p)
    for lab, C, r in combos:
        eff = EFF * C * CTX
        print(f"  {lab.split(chr(10))[0]:14} 실효워크셋 {eff:>10,.0f}  용량 {(1+r)*POOL:>10,}  수용률 {(1+r)*POOL/eff:.1%}")


if __name__ == "__main__":
    main()
