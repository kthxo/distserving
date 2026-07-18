#!/usr/bin/env python3
"""vLLM 내부 동작 검증 — expC 기존 JSONL/CSV 재분석 (GPU 0장).

산출:
  figures/vllm_timeline_tr_vs_default.png   실제 타임라인 (nrr / reasoning / acting)
  figures/vllm_U_triangulation.png          U 3종 측정 일치 검증 (Phase 4)
  figures/vllm_batch_refutes_H2.png         cond_nrr ≈ 1.2~1.45 → 배치 무료점심 반증
  figures/vllm_queries_inflation.png        prefix_cache_queries 재검사 오염 (Phase 1-2)
  figures/vllm_prefill_curve.png            cold(선형) vs warm(평탄) prefill (Phase 3)

근거 코드(vLLM 0.24.0):
  v1/core/sched/scheduler.py:673-712  waiting 요청은 num_computed_tokens==0이면 get_computed_blocks 호출
  v1/core/sched/scheduler.py:888-895  allocate 실패 시 break — pop_request(917) 전이라 큐에 남음
  v1/core/sched/scheduler.py:1141-43  num_computed_tokens는 '스케줄된' 요청만 전진
  → 미승인 waiting 요청이 매 step 재기록 → queries/hits 중복 계수
"""
import csv
import glob
import os

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import json

SCRATCH = "/home/yunuikang/yunuikang_work/scratch/expC"
FIG = "/home/yunuikang/yunuikang_work/distserving/figures"
os.makedirs(FIG, exist_ok=True)


def col(r, k):
    try:
        return float(r.get(k, ""))
    except (TypeError, ValueError):
        return np.nan


def load_sample(path):
    rows = list(csv.DictReader(open(path)))
    d = {k: np.array([col(r, k) for r in rows]) for k in rows[0]}
    res = d["b0_reasoning"] + d["b1_reasoning"] + d["b0_acting"] + d["b1_acting"]
    idx = np.where(res > 0)[0]
    sl = slice(idx[0], idx[-1] + 1) if len(idx) else slice(0, len(rows))
    return d, sl


def summarize(path):
    d, sl = load_sample(path)
    r0, r1 = d["b0_reasoning"][sl], d["b1_reasoning"][sl]
    a0, a1 = d["b0_acting"][sl], d["b1_acting"][sl]
    n0, n1 = d["b0_nrr"][sl], d["b1_nrr"][sl]
    g2, g3 = d["gpu2_util"][sl], d["gpu3_util"][sl]
    allnrr = np.concatenate([n0, n1])
    return dict(
        U_reas=(np.nanmean(r0 > 0) + np.nanmean(r1 > 0)) / 2,
        U_nrr=(np.nanmean(n0 > 0) + np.nanmean(n1 > 0)) / 2,
        smi=(np.nanmean(g2) + np.nanmean(g3)) / 2 / 100.0,
        mean_nrr=(np.nanmean(n0) + np.nanmean(n1)) / 2,
        cond_nrr=float(np.nanmean(allnrr[allnrr > 0])) if (allnrr > 0).any() else 0.0,
        k_fit=(np.nanmean(r0 + a0) + np.nanmean(r1 + a1)) / 2,
        mean_reas=(np.nanmean(r0) + np.nanmean(r1)) / 2,
    )


# ---------------------------------------------------------------- fig 1: timeline
def fig_timeline():
    pairs = [("sample_tr_ts1.0_c16.csv", "tr  (R=0.31 <1)"),
             ("sample_default_ts1.0_c16.csv", "default  (R=1.20 >1)")]
    fig, axes = plt.subplots(2, 1, figsize=(13, 6.4), sharex=True)
    for ax, (f, title) in zip(axes, pairs):
        d, sl = load_sample(os.path.join(SCRATCH, f))
        t = d["t"][sl] - d["t"][sl][0]
        nrr = d["b0_nrr"][sl] + d["b1_nrr"][sl]
        reas = d["b0_reasoning"][sl] + d["b1_reasoning"][sl]
        act = d["b0_acting"][sl] + d["b1_acting"][sl]
        pau = d["b0_paused"][sl] + d["b1_paused"][sl]
        ax.fill_between(t, 0, nrr, step="mid", color="#c0392b", alpha=.85,
                        label="vLLM num_requests_running (actual GPU batch, sum of 2 backends)")
        ax.plot(t, reas, color="#2e86ab", lw=.9, alpha=.9, label="proxy REASONING (dispatched)")
        ax.plot(t, act, color="#27ae60", lw=.9, alpha=.7, label="proxy ACTING (in tool, off-GPU)")
        if np.nanmax(pau) > 0:
            ax.plot(t, pau, color="#8e44ad", lw=1.0, alpha=.8, label="proxy PAUSED (proxy queue)")
        s = summarize(os.path.join(SCRATCH, f))
        ax.set_title(f"{title}   |  U(nrr>0)={s['U_nrr']:.2f}, mean nrr={s['mean_nrr']:.2f}, "
                     f"batch|busy={s['cond_nrr']:.2f}, k_fit={s['k_fit']:.2f}   (nrr/reasoning/acting stats are PER-BACKEND; curves show the 2-backend sum)", fontsize=9)
        ax.set_ylabel("count"); ax.grid(alpha=.25); ax.legend(fontsize=7, ncol=4, loc="upper right")
        ax.set_ylim(0, 17)
    axes[-1].set_xlabel("time (s)")
    fig.suptitle("Real vLLM timeline (expC, 2x4090, TraceLab C=16): the GPU fills along the TIME axis, not by larger BATCH",
                 fontsize=11.5)
    fig.tight_layout()
    p = f"{FIG}/vllm_timeline_tr_vs_default.png"
    fig.savefig(p, dpi=145); plt.close(fig); print("wrote", p)


# ------------------------------------------------- fig 2: U triangulation (Phase 4)
def fig_triangulation():
    files = sorted(glob.glob(f"{SCRATCH}/sample_*.csv"))
    lab, ur, un, sm = [], [], [], []
    for f in files:
        s = summarize(f)
        lab.append(os.path.basename(f)[7:-4].replace("_ts1.0", ""))
        ur.append(s["U_reas"]); un.append(s["U_nrr"]); sm.append(s["smi"])
    x = np.arange(len(lab))
    fig, ax = plt.subplots(1, 2, figsize=(13.5, 4.6))
    ax[0].bar(x - .25, ur, .25, label="U = proxy REASONING>0 (definition used by expC)", color="#2e86ab")
    ax[0].bar(x, un, .25, label="U = vLLM num_requests_running>0", color="#c0392b")
    ax[0].bar(x + .25, sm, .25, label="U = nvidia-smi util/100", color="#f39c12")
    ax[0].set_xticks(x); ax[0].set_xticklabels(lab, rotation=45, ha="right", fontsize=7)
    ax[0].set_ylabel("U"); ax[0].legend(fontsize=8); ax[0].grid(alpha=.25, axis="y")
    ax[0].set_title("Phase 4: three independent U measures agree -> U definition is sound", fontsize=10)

    ax[1].scatter(un, sm, c="#c0392b", s=45, label="nvidia-smi vs nrr>0")
    ax[1].scatter(un, ur, c="#2e86ab", s=45, marker="s", label="proxy REASONING>0 vs nrr>0")
    lims = [0, 1]
    ax[1].plot(lims, lims, "k--", lw=1, alpha=.6, label="y=x")
    r1 = np.corrcoef(un, sm)[0, 1]; r2 = np.corrcoef(un, ur)[0, 1]
    ax[1].set_xlabel("U (vLLM nrr>0)"); ax[1].set_ylabel("U (other measure)")
    ax[1].set_title(f"agreement: smi r={r1:.3f}, proxy r={r2:.3f}\n"
                    "util is NOT pinned at 100% -> the batch1=batch32=100% concern does not arise here", fontsize=10)
    ax[1].legend(fontsize=8); ax[1].grid(alpha=.25)
    fig.tight_layout(); p = f"{FIG}/vllm_U_triangulation.png"
    fig.savefig(p, dpi=145); plt.close(fig); print("wrote", p)


# ------------------------------------------------- fig 3: batch refutes H2
def fig_batch():
    files = sorted(glob.glob(f"{SCRATCH}/sample_*.csv"))
    lab, kfit, cond, mnrr = [], [], [], []
    for f in files:
        s = summarize(f)
        lab.append(os.path.basename(f)[7:-4].replace("_ts1.0", ""))
        kfit.append(s["k_fit"]); cond.append(s["cond_nrr"]); mnrr.append(s["mean_nrr"])
    x = np.arange(len(lab))
    fig, ax = plt.subplots(figsize=(12.5, 4.8))
    ax.bar(x - .2, kfit, .4, label="k_fit = proxy resident (reasoning+acting)", color="#95a5a6")
    ax.bar(x + .2, cond, .4, label="actual decode batch = mean nrr | nrr>0", color="#c0392b")
    ax.axhline(1.0, color="k", ls=":", lw=1)
    for i, c in enumerate(cond):
        ax.text(x[i] + .2, c + .12, f"{c:.2f}", ha="center", fontsize=7, color="#c0392b")
    ax.set_xticks(x); ax.set_xticklabels(lab, rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("count"); ax.legend(fontsize=9); ax.grid(alpha=.25, axis="y")
    ax.set_title("H2 (batching free lunch) REFUTED: even at k_fit=6-10 the real GPU batch stays 1.1-1.5\n"
                 "default did NOT buy batching. Most residents are ACTING (off-GPU) or queued inside vLLM.",
                 fontsize=10.5)
    fig.tight_layout(); p = f"{FIG}/vllm_batch_refutes_H2.png"
    fig.savefig(p, dpi=145); plt.close(fig); print("wrote", p)


# ------------------------------------------------- fig 4: queries inflation
def fig_inflation():
    out = {}
    for f, name in [(f"{SCRATCH}/expC_tr.jsonl", "tr"), (f"{SCRATCH}/expC_default.jsonl", "default")]:
        agg = {}
        for line in open(f):
            d = json.loads(line)
            c = d["concurrency"]
            q = d.get("prefix_cache_queries_delta", 0)
            pt = d.get("prompt_tokens_total_delta", 0)
            agg.setdefault(c, []).append((q, pt, d.get("prefix_cache_hit_rate", 0)))
        out[name] = {c: (np.mean([r[0] for r in v]), np.mean([r[1] for r in v]),
                         np.mean([r[2] for r in v])) for c, v in agg.items()}
    fig, ax = plt.subplots(1, 2, figsize=(12.5, 4.4))
    for name, color in [("tr", "#2e86ab"), ("default", "#c0392b")]:
        cs = sorted(out[name])
        infl = [out[name][c][0] / max(out[name][c][1], 1) for c in cs]
        hit = [out[name][c][2] for c in cs]
        ax[0].plot(cs, infl, "-o", color=color, label=name)
        ax[1].plot(infl, hit, "-o", color=color, label=name)
        for c, i, h in zip(cs, infl, hit):
            ax[0].annotate(f"C={c}", (c, i), fontsize=7)
            ax[1].annotate(f"C={c}", (i, h), fontsize=7)
    ax[0].axhline(1.0, color="k", ls=":", lw=1, label="=1 if uncontaminated")
    ax[0].set_xlabel("concurrency C"); ax[0].set_ylabel("queries / prompt_tokens_total")
    ax[0].set_xscale("log", base=2); ax[0].set_yscale("log")
    ax[0].set_title("prefix_cache_queries inflation factor\n(= times a request is re-examined at head of vLLM waiting queue)", fontsize=10)
    ax[0].legend(fontsize=8); ax[0].grid(alpha=.25, which="both")
    ax[1].set_xlabel("inflation factor (re-examinations)"); ax[1].set_ylabel("reported hit rate")
    ax[1].set_xscale("log")
    ax[1].set_title("reported hit rate collapses together with inflation\n-> the hit metric is confounded by queue waiting", fontsize=10)
    ax[1].legend(fontsize=8); ax[1].grid(alpha=.25, which="both")
    fig.tight_layout(); p = f"{FIG}/vllm_queries_inflation.png"
    fig.savefig(p, dpi=145); plt.close(fig); print("wrote", p)


# ------------------------------------------------- fig 5: prefill curve
def fig_prefill():
    rows = list(csv.DictReader(open(f"{SCRATCH}/prof_duty/step_profiles.csv")))
    sid = np.array([int(r["step_id"]) for r in rows])
    pt = np.array([float(r["prompt_tokens"]) for r in rows])
    pf = np.array([float(r["prefill_s"]) for r in rows])
    cold, warm = sid == 1, sid > 1
    fig, ax = plt.subplots(figsize=(7.6, 5.2))
    ax.scatter(pt[cold], pf[cold], c="#c0392b", s=45, label="cold (step 1, no cache)")
    ax.scatter(pt[warm], pf[warm], c="#2e86ab", s=28, alpha=.75, label="warm (step>1, prefix hit)")
    A = np.polyfit(pt[cold], pf[cold], 1)
    r = np.corrcoef(pt[cold], pf[cold])[0, 1]
    xs = np.linspace(0, pt.max(), 50)
    ax.plot(xs, np.polyval(A, xs), "--", color="#c0392b", lw=1.4,
            label=f"cold linear fit r2={r*r:.3f}\n-> {1/A[0]:.0f} tok/s (compute-bound)")
    ax.axhline(pf[warm].mean(), color="#2e86ab", ls=":", lw=1.4,
               label=f"warm mean {pf[warm].mean():.2f}s (flat, r2=0.05)")
    ax.set_xlabel("prompt tokens"); ax.set_ylabel("TTFT / prefill_s (s)")
    ax.set_title("Phase 3: prefill cost curve (c=1 duty profile, 4090 Qwen3-8B)\n"
                 f"marginal cost of one full cache miss ~ {18684/(1/A[0]):.2f}s - {pf[warm].mean():.2f}s ~ "
                 f"{18684/(1/A[0]) - pf[warm].mean():.2f}s / turn", fontsize=10.5)
    ax.legend(fontsize=8); ax.grid(alpha=.25)
    fig.tight_layout(); p = f"{FIG}/vllm_prefill_curve.png"
    fig.savefig(p, dpi=145); plt.close(fig); print("wrote", p)


if __name__ == "__main__":
    fig_timeline(); fig_triangulation(); fig_batch(); fig_inflation(); fig_prefill()
    print("\n=== 요약 표 ===")
    print(f"{'run':<26}{'k_fit':>7}{'R=k·d':>8}{'mean_nrr':>9}{'U_nrr':>7}{'batch':>7}")
    for f in sorted(glob.glob(f"{SCRATCH}/sample_*.csv")):
        s = summarize(f)
        R = s["k_fit"] * 0.196
        print(f"{os.path.basename(f)[7:-4][:25]:<26}{s['k_fit']:>7.2f}{R:>8.2f}"
              f"{s['mean_nrr']:>9.2f}{s['U_nrr']:>7.3f}{s['cond_nrr']:>7.2f}")
