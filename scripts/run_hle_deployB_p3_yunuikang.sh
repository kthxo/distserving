#!/usr/bin/env bash
# P3 Deployment B (venv-adapted, isolated): FAISS retriever (GPU2) + Nemotron-8B
# orchestrator vLLM (GPU1) + ThunderAgent proxy. GPU0 untouched. Keys from .hle_env only.
# Usage: run_hle_deployB_p3_yunuikang.sh <router: default|tr>
set -uo pipefail
ROUTER="${1:-default}"
set -a; source /home/yunuikang/yunuikang_work/.hle_env 2>/dev/null; set +a
source /home/yunuikang/yunuikang_work/.venv/bin/activate
HDR=/home/yunuikang/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/include/python3.12
export CPATH="$HDR" C_INCLUDE_PATH="$HDR" VLLM_USE_FLASHINFER_SAMPLER=0
export GLM_BASE_URL="https://api.z.ai/api/paas/v4"   # correct path (override wrong .hle_env if any)
export HLE_ENABLE_JUDGE=0 TAVILY_KEY=""

REPO=/home/yunuikang/yunuikang_work/distserving
EVAL=$REPO/examples/inference/ToolOrchestra/evaluation
ASSETS=/home/yunuikang/yunuikang_work/scratch/p3_assets
LOG=/home/yunuikang/yunuikang_work/scratch/p3
mkdir -p "$LOG" "$EVAL/cache/hle"
ORCH=$ASSETS/orchestrator
RETPORT=1401 BACKPORT=8100 PROXYPORT=9000
MODELNAME="orchestrator"

# --- 1) retriever on GPU2 (embedder + FAISS eval index) ---
echo "[B] starting retriever GPU2 (embedder+faiss)..."
INDEX_DIR="$ASSETS/faiss_index" CUDA_VISIBLE_DEVICES=2 \
  nohup python "$EVAL/retrieval_hle_p3_yunuikang.py" --port $RETPORT \
    --new_cache_dir "$EVAL/cache/hle" --example_id_file "$EVAL/examples.json" \
    > "$LOG/retriever.log" 2>&1 &
echo $! > "$LOG/retriever.pid"

# --- 2) orchestrator vLLM on GPU1 (Nemotron-8B) ---
echo "[B] starting orchestrator vLLM GPU1 (Nemotron-8B)..."
CUDA_VISIBLE_DEVICES=1 nohup vllm serve "$ORCH" --port $BACKPORT \
  --served-model-name "$MODELNAME" --max-model-len 32768 --gpu-memory-utilization 0.55 \
  --enable-prefix-caching --enable-prompt-tokens-details --enable-force-include-usage \
  --enable-auto-tool-choice --tool-call-parser hermes \
  > "$LOG/orchestrator.log" 2>&1 &
echo $! > "$LOG/orchestrator.pid"

echo "[B] waiting for orchestrator health (up to 20min)..."
for i in $(seq 1 240); do curl -sf "http://127.0.0.1:$BACKPORT/health" >/dev/null 2>&1 && { echo "orchestrator READY (~$((i*5))s)"; break; }; sleep 5; done
curl -sf "http://127.0.0.1:$BACKPORT/health" >/dev/null 2>&1 || { echo "ERROR: orchestrator not ready"; exit 1; }

# --- 3) ThunderAgent proxy (router in front of orchestrator), profiling for record ---
echo "[B] starting ThunderAgent proxy (:$PROXYPORT, router=$ROUTER)..."
pkill -9 -f "bin/thunderagent" 2>/dev/null; sleep 2
nohup thunderagent --backend-type vllm --backends "http://127.0.0.1:$BACKPORT" \
  --port $PROXYPORT --router "$ROUTER" --metrics --profile --profile-dir "$LOG/prof_hle" \
  > "$LOG/proxy.log" 2>&1 &
echo $! > "$LOG/proxy.pid"
for i in $(seq 1 30); do curl -sf "http://127.0.0.1:$PROXYPORT/health" >/dev/null 2>&1 && break; sleep 2; done
MODE=$(curl -s "http://127.0.0.1:$PROXYPORT/health" | python -c 'import sys,json;print(json.load(sys.stdin)["router_mode"])' 2>/dev/null)
echo "[B] proxy mode=$MODE (expect $ROUTER)"

# --- 4) generate model_config (orchestrator -> proxy, retrieval -> retriever) ---
MC="$EVAL/model_configs/hle_local_router_p3.json"
python - "$MC" "$MODELNAME" $PROXYPORT $RETPORT <<'PY'
import json,sys
mc,name,rp,retp=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4]
cfg={"retrieval":[{"ip_addr":"127.0.0.1","port":str(retp)}],
     name:[{"ip_addr":"127.0.0.1","port":str(rp)}],
     "vllm_model_config_path":mc}
json.dump(cfg,open(mc,"w"),indent=2)
print("model_config ->",mc)
PY
echo "[B] Deployment B UP: retriever:$RETPORT orchestrator:$BACKPORT proxy:$PROXYPORT model=$MODELNAME"
echo "MODEL_CONFIG=$MC"
