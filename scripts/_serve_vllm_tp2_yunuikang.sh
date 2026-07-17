#!/usr/bin/env bash
# Deployment A (nutella1): TP2 Qwen3-32B on GPU1+GPU2. Non-eager (exercises the
# torch.compile / CUDA-graph path so we surface any Python.h/compile issue).
# Isolated copy — does NOT touch _serve_vllm_yunuikang.sh (Phase D 8B single-GPU).
# Env overridable: MODEL, GPUS, TP, PORT, MML, GMU, LOG.
set -uo pipefail
MODEL="${MODEL:-Qwen/Qwen3-32B}"
GPUS="${GPUS:-1,2}"
TP="${TP:-2}"
PORT="${PORT:-8000}"
MML="${MML:-32768}"
GMU="${GMU:-0.92}"
source /home/yunuikang/yunuikang_work/.venv/bin/activate
HDR=/home/yunuikang/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/include/python3.12
export CPATH="$HDR" C_INCLUDE_PATH="$HDR"
export VLLM_USE_FLASHINFER_SAMPLER=0
LOG="${LOG:-/home/yunuikang/yunuikang_work/scratch/tp2/vllm_serve_${PORT}.log}"
mkdir -p "$(dirname "$LOG")"
echo "[serve-tp2] MODEL=$MODEL GPUS=$GPUS TP=$TP PORT=$PORT MML=$MML GMU=$GMU log=$LOG"
CUDA_VISIBLE_DEVICES="$GPUS" vllm serve "$MODEL" \
  --tensor-parallel-size "$TP" --host 0.0.0.0 --port "$PORT" \
  --max-model-len "$MML" --gpu-memory-utilization "$GMU" 2>&1 | tee "$LOG"
