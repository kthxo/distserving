#!/usr/bin/env python3
"""STEP 7 Part B (⑤) — step_profiles.csv로 GPU 시간 분해 + 정확 goodput.

입력: <prof>/profile_<tag>/step_profiles.csv  (ThunderAgent --profile 산출)
      컬럼: program_id, step_id, prefill_s, decode_s, pause_s, tool_call_s,
            prompt_tokens, completion_tokens, cached_tokens, kv_hit_rate, completed_at
      (`ThunderAgent/profile/state.py:66-104`)

산출:
 (a) **GPU 바쁜 시간** = Σ(prefill_s + decode_s) 중 decode(생산적) vs prefill(준비·recompute 포함) 비율.
     pause_s는 스케줄러 대기라 GPU 시간이 **아니다** — 분모에서 제외한다.
 (b) **TTFT 분해**: 클라이언트가 겪는 TTFT = pause_s + prefill_s.
     p50/p95에서 pause가 차지하는 몫을 낸다 → "pause가 TTFT를 지배한다"를 [측정]으로 확정.
 (c) 건강 셀 vs C80에서 decode 비율이 어떻게 떨어지는지.
 (d) **정확 goodput**: SLO별로 (pause_s+prefill_s) <= SLO 인 스텝의 completion_tokens 합 ÷ steady wall.
     — Part A ③의 순서통계 구간을 프로파일 셀에 한해 실측으로 대체한다.

warmup: completed_at 기준 앞 --warm 비율을 버린다 (드라이버 --warmup-frac와 같은 취지).
"""
import argparse
import csv
import glob
import json
import os
import statistics as st


def q(v, p):
    if not v:
        return None
    s = sorted(v)
    i = max(0, min(len(s) - 1, int(round(p * (len(s) - 1)))))
    return s[i]


def f(r, k):
    v = r.get(k)
    if v in (None, "", "None"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def load(path, warm):
    rows = []
    for r in csv.DictReader(open(path)):
        d = {k: f(r, k) for k in ("prefill_s", "decode_s", "pause_s", "tool_call_s",
                                  "prompt_tokens", "completion_tokens", "cached_tokens",
                                  "kv_hit_rate", "completed_at")}
        d["program_id"] = r.get("program_id")
        if d["completed_at"]:
            rows.append(d)
    if not rows:
        return []
    rows.sort(key=lambda x: x["completed_at"])
    t0, t1 = rows[0]["completed_at"], rows[-1]["completed_at"]
    cut = t0 + warm * (t1 - t0)
    return [r for r in rows if r["completed_at"] >= cut]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prof", default="/home/yunuikang/yunuikang_work/scratch/mori/prof")
    ap.add_argument("--warm", type=float, default=0.25)
    ap.add_argument("--slo", default="2,5")
    ap.add_argument("--json")
    args = ap.parse_args()
    slos = [float(x) for x in args.slo.split(",")]

    cells = {}
    for d in sorted(glob.glob(os.path.join(args.prof, "profile_*"))):
        tag = os.path.basename(d)[len("profile_"):]
        p = os.path.join(d, "step_profiles.csv")
        if os.path.exists(p):
            rows = load(p, args.warm)
            if rows:
                cells[tag] = rows

    if not cells:
        print(f"[!] {args.prof} 에 step_profiles.csv 가 없다.")
        return

    out = {}
    # ---------------------------------------------------------------- (a)(c)
    print("=" * 108)
    print("(a)(c) 요청 처리 시간 분해 — 분모 = Σ(prefill_s + decode_s).  pause는 GPU 시간이 아니라 제외")
    print("  ⚠️ 이건 **요청별 wall-clock 국면 분해**이지 GPU 배타 점유 시간이 아니다.")
    print("     동시 요청이 겹치므로 Σ(prefill+decode)는 실제 벽시계보다 훨씬 크고, 두 값 모두")
    print("     엔진 큐잉/배칭 대기를 포함한다. 따라서 **국면 간 비율 비교**로만 읽어야 한다.")
    print("=" * 108)
    h = ("%-15s %7s %10s %10s %8s %8s | %9s %9s" %
         ("cell", "steps", "prefill_s", "decode_s", "**dec%**", "pre%", "avg_pre", "avg_dec"))
    print(h); print("-" * len(h))
    for tag, rows in sorted(cells.items()):
        pre = sum(r["prefill_s"] or 0 for r in rows)
        dec = sum(r["decode_s"] or 0 for r in rows)
        busy = pre + dec
        out.setdefault(tag, {})["busy"] = {
            "n_steps": len(rows), "prefill_s": pre, "decode_s": dec,
            "decode_pct": 100 * dec / busy if busy else None,
            "prefill_pct": 100 * pre / busy if busy else None}
        print("%-15s %7d %10.1f %10.1f %7.1f%% %7.1f%% | %9.3f %9.3f" % (
            tag, len(rows), pre, dec,
            100 * dec / busy if busy else 0, 100 * pre / busy if busy else 0,
            pre / len(rows), dec / len(rows)))

    # ---------------------------------------------------------------- (b)
    print("\n" + "=" * 108)
    print("(b) TTFT 분해:  TTFT(체감) = pause_s + prefill_s.  pause = 스케줄러 대기(GPU 아님)")
    print("=" * 108)
    h = ("%-15s | %8s %8s %8s | %8s %8s %8s | %8s %8s" %
         ("cell", "ttft_p50", "pause_p50", "pre_p50", "ttft_p95", "pause_p95", "pre_p95",
          "pause점유", "pause>0%"))
    print(h); print("-" * len(h))
    for tag, rows in sorted(cells.items()):
        pa = [r["pause_s"] or 0 for r in rows]
        pf = [r["prefill_s"] or 0 for r in rows]
        tt = [(r["pause_s"] or 0) + (r["prefill_s"] or 0) for r in rows]
        share = 100 * sum(pa) / sum(tt) if sum(tt) else 0
        nz = 100 * sum(1 for x in pa if x > 0.01) / len(pa)
        out.setdefault(tag, {})["ttft"] = {
            "ttft_p50": q(tt, .5), "ttft_p95": q(tt, .95),
            "pause_p50": q(pa, .5), "pause_p95": q(pa, .95),
            "prefill_p50": q(pf, .5), "prefill_p95": q(pf, .95),
            "pause_share_pct": share, "pause_nonzero_pct": nz}
        print("%-15s | %8.2f %8.2f %8.2f | %8.2f %8.2f %8.2f | %7.1f%% %7.1f%%" % (
            tag, q(tt, .5), q(pa, .5), q(pf, .5), q(tt, .95), q(pa, .95), q(pf, .95), share, nz))

    # ---------------------------------------------------------------- (d)
    print("\n" + "=" * 108)
    print("(d) **정확 goodput** — SLO 만족 스텝의 completion_tokens ÷ steady wall (구간 아님, 실측)")
    print("=" * 108)
    h = "%-15s %9s %10s" % ("cell", "wall_s", "thr_tok/s")
    for s in slos:
        h += " | %-24s" % f"SLO {s:g}s: 만족% / goodput"
    print(h); print("-" * len(h))
    for tag, rows in sorted(cells.items()):
        wall = max(1e-9, rows[-1]["completed_at"] - rows[0]["completed_at"])
        tot = sum(r["completion_tokens"] or 0 for r in rows)
        line = "%-15s %9.1f %10.1f" % (tag, wall, tot / wall)
        rec = {"wall_s": wall, "throughput_tok_s": tot / wall}
        for s in slos:
            ok = [r for r in rows if (r["pause_s"] or 0) + (r["prefill_s"] or 0) <= s]
            g = sum(r["completion_tokens"] or 0 for r in ok) / wall
            sat = 100 * len(ok) / len(rows)
            line += " | %-24s" % f"{sat:5.1f}% / {g:6.1f}"
            rec[f"slo_{s:g}"] = {"sat_pct": sat, "goodput_tok_s": g}
        out.setdefault(tag, {})["goodput"] = rec
        print(line)

    # ---------------------------------------------------------------- 부가
    print("\n" + "=" * 108)
    print("부가: kv_hit_rate (per-step) 및 tool_call_s — 캐시 붕괴/유휴 확인")
    print("=" * 108)
    h = "%-15s %10s %10s %12s %12s" % ("cell", "kv_hit_p50", "kv_hit_avg", "tool_call_p50", "prompt_p50")
    print(h); print("-" * len(h))
    for tag, rows in sorted(cells.items()):
        kv = [r["kv_hit_rate"] for r in rows if r["kv_hit_rate"] is not None]
        tc = [r["tool_call_s"] for r in rows if r["tool_call_s"] is not None]
        pt = [r["prompt_tokens"] for r in rows if r["prompt_tokens"] is not None]
        out.setdefault(tag, {})["extra"] = {
            "kv_hit_p50": q(kv, .5), "kv_hit_mean": st.mean(kv) if kv else None,
            "tool_call_p50": q(tc, .5), "prompt_p50": q(pt, .5)}
        print("%-15s %10s %10s %12s %12s" % (
            tag,
            f"{q(kv,.5):.3f}" if kv else "n/a",
            f"{st.mean(kv):.3f}" if kv else "n/a",
            f"{q(tc,.5):.2f}" if tc else "n/a",
            f"{q(pt,.5):.0f}" if pt else "n/a"))

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(out, fh, indent=1)
        print(f"\n[wrote] {args.json}")


if __name__ == "__main__":
    main()
