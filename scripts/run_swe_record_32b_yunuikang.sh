#!/usr/bin/env bash
# P1-2 SWE re-record (Qwen3-32B): stratified-64 via proxy(:9000 default --profile) + docker.
# Assumes Deployment A backend (:8000) is up and IDLE (TraceLab sweep finished).
# Outputs: step_profiles.csv in RECDIR, mini-swe trajectories in OUTDIR.
set -uo pipefail
REPO=/home/yunuikang/yunuikang_work/distserving
source /home/yunuikang/yunuikang_work/.venv/bin/activate
HDR=/home/yunuikang/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/include/python3.12
export CPATH="$HDR" C_INCLUDE_PATH="$HDR" VLLM_USE_FLASHINFER_SAMPLER=0
FILTER=$(cat /home/yunuikang/yunuikang_work/scratch/traces/swebench_stratified64.filter.txt)
RECDIR=/home/yunuikang/yunuikang_work/scratch/tp2/rec_swe
OUTDIR=/home/yunuikang/yunuikang_work/scratch/tp2/swebench_out_32b
WORKERS="${WORKERS:-12}"
mkdir -p "$RECDIR" "$OUTDIR"

# fresh proxy with profiling (default router for recording — minimize scheduling interference)
pkill -9 -f "bin/thunderagent" 2>/dev/null; sleep 3
nohup thunderagent --backend-type vllm --backends http://localhost:8000 --port 9000 \
  --router default --metrics --profile --profile-dir "$RECDIR" \
  > /home/yunuikang/yunuikang_work/scratch/tp2/proxy_rec_swe.log 2>&1 &
echo $! > /home/yunuikang/yunuikang_work/scratch/tp2/rec_proxy.pid
for i in $(seq 1 30); do curl -sf http://localhost:9000/health >/dev/null 2>&1 && break; sleep 2; done
MODE=$(curl -s http://localhost:9000/health | python -c 'import sys,json;print(json.load(sys.stdin)["router_mode"])' 2>/dev/null)
echo "rec proxy up: mode=$MODE (expect default)"
[ "$MODE" = "default" ] || { echo "FATAL: proxy not default"; exit 3; }

echo "### SWE record START $(date) workers=$WORKERS stratified-64 model=Qwen3-32B"
mini-extra swebench --subset lite --split test \
  --filter "$FILTER" --workers "$WORKERS" \
  --config "$REPO/scripts/swebench_qwen32b_config_yunuikang.yaml" \
  --environment-class docker --cleanup-images \
  --output "$OUTDIR"
echo "### SWE record DONE $(date)"
echo "step_profiles rows: $(wc -l < "$RECDIR/step_profiles.csv" 2>/dev/null || echo 0)"
