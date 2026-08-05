#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MORI 논문 §4 설계 · §5 구현 — 논문 리딩 발표 데크 (한국어, 13슬라이드).

모든 내용은 MORI.pdf(arXiv:2606.00866v1) 원문 직접 대조.
인용 표기: [§4.1] [§4.2] [§4.3.1] [§4.3.2] [§5] [§3.4] [Fig.6] — 논문 절 번호 그대로.
설계 동기(§3.4)는 §4를 이해하는 데 필요한 만큼만 앞에 붙였다.

★ 원문 대조 중 발견한 계획서 오기(S11에 명기):
  계획서 goguma6판 §B-Phase2는 CPU tier eviction을 "busy → idle → inactive"로 적었으나,
  논문 §4.3.2 원문은 "inactive → busy → idle"이다. 두 tier 모두 inactive를 먼저 버리고,
  busy/idle 순서만 뒤집힌다. (GPU: inactive → idle → busy / CPU: inactive → busy → idle)

하우스 스타일: scripts/build_p1_results_deck_yunuikang.py · build_mori_overview_deck 계승
Output: slides/2026-08-01_MORI-design-and-implementation_yunuikang.pptx
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

ROOT = "/home/yunuikang/yunuikang_work/distserving"
OUT = os.path.join(ROOT, "slides",
                   "2026-08-01_MORI-design-and-implementation_yunuikang.pptx")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

INK    = RGBColor(0x1F, 0x24, 0x30)
BLUE   = RGBColor(0x27, 0x46, 0x90)
AMBER  = RGBColor(0xB8, 0x86, 0x0B)
GREEN  = RGBColor(0x1E, 0x7D, 0x4F)
RED    = RGBColor(0xC0, 0x39, 0x2B)
PURPLE = RGBColor(0x85, 0x57, 0xC7)
GRAY   = RGBColor(0x6B, 0x72, 0x80)
LGRAY  = RGBColor(0xEC, 0xEE, 0xF2)
PANEL  = RGBColor(0xF4, 0xF6, 0xFB)
CREAM  = RGBColor(0xFB, 0xEE, 0xCD)
GREENBG = RGBColor(0xD7, 0xEB, 0xDD)
REDBG   = RGBColor(0xF7, 0xDE, 0xDA)
BLUEBG  = RGBColor(0xDD, 0xE6, 0xF6)
WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
FONT   = "Malgun Gothic"

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)


def blank():
    return prs.slides.add_slide(prs.slide_layouts[6])


def _style(tf, size, color, bold=False, italic=False, align=PP_ALIGN.LEFT):
    tf.word_wrap = True
    for p in tf.paragraphs:
        p.alignment = align
        for r in p.runs:
            r.font.size = Pt(size); r.font.color.rgb = color
            r.font.bold = bold; r.font.italic = italic; r.font.name = FONT


def text(slide, s, x, y, w, h, size=13, color=INK, bold=False, italic=False,
         align=PP_ALIGN.LEFT):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tb.text_frame.text = s
    _style(tb.text_frame, size, color, bold, italic, align)
    return tb


def band(slide, x, y, w, h, color):
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y),
                                Inches(w), Inches(h))
    sh.fill.solid(); sh.fill.fore_color.rgb = color
    sh.line.fill.background(); sh.shadow.inherit = False
    return sh


def title(slide, s, sub=None):
    text(slide, s, 0.45, 0.26, 12.5, 0.7, size=26, bold=True)
    band(slide, 0.45, 0.95, 12.44, 0.035, BLUE)
    if sub:
        text(slide, sub, 0.45, 1.03, 12.5, 0.5, size=14, color=BLUE,
             bold=True, italic=True)


def panel(slide, x, y, w, h, color=PANEL, line=True):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x),
                                Inches(y), Inches(w), Inches(h))
    sh.fill.solid(); sh.fill.fore_color.rgb = color
    if line:
        sh.line.color.rgb = RGBColor(0xD8, 0xDD, 0xE6); sh.line.width = Pt(0.75)
    else:
        sh.line.fill.background()
    sh.shadow.inherit = False
    return sh


def box(slide, s, x, y, w, h, fill, fg=INK, size=12.5, bold=True,
        shape=MSO_SHAPE.ROUNDED_RECTANGLE):
    sh = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w),
                                Inches(h))
    sh.fill.solid(); sh.fill.fore_color.rgb = fill
    sh.line.color.rgb = RGBColor(0xB9, 0xC1, 0xD0); sh.line.width = Pt(0.9)
    sh.shadow.inherit = False
    sh.text_frame.text = s
    _style(sh.text_frame, size, fg, bold=bold, align=PP_ALIGN.CENTER)
    sh.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    sh.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    return sh


def arrow(slide, x, y, w, h, color, up=False):
    sh = slide.shapes.add_shape(
        MSO_SHAPE.UP_ARROW if up else MSO_SHAPE.DOWN_ARROW,
        Inches(x), Inches(y), Inches(w), Inches(h))
    sh.fill.solid(); sh.fill.fore_color.rgb = color
    sh.line.fill.background(); sh.shadow.inherit = False
    return sh


def chip(slide, s, x, y, w, color, fg=WHITE, size=10.5, h=0.3):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x),
                                Inches(y), Inches(w), Inches(h))
    sh.fill.solid(); sh.fill.fore_color.rgb = color
    sh.line.fill.background(); sh.shadow.inherit = False
    sh.text_frame.text = s
    _style(sh.text_frame, size, fg, bold=True, align=PP_ALIGN.CENTER)
    sh.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    return sh


def bullets(slide, items, x, y, w, h, size=13.5, gap=7):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame; tf.word_wrap = True
    for i, (txt, lvl, col, bd) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = ("- " if lvl else "* ") + txt
        p.level = lvl; p.space_after = Pt(gap)
        for r in p.runs:
            r.font.size = Pt(size - (1.0 if lvl else 0))
            r.font.color.rgb = col; r.font.bold = bd; r.font.name = FONT
    return tb


def table(slide, rows, x, y, w, h, fs=11, hdr_fs=11, col_widths=None,
          hl_rows=None, hdr_bg=INK, left_cols=1):
    nr, nc = len(rows), len(rows[0])
    t = slide.shapes.add_table(nr, nc, Inches(x), Inches(y), Inches(w),
                               Inches(h)).table
    if col_widths:
        for j, cw in enumerate(col_widths):
            t.columns[j].width = Inches(cw)
    hl_rows = hl_rows or {}
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            c = t.cell(i, j); c.text = str(val)
            c.margin_left = Inches(0.06); c.margin_right = Inches(0.05)
            c.margin_top = Inches(0.02); c.margin_bottom = Inches(0.02)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = c.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT if j < left_cols else PP_ALIGN.CENTER
            r = p.runs[0] if p.runs else p.add_run()
            r.font.name = FONT
            if i == 0:
                c.fill.solid(); c.fill.fore_color.rgb = hdr_bg
                r.font.size = Pt(hdr_fs); r.font.bold = True
                r.font.color.rgb = WHITE
            else:
                r.font.size = Pt(fs); r.font.color.rgb = INK
                if i in hl_rows:
                    c.fill.solid(); c.fill.fore_color.rgb = hl_rows[i]
                    r.font.bold = True
                elif i % 2 == 0:
                    c.fill.solid(); c.fill.fore_color.rgb = LGRAY
                else:
                    c.fill.solid(); c.fill.fore_color.rgb = WHITE
    return t


def caption(slide, s, x, y, w, size=9.5):
    text(slide, s, x, y, w, 0.32, size=size, color=GRAY, italic=True)


def notes(slide, s):
    slide.notes_slide.notes_text_frame.text = s


def footer(slide, n):
    text(slide, "MORI 논문 §4 설계 · §5 구현  |  2026-08-01  |  강윤의",
         0.45, 7.05, 7.0, 0.3, size=9, color=GRAY)
    text(slide, str(n), 12.6, 7.05, 0.4, 0.3, size=9, color=GRAY,
         align=PP_ALIGN.RIGHT)


# ══════════════════════════════════════════════════════════════════════════
# S1 — 타이틀
# ══════════════════════════════════════════════════════════════════════════
s = blank()
band(s, 0, 0, 13.333, 2.05, INK)
text(s, "MORI — 설계와 구현", 0.75, 0.5, 11.5, 0.9, size=40, color=WHITE,
     bold=True)
text(s, "논문 §4 Design · §5 Implementation 정독", 0.78, 1.42, 11.5, 0.5,
     size=16, color=RGBColor(0xC5, 0xD2, 0xE8))
text(s, "강윤의   |   2026-08-01   |   MORI.pdf (arXiv:2606.00866v1) 원문 대조",
     0.78, 2.35, 11.5, 0.4, size=14, color=GRAY)

panel(s, 0.75, 3.0, 5.75, 2.75, PANEL)
text(s, "이 발표의 범위", 1.0, 3.15, 5.2, 0.35, size=15, bold=True, color=BLUE)
bullets(s, [
    ("§3.4  설계 요구사항 3개 + 핵심 통찰 (S2)", 0, GRAY, False),
    ("§4.1  아키텍처와 3-tier 큐 (S3-S5)", 0, INK, False),
    ("§4.2  idleness 지표 ι (S6-S7)", 0, INK, False),
    ("§4.3  스케줄링 정책 (S8-S11)", 0, INK, False),
    ("§5    구현 (S12)", 0, INK, False),
    ("정리: 설계 결정 → 근거 매핑 (S13)", 0, GRAY, False),
], 0.95, 3.55, 5.4, 2.1, size=12.5, gap=5)

panel(s, 6.85, 3.0, 5.75, 2.75, CREAM)
text(s, "한 문장 요약", 7.1, 3.15, 5.2, 0.35, size=15, bold=True, color=AMBER)
text(s, "프로그램마다 '최근 얼마나 놀았는지'를 연속값 ι로 재고,\n"
        "그 상대 순위로 GPU / CPU / Waiting 세 계층에\n"
        "끈끈하게(sticky) 배치한 다음,\n"
        "같은 라벨을 엔진 캐시 축출 정책까지 전파해\n"
        "스케줄러의 결정이 블록 수준에서도 관철되게 한다.",
     7.1, 3.6, 5.3, 2.0, size=13)

text(s, "모든 수치·정의·정책 순서는 논문 원문에서 직접 옮겼고, 슬라이드마다 절 번호를 병기했습니다.",
     0.75, 6.0, 11.8, 0.4, size=11.5, color=GRAY)
text(s, "* 원문 대조 중 계획서(§B-Phase2)의 CPU tier 축출 순서 오기를 1건 발견했습니다 — S11에서 정정합니다.",
     0.75, 6.42, 11.8, 0.4, size=11.5, color=RED, bold=True)
footer(s, 1)
notes(s, """[이 발표의 목적]
지난 개요 발표(2026-07-30)에서는 MORI가 '무엇을' 하는지를 다뤘습니다.
이번에는 '어떻게' 하는지 — 논문 §4와 §5를 구현 가능한 수준까지 파고듭니다.
제가 이 논문을 ThunderAgent 위에 재구현해야 하므로, 정책의 순서와 경계 조건을
정확히 읽는 것이 목적입니다.

[읽는 순서에 대해]
§4는 §3.4가 제기한 세 가지 요구사항에 대한 답으로 쓰여 있습니다. 그래서 S2에
§3.4를 요약해 두었습니다. 설계를 그 자체로 외우는 것보다 "무슨 문제를 풀려고
이렇게 했나"로 읽는 편이 재구현에 훨씬 유용합니다.

[§5가 짧은 이유 — 미리 말씀드립니다]
논문의 Implementation 절은 한 페이지가 안 됩니다. 코드 줄 수, User API, 스케줄러
루프 정도가 전부입니다. 엔진 쪽 구현의 실질은 §4.3.2(typed offloading)에 들어 있어서,
이 발표에서도 §4.3.2를 비중 있게 다루고 §5는 정리 성격으로 배치했습니다.

[정직 고지]
발표 준비 중 계획서에 적어둔 CPU tier 축출 순서가 논문과 다르다는 것을 발견했습니다.
S11에서 원문과 나란히 놓고 정정합니다. 구현에 직접 영향이 있는 오기라 그냥 넘기지
않고 슬라이드로 만들었습니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S2 — §3.4 설계 요구사항
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "설계가 풀어야 할 문제 세 가지 [§3.4]",
      "이 셋이 §4 설계의 각 조각과 1:1로 대응한다. 그래서 §4를 이 순서로 읽으면 된다.")

table(s, [
    ["문제 [§3.4]", "무엇이 잘못되나", "§4의 답"],
    ["① program-aware KV 제어의 부재",
     "표준 LRU는 phase를 모른 채 '가장 오래 안 쓴' 프로그램을 버린다.\n"
     "짧은 툴콜 갭에 있는 busy 프로그램을 버리고, 방금 수십 초짜리 툴콜에\n"
     "들어간 idle 프로그램을 남기는 병리적 결정이 나온다",
     "program ID로 생애 추적\n+ typed offloading [§4.1, §4.3.2]"],
    ["② 고정된 phase 분류는 일반화 안 됨",
     "프로그램은 phase를 계속 바꾸고 컨텍스트도 자란다. HW의 GPU:CPU 용량비는\n"
     "고정인데(예: H100 DGX 1:1.6 vs DRAM 2TB면 1:3.1) 수요는 계속 움직인다.\n"
     "어떤 고정 분할도 어느 순간엔 용량과 어긋난다",
     "연속 스펙트럼 ι + 상대 순위\n[§4.2]"],
    ["③ CPU 쪽 admission control의 부재",
     "idle 프로그램을 CPU DRAM에 너무 많이 내리면 거기서 서로를 축출해\n"
     "reload thrashing이 난다 (GPU 쪽 thrashing과 같은 현상)",
     "두 tier 모두 용량 제약 강제\n+ Waiting tier [§4.1, §4.3.1]"],
], 0.5, 1.75, 12.4, 3.3, fs=10, hdr_fs=10.5,
    col_widths=[2.85, 6.6, 2.95])

panel(s, 0.5, 5.25, 12.35, 1.55, CREAM)
text(s, "핵심 통찰 — idleness는 절대값이 아니라 상대적 스펙트럼이다 [§3.4]",
     0.72, 5.38, 9.0, 0.32, size=13.5, bold=True, color=AMBER)
text(s, "질문은 '이 프로그램이 idle한가'가 아니라 '다른 프로그램보다 더 idle한가'다.\n"
        "· 여러 프로그램이 모두 긴 툴콜에 있으면 → 그중 가장 오래 갈 것들을 CPU로, 먼저 돌아올 것들을 GPU에\n"
        "· 대부분이 짧은 툴콜이면 → 더 빨리 돌아올 것들을 GPU에 (내려봐야 곧바로 다시 올려야 하므로 역효과)",
     0.72, 5.72, 11.9, 1.0, size=12)
footer(s, 2)
notes(s, """[①을 구체적으로 — LRU가 왜 병리적인가]
논문이 드는 예가 아주 선명합니다. LRU는 '마지막 활동 시각'만 봅니다.
- 프로그램 A: busy phase, 마지막 추론이 몇 초 전 (지금 짧은 툴콜 갭에 잠깐 들어가 있음)
- 프로그램 B: idle phase, 마지막 추론이 방금 (그런데 막 수십 초짜리 툴콜에 들어감)
LRU는 A를 버리고 B를 남깁니다. 최근성만 보면 B가 더 최근이니까요.
결과는 최악입니다. A는 곧 돌아와서 비싼 reload나 recompute를 물고, B는 수십 초 동안
GPU 메모리를 낭비합니다. 정확히 반대로 해야 하는데 거꾸로 한 겁니다.
이게 "program-aware가 필요하다"의 근거입니다.

[②가 왜 어려운가 — 세 가지 이유가 겹칩니다]
논문이 세 가지를 듭니다.
(a) 프로그램이 phase를 계속 바꾸고 컨텍스트가 자라서, busy/idle 각각의 총 메모리 수요가
    시간에 따라 움직인다.
(b) 하드웨어의 GPU:CPU 용량비는 고정이다. 움직이는 수요와 고정된 용량비가 맞을 이유가 없다.
(c) 하드웨어마다 비율 자체가 다르다. 논문이 든 예가 좋습니다 — H100 DGX 8x80GB에
    호스트 DRAM 1TB면 1:1.6인데, 같은 노드에 DRAM 2TB면 1:3.1입니다.
    1:1.6에 맞춘 고정 분할은 1:3.1에서 틀립니다.
즉 "툴콜 2초 넘으면 idle" 같은 절대 임계값은 어떤 값을 골라도 어느 하드웨어, 어느 순간엔
틀립니다. 그래서 상대 순위로 갑니다 — 용량이 허락하는 만큼 위에서부터 자르면 되니까
임계값 자체가 사라집니다.

[③은 자주 놓치는 지점입니다]
"CPU로 내리면 해결"이 아닙니다. CPU DRAM도 유한합니다. 너무 많이 내리면 CPU에서
서로 축출하고, 축출된 건 결국 재계산해야 하니 GPU thrashing이 CPU thrashing으로
자리만 옮긴 꼴이 됩니다.
그래서 MORI는 GPU와 CPU 양쪽에 admission control을 겁니다. 둘 다 못 들어가는
프로그램은 Waiting으로 보내 KV를 아예 버립니다. Waiting tier가 존재하는 이유가
바로 이것입니다 — 도망갈 곳이 아니라, 두 tier를 보호하기 위한 안전밸브입니다.

[표의 오른쪽 열이 이 발표의 목차입니다]
①의 답은 §4.1(program ID 추적)과 §4.3.2(typed offloading),
②의 답은 §4.2(연속 ι), ③의 답은 §4.1의 3-tier와 §4.3.1의 용량 강제입니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S3 — §4.1 개요
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "§4.1 개요 — MORI는 어디에 서 있나",
      "에이전트 클라이언트와 추론 엔진 레플리카 풀 사이에 서는 program-aware 스케줄러.")

bullets(s, [
    ("모든 요청을 프록시하고, affinity를 지키며 레플리카 간 load-balance하고, 엔진에 KV 배치 힌트를 준다 [§4.1]", 0, INK, True),
    ("클라이언트가 요청에 program ID를 붙인다 → 스케줄러가 추론 스텝·툴콜 전 생애를 추적 [§4.1]", 0, INK, False),
    ("스케줄러가 프로그램별로 들고 있는 것 3가지: 현재 status / 추정 KV 컨텍스트 크기(토큰) / 최근 Reasoning·Acting 구간 길이 [§4.1]", 0, INK, False),
    ("용량 초과로 gating되어 기다린 시간은 Reasoning·Acting 어느 쪽에도 넣지 않는다 → 지표가 스케줄러가 만든 지연이 아니라 프로그램 자체 행동만 반영 [§4.1]", 0, RED, True),
], 0.5, 1.72, 12.4, 2.2, size=13)

text(s, "status(순간) vs phase(지속) — 논문이 명확히 구분한다 [§4.1]", 0.5, 4.0,
     8.0, 0.35, size=14, bold=True, color=BLUE)

table(s, [
    ["", "Status — 순간적", "Phase — 지속적 패턴"],
    ["정의", "Reasoning: GPU에서 실제로 실행 중\nActing: 외부 툴콜 대기 중, KV는 놀고 있음",
     "busy phase: 두 status를 빠르게 왕복\nidle phase: 오랫동안 Acting에 머무름"],
    ["변화 시점", "매 요청 경계마다 — 요청 도착 시 Reasoning,\n응답 완료 시 Acting으로 전이",
     "수십 초~분 단위로 지속 (§3.3: 전이는 드물다)"],
    ["역할", "ι 계산의 원자료", "스케줄러가 실제로 맞추려는 대상"],
], 0.5, 4.42, 12.4, 2.2, fs=10.5, hdr_fs=11,
    col_widths=[1.3, 5.55, 5.55], hl_rows={1: BLUEBG})
footer(s, 3)
notes(s, """[MORI의 위치를 먼저 잡아야 합니다]
MORI는 추론 엔진이 아닙니다. 엔진(SGLang) 앞에 서는 프록시 겸 스케줄러입니다.
하는 일이 네 가지입니다: (1) 모든 요청 프록시, (2) 레플리카 간 로드밸런싱(affinity 존중),
(3) 프로그램 tier 배치 결정, (4) 엔진에 KV 배치 힌트 전달.
(4)가 §4.3.2의 typed offloading이고, 스케줄러 결정이 엔진 내부까지 관철되게 하는 통로입니다.

[program ID — 클라이언트에게 요구하는 유일한 것]
에이전트 클라이언트가 같은 프로그램의 모든 요청에 같은 program ID를 붙여줘야 합니다.
이게 클라이언트 측 요구사항의 전부입니다(§5에서 다시 나옵니다). 툴콜 주석이나 phase
힌트 같은 건 요구하지 않습니다. 이 최소성이 논문이 강조하는 실용성 포인트입니다.

[status와 phase를 헷갈리면 §4 전체가 안 읽힙니다 — 여기가 중요합니다]
- status는 순간 상태입니다. 요청이 오면 Reasoning, 응답이 끝나면 Acting.
  매 요청 경계마다 바뀝니다. 이진값이고 관측이 쉽습니다.
- phase는 지속되는 패턴입니다. busy phase 프로그램은 Reasoning↔Acting을 빠르게
  왕복하고, idle phase 프로그램은 Acting에 오래 머뭅니다.
즉 같은 'Acting' status라도 0.2초 뒤 돌아올 Acting과 40초 뒤 돌아올 Acting은
완전히 다른 상황인데, status만 보면 구분이 안 됩니다.
스케줄러가 진짜 맞추고 싶은 건 phase인데 직접 관측이 안 되니, status 구간의 '길이'를
모아서 phase를 추정합니다. 그 추정량이 §4.2의 ι입니다.

[waiting time 제외 — 재구현 시 반드시 지켜야 할 디테일]
용량이 넘쳐서 스케줄러가 프로그램을 세워둔 시간은 Reasoning에도 Acting에도 넣지
않습니다. 이유는 자기강화 루프를 막기 위해서입니다.
만약 gating 시간을 Acting으로 세면, 한 번 CPU로 내려간 프로그램은 대기 시간 때문에
ι가 올라가고, ι가 높으니 계속 내려가 있게 되고, 그래서 더 오래 기다리고... 하는 악순환이
생깁니다. 스케줄러가 자기 결정으로 자기 입력을 오염시키는 셈입니다.
논문은 "the metric reflects only the program's intrinsic behavior"라고 명시합니다.
우리 코드에서는 profile/state.py가 tool_call_time(pause 이전)과 pause_time(pause 이후)을
이미 분리해 재고 있어서 계측점이 정확히 맞습니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S4 — §4.1 3-tier 구조 (Fig.6 재작성)
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "§4.1 3-tier 큐 구조 [Fig.6]",
      "메모리 계층의 각 단에 큐 하나씩. GPU·CPU 큐는 레플리카마다, Waiting 큐는 전역에 하나.")

# 좌측 메모리 계층 라벨
text(s, "GPU HBM", 0.55, 2.42, 1.15, 0.3, size=11.5, bold=True, color=RED)
text(s, "CPU DRAM", 0.55, 3.92, 1.15, 0.3, size=11.5, bold=True, color=GREEN)
text(s, "KV 폐기", 0.55, 5.42, 1.15, 0.3, size=11.5, bold=True, color=GRAY)

# 레플리카 헤더
text(s, "Replica 1", 1.85, 1.78, 4.5, 0.3, size=12, bold=True, color=BLUE,
     align=PP_ALIGN.CENTER)
text(s, "Replica 2", 7.45, 1.78, 4.5, 0.3, size=12, bold=True, color=BLUE,
     align=PP_ALIGN.CENTER)

# GPU 큐
box(s, "GPU Queue   [busy]\nP1   P2", 1.85, 2.15, 4.5, 0.9, REDBG, size=12)
box(s, "GPU Queue   [busy]\nP5", 7.45, 2.15, 4.5, 0.9, REDBG, size=12)
# CPU 큐
box(s, "CPU Queue   [idle]\nP3", 1.85, 3.65, 4.5, 0.9, GREENBG, size=12)
box(s, "CPU Queue (Full)   [idle]\nP6   P7", 7.45, 3.65, 4.5, 0.9, GREENBG,
    size=12)
# Waiting 큐 (전역)
box(s, "Waiting Queue  [inactive]  —  전 레플리카 공유 (global)\nP4   P8",
    1.85, 5.15, 10.1, 0.85, LGRAY, size=12)

# 화살표 (GPU <-> CPU)
for bx in (2.75, 8.35):
    arrow(s, bx, 3.12, 0.3, 0.48, GREEN)
for bx in (5.15, 10.75):
    arrow(s, bx, 3.12, 0.3, 0.48, RED, up=True)
# 화살표 (CPU <-> Waiting)
for bx in (2.75, 8.35):
    arrow(s, bx, 4.62, 0.3, 0.48, GRAY)
for bx in (5.15, 10.75):
    arrow(s, bx, 4.62, 0.3, 0.48, RED, up=True)

text(s, "Demote", 3.1, 3.22, 1.0, 0.28, size=9.5, color=GREEN, bold=True)
text(s, "Promote", 4.28, 3.22, 0.85, 0.28, size=9.5, color=RED, bold=True,
     align=PP_ALIGN.RIGHT)
text(s, "Demote", 3.1, 4.72, 1.0, 0.28, size=9.5, color=GRAY, bold=True)
text(s, "Promote", 4.28, 4.72, 0.85, 0.28, size=9.5, color=RED, bold=True,
     align=PP_ALIGN.RIGHT)

caption(s, "논문 Fig.6을 발표용으로 재작성 — 구조는 원문 그대로이고, 프로그램 라벨(P1~P8)은 설명을 위한 예시입니다.",
        1.85, 6.02, 10.1, size=9)
panel(s, 0.5, 6.15, 12.35, 0.75, PANEL)
text(s, "Demote(아래로) = idle한 쪽을 내린다:  GPU→CPU 오프로드  /  CPU→Waiting KV 폐기        "
        "Promote(위로) = busy한 쪽을 올린다:  CPU→GPU 재로드(PCIe)  /  Waiting→GPU full prefill 재계산",
     0.7, 6.3, 12.0, 0.5, size=11.5)
footer(s, 4)
notes(s, """[그림을 읽는 법]
세로축이 메모리 계층입니다. 위가 GPU HBM, 가운데가 CPU DRAM, 아래가 '아무 데도 없음'.
가로축이 레플리카입니다. GPU 큐와 CPU 큐는 레플리카마다 하나씩 있고,
Waiting 큐만 전역에 하나입니다.

[왜 Waiting만 전역인가 — 설계상 이유가 있습니다]
GPU 큐와 CPU 큐에 있는 프로그램은 특정 레플리카의 물리 메모리를 실제로 점유합니다.
그래서 소속 레플리카가 정해져 있어야 합니다.
반면 Waiting 큐의 프로그램은 KV가 아예 없습니다. 아무 데도 물리적으로 매여 있지
않으니 어느 레플리카로든 갈 수 있습니다. 그래서 전역 큐 하나로 두고, 승격할 때
용량이 있는 레플리카를 골라 보냅니다(§4.3.1의 BFD 빈패킹).

[세 tier의 결정적 차이는 '복귀 비용'입니다]
- GPU 큐: 요청이 오면 엔진으로 그냥 포워딩. 비용 0.
- CPU 큐: 요청이 오면 gating(막아둠). 승격 시 PCIe로 재로드. 컨텍스트 크기에 비례.
- Waiting 큐: 요청이 오면 gating. 승격 시 full prefill로 전부 재계산.
CPU 큐가 존재하는 이유가 이 중간 지점입니다. 기존 ThunderAgent에는 이 층이 없어서
GPU에서 밀리면 곧장 전량 재계산이었습니다.

[불변식 — 재구현 시 assert로 박을 것]
논문이 명시합니다: 한 레플리카의 GPU 큐에 있는 모든 프로그램의 KV 총합이 GPU 메모리
용량을 넘지 않아야 합니다. CPU 큐도 같은 제약을 동일하게 겁니다.
이 두 불변식이 곧 §3.4의 세 번째 문제(CPU admission control)에 대한 답입니다.

[cache affinity — 다음 슬라이드에서 자세히]
CPU 큐가 레플리카별이라는 점이 그냥 구현 편의가 아니라 성능 장치입니다.
오프로드된 KV는 그 계산을 했던 노드의 DRAM에 있으므로, 나중에 승격할 때 같은
레플리카로 보내면 재계산 없이 PCIe로 로컬 재로드만 하면 됩니다.

[그림 속 P6, P7 — CPU Queue (Full)]
Replica 2의 CPU 큐가 꽉 찬 상태를 표현했습니다. 이 상태에서 Replica 2의 GPU 큐에서
누군가를 내려야 하면, CPU에 자리가 없으니 곧바로 Waiting으로 갑니다(§4.3.1).
즉 CPU tier는 무한 완충재가 아니라 용량이 걸린 유한 자원입니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S5 — §4.1 tier 비교표 + affinity
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "§4.1 세 tier의 계약 — 그리고 affinity",
      "tier를 나누는 기준은 'KV가 어디 있나'가 아니라 '돌아올 때 얼마를 내나'다.")

table(s, [
    ["", "GPU 큐", "CPU 큐", "Waiting 큐"],
    ["담는 프로그램", "현재 busy로 분류된 것", "현재 idle로 분류된 것", "두 tier 모두 못 들어간 것"],
    ["KV 위치", "GPU HBM", "같은 노드의 CPU DRAM", "없음 — 전부 폐기"],
    ["들어온 요청 처리", "엔진으로 즉시 포워딩", "GPU 큐로 승격될 때까지 gating",
     "레플리카에 자리 날 때까지 gating"],
    ["복귀 비용", "없음", "PCIe 재로드 (컨텍스트 크기에 비례)", "full prefill 전량 재계산"],
    ["용량 제약", "레플리카의 GPU 메모리 용량", "레플리카의 CPU 메모리 용량 (동일하게 강제)", "-"],
    ["범위", "레플리카별", "레플리카별", "전역 1개 (전 레플리카 공유)"],
], 0.5, 1.72, 12.4, 3.1, fs=10.5, hdr_fs=11,
    col_widths=[2.0, 2.7, 4.15, 3.55],
    hl_rows={4: CREAM})

panel(s, 0.5, 5.0, 6.05, 1.85, GREENBG)
text(s, "CPU 큐가 레플리카별인 것의 부수 효과 = cache affinity [§4.1]",
     0.72, 5.12, 5.6, 0.3, size=12.5, bold=True, color=GREEN)
text(s, "오프로드된 KV는 그 계산을 했던 바로 그 노드의\nDRAM에 있다.\n\n"
        "→ 나중에 GPU로 승격할 때 같은 레플리카로\n   우선 배정하면 재계산 없이\n   로컬 PCIe 재로드만 하면 된다.",
     0.72, 5.45, 5.6, 1.3, size=11.5)

panel(s, 6.85, 5.0, 6.0, 1.85, CREAM)
text(s, "왜 Waiting tier가 필요한가", 7.07, 5.12, 5.5, 0.3, size=12.5,
     bold=True, color=AMBER)
text(s, "GPU도 CPU도 유한하다. 동시 프로그램 수가 두 tier\n용량을 넘으면 초과분은 어딘가로 가야 한다.\n\n"
        "Waiting은 '도망갈 곳'이 아니라 두 tier를\n과부하로부터 지키는 안전밸브다.\n"
        "(§3.4 ③ CPU admission control의 답)",
     7.07, 5.45, 5.6, 1.3, size=11.5)
footer(s, 5)
notes(s, """[표에서 '복귀 비용' 행이 핵심입니다 — 노란 행]
세 tier를 가르는 진짜 기준이 이것입니다. KV가 어디 있느냐는 결과이고,
설계 관점에서 중요한 건 "이 프로그램이 다시 추론하려 할 때 얼마를 내야 하나"입니다.
  GPU: 0
  CPU: 컨텍스트 크기 × (1/PCIe 대역폭)
  Waiting: full prefill — 컨텍스트 전체를 다시 계산
CPU와 Waiting의 비용 차이가 CPU tier를 도입할 가치입니다. 그리고 그 차이는
컨텍스트가 길수록 커집니다. 짧은 컨텍스트면 재계산이 재로드보다 쌀 수도 있어서,
제 실험 계획에는 이 손익분기점을 마이크로벤치로 재는 항목을 넣어뒀습니다.

[gating의 의미 — 구현상 중요합니다]
CPU 큐나 Waiting 큐에 있는 프로그램에 요청이 오면 그 요청을 '막아둡니다'.
엔진으로 보내지 않습니다. 왜냐하면 그 프로그램의 KV가 GPU에 없는 상태에서 요청이
엔진에 도달하면, 엔진이 알아서 재계산을 시작해버려 스케줄러의 용량 계획이 깨지기
때문입니다.
§5에서 이걸 "request handlers block until the scheduler promotes them back"이라고
구현했다고 밝힙니다. 즉 HTTP 핸들러가 실제로 await로 대기합니다.

[affinity를 성능 장치로 읽어야 합니다]
CPU 큐를 레플리카별로 둔 것은 구현 편의가 아닙니다.
만약 CPU 큐도 전역이었다면, 승격할 때 아무 레플리카나 고를 수 있지만 KV는 원래
노드의 DRAM에 있으니 노드 간 전송이 필요하거나 재계산해야 합니다.
레플리카별로 두면 "이 프로그램은 Replica 1의 DRAM에 있다"가 자명하므로
Replica 1로 돌려보내면 로컬 PCIe 재로드로 끝납니다.
논문 §6.2의 멀티레플리카 실험에서 program churn이 TA+O 5.5% vs MORI 2.0%로
낮게 나오는 이유가 이 구조입니다.

[우리 실험에서는]
DP=1이라 레플리카가 하나뿐입니다. 그래서 affinity와 BFD 빈패킹은 사실상 무의미해지고,
평가 범위 밖으로 명시했습니다. 다만 재구현할 때 구조는 논문대로 만들어 두는 게
나중에 DP>1로 확장할 때 편합니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S6 — §4.2 idleness 지표
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "§4.2 idleness 지표 ι — 정의",
      "최근 k 스텝 윈도우에서 '툴에 쓴 시간의 비중'. 0에 가까우면 busy, 1에 가까우면 idle.")

panel(s, 0.5, 1.72, 12.35, 1.35, BLUEBG)
text(s, "ι  =  T_acting^(k)   /   ( T_reasoning^(k)  +  T_acting^(k) )",
     0.7, 1.88, 12.0, 0.55, size=22, bold=True, color=BLUE,
     align=PP_ALIGN.CENTER)
text(s, "^(k) = 최근 k회 추론-툴콜 사이클 동안 해당 status에 머문 총 시간의 합   ·   논문 전 실험에서 k = 5 [§4.2 식(1)]",
     0.7, 2.48, 12.0, 0.4, size=11.5, color=INK, align=PP_ALIGN.CENTER)

bullets(s, [
    ("ι → 1 : idle phase (대부분의 시간을 툴콜에)   ·   ι → 0 : busy phase (대부분의 시간을 추론에) [§4.2]", 0, INK, True),
    ("스케줄러 대기 시간(CPU·Waiting tier에서 큐잉된 시간)은 두 항 모두에서 제외 → 프로그램 고유 행동만 반영 [§4.2]", 0, RED, True),
    ("전역 평균이 아니라 '최근 윈도우'인 이유: 프로그램은 non-stationary하고 phase를 오간다. 전 생애 평균은 현재 phase의 나쁜 추정량 [§4.2]", 0, INK, False),
    ("윈도우가 정당한 근거: phase 전이가 드물다(§3.3) → 최근 행동이 앞으로의 행동에 대한 신뢰할 만한 대리값 [§4.2]", 0, INK, False),
], 0.5, 3.3, 12.4, 2.2, size=13)

panel(s, 0.5, 5.6, 12.35, 1.25, CREAM)
text(s, "이 지표가 노리는 것 [§4.2]", 0.72, 5.72, 6.0, 0.3, size=13,
     bold=True, color=AMBER)
text(s, "앞으로의 시간을 대부분 GPU 추론에 쓸 프로그램(덜 idle)을 찾아 GPU 상주를 우선 배정하고,\n"
        "긴 툴콜에 들어갔거나 들어가려는 프로그램(더 idle)은 그 idle 창을 이용해 KV를 CPU DRAM으로 내려 HBM을 비운다.",
     0.72, 6.06, 11.9, 0.7, size=12)
footer(s, 6)
notes(s, """[식을 말로 풀면]
분모가 '최근 k 사이클의 전체 시간', 분자가 '그중 툴콜에 쓴 시간'입니다.
그래서 ι는 0과 1 사이의 비율이고, "최근에 얼마나 놀았나"를 뜻합니다.
k=5는 논문 전 실험에서 고정입니다. 우리 재구현에서도 --mori-k로 노출하되 기본 5로 두고,
민감도 ablation은 선택 항목으로 미뤄뒀습니다.

[제 기존 트랙의 duty와의 관계]
제가 쓰던 duty d는 "GPU를 실제로 쓰는 시간 비중"입니다. ι = 1 - d 입니다.
같은 것을 반대편에서 본 것이라, 기존 fit x d 좌표계와 그대로 연결됩니다.

[waiting time 제외를 다시 강조하는 이유]
S3에서도 말했지만, 이건 식의 정의에 들어 있는 조건이라 다시 나옵니다.
구현할 때 실수하기 가장 쉬운 지점이기도 합니다. "Acting = 요청이 안 들어온 모든 시간"으로
짜면 자동으로 틀립니다. gating으로 막아둔 시간이 Acting에 섞이기 때문입니다.
정확히는 '툴이 도는 시간'만 Acting이고, '스케줄러가 세워둔 시간'은 어느 쪽도 아닙니다.
계측점을 pause 이전/이후로 나눠야 합니다.

[왜 전역 평균이 아니라 윈도우인가 — 논리 구조를 보세요]
논문의 논증이 두 단계입니다.
(1) 프로그램은 non-stationary하다. 즉 통계적 성질이 시간에 따라 변한다. 그래서 전 생애
    평균은 '지금'을 설명하지 못한다. → 최근 것만 봐야 한다.
(2) 그런데 최근 것만 보면 노이즈에 취약하지 않나? 아니다. §3.3에서 phase 전이가
    드물다는 걸 측정으로 보였으므로, 최근 행동이 가까운 미래의 좋은 대리값이다.
즉 §3.3의 측정(busy phase가 수십 초 지속, 전이 드묾)이 §4.2의 설계를 정당화하는
구조입니다. 측정 → 설계로 이어지는 논문의 논증이 깔끔한 대목입니다.

[k를 크게/작게 하면]
k가 크면 안정적이지만 phase 전이에 늦게 반응합니다. k가 작으면 민감하지만 outlier
하나에 흔들립니다. k=5는 그 절충이고, 다음 슬라이드의 두 성질이 정확히 이 절충의
양면입니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S7 — §4.2 두 가지 성질
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "§4.2 윈도우 지표의 두 가지 성질",
      "빠르게 반응하되 이상치에는 흔들리지 않는다 — 같은 윈도우가 두 성질을 동시에 준다.")

panel(s, 0.5, 1.72, 6.05, 3.5, REDBG)
text(s, "① Responsive — 빠른 반응성", 0.75, 1.88, 5.5, 0.35, size=15,
     bold=True, color=RED)
text(s, "busy → idle 전환 시", 0.75, 2.35, 5.5, 0.3, size=12, bold=True,
     color=INK)
text(s, "진행 중인 툴콜의 경과 시간이 계속 커지면서\n"
        "곧 윈도우의 다른 항들을 압도한다\n→ ι가 빠르게 상승",
     0.75, 2.68, 5.5, 0.9, size=12)
text(s, "idle → busy 전환 시", 0.75, 3.62, 5.5, 0.3, size=12, bold=True,
     color=INK)
text(s, "짧은 툴콜이 연달아 들어오면서\n"
        "긴 idle 툴콜을 슬라이딩 윈도우 밖으로 밀어낸다\n→ ι가 빠르게 하락",
     0.75, 3.95, 5.5, 0.9, size=12)
text(s, "재구현 핵심: 진행 중인 툴콜을 ι에 반영해야 한다",
     0.75, 4.85, 5.5, 0.3, size=11.5, bold=True, color=RED)

panel(s, 6.85, 1.72, 6.0, 3.5, GREENBG)
text(s, "② Robustness — 이상치 내성", 7.1, 1.88, 5.5, 0.35, size=15,
     bold=True, color=GREEN)
text(s, "일시적으로 느린 shell 명령 하나로\n"
        "busy 프로그램이 idle로 잘못 분류되면 안 된다.\n\n"
        "최근 짧은 툴콜들이 채운 윈도우가\n"
        "이 이상치 하나를 희석시킨다\n→ 성급한 재분류를 막는다",
     7.1, 2.35, 5.5, 1.5, size=12)
text(s, "그러나 진짜 전환이면", 7.1, 3.95, 5.5, 0.3, size=12, bold=True,
     color=INK)
text(s, "긴 툴콜이 연속으로 이어지므로\n"
        "ι가 사이클을 거듭하며 상승한다\n→ 결국 올바르게 재분류된다",
     7.1, 4.28, 5.5, 0.9, size=12)

panel(s, 0.5, 5.4, 12.35, 1.4, CREAM)
text(s, "구현 함정 — 논문 본문의 'ongoing tool call'을 놓치면 ①이 통째로 사라진다",
     0.72, 5.52, 9.5, 0.3, size=13, bold=True, color=AMBER)
text(s, "ι를 '툴콜이 끝난 시점'에만 갱신하면, 방금 40분짜리 빌드에 들어간 프로그램의 ι는 직전 5턴 기준의 낮은 값 그대로다.\n"
        "→ value(now) 계산 시 현재 Acting 중이면 (now − acting_since)를 진행 중 항으로 더해, 시간이 갈수록 ι가 단조 증가하게 만들어야 한다.",
     0.72, 5.86, 11.9, 0.8, size=12)
footer(s, 7)
notes(s, """[두 성질이 서로 반대 방향처럼 보이지만 아닙니다]
"빠르게 반응한다"와 "이상치에 안 흔들린다"는 보통 트레이드오프입니다.
그런데 슬라이딩 윈도우가 둘을 동시에 주는 이유는, 두 상황에서 신호의 '크기'가
다르기 때문입니다.
- 진짜 phase 전이: 긴 툴콜이 '연속으로' 온다. 윈도우 안 여러 항이 커진다. ι가 계속 오른다.
- 일시적 이상치: 긴 툴콜이 '하나만' 온다. 나머지 4개 항이 여전히 짧다. 희석된다.
즉 윈도우가 지속성 필터 역할을 합니다. 한 번은 무시하고 계속되면 반응합니다.

[①의 메커니즘을 정확히]
busy → idle 방향은 '진행 중인 툴콜의 경과 시간'이 만듭니다. 툴콜이 아직 안 끝났어도
지금까지 흐른 시간이 계속 커지고, 그게 분자에 들어가면서 다른 항들을 압도합니다.
그래서 40분짜리 빌드에 들어간 지 1분만 지나도 ι가 이미 높아집니다.
idle → busy 방향은 슬라이딩 윈도우의 '밀어내기'가 만듭니다. 짧은 툴콜 5개가 연달아
들어오면 긴 툴콜 항이 윈도우 밖으로 밀려나면서 ι가 뚝 떨어집니다.
k=5라서 5사이클이면 완전히 교체됩니다.

[구현 함정 — 이걸 놓치면 논문 재현이 실패합니다]
가장 자연스러운 구현은 "툴콜이 끝나면 그 길이를 링버퍼에 push"입니다.
이렇게 짜면 ①의 전반부가 통째로 사라집니다. 40분짜리 툴콜은 40분 뒤에야 반영되는데,
그때는 이미 늦었습니다. 우리가 하고 싶었던 건 "지금 긴 툴콜에 들어간 놈을 내리는 것"인데,
그 신호가 40분 뒤에 오는 겁니다.
그래서 ι를 읽는 함수가 시각을 인자로 받아야 합니다. value(now)를 호출할 때 현재
status가 Acting이면 (now - acting_since)를 진행 중 항으로 더해서 계산해야 합니다.
논문 본문의 "the ongoing tool call's elapsed time keeps increasing"이 이 뜻입니다.

[단위 테스트로 고정할 것 3가지]
(a) 짧은 툴콜만 반복 → ι가 0 근처로 수렴
(b) 긴 툴콜 진행 중 → 시간이 갈수록 ι가 단조 증가
(c) 짧은 툴콜 5회 + 긴 툴콜 1회 → ι가 크게 안 튐 (희석 확인)
(c)가 ②를 검증합니다. 이 세 개를 통과해야 지표가 논문대로 동작한다고 말할 수 있습니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S8 — §4.3 sticky rebalancing
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "§4.3 스케줄링 정책 — sticky rebalancing",
      "매 tick마다 재배치하지 않는다. 실제로 어긋났을 때만 움직인다.")

bullets(s, [
    ("주기적 control loop가 tick마다 모든 프로그램의 ι와 각 tier의 용량을 살펴, phase에 맞는 tier 쪽으로 옮긴다 — busy는 GPU로, idle은 CPU로 [§4.3]", 0, INK, False),
    ("그러나 매 tick 적극적으로 뒤섞지 않는다: ι가 다른 프로그램들 대비 분할 경계를 넘지 않는 한 현재 tier에 머문다 [§4.3]", 0, RED, True),
    ("tier 이동은 '실제 mismatch'가 있을 때만 — 예: busy인데 KV가 CPU에 놀고 있다 / idle인데 긴 툴콜 대기 중에 HBM을 점유하고 있다 [§4.3]", 0, INK, True),
    ("옮길 후보를 골라야 할 때는 ι로 순위를 매겨 최상위부터 옮긴다 [§4.3]", 0, INK, False),
    ("stickiness가 중요한 이유: tier 이동은 공짜가 아니다 — GPU→CPU는 offload 비용, 되돌리면 reload 비용 [§4.3]", 0, INK, True),
], 0.5, 1.75, 12.4, 2.7, size=13.5)

panel(s, 0.5, 4.6, 6.05, 2.2, REDBG)
text(s, "sticky가 없으면 — churn", 0.75, 4.73, 5.5, 0.32, size=13.5,
     bold=True, color=RED)
text(s, "ι 랭킹은 매 tick 조금씩 흔들린다.\n"
        "경계 근처의 프로그램들이 tick마다\nGPU↔CPU를 왕복하게 된다.\n\n"
        "이동 비용(offload + reload)이\n스케줄링으로 얻은 이득을 다 까먹는다.",
     0.75, 5.12, 5.6, 1.5, size=12)

panel(s, 6.85, 4.6, 6.0, 2.2, GREENBG)
text(s, "sticky가 주는 것", 7.1, 4.73, 5.5, 0.32, size=13.5, bold=True,
     color=GREEN)
text(s, "필요할 때만 재배치하므로\n불필요한 churn을 피하면서도\n"
        "phase 변화에는 몇 tick 안에 적응한다.\n\n"
        "즉 '반응 속도'를 조금 내주고\n'안정성'을 크게 얻는 교환.",
     7.1, 5.12, 5.6, 1.5, size=12)
footer(s, 8)
notes(s, """[sticky를 한 문장으로]
"맞는 자리에 있으면 그냥 둔다. 틀린 자리에 있을 때만 옮긴다."

[왜 이게 당연하지 않은가]
순진하게 짜면 이렇게 됩니다: 매 tick마다 모든 프로그램을 ι로 정렬하고, 위에서부터
GPU 용량만큼 잘라 GPU에 넣고, 나머지는 CPU에 넣는다.
논리적으로는 항상 최적 배치입니다. 그런데 실제로는 재앙입니다.
ι는 연속값이라 매 tick 조금씩 변합니다. 경계선 바로 위아래에 있는 프로그램들은
순위가 엎치락뒤치락하면서 tick마다 tier를 왕복합니다.
왕복 한 번에 offload + reload 비용을 냅니다. 컨텍스트가 6만 토큰이면 8.6 GiB를
PCIe로 왔다 갔다 하는 겁니다. 스케줄링으로 얻은 이득이 전송 비용에 다 먹힙니다.

[그래서 조건을 mismatch로 바꿉니다]
"최적 배치인가"가 아니라 "실제로 어긋났는가"를 묻습니다.
논문이 드는 mismatch 예가 두 가지입니다:
 - busy 프로그램인데 KV가 CPU에 있다 (곧 추론할 건데 재로드를 물어야 함)
 - idle 프로그램인데 GPU HBM을 점유하고 있다 (긴 툴콜 대기 중인데 메모리를 낭비)
이 둘 중 하나가 성립할 때만 움직입니다. 그리고 움직여야 할 때, 누구를 옮길지는
ι 순위로 정합니다 — 즉 ι는 '옮길지 말지'가 아니라 '누구를 먼저 옮길지'에 쓰입니다.

[논문이 명시한 트레이드오프]
"avoids unnecessary churn while still adapting to phase changes within a few ticks."
몇 tick 안에는 적응한다는 것이 보장 조건입니다. tick이 5초이니 phase 전환 후
10~20초 안에는 올바른 tier로 갑니다. §3.3에서 busy phase가 median 20초, p90 81초라고
측정했으니, 이 정도 반응 속도면 phase 길이에 비해 충분히 빠릅니다.
여기서도 측정(§3.3)이 설계 파라미터(tick 5초)를 정당화합니다.

[재구현 시 추가로 넣기로 한 것]
논문에는 명시가 없지만, 저는 진동 방지를 위해 두 가지를 더 넣을 계획입니다:
한 tick 안에서 같은 프로그램의 demote와 promote를 동시에 하지 않기(불변식 I5),
그리고 tier 이동 후 최소 체류 tick(min_dwell) 두기.
논문의 sticky 서술을 구현으로 옮길 때 자연스럽게 필요한 안전장치입니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S9 — §4.3.1 Demotion
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "§4.3.1 Demotion — GPU에서 누구를 내리나",
      "GPU 큐 KV 총합이 용량을 넘으면, 예산 안에 들어올 때까지 내린다.")

table(s, [
    ["순서", "규칙 [§4.3.1]", "이유"],
    ["1", "Acting 프로그램을 Reasoning 프로그램보다 먼저 내린다",
     "Acting의 KV는 GPU에서 놀고 있고, Reasoning은 지금 실제로 추론 중이다"],
    ["2", "같은 status 안에서는 ι가 가장 높은 것부터",
     "idle phase에 이미 들어갔거나 들어가는 중일 가능성이 가장 큰 프로그램"],
    ["3", "Reasoning만 남았으면 lazy demotion — 현재 추론 스텝을 끝낸 뒤 이동",
     "진행 중인 스텝을 중간에 끊지 않는다"],
    ["4", "목적지: CPU 용량이 허락하면 CPU 큐, 아니면 Waiting 큐",
     "CPU가 꽉 찼으면 KV를 버릴 수밖에 없다"],
], 0.5, 1.75, 12.4, 2.5, fs=10.5, hdr_fs=11,
    col_widths=[0.75, 5.6, 6.05], hl_rows={2: CREAM})

bullets(s, [
    ("내려간 프로그램은 엔진으로부터 gating되고, 남은 프로그램들의 KV는 보존된다 [§4.3.1]", 0, INK, False),
    ("정렬키가 '컨텍스트 크기'가 아니라 'ι'라는 점이 ThunderAgent와의 결정적 차이 — TA는 total_tokens 오름차순으로 고른다", 0, RED, True),
], 0.5, 4.42, 12.4, 0.9, size=13)

panel(s, 0.5, 5.4, 12.35, 1.4, PANEL)
text(s, "우선순위를 두 단계로 나눈 것이 설계의 요점", 0.72, 5.52, 8.0, 0.32,
     size=13, bold=True, color=BLUE)
text(s, "1단계(status)는 '지금 GPU를 실제로 쓰고 있나'라는 확실한 사실 — 틀릴 여지가 없다.\n"
        "2단계(ι)는 '앞으로 얼마나 안 쓸 것 같나'라는 추정 — 틀릴 수 있다.\n"
        "→ 확실한 정보를 먼저 쓰고, 그것으로 못 가르는 동률 안에서만 추정을 쓴다.",
     0.72, 5.86, 11.9, 0.85, size=12)
footer(s, 9)
notes(s, """[전체 흐름]
트리거는 하나입니다: GPU 큐 프로그램들의 KV 총합이 GPU 메모리 용량을 넘었을 때.
그러면 예산 안에 들어올 때까지 프로그램을 내립니다. 몇 개를 내릴지는 용량이 정하고,
누구를 내릴지를 이 표가 정합니다.

[1단계와 2단계를 나눈 이유 — 여기가 이 슬라이드의 핵심입니다]
왜 그냥 ι가 제일 높은 놈부터 내리지 않을까요?
status는 관측된 사실입니다. 'Acting이다'는 곧 '지금 이 순간 GPU에서 아무 일도 안 하고
있다'는 뜻이고, 여기엔 추정이 없습니다.
ι는 추정입니다. '앞으로도 오래 안 쓸 것 같다'는 예측이고, 틀릴 수 있습니다.
그래서 확실한 정보(status)로 먼저 가르고, 그걸로 구분이 안 되는 동률 그룹 안에서만
추정(ι)을 씁니다. 추정을 확실한 정보보다 앞세우지 않는다 — 스케줄러 설계의 상식적인
원칙이고, 논문이 이 순서를 지켰습니다.
실제로 Reasoning 중인 프로그램은 ι가 아무리 높아도 Acting 프로그램보다 나중에 내려갑니다.

[lazy demotion]
내릴 대상이 Reasoning 프로그램밖에 없는 상황이 생깁니다(전부 추론 중일 때).
이때 진행 중인 스텝을 중간에 끊지 않고, 그 스텝이 끝날 때까지 기다렸다가 옮깁니다.
논문 용어로 lazy demotion입니다.
ThunderAgent에는 이 메커니즘이 이미 있습니다 — marked_for_pause 플래그를 세워두고
update_program_after_request에서 처리합니다. 그대로 재사용할 수 있습니다.

[ThunderAgent와의 차이 — 재구현 시 실제로 바꾸는 곳]
TA의 _pause_until_safe는 ACTING 우선까지는 같은데, 같은 status 안에서 total_tokens
오름차순(작은 것부터)으로 고릅니다. 즉 '컨텍스트가 작은 놈부터' 내립니다.
MORI는 여기를 ι 내림차순으로 바꿉니다. 그리고 목적지가 다릅니다 — TA는 무조건
Waiting(KV 폐기)인데 MORI는 CPU 큐를 먼저 시도합니다.
정렬키 교체와 목적지 추가, 이 두 줄이 demotion에서 바뀌는 전부입니다.

[목적지 결정에 용량 검사가 들어간다는 점]
"CPU 용량이 허락하면"이 조건입니다. CPU 큐도 admission control이 걸려 있으므로,
내리려는 프로그램의 KV 크기가 CPU 여유 용량 안에 들어가는지 확인해야 합니다.
안 들어가면 Waiting으로 갑니다. §3.4의 세 번째 문제에 대한 답이 여기서 실행됩니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S10 — §4.3.1 Promotion
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "§4.3.1 Promotion — GPU에 누구를 올리나",
      "GPU에 자리가 나면 3단계 우선순위. 각 단계 안에서는 ι가 가장 낮은 것부터.")

table(s, [
    ["우선순위", "대상 [§4.3.1]", "왜 이 순서인가"],
    ["1", "CPU 큐 프로그램 중 툴콜을 마치고 추론을 기다리는 것",
     "이미 요청이 대기 중이고, 복귀 비용이 재로드로 가장 싸다"],
    ["2", "Waiting 큐에서 추론을 기다리는 것 — 복귀 프로그램을 신규 도착보다 우선",
     "복귀 프로그램은 진행 중인 작업이 있다"],
    ["3", "새로 도착한 프로그램 — 컨텍스트가 작은 것부터",
     "작은 것부터 넣어야 더 많이 수용된다"],
], 0.5, 1.75, 12.4, 1.95, fs=10.5, hdr_fs=11,
    col_widths=[1.1, 5.65, 5.65])

bullets(s, [
    ("각 우선순위 단계 안에서는 ι가 가장 낮은 것부터 — busy phase에 있거나 들어가는 중일 가능성이 가장 커, GPU 상주를 가장 잘 활용할 프로그램 [§4.3.1]", 0, RED, True),
], 0.5, 3.85, 12.4, 0.65, size=13)

text(s, "멀티레플리카일 때 [§4.3.1]", 0.5, 4.55, 6.0, 0.35, size=14,
     bold=True, color=BLUE)

panel(s, 0.5, 4.98, 6.05, 1.85, PANEL)
text(s, "Waiting → GPU 승격", 0.75, 5.1, 5.5, 0.3, size=12.5, bold=True,
     color=INK)
text(s, "Best-Fit-Decreasing 빈패킹으로\n레플리카를 고른다 —\n"
        "여유 용량이 가장 많은 레플리카 우선.\n\n"
        "(KV가 없으니 어느 레플리카로든 갈 수 있다)",
     0.75, 5.45, 5.6, 1.3, size=11.5)

panel(s, 6.85, 4.98, 6.0, 1.85, GREENBG)
text(s, "CPU → GPU 승격", 7.1, 5.1, 5.5, 0.3, size=12.5, bold=True, color=INK)
text(s, "레플리카 affinity를 보존한다 —\n"
        "KV가 있는 바로 그 노드로 되돌린다.\n\n"
        "(다른 레플리카로 보내면 로컬 재로드의\n 이점이 사라진다)",
     7.1, 5.45, 5.6, 1.3, size=11.5)
footer(s, 10)
notes(s, """[Demotion과 정확히 대칭입니다]
Demotion은 ι가 '가장 높은' 것부터 내렸습니다. Promotion은 ι가 '가장 낮은' 것부터
올립니다. 같은 랭킹의 양 끝을 쓰는 셈입니다.
직관도 대칭입니다 — 내릴 때는 "가장 오래 안 돌아올 놈", 올릴 때는 "가장 빨리 쓸 놈".

[3단계 우선순위의 논리]
1순위가 CPU 큐인 이유는 두 가지가 겹칩니다. (a) 이미 툴콜을 마치고 요청이 대기 중이다
= 올리면 즉시 일한다. (b) 복귀 비용이 재로드뿐이라 가장 싸다.
즉 '효과가 가장 크고 비용이 가장 싼' 후보라 맨 앞입니다.
2순위 Waiting 안에서 복귀 > 신규인 이유는, 복귀 프로그램은 이미 진행 중인 작업이
있어서 끝내주는 게 낫기 때문입니다. 신규는 아직 아무것도 시작 안 했으니 조금 더
기다려도 손실이 적습니다.
3순위 신규에서 '작은 컨텍스트 먼저'는 빈패킹 휴리스틱입니다. 같은 여유 용량에
더 많은 프로그램을 넣을 수 있습니다.

[BFD와 affinity가 다른 이유 — 질문 나올 만한 대목]
왜 Waiting 승격은 BFD로 레플리카를 고르고, CPU 승격은 원래 레플리카로 고정할까요?
Waiting 프로그램은 KV가 없습니다. 어디로 가든 full prefill을 새로 해야 하므로
어느 레플리카로 가든 비용이 같습니다. 그러면 부하 균형만 보면 되니 여유가 가장 많은
곳으로 보냅니다(BFD).
CPU 프로그램은 KV가 특정 노드의 DRAM에 있습니다. 다른 레플리카로 보내면 그 KV를
못 쓰고 재계산해야 합니다. CPU tier를 둔 의미가 사라집니다. 그래서 affinity 고정입니다.
결국 "KV가 물리적으로 매여 있느냐"가 두 정책을 가릅니다.

[우리 실험에서는]
DP=1이라 레플리카가 하나뿐이므로 BFD와 affinity 둘 다 실질적으로 무의미해집니다.
논문 §6.2.2의 멀티레플리카 결과(throughput +54~79%, churn 5.5%→2.0%)가 우리
재현 범위 밖인 이유가 이것입니다. 구조는 논문대로 만들어 두되 평가는 하지 않습니다.

[gating 해제 시점]
승격이 실제로 일어나는 시점에 대기 중이던 요청 핸들러를 깨웁니다. 중요한 건
'GPU 큐로 승격될 때만' 깨운다는 점입니다. CPU 큐에 있는 동안에는 요청이 계속
막혀 있어야 합니다 — KV가 아직 GPU에 없으니까요.""")


# ══════════════════════════════════════════════════════════════════════════
# S11 — §4.3.2 Typed offloading
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "§4.3.2 Typed offloading — 스케줄러 결정을 엔진까지 관철시키기",
      "스케줄러는 '어느 프로그램'을 정하고, 엔진은 '어느 블록'을 버린다. 둘을 일치시키는 장치.")

bullets(s, [
    ("문제: 스케줄러가 배치를 정해도, 실제 KV 블록을 관리하고 메모리 압박 시 축출하는 것은 엔진이다 [§4.3.2]", 0, INK, False),
    ("해법: 스케줄러가 프로그램의 type 라벨을 엔진의 KV 캐시 트리 노드까지 전파한다 — GPU 큐=busy, CPU 큐=idle, Waiting 큐=inactive [§4.3.2]", 0, INK, True),
    ("각 요청이 program ID를 싣고 오므로, 엔진이 radix tree에 KV 블록을 삽입할 때 그 프로그램의 type을 스탬프한다 [§4.3.2]", 0, INK, False),
    ("ι가 상대값이므로, 이 라벨도 '다른 활성 프로그램들과 현재 하드웨어 용량 대비 상대적 위치'를 반영한다 [§4.3.2]", 0, INK, False),
], 0.5, 1.72, 12.4, 2.2, size=13)

text(s, "축출 순서 — 핵심은 LRU를 버리는 게 아니라 type을 상위 정렬키로 얹는 것 [§4.3.2]",
     0.5, 3.92, 9.5, 0.35, size=13.5, bold=True, color=BLUE)

table(s, [
    ["tier", "축출 우선순위 (먼저 버리는 순)", "결과"],
    ["GPU HBM", "inactive  →  idle  →  busy", "busy 프로그램의 블록이 가장 마지막에 축출된다"],
    ["CPU DRAM", "inactive  →  busy  →  idle", "idle 프로그램의 블록이 가장 마지막에 축출된다"],
], 0.5, 4.35, 7.7, 1.15, fs=11.5, hdr_fs=11,
    col_widths=[1.5, 3.3, 2.9], hl_rows={2: CREAM})
caption(s, "같은 type 안에서는 LRU가 tie-break. 두 tier 모두 inactive를 먼저 버리고, busy/idle 순서만 뒤집힌다.",
        0.5, 5.55, 7.7, size=9.5)

panel(s, 8.42, 4.35, 4.43, 1.5, REDBG)
text(s, "★ 계획서 오기 정정", 8.62, 4.45, 4.0, 0.3, size=12.5, bold=True,
     color=RED)
text(s, "계획서 §B-Phase2: \"CPU tier = busy → idle → inactive (완전 반전)\"\n"
        "논문 원문: inactive → busy → idle\n"
        "→ inactive는 양쪽 tier 모두 1순위. 재구현 시 정정 필요.",
     8.62, 4.78, 4.05, 1.0, size=10.5)

panel(s, 0.5, 5.95, 12.35, 0.85, GREENBG)
text(s, "덤: 같은 type 라벨이 엔진의 배치 스케줄링에도 쓰인다 [§4.3.2] — "
        "다음 batch에 어떤 대기 요청을 넣을지 정할 때 busy-typed 요청을 idle-typed보다 먼저 admit해, "
        "스케줄러가 GPU에 올려둔 프로그램이 신속히 서빙되도록 보장한다.",
     0.7, 6.1, 12.0, 0.6, size=11.5)
footer(s, 11)
notes(s, """[이 절이 없으면 §4.3 전체가 헛돕니다]
스케줄러가 "P3는 CPU에 둬라"라고 결정해도, 엔진이 자기 LRU로 P3의 블록을 GPU에서
그냥 버려버리면 스케줄러의 결정은 아무 의미가 없습니다.
반대로 스케줄러가 "P1은 GPU에 유지"라고 했는데 엔진 LRU가 P1을 축출하면,
P1은 곧 추론할 건데 재계산을 물게 됩니다.
즉 스케줄러의 '프로그램 수준' 결정과 엔진의 '블록 수준' 결정이 어긋나면 안 됩니다.
§4.3.2가 그 두 층을 잇는 다리입니다.

[전파 경로 — 재구현 시 가장 어려운 부분]
경로가 이렇습니다: 스케줄러가 tier 배치 → 프로그램에 type 라벨(busy/idle/inactive) 부여
→ 요청이 program ID를 싣고 엔진에 도착 → 엔진이 radix tree에 블록 삽입할 때 그
프로그램의 type을 노드에 스탬프 → 축출 시 그 스탬프를 상위 정렬키로 사용.
문제는 SGLang의 radix 노드가 토큰 ID prefix로 키잉되고 program ID를 native로 담지
않는다는 점입니다. 그래서 rid → program → type 매핑을 노드 삽입 경로까지 전파할 수
있는지가 우리 재구현의 미해결 과제(OQ-F)입니다.
못 하면 Phase 2를 "host tier 용량 제어만, typed eviction 없이"로 축소하고 명기해야 합니다.

[축출 순서 — 왜 반전인가]
각 tier가 '자기에게 배정된 프로그램'을 우선 보존하도록 만든 것입니다.
GPU는 busy를 위한 자리이므로 busy를 마지막까지 지킵니다.
CPU는 idle을 위한 자리이므로 idle을 마지막까지 지킵니다.
inactive(Waiting)는 어차피 KV를 버리기로 한 프로그램이므로 양쪽 tier 모두에서
1순위로 버립니다. 여기에 반전이 없습니다.
따라서 반전되는 것은 busy와 idle의 상대 순서뿐입니다.

[★ 계획서 오기 — 이번에 발견했습니다. 발표에서 짚고 넘어가세요]
제 계획서 §B-Phase2에 CPU tier 축출 순서를 "busy → idle → inactive"로 적어뒀습니다.
전체를 뒤집은 것으로 이해한 건데, 논문 원문은 "inactive → busy → idle"입니다.
inactive가 양쪽 tier 모두에서 1순위라는 점을 놓친 오기입니다.
구현에 직접 영향이 있습니다 — 제 버전대로 짜면 이미 버리기로 한 Waiting 프로그램의
블록을 CPU DRAM에 가장 오래 남기게 되어, 정작 곧 GPU로 올라갈 idle 프로그램의
블록을 먼저 버리게 됩니다. 정확히 반대 동작입니다.
계획서를 수정해야 합니다.

[LRU를 버리지 않는다는 점도 중요]
논문 표현이 "The engine's eviction policy remains LRU at its core, but uses the type
label as a higher-priority sort key"입니다. LRU를 대체하는 게 아니라 그 위에 한 겹
얹는 것입니다. 같은 type 안에서는 여전히 LRU입니다.
구현 관점에서는 정렬 비교 함수에 키를 하나 추가하는 정도라 침습이 작습니다.
논문이 SGLang 쪽 수정을 500줄로 끝낸 이유이기도 합니다.

[배치 admission에도 쓴다 — 놓치기 쉬운 문장]
type 라벨이 축출에만 쓰이는 게 아니라 엔진의 배치 스케줄링에도 쓰입니다.
다음 batch에 어떤 대기 요청을 넣을지 정할 때 busy-typed를 idle-typed보다 먼저
admit합니다. 스케줄러가 GPU에 올려둔 프로그램이 정작 배치에서 밀려 늦게 서빙되면
곤란하니, 그 일관성까지 맞춘 것입니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S12 — §5 구현
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "§5 구현",
      "ThunderAgent + SGLang v0.5.10. 클라이언트에 요구하는 것은 program_id 하나뿐.")

table(s, [
    ["항목", "내용 [§5]"],
    ["기반", "ThunderAgent [24] + SGLang [68] v0.5.10"],
    ["코드 규모", "ThunderAgent 스케줄러에 Python 약 3,300줄  +  SGLang 캐시 서브시스템(HiCache 경유)에 약 500줄"],
    ["User API", "표준 OpenAI 호환 chat/completion API에 program_id 필드를 추가한 것"],
    ["클라이언트 요구사항", "같은 에이전트 프로그램의 모든 요청에 같은 program_id를 붙일 것. "
     "서브에이전트를 스폰하면 서브에이전트는 별도 식별자를 쓴다. 이것이 클라이언트 측 요구사항의 전부 — "
     "툴콜 주석이나 phase 힌트는 요구하지 않는다"],
    ["스케줄러", "ThunderAgent 라우터 프로세스 안의 비동기 control loop (기본 tick 5 s), §4.3 정책 구현"],
    ["gating 구현", "demote된 프로그램의 요청 핸들러는 스케줄러가 다시 승격시킬 때까지 block — "
     "프로그램의 KV가 GPU에 상주하기 전에는 어떤 추론 요청도 엔진에 도달하지 않음을 보장"],
    ["멀티레플리카", "CPU 큐 승격이 자연히 레플리카별 affinity를 보존한다"],
], 0.5, 1.72, 12.4, 3.85, fs=10.5, hdr_fs=11,
    col_widths=[2.35, 10.05], hl_rows={4: CREAM, 6: BLUEBG})

panel(s, 0.5, 5.75, 6.05, 1.1, GREENBG)
text(s, "설계상 미덕: 최소 침습", 0.72, 5.85, 5.5, 0.3, size=12.5, bold=True,
     color=GREEN)
text(s, "에이전트 코드를 고칠 필요가 없다. 요청에 ID 하나만 붙이면 되고, "
        "툴이 얼마나 걸릴지 미리 알려줄 필요도 없다.",
     0.72, 6.18, 5.6, 0.6, size=11.5)

panel(s, 6.85, 5.75, 6.0, 1.1, CREAM)
text(s, "§5가 짧은 이유", 7.07, 5.85, 5.5, 0.3, size=12.5, bold=True,
     color=AMBER)
text(s, "엔진 쪽 구현의 실질은 §4.3.2(typed offloading)에 이미 서술돼 있다. "
        "§5는 그 위의 배선만 정리한다.",
     7.07, 6.18, 5.6, 0.6, size=11.5)
footer(s, 12)
notes(s, """[코드 규모를 어떻게 읽을까]
스케줄러 3,300줄 + 엔진 500줄입니다. 비대칭이 큽니다.
엔진 쪽이 500줄로 끝나는 이유는 §4.3.2에서 봤듯이 LRU를 대체하는 게 아니라 정렬키를
하나 얹는 방식이라 침습이 작기 때문입니다.
스케줄러 3,300줄은 3-tier 큐 관리, ι 추적, 주기적 control loop, 멀티레플리카 라우팅,
gating과 그 동시성 처리 전부를 포함한 숫자로 보입니다.

[우리 추정과의 격차 — 정직하게 말할 부분]
제 재구현 계획의 추정은 신규 약 760줄 + 엔진 약 500줄입니다. 엔진 쪽은 논문과
비슷한데 스케줄러 쪽이 4배 이상 차이 납니다.
차이의 상당 부분은 DP=1이라 멀티레플리카 affinity LB와 BFD 빈패킹을 안 만들기
때문으로 보입니다. 또 저는 ThunderAgent의 기존 큐 관리·프록시 기계를 그대로
상속받아 쓰므로 새로 쓸 코드가 적습니다.
다만 우리가 뭔가를 빠뜨렸을 가능성도 열어두고, Phase 1 완료 후 재점검하기로 했습니다.

[User API의 최소성이 논문의 세일즈 포인트]
"This is the only client-side requirement; no tool-call annotations or phase hints
are needed."
이 문장이 중요합니다. 경쟁 접근 중에는 "툴이 얼마나 걸릴지 예측해서 알려달라"거나
"이건 긴 작업이라고 표시해달라"는 식으로 클라이언트에 부담을 지우는 것들이 있는데,
MORI는 ID 하나만 요구합니다. 나머지는 전부 관측으로 추론합니다.
§3.2에서 "predicting individual tool-call durations ahead of time is unreliable"라고
예측 기반 접근을 배제한 것과 일관됩니다 — 예측하지 않고 최근 관측으로만 갑니다.

[서브에이전트는 별도 program_id]
논문은 서브에이전트에 독립 식별자를 부여합니다. 즉 서브에이전트가 부모와 별개의
프로그램으로 스케줄링됩니다.
우리 trace(TraceLab)에서는 이게 불가능합니다 — 원본에 parent_session_id나 agent_type
필드가 없고, 서브에이전트 실행 전체가 부모의 단일 긴 툴콜로 접혀 있습니다.
그래서 session=program 1:1로 가고, 이건 한계로 명기했습니다.

[gating 구현 — 우리 코드에도 이미 있는 구조]
"Request handlers block until the scheduler promotes them back."
ThunderAgent에는 waiting_event(asyncio.Event)와 _wait_for_resume이 이미 있어서
같은 방식으로 동작합니다. MORI에서 달라지는 건 '언제 event를 set하느냐'입니다 —
GPU 큐로 승격될 때만 set해야 하고, CPU 큐에 있는 동안에는 계속 막아둬야 합니다.
제 재구현 계획의 불변식 I3이 이것을 고정합니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S13 — 정리
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "정리 — 설계 결정과 그 근거",
      "다섯 결정이 §3의 관찰·요구사항과 1:1로 이어진다. 그래서 하나라도 빼면 나머지가 헛돈다.")

table(s, [
    ["설계 결정", "무엇을 푸는가", "근거 절"],
    ["program ID로 생애 추적, status/phase 구분",
     "요청 단위 스케줄러가 표현하지 못하는 '다시 올 때까지의 시간'을 표현", "§4.1, §3.1"],
    ["연속값 ι + 상대 순위 (k=5 윈도우)",
     "고정 임계·고정 분류가 하드웨어·시간에 따라 반드시 틀리는 문제", "§4.2, §3.4 ②"],
    ["3-tier (GPU / CPU / Waiting) + 양쪽 tier 용량 강제",
     "KV 폐기와 유지 사이의 중간 지점 제공 + CPU 쪽 thrashing 방지", "§4.1, §3.4 ③"],
    ["sticky rebalancing (mismatch일 때만 이동)",
     "tier 이동 비용이 스케줄링 이득을 잠식하는 churn", "§4.3"],
    ["typed offloading (type = 상위 정렬키, LRU = tie-break)",
     "엔진의 블록 수준 축출이 스케줄러의 프로그램 수준 결정을 무시하는 문제", "§4.3.2, §3.4 ①"],
], 0.5, 1.72, 12.4, 3.0, fs=10.5, hdr_fs=11,
    col_widths=[4.3, 6.55, 1.55])

text(s, "내 재구현에서 실제로 바꿔야 하는 지점", 0.5, 4.92, 7.0, 0.35,
     size=14, bold=True, color=BLUE)
bullets(s, [
    ("demotion 정렬키: total_tokens 오름차순 → ι 내림차순, 목적지에 CPU 큐 추가 [§4.3.1]", 0, INK, False),
    ("promotion 정렬키: 각 우선순위 그룹 안에서 ι 오름차순, CPU 큐를 최상위 그룹으로 [§4.3.1]", 0, INK, False),
    ("ι는 반드시 value(now) 형태로 — 진행 중 툴콜의 경과 시간을 포함해야 한다 [§4.2]", 0, RED, True),
    ("typed eviction: rid → program → type 스탬프 경로 확보가 관문(미해결). 실패 시 host 용량 제어만으로 축소하고 명기 [§4.3.2]", 0, RED, True),
    ("계획서 §B-Phase2의 CPU tier 축출 순서를 'inactive → busy → idle'로 정정 [§4.3.2]", 0, RED, True),
], 0.5, 5.32, 12.4, 1.6, size=12, gap=4)
footer(s, 13)
notes(s, """[이 표가 이 발표의 결론입니다]
MORI는 다섯 개의 독립적인 아이디어를 모아둔 게 아닙니다. §3에서 관찰한 문제 하나하나에
대응하는 답들이고, 서로 물려 있습니다.
- program 단위로 안 보면 ι를 정의할 수조차 없습니다.
- ι가 없으면 누구를 옮길지 정할 수 없습니다.
- 3-tier가 없으면 옮길 곳이 없습니다.
- sticky가 없으면 옮기는 비용이 이득을 먹습니다.
- typed offloading이 없으면 옮기라는 결정이 엔진에서 무시됩니다.
그래서 하나라도 빼면 나머지가 헛돕니다. 발표에서 이 연결을 강조하는 게 좋습니다.

[Phase 1과 Phase 2의 경계가 이 표에서 보입니다]
위 네 개(program 추적, ι, 3-tier, sticky)는 전부 스케줄러 안에서 끝납니다.
마지막 하나(typed offloading)만 엔진 수정이 필요합니다.
제가 재구현을 Phase 1(스케줄러 전용) / Phase 2(엔진 연동)로 나눈 근거가 이것입니다.
Phase 1만으로도 "상대 idleness 랭킹이 context-length 랭킹보다 낫다"는 핵심 주장을
TA vs MORI(sim)로 검증할 수 있습니다.
다만 Phase 1에서는 CPU tier가 장부상 큐이고 재로드 비용이 실측이 아니라 모델이므로,
Phase 2 결과와 반드시 대조하고 어긋나면 Phase 1 결론을 철회하기로 했습니다.

[가장 큰 미해결 리스크]
typed eviction의 스탬프 경로입니다. SGLang의 radix 노드는 토큰 ID prefix로 키잉되고
program ID를 담지 않습니다. rid에서 program을 거쳐 type까지 노드 삽입 경로로
전파할 수 있는지 소스로 확인해야 합니다(OQ-F).
불가능하면 Phase 2를 "hicache_ratio로 host tier 용량만 제어, typed eviction 없음"으로
축소하고 그 사실을 한계에 명기합니다. 조용히 넘어가지 않습니다.

[오늘 발견한 것 하나 더]
계획서의 CPU tier 축출 순서 오기(S11)입니다. 논문을 정독하지 않았으면 그대로 구현할
뻔했고, 구현했다면 정확히 반대로 동작했을 겁니다.
설계 절을 이렇게 문장 단위로 다시 읽는 작업이 필요했던 이유입니다.""")


prs.save(OUT)
print(f"saved: {OUT}")
print(f"slides: {len(prs.slides.__iter__.__self__._sldIdLst)}")
