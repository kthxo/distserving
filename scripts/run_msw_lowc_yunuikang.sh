#!/usr/bin/env bash
# M-SWP-LOWC — MORI r2 low-concurrency diagnostic sweep (goguma6, real SGLang HiCache).
#   Fills the low-pressure gap below fit: C in {2,4,8,10} (oversub 0.25/0.5/1.0/1.25x
#   at fit median 8.1). MORI r2 ONLY: --router mori --mori-cpu-capacity-ratio 2,
#   --hicache-ratio 2, EVICT=mori. All other config identical to M-SWP MORI r2.
# Goal: see if MORI is competitive at oversub<=~1.25x and where degradation starts;
#   splice onto existing C=20/50/80 (collapsed) curve.
# 1h/cell (kept full 1h to maximize steady_turns — low-C is idle-heavy = small sample).
set -uo pipefail
REPO=/home/yunuikang/yunuikang_work/distserving
VENV=/home/yunuikang/yunuikang_work/.venv
TRACE=/home/yunuikang/yunuikang_work/scratch/traces/tracelab_moriM_L64k_yunuikang.jsonl
BP=8123; PP=9000; PIN="${PIN:-262144}"
DUR="${DUR:-3600}"; GRACE="${GRACE:-60}"; WARM="${WARM:-0.2}"
OUT=/home/yunuikang/yunuikang_work/scratch/mori/msw; RES=$OUT/results_msw_lowc.jsonl
HM="sglang:hicache_host_used_tokens,sglang:hicache_host_total_tokens,sglang:evicted_tokens_total,sglang:load_back_tokens_total,sglang:cached_tokens_total,sglang:prompt_tokens_total,sglang:generation_tokens_total"
mkdir -p "$OUT"
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
  DEC=$(grep -a "\"run_tag\": \"$1\"" "$RES" | tail -1 | python3 -c "
import sys,json
d=json.loads(sys.stdin.read() or '{}')
c=d.get('completed_programs',0); f=d.get('failed_programs',0); t=c+f
fr=100*f/t if t else 0.0
ft=d.get('failure_types',{}); bad=ft.get('http_400',0)+ft.get('timeout',0)
if fr>1.0 and f>=3: print(f'ABORT fr={fr:.2f} failed={f} types={ft}')
elif fr>1.0: print(('RECUR' if bad>0 else 'WARN')+f' fr={fr:.2f} failed={f} types={ft}')
else: print(f'OK fr={fr:.2f} failed={f} types={ft}')" 2>/dev/null)
  echo "[cell $1] DONE $(date +%T) gate: $DEC"
  case "$DEC" in
    ABORT*) echo "[cell $1] GATE ABORT (systematic failures >=3, >1%). Fix before continuing."; kill_proxy; kill_backend; exit 4;;
    RECUR*) echo "[cell $1] GATE WARN: tolerated (<3) BUT includes 400/timeout — REVIEW.";;
  esac
}

echo "==[M-SWP-LOWC] start $(date) pin=$PIN dur=${DUR}s (MORI r2, C in 2,4,8,10) =="
boot_backend mori 2 || exit 1
for C in 2 4 8 10; do run_cell "MORI_r2_C$C" MORI mori "--mori-cpu-capacity-ratio 2" $C; done
kill_proxy; kill_backend
echo "==[M-SWP-LOWC-DONE] $(date) results=$RES =="
nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null || true
