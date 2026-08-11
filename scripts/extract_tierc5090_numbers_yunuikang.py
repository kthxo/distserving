#!/usr/bin/env python3
"""5090 TP1 결과 전용 덱 — 수치 추출 (원자료에서만 읽는다).

출력: scratch/mori/tierc_5090tp1/deck_numbers_5090.json
덱 빌더와 플롯은 이 JSON 만 읽는다 (하드코딩 금지).
해석·판정은 넣지 않는다 — 측정값과 정의만.
"""
import csv
import json
import os
import re

D = "/home/yunuikang/yunuikang_work/scratch/mori/tierc_5090tp1"
OUT = os.path.join(D, "deck_numbers_5090.json")
CS = [7, 15, 20, 70]
SYS = ["MORI", "TAO"]
FIT_DEN = 32376


def num(x, d=0.0):
    try:
        s = str(x).strip()
        return float(s) if s not in ("", "None") else d
    except (TypeError, ValueError):
        return d


def goodput(tag, slo=5.0):
    """goodput@SLO = Σ completion_tokens(TTFT≤SLO 인 스텝) ÷ 고정 steady 창."""
    p = os.path.join(D, f"profile_{tag}", "step_profiles.csv")
    w = json.load(open(os.path.join(D, f"window_{tag}.json")))
    lo = w["t_start"] + w["warm"] * (w["t_end"] - w["t_start"])
    hi = w["t_end"]
    sat = tot = 0.0
    ok = cnt = 0
    for r in csv.DictReader(open(p)):
        t = num(r["completed_at"], -1)
        if not (lo <= t <= hi):
            continue
        cnt += 1
        c = num(r["completion_tokens"])
        tot += c
        if num(r["pause_s"]) + num(r["prefill_s"]) <= slo:
            sat += c
            ok += 1
    wall = hi - lo
    return dict(goodput5=sat / wall, sat_frac=(ok / cnt if cnt else None),
                out_tok=tot, steps=cnt)


def prefix_hit(tag):
    """엔진 카운터 델타: cached ÷ prompt (고정 steady 창)."""
    p = os.path.join(D, f"engine_{tag}.csv")
    w = json.load(open(os.path.join(D, f"window_{tag}.json")))
    lo = w["t_start"] + w["warm"] * (w["t_end"] - w["t_start"])
    hi = w["t_end"]
    rows = [r for r in csv.DictReader(open(p)) if lo <= num(r["wall_clock"], -1) <= hi]
    if len(rows) < 2:
        return None
    d = lambda k: num(rows[-1][k]) - num(rows[0][k])
    pr, ca = d("prompt_tokens_total"), d("cached_tokens_total")
    return (ca / pr) if pr else None


def waiting_evict(tag, router):
    """MORI: 프록시 로그의 `MORI evict CPU->Waiting` · 그 외: `Paused program`.
    두 문자열은 **서로 다른 사건**이라 시스템 간 절대값 비교는 성립하지 않는다."""
    p = os.path.join(D, f"proxy_{tag}.log")
    if not os.path.exists(p):
        return None, None
    pat = "MORI evict CPU->Waiting" if router == "mori" else "Paused program"
    n = 0
    with open(p, errors="ignore") as f:
        for line in f:
            if pat in line:
                n += 1
    return n, pat


def boot_asserts():
    """러너 로그의 기동 assert 를 셀 순서대로 긁는다."""
    out = []
    for name in ("runner_full.log", "runner_smoke.log"):
        p = os.path.join(D, name)
        if not os.path.exists(p):
            continue
        cur = None
        for line in open(p, errors="ignore"):
            m = re.search(r"\[assert\] GPU=([\d,]+) \(기대 ([\d,]+)\) host=([\d,]+) "
                          r"\(기대 ([\d,]+)\) fit=([\d.]+)", line)
            if m:
                cur = dict(gpu=int(m.group(1).replace(",", "")),
                           gpu_exp=int(m.group(2).replace(",", "")),
                           host=int(m.group(3).replace(",", "")),
                           host_exp=int(m.group(4).replace(",", "")),
                           fit=float(m.group(5)))
            m2 = re.search(r"\[cell (\S+)\] START", line)
            if m2 and cur:
                out.append(dict(tag=m2.group(1), **cur))
                cur = None
    return out


def main():
    A = {x["tag"]: x for x in json.load(open(os.path.join(D, "tierc_summary.json")))}
    DRV = {}
    for line in open(os.path.join(D, "results_tierc.jsonl")):
        r = json.loads(line)
        DRV[r["run_tag"]] = r

    cells = {}
    for C in CS:
        for s in SYS:
            tag = f"{s}_C{C}"
            a, dv = A[tag], DRV[tag]
            w = a["wall_ms"]
            gp = goodput(tag)
            ev, evkind = waiting_evict(tag, "mori" if s == "MORI" else "tr")
            cells[tag] = dict(
                system=s, C=C, oversub=C / (a["prefill_computed_tok"] and 1) if False else C / 7.0,
                window_s=a["window_s"],
                # GPU 예산 (창 wall 대비 %)
                decode_pct=a["decode_ms"] / w * 100,
                prefill_new_pct=a["prefill_new_ms"] / w * 100,
                prefill_recomp_pct=a["prefill_recompute_ms"] / w * 100,
                idle_pct=a["idle_ms"] / w * 100,
                transfer_pct=(a["xfer_reload_ms"] + a["xfer_offload_ms"]) / w * 100,
                # 절대 시간(초)
                decode_s=a["decode_ms"] / 1e3, prefill_new_s=a["prefill_new_ms"] / 1e3,
                prefill_recomp_s=a["prefill_recompute_ms"] / 1e3, idle_s=a["idle_ms"] / 1e3,
                reload_s=a["xfer_reload_ms"] / 1e3, offload_s=a["xfer_offload_ms"] / 1e3,
                # 토큰
                decode_tok=a["decode_tok"], prefill_computed_tok=a["prefill_computed_tok"],
                recompute_tok=a["recompute_tok"], recompute_frac=a["recompute_frac"],
                reload_tok=a["reload_tok"], offload_tok=a["offload_tok"],
                out_tok=gp["out_tok"],
                reload_per_out=(a["reload_tok"] / gp["out_tok"]) if gp["out_tok"] else None,
                recompute_per_out=(a["recompute_tok"] / gp["out_tok"]) if gp["out_tok"] else None,
                prefix_hit=prefix_hit(tag),
                waiting_evict=ev, waiting_evict_kind=evkind,
                # 처리량·지연
                goodput5=gp["goodput5"], sat_frac=gp["sat_frac"],
                drv_thr=dv["output_throughput_tok_s"],
                ttft_p50=dv["ttft_p50_s"], ttft_p95=dv["ttft_p95_s"],
                steady_turns=dv["steady_turns"], completed_programs=dv["completed_programs"],
                failed_programs=dv["failed_programs"],
                # closure
                checks=a["checks"],
                xcheck_prefill=a.get("xcheck_prefill_ratio"),
                xcheck_decode=a.get("xcheck_decode_ratio"),
                steps_in_window=a["steps_in_window"],
                decode_steps=a["decode_steps"], prefill_steps=a["prefill_steps"],
                xfer_events=a["xfer_events"],
            )

    ratio = {}
    for C in CS:
        m, t = cells[f"MORI_C{C}"], cells[f"TAO_C{C}"]
        ratio[str(C)] = {k: (m[k] / t[k]) if (m.get(k) and t.get(k)) else None
                         for k in ("goodput5", "decode_tok", "drv_thr", "recompute_frac",
                                   "reload_tok", "ttft_p50", "ttft_p95", "prefix_hit")}

    data = dict(
        cells=cells, ratio=ratio, boot=boot_asserts(),
        env=dict(gpu="NVIDIA GeForce RTX 5090 ×1", gpu_mem_mib=32607, tp=1,
                 cuda_visible_devices="0", box="goguma6",
                 engine="SGLang 0.5.10 + HiCache", model="Qwen/Qwen2.5-7B-Instruct",
                 kv_per_tok_kib=56, weights_gib=14.19,
                 context_length=71680, yarn_factor=2.1875, yarn_base=32768,
                 attention_backend="triton", sampling_backend="pytorch",
                 mem_fraction_static=0.90, page_size=1,
                 max_total_tokens=226632, fit=226632 / FIT_DEN,
                 hicache_ratio=2, host_tier_tokens=453265,
                 trace="tracelab_moriM_L64k_yunuikang.jsonl", ctx_median=FIT_DEN,
                 duration_s=1500, warmup_frac=0.2, grace_s=60, ctx_cap=69632,
                 cells=8, repeats=1),
        # 참고 데이터 (다른 실행 · 측정값 그대로)
        ref=dict(orig5090_tp2_8b_C80_ratio_drv=0.45,
                 orig5090_note="5090 ×2 · TP2 · Qwen3-8B · fit 8.10 · C80 · oversub 9.88×"),
    )
    json.dump(data, open(OUT, "w"), indent=1, ensure_ascii=False)
    print(f"[wrote] {OUT}")
    print(f"{'cell':10}{'decode%':>9}{'pf새%':>8}{'재계산%':>9}{'idle%':>8}{'재계산율':>9}"
          f"{'reload/out':>11}{'hit':>7}{'Wait':>6}{'goodput':>9}{'drv':>8}")
    for C in CS:
        for s in SYS:
            c = cells[f"{s}_C{C}"]
            print(f"{s+'_C'+str(C):10}{c['decode_pct']:9.2f}{c['prefill_new_pct']:8.2f}"
                  f"{c['prefill_recomp_pct']:9.2f}{c['idle_pct']:8.2f}{c['recompute_frac']*100:9.1f}"
                  f"{c['reload_per_out']:11.2f}{c['prefix_hit']:7.3f}{c['waiting_evict']:6d}"
                  f"{c['goodput5']:9.2f}{c['drv_thr']:8.2f}")


if __name__ == "__main__":
    main()
