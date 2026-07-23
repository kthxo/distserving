# -*- coding: utf-8 -*-
"""Full-study deck builder — part 1 (slides 1–10). Numbers are verbatim from logs."""
import sys
sys.path.insert(0, "/home/yunuikang/yunuikang_work/distserving/scripts")
import decklib_yunuikang as D
from decklib_yunuikang import (INK, BLUE, RED, GREEN, GRAY, LT, AMBER, WHITE,
                               RGBColor)
from pptx.enum.text import PP_ALIGN

prs = D.new_deck()
HL = RGBColor(0xFF, 0xF3, 0xD6)   # amber row highlight
WIN = RGBColor(0xDF, 0xEE, 0xE4)  # green row (tr win)
LOSE = RGBColor(0xF7, 0xDD, 0xD8) # red row (tr lose)


# ---------------------------------------------------------------- slide 1
s = D._blank(prs)
D.band(s, 0, 0.16, BLUE)
D.band(s, 7.34, 0.16, BLUE)
D.add_text(s, "언제 프로그램-인지 스케줄러(ThunderAgent)가 이기고, 언제 지는가",
           0.8, 2.35, 11.7, 1.2, size=30, color=INK, bold=True)
D.add_text(s, "Agentic LLM 서빙의 tr(program-aware) vs default(vLLM) — fit×d 레짐으로 승패를 예측하고,\n"
              "미포화 구간의 idle↔recompute 상충을 두 레버(overcommit·duty)로 해부하다",
           0.8, 3.75, 11.7, 1.2, size=15, color=BLUE)
D.chip(s, "P1  스케일 재현", 0.8, 5.5, 2.7, INK)
D.chip(s, "레짐 모델  overcommit×duty", 3.7, 5.5, 3.7, BLUE)
D.chip(s, "4 워크로드  SWE·TraceLab·HLE·Science", 7.6, 5.5, 5.0, GREEN)
D.add_text(s, "강윤의 · 2026-07-21 · nutella1 / Pro6000·4090·(합성 5090)",
           0.8, 6.7, 11.7, 0.4, size=12, color=GRAY)
D.set_notes(s,
"안녕하세요, 강윤의입니다. 오늘 발표는 세 덩어리의 연구를 하나의 이야기로 잇는 자리입니다. "
"첫째는 P1 — 논문의 서빙 평가를 Pro6000 장비로 축소 재현해, ThunderAgent의 프로그램-인지 라우터(이하 tr)가 "
"vLLM 기본(default)을 언제 이기고 언제 지는지 실측한 부분입니다. 둘째는 그 승패를 하나의 수 fit×d로 예측하는 "
"레짐 모델, 그리고 tr이 지는 '미포화' 구간에서 GPU를 놀리지 않으려면 어떻게 해야 하는지를 두 개의 레버 — "
"overcommit(캐시를 초과 적재)과 duty(추론:도구 비율) — 로 해부한 부분입니다. 셋째는 이 모델을 네 개의 실제 "
"워크로드(SWE-bench, TraceLab, HLE, ScienceAgentBench)로 교차검증한 부분입니다. "
"핵심 주장 한 줄은 이렇습니다: 'tr의 승패는 fit×d라는 한 수로 예측되고, 그 경계는 1이 아니라 0.62 — "
"즉 GPU를 놀리는 비용과 캐시를 다시 계산하는 비용이 균형을 이루는 지점 — 이며, tr(SOTA)은 이 레짐을 모르기 "
"때문에 미포화에서 느리고 불안정하다'는 것입니다. 지금부터 왜 이 질문이 나왔는지부터 순서대로 보여드리겠습니다.")


# ---------------------------------------------------------------- slide 2
s = D._blank(prs)
D.band(s, 0, 0.14, BLUE)
D.add_title(s, "배경 — Agentic 서빙과 KV thrashing, 그리고 퍼즐")
D.add_text(s, "배경", 0.42, 1.02, 6.0, 0.3, size=12.5, color=GRAY, bold=True)
D.add_takeaway(s, "SOTA인 tr(ThunderAgent)이 어떤 워크로드·하드웨어에선 default(vLLM)에게 진다 — 왜?", y=1.32)
# left: mechanism boxes
D.add_text(s, "Agentic 프로그램 = reasoning(디코드) ↔ tool(외부호출) 루프.\n"
              "턴마다 KV 컨텍스트가 누적 → 프로그램당 KV 점유가 커진다.",
           0.5, 2.0, 6.0, 1.0, size=12.5, color=INK)
items = [
 ("default (vLLM): 모든 요청을 GPU에 밀어넣음 → 프로그램 수 × 컨텍스트 > KV 풀이면 "
  "축출·재프리필(thrashing) → hit 붕괴·재계산 낭비", 0, RED, False),
 ("tr (ThunderAgent): 용량 부등식(Eq.6)으로 초과분을 pause/resume(f(t)=2^-t 감쇠) → "
  "resident 집합을 KV 풀 안(k_fit ≤ fit)으로 유지 → 캐시 보존", 0, BLUE, False),
]
D.add_bullets(s, items, 0.5, 3.05, 6.2, 2.4, size=12.5, gap=10)
# right: puzzle box
b = s.shapes.add_textbox(D.Inches(7.0), D.Inches(2.25), D.Inches(5.9), D.Inches(4.6))
tf = b.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = "퍼즐"
p.runs[0].font.size = D.Pt(15); p.runs[0].font.bold = True; p.runs[0].font.color.rgb = GREEN
for line, col in [
  ("논문은 tr이 default보다 빠르다고 주장(SOTA).", INK),
  ("그런데 우리 4090 실측: TraceLab에서 tr이 −34%로 졌다.", RED),
  ("같은 tr이 Pro6000에선 +80~87%로 이겼다.", BLUE),
  ("→ 승패가 '워크로드 × 하드웨어'에 따라 뒤집힌다.", INK),
  ("→ 무엇이 이 뒤집힘을 결정하는가? (이 발표의 출발 질문)", GREEN),
]:
    q = tf.add_paragraph(); q.text = "•  " + line; q.space_after = D.Pt(9)
    q.runs[0].font.size = D.Pt(13); q.runs[0].font.color.rgb = col
    q.runs[0].font.bold = (col == GREEN)
D.set_notes(s,
"이 발표가 답하려는 질문이 어디서 나왔는지부터 말씀드립니다. Agentic 프로그램은 모델이 생각하고(reasoning=디코드) "
"도구를 부르는(tool) 루프를 여러 턴 반복합니다. 턴이 쌓일수록 그 프로그램의 KV 캐시 컨텍스트가 누적돼, "
"프로그램 하나가 GPU KV 메모리를 점점 크게 차지합니다. 여기서 두 정책이 갈립니다. vLLM 기본(default)은 들어온 "
"요청을 전부 GPU에 올립니다. 동시 프로그램 수 곱하기 컨텍스트가 KV 풀보다 커지면, 자리가 없어 이미 계산해둔 "
"캐시를 내쫓고 다음 턴에 다시 계산합니다. 이게 KV thrashing이고, 캐시 적중률(hit)이 무너지며 재프리필 낭비가 "
"생깁니다. 반대로 ThunderAgent(tr)는 용량 부등식으로 초과분을 잠시 멈췄다(pause) 다시 올립니다(resume). "
"f(t)=2의 -t승으로 감쇠하는 스케줄로요. 그래서 GPU에 상주하는 프로그램 집합을 KV 풀 안(k_fit이 fit 이하)으로 "
"유지해 캐시를 지킵니다. 논문은 이 tr이 SOTA로 더 빠르다고 합니다. 그런데 저희가 4090에서 TraceLab을 돌리니 "
"tr이 오히려 34% 느렸고, 같은 tr이 Pro6000에선 80~87% 빨랐습니다. 승패가 워크로드와 하드웨어에 따라 뒤집힌 "
"겁니다. 무엇이 이 뒤집힘을 결정하는가 — 이것이 오늘의 출발 질문입니다.")


# ---------------------------------------------------------------- slide 3
s = D._blank(prs)
D.band(s, 0, 0.14, BLUE)
D.add_title(s, "R 모델 — 'GPU를 동시에 원하는 프로그램 수' = k_fit × d")
D.add_text(s, "레짐 모델의 기초", 0.42, 1.02, 6.0, 0.3, size=12.5, color=GRAY, bold=True)
D.add_takeaway(s, "tr이 지는 조건 = 미포화(R < 1). 변수는 duty(d)·fit(=KV/입력)·GPU. — 현실에서 진짜 발생하나?")
# formula hero
D.chip(s, "R  =  k_fit × d   ≈  평균 nrr(동시 실행 요청 수)", 0.6, 1.95, 8.4, GREEN, size=15, h=0.55)
items = [
 ("k_fit = 실제 GPU에 상주하는 프로그램 수 (정책이 통제; tr은 fit 이하로 억제)", 0, INK, False),
 ("d = duty = reasoning /(reasoning + tool) = 프로그램이 GPU를 실제로 쓰는 시간 비율 (워크로드 성질)", 0, INK, False),
 ("R = 그 곱 = '한 순간 GPU 일을 동시에 원하는 프로그램 수'의 기댓값", 0, BLUE, True),
 ("U(이용률) ≈ min(R, 1).  R<1이면 물리적으로 다 적재해도 GPU가 논다(미포화).", 0, INK, False),
]
D.add_bullets(s, items, 0.5, 2.75, 6.7, 2.5, size=12, gap=9)
# validation box (right)
D.add_text(s, "프로파일링 검증 (VLLM_PROFILING)", 7.4, 2.75, 5.4, 0.35, size=12.5, color=GREEN, bold=True)
D.add_table(s, [
  ["run", "R=k_fit·d", "실측 mean nrr", "오차"],
  ["default C=4", "0.36", "0.36", "0.00"],
  ["default C=16", "1.20", "1.24", "+0.04"],
  ["tr C=16", "0.31", "0.38", "+0.07"],
  ["default C=32", "2.06", "1.29", "포화*"],
], 7.4, 3.2, 5.5, 2.0, fs=11, hdr_fs=11,
   col_widths=[1.7, 1.3, 1.5, 1.0], highlight_rows={2: WIN})
D.add_text(s, "* R≥1에서 실제 배치는 nrr≈1.44에 물리 상한 → '실측 U가 예측 U를 하회'의 원인.\n"
              "R은 '이용률'이 아니라 'GPU 수요'였다. 이 수요가 1을 넘느냐가 승패의 축.",
           7.4, 5.3, 5.4, 1.2, size=10.5, color=GRAY, align=PP_ALIGN.LEFT)
D.set_notes(s,
"앞의 뒤집힘을 설명하려면 공통의 언어가 필요합니다. 그 언어가 R 모델입니다. R은 k_fit 곱하기 d로 정의합니다. "
"k_fit은 실제로 GPU에 상주하는 프로그램 수인데, 정책이 통제합니다 — tr은 이걸 fit(=KV풀/프로그램입력) 이하로 "
"억제하고, default는 제한 없이 올립니다. d는 duty, 즉 reasoning 시간을 reasoning 더하기 tool 시간으로 나눈 값 "
"— 프로그램이 실제로 GPU를 쓰는 시간의 비율이고, 이건 워크로드의 성질입니다. 둘을 곱한 R은 '한 순간 GPU 일을 "
"동시에 원하는 프로그램 수'의 기댓값입니다. 이용률 U는 대략 min(R,1)이고요. 핵심은 R이 1보다 작으면, 물리적으로 "
"프로그램을 전부 올려도 GPU가 논다는 겁니다 — 이걸 미포화라고 부릅니다. tr이 지는 조건이 바로 이 미포화입니다. "
"오른쪽 표가 이 정의가 말장난이 아님을 보여줍니다. R을 계산한 값과, 프로파일링으로 실측한 평균 동시 실행 요청 수"
"(mean nrr)가 거의 일치합니다 — default C=16에서 예측 1.20 대 실측 1.24. 다만 R이 1을 넘어가면 실제 배치가 "
"1.44 근처에 물리적으로 묶여서 실측 U가 예측을 하회하는데, 이건 뒤에서 heavy-tail 이야기로 다시 나옵니다. "
"정리하면 R은 이용률이 아니라 'GPU 수요'이고, 이 수요가 1을 넘느냐 못 넘느냐가 승패의 축입니다. "
"그럼 미포화(R<1)가 현실에서 진짜 발생하는지, 아니면 4090에서만 생기는 예외인지를 다음 장에서 수치로 따집니다.")


# ---------------------------------------------------------------- slide 4
s = D._blank(prs)
D.band(s, 0, 0.14, BLUE)
D.add_title(s, "수치 계산 — 미포화는 4090 전용인가? (fit×d 격자)")
D.add_text(s, "진짜 문제인가 검증", 0.42, 1.02, 6.0, 0.3, size=12.5, color=GRAY, bold=True)
D.add_takeaway(s, "미포화(fit×d<1)는 4090 전용이 아니다 — 저듀티·긴컨텍스트·작은KV 중 하나만으로 진입")
D.add_text(s, "격자 (7 GPU/모델 × 워크로드, 42행) — 발췌:  fit×d<1 = 트레이드오프 zone",
           0.5, 1.95, 7.5, 0.35, size=12.5, color=INK, bold=True)
D.add_table(s, [
  ["GPU / 모델", "워크로드", "fit×d", "f_sat", "zone"],
  ["4090 / 8B", "TraceLab", "0.46", "2.17", "트레이드오프"],
  ["A100-80G / 32B", "TraceLab (d0.289)", "0.60", "1.67", "트레이드오프"],
  ["H100-80G / 32B", "TraceLab (d0.289)", "0.60", "1.67", "트레이드오프"],
  ["5090 / 8B", "longctx (d0.15)", "0.45", "2.20", "트레이드오프"],
  ["Pro6000×2 / 32B", "deep-research (d0.10)", "0.71", "1.40", "트레이드오프"],
  ["4090·A100·H100", "deep-research (d0.10)", "0.07", "~15", "트레이드오프"],
  ["8×H100 / 235B", "(전 워크로드)", "모두 ≥1", "—", "tr 지배"],
], 0.5, 2.4, 7.6, 3.9, fs=11, hdr_fs=11,
   col_widths=[2.0, 2.2, 1.0, 0.9, 1.5],
   highlight_rows={2: HL, 3: HL})
D.add_figure(s, "fitd_hyperbola_full_yunuikang", 8.3, 2.2, 4.7, 4.2)
D.add_caption(s, "fit×d=1 쌍곡선 + 측정 워크로드(4셀 + Science·HLE). 아래=트레이드오프, 위=tr 지배", 8.3, 6.3, 4.7, size=9)
D.set_notes(s,
"미포화가 4090이라는 약한 소비자 GPU에서만 생기는 예외라면, 이 연구는 지엽적입니다. 그래서 GPU 7종과 여러 "
"워크로드를 곱한 42행짜리 격자로 fit×d를 계산했습니다. fit×d가 1보다 작으면 트레이드오프 zone, 즉 tr이 지는 "
"미포화 영역입니다. 표를 보시면 4090만이 아닙니다. 데이터센터급 A100 80GB와 H100 80GB조차도 32B 모델에 "
"중간 듀티(0.289)의 TraceLab을 올리면 fit×d가 0.60으로 zone 안에 들어옵니다. 5090에 긴 컨텍스트(듀티 0.15)면 "
"0.45, Pro6000 두 장에 deep-research(듀티 0.10)면 0.71 — 전부 1 미만입니다. 공식이 왜 일반적인지 보면, "
"fit×d를 1 아래로 떨어뜨리는 길이 세 가지입니다: 듀티가 낮거나(도구 대기가 김), 컨텍스트가 길거나(프로그램당 "
"KV가 큼), KV 풀이 작거나. 이 중 하나만 세게 밀어도 진입합니다. 오른쪽 쌍곡선 그림이 그 경계를 시각화합니다 — "
"fit×d=1 곡선 아래가 트레이드오프, 위가 tr 지배입니다. 유일하게 8H100에 235B 같은 초대형 구성만 모든 "
"워크로드에서 1 이상이라 안전합니다. 결론은 명확합니다. 미포화는 실재하고, 특정 GPU의 문제가 아니라 "
"'워크로드 × 하드웨어'의 구조적 현상입니다. 그러면 실제 워크로드 네 개는 이 축의 어디에 앉는지를 봐야겠죠.")


# ---------------------------------------------------------------- slide 5
s = D._blank(prs)
D.band(s, 0, 0.14, BLUE)
D.add_title(s, "4 워크로드의 fit×d — 표로 먼저 (승패의 지도)")
D.add_text(s, "실데이터 4종의 좌표", 0.42, 1.02, 6.0, 0.3, size=12.5, color=GRAY, bold=True)
D.add_takeaway(s, "TraceLab만 fit×d<1(미포화)에서 tr 패, 나머지 셋은 fit×d≫1(포화)에서 tr 승 — 경계가 승패를 가른다")
D.add_table(s, [
  ["워크로드 (측정 셀)", "d (duty)", "입력 median", "fit", "fit×d", "R≷1", "실측 승자"],
  ["TraceLab · 4090", "0.196", "≈18.3k", "2.35", "0.46", "R<1", "default (tr −34%)"],
  ["TraceLab · Pro6000×2", "0.289", "18.7k", "24.5", "7.07", "R≫1", "tr (+80~87%)"],
  ["SWE-bench · 4090", "0.996", "7.9k", "5.56", "5.54", "R≫1", "tr (+78~84%)"],
  ["SWE-bench · Pro6000×2", "0.996", "7,897", "57.9", "57.6", "R≫1", "tr (+113%)"],
  ["HLE · Pro6000×1 (8B)", "≈0.82", "2,952", "34.5*", "≈28", "R≫1", "tr≈default (throughput)"],
  ["Science · Pro6000×1", "0.989", "6,214", "16.2", "16.0", "R≫1", "tr (+175~227%)"],
], 0.5, 1.95, 12.3, 3.3, fs=11.5, hdr_fs=11.5,
   col_widths=[2.9, 1.2, 1.6, 1.0, 1.1, 1.0, 2.9],
   highlight_rows={1: LOSE, 2: WIN, 4: WIN, 6: WIN})
D.add_text(s, "* HLE는 KV를 인위 축소한 후속(fit≈34.5)에서만 붕괴 재현. 큰 KV(fit~170)에선 스래싱 자체가 없어 tr=default.",
           0.5, 5.35, 12.3, 0.4, size=10.5, color=GRAY)
D.add_bullets(s, [
  ("TraceLab·4090가 유일한 fit×d<1 → 유일하게 tr이 진 셀. 경계가 승패를 100% 설명.", 0, INK, True),
  ("그런데 HLE는 fit×d≫1(포화)인데도 tr이 throughput으로 못 이긴다 → fit×d만으로는 부족하다는 첫 신호.", 0, AMBER, True),
], 0.5, 5.75, 12.3, 1.2, size=12.5, gap=8)
D.set_notes(s,
"이제 실제 워크로드 네 개가 fit×d 축의 어디에 앉는지 정확한 수치 표로 봅니다. 결과를 먼저 표로 드리고 다음 장에서 "
"왜 이런 특성이 나오는지 분석하겠습니다. TraceLab은 프리필 위주라 듀티가 낮습니다(4090 0.196). 4090에서 fit×d가 "
"0.46으로 유일하게 1 미만 — 미포화 — 이고, 실측에서도 유일하게 tr이 34% 졌습니다. 같은 TraceLab을 Pro6000 두 "
"장으로 KV를 열 배 키우면 fit×d가 7.07로 올라가 tr이 80~87% 이깁니다. SWE-bench는 디코드 위주라 듀티가 0.996 — "
"거의 1 — 이고 fit×d가 5.5에서 57.6까지, 전부 포화라 tr이 크게 이깁니다. Science는 제가 이번에 측정한 셀인데 듀티 "
"0.989, fit 16.2, fit×d 16.0으로 역시 포화이고 tr이 175에서 227% 이겼습니다. 여기까지는 경계가 승패를 100% "
"설명합니다 — 진 곳은 fit×d<1인 TraceLab·4090 하나뿐. 그런데 아래 노란 줄을 주목하세요. HLE는 fit×d가 1을 훨씬 "
"넘는 포화인데도 tr이 처리량으로는 못 이깁니다. fit×d만으로는 설명이 안 되는 첫 신호이고, 이게 뒤에서 '진짜 "
"U'라는 개념으로 이어집니다. 그 전에, 이 네 워크로드가 왜 이렇게 다른 특성을 갖는지부터 분석하겠습니다.")


# ---------------------------------------------------------------- slide 5b (regime map graph)
s = D._blank(prs)
D.band(s, 0, 0.14, BLUE)
D.add_title(s, "4 워크로드 승패 지도 — 표에 이어 그래프로")
D.add_text(s, "fit×d 축 위의 위치", 0.42, 1.02, 6.0, 0.3, size=12.5, color=GRAY, bold=True)
D.add_takeaway(s, "fit×d < 0.62 = default 승 / > 0.62 = tr 승. Science는 예측대로 tr 승, HLE는 tr 영역이나 throughput 예외")
D.add_figure(s, "regime_map_full_yunuikang", 0.35, 1.75, 12.6, 5.15)
D.set_notes(s,
"앞 장의 정확한 수치 표를 이제 한 장의 그래프로 봅니다. 가로축은 fit×d를 로그 스케일로 놓은 것이고, 빨간 점선 "
"0.62가 정책 전환점입니다 — 왼쪽 주황은 default가 이기는 영역, 오른쪽 파랑은 tr이 이기는 영역입니다. 위 행은 실제 "
"측정한 워크로드입니다. 4090/TraceLab만 전환점 왼쪽(fit×d=0.46)에 있어 default가 34% 이겼고, 나머지 4090/SWE, "
"Pro6000/TraceLab, Pro6000/SWE는 모두 오른쪽 tr 영역에서 tr이 78, 87, 113% 이겼습니다. 가운데 행은 뒤에서 볼 "
"합성 duty 스윕으로, 전환점을 촘촘히 훑어 경계가 0.62임을 확정한 점들입니다. 아래 행이 이번에 새로 채운 두 "
"워크로드입니다. Science는 fit×d=16으로 tr 영역 깊숙이 있고 예측대로 tr이 227% 이겼습니다 — 초록 사각형. "
"그런데 HLE는 fit×d가 28로 역시 tr 영역인데도, 속 빈 주황 다이아몬드에 빨간 가위표로 표시했습니다. 위치는 tr "
"영역이지만 상시 heavy-tail이 진짜 GPU 이용률을 0.64에서 0.71로 무너뜨려서, 캐시 적중은 28% 지켜도 처리량으로는 "
"tr이 지는 유일한 예외이기 때문입니다. 즉 이 지도 한 장이 연구의 뼈대를 요약합니다 — fit×d가 승패를 예측하되, "
"그 전제는 '진짜 U가 살아있을 때'이고, HLE만 그 전제가 깨진 예외라는 것입니다.")


# ---------------------------------------------------------------- slide 6
s = D._blank(prs)
D.band(s, 0, 0.14, BLUE)
D.add_title(s, "워크로드 특성 분석 — 무엇이 '진짜 U'를 가르나")
D.add_text(s, "duty·도구시간·tool tail 구조", 0.42, 1.02, 6.5, 0.3, size=12.5, color=GRAY, bold=True)
D.add_takeaway(s, "tool tail 스펙트럼: SWE(없음)─TraceLab(중간·30s cap)─Science(희소)─HLE(상시 원격). tail이 GPU 병목을 안 뺏으면 tr 승")
D.add_table(s, [
  ["특성", "SWE-bench", "TraceLab", "Science", "HLE"],
  ["duty d", "0.996", "0.196~0.289", "0.989", "≈0.82"],
  ["도구 위치", "로컬(docker)", "로컬(합성 replay)", "로컬(python)", "원격 GLM API"],
  ["도구시간 median", "0.15s", "0.047s", "0.077s", "2.7s"],
  ["도구시간 mean", "낮음", "6.87s", "1.09s", "높음"],
  ["도구시간 tail(max)", "없음", "30s (cap)", "300s(희소 1.3%)", "98s(상시)"],
  ["tool tail 구조", "없음", "중간·capped", "희소·극단", "상시 heavy-tail"],
  ["→ 진짜 U 영향", "포화", "포화(Pro6000)", "포화(U=100%)", "붕괴(U 0.64~0.71)"],
], 0.5, 1.9, 8.1, 3.9, fs=10.5, hdr_fs=11,
   col_widths=[1.9, 1.5, 1.6, 1.55, 1.55],
   highlight_rows={4: RGBColor(0xFF,0xF3,0xD6), 7: HL})
# tool tail spectrum diagram (right)
D.add_text(s, "tool-wait tail 스펙트럼", 8.9, 2.0, 4.0, 0.35, size=12.5, color=INK, bold=True)
D.chip(s, "SWE / Science  —  tail 없음·희소 → GPU 안 놀림 → U 포화 → tr이 hit를 throughput으로 전환",
       8.85, 2.55, 4.05, GREEN, size=10, h=1.0)
D.chip(s, "HLE  —  원격 API 상시 tail → 다수 프로그램이 늘 tool-wait로 off-GPU → U 무너짐 → tr이 hit 지켜도 throughput 못 얻음",
       8.85, 3.75, 4.05, RED, size=10, h=1.3)
D.add_text(s, "핵심: tool-wait이 wall-time을 지배하느냐가\n'진짜 U'(GPU 병목)를 가른다.\n"
              "fit×d가 커도 상시 tail이면 U가 낮아\ntr 이득이 throughput으로 안 바뀐다.",
           8.85, 5.25, 4.05, 1.4, size=11.5, color=INK)
D.set_notes(s,
"왜 HLE만 포화인데도 tr이 처리량으로 못 이기는지 — 그 답이 이 특성 분석에 있습니다. 네 워크로드를 duty, 도구 "
"위치, 도구 시간의 중앙값과 꼬리(tail), 그리고 tool tail 구조로 나눠봤습니다. SWE는 로컬 도커 도구라 도구 시간이 "
"0.15초 수준이고 꼬리가 사실상 없습니다 — 듀티 0.996. TraceLab은 짚고 넘어갈 뉘앙스가 있습니다. 도구 시간 "
"중앙값은 0.047초로 아주 낮지만, 평균은 6.87초입니다 — 전체 턴의 68%가 도구를 쓰고 그 꼬리가 30초에 캡됩니다. "
"즉 TraceLab의 낮은 듀티 0.196에서 0.289는 중앙값이 아니라 이 캡된 도구 꼬리에서 옵니다(추론 평균 2.80초보다 "
"도구 평균 6.87초가 크죠). 다만 HLE와 달리 이 꼬리는 로컬 합성 replay라 30초에 캡되어 있고 결정론적입니다. "
"참고로 원본 무캡 trace에는 42시간짜리 비정상 이상치가 한 건 있어 30초 캡으로 처리했습니다. Science도 로컬 "
"파이썬인데, 도구 시간 중앙값이 0.077초로 "
"거의 0이지만, 가끔 실제 모델 학습이 돌면 300초까지 튑니다. 다만 그런 극단이 전체의 1.3%뿐인 '희소한' 꼬리입"
"니다 — 듀티 0.989. 반면 HLE는 원격 GLM API가 도구라, 도구 시간 중앙값이 2.7초에 꼬리가 98초까지 '상시로' "
"깁니다 — 듀티 0.82. 오른쪽 스펙트럼이 핵심입니다. SWE와 Science처럼 꼬리가 없거나 희소하면, GPU가 도구 대기로 "
"노는 시간이 거의 없어 진짜 이용률 U가 포화 상태를 유지합니다 — Science는 실측 U가 100%였습니다. 그러면 tr이 "
"지켜낸 캐시 적중이 그대로 처리량 이득으로 바뀝니다. 그런데 HLE는 원격 API 꼬리가 상시로 길어서, 열두세 개 "
"프로그램이 늘 도구 대기 상태로 GPU에서 빠져 있습니다. 그래서 fit×d가 아무리 커도 실측 U가 0.64에서 0.71로 "
"낮게 눌립니다. 이 상태에선 tr이 캐시 적중을 지켜도 그게 처리량으로 환산되지 않습니다. 즉 승패의 진짜 결정자는 "
"fit×d가 아니라 'tool-wait이 wall-time을 지배하느냐', 곧 진짜 U입니다. 이 통찰이 뒤의 HLE와 Science 대조에서 "
"결정적으로 쓰입니다. 참고로 이 '진짜 U'는 프록시 in-flight·vLLM nrr·nvidia-smi 세 방식으로 독립 측정해 "
"상관 0.999, 평균 절대차 0.06 이내로 일치를 확인했습니다 — U가 계측 아티팩트가 아니라 실제 GPU 병목 신호임을 "
"보증합니다.")


# ---------------------------------------------------------------- slide 7
s = D._blank(prs)
D.band(s, 0, 0.14, BLUE)
D.add_title(s, "두 레버 — R을 1 위로 올리는 두 축")
D.add_text(s, "미포화 탈출 전략", 0.42, 1.02, 6.0, 0.3, size=12.5, color=GRAY, bold=True)
D.add_takeaway(s, "R = k_fit × d 는 곱 — k_fit↑(overcommit, 정책) 또는 d↑(duty, 워크로드). idle↔recompute 상충이 핵심")
D.chip(s, "R = k_fit × d   (곱)", 4.4, 1.9, 4.5, GREEN, size=15, h=0.5)
# two lever boxes
b1 = s.shapes.add_textbox(D.Inches(0.6), D.Inches(2.65), D.Inches(5.9), D.Inches(3.6))
tf = b1.text_frame; tf.word_wrap = True
tf.paragraphs[0].text = "레버 A — k_fit ↑ (overcommit)"
tf.paragraphs[0].runs[0].font.size = D.Pt(15); tf.paragraphs[0].runs[0].font.bold = True
tf.paragraphs[0].runs[0].font.color.rgb = BLUE
for t in ["정책이 통제하는 축. 캐시를 fit 위로 초과 적재해 노는 GPU를 회수.",
          "이득: idle 감소 (+d 만큼 점유 회수).",
          "비용: 초과분이 thrashing → recompute(재프리필).",
          "→ 조건 1에서 노브 f로 실험 (f=1 tr … f=∞ default)."]:
    p = tf.add_paragraph(); p.text = "•  " + t; p.space_after = D.Pt(8)
    p.runs[0].font.size = D.Pt(12.5); p.runs[0].font.color.rgb = INK
b2 = s.shapes.add_textbox(D.Inches(6.8), D.Inches(2.65), D.Inches(6.0), D.Inches(3.6))
tf = b2.text_frame; tf.word_wrap = True
tf.paragraphs[0].text = "레버 B — d ↑ (duty)"
tf.paragraphs[0].runs[0].font.size = D.Pt(15); tf.paragraphs[0].runs[0].font.bold = True
tf.paragraphs[0].runs[0].font.color.rgb = GREEN
for t in ["워크로드 성질. reasoning:tool 비율이 높을수록 d↑ → R↑.",
          "d가 높으면 같은 k_fit로도 R이 쉽게 1을 넘음(포화).",
          "정책으로 못 바꾸는 축 → 정밀 통제하려면 합성이 필요.",
          "→ 조건 2에서 E2E 고정·비율만 변경해 스윕."]:
    p = tf.add_paragraph(); p.text = "•  " + t; p.space_after = D.Pt(8)
    p.runs[0].font.size = D.Pt(12.5); p.runs[0].font.color.rgb = INK
D.add_text(s, "★ 상충(tradeoff): k_fit을 1 올리면 idle 이득 ≈ +d,  recompute 비용 ≈ ctx·P(miss)/prefill_rate. "
              "두 한계효과가 같아지는 지점 = 최적 overcommit f*.  tr(f=1)·default(f=∞)는 양 끝.",
           0.6, 6.35, 12.3, 0.9, size=12, color=INK, bold=True)
D.set_notes(s,
"미포화에서 GPU를 놀리지 않으려면 R을 1 위로 올려야 합니다. R은 k_fit 곱하기 d인 곱이라, 올리는 길이 두 갈래 "
"입니다. 레버 A는 k_fit을 올리는 것 — 이건 정책이 통제하는 축입니다. 캐시를 fit 한계 위로 초과 적재(overcommit)"
"해서 노는 GPU를 회수합니다. 이득은 idle이 줄어드는 것이고(대략 듀티 d만큼 점유를 회수), 비용은 fit을 넘은 "
"초과분이 thrashing을 일으켜 재프리필(recompute)이 생기는 겁니다. 이 축을 노브 f로 만들어 실험한 게 조건 1입"
"니다 — f=1이면 tr, f=무한대면 default. 레버 B는 duty d를 올리는 것 — 이건 워크로드의 성질입니다. reasoning 대 "
"tool 비율이 높을수록 d가 커지고, d가 크면 같은 k_fit로도 R이 쉽게 1을 넘어 포화됩니다. 그런데 이건 정책으로 "
"바꿀 수 없는 축이라, 정밀하게 통제하려면 합성 워크로드가 필요합니다 — 그게 조건 2입니다. 맨 아래 별표가 이 "
"발표의 이론적 심장입니다. k_fit을 하나 올리면 idle 이득은 대략 +d만큼, recompute 비용은 컨텍스트 곱하기 미스 "
"확률 나누기 프리필 속도만큼 생깁니다. 이 두 한계효과가 같아지는 지점이 최적 overcommit f*입니다. tr은 f=1, "
"default는 f=무한대로 양 끝이고, 그 사이 어딘가에 최적이 있느냐가 조건 1의 질문입니다. 다음 두 장에서 두 조건을 "
"어떻게 설계했는지 보여드립니다.")


# ---------------------------------------------------------------- slide 8
s = D._blank(prs)
D.band(s, 0, 0.14, BLUE)
D.add_title(s, "조건 1 — overcommit 노브 (왜·어떻게·무엇을)")
D.add_text(s, "레버 A 실험 설계", 0.42, 1.02, 6.0, 0.3, size=12.5, color=GRAY, bold=True)
D.add_takeaway(s, "--capacity-overcommit-factor f 하나로 tr(f=1)↔default(f=∞) 연속축. router.py 4곳에 +margin만.")
D.add_bullets(s, [
  ("왜: k_fit을 fit 위로 밀어 노는 GPU를 회수하면, 그 recompute 비용을 상쇄하고 이득이 남는가?", 0, INK, True),
  ("어떻게: margin =(f−1)·C_total 을 용량 부등식에 더함. f=1→tr과 비트동일, f→∞→default.", 0, INK, False),
  ("무엇을: f∈{1, 1.25, 1.5, 2, 3, 5, ∞} 스윕 → 미포화 zone에 내부 최적 f*가 있나?", 0, BLUE, True),
], 0.5, 1.95, 6.4, 2.0, size=12.5, gap=9)
D.add_text(s, "★ 금지: C_total 자체를 부풀리면 안 됨 (calculate_shared_tokens가 그 값을 재사용 → overcommit 역효과).\n"
              "각 비교식에 +margin 만. pause victim·decay 2^-t·BFD packing·fairness는 불변.",
           0.5, 4.1, 6.4, 1.2, size=11, color=AMBER)
# code map (right)
D.add_text(s, "scheduler/router.py — 손댄 4곳(+margin)", 7.1, 1.95, 5.8, 0.35, size=12.5, color=INK, bold=True)
D.add_table(s, [
  ["위치", "함수", "변경"],
  [":770", "_scheduled_check", "remaining()+margin < 0"],
  [":780", "_pause_until_safe", "while remaining()+margin < 0"],
  [":835/837", "_greedy_resume", "remaining = (...)+margin"],
  [":356", "_select_backend…", "remaining()+margin < required"],
], 7.1, 2.4, 5.8, 2.3, fs=10.5, hdr_fs=11, col_widths=[1.1, 2.3, 2.4])
D.add_text(s, "5-hop CLI 배선: __main__(add_argument·Config) → config.py field → app.py Router ctor → router.py param.\n"
              "격리 원칙: 이 4곳 +margin 외 로직 무수정. f=1e6 스모크로 default 수렴 확인.",
           7.1, 4.85, 5.8, 1.3, size=10.5, color=GRAY)
D.set_notes(s,
"레버 A를 어떻게 실험으로 만들었는지입니다. 왜 하냐면, k_fit을 fit 한계 위로 밀어 노는 GPU를 회수했을 때, "
"거기서 생기는 재계산 비용을 상쇄하고도 이득이 남는지를 봐야 하기 때문입니다. 어떻게 하냐면, 새 CLI 플래그 "
"--capacity-overcommit-factor f를 만들고, margin을 (f-1) 곱하기 KV 총용량으로 정의해 스케줄러의 용량 부등식에 "
"더합니다. f가 1이면 margin이 0이라 지금의 tr과 비트 단위로 동일하고, f가 무한대로 가면 용량이 사실상 무제한이라 "
"default처럼 됩니다. 즉 노브 하나로 두 정책 사이를 연속으로 잇습니다. 무엇을 보냐면, f를 1부터 무한대까지 "
"스윕해서 미포화 zone 안에 tr과 default를 둘 다 이기는 내부 최적 f*가 존재하는지를 봅니다. 오른쪽이 실제로 손댄 "
"코드입니다. scheduler/router.py의 딱 네 곳 — 일시정지 트리거, 정지 루프, 재개 용량, 새 프로그램 배정 — 각각의 "
"비교식에 +margin만 더했습니다. 중요한 금지 사항이 있습니다. C_total 값 자체를 부풀리면 안 됩니다. "
"calculate_shared_tokens가 그 값을 재사용하기 때문에, 부풀리면 remaining_capacity가 오히려 줄어 overcommit이 "
"역효과를 냅니다. 그래서 각 비교식에 +margin만 얹고, pause 희생자 선택·감쇠 2의 -t승·BFD 패킹·공정성 큐 같은 "
"불변식은 건드리지 않았습니다. f를 백만으로 준 스모크로 default에 수렴하는 것도 확인했습니다.")


# ---------------------------------------------------------------- slide 9
s = D._blank(prs)
D.band(s, 0, 0.14, BLUE)
D.add_title(s, "조건 2 — duty 통제 합성 (왜·어떻게·무엇을)")
D.add_text(s, "레버 B 실험 설계", 0.42, 1.02, 6.0, 0.3, size=12.5, color=GRAY, bold=True)
D.add_takeaway(s, "E2E 시간을 고정하고 acting:reasoning 비율만 바꿔 duty d를 정밀 통제 — 처리량 이득의 자명성 제거")
D.add_bullets(s, [
  ("왜: 예전 tool_scale는 도구시간을 줄여 E2E까지 단축 → 처리량 이득이 '자명'해 상충을 못 봄.", 0, RED, True),
  ("어떻게: 프로그램 총시간 T 고정. reasoning=d·T, tool=(1−d)·T. d만 바꿈.", 0, INK, True),
  ("  reasoning은 토큰 프로파일(모델 GPU시간), tool은 드라이버 sleep으로 설정.", 1, GRAY, False),
  ("  캘리브: cold prefill 1.696e-4·ptok−0.450 (r²0.981), 5,896 tok/s, decode~52 tok/s.", 1, GRAY, False),
  ("무엇을: d∈{0.1,0.2,0.3,0.5,0.7,0.9} × f{1,1.5,2,∞} × C{fit/2,fit,2fit,4fit}, REPEAT=3.", 0, BLUE, True),
], 0.5, 1.95, 8.0, 3.3, size=12, gap=7)
D.add_text(s, "정직 caveat: 캘리브는 c=1 값. 부하 시 TTFT가 큐 대기를 흡수(부하 TTFT 10.79s vs c=1 0.46s) →\n"
              "duty는 '순수 GPU(reasoning) 시간'으로 정의하고 STEP 5에서 부하 하 교차검증.",
           0.5, 5.35, 8.0, 1.1, size=10.5, color=AMBER)
# right schematic
D.chip(s, "E2E 고정", 9.0, 2.1, 3.6, INK, size=13, h=0.45)
D.add_text(s, "d=0.2 (저듀티)\n"
              "[reasoning ▪▪ ][ tool ▪▪▪▪▪▪▪▪ ]\n\n"
              "d=0.9 (고듀티)\n"
              "[reasoning ▪▪▪▪▪▪▪▪▪ ][tool ▪]\n\n"
              "→ 총 길이 T는 동일, 내부 비율만 이동\n→ 처리량 차이는 오직 duty 효과",
           9.0, 2.75, 3.9, 3.5, size=12, color=INK)
D.set_notes(s,
"레버 B, 즉 duty를 어떻게 정밀 통제했는지입니다. 왜 새 설계가 필요했냐면, 예전 방식(tool_scale)은 도구 시간을 "
"줄여서 워크로드를 만들었는데, 그러면 프로그램 전체 시간(E2E)까지 짧아집니다. 그럼 처리량이 좋아지는 게 너무 "
"당연해서, idle과 recompute의 상충을 관찰할 수가 없습니다. 그래서 새 설계는 각 프로그램의 E2E 시간 T를 고정하고, "
"그 안에서 reasoning을 d 곱하기 T, tool을 (1-d) 곱하기 T로 나눠 duty d만 바꿉니다. reasoning 시간은 입력·출력 "
"토큰 프로파일로(모델 GPU 시간), tool 시간은 드라이버의 sleep으로 설정합니다. 캘리브레이션은 프로파일링에서 잰 "
"값을 씁니다 — 콜드 프리필이 토큰당 1.696e-4초 빼기 0.45, 결정계수 0.981, 초당 5896토큰, 디코드는 배치1에서 "
"초당 52토큰. 무엇을 보냐면, duty 여섯 값과 f 값들과 프로그램 수 C를 곱한 격자를 반복 3회로 돌립니다. 오른쪽 "
"그림처럼 총 길이 T는 같고 내부 비율만 움직이니, 처리량 차이는 오직 duty 효과입니다. 정직한 한계도 있습니다. "
"캘리브 값은 동시성 1에서 잰 것인데, 부하가 걸리면 TTFT가 큐 대기를 흡수합니다 — 부하 TTFT 10.79초 대 동시성1 "
"0.46초. 그래서 duty는 큐 대기를 뺀 '순수 GPU 시간'으로 정의하고, 부하 하에서는 STEP 5에서 교차검증했습니다.")


# ---------------------------------------------------------------- slide 9b (experimental environment)
s = D._blank(prs)
D.band(s, 0, 0.14, BLUE)
D.add_title(s, "실험 환경 정리 — duty 스윕 셋업 (goguma 2×5090)")
D.add_text(s, "결과 전 셋업", 0.42, 1.02, 6.0, 0.3, size=12.5, color=GRAY, bold=True)
D.add_takeaway(s, "5090/8B에 fit=4.77 고정, duty만 0.1~0.9 스윕 → 예상 R(=fit×d) 0.48~4.29로 미포화~포화 전 구간 관통")
# left: hardware / cache
D.add_text(s, "하드웨어 · KV 캐시", 0.5, 1.85, 6.2, 0.32, size=12.5, color=INK, bold=True)
D.add_table(s, [
  ["항목", "값 (실측)"],
  ["서버 / GPU", "goguma · 2×RTX5090 (각 32GB)"],
  ["모델", "Qwen3-8B (단일 GPU)"],
  ["SM / 드라이버", "Blackwell sm_120 · CUDA 13.0"],
  ["★ C_total (KV풀)", "89,040 tok (block16 × 5,565)"],
  ["vs 4090", "×2.03 (43,888 → 89,040)"],
  ["배치 레짐", "32GB<70GiB → 2048/256 (4090 동일)"],
  ["ctx / fit", "18,684 tok → fit = 4.77"],
], 0.5, 2.25, 6.2, 2.5, fs=10.5, hdr_fs=11,
   col_widths=[2.0, 4.2], highlight_rows={4: RGBColor(0xFF,0xF3,0xD6), 8: RGBColor(0xDF,0xEE,0xE4)})
# right: synthetic workload calibration
D.add_text(s, "합성 duty 워크로드 캘리브 (5090 c=1)", 7.0, 1.85, 5.8, 0.32, size=12.5, color=INK, bold=True)
D.add_table(s, [
  ["캘리브 항목", "값"],
  ["COLD prefill", "9,202 tok/s"],
  ["WARM prefill", "3,974 tok/s"],
  ["DECODE", "97 tok/s"],
  ["설계 d vs 실측 d", "0.20 vs 0.1978 (오차 1.12%)"],
], 7.0, 2.25, 5.8, 1.55, fs=10.5, hdr_fs=11,
   col_widths=[2.6, 3.2], highlight_rows={4: RGBColor(0xDF,0xEE,0xE4)})
D.add_text(s, "정직 기록: 1차 4090 레이트(5896/52 tok/s) → 실측 d 400% 오류(5090이 2배 빠름). "
              "5090 레이트로 교정 + prefix cache flush(clean restart) 후 오차 1.12% PASS.",
           7.0, 3.9, 5.8, 0.9, size=10, color=GRAY)
# bottom: duty × expected R (full width)
D.add_text(s, "duty별 예상 R (fit=4.77 고정, C=10≈2×fit) — 미포화부터 포화까지 관통", 0.5, 4.9, 12.3, 0.32,
           size=12.5, color=INK, bold=True)
D.add_table(s, [
  ["duty d", "0.1", "0.2", "0.3", "0.5", "0.7", "0.9"],
  ["예상 R = fit×d", "0.48", "0.95", "1.43", "2.38", "3.33", "4.29"],
  ["f_sat = 1/(fit×d)", "2.10", "1.05", "0.70", "0.42", "0.30", "0.23"],
  ["영역", "미포화", "경계", "포화", "포화", "포화", "포화"],
], 0.5, 5.3, 12.3, 1.35, fs=11, hdr_fs=11,
   col_widths=[2.5, 1.63, 1.63, 1.63, 1.63, 1.63, 1.63],
   highlight_col=None, highlight_rows={1: RGBColor(0xEA,0xF2,0xFB)})
D.add_text(s, "스윕: f ∈ {1, 1.25, 1.5, 2, ∞} · REPEAT=3 · router.py 4곳 +margin 외 무수정 · 격리 파일 *_yunuikang",
           0.5, 6.75, 12.3, 0.4, size=10.5, color=GRAY)
D.set_notes(s,
"duty 스윕 결과를 보기 전에, 제가 어떤 환경에서 무엇을 어떻게 만들었는지 한 장에 정리합니다. 하드웨어는 goguma "
"서버의 RTX 5090 두 장, 각 32GB입니다 — nutella1에는 이 실험에 쓸 여유 GPU가 없어 goguma를 썼습니다. 모델은 "
"Qwen3-8B를 단일 GPU에 올렸고, Blackwell sm_120에 CUDA 13입니다. 왼쪽 표의 핵심은 KV 캐시 총량 C_total인데, "
"기동 로그에서 실측한 값이 89,040 토큰입니다 — 블록 크기 16에 블록 5,565개죠. 4090의 43,888보다 2.03배 크고, "
"32GB는 70GiB 경계 아래라 4090과 동일한 2048/256 배치 토큰 레짐입니다. 이게 중요한 이유는, 배치 변수를 4090과 "
"똑같이 고정한 깨끗한 대조가 되기 때문입니다. TraceLab 8B의 컨텍스트가 18,684 토큰이라 fit은 89,040 나누기 "
"18,684, 즉 4.77입니다. 오른쪽은 제가 만든 합성 duty 워크로드의 캘리브레이션입니다. E2E 시간을 고정하고 duty만 "
"바꾸려면 모델의 프리필·디코드 속도를 정확히 알아야 하는데, 5090에서 동시성 1로 재니 콜드 프리필 초당 9,202, "
"웜 3,974, 디코드 97 토큰입니다. 정직하게 기록할 실패담이 하나 있습니다 — 처음엔 4090 레이트(5896, 52)를 "
"그대로 썼다가 실측 duty가 설계값의 400% 어긋났습니다. 5090이 두 배 빨라서였죠. 5090 레이트로 바꾸고 prefix "
"캐시를 비운 뒤 재기동하니 오차 1.12%로 통과했습니다. 아래 표가 이 셋업의 결론입니다. fit을 4.77로 고정하고 "
"duty만 0.1부터 0.9까지 바꾸면, 예상 R 즉 fit×d가 0.48부터 4.29까지 움직입니다. 즉 duty 하나로 미포화(0.48)와 "
"경계(0.95)와 포화(4.29)를 전부 관통하도록 설계했습니다. 각 duty의 f_sat, 즉 포화에 필요한 overcommit 배수도 "
"함께 적었습니다. 스윕은 f를 1부터 무한대까지, 프로그램 수 C는 fit의 두 배인 10으로, 반복 3회 돌렸습니다. "
"router.py는 앞서 말한 네 곳에 margin을 더한 것 외에는 건드리지 않았고, 모든 신규 파일은 격리 접미사를 "
"붙였습니다. 이제 이 환경에서 나온 결과를 보겠습니다.")


# ---------------------------------------------------------------- slide 10
s = D._blank(prs)
D.band(s, 0, 0.14, BLUE)
D.add_title(s, "결과 ① — 2D 극단 표: duty × {tr(f=1), default(f=∞)}")
D.add_text(s, "조건1 × 조건2 (표 먼저)", 0.42, 1.02, 6.5, 0.3, size=12.5, color=GRAY, bold=True)
D.add_takeaway(s, "duty=0.1에서 승자가 default로 뒤집힌다 — 미포화에선 tr이 GPU를 굶겨(U 22%) 진다")
D.add_table(s, [
  ["d", "fit×d", "tr goodput", "tr p95", "tr hit", "tr U%", "tr fail", "def goodput", "def p95", "def hit", "def U%", "승자"],
  ["0.1", "0.476", "0.036", "238", "0.76", "22", "10%", "0.051", "186", "0.01", "84", "default +26%"],
  ["0.2", "0.952", "0.073", "121", "0.86", "30", "0%", "0.055", "171", "0.01", "92", "tr +31%"],
  ["0.3", "1.428", "0.093", "97", "0.86", "44", "0%", "0.057", "165", "0.01", "91", "tr +64%"],
  ["0.5", "2.381", "0.111", "76", "0.86", "49", "0%", "0.057", "166", "0.01", "93", "tr +96%"],
  ["0.7", "3.333", "0.115", "73", "0.86", "50", "0%", "0.057", "164", "0.01", "93", "tr +101%"],
  ["0.9", "4.285", "0.133", "59", "0.85", "61", "0%", "0.057", "164", "0.01", "92", "tr +132%"],
], 0.4, 1.95, 12.5, 3.5, fs=10.5, hdr_fs=10,
   col_widths=[0.6,0.85,1.05,0.75,0.75,0.75,0.8,1.05,0.85,0.8,0.8,1.6],
   highlight_rows={1: LOSE})
D.add_bullets(s, [
  ("d=0.1(fit×d=0.476): tr goodput 0.036 < default 0.051 → default 승 +26%. tr U 22%로 GPU를 굶김.", 0, RED, True),
  ("d≥0.2: tr이 hit(0.85~0.86)를 지켜 goodput +31~132% 압승. default hit은 전 구간 0.01(스래싱).", 0, BLUE, True),
  ("★ tr fail 10%(d=0.1) — capacity timeout. default는 전 구간 0%. tr의 신뢰성 리스크.", 0, AMBER, True),
], 0.4, 5.55, 12.5, 1.4, size=11.5, gap=6)
D.set_notes(s,
"이제 두 조건을 곱한 2D 결과입니다. 지표부터 짚습니다. 여기 throughput은 goodput, 즉 완료 프로그램 수 나누기 "
"makespan입니다. 날 것의 초당 토큰 수는 default의 재계산 낭비까지 토큰으로 세어 오도하기 때문에 쓰지 않습니다 — "
"이게 이 연구의 핵심 논점 중 하나입니다. 표는 극단 두 정책, tr(f=1)과 default(f=무한대)를 duty별로 비교합니다. "
"맨 윗줄, duty 0.1에서 승자가 뒤집힙니다. tr의 goodput이 0.036으로 default의 0.051보다 낮아 default가 26% "
"이깁니다. 이유는 tr의 U가 22%밖에 안 된다는 것 — tr이 pause만 하다 보니 미포화에서 GPU를 굶깁니다. 반대로 "
"duty가 0.2 이상이면 tr이 캐시 적중을 0.85에서 0.86으로 지켜서 goodput이 31%에서 132%까지 압승합니다. default는 "
"전 구간 적중이 0.01 — 완전히 스래싱합니다. 그리고 별표로 표시한 신뢰성 리스크가 중요합니다. duty 0.1에서 tr의 "
"실패율이 10%입니다 — capacity timeout으로 일부 프로그램이 마감을 못 지킵니다. default는 전 구간 실패 0%입니다. "
"즉 tr은 미포화에서 느릴 뿐 아니라 불안정합니다. 그럼 tr과 default 사이 중간 f가 이 두 문제를 다 푸는 최적이 "
"될까요? 다음 장에서 봅니다.")

prs.save("/home/yunuikang/yunuikang_work/distserving/scratch/sab/_deck_part1.pptx")
print("part1 saved:", len(prs.slides._sldIdLst), "slides")
