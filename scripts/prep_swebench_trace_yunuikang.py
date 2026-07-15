#!/usr/bin/env python3
"""SWE-bench 녹화(step_profiles.csv) → 공통 스키마 trace JSONL 정규화기.

Phase C(SWE-bench Lite 라이브 실행 + ThunderAgent --profile)로 박제된
`step_profiles.csv`를 replay 드라이버가 읽는 canonical 스키마로 변환한다.
TraceLab 정규화기(prep_tracelab_yunuikang.py)와 동일한 validate/summary/meta 스타일.

step_profiles.csv 컬럼(ThunderAgent/profile/state.py):
  program_id, step_id, prefill_s, decode_s, pause_s, tool_call_s,
  prompt_tokens, completion_tokens, cached_tokens, kv_hit_rate, completed_at

canonical 스키마(계획서 §2):
  {"session_id","turn","input_tokens","output_tokens","tool_duration_s"[,"cached_tokens"]}

매핑:
  session_id       ← program_id
  turn             ← step_id - 1            (profiler step_id는 1-index → 0-index)
  input_tokens     ← prompt_tokens
  output_tokens    ← completion_tokens
  tool_duration_s  ← tool_call_s            (다음 요청까지의 도구/유휴, 마지막 턴은 0으로 강제)
  cached_tokens    ← cached_tokens          (있으면)

주의: GPU/Docker 불필요(순수 CSV 변환). Phase C 녹화 완료 후 실행.
"""
import argparse
import csv
import json
import statistics
from collections import defaultdict
from typing import List, Optional


def load_csv(path: str) -> List[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _to_int(v) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _to_float(v, default=0.0) -> float:
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def normalize(rows: List[dict], args) -> List[dict]:
    """CSV rows → canonical records, grouped by program, turn-sorted, tool capped/zeroed."""
    by_prog = defaultdict(list)
    for r in rows:
        pid = r.get("program_id")
        if not pid:
            continue
        by_prog[pid].append(r)

    recs: List[dict] = []
    for pid, steps in by_prog.items():
        # sort by step_id (profiler is 1-indexed, monotonic per program)
        steps.sort(key=lambda x: _to_int(x.get("step_id")) or 0)
        n = len(steps)
        if n < args.min_turns:
            continue
        # optional: drop whole session if any turn exceeds max-input-tokens (keeps context integrity)
        if args.max_input_tokens > 0:
            if any((_to_int(s.get("prompt_tokens")) or 0) > args.max_input_tokens for s in steps):
                continue
        sess_recs = []
        for i, s in enumerate(steps):
            in_tok = _to_int(s.get("prompt_tokens"))
            out_tok = _to_int(s.get("completion_tokens"))
            if in_tok is None or in_tok <= 0:
                # invalid row; skip whole session to preserve cumulative context integrity
                sess_recs = []
                break
            tool = _to_float(s.get("tool_call_s"), 0.0)
            if i == n - 1:
                tool = 0.0  # last turn has no following tool wait
            if args.cap_tool_s > 0:
                tool = min(tool, args.cap_tool_s)
            rec = {
                "session_id": pid,
                "turn": i,                       # re-index 0..n-1 (monotonic)
                "input_tokens": in_tok,
                "output_tokens": out_tok if out_tok is not None else 0,
                "tool_duration_s": round(max(0.0, tool), 4),
            }
            cached = _to_int(s.get("cached_tokens"))
            if cached is not None:
                rec["cached_tokens"] = cached
            sess_recs.append(rec)
        recs.extend(sess_recs)
    return recs


def validate(recs: List[dict]) -> List[str]:
    """Return a list of schema violations (empty = OK). Same rules as prep_tracelab."""
    errs = []
    req = ("session_id", "turn", "input_tokens", "output_tokens", "tool_duration_s")
    last_turn = {}
    for i, r in enumerate(recs):
        for k in req:
            if k not in r:
                errs.append(f"rec {i}: missing {k}")
        if r.get("tool_duration_s", 0) < 0:
            errs.append(f"rec {i}: negative tool_duration_s")
        if r.get("input_tokens", 0) <= 0:
            errs.append(f"rec {i}: non-positive input_tokens")
        sid = r.get("session_id")
        if sid in last_turn and r["turn"] != last_turn[sid] + 1:
            errs.append(f"session {sid}: turn not monotonic (+1) at {r['turn']}")
        last_turn[sid] = r.get("turn", last_turn.get(sid, -1))
    return errs


def _stats(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    s = sorted(vals)
    def p(q):
        return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]
    return {"n": len(s), "min": s[0], "max": s[-1],
            "mean": round(statistics.mean(s), 2), "median": statistics.median(s),
            "p95": p(0.95)}


def summarize(recs: List[dict]) -> dict:
    by_sess = defaultdict(list)
    for r in recs:
        by_sess[r["session_id"]].append(r)
    turns_per = [len(v) for v in by_sess.values()]
    return {
        "sessions": len(by_sess),
        "turns_total": len(recs),
        "turns_per_session": _stats(turns_per),
        "input_tokens": _stats([r["input_tokens"] for r in recs]),
        "output_tokens": _stats([r["output_tokens"] for r in recs]),
        "tool_duration_s": _stats([r["tool_duration_s"] for r in recs]),
        "cached_tokens": _stats([r.get("cached_tokens") for r in recs]),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="SWE-bench step_profiles.csv → canonical trace JSONL")
    ap.add_argument("--in", dest="inp",
                    default="/home/yunuikang/yunuikang_work/scratch/rec_swebench/step_profiles.csv")
    ap.add_argument("--out",
                    default="/home/yunuikang/yunuikang_work/scratch/traces/swebench_trace.jsonl")
    ap.add_argument("--min-turns", type=int, default=1)
    ap.add_argument("--max-input-tokens", type=int, default=0,
                    help="drop whole session if any turn's prompt_tokens exceeds N (0=off, "
                         "use 32768 to fit 4090 KV like tracelab_fit32k)")
    ap.add_argument("--cap-tool-s", type=float, default=0.0,
                    help="clip tool_duration_s to at most S seconds (0=off)")
    ap.add_argument("--model", default="", help="record model name into sidecar meta only")
    ap.add_argument("--workers", type=int, default=0, help="record workers into sidecar meta only")
    args = ap.parse_args()

    rows = load_csv(args.inp)
    recs = normalize(rows, args)
    errs = validate(recs)

    import os
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # sidecar metadata (document model/workers/collection provenance)
    meta = {
        "source": args.inp,
        "dataset": "swebench-lite",
        "model": args.model,
        "workers": args.workers,
        "min_turns": args.min_turns,
        "max_input_tokens": args.max_input_tokens,
        "cap_tool_s": args.cap_tool_s,
        "rows_in": len(rows),
        "records_out": len(recs),
    }
    with open(args.out.rsplit(".", 1)[0] + ".meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    summary = summarize(recs)
    print(json.dumps({"out": args.out, "schema_ok": not errs,
                      "violations": errs[:10], "summary": summary},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
