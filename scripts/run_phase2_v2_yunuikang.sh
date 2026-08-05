#!/usr/bin/env bash
# Phase 2 v2 — 1시간 셀 · 반복 없음 · 앵커 게이트 · 불편향 교차지표 병기
#
# 변경 이유 [측정]: 20분 셀에서 드라이버 throughput이 MORI를 체계적으로 불리하게 만든다.
#   드라이버는 **완료된 프로그램만** 집계(mori_replay_driver:300-317)하는데 MORI는 설계상
#   프로그램 완주 시간을 늘리므로 미완 토큰이 통째로 빠진다.
#   같은 셀: 드라이버 0.57x vs 엔진(완료무관) 0.86x  → 프로토콜 편향 확인.
#
# 그래서:
#   (a) 셀 1시간(M-SWP와 동일) · 반복 제거
#   (b) 앵커 MORI_r2_C20 **1셀 먼저** 돌려 M-SWP의 1.12x가 복원되는지 게이트
#       (TA+O 기준선은 M-SWP TAO_r2_C20=19.9 재사용 — tr 라우터는 A7c 수정의 영향을 받지 않음)
#   (c) 불편향 교차지표 3종 병기:
#       · 엔진 steady-window 토큰 (phase2_engine_sampler, /metrics 5s 폴링)
#       · Waiting 축출 (프록시 로그)
#       · goodput (--profile per-step CSV: pause_s+prefill_s ≤ SLO 인 스텝의 completion_tokens)
#
# MODE=anchor : 앵커 1셀만
# MODE=matrix : 나머지 10셀 (앵커 통과 후)
set -uo pipefail
REPO=/home/yunuikang/yunuikang_work/distserving
VENV=/home/yunuikang/yunuikang_work/.venv
TRACE=/home/yunuikang/yunuikang_work/scratch/traces/tracelab_moriM_L64k_yunuikang.jsonl
BP=8123; PP=9000; PIN=262144; FIT_DEN=32376
DUR="${DUR:-3600}"; GRACE="${GRACE:-60}"; WARM="${WARM:-0.2}"     # M-SWP와 동일
OUT="${OUT:-/home/yunuikang/yunuikang_work/scratch/mori/phase2}"; RES=$OUT/results_phase2.jsonl
MODE="${MODE:-anchor}"; DRAM_MIN_GIB="${DRAM_MIN_GIB:-8}"
HM="sglang:hicache_host_used_tokens,sglang:hicache_host_total_tokens,sglang:evicted_tokens_total,sglang:load_back_tokens_total,sglang:cached_tokens_total,sglang:prompt_tokens_total,sglang:generation_tokens_total"
mkdir -p "$OUT"; touch "$RES"
source "$VENV/bin/activate"

BPID=""
kill_backend(){ [ -n "$BPID" ] && kill "$BPID" 2>/dev/null
  pkill -9 -f "_serve_sglang_8b_tp2_mori_yunuikang" 2>/dev/null
  pkill -9 -f "sglang.launch_server" 2>/dev/null; pkill -9 -f "sglang::" 2>/dev/null
  sleep 8; BPID=""; }
kill_proxy(){ for pid in $(pgrep -f "bin/thunderagent" 2>/dev/null); do
  cl=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null); case " $cl " in *" --port $PP "*) kill "$pid";; esac; done; sleep 2; }
trap 'kill_proxy; kill_backend' EXIT
wait_gpu_idle(){ for i in $(seq 1 30); do
  n=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -c . || echo 0)
  [ "$n" = "0" ] && return 0; sleep 2; done; kill_backend; }

boot_backend(){ # $1=EVICT $2=RATIO
  kill_proxy; kill_backend; wait_gpu_idle
  echo "==[backend $1 r$2] boot $(TZ=Asia/Seoul date +%H:%M) KST  (DRAM $(free -g|awk '/^Mem:/{print $7}')GiB)"
  MAXTOK=$PIN RATIO="$2" EVICT="$1" PORT=$BP MEMFRAC=0.85 \
    LOG="$OUT/serve_${1}_r${2}.log" nohup bash "$REPO/scripts/_serve_sglang_8b_tp2_mori_yunuikang.sh" >/dev/null 2>&1 &
  BPID=$!
  for i in $(seq 1 300); do
    curl -sf "http://127.0.0.1:$BP/health" >/dev/null 2>&1 && { echo "   READY ~$((i*3))s"; break; }
    kill -0 "$BPID" 2>/dev/null || { echo "   !! DIED"; grep -aiE "Not enough host memory|ValueError|Killed" "$OUT/serve_${1}_r${2}.log"|head -3; return 1; }
    sleep 3; done
  curl -sf "http://127.0.0.1:$BP/health" >/dev/null 2>&1 || { echo "   !! TIMEOUT"; return 1; }
  G=$(grep -am1 -o "max_total_num_tokens=[0-9]*" "$OUT/serve_${1}_r${2}.log"|cut -d= -f2)
  H=$(curl -s "http://127.0.0.1:$BP/metrics"|grep -m1 "^sglang:hicache_host_total_tokens"|awk '{print $2}')
  python3 - "$G" "$H" "$2" "$PIN" "$FIT_DEN" <<'PY' || return 1
import sys
g,h,r,pin,den=int(sys.argv[1]),float(sys.argv[2]),float(sys.argv[3]),int(sys.argv[4]),int(sys.argv[5])
print(f"   [assert] GPU={g:,} host={h:,.0f} (기대 {r*pin:,.0f})  fit={g/den:.2f}  C_crit={(1+r)*g/den:.1f}")
sys.exit(1 if (g!=pin or abs(h-r*pin)>pin*0.02) else 0)
PY
}

run_cell(){ # $1=tag $2=system $3=router $4=extra $5=C
  grep -qa "\"run_tag\": \"$1\"" "$RES" 2>/dev/null && { echo "[cell $1] SKIP"; return 0; }
  FREE=$(free -g|awk '/^Mem:/{print $7}')
  [ "$FREE" -lt "$DRAM_MIN_GIB" ] && { echo "[cell $1] !! DRAM ${FREE}GiB 부족 — 스킵"; return 0; }
  echo "[cell $1] START $(TZ=Asia/Seoul date +%H:%M) KST  C=$5 DRAM=${FREE}GiB"
  kill_proxy
  PDIR="$OUT/profile_$1"; rm -rf "$PDIR"; mkdir -p "$PDIR"
  nohup thunderagent --backend-type sglang --backends "http://localhost:$BP" --port $PP \
    --router "$3" --metrics --profile --profile-dir "$PDIR" $4 > "$OUT/proxy_$1.log" 2>&1 &
  for i in $(seq 1 60); do curl -sf "http://127.0.0.1:$PP/health" >/dev/null 2>&1 && break; sleep 1; done
  MODE_=$(curl -s "http://127.0.0.1:$PP/health"|python -c 'import sys,json;print(json.load(sys.stdin)["router_mode"])' 2>/dev/null)
  PROF=$(curl -s "http://127.0.0.1:$PP/health"|python -c 'import sys,json;print(json.load(sys.stdin)["profile_enabled"])' 2>/dev/null)
  [ "$MODE_" = "$3" ] && [ "$PROF" = "True" ] || { echo "[cell $1] FATAL mode=$MODE_ profile=$PROF"; return 1; }
  [ "$3" = "mori" ] && { sleep 6; grep -a "MORI CPU tier" "$OUT/proxy_$1.log"|tail -1|sed 's/^/   [I6] /'; }

  # 불편향 교차지표 (b): 엔진 /metrics 5초 폴링
  nohup python "$REPO/scripts/phase2_engine_sampler_yunuikang.py" --backend "http://localhost:$BP" \
    --out "$OUT/engine_$1.csv" --interval 5 >/dev/null 2>&1 & EPID=$!
  nohup python "$REPO/scripts/sample_gpu_resident_yunuikang.py" --gpus 0,1 --out "$OUT/gpu_$1.jsonl" \
    --health-url "http://localhost:$PP/health" --backends "http://localhost:$BP" >/dev/null 2>&1 & SPID=$!

  timeout $((DUR+GRACE+900)) python "$REPO/scripts/mori_replay_driver_yunuikang.py" --trace "$TRACE" \
    --base-url "http://localhost:$PP" --router-url "http://localhost:$PP" --backends "http://localhost:$BP" \
    --model Qwen/Qwen3-8B --tokenizer Qwen/Qwen3-8B --router "$3" --system "$2" \
    --concurrency "$5" --duration-s $DUR --deadline-grace-s $GRACE --warmup-frac $WARM --metric-interval 30 \
    --ctx-cap 69632 --http-timeout 2400 \
    --hicache-metrics "$HM" --run-tag "$1" --out "$RES" 2>"$OUT/err_$1.log" || echo "   driver rc=$?"
  kill "$SPID" "$EPID" 2>/dev/null || true; sleep 1
  EV=$(grep -ac "MORI evict CPU->Waiting" "$OUT/proxy_$1.log" 2>/dev/null || echo 0)
  NP=$(wc -l < "$PDIR/step_profiles.csv" 2>/dev/null || echo 0)
  SUM=$(grep -a "\"run_tag\": \"$1\"" "$RES"|tail -1|python3 -c "
import sys,json; d=json.loads(sys.stdin.read() or '{}')
print(f\"drv_thr={d.get('output_throughput_tok_s') or 0:.2f} ttft_p50={d.get('ttft_p50_s') or 0:.2f} turns={d.get('steady_turns',0)} fail={d.get('failed_programs',0)}\")" 2>/dev/null)
  echo "[cell $1] DONE $(TZ=Asia/Seoul date +%H:%M) KST  $SUM  evict=$EV  profile_rows=$NP"
}

echo "######## PHASE 2 v2  MODE=$MODE  DUR=${DUR}s  시작 $(TZ=Asia/Seoul date '+%m/%d %H:%M') KST ########"
echo "  fit=$(python3 -c "print(f'{$PIN/$FIT_DEN:.2f}')")  C_crit: r2=$(python3 -c "print(f'{3*$PIN/$FIT_DEN:.1f}')") r3=$(python3 -c "print(f'{4*$PIN/$FIT_DEN:.1f}')") r4=$(python3 -c "print(f'{5*$PIN/$FIT_DEN:.1f}')")"

if [ "$MODE" = "anchor" ]; then
  echo "  [앵커 게이트] MORI_r2_C20 1셀 — M-SWP 기준선(MORI 22.2 / TAO 19.9 = 1.12x) 복원 확인"
  boot_backend mori 2 || exit 1
  run_cell "MORI_r2_C20" MORI mori "--mori-cpu-capacity-ratio 2" 20
  kill_proxy; kill_backend
  echo "######## 앵커 완료 $(TZ=Asia/Seoul date '+%m/%d %H:%M') KST — 판정 후 MODE=matrix 실행 ########"
  exit 0
fi

# ---- 본 매트릭스 (반복 없음, 앵커 통과 후) ----
boot_backend lru 2  || exit 1; run_cell "TAO_r2_C32"  TAO  tr "" 32
boot_backend mori 2 || exit 1; run_cell "MORI_r2_C32" MORI mori "--mori-cpu-capacity-ratio 2" 32
boot_backend lru 3  || exit 1; run_cell "TAO_r3_C32"  TAO  tr "" 32
boot_backend mori 3 || exit 1; run_cell "MORI_r3_C32" MORI mori "--mori-cpu-capacity-ratio 3" 32
boot_backend lru 4  || exit 1
run_cell "TAO_r4_C32" TAO tr "" 32; run_cell "TAO_r4_C40" TAO tr "" 40; run_cell "TAO_r4_C48" TAO tr "" 48
boot_backend mori 4 || exit 1
run_cell "MORI_r4_C32" MORI mori "--mori-cpu-capacity-ratio 4" 32
run_cell "MORI_r4_C40" MORI mori "--mori-cpu-capacity-ratio 4" 40
run_cell "MORI_r4_C48" MORI mori "--mori-cpu-capacity-ratio 4" 48
kill_proxy; kill_backend
echo "######## PHASE 2 v2 DONE $(TZ=Asia/Seoul date '+%m/%d %H:%M') KST  results=$RES ########"
