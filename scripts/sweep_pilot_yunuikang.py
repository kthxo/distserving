#!/usr/bin/env python3
"""STEP 5 — Pilot sweep runner: d=0.1 (deep zone, fit×d=0.48) × f grid × C=10.

Measures thr / true_hit / p95 / preemptions / GPU utilization vs f.
Restarts vLLM + ThunderAgent between each (f, repeat) for fair comparison.

Protocol:
  1. vLLM restart → clean prefix cache, pinned C_total=95,936
  2. ThunderAgent restart → --capacity-overcommit-factor f
  3. nvidia-smi polling at 100ms in background
  4. microbench_recompute wrapping → true hit (prompt_tokens_by_source)
  5. trace_replay_driver_expC → thr/latency/preemptions

작성: 강윤의 · 2026-07-19 · STEP 5 pilot (plans/2026-07-19_PLAN §5)
"""
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request

VLLM_CMD = (
    "{venv}/bin/vllm serve Qwen/Qwen3-8B "
    "--host 0.0.0.0 --port {vllm_port} "
    "--max-model-len 32768 --gpu-memory-utilization 0.92"
)

VLLM_ENV = {
    "CUDA_VISIBLE_DEVICES": "0",
    "VLLM_USE_FLASHINFER_SAMPLER": "0",
    "VLLM_ATTENTION_BACKEND": "FLASH_ATTN",
}

# GPU device index (overridable via --gpu). Set in main().
GPU_DEVICE = "0"

TA_CMD = (
    "{venv}/bin/python -m ThunderAgent "
    "--backend-type vllm --backends http://localhost:{vllm_port} "
    "--port {ta_port} --router tr --metrics "
    "--capacity-overcommit-factor {f}"
)

DRIVER_CMD = (
    "{venv}/bin/python scripts/trace_replay_driver_expC_yunuikang.py "
    "--trace {trace} "
    "--base-url http://localhost:{ta_port} "
    "--router-url http://localhost:{ta_port} "
    "--backends http://localhost:{vllm_port} "
    "--concurrency {C} "
    "--stream "
    "--trace-out {trace_out} "
    "--out {summary_out}"
)

EXPECTED_C_TOTAL = 95936


def kill_proc(name_pattern):
    """Kill processes matching pattern."""
    subprocess.run(f"pkill -f '{name_pattern}'", shell=True,
                   capture_output=True)
    time.sleep(2)


def wait_for_health(url, timeout=120):
    """Wait for HTTP health endpoint."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = urllib.request.urlopen(f"{url}/health", timeout=5)
            if r.status == 200:
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def verify_c_total(vllm_url):
    """Read C_total from vLLM metrics and verify."""
    try:
        r = urllib.request.urlopen(f"{vllm_url}/metrics", timeout=10)
        text = r.read().decode()
        m = re.search(r'kv_cache_size_tokens="(\d+)"', text)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return None


def scrape_metrics(vllm_url):
    """Scrape key vLLM metrics."""
    try:
        r = urllib.request.urlopen(f"{vllm_url}/metrics", timeout=10)
        text = r.read().decode()
    except Exception:
        return {}

    def extract(pattern):
        m = re.search(pattern, text, re.M)
        return float(m.group(1)) if m else 0.0

    return {
        "prompt_tokens_total": extract(r'vllm:prompt_tokens_total\{[^}]*\}\s+([0-9.eE+-]+)'),
        "prompt_tokens_local_compute": extract(
            r'vllm:prompt_tokens_by_source_total\{[^}]*source="local_compute"[^}]*\}\s+([0-9.eE+-]+)'),
        "prompt_tokens_local_cache_hit": extract(
            r'vllm:prompt_tokens_by_source_total\{[^}]*source="local_cache_hit"[^}]*\}\s+([0-9.eE+-]+)'),
        "prefix_cache_queries": extract(r'vllm:prefix_cache_queries_total\{[^}]*\}\s+([0-9.eE+-]+)'),
        "prefix_cache_hits": extract(r'vllm:prefix_cache_hits_total\{[^}]*\}\s+([0-9.eE+-]+)'),
        "num_preemptions": extract(r'vllm:num_preemptions_total\{[^}]*\}\s+([0-9.eE+-]+)'),
    }


def start_nvidia_smi(log_path, interval_ms=100):
    """Start nvidia-smi polling in background, return Popen."""
    # nvidia-smi -l only supports 1s minimum. Use dmon for sub-second:
    cmd = f"nvidia-smi dmon -i {GPU_DEVICE} -s u -d 1"
    f = open(log_path, "w")
    p = subprocess.Popen(cmd, shell=True, stdout=f, stderr=subprocess.DEVNULL)
    return p, f


def parse_nvidia_smi_dmon(log_path):
    """Parse nvidia-smi dmon output for GPU utilization."""
    utils = []
    try:
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        sm_util = int(parts[1])  # sm utilization %
                        utils.append(sm_util)
                    except ValueError:
                        pass
    except FileNotFoundError:
        pass
    if not utils:
        return {"gpu_util_mean": None, "gpu_util_samples": 0}
    return {
        "gpu_util_mean": sum(utils) / len(utils),
        "gpu_util_p50": sorted(utils)[len(utils) // 2],
        "gpu_util_p95": sorted(utils)[min(len(utils) - 1, int(0.95 * (len(utils) - 1)))],
        "gpu_util_max": max(utils),
        "gpu_util_samples": len(utils),
    }


def run_one(args, f_value, repeat, out_dir):
    """Run one sweep point: restart vLLM+TA, replay trace, collect metrics."""
    label = f"f={f_value}_r={repeat}"
    vllm_url = f"http://localhost:{args.vllm_port}"
    ta_url = f"http://localhost:{args.ta_port}"

    print(f"\n{'='*60}")
    print(f"  {label}  (d={args.duty}, C={args.concurrency})")
    print(f"{'='*60}")

    # 1. Kill existing processes
    kill_proc("vllm serve")
    kill_proc("ThunderAgent")
    time.sleep(3)

    # 2. Start vLLM
    vllm_log = os.path.join(out_dir, f"vllm_{label}.log")
    vllm_cmd = VLLM_CMD.format(venv=args.venv, vllm_port=args.vllm_port)
    env = {**os.environ, **VLLM_ENV}
    cpath = env.get("CPATH", "")
    if "/usr/include/x86_64-linux-gnu" not in cpath:
        env["CPATH"] = f"/usr/include/x86_64-linux-gnu:{cpath}" if cpath else "/usr/include/x86_64-linux-gnu"
    with open(vllm_log, "w") as lf:
        vllm_proc = subprocess.Popen(
            vllm_cmd.split(), env=env,
            stdout=lf, stderr=subprocess.STDOUT)
    print(f"  vLLM starting (pid={vllm_proc.pid})...")
    if not wait_for_health(vllm_url, timeout=120):
        print(f"  ERROR: vLLM failed to start")
        return None
    c_total = verify_c_total(vllm_url)
    print(f"  vLLM ready. C_total={c_total}")
    if c_total != EXPECTED_C_TOTAL:
        print(f"  WARNING: C_total={c_total} != expected {EXPECTED_C_TOTAL}")

    # 3. Start ThunderAgent
    ta_log = os.path.join(out_dir, f"ta_{label}.log")
    ta_cmd = TA_CMD.format(venv=args.venv, vllm_port=args.vllm_port,
                            ta_port=args.ta_port, f=f_value)
    with open(ta_log, "w") as lf:
        ta_proc = subprocess.Popen(
            ta_cmd.split(),
            stdout=lf, stderr=subprocess.STDOUT)
    time.sleep(3)
    if not wait_for_health(ta_url, timeout=30):
        print(f"  ERROR: ThunderAgent failed to start")
        vllm_proc.terminate()
        return None
    print(f"  ThunderAgent ready (f={f_value})")

    # 4. Start nvidia-smi polling
    nv_log = os.path.join(out_dir, f"nvsmi_{label}.log")
    nv_proc, nv_file = start_nvidia_smi(nv_log)

    # 5. Scrape metrics before
    m_before = scrape_metrics(vllm_url)

    # 6. Run replay
    trace_out = os.path.join(out_dir, f"turns_{label}.jsonl")
    summary_out = os.path.join(out_dir, f"summary_{label}.jsonl")
    driver_cmd = DRIVER_CMD.format(
        venv=args.venv, trace=args.trace, ta_port=args.ta_port,
        vllm_port=args.vllm_port, C=args.concurrency,
        trace_out=trace_out, summary_out=summary_out)

    print(f"  Running replay (C={args.concurrency})...")
    t0 = time.time()
    result = subprocess.run(driver_cmd, shell=True, capture_output=True, text=True,
                            timeout=600)
    wall = time.time() - t0
    print(f"  Replay done in {wall:.1f}s (rc={result.returncode})")

    # 7. Stop nvidia-smi
    nv_proc.terminate()
    nv_proc.wait()
    nv_file.close()

    # 8. Scrape metrics after
    m_after = scrape_metrics(vllm_url)

    # 9. Parse driver output
    driver_summary = {}
    if result.stdout.strip():
        try:
            driver_summary = json.loads(result.stdout.strip().split('\n')[-1])
        except json.JSONDecodeError:
            print(f"  WARNING: couldn't parse driver output")
            print(f"  stdout: {result.stdout[:500]}")

    # 10. Compute derived metrics
    d_total = m_after.get("prompt_tokens_total", 0) - m_before.get("prompt_tokens_total", 0)
    d_compute = m_after.get("prompt_tokens_local_compute", 0) - m_before.get("prompt_tokens_local_compute", 0)
    d_cached = m_after.get("prompt_tokens_local_cache_hit", 0) - m_before.get("prompt_tokens_local_cache_hit", 0)
    d_preemptions = m_after.get("num_preemptions", 0) - m_before.get("num_preemptions", 0)

    true_hit_rate = d_cached / d_total if d_total > 0 else None
    true_recompute_frac = d_compute / d_total if d_total > 0 else None
    invariant_ok = abs((d_compute + d_cached) - d_total) < 1.0 if d_total > 0 else None

    nv_stats = parse_nvidia_smi_dmon(nv_log)

    record = {
        "f": f_value,
        "repeat": repeat,
        "duty": args.duty,
        "C": args.concurrency,
        "wall_s": wall,
        "c_total": c_total,
        # from driver
        "completed": driver_summary.get("completed", 0),
        "failed": driver_summary.get("failed", 0),
        "throughput_programs_per_s": driver_summary.get("throughput_programs_per_s"),
        "throughput_tok_per_s": driver_summary.get("throughput_completion_tok_per_s"),
        "latency_mean_s": driver_summary.get("latency_mean_s"),
        "latency_p50_s": driver_summary.get("latency_p50_s"),
        "latency_p95_s": driver_summary.get("latency_p95_s"),
        "latency_max_s": driver_summary.get("latency_max_s"),
        # true hit (uncontaminated)
        "prompt_tokens_total": d_total,
        "prompt_tokens_local_compute": d_compute,
        "prompt_tokens_cached": d_cached,
        "TRUE_hit_rate": true_hit_rate,
        "TRUE_recompute_frac": true_recompute_frac,
        "invariant_ok": invariant_ok,
        # preemptions
        "num_preemptions": d_preemptions,
        # reported (possibly contaminated)
        "REPORTED_hit_rate": driver_summary.get("prefix_cache_hit_rate"),
        # GPU utilization
        **nv_stats,
    }
    print(f"  thr={record['throughput_tok_per_s']:.1f} tok/s, "
          f"TRUE_hit={true_hit_rate:.3f}, "
          f"p95={record['latency_p95_s']:.1f}s, "
          f"preemptions={d_preemptions:.0f}, "
          f"gpu_util={nv_stats.get('gpu_util_mean', '?')}%")

    # Cleanup
    ta_proc.terminate()
    vllm_proc.terminate()
    ta_proc.wait()
    vllm_proc.wait()

    return record


def main():
    ap = argparse.ArgumentParser(description="STEP 5 pilot sweep")
    ap.add_argument("--duty", type=float, default=0.1)
    ap.add_argument("--trace", required=True, help="Canonical trace JSONL")
    ap.add_argument("--concurrency", type=int, default=10, help="C = number of concurrent programs")
    ap.add_argument("--f-grid", type=str, default="1.0,1.2,1.5,1.8,2.0,2.5,3.0,1000000",
                    help="Comma-separated f values")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--venv", default="/home/yunuikang/yunuikang_work/.venv")
    ap.add_argument("--vllm-port", type=int, default=8100)
    ap.add_argument("--ta-port", type=int, default=9200)
    ap.add_argument("--out-dir", required=True, help="Output directory for all results")
    ap.add_argument("--gpu", type=str, default="0",
                    help="GPU device index (CUDA_VISIBLE_DEVICES + nvidia-smi dmon target)")
    args = ap.parse_args()

    global GPU_DEVICE
    GPU_DEVICE = args.gpu
    VLLM_ENV["CUDA_VISIBLE_DEVICES"] = args.gpu

    f_grid = [float(x.strip()) for x in args.f_grid.split(",")]
    os.makedirs(args.out_dir, exist_ok=True)

    results = []
    combined_out = os.path.join(args.out_dir, "pilot_results.jsonl")

    print(f"=== STEP 5 Pilot Sweep ===")
    print(f"  d={args.duty}, C={args.concurrency}, f_grid={f_grid}, repeats={args.repeats}")
    print(f"  trace: {args.trace}")
    print(f"  out: {args.out_dir}")

    for f_val in f_grid:
        for rep in range(args.repeats):
            record = run_one(args, f_val, rep, args.out_dir)
            if record:
                results.append(record)
                with open(combined_out, "a") as f:
                    f.write(json.dumps(record) + "\n")

    # Print summary table
    print(f"\n{'='*80}")
    print(f"  PILOT SWEEP SUMMARY (d={args.duty}, C={args.concurrency})")
    print(f"{'='*80}")
    print(f"{'f':>10} {'thr(tok/s)':>12} {'TRUE_hit':>10} {'recomp%':>10} "
          f"{'preempt':>8} {'p95(s)':>10} {'gpu%':>8}")
    print("-" * 80)
    for r in results:
        f_str = f"{r['f']:.1f}" if r['f'] < 1000 else "inf"
        thr = r.get('throughput_tok_per_s')
        thr_s = f"{thr:.1f}" if thr else "?"
        hit = r.get('TRUE_hit_rate')
        hit_s = f"{hit:.3f}" if hit is not None else "?"
        rc = r.get('TRUE_recompute_frac')
        rc_s = f"{rc:.3f}" if rc is not None else "?"
        p95 = r.get('latency_p95_s')
        p95_s = f"{p95:.1f}" if p95 else "?"
        gpu = r.get('gpu_util_mean')
        gpu_s = f"{gpu:.0f}" if gpu is not None else "?"
        print(f"{f_str:>10} {thr_s:>12} {hit_s:>10} {rc_s:>10} "
              f"{r['num_preemptions']:>8.0f} {p95_s:>10} {gpu_s:>8}")

    # Save summary
    with open(os.path.join(args.out_dir, "pilot_summary.json"), "w") as f:
        json.dump({"args": vars(args), "results": results}, f, indent=2)

    print(f"\nResults saved to {args.out_dir}/")


if __name__ == "__main__":
    main()
