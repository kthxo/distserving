#!/usr/bin/env bash
# SGLang Qwen2.5-7B-Instruct **TP1 on a SINGLE RTX 5090** (goguma6).
#
# 왜 이 파일이 새로 필요한가 — 미해결 #1 을 가르기 위해서다.
#   원래 5090 붕괴(MORI÷TA+O = 0.45x)의 조건은 [TP2 + Qwen3-8B + NVLink 없음 + cross-NUMA]
#   가 한 덩어리였다. H200 실험이 그중 **모델/KV밀도**를 배제했고(8B 로 맞춰도 재현 안 됨),
#   남은 것은 [GPU 세대·대역폭] + [TP2 / interconnect] 두 덩어리다.
#   이 스크립트는 **단일 5090 + 7B** 로 TP2·interconnect 를 제거해 GPU 세대만 남긴다.
#     C70(oversub~10)에서 MORI < TA+O 재현  → 원인은 **GPU 세대**
#     재현 안 됨                             → 원인은 **TP2 · interconnect**
#
# 기존 파일 무수정 원칙:
#   `_serve_sglang_8b_tp2_mori_yunuikang.sh` (5090 TP2 · 8B · YaRN 1.75) 와
#   `_serve_sglang_7b_tp1_h200_mori_yunuikang.sh` (H200 · /workspace 경로) 둘 다 손대지 않는다.
#   전자는 TP2/8B 가 하드코딩돼 있고, 후자는 H200 박스의 경로(/workspace, /venv/main)를 쓴다.
#
# Env (전부 오버라이드 가능):
#   MODEL   Qwen/Qwen2.5-7B-Instruct   GPUS 0     TP 1     PORT 8123
#   MML     71680 (--context-length)   MEMFRAC 0.90
#   MAXTOK  REQUIRED — fit = MAXTOK / 32376.  fit 7 => 226632
#   RATIO   0 (HiCache off; >0 => --enable-hierarchical-cache --hicache-ratio RATIO = r)
#   EVICT   lru (TA/TA+O) | priority | mori (MORI typed eviction)
#
# 이 박스에서 확인된 것 [측정 2026-08-08]:
#   * 5090 1장 = 32,607 MiB (31.85 GiB). 7B weights 14.19 GiB.
#     gmu 0.90 => weights+KV 28.67 GiB => KV 예산 14.48 GiB => 자연 pool 271,038 tok (fit 8.37).
#     따라서 MAXTOK 226,632 (12.10 GiB, fit 7.00) 은 자연 pool **아래**라 캡이 실제로 문다.
#   * triton attention — 5090 TP2 run 과 **동일**하게 유지한다. backend 가 바뀌면
#     "GPU 세대 vs interconnect" 판별에 새 교란이 들어간다.
#   * --disable-custom-all-reduce 는 **넣지 않는다**. TP1 이라 all-reduce 자체가 없다.
#     (그 플래그는 TP2 에서 5090 sm_120 커스텀 all-reduce 를 우회하려던 것이다.)
#   * CUDA_HOME / gcc-11 은 이 박스의 SGLang JIT 요구사항이다 — 빼면 커널 컴파일이 깨진다.
set -uo pipefail
REPO=/home/yunuikang/yunuikang_work/distserving
VENV=/home/yunuikang/yunuikang_work/.venv-sglang
MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}"
GPUS="${GPUS:-0}"; TP="${TP:-1}"; PORT="${PORT:-8123}"
MML="${MML:-71680}"                  # Track M p999 input+output 67,928 을 덮는다
MAXTOK="${MAXTOK:?MAXTOK (--max-total-tokens) is required — fit = MAXTOK/32376}"
MEMFRAC="${MEMFRAC:-0.90}"
RATIO="${RATIO:-0}"
EVICT="${EVICT:-lru}"
LOG="${LOG:-/home/yunuikang/yunuikang_work/scratch/mori/tierc_5090tp1/serve_${EVICT}_r${RATIO}_t${MAXTOK}.log}"
mkdir -p "$(dirname "$LOG")"

source "$VENV/bin/activate"
# goguma6 SGLang JIT 툴체인 (sm_120 커널 컴파일에 필요)
export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda-13.0}"
export PATH="$CUDA_HOME/bin:$PATH"
export CC="${CC:-/usr/bin/gcc-11}" CXX="${CXX:-/usr/bin/g++-11}"
export NVCC_PREPEND_FLAGS="${NVCC_PREPEND_FLAGS:--ccbin /usr/bin/g++-11}"
export MAX_JOBS="${MAX_JOBS:-16}"

# YaRN. Qwen2.5-7B config.json 은 max_position_embeddings=32768 이고 rope_scaling 이 없다.
# 2.1875 x 32768 = 71680 = MML. H200 7B run 과 **같은 값**이어야 대조가 성립한다.
export SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=1
YARN_KEY="${YARN_KEY:-rope_parameters}"
YARN="{\"${YARN_KEY}\":{\"rope_type\":\"yarn\",\"factor\":2.1875,\"original_max_position_embeddings\":32768,\"rope_theta\":1000000}}"

HICACHE=()
if [ "${RATIO%.*}" != "0" ] && [ "$RATIO" != "0" ]; then
  HICACHE=(--enable-hierarchical-cache --hicache-ratio "$RATIO")
fi

# MORI typed-eviction 및 Tier C 계측은 SGLang 이 spawn 하는 스케줄러 서브프로세스까지
# 닿아야 하므로 PYTHONPATH 의 sitecustomize 경유로만 걸린다 (부모만 패치하면 안 걸린다).
export PYTHONPATH="$REPO/scripts:${PYTHONPATH:-}"
export SGLANG_MORI_PATCH=1
# MORI_TIERC / MORI_TIERC_TAG / MORI_TIERC_OUT 은 러너가 주입한다 (미설정이면 계측 OFF).

echo "[serve-5090-tp1-7b] MODEL=$MODEL GPUS=$GPUS TP=$TP PORT=$PORT MML=$MML MAXTOK=$MAXTOK (fit=$(python3 -c "print(f'{$MAXTOK/32376:.2f}')")) MEMFRAC=$MEMFRAC RATIO=$RATIO EVICT=$EVICT log=$LOG"
CUDA_VISIBLE_DEVICES="$GPUS" python -m sglang.launch_server \
  --model-path "$MODEL" --tp "$TP" --host 0.0.0.0 --port "$PORT" \
  --context-length "$MML" --max-total-tokens "$MAXTOK" --mem-fraction-static "$MEMFRAC" \
  --json-model-override-args "$YARN" --enable-metrics \
  --attention-backend triton --sampling-backend pytorch \
  --radix-eviction-policy "$EVICT" \
  "${HICACHE[@]}" 2>&1 | tee "$LOG"

# 검증: grep "max_total_num_tokens" "$LOG"        (MAXTOK 와 일치해야 함)
#       grep -i "larger than the profiled value"  (아무것도 안 나와야 함 = 캡이 실제로 뭄)
