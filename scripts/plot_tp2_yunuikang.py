#!/usr/bin/env python3
"""P1 analysis + plots for the Pro6000 TP2 serving-eval (TraceLab + SWE).
Reads sweep JSONL + sampler CSVs, computes R-model (pred U vs measured U),
emits figures/tp2_*.png and a summary table.
"""
import csv, json, os, statistics
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TP2 = "/home/yunuikang/yunuikang_work/scratch/tp2"
FIG = "/home/yunuikang/yunuikang_work/distserving/figures"
os.makedirs(FIG, exist_ok=True)
CS = [16, 32, 64]
DUTY = {"tracelab": 0.289, "swe": 0.996}   # measured c=1 (TraceLab P0) / step_profiles (SWE)
KVPOOL = 456944

def load_sweep(path):
    by = defaultdict(list)
    for l in open(path):
        d = json.loads(l); by[d["concurrency"]].append(d)
    out = {}
    for C, ds in by.items():
        out[C] = {k: statistics.mean([x[k] for x in ds]) for k in
                  ("throughput_programs_per_s", "prefix_cache_hit_rate", "latency_p95_s")}
        out[C]["n"] = len(ds)
    return out

def load_sampler(path):
    """Return (k_fit, U_measured) from a sampler CSV. k_fit=mean(reasoning+acting)
    over active ticks; U=fraction of active window with nrr>0 (GPU busy)."""
    if not os.path.exists(path): return (None, None)
    rows = list(csv.DictReader(open(path)))
    def num(r, k):
        try: return float(r.get(k) or 0)
        except ValueError: return 0.0
    act = [(num(r,"b0_reasoning")+num(r,"b0_acting"), num(r,"b0_nrr")) for r in rows]
    # trim leading/trailing all-zero (nrr==0 and resident==0)
    nz = [i for i,(res,nrr) in enumerate(act) if res>0 or nrr>0]
    if not nz: return (None, None)
    win = act[nz[0]:nz[-1]+1]
    if not win: return (None, None)
    kfit = statistics.mean([res for res,_ in win])
    U = sum(1 for _,nrr in win if nrr>0)/len(win)
    return (kfit, U)

def sampler_path(wl, router, C):
    base = TP2 if wl=="tracelab" else f"{TP2}/swe"
    return f"{base}/sample_{router}_ts1.0_c{C}.csv"

# ---- load everything ----
data = {}
for wl in ("tracelab","swe"):
    for router in ("default","tr"):
        sw = load_sweep(f"{TP2}/{wl}_{router}.jsonl")
        for C in CS:
            kfit, U = load_sampler(sampler_path(wl, router, C))
            data[(wl,router,C)] = {**sw.get(C,{}), "kfit":kfit, "U":U}

# ---- summary table + R-model ----
print("="*92)
print(f"{'wl':9} {'router':7} {'C':>4} {'thru':>7} {'hit':>6} {'p95':>7} {'kfit':>6} {'U_meas':>7} {'R=kfit*d':>9} {'predU':>6}")
rows_for_scatter = []
for wl in ("tracelab","swe"):
    d = DUTY[wl]
    for router in ("default","tr"):
        for C in CS:
            x = data[(wl,router,C)]
            thru=x.get("throughput_programs_per_s"); hit=x.get("prefix_cache_hit_rate")
            p95=x.get("latency_p95_s"); kfit=x.get("kfit"); U=x.get("U")
            R = kfit*d if kfit is not None else None
            predU = min(R,1.0) if R is not None else None
            if U is not None and predU is not None: rows_for_scatter.append((predU,U,wl,router,C))
            def f(v,fmt): return (fmt%v) if v is not None else "  -  "
            print(f"{wl:9} {router:7} {C:>4} {f(thru,'%7.3f')} {f(hit,'%6.3f')} {f(p95,'%7.0f')} "
                  f"{f(kfit,'%6.1f')} {f(U,'%7.2f')} {f(R,'%9.2f')} {f(predU,'%6.2f')}")
print("="*92)

# ---- plots: throughput / hit / p95 vs C, tr vs default, per workload ----
def sweep_plot(wl, metric, ylabel, fname, logy=False):
    plt.figure(figsize=(5,3.6))
    for router,color,mk in (("default","#d62728","o"),("tr","#1f77b4","s")):
        ys=[data[(wl,router,C)].get(metric) for C in CS]
        plt.plot(CS, ys, mk+"-", color=color, label=router, lw=2, ms=7)
    if logy: plt.yscale("log")
    plt.xlabel("parallel workflow number (C)"); plt.ylabel(ylabel)
    plt.title(f"{wl}  (Qwen3-32B TP2, KV {KVPOOL//1000}k)")
    plt.xticks(CS); plt.grid(alpha=.3); plt.legend()
    plt.tight_layout(); plt.savefig(f"{FIG}/{fname}", dpi=130); plt.close()

for wl in ("tracelab","swe"):
    sweep_plot(wl,"throughput_programs_per_s","throughput (prog/s)",f"tp2_{wl}_throughput.png")
    sweep_plot(wl,"prefix_cache_hit_rate","KV cache hit rate",f"tp2_{wl}_hitrate.png")
    sweep_plot(wl,"latency_p95_s","p95 latency (s)",f"tp2_{wl}_p95.png",logy=True)

# ---- pred U vs measured U scatter (R-model), anchored with 4090 expC points ----
# 4090 reference (expC): tr R=0.31 U~0.35 (starved, lost); default R>1 U~0.87.
ANCHORS = [(0.31,0.35,"4090","tr",32),(1.00,0.87,"4090","default",32)]
allpts = rows_for_scatter + ANCHORS
if allpts:
    plt.figure(figsize=(4.8,4.6))
    for predU,U,wl,router,C in allpts:
        c = "#1f77b4" if router=="tr" else "#d62728"
        m = {"swe":"s","tracelab":"o","4090":"^"}[wl]
        plt.scatter(predU,U,c=c,marker=m,s=75,edgecolor="k",lw=.6,zorder=3)
        plt.annotate(f"{wl[:2]}{router[:1]}{C}",(predU,U),fontsize=6,xytext=(3,3),textcoords="offset points")
    plt.plot([0,1],[0,1],"k--",alpha=.5,label="y=x (U=min(R,1))")
    plt.xlabel("predicted U = min(R,1),  R=k_fit·d"); plt.ylabel("measured U (GPU busy frac)")
    plt.title("R-model + k_fit-flip (Pro6000 ●■ vs 4090 ▲)")
    plt.xlim(0,1.08); plt.ylim(0,1.08); plt.grid(alpha=.3); plt.legend(fontsize=8)
    plt.tight_layout(); plt.savefig(f"{FIG}/tp2_pred_vs_meas_U.png",dpi=130); plt.close()
    xs=[r[0] for r in allpts]; ys=[r[1] for r in allpts]
    if len(set(xs))>1 and len(set(ys))>1:
        import math
        mx,my=statistics.mean(xs),statistics.mean(ys)
        num=sum((a-mx)*(b-my) for a,b in zip(xs,ys))
        den=math.sqrt(sum((a-mx)**2 for a in xs)*sum((b-my)**2 for b in ys))
        print(f"R-model Pearson r(predU, measU) incl 4090 anchors = {num/den:.3f}  (n={len(xs)})")
    print("NOTE: on Pro6000 all cells have R>1 -> U~1 (GPU busy incl. wasteful thrash recompute);")
    print("      tr's edge there is hit-rate/goodput, not occupancy. The k_fit-flip is tr's U 0.35(4090)->~0.97(Pro6000).")

# ---- k_fit-flip: 4090 (lost) vs Pro6000 (won), TraceLab C=32 ----
plt.figure(figsize=(5,3.6))
labels=["4090 (KV 43.9k)\nfit~2","Pro6000 TP2 (KV 457k)\nfit~25"]
tr_gain=[-34, +87]   # % throughput of tr vs default (4090 from expC; Pro6000 C=32 this run)
colors=["#d62728" if g<0 else "#1f77b4" for g in tr_gain]
plt.bar(labels,tr_gain,color=colors,edgecolor="k")
plt.axhline(0,color="k",lw=.8)
plt.ylabel("tr throughput vs default (%)"); plt.title("TraceLab k_fit-flip (C=32)")
for i,g in enumerate(tr_gain): plt.text(i,g+(3 if g>0 else -6),f"{g:+d}%",ha="center",fontweight="bold")
plt.tight_layout(); plt.savefig(f"{FIG}/tp2_kfit_flip_4090_vs_pro6000.png",dpi=130); plt.close()

# ---- SYS microbench ----
mb=f"{TP2}/microbench_sys.jsonl"
if os.path.exists(mb):
    recs={json.loads(l)["label"]:json.loads(l) for l in open(mb)}
    if "tp1" in recs and "tp2" in recs:
        plt.figure(figsize=(4,3.4))
        vals=[recs["tp1"]["decode_tok_per_s"],recs["tp2"]["decode_tok_per_s"]]
        plt.bar(["TP1\n(GPU1)","TP2\n(GPU1+2, SYS)"],vals,color=["#7f7f7f","#1f77b4"],edgecolor="k")
        for i,v in enumerate(vals): plt.text(i,v+15,f"{v:.0f}",ha="center",fontweight="bold")
        plt.ylabel("decode tok/s"); plt.title(f"SYS penalty: TP2/TP1={vals[1]/vals[0]:.2f}x")
        plt.tight_layout(); plt.savefig(f"{FIG}/tp2_sys_microbench.png",dpi=130); plt.close()

print(f"\nfigures -> {FIG}/tp2_*.png")
print("saved:", sorted(f for f in os.listdir(FIG) if f.startswith("tp2_")))
