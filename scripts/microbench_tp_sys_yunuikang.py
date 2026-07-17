#!/usr/bin/env python3
"""P0 §4-6 — SYS all-reduce penalty microbench (decode throughput).

Loads the model OFFLINE at a chosen TP degree on chosen GPUs, generates a fixed
batch of `--gen-tokens` (ignore_eos) and reports decode-dominated output tok/s.
Run once per config and compare:
  TP2 (GPU1+GPU2, cross-NUMA SYS all-reduce)  vs  TP1 (GPU1 only, no all-reduce).

Also surfaces vLLM's "GPU KV cache size: N tokens" in the startup log (num_gpu_blocks),
and exercises the non-eager compile path (Python.h/compile check).

Usage (set CUDA_VISIBLE_DEVICES yourself):
  CUDA_VISIBLE_DEVICES=1,2 python microbench_tp_sys_yunuikang.py --tp 2 --label tp2 \
      --model Qwen/Qwen3-32B --batch 32 --gen-tokens 256 --input-len 512 \
      --out /home/yunuikang/yunuikang_work/scratch/tp2/microbench_sys.jsonl
  CUDA_VISIBLE_DEVICES=1   python microbench_tp_sys_yunuikang.py --tp 1 --label tp1 ... (same --out)
"""
import argparse, json, os, time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen3-32B")
    ap.add_argument("--tp", type=int, required=True)
    ap.add_argument("--label", required=True, help="tp2 | tp1")
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--gen-tokens", type=int, default=256)
    ap.add_argument("--input-len", type=int, default=512)
    ap.add_argument("--max-model-len", type=int, default=32768)
    ap.add_argument("--gpu-mem-util", type=float, default=0.92)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from vllm import LLM, SamplingParams
    t_load0 = time.time()
    llm = LLM(model=args.model, tensor_parallel_size=args.tp,
              max_model_len=args.max_model_len, gpu_memory_utilization=args.gpu_mem_util,
              disable_log_stats=True)
    load_s = time.time() - t_load0

    # fixed-length prompt built from token ids so every request has identical prefill
    tok = llm.get_tokenizer()
    ids = (tok.encode("The quick brown fox jumps over the lazy dog. ") *
           ((args.input_len // 10) + 1))[: args.input_len]
    prompt = tok.decode(ids)
    prompts = [prompt] * args.batch
    sp = SamplingParams(temperature=0.0, max_tokens=args.gen_tokens,
                        min_tokens=args.gen_tokens, ignore_eos=True)

    # warmup (compile/graph capture happens here) then timed
    llm.generate([prompt], SamplingParams(max_tokens=8, min_tokens=8, ignore_eos=True))
    t0 = time.time()
    outs = llm.generate(prompts, sp)
    dt = time.time() - t0

    out_toks = sum(len(o.outputs[0].token_ids) for o in outs)
    tok_s = out_toks / dt if dt else 0.0
    rec = {"label": args.label, "tp": args.tp,
           "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES", ""),
           "model": args.model, "batch": args.batch, "gen_tokens": args.gen_tokens,
           "input_len": args.input_len, "load_s": round(load_s, 1),
           "gen_wall_s": round(dt, 3), "out_tokens": out_toks,
           "decode_tok_per_s": round(tok_s, 1)}
    print("[microbench]", json.dumps(rec))
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "a") as f:
        f.write(json.dumps(rec) + "\n")


if __name__ == "__main__":
    main()
