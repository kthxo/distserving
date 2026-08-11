#!/usr/bin/env python3
"""5090 TP1 결과 전용 그림 — 측정값만 표시한다.

★ 제목·주석에 해석/판정 언어를 넣지 않는다. 축·단위·수치만.
R1  GPU 시간 예산 스택 (8셀)
R2  절대 지표 vs C (goodput@5s · 엔진 decode 토큰 · 드라이버 thr), MORI/TA+O
R3  MORI ÷ TA+O 비 vs C  (+ 참고 데이터 1개 수평선)
R4  토큰 지표 vs C (재계산율 · reload/출력토큰 · prefix hit)
R5  계측 정의 다이어그램 (개념도)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plot_h200_lib_yunuikang import style, save, INK, MUTE, GRID  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch  # noqa: E402

D = "/home/yunuikang/yunuikang_work/scratch/mori/tierc_5090tp1"
CS = [7, 15, 20, 70]
MORI_C, TAO_C = "#C0392B", "#2E5EAA"
PART = [("decode_pct", "decode", "#1E7D4F"),
        ("prefill_new_pct", "prefill_new", "#2E5EAA"),
        ("prefill_recomp_pct", "prefill_recompute", "#C0392B"),
        ("idle_pct", "idle", "#C9CDD6")]
DD = json.load(open(f"{D}/deck_numbers_5090.json"))
C_ = DD["cells"]
R_ = DD["ratio"]
g = lambda s, c, k: C_[f"{s}_C{c}"][k]


def r1_budget():
    fig, ax = plt.subplots(figsize=(10.6, 4.3))
    xs, w = [], 0.38
    for i in range(len(CS)):
        xs += [i - w / 2, i + w / 2]
    bottoms = [0.0] * len(xs)
    for key, name, col in PART:
        vals = [g(s, C, key) for C in CS for s in ("MORI", "TAO")]
        ax.bar(xs, vals, w, bottom=bottoms, color=col, edgecolor="white", lw=1.1, label=name)
        for x, v, b in zip(xs, vals, bottoms):
            if v >= 5:
                ax.text(x, b + v / 2, f"{v:.1f}", ha="center", va="center", fontsize=8.5,
                        color="white" if col != "#C9CDD6" else INK, fontweight="bold")
        bottoms = [b + v for b, v in zip(bottoms, vals)]
    for i, C in enumerate(CS):
        for k, s in enumerate(("MORI", "TA+O")):
            ax.text(i + (k - 0.5) * w, -4.2, s, ha="center", fontsize=8.5,
                    color=MORI_C if k == 0 else TAO_C, fontweight="bold")
            xf = g("MORI" if k == 0 else "TAO", C, "transfer_pct")
            ax.text(i + (k - 0.5) * w, 101.5, f"xfer {xf:.2f}", ha="center", fontsize=7.5,
                    color=MUTE)
    ax.set_xticks(range(len(CS)))
    ax.set_xticklabels([f"C={C}\noversub {C/7:.2f}×" for C in CS], fontsize=9.5)
    ax.set_ylim(-7, 110)
    style(ax, ylab="창 wall 대비 비중 (%)",
          title="GPU 시간 예산 — decode / prefill_new / prefill_recompute / idle (합 = 100%)")
    ax.legend(frameon=False, fontsize=8.5, loc="lower center", ncol=4, columnspacing=1.2,
              handlelength=1.2, bbox_to_anchor=(0.5, -0.30))
    ax.text(0.5, -0.44, "막대 위 숫자 = transfer(reload+offload) 비중 (%), 가산 예산에 미포함",
            transform=ax.transAxes, fontsize=8.5, color=MUTE, ha="center")
    save(fig, "tierc5090_R1_budget_yunuikang")


def r2_absolute():
    fig, axes = plt.subplots(1, 3, figsize=(12.8, 3.5))
    specs = [("goodput5", "goodput @SLO 5s (tok/s)", "goodput @SLO 5s", "{:.2f}"),
             ("decode_tok", "엔진 decode 토큰 (창 내)", "엔진 decode 토큰", "{:,.0f}"),
             ("drv_thr", "드라이버 throughput (tok/s)", "드라이버 throughput", "{:.2f}")]
    for ax, (k, ylab, title, fmt) in zip(axes, specs):
        for s, col, lab in (("MORI", MORI_C, "MORI"), ("TAO", TAO_C, "TA+O")):
            ys = [g(s, C, k) for C in CS]
            ax.plot(range(len(CS)), ys, "-o", color=col, lw=2.2, ms=8,
                    markeredgecolor="white", markeredgewidth=1.2, label=lab)
            for i, v in enumerate(ys):
                up = v >= g("TAO" if s == "MORI" else "MORI", CS[i], k)
                ax.annotate(fmt.format(v), (i, v), textcoords="offset points",
                            xytext=(0, 10 if up else -16), ha="center", fontsize=8.5,
                            color=col, fontweight="bold")
        ax.set_xticks(range(len(CS)))
        ax.set_xticklabels([f"C={C}" for C in CS], fontsize=9)
        style(ax, ylab=ylab, title=title)
        ax.margins(y=0.22)
        ax.legend(frameon=False, fontsize=8.5, loc="best")
    fig.suptitle("절대값 — 5090 ×1 · TP1 · fit 7.00 · r=2 · 셀 25분 · n=1   [측정]",
                 fontsize=9.5, color=MUTE, y=1.04)
    save(fig, "tierc5090_R2_absolute_yunuikang")


def r3_ratio():
    fig, ax = plt.subplots(figsize=(7.8, 4.2))
    specs = [("goodput5", "goodput @5s", MORI_C, "-o", 2.6, 9),
             ("decode_tok", "엔진 decode 토큰", MUTE, "--s", 1.7, 6),
             ("drv_thr", "드라이버 throughput", "#B87A1E", ":^", 1.5, 6)]
    for k, name, col, mk, lw, ms in specs:
        ys = [R_[str(C)][k] for C in CS]
        ax.plot(range(len(CS)), ys, mk, color=col, lw=lw, ms=ms,
                markeredgecolor="white", markeredgewidth=1.2, label=name)
        if k == "goodput5":
            for i, v in enumerate(ys):
                ax.annotate(f"{v:.3f}", (i, v), textcoords="offset points", xytext=(0, 11),
                            ha="center", fontsize=9.5, color=INK, fontweight="bold")
    ax.axhline(1.0, color=INK, lw=1.5, ls="--")
    ref = DD["ref"]["orig5090_tp2_8b_C80_ratio_drv"]
    ax.axhline(ref, color="#4A4A63", lw=1.6, ls="-.")
    ax.text(len(CS) - 1 + 0.05, ref + 0.04,
            f"참고 데이터 {ref:.2f} — 5090 ×2 · TP2 · Qwen3-8B · C80 (드라이버 thr 비)",
            fontsize=8, color="#4A4A63", ha="right")
    ax.set_xticks(range(len(CS)))
    ax.set_xticklabels([f"C={C}\noversub {C/7:.2f}×" for C in CS], fontsize=9)
    ax.set_ylim(0.3, 2.25)
    ax.text(-0.42, 1.02, "1.0", fontsize=8.5, color=MUTE)
    style(ax, ylab="MORI ÷ TA+O", title="비 (MORI ÷ TA+O)")
    ax.legend(frameon=False, fontsize=8.5, loc="upper left")
    save(fig, "tierc5090_R3_ratio_yunuikang")


def r4_tokens():
    fig, axes = plt.subplots(1, 3, figsize=(12.8, 3.5))
    specs = [("recompute_frac", "재계산율 (recompute ÷ computed)", "{:.1%}", 100),
             ("reload_per_out", "reload 토큰 ÷ 출력 토큰", "{:.2f}", 1),
             ("prefix_hit", "prefix cache hit rate", "{:.3f}", 1)]
    for ax, (k, title, fmt, scale) in zip(axes, specs):
        for s, col, lab in (("MORI", MORI_C, "MORI"), ("TAO", TAO_C, "TA+O")):
            ys = [g(s, C, k) * (100 if scale == 100 else 1) for C in CS]
            ax.plot(range(len(CS)), ys, "-o", color=col, lw=2.2, ms=8,
                    markeredgecolor="white", markeredgewidth=1.2, label=lab)
            for i, v in enumerate(ys):
                raw = g(s, CS[i], k)
                up = raw >= g("TAO" if s == "MORI" else "MORI", CS[i], k)
                ax.annotate(fmt.format(raw), (i, v), textcoords="offset points",
                            xytext=(0, 10 if up else -16), ha="center", fontsize=8.5,
                            color=col, fontweight="bold")
        ax.set_xticks(range(len(CS)))
        ax.set_xticklabels([f"C={C}" for C in CS], fontsize=9)
        style(ax, ylab=("%" if scale == 100 else ""), title=title)
        ax.margins(y=0.22)
        ax.legend(frameon=False, fontsize=8.5, loc="best")
    fig.suptitle("토큰 지표 — 창 내 집계   [측정]", fontsize=9.5, color=MUTE, y=1.04)
    save(fig, "tierc5090_R4_tokens_yunuikang")


def r5_method():
    fig, ax = plt.subplots(figsize=(12.6, 5.0))
    ax.set_xlim(0, 100); ax.set_ylim(0, 70); ax.axis("off")
    ax.text(0, 66, "계측 정의", fontsize=12.5, color=INK, fontweight="bold")

    # 가산 예산 막대
    ax.text(0, 58, "GPU 가산 예산  (합 = 창 wall)", fontsize=10, color=INK, fontweight="bold")
    segs = [("decode", 26, "#1E7D4F"), ("prefill_new", 20, "#2E5EAA"),
            ("prefill_recompute", 22, "#C0392B"), ("idle", 20, "#C9CDD6")]
    x = 0
    for name, wdt, col in segs:
        ax.add_patch(FancyBboxPatch((x, 47), wdt, 8, boxstyle="round,pad=0.25",
                                    facecolor=col, edgecolor="white", linewidth=1.4))
        ax.text(x + wdt / 2, 51, name, ha="center", va="center", fontsize=9,
                color="white" if col != "#C9CDD6" else INK, fontweight="bold")
        x += wdt
    ax.annotate("", xy=(88, 44), xytext=(0, 44),
                arrowprops=dict(arrowstyle="<->", color=MUTE, lw=1.3))
    ax.text(44, 41.2, "창 wall = [t_start + 0.2×DUR, t_start + DUR]", ha="center",
            fontsize=8.5, color=MUTE)

    # transfer 별도 스트림
    ax.add_patch(FancyBboxPatch((0, 31), 40, 7, boxstyle="round,pad=0.25",
                                facecolor="#F4F6FA", edgecolor="#DDE1E8", linewidth=1.2))
    ax.text(20, 34.5, "transfer = reload + offload  (별도 스트림, 예산에 미포함)",
            ha="center", va="center", fontsize=9, color=INK)

    # 정의 목록
    defs = [
        "decode / prefill  —  forward_batch_generation 을 CUDA event 로 브래킷, forward_mode 로 분류",
        "transfer  —  HiCache start_writing / start_loading 을 각 전송 스트림 위에서 CUDA event",
        "prefill_new / prefill_recompute  —  Method B: recompute = computed − new_required,",
        "        new_required = Σ per-program 컨텍스트 증분 (prompt[i] − prompt[i−1] − completion[i−1])",
        "goodput@5s  —  Σ completion_tokens (pause_s + prefill_s ≤ 5s 인 스텝) ÷ 창 wall",
        "prefix hit  —  Δcached_tokens_total ÷ Δprompt_tokens_total (엔진 카운터)",
        "Waiting 축출  —  MORI: `MORI evict CPU→Waiting` · TA+O: `Paused program` (서로 다른 사건)",
    ]
    for i, t in enumerate(defs):
        ax.text(0, 25.0 - i * 3.6, t, fontsize=9, color=INK)
    save(fig, "tierc5090_R5_method_yunuikang")


if __name__ == "__main__":
    r1_budget(); r2_absolute(); r3_ratio(); r4_tokens(); r5_method()
