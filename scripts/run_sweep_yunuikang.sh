#!/usr/bin/env bash
# Concurrency sweep for one router mode against the 2-backend ThunderAgent proxy.
# Restarts the proxy in the requested router mode, then sweeps concurrency and
# appends one JSON line per run to the output file. Also records per-backend
# prefix-cache query deltas (routing-distribution evidence) into the JSON via
# the driver's own hit-rate + a side CSV here.
#
# Usage: run_sweep_yunuikang.sh <router: tr|default> <out.jsonl> [concurrencies...]
set -uo pipefail
ROUTER="${1:?router (tr|default)}"
OUT="${2:?output jsonl path}"
shift 2
CONCS=("$@"); [ ${#CONCS[@]} -eq 0 ] && CONCS=(8 16 32 48 64 96 128)

VENV=/home/yunuikang/yunuikang_work/.venv
REPO=/home/yunuikang/yunuikang_work/distserving
B0=http://localhost:8000; B1=http://localhost:8001
# Workload knobs (override via env). Defaults = light (§7) config.
TURNS="${TURNS:-4}"; SLEEP="${SLEEP:-0.4}"; MAXTOK="${MAXTOK:-256}"
CTX="${CTX:-0}"; NPROG_MULT="${NPROG_MULT:-2}"; NPROG_CAP="${NPROG_CAP:-100000}"
source "$VENV/bin/activate"

# (re)start proxy in ROUTER mode
OLD=$(pgrep -f "bin/thunderagent" | head -1); [ -n "$OLD" ] && kill "$OLD"; sleep 3
PLOG=/home/yunuikang/yunuikang_work/scratch/thunderagent_${ROUTER}.log; : > "$PLOG"
nohup thunderagent --backend-type vllm --backends "$B0,$B1" \
  --port 9000 --router "$ROUTER" --metrics --profile > "$PLOG" 2>&1 &
for i in $(seq 1 30); do curl -sf http://localhost:9000/health >/dev/null 2>&1 && break; sleep 2; done
echo "proxy up: $(curl -s http://localhost:9000/health | python -c 'import sys,json;d=json.load(sys.stdin);print(d["router_mode"],d["backends"])')"

q() { curl -s "$1/metrics" | awk '/^vllm:prefix_cache_queries_total/{print $2}'; }
: > "$OUT"
DIST=/home/yunuikang/yunuikang_work/scratch/dist_${ROUTER}.csv; echo "concurrency,b0_delta,b1_delta" > "$DIST"

for C in "${CONCS[@]}"; do
  N=$(( C*NPROG_MULT )); [ $N -lt 48 ] && N=48; [ $N -gt $NPROG_CAP ] && N=$NPROG_CAP
  q0b=$(q "$B0"); q1b=$(q "$B1")
  python "$REPO/scripts/workload_driver_yunuikang.py" \
    --concurrency "$C" --num-programs "$N" --turns "$TURNS" --tool-sleep "$SLEEP" \
    --max-tokens "$MAXTOK" --ctx-tokens "$CTX" \
    --router "$ROUTER" --out "$OUT" >/dev/null 2>>"$OUT.err"
  q0a=$(q "$B0"); q1a=$(q "$B1")
  d0=$(python -c "print(int($q0a-$q0b))"); d1=$(python -c "print(int($q1a-$q1b))")
  echo "$C,$d0,$d1" >> "$DIST"
  python -c "import json;d=json.loads(open('$OUT').read().splitlines()[-1]);print(f\"  $ROUTER c=$C n=$N thru={d['throughput_programs_per_s']:.2f}p/s lat_mean={d['latency_mean_s']:.2f} p95={d['latency_p95_s']:.2f} hit={d['prefix_cache_hit_rate']:.3f} preempt={int(d['num_preemptions_delta'])} split=$d0/$d1\")"
done
echo "done: $OUT ; distribution: $DIST"
