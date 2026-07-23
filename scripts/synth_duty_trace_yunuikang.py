#!/usr/bin/env python3
"""
STEP 4 — Duty-controlled synthetic trace generator.

Generates canonical JSONL traces where E2E latency is fixed and only
the duty ratio d = reasoning/(reasoning+tool) varies.

Design:
  * E2E per program = T = n_turns × (reasoning_per_turn + tool_per_turn).
  * reasoning_per_turn = prefill_time + decode_time
  * tool_per_turn = reasoning_per_turn × (1-d) / d
  * Total T ≈ n_turns × reasoning_per_turn × 1/d

Calibration model (context-aware, Qwen3-8B on 5090, c=1):
  Cold prefill (turn 0): input_tokens / COLD_PREFILL_RATE
  Warm prefill (turn 1+): new_tokens / R_NEW + total_ctx / R_CTX
    - R_NEW = new token KV computation rate
    - R_CTX = attention-over-cached-context overhead rate
    Two-point fit from ctx=4-8K and ctx=16-20K measurements.
  Decode: output_tokens / DECODE_RATE

Output schema (compatible with trace_replay_driver_expC):
  {"session_id": "...", "turn": N, "input_tokens": N, "output_tokens": N, "tool_duration_s": float}

작성: 강윤의 · 2026-07-19 · STEP 4 (plans/2026-07-19_PLAN §4)
"""
import argparse
import json
import os

# Calibration constants (Qwen3-8B on 5090, c=1 실측, ctx-aware 2-point calibration)
# Measured from Gate C runs at ctx=4-8K and ctx=16-20K (2026-07-19)
COLD_PREFILL_RATE = 9038    # tok/s (full prompt, turn 0, measured at 16K)
WARM_NEW_TOKEN_RATE = 7208  # tok/s (new token KV compute component)
WARM_CTX_ATTN_RATE = 116228 # tok/s (attention over cached context component)
DECODE_RATE = 91            # tok/s (c=1, Qwen3-8B on 5090, 16-20K ctx)


def reasoning_time(input_tokens: int, output_tokens: int, turn: int,
                   input_growth: int, prev_output: int) -> float:
    """Estimated GPU reasoning time for one turn (prefill + decode).

    Turn 0: cold prefill (full input, no prefix cache).
    Turn 1+: warm prefill = new_token_compute + ctx_attention_overhead.
      The warm prefill cost has two components:
        1) KV computation for new tokens: new_tokens / R_NEW
        2) Attention of new tokens over full cached context: input_tokens / R_CTX
      This captures the context-length dependency observed in measurements.
    """
    if turn == 0:
        prefill_s = input_tokens / COLD_PREFILL_RATE
    else:
        new_tokens = prev_output + input_growth
        prefill_s = new_tokens / WARM_NEW_TOKEN_RATE + input_tokens / WARM_CTX_ATTN_RATE
    decode_s = output_tokens / DECODE_RATE
    return prefill_s + decode_s


def main() -> None:
    ap = argparse.ArgumentParser(description="STEP 4: duty-controlled synthetic trace generator")
    ap.add_argument("--duty", type=float, required=True,
                    help="Target duty ratio d = reasoning/(reasoning+tool), 0 < d < 1")
    ap.add_argument("--sessions", type=int, default=10,
                    help="Number of programs/sessions (=C for replay)")
    ap.add_argument("--turns-per-session", type=int, default=8,
                    help="Turns per session (all sessions same length)")
    ap.add_argument("--input-tokens-base", type=int, default=4000,
                    help="First-turn input tokens (context grows each turn)")
    ap.add_argument("--input-growth", type=int, default=500,
                    help="Input token growth per turn (accumulated context)")
    ap.add_argument("--output-tokens", type=int, default=50,
                    help="Output tokens per turn (fixed)")
    ap.add_argument("--out", type=str, required=True,
                    help="Output JSONL path")
    args = ap.parse_args()

    d = args.duty
    assert 0 < d < 1, f"duty must be in (0,1), got {d}"

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    total_turns = 0
    total_reasoning_s = 0.0
    total_tool_s = 0.0

    with open(args.out, "w", encoding="utf-8") as f:
        for s in range(args.sessions):
            sid = f"synth_d{d:.2f}_s{s:03d}"
            ctx = args.input_tokens_base
            for t in range(args.turns_per_session):
                out_tok = args.output_tokens
                reas_s = reasoning_time(ctx, out_tok, turn=t,
                                        input_growth=args.input_growth,
                                        prev_output=out_tok)
                # tool_duration such that d = reas / (reas + tool)
                # → tool = reas * (1-d) / d
                # All turns including last get tool sleep (driver will sleep then release).
                # This ensures actual_d == target_d exactly.
                tool_s = reas_s * (1.0 - d) / d

                rec = {
                    "session_id": sid,
                    "turn": t,
                    "input_tokens": ctx,
                    "output_tokens": out_tok,
                    "tool_duration_s": round(tool_s, 4),
                }
                f.write(json.dumps(rec) + "\n")

                total_turns += 1
                total_reasoning_s += reas_s
                total_tool_s += tool_s

                # Context grows (accumulated: prev output + tool result tokens)
                ctx += out_tok + args.input_growth

    actual_d = total_reasoning_s / (total_reasoning_s + total_tool_s) if (total_reasoning_s + total_tool_s) > 0 else 0
    avg_reas = total_reasoning_s / total_turns
    avg_tool = total_tool_s / total_turns

    print(f"=== Synthetic duty trace generated ===")
    print(f"  Output: {args.out}")
    print(f"  Sessions: {args.sessions}, Turns/session: {args.turns_per_session}, Total turns: {total_turns}")
    print(f"  Target duty d = {d:.3f}")
    print(f"  Design duty d = {actual_d:.4f}")
    print(f"  Avg reasoning/turn = {avg_reas:.3f}s  (prefill+decode, cold/warm calibrated)")
    print(f"  Avg tool_sleep/turn = {avg_tool:.3f}s")
    print(f"  Total reasoning = {total_reasoning_s:.1f}s, Total tool = {total_tool_s:.1f}s")
    print(f"  Per-session E2E ≈ {(total_reasoning_s + total_tool_s)/args.sessions:.1f}s")
    # fit×d context
    mid_ctx = args.input_tokens_base + (args.turns_per_session // 2) * (args.output_tokens + args.input_growth)
    print(f"  Mid-session ctx ≈ {mid_ctx} tok (for fit calculation reference)")


if __name__ == "__main__":
    main()
