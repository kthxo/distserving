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
        lines.append(f"- **부지표 MORI÷TA+O (엔진) = "
                     f"{'n/a' if re_ is None else f'{re_:.3f}'}** "
                     f"({'≤' if re_ is not None and re_ <= THRESHOLD else '>'} {THRESHOLD:.2f})")
    lines.append("")
    lines.append(f"### 판정: **{verdict}** — {reason}")
    lines.append("")
    if verdict == "REPRODUCED":
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
