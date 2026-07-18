#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P1 진행보고 데크 — Pro6000 TP2 축소재현(P0+P1).
탑다운 한 줄기: 배경(R모델·k_fit-flip 가설) → 전체 설계(P0~P3) → 환경 → P0 → P1 →
결과(TraceLab flip · SWE flip · fit 교차입증 · R모델) → 분석(정직 caveat) → 남은 P2/P3 → 요약.
결과·분석은 P1까지, 설계는 P0~P3 전체.

근거 문서(수치 그대로): logs/2026-07-16_TP2_RESULTS · plans/2026-07-15_PLAN_pro6000-tp-rescale ·
logs/2026-07-07_EXPERIMENT_C_RESULTS · logs/2026-07-06_MECHANISM_REFERENCE.
그림: figures/tp2_*.png 9종.
Output: slides/2026-07-17_P1-results_yunuikang.pptx
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from PIL import Image

FIGS = "/home/yunuikang/yunuikang_work/distserving/figures"
OUT  = "/home/yunuikang/yunuikang_work/distserving/slides/2026-07-17_P1-results_yunuikang.pptx"
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
CREAM = RGBColor(0xFB, 0xEE, 0xCD)
TL_COL = RGBColor(0x2f, 0x6d, 0xb0)   # TraceLab (matches figure blue)
SW_COL = RGBColor(0xC6, 0x76, 0x0A)   # SWE (matches figure orange, darkened for text)
GREENBG = RGBColor(0xD7, 0xEB, 0xDD)
REDBG   = RGBColor(0xF7, 0xDE, 0xDA)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT  = "Malgun Gothic"

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

def rect(s, l, t, w, h, fill, line=None, lw=1.0, shape=MSO_SHAPE.RECTANGLE):
    sp = s.shapes.add_shape(shape, Inches(l), Inches(t), Inches(w), Inches(h))
    if fill is None:
        sp.fill.background()
    else:
        sp.fill.solid(); sp.fill.fore_color.rgb = fill
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = line; sp.line.width = Pt(lw)
    sp.shadow.inherit = False
    return sp

def boxtext(s, l, t, w, h, fill, lines, line=None, lw=1.0, align=PP_ALIGN.CENTER,
            shape=MSO_SHAPE.ROUNDED_RECTANGLE):
    sp = rect(s, l, t, w, h, fill, line=line, lw=lw, shape=shape)
    tf = sp.text_frame; tf.word_wrap = True; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = Pt(4); tf.margin_right = Pt(4); tf.margin_top = Pt(2); tf.margin_bottom = Pt(2)
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        runs = ln if isinstance(ln, list) else [ln]
        for (txt, sz, col, bold) in runs:
            r = p.add_run(); r.text = txt; _set_font(r, sz, col, bold)
        p.space_after = Pt(1); p.space_before = Pt(0)
    return sp

def arrow(s, l, t, w, h, fill=GRAY, shape=MSO_SHAPE.RIGHT_ARROW):
    return rect(s, l, t, w, h, fill, shape=shape)

def title(s, tag, tag_color, head, sub=None):
    if tag:
        rect(s, 0.55, 0.42, 0.14, 0.62, tag_color)
    textbox(s, 0.78, 0.34, 12.0, 0.72,
            [[(head, 24, INK, True)]], anchor=MSO_ANCHOR.MIDDLE)
    if tag:
        textbox(s, 0.80, 1.00, 11.8, 0.34, [[(tag, 12.5, tag_color, True)]])
    rect(s, 0.78, 1.36, 11.95, 0.02, tag_color)

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
    return top + (w * ih / iw) / 914400.0  # returns bottom in inches

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
            cell.margin_top = Pt(1); cell.margin_bottom = Pt(1)
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

def C(txt, col=INK, bold=False):
    return (txt, col, bold)

# ===========================================================================
# SLIDE 1 — Title
# ===========================================================================
s = slide()
rect(s, 0, 0, 13.333, 7.5, WHITE)
rect(s, 0, 2.62, 13.333, 0.06, AMBER)
textbox(s, 0.9, 1.05, 11.5, 1.6,
        [[("P1 진행보고 — Pro6000 TP2 축소 재현", 33, BLUE, True)],
         [("k_fit-flip 가설을 두 워크로드에서 정량 입증", 25, INK, True)]])
textbox(s, 0.9, 2.9, 11.7, 1.7,
        [[("배경(4090 R모델) → 전체 설계(P0~P3) → 환경 → P0 기준측정 → ", 15, GRAY, False),
          ("P1 결과·분석", 15, AMBER, True),
          (" → 남은 P2/P3", 15, GRAY, False)],
         [("ThunderAgent serving-eval 축소 재현 · 서버 nutella1 · Deployment A(TP2 Qwen3-32B)", 14, GRAY, False)]])
textbox(s, 0.9, 6.55, 11.5, 0.5,
        [[("강윤의  ·  브랜치 yunuikang/thunderagent  ·  2026-07-17", 13, GRAY, False)]])
notes(s,
"안녕하세요, 강윤의입니다. 오늘은 Pro6000 두 장을 TP2로 묶은 축소 재현 실험의 진행 상황을 보고드립니다. "
"전체 실험은 P0부터 P3까지 네 단계로 설계했는데, 지금 결과가 나온 건 P0 기준측정과 P1 두 워크로드까지입니다. "
"그래서 오늘 발표는 하나의 줄기로 흐릅니다. 먼저 4090에서 우리가 세운 R 모델과 거기서 나온 k_fit-flip "
"가설을 배경으로 깔고, 전체 실험을 어떻게 설계했는지, 환경을 어떻게 셋업했는지, P0에서 무엇을 검증했고 "
"P1에서 어떤 결과가 나왔고 그걸 어떻게 분석했는지, 마지막으로 남은 P2와 P3를 어떻게 할지 말씀드립니다. "
"핵심 메시지 한 줄은 이겁니다. 4090에서 R이 1보다 작아 tr이 지던 TraceLab 워크로드가, KV 풀을 열 배로 "
"키우니 R이 1을 넘어 tr이 이기는 쪽으로 뒤집혔고, 이걸 TraceLab과 SWE 두 워크로드에서 정량으로 확인했습니다. "
"단, 모델이 32B라 논문의 235B, 355B에 못 미치므로 절대 성능 비교는 하지 않고, 상대 비교와 R 모델 정합, "
"정성적 메커니즘에만 근거합니다. 이 점은 발표 내내 지키겠습니다.")

# ===========================================================================
# SLIDE 2 — Background: R model + k_fit-flip hypothesis
# ===========================================================================
s = slide()
title(s, "배경", BLUE, "4090에서 세운 R 모델과 k_fit-flip 가설")
textbox(s, 0.78, 1.50, 12.0, 0.5,
        [[("R = k_fit × d,   U ≈ min(R, 1)", 16, INK, True),
          ("     — 4090 2× 실험(C)에서 예측 U vs 실측 U  Pearson r = 0.959 (clean 13점)", 12.5, GRAY, False)]])
textbox(s, 0.78, 1.98, 12.0, 0.35,
        [[("d = duty = reasoning/(reasoning+tool) · k_fit = GPU 평균 resident 수 · R≥1→GPU 포화→tr 우세, R<1→bubble→tr 열세",
           11, GRAY, False)]])

# causal chain — 4090 (lose) row
y1 = 2.65
boxtext(s, 0.78, y1, 1.95, 0.95, REDBG,
        [[("4090", 12, RED, True)], [("KV 43,888 tok", 10.5, INK, False)], [("작은 풀", 10, GRAY, False)]], line=RED)
arrow(s, 2.80, y1+0.30, 0.42, 0.34, GRAY)
boxtext(s, 3.28, y1, 1.75, 0.95, PANEL,
        [[("fit ≈ 2", 12, INK, True)], [("k_fit ≈ 1.6", 10.5, INK, False)]])
arrow(s, 5.10, y1+0.30, 0.42, 0.34, GRAY)
boxtext(s, 5.58, y1, 2.0, 0.95, PANEL,
        [[("R = 1.6 × 0.196", 11.5, INK, True)], [("= 0.31  < 1", 12, RED, True)]])
arrow(s, 7.65, y1+0.30, 0.42, 0.34, GRAY)
boxtext(s, 8.13, y1, 2.0, 0.95, PANEL,
        [[("GPU 굶음", 11.5, INK, True)], [("U ≈ 0.35", 10.5, INK, False)]])
arrow(s, 10.20, y1+0.30, 0.42, 0.34, RED)
boxtext(s, 10.70, y1, 2.02, 0.95, REDBG,
        [[("tr 패", 12.5, RED, True)], [("−34%", 12, RED, True)]], line=RED)

# causal chain — Pro6000 (flip) row
y2 = 3.95
boxtext(s, 0.78, y2, 1.95, 0.95, GREENBG,
        [[("Pro6000 TP2", 11.5, GREEN, True)], [("KV 456,944 tok", 10, INK, False)], [("×10.4 큰 풀", 10, GREEN, True)]], line=GREEN)
arrow(s, 2.80, y2+0.30, 0.42, 0.34, GREEN)
boxtext(s, 3.28, y2, 1.75, 0.95, PANEL,
        [[("fit ≈ 25", 12, INK, True)], [("k_fit ↑", 10.5, INK, False)]])
arrow(s, 5.10, y2+0.30, 0.42, 0.34, GREEN)
boxtext(s, 5.58, y2, 2.0, 0.95, PANEL,
        [[("R = k_fit × d", 11.5, INK, True)], [("≫ 1", 12, GREEN, True)]])
arrow(s, 7.65, y2+0.30, 0.42, 0.34, GREEN)
boxtext(s, 8.13, y2, 2.0, 0.95, PANEL,
        [[("GPU 안 굶음", 11, INK, True)], [("U → ~1", 10.5, INK, False)]])
arrow(s, 10.20, y2+0.30, 0.42, 0.34, GREEN)
boxtext(s, 10.70, y2, 2.02, 0.95, GREENBG,
        [[("tr 승 (가설)", 11.5, GREEN, True)], [("역전", 12, GREEN, True)]], line=GREEN)

boxtext(s, 0.78, 5.30, 11.95, 0.95, CREAM,
        [[("★ k_fit-flip 가설:  ", 14, AMBER, True),
          ("4090에서 R<1이라 tr이 지던 워크로드가, KV 풀을 키우면 R≥1로 뒤집혀 tr이 이긴다.", 14, INK, True)],
         [("→ 같은 워크로드·같은 스케줄러, KV 용량(k_fit)만 바꿔 승패가 뒤집히는가를 Pro6000 TP2에서 검증한다.", 11.5, GRAY, False)]],
        line=AMBER, align=PP_ALIGN.LEFT, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
notes(s,
"배경부터 말씀드립니다. 지난 4090 두 장 실험에서 우리는 R 모델이라는 걸 세웠습니다. tr의 GPU 활용률 U는 "
"R이라는 하나의 숫자로 예측되는데, R은 duty_cycle d와 k_fit의 곱입니다. d는 프로그램이 벽시계 시간 중 실제로 "
"GPU 연산에 쓰는 비율이고, k_fit은 GPU에 동시에 올라가는 평균 프로그램 수입니다. R이 1보다 크면 GPU가 꽉 차 "
"tr이 유리하고, 1보다 작으면 GPU에 구멍이 생겨 tr이 불리합니다. 4090 실험 C에서 예측 U와 실측 U의 상관이 "
"0.959로 이 식이 검증됐습니다. 그림의 위 줄이 4090입니다. KV 풀이 43,888 토큰으로 작아서 median 18k짜리 "
"TraceLab 프로그램이 두 개 정도만 올라갑니다. 그래서 k_fit이 1.6, d가 0.196이라 R이 0.31, 1보다 작습니다. "
"GPU가 65% 놀아서 tr이 default에게 34% 졌습니다. 아래 줄이 이번 Pro6000입니다. KV 풀을 열 배 넘게 키우면 "
"fit이 25 정도로 올라가고, tr이 충분히 적재할 수 있어 R이 1을 훨씬 넘습니다. 그러면 GPU가 굶지 않으니 tr이 "
"이기는 쪽으로 뒤집힐 것이다, 이게 오늘 검증할 k_fit-flip 가설입니다. 핵심은 워크로드도 스케줄러도 그대로 "
"두고 KV 용량 하나만 바꿔서 승패가 뒤집히는지를 보는 겁니다. R 모델의 근거는 4090 상관계수 0.959이고, "
"오늘 Pro6000에서 이 가설을 실측합니다.")

# ===========================================================================
# SLIDE 3 — Full experiment design (P0~P3): 4 workloads x 2 deployments
# ===========================================================================
s = slide()
title(s, "전체 설계 (P0~P3)", BLUE, "왜 Pro6000 TP2 축소재현인가 — 4워크로드 × 2 deployment")
textbox(s, 0.78, 1.48, 12.0, 0.42,
        [[("논문 serving eval(단일 deployment + 동시성 스윕 + 정책 비교)을 Pro6000 축소 인스턴스에서 4워크로드로 재현. "
           "정책: default(≈vLLM baseline) vs tr(≈ThunderAgent).", 11.5, GRAY, False)]])
data = [
 [C("워크로드", WHITE, True), C("Deployment", WHITE, True), C("tool 성격", WHITE, True),
  C("자극하는 스케줄러 축", WHITE, True), C("우리 예측", WHITE, True), C("Phase", WHITE, True)],
 [C("TraceLab", INK, True), C("A · TP2 32B\nGPU1+2"), C("prefill-heavy\n저듀티 d≈0.2"),
  C("★ k_fit-flip (KV 용량)"), C("4090 R<1 패 →\nPro6000 R≥1 승", GREEN, True), C("P1 ✅", GREEN, True)],
 [C("SWE-bench", INK, True), C("A · TP2 32B"), C("로컬 경량\ndecode-heavy d≈1"),
  C("KV pin → hit↑"), C("tr 압승\n(hit·throughput)", GREEN, True), C("P1 ✅", GREEN, True)],
 [C("ScienceAgent", INK, True), C("A · TP2 32B"), C("샌드박스\n다소 가변"),
  C("중간 (duty 축 중간)"), C("tr 우세\n(SWE보다 격차↓)"), C("P2 ▶", AMBER, True)],
 [C("HLE", INK, True), C("B · 8B GPU0\n+ FAISS GPU1"), C("원격 API\nheavy-tailed"),
  C("f(t) pause/resume\n(stochastic 축)"), C("tr thru 우세,\nhit는 낮음"), C("P3 ▶", AMBER, True)],
]
cc = {(1,3):CREAM, (1,5):GREENBG, (2,5):GREENBG, (3,5):RGBColor(0xfb,0xee,0xcd), (4,5):RGBColor(0xfb,0xee,0xcd)}
table(s, data, 0.78, 2.02, 11.95, [1.75, 1.85, 1.85, 2.5, 2.25, 1.0], fs=11, hfs=11.5, row_h=0.95, cell_colors=cc)
textbox(s, 0.78, 6.95, 12.0, 0.42,
        [[("4워크로드가 서로 다른 스케줄러 축을 자극 → 결론 일반성.  ", 12, INK, False),
          ("오늘 결과는 P1(TraceLab·SWE)까지", 12, GREEN, True),
          (", 설계는 P0~P3 전체.", 12, INK, False)]])
notes(s,
"전체 실험을 어떻게 설계했는지가 이 슬라이드입니다. 먼저 프레이밍을 정정했습니다. 우리가 4090에서 하던 백엔드 "
"두 개 라우팅은 사실 논문의 serving eval이 아니라 rollout 구조였습니다. 이번엔 진짜 serving eval, 즉 단일 "
"deployment 하나 앞에 ThunderAgent 프록시를 두고 동시성을 스윕하며 default와 tr 정책을 비교하는 구조를 "
"축소 재현합니다. 논문은 세 데이터셋에 네 워크로드를 쓰는데, 우리는 그 네 워크로드를 각각의 성격에 맞게 "
"가져왔습니다. 표를 보시면, TraceLab은 prefill 중심에 듀티가 낮아서 k_fit-flip을 검증하는 핵심 워크로드입니다. "
"SWE-bench는 decode 중심이라 KV를 pin하면 적중률이 올라 tr이 압승할 걸로 봅니다. ScienceAgentBench는 "
"샌드박스라 그 중간이고, HLE는 원격 API라 지연이 heavy-tailed해서 tr의 f(t) pause/resume 코스트모델이 "
"진짜 시험받는 stochastic 축입니다. 오른쪽 Phase 열을 보시면 TraceLab과 SWE는 P1에서 이미 끝났고, "
"ScienceAgent는 P2, HLE는 P3로 남아 있습니다. Deployment는 두 종류인데, A는 Qwen3-32B를 GPU 1번과 "
"2번에 TP2로 올린 번들이고 SWE, Science, TraceLab이 여기서 돕니다. B는 HLE 전용으로 8B 오케스트레이터를 "
"GPU 0번에, FAISS 리트리버를 GPU 1번에 두고 A와 시간대를 분리해 돌립니다. 워크로드별로 다른 하드웨어를 "
"쓴 논문 구조를 반영한 겁니다. 네 워크로드가 서로 다른 스케줄러 축을 자극하니 결론의 일반성을 확인할 수 "
"있습니다. 오늘 결과는 P1까지지만 설계는 이 전체 그림입니다.")

# ===========================================================================
# SLIDE 3b — Workload characterization (quantitative)
# ===========================================================================
s = slide()
title(s, "워크로드 특성 (정량)", BLUE, "워크로드별 토큰·듀티·fit 비교 — 같은 HW, 다른 자극")
add_image(s, "tp2_workload_char.png", 1.50, width=9.7, center=True)  # ~2.9in tall → bottom ~4.4
# comparison table (all 4; Science/HLE pending)
wdata = [
 [C("특성 (per-turn)", WHITE, True), C("TraceLab", WHITE, True), C("SWE-bench", WHITE, True),
  C("Science", WHITE, True), C("HLE", WHITE, True)],
 [C("입력 토큰"), C("18,684 (mean)", TL_COL, True), C("7,897 (median)", SW_COL, True), C("— (P2)", GRAY, False), C("— (P3)", GRAY, False)],
 [C("출력 토큰"), C("54.8 (mean)", TL_COL, True), C("854 (median)", SW_COL, True), C("—", GRAY, False), C("—", GRAY, False)],
 [C("입력/출력 비"), C("~341×  (prefill-heavy)", TL_COL, True), C("~9×  (decode-heavy)", SW_COL, True), C("중간(예측)", GRAY, False), C("—", GRAY, False)],
 [C("tool 시간"), C("mean 6.87s (med 0.54)"), C("median 0.15s"), C("가변(예측)", GRAY, False), C("원격 heavy-tailed", GRAY, False)],
 [C("turns/session"), C("≈3.5 (c=1 프로파일)"), C("median 16 (max 40)"), C("—", GRAY, False), C("—", GRAY, False)],
 [C("duty  d"), C("0.289", TL_COL, True), C("0.996", SW_COL, True), C("중간(예측)", GRAY, False), C("낮음(예측)", GRAY, False)],
 [C("fit = KV풀/입력 → 붕괴 C"), C("≈25 → C=32", TL_COL, True), C("≈58 → C=64", SW_COL, True), C("—", GRAY, False), C("—", GRAY, False)],
]
cw = {(3,1):RGBColor(0xdd,0xe9,0xf5),(3,2):RGBColor(0xfb,0xee,0xcd),
      (7,1):RGBColor(0xdd,0xe9,0xf5),(7,2):RGBColor(0xfb,0xee,0xcd)}
table(s, wdata, 0.78, 4.52, 11.95, [2.75, 2.45, 2.35, 1.9, 2.5], fs=10, hfs=10.5, row_h=0.305, cell_colors=cw)
textbox(s, 0.78, 7.02, 11.95, 0.35,
        [[("KV 풀 456,944 tok 고정 → 프로그램 '크기'만 다른데 fit·붕괴 임계가 갈림. TraceLab/SWE=P1 실측, Science/HLE=P2/P3 예정. "
           "(TraceLab은 c=1 duty 프로파일 mean, SWE는 녹화 median — 지표 성격 상이 명시.)", 8.5, GRAY, False)]])
notes(s,
"슬라이드 3에서 네 워크로드를 질적으로 매핑했다면, 이 슬라이드는 그걸 숫자로 정량 비교한 것입니다. 지금 실측이 "
"끝난 건 TraceLab과 SWE 두 개라 그림은 이 둘을 비교하고, Science와 HLE는 P2·P3라 표에서 예정으로 표시했습니다. "
"왼쪽 그림 첫 패널이 핵심인데, 턴당 입력과 출력 토큰을 로그 스케일로 그린 겁니다. TraceLab은 입력이 18,684인데 "
"출력이 54.8밖에 안 됩니다. 입력 대 출력 비가 341배로, 긴 프롬프트를 읽고 짧게 답하는 전형적인 prefill-heavy "
"입니다. 반대로 SWE는 입력 7,897에 출력 854로 비가 9배입니다. 상대적으로 많이 생성하는 decode-heavy죠. 이 한 "
"장으로 두 워크로드가 정반대 축을 자극한다는 게 보입니다. 가운데 패널은 duty cycle입니다. TraceLab은 0.289로, "
"벽시계 시간의 29%만 GPU 연산에 쓰고 나머지는 tool입니다. tool 시간이 평균 6.87초로 길기 때문입니다. GPU 하나를 "
"채우려면 1/d, 즉 3.45개가 동시에 돌아야 합니다. SWE는 duty가 0.996으로 거의 1입니다. tool이 median 0.15초로 "
"거의 없어서 사실상 계속 GPU를 씁니다. 오른쪽 패널이 이 둘을 붕괴 임계로 연결합니다. fit은 KV 풀 456,944를 입력 "
"크기로 나눈 값인데, 하드웨어가 같으니 KV 풀은 고정이고 오직 프로그램 크기만 다릅니다. TraceLab은 입력이 커서 "
"25개, SWE는 작아서 58개가 들어갑니다. 그래서 default가 붕괴하는 동시성이 각각 32와 64로 갈립니다. 표에 이 "
"숫자들을 정리했습니다. 마지막으로 정직하게 짚으면, TraceLab 숫자는 동시성 1 duty 프로파일의 평균값이고 SWE는 "
"녹화 분포의 중앙값이라 통계 성격이 조금 다릅니다. 그래서 절대 비교보다는 두 워크로드의 성격 대비와, 같은 "
"하드웨어에서 크기가 붕괴 임계를 결정한다는 구조를 보시면 됩니다. 이게 뒤의 결과와 fit 교차입증으로 이어집니다.")

# ===========================================================================
# SLIDE 4 — Environment
# ===========================================================================
s = slide()
title(s, "환경 설정", BLUE, "nutella1 · Deployment A (2×Pro6000 96GB TP2)")
# left: HW / stack
rect(s, 0.78, 1.55, 6.0, 3.05, PANEL)
textbox(s, 1.0, 1.66, 5.6, 2.95,
        [[("하드웨어 / 스택", 13.5, BLUE, True)],
         [("• GPU: 2×RTX PRO 6000 96GB, GPU1+GPU2 TP2", 11.5, INK, False)],
         [("  CUDA_VISIBLE_DEVICES=1,2  (합 192GB)", 10.5, GRAY, False)],
         [("• vLLM 0.24.0 / torch 2.11.0+cu130", 11.5, INK, False)],
         [("• driver 590.48.01 / CUDA 13.1, Blackwell sm_120", 11.5, INK, False)],
         [("• Qwen3-32B BF16 (weights ~66GB), max-len 32768", 11.5, INK, False)],
         [("• GPU 매핑 검증: CUDA_DEVICE_ORDER=PCI_BUS_ID", 11, INK, False)],
         [("  → 두 카드 모두 96GB 대칭 TP2 확정 (48GB 아님)", 10.5, GRAY, False)]])
# right: KV pool hero
rect(s, 7.0, 1.55, 5.55, 3.05, GREENBG)
textbox(s, 7.22, 1.68, 5.15, 2.9,
        [[("★ 실측 KV 풀", 13.5, GREEN, True)],
         [("456,944 tok", 30, GREEN, True)],
         [("= block_size 16 × 28,559 blocks", 11, INK, False)],
         [("vs 4090(43,888 tok) = ", 12, INK, False), ("×10.41", 13, GREEN, True)],
         [("TraceLab fit(median 18.7k) ≈ 25 프로그램", 11.5, INK, False)],
         [("  (4090은 fit~2) → k_fit-flip 검증 여건 확보", 10.5, GRAY, False)]])
# bottom: caveat + guardrail
rect(s, 0.78, 4.78, 11.77, 1.55, CREAM)
textbox(s, 1.0, 4.88, 11.35, 1.45,
        [[("⚠ caveat & 가드레일", 12.5, AMBER, True)],
         [("• 링크: GPU1↔GPU2 = NVLink 없음 + cross-NUMA(SYS) → TP all-reduce에 오버헤드 (throughput 절대값 caveat, "
           "P0에서 마이크로벤치로 상수화 — 다음 장).", 11, INK, False)],
         [("• 가드레일: scheduler/router.py 로직 미수정(관측·CLI 노브·replay만) · 공유 스크립트 격리 복사본 · GPU1·GPU2 전용(타 프로세스 무간섭).",
           11, INK, False)]])
notes(s,
"환경 설정입니다. 서버는 nutella1이고, 오늘 결과가 나온 Deployment A는 Pro6000 96기가 두 장을 TP2로 묶은 "
"구성입니다. CUDA_VISIBLE_DEVICES를 1,2로 지정해서 GPU 1번과 2번을 씁니다. 소프트웨어는 vLLM 0.24.0에 "
"torch 2.11, 드라이버는 590, CUDA 13.1이고 Blackwell sm_120 아키텍처입니다. 모델은 Qwen3-32B를 BF16로 "
"올렸고 가중치가 66기가입니다. 여기서 한 가지 확인한 게, CUDA 기본 순서가 FASTEST_FIRST면 96기가 두 장이 "
"아니라 96기가와 48기가 이종으로 잡힐 위험이 있었는데, CUDA_DEVICE_ORDER를 PCI_BUS_ID로 박아서 두 카드 "
"모두 96기가 대칭임을 워커 UUID와 nvidia-smi 메모리로 검증했습니다. 오른쪽이 이번 실험의 물리적 전제인데, "
"실제로 뜬 KV 풀이 456,944 토큰입니다. block_size 16에 GPU 블록이 28,559개죠. 이게 4090의 43,888 토큰 "
"대비 정확히 10.41배입니다. TraceLab 프로그램이 median 18.7k니까 fit이 25 정도, 즉 25개가 동시에 올라갈 "
"수 있습니다. 4090에선 두 개였으니 k_fit-flip을 검증할 여건이 딱 갖춰진 겁니다. 아래는 정직한 caveat인데, "
"GPU 1번과 2번 사이에 NVLink가 없고 NUMA 노드도 달라서 SYS 경로로 all-reduce가 갑니다. 논문의 H100 "
"NVSwitch보다 나쁘죠. 그래서 throughput 절대값엔 오버헤드가 있는데, 이건 P0에서 마이크로벤치로 상수화했고 "
"다음 장에서 보여드립니다. 그리고 가드레일로, 스케줄러 라우터 코드는 로직을 전혀 안 건드리고 관측과 CLI "
"노브, replay 옵션만 썼으며, 공유 스크립트는 격리 복사본으로, GPU도 1번 2번 전용으로 잡아 다른 프로세스와 "
"섞이지 않게 했습니다.")

# ===========================================================================
# SLIDE 5 — P0 bring-up & baseline (Gate 1)
# ===========================================================================
s = slide()
title(s, "P0 · 완료", GREEN, "브링업·기준측정 — 게이트 1 요약")
gdata = [
 [C("항목", WHITE, True), C("결과", WHITE, True), C("판정", WHITE, True)],
 [C("실측 KV 풀"), C("456,944 tok (16 × 28,559)"), C("×10.41, fit≈25 prog", GREEN, True)],
 [C("Python.h / torch.compile"), C("CUDA graph 51개 캡처 성공"), C("이슈 없음(CPATH 우회)", GREEN, True)],
 [C("SYS 페널티 (TP2 vs TP1)"), C("1038 / 599 tok/s = 1.73×"), C("효율 86.5%, OH ~13.5%", BLUE, True)],
 [C("TraceLab duty d"), C("0.289  (NEED 1/d = 3.45)"), C("4090(0.196)↑, flip 지지", GREEN, True)],
 [C("스모크·프록시·docker"), C("SMOKE OK · router OK · docker OK"), C("정상", GREEN, True)],
]
table(s, gdata, 0.78, 1.55, 7.3, [2.55, 3.05, 1.7], fs=11, hfs=11.5, row_h=0.72)
add_image(s, "tp2_sys_microbench.png", 1.62, width=4.55, center=False, left=8.35)
textbox(s, 8.35, 6.05, 4.55, 0.9,
        [[("SYS 마이크로벤치: TP2가 단일 GPU보다 73% 빠름", 10.5, INK, True)],
         [("→ 2GPU 연산분할 이득이 cross-NUMA all-reduce 비용을 상회. SYS caveat는 소폭(정성 결론 무해).",
           10, GRAY, False)]])
textbox(s, 0.78, 5.95, 7.3, 1.0,
        [[("★ 사전예측: fit≈25 → C≤~24에서 tr k_fit≈C ≫ NEED(3.45) → R=k_fit·d ≫ 1 → tr 승 예상.", 11, AMBER, True)],
         [("d가 4090 0.196 → 0.289로 상승(32B의 느린 reasoning이 tool 대비 비중↑) → R을 더 밀어올림. P1이 실측 검증.",
           10.5, GRAY, False)]])
notes(s,
"P0는 브링업과 기준측정입니다. 게이트 1로 정리한 표를 보시죠. 첫째, 실측 KV 풀은 앞서 말한 456,944 토큰, "
"4090의 10.41배입니다. 둘째, Blackwell에서 우려했던 Python.h와 torch.compile 문제인데, CPATH 우회를 "
"유지한 채 compile 경로로 기동하니 CUDA graph 51개가 정상 캡처됐고 이슈가 없었습니다. 셋째, 오른쪽 그림이 "
"SYS 페널티 마이크로벤치입니다. 서버를 내리고 순수 decode 처리량을 쟀는데, TP2가 1038 토큰퍼섹, GPU 한 "
"장 단독 TP1이 599였습니다. TP2가 오히려 1.73배 빠릅니다. 즉 2GPU로 연산과 대역폭을 나눈 이득이 cross-NUMA "
"all-reduce 비용을 넘어섭니다. 이상적 선형 2배 대비 효율이 86.5%니까 SYS 오버헤드는 13.5% 정도로 소폭이고, "
"우리 결론은 상대 비교라 무해합니다. 넷째, TraceLab의 duty를 동시성 1에서 재니 0.289가 나왔습니다. 4090의 "
"0.196보다 올라갔는데, 32B는 reasoning이 느려서 tool 대비 연산 비중이 커지기 때문입니다. d가 클수록 R이 "
"커지니 flip 가설에 유리합니다. 마지막으로 스모크, 프록시 라우터 검증, docker 접근까지 다 정상이라 P1으로 "
"넘어갈 수 있었습니다. 아래 별표가 핵심 사전예측인데, fit이 25니까 동시성이 24 이하일 땐 tr이 프로그램을 "
"거의 다 올려서 k_fit이 C에 가깝고, 이건 NEED인 3.45를 훨씬 넘으니 R이 1보다 크고 tr이 이길 거라고 P0 "
"단계에서 미리 예측했습니다. 이걸 P1에서 실측으로 검증합니다.")

# ===========================================================================
# SLIDE 6 — P1 overview (what we did)
# ===========================================================================
s = slide()
title(s, "P1 · 완료", GREEN, "무엇을 했나 — 파이프라인 5단계 (Deployment A)")
steps = [
 ("① TraceLab 스윕", "default→tr\nC=16·32·64\nk_fit-flip 검증", GREENBG, GREEN),
 ("② SWE 재녹화", "mini-SWE-Agent\nQwen3-32B, docker\n64/64 인스턴스", PANEL, BLUE),
 ("③ 풀 불변성", "pool 32 vs 58\nsteady-state 동일?\n→ 축소본 대표성", PANEL, BLUE),
 ("④ SWE 스윕", "default→tr\nC=16·32·64\nSWE flip 검증", GREENBG, GREEN),
 ("⑤ R모델 분석", "k_fit·d·U 산출\n예측U vs 실측U\n(4090 vs Pro6000)", CREAM, AMBER),
]
x = 0.78; w = 2.28; gap = 0.09
for i,(hd,bd,bg,cl) in enumerate(steps):
    boxtext(s, x, 1.75, w, 2.15, bg,
            [[(hd, 13, cl, True)], [("", 5, INK, False)],
             *[[(ln, 11, INK, False)] for ln in bd.split("\n")]],
            line=cl, align=PP_ALIGN.CENTER)
    if i < 4:
        arrow(s, x+w+0.005, 2.65, gap+0.10, 0.34, GRAY)
    x += w + gap + 0.10
rect(s, 0.78, 4.25, 11.95, 1.02, PANEL)
textbox(s, 1.0, 4.35, 11.55, 0.95,
        [[("공통 조건", 12, BLUE, True),
          ("  —  C=16(fit 미만, 음성대조) · 32 · 64,  per-C NPROG=max(96, 2C)=96·96·128,  REPEAT=3(에러바).",
           11.5, INK, False)],
         [("record→replay: tr/default가 동일 offered load를 결정적으로 재생 → 정책 비교 오염 제거.  "
           "C=128·256 제외(스래싱 slow, flip은 C≤64로 충분 입증).", 11, GRAY, False)]])
rect(s, 0.78, 5.42, 11.95, 1.35, GREENBG)
textbox(s, 1.0, 5.52, 11.55, 1.25,
        [[("P1 산출물 (전부 완료)", 12.5, GREEN, True)],
         [("• TraceLab flip ✅   • SWE 재녹화(64/64, decode-heavy, clip 13.8%) ✅   • 풀 불변성(32≈58) ✅",
           11.5, INK, False)],
         [("• SWE flip ✅   • R모델(Pearson r=0.982) ✅   • 그래프 9종 ✅   →  게이트 3 통과, P2 진입 전 정지.",
           11.5, INK, False)]])
notes(s,
"P1에서 무엇을 했는지 파이프라인으로 보여드립니다. 다섯 단계입니다. 먼저 TraceLab을 default와 tr로 동시성 "
"16, 32, 64에서 스윕해 k_fit-flip을 검증했습니다. 둘째, SWE는 모델이 8B에서 32B로 바뀌었으니 mini-SWE-Agent로 "
"docker 위에서 64개 인스턴스를 다시 녹화했습니다. 셋째, 이 축소본 64개가 대표성이 있는지 풀 크기 32와 58을 "
"비교해 steady-state 처리량이 같은지 확인했습니다. 넷째, SWE도 같은 동시성으로 스윕해 flip을 봤습니다. "
"다섯째, 모든 샘플러에서 k_fit, d, U를 뽑아 예측 U와 실측 U를 4090과 Pro6000을 함께 놓고 R 모델을 "
"분석했습니다. 공통 조건은 아래에 있는데, 동시성은 16, 32, 64를 씁니다. 16은 fit 25보다 작아서 양쪽이 다 "
"여유가 있는 음성 대조군입니다. 프로그램 수는 동시성의 두 배 또는 최소 96으로 잡아 정상상태를 확보했고, "
"에러바를 위해 세 번씩 반복했습니다. 중요한 방법론이 record-replay인데, tr과 default가 완전히 동일한 부하를 "
"결정적으로 재생하게 해서 정책 비교가 에이전트나 원격 도구 편차로 오염되지 않게 합니다. 128과 256은 스래싱 "
"구간이라 너무 느리고, flip은 64까지로 충분히 입증되므로 제외했습니다. 결과적으로 TraceLab flip, SWE 재녹화, "
"풀 불변성, SWE flip, R 모델, 그래프 아홉 종까지 전부 완료해 게이트 3를 통과했고, 지시대로 P2 진입 전에 "
"정지한 상태입니다.")

# ===========================================================================
# SLIDE 7 — Result 1: TraceLab flip (triptych)
# ===========================================================================
s = slide()
title(s, "P1 결과 ①", GREEN, "TraceLab k_fit-flip — C≥32에서 tr이 default를 역전")
add_image(s, "tp2_tracelab_throughput.png", 1.52, width=4.05, center=False, left=0.30)
add_image(s, "tp2_tracelab_hitrate.png",   1.52, width=4.05, center=False, left=4.62)
add_image(s, "tp2_tracelab_p95.png",       1.52, width=4.05, center=False, left=8.94)
tdata = [
 [C("C", WHITE, True), C("def thru", WHITE, True), C("tr thru", WHITE, True),
  C("def hit", WHITE, True), C("tr hit", WHITE, True), C("def p95", WHITE, True),
  C("tr p95", WHITE, True), C("tr 이득", WHITE, True)],
 [C("16 (fit 미만)"), C("0.133"), C("0.133"), C("0.809"), C("0.810"), C("254"), C("254"), C("동률(음성대조 ✅)", GRAY, True)],
 [C("32 (fit 초과)"), C("0.039"), C("0.073", GREEN, True), C("0.269"), C("0.613", GREEN, True), C("1402"), C("761", GREEN, True), C("thru +87%, hit 2.3×, p95 −46%", GREEN, True)],
 [C("64 (fit 초과)"), C("0.040"), C("0.073", GREEN, True), C("0.182"), C("0.569", GREEN, True), C("2382"), C("1254", GREEN, True), C("thru +80%, hit 3.1×, p95 −47%", GREEN, True)],
]
cc7 = {(2,2):GREENBG,(2,4):GREENBG,(2,6):GREENBG,(3,2):GREENBG,(3,4):GREENBG,(3,6):GREENBG}
table(s, tdata, 0.55, 4.62, 12.25, [1.6, 1.25, 1.25, 1.25, 1.15, 1.25, 1.15, 3.35], fs=10.5, hfs=10.5, row_h=0.48, cell_colors=cc7)
textbox(s, 0.55, 6.55, 12.25, 0.5,
        [[("★ 4090에서 tr −34% 패 → Pro6000(KV ×10.4, fit≈25)에서 C≥32 역전.  ", 12, AMBER, True),
          ("C=16(<fit)은 양쪽 여유 → 동률(음성대조 성립).", 11.5, INK, False)]])
notes(s,
"P1 첫 결과, TraceLab flip입니다. 세 패널이 각각 throughput, KV hit rate, p95 지연이고 가로축이 동시성입니다. "
"동시성 16은 fit 25보다 작아서 tr과 default가 완전히 겹칩니다. 양쪽 다 KV에 여유가 있으니 스케줄링이 개입할 "
"일이 없죠. 이게 음성 대조군으로, 우리 측정이 인위적 편향이 없다는 증거입니다. 그런데 동시성이 32, 즉 fit을 "
"넘어서면 갈라집니다. default는 throughput이 0.133에서 0.039로 3.4배 떨어지고, 적중률이 0.81에서 0.27로 "
"붕괴하고, p95가 254초에서 1402초로 여섯 배 뜁니다. 전형적인 스래싱입니다. 반면 tr은 throughput 0.073, "
"적중률 0.61, p95 761초로 버팁니다. 그래서 C=32에서 tr이 throughput은 87% 높고, 적중률은 2.3배, p95는 "
"46% 낮습니다. C=64에서도 throughput 80% 우세, 적중률 3.1배, p95 47% 감소로 격차가 유지됩니다. 핵심은 "
"이겁니다. 정확히 같은 TraceLab 워크로드가 4090에선 tr이 34% 졌는데, KV를 10.4배로 키운 Pro6000에선 "
"C가 fit을 넘는 순간 tr이 세 지표 모두에서 명확히 이깁니다. k_fit-flip 가설이 정량으로 입증된 겁니다. "
"세 번 반복했고 셀별 편차는 작았습니다.")

# ===========================================================================
# SLIDE 8 — Result 2: SWE flip (triptych)
# ===========================================================================
s = slide()
title(s, "P1 결과 ②", GREEN, "SWE k_fit-flip — decode-heavy, C=64(fit 초과)에서 역전")
add_image(s, "tp2_swe_throughput.png", 1.52, width=4.05, center=False, left=0.30)
add_image(s, "tp2_swe_hitrate.png",   1.52, width=4.05, center=False, left=4.62)
add_image(s, "tp2_swe_p95.png",       1.52, width=4.05, center=False, left=8.94)
sdata = [
 [C("C", WHITE, True), C("def thru", WHITE, True), C("tr thru", WHITE, True),
  C("def hit", WHITE, True), C("tr hit", WHITE, True), C("def p95", WHITE, True),
  C("tr p95", WHITE, True), C("tr 이득", WHITE, True)],
 [C("16 (fit 미만)"), C("0.125"), C("0.124"), C("0.911"), C("0.911"), C("264"), C("268"), C("동률", GRAY, True)],
 [C("32 (fit 미만)"), C("0.135"), C("0.133"), C("0.911"), C("0.911"), C("403"), C("467"), C("동률(둘 다 스래싱 전)", GRAY, True)],
 [C("64 (fit 초과)"), C("0.024"), C("0.051", GREEN, True), C("0.241"), C("0.686", GREEN, True), C("4118"), C("2016", GREEN, True), C("thru +113%, hit 2.8×, p95 −51%", GREEN, True)],
]
cc8 = {(3,2):GREENBG,(3,4):GREENBG,(3,6):GREENBG}
table(s, sdata, 0.55, 4.62, 12.25, [1.6, 1.25, 1.25, 1.25, 1.15, 1.25, 1.15, 3.35], fs=10.5, hfs=10.5, row_h=0.48, cell_colors=cc8)
textbox(s, 0.55, 6.55, 12.25, 0.5,
        [[("SWE: decode-heavy(d=0.996), input median 7,897 → fit≈58.  ", 12, INK, False),
          ("C=16·32(<fit) 동률, C=64(>fit) tr 역전.", 12, AMBER, True),
          ("  풀 불변성 pool 32≈58(~4% 이내) → 축소본 대표성 확인.", 11, GRAY, False)]])
notes(s,
"P1 두 번째 결과, SWE flip입니다. SWE는 성격이 TraceLab과 반대인 decode-heavy 워크로드입니다. duty가 0.996, "
"거의 1이고, 입력 median이 7,897 토큰으로 TraceLab의 18.7k보다 작습니다. 프로그램이 작으니 KV 풀에 더 많이 "
"들어가서 fit이 58 정도로 큽니다. 그래서 붕괴 임계가 TraceLab보다 오른쪽으로 밀립니다. 패널을 보시면 동시성 "
"16과 32에서는 tr과 default가 둘 다 적중률 0.91로 정상입니다. fit 58보다 아래라 아직 스래싱이 안 일어나기 "
"때문입니다. 이 두 점도 음성 대조가 됩니다. 그런데 동시성 64, fit을 넘는 순간 default가 붕괴합니다. 적중률이 "
"0.91에서 0.24로 떨어지고 throughput이 0.024로 주저앉고 p95가 4118초까지 치솟습니다. tr은 throughput "
"0.051, 적중률 0.69, p95 2016초로 버팁니다. 그래서 C=64에서 tr이 throughput 113% 우세, 적중률 2.8배, "
"p95 51% 감소입니다. TraceLab보다 오히려 throughput 이득이 큽니다. 그리고 이 SWE 축소본 64개가 대표성이 "
"있는지 풀 32와 58을 비교했는데 처리량과 적중률이 4% 이내로 같아서 축소본으로 충분하다는 걸 확인했습니다. "
"정직하게 짚으면, SWE의 16과 32는 fit 아래라 tr과 default가 같고, 붕괴는 64에서만 나타납니다. 이건 다음 "
"장의 fit 개념으로 자연스럽게 설명됩니다.")

# ===========================================================================
# SLIDE 9 — fit concept: cross-validation across workloads
# ===========================================================================
s = slide()
title(s, "P1 결과 ② (교차입증)", GREEN, "fit = KV풀 / 입력크기 — 워크로드가 붕괴 임계를 결정")
# concept formula
boxtext(s, 3.35, 1.55, 6.6, 0.78, CREAM,
        [[("fit  =  KV 풀 (456,944 tok)  ÷  프로그램 입력크기", 15, INK, True)]],
        line=AMBER)
textbox(s, 0.78, 2.42, 12.0, 0.35,
        [[("같은 하드웨어(KV 풀 고정) · 같은 스케줄러 → 프로그램 '크기'만 다른데 default 붕괴 임계(C)가 갈린다.",
           12, GRAY, False)], ], align=PP_ALIGN.CENTER)
# two workload columns
rect(s, 1.3, 3.0, 4.9, 3.05, PANEL)
textbox(s, 1.55, 3.12, 4.45, 2.9,
        [[("TraceLab (prefill-heavy)", 13.5, BLUE, True)],
         [("입력 median  18,684 tok", 12, INK, False)],
         [("fit ≈ 456,944 / 18,684  ", 12, INK, False), ("≈ 25", 14, AMBER, True)],
         [("", 6, INK, False)],
         [("→ C=16(<25) 동률", 12, INK, False)],
         [("→ ", 12, INK, False), ("C=32(>25) default 붕괴", 12.5, RED, True)],
         [("   tr 역전 (+87% thru)", 12, GREEN, True)]])
rect(s, 7.13, 3.0, 4.9, 3.05, PANEL)
textbox(s, 7.38, 3.12, 4.45, 2.9,
        [[("SWE (decode-heavy)", 13.5, BLUE, True)],
         [("입력 median  7,897 tok", 12, INK, False)],
         [("fit ≈ 456,944 / 7,897  ", 12, INK, False), ("≈ 58", 14, AMBER, True)],
         [("", 6, INK, False)],
         [("→ C=16·32(<58) 동률", 12, INK, False)],
         [("→ ", 12, INK, False), ("C=64(>58) default 붕괴", 12.5, RED, True)],
         [("   tr 역전 (+113% thru)", 12, GREEN, True)]])
# center small arrow marker
boxtext(s, 6.2, 4.15, 0.9, 0.75, WHITE, [[("작을수록", 9.5, GRAY, False)],[("fit↑", 11, INK, True)]], line=GRAY)
textbox(s, 0.78, 6.25, 12.0, 0.55,
        [[("★ 프로그램이 작을수록 더 많이 적재(fit↑) → 붕괴가 더 높은 C에서 발생.  ", 12, AMBER, True),
          ("두 워크로드가 같은 HW에서 fit이 임계를 결정함을 교차입증.", 11.5, INK, False)]], align=PP_ALIGN.CENTER)
notes(s,
"이 슬라이드가 TraceLab과 SWE 두 결과를 하나로 묶는 교차입증입니다. 개념은 간단합니다. fit은 KV 풀을 프로그램 "
"하나의 입력 크기로 나눈 값, 즉 GPU에 동시에 몇 개나 올릴 수 있느냐입니다. 하드웨어가 같으면 KV 풀은 456,944로 "
"고정이고 스케줄러도 같으니, 오직 프로그램 크기만 다릅니다. 그런데 그 크기 하나가 default가 언제 붕괴하는지를 "
"결정합니다. 왼쪽 TraceLab은 입력이 18,684 토큰으로 커서 fit이 25입니다. 그래서 동시성 16까진 여유롭다가 "
"32에서 fit을 넘어 default가 붕괴하고 tr이 87% 역전합니다. 오른쪽 SWE는 입력이 7,897로 절반 이하라 fit이 "
"58로 큽니다. 프로그램이 작으니 더 많이 올라가는 거죠. 그래서 16과 32까진 둘 다 멀쩡하다가 64에서야 붕괴하고 "
"tr이 113% 역전합니다. 즉 프로그램이 작을수록 fit이 커지고 붕괴가 더 높은 동시성에서 일어납니다. 같은 하드웨어, "
"같은 스케줄러인데 워크로드 크기만으로 붕괴 임계가 25 대 58로 갈린 걸 두 워크로드에서 서로 독립적으로 확인한 "
"겁니다. 이건 R 모델과 k_fit-flip이 우연이 아니라 물리적 fit 법칙에서 나온다는 강한 방증입니다.")

# ===========================================================================
# SLIDE 10 — Result 3: R model quantification
# ===========================================================================
s = slide()
title(s, "P1 결과 ③", GREEN, "R 모델 정량 — flip을 예측 U vs 실측 U로 검증")
add_image(s, "tp2_pred_vs_meas_U.png", 1.55, width=4.85, center=False, left=0.55)
# right: k_fit-flip quantification
rdata = [
 [C("TraceLab tr", WHITE, True), C("4090", WHITE, True), C("Pro6000(C=32)", WHITE, True)],
 [C("k_fit"), C("1.6"), C("21.6", GREEN, True)],
 [C("d"), C("0.196"), C("0.289")],
 [C("R = k_fit·d"), C("0.31", RED, True), C("6.2", GREEN, True)],
 [C("실측 U"), C("0.35", RED, True), C("0.97", GREEN, True)],
]
cc10 = {(1,2):GREENBG,(3,1):REDBG,(3,2):GREENBG,(4,1):REDBG,(4,2):GREENBG}
table(s, rdata, 5.75, 1.62, 7.0, [2.3, 2.0, 2.7], fs=12.5, hfs=12, row_h=0.56, cell_colors=cc10)
rect(s, 5.75, 4.6, 7.0, 2.3, CREAM)
textbox(s, 5.98, 4.72, 6.55, 2.15,
        [[("k_fit-flip 정량", 14, AMBER, True)],
         [("KV ×10.4 → tr이 충분히 적재(k_fit 1.6→21.6)", 12, INK, False)],
         [("→ R 0.31→6.2 → 실측 U 0.35→0.97", 12, INK, True)],
         [("= 4090에서 pause로 GPU를 굶겨(R<1) 지던 것이,", 11.5, GRAY, False)],
         [("  fit이 커져 tr이 GPU를 안 굶김(R≫1) → 승.", 11.5, GRAY, False)],
         [("★ 4090 앵커 포함 Pearson r(예측U, 실측U) = 0.982", 12.5, GREEN, True)]])
notes(s,
"P1 세 번째 결과는 flip을 R 모델 숫자로 정량화한 겁니다. 왼쪽 그림이 예측 U 대 실측 U인데, 삼각형이 4090, "
"동그라미와 네모가 Pro6000입니다. 점들이 대각선 y=x 위에 잘 올라옵니다. 오른쪽 표가 핵심입니다. TraceLab tr을 "
"보면, k_fit이 4090에서 1.6이었는데 Pro6000에선 21.6으로 뛰었습니다. KV를 10.4배로 키우니 tr이 프로그램을 "
"그만큼 더 많이 올릴 수 있게 된 거죠. 그 결과 R이 0.31에서 6.2로, 실측 GPU 활용률 U가 0.35에서 0.97로 "
"올라갔습니다. 해석하면, 4090에서는 tr이 캐시를 지키려 pause를 많이 해서 GPU를 굶겼고 그게 R이 1보다 작은 "
"이유였는데, fit이 커지니 pause를 해도 충분히 적재돼서 GPU가 안 굶고, 그래서 이깁니다. 4090 앵커까지 포함해 "
"예측 U와 실측 U의 Pearson 상관이 0.982로, 4090에서 세운 R 모델이 Pro6000까지 일관되게 설명합니다. 다만 "
"여기엔 다음 장에서 다룰 정직한 caveat가 있습니다. Pro6000에선 U가 거의 다 포화라, 이 표만 보면 tr 우위가 "
"occupancy 때문인 것처럼 보이는데 실제로는 그렇지 않습니다.")

# ===========================================================================
# SLIDE 11 — Analysis + honest caveat
# ===========================================================================
s = slide()
title(s, "분석 · 정직한 통찰", AMBER, "붕괴 메커니즘과 flip 메커니즘의 '층위 차이'")
# mechanism boxes: default vs tr
rect(s, 0.78, 1.55, 5.9, 2.35, REDBG)
textbox(s, 1.0, 1.66, 5.5, 2.25,
        [[("default (C > fit)", 13, RED, True)],
         [("KV 과구독 → remaining_capacity()<0", 11.5, INK, False)],
         [("→ 스래싱: 캐시 evict → 다음 턴 재프리필", 11.5, INK, False)],
         [("→ hit 붕괴(0.81→0.18), 재프리필 낭비로", 11.5, INK, False)],
         [("  throughput·latency 붕괴", 11.5, INK, False)],
         [("(GPU는 재프리필로 busy — 그러나 낭비)", 11, GRAY, True)]])
rect(s, 6.85, 1.55, 5.9, 2.35, GREENBG)
textbox(s, 7.07, 1.66, 5.5, 2.25,
        [[("tr (pause/resume)", 13, GREEN, True)],
         [("용량 부등식 위반 시 가장 작은 ACTING pause", 11.5, INK, False)],
         [("→ resident를 fit 내로 유지 → evict 사전차단", 11.5, INK, False)],
         [("→ hit 유지(0.57~0.61), goodput productive", 11.5, INK, False)],
         [("코드: _pause_until_safe (router.py:773),", 10.5, GRAY, False)],
         [("shared_tokens=caching (vllm_metrics.py:294)", 10.5, GRAY, False)]])
# honest caveat banner
rect(s, 0.78, 4.05, 11.97, 2.75, CREAM)
textbox(s, 1.0, 4.16, 11.55, 2.65,
        [[("★ 정직 caveat — tr 우위의 정체가 층위가 다르다", 14, AMBER, True)],
         [("Pro6000에선 모든 셀에서 R>1 → 실측 U가 ~0.97–1.0으로 포화 (스래싱하는 default도 GPU는 재프리필로 busy).",
           12, INK, True)],
         [("→ 따라서 Pro6000에서 tr 우위는 ", 12, INK, False),
          ("occupancy(U)가 아니라 KV hit / goodput", 12.5, RED, True),
          (" 이다 (default는 busy하지만 낭비, tr은 hit 유지로 productive).", 12, INK, False)],
         [("", 5, INK, False)],
         [("즉 k_fit-flip 메커니즘의 층위가 다르다:  ", 12, INK, True),
          ("4090 = R<1 starvation 해소(occupancy) · Pro6000 = thrashing 회피(goodput).", 12, BLUE, True)],
         [("한계: 모델 32B(논문 235B/355B 미달) → 절대비교 안 함, 상대·R정합·정성.  U 포화로 Pro6000 R모델은 4090 앵커로 flip 해석.",
           10.5, GRAY, False)]])
notes(s,
"이제 분석인데, 결과가 좋을수록 정직하게 파고들어야 합니다. 위쪽 두 박스가 붕괴 메커니즘입니다. default는 "
"동시성이 fit을 넘으면 KV를 과구독합니다. 코드로는 remaining_capacity가 음수가 되는 거죠. 그러면 스래싱이 "
"일어나 캐시가 evict되고, 다음 턴에 그 프로그램이 다시 오면 처음부터 재프리필해야 합니다. 그래서 적중률이 "
"0.81에서 0.18로 붕괴하고 재프리필 낭비로 throughput과 지연이 무너집니다. 여기서 중요한 건, GPU 자체는 그 "
"재프리필 때문에 계속 바쁘다는 겁니다. 바쁜데 낭비인 거죠. 오른쪽 tr은 용량 부등식이 깨질 것 같으면 가장 작은 "
"ACTING 프로그램부터 pause해서 resident를 fit 안으로 유지합니다. 그래서 evict를 사전에 막고 적중률을 0.6 "
"근처로 지켜 goodput이 productive합니다. 코드 근거는 router.py 773번 줄의 pause_until_safe와 vllm_metrics "
"294번의 shared_tokens입니다. 그리고 아래 별표가 오늘 발표에서 제가 가장 정직하게 강조하고 싶은 caveat입니다. "
"Pro6000에선 모든 셀에서 R이 1보다 큽니다. 그래서 실측 U가 tr이든 default든 거의 0.97에서 1.0으로 포화입니다. "
"스래싱하는 default조차 재프리필로 GPU가 바쁘니까요. 이 말은, Pro6000에서 tr이 이기는 이유는 GPU를 더 많이 "
"써서, 즉 occupancy 때문이 아니라, 같은 busy 시간을 낭비 없이 KV hit으로 쓰는 goodput 때문이라는 겁니다. "
"그래서 k_fit-flip이라는 같은 이름의 현상이 4090과 Pro6000에서 메커니즘 층위가 다릅니다. 4090에선 R이 1보다 "
"작던 걸 1 위로 올려 GPU 굶주림, 즉 occupancy를 해소한 거고, Pro6000에선 이미 GPU가 꽉 찬 상태에서 스래싱을 "
"피해 goodput을 지킨 겁니다. 이 구분을 흐리면 안 됩니다. 마지막 줄은 전역 한계인데, 모델이 32B라 논문 대형 "
"모델과 절대 비교는 안 하고 상대 비교와 R 정합, 정성에만 근거하며, U 포화 때문에 Pro6000의 R 모델 해석은 "
"4090 앵커에 기대어 flip으로 읽습니다.")

# ===========================================================================
# SLIDE 11a — Absolute comparison with paper (matched unit: steps/min)
# ===========================================================================
s = slide()
title(s, "논문과의 비교 ① (절대)", AMBER, "정량 결과 절대비교 — 단위 steps/min (논문과 동일)")
add_image(s, "tp2_abs_stepsmin.png", 1.48, width=10.6, center=True)  # ~3.2in tall → bottom ~4.7
# exact-number table (left)
adata = [
 [C("steps/min", WHITE, True), C("default(=vLLM)", WHITE, True), C("tr(=TA)", WHITE, True), C("tr/def", WHITE, True)],
 [C("우리 SWE  C=32 (fit 미만·peak)"), C("146"), C("143"), C("~1.0", GRAY, True)],
 [C("우리 SWE  C=64 (fit 초과)"), C("27"), C("56", GREEN, True), C("2.07×", GREEN, True)],
 [C("우리 TraceLab  C=32 (fit 초과)"), C("13"), C("24", GREEN, True), C("1.88×", GREEN, True)],
 [C("논문 mini-SWE  C=144 (2×H100)"), C("375"), C("672", BLUE, True), C("1.79×", BLUE, True)],
]
ac = {(2,2):GREENBG,(2,3):GREENBG,(3,2):GREENBG,(3,3):GREENBG,(4,2):RGBColor(0xdd,0xe9,0xf5),(4,3):RGBColor(0xdd,0xe9,0xf5)}
table(s, adata, 0.55, 4.82, 7.0, [3.35, 1.55, 1.05, 1.05], fs=10, hfs=9.5, row_h=0.42, cell_colors=ac)
# caveat (right)
rect(s, 7.75, 4.82, 5.05, 2.1, CREAM)
textbox(s, 7.94, 4.9, 4.7, 2.0,
        [[("읽는 법 (정직)", 11.5, AMBER, True)],
         [("• 1 step = reasoning+acting 1턴 (논문 정의).", 10, INK, False)],
         [("• 절대 steps/min은 우리가 논문의 ~1/7–1/12", 10, INK, True)],
         [("  (32B·2×Pro6000 SYS vs 355B급·2×H100 노드,", 9.3, GRAY, False)],
         [("   동시성 C=64 vs 144) → 절대비교 부적절, 규모·단위 확인용.", 9.3, GRAY, False)],
         [("• tr/default 비 1.8–2.1× 는 논문 tr/vLLM 1.79×와 같은 대역.", 10, GREEN, True)],
         [("• 논문 Fig 4 규모(step/min): SWE~400·OpenH~200·Sci~60·HLE~8.", 9.3, GRAY, False)]])
notes(s,
"교수님 말씀대로, 절대비교가 엄밀히는 안 되더라도 단위를 논문과 맞춰서 정량 수치를 일단 보여드리는 슬라이드입니다. "
"논문의 throughput 단위는 steps per minute이고, 1 step은 reasoning과 acting 한 턴입니다. 우리 결과는 원래 초당 "
"프로그램 수로 쟀는데, 프로그램당 평균 턴 수를 곱하고 60을 곱해 steps per minute으로 변환했습니다. 이 턴 수는 "
"결정적 replay라 tr과 default가 완전히 같아서, 앞서 보고한 상대 이득이 그대로 보존됩니다. 그림 왼쪽이 우리 SWE, "
"즉 mini-SWEAgent입니다. 동시성 16과 32에서는 tr과 default가 130에서 145로 비슷하다가, fit을 넘는 64에서 "
"default가 27로 붕괴하고 tr은 56으로, 두 배 넘게 이깁니다. 가운데가 우리 TraceLab인데 우리 고유 워크로드라 "
"논문엔 없습니다. 여기서도 C=32에서 default 13, tr 24로 tr이 이깁니다. 오른쪽이 논문 값입니다. 논문 부록 Table 7이 "
"mini-SWEAgent를 steps per minute으로 딱 보고하는데, 2×H100 노드에서 동시성 144일 때 vLLM이 375, 여기에 "
"로컬 스케줄링을 켜면 602, 글로벌 큐까지 켠 완전한 ThunderAgent가 672입니다. vLLM 대비 1.79배죠. 아래 표에 "
"정확한 숫자를 정리했습니다. 여기서 정직하게 두 가지를 말씀드립니다. 첫째, 절대 steps per minute은 우리가 논문의 "
"7분의 1에서 12분의 1 수준입니다. 우리는 32B를 Pro6000 두 장에 올렸는데 그나마 NVLink 없는 SYS 연결이고, "
"논문은 355B급을 H100 두 노드, 즉 열여섯 장에 올렸으며 동시성도 64 대 144로 다릅니다. 그래서 절대값 자체는 "
"비교 대상이 아니고 규모와 단위를 확인하는 용도입니다. 둘째, 그런데 흥미롭게도 tr을 default로 나눈 비는 우리가 "
"1.8에서 2.1배로, 논문의 1.79배와 같은 대역에 있습니다. 즉 절대 규모는 크게 다르지만 ThunderAgent가 vLLM을 "
"이기는 배수는 비슷하다는 겁니다. 이게 다음 장에서 정리할 경향성 일치의 정량적 예고편입니다.")

# ===========================================================================
# SLIDE 11b — Comparison with ThunderAgent paper (trend agreement)
# ===========================================================================
s = slide()
title(s, "논문과의 비교 ② (경향)", AMBER, "경향성 일치 — 절대값이 아니라 방향이 논문과 같다")
add_image(s, "tp2_paper_trend.png", 1.52, width=6.35, center=False, left=0.5)
# trend agreement table (right)
pdata = [
 [C("경향성", WHITE, True), C("논문 (Fig 4/5)", WHITE, True), C("우리 (P1)", WHITE, True), C("", WHITE, True)],
 [C("tr > vLLM throughput"), C("전 워크로드 1.48–3.58×"), C("SWE 2.13×, TL 1.87×"), C("✅", GREEN, True)],
 [C("고동시성서 이득 발생·확대"), C("96 병렬서 격차 최대"), C("C<fit 동률→C≥fit 역전"), C("✅", GREEN, True)],
 [C("tr KV hit ≫ vLLM (thrash 회피)"), C("예측가능 ≈100%, vLLM 붕괴"), C("tr hit 2.3–3.1×"), C("✅", GREEN, True)],
 [C("decode-heavy = 최대 승"), C("SWE·OpenHands 2.4–3.6×"), C("SWE 최대 +113%"), C("✅", GREEN, True)],
 [C("stochastic → hit 희생·승폭↓"), C("HLE 1.48×(hit≤25%), Sci 1.24×"), C("P2/P3 예정(예측 동일)"), C("▶", AMBER, True)],
]
table(s, pdata, 6.95, 1.55, 6.25, [2.2, 1.95, 1.65, 0.45], fs=8.8, hfs=9, row_h=0.62)
# mechanism-match callout
rect(s, 6.95, 5.42, 6.25, 1.0, GREENBG)
textbox(s, 7.14, 5.5, 5.9, 0.95,
        [[("메커니즘도 동일", 11, GREEN, True)],
         [("논문: vLLM 붕괴 = KV eviction→thrashing (동시성↑, 메모리 부족).", 9.5, INK, False)],
         [("= 우리 default 붕괴 메커니즘과 일치(fit 초과 시 스래싱).", 9.5, INK, False)]])
# honest differences (bottom-left)
rect(s, 0.5, 4.35, 6.35, 2.07, CREAM)
textbox(s, 0.68, 4.45, 6.0, 1.97,
        [[("정직한 차이 (절대비교 안 함)", 11, AMBER, True)],
         [("• HW·모델 상이: 우리 32B/Pro6000 TP2(SYS) vs 논문 235B·355B/8×H100, HLE 8B/5090 → 방향·상대만.",
           9.3, INK, False)],
         [("• k_fit-flip은 논문의 확장: 논문은 KV 충분(H100)→tr 상시 승. 우리는 KV 축소(4090 패)→확대(승)로 '이득의 경계(fit)'를 드러냄.",
           9.3, INK, False)],
         [("• Continuum 미구현→vLLM(=default) 대비만(논문 tr–Continuum HLE 0.65×는 인용). SWE만 논문 직접대응, TraceLab은 우리 고유.",
           9.3, INK, False)]])
notes(s,
"교수님이 요청하신 논문과의 비교입니다. 핵심 메시지는 절대 성능이 아니라 경향성, 즉 방향이 논문과 같다는 "
"겁니다. 왼쪽 그림 왼쪽 패널이 논문 Figure 4인데, ThunderAgent가 vLLM 대비 throughput을 얼마나 올렸는지입니다. "
"여섯 워크로드 전부 1배 선 위, 즉 전부 vLLM을 이깁니다. 논문 본문 표현으로 vLLM 대비 1.48배에서 3.58배입니다. "
"파란색이 예측가능한 decode-heavy 코딩 에이전트인 SWE와 OpenHands인데 2.4배에서 3.6배로 크게 이기고, 주황색이 "
"stochastic한 HLE와 Science인데 1.24에서 1.48배로 이득이 작습니다. 오른쪽 패널이 우리 결과입니다. fit을 넘는 "
"동시성에서 tr을 default로 나눈 값이 SWE는 2.13배, TraceLab은 1.87배로 둘 다 1배 선 위, 같은 방향입니다. "
"오른쪽 표에 경향을 다섯 개로 정리했습니다. 첫째, tr이 vLLM 기준선을 이기는 방향이 일치합니다. 우리 1.87에서 "
"2.13배가 논문 1.48에서 3.58배 범위 안에 들어갑니다. 둘째, 이득이 고동시성에서 커지는 것도 같습니다. 논문은 "
"96 병렬에서 격차가 최대고, 우리는 fit 미만에선 동률이다가 fit을 넘으면 역전합니다. 즉 메모리가 넉넉하면 이득이 "
"없고 과구독될 때 이득이 난다는 방향이 똑같습니다. 셋째, KV hit이 tr에서 훨씬 높은 것도 일치합니다. 논문은 "
"예측가능 워크로드에서 거의 100%인데 vLLM은 붕괴하고, 우리도 tr이 default 대비 2.3에서 3.1배입니다. 넷째, "
"decode-heavy 워크로드가 가장 크게 이기는 것도 같아서, 논문의 SWE와 우리 SWE가 둘 다 최대 이득입니다. "
"다섯째, stochastic 워크로드는 hit을 희생하고 이득이 작은데, 이건 우리 P2, P3라 아직인데 예측이 논문과 "
"같습니다. 그리고 결정적으로, 메커니즘 설명까지 같습니다. 논문도 vLLM 붕괴를 동시성이 높아 메모리가 부족할 때 "
"KV가 축출되면서 스래싱이 나기 때문이라고 설명하는데, 이게 정확히 우리가 관찰한 default 붕괴 메커니즘입니다. "
"이제 정직한 차이도 반드시 말씀드립니다. 왼쪽 아래입니다. 첫째, 하드웨어와 모델이 완전히 달라서, 우리는 32B에 "
"Pro6000 TP2인데 SYS 오버헤드까지 있고, 논문은 235B, 355B에 H100 여덟 장입니다. 그래서 절대값은 절대 비교하지 "
"않고 방향과 상대 비교만 합니다. 둘째, 우리의 k_fit-flip은 사실 논문의 확장입니다. 논문은 KV가 충분한 H100이라 "
"tr이 항상 이기지만, 우리는 KV를 4090으로 줄이면 tr이 지고 Pro6000으로 키우면 이기는 걸 보여서, 논문이 항상 "
"이기던 그 이득이 어느 KV 용량 경계, 즉 fit에서 나타나는지를 드러냈습니다. 논문의 고동시성 tr 우위를 KV 용량 "
"축으로 분해한 셈입니다. 셋째, 논문의 SOTA인 Continuum은 우리가 구현을 안 해서 vLLM에 해당하는 default 대비만 "
"했고, 논문에서 HLE의 tr이 Continuum한테 0.65배로 지는 부분은 우리 범위 밖이라 인용만 합니다. 넷째, 우리 "
"워크로드 중 SWE는 mini-SWEAgent에 SWEBench-Lite로 논문과 직접 대응하지만, TraceLab은 우리 고유 워크로드라 "
"논문엔 없습니다. 정리하면, 절대값은 비교 못 하지만 tr이 vLLM을 이기는 방향, 고동시성에서 이득이 커지는 방향, "
"KV hit을 지키며 스래싱을 피하는 메커니즘까지 논문과 일관되게 재현됐다는 게 이 슬라이드의 결론입니다.")

# ===========================================================================
# SLIDE 12 — Remaining P2/P3 roadmap
# ===========================================================================
s = slide()
title(s, "남은 실험 (P2 · P3)", BLUE, "다음은 여기 — 진행 방식·리스크")
# P2
rect(s, 0.78, 1.6, 5.85, 4.15, PANEL)
textbox(s, 1.02, 1.72, 5.4, 4.0,
        [[("P2 · ScienceAgentBench", 15, BLUE, True)],
         [("목적: duty 축의 '중간' — SWE보다 가변한 샌드박스/파이썬 실행", 11.5, INK, False)],
         [("• Deployment A(32B TP2) 재사용, OpenHands + Docker", 11.5, INK, False)],
         [("• 예측: tr 우세(SWE보다 격차 작음)", 11.5, GREEN, False)],
         [("", 5, INK, False)],
         [("⚠ 리스크: OpenHands eval 하네스에 SAB 미포함", 11.5, RED, True)],
         [("  → 하네스 이식 개발 필요(upstream 이식·충실도 확인)", 11, GRAY, False)],
         [("• 데이터셋 osunlp/ScienceAgentBench ungated 확인", 11, GRAY, False)],
         [("예상: ~8–14h GPU (하네스 개발 별도)", 11.5, INK, True)]])
# P3
rect(s, 6.85, 1.6, 5.9, 4.15, PANEL)
textbox(s, 7.09, 1.72, 5.45, 4.0,
        [[("P3 · HLE / ToolOrchestra", 15, BLUE, True)],
         [("목적: stochastic 축 — 원격 API heavy-tailed로 f(t) pause/resume 코스트모델 시험", 11.5, INK, False)],
         [("• Deployment B: 8B 오케스트레이터(GPU0)+FAISS(GPU1)", 11.5, INK, False)],
         [("• 예측: tr throughput 우세, hit는 낮음", 11.5, GREEN, False)],
         [("", 5, INK, False)],
         [("⚠ 유료 API(gpt-5 등) → 무료 GLM Flash 대체($0)", 11.5, RED, True)],
         [("  judge OFF · Tavily OFF · 로컬 FAISS retrieval", 11, GRAY, False)],
         [("• 셋업: FAISS 인덱스·conda·checkpoint·GLM 코드변경", 11, GRAY, False)],
         [("예상: ~4–8h GPU + $0(무료 한도 내)", 11.5, INK, True)]])
rect(s, 0.78, 5.9, 11.97, 0.92, CREAM)
textbox(s, 1.0, 6.0, 11.55, 0.85,
        [[("공통 제약: Continuum(논문 SOTA baseline) repo 미구현 → 전 워크로드 default vs tr만 (tr–Continuum 대비는 논문 인용).",
           11.5, INK, False)],
         [("게이트 3(P1 완료)에서 정지 중 — 백엔드 tp2serve는 가동 중, P2 승인 시 재사용 / 불필요 시 정지해 GPU 반환.",
           11, GRAY, False)]])
notes(s,
"남은 실험은 P2와 P3입니다. 왼쪽 P2는 ScienceAgentBench입니다. 목적은 duty 축의 중간 지점을 채우는 겁니다. "
"SWE가 decode-heavy로 duty가 거의 1이고 TraceLab이 prefill-heavy로 낮다면, Science는 샌드박스에서 파이썬을 "
"실행하니 그 중간의 가변성을 갖습니다. Deployment A를 그대로 재사용하고 OpenHands와 Docker를 씁니다. 예측은 "
"tr이 우세하되 SWE보단 격차가 작을 것이다입니다. 가장 큰 리스크는 OpenHands 평가 하네스에 SWE만 있고 "
"ScienceAgentBench가 빠져 있다는 점입니다. 그래서 upstream에서 하네스를 이식하는 개발이 필요하고 그 충실도를 "
"확인해야 합니다. 데이터셋 자체는 ungated로 확인했습니다. 예상 GPU 시간은 8에서 14시간에 하네스 개발이 "
"별도입니다. 오른쪽 P3는 HLE입니다. 목적은 stochastic 축인데, 원격 API 도구가 heavy-tailed로 길고 들쭉날쭉해서 "
"tr의 f(t) 지수 감쇠 pause/resume 코스트모델이 진짜 시험받는 케이스입니다. Deployment B로 8B 오케스트레이터를 "
"GPU 0번, FAISS 리트리버를 1번에 두고 A와 시간대를 분리해 돌립니다. 예측은 tr이 throughput은 이기지만 "
"적중률은 낮다입니다. 여기서 중요한 건, 논문이 gpt-5 같은 유료 API를 쓰는데 우리는 전량 무료 GLM Flash로 "
"대체해서 API 비용을 0으로 만들었다는 겁니다. judge와 Tavily를 끄고 로컬 FAISS retrieval만 씁니다. 셋업으로 "
"FAISS 인덱스, conda 환경, checkpoint 선택, GLM 코드 변경이 남아 있습니다. 예상은 4에서 8시간에 비용 0입니다. "
"공통 제약으로, 논문의 SOTA baseline인 Continuum이 repo에 구현돼 있지 않아서 전 워크로드에서 default와 tr만 "
"비교하고, tr 대 Continuum은 논문 수치를 인용합니다. 지금은 P1 완료 게이트에서 정지한 상태이고, 백엔드는 "
"가동 중이라 P2 승인하시면 바로 재사용하고 아니면 내려서 GPU를 반환할 수 있습니다.")

# ===========================================================================
# SLIDE 13 — Summary
# ===========================================================================
s = slide()
title(s, "요약", AMBER, "가설 → 두 워크로드 flip 입증 → R모델 정합 → 남은 것")
add_image(s, "tp2_kfit_flip_4090_vs_pro6000.png", 1.65, width=5.15, center=False, left=0.6)
rect(s, 6.15, 1.6, 6.6, 5.05, PANEL)
textbox(s, 6.4, 1.74, 6.15, 4.9,
        [[("① 가설 (k_fit-flip)", 13.5, BLUE, True)],
         [("4090 R<1 패 → KV↑ → R≥1 승. 워크로드·스케줄러 불변, KV 용량만 바꿔 검증.", 11.5, INK, False)],
         [("② 입증 (2 워크로드 flip)", 13.5, GREEN, True)],
         [("• TraceLab(fit≈25): C=32 tr +87% thru·2.3× hit·p95 −46%", 11, INK, False)],
         [("• SWE(fit≈58): C=64 tr +113% thru·2.8× hit·p95 −51%", 11, INK, False)],
         [("• fit=KV풀/입력이 붕괴 임계 결정(교차입증)", 11, GRAY, False)],
         [("③ R모델 정합", 13.5, GREEN, True)],
         [("tr U 0.35(4090)→0.97(Pro6000), k_fit 1.6→21.6, R 0.31→6.2. Pearson r=0.982.", 11, INK, False)],
         [("★ 정직: Pro6000은 U 포화 → tr 우위는 occupancy 아닌 hit/goodput(층위 차이).", 11, AMBER, True)],
         [("④ 남은 것", 13.5, BLUE, True)],
         [("P2 Science(duty 중간, 하네스 이식) · P3 HLE(stochastic, 무료 GLM). Continuum 미구현→논문 인용.", 11, INK, False)]])
textbox(s, 0.6, 6.95, 5.15, 0.4,
        [[("핵심 flip 한 장: 같은 TraceLab, KV ×10.4로 −34%→+87%", 10.5, GRAY, True)]])
notes(s,
"요약하겠습니다. 왼쪽 그림이 오늘의 핵심을 한 장으로 보여줍니다. 정확히 같은 TraceLab 워크로드인데, 4090에선 "
"tr이 34% 지고, KV를 10.4배로 키운 Pro6000에선 tr이 87% 이깁니다. 오른쪽에 네 가지로 정리했습니다. 첫째, "
"가설은 k_fit-flip이었습니다. 4090에서 R이 1보다 작아 지던 게 KV를 키워 R을 1 위로 올리면 이긴다, 워크로드도 "
"스케줄러도 그대로 두고 KV 용량만 바꿔 검증한다였습니다. 둘째, 이걸 두 워크로드에서 입증했습니다. TraceLab은 "
"fit 25라 C=32에서, SWE는 fit 58이라 C=64에서 tr이 각각 87%, 113% 역전했고, fit이 KV 풀 나누기 입력이라는 "
"공식으로 붕괴 임계가 갈리는 걸 교차입증했습니다. 셋째, R 모델이 정합합니다. tr의 U가 0.35에서 0.97로, k_fit이 "
"1.6에서 21.6으로, R이 0.31에서 6.2로 올라갔고 예측과 실측 U의 상관이 0.982입니다. 다만 정직하게, Pro6000은 "
"U가 포화라 tr 우위의 정체는 occupancy가 아니라 hit과 goodput이고 이건 4090과 층위가 다릅니다. 넷째, 남은 "
"건 P2 ScienceAgentBench로 duty 축 중간을 채우는 것과, P3 HLE로 stochastic 축을 무료 GLM으로 검증하는 "
"것입니다. Continuum은 미구현이라 논문 인용으로 보완합니다. 이상입니다. 질문 받겠습니다.")

prs.save(OUT)
print("SAVED:", OUT, "slides:", len(prs.slides._sldIdLst))
