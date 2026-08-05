#!/usr/bin/env python3
"""STEP 7 Part A — "유용한 일" 정량화 (①~④). 기존 M-SWP 로그 재집계, GPU 불필요.

개념: decode(출력) = 진짜 산출물 / prefill = 준비 비용 / recompute·왕복 = 낭비.
      goodput = SLO를 만족한 산출만.

입력 (읽기 전용, 전부 기존 산출물):
  <msw>/results_msw{,_lowc}.jsonl   throughput·ttft 분위수·sglang 카운터
  <msw>/gpu_<tag>.jsonl             util 시계열 1Hz (CSV)
  <msw>/proxy_<tag>.log             MORI tier 이동 이벤트 (순서 보존, 타임스탬프 없음)

⚠️ 데이터 한계 (보고서에 그대로 명시할 것):
  * per-turn 레코드가 **저장되지 않았다**. 드라이버가 trace를 메모리에서 집계하고 요약만 쓴다
    (mori_replay_driver_yunuikang.py:320-345, 433-437). 따라서 **정확한 goodput은 계산 불가**.
    대신 ttft 분위수(p50/p95)로부터 **분포 가정 없는 순서통계 하한/상한**을 낸다 (③).
  * 프록시 로그에 타임스탬프가 없다 → ping-pong의 *시간 간격*은 못 재고, *횟수/순서*만 잰다 (④).
  * util은 nvidia-smi 1Hz 샘플이라 "SM이 하나라도 돌면 100"에 가까운 거친 지표다.
    ①의 분모로 쓰되 절대값이 아니라 **시스템 간 비교**로만 읽어야 한다.
"""
import argparse
import csv
import glob
import json
import os
import re
import statistics as st
from collections import Counter, OrderedDict

CUM = ["sglang:load_back_tokens_total", "sglang:evicted_tokens_total",
       "sglang:cached_tokens_total", "sglang:prompt_tokens_total",
       "sglang:generation_tokens_total"]

ORDER = ["SMG", "TA", "TAO", "MORI"]
CS = [2, 4, 8, 10, 20, 50, 80]
FIT_MEDIAN = 8.1          # M-SWP fit median k -> oversub = C / 8.1


def num(v, d=0.0):
    return d if v is None else v


def load_cells(msw):
    cells = []
    for f in ("results_msw.jsonl", "results_msw_lowc.jsonl"):
        p = os.path.join(msw, f)
        if not os.path.exists(p):
            continue
        for i, line in enumerate(open(p)):
            if line.strip():
                d = json.loads(line)
                d["_src"], d["_ord"] = f, i
                cells.append(d)
    # 같은 (파일, system, ratio) 그룹 = 같은 백엔드 부팅. 누적 카운터를 차분한다.
    groups = {}
    for c in cells:
        groups.setdefault((c["_src"], c["system"], c.get("hicache_ratio")), []).append(c)
    for gs in groups.values():
        gs.sort(key=lambda x: x["_ord"])
        prev = {k: 0.0 for k in CUM}
        for c in gs:
            h = (c.get("sglang_metrics") or {}).get("hicache_extra") or {}
            d = {}
            for k in CUM:
                cur = num(h.get(k))
                if cur < prev[k]:            # 카운터 감소 = 백엔드 재부팅
                    prev[k] = 0.0
                d[k] = cur - prev[k]
                prev[k] = cur
            c["_d"] = d
    return cells


def util_of(msw, tag, warm=0.2):
    p = os.path.join(msw, f"gpu_{tag}.jsonl")
    try:
        rows = list(csv.DictReader(open(p)))
    except Exception:
        return None
    if not rows:
        return None
    tm = max(float(r["t"]) for r in rows)
    rows = [r for r in rows if float(r["t"]) > warm * tm]
    v = [int(r["gpu0_util"]) for r in rows if r.get("gpu0_util") not in (None, "", "None")]
    return st.mean(v) if v else None


def moves_of(msw, tag):
    """프록시 로그의 tier 이동 이벤트를 **순서대로** 뽑는다 (타임스탬프 없음)."""
    p = os.path.join(msw, f"proxy_{tag}.log")
    if not os.path.exists(p):
        return None
    body = open(p, "rb").read().decode("utf-8", "replace")
    seq = []
    for m in re.finditer(r"MORI (demote GPU->CPU|promote CPU->GPU|evict CPU->Waiting) (\S+)", body):
        kind = {"demote GPU->CPU": "D", "promote CPU->GPU": "P", "evict CPU->Waiting": "E"}[m.group(1)]
        seq.append((kind, m.group(2)))
    return seq


def pick(cells, system, C):
    """해당 (system, C)의 **대표 셀**.

    hicache ratio r2를 우선한다 (headline 설정이자 low-C 스윕에서 쓴 것). r2가 없으면 r1, r0 순.
    `hicache_ratio` 필드는 드라이버에서 라벨로만 받는데 스윕이 안 넘겨서 전부 0이므로,
    run_tag의 `_r<N>_`로 판별한다. (throughput 최대로 고르면 C별로 r1/r2가 섞여
    STEP 6 보고와 어긋난다 — 그래서 고정한다.)
    """
    cs = [c for c in cells if c["system"] == system and c["concurrency"] == C]
    if not cs:
        return None
    def rank(c):
        m = re.search(r"_r(\d)_", c["run_tag"])
        return -(int(m.group(1)) if m else 0)
    return sorted(cs, key=rank)[0]


def ttft_bound(c, slo):
    """분포 가정 없는 SLO 만족률 구간 [lo, hi] (%) — 순서통계만 사용.

    p50 = 중앙값, p95 = 95분위. SLO가 p95 이상이면 만족률 >= 95%,
    p50 이상 p95 미만이면 [50, 95), p50 미만이면 [0, 50).
    """
    p50, p95 = c.get("ttft_p50_s"), c.get("ttft_p95_s")
    if p50 is None or p95 is None:
        return None
    if slo >= p95:
        return (95.0, 100.0)
    if slo >= p50:
        return (50.0, 95.0)
    return (0.0, 50.0)


def hdr(title):
    print("\n" + "=" * 112)
    print(title)
    print("=" * 112)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--msw", default="/home/yunuikang/yunuikang_work/scratch/mori/msw")
    ap.add_argument("--slo", default="2,5", help="goodput SLO 초 (콤마)")
    ap.add_argument("--json")
    args = ap.parse_args()
    slos = [float(x) for x in args.slo.split(",")]
    cells = load_cells(args.msw)
    out = {}

    # ---------------------------------------------------------------- ①
    hdr("① 생산성 비율 = output_throughput ÷ mean_gpu_util  (\"바쁜 GPU 1초가 만든 유용 토큰\")")
    print("   util은 nvidia-smi 1Hz의 거친 지표 — 절대값이 아니라 같은 C에서의 시스템 간 비교로 읽을 것.\n")
    line = "%-4s %-8s" % ("C", "oversub")
    for s in ORDER:
        line += " | %-22s" % f"{s}: thr / util% / thr÷util"
    print(line)
    print("-" * len(line))
    prod = {}
    for C in CS:
        row = "%-4d %-8s" % (C, f"{C/FIT_MEDIAN:.1f}x")
        for s in ORDER:
            c = pick(cells, s, C)
            if not c:
                row += " | %-22s" % "-"
                continue
            u = util_of(args.msw, c["run_tag"])
            thr = num(c.get("output_throughput_tok_s"))
            if not u:
                row += " | %-22s" % "-"
                continue
            p = thr / (u / 100.0)
            prod[(s, C)] = p
            row += " | %-22s" % f"{thr:5.1f} /{u:5.1f} / {p:6.1f}"
        print(row)
    out["productivity"] = {f"{s}_C{C}": v for (s, C), v in prod.items()}

    # ---------------------------------------------------------------- ②
    hdr("② prefill vs decode + prefill 3분해 (GPU캐시히트=공짜 / host reload=쌈 / recompute=낭비)")
    print("   prefill_total = sglang:prompt_tokens_total 델타,  decode = generation_tokens_total 델타")
    print("   recompute = prefill − cached  (캐시에 없어 실제로 다시 계산한 토큰)")
    print("   host_reload = load_back_tokens_total 델타 (cached 중 호스트에서 끌어온 몫)")
    print("   gpu_hit = cached − host_reload  (이미 GPU radix에 있어 공짜)")
    print("   낭비율 = recompute ÷ (decode + prefill)\n")
    h = ("%-15s %-4s %9s %9s %8s | %9s %9s %9s | %7s %7s" %
         ("cell", "C", "decode", "prefill", "dec:pre", "gpu_hit", "reload", "RECOMP", "hit", "낭비율"))
    print(h)
    print("-" * len(h))
    dec = {}
    for s in ORDER:
        for C in CS:
            c = pick(cells, s, C)
            if not c:
                continue
            d = c["_d"]
            pre = d["sglang:prompt_tokens_total"]
            de = d["sglang:generation_tokens_total"]
            cached = d["sglang:cached_tokens_total"]
            reload_ = d["sglang:load_back_tokens_total"]
            recomp = max(0.0, pre - cached)
            gpu_hit = max(0.0, cached - reload_)
            waste = recomp / (de + pre) if (de + pre) else 0.0
            dec[c["run_tag"]] = {"decode": de, "prefill": pre, "recompute": recomp,
                                 "reload": reload_, "gpu_hit": gpu_hit, "waste_frac": waste}
            print("%-15s %-4d %8.2fM %8.2fM %8s | %8.2fM %8.2fM %8.2fM | %7.3f %7.3f" % (
                c["run_tag"], C, de / 1e6, pre / 1e6,
                f"1:{pre/de:.0f}" if de else "-",
                gpu_hit / 1e6, reload_ / 1e6, recomp / 1e6,
                (cached / pre if pre else 0), waste))
    out["decomposition"] = dec

    # ---------------------------------------------------------------- ③
    hdr("③ goodput (SLO 만족 산출만) — ⚠️ per-turn 미저장이라 **순서통계 구간**으로만 산출")
    print("   드라이버가 per-turn ttft를 저장하지 않는다(요약만). 분포 가정을 하지 않고,")
    print("   p50/p95만으로 확실히 말할 수 있는 구간을 낸다. goodput은 만족률×throughput")
    print("   (턴당 출력 토큰이 ttft와 무관하다는 가정 하 — 이 가정은 [추론]).\n")
    h = "%-15s %-4s %8s %8s %9s" % ("cell", "C", "ttft_p50", "ttft_p95", "thr")
    for slo in slos:
        h += " | %-26s" % f"SLO {slo:g}s: 만족률 / goodput"
    print(h)
    print("-" * len(h))
    gp = {}
    for s in ORDER:
        for C in CS:
            c = pick(cells, s, C)
            if not c:
                continue
            thr = num(c.get("output_throughput_tok_s"))
            row = "%-15s %-4d %8.2f %8.2f %9.1f" % (
                c["run_tag"], C, num(c.get("ttft_p50_s")), num(c.get("ttft_p95_s")), thr)
            rec = {}
            for slo in slos:
                b = ttft_bound(c, slo)
                if b is None:
                    row += " | %-26s" % "-"
                    continue
                lo, hi = b
                row += " | %-26s" % (f"[{lo:.0f},{hi:.0f})% / [{thr*lo/100:.1f},{thr*hi/100:.1f})")
                rec[str(slo)] = {"sat_lo": lo, "sat_hi": hi,
                                 "goodput_lo": thr * lo / 100, "goodput_hi": thr * hi / 100}
            gp[c["run_tag"]] = rec
            print(row)
    out["goodput_bounds"] = gp

    # ---------------------------------------------------------------- ④
    hdr("④ thrashing: 승격당 출력 / 이동률 / ping-pong  (MORI 셀만 — tier 이동이 있는 시스템)")
    print("   출력/promote = '한 번 GPU로 올려서 실제로 뽑아낸 출력 토큰'. 낮으면 자리만 옮긴 것.")
    print("   ping-pong = 같은 프로그램이 2회 이상 강등된 비율 (로그 순서 기반; 타임스탬프 없어 간격은 불가).\n")
    h = ("%-15s %-4s %8s %8s %6s %10s %9s %9s %9s" %
         ("cell", "C", "demote", "promote", "evict", "출력tok", "출력/prom", "이동/분", "pingpong%"))
    print(h)
    print("-" * len(h))
    thr_stats = {}
    for C in CS:
        for c in [x for x in cells if x["system"] == "MORI" and x["concurrency"] == C]:
            seq = moves_of(args.msw, c["run_tag"])
            if seq is None:
                continue
            nD = sum(1 for k, _ in seq if k == "D")
            nP = sum(1 for k, _ in seq if k == "P")
            nE = sum(1 for k, _ in seq if k == "E")
            outtok = num(c.get("steady_completion_tokens"))
            wall = num(c.get("steady_wall_s"), 1.0) or 1.0
            dem_counts = Counter(p for k, p in seq if k == "D")
            pp = (100.0 * sum(1 for v in dem_counts.values() if v >= 2) / len(dem_counts)) if dem_counts else 0.0
            thr_stats[c["run_tag"]] = {"demote": nD, "promote": nP, "evict": nE,
                                       "out_per_promote": (outtok / nP) if nP else None,
                                       "moves_per_min": (nD + nP) / wall * 60,
                                       "pingpong_pct": pp,
                                       "unique_demoted_programs": len(dem_counts)}
            print("%-15s %-4d %8d %8d %6d %10.0f %9s %9.2f %9.1f" % (
                c["run_tag"], C, nD, nP, nE, outtok,
                f"{outtok/nP:.0f}" if nP else "n/a", (nD + nP) / wall * 60, pp))
    out["thrash"] = thr_stats

    if args.json:
        with open(args.json, "w") as f:
            json.dump(out, f, indent=1)
        print(f"\n[wrote] {args.json}")


if __name__ == "__main__":
    main()
