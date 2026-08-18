"""MORI raw-event 상시 로거 — 6-file stream.

SCHEMA : plans/2026-08-16_SCHEMA_rawlog_yunuikang.md
PLAN   : plans/2026-08-15_PLAN_rawlog-steadystate-mori-tp1_yunuikang.md §6

이 모듈은 **두 개의 역할**을 한 파일에 담는다 (가드레일이 파일 하나를 지정했으므로):

  A. `install()`  — ENGINE 쪽 monkeypatch. sitecustomize 경유로 SGLang 스케줄러
     서브프로세스에서 실행되어 `kv_events.jsonl` 을 쓴다.  `MORI_RAWLOG=1` 일 때만.
     `mori_tierc_instrument_yunuikang` 과 **독립 레이어**로 겹쳐 적용된다.
  B. `RawLogWriter` — DRIVER 쪽 writer.  `run_meta.json` / `requests.jsonl` /
     `events.jsonl` / `snapshots.jsonl` / `gpu.jsonl` 5개를 쓴다.

★ 원본·baseline 0-diff:  SGLang 원본 파일도, ThunderAgent baseline 경로
  (`scheduler/router.py`·`backend/state.py`·`profile/state.py`) 도 건드리지 않는다.
  전부 monkeypatch + 신규 파일.  플래그 OFF 면 `install()` 은 즉시 반환한다.

---------------------------------------------------------------------------
시각 규약 (SCHEMA §2)
---------------------------------------------------------------------------
run origin 0.0s = 환경변수 `MORI_RAWLOG_T0` (unix float).  러너가 serve 기동
**전에** 정해서 serve/driver 양쪽에 같은 값을 주입한다.

  * ENGINE (별도 프로세스): `ts = time.time() - T0`         — wall clock
  * DRIVER: `ts = (perf_counter() - pc0) + (t_wall0 - T0)`  — 내부는 단조시계,
    원점만 T0 로 shift.  즉 driver 안에서는 단조시계 **하나**만 쓴다.

driver 와 engine 은 같은 박스·같은 시스템 클럭이라 스큐가 없다.  다만 wall↔monotonic
드리프트를 사후 검증할 수 있게 run_meta 에 `clock_anchor` (t_wall0·pc0·T0) 를 남긴다.

---------------------------------------------------------------------------
알려진 한계 — 숨기지 않고 기록한다
---------------------------------------------------------------------------
1. **kv_events 의 session 귀속 불가**: HiCache 전송(`start_writing`/`start_loading`)
   과 radix 축출은 **트리 노드 단위**로 일어난다.  한 노드의 KV 가 여러 세션에
   공유될 수 있고, 엔진 그 레이어에는 session_id 가 존재하지 않는다.
   따라서 kv_events 의 `session_idx` 는 **항상 null** 이다.  지어내지 않는다.
   세션 귀속이 필요한 분석은 requests 의 `cached_tokens`·`kv_tokens_end` 궤적으로
   offline 재구성한다 (SCHEMA §0-5 가 상정한 경로 그대로).
2. **`tier_move` 이벤트 없음**: MORI 의 tier 이동은 별도 이벤트가 아니라
   evict(GPU→CPU) / reload(CPU→GPU) / evict_host(CPU→discard) 로 나타난다.
   스키마의 `tier_move` 대신 이 3종을 raw 로 남기고, tier 점유는 snapshots 의
   `hicache_host_used_tokens` + `num_used_tokens` 로 본다.
3. **이 SGLang 빌드에 없는 metric**: `sglang:evicted_tokens_total` ·
   `load_back_tokens_total` · `cached_tokens_total` 은 0.5.10 이 노출하지 않는다
   (실측: /metrics 목록).  그래서 evict/reload 누적은 kv_events 를 창별로 합산해
   얻는다 — snapshots 의 `cum` 에는 실제 존재하는 counter 만 넣는다.
"""
import json
import os
import sys
import threading
import time

SCHEMA_VERSION = "1.0-yunuikang-nutella"

# --------------------------------------------------------------------------
# 공통: run origin
# --------------------------------------------------------------------------
def _t0() -> float:
    """run origin (unix float).  미설정이면 프로세스 시작 시각으로 폴백하고 경고한다."""
    v = os.environ.get("MORI_RAWLOG_T0")
    if v:
        try:
            return float(v)
        except ValueError:
            pass
    return 0.0


# --------------------------------------------------------------------------
# JSONL sink — 크래시 안전 append (SCHEMA §0-2)
# --------------------------------------------------------------------------
class JsonlSink:
    """줄 단위 append writer.  레코드 수 + 경과시간 두 기준으로 flush 해서
    SIGKILL 로 죽어도 유실을 1초 미만으로 묶는다 (MORI_TIERC 규약 계승)."""

    def __init__(self, path, flush_every=50, flush_secs=1.0):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.path = path
        self._f = open(path, "a", buffering=1024 * 64)
        self._n = 0
        self._bytes = 0
        self._flush_every = int(flush_every)
        self._flush_secs = float(flush_secs)
        self._last = time.time()
        self._lock = threading.Lock()

    def write(self, rec):
        line = json.dumps(rec, separators=(",", ":"), ensure_ascii=False) + "\n"
        with self._lock:
            self._f.write(line)
            self._n += 1
            self._bytes += len(line)
            now = time.time()
            if self._n % self._flush_every == 0 or (now - self._last) >= self._flush_secs:
                self._f.flush()
                self._last = now

    @property
    def n(self):
        return self._n

    def close(self):
        try:
            with self._lock:
                self._f.flush()
                self._f.close()
        except Exception:
            pass


# ==========================================================================
# A.  ENGINE 쪽 — kv_events.jsonl  (sitecustomize 경유 monkeypatch)
# ==========================================================================
_INSTALLED = False
_ENABLED = os.environ.get("MORI_RAWLOG") == "1"


def install() -> None:
    """SGLang import 이후·스케줄러 생성 이전에 sitecustomize 가 호출한다."""
    global _INSTALLED
    if not _ENABLED or _INSTALLED:
        return
    _INSTALLED = True

    outdir = os.environ.get("MORI_RAWLOG_DIR") or "/tmp/mori_rawlog"
    # 스케줄러 서브프로세스가 여럿일 수 있으므로 pid 를 붙인다 (TP1 이라 보통 1개).
    sink = JsonlSink(os.path.join(outdir, f"kv_events.{os.getpid()}.jsonl"))
    T0 = _t0()

    def ts():
        return time.time() - T0

    def emit(rec):
        sink.write(rec)

    try:
        import torch
    except Exception as e:
        print(f"[rawlog] torch 없음, 엔진 계측 비활성: {e!r}", file=sys.stderr)
        return

    # ---------------- HiCache 전송: offload(evict->cpu) / reload(cpu->gpu)
    try:
        from sglang.srt.managers import cache_controller as CC
        HCC = CC.HiCacheController
    except Exception as e:
        print(f"[rawlog] hicache 패치 대상 없음: {e!r}", file=sys.stderr)
        HCC = None

    def _wrap_transfer(cls, name, event, queue_attr, idx_attr, extra):
        orig = getattr(cls, name, None)
        if orig is None:
            print(f"[rawlog] {name} 없음 — 건너뜀", file=sys.stderr)
            return

        def _patched(self, *a, **kw):
            q = getattr(self, queue_attr, None)
            ntok = 0
            try:
                if q:
                    ntok = sum(int(getattr(op, idx_attr).shape[0]) for op in q)
            except Exception:
                ntok = 0
            if not ntok:
                return orig(self, *a, **kw)          # 빈 큐는 이벤트 아님
            t_enq = ts()
            t_host0 = time.perf_counter()
            try:
                return orig(self, *a, **kw)
            finally:
                rec = {"ts": round(t_enq, 6), "event": event, "session_idx": None,
                       "kv_tokens": ntok,
                       "enqueue_host_s": round(time.perf_counter() - t_host0, 6)}
                rec.update(extra)
                emit(rec)

        setattr(cls, name, _patched)

    if HCC is not None:
        # write = device->host (GPU tier 축출 = CPU tier 로 내림)
        _wrap_transfer(HCC, "start_writing", "evict", "write_queue",
                       "device_indices", {"to": "cpu"})
        # load  = host->device (CPU tier 에서 복원)
        _wrap_transfer(HCC, "start_loading", "reload", "load_queue",
                       "host_indices", {"from": "cpu"})

    # ---------------- radix 축출: device tier / host tier
    try:
        from sglang.srt.mem_cache import hiradix_cache as HR
        HRC = HR.HiRadixCache
    except Exception as e:
        print(f"[rawlog] hiradix 패치 대상 없음: {e!r}", file=sys.stderr)
        HRC = None

    def _wrap_evict(cls, name, event, to):
        orig = getattr(cls, name, None)
        if orig is None:
            print(f"[rawlog] {name} 없음 — 건너뜀", file=sys.stderr)
            return

        def _patched(self, num_tokens=None, *a, **kw):
            t_enq = ts()
            t0 = time.perf_counter()
            try:
                if num_tokens is None:
                    return orig(self, *a, **kw)
                return orig(self, num_tokens, *a, **kw)
            finally:
                try:
                    req = int(num_tokens) if num_tokens is not None else 0
                except Exception:
                    req = 0
                emit({"ts": round(t_enq, 6), "event": event, "session_idx": None,
                      "kv_tokens_requested": req, "to": to,
                      "host_s": round(time.perf_counter() - t0, 6)})

        setattr(cls, name, _patched)

    if HRC is not None:
        # evict      = GPU tier 에서 노드 축출 (write_through 라 CPU 에 이미 사본 있음)
        _wrap_evict(HRC, "evict", "radix_evict_device", "cpu_or_discard")
        # evict_host = CPU tier 에서 완전 폐기 (MORI 는 여기 순서를 뒤집는다)
        _wrap_evict(HRC, "evict_host", "radix_evict_host", "discard")

    # ---------------- 종료 처리
    import atexit
    import signal

    done = {"v": False}

    def _final(*_a):
        if done["v"]:
            return
        done["v"] = True
        try:
            emit({"ts": round(ts(), 6), "event": "logger_close",
                  "session_idx": None, "records": sink.n})
        finally:
            sink.close()

    atexit.register(_final)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            prev = signal.getsignal(sig)

            def _h(signum, frame, _prev=prev):
                _final()
                if callable(_prev):
                    _prev(signum, frame)
                elif _prev == signal.SIG_DFL:
                    signal.signal(signum, signal.SIG_DFL)
                    os.kill(os.getpid(), signum)

            signal.signal(sig, _h)
        except (ValueError, OSError):
            pass          # 메인 스레드가 아니면 등록 불가 — 주기 flush 가 방어선

    emit({"ts": round(ts(), 6), "event": "logger_open", "session_idx": None,
          "pid": os.getpid(), "t0_unix": T0})
    print(f"[rawlog] 엔진 계측 ON · kv_events={sink.path} · T0={T0!r}", file=sys.stderr)


# ==========================================================================
# B.  DRIVER 쪽 — run_meta / requests / events / snapshots / gpu
# ==========================================================================
class RawLogWriter:
    """driver 프로세스에서 5개 stream 을 쓴다.  ts 는 전부 run origin 기준 float 초."""

    def __init__(self, outdir, t0_unix=None):
        os.makedirs(outdir, exist_ok=True)
        self.dir = outdir
        self.T0 = float(t0_unix) if t0_unix is not None else _t0()
        # 단조시계 앵커: 이후 모든 ts 는 pc0 기준 단조 증가값에 (t_wall0 - T0) 만 더한다.
        self._pc0 = time.perf_counter()
        self._wall0 = time.time()
        self._shift = self._wall0 - self.T0
        self.requests = JsonlSink(os.path.join(outdir, "requests.jsonl"))
        self.events = JsonlSink(os.path.join(outdir, "events.jsonl"), flush_every=10)
        self.snapshots = JsonlSink(os.path.join(outdir, "snapshots.jsonl"), flush_every=1)
        self.gpu = JsonlSink(os.path.join(outdir, "gpu.jsonl"), flush_every=20)

    # -- 시계 -------------------------------------------------------------
    def ts(self) -> float:
        """run origin(0.0) 기준 초.  driver 내부는 단조시계 하나만 쓴다."""
        return (time.perf_counter() - self._pc0) + self._shift

    def clock_anchor(self) -> dict:
        return {"t0_unix": self.T0, "driver_wall0_unix": self._wall0,
                "driver_perf_counter0": self._pc0,
                "driver_shift_s": self._shift}

    # -- streams ----------------------------------------------------------
    def run_meta(self, meta: dict):
        meta = dict(meta)
        meta["schema_version"] = SCHEMA_VERSION
        meta["clock_anchor"] = self.clock_anchor()
        path = os.path.join(self.dir, "run_meta.json")
        with open(path, "w") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        return path

    def request(self, rec: dict):
        self.requests.write(rec)

    def event(self, event: str, session_idx=None, **kw):
        rec = {"ts": round(self.ts(), 6), "event": event, "session_idx": session_idx}
        rec.update(kw)
        self.events.write(rec)

    def snapshot(self, rec: dict):
        self.snapshots.write(rec)

    def gpu_sample(self, rec: dict):
        self.gpu.write(rec)

    def counts(self) -> dict:
        return {"requests": self.requests.n, "events": self.events.n,
                "snapshots": self.snapshots.n, "gpu": self.gpu.n}

    def close(self):
        for s in (self.requests, self.events, self.snapshots, self.gpu):
            s.close()
