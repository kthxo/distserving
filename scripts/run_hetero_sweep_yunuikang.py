#!/usr/bin/env python3
"""Phase F (homo-hetero) sweep orchestrator: 4090 + 5090, PER-BACKEND metrics.

For each (concurrency, repeat) it:
  1. snapshots each backend's prefix-cache queries/hits + prompt_tokens (reprefill),
  2. samples each backend's kv_cache_usage_perc AND the proxy's per-backend `paused`
     count in a background thread while the synthetic driver runs,
  3. runs workload_driver_yunuikang.py (synthetic §9 KV-pressure workload) as a
     subprocess against the proxy,
  4. records per-backend {split(queries), hit_rate, reprefill_tokens, kv_usage
     peak/mean, paused peak} + the driver's global summary.

Restarts the ThunderAgent proxy in the requested router mode (tr|default) with the
two cross-node backends. Does NOT touch the vLLM backends.

Hypothesis (EXPERIMENT_LOG §12 H1): tr's absolute-token balancing overloads the
smaller 4090 first -> 4090 shows higher KV usage / more pauses / lower hit rate /
more reprefill than the 5090, while the 5090 stays under-utilized.
"""
import argparse
import json
import re
import subprocess
import threading
import time
import urllib.request
from typing import Dict, List

REPO = "/home/yunuikang/yunuikang_work/distserving"


def _get(url: str, timeout: float = 5) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _metric_sum(text: str, metric: str) -> float:
    total = 0.0
    for m in re.finditer(rf"^{re.escape(metric)}(?:{{[^}}]*}})?\s+([0-9.eE+-]+)$", text, re.M):
        try:
            total += float(m.group(1))
        except ValueError:
            pass
    return total


def scrape_backend(url: str) -> Dict[str, float]:
    try:
        t = _get(f"{url}/metrics")
    except Exception:
        return {}
    return {
        "queries": _metric_sum(t, "vllm:prefix_cache_queries_total"),
        "hits": _metric_sum(t, "vllm:prefix_cache_hits_total"),
        "prompt_tokens": _metric_sum(t, "vllm:prompt_tokens_total"),
        "kv_usage": _metric_sum(t, "vllm:kv_cache_usage_perc"),
    }


def proxy_paused(proxy: str) -> Dict[str, int]:
    """Return {backend_url: paused_count} from proxy /health per_backend."""
    try:
        d = json.loads(_get(f"{proxy}/health"))
    except Exception:
        return {}
    return {b: (v.get("paused", 0) + v.get("marked_for_pause", 0))
            for b, v in d.get("per_backend", {}).items()}


class Sampler(threading.Thread):
    """Polls kv_cache_usage_perc per backend + proxy paused counts until stopped."""
    def __init__(self, backends: Dict[str, str], proxy: str, interval: float = 1.0):
        super().__init__(daemon=True)
        self.backends = backends            # label -> url
        self.proxy = proxy
        self.interval = interval
        self._stop_evt = threading.Event()
        self.kv_peak = {lab: 0.0 for lab in backends}
        self.kv_sum = {lab: 0.0 for lab in backends}
        self.paused_peak = {lab: 0 for lab in backends}
        self.n = 0

    def run(self):
        while not self._stop_evt.is_set():
            self.n += 1
            for lab, url in self.backends.items():
                s = scrape_backend(url)
                kv = s.get("kv_usage", 0.0)
                self.kv_peak[lab] = max(self.kv_peak[lab], kv)
                self.kv_sum[lab] += kv
            paused = proxy_paused(self.proxy)
            for lab, url in self.backends.items():
                self.paused_peak[lab] = max(self.paused_peak[lab], paused.get(url, 0))
            self._stop_evt.wait(self.interval)

    def stop(self):
        self._stop_evt.set()


def restart_proxy(router: str, backend_urls: List[str], proxy_port: int, logdir: str):
    subprocess.run("pkill -f 'bin/thunderagent'", shell=True)
    time.sleep(3)
    log = f"{logdir}/thunderagent_phaseF_{router}.log"
    cmd = ["thunderagent", "--backend-type", "vllm", "--backends", ",".join(backend_urls),
           "--port", str(proxy_port), "--router", router, "--metrics", "--profile"]
    with open(log, "w") as f:
        subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
    proxy = f"http://localhost:{proxy_port}"
    for _ in range(30):
        try:
            d = json.loads(_get(f"{proxy}/health", timeout=3))
            if d.get("router_mode") == router and len(d.get("backends", [])) == len(backend_urls):
                return proxy
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError(f"proxy did not come up in {router} mode")


def run_point(args, backends, proxy, C, rep) -> dict:
    urls = list(backends.values())
    before = {lab: scrape_backend(url) for lab, url in backends.items()}
    sampler = Sampler(backends, proxy, interval=args.sample_interval)
    sampler.start()
    nprog = max(args.nprog, C)
    if args.trace:
        # real-trace load source (trace_replay_driver); per-backend sampling identical
        cmd = [
            "python", f"{REPO}/scripts/trace_replay_driver_yunuikang.py",
            "--trace", args.trace,
            "--base-url", proxy, "--router-url", proxy, "--backends", ",".join(urls),
            "--concurrency", str(C), "--num-programs", str(nprog), "--router", args.router,
        ]
    else:
        cmd = [
            "python", f"{REPO}/scripts/workload_driver_yunuikang.py",
            "--base-url", proxy, "--router-url", proxy, "--backends", ",".join(urls),
            "--concurrency", str(C), "--num-programs", str(nprog),
            "--turns", str(args.turns), "--tool-sleep", str(args.tool_sleep),
            "--max-tokens", str(args.max_tokens), "--ctx-tokens", str(args.ctx_tokens),
            "--router", args.router,
        ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    sampler.stop(); sampler.join(timeout=5)
    after = {lab: scrape_backend(url) for lab, url in backends.items()}
    try:
        drv = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        drv = {"completed": None, "failed": None, "error": proc.stderr[-300:]}

    per_backend = {}
    for lab in backends:
        b, a = before.get(lab, {}), after.get(lab, {})
        qd = a.get("queries", 0) - b.get("queries", 0)
        hd = a.get("hits", 0) - b.get("hits", 0)
        pt = a.get("prompt_tokens", 0) - b.get("prompt_tokens", 0)
        per_backend[lab] = {
            "queries_delta": qd, "hits_delta": hd,
            "hit_rate": (hd / qd) if qd else None,
            "reprefill_prompt_tokens": pt,
            "kv_usage_peak": round(sampler.kv_peak[lab], 4),
            "kv_usage_mean": round(sampler.kv_sum[lab] / sampler.n, 4) if sampler.n else None,
            "paused_peak": sampler.paused_peak[lab],
        }
    return {
        "router": args.router, "concurrency": C, "repeat": rep,
        "completed": drv.get("completed"), "failed": drv.get("failed"),
        "throughput_programs_per_s": drv.get("throughput_programs_per_s"),
        "latency_p95_s": drv.get("latency_p95_s"),
        "prefix_cache_hit_rate_global": drv.get("prefix_cache_hit_rate"),
        "per_backend": per_backend,
        "workload": ({"trace": args.trace, "num_programs": nprog} if args.trace else
                     {"ctx_tokens": args.ctx_tokens, "turns": args.turns,
                      "tool_sleep": args.tool_sleep, "max_tokens": args.max_tokens,
                      "num_programs": nprog}),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--router", required=True, choices=["tr", "default"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--backend-labels", required=True,
                    help="comma list label=url, e.g. 4090=http://IP1:8000,5090=http://IP2:8000")
    ap.add_argument("--proxy-port", type=int, default=9000)
    ap.add_argument("--logdir", default="/home/yunuikang/yunuikang_work/scratch")
    ap.add_argument("--concurrencies", default="8 16 24 32 48")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--nprog", type=int, default=48)
    ap.add_argument("--trace", default="",
                    help="if set, load source = trace_replay_driver with this canonical trace "
                         "(real workload); otherwise synthetic workload_driver")
    # §9 KV-pressure synthetic workload defaults
    ap.add_argument("--ctx-tokens", type=int, default=3000)
    ap.add_argument("--turns", type=int, default=3)
    ap.add_argument("--tool-sleep", type=float, default=0.5)
    ap.add_argument("--max-tokens", type=int, default=96)
    ap.add_argument("--sample-interval", type=float, default=1.0)
    args = ap.parse_args()

    backends = {}
    for tok in args.backend_labels.split(","):
        lab, url = tok.split("=", 1)
        backends[lab.strip()] = url.strip()
    concs = [int(x) for x in args.concurrencies.split()]

    proxy = restart_proxy(args.router, list(backends.values()), args.proxy_port, args.logdir)
    print(f"proxy up: {args.router} {list(backends.values())}")
    open(args.out, "w").close()
    for C in concs:
        for rep in range(1, args.repeat + 1):
            res = run_point(args, backends, proxy, C, rep)
            with open(args.out, "a") as f:
                f.write(json.dumps(res) + "\n")
            pb = res["per_backend"]
            desc = " ".join(
                f"{lab}[kv={pb[lab]['kv_usage_peak']:.2f} hit={(pb[lab]['hit_rate'] or 0):.2f} "
                f"pause={pb[lab]['paused_peak']} q={int(pb[lab]['queries_delta'])}]"
                for lab in backends)
            print(f"  {args.router} c={C} r={rep} comp={res['completed']}/{res['workload']['num_programs']} "
                  f"thru={res['throughput_programs_per_s']:.2f} | {desc}")
    print(f"done: {args.out}")


if __name__ == "__main__":
    main()
