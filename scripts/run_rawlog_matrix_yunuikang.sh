#!/usr/bin/env bash
# MORI raw-log steady-state 러너 — nutella1 / RTX PRO 6000 (GPU2) / TP1 / 3셀
#
# PLAN : plans/2026-08-15_PLAN_rawlog-steadystate-mori-tp1_yunuikang.md §5
# 셀   : C = fit / 2fit / 4fit  (STEP2 실측: pool 1,320,086 · s_ctx 31,650 · fit 41.71)
#
# 실행:
#   bash scripts/run_rawlog_matrix_yunuikang.sh                 # 3셀 순차 (본 런)
#   CLIST="42" DUR=600 SMOKE=1 bash scripts/run_rawlog_matrix_yunuikang.sh   # 스모크
#
# 셀마다: serve 재기동 -> boot assert -> proxy -> driver -> 6파일 -> closure check
# 이미 끝난 셀은 건너뛴다 (run_meta.json + summary 존재 여부로 판정).
set -uo pipefail
REPO="${REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
VENV="${VENV:-/home/yunuikang/yunuikang_work/.venv-sglang}"
PY="$VENV/bin/python"

GPU_ID="${GPU_ID:-2}"                 # ★ 지정 GPU. 0/1 은 타 사용자 점유 — 미접촉.
GPU_LABEL="${GPU_LABEL:-pro6000}"
TRACE="${TRACE:-/home/yunuikang/yunuikang_work/scratch/traces/tracelab_rawfilt_yunuikang.jsonl}"
MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}"
SERVE="${SERVE:-$REPO/scripts/_serve_sglang_7b_tp1_pro6000_mori_yunuikang.sh}"
BP=8123; PP=9000
RATIO="${RATIO:-2}"
S_CTX="${S_CTX:-31650}"               # STEP1 확정값
POOL_EXPECT="${POOL_EXPECT:-1320086}" # STEP2 실측 자연 풀
CLIST="${CLIST:-42 83 167}"           # fit / 2fit / 4fit
DUR="${DUR:-28800}"                   # ★ 셀당 고정 8h (2026-08-16 확정).
                                      #   throughput 은 rate 라 런 길이에 불변 → 정확히 끊을 필요 없음.
                                      #   대신 offline 측정 프로토콜(docs/2026-08-16_SPEC_rawlog_measurement)
                                      #   을 셀마다 동일 적용한다: warmup 40분 컷 + steady >=2h + 10분 sub-window.
GRACE="${GRACE:-2100}"                # deadline grace 35분 — 세션 wall <30분이라 완주 가능
WARM="${WARM:-0.2}"
CTXCAP="${CTXCAP:-69632}"
MAXRUN="${MAXRUN:-1024}"              # in-flight 상한 (캡 아님).  C_max=167 보다 충분히 큼
SNAPI="${SNAPI:-20}"; GPUI="${GPUI:-1}"
OUT="${OUT:-/home/yunuikang/yunuikang_work/scratch/mori/rawlog_${GPU_LABEL}}"
SMOKE="${SMOKE:-0}"
TIERC="${TIERC:-1}"                   # ★ step-log(MORI_TIERC) 기본 ON — goguma 와 대칭.
                                      #   GPU 시간예산 직접측정 + closure C1~C3 의 입력.
mkdir -p "$OUT"
RES="$OUT/results_rawlog.jsonl"; touch "$RES"

source "$VENV/bin/activate"
GITC=$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo "")
TSHA=$(sha256sum "$TRACE" | cut -d' ' -f1)
NSESS=$($PY -c "
import json,sys
s=set()
for l in open('$TRACE'):
    s.add(json.loads(l)['session_id'])
print(len(s))")

echo "=========================================================="
echo " MORI raw-log matrix · $GPU_LABEL(GPU$GPU_ID) · TP1 · MORI 단독"
echo "  trace   = $(basename "$TRACE")  sessions=$NSESS"
echo "  s_ctx   = $S_CTX   pool_expect = $POOL_EXPECT"
echo "  CLIST   = $CLIST   dur=${DUR}s grace=${GRACE}s"
echo "  out     = $OUT"
echo "=========================================================="

BPID=""; PXPID=""
kill_proxy(){ [ -n "$PXPID" ] && kill "$PXPID" 2>/dev/null
  for pid in $(pgrep -u "$(id -u)" -f "bin/thunderagent" 2>/dev/null); do
    cl=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null); case " $cl " in *" --port $PP "*) kill "$pid";; esac; done
  sleep 2; PXPID=""; }
# ★ 가드레일: pkill 을 반드시 `-u $(id -u)` 로 한정한다.
#   이 박스에는 타 사용자(muchwater)의 sglang 프로세스가 상시 떠 있다.
#   `-u` 없이 `pkill -f sglang.launch_server` 를 하면 그 프로세스까지 시그널 대상이 된다.
MYUID=$(id -u)
kill_backend(){ [ -n "$BPID" ] && kill "$BPID" 2>/dev/null
  # SIGTERM 먼저 — 로거가 잔여 이벤트를 flush 할 시간을 준다 (SIGKILL 은 못 잡는다)
  pkill -u "$MYUID" -f "_serve_sglang_7b_tp1_pro6000_mori_yunuikang" 2>/dev/null
  pkill -u "$MYUID" -f "sglang.launch_server" 2>/dev/null
  pkill -u "$MYUID" -f "sglang::" 2>/dev/null
  sleep 8
  pkill -9 -u "$MYUID" -f "_serve_sglang_7b_tp1_pro6000_mori_yunuikang" 2>/dev/null
  pkill -9 -u "$MYUID" -f "sglang.launch_server" 2>/dev/null
  pkill -9 -u "$MYUID" -f "sglang::" 2>/dev/null
  sleep 6; BPID=""; }
trap 'kill_proxy; kill_backend' EXIT

# ★ 타 사용자 GPU 미접촉 확인 + 우리 GPU 정리 확인
#
# 강화 이력 (2026-08-17): 1차 본 런에서 C83 이 직전 셀 메모리가 덜 반환된 상태로 기동해
#   avail mem 75.91 GB (정상 94.25 GB) 에서 프로파일 -> 풀 1,009,662 (-23.5%) -> A1 거부.
#   nvidia-smi 가 <500MiB 를 한 번 보고해도 CUDA 컨텍스트 teardown 이 아직 진행 중일 수 있다.
#   -> **연속 3회** clear 확인 + **settle 20s** 로 바꾼다.
CLEAR_STREAK="${CLEAR_STREAK:-3}"
SETTLE_S="${SETTLE_S:-20}"
wait_gpu_clear(){
  local streak=0 used
  for i in $(seq 1 120); do
    used=$(nvidia-smi --id=$GPU_ID --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null)
    if [ "${used:-9999}" -lt 500 ] 2>/dev/null; then
      streak=$((streak+1))
      if [ "$streak" -ge "$CLEAR_STREAK" ]; then
        echo "   [gpu] GPU$GPU_ID clear x$CLEAR_STREAK (${used}MiB) — settle ${SETTLE_S}s"
        sleep "$SETTLE_S"
        # settle 후 한 번 더 확인 (그 사이 타 사용자가 잡았을 수 있다 -> 그러면 대기 계속)
        used=$(nvidia-smi --id=$GPU_ID --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null)
        [ "${used:-9999}" -lt 500 ] 2>/dev/null && return 0
        echo "   [gpu] settle 후 재점유 감지 (${used}MiB) — 계속 대기"
        streak=0
      fi
    else
      streak=0
    fi
    sleep 3
  done
  echo "   !! GPU$GPU_ID 가 ${used}MiB 로 안 비워짐"; return 1; }

boot(){ # $1=TAG $2=RAWDIR $3=T0
  kill_proxy; kill_backend; wait_gpu_clear || return 1
  echo "==[serve] boot $(TZ=Asia/Seoul date +%H:%M:%S) KST  (DRAM avail $(free -g|awk '/^Mem:/{print $7}')GiB)"
  MORI_RAWLOG=1 MORI_RAWLOG_DIR="$2" MORI_RAWLOG_T0="$3" \
  MORI_TIERC="$TIERC" MORI_TIERC_TAG="$1" MORI_TIERC_OUT="$2/steplog.jsonl" \
  PYTHONPATH="$REPO/scripts/rawlog_hook_yunuikang:$REPO/scripts" \
  MODEL="$MODEL" GPUS="$GPU_ID" RATIO="$RATIO" EVICT=mori PORT=$BP MAXRUN="$MAXRUN" \
    LOG="$2/serve.log" nohup bash "$SERVE" >/dev/null 2>&1 &
  BPID=$!
  for i in $(seq 1 400); do
    curl -sf "http://127.0.0.1:$BP/health" >/dev/null 2>&1 && { echo "   READY ~$((i*3))s"; break; }
    kill -0 "$BPID" 2>/dev/null || { echo "   !! DIED"; tail -20 "$2/serve.log"; return 1; }
    sleep 3; done
  curl -sf "http://127.0.0.1:$BP/health" >/dev/null 2>&1 || { echo "   !! TIMEOUT"; return 1; }
  grep -qa "\[rawlog\] 엔진 계측 ON" "$2/serve.log" || { echo "   !! [rawlog] 배너 없음 — 엔진 로거 미적용"; return 1; }
  if [ "$TIERC" = "1" ]; then
    grep -qa "\[tierc\] 계측 ON" "$2/serve.log"    || { echo "   !! [tierc] 배너 없음 — steplog 미적용"; return 1; }
    echo "   [tierc] step-log ON: $(grep -am1 -o 'steplog=[^ ]*' "$2/serve.log")"
  fi
  # cuda graph 캡처 bs 목록 — C=83/167 에서 num_running 이 이 상한을 넘으면 eager 로 떨어진다
  echo "   [graph] $(grep -am1 -o 'Capture cuda graph bs \[[^]]*\]' "$2/serve.log")"

  # ---------- boot assert (PLAN §9.3) ----------
  G=$(grep -am1 -o "max_total_num_tokens=[0-9]*" "$2/serve.log" | cut -d= -f2)
  H=$(curl -s "http://127.0.0.1:$BP/metrics" | grep -m1 "^sglang:hicache_host_total_tokens" | awk '{print $2}')
  CAPPED=$(curl -s "http://127.0.0.1:$BP/get_server_info" | $PY -c 'import json,sys; print(json.load(sys.stdin).get("max_total_tokens"))')
  # ★ A1 수정 (2026-08-16): 자연 풀을 **하드코딩 값과 비트일치**로 검사하지 않는다.
  #   SGLang 의 풀 프로파일링은 기동마다 ±0.1% 수준으로 흔들리므로 비트일치 검사는
  #   false FAIL 을 낸다 (goguma 에서 이걸로 전 셀이 중단된 전례).
  #   대신 **"캡이 적용되지 않았음"** 을 직접 검사한다:
  #     (a) max_total_tokens == None      — 캡 플래그 자체가 안 붙었다
  #     (b) 기동 로그에 캡 경고 0건       — "larger than the profiled value" 류
  #     (c) host tier == r * pool         — 실측 풀 기준
  #   진짜 캡 실수(MAXTOK 를 실수로 주는 등)는 (a)(b) 에서 여전히 FAIL 난다.
  #   참고용으로 기준값 대비 편차를 출력하되, 편차만으로는 FAIL 시키지 않는다.
  CAPWARN=$(grep -aci "larger than the profiled\|max_total_tokens is capped\|reduce max_total_tokens" "$2/serve.log" 2>/dev/null); CAPWARN=${CAPWARN:-0}
  $PY - "$G" "$H" "$RATIO" "$POOL_EXPECT" "$S_CTX" "$CAPPED" "$CAPWARN" <<'PY' || { echo "   !! FATAL boot assert"; return 1; }
import sys
g, h, r, ref, den, capped, capwarn = (int(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]),
                                      int(sys.argv[4]), int(sys.argv[5]), sys.argv[6], int(sys.argv[7]))
fit = g / den
# ★ C 는 매 기동 **실측 풀**로 재계산한다 (하드코딩 재사용 금지)
C = [round(fit), round(2*fit), round(4*fit)]
dev = 100.0 * (g - ref) / ref
print(f"   [assert] GPU pool  = {g:,}  (기준 {ref:,} 대비 {dev:+.3f}% — 참고값, FAIL 조건 아님)")
print(f"   [assert] cap flag  = {capped}   (None 이어야 캡 미적용)")
print(f"   [assert] cap warn  = {capwarn} 건  (0 이어야 캡 미적용)")
print(f"   [assert] host tier = {h:,.0f}  (기대 r*pool = {r*g:,.0f})")
print(f"   [assert] fit       = {fit:.4f} = pool/{den:,}")
print(f"   [assert] C 재계산  = {C[0]} / {C[1]} / {C[2]}   (기대 42 / 83 / 167)")
bad = []
if capped not in ("None", "none", ""):
    bad.append(f"max_total_tokens 가 캡됨: {capped}")
if capwarn:
    bad.append(f"기동 로그에 캡 경고 {capwarn}건")
if abs(h - r*g) > g*0.02:
    bad.append(f"host tier {h:,.0f} != r*pool {r*g:,.0f}")
if C != [42, 83, 167]:
    bad.append(f"실측 풀로 재계산한 C {C} != 승인 격자 [42, 83, 167]")
if bad:
    print("   [assert] FAIL: " + "; ".join(bad)); sys.exit(1)
print("   [assert] PASS (캡 미적용 · host tier == r*pool · C 격자 일치)")
PY
}

cell(){ # $1=C
  local C="$1" TAG RAW T0
  TAG="C${C}"; RAW="$OUT/$TAG"
  if [ -s "$RAW/run_meta.json" ] && grep -qa "\"run_tag\": \"$TAG\"" "$RES" 2>/dev/null; then
    echo "[cell $TAG] SKIP (이미 완료)"; return 0; fi
  rm -rf "$RAW"; mkdir -p "$RAW"
  T0=$($PY -c 'import time;print(f"{time.time():.6f}")')   # ★ run origin — serve/driver 공통
  echo "[cell $TAG] START $(TZ=Asia/Seoul date +%H:%M:%S) KST  C=$C dur=${DUR}s T0=$T0"
  # ★ 풀 편차 > 5% 면 오염된 기동으로 보고 자동 1회 재기동 (2026-08-17 추가).
  #   teardown 지연으로 avail mem 이 덜 반환된 상태에서 프로파일되면 풀이 작게 잡힌다.
  #   A1 assert 가 잡아 주지만, 일시적 원인이므로 한 번은 자동으로 다시 시도한다.
  local attempt
  for attempt in 1 2; do
    if boot "$TAG" "$RAW" "$T0"; then
      break
    fi
    if [ "$attempt" = "1" ]; then
      G=$(grep -am1 -o "max_total_num_tokens=[0-9]*" "$RAW/serve.log" 2>/dev/null | cut -d= -f2)
      DEV=$($PY -c "print(abs(${G:-0}-$POOL_EXPECT)/$POOL_EXPECT*100 if ${G:-0} else 999)" 2>/dev/null)
      echo "[cell $TAG] boot 실패 (풀 ${G:-?}, 편차 ${DEV}%) — teardown 지연 의심, 1회 재기동"
      kill_proxy; kill_backend
      T0=$($PY -c 'import time;print(f"{time.time():.6f}")')   # 재기동이므로 원점도 새로
      rm -f "$RAW"/*.jsonl "$RAW"/run_meta.json 2>/dev/null
    else
      echo "[cell $TAG] BOOT FAIL (재기동에도 실패)"; return 1
    fi
  done

  kill_proxy
  PDIR="$RAW/profile"; mkdir -p "$PDIR"
  nohup thunderagent --backend-type sglang --backends "http://localhost:$BP" --port $PP \
    --router mori --metrics --profile --profile-dir "$PDIR" > "$RAW/proxy.log" 2>&1 &
  PXPID=$!
  for i in $(seq 1 60); do curl -sf "http://127.0.0.1:$PP/health" >/dev/null 2>&1 && break; sleep 1; done
  M=$(curl -s "http://127.0.0.1:$PP/health" | $PY -c 'import sys,json;print(json.load(sys.stdin)["router_mode"])' 2>/dev/null)
  [ "$M" = "mori" ] || { echo "[cell $TAG] FATAL router=$M (mori 아님)"; return 1; }
  echo "   [proxy] router_mode=mori"

  FIT=$($PY -c "print(f'{$POOL_EXPECT/$S_CTX:.4f}')")
  timeout $((DUR+GRACE+1800)) $PY "$REPO/scripts/mori_replay_driver_rawlog_yunuikang.py" \
    --trace "$TRACE" \
    --base-url "http://localhost:$PP" --router-url "http://localhost:$PP" \
    --backends "http://localhost:$BP" \
    --model "$MODEL" --tokenizer "$MODEL" --router mori --system MORI \
    --concurrency "$C" --duration-s $DUR --deadline-grace-s $GRACE --warmup-frac $WARM \
    --ctx-cap $CTXCAP --http-timeout 2400 --metric-interval 30 \
    --hicache-ratio $RATIO --run-tag "$TAG" --out "$RES" \
    --rawlog-dir "$RAW" --rawlog-t0 "$T0" \
    --snapshot-interval $SNAPI --gpu-interval $GPUI \
    --gpu-id $GPU_ID --gpu-label "$GPU_LABEL" \
    --fit "$FIT" --s-ctx $S_CTX --regime-label "$2" \
    --git-commit "$GITC" --trace-sha256 "$TSHA" --num-sessions "$NSESS" \
    --steplog-enabled "$TIERC" \
    > "$RAW/driver.log" 2>&1
  RC=$?
  echo "[cell $TAG] driver rc=$RC $(TZ=Asia/Seoul date +%H:%M:%S) KST"
  kill_proxy; kill_backend        # 엔진 로거가 flush 하도록 SIGTERM 먼저

  echo "[cell $TAG] closure check"
  $PY "$REPO/scripts/check_rawlog_closure_yunuikang.py" --dir "$RAW" \
    | tee "$RAW/closure.txt"
  ls -la "$RAW"/*.jsonl "$RAW"/run_meta.json 2>/dev/null | awk '{print "   "$5"  "$9}'
}

# ★ 셀 실패 시 **루프를 중단**한다 (2026-08-17 수정).
#   1차 본 런에서는 C83 이 BOOT FAIL 했는데도 루프가 C167 로 진행했다.
#   "실패면 정지·보고, 우회 금지" 원칙과 어긋나므로 첫 실패에서 멈춘다.
#   (완료된 셀은 run_meta+summary 로 판정해 다음 실행에서 자동 skip 되므로 이어받기는 그대로 된다.)
i=0
RC_ALL=0
for C in $CLIST; do
  case "$C" in 42) LBL="fit";; 83) LBL="2fit";; 167) LBL="4fit";; *) LBL="c$C";; esac
  [ "$SMOKE" = "1" ] && LBL="smoke"
  if ! cell "$C" "$LBL"; then
    echo "== ABORT: cell C$C 실패 — 이후 셀($CLIST 중 남은 것)을 진행하지 않고 중단 =="
    echo "   완료된 셀은 보존됨. 원인 해결 후 같은 명령을 다시 실행하면 완료 셀은 skip 된다."
    RC_ALL=1
    break
  fi
  i=$((i+1))
done
echo "== ALL DONE $(TZ=Asia/Seoul date +%H:%M:%S) KST (rc=$RC_ALL) =="
exit $RC_ALL
