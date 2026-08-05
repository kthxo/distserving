#!/usr/bin/env python3
"""Phase 2 엔진측 지표 샘플러 — **완료-무관 불편향 교차지표**용.

왜 필요한가 [측정]:
  드라이버의 throughput/ttft는 **완료된 프로그램만** 집계한다
  (`mori_replay_driver_yunuikang.py:300-317` — "Programs still in flight at the deadline
  never entered `ok`"). MORI는 설계상 프로그램을 pause/demote해 완주 시간을 늘리므로,
  마감 시각에 미완인 프로그램이 많아지고 그 토큰이 통째로 빠진다 → **MORI에만 걸리는 편향**.
  20분 run에서 같은 셀이 드라이버 0.57× vs 엔진 0.86× 로 갈린 것이 실측 근거.

이 샘플러는 SGLang `/metrics` 를 주기적으로 찍어 **steady 창에서의 델타**를 계산할 수 있게 한다.
프로그램 완료 여부와 무관하므로 불편향이다.

출력 CSV 1행/틱: t, wall_clock, generation_tokens_total, prompt_tokens_total,
  cached_tokens_total, load_back_tokens_total, evicted_tokens_total,
  hicache_host_used_tokens, num_used_tokens, num_running_reqs, cache_hit_rate
"""
import argparse
import csv
import os
import re
import sys
import time
import urllib.request

METRICS = [
    "sglang:generation_tokens_total",
    "sglang:prompt_tokens_total",
    "sglang:cached_tokens_total",
    "sglang:load_back_tokens_total",
    "sglang:evicted_tokens_total",
    "sglang:hicache_host_used_tokens",
    "sglang:hicache_host_total_tokens",
    "sglang:num_used_tokens",
    "sglang:num_running_reqs",
    "sglang:cache_hit_rate",
]
_RX = {}


def val(body, name):
    rx = _RX.get(name)
    if rx is None:
        rx = re.compile(r"^" + re.escape(name) + r"(?:\{[^}]*\})?\s+([0-9.eE+-]+)", re.M)
        _RX[name] = rx
    v = [float(x) for x in rx.findall(body)]
    if not v:
        return ""
    # counter는 TP rank별로 중복 노출될 수 있다 → 게이지는 평균, 카운터는 최댓값이 안전.
    # sglang은 rank0만 export하므로 실무상 동일하나, 방어적으로 처리.
    return max(v) if name.endswith("_total") or name.startswith("sglang:num") else sum(v) / len(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="http://localhost:8123")
    ap.add_argument("--out", required=True)
    ap.add_argument("--interval", type=float, default=5.0)
    args = ap.parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)

    cols = ["t", "wall_clock"] + [m.split(":", 1)[1] for m in METRICS]
    new = not os.path.exists(args.out) or os.path.getsize(args.out) == 0
    f = open(args.out, "a", newline="")
    w = csv.writer(f)
    if new:
        w.writerow(cols); f.flush()

    t0 = time.time()
    url = args.backend.rstrip("/") + "/metrics"
    while True:
        tick = time.time()
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                body = r.read().decode()
            row = [round(tick - t0, 2), round(tick, 3)] + [val(body, m) for m in METRICS]
        except Exception:
            row = [round(tick - t0, 2), round(tick, 3)] + [""] * len(METRICS)
        w.writerow(row); f.flush()
        time.sleep(max(0.0, tick + args.interval - time.time()))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
