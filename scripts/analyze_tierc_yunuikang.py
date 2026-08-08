#!/usr/bin/env python3
"""Tier C 집계·분해·그림 + closure 게이트.

입력 (한 디렉터리 안):
  steplog_<TAG>.jsonl.<pid>   forward/xfer 이벤트  (mori_tierc_instrument 가 씀)
  window_<TAG>.json           계측 창 t_start/t_end + 셀 파라미터
  profile_<TAG>/step_profiles.csv   프록시 per-step (Method B 의 new_required 용)

GPU 가산 예산
  decode_ms + prefill_new_ms + prefill_recompute_ms + idle_ms = window_wall_ms
  * idle_ms 는 유도값 = window_wall − (decode + prefill)
  * transfer_ms 는 **예산에 더하지 않는다** — 별도 스트림에서 compute 와 overlap 되므로
    가산하면 이중 계상이다. 진단용 상한으로만 병기한다. 실제 reload stall 은 idle 에 흡수된다.

Method B (집계 빼기 — 엔진 침습 최소)
  prefill_computed_tok = Σ extend_num_tokens            (엔진이 실제로 계산한 prefill 토큰)
  new_required_tok     = Σ per-program 불가피 컨텍스트 증가   (프록시 per-step CSV 에서 유도)
        step i>0:  prompt[i] − (prompt[i-1] + completion[i-1])
        step i=0:  prompt[0]
  recompute_tok        = computed − new_required
  prefill_ms 를 토큰 비로 안분한다 (prefill 토큰당 비용 균일 가정 — [추정]).

시스템 간 비교는 완주량이 다를 수 있으므로 **완료 토큰당 / 턴당으로 정규화**해 병기한다.
"""
import argparse
import csv
import glob
import json
import os
import sys
from collections import defaultdict

CLOSURE_TOL = 0.05          # ±5%
SYS_COLOR = {"MORI": "#C0392B", "TAO": "#2E5EAA", "TA+O": "#2E5EAA"}
PART_COLOR = {
    "decode": "#1E7D4F",
    "prefill_new": "#2E5EAA",
    "prefill_recompute": "#C0392B",
    "idle": "#C9CDD6",
}
PART_LABEL = {
    "decode": "decode (생성)",
    "prefill_new": "prefill — 새 컨텍스트",
    "prefill_recompute": "prefill — 재계산",
    "idle": "idle (GPU 유휴)",
}


# ───────────────────────────────────────────── 입력 로드
def load_steplog(d, tag):
    """★ TP>1 이면 모든 rank 가 **같은 forward 를 동시에** 돌므로 그대로 합치면
    GPU 시간이 rank 수만큼 이중 계상된다 (TP2 → busy 가 wall 의 2배 → C1 FAIL).
    forward 는 rank 간 동기적이므로 **한 rank 만** 세는 것이 올바른 wall-clock 몫이다.
    HiCache 전송도 각 rank 가 자기 KV shard 를 병렬 전송하므로 동일하게 한 rank 만 센다.
    """
    pats = [f"steplog_{tag}.*.jsonl", f"steplog_{tag}.jsonl", f"steplog_{tag}.jsonl.*"]
    files = sorted({f for pat in pats for f in glob.glob(os.path.join(d, pat))})
    by_pid = {}
    for p in files:
        recs = []
        with open(p) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    recs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass          # 마지막 줄이 잘렸을 수 있다
        if any(r.get("kind") == "fwd" for r in recs):
            by_pid[p] = recs
    if not by_pid:
        return [], {"ranks": 0, "picked": None, "files": len(files)}

    # rank 0 우선. rank 스탬프가 없는 구버전 로그는 pid 오름차순 첫 파일.
    def rank_of(recs):
        for r in recs:
            if r.get("kind") == "fwd" and r.get("rank") is not None:
                return r["rank"]
        return None

    ranks = {p: rank_of(rs) for p, rs in by_pid.items()}
    zero = [p for p, rk in ranks.items() if rk == 0]
    picked = sorted(zero)[0] if zero else sorted(by_pid)[0]
    meta = {"ranks": len(by_pid), "picked": os.path.basename(picked),
            "picked_rank": ranks[picked], "files": len(files),
            "dropped": [os.path.basename(p) for p in sorted(by_pid) if p != picked]}
    return by_pid[picked], meta


def driver_deltas(d, tag):
    """드라이버 결과 jsonl 에서 **전체 run** 엔진 델타를 읽는다.
    창 슬라이싱과 무관한 절대 교차검증용 — steplog 토큰 회계가 맞는지 여기서 검증한다."""
    for name in ("results_smoke.jsonl", "results_tierc.jsonl", "results_c50.jsonl"):
        p = os.path.join(d, name)
        if not os.path.exists(p):
            continue
        for line in open(p):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("run_tag") != tag:
                continue
            m = r.get("sglang_metrics") or {}
            pt, gt = m.get("prompt_tokens_total_delta"), m.get("generation_tokens_total_delta")
            ex = m.get("hicache_extra") or {}
            # cached 델타는 절대값만 있어 run 시작 0 가정 (백엔드를 셀마다 재기동하므로 성립)
            ca = ex.get("sglang:cached_tokens_total")
            if pt is None or ca is None:
                return None
            return {"computed": pt - ca, "generation": gt}
    return None


def load_window(d, tag):
    p = os.path.join(d, f"window_{tag}.json")
    return json.load(open(p)) if os.path.exists(p) else None


def new_required_tokens(d, tag, lo, hi):
    """프록시 per-step CSV → 프로그램별 불가피 컨텍스트 증가 합 (Method B 의 분모)."""
    p = os.path.join(d, f"profile_{tag}", "step_profiles.csv")
    if not os.path.exists(p):
        return None, None, None
    rows = [r for r in csv.DictReader(open(p))]
    if not rows:
        return None, None, None
    per_prog = defaultdict(list)
    for r in rows:
        try:
            per_prog[r["program_id"]].append((
                int(r["step_id"]), float(r["completed_at"]),
                int(float(r["prompt_tokens"])), int(float(r["completion_tokens"]))))
        except (KeyError, ValueError):
            continue
    new_tok, comp_tok, nstep = 0, 0, 0
    for _, steps in per_prog.items():
        steps.sort()
        prev = None
        for _, t, prompt, completion in steps:
            inc = prompt if prev is None else max(0, prompt - (prev[0] + prev[1]))
            prev = (prompt, completion)
            if lo <= t <= hi:                 # 창 안의 스텝만 센다
                new_tok += inc
                comp_tok += completion
                nstep += 1
    return new_tok, comp_tok, nstep


# ───────────────────────────────────────────── 집계
def aggregate(d, tag):
    win = load_window(d, tag)
    if win is None:
        return {"tag": tag, "error": f"window_{tag}.json 없음"}
    t0, t1 = win["t_start"], win["t_end"]
    warm = float(win.get("warm", 0.2))
    lo = t0 + warm * (t1 - t0)                # 고정 steady 창 — 다른 지표와 동일 규약
    hi = t1
    wall_ms = (hi - lo) * 1e3

    recs, srcmeta = load_steplog(d, tag)
    if not recs:
        return {"tag": tag, "error": "steplog 비어 있음 (계측이 안 걸렸다)"}

    a = {"decode_ms": 0.0, "prefill_ms": 0.0, "other_ms": 0.0,
         "decode_tok": 0, "prefill_computed_tok": 0,
         "decode_steps": 0, "prefill_steps": 0, "host_ms": 0.0,
         "xfer_reload_ms": 0.0, "xfer_offload_ms": 0.0,
         "reload_tok": 0, "offload_tok": 0, "xfer_events": 0,
         "dropped_no_gpu_ms": 0, "steps_in_window": 0}

    # 전체 run 합계 (창 무관) — 드라이버 델타와의 절대 교차검증용
    full = {"prefill_tok": 0, "decode_tok": 0}
    for r in recs:
        if r.get("kind") == "fwd" and r.get("gpu_ms") is not None:
            if r.get("batch") == "prefill":
                full["prefill_tok"] += int(r.get("ntok") or 0)
            elif r.get("batch") == "decode":
                full["decode_tok"] += int(r.get("ntok") or 0)

    for r in recs:
        k = r.get("kind")
        t = r.get("t")
        if k not in ("fwd", "xfer") or t is None or not (lo <= t <= hi):
            continue
        ms = r.get("gpu_ms")
        if ms is None:
            a["dropped_no_gpu_ms"] += 1
            continue
        if k == "fwd":
            a["steps_in_window"] += 1
            a["host_ms"] += float(r.get("host_ms") or 0.0)
            b = r.get("batch")
            if b == "decode":
                a["decode_ms"] += ms; a["decode_tok"] += int(r.get("ntok") or 0)
                a["decode_steps"] += 1
            elif b == "prefill":
                a["prefill_ms"] += ms
                a["prefill_computed_tok"] += int(r.get("ntok") or 0)
                a["prefill_steps"] += 1
            else:
                a["other_ms"] += ms
        else:
            a["xfer_events"] += 1
            if r.get("dir") == "reload":
                a["xfer_reload_ms"] += ms; a["reload_tok"] += int(r.get("ntok") or 0)
            else:
                a["xfer_offload_ms"] += ms; a["offload_tok"] += int(r.get("ntok") or 0)

    # ── Method B: new vs recompute
    new_tok, out_tok, nstep = new_required_tokens(d, tag, lo, hi)
    computed = a["prefill_computed_tok"]
    if new_tok is None:
        split = {"new_required_tok": None, "recompute_tok": None,
                 "prefill_new_ms": None, "prefill_recompute_ms": None,
                 "note": "profile CSV 없음 — prefill 분해 불가"}
    else:
        new_eff = min(new_tok, computed)          # 창 경계 어긋남으로 초과할 수 있다
        recomp = max(0, computed - new_eff)
        frac = (new_eff / computed) if computed else 0.0
        split = {"new_required_tok": new_tok, "new_required_used_tok": new_eff,
                 "recompute_tok": recomp,
                 "recompute_frac": (recomp / computed) if computed else None,
                 "prefill_new_ms": a["prefill_ms"] * frac,
                 "prefill_recompute_ms": a["prefill_ms"] * (1 - frac),
                 "new_over_computed": (new_tok / computed) if computed else None,
                 "note": None if new_tok <= computed else
                         (f"new_required 가 computed 의 {new_tok/computed:.2f}배 → "
                          "recompute≈0 으로 본다. 압박이 없어 재계산이 실제로 없거나, "
                          "창 경계 불일치. 압박 있는 셀에서 재확인 필요")}

    busy_ms = a["decode_ms"] + a["prefill_ms"] + a["other_ms"]
    idle_ms = wall_ms - busy_ms

    out = {"tag": tag, "system": win.get("system", tag), "C": win.get("C"),
           "window_s": (hi - lo), "wall_ms": wall_ms,
           "busy_ms": busy_ms, "idle_ms": idle_ms,
           "gpu_busy_frac": busy_ms / wall_ms if wall_ms else None,
           "out_tok_window": out_tok, "steps_profile": nstep,
           "steplog_src": srcmeta, "full_run": full, **a, **split}

    # ── closure 진단
    #
    # ⚠️ idle 은 wall − busy 로 **유도**한 값이라 "decode+prefill+idle = wall" 은 항등식이다.
    #    그걸 검사해 봐야 항상 통과한다 → 계측 구멍을 못 잡는다.
    #    실제로 검사해야 하는 것은 **유도가 성립할 조건** 셋이다:
    #      C1  busy ≤ wall        (초과하면 이중 계상 — 예산이 음수 idle 을 낳는다)
    #      C2  steplog 이 창을 덮는가 (일부만 덮으면 busy 가 과소 → idle 이 가짜로 커진다)
    #      C3  GPU busy 가 run_batch host 시간과 물리적으로 정합하는가
    checks = []

    # C1
    if idle_ms < 0:
        checks.append(("FAIL", f"C1 busy({busy_ms/1e3:.2f}s) > wall({wall_ms/1e3:.2f}s) — "
                               "이중 계상 (idle 이 음수)"))
    else:
        checks.append(("PASS", f"C1 busy ≤ wall — busy {busy_ms/wall_ms*100:.2f}%, "
                               f"idle {idle_ms/wall_ms*100:.2f}%"))

    # C2 — steplog 이 창을 시간적으로 덮는가
    ts = [r["t"] for r in recs if r.get("kind") == "fwd" and r.get("t") is not None
          and lo <= r["t"] <= hi]
    if not ts:
        checks.append(("FAIL", "C2 창 안 forward step 0 — 창 경계 또는 계측 오류"))
    else:
        cov = (max(ts) - min(ts)) / (hi - lo)
        gap_head = (min(ts) - lo) / (hi - lo)
        gap_tail = (hi - max(ts)) / (hi - lo)
        checks.append(("PASS" if cov >= 1 - CLOSURE_TOL else "FAIL",
                       f"C2 steplog 커버리지 {cov*100:.2f}% "
                       f"(앞 공백 {gap_head*100:.2f}% · 뒤 공백 {gap_tail*100:.2f}%, "
                       f"허용 미달 {CLOSURE_TOL*100:.0f}%)"))

    # C3 — overlap 스케줄링에서 host 는 **enqueue 만** 하고 즉시 반환하므로
    #      GPU/host 가 10× 를 넘는 것도 정상이다. 이상신호는 "GPU 가 host 보다 훨씬 작을 때"뿐.
    if a["host_ms"] > 0:
        ratio = busy_ms / a["host_ms"]
        st = "PASS" if ratio >= 0.5 else "WARN"
        checks.append((st, f"C3 GPU busy ÷ forward host 시간 = {ratio:.2f}× "
                           f"(overlap 이라 host 는 enqueue 만 — 1 초과가 정상, 0.5 미만이면 의심)"))

    # C4 ★ 토큰 회계 교차검증 — steplog 전체 run 합 vs 드라이버가 보고한 엔진 델타.
    #    창 슬라이싱과 무관한 절대 검증이라 계측 정확성의 핵심 근거다.
    dd = driver_deltas(d, tag)
    if dd and dd.get("computed"):
        rp = full["prefill_tok"] / dd["computed"]
        rd = (full["decode_tok"] / dd["generation"]) if dd.get("generation") else None
        ok = 0.9 <= rp <= 1.1 and (rd is None or 0.9 <= rd <= 1.1)
        checks.append(("PASS" if ok else "FAIL",
                       f"C4 토큰 교차검증 (전체 run): prefill {full['prefill_tok']:,} ÷ 엔진 "
                       f"{dd['computed']:,} = {rp:.3f}"
                       + (f" · decode {full['decode_tok']:,} ÷ {dd['generation']:,} = {rd:.3f}"
                          if rd is not None else "")
                       + "  (허용 0.9~1.1)"))
        out["xcheck_prefill_ratio"] = rp
        out["xcheck_decode_ratio"] = rd
    else:
        checks.append(("WARN", "C4 드라이버 델타 없음 — 토큰 교차검증 생략"))

    if a["dropped_no_gpu_ms"]:
        checks.append(("WARN", f"gpu_ms 결측 {a['dropped_no_gpu_ms']}건 "
                               "(종료 시 미완료 이벤트 — 소량이면 무해)"))
    out["checks"] = checks
    out["closure_ok"] = all(s != "FAIL" for s, _ in checks)
    return out


# ───────────────────────────────────────────── 그림
def plot(aggs, outdir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Noto Sans CJK KR"
    plt.rcParams["axes.unicode_minus"] = False
    INK, MUTE, GRID = "#1A1A2E", "#6B6B7B", "#DDE1E8"

    ok = [a for a in aggs if not a.get("error") and a.get("prefill_new_ms") is not None]
    if not ok:
        print("  [plot] 그릴 셀이 없다 (prefill 분해 실패)")
        return None
    fig, axes = plt.subplots(1, 2, figsize=(11.4, 4.2),
                             gridspec_kw={"width_ratios": [1.15, 1.0]})

    # 좌: GPU 시간 예산 스택 (절대 ms → % 로 정규화해 두 시스템 창 길이 차이를 제거)
    ax = axes[0]
    parts = ["decode", "prefill_new", "prefill_recompute", "idle"]
    xs = range(len(ok))
    bottom = [0.0] * len(ok)
    for p in parts:
        key = {"decode": "decode_ms", "prefill_new": "prefill_new_ms",
               "prefill_recompute": "prefill_recompute_ms", "idle": "idle_ms"}[p]
        vals = [max(0.0, a[key]) / a["wall_ms"] * 100 for a in ok]
        ax.bar(xs, vals, 0.5, bottom=bottom, color=PART_COLOR[p],
               edgecolor="white", linewidth=1.3, label=PART_LABEL[p])
        for i, (v, b) in enumerate(zip(vals, bottom)):
            if v >= 4:
                ax.text(i, b + v / 2, f"{v:.1f}%", ha="center", va="center",
                        fontsize=9.5, color="white" if p != "idle" else INK,
                        fontweight="bold")
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set_xticks(list(xs)); ax.set_xticklabels([a["system"] for a in ok], fontsize=11)
    ax.set_ylim(0, 108)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTE, labelsize=9.5)
    ax.grid(axis="y", color=GRID, lw=0.7); ax.set_axisbelow(True)
    ax.set_ylabel("window wall 중 비중 (%)", color=MUTE, fontsize=10)
    ax.set_title("GPU 시간 분해 — 가산 예산 (합 = 100%)", color=INK,
                 fontsize=11.5, fontweight="bold", pad=9)
    ax.legend(frameon=False, fontsize=8.5, loc="upper center", ncol=2,
              columnspacing=1.0, handlelength=1.3)

    # 우: 정규화 지표 (완료 토큰당) — 완주량 차이를 제거한 비교
    ax = axes[1]
    metrics = [("recompute 토큰\n/ 출력 토큰", lambda a: (a["recompute_tok"] / a["out_tok_window"])
                if a.get("out_tok_window") else 0),
               ("reload 토큰\n/ 출력 토큰", lambda a: (a["reload_tok"] / a["out_tok_window"])
                if a.get("out_tok_window") else 0)]
    w = 0.34
    for k, a in enumerate(ok):
        pos = [i + (k - (len(ok) - 1) / 2) * w for i in range(len(metrics))]
        vals = [f(a) for _, f in metrics]
        ax.bar(pos, vals, w, color=SYS_COLOR.get(a["system"], "#6B6B7B"),
               edgecolor="white", linewidth=1.3, label=a["system"])
        for x, v in zip(pos, vals):
            ax.annotate(f"{v:.2f}", (x, v), textcoords="offset points", xytext=(0, 5),
                        ha="center", fontsize=10, fontweight="bold", color=INK)
    ax.set_xticks(range(len(metrics)))
    ax.set_xticklabels([m[0] for m in metrics], fontsize=9.5)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTE, labelsize=9.5)
    ax.grid(axis="y", color=GRID, lw=0.7); ax.set_axisbelow(True)
    ax.set_ylabel("출력 토큰당 (정규화)", color=MUTE, fontsize=10)
    ax.set_title("정규화 비교 — 완주량 차이 제거", color=INK,
                 fontsize=11.5, fontweight="bold", pad=9)
    ax.legend(frameon=False, fontsize=9.5, loc="upper left")

    sub = " · ".join(f"{a['system']}: transfer {(a['xfer_reload_ms']+a['xfer_offload_ms'])/a['wall_ms']*100:.1f}% "
                     f"(별도 스트림, 예산 미가산)" for a in ok)
    fig.suptitle(sub, fontsize=9.5, color=MUTE, y=1.02)
    os.makedirs(outdir, exist_ok=True)
    p = os.path.join(outdir, "mori_tierc_budget_yunuikang.png")
    fig.savefig(p, dpi=200, bbox_inches="tight", facecolor="white")
    print(f"  [plot] {p}")
    return p


# ───────────────────────────────────────────── main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="셀 산출물 디렉터리")
    ap.add_argument("--tags", default="", help="쉼표 구분 (기본: window_*.json 자동 탐색)")
    ap.add_argument("--figdir", default="/home/yunuikang/yunuikang_work/distserving/figures")
    ap.add_argument("--gate", action="store_true", help="closure 실패 시 exit 1")
    args = ap.parse_args()

    tags = [t for t in args.tags.split(",") if t] or \
        sorted(os.path.basename(p)[len("window_"):-len(".json")]
               for p in glob.glob(os.path.join(args.dir, "window_*.json")))
    if not tags:
        print("!! window_*.json 이 없다 — 셀이 안 돌았거나 디렉터리가 틀렸다")
        return 2

    aggs = [aggregate(args.dir, t) for t in tags]
    out_json = os.path.join(args.dir, "tierc_summary.json")
    json.dump(aggs, open(out_json, "w"), ensure_ascii=False, indent=2)

    print(f"\n{'='*78}\nTier C 집계 — {args.dir}\n{'='*78}")
    hard_fail = False
    for a in aggs:
        if a.get("error"):
            print(f"\n[{a['tag']}] !! {a['error']}"); hard_fail = True; continue
        print(f"\n[{a['tag']}]  system={a['system']} C={a['C']} 창={a['window_s']:.0f}s")
        sm = a.get("steplog_src", {})
        if sm.get("ranks", 0) > 1:
            print(f"  ★ TP{sm['ranks']} — rank {sm.get('picked_rank')} ({sm['picked']}) 만 집계 "
                  f"(이중 계상 방지). 제외: {', '.join(sm.get('dropped', []))}")
        print(f"  step: decode {a['decode_steps']:,} · prefill {a['prefill_steps']:,} "
              f"· 창 안 총 {a['steps_in_window']:,} · xfer 이벤트 {a['xfer_events']:,}")
        w = a["wall_ms"]
        print(f"  GPU 예산 (창 wall {w/1e3:.1f}s = 100%)")
        print(f"    decode            {a['decode_ms']/1e3:8.2f}s  {a['decode_ms']/w*100:6.2f}%   "
              f"({a['decode_tok']:,} tok)")
        if a.get("prefill_new_ms") is not None:
            print(f"    prefill(새)       {a['prefill_new_ms']/1e3:8.2f}s  {a['prefill_new_ms']/w*100:6.2f}%   "
                  f"({a['new_required_used_tok']:,} tok)")
            print(f"    prefill(재계산)   {a['prefill_recompute_ms']/1e3:8.2f}s  "
                  f"{a['prefill_recompute_ms']/w*100:6.2f}%   ({a['recompute_tok']:,} tok · "
                  f"재계산율 {a['recompute_frac']*100:.1f}%)")
        else:
            print(f"    prefill(합)       {a['prefill_ms']/1e3:8.2f}s  {a['prefill_ms']/w*100:6.2f}%   "
                  f"({a['prefill_computed_tok']:,} tok)  ※ 분해 불가: {a.get('note')}")
        if a["other_ms"] > 0:
            print(f"    기타 batch        {a['other_ms']/1e3:8.2f}s  {a['other_ms']/w*100:6.2f}%")
        print(f"    idle              {a['idle_ms']/1e3:8.2f}s  {a['idle_ms']/w*100:6.2f}%")
        xf = a["xfer_reload_ms"] + a["xfer_offload_ms"]
        print(f"  transfer (별도 스트림 · 예산 미가산):  {xf/1e3:.2f}s  {xf/w*100:.2f}% of wall")
        print(f"    reload  {a['xfer_reload_ms']/1e3:7.2f}s  ({a['reload_tok']:,} tok)")
        print(f"    offload {a['xfer_offload_ms']/1e3:7.2f}s  ({a['offload_tok']:,} tok)")
        if a.get("out_tok_window"):
            print(f"  정규화: 출력 {a['out_tok_window']:,} tok · "
                  f"recompute/out {a['recompute_tok']/a['out_tok_window']:.3f} · "
                  f"reload/out {a['reload_tok']/a['out_tok_window']:.3f}")
        print("  closure:")
        for st, msg in a["checks"]:
            print(f"    [{st}] {msg}")
            if st == "FAIL":
                hard_fail = True
        if a.get("note"):
            print(f"    [주의] {a['note']}")

    p = plot(aggs, args.figdir)
    print(f"\n요약 JSON: {out_json}")
    if p:
        print(f"그림:      {p}")

    if hard_fail:
        print("\n★ 게이트 FAIL — closure 또는 계측 오류. push 하지 않는다.")
        return 1 if args.gate else 0
    print("\n★ 게이트 PASS — closure 통과, 계측 정상.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
