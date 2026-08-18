#!/usr/bin/env python3
"""MORI replay driver + raw-event 상시 로깅 (STEP 3).

SCHEMA : plans/2026-08-16_SCHEMA_rawlog_yunuikang.md
PLAN   : plans/2026-08-15_PLAN_rawlog-steadystate-mori-tp1_yunuikang.md §6

★ 결정 로직 0-diff
------------------
`mori_replay_driver_yunuikang.py` 를 **수정하지 않고 import** 한다.  concurrency 는
이미 세션 단위(C개 영속 워커가 세션 하나씩 끝까지)이므로 **아무것도 바꾸지 않는다.**

세션 루프(`run_session`)만은 turn 경계마다 로깅이 필요해서 이 파일에 복사본을 둔다.
복사본은 원본에서 **로깅 호출만 추가**한 것이고, 그 사실은 기계 검증된다:

    python scripts/verify_rawlog_0diff_yunuikang.py

(로깅 라인을 제거한 뒤 원본 `run_session` 과 토큰 단위로 비교한다.)

나머지(`corpus_cycler`·`_chat`·`_worker` 구조·`summarize`·metrics 파서)는 원본을
그대로 호출한다.

출력 6-file (`--rawlog-dir`):
    run_meta.json  requests.jsonl  events.jsonl  snapshots.jsonl  gpu.jsonl
    (+ kv_events.jsonl 은 **엔진 프로세스**가 같은 디렉터리에 쓴다)
"""
import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mori_replay_driver_yunuikang as MRD          # noqa: E402  (원본, 무수정)
from mori_rawlog_yunuikang import RawLogWriter      # noqa: E402
from trace_replay_driver_yunuikang import (         # noqa: E402
    load_trace, SHARED_SYSTEM_PROMPT, TURN_PROMPT,
)

LOG = None          # RawLogWriter, main 에서 채운다


# ==========================================================================
# run_session — 원본 복사 + 로깅.  결정 로직은 한 글자도 다르지 않다.
# ==========================================================================
async def run_session_logged(client, args, padder, program_id, turns, seed,
                             results, trace, session_idx=None, cycle=None,
                             trace_session_id=None):
    """One session=program.  (원본 mori_replay_driver_yunuikang.run_session 과
    결정 로직 동일 — 로깅 호출만 추가)"""
    ctx_cap = args.ctx_cap
    messages = [{"role": "system", "content": SHARED_SYSTEM_PROMPT}]
    t_start = time.perf_counter()
    completion_tokens = turns_done = offered = tmerr = 0
    ok = True
    LOG.event("session_start", session_idx=session_idx, cycle=cycle,
              trace_session_id=trace_session_id, program_id=program_id,
              n_turns=len(turns))
    kv_tokens_end = 0
    for rec in turns:
        target_in = int(rec["input_tokens"]); out_tok = max(1, int(rec["output_tokens"]))
        tool_s = float(rec.get("tool_duration_s") or 0.0)
        core = f"[turn {rec['turn']}] {TURN_PROMPT}"
        user_msg, achieved = padder.build_user(messages, core, target_in, seed + rec["turn"])
        # trim oldest (user,assistant) pairs if the prompt overflows the window
        guard = 0
        while achieved > ctx_cap - 32 and len(messages) > 1 and guard < 200:
            del messages[1:3]
            achieved = padder.count(messages + [user_msg]); guard += 1
        if guard:
            # ctx-cap trim 이 실제로 잘랐다 — 재생 KV 곡선 추적에 필요 (SCHEMA §9-5)
            LOG.event("context_truncate", session_idx=session_idx, cycle=cycle,
                      turn=int(rec["turn"]), pairs_dropped=guard,
                      target_input_tokens=target_in, achieved_prompt_tokens=achieved,
                      ctx_cap=ctx_cap)
        messages.append(user_msg)
        offered += achieved; tmerr += abs(target_in - achieved)
        max_tokens = max(1, min(out_tok, ctx_cap - achieved - 8))  # fit prompt+output in window
        if args.dry_run:
            messages.append({"role": "assistant", "content": padder._filler_text(seed * 31 + rec["turn"], max_tokens)})
            completion_tokens += max_tokens; turns_done += 1
            trace.append({"program_id": program_id, "turn": rec["turn"], "target_input_tokens": target_in,
                          "achieved_prompt_tokens": achieved})
            continue
        payload = {"model": args.model, "messages": messages, "max_tokens": max_tokens,
                   "temperature": 0, "program_id": program_id}
        submit_ts = LOG.ts()
        try:
            msg, usage, ttft, lat = await MRD._chat(client, args.base_url, payload, args.stream, args.http_timeout)
        except asyncio.CancelledError:
            LOG.event("request_cancelled", session_idx=session_idx, cycle=cycle,
                      turn=int(rec["turn"]))
            raise
        except Exception as e:
            ok = False
            LOG.request({
                "session_idx": session_idx, "cycle": cycle, "turn": int(rec["turn"]),
                "trace_session_id": trace_session_id, "program_id": program_id,
                "session_first": int(rec["turn"]) == 0,
                "submit_ts": round(submit_ts, 6), "first_token_ts": None,
                "end_ts": round(LOG.ts(), 6),
                "input_tokens": achieved, "cached_tokens": None, "output_tokens": 0,
                "kv_tokens_end": None, "gpu_id": args.gpu_id, "status": "error",
                "error": str(e)[:200],
            })
            results.append({"program_id": program_id, "ok": False, "error": str(e)[:200]})
            break
        end_ts = LOG.ts()
        turns_done += 1
        ctok = int(usage.get("completion_tokens") or 0); completion_tokens += ctok
        trace.append({"program_id": program_id, "turn": rec["turn"], "target_input_tokens": target_in,
                      "achieved_prompt_tokens": achieved, "server_prompt_tokens": int(usage.get("prompt_tokens") or achieved),
                      "completion_tokens": ctok, "ttft_s": ttft, "turn_latency_s": lat, "tool_duration_s": tool_s})
        # ---- raw request 레코드 -------------------------------------------------
        ptok = int(usage.get("prompt_tokens") or achieved)
        det = usage.get("prompt_tokens_details") or {}
        cached = det.get("cached_tokens") if isinstance(det, dict) else None
        kv_tokens_end = ptok + ctok          # 이 턴 후 세션이 물고 있는 KV (누적)
        LOG.request({
            "session_idx": session_idx, "cycle": cycle, "turn": int(rec["turn"]),
            "trace_session_id": trace_session_id, "program_id": program_id,
            "session_first": int(rec["turn"]) == 0,
            "submit_ts": round(submit_ts, 6),
            "first_token_ts": round(submit_ts + ttft, 6) if ttft is not None else None,
            "end_ts": round(end_ts, 6),
            "ttft_s": round(ttft, 6) if ttft is not None else None,
            "turn_latency_s": round(lat, 6),
            "target_input_tokens": target_in,
            "input_tokens": ptok,
            "cached_tokens": int(cached) if cached is not None else None,
            "output_tokens": ctok,
            "max_tokens": max_tokens,
            "kv_tokens_end": kv_tokens_end,
            "tool_duration_s": tool_s,
            "gpu_id": args.gpu_id, "status": "ok",
        })
        messages.append({"role": "assistant", "content": msg})
        if tool_s > 0:
            LOG.event("tool_call", session_idx=session_idx, cycle=cycle,
                      after_turn=int(rec["turn"]), tool_s=tool_s)
            await asyncio.sleep(tool_s)
    if not args.dry_run:
        try:
            await client.post(f"{args.router_url}/programs/release", json={"program_id": program_id}, timeout=10)
        except Exception:
            pass
    if ok:
        results.append({"program_id": program_id, "ok": True, "program_latency_s": time.perf_counter() - t_start,
                        "completion_tokens": completion_tokens, "turns_done": turns_done,
                        "offered_input_tokens": offered, "token_match_err": tmerr, "finished_at": time.perf_counter()})
    LOG.event("session_end", session_idx=session_idx, cycle=cycle,
              program_id=program_id, reason="completed" if ok else "error",
              turns_done=turns_done, completion_tokens=completion_tokens,
              kv_tokens_end=kv_tokens_end)


# ==========================================================================
# worker — 원본 _worker 와 동일 구조 (세션 단위 closed-loop, 변경 없음)
# ==========================================================================
async def _worker_logged(client, args, padder, gen, sem, results, trace, deadline, cyc,
                         sid_index):
    while time.perf_counter() < deadline:
        pid, turns, seed, base_sid, cycle = next(gen)
        cyc["seen"].add(base_sid)
        cyc["max_cycle"] = max(cyc["max_cycle"], cycle)
        cyc["started"] += 1
        await run_session_logged(client, args, padder, pid, turns, seed, results, trace,
                                 session_idx=sid_index.get(base_sid), cycle=cycle,
                                 trace_session_id=base_sid)


# ==========================================================================
# 샘플러 — snapshots.jsonl / gpu.jsonl
# ==========================================================================
SNAP_GAUGES = [
    "sglang:token_usage", "sglang:num_used_tokens", "sglang:max_total_num_tokens",
    "sglang:num_running_reqs", "sglang:num_queue_reqs", "sglang:num_paused_reqs",
    "sglang:num_retracted_reqs", "sglang:cache_hit_rate", "sglang:gen_throughput",
    "sglang:hicache_host_used_tokens", "sglang:hicache_host_total_tokens",
    "sglang:utilization", "sglang:full_token_usage",
]
SNAP_COUNTERS = [
    "sglang:prompt_tokens_total", "sglang:generation_tokens_total",
    "sglang:num_requests_total", "sglang:cuda_graph_passes_total",
]


async def _snapshot_sampler(client, backend, interval, stop, cyc):
    """엔진 상태 스냅샷.  /metrics 만 읽는다 (스케줄러 루프를 건드리지 않음)."""
    while not stop.is_set():
        rec = {"ts": round(LOG.ts(), 6)}
        try:
            r = await client.get(f"{backend}/metrics", timeout=10)
            if r.status_code == 200:
                m = MRD._parse_sglang(r.text, SNAP_GAUGES + SNAP_COUNTERS)
                for k in SNAP_GAUGES:
                    rec[k.split(":", 1)[1]] = m.get(k)
                rec["cum"] = {k.split(":", 1)[1]: m.get(k) for k in SNAP_COUNTERS}
            else:
                rec["error"] = f"http {r.status_code}"
        except Exception as e:
            rec["error"] = str(e)[:200]
        rec["driver"] = {"sessions_started": cyc["started"],
                         "unique_sessions_seen": len(cyc["seen"]),
                         "max_cycle": cyc["max_cycle"]}
        LOG.snapshot(rec)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


def _gpu_sampler_thread(gpu_index, interval, stop_evt):
    """nvidia-smi 를 한 번 띄워 스트리밍으로 받는다 (프로세스 반복 생성 회피)."""
    smi = shutil.which("nvidia-smi")
    if not smi:
        LOG.gpu_sample({"ts": round(LOG.ts(), 6), "error": "nvidia-smi not found"})
        return
    cmd = [smi, f"--id={gpu_index}", "--format=csv,noheader,nounits",
           "--query-gpu=utilization.gpu,utilization.memory,memory.used,memory.total,"
           "power.draw,clocks.sm,clocks.mem,temperature.gpu",
           f"-l", str(max(1, int(round(interval))))]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    except Exception as e:
        LOG.gpu_sample({"ts": round(LOG.ts(), 6), "error": f"spawn failed {e!r}"})
        return
    try:
        for line in p.stdout:
            if stop_evt.is_set():
                break
            f = [x.strip() for x in line.strip().split(",")]
            if len(f) < 8:
                continue

            def _n(v):
                try:
                    return float(v)
                except ValueError:
                    return None
            LOG.gpu_sample({"ts": round(LOG.ts(), 6), "gpu_id": gpu_index,
                            "util_pct": _n(f[0]), "mem_util_pct": _n(f[1]),
                            "mem_used_mib": _n(f[2]), "mem_total_mib": _n(f[3]),
                            "power_w": _n(f[4]), "sm_clock_mhz": _n(f[5]),
                            "mem_clock_mhz": _n(f[6]), "temp_c": _n(f[7])})
    except Exception as e:
        LOG.gpu_sample({"ts": round(LOG.ts(), 6), "error": str(e)[:200]})
    finally:
        try:
            p.terminate()
        except Exception:
            pass


# ==========================================================================
# orchestration — 원본 main_async 와 동일 구조 + 로깅/샘플러
# ==========================================================================
async def main_async(args) -> dict:
    import threading

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.tokenizer)
    padder = MRD.Padder(tok)
    sessions = load_trace(args.trace)
    # session_idx = pool 순서 인덱스 (전 run 고정) — SCHEMA §2 join 키
    sid_index = {sid: i for i, (sid, _turns) in enumerate(sessions)}
    extra = [s.strip() for s in args.hicache_metrics.split(",") if s.strip()]
    backends = [u.strip() for u in args.backends.split(",") if u.strip()]

    results, trace = [], []
    cyc = {"seen": set(), "max_cycle": 0, "started": 0}

    import httpx
    limits = httpx.Limits(max_connections=None, max_keepalive_connections=None)
    async with httpx.AsyncClient(limits=limits) as client:
        m_before = await MRD._fetch_sglang(client, backends, extra)
        series: list = []
        stop = asyncio.Event()
        sampler = asyncio.create_task(
            MRD._metric_sampler(client, backends, args.metric_interval, extra, series, stop))
        snapper = asyncio.create_task(
            _snapshot_sampler(client, backends[0], args.snapshot_interval, stop, cyc))
        gpu_stop = threading.Event()
        gpu_thr = threading.Thread(target=_gpu_sampler_thread,
                                   args=(args.gpu_id, args.gpu_interval, gpu_stop),
                                   daemon=True)
        gpu_thr.start()

        LOG.event("run_start", concurrency=args.concurrency, duration_s=args.duration_s)
        gen = MRD.corpus_cycler(sessions, args.seed)
        sem = asyncio.Semaphore(args.concurrency)
        wall0 = time.perf_counter()
        deadline = wall0 + args.duration_s
        workers = [
            asyncio.create_task(
                _worker_logged(client, args, padder, gen, sem, results, trace, deadline, cyc, sid_index))
            for _ in range(args.concurrency)
        ]
        try:
            await asyncio.wait_for(asyncio.gather(*workers),
                                   timeout=args.duration_s + args.deadline_grace_s)
        except asyncio.TimeoutError:
            LOG.event("deadline_cancel", n_workers=len(workers),
                      grace_s=args.deadline_grace_s)
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
        wall = time.perf_counter() - wall0
        LOG.event("run_end", wall_s=round(wall, 3))

        stop.set()
        gpu_stop.set()
        await sampler
        await snapper
        m_after = await MRD._fetch_sglang(client, backends, extra)

    return MRD.summarize(args, backends, sessions, results, trace, wall, cyc, series,
                         m_before=m_before, m_after=m_after, extra=extra, wall0=wall0)


def build_run_meta(args, boot: dict) -> dict:
    return {
        "run_id": args.run_tag,
        "gpu": args.gpu_label, "gpu_index": args.gpu_id, "tp": 1,
        "host": os.uname().nodename,
        "git_commit": args.git_commit,
        "engine": {"name": "sglang", "version": boot.get("version"),
                   "attention_backend": boot.get("attention_backend"),
                   "sampling_backend": boot.get("sampling_backend"),
                   "flags": {"tp_size": boot.get("tp_size"),
                             "mem_fraction_static": boot.get("mem_fraction_static"),
                             "max_running_requests": boot.get("max_running_requests"),
                             "hierarchical_cache": boot.get("enable_hierarchical_cache"),
                             "hicache_ratio": boot.get("hicache_ratio"),
                             "hicache_write_policy": boot.get("hicache_write_policy"),
                             "chunked_prefill_size": boot.get("chunked_prefill_size"),
                             "max_total_tokens_cap": boot.get("max_total_tokens"),
                             "radix_eviction_policy": boot.get("radix_eviction_policy")}},
        "model": {"name": args.model, "dtype": "bf16", "num_layers": 28,
                  "kv_heads": 4, "head_dim": 128, "kv_bytes_per_token": 57344,
                  "context_length": boot.get("context_length")},
        "router": {"mode": args.router, "system": args.system},
        "kv_pool": {"gpu_pool_tokens": boot.get("max_total_num_tokens"),
                    "host_tier_tokens": boot.get("host_tier_tokens"),
                    "r": args.hicache_ratio, "capped": boot.get("max_total_tokens") is not None},
        "regime": {"fit": args.fit, "s_ctx_tokens": args.s_ctx,
                   "concurrency_level": args.regime_label},
        "concurrency": args.concurrency,
        "dataset": {"pool_file": args.trace, "pool_sha256": args.trace_sha256,
                    "num_sessions": args.num_sessions, "seed": args.seed},
        "preprocessing": {"base": "tracelab_moriM_L64k_yunuikang.jsonl (Track M, L=64k window, tool/hw cap 300s)",
                          "filter": "drop_session_if_wall_ge",
                          "wall_threshold_s": 1800},
        "driver": {"ctx_cap": args.ctx_cap, "deadline_grace_s": args.deadline_grace_s,
                   "duration_s": args.duration_s, "warmup_frac": args.warmup_frac,
                   "http_timeout_s": args.http_timeout, "stream": args.stream},
        "steplog_enabled": str(args.steplog_enabled) == "1",
        "cuda_graph": {
            "max_bs_raised": False,
            "note": "--cuda-graph-max-bs 를 올리지 않았다(기본값 유지). 올리면 graph 캡처가 "
                    "정적 메모리를 더 먹어 자연 KV 풀이 줄고 fit·C(42/83/167)가 바뀐다 — "
                    "승인된 격자를 보존하려고 기본값을 유지했다. 대신 snapshots.num_running_reqs 로 "
                    "graph 상한 초과분을 사후 계량한다(아래 caveat).",
        },
        "sampler": {"snapshot_interval_s": args.snapshot_interval,
                    "gpu_interval_s": args.gpu_interval,
                    "metric_interval_s": args.metric_interval},
        "timing": {"wall_clock_origin_kst": time.strftime(
            "%Y-%m-%dT%H:%M:%S+09:00", time.localtime(LOG.T0 + 9 * 3600))},
        "numa": {
            "gpu_numa_node": 1,
            "policy": "numactl --preferred=1 --cpunodebind=1",
            "membind_not_used_reason":
                "host tier 141 GiB > node1 용량 126 GiB → --membind=1 이면 할당 실패. "
                "--preferred 로 node1 우선 + node0 spill 허용.",
        },
        "caveats": [
            "동일 박스 co-tenant 있음: 사용자 muchwater 가 GPU0/GPU1 을 점유한 채 별도 작업 수행 "
            "(CPU 16core·DRAM·PCIe 를 공유).  이 run 은 GPU2 만 사용하지만 host 자원 경합은 통제되지 않음.",
            "★ host tier(141 GiB) > NUMA node1 용량(126 GiB) 이므로 host tier 의 일부가 node0 로 "
            "spill 된다.  압박이 큰 셀(C=4fit)일수록 host tier 점유가 포화에 가까워져 spill 비중이 "
            "커지고, 그 셀의 reload latency 에는 [cross-NUMA 전송] + [co-tenant PCIe/DRAM 경합] 이 "
            "섞인다.  → C=4fit 셀의 reload 관련 수치는 과해석 금지 (교란 미통제).",
            "kv_events 의 session_idx 는 항상 null — 엔진 HiCache/radix 레이어에 세션 개념이 없음.",
            "tier_move 이벤트 없음 — MORI tier 이동은 evict/reload/evict_host 3종으로만 관측됨.",
            "n=1 (런 1회).  분산은 steady window 를 10분 sub-window 로 분할해 얻는다.",
            "★ cuda graph 캡처 bs 상한(기본, 실측 최대 32)을 넘는 배치는 eager 로 떨어진다. "
            "C=fit(42)는 대부분 graph 안에 들지만 C=2fit(83)·4fit(167)에서는 num_running 이 "
            "상한을 넘는 구간이 생길 수 있다. 그러면 셀 간 차이에 [MORI 동역학] 뿐 아니라 "
            "[graph vs eager 실행경로] 가 섞인다. snapshots.num_running_reqs 로 초과 비율을 "
            "계량해 결과 로그에 남긴다 — 그 비율이 셀마다 크게 다르면 셀 간 비교 시 교란으로 취급할 것.",
            "★ steady bin 들은 서로 독립이 아닐 수 있다 (throughput 지속성/자기상관). "
            "따라서 bin 표본에 정규근사로 붙인 CI95 는 실제보다 **다소 낙관적(좁게)** 나올 수 있다. "
            "이 배치는 판정이 아니라 특성화이므로 그대로 진행하되, CI95 를 유의성 근거로 쓰지 말 것.",
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="MORI replay driver + raw-event logging")
    # --- 원본과 동일한 인자 (결정 로직에 들어가는 것들) ---
    ap.add_argument("--trace", required=True)
    ap.add_argument("--base-url", default="http://localhost:9000")
    ap.add_argument("--router-url", default="http://localhost:9000")
    ap.add_argument("--backends", default="http://localhost:8123")
    ap.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--tokenizer", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--router", default="mori")
    ap.add_argument("--system", default="MORI")
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--duration-s", type=float, default=3600.0)
    ap.add_argument("--deadline-grace-s", type=float, default=45.0)
    ap.add_argument("--ctx-cap", type=int, default=69632)
    ap.add_argument("--http-timeout", type=float, default=2400.0)
    ap.add_argument("--warmup-frac", type=float, default=0.2)
    ap.add_argument("--hicache-ratio", type=float, default=2.0)
    ap.add_argument("--metric-interval", type=float, default=30.0)
    ap.add_argument("--hicache-metrics", default="")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--stream", action="store_true", default=True)
    ap.add_argument("--no-stream", dest="stream", action="store_false")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run-tag", default="mori")
    ap.add_argument("--out", default="")
    # --- raw 로깅 전용 (결정 로직에 영향 없음) ---
    ap.add_argument("--rawlog-dir", required=True)
    ap.add_argument("--rawlog-t0", type=float, default=None,
                    help="run origin unix time (러너가 serve 기동 전에 정한 값)")
    ap.add_argument("--snapshot-interval", type=float, default=20.0)
    ap.add_argument("--gpu-interval", type=float, default=1.0)
    ap.add_argument("--gpu-id", type=int, default=2)
    ap.add_argument("--gpu-label", default="pro6000")
    ap.add_argument("--fit", type=float, default=None)
    ap.add_argument("--s-ctx", type=int, default=31650)
    ap.add_argument("--regime-label", default="")
    ap.add_argument("--git-commit", default="")
    ap.add_argument("--trace-sha256", default="")
    ap.add_argument("--num-sessions", type=int, default=0)
    ap.add_argument("--steplog-enabled", default="0",
                    help="러너가 MORI_TIERC 값을 그대로 넘긴다 (run_meta 기록용)")
    args = ap.parse_args()

    global LOG
    LOG = RawLogWriter(args.rawlog_dir,
                       t0_unix=args.rawlog_t0 if args.rawlog_t0 else None)

    # boot 정보 (run_meta 용) — 실패해도 런은 계속한다
    boot = {}
    try:
        import urllib.request
        with urllib.request.urlopen(f"{args.backends.split(',')[0]}/get_server_info",
                                    timeout=20) as r:
            boot = json.load(r)
    except Exception as e:
        boot = {"error": str(e)[:200]}
    try:
        import urllib.request
        with urllib.request.urlopen(f"{args.backends.split(',')[0]}/metrics", timeout=20) as r:
            txt = r.read().decode()
        m = MRD._parse_sglang(txt, ["sglang:hicache_host_total_tokens"])
        boot["host_tier_tokens"] = m.get("sglang:hicache_host_total_tokens")
    except Exception:
        boot["host_tier_tokens"] = None

    meta_path = LOG.run_meta(build_run_meta(args, boot))
    print(f"[rawlog] run_meta -> {meta_path}", flush=True)

    try:
        summary = asyncio.run(main_async(args))
    finally:
        LOG.event("logger_close", counts=LOG.counts())
        LOG.close()

    summary["rawlog_dir"] = args.rawlog_dir
    summary["rawlog_counts"] = LOG.counts()
    line = json.dumps(summary, ensure_ascii=False)
    print(line)
    if args.out:
        with open(args.out, "a", encoding="utf-8") as f:
            f.write(line + "\n")


if __name__ == "__main__":
    main()
