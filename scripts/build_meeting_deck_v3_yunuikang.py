#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the meeting deck (v3 — 실험 C·SWE 모두 완료): 현상 관찰 → R 모델(상관+인과).
작업 4(실험 C)·작업 6(SWE)이 모두 완료되어 결과·인과 슬라이드를 반영한 최종본.
Output: slides/2026-07-07_meeting_deep-analysis_yunuikang.pptx (canonical)

Figures: legacy deck figs (fig_sched/fig_Rtimeline/... — 이전 분석 산출물)와
실험 C 결과 그림(figures/expC_*.png → fig_expC_R1/cross/knob)을 한 폴더(FIGS)에 모아 사용.
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from PIL import Image

FIGS = "/tmp/claude-20060/-home-yunuikang-yunuikang-work-distserving/c27e6b57-66d8-42b6-8b8e-2a3c2fb86e8b/scratchpad/deck_figs"
OUT  = "/home/yunuikang/yunuikang_work/distserving/slides/2026-07-07_meeting_deep-analysis_yunuikang.pptx"
os.makedirs(os.path.dirname(OUT), exist_ok=True)

# palette
INK   = RGBColor(0x1f, 0x24, 0x30)
BLUE  = RGBColor(0x27, 0x46, 0x90)
AMBER = RGBColor(0xE0, 0x8A, 0x1E)
GREEN = RGBColor(0x2E, 0x7D, 0x46)
RED   = RGBColor(0xC0, 0x39, 0x2B)
GRAY  = RGBColor(0x6B, 0x72, 0x80)
LGRAY = RGBColor(0xEC, 0xEE, 0xF2)
PANEL = RGBColor(0xF4, 0xF6, 0xFB)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT  = "Malgun Gothic"   # viewer-side Korean font; falls back gracefully

prs = Presentation()
prs.slide_width  = Inches(13.333)
prs.slide_height = Inches(7.5)
SW, SH = prs.slide_width, prs.slide_height
BLANK = prs.slide_layouts[6]

def slide():
    return prs.slides.add_slide(BLANK)

def _set_font(run, size, color, bold=False, italic=False, name=FONT):
    run.font.size = Pt(size); run.font.color.rgb = color
    run.font.bold = bold; run.font.italic = italic; run.font.name = name

def textbox(s, l, t, w, h, lines, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    """lines: list of (text, size, color, bold) or list of such for multi-run paragraphs."""
    tb = s.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = tb.text_frame; tf.word_wrap = True; tf.vertical_anchor = anchor
    tf.margin_left = Pt(4); tf.margin_right = Pt(4); tf.margin_top = Pt(2); tf.margin_bottom = Pt(2)
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        runs = ln if isinstance(ln, list) else [ln]
        for (txt, sz, col, bold) in runs:
            r = p.add_run(); r.text = txt; _set_font(r, sz, col, bold)
        p.space_after = Pt(3); p.space_before = Pt(0)
    return tb

def rect(s, l, t, w, h, fill, line=None, lw=1.0):
    sp = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(l), Inches(t), Inches(w), Inches(h))
    sp.fill.solid(); sp.fill.fore_color.rgb = fill
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = line; sp.line.width = Pt(lw)
    sp.shadow.inherit = False
    return sp

def title(s, tag, tag_color, head, sub=None):
    # tag chip
    if tag:
        chip = rect(s, 0.55, 0.42, 0.14, 0.62, tag_color)
    textbox(s, 0.78, 0.36, 11.0, 0.9,
            [[(head, 25, INK, True)]], anchor=MSO_ANCHOR.MIDDLE)
    if tag:
        textbox(s, 0.78, 1.02, 11.8, 0.34, [[(tag, 12.5, tag_color, True)]])
    # accent rule
    rect(s, 0.78, 1.38 if sub is None else 1.40, 11.9, 0.02, tag_color)

def add_image(s, name, top, width=None, center=True, left=None):
    path = os.path.join(FIGS, name)
    iw, ih = Image.open(path).size
    if width is None: width = 11.7
    w = Inches(width); h = Emu(int(w * ih / iw))
    if left is None:
        left = (SW - w) / 2 if center else Inches(0.8)
    else:
        left = Inches(left)
    s.shapes.add_picture(path, left, Inches(top), width=w, height=h)
    return Inches(top) + h

def notes(s, text):
    s.notes_slide.notes_text_frame.text = text

def table(s, data, l, t, w, col_w, header_fill=BLUE, header_col=WHITE,
          fs=12, hfs=12, row_h=0.42, zebra=True, cell_colors=None):
    rows, cols = len(data), len(data[0])
    gt = s.shapes.add_table(rows, cols, Inches(l), Inches(t), Inches(w), Inches(row_h*rows)).table
    gt.first_row = False; gt.horz_banding = False
    for ci, cw in enumerate(col_w):
        gt.columns[ci].width = Inches(cw)
    for ri in range(rows):
        gt.rows[ri].height = Inches(row_h)
        for ci in range(cols):
            cell = gt.cell(ri, ci)
            cell.margin_left = Pt(6); cell.margin_right = Pt(6)
            cell.margin_top = Pt(2); cell.margin_bottom = Pt(2)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            if ri == 0:
                cell.fill.solid(); cell.fill.fore_color.rgb = header_fill
            elif cell_colors and cell_colors.get((ri, ci)):
                cell.fill.solid(); cell.fill.fore_color.rgb = cell_colors[(ri, ci)]
            elif zebra and ri % 2 == 0:
                cell.fill.solid(); cell.fill.fore_color.rgb = PANEL
            else:
                cell.fill.solid(); cell.fill.fore_color.rgb = WHITE
            txt, col, bold = data[ri][ci]
            tf = cell.text_frame; tf.word_wrap = True
            p = tf.paragraphs[0]; p.alignment = PP_ALIGN.LEFT
            r = p.add_run(); r.text = txt
            _set_font(r, hfs if ri == 0 else fs, header_col if ri == 0 else col, bold or ri == 0)
    return gt

def C(txt, col=INK, bold=False):  # cell helper
    return (txt, col, bold)

# ===========================================================================
# SLIDE 1 — Title
# ===========================================================================
s = slide()
rect(s, 0, 0, 13.333, 7.5, WHITE)
rect(s, 0, 2.55, 13.333, 0.06, AMBER)
textbox(s, 0.9, 1.15, 11.5, 1.5,
        [[("피드백 대응", 34, BLUE, True)],
         [("'현상 관찰'에서 '알고리즘 기반 인과 모델'로", 27, INK, True)]])
textbox(s, 0.9, 2.8, 11.5, 1.6,
        [[("cost model 정리  →  eviction·지표 재정렬  →  ", 15, GRAY, False),
          ("R 모델(인과)", 15, AMBER, True),
          ("  →  SWE 2차 검증", 15, GRAY, False)],
         [("ThunderAgent 이종(heterogeneous) GPU 서빙 심화 분석", 14, GRAY, False)]])
textbox(s, 0.9, 6.5, 11.5, 0.5,
        [[("강윤의  ·  브랜치 yunuikang/thunderagent  ·  2026-07-07", 13, GRAY, False)]])
notes(s,
"안녕하세요, 강윤의입니다. 지난 미팅에서 교수님께서 결과를 현상으로만 보지 말고, 먼저 알고리즘을 정확히 "
"이해해서 그 로직으로 원인을 설명하라고 하셨습니다. 오늘은 그 피드백에 대응한 여섯 가지 작업을 보고드립니다. "
"핵심은, 흩어져 있던 관찰들을 'R 모델'이라는 하나의 인과 모델로 묶었다는 것입니다. R 모델은 뒤에서 자세히 "
"설명드립니다. 완료한 작업 네 개는 결과 분석까지, 아직 돌리고 있는 실험 두 개는 지금까지의 부분 결과와 "
"어떻게 돌리고 있는지를 정직하게 말씀드리겠습니다.")

# ===========================================================================
# SLIDE 2 — Feedback -> Work map
# ===========================================================================
s = slide()
title(s, "전체 대응 맵", BLUE, "교수님 피드백을 작업 1~6에 매핑")
data = [
 [C("교수님 요구", WHITE, True), C("대응 작업", WHITE, True), C("무엇을 했나", WHITE, True), C("상태", WHITE, True)],
 [C("(a) 알고리즘(cost model·policy)\n먼저 정확히 이해"), C("작업 1  메커니즘 정리", BLUE, True),
  C("논문 STP 5항 ↔ 코드 용량 부등식(Eq.6) 1:1 매핑"), C("✅ 완료", GREEN, True)],
 [C("(e) KV 초과 시 처리\n(CPU swap 하나?)"), C("작업 2  eviction 규명", BLUE, True),
  C("vLLM V1은 swap 안 씀 → '재프리필' 해석이 코드상 참"), C("✅ 완료", GREEN, True)],
 [C("(b)(c) 재프리필 정의·\n용량을 메모리 지표로"), C("작업 3  지표 재정렬", BLUE, True),
  C("재프리필=미스율(1−hit), 용량=kv_usage로 교체"), C("✅ 완료", GREEN, True)],
 [C("(f) SWE 워크로드로 검증"), C("작업 5  characterization", BLUE, True),
  C("SWE=decode-heavy(d≈1) — TraceLab의 반대극"), C("✅ 완료", GREEN, True)],
 [C("(d) tr 승패 원인을\n가설 아닌 수치로 증명"), C("작업 4  실험 C", GREEN, True),
  C("R 모델 상관(r=0.959)+인과(R=1 역전) 모두 확정"), C("✅ 완료", GREEN, True)],
 [C("(f) SWE에서 결론 재현"), C("작업 6  SWE 스윕", GREEN, True),
  C("2×4090 스윕 완료 → tr 승 확정(+78~84%), R 예측 적중"), C("✅ 완료·적중", GREEN, True)],
]
table(s, data, 0.78, 1.75, 11.9, [2.7, 2.6, 4.9, 1.7], fs=12.5, hfs=12.5, row_h=0.72)
textbox(s, 0.78, 6.98, 11.9, 0.4,
        [[("관통 주제 — 여섯 작업이 모두 하나의 ", 12.5, INK, False),
          ("R 모델(인과)", 12.5, AMBER, True),
          ("로 수렴.  여섯 작업 전부 완료 — 진행 중 없음.", 12.5, GREEN, True)]])
notes(s,
"이 표가 오늘 발표의 지도입니다. 왼쪽이 교수님이 주신 요구, 가운데가 그에 대응한 작업, 오른쪽이 상태입니다. "
"(a) 알고리즘을 먼저 이해하라는 요구에는 작업 1에서 논문의 비용 모델과 실제 코드를 한 줄씩 대응시켰습니다. "
"(e) KV가 넘칠 때 CPU로 옮기느냐는 질문에는 작업 2에서 '아니다, 다시 계산한다'를 코드로 확인했습니다. "
"(b)(c) 지표가 잘못됐다는 지적에는 작업 3에서 올바른 지표로 바꿨습니다. (f) SWE 워크로드는 작업 5에서 특성 "
"분석을 끝냈습니다. (f) SWE 재현인 작업 6은 스윕이 끝나 tr이 세 지표 모두에서 이겨 R 예측이 적중했습니다. "
"그리고 오늘의 핵심인 (d), 원인을 수치로 증명하라는 작업 4 실험 C도 완료됐습니다. R 모델이 GPU 활용률을 "
"상관계수 0.96으로 예측했고, 게다가 R을 일부러 1 위로 밀었더니 tr이 예측대로 역전돼서 '상관'을 넘어 '인과'까지 "
"확정했습니다. 즉 여섯 작업이 전부 끝났고, 모두 'R 모델' 하나로 이어진다는 점이 오늘의 메시지입니다.")

# ===========================================================================
# SLIDE 3 — [작업1] Mechanism
# ===========================================================================
s = slide()
title(s, "작업 1 · 완료", BLUE, "ThunderAgent 메커니즘: cost model = 용량 부등식")
add_image(s, "fig_sched.png", 1.62, width=11.3)
textbox(s, 0.9, 6.95, 11.9, 0.5,
        [[("★ 신규 배정이 '용량 비례'가 아니라 '절대 토큰 균형' → 용량 2배인 5090을 2배 활용하지 못하는 근원.",
           12.5, AMBER, True)]])
notes(s,
"작업 1은 알고리즘을 코드 수준까지 정확히 이해한 것입니다. ThunderAgent의 스케줄러는 논문의 복잡한 비용식을 "
"직접 풀지 않고, '백엔드에 올라간 KV 합이 GPU 용량을 넘으면 안 된다'는 하나의 용량 부등식으로 근사합니다. "
"이걸 5초마다 검사해서 세 가지 행동으로 유지합니다. 넘칠 것 같으면 가장 작은 프로그램을 빼고(pause), 여유가 "
"생기면 다시 넣고(resume), 새 프로그램은 가장 덜 찬 백엔드에 배정합니다. 여기서 제가 찾은 핵심은 오른쪽 "
"박스입니다. 새 프로그램을 배정할 때 '토큰 절대량'만 보고 백엔드 용량으로 나누지 않습니다. 그래서 용량이 두 "
"배인 5090에도 두 배로 보내지 않고, 5090이 놀게 됩니다. 이게 나중에 나올 5090 과소활용 문제의 코드적 뿌리입니다.")

# ===========================================================================
# SLIDE 4 — [작업2] eviction
# ===========================================================================
s = slide()
title(s, "작업 2 · 완료", BLUE, "eviction = 재프리필 확정 (CPU swap 아님)")
add_image(s, "fig_evict.png", 1.65, width=11.3)
notes(s,
"작업 2는 교수님의 (e) 질문, 'KV 캐시가 GPU 메모리를 넘치면 CPU로 옮겨두느냐'에 답한 것입니다. 결론은 "
"'아니다'입니다. 우리가 쓰는 vLLM V1 엔진은 CPU로 내렸다 올리는 swap 기능 자체를 없앴고, 대신 필요하면 "
"다시 계산하는 방식만 씁니다. 코드에 swap 설정이 하나도 없고, 엔진 설정에 swap 항목 자체가 없으며, 실제 "
"실행에서도 강제 축출은 거의 0이었습니다. default 모드는 새 요청이 다른 프로그램의 캐시를 밀어내서 다음 "
"턴에 처음부터 다시 계산하고, tr 모드는 미리 프로그램을 빼서 그 손실을 막습니다. 즉 우리가 그동안 쓴 "
"'재프리필'이라는 표현이 코드상 정확했다는 걸 확인했고, 논문의 swap 지연 이야기는 우리 환경엔 해당되지 않습니다.")

# ===========================================================================
# SLIDE 5 — [작업3] metric realignment
# ===========================================================================
s = slide()
title(s, "작업 3 · 완료", BLUE, "지표 재정렬: 재프리필=미스율, 용량=실제 메모리")
add_image(s, "fig_metrics.png", 1.7, width=11.4)
textbox(s, 0.9, 6.95, 11.9, 0.5,
        [[("메모리 사용률(kv_usage)은 tr·default 둘 다 ~1.0 포화 → 단독으론 무의미. hit·pause·resident와 함께 봐야.",
           12, GRAY, False)]])
notes(s,
"작업 3은 (b)(c), 지표가 잘못됐다는 지적을 바로잡은 것입니다. 왼쪽 그림처럼 예전에 재프리필 지표로 쓰던 "
"prompt_tokens_total은 부하를 아무리 올려도 값이 거의 평평합니다. 스래싱이 일어나는데도 안 보이니 잘못된 "
"지표였습니다. 오른쪽처럼 캐시 미스율, 즉 1에서 캐시 적중률을 뺀 값으로 봐야 재계산 압력이 제대로 보입니다. "
"default는 부하가 커지자 미스율이 0.18에서 0.97까지 폭발하고, tr은 0.2 근처로 평평하게 눌러 줍니다. "
"용량도 프리필이 아니라 실제 메모리 지표로 봤는데, 흥미롭게도 메모리 사용률은 tr이든 default든 거의 꽉 차서 "
"그것만으론 둘을 구분 못 합니다. 그래서 사용률에 더해 적중률·pause·동시 실행 수를 함께 봐야 한다는 결론입니다.")

# ===========================================================================
# SLIDE 6 — ★ R model (hero)
# ===========================================================================
s = slide()
title(s, "★ 핵심 발견", AMBER, "R 모델 — GPU 활용률과 승패를 결정하는 한 식")
add_image(s, "fig_Rtimeline.png", 1.55, width=11.7)
notes(s,
"이 슬라이드가 오늘의 핵심입니다. tr의 성능은 R이라는 하나의 숫자로 예측됩니다. R은 두 값의 곱입니다. "
"duty_cycle, 즉 d는 프로그램이 실제로 GPU 연산에 쓰는 시간 비율입니다. 토큰을 생성하는 시간이 reasoning, "
"도구를 실행하거나 노는 시간이 tool인데, 그 비율입니다. k_fit은 tr이 GPU에 동시에 올려두는 평균 프로그램 "
"수입니다. 직관은 이렇습니다. 올라간 프로그램 하나하나는 자기 시간의 d만큼만 GPU를 쓰고 나머지는 도구 "
"실행하느라 GPU를 비웁니다. 그래서 k_fit개가 GPU를 채우는 비율이 대략 k_fit 곱하기 d입니다. 위쪽 합성 "
"워크로드는 이 곱이 1.7이라 GPU가 꽉 차서 tr이 이깁니다. 아래쪽 실데이터는 0.37이라, GPU에 구멍, 즉 "
"버블이 생겨서 활용률이 딱 그만큼 떨어지고 tr이 집니다. 실제로 측정한 활용률도 36%로 이 예측과 일치했습니다. "
"즉 tr이 지는 이유가 '나쁜 스케줄러'가 아니라 '워크로드의 duty가 낮아 GPU에 구멍이 생기기 때문'임을 보여줍니다.")

# ===========================================================================
# SLIDE 7 — [작업5] SWE characterization
# ===========================================================================
s = slide()
title(s, "작업 5 · 완료", BLUE, "SWE characterization: SWE는 decode-heavy (d≈1)")
add_image(s, "fig_3way.png", 1.6, width=11.4)
textbox(s, 0.9, 6.55, 11.9, 0.7,
        [[("SWE=decode-heavy(d=0.995), TraceLab=prefill-heavy(d=0.18), 합성=balanced(d=0.56) → 세 워크로드가 서로 다른 축을 자극.",
           12, INK, False)],
         [("한계(정직): step_limit=40에서 clip rate 20.3% — 프로그램 lifetime 상단 꼬리만 절단(per-turn 특성엔 무영향).",
           11.5, RED, False)]])
notes(s,
"작업 5는 (f), SWE 워크로드로 결론을 검증하기 위한 특성 분석입니다. SWE 에이전트는 코드를 고치는 작업이라 "
"토큰을 아주 많이 생성합니다. 턴당 출력이 834토큰으로 TraceLab의 여섯 배고, duty_cycle이 0.995로 거의 1입니다. "
"즉 벽시계 시간의 99.5%를 GPU 연산에 씁니다. TraceLab은 반대로 입력이 크고 생성이 적은 prefill 중심, d가 "
"0.18이고, 합성은 그 중간입니다. 이렇게 세 워크로드가 서로 다른 축을 자극하니 결론의 일반성을 확인하기에 "
"이상적입니다. 정직하게 한계도 말씀드리면, 녹화할 때 턴 수를 40으로 제한해서 20.3%의 어려운 태스크가 40턴에서 "
"잘렸습니다. 다만 이건 프로그램이 몇 턴을 사는지 분포 상단만 자르는 것이고, 턴 하나하나의 토큰·시간 특성은 "
"온전히 기록돼서 R 모델 입력값에는 영향이 없습니다.")

# ===========================================================================
# SLIDE 8 — SWE data composition: stratified sampling + per-repo distribution
# ===========================================================================
s = slide()
title(s, "작업 5 · 완료 (심화)", BLUE, "SWE 데이터 구성 — 계층적 샘플링 + 레포별 분포")
add_image(s, "fig_swe_sampling.png", 1.5, width=11.5)
textbox(s, 0.78, 6.72, 11.9, 0.7,
        [[("방법: 원본 300개(12 레포, django 38%·sympy 26% 편중) → 레포별 비례배분(largest-remainder) + 레포당 최소 1개 + 시드고정 랜덤 → 64개(21.3%).",
           11.5, INK, False)],
         [("head-64는 알파벳 정렬로 astropy+django만 뽑혀 폐기.  세션 길이 10~40턴으로 다양하나 전 레포 output 560~1700 tok = 모두 decode-heavy.",
           11.5, GRAY, False)]])
notes(s,
"교수님이 물으신 'SWE 데이터를 어떻게 구성했나'에 대한 자세한 답입니다. SWE-bench Lite 전체는 태스크 300개이고, "
"이게 12개 오픈소스 레포에서 나오는데 분포가 심하게 치우쳐 django 혼자 38%, sympy가 26%를 차지합니다. 시간 "
"때문에 64개만 녹화하는데, 그냥 앞에서 64개를 자르면 데이터셋이 알파벳 순이라 astropy와 django만 뽑히고 10개 "
"레포가 빠집니다. 그래서 레포별 비례 배분을 썼습니다. 왼쪽 그림처럼 원본에서 각 레포가 차지하는 비율을 그대로 "
"유지하도록 64개를 나눠 뽑되, 아무리 작은 레포도 최소 1개는 보장하고, 레포 안에서는 시드를 고정한 랜덤으로 "
"골랐습니다. 그래서 회색(원본)과 주황(표본) 막대가 거의 겹칩니다. 최소 1개 보장 때문에 django가 38에서 32.8로 "
"조금 내려가지만 전체 분포 오차는 14.7%포인트로 양호합니다. 오른쪽은 레포별 특성인데, 세션 길이는 requests "
"10턴부터 flask 40턴까지 다양하지만, 어느 레포든 턴당 출력 토큰이 560에서 1700으로 커서 전부 decode-heavy라는 "
"게 일관됩니다. 즉 특정 레포에 쏠려서 decode-heavy로 보이는 게 아니라, SWE 도메인 전반의 성질입니다.")

# ===========================================================================
# SLIDE 9 — SWE per-time breakout (wall-time composition + turn-index evolution)
# ===========================================================================
s = slide()
title(s, "작업 5 · 완료 (심화)", BLUE, "SWE per-time breakout — 시간 분해 + turn별 진화")
add_image(s, "fig_swe_pertime.png", 1.5, width=11.6)
textbox(s, 0.78, 6.72, 11.9, 0.7,
        [[("핵심: wall-time의 99.5%가 GPU 연산(reasoning), tool은 0.5%뿐 → ", 11.5, INK, False),
          ("d=0.995 → R≫1", 11.5, AMBER, True),
          (".  세션이 길어져도 tool은 계속 무시가능 → d≈1 전 구간 유지.", 11.5, INK, False)],
         [("정직: 이 녹화는 1×4090+12워커라 prefill 절대시간은 경합으로 부풀려짐(prefill_s~prompt corr 0.19); 견고한 사실은 tool 0.5%와 decode∝output(0.97).",
           11, GRAY, False)]])
notes(s,
"교수님이 요청하신 SWE의 시간 분해, per-time breakout입니다. 왼쪽은 녹화한 64세션 1388턴의 벽시계 시간을 "
"무엇에 썼는지 나눈 것입니다. 핵심은 tool 실행에 쓴 시간이 전체의 0.5%밖에 안 되고, 나머지 99.5%가 모두 GPU "
"연산(프리필과 디코드)이라는 점입니다. 이게 바로 duty_cycle이 0.995, 즉 거의 1이 되는 이유이고, 그래서 R이 "
"1보다 훨씬 커서 tr이 유리하다고 예측되는 근거입니다. 오른쪽은 세션이 진행되면서 어떻게 변하는지인데, 턴이 "
"쌓일수록 입력 토큰이 1.8천에서 1만4천까지 늘어납니다. 앞의 대화가 계속 컨텍스트로 붙기 때문입니다. 반면 "
"출력은 900 근처로 평탄하고, tool 시간은 처음부터 끝까지 0.2초 수준으로 무시할 만합니다. 즉 세션이 아무리 "
"길어져도 tool 비중이 커지지 않아 d가 1에 가깝게 유지됩니다. 마지막으로 정직하게 한 가지 짚으면, 이 녹화는 "
"4090 한 장에 워커 12개가 몰려서 프리필 절대 시간이 경합으로 부풀려져 있습니다. 프리필 시간과 프롬프트 길이의 "
"상관이 0.19로 약한 게 그 증거입니다. 그래서 프리필이 69%라는 절대 숫자는 조심해서 봐야 하고, 경합과 무관하게 "
"견고한 사실은 tool이 0.5%라는 것과 디코드 시간이 출력 토큰에 0.97로 거의 완벽히 비례한다는 두 가지입니다.")

# ===========================================================================
# SLIDE 10 — R prediction (decisive)
# ===========================================================================
s = slide()
title(s, "★ R 모델의 결정적 예측", AMBER, "같은 2×4090인데 D는 지고 SWE는 이긴다")
add_image(s, "fig_Rpredict.png", 1.5, width=8.0, center=False, left=0.55)
# side prediction table (2x2 background cross-check)
pdata = [
 [C("셀", WHITE, True), C("d", WHITE, True), C("R", WHITE, True), C("관측", WHITE, True)],
 [C("합성 2×4090"), C("0.56"), C("~1.7"), C("+57% 승", GREEN, True)],
 [C("D 실제 2×4090"), C("0.18"), C("0.37"), C("−34% 패", RED, True)],
 [C("F 4090+5090"), C("0.56"), C(">1"), C("+100% 승", GREEN, True)],
 [C("G 4090+5090"), C("0.18"), C("0.37/0.72"), C("−8% 부분", AMBER, True)],
 [C("SWE 2×4090"), C("0.995"), C("2–4"), C("★승 확정 +78~84%", GREEN, True)],
]
table(s, pdata, 8.75, 1.65, 4.25, [1.5, 0.7, 1.05, 1.0], fs=11, hfs=11, row_h=0.5,
      cell_colors={(5,0):RGBColor(0xd7,0xeb,0xdd),(5,1):RGBColor(0xd7,0xeb,0xdd),(5,2):RGBColor(0xd7,0xeb,0xdd),(5,3):RGBColor(0xd7,0xeb,0xdd)})
textbox(s, 8.75, 4.9, 4.25, 1.8,
        [[("사전 등록 예측 → 적중", 12.5, GREEN, True)],
         [("R≥1→승, R<1→패 규칙이", 11.5, INK, False)],
         [("다섯 셀 전부 적중 (SWE 확정).", 11.5, INK, True)],
         [("결과 보고 끼워맞춘 게 아니라 예측.", 11.5, GRAY, False)]])
notes(s,
"이 슬라이드가 R 모델이 왜 강한 증거인지 보여줍니다. 하드웨어는 똑같이 4090 두 장인데, 결과가 정반대입니다. "
"TraceLab을 돌린 실험 D는 d가 0.18이라 R이 0.37, 1보다 작아서 tr이 34% 졌습니다. 같은 하드웨어에서 SWE는 "
"d가 0.995라 R이 2에서 4, 1보다 훨씬 커서 tr이 이길 거라고 예측됩니다. 오른쪽 표를 보시면, 이미 확보한 네 개 "
"배경 실험이 전부 이 R 규칙과 맞습니다. 여기서 중요한 점은, 이 예측을 실험 전에 미리 계산해서 등록했다는 "
"것입니다. 결과를 보고 끼워 맞춘 게 아니라, duty_cycle이라는 워크로드 성질 하나만으로 서로 상반된 두 결과를 "
"미리 맞히는 것이라 인과 모델로서 훨씬 강한 증거입니다. 그리고 SWE 스윕이 방금 끝났는데, 예측대로 tr이 "
"78에서 84%까지 이겨서 다섯 번째 셀도 R 규칙에 그대로 들어맞았습니다. 다음 슬라이드에서 그 결과를 보시겠습니다.")

# ===========================================================================
# SLIDE 9 — [작업4] Experiment C — DESIGN (what / why / conditions)
# ===========================================================================
s = slide()
title(s, "작업 4 · 완료  —  왜: tr 승패 원인을 가설이 아니라 수치·인과로 (피드백 d)",
      GREEN, "실험 C 설계 — 무엇을 · 왜 · 어떤 조건")
add_image(s, "fig_expC_design.png", 1.48, width=8.6)
# left panel: experiment matrix
rect(s, 0.55, 5.35, 6.05, 2.0, PANEL)
textbox(s, 0.75, 5.45, 5.7, 1.9,
        [[("실험 매트릭스  (scheduler 미수정 — 관측 + CLI 노브만)", 11.5, BLUE, True)],
         [("• 4-A 기본 스윕 — tr·default × C=4·8·16·32, 3회 → d·k_fit·U 실측 [R1]", 10.3, INK, False)],
         [("• 4-B1 k_fit 축 — C=16, --decay / --weight 0.5 [R3 나쁜 회복]", 10.3, INK, False)],
         [("• 4-B2 duty 축 ★ — C=16, --tool-scale S=2·1·0.5·0.25·0.2 [R4 결정타]", 10.3, AMBER, True)],
         [("• 4-C 교차검증 — §9·F·G 대표점 U 실측 [R2 4칸 전부]", 10.3, INK, False)]])
# right panel: measurement + common conditions
rect(s, 6.75, 5.35, 6.0, 2.0, RGBColor(0xfb,0xee,0xcd))
textbox(s, 6.95, 5.45, 5.65, 1.9,
        [[("측정 3종 (동시 수집)", 11.5, BLUE, True)],
         [("① 프로파일러 — latency 분해 (prefill/decode/pause/tool)", 10.3, INK, False)],
         [("② GPU 샘플러(1초) — util·resident·idle 시계열", 10.3, INK, False)],
         [("③ 파생 — k_fit(평균 resident), d(연산 시간비), U = 1−idle", 10.3, INK, False)],
         [("공통 — 2×4090(GPU2/3) · TraceLab(D와 동일) · NPROG=64 · 3회", 10.3, GRAY, False)]])
notes(s,
"실험 C가 무엇을, 왜, 어떤 조건으로 하는지를 정리한 설계 슬라이드입니다. 왜 하냐면, 교수님의 (d) 요구대로 tr이 "
"실험 D에서 지는 원인을 가설이 아니라 수치와 인과로 증명하기 위해서입니다. 핵심 아이디어는 위 그림입니다. "
"tr의 GPU 활용률은 R이라는 숫자로 결정되는데, R이 1보다 작으면 지고 크면 이깁니다. 지금 D는 R이 0.37이라 "
"집니다. 그래서 R을 두 가지 방법으로 인위적으로 키워 1을 넘겨 봅니다. 하나는 k_fit 축인데, pause를 완화해 "
"GPU에 더 올리는 방식이라 활용률은 오르지만 캐시 적중률을 잃습니다. 나쁜 회복입니다. 다른 하나가 핵심인 "
"duty 축으로, tool-scale이라는 새 옵션으로 도구 시간을 줄여 d를 키우는데, 캐시는 그대로라 좋은 회복입니다. "
"예측상 도구 시간을 5분의 1로 줄이면, 즉 S가 0.2쯤이면 R이 정확히 1을 넘습니다. 그때 tr이 지다가 이기는 쪽으로 "
"실제로 뒤집히면, R이 1보다 작았던 게 원인이었다는 게 인과적으로 확정됩니다. 아래 왼쪽은 정확히 무엇을 어떤 "
"동시성과 노브로 돌리는지의 실험 매트릭스이고, 오른쪽은 매 실행에서 latency 분해·GPU 점유·활용률을 함께 "
"기록하는 측정 3종과 공통 조건입니다. 모든 조건은 실험 D와 똑같이 맞춰 스케줄러만 비교합니다.")

# ===========================================================================
# SLIDE — [작업4 완료·R1] Experiment C result: predicted vs measured U
# ===========================================================================
s = slide()
title(s, "작업 4 · 완료 · R1", GREEN, "실험 C 결과 [R1] — 한 식(R)이 GPU 활용률을 예측 (r = 0.959)")
add_image(s, "fig_expC_R1.png", 1.75, width=5.3, center=False, left=1.1)
rct = table(s,
 [[C("셀", WHITE, True), C("R=k_fit·d", WHITE, True), C("예측 U", WHITE, True), C("실측 U", WHITE, True)],
  [C("tr C=4"),  C("0.31"), C("0.31"), C("0.34", GREEN, True)],
  [C("tr C=16"), C("0.31"), C("0.31"), C("0.38", GREEN, True)],
  [C("default C=16"), C("1.20"), C("1.00"), C("0.87", BLUE, True)],
  [C("default C=32"), C("2.06"), C("1.00"), C("0.91", BLUE, True)]],
 7.95, 1.75, 4.9, [1.7, 1.15, 1.0, 1.05], fs=11.5, hfs=11.5, row_h=0.5)
rect(s, 7.95, 4.35, 4.9, 2.55, PANEL)
textbox(s, 8.15, 4.45, 4.5, 2.4,
        [[("한 식이 두 레짐을 모두 예측", 13, AMBER, True)],
         [("• tr = R<1 → GPU가 굶음(U≈R)", 11.5, INK, False)],
         [("• default = R>1 → 포화(U→1)", 11.5, INK, False)],
         [("• clean 13점 r=0.959, 평균오차 0.091", 11.5, GREEN, True)],
         [("", 5, INK, False)],
         [("→ 'tr이 진다'는 나쁜 스케줄러가 아니라", 11.5, INK, True)],
         [("   R<1(=GPU 63% 유휴) 때문임을 정량 확인.", 11.5, INK, True)]])
notes(s,
"실험 C가 끝났고, 첫 번째 결과가 R 모델의 예측력입니다. 가로축이 R로 계산한 예측 활용률, 세로축이 실제 측정한 "
"GPU 활용률인데, 점들이 대각선 위에 거의 그대로 올라옵니다. 상관계수가 0.96이고 평균 오차는 0.09밖에 안 됩니다. "
"중요한 건 하나의 식이 서로 다른 두 상황을 다 맞힌다는 점입니다. tr은 R이 1보다 작은 영역이라 GPU가 굶어서 "
"활용률이 R을 그대로 따라 0.3~0.4에 머뭅니다. 반대로 default는 pause를 안 해서 프로그램을 많이 올리니 R이 "
"1을 넘고, 활용률이 0.87에서 0.91로 거의 포화됩니다. 오른쪽 표를 보시면 tr C=16은 예측 0.31에 실측 0.38, "
"default C=16은 예측 상한 1.0에 실측 0.87로, 두 레짐 모두 예측선 위에 있습니다. 결론은, tr이 실험 D에서 진 게 "
"'스케줄러가 나빠서'가 아니라 'R이 0.31이라 GPU가 63% 놀았기 때문'이라는 걸 숫자로 확인한 겁니다. "
"단, 이건 아직 '상관'입니다. 다음 슬라이드에서 '인과'를 보이겠습니다.")

# ===========================================================================
# SLIDE — [작업4 완료·R4] ★ decisive: cross R=1 -> tr overtakes (correlation->causation)
# ===========================================================================
s = slide()
title(s, "작업 4 · 완료 · ★R4 결정타", AMBER, "실험 C [R4] — R을 1 위로 밀자 tr이 default를 역전 (상관 → 인과)")
add_image(s, "fig_expC_cross.png", 1.55, width=11.5)
rct = table(s,
 [[C("tool_scale S", WHITE, True), C("2.0", WHITE, True), C("1.0", WHITE, True), C("0.5", WHITE, True), C("0.25", WHITE, True), C("0.2", WHITE, True), C("0.125", WHITE, True)],
  [C("R = k_fit·d"), C("0.18"), C("0.31"), C("0.52"), C("0.75"), C("0.85"), C("1.00", AMBER, True)],
  [C("throughput"), C("0.045"), C("0.068"), C("0.099"), C("0.127"), C("0.136"), C("0.144", GREEN, True)],
  [C("KV hit"), C("0.71"), C("0.80"), C("0.83"), C("0.82"), C("0.86"), C("0.83", GREEN, True)]],
 0.55, 5.28, 8.5, [1.55, 1.15, 1.15, 1.15, 1.15, 1.1, 1.25], fs=10.5, hfs=10.5, row_h=0.42)
rect(s, 9.35, 5.28, 3.45, 1.72, RGBColor(0xfb,0xee,0xcd))
textbox(s, 9.52, 5.36, 3.15, 1.6,
        [[("R 0.18→1.0 밀자:", 12, AMBER, True)],
         [("throughput ×3.2 (0.045→0.144)", 10.8, GREEN, True)],
         [("hit는 0.83 유지", 10.8, GREEN, True)],
         [("→ default(thr 0.098, hit 0.037)를", 10.5, INK, True)],
         [("   두 지표 모두 역전.", 10.5, INK, True)]])
notes(s,
"이 슬라이드가 실험 C의 결정타이자 오늘 발표에서 가장 중요한 논리입니다. 앞에서 R과 활용률이 '상관' 있다는 걸 "
"보였는데, 상관만으로는 R이 원인이라 단정할 수 없습니다. 그래서 R을 '일부러' 움직여 봤습니다. tool-scale이라는 "
"새 옵션으로 도구 실행 시간을 줄이면 duty가 올라가 R이 커집니다. 오른쪽으로 갈수록 도구 시간을 줄인 건데, "
"R이 0.18에서 1.0까지 올라갑니다. 그러자 tr의 처리량이 0.045에서 0.144로 3.2배 뛰고, 활용률도 같이 오릅니다. "
"핵심은 두 가지입니다. 첫째, 캐시 적중률은 0.83 근처로 그대로 유지됩니다. 캐시를 건드리지 않고 순수하게 R만 "
"올렸다는 뜻입니다. 둘째, R이 1에 도달한 지점에서 tr의 처리량 0.144가 default의 0.098을 넘고, 적중률은 0.83 대 "
"0.037로 압도합니다. 즉 tr이 default를 '두 지표 모두에서' 역전합니다. 우리가 예측한 대로, R을 1 위로 넘기니 "
"승패가 뒤집힌 겁니다. 이건 단순한 상관이 아니라, 원인을 손으로 돌려서 결과가 예측대로 따라온 '인과'의 증거입니다. "
"그래서 'R이 1보다 작았던 것이 tr이 실험 D에서 진 원인'이라고 확정할 수 있습니다.")

# ===========================================================================
# SLIDE — [작업4 완료·R3] two knobs: good vs bad recovery
# ===========================================================================
s = slide()
title(s, "작업 4 · 완료 · R3", GREEN, "실험 C [R3] — R의 두 축: 좋은 회복(duty) vs 나쁜 회복(k_fit)")
add_image(s, "fig_expC_knob.png", 1.65, width=6.6, center=False, left=0.55)
rct = table(s,
 [[C("설정 (tr, C=16)", WHITE, True), C("축", WHITE, True), C("thr", WHITE, True), C("hit", WHITE, True)],
  [C("기준 (S=1)"), C("—"), C("0.068"), C("0.80")],
  [C("--acting-token-decay"), C("k_fit"), C("0.103"), C("0.64", RED, True)],
  [C("--acting-token-weight 0.5"), C("k_fit"), C("0.091"), C("0.65", RED, True)],
  [C("--tool-scale 0.5"), C("duty"), C("0.099"), C("0.83", GREEN, True)],
  [C("--tool-scale 0.125"), C("duty"), C("0.144"), C("0.83", GREEN, True)]],
 7.35, 1.75, 5.45, [3.05, 0.95, 0.75, 0.7], fs=11, hfs=11, row_h=0.5)
rect(s, 7.35, 5.05, 5.45, 1.9, PANEL)
textbox(s, 7.55, 5.13, 5.05, 1.75,
        [[("왜 회복의 '질'이 다른가", 12.5, BLUE, True)],
         [("• k_fit축(pause 완화): GPU에 더 올리려 캐시를", 11, RED, False)],
         [("  밀어냄 → U↑지만 hit 0.80→0.64 (=default화)", 11, RED, False)],
         [("• duty축(tool 축소): 캐시 안 건드림 → hit 유지", 11, GREEN, False)],
         [("→ 진짜 해법은 pause 완화가 아니라 워크로드", 11, INK, True)],
         [("   duty↑ 또는 용량비례 라우팅(k_fit↑).", 11, INK, True)]])
notes(s,
"세 번째 결과는 R을 올리는 방법이 두 가지인데 그 '질'이 다르다는 것입니다. R은 k_fit 곱하기 duty니까, k_fit을 "
"올리거나 duty를 올리면 됩니다. 왼쪽 k_fit 축은 pause를 완화해서 GPU에 프로그램을 더 많이 올리는 방식입니다. "
"이렇게 하면 활용률과 처리량은 오르지만, 더 올린 만큼 남의 캐시를 밀어내서 적중률이 0.80에서 0.64로 떨어집니다. "
"즉 tr을 default처럼 만들어 버리는 '나쁜 회복'입니다. 반대로 오른쪽 duty 축은 도구 시간을 줄여 R을 올리는데, "
"캐시는 전혀 건드리지 않으니 적중률이 0.83으로 그대로 유지됩니다. 이게 '좋은 회복'입니다. 표를 보시면 k_fit "
"노브 두 개는 hit가 빨간색으로 떨어지고, duty 노브 두 개는 초록색으로 유지됩니다. 여기서 얻는 통찰은, tr의 "
"열세를 고치는 진짜 방법은 스케줄러의 pause를 억지로 푸는 게 아니라, 워크로드의 duty를 높이거나 GPU 용량에 "
"비례해서 더 올리는 것, 즉 용량 비례 라우팅이라는 겁니다. 이게 다음 과제로 자연스럽게 이어집니다.")

# ===========================================================================
# SLIDE 10 — [작업6 진행] SWE sweep
# ===========================================================================
s = slide()
title(s, "작업 6 · 완료", GREEN, "SWE 스윕 결과 — tr이 세 지표 모두 승 (D와 정반대)")
add_image(s, "fig_swe_result.png", 1.5, width=12.3)
# result table (compact, left)
rdata = [
 [C("지표", WHITE, True), C("c=16 tr/def", WHITE, True), C("c=32 tr/def", WHITE, True), C("tr", WHITE, True)],
 [C("throughput"), C("0.116 / 0.065"), C("0.109 / 0.059"), C("+78~84%", GREEN, True)],
 [C("p95 지연(s)"), C("233 / 448"), C("459 / 782"), C("0.5~0.6×", GREEN, True)],
 [C("KV hit rate"), C("0.80 / 0.083"), C("0.81 / 0.065"), C("압도", GREEN, True)],
]
table(s, rdata, 0.55, 5.35, 6.6, [1.5, 1.85, 1.85, 1.4], fs=11, hfs=11, row_h=0.44)
# headline banner (right, big)
rect(s, 7.4, 5.35, 5.4, 1.76, RGBColor(0xfb,0xee,0xcd))
textbox(s, 7.6, 5.45, 5.05, 1.6,
        [[("★ 같은 2×4090, 정반대 결과", 13, AMBER, True)],
         [("D(d=0.18, R≈0.37) → tr 패 −34%", 11.5, RED, True)],
         [("SWE(d≈0.995, R≫1) → tr 승 +78~84%", 11.5, GREEN, True)],
         [("워크로드만 바꿨는데 승패가 뒤집힘을", 11, INK, False)],
         [("duty_cycle 하나로 사전 예측·적중.", 11, INK, True)]])
notes(s,
"작업 6, SWE 스윕이 끝났고 R 모델 예측이 그대로 맞았습니다. 4090 두 장에서 tr과 default를 동시성별로 세 번씩 "
"돌렸는데, 그림 세 패널이 각각 처리량, 지연, 캐시 적중률입니다. 초록이 tr, 회색이 default인데 세 개 모두에서 "
"tr이 이깁니다. 동시성 16 이상에서 처리량은 78에서 84% 더 높고, p95 지연은 default의 0.5에서 0.6배로 더 "
"빠르며, 적중률은 0.8 대 0.07로 압도합니다. 여기서 꼭 강조할 대비가 있습니다. 앞서 실험 D에서 TraceLab을 "
"돌렸을 때는 tr이 적중률만 이기고 처리량과 지연은 오히려 졌습니다. 그런데 SWE는 하드웨어가 똑같은 4090 두 "
"장인데도 세 지표 모두 이깁니다. 왜냐고요? SWE는 decode-heavy라 duty_cycle이 0.995로 거의 1이고, 그래서 "
"R이 1보다 훨씬 커서 GPU가 tr의 pause에도 굶지 않기 때문입니다. 즉 tr이 지느냐 이기느냐는 tr의 결함이 "
"아니라 워크로드의 duty가 R을 1 위로 만드느냐에 달렸고, 이걸 우리가 스윕 전에 미리 예측해서 맞혔습니다. "
"정직하게 한계도 말씀드리면, 녹화 때 턴을 40으로 제한해 20%가 잘렸지만, 결론은 턴 하나하나의 특성에 근거하고 "
"TraceLab의 fit32k와 같은 성격의 제한이라 결론에는 영향이 미미합니다.")

# ===========================================================================
# SLIDE — R model triple validation (correlation + causation + generality)
# ===========================================================================
s = slide()
title(s, "★ R 모델 종합", AMBER, "R 모델을 상관 · 인과 · 다워크로드 세 방법으로 검증")
col_w = 3.95
xs = [0.55, 4.68, 8.81]
# 1) correlation
rect(s, xs[0], 1.7, col_w, 4.55, PANEL)
textbox(s, xs[0]+0.2, 1.82, col_w-0.4, 4.4,
        [[("① 상관 (correlation)", 14, BLUE, True)],
         [("실험 C · R1", 11.5, GRAY, True)],
         [("예측 U = min(R,1) vs 실측 U", 11.5, INK, False)],
         [("Pearson r = 0.959", 14, GREEN, True)],
         [("(clean 13점, 평균오차 0.091)", 11, GRAY, False)],
         [("", 5, INK, False)],
         [("한 식이 두 레짐 모두 예측:", 11.5, INK, False)],
         [("tr R<1(굶음) · default R>1(포화)", 11.5, INK, False)],
         [("", 5, INK, False)],
         [("배경 4칸(§9·D·F·G)도", 11, GRAY, False)],
         [("같은 R 규칙에 정합.", 11, GRAY, False)]])
# 2) causation
rect(s, xs[1], 1.7, col_w, 4.55, RGBColor(0xfb,0xee,0xcd))
textbox(s, xs[1]+0.2, 1.82, col_w-0.4, 4.4,
        [[("② 인과 (causation) ★", 14, AMBER, True)],
         [("실험 C · R4 (결정타)", 11.5, GRAY, True)],
         [("duty축으로 R을 0.18→1.0 밀자", 11.5, INK, False)],
         [("tr throughput ×3.2", 14, GREEN, True)],
         [("(0.045 → 0.144), hit 0.83 유지", 11, GRAY, False)],
         [("", 5, INK, False)],
         [("→ default(0.098, hit 0.037)를", 11.5, INK, True)],
         [("   두 지표 모두 역전.", 11.5, INK, True)],
         [("", 5, INK, False)],
         [("원인을 '손으로 돌려' 결과가", 11.5, INK, False)],
         [("예측대로 따라옴 = 상관 아닌 인과.", 11.5, AMBER, True)]])
# 3) generality
rect(s, xs[2], 1.7, col_w, 4.55, PANEL)
textbox(s, xs[2]+0.2, 1.82, col_w-0.4, 4.4,
        [[("③ 다워크로드 (generality)", 14, BLUE, True)],
         [("작업 6 SWE + 실험 D/F/G", 11.5, GRAY, True)],
         [("같은 2×4090, 정반대 결과:", 11.5, INK, False)],
         [("• SWE d≈0.995,R≫1 → 승 +78~84%", 11, GREEN, True)],
         [("• D d=0.18,R=0.37 → 패 −34%", 11, RED, True)],
         [("• F/G(4090+5090) → 승/부분회복", 11, INK, False)],
         [("", 5, INK, False)],
         [("워크로드만 바꿨는데 승패가", 11.5, INK, False)],
         [("뒤집힘을 duty 하나로 사전예측·적중.", 11.5, INK, True)]])
textbox(s, 0.55, 6.42, 12.3, 0.5,
        [[("→ R = k_fit × duty_cycle 이 tr 승패를 ", 13, INK, False),
          ("예측(상관)하고 인과로 설명하며 여러 워크로드에서 성립", 13, AMBER, True),
          ("한다.", 13, INK, False)]])
notes(s,
"이 슬라이드가 R 모델의 증거를 한자리에 모은 종합입니다. 우리는 R 모델을 세 가지 서로 다른 방법으로 검증했습니다. "
"첫째, 상관입니다. 실험 C에서 R로 계산한 예측 활용률과 실제 측정값의 상관이 0.96, 열세 점에서 평균 오차가 "
"0.09였습니다. 한 식이 tr의 R<1 영역과 default의 R>1 영역을 모두 맞혔고, 배경 실험 네 칸도 같은 규칙에 "
"들어맞습니다. 둘째, 인과입니다. 이게 가장 강한 증거인데, R을 손으로 0.18에서 1.0까지 올렸더니 tr의 처리량이 "
"3.2배 뛰면서 캐시 적중률은 유지한 채 default를 역전했습니다. 원인을 직접 돌렸을 때 결과가 예측대로 따라왔으니 "
"단순 상관이 아니라 인과입니다. 셋째, 일반성입니다. 같은 4090 두 장인데 SWE는 tr이 이기고 TraceLab은 지는, "
"정반대 결과를 duty_cycle 하나로 실험 전에 미리 맞혔습니다. 이 세 가지를 합치면, R = k_fit 곱하기 duty_cycle이 "
"tr의 승패를 예측하고, 인과로 설명하며, 여러 워크로드에 두루 성립한다는 결론입니다.")

# ===========================================================================
# SLIDE — Limitations (honest)
# ===========================================================================
s = slide()
title(s, "한계 (정직)", RED, "실험 C · R 모델의 한계와 사건 기록")
rect(s, 0.55, 1.7, 12.25, 3.35, PANEL)
textbox(s, 0.8, 1.85, 11.8, 3.2,
        [[("측정·모델 한계", 13.5, BLUE, True)],
         [("① 동시 실행 경합 — ", 12, INK, True), ("실험 C는 SWE 스윕과 동시 실행(노드 CPU/RAM/PCIe 공유, GPU 연산만 분리). throughput 절대값은 영향받음 → 결론은 tr-vs-default 상대비교·예측U 정합 기반.", 12, GRAY, False)],
         [("② knob 2점 예측 편차 — ", 12, INK, True), ("k_fit 노브는 pause 타이밍을 바꿔 resident 샘플링↔실제 GPU busy 관계를 교란 → R이 U를 과소예측. (r=0.959는 워크로드만 바꾼 clean 13점 기준, knob 제외.)", 12, GRAY, False)],
         [("③ 고R 실측 U가 예측 하회 — ", 12, INK, True), ("S=0.125에서 예측 1.0 vs 실측 0.71. k_fit이 4090 KV 물리상한(≈1.3×)에 묶여 잔여 bubble. 방향·단조성은 정확, 절대 포화점만 미달.", 12, GRAY, False)],
         [("④ d의 부하의존성 — ", 12, INK, True), ("d=0.196은 c=1 고유값; 부하 하 경합으로 reasoning 늘면 변동 가능(교차확인 권장). SWE 녹화 step_limit=40 clip 20.3%(lifetime 상단만).", 12, GRAY, False)]])
rect(s, 0.55, 5.25, 12.25, 1.65, RGBColor(0xfb,0xee,0xcd))
textbox(s, 0.8, 5.38, 11.8, 1.5,
        [[("사건 기록 (데이터 무손실)", 13, AMBER, True)],
         [("• proxy-router 버그 — ", 11.5, INK, True), ("초기 Phase A가 default로 실행됨(NUL cmdline grep 실패). cmdline 스캔+router assertion으로 수정, 오염분 폐기 후 재측정.", 11.5, GRAY, False)],
         [("• 외부 종료로 D2 오염 — ", 11.5, INK, True), ("다른 터미널의 SWE 정리가 expC proxy까지 종료 → D2 3점 실패. A/R/K(42점) 무손실, D2만 경합 없이 재실행(61/64 정상)해 대체.", 11.5, GRAY, False)]])
notes(s,
"결과가 좋을수록 한계를 정직하게 밝히는 게 중요합니다. 네 가지입니다. 첫째, 실험 C는 SWE 스윕과 GPU만 분리한 채 "
"같은 노드에서 동시에 돌아서 CPU와 메모리를 나눠 썼습니다. 그래서 처리량의 '절대 수치'는 경합 영향을 받을 수 "
"있고, 그래서 저희 결론은 절대값이 아니라 tr과 default의 '상대 비교'와 예측·실측 활용률의 일치에 근거합니다. "
"둘째, k_fit 노브 두 점은 예측이 어긋났습니다. 이 노브가 pause 타이밍 자체를 바꿔서, 우리가 재는 resident 수와 "
"실제 GPU가 바쁜 시간의 관계를 교란하기 때문입니다. 그래서 상관계수 0.96은 워크로드만 바꾼 깨끗한 13점 기준이고 "
"노브 점은 제외했습니다. 셋째, R이 1에 가까운 구간에서 실측 활용률이 예측보다 조금 낮습니다. 4090의 KV 용량이 "
"물리적으로 프로그램 한 개 남짓이라 완전히 못 채우기 때문인데, 방향과 단조 증가는 정확합니다. 넷째, duty 값은 "
"동시성 1에서 잰 고유값이라 부하가 크면 조금 달라질 수 있어 교차확인이 필요합니다. 마지막으로 실험 도중 두 "
"사건이 있었는데, 프록시 라우터 버그와 외부 종료로 인한 D2 오염 모두 재측정으로 복구했고 최종 데이터에는 손실이 "
"없습니다. 이 점도 투명하게 남겨 두었습니다.")

# ===========================================================================
# SLIDE 11 — Summary & next
# ===========================================================================
s = slide()
title(s, "종합 · 다음", BLUE, "피드백을 '알고리즘 기반 인과 모델(R)'로 대응")
# two panels
rect(s, 0.78, 1.75, 5.85, 4.7, PANEL)
textbox(s, 1.05, 1.95, 5.4, 4.4,
        [[("이번에 한 것", 15, BLUE, True)],
         [("① 알고리즘을 코드까지 정확히 이해", 12.5, INK, False)],
         [("   (cost model = 용량 부등식)", 11, GRAY, False)],
         [("② eviction=재프리필 확정 (swap 아님)", 12.5, INK, False)],
         [("③ 지표 재정렬 (미스율·kv_usage)", 12.5, INK, False)],
         [("⑤ SWE=decode-heavy 특성 분석", 12.5, INK, False)],
         [("★ 흩어진 관찰 → R 모델 하나로 통합", 13, AMBER, True)],
         [("   R = k_fit × duty_cycle", 12, AMBER, True)],
         [("   (4칸 배경 실험이 이미 정합)", 11, GRAY, False)]])
rect(s, 6.9, 1.75, 5.85, 4.7, RGBColor(0xfb,0xee,0xcd))
textbox(s, 7.17, 1.95, 5.4, 4.4,
        [[("완료 (여섯 작업 전부) · 다음", 15, AMBER, True)],
         [("⑥ SWE 스윕 — tr 승 확정 +78~84%", 12.5, GREEN, True)],
         [("   (R 예측 적중: TraceLab 패·SWE 승)", 11, GREEN, False)],
         [("④ 실험 C — R 상관(r=0.959)+인과(R=1 역전)", 12.5, GREEN, True)],
         [("   확정. duty축으로 tr이 default 역전(hit 유지).", 11, GREEN, False)],
         [("", 5, INK, False)],
         [("★ tr 열세는 tr 결함이 아니라 워크로드(R<1) 탓", 12.5, AMBER, True)],
         [("   — 상관·인과·다워크로드로 검증 완료", 11, GRAY, False)],
         [("다음 과제", 14, BLUE, True)],
         [("용량 비례 라우팅으로 R을 용량으로 올려", 12.5, INK, True)],
         [("5090 과소활용 해결 (작업1 근거)", 12.5, INK, True)]])
notes(s,
"정리하겠습니다. 이번 대응의 핵심은, 교수님 피드백을 단순히 하나씩 처리한 게 아니라 'R 모델'이라는 인과 "
"모델로 묶었다는 점입니다. 왼쪽처럼 알고리즘을 코드까지 이해했고, KV 축출이 재계산이라는 걸 확정했고, 지표를 "
"바로잡았고, SWE 특성을 분석했습니다. 그리고 이 관찰들이 전부 R = k_fit 곱하기 duty_cycle 하나로 설명됩니다. "
"오른쪽이 결론입니다. 여섯 작업이 전부 끝났습니다. SWE 스윕은 tr이 78에서 84% 이겨 R 예측이 적중했고, "
"핵심인 실험 C는 R 모델을 상관계수 0.96으로 검증했을 뿐 아니라, R을 일부러 1 위로 밀어 tr이 default를 캐시 "
"적중률을 지키며 역전하는 것을 보여 '인과'까지 확정했습니다. 즉 R 모델을 상관·인과·여러 워크로드 세 방법으로 "
"검증한 겁니다. 그래서 tr이 지는 건 tr이 나빠서가 아니라 워크로드의 R이 1보다 작아서라는 게 확정됐습니다. "
"그 다음 과제는, 작업 1에서 찾은 5090 과소활용 문제를 '용량 비례 라우팅'으로 푸는 것입니다. R을 워크로드가 "
"아니라 하드웨어 용량으로 올려서 큰 5090을 제대로 활용하는 방향입니다. 이상입니다. 질문 받겠습니다.")

prs.save(OUT)
print("SAVED:", OUT, "slides:", len(prs.slides._sldIdLst))
