#!/usr/bin/env python3
"""H200 Phase 1 — per-cell metric extraction + progress-file append.

Runs once after each cell. Reads only artefacts the cell already produced; never
touches the trace, the baselines, or any existing script.

Metric definitions are COPIED VERBATIM from the 5090 analyser
(`analyze_phase2_rsweep_yunuikang.py` moves()/band()) so the H200 numbers are
comparable to the 5090 anchors without a second convention:

  ping-pong%       MORI: pids demoted GPU->CPU at least twice, over distinct demoted pids
                   TA+O: pids "Paused program" at least twice, over distinct paused pids
  Waiting evict    MORI: "MORI evict CPU->Waiting"   (router event)
                   TA+O: "Paused program"            (DIFFERENT event — the tr router has no
                                                      CpuTier; absolute values are NOT
                                                      comparable across systems, per plan §5.3)
  goodput          TTFT order-statistic BAND, not a point estimate: the driver stores no
                   per-turn records (mori_replay_driver_yunuikang.py:320-345), so a point
                   goodput is not computable. Same convention as the 5090 runs. PREREG §10.6.

Engine steady-window throughput (the unbiased corroborant of PREREG §10.2) uses the FIXED
window [t_start + 0.2*DUR, t_start + DUR] — plan §5.3, after a variable window flipped a
conclusion on the 5090.
"""
import argparse
import csv
import json
import os
import re
from collections import Counter


def read_driver(res_path, tag):
    if not os.path.exists(res_path):
        return None
    rec = None
    for line in open(res_path, errors="replace"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("run_tag") == tag:
            rec = d          # last wins
    return rec


def moves(proxy_log, system):
    """VERBATIM from analyze_phase2_rsweep_yunuikang.py:64-89."""
    if not os.path.exists(proxy_log):
        return None
    b = open(proxy_log, "rb").read().decode("utf-8", "replace")
    if system == "MORI":
        dem = re.findall(r"MORI demote GPU->CPU (\S+)", b)
        return {"demote": len(dem),
                "promote": len(re.findall(r"MORI promote CPU->GPU", b)),
                "evict": len(re.findall(r"MORI evict CPU->Waiting", b)),
                "evict_kind": "CPU->Waiting",
                "pingpong": (100.0 * sum(1 for v in Counter(dem).values() if v >= 2) / len(set(dem)))
                            if dem else 0.0}
    paused = re.findall(r"Paused program (\S+) from", b)
    return {"demote": len(paused), "promote": len(re.findall(r"Resumed program", b)),
            "evict": len(paused), "evict_kind": "GPU->Waiting(pause)",
            "pingpong": (100.0 * sum(1 for v in Counter(paused).values() if v >= 2) / len(set(paused)))
                        if paused else 0.0}


def band(rec, slo=5.0):
    """VERBATIM from analyze_phase2_rsweep_yunuikang.py:106-112."""
    if not rec:
        return None
    p50, p95 = rec.get("ttft_p50_s"), rec.get("ttft_p95_s")
    if p50 is None or p95 is None:
        return None
    return (95.0, 100.0) if slo >= p95 else ((50.0, 95.0) if slo >= p50 else (0.0, 50.0))


def engine_steady_tok_s(csv_path, t_start, dur, warm=0.2):
    """Fixed steady window [t_start + warm*dur, t_start + dur] over the /metrics counter."""
    if not os.path.exists(csv_path):
        return None, "engine csv missing"
    w0, w1 = t_start + warm * dur, t_start + dur
    rows = []
    try:
        for r in csv.DictReader(open(csv_path)):
            try:
                wc = float(r["wall_clock"])
                g = float(r["generation_tokens_total"])
            except (TypeError, ValueError, KeyError):
                continue
            rows.append((wc, g))
    except Exception as e:
        return None, f"engine csv unreadable: {e!r}"
    win = [x for x in rows if w0 <= x[0] <= w1]
    if len(win) < 2:
        return None, f"engine samples in window: {len(win)}"
    win.sort()
    dt = win[-1][0] - win[0][0]
    dg = win[-1][1] - win[0][1]
    if dt <= 0 or dg < 0:
        return None, f"engine window degenerate (dt={dt:.1f}, dg={dg:.0f})"
    return dg / dt, f"{len(win)} samples over {dt:.0f}s"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)          # e.g. MORI_F1
    ap.add_argument("--system", required=True)       # MORI | TAO
    ap.add_argument("--fit-label", required=True)    # F1..F4
    ap.add_argument("--fit", type=float, required=True)
    ap.add_argument("--maxtok", type=int, required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--dur", type=float, required=True)
    ap.add_argument("--t-start", type=float, required=True)
    ap.add_argument("--t-end", type=float, required=True)
    ap.add_argument("--status", default="OK")        # OK | SKIP_GATE | SKIP_BOOT | CRASH
    ap.add_argument("--note", default="")
    ap.add_argument("--progress", required=True)
    ap.add_argument("--summary-json", required=True)  # machine-readable, for the verdict step
    args = ap.parse_args()

    rec = read_driver(args.results, args.tag)
    mv = moves(os.path.join(args.out_dir, f"proxy_{args.tag}.log"), args.system)
    eng, eng_note = engine_steady_tok_s(
        os.path.join(args.out_dir, f"engine_{args.tag}.csv"), args.t_start, args.dur)
    gb = band(rec)

    out = {
        "tag": args.tag, "system": args.system, "fit_label": args.fit_label,
        "fit": args.fit, "maxtok": args.maxtok, "status": args.status, "note": args.note,
        "t_start": args.t_start, "t_end": args.t_end,
        "wall_s": round(args.t_end - args.t_start, 1),
        "driver_thr_tok_s": (rec or {}).get("output_throughput_tok_s"),
        "engine_thr_tok_s": eng, "engine_note": eng_note,
        "ttft_p50_s": (rec or {}).get("ttft_p50_s"),
        "ttft_p95_s": (rec or {}).get("ttft_p95_s"),
        "goodput_band_5s": gb,
        "steady_turns": (rec or {}).get("steady_turns"),
        "steady_programs": (rec or {}).get("steady_programs"),
        "failed_programs": (rec or {}).get("failed_programs"),
        "waiting_evict": (mv or {}).get("evict"),
        "evict_kind": (mv or {}).get("evict_kind"),
        "pingpong_pct": (mv or {}).get("pingpong"),
        "demote": (mv or {}).get("demote"), "promote": (mv or {}).get("promote"),
    }

    # ratio vs the paired TA+O cell of the same fit (filled on MORI rows only)
    ratio_drv = ratio_eng = None
    if args.system == "MORI" and os.path.exists(args.summary_json):
        for line in open(args.summary_json, errors="replace"):
            line = line.strip()
            if not line:
                continue
            try:
                p = json.loads(line)
            except json.JSONDecodeError:
                continue
            if p.get("fit_label") == args.fit_label and p.get("system") == "TAO":
                dt, et = p.get("driver_thr_tok_s"), p.get("engine_thr_tok_s")
                if dt and out["driver_thr_tok_s"] is not None and dt > 0:
                    ratio_drv = out["driver_thr_tok_s"] / dt
                if et and out["engine_thr_tok_s"] is not None and et > 0:
                    ratio_eng = out["engine_thr_tok_s"] / et
    out["ratio_driver_mori_over_tao"] = ratio_drv
    out["ratio_engine_mori_over_tao"] = ratio_eng

    with open(args.summary_json, "a") as f:
        f.write(json.dumps(out) + "\n")

    def fmt(v, spec=".2f", dash="-"):
        return dash if v is None else format(v, spec)

    ts = lambda t: __import__("time").strftime("%H:%M:%S", __import__("time").localtime(t))
    gb_s = "-" if gb is None else f"{gb[0]:.0f}-{gb[1]:.0f}%"
    ratio_s = "-"
    if ratio_drv is not None or ratio_eng is not None:
        ratio_s = f"drv {fmt(ratio_drv, '.3f')} / eng {fmt(ratio_eng, '.3f')}"

    row = (f"| {args.tag} | {args.fit_label} (fit {args.fit:.2f}) | {args.status} | "
           f"{ts(args.t_start)} | {ts(args.t_end)} | {fmt(out['driver_thr_tok_s'])} | "
           f"{fmt(out['engine_thr_tok_s'])} | {gb_s} | {ratio_s} | "
           f"{fmt(out['waiting_evict'], 'd')} | {fmt(out['pingpong_pct'], '.0f')}% | "
           f"{fmt(out['steady_turns'], 'd')} | {args.note} |")
    with open(args.progress, "a") as f:
        f.write(row + "\n")
    print(row)


if __name__ == "__main__":
    main()
