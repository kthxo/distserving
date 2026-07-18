#!/usr/bin/env python3
"""재프리필 참값 측정 — vLLM /metrics의 오염 없는 카운터로 hit 지표 오염을 정량화.

배경 (logs/2026-07-17_VLLM_PROFILING_yunuikang.md §1-2):
  vLLM V1은 waiting 큐에서 승인 실패한 요청을 매 step 재계수한다
  (scheduler.py:636 peek → :710 record() → :888-895 break, pop은 :917).
  → prefix_cache_queries/hits가 최대 30배 팽창 → hit rate 오염.

오염 없는 대안 (stats.py:281,292-322; loggers.py:643-664,1161-1164):
  vllm:prompt_tokens_by_source_total{source="local_compute"}  = 실제 계산한 프리필 토큰
  vllm:prompt_tokens_cached_total                             = 캐시로 건너뛴 토큰
  vllm:prompt_tokens_total                                    = 논리적 총량
  불변식: local_compute + local_cache_hit + external_kv_transfer = total
  → 참 hit rate = cached / total   (재검사 오염 없음: 실제 prefill 출력에서만 누적)

이 스크립트는 드라이버를 수정하지 않는다. 실행 전후 /metrics를 스냅샷할 뿐이다.
"""
import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request

# name{labels} value   (Counter는 _total 접미사)
_LINE = re.compile(r'^(vllm:[a-z_]+)(?:\{([^}]*)\})?\s+([0-9.eE+-]+)\s*$', re.M)


def scrape(url, timeout=10):
    """{(metric, source_label|None): value} 반환."""
    with urllib.request.urlopen(f"{url.rstrip('/')}/metrics", timeout=timeout) as r:
        text = r.read().decode()
    out = {}
    for name, labels, val in _LINE.findall(text):
        src = None
        if labels:
            m = re.search(r'source="([^"]+)"', labels)
            if m:
                src = m.group(1)
        key = (name, src)
        try:
            out[key] = out.get(key, 0.0) + float(val)
        except ValueError:
            pass
    return out


KEYS = [
    ("vllm:prompt_tokens_total", None),
    ("vllm:prompt_tokens_cached_total", None),
    ("vllm:prompt_tokens_by_source_total", "local_compute"),
    ("vllm:prompt_tokens_by_source_total", "local_cache_hit"),
    ("vllm:prompt_tokens_by_source_total", "external_kv_transfer"),
    ("vllm:generation_tokens_total", None),
    ("vllm:prefix_cache_queries_total", None),
    ("vllm:prefix_cache_hits_total", None),
    ("vllm:num_preemptions_total", None),
]


def snap(backends):
    tot = {}
    for b in backends:
        s = scrape(b)
        for k in KEYS:
            tot[k] = tot.get(k, 0.0) + s.get(k, 0.0)
    return tot


def delta(a, b):
    return {k: b.get(k, 0.0) - a.get(k, 0.0) for k in KEYS}


def report(d):
    g = lambda n, s=None: d.get((n, s), 0.0)
    total = g("vllm:prompt_tokens_total")
    cached = g("vllm:prompt_tokens_cached_total")
    compute = g("vllm:prompt_tokens_by_source_total", "local_compute")
    lch = g("vllm:prompt_tokens_by_source_total", "local_cache_hit")
    q = g("vllm:prefix_cache_queries_total")
    h = g("vllm:prefix_cache_hits_total")
    out = {
        "prompt_tokens_total": total,
        "prompt_tokens_cached": cached,
        "prompt_tokens_local_compute": compute,
        "prompt_tokens_local_cache_hit": lch,
        "generation_tokens": g("vllm:generation_tokens_total"),
        "prefix_cache_queries": q,
        "prefix_cache_hits": h,
        "num_preemptions": g("vllm:num_preemptions_total"),
        # ★ 참 hit rate — 재검사 오염 없음
        "TRUE_hit_rate": (cached / total) if total else None,
        "TRUE_recompute_tokens": compute,
        "TRUE_recompute_frac": (compute / total) if total else None,
        # 기존(오염된) 지표
        "REPORTED_hit_rate": (h / q) if q else None,
        "queries_inflation": (q / total) if total else None,
        # 불변식 검산
        "invariant_ok": abs((compute + cached) - total) < 1e-6 if total else None,
    }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backends", default="http://localhost:8002,http://localhost:8003")
    ap.add_argument("--driver-cmd", required=True, help="드라이버 실행 명령 (shell)")
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    backends = [b.strip() for b in a.backends.split(",") if b.strip()]

    before = snap(backends)
    t0 = time.time()
    rc = subprocess.call(a.driver_cmd, shell=True)
    wall = time.time() - t0
    after = snap(backends)

    d = delta(before, after)
    rep = report(d)
    rep.update({"label": a.label, "wall_s": wall, "driver_rc": rc,
                "backends": backends, "ts": t0})
    with open(a.out, "a") as f:
        f.write(json.dumps(rep) + "\n")

    print(f"\n===== {a.label}  (wall {wall:.0f}s, rc={rc}) =====")
    print(f"  prompt_tokens_total        {rep['prompt_tokens_total']:>14,.0f}")
    print(f"  prompt_tokens_cached       {rep['prompt_tokens_cached']:>14,.0f}")
    print(f"  local_compute (참 재프리필) {rep['prompt_tokens_local_compute']:>14,.0f}")
    print(f"  invariant compute+cached==total : {rep['invariant_ok']}")
    print(f"  ---")
    print(f"  ★ TRUE hit rate   = cached/total = {rep['TRUE_hit_rate']}")
    print(f"  ★ TRUE recompute frac            = {rep['TRUE_recompute_frac']}")
    print(f"    REPORTED hit rate = hits/queries = {rep['REPORTED_hit_rate']}")
    print(f"    queries inflation = queries/total= {rep['queries_inflation']}")
    print(f"    preemptions                      = {rep['num_preemptions']}")
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
