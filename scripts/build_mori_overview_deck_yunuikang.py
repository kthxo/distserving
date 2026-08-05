#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MORI on ThunderAgent — 연구실/지도교수 발표용 개요 데크 (한국어, 22슬라이드).

수치 출처 규약 (지어낸 값 0개):
  [논문]  MORI.pdf(arXiv:2606.00866v1) 원문 직접 대조 완료.
          2026-07-30 PDF 확보 후 Fig.3 / Fig.5 / Table 1 / Table 2 / §6.2 본문을
          전수 대조하여, 이전 판의 미검증(논문?) 29건을 전부 검증으로 승격.
  [§C-4]  계획서 goguma6판 §C-4 측정표 (원본 gz per-call n=431,905 /
          human-wait gap n=33,501). §C-1/§C-3/§5-(12)도 같은 방식으로 § 병기.
  [실측]  본 서버 실측 (nvidia-smi / free / nproc / 계획서 실측표).
  [결정]  설계·결정값 (계획서 승인 결정).
  [계산]  실측값으로부터의 산술 유도.
  TBD(미측정) — 확인 불가. 추정치를 사실처럼 쓰지 않는다.

근거 문서:
  MORI.pdf (arXiv:2606.00866v1, 15p)
  plans/2026-07-30_PLAN_mori-on-thunderagent_yunuikang.md            (base, nutella/vLLM)
  plans/2026-07-30_PLAN_mori-on-thunderagent-goguma6_yunuikang.md    (goguma6/SGLang 재계산판)
  ThunderAgent/{scheduler/router.py, backend/state.py, config.py, __main__.py, program/state.py}
그림: figures/mori_trace_pctile_yunuikang.png (scripts/plot_mori_trace_cdf_yunuikang.py)
      figures/mori_fig3_match_yunuikang.png  (scripts/plot_mori_fig3_match_yunuikang.py)

Output: slides/2026-07-30_MORI-on-thunderagent_overview_yunuikang.pptx
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from PIL import Image

ROOT = "/home/yunuikang/yunuikang_work/distserving"
FIGS = os.path.join(ROOT, "figures")
OUT = os.path.join(ROOT, "slides",
                   "2026-07-30_MORI-on-thunderagent_overview_yunuikang.pptx")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

# ── palette (house style, build_p1_results_deck 계승) ──────────────────────
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

SW, SH = Inches(13.333), Inches(7.5)
prs = Presentation()
prs.slide_width, prs.slide_height = SW, SH


# ── primitives ────────────────────────────────────────────────────────────
def blank():
    return prs.slides.add_slide(prs.slide_layouts[6])


def _style(tf, size, color, bold=False, italic=False, align=PP_ALIGN.LEFT):
    tf.word_wrap = True
    for p in tf.paragraphs:
        p.alignment = align
        for r in p.runs:
            r.font.size = Pt(size)
            r.font.color.rgb = color
            r.font.bold = bold
            r.font.italic = italic
            r.font.name = FONT


def text(slide, s, x, y, w, h, size=13, color=INK, bold=False,
         italic=False, align=PP_ALIGN.LEFT):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tb.text_frame.text = s
    _style(tb.text_frame, size, color, bold, italic, align)
    return tb


def title(slide, s, sub=None):
    text(slide, s, 0.45, 0.26, 12.5, 0.7, size=26, bold=True)
    band(slide, 0.45, 0.95, 12.44, 0.035, BLUE)
    if sub:
        text(slide, sub, 0.45, 1.03, 12.5, 0.5, size=14, color=BLUE,
             bold=True, italic=True)


def band(slide, x, y, w, h, color):
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y),
                                Inches(w), Inches(h))
    sh.fill.solid(); sh.fill.fore_color.rgb = color
    sh.line.fill.background(); sh.shadow.inherit = False
    return sh


def panel(slide, x, y, w, h, color=PANEL):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x),
                                Inches(y), Inches(w), Inches(h))
    sh.fill.solid(); sh.fill.fore_color.rgb = color
    sh.line.color.rgb = RGBColor(0xD8, 0xDD, 0xE6); sh.line.width = Pt(0.75)
    sh.shadow.inherit = False
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
    """items: (text, level, color, bold)"""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame; tf.word_wrap = True
    for i, (txt, lvl, col, bd) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = ("- " if lvl else "* ") + txt
        p.level = lvl
        p.space_after = Pt(gap)
        for r in p.runs:
            r.font.size = Pt(size - (1.0 if lvl else 0))
            r.font.color.rgb = col
            r.font.bold = bd
            r.font.name = FONT
    return tb


def table(slide, rows, x, y, w, h, fs=11, hdr_fs=11, col_widths=None,
          hl_rows=None, zebra=True, hdr_bg=INK, left_cols=1):
    nr, nc = len(rows), len(rows[0])
    t = slide.shapes.add_table(nr, nc, Inches(x), Inches(y),
                               Inches(w), Inches(h)).table
    if col_widths:
        for j, cw in enumerate(col_widths):
            t.columns[j].width = Inches(cw)
    hl_rows = hl_rows or {}
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            c = t.cell(i, j)
            c.text = str(val)
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
                elif zebra and i % 2 == 0:
                    c.fill.solid(); c.fill.fore_color.rgb = LGRAY
                else:
                    c.fill.solid(); c.fill.fore_color.rgb = WHITE
    return t


def figure(slide, name, x, y, max_w, max_h):
    path = os.path.join(FIGS, name)
    iw, ih = Image.open(path).size
    ar = iw / ih
    if ar > max_w / max_h:
        w, hh = max_w, max_w / ar
    else:
        hh, w = max_h, max_h * ar
    pic = slide.shapes.add_picture(path, Inches(x + (max_w - w) / 2),
                                   Inches(y + (max_h - hh) / 2),
                                   Inches(w), Inches(hh))
    pic.line.color.rgb = RGBColor(0xD5, 0xD8, 0xDE); pic.line.width = Pt(0.75)
    return pic


def caption(slide, s, x, y, w, size=9.5):
    text(slide, s, x, y, w, 0.32, size=size, color=GRAY, italic=True)


def notes(slide, s):
    slide.notes_slide.notes_text_frame.text = s


def footer(slide, n):
    text(slide, f"MORI on ThunderAgent  |  2026-07-30  |  강윤의", 0.45, 7.05,
         6.0, 0.3, size=9, color=GRAY)
    text(slide, str(n), 12.6, 7.05, 0.4, 0.3, size=9, color=GRAY,
         align=PP_ALIGN.RIGHT)


LEGEND = ("출처 표기:  [논문] MORI.pdf 원문 직접 대조 완료 (Fig./Table 번호 병기)   "
          "[§C-4] 계획서 goguma6판 해당 절의 실측표   "
          "[실측] 본 서버 실측   [계산] 실측 유도   [결정] 설계 결정   TBD(미측정)")


# ══════════════════════════════════════════════════════════════════════════
# S1 — 타이틀
# ══════════════════════════════════════════════════════════════════════════
s = blank()
band(s, 0, 0, 13.333, 2.05, INK)
text(s, "MORI on ThunderAgent", 0.75, 0.5, 11.5, 0.9, size=40, color=WHITE,
     bold=True)
text(s, "상대 idleness 기반 3-tier KV 오프로딩 — 개요 · 현황 · 실험 계획",
     0.78, 1.42, 11.5, 0.5, size=16, color=RGBColor(0xC5, 0xD2, 0xE8))

text(s, "강윤의   |   2026-07-30   |   브랜치 mori (off yunuikang/thunderagent)",
     0.78, 2.35, 11.5, 0.4, size=14, color=GRAY)

panel(s, 0.75, 3.0, 5.75, 2.5, PANEL)
text(s, "발표 구성", 1.0, 3.15, 5.2, 0.35, size=15, bold=True, color=BLUE)
bullets(s, [
    ("1부  문제 배경 · ThunderAgent · MORI 개념 (S2-S5)", 0, INK, False),
    ("2부  논문 재현 대상: 세팅 · trace · 결과 (S6-S8)", 0, INK, False),
    ("3부  내 환경 · 변경점 · 실험 계획 (S9-S13)", 0, INK, False),
    ("부록  개념 정리 · 출처와 한계 (S14-S15)", 0, GRAY, False),
], 0.95, 3.55, 5.4, 1.8, size=12.5)

panel(s, 6.85, 3.0, 5.75, 2.5, CREAM)
text(s, "이 발표의 수치 규칙", 7.1, 3.15, 5.2, 0.35, size=15, bold=True,
     color=AMBER)
bullets(s, [
    ("모든 수치에 출처를 괄호로 병기한다", 0, INK, True),
    ("논문 값은 MORI.pdf 원문과 전수 대조 [논문]", 0, INK, False),
    ("내 값은 계획서 해당 절 번호를 병기 [§C-4] 등", 0, INK, False),
    ("미측정은 TBD. 추정치를 사실처럼 쓰지 않는다", 0, INK, False),
], 7.05, 3.55, 5.4, 1.8, size=12.5)

text(s, LEGEND, 0.75, 5.75, 11.8, 0.6, size=10, color=GRAY)
text(s, "* 논문 원본(MORI.pdf, arXiv:2606.00866v1) 확보 완료 — Fig.3 / Fig.5 / Table 1 / Table 2 / 6.2절을 "
        "직접 대조해 이전 판의 미검증 29건을 전부 검증으로 승격했습니다.",
     0.75, 6.35, 11.8, 0.5, size=11, color=GREEN, bold=True)
footer(s, 1)
notes(s, """[발표 목적]
MORI 논문을 ThunderAgent 코드베이스 위에 구현·평가하는 프로젝트의 현재 상태를 공유하고,
실험 계획(특히 논문 대비 무엇을 왜 바꿨는지)에 대한 피드백을 받는 것이 목적입니다.

[아직 결과가 없다는 점을 먼저 밝힙니다]
오늘 보고드리는 것은 (1) 논문 이해, (2) 코드 매핑, (3) 환경 실측, (4) 데이터셋 특성 실측,
(5) 실험 설계입니다. 성능 결과는 M4(Phase 1 스윕) 이후에 나옵니다.
현재 완료된 마일스톤은 M0(브랜치 생성)뿐이고, GPU는 아직 한 번도 점유하지 않았습니다.

[이 판에서 달라진 것]
직전 판 대비 (1) 논문 PDF를 확보해 미검증 수치 29건을 전수 대조로 승격했고,
(2) SGLang sm_120 스모크가 통과했으며, (3) "데이터셋을 논문 특성에 맞게 어떻게 가공하나"
7장(S12~S18)이 새로 들어갔습니다. 발표의 무게중심이 이 데이터 섹션에 있습니다.

[수치 규칙을 앞에 두는 이유]
이 프로젝트는 "논문 재현"이 목적이라 논문 수치와 내 수치가 한 슬라이드에 섞여 나옵니다.
섞이면 나중에 "이거 우리가 잰 거였나 논문 거였나"가 반드시 헷갈립니다. 그래서 모든 셀에
출처 태그를 답니다.
논문 수치는 전부 MORI.pdf 원문과 직접 대조했습니다. Fig.3의 백분위 4개, Fig.5의
532 프로그램·3개 임계 median/p90, Table 1의 하드웨어 4행, Table 2의 오버헤드,
6.2절의 개선폭과 구체 수치(853/667, 213/124, 546/534, GPU util, churn)까지 전수 확인했고,
전부 일치했습니다.
내 수치는 계획서의 절 번호를 병기합니다 — 특히 데이터셋 섹션(S12~S18)은 §C-4가
근거이고, 서브에이전트·human-wait 조사는 §C-3, 한계는 §5-(12)/(13)입니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S2 — 문제 배경
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "문제 배경 — agentic 워크로드는 왜 다른가",
      "프로그램은 reasoning(GPU)과 acting(툴)을 번갈아 한다. 툴 시간이 자릿수로 흔들리면 GPU는 놀고 KV는 자리를 차지한다.")

bullets(s, [
    ("Agentic 워크로드 = 한 프로그램이 reasoning(GPU 점유) ↔ acting(툴 실행) 을 수십~수백 턴 반복", 0, INK, True),
    ("acting 동안 GPU는 이 프로그램에 대해 아무 일도 안 하지만, KV cache는 HBM을 계속 차지한다", 0, INK, False),
    ("프로그램들의 KV 합이 HBM 초과 → 버리거나(재계산) CPU DRAM으로 내리거나(재로드) 선택해야 함", 0, INK, False),
    ("툴콜 duration이 자릿수로 varying:  P50 1,096 ms → P99 19,980 ms  (논문 Fig.3, n=16,886) [논문]", 0, RED, True),
    ("→ 프로그램이 busy phase / idle phase 두 국면으로 갈린다. 2 s 임계에서 콜의 13%(long)가 tool-time의 58% 차지 [논문]", 0, INK, False),
], 0.5, 1.75, 12.4, 2.5, size=13.5)

panel(s, 0.5, 4.4, 6.05, 2.35, PANEL)
text(s, "idle phase를 만드는 3대 원인 (논문 3.3절)", 0.75, 4.55, 5.5, 0.32,
     size=13, bold=True, color=BLUE)
bullets(s, [
    ("긴 툴콜 (빌드/테스트/네트워크)", 0, INK, False),
    ("인간 상호작용 대기 (human-in-the-loop)", 0, INK, False),
    ("서브에이전트 실행 (부모 입장에선 하나의 긴 툴콜)", 0, INK, False),
], 0.72, 4.95, 5.6, 1.5, size=12.5)
text(s, "우리 trace는 이 중 2번이 전처리 단계에서 소실되어 있다 (S11 참조)",
     0.72, 6.28, 5.6, 0.35, size=11, color=RED, bold=True)

panel(s, 6.85, 4.4, 6.0, 2.35, CREAM)
text(s, "핵심 질문", 7.1, 4.55, 5.5, 0.32, size=13, bold=True, color=AMBER)
text(s, "지금 GPU에서 내려야 할 프로그램은 누구인가?\n\n"
        "ThunderAgent의 답 = 컨텍스트가 긴 놈\n"
        "MORI의 답 = 지금 가장 오래 안 돌아올 놈",
     7.1, 4.95, 5.5, 1.6, size=13.5, color=INK)
footer(s, 2)
notes(s, """[왜 request 단위가 아니라 program 단위인가 — 이 슬라이드의 진짜 요점]
일반 LLM 서빙 스케줄러는 "요청(request)" 단위로 생각합니다. 요청이 끝나면 그 요청의 KV는
용도가 끝났다고 보고 반납합니다. Agentic 워크로드에서는 이 가정이 깨집니다.

한 프로그램의 턴 N이 끝나면 KV를 반납해도 될 것 같지만, 턴 N+1이 몇 초~몇 분 뒤에
"턴 N까지의 전체 대화"를 프롬프트로 들고 다시 옵니다. 즉 같은 KV를 다시 씁니다.
따라서 턴 N 종료 시점에 KV를 버리면 턴 N+1에서 full prefill 재계산 비용을 물게 됩니다.
반대로 붙들고 있으면 툴이 도는 내내 HBM을 점유합니다.

이 트레이드오프는 "요청" 수준에서는 표현조차 되지 않습니다. 물어야 할 질문이
"이 프로그램은 얼마나 오래 안 돌아오는가"인데, 그건 요청이 아니라 프로그램의 속성이기
때문입니다. 그래서 ThunderAgent도 MORI도 스케줄링 단위를 program으로 올립니다.

[숫자의 의미]
P50 1.1초 / P99 20초는 178배 차이입니다. 이 분산이 핵심입니다. 만약 모든 툴콜이 1초씩
균일했다면 "잠깐 기다렸다 다시 쓴다"가 언제나 정답이고 스케줄러가 할 일이 없습니다.
13%의 긴 콜이 전체 tool-time의 58%를 먹는다는 것은, 소수의 프로그램이 대부분의 idle 시간을
만든다는 뜻이고, 그 소수를 정확히 골라내면 큰 이득이 있다는 뜻입니다. MORI의 존재 이유입니다.

[caveat]
우리 trace는 이 분포가 논문과 다릅니다(S11). 우리 쪽이 오히려 더 idle-heavy해서
MORI에 유리한 편향이 있습니다. 이건 한계로 명기해야 합니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S3 — ThunderAgent 베이스라인
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "베이스라인: ThunderAgent (TA)",
      "program-aware 2-tier 스케줄러. GPU와 Waiting 사이에 CPU 단이 통째로 없다 — MORI가 채우는 자리가 여기다.")

bullets(s, [
    ("program-aware 프록시 스케줄러: 요청을 중계하면서 프로그램별 상태(REASONING/ACTING)를 관리", 0, INK, False),
    ("2-tier 구조 — GPU tier = BackendState._programs  /  Waiting tier = global_waiting_queue", 0, INK, True),
    ("툴콜 갭 동안 프로그램을 GPU에 pin 해서 KV를 유지 (다음 턴의 재계산 회피)", 0, INK, False),
    ("용량 위반 시 demotion: ACTING 우선, 같은 status 안에서는 context-length(total_tokens) 작은 것부터", 0, INK, False),
    ("promotion: REASONING → NEW → ACTING 순, 각 그룹 토큰 오름차순 + BFD 배치.  scheduler tick 5 s", 0, INK, False),
], 0.5, 1.75, 12.4, 2.4, size=13.5)

table(s, [
    ["구성요소", "코드 위치 [실측: 소스 대조 완료]", "역할"],
    ["Waiting tier", "scheduler/router.py:93  global_waiting_queue", "pause된 프로그램 (KV 폐기됨)"],
    ["GPU tier", "backend/state.py:50  _programs", "현재 백엔드에 상주"],
    ["스케줄 루프", "router.py:759  _scheduled_check  (tick 5 s)", "주기적 용량 점검"],
    ["Demotion", "router.py:773  _pause_until_safe", "GPU → Waiting"],
    ["Promotion", "router.py:807  _greedy_resume", "Waiting → GPU"],
    ["상태 전이 훅", "router.py:371 / 460  update_program_before/after_request", "MORI 계측을 붙일 지점"],
], 0.5, 4.3, 12.4, 2.2, fs=10.5, hdr_fs=10.5,
    col_widths=[2.2, 5.9, 4.3])
caption(s, "tick 5 s = config.py scheduler_interval 기본값 5.0 [실측] · "
           "용량식은 BUFFER_PER_PROGRAM=100 (backend/state.py:23) [실측]",
        0.5, 6.6, 12.4)
footer(s, 3)
notes(s, """[현 코드 구조 요약 — 전부 이번에 소스로 직접 확인했습니다]
ThunderAgent는 vLLM/SGLang 앞단에 서는 프록시 겸 스케줄러입니다. 스케줄링 진입점 5개가
전부 MultiBackendRouter의 '메서드'라서, 서브클래스 오버라이드만으로 정책을 통째로 갈아끼울
수 있습니다. 이게 MORI 구현을 격리해서 넣을 수 있는 이유입니다:
  _scheduled_check(759) / _pause_until_safe(773) / _greedy_resume(807) /
  update_program_before_request(371) / update_program_after_request(460)

[가장 중요한 관찰: 빠진 층]
GPU tier와 Waiting tier 둘뿐입니다. Waiting으로 내려가면 KV는 그냥 사라지고, 돌아올 때
full prefill을 다시 냅니다. "GPU엔 없지만 KV는 살아있는" 중간 상태가 존재하지 않습니다.
MORI가 추가하는 CPU tier가 정확히 이 빈칸입니다.

[베이스라인 무수정 원칙]
TA/TA+O가 비교 기준이므로 router.py와 backend/state.py는 diff 0줄을 유지합니다.
매 커밋마다 git diff yunuikang/thunderagent..mori 로 기계적으로 검증합니다(게이트 G3).

[발표 중 나올 수 있는 질문 대비 — 알려진 결함 2개]
1) backend/state.py:129 update_shared_tokens()는 정의만 있고 호출자가 0입니다(grep 확인).
   즉 shared_tokens는 영구히 0이고, 용량 계산이 prefix 공유를 전혀 반영하지 않습니다.
   → 고치지 않습니다. 베이스라인의 실제 동작이고, MORI의 CPU tier 회계도 같은 규약을 써야
   TA+O와 공정 비교가 됩니다. 다만 4종 모두 절대 용량이 보수적으로 과대 계상됩니다.
2) _pause_until_safe는 pause_resume_lock 밖에서 돕니다. CPU tier가 추가되면 3자 간 이동이
   생기므로 lock 범위를 넓혀야 합니다(구현상 최대 리스크, S13에서 언급).""")


# ══════════════════════════════════════════════════════════════════════════
# S4 — MORI 개념
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "MORI가 다른 점 — 개념",
      "idleness를 켜짐/꺼짐이 아니라 연속적·상대적 스펙트럼으로 보고, 그 랭킹으로 3-tier를 운용한다.")

panel(s, 0.5, 1.75, 3.9, 2.1, BLUEBG)
text(s, "1. 상대 idleness  ι", 0.72, 1.9, 3.5, 0.32, size=14, bold=True,
     color=BLUE)
text(s, "ι = T_acting / (T_reasoning + T_acting)\n\n"
        "최근 k=5 스텝 윈도우\n스케줄러 pause 시간은 제외",
     0.72, 2.3, 3.5, 1.4, size=12.5)

panel(s, 4.62, 1.75, 3.9, 2.1, GREENBG)
text(s, "2. 3-tier 큐", 4.84, 1.9, 3.5, 0.32, size=14, bold=True, color=GREEN)
text(s, "GPU  /  CPU DRAM  /  Waiting\n\n"
        "TA의 2-tier 사이에 CPU가 들어감\n"
        "Waiting = KV 폐기, CPU = KV 보존",
     4.84, 2.3, 3.5, 1.4, size=12.5)

panel(s, 8.74, 1.75, 4.1, 2.1, CREAM)
text(s, "3. sticky + typed eviction", 8.96, 1.9, 3.7, 0.32, size=14,
     bold=True, color=AMBER)
text(s, "sticky: 매 tick 재배치 금지,\nmismatch일 때만 이동\n\n"
        "typed eviction: type이 상위 정렬키,\nLRU는 tie-break",
     8.96, 2.3, 3.7, 1.4, size=12.5)

bullets(s, [
    ("스케줄링 신호가 '컨텍스트가 긴가'에서 '지금 얼마나 오래 안 돌아오는가'로 바뀐다", 0, INK, True),
    ("진행 중인 툴콜을 ι에 반영해야 한다 — ι(now) 계산 시 (now - acting_since)를 acting 항에 더함", 0, RED, True),
    ("    이게 빠지면 '긴 툴콜에 들어간 프로그램을 내린다'는 동작 자체가 생기지 않는다 (재현 핵심)", 1, RED, False),
    ("typed eviction 방향: GPU tier는 inactive → idle → busy 순으로 버리고, CPU tier는 반대로 busy부터 버린다", 0, INK, False),
], 0.5, 4.1, 12.4, 1.9, size=13)

panel(s, 0.5, 6.05, 12.35, 0.75, PANEL)
text(s, "ι 는 내가 기존 트랙에서 쓰던 duty d 의 여집합:  ι = 1 - d.  "
        "d는 'GPU를 쓰는 시간 비중', ι는 '툴이 도는 시간 비중'.  "
        "k=5, tick 5 s 는 논문 전 실험 고정값 [논문] — 우리 scheduler_interval 기본값 5.0과 우연히 일치 [실측]",
     0.72, 6.2, 11.9, 0.5, size=11.5, color=INK)
footer(s, 4)
notes(s, """[ι 정의를 천천히]
ι = T_acting / (T_reasoning + T_acting). 최근 k=5 스텝의 윈도우로 계산합니다.
ι가 1에 가까우면 "이 프로그램은 대부분 툴을 돌리고 있다 = GPU에 있어봐야 놀린다".
ι가 0에 가까우면 "쉴 새 없이 추론을 요청한다 = GPU에 붙들어야 한다".

여기서 '상대'가 중요합니다. 절대 임계값(예: 툴이 2초 넘으면 idle)이 아니라, 지금 동시에
도는 프로그램들 사이의 ι 랭킹으로 누구를 내릴지 정합니다. 그래서 워크로드 전체가 느려지거나
빨라져도 임계값을 다시 안 잡아도 됩니다.

[pause 시간을 빼는 이유]
스케줄러가 강제로 세워둔 시간을 acting으로 세면, 한 번 내려간 프로그램의 ι가 올라가서
계속 내려가는 자기강화 루프가 생깁니다. 논문도 "waiting time is excluded from both"라고
명시합니다. 우리 코드에선 profile/state.py의 계측점 구분(tool_call_time은 pause 이전,
pause_time은 pause 이후)이 이 요건과 정확히 일치합니다 — 그대로 재사용할 수 있습니다.

[진행 중 툴콜 반영 = 구현의 핵심 디테일]
ι를 push 시점(툴콜이 끝난 뒤)에만 갱신하면, 지금 막 40분짜리 빌드에 들어간 프로그램의 ι는
직전 5턴 기준의 낮은 값 그대로입니다. 그러면 그 프로그램을 내려야 한다는 신호가 안 옵니다.
그래서 value(now)를 호출할 때 현재 ACTING 중이면 (now - acting_since)를 진행 중 항으로
더해서, 시간이 갈수록 ι가 단조 증가하게 만들어야 합니다. 논문 4.2절의 "responsive" 성질입니다.
단위 테스트로 (a) 짧은 툴만 → ι→0, (b) 긴 툴 진행 중 → ι 단조증가, (c) 긴 툴 1회가 짧은 툴
5회에 희석되는지를 고정할 계획입니다.

[typed eviction 방향이 tier마다 반대인 이유]
GPU에는 곧 추론할 놈(busy)을 남겨야 하니 inactive→idle→busy 순으로 버립니다.
CPU에는 곧 GPU로 올라올 놈(idle/inactive)을 남겨야 하니 반대로 busy부터 버립니다.
busy 프로그램의 KV는 어차피 GPU에 있을 테니 CPU 사본은 덜 중요하다는 논리입니다.

[구현량 비교]
논문은 ThunderAgent에 약 3,300줄, SGLang에 약 500줄을 더했다고 밝힙니다 [논문].
우리 추정은 신규 약 760줄 + 엔진 패치 약 500줄입니다. 차이가 큰데, 논문이 multi-replica와
운영 코드를 포함하기 때문으로 보이지만 우리가 뭘 빠뜨렸을 가능성도 있어 Phase 1 완료 후
재점검 항목으로 남겨뒀습니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S5 — MORI vs ThunderAgent 비교표
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "MORI vs ThunderAgent — 축별 대조",
      "바뀌는 것은 다섯 축. 그중 성능을 가르는 것은 스케줄링 신호와 demotion 목적지다.")

table(s, [
    ["축", "ThunderAgent (TA)", "MORI", "성능 함의"],
    ["스케줄링 신호",
     "context-length (total_tokens) 오름차순\n엔진 캐시는 LRU",
     "상대 idleness ι (k=5 윈도우)\n진행 중 툴콜까지 반영",
     "긴 컨텍스트가 아니라\n오래 안 올 놈을 내림"],
    ["메모리 tier",
     "2-tier: GPU ↔ Waiting\n(그 사이가 비어 있음)",
     "3-tier: GPU / CPU DRAM / Waiting",
     "KV 폐기 대신 보존\n재계산 → 재로드"],
    ["demotion 목적지",
     "Waiting (KV 폐기 → 복귀 시 full prefill)",
     "CPU tier 우선, 용량 부족 시 Waiting",
     "복귀 비용 대폭 감소"],
    ["배치 정책",
     "용량 위반 시 반응적 이동",
     "sticky — mismatch일 때만,\ntick 내 demote+promote 금지",
     "진동(thrashing) 억제"],
    ["엔진 eviction",
     "LRU (SGLang HiCache 기본)",
     "typed: GPU는 inactive→idle→busy,\nCPU는 반전. 동타입 LRU",
     "곧 쓸 KV를 안 버림"],
    ["코드 변경 규모",
     "— (기준)",
     "논문: TA +약 3,300줄 / SGLang +약 500줄 [논문]\n내 계획: 신규 약 760줄 + 엔진 약 500줄 [결정]",
     "차이는 multi-replica·\n운영코드로 추정"],
], 0.5, 1.8, 12.4, 4.7, fs=10.5, hdr_fs=11,
    col_widths=[1.7, 3.85, 4.5, 2.35],
    hl_rows={1: CREAM, 3: CREAM})

caption(s, "노란 행 = 논문이 주장하는 이득의 대부분이 나오는 두 축. "
           "나머지 세 축은 그 이득을 실제로 유지시키는 보조 장치.",
        0.5, 6.6, 12.4)
footer(s, 5)
notes(s, """[이 표를 한 줄로 요약하면]
TA는 "누가 메모리를 많이 먹나"로 정렬하고, MORI는 "누가 오래 자리를 비우나"로 정렬합니다.
그리고 TA는 내리면 KV를 버리지만, MORI는 CPU에 보관합니다.

[왜 두 축(신호·목적지)이 핵심인가]
나머지 세 축(sticky, typed eviction, 코드 규모)은 단독으로는 이득을 못 만듭니다.
- sticky가 없으면 매 tick마다 랭킹이 흔들려 프로그램이 tier 사이를 왕복하고, 이동 비용이
  이득을 다 까먹습니다. 즉 sticky는 이득의 '보존' 장치입니다.
- typed eviction이 없으면 스케줄러가 "이건 CPU에 둬라"고 결정해도 엔진의 LRU가 그걸 무시하고
  버릴 수 있습니다. 즉 스케줄러 결정이 엔진까지 관철되게 하는 장치입니다.
그래서 Phase 1(스케줄러만)에서도 핵심 주장은 검증 가능하고, Phase 2(엔진 연동)가 그걸
실물로 확정하는 구조입니다.

[비교 실험이 4종인 이유 — 이 표에서 바로 나옵니다]
  SMG   = 스케줄러 없음, 오프로딩 없음        (바닥)
  TA    = 스케줄러 있음, 오프로딩 없음        (신호만 있는 경우)
  TA+O  = TA 스케줄러 + 엔진 오프로딩 (엔진 LRU가 CPU tier를 독립 관리)
  MORI  = ι 신호 + 조율된 3-tier + typed eviction
TA+O와 MORI의 차이가 곧 "CPU tier를 스케줄러가 조율하느냐"의 순수 효과입니다.
이게 우리 실험의 주 비교쌍입니다.

[코드 규모 행의 정직한 읽기]
논문 3,300줄 대 우리 760줄은 우리가 뭔가를 안 하고 있다는 신호일 수 있습니다.
현재 파악으론 multi-replica affinity LB(DP=1이라 제외)와 운영 코드 차이지만,
Phase 1 완료 후 다시 점검하기로 열어뒀습니다. 이 숫자는 지금 [논문] 태그입니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S6 — 논문 실험 세팅
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "논문 실험 세팅 (Table 1)",
      "H200/B200 4구성 × baseline 4종 × 지표 3종 × 동시성 3단 × CPU:GPU 2단, 고정 1시간 런.")

table(s, [
    ["구성", "GPU", "모델", "병렬"],
    ["1", "H200 (80 GB로 capping)", "Qwen2.5-7B", "-"],
    ["2", "H200", "Qwen3-30B-A3B (MoE)", "-"],
    ["3", "H200", "Qwen3-30B-A3B", "DP3 (멀티레플리카)"],
    ["4", "B200", "Llama-3.1-70B", "TP2"],
], 0.5, 1.8, 6.1, 1.9, fs=11, hdr_fs=11, col_widths=[0.75, 2.35, 2.1, 0.9])
caption(s, "Table 1 (MORI.pdf p.9) — 4행 전부 원문 직접 대조 완료", 0.5, 3.75, 6.1)

table(s, [
    ["축", "값", "출처"],
    ["엔진", "SGLang v0.5.10 + HiCache", "[논문]"],
    ["baseline", "SMG / TA / TA+O / MORI", "[논문]"],
    ["지표", "output throughput (tok/s)\nstep throughput (req/s), TTFT (s)", "[논문]"],
    ["동시성 C", "20 / 50 / 80", "[논문]"],
    ["CPU:GPU 비", "1x / 2x", "[논문]"],
    ["런 프로토콜", "고정 1시간, closed-loop 슬롯\n완주 시 코퍼스에서 즉시 다음 세션", "[논문]"],
    ["하이퍼파라미터", "k=5 윈도우, tick 5 s", "[논문]"],
    ["구현량", "ThunderAgent +약 3,300줄 / SGLang +약 500줄", "[논문]"],
], 6.85, 1.8, 6.0, 3.5, fs=10.5, hdr_fs=10.5, col_widths=[1.5, 3.55, 0.95])

panel(s, 0.5, 4.3, 6.1, 2.2, CREAM)
text(s, "방법론적으로 우리에게 중요한 한 줄", 0.72, 4.45, 5.6, 0.32,
     size=13, bold=True, color=AMBER)
text(s, "논문도 H200의 가용 HBM을 capping 해서\n"
        "H100급 메모리 용량을 에뮬레이션한다 (6.1절) [논문]\n\n"
        "→ 메모리 압박 레짐을 인위적으로 만드는 것이\n"
        "   논문 자신의 방법론이므로, 우리가 L을 줄이는 것도\n"
        "   같은 근거로 정당화된다 (S10)",
     0.72, 4.85, 5.6, 1.5, size=12.5)

text(s, "SMG는 DP=1에서 '엔진으로 직접 포워딩'으로 환원된다 (6.1절) [논문] "
        "→ 우리 --router default 모드와 정확히 일치. 4종 중 3종이 플래그 조합만으로 재현됨.",
     6.85, 5.45, 6.0, 0.9, size=11.5, color=BLUE, bold=True)
footer(s, 6)
notes(s, """[논문 세팅에서 우리가 그대로 가져가는 것]
baseline 4종, 지표 3종, 동시성 20/50/80, CPU:GPU 1x/2x, k=5, tick 5s — 전부 동일하게 갑니다.
특히 tick 5s는 우리 config.py의 scheduler_interval 기본값 5.0과 이미 같습니다(우연).

[SMG 항목이 왜 반가운가]
논문의 SMG(SGLang model gateway)는 DP=1 구성에서는 그냥 엔진으로 직접 포워딩하는 것과
같아진다고 논문이 명시합니다. 우리 하네스의 --router default가 바로 순수 프록시입니다.
즉 우리는 DP=1이지만 SMG 베이스라인을 '정확히' 재현합니다 — 근사가 아닙니다.

[반대로 못 가져가는 것]
- 하드웨어(H200/B200)와 모델 크기(7B/30B/70B): 우리는 5090 x2에 8B (S9, S10)
- DP3 멀티레플리카: 우리는 백엔드 1개(DP=1)라 affinity-aware LB와 churn은 재현 범위 밖
- 고정 1시간: 우리는 고정 20분창 x 3 repeat (GPU 1노드 직렬, 예산 문제)

[capping 관련해서 지도교수 질문이 예상되는 지점]
"메모리를 인위로 줄여서 유리하게 만든 것 아니냐"는 질문이 나올 수 있습니다. 답은 두 갈래입니다.
1) 논문 자신이 H200을 80GB로 capping해서 H100급을 흉내냅니다. 압박 레짐을 만드는 것은
   이 분야의 표준 방법론입니다.
2) 더 중요한 건, 우리는 GPU가 작아서 capping이 아예 필요 없다는 점입니다(S9).
   native 상태로 이미 fit≈4.2라 논문의 압박 레짐에 들어가 있습니다. 우리가 조정하는 건
   HBM이 아니라 컨텍스트 예산 L입니다. 방법론적으로는 오히려 더 정직한 위치입니다.

[정직 고지]
Table 1의 하드웨어/모델 조합 4행은 오늘 구두로 받은 값이고 계획서에 인용 기록이 없어
[논문]입니다. 발표 전 PDF로 확인해야 합니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S7 — 논문 trace 분포
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "논문 trace 분포 (Fig.3 / Fig.5)",
      "툴콜은 자릿수로 흩어지고, busy phase 길이는 어떤 임계를 쓰냐에 따라 4 s에서 41 s까지 움직인다.")

text(s, "Fig.3 — 툴콜 duration CDF (n = 16,886)", 0.5, 1.75, 6.0, 0.35,
     size=14, bold=True, color=BLUE)
table(s, [
    ["백분위", "값", "출처"],
    ["P50", "1,096 ms", "[논문]"],
    ["P90", "2,034 ms", "[논문]"],
    ["P99", "19,980 ms", "[논문]"],
    ["P99.95", "83,626 ms", "[논문 Fig.3]"],
], 0.5, 2.2, 6.0, 1.65, fs=12, hdr_fs=11, col_widths=[1.7, 2.6, 1.7])
text(s, "P50 → P99 가 18배. 이 분산이 MORI의 전제.", 0.5, 3.95, 6.0, 0.35,
     size=12, color=RED, bold=True)

text(s, "Fig.5 — busy phase 길이 (532 프로그램) [논문]", 6.85, 1.75, 6.0,
     0.35, size=14, bold=True, color=BLUE)
table(s, [
    ["임계", "median", "p90", "출처"],
    ["1 s", "4 s", "15 s", "[논문]"],
    ["2 s", "20 s", "81 s", "[논문]"],
    ["5 s", "41 s", "185 s", "[논문]"],
], 6.85, 2.2, 6.0, 1.4, fs=12, hdr_fs=11, col_widths=[1.4, 1.6, 1.6, 1.4])
text(s, "임계를 뭘로 잡느냐에 따라 phase 길이가 10배 움직인다\n"
        "→ 절대 임계 대신 상대 랭킹(ι)을 쓰는 근거",
     6.85, 3.7, 6.0, 0.7, size=12, color=RED, bold=True)

panel(s, 0.5, 4.55, 12.35, 1.35, CREAM)
text(s, "2 s 임계 기준 분해 [논문]", 0.75, 4.68, 5.5, 0.3, size=13,
     bold=True, color=AMBER)
text(s, "콜의 87% = short (tool-time의 42%)          "
        "콜의 13% = long (tool-time의 58%)\n"
        "→ 소수의 긴 콜이 idle 시간의 과반을 만든다. 그 소수만 정확히 골라내면 이득이 크다는 것이 MORI의 논거.",
     0.75, 5.02, 11.8, 0.8, size=12.5)

caption(s, "값은 MORI.pdf Fig.3 / Fig.5 / 3.3절 본문에서 직접 옮김 (원본 그림 이미지 대신 표로 재작성 — 서버에 pdfimages 미설치). "
           "Fig.5의 532 프로그램·3개 임계 전부 원문 대조 완료.",
        0.5, 6.05, 12.4)
footer(s, 7)
notes(s, """[Fig.3을 읽는 법]
툴콜 duration의 CDF입니다. 절반은 1초 안에 끝나는데, 상위 1%는 20초, 상위 0.05%는 83초입니다
(83.6초). 이게 "orders-of-magnitude varying"의 실체입니다.

이 분산이 왜 스케줄러 문제인가: 모든 툴콜이 1초 균일하면 "잠깐 기다렸다 쓴다"가 항상 정답이라
스케줄러가 필요 없습니다. 20초, 80초짜리가 섞여 있으니 "이번엔 기다릴까 내릴까"를 매번
판단해야 하고, 판단 근거가 필요합니다.

[Fig.5를 읽는 법 — 이게 더 중요합니다]
busy phase = "짧은 툴콜들이 연달아 오는 구간". 문제는 '짧다'의 기준을 몇 초로 잡느냐입니다.
1초로 잡으면 busy phase median 4초, 2초로 잡으면 20초, 5초로 잡으면 41초.
같은 데이터인데 임계값 하나로 결과가 10배 달라집니다.

여기서 MORI의 설계 결정이 나옵니다: 절대 임계값을 잡는 순간 그 값이 워크로드마다,
하드웨어 속도마다 다시 튜닝해야 하는 하이퍼파라미터가 됩니다. 대신 "지금 도는 프로그램들
중에서 상대적으로 누가 더 idle한가"를 쓰면 임계값 자체가 사라집니다.
이 슬라이드는 "왜 상대적(relative) idleness인가"에 대한 논문의 경험적 근거입니다.

[87% / 13% 분해]
2초 임계에서 콜 개수의 13%가 tool-time의 58%를 차지합니다. 롱테일이 시간을 지배한다는
전형적 패턴입니다. 스케줄러 입장에선 반가운 소식인데, 소수의 프로그램만 정확히 식별해
내리면 대부분의 idle GPU 시간을 회수할 수 있다는 뜻이기 때문입니다.

[왜 그림을 안 붙였나 — 질문 나오면]
원래 pdfimages로 논문 Fig.3/Fig.5를 추출해 붙이려 했으나, MORI.pdf가 현재 서버에
없습니다(계획서가 가리키는 경로 부재). 없는 그림을 그럴듯하게 다시 그리면 조작이므로,
검증 가능한 수치만 표로 옮기고 출처 태그를 달았습니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S8 — 논문 결과 경향
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "논문 결과 경향",
      "동시성이 높고 메모리가 타이트할수록 격차가 벌어진다. C=20에서는 거의 동률 — 이게 위생 대조군이 된다.")

table(s, [
    ["조건 / 지표", "TA+O", "MORI", "차이", "출처"],
    ["C=80  output throughput (전 구성)", "-", "-", "+20 ~ 71%", "[논문]"],
    ["C=80  TTFT (전 구성)", "-", "-", "-18 ~ 43%", "[논문]"],
    ["C=80  vs SMG / TA (throughput)", "-", "-", "1.6 ~ 2.1x", "[논문]"],
    ["C=80  vs SMG (TTFT)", "-", "-", "-33 ~ 66%", "[논문]"],
    ["H200(80GB), 80 프로그램  tok/s", "667", "853", "+28%", "[논문]"],
    ["B200 2x CPU, 80 프로그램  tok/s", "124", "213", "+71%", "[논문]"],
    ["C=20  tok/s  (위생 대조)", "534", "546", "+2%", "[논문]"],
    ["B200 1x  C 스케일링 20→50→80  tok/s", "147→181→146\n(비단조)", "136→191→189\n(단조 비감소)", "-", "[논문]"],
    ["B200 80프로그램  1x→2x  TTFT", "56 → 58 s\n(개선 없음)", "38 → 33 s", "-", "[논문]"],
    ["DP3 멀티레플리카  throughput", "-", "-", "+54 ~ 79%", "[논문]"],
    ["DP3  GPU util", "59 ~ 76%", "99%+", "-", "[논문]"],
    ["DP3  프로그램 churn", "5.5%", "0.3 ~ 2.9%", "-", "[논문]"],
], 0.5, 1.75, 8.5, 4.35, fs=10, hdr_fs=10,
    col_widths=[3.35, 1.55, 1.55, 1.2, 0.85],
    hl_rows={7: GREENBG, 8: CREAM, 9: CREAM})

panel(s, 9.25, 1.75, 3.6, 2.1, PANEL)
text(s, "오버헤드 (Table 2) [논문]", 9.45, 1.88, 3.2, 0.3, size=12.5,
     bold=True, color=BLUE)
text(s, "CPU 스케줄링 시간\n  MORI 23.8 ms\n  TA+O  21.5 ms\n\n"
        "GPU 스텝 약 32 ms 안에\n완전히 오버랩됨\n→ 순 오버헤드 사실상 0",
     9.45, 2.25, 3.2, 1.5, size=12)

panel(s, 9.25, 4.0, 3.6, 2.1, CREAM)
text(s, "읽어야 할 두 가지", 9.45, 4.13, 3.2, 0.3, size=12.5, bold=True,
     color=AMBER)
text(s, "1. TA+O는 C를 올려도 비단조.\n   eviction thrashing 때문.\n\n"
        "2. TA+O는 CPU를 2배 줘도\n   TTFT가 그대로다. 조율하지\n   않으면 용량을 못 쓴다.",
     9.45, 4.5, 3.2, 1.5, size=11.5)

caption(s, "노란 행 = MORI의 이득이 '더 많은 메모리'가 아니라 '조율'에서 온다는 증거. "
           "초록 행 = C=20 동률, 우리 실험의 위생 대조군(P3) 근거.",
        0.5, 6.2, 12.4)
footer(s, 8)
notes(s, """[결과를 한 문장으로]
"메모리 압박이 크고 동시성이 높을수록 MORI가 이긴다. 여유가 있으면 아무 차이 없다."

[C=20 행(초록)이 중요한 이유 — 여기를 강조하세요]
C=20에서 MORI 546, TA+O 534로 2% 차이입니다. 사실상 동률입니다.
이건 논문의 약점이 아니라 오히려 신뢰성의 근거입니다. 메모리에 여유가 있으면 스케줄링이
할 일이 없는 게 당연하고, 그런데도 이득이 나온다면 측정 버그를 의심해야 합니다.
우리 실험에서도 이걸 그대로 위생 검사(P3: C=20에서 ±5% 이내)로 씁니다. 여기서 큰 차이가
나면 우리 구현에 버그가 있다는 신호로 삼습니다.

[노란 행 두 개가 MORI의 핵심 메커니즘 증거]
1) C 스케일링 비단조: TA+O는 147→181→146으로 C=80에서 오히려 떨어집니다. eviction
   thrashing입니다 — 엔진 LRU가 곧 쓸 KV를 버리고, 버린 걸 다시 올리는 왕복이 생깁니다.
   MORI는 136→191→189로 단조 비감소입니다. sticky + typed eviction의 효과입니다.
2) CPU를 2배로 줘도 TA+O TTFT는 56→58초로 그대로인데 MORI는 38→33초로 개선됩니다.
   이게 가장 강한 논거입니다: 이득이 '메모리를 더 줘서'가 아니라 '스케줄러가 그 메모리를
   조율해서' 나온다는 뜻이니까요. 메모리만 늘리면 TA+O도 좋아져야 하는데 안 좋아집니다.

[오버헤드 표]
MORI의 CPU 스케줄링 시간 23.8ms는 TA+O의 21.5ms보다 2.3ms 깁니다. 그런데 GPU 스텝이
약 32ms라 그 안에 완전히 숨습니다. "ι 계산이 비싸지 않냐"는 질문에 대한 답입니다.
다만 이 표 값들은 [논문] — 아직 원문 대조를 못 했습니다.

[출처 상태: 이 표는 전 행이 원문 대조 완료입니다]
853/667(§6.2), 213/124(§6.2), 546/534(§6.2), C 스케일링, TTFT 1x→2x, DP3 54~79%,
GPU util 99%+ vs 59~76%, churn 2.0% vs 5.5%, Table 2 오버헤드까지 MORI.pdf에서
직접 확인했고 전부 일치했습니다.
덧붙일 만한 원문 수치: 같은 H200(80GB) 80프로그램에서 SMG는 447 tok/s, TA는 557 tok/s로
정체하는 반면 MORI는 853 tok/s입니다. B200 70B에서는 SMG 96 tok/s vs MORI 189 tok/s로
정확히 두 배 차이입니다. 비오프로딩 baseline이 왜 안 되는지 보여주는 대목이라
질문이 나오면 인용할 만합니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S9 — 내 실험 환경 (goguma6)
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "내 실험 환경 — goguma6 (실측)",
      "HBM이 작아서 오히려 좋다: capping 없이 native 상태로 논문의 압박 레짐(fit≈4)에 들어가 있다.")

table(s, [
    ["항목", "값", "근거"],
    ["GPU", "RTX 5090 32,607 MiB x 2 (GPU0,1 모두 유휴)", "nvidia-smi [실측]"],
    ["TP2 합산 HBM", "63.68 GiB", "[계산]"],
    ["상호연결", "SYS, NVLink 없음. GPU0=NUMA0 / GPU1=NUMA1 (cross-NUMA)", "topo -m [실측]"],
    ["CPU DRAM", "188 GiB total / 185 GiB avail, 32코어 2 NUMA", "free, nproc [실측]"],
    ["드라이버 / CUDA / arch", "580.82.07 / 13.0 / sm_120 Blackwell", "nvidia-smi [실측]"],
    ["모델", "Qwen3-8B.  B_tok = 2x36x8x128x2 = 144 KiB/tok", "[계산]"],
    ["native KV 풀", "약 38 GiB = 약 277k tok (범위 270-310k) — STEP1에서 확정", "[계산: 추정, 미확정]"],
    ["native fit", "약 4.2  (= 277k / ec128k median peak 65,678)", "[계산]"],
    ["C_gpu 핀", "262,144 tok = 36 GiB (재현성용, 압박 생성 목적 아님)", "[결정]"],
    ["CPU tier", "1x = 36 GiB / 2x = 72 GiB  (둘 다 185 GiB 안에 여유)", "[결정]"],
    ["엔진", "SGLang 0.5.10 + HiCache, 별도 venv 설치 완료 (기존 vLLM .venv 무손상)", "[실측 §A-2b]"],
], 0.5, 1.75, 12.4, 3.75, fs=10.5, hdr_fs=10.5,
    col_widths=[2.35, 7.55, 2.5], hl_rows={8: GREENBG})

panel(s, 0.5, 5.7, 6.05, 1.15, GREENBG)
text(s, "좋은 소식", 0.72, 5.8, 5.5, 0.3, size=12.5, bold=True, color=GREEN)
text(s, "HBM capping이 불필요하다. native fit≈4.2로 이미 논문의 압박 레짐. "
        "레짐 조정 레버는 HBM이 아니라 컨텍스트 예산 L로 이동한다.",
     0.72, 6.12, 5.6, 0.6, size=11.5)

panel(s, 6.85, 5.7, 6.0, 1.15, GREENBG)
text(s, "최우선 롱폴 해소 — M-SGL 스모크 PASS [§A-2b]", 7.07, 5.8, 5.5, 0.3,
     size=12.5, bold=True, color=GREEN)
text(s, "sm_120 비호환이 아니라 JIT 툴체인 문제였음 (CUDA_HOME·gcc-11 env로 해소). "
        "TP2 기동 READY 126 s, HiCache host 9.66 GB 할당 확인.",
     7.07, 6.12, 5.6, 0.6, size=11.5)
footer(s, 9)
notes(s, """[nutella → goguma6 재실측 경위 — 질문이 나올 대목이라 정확히 말씀드립니다]
처음 이 프로젝트를 정리할 때 저는 실험 서버가 "RTX 5090 32GB x2"라고 알고 있었습니다.
그런데 base 계획서를 쓰던 시점의 서버는 nutella였고, 거기서 nvidia-smi를 실제로 돌려보니
GPU0 = RTX PRO 5000 48GB(타 사용자 사용 중), GPU1/2 = RTX PRO 6000 96GB x2 였습니다.
즉 TP2 합산 191 GiB. 제 기억이 틀렸던 겁니다.

그 다음, 실제 실험 서버가 goguma6로 확정되면서 다시 실측했더니 이번엔 진짜로
RTX 5090 32GB x2 = 63.68 GiB였습니다. nutella의 0.33배입니다. 그래서 계획서를 goguma6판으로
재계산했습니다. 지금 이 슬라이드 값은 전부 goguma6에서 오늘 직접 확인한 값입니다.

[HBM이 3배 작아진 결과 — 두 가지가 바뀝니다]
1) capping이 불필요해졌습니다. nutella(191 GiB)에서는 KV 풀이 158 GiB, fit이 17을 넘어서
   메모리 압박이 아예 없었고, 논문 레짐을 만들려면 --kv-cache-memory-bytes로 60 GiB까지
   인위 축소해야 했습니다. goguma6에서는 native KV 풀이 약 38 GiB, fit≈4.2로 이미
   논문의 압박 구간에 있습니다. 인위 조작이 줄어드니 방법론적으로 더 정직합니다.
2) 레짐 미세조정 레버가 이동했습니다. GPU가 작아서 C_gpu를 올려 맞출 수가 없으므로,
   대신 컨텍스트 예산 L을 128k에서 64k로 줄여 조정합니다(S10, S11).

[fit 4.2를 어떻게 얻었나]
TP2 usable 63.68 x 0.92 ≈ 58.6 GiB에서 8B bf16 가중치 약 15.3 GiB와 오버헤드 약 5 GiB를
빼면 약 38 GiB. 토큰당 144 KiB로 나누면 약 277k 토큰. 이걸 ec128k trace의 median peak
컨텍스트 65,678 토큰으로 나누면 4.2입니다.
주의: 38 GiB는 아직 추정이고, STEP1에서 SGLang 기동 로그의 max_total_num_tokens로
확정해야 합니다. 그래서 [계산: 추정, 미확정] 태그입니다.

[36 GiB 핀의 목적을 오해하지 마세요]
--max-total-tokens 262144(36 GiB)로 고정하는 것은 압박을 '만들기' 위해서가 아닙니다.
native가 이미 압박이라 필요 없습니다. 재현성(매 런 같은 용량)과 불변식 I6 검증(스케줄러
장부 용량 == 엔진 실제 용량) 때문에 라운드 값으로 핀만 박는 것입니다.

[엔진 결정과 롱폴 해소 — 업데이트]
논문과 스택을 맞추려고 SGLang + HiCache로 통일했습니다(vLLM 0.24가 이미 설치돼 있고
네이티브 오프로딩도 있지만 쓰지 않습니다). 최대 리스크는 5090이 sm_120이라 SGLang이
빌드·구동될지 미확인이라는 점이었는데, M-SGL 스모크에서 해소됐습니다(§A-2b).
별도 venv(.venv-sglang)에 sglang 0.5.10 / torch 2.9.1+cu130 / sgl_kernel 0.4.1 /
flashinfer 0.6.7 설치. 기존 vLLM .venv는 건드리지 않았습니다.
초기 실패는 sm_120 비호환이 아니라 JIT nvcc 툴체인 문제였습니다 — 커널은
compute_120a/sm_120a를 정상 타겟팅하고 있었고, 원인은 (1) CUDA_HOME 미설정,
(2) 기본 gcc-13이 nvcc 허용 상한(11)을 넘긴 것 두 가지였습니다. 환경변수만으로 해결됐고,
serve 스크립트에 반드시 박아야 합니다(CUDA_HOME=/usr/local/cuda-13.0, gcc-11,
NVCC_PREPEND_FLAGS).
또 하나 확정된 것: GPU0↔GPU1이 SYS라 P2P peer access가 안 돼
--disable-custom-all-reduce가 필수입니다. NCCL fallback이라 절대 throughput은
내려가지만, 4종 시스템 모두 같은 인터커넥트를 쓰므로 상대 비교는 보존됩니다(§5-(14)).
남은 Phase 2 전제는 typed eviction 소스 통합(OQ-E2/F)뿐입니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S10 — 논문 대비 변경점
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "논문 대비 내가 바꾼 것 — 그리고 왜",
      "여덟 축을 바꿨다. 대부분 자원 제약이지만, 두 개(압박 emulation·전처리)는 방법론적 개선이다.")

table(s, [
    ["축", "논문", "내 실험", "왜 바꿨나"],
    ["모델", "Qwen2.5-7B / Qwen3-30B-A3B / Llama-3.1-70B",
     "Qwen3-8B 고정",
     "기존 트랙 실측자산 재사용. 32B는 2x CPU tier가 DRAM 한계에 걸림"],
    ["하드웨어", "H200(80GB) / B200", "RTX 5090 32G x2, TP2 (63.7 GiB)",
     "가용 서버가 goguma6뿐"],
    ["압박 emulation", "HBM capping (H200 → H100급)",
     "capping 없음 + L capping (128k → 64k)",
     "native fit≈4.2로 이미 압박. GPU가 작아 C_gpu를 올릴 수 없어 레버가 L로 이동"],
    ["엔진", "SGLang v0.5.10 + HiCache", "동일 (신규 설치 예정)",
     "재현 정합성 우선. 단 sm_120 구동은 미검증"],
    ["데이터셋", "Claude Code + SWE-bench Pro 자체 수집",
     "TraceLab / SyFI 재가공",
     "자체 수집 불가. 분포 차이는 한계로 명기 (S11)"],
    ["런 프로토콜", "고정 1시간", "고정 20분창 x 3 repeat",
     "GPU 1노드 직렬, 예산 약 38 GPU-node-h. run-to-completion은 drain-bias 때문에 폐기"],
    ["병렬성", "DP3 포함", "DP=1 (백엔드 1개)",
     "affinity-aware LB와 churn은 재현 범위 밖으로 명시"],
    ["전처리", "-", "prefix truncation 금지, turn-window slicing",
     "prefix truncation이 busy/idle 전이를 17.6 → 1.3으로 붕괴시킴 (S11)"],
], 0.5, 1.75, 12.4, 4.6, fs=9.5, hdr_fs=10.5,
    col_widths=[1.4, 2.9, 2.9, 5.2],
    hl_rows={3: GREENBG, 8: GREENBG})

caption(s, "초록 행 = 자원 제약이 아니라 방법론적 판단으로 바꾼 축. 이 둘은 논문보다 나은 선택이라고 주장할 수 있는 지점.",
        0.5, 6.45, 12.4)
footer(s, 10)
notes(s, """[이 표의 사용법]
"논문과 다른데 재현이라 할 수 있나"라는 질문에 대한 방어 문서입니다. 축마다 (a) 어쩔 수 없어
바꾼 것과 (b) 일부러 바꾼 것을 구분하는 게 핵심입니다.

[어쩔 수 없이 바꾼 것 — 자원 제약]
모델, 하드웨어, 데이터셋, 런 프로토콜, 병렬성. 여기는 변명하지 말고 한계로 명기합니다.
특히 DP=1이라 논문 6.2.2절의 멀티레플리카 결과(+54~79%, churn)는 재현 범위 밖입니다.
발표에서 먼저 밝히는 게 좋습니다.

[일부러 바꾼 것 — 초록 행 두 개, 여기가 방어 포인트]
1) 압박 emulation: 논문은 H200의 HBM을 80GB로 capping해서 H100급 압박을 흉내냅니다.
   우리는 GPU가 원래 작아서 native로 fit≈4.2, 이미 압박 레짐입니다. 인위 조작이 논문보다
   적습니다. 대신 레짐 미세조정은 L(컨텍스트 예산)로 합니다. 왜 L이냐면, GPU가 작아서
   C_gpu를 위로 올리는 방향이 불가능하기 때문입니다.
   구체적으로: L=128k(peak 65.7k)를 유지하면 C=20의 작업집합이 1.31M 토큰인데 용량이
   786k(=3 x 262k)라 C=20부터 이미 overflow입니다. 그러면 "C=20에서는 동률"이라는 위생
   대조군을 잃습니다. L=64k로 줄이면 windowed median peak가 38~40k가 되어 C=20 작업집합이
   약 780k로 용량과 거의 같아지고(동률 확보), C=80은 3.1M으로 강압박이 됩니다.
   즉 L 축소는 논문 그림의 모양을 재현하기 위한 사이징입니다.
2) 전처리: 기존 early-cutoff 방식(prefix truncation)은 세션 뒤를 잘라서 세션당 턴 수를
   median 17에서 5로 줄이고, busy/idle 전이를 17.6에서 1.3으로 붕괴시킵니다. MORI 평가에
   필수인 "프로그램이 두 국면을 오간다"는 성질이 사라집니다. 그래서 중반부를 보존하는
   turn-window slicing으로 바꿉니다. 이건 논문 재현을 위한 필수 수정입니다.

[L 축소의 리스크는 정직하게]
L을 128k에서 64k로 줄이면서도 전이를 보존할 수 있다는 것은 아직 가설입니다.
ec40k가 40k에서 전이 1.3으로 붕괴한 건 prefix truncation 때문이었고 우리는 방식이 다르지만,
게이트 G1에서 "전이 median >= 4"를 실측으로 판정하고 통과 못 하면 L을 다시 올립니다.
이게 L 축소의 최대 리스크입니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S11 — 데이터셋 분포 비교
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "데이터셋 분포 — 논문 trace vs 내 trace",
      "busy phase 길이는 거의 같다. 하지만 우리 tail이 훨씬 무겁다 — 다음 7장에서 이 격차를 어떻게 좁히는지 다룬다.")

figure(s, "mori_trace_pctile_yunuikang.png", 0.45, 1.68, 6.3, 3.42)

table(s, [
    ["지표 (per-turn tool_s)", "논문", "full", "ec128k", "ec40k", "swe"],
    ["tool P50", "1.096 s", "0.188", "0.155", "0.092", "0.227"],
    ["tool P90", "2.034 s", "10.2", "7.06", "4.80", "0.643"],
    ["tool P99", "19.98 s", "210", "150.8", "129.4", "2.46"],
    ["tool P99.95", "83.63 s", "2,502", "300", "300", "30"],
    ["short/long @2 s", "87 / 13", "75.8 / 24.2", "79.7 / 20.3", "85.7 / 14.3", "98.5 / 1.5"],
    ["long tool-time 점유", "58%", "98.7%", "96.3%", "96.0%", "29.9%"],
    ["busy phase P50 / P90", "20 / 81 s", "9.6 / 77.7", "9.5 / 73.1", "8.2 / 38.9", "98 / 301"],
    ["전이 / 세션", "TBD", "17.6", "8.6", "1.3", "0.6"],
    ["세션 ι mean", "TBD", "0.341", "0.335", "0.256", "0.042"],
    ["MORI 적합성", "-", "원본", "차선", "전이 붕괴", "degenerate"],
], 6.95, 1.68, 5.95, 3.42, fs=8.5, hdr_fs=9,
    col_widths=[1.65, 1.0, 0.9, 0.85, 0.8, 0.75],
    hl_rows={6: CREAM, 8: REDBG})
caption(s, "논문 열 = MORI.pdf Fig.3 / Fig.5 (직접 대조) · 내 trace 4열 = 계획서 §C-4 측정표 (초 단위) · "
           "busy phase·전이·ι 행은 §C-1 · TBD = 논문에 해당 수치 없음",
        6.95, 5.13, 5.95, size=8)

bullets(s, [
    ("유사: busy phase P90이 거의 같다 (논문 81 s vs full 77.7 s) → idle 창의 '크기'는 재현된다", 0, GREEN, True),
    ("상이: 우리 P50이 논문의 1/6이고 tail은 훨씬 무겁다. long tool-time 점유 98.7% vs 58%", 0, RED, True),
    ("→ TraceLab full은 논문보다 더 idle-heavy = MORI에 유리한 편향. 다음 5장에서 이걸 어떻게 좁히는지 다룬다", 0, RED, True),
    ("전처리가 파괴하는 것은 tail이 아니라 전이다: tool clamp 300 s는 189k턴 중 894개(0.47%)만 건드림 [§C-2]", 0, INK, False),
], 0.5, 5.55, 12.4, 1.45, size=12.5)
footer(s, 11)
notes(s, """[이 슬라이드가 발표에서 가장 정직해야 하는 부분입니다]
"우리 데이터가 논문 데이터와 다른데 결과를 믿을 수 있나"에 대한 답입니다.

[닮은 점]
busy phase P90이 논문 81초, TraceLab full 77.7초로 거의 같습니다. 즉 "프로그램이 바쁘게
연속 추론하는 구간의 길이"는 두 데이터가 비슷합니다. MORI가 반응해야 할 시간 스케일이
같다는 뜻이라 중요한 일치입니다.

[다른 점 — 그리고 그 방향이 우리에게 불리한 쪽이 아니라는 점]
우리 P50은 169ms로 논문 1,096ms의 1/6.5입니다. 짧은 콜이 더 짧습니다.
반대로 P99는 180.9초로 논문 20초의 9배입니다. tail이 훨씬 무겁습니다.
>2초 콜이 tool-time에서 차지하는 비중이 98.5% 대 58%입니다.
종합하면 TraceLab이 훨씬 더 idle-heavy합니다. idle 창이 더 크고 더 자주 옵니다.

이건 MORI에 유리한 방향의 편향입니다. 즉 우리가 MORI의 이득을 관측하더라도, 그 이득의
일부는 데이터가 MORI에 우호적이어서일 수 있습니다. 이 사실을 결과 슬라이드가 아니라
데이터 슬라이드에서 먼저 밝히는 게 맞습니다. 한계 목록에도 넣었습니다(S15).

[전처리에 대한 통념 정정 — 제가 처음에 틀리게 알고 있던 부분]
저는 원래 "기존 전처리의 tool clamp가 heavy tail을 잘라서 idle 창을 지운다"고 생각했습니다.
실측해보니 절반만 맞았습니다. tool clamp 300초는 ec128k 189,431턴 중 894개(0.47%)만
건드립니다. tail 손상은 생각보다 작습니다.
진짜 파괴되는 것은 tail이 아니라 '전이'였습니다. early-cutoff = prefix truncation이
세션 뒤를 자르면서 세션당 턴 수가 median 17에서 5로 줄고, busy/idle 전이가 세션당
17.6에서 1.3으로 붕괴합니다(ec40k). MORI가 요구하는 "프로그램이 두 국면을 번갈아 간다"는
전제가 거의 사라지는 겁니다.
swebench는 더 심해서 세션 ι 평균이 0.042입니다. 툴이 거의 안 도는 degenerate 워크로드라
MORI든 TA든 차이가 날 수 없습니다. 그래서 음성 대조군으로만 씁니다.

[그래서 무엇을 하는가 — turn-window slicing]
세션 앞부분을 취하는 대신, "컨텍스트 예산 L 안에 들어가는 가장 긴 연속 turn 윈도우"를
고르고 시작점 컨텍스트를 SEED(4096 토큰)로 rebase합니다. 긴 세션의 중반부, 즉 전이가
많은 구간을 살릴 수 있습니다.
여기에 ι 3분위 층화(busy-heavy <0.2 / mixed 0.2~0.6 / idle-heavy >0.6를 1/3씩)를 얹고
출력 파일에 인터리브해서, 같은 시점에 세 부류가 공존하도록 만듭니다. '상대' 랭킹이
의미를 가지려면 동시점 ι 이질성이 필수이기 때문입니다.

[게이트 G1 — 8+2 항목]
전이 median >= 4 / 세션 턴 수 median >= 12 / tool P99 >= 60s / tool P90 >= 5s /
>2s 점유 >= 80% / 윈도우 ι busy(<0.2) >= 35% AND idle(>0.8) >= 12% /
동시점 ι IQR >= 0.35 / peak <= L, 여기에 goguma6 추가 2항(peak <= 64k, C=20 작업집합이
용량 안에 들어갈 것).
이 중 '동시점 ι IQR >= 0.35'는 제가 새로 만든 지표입니다. 단일 duty 상수로 합성한 trace는
IQR이 0에 가까워지는데, 그런 degenerate 데이터를 정량적으로 배제하는 유일한 검사입니다.
이 게이트를 통과 못 하면 M3(구현)으로 넘어가지 않습니다.

[남은 한계 하나]
human-in-the-loop 대기가 전처리 단계에서 이미 사라져 있습니다. 원본 조사 결과
first_input_event_type이 user_message인 라운드가 10.4%로 인간 개입 신호는 존재하지만,
prep이 그런 라운드의 tool_duration_s를 0으로 만들어 실제 인간 think 시간이 소실됩니다.
논문이 드는 idle 3대 원인 중 하나가 없는 셈입니다. 라운드 간 wall gap으로 복원하는
옵션을 검토 중이고(OQ-G), 채택 안 하면 한계로 명기합니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S12 — 데이터셋 가공 (1/7) 왜·무엇을 목표로
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "데이터셋 가공 (1/7) — 왜, 무엇을 목표로",
      "논문 원본 trace를 못 구한다. 그래서 TraceLab을 논문 Fig.3 툴콜 분포에 '최대한 근접'시키는 것이 목표다.")

bullets(s, [
    ("MORI 논문의 자체 수집 Claude Code trace는 공개되지 않음 → TraceLab/SyFI로 대체할 수밖에 없다", 0, INK, False),
    ("목표 재정의: '우리 데이터가 다르다'를 한계로만 적지 않고, 논문 Fig.3 분포에 능동적으로 최근접시킨다 [§C]", 0, INK, True),
    ("58%(long tool-time 점유)는 손잡이가 아니라 분포에서 나오는 결과값 → 58%를 직접 만지지 않고 분포를 맞춘다 [§C]", 0, RED, True),
    ("논문 Fig.3은 human input·subagent 호출을 툴콜에 포함 → 비교는 human-wait 포함 기준 apples-to-apples [논문 §3.2]", 0, INK, False),
    ("두 축은 별개: L=64k turn-window(= KV 크기 축) ∧ 툴콜 분포 매칭(= duration 축). primary는 둘 다 만족 [§C]", 0, INK, False),
], 0.5, 1.75, 12.4, 2.5, size=13.5)

text(s, "가공 파이프라인 3단계 (설계 확정, 생성은 다음 승인)", 0.5, 4.35, 8.0,
     0.35, size=14, bold=True, color=BLUE)
chip(s, "① CAP_HARD 300 s 로 tail 정리", 0.5, 4.8, 3.85, BLUE, size=11.5, h=0.42)
text(s, "→", 4.48, 4.83, 0.4, 0.35, size=17, color=GRAY, bold=True)
chip(s, "② 세션 blend 로 long-share 58% 조준", 4.92, 4.8, 3.85, GREEN,
     size=11.5, h=0.42)
text(s, "→", 8.90, 4.83, 0.4, 0.35, size=17, color=GRAY, bold=True)
chip(s, "③ short 콜 날조 금지 (하드 제약)", 9.34, 4.8, 3.5, RED, size=11.5,
     h=0.42)

panel(s, 0.5, 5.5, 12.35, 1.35, CREAM)
text(s, "이 섹션에서 답하는 질문 5개", 0.72, 5.62, 6.0, 0.3, size=12.5,
     bold=True, color=AMBER)
text(s, "(2/7) 우리는 논문에서 얼마나 떨어져 있나 · (3/7) 왜 CAP만으로는 못 좁히나 · "
        "(4/7) human-wait를 왜 넣나\n"
        "(5/7) CAP를 왜 1800 s → 300 s로 내렸나 · (6/7) 어떻게 58%를 조준하나 · (7/7) 그래도 남는 gap은",
     0.72, 5.95, 11.9, 0.8, size=12)
footer(s, 12)
notes(s, """[이 섹션이 새로 생긴 이유]
앞 슬라이드(11)까지는 "우리 데이터가 논문과 다르다"를 한계로 기록하는 데서 끝났습니다.
그건 소극적입니다. 논문 재현이 목적이라면, 우리가 통제할 수 있는 범위 안에서 분포를
논문에 맞추려는 시도를 하고, 그래도 남는 차이를 정량화하는 것이 맞습니다.
이 7장은 그 작업의 측정·진단·설계·한계를 순서대로 보여줍니다.

[핵심 개념 하나 — 58%는 손잡이가 아니다]
가장 흔한 오해가 "58%에 맞추면 되는 것 아니냐"입니다. 58%는 조절 손잡이가 아니라
툴콜 duration 분포에서 파생되는 결과값입니다. 분포가 정해지면 58%는 자동으로 정해집니다.
따라서 58%를 직접 조작하려 들면(예: 임의로 콜 길이를 늘림) 그건 데이터 날조입니다.
우리가 할 수 있는 정당한 조작은 두 가지뿐입니다:
  (a) tail 클램프 — 어디까지를 유효 idle로 볼지 정하는 것
  (b) 세션 선택/조합 — 어떤 세션을 코퍼스에 넣을지 고르는 것
둘 다 "있는 데이터를 고르거나 자르는" 것이지 "없는 데이터를 만드는" 것이 아닙니다.
③ short 콜 날조 금지가 하드 제약인 이유입니다.

[human-wait 포함이 apples-to-apples인 이유]
논문 Fig.3 본문(§3.2)이 명시합니다: 분포가 "hundreds of milliseconds for file reads to
up to minutes for human input or subagent invocations"에 걸쳐 있다고요.
즉 논문의 툴콜 분포에는 인간 대기와 서브에이전트 호출이 이미 포함돼 있습니다.
우리가 human-wait를 빼고 비교하면 정의가 다른 두 분포를 비교하는 셈이 됩니다.
그래서 primary는 human-wait 포함본입니다(4/7에서 자세히).

[두 축이 별개라는 점을 놓치지 마세요]
L=64k turn-window slicing은 "프로그램 하나가 KV를 얼마나 먹느냐"를 다루는 축입니다
(메모리 압박 레짐 사이징). 툴콜 분포 매칭은 "프로그램이 얼마나 오래 노느냐"를 다루는
축입니다(idleness 구조). 둘은 독립이고, 최종 primary는 두 조건을 동시에 만족해야 합니다.
그래서 6/7의 게이트에 'blend ∩ L=64k ∩ 전이≥4'가 교집합으로 들어갑니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S13 — 데이터셋 가공 (2/7) 측정 결과
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "데이터셋 가공 (2/7) — 측정: 우리는 어디에 있나",
      "full은 너무 idle(99.7%), swebench는 너무 busy(29.9%). 논문 58%는 정확히 그 사이에 있다.")

table(s, [
    ["변형", "P50 (s)", "P90", "P99", "P99.95", "short/long @2s", "long time-share"],
    ["논문 target (Fig.3)", "1.096", "2.034", "19.98", "83.63", "87 / 13", "58%"],
    ["full — tools만", "0.196", "8.17", "180", "1,938", "79.6 / 20.4", "98.2%"],
    ["full — +human-wait (PRIMARY)", "0.240", "30.0", "955.7", "27,284", "74.2 / 25.8", "99.7%"],
    ["swebench", "0.227", "0.643", "2.46", "30", "98.5 / 1.5", "29.9%"],
], 0.5, 1.72, 12.4, 1.62, fs=10.5, hdr_fs=10.5,
    col_widths=[2.95, 1.35, 1.3, 1.35, 1.45, 2.15, 1.85],
    hl_rows={1: CREAM, 3: BLUEBG})
caption(s, "논문 행 = MORI.pdf Fig.3 / §3.3 (직접 대조) · 내 3행 = 계획서 §C-4 측정표 "
           "(원본 gz per-call n=431,905, human-wait gap n=33,501, >12h 459건 제외)",
        0.5, 3.4, 12.4, size=9)

figure(s, "mori_fig3_match_yunuikang.png", 0.5, 3.78, 12.35, 3.2)
footer(s, 13)
notes(s, """[표를 읽는 순서]
맨 윗 행이 논문 target, 그 아래 세 행이 우리 후보들입니다. 오른쪽 끝 열(long time-share)이
가장 중요한 요약 지표입니다.

[한눈에 보이는 것]
- swebench 29.9% : 논문 58%보다 아래 (너무 busy — 툴이 거의 안 돎)
- 논문 58%
- full tools만 98.2% / primary 99.7% : 논문보다 훨씬 위 (너무 idle)
즉 우리가 가진 두 극단 사이에 논문이 있습니다. 이건 좋은 소식입니다 — 두 극단을 섞으면
중간을 만들 수 있다는 뜻이고, 그게 6/7의 세션 blend 아이디어입니다.

[그림 (a) 백분위 프로파일에서 봐야 할 것]
P50 지점을 보세요. 논문은 1.10초인데 우리는 0.20초입니다. 즉 우리의 '짧은 콜'이 논문의
짧은 콜보다 5배 이상 짧습니다. 그런데 P90 이후로는 우리 선들이 논문 위로 치솟습니다.
이 교차가 핵심입니다: 우리는 짧은 건 더 짧고 긴 건 더 깁니다. 분산이 논문보다 큽니다.

[그림 (b)에서 봐야 할 것]
보라색 점선이 논문 58%입니다. 우리 세 후보가 그 선의 양쪽에 있습니다.
막대 길이가 곧 long-share이고, 목표는 primary를 저 점선 쪽으로 끌어오는 것입니다.

[측정 방법에 대한 주의 — 질문 나오면]
이번 §C-4 측정은 per-tool-call 단위입니다(원본 gz의 tools[].tool_wall_latency_ms,
n=431,905 콜, Agent 툴콜 1,156개 포함). 앞 슬라이드 11의 표는 per-turn tool_duration_s
단위였습니다. 한 턴에 여러 툴콜이 있을 수 있어 두 단위의 숫자가 조금 다릅니다.
논문 Fig.3은 개별 툴콜 분포이므로, 매칭 작업에는 per-call 쪽이 올바른 비교 단위입니다.
슬라이드 11의 표는 가공본 4종 비교용(per-turn)이라 그대로 두고, 단위를 표 머리에
명시해 뒀습니다.

[human-wait gap 표본 수]
33,501건이고, 12시간을 넘는 459건(유저 이탈로 판단)은 제외했습니다. 이 제외는
4/7과 5/7에서 다시 다룹니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S14 — 데이터셋 가공 (3/7) 진단
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "데이터셋 가공 (3/7) — 진단: 58%는 왜 CAP로 못 맞추나",
      "문제는 tail이 아니라 short 콜이다. 우리 짧은 콜이 너무 짧아 busy-time을 쌓지 못한다.")

bullets(s, [
    ("직관적 처방은 'tail을 자르면 long-share가 내려간다'지만, 실제로는 거의 움직이지 않는다", 0, INK, False),
    ("진짜 원인: short 콜이 너무 짧다 — P50 0.196 s vs 논문 1.096 s (−82%) [§C-4]", 0, RED, True),
    ("exec_command / write_stdin 등 sub-초 콜이 과다 → short 콜이 busy-time을 못 쌓는다 [§C-4]", 0, INK, False),
    ("논문 58%는 short 콜이 1.1 s급이라 나머지 42%를 busy-time으로 채워주기 때문 [§C-4]", 0, INK, True),
    ("→ 분자(long)를 줄이는 게 아니라 분모(전체 tool-time)의 busy 몫이 비어 있는 구조적 문제", 0, RED, True),
], 0.5, 1.75, 12.4, 2.45, size=13.5)

table(s, [
    ["CAP_HARD", "P99", "P99.95", "long time-share"],
    ["84 s (논문 P99.95)", "84", "84", "97.2%"],
    ["300 s (권장)", "300", "300", "98.6%"],
    ["1800 s (기존)", "956", "1,800", "99.3%"],
    ["no-cap", "956", "27,284", "99.7%"],
], 0.5, 4.35, 6.15, 1.75, fs=11, hdr_fs=11,
    col_widths=[2.15, 1.25, 1.4, 1.35], hl_rows={1: REDBG})
caption(s, "primary per-call 기준, 전 duration에 cap 적용 [§C-4]", 0.5, 6.15, 6.15,
        size=9.5)

panel(s, 6.9, 4.35, 5.95, 2.15, CREAM)
text(s, "결정적 관찰", 7.12, 4.47, 5.5, 0.3, size=13, bold=True, color=AMBER)
text(s, "CAP를 논문 P99.95(84 s)까지 내려도 long-share는\n"
        "97.2%. 99.7%에서 2.5%p밖에 안 내려간다.\n"
        "즉 CAP는 58%로 가는 손잡이가 아니다.\n"
        "tail을 아무리 잘라도 short 콜이 busy-time을\n"
        "채워주지 않으면 비율은 그대로다.\n"
        "→ 남은 정당한 수단은 '세션 선택'뿐 (6/7)",
     7.12, 4.82, 5.5, 1.55, size=11)
footer(s, 14)
notes(s, """['long time-share'가 뭔지 쉽게]
전체 툴콜에 쓴 시간을 100이라 할 때, 그중 2초를 넘는 긴 콜들이 차지하는 몫입니다.
개수 비율이 아니라 시간 비율입니다.
논문에서는 콜 개수의 13%인 긴 콜이 시간의 58%를 먹습니다 — 나머지 42%는 짧은 콜
87%가 차곡차곡 쌓아 만든 시간입니다.
우리 데이터에서는 짧은 콜 75~80%가 만드는 시간이 겨우 1~2%밖에 안 됩니다.
콜 하나가 0.2초라 아무리 많아도 시간이 안 쌓이기 때문입니다.

[왜 이게 중요한가 — MORI의 관점에서]
busy phase란 "짧은 콜이 연달아 오면서 GPU를 계속 쓰는 구간"입니다. 우리 데이터에서
짧은 콜은 0.2초라, 콜이 연달아 와도 프로그램이 busy 상태로 '머무는 시간'이 거의 없습니다.
그래서 프로그램이 사실상 idle 상태에만 오래 머무르는 것처럼 보입니다.
MORI가 구분해야 할 두 국면 중 한쪽(busy)이 시간적으로 얇은 셈입니다.

[CAP sweep 표가 말하는 것]
84초로 자르면 P99도 P99.95도 전부 84초가 됩니다. 극단적으로 tail을 뭉갠 것이죠.
그런데도 long-share는 97.2%입니다. no-cap 99.7% 대비 2.5%p 차이입니다.
이 실험이 "CAP로는 58%에 못 간다"를 정량적으로 못 박습니다.
수학적으로도 당연한데, 긴 콜을 짧게 잘라도 여전히 2초보다는 훨씬 기니까 여전히 'long'으로
분류되고, 짧은 콜의 시간 몫은 조금도 늘지 않기 때문입니다.

[그래서 무엇을 하지 않기로 했나 — 중요]
여기서 유혹이 하나 생깁니다: "short 콜 길이를 인위로 늘려서 1.1초로 맞추면 되잖아".
그건 데이터 날조입니다. 실제로 존재하지 않는 워크로드를 만들어 놓고 재현이라 부르는
셈이 됩니다. 그래서 §C-4-(3)에 'short 콜 길이 조작/합성 금지'를 하드 제약으로 박았습니다.
우리가 쓸 수 있는 건 tail 정리와 세션 선택뿐이고, 그걸로 갈 수 있는 데까지만 갑니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S15 — 데이터셋 가공 (4/7) human-wait 복원
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "데이터셋 가공 (4/7) — human-wait 복원 (실데이터)",
      "timing_events가 실제 wall-clock을 담고 있다. 모델링이 아니라 복원이므로 primary에 넣는다.")

bullets(s, [
    ("OQ-G 검증 완료: `timing_events`는 실제 wall-clock 타임스탬프를 담는다 → 인간 대기는 '실데이터 복원' [§C-3]", 0, GREEN, True),
    ("user_message 라운드 직전의 wall gap 실측 표본: 8.6 / 23.6 / 82.5 / 224.7 / 429.7 s — 현실적 분포 [§C-3]", 0, INK, False),
    ("논문 Fig.3이 human input을 툴콜에 포함 → 빼면 그건 실데이터 삭제. 그래서 primary로 채택 [§C-3 결정]", 0, INK, True),
    ("대가: long-share가 98.2% → 99.7%로 논문에서 오히려 더 멀어진다. 그래도 뺄 수 없다 [§C-4]", 0, RED, True),
    ("투명성: human-wait 유무를 ι 층화 민감도 축으로 두고 primary / ablation 양쪽 병기 [§C-3, §D-2]", 0, INK, False),
], 0.5, 1.75, 12.4, 2.6, size=13.5)

table(s, [
    ["원본 gz 조사 결과 (120k 라운드 샘플) [§C-3]", "값"],
    ["first_input_event_type = tool_result", "87.3%"],
    ["first_input_event_type = user_message  (인간 개입 신호)", "10.4%"],
    ["first_input_event_type = None", "2.3%"],
    ["zero-tool 라운드", "10.2%"],
    ["subagent 스폰 (Agent 툴콜) — 463 / 120k 라운드", "0.39%"],
], 0.5, 4.5, 7.05, 1.95, fs=10.5, hdr_fs=10.5, col_widths=[5.4, 1.65])

panel(s, 7.8, 4.5, 5.05, 1.95, PANEL)
text(s, "왜 이게 '복원'인가", 8.02, 4.62, 4.6, 0.3, size=12.5, bold=True,
     color=BLUE)
text(s, "기존 prep은 human 라운드의\n"
        "tool_duration_s를 0으로 만들어\n"
        "인간 think 시간을 버렸다.\n"
        "그런데 원본에는 그 시간이\n"
        "타임스탬프로 남아 있었다.\n"
        "→ 없는 값을 만드는 게 아니라\n"
        "   버려진 값을 되살리는 것",
     8.02, 4.9, 4.6, 1.45, size=11)
footer(s, 15)
notes(s, """[사용자 규칙: "실데이터면 채택"]
이 결정의 근거는 단순합니다. 만약 human-wait를 시뮬레이션으로 '모델링'해야 했다면
넣지 않았을 겁니다. 가정이 결과를 만드는 구조가 되니까요.
그런데 조사해보니 원본 gz의 timing_events에 실제 wall-clock 타임스탬프가 있었습니다.
user_message 라운드의 직전 라운드 마지막 이벤트와 user_message 이벤트 사이의 시간차가
곧 실제 인간 대기 시간입니다. 표본을 뽑아 보니 8.6초, 23.6초, 82.5초, 224.7초, 429.7초 등
사람이 읽고 판단하고 답하는 시간으로 자연스러운 값들이었습니다.
즉 우리가 하는 일은 모델링이 아니라, 전처리가 0으로 뭉갠 값을 원본에서 되살리는 복원입니다.

[논문 정의와의 정합]
논문 Fig.3(§3.2)은 툴콜 분포에 human input을 포함합니다. 논문 Fig.4는 idle phase의
3대 원천으로 (a) 긴 툴콜 (b) human interaction (c) subagent를 듭니다.
우리 상황을 보면 subagent는 이미 부모의 단일 긴 툴콜로 접혀 있어 독립 분리가 불가능합니다
(원본에 parent_session_id/agent_type 필드가 없음, Agent 툴콜 0.39%로만 관찰).
여기서 human-wait까지 빼면 3대 원천 중 둘이 사라져 idle이 심각하게 과소대표됩니다.
그래서 §C-3에서 primary 채택으로 결정했습니다.

[불편한 진실을 먼저 말하기]
human-wait를 넣으면 long-share가 98.2%에서 99.7%로 올라갑니다. 즉 우리 목표(58%)에서
더 멀어집니다. 매칭 관점에서는 손해입니다.
그런데도 넣습니다. 목표에 가까워지려고 실데이터를 삭제하는 건 매칭이 아니라 조작이기
때문입니다. 이 순서 — "정의 정합성이 우선, 매칭은 그 다음" — 를 발표에서 분명히 하는 게
좋습니다. 질문이 나오면 이게 가장 강한 방어입니다.

[그래서 투명성 장치]
human-wait 유무를 실험 축으로 둡니다. primary(주입)와 ablation(미주입) 양쪽을 다 돌리고
결과를 병기합니다. 만약 MORI의 이득이 human-wait 주입에서만 나온다면 그것도 발견이고,
양쪽에서 다 나온다면 결론이 더 튼튼해집니다. 어느 쪽이든 숨기지 않습니다.

[남는 한계]
서브에이전트는 여전히 session=program 1:1입니다. 논문은 subagent에 별도 program_id를
부여하지만(§5 구현 요구사항), 우리 trace로는 분리가 불가능합니다. 이건 §5-(11)에
한계로 남깁니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S16 — 데이터셋 가공 (5/7) CAP_HARD 결정
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "데이터셋 가공 (5/7) — CAP_HARD: 1800 s → 300 s",
      "5분 넘는 human gap 28.5%는 '자리 비움'이지 CPU tier가 겨냥하는 idle이 아니다.")

table(s, [
    ["human-wait gap 분포 (n = 33,501, >12h 459건 제외) [§C-4]", "값"],
    ["P50", "123 s"],
    ["P90", "1,317 s"],
    ["P99", "18,358 s"],
    ["P99.95", "41,520 s"],
    ["max", "43,198 s"],
    ["> 300 s 비율", "28.5%"],
    ["> 1800 s 비율", "7.9%"],
    ["> 3600 s 비율", "3.7%"],
], 0.5, 1.75, 5.55, 2.85, fs=10.5, hdr_fs=10, col_widths=[3.95, 1.6],
    hl_rows={6: CREAM})

text(s, "300 s를 고른 세 가지 이유 [§C-4]", 6.3, 1.75, 6.5, 0.35, size=14,
     bold=True, color=BLUE)
bullets(s, [
    ("논문의 '분 단위' tail 스케일에 근접 — 84 s보다 실데이터를 존중", 0, INK, False),
    ("5분 초과 human gap 28.5%는 대부분 '자리 비움' → 운영상 세션 일시정지로 처리하는 게 맞다", 0, INK, True),
    ("MORI가 실제로 활용하는 분 단위 idle 창은 그대로 보존", 0, INK, False),
], 6.3, 2.2, 6.5, 1.5, size=12.5)

panel(s, 6.3, 3.85, 6.55, 0.85, REDBG)
text(s, "84 s는 paper-strict ablation으로만", 6.5, 3.94, 6.1, 0.3, size=12,
     bold=True, color=RED)
text(s, "그 이하로 내리면 MORI가 필요로 하는 long idle 자체가 지워져 regime이 파괴된다 (= MORI에 불리)",
     6.5, 4.24, 6.15, 0.4, size=11)

bullets(s, [
    ("> 12h human gap (54.7 h 등 실측 459건)은 주입에서 제외 — 세션 이탈로 판단 [§C-3]", 0, INK, False),
    ("300 s ~ 12 h 구간은 300 s로 클램프 [§C-3]", 0, INK, False),
    ("cap ∈ {300, 600} 민감도 양쪽 병기 — 단일 값 선택에 결론이 걸리지 않도록 [§C-4, §D-2]", 0, INK, True),
], 0.5, 4.85, 12.4, 1.3, size=12.5)

caption(s, "참고: 툴콜 자체의 clamp(기존 ec 계열 300 s)는 189k턴 중 894개(0.47%)만 건드렸다 [§C-2] — "
           "여기서 말하는 CAP_HARD는 human-wait를 포함한 primary 전체에 적용하는 상한이다.",
        0.5, 6.3, 12.4, size=9.5)
footer(s, 16)
notes(s, """[왜 1800초(30분)에서 내렸나]
base 계획에서는 CAP_HARD=1800초였습니다. 근거는 "논문이 tail은 분 단위로 뻗는다고 했으니
넉넉히 두자"였습니다. 그런데 human-wait를 주입하기로 하면서 상황이 달라졌습니다.
human gap의 P90이 1,317초(22분), P99가 18,358초(5시간)입니다. 1800초 상한이면
이 거대한 gap들이 거의 그대로 들어옵니다.

[핵심 논거 — 28.5%라는 숫자]
5분(300초)을 넘는 human gap이 28.5%입니다. 이게 무슨 상황인지 생각해보면,
사람이 자리를 비웠거나 다른 일을 하다가 나중에 돌아온 것입니다.
운영 관점에서 이건 "곧 재개될 idle"이 아니라 사실상 세션 일시정지입니다.
실제 서빙 시스템이라면 이런 세션의 KV를 CPU DRAM에 5시간씩 붙들고 있지 않습니다.
MORI의 CPU tier가 겨냥하는 것은 "몇 초~몇 분 뒤에 돌아올 프로그램"입니다.
그래서 300초에서 자르고, 그 이상은 전부 300초로 취급합니다.

[왜 84초는 아닌가 — 반대 방향의 실수]
84초는 논문 Fig.3의 P99.95입니다. "논문에 정확히 맞추자"는 관점에서 매력적으로 보입니다.
그런데 여기까지 내리면 우리 데이터의 분 단위 idle 창이 전부 84초로 뭉개집니다.
MORI가 이득을 내는 상황이 바로 그 분 단위 idle인데, 그걸 지워버리면 MORI가 활약할
무대 자체가 사라집니다. 즉 regime을 파괴하면서 MORI에 불리한 데이터를 만드는 셈입니다.
매칭 지표 하나를 위해 실험 목적을 훼손하는 전형적인 실수입니다.
그래서 84초는 별도 ablation(paper-strict)으로만 돌리고 primary로 쓰지 않습니다.

[민감도를 병기하는 이유]
300초라는 값은 판단이 들어간 선택입니다. 판단이 결론을 좌우하면 안 되므로
cap 300과 600 양쪽을 돌려 결과가 뒤집히지 않는지 확인합니다.
만약 300과 600에서 결론이 달라진다면, 그 사실 자체를 보고해야 합니다.

[54.7시간짜리 gap 459건]
12시간을 넘는 gap이 459건 있습니다. 최장 54.7시간입니다. 이건 사용자가 세션을 열어두고
이틀 뒤에 돌아온 경우로, 어떤 기준으로도 서빙 시스템이 대비할 idle이 아닙니다.
클램프가 아니라 아예 주입에서 제외합니다.

[표에서 헷갈리기 쉬운 점 — 질문 대비]
툴콜 자체의 clamp와 CAP_HARD는 다릅니다. 기존 ec 계열의 300초 clamp는 툴콜 duration에
적용됐고 189k턴 중 894개(0.47%)만 건드렸습니다. 여기서 말하는 CAP_HARD는
human-wait를 포함한 primary 전체 duration에 적용하는 상한입니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S17 — 데이터셋 가공 (6/7) ι 층화 & reshape
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "데이터셋 가공 (6/7) — ι 층화와 reshape 설계",
      "세션이 0% 아니면 98%로 양극화돼 있다. 단일 stratum엔 58%가 없지만, 섞으면 조준할 수 있다.")

table(s, [
    ["stratum (세션 ι 3분위)", "n", "median long-time-share (세션)"],
    ["busy-heavy  ι < 0.28", "1,420", "0.0%  (거의 전부 short 콜)"],
    ["mixed", "1,425", "97.5%"],
    ["idle-heavy  ι ≥ 0.91", "1,420", "99.9%"],
], 0.5, 1.75, 6.1, 1.5, fs=10.5, hdr_fs=10.5, col_widths=[2.35, 0.85, 2.9],
    hl_rows={1: GREENBG})
caption(s, "full·human-wait 포함·세션 단위. tercile q33 = 0.277 / q67 = 0.906, mean ι = 0.574 [§C-4]",
        0.5, 3.3, 6.1, size=9)

panel(s, 6.85, 1.75, 6.0, 1.85, CREAM)
text(s, "양극화가 오히려 기회다", 7.07, 1.87, 5.5, 0.3, size=13, bold=True,
     color=AMBER)
text(s, "단일 stratum에는 58%가 존재하지 않는다.\n"
        "그러나 busy-heavy(0%)와 idle 세션을\n비율 조합하면 aggregate 58%를 조준할 수 있다.\n\n"
        "덤: 저-ι stratum 자체가 논문과 유사한\nbusy regime → stratum별 비교로도 보고",
     7.07, 2.2, 5.6, 1.3, size=11.5)

text(s, "reshape 3단계 [§C-4]", 0.5, 3.75, 6.0, 0.35, size=13.5, bold=True,
     color=BLUE)
bullets(s, [
    ("CAP_HARD 300 s 클램프로 tail·자리비움 정리", 0, INK, False),
    ("busy-heavy와 idle stratum을 선형 조합해 aggregate long-share를 58%에 최근접 "
     "(∩ L=64k · 전이 median ≥ 4 제약과 교집합)", 0, INK, True),
    ("short 콜 길이 조작·합성 금지 — tail 정리와 세션 선택으로 갈 수 있는 데까지만", 0, RED, True),
], 0.5, 4.15, 6.2, 1.6, size=12)

text(s, "매칭 게이트 (기존 hard 게이트와 병존) [§C-4]", 6.85, 3.75, 6.0, 0.35,
     size=13.5, bold=True, color=BLUE)
bullets(s, [
    ("P50 / P90 / P99 논문 대비 best-effort 최근접 — P50은 구조상 미달 가능 → "
     "잔여 gap 수치 명기가 통과 요건 (hard-fail 아님)", 0, INK, True),
    ("long-time-share 58%에 최근접 (달성값·잔여 gap 병기)", 0, INK, False),
    ("논문 CDF 대비 KS 거리 최소화", 0, INK, False),
    ("hard 게이트 유지: 전이 median ≥ 4 · 동시점 ι IQR ≥ 0.35 · peak ≤ 64k", 0, RED, True),
], 6.85, 4.15, 6.0, 1.8, size=12)

panel(s, 0.5, 6.05, 12.35, 0.8, PANEL)
text(s, "turn-window slicing이 prefix truncation과 다른 이유: 후자는 세션 뒤를 잘라 busy↔idle 전이를 "
        "17.6 → 1.3으로 붕괴시킨다 [§C-2]. 전자는 컨텍스트 예산 안에 들어가는 '가장 긴 연속 구간'을 골라 중반부를 살린다.",
     0.72, 6.2, 11.9, 0.6, size=11.5)
footer(s, 17)
notes(s, """[층화 표가 보여주는 놀라운 사실]
세션별 long-time-share의 분포가 이봉(bimodal)입니다. 중간이 거의 없습니다.
busy-heavy 3분위 세션들은 median 0.0% — 즉 2초 넘는 콜이 사실상 없습니다.
반대로 idle-heavy는 99.9%입니다. mixed조차 97.5%로 사실상 idle 쪽입니다.
즉 "평균 58%짜리 세션"은 우리 코퍼스에 존재하지 않습니다.

[그런데 이게 왜 기회인가]
aggregate 지표는 세션들의 가중 평균입니다. 0%짜리 세션과 99%짜리 세션을 적절한
비율로 섞으면 전체 58%를 만들 수 있습니다. 두 극단이 다 있다는 것은
목표값을 사이에 두고 있다는 뜻이고, 선형 조합으로 조준이 가능하다는 뜻입니다.
만약 우리 세션이 전부 95~99% 사이에 몰려 있었다면 어떤 조합으로도 58%에 못 갔을 겁니다.

[중요한 부수 효과 — 저-ι stratum]
busy-heavy stratum(ι<0.28)은 그 자체로 논문과 유사한 busy regime입니다.
그래서 aggregate 매칭과 별개로, stratum별 시스템 비교를 따로 보고할 계획입니다(§D-2).
논문 결과와 가장 가깝게 대응되어야 하는 구간이 바로 이 저-ι stratum입니다.
aggregate가 idle 쪽으로 치우쳐도 이 층에서 논문 경향이 재현되면 결론이 훨씬 튼튼해집니다.

[게이트를 두 종류로 나눈 이유 — 이 설계의 핵심]
- hard 게이트(전이 median≥4, 동시점 ι IQR≥0.35, peak≤64k): 통과 못 하면 진행 불가.
  이건 실험이 성립하기 위한 최소 조건입니다. 전이가 없으면 MORI가 발동할 기회 자체가
  없고, ι 이질성이 없으면 '상대' 랭킹이 무의미하고, peak가 L을 넘으면 서빙이 안 됩니다.
- 매칭 게이트(P50/P90/P99, long-share 58%, KS): best-effort입니다.
  P50은 구조적으로 못 맞출 가능성이 큽니다(3/7의 진단). 그래서 "달성"이 아니라
  "잔여 gap을 수치로 명기하는 것"을 통과 요건으로 정의했습니다.
이 구분이 없으면 못 맞추는 지표 때문에 프로젝트가 멈추거나, 반대로 맞추려고 데이터를
조작하게 됩니다. 둘 다 피하려는 설계입니다.

[turn-window slicing 복습]
prefix truncation은 세션의 앞부분만 남기고 뒤를 자릅니다. 그러면 세션당 턴 수가
median 17에서 5로 줄고 busy↔idle 전이가 17.6에서 1.3으로 붕괴합니다(ec40k에서 실측).
turn-window slicing은 대신 "컨텍스트 예산 L 안에 들어가는 가장 긴 연속 turn 구간"을
고르고 시작점 컨텍스트를 SEED로 rebase합니다. 긴 세션의 중반부(전이가 많은 구간)를
살릴 수 있습니다. 이게 L=64k로 줄이면서도 전이를 보존할 수 있다고 기대하는 근거입니다.
다만 아직 가설이고 G1에서 실측 판정합니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S18 — 데이터셋 가공 (7/7) 정직한 한계
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "데이터셋 가공 (7/7) — 정직한 한계",
      "정확히 못 맞출 수 있다. 목표는 '최근접 + 잔여 gap 정량 명기'이지 숫자 맞추기가 아니다.")

bullets(s, [
    ("TraceLab은 논문과 다른 에이전트다 → short-call busy-time이 구조적으로 빈약 [§5-(12)]", 0, INK, True),
    ("따라서 58%와 P50 = 1.096 s에 정확히 못 맞출 수 있다. 이를 실패가 아니라 예상된 결과로 미리 선언한다", 0, RED, True),
    ("목표는 '최근접 + 잔여 gap 수치 명기'. fabrication(short 콜 합성)은 금지 [§C-4, §5-(12)]", 0, RED, True),
    ("primary는 구성된(constructed) subset — 자연 도착분포가 아니다 [§5-(13)]", 0, INK, True),
    ("보완: 저-ι stratum은 논문 유사 regime → stratum별 비교로 aggregate gap을 보완 [§5-(12), §D-2]", 0, GREEN, True),
], 0.5, 1.75, 12.4, 2.6, size=13.5)

text(s, "결과와 함께 반드시 병기할 것 [§C-4-(4)]", 0.5, 4.35, 6.0, 0.35,
     size=14, bold=True, color=BLUE)

table(s, [
    ["병기 항목", "왜 필요한가"],
    ["가공 전 원본 분포", "무엇을 출발점으로 삼았는지 없으면 재현 불가"],
    ["blend 비율 (busy-heavy : mixed : idle 세션 몫)", "aggregate 58%가 어떻게 구성됐는지 드러냄"],
    ["소스 세션 분포", "특정 세션에 과대 의존하지 않았는지 검증 가능"],
    ["논문 대비 잔여 gap (P50 / P90 / P99 / long-share)", "'최근접'의 실제 도달 지점을 정량화"],
    ["human-wait primary vs ablation 양쪽 결과", "주입 결정이 결론을 만들지 않았음을 보임"],
    ["CAP ∈ {300, 600} 민감도", "판단이 들어간 상한이 결론을 좌우하지 않음을 보임"],
], 0.5, 4.75, 12.4, 2.1, fs=10.5, hdr_fs=10.5, col_widths=[5.3, 7.1])
footer(s, 18)
notes(s, """[이 슬라이드를 넣은 이유]
매칭 작업은 잘못하면 "논문에 맞을 때까지 데이터를 주무른 것"으로 보입니다.
그 의심을 받지 않는 유일한 방법은, 무엇을 했고 무엇을 못 했는지를 결과와 함께
전부 드러내는 것입니다.

[구조적 한계를 미리 선언하는 이유]
3/7에서 봤듯이 P50 gap(0.196 vs 1.096초)은 우리가 고칠 수 없습니다.
TraceLab을 만든 에이전트가 애초에 다른 도구를 다른 방식으로 씁니다.
sub-초 exec_command를 많이 쓰는 에이전트와, 1초대 파일 읽기를 하는 Claude Code는
다른 워크로드입니다.
그러므로 "58% 달성 실패"는 실험의 실패가 아니라 데이터의 속성입니다.
이걸 결과가 나온 뒤에 변명하면 궁색해지지만, 미리 선언해두면 정직한 보고가 됩니다.

[constructed subset이라는 고백]
blend로 만든 primary는 자연스러운 도착 분포가 아닙니다. 우리가 목표값을 겨냥해
세션을 골라 섞은 것입니다. 이건 논문 매칭이라는 목적에는 정당하지만, "실제 프로덕션
트래픽이 이렇게 생겼다"는 주장은 절대 할 수 없습니다.
meta 파일과 한계 절에 명시하고, blend 비율을 같이 공개합니다.

[그래도 결론이 서는 이유 — 여기서 마무리하세요]
세 겹의 방어가 있습니다.
1) 매칭된 primary에서 MORI 이득이 나오는지 본다.
2) 저-ι stratum(논문 유사 busy regime)에서 따로 본다 — 여기가 논문과 가장 잘 대응됩니다.
3) 음성 대조군(ec40k 전이 붕괴, swebench ι 0.042)에서 이득이 사라지는지 본다.
1번만으로는 "데이터를 맞춰서 얻은 결과 아니냐"는 반론이 가능하지만, 2번과 3번이
같이 성립하면 관측된 이득이 idleness 구조에서 온다는 논거가 됩니다.

[병기 항목 표에 대해]
여섯 항목 전부 결과 로그와 meta에 자동으로 남기도록 스크립트에 넣을 계획입니다.
사람이 나중에 기억해서 적는 방식이면 반드시 빠집니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S19 — 일치 기대 경향
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "논문과 일치할 것으로 기대하는 경향",
      "우리는 이미 논문의 압박 레짐 안에 있다. 그래서 그림의 '모양'은 재현되어야 한다 — 절대 수치는 아니다.")

table(s, [
    ["조건", "예측", "근거"],
    ["C=20, 오프로딩 4종", "격차 5% 이내 (위생 대조 P3)",
     "논문 C=20: 546 vs 534 = 2% [논문].\nL=64k 사이징으로 C=20 작업집합을 용량에 맞춤 [결정]"],
    ["C=50", "MORI가 TA+O 대비 +10 ~ 25%", "논문 30B의 30% 구간 [논문]"],
    ["C=80, r=1x", "MORI >= TA+O x1.15, TTFT <= 0.85x",
     "논문 하한 +20% / -18% 보다 완화 (DP=1, 다른 HW, 다른 trace) [결정]"],
    ["C=80, r=2x", "격차가 1x보다 더 벌어진다",
     "TA+O는 CPU를 2배 줘도 TTFT 56→58s 무변 [논문]. 조율 없이는 용량을 못 씀"],
    ["TA+O의 C 스케일링", "비단조 (C=50 > C=80) 가능",
     "논문 B200 1x: 147→181→146 [논문]. eviction thrashing"],
    ["MORI의 C 스케일링", "단조 비감소", "논문 136→191→189 [논문]"],
    ["trace를 ec40k로 교체", "MORI 이득이 크게 축소",
     "전이 1.3/세션 [실측] → sticky·ι 랭킹이 발동할 기회 자체가 없음"],
    ["trace를 swebench로 교체", "MORI ≈ TA+O (차이 무의미)",
     "세션 ι mean 0.042 [실측] → idle 창 부재. degenerate 음성대조"],
], 0.5, 1.75, 12.4, 4.1, fs=10, hdr_fs=10.5,
    col_widths=[2.35, 3.55, 6.5], hl_rows={1: GREENBG, 4: CREAM})

panel(s, 0.5, 6.0, 12.35, 0.95, PANEL)
text(s, "기존 트랙(fit x d 트레이드오프)과의 연결", 0.72, 6.1, 6.0, 0.3,
     size=12.5, bold=True, color=BLUE)
text(s, "기존 트랙에서 찾은 전환점 fit x d* = 0.62 [실측, logs/2026-07-19].  "
        "d = 1 - ι.  MORI는 d가 낮은(= ι가 높은, 오래 노는) 프로그램을 CPU로 내려 "
        "같은 fit에서 유효 동시 수용량을 늘리는 것 — 즉 같은 곡선 위에서 왼쪽으로 미는 조작이다.",
     0.72, 6.42, 11.9, 0.5, size=11.5)
footer(s, 19)
notes(s, """[이 슬라이드의 목적]
결과가 나오기 전에 예측을 문서로 박아두는 것입니다. 나중에 결과를 보고 사후 해석하면
확증편향이 들어갑니다. 미리 써두면 어긋났을 때 "예측이 틀렸다"고 정직하게 말할 수 있습니다.

[왜 '모양'은 재현되어야 한다고 믿는가]
논문 결과의 형태는 메모리 압박 정도(fit)의 함수입니다. 우리 native fit이 약 4.2로
논문의 압박 구간에 들어가 있고, C=20에서 용량과 작업집합이 맞도록 L=64k로 사이징했습니다.
같은 레짐에 있으면 같은 모양이 나와야 한다는 것이 논거입니다.

[반대로 재현되지 않을 것 — 절대 수치]
tok/s 절대값은 하드웨어(5090 vs H200/B200)와 모델(8B vs 7B/30B/70B)이 달라 비교 불가입니다.
시스템 간 상대 비교만 유효합니다. 엔진을 SGLang로 통일한 덕에 이 한계는 조금 완화됐습니다
(base 계획 시점에는 vLLM이라 더 심했습니다).

[초록 행과 노란 행]
초록(C=20): 여기서 차이가 크게 나면 우리 구현에 버그가 있다는 신호입니다. 위생 검사입니다.
노란(r=2x): 여기가 MORI 주장의 핵심 검증입니다. 이득이 '메모리를 더 줘서'가 아니라
'조율해서' 온다는 것을 보이는 자리입니다. r=1x에서 2x로 갈 때 TA+O는 그대로인데
MORI만 좋아져야 합니다.

[음성 대조 두 개가 중요한 이유]
ec40k(전이 붕괴)와 swebench(ι 0.042)에서 MORI 이득이 사라져야 합니다. 만약 이 두
데이터에서도 MORI가 이긴다면, 우리가 측정하는 것이 idleness 스케줄링이 아니라 뭔가 다른
것(예: 구현 차이로 인한 우연한 이득, 측정 버그)이라는 뜻입니다.
즉 "지는 것이 예측인 실험"을 일부러 넣어뒀습니다.

[fit x d 연결]
제가 기존에 하던 트랙에서 전환점 fit x d* = 0.62를 실측했습니다. d는 duty, 즉 프로그램이
GPU를 실제로 쓰는 시간 비중이고 ι = 1 - d입니다. MORI를 이 언어로 번역하면,
d가 낮은(오래 노는) 프로그램의 KV를 GPU 밖으로 빼내 같은 물리 fit에서 더 많은 프로그램을
수용하는 조작입니다. 두 트랙이 같은 좌표계 위에 있다는 점을 보이면 논문 재현이 기존 연구의
연장선에 놓입니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S20 — 내 실험 계획
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "실험 계획 — Phase 1 → Phase 2, 마일스톤과 게이트",
      "Phase 1은 엔진과 무관해 SGLang 리스크와 병렬로 간다. 게이트를 통과 못 하면 다음 단계로 넘어가지 않는다.")

table(s, [
    ["", "Phase 1 — 스케줄러 전용 (엔진 무관)", "Phase 2 — SGLang HiCache 실연동"],
    ["CPU tier 실체", "mori_tier.py 장부상 큐", "HiCache host memory pool (계층 radix의 host tier)"],
    ["재로드 비용", "비용 모델 sleep(ctx x B_tok / BW_eff)\nBW_eff는 PCIe 마이크로벤치 실측", "SGLang이 실제 host→device 전송으로 지불"],
    ["typed eviction", "없음 (스케줄러 결정만)", "HiRadixCache 노드 타입 라벨 + 정렬키 패치"],
    ["엔진 수정", "0 (SGLang 설치조차 불필요)", "monkey-patch 또는 fork"],
    ["선후행", "SGLang 검증과 무관하게 선행 가능", "M-SGL 스모크 통과 후"],
], 0.5, 1.72, 6.35, 2.15, fs=9.5, hdr_fs=9.5,
    col_widths=[1.25, 2.5, 2.6], hdr_bg=BLUE)

table(s, [
    ["M", "내용", "GPU", "게이트"],
    ["M0", "브랜치 mori 생성", "-", "완료"],
    ["M1", "trace 가공 (L=64k + Fig.3 분포 매칭)", "-", "G1 + 매칭 게이트 (S17)\n조사·측정 완료 / 생성은 다음 승인"],
    ["M-SGL", "SGLang 설치 + sm_120 스모크", "O", "G-SGL 통과 — READY 126 s,\nHiCache host 9.66 GB 확인 [§A-2b]"],
    ["M3", "Phase 1 구현 + 불변식 I1~I5", "-", "G3: tr 회귀 없음,\nrouter.py/backend/state.py diff 0줄"],
    ["M4", "PCIe 마이크로벤치 + Phase 1 스윕\n(12셀 x 3)", "O", "G4: C=80에서 MORI-sim > TA"],
    ["M5", "Phase 2: typed eviction + I6", "O", "G5: 장부 vs host 점유 ±10%"],
    ["M6", "Phase 2 본 스윕 (18셀 x 3) + 대조", "O", "G6: P1~P4 판정"],
], 7.1, 1.72, 5.75, 3.2, fs=9, hdr_fs=9.5,
    col_widths=[0.62, 2.1, 0.42, 2.61],
    hl_rows={1: GREENBG, 3: GREENBG})

panel(s, 0.5, 4.05, 6.35, 2.3, PANEL)
text(s, "스윕 축과 예산", 0.72, 4.15, 5.8, 0.3, size=12.5, bold=True,
     color=BLUE)
bullets(s, [
    ("시스템 4종 x C{20,50,80} x r{1x,2x} = Phase 2 주 trace 18셀", 0, INK, False),
    ("주 trace = tracelab_mori_L64k / 대조 = ec128k, ec40k, swebench", 0, INK, False),
    ("고정 20분창 x 3 repeat. 승리 선언은 non-overlapping일 때만", 0, INK, False),
    ("예산 약 38 GPU-node-h [계산]  = Phase 2 19.4h + Phase 1 13h + 기타 6h", 0, INK, True),
    ("SGLang 설치·스모크·디버깅 시간은 별도 (불확실)", 0, RED, False),
], 0.7, 4.5, 6.0, 1.7, size=11.5)

panel(s, 7.1, 5.05, 5.75, 1.3, CREAM)
text(s, "지금 위치 / 다음 액션", 7.32, 5.15, 5.3, 0.3, size=12.5, bold=True,
     color=AMBER)
text(s, "완료: M0 · M-SGL 스모크 PASS · M1 조사/측정분(§C-3, §C-4).\n"
        "다음: (1) trace 가공 생성·스크립트화(승인 대기)  "
        "(2) M3 Phase 1 구현 착수  (3) typed eviction 소스 조사(OQ-E2/F)",
     7.32, 5.47, 5.3, 0.8, size=11)
footer(s, 20)
notes(s, """[Phase를 나눈 이유가 핵심입니다]
MORI의 핵심 주장은 "상대 idleness 랭킹이 context-length 랭킹보다 낫다"입니다.
이건 스케줄러만으로 검증할 수 있습니다. CPU tier를 장부상으로만 두고 재로드 비용을
모델로 물리면 TA vs MORI(sim)라는 깨끗한 A/B가 나옵니다.
그래서 Phase 1은 SGLang이 5090에서 안 돌아도 진행됩니다. 프로젝트 최대 리스크(sm_120)를
크리티컬 패스에서 빼내는 구조입니다.

[Phase 1의 약점도 같이 말해야 합니다]
재로드 비용이 실측이 아니라 모델입니다. sleep(ctx x B_tok / BW_eff)로 물리는데,
BW_eff를 PCIe 마이크로벤치로 실측해도 전송 오버헤드·대역 경합을 과소 반영합니다.
따라서 Phase 1은 Phase 2보다 낙관적으로 나올 것으로 예상하고, 어긋나면 Phase 1 결론을
철회한다고 계획서에 못박아 뒀습니다.

[게이트가 있는 이유]
각 마일스톤에서 통과 조건을 미리 정해두고, 통과 못 하면 다음으로 안 갑니다.
- G1(데이터): 전이 median >= 4를 못 넘기면 L=64k를 포기하고 다시 올립니다. L 축소가
  이 프로젝트의 최대 데이터 리스크라 여기서 멈출 수 있게 해뒀습니다.
- G3(격리): git diff로 router.py와 backend/state.py가 0줄인지 기계적으로 확인합니다.
  베이스라인이 오염되면 모든 비교가 무의미해집니다.
- G4(조기 실패 감지): Phase 1에서 C=80에서도 MORI-sim이 TA를 못 이기면 ι 지표나 정책 설계에
  결함이 있다는 뜻입니다. 엔진 작업(M5)에 시간을 쓰기 전에 여기서 잡습니다.
- G5(정합성): 스케줄러 장부의 CPU tier 점유와 엔진 실제 host tier 점유가 ±10% 안에 있어야
  합니다. 어긋나면 스케줄러는 여유가 있다고 믿는데 엔진은 이미 축출한 상태 = 조용한 성능 붕괴.

[프로토콜을 고정 시간창으로 바꾼 이유 — 질문 예상]
기존 하네스는 run-to-completion(모든 프로그램 완주)이었습니다. 두 가지 문제가 있습니다.
1) 최장 세션의 E2E가 셀당 시간 하한이 됩니다. 기존 로그에서 128k는 셀당 13.7시간이었습니다.
2) 더 나쁜 건 drain-bias입니다. 창을 닫을 때 heavy-tail 세션(= idle이 많은 = MORI가 유리한
   세션)이 통째로 버려집니다. 즉 MORI에 불리한 방향으로 데이터가 편향됩니다.
논문 방식(고정 시간창)으로 바꾸면 둘 다 해결되고, 덤으로 TTFT 집계도 새 드라이버에
넣습니다(기존 드라이버는 turn별 ttft를 기록만 하고 집계하지 않았습니다).
대신 무한 순환 제너레이터가 같은 trace를 반복하면서 prefix cache를 인위적으로 warm하게
만들 수 있어서, 사이클마다 셔플 + 고유 세션 커버리지 + hit rate 단조증가 여부를 게이트에
추가했습니다.

[구현상 최대 리스크]
동시성입니다. 기존 코드는 pause_resume_lock으로 global_waiting_queue 접근만 보호하고
_pause_until_safe는 lock 밖에서 돕니다. CPU tier가 들어오면 GPU/CPU/Waiting 3자 간 이동이
생기므로 _scheduled_check 전체를 하나의 mori_lock 안에서 돌리도록 넓혀야 합니다.
데이터 플레인은 tier 조회만 lock-free로 두고, 실제 이동은 스케줄러 tick에서만 일어나게
제한합니다. 이건 논문의 "periodic control loop"와도 일치하는 구조입니다.

[오늘 기준 정직한 현황]
완료된 것은 M0(브랜치 생성)뿐입니다. GPU는 한 번도 점유하지 않았습니다.
계획서 두 편, 코드 매핑, 환경 실측, trace 특성 실측이 지금까지의 산출물입니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S21 — 개념 부록
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "부록 — 용어 정리",
      "이 발표에 나온 개념을 한 줄씩. 자세한 비유는 노트에.")

table(s, [
    ["용어", "한 줄 설명"],
    ["모델 (8B)",
     "파라미터(가중치)가 N개인 신경망. 8B = 80억 개. 크면 가중치 메모리가 커져 KV 여유가 줄고, 토큰당 계산도 늘어 느려진다"],
    ["KV cache",
     "이미 읽은 토큰의 중간 계산 결과 저장소. 다음 토큰을 만들 때마다 앞을 다시 계산하지 않게 해준다. 컨텍스트 길이에 비례해 커진다 (8B: 144 KiB/토큰) [계산]"],
    ["TP (tensor parallel)",
     "모델 한 층을 여러 GPU에 쪼개 동시에 계산. TP2 = GPU 2장이 한 모델을 나눠 든다 → 우리 합산 HBM 63.7 GiB [실측]"],
    ["idleness ι / duty d",
     "ι = 전체 시간 중 툴이 도는(= GPU를 안 쓰는) 비중. d = 1 - ι = 추론하는 비중. MORI는 ι가 큰 프로그램부터 GPU에서 내린다"],
    ["busy / idle phase",
     "짧은 툴콜이 연달아 오는 구간이 busy, 긴 툴콜 하나로 오래 비는 구간이 idle. 한 프로그램이 둘 사이를 번갈아 간다"],
    ["fit",
     "KV 풀이 동시 실행 프로그램들의 작업집합을 몇 배 담을 수 있는가. fit≈4 = 압박 있음, fit≈17 = 압박 없음 (nutella가 그랬다)"],
    ["L (컨텍스트 예산)",
     "한 프로그램에 허용하는 최대 컨텍스트 토큰 수. 줄이면 프로그램당 KV가 줄어 압박이 완화된다. 우리의 레짐 조정 레버 [결정]"],
    ["오프로딩 / 재로드 vs 재계산",
     "GPU에 안 들어가는 KV를 CPU DRAM에 내려두는 것. 다시 쓸 때 PCIe로 올리면 재로드, 버렸으면 처음부터 재계산(full prefill)"],
    ["tier (GPU / CPU / Waiting)",
     "GPU = 지금 추론 가능. CPU = KV는 살아있지만 GPU엔 없음. Waiting = KV가 폐기됨. TA는 CPU가 없어 GPU↔Waiting뿐"],
], 0.5, 1.75, 12.4, 4.9, fs=10, hdr_fs=11,
    col_widths=[2.3, 10.1], left_cols=2)
footer(s, 21)
notes(s, """[비유 모음 — 질문이 나오면 쓰세요]

모델 크기: 요리사의 경력이라고 생각하면 됩니다. 경력이 많을수록(파라미터가 많을수록)
결과가 좋지만, 주방(HBM)에서 차지하는 자리도 크고 한 접시 만드는 데도 오래 걸립니다.
8B 가중치는 bf16으로 약 15.3 GiB를 먹습니다. 63.7 GiB 중 15.3을 가중치가 먼저 가져가고,
남은 자리를 KV cache가 씁니다.

KV cache: 책을 읽으면서 만드는 요약 노트입니다. 다음 페이지를 읽을 때 앞을 다시 안 읽어도
되게 해줍니다. 노트는 읽은 분량에 비례해 두꺼워집니다. 우리 8B에서는 토큰 하나당 144 KiB라,
6만 토큰짜리 대화면 노트만 8.6 GiB입니다. 프로그램 20개면 172 GiB — 63.7 GiB 안에
절대 안 들어갑니다. 이게 문제의 출발점입니다.

TP: 큰 요리를 두 주방에서 나눠 하는 것입니다. 각자 절반씩 만들고 매 단계 결과를 합칩니다.
합치는 통신이 필요한데, 우리 GPU 2장 사이에는 NVLink가 없고 cross-NUMA라 이 통신이
느립니다. 실측된 사실이라 마이크로벤치에 numactl 바인딩 실험을 넣었습니다.

idleness: 도서관 열람석과 같습니다. 자리에 앉아 책을 보는 시간이 d, 자리에 짐만 두고
나가 있는 시간이 ι입니다. 자리가 부족하면 오래 나가 있을 사람부터 짐을 빼야 합니다.
TA는 "짐이 많은 사람"부터 뺐고, MORI는 "오래 안 돌아올 사람"부터 뺍니다.

Waiting과 CPU tier의 차이: 짐을 통째로 버리는 것(Waiting, 돌아오면 처음부터 다시)과
사물함에 옮겨두는 것(CPU, 돌아오면 꺼내오기만)의 차이입니다. 사물함에서 꺼내오는 게
처음부터 다시 하는 것보다 싸면 이득입니다. 그 손익분기점을 마이크로벤치로 잽니다.

fit: 주차장 크기 대 차 대수입니다. fit=17이면 자리가 17배 남아돌아 주차 관리인이 필요
없습니다. fit=4면 관리가 성능을 가릅니다. nutella(191 GiB)에서는 fit이 17이라 MORI가
할 일이 없어서 인위로 줄여야 했고, goguma6(63.7 GiB)에서는 native로 4.2입니다.

L: 한 사람이 가져올 수 있는 짐의 상한입니다. 상한을 낮추면 같은 주차장에 더 많은 사람이
들어옵니다. 우리는 GPU를 키울 수 없으니 이 레버를 씁니다.""")


# ══════════════════════════════════════════════════════════════════════════
# S22 — 출처 · 검증 상태 · 한계
# ══════════════════════════════════════════════════════════════════════════
s = blank()
title(s, "출처 · 검증 상태 · 한계",
      "지금 시점에 무엇이 검증됐고 무엇이 안 됐는지를 명시한다.")

table(s, [
    ["태그", "의미", "이 발표에서의 예"],
    ["[논문]", "MORI.pdf 원문 직접 대조 완료 (2026-07-30 PDF 확보 후 전수 대조)",
     "Fig.3 P50~P99.95 · Fig.5 532프로그램/3임계 · Table 1 4행 · Table 2 · §6.2 전 수치"],
    ["[§C-4] 등", "계획서 goguma6판 해당 절의 실측표 (절 번호를 셀마다 병기)",
     "per-call 분포·CAP sweep·human-wait gap·ι 층화(§C-4), 서브에이전트·human 조사(§C-3)"],
    ["[실측]", "본 서버(goguma6)에서 직접 측정",
     "GPU 32,607 MiB x2, DRAM 188/185 GiB, SGLang 스모크 PASS(§A-2b)"],
    ["[계산]", "실측값으로부터의 산술 유도", "TP2 63.68 GiB, B_tok 144 KiB/tok, fit 4.2"],
    ["[결정]", "설계·승인 결정값", "L=64k, C_gpu 36 GiB 핀, CAP_HARD 300 s, 20분창 x3"],
    ["TBD", "확인 불가. 추정치로 채우지 않음", "논문 trace의 전이 per 세션 / 세션 ι (논문에 해당 수치 없음)"],
], 0.5, 1.72, 12.4, 2.5, fs=9.5, hdr_fs=10,
    col_widths=[1.15, 4.5, 6.75], left_cols=3, hl_rows={1: GREENBG})

text(s, "알려진 한계 (계획서 5절)", 0.5, 4.36, 6.0, 0.35, size=14,
     bold=True, color=RED)
bullets(s, [
    ("논문 Fig.3 분포 gap이 구조적 — short 콜이 빈약해 long-share 99.7% vs 58% [§5-(12)]", 0, RED, True),
    ("primary는 구성된(constructed) subset — 자연 도착분포 아님, blend 비율 병기 [§5-(13)]", 0, RED, True),
    ("DP=1 → 멀티레플리카 affinity·churn은 재현 범위 밖", 0, INK, False),
    ("L=64k의 전이 보존은 아직 가설 — G1에서 실측 판정", 0, INK, False),
    ("Phase 1 재로드 비용은 모델이지 실측이 아님 → Phase 2와 대조 필수", 0, INK, False),
    ("엔진 prefix cache 때문에 참 recompute가 과소 측정될 수 있음 (local_compute로 교차검증)", 0, INK, False),
    ("shared_tokens dead code → 4종 모두 prefix 공유 미반영 (비교는 공정, 절대 용량은 과대 계상)", 0, INK, False),
    ("서브에이전트는 session=program 1:1 (독립 분리 불가) [§5-(11)]", 0, INK, False),
    ("TP2가 NVLink 없는 SYS·cross-NUMA → 절대 throughput 하향, 상대 비교는 보존 [§5-(14)]", 0, INK, False),
], 0.5, 4.76, 12.4, 2.0, size=11, gap=2)

panel(s, 0.5, 6.85, 12.35, 0.5, GREENBG)
text(s, "해소됨: MORI.pdf 확보 → 논문 수치 전수 대조 완료 · SGLang sm_120 스모크 PASS(§A-2b) · human-wait 실데이터 복원 확인(§C-3 OQ-G)",
     0.72, 6.93, 11.9, 0.35, size=11.5, bold=True, color=GREEN)
footer(s, 22)
notes(s, """[이 슬라이드를 마지막에 두는 이유]
결과가 없는 발표에서 신뢰를 얻는 방법은 "무엇을 모르는지"를 정확히 말하는 것입니다.
질문 시간에 이 슬라이드를 띄워두면 좋습니다.

[이전 판에서 해소된 것 세 가지 — 먼저 말씀드립니다]
1) 논문 PDF 확보. 직전 발표 준비 시점에는 MORI.pdf가 서버에 없어 논문 수치를
   "계획서에 인용이 남은 것"과 "그렇지 않은 것"으로 나눠 표기했습니다. 이제 PDF를
   확보해 Fig.3 / Fig.5 / Table 1 / Table 2 / 6.2절을 전수 대조했고, 미검증이던 29건이
   전부 원문과 일치함을 확인했습니다. 태그를 [논문]으로 통일했습니다.
2) SGLang sm_120. 스모크 PASS(§A-2b). 비호환이 아니라 JIT 툴체인 문제였습니다.
3) human-wait. timing_events가 실제 wall-clock을 담는 것이 확인돼(OQ-G), 모델링이 아닌
   실데이터 복원으로 primary에 채택했습니다(§C-3).

[한계 목록에서 가장 아픈 것 두 개 — 둘 다 데이터입니다]
1) 논문 Fig.3 분포 gap이 구조적입니다(§5-(12)). short 콜이 너무 짧아 long-share가
   99.7%로 논문 58%를 크게 초과하고, CAP로는 좁혀지지 않습니다. S14~S18에서 다룬
   그대로, 세션 blend로 최근접시키되 잔여 gap을 정량 명기하는 것이 목표입니다.
2) 그 결과 primary가 constructed subset이 됩니다(§5-(13)). 자연 도착분포가 아니므로
   blend 비율·원본 분포·소스 세션 분포를 반드시 병기합니다.
이 둘에 대한 방어는 저-ι stratum 비교와 음성 대조군(ec40k, swebench)입니다.
매칭된 aggregate에서만 이득이 나오면 의심스럽지만, 저-ι stratum에서도 나오고
음성 대조군에서 사라지면 idleness 구조가 원인이라는 논거가 섭니다.

[정직 원칙 하나 더]
SGLang이 만약 실패했더라도 조용히 vLLM으로 되돌리지 않고 리포트하고 멈추기로
결정했었습니다. 결과적으로 통과했지만, 이 원칙 자체는 유지합니다.

[지도교수 예상 질문과 답]
Q. 결과가 언제 나오나?
A. M4(Phase 1 스윕)에서 첫 성능 수치가 나옵니다. 그 전에 G1(데이터 게이트)과
   G3(격리 게이트)를 통과해야 하고, GPU 사용은 M-SGL 스모크부터라 별도 승인이 필요합니다.
Q. 논문과 하드웨어가 다른데 재현이라 할 수 있나?
A. 절대 수치는 비교 불가하고 시스템 간 상대 비교만 유효합니다. 다만 우리가 논문과 같은
   압박 레짐(fit≈4)에 있어서 그림의 모양은 재현되어야 한다고 봅니다. 예측을 S12에
   미리 박아뒀습니다.
Q. 왜 아직 코드를 안 짰나?
A. 데이터 게이트(G1)를 먼저 통과시키려 합니다. 전이가 붕괴된 데이터로 스케줄러를 평가하면
   결과가 무의미해집니다. 데이터가 준비되면 Phase 1 구현은 엔진과 무관하게 바로 착수합니다.
Q. 데이터를 논문에 맞춰 고른 것 아닌가?
A. 맞습니다. 그래서 blend 비율과 원본 분포를 결과와 함께 공개하고, constructed subset임을
   명시합니다(§5-(13)). 다만 우리가 한 조작은 tail 클램프와 세션 선택 두 가지뿐이고,
   short 콜 길이 합성은 하드 제약으로 금지했습니다(§C-4-(3)). 그리고 매칭 안 된
   저-ι stratum과 음성 대조군을 함께 보고해 결론이 매칭에만 의존하지 않게 했습니다.""")


prs.save(OUT)
print(f"saved: {OUT}")
print(f"slides: {len(prs.slides.__iter__.__self__._sldIdLst)}")
