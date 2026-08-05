#!/usr/bin/env python3
"""STEP 6 B1 — MORI 메커니즘 통제 프로브: "idle은 GPU를 떠나고 busy는 남는가".

논문 근거: active 프로그램을 GPU에 두어 util 최대화(§2), idle(긴 툴콜)은 CPU로 offload해
HBM 확보(§3.4), CPU 재개 = PCIe reload(쌈) vs Waiting 재개 = full recompute(비쌈)(§4.1).

설계 (모든 값은 관측이지 가정이 아님):
  * 프로그램 N개를 ThunderAgent 프록시에 붙여 비슷한 크기의 컨텍스트를 만든다 (GPU tier 압박 유발).
  * 그 중 **LONG 1개**만 지정된 시점에 **긴 tool call**(수십 초 sleep)에 들어가고,
    나머지 **SHORT**들은 짧은 콜(1~2s)을 유지한다.
  * 관측: (a) LONG의 KV가 실제로 CPU tier로 내려가 GPU KV(sglang:num_used_tokens)가 비는가,
          (b) SHORT들은 GPU에 잔류하는가,
          (c) LONG 재개가 reload 경로(prefix cache hit)인가 full prefill인가.

계측 (baseline 코드 무수정 — 전부 읽기 전용 엔드포인트):
  * 프록시 ``/health``: cpu_tier는 노출되지 않으므로 **파생**한다 —
        cpu_tier = programs_count - Σ_url per_backend[url].total - paused_count
    (CPU tier 프로그램은 backend_url=None이라 per_backend에서 빠지고,
     paused_count = len(global_waiting_queue)에는 CPU tier가 안 들어간다. router.py:958-986 근거)
  * SGLang ``/metrics``: num_used_tokens(=GPU KV 사용량), hicache host used,
    load_back_tokens_total(=CPU->GPU reload), cached_tokens_total/prompt_tokens_total(=prefix hit).
    **nvidia-smi memory로는 HBM 해제를 볼 수 없다** — SGLang이 KV 풀을 정적 선점하기 때문
    (기존 M-SWP 로그에서 mem이 27.7GB로 상수인 것으로 확인). 그래서 num_used_tokens를 쓴다.
  * 프록시 로그의 ``MORI demote/promote`` 라인은 별도로 대조한다.

산출: --out 접두사로 <out>_samples.csv (시계열), <out>_turns.jsonl (턴별), <out>_summary.json
"""
import argparse
import asyncio
import json
import os
import re
import subprocess
import time
import urllib.request

import httpx

# ---------------------------------------------------------------------------
# 계측 유틸
# ---------------------------------------------------------------------------

_METRIC_RE_CACHE = {}


def _metric(body: str, name: str):
    rx = _METRIC_RE_CACHE.get(name)
    if rx is None:
        rx = re.compile(r"^" + re.escape(name) + r"(?:\{[^}]*\})?\s+([0-9.eE+-]+)", re.M)
        _METRIC_RE_CACHE[name] = rx
    vals = [float(v) for v in rx.findall(body)]
    return sum(vals) if vals else None


ENGINE_METRICS = [
    "sglang:num_used_tokens",
    "sglang:token_usage",
    "sglang:cache_hit_rate",
    "sglang:hicache_host_used_tokens",
    "sglang:load_back_tokens_total",
    "sglang:evicted_tokens_total",
    "sglang:cached_tokens_total",
    "sglang:prompt_tokens_total",
    "sglang:num_running_reqs",
]


def fetch_engine(backend_url: str, timeout=3):
    try:
        with urllib.request.urlopen(backend_url.rstrip("/") + "/metrics", timeout=timeout) as r:
            body = r.read().decode()
    except Exception:
        return {}
    return {k: _metric(body, k) for k in ENGINE_METRICS}


def fetch_health(proxy_url: str, timeout=3):
    try:
        with urllib.request.urlopen(proxy_url.rstrip("/") + "/health", timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def derive_tiers(health: dict):
    """(gpu_resident, cpu_tier, waiting, total) — cpu_tier는 파생값 (docstring 참조)."""
    if not health:
        return (None, None, None, None)
    total = health.get("programs_count") or 0
    waiting = health.get("paused_count") or 0
    gpu = sum((d or {}).get("total", 0) for d in (health.get("per_backend") or {}).values())
    return (gpu, total - gpu - waiting, waiting, total)


def gpu_smi(gpus="0,1"):
    try:
        out = subprocess.run(
            ["nvidia-smi", f"--id={gpus}", "--query-gpu=utilization.gpu,memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=8).stdout
        rows = [[int(float(x)) for x in l.split(",")] for l in out.strip().splitlines()]
        return rows
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 워크로드
# ---------------------------------------------------------------------------

FILLER_WORD = "telemetry "


def make_system_prompt(pid: str, approx_tokens: int) -> str:
    """프로그램마다 **고유한** 접두사 — 프로그램 간 prefix 공유로 캐시 히트가 부풀지 않게 한다."""
    uniq = f"[session {pid} seed {abs(hash(pid)) % 10**9}] "
    # Qwen 계열에서 'telemetry '는 대략 2 토큰. 넉넉히 잡고 실제 토큰수는 usage로 관측한다.
    return uniq + FILLER_WORD * max(1, approx_tokens // 2)


class Program:
    # 대화를 슬라이딩 윈도우로 잘라 **컨텍스트 길이를 대략 일정하게** 유지한다.
    # (그러지 않으면 턴마다 컨텍스트가 자라 GPU 압박이 시간에 따라 표류하고,
    #  "얼마나 압박을 줬는지"를 통제할 수 없다 — 1·2차 run에서 실측한 문제)
    KEEP_MSGS = 4

    def __init__(self, pid: str, role: str, sys_tokens: int, max_tokens: int, release_at=None):
        self.pid = pid
        self.role = role                      # "LONG" | "SHORT"
        self.system = {"role": "system", "content": make_system_prompt(pid, sys_tokens)}
        self.messages = [self.system]
        self.max_tokens = max_tokens
        self.release_at = release_at          # 초; None이면 끝까지 실행
        self.released = False
        self.turns = []

    def _trim(self):
        if len(self.messages) > 1 + self.KEEP_MSGS:
            self.messages = [self.system] + self.messages[-self.KEEP_MSGS:]

    async def one_turn(self, client, base_url, model, t0, phase):
        self._trim()
        self.messages.append({"role": "user", "content":
                              f"Reply with exactly one short sentence. turn={len(self.turns)+1}"})
        payload = {
            "model": model,
            "messages": self.messages,
            "max_tokens": self.max_tokens,
            "temperature": 0.0,
            "program_id": self.pid,
        }
        t_req = time.time()
        try:
            r = await client.post(base_url.rstrip("/") + "/v1/chat/completions",
                                  json=payload, timeout=600.0)
            r.raise_for_status()
            d = r.json()
        except Exception as e:
            rec = {"pid": self.pid, "role": self.role, "phase": phase,
                   "t": round(t_req - t0, 2), "error": repr(e)[:200]}
            self.turns.append(rec)
            return rec
        lat = time.time() - t_req
        usage = d.get("usage") or {}
        msg = (d.get("choices") or [{}])[0].get("message", {}) or {}
        self.messages.append({"role": "assistant", "content": msg.get("content", "") or "."})
        rec = {
            "pid": self.pid, "role": self.role, "phase": phase,
            "turn": len(self.turns) + 1,
            "t": round(t_req - t0, 2), "latency_s": round(lat, 3),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            # SGLang은 usage에 캐시 적중 프리필 토큰을 실어주기도 한다 (버전 의존)
            "cached_tokens": ((usage.get("prompt_tokens_details") or {}) or {}).get("cached_tokens"),
        }
        self.turns.append(rec)
        return rec


async def release(client, router_url, pid):
    try:
        await client.post(router_url.rstrip("/") + "/release",
                          json={"program_id": pid}, timeout=30.0)
        return True
    except Exception:
        return False


async def run_program(prog, client, args, t0, sampler_state):
    """warm -> (LONG만) 긴 툴콜 1회 -> 재개 -> 마무리.

    SHORT 중 일부는 ``--release-at-s``에 스스로 종료(/release)한다. 실제 trace에서는
    프로그램이 완료되며 GPU 용량이 회전하는데, 무한 루프 프로브에는 그 회전이 없어
    CPU tier 프로그램이 영구 기아 상태가 된다(1차 run에서 실측). 완료를 모사해
    "긴 콜 종료 시점에 자리가 나는" 현실적 조건을 만든다.
    """
    # --- phase warm: 모두 짧은 콜로 컨텍스트를 만들고 GPU에 자리잡는다 ---
    while time.time() - t0 < args.warm_s:
        await prog.one_turn(client, args.base_url, args.model, t0, "warm")
        await asyncio.sleep(args.short_s)

    if prog.role == "LONG":
        sampler_state["long_call_start"] = time.time() - t0
        print(f"[probe] t={time.time()-t0:6.1f}s  {prog.pid}: 긴 tool call 진입 ({args.long_s}s)",
              flush=True)
        await asyncio.sleep(args.long_s)          # 긴 tool call (스케줄러가 보기엔 ACTING)
        sampler_state["long_call_end"] = time.time() - t0
        print(f"[probe] t={time.time()-t0:6.1f}s  {prog.pid}: 긴 콜 종료 -> 재개 요청", flush=True)
        rec = await prog.one_turn(client, args.base_url, args.model, t0, "resume")
        sampler_state["resume_rec"] = rec
        sampler_state["resume_done_s"] = time.time() - t0
        print(f"[probe] t={time.time()-t0:6.1f}s  {prog.pid}: 재개 완료 latency={rec.get('latency_s')}s "
              f"prompt_tokens={rec.get('prompt_tokens')} cached={rec.get('cached_tokens')}", flush=True)
        end = time.time() + args.tail_s
        while time.time() < end:
            await prog.one_turn(client, args.base_url, args.model, t0, "tail")
            await asyncio.sleep(args.short_s)
        return

    # SHORT: 긴 콜 동안 압박을 유지한다. release는 별도 releaser 태스크가 담당한다
    # (턴이 블록되면 루프 안의 release 체크가 영원히 안 돌기 때문 — 2차 run에서 실측).
    while time.time() - t0 < args.warm_s + args.long_s + args.tail_s:
        if prog.released:
            return
        await prog.one_turn(client, args.base_url, args.model, t0, "probe")
        await asyncio.sleep(args.short_s)


async def releaser(progs, client, args, t0, sampler_state):
    """프로그램 완료(=/release)를 **독립 태스크**로 예약한다. 프로그램 루프가 블록돼도
    정확한 시각에 GPU 용량이 회전한다 (실제 trace에서 프로그램이 끝나는 상황의 모사)."""
    targets = [p for p in progs if p.release_at is not None]
    if not targets:
        return
    delay = max(0.0, targets[0].release_at - (time.time() - t0))
    await asyncio.sleep(delay)
    for p in targets:
        p.released = True
        ok = await release(client, args.router_url, p.pid)
        sampler_state.setdefault("released", []).append(
            {"pid": p.pid, "t": round(time.time() - t0, 1), "ok": ok})
        print(f"[probe] t={time.time()-t0:6.1f}s  {p.pid}: 완료/release (ok={ok}) -> GPU 용량 회전",
              flush=True)


async def sampler(args, t0, stop, rows, sampler_state, writer=None, fh=None):
    """샘플을 **즉시 디스크로 흘려보낸다** — 프로브가 멈추거나 kill돼도 데이터가 남게
    (1차 run에서 교착으로 메모리 상 샘플을 통째로 잃은 뒤 추가한 안전장치)."""
    while not stop.is_set():
        h = fetch_health(args.router_url)
        gpu_r, cpu_t, wait, total = derive_tiers(h)
        e = fetch_engine(args.backend)
        smi = gpu_smi(args.gpus)
        pb = (h or {}).get("per_backend") or {}
        first = next(iter(pb.values()), {}) if pb else {}
        row = {
            "t": round(time.time() - t0, 2),
            "gpu_resident": gpu_r, "cpu_tier": cpu_t, "waiting": wait, "total": total,
            "reasoning": (h or {}).get("reasoning_count"),
            "acting": (h or {}).get("acting_count"),
            "marked": first.get("marked_for_pause"),
            "num_used_tokens": e.get("sglang:num_used_tokens"),
            "token_usage": e.get("sglang:token_usage"),
            "num_running_reqs": e.get("sglang:num_running_reqs"),
            "hicache_host_used": e.get("sglang:hicache_host_used_tokens"),
            "load_back_total": e.get("sglang:load_back_tokens_total"),
            "evicted_total": e.get("sglang:evicted_tokens_total"),
            "cached_total": e.get("sglang:cached_tokens_total"),
            "prompt_total": e.get("sglang:prompt_tokens_total"),
            "gpu0_util": smi[0][0] if len(smi) > 0 else None,
            "gpu0_mem": smi[0][1] if len(smi) > 0 else None,
            "gpu1_util": smi[1][0] if len(smi) > 1 else None,
        }
        rows.append(row)
        if writer is not None:
            writer.writerow(row)
            fh.flush()
        try:
            await asyncio.wait_for(stop.wait(), timeout=args.interval)
        except asyncio.TimeoutError:
            pass


SAMPLE_COLS = [
    "t", "gpu_resident", "cpu_tier", "waiting", "total", "reasoning", "acting", "marked",
    "num_used_tokens", "token_usage", "num_running_reqs", "hicache_host_used",
    "load_back_total", "evicted_total", "cached_total", "prompt_total",
    "gpu0_util", "gpu0_mem", "gpu1_util",
]


async def amain(args):
    import csv
    # release 시각: 긴 콜이 끝나기 --release-before-s 전에 SHORT 앞쪽 --release-n 개가 완료.
    rel_t = args.warm_s + args.long_s - args.release_before_s
    progs = [Program("b1-LONG", "LONG", args.long_sys_tokens or args.sys_tokens, args.max_tokens)]
    for i in range(args.n_short):
        progs.append(Program(f"b1-SHORT{i+1}", "SHORT", args.sys_tokens, args.max_tokens,
                             release_at=(rel_t if i < args.release_n else None)))
    print(f"[probe] 프로그램 {len(progs)}개 (LONG 1 + SHORT {args.n_short}), "
          f"system prompt ~{args.sys_tokens} tok, warm={args.warm_s}s long={args.long_s}s "
          f"tail={args.tail_s}s, SHORT {args.release_n}개가 t={rel_t}s에 완료, "
          f"hard deadline={args.deadline_s}s", flush=True)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    fh = open(args.out + "_samples.csv", "w", newline="")
    writer = csv.DictWriter(fh, fieldnames=SAMPLE_COLS)
    writer.writeheader()
    fh.flush()

    t0 = time.time()
    rows, sampler_state, stop = [], {}, asyncio.Event()
    async with httpx.AsyncClient(timeout=args.turn_timeout_s,
                                 limits=httpx.Limits(max_connections=None)) as client:
        stask = asyncio.create_task(sampler(args, t0, stop, rows, sampler_state, writer, fh))
        rtask = asyncio.create_task(releaser(progs, client, args, t0, sampler_state))
        work = asyncio.gather(*[run_program(p, client, args, t0, sampler_state) for p in progs],
                              return_exceptions=True)
        try:
            await asyncio.wait_for(work, timeout=args.deadline_s)
        except asyncio.TimeoutError:
            sampler_state["deadline_hit"] = True
            print(f"[probe] !! hard deadline {args.deadline_s}s 도달 — 남은 작업 취소하고 "
                  f"수집된 데이터를 기록한다 (진행 중 턴이 블록됐을 수 있음)", flush=True)
            work.cancel()
            try:
                await work
            # CancelledError는 BaseException 상속이라 `except Exception`으로는 안 잡힌다
            # (2차 run에서 summary/turns 기록이 통째로 누락된 원인).
            except (Exception, asyncio.CancelledError):
                pass
        rtask.cancel()
        try:
            await rtask
        except (Exception, asyncio.CancelledError):
            pass
        stop.set()
        await stask
        for p in progs:                       # 정리 (라우터 상태 누수 방지)
            await release(client, args.router_url, p.pid)
    fh.close()

    with open(args.out + "_turns.jsonl", "w") as f:
        for p in progs:
            for r in p.turns:
                f.write(json.dumps(r) + "\n")
    summary = {
        "args": vars(args),
        "long_call_start_s": sampler_state.get("long_call_start"),
        "long_call_end_s": sampler_state.get("long_call_end"),
        "resume_rec": sampler_state.get("resume_rec"),
        "resume_done_s": sampler_state.get("resume_done_s"),
        "released": sampler_state.get("released", []),
        "deadline_hit": bool(sampler_state.get("deadline_hit")),
        "n_samples": len(rows),
        "programs": [{"pid": p.pid, "role": p.role, "turns": len(p.turns),
                      "last_total_tokens": (p.turns[-1].get("total_tokens") if p.turns else None)}
                     for p in progs],
    }
    with open(args.out + "_summary.json", "w") as f:
        json.dump(summary, f, indent=1)
    print(f"[probe] wrote {args.out}_samples.csv / _turns.jsonl / _summary.json  ({len(rows)} samples)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:9000")
    ap.add_argument("--router-url", default="http://localhost:9000")
    ap.add_argument("--backend", default="http://localhost:8123")
    ap.add_argument("--model", default="Qwen/Qwen3-8B")
    ap.add_argument("--gpus", default="0,1")
    ap.add_argument("--n-short", type=int, default=5, help="SHORT 프로그램 수 (= GPU 압박 노브)")
    ap.add_argument("--sys-tokens", type=int, default=6000, help="SHORT의 system prompt 대략 토큰")
    ap.add_argument("--long-sys-tokens", type=int, default=0,
                    help="LONG의 system prompt 토큰 (0이면 --sys-tokens와 동일). "
                         "LONG을 더 크게 잡으면 'LONG 하나만 내리면 용량 해소'인 깨끗한 조건이 된다")
    ap.add_argument("--max-tokens", type=int, default=24, help="턴당 생성 토큰 (짧게 = 빠른 사이클)")
    ap.add_argument("--short-s", type=float, default=1.0, help="SHORT의 tool call 길이")
    ap.add_argument("--long-s", type=float, default=90.0, help="LONG의 긴 tool call 길이")
    ap.add_argument("--warm-s", type=float, default=90.0)
    ap.add_argument("--tail-s", type=float, default=30.0)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--release-n", type=int, default=2,
                    help="긴 콜 종료 직전에 완료(release)시킬 SHORT 개수 (GPU 용량 회전 모사)")
    ap.add_argument("--release-before-s", type=float, default=20.0,
                    help="긴 콜 종료 몇 초 전에 완료시킬지")
    ap.add_argument("--turn-timeout-s", type=float, default=180.0,
                    help="턴당 HTTP 타임아웃 (블록된 재개가 영구 대기하지 않게)")
    ap.add_argument("--deadline-s", type=float, default=420.0,
                    help="전체 하드 데드라인 — 초과 시 취소하고 수집분을 기록")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
