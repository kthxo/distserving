#!/usr/bin/env python3
"""Phase 2 C=50 pivot 분석 — "CPU 용량(dial②) vs GPU-oversub 스래싱" 판별.

판별 로직 (사전 등록):
  r↑ 로 MORI÷TA+O 상승·>1 교차 + Waiting↓ + ping-pong↓ + pause↓ + hit↑
      → 붕괴 원인 = CPU 용량.  lever = DRAM.
  r↑ 로 Waiting은 0인데 비율 정체(<1) + ping-pong/pause 여전
      → 붕괴 원인 = GPU-oversub 스래싱.  lever = fit(HBM) = H200 필수.

지표 (전부 [측정]):
  [불편함 3종]  엔진 steady-window tok/s · Waiting 축출 · goodput@5s (profile per-step)
  [스래싱 3종]  ping-pong% · prefix cache hit · pause 점유(TTFT 중 pause 비중)
  [참고]        드라이버 throughput (완료-경계 편향 있음, 편향 크기 확인용)
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


def load(d):
    p = os.path.join(d, "results_c50.jsonl")
    out = []
    if not os.path.exists(p):
        return out
    for line in open(p):
        if not line.strip():
            continue
        c = json.loads(line)
        m = re.match(r"(MORI|TAO)_r(\d+)_C(\d+)", c["run_tag"])
        if m:
            c["_sys"], c["_r"], c["_C"] = m.group(1), int(m.group(2)), int(m.group(3))
            out.append(c)
    return out


def engine(d, tag, dur):
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

    def dl(k):
        try:
            return float(w[-1][k]) - float(w[0][k])
        except Exception:
            return None
    gen, pre, cac, lb = (dl(k) for k in ("generation_tokens_total", "prompt_tokens_total",
                                         "cached_tokens_total", "load_back_tokens_total"))
    return {"thr": gen / span if span > 0 else None,
            "hit": cac / pre if (pre and cac is not None) else None,
            "recompute": (pre - cac) / (pre + gen) if (pre and cac is not None and gen is not None) else None,
            "reload_M": lb / 1e6 if lb is not None else None, "span": span}


def profile(d, tag, slo=5.0, dur=3600.0):
    """불편함 goodput + pause 점유(스래싱 지표).

    ⚠️ 시간창은 **고정**한다: [첫 스텝 + WARM×dur, 첫 스텝 + dur].
    파일의 min/max 범위를 쓰면 grace 구간에 끝난 낙오 스텝 몇 개가 창을 통째로 늘려
    goodput이 크게 흔들린다 [측정: TAO_r2_C50 은 4100s·4289s·5050s 낙오로 창이 3640→5050s,
    goodput 22.96 → 14.77 로 요동]. 고정창은 드라이버의 steady 정의와도 일치하고 결정적이다.
    """
    p = os.path.join(d, f"profile_{tag}", "step_profiles.csv")
    try:
        rows = [r for r in csv.DictReader(open(p)) if r.get("completed_at")]
    except Exception:
        return None
    if len(rows) < 10:
        return None
    rows.sort(key=lambda r: float(r["completed_at"]))
    a = float(rows[0]["completed_at"])
    lo, hi = a + WARM * dur, a + dur
    S = [r for r in rows if lo <= float(r["completed_at"]) <= hi]
    if len(S) < 5:
        return None
    wall = dur - WARM * dur          # 고정 (2880s)
    n_late = sum(1 for r in rows if float(r["completed_at"]) > hi)
    pa = [float(r["pause_s"] or 0) for r in S]
    pf = [float(r["prefill_s"] or 0) for r in S]
    tt = [x + y for x, y in zip(pa, pf)]
    ok = [r for r, t in zip(S, tt) if t <= slo]
    tok = lambda rs: sum(int(r["completion_tokens"] or 0) for r in rs)
    return {"goodput": tok(ok) / wall, "sat": 100.0 * len(ok) / len(S),
            "step_thr": tok(S) / wall, "n": len(S), "n_late": n_late,
            "pause_share": 100.0 * sum(pa) / sum(tt) if sum(tt) else 0.0,   # 스래싱 지표
            "pause_nz": 100.0 * sum(1 for x in pa if x > 0.01) / len(pa),
            "pause_p50": st.median(pa), "ttft_p50": st.median(tt)}


def moves(d, tag, sys_name):
    p = os.path.join(d, f"proxy_{tag}.log")
    if not os.path.exists(p):
        return None
    b = open(p, "rb").read().decode("utf-8", "replace")
    if sys_name == "MORI":
        dem = re.findall(r"MORI demote GPU->CPU (\S+)", b)
        ev = len(re.findall(r"MORI evict CPU->Waiting", b))
        kind = "CPU→W"
    else:
        dem = re.findall(r"Paused program (\S+) from", b)
        ev = len(dem)
        kind = "GPU→W"
    return {"demote": len(dem), "evict": ev, "kind": kind,
            "pingpong": (100.0 * sum(1 for v in Counter(dem).values() if v >= 2) / len(set(dem))) if dem else 0.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/home/yunuikang/yunuikang_work/scratch/mori/phase2_c50")
    ap.add_argument("--slo", type=float, default=5.0)
    ap.add_argument("--json")
    args = ap.parse_args()
    CS = load(args.dir)
    if not CS:
        print("결과 없음"); return

    R = {}
    for c in CS:
        t = c["run_tag"]
        e = engine(args.dir, t, c.get("duration_s", 3600)) or {}
        g = profile(args.dir, t, args.slo) or {}
        m = moves(args.dir, t, c["_sys"]) or {}
        R[t] = dict(sys=c["_sys"], r=c["_r"], C=c["_C"],
                    drv=num(c.get("output_throughput_tok_s")),
                    eng=e.get("thr"), hit=e.get("hit"), recompute=e.get("recompute"),
                    reload_M=e.get("reload_M"),
                    gp=g.get("goodput"), sat=g.get("sat"),
                    pause_share=g.get("pause_share"), pause_nz=g.get("pause_nz"),
                    pause_p50=g.get("pause_p50"),
                    evict=m.get("evict"), evict_kind=m.get("kind"),
                    demote=m.get("demote"), pingpong=m.get("pingpong"),
                    ttft_p50=num(c.get("ttft_p50_s")), ttft_p95=num(c.get("ttft_p95_s")),
                    turns=c.get("steady_turns"), fail=c.get("failed_programs"))

    def f(x, n=2, w=8):
        return f"{x:{w}.{n}f}" if isinstance(x, (int, float)) else f"{'-':>{w}}"

    print("=" * 132)
    print(f"Phase 2 C=50 pivot — 셀별 결과   fit={FIT:.2f}  oversub={50/FIT:.2f}x  [측정] 1시간 셀")
    print("=" * 132)
    hd = ("%-15s %-5s %2s | %8s %8s %8s %7s | %7s %7s %8s %9s | %8s" %
          ("cell", "sys", "r", "엔진", "goodput", "만족%", "Wait축출",
           "ping%", "hit", "recomp", "pause점유%", "drv*"))
    print(hd); print("-" * len(hd))
    print("  불편향 3종 = 엔진·goodput·Wait축출  |  스래싱 3종 = ping-pong·hit·pause점유  |  drv* = 편향(참고)")
    print("  Wait축출: MORI=CPU→Waiting / TA+O=GPU→Waiting pause (라우터가 달라 동일 지표 아님)")
    for t in sorted(R, key=lambda k: (R[k]["r"], R[k]["sys"])):
        v = R[t]
        print("%-15s %-5s %2d | %s %s %s %7s | %s %s %s %s | %s" % (
            t, v["sys"], v["r"], f(v["eng"]), f(v["gp"]), f(v["sat"], 1, 8),
            str(v["evict"]) if v["evict"] is not None else "-",
            f(v["pingpong"], 0, 7), f(v["hit"], 3, 7), f(v["recompute"], 3, 8),
            f(v["pause_share"], 1, 9), f(v["drv"])))

    print("\n" + "=" * 132)
    print("★ 판별 — r↑ 에 따른 궤적 (MORI÷TA+O 및 MORI 스래싱 지표)")
    print("=" * 132)
    print("%-4s | %-22s %-22s %-22s | %-9s %-8s %-9s %-9s" % (
        "r", "엔진 M/T", "goodput M/T", "드라이버 M/T(참고)",
        "MORI Wait", "ping%", "hit", "pause점유%"))
    print("-" * 128)
    traj = {}
    for r in (2, 3, 4):
        M = [v for v in R.values() if v["sys"] == "MORI" and v["r"] == r]
        T = [v for v in R.values() if v["sys"] == "TAO" and v["r"] == r]
        if not M or not T:
            continue
        m, t = M[0], T[0]
        rr = lambda k: (m[k] / t[k]) if (m.get(k) and t.get(k)) else None
        e, g, d = rr("eng"), rr("gp"), rr("drv")
        traj[r] = dict(eng=e, gp=g, evict=m["evict"], ping=m["pingpong"],
                       hit=m["hit"], pause=m["pause_share"])
        cel = lambda x, a, b: f"{a:6.2f}/{b:6.2f} = {x:5.2f}x" if x else " " * 22
        print("%-4d | %s %s %s | %9s %8s %9s %9s" % (
            r, cel(e, m.get("eng") or 0, t.get("eng") or 0),
            cel(g, m.get("gp") or 0, t.get("gp") or 0),
            cel(d, m.get("drv") or 0, t.get("drv") or 0),
            m["evict"], f(m["pingpong"], 0, 8), f(m["hit"], 3, 9), f(m["pause_share"], 1, 9)))

    if len(traj) >= 2:
        ks = sorted(traj)
        es = [traj[k]["eng"] for k in ks if traj[k]["eng"]]
        print("\n" + "-" * 132)
        if len(es) >= 2:
            mono = all(a <= b + 1e-9 for a, b in zip(es, es[1:]))
            crossed = es[-1] > 1.0
            dping = traj[ks[-1]]["ping"] - traj[ks[0]]["ping"] if all(traj[k]["ping"] is not None for k in (ks[0], ks[-1])) else None
            dpause = traj[ks[-1]]["pause"] - traj[ks[0]]["pause"] if all(traj[k]["pause"] is not None for k in (ks[0], ks[-1])) else None
            print(f"  엔진 비 궤적: {' → '.join(f'{v:.2f}x' for v in es)}   단조상승 {'예' if mono else '아니오'} · r_max에서 >1 {'예' if crossed else '아니오'}")
            if dping is not None:
                print(f"  MORI ping-pong: {traj[ks[0]]['ping']:.0f}% → {traj[ks[-1]]['ping']:.0f}%  (Δ{dping:+.0f}%p)")
            if dpause is not None:
                print(f"  MORI pause 점유: {traj[ks[0]]['pause']:.1f}% → {traj[ks[-1]]['pause']:.1f}%  (Δ{dpause:+.1f}%p)")
            print()
            if mono and crossed and (dping is None or dping < -5) :
                v = "【CPU 용량 lever】 붕괴 원인 = CPU tier 부족. lever = DRAM. H200은 확증용."
            elif not crossed and (dping is None or abs(dping) < 10):
                v = "【GPU-fit lever】 r을 올려도 구조 안 됨 + 스래싱 여전 → 원인 = GPU-oversub. lever = HBM(fit). H200 필수."
            else:
                v = "【혼합/판정보류】 두 지표군이 같은 방향을 안 가리킴 — 셀별 값을 직접 확인할 것."
            print(f"  => 판별: {v}")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump({"fit": FIT, "C": 50, "cells": R, "traj": traj}, fh, indent=1, ensure_ascii=False)
        print(f"\n[wrote] {args.json}")


if __name__ == "__main__":
    main()
