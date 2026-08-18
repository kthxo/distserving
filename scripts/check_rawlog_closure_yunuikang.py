#!/usr/bin/env python3
"""raw-log 무결성 검사 — 6파일 존재 · 스키마 · 타임스탬프 정합 · closure C1~C4.

PLAN §9.3 의 게이트를 그대로 코드화한다.  **판정/해석은 하지 않는다** — PASS/FAIL 과
수치만 낸다.

closure
  C1  busy <= wall           : steplog forward GPU 시간 합 <= 런 wall (rank 별)
  C2  steplog 창 커버리지     : steplog 이 측정창을 처음부터 끝까지 덮는가 (구멍 없음)
  C3  GPU busy / forward host : CUDA event 시간 / host 관측 시간 <= 1 (초과면 계측 오류)
  C4  토큰 교차검증           : requests 합 vs snapshots 누적 counter 델타

사용:  python scripts/check_rawlog_closure_yunuikang.py --dir <셀 디렉터리>
"""
import argparse
import glob
import json
import os
import sys

FILES = ["run_meta.json", "requests.jsonl", "events.jsonl",
         "kv_events.jsonl", "snapshots.jsonl", "gpu.jsonl"]

REQ_REQUEST = ["session_idx", "cycle", "turn", "submit_ts", "end_ts",
               "input_tokens", "output_tokens", "status"]
REQ_EVENT = ["ts", "event"]
REQ_KV = ["ts", "event"]
REQ_SNAP = ["ts"]
REQ_GPU = ["ts"]

OK, BAD = "PASS", "FAIL"
_result = []


def say(tag, verdict, detail=""):
    _result.append(verdict == OK)
    print(f"  [{verdict}] {tag}" + (f" — {detail}" if detail else ""))


def load_jsonl(path):
    rows, bad = [], 0
    if not os.path.exists(path):
        return rows, -1
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
    return rows, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    args = ap.parse_args()
    D = args.dir

    print(f"=== raw-log closure check: {D} ===")

    # ---------- kv_events 는 엔진이 pid 접미사로 쓴다 -> 정규화 ----------
    kv_parts = sorted(glob.glob(os.path.join(D, "kv_events.*.jsonl")))
    kv_path = os.path.join(D, "kv_events.jsonl")
    if kv_parts and not os.path.exists(kv_path):
        rows = []
        for p in kv_parts:
            r, _ = load_jsonl(p)
            rows.extend(r)
        rows.sort(key=lambda r: r.get("ts", 0))
        with open(kv_path, "w") as f:
            for r in rows:
                f.write(json.dumps(r, separators=(",", ":")) + "\n")
        print(f"  (kv_events {len(kv_parts)}개 shard -> kv_events.jsonl 병합, {len(rows)}줄)")

    # ---------- 0. 파일 존재 ----------
    print("\n-- 파일 --")
    missing = []
    for fn in FILES:
        p = os.path.join(D, fn)
        if os.path.exists(p):
            n = sum(1 for _ in open(p)) if fn.endswith(".jsonl") else 1
            print(f"     {fn:20s} {os.path.getsize(p):>12,} B  {n:>9,} 줄")
        else:
            missing.append(fn)
    say("6파일 생성", OK if not missing else BAD,
        "" if not missing else "없음: " + ", ".join(missing))

    meta = {}
    mp = os.path.join(D, "run_meta.json")
    if os.path.exists(mp):
        meta = json.load(open(mp))

    reqs, bad_r = load_jsonl(os.path.join(D, "requests.jsonl"))
    evs, bad_e = load_jsonl(os.path.join(D, "events.jsonl"))
    kvs, bad_k = load_jsonl(kv_path)
    snaps, bad_s = load_jsonl(os.path.join(D, "snapshots.jsonl"))
    gpus, bad_g = load_jsonl(os.path.join(D, "gpu.jsonl"))

    # ---------- 1. 스키마 ----------
    print("\n-- 스키마 --")
    def check_schema(name, rows, required):
        if not rows:
            say(f"{name} 스키마", BAD, "레코드 0")
            return
        viol = []
        for i, r in enumerate(rows):
            miss = [k for k in required if k not in r]
            if miss:
                viol.append((i, miss))
                if len(viol) >= 5:
                    break
        say(f"{name} 필수필드", OK if not viol else BAD,
            f"{len(rows):,}줄 전부 OK" if not viol
            else f"위반 예: line{viol[0][0]} 누락 {viol[0][1]}")

    check_schema("requests", reqs, REQ_REQUEST)
    check_schema("events", evs, REQ_EVENT)
    check_schema("kv_events", kvs, REQ_KV)
    check_schema("snapshots", snaps, REQ_SNAP)
    check_schema("gpu", gpus, REQ_GPU)
    for nm, b in [("requests", bad_r), ("events", bad_e), ("kv_events", bad_k),
                  ("snapshots", bad_s), ("gpu", bad_g)]:
        if b > 0:
            say(f"{nm} JSON 파싱", BAD, f"깨진 줄 {b}")

    # requests 값 정합
    if reqs:
        neg = [r for r in reqs if r.get("end_ts", 0) < r.get("submit_ts", 0)]
        say("requests end_ts >= submit_ts", OK if not neg else BAD,
            f"위반 {len(neg)}")
        okr = [r for r in reqs if r.get("status") == "ok"]
        cle = [r for r in okr if r.get("cached_tokens") is not None
               and r["cached_tokens"] > r["input_tokens"]]
        say("cached_tokens <= input_tokens", OK if not cle else BAD, f"위반 {len(cle)}")
        ncache = sum(1 for r in okr if r.get("cached_tokens") is None)
        print(f"     (cached_tokens null: {ncache:,}/{len(okr):,} — 엔진이 "
              f"prompt_tokens_details 를 안 주면 null)")

    # ---------- 2. 타임스탬프 정합 ----------
    print("\n-- 타임스탬프 정합 (run origin 0.0) --")
    spans = {}
    for nm, rows, key in [("requests", reqs, "submit_ts"), ("events", evs, "ts"),
                          ("kv_events", kvs, "ts"), ("snapshots", snaps, "ts"),
                          ("gpu", gpus, "ts")]:
        ts = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
        if ts:
            spans[nm] = (min(ts), max(ts))
            print(f"     {nm:12s} [{min(ts):10.2f} .. {max(ts):10.2f}] s   n={len(ts):,}")
    neg_ts = {nm: s for nm, s in spans.items() if s[0] < -1.0}
    say("모든 ts >= 0 (run origin 이후)", OK if not neg_ts else BAD,
        "" if not neg_ts else f"음수 시작: {neg_ts}")
    # driver 와 engine 이 같은 원점을 쓰는지 — 겹치는 구간이 있어야 한다
    if "requests" in spans and "kv_events" in spans:
        a, b = spans["requests"], spans["kv_events"]
        overlap = min(a[1], b[1]) - max(a[0], b[0])
        say("driver/engine 시계 원점 일치", OK if overlap > 0 else BAD,
            f"겹침 {overlap:.1f}s (driver {a[0]:.1f}-{a[1]:.1f} / engine {b[0]:.1f}-{b[1]:.1f})")

    # ---------- 3. closure C1~C4 ----------
    print("\n-- closure C1~C4 --")
    wall = None
    for e in evs:
        if e.get("event") == "run_end":
            wall = e.get("wall_s")
    if wall is None and spans.get("requests"):
        wall = spans["requests"][1] - spans["requests"][0]

    # steplog (MORI_TIERC) 로드
    step_files = sorted(glob.glob(os.path.join(D, "steplog*.jsonl")))
    steps = []
    for p in step_files:
        r, _ = load_jsonl(p)
        steps.extend(r)
    fwd = [s for s in steps if s.get("kind") == "fwd" and s.get("gpu_ms") is not None]

    # --- C1 busy <= wall
    if fwd and wall:
        by_rank = {}
        for s in fwd:
            by_rank.setdefault(s.get("rank", -1), 0.0)
            by_rank[s["rank"]] += s["gpu_ms"]
        worst = max(by_rank.values()) / 1000.0
        say("C1 busy <= wall", OK if worst <= wall * 1.02 else BAD,
            f"busy {worst:,.1f}s / wall {wall:,.1f}s = {worst/wall:.3f}")
    else:
        say("C1 busy <= wall", BAD,
            f"steplog fwd 레코드 {len(fwd)} · wall {wall}")

    # --- C2 steplog 창 커버리지
    #
    # ★ 판정 구간 수정 (2026-08-17, 승인)
    #   1차 본 런에서 C42 가 "최대구멍 300.6s" 로 FAIL 했는데, 추적해 보니 그 구멍은
    #   8h 측정창(28,800s)이 **끝난 뒤 grace/drain 구간**(t=30,470~30,771s)이었고
    #   그 동안 snapshots 는 running=0 · queue=0 · used_tok=0 이었다.
    #   = 세션이 전부 끝나 엔진이 할 일이 없어 forward 가 호출되지 않은 **정상 유휴**이지
    #     로깅 손실이 아니다.  측정창 내부의 최대구멍은 47.5s 였다.
    #   따라서 C2 를 두 가지로 고친다:
    #     (a) 판정 구간을 **[run_start, run_start + duration_s]** 로 한정 (grace/drain 제외)
    #     (b) 구멍이 걸친 구간의 snapshots 가 **전부 running=0 & queue=0** 이면 유휴로 인정
    #   ※ running>0 인데 로그가 비어 있으면 **여전히 FAIL** — 그건 진짜 손실이다.
    GAP_LIMIT_S = 300.0
    if fwd and meta:
        t0 = meta.get("clock_anchor", {}).get("t0_unix", 0)
        dur = ((meta.get("driver") or {}).get("duration_s")) or wall or 0.0
        t_lo = next((e["ts"] for e in evs if e.get("event") == "run_start"), 0.0)
        t_hi = t_lo + dur
        sts = sorted(s["t"] - t0 for s in fwd)
        inwin = [t for t in sts if t_lo <= t <= t_hi]
        if not inwin:
            say("C2 steplog 창 커버리지", BAD, "측정창 안에 forward 레코드가 없음")
        else:
            def idle_between(a, b):
                """구멍 (a,b) 에 걸친 snapshots 가 전부 무작업이면 True."""
                ss = [s for s in snaps if a <= s.get("ts", -1) <= b]
                if not ss:
                    return False          # 근거 없음 -> 보수적으로 구멍 취급
                return all((s.get("num_running_reqs") or 0) == 0
                           and (s.get("num_queue_reqs") or 0) == 0 for s in ss)

            real_gaps, idle_gaps = [], []
            for a, b in zip(inwin, inwin[1:]):
                g = b - a
                if g <= GAP_LIMIT_S:
                    continue
                (idle_gaps if idle_between(a, b) else real_gaps).append((g, a, b))
            max_all = max((b - a for a, b in zip(inwin, inwin[1:])), default=0.0)
            cover0, cover1 = inwin[0], inwin[-1]
            bad = []
            if real_gaps:
                g, a, b = max(real_gaps)
                bad.append(f"작업중({GAP_LIMIT_S:.0f}s 초과) 로그공백 {len(real_gaps)}건, "
                           f"최대 {g:.1f}s @[{a:.0f}..{b:.0f}]s")
            if cover0 > t_lo + max(60.0, dur * 0.05):
                bad.append(f"시작 커버리지 부족 (첫 step {cover0:.0f}s > {t_lo + max(60.0, dur*0.05):.0f}s)")
            if cover1 < t_hi - max(60.0, dur * 0.05):
                bad.append(f"끝 커버리지 부족 (마지막 step {cover1:.0f}s < {t_hi - max(60.0, dur*0.05):.0f}s)")
            say("C2 steplog 창 커버리지", OK if not bad else BAD,
                f"측정창 [{t_lo:.0f}..{t_hi:.0f}]s · step [{cover0:.0f}..{cover1:.0f}]s · "
                f"최대구멍 {max_all:.1f}s (유휴인정 {len(idle_gaps)}건 / 실공백 {len(real_gaps)}건)"
                + ("" if not bad else " | " + "; ".join(bad)))
    else:
        say("C2 steplog 창 커버리지", BAD, "steplog 없음")

    # --- C3 forward 계측 무결성
    #
    # ★ 정의 변경 이력 (숨기지 않고 기록)
    #   PLAN §9.3 의 원문 표현은 "GPU busy ÷ forward host" 였고, 1차 스모크에서 이 비가
    #   46.59x 로 나와 FAIL 했다.  원인을 파보니 **계측 오류가 아니라 임계 자체가
    #   overlap 스케줄링에서 성립하지 않는 것**이었다:
    #     host_ms median 0.4995 ms  vs  gpu_ms median 33.6085 ms
    #   SGLang 은 overlap 스케줄링이 기본 ON 이라 `forward_batch_generation` 은 커널을
    #   forward_stream 에 **enqueue 만 하고 즉시 반환**한다 (mori_tierc_instrument
    #   docstring §1 이 명시).  따라서 host_ms 는 GPU 작업시간의 분모가 될 수 없고,
    #   비가 1 근처여야 한다는 전제가 틀렸다.  임계를 넓혀 FAIL 을 지우는 대신
    #   **의도(=계측이 GPU 시간을 이중계상/오계상하지 않았나)를 직접 검사**하도록 바꾼다.
    #   원래 비는 아래에 참고값으로 계속 출력한다.
    if fwd:
        g = sum(s["gpu_ms"] for s in fwd)
        h = sum(s.get("host_ms", 0) or 0 for s in fwd)
        ratio = (g / h) if h else float("inf")
        ranks = {s.get("rank", -1) for s in fwd}
        tp = (meta.get("engine", {}).get("flags", {}) or {}).get("tp_size") or 1
        neg = [s for s in fwd if s["gpu_ms"] < 0]
        huge = [s for s in fwd if s["gpu_ms"] > 60_000]     # 한 step 60s 초과 = 비현실적
        busy_per_rank = {}
        for s in fwd:
            busy_per_rank[s.get("rank", -1)] = busy_per_rank.get(s.get("rank", -1), 0.0) + s["gpu_ms"]
        over = {r: b / 1000 for r, b in busy_per_rank.items() if wall and b / 1000 > wall * 1.02}
        bad = []
        if len(ranks) != tp:
            bad.append(f"rank 수 {len(ranks)} != tp {tp} (이중계상 위험)")
        if neg:
            bad.append(f"음수 gpu_ms {len(neg)}")
        if huge:
            bad.append(f"60s 초과 step {len(huge)}")
        if over:
            bad.append(f"rank별 busy > wall: {over}")
        say("C3 forward 계측 무결성", OK if not bad else BAD,
            f"rank={sorted(ranks)} tp={tp} · 음수 {len(neg)} · 과대 {len(huge)}"
            + ("" if not bad else " | " + "; ".join(bad)))
        print(f"     (참고) gpu {g/1000:,.1f}s / host(enqueue만) {h/1000:,.1f}s = {ratio:.2f}x "
              f"— overlap 스케줄링이라 1 근처가 아닌 것이 정상")
    else:
        say("C3 forward 계측 무결성", BAD, "steplog 없음")

    # --- C4 토큰 교차검증
    if reqs and len(snaps) >= 2:
        okr = [r for r in reqs if r.get("status") == "ok"]
        d_out = sum(r.get("output_tokens", 0) for r in okr)
        d_in = sum(r.get("input_tokens", 0) for r in okr)

        def cum(s, k):
            c = s.get("cum") or {}
            return c.get(k)
        first = next((s for s in snaps if cum(s, "generation_tokens_total") is not None), None)
        last = next((s for s in reversed(snaps) if cum(s, "generation_tokens_total") is not None), None)
        if first and last:
            e_out = cum(last, "generation_tokens_total") - cum(first, "generation_tokens_total")
            e_in = (cum(last, "prompt_tokens_total") or 0) - (cum(first, "prompt_tokens_total") or 0)
            # 스냅샷 창이 driver 창보다 약간 좁/넓으므로 ±15% 를 허용한다
            ro = (d_out / e_out) if e_out else float("inf")
            ri = (d_in / e_in) if e_in else float("inf")
            ok = 0.85 <= ro <= 1.15 and 0.85 <= ri <= 1.15
            say("C4 토큰 교차검증", OK if ok else BAD,
                f"output driver {d_out:,} / engine {e_out:,.0f} = {ro:.3f} · "
                f"input driver {d_in:,} / engine {e_in:,.0f} = {ri:.3f}")
        else:
            say("C4 토큰 교차검증", BAD, "snapshots 에 cum counter 없음")
    else:
        say("C4 토큰 교차검증", BAD, f"requests {len(reqs)} snapshots {len(snaps)}")

    # ---------- 4. 참고 수치 (판정 아님) ----------
    print("\n-- 참고 수치 (해석 아님) --")
    if reqs:
        okr = [r for r in reqs if r.get("status") == "ok"]
        err = [r for r in reqs if r.get("status") != "ok"]
        print(f"     requests ok={len(okr):,} err={len(err):,}")
        sess = {(r.get("session_idx"), r.get("cycle")) for r in reqs}
        print(f"     고유 (session_idx,cycle) = {len(sess):,}")
    ends = [e for e in evs if e.get("event") == "session_end"]
    print(f"     session_end = {len(ends):,}  "
          f"(completed {sum(1 for e in ends if e.get('reason')=='completed'):,})")
    print(f"     context_truncate = {sum(1 for e in evs if e.get('event')=='context_truncate'):,}")
    print(f"     tool_call = {sum(1 for e in evs if e.get('event')=='tool_call'):,}")
    kinds = {}
    for k in kvs:
        kinds[k.get("event")] = kinds.get(k.get("event"), 0) + 1
    print(f"     kv_events by type = {kinds}")

    # cuda graph 상한 초과 계량 (교란 계량용 — 판정 아님).
    # 기본 캡처 bs 목록의 최대는 실측 32.  num_running 이 이를 넘는 구간은 eager 로 떨어진다.
    GRAPH_MAX_BS = 32
    nr = [s["num_running_reqs"] for s in snaps if s.get("num_running_reqs") is not None]
    if nr:
        over = sum(1 for v in nr if v > GRAPH_MAX_BS)
        nr_sorted = sorted(nr)
        p50 = nr_sorted[len(nr_sorted) // 2]
        p90 = nr_sorted[int(0.9 * (len(nr_sorted) - 1))]
        print(f"     num_running_reqs: p50={p50:.0f} p90={p90:.0f} max={max(nr):.0f} · "
              f">graph상한({GRAPH_MAX_BS}) 스냅샷 {over}/{len(nr)} = {100.0*over/len(nr):.1f}% "
              f"(eager 낙하 구간 비율 — 셀 간 비교 시 교란으로 취급)")

    print(f"     steplog_enabled(run_meta) = {meta.get('steplog_enabled')}")

    n_fail = sum(1 for x in _result if not x)
    print(f"\nRESULT: {'PASS' if n_fail == 0 else f'FAIL ({n_fail})'}")
    sys.exit(0 if n_fail == 0 else 1)


if __name__ == "__main__":
    main()
