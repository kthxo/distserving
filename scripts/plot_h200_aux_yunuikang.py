#!/usr/bin/env python3
"""보조 그림 4종 — F2 · F5 · F8 · F9.

F2  하드웨어 교체 이득의 비대칭 (5090 → H200, 같은 8B)
F5  MORI ÷ TA+O vs C   (기준선 1.0 · 논문 하한 1.10)
F8  SMG 절벽            (goodput 로그축 + TTFT 별도 패널 — 이중축 금지)
F9  prefix hit vs goodput 산점 (직관 반전: hit 최저인 MORI 가 1등)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plot_h200_lib_yunuikang import (  # noqa: E402
    phase2, engine_delta, style, save, SYS_COLOR, SYS_LABEL, SYS_ORDER,
    INK, MUTE, BAD, OK, AMBER, WIN_BG, LOSE_BG)
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

CS = [20, 40, 80]
# 5090 앵커 [측정, H200_RESULTS §3.2]
A_TAO, A_MORI = 14.28, 6.47
H_TAO, H_MORI = 23.17, 25.03


def f2_asym():
    fig, ax = plt.subplots(figsize=(7.6, 4.0))
    xs, w = np.arange(2), 0.34
    for k, (name, a, h, col) in enumerate((("TA+O", A_TAO, H_TAO, SYS_COLOR["TAO"]),
                                           ("MORI", A_MORI, H_MORI, SYS_COLOR["MORI"]))):
        pos = xs + (k - 0.5) * w
        ax.bar(pos, [a, h], w, color=col, edgecolor="white", lw=1.4, label=SYS_LABEL.get(name, name))
        for xi, v in zip(pos, [a, h]):
            ax.annotate(f"{v:.2f}", (xi, v), textcoords="offset points", xytext=(0, 6),
                        ha="center", fontsize=10.5, fontweight="bold", color=INK)
        ax.annotate("", xy=(pos[1], h), xytext=(pos[0], a),
                    arrowprops=dict(arrowstyle="->", color=col, lw=1.8, alpha=0.6))
        # 배율 라벨은 두 그룹 사이 빈 구간(x≈0.52)에 둔다 — 막대와 겹치지 않게
        ax.text(0.52, 11.0 if k else 21.5, f"×{h/a:.2f}", ha="center",
                fontsize=13.5, color=col, fontweight="bold")
    ax.set_xticks(xs)
    ax.set_xticklabels(["5090 ×2 · TP2\nSYS · cross-NUMA", "H200 ×1 · TP1\nnode-local"], fontsize=9.5)
    ax.set_ylim(0, 31)
    style(ax, ylab="드라이버 throughput (tok/s)",
          title="하드웨어 교체 이득이 비대칭이다")
    ax.legend(frameon=False, fontsize=9.5, loc="upper left")
    ax.text(0.0, -0.22, "Qwen3-8B · fit 8.10 · oversub 9.88× · r=2 · 60분 — 모델·KV밀도·셀길이 모두 동일. "
                        "MORI 가 이득을 2.4배 크게 받았다   [측정]",
            transform=ax.transAxes, fontsize=8, color=MUTE)
    save(fig, "mori_h200_f2_asym_yunuikang")


def f5_ratio(P):
    g = lambda s, c: P[(s, c)]["goodput_5s"]
    fig, ax = plt.subplots(figsize=(7.6, 4.0))
    ys = [g("MORI", c) / g("TAO", c) for c in CS]
    ax.axhspan(1.10, 1.30, color=WIN_BG, zorder=0)
    ax.axhspan(0.90, 1.0, color=LOSE_BG, zorder=0)
    ax.plot(CS, ys, "-o", color=SYS_COLOR["MORI"], lw=2.8, ms=11,
            markeredgecolor="white", markeredgewidth=1.5, zorder=4)
    for c, v in zip(CS, ys):
        ax.annotate(f"{v:.3f}", (c, v), textcoords="offset points", xytext=(0, 13),
                    ha="center", fontsize=11.5, fontweight="bold", color=INK)
    ax.axhline(1.0, color=INK, lw=1.5, ls="--", zorder=3)
    ax.axhline(1.10, color=OK, lw=1.6, ls=":", zorder=3)
    ax.set_xticks(CS); ax.set_xticklabels([f"C={c}" for c in CS], fontsize=10)
    ax.set_ylim(0.95, 1.24); ax.set_xlim(12, 92)
    style(ax, ylab="MORI ÷ TA+O  (goodput @5s)", xlab="동시성 C",
          title="압박이 커질수록 MORI 우위가 커진다")
    ax.text(90, 1.115, "논문 하한 완화판 1.10", ha="right", fontsize=9, color=OK, fontweight="bold")
    ax.text(90, 1.012, "1.0 = 동률", ha="right", fontsize=9, color=MUTE)
    ax.text(90, 1.205, "P2 통과 (C=80)", ha="right", fontsize=10, color=OK, fontweight="bold")
    ax.text(0.0, -0.22, "P2 는 goodput 비 ≥1.10 **그리고** TTFT p50 −10% 이상을 요구 — "
            "goodput 은 통과, TTFT 에서 불성립(F6)   [측정]".replace("**", ""),
            transform=ax.transAxes, fontsize=8, color=MUTE)
    save(fig, "mori_h200_f5_ratio_yunuikang")


def f8_smg(P):
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 3.7))
    ax = axes[0]
    ys = [max(P[("SMG", c)]["goodput_5s"], 0.008) for c in CS]
    ax.bar([str(c) for c in CS], ys, 0.55, color=SYS_COLOR["SMG"], edgecolor="white", lw=1.4)
    ax.set_yscale("log"); ax.set_ylim(0.005, 600)
    for i, c in enumerate(CS):
        v = P[("SMG", c)]["goodput_5s"]
        ax.annotate(f"{v:.2f}", (i, max(v, 0.008)), textcoords="offset points",
                    xytext=(0, 6), ha="center", fontsize=11, fontweight="bold", color=INK)
    style(ax, ylab="goodput @5s (tok/s, 로그축)", xlab="동시성 C",
          title="A. 유용한 일이 0 으로 간다")
    ax.text(0.98, 0.97, "C80 의 0.00 은 로그축 표시상 하단 고정", transform=ax.transAxes,
            fontsize=7.5, color=MUTE, ha="right", va="top")

    ax = axes[1]
    ys = [P[("SMG", c)]["ttft_p50_s"] for c in CS]
    ax.bar([str(c) for c in CS], ys, 0.55, color=SYS_COLOR["SMG"], edgecolor="white", lw=1.4)
    for i, v in enumerate(ys):
        ax.annotate(f"{v:.2f} s", (i, v), textcoords="offset points", xytext=(0, 6),
                    ha="center", fontsize=11, fontweight="bold", color=INK)
    ax.axhline(5.0, color=BAD, lw=1.8, ls="--")
    ax.text(1.5, 8.5, "SLO 5 s", ha="center", fontsize=9.5, color=BAD, fontweight="bold")
    ax.set_ylim(0, 88)
    style(ax, ylab="TTFT p50 (s)", xlab="동시성 C", title="B. 왜냐하면 응답이 늦어서")
    fig.suptitle("SMG(admission control 없음) — oversub 가 1을 넘는 순간 붕괴   [측정]",
                 fontsize=10.5, color=INK, y=1.04, fontweight="bold")
    save(fig, "mori_h200_f8_smg_yunuikang")


def f9_hit(P):
    fig, ax = plt.subplots(figsize=(7.8, 4.2))
    # 계열마다 라벨 방향을 달리해 겹침을 피한다
    OFF = {"TA": (10, 7), "TAO": (10, -14), "MORI": (11, 5)}
    for s in SYS_ORDER:
        if s == "SMG":
            continue
        xs = [engine_delta(f"{s}_C{c}")["hit"] for c in CS]
        ys = [P[(s, c)]["goodput_5s"] for c in CS]
        ax.plot(xs, ys, "-o", color=SYS_COLOR[s], lw=1.6, ms=11, alpha=0.9,
                markeredgecolor="white", markeredgewidth=1.5, label=SYS_LABEL[s])
        for c, x, y in zip(CS, xs, ys):
            ax.annotate(f"C{c}", (x, y), textcoords="offset points", xytext=OFF[s],
                        fontsize=8.5, color=SYS_COLOR[s], fontweight="bold")
    ax.set_xlim(0.805, 0.962); ax.set_ylim(149, 219)
    style(ax, ylab="goodput @SLO 5s (tok/s)", xlab="prefix cache hit rate",
          title="캐시 적중률은 성능의 대리 지표가 아니다")
    ax.legend(frameon=False, fontsize=9.5, loc="upper right")
    ax.annotate("MORI: hit 이 가장 낮은데(0.827)\ngoodput 은 1등(210.02)",
                xy=(0.830, 208.5), xytext=(0.856, 199),
                fontsize=9.5, color=BAD, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=BAD, lw=1.4))
    ax.text(0.0, -0.20, "→ reload 가 recompute 보다 싸다는 전제의 직접 증거. "
                        "H200 Phase 2 · fit 20 · r=2   [측정→추론]",
            transform=ax.transAxes, fontsize=8, color=MUTE)
    save(fig, "mori_h200_f9_hit_yunuikang")


if __name__ == "__main__":
    P = phase2()
    f2_asym(); f5_ratio(P); f8_smg(P); f9_hit(P)
