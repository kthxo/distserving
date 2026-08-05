#!/usr/bin/env python3
"""§7.1b fit gate — does `--max-total-tokens` ACTUALLY take effect?

Plan: plans/2026-08-04_PLAN_h200-rescale-reproduction_yunuikang.md (rev3), risk 7.1b:
"--max-total-tokens가 안 먹거나 다른 값으로 착지 => fit 스윕이 성립 안 함 = 계획 전체 무효."
This gate runs on EVERY fit cell (Phase 1) before the cell is allowed to count.

WHY FIVE LAYERS. Reading the boot log line `max_total_num_tokens=N` only proves the
engine SAYS N. It does not prove the allocator ENFORCES N. So:

  G0 boot prerequisites   engine up, right model, TP1, YaRN actually applied
  G1 declared             log value vs target, cap semantics, fit bounds
  G2 four-source ledger   log == /metrics gauge == cache_config_info == /get_server_info
  G2b physical VRAM       nvidia-smi vs weights+pool  (WARN-ONLY, never blocks)
  G3 host tier            hicache_host_total_tokens ~= r x N   (RATIO>0 cells only)
  G4 behavioural probe    load the engine past N and watch the allocator   <-- THE POINT
  G6 two-point slope      dN/dMAXTOK == 1.00 +- 0.05 across two cells (--slope-check)

G4 measures ACTUAL resident capacity by eviction arithmetic. Every offered token is
either still in the pool or was evicted from it, so

    resident_est = offered_unique_tokens - delta(evicted_tokens_total)

and when the probe offers more than the pool holds, resident_est IS the real capacity.
Its two bounds catch opposite failures, and P-c guards the whole thing:
  P-a  resident_est <= 1.05 x N           catches "cap ignored, the real pool is the 2.1M
                                          profiled one" (all 1.60 x N offered would fit)
  P-b  resident_est >= 0.80 x N           catches "LEDGER > ACTUAL" — the only axis that
                                          does. All four G2 sources read the same ledger,
                                          so a real capacity of e.g. 100k passes G2 cleanly.
  P-c  delta evicted_tokens_total > 0     catches "the cap was never reached" (probe too
                                          weak), which would make resident_est meaningless

WHY NOT num_used_tokens — 2026-08-05 amendment, see PREREG §9.3. The first version of this
gate read `sglang:num_used_tokens` for P-a/P-b. That gauge is
    num_used = max_total_num_tokens - (available_size + evictable_size)
[measured: managers/scheduler_runtime_checker_mixin.py:44-49], i.e. it EXCLUDES the radix
cache's evictable residency and counts only in-flight protected KV. Two consequences:
  * P-b was unreachable by construction — in-flight is bounded by concurrency x prompt
    (4 x 32,376 = 129,504), and the observed peak was 128,705, 99.4% of that bound, never
    the 0.80 x 262,246 = 209,797 the criterion asked for. It FAILED on the F1 run.
  * P-a was an arithmetic identity — num_used <= N holds always, so it could not fail even
    if the cap were ignored (the value would go negative, not above N).
The 0.80 fraction is UNCHANGED; only the quantity it applies to was corrected. The original
F1 FAIL record stands; the corrected run is a separate label (F1b).

EVERYTHING in PREREG below — thresholds AND the probe load spec — is pre-registered and
frozen before the first boot (see logs/2026-08-05_H200_GATE_PREREG_yunuikang.md, committed
before execution). If the probe load ever needs to change, that is a NEW labelled run
recorded alongside the original, never a replacement.

Usage:
  # per-cell gate (static only)
  python fit_gate_yunuikang.py --target-maxtok 262246 --log serve.log --out gate.jsonl --tag F1
  # F1 verification (adds the behavioural probe)
  python fit_gate_yunuikang.py --target-maxtok 262246 --log serve.log --probe --tag F1_probe ...
  # two-point sensitivity, after >=2 records exist
  python fit_gate_yunuikang.py --slope-check gate.jsonl

Exit code 0 = no FAIL (WARN allowed), 1 = at least one FAIL.
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

# ─────────────────────────────────────────────────────────────────────────────
# PRE-REGISTERED CONSTANTS — frozen before the first boot. Do not edit after
# seeing a result; a changed threshold makes the gate unfalsifiable.
# ─────────────────────────────────────────────────────────────────────────────
PREREG = {
    # fit definition
    "FIT_DEN": 32376,          # Track M ctx median [측정] = median(input_tokens) over
                               # 117,257 turns of tracelab_moriM_L64k. Tokenizer-INDEPENDENT:
                               # the trace stores integer token counts, and the driver uses
                               # the tokenizer only as a Padder to hit them. Reproduced
                               # exactly on this box 2026-08-05. Same denominator as the
                               # 5090 runs, which is what makes F1 vs 5090 C80 comparable.
    "KV_KIB_PER_TOK": 56,      # Qwen2.5-7B: 2 x 28L x 4kv x 128hd x 2B [측정, config.json]
    "WEIGHTS_GIB": 14.19,      # safetensors index total_size [측정]
    "GPU_TOTAL_GIB": 140.40,   # 143771 MiB [측정, nvidia-smi]
    # G1
    "TOL_PCT": 5.0,            # plan §5.1 Phase 0: "목표 ±5% 이내"
    "FIT_MAX": 30.0,           # plan risk 7.6 upper bound (rev2 uses fit26 intentionally)
    "CONTEXT_LEN": 71680,      # plan §5.2 (--context-length), YaRN 2.1875 x 32768
    # G3
    "HOST_TOL_PCT": 2.0,       # same tolerance as the 5090 run_phase2_rsweep assert
    # G4 — probe load spec is pre-registered too, not a tunable calibration
    "PROBE_N_REQ": 13,         # 13 x 32376 = 420,888 tok = 1.60 x N at F1
    "PROBE_PROMPT_TOK": 32376, # = ctx median, keeps the probe on-regime
    "PROBE_CONCURRENCY": 4,
    "PROBE_MAX_NEW_TOKENS": 8,
    "PROBE_SAMPLE_HZ": 1.0,
    "P_B_FRAC": 0.80,          # P-b: resident_est >= 0.80 x N. The FRACTION is unchanged
                               # from the original pre-registration; only the quantity it
                               # applies to was corrected (PREREG §9.3).
    "P_A_UPPER": 1.05,         # P-a: resident_est <= 1.05 x N. 5% = the tolerance TOL_PCT
                               # already uses; absorbs the 1 Hz counter edge and the
                               # shared-prefix correction.
    # G6
    "SLOPE_TOL": 0.05,         # dN/dMAXTOK == 1.00 +- 0.05
}

FAIL, PASS, WARN, SKIP = "FAIL", "PASS", "WARN", "SKIP"


# ── small helpers ────────────────────────────────────────────────────────────
def http_get(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode()


def http_post_json(url, payload, timeout=600):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode())


def metric_value(body, name):
    """Scalar metric value (max across TP ranks for counters/gauges)."""
    rx = re.compile(r"^" + re.escape(name) + r"(?:\{[^}]*\})?\s+([0-9.eE+-]+)", re.M)
    v = [float(x) for x in rx.findall(body)]
    return max(v) if v else None


def metric_labels(body, name):
    """Label dict of the first sample of an info-style metric."""
    m = re.search(r"^" + re.escape(name) + r"\{([^}]*)\}", body, re.M)
    if not m:
        return None
    out = {}
    for kv in re.findall(r'(\w+)="([^"]*)"', m.group(1)):
        out[kv[0]] = kv[1]
    return out


def find_key(obj, key):
    """Recursive first-match lookup in nested dict/list."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = find_key(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_key(v, key)
            if r is not None:
                return r
    return None


def pct_err(got, want):
    return abs(got - want) / want * 100.0 if want else float("inf")


class Report:
    def __init__(self):
        self.checks = []

    def add(self, cid, status, detail, **values):
        self.checks.append({"id": cid, "status": status, "detail": detail, **values})
        icon = {PASS: "PASS", FAIL: "FAIL", WARN: "WARN", SKIP: "SKIP"}[status]
        print(f"  [{icon}] {cid:6s} {detail}")
        return status

    @property
    def failed(self):
        return [c for c in self.checks if c["status"] == FAIL]


# ── G0 boot prerequisites ────────────────────────────────────────────────────
def g0_boot(rep, backend, logtext, expect_model, expect_tp):
    try:
        health = http_get(backend + "/health", timeout=10)
        rep.add("G0.1", PASS, f"/health reachable ({backend})", health=health[:80])
    except Exception as e:
        rep.add("G0.1", FAIL, f"/health unreachable: {e!r}")
        return False

    try:
        info = json.loads(http_get(backend + "/get_model_info", timeout=10))
        path = str(info.get("model_path", ""))
        ok = expect_model.lower() in path.lower()
        rep.add("G0.2", PASS if ok else FAIL,
                f"model_path={path} (expect contains {expect_model})", model_path=path)
    except Exception as e:
        rep.add("G0.2", FAIL, f"/get_model_info failed: {e!r}")

    m = re.search(r"context_len=(\d+)", logtext)
    if not m:
        rep.add("G0.3", FAIL, "context_len= not found in boot log (engine never printed the "
                              "scheduler line?)")
    else:
        clen = int(m.group(1))
        ok = clen == PREREG["CONTEXT_LEN"]
        rep.add("G0.3", PASS if ok else FAIL,
                f"context_len={clen:,} (expect {PREREG['CONTEXT_LEN']:,}) "
                f"-> YaRN override {'applied' if ok else 'NOT applied — check YARN_KEY'}",
                context_len=clen)

    try:
        si = json.loads(http_get(backend + "/get_server_info", timeout=10))
        tp = find_key(si, "tp_size")
        ok = tp == expect_tp
        rep.add("G0.4", PASS if ok else FAIL, f"tp_size={tp} (expect {expect_tp})", tp_size=tp)
    except Exception as e:
        rep.add("G0.4", WARN, f"/get_server_info unavailable for tp check: {e!r}")
    return True


# ── G1 declared value ────────────────────────────────────────────────────────
def g1_declared(rep, logtext, target):
    hits = re.findall(r"max_total_num_tokens=(\d+)", logtext)
    if not hits:
        rep.add("G1.1", FAIL, "max_total_num_tokens= absent from boot log")
        return None
    n = int(hits[-1])
    fit = n / PREREG["FIT_DEN"]
    fit_target = target / PREREG["FIT_DEN"]
    err = pct_err(n, target)

    rep.add("G1.1", PASS if err <= PREREG["TOL_PCT"] else FAIL,
            f"pool={n:,} tok vs target {target:,} (err {err:.3f}%, tol {PREREG['TOL_PCT']}%)",
            pool_tokens=n, target_tokens=target, err_pct=round(err, 4))
    rep.add("G1.2", PASS if n <= target else FAIL,
            f"cap semantics: pool <= target ({n:,} <= {target:,}) — capacity=min(profiled,user)",
            )
    rep.add("G1.3", PASS if fit <= PREREG["FIT_MAX"] else FAIL,
            f"fit={fit:.3f} (target {fit_target:.3f}, upper bound {PREREG['FIT_MAX']} per §7.6)",
            fit=round(fit, 4), fit_target=round(fit_target, 4))

    warned = re.search(r"is larger than the profiled value", logtext)
    rep.add("G1.4", FAIL if warned else PASS,
            "engine WARNED that the request exceeds the profiled pool -> the cap did NOT "
            "bind, the natural pool is in use (fit sweep invalid)" if warned
            else "no 'larger than the profiled value' warning (cap bound)",
            profiled_warning=bool(warned))
    return n


# ── G2 four-source ledger + G2b physical ─────────────────────────────────────
def g2_sources(rep, backend, log_n, target):
    body = None
    try:
        body = http_get(backend + "/metrics", timeout=15)
    except Exception as e:
        rep.add("G2.1", FAIL, f"/metrics unreachable (is --enable-metrics on?): {e!r}")

    gauge = metric_value(body, "sglang:max_total_num_tokens") if body else None
    cc = metric_labels(body, "sglang:cache_config_info") if body else None
    page_size = num_pages = ledger = None
    if cc:
        try:
            page_size = int(cc.get("page_size"))
            num_pages = int(cc.get("num_pages"))
            ledger = page_size * num_pages
        except (TypeError, ValueError):
            pass

    srv_arg = srv_page = None
    try:
        si = json.loads(http_get(backend + "/get_server_info", timeout=10))
        srv_arg = find_key(si, "max_total_tokens")
        srv_page = find_key(si, "page_size")
    except Exception:
        pass

    if gauge is not None:
        rep.add("G2.1", PASS if int(gauge) == log_n else FAIL,
                f"sglang:max_total_num_tokens={int(gauge):,} vs log {log_n:,}",
                gauge=int(gauge))
    if ledger is not None:
        rep.add("G2.2", PASS if ledger == log_n else FAIL,
                f"I6 ledger cache_config_info: page_size={page_size} x num_pages={num_pages:,} "
                f"= {ledger:,} vs log {log_n:,}",
                page_size=page_size, num_pages=num_pages, ledger_tokens=ledger)
    else:
        rep.add("G2.2", FAIL, "sglang:cache_config_info absent — I6 ledger unverifiable")

    if srv_arg is not None:
        rep.add("G2.3", PASS if int(srv_arg) == target else FAIL,
                f"/get_server_info max_total_tokens={int(srv_arg):,} vs requested {target:,}",
                server_info_arg=int(srv_arg), server_info_page_size=srv_page)
    else:
        rep.add("G2.3", WARN, "/get_server_info did not expose max_total_tokens")

    p = page_size or srv_page
    if p:
        expect = (target // int(p)) * int(p)
        rep.add("G2.4", PASS if log_n == expect else FAIL,
                f"page alignment fully explains the residual: floor({target:,}/{p})x{p} "
                f"= {expect:,} vs pool {log_n:,}", page_aligned_expect=expect)
    else:
        rep.add("G2.4", WARN, "page_size unknown — alignment identity not checked")


def g2b_vram(rep, log_n):
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=20).stdout.strip().splitlines()[0]
        used_gib = float(out) / 1024.0
    except Exception as e:
        rep.add("G2b", WARN, f"nvidia-smi unreadable: {e!r}")
        return
    kv_gib = log_n * PREREG["KV_KIB_PER_TOK"] / 1024.0 / 1024.0
    floor_gib = PREREG["WEIGHTS_GIB"] + kv_gib
    reserved_gib = PREREG["GPU_TOTAL_GIB"] * 0.90
    # WARN-ONLY BY DESIGN: mem-fraction-static may pre-reserve regardless of the cap, which
    # would look like "cap not physical" while the experiment is perfectly valid. We record
    # the number and let G4 decide. Never a blocker — a false FAIL here would kill a valid plan.
    note = "consistent with a capped pool" if used_gib < reserved_gib * 0.85 else \
           "close to the mem-fraction reservation — pool may be pre-reserved, see G4"
    rep.add("G2b", WARN, f"VRAM used={used_gib:.1f} GiB; weights+KV floor={floor_gib:.1f} GiB "
                         f"(KV {kv_gib:.1f}); 0.90x{PREREG['GPU_TOTAL_GIB']:.1f}="
                         f"{reserved_gib:.1f} GiB -> {note}",
            vram_used_gib=round(used_gib, 2), kv_expect_gib=round(kv_gib, 2))


# ── G3 host tier ─────────────────────────────────────────────────────────────
def g3_host(rep, backend, log_n, ratio):
    if not ratio or float(ratio) == 0.0:
        rep.add("G3", SKIP, "RATIO=0 (HiCache off) — host tier not applicable to this cell")
        return
    try:
        body = http_get(backend + "/metrics", timeout=15)
    except Exception as e:
        rep.add("G3", FAIL, f"/metrics unreachable: {e!r}")
        return
    host = metric_value(body, "sglang:hicache_host_total_tokens")
    if host is None:
        rep.add("G3", FAIL, "sglang:hicache_host_total_tokens absent although RATIO>0")
        return
    want = float(ratio) * log_n
    err = pct_err(host, want)
    rep.add("G3", PASS if err <= PREREG["HOST_TOL_PCT"] else FAIL,
            f"host tier={host:,.0f} tok vs r x pool = {float(ratio):g} x {log_n:,} = {want:,.0f} "
            f"(err {err:.2f}%, tol {PREREG['HOST_TOL_PCT']}%)",
            host_total_tokens=int(host), host_expect=int(want), host_err_pct=round(err, 3))


# ── G4 behavioural probe ─────────────────────────────────────────────────────
def build_probe_prompts(tokenizer_name, n_req, target_tok):
    """Unique-filler prompts via the driver's Padder (imported, not modified).

    Each request gets its own seed, so the only shared prefix is the ~150-token system
    prompt — prefix-cache dedup cannot mask the pressure. Byproduct: padder realisation
    error under the Qwen2.5 tokenizer (P-e), the ONLY place the tokenizer enters the
    experiment at all.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from transformers import AutoTokenizer
    from trace_replay_driver_yunuikang import Padder, SHARED_SYSTEM_PROMPT

    tok = AutoTokenizer.from_pretrained(tokenizer_name)
    pad = Padder(tok)
    base = [{"role": "system", "content": SHARED_SYSTEM_PROMPT}]
    shared_prefix = pad.count(base)   # counted once in the radix tree, n_req times in the
                                      # per-request prompt lengths -> subtracted below
    out = []
    for i in range(n_req):
        user, achieved = pad.build_user(base, "Reply with the single word OK.",
                                        target_tok, seed=10_000 + i)
        out.append((base + [user], achieved))
    return out, shared_prefix


class MetricsSampler(threading.Thread):
    def __init__(self, backend, hz):
        super().__init__(daemon=True)
        self.url = backend + "/metrics"
        self.dt = 1.0 / hz
        self.stop_flag = threading.Event()
        self.samples = []

    def run(self):
        while not self.stop_flag.is_set():
            t = time.time()
            try:
                body = http_get(self.url, timeout=5)
                self.samples.append({
                    "t": t,
                    "num_used_tokens": metric_value(body, "sglang:num_used_tokens"),
                    "evicted_tokens_total": metric_value(body, "sglang:evicted_tokens_total"),
                    "num_running_reqs": metric_value(body, "sglang:num_running_reqs"),
                })
            except Exception:
                pass
            time.sleep(max(0.0, t + self.dt - time.time()))


def g4_probe(rep, backend, log_n, model_name, tokenizer_name):
    n_req = PREREG["PROBE_N_REQ"]
    ptok = PREREG["PROBE_PROMPT_TOK"]
    offered = n_req * ptok
    print(f"  ... building {n_req} x {ptok:,}-token prompts "
          f"(offered {offered:,} tok = {offered/log_n:.2f} x pool)")
    try:
        prompts, shared_prefix = build_probe_prompts(tokenizer_name, n_req, ptok)
    except Exception as e:
        rep.add("G4", FAIL, f"probe prompt build failed: {e!r}")
        return

    errs = [abs(a - ptok) for _, a in prompts]
    rep.add("P-e", PASS, f"padder realisation error vs {ptok:,} tok target: "
                         f"max {max(errs)} tok, mean {sum(errs)/len(errs):.1f} tok "
                         f"(Qwen2.5 tokenizer; recorded, not a criterion)",
            padder_err_max=max(errs), padder_err_mean=round(sum(errs) / len(errs), 2))

    sampler = MetricsSampler(backend, PREREG["PROBE_SAMPLE_HZ"])
    try:
        body0 = http_get(backend + "/metrics", timeout=15)
        ev0 = metric_value(body0, "sglang:evicted_tokens_total") or 0.0
    except Exception as e:
        rep.add("G4", FAIL, f"/metrics unreachable before probe: {e!r}")
        return
    sampler.start()

    results = []
    lock = threading.Lock()

    def one(idx):
        msgs, _ = prompts[idx]
        payload = {"model": model_name, "messages": msgs,
                   "max_tokens": PREREG["PROBE_MAX_NEW_TOKENS"], "temperature": 0.0}
        t0 = time.time()
        comp = 0
        try:
            status, body = http_post_json(backend + "/v1/chat/completions", payload)
            ok = status == 200
            comp = int((body.get("usage") or {}).get("completion_tokens") or 0)
        except urllib.error.HTTPError as e:
            status, ok = e.code, False
        except Exception:
            status, ok = -1, False
        with lock:
            results.append({"i": idx, "status": status, "ok": ok, "completion": comp,
                            "s": round(time.time() - t0, 2)})

    t_start = time.time()
    idx = 0
    threads = []
    while idx < n_req or threads:
        threads = [t for t in threads if t.is_alive()]
        while idx < n_req and len(threads) < PREREG["PROBE_CONCURRENCY"]:
            th = threading.Thread(target=one, args=(idx,), daemon=True)
            th.start()
            threads.append(th)
            idx += 1
        time.sleep(0.2)
    probe_s = time.time() - t_start

    time.sleep(3.0)                      # let the last evictions land in the counter
    sampler.stop_flag.set()
    sampler.join(timeout=5)

    # Read the eviction counter directly (not via the 1 Hz sampler) so the arithmetic uses
    # the settled final value rather than the last sampled tick.
    try:
        ev1 = metric_value(http_get(backend + "/metrics", timeout=15),
                           "sglang:evicted_tokens_total")
    except Exception:
        ev1 = None
    evs = [s["evicted_tokens_total"] for s in sampler.samples
           if s["evicted_tokens_total"] is not None]
    if ev1 is None:
        ev1 = max(evs) if evs else None
    d_ev = (ev1 - ev0) if ev1 is not None else None

    used = [s["num_used_tokens"] for s in sampler.samples if s["num_used_tokens"] is not None]
    peak = max(used) if used else None    # RECORDED ONLY — in-flight KV, not pool residency
    n_ok = sum(1 for r in results if r["ok"])

    # offered unique KV: prompt tokens + generated tokens, minus the shared system prefix
    # counted once in the radix tree but n_req times in the prompt lengths.
    achieved = sum(a for _, a in prompts)
    generated = sum(r.get("completion", 0) for r in results)
    offered_unique = achieved + generated - (n_req - 1) * shared_prefix
    resident_est = (offered_unique - d_ev) if d_ev is not None else None

    print(f"  ... probe done in {probe_s:.1f}s, {len(sampler.samples)} metric samples; "
          f"offered_unique={offered_unique:,} evicted={0 if d_ev is None else int(d_ev):,} "
          f"-> resident_est={'n/a' if resident_est is None else f'{resident_est:,.0f}'}")

    rep.add("P-0", PASS, f"instrument: offered_unique={offered_unique:,} "
                         f"(prompts {achieved:,} + gen {generated:,} - shared prefix "
                         f"{n_req - 1}x{shared_prefix:,}); peak in-flight num_used_tokens="
                         f"{'n/a' if peak is None else f'{peak:,.0f}'} (RECORDED, not a "
                         f"criterion — see PREREG §9.3)",
            offered_unique=offered_unique, peak_used_tokens=None if peak is None else int(peak),
            padder_achieved=achieved, generated=generated, shared_prefix=shared_prefix)

    if resident_est is None:
        rep.add("P-a", FAIL, "evicted_tokens_total unreadable — resident capacity unmeasurable")
        rep.add("P-b", FAIL, "evicted_tokens_total unreadable — resident capacity unmeasurable")
    else:
        hi = PREREG["P_A_UPPER"] * log_n
        rep.add("P-a", PASS if resident_est <= hi else FAIL,
                f"resident_est={resident_est:,.0f} <= {PREREG['P_A_UPPER']:.2f} x pool "
                f"= {hi:,.0f} "
                f"({'cap enforced' if resident_est <= hi else 'CAP NOT ENFORCED — plan invalid'})",
                resident_est=int(resident_est), p_a_threshold=int(hi))
        lo = PREREG["P_B_FRAC"] * log_n
        rep.add("P-b", PASS if resident_est >= lo else FAIL,
                f"resident_est={resident_est:,.0f} >= {PREREG['P_B_FRAC']:.2f} x pool "
                f"= {lo:,.0f} (ratio {resident_est/log_n:.4f} — actual capacity matches the "
                f"ledger from below)",
                p_b_threshold=int(lo), resident_ratio=round(resident_est / log_n, 4))
    if d_ev is None:
        rep.add("P-c", FAIL, "sglang:evicted_tokens_total never read")
    else:
        note = ("pool saturated, cap reached" if d_ev > 0 else
                "cap never reached — the probe exerted no pressure, so resident_est is "
                "just the offered load and P-a/P-b say nothing")
        rep.add("P-c", PASS if d_ev > 0 else FAIL,
                f"evicted_tokens_total delta={d_ev:,.0f} ({note})",
                evicted_delta=int(d_ev))
    rep.add("P-d", PASS if n_ok == n_req else FAIL,
            f"{n_ok}/{n_req} requests 200 OK "
            f"(statuses: {sorted({r['status'] for r in results})})",
            probe_ok=n_ok, probe_n=n_req, probe_wall_s=round(probe_s, 1),
            probe_offered_tokens=offered)


# ── G6 two-point slope ───────────────────────────────────────────────────────
def slope_check(path):
    recs = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    recs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    pts = {}
    for r in recs:
        t, n = r.get("target_maxtok"), r.get("pool_tokens")
        if t and n:
            pts[t] = n
    print(f"\n=== G6 two-point sensitivity (dN/dMAXTOK) — {len(pts)} distinct targets ===")
    for t in sorted(pts):
        print(f"    MAXTOK={t:,} -> pool={pts[t]:,}  fit={pts[t]/PREREG['FIT_DEN']:.3f}")
    if len(pts) < 2:
        print("  [SKIP] G6 needs >= 2 distinct MAXTOK values")
        return 0
    ts = sorted(pts)
    lo, hi = ts[0], ts[-1]
    slope = (pts[hi] - pts[lo]) / (hi - lo)
    ok = abs(slope - 1.0) <= PREREG["SLOPE_TOL"]
    print(f"  [{'PASS' if ok else 'FAIL'}] G6   slope = ({pts[hi]:,} - {pts[lo]:,}) / "
          f"({hi:,} - {lo:,}) = {slope:.5f}  (expect 1.000 +- {PREREG['SLOPE_TOL']})")
    if not ok:
        print("        -> the pool does NOT track the flag linearly; the fit grid must be "
              "recomputed before Phase 1.")
    return 0 if ok else 1


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slope-check", metavar="JSONL",
                    help="G6 only: read a gate results jsonl and check dN/dMAXTOK")
    ap.add_argument("--backend", default="http://127.0.0.1:8123")
    ap.add_argument("--log", help="serve log file (for max_total_num_tokens / context_len)")
    ap.add_argument("--target-maxtok", type=int, help="the --max-total-tokens that was requested")
    ap.add_argument("--ratio", default="0", help="hicache ratio r of this cell (0 = off)")
    ap.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--tokenizer", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--tp", type=int, default=1)
    ap.add_argument("--probe", action="store_true", help="run G4 behavioural enforcement probe")
    ap.add_argument("--out", help="append the verdict as one JSON line here")
    ap.add_argument("--tag", default="cell")
    args = ap.parse_args()

    if args.slope_check:
        sys.exit(slope_check(args.slope_check))

    if not (args.log and args.target_maxtok):
        ap.error("--log and --target-maxtok are required unless --slope-check is used")

    backend = args.backend.rstrip("/")
    logtext = open(args.log, errors="replace").read() if os.path.exists(args.log) else ""

    print(f"\n=== §7.1b fit gate — tag={args.tag} target MAXTOK={args.target_maxtok:,} "
          f"(fit {args.target_maxtok/PREREG['FIT_DEN']:.2f}) r={args.ratio} "
          f"probe={'on' if args.probe else 'off'} ===")

    rep = Report()
    if not g0_boot(rep, backend, logtext, args.model.split("/")[-1], args.tp):
        pool = None
    else:
        pool = g1_declared(rep, logtext, args.target_maxtok)
        if pool:
            g2_sources(rep, backend, pool, args.target_maxtok)
            g2b_vram(rep, pool)
            g3_host(rep, backend, pool, args.ratio)
            if args.probe:
                g4_probe(rep, backend, pool, args.model, args.tokenizer)

    verdict = FAIL if rep.failed else PASS
    rec = {
        "tag": args.tag, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "target_maxtok": args.target_maxtok, "pool_tokens": pool,
        "fit": round(pool / PREREG["FIT_DEN"], 4) if pool else None,
        "ratio": args.ratio, "probe": args.probe, "verdict": verdict,
        "n_fail": len(rep.failed), "prereg": PREREG, "checks": rep.checks,
        "backend": backend, "log": os.path.abspath(args.log),
    }
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
        with open(args.out, "a") as f:
            f.write(json.dumps(rec) + "\n")

    print(f"=== VERDICT {verdict} — {len(rep.failed)} FAIL / {len(rep.checks)} checks ===")
    for c in rep.failed:
        print(f"    FAILED {c['id']}: {c['detail']}")
    sys.exit(0 if verdict == PASS else 1)


if __name__ == "__main__":
    main()
