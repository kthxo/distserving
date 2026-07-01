# Setup Notes — ThunderAgent + vLLM (8B smoke test)

> Branch: `yunuikang/thunderagent`. Reproduction baseline for heterogeneous
> agent-serving. This documents how the ThunderAgent + vLLM path was brought up
> on our lab box (4× RTX 4090) and the non-obvious workarounds needed.

## Hardware / environment
- 4× NVIDIA RTX 4090 (24 GB each), driver 595.71.05 (CUDA 13-era).
- System Python 3.12.3, gcc 13.3, **no passwordless sudo**.
- System CUDA toolkit is 12.1 (`/usr/local/cuda` → nvcc 12.1); torch ships cu130.

## Software versions that worked
- vLLM 0.24.0, torch 2.11.0+cu130 (installed via `uv pip install vllm --torch-backend=auto`).
- ThunderAgent installed editable (`pip install -e .`), deps: fastapi/httpx/uvicorn.
- Isolated venv at `/home/yunuikang/yunuikang_work/.venv`.

## Three blockers hit during bring-up (and fixes)

### 1. `fatal error: Python.h: No such file or directory`
torch.compile/Triton JIT needs CPython dev headers, but `python3.12-dev` is not
installed and we have no sudo. Fix without sudo: install a uv-managed standalone
CPython 3.12 (bundles headers) and point the compiler at them via `CPATH`:
```bash
uv python install 3.12
HDR=/home/yunuikang/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/include/python3.12
export CPATH="$HDR" C_INCLUDE_PATH="$HDR"
```

### 2. KV cache doesn't fit at default context length
Qwen3-8B default max len 40960 needs ~5.6 GiB KV but only ~4.6 GiB free after
weights on a 24 GB card. Fix: cap context length.
```bash
--max-model-len 32768 --gpu-memory-utilization 0.92
```

### 3. flashinfer JIT fails: `unsupported GNU version! gcc versions later than 12 are not supported`
flashinfer JIT-compiles sampling kernels with the system nvcc 12.1, which rejects
gcc 13. (Also nvcc 12.1 mismatches torch's cu130.) Fix: bypass flashinfer and use
vLLM's precompiled FlashAttention + native torch sampler.
```bash
export VLLM_ATTENTION_BACKEND=FLASH_ATTN
export VLLM_USE_FLASHINFER_SAMPLER=0
```

## Working launch commands

Backend (vLLM), GPU 0:
```bash
source /home/yunuikang/yunuikang_work/.venv/bin/activate
HDR=/home/yunuikang/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/include/python3.12
export CPATH="$HDR" C_INCLUDE_PATH="$HDR"
export VLLM_ATTENTION_BACKEND=FLASH_ATTN VLLM_USE_FLASHINFER_SAMPLER=0
CUDA_VISIBLE_DEVICES=0 vllm serve Qwen/Qwen3-8B \
  --port 8000 --gpu-memory-utilization 0.92 --max-model-len 32768
```

ThunderAgent proxy (program-aware `tr` router) on port 9000:
```bash
thunderagent --backend-type vllm --backends http://localhost:8000 \
  --port 9000 --router tr --metrics --profile
```

Send agent requests to **port 9000** with a `program_id` in `extra_body`.

## Smoke test
`scripts/smoke_test_yunuikang.py` exercises the full path: single completion,
multi-turn reuse of one `program_id` (KV-locality path), and
`POST /programs/release`. Run it after both services are up:
```bash
python scripts/smoke_test_yunuikang.py \
  --base-url http://localhost:9000/v1 --router-url http://localhost:9000 \
  --model Qwen/Qwen3-8B
# -> prints "SMOKE TEST OK"
```

## Notes / next steps
- `GET /v1/models` through the proxy returns 404 (it forwards to backend
  `/models`); this is cosmetic. Core `POST /v1/chat/completions` works.
- Only GPU 0 is used; GPUs 1–3 are free for multi-instance homogeneous
  reproduction (run more `vllm serve` on other GPUs and pass all backends to
  `thunderagent --backends url1,url2,...`).
- Packaged examples (ToolOrchestra/OpenHands/mini-swe-agent) need paid API keys
  or Docker + large model/data downloads; deferred until keys are available.
