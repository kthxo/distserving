#!/usr/bin/env bash
# 재프리필 참값 마이크로벤치 (GPU 제안 1+2+3을 한 런으로)
#  - expC와 동일 조건: GPU2/GPU3 -> 8002/8003, 프록시 9011, tracelab_fit32k.jsonl, C=16
#  - NPROG=32 (expC의 64를 절반으로 축소)
#  - ★ --stream 추가 -> prefill_s/decode_s 복구 (제안 2)
#  - 실행 전후 /metrics 스냅샷 -> local_compute = 참 재프리필 (제안 1)
# router.py 미수정. 드라이버 미수정. 스냅샷은 별도 스크립트.
set -uo pipefail
cd /home/yunuikang/yunuikang_work/distserving
source /home/yunuikang/yunuikang_work/.venv/bin/activate

OUT=/home/yunuikang/yunuikang_work/scratch/vprof
TRACE=/home/yunuikang/yunuikang_work/scratch/traces/tracelab_fit32k.jsonl
BACKENDS="http://localhost:8002,http://localhost:8003"
PORT=9011
C=16
NPROG=32
RESULT=$OUT/vprof_metrics.jsonl

for ROUTER in default tr; do
  echo "=================== router=$ROUTER ==================="
  # --- 프록시 기동 (9011만 정리) ---
  for pid in $(ps -eo pid= -o args= | tr '\0' ' ' | grep -E "thunderagent.*--port $PORT" | grep -v grep | awk '{print $1}'); do
    echo "[kill] stale proxy pid=$pid"; kill -9 "$pid" 2>/dev/null
  done
  sleep 2
  thunderagent --backend-type vllm --backends "$BACKENDS" --port $PORT \
    --router "$ROUTER" --metrics --profile --profile-dir "$OUT/prof_${ROUTER}" \
    > "$OUT/proxy_${ROUTER}.log" 2>&1 &
  PROXY_PID=$!
  echo "[proxy] pid=$PROXY_PID router=$ROUTER"

  # --- health + router assertion (오염 방지: expC 버그1 재발 차단) ---
  for i in $(seq 1 40); do
    H=$(curl -s http://localhost:$PORT/health 2>/dev/null) && [ -n "$H" ] && break
    sleep 1
  done
  MODE=$(echo "$H" | python3 -c "import sys,json; print(json.load(sys.stdin).get('router_mode','?'))" 2>/dev/null)
  echo "[assert] router_mode=$MODE (expected $ROUTER)"
  if [ "$MODE" != "$ROUTER" ]; then echo "!! ROUTER MISMATCH — abort"; kill -9 $PROXY_PID; exit 2; fi

  # --- 샘플러 (GPU2/3) ---
  python3 scripts/sample_gpu_resident_yunuikang.py \
    --gpus 2,3 --backends "$BACKENDS" --health-url "http://localhost:$PORT/health" \
    --out "$OUT/sample_${ROUTER}_c${C}.csv" > "$OUT/sampler_${ROUTER}.log" 2>&1 &
  SAMP_PID=$!

  # --- 측정 (드라이버는 subprocess, 전후 /metrics 스냅샷) ---
  python3 scripts/microbench_recompute_yunuikang.py \
    --backends "$BACKENDS" --label "${ROUTER}_c${C}" --out "$RESULT" \
    --driver-cmd "python3 scripts/trace_replay_driver_expC_yunuikang.py \
        --trace $TRACE --base-url http://localhost:$PORT \
        --backends $BACKENDS --router $ROUTER \
        --concurrency $C --num-programs $NPROG --stream --tool-scale 1.0 \
        --run-tag vprof-${ROUTER}-c${C} --out $OUT/vprof_${ROUTER}.jsonl"

  kill -9 $SAMP_PID 2>/dev/null
  kill -9 $PROXY_PID 2>/dev/null
  sleep 3
done
echo "=================== DONE ==================="
cat $RESULT
