#!/usr/bin/env bash
# SWE-bench Lite stratified-64 녹화 실행기 (tmux + sg docker 하에서 구동).
# 요청이 프록시(:9000, --profile)를 통과하며 step_profiles.csv에 per-step 기록.
set -uo pipefail

source /home/yunuikang/yunuikang_work/.venv/bin/activate
export MSWEA_SILENT_STARTUP=1
cd /home/yunuikang/yunuikang_work/distserving

FILTER="$(cat /home/yunuikang/yunuikang_work/scratch/traces/swebench_stratified64.filter.txt)"
LOG=/home/yunuikang/yunuikang_work/scratch/rec_swebench/run_full.log

echo "[record] start $(date '+%F %T')  workers=12 step_limit=40" | tee -a "$LOG"
mini-extra swebench \
  --subset lite --split test \
  --filter "$FILTER" \
  --workers 12 \
  --config scripts/swebench_qwen_config_yunuikang.yaml \
  --environment-class docker \
  --cleanup-images \
  --output /home/yunuikang/yunuikang_work/scratch/swebench_out 2>&1 | tee -a "$LOG"
echo "[record] done $(date '+%F %T')" | tee -a "$LOG"
