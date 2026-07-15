#!/usr/bin/env python3
"""SWE-bench 녹화 워크로드 characterization (§D-char 방식, decode-heavy 대비).

입력(모두 GPU/Docker 불필요):
  - scratch/traces/swebench_trace.jsonl           (정규화된 canonical trace)
  - scratch/rec_swebench/step_profiles.csv        (per-step prefill/decode/pause/tool 실측)
  - scratch/traces/swebench_stratified64.order.txt (program_id -> instance_id, 레포 귀속용)

산출:
  - figures/char_swebench_{tokens,lifetime,turn_breakdown,by_repo}.png
  - 콘솔: 3-way 대비표(SWE vs TraceLab vs 합성) + 레포별 분포 + duty_cycle(d) 추정
"""
import csv, json, statistics as st
from collections import defaultdict
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

S = Path("/home/yunuikang/yunuikang_work/scratch")
FIG = Path("/home/yunuikang/yunuikang_work/distserving/figures"); FIG.mkdir(exist_ok=True)

trace = [json.loads(l) for l in (S/"traces/swebench_trace.jsonl").read_text().splitlines() if l.strip()]
steps = list(csv.DictReader(open(S/"rec_swebench/step_profiles.csv")))

# program_id -> instance_id -> repo
pid2iid = {}
for line in (S/"traces/swebench_stratified64.order.txt").read_text().splitlines():
    n, iid = line.split("\t"); pid2iid[n] = iid
def repo_of(iid): return iid.split("__")[0]

def stats(v):
    v = [x for x in v if x is not None]
    s = sorted(v)
    q = lambda p: s[min(len(s)-1, int(round(p*(len(s)-1))))]
    return dict(n=len(s), median=st.median(s), mean=round(st.mean(s),1), p95=q(0.95), max=s[-1])

# ---- per-session (program) aggregates
by_sess = defaultdict(list)
for r in trace: by_sess[r["session_id"]].append(r)
turns_per = [len(v) for v in by_sess.values()]
inp = [r["input_tokens"] for r in trace]
out = [r["output_tokens"] for r in trace]
tool = [r["tool_duration_s"] for r in trace]

# ---- duty_cycle d from recorded per-step timing (reasoning=prefill+decode, tool=tool_call)
reasoning = sum(float(x["prefill_s"])+float(x["decode_s"]) for x in steps)
tool_t = sum(float(x["tool_call_s"]) for x in steps)
d_agg = reasoning/(reasoning+tool_t)
# per-program d then median
d_prog = []
by_pid = defaultdict(list)
for x in steps: by_pid[x["program_id"]].append(x)
for pid, xs in by_pid.items():
    rz = sum(float(x["prefill_s"])+float(x["decode_s"]) for x in xs)
    tz = sum(float(x["tool_call_s"]) for x in xs)
    if rz+tz>0: d_prog.append(rz/(rz+tz))

print("=== SWE-bench workload characterization ===")
print(f"sessions={len(by_sess)} turns={len(trace)}")
print(f"turns/session: {stats(turns_per)}")
print(f"input_tokens : {stats(inp)}")
print(f"output_tokens: {stats(out)}")
print(f"tool_dur_s   : {stats(tool)}")
print(f"duty_cycle d = reasoning/(reasoning+tool): aggregate={d_agg:.3f}  per-prog median={st.median(d_prog):.3f}")
print("\n=== 3-way workload contrast (median) ===")
print(f"{'metric':16s}{'SWE-bench':>14s}{'TraceLab':>12s}{'synthetic§9':>13s}")
print(f"{'input tok/turn':16s}{st.median(inp):>14.0f}{'18275':>12s}{'14558':>13s}")
print(f"{'output tok/turn':16s}{st.median(out):>14.0f}{'144':>12s}{'~28':>13s}")
print(f"{'tool s/turn':16s}{st.median(tool):>14.3f}{'0.047':>12s}{'0.4':>13s}")
print(f"{'turns/session':16s}{st.median(turns_per):>14.0f}{'9.5':>12s}{'3':>13s}")
print(f"{'-> character':16s}{'decode-heavy':>14s}{'prefill-hvy':>12s}{'balanced':>13s}")

# ---- repo attribution
repo_turns = defaultdict(int); repo_sess = defaultdict(int); repo_out = defaultdict(list)
for sid, rows in by_sess.items():
    iid = pid2iid.get(sid, ""); rp = repo_of(iid) if iid else "?"
    repo_sess[rp]+=1; repo_turns[rp]+=len(rows); repo_out[rp]+=[r["output_tokens"] for r in rows]
print("\n=== by repo (sessions / turns / median output tok) ===")
for rp in sorted(repo_sess, key=lambda x:-repo_sess[x]):
    print(f"  {rp:14s} sess={repo_sess[rp]:2d} turns={repo_turns[rp]:4d} out_med={st.median(repo_out[rp]):.0f}")

# ---- figures
# 1) token distributions
fig, ax = plt.subplots(1,2, figsize=(11,4))
ax[0].hist(inp, bins=40, color="#2e86ab"); ax[0].set_title(f"SWE input tokens/turn (median {st.median(inp):.0f})"); ax[0].set_xlabel("tokens")
ax[1].hist(out, bins=40, color="#d1495b"); ax[1].set_title(f"SWE output tokens/turn (median {st.median(out):.0f}) — decode-heavy"); ax[1].set_xlabel("tokens")
fig.tight_layout(); fig.savefig(FIG/"char_swebench_tokens.png", dpi=130); plt.close(fig)

# 2) lifetime (turns/session)
fig, ax = plt.subplots(figsize=(6,4))
ax.hist(turns_per, bins=range(0,42,2), color="#3a7d44")
ax.axvline(40, color="gray", ls=":", label="step_limit=40 (clip)")
ax.set_title(f"SWE turns/session (median {st.median(turns_per):.0f}, clip@40={sum(1 for t in turns_per if t>=40)}/64)")
ax.set_xlabel("turns"); ax.legend(); fig.tight_layout(); fig.savefig(FIG/"char_swebench_lifetime.png", dpi=130); plt.close(fig)

# 3) turn breakdown (mean prefill/decode/tool per step)
pf = st.mean([float(x["prefill_s"]) for x in steps]); dc = st.mean([float(x["decode_s"]) for x in steps]); tl = st.mean([float(x["tool_call_s"]) for x in steps])
fig, ax = plt.subplots(figsize=(6,4))
ax.bar(["prefill","decode","tool"], [pf,dc,tl], color=["#2e86ab","#d1495b","#e08e0b"])
ax.set_ylabel("mean seconds/step"); ax.set_title(f"SWE per-step time (decode dominates, d={d_agg:.2f})")
for i,v in enumerate([pf,dc,tl]): ax.text(i, v, f"{v:.1f}s", ha="center", va="bottom")
fig.tight_layout(); fig.savefig(FIG/"char_swebench_turn_breakdown.png", dpi=130); plt.close(fig)

# 4) by-repo sessions
fig, ax = plt.subplots(figsize=(8,4))
rps = sorted(repo_sess, key=lambda x:-repo_sess[x])
ax.bar(range(len(rps)), [repo_sess[r] for r in rps], color="#2e86ab")
ax.set_xticks(range(len(rps))); ax.set_xticklabels([r.split("/")[-1] for r in rps], rotation=45, ha="right", fontsize=8)
ax.set_ylabel("sessions"); ax.set_title("SWE stratified-64: sessions per repo")
fig.tight_layout(); fig.savefig(FIG/"char_swebench_by_repo.png", dpi=130); plt.close(fig)

print("\nwrote figures: char_swebench_{tokens,lifetime,turn_breakdown,by_repo}.png")
