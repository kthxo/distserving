#!/usr/bin/env bash
# STEP 6 B1 — MORI 메커니즘 통제 run (작은 통제 run, 스윕 아님).
# 기존 하네스 재사용: _serve_sglang_8b_tp2_mori_yunuikang.sh (무수정, env로만 구동).
# 압박 노브: MAXTOK을 작게 잡아 **소수 프로그램**으로 GPU tier 초과를 만든다
#   (M-SWP의 262144 대신 32768 => LONG 1 + SHORT 5, 각 ~6k tok 이면 오버서브).
set -uo pipefail
REPO=/home/yunuikang/yunuikang_work/distserving
VENV=/home/yunuikang/yunuikang_work/.venv
OUT="${OUT:-/home/yunuikang/yunuikang_work/scratch/mori/b1}"
BP="${BP:-8123}"; PP="${PP:-9000}"
MAXTOK="${MAXTOK:-32768}"; RATIO="${RATIO:-2}"; EVICT="${EVICT:-mori}"
NSHORT="${NSHORT:-5}"; SYSTOK="${SYSTOK:-6000}"
WARM="${WARM:-90}"; LONG="${LONG:-90}"; TAIL="${TAIL:-30}"
TAG="${TAG:-b1_mori}"
mkdir -p "$OUT"

kill_all(){
  for pid in $(pgrep -f "bin/thunderagent" 2>/dev/null); do
    cl=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null); case " $cl " in *" --port $PP "*) kill "$pid";; esac; done
  pkill -9 -f "_serve_sglang_8b_tp2_mori_yunuikang" 2>/dev/null
  pkill -9 -f "sglang.launch_server" 2>/dev/null; pkill -9 -f "sglang::" 2>/dev/null
  sleep 5
}
trap kill_all EXIT
kill_all

echo "==[B1] backend boot: MAXTOK=$MAXTOK RATIO=$RATIO EVICT=$EVICT $(date +%T) =="
MAXTOK=$MAXTOK RATIO="$RATIO" EVICT="$EVICT" PORT=$BP MEMFRAC="${MEMFRAC:-0.85}" \
  LOG="$OUT/serve_${TAG}.log" nohup bash "$REPO/scripts/_serve_sglang_8b_tp2_mori_yunuikang.sh" >/dev/null 2>&1 &
BPID=$!
for i in $(seq 1 300); do
  curl -sf "http://127.0.0.1:$BP/health" >/dev/null 2>&1 && { echo "[backend] READY ~$((i*3))s $(date +%T)"; break; }
  kill -0 "$BPID" 2>/dev/null || { echo "[backend] DIED — tail $OUT/serve_${TAG}.log"; tail -30 "$OUT/serve_${TAG}.log"; exit 1; }
  sleep 3
done
curl -sf "http://127.0.0.1:$BP/health" >/dev/null 2>&1 || { echo "[backend] TIMEOUT"; exit 1; }
grep -m1 "max_total_num_tokens" "$OUT/serve_${TAG}.log" || true

source "$VENV/bin/activate"
echo "==[B1] proxy boot (router=mori, ratio=$RATIO) =="
nohup thunderagent --backend-type sglang --backends "http://localhost:$BP" --port $PP \
  --router mori --mori-cpu-capacity-ratio "$RATIO" --metrics \
  > "$OUT/proxy_${TAG}.log" 2>&1 &
for i in $(seq 1 60); do curl -sf "http://127.0.0.1:$PP/health" >/dev/null 2>&1 && break; sleep 1; done
MODE=$(curl -s "http://127.0.0.1:$PP/health" | python -c 'import sys,json;print(json.load(sys.stdin)["router_mode"])' 2>/dev/null)
[ "$MODE" = "mori" ] || { echo "[proxy] FATAL router_mode=$MODE != mori"; exit 1; }
echo "[proxy] READY router_mode=$MODE"

echo "==[B1] probe start $(date +%T) =="
PYTHONUNBUFFERED=1 python -u "$REPO/scripts/mori_b1_probe_yunuikang.py" \
  --base-url "http://localhost:$PP" --router-url "http://localhost:$PP" \
  --backend "http://localhost:$BP" --gpus 0,1 \
  --n-short "$NSHORT" --sys-tokens "$SYSTOK" --long-sys-tokens "${LSYSTOK:-0}" \
  --warm-s "$WARM" --long-s "$LONG" --tail-s "$TAIL" \
  --release-n "${RELN:-2}" --release-before-s "${RELBEF:-20}" \
  --deadline-s "${DEADLINE:-420}" \
  --out "$OUT/${TAG}" 2>&1 | tee "$OUT/probe_${TAG}.log"

echo "==[B1] tier moves in proxy log =="
grep -ac "MORI demote GPU->CPU"   "$OUT/proxy_${TAG}.log" | sed 's/^/  demote GPU->CPU: /'
grep -ac "MORI promote CPU->GPU"  "$OUT/proxy_${TAG}.log" | sed 's/^/  promote CPU->GPU: /'
grep -ac "MORI evict CPU->Waiting" "$OUT/proxy_${TAG}.log" | sed 's/^/  evict CPU->Waiting: /'
grep -a "MORI demote\|MORI promote\|MORI evict" "$OUT/proxy_${TAG}.log" | head -40
echo "==[B1-DONE] $(date) out=$OUT/${TAG}_* =="
