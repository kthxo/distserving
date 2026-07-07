#!/usr/bin/env bash
# Experiment C master orchestrator — runs ALL phases sequentially in one tmux
# window, crash-resilient (each point appends immediately to its own jsonl).
# Isolated to GPU2/3, proxy :9001. Never touches the SWE sweep (:9000, GPU0/1).
#
# Phases (per plans/2026-07-06_PLAN_experiment-C + user priority):
#   0  wait for c=1 duty profile to finish (started separately)
#   A  main sweep: tr + default, C=4,8,16,32, REPEAT=3, tool_scale=1
#   R  R=1 crossing (KEY causal test): tr, C=16, tool_scale in {0.5,0.25,0.2,0.125}
#   K  k_fit knob: tr, C=16, --use-acting-token-decay ; --acting-token-weight 0.5
#   D2 duty knob (other end, causal isolation): tr, C=16, tool_scale=2
set -uo pipefail
REPO=/home/yunuikang/yunuikang_work/distserving
S=/home/yunuikang/yunuikang_work/scratch/expC
SWEEP="$REPO/scripts/run_trace_sweep_expC_yunuikang.sh"
TRACE=/home/yunuikang/yunuikang_work/scratch/traces/tracelab_fit32k.jsonl
export NPROG=64 REPEAT=3 TAG=tracelab
MLOG="$S/MASTER.log"
ts(){ date +%H:%M:%S; }
say(){ echo "[$(ts)] $*" | tee -a "$MLOG"; }

mkdir -p "$S"
say "===== expC MASTER START (concurrent with SWE sweep — shares node CPU/RAM) ====="

# --- Phase 0: wait for c=1 duty profile ---
say "Phase 0: waiting for c=1 duty profile (DUTY_END marker)..."
for i in $(seq 1 120); do grep -q DUTY_END "$S/duty_timing.txt" 2>/dev/null && break; sleep 15; done
say "Phase 0 done (or timed out after 30min). duty steps: $(wc -l < $S/prof_duty/step_profiles.csv 2>/dev/null)"

# --- Phase A: main sweep ---
say "Phase A: tr main sweep C=4,8,16,32 (tool_scale=1)"
TOOL_SCALE=1.0 bash "$SWEEP" tr      "$S/expC_tr.jsonl"      "$TRACE" 4 8 16 32 2>&1 | tee -a "$MLOG"
say "Phase A: default main sweep C=4,8,16,32 (tool_scale=1)"
TOOL_SCALE=1.0 bash "$SWEEP" default "$S/expC_default.jsonl" "$TRACE" 4 8 16 32 2>&1 | tee -a "$MLOG"
say "Phase A COMPLETE"

# --- Phase R: R=1 crossing (KEY) — tr, C=16, decreasing tool_scale ---
for TS in 0.5 0.25 0.2 0.125; do
  say "Phase R: tr C=16 tool_scale=$TS (R=1 crossing)"
  LABEL="cross_ts${TS}" TOOL_SCALE=$TS bash "$SWEEP" tr "$S/expC_cross_ts${TS}.jsonl" "$TRACE" 16 2>&1 | tee -a "$MLOG"
done
say "Phase R COMPLETE"

# --- Phase K: k_fit knob — tr, C=16 ---
say "Phase K: tr C=16 --use-acting-token-decay"
LABEL="knob_decay" PROXY_EXTRA="--use-acting-token-decay" TOOL_SCALE=1.0 \
  bash "$SWEEP" tr "$S/expC_knob_decay.jsonl" "$TRACE" 16 2>&1 | tee -a "$MLOG"
say "Phase K: tr C=16 --acting-token-weight 0.5"
LABEL="knob_weight05" PROXY_EXTRA="--acting-token-weight 0.5" TOOL_SCALE=1.0 \
  bash "$SWEEP" tr "$S/expC_knob_weight05.jsonl" "$TRACE" 16 2>&1 | tee -a "$MLOG"
say "Phase K COMPLETE"

# --- Phase D2: duty knob other end (causal isolation, minimal) ---
say "Phase D2: tr C=16 tool_scale=2 (duty other end)"
LABEL="cross_ts2.0" TOOL_SCALE=2.0 bash "$SWEEP" tr "$S/expC_cross_ts2.0.jsonl" "$TRACE" 16 2>&1 | tee -a "$MLOG"
say "Phase D2 COMPLETE"

say "===== expC MASTER DONE ====="
touch "$S/expC_all_done.marker"
