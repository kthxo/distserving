#!/usr/bin/env bash
# P3 HLE smoke: run eval_hle_local_p3 on a few HLE questions through the proxy.
# Assumes Deployment B up (retriever:1401, orchestrator:8100, proxy:9000).
# Usage: run_hle_smoke_p3_yunuikang.sh [example_jsonl] [n_out_dir_tag]
set -uo pipefail
set -a; source /home/yunuikang/yunuikang_work/.hle_env 2>/dev/null; set +a
source /home/yunuikang/yunuikang_work/.venv/bin/activate
export GLM_BASE_URL="https://api.z.ai/api/paas/v4"   # correct path
export HLE_ENABLE_JUDGE=0 TAVILY_KEY="" HLE_CONCURRENCY=1
EVAL=/home/yunuikang/yunuikang_work/distserving/examples/inference/ToolOrchestra/evaluation
EX="${1:-/home/yunuikang/yunuikang_work/scratch/p3_assets/hle_smoke5.jsonl}"
TAG="${2:-smoke}"
OUT=/home/yunuikang/yunuikang_work/scratch/p3/eval_out_$TAG
mkdir -p "$OUT"
cd "$EVAL"
echo "[smoke] examples=$EX out=$OUT"
python eval_hle_local_p3_yunuikang.py \
  --model_name orchestrator \
  --output_dir "$OUT" \
  --model_config "$EVAL/model_configs/hle_local_router_p3.json" \
  --max_rounds 30 \
  --model_type "Qwen/Qwen3-8B" \
  --example_path "$EX" \
  --concurrency 1 \
  --log_level INFO
echo "[smoke] done. outputs:"; ls "$OUT"
