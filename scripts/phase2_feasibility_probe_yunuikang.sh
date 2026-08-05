#!/usr/bin/env bash
# Phase 2 실현가능성 프로브 — r을 실제로 기동해 (a) OOM 없이 뜨는지 (b) 불변식 I6가 성립하는지만 본다.
# 매트릭스(≈6h)를 걸기 전에 돌린다. 셀은 돌리지 않는다.
#
# 확인 항목:
#   1) 백엔드가 뜨는가 (SGLang host pool 가드: available-10GiB 초과 시 ValueError로 죽음)
#   2) 실제 max_total_tokens (GPU pool)  == 262,144 인가
#   3) 실제 hicache_host_total_tokens    == r x GPU pool 인가
#   4) 스케줄러 CpuTier.capacity_tokens  == host pool tokens 인가  <-- 불변식 I6
#   5) 기동 후 DRAM 여유
set -uo pipefail
REPO=/home/yunuikang/yunuikang_work/distserving
VENV=/home/yunuikang/yunuikang_work/.venv
OUT="${OUT:-/home/yunuikang/yunuikang_work/scratch/mori/phase2}"
BP=8123; PP=9000; PIN=262144
R="${R:-4}"
mkdir -p "$OUT"

kill_all(){
  for pid in $(pgrep -f "bin/thunderagent" 2>/dev/null); do
    cl=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null); case " $cl " in *" --port $PP "*) kill "$pid";; esac; done
  pkill -9 -f "_serve_sglang_8b_tp2_mori_yunuikang" 2>/dev/null
  pkill -9 -f "sglang.launch_server" 2>/dev/null; pkill -9 -f "sglang::" 2>/dev/null
  sleep 6
}
trap kill_all EXIT
kill_all

echo "==[PROBE r=$R] $(date +%T) =="
echo "-- 기동 전 DRAM --"; free -g | sed -n '2p'
echo "-- 기동 전 GPU --"; nvidia-smi --query-compute-apps=pid --format=csv,noheader | wc -l | sed 's/^/   compute procs: /'

MAXTOK=$PIN RATIO="$R" EVICT=mori PORT=$BP MEMFRAC=0.85 \
  LOG="$OUT/probe_serve_r${R}.log" nohup bash "$REPO/scripts/_serve_sglang_8b_tp2_mori_yunuikang.sh" >/dev/null 2>&1 &
BPID=$!
READY=0
for i in $(seq 1 300); do
  curl -sf "http://127.0.0.1:$BP/health" >/dev/null 2>&1 && { READY=1; echo "[backend] READY ~$((i*3))s"; break; }
  kill -0 "$BPID" 2>/dev/null || { echo "[backend] DIED at ~$((i*3))s"; break; }
  sleep 3
done
if [ "$READY" != "1" ]; then
  echo "!! 기동 실패 — host pool 가드 메시지 확인:"
  grep -aiE "Not enough host memory|ValueError|OutOfMemory|Killed" "$OUT/probe_serve_r${R}.log" | head -5
  echo "   (r을 낮춰 재시도 필요)"
  exit 2
fi

echo "-- 엔진 실측 --"
grep -am1 "max_total_num_tokens" "$OUT/probe_serve_r${R}.log" | sed 's/^/   /'
grep -am1 "Allocating .* host memory" "$OUT/probe_serve_r${R}.log" | sed 's/^/   /'
HOST_TOK=$(curl -s "http://127.0.0.1:$BP/metrics" | grep -m1 "^sglang:hicache_host_total_tokens" | awk '{print $2}')
echo "   hicache_host_total_tokens = $HOST_TOK"

source "$VENV/bin/activate"
nohup thunderagent --backend-type sglang --backends "http://localhost:$BP" --port $PP \
  --router mori --mori-cpu-capacity-ratio "$R" --metrics > "$OUT/probe_proxy_r${R}.log" 2>&1 &
for i in $(seq 1 60); do curl -sf "http://127.0.0.1:$PP/health" >/dev/null 2>&1 && break; sleep 1; done
sleep 8   # start()가 cache_config를 받아 CpuTier 용량을 세팅할 시간

echo "-- 스케줄러 장부 (불변식 I6) --"
grep -a "MORI CPU tier" "$OUT/probe_proxy_r${R}.log" | tail -1 | sed 's/^/   /'

PROXY_LOG="$OUT/probe_proxy_r${R}.log" python - "$HOST_TOK" "$R" "$PIN" <<'PY'
import re, sys, os
host_tok = float(sys.argv[1]); R = float(sys.argv[2]); PIN = int(sys.argv[3])
log = open(os.environ.get("PROXY_LOG"), encoding="utf-8", errors="replace").read()
m = re.search(r"MORI CPU tier \S+: capacity=(\d+) tok \(ratio=([\d.]+) x GPU (\d+)\)", log)
print("\n== 검증 ==")
ok = True
if not m:
    print("  !! 프록시 로그에서 CpuTier 용량 라인을 못 찾음 -> FATAL"); ok = False
else:
    cap, ratio, gpu = int(m.group(1)), float(m.group(2)), int(m.group(3))
    print(f"  GPU pool (엔진 보고)      = {gpu:,} tok   (기대 {PIN:,})  {'OK' if gpu==PIN else '!! 불일치'}")
    print(f"  host pool (엔진 metric)   = {host_tok:,.0f} tok  (기대 ~{R*PIN:,.0f})")
    print(f"  CpuTier.capacity (스케줄러) = {cap:,} tok  (기대 {int(R*PIN):,})")
    if gpu != PIN: ok = False
    if abs(host_tok - R*PIN) > PIN*0.02:
        print("  !! host pool 이 r x GPU pool 과 불일치 -> FATAL"); ok = False
    if abs(cap - R*PIN) > 1:
        print("  !! CpuTier 용량 불일치 -> FATAL"); ok = False
    if abs(cap - host_tok) > PIN*0.02:
        print(f"  !! I6 위반: 스케줄러 장부({cap:,}) != 엔진 host pool({host_tok:,.0f}) -> FATAL"); ok = False
    else:
        print(f"  I6 (스케줄러 장부 == 엔진 host pool): OK")
    fit = PIN/32376
    print(f"\n  fit = {fit:.2f}   C_crit = (1+{R:g}) x {fit:.2f} = {(1+R)*fit:.1f}")
print("\n  => 프로브", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 3)
PY
RC=$?
echo "-- 기동 후 DRAM --"; free -g | sed -n '2p'
echo "==[PROBE r=$R DONE] rc=$RC $(date +%T) =="
exit $RC
