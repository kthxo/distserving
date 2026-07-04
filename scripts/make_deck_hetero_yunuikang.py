#!/usr/bin/env python3
"""Build the meeting deck for the heterogeneous ThunderAgent experiments.

Analytical narrative: workload characterization (TraceLab vs homo-homo synthetic)
-> D(TraceLab, 2x4090) results explained by that characterization -> F(4090+5090)
per-backend results -> homo-homo comparison -> revised research direction.

Inserts the real PNGs from figures/. Output: slides/2026-07-04_meeting_hetero_yunuikang.pptx
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

REPO = "/home/yunuikang/yunuikang_work/distserving"
FIG = os.path.join(REPO, "figures")
OUT = os.path.join(REPO, "slides", "2026-07-04_meeting_hetero_yunuikang.pptx")

NAVY = RGBColor(0x1B, 0x2A, 0x4A)
BLUE = RGBColor(0x2E, 0x6D, 0xB4)
GRAY = RGBColor(0x4A, 0x4A, 0x4A)
GREEN = RGBColor(0x1E, 0x7A, 0x3C)
RED = RGBColor(0xB1, 0x2A, 0x2A)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT = RGBColor(0xCF, 0xDD, 0xEE)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
SW = prs.slide_width
BLANK = prs.slide_layouts[6]


def slide():
    return prs.slides.add_slide(BLANK)


def title(s, text, accent=NAVY):
    tb = s.shapes.add_textbox(Inches(0.55), Inches(0.3), Inches(12.3), Inches(0.9))
    p = tb.text_frame.paragraphs[0]
    r = p.add_run(); r.text = text
    r.font.size = Pt(26); r.font.bold = True; r.font.color.rgb = accent
    bar = s.shapes.add_shape(1, Inches(0.58), Inches(1.1), Inches(3.2), Pt(3))
    bar.fill.solid(); bar.fill.fore_color.rgb = BLUE; bar.line.fill.background()
    return s


def bullets(s, items, left=0.7, top=1.4, width=12.0, height=5.5, size=17, gap=7):
    tb = s.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tb.text_frame; tf.word_wrap = True
    for i, it in enumerate(items):
        if isinstance(it, tuple):
            lvl, txt = it[0], it[1]
            color = it[2] if len(it) > 2 else (NAVY if lvl == 0 else GRAY)
        else:
            lvl, txt, color = 0, it, NAVY
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.level = lvl; p.space_after = Pt(gap)
        r = p.add_run(); r.text = txt
        sz = size if lvl == 0 else size - 2
        r.font.size = Pt(sz); r.font.color.rgb = color
        r.font.bold = (lvl == 0)
    return s


def note(s, text, top=7.02, color=BLUE):
    tb = s.shapes.add_textbox(Inches(0.7), Inches(top), Inches(12.2), Inches(0.4))
    p = tb.text_frame.paragraphs[0]
    r = p.add_run(); r.text = text
    r.font.size = Pt(11); r.font.italic = True; r.font.color.rgb = color


def caption(s, x, w, text, top):
    cb = s.shapes.add_textbox(x, Inches(top), w, Inches(0.35))
    p = cb.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = text
    r.font.size = Pt(11); r.font.bold = True; r.font.color.rgb = NAVY


def pic(s, name, x, y, w=None, h=None):
    kw = {}
    if w: kw["width"] = Inches(w)
    if h: kw["height"] = Inches(h)
    return s.shapes.add_picture(os.path.join(FIG, name), Inches(x), Inches(y), **kw)


def dtable(s, rows, x, y, w, col_w, size=11, rowh=0.32, hi=None):
    """Compact data table. rows[0]=header. hi = set of (ri,ci) cells to color RED."""
    nr, nc = len(rows), len(rows[0])
    tb = s.shapes.add_table(nr, nc, Inches(x), Inches(y), Inches(w), Inches(rowh * nr)).table
    tb.first_row = False; tb.horz_banding = False
    for ci, cw in enumerate(col_w):
        tb.columns[ci].width = Inches(cw)
    for ri in range(nr):
        for ci in range(nc):
            cell = tb.cell(ri, ci); cell.margin_top = Pt(1); cell.margin_bottom = Pt(1)
            cell.text_frame.clear()
            p = cell.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
            run = p.add_run(); run.text = str(rows[ri][ci]); run.font.size = Pt(size)
            if ri == 0:
                run.font.bold = True; run.font.color.rgb = WHITE
                cell.fill.solid(); cell.fill.fore_color.rgb = NAVY
            else:
                cell.fill.solid(); cell.fill.fore_color.rgb = WHITE
                run.font.color.rgb = RED if (hi and (ri, ci) in hi) else NAVY
                run.font.bold = bool(hi and (ri, ci) in hi)
    return tb


# ---------------- 1. Title ----------------
s = slide()
band = s.shapes.add_shape(1, 0, Inches(2.2), SW, Inches(3.0))
band.fill.solid(); band.fill.fore_color.rgb = NAVY; band.line.fill.background()
tb = s.shapes.add_textbox(Inches(0.8), Inches(2.5), Inches(11.7), Inches(1.7))
tf = tb.text_frame; tf.word_wrap = True
r = tf.paragraphs[0].add_run()
r.text = "ThunderAgent 이종 GPU 서빙 실험"
r.font.size = Pt(40); r.font.bold = True; r.font.color.rgb = WHITE
p = tf.add_paragraph(); r = p.add_run()
r.text = "실제 워크로드(TraceLab) 특성 분석 · homo-homo 대비 · 4090+5090 이종 결과"
r.font.size = Pt(18); r.font.color.rgb = LIGHT
tb2 = s.shapes.add_textbox(Inches(0.8), Inches(5.5), Inches(11.7), Inches(0.8))
r = tb2.text_frame.paragraphs[0].add_run()
r.text = "강윤의 · 2026-07-04 · 브랜치 yunuikang/thunderagent"
r.font.size = Pt(15); r.font.color.rgb = GRAY

# ---------------- 2. Background / Goal ----------------
s = slide(); title(s, "배경 · 목표")
bullets(s, [
    (0, "ThunderAgent = program-aware KV 캐시 스케줄링 (router tr) vs naive 프록시 (default)"),
    (1, "에이전트 프로그램마다 KV를 sticky하게 유지 → 용량 초과 시 pause/resume으로 스래싱 억제 (핵심 주장)"),
    (0, "연구 지형: 2×2 (데이터 × GPU)"),
    (1, "✅ homo-homo (합성 × 2×4090) — 기존 §7·§9·§10"),
    (1, "★ 이번: D(실TraceLab×2×4090) + F(합성×이종) + G(실TraceLab×이종) — 2×2 4칸 완성", GREEN),
    (1, "🔸 보류(다음 미팅): C·D(SWE-bench 녹화), E(cross-node homo)", GRAY),
    (0, "질문: 실제 데이터·이종 GPU에서 tr의 이득이 유지되는가? 어디서 이기고 어디서 지는가?"),
])
note(s, "정직·정량·인과 관점: 워크로드 특성으로 결과를 설명한다.")

# ---------------- 3. Method ----------------
s = slide(); title(s, "방법 · 셋업")
bullets(s, [
    (0, "하드웨어 (KV 풀 = 실측 vLLM 로그)"),
    (1, "4090: 43,888 tokens = 6.03 GiB   |   5090: 89,040 tokens = 12.23 GiB  →  2.03×"),
    (1, "Qwen3-8B, KV 144 KiB/token, --max-model-len 32768, gpu-mem-util 0.92"),
    (0, "비교: router tr (ThunderAgent) vs default (naive 최소부하)"),
    (0, "워크로드"),
    (1, "D: 실제 TraceLab trace (SyFI 공개, 코딩 에이전트) — fit≤32k 서브셋 982세션"),
    (1, "F: 합성 KV-압박 워크로드 (§9와 동일, ctx=3000·turns=3)"),
    (0, "지표: throughput(prog/s), KV prefix-cache hit rate, p95 latency, 백엔드별 split·KV usage·pause"),
    (1, "각 점 3회 반복 (에러바). 측정=steady-state 구간.", GRAY),
])
note(s, "guardrail: router.py 로직 미수정(관측만), __init__.py 지연 import 픽스 유지.")

# ---------------- 4. Workload char: tokens ----------------
s = slide(); title(s, "TraceLab은 무엇이 다른가 ① — 토큰 분포")
bullets(s, [
    (0, "실제 코딩 에이전트 trace는 합성과 질적으로 다르다:"),
    (1, "input/turn: median 18,275 (p95 29k) vs 합성 ~14,558 균일 → 크고 가변적"),
    (1, "output/turn: median 144 (max 14,641) vs 합성 ~28.6 고정 → prefill-heavy, 꼬리 큼"),
], top=1.35, height=1.7, size=16)
pic(s, "char_tracelab_tokens.png", 1.15, 3.05, w=11.0)
caption(s, Inches(1.15), Inches(11.0), "input/output 토큰 분포 (빨간 점선 = homo-homo 합성 기준)", 6.65)

# ---------------- 5. Workload char: lifetime + breakdown ----------------
s = slide(); title(s, "TraceLab은 무엇이 다른가 ② — lifetime · turn 분해")
bullets(s, [
    (0, "prefill-heavy + KV locality: turn0만 cold prefill 1.89s, 이후 warm 0.40s (§10과 동일 패턴)"),
    (1, "프로그램 lifetime median 34.6s (c=1). tool 시간이 실제로 큼 (median 0.05s, p95 30s).", GRAY),
], top=1.35, height=1.3, size=16)
pic(s, "char_tracelab_lifetime.png", 0.5, 2.85, w=6.2)
caption(s, Inches(0.5), Inches(6.2), "프로그램 lifetime 분포", 6.7)
pic(s, "char_tracelab_turn_breakdown.png", 6.95, 2.75, w=6.0)
caption(s, Inches(6.95), Inches(6.0), "turn별 prefill/decode/tool (c=1)", 6.7)

# ---------------- 6. Workload char: KV (the cause) ----------------
s = slide(); title(s, "TraceLab은 무엇이 다른가 ③ — KV 필요량 (D 결과의 원인)")
bullets(s, [
    (0, "프로그램 1개 peak KV = median 2.87 GiB (p95 4.35) — 합성 2.01 GiB보다 크고 가변"),
    (1, "→ 4090 풀(6.03 GiB)에 ~2.1개, 5090(12.23)에 ~4.3개만 동시 적재", RED),
    (1, "이 '프로그램이 KV에 육박' 사실이 D·F 결과를 지배한다 (다음 슬라이드).", NAVY),
], top=1.35, height=1.7, size=16)
pic(s, "char_tracelab_kv.png", 3.6, 2.75, h=3.85)
caption(s, Inches(3.35), Inches(6.6), "프로그램별 peak KV vs 4090/5090 풀 (수직선)", 6.65)

# ---------------- 7. D result 1: hit rate ----------------
s = slide(); title(s, "D 결과 ① — KV hit rate: tr이 캐시를 지킨다 (실데이터 재현)")
bullets(s, [
    (0, "실제 TraceLab × 2×4090"),
    (1, "tr: 0.77~0.80 부하 무관 유지  |  default: 0.82 → 0.026 붕괴", NAVY),
    (1, "c=48에서 30× 차이 → 스래싱 억제 실데이터 재현", GREEN),
], left=0.55, top=1.35, width=5.4, height=1.6, size=15)
dtable(s, [
    ["C", "tr hit", "default hit"],
    ["2", "0.823", "0.823"],
    ["4", "0.786", "0.611"],
    ["8", "0.800", "0.210"],
    ["16", "0.799", "0.047"],
    ["32", "0.774", "0.032"],
    ["48", "0.772", "0.026"],
], x=0.7, y=3.05, w=4.6, col_w=[1.2, 1.7, 1.7], size=12, rowh=0.30,
   hi={(4, 2), (5, 2), (6, 2), (7, 2)})
caption(s, Inches(0.7), Inches(4.6), "KV hit rate, C=2~48 (3회 평균)", 5.3)
pic(s, "hetero_homo_tracelab_hit_rate.png", 5.9, 1.75, w=7.1)

# ---------------- 8. D result 2: the reversal ----------------
s = slide(); title(s, "D 결과 ② — 반전: throughput·p95는 tr이 불리")
bullets(s, [
    (0, "같은 실험인데 throughput/latency는 default가 더 좋다 (반전):"),
    (1, "원인=슬6: 프로그램이 4090 KV에 육박(~2개). tr은 초과분 pause→병렬성 희생, default는 스래싱하며 다 돌림", NAVY),
    (0, "합성 §9(tr +57%)와 정반대 → tr 이득은 '프로그램/KV 비율'에 좌우됨.", NAVY),
], left=0.55, top=1.35, width=6.1, height=1.9, size=14)
dtable(s, [
    ["C", "thru tr", "thru def", "p95 tr", "p95 def"],
    ["2", "0.048", "0.048", "110s", "110s"],
    ["4", "0.084", "0.093", "132s", "113s"],
    ["8", "0.078", "0.120", "184s", "153s"],
    ["16", "0.073", "0.107", "595s", "289s"],
    ["32", "0.069", "0.108", "660s", "418s"],
    ["48", "0.067", "0.102", "727s", "481s"],
], x=0.55, y=3.25, w=6.2, col_w=[0.8, 1.35, 1.35, 1.35, 1.35], size=12, rowh=0.30,
   hi={(3, 1), (4, 1), (5, 1), (6, 1), (3, 3), (4, 3), (5, 3), (6, 3)})
caption(s, Inches(0.55), Inches(6.2), "throughput(p/s)·p95, C=2~48 — tr(빨강)이 열세", 5.6)
pic(s, "hetero_homo_tracelab_throughput.png", 7.0, 1.7, w=6.1)
caption(s, Inches(7.0), Inches(6.1), "throughput vs concurrency", 6.35)

# ---------------- 9. F result 1: global ----------------
s = slide(); title(s, "F 결과 ① — 이종 4090+5090, 전역: tr이 throughput·p95 모두 우세")
bullets(s, [
    (0, "합성 KV-압박 워크로드, 4090+5090 (F의 concurrency 축 = 8·16·24·32·48)"),
    (1, "고부하 throughput tr≈2×, hit 0.67 vs 0.02, p95도 tr이 절반 이하(c48 70 vs 149s)", GREEN),
    (0, "합성에선 이종에서도 tr 우세 (실데이터 D와 대조; D는 tr이 p95 열세였음)."),
], left=0.55, top=1.3, width=6.3, height=1.9, size=14)
pic(s, "homo_hetero_throughput.png", 7.35, 1.5, w=5.5)
dtable(s, [
    ["C", "thru tr", "thru def", "hit tr", "hit def", "p95 tr", "p95 def"],
    ["8", "0.67", "0.62", "0.56", "0.23", "20.6s", "25.7s"],
    ["16", "0.64", "0.34", "0.67", "0.03", "34.9s", "52.2s"],
    ["24", "0.63", "0.32", "0.67", "0.02", "48.9s", "77.3s"],
    ["32", "0.64", "0.35", "0.67", "0.03", "55.1s", "99.0s"],
    ["48", "0.64", "0.32", "0.67", "0.02", "70.2s", "149.0s"],
], x=0.4, y=5.35, w=12.5, col_w=[0.9, 1.9, 1.9, 1.9, 1.9, 1.95, 2.05], size=12, rowh=0.28,
   hi={(2, 2), (3, 2), (4, 2), (5, 2), (2, 4), (3, 4), (4, 4), (5, 4)})
caption(s, Inches(0.4), Inches(12.5), "F 전역 지표 C=8~48 (3회 평균) — default hit·throughput 붕괴(빨강)", 5.05)

# ---------------- 10. F result 2: per-backend (core) ----------------
s = slide(); title(s, "F 결과 ② — 백엔드별 (핵심): 누가 스래싱하나")
bullets(s, [
    (0, "default가 작은 4090을 혹사 (c8 hit 0.08, 재프리필 ~4×)", RED),
    (0, "tr은 4090·5090 둘 다 ~0.67 균형, 큰 5090에 더 라우팅(1:1.6)", GREEN),
], left=0.55, top=1.35, width=5.6, height=1.3, size=14)
dtable(s, [
    ["지표", "tr 4090", "tr 5090", "def 4090", "def 5090"],
    ["hit (c=8)", "0.48", "0.64", "0.08", "0.67"],
    ["hit (c≥16)", "0.67", "0.67", "0.02", "0.02"],
    ["재프리필 M (c≥16)", "0.80", "1.29", "9.2", "2.2"],
], x=0.5, y=2.85, w=5.7, col_w=[1.7, 1.0, 1.0, 1.0, 1.0], size=12,
   hi={(1, 3), (2, 3), (3, 3)})
caption(s, Inches(0.5), Inches(5.7), "백엔드별 수치 (빨강=default 4090, 혹사)", 4.55)
pic(s, "homo_hetero_perbackend_hitrate.png", 6.35, 2.1, w=6.7)
caption(s, Inches(6.35), Inches(6.7), "백엔드별 hit rate: default 4090만 붕괴", 6.5)

# ---------------- 11. F result 3: hypothesis ----------------
s = slide(); title(s, "F 결과 ③ — 가설 검증: H1 반증")
bullets(s, [
    (0, "사전 가설 H1: 'tr의 절대-토큰 균형이 작은 4090을 먼저 포화'"),
    (0, "실측: tr 4090·5090 hit 유사(≈0.67) → 사전 등록 반증 조건 충족 → H1 기각", RED),
    (1, "소형-GPU 혹사는 default 병리. 단 tr은 큰 5090을 다 못 씀 ↓", NAVY),
], left=0.55, top=1.35, width=6.1, height=1.7, size=14)
dtable(s, [
    ["", "4090", "5090", "비율"],
    ["KV 풀 (GiB)", "6.03", "12.23", "1 : 2.03"],
    ["tr split (q, M)", "0.80", "1.29", "1 : 1.6"],
], x=0.6, y=3.3, w=6.0, col_w=[1.9, 1.2, 1.2, 1.7], size=13,
   hi={(2, 3)})
caption(s, Inches(0.6), Inches(4.55), "tr split(1:1.6) < 용량비(1:2.03) → 5090 과소활용", 4.35)
pic(s, "homo_hetero_perbackend_reprefill.png", 7.05, 1.85, w=6.0)
caption(s, Inches(7.05), Inches(6.0), "백엔드별 재프리필: default 4090이 ~4배", 6.2)

# ---------------- 12. G result 1: recovery vs D ----------------
s = slide(); title(s, "G 결과 ① — 실 TraceLab × 이종: tr throughput 회복 (vs D)")
bullets(s, [
    (0, "실데이터를 4090+5090으로: D(2×4090)에서 tr이 잃은 throughput이 회복되나?"),
    (1, "tr throughput D 대비 1.6~1.7× 회복 (D 0.067~0.078 → G 0.115~0.126)", GREEN),
    (1, "default와 격차 34%→8%로 축소(c48) — 단 완전 역전은 아님", NAVY),
    (0, "hit rate는 tr 압승 유지(0.68~0.83 vs 0.03). p95는 tr 여전히 열세(D 패턴)."),
], left=0.55, top=1.3, width=6.3, height=2.0, size=14)
dtable(s, [
    ["C", "D tr", "G tr", "G def", "hit tr", "hit def"],
    ["8", "0.078", "0.126", "0.154", "0.77", "0.39"],
    ["16", "0.073", "0.116", "0.143", "0.74", "0.07"],
    ["32", "0.069", "0.116", "0.132", "0.73", "0.03"],
    ["48", "0.067", "0.115", "0.125", "0.68", "0.03"],
], x=0.5, y=3.5, w=6.3, col_w=[0.7, 1.1, 1.1, 1.1, 1.15, 1.15], size=12, rowh=0.30,
   hi={(1, 5), (2, 5), (3, 5), (4, 5)})
caption(s, Inches(0.5), Inches(6.3), "throughput D tr→G tr 회복 / default hit 붕괴(빨강)", 5.2)
pic(s, "hetero_hetero_hitrate.png", 7.1, 1.7, w=6.0)
caption(s, Inches(7.1), Inches(6.0), "G 전역 hit rate: tr 유지 vs default 붕괴", 6.35)

# ---------------- 13. G result 2: per-backend + three-way ----------------
s = slide(); title(s, "G 결과 ② — 백엔드별 + 세 방향 결론")
bullets(s, [
    (0, "F 패턴이 실데이터에서도 유지:"),
    (1, "default가 작은 4090 최악 붕괴 (c48 4090 hit 0.03 vs 5090 0.06)", RED),
    (1, "tr은 4090·5090 균형 (둘 다 ~0.67~0.87)", GREEN),
    (0, "단 tr split ~1:1 ≪ 용량비 1:2.03 → 실데이터에서 5090 과소활용 (F 1:1.6보다 큼)", NAVY),
    (1, "그럼에도 throughput +72%(용량 +51% 대비 초선형) → 용량 비례로 5090 더 쓰면 상단↑", NAVY),
], left=0.55, top=1.3, width=5.7, height=2.7, size=14)
dtable(s, [
    ["hit (c=48)", "tr", "default"],
    ["4090", "0.69", "0.03"],
    ["5090", "0.67", "0.06"],
], x=0.6, y=4.5, w=4.4, col_w=[1.6, 1.4, 1.4], size=13, rowh=0.32, hi={(1, 2), (2, 2)})
caption(s, Inches(0.6), Inches(4.4), "백엔드별 hit (c=48): default 4090 최악 붕괴", 5.55)
pic(s, "hetero_hetero_perbackend_hitrate.png", 6.35, 2.0, w=6.8)
caption(s, Inches(6.35), Inches(6.8), "tr 균형 vs default 4090 최악 붕괴", 6.6)

# ---------------- 14. Comparison table (2x2) ----------------
s = slide(); title(s, "종합: 2×2 매트릭스 (데이터 × GPU) — 4칸 완성")
M = [
    ["", "2×4090 (homo GPU)", "4090+5090 (hetero GPU)"],
    ["합성 데이터", "§9: tr thru +57% · hit 압승", "F: tr thru +100% · hit·p95 우위"],
    ["실제 TraceLab", "D: tr thru −34% · hit 압승(30×)", "G: tr thru −8%(회복) · hit 압승"],
]
tb = s.shapes.add_table(3, 3, Inches(0.7), Inches(1.65), Inches(11.9), Inches(2.3)).table
tb.columns[0].width = Inches(2.5); tb.columns[1].width = Inches(4.5); tb.columns[2].width = Inches(4.9)
for ri in range(3):
    for ci in range(3):
        cell = tb.cell(ri, ci); cell.text_frame.clear()
        p = cell.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
        run = p.add_run(); run.text = M[ri][ci]; run.font.size = Pt(14)
        if ri == 0 or ci == 0:
            run.font.bold = True; run.font.color.rgb = WHITE
            cell.fill.solid(); cell.fill.fore_color.rgb = NAVY
        else:
            cell.fill.solid(); cell.fill.fore_color.rgb = WHITE; run.font.color.rgb = NAVY
bullets(s, [
    (0, "KV hit rate: tr은 4칸 모두 압승 (스래싱 억제 견고)."),
    (0, "Throughput: 프로그램이 KV에 육박하는 실데이터(D)에선 tr이 지고, 여유·이종이면 이기거나 회복(§9·F·G)."),
    (1, "→ tr 이득은 '프로그램/KV 비율'·'GPU 용량'에 좌우. 이종 5090이 실데이터 적자를 34%→8%로 축소.", NAVY),
], top=4.5, height=2.3, size=15)

# ---------------- 13. Implication / next ----------------
s = slide(); title(s, "시사점 · 다음 방향")
bullets(s, [
    (0, "핵심 발견"),
    (1, "① tr의 스래싱 억제(KV hit)는 실데이터·이종에서 견고히 재현."),
    (1, "② 이종에서 소형-GPU 혹사는 default의 병리 — tr은 균형 유지(H1 반증)."),
    (1, "③ 그러나 tr은 큰 5090을 과소활용 (split 1:1.6 < 용량 1:2.03, +31% < +51%).", RED),
    (0, "다음 과제: 용량 비례 라우팅"),
    (1, "목표를 재정의 — '소형 GPU 부하 경감'이 아니라 '대형 GPU 여유 활용으로 throughput 상단 올리기'.", GREEN),
    (1, "용량(가능하면 속도·대역폭)에 비례해 신규 프로그램 배정 → 5090 활용률↑ 검증.", NAVY),
])
note(s, "router.py의 신규-프로그램 배정 로직을 용량 비례로 확장 (이번엔 관측만, 근거 확보 완료).")

# ---------------- 14. Limitations / TODO ----------------
s = slide(); title(s, "한계 · TODO")
bullets(s, [
    (0, "측정 신뢰도: 각 점 3회 (반복 간 편차, 특히 tr pause 타이밍) → 반복·에러바 보강."),
    (0, "워크로드: F는 합성(§9). 실데이터 이종(TraceLab × 4090+5090)은 미실행."),
    (0, "지표 근사: split을 prefix-cache queries(재프리필 포함)로 근사 — 순수 라우팅 프로그램 수와 다름."),
    (0, "데이터 편향: fit≤32k 서브셋(982세션)은 짧은 세션 편향 — 92.5% turn이 32k 초과라 제외됨."),
    (0, "보류: C·D(SWE-bench 녹화), E(cross-node homo) — 다음 미팅 이후."),
    (0, "다음: 용량 비례 라우팅 구현 → D·F 재실행으로 이득 검증."),
], size=16)

# ---------------- speaker notes (대본체, 청중=지도교수) ----------------
NOTES = [
    # 1 title
    "안녕하세요. ThunderAgent를 이종 GPU 환경에서 돌린 실험 결과를 말씀드리겠습니다. "
    "오늘 순서는 세 부분입니다. 먼저 실제 코딩 에이전트 로그인 TraceLab 워크로드가 기존 합성 "
    "워크로드와 뭐가 다른지 특성을 보고, 그 특성이 2×4090 실데이터 실험 결과를 어떻게 설명하는지, "
    "마지막으로 4090과 5090을 섞은 이종 실험 결과를 보여드립니다. "
    "핵심 메시지는 'tr이 KV 캐시는 확실히 지키는데, 그게 항상 처리량으로 이어지진 않고 워크로드와 "
    "GPU 구성에 달렸다'입니다.",
    # 2 background
    "ThunderAgent가 푸는 문제부터요. 에이전트는 한 작업을 여러 턴에 걸쳐 처리하는데, 턴 사이에 툴을 "
    "호출하는 동안 그 프로그램의 KV 캐시—지금까지 계산해둔 문맥—가 GPU 메모리에서 밀려나 축출될 수 "
    "있습니다. 그러면 다음 턴에 그 문맥을 처음부터 다시 계산해야 하는데, 이걸 재프리필, 이게 심해지는 "
    "걸 스래싱이라고 부릅니다. tr 라우터는 프로그램 단위로 관리해서 활성 프로그램들의 KV가 GPU 용량 "
    "안에 들어오도록 유지하고, 초과하면 잠시 멈췄다 재개시켜 이 스래싱을 막습니다. 저희는 이걸 데이터 축"
    "(합성 대 실제)과 GPU 축(동일 대 이종) 둘로 나눠 봤고, 오늘은 나머지 세 칸(D·F·G)을 채워 "
    "2×2 매트릭스를 완성한 겁니다.",
    # 3 method
    "셋업입니다. GPU는 4090과 5090을 쓰는데, 실제 KV 캐시 풀 크기를 vLLM 로그에서 뽑아보니 4090은 "
    "43,888토큰으로 6.03기가바이트, 5090은 89,040토큰 12.23기가바이트로 딱 2.03배였습니다. 이 2배 "
    "용량 차이가 뒤 이종 실험의 핵심 변수입니다. 비교는 ThunderAgent 스케줄러인 tr과, 단순히 부하 "
    "적은 쪽으로 보내는 default 프록시 둘입니다. 워크로드는 D 실험이 실제 TraceLab 트레이스, F 실험이 "
    "기존과 같은 합성 부하고요. 처리량·KV 히트율·p95 지연에 더해 백엔드별 지표까지 각 조건 3번씩 반복 "
    "측정했습니다.",
    # 4 char tokens
    "여기서부터 왜 TraceLab이 특별한지 세 장에 걸쳐 깔겠습니다. 실제 코딩 에이전트 로그는 합성과 질적"
    "으로 다릅니다. 한 턴 입력이 중앙값 18,275토큰, 상위 5%는 2만9천까지 가는데, 기존 합성은 1만4천5백 "
    "정도로 균일했습니다. 반면 출력은 중앙값 144토큰으로 짧습니다—합성은 28개 고정이었고요. 즉 입력은 "
    "크고 들쭉날쭉, 출력은 짧다—전형적인 prefill-heavy, 계산 비용이 입력 처리 쪽에 쏠린 워크로드입니다. "
    "그래서 KV 캐시를 얼마나 잘 재사용하느냐가 성능을 좌우합니다.",
    # 5 char lifetime/breakdown
    "오른쪽 턴별 분해 그림을 보시면, 첫 턴만 prefill 시간이 1.89초로 길고 그다음 턴부터는 0.40초로 확 "
    "줄어듭니다. 첫 턴은 큰 입력을 처음부터 다 계산하지만, 이후 턴은 같은 세션의 앞부분 KV를 재사용하기 "
    "때문입니다—이게 바로 KV locality이고, 기존 합성 실험에서 본 패턴과 똑같습니다. 왼쪽은 프로그램 하나가 "
    "사는 시간인데 중앙값 34.6초, 그리고 툴 실행 시간이 실제로 꽤 큽니다. 요점은 '앞 문맥을 재사용하니 그 "
    "KV를 지키는 게 중요하다'는 겁니다.",
    # 6 char KV (cause)
    "이 슬라이드가 뒤 결과의 원인이라 제일 중요합니다. 프로그램 하나가 최대로 차지하는 KV 메모리가 "
    "중앙값 2.87기가바이트, 상위 5%가 4.35기가입니다. 4090 풀이 6기가밖에 안 되니까 한 GPU에 프로그램이 "
    "딱 2개 정도밖에 동시에 안 올라갑니다. 5090도 4개 정도고요. 기존 합성은 프로그램당 2기가로 더 작고 "
    "균일했는데 실제는 더 크고 가변적입니다. 이 '프로그램 하나가 GPU 용량에 육박한다'는 사실을 기억해두시면 "
    "다음에 나올 D 실험의 반전이 자연스럽게 이해됩니다.",
    # 7 D1 hit rate
    "이제 실제 데이터로 2×4090에서 돌린 결과입니다. 파란선 tr은 부하가 아무리 올라도 KV 히트율을 0.77에서 "
    "0.80으로 유지합니다. 반면 주황색 default는 0.82에서 시작해 0.026까지 무너집니다. 부하가 오르면 "
    "프로그램들이 서로의 KV 캐시를 밀어내서 매 턴 처음부터 다시 계산하는 스래싱에 빠지는 거죠. 동시 48개 "
    "기준으로 tr이 default보다 히트율이 30배 높습니다. 논문이 주장한 'program-aware 스케줄링이 캐시 스래싱을 "
    "막는다'를 저희가 합성이 아니라 실제 데이터로 재현한 겁니다.",
    # 8 D2 reversal (careful)
    "그런데 여기서 정직하게 말씀드릴 반전이 있습니다. 캐시는 tr이 지켰는데 정작 처리량은 tr이 더 낮습니다—"
    "동시 48개에서 tr 0.067 대 default 0.102, p95 지연도 727초 대 481초로 tr이 나쁩니다. 왜냐면 아까 "
    "슬라이드 6에서 봤듯이 프로그램 하나가 4090 KV를 거의 다 먹어서 2개밖에 못 올라가는데, tr은 용량을 넘는 "
    "프로그램을 잠시 멈춰 세우거든요. 그러면 캐시는 지키지만 동시에 도는 프로그램 수가 줄어 GPU가 놀고 "
    "대기줄이 길어집니다. default는 스래싱하면서도 다 밀어넣어 돌리니 벽시계 기준 처리량은 오히려 높고요. "
    "결론은 '캐시 보호가 항상 처리량으로 이어지진 않는다, 특히 프로그램이 GPU 용량에 육박할 때는'입니다. "
    "예상 질문 '그럼 tr이 나쁜 거냐?'—아닙니다, tr은 캐시를 지켰고, 이건 작은 4090에 프로그램이 너무 큰 특수 "
    "상황이라 오히려 더 큰 KV를 가진 이종 GPU가 필요하다는 다음 이야기로 이어집니다.",
    # 9 F1 global
    "이제 4090에 5090을 붙인 이종 실험입니다. 워크로드는 다시 합성으로 통제했고요. 전역 처리량을 보면 "
    "고부하에서 tr이 0.64로 default 0.32의 약 2배입니다. 히트율도 0.67 대 0.02로 압도적이고요. 즉 프로그램 "
    "크기가 적당한 합성 워크로드에서는 이종 GPU에서도 tr이 확실히 이깁니다—방금 본 실데이터 D와 대조되는 "
    "지점입니다.",
    # 10 F2 per-backend (core)
    "이게 이종 실험의 핵심입니다. 백엔드를 4090과 5090으로 나눠서 봤어요. default를 보면 작은 4090을 "
    "파국적으로 혹사시킵니다. 동시 8개에서 이미 4090 히트율이 0.08로 스래싱인데 5090은 0.67로 멀쩡합니다. "
    "고부하에선 4090이 재프리필을 5090의 약 4배—9.2백만 대 2.2백만 토큰—처리하고요. 반면 tr은 4090과 5090 "
    "둘 다 0.67로 균형을 맞추고, 오히려 큰 5090에 일을 더 보냅니다—대략 1대 1.6 비율로요. 그림에서 빨간 "
    "점선인 default의 4090만 바닥으로 떨어지는 게 한눈에 보이실 겁니다.",
    # 11 F3 H1 refute (honest)
    "여기가 두 번째 정직 포인트입니다. 저희는 원래 가설로 'tr이 절대 토큰 양만 맞추니까 작은 4090을 먼저 "
    "포화시킬 것'이라고 세웠고, 심지어 이게 틀렸다고 볼 반증 조건—두 GPU 히트율이 비슷하게 나오면 가설 "
    "기각—을 미리 정해놨습니다. 그런데 실측에서 tr의 4090·5090 히트율이 둘 다 0.67로 비슷했어요. 그래서 이 "
    "가설은 기각·수정됐습니다. 우리가 걱정했던 tr의 문제는 실제로 없었고, 소형 GPU를 혹사시키는 건 오히려 "
    "default의 병리였던 거죠. 예상 질문 '그럼 tr이 완벽하냐?'—아닙니다. tr은 큰 GPU를 다 활용하진 못하는데 "
    "그게 다음 슬라이드입니다.",
    # 12 G1 recovery vs D
    "이제 2×2의 마지막 칸입니다. 실제 TraceLab 데이터를 4090과 5090 이종에서 돌렸어요. 핵심 질문은, D에서 "
    "tr이 잃었던 처리량이 더 큰 5090을 붙이면 회복되느냐였습니다. 결과는 회복됩니다—tr 처리량이 D 대비 1.6에서 "
    "1.7배로 올랐고(0.067→0.115), default와의 격차도 34%에서 8%로 좁혀졌습니다. 다만 완전히 역전하진 못했고, "
    "히트율은 여전히 tr 압승(0.68~0.83 대 0.03), p95는 tr이 조금 열세입니다. 즉 큰 GPU가 tr의 실데이터 약점을 "
    "상당히 메워줬다는 게 이 칸의 메시지입니다.",
    # 13 G2 per-backend + three-way
    "백엔드별로 보면 합성 이종(F)에서 봤던 패턴이 실제 데이터에서도 그대로입니다—default는 작은 4090을 가장 "
    "심하게 태우고(c48에서 4090 히트 0.03 대 5090 0.06), tr은 두 GPU를 0.67에서 0.87로 균형 있게 유지합니다. "
    "한 가지 차이는, F에선 tr이 큰 5090에 일을 1.6배 더 보냈는데 실제 데이터에선 거의 1대 1로 5090을 덜 "
    "활용한다는 점입니다. 그런데도 처리량이 용량 증가분보다 더 많이 올랐다는 건 5090에 아직 여유가 있다는 "
    "뜻이라, 용량 비례로 5090에 더 밀면 default를 넘어설 여지가 있습니다—다음 과제로 이어집니다.",
    # 14 comparison (2x2)
    "이제 2×2 네 칸을 다 채웠습니다. 표로 정리하면, 합성에 동일 GPU는 tr 처리량 +57%, 합성에 이종은 +100%, "
    "실데이터에 동일 GPU는 -34%, 실데이터에 이종은 -8%로 회복입니다. KV 히트율은 네 칸 모두 tr 압승이고요. "
    "그러니까 tr의 스래싱 억제 능력 자체는 항상 견고한데, 처리량 이득은 프로그램이 GPU KV에 얼마나 육박하는지와 "
    "GPU 용량 구성에 달려 있다—이게 최종 결론입니다. 특히 실데이터에서 큰 5090이 tr의 적자를 34%에서 8%로 "
    "줄였다는 게 이종의 의미입니다.",
    # 13 implication/next
    "그럼 다음에 뭘 할 거냐. tr이 5090에 일을 더 보내긴 하는데 그 비율이 1대 1.6이었습니다. 실제 용량비는 1대 "
    "2.03인데 말이죠. 즉 tr이 큰 5090의 여유를 다 못 씁니다—처리량이 용량을 51% 늘렸는데 31%밖에 안 올랐어요. "
    "그래서 다음 과제는 용량 비례 라우팅입니다. 방향을 다시 잡자면 '작은 GPU 혹사를 고치는 것'이 아니라 '큰 "
    "GPU 활용을 끌어올려 처리량 상단을 높이는 것'입니다. 신규 프로그램을 GPU 용량에 비례해서—가능하면 속도·"
    "대역폭까지 반영해서—배정하도록 라우터를 확장하는 게 계획입니다.",
    # 14 limitations
    "마지막으로 한계도 솔직히 말씀드립니다. 각 점을 3번만 반복해서 tr의 pause 타이밍에 따른 편차가 남아 "
    "있고, F 실험은 합성 워크로드라 실제 분포와 다릅니다. 백엔드별 부하를 prefix-cache 쿼리 수로 근사했는데 "
    "이건 재프리필이 섞여서 순수 라우팅된 프로그램 수와는 다릅니다. 또 D의 데이터는 32k 이하로 맞춘 "
    "서브셋이라—전체 턴의 92.5%가 32k를 넘어 제외됐거든요—짧은 세션 쪽 편향이 있습니다. SWE-bench 녹화와 "
    "cross-node 실험은 다음 미팅 이후로 미뤘고, 다음 단계는 용량 비례 라우팅을 구현해 D와 F를 다시 돌려 "
    "검증하는 겁니다.",
]
for _sl, _txt in zip(prs.slides, NOTES):
    _sl.notes_slide.notes_text_frame.text = _txt

prs.save(OUT)
print("saved:", OUT, "| slides:", len(prs.slides._sldIdLst), "| notes:", len(NOTES))
