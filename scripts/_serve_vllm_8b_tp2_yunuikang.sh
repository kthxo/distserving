#!/usr/bin/env bash
# STEP 1 of PLAN 2026-07-23 (tracelab-earlycutoff-8b-2hw): Qwen3-8B FP16 (16-bit
# weights+KV, NOT FP8) on TP2. Isolated copy — does NOT touch
# _serve_vllm_tp2_yunuikang.sh (that one is 32B). Batch knob pinned to 2048/256
# to remove the 70GiB-boundary confounder (VLLM_PROFILING §1-5).
# Env overridable: MODEL, GPUS, TP, PORT, MML, GMU, MNBT, MNS, LOG.
set -uo pipefail
MODEL="${MODEL:-Qwen/Qwen3-8B}"
GPUS="${GPUS:-0,1}"
TP="${TP:-2}"
PORT="${PORT:-8100}"
MML="${MML:-131072}"          # 128k = early-cutoff limit (min(128k, 0.8*C_total))
GMU="${GMU:-0.92}"
MNBT="${MNBT:-2048}"          # pinned batch knobs
MNS="${MNS:-256}"
source /home/yunuikang/yunuikang_work/.venv/bin/activate
# CPATH header: match the venv python (goguma6 = cpython-3.12.11)
HDR="$(ls -d /home/yunuikang/.local/share/uv/python/cpython-3.12.*/include/python3.12 2>/dev/null | head -1)"
export CPATH="$HDR" C_INCLUDE_PATH="$HDR"
export VLLM_USE_FLASHINFER_SAMPLER=0
export VLLM_ATTENTION_BACKEND=FLASH_ATTN
LOG="${LOG:-/home/yunuikang/yunuikang_work/scratch/step_ec/vllm_serve_8b_tp2_${PORT}.log}"
mkdir -p "$(dirname "$LOG")"
echo "[serve-8b-tp2] MODEL=$MODEL GPUS=$GPUS TP=$TP PORT=$PORT MML=$MML GMU=$GMU MNBT=$MNBT MNS=$MNS log=$LOG"
CUDA_VISIBLE_DEVICES="$GPUS" vllm serve "$MODEL" \
  --tensor-parallel-size "$TP" --host 0.0.0.0 --port "$PORT" \
  --max-model-len "$MML" --gpu-memory-utilization "$GMU" \
  --max-num-batched-tokens "$MNBT" --max-num-seqs "$MNS" 2>&1 | tee "$LOG"
