#!/usr/bin/env bash
# Tier C 계측 — 5090 소형 스모크 게이트 (push 전 필수)
#
# 목적: H200 에서 디버깅 없이 바로 돌 수 있는지 여기서 확인한다.
#   1) steplog jsonl 이 정상 기록되고 값이 sane 한가
#   2) closure 통과: decode+prefill+idle ≈ window_wall (±5%)
#   3) HiCache: 오프로딩계(MORI·TA+O)만 transfer_tok > 0
#   4) analyze 스크립트가 end-to-end 로 도는가 (그림까지)
#   5) (덤) 5090 Tier C 결과 확보 → H200 대조에 씀
#
# 소형: C=8 · fit 8.10(MAXTOK 262144) · 기본 5분 · MORI/TA+O 각 1셀.
# 엔진 계측은 프로그램 완주와 무관하므로 짧은 창으로 충분하다.
set -uo pipefail
REPO=/home/yunuikang/yunuikang_work/distserving
VENV=/home/yunuikang/yunuikang_work/.venv
TRACE=/home/yunuikang/yunuikang_work/scratch/traces/tracelab_moriM_L64k_yunuikang.jsonl
BP=8123; PP=9000; PIN=262144; FIT_DEN=32376
C="${C:-8}"; DUR="${DUR:-300}"; GRACE="${GRACE:-45}"; WARM="${WARM:-0.2}"; RATIO="${RATIO:-2}"
OUT="${OUT:-/home/yunuikang/yunuikang_work/scratch/mori/tierc_smoke}"
RES=$OUT/results_smoke.jsonl
HM="sglang:hicache_host_used_tokens,sglang:hicache_host_total_tokens,sglang:evicted_tokens_total,sglang:load_back_tokens_total,sglang:cached_tokens_total,sglang:prompt_tokens_total,sglang:generation_tokens_total"
mkdir -p "$OUT"; touch "$RES"
source "$VENV/bin/activate"

BPID=""
kill_backend(){ [ -n "$BPID" ] && kill "$BPID" 2>/dev/null
  # ★ SIGTERM 먼저 — 계측이 잔여 CUDA event 를 회수하고 flush 할 시간을 준다 (SIGKILL 은 못 잡는다)
  pkill -f "_serve_sglang_8b_tp2_mori_yunuikang" 2>/dev/null
  pkill -f "sglang.launch_server" 2>/dev/null; pkill -f "sglang::" 2>/dev/null
  sleep 6
  pkill -9 -f "_serve_sglang_8b_tp2_mori_yunuikang" 2>/dev/null
  pkill -9 -f "sglang.launch_server" 2>/dev/null; pkill -9 -f "sglang::" 2>/dev/null
  sleep 6; BPID=""; }
kill_proxy(){ for pid in $(pgrep -f "bin/thunderagent" 2>/dev/null); do
  cl=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null); case " $cl " in *" --port $PP "*) kill "$pid";; esac; done; sleep 2; }
trap 'kill_proxy; kill_backend' EXIT
wait_gpu_idle(){ for i in $(seq 1 40); do
  n=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -c . || echo 0)
  [ "$n" = "0" ] && return 0; sleep 2; done; kill_backend; }

boot(){ # $1=EVICT $2=TAG [$3=RATIO override] — 계측 env 를 백엔드 프로세스에 주입한다
  local R="${3:-$RATIO}"
  kill_proxy; kill_backend; wait_gpu_idle
  echo "==[backend $1] boot $(TZ=Asia/Seoul date +%H:%M:%S) KST  (DRAM $(free -g|awk '/^Mem:/{print $7}')GiB)"
  MORI_TIERC=1 MORI_TIERC_TAG="$2" MORI_TIERC_OUT="$OUT/steplog_$2.jsonl" \
  MAXTOK=$PIN RATIO="$R" EVICT="$1" PORT=$BP MEMFRAC=0.85 \
    LOG="$OUT/serve_$2.log" nohup bash "$REPO/scripts/_serve_sglang_8b_tp2_mori_yunuikang.sh" >/dev/null 2>&1 &
  BPID=$!
  for i in $(seq 1 320); do
    curl -sf "http://127.0.0.1:$BP/health" >/dev/null 2>&1 && { echo "   READY ~$((i*3))s"; break; }
    kill -0 "$BPID" 2>/dev/null || { echo "   !! DIED"; tail -5 "$OUT/serve_$2.log"; return 1; }
    sleep 3; done
  curl -sf "http://127.0.0.1:$BP/health" >/dev/null 2>&1 || { echo "   !! TIMEOUT"; return 1; }
  # 계측이 실제로 걸렸는지 — serve 로그에 tierc 배너가 있어야 한다
  if grep -qa "\[tierc\] 계측 ON" "$OUT/serve_$2.log"; then
    echo "   [tierc] 배너 확인: $(grep -am1 -o 'steplog=[^ ]*' "$OUT/serve_$2.log")"
  else
    echo "   !! [tierc] 배너 없음 — 계측이 안 걸렸다"; return 1
  fi
  G=$(grep -am1 -o "max_total_num_tokens=[0-9]*" "$OUT/serve_$2.log"|cut -d= -f2)
  echo "   [assert] GPU pool=$G (기대 $PIN) · fit=$(python3 -c "print(f'{$G/$FIT_DEN:.2f}')")"
  [ "$G" = "$PIN" ] || { echo "   !! pool 불일치"; return 1; }
}

cell(){ # $1=tag $2=system $3=router $4=extra
  [ -s "$OUT/window_$1.json" ] && { echo "[cell $1] SKIP (이미 완료)"; return 0; }
  echo "[cell $1] START $(TZ=Asia/Seoul date +%H:%M:%S) KST  C=$C dur=${DUR}s"
  kill_proxy
  PDIR="$OUT/profile_$1"; rm -rf "$PDIR"; mkdir -p "$PDIR"
  nohup thunderagent --backend-type sglang --backends "http://localhost:$BP" --port $PP \
    --router "$3" --metrics --profile --profile-dir "$PDIR" $4 > "$OUT/proxy_$1.log" 2>&1 &
  for i in $(seq 1 60); do curl -sf "http://127.0.0.1:$PP/health" >/dev/null 2>&1 && break; sleep 1; done
  M=$(curl -s "http://127.0.0.1:$PP/health"|python -c 'import sys,json;print(json.load(sys.stdin)["router_mode"])' 2>/dev/null)
  [ "$M" = "$3" ] || { echo "[cell $1] FATAL router=$M"; return 1; }
  nohup python "$REPO/scripts/phase2_engine_sampler_yunuikang.py" --backend "http://localhost:$BP" \
    --out "$OUT/engine_$1.csv" --interval 5 >/dev/null 2>&1 & EPID=$!
  # ★ 계측 창의 경계를 기록한다 — analyze 가 이 창으로 자른다
  T0=$(python3 -c 'import time;print(f"{time.time():.3f}")')
  timeout $((DUR+GRACE+600)) python "$REPO/scripts/mori_replay_driver_yunuikang.py" --trace "$TRACE" \
    --base-url "http://localhost:$PP" --router-url "http://localhost:$PP" --backends "http://localhost:$BP" \
    --model Qwen/Qwen3-8B --tokenizer Qwen/Qwen3-8B --router "$3" --system "$2" \
    --concurrency "$C" --duration-s $DUR --deadline-grace-s $GRACE --warmup-frac $WARM --metric-interval 30 \
    --ctx-cap 69632 --http-timeout 2400 \
    --hicache-metrics "$HM" --run-tag "$1" --out "$RES" 2>"$OUT/err_$1.log" || echo "   driver rc=$?"
  T1=$(python3 -c 'import time;print(f"{time.time():.3f}")')
  kill "$EPID" 2>/dev/null || true
  python3 -c "
import json,sys
json.dump({'tag':'$1','system':'$2','t_start':float('$T0'),'t_end':float('$T1'),
           'C':$C,'dur_s':$DUR,'warm':$WARM,'ratio':$RATIO,'maxtok':$PIN},
          open('$OUT/window_$1.json','w'))"
  echo "[cell $1] DONE $(TZ=Asia/Seoul date +%H:%M:%S) KST  창=$(python3 -c "print(f'{float('$T1')-float('$T0'):.0f}s')")"
}

echo "######## Tier C 스모크 (5090) 시작 $(TZ=Asia/Seoul date '+%m/%d %H:%M') KST ########"
echo "  C=$C · dur=${DUR}s · MAXTOK=$PIN (fit 8.10) · r=$RATIO · MORI/TA+O 각 1셀"
echo "  out=$OUT"

if [ ! -s "$OUT/window_MORI.json" ]; then
  boot mori MORI || exit 1
  cell MORI MORI mori "--mori-cpu-capacity-ratio $RATIO" || exit 1
else
  echo "[cell MORI] SKIP (이미 완료) — 백엔드 기동 생략"
fi
if [ ! -s "$OUT/window_TAO.json" ]; then
  boot lru TAO || exit 1
  cell TAO TAO tr "" || exit 1
else
  echo "[cell TAO] SKIP (이미 완료)"
fi
# 비오프로딩 대조군 (게이트 항목 3: 비오프로딩계는 transfer_tok = 0 이어야 한다)
if [ "${WITH_TA:-1}" = "1" ] && [ ! -s "$OUT/window_TA.json" ]; then
  DUR_SAVE=$DUR; DUR=${TA_DUR:-150}
  boot lru TA 0 || exit 1
  cell TA TA tr "" || exit 1
  DUR=$DUR_SAVE
fi
kill_proxy; kill_backend

echo
echo "######## 스모크 셀 완료 — 이제 게이트 검사 ########"
python3 "$REPO/scripts/analyze_tierc_yunuikang.py" --dir "$OUT" --gate
