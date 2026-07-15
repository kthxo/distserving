#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the meeting deck: 피드백 대응 — 현상 관찰에서 알고리즘 기반 인과 모델로.
Output: slides/2026-07-07_meeting_deep-analysis_yunuikang.pptx
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from PIL import Image

FIGS = "/tmp/claude-20060/-home-yunuikang-yunuikang-work-distserving/3e5dd026-91c5-4894-b770-d96496ebbe7b/scratchpad/figs"
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
 [C("(d) tr 승패 원인을\n가설 아닌 수치로 증명"), C("작업 4  실험 C", AMBER, True),
  C("R 모델로 GPU 활용률 정량 예측·인과 확정"), C("🔄 진행 중", AMBER, True)],
 [C("(f) SWE에서 결론 재현"), C("작업 6  SWE 스윕", AMBER, True),
  C("2×4090 스윕으로 'tr이 SWE에선 이기는지' 실측 검증"), C("🔄 진행 중", AMBER, True)],
]
table(s, data, 0.78, 1.75, 11.9, [2.7, 2.6, 4.9, 1.7], fs=12.5, hfs=12.5, row_h=0.72)
textbox(s, 0.78, 6.98, 11.9, 0.4,
        [[("관통 주제 — 여섯 작업이 모두 하나의 ", 12.5, INK, False),
          ("R 모델(인과)", 12.5, AMBER, True),
          ("로 수렴한다.", 12.5, INK, False)]])
notes(s,
"이 표가 오늘 발표의 지도입니다. 왼쪽이 교수님이 주신 요구, 가운데가 그에 대응한 작업, 오른쪽이 상태입니다. "
"(a) 알고리즘을 먼저 이해하라는 요구에는 작업 1에서 논문의 비용 모델과 실제 코드를 한 줄씩 대응시켰습니다. "
"(e) KV가 넘칠 때 CPU로 옮기느냐는 질문에는 작업 2에서 '아니다, 다시 계산한다'를 코드로 확인했습니다. "
"(b)(c) 지표가 잘못됐다는 지적에는 작업 3에서 올바른 지표로 바꿨습니다. (f) SWE 워크로드는 작업 5에서 특성 "
"분석을 끝냈습니다. (d) 원인을 수치로 증명하라는 핵심 요구는 작업 4 실험 C, 그리고 SWE 재현은 작업 6인데, "
"이 둘은 지금 서버에서 돌고 있습니다. 중요한 건 여섯 작업이 전부 'R 모델' 하나로 이어진다는 점입니다.")

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
 [C("SWE 2×4090"), C("0.995"), C("2–4"), C("승 예측", GREEN, True)],
]
table(s, pdata, 8.75, 1.65, 4.25, [1.5, 0.7, 1.05, 1.0], fs=11, hfs=11, row_h=0.5,
      cell_colors={(5,0):PANEL,(5,1):PANEL,(5,2):PANEL,(5,3):RGBColor(0xd7,0xeb,0xdd)})
textbox(s, 8.75, 4.9, 4.25, 1.8,
        [[("사전 등록 예측", 12.5, AMBER, True)],
         [("네 개 배경 셀이 이미 R=min(R,1) 선과 정합.", 11.5, INK, False)],
         [("SWE는 이 규칙의 다섯 번째 검증 —", 11.5, INK, False)],
         [("스윕이 확인 중.", 11.5, INK, False)]])
notes(s,
"이 슬라이드가 R 모델이 왜 강한 증거인지 보여줍니다. 하드웨어는 똑같이 4090 두 장인데, 결과가 정반대입니다. "
"TraceLab을 돌린 실험 D는 d가 0.18이라 R이 0.37, 1보다 작아서 tr이 34% 졌습니다. 같은 하드웨어에서 SWE는 "
"d가 0.995라 R이 2에서 4, 1보다 훨씬 커서 tr이 이길 거라고 예측됩니다. 오른쪽 표를 보시면, 이미 확보한 네 개 "
"배경 실험이 전부 이 R 규칙과 맞습니다. 여기서 중요한 점은, 이 예측을 실험 전에 미리 계산해서 등록했다는 "
"것입니다. 결과를 보고 끼워 맞춘 게 아니라, duty_cycle이라는 워크로드 성질 하나만으로 서로 상반된 두 결과를 "
"미리 맞히는 것이라 인과 모델로서 훨씬 강한 증거입니다. SWE 스윕은 이 규칙의 다섯 번째 시험대입니다.")

# ===========================================================================
# SLIDE 9 — [작업4] Experiment C — DESIGN (what / why / conditions)
# ===========================================================================
s = slide()
title(s, "작업 4 · 진행 중  —  왜: tr 승패 원인을 가설이 아니라 수치·인과로 (피드백 d)",
      AMBER, "실험 C 설계 — 무엇을 · 왜 · 어떤 조건")
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
# SLIDE 10 — [작업4 진행] Experiment C — progress & partial results
# ===========================================================================
s = slide()
title(s, "작업 4 · 진행 중", AMBER, "실험 C 진행 · 부분결과 — R 모델 예측이 이미 실측과 일치")
add_image(s, "fig_expC.png", 1.5, width=8.2, center=False, left=0.5)
textbox(s, 9.0, 1.65, 4.0, 5.2,
        [[("무엇을 측정 중", 13, BLUE, True)],
         [("d, k_fit을 실측 → R 계산 →", 11.5, INK, False)],
         [("예측 U vs 실측 GPU 활용률 대조.", 11.5, INK, False)],
         [("", 6, INK, False)],
         [("완료되면 무엇이 증명", 13, BLUE, True)],
         [("tool-scale 노브로 R을 1 경계 위로", 11.5, INK, False)],
         [("넘겨 승패 역전 → 인과 확정.", 11.5, INK, False)],
         [("", 6, INK, False)],
         [("현재 부분결과", 13, GREEN, True)],
         [("C=4: 예측 R=0.31, 실측 U=0.34 ✓", 11.5, GREEN, True)],
         [("C=8: 예측 R=0.36, 실측 U=0.37 ✓", 11.5, GREEN, True)],
         [("→ 이미 예측선 위 (d≈0.20 실측)", 11.5, INK, False)],
         [("", 6, INK, False)],
         [("실행: mango1 GPU2/3, SWE와 분리.", 11, GRAY, False)],
         [("지금 tr C=8 반복3 실행 중.", 11, GRAY, False)]])
notes(s,
"작업 4 실험 C는 교수님의 핵심 요구 (d), 원인을 가설이 아니라 수치로 증명하는 것입니다. 방법은 세 단계입니다. "
"먼저 d와 k_fit을 직접 재서 R을 계산하고, 그 R이 예측하는 GPU 활용률이 실제 측정한 활용률과 맞는지 봅니다. "
"그 다음 tool-scale이라는 노브로 도구 시간을 줄여 R을 인위적으로 1 위로 올려서, 예측대로 tr이 지다가 이기는 "
"쪽으로 역전되는지 확인합니다. 이게 되면 'R이 1보다 작은 게 원인'이라는 게 인과적으로 확정됩니다. 오른쪽 "
"아래 부분결과를 보시면, 벌써 좋은 신호가 있습니다. C가 4일 때 예측 0.31에 실측 0.34, C가 8일 때 예측 0.36에 "
"실측 0.37로, 측정한 활용률이 예측선 위에 거의 정확히 올라와 있습니다. 이 실험은 SWE 스윕과 GPU를 분리해서 "
"mango1의 GPU 2, 3번에서 병렬로 돌고 있고, 지금은 tr의 C=8 세 번째 반복을 실행 중입니다.")

# ===========================================================================
# SLIDE 10 — [작업6 진행] SWE sweep
# ===========================================================================
s = slide()
title(s, "작업 6 · 진행 중", AMBER, "SWE 스윕: tr이 D와 달리 이기는지 실측 검증")
add_image(s, "fig_swe.png", 1.55, width=8.2, center=False, left=0.5)
textbox(s, 9.0, 1.7, 4.0, 5.0,
        [[("설정", 13, BLUE, True)],
         [("2×4090, C=4·8·16·32,", 11.5, INK, False)],
         [("3회 반복 = 24런, 약 8시간.", 11.5, INK, False)],
         [("", 6, INK, False)],
         [("무엇을 검증", 13, BLUE, True)],
         [("D(d=0.18)는 tr 패였는데,", 11.5, INK, False)],
         [("SWE(d≈1)는 R≫1 → tr 승 예측.", 11.5, INK, False)],
         [("R 모델의 실측 검증.", 11.5, INK, False)],
         [("", 6, INK, False)],
         [("현재 부분결과 (default 기준선)", 13, GREEN, True)],
         [("C≥8에서 hit 붕괴(0.83→0.08)", 11.5, RED, True)],
         [("= 스래싱 확인.", 11.5, INK, False)],
         [("tr 런은 실행 대기 → 승패 판정 예정.", 11.5, GRAY, False)],
         [("", 6, INK, False)],
         [("실행: 2×4090, 지금 default C=32 중.", 11, GRAY, False)]])
notes(s,
"작업 6은 SWE 데이터로 결론을 재현하는 스윕입니다. 4090 두 장에서 동시성을 4, 8, 16, 32로 바꿔가며 tr과 "
"default를 각각 세 번씩, 총 24번 돌립니다. 검증하려는 건 명확합니다. 앞서 D에서는 duty가 낮아 tr이 졌는데, "
"SWE는 duty가 거의 1이라 R이 훨씬 커서 tr이 이겨야 합니다. 즉 R 모델이 실제 데이터에서도 맞는지 보는 "
"결정적 시험입니다. 지금까지 나온 부분결과는 비교 기준인 default 쪽입니다. 왼쪽 그림처럼 동시성이 8 이상으로 "
"오르면 캐시 적중률이 0.83에서 0.08까지 무너집니다. 스래싱이 실제로 일어난다는 뜻이고, 그래서 tr이 이걸 "
"막아 이길 여지가 있다는 겁니다. tr 런은 아직 실행 대기라 최종 승패는 스윕이 끝나야 나옵니다. 지금 default의 "
"C=32를 돌리는 중입니다.")

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
        [[("진행 중 · 다음", 15, AMBER, True)],
         [("④ 실험 C — R을 1 경계 위로 넘겨 인과 확정", 12.5, INK, False)],
         [("   (부분결과 이미 예측선 위)", 11, GREEN, False)],
         [("⑥ SWE 스윕 — tr 승 예측 실측 검증", 12.5, INK, False)],
         [("   (default 기준선 스래싱 확인)", 11, GREEN, False)],
         [("", 8, INK, False)],
         [("다음 과제", 14, BLUE, True)],
         [("C·6 완료 → R 최종 검증", 12.5, INK, False)],
         [("용량 비례 라우팅으로", 12.5, INK, True)],
         [("5090 과소활용 해결 (작업1 근거)", 12.5, INK, True)]])
notes(s,
"정리하겠습니다. 이번 대응의 핵심은, 교수님 피드백을 단순히 하나씩 처리한 게 아니라 'R 모델'이라는 인과 "
"모델로 묶었다는 점입니다. 왼쪽처럼 알고리즘을 코드까지 이해했고, KV 축출이 재계산이라는 걸 확정했고, 지표를 "
"바로잡았고, SWE 특성을 분석했습니다. 그리고 이 관찰들이 전부 R = k_fit 곱하기 duty_cycle 하나로 설명됩니다. "
"오른쪽은 지금 돌리는 두 실험인데, 실험 C는 R을 인위적으로 1 위로 넘겨 원인을 확정하는 것이고 부분결과가 "
"이미 예측과 맞고 있습니다. SWE 스윕은 R 모델의 실데이터 검증입니다. 이 둘이 끝나면 R 모델이 최종 검증됩니다. "
"그 다음 과제는, 작업 1에서 찾은 5090 과소활용 문제를 '용량 비례 라우팅'으로 푸는 것입니다. 이상입니다. 질문 받겠습니다.")

prs.save(OUT)
print("SAVED:", OUT, "slides:", len(prs.slides._sldIdLst))
