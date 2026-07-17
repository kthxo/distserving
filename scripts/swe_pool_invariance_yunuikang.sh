#!/usr/bin/env bash
# P1 §4-2 — SWE workload-pool size invariance check.
# At a FIXED concurrency, replay the recorded SWE trace using pool=32 vs pool=64
# distinct sessions and compare steady-state throughput. Same → stratified-64
# confirmed; differ → raise pool (report before deciding).
# Assumes the :9000 proxy + :8000 backend (Deployment A) are already up.
#
# Usage: swe_pool_invariance_yunuikang.sh <full_swe_trace.jsonl> <router: tr|default> [C]
set -uo pipefail
TRACE="${1:?recorded SWE canonical trace}"
ROUTER="${2:?router (tr|default)}"
C="${3:-64}"
REPO=/home/yunuikang/yunuikang_work/distserving
VENV=/home/yunuikang/yunuikang_work/.venv
OUTDIR="${SAMPLEDIR:-$REPO/../scratch/tp2}/pool_invariance"
MODEL="${MODEL:-Qwen/Qwen3-32B}"
PORT="${PORT:-9000}"
REPEAT="${REPEAT:-2}"
mkdir -p "$OUTDIR"
source "$VENV/bin/activate"

# build pool subsets (first N distinct session_ids, keeping full turn sequences)
for N in 32 64; do
  python - "$TRACE" "$N" "$OUTDIR/swe_pool${N}.jsonl" <<'PY'
import json,sys
trace,n,out=sys.argv[1],int(sys.argv[2]),sys.argv[3]
seen=[]; keep=set()
rows=[json.loads(l) for l in open(trace) if l.strip()]
for r in rows:
    s=r["session_id"]
    if s not in keep:
        if len(keep)>=n: continue
        keep.add(s); seen.append(s)
with open(out,"w") as f:
    for r in rows:
        if r["session_id"] in keep: f.write(json.dumps(r)+"\n")
print(f"pool{n}: {len(keep)} sessions -> {out}")
PY
done

echo "=== pool invariance: router=$ROUTER C=$C repeat=$REPEAT ==="
for N in 32 64; do
  OUT="$OUTDIR/pool${N}_${ROUTER}_c${C}.jsonl"; : > "$OUT"
  for r in $(seq 1 "$REPEAT"); do
    python "$REPO/scripts/trace_replay_driver_expC_yunuikang.py" \
      --trace "$OUTDIR/swe_pool${N}.jsonl" \
      --base-url http://localhost:$PORT --router-url http://localhost:$PORT \
      --backends http://localhost:8000 --model "$MODEL" --tokenizer "$MODEL" \
      --concurrency "$C" --num-programs "$N" \
      --router "$ROUTER" --run-tag "poolinv-${ROUTER}-pool${N}-c${C}-r${r}" \
      --out "$OUT" >/dev/null 2>>"$OUT.err"
    python -c "import json;d=json.loads(open('$OUT').read().splitlines()[-1]);print(f'  pool${N} r=$r thru={d[\"throughput_programs_per_s\"]:.3f}p/s hit={d[\"prefix_cache_hit_rate\"]:.3f}')" 2>/dev/null || echo "  pool$N r=$r parse-fail"
  done
done
echo "compare mean throughput of pool32 vs pool64 above; ~equal => stratified-64 confirmed."
