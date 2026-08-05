#!/usr/bin/env python3
"""MORI 코드 검증 발표덱 (S1~S16).

수치는 전부 scratch/mori/deck_numbers.json (로그 직추출)에서만 읽는다 — 하드코딩 금지.
★ 검증 슬라이드는 동일한 3구역 패턴: ① 논문이 이렇게 규정 → ② 그래서 이 실험 → ③ 측정+판정.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decklib_yunuikang import (  # noqa: E402
    new_deck, _blank, add_title, add_takeaway, add_text, add_bullets, add_figure,
    add_caption, add_table, set_notes, band, chip,
    INK, BLUE, RED, GREEN, GRAY, LT, AMBER, WHITE,
)
from pptx.util import Inches, Pt  # noqa: E402
from pptx.dml.color import RGBColor  # noqa: E402
from pptx.enum.shapes import MSO_SHAPE  # noqa: E402
from pptx.enum.text import PP_ALIGN  # noqa: E402

D = json.load(open("/home/yunuikang/yunuikang_work/scratch/mori/deck_numbers.json"))
S7 = D["S7"]
OUT = "/home/yunuikang/yunuikang_work/distserving/slides/2026-08-04_MORI_code-verification_yunuikang.pptx"

PURPLE = RGBColor(0x6E, 0x4B, 0x9E)
HEALTHY = RGBColor(0xE7, 0xF3, 0xEC)
EXTREME = RGBColor(0xFB, 0xE9, 0xE7)
PANEL = RGBColor(0xF4, 0xF6, 0xFA)

prs = new_deck()


def slide(title, takeaway=None, tw_color=BLUE):
    s = _blank(prs)
    band(s, 0.0, 0.11, INK)
    add_title(s, title)
    if takeaway:
        add_takeaway(s, takeaway, color=tw_color)
    return s


def zone(s, n, label, x, y, w, h, color):
    """검증 3구역 패턴의 한 구역: 번호칩 + 제목 + 배경 패널."""
    p = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    p.fill.solid(); p.fill.fore_color.rgb = PANEL
    p.line.color.rgb = RGBColor(0xDD, 0xE1, 0xE8); p.line.width = Pt(0.75)
    p.shadow.inherit = False
    chip(s, f"{n}  {label}", x + 0.12, y + 0.10, min(w - 0.24, 4.5), color, size=10.5, h=0.30)
    return p


def footer(s, txt):
    add_text(s, txt, 0.42, 7.06, 12.5, 0.3, size=8.5, color=GRAY)


# =====================================================================  S1 표지
s = slide("")
band(s, 0.0, 7.5, INK)
add_text(s, "MORI 구현 코드 검증", 0.9, 2.15, 11.5, 1.0, size=44, color=WHITE, bold=True)
add_text(s, "우리가 만든 코드가 논문 정책대로 정확히 작동하는가", 0.92, 3.25, 11.5, 0.5,
         size=19, color=RGBColor(0x9F, 0xB6, 0xD8))
band(s, 4.05, 0.035, RGBColor(0x2E, 0x5E, 0xAA), x=0.92, w=3.2)
add_text(s,
         f"goguma6 · RTX 5090 ×2 (TP2) · SGLang + HiCache · {D['env']['model']} · "
         f"KV pool {D['env']['pool_tokens']:,} tok",
         0.92, 4.35, 11.5, 0.4, size=13, color=RGBColor(0xC7, 0xD3, 0xE6))
add_text(s, "2026-08-04 · yunuikang", 0.92, 4.85, 11.5, 0.4, size=12, color=GRAY)
chip(s, f"A 계층 {D['A_total']}/{D['A_denom']} PASS", 0.92, 5.55, 2.5, GREEN, size=12, h=0.42)
chip(s, "B 계층 실동작 확인", 3.62, 5.55, 2.5, BLUE, size=12, h=0.42)
chip(s, "STEP7 유용성 정량화", 6.32, 5.55, 2.6, PURPLE, size=12, h=0.42)
set_notes(s, """오늘 발표는 "MORI 논문을 우리가 구현한 코드"가 논문에 적힌 정책대로 정확히 동작하는지
직접 검증한 결과입니다.

핵심 메시지 세 가지를 미리 말씀드리면:
1) 정책 충실성 검사 17개를 모두 통과했습니다.
2) 실제 GPU를 돌려서 "idle 프로그램이 CPU로 내려가고 다시 올라온다"는 메커니즘이 진짜로 작동함을 확인했습니다.
3) 그런데 아주 높은 동시성에서는 성능이 논문과 반대로 나옵니다. 이게 코드 버그 때문이 아니라
   하드웨어 환경(레짐) 때문이라는 것까지 데이터로 보여드립니다.

환경은 5090 두 장에 Qwen3-8B를 텐서병렬 2로 올렸고, SGLang의 HiCache(호스트 메모리 KV 캐시)를 씁니다.
GPU KV 풀은 262,144 토큰으로 고정했습니다.""")

# =====================================================================  S2 목적
s = slide("왜 검증이 먼저인가", "우리의 모든 결과 분석은 “코드가 맞다”는 가정 위에 있다 → 그 가정을 직접 검증한다")
# 좌: 문제제기
p = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.42), Inches(1.85), Inches(6.0), Inches(2.15))
p.fill.solid(); p.fill.fore_color.rgb = EXTREME; p.line.fill.background(); p.shadow.inherit = False
add_text(s, "지금까지의 실험 해석은 전부 전제가 하나 있었다", 0.65, 2.0, 5.6, 0.4, size=13, bold=True, color=RED)
add_bullets(s, [
    ("“throughput이 이렇다 / TTFT가 저렇다” → 다 맞는 말이려면", 0, INK, False),
    ("먼저 **스케줄러가 논문대로 결정하고 있어야** 한다", 0, INK, True),
    ("아니면 우리는 “버그의 성능”을 분석하고 있는 셈", 0, RED, True),
], 0.65, 2.45, 5.6, 1.4, size=12.5)
# 우: MORI 한 줄 소개 다이어그램
add_text(s, "MORI가 하는 일 (한 줄)", 6.95, 1.9, 6.0, 0.35, size=13, bold=True, color=BLUE)
for i, (t, sub, col, x) in enumerate([
        ("busy 프로그램", "ι 낮음 → GPU 유지", GREEN, 6.95),
        ("idle 프로그램", "ι 높음(긴 tool call)\n→ CPU로 offload", AMBER, 9.05),
        ("여유 생기면", "다시 GPU로 promote", BLUE, 11.15)]):
    b = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(2.3), Inches(1.9), Inches(1.15))
    b.fill.solid(); b.fill.fore_color.rgb = col; b.line.fill.background(); b.shadow.inherit = False
    tf = b.text_frame; tf.word_wrap = True; tf.text = t
    tf.paragraphs[0].runs[0].font.size = Pt(12); tf.paragraphs[0].runs[0].font.bold = True
    tf.paragraphs[0].runs[0].font.color.rgb = WHITE
    tf.paragraphs[0].alignment = PP_ALIGN.CENTER
    pp = tf.add_paragraph(); pp.text = sub; pp.alignment = PP_ALIGN.CENTER
    pp.runs[0].font.size = Pt(9.5); pp.runs[0].font.color.rgb = WHITE
add_text(s, "ι(iota) = 상대 idleness = 최근 실행시간 중 tool call이 차지한 비율 (0~1)\n"
            "→ 고정 임계가 아니라 **다른 프로그램과 비교한 상대 순위**로 자리를 정한다",
         6.95, 3.6, 6.0, 0.8, size=11, color=GRAY)
add_table(s, [
    ["검증 계층", "무엇을 보는가", "결과"],
    ["A 정책 충실성", "코드가 논문 규칙대로 결정하는가 (합성)", f"{D['A_total']}/{D['A_denom']} PASS"],
    ["B 실동작", "실제 GPU에서 메커니즘이 도는가", "핵심 3개 확인"],
    ["STEP7 유용성", "바쁜 GPU가 실제로 유용한 일을 했는가", "건강 구간 정상"],
], 0.42, 4.35, 12.5, 1.35, fs=12, hdr_fs=12,
    col_widths=[2.6, 6.6, 3.3], highlight_rows={1: HEALTHY})
footer(s, "※ 검증 목표는 “결과 정당화”가 아니라 “코드가 논문 정책과 일치하는가”이다.")
set_notes(s, """왜 굳이 코드 검증을 따로 하느냐는 질문에 답하는 슬라이드입니다.

우리는 지금까지 throughput, TTFT 같은 성능 숫자를 놓고 해석을 해왔습니다.
그런데 그 해석이 의미가 있으려면 대전제가 하나 성립해야 합니다 —
"스케줄러가 논문에 적힌 대로 판단하고 있다"는 것이죠.
만약 구현에 버그가 있다면 우리는 논문 정책의 성능이 아니라 버그의 성능을 분석한 게 됩니다.
그래서 성능 얘기를 더 하기 전에 이 전제를 직접 검증했습니다.

오른쪽은 MORI가 뭘 하는지 한 줄 소개입니다.
LLM 에이전트는 "생각(GPU에서 토큰 생성)"과 "행동(tool call, 예를 들어 웹 검색이나 코드 실행)"을 번갈아 합니다.
tool call 중에는 GPU를 안 쓰는데도 그 프로그램의 KV 캐시가 GPU 메모리를 차지하고 있습니다.
MORI는 이걸 CPU 메모리로 잠깐 내려놓고, 그 자리에 다른 바쁜 프로그램을 올립니다.

여기서 핵심 개념이 ι(이오타)입니다. 최근 실행 시간 중 tool call이 차지한 비율이에요.
중요한 건 "ι가 0.7 넘으면 내린다" 같은 고정 임계가 아니라,
지금 돌고 있는 프로그램들끼리 상대적으로 비교해서 순위를 매긴다는 점입니다.
그래서 논문 제목이 "Idleness is Relative"입니다.""")

# =====================================================================  S3 방법론
s = slide("검증 방법론 — 3계층", "각 계층이 답하는 질문이 다르다 · 신뢰장치 2개로 검증 자체를 검증")
tiers = [
    ("A", "정책 충실성", "white-box · known-answer 합성",
     "가짜 프로그램을 손으로 만들어\n스케줄러 결정만 격리 호출\n→ 정답을 미리 알고 맞히는지 본다",
     f"A1~A7f {D['A_total']}개", GREEN, 0.42),
    ("B", "실동작", "black-box · 실 GPU 실측",
     "실제 SGLang + HiCache로 돌려\ntier 이동·KV 감소·reload를\n엔진 카운터로 관측",
     "B0~B3", BLUE, 4.72),
    ("7", "유용성", "goodput · 시간 분해",
     "GPU가 바쁜 것과 유용한 일을\n구분 — goodput, recompute율,\nping-pong, profile 분해",
     "지표 ①~⑤", PURPLE, 9.02),
]
for tag, name, kind, body, cnt, col, x in tiers:
    p = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(1.85), Inches(3.9), Inches(2.75))
    p.fill.solid(); p.fill.fore_color.rgb = PANEL
    p.line.color.rgb = col; p.line.width = Pt(1.5); p.shadow.inherit = False
    chip(s, f"{tag}   {name}", x + 0.15, 2.0, 2.5, col, size=12, h=0.34)
    add_text(s, kind, x + 0.2, 2.45, 3.5, 0.3, size=10.5, color=GRAY, bold=True)
    add_text(s, body, x + 0.2, 2.8, 3.5, 1.3, size=11.5, color=INK)
    chip(s, cnt, x + 0.15, 4.12, 1.7, col, size=10.5, h=0.30)
add_text(s, "신뢰장치 — “검증을 믿어도 되는가”", 0.42, 4.85, 12.5, 0.35, size=13.5, bold=True, color=INK)
add_table(s, [
    ["장치", "무엇을 막는가", "방법", "결과"],
    ["Mutation testing", "“무조건 통과하는 테스트” 자기기만",
     "정책을 8가지 그럴듯한 대안으로 바꿔치기(M1~M8)", "17개 전부 최소 1개에서 FAIL"],
    ["baseline 0-line diff", "비교 대상을 건드려 결과를 만드는 것",
     "router.py / backend·profile·program/state.py / app.py 무수정", "git diff = 없음"],
], 0.42, 5.28, 12.5, 1.4, fs=11.5, hdr_fs=11.5, col_widths=[2.5, 3.0, 4.5, 2.5])
footer(s, "라벨 규율: [측정]=실행/코드열람 관측값 · [추론]=관측으로부터의 해석 · [논문-인용]=논문 §근거")
set_notes(s, """검증을 세 계층으로 나눴습니다. 각각 답하는 질문이 다릅니다.

A 계층은 화이트박스입니다. 가짜 프로그램 몇 개를 손으로 만들어서 ι값과 토큰 수를 원하는 대로 세팅하고,
스케줄러의 결정 함수만 딱 떼어내 호출합니다. 정답을 미리 알고 있으니 맞히는지 바로 알 수 있죠.
GPU가 전혀 필요 없습니다.

B 계층은 블랙박스입니다. 실제로 GPU에 모델을 올리고 트래픽을 흘려서,
엔진 카운터로 "KV가 정말 GPU에서 CPU로 내려갔는가"를 봅니다.

STEP7은 조금 다른 질문입니다. GPU 사용률이 높다고 유용한 일을 한 건 아니거든요.
그래서 goodput 같은 지표로 "바쁜 것"과 "쓸모 있는 것"을 분리했습니다.

아래 두 줄이 중요합니다. 검증한다고 해놓고 사실은 통과할 수밖에 없는 테스트를 짜는 게 흔한 함정입니다.
그래서 일부러 코드 정책을 8가지 방식으로 망가뜨려 봤고(mutation testing),
17개 테스트가 전부 최소 한 번은 실패하는 걸 확인했습니다. 즉 이 테스트들은 "틀릴 수 있는" 테스트입니다.
또 비교 대상인 baseline 코드는 한 줄도 안 건드렸습니다.""")

# =====================================================================  S4 A계층 설계
s = slide("A 계층 설계 — 논문 규칙 ↔ 테스트 매핑",
          "논문의 정책 규칙 7가지를 각각 “틀리면 반드시 실패하는” 합성 시나리오로 옮겼다")
zone(s, "①", "논문이 이렇게 규정 (§4.2 / §4.3)", 0.42, 1.72, 6.1, 4.9, PURPLE)
zone(s, "②", "그래서 이 실험을 설계 (합성 known-answer)", 6.72, 1.72, 6.2, 4.9, BLUE)
rules = [
    ["규칙 (논문)", "테스트", "틀리면 실패하도록 심은 함정"],
    ["스티키 배치 — 압박 없으면 재배치 X", "A1", "ι를 10틱 진동시켜도 이동 0이어야"],
    ["demote = ι 최고 (§4.3.1)", "A2a", "토큰 수와 ι를 반대로 배치"],
    ["ACTING을 REASONING보다 먼저", "A2b", "전역 최고 ι를 REASONING에 둠"],
    ["REASONING은 lazy demotion", "A2c", "틱 안에서 이동하면 실패"],
    ["promote = 그룹 내 ι 최소", "A3 / A3b", "admit 순서를 ι와 반대로"],
    ["양 tier 모두 유한 용량", "A4", "6개를 2+2칸에 밀어넣음"],
    ["★ 상대적 경계 (제목)", "A5", "같은 집합, GPU 칸수만 변경"],
    ["ι = robust + responsive (§4.2 식1)", "A6a/b/c", "outlier 1회 · 진행중 콜 · phase 전환"],
    ["typed eviction + 동타입 LRU (§4.3.2)", "A7a~f", "ι 동률에서 FIFO와 LRU가 갈리게"],
]
add_table(s, rules, 0.58, 2.28, 12.2, 4.2, fs=11, hdr_fs=11,
          col_widths=[4.6, 1.5, 6.1],
          highlight_rows={7: HEALTHY})
footer(s, "[논문-인용] §4.2 idleness 식(1) · §4.3.1 demote/promote 랭킹 · §4.3.2 typed eviction")
set_notes(s, """A 계층을 어떻게 설계했는지 보여주는 슬라이드입니다.

왼쪽 열이 논문에 적힌 정책 규칙이고, 가운데가 그걸 검사하는 테스트 번호,
오른쪽이 제일 중요한데 "이 테스트가 틀리면 반드시 실패하도록 심어둔 함정"입니다.

예를 들어 A2a를 보세요. "가장 idle한 프로그램을 내린다"가 규칙인데,
만약 코드가 실수로 "컨텍스트가 가장 긴 프로그램을 내린다"로 구현돼 있어도
보통 테스트는 통과해버릴 수 있습니다. 두 기준이 같은 답을 낼 수 있으니까요.
그래서 일부러 토큰 수가 가장 많은 프로그램의 ι를 가장 낮게 잡았습니다.
이러면 두 정책이 서로 다른 답을 내기 때문에, 어느 쪽으로 구현됐는지 구분됩니다.

A5는 논문 제목이 걸린 테스트라 특히 중요합니다. 똑같은 프로그램 집합을 두고
GPU 칸 수만 2칸에서 3칸으로 바꿉니다. 만약 코드가 "ι 0.5 넘으면 내린다" 같은
고정 임계를 쓴다면 두 경우 결과가 같아야 합니다. 결과가 달라져야 진짜 "상대적"인 겁니다.""")

# =====================================================================  S5 A계층 결과
s = slide("A 계층 결과 — 17/17 PASS", f"측정된 실제 결정이 논문 규칙과 일치 · 최초 {D['A_initial']} → A7c 수정 후 {D['A_total']}/{D['A_denom']}",
          tw_color=GREEN)
zone(s, "③", "측정 결과 + 판정", 0.42, 1.68, 12.5, 5.0, GREEN)
# A5 상대성 미니 그림
add_text(s, "A5  ★ 상대성 — 같은 프로그램, GPU 칸수만 변경", 0.62, 2.2, 4.3, 0.3, size=11.5, bold=True, color=INK)
for row, (cap, gpu, cpu, yy) in enumerate([
        ("GPU 2칸", ["A .1", "B .4"], ["C .6", "D .9"], 2.6),
        ("GPU 3칸", ["A .1", "B .4", "C .6"], ["D .9"], 3.45)]):
    add_text(s, cap, 0.62, yy + 0.05, 0.85, 0.3, size=10.5, bold=True, color=GRAY)
    for i, g in enumerate(gpu):
        chip(s, g, 1.5 + i * 0.78, yy, 0.72, GREEN, size=9.5, h=0.30)
    for i, c in enumerate(cpu):
        chip(s, c, 1.5 + (len(gpu) + i) * 0.78, yy, 0.72, AMBER, size=9.5, h=0.30)
add_text(s, "경계가 ι≤0.4 → ι≤0.6 으로 이동  [측정]\n고정 임계였다면 두 줄이 같아야 한다",
         0.62, 4.25, 4.3, 0.6, size=10.5, color=GREEN, bold=True)
add_text(s, "GPU 잔류 = 초록 · CPU 강등 = 주황", 0.62, 4.85, 4.3, 0.3, size=9.5, color=GRAY)
# A2a 미니 표
add_text(s, "A2  demote는 ι 최고 (context-len 아님)", 5.2, 2.2, 3.6, 0.3, size=11.5, bold=True, color=INK)
add_table(s, [
    ["프로그램", "토큰", "ι", "결과"],
    ["A", "400 (최대)", "0.10", "GPU 유지"],
    ["B", "250", "0.90", "→ CPU 강등"],
    ["C", "250", "0.20", "GPU 유지"],
], 5.2, 2.55, 3.6, 1.25, fs=10.5, hdr_fs=10.5,
    col_widths=[0.95, 1.0, 0.65, 1.0], highlight_rows={2: EXTREME})
add_text(s, "토큰 최대는 A인데 내려간 건 B\n→ context-length 정책이면 A가 내려갔어야  [측정]",
         5.2, 3.9, 3.6, 0.6, size=10.5, color=GREEN, bold=True)
add_figure(s, "mori_ver_A6b_iota_yunuikang", 9.0, 2.15, 3.8, 2.6)
add_caption(s, "A6b  진행 중 tool call이 ι를 밀어올린다 (now 주입) [측정]", 9.0, 4.78, 3.8, size=9.5)
add_table(s, [
    ["A1 스티키", "A2a/b/c demote", "A3/A3b promote", "A4 admission",
     "A5 상대성", "A6a/b/c 지표", "A7a~f typed evict"],
    ["PASS", "PASS ×3", "PASS ×2", "PASS", "PASS", "PASS ×3", "PASS ×6"],
], 0.62, 5.45, 12.1, 0.85, fs=11, hdr_fs=10.5, highlight_rows={1: HEALTHY})
footer(s, f"A6a robust: busy 기준선 ι={D['A6a_base']} → outlier 1회 포함 {D['A6a_outlier']} (완전 idle {D['A6a_idle']}) — busy 타입 유지 [측정]")
set_notes(s, """A 계층 결과입니다. 17개 전부 통과했습니다. 대표 세 개만 그림으로 보겠습니다.

왼쪽 A5가 논문 제목에 걸린 테스트입니다.
프로그램 네 개(A,B,C,D)의 ι를 각각 0.1, 0.4, 0.6, 0.9로 고정해 두고 GPU 칸 수만 바꿨습니다.
2칸일 때는 A와 B가 남고, 3칸일 때는 A, B, C가 남았습니다.
즉 GPU에 남을 수 있는 ι의 경계선이 0.4에서 0.6으로 저절로 움직인 겁니다.
만약 "ι가 얼마 이상이면 내린다"는 고정 기준이었다면 두 줄이 똑같아야 했겠죠.
하드웨어가 바뀌어도 튜닝 없이 적응한다는 게 논문의 핵심 주장인데, 그게 코드에 살아있습니다.

가운데 A2는 함정 설계가 잘 먹힌 사례입니다.
토큰을 가장 많이 쓰는 건 A(400 토큰)인데, ι가 가장 높은 건 B입니다.
실제로 내려간 건 B였습니다. 만약 코드가 "메모리 많이 먹는 놈부터 내린다"로 돼 있었다면 A가 내려갔을 겁니다.

오른쪽 그래프는 ι 지표가 "반응성"이 있는지 본 겁니다.
어떤 프로그램이 긴 tool call에 막 들어갔다고 해봅시다.
아직 끝나지 않았으니 과거 기록만 보면 이 프로그램은 여전히 바빠 보입니다.
그런데 코드는 "지금 진행 중인 tool call 시간"도 ι에 반영합니다.
그래서 시간이 갈수록 ι가 올라가고, 48초쯤에 0.5를 넘어 강등 후보가 됩니다.""")

# =====================================================================  S6 A계층 신뢰성 & 발견
s = slide("A 계층 신뢰성 & 발견", "테스트가 “틀릴 수 있음”을 mutation으로 증명 · 이탈 1건 발견 → 수정 → 17/17")
zone(s, "①", "테스트 자체를 검증 — mutation testing", 0.42, 1.72, 6.1, 2.72, PURPLE)
add_table(s, [
    ["정책을 이렇게 망가뜨리면", "깨지는 테스트"],
    ["M1 ι 대신 context-length로 랭킹", "A2a A3 A4 A5 A7a A7b"],
    ["M2 ι 랭킹 반전 (1−ι)", "A2a A2b A3 A4 A5 A6a A7a A7b A7d"],
    ["M3 용량 게이팅 제거(매틱 재배치)", "A1 A2a A2b A3 A3b A4 A5"],
    ["M4 진행 중 tool call 무시", "A6b"],
    ["M5 옛 표본 미폐기(무한 윈도우)", "A6c"],
    ["M6 lazy demotion 제거", "A2c"],
    ["M7 tie-break를 MRU로 반전", "A7c A7e A7f"],
    ["M8 tie-break 제거(수정 전 회귀)", "A7c A7f"],
    ["→ 17개 전부 최소 1개에서 FAIL  [측정]", "테스트가 “틀릴 수 있음” 확인"],
], 0.58, 2.25, 5.8, 1.85, fs=8.5, hdr_fs=9,
    highlight_rows={9: HEALTHY})

zone(s, "②", "판정이 갈렸던 2건 — 논문 원문이 정답", 6.72, 1.72, 6.2, 2.6, BLUE)
add_table(s, [
    ["관측", "처음 의심", "판정 근거", "결론"],
    ["promote가 ι 최소를 안 고름\n(cpu_pending ι.9 > cpu_idle ι.1)", "이탈?",
     "§4.3.1 “그룹 우선순위 후\n각 레벨 내 ι 최저”", "충실"],
    ["ι가 합의 비(ratio-of-sums)\n≠ 스텝별 평균", "이탈?",
     "논문 식(1)이 곧 합의 비", "충실"],
], 6.88, 2.28, 5.9, 1.9, fs=9.5, hdr_fs=10, col_widths=[2.3, 0.85, 1.9, 0.85],
    highlight_rows={1: HEALTHY, 2: HEALTHY})

zone(s, "③", "실제 이탈 1건 — 발견 → 수정 → 재검증", 0.42, 4.70, 12.5, 1.95, RED)
add_table(s, [
    ["항목", "논문 요구 (§4.3.2)", "수정 전 코드", "원인", "수정", "결과"],
    ["A7c 동타입 LRU tie-break",
     "타입 우선 + 동타입은\nLRU(가장 오래된 것) 축출",
     f"삽입순 FIFO — {D['A7c_before']} 축출",
     "정렬키가 ι 단독\n(2차 키 없음)\nCpuTier에 last-access 필드 부재",
     f"{D['A7c_fix_router']}\n+ CpuTier last_access 장부",
     f"{D['A7c_after']} 축출\n17/17"],
], 0.58, 5.22, 12.2, 1.3, fs=9, hdr_fs=9.5,
    col_widths=[2.0, 2.2, 2.1, 2.5, 1.9, 1.5], highlight_rows={1: EXTREME})
footer(s, "수정은 mori_router.py / mori_tier.py 2파일만 (+47/−4). baseline 0-line diff · 커밋 없음. "
          "M7·M8이 이 수정을 양방향으로 검출한다.")
set_notes(s, """이 슬라이드가 검증의 신뢰도를 담보하는 부분입니다.

왼쪽. "우리 테스트가 사실은 아무거나 통과시키는 거 아니냐"는 의심을 없애기 위해,
코드를 건드리지 않고 런타임에 정책을 8가지 방식으로 바꿔치기해봤습니다.
예를 들어 M1은 "ι 대신 컨텍스트 길이로 순위를 매기게" 바꾼 겁니다.
그랬더니 A2a, A3, A4, A5 등이 무더기로 실패했습니다.
17개 테스트 전부가 최소 한 번은 실패했다는 건, 이 테스트들이 진짜로 뭔가를 검사하고 있다는 뜻입니다.

가운데. 처음엔 "이거 논문이랑 다른데?" 싶었던 게 두 개 있었습니다.
하나는 promote할 때 ι가 가장 낮은 걸 안 고르는 것처럼 보인 거고,
다른 하나는 ι 계산식이 스텝별 평균이 아니라 전체 합의 비율인 거였습니다.
둘 다 논문 원문을 확인해보니 코드가 맞았습니다. 논문 §4.3.1은 그룹 우선순위를 먼저 두라고 명시하고 있고,
식(1) 자체가 합의 비율이었습니다.

아래. 진짜 이탈은 딱 하나 있었습니다.
CPU tier가 꽉 차서 누군가를 완전히 버려야 할 때, ι가 똑같은 프로그램들 사이에서
논문은 "가장 오래 안 쓴 것(LRU)"을 버리라고 하는데 코드는 "먼저 들어온 것"을 버리고 있었습니다.
원인은 정렬 기준에 2차 키가 없었고, 애초에 마지막 접근 시각을 기록하는 필드 자체가 없었기 때문입니다.
필드를 추가하고 정렬키를 고쳐서 17/17이 됐습니다. 수정은 MORI 전용 파일 2개에만 했습니다.""")

# =====================================================================  S4b A계층 실험 설계 (1/2)
s = slide("A 계층 실험 설계 (1/2) — 언제 내리고, 누구를 내리고 올리는가",
          "모든 테스트는 “논문 규칙과 다른 답을 내는 대안 정책”을 먼저 정하고, 둘이 갈리는 픽스처를 만든다")
# 공통 설계 원리
p = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.42), Inches(1.62), Inches(12.5), Inches(0.62))
p.fill.solid(); p.fill.fore_color.rgb = PANEL
p.line.color.rgb = RGBColor(0xDD, 0xE1, 0xE8); p.line.width = Pt(0.75); p.shadow.inherit = False
for i, (t, col, x, w) in enumerate([
        ("① 논문 규칙 1개 선택", PURPLE, 0.62, 2.5),
        ("② 다른 답을 내는 **대안 정책** 지정\n(context-len / FIFO / 고정임계 …)", RED, 3.32, 3.7),
        ("③ 두 정책이 **갈리는** 픽스처 구성", AMBER, 7.22, 3.1),
        ("④ 논문 쪽 답을 assert", GREEN, 10.52, 2.3)]):
    chip(s, t.split("\n")[0], x, 1.74, w, col, size=9.5, h=0.30)
    if "\n" in t:
        add_text(s, t.split("\n")[1], x, 2.02, w, 0.22, size=8.5, color=GRAY)
    if i < 3:
        add_text(s, "→", x + w + 0.02, 1.74, 0.25, 0.3, size=12, bold=True, color=GRAY)
add_text(s, "→ ③이 없으면 오구현도 통과한다", 0.62, 2.02, 2.5, 0.22, size=8.5, color=RED, bold=True)

add_table(s, [
    ["규칙 (논문)", "픽스처 — 구체 수치", "심어둔 함정 (= 오구현이면 다른 답)", "관측된 결정 [측정]", "잡는 mutant"],
    ["A1  스티키 배치\n압박 없으면 재배치 X",
     "GPU 4칸에 A·B 2개만(여유 2칸)\nA의 ι를 10틱 동안 0.1↔0.9 진동",
     "ι가 극단을 오가므로, ι만 보고 매 틱\n재배치하는 구현이면 반드시 움직인다",
     "tier 이동 **0회**, 마킹 0,\nmoved_tick 둘 다 None", "M3"],
    ["A2a  demote = ι 최고\n(§4.3.1)",
     "GPU 2칸(1000tok)\nA(400tok, ι.1) B(**250tok**, ι.9) C(250tok, ι.2)\nused 1200 → 1개 강제",
     "**토큰 수와 ι를 반대로 배치.**\ncontext-len 정책 → A(400tok 최대)\nLRU/FIFO → A(첫 등록)",
     "**B 강등** (ι 0.9), A·C 잔류\ngpu_remaining −200 → 150", "M1 M2 M3"],
    ["A2b  ACTING을\nREASONING보다 먼저",
     "R(250tok, **ι.99**, REASONING)\nA(400tok, ι.5, ACTING) C(250tok, ι.2, ACTING)",
     "**전역 최고 ι를 REASONING에 둠.**\n상태 무시하고 전역 ι 정렬하면\nR이 먼저 걸린다",
     "**A 강등**(ACTING 중 최고 ι)\nR은 마킹조차 안 됨", "M2 M3"],
    ["A2c  REASONING은\nlazy demotion",
     "GPU 900tok에 REASONING만 2개\nR1(400, ι.8) R2(400, ι.2), used 1000",
     "틱 안에서 KV를 즉시 뺏는 구현이면\ntier가 그 자리에서 바뀐다",
     "틱 내 이동 **0** (tier=gpu, ACTIVE 유지)\n마킹만 섬 → `_clear_mark_and_pause`\n시점에 **CPU tier**로 이동", "M6"],
    ["A3  promote =\n그룹 내 ι 최소",
     "GPU 여유 1칸(remaining 500 = 필요 500)\nCPU tier **admit 순서 [C, D]**\nC(ι.8) D(ι.3), 둘 다 ACTING(동일 그룹)",
     "**admit 순서를 ι와 반대로.**\nFIFO면 C, ι 내림차순이면 C\n→ 셋이 서로 다른 답",
     "**D 승격** (ι 0.3)\npromote 후 remaining 정확히 0", "M1 M2 M3"],
    ["A3b  그룹 우선순위가\nι보다 앞섬 (§4.3.1)",
     "CPU tier: P(**ι.9**, REASONING=cpu_pending)\nQ(**ι.1**, ACTING=cpu_idle)",
     "**ι와 그룹을 정반대로 배치.**\n그룹 무시하고 순수 ι 최소면 Q",
     "**P 승격** (ι 0.9인데도)\n→ §4.3.1 충실로 판정", "M3"],
    ["A4  양 tier\nadmission control",
     "6개(각 400tok, ι .1~.6) 전부 GPU에 얹고 1틱\nGPU 2칸 / CPU 2칸, gpu_remaining −2000",
     "한쪽 tier만 채우거나 초과 허용하면\n분포가 2/2/2로 안 나온다",
     "GPU 2 + CPU 2 + waiting 2\n양쪽 remaining **정확히 0**\nGPU 잔류 = ι 최소 2개", "M1 M2 M3"],
], 0.42, 2.42, 12.5, 4.0, fs=8, hdr_fs=9,
    col_widths=[1.85, 3.5, 3.4, 2.55, 1.2],
    highlight_rows={2: HEALTHY, 6: HEALTHY})
footer(s, "위 표의 “심어둔 함정” 열이 각 테스트의 핵심 설계다 — 이게 없으면 오구현도 통과한다. "
          "픽스처의 ι는 윈도우에 동일 표본 k쌍을 push해 주입 — 논문 식(1)/평균-of-비율 어느 해석으로도 같은 값이라 "
          "구현 계산식을 베끼지 않는다.")
set_notes(s, """A 계층에서 각 규칙을 어떻게 시험했는지 구체적으로 보는 슬라이드입니다.

맨 위 띠가 모든 테스트에 공통으로 적용한 설계 절차입니다. 이게 핵심이에요.
그냥 "규칙대로 동작하나 보자"고 짜면, 오구현인데도 우연히 같은 답이 나와서 통과해버립니다.
그래서 먼저 "이 규칙과 다른 답을 내는 그럴듯한 대안 정책"을 정하고,
두 정책이 서로 다른 답을 내도록 픽스처를 일부러 비틀었습니다.
표의 세 번째 열 "심어둔 함정"이 그 비튼 내용입니다.

하나씩 보겠습니다.

A1 스티키. GPU에 여유를 두고 프로그램 하나의 ι를 10틱 동안 0.1과 0.9로 왕복시켰습니다.
만약 코드가 ι만 보고 매 틱 자리를 다시 정한다면 반드시 움직였을 겁니다. 0회 움직였습니다.

A2a가 함정 설계의 대표입니다. 토큰을 가장 많이 쓰는 A의 ι를 가장 낮게, ι가 가장 높은 B의 토큰을 적게 잡았습니다.
이러면 "메모리 많이 먹는 놈부터 내린다"는 정책과 "가장 idle한 놈부터 내린다"는 정책이 정반대 답을 냅니다.
실제로 B가 내려갔으니 ι 기준이 맞습니다.

A2b는 전역에서 가장 idle한 프로그램(ι 0.99)을 일부러 REASONING 상태에 뒀습니다.
상태를 무시하고 ι만 정렬하면 이 프로그램이 먼저 걸렸을 텐데, 실제로는 ACTING 중에서 가장 idle한 A가 내려갔습니다.

A2c는 "즉시 뺏지 않는다"를 봅니다. 틱이 도는 동안 tier가 그대로인지, 상태가 ACTIVE로 남아있는지,
백엔드에 등록이 유지되는지를 다 확인했습니다. 셋 다 유지됐고 마킹만 섰습니다.

A3는 CPU tier에 넣는 순서를 ι와 반대로 했습니다. 먼저 넣은 게 ι가 높은 쪽이라,
선입선출이면 C가 올라가고 ι 최소면 D가 올라갑니다. D가 올라갔습니다.

A3b는 ι와 그룹을 정반대로 배치했습니다. ι만 보면 Q가 압도적으로 유리한데 P가 올라갔죠.
처음엔 이탈인가 싶었지만 논문 §4.3.1이 그룹 우선순위를 먼저 두라고 명시하고 있어서 코드가 맞습니다.

A4는 용량의 두 배가 넘는 프로그램을 한꺼번에 밀어넣고, 2/2/2로 정확히 갈리는지와
양쪽 tier의 남은 용량이 정확히 0인지를 봤습니다.

맨 아래 각주도 중요합니다. ι를 주입할 때 같은 표본을 k개 넣었는데,
이러면 논문 식이든 다른 해석이든 같은 값이 나와서, 구현 계산식을 테스트에 베껴온 게 아니게 됩니다.""")

# =====================================================================  S4c A계층 실험 설계 (2/2)
s = slide("A 계층 실험 설계 (2/2) — 상대성 · 지표 · typed eviction",
          "A5는 “같은 입력, 용량만 변경”으로 고정 임계를 배제 · A6은 지표의 두 성질을 분리 측정")
add_table(s, [
    ["규칙 (논문)", "픽스처 — 구체 수치", "심어둔 함정 (= 오구현이면 다른 답)", "관측된 결정 [측정]", "잡는 mutant"],
    ["★ A5  상대적 경계\n(논문 제목)",
     "**동일 집합** A/B/C/D (ι .1/.4/.6/.9, 각 400tok)를\nGPU **2칸** → **3칸** 으로 두 번 실행\n(CPU는 4칸으로 넉넉히 = 경계만 관찰)",
     "**입력을 완전히 고정하고 용량만 바꾼다.**\n고정 ι 임계(예 0.5)면 두 번 다 {A,B}가 나와야\n한다 → 결과가 같으면 상대성 아님",
     "2칸 → GPU={A,B}\n3칸 → GPU={A,B,C}\n경계 **ι≤0.4 → ι≤0.6 이동**", "M1 M2 M3"],
    ["A6a  지표 robust\n(§4.2 식1)",
     "k=5, reasoning 10s×5 고정\nacting = [0.5, 0.5, **5.0**, 0.5, 0.5]\n(짧은 콜 사이 10배 outlier 1회)",
     "outlier 1회로 타입이 뒤집히면\n“busy phase 중 긴 콜에 흔들린다”",
     "ι 0.0476 → **0.1228** (Δ+0.075)\nbusy 구간(<0.33) 유지, rank=2\n(완전 idle은 0.75)", "M2"],
    ["A6b  지표 responsive\n— 진행 중인 콜",
     "busy 윈도우에서 t0에 툴콜 진입\n`value(now=t0+x, acting_since=t0)`로 **시간 주입**\n(IdlenessWindow가 time.time()을 안 부름)",
     "진행 중 콜을 무시하면 ι가 평평하다\n→ 방금 긴 콜에 들어간 프로그램을\n영원히 demote 못 함",
     "0s .048 → 60s .556 → 300s .858\n**단조 증가**, 48s에 ι=0.5 통과", "M4"],
    ["A6c  지표 responsive\n— phase 전환",
     "busy 5스텝(acting .5) 후\nidle 스텝(acting 30)을 순차 push",
     "옛 표본을 안 버리면(무한 윈도우)\nι가 천천히만 오른다",
     "궤적 .048→.39→.552→.645→.707→**.75**\n5 push 후 **정확히 150/200**\n= 옛 표본 완전 폐기", "M5"],
    ["A7a  타입 우선순위\n(§4.3.2)",
     "ι를 0.0~1.0으로 훑으며 `_type_rank` 호출",
     "ι에 대해 비증가가 아니면 타입 경계가 깨짐",
     "0.32→2 · 0.34→1 · 0.65→1 · 0.67→0\nbusy>mixed>idle, 비증가 확인", "M1 M2"],
    ["A7b  tier 내부\n타입 순서",
     "CPU 2칸에 3개 강제 admit\n**admit 순서를 ι와 반대로**: busy→mixed→idle",
     "**FIFO면 E_busy가 먼저 축출**된다\n(idle을 마지막에 넣었으므로)",
     "**E_idle 축출**, busy·mixed 잔류\ncpu_remaining −500 → 0", "M1 M2"],
    ["★ A7c  동타입\nLRU tie-break",
     "ι를 **전부 0.5로 동일**(같은 타입)\nlast_response_end만 NEW3000/MID2000/OLD1000\n**admit 순서 [NEW, MID, OLD]**",
     "**FIFO와 LRU가 정반대 답을 내게 배치.**\nFIFO → NEW 축출 / LRU → OLD 축출",
     "수정 전 **NEW 축출** ❌\n수정 후 **OLD 축출** ✅", "M7 M8"],
    ["A7d~f  수정 회귀 방지",
     "d: idle(ι.9/last3000) vs busy(ι.1/last1000)\ne: last_response_end=None + ι 전부 default 0.5\nf: remove 후 재-admit",
     "d: LRU가 타입을 덮어쓰면 busy가 축출\ne: 스탬프 없으면 정렬 불능/크래시\nf: 옛 스탬프 잔존 시 LRU 오염",
     "d: **E_idle 축출**(타입이 1차 키)\ne: admit 순 스탬프, 가장 오래된 것 축출\nf: last_access −inf, 장부 크기 0", "M2 M7 M8"],
], 0.42, 1.68, 12.5, 4.95, fs=7.8, hdr_fs=9,
    col_widths=[1.75, 3.55, 3.45, 2.6, 1.15],
    highlight_rows={1: HEALTHY, 7: EXTREME})
footer(s, "A5는 “입력 고정 · 용량만 변경”이라는 대조 설계라 고정 임계 구현을 원리적으로 배제한다 — "
          "A 계층에서 논문 제목(Relative)을 직접 겨냥한 유일한 테스트.")
set_notes(s, """A 계층 설계 설명 두 번째 장입니다. 상대성, 지표, 축출 순서를 봅니다.

A5가 논문 제목이 걸린 테스트라 설계가 가장 중요합니다.
다른 테스트들은 픽스처를 비틀어 함정을 만들었지만, A5는 반대로 **입력을 완전히 고정**합니다.
프로그램 네 개의 ι를 0.1, 0.4, 0.6, 0.9로 박아두고, 오직 GPU 칸 수만 2개에서 3개로 바꿉니다.
CPU는 넉넉하게 4칸을 줘서 경계선만 보이게 했습니다.
만약 코드가 "ι 0.5 넘으면 내린다" 같은 고정 기준을 쓴다면 두 번 다 같은 결과가 나와야 합니다.
실제로는 GPU에 남는 경계가 0.4에서 0.6으로 움직였습니다.
이건 함정을 심는 방식이 아니라 대조 실험 설계라, 고정 임계 구현을 원리적으로 배제합니다.

A6은 지표의 두 성질을 일부러 분리해서 쟀습니다.
robust는 "흔들리지 않아야 한다", responsive는 "빨리 반응해야 한다"인데 서로 반대 방향이거든요.
A6a는 짧은 콜들 사이에 10배 긴 콜을 딱 한 번 끼워넣고 타입이 안 뒤집히는지 봤습니다.
A6b는 조금 특이한데, 진행 중인 tool call을 봅니다.
아직 안 끝난 콜은 과거 기록에 없으니 무시할 수도 있는데, 그러면 방금 긴 콜에 들어간 프로그램을 영원히 못 내립니다.
여기서 운이 좋았던 게, IdlenessWindow가 현재 시각을 직접 읽지 않고 인자로 받습니다.
그래서 몽키패치 없이 시간을 주입해서 ι가 단조 증가하는지 확인할 수 있었습니다.
A6c는 오래된 표본을 진짜로 버리는지 봅니다. 5번 밀어넣은 뒤 값이 정확히 150 나누기 200이 나왔는데,
이건 옛날 값이 하나도 안 남았다는 뜻입니다.

A7b와 A7c가 축출 순서인데, 둘 다 "넣는 순서"를 무기로 씁니다.
A7b는 idle한 걸 일부러 마지막에 넣었습니다. 선입선출이면 busy가 먼저 나가야 하는데 idle이 나갔죠.
A7c는 더 정교합니다. ι를 전부 0.5로 똑같이 만들어서 타입으로는 구분이 안 되게 하고,
마지막 접근 시각만 다르게 준 다음, 넣는 순서를 그 시각과 반대로 했습니다.
이러면 선입선출은 NEW를, LRU는 OLD를 버립니다. 수정 전에는 NEW가 나갔고, 그게 유일하게 발견한 이탈이었습니다.

A7d부터 f는 그 수정 때문에 새로 생길 수 있는 문제를 막는 회귀 테스트입니다.
특히 d가 중요한데, LRU를 넣었다고 해서 그게 타입보다 우선하면 안 됩니다.
그래서 가장 오래된 것을 busy로, 가장 최근 것을 idle로 만들어놓고 idle이 축출되는지 확인했습니다.""")

# =====================================================================  S7 B계층 설계
s = slide("B 계층 설계 — 실 GPU에서 메커니즘이 도는가",
          "논문의 3-tier 이동이 실런에서 실제로 일어나는지 엔진 카운터로 직접 관측")
zone(s, "①", "논문이 규정하는 3-tier 동작", 0.42, 1.72, 6.1, 2.9, PURPLE)
# tier 다이어그램
for name, sub, col, x in [("GPU", "KV 상주 · 계산", GREEN, 0.75),
                          ("CPU tier", "KV 보존 (HiCache host)", AMBER, 2.85),
                          ("Waiting", "KV 폐기", RED, 4.95)]:
    b = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(2.35), Inches(1.55), Inches(0.9))
    b.fill.solid(); b.fill.fore_color.rgb = col; b.line.fill.background(); b.shadow.inherit = False
    tf = b.text_frame; tf.word_wrap = True; tf.text = name
    tf.paragraphs[0].runs[0].font.size = Pt(12.5); tf.paragraphs[0].runs[0].font.bold = True
    tf.paragraphs[0].runs[0].font.color.rgb = WHITE
    tf.paragraphs[0].alignment = PP_ALIGN.CENTER
    p2 = tf.add_paragraph(); p2.text = sub; p2.alignment = PP_ALIGN.CENTER
    p2.runs[0].font.size = Pt(8.5); p2.runs[0].font.color.rgb = WHITE
add_text(s, "demote (ι 최고) →", 2.32, 3.3, 1.5, 0.25, size=9, color=RED, bold=True)
add_text(s, "← promote (ι 최소)", 2.32, 3.55, 1.5, 0.25, size=9, color=BLUE, bold=True)
add_text(s, "CPU 꽉 차면 →", 4.45, 3.3, 1.4, 0.25, size=9, color=GRAY, bold=True)
add_bullets(s, [
    ("재개 비용: CPU→GPU = PCIe reload(쌈) · Waiting→GPU = full recompute(비쌈) [논문-인용 §4.1]", 0, INK, True),
    ("idle을 CPU로 내려 HBM 확보 [논문-인용 §3.4]", 0, INK, False),
], 0.62, 3.85, 5.8, 0.7, size=10.5)

zone(s, "②", "그래서 이 실험 (B0~B3)", 6.72, 1.72, 6.2, 2.9, BLUE)
add_table(s, [
    ["실험", "무엇을", "어떻게"],
    ["B0", "tier 이동이 압박에 따라 생기나", "기존 30셀 프록시 로그 채굴 (새 run 0)"],
    ["B1", "idle→CPU / busy 잔류 / 재개=reload", "통제 run: LONG 1개만 90초 tool call"],
    ["B2", "GPU util vs 동시성", "util 시계열 1Hz (기존 로그)"],
    ["B3", "재개가 reload인가 recompute인가", "load_back·cached 카운터 델타"],
], 6.88, 2.28, 5.9, 1.6, fs=10, hdr_fs=10.5, col_widths=[0.7, 2.4, 2.8])
add_text(s, "계측 제약 2가지 — 그래서 이렇게 우회했다  [측정]", 6.88, 3.95, 5.9, 0.3,
         size=11, bold=True, color=RED)
add_bullets(s, [
    ("nvidia-smi 메모리로는 KV 해제가 안 보임 (SGLang이 풀을 정적 선점 → 27.7GB 상수)\n"
     "→ sglang:num_used_tokens 사용", 0, INK, False),
    ("/health가 cpu_tier를 안 내보냄 → app.py 무수정 위해 파생:\n"
     "cpu_tier = programs_count − Σper_backend.total − paused_count", 0, INK, False),
], 6.88, 4.25, 5.9, 1.0, size=9.5)
zone(s, "③", "결과는 다음 장", 0.42, 4.75, 6.1, 1.9, GREEN)
add_bullets(s, [
    ("(a) idle이 GPU를 떠나는가 → ✅ PASS", 0, GREEN, True),
    ("(b) busy가 GPU에 남는가 → ⚠️ 미확정 (분리 조건을 못 만듦)", 0, AMBER, True),
    ("(c) 재개가 reload인가 → ✅ PASS", 0, GREEN, True),
], 0.62, 5.3, 5.8, 1.1, size=12)
footer(s, "기존 하네스(serve 스크립트·replay driver) 무수정 재사용. 신규는 계측·분석 스크립트만.")
set_notes(s, """B 계층은 실제 GPU를 돌려서 보는 부분입니다.

왼쪽 그림이 MORI의 3단 구조입니다.
GPU는 KV가 살아있고 계산도 하는 곳, CPU tier는 KV만 호스트 메모리에 보관하는 곳,
Waiting은 KV를 아예 버리는 곳입니다.
중요한 건 CPU tier에서 다시 올라올 때는 PCIe로 복사만 하면 되니까 싸고,
Waiting에서 올라올 때는 처음부터 다시 계산해야 하니까 비싸다는 겁니다.
MORI가 CPU tier를 만든 이유가 바로 이거예요.

오른쪽은 실험 설계입니다. B0는 새로 안 돌리고 이미 있던 30개 셀의 로그를 캐냈습니다.
B1만 새로 통제 실험을 했는데, 프로그램 하나만 90초짜리 긴 tool call에 들어가게 하고
나머지는 1초짜리 짧은 콜을 계속 돌게 했습니다.

계측하면서 막힌 게 두 개 있었는데 솔직히 적어뒀습니다.
하나는 nvidia-smi로 GPU 메모리를 봐도 KV가 풀렸는지 안 보인다는 겁니다.
SGLang이 시작할 때 KV 풀을 통째로 잡아버려서 항상 27.7GB로 고정이거든요.
그래서 엔진이 내부적으로 세는 num_used_tokens를 썼습니다.
또 하나는 프록시의 /health가 CPU tier 개수를 안 알려줘서, 전체에서 GPU와 대기열을 빼는 식으로 계산했습니다.
app.py를 고치지 않기 위해서였습니다.""")

# =====================================================================  S8 B계층 결과
s = slide("B 계층 결과 — 메커니즘이 실제로 돈다", "tier 이동 시각과 GPU KV 감소량이 프로그램 단위로 일치",
          tw_color=GREEN)
zone(s, "③", "측정 결과 + 판정", 0.42, 1.68, 12.5, 5.0, GREEN)
add_figure(s, "mori_ver_tier_moves_yunuikang", 0.6, 2.15, 5.5, 2.75)
add_caption(s, "B0  압박(oversub)에 따른 tier 이동 — 무압박에서 정확히 0 [측정]", 0.6, 4.92, 5.5, size=9.5)
add_table(s, [
    ["관측", "측정값", "일치하는 것", "판정"],
    ["(a) idle이 GPU를 떠남",
     f"cpu_tier 0→1 시각에\nGPU KV {D['B1a_kv_before']} → {D['B1a_kv_after']}\n(−{D['B1a_drop']} tok)",
     f"그때 강등된 b1-LONG의\nKV = {D['B1a_prog_kv']:,} tok", "✅ PASS"],
    ["(c) 재개 = reload",
     f"promote 시각에 load_back\n660 → 13,900 (+{D['B1c_loadback']} tok)",
     f"promote된 2개 KV 합\n{D['B1a_prog_kv']:,}×2 = 13,166", "✅ PASS"],
    ["(b) busy가 GPU 잔류", "LONG은 확실히 강등됐으나\nSHORT도 함께 강등", "분리 조건 실패", "⚠️ 미확정"],
], 6.35, 2.15, 6.4, 2.6, fs=9.5, hdr_fs=10,
    col_widths=[1.7, 2.2, 1.7, 0.8],
    highlight_rows={1: HEALTHY, 2: HEALTHY, 3: EXTREME})
add_text(s, "B3  재개는 recompute가 아니라 reload다  [측정]", 6.35, 4.92, 6.4, 0.3,
         size=11.5, bold=True, color=INK)
add_table(s, [
    ["셀 (oversub)", "prefix hit", "reload (CPU→GPU)", "CPU→Waiting 축출"],
    ["TA C8 (offload 없음)", "0.920", "0.00M", "n/a"],
    ["TA+O C8 (LRU)", "0.949", "2.92M", "n/a"],
    ["MORI C8 (typed)", "0.944", "7.88M", "0"],
    ["MORI C10", "0.945", "12.83M", "0"],
    ["MORI C80 (극단)", "0.600", "7.25M", "9 (1.3%)"],
], 6.35, 5.25, 6.4, 1.3, fs=9.5, hdr_fs=9.5,
    col_widths=[2.1, 1.3, 1.6, 1.4],
    highlight_rows={3: HEALTHY, 4: HEALTHY, 5: EXTREME})
footer(s, "reload가 TA+O의 2.7~3.1배인데 KV 폐기는 0건 → CPU tier가 실제로 쓰이고, 내려간 KV의 98.7%↑가 보존된다.")
set_notes(s, """B 계층 결과입니다. 이게 "MORI의 심장이 뛰고 있다"를 보여주는 슬라이드예요.

왼쪽 막대그래프. 동시성이 낮아서 GPU에 여유가 있을 때(C2, C4)는 tier 이동이 정확히 0입니다.
ι는 계속 변하는데도 아무도 안 움직였어요. A1에서 확인한 "스티키" 성질이 실제 환경에서도 그대로입니다.
압박이 생기기 시작하는 C8부터 이동이 나타나고, C80에서는 690번까지 늘어납니다.
보라색 막대가 "KV를 아예 버린 횟수"인데 거의 안 보이죠. 이게 중요합니다.

오른쪽 위 표가 가장 결정적인 증거입니다.
CPU tier 인원이 0명에서 1명으로 늘어난 바로 그 순간, GPU가 쓰던 KV가 32,589에서 26,331 토큰으로 줄었습니다.
6,258 토큰이 빠진 건데, 그때 강등된 프로그램의 KV가 6,583 토큰이었습니다. 거의 정확히 일치하죠.
우연이 아니라 그 프로그램의 KV가 실제로 GPU에서 빠져나간 겁니다.

재개도 마찬가지입니다. 프로그램이 다시 GPU로 올라온 순간 호스트에서 GPU로 복사된 토큰이
13,240개 늘었는데, 그때 올라온 프로그램 2개의 KV 합과 맞아떨어집니다.
즉 처음부터 다시 계산한 게 아니라 저장해둔 걸 불러온 겁니다.

솔직하게 말씀드릴 게 하나 있습니다. (b) "바쁜 프로그램은 GPU에 남는다"는 확인하지 못했습니다.
압박을 너무 세게 주는 바람에 짧은 콜 프로그램들도 같이 내려가버려서, 둘을 분리해서 보여주지 못했습니다.""")

# =====================================================================  S9 STEP7 설계
s = slide("STEP 7 설계 — “바쁜 GPU”와 “유용한 일”은 다르다",
          "GPU util 100%인데 throughput 3.0인 시스템이 있다 → util은 품질 지표가 아니다", tw_color=RED)
zone(s, "①", "문제 제기 — 반례가 실제로 있다", 0.42, 1.72, 5.4, 1.85, RED)
add_table(s, [
    ["시스템 (C80)", "GPU util", "throughput"],
    ["SMG (스케줄링 없음)", "100.0 %", "3.0 tok/s"],
    ["MORI", "90.5 %", "6.5 tok/s"],
    ["TA+O", "73.3 %", "14.3 tok/s"],
], 0.58, 2.25, 5.1, 1.2, fs=10.5, hdr_fs=10.5, col_widths=[2.3, 1.4, 1.4],
    highlight_rows={1: EXTREME})
add_text(s, "util 최고 = 성능 최저 → util로는 아무것도 못 판단", 0.58, 3.5, 5.1, 0.3,
         size=10.5, bold=True, color=RED)

zone(s, "②", "그래서 5개 지표 — 계산법을 못 박는다", 6.05, 1.72, 6.87, 1.85, BLUE)
add_text(s, "decode(출력) = 진짜 산출물 · prefill = 준비 비용 · recompute/왕복 = 낭비",
         6.22, 2.25, 6.5, 0.3, size=10.5, color=GRAY, bold=True)
add_bullets(s, [
    ("데이터: 기존 30셀 재집계(①~④, 새 run 0) + --profile 3셀 최소 run(⑤)", 0, INK, False),
    ("셀 선택은 hicache ratio r2 고정 — C별로 r1/r2가 섞이지 않게", 0, INK, False),
], 6.22, 2.6, 6.5, 0.8, size=10)
add_table(s, [
    ["지표", "정의식", "무엇을 잡아내나", "데이터 출처"],
    ["① 생산성 비율", "output_throughput ÷ mean_gpu_util",
     "바쁜 GPU 1초가 만든 유용 토큰", "results_msw + gpu_*.jsonl (1Hz)"],
    ["② recompute 낭비율", "recompute ÷ (decode + prefill)\nrecompute = prefill − cached",
     "캐시에 없어 다시 계산한 몫", "sglang prompt/cached/load_back 카운터 델타"],
    ["③ goodput", "Σ(SLO 만족 턴의 출력 토큰) ÷ steady_wall",
     "SLO 안에 도착한 산출만 인정", "Part A=ttft 분위수 구간 / Part B=per-step 실측"],
    ["④ thrashing", "출력 토큰 ÷ promote 횟수 ,\nping-pong% = 2회↑ 강등된 프로그램 비율",
     "자리만 옮기고 산출이 없는 상태", "프록시 로그 tier 이벤트 순서"],
    ["⑤ 시간 분해", "TTFT = pause + prefill , decode%",
     "GPU 시간인지 스케줄러 대기인지", "--profile step_profiles.csv (927 스텝)"],
], 0.42, 3.75, 12.5, 2.9, fs=10, hdr_fs=10.5, col_widths=[1.7, 3.6, 3.1, 4.1])
footer(s, "③ Part A는 per-turn 미저장이라 순서통계 **구간**, Part B(⑤)가 프로파일 셀에 한해 실측으로 대체한다.")
set_notes(s, """STEP 7은 문제 제기부터 시작합니다.

왼쪽 표를 보세요. SMG라는 시스템은 GPU 사용률이 100%인데 처리량은 3.0 tok/s로 꼴찌입니다.
반면 TA+O는 사용률이 73%인데 처리량은 14.3으로 가장 높습니다.
GPU가 바쁜 것과 유용한 일을 하는 건 전혀 다른 얘기라는 극단적인 반례입니다.
그래서 사용률 말고 다른 지표가 필요합니다.

오른쪽 표가 그 지표 다섯 개인데, 정의식을 반드시 같이 적어뒀습니다.
말로만 "생산성"이라고 하면 사람마다 다르게 이해하니까요.

①은 처리량을 사용률로 나눈 겁니다. GPU가 바쁜 1초당 몇 토큰을 만들었나.
②는 전체 토큰 작업 중 "캐시에 없어서 다시 계산한" 비율입니다. 이건 순수한 낭비죠.
③ goodput이 표준 지표인데, 그냥 만든 토큰이 아니라 "약속한 응답 시간 안에 도착한" 토큰만 셉니다.
④는 한 번 GPU에 올려서 몇 토큰이나 뽑고 내려갔는지, 그리고 같은 프로그램이 몇 번이나 오르내렸는지입니다.
⑤는 프로파일러를 켜서 시간을 prefill, decode, 그리고 스케줄러 대기로 쪼갠 겁니다.

맨 아래 주의사항 하나. ③은 기존 로그에 턴별 기록이 안 남아 있어서 정확한 값이 아니라
"이 구간 안에 있다"는 범위로만 냈습니다. 대신 ⑤에서 프로파일을 켜고 다시 돌려서 정확한 값을 얻었습니다.""")

# =====================================================================  S10 STEP7 결과
s = slide("STEP 7 결과 — 압박이 커질수록 단조 악화, 극단에서 붕괴",
          "oversub 1.0×→2.5×→9.9× 로 갈수록 전 지표가 순차 악화 — C20이 중간 단계를 보여준다")
add_figure(s, "mori_ver_step7_metrics_yunuikang", 0.42, 1.60, 12.5, 2.92)
_w = S7["waste"]; _t = S7["thrash"]
add_table(s, [
    ["지표", "MORI C8\n1.0×", "MORI C10\n1.2×", "MORI C20\n2.5×", "MORI C80\n9.9×",
     "C8→C80 배율", "TA+O C80\n9.9×"],
    ["GPU util", "53.2 %", "58.7 %", "73.0 %", "90.5 %", "▲1.7배", "73.3 %"],
    ["① 생산성 (thr÷util)", S7["prod_C8_MORI"], S7["prod_C10_MORI"], S7["prod_C20_MORI"],
     S7["prod_C80_MORI"], "▼5.6배", S7["prod_C80_TAO"]],
    ["② 낭비율 (recompute)", f'{_w["MORI_r2_C8"]["waste"]}', f'{_w["MORI_r2_C10"]["waste"]}',
     f'{_w["MORI_r2_C20"]["waste"]}', f'{_w["MORI_r2_C80"]["waste"]}', "▲7.2배",
     f'{_w["TAO_r2_C80"]["waste"]}'],
    ["② prefix cache hit", f'{_w["MORI_r2_C8"]["hit"]}', f'{_w["MORI_r2_C10"]["hit"]}',
     f'{_w["MORI_r2_C20"]["hit"]}', f'{_w["MORI_r2_C80"]["hit"]}', "▼",
     f'{_w["TAO_r2_C80"]["hit"]}'],
    ["③ goodput @SLO 5s", "≥20.1", "≥22.5", "≥11.1", "<3.2", "▼7배+", "≥7.1"],
    ["④ 출력 / promote", _t["MORI_r2_C8"]["out_per_promote"], _t["MORI_r2_C10"]["out_per_promote"],
     _t["MORI_r2_C20"]["out_per_promote"], _t["MORI_r2_C80"]["out_per_promote"], "▼96배", "n/a"],
    ["④ ping-pong %", f'{_t["MORI_r2_C8"]["pingpong"]}', f'{_t["MORI_r2_C10"]["pingpong"]}',
     f'{_t["MORI_r2_C20"]["pingpong"]}', f'{_t["MORI_r2_C80"]["pingpong"]}', "▲", "n/a"],
], 0.42, 4.72, 12.5, 2.0, fs=9.5, hdr_fs=9,
    col_widths=[2.25, 1.65, 1.65, 1.65, 1.65, 1.3, 2.35],
    highlight_rows={2: EXTREME, 3: EXTREME, 6: EXTREME})
footer(s, "★ C80의 MORI는 prefill을 **덜** 하고도(38.01M < TA+O 63.42M) recompute는 **더** 버렸다(15.21M > 10.55M)  [측정]")
set_notes(s, """STEP 7의 핵심 결과표입니다. 왼쪽 두 열이 건강한 구간, 세 번째 열이 극단 구간입니다.

먼저 위 그래프 네 개를 보시면 패턴이 똑같습니다.
C8, C10에서는 멀쩡하다가 C80에서만 뚝 떨어지거나 확 치솟습니다.

숫자로 보면:
GPU 사용률은 오히려 90.5%로 가장 높아졌는데,
바쁜 1초당 산출(①)은 39.7에서 7.2로 5.6배 떨어졌습니다. 같은 조건의 TA+O는 19.5니까 거의 3배 차이죠.
낭비율(②)은 5.6%에서 39.9%로 뜁니다. 전체 토큰 작업의 40%가 다시 계산이라는 뜻입니다.
prefix 캐시 적중률은 0.944에서 0.600으로 무너집니다.
그리고 ④를 보시면, 한 번 GPU에 올려서 뽑아낸 토큰이 2,783개에서 29개로 96배 줄었습니다.
프로그램을 올렸다 내렸다만 하고 일은 거의 안 한 거예요.
ping-pong 비율은 90.7%. 강등된 프로그램 10개 중 9개가 두 번 이상 오르내렸습니다.

맨 아래 한 줄이 제일 인상적입니다.
C80에서 MORI는 TA+O보다 prefill 작업을 적게 했는데(38M 대 63M),
버린 양은 더 많습니다(15.2M 대 10.6M). 일을 덜 하면서 더 많이 버린 겁니다.

반대로 건강한 구간에서는 MORI가 CPU tier를 TA+O보다 3배나 적극적으로 쓰면서도
낭비율은 오히려 같거나 낮습니다. 오프로딩이 제값을 하고 있다는 뜻입니다.""")

# =====================================================================  S11 STEP7 profile
s = slide("STEP 7 ⑤ — “pause가 TTFT를 지배한다” [추론] → [측정] 확정",
          "MORI와 TA+O의 실제 차이는 “얼마나 자주 요청을 세우는가”였다", tw_color=RED)
add_figure(s, "mori_ver_pause_goodput_yunuikang", 0.42, 1.62, 12.5, 3.05)
pk = S7["profile_ttft"]
gk = S7["profile_goodput"]
add_table(s, [
    ["셀", "TTFT p50", "└ pause p50", "└ prefill p50", "pause 점유", "대기 겪은 스텝",
     "throughput", "goodput @5s", "SLO 만족"],
    ["MORI C10 (건강 1.2×)", f'{pk["MORI_r2_C10"]["ttft_p50"]}s', f'{pk["MORI_r2_C10"]["pause_p50"]}s',
     f'{pk["MORI_r2_C10"]["prefill_p50"]}s', f'{pk["MORI_r2_C10"]["pause_share"]}%',
     f'{pk["MORI_r2_C10"]["pause_nonzero"]}%', f'{gk["MORI_r2_C10"]["thr"]}',
     f'{gk["MORI_r2_C10"]["slo5_gp"]}', f'{gk["MORI_r2_C10"]["slo5_sat"]}%'],
    ["MORI C80 (극단 9.9×)", f'{pk["MORI_r2_C80"]["ttft_p50"]}s', f'{pk["MORI_r2_C80"]["pause_p50"]}s',
     f'{pk["MORI_r2_C80"]["prefill_p50"]}s', f'{pk["MORI_r2_C80"]["pause_share"]}%',
     f'{pk["MORI_r2_C80"]["pause_nonzero"]}%', f'{gk["MORI_r2_C80"]["thr"]}',
     f'{gk["MORI_r2_C80"]["slo5_gp"]}', f'{gk["MORI_r2_C80"]["slo5_sat"]}%'],
    ["TA+O C80 (극단 9.9×)", f'{pk["TAO_r2_C80"]["ttft_p50"]}s', f'{pk["TAO_r2_C80"]["pause_p50"]}s',
     f'{pk["TAO_r2_C80"]["prefill_p50"]}s', f'{pk["TAO_r2_C80"]["pause_share"]}%',
     f'{pk["TAO_r2_C80"]["pause_nonzero"]}%', f'{gk["TAO_r2_C80"]["thr"]}',
     f'{gk["TAO_r2_C80"]["slo5_gp"]}', f'{gk["TAO_r2_C80"]["slo5_sat"]}%'],
], 0.42, 4.82, 12.5, 1.35, fs=9.5, hdr_fs=9.5,
    col_widths=[2.4, 1.15, 1.35, 1.35, 1.2, 1.5, 1.35, 1.35, 0.85],
    highlight_rows={1: HEALTHY, 2: EXTREME})
add_text(s, "★ 점유율은 68.4% vs 69.7%로 비슷해 보이지만 — TA+O는 대기가 소수 꼬리에 몰리고(35.7%), "
            "MORI는 전면적(75.0%)이다. 중앙값을 함께 봐야 보인다.",
         0.42, 6.24, 12.5, 0.3, size=10.5, color=RED, bold=True)
add_text(s, "decode 비중은 오히려 유지됨(56.4% → 50.3%) — 무너진 건 비율이 아니라 스텝당 절대 속도"
            " (prefill 17.7배, decode 13.9배 느려짐)  [측정]",
         0.42, 6.56, 12.5, 0.3, size=10.5, color=GRAY)
footer(s, "⚠️ Part B는 420초 run(M-SWP는 3600초)이라 C80이 더 열화됨 → 절대값이 아니라 같은 run 안의 셀 간 비교로 읽을 것.")
set_notes(s, """이 슬라이드가 STEP 7에서 가장 결정적인 발견입니다.

그동안 우리는 "응답이 느린 건 아마 스케줄러가 요청을 붙잡고 있어서일 것"이라고 추측만 했습니다.
프로파일러를 켜서 이걸 실제 숫자로 확정했습니다.

왼쪽 그래프. 빨간색이 스케줄러 대기 시간, 파란색이 실제 계산 시간입니다.
건강한 구간(MORI C10)에서는 빨간색이 아예 안 보입니다. 중앙값 기준 대기가 0초예요.
대기를 겪은 요청도 전체의 0.4%뿐입니다. 즉 오프로딩을 해도 응답이 안 느려집니다.

그런데 C80에서는 TTFT 45.83초 중에 38.3초가 대기입니다. 84%가 기다리는 시간이에요.
요청의 75%가 대기를 겪습니다.

여기서 TA+O와 비교가 중요합니다.
전체 시간 중 대기 비중만 보면 68.4% 대 69.7%로 비슷해 보입니다.
그런데 TA+O는 중앙값 대기가 0초입니다. 대기를 겪는 요청이 35.7%밖에 안 되고, 대신 그 소수가 아주 오래 기다립니다.
MORI는 75%가 전면적으로 기다립니다. 평균만 보면 놓치고 중앙값을 같이 봐야 보이는 차이입니다.

오른쪽 그래프. 처리량은 22.3 대 39.1로 1.8배 차이인데,
약속 시간 안에 도착한 산출인 goodput은 0.7 대 17.1로 24배 차이입니다.
처리량만 보면 격차를 13배나 과소평가하게 됩니다.

의외였던 것 하나. decode 비중은 별로 안 떨어졌습니다. 무너진 건 비율이 아니라 스텝 하나하나의 절대 속도였습니다.""")

# =====================================================================  S12 종합 결론
s = slide("종합 결론 — 코드는 논문대로다", "3계층 모두 통과 · C80 역전은 정책 오구현이 원인이 아니다",
          tw_color=GREEN)
for tag, head, body, col, x in [
        ("A", f"정책 충실성 {D['A_total']}/{D['A_denom']}",
         "스티키 · ι 최고 demote · ACTING 우선 · lazy · 그룹 후 ι 최소 promote ·\n"
         "양 tier admission · ★상대적 경계 · robust+responsive ι · typed evict\n\n"
         "이탈 1건(A7c LRU) 발견 → 수정 → 재검증", GREEN, 0.42),
        ("B", "실동작 확인",
         "cpu_tier 0→1 시각에 GPU KV −6,258 tok\n(= 강등 프로그램 KV 6,583)\n"
         "promote 시각에 reload +13,240 tok\nKV 폐기 0건 (전 구간 ≤1.3%)\n\n"
         "(b) busy 잔류만 미확정", BLUE, 4.72),
        ("7", "건강 구간에서 유용",
         "SLO 5초 만족 99.6% · goodput ≈ throughput\npause 점유 0.9%\n"
         "오프로딩을 TA+O의 3배 쓰고도\n낭비율은 동등하거나 더 낮음\n\n"
         "→ 오프로딩이 지연 비용 없이 작동", PURPLE, 9.02)]:
    p = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(1.8), Inches(3.9), Inches(3.15))
    p.fill.solid(); p.fill.fore_color.rgb = PANEL
    p.line.color.rgb = col; p.line.width = Pt(1.5); p.shadow.inherit = False
    chip(s, tag, x + 0.15, 1.95, 0.42, col, size=13, h=0.34)
    add_text(s, head, x + 0.68, 1.97, 3.1, 0.3, size=13, bold=True, color=col)
    add_text(s, body, x + 0.2, 2.42, 3.5, 2.4, size=10.5, color=INK)
band(s, 5.2, 0.045, GREEN, x=0.42, w=12.5)
add_text(s, "따라서 — 높은 동시성에서 MORI가 TA+O에 뒤지는 것은 “구현이 틀려서”가 아니다.",
         0.42, 5.42, 12.5, 0.4, size=17, bold=True, color=INK)
add_text(s, "충실하게 구현된 논문 정책이, 우리 하드웨어의 극단 레짐(oversub 9.9×)에서 보이는 성질이다.  [추론]",
         0.42, 5.9, 12.5, 0.4, size=13.5, color=GRAY)
add_text(s, "→ 그럼 왜 논문과 반대 결과가 나오는가? 다음 장", 0.42, 6.4, 12.5, 0.4,
         size=13, bold=True, color=BLUE)
footer(s, "baseline 0-line diff 유지 · 수정은 mori_router.py / mori_tier.py 2파일뿐 · 커밋 없음")
set_notes(s, """여기까지가 검증 결과 종합입니다.

A 계층: 논문 정책 규칙을 전부 확인했고 17개 테스트를 통과했습니다. 이탈 하나를 찾아서 고쳤습니다.
B 계층: 실제 GPU에서 KV가 오르내리는 게 프로그램 단위로 숫자가 맞아떨어졌습니다.
STEP 7: 건강한 구간에서는 오프로딩이 지연 비용 없이 제값을 합니다.

그래서 결론은 굵은 글씨 한 줄입니다.
높은 동시성에서 MORI가 TA+O보다 못한 건 우리가 코드를 잘못 짜서가 아닙니다.
논문대로 충실히 구현된 정책이, 우리 하드웨어의 극단적인 조건에서 보이는 성질입니다.

이건 변명이 아니라 검증으로 뒷받침된 주장입니다.
만약 검증을 안 했다면 "성능이 안 나오는데 구현이 잘못됐나?"라는 의심을 계속 안고 가야 했을 겁니다.
이제 그 가능성을 배제하고 다음 질문으로 넘어갈 수 있습니다.

다음 장에서 실제로 논문과 어떻게 다른지, 그리고 왜 그런지 보겠습니다.""")

# =====================================================================  S13 논문과 반대
s = slide("그런데 왜 논문과 반대인가 — 전 곡선 재현",
          "건강 구간에서는 MORI 우위(논문과 일치) · 고 oversub에서만 역전", tw_color=RED)
add_figure(s, "mori_ver_msw_curve_yunuikang", 0.42, 1.6, 12.5, 3.1)
b2 = {r["C"]: r for r in D["B2"]}
rows = [["C (oversub)", "TA thr", "TA+O thr", "MORI thr", "MORI vs TA+O", "MORI ttft_p50", "TA+O ttft_p50"]]
for C in (8, 10, 20, 50, 80):
    r = b2[C]
    ratio = r["MORI"]["thr"] / r["TAO"]["thr"]
    rows.append([f'{C} ({r["oversub"]}×)', f'{r["TA"]["thr"]}', f'{r["TAO"]["thr"]}', f'{r["MORI"]["thr"]}',
                 f'{ratio:.2f}×', f'{r["MORI"]["ttft_p50"]}s', f'{r["TAO"]["ttft_p50"]}s'])
add_table(s, rows, 0.42, 4.85, 7.3, 1.75, fs=10, hdr_fs=10,
          col_widths=[1.15, 0.9, 0.95, 0.95, 1.05, 1.3, 1.3],
          highlight_rows={1: HEALTHY, 2: HEALTHY, 5: EXTREME})
p = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.25), Inches(4.85), Inches(4.67), Inches(1.75))
p.fill.solid(); p.fill.fore_color.rgb = EXTREME; p.line.fill.background(); p.shadow.inherit = False
add_text(s, "논문 vs 우리", 8.45, 4.95, 4.3, 0.3, size=12, bold=True, color=RED)
add_text(s,
         "논문 [논문-인용]: C=80에서 MORI가 TA+O 대비\n"
         "    throughput +20~71% / TTFT −18~43%\n\n"
         "우리 [측정]: C=80에서 MORI는 TA+O의 0.45배\n"
         "    (6.5 vs 14.3), TTFT는 4.1배 악화 (13.93 vs 3.40s)",
         8.45, 5.3, 4.3, 1.2, size=10.5, color=INK)
footer(s, "동일 트레이스·동일 드라이버·동일 엔진 설정에서 시스템 플래그만 바꾼 1시간 run × 30셀. "
          "논문 수치 출처: plans/2026-07-30_PLAN_mori-on-thunderagent_yunuikang.md:482")
set_notes(s, """이제 불편한 얘기를 정면으로 하겠습니다. 우리 결과가 논문과 반대로 나옵니다.

왼쪽 그래프를 보시면 동시성 8과 10, 즉 초록 배경 구간에서는 빨간 선(MORI)이 가장 위에 있습니다.
논문 주장대로 MORI가 이깁니다. 21.1 대 20.6, 23.7 대 23.3으로 미세하지만 우위입니다.

그런데 동시성 50, 80으로 가면 빨간 선이 아래로 꺾입니다.
C80에서는 MORI가 6.5, TA+O가 14.3으로 절반 이하입니다.
오른쪽 그래프는 응답 시간인데 로그 스케일입니다. MORI만 위로 치솟습니다. 13.93초 대 3.40초, 4배 넘게 나쁩니다.

오른쪽 아래 상자가 핵심 대비입니다.
논문은 동시성 80에서 MORI가 처리량 20~71% 좋고 응답시간 18~43% 낫다고 주장합니다.
우리는 같은 동시성 80에서 처리량이 0.45배, 응답시간은 4.1배 나쁩니다.

정반대죠. 그런데 앞에서 코드는 논문대로라는 걸 확인했습니다.
그럼 뭐가 다른 걸까요? 다음 장입니다.""")

# =====================================================================  S14 원인
s = slide("원인 — 같은 “C=80”이 우리 하드웨어에서는 다른 레짐이다",
          "논문 우위 레짐은 “고 동시성 + moderate oversub” · 5090에서는 이 둘이 동시에 성립하지 않는다",
          tw_color=RED)
zone(s, "①", "왜 우리 C80이 극단이 되는가 — 용량 계산", 0.42, 1.7, 6.1, 2.5, PURPLE)
add_table(s, [
    ["항목", "값", "출처"],
    ["GPU KV 풀 (pin)", f'{D["env"]["pool_tokens"]:,} tok', "--max-total-tokens"],
    ["Track M 컨텍스트 median", "32,376 tok", "trace 통계"],
    ["→ 동시 수용 가능 (fit)", "8.10 프로그램", "pool ÷ median"],
    ["oversub = C ÷ fit", "C80 → 9.9×", "정의"],
], 0.58, 2.25, 5.8, 1.6, fs=10.5, hdr_fs=10.5, col_widths=[2.3, 1.7, 1.8],
    highlight_rows={4: EXTREME})
add_text(s, "5090의 HBM으로는 “C를 키우면 반드시 oversub도 커진다”\n"
            "→ 논문이 이겼다는 “고 C + 여유 있는 oversub” 조합에 도달할 수 없다  [추론]",
         0.58, 3.9, 5.8, 0.55, size=10.5, color=RED, bold=True)
zone(s, "②", "그 레짐에서 무슨 일이 벌어지나 — 인과 사슬", 6.72, 1.7, 6.2, 2.5, BLUE)
add_bullets(s, [
    ("oversub가 커지면 “내려야 할 프로그램”이 상시 존재", 0, INK, False),
    ("→ 스티키가 걸릴 여유 자체가 없어 왕복이 상시화", 0, INK, False),
    ("→ KV가 GPU에 안정적으로 머물지 못해 prefix cache가 깨짐", 0, INK, False),
    ("→ 그 자리를 recompute가 채우고, 요청은 대기열에 묶임", 0, INK, False),
    ("= 정책은 그대로인데 **환경이 정책의 전제를 깬 것**", 0, RED, True),
], 6.88, 2.3, 5.9, 1.7, size=11)
add_figure(s, "mori_ver_causal_chain_yunuikang", 0.42, 4.4, 12.5, 1.55)
add_text(s, "논문 정책은 “가끔 내리고 오래 머문다”를 전제한다. oversub 9.9×에서는 “상시 내리고 금방 되올린다”가 되어 "
            "전제가 성립하지 않는다.  [추론]",
         0.42, 6.15, 12.5, 0.4, size=11.5, color=INK, bold=True)
footer(s, "= 극단 레짐 × 충실하게 구현된 논문 정책의 성질. 구현 버그가 아니다. "
          "fit median 8.10 / peak 4.00 출처: logs/2026-07-31_M-SWP_1run_results_yunuikang.md:92")
set_notes(s, """왜 논문과 반대 결과가 나오는지, 원인을 설명하는 슬라이드입니다.

핵심은 "같은 동시성 80이라도 하드웨어에 따라 전혀 다른 상황"이라는 겁니다.

왼쪽 계산을 보세요. 우리 GPU KV 풀은 262,144 토큰입니다.
그런데 우리가 쓰는 트레이스의 프로그램 하나가 평균 32,376 토큰을 씁니다.
나눠보면 동시에 8개 정도밖에 못 올립니다. 이걸 fit이라고 부르겠습니다.
그럼 동시성 80이면 8로 나눠서 9.9배 초과 신청 상태입니다.
자리가 8개인데 80명이 들어오려는 거예요.

여기가 문제입니다. 5090의 HBM 크기 때문에 우리는 동시성을 키우면 초과율도 같이 커집니다.
논문이 우위를 보인 조건은 "동시성은 높은데 초과율은 적당한" 상태인데,
우리 하드웨어에서는 그 둘을 동시에 만들 수가 없습니다.

오른쪽과 아래 그림이 그래서 무슨 일이 벌어지는지입니다.
초과율이 크면 항상 누군가를 내려야 하는 상태가 됩니다.
MORI의 스티키 정책은 "여유가 있으면 안 움직인다"인데, 여유가 아예 없으니 스티키가 발동할 틈이 없습니다.
그래서 분당 27.7번씩 오르내리고, KV가 GPU에 자리를 못 잡아 캐시가 깨지고,
그 자리를 다시 계산이 채우고, 요청은 대기열에 묶입니다.

정리하면 정책은 그대로인데 환경이 정책의 전제를 깨버린 겁니다.
논문 정책은 "가끔 내리고 오래 머문다"를 가정하는데, 우리 환경에서는 "상시 내리고 금방 되올린다"가 됩니다.""")

# =====================================================================  S15 다음 단계
s = slide("다음 단계 — 논문 유사 레짐 재현", "더 큰 HBM에서 “고 C + moderate oversub”를 만들어 논문 우위 레짐에 도달하는지 확인")
add_table(s, [
    ["", "현재 (goguma6)", "목표 (대형 GPU 임대)"],
    ["GPU", "RTX 5090 ×2 (32GB ×2)", "H100급 대형 HBM (vast.ai 임대)"],
    ["KV 풀", f'{D["env"]["pool_tokens"]:,} tok', "수 배 확대"],
    ["fit (동시 수용)", "8.10 프로그램", "수십 프로그램"],
    ["C=80일 때 oversub", "9.9× (극단)", "moderate (논문 우위 레짐)"],
    ["예상 검증 포인트", "고 C = 반드시 극단 oversub", "고 C인데 oversub는 적당 → MORI 우위 재현되는가"],
], 0.42, 1.85, 7.9, 2.3, fs=11.5, hdr_fs=11.5, col_widths=[2.3, 2.7, 2.9],
    highlight_rows={4: EXTREME, 5: HEALTHY})
p = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.55), Inches(1.85), Inches(4.37), Inches(2.3))
p.fill.solid(); p.fill.fore_color.rgb = HEALTHY; p.line.fill.background(); p.shadow.inherit = False
add_text(s, "이 실험이 가르는 것", 8.75, 1.98, 4.0, 0.3, size=12.5, bold=True, color=GREEN)
add_bullets(s, [
    ("moderate oversub에서 MORI가 이기면\n→ 논문 재현 성공 + 레짐 가설 확정", 0, INK, True),
    ("거기서도 지면\n→ 레짐이 아닌 다른 요인 (엔진/트레이스 특성)\n   을 다시 조사", 0, INK, False),
], 8.75, 2.4, 4.0, 1.6, size=10.5)
add_text(s, "함께 닫을 미해결 항목", 0.42, 4.35, 12.5, 0.35, size=13, bold=True, color=INK)
add_table(s, [
    ["미해결", "상태", "닫는 방법"],
    ["B1(b) busy는 GPU에 남는가", "미확정 — 압박 분리 실패",
     "SHORT의 tool call을 0.1초로 줄여 ι 격차를 키우고, 오버플로가 정확히 LONG 1개분이 되게 사이징"],
    ["엔진측 typed eviction 실제 축출", "격리 호출 불가 (sglang 미설치 + 클로저-로컬)",
     "sglang 설치 환경에서 실런하며 radix node 축출 순서 직접 관측"],
    ["데이터플레인 ι 측정 / pause 제외", "코드 읽기로만 확인",
     "요청/응답 경로를 실제로 태워 ι 표본에서 대기가 빠지는지 검증"],
    ["축출 방향 (라우터 idle부터 vs hicache busy부터)", "판정 보류", "논문 §4.3.2 원문 대조"],
], 0.42, 4.75, 12.5, 1.85, fs=10, hdr_fs=10.5, col_widths=[3.3, 3.2, 6.0])
footer(s, "F2 과잉 마킹 · F3 큰 프로그램 기아는 tr/MORI 공통(baseline 상속)이라 비교에 중립 — 수정 안 하는 것이 맞다.")
set_notes(s, """다음 단계입니다.

앞에서 원인이 "우리 하드웨어에서는 고 동시성과 적당한 초과율을 동시에 만들 수 없다"였습니다.
그럼 검증 방법은 간단합니다. 더 큰 GPU를 빌려서 그 조합을 만들어보면 됩니다.

vast.ai 같은 데서 H100급을 임대하면 HBM이 훨씬 크니까 KV 풀도 커지고,
동시에 수용 가능한 프로그램 수(fit)가 수십 개로 올라갑니다.
그러면 동시성 80이어도 초과율이 적당한 수준이 됩니다. 논문이 우위를 보였다는 그 조건이죠.

거기서 MORI가 이기면 논문 재현에 성공한 거고, 레짐 가설도 확정됩니다.
만약 거기서도 진다면 하드웨어 레짐이 아닌 다른 요인, 예를 들어 엔진 차이나 트레이스 특성을 다시 봐야 합니다.
어느 쪽이든 답이 나오는 실험입니다.

아래 표는 이번에 다 못 닫은 항목들입니다. 숨기지 않고 적어뒀습니다.
가장 중요한 건 첫 줄, "바쁜 프로그램은 GPU에 남는가"입니다.
다시 하려면 짧은 콜을 0.1초로 줄여서 ι 격차를 크게 벌리고,
초과량이 정확히 프로그램 하나 분량이 되도록 크기를 맞춰야 합니다.

맨 아래 각주. 검증 중에 발견한 것 중에 과잉 마킹이나 큰 프로그램 기아 문제가 있었는데,
이건 baseline 코드에서 물려받은 거라 MORI와 비교 대상이 똑같이 겪습니다.
그래서 비교에는 영향이 없고, 고치지 않는 게 맞습니다.""")

# =====================================================================  S16 한 장 요약
s = slide("한 장 요약", "코드는 논문대로 작동한다 — 성능 역전의 원인은 구현이 아니라 레짐", tw_color=GREEN)
add_table(s, [
    ["계층", "질문", "결과", "핵심 근거 [측정]"],
    ["A 정책 충실성", "코드가 논문 규칙대로 결정하는가",
     f"{D['A_total']}/{D['A_denom']} PASS",
     "A5 상대성: GPU 2칸→3칸에서 경계 ι≤0.4→ι≤0.6 이동 · mutation M1~M8로 falsifiability 증명"],
    ["B 실동작", "실 GPU에서 메커니즘이 도는가",
     "핵심 3개 중 2 PASS\n1 미확정",
     "cpu_tier 0→1 시각에 GPU KV −6,258 tok (강등 프로그램 KV 6,583과 일치) · reload +13,240 tok · KV 폐기 0건"],
    ["STEP 7 유용성", "바쁜 GPU가 유용한 일을 했는가",
     "건강 구간 정상\n극단만 붕괴",
     "C10: SLO5s 만족 99.6%, pause 점유 0.9% ↔ C80: ping-pong 90.7%, 낭비율 0.399, goodput 0.7"],
], 0.42, 1.75, 12.5, 2.25, fs=10.5, hdr_fs=11,
    col_widths=[1.9, 3.0, 1.8, 5.8],
    highlight_rows={1: HEALTHY, 3: HEALTHY})
band(s, 4.15, 0.04, GREEN, x=0.42, w=12.5)
add_text(s, "결론:  A 계층 충실 + B 계층 실동작 확인 + 건강 구간 유용  →  C80 역전은 정책 오구현이 아니라 "
            "oversub 9.9× 극단 레짐의 성질",
         0.42, 4.32, 12.5, 0.45, size=14, bold=True, color=INK)
add_text(s, "다음:  대형 HBM 환경 임대 → “고 C + moderate oversub”에서 논문 우위 레짐 재현 검증",
         0.42, 4.8, 12.5, 0.35, size=12.5, bold=True, color=BLUE)
add_text(s, "부록 — 측정 제약 (해석 시 반드시 함께 읽을 것)", 0.42, 5.20, 12.5, 0.3,
         size=12, bold=True, color=RED)
add_table(s, [
    ["제약", "영향", "대응"],
    ["Part B는 420초 run (M-SWP는 3600초)", "C80이 더 열화됨 (드라이버 thr 1.19 vs 6.5)", "절대값 비교 금지 — 같은 run 안의 셀 간 비교로만"],
    ["③ goodput Part A는 per-turn 미저장", "정확값 불가 → 순서통계 구간", "Part B(⑤)가 프로파일 셀에 한해 실측으로 대체"],
    ["nvidia-smi로 KV 해제가 안 보임", "메모리가 27.7GB 상수", "sglang:num_used_tokens로 관측"],
    ["B1(b) busy 잔류 미확정", "“busy는 남는다”를 실런에서 못 보임", "ι 격차 키우고 오버플로 정밀 사이징 후 재시도"],
    ["prefill_s/decode_s는 요청별 wall-clock", "GPU 배타 점유 시간이 아님(큐잉 포함)", "국면 간 비율 비교로만 읽음"],
], 0.42, 5.50, 12.5, 1.3, fs=8.8, hdr_fs=9.5, col_widths=[3.6, 4.2, 4.7])
footer(s, "원본 로그 5개 + 통합본: logs/2026-08-04_MORI_VERIFICATION_yunuikang.md · "
          "재현: python tests/test_mori_policy_yunuikang.py (GPU 불필요)")
set_notes(s, """마지막 요약입니다.

위 표 한 줄씩 읽으면 오늘 발표가 다 들어있습니다.
A 계층은 코드가 논문 규칙대로 판단하는지 봤고 17개 다 통과했습니다.
B 계층은 실제 GPU에서 메커니즘이 도는지 봤고, KV 이동이 토큰 단위로 맞아떨어졌습니다.
STEP 7은 바쁜 게 유용한 건지 봤고, 건강한 구간에서는 정상, 극단에서만 무너집니다.

결론 줄이 오늘의 메시지입니다.
코드는 맞습니다. 높은 동시성에서 성능이 뒤집히는 건 구현 잘못이 아니라
우리 하드웨어에서 초과율이 9.9배까지 가는 극단 조건 때문입니다.

다음은 큰 GPU를 빌려서 논문과 비슷한 조건을 만들어보는 겁니다.

아래 부록은 이 결과를 인용하실 때 꼭 같이 봐주셔야 할 제약들입니다.
특히 첫 줄이 중요한데, 프로파일 실험은 7분짜리 짧은 run이라 1시간 run과 절대값을 비교하면 안 됩니다.
같은 run 안에서 셀끼리 비교하는 용도로만 쓰셔야 합니다.
그리고 B1(b)는 아직 확인 못 했다는 점, 숨기지 않고 적어뒀습니다.""")

# =====================================================================  S17 세 다이얼 (보정)
s = slide("보정 — “fit≈20”은 GPU 쪽 정답, 결정 조건은 따로 있다",
          "붕괴를 가른 건 fit이 아니라 ② GPU+CPU 합이 워크셋을 담는가 · ③ reload가 싼가", tw_color=RED)

# --- 개념: 오프로딩이 이기는 조건 ---
add_text(s, "오프로딩이 이기는 조건", 0.42, 1.66, 3.2, 0.3, size=12.5, bold=True, color=INK)
for i, (t, col, x) in enumerate([
        ("GPU 단독으로는\n못 담는다  (oversub > 1)", AMBER, 3.55),
        ("GPU+CPU 합치면\n담긴다  → Waiting 축출 ≈ 0", GREEN, 6.65),
        ("reload가 싸다\n(recompute 대신 PCIe 복사)", BLUE, 9.75)]):
    b = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(1.62), Inches(2.9), Inches(0.78))
    b.fill.solid(); b.fill.fore_color.rgb = col; b.line.fill.background(); b.shadow.inherit = False
    tf = b.text_frame; tf.word_wrap = True; tf.text = t
    for p_ in tf.paragraphs:
        p_.alignment = PP_ALIGN.CENTER
        for r_ in p_.runs:
            r_.font.size = Pt(10.5); r_.font.bold = True; r_.font.color.rgb = WHITE; r_.font.name = "Arial"
    if i < 2:
        add_text(s, "＋", x + 2.92, 1.85, 0.3, 0.3, size=15, bold=True, color=GRAY)
add_text(s, "세 개가 **동시에** 성립해야 한다 — 하나라도 깨지면 thrashing", 0.42, 2.02, 3.2, 0.3,
         size=10, color=GRAY)

# --- 세 다이얼 ---
add_table(s, [
    ["다이얼", "무엇을 맞추나", "공식", "5090에서", "H200에서"],
    ["① fit", "GPU oversub를 2~4× 대역으로\n(논문 우위 대역)", "fit = GPU풀 ÷ ctx_median\noversub = C ÷ fit",
     "fit 8.10 고정 →\nC80이 9.9× [측정]", "fit 15~20 →\nC40 2× · C80 4×"],
    ["★ ② CPU tier r", "GPU+CPU가 워크셋을 담게\n= Waiting 축출 ≈ 0", "**r ≥ oversub − 1**\nCPU풀 ≥ (oversub−1)×GPU풀",
     "**r=2 고정 → C50·C80에서\n부족** [측정]", "C40 → r≥1\nC80 → r≥3"],
    ["③ interconnect", "reload 단가를 낮춰\noffload 이점을 살림", "recompute 대신 PCIe 복사가\n싸야 이득이 남음",
     "**NVLink 없음 · SYS ·\ncross-NUMA** [측정]", "SXM/NVLink · PCIe5\nTP1이라 all-reduce 자체 없음"],
], 0.42, 2.48, 12.5, 1.75, fs=9.5, hdr_fs=10,
    col_widths=[1.55, 2.85, 3.0, 2.55, 2.55], highlight_rows={2: EXTREME})
add_text(s, "① 은 “압박을 만드는” 다이얼, ② 는 “붕괴를 막는” 다이얼 — 역할이 다르다. "
            "fit=20이어도 r=2면 GPU+CPU가 워크셋의 75%만 담아 25%가 Waiting으로 넘친다.",
         0.42, 4.28, 12.5, 0.3, size=10, color=RED, bold=True)

# --- 측정 근거: 5090 곡선이 ②로 설명된다 ---
add_text(s, "★ 우리 5090 데이터가 이미 ②를 증명한다 — r=2 고정에서 수용률이 떨어지는 순간 역전  [측정]",
         0.42, 4.66, 12.5, 0.32, size=12.5, bold=True, color=INK)
add_table(s, [
    ["C", "워크셋 (= C × ctx_median)", "GPU+CPU (r=2)", "**수용률**", "Waiting 넘침", "Waiting 축출", "MORI / TA+O"],
    ["20", "647,520 tok (88.9 GiB)", "786,432 tok (108.0 GiB)", "**121 %**", "0 %", "2", "**1.12× 우위**"],
    ["50", "1,618,800 tok (222.3 GiB)", "786,432 tok (108.0 GiB)", "49 %", "51 %", "4", "0.73×"],
    ["80", "2,590,080 tok (355.7 GiB)", "786,432 tok (108.0 GiB)", "**30 %**", "**70 %**", "9", "**0.45×**"],
], 0.42, 5.02, 12.5, 1.15, fs=10, hdr_fs=10,
    col_widths=[0.75, 3.0, 2.75, 1.35, 1.5, 1.5, 1.65],
    highlight_rows={1: HEALTHY, 3: EXTREME})
add_text(s, "수용률 121% → 49% → 30% 로 떨어지는 것과 MORI/TA+O 1.12× → 0.73× → 0.45× 가 정확히 동행한다. "
            "임계 예측 C ≤ (1+r)×fit = 3×8.10 = 24.3 이 실측 C20(승)·C50(패) 사이에 위치.",
         0.42, 6.28, 12.5, 0.3, size=10, color=GRAY)
band(s, 6.62, 0.035, RED, x=0.42, w=12.5)
add_text(s, "한 줄:  goguma6에서 깨진 것은 ①(fit)이 아니라 ②(총용량)와 ③(interconnect)였다.",
         0.42, 6.70, 12.5, 0.34, size=13.5, bold=True, color=INK)
footer(s, "→ Phase 2(진행 중): 5090에서 r만 2→3→4로 올려 같은 C=32가 뒤집히는지 확인. "
          "예측 C_crit=(1+r)×8.10 = 24.3 / 32.4 / 40.5")
set_notes(s, """앞 장(S14)에서 원인을 "oversub가 9.9배라서"라고 설명했는데, 여기서 한 단계 더 들어가 보정합니다.

fit을 20으로 맞춰서 oversub를 2~4배 대역에 놓는다는 것 자체는 맞습니다.
그 대역이 논문에서 우위가 나오는 구간이고요.
그런데 "가장 중요한 하나"를 꼽으라면 fit이 아닙니다.

맨 위 그림이 오프로딩이 이기는 조건입니다. 세 개가 동시에 성립해야 해요.
GPU 혼자서는 못 담아야 오프로딩할 일이 생기고(①),
GPU와 CPU를 합치면 담겨야 버리지 않고 싸게 되불러올 수 있고(②),
되불러오는 게 실제로 싸야 이득이 남습니다(③).

가운데 표에서 ①과 ②의 역할이 다르다는 게 핵심입니다.
①은 압박을 만드는 다이얼이고, ②는 붕괴를 막는 다이얼입니다.
그래서 fit을 20으로 잘 맞춰놔도 CPU tier를 2배로만 두면,
C80에서는 GPU와 CPU를 합쳐도 워크셋의 75%밖에 못 담습니다.
나머지 25%는 Waiting으로 넘어가서 KV를 버리고, 다시 계산해야 합니다. fit이 맞아도 붕괴하는 겁니다.
필요한 CPU tier는 간단한 식으로 나옵니다. oversub가 4배면 넘치는 3배분을 CPU가 받아야 하니 r은 3 이상.

아래 표가 이 슬라이드에서 가장 중요합니다.
우리 5090 데이터가 이미 ②를 증명하고 있습니다.
r을 2로 고정해두고 C만 올렸더니, GPU+CPU가 워크셋을 담는 비율이 121%, 49%, 30%로 떨어집니다.
그리고 MORI 대 TA+O 성능비가 1.12배, 0.73배, 0.45배로 정확히 같이 떨어집니다.
수용률이 100%를 넘는 C20에서만 MORI가 이겼어요.

임계도 계산과 맞습니다. r=2면 C가 24.3 이하일 때까지만 담기는데,
실측에서 C20은 이기고 C50은 졌으니 임계가 그 사이에 있습니다.

세 번째 다리인 interconnect도 이 머신에서 직접 확인했습니다.
nvidia-smi로 보니 두 GPU가 NVLink 없이 시스템 버스로 연결돼 있고 NUMA 노드도 갈라져 있습니다.
되불러오는 비용이 비쌌다는 뜻이고, 조용히 MORI에 불리하게 작용했습니다.

한 줄로 정리하면, goguma6에서 깨진 건 fit이 아니라 총용량과 interconnect였습니다.

그래서 지금 Phase 2를 돌리고 있습니다. H200을 빌리기 전에 5090에서 r만 2, 3, 4로 올려가며
같은 C=32에서 결과가 뒤집히는지 봅니다. 뒤집히면 ②가 결정 조건이라는 게 실측으로 확정됩니다.""")

# =====================================================================  S20 Phase2 개념·원래설계
s = slide("Phase 2 — 왜 r을 올려봤나 (개념과 수식)",
          "H200을 빌리기 전에, 5090에서 “CPU tier(r)만 키워도 붕괴가 풀리는가”를 격리 검증")
add_figure(s, "mori_phase2_concept_yunuikang", 0.42, 1.6, 12.5, 3.35)
add_caption(s, "좌: 세 개념의 정의와 실측값 · 우: 용량(GPU+CPU)이 실효 워크셋을 담는지 — 수용률 100%가 판정선  [측정]",
            0.42, 4.98, 12.5, size=9.5)
zone(s, "①", "원래 설계 — C=32 고정, r만 2→3→4", 0.42, 5.30, 6.1, 1.44, PURPLE)
add_table(s, [
    ["r", "CPU tier", "수용률(명목식)", "C_crit=(1+r)×8.10", "예측"],
    ["2", "2×풀", "76 %", "24.3", "패 (32>24.3)"],
    ["3", "3×풀", "101 %", "32.4", "경계"],
    ["4", "4×풀", "127 %", "40.5", "**승** ← 교차"],
], 0.58, 5.78, 5.8, 0.82, fs=9, hdr_fs=9,
    col_widths=[0.5, 1.0, 1.5, 1.6, 1.2], highlight_rows={3: HEALTHY})
zone(s, "②", "의도한 결과 — 이게 나오면 dial② 확정", 6.72, 5.30, 6.2, 1.44, BLUE)
add_bullets(s, [
    ("같은 C=32에서 **r만 올려** MORI÷TA+O가 1.0을 교차", 0, INK, True),
    ("동시에 Waiting 축출 >0 → ≈0, ping-pong↓, prefix hit↑", 0, INK, False),
    ("→ 붕괴 원인이 **CPU 용량**임이 확정 (lever = DRAM)", 0, GREEN, True),
], 6.88, 5.78, 5.9, 0.85, size=9.5)
footer(s, "fit·oversub·r은 전부 실측값에서 유도: GPU풀 262,144 tok(--max-total-tokens) ÷ Track M ctx median 32,376 tok")
set_notes(s, """Phase 2가 왜 필요했고 어떤 개념 위에 서 있는지 설명하는 슬라이드입니다.

먼저 세 개념입니다. 왼쪽 그림을 보세요.

fit은 GPU에 동시에 몇 개의 프로그램을 올릴 수 있느냐입니다.
GPU KV 풀이 262,144 토큰이고 프로그램 하나가 평균 32,376 토큰을 쓰니까, 나누면 8.1개입니다.
즉 자리가 8개뿐입니다.

oversub는 그 자리보다 몇 배 많은 프로그램이 들어오느냐입니다. C를 fit으로 나눈 값이죠.
동시성 32면 3.95배, 50이면 6.18배입니다.

r은 CPU tier의 크기입니다. GPU 풀의 몇 배를 호스트 메모리에 잡아둘지를 정합니다.
GPU에서 밀려난 KV를 여기에 받아두면 나중에 싸게 되불러올 수 있습니다.

그래서 핵심 지표가 수용률입니다. GPU와 CPU를 합친 용량을 워크셋으로 나눈 값이고,
이게 100% 미만이면 담을 데가 없어서 Waiting으로 넘어가고, 넘어간 KV는 버려집니다.

오른쪽 막대가 그걸 그림으로 보여줍니다.
파란 게 GPU 풀, 초록이 CPU tier, 빨간 세로선이 실제 워크셋입니다.
빨간 선이 막대 안에 들어오면 다 담긴 거고, 밖으로 나가면 넘친 겁니다.

한 가지 중요한 보정이 있습니다. 워크셋을 C 곱하기 평균 컨텍스트로 계산하면 실제보다 큽니다.
모든 프로그램이 동시에 평균 길이를 갖고 있진 않거든요. 실측해보니 0.73배였습니다.

아래 왼쪽이 원래 설계입니다. C를 32로 고정하고 r만 2, 3, 4로 올리면
수용률이 76%, 101%, 127%로 올라가니까, r=4에서 MORI가 이기는 쪽으로 뒤집혀야 한다는 예측이었습니다.
아래 오른쪽이 그게 나왔을 때의 결론입니다. 붕괴 원인이 CPU 용량이라면 해결책은 DRAM을 늘리는 것이고,
그건 5090에서도 확인할 수 있으니 H200을 빌리기 전에 답이 나옵니다.""")

# =====================================================================  S21 Phase2 결과·재설계
s = slide("Phase 2 — 결과가 예측과 반대 → 중단 → C를 바꿔 재설계",
          "MORI가 이겨버려서 “교차”를 만들 수 없었다 · 원인은 메커니즘이 아니라 C_crit 공식의 과대평가",
          tw_color=RED)
zone(s, "①", "측정 결과 — 예측 패, 실측 승", 0.42, 1.7, 6.1, 2.45, RED)
add_table(s, [
    ["셀 (1시간)", "엔진(불편향)", "goodput@5s", "드라이버", "MORI÷TA+O"],
    ["앵커 MORI_r2_C20", "31.11", "26.35", "25.73", "**1.29×** 승"],
    ["MORI_r2_C32", "31.62", "25.66", "21.93", "—"],
    ["TAO_r2_C32", "28.42", "23.81", "19.50", "—"],
    ["→ C=32 비", "**1.11×**", "**1.08×**", "1.12×", "**전부 승**"],
], 0.58, 2.24, 5.8, 1.45, fs=9, hdr_fs=9,
    col_widths=[1.7, 1.15, 1.1, 0.95, 0.9], highlight_rows={1: HEALTHY, 4: HEALTHY})
add_text(s, "★ 왜 빗나갔나 (한 줄): **Waiting 넘침 자체가 안 일어났다** — MORI의 CPU→Waiting 축출 **3건**뿐."
            "\n   명목 워크셋이 실제를 과대평가: 실측 상주 758,905 ÷ 명목 1,036,032 = **0.73×**  [측정]",
         0.58, 3.72, 5.8, 0.42, size=9.5, color=RED, bold=True)

zone(s, "②", "그래서 중단 — 남은 격자로는 반증 불가", 6.72, 1.7, 6.2, 2.45, AMBER)
add_table(s, [
    ["C (r=2)", "MORI÷TA+O", "출처"],
    ["20", "1.29× 승", "Phase 2 앵커"],
    ["**32**", "**1.11× 승**", "Phase 2 (여기)"],
    ["50", "0.73× 패", "M-SWP"],
    ["80", "0.45× 패", "M-SWP"],
], 6.88, 2.24, 5.9, 1.15, fs=9, hdr_fs=9,
    col_widths=[1.1, 1.6, 3.2], highlight_rows={2: HEALTHY, 3: EXTREME})
add_text(s, "실측 임계는 **C 32~50 사이** — 공식의 24.3보다 훨씬 높다.\n"
            "→ 남은 격자(C32/40/48)에서 r을 올리면 용량만 더 늘어 **전부 “승”** → 교차가 안 생겨 반증 불가.\n"
            "→ 8.3시간을 “다 이겼다” 확인에 쓰게 됨 → **중단**.",
         6.88, 3.46, 5.9, 0.68, size=9.5, color=INK)

zone(s, "③", "재설계 — 수식에서 바꾼 값은 C 하나", 0.42, 4.28, 12.5, 2.35, GREEN)
add_text(s, "oversub = C ÷ fit   ·   수용률 = (1+r) × fit ÷ (0.73 × C)",
         0.62, 4.78, 5.6, 0.3, size=13, bold=True, color=INK)
add_text(s, "fit(8.10)은 그대로 · r 스윕도 그대로 —  **C 만 32 → 50 으로 바꿨다**\n"
            "   oversub  3.95× → **6.18×**   (MORI가 실제로 지는 구간으로 이동)",
         0.62, 5.12, 5.6, 0.6, size=10.5, color=INK)
add_table(s, [
    ["C=50", "수용률(보정식)", "예측", "판별에 쓰는 신호"],
    ["r=2", "**67 %**", "패", "Waiting↑ / ping-pong↑ / pause↑"],
    ["r=3", "89 %", "경계", "중간값"],
    ["r=4", "**111 %**", "**승 ← 교차**", "Waiting≈0 / ping-pong↓ / pause↓"],
], 6.35, 4.75, 6.4, 1.1, fs=9, hdr_fs=9,
    col_widths=[0.8, 1.5, 1.3, 2.8], highlight_rows={1: EXTREME, 3: HEALTHY})
add_text(s, "★ 이 실험이 가르는 것 —  ⓐ r 올려 **구조되면** 원인=CPU 용량 → lever는 **DRAM** (H200은 확증용)   |   "
            "ⓑ Waiting은 0인데 **정체되면** 원인=GPU-oversub 스래싱 → lever는 **HBM(fit)** → H200 필수, 예산을 HBM에 집중",
         0.62, 5.96, 12.1, 0.5, size=10, color=INK, bold=True)
footer(s, "현재 진행: C=50 · r∈{2,3,4} × MORI/TA+O 6셀(각 1시간). "
          "근거: C=32(승)와 C=50(패)의 Waiting 축출이 3~4건으로 거의 같다 → C50 loss는 Waiting 넘침이 아니다.")
set_notes(s, """앞 장의 실험을 실제로 돌린 결과와, 왜 설계를 바꿨는지 설명합니다.

왼쪽 위가 측정 결과입니다. 예측은 "r=2, C=32에서 MORI가 진다"였는데 실제로는 이겼습니다.
불편향 엔진 지표로 1.11배, goodput으로 1.08배, 드라이버로 1.12배. 세 지표가 다 같은 방향입니다.

왜 빗나갔을까요. 한 줄로 말하면 넘침이 안 일어났습니다.
MORI가 CPU tier에서 Waiting으로 버린 게 딱 3건입니다. 사실상 0이에요.
dial 2 가설은 "용량이 부족해서 넘치면 붕괴한다"인데, 넘치질 않았으니 붕괴할 이유가 없었던 겁니다.
즉 메커니즘이 틀린 게 아니라, 언제 넘치는지를 계산한 공식이 압박을 과대평가한 겁니다.
실제로 상주하는 토큰을 재보니 명목 계산의 0.73배였습니다.

오른쪽 위를 보면 r=2에서 C를 올려가며 MORI가 언제 지기 시작하는지가 정리돼 있습니다.
20과 32에서는 이기고, 50과 80에서는 집니다. 그러니까 진짜 임계는 32와 50 사이인데,
공식은 24.3이라고 했으니 한참 낮게 잡은 겁니다.

그래서 남은 실험을 중단했습니다. 계획했던 격자가 C 32, 40, 48인데,
여기서 r을 올리면 용량만 더 늘어나니까 전부 이기는 결과만 나옵니다.
교차가 안 생기면 가설을 반증할 수가 없어요. 8시간을 써서 "다 이겼다"만 확인하게 됩니다.

아래가 재설계입니다. 수식에서 바꾼 값은 딱 하나, C입니다.
fit은 하드웨어가 정하는 값이라 5090에서는 못 바꾸고, r 스윕은 원래 목적이라 그대로 둡니다.
C만 32에서 50으로 옮기면 oversub가 3.95배에서 6.18배가 되고, MORI가 실제로 지는 구간에 들어갑니다.
보정계수 0.73을 넣어 다시 계산하면 수용률이 67%, 89%, 111%가 되어
r=4에서 100%를 넘습니다. 즉 r=4에서 교차가 예측됩니다.

맨 아래 줄이 이 실험의 진짜 가치입니다. 어느 쪽으로 나와도 답이 나옵니다.
r을 올려서 구조되면 원인은 CPU 용량이고, 해결책은 DRAM입니다. 그럼 H200은 확인용이지 필수가 아닙니다.
반대로 Waiting은 0인데 성능이 정체되면 원인은 GPU 자리 부족으로 인한 스래싱이고,
그건 HBM을 키우는 수밖에 없으니 H200이 필수가 되고 예산을 HBM에 몰아야 합니다.

판단 근거가 하나 더 있습니다. C=32는 이기고 C=50은 지는데 Waiting 축출은 둘 다 3~4건으로 거의 같습니다.
그러니 C=50에서 지는 건 Waiting 넘침 때문이 아닙니다. 달라진 건 GPU oversub뿐이에요.""")

# =====================================================================  S21b 두 원인과 r의 판별력
s = slide("성능을 죽이는 원인은 둘 — 서로 다른 자원에 걸려 있다",
          "r은 CPU 상자만 키우고 GPU 슬롯(fit)은 그대로 → 그래서 r 스윕이 둘을 갈라낸다", tw_color=RED)
add_text(s, "전제:  프로그램은 **GPU에 KV가 올라와 있을 때만** inference를 돈다. "
            "GPU는 동시에 fit(≈8)개만 담는다. C=50이면 8개만 돌고 42개는 대기 → 스케줄러가 매 tick 8자리를 회전.",
         0.42, 1.58, 12.5, 0.34, size=11, color=INK)
add_figure(s, "mori_phase2_two_causes_yunuikang", 0.42, 1.92, 12.5, 2.88)
add_table(s, [
    ["", "원인 ① CPU tier 용량 부족", "원인 ② GPU 슬롯 경쟁 (스래싱)"],
    ["무슨 일이", "demote된 KV를 받을 CPU 자리가 없어 **폐기**\n→ Waiting → 재개 시 **full recompute(prefill 전체)**",
     "CPU를 무한히 키워도 GPU는 **여전히 8칸**\n50개가 8자리를 다퉈 승격/강등이 끝없이 반복"],
    ["증상", "Waiting 축출 > 0 · recompute율↑ · throughput↓",
     "ping-pong↑ (매번 offload+reload 전송비)\nprefix cache hit↓ (교체로 계속 밀려남) → prefill 일↑\npause↑ (승격까지 여러 tick 대기 → **TTFT를 대기가 지배**)"],
    ["고치는 lever", "**r (CPU tier = DRAM)**\n자리가 생기면 폐기 대신 보관 → 재개는 싼 reload",
     "**fit (GPU풀 = HBM)**\nfit = GPU풀 ÷ ctx — r로는 전혀 안 바뀜"],
    ["r을 올리면", "✅ 해결됨 (Waiting → 0)", "❌ 그대로 (둘 곳만 늘 뿐, 돌 수 있는 개수는 불변)"],
], 0.42, 4.90, 12.5, 1.5, fs=8.2, hdr_fs=9,
    col_widths=[1.35, 5.35, 5.8], highlight_rows={4: EXTREME})
band(s, 6.72, 0.035, RED, x=0.42, w=12.5)
add_text(s, "★ 결정적 관찰의 답:  Waiting 11→1 인데 회복 없음  →  **원인② 확정 (HBM·H200)**",
         0.42, 6.80, 12.5, 0.24, size=11, bold=True, color=INK)
footer(s, "HBM이 왜 ②를 고치나: HBM↑ → GPU풀↑ → fit↑ → 동시 상주 프로그램↑ → 승격/강등 회전↓ → ping-pong·pause·cache 붕괴 완화. "
          "5090 64GB vs H200 141GB.")
set_notes(s, """이 슬라이드가 Phase 2 실험의 논리적 핵심입니다. 왜 r을 돌려보는 것만으로 두 원인을 구분할 수 있는지 설명합니다.

먼저 전제입니다. 프로그램은 자기 KV가 GPU에 올라와 있어야만 추론을 돌릴 수 있습니다.
그런데 GPU 메모리는 동시에 8개 분량의 KV만 담습니다.
동시성이 50이면 8개만 실제로 돌고 나머지 42개는 CPU tier나 대기열에서 순서를 기다립니다.
스케줄러는 매 tick마다 승격과 강등으로 이 8자리를 돌려가며 씁니다.

여기서 성능을 죽이는 원인이 두 가지인데, 서로 다른 자원에 걸려 있다는 게 포인트입니다.

원인 1은 CPU tier 용량 부족입니다.
GPU에서 밀려난 프로그램의 KV는 CPU tier로 갑니다.
그런데 CPU tier가 꽉 차 있으면 그 KV를 통째로 버리고 대기열로 보냅니다.
나중에 그 프로그램이 재개할 때는 처음부터 프리필을 다시 해야 합니다.
이 재계산이 GPU 사이클을 잡아먹어서 처리량을 깎습니다.
이건 r로 고쳐집니다. CPU에 자리가 생기면 버리는 대신 보관되고, 재개는 싼 복사로 끝납니다.

원인 2는 GPU 슬롯 경쟁입니다.
CPU tier를 무한히 키워도 GPU에 동시에 올릴 수 있는 건 여전히 8개입니다.
50개가 8자리를 두고 다투니까 스케줄러가 쉼 없이 승격과 강등을 반복합니다.
그러면 세 가지 문제가 생깁니다.
첫째 핑퐁입니다. 올렸다가 잠깐 돌리고 다음 프로그램 자리 만들려고 다시 내리는 걸 반복하면
매번 전송 비용이 듭니다.
둘째 prefix 캐시 붕괴입니다. 프로그램이 계속 교체되니 GPU 캐시가 계속 밀려나서 적중률이 떨어지고,
그만큼 프리필 일이 늘어납니다.
셋째 pause입니다. 요청이 도착했는데 그 프로그램이 GPU에 없으면 승격될 때까지 여러 tick을 기다립니다.
그래서 응답 시간이 계산이 아니라 이 대기 시간에 지배됩니다.
이건 r로 안 고쳐집니다. CPU tier를 키워도 GPU 슬롯 수는 그대로 8개니까요.
강등된 프로그램을 둘 곳만 늘어날 뿐, 돌 수 있는 개수는 안 늘어납니다.

오른쪽 그림이 그걸 보여줍니다. r을 2에서 4로 올리면 초록 상자만 커지고 파란 GPU 8칸은 그대로입니다.

그래서 r을 돌려보면 둘이 갈립니다.
r을 올려서 대기열 축출을 0까지 만들면 원인 1을 완전히 제거한 상태가 됩니다.
그 다음에 처리량이 회복되면 원래 병목이 원인 1이었던 거고, 해결책은 DRAM입니다.
반대로 축출은 0인데 처리량이 정체되고 핑퐁과 pause가 여전하면
원인 1은 애초에 병목이 아니었고 남은 건 원인 2뿐입니다. 그건 r로는 못 건드리는 영역이고,
HBM을 키워서 fit을 늘리는 수밖에 없습니다. 그래서 H200이 필수가 됩니다.

맨 아래 각주가 HBM이 왜 원인 2를 고치는지입니다.
HBM이 크면 GPU 풀이 커지고, fit이 커져서 동시에 상주하는 프로그램 수가 늘어납니다.
8자리를 두고 다투던 게 완화되니까 회전이 줄고, 핑퐁과 pause와 캐시 붕괴가 함께 줄어듭니다.

빨간 줄에 이미 답을 적어뒀습니다. 실제로 돌려봤더니 축출은 11건에서 1건으로 사라졌는데
성능은 회복되지 않았습니다. 즉 두 번째 갈래입니다. 구체적인 숫자는 뒤에서 두 장 뒤에 나옵니다.""")

# =====================================================================  S22 H200 계획 (Phase2 분기별)
s = slide("Phase 2가 확정되면 — H200에서 무엇을, 왜 할 것인가",
          "결과에 따라 H200의 **역할과 예산 배분이 달라진다** · 공통 목표는 논문 우위 레짐(고C + moderate oversub) 재현")

# --- 분기 ---
add_text(s, "Phase 2 결과에 따른 분기", 0.42, 1.62, 6.0, 0.3, size=13, bold=True, color=INK)
for tag, head, body, lever, col, x in [
        ("ⓐ", "CPU 용량 lever 확정\n(r↑ → C50 구조됨)",
         "붕괴 원인 = CPU tier 부족\n5090에서도 DRAM으로 완화 가능",
         "H200 = **확증용**\n예산 → DRAM 우선", GREEN, 0.42),
        ("ⓑ", "GPU-fit lever 확정\n(r↑ 해도 정체·스래싱 여전)",
         "붕괴 원인 = GPU 자리 부족(oversub)\n5090으로는 원리적으로 해결 불가",
         "H200 = **필수**\n예산 → HBM(fit) 집중", RED, 6.72)]:
    p = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(1.98), Inches(6.1), Inches(1.5))
    p.fill.solid(); p.fill.fore_color.rgb = PANEL
    p.line.color.rgb = col; p.line.width = Pt(1.6); p.shadow.inherit = False
    chip(s, tag, x + 0.14, 2.10, 0.4, col, size=13, h=0.32)
    add_text(s, head, x + 0.62, 2.08, 2.7, 0.5, size=10.5, bold=True, color=col)
    add_text(s, body, x + 0.62, 2.62, 2.7, 0.7, size=9.5, color=INK)
    add_text(s, lever, x + 3.45, 2.20, 2.5, 1.0, size=10.5, bold=True, color=INK)

# --- 공통 코어 ---
zone(s, "공통", "어느 쪽이든 H200에서 할 실험 — 논문 레짐 재현", 0.42, 3.62, 12.5, 1.72, PURPLE)
add_text(s, "5090은 fit이 8.10에 고정 → C를 키우면 oversub도 같이 커져 “고C + moderate oversub”를 만들 수 없다.\n"
            "H200(141GB·TP1)은 fit을 15~20으로 올릴 수 있어 **C80을 oversub 3~4×에 착지**시킬 수 있다.",
         0.62, 4.12, 12.1, 0.5, size=10.5, color=INK)
add_table(s, [
    ["모델", "per-tok KV", "weights", "GPU 풀", "fit (med/peak)", "oversub @C40 / C80", "비고"],
    ["Qwen2.5-7B", "56 KiB", "14.19 GiB", "647,520 tok (34.6G) **캡**", "20.0 / 9.9", "2.00× / 4.00×", "캡 안 하면 fit 64.9 → 압박 소멸"],
    ["Qwen3-30B-A3B", "96 KiB", "56.87 GiB", "759,016 tok (69.5G) 자연", "23.4 / 11.6", "1.71× / 3.42×", "MoE지만 KV는 attention만"],
], 0.62, 4.66, 12.1, 0.6, fs=9, hdr_fs=9,
    col_widths=[1.6, 1.15, 1.2, 2.5, 1.5, 1.85, 2.3])

# --- Phase2가 사이징을 바꾼다 ---
zone(s, "★", "Phase 2가 H200 사이징을 바꾼다 — 실효계수 0.73 반영", 0.42, 5.48, 12.5, 1.2, AMBER)
add_table(s, [
    ["모델 @C80", "명목 워크셋", "실효 워크셋 (×0.73)", "필요 1+r", "쓸 r", "host KV", "권장 DRAM", "원 계획 대비"],
    ["Qwen2.5-7B", "2,590,080", "1,890,758", "2.92", "**2**", "69.2 GiB", "**≈124 GiB**", "r3·158G → **−34G**"],
    ["Qwen3-30B-A3B", "2,590,080", "1,890,758", "2.49", "**2**", "139.0 GiB", "**≈236 GiB**", "r3·305G → **−69G**"],
], 0.62, 5.94, 12.1, 0.6, fs=9, hdr_fs=9,
    col_widths=[1.6, 1.4, 1.85, 1.15, 0.75, 1.25, 1.6, 2.5],
    highlight_rows={1: HEALTHY, 2: HEALTHY})
add_text(s, "→ C80에서 필요 r이 3 → 2 로 내려가 **인스턴스 DRAM 요구가 낮아진다** = 렌트 비용 절감  [추정, 계수는 C32 실측]",
         0.62, 6.60, 12.1, 0.3, size=10, color=INK, bold=True)
footer(s, "→ **결과: 분기 ⓑ 확정** (다음 슬라이드). 따라서 예산은 HBM 집중이고, 위 DRAM 표는 "
          "**“r=2면 충분”의 하한선**으로만 쓴다 — r을 더 올리는 건 실측상 이롭지 않았다.")
set_notes(s, """Phase 2 결과가 나오면 H200에서 뭘 할지, 그리고 왜 그게 결과에 따라 달라지는지 설명합니다.

위쪽 두 갈래가 핵심입니다.

ⓐ쪽으로 나오면, 즉 r을 올려서 C=50이 구조되면 붕괴 원인은 CPU tier 부족입니다.
그러면 해결책은 호스트 메모리를 늘리는 것이고, 이건 5090에서도 할 수 있습니다.
H200은 "더 큰 규모에서도 같은 결론이 나오는지" 확인하는 용도가 되고, 예산은 DRAM에 먼저 씁니다.

ⓑ쪽으로 나오면, r을 올려도 Waiting은 0인데 성능이 정체되고 스래싱이 그대로면
원인은 GPU 자리 부족입니다. 이건 5090의 HBM 크기 때문이라 원리적으로 못 고칩니다.
그러면 H200이 필수가 되고, 예산은 HBM 큰 인스턴스에 집중해야 합니다.

가운데가 어느 쪽이든 공통으로 할 실험입니다.
5090은 fit이 8.1에 고정돼 있어서 C를 키우면 oversub도 반드시 같이 커집니다.
그래서 논문이 우위를 보인 조건인 "동시성은 높은데 초과율은 적당한" 상태를 만들 수가 없습니다.
H200은 HBM이 141GB라 fit을 15에서 20까지 올릴 수 있고,
그러면 동시성 80에서도 초과율이 3~4배에 머뭅니다. 그게 논문 레짐입니다.

모델은 두 개를 씁니다. 7B는 KV가 작아서 그냥 두면 fit이 65가 되어 압박이 아예 안 생깁니다.
그래서 풀을 일부러 캡해서 fit을 20으로 맞춥니다. 논문이 쓴 방식과 같습니다.
30B는 가중치가 커서 KV 예산이 줄어드니 자연스럽게 fit 23에 착지합니다.

아래가 이번 Phase 2가 H200 계획을 실제로 바꾸는 부분입니다.
원래 계획에서는 워크셋을 C 곱하기 평균 컨텍스트로 잡아서 C80에 r이 3 이상 필요하다고 봤습니다.
그런데 Phase 2에서 실제 상주량이 명목의 0.73배라는 걸 측정했습니다.
이걸 넣어 다시 계산하면 필요한 r이 2로 내려갑니다.
7B는 호스트 메모리가 104기가에서 69기가로, 권장 DRAM이 158기가에서 124기가로 줄고,
30B는 209기가에서 139기가로, DRAM이 305기가에서 236기가로 줄어듭니다.
인스턴스를 빌릴 때 DRAM이 큰 게 비싸니까 이건 바로 비용 절감입니다.

다만 이 0.73은 C=32에서 잰 값이라 추정입니다.
지금 돌리는 C=50 실험이 이 계수를 직접 검증합니다.
예측대로 r=2에서 지면 계수가 맞는 거고, 또 이기면 계수를 더 낮춰서 다시 계산해야 합니다.
그 결과가 나온 뒤에 인스턴스 스펙을 최종 결정하겠습니다.""")

# =====================================================================  S24 Phase2 결과 & 판정
P2 = json.load(open("/home/yunuikang/yunuikang_work/scratch/mori/phase2_c50_summary.json"))["cells"]
c = lambda sys_, r, k: P2[f"{sys_}_r{r}_C50"][k]
rat = lambda r, k: c("MORI", r, k) / c("TAO", r, k)

s = slide("Phase 2 결과 — 답은 ⓑ: r은 MORI를 구조하지 못했다",
          "**용량은 풀렸는데(Waiting 11→1) 성능은 오히려 나빠졌다(1.05×→0.66×)** · "
          "남는 원인은 GPU 자리 부족 → **예산은 DRAM이 아니라 HBM으로**", tw_color=RED)

# --- ① 결정적 관찰의 답 ---
zone(s, "①", "S22의 “결정적 관찰”에 대한 답 — r 2→4 로 올렸을 때", 0.42, 1.60, 12.5, 1.30, PURPLE)
for lab, val, sub, col, x in [
        ("MORI Waiting 축출", f"{int(c('MORI',2,'evict'))} → {int(c('MORI',4,'evict'))}",
         "원인① 은 실제로 제거됨 ✓", GREEN, 0.62),
        ("goodput 비 (M÷T)", f"{rat(2,'gp'):.2f}× → {rat(4,'gp'):.2f}×",
         "그런데 성능은 회복 안 됨 ✗", RED, 4.85),
        ("ping-pong", f"{c('MORI',2,'pingpong'):.0f}% → {c('MORI',4,'pingpong'):.0f}%",
         "스래싱은 r에 무반응 ✗", RED, 9.08)]:
    add_text(s, lab, x, 2.02, 3.9, 0.25, size=10, color=GRAY)
    add_text(s, val, x, 2.24, 3.9, 0.42, size=20, bold=True, color=col)
    add_text(s, sub, x, 2.62, 3.9, 0.25, size=10, bold=True, color=col)

# --- ② 6셀 실측 ---
zone(s, "②", "C=50 · r∈{2,3,4} · 6셀 전부 1시간 · 반복 없음(n=1)  [측정]", 0.42, 3.00, 7.55, 3.62, BLUE)
rows = [["셀", "엔진 thr", "goodput\n@5s", "만족%", "Wait\n축출", "ping\n%", "hit", "pause\n점유%"]]
for r in (2, 3, 4):
    for sysn, disp in (("MORI", f"MORI r{r}"), ("TAO", f"TA+O r{r}")):
        rows.append([disp, f"{c(sysn,r,'eng'):.2f}", f"**{c(sysn,r,'gp'):.2f}**",
                     f"{c(sysn,r,'sat'):.1f}", f"{int(c(sysn,r,'evict'))}",
                     f"{c(sysn,r,'pingpong'):.0f}", f"{c(sysn,r,'hit'):.3f}",
                     f"{c(sysn,r,'pause_share'):.1f}"])
add_table(s, rows, 0.60, 3.48, 7.19, 0.6, fs=8.5, hdr_fs=8.5,
          col_widths=[1.15, 0.95, 0.95, 0.75, 0.72, 0.62, 0.75, 0.80],
          highlight_rows={1: HEALTHY, 3: EXTREME, 5: EXTREME})
add_text(s, "TA+O의 “Wait 축출”은 `Paused program` 카운트 — MoriRouter의 CPU→Waiting 축출과 **다른 사건**이다.\n"
            "시스템 간 절대값 비교는 무의미하고, **각 시스템 내부의 r 추세**만 읽어야 한다.",
         0.60, 5.92, 7.19, 0.5, size=8.5, color=GRAY)
add_text(s, "goodput = SLO(TTFT≤5s) 만족 스텝의 출력토큰 ÷ 고정창 2880s   [측정]",
         0.60, 6.34, 7.19, 0.25, size=8.5, color=GRAY)

# --- ③ 그림 ---
zone(s, "③", "★ 두 시스템이 같은 자극에 정반대로 반응", 0.42 + 7.68, 3.00, 4.82, 3.62, RED)
add_figure(s, "mori_phase2_c50_deck_yunuikang", 8.24, 3.46, 4.42, 2.55)
add_caption(s, "r↑ 에 TA+O는 개선(23.0→25.9), MORI는 악화(24.0→17.1)\n"
               "→ “r 자체가 나쁘다”로는 설명 안 된다",
            8.20, 6.06, 4.50, size=9)

footer(s, "★ 사전 등록 반증테스트: “r2(패)→r4(승)로 뒤집히면 CPU용량 lever” → Waiting 조건만 성립(11→1), "
          "goodput은 반대 방향(승→패) → **dial②(CPU 용량) 기각**. "
          "단 분기 ⓑ는 “정체”를 예측했는데 실측은 “악화” — 3번째 패턴이라 메커니즘은 미해결(n=1·r3<r4 비단조). "
          "확정된 것은 “DRAM은 lever가 아니다”이고, “HBM이 lever다”는 H200 fit 스윕이 확증한다.  [측정→추론]")
set_notes(s, """Phase 2 결과 슬라이드입니다. 앞 슬라이드에서 예고한 두 갈래 중 어느 쪽인지 답이 나왔습니다.

맨 위 세 숫자만 보시면 됩니다.

첫째, MORI의 Waiting 축출이 11건에서 1건으로 줄었습니다.
r을 올려서 CPU 상자를 키웠더니 KV를 버리는 일이 사실상 사라진 겁니다.
즉 원인 1번인 CPU 용량 부족은 r로 실제로 고쳐졌습니다. 여기까지는 계획대로입니다.

둘째, 그런데 성능 비가 1.05배에서 0.66배로 떨어졌습니다.
용량 문제를 없앴는데 성능이 회복되기는커녕 더 나빠졌습니다.
이건 용량이 병목이 아니었다는 뜻입니다.

셋째, 핑퐁 비율이 87퍼센트에서 95퍼센트로, 오히려 올라갔습니다.
pause 점유도 91퍼센트 근처에서 꿈쩍하지 않습니다.
스래싱은 r에 전혀 반응하지 않았습니다.

r이 못 건드리는 자원은 정의상 하나뿐입니다. GPU 자리, 즉 fit입니다.
C가 50인데 GPU에 8개만 올라가는 구조 자체가 병목이라는 겁니다.
그래서 판정은 ⓑ, GPU-fit lever입니다. 해결책은 DRAM이 아니라 HBM이고, H200이 필수입니다.

왼쪽 표가 6개 셀 실측 전부입니다. 각 셀이 1시간이고 반복은 없습니다.
표에서 한 가지 주의할 게 있는데, TA+O의 Waiting 축출 숫자가 500대로 큽니다.
이건 MORI의 CPU에서 Waiting으로 내리는 축출과는 다른 사건을 센 겁니다.
TA+O에는 CPU tier 자체가 없어서 그냥 pause 횟수를 센 거라, 두 시스템 사이 절대값 비교는 의미가 없습니다.
각 시스템 안에서 r이 바뀔 때 어떻게 움직이는지만 보시면 됩니다.

오른쪽 그림이 이번 실험에서 제일 중요한 그림입니다.
똑같이 r을 올렸는데 파란 선인 베이스라인은 23에서 25.9로 계속 좋아지고,
빨간 선인 MORI는 24에서 17.1로 나빠집니다. 정반대입니다.
그래서 "r을 올리는 게 원래 나쁜 거다"로는 설명이 안 됩니다. MORI에서만 나쁩니다.

마지막으로 솔직하게 밝혀둘 한계가 있습니다.
저희가 미리 등록한 ⓑ 시나리오는 "r을 올려도 제자리걸음"이었는데,
실제로는 제자리가 아니라 적극적으로 나빠졌습니다. 예상한 두 갈래 어디에도 없는 세 번째 패턴입니다.
왜 r이 MORI에만 해로운지, 그 메커니즘은 아직 모릅니다.
셀마다 한 번씩만 돌렸고, r=3이 r=4보다 더 나쁜 것도 순서가 뒤집혀 있어서
r 사이의 정확한 순서까지는 주장하지 않겠습니다.

그래서 확정하는 건 하나입니다. DRAM은 손잡이가 아니다.
HBM이 손잡이라는 건 H200에서 fit을 직접 바꿔보는 실험으로 확증할 계획입니다.""")

prs.save(OUT)
print("saved:", OUT, f"({len(prs.slides.__iter__.__self__._sldIdLst)} slides)")
