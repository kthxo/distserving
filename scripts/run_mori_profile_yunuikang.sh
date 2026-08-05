#!/usr/bin/env bash
# STEP 7 Part B (⑤) — GPU 시간 분해용 최소 --profile run. **스윕 아님: 3셀만.**
#   MORI_r2_C10 (건강, oversub 1.2x) / MORI_r2_C80 (극단, 9.9x) / TAO_r2_C80 (극단 대조)
# 기존 하네스 재사용(무수정): _serve_sglang_8b_tp2_mori_yunuikang.sh, mori_replay_driver_yunuikang.py.
# 신규는 이 런처뿐. --profile을 켜면 ThunderAgent가 프록시별 profile_dir에
# step_profiles.csv (prefill_s/decode_s/pause_s/tool_call_s/토큰/kv_hit_rate/completed_at)를 남긴다.
#
# M-SWP는 셀당 3600s였지만 여기서는 시간 분해 비율만 필요하므로 DUR=420s로 짧게 간다.
set -uo pipefail
REPO=/home/yunuikang/yunuikang_work/distserving
VENV=/home/yunuikang/yunuikang_work/.venv
TRACE=/home/yunuikang/yunuikang_work/scratch/traces/tracelab_moriM_L64k_yunuikang.jsonl
BP=8123; PP=9000; PIN="${PIN:-262144}"
DUR="${DUR:-420}"; GRACE="${GRACE:-60}"; WARM="${WARM:-0.25}"
OUT="${OUT:-/home/yunuikang/yunuikang_work/scratch/mori/prof}"; RES=$OUT/results_prof.jsonl
HM="sglang:hicache_host_used_tokens,sglang:hicache_host_total_tokens,sglang:evicted_tokens_total,sglang:load_back_tokens_total,sglang:cached_tokens_total,sglang:prompt_tokens_total,sglang:generation_tokens_total"
mkdir -p "$OUT"
[ -z "${RESUME:-}" ] && : > "$RES"
source "$VENV/bin/activate"

BPID=""
kill_backend(){ [ -n "$BPID" ] && kill "$BPID" 2>/dev/null
  pkill -9 -f "_serve_sglang_8b_tp2_mori_yunuikang" 2>/dev/null
  pkill -9 -f "sglang.launch_server" 2>/dev/null; pkill -9 -f "sglang::" 2>/dev/null; sleep 6; BPID=""; }
kill_proxy(){ for pid in $(pgrep -f "bin/thunderagent" 2>/dev/null); do
  cl=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null); case " $cl " in *" --port $PP "*) kill "$pid";; esac; done; sleep 2; }
trap 'kill_proxy; kill_backend' EXIT

boot_backend(){ # $1=EVICT $2=RATIO
  kill_backend
  MAXTOK=$PIN RATIO="$2" EVICT="$1" PORT=$BP MEMFRAC=0.85 \
    LOG="$OUT/serve_${1}_r${2}.log" nohup bash "$REPO/scripts/_serve_sglang_8b_tp2_mori_yunuikang.sh" >/dev/null 2>&1 &
  BPID=$!
  for i in $(seq 1 300); do
    curl -sf "http://127.0.0.1:$BP/health" >/dev/null 2>&1 && { echo "[backend $1 r$2] READY ~$((i*3))s $(date +%T)"; return 0; }
    kill -0 "$BPID" 2>/dev/null || { echo "[backend $1 r$2] DIED"; tail -20 "$OUT/serve_${1}_r${2}.log"; return 1; }
    sleep 3
  done; echo "[backend $1 r$2] TIMEOUT"; return 1; }

run_cell(){ # $1=tag $2=system $3=router $4=extra $5=C
  echo "[cell $1] START $(date +%T)  (dur=${DUR}s)"
  kill_proxy
  PDIR="$OUT/profile_$1"; rm -rf "$PDIR"; mkdir -p "$PDIR"
  nohup thunderagent --backend-type sglang --backends "http://localhost:$BP" --port $PP \
    --router "$3" --metrics --profile --profile-dir "$PDIR" $4 > "$OUT/proxy_$1.log" 2>&1 &
  for i in $(seq 1 60); do curl -sf "http://127.0.0.1:$PP/health" >/dev/null 2>&1 && break; sleep 1; done
  MODE=$(curl -s "http://127.0.0.1:$PP/health" | python -c 'import sys,json;print(json.load(sys.stdin)["router_mode"])' 2>/dev/null)
  PROF=$(curl -s "http://127.0.0.1:$PP/health" | python -c 'import sys,json;print(json.load(sys.stdin)["profile_enabled"])' 2>/dev/null)
  if [ "$MODE" != "$3" ] || [ "$PROF" != "True" ]; then
    echo "[cell $1] FATAL mode=$MODE (want $3), profile_enabled=$PROF (want True)"; return; fi
  echo "[cell $1] proxy ready mode=$MODE profile=$PROF -> $PDIR"

  nohup python "$REPO/scripts/sample_gpu_resident_yunuikang.py" --gpus 0,1 --out "$OUT/gpu_$1.jsonl" \
    --health-url "http://localhost:$PP/health" --backends "http://localhost:$BP" >/dev/null 2>&1 & SPID=$!
  timeout $((DUR+GRACE+300)) python "$REPO/scripts/mori_replay_driver_yunuikang.py" --trace "$TRACE" \
    --base-url "http://localhost:$PP" --router-url "http://localhost:$PP" --backends "http://localhost:$BP" \
    --model Qwen/Qwen3-8B --tokenizer Qwen/Qwen3-8B --router "$3" --system "$2" \
    --concurrency "$5" --duration-s $DUR --deadline-grace-s $GRACE --warmup-frac $WARM --metric-interval 30 \
    --ctx-cap 69632 --http-timeout 2400 \
    --hicache-metrics "$HM" --run-tag "$1" --out "$RES" 2>"$OUT/err_$1.log" || echo "[cell $1] driver rc=$?"
  kill "$SPID" 2>/dev/null || true
  N=$(wc -l < "$PDIR/step_profiles.csv" 2>/dev/null || echo 0)
  echo "[cell $1] DONE $(date +%T)  step_profiles rows=$N"
}

echo "==[PROF] start $(date) dur=${DUR}s  (3 cells only, no sweep) =="
boot_backend mori 2 || exit 1
run_cell "MORI_r2_C10" MORI mori "--mori-cpu-capacity-ratio 2" 10
run_cell "MORI_r2_C80" MORI mori "--mori-cpu-capacity-ratio 2" 80
boot_backend lru 2 || exit 1
run_cell "TAO_r2_C80" TAO tr "" 80
kill_proxy; kill_backend
echo "==[PROF-DONE] $(date) results=$RES =="
