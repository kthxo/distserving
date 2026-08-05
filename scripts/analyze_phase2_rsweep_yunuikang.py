#!/usr/bin/env python3
"""Phase 2 분석 — r 스윕이 dial ② 가설을 지지하는가.

가설: MORI 붕괴 = GPU+CPU 용량 부족.  C_crit = (1+r) x fit,  fit = GPU pool / ctx_median
판정 3종 (사전 등록):
  1) C=32 고정에서 r↑ → MORI/TA+O 상승, r=4에서 >1 교차
  2) 교차와 동시에 Waiting 축출 >0 → ≈0, prefix hit 회복, recompute↓, ping-pong↓
  3) 붕괴 임계가 (1+r)x8.10 (24.3/32.4/40.5)과 ±20% 내 일치

읽기 전용. 입력: scratch/mori/phase2/{results_phase2.jsonl, proxy_*.log, gpu_*.jsonl}
"""
import argparse
import csv
import glob
import json
import os
import re
import statistics as st
from collections import Counter

PIN, CTXMED = 262144, 32376
FIT = PIN / CTXMED
CUM = ["sglang:load_back_tokens_total", "sglang:evicted_tokens_total",
       "sglang:cached_tokens_total", "sglang:prompt_tokens_total",
       "sglang:generation_tokens_total"]


def num(v, d=0.0):
    return d if v is None else v


def load(d):
    p = os.path.join(d, "results_phase2.jsonl")
    cells = []
    for i, line in enumerate(open(p)):
        if line.strip():
            c = json.loads(line)
            c["_ord"] = i
            m = re.match(r"(MORI|TAO)_r(\d+)_C(\d+)(_rep\d)?", c["run_tag"])
            if m:
                c["_sys"], c["_r"], c["_C"] = m.group(1), int(m.group(2)), int(m.group(3))
                c["_rep"] = m.group(4) or ""
            cells.append(c)
    # 누적 sglang 카운터를 같은 백엔드 부팅 그룹 안에서 차분
    groups = {}
    for c in cells:
        groups.setdefault((c["_sys"], c["_r"]), []).append(c)
    for gs in groups.values():
        gs.sort(key=lambda x: x["_ord"])
        prev = {k: 0.0 for k in CUM}
        for c in gs:
            h = (c.get("sglang_metrics") or {}).get("hicache_extra") or {}
            dd = {}
            for k in CUM:
                cur = num(h.get(k))
                if cur < prev[k]:
                    prev[k] = 0.0
                dd[k] = cur - prev[k]
                prev[k] = cur
            c["_d"] = dd
    return cells


def moves(d, tag, sys_name):
    """tier 이동 이벤트.

    ⚠️ `MORI evict CPU->Waiting` 라인은 MoriRouter에만 있다 → TA+O(tr 라우터)에서는 항상 0이 되어
    "축출 없음"으로 오해된다. tr의 대응 신호는 base `_pause_program`의 "Paused program" 로그
    (= GPU에서 밀려 global_waiting_queue로 감)이므로 시스템별로 다른 것을 센다.
    dial② 판정에 쓰는 것은 **MORI의 evict**이고, TA+O 값은 참고용이다.
    """
    p = os.path.join(d, f"proxy_{tag}.log")
    if not os.path.exists(p):
        return None
    b = open(p, "rb").read().decode("utf-8", "replace")
    if sys_name == "MORI":
        dem = re.findall(r"MORI demote GPU->CPU (\S+)", b)
        return {"demote": len(dem),
                "promote": len(re.findall(r"MORI promote CPU->GPU", b)),
                "evict": len(re.findall(r"MORI evict CPU->Waiting", b)),
                "evict_kind": "CPU→Waiting",
                "pingpong": (100.0 * sum(1 for v in Counter(dem).values() if v >= 2) / len(set(dem)))
                            if dem else 0.0}
    # tr 계열(TA+O): 라우터 CpuTier가 없다. GPU→Waiting pause 를 대응 신호로 센다.
    paused = re.findall(r"Paused program (\S+) from", b)
    return {"demote": len(paused), "promote": len(re.findall(r"Resumed program", b)),
            "evict": len(paused), "evict_kind": "GPU→Waiting(pause)",
            "pingpong": (100.0 * sum(1 for v in Counter(paused).values() if v >= 2) / len(set(paused)))
                        if paused else 0.0}


def util(d, tag, warm=0.2):
    p = os.path.join(d, f"gpu_{tag}.jsonl")
    try:
        rows = list(csv.DictReader(open(p)))
    except Exception:
        return None
    if not rows:
        return None
    tm = max(float(r["t"]) for r in rows)
    rows = [r for r in rows if float(r["t"]) > warm * tm]
    v = [int(r["gpu0_util"]) for r in rows if r.get("gpu0_util") not in (None, "", "None")]
    return round(st.mean(v), 1) if v else None


def band(c, slo):
    """per-turn 미저장 → 순서통계 구간 (STEP7 ③과 동일 규약)."""
    p50, p95 = c.get("ttft_p50_s"), c.get("ttft_p95_s")
    if p50 is None or p95 is None:
        return None
    return (95.0, 100.0) if slo >= p95 else ((50.0, 95.0) if slo >= p50 else (0.0, 50.0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/home/yunuikang/yunuikang_work/scratch/mori/phase2")
    ap.add_argument("--slo", type=float, default=5.0)
    ap.add_argument("--json")
    args = ap.parse_args()
    cells = load(args.dir)
    if not cells:
        print("결과 없음"); return
    by = {c["run_tag"]: c for c in cells}

    print("=" * 118)
    print(f"Phase 2 — r 스윕 셀별 결과   fit={FIT:.2f}  C_crit=(1+r)x{FIT:.2f}   [측정]")
    print("=" * 118)
    h = ("%-18s %-5s %2s %3s %8s %8s %8s %8s | %6s %7s %7s %6s %7s %7s" %
         ("cell", "sys", "r", "C", "oversub", "C_crit", "thr", "ttft_p50",
          "util", "hit", "recomp", "evict*", "pingpg", "goodput"))
    print(h); print("-" * len(h))
    print("  * evict: MORI=CPU→Waiting 축출 / TA+O=GPU→Waiting pause (라우터가 달라 같은 지표가 아님)")
    out = {}
    for c in sorted(cells, key=lambda x: (x["_r"], x["_C"], x["_sys"], x["_ord"])):
        d = c["_d"]; pre = d["sglang:prompt_tokens_total"]; de = d["sglang:generation_tokens_total"]
        cached = d["sglang:cached_tokens_total"]
        hit = cached / pre if pre else 0.0
        recomp = max(0.0, pre - cached) / (de + pre) if (de + pre) else 0.0
        mv = moves(args.dir, c["run_tag"], c["_sys"]) or {}
        thr = num(c.get("output_throughput_tok_s"))
        b = band(c, args.slo)
        gp = f"[{thr*b[0]/100:.1f},{thr*b[1]/100:.1f})" if b else "-"
        crit = (1 + c["_r"]) * FIT
        rec = dict(sys=c["_sys"], r=c["_r"], C=c["_C"], rep=c["_rep"],
                   oversub=c["_C"] / FIT, crit=crit, thr=thr,
                   ttft_p50=num(c.get("ttft_p50_s")), ttft_p95=num(c.get("ttft_p95_s")),
                   util=util(args.dir, c["run_tag"]), hit=hit, recompute=recomp,
                   evict=mv.get("evict"), evict_kind=mv.get("evict_kind"),
                   demote=mv.get("demote"), promote=mv.get("promote"),
                   pingpong=mv.get("pingpong"), steady_turns=c.get("steady_turns"),
                   goodput_band=gp)
        out[c["run_tag"]] = rec
        print("%-18s %-5s %2d %3d %7.2fx %8.1f %8.2f %8.2f | %6s %7.3f %7.3f %6s %7s %7s" % (
            c["run_tag"], c["_sys"], c["_r"], c["_C"], c["_C"] / FIT, crit, thr,
            num(c.get("ttft_p50_s")), rec["util"] if rec["util"] is not None else "-",
            hit, recomp,
            str(mv.get("evict")) if mv else "-",
            f'{mv["pingpong"]:.0f}%' if mv else "-", gp))

    # ---------------- 판정 1: C=32 에서 r↑ → 비율 교차 ----------------
    print("\n" + "=" * 118)
    print("★ 판정 1 — C=32 고정, r 스윕에서 MORI/TA+O 가 1.0을 교차하는가")
    print("=" * 118)
    print("%-4s %9s %10s %10s %9s %9s   %s" %
          ("r", "C_crit", "MORI thr", "TA+O thr", "MORI/TAO", "예측", "판정"))
    print("-" * 78)
    ratios = {}
    for r in (2, 3, 4):
        ms = [v for k, v in out.items() if v["sys"] == "MORI" and v["r"] == r and v["C"] == 32]
        ts = [v for k, v in out.items() if v["sys"] == "TAO" and v["r"] == r and v["C"] == 32]
        if not ms or not ts:
            continue
        mt = st.mean([x["thr"] for x in ms]); tt = st.mean([x["thr"] for x in ts])
        ratio = mt / tt if tt else 0
        ratios[r] = ratio
        crit = (1 + r) * FIT
        pred = "승(>1)" if 32 < crit else "패(<1)"
        got = "승" if ratio > 1.0 else "패"
        ok = "OK" if (32 < crit) == (ratio > 1.0) else "빗나감"
        rep = f" (n={len(ms)})" if len(ms) > 1 else ""
        print("%-4d %9.1f %10.2f %10.2f %9.2fx %9s   %s%s" % (r, crit, mt, tt, ratio, pred, ok, rep))
    if len(ratios) >= 2:
        mono = all(ratios[a] <= ratios[b] for a, b in zip(sorted(ratios), sorted(ratios)[1:]))
        crossed = any(v > 1.0 for v in ratios.values()) and any(v <= 1.0 for v in ratios.values())
        print(f"\n  r↑에 따라 단조 상승: {'예' if mono else '아니오'}   ·   1.0 교차 발생: {'예' if crossed else '아니오'}")
        print(f"  => 판정 1: {'PASS' if (mono and crossed) else 'FAIL'}")

    # ---------------- 판정 2: 교차와 함께 매개변수도 회복 ----------------
    print("\n" + "=" * 118)
    print("★ 판정 2 — 교차와 동시에 Waiting 축출↓ · prefix hit↑ · recompute↓ · ping-pong↓ (MORI, C=32)")
    print("=" * 118)
    print("%-4s %8s %8s %10s %10s %10s" % ("r", "evict", "pingpg", "prefix hit", "recompute", "thr"))
    print("-" * 56)
    for r in (2, 3, 4):
        ms = [v for v in out.values() if v["sys"] == "MORI" and v["r"] == r and v["C"] == 32]
        if not ms:
            continue
        f = lambda k: st.mean([x[k] for x in ms if x[k] is not None]) if any(x[k] is not None for x in ms) else float("nan")
        print("%-4d %8.1f %7.0f%% %10.3f %10.3f %10.2f" % (r, f("evict"), f("pingpong"), f("hit"), f("recompute"), f("thr")))

    # ---------------- 판정 3: 붕괴 임계 위치 ----------------
    print("\n" + "=" * 118)
    print("★ 판정 3 — r=4에서 C를 올릴 때 붕괴 임계가 C_crit=40.5 근처인가 (±20% = 32.4~48.6)")
    print("=" * 118)
    print("%-4s %9s %10s %10s %9s %9s   %s" % ("C", "oversub", "MORI thr", "TA+O thr", "MORI/TAO", "예측", "판정"))
    print("-" * 78)
    crit4 = 5 * FIT
    for C in (32, 40, 48):
        ms = [v for v in out.values() if v["sys"] == "MORI" and v["r"] == 4 and v["C"] == C]
        ts = [v for v in out.values() if v["sys"] == "TAO" and v["r"] == 4 and v["C"] == C]
        if not ms or not ts:
            continue
        mt = st.mean([x["thr"] for x in ms]); tt = st.mean([x["thr"] for x in ts])
        ratio = mt / tt if tt else 0
        pred = "승(>1)" if C < crit4 else "패(<1)"
        ok = "OK" if (C < crit4) == (ratio > 1.0) else "빗나감"
        print("%-4d %8.2fx %10.2f %10.2f %9.2fx %9s   %s" % (C, C / FIT, mt, tt, ratio, pred, ok))

    if args.json:
        with open(args.json, "w") as f:
            json.dump({"fit": FIT, "cells": out, "ratio_C32": ratios}, f, indent=1, ensure_ascii=False)
        print(f"\n[wrote] {args.json}")


if __name__ == "__main__":
    main()
