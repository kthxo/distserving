#!/usr/bin/env bash
# M-SWP headline sweep — 18-cell 1-run pass (goguma6, real SGLang HiCache).
#   SMG(3) + TA(3) + TA+O(6=r×C) + MORI(6=r×C), C{20,50,80}, r{1,2} offloading only.
# Engine: pin --max-total-tokens 262144, YaRN 64k, --enable-metrics, HiCache ratio r,
# EVICT per system. primary=Track M (117k, decode152). Fixed 1h (hard deadline).
# Backend restarted only on the (evict,ratio) axis (5 backends); proxy (router) is
# cheap. 1 run/cell; decision-cell repeats + a-only ablation come AFTER interim report.
set -uo pipefail
REPO=/home/yunuikang/yunuikang_work/distserving
VENV=/home/yunuikang/yunuikang_work/.venv
TRACE=/home/yunuikang/yunuikang_work/scratch/traces/tracelab_moriM_L64k_yunuikang.jsonl
BP=8123; PP=9000; PIN="${PIN:-262144}"
DUR="${DUR:-3600}"; GRACE="${GRACE:-60}"; WARM="${WARM:-0.2}"  # env-overridable for pre-flight
OUT=/home/yunuikang/yunuikang_work/scratch/mori/msw; RES=$OUT/results_msw.jsonl
HM="sglang:hicache_host_used_tokens,sglang:hicache_host_total_tokens,sglang:evicted_tokens_total,sglang:load_back_tokens_total,sglang:cached_tokens_total,sglang:prompt_tokens_total,sglang:generation_tokens_total"
mkdir -p "$OUT"
# Resumable: on a fresh run, truncate results; on RESUME=1 (re-launch after a
# crash/disconnect), KEEP results and skip cells already present (run_cell checks).
[ -z "${RESUME:-}" ] && : > "$RES"
source "$VENV/bin/activate"

BPID=""
kill_backend(){ [ -n "$BPID" ] && kill "$BPID" 2>/dev/null
  pkill -9 -f "_serve_sglang_8b_tp2_mori_yunuikang" 2>/dev/null
  pkill -9 -f "sglang.launch_server" 2>/dev/null; pkill -9 -f "sglang::" 2>/dev/null; sleep 6; BPID=""; }
kill_proxy(){ for pid in $(pgrep -f "bin/thunderagent" 2>/dev/null); do
  cl=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null); case " $cl " in *" --port $PP "*) kill "$pid";; esac; done; sleep 2; }

boot_backend(){ # $1=EVICT $2=RATIO
  kill_backend
  MAXTOK=$PIN RATIO="$2" EVICT="$1" PORT=$BP MEMFRAC=0.85 \
    LOG="$OUT/serve_${1}_r${2}.log" nohup bash "$REPO/scripts/_serve_sglang_8b_tp2_mori_yunuikang.sh" >/dev/null 2>&1 &
  BPID=$!
  for i in $(seq 1 240); do
    curl -sf "http://127.0.0.1:$BP/health" >/dev/null 2>&1 && { echo "[backend $1 r$2] READY ~$((i*3))s $(date +%T)"; return 0; }
    kill -0 "$BPID" 2>/dev/null || { echo "[backend $1 r$2] DIED (serve_${1}_r${2}.log)"; return 1; }
    sleep 3
  done; echo "[backend $1 r$2] TIMEOUT"; return 1; }

run_cell(){ # $1=tag $2=system $3=router $4=extra $5=C
  # Resume skip: a completed cell writes a summary line with its run_tag to $RES.
  if grep -qa "\"run_tag\": \"$1\"" "$RES" 2>/dev/null; then
    echo "[cell $1] SKIP (already in results) $(date +%T)"; return; fi
  echo "[cell $1] START $(date +%T)"
  kill_proxy
  nohup thunderagent --backend-type sglang --backends "http://localhost:$BP" --port $PP \
    --router "$3" --metrics $4 > "$OUT/proxy_$1.log" 2>&1 &
  for i in $(seq 1 40); do curl -sf "http://127.0.0.1:$PP/health" >/dev/null 2>&1 && break; sleep 1; done
  MODE=$(curl -s "http://127.0.0.1:$PP/health" | python -c 'import sys,json;print(json.load(sys.stdin)["router_mode"])' 2>/dev/null)
  if [ "$MODE" != "$3" ]; then echo "[cell $1] FATAL proxy mode=$MODE != $3, skip"; return; fi
  SP_LOG="$OUT/gpu_$1.jsonl"
  nohup python "$REPO/scripts/sample_gpu_resident_yunuikang.py" --gpus 0,1 --out "$SP_LOG" \
    --health-url "http://localhost:$PP/health" --backends "http://localhost:$BP" >/dev/null 2>&1 & SPID=$!
  timeout $((DUR+GRACE+300)) python "$REPO/scripts/mori_replay_driver_yunuikang.py" --trace "$TRACE" \
    --base-url "http://localhost:$PP" --router-url "http://localhost:$PP" --backends "http://localhost:$BP" \
    --model Qwen/Qwen3-8B --tokenizer Qwen/Qwen3-8B --router "$3" --system "$2" \
    --concurrency "$5" --duration-s $DUR --deadline-grace-s $GRACE --warmup-frac $WARM --metric-interval 30 \
    --ctx-cap 69632 --http-timeout 2400 \
    --hicache-metrics "$HM" --run-tag "$1" --out "$RES" 2>"$OUT/err_$1.log" || echo "[cell $1] driver rc=$?"
  kill "$SPID" 2>/dev/null || true
  # auto failure-rate gate (>1% => invalid, abort sweep early — no silent invalid data)
  FR=$(grep -a "\"run_tag\": \"$1\"" "$RES" | tail -1 | python3 -c "import sys,json;d=json.loads(sys.stdin.read() or '{}');c=d.get('completed_programs',0);f=d.get('failed_programs',0);t=c+f;print(round(100*f/t,3) if t else 0)" 2>/dev/null)
  echo "[cell $1] DONE $(date +%T) failure_rate=${FR}%"
  if python3 -c "import sys;sys.exit(0 if float('${FR:-0}')>1.0 else 1)" 2>/dev/null; then
    echo "[cell $1] ★★ FAILURE-RATE GATE TRIPPED: ${FR}% > 1% — ABORTING sweep (invalid). Fix before continuing."
    kill_proxy; kill_backend; exit 4
  fi
}

echo "==[M-SWP] start $(date) pin=$PIN dur=${DUR}s (18-cell 1-run pass) =="

boot_backend lru 0 || exit 1
for C in 20 50 80; do run_cell "SMG_r0_C$C" SMG default "" $C; done
for C in 20 50 80; do run_cell "TA_r0_C$C"  TA  tr      "" $C; done

boot_backend lru 1 || exit 1
for C in 20 50 80; do run_cell "TAO_r1_C$C" TAO tr "" $C; done
boot_backend lru 2 || exit 1
for C in 20 50 80; do run_cell "TAO_r2_C$C" TAO tr "" $C; done

boot_backend mori 1 || exit 1
for C in 20 50 80; do run_cell "MORI_r1_C$C" MORI mori "--mori-cpu-capacity-ratio 1" $C; done
boot_backend mori 2 || exit 1
for C in 20 50 80; do run_cell "MORI_r2_C$C" MORI mori "--mori-cpu-capacity-ratio 2" $C; done

kill_proxy; kill_backend
echo "==[M-SWP-DONE] $(date) results=$RES =="
nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null || true
