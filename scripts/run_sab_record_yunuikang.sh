#!/usr/bin/env bash
# P2 Science: SAB inference via ThunderAgent proxy(:9000 default --profile) + docker sandbox.
# Backend = Deployment A' (:8000, GPU1 single-GPU Qwen3-32B) — assumed already up and idle.
# Runs the isolated ported harness in the isolated OpenHands venv.
# Usage: NLIMIT=1 WORKERS=1 run_sab_record_yunuikang.sh [eval_note]
set -uo pipefail
REPO=/home/yunuikang/yunuikang_work/distserving
OH="$REPO/examples/inference/OpenHands"
OHVENV=/home/yunuikang/yunuikang_work/.venv_oh_yunuikang/bin
MAINVENV=/home/yunuikang/yunuikang_work/.venv/bin

NOTE="${1:-sab}"
NLIMIT="${NLIMIT:-1}"
WORKERS="${WORKERS:-1}"
MAXITER="${MAXITER:-30}"
RECDIR="${RECDIR:-/home/yunuikang/yunuikang_work/scratch/sab/rec_${NOTE}}"
OUTDIR="${OUTDIR:-/home/yunuikang/yunuikang_work/scratch/sab/out_${NOTE}}"
mkdir -p "$RECDIR" "$OUTDIR"

# --- fresh proxy on :9000 (default router, profiling on) --------------------
for pid in $(pgrep -f "bin/thunderagent" 2>/dev/null); do
  cl=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
  case " $cl " in *" --port 9000 "*) kill "$pid";; esac
done
sleep 3
PATH="$MAINVENV:$PATH" nohup thunderagent --backend-type vllm \
  --backends http://127.0.0.1:8000 --port 9000 \
  --router default --metrics --profile --profile-dir "$RECDIR" \
  > "$RECDIR/proxy.log" 2>&1 &
for i in $(seq 1 30); do curl -sf http://127.0.0.1:9000/health >/dev/null 2>&1 && break; sleep 2; done
MODE=$(curl -s http://127.0.0.1:9000/health | "$MAINVENV/python" -c 'import sys,json;print(json.load(sys.stdin)["router_mode"])' 2>/dev/null)
echo "rec proxy up: mode=$MODE (expect default)"
[ "$MODE" = "default" ] || { echo "FATAL: proxy not default"; exit 3; }

# --- run SAB inference -----------------------------------------------------
echo "### SAB record START $(date) note=$NOTE n_limit=$NLIMIT workers=$WORKERS max_iter=$MAXITER"
cd "$OH" || exit 4
RUNTIME=docker SAB_BENCHMARK_PATH="$REPO/scratch/sab/benchmark" \
"$OHVENV/python" -m evaluation.benchmarks.scienceagentbench_yunuikang.run_infer_yunuikang \
  --config-file "$REPO/scripts/sab_config_yunuikang.toml" \
  --llm-config sab_qwen32b \
  --agent-cls CodeActAgent \
  --max-iterations "$MAXITER" \
  --eval-n-limit "$NLIMIT" \
  --eval-num-workers "$WORKERS" \
  --eval-output-dir "$OUTDIR" \
  --eval-note "$NOTE" \
  --use-knowledge true
RC=$?
echo "### SAB record DONE $(date) rc=$RC"
echo "step_profiles rows: $(wc -l < "$RECDIR/step_profiles.csv" 2>/dev/null || echo 0)"
exit $RC
