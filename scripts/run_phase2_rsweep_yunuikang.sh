#!/usr/bin/env bash
# Phase 2 — r 스윕으로 dial ② 격리 검증 (goguma6 5090, Qwen3-8B).
#
# 가설: MORI 붕괴는 GPU+CPU 용량 부족(oversub > 1+r) 때문이다.
#       C_crit = (1+r) x fit,  fit = 262,144 / 32,376 = 8.10
#       r=2 -> 24.3 | r=3 -> 32.4 | r=4 -> 40.5
# ★ 반증테스트: 같은 C=32에서 r=2(패) -> r=4(승) 로 뒤집히는가.
#
# 기존 스크립트 0-line diff: _serve_sglang_8b_tp2_mori_yunuikang.sh 와
# mori_replay_driver_yunuikang.py 는 그대로 호출만 한다.
#
# 백엔드는 (EVICT, RATIO) 축에서만 재기동 -> r당 2회(lru/mori), 총 6회.
set -uo pipefail
REPO=/home/yunuikang/yunuikang_work/distserving
VENV=/home/yunuikang/yunuikang_work/.venv
TRACE=/home/yunuikang/yunuikang_work/scratch/traces/tracelab_moriM_L64k_yunuikang.jsonl
BP=8123; PP=9000; PIN=262144
DUR="${DUR:-1200}"; GRACE="${GRACE:-60}"; WARM="${WARM:-0.2}"
OUT="${OUT:-/home/yunuikang/yunuikang_work/scratch/mori/phase2}"; RES=$OUT/results_phase2.jsonl
FIT_DEN=32376                      # Track M ctx median [측정]
DRAM_MIN_GIB="${DRAM_MIN_GIB:-8}"  # 셀 시작 전 최소 여유
HM="sglang:hicache_host_used_tokens,sglang:hicache_host_total_tokens,sglang:evicted_tokens_total,sglang:load_back_tokens_total,sglang:cached_tokens_total,sglang:prompt_tokens_total,sglang:generation_tokens_total"
mkdir -p "$OUT"
[ -z "${RESUME:-}" ] && : > "$RES"
source "$VENV/bin/activate"

BPID=""
kill_backend(){ [ -n "$BPID" ] && kill "$BPID" 2>/dev/null
  pkill -9 -f "_serve_sglang_8b_tp2_mori_yunuikang" 2>/dev/null
  pkill -9 -f "sglang.launch_server" 2>/dev/null; pkill -9 -f "sglang::" 2>/dev/null
  sleep 8; BPID=""; }
kill_proxy(){ for pid in $(pgrep -f "bin/thunderagent" 2>/dev/null); do
  cl=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null); case " $cl " in *" --port $PP "*) kill "$pid";; esac; done; sleep 2; }
trap 'kill_proxy; kill_backend' EXIT

# GPU가 실제로 비었는지 확인 (기존 gotcha: 급종료 후 util 카운터 잔상)
wait_gpu_idle(){
  for i in $(seq 1 30); do
    n=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -c . || echo 0)
    [ "$n" = "0" ] && { echo "   [gpu] compute procs=0 (유휴)"; return 0; }
    sleep 2
  done
  echo "   [gpu] !! compute procs 잔존 — 강제 종료 시도"; kill_backend; return 0
}

boot_backend(){ # $1=EVICT $2=RATIO
  kill_proxy; kill_backend; wait_gpu_idle
  echo "==[backend $1 r$2] boot $(date +%T)  (DRAM: $(free -g | awk '/^Mem:/{print $7}') GiB free)"
  MAXTOK=$PIN RATIO="$2" EVICT="$1" PORT=$BP MEMFRAC=0.85 \
    LOG="$OUT/serve_${1}_r${2}.log" nohup bash "$REPO/scripts/_serve_sglang_8b_tp2_mori_yunuikang.sh" >/dev/null 2>&1 &
  BPID=$!
  for i in $(seq 1 300); do
    curl -sf "http://127.0.0.1:$BP/health" >/dev/null 2>&1 && { echo "   READY ~$((i*3))s"; break; }
    kill -0 "$BPID" 2>/dev/null || { echo "   !! DIED"; grep -aiE "Not enough host memory|ValueError|Killed" "$OUT/serve_${1}_r${2}.log" | head -3; return 1; }
    sleep 3
  done
  curl -sf "http://127.0.0.1:$BP/health" >/dev/null 2>&1 || { echo "   !! TIMEOUT"; return 1; }
  # --- fit assert (엔진 실측 pool) ---
  GPUTOK=$(grep -am1 -o "max_total_num_tokens=[0-9]*" "$OUT/serve_${1}_r${2}.log" | cut -d= -f2)
  HOSTTOK=$(curl -s "http://127.0.0.1:$BP/metrics" | grep -m1 "^sglang:hicache_host_total_tokens" | awk '{print $2}')
  python3 - "$GPUTOK" "$HOSTTOK" "$2" "$PIN" "$FIT_DEN" <<'PY' || return 1
import sys
g,h,r,pin,den = int(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
fit=g/den; crit=(1+r)*fit
print(f"   [assert] GPU pool={g:,} (기대 {pin:,})  host={h:,.0f} (기대 {r*pin:,.0f})")
print(f"   [assert] fit={fit:.2f}  C_crit=(1+{r:g})x{fit:.2f}={crit:.1f}")
bad = (g!=pin) or (abs(h-r*pin) > pin*0.02)
if bad: print("   [assert] !! FATAL 풀 크기 불일치"); sys.exit(1)
PY
  return 0
}

run_cell(){ # $1=tag $2=system $3=router $4=extra $5=C
  if grep -qa "\"run_tag\": \"$1\"" "$RES" 2>/dev/null; then echo "[cell $1] SKIP (이미 있음)"; return; fi
  FREE=$(free -g | awk '/^Mem:/{print $7}')
  if [ "$FREE" -lt "$DRAM_MIN_GIB" ]; then
    echo "[cell $1] !! DRAM 여유 ${FREE}GiB < ${DRAM_MIN_GIB}GiB — 건너뜀(OOM 위험)"; return; fi
  echo "[cell $1] START $(date +%T)  C=$5  DRAM free=${FREE}GiB"
  kill_proxy
  nohup thunderagent --backend-type sglang --backends "http://localhost:$BP" --port $PP \
    --router "$3" --metrics $4 > "$OUT/proxy_$1.log" 2>&1 &
  for i in $(seq 1 60); do curl -sf "http://127.0.0.1:$PP/health" >/dev/null 2>&1 && break; sleep 1; done
  MODE=$(curl -s "http://127.0.0.1:$PP/health" | python -c 'import sys,json;print(json.load(sys.stdin)["router_mode"])' 2>/dev/null)
  [ "$MODE" = "$3" ] || { echo "[cell $1] FATAL router_mode=$MODE != $3"; return; }
  # I6: 스케줄러 CpuTier 장부 == 엔진 host pool (mori 셀만 해당)
  if [ "$3" = "mori" ]; then
    sleep 6
    grep -a "MORI CPU tier" "$OUT/proxy_$1.log" | tail -1 | sed 's/^/   [I6] /'
  fi
  nohup python "$REPO/scripts/sample_gpu_resident_yunuikang.py" --gpus 0,1 --out "$OUT/gpu_$1.jsonl" \
    --health-url "http://localhost:$PP/health" --backends "http://localhost:$BP" >/dev/null 2>&1 & SPID=$!
  timeout $((DUR+GRACE+600)) python "$REPO/scripts/mori_replay_driver_yunuikang.py" --trace "$TRACE" \
    --base-url "http://localhost:$PP" --router-url "http://localhost:$PP" --backends "http://localhost:$BP" \
    --model Qwen/Qwen3-8B --tokenizer Qwen/Qwen3-8B --router "$3" --system "$2" \
    --concurrency "$5" --duration-s $DUR --deadline-grace-s $GRACE --warmup-frac $WARM --metric-interval 30 \
    --ctx-cap 69632 --http-timeout 2400 \
    --hicache-metrics "$HM" --run-tag "$1" --out "$RES" 2>"$OUT/err_$1.log" || echo "   driver rc=$?"
  kill "$SPID" 2>/dev/null || true
  SUM=$(grep -a "\"run_tag\": \"$1\"" "$RES" | tail -1 | python3 -c "
import sys,json
d=json.loads(sys.stdin.read() or '{}')
print(f\"thr={d.get('output_throughput_tok_s') or 0:.2f} ttft_p50={d.get('ttft_p50_s') or 0:.2f} turns={d.get('steady_turns',0)} fail={d.get('failed_programs',0)}\")" 2>/dev/null)
  EV=$(grep -ac "MORI evict CPU->Waiting" "$OUT/proxy_$1.log" 2>/dev/null || echo 0)
  echo "[cell $1] DONE $(date +%T)  $SUM  evict_CPU->Waiting=$EV"
}

echo "############ PHASE 2  r-sweep  start $(date) ############"
echo "  fit = $PIN / $FIT_DEN = $(python3 -c "print(f'{$PIN/$FIT_DEN:.2f}')")"
echo "  C_crit:  r=2 -> $(python3 -c "print(f'{3*$PIN/$FIT_DEN:.1f}')")  r=3 -> $(python3 -c "print(f'{4*$PIN/$FIT_DEN:.1f}')")  r=4 -> $(python3 -c "print(f'{5*$PIN/$FIT_DEN:.1f}')")"
echo "  셀당 ${DUR}s · 총 16셀 · 예상 $(python3 -c "print(f'{16*($DUR+120)/3600:.1f}')")h"

# ---- r=2 : C20(앵커,예측 승) / C32(예측 패, pivot x2) ----
boot_backend lru 2  || exit 1
run_cell "TAO_r2_C20"      TAO  tr "" 20
run_cell "TAO_r2_C32"      TAO  tr "" 32
run_cell "TAO_r2_C32_rep2" TAO  tr "" 32
boot_backend mori 2 || exit 1
run_cell "MORI_r2_C20"      MORI mori "--mori-cpu-capacity-ratio 2" 20
run_cell "MORI_r2_C32"      MORI mori "--mori-cpu-capacity-ratio 2" 32
run_cell "MORI_r2_C32_rep2" MORI mori "--mori-cpu-capacity-ratio 2" 32

# ---- r=3 : C32(예측 경계) ----
boot_backend lru 3  || exit 1
run_cell "TAO_r3_C32"  TAO  tr "" 32
boot_backend mori 3 || exit 1
run_cell "MORI_r3_C32" MORI mori "--mori-cpu-capacity-ratio 3" 32

# ---- r=4 : C32(예측 승, pivot x2) / C40(경계) / C48(예측 패) ----
boot_backend lru 4  || exit 1
run_cell "TAO_r4_C32"      TAO tr "" 32
run_cell "TAO_r4_C32_rep2" TAO tr "" 32
run_cell "TAO_r4_C40"      TAO tr "" 40
run_cell "TAO_r4_C48"      TAO tr "" 48
boot_backend mori 4 || exit 1
run_cell "MORI_r4_C32"      MORI mori "--mori-cpu-capacity-ratio 4" 32
run_cell "MORI_r4_C32_rep2" MORI mori "--mori-cpu-capacity-ratio 4" 32
run_cell "MORI_r4_C40"      MORI mori "--mori-cpu-capacity-ratio 4" 40
run_cell "MORI_r4_C48"      MORI mori "--mori-cpu-capacity-ratio 4" 48

kill_proxy; kill_backend
echo "############ PHASE 2 DONE $(date)  results=$RES ############"
