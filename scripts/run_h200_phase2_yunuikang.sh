#!/usr/bin/env bash
# H200 Phase 2 — C 스윕 (논문 곡선 재현). 무인 실행용.
#
# 계획: plans/..._h200-rescale-reproduction_yunuikang.md rev4 §5.1 Phase 2 · 판정 §6.4 P1~P4
# 사전 등록: logs/2026-08-05_H200_PREREG_yunuikang.md §E (계측기) — P1~P4 판정식은 계획 §6.4 원문
#
#   모델 Qwen2.5-7B · fit 20.00 고정(MAXTOK 647,520) · r=2 · 셀 60분
#   4종 x C{20,40,80} = 12셀
#     SMG  router=default RATIO=0 EVICT=lru     (오프로딩 없음, 스케줄링 없음)
#     TA   router=tr      RATIO=0 EVICT=lru     (스케줄링만)
#     TA+O router=tr      RATIO=2 EVICT=lru     (스케줄링 + 오프로딩)
#     MORI router=mori    RATIO=2 EVICT=mori    (+ typed eviction, 3-tier)
#   -> SMG→TA 가 스케줄러의 값, TA→TA+O 가 오프로딩의 값, TA+O→MORI 가 MORI 정책의 값.
#      TA+O vs MORI 만 보면 이 분해가 안 된다(계획 §0.5).
#
# 셀 순서: C20 → C80 → C40 (§E.4). C20 은 P1 프로토콜 앵커라 싸게 먼저 확인하고,
#          C80 이 P2·P4 를 지므로 두 번째. C40 은 P3 보간이라 마지막.
#
# ★ 셀마다 백엔드 재기동한다 (5090 프로토콜과 다른 점, 의도적):
#   radix 캐시가 셀 사이에 넘어가면 뒤에 도는 시스템이 warm start 이득을 본다.
#   Phase 2 의 핵심 비교는 **같은 C 안에서 4종**이므로 그 편향이 곧 판정 오염이다.
#   비용은 12 x ~1.5분 = 18분.
set -uo pipefail
REPO=/workspace/distserving
VENV=/venv/main
TRACE=$REPO/scratch/traces/tracelab_moriM_L64k_yunuikang.jsonl
OUT="${OUT:-$REPO/scratch/mori/h200_phase2}"
RES="$OUT/results_phase2.jsonl"
SUMJ="$OUT/cell_summaries.jsonl"
PROGRESS="${PROGRESS:-$OUT/progress.md}"
GATEJ="$OUT/gate_percell.jsonl"
BP=8123; PP=9000
FIT=20.00; MAXTOK=647520          # = round(20.00 x 32,376) — 계획 §4.1 격자
DUR="${DUR:-3600}"; GRACE="${GRACE:-60}"; WARM="${WARM:-0.2}"; SETTLE="${SETTLE:-60}"
MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}"
SERVE="${SERVE:-$REPO/scripts/_serve_sglang_7b""_tp1_h200_mori_yunuikang.sh}"
CLIST="${CLIST:-20 80 40}"
SYSLIST="${SYSLIST:-SMG TA TAO MORI}"
BOOT_TIMEOUT_S="${BOOT_TIMEOUT_S:-900}"
HM="sglang:hicache_host_used_tokens,sglang:hicache_host_total_tokens,sglang:evicted_tokens_total,sglang:load_back_tokens_total,sglang:cached_tokens_total,sglang:prompt_tokens_total,sglang:generation_tokens_total"

mkdir -p "$OUT"; source "$VENV/bin/activate"

sys_router(){ case "$1" in SMG) echo default;; TA|TAO) echo tr;; MORI) echo mori;; esac; }
sys_ratio(){  case "$1" in SMG|TA) echo 0;; TAO|MORI) echo 2;; esac; }
sys_evict(){  case "$1" in MORI) echo mori;; *) echo lru;; esac; }
sys_extra(){  case "$1" in MORI) echo "--mori-cpu-capacity-ratio 2";; *) echo "";; esac; }

BPID=""; SPID=""; EPID=""
kill_backend(){
  [ -n "$BPID" ] && kill "$BPID" 2>/dev/null
  pkill -9 -f "_serve_sglang_7b_tp1_h200_mori_yunuikang" 2>/dev/null
  pkill -9 -f "sglang.launch_server" 2>/dev/null
  pkill -9 -f "sglang::" 2>/dev/null
  sleep 8; BPID=""
}
kill_proxy(){   # TERM -> KILL -> 포트 확인 (stale 프록시가 남으면 다음 셀이 이전 라우터에 붙는다)
  local pids sig
  for sig in TERM KILL; do
    pids=""
    for pid in $(pgrep -f "bin/thunderagent" 2>/dev/null); do
      cl=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
      case " $cl " in *" --port $PP "*) pids="$pids $pid";; esac
    done
    [ -z "$pids" ] && break
    kill -$sig $pids 2>/dev/null
    for _ in $(seq 1 10); do curl -sf -m 2 "http://127.0.0.1:$PP/health" >/dev/null 2>&1 || break; sleep 1; done
  done
  sleep 2
}
kill_samplers(){ [ -n "$SPID" ] && kill "$SPID" 2>/dev/null; [ -n "$EPID" ] && kill "$EPID" 2>/dev/null; SPID=""; EPID=""; }
trap 'kill_samplers; kill_proxy; kill_backend' EXIT

wait_gpu_idle(){
  for _ in $(seq 1 30); do
    n=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | awk 'NF{c++} END{print c+0}')
    [ "$n" = "0" ] && return 0; sleep 2
  done; kill_backend
}
log(){ echo "[$(date +%H:%M:%S)] $*"; }

boot_backend(){ # $1=EVICT $2=RATIO $3=tag
  kill_proxy; kill_backend; wait_gpu_idle
  local lg="$OUT/serve_$3.log"
  log "  boot EVICT=$1 RATIO=$2 MAXTOK=$MAXTOK"
  MAXTOK=$MAXTOK RATIO="$2" EVICT="$1" PORT=$BP MEMFRAC=0.90 LOG="$lg" \
    nohup bash "$SERVE" >/dev/null 2>&1 &
  BPID=$!
  for i in $(seq 1 $((BOOT_TIMEOUT_S/3))); do
    curl -sf "http://127.0.0.1:$BP/health" >/dev/null 2>&1 && { log "  READY ~$((i*3))s"; return 0; }
    kill -0 "$BPID" 2>/dev/null || { log "  !! DIED"; tail -5 "$lg"; return 1; }
    sleep 3
  done
  log "  !! BOOT TIMEOUT"; tail -5 "$lg"; return 1
}

emit(){ # $1=tag $2=system $3=Clabel $4=C $5=t0 $6=t1 $7=status $8=note
  python "$REPO/scripts/phase1_cell_summary_yunuikang.py" \
    --tag "$1" --system "$2" --fit-label "$3" --fit "$FIT" --maxtok "$MAXTOK" \
    --out-dir "$OUT" --results "$RES" --dur "$DUR" --t-start "$5" --t-end "$6" \
    --status "$7" --note "$8" --progress "$PROGRESS" --summary-json "$SUMJ" \
    --profile-dir "$OUT/profile_$1" || true
}

run_cell(){ # $1=system $2=C
  local sysn=$1 C=$2 tag="${1}_C${2}"
  local router=$(sys_router "$sysn") ratio=$(sys_ratio "$sysn") evict=$(sys_evict "$sysn")
  local extra=$(sys_extra "$sysn") stag="${sysn}_C${C}"
  local t0=$(date +%s)

  if ! boot_backend "$evict" "$ratio" "$stag"; then
    log "[cell $tag] SKIP — 백엔드 기동 실패"
    emit "$tag" "$sysn" "C$C" "$C" "$t0" "$(date +%s)" "SKIP_BOOT" "백엔드 기동 실패"; return 0
  fi
  # §7.1b 셀마다 게이트 (probe 없음)
  if ! python "$REPO/scripts/fit_gate_yunuikang.py" \
        --backend "http://127.0.0.1:$BP" --log "$OUT/serve_$stag.log" \
        --model "$MODEL" --tokenizer "$MODEL" \
        --target-maxtok $MAXTOK --ratio "$ratio" --tag "gate_$tag" --out "$GATEJ" \
        >> "$OUT/gate_$tag.log" 2>&1; then
    log "[cell $tag] SKIP — §7.1b 게이트 FAIL"
    emit "$tag" "$sysn" "C$C" "$C" "$t0" "$(date +%s)" "SKIP_GATE" "게이트 FAIL"; return 0
  fi

  log "[cell $tag] START router=$router ratio=$ratio evict=$evict C=$C dur=${DUR}s"
  kill_proxy; mkdir -p "$OUT/profile_$tag"
  nohup thunderagent --backend-type sglang --backends "http://localhost:$BP" --port $PP \
    --router "$router" --metrics --profile --profile-dir "$OUT/profile_$tag" $extra \
    > "$OUT/proxy_$tag.log" 2>&1 &
  local up=0
  for _ in $(seq 1 60); do curl -sf "http://127.0.0.1:$PP/health" >/dev/null 2>&1 && { up=1; break; }; sleep 1; done
  if [ "$up" != "1" ]; then
    log "[cell $tag] SKIP — 프록시 기동 실패"
    emit "$tag" "$sysn" "C$C" "$C" "$t0" "$(date +%s)" "CRASH" "프록시 기동 실패"; return 0
  fi
  MODE=$(curl -s "http://127.0.0.1:$PP/health" | python -c 'import sys,json;print(json.load(sys.stdin)["router_mode"])' 2>/dev/null)
  if [ "$MODE" != "$router" ]; then
    log "[cell $tag] SKIP — router_mode=$MODE != $router"
    emit "$tag" "$sysn" "C$C" "$C" "$t0" "$(date +%s)" "CRASH" "router_mode 불일치"; return 0
  fi
  [ "$router" = "mori" ] && { sleep 6; grep -a "MORI CPU tier" "$OUT/proxy_$tag.log" | tail -1 | sed 's/^/   [I6] /'; }

  nohup python "$REPO/scripts/phase2_engine_sampler_yunuikang.py" \
    --backend "http://127.0.0.1:$BP" --out "$OUT/engine_$tag.csv" --interval 5 >/dev/null 2>&1 & EPID=$!
  nohup python "$REPO/scripts/sample_gpu_resident_yunuikang.py" --gpus 0 --out "$OUT/gpu_$tag.jsonl" \
    --health-url "http://localhost:$PP/health" --backends "http://localhost:$BP" >/dev/null 2>&1 & SPID=$!

  local tdrv=$(date +%s)
  timeout $((DUR+GRACE+900)) python "$REPO/scripts/mori_replay_driver_yunuikang.py" --trace "$TRACE" \
    --base-url "http://localhost:$PP" --router-url "http://localhost:$PP" --backends "http://localhost:$BP" \
    --model "$MODEL" --tokenizer "$MODEL" --router "$router" --system "$sysn" \
    --concurrency "$C" --duration-s "$DUR" --deadline-grace-s $GRACE --warmup-frac $WARM \
    --metric-interval 30 --ctx-cap 69632 --http-timeout 2400 --hicache-ratio "$ratio" \
    --hicache-metrics "$HM" --run-tag "$tag" --out "$RES" 2> "$OUT/err_$tag.log"
  local rc=$?
  kill_samplers; kill_proxy
  local t1=$(date +%s)
  sleep "$SETTLE"
  if [ $rc -ne 0 ]; then
    log "[cell $tag] driver rc=$rc — 부분 결과로 집계"
    emit "$tag" "$sysn" "C$C" "$C" "$tdrv" "$t1" "CRASH" "driver rc=$rc"
  else
    emit "$tag" "$sysn" "C$C" "$C" "$tdrv" "$t1" "OK" ""
    log "[cell $tag] DONE"
  fi
  return 0
}

if [ ! -s "$PROGRESS" ]; then
  {
    echo "# H200 Phase 2 진행 상황 (러너용 임시 로그 · 정식 기록은 logs/*_H200_RESULTS_*)"
    echo
    echo "- 시작: $(date '+%Y-%m-%d %H:%M:%S %Z') · 모델 $MODEL · fit $FIT (MAXTOK $MAXTOK) · r=2 · 셀당 ${DUR}s"
    echo "- 순서: C $CLIST · 시스템 $SYSLIST · **셀마다 백엔드 재기동**(캐시 cold start)"
    echo "- goodput 은 **점추정**이다 (프록시 --profile per-step, TTFT=pause+prefill) — PREREG §E"
    echo
    echo "| 셀 | C | 상태 | 시작 | 종료 | thr(드라이버) | thr(엔진) | TTFT p50 | TTFT p95 | goodput@5s | goodput구간 | MORI÷TA+O | Waiting축출 | ping-pong | steady턴 | 비고 |"
    echo "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"
  } > "$PROGRESS"
fi

log "############ H200 PHASE 2 START ############"
log "  fit=$FIT MAXTOK=$MAXTOK · C: $CLIST · 시스템: $SYSLIST · 셀당 ${DUR}s"
log "  예상 $(python3 -c "print(f'{12*($DUR+270)/3600:.1f}')")h · progress=$PROGRESS"

for C in $CLIST; do
  log "===== C=$C ====="
  for S in $SYSLIST; do run_cell "$S" "$C"; done
  # C 그룹이 끝날 때마다 중간 판정을 갱신해 둔다 (도중에 죽어도 그때까지의 그림이 남는다)
  python "$REPO/scripts/phase2_verdict_yunuikang.py" --summary-json "$SUMJ" \
    --progress "$PROGRESS" --partial || true
done

kill_samplers; kill_proxy; kill_backend
python "$REPO/scripts/phase2_verdict_yunuikang.py" --summary-json "$SUMJ" --progress "$PROGRESS" || true
log "############ H200 PHASE 2 DONE ############"
