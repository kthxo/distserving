import json, statistics as st
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
D='/home/yunuikang/yunuikang_work/scratch/sab'
def load(f): return [json.loads(l) for l in open(f) if l.strip()]
dd={};tt={}
for r in load(f'{D}/sab_default.jsonl'): dd.setdefault(r['concurrency'],[]).append(r)
for r in load(f'{D}/sab_tr.jsonl'): tt.setdefault(r['concurrency'],[]).append(r)
def med(runs,k):
    v=[x[k] for x in runs if x.get(k) is not None]; return st.median(v) if v else float('nan')
Cs=[8,16,24,32,48]; fit=16.2
dth=[med(dd[c],'throughput_programs_per_s') for c in Cs]
tth=[med(tt[c],'throughput_programs_per_s') for c in Cs]
dht=[med(dd[c],'true_hit_local_compute') for c in Cs]
tht=[med(tt[c],'true_hit_local_compute') for c in Cs]
dp=[med(dd[c],'latency_p95_s') for c in Cs]
tp=[med(tt[c],'latency_p95_s') for c in Cs]

fig,ax=plt.subplots(1,3,figsize=(15,4.5))
for a in ax: a.axvline(fit,ls=':',c='gray',lw=1); a.set_xlabel('concurrency C')
ax[0].plot(Cs,dth,'o-',c='crimson',label='default'); ax[0].plot(Cs,tth,'s-',c='steelblue',label='tr')
ax[0].set_title('Throughput (prog/s)'); ax[0].legend(); ax[0].text(fit,ax[0].get_ylim()[1]*0.9,'fit=16.2',fontsize=8,color='gray')
ax[1].plot(Cs,dht,'o-',c='crimson',label='default'); ax[1].plot(Cs,tht,'s-',c='steelblue',label='tr')
ax[1].set_title('True KV hit (local_compute)'); ax[1].legend(); ax[1].set_ylim(0,1)
ax[2].plot(Cs,dp,'o-',c='crimson',label='default'); ax[2].plot(Cs,tp,'s-',c='steelblue',label='tr')
ax[2].set_title('p95 latency (s)'); ax[2].legend()
fig.suptitle('P2 Science (mini-swe scaffold, Pro6000 1-GPU Qwen3-32B, fit×d=16.0 → tr-win zone)',fontsize=11)
fig.tight_layout(); fig.savefig(f'/home/yunuikang/yunuikang_work/distserving/figures/p2_sab_sweep.png',dpi=110)
print("saved p2_sab_sweep.png")
print(f"tr gain: "+", ".join(f"C{c}:{(tt_/max(d_,1e-9)-1)*100:+.0f}%" for c,d_,tt_ in zip(Cs,dth,tth)))
