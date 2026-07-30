#!/usr/bin/env bash
# MORI headline eval runner (goguma6). Clones run_serving_eval_yunuikang.sh:
# single SGLang backend (:8100) + ThunderAgent proxy (:9000) + fixed-1h replay.
# System selector maps <system> -> (proxy router mode, expected backend HiCache).
#
# Usage: run_mori_eval_yunuikang.sh <system: smg|ta|tao|mori> <out.jsonl> <trace> [C...]
# Env: BACKEND(:8100) PROXY_PORT(9000) R(hicache ratio label for tao|mori, 1|2)
#      DURATION(3600) REPEAT(1) MODEL(Qwen/Qwen3-8B) SAMPLEDIR
#
# IMPORTANT: the SGLang backend must ALREADY be serving with the HiCache/eviction
# config matching <system> (start it with _serve_sglang_8b_tp2_mori_yunuikang.sh):
#   smg -> RATIO=0 EVICT=lru | ta -> RATIO=0 EVICT=lru
#   tao -> RATIO=$R EVICT=lru | mori -> RATIO=$R EVICT=mori
# This runner only (re)starts the :9000 proxy and drives the replay.
set -uo pipefail
SYS="${1:?system: smg|ta|tao|mori}"
OUT="${2:?output jsonl}"
TRACE="${3:?canonical trace jsonl}"
shift 3
CONCS=("$@"); [ ${#CONCS[@]} -eq 0 ] && CONCS=(20 50 80)

REPO=/home/yunuikang/yunuikang_work/distserving
VENV=/home/yunuikang/yunuikang_work/.venv
BACKEND="${BACKEND:-http://localhost:8100}"
PORT="${PROXY_PORT:-9000}"
R="${R:-1}"; DURATION="${DURATION:-3600}"; REPEAT="${REPEAT:-1}"
MODEL="${MODEL:-Qwen/Qwen3-8B}"
SAMPLEDIR="${SAMPLEDIR:-/home/yunuikang/yunuikang_work/scratch/mori}"
mkdir -p "$SAMPLEDIR"

# system -> proxy router mode + label + scheduler extra
case "$SYS" in
  smg)  ROUTER=default; RATIO_LBL=0; EXTRA="" ;;
  ta)   ROUTER=tr;      RATIO_LBL=0; EXTRA="" ;;
  tao)  ROUTER=tr;      RATIO_LBL=$R; EXTRA="" ;;
  mori) ROUTER=mori;    RATIO_LBL=$R; EXTRA="--mori-cpu-capacity-ratio $R" ;;
  *) echo "FATAL: unknown system $SYS" >&2; exit 2 ;;
esac
source "$VENV/bin/activate"

# (re)start ONLY the :$PORT proxy (kill stale thunderagent on this port).
for pid in $(pgrep -f "bin/thunderagent" 2>/dev/null); do
  cl=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
  case " $cl " in *" --port $PORT "*) echo "kill stale proxy $pid"; kill "$pid" ;; esac
done
sleep 3
PLOG="$SAMPLEDIR/thunderagent_${SYS}_r${RATIO_LBL}.log"; : > "$PLOG"
nohup thunderagent --backend-type sglang --backends "$BACKEND" \
  --port "$PORT" --router "$ROUTER" --metrics $EXTRA > "$PLOG" 2>&1 &
echo $! > "$SAMPLEDIR/proxy_${PORT}.pid"
for i in $(seq 1 30); do curl -sf "http://localhost:$PORT/health" >/dev/null 2>&1 && break; sleep 2; done
MODE=$(curl -s "http://localhost:$PORT/health" | python -c 'import sys,json;print(json.load(sys.stdin)["router_mode"])' 2>/dev/null)
echo "proxy up: system=$SYS mode=$MODE backend=$BACKEND ratio=$RATIO_LBL"
if [ "$MODE" != "$ROUTER" ]; then
  echo "FATAL: proxy router=$MODE but system=$SYS expects $ROUTER" >&2; exit 3
fi

: > "$OUT"
echo "MORI eval system=$SYS trace=$(basename "$TRACE") dur=${DURATION}s repeat=$REPEAT concs=${CONCS[*]}"
for C in "${CONCS[@]}"; do
  SLOG="$SAMPLEDIR/gpu_${SYS}_r${RATIO_LBL}_C${C}.jsonl"
  nohup python "$REPO/scripts/sample_gpu_resident_yunuikang.py" --gpus 0,1 --out "$SLOG" \
    --health-url "http://localhost:$PORT/health" --backends "$BACKEND" >/dev/null 2>&1 &
  SPID=$!
  for rep in $(seq 1 "$REPEAT"); do
    echo "  [C=$C rep=$rep] fixed ${DURATION}s ..."
    python "$REPO/scripts/mori_replay_driver_yunuikang.py" \
      --trace "$TRACE" --base-url "http://localhost:$PORT" --router-url "http://localhost:$PORT" \
      --backends "$BACKEND" --model "$MODEL" --tokenizer "$MODEL" \
      --router "$ROUTER" --system "$SYS" --concurrency "$C" --duration-s "$DURATION" \
      --hicache-ratio "$RATIO_LBL" --run-tag "${SYS}_r${RATIO_LBL}_C${C}_rep${rep}" --out "$OUT"
  done
  kill "$SPID" 2>/dev/null || true
done
echo "done -> $OUT"
