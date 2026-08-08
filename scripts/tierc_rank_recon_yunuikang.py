#!/usr/bin/env python3
"""STEP 1a — _type_rank 분포를 기존 C80 산출물에서 **재구성**한다 (프로브 없이).

근거 (ThunderAgent/scheduler/mori_router.py · mori_idleness.py 소스 그대로):
  * `update_program_before_request` 가 매 요청 직전에
        push_acting(now - last_response_end)      # 직전 툴콜 = acting
    를 넣고, super() (여기서 pause 대기가 일어난다) 를 거친 **뒤**
        payload["priority"] = _type_rank(state, now)
        state.reason_started_at = time.time()
    순서로 스탬프한다. 즉 reasoning 구간은 pause 를 **포함하지 않는다**.
  * `update_program_after_request` 가
        push_reasoning(now - reason_started_at)   # = prefill_s + decode_s
    를 넣는다.
  * ι = Σacting / (Σacting + Σreasoning), 각각 k=5 링버퍼. 샘플이 없으면 default_iota.
  * _type_rank: ι < 0.33 -> 2 · ι < 0.66 -> 1 · else 0.

따라서 step_profiles.csv 의 (tool_call_s, prefill_s, decode_s) 로 스탬프 시점의 ι 를
그대로 재생할 수 있다. [추정] 진행 중 툴콜의 acting_since 항만 재현 불가 —
스탬프 시점엔 직전 acting 이 이미 push 된 뒤라 기여가 작다.
"""
import argparse
import csv
import json
import os
import sys
from collections import defaultdict, deque

K = 5
DEFAULT_IOTA = 0.5


def _f(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def type_rank(iota):
    if iota < 0.33:
        return 2
    if iota < 0.66:
        return 1
    return 0


def replay(csv_path, t_lo=None, t_hi=None):
    rows = list(csv.DictReader(open(csv_path)))
    rows.sort(key=lambda r: _f(r["completed_at"], 0.0))
    by_prog = defaultdict(lambda: {"a": deque(maxlen=K), "r": deque(maxlen=K),
                                   "last_end": None})
    stamps = []
    for r in rows:
        pid = r["program_id"]
        done = _f(r["completed_at"], -1.0)
        st = by_prog[pid]
        # 요청 직전: 직전 응답 종료 이후의 acting(툴콜) 시간을 push
        if st["last_end"] is not None:
            st["a"].append(max(0.0, _f(r["tool_call_s"])))
        # ── 이 시점에 스탬프가 찍힌다
        a, rr = sum(st["a"]), sum(st["r"])
        iota = DEFAULT_IOTA if (a + rr) <= 0.0 else a / (a + rr)
        in_win = (t_lo is None) or (t_lo <= done <= t_hi)
        if in_win:
            stamps.append({
                "pid": pid, "t": done, "iota": iota, "rank": type_rank(iota),
                "n_samples": min(len(st["a"]), len(st["r"])),
                "seeded": (a + rr) > 0.0,
            })
        # 응답 후: reasoning = prefill + decode (pause 제외)
        st["r"].append(max(0.0, _f(r["prefill_s"]) + _f(r["decode_s"])))
        st["last_end"] = done
    return stamps


def summarize(tag, stamps):
    n = len(stamps)
    hist = defaultdict(int)
    for s in stamps:
        hist[s["rank"]] += 1
    distinct = sorted(hist)
    seeded = [s for s in stamps if s["seeded"]]
    iotas = sorted(s["iota"] for s in seeded)

    def q(p):
        if not iotas:
            return float("nan")
        return iotas[min(len(iotas) - 1, int(p * len(iotas)))]

    print(f"\n[{tag}]  스탬프 {n:,}건 (그 중 실측 ι {len(seeded):,}건 · "
          f"default_iota=0.5 로 시작 {n - len(seeded):,}건)")
    print(f"  ★ 실제로 쓰인 distinct rank = {len(distinct)}개  {distinct}")
    for rk in (2, 1, 0):
        c = hist.get(rk, 0)
        bar = "#" * int(round(60 * c / n)) if n else ""
        lab = {2: "busy  (ι<0.33)", 1: "mixed (0.33≤ι<0.66)", 0: "idle  (ι≥0.66)"}[rk]
        print(f"    rank {rk} {lab:22s} {c:6,} ({c/n*100 if n else 0:5.1f}%) {bar}")
    if iotas:
        print(f"  ι 분포(실측만): min={iotas[0]:.4f} p10={q(.10):.4f} p25={q(.25):.4f} "
              f"p50={q(.50):.4f} p75={q(.75):.4f} p90={q(.90):.4f} max={iotas[-1]:.4f}")
        near = sum(1 for v in iotas if v < 0.02)
        print(f"  ι < 0.02 인 비율 = {near/len(iotas)*100:.1f}%  "
              f"(ι 가 0 근처로 뭉치면 지표 문제, 퍼지는데 rank 만 뭉치면 버킷 문제)")
    return {"tag": tag, "n": n, "distinct_ranks": distinct,
            "hist": {str(k): v for k, v in sorted(hist.items())},
            "iota_p50": q(.50) if iotas else None,
            "iota_p90": q(.90) if iotas else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="scratch/mori/tierc_h200")
    ap.add_argument("--tags", nargs="*", default=["MORI_C80"])
    ap.add_argument("--window", action="store_true", help="분석 창으로 제한")
    a = ap.parse_args()
    out = []
    for tag in a.tags:
        csv_path = os.path.join(a.dir, f"profile_{tag}", "step_profiles.csv")
        if not os.path.exists(csv_path):
            print(f"[{tag}] step_profiles.csv 없음 — 건너뜀", file=sys.stderr)
            continue
        lo = hi = None
        wj = os.path.join(a.dir, f"window_{tag}.json")
        if a.window and os.path.exists(wj):
            w = json.load(open(wj))
            lo = w["t_start"] + w["warm"] * (w["t_end"] - w["t_start"])
            hi = w["t_end"]
        out.append(summarize(tag, replay(csv_path, lo, hi)))
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
