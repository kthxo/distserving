#!/usr/bin/env bash
# ============================================================================
# goguma6 (RTX 5090 / Blackwell) — vLLM backend setup + serve, from scratch.
# /home is NOT shared with mango1, so this builds a fresh venv + installs vLLM
# + downloads the model on goguma6 itself. Run this ON goguma6 (copy-paste).
#
# Mirrors the mango1 working stack (SETUP_NOTES): vLLM + torch, Python.h header
# workaround (CPATH), FLASH_ATTN attention, flashinfer sampler disabled.
#
# Blackwell caveat: vLLM/torch must ship sm_120 kernels. If serve fails, DO NOT
# grind — copy the error lines (see "IF IT FAILS" at the bottom) and report back.
#
# Usage:  bash setup_goguma6_yunuikang.sh          # setup + serve on GPU0:8000
# Env:    WORK (base dir, default $HOME/ta_goguma6), GPU (default 0), PORT (8000)
#         SKIP_SETUP=1  -> skip install steps, just (re)serve
# ============================================================================
set -uo pipefail
WORK="${WORK:-$HOME/ta_goguma6}"
GPU="${GPU:-0}"; PORT="${PORT:-8000}"
VENV="$WORK/.venv"
LOG="$WORK/vllm_goguma6_${PORT}.log"
mkdir -p "$WORK"; cd "$WORK"

echo "==[0] node/GPU check ============================================"
nvidia-smi | sed -n '3p' || true            # driver + CUDA version (need Blackwell-capable: CUDA 13.x)
nvidia-smi --query-gpu=index,name --format=csv,noheader || true
echo "WORK=$WORK GPU=$GPU PORT=$PORT"

if [ "${SKIP_SETUP:-0}" != "1" ]; then
  echo "==[1] uv (installer for standalone python + fast pip) ==========="
  if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
  export PATH="$HOME/.local/bin:$PATH"
  uv --version

  echo "==[2] standalone Python 3.12 (ships Python.h headers) + venv ===="
  uv python install 3.12
  [ -d "$VENV" ] || uv venv --python 3.12 "$VENV"
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"

  echo "==[3] install vLLM (auto CUDA backend; Blackwell expects cu13) ==="
  # --torch-backend=auto detects the driver's CUDA and picks the matching torch.
  uv pip install vllm --torch-backend=auto
else
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
fi

echo "==[4] versions ================================================="
python -c "import torch,vllm; print('torch',torch.__version__,'| vllm',vllm.__version__)" || {
  echo '!! torch/vllm import failed — report this. (Blackwell may need a newer vLLM/torch.)'; exit 1; }
python -c "import torch; print('cuda_avail',torch.cuda.is_available(),'| dev0', (torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE'))"

echo "==[5] env workarounds (Python.h header + flashinfer/nvcc bypass) ="
HDR="$(python -c 'import sysconfig; print(sysconfig.get_path("include"))')"
export CPATH="$HDR" C_INCLUDE_PATH="$HDR"
export VLLM_ATTENTION_BACKEND=FLASH_ATTN
export VLLM_USE_FLASHINFER_SAMPLER=0
echo "CPATH=$CPATH"

echo "==[6] serve (first run downloads Qwen/Qwen3-8B ~16GB) ==========="
echo "log -> $LOG"
CUDA_VISIBLE_DEVICES="$GPU" vllm serve Qwen/Qwen3-8B \
  --host 0.0.0.0 --port "$PORT" \
  --max-model-len 32768 --gpu-memory-utilization 0.92 \
  2>&1 | tee "$LOG"

# ---------------------------------------------------------------------------
# IF IT FAILS: send me these ->
#   grep -iE "error|not supported|sm_|no kernel|CUDA|flashinfer|assert|Traceback" "$LOG" | tail -40
#   nvidia-smi | sed -n '3p'
# WHEN IT WORKS: send me ->
#   grep "GPU KV cache size" "$LOG" | tail -1      # 5090 KV pool size
#   curl -sf http://localhost:8000/health && echo HEALTH_OK
# ---------------------------------------------------------------------------
