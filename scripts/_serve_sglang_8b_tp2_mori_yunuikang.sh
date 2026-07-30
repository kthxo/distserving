#!/usr/bin/env bash
# SGLang Qwen3-8B TP2 serve for the MORI experiments on goguma6 (RTX 5090 x2, sm_120).
# Real HiCache (offloading) + optional MORI typed eviction. One script, env-driven,
# for all 4 systems (SMG/TA/TA+O/MORI) — the caller sets RATIO/EVICT per system.
#
# Env (all overridable):
#   MODEL   Qwen/Qwen3-8B        GPUS   0,1              TP     2
#   PORT    8100                 MML    65536 (=L, 64k)  MAXTOK 262144 (=36GiB C_gpu pin, STEP1-confirm)
#   MEMFRAC 0.85                 RATIO  0 (HiCache off; >0 => --hicache-ratio RATIO)
#   EVICT   lru (SMG/TA/TA+O)    | priority | mori (MORI full typed eviction)
#
# NOTE: uses the Python RadixCache/HiRadixCache path (NOT --*-cpp-radix; the C++
# tree ignores the Python eviction strategy). Toolchain env is REQUIRED on goguma6
# (see memory goguma6-sglang-toolchain): CUDA_HOME + gcc-11, else JIT fails.
set -uo pipefail
REPO=/home/yunuikang/yunuikang_work/distserving
VENV=/home/yunuikang/yunuikang_work/.venv-sglang
MODEL="${MODEL:-Qwen/Qwen3-8B}"
GPUS="${GPUS:-0,1}"; TP="${TP:-2}"; PORT="${PORT:-8100}"
MML="${MML:-65536}"                  # --context-length = L (64k)
MAXTOK="${MAXTOK:-262144}"           # --max-total-tokens = C_gpu pin (36 GiB); STEP1 confirms <= native
MEMFRAC="${MEMFRAC:-0.85}"
RATIO="${RATIO:-0}"                  # host:device HiCache ratio; 0 => HiCache OFF
EVICT="${EVICT:-lru}"               # lru | priority | mori
LOG="${LOG:-/home/yunuikang/yunuikang_work/scratch/step_ec/sglang_serve_mori_${PORT}.log}"
mkdir -p "$(dirname "$LOG")"

source "$VENV/bin/activate"
# --- toolchain env (goguma6): CUDA_HOME + gcc-11 or the JIT nvcc build fails ---
export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda-13.0}"
export PATH="$CUDA_HOME/bin:$PATH"
export CC="${CC:-/usr/bin/gcc-11}" CXX="${CXX:-/usr/bin/g++-11}"
export NVCC_PREPEND_FLAGS="${NVCC_PREPEND_FLAGS:--ccbin /usr/bin/g++-11}"
export MAX_JOBS="${MAX_JOBS:-16}"

HICACHE=()
if [ "${RATIO%.*}" != "0" ] && [ "$RATIO" != "0" ]; then
  HICACHE=(--enable-hierarchical-cache --hicache-ratio "$RATIO")
fi

echo "[serve-sglang-mori] MODEL=$MODEL GPUS=$GPUS TP=$TP PORT=$PORT MML=$MML MAXTOK=$MAXTOK MEMFRAC=$MEMFRAC RATIO=$RATIO EVICT=$EVICT log=$LOG"
CUDA_VISIBLE_DEVICES="$GPUS" python "$REPO/scripts/serve_sglang_mori_launch_yunuikang.py" \
  --model-path "$MODEL" --tp "$TP" --host 0.0.0.0 --port "$PORT" \
  --context-length "$MML" --max-total-tokens "$MAXTOK" --mem-fraction-static "$MEMFRAC" \
  --attention-backend triton --sampling-backend pytorch --disable-custom-all-reduce \
  --radix-eviction-policy "$EVICT" \
  "${HICACHE[@]}" 2>&1 | tee "$LOG"

# WHEN IT WORKS: grep "max_total_num_tokens" "$LOG"   # native pool (STEP1: pin MAXTOK <= this)
#                grep -iE "hierarchical|host memory" "$LOG"   # HiCache host pool allocated
