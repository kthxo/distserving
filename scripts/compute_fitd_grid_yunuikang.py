#!/usr/bin/env python3
"""
STEP 2 — fit×d 격자 계산 + 쌍���선(money figure).  GPU 불필요(계산·플롯만).

질문: tr이 TraceLab에서 진 게 4090 특수현상이냐 일반 문제냐?
경계: fit��d < 1  ⇔  fit < NEED(=1/d)  →  스래싱 없이는 GPU가 놀아 idle↔recompute 트레이드오프가 산다.

★ v2 (2026-07-19): 검증 불가능한 추정 GPU 셀(A100·H100·8×H100) 제거.
  유지: 실측 3 GPU(4090·5090·Pro6000×2) × 실측 워크로드(SWE·TraceLab) + placeholder(HLE·Science).
  일반성 논증은 추정치 의존 제거 → 실측 3 GPU 다양성 + 구조적 근거 + STEP 4 합성 실증으로 뒷받침.

산출: scratch/step2/fitd_grid_yunuikang.csv, figures/step2_fitd_hyperbola_yunuikang.png

플랜: plans/2026-07-19_PLAN_overcommit-and-duty-tradeoff_yunuikang.md §2
근거: logs/2026-07-16_TP2_RESULTS_yunuikang.md(측정 C_total), logs/2026-07-17_VLLM_PROFILING_yunuikang.md(d)
작성: 강윤의 · 2026-07-19 (v2)
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "scratch/step2/fitd_grid_yunuikang.csv"
FIG = ROOT / "figures/step2_fitd_hyperbola_yunuikang.png"

# --------------------------------------------------------------------------
# 1. 모델 아키텍처 (로컬 config.json 실측; KV/tok = 2·layers·kv_heads·head_dim·dtype_bytes)
# --------------------------------------------------------------------------
def kv_bytes_per_token(layers, kv_heads, head_dim, dtype_bytes):
    return 2 * layers * kv_heads * head_dim * dtype_bytes

MODELS = {
    "Qwen3-8B":  (kv_bytes_per_token(36, 8, 128, 2), 16.4, "BF16, 36L/8KV/128"),   # 147,456 B
    "Qwen3-32B": (kv_bytes_per_token(64, 8, 128, 2), 65.6, "BF16, 64L/8KV/128"),   # 262,144 B
}

# --------------------------------------------------------------------------
# 2. GPU/모델 조합 — 실측 셀만 (미보유 GPU 제거)
# --------------------------------------------------------------------------
# (label, model, mem_total_GB, C_total_measured)
HW = [
    ("RTX 4090",         "Qwen3-8B",    24.0,   43888),   # 측정 (expC/D, mango1)
    ("RTX 5090",         "Qwen3-8B",    32.0,   89040),   # 측정 (goguma STEP1, gpu_util=0.92)
    ("Pro6000 x2 (TP2)", "Qwen3-32B",  192.0,  456944),   # 측정 (nutella1 P1, gpu_util=0.92)
]

# --------------------------------------------------------------------------
# 3. 워크로드 (d=duty, ctx=프로그램KV≈입력 median tok). 실측 + placeholder.
# --------------------------------------------------------------------------
WORKLOADS = [
    ("SWE",       7897,  {"*": 0.996},                                "measured"),
    ("TraceLab", 18684,  {"Qwen3-8B": 0.196, "Qwen3-32B": 0.289},   "measured"),
    ("HLE",       None,  {"*": None},  "placeholder: P3 24h 녹화→tool지연에서 산출 예정"),
    ("Science",   None,  {"*": None},  "placeholder: 데이터 blocker 미수집(보류)"),
]

def get_d(dmap, model):
    if model in dmap:
        return dmap[model]
    return dmap.get("*", None)

# --------------------------------------------------------------------------
# 4. 격자 조립
# --------------------------------------------------------------------------
rows = []
for label, model, mem, c_meas in HW:
    c_total = c_meas
    for wl, ctx, dmap, wstatus in WORKLOADS:
        d = get_d(dmap, model)
        if ctx is None or d is None:
            fit = R_cap = need = f_need = np.nan
            zone = "TBD"
        else:
            fit = c_total / ctx
            R_cap = fit * d
            need = 1.0 / d
            f_need = 1.0 / R_cap if R_cap > 0 else np.nan
            zone = "tradeoff(<1)" if R_cap < 1 else "tr-dominant(>=1)"
        rows.append(dict(
            gpu=label, model=model, mem_GB=mem,
            C_total_tok=c_total,
            C_total_src="measured",
            workload=wl, wl_status=wstatus,
            d=d, ctx_tok=ctx,
            fit=round(fit, 3) if not (isinstance(fit, float) and np.isnan(fit)) else np.nan,
            R_cap_fitxd=round(R_cap, 3) if not (isinstance(R_cap, float) and np.isnan(R_cap)) else np.nan,
            NEED_inv_d=round(need, 2) if not (isinstance(need, float) and np.isnan(need)) else np.nan,
            f_needed_sat=round(f_need, 2) if not (isinstance(f_need, float) and np.isnan(f_need)) else np.nan,
            zone=zone,
        ))

df = pd.DataFrame(rows)
CSV.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(CSV, index=False)
print(f"=== 격자 CSV 저장: {CSV}  ({len(df)} 행, 전부 실측 C_total) ===\n")

# --------------------------------------------------------------------------
# 5. 핵심 검증: 측정 4셀 정합 (fit×d ≷ 1 → 승패 100% 일치)
# --------------------------------------------------------------------------
print("=== ★ 실측 4셀 정합 (fit×d ≷ 1 → 승패 100% 일치) ===")
outcome = {
    ("RTX 4090","TraceLab"):        "tr 패(-34%)",
    ("RTX 4090","SWE"):             "tr 승(+78~84%)",
    ("Pro6000 x2 (TP2)","TraceLab"): "tr 승(+80~87%)",
    ("Pro6000 x2 (TP2)","SWE"):     "tr 승(+113%)",
}
four = df[df.workload.isin(["SWE","TraceLab"]) &
          df.gpu.isin(["RTX 4090","Pro6000 x2 (TP2)"])].copy()
for _, r in four.iterrows():
    oc = outcome.get((r.gpu, r.workload), "?")
    consistent = "✅" if ((r.R_cap_fitxd < 1) == ("패" in oc)) else "❌"
    print(f"  {r.gpu:18s} {r.workload:9s} fit={r.fit:6.2f} d={r.d:.3f} "
          f"fit×d={r.R_cap_fitxd:6.2f} f_sat={r.f_needed_sat:>5.2f} "
          f"[{r.zone:16s}] 실측:{oc:14s} {consistent}")

# 5090 (win/loss는 STEP 5에서 실측 예정 — 여기서는 C_total·fit×d만 보고)
print("\n=== 5090 셀 (C_total 실측, win/loss는 STEP 5에서) ===")
five = df[df.gpu == "RTX 5090"].dropna(subset=["R_cap_fitxd"])
for _, r in five.iterrows():
    print(f"  {r.gpu:18s} {r.workload:9s} fit={r.fit:6.2f} d={r.d:.3f} "
          f"fit×d={r.R_cap_fitxd:6.2f} f_sat={r.f_needed_sat:>5.2f} [{r.zone}]")

# --------------------------------------------------------------------------
# 6. 일반성 논증 (검증 가능한 근거로 재작성)
# --------------------------------------------------------------------------
print("\n=== 일반성 논증 (추정치 의존 제거, 검증 가능 근거만) ===")
print("""
(1) 실측 3 GPU × 2 워크로드에서 fit×d 부등호가 승패를 가름:
    - 4090/8B·TraceLab: fit×d=0.46 < 1 → tr 패  (유일한 패 = 유일한 <1)
    - 4090/8B·SWE:      fit×d=5.54 ≥ 1 → tr 승
    - Pro6000×2/32B·TraceLab: fit×d=7.07 ≥ 1 → tr 승
    - Pro6000×2/32B·SWE:      fit×d=57.6 ≥ 1 → tr 승
    - 5090/8B·TraceLab: fit×d=0.93 < 1 → STEP 5에서 검증 예정

(2) fit×d = (C_total/ctx) × d 공식 자체가 "GPU 브랜드가 아니라
    (KV예산 × 듀티 × 컨텍스트) 조합"이 영역을 결정함:
    - 같은 4090에서도 SWE(d=0.996)는 ≥1이고 TraceLab(d=0.196)은 <1.
    - 같은 TraceLab에서도 4090(KV=44k)은 <1이고 Pro6000(KV=457k)은 ≥1.
    → 영역 진입은 특정 GPU가 아니라 조합의 문제.

(3) STEP 4 저듀티 합성이 5090에서 깊은 zone 진입을 실증:
    - d=0.1 → fit×d≈0.48(깊은 zone). d=0.2 → fit×d≈0.93(경계).
    → 실측·합성 양쪽에서 일반성 뒷받침 (추정 불필요).
""")

# --------------------------------------------------------------------------
# 7. 머니 피겨 — (d, fit) 평면 + fit×d=1 쌍곡선
# --------------------------------------------------------------------------
plot = df.dropna(subset=["d", "fit"]).copy()

fig, ax = plt.subplots(figsize=(8.5, 6.0))

# fit x d = 1 hyperbola
dd = np.linspace(0.03, 1.02, 400)
ax.plot(dd, 1.0/dd, color="black", lw=2, zorder=5, label=r"$fit\times d = 1$  (boundary)")
ax.fill_between(dd, 0.1, 1.0/dd, color="#e8736a", alpha=0.14, zorder=0)
ax.fill_between(dd, 1.0/dd, 1e4, color="#5b8ff9", alpha=0.10, zorder=0)
ax.text(0.14, 1.6, "TRADEOFF zone\n(fit×d < 1: idle↔recompute)", fontsize=10.5,
        color="#b23b31", ha="left", va="center", zorder=6)
ax.text(0.72, 150, "tr-DOMINANT zone\n(fit×d ≥ 1)", fontsize=10.5,
        color="#2f5fbf", ha="center", va="center", zorder=6)

# 점: 모두 실측
for _, r in plot.iterrows():
    below = r.R_cap_fitxd < 1
    face = "#e8736a" if below else "#5b8ff9"
    # 4셀(win/loss 실측)은 별, 5090은 다이아(win/loss 미실측)
    if r.gpu in ["RTX 4090", "Pro6000 x2 (TP2)"]:
        marker, s = "*", 340
    else:
        marker, s = "D", 160
    ax.scatter(r.d, r.fit, marker=marker, s=s, edgecolor="black", lw=1.2,
               facecolor=face, zorder=12)
    lbl = f"{r.gpu.split(' (')[0]}/{r.workload}"
    ax.annotate(lbl, (r.d, r.fit), fontsize=7.5, xytext=(4, 4),
                textcoords="offset points", zorder=13)

# legend
from matplotlib.lines import Line2D
leg = [
    Line2D([0],[0], marker="*", color="w", markerfacecolor="gray", markeredgecolor="k",
           markersize=16, label="measured 4 cells (win/loss verified)"),
    Line2D([0],[0], marker="D", color="w", markerfacecolor="gray", markeredgecolor="k",
           markersize=10, label="5090 measured (STEP 5 pending)"),
    Line2D([0],[0], color="black", lw=2, label=r"$fit\times d=1$ boundary"),
    Line2D([0],[0], marker="s", color="w", markerfacecolor="#e8736a", markeredgecolor="k",
           markersize=11, label="fit×d < 1 (tradeoff)"),
    Line2D([0],[0], marker="s", color="w", markerfacecolor="#5b8ff9", markeredgecolor="k",
           markersize=11, label="fit×d ≥ 1 (tr-dominant)"),
]
ax.legend(handles=leg, loc="upper right", fontsize=8.5, framealpha=0.9)

ax.set_xscale("linear")
ax.set_yscale("log")
ax.set_xlim(0.05, 1.03)
ax.set_ylim(0.7, 700)
ax.set_xlabel("d  (duty = reasoning / (reasoning + tool))", fontsize=11.5)
ax.set_ylabel("fit  =  C_total / ctx   (max thrash-free residents, log)", fontsize=11.5)
ax.set_title("STEP 2 — fit×d boundary: tradeoff zone across 3 measured GPUs\n"
             "(all C_total measured; no estimated cells)", fontsize=10.5)
ax.grid(True, which="both", alpha=0.22)
fig.tight_layout()
FIG.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(FIG, dpi=140)
print(f"\n=== 쌍곡선 그림 저장: {FIG} ===")

# 요약
below = df[(df.R_cap_fitxd < 1)].dropna(subset=["R_cap_fitxd"])
print(f"\n=== fit×d<1 (트레이드오프 영역) 셀: {len(below)}개 (전부 실측) ===")
for _, r in below.iterrows():
    print(f"  {r.gpu:18s} {r.workload:9s} fit×d={r.R_cap_fitxd:5.2f}  (f_sat={r.f_needed_sat})")
