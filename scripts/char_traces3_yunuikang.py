#!/usr/bin/env python3
"""char_traces3_yunuikang.py — 3종 TraceLab 트레이스 동일-규약 특성 비교 (READ-ONLY).

대상(기본):
  1) tracelab_trace_full.jsonl              원본 (cap 없음, 가공 전)
  2) tracelab_moriM_L64k_yunuikang.jsonl    Track M (turn-window + human-wait + CAP_HARD 300s)
  3) tracelab_fit32k.jsonl                  7월 초 fit<=32k 컷 (cap 30s + max-input session-drop)

원본 트레이스는 절대 수정하지 않는다. stdout + --out JSON 만 쓴다.

규약(3종 전부 동일하게 적용):
  - 스키마: {session_id, turn, input_tokens, output_tokens, tool_duration_s, cached_tokens}
  - uncached_input = max(input_tokens - cached_tokens, 0)   (파일에 없어 파생)
  - T_acting(턴)   = tool_duration_s
  - T_reasoning(턴)= uncached_input / REASON_PREFILL + output_tokens / REASON_DECODE
    * prep_tracelab_mori_yunuikang.py:57-58 과 동일 상수 (8000 / 152).
      moriM meta.json 의 "uncached/8000 + output/145" 문자열은 stale(코드는 152).
  - iota = T_acting / (T_acting + T_reasoning)
  - busy/idle phase 라벨 = tool_duration_s > LONG_THRESH(2.0s), 전이 = 라벨 변화 횟수
  - 윈도우 iota(k=5) = 최근 5턴 rolling (ThunderAgent/scheduler/mori_idleness.py 의 IdlenessWindow 와 동일 정의)

주의(3종 공통 아티팩트): 세 파일 모두 각 세션의 마지막 턴 tool_duration_s 를 0.0 으로 강제한다
(prep_tracelab_yunuikang.py:118, prep_tracelab_mori_yunuikang.py:236-248).
zero-tool 비율은 raw 와 last-turn 제외 두 가지로 모두 보고한다.

사용:
  python3 scripts/char_traces3_yunuikang.py --out logs/2026-08-11_trace_comparison_yunuikang.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import OrderedDict

import numpy as np

# --- 규약 상수 (prep_tracelab_mori_yunuikang.py:50-66 과 동일) ------------------
REASON_PREFILL = 8000.0   # uncached_input tok/s (프리필 프록시)
REASON_DECODE = 152.0     # output tok/s (STEP1 goguma6/SGLang 실측; nutella 145 아님)
LONG_THRESH = 2.0         # busy/idle 임계 (s)
IOTA_K = 5                # 윈도우 iota 창 길이
BUSY_IOTA = 0.2           # 윈도우 iota < 0.2 -> busy(추론 지배)
IDLE_IOTA = 0.8           # 윈도우 iota > 0.8 -> idle(툴 지배)

TRACE_DIR = "/home/yunuikang/yunuikang_work/scratch/traces"
DEFAULT_TRACES = OrderedDict([
    ("full",   os.path.join(TRACE_DIR, "tracelab_trace_full.jsonl")),
    ("trackM", os.path.join(TRACE_DIR, "tracelab_moriM_L64k_yunuikang.jsonl")),
    ("fit32k", os.path.join(TRACE_DIR, "tracelab_fit32k.jsonl")),
])

PCTS = [10, 25, 50, 75, 90, 99]


def dist(arr, pcts=PCTS):
    """min / p10 / p25 / p50 / p75 / p90 / p99 / max + mean."""
    a = np.asarray(arr, dtype=float)
    if a.size == 0:
        return {"n": 0}
    out = {"n": int(a.size), "min": float(a.min()), "max": float(a.max()),
           "mean": float(a.mean())}
    for q in pcts:
        out[f"p{q}"] = float(np.percentile(a, q))
    return out


def iter_sessions(path):
    """세션(연속 session_id 블록) 단위로 턴 리스트를 yield. 스트리밍, 원본 미변경."""
    cur_id, cur = None, []
    bad = 0
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            sid = r["session_id"]
            if sid != cur_id:
                if cur:
                    yield cur_id, cur
                cur_id, cur = sid, []
            cur.append(r)
    if cur:
        yield cur_id, cur
    if bad:
        print(f"  [warn] {path}: {bad} unparseable lines skipped", file=sys.stderr)


def concurrent_iota_iqr(sess_iota, sess_wall, k_slots=8, n_ticks=400):
    """동시점 iota 이질성. prep_tracelab_mori_yunuikang.py::concurrent_iota_iqr 와
    동일한 단순 동시성 시뮬레이션(파일 등장 순서를 k_slots 에 라운드로빈 배치,
    makespan 을 n_ticks 로 균등 샘플링해 활성 세션 iota 의 IQR)."""
    n = len(sess_iota)
    if n == 0:
        return None
    walls = [max(float(w), 1e-3) for w in sess_wall]
    slots = [[] for _ in range(k_slots)]
    for i in range(n):
        slots[i % k_slots].append(i)
    slot_cum = []
    for sl in slots:
        slot_cum.append(np.cumsum([0.0] + [walls[i] for i in sl]))
    makespan = max((c[-1] for c in slot_cum if len(c)), default=0.0)
    if makespan <= 0:
        return None
    sampled = []
    for tick in np.linspace(0, makespan, n_ticks, endpoint=False):
        for si, sl in enumerate(slots):
            c = slot_cum[si]
            if not len(sl) or tick >= c[-1]:
                continue
            pos = min(max(int(np.searchsorted(c, tick, side="right") - 1), 0), len(sl) - 1)
            sampled.append(sess_iota[sl[pos]])
    if not sampled:
        return None
    q1, q3 = np.percentile(sampled, [25, 75])
    return {"iqr": float(q3 - q1), "q25": float(q1), "q75": float(q3),
            "n_samples": len(sampled), "k_slots": k_slots, "n_ticks": n_ticks}


def analyze(path, label):
    n_turns = 0
    # per-turn pools
    inp, tool, out_tok, unc_tok = [], [], [], []
    reason_all = []
    is_last_flag = []
    # per-session pools
    turns_per_sess, peak_ctx, transitions = [], [], []
    sess_iota, sess_wall, sess_tool, sess_reason = [], [], [], []
    win_iota = []

    for _sid, rows in iter_sessions(path):
        n = len(rows)
        n_turns += n
        turns_per_sess.append(n)

        ii = np.fromiter((float(r["input_tokens"]) for r in rows), float, n)
        cc = np.fromiter((float(r["cached_tokens"]) for r in rows), float, n)
        oo = np.fromiter((float(r["output_tokens"]) for r in rows), float, n)
        td = np.fromiter((float(r["tool_duration_s"]) for r in rows), float, n)
        uu = np.maximum(ii - cc, 0.0)
        rr = uu / REASON_PREFILL + oo / REASON_DECODE   # T_reasoning 프록시

        inp.append(ii); out_tok.append(oo); tool.append(td)
        unc_tok.append(uu); reason_all.append(rr)
        lastf = np.zeros(n, bool); lastf[-1] = True
        is_last_flag.append(lastf)

        peak_ctx.append(float(ii.max()))

        lab = td > LONG_THRESH
        transitions.append(int(np.count_nonzero(lab[1:] != lab[:-1])))

        T_act = float(td.sum()); T_rea = float(rr.sum())
        denom = T_act + T_rea
        sess_tool.append(T_act); sess_reason.append(T_rea)
        sess_wall.append(denom)
        sess_iota.append(T_act / denom if denom > 0 else 0.0)

        # 윈도우 iota(k=5): 최근 5턴 rolling (IdlenessWindow 정의와 동일)
        ca = np.concatenate(([0.0], np.cumsum(td)))
        cr = np.concatenate(([0.0], np.cumsum(rr)))
        for t in range(n):
            s = max(0, t - IOTA_K + 1)
            a = ca[t + 1] - ca[s]
            r_ = cr[t + 1] - cr[s]
            if a + r_ > 0:
                win_iota.append(a / (a + r_))

    inp = np.concatenate(inp); tool = np.concatenate(tool)
    out_tok = np.concatenate(out_tok); unc_tok = np.concatenate(unc_tok)
    reason_all = np.concatenate(reason_all); is_last_flag = np.concatenate(is_last_flag)
    win_iota = np.asarray(win_iota, float)
    si = np.asarray(sess_iota, float)

    tot_tool = float(tool.sum()); tot_reason = float(reason_all.sum())
    tot_wall = tot_tool + tot_reason
    longm = tool > LONG_THRESH
    nonlast = ~is_last_flag

    res = {
        "label": label,
        "path": path,
        "file_bytes": os.path.getsize(path),
        "n_sessions": len(turns_per_sess),
        "n_turns": n_turns,

        "turns_per_session": dist(turns_per_sess),
        "input_tokens_per_turn": dist(inp),
        "session_peak_context": dist(peak_ctx),
        "output_tokens_per_turn": dist(out_tok),
        "uncached_input_per_turn": dist(unc_tok),

        "transitions_per_session": dist(transitions),
        "transitions_median": float(np.median(transitions)) if transitions else 0.0,

        "tool_duration_s": dist(tool),
        "tool_duration_s_p999": float(np.percentile(tool, 99.9)),
        "session_wall_s": dist(sess_wall),
        "session_tool_s": dist(sess_tool),
        "session_reason_s": dist(sess_reason),

        "tool_time_share_pct": 100.0 * tot_tool / tot_wall if tot_wall > 0 else 0.0,
        "total_tool_s": tot_tool,
        "total_reason_s": tot_reason,
        "zero_tool_turn_pct_raw": 100.0 * float((tool == 0.0).mean()),
        "zero_tool_turn_pct_excl_last": 100.0 * float((tool[nonlast] == 0.0).mean()),
        "long_turn_pct": 100.0 * float(longm.mean()),
        "long_turn_tool_time_share_pct": (100.0 * float(tool[longm].sum() / tot_tool)
                                          if tot_tool > 0 else 0.0),

        "session_iota_mean": float(si.mean()),
        "session_iota_median": float(np.median(si)),
        "session_iota_p25": float(np.percentile(si, 25)),
        "session_iota_p75": float(np.percentile(si, 75)),
        "session_iota_iqr": float(np.percentile(si, 75) - np.percentile(si, 25)),
        "window_iota_k5": dist(win_iota),
        "window_iota_busy_pct": 100.0 * float((win_iota < BUSY_IOTA).mean()),
        "window_iota_idle_pct": 100.0 * float((win_iota > IDLE_IOTA).mean()),
        "concurrent_iota": concurrent_iota_iqr(sess_iota, sess_wall),
    }
    return res, {"tool": tool, "input": inp, "turns_per_session": np.asarray(turns_per_sess, float),
                 "peak_ctx": np.asarray(peak_ctx, float), "win_iota": win_iota, "sess_iota": si}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces", nargs="*", default=None,
                    help="label=path 형태. 미지정 시 기본 3종")
    ap.add_argument("--out", default="")
    ap.add_argument("--npz", default="", help="분포 그림용 raw 배열 저장 경로(.npz)")
    args = ap.parse_args()

    traces = DEFAULT_TRACES
    if args.traces:
        traces = OrderedDict(t.split("=", 1) for t in args.traces)

    results, raws = OrderedDict(), {}
    for label, path in traces.items():
        if not os.path.exists(path):
            print(f"[skip] {label}: {path} 없음", file=sys.stderr)
            continue
        print(f"[..] {label}: {path}", file=sys.stderr)
        r, raw = analyze(path, label)
        results[label] = r
        for k, v in raw.items():
            raws[f"{label}__{k}"] = v
        print(f"     세션 {r['n_sessions']:,} / 턴 {r['n_turns']:,}", file=sys.stderr)

    payload = {
        "convention": {
            "REASON_PREFILL": REASON_PREFILL, "REASON_DECODE": REASON_DECODE,
            "T_reasoning": "uncached_input/8000 + output/152 [s]",
            "uncached_input": "input_tokens - cached_tokens (파일에 없어 파생)",
            "LONG_THRESH_s": LONG_THRESH, "IOTA_K": IOTA_K,
            "busy_window_iota": f"< {BUSY_IOTA}", "idle_window_iota": f"> {IDLE_IOTA}",
            "note": "3종 전부 동일 규약. 각 세션 마지막 턴 tool_duration_s=0 강제는 3종 공통 아티팩트.",
        },
        "datasets": results,
    }
    js = json.dumps(payload, indent=2, ensure_ascii=False)
    print(js)
    if args.out:
        with open(args.out, "w") as f:
            f.write(js + "\n")
        print(f"[ok] wrote {args.out}", file=sys.stderr)
    if args.npz:
        np.savez_compressed(args.npz, **raws)
        print(f"[ok] wrote {args.npz}", file=sys.stderr)


if __name__ == "__main__":
    main()
