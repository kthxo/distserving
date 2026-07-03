#!/usr/bin/env python3
"""Generate a small SYNTHETIC canonical trace to validate the replay driver
offline (Phase A smoke). NOT a real dataset -- just exercises the schema:
variable session lengths, monotonically growing input_tokens (accumulated
context), short outputs, tool bubbles. Real traces come from Phase B/C.

Output: JSONL, one line = one turn, matching EXPERIMENT_PLAN §2 schema.
"""
import argparse
import json
import random


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=20)
    ap.add_argument("--out", default="/home/yunuikang/yunuikang_work/scratch/traces/mini_trace.jsonl")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    import os
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for s in range(args.sessions):
            sid = f"sess{s:03d}"
            nturns = rng.randint(2, 5)
            base = rng.randint(400, 1200)      # first-turn prompt size (kept small for cheap smoke)
            ctx = base
            for t in range(nturns):
                out_tok = rng.randint(8, 40)
                # accumulated context grows each turn (like a real rollout)
                rec = {
                    "session_id": sid,
                    "turn": t,
                    "input_tokens": ctx,
                    "output_tokens": out_tok,
                    "tool_duration_s": round(rng.uniform(0.1, 0.5), 2) if t < nturns - 1 else 0.0,
                }
                f.write(json.dumps(rec) + "\n")
                ctx += out_tok + rng.randint(100, 400)   # next turn sees more context
    print(f"wrote {args.out} ({args.sessions} sessions)")


if __name__ == "__main__":
    main()
