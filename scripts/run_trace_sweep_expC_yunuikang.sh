#!/usr/bin/env bash
# Experiment C concurrency sweep — ISOLATED from the SWE sweep.
#   backends: GPU2->8002, GPU3->8003   proxy: 9001   driver: *_expC (has --tool-scale)
#   Restarts ONLY the expC proxy (pgrep filtered to :9001), never the SWE proxy(:9000).
#   Per C point: starts the GPU2/3 sampler, runs REPEAT replays, stops the sampler.
#   Proxy restarted once per ROUTER (cache warms across C -> comparable to Phase D).
#
# Usage: run_trace_sweep_expC_yunuikang.sh <router: tr|default> <out.jsonl> <trace.jsonl> [C...]
# Env: NPROG (default 64), REPEAT (default 3), TAG (default tracelab),
#      TOOL_SCALE (default 1.0), SAMPLEDIR (default scratch/expC)
set -uo pipefail
ROUTER="${1:?router (tr|default)}"
OUT="${2:?output jsonl path}"
TRACE="${3:?canonical trace jsonl}"
shift 3
CONCS=("$@"); [ ${#CONCS[@]} -eq 0 ] && CONCS=(4 8 16 32)

VENV=/home/yunuikang/yunuikang_work/.venv
REPO=/home/yunuikang/yunuikang_work/distserving
B0=http://localhost:8002; B1=http://localhost:8003
PORT=9001
NPROG="${NPROG:-64}"; REPEAT="${REPEAT:-3}"; TAG="${TAG:-tracelab}"
TOOL_SCALE="${TOOL_SCALE:-1.0}"
LABEL="${LABEL:-${ROUTER}_ts${TOOL_SCALE}}"   # unique tag for sampler/profile files
SAMPLEDIR="${SAMPLEDIR:-$REPO/../scratch/expC}"
mkdir -p "$SAMPLEDIR"
source "$VENV/bin/activate"

# (re)start ONLY the expC proxy on :$PORT. Scan real /proc cmdlines (NUL-separated,
# so convert NUL->space first) and kill any thunderagent bound to :$PORT.
# The SWE proxy is on :9000 -> never matched. pgrep excludes itself.
PIDFILE="$SAMPLEDIR/expC_proxy.pid"
for pid in $(pgrep -f "bin/thunderagent" 2>/dev/null); do
  cl=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
  case " $cl " in
    *" --port $PORT "*) echo "kill stale expC proxy $pid"; kill "$pid" ;;
  esac
done
sleep 3
PROFDIR="$SAMPLEDIR/prof_${LABEL}"; mkdir -p "$PROFDIR"
PLOG="$SAMPLEDIR/thunderagent_${TAG}_${ROUTER}.log"; : > "$PLOG"
# PROXY_EXTRA: optional extra proxy flags (k_fit knob), e.g. "--use-acting-token-decay"
nohup thunderagent --backend-type vllm --backends "$B0,$B1" \
  --port "$PORT" --router "$ROUTER" --metrics --profile --profile-dir "$PROFDIR" \
  ${PROXY_EXTRA:-} > "$PLOG" 2>&1 &
echo $! > "$PIDFILE"
for i in $(seq 1 30); do curl -sf http://localhost:$PORT/health >/dev/null 2>&1 && break; sleep 2; done
MODE=$(curl -s http://localhost:$PORT/health | python -c 'import sys,json;print(json.load(sys.stdin)["router_mode"])' 2>/dev/null)
echo "proxy up: mode=$MODE backends=$(curl -s http://localhost:$PORT/health | python -c 'import sys,json;print(json.load(sys.stdin)["backends"])' 2>/dev/null)"
if [ "$MODE" != "$ROUTER" ]; then
  echo "FATAL: proxy on :$PORT is router=$MODE but expected $ROUTER (stale proxy squatting port?). Aborting sweep." >&2
  exit 3
fi

: > "$OUT"
echo "expC sweep router=$ROUTER trace=$(basename "$TRACE") nprog=$NPROG repeat=$REPEAT tool_scale=$TOOL_SCALE concs=${CONCS[*]}"
for C in "${CONCS[@]}"; do
  SAMP="$SAMPLEDIR/sample_${LABEL}_c${C}.csv"; : > "$SAMP"
  python "$REPO/scripts/sample_gpu_resident_yunuikang.py" --gpus 2,3 \
    --health-url http://localhost:$PORT/health --backends "$B0,$B1" \
    --out "$SAMP" --interval 1.0 &
  SPID=$!
  for r in $(seq 1 "$REPEAT"); do
    python "$REPO/scripts/trace_replay_driver_expC_yunuikang.py" \
      --trace "$TRACE" --base-url http://localhost:$PORT --router-url http://localhost:$PORT \
      --backends "$B0,$B1" --concurrency "$C" --num-programs "$NPROG" \
      --tool-scale "$TOOL_SCALE" \
      --router "$ROUTER" --run-tag "${TAG}-${ROUTER}-ts${TOOL_SCALE}-c${C}-r${r}" \
      --out "$OUT" >/dev/null 2>>"$OUT.err"
    python -c "import json;d=json.loads(open('$OUT').read().splitlines()[-1]);print(f\"  $ROUTER ts=$TOOL_SCALE c=$C r=$r thru={d['throughput_programs_per_s']:.2f}p/s p95={d['latency_p95_s']:.1f}s hit={d['prefix_cache_hit_rate']:.3f} split={list(d['per_backend_query_delta'].values())}\")"
  done
  kill "$SPID" 2>/dev/null; wait "$SPID" 2>/dev/null
  echo "  sampler stopped -> $SAMP ($(wc -l < "$SAMP") rows)"
done
echo "done: $OUT"
