#!/usr/bin/env python3
"""Tier C 결과-전용 덱 그림 (deck_numbers.json 만 읽는다).

만드는 것
  tierc_clock_diagram_yunuikang.png   GPU 시계 5분할 + 계측 지점 (개념 다이어그램)
  tierc_budget_deck_yunuikang.png     셀별 GPU 가산 예산 스택 (+ transfer 별도 막대)
  tierc_curve4_deck_yunuikang.png     3점 곡선 4패널
  tierc_derived_deck_yunuikang.png    goodput@5s · engine thr · TTFT p50/p95
  tierc_rank_deck_yunuikang.png       _type_rank 분포 + ι percentile
  tierc_5090_deck_yunuikang.png       5090 TP1 예산 스택 (있으면)
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import FancyArrowPatch, Patch, Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIGDIR = os.path.join(ROOT, "figures")
NUM = os.path.join(os.path.dirname(ROOT), "scratch", "mori", "tierc_h200",
                   "deck_numbers.json")

_TTF = os.path.join(HERE, "NanumGothic_yunuikang.ttf")
if os.path.exists(_TTF):
    fm.fontManager.addfont(_TTF)
    plt.rcParams["font.family"] = fm.FontProperties(fname=_TTF).get_name()
plt.rcParams["axes.unicode_minus"] = False

INK, MUTE, GRID = "#1A1A2E", "#6B6B7B", "#DDE1E8"
RED, BLUE, GREEN, AMBER, PURPLE = "#C0392B", "#2E5EAA", "#1E7D4F", "#B87A1E", "#6E4B9E"
SYSC = {"MORI": RED, "TA+O": BLUE}
PART = [("decode_pct", GREEN, "decode (생성)"),
        ("prefill_new_pct", BLUE, "prefill - 새 컨텍스트"),
        ("prefill_recompute_pct", RED, "prefill - 재계산"),
        ("idle_pct", "#C9CDD6", "idle (GPU 유휴)")]


def style(ax, ylab=None, title=None, xlab=None):
    ax.set_facecolor("white")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTE, labelsize=10, length=0)
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    if ylab:
        ax.set_ylabel(ylab, color=MUTE, fontsize=11)
    if xlab:
        ax.set_xlabel(xlab, color=MUTE, fontsize=11)
    if title:
        ax.set_title(title, color=INK, fontsize=13, fontweight="bold", pad=10)


def save(fig, name):
    p = os.path.join(FIGDIR, name)
    fig.savefig(p, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("[fig]", p)


# ─────────────────────────────────────────── 1. GPU 시계 다이어그램
def fig_clock():
    fig, ax = plt.subplots(figsize=(13.0, 5.6), facecolor="white")
    ax.set_xlim(0, 100); ax.set_ylim(0, 62); ax.axis("off")

    ax.text(0, 58.5, "계측 창 wall (셀 1,254 s) = 100 %", fontsize=13,
            color=INK, fontweight="bold")

    segs = [("decode", 46, GREEN), ("prefill - 새", 24, BLUE),
            ("prefill - 재계산", 22, RED), ("idle", 8, "#C9CDD6")]
    x = 0.0
    for lab, w, col in segs:
        ax.add_patch(Rectangle((x, 44), w - 0.4, 8.5, facecolor=col,
                               edgecolor="white", lw=1.4))
        ax.text(x + (w - 0.4) / 2, 48.2, lab, ha="center", va="center",
                fontsize=11.5, color="white" if col != "#C9CDD6" else INK,
                fontweight="bold")
        x += w
    ax.annotate("", xy=(0, 41.5), xytext=(99.6, 41.5),
                arrowprops=dict(arrowstyle="<->", color=MUTE, lw=1.1))
    ax.text(50, 39.0, "네 조각의 합 = wall  (가산 예산)", ha="center",
            fontsize=11, color=MUTE)

    # transfer - 별도 스트림, 예산에 더하지 않음
    ax.add_patch(Rectangle((0, 30), 30, 6.2, facecolor=PURPLE, alpha=0.85,
                           edgecolor="white", lw=1.4))
    ax.text(15, 33.1, "transfer  (reload / offload)", ha="center", va="center",
            fontsize=11.5, color="white", fontweight="bold")
    ax.text(31.5, 33.1, "별도 CUDA 스트림 - 위 예산에 더하지 않는다 (병기만)",
            va="center", fontsize=11, color=PURPLE)

    # 계측 지점
    ax.add_patch(Rectangle((0, 14), 47, 11.5, facecolor="#F4F6FA",
                           edgecolor="#DDE1E8", lw=1.0))
    ax.text(1.5, 22.6, "계측 지점 (1)  forward_batch_generation", fontsize=11.5,
            color=INK, fontweight="bold")
    ax.text(1.5, 19.4, "CUDA event start/end 로 커널 시간 측정", fontsize=10.5, color=MUTE)
    ax.text(1.5, 16.5, "-> decode_ms / prefill_ms / step 별 토큰 수", fontsize=10.5, color=MUTE)

    ax.add_patch(Rectangle((52, 14), 47, 11.5, facecolor="#F4F6FA",
                           edgecolor="#DDE1E8", lw=1.0))
    ax.text(53.5, 22.6, "계측 지점 (2)  HiCache load / store", fontsize=11.5,
            color=INK, fontweight="bold")
    ax.text(53.5, 19.4, "CUDA event start/end (전송 스트림)", fontsize=10.5, color=MUTE)
    ax.text(53.5, 16.5, "-> xfer_reload_ms / xfer_offload_ms / 전송 토큰", fontsize=10.5, color=MUTE)

    for x0, y0, x1, y1 in ((23, 25.5, 23, 43.5), (75, 25.5, 60, 29.8)):
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>",
                                     mutation_scale=13, color=MUTE, lw=1.1,
                                     linestyle="--"))

    ax.add_patch(Rectangle((0, 1.5), 99, 9.5, facecolor="#FBFCFE",
                           edgecolor="#DDE1E8", lw=1.0))
    ax.text(1.5, 8.2, "prefill 을 새 / 재계산 으로 나누는 법 - Method B (집계 빼기)",
            fontsize=11.5, color=INK, fontweight="bold")
    ax.text(1.5, 5.2, "재계산 토큰 = 엔진이 실제 계산한 prefill 토큰 (sum  extend_num_tokens)  -  "
                      "프로그램별 불가피 컨텍스트 증가 (new_required)", fontsize=10.5, color=MUTE)
    ax.text(1.5, 2.8, "시간은 prefill GPU 시간을 이 토큰 비로 안분한다.", fontsize=10.5, color=MUTE)
    save(fig, "tierc_clock_diagram_yunuikang.png")


# ─────────────────────────────────────────── 2. 예산 스택
def fig_budget(H, Cs, name, w=13.0):
    fig, ax = plt.subplots(figsize=(w, 5.4), facecolor="white")
    xs, labs = [], []
    for gi, C in enumerate(Cs):
        for si, (tag, sysn) in enumerate((("MORI", "MORI"), ("TAO", "TA+O"))):
            c = H[f"{tag}_C{C}"]
            x = gi * 4.4 + si * 1.75
            bot = 0.0
            for key, col, _ in PART:
                v = c[key]
                ax.bar(x, v - 0.16, 0.80, bottom=bot + 0.08, color=col,
                       edgecolor="white", lw=0.8)
                if v >= 3.0:
                    ax.text(x, bot + v / 2, f"{v:.2f}", ha="center", va="center",
                            fontsize=9.2, color="white" if col != "#C9CDD6" else INK,
                            fontweight="bold")
                elif key != "idle_pct":          # 작은 조각은 바깥 인출선
                    ax.annotate(f"{v:.2f}", (x - 0.42, bot + v / 2),
                                xytext=(x - 1.05, bot + v / 2 - 6.0),
                                fontsize=8.6, color=col, fontweight="bold",
                                ha="center", va="center",
                                arrowprops=dict(arrowstyle="-", color=col, lw=0.8))
                bot += v
            # transfer - 별도(가산 안 함)
            xt = x + 0.68
            ax.bar(xt, c["transfer_pct"], 0.22, color=PURPLE, alpha=0.9)
            ax.text(xt, c["transfer_pct"] + 1.6, f"{c['transfer_pct']:.2f}",
                    ha="center", fontsize=8.6, color=PURPLE, fontweight="bold")
            xs.append(x); labs.append(sysn)
        ax.text(gi * 4.4 + 0.87, -9.0, f"C = {C}\noversub {H[f'MORI_C{C}']['oversub']:.2f}x",
                ha="center", va="top", fontsize=11, color=INK, fontweight="bold")
    ax.set_xticks(xs); ax.set_xticklabels(labs, fontsize=10.5)
    ax.set_ylim(0, 104)
    style(ax, ylab="창 wall 대비 몫 (%)")
    ax.legend(handles=[Patch(facecolor=c, label=l) for _, c, l in PART] +
                      [Patch(facecolor=PURPLE, alpha=0.9,
                             label="transfer (별도 스트림 / 예산 미가산)")],
              loc="upper center", bbox_to_anchor=(0.5, 1.17), ncol=5,
              frameon=False, fontsize=10)
    save(fig, name)


# ─────────────────────────────────────────── 3. 3점 곡선 4패널
def fig_curve4(H, R):
    Cs = [20, 40, 80]
    panels = [
        ("prefill - 재계산 몫 (창 wall 대비 %)", lambda c: c["prefill_recompute_pct"],
         "{:.2f}", "upper left"),
        ("Waiting 축출 (건)", lambda c: c["wait_evict"], "{:.0f}", "upper left"),
        ("reload 토큰 / 출력 토큰", lambda c: c["reload_per_output"], "{:.2f}", "upper left"),
        ("prefix hit (엔진 cached / prompt)", lambda c: c["prefix_hit"], "{:.3f}", "lower left"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(13.0, 7.4), facecolor="white")
    for ax, (title, get, fmt, leg) in zip(axes.ravel(), panels):
        series = {}
        for tag, sysn in (("MORI", "MORI"), ("TAO", "TA+O")):
            ys = [get(H[f"{tag}_C{C}"]) for C in Cs]
            series[sysn] = ys
            ax.plot(Cs, ys, "-o", color=SYSC[sysn], lw=2.2, ms=8,
                    markeredgecolor="white", markeredgewidth=1.2, label=sysn)
        for i, C in enumerate(Cs):
            hi = "MORI" if series["MORI"][i] >= series["TA+O"][i] else "TA+O"
            for sysn in ("MORI", "TA+O"):
                dy = 13 if sysn == hi else -16
                ax.annotate(fmt.format(series[sysn][i]), (C, series[sysn][i]),
                            textcoords="offset points", xytext=(0, dy),
                            ha="center", va="bottom" if dy > 0 else "top",
                            fontsize=9.4, color=SYSC[sysn], fontweight="bold")
        style(ax, title=title, xlab="C (동시성)")
        ax.set_xticks(Cs)
        ax.set_xticklabels([f"{C}\n({H[f'MORI_C{C}']['oversub']:.2f}x)" for C in Cs])
        ax.set_xlim(min(Cs) - 9, max(Cs) + 9)
        lo = min(min(v) for v in series.values())
        hi_ = max(max(v) for v in series.values())
        rng = (hi_ - lo) or 1.0
        ax.set_ylim(lo - rng * 0.22, hi_ + rng * 0.20)
        ax.set_yticks([t for t in ax.get_yticks() if t >= 0 and t <= hi_ + rng * 0.20])
        ax.legend(frameon=False, fontsize=10.5, loc=leg)
    fig.tight_layout(pad=1.6)
    save(fig, "tierc_curve4_deck_yunuikang.png")


# ─────────────────────────────────────────── 4. 파생 지표
def fig_derived(H):
    Cs = [20, 40, 80]
    fig, axes = plt.subplots(1, 3, figsize=(13.6, 4.5), facecolor="white")
    specs = [("goodput@5s (tok/s)", "goodput5", "{:.1f}", False),
             ("엔진 steady-window thr (tok/s)", "engine_thr", "{:.1f}", False),
             ("TTFT (s) - p50 / p95", None, None, True)]
    for ax, (title, key, fmt, is_ttft) in zip(axes, specs):
        w = 0.36
        for si, (tag, sysn) in enumerate((("MORI", "MORI"), ("TAO", "TA+O"))):
            xs = [i + (si - 0.5) * w for i in range(len(Cs))]
            if not is_ttft:
                ys = [H[f"{tag}_C{C}"][key] for C in Cs]
                ax.bar(xs, ys, w * 0.92, color=SYSC[sysn], label=sysn)
                for x, y in zip(xs, ys):
                    ax.text(x, y * 1.02, fmt.format(y), ha="center", va="bottom",
                            fontsize=9.2, color=SYSC[sysn], fontweight="bold")
            else:
                p95 = [H[f"{tag}_C{C}"]["ttft_p95"] for C in Cs]
                p50 = [H[f"{tag}_C{C}"]["ttft_p50"] for C in Cs]
                ax.bar(xs, p95, w * 0.92, color=SYSC[sysn], alpha=0.35,
                       label=f"{sysn} p95")
                ax.bar(xs, p50, w * 0.92, color=SYSC[sysn], label=f"{sysn} p50")
                for x, a, b in zip(xs, p95, p50):
                    ax.text(x, a * 1.06, f"{a:.1f}", ha="center", va="bottom",
                            fontsize=8.8, color=SYSC[sysn], fontweight="bold")
                    ax.text(x, b * 1.06, f"{b:.2f}", ha="center", va="bottom",
                            fontsize=8.2, color=SYSC[sysn])
        if is_ttft:
            ax.set_yscale("log"); ax.set_ylim(0.3, 400)
        ax.set_xticks(range(len(Cs)))
        ax.set_xticklabels([f"C={C}" for C in Cs])
        style(ax, title=title)
        ax.legend(frameon=False, fontsize=9.5, ncol=2, loc="upper left")
        if not is_ttft:
            ax.set_ylim(0, max(H[f"{t}_C{C}"][key] for t in ("MORI", "TAO")
                               for C in Cs) * 1.22)
    fig.tight_layout(pad=1.4)
    save(fig, "tierc_derived_deck_yunuikang.png")


# ─────────────────────────────────────────── 5. rank 분포
def fig_rank(RK):
    tags = [t for t in ("MORI_C20", "MORI_C40", "MORI_C80") if t in RK]
    fig, axes = plt.subplots(1, 2, figsize=(13.0, 4.4), facecolor="white",
                             gridspec_kw={"width_ratios": [1.15, 1]})
    ax = axes[0]
    cols = {"2": RED, "1": AMBER, "0": BLUE}
    labs = {"2": "rank 2 busy (iota<0.33)", "1": "rank 1 mixed (0.33<=iota<0.66)",
            "0": "rank 0 idle (iota>=0.66)"}
    for i, t in enumerate(tags):
        bot = 0.0
        for k in ("2", "1", "0"):
            v = RK[t]["pct"][k]
            ax.bar(i, v, 0.6, bottom=bot, color=cols[k], edgecolor="white", lw=1.2,
                   label=labs[k] if i == 0 else None)
            ax.text(i, bot + v / 2, f"{v:.1f}%", ha="center", va="center",
                    fontsize=10, color="white", fontweight="bold")
            bot += v
    ax.set_xticks(range(len(tags)))
    ax.set_xticklabels([f"{t.replace('MORI_', '')}\n스탬프 {RK[t]['n_stamps']:,}건"
                        for t in tags], fontsize=10)
    ax.set_ylim(0, 145)
    style(ax, ylab="스탬프 비율 (%)", title="_type_rank 분포 (MORI 셀)")
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.legend(frameon=False, fontsize=9.8, ncol=1, loc="upper center",
              bbox_to_anchor=(0.5, 1.01))

    ax = axes[1]
    for i, t in enumerate(tags):
        q = RK[t]["iota"]
        ax.plot([q["p10"], q["p90"]], [i, i], color=MUTE, lw=2.0, zorder=1)
        ax.plot([q["p25"], q["p75"]], [i, i], color=PURPLE, lw=7.0,
                solid_capstyle="butt", zorder=2)
        ax.plot([q["p50"]], [i], "o", color="white", ms=9, zorder=3,
                markeredgecolor=PURPLE, markeredgewidth=2.0)
        for v, lab, dy in ((q["p10"], "p10", 0.26), (q["p50"], "p50", -0.30),
                           (q["p90"], "p90", 0.26)):
            ax.annotate(f"{lab} {v:.3f}", (v, i), textcoords="offset points",
                        xytext=(0, dy * 40), ha="center", fontsize=9,
                        color=MUTE if lab != "p50" else PURPLE,
                        fontweight="bold" if lab == "p50" else "normal")
    for b in (0.33, 0.66):
        ax.axvline(b, color=GRID, ls="--", lw=1.2)
        ax.text(b, len(tags) - 0.34, f"iota={b}", ha="center", fontsize=9, color=MUTE)
    ax.set_yticks(range(len(tags)))
    ax.set_yticklabels([t.replace("MORI_", "") for t in tags], fontsize=10.5)
    ax.set_ylim(-0.6, len(tags) - 0.15)
    ax.set_xlim(0, 1)
    style(ax, xlab="iota (idleness)", title="iota 분포 - p10 / p25-p75 / p50 / p90")
    ax.xaxis.grid(True, color=GRID, lw=0.8); ax.yaxis.grid(False)
    fig.tight_layout(pad=1.4)
    save(fig, "tierc_rank_deck_yunuikang.png")


def main():
    D = json.load(open(NUM))
    fig_clock()
    fig_budget(D["h200"], [20, 40, 80], "tierc_budget_deck_yunuikang.png")
    fig_curve4(D["h200"], D["h200_ratio"])
    fig_derived(D["h200"])
    fig_rank(D["rank"])
    if "h5090" in D:
        Cs = sorted({c["C"] for c in D["h5090"].values()})
        fig_budget(D["h5090"], Cs, "tierc_5090_budget_deck_yunuikang.png", w=9.5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
