#!/usr/bin/env bash
# SGLang Qwen2.5-7B-Instruct **TP1 on a SINGLE RTX PRO 6000 Blackwell Max-Q** (nutella1).
#
# PLAN: plans/2026-08-15_PLAN_rawlog-steadystate-mori-tp1_yunuikang.md §2 / §4
#
# 이 파일이 왜 새로 필요한가
#   `_serve_sglang_7b_tp1_5090_mori_yunuikang.sh` 는 goguma6 전용이다:
#     * VENV=/home/.../.venv-sglang 가 nutella1 엔 없었다(이 배치에서 새로 만듦)
#     * gcc-11/g++-11 을 핀하는데 nutella1 엔 gcc-13 만 있다
#     * MAXTOK 를 required 로 강제한다 — 이번 배치는 **자연 KV 풀(캡 없음)** 이 요구조건
#   원본 무수정 원칙에 따라 그 파일은 손대지 않고 이 파일을 새로 만든다.
#
# ★ 5090 스크립트와의 의도적 차이 (전부 run_meta 에 diff 로 기록된다)
#   1. MAXTOK 가 **선택**이다. 미설정 = `--max-total-tokens` 를 아예 넘기지 않음
#      = SGLang 프로파일 자연값 그대로. 이번 배치의 핵심 조건(PLAN §4 "cap 안 함").
#   2. GPUS 기본 **2**. nutella1 의 GPU0(PRO 5000)·GPU1(PRO 6000)은 타 사용자(muchwater)가
#      점유 중이라 미접촉. GPU2 만 쓴다.
#   3. CC/CXX = gcc-13 (이 박스에 gcc-11 없음). CUDA_HOME=/usr/local/cuda-13.0.
#   4. MAXRUN(--max-running-requests) 상향. C=4fit(~170 세션)이 스케줄러 in-flight 상한에
#      걸리지 않게. **캡이 아니라 동시 in-flight 상한**이라 KV 풀은 건드리지 않는다.
#   5. NUMA: GPU2 는 node1(CPU affinity 8-15). HiCache host tier 를 node1 에 preferred 로
#      붙여 cross-NUMA 전송을 피한다. numactl 이 없으면 사유를 로그에 남기고 그냥 진행.
#      ※ --membind 는 쓰지 않는다: host tier 141 GiB > node1 용량 126 GiB 라 강제 바인딩이면
#        할당이 실패한다. --preferred 는 node1 을 우선하되 node0 spill 을 허용한다.
#   6. --enable-cache-report: 이게 없으면 응답 usage 의 `prompt_tokens_details.cached_tokens`
#      가 **항상 null** 이다 (sglang usage_processor.calculate_streaming_usage 의
#      enable_cache_report 게이트).  SCHEMA §4 의 `cached_tokens`(= 엔진 replay 시점
#      prefix-hit) 와 §0-5 의 recompute offline 재구성이 이 필드에 의존하므로 필수다.
#      1차 스모크에서 1,556/1,556 전부 null 로 나와 발견 -> 추가.
#
# Env (전부 오버라이드 가능):
#   MODEL   Qwen/Qwen2.5-7B-Instruct   GPUS 2     TP 1     PORT 8123
#   MML     71680 (--context-length)   MEMFRAC 0.90
#   MAXTOK  (선택) 미설정이면 자연 풀. 설정하면 캡이 문다.
#   RATIO   2 (>0 => --enable-hierarchical-cache --hicache-ratio RATIO = r)
#   EVICT   mori | priority | lru
#   MAXRUN  1024 (--max-running-requests)
#   NUMANODE 1  (빈 문자열이면 numactl 미사용)
set -uo pipefail
REPO=/home/yunuikang/yunuikang_work/distserving
VENV=/home/yunuikang/yunuikang_work/.venv-sglang
MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}"
GPUS="${GPUS:-2}"; TP="${TP:-1}"; PORT="${PORT:-8123}"
MML="${MML:-71680}"                  # YaRN 2.1875 x 32768. 5090/H200 7B run 과 동일 값.
MEMFRAC="${MEMFRAC:-0.90}"
MAXTOK="${MAXTOK:-}"                 # 비어 있으면 자연 풀 (캡 없음) — 이번 배치 기본
RATIO="${RATIO:-2}"
EVICT="${EVICT:-mori}"
MAXRUN="${MAXRUN:-1024}"
NUMANODE="${NUMANODE:-1}"
LOG="${LOG:-/home/yunuikang/yunuikang_work/scratch/mori/rawlog_pro6000/serve_${EVICT}_r${RATIO}_$(date +%H%M%S).log}"
mkdir -p "$(dirname "$LOG")"

source "$VENV/bin/activate"
# nutella1 SGLang JIT 툴체인. gcc-11 이 없어 gcc-13 을 쓴다 — 이것이 goguma6 와의 diff.
export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda-13.0}"
export PATH="$CUDA_HOME/bin:$PATH"
export CC="${CC:-/usr/bin/gcc-13}" CXX="${CXX:-/usr/bin/g++-13}"
export NVCC_PREPEND_FLAGS="${NVCC_PREPEND_FLAGS:--ccbin /usr/bin/g++-13}"
export MAX_JOBS="${MAX_JOBS:-8}"     # 타 사용자와 CPU 공유 중이라 16 -> 8

# YaRN. Qwen2.5-7B config.json 은 max_position_embeddings=32768, rope_scaling 없음.
export SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=1
YARN_KEY="${YARN_KEY:-rope_parameters}"
YARN="{\"${YARN_KEY}\":{\"rope_type\":\"yarn\",\"factor\":2.1875,\"original_max_position_embeddings\":32768,\"rope_theta\":1000000}}"

HICACHE=()
if [ "${RATIO%.*}" != "0" ] && [ "$RATIO" != "0" ]; then
  HICACHE=(--enable-hierarchical-cache --hicache-ratio "$RATIO")
fi

# 자연 풀이 기본. MAXTOK 를 준 경우에만 캡 플래그가 붙는다.
CAP=()
if [ -n "$MAXTOK" ]; then
  CAP=(--max-total-tokens "$MAXTOK")
fi

# MORI typed-eviction / raw 로거는 SGLang 이 spawn 하는 스케줄러 서브프로세스까지 닿아야
# 하므로 PYTHONPATH 의 sitecustomize 경유로만 걸린다 (부모만 패치하면 안 걸린다).
# ★ 순서가 중요하다. Python 은 sys.path 에서 **처음 찾은** sitecustomize 하나만 import 한다.
#   raw 로거 훅(rawlog_hook_yunuikang/sitecustomize.py)이 원본보다 앞서야 로드되고,
#   그 훅이 원본 sitecustomize 를 경로로 직접 실행해 기존 동작을 그대로 이어받는다.
#   (앞뒤가 바뀌면 원본만 걸리고 kv_events 가 한 줄도 안 나온다 — 스모크에서 실측된 버그)
export PYTHONPATH="$REPO/scripts/rawlog_hook_yunuikang:$REPO/scripts:${PYTHONPATH:-}"
export SGLANG_MORI_PATCH=1
# MORI_RAWLOG / MORI_RAWLOG_DIR / MORI_TIERC* 는 러너가 주입한다 (미설정이면 계측 OFF).

# NUMA: GPU2 는 node1. HiCache host tier 할당을 node1 로 preferred.
NUMA=()
if [ -n "$NUMANODE" ]; then
  if command -v numactl >/dev/null 2>&1; then
    NUMA=(numactl "--preferred=$NUMANODE" "--cpunodebind=$NUMANODE")
  else
    echo "[serve-pro6000-tp1-7b] WARN: numactl 없음 -> NUMA 핀 생략 (host tier 가 node0/1 에 걸쳐 할당될 수 있음)"
  fi
fi

echo "[serve-pro6000-tp1-7b] MODEL=$MODEL GPUS=$GPUS TP=$TP PORT=$PORT MML=$MML MEMFRAC=$MEMFRAC RATIO=$RATIO EVICT=$EVICT MAXRUN=$MAXRUN MAXTOK=${MAXTOK:-<natural>} NUMA=${NUMANODE:-off} log=$LOG"
CUDA_VISIBLE_DEVICES="$GPUS" "${NUMA[@]}" python -m sglang.launch_server \
  --model-path "$MODEL" --tp "$TP" --host 0.0.0.0 --port "$PORT" \
  --context-length "$MML" --mem-fraction-static "$MEMFRAC" \
  --max-running-requests "$MAXRUN" \
  --json-model-override-args "$YARN" --enable-metrics --enable-cache-report \
  --attention-backend triton --sampling-backend pytorch \
  --radix-eviction-policy "$EVICT" \
  "${CAP[@]}" "${HICACHE[@]}" 2>&1 | tee "$LOG"

# 검증: grep "max_total_num_tokens" "$LOG"       -> C_gpu (자연 풀)
#       grep -i "larger than the profiled"        -> 아무것도 안 나와야 함
