#!/usr/bin/env python3
"""H200 Phase 2 — P1~P4 판정 (논문 곡선 재현).

**판정식은 계획 §6.4 원문 그대로다. 이 스크립트는 그것을 계산할 뿐 새로 만들지 않는다.**
계측기만 PREREG §E 에서 확정했다: goodput = 점추정(프록시 --profile per-step,
TTFT = pause_s + prefill_s, 고정 steady 창).

계획 §6.4 (rev3, 사전 등록):
  P1  저 동시성 동률   — C=20 에서 4종 최대·최소 차 <= 5%
  P2  고 동시성 우위   — C=80 에서 goodput 비 >= 1.10x, TTFT p50 -10% 이상
  P3  MORI 단조 비감소 — MORI goodput 이 C 20->40->80 에서 하락 폭 < run 변동 15%
  P4  TA+O 비단조/붕괴 — TA+O goodput 이 C=80 에서 C=40 대비 하락, 또는 MORI 대비 격차 확대

주 판정: P1~P4 모두 만족 -> "논문 곡선 재현 성공".
부분 재현 분기도 §6.4 표 그대로 출력한다.
"""
import argparse
import json
import os
import sys
import time

P1_SPREAD = 0.05      # §6.4 P1
P2_RATIO = 1.10       # §6.4 P2
P2_TTFT_GAIN = 0.10   # §6.4 P2 — MORI p50 <= (1-0.10) x TAO p50
P3_DROP = 0.15        # §6.4 P3 — run 변동 15%
SYS = ["SMG", "TA", "TAO", "MORI"]


def load(path):
    cells = {}
    if not os.path.exists(path):
        return cells
    for line in open(path, errors="replace"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("status") == "OK":
            cells[(d.get("system"), d.get("fit_label"))] = d   # 나중 것이 이긴다
    return cells


def g(cells, s, c):
    d = cells.get((s, f"C{c}"))
    return None if not d else d.get("goodput_5s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary-json", required=True)
    ap.add_argument("--progress", required=True)
    ap.add_argument("--partial", action="store_true", help="중간 갱신 — 결측은 '미측정'으로 두고 판정 보류")
    args = ap.parse_args()

    cells = load(args.summary_json)
    L, verdicts = [], {}

    L.append("")
    L.append(f"## {'중간 현황' if args.partial else '★ P1~P4 판정'} "
             f"— H200 Phase 2 ({time.strftime('%Y-%m-%d %H:%M:%S')})")
    L.append("")
    L.append("판정식은 **계획 §6.4 원문**. 계측기는 PREREG §E (점추정 goodput@5s).")
    L.append("")
    L.append("| goodput@5s (tok/s) | C=20 | C=40 | C=80 |")
    L.append("|---|---|---|---|")
    for s in SYS:
        row = [g(cells, s, c) for c in (20, 40, 80)]
        L.append(f"| {s} | " + " | ".join("–" if v is None else f"{v:.2f}" for v in row) + " |")
    L.append("")

    # ---- P1: C=20 에서 4종 최대·최소 차 <= 5% ----
    v20 = {s: g(cells, s, 20) for s in SYS}
    if all(v is not None for v in v20.values()):
        hi, lo = max(v20.values()), min(v20.values())
        spread = (hi - lo) / hi if hi else float("inf")
        verdicts["P1"] = spread <= P1_SPREAD
        L.append(f"- **P1** (저 C 동률, ≤{P1_SPREAD:.0%}): 최대 {hi:.2f} / 최소 {lo:.2f} → "
                 f"차 **{spread:.1%}** → {'✅ 성립' if verdicts['P1'] else '❌ 불성립'}")
        # 진단 기록 (PREREG §E.8) — 판정 아님. P1 실패 시 원인이 SMG 인지 프로토콜인지 가른다.
        v3 = {k: v for k, v in v20.items() if k != "SMG"}
        hi3, lo3 = max(v3.values()), min(v3.values())
        sp3 = (hi3 - lo3) / hi3 if hi3 else float("inf")
        L.append(f"  - (기록·판정 아님) SMG 제외 3종 spread = **{sp3:.1%}** — "
                 f"{'4종만 갈린다 → 원인은 SMG 구조적 약세, 프로토콜 아님' if (spread > P1_SPREAD and sp3 <= P1_SPREAD) else '3종도 갈린다 → §6.4대로 프로토콜·트레이스 의심'} (§E.8)")
    else:
        L.append("- **P1**: C=20 미완 — 판정 보류")

    # ---- P2: C=80 에서 goodput 비 >= 1.10 AND TTFT p50 -10% 이상 ----
    m80, t80 = g(cells, "MORI", 80), g(cells, "TAO", 80)
    dm, dt = cells.get(("MORI", "C80")), cells.get(("TAO", "C80"))
    if m80 and t80 and dm and dt:
        ratio = m80 / t80
        p50m, p50t = dm.get("ttft_p50_s"), dt.get("ttft_p50_s")
        ttft_ok = (p50m is not None and p50t and p50m <= (1 - P2_TTFT_GAIN) * p50t)
        verdicts["P2"] = (ratio >= P2_RATIO) and ttft_ok
        L.append(f"- **P2** (고 C 우위, 비≥{P2_RATIO} **그리고** TTFT p50 −{P2_TTFT_GAIN:.0%} 이상): "
                 f"goodput 비 **{ratio:.3f}** ({'✅' if ratio >= P2_RATIO else '❌'}) · "
                 f"TTFT p50 MORI {p50m} vs TAO {p50t} ({'✅' if ttft_ok else '❌'}) → "
                 f"{'✅ 성립' if verdicts['P2'] else '❌ 불성립'}")
    else:
        L.append("- **P2**: C=80 미완 — 판정 보류")

    # ---- P3: MORI goodput 이 C 20->40->80 에서 하락 폭 < 15% ----
    mm = [g(cells, "MORI", c) for c in (20, 40, 80)]
    if all(v is not None for v in mm):
        drops = [(mm[i] - mm[i + 1]) / mm[i] for i in range(2)]
        verdicts["P3"] = all(d < P3_DROP for d in drops)
        L.append(f"- **P3** (MORI 단조 비감소, 하락 < {P3_DROP:.0%}): "
                 f"20→40 **{drops[0]:+.1%}** · 40→80 **{drops[1]:+.1%}** → "
                 f"{'✅ 성립' if verdicts['P3'] else '❌ 불성립'} (양수 = 하락)")
    else:
        L.append("- **P3**: MORI 3점 미완 — 판정 보류")

    # ---- P4: TA+O 가 C80 에서 C40 대비 하락, 또는 MORI 대비 격차 확대 ----
    t40, t80b, m40 = g(cells, "TAO", 40), g(cells, "TAO", 80), g(cells, "MORI", 40)
    if t40 and t80b and m40 and m80:
        declined = t80b < t40
        gap40, gap80 = (m40 - t40) / t40, (m80 - t80b) / t80b
        widened = gap80 > gap40
        verdicts["P4"] = declined or widened
        L.append(f"- **P4** (TA+O 비단조/붕괴): C40 {t40:.2f} → C80 {t80b:.2f} "
                 f"({'하락 ✅' if declined else '하락 아님'}) · "
                 f"MORI 대비 격차 {gap40:+.1%} → {gap80:+.1%} "
                 f"({'확대 ✅' if widened else '확대 아님'}) → "
                 f"{'✅ 성립' if verdicts['P4'] else '❌ 불성립'}")
    else:
        L.append("- **P4**: C40/C80 미완 — 판정 보류")

    L.append("")
    if len(verdicts) < 4:
        L.append(f"### 판정 보류 — {len(verdicts)}/4 명제만 계산 가능 (미완 셀 존재)")
    else:
        allp = all(verdicts.values())
        L.append(f"### 주 판정: **{'논문 곡선 재현 성공' if allp else '부분 재현/미재현'}** "
                 f"— P1 {'✅' if verdicts['P1'] else '❌'} · P2 {'✅' if verdicts['P2'] else '❌'} · "
                 f"P3 {'✅' if verdicts['P3'] else '❌'} · P4 {'✅' if verdicts['P4'] else '❌'}")
        L.append("")
        # §6.4 부분 재현 분기 (원문)
        if allp:
            L.append("→ **완전 재현.** 논문 대조표 작성. `r=1` 축으로 견고성 확인 (§6.4).")
        elif verdicts["P2"] and not verdicts["P3"]:
            L.append("→ **부분 재현.** MORI 가 이기긴 하나 *스케일링*은 재현 안 됨 → "
                     "하락 원인을 `--profile` 로 분해 (§6.4).")
        elif not verdicts["P2"]:
            L.append("→ **미재현.** fit20 이 아직 부족한 레짐일 수 있음 → "
                     "F5(fit26) 셀로 oversub 3.08× 까지 밀어 본다 (§6.4).")
        elif not verdicts["P1"]:
            L.append("→ **교란.** 저 C 는 압박이 없어 갈릴 이유가 없다. "
                     "프로토콜·트레이스 쪽 문제 의심 → Phase 0 재점검 (§6.4).")
        else:
            L.append("→ §6.4 분기표에 정확히 대응하는 항목 없음 — 사람이 판단할 것.")
    L.append("")

    text = "\n".join(L)
    with open(args.progress, "a") as f:
        f.write(text + "\n")
    print(text)
    sys.exit(0)


if __name__ == "__main__":
    main()
