#!/usr/bin/env python3
"""Phase 2 v2 분석 — dial ② 격리 검증 (1시간 셀 · 불편향 교차지표 병기).

가설: MORI 붕괴 = GPU+CPU 용량 부족.  C_crit = (1+r) x fit,  fit = GPU pool / ctx_median = 8.10
판정 3종 (사전 등록, 결과 보고 바꾸지 않음):
  1) C=32 고정에서 r↑ → MORI/TA+O 상승, r=4에서 >1 교차
  2) 교차와 동시에 Waiting 축출 >0 → ≈0, prefix hit 회복, recompute↓
  3) r=4에서 붕괴 임계가 C_crit=40.5 ±20% (32.4~48.6) 안에 위치

★ 지표 규약 — 드라이버 throughput은 **편향**되어 있다 [측정]:
  드라이버는 완료된 프로그램만 집계한다(mori_replay_driver:300-317). MORI는 설계상 프로그램
  완주 시간을 늘리므로 미완 토큰이 통째로 빠진다. 같은 셀 20분 14.88 → 1시간 25.73 (+72.9%).
  → **판정에는 불편향 지표를 쓰고, 드라이버 값은 편향 크기를 보이기 위해 병기**한다.
    · 엔진 steady-window : engine_<tag>.csv 의 generation_tokens_total 차분 (완료 무관)
    · goodput            : profile_<tag>/step_profiles.csv, pause_s+prefill_s <= SLO (스텝 단위)
    · Waiting 축출       : 프록시 로그 (MORI=CPU→Waiting / TA+O=GPU→Waiting pause)
"""
import argparse
import csv
import json
import os
import re
import statistics as st
from collections import Counter

PIN, CTXMED, WARM = 262144, 32376, 0.2
FIT = PIN / CTXMED


def num(v, d=0.0):
    return d if v is None else v


def cells(d):
    out = []
    p = os.path.join(d, "results_phase2.jsonl")
    if not os.path.exists(p):
        return out
    for line in open(p):
        if not line.strip():
            continue
        c = json.loads(line)
        m = re.match(r"(MORI|TAO)_r(\d+)_C(\d+)", c["run_tag"])
        if not m:
            continue
        c["_sys"], c["_r"], c["_C"] = m.group(1), int(m.group(2)), int(m.group(3))
        out.append(c)
    return out


def engine_steady(d, tag, dur):
    """엔진 steady-window throughput + 캐시 지표 (완료 무관)."""
    p = os.path.join(d, f"engine_{tag}.csv")
    try:
        rows = [r for r in csv.DictReader(open(p)) if r.get("generation_tokens_total")]
    except Exception:
        return None
    if len(rows) < 4:
        return None
    t0 = float(rows[0]["t"])
    w = [r for r in rows if float(r["t"]) >= t0 + WARM * dur]
    if len(w) < 2:
        return None
    span = float(w[-1]["t"]) - float(w[0]["t"])
    if span <= 0:
        return None

    def dl(k):
        try:
            return float(w[-1][k]) - float(w[0][k])
        except Exception:
            return None
    gen, pre, cac, lb = dl("generation_tokens_total"), dl("prompt_tokens_total"), \
        dl("cached_tokens_total"), dl("load_back_tokens_total")
    return {"thr": gen / span, "span": span, "gen": gen,
            "hit": (cac / pre) if (pre and cac is not None) else None,
            "recompute": ((pre - cac) / (pre + gen)) if (pre and cac is not None and gen is not None) else None,
            "reload_M": (lb / 1e6) if lb is not None else None}


def goodput(d, tag, slo=5.0):
    """profile per-step 기반 불편향 goodput."""
    p = os.path.join(d, f"profile_{tag}", "step_profiles.csv")
    try:
        rows = [r for r in csv.DictReader(open(p)) if r.get("completed_at")]
    except Exception:
        return None
    if len(rows) < 10:
        return None
    rows.sort(key=lambda r: float(r["completed_at"]))
    a, b = float(rows[0]["completed_at"]), float(rows[-1]["completed_at"])
    S = [r for r in rows if float(r["completed_at"]) >= a + WARM * (b - a)]
    if len(S) < 5:
        return None
    wall = float(S[-1]["completed_at"]) - float(S[0]["completed_at"])
    if wall <= 0:
        return None
    def tok(rs):
        return sum(int(r["completion_tokens"] or 0) for r in rs)
    ok = [r for r in S if float(r["pause_s"] or 0) + float(r["prefill_s"] or 0) <= slo]
    pa = [float(r["pause_s"] or 0) for r in S]
    return {"step_thr": tok(S) / wall, "goodput": tok(ok) / wall,
            "sat": 100.0 * len(ok) / len(S), "n": len(S),
            "pause_nonzero": 100.0 * sum(1 for x in pa if x > 0.01) / len(pa),
            "pause_p50": st.median(pa)}


def moves(d, tag, sys_name):
    p = os.path.join(d, f"proxy_{tag}.log")
    if not os.path.exists(p):
        return None
    b = open(p, "rb").read().decode("utf-8", "replace")
    if sys_name == "MORI":
        dem = re.findall(r"MORI demote GPU->CPU (\S+)", b)
        return {"demote": len(dem), "promote": len(re.findall(r"MORI promote CPU->GPU", b)),
                "evict": len(re.findall(r"MORI evict CPU->Waiting", b)), "kind": "CPU→W",
                "pingpong": (100.0 * sum(1 for v in Counter(dem).values() if v >= 2) / len(set(dem))) if dem else 0.0}
    pa = re.findall(r"Paused program (\S+) from", b)
    return {"demote": len(pa), "promote": len(re.findall(r"Resumed program", b)),
            "evict": len(pa), "kind": "GPU→W",
            "pingpong": (100.0 * sum(1 for v in Counter(pa).values() if v >= 2) / len(set(pa))) if pa else 0.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/home/yunuikang/yunuikang_work/scratch/mori/phase2")
    ap.add_argument("--slo", type=float, default=5.0)
    ap.add_argument("--json")
    args = ap.parse_args()
    CS = cells(args.dir)
    if not CS:
        print("결과 없음"); return

    rec = {}
    for c in CS:
        tag = c["run_tag"]
        e = engine_steady(args.dir, tag, c.get("duration_s", 3600))
        g = goodput(args.dir, tag, args.slo)
        mv = moves(args.dir, tag, c["_sys"]) or {}
        rec[tag] = dict(sys=c["_sys"], r=c["_r"], C=c["_C"], oversub=c["_C"] / FIT,
                        crit=(1 + c["_r"]) * FIT,
                        drv=num(c.get("output_throughput_tok_s")),
                        eng=e["thr"] if e else None, hit=e["hit"] if e else None,
                        recompute=e["recompute"] if e else None,
                        reload_M=e["reload_M"] if e else None,
                        gp=g["goodput"] if g else None, sat=g["sat"] if g else None,
                        step_thr=g["step_thr"] if g else None,
                        pause_nz=g["pause_nonzero"] if g else None,
                        pause_p50=g["pause_p50"] if g else None,
                        evict=mv.get("evict"), evict_kind=mv.get("kind"),
                        pingpong=mv.get("pingpong"),
                        ttft_p50=num(c.get("ttft_p50_s")), ttft_p95=num(c.get("ttft_p95_s")),
                        turns=c.get("steady_turns"), fail=c.get("failed_programs"))

    def f(x, n=2, w=8):
        return f"{x:{w}.{n}f}" if isinstance(x, (int, float)) else f"{'-':>{w}}"

    print("=" * 128)
    print(f"Phase 2 v2 — 셀별 결과  fit={FIT:.2f}  C_crit=(1+r)x{FIT:.2f}   [측정]  (1시간 셀·반복없음)")
    print("=" * 128)
    hd = ("%-14s %-5s %2s %3s %7s %7s | %8s %8s %8s %7s | %6s %6s %7s %6s %7s" %
          ("cell", "sys", "r", "C", "over", "C_crit", "drv*", "엔진", "goodput", "만족%",
           "evict", "hit", "recomp", "pp%", "pause_nz"))
    print(hd); print("-" * len(hd))
    print("  drv* = 드라이버(완료 프로그램 기준, MORI에 편향) · 엔진/goodput = 불편향")
    for t in sorted(rec, key=lambda k: (rec[k]["r"], rec[k]["C"], rec[k]["sys"])):
        v = rec[t]
        print("%-14s %-5s %2d %3d %6.2fx %7.1f | %s %s %s %s | %6s %s %s %6s %s" % (
            t, v["sys"], v["r"], v["C"], v["oversub"], v["crit"],
            f(v["drv"]), f(v["eng"]), f(v["gp"]), f(v["sat"], 1, 7),
            str(v["evict"]) if v["evict"] is not None else "-",
            f(v["hit"], 3, 6), f(v["recompute"], 3, 7),
            f"{v['pingpong']:.0f}" if v["pingpong"] is not None else "-",
            f(v["pause_nz"], 1, 7)))

    # ---------- 판정 1 ----------
    print("\n" + "=" * 128)
    print("★ 판정 1 — C=32 고정, r 스윕에서 MORI/TA+O 가 1.0을 교차하는가  (불편향 지표 기준)")
    print("=" * 128)
    print("%-4s %8s | %-24s | %-24s | %-24s | %s" %
          ("r", "C_crit", "엔진 M/T", "goodput M/T", "드라이버 M/T (참고)", "예측 / 판정"))
    print("-" * 120)
    ratios = {}
    for r in (2, 3, 4):
        M = [v for v in rec.values() if v["sys"] == "MORI" and v["r"] == r and v["C"] == 32]
        T = [v for v in rec.values() if v["sys"] == "TAO" and v["r"] == r and v["C"] == 32]
        if not M or not T:
            continue
        m, t = M[0], T[0]
        def ratio(k):
            return (m[k] / t[k]) if (m.get(k) and t.get(k)) else None
        re_, rg, rd = ratio("eng"), ratio("gp"), ratio("drv")
        ratios[r] = re_
        crit = (1 + r) * FIT
        pred = "승(>1)" if 32 < crit else "패(<1)"
        ok = "-" if re_ is None else ("OK" if (32 < crit) == (re_ > 1.0) else "빗나감")
        def cell(rr, mm, tt):
            return f"{mm:6.2f}/{tt:6.2f} = {rr:5.2f}x" if rr else " " * 24
        print("%-4d %8.1f | %s | %s | %s | %s / %s" % (
            r, crit, cell(re_, m.get("eng") or 0, t.get("eng") or 0),
            cell(rg, m.get("gp") or 0, t.get("gp") or 0),
            cell(rd, m.get("drv") or 0, t.get("drv") or 0), pred, ok))
    vals = [ratios[k] for k in sorted(ratios) if ratios[k]]
    if len(vals) >= 2:
        mono = all(a <= b for a, b in zip(vals, vals[1:]))
        crossed = any(v > 1.0 for v in vals) and any(v <= 1.0 for v in vals)
        print(f"\n  r↑ 단조 상승: {'예' if mono else '아니오'}  ·  1.0 교차: {'예' if crossed else '아니오'}"
              f"  =>  판정 1: {'PASS' if (mono and crossed) else 'FAIL/보류'}")

    # ---------- 판정 2 ----------
    print("\n" + "=" * 128)
    print("★ 판정 2 — 교차와 동시에 Waiting 축출↓ · prefix hit↑ · recompute↓ (MORI, C=32)")
    print("=" * 128)
    print("%-4s %9s %9s %10s %10s %10s %10s" % ("r", "evict", "pingpong%", "prefix hit", "recompute", "엔진 thr", "goodput"))
    print("-" * 70)
    for r in (2, 3, 4):
        M = [v for v in rec.values() if v["sys"] == "MORI" and v["r"] == r and v["C"] == 32]
        if not M:
            continue
        v = M[0]
        print("%-4d %9s %9s %10s %10s %10s %10s" % (
            r, v["evict"], f"{v['pingpong']:.0f}" if v["pingpong"] is not None else "-",
            f(v["hit"], 3, 9), f(v["recompute"], 3, 9), f(v["eng"], 2, 9), f(v["gp"], 2, 9)))

    # ---------- 판정 3 ----------
    print("\n" + "=" * 128)
    print(f"★ 판정 3 — r=4에서 붕괴 임계가 C_crit={5*FIT:.1f} ±20% ({4*FIT:.1f}~{6*FIT:.1f}) 안인가")
    print("=" * 128)
    print("%-4s %8s %14s %14s %10s %10s %s" % ("C", "oversub", "MORI 엔진", "TA+O 엔진", "M/T", "evict", "예측 / 판정"))
    print("-" * 90)
    crit4 = 5 * FIT
    for C in (32, 40, 48):
        M = [v for v in rec.values() if v["sys"] == "MORI" and v["r"] == 4 and v["C"] == C]
        T = [v for v in rec.values() if v["sys"] == "TAO" and v["r"] == 4 and v["C"] == C]
        if not M or not T:
            continue
        m, t = M[0], T[0]
        rr = (m["eng"] / t["eng"]) if (m.get("eng") and t.get("eng")) else None
        pred = "승(>1)" if C < crit4 else "패(<1)"
        ok = "-" if rr is None else ("OK" if (C < crit4) == (rr > 1.0) else "빗나감")
        print("%-4d %7.2fx %14s %14s %10s %10s %s / %s" % (
            C, C / FIT, f(m.get("eng"), 2, 13), f(t.get("eng"), 2, 13),
            f"{rr:.2f}x" if rr else "-", str(m["evict"]), pred, ok))

    if args.json:
        with open(args.json, "w") as fh:
            json.dump({"fit": FIT, "cells": rec}, fh, indent=1, ensure_ascii=False)
        print(f"\n[wrote] {args.json}")


if __name__ == "__main__":
    main()
