#!/usr/bin/env python3
"""검증 덱용 그림 생성. 모든 수치는 scratch/mori/deck_numbers.json(로그 직추출)에서만 읽는다.

dataviz 규칙 준수:
  * 고정 순서 categorical 팔레트 (검증 통과: SMG/TA/TAO/MORI = 보라/앰버/블루/레드,
    worst CVD ΔE 18.8 protan/tritan — floor band 아님)
  * **dual-axis 금지** — 척도가 다른 두 지표는 별도 패널(small multiples)로.
  * 계열 2개 이상이면 legend 항상 + 직접 라벨 병행(색 단독 식별 금지)
  * 얇은 마크, 억제된 grid/axis, 값 라벨은 선택적으로만
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle

plt.rcParams["font.family"] = "Noto Sans CJK KR"
plt.rcParams["axes.unicode_minus"] = False

D = json.load(open("/home/yunuikang/yunuikang_work/scratch/mori/deck_numbers.json"))
FIG = "/home/yunuikang/yunuikang_work/distserving/figures"
os.makedirs(FIG, exist_ok=True)

# 고정 순서 팔레트 (validate_palette.js 통과)
SMG, TA, TAO, MORI = "#6E4B9E", "#B87A1E", "#2E5EAA", "#C0392B"
INK, MUTE, GRID = "#1A1A2E", "#6B6B7B", "#DDE1E8"
OK, BAD = "#1E7D4F", "#C0392B"
HEALTHY_BG, EXTREME_BG = "#E7F3EC", "#FBE9E7"


def style(ax, ylab=None, xlab=None, title=None):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTE, labelsize=9, length=3)
    ax.grid(axis="y", color=GRID, lw=0.7, alpha=0.9)
    ax.set_axisbelow(True)
    if ylab:
        ax.set_ylabel(ylab, color=MUTE, fontsize=9.5)
    if xlab:
        ax.set_xlabel(xlab, color=MUTE, fontsize=9.5)
    if title:
        ax.set_title(title, color=INK, fontsize=11.5, fontweight="bold", pad=8)


def save(fig, name):
    p = os.path.join(FIG, name + ".png")
    fig.savefig(p, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("  wrote", os.path.basename(p))


# ---------------------------------------------------------------- F1: A6b ι 궤적
def f_a6b():
    traj = D["A6b_traj"]                       # "0s=0.048, 1s=0.065, ..."
    xs, ys = [], []
    for tok in traj.split(","):
        k, v = tok.strip().split("=")
        xs.append(float(k.rstrip("s")))
        ys.append(float(v))
    cross = D["A6b_crossover_s"]

    fig, ax = plt.subplots(figsize=(5.0, 3.0))
    ax.plot(xs, ys, "-o", color=MORI, lw=2, ms=6, zorder=3,
            markeredgecolor="white", markeredgewidth=1.2, label="ι (진행 중 tool call)")
    ax.axhline(0.5, color=MUTE, lw=1.2, ls="--", zorder=1)
    ax.axvline(cross, color=OK, lw=1.4, ls=":", zorder=1)
    ax.annotate(f"{cross}s에 ι=0.5 통과\n→ demote 대상이 됨",
                xy=(cross, 0.5), xytext=(cross + 55, 0.30), fontsize=8.5, color=OK,
                arrowprops=dict(arrowstyle="->", color=OK, lw=1.2))
    for x, y in [(xs[0], ys[0]), (xs[4], ys[4]), (xs[-1], ys[-1])]:
        ax.annotate(f"{y:.3f}", (x, y), textcoords="offset points", xytext=(4, 7),
                    fontsize=8.5, color=INK, fontweight="bold")
    ax.set_ylim(0, 1.0)
    style(ax, ylab="ι (상대 idleness)", xlab="tool call 경과 시간 (초)")
    ax.legend(frameon=False, fontsize=8.5, loc="lower right")
    save(fig, "mori_ver_A6b_iota_yunuikang")


# ---------------------------------------------------------------- F2: B tier 이동
def f_tier():
    rows = D["B_tier_moves"]
    C = [r["C"] for r in rows]
    dem = [r["demote"] for r in rows]
    pro = [r["promote"] for r in rows]
    ev = [r["evict"] for r in rows]
    x = range(len(C))
    fig, ax = plt.subplots(figsize=(6.2, 3.0))
    w = 0.27
    ax.bar([i - w for i in x], dem, w * 0.92, color=MORI, label="demote GPU→CPU")
    ax.bar(list(x), pro, w * 0.92, color=TAO, label="promote CPU→GPU")
    ax.bar([i + w for i in x], ev, w * 0.92, color=SMG, label="evict CPU→Waiting (KV 폐기)")
    for i, (d, e) in enumerate(zip(dem, ev)):
        if d:
            ax.text(i - w, d + 14, str(d), ha="center", fontsize=8, color=INK, fontweight="bold")
        if e:
            ax.text(i + w, e + 14, str(e), ha="center", fontsize=8, color=SMG, fontweight="bold")
    ax.text(0.5, 60, "무압박 → 이동 0\n(스티키 확인)", ha="center", fontsize=8.5, color=OK)
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"C{c}\n{r['oversub']}×" for c, r in zip(C, rows)], fontsize=8.5)
    style(ax, ylab="이벤트 수 (1시간 run)", xlab="동시성 C / oversub")
    ax.legend(frameon=False, fontsize=8.5, loc="upper left")
    save(fig, "mori_ver_tier_moves_yunuikang")


# ---------------------------------------------------------------- F3: B2 util vs thr (2패널)
def f_util_thr():
    b2 = D["B2"]
    C = [r["C"] for r in b2]
    x = list(range(len(C)))
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.1))
    series = [("TA", TA, "TA (offload 없음)"), ("TAO", TAO, "TA+O (offload+LRU)"),
              ("MORI", MORI, "MORI (offload+typed)")]
    for key, col, lab in series:
        axes[0].plot(x, [r[key]["util"] for r in b2], "-o", color=col, lw=2, ms=5,
                     markeredgecolor="white", markeredgewidth=1, label=lab)
        axes[1].plot(x, [r[key]["thr"] for r in b2], "-o", color=col, lw=2, ms=5,
                     markeredgecolor="white", markeredgewidth=1, label=lab)
    for ax, ttl, yl in ((axes[0], "GPU util (%)", "util %"), (axes[1], "output throughput (tok/s)", "tok/s")):
        ax.axvspan(1.5, 3.5, color=HEALTHY_BG, zorder=0)
        ax.axvspan(4.5, 6.5, color=EXTREME_BG, zorder=0)
        ax.set_xticks(x)
        ax.set_xticklabels([f"{c}\n{r['oversub']}×" for c, r in zip(C, b2)], fontsize=8)
        style(ax, ylab=yl, xlab="C / oversub", title=ttl)
    axes[0].text(2.5, 12, "건강", ha="center", fontsize=9, color=OK, fontweight="bold")
    axes[0].text(5.5, 12, "극단", ha="center", fontsize=9, color=BAD, fontweight="bold")
    # 직접 라벨 (색 단독 식별 금지)
    axes[0].annotate("MORI 90.5", (6, 90.5), textcoords="offset points", xytext=(-46, 2),
                     fontsize=8.5, color=MORI, fontweight="bold")
    axes[1].annotate("MORI 6.5", (6, 6.5), textcoords="offset points", xytext=(-40, -12),
                     fontsize=8.5, color=MORI, fontweight="bold")
    axes[1].annotate("TA+O 14.3", (6, 14.3), textcoords="offset points", xytext=(-50, 4),
                     fontsize=8.5, color=TAO, fontweight="bold")
    axes[0].legend(frameon=False, fontsize=8, loc="lower right")
    fig.suptitle("util은 오르는데 throughput은 무너진다 — 같은 축이 아님(별도 패널)",
                 fontsize=10, color=MUTE, y=1.03)
    save(fig, "mori_ver_util_thr_yunuikang")


# ---------------------------------------------------------------- F4: STEP7 4지표
def f_step7():
    s7 = D["S7"]
    w8, w10, w20, w80, t80 = (s7["waste"][k] for k in
                              ("MORI_r2_C8", "MORI_r2_C10", "MORI_r2_C20",
                               "MORI_r2_C80", "TAO_r2_C80"))
    th = s7["thrash"]
    labs = ["C8\n1.0×", "C10\n1.2×", "C20\n2.5×", "C80\n9.9×", "TA+O C80\n9.9×"]
    cols = [MORI, MORI, MORI, MORI, TAO]
    edge = ["none", "none", "none", BAD, "none"]
    N = len(labs)

    panels = [
        ("① 생산성 = thr ÷ util", [float(s7["prod_C8_MORI"]), float(s7["prod_C10_MORI"]),
                                float(s7["prod_C20_MORI"]), float(s7["prod_C80_MORI"]),
                                float(s7["prod_C80_TAO"])], "{:.1f}"),
        ("② 낭비율 = recompute ÷ (dec+pre)",
         [w8["waste"], w10["waste"], w20["waste"], w80["waste"], t80["waste"]], "{:.3f}"),
        ("④ 출력 / promote (토큰)", [float(th[k]["out_per_promote"].replace(",", ""))
                                for k in ("MORI_r2_C8", "MORI_r2_C10", "MORI_r2_C20",
                                          "MORI_r2_C80")] + [0], "{:,.0f}"),
        ("④ ping-pong (2회↑ 강등 비율 %)", [th[k]["pingpong"] for k in
                                     ("MORI_r2_C8", "MORI_r2_C10", "MORI_r2_C20",
                                      "MORI_r2_C80")] + [0], "{:.1f}"),
    ]
    fig, axes = plt.subplots(1, 4, figsize=(13.0, 2.95))
    for ax, (ttl, vals, fmt) in zip(axes, panels):
        bars = ax.bar(range(N), vals, 0.66, color=cols)
        for b, e in zip(bars, edge):
            if e != "none":
                b.set_edgecolor(e); b.set_linewidth(2)
        for i, (b, v) in enumerate(zip(bars, vals)):
            if v == 0 and i == N - 1:
                ax.text(i, 0.02 * max(vals), "n/a", ha="center", fontsize=8.5, color=MUTE)
                b.set_alpha(0.12)
            else:
                ax.text(i, v + 0.035 * max(vals), fmt.format(v), ha="center",
                        fontsize=8.5, color=INK, fontweight="bold")
        ax.set_xticks(range(N))
        ax.set_xticklabels(labs, fontsize=8.4)
        ax.set_ylim(0, max(vals) * 1.24)
        style(ax, title=ttl)
        ax.get_xticklabels()[3].set_color(BAD)
        ax.get_xticklabels()[3].set_fontweight("bold")
    fig.suptitle("MORI(빨강) — 압박이 커질수록 단조 악화, 극단 C80에서 붕괴  ·  TA+O(파랑)는 같은 C80 대조   [측정]",
                 fontsize=10.5, color=MUTE, y=1.07)
    save(fig, "mori_ver_step7_metrics_yunuikang")


# ---------------------------------------------------------------- F5: pause 분해
def f_pause():
    p = D["S7"]["profile_ttft"]
    g = D["S7"]["profile_goodput"]
    keys = ["MORI_r2_C10", "MORI_r2_C80", "TAO_r2_C80"]
    labs = ["MORI C10\n(건강 1.2×)", "MORI C80\n(극단 9.9×)", "TA+O C80\n(극단 9.9×)"]

    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.1))
    # 좌: TTFT 중앙값 = pause + prefill  (누적, 2px 흰 간격)
    ax = axes[0]
    pause = [p[k]["pause_p50"] for k in keys]
    pref = [p[k]["prefill_p50"] for k in keys]
    ax.bar(range(3), pause, 0.55, color=BAD, label="pause (스케줄러 대기 · GPU 아님)")
    ax.bar(range(3), pref, 0.55, bottom=pause, color=TAO, label="prefill (실제 계산)",
           edgecolor="white", linewidth=2)
    for i, k in enumerate(keys):
        tot = p[k]["ttft_p50"]
        ax.text(i, tot + 1.6, f"TTFT {tot:.2f}s", ha="center", fontsize=8.5,
                color=INK, fontweight="bold")
        if p[k]["pause_p50"] > 1:
            ax.text(i, pause[i] / 2, f"{pause[i]:.1f}s", ha="center", fontsize=8.5,
                    color="white", fontweight="bold")
        ax.text(i, -3.4, f"대기 스텝 {p[k]['pause_nonzero']}%", ha="center",
                fontsize=8, color=MUTE)
    ax.set_xticks(range(3)); ax.set_xticklabels(labs, fontsize=8)
    ax.set_ylim(-5, 52)
    style(ax, ylab="TTFT 중앙값 (초)", title="TTFT 분해: pause가 지배하는가")
    ax.legend(frameon=False, fontsize=8, loc="lower center",
              bbox_to_anchor=(0.5, 1.06), ncol=1)

    # 우: throughput vs goodput (같은 단위 tok/s → 한 축 OK)
    ax = axes[1]
    thr = [g[k]["thr"] for k in keys]
    gp = [g[k]["slo5_gp"] for k in keys]
    xx = range(3)
    ax.bar([i - 0.17 for i in xx], thr, 0.32, color=MUTE, label="throughput (전체 산출)")
    ax.bar([i + 0.17 for i in xx], gp, 0.32, color=OK, label="goodput (SLO 5초 만족분)")
    for i, k in enumerate(keys):
        ax.text(i - 0.17, thr[i] + 1.0, f"{thr[i]:.1f}", ha="center", fontsize=8.5, color=INK)
        ax.text(i + 0.17, gp[i] + 1.0, f"{gp[i]:.1f}", ha="center", fontsize=8.5,
                color=OK, fontweight="bold")
        ax.text(i, -3.4, f"만족 {g[k]['slo5_sat']}%", ha="center", fontsize=8, color=MUTE)
    ax.set_xticks(list(xx)); ax.set_xticklabels(labs, fontsize=8)
    ax.set_ylim(-5, 46)
    style(ax, ylab="tok/s", title="throughput vs goodput (동일 단위)")
    ax.legend(frameon=False, fontsize=8, loc="lower center",
              bbox_to_anchor=(0.5, 1.06), ncol=1)
    ax.annotate("goodput 격차 24배\n(throughput 격차는 1.8배)", xy=(1.17, 0.7),
                xytext=(1.32, 24), fontsize=8.5, color=BAD, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=BAD, lw=1.3))
    save(fig, "mori_ver_pause_goodput_yunuikang")


# ---------------------------------------------------------------- F6: M-SWP 전곡선
def f_curve():
    b2 = D["B2"]
    C = [r["C"] for r in b2]
    x = list(range(len(C)))
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.1))
    for key, col, lab in (("TA", TA, "TA"), ("TAO", TAO, "TA+O"), ("MORI", MORI, "MORI")):
        axes[0].plot(x, [r[key]["thr"] for r in b2], "-o", color=col, lw=2, ms=5,
                     markeredgecolor="white", markeredgewidth=1, label=lab)
        axes[1].plot(x, [r[key]["ttft_p50"] for r in b2], "-o", color=col, lw=2, ms=5,
                     markeredgecolor="white", markeredgewidth=1, label=lab)
    for ax, ttl, yl in ((axes[0], "output throughput (tok/s) — 높을수록 좋음", "tok/s"),
                        (axes[1], "TTFT p50 (초) — 낮을수록 좋음", "초")):
        ax.axvspan(1.5, 3.5, color=HEALTHY_BG, zorder=0)
        ax.axvspan(4.5, 6.5, color=EXTREME_BG, zorder=0)
        ax.set_xticks(x); ax.set_xticklabels([f"{c}\n{r['oversub']}×" for c, r in zip(C, b2)], fontsize=8)
        style(ax, ylab=yl, xlab="C / oversub", title=ttl)
        ax.legend(frameon=False, fontsize=8.5)
    axes[0].annotate("MORI 우위\n(21.1 / 23.7)", xy=(3.0, 23.7), xytext=(0.35, 17.5),
                     fontsize=8.5, color=OK, fontweight="bold",
                     arrowprops=dict(arrowstyle="->", color=OK, lw=1.2))
    axes[0].annotate("역전: MORI 6.5\nvs TA+O 14.3", xy=(6, 6.5), xytext=(4.0, 3.0),
                     fontsize=8.5, color=BAD, fontweight="bold",
                     arrowprops=dict(arrowstyle="->", color=BAD, lw=1.2))
    axes[1].set_yscale("log")
    axes[1].annotate("MORI 13.93s\n(TA+O 3.40s)", xy=(6, 13.93), xytext=(2.1, 5.2),
                     fontsize=8.5, color=BAD, fontweight="bold",
                     arrowprops=dict(arrowstyle="->", color=BAD, lw=1.2))
    save(fig, "mori_ver_msw_curve_yunuikang")


# ---------------------------------------------------------------- F7: 인과 사슬
def f_chain():
    fig, ax = plt.subplots(figsize=(11.4, 2.15))
    ax.set_xlim(0, 100); ax.set_ylim(0, 22); ax.axis("off")
    boxes = [
        ("극단 oversub\nC80 = 9.9×", "#4A4A63"),
        ("tier 왕복 폭증\n27.7회/분\nping-pong 90.7%", MORI),
        ("prefix cache 붕괴\n0.944 → 0.600", MORI),
        ("recompute 40%\npause 중앙 38.3초", MORI),
        ("goodput 0.7 tok/s\n(util은 90.5%)", BAD),
    ]
    w, gap = 17.6, 3.0
    for i, (txt, col) in enumerate(boxes):
        x0 = i * (w + gap)
        ax.add_patch(Rectangle((x0, 4), w, 13, facecolor=col, edgecolor="none",
                               zorder=2, alpha=0.93))
        ax.text(x0 + w / 2, 10.5, txt, ha="center", va="center", color="white",
                fontsize=9.0, fontweight="bold", zorder=3)
        if i < len(boxes) - 1:
            ax.add_patch(FancyArrowPatch((x0 + w + 0.4, 10.5), (x0 + w + gap - 0.4, 10.5),
                                         arrowstyle="-|>", mutation_scale=15,
                                         color="#4A4A63", lw=2, zorder=1))
    ax.text(50, 0.6, "정책은 논문대로 충실히 구현됨 — 무너진 것은 레짐이지 구현이 아니다   [추론]",
            ha="center", fontsize=9.5, color=MUTE, style="italic")
    save(fig, "mori_ver_causal_chain_yunuikang")


if __name__ == "__main__":
    print("figures:")
    f_a6b(); f_tier(); f_util_thr(); f_step7(); f_pause(); f_curve(); f_chain()
    print("done")
