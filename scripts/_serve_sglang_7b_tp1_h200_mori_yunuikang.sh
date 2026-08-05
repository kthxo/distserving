#!/usr/bin/env bash
# SGLang Qwen2.5-7B-Instruct TP1 serve on H200 SXM x1, for the H200 rescale plan
# (plans/2026-08-04_PLAN_h200-rescale-reproduction_yunuikang.md, rev3).
#
# NEW FILE. The goguma6 script `_serve_sglang_8b_tp2_mori_yunuikang.sh` is left
# untouched (plan constraint: existing scripts/traces/baselines are 0-line diff).
# It cannot be reused here anyway: it hardcodes /home/yunuikang paths, TP2,
# Qwen3-8B and YaRN factor 1.75.
#
# Env (all overridable):
#   MODEL   Qwen/Qwen2.5-7B-Instruct   GPUS 0        TP 1       PORT 8123
#   MML     71680  (--context-length)  MEMFRAC 0.90
#   MAXTOK  REQUIRED — the fit-sweep variable. fit = MAXTOK / 32376.
#           F1 262246 (fit 8.10) · F2 388512 (12) · F3 518016 (16) · F4 647520 (20)
#   RATIO   0 (HiCache off; >0 => --enable-hierarchical-cache --hicache-ratio RATIO = r)
#   EVICT   lru (SMG/TA/TA+O) | priority | mori (MORI full typed eviction)
#   NUMA_NODE 0  (GPU0 is on NUMA node 0 on this box: cpus 0-55,112-167, distance 10/21)
#
# WHY these flags [measured on this box, 2026-08-05]:
#   * TP1        — 7B weights 14.19 GiB fit on one H200 (143771 MiB = 140.40 GiB).
#                  No all-reduce at all, so --disable-custom-all-reduce is moot (plan §1.3).
#   * triton     — SAME attention backend as the goguma6 5090 runs. Keeping it makes
#                  F1 vs 5090 C80 differ by HARDWARE ONLY, which is the whole point of
#                  the F1 control cell (plan §6.2). Must stay identical across ALL H200 cells.
#   * YaRN 2.1875 — Qwen2.5-7B config.json has max_position_embeddings=32768 and NO
#                  rope_scaling / rope_parameters, so YaRN must be injected as an override.
#                  2.1875 x 32768 = 71680 = MML. transformers 5.3.0 uses the `rope_parameters`
#                  key (renamed from `rope_scaling` in v5) — override YARN_KEY to fall back.
#   * numactl    — GPU0 -> NUMA node 0. HiCache host pool must be allocated node-local,
#                  else host<->device reload pays the cross-NUMA penalty (distance 21).
#
# --max-total-tokens semantics [measured, sglang 0.5.10 source
#   model_executor/model_runner_kv_cache_mixin.py:808-838]:
#     capacity = min(profiled_tokens, max_total_tokens); then floored to a page_size
#     multiple. It is a CAP ONLY — it can never raise the pool. If the request exceeds
#     the profiled value sglang WARNS ("is larger than the profiled value") and silently
#     uses the profiled one; scripts/fit_gate_yunuikang.py treats that warning as FATAL.
set -uo pipefail
REPO=/workspace/distserving
VENV=/venv/main
MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}"
GPUS="${GPUS:-0}"; TP="${TP:-1}"; PORT="${PORT:-8123}"
MML="${MML:-71680}"                  # --context-length: covers Track M p999 input+output 67,935
MAXTOK="${MAXTOK:?MAXTOK (--max-total-tokens) is required — it IS the fit-sweep variable}"
MEMFRAC="${MEMFRAC:-0.90}"           # [추정] per plan §4; Phase 0 confirms via the gate
RATIO="${RATIO:-0}"                  # host:device HiCache ratio r; 0 => HiCache OFF
EVICT="${EVICT:-lru}"                # lru | priority | mori
NUMA_NODE="${NUMA_NODE:-0}"
LOG="${LOG:-$REPO/scratch/mori/h200_gate/serve_${EVICT}_r${RATIO}_t${MAXTOK}.log}"
mkdir -p "$(dirname "$LOG")"

source "$VENV/bin/activate"

# YaRN override. Qwen2.5-7B has neither rope_scaling nor rope_parameters in config.json.
export SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=1
YARN_KEY="${YARN_KEY:-rope_parameters}"   # transformers 5.3.0; fall back to rope_scaling if rejected
YARN="{\"${YARN_KEY}\":{\"rope_type\":\"yarn\",\"factor\":2.1875,\"original_max_position_embeddings\":32768,\"rope_theta\":1000000}}"

HICACHE=()
if [ "${RATIO%.*}" != "0" ] && [ "$RATIO" != "0" ]; then
  HICACHE=(--enable-hierarchical-cache --hicache-ratio "$RATIO")
fi

# MORI typed-eviction patch reaches SGLang's spawned scheduler subprocesses only via
# sitecustomize on PYTHONPATH (a parent-only monkey-patch does NOT). Same mechanism as
# the goguma6 script — scripts/sitecustomize.py and mori_hicache_yunuikang.py unmodified.
export PYTHONPATH="$REPO/scripts:${PYTHONPATH:-}"
export SGLANG_MORI_PATCH=1

# NUMA pinning: --cpunodebind ONLY. `--membind`/`--preferred` need set_mempolicy(2), which
# is EPERM in this unprivileged container [측정 2026-08-05: "set_mempolicy: Operation not
# permitted"; the engine died before loading weights]. Dropping it is not a compromise here:
# the default policy is `policy: default / preferred node: current` = first-touch local
# allocation, so with every thread bound to node 0 the HiCache host pool still lands on
# node 0. See the amendment record in logs/2026-08-05_H200_GATE_PREREG_yunuikang.md §9.
NUMA=()
if command -v numactl >/dev/null 2>&1 && numactl --cpunodebind="$NUMA_NODE" true 2>/dev/null; then
  NUMA=(numactl --cpunodebind="$NUMA_NODE")
fi

echo "[serve-h200-7b] MODEL=$MODEL GPUS=$GPUS TP=$TP PORT=$PORT MML=$MML MAXTOK=$MAXTOK (fit=$(python3 -c "print(f'{$MAXTOK/32376:.2f}')")) MEMFRAC=$MEMFRAC RATIO=$RATIO EVICT=$EVICT NUMA=$NUMA_NODE log=$LOG"
CUDA_VISIBLE_DEVICES="$GPUS" "${NUMA[@]}" python -m sglang.launch_server \
  --model-path "$MODEL" --tp "$TP" --host 0.0.0.0 --port "$PORT" \
  --context-length "$MML" --max-total-tokens "$MAXTOK" --mem-fraction-static "$MEMFRAC" \
  --json-model-override-args "$YARN" --enable-metrics \
  --attention-backend triton --sampling-backend pytorch \
  --radix-eviction-policy "$EVICT" \
  "${HICACHE[@]}" 2>&1 | tee "$LOG"

# VERIFY: grep "max_total_num_tokens" "$LOG"   (expect == MAXTOK, page-aligned)
#         grep -i "larger than the profiled value" "$LOG"   (expect NOTHING)
#         python scripts/fit_gate_yunuikang.py --target-maxtok "$MAXTOK" --log "$LOG" ...
