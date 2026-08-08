#!/usr/bin/env python3
"""H200 그림 공통 — 원시 데이터 로더 + 하우스 스타일.

수치는 전부 ~/yunuikang_work/h200_scratch/mori/ 원시 JSONL/CSV 에서만 읽는다.
(RESULTS 로그의 `scratch/mori/...` 경로 표기는 틀렸다 — ANALYSIS §0.2)
스타일 규격: docs/DECK_STYLE_yunuikang.md §5.
"""
import csv
import json
import os
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Noto Sans CJK KR"
plt.rcParams["axes.unicode_minus"] = False

RAW = os.path.expanduser("~/yunuikang_work/h200_scratch/mori")
FIG = "/home/yunuikang/yunuikang_work/distserving/figures"

# 고정 팔레트 (DECK_STYLE §1 · CVD 검증 통과 조합)
SYS_COLOR = {"SMG": "#6E4B9E", "TA": "#B87A1E", "TAO": "#2E5EAA", "MORI": "#C0392B"}
SYS_LABEL = {"SMG": "SMG", "TA": "TA", "TAO": "TA+O", "MORI": "MORI"}
SYS_ORDER = ["SMG", "TA", "TAO", "MORI"]          # 고정 순서 — 절대 바꾸지 않는다

INK, MUTE, GRID = "#1A1A2E", "#6B6B7B", "#DDE1E8"
OK, BAD, AMBER = "#1E7D4F", "#C0392B", "#B87A1E"
WIN_BG, LOSE_BG = "#E7F3EC", "#FBE9E7"


def jl(path):
    return [json.loads(l) for l in open(path) if l.strip()]


def phase2():
    """{(system, C): row} — 12셀."""
    out = {}
    for r in jl(f"{RAW}/h200_phase2/cell_summaries.jsonl"):
        out[(r["system"], int(r["tag"].split("C")[-1]))] = r
    for r in jl(f"{RAW}/h200_phase2/results_phase2.jsonl"):
        out[(r["system"], int(r["concurrency"]))].update(
            ttft_p95_s=r["ttft_p95_s"], completed_programs=r["completed_programs"])
    return out


def phase1(which="h200_phase1"):
    """{system: row} — F1 2셀. which: h200_phase1(7B) | h200_phase1_8b(8B)."""
    return {r["system"]: r for r in jl(f"{RAW}/{which}/cell_summaries.jsonl")}


def engine_delta(tag, sub="h200_phase2"):
    """steady 창(0.2~1.0)의 엔진 카운터 델타 → prefix hit 등."""
    rows = list(csv.DictReader(open(f"{RAW}/{sub}/engine_{tag}.csv")))
    ts = [float(r["t"]) for r in rows]
    lo = min(ts) + 0.2 * (max(ts) - min(ts))
    S = [r for r in rows if float(r["t"]) >= lo]
    f = lambda r, k: float(r[k]) if r.get(k) not in (None, "", "None") else 0.0
    d = lambda k: f(S[-1], k) - f(S[0], k)
    prompt, cached = d("prompt_tokens_total"), d("cached_tokens_total")
    return dict(hit=cached / prompt if prompt else None,
                load_back=d("load_back_tokens_total"))


def gpu_util(tag, sub="h200_phase2"):
    p = f"{RAW}/{sub}/gpu_{tag}.jsonl"
    if not os.path.exists(p):
        return None
    rows = list(csv.DictReader(open(p)))
    ts = [float(r["t"]) for r in rows]
    lo = min(ts) + 0.2 * (max(ts) - min(ts))
    v = [float(r["gpu0_util"]) for r in rows
         if float(r["t"]) >= lo and r.get("gpu0_util") not in (None, "", "None")]
    return st.mean(v) if v else None


def style(ax, ylab=None, xlab=None, title=None, grid_axis="y"):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTE, labelsize=9.5, length=3)
    ax.grid(axis=grid_axis, color=GRID, lw=0.7, alpha=0.9)
    ax.set_axisbelow(True)
    if ylab:
        ax.set_ylabel(ylab, color=MUTE, fontsize=10)
    if xlab:
        ax.set_xlabel(xlab, color=MUTE, fontsize=10)
    if title:
        ax.set_title(title, color=INK, fontsize=11.5, fontweight="bold", pad=9)


def save(fig, name):
    os.makedirs(FIG, exist_ok=True)
    p = os.path.join(FIG, f"{name}.png")
    fig.savefig(p, dpi=200, bbox_inches="tight", facecolor="white")
    print("wrote", p)
    return p
