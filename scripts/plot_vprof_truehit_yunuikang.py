#!/usr/bin/env python3
"""마이크로벤치 결과 분석 — 참 hit vs 보고 hit, 부하 하 latency 분해.

  figures/vllm_true_vs_reported_hit.png
  figures/vllm_latency_breakdown_loaded.png
"""
import csv
import json
import os

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

VP = "/home/yunuikang/yunuikang_work/scratch/vprof"
FIG = "/home/yunuikang/yunuikang_work/distserving/figures"

rows = [json.loads(l) for l in open(f"{VP}/vprof_metrics_fixed.jsonl")]
by = {r["label"]: r for r in rows}
order = [k for k in ["tr_c16", "default_c16"] if k in by]


def prof(router):
    p = f"{VP}/fx_prof_{router}/step_profiles.csv"
    if not os.path.exists(p):
        return None
    rs = list(csv.DictReader(open(p)))
    if not rs:
        return None
    g = lambda k: np.array([float(r[k]) for r in rs])
    return dict(n=len(rs), prefill=g("prefill_s"), decode=g("decode_s"),
                pause=g("pause_s"), tool=g("tool_call_s"))


# ---------------------------------------------- fig A: true vs reported hit
def fig_hit():
    fig, ax = plt.subplots(1, 2, figsize=(12.2, 4.6))
    labs = [l.replace("_c16", "") for l in order]
    x = np.arange(len(order))
    true = [by[l]["TRUE_hit_rate"] for l in order]
    rep = [by[l]["REPORTED_hit_rate"] for l in order]
    infl = [by[l]["queries_inflation"] for l in order]

    ax[0].bar(x - .21, true, .38, color="#1e8a5a",
              label="TRUE hit = prompt_tokens_cached / prompt_tokens_total\n(no re-examination contamination)")
    ax[0].bar(x + .21, rep, .38, color="#c0392b",
              label="REPORTED hit = prefix_cache_hits / queries\n(the metric we have been using - contaminated)")
    for i, (t, r) in enumerate(zip(true, rep)):
        ax[0].text(x[i] - .21, t + .012, f"{t:.3f}", ha="center", fontsize=10, weight="bold", color="#1e8a5a")
        ax[0].text(x[i] + .21, r + .012, f"{r:.3f}", ha="center", fontsize=10, weight="bold", color="#c0392b")
        ax[0].annotate((f"{t/r:.1f}x understated" if t/r>1.02 else "accurate (1.0x)"), (x[i], max(t, r) + .075), ha="center",
                       fontsize=9.5, weight="bold", color="#2c3e50")
    ax[0].set_xticks(x); ax[0].set_xticklabels(labs, fontsize=12)
    ax[0].set_ylabel("hit rate"); ax[0].legend(fontsize=8, loc="upper right")
    ax[0].grid(alpha=.25, axis="y"); ax[0].set_ylim(0, max(true + rep) * 1.55)
    ax[0].set_title("TRUE vs REPORTED hit rate  (measured, C=16, NPROG=32)", fontsize=11)

    ax[1].bar(x, infl, .45, color="#e67e22")
    for i, v in enumerate(infl):
        ax[1].text(x[i], v + .4, f"{v:.1f}x", ha="center", fontsize=11, weight="bold", color="#e67e22")
    ax[1].axhline(1.0, color="k", ls=":", lw=1.2, label="=1 if uncontaminated")
    ax[1].set_xticks(x); ax[1].set_xticklabels(labs, fontsize=12)
    ax[1].set_ylabel("prefix_cache_queries / prompt_tokens_total")
    ax[1].set_title("queries inflation = re-examinations at vLLM waiting-queue head\n"
                    "(scheduler.py:888-895 break before pop_request:917)", fontsize=10)
    ax[1].legend(fontsize=9); ax[1].grid(alpha=.25, axis="y")
    fig.suptitle("vLLM V1 re-counts rejected waiting requests every step -> our hit metric UNDERSTATES the true hit rate",
                 fontsize=12, weight="bold")
    fig.tight_layout()
    p = f"{FIG}/vllm_true_vs_reported_hit.png"
    fig.savefig(p, dpi=150); plt.close(fig); print("wrote", p)


# ---------------------------------------------- fig B: loaded latency breakdown
def fig_latency():
    data = {}
    for l in order:
        r = l.replace("_c16", "")
        pr = prof(r)
        if pr:
            data[r] = pr
    if not data:
        print("no profiles"); return
    fig, ax = plt.subplots(figsize=(9.6, 5.0))
    labs = list(data)
    x = np.arange(len(labs))
    keys = [("pause", "#8e44ad", "pause_s (proxy queue)"),
            ("prefill", "#c0392b", "prefill_s = TTFT (includes vLLM queue wait!)"),
            ("decode", "#2980b9", "decode_s"),
            ("tool", "#27ae60", "tool_call_s")]
    bottom = np.zeros(len(labs))
    for k, c, lab in keys:
        vals = np.array([data[l][k].mean() for l in labs])
        ax.bar(x, vals, .5, bottom=bottom, color=c, label=lab)
        for i, v in enumerate(vals):
            if v > 0.4:
                ax.text(x[i], bottom[i] + v / 2, f"{v:.1f}s", ha="center", va="center",
                        fontsize=10, color="white", weight="bold")
        bottom += vals
    for i, b in enumerate(bottom):
        ax.text(x[i], b + .25, f"total {b:.1f}s", ha="center", fontsize=10.5, weight="bold")
    ax.set_xticks(x); ax.set_xticklabels([f"{l}\n(n={data[l]['n']} steps)" for l in labs], fontsize=11)
    ax.set_ylabel("mean seconds per step")
    ax.legend(fontsize=9); ax.grid(alpha=.25, axis="y")
    ax.set_title("Loaded step-time breakdown (--stream restored prefill_s)\n"
                 "tr queues in the PROXY (pause_s); default queues INSIDE vLLM (hidden in TTFT)",
                 fontsize=11.5)
    fig.tight_layout()
    p = f"{FIG}/vllm_latency_breakdown_loaded.png"
    fig.savefig(p, dpi=150); plt.close(fig); print("wrote", p)


def summary():
    print("\n=============== 마이크로벤치 요약 ===============")
    print(f"{'run':<12}{'TRUE hit':>10}{'REP hit':>9}{'배수':>7}{'infl':>7}{'recompute tok':>15}{'preempt':>9}{'wall':>7}")
    for l in order:
        d = by[l]
        print(f"{l:<12}{d['TRUE_hit_rate']:>10.4f}{d['REPORTED_hit_rate']:>9.4f}"
              f"{d['TRUE_hit_rate']/d['REPORTED_hit_rate']:>7.2f}{d['queries_inflation']:>7.1f}"
              f"{d['TRUE_recompute_tokens']:>15,.0f}{d['num_preemptions']:>9.0f}{d['wall_s']:>7.0f}")
    print("\n불변식 compute+cached==total:", {l: by[l]["invariant_ok"] for l in order})
    print("\n--- 부하 하 step 분해 (mean s) ---")
    print(f"{'run':<10}{'pause':>8}{'prefill':>9}{'decode':>8}{'tool':>7}{'total':>8}{'n':>6}")
    for l in order:
        r = l.replace("_c16", ""); pr = prof(r)
        if pr:
            tot = pr['pause'].mean() + pr['prefill'].mean() + pr['decode'].mean() + pr['tool'].mean()
            print(f"{r:<10}{pr['pause'].mean():>8.2f}{pr['prefill'].mean():>9.2f}"
                  f"{pr['decode'].mean():>8.2f}{pr['tool'].mean():>7.2f}{tot:>8.2f}{pr['n']:>6}")


if __name__ == "__main__":
    fig_hit(); fig_latency(); summary()
