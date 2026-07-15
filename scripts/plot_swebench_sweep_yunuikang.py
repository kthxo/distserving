#!/usr/bin/env python3
"""SWE-bench Phase D-SWE 스윕 결과 플롯 (tr vs default, 2×4090).

입력: scratch/swebench_{default,tr}.jsonl (run_trace_sweep 출력, 각 점 REPEAT줄).
출력: figures/swebench_{throughput,hitrate,p95}.png + 콘솔 요약표.
스키마: throughput_programs_per_s, latency_p95_s, prefix_cache_hit_rate,
        prefix_cache_{hits,queries}_delta, num_preemptions_delta, per_backend_query_delta.
"""
import json, statistics as st
from collections import defaultdict
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

S = Path("/home/yunuikang/yunuikang_work/scratch")
FIG = Path("/home/yunuikang/yunuikang_work/distserving/figures"); FIG.mkdir(exist_ok=True)

def agg(name):
    rows = [json.loads(l) for l in (S/name).read_text().splitlines() if l.strip()]
    by_c = defaultdict(list)
    for r in rows: by_c[r["concurrency"]].append(r)
    out = {}
    for c, lst in sorted(by_c.items()):
        def m(k):
            v=[r.get(k) for r in lst if r.get(k) is not None]; return st.mean(v) if v else 0
        # true reprefill = miss rate = 1 - hit
        out[c] = dict(
            thru=m("throughput_programs_per_s"), p95=m("latency_p95_s"),
            hit=m("prefix_cache_hit_rate"), completed=m("completed"),
            n=len(lst),
        )
    return out

def main():
    tr = agg("swebench_tr.jsonl"); df = agg("swebench_default.jsonl")
    concs = sorted(set(tr)&set(df))
    if not concs:
        print("no overlapping concurrency points yet"); return

    print("=== SWE-bench Phase D-SWE sweep (2x4090, tr vs default) ===")
    print(f"{'C':>3} | {'thru tr/def':>16} | {'p95 tr/def':>16} | {'hit tr/def':>16}")
    for c in concs:
        print(f"{c:>3} | {tr[c]['thru']:.4f}/{df[c]['thru']:.4f} | "
              f"{tr[c]['p95']:.0f}/{df[c]['p95']:.0f}s | {tr[c]['hit']:.3f}/{df[c]['hit']:.3f}")

    def plot(key, ylabel, fname, title):
        fig, ax = plt.subplots(figsize=(7,4.4))
        ax.plot(concs, [df[c][key] for c in concs], "--x", color="#8a8d91", label="default")
        ax.plot(concs, [tr[c][key] for c in concs], "-o", color="#3a7d44", label="tr")
        ax.set_xlabel("concurrency (offered)"); ax.set_ylabel(ylabel); ax.set_title(title)
        ax.legend(); ax.grid(alpha=0.3); fig.tight_layout()
        fig.savefig(FIG/fname, dpi=130); plt.close(fig); return fname

    made = [
        plot("thru","throughput (programs/s)","swebench_throughput.png",
             "SWE-bench (2x4090): throughput tr vs default"),
        plot("hit","prefix-cache hit rate","swebench_hitrate.png",
             "SWE-bench (2x4090): KV hit rate tr vs default"),
        plot("p95","p95 latency (s)","swebench_p95.png",
             "SWE-bench (2x4090): p95 latency tr vs default"),
    ]
    print("wrote:", ", ".join(made))

if __name__ == "__main__":
    main()
