#!/usr/bin/env python3
"""Experiment C analysis + plots (R model: U ≈ min(R,1), R = k_fit·d).

Reads (all under scratch/expC/, resilient to partial data):
  * result jsonls: expC_tr.jsonl, expC_default.jsonl, expC_cross_ts*.jsonl,
    expC_knob_*.jsonl   (one summary line per (C, repeat))
  * sampler csvs:  sample_<label>_c<C>.csv  -> measured U, k_fit, gpu util
  * duty profile:  prof_duty/step_profiles.csv -> workload d
  * per-run step profiles: prof_<label>/step_profiles.csv -> latency breakdown

Writes figures to figures/ and a merged table scratch/expC/expC_summary.csv.
Run any time; regenerates from whatever data exists so far.
"""
import os, glob, json, csv, re, math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

S = "/home/yunuikang/yunuikang_work/scratch/expC"
FIG = "/home/yunuikang/yunuikang_work/distserving/figures"
os.makedirs(FIG, exist_ok=True)

# ---------- duty cycle d (workload-intrinsic) ----------
def duty_cycle(profdir=os.path.join(S, "prof_duty")):
    fp = os.path.join(profdir, "step_profiles.csv")
    if not os.path.exists(fp):
        return None
    reas = tool = 0.0
    for r in csv.DictReader(open(fp)):
        def g(k):
            try: return float(r[k])
            except: return 0.0
        reas += g("prefill_s") + g("decode_s")
        tool += g("tool_call_s")
    return reas / (reas + tool) if (reas + tool) else None

# ---------- sampler -> measured U, k_fit ----------
def analyze_sampler(fp):
    """Return per-file dict: U_meas (pair busy frac), k_fit (mean resident),
    gpu_util, over the active window (first..last tick with any resident>0)."""
    rows = list(csv.DictReader(open(fp)))
    if not rows: return None
    def col(r, k):
        try: return float(r[k])
        except: return 0.0
    b0res = np.array([col(r,"b0_reasoning") for r in rows])
    b0act = np.array([col(r,"b0_acting") for r in rows])
    b1res = np.array([col(r,"b1_reasoning") for r in rows])
    b1act = np.array([col(r,"b1_acting") for r in rows])
    g2 = np.array([col(r,"gpu2_util") for r in rows])
    g3 = np.array([col(r,"gpu3_util") for r in rows])
    resid_tot = b0res+b0act+b1res+b1act
    active = np.where(resid_tot > 0)[0]
    if len(active) < 2: return None
    lo, hi = active[0], active[-1]+1
    sl = slice(lo, hi)
    # per-backend busy fraction (reasoning>0 => GPU doing inference)
    u0 = float(np.mean(b0res[sl] > 0)); u1 = float(np.mean(b1res[sl] > 0))
    k0 = float(np.mean(b0res[sl]+b0act[sl])); k1 = float(np.mean(b1res[sl]+b1act[sl]))
    return {
        "U_meas": (u0+u1)/2, "U_b0": u0, "U_b1": u1,
        "k_fit": (k0+k1)/2, "k_b0": k0, "k_b1": k1,
        "gpu_util": (float(np.mean(g2[sl]))+float(np.mean(g3[sl])))/2,
        "idle_frac": 1-(u0+u1)/2,
        "paused_mean": float(np.mean([col(r,"paused_total") for r in rows[lo:hi]])),
        "n_ticks": int(hi-lo),
        "_series": np.stack([b0res,b0act,b1res,b1act,g2,g3]), "_lo": lo, "_hi": hi,
    }

def sampler_label(fname):
    m = re.match(r"sample_(.+)_c(\d+)\.csv$", os.path.basename(fname))
    return (m.group(1), int(m.group(2))) if m else (None, None)

# ---------- result jsonls ----------
FILE2LABEL = {  # result file basename (no ext) -> sampler label
    "expC_tr": "tr_ts1.0", "expC_default": "default_ts1.0",
    "expC_knob_decay": "knob_decay", "expC_knob_weight05": "knob_weight05",
}
def result_label(basename):
    if basename in FILE2LABEL: return FILE2LABEL[basename]
    m = re.match(r"expC_(cross_ts[0-9.]+)$", basename)
    return m.group(1) if m else basename

def load_results():
    """dict[(label, C)] -> aggregated {throughput, p95, hit, wall, n, router, tool_scale}."""
    agg = {}
    for fp in sorted(glob.glob(os.path.join(S, "expC_*.jsonl"))):
        base = os.path.splitext(os.path.basename(fp))[0]
        if base.endswith("_done"): continue
        label = result_label(base)
        for line in open(fp):
            line=line.strip()
            if not line: continue
            try: d=json.loads(line)
            except: continue
            C=d.get("concurrency")
            tag=d.get("run_tag","")
            mts=re.search(r"ts([0-9.]+)", tag); ts=float(mts.group(1)) if mts else 1.0
            key=(label, C)
            a=agg.setdefault(key, {"thr":[], "p95":[], "hit":[], "wall":[],
                                   "router":d.get("router"), "tool_scale":ts})
            a["thr"].append(d.get("throughput_programs_per_s"))
            a["p95"].append(d.get("latency_p95_s"))
            a["hit"].append(d.get("prefix_cache_hit_rate"))
            a["wall"].append(d.get("wall_s"))
    out={}
    for k,a in agg.items():
        f=lambda xs:[x for x in xs if x is not None]
        out[k]={"thr":np.mean(f(a["thr"])) if f(a["thr"]) else None,
                "thr_sd":np.std(f(a["thr"])) if len(f(a["thr"]))>1 else 0,
                "p95":np.mean(f(a["p95"])) if f(a["p95"]) else None,
                "hit":np.mean(f(a["hit"])) if f(a["hit"]) else None,
                "wall":np.mean(f(a["wall"])) if f(a["wall"]) else None,
                "n":len(f(a["thr"])), "router":a["router"], "tool_scale":a["tool_scale"]}
    return out

# ---------- latency breakdown from per-run step profiles ----------
def latency_breakdown(label):
    fp=os.path.join(S, f"prof_{label}", "step_profiles.csv")
    if not os.path.exists(fp): return None
    acc={"prefill_s":0.,"decode_s":0.,"pause_s":0.,"tool_call_s":0.}
    n=0
    for r in csv.DictReader(open(fp)):
        for k in acc:
            try: acc[k]+=float(r[k])
            except: pass
        n+=1
    if not n: return None
    return {k:v/n for k,v in acc.items()}

# ================= build merged table =================
def build():
    d = duty_cycle()
    results = load_results()
    samplers = {}
    for fp in glob.glob(os.path.join(S, "sample_*.csv")):
        lab, C = sampler_label(fp)
        if lab is None: continue
        a = analyze_sampler(fp)
        if a: samplers[(lab, C)] = a
    rows=[]
    keys = set(results) | set(samplers)
    for (label, C) in sorted(keys, key=lambda x:(str(x[0]), x[1] or 0)):
        r = results.get((label,C), {})
        s = samplers.get((label,C), {})
        kfit = s.get("k_fit")
        ts = r.get("tool_scale", 1.0)
        # d scales with tool_scale: tool time *= ts  => d(ts)=reas/(reas+ts*tool)
        # recover reas/tool ratio from base d: base d uses ts=1.
        d_eff = None
        if d is not None:
            ratio = d/(1-d) if d<1 else None   # reas/tool at ts=1
            if ratio is not None:
                d_eff = ratio/(ratio+ts) if (ratio+ts) else None
        R = (kfit*d_eff) if (kfit is not None and d_eff is not None) else None
        rows.append({"label":label, "C":C, "router":r.get("router"),
                     "tool_scale":ts, "d_eff":d_eff,
                     "thr":r.get("thr"), "thr_sd":r.get("thr_sd"),
                     "p95":r.get("p95"), "hit":r.get("hit"), "wall":r.get("wall"),
                     "n":r.get("n"),
                     "U_meas":s.get("U_meas"), "k_fit":kfit,
                     "gpu_util":s.get("gpu_util"), "idle_frac":s.get("idle_frac"),
                     "paused_mean":s.get("paused_mean"),
                     "R":R, "U_pred": (min(R,1) if R is not None else None)})
    return d, rows, samplers

def save_table(rows):
    fp=os.path.join(S,"expC_summary.csv")
    cols=["label","C","router","tool_scale","d_eff","thr","thr_sd","p95","hit",
          "wall","n","U_meas","U_pred","R","k_fit","gpu_util","idle_frac","paused_mean"]
    with open(fp,"w",newline="") as f:
        w=csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for r in rows:
            w.writerow({k:(round(r[k],4) if isinstance(r.get(k),float) else r.get(k)) for k in cols})
    return fp

# ================= figures =================
def fig_pred_vs_meas(rows, d):
    pts=[(r["U_pred"],r["U_meas"],r["label"]) for r in rows
         if r["U_pred"] is not None and r["U_meas"] is not None]
    if not pts: return
    plt.figure(figsize=(6,6))
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
    plt.plot([0,1],[0,1],"k--",alpha=.5,label="U=min(R,1) (predicted)")
    plt.scatter(xs,ys,c="#2b6cb0",s=60,zorder=3)
    for x,y,l in pts: plt.annotate(l,(x,y),fontsize=6,alpha=.7)
    plt.xlabel("predicted U = min(R,1)"); plt.ylabel("measured U (GPU busy frac)")
    plt.title(f"R1: predicted vs measured GPU occupancy (d={d:.3f})")
    plt.xlim(0,1.05); plt.ylim(0,1.05); plt.legend(); plt.grid(alpha=.3)
    plt.tight_layout(); plt.savefig(f"{FIG}/expC_pred_vs_meas_U.png",dpi=130); plt.close()

def fig_crossing(rows):
    cr=sorted([r for r in rows if str(r["label"]).startswith("cross_ts") or r["label"]=="tr_ts1.0"],
              key=lambda r:r["tool_scale"])
    cr=[r for r in cr if r["C"]==16]
    if len(cr)<2: return
    ts=[r["tool_scale"] for r in cr]
    fig,ax=plt.subplots(1,3,figsize=(14,4))
    for a,key,ttl in [(ax[0],"U_meas","measured U"),(ax[1],"thr","throughput p/s"),(ax[2],"hit","prefix hit")]:
        y=[r[key] for r in cr]; yp=[r["U_pred"] for r in cr]
        a.plot(ts,y,"o-",color="#2b6cb0",label=ttl)
        if key=="U_meas": a.plot(ts,yp,"s--",color="#e53e3e",alpha=.7,label="pred U=min(R,1)")
        a.axvline(0.2,color="gray",ls=":",label="pred R=1 (S≈0.2)")
        a.set_xlabel("tool_scale S"); a.set_title(ttl); a.invert_xaxis(); a.grid(alpha=.3); a.legend(fontsize=7)
    fig.suptitle("R4: R=1 crossing via duty knob (tr, C=16) — lower S -> higher d -> higher R")
    plt.tight_layout(); plt.savefig(f"{FIG}/expC_R1_crossing.png",dpi=130); plt.close()

def fig_knob_two_axes(rows):
    # duty axis: cross_ts*, k_fit axis: knob_*  (all C=16, tr)
    base=[r for r in rows if r["label"]=="tr_ts1.0" and r["C"]==16]
    duty=[r for r in rows if str(r["label"]).startswith("cross_ts") and r["C"]==16]
    knob=[r for r in rows if str(r["label"]).startswith("knob_") and r["C"]==16]
    grp=base+duty+knob
    if not grp: return
    fig,ax=plt.subplots(1,2,figsize=(11,4.5))
    for r in grp:
        c="#2b6cb0" if (str(r["label"]).startswith("cross") or r["label"]=="tr_ts1.0") else "#e53e3e"
        if r["U_meas"] is not None and r["k_fit"] is not None:
            ax[0].scatter(r["k_fit"],r["U_meas"],c=c,s=55)
            ax[0].annotate(r["label"],(r["k_fit"],r["U_meas"]),fontsize=6)
        if r["hit"] is not None and r["U_meas"] is not None:
            ax[1].scatter(r["U_meas"],r["hit"],c=c,s=55)
            ax[1].annotate(r["label"],(r["U_meas"],r["hit"]),fontsize=6)
    ax[0].set_xlabel("k_fit (mean resident)"); ax[0].set_ylabel("measured U"); ax[0].set_title("R3: U vs k_fit"); ax[0].grid(alpha=.3)
    ax[1].set_xlabel("measured U"); ax[1].set_ylabel("prefix hit"); ax[1].set_title("R3: hit vs U (blue=duty knob keeps hit; red=k_fit knob loses hit)"); ax[1].grid(alpha=.3)
    plt.tight_layout(); plt.savefig(f"{FIG}/expC_knob_two_axes.png",dpi=130); plt.close()

def fig_main_sweep(rows):
    tr=sorted([r for r in rows if r["label"]=="tr_ts1.0"],key=lambda r:r["C"])
    de=sorted([r for r in rows if r["label"]=="default_ts1.0"],key=lambda r:r["C"])
    if not tr and not de: return
    fig,ax=plt.subplots(1,3,figsize=(14,4))
    for series,lab,col in [(tr,"tr","#2b6cb0"),(de,"default","#dd6b20")]:
        if not series: continue
        def xy(key):
            p=[(r["C"],r[key]) for r in series if r.get(key) is not None]
            return [a for a,_ in p],[b for _,b in p]
        cx,cy=xy("thr"); _,csd=([r["C"] for r in series if r.get("thr") is not None],
                                [ (r.get("thr_sd") or 0) for r in series if r.get("thr") is not None])
        if cx: ax[0].errorbar(cx,cy,yerr=csd,marker="o",label=lab,color=col)
        px,py=xy("p95");  ax[1].plot(px,py,"o-",label=lab,color=col) if px else None
        ux,uy=xy("U_meas"); ax[2].plot(ux,uy,"o-",label=lab,color=col) if ux else None
    ax[0].set_title("throughput p/s"); ax[1].set_title("latency p95 s"); ax[2].set_title("measured U")
    for a in ax: a.set_xlabel("concurrency C"); a.grid(alpha=.3); a.legend()
    fig.suptitle("Phase A: tr vs default main sweep (real TraceLab, 2x4090, GPU2/3)")
    plt.tight_layout(); plt.savefig(f"{FIG}/expC_main_sweep.png",dpi=130); plt.close()

def fig_latency_breakdown(rows):
    labels=["tr_ts1.0","default_ts1.0"]
    data={l:latency_breakdown(l) for l in labels}
    data={l:v for l,v in data.items() if v}
    if not data: return
    parts=["prefill_s","decode_s","pause_s","tool_call_s"]
    colors=["#3182ce","#63b3ed","#e53e3e","#a0aec0"]
    plt.figure(figsize=(6,4.5))
    for i,(l,v) in enumerate(data.items()):
        bottom=0
        for p,c in zip(parts,colors):
            plt.bar(i,v[p],bottom=bottom,color=c,label=p if i==0 else None)
            bottom+=v[p]
    plt.xticks(range(len(data)),list(data.keys()))
    plt.ylabel("mean per-step seconds"); plt.title("C5: latency breakdown (tr pause vs default)")
    plt.legend(fontsize=8); plt.tight_layout(); plt.savefig(f"{FIG}/expC_latency_breakdown.png",dpi=130); plt.close()

def fig_need_vs_fit(rows,d):
    grp=[r for r in rows if r["k_fit"] is not None and r["label"] in ("tr_ts1.0","default_ts1.0") and r["C"]==16]
    if not grp or not d: return
    need=1/d
    plt.figure(figsize=(6,4.5))
    for i,r in enumerate(grp):
        plt.bar(i-0.18,need,0.35,color="#e53e3e",label="NEED=1/d" if i==0 else None)
        plt.bar(i+0.18,r["k_fit"],0.35,color="#2b6cb0",label="FIT=k_fit" if i==0 else None)
    plt.xticks(range(len(grp)),[r["label"] for r in grp])
    plt.title(f"C6: NEED=1/d ({need:.1f}) vs FIT=k_fit  (NEED>FIT <=> R<1)")
    plt.legend(); plt.tight_layout(); plt.savefig(f"{FIG}/expC_need_vs_fit.png",dpi=130); plt.close()

def fig_thr_vs_idle(rows):
    pts=[(r["idle_frac"],r["thr"],r["label"]) for r in rows
         if r["idle_frac"] is not None and r["thr"] is not None]
    if len(pts)<2: return
    plt.figure(figsize=(6,4.5))
    for x,y,l in pts:
        plt.scatter(x,y,s=45,c="#2b6cb0"); plt.annotate(l,(x,y),fontsize=6)
    plt.xlabel("GPU idle fraction (1-U)"); plt.ylabel("throughput p/s")
    plt.title("C4: throughput vs GPU idle"); plt.grid(alpha=.3)
    plt.tight_layout(); plt.savefig(f"{FIG}/expC_throughput_vs_idle.png",dpi=130); plt.close()

def main():
    d, rows, samplers = build()
    fp=save_table(rows)
    print(f"duty_cycle d = {d}")
    print(f"wrote {fp} ({len(rows)} rows)")
    # print compact table
    hdr=["label","C","thr","hit","U_meas","U_pred","R","k_fit","d_eff"]
    print("  ".join(f"{h:>10}" for h in hdr))
    for r in rows:
        print("  ".join(f"{('' if r[h] is None else (f'{r[h]:.3f}' if isinstance(r[h],float) else str(r[h]))):>10}" for h in hdr))
    fig_pred_vs_meas(rows,d or 0.2)
    fig_crossing(rows); fig_knob_two_axes(rows); fig_main_sweep(rows)
    fig_latency_breakdown(rows); fig_need_vs_fit(rows,d); fig_thr_vs_idle(rows)
    print(f"figures -> {FIG}/expC_*.png")

if __name__=="__main__":
    main()
