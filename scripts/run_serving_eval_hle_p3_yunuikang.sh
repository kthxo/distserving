#!/usr/bin/env bash
# P3 HLE replay sweep — SINGLE backend (Nemotron-8B orchestrator :8100, GPU1) + proxy.
# Replays the 24h-distribution HLE trace (tail included). Captures reported hit AND
# true hit via vllm:prompt_tokens_by_source{local_compute}. Isolated copy.
# Usage: run_serving_eval_hle_p3_yunuikang.sh <router: tr|default> <out.jsonl> <trace.jsonl> [C...]
set -uo pipefail
ROUTER="${1:?router}"; OUT="${2:?out}"; TRACE="${3:?trace}"; shift 3
CONCS=("$@"); [ ${#CONCS[@]} -eq 0 ] && CONCS=(24 32 40 48)
VENV=/home/yunuikang/yunuikang_work/.venv; REPO=/home/yunuikang/yunuikang_work/distserving
B0=http://127.0.0.1:8100; PORT=9000
MODEL=orchestrator
TOKENIZER=/home/yunuikang/yunuikang_work/scratch/p3_assets/orchestrator
NPROG_MIN="${NPROG_MIN:-96}"; REPEAT="${REPEAT:-3}"; TAG="${TAG:-hle}"
LABEL="${LABEL:-${ROUTER}}"; SAMPLEDIR="${SAMPLEDIR:-$REPO/../scratch/p3/sweep}"
mkdir -p "$SAMPLEDIR"; source "$VENV/bin/activate"

# fresh proxy on :$PORT (kill only :$PORT thunderagent)
for pid in $(pgrep -f "bin/thunderagent" 2>/dev/null); do
  cl=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
  case " $cl " in *" --port $PORT "*) kill "$pid";; esac
done
sleep 3
PROFDIR="$SAMPLEDIR/prof_${LABEL}"; mkdir -p "$PROFDIR"
nohup thunderagent --backend-type vllm --backends "$B0" --port "$PORT" --router "$ROUTER" \
  --metrics --profile --profile-dir "$PROFDIR" > "$SAMPLEDIR/proxy_${ROUTER}.log" 2>&1 &
for i in $(seq 1 30); do curl -sf http://127.0.0.1:$PORT/health >/dev/null 2>&1 && break; sleep 2; done
MODE=$(curl -s http://127.0.0.1:$PORT/health | python -c 'import sys,json;print(json.load(sys.stdin)["router_mode"])' 2>/dev/null)
[ "$MODE" = "$ROUTER" ] || { echo "FATAL proxy mode=$MODE != $ROUTER"; exit 3; }
echo "proxy up mode=$MODE"

# true-hit metric helper (prompt_tokens_by_source)
lc_snap(){ curl -s $B0/metrics 2>/dev/null | grep -oE "prompt_tokens_by_source_total\{[^}]*source=\"$1\"[^}]*\} [0-9.e+]+" | grep -oE "[0-9.e+]+$" | tail -1; }
tot_snap(){ curl -s $B0/metrics 2>/dev/null | grep -oE "vllm:prompt_tokens_total\{[^}]*\} [0-9.e+]+" | grep -oE "[0-9.e+]+$" | tail -1; }

: > "$OUT"
echo "HLE sweep router=$ROUTER trace=$(basename "$TRACE") nprog_min=$NPROG_MIN repeat=$REPEAT concs=${CONCS[*]}"
for C in "${CONCS[@]}"; do
  NP=$(( 2*C )); [ "$NP" -lt "$NPROG_MIN" ] && NP="$NPROG_MIN"
  echo "  [C=$C NPROG=$NP]"
  SAMP="$SAMPLEDIR/sample_${LABEL}_c${C}.csv"; : > "$SAMP"
  python "$REPO/scripts/sample_gpu_resident_yunuikang.py" --gpus 1 \
    --health-url http://127.0.0.1:$PORT/health --backends "$B0" --out "$SAMP" --interval 1.0 &
  SPID=$!
  for r in $(seq 1 "$REPEAT"); do
    lc0=$(lc_snap local_compute); tp0=$(tot_snap)
    python "$REPO/scripts/trace_replay_driver_expC_yunuikang.py" \
      --trace "$TRACE" --base-url http://127.0.0.1:$PORT --router-url http://127.0.0.1:$PORT \
      --backends "$B0" --model "$MODEL" --tokenizer "$TOKENIZER" \
      --concurrency "$C" --num-programs "$NP" --stream \
      --router "$ROUTER" --run-tag "${TAG}-${ROUTER}-c${C}-r${r}" --out "$OUT" >/dev/null 2>>"$OUT.err"
    lc1=$(lc_snap local_compute); tp1=$(tot_snap)
    # true hit = 1 - local_compute_delta/total_prompt_tokens_delta
    python3 -c "
import json
d=json.loads(open('$OUT').read().splitlines()[-1])
lc=(${lc1:-0})-(${lc0:-0}); tp=(${tp1:-0})-(${tp0:-0})
truehit=1-lc/tp if tp>0 else float('nan')
d['true_hit_local_compute']=round(truehit,4)
lines=open('$OUT').read().splitlines(); lines[-1]=json.dumps(d); open('$OUT','w').write('\n'.join(lines)+'\n')
print(f\"  $ROUTER c=$C r=$r thru={d['throughput_programs_per_s']:.3f}p/s p95={d['latency_p95_s']:.1f}s hit_rep={d['prefix_cache_hit_rate']:.3f} hit_true={truehit:.3f}\")
" 2>/dev/null || echo "  $ROUTER c=$C r=$r (summary parse fail)"
  done
  kill "$SPID" 2>/dev/null; wait "$SPID" 2>/dev/null
  echo "  sampler -> $SAMP ($(wc -l < "$SAMP") rows)"
done
echo "done: $OUT"
