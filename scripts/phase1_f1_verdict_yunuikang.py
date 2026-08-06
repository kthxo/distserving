#!/usr/bin/env python3
"""§7.1c branch decision after the F1 pair — PRE-REGISTERED, see
logs/2026-08-05_H200_GATE_PREREG_yunuikang.md §10.3 (committed before the first cell ran).

Threshold 0.60 is NOT invented here: it is plan §6.3 main-judgement condition 1
("F1이 5090 붕괴를 재현 — MORI÷TA+O ≤ 0.6×"). The 5090 C80 anchor is 0.45x.
What §10.2 pre-registers is WHICH instruments measure it:

  primary      driver output_throughput_tok_s ratio  (same instrument as the 0.45x anchor —
                                                      a reproduction claim needs the same
                                                      instrument on both sides)
  corroborant  engine steady-window tok/s ratio      (§5.3 unbiased; the driver metric is
                                                      biased against MORI — 5090 measured
                                                      0.57x driver vs 0.86x engine on one cell)

  REPRODUCED      both <= 0.60   -> continue to F2..F4
  NOT_REPRODUCED  both >  0.60   -> stop (plan §6.3 fourth branch)
  DISAGREE        exactly one    -> stop; the foundation is ambiguous, a human decides
  INVALID         a cell missing -> stop

Exit code 0 = REPRODUCED (caller continues), 1 = anything else (caller stops).
"""
import argparse
import json
import os
import sys
import time

THRESHOLD = 0.60          # plan §6.3 condition 1 — pre-registered, not tunable here
ANCHOR_5090 = 0.45        # measured, logs/2026-08-04_MORI_VERIFICATION_yunuikang.md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary-json", required=True)
    ap.add_argument("--progress", required=True)
    ap.add_argument("--fit-label", default="F1")
    ap.add_argument("--mode", default="sweep", choices=["sweep", "model-confound"],
                    help="sweep: rev3 fit 스윕 분기 / model-confound: rev4 8B 재실행 분기. "
                         "수치 규칙(0.60·두 지표·4상태)은 동일하고 해석문만 다르다")
    args = ap.parse_args()

    cells = {}
    if os.path.exists(args.summary_json):
        for line in open(args.summary_json, errors="replace"):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("fit_label") == args.fit_label:
                cells[d.get("system")] = d

    mori, tao = cells.get("MORI"), cells.get("TAO")
    lines, verdict, reason = [], None, ""

    if not mori or not tao or mori.get("status") != "OK" or tao.get("status") != "OK":
        verdict = "INVALID"
        reason = (f"F1 셀 누락/실패 — MORI={'없음' if not mori else mori.get('status')}, "
                  f"TAO={'없음' if not tao else tao.get('status')}")
    else:
        rd = mori.get("ratio_driver_mori_over_tao")
        re_ = mori.get("ratio_engine_mori_over_tao")
        if rd is None or re_ is None:
            verdict = "INVALID"
            reason = (f"비율 계산 불가 — driver={rd}, engine={re_} "
                      f"(engine_note: MORI '{mori.get('engine_note')}' / TAO '{tao.get('engine_note')}')")
        else:
            p, c = rd <= THRESHOLD, re_ <= THRESHOLD
            if p and c:
                verdict, reason = "REPRODUCED", "주·부 지표 모두 임계값 이하 — 5090 붕괴 재현"
            elif not p and not c:
                verdict, reason = "NOT_REPRODUCED", "주·부 지표 모두 임계값 초과 — 붕괴가 재현되지 않음"
            else:
                verdict = "DISAGREE"
                reason = (f"주지표 {'통과' if p else '미통과'} / 부지표 {'통과' if c else '미통과'} "
                          f"— 재현 주장의 토대가 모호")

    lines.append("")
    lines.append(f"## ★ §7.1c 분기 판정 — {args.fit_label} ({time.strftime('%Y-%m-%d %H:%M:%S')})")
    lines.append("")
    lines.append(f"- 사전 등록: PREREG §10.3 · 임계값 **{THRESHOLD:.2f}** (계획 §6.3 조건 1) · "
                 f"5090 C80 앵커 **{ANCHOR_5090:.2f}×**")
    if mori and tao:
        lines.append(f"- 드라이버 thr: MORI {mori.get('driver_thr_tok_s')} / "
                     f"TAO {tao.get('driver_thr_tok_s')}")
        lines.append(f"- 엔진 steady thr: MORI {mori.get('engine_thr_tok_s')} / "
                     f"TAO {tao.get('engine_thr_tok_s')}")
        rd, re_ = mori.get("ratio_driver_mori_over_tao"), mori.get("ratio_engine_mori_over_tao")
        lines.append(f"- **주지표 MORI÷TA+O (드라이버) = "
                     f"{'n/a' if rd is None else f'{rd:.3f}'}** "
                     f"({'≤' if rd is not None and rd <= THRESHOLD else '>'} {THRESHOLD:.2f})")
        for k, lab in (("ttft_p50_s", "TTFT p50"), ("ttft_p95_s", "TTFT p95")):
            a, b = mori.get(k), tao.get(k)
            r = (a / b) if (a and b) else None
            lines.append(f"- {lab}: MORI {a} / TAO {b} → 비 "
                         f"{'n/a' if r is None else f'{r:.2f}x'} (기록 항목, 판정 아님)")
        lines.append(f"- **부지표 MORI÷TA+O (엔진) = "
                     f"{'n/a' if re_ is None else f'{re_:.3f}'}** "
                     f"({'≤' if re_ is not None and re_ <= THRESHOLD else '>'} {THRESHOLD:.2f})")
    lines.append("")
    lines.append(f"### 판정: **{verdict}** — {reason}")
    lines.append("")
    if args.mode == "model-confound":
        # rev4 §5.1 — 모델을 5090에 맞췄으므로 남는 차이는 interconnect/TP 하나다.
        if verdict == "REPRODUCED":
            lines.append("→ **원인은 ④ 모델/KV밀도다.** 8B에서 붕괴가 재현됐다 — 7B가 이겼던 것은 "
                         "KV가 가벼워(56 vs 144 KiB/tok) 같은 fit에서도 압박이 덜했기 때문으로 "
                         "설명된다. 진짜 축은 fit이 아니라 **KV밀도**다. (계획 §0.6 후보 ④ 확정)")
        elif verdict == "NOT_REPRODUCED":
            lines.append("→ **원인은 ③ interconnect/TP다.** 모델·KV밀도·셀길이를 5090에 맞췄는데도 "
                         "붕괴가 재현되지 않았다 → 남는 차이는 TP2/SYS/cross-NUMA뿐이다. "
                         "(계획 §0.6 후보 ③ 확정 · 5090에서 TP1로 재확인하면 닫힌다)")
        elif verdict == "DISAGREE":
            lines.append("→ **판단 보류.** 두 계측기가 갈렸다. 어느 쪽을 믿을지는 사전 등록이 "
                         "정하지 않았고, 결과를 보고 정하면 사후 선택이 된다.")
        else:
            lines.append("→ **중단.** 셀이 온전하지 않아 판정 불가. 로그를 확인할 것.")
        lines.append("")
        lines.append("**어느 경우든 Phase 1은 여기서 끝난다** — rev4의 Phase 1은 이 2셀이 전부다. "
                     "다음은 Phase 2(7B, C 스윕)이며 사람이 결정한다.")
    elif verdict == "REPRODUCED":
        lines.append("→ F2 · F3 · F4로 **자동 진행**. 하드웨어 교란요인이 닫혔으므로 fit 스윕의 "
                     "상승분을 fit에 귀속할 수 있다.")
    elif verdict == "NOT_REPRODUCED":
        lines.append("→ **중단.** 계획 §6.3 네 번째 분기: 5090 붕괴가 fit 탓이 아니었을 수 있다. "
                     "남는 후보는 dial③(interconnect·NUMA)과 TP2다. "
                     "F2~F4를 돌려도 상승분을 fit에 귀속할 수 없으므로 예산을 쓰지 않는다.")
    elif verdict == "DISAGREE":
        lines.append("→ **중단.** 두 계측기가 갈렸다. 어느 쪽을 믿을지는 사전 등록이 정하지 않았고 "
                     "결과를 보고 정하면 사후 선택이 된다. 아침에 사람이 판단한다. "
                     "(참고: 5090에서도 같은 셀이 드라이버 0.57× vs 엔진 0.86×로 갈린 전력이 있다.)")
    else:
        lines.append("→ **중단.** F1 셀이 온전하지 않아 판정 자체가 불가능하다. "
                     "셀 로그(`serve_*.log`, `err_*.log`, `proxy_*.log`)를 확인할 것.")
    lines.append("")

    text = "\n".join(lines)
    with open(args.progress, "a") as f:
        f.write(text + "\n")
    print(text)
    sys.exit(0 if verdict == "REPRODUCED" else 1)


if __name__ == "__main__":
    main()
