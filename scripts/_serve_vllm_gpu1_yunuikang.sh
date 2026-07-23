#!/usr/bin/env bash
# Deployment A' (P2/Science): SINGLE-GPU Qwen3-32B on GPU1 (Pro6000 96GB).
# GPU2 is occupied by another user (suuinmoon/K-Search) -> TP2 unavailable; GPU0 untouched.
# CUDA_DEVICE_ORDER pinned to PCI_BUS_ID so device "1" is unambiguously the 96GB card.
# Isolated copy — does NOT modify _serve_vllm_tp2_yunuikang.sh.
set -uo pipefail
MODEL="${MODEL:-Qwen/Qwen3-32B}"
GPUS="${GPUS:-1}"
TP="${TP:-1}"
PORT="${PORT:-8000}"
MML="${MML:-32768}"
GMU="${GMU:-0.92}"
source /home/yunuikang/yunuikang_work/.venv/bin/activate
HDR=/home/yunuikang/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/include/python3.12
export CPATH="$HDR" C_INCLUDE_PATH="$HDR"
export VLLM_USE_FLASHINFER_SAMPLER=0
export CUDA_DEVICE_ORDER=PCI_BUS_ID
LOG="${LOG:-/home/yunuikang/yunuikang_work/scratch/sab/vllm_serve_gpu1_${PORT}.log}"
mkdir -p "$(dirname "$LOG")"
echo "[serve-gpu1] MODEL=$MODEL GPUS=$GPUS TP=$TP PORT=$PORT MML=$MML GMU=$GMU log=$LOG"
CUDA_VISIBLE_DEVICES="$GPUS" vllm serve "$MODEL" \
  --tensor-parallel-size "$TP" --host 0.0.0.0 --port "$PORT" \
  --max-model-len "$MML" --gpu-memory-utilization "$GMU" 2>&1 | tee "$LOG"
