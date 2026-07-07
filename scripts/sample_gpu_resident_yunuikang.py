#!/usr/bin/env python3
"""Experiment C GPU util + resident sampler (isolated to chosen GPUs).

Polls, every --interval seconds:
  * nvidia-smi for the GPUs given by --gpus (index-filtered so it NEVER reads
    the SWE-sweep GPUs) -> utilization.gpu, memory.used
  * the ThunderAgent proxy /health per_backend -> reasoning / acting / paused
  * each vLLM backend /metrics -> vllm:num_requests_running (occupancy witness)

resident(k_fit) = reasoning + acting per backend.  REASONING busy = reasoning>0.
Writes one CSV row per tick (append-safe, header written once).

Usage:
  sample_gpu_resident_yunuikang.py --gpus 2,3 \
     --health-url http://localhost:9001/health \
     --backends http://localhost:8002,http://localhost:8003 \
     --out scratch/expC/sample_<router>_c<C>.csv [--interval 1.0]
"""
import argparse, csv, subprocess, sys, time, urllib.request, json, re, os


def nvidia_smi(gpus):
    """Return {idx: (util_pct, mem_used_mib)} for the given index list only."""
    ids = ",".join(str(g) for g in gpus)
    try:
        out = subprocess.run(
            ["nvidia-smi", f"--id={ids}",
             "--query-gpu=index,utilization.gpu,memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return {}
    res = {}
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 3:
            try:
                res[int(parts[0])] = (int(float(parts[1])), int(float(parts[2])))
            except ValueError:
                pass
    return res


def get_json(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


_NRR_RE = re.compile(r'^vllm:num_requests_running(?:\{[^}]*\})?\s+([0-9.eE+-]+)', re.M)


def vllm_nrr(base_url, timeout=3):
    """num_requests_running from a vLLM /metrics endpoint, or '' on failure."""
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/metrics", timeout=timeout) as r:
            body = r.read().decode()
    except Exception:
        return ""
    m = _NRR_RE.findall(body)
    if not m:
        return ""
    try:
        return int(float(m[-1]))
    except ValueError:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpus", default="2,3", help="comma GPU indices to sample (ONLY these)")
    ap.add_argument("--health-url", default="http://localhost:9001/health")
    ap.add_argument("--backends", default="http://localhost:8002,http://localhost:8003")
    ap.add_argument("--out", required=True)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--dry", action="store_true", help="one tick, print header+row, exit")
    args = ap.parse_args()

    gpus = [int(x) for x in args.gpus.split(",") if x.strip() != ""]
    backends = [b.strip() for b in args.backends.split(",") if b.strip()]
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)

    # header: t, per-gpu util/mem, per-backend reasoning/acting/paused/nrr, paused_total
    cols = ["t"]
    for g in gpus:
        cols += [f"gpu{g}_util", f"gpu{g}_mem"]
    for i, _ in enumerate(backends):
        cols += [f"b{i}_reasoning", f"b{i}_acting", f"b{i}_paused", f"b{i}_nrr"]
    cols += ["paused_total"]

    new_file = not os.path.exists(args.out) or os.path.getsize(args.out) == 0
    f = open(args.out, "a", newline="")
    w = csv.writer(f)
    if new_file:
        w.writerow(cols)
        f.flush()

    t0 = time.time()
    while True:
        tick = time.time()
        smi = nvidia_smi(gpus)
        health = get_json(args.health_url)
        pb = (health or {}).get("per_backend", {}) if health else {}
        row = [round(tick - t0, 2)]
        for g in gpus:
            u, m = smi.get(g, ("", ""))
            row += [u, m]
        paused_total = (health or {}).get("paused_count", "") if health else ""
        for b in backends:
            d = pb.get(b, {})
            row += [d.get("reasoning", ""), d.get("acting", ""),
                    d.get("paused", ""), vllm_nrr(b)]
        row += [paused_total]
        w.writerow(row)
        f.flush()
        if args.dry:
            print(",".join(cols))
            print(",".join(str(x) for x in row))
            return
        # drift-corrected sleep
        nxt = tick + args.interval
        time.sleep(max(0.0, nxt - time.time()))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
