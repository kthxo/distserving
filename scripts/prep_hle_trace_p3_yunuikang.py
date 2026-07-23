#!/usr/bin/env python3
"""P3 §4-4-4 D — build HLE canonical trace: orchestrator turns + tool_duration
sampled from the FULL 24h GLM-latency distribution (tail included). Fixed seed ->
identical trace replayed to tr and default (fair). GPU-free.
"""
import argparse, json, random, statistics

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--lat", default="/home/yunuikang/yunuikang_work/scratch/p3/glm_latency_24h.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--nprog", type=int, default=256)
    ap.add_argument("--seed", type=int, default=20260720)
    args=ap.parse_args()
    rng=random.Random(args.seed)
    rows=[json.loads(l) for l in open(args.lat) if l.strip()]
    c=[r for r in rows if r.get("success") and "latency_s" in r]
    S=[r["latency_s"] for r in c if r["kind"]=="search"]      # 24h search latencies (tail incl)
    A=[r["latency_s"] for r in c if r["kind"]=="answer"]      # 24h answer latencies (tail incl)
    FAISS=0.32
    # observed per-workflow search-turn counts (smoke5b): mostly 1, occasionally many (heavy tail)
    NSEARCH_POOL=[1,1,1,1,2,2,3,5,9]   # empirical-ish (one workflow had 9)
    out=[]
    for p in range(args.nprog):
        sid=f"hle-{p:04d}"
        ns=rng.choice(NSEARCH_POOL)
        turn=0
        ctx=rng.randint(150,400)   # initial context tokens
        for i in range(ns):
            inp=min(15000, ctx)
            out.append({"session_id":sid,"turn":turn,"input_tokens":inp,
                        "output_tokens":rng.randint(350,650),        # orchestrator tool-call gen (~t_reason 14s)
                        "tool_duration_s":round(rng.choice(S)+FAISS,3)})  # search tool = GLM + FAISS
            ctx+=rng.randint(1200,2200)   # docs accumulate
            turn+=1
        # answer turn
        out.append({"session_id":sid,"turn":turn,"input_tokens":min(15000,ctx),
                    "output_tokens":rng.randint(500,1000),
                    "tool_duration_s":round(rng.choice(A),3)})        # answer tool = GLM (no FAISS)
        turn+=1
        # final turn (produce answer, no tool)
        out.append({"session_id":sid,"turn":turn,"input_tokens":min(15000,ctx),
                    "output_tokens":rng.randint(100,300),"tool_duration_s":0.0})
    with open(args.out,"w") as f:
        for r in out: f.write(json.dumps(r)+"\n")
    tds=[r["tool_duration_s"] for r in out if r["tool_duration_s"]>0]
    tpr=[sum(1 for r in out if r["session_id"]==s) for s in {r["session_id"] for r in out}]
    print(f"trace: {len({r['session_id'] for r in out})} sessions, {len(out)} turns -> {args.out}")
    print(f"  turns/session median={statistics.median(tpr)} | tool_duration median={statistics.median(tds):.1f}s p95={sorted(tds)[int(0.95*(len(tds)-1))]:.1f}s max={max(tds):.1f}s (tail preserved)")
    print(f"  input median={statistics.median([r['input_tokens'] for r in out])} output median={statistics.median([r['output_tokens'] for r in out])}")

if __name__=="__main__": main()
