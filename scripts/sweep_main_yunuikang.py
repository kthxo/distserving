#!/usr/bin/env python3
"""STEP 5 — Main sweep: transition point fit×d* precision measurement.

Binary tr(f=1) vs default(f=∞) comparison across dense fit×d grid.
Measures where the optimal policy flips from default to tr.

Grid:
  fit×d ∈ {0.50, 0.60, 0.65, 0.70, 0.75, 0.80, 0.90}
  f    ∈ {1.0, 1000000}  (tr vs default)
  C    ∈ {10, 20}        (2×fit, 4×fit — C-stability check)
  REPEAT = 3             (error bars at transition)

Protocol (per point):
  1. vLLM restart → clean prefix cache, pinned C_total=95,936
  2. ThunderAgent restart → --capacity-overcommit-factor f
  3. nvidia-smi dmon 1s polling
  4. Scrape vLLM metrics before/after for true hit (prompt_tokens_by_source)
  5. trace_replay_driver_expC → thr/latency/preemptions (--stream)

작성: 강윤의 · 2026-07-20 · STEP 5 main sweep
"""
import argparse
import json
import os
import re
import subprocess
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
FIT = 95936 / 20150  # 4.76109

# Grid definition
FITD_GRID = [0.50, 0.60, 0.65, 0.70, 0.75, 0.80, 0.90]
F_GRID = [1.0, 1000000.0]
C_GRID = [10, 20]
REPEATS = 3

# Trace paths (pre-generated)
TRACE_DIR = "scratch/step5/main_sweep/traces"


def d_from_fitd(fitd):
    """Compute d from fit×d target."""
    return fitd / FIT


def trace_path(fitd):
    """Get trace file path for a fit×d target."""
    d = d_from_fitd(fitd)
    return os.path.join(TRACE_DIR, f"synth_fd{fitd:.2f}_d{d:.5f}_v3.jsonl")


def kill_proc(name_pattern):
    subprocess.run(f"pkill -f '{name_pattern}'", shell=True, capture_output=True)
    time.sleep(2)


def wait_for_health(url, timeout=120):
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


def start_nvidia_smi(log_path):
    cmd = "nvidia-smi dmon -i 0 -s u -d 1"
    f = open(log_path, "w")
    p = subprocess.Popen(cmd, shell=True, stdout=f, stderr=subprocess.DEVNULL)
    return p, f


def parse_nvidia_smi_dmon(log_path):
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
                        utils.append(int(parts[1]))
                    except ValueError:
                        pass
    except FileNotFoundError:
        pass
    if not utils:
        return {"gpu_util_mean": None, "gpu_util_samples": 0}
    s = sorted(utils)
    n = len(s)
    return {
        "gpu_util_mean": sum(s) / n,
        "gpu_util_p50": s[n // 2],
        "gpu_util_p95": s[min(n - 1, int(0.95 * (n - 1)))],
        "gpu_util_max": max(s),
        "gpu_util_samples": n,
    }


def run_one(args, fitd, f_value, C, repeat, out_dir):
    """Run one sweep point."""
    d = d_from_fitd(fitd)
    trace = trace_path(fitd)
    label = f"fd{fitd:.2f}_f={'inf' if f_value > 1000 else f'{f_value:.0f}'}_C{C}_r{repeat}"
    vllm_url = f"http://localhost:{args.vllm_port}"
    ta_url = f"http://localhost:{args.ta_port}"

    print(f"\n{'='*60}")
    print(f"  {label}  (fit×d={fitd}, d={d:.5f}, f={f_value}, C={C})")
    print(f"{'='*60}")

    # Verify trace exists
    if not os.path.exists(trace):
        print(f"  ERROR: trace not found: {trace}")
        return None

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
    if not wait_for_health(vllm_url, timeout=180):
        print(f"  ERROR: vLLM failed to start")
        vllm_proc.terminate()
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
        ta_proc.terminate()
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
        venv=args.venv, trace=trace, ta_port=args.ta_port,
        vllm_port=args.vllm_port, C=C,
        trace_out=trace_out, summary_out=summary_out)

    print(f"  Running replay (C={C})...")
    t0 = time.time()
    result = subprocess.run(driver_cmd, shell=True, capture_output=True, text=True,
                            timeout=900)
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
        "fitd": fitd,
        "d": round(d, 5),
        "f": f_value,
        "C": C,
        "repeat": repeat,
        "wall_s": wall,
        "c_total": c_total,
        "completed": driver_summary.get("completed", 0),
        "failed": driver_summary.get("failed", 0),
        "throughput_programs_per_s": driver_summary.get("throughput_programs_per_s"),
        "throughput_tok_per_s": driver_summary.get("throughput_completion_tok_per_s"),
        "latency_mean_s": driver_summary.get("latency_mean_s"),
        "latency_p50_s": driver_summary.get("latency_p50_s"),
        "latency_p95_s": driver_summary.get("latency_p95_s"),
        "latency_max_s": driver_summary.get("latency_max_s"),
        "prompt_tokens_total": d_total,
        "prompt_tokens_local_compute": d_compute,
        "prompt_tokens_cached": d_cached,
        "TRUE_hit_rate": true_hit_rate,
        "TRUE_recompute_frac": true_recompute_frac,
        "invariant_ok": invariant_ok,
        "num_preemptions": d_preemptions,
        "REPORTED_hit_rate": driver_summary.get("prefix_cache_hit_rate"),
        **nv_stats,
    }

    thr_s = f"{record['throughput_tok_per_s']:.1f}" if record['throughput_tok_per_s'] else "?"
    hit_s = f"{true_hit_rate:.3f}" if true_hit_rate is not None else "?"
    p95_s = f"{record['latency_p95_s']:.1f}" if record['latency_p95_s'] else "?"
    gpu_s = f"{nv_stats.get('gpu_util_mean', '?')}"
    print(f"  thr={thr_s} tok/s, TRUE_hit={hit_s}, p95={p95_s}s, "
          f"preempt={d_preemptions:.0f}, gpu={gpu_s}%")

    # Cleanup
    ta_proc.terminate()
    vllm_proc.terminate()
    ta_proc.wait()
    vllm_proc.wait()

    return record


def main():
    ap = argparse.ArgumentParser(description="STEP 5 main sweep: transition point measurement")
    ap.add_argument("--venv", default="/home/yunuikang/yunuikang_work/.venv")
    ap.add_argument("--vllm-port", type=int, default=8100)
    ap.add_argument("--ta-port", type=int, default=9200)
    ap.add_argument("--out-dir", default="scratch/step5/main_sweep")
    ap.add_argument("--resume-from", type=int, default=0,
                    help="Resume from run index N (skip first N runs)")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    # Build grid: iterate in order fitd → C → f → repeat
    grid = []
    for fitd in FITD_GRID:
        for C in C_GRID:
            for f_val in F_GRID:
                for rep in range(REPEATS):
                    grid.append((fitd, C, f_val, rep))

    total = len(grid)
    combined_out = os.path.join(args.out_dir, "sweep_results.jsonl")

    print(f"{'='*80}")
    print(f"  STEP 5 MAIN SWEEP — Transition Point Measurement")
    print(f"{'='*80}")
    print(f"  fit×d grid: {FITD_GRID}")
    print(f"  f grid: {F_GRID}")
    print(f"  C grid: {C_GRID}")
    print(f"  repeats: {REPEATS}")
    print(f"  total runs: {total}")
    print(f"  resume from: {args.resume_from}")
    print(f"  out: {args.out_dir}")
    print()

    results = []
    for idx, (fitd, C, f_val, rep) in enumerate(grid):
        if idx < args.resume_from:
            continue

        print(f"\n>>> Run {idx+1}/{total} <<<")
        record = run_one(args, fitd, f_val, C, rep, args.out_dir)
        if record:
            record["run_index"] = idx
            results.append(record)
            with open(combined_out, "a") as f:
                f.write(json.dumps(record) + "\n")

    # Print summary table
    print(f"\n{'='*100}")
    print(f"  SWEEP COMPLETE — {len(results)}/{total} runs succeeded")
    print(f"{'='*100}")
    print(f"{'fit×d':>7} {'C':>4} {'f':>6} {'rep':>4} {'thr(tok/s)':>12} "
          f"{'TRUE_hit':>10} {'p95(s)':>10} {'preempt':>8} {'gpu%':>8}")
    print("-" * 100)
    for r in results:
        f_str = "inf" if r['f'] > 1000 else f"{r['f']:.0f}"
        thr = r.get('throughput_tok_per_s')
        thr_s = f"{thr:.1f}" if thr else "?"
        hit = r.get('TRUE_hit_rate')
        hit_s = f"{hit:.3f}" if hit is not None else "?"
        p95 = r.get('latency_p95_s')
        p95_s = f"{p95:.1f}" if p95 else "?"
        gpu = r.get('gpu_util_mean')
        gpu_s = f"{gpu:.0f}" if gpu is not None else "?"
        print(f"{r['fitd']:>7.2f} {r['C']:>4} {f_str:>6} {r['repeat']:>4} "
              f"{thr_s:>12} {hit_s:>10} {p95_s:>10} {r['num_preemptions']:>8.0f} {gpu_s:>8}")

    print(f"\nResults saved to {combined_out}")


if __name__ == "__main__":
    main()
