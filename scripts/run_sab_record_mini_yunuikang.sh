#!/usr/bin/env bash
# P2 Science recording via mini-swe-agent (option B).
# Backend = Deployment A' (:8000, GPU1 single-GPU Qwen3-32B); proxy :9000 default --profile.
# Usage: NLIMIT=1 WORKERS=1 run_sab_record_mini_yunuikang.sh <note> [task_ids]
set -uo pipefail
REPO=/home/yunuikang/yunuikang_work/distserving
source /home/yunuikang/yunuikang_work/.venv/bin/activate
HDR=/home/yunuikang/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/include/python3.12
export CPATH="$HDR" C_INCLUDE_PATH="$HDR" VLLM_USE_FLASHINFER_SAMPLER=0

NOTE="${1:-smoke}"
TASK_IDS="${2:-}"
NLIMIT="${NLIMIT:-1}"
WORKERS="${WORKERS:-1}"
RECDIR="${RECDIR:-/home/yunuikang/yunuikang_work/scratch/sab/rec_${NOTE}}"
OUTDIR="${OUTDIR:-/home/yunuikang/yunuikang_work/scratch/sab/out_${NOTE}}"
mkdir -p "$RECDIR" "$OUTDIR"

# --- fresh proxy on :9000 (default router, profiling on) --------------------
for pid in $(pgrep -f "bin/thunderagent" 2>/dev/null); do
  cl=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
  case " $cl " in *" --port 9000 "*) kill "$pid";; esac
done
sleep 3
nohup thunderagent --backend-type vllm --backends http://127.0.0.1:8000 --port 9000 \
  --router default --metrics --profile --profile-dir "$RECDIR" \
  > "$RECDIR/proxy.log" 2>&1 &
for i in $(seq 1 30); do curl -sf http://127.0.0.1:9000/health >/dev/null 2>&1 && break; sleep 2; done
MODE=$(curl -s http://127.0.0.1:9000/health | python -c 'import sys,json;print(json.load(sys.stdin)["router_mode"])' 2>/dev/null)
echo "rec proxy up: mode=$MODE (expect default)"
[ "$MODE" = "default" ] || { echo "FATAL: proxy not default"; exit 3; }

echo "### SAB(mini-swe) record START $(date) note=$NOTE n=$NLIMIT workers=$WORKERS ids=${TASK_IDS:-<head>}"
ARGS=(-c "$REPO/scripts/sab_qwen32b_config_yunuikang.yaml" -o "$OUTDIR" -w "$WORKERS")
[ -n "$TASK_IDS" ] && ARGS+=(--task-ids "$TASK_IDS") || ARGS+=(-n "$NLIMIT")
python "$REPO/scripts/run_sab_minisweagent_yunuikang.py" "${ARGS[@]}"
RC=$?
echo "### SAB record DONE $(date) rc=$RC"
echo "step_profiles rows: $(wc -l < "$RECDIR/step_profiles.csv" 2>/dev/null || echo 0)"
exit $RC
