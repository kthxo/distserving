#!/usr/bin/env bash
# Launch one vLLM backend with the required env workarounds (SETUP_NOTES).
# Usage: _serve_vllm_yunuikang.sh <GPU_INDEX> <PORT>
set -uo pipefail
GPU="${1:?gpu index}"; PORT="${2:?port}"
source /home/yunuikang/yunuikang_work/.venv/bin/activate
HDR=/home/yunuikang/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/include/python3.12
export CPATH="$HDR" C_INCLUDE_PATH="$HDR"
export VLLM_ATTENTION_BACKEND=FLASH_ATTN
export VLLM_USE_FLASHINFER_SAMPLER=0
LOG=/home/yunuikang/yunuikang_work/scratch/vllm_phaseD_${PORT}.log
echo "[serve] GPU=$GPU PORT=$PORT log=$LOG"
CUDA_VISIBLE_DEVICES="$GPU" exec vllm serve Qwen/Qwen3-8B \
  --host 0.0.0.0 --port "$PORT" --max-model-len 32768 --gpu-memory-utilization 0.92 2>&1 | tee "$LOG"
