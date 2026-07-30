#!/usr/bin/env python3
"""MORI reshape of the TraceLab (SyFI) coding trace  (PLAN 2026-07-30 goguma6, §C-4).

Builds a CONSTRUCTED primary evaluation trace whose per-turn idle-period regime
approaches the MORI paper Fig.3 tool-call distribution (human-input + subagent
included), on top of an L=64k turn-window slicing (context rebased to a SEED),
NOT prefix truncation.  CPU-only.  Reads the ORIGINAL gz read-only; writes only
NEW output files.  Does NOT modify any original trace or existing script.

Pipeline (see PLAN §C-2/§C-3/§C-4):
  1. turn-window slicing to L=64k with context rebase to SEED=4096 tokens
     (longest contiguous turn window whose rebased peak context <= L).
  2. human-wait injection (primary): wall gap before a `user_message` round is
     added to that turn's tool_duration_s.  All durations clamped to CAP_HARD=300s.
     human gaps >= 12h excluded entirely (session boundary / user left).
     Ablation variant: identical selection/windows, WITHOUT human-wait.
  3. session blend: sessions are bimodal in idleness iota; select a blended
     subset (busy-heavy + idle) whose AGGREGATE long(>2s) time-share approaches
     58%.  No short-call fabrication or lengthening.
  4. interleave output session order by iota-tercile so concurrent replay sees
     iota heterogeneity.

Output schema (matches the existing processed traces exactly, one row per turn):
    {session_id, turn, input_tokens, output_tokens, tool_duration_s, cached_tokens}

DEFINITIONAL NOTES (audited):
  * The replay driver consumes ONE tool_duration_s per turn, so the regime the
    scheduler actually experiences is the PER-TURN tool_duration_s distribution.
    The blend + the 58% long-time-share gate are therefore optimized/reported on
    the per-turn quantity (the emitted, replayed value).
  * The paper Fig.3 is PER-CALL (each individual tool call / human-input).  For
    apples-to-apples shape comparison a PER-CALL-EQUIVALENT distribution
    (individual tool_wall_latency_ms + one entry per injected human-wait, each
    clamped to 300s) is ALSO reported alongside.  Both appear in the gate table.
  * This is a CONSTRUCTED subset for paper matching, NOT a natural arrival
    distribution.  meta carries "constructed": true, the blend ratio, and the
    original (pre-reshape) distribution.
"""
import argparse
import gzip
import io
import json
import math
import os
from collections import defaultdict
from datetime import datetime

import numpy as np

# ---- constants (PLAN §C-2 / §C-4) ------------------------------------------
SEED = 4096                 # rebased window-start context
L = 65536                   # L = 64k context budget
CAP_HARD = 300.0            # hard clamp on every duration (tool AND human-wait)
HW_EXCLUDE_S = 12 * 3600    # human gaps >= 12h excluded (session boundary / left)
LONG_THRESH = 2.0           # short/long boundary (s)
TARGET_SHARE = 0.58         # paper long(>2s) time-share
REASON_PREFILL = 8000.0     # T_reasoning proxy: uncached_input / 8000
REASON_DECODE = 145.0       # T_reasoning proxy: output      / 145
PS = [50, 90, 99, 99.95]

# paper Fig.3 target (tool-call durations incl human-input & subagent)
PAPER = {"P50": 1.096, "P90": 2.034, "P99": 19.98, "P99.95": 83.63,
         "short_pct": 87.0, "long_pct": 13.0, "long_time_share_pct": 58.0}
# paper CDF anchors (duration_s, cdf) reconstructed from the published points
PAPER_CDF_ANCHORS = [(0.01, 0.0), (1.096, 0.50), (2.0, 0.87), (2.034, 0.90),
                     (19.98, 0.99), (83.63, 0.9995), (CAP_HARD, 1.0)]


def _open(path):
    if path.endswith(".gz"):
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8")
    return open(path, "r", encoding="utf-8")


def _ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return None


def tool_span_s(tools):
    """Wall span of a round's tool calls (parallel-safe), in seconds — matches
    the field mapping used by the existing processed traces."""
    if not tools:
        return 0.0
    starts, ends = [], []
    for t in tools:
        a, b = _ts(t.get("emitted_at")), _ts(t.get("result_at"))
        if a is not None and b is not None:
            starts.append(a)
            ends.append(b)
    if starts and ends:
        return max(0.0, max(ends) - min(starts))
    total_ms = 0.0
    for t in tools:
        ms = t.get("tool_wall_latency_ms")
        if ms is None:
            ms = t.get("tool_internal_latency_ms")
        if ms:
            total_ms += float(ms)
    return total_ms / 1000.0


# ---------------------------------------------------------------------------
# 1. load gz -> per-session round records (read-only)
# ---------------------------------------------------------------------------
def load_sessions(path):
    sessions = defaultdict(list)
    n_rows = n_nonpos = 0
    with _open(path) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            n_rows += 1
            itot = int(d.get("input_tokens_total") or 0)
            if itot <= 0:                       # invalid/empty rows (mirror base prep)
                n_nonpos += 1
                continue
            tools = d.get("tools") or []
            evs = d.get("timing_events") or []
            ev_ts = [_ts(e.get("timestamp")) for e in evs]
            ev_ts = [t for t in ev_ts if t is not None]
            um_ts = [_ts(e.get("timestamp")) for e in evs
                     if e.get("event_type") == "user_message" and _ts(e.get("timestamp")) is not None]
            cached = d.get("claude_cache_read_input_tokens")
            if cached is None:
                cached = d.get("prefix_tokens")
            rec = {
                "round_index": int(d.get("round_index", 0)),
                "itot": itot,
                "otok": int(d.get("output_tokens") or 0),
                "unc": int(d.get("claude_uncached_input_tokens") or 0),
                "cached": int(cached or 0),
                "tool_span": tool_span_s(tools),
                "tool_calls": [float(t["tool_wall_latency_ms"]) / 1000.0
                               for t in tools if t.get("tool_wall_latency_ms") is not None],
                "fie": d.get("first_input_event_type"),
                "last_ts": max(ev_ts) if ev_ts else None,
                "first_um_ts": min(um_ts) if um_ts else None,
            }
            sessions[d.get("session_id")].append(rec)
    return sessions, n_rows, n_nonpos


# ---------------------------------------------------------------------------
# 2. turn-window slicing (longest contiguous window; rebased peak <= L)
# ---------------------------------------------------------------------------
def best_window(rounds):
    """Return (i, j) inclusive indices of the longest contiguous window whose
    context, after rebasing the start to SEED, stays within L:
        max_{t in [i,j]} itot[t] - itot[i] <= L - SEED.
    Tie-break: earliest start.  Empty session -> None."""
    n = len(rounds)
    if n == 0:
        return None
    budget = L - SEED
    itot = [r["itot"] for r in rounds]
    # Longest window whose context SPAN (max - min) <= budget. Using max-min (not
    # max - start) is REQUIRED: some sessions are non-monotonic (context resets),
    # so anchoring on the start value produced negative rebased tokens. Two-pointer
    # with monotonic deques -> O(n).
    from collections import deque
    maxd: deque = deque()
    mind: deque = deque()
    left = 0
    best = (0, 0)
    best_len = 1
    for right in range(n):
        while maxd and itot[maxd[-1]] <= itot[right]:
            maxd.pop()
        maxd.append(right)
        while mind and itot[mind[-1]] >= itot[right]:
            mind.pop()
        mind.append(right)
        while itot[maxd[0]] - itot[mind[0]] > budget:
            left += 1
            if maxd[0] < left:
                maxd.popleft()
            if mind[0] < left:
                mind.popleft()
        if right - left + 1 > best_len:
            best_len = right - left + 1
            best = (left, right)
    return best


# ---------------------------------------------------------------------------
# 3. build per-session windowed turn records + iota / blend metrics
# ---------------------------------------------------------------------------
def build_session(sid, rounds):
    """rounds: session round records sorted by round_index.  Returns a dict of
    windowed per-turn data for both the primary (human-wait injected) and the
    ablation (no human-wait) variants, plus iota and blend metrics."""
    win = best_window(rounds)
    if win is None:
        return None
    i, j = win
    # Rebase against the window MINIMUM (not the start) so rebased context is
    # always >= SEED even when the session's context is non-monotonic.
    offset = min(rounds[k]["itot"] for k in range(i, j + 1)) - SEED

    # human-wait per position (uses the previous KEPT round's last_ts)
    def hw_at(pos):
        if pos == 0:
            return None, False
        r = rounds[pos]
        if r["fie"] != "user_message" or r["first_um_ts"] is None:
            return None, False
        prev_last = rounds[pos - 1]["last_ts"]
        if prev_last is None:
            return None, False
        gap = r["first_um_ts"] - prev_last
        if gap < 0:
            gap = 0.0
        if gap >= HW_EXCLUDE_S:
            return None, True                    # excluded (session boundary / left)
        return gap, False

    turns = []
    calls_primary, calls_ablation = [], []       # per-call-equivalent pools
    td_primary, td_ablation = [], []             # per-turn emitted values
    T_reason = 0.0
    n_hw_inj = n_hw_excl = 0
    wlen = j - i + 1
    for k, pos in enumerate(range(i, j + 1)):
        r = rounds[pos]
        in_reb = r["itot"] - offset
        cached_reb = min(max(r["cached"] - offset, 0), in_reb)
        tool_s = min(r["tool_span"], CAP_HARD)
        hw, excl = hw_at(pos)
        if excl:
            n_hw_excl += 1
        hw_c = min(hw, CAP_HARD) if hw is not None else 0.0
        if hw is not None and hw > 0:
            n_hw_inj += 1
        is_last = (k == wlen - 1)
        # per-turn emitted values (last turn: no trailing wait, per existing convention)
        p_td = 0.0 if is_last else min(tool_s + hw_c, CAP_HARD)
        a_td = 0.0 if is_last else tool_s
        td_primary.append(p_td)
        td_ablation.append(a_td)
        # per-call-equivalent pools (skip the zeroed last turn for consistency)
        if not is_last:
            cc = [min(c, CAP_HARD) for c in r["tool_calls"]]
            calls_ablation.extend(cc)
            calls_primary.extend(cc)
            if hw is not None and hw > 0:
                calls_primary.append(min(hw, CAP_HARD))
        T_reason += r["unc"] / REASON_PREFILL + r["otok"] / REASON_DECODE
        turns.append({
            "session_id": sid,
            "input_tokens": int(in_reb),
            "output_tokens": r["otok"],
            "cached_tokens": int(cached_reb),
            "td_primary": round(p_td, 3),
            "td_ablation": round(a_td, 3),
        })

    T_acting = float(sum(td_primary))            # tool + human-wait (primary)
    denom = T_acting + T_reason
    iota = (T_acting / denom) if denom > 0 else 0.0
    tdp = np.asarray(td_primary, float)
    Ls = float(tdp[tdp > LONG_THRESH].sum())     # long time (primary, per-turn)
    Ts = float(tdp.sum())
    labels = [v > LONG_THRESH for v in td_primary]
    n_trans = sum(1 for a, b in zip(labels, labels[1:]) if a != b)
    return {
        "sid": sid, "turns": turns, "iota": iota, "n_trans": n_trans,
        "peak_ctx": max(t["input_tokens"] for t in turns),
        "L_s": Ls, "T_s": Ts,
        "td_primary": td_primary, "td_ablation": td_ablation,
        "calls_primary": calls_primary, "calls_ablation": calls_ablation,
        "n_hw_inj": n_hw_inj, "n_hw_excl": n_hw_excl,
    }


# ---------------------------------------------------------------------------
# 4. blend selection: approach 58% aggregate per-turn long-time-share
# ---------------------------------------------------------------------------
def _iqr(vals):
    q1, q3 = np.percentile(vals, [25, 75])
    return float(q3 - q1)


def choose_blend(sess, tol=0.01, min_turns=6):
    """sess: list of per-session dicts.  Returns (selected_sids, selected, report).

    Dilution (short-time) must come from busy-heavy (low-iota, ~0% long-share)
    sessions; long-time from idle/mixed sessions -- the population is bimodal so
    NO single stratum sits at 58% (PLAN §C-4).  The blend therefore MUST mix the
    two extremes, which structurally lowers the busy<->idle transition median and
    compresses the iota spread.  To satisfy 58% while keeping the trace as
    transition-rich / iota-heterogeneous as possible, we prefer LARGER busy
    sessions (which still dilute but carry real transitions) over tiny all-short
    ones, and search over how many busy sessions to use:

      * busy pool sorted by short-time (T_s) DESCENDING  (few big diluters first)
      * idle/mixed contributors sorted by long-time (L_s) ASCENDING (fine control)
      * for each busy-prefix size, pick the contributor-prefix that best hits 58%
      * among busy-prefix sizes whose aggregate is within `tol` of 58%, choose the
        one MAXIMIZING (transition_median, per-session iota IQR); else min |gap|.

    Sessions shorter than `min_turns` are excluded from the pool (degenerate
    1-2 turn sessions carry no transitions and only dilute the median); the count
    excluded is reported.  No short-call fabrication or lengthening anywhere."""
    iotas_all = np.array([s["iota"] for s in sess])
    q33, q67 = np.percentile(iotas_all, [33.3, 66.7])
    for s in sess:
        s["tercile"] = ("busy" if s["iota"] < q33
                        else "idle" if s["iota"] >= q67 else "mixed")
    pool = [s for s in sess if len(s["turns"]) >= min_turns]
    n_excluded_short = len(sess) - len(pool)

    busy = sorted((s for s in pool if s["tercile"] == "busy"),
                  key=lambda s: -s["T_s"])                 # biggest diluters first
    contrib = sorted((s for s in pool if s["tercile"] != "busy"),
                     key=lambda s: s["L_s"])               # smallest long-time first
    bL = np.cumsum([0.0] + [s["L_s"] for s in busy])
    bT = np.cumsum([0.0] + [s["T_s"] for s in busy])
    cL = np.cumsum([0.0] + [s["L_s"] for s in contrib])
    cT = np.cumsum([0.0] + [s["T_s"] for s in contrib])
    busy_tr = [s["n_trans"] for s in busy]
    busy_io = [s["iota"] for s in busy]
    con_tr = [s["n_trans"] for s in contrib]
    con_io = [s["iota"] for s in contrib]

    best = None                       # (feasible, tmed, iqr, -gap, nb, ni, agg)
    step = max(1, len(busy) // 120)
    nb_grid = sorted(set(list(range(0, len(busy) + 1, step)) + [len(busy)]))
    for nb in nb_grid:
        denom = bT[nb] + cT
        with np.errstate(divide="ignore", invalid="ignore"):
            agg = (bL[nb] + cL) / denom
        gaps = np.abs(agg - TARGET_SHARE)
        gaps[denom <= 0] = np.inf
        ni = int(np.argmin(gaps))
        gap = float(gaps[ni])
        if not np.isfinite(gap):
            continue
        a = float(agg[ni])
        sel_tr = busy_tr[:nb] + con_tr[:ni]
        sel_io = busy_io[:nb] + con_io[:ni]
        if not sel_tr:
            continue
        tmed = float(np.median(sel_tr))
        iqr = _iqr(sel_io)
        feasible = gap <= tol
        key = (feasible, tmed, iqr, -gap)
        if best is None or key > best[0]:
            best = (key, nb, ni, a, gap, tmed, iqr)
    _, nb, ni, agg, gap, tmed, iqr = best
    selected = busy[:nb] + contrib[:ni]
    sel_sids = {s["sid"] for s in selected}
    counts = {"busy": 0, "mixed": 0, "idle": 0}
    for s in selected:
        counts[s["tercile"]] += 1
    report = {
        "iota_terciles": {"q33": round(float(q33), 4), "q67": round(float(q67), 4),
                          "mean": round(float(iotas_all.mean()), 4)},
        "source_session_terciles": {
            "busy": sum(1 for s in sess if s["tercile"] == "busy"),
            "mixed": sum(1 for s in sess if s["tercile"] == "mixed"),
            "idle": sum(1 for s in sess if s["tercile"] == "idle")},
        "pool_min_turns": min_turns,
        "sessions_excluded_lt_min_turns": n_excluded_short,
        "blend_selected_counts": counts,
        "blend_ratio_busy_mixed_idle": f"{counts['busy']}:{counts['mixed']}:{counts['idle']}",
        "busy_used_of_pool": f"{nb}/{len(busy)}",
        "contrib_used_of_pool": f"{ni}/{len(contrib)}",
        "tolerance_pct_points": round(100 * tol, 3),
        "within_tolerance": bool(gap <= tol),
        "achieved_aggregate_long_time_share_pct": round(100 * agg, 3),
        "residual_gap_pct_points": round(100 * (agg - TARGET_SHARE), 3),
        "selected_transition_median": tmed,
        "selected_iota_iqr": round(iqr, 4),
    }
    return sel_sids, selected, report


def select_pool(sess, min_turns=4):
    """Track M (MORI-mechanism, PRIMARY): tag iota terciles and take the FULL
    >=min_turns windowed pool with NO 58% blend.

    Audit (PLAN §C-4b) showed the pool already passes both hard gates
    (transition-median 4.0, per-session iota-IQR ~0.69); the 58% blend is what
    collapses them (mixing ~0%-busy + ~98%-idle sessions). Track M therefore
    keeps the pool intact: long-time-share is idle-heavy (~98%) BY DESIGN and the
    58% paper-regime match is abandoned as an emergent property of the paper's
    agent (1.1s median tool call) that our agent (0.24s) cannot reproduce."""
    iotas_all = np.array([s["iota"] for s in sess])
    q33, q67 = np.percentile(iotas_all, [33.3, 66.7])
    for s in sess:
        s["tercile"] = ("busy" if s["iota"] < q33
                        else "idle" if s["iota"] >= q67 else "mixed")
    pool = [s for s in sess if len(s["turns"]) >= min_turns]
    counts = {"busy": 0, "mixed": 0, "idle": 0}
    for s in pool:
        counts[s["tercile"]] += 1
    report = {
        "track": "M (MORI-mechanism, primary)",
        "blend": "none (full >=min_turns pool; 58% NOT targeted)",
        "iota_terciles": {"q33": round(float(q33), 4), "q67": round(float(q67), 4),
                          "mean": round(float(iotas_all.mean()), 4)},
        "pool_min_turns": min_turns,
        "sessions_excluded_lt_min_turns": len(sess) - len(pool),
        "selected_counts": counts,
        "ratio_busy_mixed_idle": f"{counts['busy']}:{counts['mixed']}:{counts['idle']}",
    }
    return {s["sid"] for s in pool}, pool, report


# ---------------------------------------------------------------------------
# 5. interleave selected sessions by iota-tercile (round-robin)
# ---------------------------------------------------------------------------
def interleave(selected):
    buckets = {"busy": [], "mixed": [], "idle": []}
    for s in sorted(selected, key=lambda s: s["iota"]):
        buckets[s["tercile"]].append(s)
    order, idx = [], {k: 0 for k in buckets}
    remaining = sum(len(v) for v in buckets.values())
    keys = ["busy", "mixed", "idle"]
    while remaining:
        for kk in keys:
            if idx[kk] < len(buckets[kk]):
                order.append(buckets[kk][idx[kk]])
                idx[kk] += 1
                remaining -= 1
    return order


# ---------------------------------------------------------------------------
# gate helpers
# ---------------------------------------------------------------------------
def dist(arr):
    a = np.asarray(arr, float)
    if a.size == 0:
        return {"n": 0}
    p = {f"P{q}": round(float(np.percentile(a, q)), 4) for q in PS}
    long = a[a > LONG_THRESH]
    p.update({
        "n": int(a.size),
        "short_pct": round(100 * float((a <= LONG_THRESH).mean()), 2),
        "long_pct": round(100 * float((a > LONG_THRESH).mean()), 2),
        "long_time_share_pct": round(100 * float(long.sum() / a.sum()) if a.sum() > 0 else 0.0, 3),
        "mean": round(float(a.mean()), 4), "max": round(float(a.max()), 3),
    })
    return p


def paper_cdf(x):
    xs = [a for a, _ in PAPER_CDF_ANCHORS]
    ys = [b for _, b in PAPER_CDF_ANCHORS]
    lx = math.log10(max(x, 1e-6))
    lxs = [math.log10(v) for v in xs]
    if lx <= lxs[0]:
        return 0.0
    if lx >= lxs[-1]:
        return 1.0
    return float(np.interp(lx, lxs, ys))


def ks_vs_paper(arr):
    a = np.sort(np.asarray(arr, float))
    if a.size == 0:
        return None
    grid = np.unique(np.clip(a, 1e-3, CAP_HARD))
    n = a.size
    ks = 0.0
    for x in grid:
        femp = np.searchsorted(a, x, side="right") / n
        ks = max(ks, abs(femp - paper_cdf(x)))
    return round(float(ks), 4)


def transitions_median(sessions_td):
    """Median number of busy<->idle transitions per session (threshold 2s)."""
    counts = []
    for td in sessions_td:
        labels = [v > LONG_THRESH for v in td]
        counts.append(sum(1 for a, b in zip(labels, labels[1:]) if a != b))
    return (float(np.median(counts)) if counts else 0.0), counts


def concurrent_iota_iqr(order, k_slots=8, n_ticks=400):
    """Simple concurrency simulation: feed the interleaved session order into
    k_slots concurrent slots (each session runs for its wall = T_acting+T_reason
    proxy), sample the iota of every active session at n_ticks even ticks across
    the makespan, and return the IQR of all sampled iota values."""
    walls, iotas = [], []
    for s in order:
        w = s["T_s"] + max(s["T_s"] / max(s["iota"], 1e-6) - s["T_s"], 0.0) if s["iota"] > 0 else s["T_s"]
        walls.append(max(w, 1e-3))
        iotas.append(s["iota"])
    # round-robin assign sessions to slots; build per-slot cumulative timelines
    slots = [[] for _ in range(k_slots)]
    for n, s in enumerate(order):
        slots[n % k_slots].append(n)
    slot_cum, slot_end = [], []
    for sl in slots:
        c = np.cumsum([0.0] + [walls[n] for n in sl])
        slot_cum.append(c)
        slot_end.append(c[-1] if len(c) else 0.0)
    makespan = max(slot_end) if slot_end else 0.0
    if makespan <= 0:
        return None
    sampled = []
    for tick in np.linspace(0, makespan, n_ticks, endpoint=False):
        for si, sl in enumerate(slots):
            c = slot_cum[si]
            if not len(sl) or tick >= c[-1]:
                continue
            pos = int(np.searchsorted(c, tick, side="right") - 1)
            pos = min(max(pos, 0), len(sl) - 1)
            sampled.append(iotas[sl[pos]])
    if not sampled:
        return None
    q1, q3 = np.percentile(sampled, [25, 75])
    return round(float(q3 - q1), 4)


def gate_table(order, td_key, calls_key):
    """Compute the full gate table for one variant.  td_key/calls_key select
    the per-turn / per-call-equivalent pools ('td_primary'/'calls_primary' or
    the ablation keys)."""
    per_turn, per_call, sess_td = [], [], []
    iotas = []
    peak = 0
    for s in order:
        td = s[td_key]
        per_turn.extend(td)
        per_call.extend(s[calls_key])
        sess_td.append(td)
        iotas.append(s["iota"])
        peak = max(peak, s["peak_ctx"])
    tmed, tcounts = transitions_median(sess_td)
    q1, q3 = np.percentile(iotas, [25, 75])
    return {
        "per_turn_tool_duration_s": dist(per_turn),
        "per_call_equivalent": dist(per_call),
        "ks_vs_paper_cdf_percall": ks_vs_paper(per_call),
        "transition_median": tmed,
        "transition_mean": round(float(np.mean(tcounts)), 3) if tcounts else 0.0,
        "peak_context_max": int(peak),
        "session_iota_iqr": round(float(q3 - q1), 4),
        "concurrent_iota_iqr_sim": concurrent_iota_iqr(order),
        "n_sessions": len(order),
        "n_turns": len(per_turn),
    }


def build_gate_summary(gt, blend):
    """Human-readable achieved-vs-target rows with residual gaps."""
    pt = gt["per_turn_tool_duration_s"]
    pc = gt["per_call_equivalent"]
    def row(name, achieved, target, unit=""):
        gap = None if (achieved is None or target is None) else round(achieved - target, 4)
        return {"metric": name, "achieved": achieved, "target": target,
                "residual": gap, "unit": unit}
    rows = [
        row("P50 (per-call-equiv)", pc.get("P50"), PAPER["P50"], "s"),
        row("P90 (per-call-equiv)", pc.get("P90"), PAPER["P90"], "s"),
        row("P99 (per-call-equiv)", pc.get("P99"), PAPER["P99"], "s"),
        row("P99.95 (per-call-equiv)", pc.get("P99.95"), PAPER["P99.95"], "s"),
        row("short%@2s (per-call-equiv)", pc.get("short_pct"), PAPER["short_pct"], "%"),
        row("long%@2s (per-call-equiv)", pc.get("long_pct"), PAPER["long_pct"], "%"),
        row("long time-share (per-turn, OPERATIONAL)", pt.get("long_time_share_pct"),
            PAPER["long_time_share_pct"], "%"),
        row("long time-share (per-call-equiv, paper-def)", pc.get("long_time_share_pct"),
            PAPER["long_time_share_pct"], "%"),
        {"metric": "KS distance vs paper CDF (per-call-equiv, approx)",
         "achieved": gt["ks_vs_paper_cdf_percall"], "target": "-> 0", "residual": None, "unit": ""},
        {"metric": "HARD: transition median >= 4", "achieved": gt["transition_median"],
         "target": 4, "residual": round(gt["transition_median"] - 4, 3),
         "pass": gt["transition_median"] >= 4, "unit": "transitions"},
        {"metric": "HARD: peak context <= 64k", "achieved": gt["peak_context_max"],
         "target": L, "residual": gt["peak_context_max"] - L,
         "pass": gt["peak_context_max"] <= L, "unit": "tokens"},
        {"metric": "HARD: iota IQR >= 0.35 (per-session)", "achieved": gt["session_iota_iqr"],
         "target": 0.35, "residual": round(gt["session_iota_iqr"] - 0.35, 4),
         "pass": gt["session_iota_iqr"] >= 0.35, "unit": "",
         "note": "supplementary concurrency-sim IQR = %s (time-domination biased, "
                 "reported for reference only)" % gt["concurrent_iota_iqr_sim"]},
    ]
    return rows


# ---------------------------------------------------------------------------
# emit
# ---------------------------------------------------------------------------
def write_trace(path, order, td_key):
    with open(path, "w", encoding="utf-8") as f:
        for s in order:
            td_vals = s[td_key]
            for i, t in enumerate(s["turns"]):
                rec = {"session_id": t["session_id"], "turn": i,
                       "input_tokens": t["input_tokens"],
                       "output_tokens": t["output_tokens"],
                       "tool_duration_s": td_vals[i],
                       "cached_tokens": t["cached_tokens"]}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp",
                    default="/home/yunuikang/yunuikang_work/scratch/traces/syfi_coding_trace.jsonl.gz")
    ap.add_argument("--track", choices=["P", "M"], default="M",
                    help="M = MORI-mechanism full pool (PRIMARY; passes transition>=4 & "
                         "iota-IQR>=0.35, long-share ~98%%). P = paper-regime 58%% blend "
                         "(trilemma evidence only, SECONDARY, not swept).")
    ap.add_argument("--out-primary", default=None,
                    help="default resolves from --track (M->tracelab_moriM_L64k, P->tracelab_mori_L64k)")
    ap.add_argument("--out-ablation", default=None)
    ap.add_argument("--min-turns", type=int, default=4,
                    help="exclude sessions shorter than this from the blend pool "
                         "(degenerate 1-2 turn sessions carry no transitions). "
                         "min_turns=4 is the knee: largest sample + iota-IQR while "
                         "keeping transition median at its ceiling of 2 (see "
                         "gate_tradeoff_min_turns_sweep in meta).")
    ap.add_argument("--tol", type=float, default=0.01,
                    help="tolerance band (fraction) around 58%% within which the "
                         "blend maximizes transition-median / iota-IQR")
    ap.add_argument("--sweep-min-turns", default="",
                    help="comma list: only PROBE blend gates for these min_turns "
                         "values (no files written), then exit")
    args = ap.parse_args()
    _base = "/home/yunuikang/yunuikang_work/scratch/traces/"
    _stem = "tracelab_moriM_L64k" if args.track == "M" else "tracelab_mori_L64k"
    if args.out_primary is None:
        args.out_primary = f"{_base}{_stem}_yunuikang.jsonl"
    if args.out_ablation is None:
        args.out_ablation = f"{_base}{_stem}_nohw_yunuikang.jsonl"

    print(f"[0] track={args.track}  out={args.out_primary}", flush=True)
    print("[1] loading gz (read-only) ...", flush=True)
    sessions, n_rows, n_nonpos = load_sessions(args.inp)
    print(f"    rows={n_rows} nonpositive_dropped={n_nonpos} sessions={len(sessions)}", flush=True)

    print("[2] turn-window slicing (L=64k, rebase SEED=4096) + build ...", flush=True)
    sess = []
    n_hw_inj = n_hw_excl = 0
    for sid, rounds in sessions.items():
        rounds.sort(key=lambda r: r["round_index"])
        s = build_session(sid, rounds)
        if s is None or not s["turns"]:
            continue
        n_hw_inj += s["n_hw_inj"]
        n_hw_excl += s["n_hw_excl"]
        sess.append(s)
    print(f"    windowed sessions={len(sess)}  human-wait injected turns={n_hw_inj} "
          f"excluded(>=12h)={n_hw_excl}", flush=True)

    if args.sweep_min_turns:
        print("[probe] min_turns sweep (no files written):", flush=True)
        for mt in (int(x) for x in args.sweep_min_turns.split(",")):
            _, sel, rep = choose_blend(sess, tol=args.tol, min_turns=mt)
            gt = gate_table(interleave(sel), "td_primary", "calls_primary")
            print(f"  min_turns={mt:3d} sel={len(sel):4d} "
                  f"long_share={rep['achieved_aggregate_long_time_share_pct']:.2f}% "
                  f"trans_median={gt['transition_median']:.1f} trans_mean={gt['transition_mean']:.1f} "
                  f"iota_iqr={gt['session_iota_iqr']:.3f} "
                  f"blend={rep['blend_ratio_busy_mixed_idle']} "
                  f"excl_short={rep['sessions_excluded_lt_min_turns']}")
        return

    if args.track == "M":
        print("[3] Track M: full >=min_turns pool (no blend; PRIMARY) ...", flush=True)
        sel_sids, selected, blend = select_pool(sess, min_turns=args.min_turns)
    else:
        print("[3] Track P: blend -> approach 58% (trilemma evidence; SECONDARY) ...", flush=True)
        sel_sids, selected, blend = choose_blend(sess, tol=args.tol, min_turns=args.min_turns)
    print("    selection:", json.dumps(blend), flush=True)

    # ---- original (pre-blend) all-windowed-sessions distribution (transparency) ----
    all_order = interleave(sess)
    orig_gt = gate_table(all_order, "td_primary", "calls_primary")

    # ---- min_turns tradeoff sweep (documents the 58% / transition / iota trilemma) ----
    print("[3b] min_turns tradeoff sweep (transparency) ...", flush=True)
    tradeoff = []
    for mt in (2, 4, 6, 15, 25, 40):
        _, sel_mt, rep_mt = choose_blend(sess, tol=args.tol, min_turns=mt)
        gmt = gate_table(interleave(sel_mt), "td_primary", "calls_primary")
        tradeoff.append({
            "min_turns": mt, "n_sessions": len(sel_mt),
            "long_time_share_pct": rep_mt["achieved_aggregate_long_time_share_pct"],
            "transition_median": gmt["transition_median"],
            "transition_mean": gmt["transition_mean"],
            "session_iota_iqr": gmt["session_iota_iqr"],
            "blend_ratio_busy_mixed_idle": rep_mt["blend_ratio_busy_mixed_idle"],
        })

    print("[4] interleave by iota-tercile + gates ...", flush=True)
    order = interleave(selected)
    gt_primary = gate_table(order, "td_primary", "calls_primary")
    gt_ablation = gate_table(order, "td_ablation", "calls_ablation")

    # ---- write NEW output files only ----
    write_trace(args.out_primary, order, "td_primary")
    write_trace(args.out_ablation, order, "td_ablation")

    if args.track == "M":
        note = ("Track M (MORI-mechanism, PRIMARY). Turn-window sliced to L=64k (context "
                "rebased to SEED=4096, NOT prefix truncation), human-wait injected into "
                "tool_duration_s (primary; ablation omits it on the SAME sessions), all "
                "durations clamped to 300s, human gaps >=12h excluded. The FULL "
                ">=min_turns windowed pool is kept with NO 58% blend and interleaved by "
                "iota-tercile: it passes the hard gates (transition-median>=4, "
                "per-session iota-IQR>=0.35, peak<=64k). long-time-share is idle-heavy "
                "(~98%) BY DESIGN; the paper's 58% is an emergent property of its agent "
                "(1.1s median tool call) not reproducible with ours (0.24s) - see "
                "gate_tradeoff_min_turns_sweep for the trilemma. No short-call "
                "fabrication anywhere.")
    else:
        note = ("Track P (paper-regime 58% blend, SECONDARY / trilemma evidence only - "
                "NOT an experiment arm). CONSTRUCTED subset: turn-window sliced to L=64k "
                "(rebased SEED=4096), human-wait injected, clamped 300s, gaps >=12h "
                "excluded, then a busy+idle blend selected to hit aggregate per-turn "
                "long(>2s) time-share ~58%. Forcing 58% collapses per-session iota-IQR "
                "from ~0.69 (pool) to ~0.26 and transition-median from 4 to 2 - the "
                "trilemma. Kept only to document that 58% is unreproducible without "
                "sacrificing MORI's idleness-ranking signal. Short calls never "
                "fabricated.")

    if args.track == "M":
        tension_note = (
            "TRILEMMA (PLAN §C-4b): 58%-long-share, transition-median>=4, and "
            "iota-IQR>=0.35 cannot co-hold on this data. Track M takes the full pool "
            "(no 58% blend) and therefore PASSES transition-median>=4 and "
            "iota-IQR>=0.35, at the cost of long-share ~98% (58% abandoned as an "
            "emergent property of the paper's 1.1s-median agent, unreproducible with "
            "our 0.24s calls). gate_tradeoff_min_turns_sweep shows the 58%-blend arm "
            "that collapses these gates (transition 2, iota-IQR ~0.26).")
    else:
        tension_note = (
            "TRILEMMA (PLAN §C-4b): forcing 58% (this Track P) collapses "
            "transition-median 4->2 and per-session iota-IQR ~0.69->~0.26. That is why "
            "Track P is NOT an experiment arm; the primary is Track M (full pool).")

    for path, gt, variant in ((args.out_primary, gt_primary, "primary (human-wait injected)"),
                              (args.out_ablation, gt_ablation, "ablation (no human-wait; same subset)")):
        meta = {
            "constructed": True,
            "variant": variant,
            "source": args.inp,
            "note": note,
            "params": {"SEED": SEED, "L": L, "CAP_HARD_s": CAP_HARD,
                       "human_wait_exclude_s": HW_EXCLUDE_S, "long_threshold_s": LONG_THRESH,
                       "target_long_time_share_pct": PAPER["long_time_share_pct"],
                       "reasoning_proxy": "uncached/8000 + output/145"},
            "paper_target": PAPER,
            "blend": blend,
            "human_wait": {"injected_turns_windowed_total": n_hw_inj,
                           "excluded_ge_12h_windowed_total": n_hw_excl,
                           "note": "ablation variant sets human-wait contribution to 0"},
            "gate_table": build_gate_summary(gt, blend),
            "gates_raw": gt,
            "structural_tension_note": tension_note,
            "gate_tradeoff_min_turns_sweep": tradeoff,
            "distribution_original_pre_reshape": {
                "all_windowed_sessions_no_blend": orig_gt,
                "note": ("distribution over ALL turn-windowed sessions BEFORE blend "
                         "selection (primary, human-wait injected); shows the pre-blend "
                         "regime the blend corrects toward 58%."),
            },
            "schema": ["session_id", "turn", "input_tokens", "output_tokens",
                       "tool_duration_s", "cached_tokens"],
        }
        with open(path.rsplit(".", 1)[0] + ".meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

    # ---- console report ----
    def show(tag, gt):
        print(f"\n===== {tag} =====")
        for r in build_gate_summary(gt, blend):
            extra = ""
            if "pass" in r:
                extra = "  [PASS]" if r["pass"] else "  [FAIL]"
            if "note" in r:
                extra += "  (" + r["note"] + ")"
            print(f"  {r['metric']:52} achieved={r['achieved']}  target={r['target']}"
                  f"  residual={r['residual']}{extra}")

    print("\n########## RESULTS ##########")
    print(f"source: {args.inp}")
    print(f"windowed sessions total: {len(sess)}  ->  selected (primary/ablation): {len(order)}")
    print("blend:", json.dumps(blend, indent=2))
    print("\n--- ORIGINAL (pre-reshape) all-windowed-sessions, human-wait injected ---")
    ot, oc = orig_gt["per_turn_tool_duration_s"], orig_gt["per_call_equivalent"]
    print(f"  per-turn:  {json.dumps(ot)}")
    print(f"  per-call:  {json.dumps(oc)}")
    show("PRIMARY (human-wait injected)", gt_primary)
    show("ABLATION (no human-wait; same subset)", gt_ablation)
    print("\noutputs:")
    print(f"  {args.out_primary}")
    print(f"  {args.out_ablation}")
    print("  + .meta.json sidecars (constructed=true, gate table, blend ratio, original dist)")


if __name__ == "__main__":
    main()
