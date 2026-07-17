#!/usr/bin/env bash
# P1 serving-eval concurrency sweep — SINGLE backend (Deployment A: one TP2 vLLM
# instance) + ThunderAgent proxy in front. Serving-eval semantics (not 2-backend
# routing). Isolated copy of run_trace_sweep_expC (single backend, GPU1+2 sampler).
#   backend: :8000 (TP2 Qwen3-32B on GPU1+GPU2)   proxy: :9000   sampler: --gpus 1,2
#   Restarts ONLY the :9000 proxy (never a :9001/:9000-other proxy of someone else).
#   Per C: start GPU1/2 sampler, run REPEAT replays, stop sampler.
#
# Usage: run_serving_eval_yunuikang.sh <router: tr|default> <out.jsonl> <trace.jsonl> [C...]
# Env: NPROG (256), REPEAT (3), TAG (tracelab), MODEL (Qwen/Qwen3-32B),
#      TOOL_SCALE (1.0), SAMPLEDIR (scratch/tp2), PROXY_EXTRA, LABEL
set -uo pipefail
ROUTER="${1:?router (tr|default)}"
OUT="${2:?output jsonl path}"
TRACE="${3:?canonical trace jsonl}"
shift 3
CONCS=("$@"); [ ${#CONCS[@]} -eq 0 ] && CONCS=(16 32 64 128 256)

VENV=/home/yunuikang/yunuikang_work/.venv
REPO=/home/yunuikang/yunuikang_work/distserving
B0=http://localhost:8000
PORT=9000
NPROG="${NPROG:-256}"; REPEAT="${REPEAT:-3}"; TAG="${TAG:-tracelab}"
# NPROG_MODE=scale -> per-C NPROG = max(NPROG_MIN, 2*C) (keeps low-C fast, high-C >= C).
NPROG_MODE="${NPROG_MODE:-fixed}"; NPROG_MIN="${NPROG_MIN:-96}"
MODEL="${MODEL:-Qwen/Qwen3-32B}"
TOOL_SCALE="${TOOL_SCALE:-1.0}"
LABEL="${LABEL:-${ROUTER}_ts${TOOL_SCALE}}"
SAMPLEDIR="${SAMPLEDIR:-$REPO/../scratch/tp2}"
mkdir -p "$SAMPLEDIR"
source "$VENV/bin/activate"

# (re)start ONLY the :$PORT proxy. Scan real /proc cmdlines (NUL->space) and kill
# any thunderagent bound to :$PORT. pgrep excludes itself.
PIDFILE="$SAMPLEDIR/tp2_proxy.pid"
for pid in $(pgrep -f "bin/thunderagent" 2>/dev/null); do
  cl=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
  case " $cl " in
    *" --port $PORT "*) echo "kill stale proxy $pid"; kill "$pid" ;;
  esac
done
sleep 3
PROFDIR="$SAMPLEDIR/prof_${LABEL}"; mkdir -p "$PROFDIR"
PLOG="$SAMPLEDIR/thunderagent_${TAG}_${ROUTER}.log"; : > "$PLOG"
nohup thunderagent --backend-type vllm --backends "$B0" \
  --port "$PORT" --router "$ROUTER" --metrics --profile --profile-dir "$PROFDIR" \
  ${PROXY_EXTRA:-} > "$PLOG" 2>&1 &
echo $! > "$PIDFILE"
for i in $(seq 1 30); do curl -sf http://localhost:$PORT/health >/dev/null 2>&1 && break; sleep 2; done
MODE=$(curl -s http://localhost:$PORT/health | python -c 'import sys,json;print(json.load(sys.stdin)["router_mode"])' 2>/dev/null)
echo "proxy up: mode=$MODE backends=$(curl -s http://localhost:$PORT/health | python -c 'import sys,json;print(json.load(sys.stdin)["backends"])' 2>/dev/null)"
if [ "$MODE" != "$ROUTER" ]; then
  echo "FATAL: proxy on :$PORT is router=$MODE but expected $ROUTER. Aborting." >&2
  exit 3
fi

: > "$OUT"
echo "serving-eval sweep router=$ROUTER trace=$(basename "$TRACE") model=$MODEL nprog=$NPROG repeat=$REPEAT concs=${CONCS[*]}"
for C in "${CONCS[@]}"; do
  if [ "$NPROG_MODE" = "scale" ]; then
    NP=$(( 2*C )); [ "$NP" -lt "$NPROG_MIN" ] && NP="$NPROG_MIN"
  else
    NP="$NPROG"
  fi
  echo "  [C=$C NPROG=$NP]"
  SAMP="$SAMPLEDIR/sample_${LABEL}_c${C}.csv"; : > "$SAMP"
  python "$REPO/scripts/sample_gpu_resident_yunuikang.py" --gpus 1,2 \
    --health-url http://localhost:$PORT/health --backends "$B0" \
    --out "$SAMP" --interval 1.0 &
  SPID=$!
  for r in $(seq 1 "$REPEAT"); do
    python "$REPO/scripts/trace_replay_driver_expC_yunuikang.py" \
      --trace "$TRACE" --base-url http://localhost:$PORT --router-url http://localhost:$PORT \
      --backends "$B0" --model "$MODEL" --tokenizer "$MODEL" \
      --concurrency "$C" --num-programs "$NP" --tool-scale "$TOOL_SCALE" \
      --router "$ROUTER" --run-tag "${TAG}-${ROUTER}-c${C}-r${r}" \
      --out "$OUT" >/dev/null 2>>"$OUT.err"
    python -c "import json;d=json.loads(open('$OUT').read().splitlines()[-1]);print(f\"  $ROUTER c=$C r=$r thru={d['throughput_programs_per_s']:.3f}p/s p95={d['latency_p95_s']:.1f}s hit={d['prefix_cache_hit_rate']:.3f}\")" 2>/dev/null || echo "  $ROUTER c=$C r=$r (summary parse failed, see $OUT)"
  done
  kill "$SPID" 2>/dev/null; wait "$SPID" 2>/dev/null
  echo "  sampler stopped -> $SAMP ($(wc -l < "$SAMP") rows)"
done
echo "done: $OUT"
