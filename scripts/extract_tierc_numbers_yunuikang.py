#!/usr/bin/env python3
"""Tier C 결과-전용 덱을 위한 수치 추출 (원자료 → deck_numbers.json).

읽는 것 (전부 원자료):
  scratch/mori/tierc_h200/tierc_summary.json     GPU 시간 분해 + closure 게이트
  scratch/mori/tierc_h200/results_tierc.jsonl    드라이버 지표 (TTFT · thr · 완주)
  scratch/mori/tierc_h200/engine_<TAG>.csv       엔진 steady-window (prefix hit · recompute · reload)
  scratch/mori/tierc_h200/profile_<TAG>/step_profiles.csv   goodput@5s
  scratch/mori/tierc_h200/proxy_<TAG>.log        Waiting 축출 · demote · ping-pong
  h200_scratch/mori/h200_phase2/*                Phase 2 나란히-표
  scratch/mori/tierc_5090tp1/*                   5090 TP1 (있으면)

엔진/goodput/moves 는 Phase 2 분석기(`analyze_phase2_v2_yunuikang.py`)의 함수를
**그대로 import** 해서 쓴다 — 지표 정의를 재구현하지 않기 위함.

빌더는 이 스크립트가 쓴 JSON 만 읽는다 (수치 하드코딩 금지).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from analyze_phase2_v2_yunuikang import engine_steady, goodput, moves  # noqa: E402
import tierc_rank_recon_yunuikang as RANK  # noqa: E402

ROOT = os.path.dirname(HERE)                       # distserving/
WORK = os.path.dirname(ROOT)                       # yunuikang_work/
TIERC = os.path.join(WORK, "scratch", "mori", "tierc_h200")
T5090 = os.path.join(WORK, "scratch", "mori", "tierc_5090tp1")
PHASE2 = os.path.join(WORK, "h200_scratch", "mori", "h200_phase2")
OUT = os.path.join(TIERC, "deck_numbers.json")

FIT_DEN = 32376          # ctx median (트레이스)
POOL = 647520            # max-total-tokens (boot assert)


def goodput_window(d, tag, slo=5.0):
    """Tier C 전용 goodput@SLO — **계측 창 안**의 step 만 센다.

    Phase 2 의 `goodput()` 은 step_profiles.csv 전체 구간을 분모로 쓴다. Tier C 의
    MORI 셀은 드레인 꼬리가 창 밖으로 길게 남아(csv span 1960~2185s vs 창 1254s)
    같은 함수를 그대로 쓰면 분모가 창의 1.6~1.7 배가 된다. GPU 예산·closure 와
    같은 창을 쓰려면 창으로 잘라야 한다. 분모 = 창 wall (`window_<TAG>.json`).
    """
    csvp = os.path.join(d, f"profile_{tag}", "step_profiles.csv")
    winp = os.path.join(d, f"window_{tag}.json")
    if not (os.path.exists(csvp) and os.path.exists(winp)):
        return None
    w = json.load(open(winp))
    lo = w["t_start"] + w["warm"] * (w["t_end"] - w["t_start"])
    hi = w["t_end"]
    rows = [r for r in __import__("csv").DictReader(open(csvp)) if r.get("completed_at")]
    S = [r for r in rows if lo <= float(r["completed_at"]) <= hi]
    if len(S) < 5:
        return None
    wall = hi - lo

    def tok(rs):
        return sum(int(r["completion_tokens"] or 0) for r in rs)

    ok = [r for r in S if float(r["pause_s"] or 0) + float(r["prefill_s"] or 0) <= slo]
    return {"goodput": tok(ok) / wall, "step_thr": tok(S) / wall,
            "sat": 100.0 * len(ok) / len(S), "n": len(S), "wall": wall,
            "csv_span_s": (float(max(rows, key=lambda r: float(r["completed_at"]))["completed_at"])
                           - float(min(rows, key=lambda r: float(r["completed_at"]))["completed_at"]))}


def moves_split(d, tag, sys_name):
    """proxy 로그 이벤트 — 전체 / graceful-shutdown 이전 을 나눠서 센다."""
    p = os.path.join(d, f"proxy_{tag}.log")
    if not os.path.exists(p):
        return {}
    lines = open(p, "rb").read().decode("utf-8", "replace").splitlines()
    cut = len(lines)
    for i, ln in enumerate(lines):
        if "Shutting down" in ln:
            cut = i
            break
    pat = "MORI evict CPU->Waiting" if sys_name == "MORI" else "Paused program"
    return {"evict_total": sum(1 for ln in lines if pat in ln),
            "evict_preshutdown": sum(1 for ln in lines[:cut] if pat in ln),
            "shutdown_line": cut + 1}


def load_driver(d, fname="results_tierc.jsonl"):
    p = os.path.join(d, fname)
    out = {}
    if not os.path.exists(p):
        return out
    for line in open(p):
        if line.strip():
            c = json.loads(line)
            out[c["run_tag"]] = c
    return out


def derive(d, summary_path, driver_file, fit_den=FIT_DEN):
    """한 실험 디렉터리(H200 Tier C 또는 5090 TP1)의 셀별 수치."""
    S = json.load(open(summary_path))
    drv = load_driver(d, driver_file)
    cells = {}
    for c in S:
        tag = c["tag"]
        w = c["wall_ms"]
        dr = drv.get(tag, {})
        dur = dr.get("duration_s", 1500.0)
        e = engine_steady(d, tag, dur) or {}
        g = goodput_window(d, tag, 5.0) or {}
        g_csv = goodput(d, tag, 5.0) or {}
        mv = moves(d, tag, c["system"]) or {}
        ms = moves_split(d, tag, c["system"])
        out_tok = c["out_tok_window"]
        winp = os.path.join(d, f"window_{tag}.json")
        maxtok = json.load(open(winp)).get("maxtok") if os.path.exists(winp) else POOL
        fit = maxtok / fit_den
        cells[tag] = {
            "system": "MORI" if c["system"] == "MORI" else "TA+O",
            "C": c["C"],
            "fit": fit,
            "maxtok": maxtok,
            "oversub": c["C"] / fit,
            # ── GPU 가산 예산 (창 wall = 100%)
            "wall_s": c["window_s"],
            "decode_s": c["decode_ms"] / 1e3,
            "prefill_new_s": c["prefill_new_ms"] / 1e3,
            "prefill_recompute_s": c["prefill_recompute_ms"] / 1e3,
            "idle_s": c["idle_ms"] / 1e3,
            "decode_pct": c["decode_ms"] / w * 100,
            "prefill_new_pct": c["prefill_new_ms"] / w * 100,
            "prefill_recompute_pct": c["prefill_recompute_ms"] / w * 100,
            "idle_pct": c["idle_ms"] / w * 100,
            "transfer_s": (c["xfer_reload_ms"] + c["xfer_offload_ms"]) / 1e3,
            "transfer_pct": (c["xfer_reload_ms"] + c["xfer_offload_ms"]) / w * 100,
            "xfer_reload_s": c["xfer_reload_ms"] / 1e3,
            "xfer_offload_s": c["xfer_offload_ms"] / 1e3,
            "xfer_events": c["xfer_events"],
            # ── 토큰
            "decode_tok": c["decode_tok"],
            "prefill_computed_tok": c["prefill_computed_tok"],
            "new_required_tok": c["new_required_tok"],
            "recompute_tok": c["recompute_tok"],
            "recompute_frac": c["recompute_frac"],
            "reload_tok": c["reload_tok"],
            "offload_tok": c["offload_tok"],
            "out_tok_window": out_tok,
            "reload_per_output": c["reload_tok"] / out_tok if out_tok else None,
            "recompute_per_output": c["recompute_tok"] / out_tok if out_tok else None,
            "decode_steps": c["decode_steps"],
            "prefill_steps": c["prefill_steps"],
            "steps_profile": c["steps_profile"],
            # ── closure 게이트
            "closure_ok": c["closure_ok"],
            "checks": c["checks"],
            "gpu_busy_frac": c["gpu_busy_frac"],
            "xcheck_prefill_ratio": c["xcheck_prefill_ratio"],
            "xcheck_decode_ratio": c["xcheck_decode_ratio"],
            "full_run_prefill_tok": c["full_run"]["prefill_tok"],
            "full_run_decode_tok": c["full_run"]["decode_tok"],
            # ── 엔진 steady-window
            "engine_thr": e.get("thr"),
            "prefix_hit": e.get("hit"),
            "engine_recompute": e.get("recompute"),
            "engine_reload_M": e.get("reload_M"),
            # ── goodput (계측 창 기준)
            "goodput5": g.get("goodput"),
            "step_thr": g.get("step_thr"),
            "sat_pct": g.get("sat"),
            "goodput_n_steps": g.get("n"),
            "goodput_wall_s": g.get("wall"),
            "csv_span_s": g.get("csv_span_s"),
            "goodput5_csvspan": g_csv.get("goodput"),   # Phase 2 와 같은 분모(참고)
            # ── 라우터 이동
            "demote": mv.get("demote"),
            "wait_evict": ms.get("evict_total"),
            "wait_evict_preshutdown": ms.get("evict_preshutdown"),
            "evict_kind": mv.get("kind"),
            "pingpong_pct": mv.get("pingpong"),
            # ── 드라이버
            "drv_thr": dr.get("output_throughput_tok_s"),
            "ttft_p50": dr.get("ttft_p50_s"),
            "ttft_p95": dr.get("ttft_p95_s"),
            "ttft_mean": dr.get("ttft_mean_s"),
            "completed_programs": dr.get("completed_programs"),
            "failed_programs": dr.get("failed_programs"),
            "steady_completion_tokens": dr.get("steady_completion_tokens"),
            "steady_turns": dr.get("steady_turns"),
            "duration_s": dur,
        }
    return cells


def ratios(cells, Cs):
    """셀별 MORI ÷ TA+O."""
    out = {}
    for C in Cs:
        m, t = cells.get(f"MORI_C{C}"), cells.get(f"TAO_C{C}")
        if not m or not t:
            continue
        r = {}
        for k in ("goodput5", "engine_thr", "drv_thr", "ttft_p50", "ttft_p95",
                  "prefix_hit", "recompute_frac", "reload_per_output", "decode_pct"):
            a, b = m.get(k), t.get(k)
            r[k] = (a / b) if (a and b) else None
        out[str(C)] = r
    return out


def phase2_cells():
    """Phase 2 (H200, 3600s 셀) — 나란히 놓기 위한 같은 지표."""
    drv = load_driver(PHASE2, "results_phase2.jsonl")
    out = {}
    for tag, dr in drv.items():
        sysn = tag.split("_")[0]
        if sysn not in ("MORI", "TAO"):
            continue
        e = engine_steady(PHASE2, tag, dr.get("duration_s", 3600)) or {}
        g = goodput(PHASE2, tag, 5.0) or {}
        mv = moves(PHASE2, tag, sysn) or {}
        out[tag] = {
            "system": "MORI" if sysn == "MORI" else "TA+O",
            "C": dr.get("concurrency"),
            "duration_s": dr.get("duration_s"),
            "engine_thr": e.get("thr"),
            "prefix_hit": e.get("hit"),
            "engine_recompute": e.get("recompute"),
            "engine_reload_M": e.get("reload_M"),
            "goodput5": g.get("goodput"),
            "sat_pct": g.get("sat"),
            "wait_evict": mv.get("evict"),
            "demote": mv.get("demote"),
            "drv_thr": dr.get("output_throughput_tok_s"),
            "ttft_p50": dr.get("ttft_p50_s"),
            "ttft_p95": dr.get("ttft_p95_s"),
        }
    return out


def rank_dist(tags):
    """_type_rank 재생 (출하 코드 구동) — MORI 셀만.

    창은 `tierc_rank_recon_yunuikang.main()` 의 `--window` 와 동일하게
    t_start + warm*(t_end - t_start) ~ t_end 로 잡는다.
    """
    out = {}
    for tag in tags:
        csvp = os.path.join(TIERC, f"profile_{tag}", "step_profiles.csv")
        winp = os.path.join(TIERC, f"window_{tag}.json")
        if not os.path.exists(csvp) or not os.path.exists(winp):
            continue
        w = json.load(open(winp))
        lo = w["t_start"] + w["warm"] * (w["t_end"] - w["t_start"])
        hi = w["t_end"]
        stamps = RANK.replay(csvp, lo, hi)
        n = len(stamps)
        hist = {"0": 0, "1": 0, "2": 0}
        for s in stamps:
            hist[str(s["rank"])] += 1
        seeded = sorted(s["iota"] for s in stamps if s["seeded"])

        def q(p):
            return seeded[min(len(seeded) - 1, int(p * len(seeded)))] if seeded else None

        buckets = [0, 0, 0]
        for v in seeded:
            buckets[0 if v < 0.33 else (1 if v < 0.66 else 2)] += 1
        out[tag] = {
            "n_stamps": n,
            "n_seeded": len(seeded),
            "distinct_ranks": sorted(int(k) for k, v in hist.items() if v),
            "hist": hist,
            "pct": {k: (v / n * 100 if n else None) for k, v in hist.items()},
            "iota": {"min": seeded[0] if seeded else None, "p10": q(.10),
                     "p25": q(.25), "p50": q(.50), "p75": q(.75), "p90": q(.90),
                     "max": seeded[-1] if seeded else None},
            "bucket_pct": [b / len(seeded) * 100 if seeded else None for b in buckets],
            "iota_lt_002_pct": (100.0 * sum(1 for v in seeded if v < 0.02) / len(seeded)
                                if seeded else None),
        }
    return out


def main():
    data = {
        "meta": {
            "fit": POOL / FIT_DEN,
            "pool_tokens": POOL,
            "ctx_median": FIT_DEN,
            "host_tier_tokens": 1295041,
            "r": 2,
            "model": "Qwen2.5-7B-Instruct",
            "engine": "SGLang 0.5.10 + HiCache",
            "context_len": 71680,
            "trace": "Track M (tracelab_moriM_L64k)",
            "cell_s": 1500,
            "window_s": 1254,
            "warmup_frac": 0.2,
            "slo_s": 5.0,
            "n_repeat": 1,
            "gpu": "H200 SXM 141GB × 1 (TP1)",
            "boot_assert": "GPU=647,520 (기대 647,520) · host=1,295,041 (기대 1,295,040) · fit=20.00",
            "boot_assert_5090": "GPU=226,632 (기대 226,632) · host=453,265 (기대 453,264) · fit=7.00",
            "trace_sessions": 3514,
            "trace_turns": 117257,
            "ctx_peak": 65536,
            "chunked_prefill": 8192,
            "attention_backend": "triton",
        },
        "h200": derive(TIERC, os.path.join(TIERC, "tierc_summary.json"),
                       "results_tierc.jsonl"),
    }
    data["h200_ratio"] = ratios(data["h200"], (20, 40, 80))
    data["phase2"] = phase2_cells()

    # Phase 2 비율 (같은 계산기)
    p2 = data["phase2"]
    data["phase2_ratio"] = {}
    for C in (20, 40, 80):
        m, t = p2.get(f"MORI_C{C}"), p2.get(f"TAO_C{C}")
        if m and t:
            data["phase2_ratio"][str(C)] = {
                k: (m[k] / t[k]) if (m.get(k) and t.get(k)) else None
                for k in ("goodput5", "engine_thr", "drv_thr")
            }

    data["rank"] = rank_dist(["MORI_C20", "MORI_C40", "MORI_C80"])

    if os.path.exists(os.path.join(T5090, "tierc_summary.json")):
        data["h5090"] = derive(T5090, os.path.join(T5090, "tierc_summary.json"),
                               "results_tierc.jsonl")
        Cs = sorted({c["C"] for c in data["h5090"].values()})
        data["h5090_ratio"] = ratios(data["h5090"], Cs)
        data["h5090_meta"] = {
            "gpu": "RTX 5090 × 1 (TP1)", "pool_tokens": 226632,
            "host_tier_tokens": 453265, "fit": 226632 / FIT_DEN, "r": 2,
            "host_mem_gb": 25.99, "chunked_prefill": 2048,
            "cells_in_summary": sorted(data["h5090"]),
            "cells_raw_not_analyzed": ["MORI_C20", "TAO_C20", "MORI_C70"],
        }

    with open(OUT, "w") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
    print(f"[wrote] {OUT}")
    for k in ("h200", "phase2", "h5090"):
        if k in data:
            print(f"  {k}: {len(data[k])} cells — {sorted(data[k])}")


if __name__ == "__main__":
    main()
