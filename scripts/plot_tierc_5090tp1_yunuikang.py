#!/usr/bin/env python3
"""5090 TP1 · 7B Tier C — C 스윕 그림 (미해결 #1 판별).

A: C별 GPU 시간 예산 스택 (MORI/TA+O 나란히) — decode/prefill_new/prefill_recompute/idle
B: MORI÷TA+O 비 vs C — 1.0 기준선 + 원래 5090 TP2 앵커(0.45) 표시
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plot_h200_lib_yunuikang import style, save, INK, MUTE, GRID, OK, BAD, WIN_BG, LOSE_BG  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

D = "/home/yunuikang/yunuikang_work/scratch/mori/tierc_5090tp1"
CS = [7, 15, 20, 70]
ANCHOR = 0.45          # 원래 5090 TP2 · 8B · C80 [측정]
PART = [("decode_ms", "decode", "#1E7D4F"),
        ("prefill_new_ms", "prefill — 새", "#2E5EAA"),
        ("prefill_recompute_ms", "prefill — 재계산", "#C0392B"),
        ("idle_ms", "idle", "#C9CDD6")]


def main():
    A = {x["tag"]: x for x in json.load(open(f"{D}/tierc_summary.json"))}
    V = json.load(open(f"{D}/tierc_verdict.json"))
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 4.3),
                             gridspec_kw={"width_ratios": [1.35, 1.0]})

    # ── A: 예산 스택
    ax = axes[0]
    xs, labs, w = [], [], 0.38
    for i, C in enumerate(CS):
        for k, s in enumerate(("MORI", "TAO")):
            xs.append(i + (k - 0.5) * w)
            labs.append(s)
    bottoms = [0.0] * len(xs)
    for key, name, col in PART:
        vals = []
        for C in CS:
            for s in ("MORI", "TAO"):
                a = A[f"{s}_C{C}"]
                vals.append(max(0.0, a[key]) / a["wall_ms"] * 100)
        ax.bar(xs, vals, w, bottom=bottoms, color=col, edgecolor="white", lw=1.1, label=name)
        for x, v, b in zip(xs, vals, bottoms):
            if v >= 6:
                ax.text(x, b + v / 2, f"{v:.0f}", ha="center", va="center", fontsize=8.5,
                        color="white" if col != "#C9CDD6" else INK, fontweight="bold")
        bottoms = [b + v for b, v in zip(bottoms, vals)]
    for i, C in enumerate(CS):
        for k, s in enumerate(("MORI", "TAO")):
            ax.text(i + (k - 0.5) * w, -4.5, "M" if s == "MORI" else "T", ha="center",
                    fontsize=9, color=BAD if s == "MORI" else "#2E5EAA", fontweight="bold")
    ax.set_xticks(range(len(CS)))
    ax.set_xticklabels([f"C={C}\noversub {C/7:.2f}×" for C in CS], fontsize=9.5)
    ax.set_ylim(-7, 108)
    style(ax, ylab="window wall 중 비중 (%)",
          title="A. GPU 시간 예산 — 압박이 커질수록 idle 이 사라지고 재계산이 지배한다")
    ax.legend(frameon=False, fontsize=8.5, loc="upper center", ncol=4, columnspacing=1.0,
              handlelength=1.2)

    # ── B: 비율
    ax = axes[1]
    ax.axhspan(1.0, 2.3, color=WIN_BG, zorder=0)
    ax.axhspan(0.2, 1.0, color=LOSE_BG, zorder=0)
    series = [("goodput @5s", "gp", BAD, "-o", 2.6, 9),
              ("엔진 decode 토큰", "eng", MUTE, "--s", 1.7, 6),
              ("드라이버 thr (편향)", "drv", "#B87A1E", ":^", 1.5, 6)]
    for name, k, col, mk, lw, ms in series:
        ys = [V[f"MORI_C{C}"][k] / V[f"TAO_C{C}"][k] for C in CS]
        ax.plot(CS, ys, mk, color=col, lw=lw, ms=ms, markeredgecolor="white",
                markeredgewidth=1.2, label=name, zorder=4 if k == "gp" else 3)
        if k == "gp":
            for C, y in zip(CS, ys):
                dx, ha = (-6, "right") if C == CS[-1] else (0, "center")
                ax.annotate(f"{y:.3f}", (C, y), textcoords="offset points", xytext=(dx, 11),
                            ha=ha, fontsize=9.5, color=INK, fontweight="bold")
    ax.axhline(1.0, color=INK, lw=1.6, ls="--", zorder=5)
    ax.axhline(ANCHOR, color="#4A4A63", lw=1.8, ls="-.", zorder=5)
    ax.annotate(f"원래 5090 TP2·8B·C80 = {ANCHOR:.2f}×\n(붕괴 — 여기서 재현되지 않았다)",
                xy=(70, ANCHOR), xytext=(17, 0.60), fontsize=9, color="#4A4A63",
                fontweight="bold",
                arrowprops=dict(arrowstyle="->", color="#4A4A63", lw=1.2))
    ax.set_xscale("log"); ax.set_xticks(CS)
    ax.set_xticklabels([f"C={C}" for C in CS], fontsize=9.5)
    ax.get_xaxis().set_minor_formatter(plt.NullFormatter())
    ax.set_xlim(6.0, 105)
    ax.set_ylim(0.25, 2.3)
    style(ax, ylab="MORI ÷ TA+O", xlab="동시성 C (로그축)",
          title="B. ★ C70(oversub 10.0×)에서도 세 지표 모두 1.0 위\n= 붕괴 미재현")
    ax.legend(frameon=False, fontsize=8.5, loc="upper left")
    ax.text(102, 1.06, "MORI 우위", fontsize=9, color=OK, fontweight="bold", ha="right")
    ax.text(102, 0.90, "MORI 열세", fontsize=9, color=BAD, fontweight="bold", ha="right")

    fig.suptitle("5090 ×1 · TP1 · Qwen2.5-7B · fit 7.00 (MAXTOK 226,632) · r=2 · 셀 25분 · "
                 "n=1 · closure C1~C4 전 셀 PASS   [측정]",
                 fontsize=9.5, color=MUTE, y=1.03)
    save(fig, "mori_tierc_5090tp1_yunuikang")

    print(f"\n{'C':>4}{'oversub':>9}{'goodput비':>11}{'엔진비':>9}{'드라이버비':>11}")
    for C in CS:
        m, t = V[f"MORI_C{C}"], V[f"TAO_C{C}"]
        print(f"{C:>4}{C/7:9.2f}{m['gp']/t['gp']:11.3f}{m['eng']/t['eng']:9.3f}{m['drv']/t['drv']:11.3f}")


if __name__ == "__main__":
    main()
