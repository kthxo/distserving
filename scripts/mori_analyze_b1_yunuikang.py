#!/usr/bin/env python3
"""STEP 6 B1 분석 — 통제 run 산출물에서 (a)(b)(c) 판정.

(a) 긴 툴콜 프로그램의 KV가 실제로 CPU tier로 내려가 GPU KV가 비는가
    -> cpu_tier(파생) 증가 + sglang:num_used_tokens 감소 + hicache_host_used 증가
(b) 짧은 콜 프로그램은 GPU 잔류인가
    -> 긴 콜 구간 내내 gpu_resident >= n_short
(c) 재개가 reload 경로인가 full prefill인가
    -> 재개 턴 전후의 load_back_tokens_total 증가 + cached/prompt 비 + 재개 레이턴시

읽기 전용. 입력: <prefix>_samples.csv, _turns.jsonl, _summary.json, proxy_<tag>.log
"""
import argparse
import csv
import json
import os
import re


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def window(rows, lo, hi):
    return [r for r in rows if lo is not None and hi is not None and lo <= f(r["t"]) <= hi]


def stat(rows, col):
    vs = [f(r[col]) for r in rows if f(r[col]) is not None]
    if not vs:
        return None
    return {"min": min(vs), "max": max(vs), "mean": sum(vs) / len(vs),
            "first": vs[0], "last": vs[-1], "n": len(vs)}


def fmt(s, k="mean", scale=1.0, nd=1):
    return "n/a" if not s else f"{s[k]/scale:.{nd}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", required=True, help="예: /…/scratch/mori/b1/b1_mori")
    ap.add_argument("--proxy-log")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.prefix + "_samples.csv")))
    summ = json.load(open(args.prefix + "_summary.json"))
    turns = [json.loads(l) for l in open(args.prefix + "_turns.jsonl") if l.strip()]
    lo, hi = summ.get("long_call_start_s"), summ.get("long_call_end_s")
    n_short = summ["args"]["n_short"]

    print("=" * 100)
    print(f"[B1] 통제 run: LONG 1 + SHORT {n_short}, 긴 툴콜 구간 t=[{lo}, {hi}]s "
          f"(길이 {(hi-lo) if lo and hi else '?'}s), 샘플 {len(rows)}개")
    print("=" * 100)

    pre = window(rows, max(0, (lo or 0) - 30), lo)          # 긴 콜 직전 30s
    during = window(rows, (lo or 0) + 10, hi)               # 긴 콜 중 (스케줄러 틱 5s x2 여유)
    post = window(rows, hi, (hi or 0) + 30)                 # 재개 직후 30s

    print("\n--- tier 점유 (cpu_tier는 /health 파생: total - Σper_backend.total - paused) ---")
    hdr = "%-10s %8s %8s %8s %8s | %12s %12s %10s" % (
        "구간", "gpu_res", "cpu_tier", "waiting", "total", "num_used_tok", "hicache_host", "gpu0_util")
    print(hdr); print("-" * len(hdr))
    for name, w in (("긴콜 직전", pre), ("긴콜 중", during), ("재개 직후", post)):
        if not w:
            print(f"{name:10s}  (샘플 없음)"); continue
        print("%-10s %8s %8s %8s %8s | %12s %12s %10s" % (
            name,
            fmt(stat(w, "gpu_resident"), nd=2), fmt(stat(w, "cpu_tier"), nd=2),
            fmt(stat(w, "waiting"), nd=2), fmt(stat(w, "total"), nd=2),
            fmt(stat(w, "num_used_tokens"), nd=0), fmt(stat(w, "hicache_host_used"), nd=0),
            fmt(stat(w, "gpu0_util"), nd=1)))

    # (a) CPU tier 최대 점유 + GPU KV 감소
    cmax = stat(during, "cpu_tier")
    nu_pre, nu_dur = stat(pre, "num_used_tokens"), stat(during, "num_used_tokens")
    print("\n--- (a) idle 프로그램이 GPU를 떠나 HBM(KV)이 비는가 ---")
    print(f"  긴 콜 중 cpu_tier 최대 = {fmt(cmax,'max',nd=0)}  (직전 {fmt(stat(pre,'cpu_tier'),'max',nd=0)})")
    if nu_pre and nu_dur:
        print(f"  GPU KV(num_used_tokens): 직전 mean={nu_pre['mean']:.0f} -> 긴콜중 min={nu_dur['min']:.0f} "
              f"(감소폭 {nu_pre['mean']-nu_dur['min']:.0f} tok)")
    hh_pre, hh_dur = stat(pre, "hicache_host_used"), stat(during, "hicache_host_used")
    if hh_pre and hh_dur:
        print(f"  HiCache host used: 직전 mean={hh_pre['mean']:.0f} -> 긴콜중 max={hh_dur['max']:.0f} tok")

    # (b) SHORT 잔류
    print("\n--- (b) busy(짧은 콜) 프로그램은 GPU 잔류인가 ---")
    if during:
        gmin = stat(during, "gpu_resident")["min"]
        print(f"  긴 콜 중 gpu_resident 최소 = {gmin:.0f}  (SHORT {n_short}개가 모두 남아있으면 >= {n_short})")
        print(f"  판정: {'OK' if gmin >= n_short else 'SHORT도 이탈함'}")

    # (c) 재개 경로
    print("\n--- (c) 재개는 reload인가 full recompute인가 ---")
    lb_pre, lb_post = stat(pre, "load_back_total"), stat(post, "load_back_total")
    if lb_pre and lb_post:
        print(f"  load_back_tokens_total(CPU->GPU reload 누적): 긴콜직전 {lb_pre['last']:.0f} "
              f"-> 재개후 {lb_post['last']:.0f}  (증가 {lb_post['last']-lb_pre['last']:.0f} tok)")
    r = summ.get("resume_rec") or {}
    print(f"  재개 턴: latency={r.get('latency_s')}s prompt_tokens={r.get('prompt_tokens')} "
          f"cached_tokens={r.get('cached_tokens')}")
    long_turns = [t for t in turns if t.get("role") == "LONG" and t.get("latency_s")]
    warm_l = [t["latency_s"] for t in long_turns if t.get("phase") == "warm"]
    if warm_l and r.get("latency_s"):
        med = sorted(warm_l)[len(warm_l) // 2]
        print(f"  LONG의 warm 턴 latency 중앙값 = {med:.2f}s -> 재개 턴은 그 {r['latency_s']/med:.2f}배")
    ct_pre, ct_post = stat(pre, "cached_total"), stat(post, "cached_total")
    pt_pre, pt_post = stat(pre, "prompt_total"), stat(post, "prompt_total")
    if ct_pre and ct_post and pt_pre and pt_post:
        dc, dp = ct_post["last"] - ct_pre["last"], pt_post["last"] - pt_pre["last"]
        print(f"  재개 구간 prefix cache hit = {dc:.0f}/{dp:.0f} = {(dc/dp if dp else 0):.3f}")

    # 프록시 로그의 실제 이벤트
    if args.proxy_log and os.path.exists(args.proxy_log):
        body = open(args.proxy_log, "rb").read().decode("utf-8", "replace")
        dem = re.findall(r"MORI demote GPU->CPU (\S+) \(tokens=(\d+)\)", body)
        pro = re.findall(r"MORI promote CPU->GPU (\S+) ->", body)
        ev = re.findall(r"MORI evict CPU->Waiting (\S+)", body)
        print("\n--- 프록시 로그 실제 tier 이동 이벤트 ---")
        print(f"  demote GPU->CPU: {len(dem)}   promote CPU->GPU: {len(pro)}   evict CPU->Waiting: {len(ev)}")
        from collections import Counter
        if dem:
            print(f"  demote된 pid 분포: {dict(Counter(p for p, _ in dem))}")
        if pro:
            print(f"  promote된 pid 분포: {dict(Counter(pro))}")
        if ev:
            print(f"  Waiting으로 축출된 pid: {dict(Counter(ev))}")

    print("\n--- 프로그램별 턴 요약 ---")
    from collections import defaultdict
    by = defaultdict(list)
    for t in turns:
        by[t["pid"]].append(t)
    for pid, ts in sorted(by.items()):
        lats = [t["latency_s"] for t in ts if t.get("latency_s")]
        errs = sum(1 for t in ts if t.get("error"))
        last_tok = next((t.get("total_tokens") for t in reversed(ts) if t.get("total_tokens")), None)
        print(f"  {pid:14s} turns={len(ts):3d} err={errs} last_total_tokens={last_tok} "
              f"lat_med={sorted(lats)[len(lats)//2]:.2f}s" if lats else f"  {pid}: no latency")


if __name__ == "__main__":
    main()
