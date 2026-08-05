#!/usr/bin/env python3
"""STEP 6 B0/B2/B3 — 기존 M-SWP 로그 채굴 (읽기 전용, GPU/엔진 불필요).

입력 (전부 기존 산출물, 수정하지 않음):
  <msw>/results_msw.jsonl, results_msw_lowc.jsonl   턴/처리량/hicache 카운터
  <msw>/gpu_<tag>.jsonl                             GPU util·mem 시계열 (CSV, 헤더 있음)
  <msw>/proxy_<tag>.log                             MORI demote/promote/evict 이벤트

출력: 표 3개 (per-cell 요약 / GPU util / MORI tier 이동) + --json 덤프.

주의 (해석에 필수):
  * ``hicache_extra``의 sglang 카운터는 **백엔드 부팅 이후 누적값**이다 (드라이버가 델타를
    안 남긴다: mori_replay_driver_yunuikang.py:367 `_agg(m_after, k)`). 같은 백엔드 부팅을
    공유하는 셀들 사이에서 차분해야 셀별 값이 된다. 누적값이 감소하면 재부팅 경계로 본다.
  * GPU **memory**로는 KV 해제를 볼 수 없다 — SGLang이 KV 풀을 정적 선점하므로 mem은 상수다.
    (아래 표의 mem 열이 모든 셀에서 ~27.7GB인 것이 그 증거.)
"""
import argparse
import csv
import glob
import json
import os
import re
import statistics as st

CUM = ["sglang:load_back_tokens_total", "sglang:evicted_tokens_total",
       "sglang:cached_tokens_total", "sglang:prompt_tokens_total",
       "sglang:generation_tokens_total"]


def load_cells(msw):
    cells = []
    for f in ("results_msw.jsonl", "results_msw_lowc.jsonl"):
        p = os.path.join(msw, f)
        if not os.path.exists(p):
            continue
        for i, line in enumerate(open(p)):
            if line.strip():
                d = json.loads(line)
                d["_src"] = f
                d["_ord"] = i
                cells.append(d)
    return cells


def num(v, d=0.0):
    return d if v is None else v


def per_cell_deltas(cells):
    """같은 (system, hicache_ratio, 소스파일) 그룹 안에서 누적 카운터를 차분한다.

    그룹은 파일 내 등장 순서 = 실행 순서. 누적값이 감소하면 백엔드 재부팅으로 보고 리셋.
    """
    groups = {}
    for c in cells:
        groups.setdefault((c["_src"], c["system"], c.get("hicache_ratio")), []).append(c)
    for key, gs in groups.items():
        gs.sort(key=lambda x: x["_ord"])
        prev = {k: 0.0 for k in CUM}
        for c in gs:
            h = (c.get("sglang_metrics") or {}).get("hicache_extra") or {}
            delta, reset = {}, False
            for k in CUM:
                cur = num(h.get(k))
                if cur < prev[k]:          # 카운터 감소 = 재부팅
                    reset = True
                    prev[k] = 0.0
                delta[k] = cur - prev[k]
                prev[k] = cur
            c["_delta"] = delta
            c["_reset"] = reset


def gpu_stats(path, warm_frac=0.2):
    try:
        rows = list(csv.DictReader(open(path)))
    except Exception:
        return None
    if not rows:
        return None
    tmax = max(float(r["t"]) for r in rows)
    rows = [r for r in rows if float(r["t"]) > warm_frac * tmax]
    out = {}
    for col in ("gpu0_util", "gpu1_util", "gpu0_mem"):
        vals = [int(r[col]) for r in rows if r.get(col) not in (None, "", "None")]
        if not vals:
            continue
        vs = sorted(vals)
        out[col] = {"mean": st.mean(vals), "p50": st.median(vals),
                    "p95": vs[max(0, int(0.95 * len(vs)) - 1)],
                    "busy_pct": 100.0 * sum(1 for x in vals if x > 0) / len(vals),
                    "n": len(vals)}
    return out


def tier_moves(msw, tag):
    p = os.path.join(msw, f"proxy_{tag}.log")
    if not os.path.exists(p):
        return None
    body = open(p, "rb").read().decode("utf-8", "replace")
    return {
        "demote_gpu_to_cpu": len(re.findall(r"MORI demote GPU->CPU", body)),
        "promote_cpu_to_gpu": len(re.findall(r"MORI promote CPU->GPU", body)),
        "evict_cpu_to_waiting": len(re.findall(r"MORI evict CPU->Waiting", body)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--msw", default="/home/yunuikang/yunuikang_work/scratch/mori/msw")
    ap.add_argument("--json", help="요약 JSON 덤프 경로")
    args = ap.parse_args()

    cells = load_cells(args.msw)
    per_cell_deltas(cells)

    print("=" * 118)
    print("[B0-1] per-cell 요약  (hicache 카운터는 **셀별 델타**; hit = cached/prompt 델타 비)")
    print("=" * 118)
    hdr = ("%-16s %-5s %3s %2s %9s %8s %8s %8s | %6s %10s %10s %10s" %
           ("cell", "sys", "C", "r", "thr_tok/s", "step_r/s", "ttft_p50", "ttft_p95",
            "hit", "load_back", "evicted", "prompt"))
    print(hdr)
    print("-" * len(hdr))
    out_cells = []
    for c in sorted(cells, key=lambda x: (x["system"], num(x.get("hicache_ratio")), x["concurrency"])):
        d = c["_delta"]
        pt, ct = d["sglang:prompt_tokens_total"], d["sglang:cached_tokens_total"]
        hit = ct / pt if pt else 0.0
        print("%-16s %-5s %3d %2g %9.1f %8.3f %8.2f %8.2f | %6.3f %9.2fM %9.2fM %9.2fM%s" % (
            c["run_tag"], c["system"], c["concurrency"], num(c.get("hicache_ratio")),
            num(c.get("output_throughput_tok_s")), num(c.get("step_throughput_req_s")),
            num(c.get("ttft_p50_s")), num(c.get("ttft_p95_s")), hit,
            d["sglang:load_back_tokens_total"] / 1e6, d["sglang:evicted_tokens_total"] / 1e6,
            pt / 1e6, "  <reset>" if c["_reset"] else ""))
        out_cells.append({"tag": c["run_tag"], "system": c["system"], "C": c["concurrency"],
                          "ratio": c.get("hicache_ratio"),
                          "thr_tok_s": c.get("output_throughput_tok_s"),
                          "ttft_p50_s": c.get("ttft_p50_s"), "hit": hit,
                          "load_back_M": d["sglang:load_back_tokens_total"] / 1e6})

    print()
    print("=" * 118)
    print("[B2] GPU util (steady 구간 = 후반 80%).  mem이 상수인 것에 주목 — KV 풀 정적 선점")
    print("=" * 118)
    hdr2 = "%-16s %6s %8s %6s %6s %8s %9s" % ("cell", "n", "u0_mean", "u0_p50", "u0_p95", "busy%", "mem0_GB")
    print(hdr2)
    print("-" * len(hdr2))
    gstats = {}
    for p in sorted(glob.glob(os.path.join(args.msw, "gpu_*.jsonl"))):
        tag = os.path.basename(p)[4:-6]
        s = gpu_stats(p)
        if not s or "gpu0_util" not in s:
            continue
        u, m = s["gpu0_util"], s.get("gpu0_mem", {})
        print("%-16s %6d %8.1f %6.0f %6.0f %8.1f %9.1f" % (
            tag, u["n"], u["mean"], u["p50"], u["p95"], u["busy_pct"], m.get("mean", 0) / 1024))
        gstats[tag] = s

    print()
    print("=" * 118)
    print("[B0-2] MORI tier 이동 (프록시 로그 실측 이벤트)")
    print("=" * 118)
    hdr3 = "%-16s %8s %8s %10s %10s" % ("cell", "demote", "promote", "evictCPU→W", "demote/완료턴")
    print(hdr3)
    print("-" * len(hdr3))
    moves = {}
    for c in sorted(cells, key=lambda x: (num(x.get("hicache_ratio")), x["concurrency"])):
        if c["system"] != "MORI":
            continue
        mv = tier_moves(args.msw, c["run_tag"])
        if mv is None:
            continue
        moves[c["run_tag"]] = mv
        turns = c.get("steady_turns") or 0
        print("%-16s %8d %8d %10d %10s" % (
            c["run_tag"], mv["demote_gpu_to_cpu"], mv["promote_cpu_to_gpu"],
            mv["evict_cpu_to_waiting"],
            f"{mv['demote_gpu_to_cpu']/turns:.3f}" if turns else "n/a"))

    if args.json:
        with open(args.json, "w") as f:
            json.dump({"cells": out_cells, "gpu": gstats, "tier_moves": moves}, f, indent=1)
        print(f"\n[wrote] {args.json}")


if __name__ == "__main__":
    main()
