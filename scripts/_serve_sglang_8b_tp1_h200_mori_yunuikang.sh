#!/usr/bin/env bash
# SGLang Qwen3-8B TP1 serve on H200 — Phase 1 rev4 (모델 교란 제거).
#
# 계획: plans/2026-08-04_PLAN_h200-rescale-reproduction_yunuikang.md rev4 §5.1
# 사전 등록: logs/2026-08-05_H200_GATE_PREREG_yunuikang.md §11
#
# WHY A SEPARATE FILE. 7B 스크립트(_serve_sglang_7b_tp1_h200_mori_yunuikang.sh)를
# env 로 일반화하지 않고 새 파일로 둔다 — 그 파일은 **이미 기록된 7B F1 2셀이 사용한
# 것**이라, 나중에 손대면 "그때 무엇이 돌았는가"가 흐려진다. 중복을 감수하고 기록을 지킨다.
# goguma6 의 _serve_sglang_8b_tp2_mori_yunuikang.sh 도 물론 무수정(계획 제약).
#
# 5090 F1 과 맞춘 것 [측정, config.json]:
#   모델 Qwen3-8B · 36L·8kv·128hd -> KV/tok 144 KiB (5090과 동일)
#   YaRN factor 1.75 x max_position_embeddings 40,960 = 71,680 = --context-length
#   MAXTOK 262,246 tok = 36.0 GiB  (5090 은 262,144 tok = 36.0 GiB; 0.04% 차)
# 5090 과 다른 것 (의도적으로 남긴 유일한 차이):
#   H200 x1 · TP1 · all-reduce 없음 · node-local  <- 이것이 §5.1 이 재려는 것
#
# 사이징 [추정, gate 가 셀마다 실측 확인]:
#   weights 15.26 GiB · gmu 0.90 -> KV 예산 111.10 GiB -> 자연 풀 809,006 tok (fit 25.0)
#   목표 262,246 tok 은 자연 풀의 32% -> 캡이 여유 있게 문다
#
# Env: MODEL GPUS TP PORT MML MAXTOK(필수) MEMFRAC RATIO EVICT NUMA_NODE LOG YARN_KEY
set -uo pipefail
REPO=/workspace/distserving
VENV=/venv/main
MODEL="${MODEL:-Qwen/Qwen3-8B}"
GPUS="${GPUS:-0}"; TP="${TP:-1}"; PORT="${PORT:-8123}"
MML="${MML:-71680}"
MAXTOK="${MAXTOK:?MAXTOK (--max-total-tokens) is required}"
MEMFRAC="${MEMFRAC:-0.90}"
RATIO="${RATIO:-0}"
EVICT="${EVICT:-lru}"
NUMA_NODE="${NUMA_NODE:-0}"
LOG="${LOG:-$REPO/scratch/mori/h200_phase1_8b/serve_${EVICT}_r${RATIO}_t${MAXTOK}.log}"
mkdir -p "$(dirname "$LOG")"

source "$VENV/bin/activate"

# YaRN: Qwen3-8B 도 config 에 rope_scaling / rope_parameters 가 없다 -> override 주입.
# factor 1.75 는 5090 스크립트와 **동일한 값**이다(맞춰야 하는 항목).
export SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=1
YARN_KEY="${YARN_KEY:-rope_parameters}"   # transformers 5.3.0
YARN="{\"${YARN_KEY}\":{\"rope_type\":\"yarn\",\"factor\":1.75,\"original_max_position_embeddings\":40960,\"rope_theta\":1000000}}"

HICACHE=()
if [ "${RATIO%.*}" != "0" ] && [ "$RATIO" != "0" ]; then
  HICACHE=(--enable-hierarchical-cache --hicache-ratio "$RATIO")
fi

export PYTHONPATH="$REPO/scripts:${PYTHONPATH:-}"
export SGLANG_MORI_PATCH=1

# --membind 는 이 컨테이너에서 EPERM (PREREG §9.1) -> --cpunodebind 단독.
NUMA=()
if command -v numactl >/dev/null 2>&1 && numactl --cpunodebind="$NUMA_NODE" true 2>/dev/null; then
  NUMA=(numactl --cpunodebind="$NUMA_NODE")
fi

echo "[serve-h200-8b] MODEL=$MODEL TP=$TP PORT=$PORT MML=$MML MAXTOK=$MAXTOK (fit=$(python3 -c "print(f'{$MAXTOK/32376:.2f}')")) MEMFRAC=$MEMFRAC RATIO=$RATIO EVICT=$EVICT log=$LOG"
CUDA_VISIBLE_DEVICES="$GPUS" "${NUMA[@]}" python -m sglang.launch_server \
  --model-path "$MODEL" --tp "$TP" --host 0.0.0.0 --port "$PORT" \
  --context-length "$MML" --max-total-tokens "$MAXTOK" --mem-fraction-static "$MEMFRAC" \
  --json-model-override-args "$YARN" --enable-metrics \
  --attention-backend triton --sampling-backend pytorch \
  --radix-eviction-policy "$EVICT" \
  "${HICACHE[@]}" 2>&1 | tee "$LOG"
