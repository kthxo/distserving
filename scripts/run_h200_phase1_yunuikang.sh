#!/usr/bin/env bash
# H200 Phase 1 — fit 스윕 (인과 확증). 무인 야간 실행용.
#
# 계획: plans/2026-08-04_PLAN_h200-rescale-reproduction_yunuikang.md rev3 §5.1 Phase 1
# 사전 등록: logs/2026-08-05_H200_GATE_PREREG_yunuikang.md §10 (첫 셀 전에 커밋됨)
#
#   F1 8.10 -> [★ §7.1c 분기 판정] -> F2 12.00 -> F3 16.00 -> F4 20.00
#   각 fit: TA+O(lru/tr) 셀, MORI(mori/mori r2) 셀. C=80, r=2, 30분.
#
# 규약 (PREREG §10.5):
#   * 셀마다 §7.1b 게이트를 먼저 돈다(--ratio 2, probe 없음). FAIL이면 그 셀만 SKIP.
#   * 셀 하나가 죽어도 전체는 계속된다. 백엔드 기동 실패는 해당 셀만 건너뛴다.
#   * F1이 붕괴를 재현하지 못하면 거기서 멈춘다. F2~F4를 돌리지 않는다.
#   * Phase 1이 끝나면 멈춘다. Phase 2는 자동으로 시작하지 않는다.
#
# 기존 스크립트/트레이스/baseline 무수정 — 호출만 한다.
set -uo pipefail
REPO=/workspace/distserving
VENV=/venv/main
TRACE=$REPO/scratch/traces/tracelab_moriM_L64k_yunuikang.jsonl
OUT="${OUT:-$REPO/scratch/mori/h200_phase1}"
RES="$OUT/results_phase1.jsonl"
SUMJ="$OUT/cell_summaries.jsonl"
PROGRESS="${PROGRESS:-$REPO/logs/2026-08-05_H200_PHASE1_PROGRESS_yunuikang.md}"
GATEJ="$OUT/gate_percell.jsonl"
BP=8123; PP=9000
C=80; RATIO=2
DUR="${DUR:-1800}"; GRACE="${GRACE:-60}"; WARM="${WARM:-0.2}"
SETTLE="${SETTLE:-60}"   # §5.3: 셀 종료 후 CSV mtime이 60초 지난 뒤에만 집계
MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}"
SERVE="${SERVE:-$REPO/scripts/_serve_sglang_7b_tp1_h200_mori_yunuikang.sh}"
VERDICT_MODE="${VERDICT_MODE:-sweep}"   # sweep(rev3 fit 스윕) | model-confound(rev4 8B)
AFTER_F1="${AFTER_F1:-sweep}"           # sweep = F2~F4 진행 | stop = F1에서 종료
BOOT_TIMEOUT_S="${BOOT_TIMEOUT_S:-900}"
HM="sglang:hicache_host_used_tokens,sglang:hicache_host_total_tokens,sglang:evicted_tokens_total,sglang:load_back_tokens_total,sglang:cached_tokens_total,sglang:prompt_tokens_total,sglang:generation_tokens_total"

# fit 격자 — PREREG §10.4. pool_tok = round(fit x 32,376)
FITS="F1:8.10:262246 F2:12.00:388512 F3:16.00:518016 F4:20.00:647520"

mkdir -p "$OUT"
source "$VENV/bin/activate"

BPID=""; SPID=""; EPID=""
kill_backend(){
  [ -n "$BPID" ] && kill "$BPID" 2>/dev/null
  pkill -9 -f "_serve_sglang_7b_tp1_h200_mori_yunuikang" 2>/dev/null
  pkill -9 -f "_serve_sglang_8b_tp1_h200_mori_yunuikang" 2>/dev/null
  pkill -9 -f "sglang.launch_server" 2>/dev/null
  pkill -9 -f "sglang::" 2>/dev/null
  sleep 8; BPID=""
}
# SIGTERM 만으로는 안 죽는다 [측정 2026-08-05: 체인 검증 후 tr/mori 프록시 2개가 살아남아
# 포트 9000을 계속 물고 있었다]. stale 프록시가 남으면 이후 모든 셀이 기동 실패하거나 —
# 더 나쁘게는 — 드라이버가 **이전 셀의 라우터**에 붙는다. TERM -> KILL -> 포트 확인까지 한다.
kill_proxy(){
  local pids sig
  for sig in TERM KILL; do
    pids=""
    for pid in $(pgrep -f "bin/thunderagent" 2>/dev/null); do
      cl=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
      case " $cl " in *" --port $PP "*) pids="$pids $pid";; esac
    done
    [ -z "$pids" ] && break
    kill -$sig $pids 2>/dev/null
    for _ in $(seq 1 10); do
      curl -sf -m 2 "http://127.0.0.1:$PP/health" >/dev/null 2>&1 || break
      sleep 1
    done
  done
  # 포트가 정말 비었는지 최종 확인 — 안 비었으면 그 사실을 로그에 남긴다(셀은 MODE 체크가 잡는다)
  if curl -sf -m 2 "http://127.0.0.1:$PP/health" >/dev/null 2>&1; then
    echo "   [warn] 포트 $PP 가 여전히 응답한다 — stale 프록시 잔존 가능"
  fi
  sleep 2
}
kill_samplers(){ [ -n "$SPID" ] && kill "$SPID" 2>/dev/null; [ -n "$EPID" ] && kill "$EPID" 2>/dev/null; SPID=""; EPID=""; }
trap 'kill_samplers; kill_proxy; kill_backend' EXIT

wait_gpu_idle(){
  for _ in $(seq 1 30); do
    n=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | awk 'NF{c++} END{print c+0}')
    [ "$n" = "0" ] && return 0
    sleep 2
  done
  kill_backend
}

log(){ echo "[$(date +%H:%M:%S)] $*"; }

boot_backend(){ # $1=EVICT  $2=MAXTOK  $3=tag
  kill_proxy; kill_backend; wait_gpu_idle
  local lg="$OUT/serve_$3.log"
  log "==[$3] backend boot EVICT=$1 MAXTOK=$2 RATIO=$RATIO"
  MAXTOK="$2" RATIO=$RATIO EVICT="$1" PORT=$BP MEMFRAC=0.90 LOG="$lg" \
    nohup bash "$SERVE" >/dev/null 2>&1 &
  BPID=$!
  for i in $(seq 1 $((BOOT_TIMEOUT_S/3))); do
    curl -sf "http://127.0.0.1:$BP/health" >/dev/null 2>&1 && { log "   READY ~$((i*3))s"; return 0; }
    kill -0 "$BPID" 2>/dev/null || { log "   !! DIED"; tail -5 "$lg"; return 1; }
    sleep 3
  done
  log "   !! BOOT TIMEOUT"; tail -5 "$lg"; return 1
}

# §7.1b per-cell gate. probe 없음 — 부하를 주면 셀을 오염시키고, 캡 강제는 F1b에서 확증됐다.
run_gate(){ # $1=tag(serve log tag)  $2=MAXTOK  $3=cell tag
  python "$REPO/scripts/fit_gate_yunuikang.py" \
    --backend "http://127.0.0.1:$BP" --log "$OUT/serve_$1.log" \
    --target-maxtok "$2" --ratio $RATIO --tag "gate_$3" --out "$GATEJ" \
    >> "$OUT/gate_$3.log" 2>&1
}

emit(){ # $1=tag $2=system $3=fitlabel $4=fit $5=maxtok $6=t0 $7=t1 $8=status $9=note
  python "$REPO/scripts/phase1_cell_summary_yunuikang.py" \
    --tag "$1" --system "$2" --fit-label "$3" --fit "$4" --maxtok "$5" \
    --out-dir "$OUT" --results "$RES" --dur "$DUR" --t-start "$6" --t-end "$7" \
    --status "$8" --note "$9" --progress "$PROGRESS" --summary-json "$SUMJ" || true
}

run_cell(){ # $1=tag $2=system(MORI|TAO) $3=router $4=extra $5=fitlabel $6=fit $7=maxtok $8=servetag
  local tag=$1 sysn=$2 router=$3 extra=$4 flabel=$5 fit=$6 mtok=$7 stag=$8
  local t0=$(date +%s)

  if ! run_gate "$stag" "$mtok" "$tag"; then
    log "[cell $tag] SKIP — §7.1b 게이트 FAIL (gate_$tag.log)"
    emit "$tag" "$sysn" "$flabel" "$fit" "$mtok" "$t0" "$(date +%s)" "SKIP_GATE" "게이트 FAIL"
    return 0
  fi

  log "[cell $tag] START C=$C r=$RATIO dur=${DUR}s"
  kill_proxy
  mkdir -p "$OUT/profile_$tag"
  nohup thunderagent --backend-type sglang --backends "http://localhost:$BP" --port $PP \
    --router "$router" --metrics --profile --profile-dir "$OUT/profile_$tag" $extra \
    > "$OUT/proxy_$tag.log" 2>&1 &
  local up=0
  for _ in $(seq 1 60); do curl -sf "http://127.0.0.1:$PP/health" >/dev/null 2>&1 && { up=1; break; }; sleep 1; done
  if [ "$up" != "1" ]; then
    log "[cell $tag] SKIP — 프록시 기동 실패"
    emit "$tag" "$sysn" "$flabel" "$fit" "$mtok" "$t0" "$(date +%s)" "CRASH" "프록시 기동 실패"
    return 0
  fi
  MODE=$(curl -s "http://127.0.0.1:$PP/health" | python -c 'import sys,json;print(json.load(sys.stdin)["router_mode"])' 2>/dev/null)
  if [ "$MODE" != "$router" ]; then
    log "[cell $tag] SKIP — router_mode=$MODE != $router"
    emit "$tag" "$sysn" "$flabel" "$fit" "$mtok" "$t0" "$(date +%s)" "CRASH" "router_mode 불일치"
    return 0
  fi
  # I6 (프록시측): MORI 스케줄러 CpuTier 장부
  if [ "$router" = "mori" ]; then
    sleep 6
    grep -a "MORI CPU tier" "$OUT/proxy_$tag.log" | tail -1 | sed 's/^/   [I6] /'
  fi

  nohup python "$REPO/scripts/phase2_engine_sampler_yunuikang.py" \
    --backend "http://127.0.0.1:$BP" --out "$OUT/engine_$tag.csv" --interval 5 >/dev/null 2>&1 & EPID=$!
  nohup python "$REPO/scripts/sample_gpu_resident_yunuikang.py" --gpus 0 --out "$OUT/gpu_$tag.jsonl" \
    --health-url "http://localhost:$PP/health" --backends "http://localhost:$BP" >/dev/null 2>&1 & SPID=$!

  local tdrv=$(date +%s)
  timeout $((DUR+GRACE+900)) python "$REPO/scripts/mori_replay_driver_yunuikang.py" --trace "$TRACE" \
    --base-url "http://localhost:$PP" --router-url "http://localhost:$PP" --backends "http://localhost:$BP" \
    --model "$MODEL" --tokenizer "$MODEL" --router "$router" --system "$sysn" \
    --concurrency $C --duration-s "$DUR" --deadline-grace-s $GRACE --warmup-frac $WARM \
    --metric-interval 30 --ctx-cap 69632 --http-timeout 2400 --hicache-ratio $RATIO \
    --hicache-metrics "$HM" --run-tag "$tag" --out "$RES" 2> "$OUT/err_$tag.log"
  local rc=$?
  kill_samplers; kill_proxy
  local t1=$(date +%s)

  # goodput 고정창 규칙: 셀 종료 후 60초 지난 뒤 집계 (§5.3 — 낙오 스텝이 창을 부풀린 전력)
  sleep "$SETTLE"
  if [ $rc -ne 0 ]; then
    log "[cell $tag] driver rc=$rc — 부분 결과로 집계 시도"
    emit "$tag" "$sysn" "$flabel" "$fit" "$mtok" "$tdrv" "$t1" "CRASH" "driver rc=$rc"
  else
    emit "$tag" "$sysn" "$flabel" "$fit" "$mtok" "$tdrv" "$t1" "OK" ""
    log "[cell $tag] DONE"
  fi
  return 0
}

run_fit(){ # $1=label $2=fit $3=maxtok
  local flabel=$1 fit=$2 mtok=$3
  # --- TA+O: engine LRU + HiCache, tr router ---
  if boot_backend lru "$mtok" "lru_$flabel"; then
    run_cell "TAO_$flabel" TAO tr "" "$flabel" "$fit" "$mtok" "lru_$flabel"
  else
    log "[fit $flabel] TA+O 백엔드 기동 실패 — 셀 SKIP"
    emit "TAO_$flabel" TAO "$flabel" "$fit" "$mtok" "$(date +%s)" "$(date +%s)" "SKIP_BOOT" "백엔드 기동 실패"
  fi
  # --- MORI: typed eviction + HiCache, mori router r=2 ---
  if boot_backend mori "$mtok" "mori_$flabel"; then
    run_cell "MORI_$flabel" MORI mori "--mori-cpu-capacity-ratio 2" "$flabel" "$fit" "$mtok" "mori_$flabel"
  else
    log "[fit $flabel] MORI 백엔드 기동 실패 — 셀 SKIP"
    emit "MORI_$flabel" MORI "$flabel" "$fit" "$mtok" "$(date +%s)" "$(date +%s)" "SKIP_BOOT" "백엔드 기동 실패"
  fi
}

# ── progress 파일 헤더 (한 번만) ────────────────────────────────────────────
if [ ! -s "$PROGRESS" ]; then
  {
    echo "# H200 Phase 1 진행 상황 (자동 append)"
    echo
    echo "- 시작: $(date '+%Y-%m-%d %H:%M:%S %Z') · C=$C · r=$RATIO · 셀당 ${DUR}s · **모델 $MODEL** · TP1"
    echo "- 사전 등록: \`logs/2026-08-05_H200_GATE_PREREG_yunuikang.md\` §10 · 계획 rev3 §5.1 Phase 1"
    echo "- goodput은 **점추정이 아니라 TTFT 순서통계 구간**이다 (드라이버가 per-turn을 저장하지 않음, PREREG §10.6)"
    echo "- Waiting 축출은 시스템마다 **다른 사건**이다 — MORI: \`CPU->Waiting\`, TA+O: \`Paused program\`. 절대값 비교 불가"
    echo
    echo "| 셀 | fit | 상태 | 시작 | 종료 | thr(드라이버) | thr(엔진) | TTFT p50 | TTFT p95 | goodput@5s | MORI÷TA+O | Waiting축출 | ping-pong | steady턴 | 비고 |"
    echo "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"
  } > "$PROGRESS"
fi

log "############ H200 PHASE 1 START ############"
log "  격자: $FITS"
log "  셀당 ${DUR}s · 예상 $(python3 -c "print(f'{8*($DUR+240)/3600:.1f}')")h · progress=$PROGRESS"

# ── F1 먼저, 그리고 §7.1c 분기 판정 ────────────────────────────────────────
run_fit F1 8.10 262246

if python "$REPO/scripts/phase1_f1_verdict_yunuikang.py" \
     --summary-json "$SUMJ" --progress "$PROGRESS" --fit-label F1 --mode "$VERDICT_MODE"; then
  if [ "${SMOKE:-0}" = "1" ] || [ "$AFTER_F1" = "stop" ]; then
    log "★ F1에서 종료 (SMOKE=${SMOKE:-0} AFTER_F1=$AFTER_F1) — F2~F4로 진행하지 않는다"
  else
  log "★ F1 재현 확인 — F2~F4 자동 진행"
  run_fit F2 12.00 388512
  run_fit F3 16.00 518016
  run_fit F4 20.00 647520
  fi
else
  log "★ F1 재현 실패/모호 — PREREG §10.3에 따라 중단. F2~F4를 돌리지 않는다."
fi

kill_samplers; kill_proxy; kill_backend
{
  echo
  echo "---"
  echo
  echo "**Phase 1 종료: $(date '+%Y-%m-%d %H:%M:%S %Z')** — Phase 2는 자동으로 시작하지 않는다 (PREREG §10.5.3)."
} >> "$PROGRESS"
log "############ H200 PHASE 1 DONE ############"
