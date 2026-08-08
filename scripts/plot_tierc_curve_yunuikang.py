#!/usr/bin/env python3
"""Tier C 3점 곡선 그림 — C20/C40/C80 × (MORI, TA+O).

`analyze_tierc_yunuikang.py` 의 plot() 은 2셀 전용이라 6셀에서 x 라벨이
"MORI MORI MORI TAO TAO TAO" 로 뭉개진다. 원본은 건드리지 않고 새 파일로 만든다.

색은 기존 산출물과 동일 팔레트를 재사용(프로젝트 일관성). dataviz 검증기 결과:
데이터 3색(#1E7D4F/#2E5EAA/#C0392B) 전 항목 PASS, 시스템 2색도 전 항목 PASS.
idle 은 '잔여' 중립 회색이라 categorical 슬롯이 아니며, 대비 부족분은 각 조각의
직접 라벨 + 로그의 표(view) 로 보완한다.
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import Patch

HERE = os.path.dirname(os.path.abspath(__file__))
_TTF = os.path.join(HERE, "NanumGothic_yunuikang.ttf")
if os.path.exists(_TTF):
    fm.fontManager.addfont(_TTF)
    plt.rcParams["font.family"] = fm.FontProperties(fname=_TTF).get_name()
plt.rcParams["axes.unicode_minus"] = False

PART = [("decode_ms", "#1E7D4F", "decode (생성)"),
        ("prefill_new_ms", "#2E5EAA", "prefill - 새 컨텍스트"),
        ("prefill_recompute_ms", "#C0392B", "prefill - 재계산"),
        ("idle_ms", "#C9CDD6", "idle (GPU 유휴)")]
SYS = {"MORI": "#C0392B", "TAO": "#2E5EAA"}
INK, MUTE, GRID = "#1A1A2E", "#6B6B7B", "#DDE1E8"
CS = [(20, 1.0), (40, 2.0), (80, 4.0)]


def style(ax, ylab=None, title=None):
    ax.set_facecolor("white")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTE, labelsize=9.5, length=0)
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    if ylab:
        ax.set_ylabel(ylab, color=MUTE, fontsize=10)
    if title:
        ax.set_title(title, color=INK, fontsize=11.5, fontweight="bold", pad=10)


def main(summary, out):
    S = {c["tag"]: c for c in json.load(open(summary))}
    fig, axes = plt.subplots(1, 3, figsize=(16.4, 5.5), facecolor="white",
                             gridspec_kw={"width_ratios": [1.55, 1, 1]})

    # ── A: 가산 예산 스택 (6셀, C 로 묶음)
    ax = axes[0]
    xs, labs = [], []
    for gi, (C, ov) in enumerate(CS):
        for si, sysn in enumerate(("MORI", "TAO")):
            x = gi * 2.7 + si * 1.0
            c = S[f"{sysn}_C{C}"]
            w = c["wall_ms"]
            bot = 0.0
            for key, col, _ in PART:
                v = (c[key] or 0.0) / w * 100.0
                # 2px 표면 간격: 조각마다 아주 얇게 띄운다
                ax.bar(x, v - 0.18, 0.86, bottom=bot + 0.09, color=col,
                       edgecolor="white", linewidth=0.8)
                if v >= 4.0:                       # 직접 라벨(부차 부호화)
                    ax.text(x, bot + v / 2, f"{v:.1f}", ha="center", va="center",
                            fontsize=8.8, color="white", fontweight="bold")
                bot += v
            xs.append(x)
            labs.append("MORI" if sysn == "MORI" else "TA+O")
        ax.text(gi * 2.7 + 0.5, -7.4, f"C={C}\noversub {ov:.1f}x",
                ha="center", va="top", fontsize=10, color=INK, fontweight="bold")
    ax.set_xticks(xs)
    ax.set_xticklabels(labs, fontsize=9.5)
    ax.set_ylim(0, 104)
    style(ax, "window wall 중 비중 (%)", "GPU 시간 분해 - 가산 예산 (합 = 100%)")
    # 범례는 축 **아래** — 위쪽은 제목이 쓰고, 축 안쪽에 두면 C20 막대를 덮는다.
    # (위에 두고 pad 를 키우는 방식은 제목과 겹쳐서 버렸다.)
    ax.legend(handles=[Patch(facecolor=c, label=l) for _, c, l in PART],
              frameon=False, fontsize=8.8, loc="upper center",
              bbox_to_anchor=(0.5, -0.175), ncol=2, handlelength=1.5,
              columnspacing=1.6, handletextpad=0.6)

    # ── B: 재계산 몫 vs 압박
    ax = axes[1]
    for sysn, lab in (("MORI", "MORI"), ("TAO", "TA+O")):
        y = [S[f"{sysn}_C{C}"]["prefill_recompute_ms"] / S[f"{sysn}_C{C}"]["wall_ms"] * 100
             for C, _ in CS]
        ax.plot([o for _, o in CS], y, "-o", lw=2, ms=9, color=SYS[sysn], label=lab)
        dy = 12 if sysn == "MORI" else -20        # 위/아래로 갈라 라벨 충돌 제거
        for (_, o), v in zip(CS, y):
            ax.annotate(f"{v:.1f}%", (o, v), textcoords="offset points",
                        xytext=(0, dy), ha="center", fontsize=9, color=SYS[sysn],
                        fontweight="bold")
    ax.set_xticks([o for _, o in CS])
    ax.set_xticklabels([f"{o:.0f}x\n(C={C})" for C, o in CS], fontsize=9.5)
    ax.set_xlabel("oversubscription", color=MUTE, fontsize=10)
    ax.set_ylim(-2.6, 20)
    style(ax, "재계산이 먹은 GPU 시간 (%)", "재계산은 압박이 만든다\n(MORI 가 항상 더 많다)")
    ax.legend(frameon=False, fontsize=9.5, loc="upper left")

    # ── C: reload 강도
    ax = axes[2]
    for sysn, lab in (("MORI", "MORI"), ("TAO", "TA+O")):
        y = [S[f"{sysn}_C{C}"]["reload_tok"] / S[f"{sysn}_C{C}"]["out_tok_window"]
             for C, _ in CS]
        ax.plot([o for _, o in CS], y, "-o", lw=2, ms=9, color=SYS[sysn], label=lab)
        dy = 12 if sysn == "MORI" else -20
        for (_, o), v in zip(CS, y):
            ax.annotate(f"{v:.1f}", (o, v), textcoords="offset points",
                        xytext=(0, dy), ha="center", fontsize=9, color=SYS[sysn],
                        fontweight="bold")
    ax.set_xticks([o for _, o in CS])
    ax.set_xticklabels([f"{o:.0f}x\n(C={C})" for C, o in CS], fontsize=9.5)
    ax.set_xlabel("oversubscription", color=MUTE, fontsize=10)
    ax.set_ylim(0, 26)
    style(ax, "reload 토큰 / 출력 토큰", "MORI 는 reload 를 3~4배 한다\n- 그런데 재계산은 안 줄었다")
    ax.legend(frameon=False, fontsize=9.5, loc="upper left")

    fig.suptitle("Tier C - MORI vs TA+O GPU 시간 예산 (H200 | fit 20 | r=2 | 셀 1500s)",
                 fontsize=12.5, fontweight="bold", color=INK, y=1.005)
    fig.tight_layout()
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    fig.savefig(out, dpi=190, bbox_inches="tight", facecolor="white")
    print(f"[plot] {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "scratch/mori/tierc_h200/tierc_summary.json",
         sys.argv[2] if len(sys.argv) > 2 else "figures/mori_tierc_curve_yunuikang.png")
