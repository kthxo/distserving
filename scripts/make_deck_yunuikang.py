#!/usr/bin/env python3
"""Build the meeting deck (meeting_260702.pptx) for the ThunderAgent reproduction.

Real measured numbers only; TBD where not measured. Graphs from figures/ are
embedded on the stage-2 results slide.
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

REPO = "/home/yunuikang/yunuikang_work/distserving"
FIG = os.path.join(REPO, "figures")
OUT = os.path.join(REPO, "meeting_260702.pptx")

NAVY = RGBColor(0x1F, 0x3A, 0x5F)
BLUE = RGBColor(0x1F, 0x77, 0xB4)   # tr
ORANGE = RGBColor(0xD6, 0x5F, 0x00) # default
GRAY = RGBColor(0x44, 0x44, 0x44)
LIGHT = RGBColor(0xF2, 0xF5, 0xF9)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
SW = prs.slide_width


def slide():
    return prs.slides.add_slide(BLANK)


def _set_runs(p, text, size, color, bold_default=False):
    """Parse **bold** fragments into runs."""
    parts = text.split("**")
    for i, seg in enumerate(parts):
        if seg == "":
            continue
        r = p.add_run()
        r.text = seg
        r.font.size = Pt(size)
        r.font.color.rgb = color
        r.font.bold = bold_default or (i % 2 == 1)


def title(s, text, accent=NAVY):
    tb = s.shapes.add_textbox(Inches(0.55), Inches(0.35), Inches(12.2), Inches(0.9))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run(); r.text = text
    r.font.size = Pt(28); r.font.bold = True; r.font.color.rgb = accent
    # accent underline bar
    bar = s.shapes.add_shape(1, Inches(0.58), Inches(1.18), Inches(3.2), Pt(3))
    bar.fill.solid(); bar.fill.fore_color.rgb = accent; bar.line.fill.background()
    return s


def bullets(s, items, left=0.7, top=1.5, width=12.0, height=5.4, size=18, gap=6):
    """items: list of (text, level). level 0/1/2. Supports **bold**."""
    tb = s.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tb.text_frame; tf.word_wrap = True
    first = True
    for text, lvl in items:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.level = lvl
        p.space_after = Pt(gap)
        bullet = "•  " if lvl == 0 else ("–  " if lvl == 1 else "·  ")
        sz = size if lvl == 0 else (size - 2 if lvl == 1 else size - 3)
        col = GRAY
        # leading bullet run (no bold parsing on the marker)
        rb = p.add_run(); rb.text = bullet
        rb.font.size = Pt(sz); rb.font.color.rgb = NAVY if lvl == 0 else col
        _set_runs(p, text, sz, col)
    return tb


def note(s, text, top=6.95, color=BLUE):
    tb = s.shapes.add_textbox(Inches(0.7), Inches(top), Inches(12.0), Inches(0.4))
    p = tb.text_frame.paragraphs[0]
    r = p.add_run(); r.text = text
    r.font.size = Pt(12); r.font.italic = True; r.font.color.rgb = color


# ---------------------------------------------------------------- 1 title
s = slide()
band = s.shapes.add_shape(1, 0, Inches(2.3), SW, Inches(2.9))
band.fill.solid(); band.fill.fore_color.rgb = NAVY; band.line.fill.background()
tb = s.shapes.add_textbox(Inches(0.8), Inches(2.55), Inches(11.7), Inches(1.6))
tf = tb.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]
r = p.add_run(); r.text = "ThunderAgent 재현 실험"
r.font.size = Pt(40); r.font.bold = True; r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
p2 = tf.add_paragraph()
r = p2.add_run(); r.text = "Homogeneous baseline 재현 → Heterogeneous 방향 논의"
r.font.size = Pt(20); r.font.color.rgb = RGBColor(0xCF, 0xDD, 0xEE)
tb2 = s.shapes.add_textbox(Inches(0.8), Inches(5.5), Inches(11.7), Inches(0.8))
p = tb2.text_frame.paragraphs[0]
r = p.add_run(); r.text = "강윤의  ·  2026-07-02  ·  격주 미팅"
r.font.size = Pt(16); r.font.color.rgb = GRAY

# ---------------------------------------------------------------- 2 background
s = slide(); title(s, "배경: 에이전트 서빙은 왜 기존과 다른가")
bullets(s, [
    ("기존 채팅형 LLM: 요청 1개 → 리즈닝 1회 → 끝. **스케줄 단위 = 요청**", 0),
    ("에이전트(ReAct): 리즈닝 ↔ 툴콜을 여러 턴 반복. **스케줄 단위 = 프로그램(세션 전체)**", 0),
    ("여기서 두 가지 특성이 새로 생긴다:", 0),
    ("툴콜 중에는 GPU가 노는 **‘버블’** 이 생김 (자원 특성이 리즈닝과 다름)", 1),
    ("멀티턴이라 **KV 캐시가 턴마다 유기적으로 누적** → 매 턴 새 부분만 프리필(부분 프리필)", 1),
    ("→ 요청 하나씩 보면 안 되고, **프로그램 전체를 통으로 관리**해야 함", 0),
], top=1.6)
note(s, "핵심: 멀티턴 KV 누적 + 툴콜 버블이 기존 서빙 가정과 다르다")

# ---------------------------------------------------------------- 3 problem
s = slide(); title(s, "ThunderAgent가 푸는 문제")
bullets(s, [
    ("멀티 인스턴스 라우팅의 근본 트레이드오프:", 0),
    ("**KV Locality**: 한 프로그램은 같은 인스턴스로 고정해야 KV 재사용 (아니면 재프리필)", 1),
    ("**Load Balancing**: 클러스터 전체는 골고루 써야 throughput 최대", 1),
    ("→ 둘이 상충. 이걸 어떻게 조율해 라우팅하느냐가 연구 핵심", 1),
    ("ThunderAgent: **프로그램 단위 + capacity-aware 스케줄링**으로 KV 캐시 스래싱을 방지", 0),
    ("우리 비교축 (라우터 모드):", 0),
    ("**tr** = program-aware capacity scheduling (논문 핵심)", 1),
    ("**default** = 단순 최소부하 프록시 (naive baseline)", 1),
], top=1.55)

# ---------------------------------------------------------------- 4 goal
s = slide(); title(s, "이번 작업의 목표")
bullets(s, [
    ("논문(ICML 2026)의 경향을 **우리 랩 GPU에서 재현**한다", 0),
    ("핵심 질문:", 0),
    ("tr이 default보다 **KV hit rate·throughput을 더 잘 지키는가?**", 1),
    ("부하를 올릴 때 **KV 스래싱으로 성능이 꺾이는 지점**이 논문처럼 나타나는가?", 1),
    ("지금 단계는 **homogeneous(동일 GPU) baseline**", 0),
    ("→ 최종 목표인 **heterogeneous(서로 다른 GPU)** 로 가기 위한 발판", 1),
], top=1.7)
note(s, "‘무엇을 했다’가 아니라, 관찰이 heterogeneous로 넘어가는 근거가 되는지가 핵심")

# ---------------------------------------------------------------- 5 setup
s = slide(); title(s, "실험 구성")
bullets(s, [
    ("**mango1 단일 노드, GPU 0+1 (둘 다 RTX 4090)** — 단일노드 선택 이유:", 0),
    ("스래싱은 **GPU(백엔드) 단위** 현상 → 물리 서버 수와 무관. 네트워크 교란 없이 깨끗하게 재현", 1),
    ("vLLM **2인스턴스**(:8000/:8001, Qwen3-8B) + **ThunderAgent 프록시**(:9000)", 0),
    ("**합성 워크로드 드라이버** — 실제 에이전트 자원 패턴만 흉내 (외부 API/Docker 불필요):", 0),
    ("프로그램 = 고유 program_id, **멀티턴**(리즈닝 → 툴콜 sleep → 다음 턴), 종료 시 release", 1),
    ("동시 프로그램 수(concurrency)를 올려가며 스윕", 1),
    ("측정 지표: **throughput, p95 latency, KV prefix-cache hit rate**", 0),
], top=1.55)

# ---------------------------------------------------------------- 6 setup issues + bug
s = slide(); title(s, "세팅 이슈 & 원본 코드 버그")
bullets(s, [
    ("툴체인 이슈(간단): sudo 없이 Python 헤더 / flashinfer-nvcc(gcc13) 충돌 / KV 메모리 → 전부 우회", 0),
    ("(상세는 SETUP_NOTES 문서)", 1),
    ("★ **원본 코드 버그 발견 & 수정**:", 0),
    ("`__init__.py`가 app을 즉시 import → **CLI 설정이 반영되기 전 기본값으로 라우터 생성**", 1),
    ("결과: `--backends`/`--router`가 무시됨 → **백엔드 1개만, 항상 tr 모드**", 1),
    ("→ 안 잡았으면 **tr vs default 비교 자체가 무효**였음 (초기 결과 폐기 후 재실험)", 1),
], top=1.55)
note(s, "베이스라인 신뢰성에 직결된 버그 — 재현 연구에서 이런 검증이 중요")

# ---------------------------------------------------------------- 7 stage 1
s = slide(); title(s, "결과 1단계 — 일반 워크로드 (짧은 컨텍스트)")
bullets(s, [
    ("설정: 짧은 컨텍스트, concurrency 8 → 128, 두 백엔드 균등 분산", 0),
    ("관찰: **중고부하 C=64~96에서 tr이 우세**", 0),
    ("throughput C=96: **tr 17.9 vs default 14.1 prog/s (+27%)**, p95도 tr 낮음(6.2 vs 8.7s)", 1),
    ("default는 C=64에서 이미 throughput 천장 → tr은 C=96까지 더 버팀", 1),
    ("**단, KV hit rate는 tr·default 모두 ~0.95로 비슷**", 0),
    ("→ 이때 tr 이득은 **‘부하 분산’** 에서 온 것. 논문 핵심인 **‘스래싱 방지’는 아직 안 나타남**", 1),
    ("**한계 발견**: KV 용량을 안 넘겨서 스래싱 자체가 없었음 → 2단계로", 0),
], top=1.5)
note(s, "★ 1단계의 한계를 발견한 것이 2단계 실험의 동기")

# ---------------------------------------------------------------- 8 stage 2 (GRAPHS)
s = slide(); title(s, "결과 2단계 — 스래싱 심화 (KV 용량 압박)", accent=ORANGE)
tb = s.shapes.add_textbox(Inches(0.7), Inches(1.25), Inches(12.0), Inches(0.75))
tf = tb.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]
_set_runs(p, "정조준: 프로그램마다 **고유한 긴 컨텍스트(ctx≈3000 토큰)** 를 넣어 2×4090 KV 용량을 초과 → 재프리필 폭증 유도", 15, GRAY)
p2 = tf.add_paragraph()
_set_runs(p2, "결과: **tr hit 0.67 유지 vs default 0.02 붕괴 (~28×)**, throughput +57%, 고부하 p95 97s vs 158s", 15, ORANGE, bold_default=False)
figs = ["thrash_hit_rate.png", "thrash_throughput.png", "thrash_p95_latency.png"]
w = Inches(4.25); x0 = Inches(0.15); gap = Inches(0.12); y = Inches(2.35)
caps = ["KV hit rate (핵심)", "throughput", "p95 latency"]
for i, f in enumerate(figs):
    x = Emu(int(x0) + i * (int(w) + int(gap)))
    s.shapes.add_picture(os.path.join(FIG, f), x, y, width=w)
    cb = s.shapes.add_textbox(x, Inches(6.9), w, Inches(0.4))
    cp = cb.text_frame.paragraphs[0]; cp.alignment = PP_ALIGN.CENTER
    r = cp.add_run(); r.text = caps[i]; r.font.size = Pt(12); r.font.bold = True; r.font.color.rgb = NAVY

# ---------------------------------------------------------------- 9 analysis
s = slide(); title(s, "결과 분석 — 1→2단계 스토리")
bullets(s, [
    ("**default의 hit 0.02 붕괴 = 매 턴 재프리필 폭증 = 논문이 말한 ‘KV 스래싱’ 그 자체**", 0),
    ("재프리필 토큰량: **tr ≈ 2M vs default ≈ 25M (약 10배)**", 1),
    ("tr이 이긴 진짜 이유: capacity-aware로 **활성 working set을 용량 안에 유지 → 캐시 보존**", 0),
    ("1단계 이득(부하분산)과 **질적으로 다름** — 이번엔 ‘스래싱 방지’ 자체", 1),
    ("스토리: **1단계에서 한계 발견 → 2단계에서 정조준해 재현** → 논문 경향과 일치", 0),
    ("homogeneous에서 tr은 두 백엔드에 **거의 반반 분배** → 동일 GPU라 반반이 최적이었기 때문", 0),
], top=1.55)
note(s, "→ 이 마지막 관찰이 heterogeneous로 넘어가는 다리")

# ---------------------------------------------------------------- 10 hetero connection
s = slide(); title(s, "★ Heterogeneous로의 연결 (핵심 통찰)", accent=ORANGE)
bullets(s, [
    ("GPU가 다르면(4090 vs 5090) **반반 분배는 더 이상 최적이 아니다** → 성능에 비례해 나눠야", 0),
    ("그런데 **현재 tr 라우터는 GPU 성능 차이를 라우팅에 반영하지 못한다**", 0),
    ("compute 처리량 · 메모리 대역폭 · **KV 용량**의 차이를 모름", 1),
    ("특히 **KV 용량이 다르면 스래싱 시작점이 백엔드마다 다르다**", 0),
    ("→ 균등 분배가 **작은/느린 GPU에서 먼저 스래싱**을 유발할 수 있음", 1),
    ("→ **heterogeneous에선 tr조차 최적이 아니다. 바로 여기가 우리가 파고들 지점.**", 0),
], top=1.55)

# ---------------------------------------------------------------- 11 next experiment
s = slide(); title(s, "다음 실험 제안 & 열린 질문")
bullets(s, [
    ("제안 세팅: **mango(4090) + goguma6(5090)** 2인스턴스 heterogeneous", 0),
    ("(논문의 H100급 가정과는 격차 있음 — 우리가 가진 자원 기준)", 1),
    ("가설: tr의 **균등 분배가 4090을 먼저 스래싱**시켜 전체 throughput을 떨어뜨릴 것", 0),
    ("볼 지표: **백엔드별 KV hit rate·스래싱 시작점**, 전체 throughput/p95, 실제 분배 비율", 0),
    ("열린 질문(논의):", 0),
    ("성능 비례 분배의 기준을 무엇으로? (KV 용량? 처리량? 대역폭?)", 1),
    ("KV locality를 얼마나 희생하고 부하를 옮길 것인가?", 1),
    ("반복측정(에러바)·논문 정독은 진행 예정 (현재 각 점 1회) — **TBD**", 1),
], top=1.5)

# ---------------------------------------------------------------- 12 appendix
s = slide(); title(s, "부록 — 재현 방법 요약")
bullets(s, [
    ("2× vLLM(env: CPATH, VLLM_ATTENTION_BACKEND=FLASH_ATTN) + ThunderAgent 프록시(tr/default)", 0),
    ("합성 드라이버로 concurrency 스윕 → JSON → 그래프", 0),
    ("스래싱 유도: 드라이버 `--ctx-tokens 3000` (프로그램별 고유 긴 컨텍스트)", 0),
    ("산출물 (git 브랜치 `yunuikang/thunderagent`):", 0),
    ("EXPERIMENT_LOG_yunuikang.md · SETUP_NOTES_yunuikang.md · scripts/ · figures/", 1),
], top=1.7)

prs.save(OUT)
print("saved:", OUT, "slides:", len(prs.slides._sldIdLst))
