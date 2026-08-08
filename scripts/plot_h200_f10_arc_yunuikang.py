#!/usr/bin/env python3
"""F10 — 전체 서사 타임라인: 6단계로 원인을 좁혀 왔다.

개념 그림(DECK_STYLE §5). 코드 가설(1~3) → 자원 가설(4~5) → 재현(6).
6은 다른 축의 질문이라 5의 실패와 모순되지 않는다는 점을 색으로 구분한다.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plot_h200_lib_yunuikang import save, INK, MUTE, BAD, OK  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

STEPS = [
    ("A 계층", "코드가 논문대로\n결정하는가", "17/17 PASS", OK, "코드"),
    ("B 계층", "실 GPU 에서\n실제로 도는가", "KV −6,258 tok\n일치", OK, "코드"),
    ("STEP 7", "바쁜 GPU 가\n유용한 일을 하는가", "goodput = thr 의 3%\n→ 아니오", BAD, "코드"),
    ("5090 Phase 2", "원인이\nCPU 용량(DRAM)인가", "r 2→4 인데\n1.05→0.66×  → 아니오", BAD, "자원"),
    ("H200 Phase 1", "원인이\nGPU 슬롯(fit)인가", "붕괴 미재현\n1.405 · 1.080  → 아니오", BAD, "자원"),
    ("H200 Phase 2", "논문 곡선이\n재현되는가", "부분 재현 2/4\nC80 +14.2%", OK, "재현"),
]
BAND = {"코드": "#EDEDF2", "자원": "#FFF3E6", "재현": "#E7F3EC"}


def main():
    fig, ax = plt.subplots(figsize=(13.0, 4.1))
    ax.set_xlim(0, 100); ax.set_ylim(0, 60); ax.axis("off")

    ax.text(0, 56.5, "여섯 단계로 원인을 좁혀 왔다 — 코드 가설을 닫고, 자원 가설을 소진하고, 현상을 확보했다",
            fontsize=12, color=INK, fontweight="bold")

    # 그룹 배경 밴드
    for lab, x0, x1, key in (("코드 가설을 닫았다", 0.5, 49.5, "코드"),
                             ("자원 가설을 소진했다", 50.5, 82.5, "자원"),
                             ("현상을 확보했다", 83.5, 99.5, "재현")):
        ax.add_patch(FancyBboxPatch((x0, 6), x1 - x0, 40, boxstyle="round,pad=0.4",
                                    facecolor=BAND[key], edgecolor="none", zorder=1))
        ax.text((x0 + x1) / 2, 8.5, lab, ha="center", fontsize=9.5,
                color=MUTE, fontweight="bold", zorder=2)

    W, GAP = 14.6, 1.9
    x = 1.6
    for i, (name, q, res, col, _) in enumerate(STEPS):
        ax.add_patch(FancyBboxPatch((x, 14), W, 29, boxstyle="round,pad=0.4",
                                    facecolor="white", edgecolor=col, linewidth=1.8, zorder=3))
        ax.text(x + W / 2, 39.5, f"{i+1}. {name}", ha="center", va="center",
                fontsize=10, color=col, fontweight="bold", zorder=4)
        ax.text(x + W / 2, 31.5, q, ha="center", va="center", fontsize=8.6,
                color=MUTE, zorder=4)
        ax.text(x + W / 2, 21.0, res, ha="center", va="center", fontsize=8.8,
                color=INK, fontweight="bold", zorder=4)
        if i < len(STEPS) - 1:
            ax.text(x + W + GAP / 2, 28.5, "→", ha="center", va="center",
                    fontsize=15, color=MUTE, zorder=4)
        x += W + GAP

    ax.text(0, 2.0,
            "5 없이 6만 하면 곡선이 나와도 왜 나왔는지 모르고, 6 없이 5만 하면 원인은 알아도 “재현했다”고 말할 수 없다 "
            "— 둘을 합쳐야 “왜 그런지 아는 재현”이 된다   [추론]",
            fontsize=9, color=INK, fontweight="bold")
    save(fig, "mori_h200_f10_arc_yunuikang")


if __name__ == "__main__":
    main()
