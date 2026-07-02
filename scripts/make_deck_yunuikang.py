#!/usr/bin/env python3
"""Build the meeting deck (meeting_yunuikang.pptx) for the ThunderAgent reproduction.

Story: homogeneous baseline reproduction -> workload characterization ->
heterogeneous direction. Trend/mechanism only (no absolute-number comparison
with the paper). Real measured numbers; TBD where not measured; [추정] flagged.

Paper citations use only what is verifiable in assets/paper/_Arxiv__ThunderAgent.pdf
(28p): §3.1, §3.2, §3.3, §4.3.1 Eq.(6), §4.3.2, Table 4, Fig 1b, Fig 5, §5.1.
That PDF has NO §A.5 / A100 / compute-to-bandwidth; the heterogeneous "slower GPU
thrashes first" point is presented as OUR hypothesis grounded in §10 measurements.

Graphs: figures/thrash_*.png on slide 8; figures/char_*.png on slides 9-10.
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

REPO = "/home/yunuikang/yunuikang_work/distserving"
FIG = os.path.join(REPO, "figures")
OUT = os.path.join(REPO, "meeting_yunuikang.pptx")

NAVY = RGBColor(0x1F, 0x3A, 0x5F)
BLUE = RGBColor(0x1F, 0x77, 0xB4)   # tr
ORANGE = RGBColor(0xD6, 0x5F, 0x00) # default
GREEN = RGBColor(0x2E, 0x7D, 0x32)
GRAY = RGBColor(0x44, 0x44, 0x44)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
SW = prs.slide_width


def slide():
    return prs.slides.add_slide(BLANK)


def _set_runs(p, text, size, color, bold_default=False):
    for i, seg in enumerate(text.split("**")):
        if seg == "":
            continue
        r = p.add_run(); r.text = seg
        r.font.size = Pt(size); r.font.color.rgb = color
        r.font.bold = bold_default or (i % 2 == 1)


def title(s, text, accent=NAVY):
    tb = s.shapes.add_textbox(Inches(0.55), Inches(0.32), Inches(12.3), Inches(0.9))
    tf = tb.text_frame; tf.word_wrap = True
    r = tf.paragraphs[0].add_run(); r.text = text
    r.font.size = Pt(27); r.font.bold = True; r.font.color.rgb = accent
    bar = s.shapes.add_shape(1, Inches(0.58), Inches(1.12), Inches(3.2), Pt(3))
    bar.fill.solid(); bar.fill.fore_color.rgb = accent; bar.line.fill.background()
    return s


def bullets(s, items, left=0.7, top=1.45, width=12.0, height=5.4, size=18, gap=6):
    tb = s.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tb.text_frame; tf.word_wrap = True
    first = True
    for text, lvl in items:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.level = lvl; p.space_after = Pt(gap)
        bullet = "•  " if lvl == 0 else ("–  " if lvl == 1 else "·  ")
        sz = size if lvl == 0 else (size - 2 if lvl == 1 else size - 3)
        rb = p.add_run(); rb.text = bullet
        rb.font.size = Pt(sz); rb.font.color.rgb = NAVY if lvl == 0 else GRAY
        _set_runs(p, text, sz, GRAY)
    return tb


def note(s, text, top=6.98, color=BLUE):
    tb = s.shapes.add_textbox(Inches(0.7), Inches(top), Inches(12.2), Inches(0.4))
    p = tb.text_frame.paragraphs[0]
    r = p.add_run(); r.text = text
    r.font.size = Pt(12); r.font.italic = True; r.font.color.rgb = color


def caption(s, x, w, text, top):
    cb = s.shapes.add_textbox(x, Inches(top), w, Inches(0.35))
    cp = cb.text_frame.paragraphs[0]; cp.alignment = PP_ALIGN.CENTER
    r = cp.add_run(); r.text = text
    r.font.size = Pt(11); r.font.bold = True; r.font.color.rgb = NAVY


# ---------------------------------------------------------------- 1 title
s = slide()
band = s.shapes.add_shape(1, 0, Inches(2.3), SW, Inches(2.9))
band.fill.solid(); band.fill.fore_color.rgb = NAVY; band.line.fill.background()
tb = s.shapes.add_textbox(Inches(0.8), Inches(2.5), Inches(11.7), Inches(1.7))
tf = tb.text_frame; tf.word_wrap = True
r = tf.paragraphs[0].add_run(); r.text = "ThunderAgent 재현 실험"
r.font.size = Pt(40); r.font.bold = True; r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
p2 = tf.add_paragraph()
r = p2.add_run(); r.text = "Homogeneous 재현 · 워크로드 특성 분석 → Heterogeneous 방향 논의"
r.font.size = Pt(19); r.font.color.rgb = RGBColor(0xCF, 0xDD, 0xEE)
tb2 = s.shapes.add_textbox(Inches(0.8), Inches(5.5), Inches(11.7), Inches(0.8))
r = tb2.text_frame.paragraphs[0].add_run(); r.text = "강윤의  ·  2026-07-02  ·  격주 미팅"
r.font.size = Pt(16); r.font.color.rgb = GRAY

# ---------------------------------------------------------------- 2 background
s = slide(); title(s, "배경: 에이전트 서빙은 왜 기존과 다른가")
bullets(s, [
    ("기존 채팅형 LLM: 요청 1개 → 리즈닝 1회 → 끝. **스케줄 단위 = 요청**", 0),
    ("에이전트(ReAct): 리즈닝 ↔ 툴콜을 여러 턴 반복. **스케줄 단위 = 프로그램(세션 전체)**", 0),
    ("여기서 두 가지 특성이 새로 생긴다:", 0),
    ("툴콜 중에는 GPU가 노는 **‘버블’** 이 생김 (자원 특성이 리즈닝과 다름)", 1),
    ("멀티턴이라 **KV 캐시가 턴마다 누적** → 매 턴 새 부분만 프리필(부분 프리필)", 1),
    ("→ 요청 하나씩 보면 안 되고, **프로그램 전체를 통으로 관리**해야 함", 0),
], top=1.55)
note(s, "핵심: 멀티턴 KV 누적 + 툴콜 버블이 기존 서빙 가정과 다르다")

# ---------------------------------------------------------------- 3 problem + 3 contributions
s = slide(); title(s, "ThunderAgent가 푸는 문제 & 논문의 3대 기여")
bullets(s, [
    ("근본 트레이드오프: **KV Locality**(프로그램을 같은 인스턴스에 고정해야 KV 재사용) vs **Load Balancing**(클러스터 골고루)", 0),
    ("ThunderAgent: **프로그램 단위 + capacity-aware 스케줄링**으로 조율", 0),
    ("논문의 3대 기여:", 0),
    ("① **KV 캐시 스래싱** 완화 — program-aware waiting queue (§3.1, §4.3.1)  ← **우리가 재현한 부분**", 1),
    ("② **Cross-node 메모리 불균형** — global queue·migration (§3.2, §4.3.2)", 1),
    ("③ **Tool lifecycle 관리** — GC·async env prep (§3.3, §4.4)", 1),
    ("우리 비교축: **tr** = program-aware(≈ThunderAgent) / **default** = 단순 최소부하(≈논문 vLLM baseline)", 0),
], top=1.5)
note(s, "Continuum은 우리가 비교하지 않아 다루지 않음")

# ---------------------------------------------------------------- 4 goal
s = slide(); title(s, "이번 작업의 목표 — ‘정성적’ 재현")
bullets(s, [
    ("논문(ICML 2026)의 **경향/메커니즘 방향**을 우리 랩 GPU에서 재현", 0),
    ("★ 절대 수치는 논문과 비교하지 않는다:", 0),
    ("워크로드가 다름 (우리=합성 sleep 기반 / 논문=SWE-Agent·OpenHands·ToolOrchestra 실제 에이전트)", 1),
    ("하드웨어가 다름 (우리=RTX 4090×2 / 논문=8×H100 클러스터, §5.1)", 1),
    ("확인할 것: tr이 **KV hit rate·throughput을 더 잘 지키는가**, 부하를 올리면 **스래싱으로 꺾이는 지점**이 나오는가", 0),
    ("지금은 **homogeneous baseline** → 최종 목표 **heterogeneous(서로 다른 GPU)** 로 가는 발판", 0),
], top=1.55)
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
    ("측정: **throughput · p95 latency · KV prefix-cache hit rate** (백엔드 /metrics 델타)", 0),
], top=1.5)

# ---------------------------------------------------------------- 6 setup issues + bug
s = slide(); title(s, "세팅 이슈 & 원본 코드 버그")
bullets(s, [
    ("툴체인 이슈(간단): sudo 없이 Python 헤더 / flashinfer-nvcc(gcc13) 충돌 / KV 메모리 → 전부 우회 (SETUP_NOTES)", 0),
    ("★ **원본 코드 버그 발견 & 수정**:", 0),
    ("`__init__.py`가 app을 즉시 import → **CLI 설정 반영 전 기본값으로 라우터 생성**", 1),
    ("결과: `--backends`/`--router`가 무시됨 → **백엔드 1개만, 항상 tr 모드**", 1),
    ("→ 안 잡았으면 **tr vs default 비교 자체가 무효**였음 (초기 결과 폐기 후 재실험)", 1),
], top=1.55)
note(s, "베이스라인 신뢰성에 직결된 버그 — 재현 연구에서 이런 검증이 중요")

# ---------------------------------------------------------------- 7 stage 1
s = slide(); title(s, "결과 1단계 — 일반 워크로드 (짧은 컨텍스트)")
bullets(s, [
    ("설정: 짧은 컨텍스트, concurrency 8 → 128, 두 백엔드 균등 분산", 0),
    ("관찰: **중고부하 C=64~96에서 tr 우세**", 0),
    ("throughput C=96: **tr 17.9 vs default 14.1 prog/s (+27%)**, p95도 tr 낮음(6.2 vs 8.7s)", 1),
    ("default는 C=64에서 이미 throughput 천장 → tr은 C=96까지 더 버팀", 1),
    ("**단, KV hit rate는 tr·default 모두 ~0.95로 비슷**", 0),
    ("→ 이때 tr 이득은 **‘부하 분산’** 에서 온 것. 논문 핵심인 **‘스래싱 방지’는 아직 안 나타남**", 1),
    ("**한계 발견**: KV 용량을 안 넘겨 스래싱이 없었음 (Eq.6 미충족) → 2단계로", 0),
], top=1.5)
note(s, "★ 1단계의 한계를 발견한 것이 2단계 실험의 동기")

# ---------------------------------------------------------------- 8 stage 2 (3 GRAPHS) + paper
s = slide(); title(s, "결과 2단계 — 스래싱 심화 (KV 용량 압박)", accent=ORANGE)
tb = s.shapes.add_textbox(Inches(0.6), Inches(1.2), Inches(12.2), Inches(1.05))
tf = tb.text_frame; tf.word_wrap = True
_set_runs(tf.paragraphs[0], "정조준: 프로그램마다 **고유한 긴 컨텍스트**를 넣어 2×4090 KV 용량 초과 → 재프리필 폭증 유도", 14, GRAY)
_set_runs(tf.add_paragraph(), "결과: **tr hit 0.67 유지 vs default 0.02 붕괴 (~28×)**, throughput +57%, 고부하 p95 97s vs 158s, 재프리필 tr≈2M vs default≈25M(~10×)", 14, ORANGE)
_set_runs(tf.add_paragraph(), "논문 대조: default 붕괴 = **§3.1·Fig 1b·Fig 5의 ‘request-level → tool 중 KV evict → 재프리필 → 스래싱’** 과 방향 일치 (논문 7.14× re-prefill latency 주장과 같은 방향)", 13, NAVY)
figs = ["thrash_hit_rate.png", "thrash_throughput.png", "thrash_p95_latency.png"]
caps = ["KV hit rate (핵심)", "throughput", "p95 latency"]
w = Inches(4.25); x0 = Inches(0.15); gap = Inches(0.12); y = Inches(2.72)
for i, f in enumerate(figs):
    x = Emu(int(x0) + i * (int(w) + int(gap)))
    s.shapes.add_picture(os.path.join(FIG, f), x, y, width=w)
    caption(s, x, w, caps[i], 7.02)

# ---------------------------------------------------------------- 9 characterization: token/turn
s = slide(); title(s, "워크로드 특성 (1) — 극단적 input-heavy", accent=GREEN)
bullets(s, [
    ("이 워크로드는 **입력 ~14.5k 토큰/turn vs 출력 ~28 토큰** → 비용이 **prefill/KV에 몰림**, KV locality가 결정적", 0),
    ("turn 단계 분해: **turn 0 = full prefill ~1.82s**, **turn 1~3 = prefix 재사용 ~0.13s** (약 **14× 감소**)", 0),
    ("→ ‘프로그램을 같은 곳에 고정하면 왜 이득인지’를 **실측으로** 보여줌", 1),
], top=1.4, width=12.2, size=17)
s.shapes.add_picture(os.path.join(FIG, "char_tokens.png"), Inches(0.35), Inches(3.3), width=Inches(7.1))
caption(s, Inches(0.35), Inches(7.1), "input/output 토큰 분포", 6.7)
s.shapes.add_picture(os.path.join(FIG, "char_turn_breakdown.png"), Inches(7.85), Inches(3.0), width=Inches(5.15))
caption(s, Inches(7.85), Inches(5.15), "turn별 prefill/decode/tool", 6.7)
note(s, "prefill/decode는 vLLM이 요청별 분리 미제공 → 스트리밍 TTFT로 근사한 값 (c=1, 큐 오염 없음)", top=7.06, color=GRAY)

# ---------------------------------------------------------------- 10 characterization: KV capacity (hetero ground)
s = slide(); title(s, "워크로드 특성 (2) — KV 수용량 ★ heterogeneous 근거", accent=GREEN)
bullets(s, [
    ("KV = **144 KiB/token** (Qwen3-8B config 실측 = vLLM KV풀 로그와 교차검증 일치)", 0),
    ("프로그램당 peak ≈ **2 GiB** → **4090 한 장에 동시 ~3개만 적재** (KV풀 43,888 토큰 실측)", 0),
    ("§9에서 c=48은 용량 **~16× 초과** → 스래싱이 필연이었음을 정량 설명 (특성이 §9를 뒷받침)", 0),
    ("★ **5090(32GB) ≈ 6.6개 [추정/미측정]** vs 4090 ≈ 3개 → **GPU마다 수용량이 2배+ 다름**", 0),
], top=1.4, width=12.2, size=17)
s.shapes.add_picture(os.path.join(FIG, "char_kv.png"), Inches(1.75), Inches(3.55), width=Inches(9.8))
caption(s, Inches(1.75), Inches(9.8), "KV 누적(turn별) · GPU 수용량 (4090 실측 / 5090 추정)", 7.05)

# ---------------------------------------------------------------- 11 analysis synthesis
s = slide(); title(s, "결과 분석 종합 — 1→2단계 스토리 (논문으로 해석)")
bullets(s, [
    ("**1→2 차이의 원인 = 논문 Eq.(6) 스래싱 조건** `C_total < Σ c_p` (§4.3.1)", 0),
    ("1단계: working set이 KV 풀에 **들어감** → 스래싱 없음 → tr·default hit 유사(이득은 부하분산)", 1),
    ("2단계: working set이 풀을 **초과** → 스래싱 발생 → **용량 제어가 있는 tr만** hit rate 유지", 1),
    ("(논문 Appendix D: tool이 짧고 예측가능하면 ‘스래싱 회피=높은 hit rate’가 throughput을 지배 → 우리 레짐과 정합)", 1),
    ("우리가 재현한 범위: **논문 3대 기여 중 ① KV 스래싱(§3.1·§4.3.1)만**", 0),
    ("범위 밖(명시): ② cross-node 불균형(§3.2), ③ tool lifecycle(§3.3) — 단일노드·합성 tool이라 미재현", 1),
    ("homogeneous에선 tr이 두 백엔드에 **거의 반반 분배**(동일 GPU라 반반이 최적) — 이게 hetero로 가는 다리", 0),
], top=1.45, size=17)

# ---------------------------------------------------------------- 12 hetero connection (grounded)
s = slide(); title(s, "★ Heterogeneous로의 연결 (실측 + 논문 근거)", accent=ORANGE)
bullets(s, [
    ("GPU가 다르면(4090 vs 5090) **반반 분배는 더 이상 최적이 아님** — 성능·용량에 비례해 나눠야", 0),
    ("우리 실측 근거(§10): **4090 ≈ 3개 / 5090 ≈ 6.6개[추정]** → 수용량이 2배+ 다름 → **스래싱 시작점이 백엔드마다 다름**", 0),
    ("논문의 한계(검증 가능한 근거):", 0),
    ("§4.3.2: restore를 **‘용량 남는 아무 replica’** 로 보냄, 재프리필 비용을 **node-agnostic으로 가정**", 1),
    ("Table 4 BackendState: **용량/토큰만 추적, 처리속도·대역폭 필드 없음** → 스케줄러가 GPU 속도를 모름", 1),
    ("논문 하드웨어는 **동질 셋업만** (8×H100 또는 5090 1장) — **GPU를 섞은 실험 없음** (§5.1)", 1),
    ("→ **[우리 가설]** 균등/용량기반 분배는 **작은·느린 4090을 먼저 스래싱** → 전역 throughput 손실", 0),
    ("→ 필요한 것: **용량·속도·대역폭 비례 라우팅** — 논문 global queue엔 없는 축 = **우리 연구의 gap**", 0),
], top=1.45, size=16)
note(s, "‘느린 GPU가 먼저 스래싱’은 논문 실험이 아니라 §10 실측 기반 우리 가설([추정]) — 이 PDF엔 A100/compute-bandwidth 논의 없음")

# ---------------------------------------------------------------- 13 next experiment
s = slide(); title(s, "다음 실험 제안 & 열린 질문")
bullets(s, [
    ("제안 세팅: **mango(4090) + goguma6(5090)** 2인스턴스 heterogeneous", 0),
    ("(논문의 H100급과는 격차 — 우리가 가진 자원 기준)", 1),
    ("가설: tr의 **균등 분배가 4090을 먼저 스래싱**시켜 전체 throughput을 떨어뜨릴 것", 0),
    ("볼 지표: **백엔드별 KV hit rate·스래싱 시작점**, 전체 throughput/p95, 실제 분배 비율", 0),
    ("열린 질문(논의):", 0),
    ("성능 비례 분배의 기준을 무엇으로? (KV 용량? 처리량? 대역폭?)", 1),
    ("KV locality를 얼마나 희생하고 부하를 옮길 것인가?", 1),
    ("반복측정(에러바)·논문 심화 정독은 진행 예정 (현재 각 점 1회) — **TBD**", 1),
], top=1.5)

# ---------------------------------------------------------------- 14 appendix
s = slide(); title(s, "부록 — 재현 방법 & 재현 안 한 기여")
bullets(s, [
    ("재현 방법: 2× vLLM(env: CPATH, VLLM_ATTENTION_BACKEND=FLASH_ATTN) + ThunderAgent 프록시(tr/default)", 0),
    ("합성 드라이버로 concurrency 스윕 → JSON → 그래프. 스래싱 유도: `--ctx-tokens 3000`", 0),
    ("characterization: `--stream`(TTFT 근사)·`--trace-out`(turn별), 단일 백엔드 c=1/c=8", 0),
    ("**재현 안 한 논문 기여**: ② cross-node 메모리 불균형(§3.2), ③ tool lifecycle 관리(§3.3) — 범위 밖", 0),
    ("산출물(브랜치 `yunuikang/thunderagent`): EXPERIMENT_LOG · SETUP_NOTES · scripts/ · figures/", 0),
], top=1.6)

prs.save(OUT)
print("saved:", OUT, "slides:", len(prs.slides._sldIdLst))
