"""Tier C 시간 분해 계측 — SGLang 원본 파일 0-diff, 전부 monkeypatch.

측정하는 것
-----------
1. **Forward 타이머** — `TpModelWorker.forward_batch_generation` 을 감싸 step 마다
   CUDA event 로 GPU 시간을 잰다. `forward_mode` 로 decode / prefill(extend) 분류.
   overlap 스케줄링이 기본 ON 이라 forward 는 `forward_stream` 위에서 enqueue 된다
   → 이벤트를 **`torch.cuda.current_stream()`** 에 기록해야 그 스트림을 브래킷한다.
   (`Scheduler.run_batch` 를 감싸면 host enqueue 시간만 재게 되므로 쓰지 않는다.)

2. **HiCache 타이머** — `HiCacheController.start_writing` / `start_loading` 을 감싸
   각자의 전송 스트림(`write_stream` / `load_stream`) 위에서 CUDA event 로 전송 시간을 잰다.
   **TA+O 와 MORI 가 같은 경로를 쓴다** (MORI 의 typed-eviction 패치는 순서만 바꾼다)
   → 두 시스템 모두 계측된다. `mori_hicache_yunuikang` 와 **별개 레이어**라 겹쳐 적용된다.

설계 원칙
---------
* **비동기 드레인**: 이벤트를 기록만 하고, `query()` 가 True 인 것만 나중에 elapsed 계산.
  step 경로에서 `synchronize()` 를 호출하지 않는다 → 계측 자체가 타이밍을 바꾸지 않는다.
* **transfer_ms 는 GPU 예산에 더하지 않는다.** 별도 스트림에서 compute 와 overlap 되므로
  가산하면 이중 계상이다. 진단용 상한으로만 기록한다. 실제 reload stall 은 idle 에 흡수된다.
* **플래그 OFF 면 완전 무영향** — `MORI_TIERC=1` 이 아니면 `install()` 이 즉시 반환한다.

환경변수
--------
`MORI_TIERC=1`            계측 ON (없으면 무동작)
`MORI_TIERC_OUT=<path>`   steplog jsonl 경로 (기본 `/tmp/tierc_<pid>.jsonl`).
                          여러 스케줄러 프로세스를 대비해 `.<pid>` 가 자동으로 붙는다.
`MORI_TIERC_TAG=<str>`    각 줄에 붙는 라벨 (예: `MORI_C80`)
`MORI_TIERC_FLUSH=<n>`    n 줄마다 flush (기본 50)
"""
import json
import os
import sys
import time

_INSTALLED = False
_ENABLED = os.environ.get("MORI_TIERC") == "1"
# TP rank — forward 패치가 첫 호출에서 채운다. 미상이면 -1.
_RANK = {"v": -1}


class _Sink:
    """steplog jsonl writer — 프로세스마다 자기 파일을 연다."""

    def __init__(self):
        base = os.environ.get("MORI_TIERC_OUT") or f"/tmp/tierc_{os.getpid()}.jsonl"
        root, ext = os.path.splitext(base)
        self.path = f"{root}.{os.getpid()}{ext or '.jsonl'}"
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self.tag = os.environ.get("MORI_TIERC_TAG", "")
        self._f = open(self.path, "a", buffering=1024 * 64)
        self._n = 0
        # 러너가 백엔드를 SIGKILL 로 죽이면 atexit 가 안 돈다 → 창 tail 이 통째로 날아간다.
        # 레코드 수 + 시간 두 기준으로 자주 flush 해 유실을 1초 미만으로 묶는다.
        self._flush_every = int(os.environ.get("MORI_TIERC_FLUSH", "10"))
        self._flush_secs = float(os.environ.get("MORI_TIERC_FLUSH_S", "1.0"))
        self._last_flush = time.time()
        self.write({"kind": "open", "t": time.time(), "pid": os.getpid(),
                    "argv": " ".join(sys.argv[:6])})
        self._f.flush()

    def write(self, rec):
        rec["tag"] = self.tag
        # TP>1 이면 **모든 rank 가 같은 forward 를 동시에** 돈다. rank 를 안 찍으면
        # 집계에서 GPU 시간이 rank 수만큼 이중 계상된다 (TP2 → busy 가 wall 의 2배).
        rec["rank"] = _RANK["v"]
        self._f.write(json.dumps(rec, separators=(",", ":")) + "\n")
        self._n += 1
        now = time.time()
        if self._n % self._flush_every == 0 or (now - self._last_flush) >= self._flush_secs:
            self._f.flush()
            self._last_flush = now

    def close(self):
        try:
            self._f.flush(); self._f.close()
        except Exception:
            pass


_SINK = None


def _sink():
    global _SINK
    if _SINK is None:
        _SINK = _Sink()
    return _SINK


class _EventPool:
    """CUDA event 재사용 풀 — step 마다 새로 만들면 할당 비용이 붙는다."""

    def __init__(self, torch):
        self._torch = torch
        self._free = []

    def get(self):
        if self._free:
            return self._free.pop()
        return self._torch.cuda.Event(enable_timing=True)

    def put(self, ev):
        if len(self._free) < 512:
            self._free.append(ev)


class _Pending:
    """기록만 해 두고 완료된 것부터 회수하는 큐 (동기화 없음)."""

    def __init__(self, pool, emit):
        self._q = []
        self._pool = pool
        self._emit = emit

    def add(self, start_ev, end_ev, meta):
        self._q.append((start_ev, end_ev, meta))

    def drain(self, force=False):
        keep = []
        for start_ev, end_ev, meta in self._q:
            done = True
            if not force:
                try:
                    done = end_ev.query()
                except Exception:
                    done = True
            if not done:
                keep.append((start_ev, end_ev, meta))
                continue
            try:
                if force:
                    end_ev.synchronize()
                meta["gpu_ms"] = float(start_ev.elapsed_time(end_ev))
            except Exception as e:
                meta["gpu_ms"] = None
                meta["err"] = repr(e)[:120]
            self._emit(meta)
            self._pool.put(start_ev); self._pool.put(end_ev)
        self._q = keep

    def __len__(self):
        return len(self._q)


def install() -> None:
    """SGLang import 이후, 스케줄러 생성 이전에 호출된다 (sitecustomize 경유)."""
    global _INSTALLED
    if not _ENABLED or _INSTALLED:
        return
    _INSTALLED = True

    try:
        import torch
    except Exception as e:
        print(f"[tierc] torch 없음, 계측 비활성: {e!r}", file=sys.stderr)
        return

    pool = _EventPool(torch)
    sink = _sink()

    # ───────────────────────────── 1. Forward 타이머
    fwd_pending = _Pending(pool, sink.write)
    _ctr = {"step": 0}

    try:
        from sglang.srt.managers import tp_worker as TW
        target_cls = TW.TpModelWorker
        _orig_fwd = target_cls.forward_batch_generation
    except Exception as e:
        print(f"[tierc] forward 패치 대상 없음: {e!r}", file=sys.stderr)
        _orig_fwd = None

    if _orig_fwd is not None:

        def _fwd(self, model_worker_batch=None, *a, **kw):
            if _RANK["v"] < 0:
                try:
                    _RANK["v"] = int(getattr(self, "tp_rank", 0) or 0)
                except Exception:
                    _RANK["v"] = 0
            mwb = model_worker_batch
            fm = getattr(mwb, "forward_mode", None)
            # 분류 + 토큰 수 (host 측 값이라 GPU 동기화 불필요)
            kind, ntok = "other", 0
            try:
                if fm is not None:
                    if fm.is_decode():
                        kind = "decode"
                        sl = getattr(mwb, "seq_lens", None)
                        ntok = int(sl.shape[0]) if sl is not None else 0
                    elif fm.is_extend():
                        kind = "prefill"
                        ntok = int(getattr(mwb, "extend_num_tokens", 0) or 0)
                    elif fm.is_idle():
                        kind = "idle_batch"
            except Exception:
                pass

            start_ev = pool.get(); end_ev = pool.get()
            stream = torch.cuda.current_stream()
            t0 = time.time()
            start_ev.record(stream)
            try:
                return _orig_fwd(self, model_worker_batch, *a, **kw)
            finally:
                end_ev.record(stream)
                t1 = time.time()
                _ctr["step"] += 1
                fwd_pending.add(start_ev, end_ev, {
                    "kind": "fwd", "step": _ctr["step"], "t": t0,
                    "host_ms": (t1 - t0) * 1e3, "batch": kind, "ntok": ntok,
                    "bs": int(getattr(mwb, "seq_lens", torch.empty(0)).shape[0])
                          if getattr(mwb, "seq_lens", None) is not None else 0,
                })
                # 완료된 것만 비차단 회수
                if _ctr["step"] % 8 == 0:
                    fwd_pending.drain()

        target_cls.forward_batch_generation = _fwd

    # ───────────────────────────── 2. HiCache 타이머
    hic_pending = _Pending(pool, sink.write)

    try:
        from sglang.srt.managers import cache_controller as CC
        HCC = CC.HiCacheController
    except Exception as e:
        print(f"[tierc] hicache 패치 대상 없음: {e!r}", file=sys.stderr)
        HCC = None

    def _wrap_transfer(cls, name, direction, stream_attr, queue_attr, idx_attr):
        orig = getattr(cls, name, None)
        if orig is None:
            return

        def _patched(self, *a, **kw):
            q = getattr(self, queue_attr, None)
            ntok = 0
            try:
                if q:
                    ntok = sum(int(getattr(op, idx_attr).shape[0]) for op in q)
            except Exception:
                pass
            if not ntok:                       # 빈 큐 → 원본만 호출
                return orig(self, *a, **kw)
            stream = getattr(self, stream_attr, None)
            if stream is None:
                return orig(self, *a, **kw)
            start_ev = pool.get(); end_ev = pool.get()
            t0 = time.time()
            # 전송은 전용 스트림에 enqueue 되므로 그 스트림 위에서 브래킷한다
            with torch.cuda.stream(stream):
                start_ev.record(stream)
            try:
                return orig(self, *a, **kw)
            finally:
                with torch.cuda.stream(stream):
                    end_ev.record(stream)
                hic_pending.add(start_ev, end_ev, {
                    "kind": "xfer", "dir": direction, "t": t0, "ntok": ntok,
                })
                if len(hic_pending) > 24:
                    hic_pending.drain()

        setattr(cls, name, _patched)

    if HCC is not None:
        # write = device→host (offload) · load = host→device (reload)
        _wrap_transfer(HCC, "start_writing", "offload", "write_stream",
                       "write_queue", "device_indices")
        _wrap_transfer(HCC, "start_loading", "reload", "load_stream",
                       "load_queue", "host_indices")

    # ───────────────────────────── 3. 종료 시 잔여 회수
    import atexit
    import signal

    _done = {"v": False}

    def _final(*_a):
        if _done["v"]:
            return
        _done["v"] = True
        try:
            fwd_pending.drain(force=True)
            hic_pending.drain(force=True)
            sink.write({"kind": "close", "t": time.time()})
        finally:
            sink.close()

    atexit.register(_final)
    # 러너는 SIGTERM → (유예) → SIGKILL 순으로 죽인다. SIGTERM 에서 잔여 이벤트를 회수하고
    # 원래 핸들러로 넘겨야 창 tail 이 남는다. SIGKILL 은 잡을 수 없으므로 위의 주기 flush 가 방어선.
    for _sig in (signal.SIGTERM, signal.SIGINT):
        try:
            _prev = signal.getsignal(_sig)

            def _handler(signum, frame, _prev=_prev):
                _final()
                if callable(_prev):
                    _prev(signum, frame)
                elif _prev == signal.SIG_DFL:
                    signal.signal(signum, signal.SIG_DFL)
                    os.kill(os.getpid(), signum)

            signal.signal(_sig, _handler)
        except (ValueError, OSError):
            pass          # 메인 스레드가 아니면 등록 불가 — 주기 flush 로 충분

    print(f"[tierc] 계측 ON · steplog={sink.path} · tag={sink.tag!r}", file=sys.stderr)
