#!/usr/bin/env bash
# §7.1b gate — F1 short verification + two-point sensitivity. NOT a measurement cell:
# no trace is read, no driver runs, no baseline is touched. ~17 min total.
#
# Plan: plans/2026-08-04_PLAN_h200-rescale-reproduction_yunuikang.md (rev3) §5.1 Phase 0,
#       risks 7.1b / 7.5 / 7.6.
# Pre-registration: logs/2026-08-05_H200_GATE_PREREG_yunuikang.md (committed BEFORE this runs).
#
#   step 1  boot F1 (MAXTOK=262,246 -> fit 8.10, the 5090-parity control cell), gate + G4 probe
#   step 2  boot F4 (MAXTOK=647,520 -> fit 20.00, the target regime),           gate, no probe
#   step 3  G6 slope: dN/dMAXTOK == 1.00 +- 0.05 across the two points
#
# Both boots use RATIO=0 / EVICT=lru: this gate tests the GPU pool cap only, so HiCache and
# the MORI policy are deliberately out of the picture (G3 reports SKIP). The host-tier
# ledger check runs per-cell in Phase 1, where RATIO=2.
set -uo pipefail
REPO=/workspace/distserving
VENV=/venv/main
OUT="${OUT:-$REPO/scratch/mori/h200_gate}"
RES="$OUT/gate_results.jsonl"
BP="${BP:-8123}"
F1_MAXTOK=262246          # round(8.10 x 32,376)  — plan §4.1 fit grid
F4_MAXTOK=647520          # round(20.00 x 32,376) — plan §4.1 fit grid
BOOT_TIMEOUT_S="${BOOT_TIMEOUT_S:-900}"
TAG1="${TAG1:-F1}"        # label of the F1 run (F1b for the §9.3 corrected-instrument re-run)
SKIP_F4="${SKIP_F4:-0}"   # 1 = F1 step only (F4/G6 already recorded)
mkdir -p "$OUT"
source "$VENV/bin/activate"

BPID=""
kill_backend(){
  [ -n "$BPID" ] && kill "$BPID" 2>/dev/null
  pkill -9 -f "_serve_sglang_7b_tp1_h200_mori_yunuikang" 2>/dev/null
  pkill -9 -f "sglang.launch_server" 2>/dev/null
  pkill -9 -f "sglang::" 2>/dev/null
  sleep 8; BPID=""
}
trap 'kill_backend' EXIT

wait_gpu_idle(){
  # NOTE: `| grep -c . || echo 0` (the 5090 script's idiom) is broken — with no compute procs
  # grep prints "0" AND exits 1, so `|| echo 0` appends a second "0" and the test never matches.
  # Count with awk instead, which exits 0 either way.
  for _ in $(seq 1 30); do
    n=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | awk 'NF{c++} END{print c+0}')
    [ "$n" = "0" ] && { echo "   [gpu] compute procs=0 (유휴)"; return 0; }
    sleep 2
  done
  echo "   [gpu] !! compute procs 잔존 — 강제 종료"; kill_backend
}

boot(){ # $1=MAXTOK  $2=tag
  kill_backend; wait_gpu_idle
  local log="$OUT/serve_$2.log"
  echo "==[$2] boot MAXTOK=$1 (fit $(python3 -c "print(f'{$1/32376:.2f}')")) $(date +%T)"
  MAXTOK="$1" RATIO=0 EVICT=lru PORT=$BP MEMFRAC=0.90 LOG="$log" \
    nohup bash "$REPO/scripts/_serve_sglang_7b_tp1_h200_mori_yunuikang.sh" >/dev/null 2>&1 &
  BPID=$!
  for i in $(seq 1 $((BOOT_TIMEOUT_S/3))); do
    curl -sf "http://127.0.0.1:$BP/health" >/dev/null 2>&1 && { echo "   READY ~$((i*3))s"; return 0; }
    kill -0 "$BPID" 2>/dev/null || {
      echo "   !! DIED — 마지막 로그:"; tail -20 "$log"; return 1; }
    sleep 3
  done
  echo "   !! TIMEOUT ${BOOT_TIMEOUT_S}s"; tail -20 "$log"; return 1
}

echo "############ §7.1b FIT GATE  start $(date) ############"
echo "  results -> $RES"

# ── step 1: F1 + behavioural probe ──────────────────────────────────────────
boot $F1_MAXTOK "$TAG1" || exit 1
python "$REPO/scripts/fit_gate_yunuikang.py" \
  --backend "http://127.0.0.1:$BP" --log "$OUT/serve_$TAG1.log" \
  --target-maxtok $F1_MAXTOK --ratio 0 --probe --tag "$TAG1" --out "$RES"
RC1=$?
echo "   [$TAG1] gate rc=$RC1"

RC2=0; RC3=0
if [ "$SKIP_F4" = "1" ]; then
  kill_backend
  echo "   [F4] SKIP (SKIP_F4=1 — 이미 기록됨)"
else
  # ── step 2: F4, static gate only (two-point sensitivity) ──────────────────
  boot $F4_MAXTOK F4 || exit 1
  python "$REPO/scripts/fit_gate_yunuikang.py" \
    --backend "http://127.0.0.1:$BP" --log "$OUT/serve_F4.log" \
    --target-maxtok $F4_MAXTOK --ratio 0 --tag F4 --out "$RES"
  RC2=$?
  echo "   [F4] gate rc=$RC2"

  kill_backend

  # ── step 3: G6 slope ─────────────────────────────────────────────────────
  python "$REPO/scripts/fit_gate_yunuikang.py" --slope-check "$RES"
  RC3=$?
fi

echo "############ FIT GATE DONE $(date)  F1=$RC1 F4=$RC2 slope=$RC3 ############"
[ "$RC1" = "0" ] && [ "$RC2" = "0" ] && [ "$RC3" = "0" ] \
  && echo "  ==> GATE PASS — Phase 1 진행 가능" \
  || echo "  ==> GATE FAIL — PREREG 문서의 FAIL 행동표를 따를 것 (임계값 조정 금지)"
exit $(( RC1 || RC2 || RC3 ))
