#!/usr/bin/env bash
# STEP 5 확장 — duty×f 갭 측정 (GPU1, C=10, R=1)
# 재사용: d=0.1 전체 f, d=0.2/0.5 f={1,1.5,∞} (GPU0 파일럿). 없는 조합만 측정.
# 작성: 강윤의 · 2026-07-21
set -u
cd /home/yunuikang/yunuikang_work/distserving

VENV=/home/yunuikang/yunuikang_work/.venv
PY=$VENV/bin/python
GPU=1
FULL="1.0,1.5,2.0,1000000"   # d=0.3/0.7/0.9
GAP="2.0"                     # d=0.2/0.5 (f=1.5는 재사용)

run() {
  local d=$1 fg=$2 out=$3
  echo "############ d=$d  f-grid=$fg  → $out ############"
  $PY scripts/sweep_pilot_yunuikang.py \
    --duty "$d" \
    --trace "scratch/step4/synth_d${d}_v3.jsonl" \
    --concurrency 10 \
    --f-grid "$fg" \
    --repeats 1 \
    --out-dir "$out" \
    --gpu "$GPU"
}

# 없는 조합만 (총 14 runs)
run 0.3 "$FULL" scratch/step5/gap_d03
run 0.7 "$FULL" scratch/step5/gap_d07
run 0.9 "$FULL" scratch/step5/gap_d09
run 0.2 "$GAP"  scratch/step5/gap_d02
run 0.5 "$GAP"  scratch/step5/gap_d05

echo "############ ALL GAP RUNS DONE ############"
