#!/usr/bin/env bash
# Phase 2 C=50 pivot — "붕괴 원인 = CPU 용량(dial②) vs GPU-oversub 스래싱" 판별
#
# 배경 [측정]:
#   앵커 r2C20 = 1.29x(승) · r2C32 = 1.11x(승, 3지표 정합) · Waiting 축출 3건뿐.
#   → C_crit=(1+r)x8.10 공식이 압박을 과대평가. 실측 임계는 C 32~50 사이.
#   → C32/40/48 격자는 전부 "승"만 나와 반증 불가 → 폐기. MORI가 지는 C=50에서 r을 올린다.
#
# 판별 논리:
#   r↑ 로 MORI가 구조되고 스래싱(ping-pong/pause)도 함께 내려가면  → CPU 용량 lever (DRAM)
#   r↑ 로 Waiting은 0인데 비율 정체 + 스래싱 여전                  → GPU-fit lever (HBM=H200)
#
# ※ 엔진 재기동은 (EVICT, RATIO) 축에서 필요하다. MORI=mori / TA+O=lru 이므로
#   r 하나당 2회, 총 6회 재기동이다 (r 축만 3회가 아님).
# ※ M-SWP 옛 수치 재사용 금지 — 비율은 같은 세션의 MORI÷TA+O 로만 판정.
#
# STAGE=r2|r3|r4|all
set -uo pipefail
REPO=/home/yunuikang/yunuikang_work/distserving
VENV=/home/yunuikang/yunuikang_work/.venv
TRACE=/home/yunuikang/yunuikang_work/scratch/traces/tracelab_moriM_L64k_yunuikang.jsonl
BP=8123; PP=9000; PIN=262144; FIT_DEN=32376; C=50
DUR="${DUR:-3600}"; GRACE="${GRACE:-60}"; WARM="${WARM:-0.2}"
OUT="${OUT:-/home/yunuikang/yunuikang_work/scratch/mori/phase2_c50}"; RES=$OUT/results_c50.jsonl
STAGE="${STAGE:-r2}"; DRAM_MIN_GIB="${DRAM_MIN_GIB:-8}"
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
wait_gpu_idle(){ for i in $(seq 1 40); do
  n=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -c . || echo 0)
  [ "$n" = "0" ] && { echo "   [gpu] 유휴 확인"; return 0; }; sleep 2; done
  echo "   [gpu] !! 잔존 — 강제 종료"; kill_backend; }

boot(){ # $1=EVICT $2=RATIO
  kill_proxy; kill_backend; wait_gpu_idle
  FREE=$(free -g|awk '/^Mem:/{print $7}')
  echo "==[backend $1 r$2] boot $(TZ=Asia/Seoul date +%H:%M) KST  (DRAM ${FREE}GiB)"
  MAXTOK=$PIN RATIO="$2" EVICT="$1" PORT=$BP MEMFRAC=0.85 \
    LOG="$OUT/serve_${1}_r${2}.log" nohup bash "$REPO/scripts/_serve_sglang_8b_tp2_mori_yunuikang.sh" >/dev/null 2>&1 &
  BPID=$!
  for i in $(seq 1 320); do
    curl -sf "http://127.0.0.1:$BP/health" >/dev/null 2>&1 && { echo "   READY ~$((i*3))s"; break; }
    kill -0 "$BPID" 2>/dev/null || { echo "   !! DIED"; grep -aiE "Not enough host memory|ValueError|Killed" "$OUT/serve_${1}_r${2}.log"|head -3; return 1; }
    sleep 3; done
  curl -sf "http://127.0.0.1:$BP/health" >/dev/null 2>&1 || { echo "   !! TIMEOUT"; return 1; }
  G=$(grep -am1 -o "max_total_num_tokens=[0-9]*" "$OUT/serve_${1}_r${2}.log"|cut -d= -f2)
  H=$(curl -s "http://127.0.0.1:$BP/metrics"|grep -m1 "^sglang:hicache_host_total_tokens"|awk '{print $2}')
  python3 - "$G" "$H" "$2" "$PIN" "$FIT_DEN" "$C" <<'PY' || { echo "   !! FATAL assert"; return 1; }
import sys
g,h,r,pin,den,C=int(sys.argv[1]),float(sys.argv[2]),float(sys.argv[3]),int(sys.argv[4]),int(sys.argv[5]),int(sys.argv[6])
fit=g/den
print(f"   [assert] GPU={g:,} (기대 {pin:,})  host={h:,.0f} (기대 {r*pin:,.0f})")
print(f"   [assert] fit={fit:.2f}  C={C} oversub={C/fit:.2f}x  (참고 C_crit=(1+{r:g})x{fit:.2f}={(1+r)*fit:.1f})")
sys.exit(1 if (g!=pin or abs(h-r*pin)>pin*0.02) else 0)
PY
}

cell(){ # $1=tag $2=system $3=router $4=extra
  grep -qa "\"run_tag\": \"$1\"" "$RES" 2>/dev/null && { echo "[cell $1] SKIP"; return 0; }
  FREE=$(free -g|awk '/^Mem:/{print $7}')
  [ "$FREE" -lt "$DRAM_MIN_GIB" ] && { echo "[cell $1] !! DRAM ${FREE}GiB 부족 — 스킵"; return 0; }
  echo "[cell $1] START $(TZ=Asia/Seoul date +%H:%M) KST  C=$C DRAM=${FREE}GiB"
  kill_proxy
  PDIR="$OUT/profile_$1"; rm -rf "$PDIR"; mkdir -p "$PDIR"
  nohup thunderagent --backend-type sglang --backends "http://localhost:$BP" --port $PP \
    --router "$3" --metrics --profile --profile-dir "$PDIR" $4 > "$OUT/proxy_$1.log" 2>&1 &
  for i in $(seq 1 60); do curl -sf "http://127.0.0.1:$PP/health" >/dev/null 2>&1 && break; sleep 1; done
  M=$(curl -s "http://127.0.0.1:$PP/health"|python -c 'import sys,json;print(json.load(sys.stdin)["router_mode"])' 2>/dev/null)
  P=$(curl -s "http://127.0.0.1:$PP/health"|python -c 'import sys,json;print(json.load(sys.stdin)["profile_enabled"])' 2>/dev/null)
  [ "$M" = "$3" ] && [ "$P" = "True" ] || { echo "[cell $1] FATAL mode=$M profile=$P"; return 1; }
  [ "$3" = "mori" ] && { sleep 6; grep -a "MORI CPU tier" "$OUT/proxy_$1.log"|tail -1|sed 's/^/   [I6] /'; }
  nohup python "$REPO/scripts/phase2_engine_sampler_yunuikang.py" --backend "http://localhost:$BP" \
    --out "$OUT/engine_$1.csv" --interval 5 >/dev/null 2>&1 & EPID=$!
  nohup python "$REPO/scripts/sample_gpu_resident_yunuikang.py" --gpus 0,1 --out "$OUT/gpu_$1.jsonl" \
    --health-url "http://localhost:$PP/health" --backends "http://localhost:$BP" >/dev/null 2>&1 & SPID=$!
  timeout $((DUR+GRACE+900)) python "$REPO/scripts/mori_replay_driver_yunuikang.py" --trace "$TRACE" \
    --base-url "http://localhost:$PP" --router-url "http://localhost:$PP" --backends "http://localhost:$BP" \
    --model Qwen/Qwen3-8B --tokenizer Qwen/Qwen3-8B --router "$3" --system "$2" \
    --concurrency "$C" --duration-s $DUR --deadline-grace-s $GRACE --warmup-frac $WARM --metric-interval 30 \
    --ctx-cap 69632 --http-timeout 2400 \
    --hicache-metrics "$HM" --run-tag "$1" --out "$RES" 2>"$OUT/err_$1.log" || echo "   driver rc=$?"
  kill "$SPID" "$EPID" 2>/dev/null || true; sleep 1
  if [ "$3" = "mori" ]; then EV=$(grep -ac "MORI evict CPU->Waiting" "$OUT/proxy_$1.log" 2>/dev/null||echo 0)
  else EV=$(grep -ac "Paused program" "$OUT/proxy_$1.log" 2>/dev/null||echo 0); fi
  SUM=$(grep -a "\"run_tag\": \"$1\"" "$RES"|tail -1|python3 -c "
import sys,json; d=json.loads(sys.stdin.read() or '{}')
print(f\"drv={d.get('output_throughput_tok_s') or 0:.2f} ttft50={d.get('ttft_p50_s') or 0:.2f} turns={d.get('steady_turns',0)} fail={d.get('failed_programs',0)}\")" 2>/dev/null)
  echo "[cell $1] DONE $(TZ=Asia/Seoul date +%H:%M) KST  $SUM  waiting_ev=$EV"
}

stage(){ # $1=r
  local r=$1
  boot mori "$r" || exit 1
  cell "MORI_r${r}_C50" MORI mori "--mori-cpu-capacity-ratio $r" || exit 1
  boot lru "$r"  || exit 1
  cell "TAO_r${r}_C50"  TAO  tr "" || exit 1
}

echo "######## PHASE 2 C=50 pivot  STAGE=$STAGE  시작 $(TZ=Asia/Seoul date '+%m/%d %H:%M') KST ########"
echo "  C=$C · 셀 ${DUR}s · 반복 없음 · 재기동은 (EVICT,RATIO) 축 = r당 2회"
case "$STAGE" in
  r2) stage 2 ;;
  r3) stage 3 ;;
  r4) stage 4 ;;
  all) stage 2; stage 3; stage 4 ;;
  *) echo "STAGE=r2|r3|r4|all"; exit 2 ;;
esac
kill_proxy; kill_backend
echo "######## STAGE=$STAGE DONE $(TZ=Asia/Seoul date '+%m/%d %H:%M') KST  results=$RES ########"
