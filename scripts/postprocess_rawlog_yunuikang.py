#!/usr/bin/env python3
"""raw-log offline 측정 — 규격 문서를 그대로 구현.

규격: docs/2026-08-16_SPEC_rawlog_measurement_yunuikang.md
      (warmup max(2400, T_fill) · bin 600s 정확 · steady ±10% & >=12bin · CV/CI95)

**판정·해석·셀간 비교를 하지 않는다.** 산출은
  (a) bin 시계열,  (b) warmup/steady 구간,  (c) steady 도달 여부,  (d) 변동 크기
까지다.  그 이상(goodput@SLO·시간예산 분해·tier 동역학)은 후속 분석의 몫.

사용:
    python scripts/postprocess_rawlog_yunuikang.py --dir <셀 디렉터리> [--json out.json]
"""
import argparse
import json
import math
import os
import statistics as st

BIN_S = 600.0          # §3 고정
WARM_FLOOR_S = 2400.0  # §2 고정 하한
FILL_FRAC = 0.95       # §2
STEADY_TOL = 0.10      # §4  ±10%
STEADY_MIN_BINS = 12   # §4  = 2h


def load_jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def main():
    global BIN_S, WARM_FLOOR_S, STEADY_MIN_BINS
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--json", default="")
    # ★ 아래 3개는 **스모크에서 코드경로를 태우기 위한 것**이다.  본 런은 반드시 기본값
    #   (=규격 문서 값)으로 돌린다.  기본값이 아니면 출력에 override 사실이 박힌다.
    ap.add_argument("--bin-s", type=float, default=BIN_S)
    ap.add_argument("--warm-floor-s", type=float, default=WARM_FLOOR_S)
    ap.add_argument("--min-bins", type=int, default=STEADY_MIN_BINS)
    a = ap.parse_args()
    D = a.dir
    overridden = (a.bin_s != BIN_S or a.warm_floor_s != WARM_FLOOR_S
                  or a.min_bins != STEADY_MIN_BINS)
    BIN_S, WARM_FLOOR_S, STEADY_MIN_BINS = a.bin_s, a.warm_floor_s, a.min_bins
    if overridden:
        print(f"  !! SPEC OVERRIDE (스모크 전용): bin={BIN_S}s warm_floor={WARM_FLOOR_S}s "
              f"min_bins={STEADY_MIN_BINS} — 본 런 결과로 쓰면 안 됨")

    meta = json.load(open(os.path.join(D, "run_meta.json")))
    reqs = load_jsonl(os.path.join(D, "requests.jsonl"))
    evs = load_jsonl(os.path.join(D, "events.jsonl"))
    snaps = load_jsonl(os.path.join(D, "snapshots.jsonl"))

    pool = (meta.get("kv_pool") or {}).get("gpu_pool_tokens") or 0
    host_total = (meta.get("kv_pool") or {}).get("host_tier_tokens") or 0

    # ---------- §1 시간축 ----------
    t_start = next((e["ts"] for e in evs if e.get("event") == "run_start"), None)
    t_end = next((e["ts"] for e in reversed(evs) if e.get("event") == "run_end"), None)
    if t_start is None or t_end is None:
        raise SystemExit("run_start / run_end 이벤트 없음 — 창을 확정할 수 없다")

    # ---------- §2 warmup ----------
    post = [s for s in snaps if s.get("ts", 0) >= t_start + WARM_FLOOR_S
            and s.get("num_used_tokens") is not None]
    t_fill = None
    if post:
        med = st.median([s["num_used_tokens"] for s in post])
        target = FILL_FRAC * med
        for s in snaps:
            if s.get("ts", 0) >= t_start and (s.get("num_used_tokens") or 0) >= target:
                t_fill = s["ts"]
                break
    t_warm = max(t_start + WARM_FLOOR_S, t_fill if t_fill is not None else 0.0)

    # ---------- §3 bin ----------
    n_bins = int((t_end - t_warm) // BIN_S)
    if n_bins <= 0:
        raise SystemExit(f"warmup({t_warm:.0f}s) 이후 완전한 600s bin 이 없다 (run_end {t_end:.0f}s)")
    edges = [t_warm + BIN_S * k for k in range(n_bins + 1)]

    thr = [0.0] * n_bins          # 토큰 비례 배분 누적
    ndone = [0] * n_bins
    for r in reqs:
        if r.get("status") != "ok":
            continue
        ft, et = r.get("first_token_ts"), r.get("end_ts")
        otok = r.get("output_tokens") or 0
        if ft is None or et is None or otok <= 0:
            continue
        dur = et - ft
        for k in range(n_bins):
            lo, hi = edges[k], edges[k + 1]
            ov = min(et, hi) - max(ft, lo)
            if ov <= 0:
                continue
            # 디코드 구간을 시간 비례로 쪼갠다 (창 경계 편향 제거, §3 주석)
            thr[k] += otok * (ov / dur) if dur > 0 else otok
        if et is not None:
            k = int((et - t_warm) // BIN_S)
            if 0 <= k < n_bins:
                ndone[k] += 1

    def bin_mean(key):
        out = []
        for k in range(n_bins):
            lo, hi = edges[k], edges[k + 1]
            v = [s[key] for s in snaps
                 if lo <= s.get("ts", -1) < hi and s.get(key) is not None]
            out.append(st.mean(v) if v else None)
        return out

    kv_used = bin_mean("num_used_tokens")
    host_used = bin_mean("hicache_host_used_tokens")

    bins = []
    for k in range(n_bins):
        bins.append({
            "bin": k,
            "t_lo": round(edges[k], 1), "t_hi": round(edges[k + 1], 1),
            "throughput_tok_s": round(thr[k] / BIN_S, 3),
            "kv_usage_frac": round(kv_used[k] / pool, 4) if (kv_used[k] and pool) else None,
            "host_tier_frac": round(host_used[k] / host_total, 4) if (host_used[k] and host_total) else None,
            "req_done": ndone[k],
        })

    # ---------- §4 steady ----------
    vals = [b["throughput_tok_s"] for b in bins]
    M = st.median(vals)
    cand = [abs(v - M) <= STEADY_TOL * M for v in vals] if M > 0 else [False] * n_bins
    best_lo = best_len = cur_lo = cur_len = 0
    for i, c in enumerate(cand):
        if c:
            if cur_len == 0:
                cur_lo = i
            cur_len += 1
            if cur_len > best_len:
                best_lo, best_len = cur_lo, cur_len
        else:
            cur_len = 0
    reached = best_len >= STEADY_MIN_BINS

    # ---------- §5 분산 ----------
    var = None
    if reached:
        sv = vals[best_lo:best_lo + best_len]
        n = len(sv)
        mean = st.mean(sv)
        sd = st.stdev(sv) if n > 1 else 0.0
        half = 1.96 * sd / math.sqrt(n)
        var = {"n_bins": n, "mean_tok_s": round(mean, 3), "sd_tok_s": round(sd, 3),
               "cv": round(sd / mean, 4) if mean else None,
               "ci95_lo": round(mean - half, 3), "ci95_hi": round(mean + half, 3)}

    out = {
        "dir": D,
        "run_tag": meta.get("run_id"),
        "concurrency": meta.get("concurrency"),
        "regime": (meta.get("regime") or {}).get("concurrency_level"),
        "spec": "docs/2026-08-16_SPEC_rawlog_measurement_yunuikang.md",
        "spec_overridden": overridden,
        "window": {
            "run_start_s": round(t_start, 1), "run_end_s": round(t_end, 1),
            "run_len_s": round(t_end - t_start, 1),
            "t_fill_s": round(t_fill, 1) if t_fill is not None else None,
            "warm_cut_s": round(t_warm, 1),
            "warm_rule": f"max(run_start+{WARM_FLOOR_S:.0f}, T_fill@{FILL_FRAC:.2f})",
            "n_bins": n_bins, "bin_s": BIN_S,
        },
        "steady": {
            "median_tok_s": round(M, 3),
            "tolerance": STEADY_TOL, "min_bins": STEADY_MIN_BINS,
            "longest_run_bins": best_len,
            "reached": reached,
            "start_bin": best_lo if reached else None,
            "t_lo_s": round(edges[best_lo], 1) if reached else None,
            "t_hi_s": round(edges[best_lo + best_len], 1) if reached else None,
        },
        "variance": var,
        "bins": bins,
    }

    print(f"=== postprocess: {D} ===")
    print(f"  run   [{t_start:.0f} .. {t_end:.0f}]s  len {t_end-t_start:.0f}s")
    print(f"  warm  cut {t_warm:.0f}s  (floor {t_start+WARM_FLOOR_S:.0f} · T_fill "
          f"{('%.0f' % t_fill) if t_fill is not None else 'n/a'})")
    print(f"  bins  {n_bins} x {BIN_S:.0f}s   median throughput {M:,.1f} tok/s")
    print(f"  steady 최장연속 {best_len} bin (기준 >={STEADY_MIN_BINS}) -> "
          f"{'도달' if reached else '★미도달'}")
    if var:
        print(f"  변동  n={var['n_bins']} mean={var['mean_tok_s']:,.1f} sd={var['sd_tok_s']:,.1f} "
              f"CV={var['cv']:.3f} CI95=[{var['ci95_lo']:,.1f}, {var['ci95_hi']:,.1f}]")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(out, f, indent=2)
        print(f"  -> {a.json}")


if __name__ == "__main__":
    main()
