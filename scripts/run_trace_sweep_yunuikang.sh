#!/usr/bin/env bash
# Phase D concurrency sweep for ONE router mode against the 2-backend ThunderAgent
# proxy, using the TRACE REPLAY driver (real TraceLab/SWE-bench workload).
# Restarts the proxy in the requested router mode, sweeps concurrency, and does
# REPEAT repeats per point (error bars). Appends one JSON line per run to OUT.
#
# Usage: run_trace_sweep_yunuikang.sh <router: tr|default> <out.jsonl> <trace.jsonl> [C...]
# Env knobs: NPROG (programs/point, default 64), REPEAT (default 3),
#            TAG (dataset tag for run-tag/logs, default "tracelab")
set -uo pipefail
ROUTER="${1:?router (tr|default)}"
OUT="${2:?output jsonl path}"
TRACE="${3:?canonical trace jsonl}"
shift 3
CONCS=("$@"); [ ${#CONCS[@]} -eq 0 ] && CONCS=(2 4 8 16 32 48)

VENV=/home/yunuikang/yunuikang_work/.venv
REPO=/home/yunuikang/yunuikang_work/distserving
B0=http://localhost:8000; B1=http://localhost:8001
NPROG="${NPROG:-64}"; REPEAT="${REPEAT:-3}"; TAG="${TAG:-tracelab}"
source "$VENV/bin/activate"

# (re)start proxy in ROUTER mode with BOTH backends
OLD=$(pgrep -f "bin/thunderagent" | head -1); [ -n "$OLD" ] && kill "$OLD"; sleep 3
PLOG=/home/yunuikang/yunuikang_work/scratch/thunderagent_${TAG}_${ROUTER}.log; : > "$PLOG"
nohup thunderagent --backend-type vllm --backends "$B0,$B1" \
  --port 9000 --router "$ROUTER" --metrics --profile > "$PLOG" 2>&1 &
for i in $(seq 1 30); do curl -sf http://localhost:9000/health >/dev/null 2>&1 && break; sleep 2; done
echo "proxy up: $(curl -s http://localhost:9000/health | python -c 'import sys,json;d=json.load(sys.stdin);print(d["router_mode"],d["backends"])')"

: > "$OUT"
echo "sweep router=$ROUTER trace=$(basename "$TRACE") nprog=$NPROG repeat=$REPEAT concs=${CONCS[*]}"
for C in "${CONCS[@]}"; do
  for r in $(seq 1 "$REPEAT"); do
    python "$REPO/scripts/trace_replay_driver_yunuikang.py" \
      --trace "$TRACE" --base-url http://localhost:9000 --router-url http://localhost:9000 \
      --backends "$B0,$B1" --concurrency "$C" --num-programs "$NPROG" \
      --router "$ROUTER" --run-tag "${TAG}-${ROUTER}-c${C}-r${r}" \
      --out "$OUT" >/dev/null 2>>"$OUT.err"
    python -c "import json;d=json.loads(open('$OUT').read().splitlines()[-1]);print(f\"  $ROUTER c=$C r=$r thru={d['throughput_programs_per_s']:.2f}p/s p95={d['latency_p95_s']:.1f}s hit={d['prefix_cache_hit_rate']:.3f} split={list(d['per_backend_query_delta'].values())}\")"
  done
done
echo "done: $OUT"
