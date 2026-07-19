#!/usr/bin/env python3
"""
STEP 2 — fit×d 격자 계산 + 쌍곡선(money figure).  GPU 불필요(계산·플롯만).

질문: tr이 TraceLab에서 진 게 4090 특수현상이냐 일반 문제냐?
경계: fit×d < 1  ⇔  fit < NEED(=1/d)  →  스래싱 없이는 GPU가 놀아 idle↔recompute 트레이드오프가 산다.

- C_total 추정식: (mem_total_GB × EFF − weights_GB) × 1e9 / kv_bytes_per_token
  EFF(유효 사용률)는 측정 2셀(4090/8B=43,888 tok, Pro6000×2/32B=456,944 tok)로 검산·보정.
- 워크로드 HLE·Science는 placeholder(NaN) 행으로 포함.
- 산출: scratch/step2/fitd_grid_yunuikang.csv, figures/step2_fitd_hyperbola_yunuikang.png

플랜: plans/2026-07-19_PLAN_overcommit-and-duty-tradeoff_yunuikang.md §2
근거: logs/2026-07-16_TP2_RESULTS_yunuikang.md(측정 C_total), logs/2026-07-17_VLLM_PROFILING_yunuikang.md(d)
작성: 강윤의 · 2026-07-19
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
    # name:            (KV bytes/tok,                         weights_GB,  note)
    "Qwen3-8B":  (kv_bytes_per_token(36, 8, 128, 2), 16.4, "BF16, 36L/8KV/128"),   # 147,456 B
    "Qwen3-32B": (kv_bytes_per_token(64, 8, 128, 2), 65.6, "BF16, 64L/8KV/128"),   # 262,144 B
    # 8×H100 논문 케이스 — MoE·FP8, 아키텍처 근사 → [ROUGH] 표기
    "Qwen3-235B(MoE,FP8)": (kv_bytes_per_token(94, 4, 128, 2), 235.0, "ROUGH: MoE/FP8, 94L/4KV/128"),  # 385,024 B
}

# --------------------------------------------------------------------------
# 2. GPU/모델 조합 (mem_total_GB 은 TP 합산). 측정셀은 C_total_measured 로 고정.
# --------------------------------------------------------------------------
# (label, model, mem_total_GB, C_total_measured or None)
HW = [
    ("RTX 4090",         "Qwen3-8B",             24.0,  43888),    # 측정 (expC/D)
    ("RTX 5090",         "Qwen3-8B",             32.0,  89040),    # 측정 (goguma STEP1, gpu_util=0.92)
    ("Pro6000 x1",       "Qwen3-32B",            96.0,  None),
    ("Pro6000 x2 (TP2)", "Qwen3-32B",           192.0,  456944),   # 측정 (P1)
    ("A100-80G",         "Qwen3-32B",            80.0,  None),
    ("H100-80G",         "Qwen3-32B",            80.0,  None),
    ("8xH100-640G",      "Qwen3-235B(MoE,FP8)", 640.0,  None),     # 논문, [ROUGH]
]

# --------------------------------------------------------------------------
# 3. EFF 보정 — 측정 2셀로 유효 사용률 산출
#    usable_KV_GB = mem×EFF − weights  →  EFF = (KV_GB + weights)/mem
# --------------------------------------------------------------------------
def c_total_to_kv_gb(c_total, kv_bpt):
    return c_total * kv_bpt / 1e9

cal = []
for label, model, mem, c_meas in HW:
    if c_meas is None:
        continue
    kv_bpt, w_gb, _ = MODELS[model]
    kv_gb = c_total_to_kv_gb(c_meas, kv_bpt)
    eff = (kv_gb + w_gb) / mem
    cal.append((label, model, c_meas, kv_gb, eff))

EFF = float(np.mean([e for *_, e in cal]))

print("=== EFF 보정 (측정 2셀) ===")
for label, model, c_meas, kv_gb, eff in cal:
    print(f"  {label:20s} {model:22s} C_total={c_meas:>8,} → KV={kv_gb:6.2f}GB  EFF={eff:.4f}")
print(f"  → 채택 EFF(평균) = {EFF:.4f}\n")

def est_c_total(mem, model):
    kv_bpt, w_gb, _ = MODELS[model]
    usable_kv_gb = mem * EFF - w_gb
    if usable_kv_gb <= 0:
        return np.nan
    return usable_kv_gb * 1e9 / kv_bpt

# 검산: 측정셀 재현 잔차
print("=== 검산 (추정식으로 측정셀 재현) ===")
for label, model, mem, c_meas in HW:
    if c_meas is None:
        continue
    c_est = est_c_total(mem, model)
    err = (c_est - c_meas) / c_meas * 100
    print(f"  {label:20s} 측정={c_meas:>8,}  추정={c_est:>10,.0f}  잔차={err:+.1f}%")
print()

# --------------------------------------------------------------------------
# 4. 워크로드 (d=duty, ctx=프로그램KV≈입력 median tok). 측정/placeholder 구분.
# --------------------------------------------------------------------------
# name: (ctx_tok, d_by_model{model:d} or d_scalar, status)
WORKLOADS = [
    ("SWE",            7897,  {"*": 0.996},               "measured"),
    ("TraceLab",      18684,  {"Qwen3-8B": 0.196,
                               "Qwen3-32B": 0.289,
                               "Qwen3-235B(MoE,FP8)": 0.289},  "measured"),
    ("HLE",            None,  {"*": None},                "placeholder: P3 24h 녹화 tool지연에서 산출 예정(수집중)"),
    ("Science",        None,  {"*": None},                "placeholder: 데이터 blocker 미수집(보류)"),
    ("deep-research류", 64000, {"*": 0.10},               "assumed-class: 저듀티·롱컨텍스트"),
    ("longctx-generic",32000, {"*": 0.15},                "assumed-class: 롱컨텍스트"),
]

def get_d(dmap, model):
    if model in dmap:
        return dmap[model]
    return dmap.get("*", None)

# --------------------------------------------------------------------------
# 5. 격자 조립
# --------------------------------------------------------------------------
rows = []
for label, model, mem, c_meas in HW:
    c_total = c_meas if c_meas is not None else est_c_total(mem, model)
    c_src = "measured" if c_meas is not None else "estimated"
    rough = "ROUGH" in MODELS[model][2]
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
            C_total_tok=round(c_total) if not np.isnan(c_total) else np.nan,
            C_total_src=c_src, rough=rough,
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
print(f"=== 격자 CSV 저장: {CSV}  ({len(df)} 행) ===\n")

# 4셀 정합 재확인 표 + f_needed 열
print("=== 4셀 정합 검증 (측정치) + 포화 필요 f=1/R_cap ===")
four = df[((df.gpu == "RTX 4090") | (df.gpu == "Pro6000 x2 (TP2)")) &
          (df.workload.isin(["SWE", "TraceLab"]))].copy()
outcome = {("RTX 4090","TraceLab"):"tr 패(-34%)", ("RTX 4090","SWE"):"tr 승(+78~84%)",
           ("Pro6000 x2 (TP2)","TraceLab"):"tr 승(+80~87%)", ("Pro6000 x2 (TP2)","SWE"):"tr 승(+113%)"}
for _, r in four.iterrows():
    oc = outcome.get((r.gpu, r.workload), "?")
    consistent = "✅" if ((r.R_cap_fitxd < 1) == ("패" in oc)) else "❌"
    print(f"  {r.gpu:18s} {r.workload:9s} fit={r.fit:6.2f} d={r.d:.3f} "
          f"fit×d={r.R_cap_fitxd:6.2f} f_sat={r.f_needed_sat if not np.isnan(r.f_needed_sat) else float('nan'):>5} "
          f"[{r.zone:16s}] 실측:{oc:14s} {consistent}")
print()

# --------------------------------------------------------------------------
# 6. 머니 피겨 — (d, fit) 평면 + fit×d=1 쌍곡선
# --------------------------------------------------------------------------
plot = df.dropna(subset=["d", "fit"]).copy()

fig, ax = plt.subplots(figsize=(9.2, 6.6))

# fit x d = 1 hyperbola
dd = np.linspace(0.03, 1.02, 400)
ax.plot(dd, 1.0/dd, color="black", lw=2, zorder=5, label=r"$fit\times d = 1$  (boundary)")
ax.fill_between(dd, 0.1, 1.0/dd, color="#e8736a", alpha=0.14, zorder=0)   # below = tradeoff
ax.fill_between(dd, 1.0/dd, 1e4, color="#5b8ff9", alpha=0.10, zorder=0)   # above = tr-dominant
ax.text(0.14, 1.6, "TRADEOFF zone\n(fit x d < 1: idle<->recompute)", fontsize=10.5,
        color="#b23b31", ha="left", va="center", zorder=6)
ax.text(0.72, 220, "tr-DOMINANT zone\n(fit x d >= 1)", fontsize=10.5,
        color="#2f5fbf", ha="center", va="center", zorder=6)

# 점: 측정 vs 추정 vs assumed, 트레이드오프 여부로 색
def style(r):
    below = r.R_cap_fitxd < 1
    face = "#e8736a" if below else "#5b8ff9"
    if r.wl_status.startswith("measured") and r.C_total_src == "measured":
        return dict(marker="*", s=340, edgecolor="black", lw=1.4, facecolor=face, zorder=12)
    if r.wl_status.startswith("assumed"):
        return dict(marker="^", s=120, edgecolor="black", lw=0.8, facecolor=face, zorder=10)
    return dict(marker="o", s=95, edgecolor="black", lw=0.8, facecolor=face, zorder=10)

WL_ASCII = {"deep-research류": "deep-research", "longctx-generic": "longctx"}
for _, r in plot.iterrows():
    st = style(r)
    ax.scatter(r.d, r.fit, **st)
    wl = WL_ASCII.get(r.workload, r.workload)
    lbl = f"{r.gpu.split(' (')[0].replace('-80G','')}-{wl}"
    if "ROUGH" in str(r.model) or r.rough:
        lbl += " [rough]"
    ax.annotate(lbl, (r.d, r.fit), fontsize=6.6, xytext=(4, 3),
                textcoords="offset points", zorder=13)

# legend (manual)
from matplotlib.lines import Line2D
leg = [
    Line2D([0],[0], marker="*", color="w", markerfacecolor="gray", markeredgecolor="k",
           markersize=17, label="measured cells (4)"),
    Line2D([0],[0], marker="o", color="w", markerfacecolor="gray", markeredgecolor="k",
           markersize=9, label="estimated grid"),
    Line2D([0],[0], marker="^", color="w", markerfacecolor="gray", markeredgecolor="k",
           markersize=10, label="assumed workload class"),
    Line2D([0],[0], color="black", lw=2, label=r"$fit\times d=1$ boundary"),
]
leg_colors = [
    Line2D([0],[0], marker="s", color="w", markerfacecolor="#e8736a", markeredgecolor="k",
           markersize=11, label="fit x d < 1 (tradeoff)"),
    Line2D([0],[0], marker="s", color="w", markerfacecolor="#5b8ff9", markeredgecolor="k",
           markersize=11, label="fit x d >= 1 (tr-dominant)"),
]
first = ax.legend(handles=leg, loc="upper right", fontsize=8.5, framealpha=0.9)
ax.add_artist(first)
ax.legend(handles=leg_colors, loc="lower left", fontsize=8.5, framealpha=0.9)

ax.set_xscale("linear")
ax.set_yscale("log")
ax.set_xlim(0.05, 1.03)
ax.set_ylim(0.7, 3000)
ax.set_xlabel("d  (duty = reasoning / (reasoning + tool))", fontsize=11.5)
ax.set_ylabel("fit  =  C_total / ctx   (max thrash-free residents, log)", fontsize=11.5)
ax.set_title("STEP 2 - fit x d boundary: the tradeoff zone is NOT 4090-specific\n"
             "(star = measured 4 cells, circle = estimated grid, triangle = assumed low-duty/long-ctx)",
             fontsize=11)
ax.grid(True, which="both", alpha=0.22)
fig.tight_layout()
FIG.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(FIG, dpi=140)
print(f"=== 쌍곡선 그림 저장: {FIG} ===")

# 요약: 트레이드오프 영역에 든 셀
below = df[(df.R_cap_fitxd < 1)].dropna(subset=["R_cap_fitxd"])
print(f"\n=== fit×d<1 (트레이드오프 영역) 셀: {len(below)}개 ===")
for _, r in below.iterrows():
    print(f"  {r.gpu:18s} {r.workload:16s} fit×d={r.R_cap_fitxd:5.2f}  (f_sat={r.f_needed_sat})")
