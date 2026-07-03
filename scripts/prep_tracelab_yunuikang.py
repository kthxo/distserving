#!/usr/bin/env python3
"""Normalize TraceLab (SyFI) round traces -> canonical per-turn JSONL schema.

Input: TraceLab "round_trace" JSONL (sanitized public shape or the release
`syfi_coding_trace.jsonl.gz`). One input line = one LLM round (turn).

Output (EXPERIMENT_PLAN §2): one line = one turn
    {"session_id","turn","input_tokens","output_tokens","tool_duration_s"[,"cached_tokens"]}

Field mapping (verified against example_sessions/sanitized/round_trace.jsonl):
  session_id      <- session_id
  turn            <- round_index (re-indexed 0..n-1 per session after filtering)
  input_tokens    <- input_tokens_total  (= prefix_tokens + newly_append_tokens; accumulated)
  output_tokens   <- output_tokens        (+ reasoning_output_tokens if --include-reasoning)
  tool_duration_s <- wall span of this round's tools[]: max(result_at)-min(emitted_at), else 0
  cached_tokens   <- claude_cache_read_input_tokens or prefix_tokens (optional)

Human-in-the-loop wait is auto-excluded: rounds that open a human turn carry no
tools[], so their tool_duration_s is 0 (we only count tool-triggered latency).
The last turn of each session is forced to tool_duration_s = 0.
"""
import argparse
import gzip
import io
import json
import os
import statistics
from collections import defaultdict
from datetime import datetime
from typing import List, Optional


def _open(path: str):
    if path.endswith(".gz"):
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8")
    return open(path, "r", encoding="utf-8")


def _ts(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def tool_duration_s(row: dict) -> float:
    """Wall span of the round's tool calls (parallel-safe), in seconds.
    Falls back to summed wall latency if timestamps are missing."""
    tools = row.get("tools") or []
    if not tools:
        return 0.0
    starts, ends = [], []
    for t in tools:
        a, b = _ts(t.get("emitted_at")), _ts(t.get("result_at"))
        if a and b:
            starts.append(a)
            ends.append(b)
    if starts and ends:
        span = (max(ends) - min(starts)).total_seconds()
        return max(0.0, span)
    # fallback: sum wall (or internal) latency in ms
    total_ms = 0.0
    for t in tools:
        ms = t.get("tool_wall_latency_ms")
        if ms is None:
            ms = t.get("tool_internal_latency_ms")
        if ms:
            total_ms += float(ms)
    return total_ms / 1000.0


def normalize(rows: List[dict], args) -> List[dict]:
    # group by session
    sessions = defaultdict(list)
    for r in rows:
        if args.provider != "all" and r.get("provider") != args.provider:
            continue
        if args.model and args.model not in str(r.get("model", "")):
            continue
        sessions[r["session_id"]].append(r)

    out: List[dict] = []
    for sid, rs in sessions.items():
        rs.sort(key=lambda r: r.get("round_index", 0))
        if len(rs) < args.min_turns:
            continue
        turns = []
        for i, r in enumerate(rs):
            out_tok = int(r.get("output_tokens") or 0)
            if args.include_reasoning and r.get("reasoning_output_tokens"):
                out_tok += int(r["reasoning_output_tokens"])
            rec = {
                "session_id": sid,
                "turn": i,                       # re-indexed contiguous
                "input_tokens": int(r.get("input_tokens_total") or 0),
                "output_tokens": out_tok,
                "tool_duration_s": round(tool_duration_s(r), 3),
            }
            cached = r.get("claude_cache_read_input_tokens")
            if cached is None:
                cached = r.get("prefix_tokens")
            if cached is not None:
                rec["cached_tokens"] = int(cached)
            turns.append(rec)
        if turns:
            turns[-1]["tool_duration_s"] = 0.0   # last turn: no trailing tool wait
        out.extend(turns)
    return out


def validate(recs: List[dict]) -> List[str]:
    """Return a list of schema violations (empty = OK)."""
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp",
                    default="/home/yunuikang/yunuikang_work/scratch/TraceLab/example_sessions/sanitized/round_trace.jsonl",
                    help="TraceLab round_trace JSONL (.jsonl or .jsonl.gz)")
    ap.add_argument("--out", default="/home/yunuikang/yunuikang_work/scratch/traces/tracelab_trace.jsonl")
    ap.add_argument("--provider", default="all", choices=["all", "claude", "codex"])
    ap.add_argument("--model", default="", help="substring filter on model name (optional)")
    ap.add_argument("--min-turns", type=int, default=1)
    ap.add_argument("--include-reasoning", action="store_true",
                    help="add reasoning_output_tokens to output_tokens")
    args = ap.parse_args()

    with _open(args.inp) as f:
        rows = [json.loads(l) for l in f if l.strip()]
    recs = normalize(rows, args)
    errs = validate(recs)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # sidecar metadata
    meta = {"source": args.inp, "provider_filter": args.provider,
            "model_filter": args.model or None, "min_turns": args.min_turns,
            "include_reasoning": args.include_reasoning,
            "input_rows": len(rows), "output_turns": len(recs)}
    with open(args.out.rsplit(".", 1)[0] + ".meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    summary = summarize(recs)
    print(json.dumps({"out": args.out, "schema_ok": not errs,
                      "violations": errs[:10], "summary": summary},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
