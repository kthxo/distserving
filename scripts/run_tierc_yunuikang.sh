#!/usr/bin/env bash
# Tier C 시간 분해 — H200 러너 (MORI · TA+O × C{40,80} @ fit 20)
#
# 가설: MORI 가 recompute 를 reload 로 바꿔서 TA+O 보다 **decode 몫이 크다** → throughput 우위.
# 검증: GPU 시간을 [decode / prefill_new / prefill_recompute / idle] 로 분해해 직접 본다.
#
# ※ 엔진 계측은 **프로그램 완주와 무관**하다 (step 단위 CUDA event).
#   따라서 1시간 창이 필요 없다 — 기본 25분이면 충분하다. 4셀 ≈ 2.5시간.
# ※ 5090 스모크(scripts/run_tierc_smoke_yunuikang.sh)를 통과한 뒤에만 돌린다.
#
# 실행:  bash scripts/run_tierc_yunuikang.sh              # C40 → C80
#        CLIST="80" bash scripts/run_tierc_yunuikang.sh   # C80 만
set -uo pipefail
REPO=/home/yunuikang/yunuikang_work/distserving
VENV=/home/yunuikang/yunuikang_work/.venv
TRACE=/home/yunuikang/yunuikang_work/scratch/traces/tracelab_moriM_L64k_yunuikang.jsonl
MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}"
SERVE="${SERVE:-$REPO/scripts/_serve_sglang_7b_tp1_h200_mori_yunuikang.sh}"
BP=8123; PP=9000
MAXTOK="${MAXTOK:-647520}"        # fit 20.00 (= Phase 2 격자와 동일)
FIT_DEN=32376; RATIO="${RATIO:-2}"
CLIST="${CLIST:-40 80}"
DUR="${DUR:-1500}"; GRACE="${GRACE:-60}"; WARM="${WARM:-0.2}"
OUT="${OUT:-/home/yunuikang/yunuikang_work/scratch/mori/tierc_h200}"
RES=$OUT/results_tierc.jsonl
HM="sglang:hicache_host_used_tokens,sglang:hicache_host_total_tokens,sglang:evicted_tokens_total,sglang:load_back_tokens_total,sglang:cached_tokens_total,sglang:prompt_tokens_total,sglang:generation_tokens_total"
mkdir -p "$OUT"; touch "$RES"
source "$VENV/bin/activate"

BPID=""
kill_backend(){ [ -n "$BPID" ] && kill "$BPID" 2>/dev/null
  # ★ SIGTERM 먼저 — 계측이 잔여 CUDA event 를 회수하고 flush 할 시간을 준다 (SIGKILL 은 못 잡는다)
  pkill -f "_serve_sglang_.*_h200_mori_yunuikang" 2>/dev/null
  pkill -f "sglang.launch_server" 2>/dev/null; pkill -f "sglang::" 2>/dev/null
  sleep 6
  pkill -9 -f "_serve_sglang_.*_h200_mori_yunuikang" 2>/dev/null
  pkill -9 -f "sglang.launch_server" 2>/dev/null; pkill -9 -f "sglang::" 2>/dev/null
  sleep 6; BPID=""; }
kill_proxy(){ for pid in $(pgrep -f "bin/thunderagent" 2>/dev/null); do
  cl=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null); case " $cl " in *" --port $PP "*) kill "$pid";; esac; done; sleep 2; }
trap 'kill_proxy; kill_backend' EXIT
wait_gpu_idle(){ for i in $(seq 1 40); do
  n=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -c . || echo 0)
  [ "$n" = "0" ] && return 0; sleep 2; done; kill_backend; }

boot(){ # $1=EVICT $2=TAG
  kill_proxy; kill_backend; wait_gpu_idle
  echo "==[backend $1] boot $(TZ=Asia/Seoul date +%H:%M:%S) KST (DRAM $(free -g|awk '/^Mem:/{print $7}')GiB)"
  MORI_TIERC=1 MORI_TIERC_TAG="$2" MORI_TIERC_OUT="$OUT/steplog_$2.jsonl" \
  MODEL="$MODEL" MAXTOK=$MAXTOK RATIO="$RATIO" EVICT="$1" PORT=$BP \
    LOG="$OUT/serve_$2.log" nohup bash "$SERVE" >/dev/null 2>&1 &
  BPID=$!
  for i in $(seq 1 320); do
    curl -sf "http://127.0.0.1:$BP/health" >/dev/null 2>&1 && { echo "   READY ~$((i*3))s"; break; }
    kill -0 "$BPID" 2>/dev/null || { echo "   !! DIED"; tail -5 "$OUT/serve_$2.log"; return 1; }
    sleep 3; done
  curl -sf "http://127.0.0.1:$BP/health" >/dev/null 2>&1 || { echo "   !! TIMEOUT"; return 1; }
  grep -qa "\[tierc\] 계측 ON" "$OUT/serve_$2.log" || { echo "   !! [tierc] 배너 없음 — 계측 미적용"; return 1; }
  echo "   [tierc] $(grep -am1 -o 'steplog=[^ ]*' "$OUT/serve_$2.log")"
  G=$(grep -am1 -o "max_total_num_tokens=[0-9]*" "$OUT/serve_$2.log"|cut -d= -f2)
  H=$(curl -s "http://127.0.0.1:$BP/metrics"|grep -m1 "^sglang:hicache_host_total_tokens"|awk '{print $2}')
  python3 - "$G" "$H" "$RATIO" "$MAXTOK" "$FIT_DEN" <<'PY' || { echo "   !! FATAL assert"; return 1; }
import sys
g,h,r,pin,den=int(sys.argv[1]),float(sys.argv[2]),float(sys.argv[3]),int(sys.argv[4]),int(sys.argv[5])
print(f"   [assert] GPU={g:,} (기대 {pin:,}) host={h:,.0f} (기대 {r*pin:,.0f}) fit={g/den:.2f}")
sys.exit(1 if (g!=pin or abs(h-r*pin)>pin*0.02) else 0)
PY
}

cell(){ # $1=tag $2=system $3=router $4=C $5=extra
  grep -qa "\"run_tag\": \"$1\"" "$RES" 2>/dev/null && { echo "[cell $1] SKIP (이미 있음)"; return 0; }
  echo "[cell $1] START $(TZ=Asia/Seoul date +%H:%M:%S) KST  C=$4 dur=${DUR}s"
  kill_proxy
  PDIR="$OUT/profile_$1"; rm -rf "$PDIR"; mkdir -p "$PDIR"
  nohup thunderagent --backend-type sglang --backends "http://localhost:$BP" --port $PP \
    --router "$3" --metrics --profile --profile-dir "$PDIR" $5 > "$OUT/proxy_$1.log" 2>&1 &
  for i in $(seq 1 60); do curl -sf "http://127.0.0.1:$PP/health" >/dev/null 2>&1 && break; sleep 1; done
  M=$(curl -s "http://127.0.0.1:$PP/health"|python -c 'import sys,json;print(json.load(sys.stdin)["router_mode"])' 2>/dev/null)
  [ "$M" = "$3" ] || { echo "[cell $1] FATAL router=$M"; return 1; }
  nohup python "$REPO/scripts/phase2_engine_sampler_yunuikang.py" --backend "http://localhost:$BP" \
    --out "$OUT/engine_$1.csv" --interval 5 >/dev/null 2>&1 & EPID=$!
  T0=$(python3 -c 'import time;print(f"{time.time():.3f}")')
  timeout $((DUR+GRACE+600)) python "$REPO/scripts/mori_replay_driver_yunuikang.py" --trace "$TRACE" \
    --base-url "http://localhost:$PP" --router-url "http://localhost:$PP" --backends "http://localhost:$BP" \
    --model "$MODEL" --tokenizer "$MODEL" --router "$3" --system "$2" \
    --concurrency "$4" --duration-s $DUR --deadline-grace-s $GRACE --warmup-frac $WARM --metric-interval 30 \
    --ctx-cap 69632 --http-timeout 2400 \
    --hicache-metrics "$HM" --run-tag "$1" --out "$RES" 2>"$OUT/err_$1.log" || echo "   driver rc=$?"
  T1=$(python3 -c 'import time;print(f"{time.time():.3f}")')
  kill "$EPID" 2>/dev/null || true
  python3 -c "
import json
json.dump({'tag':'$1','system':'$2','t_start':float('$T0'),'t_end':float('$T1'),
           'C':$4,'dur_s':$DUR,'warm':$WARM,'ratio':$RATIO,'maxtok':$MAXTOK},
          open('$OUT/window_$1.json','w'))"
  echo "[cell $1] DONE $(TZ=Asia/Seoul date +%H:%M:%S) KST"
}

echo "######## Tier C (H200) 시작 $(TZ=Asia/Seoul date '+%m/%d %H:%M') KST ########"
echo "  MAXTOK=$MAXTOK (fit $(python3 -c "print(f'{$MAXTOK/$FIT_DEN:.2f}')")) · r=$RATIO · C: $CLIST · 셀 ${DUR}s"
echo "  out=$OUT"

for C in $CLIST; do
  boot mori "MORI_C${C}" || exit 1
  cell "MORI_C${C}" MORI mori "$C" "--mori-cpu-capacity-ratio $RATIO" || exit 1
  boot lru  "TAO_C${C}"  || exit 1
  cell "TAO_C${C}"  TAO  tr  "$C" "" || exit 1
done
kill_proxy; kill_backend

echo
echo "######## 집계 ########"
python3 "$REPO/scripts/analyze_tierc_yunuikang.py" --dir "$OUT"
