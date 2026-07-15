#!/usr/bin/env python3
"""조사 B — 용량 논의를 '메모리 지표'로 재정렬 (재프리필은 보조).

기존 결과 JSONL(F=homo_hetero, G=hetero_hetero, D=hetero_homo_tracelab)에서
백엔드별 kv_cache_usage_perc(포화도) · pause peak · split · (보조)재프리필을 뽑아
"용량 초과→(tr)pause로 resident 억제 / (default)재프리필 폭증"을 메모리 지표로 그린다.

새 GPU 실행 없음 — 순수 재분석. 출력: figures/deepB_*.png
"""
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SCRATCH = Path("/home/yunuikang/yunuikang_work/scratch")
FIG = Path("/home/yunuikang/yunuikang_work/distserving/figures")
FIG.mkdir(exist_ok=True)

CAP_4090 = 43888
CAP_5090 = 89040
CAP_RATIO_5_TO_4 = CAP_5090 / CAP_4090  # ~2.03


def load(name):
    return [json.loads(l) for l in (SCRATCH / name).read_text().splitlines() if l.strip()]


def mean(xs):
    xs = [x for x in xs if x is not None]
    return st.mean(xs) if xs else 0.0


# ---------------------------------------------------------------------------
# F / G : run_hetero_sweep schema (per_backend kv_usage_peak/mean, paused_peak, queries)
# ---------------------------------------------------------------------------
def agg_hetero(name):
    """Return {conc: {backend: {kv_peak, kv_mean, paused, hit, queries}}} averaged over repeats."""
    rows = load(name)
    by_c = defaultdict(lambda: defaultdict(list))
    for r in rows:
        c = r["concurrency"]
        for b, pb in r["per_backend"].items():
            by_c[c][b].append(pb)
    out = {}
    for c, bd in by_c.items():
        out[c] = {}
        for b, lst in bd.items():
            out[c][b] = {
                "kv_peak": mean([x.get("kv_usage_peak") for x in lst]),
                "kv_mean": mean([x.get("kv_usage_mean") for x in lst]),
                "paused": mean([x.get("paused_peak") for x in lst]),
                "hit": mean([x.get("hit_rate") for x in lst]),
                "queries": mean([x.get("queries_delta") for x in lst]),
            }
    return dict(sorted(out.items()))


def plot_kv_usage(tag, tr, dflt, title):
    """Per-backend KV usage peak vs concurrency — the direct memory-pressure metric."""
    concs = sorted(tr.keys())
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    styles = {"4090": dict(color="#d1495b"), "5090": dict(color="#2e86ab")}
    for b in ["4090", "5090"]:
        ax.plot(concs, [tr[c][b]["kv_peak"] for c in concs], "-o",
                label=f"tr {b}", **styles[b])
        ax.plot(concs, [dflt[c][b]["kv_peak"] for c in concs], "--x",
                label=f"default {b}", **styles[b], alpha=0.55)
    ax.axhline(1.0, color="gray", ls=":", lw=1)
    ax.set_xlabel("concurrency (offered)")
    ax.set_ylabel("KV cache usage (peak fraction of pool)")
    ax.set_title(title)
    ax.set_ylim(0, 1.05)
    ax.legend(fontsize=8, ncol=2)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p = FIG / f"deepB_{tag}_kv_usage_peak.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return p


def plot_pause(tag, tr, dflt, title):
    """Per-backend pause peak — tr's memory-control action (default never pauses)."""
    concs = sorted(tr.keys())
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    for b, col in [("4090", "#d1495b"), ("5090", "#2e86ab")]:
        ax.plot(concs, [tr[c][b]["paused"] for c in concs], "-o", color=col, label=f"tr {b}")
        ax.plot(concs, [dflt[c][b]["paused"] for c in concs], "--x", color=col, alpha=0.55,
                label=f"default {b}")
    ax.set_xlabel("concurrency (offered)")
    ax.set_ylabel("paused programs (peak)")
    ax.set_title(title)
    ax.legend(fontsize=8, ncol=2)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p = FIG / f"deepB_{tag}_pause_peak.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return p


def plot_split_vs_capacity(tag, tr, title):
    """tr's actual routing split (queries proxy) vs the true capacity ratio 1:2.03."""
    concs = sorted(tr.keys())
    frac5090 = []  # fraction of queries going to 5090
    for c in concs:
        q4 = tr[c]["4090"]["queries"]
        q5 = tr[c]["5090"]["queries"]
        frac5090.append(q5 / (q4 + q5) if (q4 + q5) else 0)
    cap_frac5090 = CAP_5090 / (CAP_4090 + CAP_5090)  # ~0.67
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.plot(concs, frac5090, "-o", color="#2e86ab", label="tr actual → 5090 (queries share)")
    ax.axhline(cap_frac5090, color="#e08e0b", ls="--", lw=1.5,
               label=f"capacity-proportional → 5090 = {cap_frac5090:.2f}")
    ax.axhline(0.5, color="gray", ls=":", lw=1, label="equal split = 0.50")
    ax.set_xlabel("concurrency (offered)")
    ax.set_ylabel("fraction routed to 5090")
    ax.set_title(title)
    ax.set_ylim(0, 0.8)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p = FIG / f"deepB_{tag}_split_vs_capacity.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return p


# ---------------------------------------------------------------------------
# D : hetero_homo_tracelab schema (global only) — reprefill(secondary) + hit
# ---------------------------------------------------------------------------
def agg_D(name):
    rows = load(name)
    by_c = defaultdict(list)
    for r in rows:
        by_c[r["concurrency"]].append(r)
    out = {}
    for c, lst in sorted(by_c.items()):
        # ★ TRUE reprefill (recompute) = queries - hits = missed prefix-cache tokens.
        #   prompt_tokens_total is the logical prompt total (flat, cache-agnostic) → NOT reprefill.
        miss = [r.get("prefix_cache_queries_delta", 0) - r.get("prefix_cache_hits_delta", 0) for r in lst]
        out[c] = {
            "reprefill_miss": mean(miss),                                   # queries - hits (true)
            "prompt_total": mean([r.get("prompt_tokens_total_delta") for r in lst]),  # flat baseline
            "hit": mean([r.get("prefix_cache_hit_rate") for r in lst]),
            "preempt": mean([r.get("num_preemptions_delta") for r in lst]),
            "thru": mean([r.get("throughput_programs_per_s") for r in lst]),
        }
    return out


def plot_D_reprefill(tr, dflt):
    """D (2x4090 real): reprefill REDEFINED as MISS RATE = 1 - hit_rate (robust, unitless).

    Rationale: prompt_tokens_total is flat (~7.3M, cache-agnostic) → NOT reprefill.
    The absolute miss-token count (queries-hits) is unreliable because vLLM V1's
    prefix_cache_queries counter is a different granularity than prompt_tokens
    (queries≈222M >> prompt≈7M cannot be reconciled 1:1). So we use the miss RATE,
    which is exactly 1 - hit_rate and is the robust recompute-pressure signal."""
    concs = sorted(tr.keys())
    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    ax.plot(concs, [1 - dflt[c]["hit"] for c in concs], "--x", color="#d1495b",
            label="default miss rate = 1 − hit")
    ax.plot(concs, [1 - tr[c]["hit"] for c in concs], "-o", color="#3a7d44",
            label="tr miss rate = 1 − hit")
    ax.set_xlabel("concurrency (offered)")
    ax.set_ylabel("prefix-cache MISS rate  (fraction recomputed)")
    ax.set_title("D (real trace, 2x4090): reprefill = MISS RATE (1 − hit)\n"
                 "default 0.18→0.97 (thrash) vs tr flat ~0.20-0.23. preemptions≈0\n"
                 "→ misses are prefix-cache eviction, not vLLM CPU swap. prompt_tokens_total flat = wrong proxy.")
    ax.set_ylim(0, 1.0)
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p = FIG / "deepB_D_missrate.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return p


def main():
    made = []
    # F = homo_hetero (synthetic, 4090+5090)
    f_tr, f_df = agg_hetero("homo_hetero_tr.jsonl"), agg_hetero("homo_hetero_default.jsonl")
    made.append(plot_kv_usage("F", f_tr, f_df,
                "F (synthetic, 4090+5090): KV usage — default 4090 saturates, tr balanced"))
    made.append(plot_pause("F", f_tr, f_df,
                "F: pause peak — tr controls memory via pause, default never pauses"))
    made.append(plot_split_vs_capacity("F", f_tr,
                "F: tr routes ~1:1.6, below capacity-proportional → 5090 under-used"))

    # G = hetero_hetero (real trace, 4090+5090)
    g_tr, g_df = agg_hetero("hetero_hetero_tr.jsonl"), agg_hetero("hetero_hetero_default.jsonl")
    made.append(plot_kv_usage("G", g_tr, g_df,
                "G (real trace, 4090+5090): KV usage — default 4090 saturates, tr balanced"))
    made.append(plot_pause("G", g_tr, g_df,
                "G: pause peak — tr's memory control vs default"))
    made.append(plot_split_vs_capacity("G", g_tr,
                "G: tr routes ~1:1 (noisy), far below capacity ratio → 5090 under-used"))

    # D = hetero_homo_tracelab (real trace, 2x4090) — global reprefill (secondary)
    d_tr, d_df = agg_D("hetero_homo_tracelab_tr.jsonl"), agg_D("hetero_homo_tracelab_default.jsonl")
    made.append(plot_D_reprefill(d_tr, d_df))

    # Print a compact numeric summary for the analysis log
    print("=== F per-backend KV usage peak (tr / default) ===")
    for c in sorted(f_tr):
        print(f"  c={c:>2}: 4090 {f_tr[c]['4090']['kv_peak']:.2f}/{f_df[c]['4090']['kv_peak']:.2f}  "
              f"5090 {f_tr[c]['5090']['kv_peak']:.2f}/{f_df[c]['5090']['kv_peak']:.2f}  "
              f"tr pause 4090/5090={f_tr[c]['4090']['paused']:.0f}/{f_tr[c]['5090']['paused']:.0f}")
    print("=== G per-backend KV usage peak (tr / default) ===")
    for c in sorted(g_tr):
        print(f"  c={c:>2}: 4090 {g_tr[c]['4090']['kv_peak']:.2f}/{g_df[c]['4090']['kv_peak']:.2f}  "
              f"5090 {g_tr[c]['5090']['kv_peak']:.2f}/{g_df[c]['5090']['kv_peak']:.2f}  "
              f"tr pause 4090/5090={g_tr[c]['4090']['paused']:.0f}/{g_tr[c]['5090']['paused']:.0f}")
    print("=== D TRUE reprefill=queries-hits (M) vs prompt_total(M) & preempt (tr / default) ===")
    for c in sorted(d_tr):
        print(f"  c={c:>2}: reprefill_miss {d_tr[c]['reprefill_miss']/1e6:.2f}/{d_df[c]['reprefill_miss']/1e6:.2f} M  "
              f"prompt_total {d_tr[c]['prompt_total']/1e6:.2f}/{d_df[c]['prompt_total']/1e6:.2f} M  "
              f"preempt {d_tr[c]['preempt']:.1f}/{d_df[c]['preempt']:.1f}  "
              f"hit {d_tr[c]['hit']:.3f}/{d_df[c]['hit']:.3f}")
    print("\nWrote:")
    for p in made:
        print(" ", p)


if __name__ == "__main__":
    main()
