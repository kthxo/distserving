#!/usr/bin/env python3
"""STEP 5 확장 — duty×f 2D 결과 표 2종 (Table A 극단 · Table B 전개).

데이터 소스 (전부 C=10, R=1):
  d=0.1 : scratch/step5/pilot/            (GPU0, full f-sweep)
  d=0.2 : scratch/step5/pilot_d02/ + gap_d02/   (f=2 신규)
  d=0.3 : scratch/step5/gap_d03/          (신규, GPU1)
  d=0.5 : scratch/step5/pilot_d05/ + gap_d05/   (f=2 신규)
  d=0.7 : scratch/step5/gap_d07/          (신규, GPU1)
  d=0.9 : scratch/step5/gap_d09/          (신규, GPU1)

산출:
  figures/step5_table_extreme_yunuikang.png   (A: 6 duty × {tr f=1, default f=∞})
  figures/step5_table_fgrid_yunuikang.png     (B: 6 duty × {1,1.5,2,∞} goodput 히트맵)
  scratch/step5/tables_2d.md                  (마크다운 표 2종, 결과 문서 append용)

지표 주의: throughput은 goodput(=completed/makespan, prog/s)로 계산.
raw decode tok/s는 default의 recompute 낭비를 토큰으로 세어 오도함(연구의 핵심 논점).

작성: 강윤의 · 2026-07-21 · STEP 5 확장
"""
import json
import os
import glob

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np

_ko = os.path.expanduser("~/.local/share/fonts/NotoSansCJKkr-Regular.otf")
if os.path.exists(_ko):
    fm.fontManager.addfont(_ko)
    plt.rcParams["font.family"] = "Noto Sans CJK KR"
    plt.rcParams["axes.unicode_minus"] = False

BASE = "/home/yunuikang/yunuikang_work/distserving"
FIT = 95936 / 20150  # 4.76109

DUTIES = [0.1, 0.2, 0.3, 0.5, 0.7, 0.9]
F_CANON = [1.0, 1.5, 2.0, 1e6]  # tr, mid, mid, default
F_LABEL = {1.0: "tr\n(f=1)", 1.5: "f=1.5", 2.0: "f=2", 1e6: "default\n(f=∞)"}

# duty → list of result jsonl source files
SOURCES = {
    0.1: ["scratch/step5/pilot/pilot_results.jsonl"],
    0.2: ["scratch/step5/pilot_d02/pilot_results.jsonl",
          "scratch/step5/gap_d02/pilot_results.jsonl"],
    0.3: ["scratch/step5/gap_d03/pilot_results.jsonl"],
    0.5: ["scratch/step5/pilot_d05/pilot_results.jsonl",
          "scratch/step5/gap_d05/pilot_results.jsonl"],
    0.7: ["scratch/step5/gap_d07/pilot_results.jsonl"],
    0.9: ["scratch/step5/gap_d09/pilot_results.jsonl"],
}


def f_key(f):
    """Map raw f to canonical bucket, or None if not one of the 4."""
    if f is None:
        return None
    if f > 1000:
        return 1e6
    for c in (1.0, 1.5, 2.0):
        if abs(f - c) < 0.01:
            return c
    return None


def load():
    """Return {d: {f_canon: metrics_dict}}."""
    data = {}
    for d, files in SOURCES.items():
        data[d] = {}
        for fn in files:
            path = os.path.join(BASE, fn)
            if not os.path.exists(path):
                print(f"  [warn] missing: {fn}")
                continue
            for line in open(path):
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                fk = f_key(r.get("f"))
                if fk is None:
                    continue
                wall = r.get("wall_s") or 0
                compl = r.get("completed") or 0
                failed = r.get("failed") or 0
                goodput = compl / wall if wall else 0.0
                total = compl + failed
                m = {
                    "f": r.get("f"),
                    "goodput": goodput,               # prog/s (correct throughput)
                    "tok_s": r.get("throughput_tok_per_s"),
                    "wall_s": wall,
                    "p95": r.get("latency_p95_s"),
                    "U": r.get("gpu_util_mean"),
                    "hit": r.get("TRUE_hit_rate"),
                    "fail_rate": (failed / total) if total else 0.0,
                    "completed": compl,
                    "failed": failed,
                    "preempt": r.get("num_preemptions"),
                }
                # last write wins (dedupe repeated f); prefer non-empty
                data[d][fk] = m
    return data


def fmt(v, spec):
    return spec.format(v) if v is not None else "—"


# ─────────────────────────────────────────────────────────────────────
# Table A — 극단 (6 duty × 2 policy)
# ─────────────────────────────────────────────────────────────────────
def table_a(data):
    fig, ax = plt.subplots(figsize=(13, 6.2))
    ax.axis("off")
    ax.set_title("Table A — duty별 tr(f=1) vs overcommit(f=∞): fit×d 전환에서 승자 뒤집힘",
                 fontsize=15, fontweight="bold", pad=14)

    # columns: duty, fit×d | tr: goodput,p95,hit,U,fail | def: goodput,p95,hit,U,fail | winner
    col_labels = [
        "d", "fit×d",
        "tr\ngoodput\n(prog/s)", "tr\np95(s)", "tr\nTRUE hit", "tr\nU(%)", "tr\nfail%",
        "def\ngoodput\n(prog/s)", "def\np95(s)", "def\nTRUE hit", "def\nU(%)", "def\nfail%",
        "승자\n(makespan)",
    ]
    rows, cell_colors = [], []
    C_TR = "#E3F2FD"; C_DEF = "#FFF3E0"
    for d in DUTIES:
        fitd = FIT * d
        tr = data[d].get(1.0, {})
        de = data[d].get(1e6, {})
        # winner by makespan (lower wall = better); handle missing
        win = "?"
        wcolor = "#FFFFFF"
        if tr.get("wall_s") and de.get("wall_s"):
            if tr["wall_s"] < de["wall_s"]:
                ratio = de["wall_s"] / tr["wall_s"]
                win = f"tr\n(+{(ratio-1)*100:.0f}%)"; wcolor = "#BBDEFB"
            else:
                ratio = tr["wall_s"] / de["wall_s"]
                win = f"default\n(+{(ratio-1)*100:.0f}%)"; wcolor = "#FFE0B2"
        row = [
            f"{d}", f"{fitd:.2f}",
            fmt(tr.get("goodput"), "{:.3f}"), fmt(tr.get("p95"), "{:.0f}"),
            fmt(tr.get("hit"), "{:.2f}"), fmt(tr.get("U"), "{:.0f}"),
            fmt(tr.get("fail_rate"), "{:.0%}"),
            fmt(de.get("goodput"), "{:.3f}"), fmt(de.get("p95"), "{:.0f}"),
            fmt(de.get("hit"), "{:.2f}"), fmt(de.get("U"), "{:.0f}"),
            fmt(de.get("fail_rate"), "{:.0%}"),
            win,
        ]
        rows.append(row)
        rc = ["#FFFFFF", "#F5F5F5"] + [C_TR]*5 + [C_DEF]*5 + [wcolor]
        cell_colors.append(rc)

    tbl = ax.table(cellText=rows, colLabels=col_labels, cellColours=cell_colors,
                   cellLoc="center", loc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9.5)
    tbl.scale(1.0, 2.3)
    for (r, c), cell in tbl.get_celld().items():
        if r == 0:
            cell.set_facecolor("#1B2A4A")
            cell.set_text_props(color="white", fontweight="bold")
            cell.set_fontsize(8.5)
        cell.set_edgecolor("#BDBDBD")

    # transition annotation between d=0.1 and d=0.2 rows
    ax.text(0.5, -0.02,
            "★ 전환: d=0.1(fit×d=0.48, default 승) → d=0.2(fit×d=0.95, tr 승).  "
            "정밀 전환점 fit×d* ≈ 0.62 (STEP 5 세밀 격자)는 두 점 사이.  "
            "throughput=goodput(완료/ makespan); raw tok/s는 recompute 낭비 포함해 오도.",
            transform=ax.transAxes, fontsize=9.5, ha="center", color="#333333",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#E8F5E9",
                      edgecolor="#43A047"))
    fig.savefig(f"{BASE}/figures/step5_table_extreme_yunuikang.png",
                dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("  wrote figures/step5_table_extreme_yunuikang.png")


# ─────────────────────────────────────────────────────────────────────
# Table B — 전개 히트맵 (6 duty × 4 f), goodput, row-max highlight
# ─────────────────────────────────────────────────────────────────────
def table_b(data):
    M = np.full((len(DUTIES), len(F_CANON)), np.nan)
    txt = [["" for _ in F_CANON] for _ in DUTIES]
    for i, d in enumerate(DUTIES):
        for j, fc in enumerate(F_CANON):
            m = data[d].get(fc)
            if m and m.get("goodput"):
                M[i, j] = m["goodput"]
                txt[i][j] = f"{m['goodput']:.3f}"

    fig, ax = plt.subplots(figsize=(9.5, 7))
    # normalize per row for color (each duty's own scale) so pattern of best-f is visible
    Mnorm = np.full_like(M, np.nan)
    for i in range(M.shape[0]):
        row = M[i]
        if np.all(np.isnan(row)):
            continue
        rmin, rmax = np.nanmin(row), np.nanmax(row)
        Mnorm[i] = (row - rmin) / (rmax - rmin) if rmax > rmin else 0.5
    im = ax.imshow(Mnorm, aspect="auto", cmap="YlGnBu", vmin=0, vmax=1)

    ax.set_xticks(range(len(F_CANON)))
    ax.set_xticklabels([F_LABEL[f] for f in F_CANON], fontsize=11)
    ax.set_yticks(range(len(DUTIES)))
    ax.set_yticklabels([f"d={d}\n(fit×d={FIT*d:.2f})" for d in DUTIES], fontsize=10)
    ax.set_xlabel("overcommit factor  f  (tr ←→ default)", fontsize=12, fontweight="bold")
    ax.set_title("Table B — duty × f goodput(prog/s) 히트맵\n"
                 "각 행(duty) 최적 f는 항상 극단(빨강 테두리) → 내부 최적 없음 = 이진",
                 fontsize=13, fontweight="bold", pad=12)

    # annotate cells + highlight row-max with red border
    for i in range(len(DUTIES)):
        row = M[i]
        best_j = int(np.nanargmax(row)) if not np.all(np.isnan(row)) else -1
        for j in range(len(F_CANON)):
            if txt[i][j]:
                shade = Mnorm[i, j]
                tc = "white" if (not np.isnan(shade) and shade > 0.6) else "#222222"
                ax.text(j, i, txt[i][j], ha="center", va="center",
                        fontsize=10, color=tc,
                        fontweight="bold" if j == best_j else "normal")
            if j == best_j:
                ax.add_patch(plt.Rectangle((j-0.5, i-0.5), 1, 1, fill=False,
                                           edgecolor="#E53935", linewidth=3.5))

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("행별 정규화 goodput (0=최저, 1=최고)", fontsize=10)

    ax.text(0.5, -0.16,
            "빨강 = 각 duty행의 최고 goodput f.  d=0.1은 f=∞(default), d≥0.2는 f=1(tr).  "
            "중간 f(1.5·2)는 어느 행에서도 최고가 아님 → 최적은 이진(f=1 or f=∞).",
            transform=ax.transAxes, fontsize=9.5, ha="center", color="#333333",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#FFFDE7",
                      edgecolor="#FF9800"))
    fig.savefig(f"{BASE}/figures/step5_table_fgrid_yunuikang.png",
                dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("  wrote figures/step5_table_fgrid_yunuikang.png")


def markdown(data):
    lines = []
    lines.append("### STEP 5 확장 — Table A (극단: tr f=1 vs default f=∞, C=10, R=1)\n")
    lines.append("> goodput = completed/makespan (prog/s). 승자는 makespan(wall) 기준. "
                 "d=0.1 GPU0(재사용), d≥0.2 일부 GPU1 신규.\n")
    lines.append("| d | fit×d | tr goodput | tr p95 | tr hit | tr U% | tr fail | "
                 "def goodput | def p95 | def hit | def U% | def fail | 승자 |")
    lines.append("|---|-------|-----------|--------|--------|-------|---------|"
                 "------------|---------|---------|-------|----------|------|")
    for d in DUTIES:
        tr = data[d].get(1.0, {}); de = data[d].get(1e6, {})
        win = "?"
        if tr.get("wall_s") and de.get("wall_s"):
            if tr["wall_s"] < de["wall_s"]:
                win = f"**tr** (+{(de['wall_s']/tr['wall_s']-1)*100:.0f}%)"
            else:
                win = f"**default** (+{(tr['wall_s']/de['wall_s']-1)*100:.0f}%)"
        lines.append(
            f"| {d} | {FIT*d:.3f} | {fmt(tr.get('goodput'),'{:.3f}')} | "
            f"{fmt(tr.get('p95'),'{:.0f}')} | {fmt(tr.get('hit'),'{:.2f}')} | "
            f"{fmt(tr.get('U'),'{:.0f}')} | {fmt(tr.get('fail_rate'),'{:.0%}')} | "
            f"{fmt(de.get('goodput'),'{:.3f}')} | {fmt(de.get('p95'),'{:.0f}')} | "
            f"{fmt(de.get('hit'),'{:.2f}')} | {fmt(de.get('U'),'{:.0f}')} | "
            f"{fmt(de.get('fail_rate'),'{:.0%}')} | {win} |")

    lines.append("\n### STEP 5 확장 — Table B (전개: duty × f goodput, C=10, R=1)\n")
    lines.append("> goodput(prog/s). ★ = 각 행 최적 f. 최적이 항상 극단(f=1 or ∞) → 내부 최적 없음(이진).\n")
    lines.append("| d | fit×d | f=1 (tr) | f=1.5 | f=2 | f=∞ (default) | 최적 f |")
    lines.append("|---|-------|----------|-------|-----|---------------|--------|")
    for d in DUTIES:
        vals = {}
        for fc in F_CANON:
            m = data[d].get(fc)
            vals[fc] = m.get("goodput") if m else None
        best = max((fc for fc in F_CANON if vals[fc] is not None),
                   key=lambda fc: vals[fc], default=None)
        def mark(fc):
            v = vals[fc]
            if v is None:
                return "—"
            s = f"{v:.3f}"
            return f"**{s}★**" if fc == best else s
        best_lbl = {1.0: "f=1(tr)", 1.5: "f=1.5", 2.0: "f=2", 1e6: "f=∞(def)"}.get(best, "?")
        lines.append(f"| {d} | {FIT*d:.3f} | {mark(1.0)} | {mark(1.5)} | "
                     f"{mark(2.0)} | {mark(1e6)} | {best_lbl} |")

    out = f"{BASE}/scratch/step5/tables_2d.md"
    open(out, "w").write("\n".join(lines) + "\n")
    print(f"  wrote {out}")
    return "\n".join(lines)


def main():
    data = load()
    print("=== coverage ===")
    for d in DUTIES:
        present = sorted(data[d].keys())
        lbl = ["inf" if f > 1000 else f"{f:g}" for f in present]
        print(f"  d={d}: f={lbl}")
    table_a(data)
    table_b(data)
    md = markdown(data)
    print("\n" + md)


if __name__ == "__main__":
    main()
