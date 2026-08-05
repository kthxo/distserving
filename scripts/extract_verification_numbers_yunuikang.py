#!/usr/bin/env python3
"""검증 덱(S1~S16)에 들어갈 수치를 **로그와 원시 결과에서 직접** 뽑아 확정한다.

원칙: 레퍼런스로 받은 값은 교차확인용일 뿐이고 **로그가 정답**이다.
로그에 없으면 지어내지 않고 TBD로 남긴다.

소스:
  logs/mori_verify_{symbol_audit,policy_results,A2c_baseline,behavior_results,usefulwork}_yunuikang.md
  scratch/mori/msw/results_msw{,_lowc}.jsonl   (raw)
  scratch/mori/msw/gpu_<tag>.jsonl             (util 시계열)
  scratch/mori/prof/…                          (STEP7 Part B)
출력: scratch/mori/deck_numbers.json  +  콘솔 대조표
"""
import csv
import glob
import json
import os
import re
import statistics as st

LOGS = "/home/yunuikang/yunuikang_work/distserving/logs"
MSW = "/home/yunuikang/yunuikang_work/scratch/mori/msw"
PROF = "/home/yunuikang/yunuikang_work/scratch/mori/prof"
OUT = "/home/yunuikang/yunuikang_work/scratch/mori/deck_numbers.json"

TBD = "TBD"


CONSOLIDATED = os.path.join(LOGS, "2026-08-04_MORI_VERIFICATION_yunuikang.md")


def log(name):
    """원본 mori_verify_*.md 를 우선 읽고, 없으면 **통합 보고서**로 폴백한다.

    통합본(2026-08-04_MORI_VERIFICATION)은 원본 5개의 표·수치·file:line 을 전부 포함한다
    (통합 시 참조 45개·수치 351개 누락 0 확인). 원본이 유실돼도 추출이 계속 동작하도록 한다.
    """
    p = os.path.join(LOGS, f"mori_verify_{name}_yunuikang.md")
    if os.path.exists(p):
        return open(p, encoding="utf-8").read()
    if os.path.exists(CONSOLIDATED):
        return open(CONSOLIDATED, encoding="utf-8").read()
    return ""


def grab(txt, pattern, group=1, cast=str, label=""):
    """로그에서 정규식으로 값 1개. 못 찾으면 TBD (지어내지 않음)."""
    m = re.search(pattern, txt)
    if not m:
        print(f"  !! 로그에서 못 찾음 -> TBD : {label or pattern[:50]}")
        return TBD
    try:
        return cast(m.group(group))
    except Exception:
        return TBD


# ---------------------------------------------------------------- raw 재계산
def load_cells():
    cells = []
    for f in ("results_msw.jsonl", "results_msw_lowc.jsonl"):
        p = os.path.join(MSW, f)
        if not os.path.exists(p):
            continue
        for i, line in enumerate(open(p)):
            if line.strip():
                d = json.loads(line)
                d["_src"], d["_ord"] = f, i
                cells.append(d)
    return cells


def pick(cells, system, C):
    """r2 우선(headline), 없으면 r1/r0 — STEP 7과 동일 규칙."""
    cs = [c for c in cells if c["system"] == system and c["concurrency"] == C]
    if not cs:
        return None
    return sorted(cs, key=lambda c: -(int(m.group(1)) if (m := re.search(r"_r(\d)_", c["run_tag"])) else 0))[0]


def util_of(tag, warm=0.2):
    p = os.path.join(MSW, f"gpu_{tag}.jsonl")
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


def moves(tag):
    p = os.path.join(MSW, f"proxy_{tag}.log")
    if not os.path.exists(p):
        return None
    b = open(p, "rb").read().decode("utf-8", "replace")
    return {
        "demote": len(re.findall(r"MORI demote GPU->CPU", b)),
        "promote": len(re.findall(r"MORI promote CPU->GPU", b)),
        "evict": len(re.findall(r"MORI evict CPU->Waiting", b)),
    }


def main():
    D = {}
    sym, pol, a2c, beh, use = (log(n) for n in
                               ("symbol_audit", "policy_results", "A2c_baseline",
                                "behavior_results", "usefulwork"))

    # ---------------- A 계층 ----------------
    print("[A 계층]")
    D["A_total"] = grab(pol, r"현재[:]? (\d+)/(\d+) PASS", 1, int, "A total pass")
    D["A_denom"] = grab(pol, r"현재[:]? (\d+)/(\d+) PASS", 2, int, "A total denom")
    D["A_initial"] = grab(pol, r"최초 검증: (\d+/\d+) PASS", 1, str, "A initial")
    # A5 상대성
    D["A5_gpu2"] = grab(pol, r"GPU \*\*2칸\*\* → gpu=`(\[[^\]]*\])`", 1, str, "A5 gpu2")
    D["A5_gpu3"] = grab(pol, r"GPU \*\*3칸\*\* → gpu=`(\[[^\]]*\])`", 1, str, "A5 gpu3")
    D["A5_boundary"] = grab(pol, r"2칸에서는 (ι≤[\d.]+)까지, 3칸에서는 (ι≤[\d.]+)까지", 0, str, "A5 boundary")
    # A2a
    D["A2a_demoted"] = grab(pol, r"demote된 pid=`(\['B'\])` \(ι=0\.9\)", 1, str, "A2a demoted")
    D["A2a_remaining_before"] = grab(pol, r"틱 전 gpu_remaining=\*\*(-?\d+)\*\*", 1, int, "A2a remaining")
    # A6b 궤적
    m = re.search(r"경과\(s\)→ι: `([^`]+)`", pol)
    D["A6b_traj"] = m.group(1) if m else TBD
    D["A6b_crossover_s"] = grab(pol, r"ι≥0\.5를 넘기는 경과시간 = \*\*(\d+)s\*\*", 1, int, "A6b crossover")
    D["A6a_base"] = grab(pol, r"busy 기준선 ι=\*\*([\d.]+)\*\*", 1, float, "A6a base")
    D["A6a_outlier"] = grab(pol, r"outlier 1회 포함 ι=\*\*([\d.]+)\*\*", 1, float, "A6a outlier")
    D["A6a_idle"] = grab(pol, r"완전 idle ι=\*\*([\d.]+)\*\*", 1, float, "A6a idle")
    D["A6c_traj"] = grab(pol, r"궤적 \(push 0\.\.5\): `(\[[^\]]+\])`", 1, str, "A6c traj")
    # A7c
    D["A7c_before"] = grab(pol, r"축출된 것=`(\['NEW'\])`\*\* ❌", 1, str, "A7c before")
    D["A7c_after"] = grab(pol, r"축출된 것=`(\['OLD'\])`\*\* ✅", 1, str, "A7c after")
    D["A7c_fix_router"] = "mori_router.py:270"
    D["A7c_fix_tier"] = "mori_tier.py:39/53-55/57-59/71-91/93-95"
    # A2c / baseline
    D["A2c_mori_marked"] = grab(a2c, r"`MoriRouter\._mori_pause_until_safe` \| −100 \| \*\*(\d+ / \d+)\*\*", 1, str, "A2c MORI")
    D["A2c_tr_marked"] = grab(a2c, r"`MultiBackendRouter\._pause_until_safe` \| −100 \| \*\*(\d+ / \d+)\*\*", 1, str, "A2c tr")
    D["A2c_verdict"] = "baseline 상속 (비교 중립)"

    # ---------------- B 계층 ----------------
    print("[B 계층]")
    # tier 이동: 로그 표 + 원시 프록시 로그 양쪽에서
    tier_rows = []
    for C in (2, 4, 8, 10, 20, 50, 80):
        tag = f"MORI_r2_C{C}"
        mv = moves(tag)
        m = re.search(rf"\| MORI_r2_C{C} \| [\d.]+× \| \*?\*?(\d+)\*?\*? \| (\d+) \| \*?\*?(\d+)\*?\*? \|", beh)
        from_log = (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
        tier_rows.append({
            "C": C, "oversub": round(C / 8.1, 1),
            "demote": mv["demote"] if mv else TBD,
            "promote": mv["promote"] if mv else TBD,
            "evict": mv["evict"] if mv else TBD,
            "log_matches_raw": (from_log == (mv["demote"], mv["promote"], mv["evict"])) if (mv and from_log) else None,
        })
    D["B_tier_moves"] = tier_rows

    # B1 (a) / (c)
    D["B1a_kv_before"] = grab(beh, r"\*\*(32,589) → 26,331\*\*", 1, str, "B1a kv before")
    D["B1a_kv_after"] = "26,331"
    D["B1a_drop"] = grab(beh, r"토큰으로 ([\d,]+) 감소", 1, str, "B1a drop")
    D["B1a_prog_kv"] = grab(beh, r"b1-LONG \(tokens=(\d+)\)", 1, int, "B1a program kv")
    D["B1c_loadback"] = grab(beh, r"\*\*660 → 13,900 \(\+([\d,]+) tok\)\*\*", 1, str, "B1c loadback delta")
    D["B1b_status"] = "미확정 (압박 과다로 SHORT도 함께 강등 → 분리 실패)"

    # B2: util / throughput  (raw에서 재계산)
    cells = load_cells()
    b2 = []
    for C in (2, 4, 8, 10, 20, 50, 80):
        row = {"C": C, "oversub": round(C / 8.1, 1)}
        for s, key in (("TA", "TA"), ("TAO", "TAO"), ("MORI", "MORI")):
            c = pick(cells, s, C)
            if c:
                row[key] = {"thr": round(c.get("output_throughput_tok_s") or 0, 1),
                            "util": util_of(c["run_tag"]),
                            "ttft_p50": round(c.get("ttft_p50_s") or 0, 2),
                            "ttft_p95": round(c.get("ttft_p95_s") or 0, 2),
                            "tag": c["run_tag"]}
            else:
                row[key] = None
        b2.append(row)
    D["B2"] = b2

    # B3: hit / reload (로그 표에서)
    b3 = []
    for tag in ("TA_r0_C8", "TAO_r2_C8", "MORI_r2_C8", "TA_r0_C10", "TAO_r2_C10",
                "MORI_r2_C10", "MORI_r2_C20", "MORI_r2_C50", "MORI_r2_C80"):
        m = re.search(rf"\| \*?\*?{re.escape(tag)}\*?\*?[^|]*\| [\d.]+× \| ([\d.]+) \| \*?\*?([\d.]+M)\*?\*? \| ([\d.]+M) \| \*?\*?(\d+|n/a)\*?\*? \|", beh)
        b3.append({"tag": tag,
                   "hit": float(m.group(1)) if m else TBD,
                   "reload": m.group(2) if m else TBD,
                   "evicted": m.group(3) if m else TBD,
                   "cpu_to_wait": m.group(4) if m else TBD})
    D["B3"] = b3

    # ---------------- STEP 7 ----------------
    print("[STEP 7]")
    s7 = {}
    # ① 생산성 비율
    prod = {}
    for label, pat in (("C8", r"\| \*\*8\*\* \| \*\*1\.0×\*\* \| — \|(.+)$"),
                       ("C10", r"\| \*\*10\*\* \| \*\*1\.2×\*\* \| — \|(.+)$"),
                       ("C20", r"^\| 20 \| 2\.5× \| 3\.8 /(.+)$"),
                       ("C80", r"\| \*\*80\*\* \| \*\*9\.9×\*\* \|(.+)$")):
        m = re.search(pat, use, re.M)
        if m:
            vals = re.findall(r"\*\*([\d.]+)\*\*", m.group(1))
            prod[label] = vals
    s7["productivity_raw"] = prod
    s7["prod_C8_MORI"] = prod.get("C8", [TBD] * 3)[-1] if prod.get("C8") else TBD
    s7["prod_C10_MORI"] = prod.get("C10", [TBD] * 3)[-1] if prod.get("C10") else TBD
    s7["prod_C80_MORI"] = prod.get("C80", [TBD] * 4)[-1] if prod.get("C80") else TBD
    s7["prod_C80_TAO"] = prod.get("C80", [TBD] * 4)[-2] if prod.get("C80") and len(prod["C80"]) >= 2 else TBD
    s7["prod_C20_MORI"] = prod.get("C20", [TBD] * 4)[-1] if prod.get("C20") else TBD

    # ② 낭비율 / prefill / recompute
    waste = {}
    for tag in ("MORI_r2_C8", "MORI_r2_C10", "MORI_r2_C20", "MORI_r2_C80", "TAO_r2_C80", "TA_r0_C80"):
        m = re.search(rf"\| \*?\*?{re.escape(tag)}\*?\*? \| \*?\*?\d+\*?\*? \| ([\d.]+M) \| ([\d.]+M) \| 1:(\d+) \| ([\d.]+M) \| \*?\*?([\d.]+M)\*?\*? \| \*?\*?([\d.]+M)\*?\*? \| ([\d.]+) \| \*?\*?([\d.]+)\*?\*? \|", use)
        if m:
            waste[tag] = {"decode": m.group(1), "prefill": m.group(2), "dec_pre": f"1:{m.group(3)}",
                          "gpu_hit": m.group(4), "reload": m.group(5), "recompute": m.group(6),
                          "hit": float(m.group(7)), "waste": float(m.group(8))}
        else:
            waste[tag] = TBD
            print(f"  !! ② 파싱 실패 -> TBD : {tag}")
    s7["waste"] = waste

    # ③ goodput 구간
    gp = {}
    for tag in ("MORI_r2_C8", "MORI_r2_C10", "MORI_r2_C20", "MORI_r2_C80", "TAO_r2_C80", "TA_r0_C80"):
        m = re.search(rf"\| \*?\*?{re.escape(tag)}\*?\*? \| \*?\*?\d+\*?\*? \| \*?\*?([\d.]+)\*?\*? \| \*?\*?([\d.]+)\*?\*? \| ([\d.]+) \|(.+)$", use, re.M)
        if m:
            slo5 = [x for x in m.group(4).split("|") if x.strip()][-1].strip()
            gp[tag] = {"ttft_p50": float(m.group(1)), "ttft_p95": float(m.group(2)),
                       "thr": float(m.group(3)), "slo5": slo5.replace("**", "")}
        else:
            gp[tag] = TBD
            print(f"  !! ③ 파싱 실패 -> TBD : {tag}")
    s7["goodput_band"] = gp

    # ④ thrashing
    th = {}
    for tag in ("MORI_r2_C2", "MORI_r2_C4", "MORI_r2_C8", "MORI_r2_C10",
                "MORI_r2_C20", "MORI_r2_C50", "MORI_r2_C80"):
        m = re.search(rf"\| \*?\*?{re.escape(tag)}\*?\*? \| \*?\*?\d+\*?\*? \| [\d.]+× \| (\d+) \| (\d+) \| (\d+) \| ([\d,]+) \| \*?\*?([\d,n/a]+)\*?\*? \| \*?\*?([\d.]+)\*?\*? \| \*?\*?([\d.]+)\*?\*? \|", use)
        if m:
            th[tag] = {"demote": int(m.group(1)), "promote": int(m.group(2)), "evict": int(m.group(3)),
                       "out_tok": m.group(4), "out_per_promote": m.group(5),
                       "moves_min": float(m.group(6)), "pingpong": float(m.group(7))}
        else:
            th[tag] = TBD
            print(f"  !! ④ 파싱 실패 -> TBD : {tag}")
    s7["thrash"] = th

    # ⑤ profile
    prof = {}
    for tag in ("MORI_r2_C10", "MORI_r2_C80", "TAO_r2_C80"):
        m = re.search(rf"\| \*\*{re.escape(tag)}\*\*[^|]*\| ([\d.]+)s \| \*\*([\d.]+)s\*\* \| ([\d.]+)s \| ([\d.]+)s \| ([\d.]+)s \| ([\d.]+)s \| \*?\*?([\d.]+)%\*?\*? \| \*\*([\d.]+)%\*\* \|", use)
        if m:
            prof[tag] = {"ttft_p50": float(m.group(1)), "pause_p50": float(m.group(2)),
                         "prefill_p50": float(m.group(3)), "ttft_p95": float(m.group(4)),
                         "pause_p95": float(m.group(5)), "prefill_p95": float(m.group(6)),
                         "pause_share": float(m.group(7)), "pause_nonzero": float(m.group(8))}
        else:
            prof[tag] = TBD
            print(f"  !! ⑤(b) 파싱 실패 -> TBD : {tag}")
    s7["profile_ttft"] = prof

    gd = {}
    for tag in ("MORI_r2_C10", "MORI_r2_C80", "TAO_r2_C80"):
        m = re.search(rf"\| \*\*{re.escape(tag)}\*\*[^|]*\| ([\d.]+) \| \*?\*?([\d.]+)% / \*?\*?([\d.]+)\*?\*?\*? \| \*?\*?([\d.]+)% / \*?\*?([\d.]+)\*?\*?\*? \|", use)
        if m:
            gd[tag] = {"thr": float(m.group(1)), "slo2_sat": float(m.group(2)), "slo2_gp": float(m.group(3)),
                       "slo5_sat": float(m.group(4)), "slo5_gp": float(m.group(5))}
        else:
            gd[tag] = TBD
            print(f"  !! ⑤(d) 파싱 실패 -> TBD : {tag}")
    s7["profile_goodput"] = gd

    # ⑤(a) 시간 분해
    dec = {}
    for tag in ("MORI_r2_C10", "MORI_r2_C80", "TAO_r2_C80"):
        m = re.search(rf"\| \*\*{re.escape(tag)}\*\*[^|]*\| (\d+) \| ([\d.]+)s \| ([\d.]+)s \| \*\*([\d.]+)%\*\* \| ([\d.]+)% \| \*\*([\d.]+)s\*\* \| \*\*([\d.]+)s\*\* \|", use)
        if m:
            dec[tag] = {"steps": int(m.group(1)), "prefill_sum": float(m.group(2)),
                        "decode_sum": float(m.group(3)), "decode_pct": float(m.group(4)),
                        "prefill_pct": float(m.group(5)), "avg_prefill": float(m.group(6)),
                        "avg_decode": float(m.group(7))}
        else:
            dec[tag] = TBD
            print(f"  !! ⑤(a) 파싱 실패 -> TBD : {tag}")
    s7["profile_phases"] = dec
    D["S7"] = s7

    # ---------------- 환경 / 레짐 ----------------
    D["env"] = {"gpu": "RTX 5090 x2 (sm_120)", "model": "Qwen/Qwen3-8B", "tp": 2,
                "engine": "SGLang + HiCache", "pool_tokens": 262144,
                "fit_median": 8.1, "oversub_def": "C / fit median"}
    D["mutants"] = ["M1 context-length 랭킹", "M2 ι 반전", "M3 용량 게이팅 제거",
                    "M4 진행중 콜 무시", "M5 옛 표본 미폐기", "M6 lazy 제거",
                    "M7 tie-break MRU 반전", "M8 tie-break 제거"]

    with open(OUT, "w") as f:
        json.dump(D, f, indent=1, ensure_ascii=False)

    # ---------------- 콘솔 대조표 ----------------
    print("\n" + "=" * 96)
    print("확정 수치 (로그/원시 데이터에서 직접 추출)")
    print("=" * 96)
    print(f"A 계층: {D['A_total']}/{D['A_denom']} PASS  (최초 {D['A_initial']})")
    print(f"  A5 경계: GPU2칸 {D['A5_gpu2']} -> GPU3칸 {D['A5_gpu3']}  ({D['A5_boundary']})")
    print(f"  A6a: busy {D['A6a_base']} / outlier {D['A6a_outlier']} / idle {D['A6a_idle']}")
    print(f"  A6b: {D['A6b_traj']}   crossover {D['A6b_crossover_s']}s")
    print(f"  A7c: {D['A7c_before']} -> {D['A7c_after']}   (fix: {D['A7c_fix_router']})")
    print(f"  A2c: MORI {D['A2c_mori_marked']} / tr {D['A2c_tr_marked']} -> {D['A2c_verdict']}")
    print("\nB tier 이동 (raw 프록시 로그 / 로그표 일치여부):")
    for r in D["B_tier_moves"]:
        print(f"  C{r['C']:<3d} ({r['oversub']}x)  demote={r['demote']:<4} promote={r['promote']:<4} "
              f"evict={r['evict']:<3} log==raw: {r['log_matches_raw']}")
    print("\nB2 util / throughput (raw 재계산):")
    print(f"  {'C':<4} {'over':<6} {'TA util/thr':<16} {'TAO util/thr':<16} {'MORI util/thr':<16}")
    for r in D["B2"]:
        def fmt(x):
            return f"{x['util']}/{x['thr']}" if x else "-"
        print(f"  {r['C']:<4} {r['oversub']:<6} {fmt(r['TA']):<16} {fmt(r['TAO']):<16} {fmt(r['MORI']):<16}")
    print("\nSTEP7 ① 생산성비: C8 MORI={} / C10 MORI={} / C80 MORI={} / C80 TAO={}".format(
        s7["prod_C8_MORI"], s7["prod_C10_MORI"], s7["prod_C80_MORI"], s7["prod_C80_TAO"]))
    print("STEP7 ② 낭비율/hit:")
    for k, v in s7["waste"].items():
        if v != TBD:
            print(f"  {k:<14} waste={v['waste']} hit={v['hit']} prefill={v['prefill']} recompute={v['recompute']}")
    print("STEP7 ④ thrashing:")
    for k, v in s7["thrash"].items():
        if v != TBD:
            print(f"  {k:<14} out/prom={v['out_per_promote']:<6} moves/min={v['moves_min']:<6} pingpong={v['pingpong']}%")
    print("STEP7 ⑤ pause 분해:")
    for k, v in s7["profile_ttft"].items():
        if v != TBD:
            print(f"  {k:<14} ttft_p50={v['ttft_p50']:<7} pause_p50={v['pause_p50']:<7} pause>0={v['pause_nonzero']}%")
    print("STEP7 ⑤ 정확 goodput:")
    for k, v in s7["profile_goodput"].items():
        if v != TBD:
            print(f"  {k:<14} thr={v['thr']:<6} SLO5 {v['slo5_sat']}% / {v['slo5_gp']}")
    print(f"\n[wrote] {OUT}")


if __name__ == "__main__":
    main()
