#!/usr/bin/env python3
"""Build meeting_yunuikang.pptx for the ThunderAgent reproduction (with speaker notes).

Story: 배경 → 문제 → 재현목표(정성적) → 버그 → 1단계(한계) → 2단계(스래싱 재현)
       → 워크로드 특성(KV 수용량) → 논문대조 → heterogeneous 연결 → 다음실험.

Paper citations verified against assets/paper/_Arxiv__ThunderAgent.pdf (28p, the
presentation version). Only sections that exist in this version are cited:
§3.1/§3.2/§3.3, §4.3.1 Eq.(6), §4.3.2, §4.4, §5.1, Fig 1b, Fig 5, Appendix D,
Table 4, 7.14×, 8×H100. This version has NO GPU-generation portability experiment
and no compute-to-bandwidth study; the heterogeneous "slower GPU thrashes first"
claim is presented as OUR hypothesis grounded in our §10 measurements.
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

REPO = "/home/yunuikang/yunuikang_work/distserving"
FIG = os.path.join(REPO, "figures")
OUT = os.path.join(REPO, "slides", "2026-07-02_meeting_yunuikang.pptx")

NAVY = RGBColor(0x1F, 0x3A, 0x5F)
BLUE = RGBColor(0x1F, 0x77, 0xB4)
ORANGE = RGBColor(0xD6, 0x5F, 0x00)
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


def bullets(s, items, left=0.7, top=1.55, width=12.0, height=5.2, size=18, gap=8):
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


def notes(s, core, script_lines, qas, minutes):
    """Speaker notes: 핵심 한 줄 / 구어체 멘트 / 예상 질문·답 / 예상 시간."""
    tf = s.notes_slide.notes_text_frame
    tf.text = "【핵심 메시지】 " + core
    tf.add_paragraph().text = ""
    tf.add_paragraph().text = "【발표 멘트 (그대로 읽어도 됨)】"
    for ln in script_lines:
        tf.add_paragraph().text = ln
    tf.add_paragraph().text = ""
    tf.add_paragraph().text = "【예상 질문 & 답변】"
    for q, a in qas:
        tf.add_paragraph().text = "Q. " + q
        tf.add_paragraph().text = "A. " + a
    tf.add_paragraph().text = ""
    tf.add_paragraph().text = "【예상 시간】 " + minutes


# ================================================================ 1 title
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
notes(s,
      "오늘 발표의 목적과 전체 흐름을 각인시킨다.",
      ["안녕하세요, 강윤의입니다. 오늘은 ThunderAgent라는 '에이전트 서빙 시스템'을 우리 랩 GPU에서 직접 돌려보고,",
       "논문과 '비슷한 경향'이 나오는지 확인한 결과, 그리고 다음 단계로 '서로 다른 GPU를 섞는(heterogeneous)'",
       "환경에서 무엇을 해볼지 논의드리려고 합니다.",
       "전체 흐름은 이렇습니다: ①왜 에이전트 서빙이 특별한가(배경) → ②ThunderAgent가 푸는 문제 →",
       "③우리 재현 목표 → ④세팅 중 발견한 버그 → ⑤결과 1단계(여기서 한계를 발견) → ⑥결과 2단계(핵심 현상 재현) →",
       "⑦워크로드 특성 분석(GPU에 몇 개나 올라가나) → ⑧논문과 대조 → ⑨heterogeneous로의 연결 → ⑩다음 실험 제안.",
       "미리 정직하게 말씀드릴 세 가지: (1) 논문과 '절대 수치'를 비교하는 게 아니라 '경향의 방향'만 봅니다",
       "(하드웨어·워크로드가 다르니까요). (2) 5090 관련 숫자는 아직 '추정'입니다. (3) 각 측정은 아직 1회씩입니다."],
      [("이거 논문 재현이 목적인가요, 새 연구인가요?",
        "재현은 baseline 확보가 목적이고, 진짜 목표는 그 뒤의 heterogeneous 확장입니다. 오늘은 그 다리를 놓는 자리예요.")],
      "약 0.5분 (총 발표 ~18분 목표)")

# ================================================================ 2 background
s = slide(); title(s, "배경: 에이전트 서빙은 왜 기존과 다른가")
bullets(s, [
    ("기존 챗봇 LLM: 요청 1개 → 답 1개. **스케줄 단위 = 요청**", 0),
    ("에이전트(ReAct): 리즈닝 ↔ 툴콜을 여러 턴 반복. **스케줄 단위 = 프로그램(세션 전체)**", 0),
    ("여기서 새로 생기는 두 특성:", 0),
    ("툴콜 중엔 GPU가 노는 **‘버블’**", 1),
    ("멀티턴이라 **KV 캐시가 턴마다 누적** (이전 계산을 저장해 재사용)", 1),
    ("→ 요청 하나씩이 아니라 **프로그램 전체를 통으로 관리**해야 함", 0),
])
note(s, "핵심: 멀티턴 KV 누적 + 툴콜 버블이 기존 서빙 가정과 다르다")
notes(s,
      "에이전트는 '요청 단위'가 아니라 '프로그램(세션 전체) 단위'로 봐야 한다.",
      ["기존 챗봇은 단순합니다. 질문 하나 넣으면 답 하나 나오고 끝. 그래서 시스템은 '요청 하나'를 스케줄 단위로 봅니다.",
       "그런데 에이전트는 다릅니다. 생각하고(리즈닝), 도구를 쓰고(툴콜, 예: 검색·코드실행), 그 결과를 보고 또 생각하고…",
       "이걸 여러 턴 반복합니다. 여기서 두 가지가 새로 생깁니다.",
       "첫째, 도구를 쓰는 동안엔 GPU가 놉니다. 이걸 '버블'이라고 부를게요.",
       "둘째, 대화가 길어질수록 KV 캐시가 계속 쌓입니다. KV 캐시는 쉽게 말해 '모델이 앞 토큰들을 계산해둔 메모장'인데,",
       "이게 있으면 다음 턴에 앞부분을 다시 계산(prefill)하지 않아도 됩니다. 그래서 이걸 잘 보존하는 게 성능의 핵심이에요.",
       "결론적으로, 요청 하나씩 따로 보면 안 되고 '프로그램 전체'를 하나로 묶어서 관리해야 한다 — 이게 오늘의 출발점입니다."],
      [("KV 캐시가 정확히 뭔가요?",
        "이전 토큰들의 key/value 벡터를 GPU 메모리에 저장한 겁니다. 있으면 재계산(prefill)을 건너뛰어 빠릅니다."),
       ("버블이 왜 문제죠?",
        "도구 실행 몇 초 동안 그 프로그램의 KV가 GPU 메모리를 잡고 있는데 계산은 안 해서, 그 자리에 다른 걸 못 올립니다.")],
      "약 1.5분")

# ================================================================ 3 problem + 3 contributions
s = slide(); title(s, "ThunderAgent가 푸는 문제 & 논문의 3대 기여")
bullets(s, [
    ("근본 트레이드오프: **KV Locality**(같은 인스턴스 고정 → KV 재사용) vs **Load Balancing**(골고루 써야 빠름)", 0),
    ("ThunderAgent: **프로그램 단위 + capacity-aware 스케줄링**으로 조율", 0),
    ("논문의 3대 기여:", 0),
    ("① **KV 캐시 스래싱** 완화 (§3.1, §4.3.1)  ← **우리가 재현한 부분**", 1),
    ("② cross-node 메모리 불균형 (§3.2, §4.3.2)   ③ tool lifecycle 관리 (§3.3, §4.4)", 1),
    ("우리 비교축: **tr**(≈ThunderAgent) vs **default**(≈논문 vLLM baseline)", 0),
])
note(s, "Continuum은 우리가 비교하지 않아 다루지 않음")
notes(s,
      "ThunderAgent는 KV locality와 load balancing의 상충을 프로그램 단위로 조율한다. 우리는 3대 기여 중 ①만 재현.",
      ["멀티 인스턴스(여러 GPU)로 서빙할 때 근본적인 딜레마가 있습니다.",
       "한 프로그램을 계속 같은 GPU로 보내면 KV 캐시를 재사용해서 좋습니다(=KV locality).",
       "하지만 그러면 특정 GPU에만 몰릴 수 있어요. 반대로 골고루 나누면(=load balancing) KV 재사용을 잃습니다.",
       "ThunderAgent는 '프로그램 단위 + 용량을 아는(capacity-aware) 스케줄링'으로 이 둘을 조율합니다.",
       "논문의 기여는 크게 3가지인데, ① KV 캐시 스래싱 완화, ② 노드 간 메모리 불균형 해소, ③ 툴 자원 관리입니다.",
       "오늘 우리가 재현한 건 이 중 ①번뿐이라는 점을 미리 못박아 둡니다. ②③은 범위 밖이에요.",
       "그리고 우리 실험의 비교축은 두 라우터입니다. tr은 논문의 ThunderAgent에, default는 논문의 vLLM baseline에 대응합니다."],
      [("Continuum은 왜 안 다루나요?",
        "우리가 비교 실험을 하지 않았기 때문입니다. 오늘은 tr vs default(=ThunderAgent vs vLLM) 대응만 다룹니다."),
       ("스래싱이 뭔가요?",
        "KV 캐시가 메모리 부족으로 쫓겨났다가 다시 계산되는 일이 반복되는 상태입니다. 뒤 슬라이드에서 자세히요.")],
      "약 1.5분")

# ================================================================ 4 goal
s = slide(); title(s, "이번 작업의 목표 — ‘정성적’ 재현")
bullets(s, [
    ("논문(ICML 2026)의 **경향/메커니즘 방향**을 우리 랩 GPU에서 재현", 0),
    ("★ 절대 수치는 논문과 비교하지 않는다 — 워크로드(합성 vs 실제 에이전트)·하드웨어(4090×2 vs 8×H100)가 다름", 0),
    ("확인할 것: tr이 **KV hit rate·throughput을 더 잘 지키는가**, 부하↑ 시 **스래싱으로 꺾이는 지점**이 나오는가", 0),
    ("지금은 **homogeneous baseline** → 최종 목표 **heterogeneous(서로 다른 GPU)** 로 가는 발판", 0),
])
note(s, "‘무엇을 했다’가 아니라, 관찰이 heterogeneous로 넘어가는 근거가 되는지가 핵심")
notes(s,
      "우리는 논문의 '경향'을 재현하려는 것이지 숫자를 맞추려는 게 아니다.",
      ["이번 작업의 목표를 정확히 하겠습니다. 우리는 논문의 '절대 성능 수치'를 재현하려는 게 아닙니다.",
       "우리 워크로드는 합성(합성 sleep 기반)이고 논문은 진짜 에이전트(SWE-Agent 등)입니다. 하드웨어도 우리는 4090 2장,",
       "논문은 H100 8장짜리 클러스터예요. 그러니 숫자를 직접 비교하는 건 무의미합니다. 대신 '경향의 방향'만 봅니다.",
       "구체적으로 두 가지를 확인합니다. 하나, tr이 default보다 KV 캐시 적중률과 처리량을 더 잘 지키는가?",
       "둘, 부하를 올리면 논문처럼 스래싱으로 성능이 꺾이는 지점이 나타나는가?",
       "그리고 지금은 '같은 GPU 두 장(homogeneous)'인 baseline 단계이고, 이건 최종 목표인 '서로 다른 GPU를 섞는'",
       "heterogeneous로 가기 위한 발판이라는 걸 기억해 주세요."],
      [("왜 숫자 비교를 안 하나요?",
        "하드웨어·워크로드가 달라서 숫자 자체는 의미가 없습니다. 같은 '방향'의 현상이 재현되는지가 재현 연구의 핵심입니다.")],
      "약 1분")

# ================================================================ 5 setup
s = slide(); title(s, "실험 구성")
bullets(s, [
    ("**mango1 단일 노드, GPU 0+1 (둘 다 RTX 4090)** — 스래싱은 GPU 단위 현상이라 단일노드로 깨끗이 재현", 0),
    ("vLLM **2인스턴스**(:8000/:8001, Qwen3-8B) + **ThunderAgent 프록시**(:9000, tr/default)", 0),
    ("**합성 워크로드 드라이버**: 프로그램=고유 id, 멀티턴(리즈닝→툴콜 sleep→다음 턴), 종료 시 release", 0),
    ("측정: **throughput · p95 latency · KV prefix-cache hit rate** (concurrency 스윕)", 0),
])
notes(s,
      "단일 노드 2×4090 + 프록시로, 합성 워크로드를 concurrency를 올려가며 측정한다.",
      ["실험 구성입니다. mango1이라는 서버 한 대에서 GPU 두 장(둘 다 RTX 4090)을 씁니다.",
       "왜 서버 한 대냐면, 우리가 보려는 스래싱은 'GPU(백엔드) 하나 안'에서 일어나는 현상이라 물리 서버 수와 무관하고,",
       "단일 노드로 하면 네트워크 잡음 없이 깨끗하게 볼 수 있어서예요.",
       "각 GPU에 vLLM(Qwen3-8B 모델)을 하나씩 띄우고, 그 앞에 ThunderAgent 프록시를 둡니다. 이 프록시의 라우터를",
       "tr이냐 default냐로 바꿔가며 비교합니다.",
       "워크로드는 직접 만든 합성 드라이버입니다. 진짜 에이전트는 유료 API·도커가 필요해서, 자원 사용 '패턴'만 흉내 냈어요.",
       "프로그램마다 고유 id를 주고, 리즈닝→툴콜(sleep로 흉내)→다음 턴을 반복하고, 끝나면 release 신호를 보냅니다.",
       "동시에 도는 프로그램 수(concurrency)를 올려가며 처리량·p95 지연·KV 적중률을 측정합니다."],
      [("합성 워크로드면 실제와 다르지 않나요?",
        "네, 그래서 절대 수치가 아니라 경향만 봅니다. 대신 멀티턴·KV 누적·툴 버블 같은 핵심 패턴은 살렸습니다."),
       ("p95 latency가 뭔가요?",
        "지연시간을 줄세웠을 때 상위 95% 지점 값입니다. 평균보다 '최악에 가까운 사용자 경험'을 잘 보여줍니다.")],
      "약 1.5분")

# ================================================================ 6 setup issues + bug
s = slide(); title(s, "세팅 이슈 & 원본 코드 버그")
bullets(s, [
    ("툴체인 이슈(간단): sudo 없이 Python 헤더 / flashinfer-nvcc(gcc13) 충돌 / KV 메모리 → 전부 우회 (SETUP_NOTES)", 0),
    ("★ **원본 코드 버그 발견 & 수정**:", 0),
    ("`__init__.py`가 app을 즉시 import → **CLI 설정 반영 전 기본값으로 라우터 생성**", 1),
    ("`--backends`/`--router` 무시 → **백엔드 1개만, 항상 tr 모드**", 1),
    ("→ 안 잡았으면 **tr vs default 비교 자체가 무효**였음 (초기 결과 폐기 후 재실험)", 1),
])
note(s, "베이스라인 신뢰성에 직결된 버그 — 재현 연구에서 이런 검증이 중요")
notes(s,
      "원본 코드의 초기화 버그 때문에 라우터 설정이 무시되고 있었고, 이를 잡아야 비교가 유효했다.",
      ["세팅 과정은 대부분 흔한 툴체인 문제였습니다. 관리자 권한 없이 파이썬 헤더를 잡거나, 컴파일러 버전 충돌,",
       "KV 메모리 부족 같은 것들인데 다 우회했고 상세는 SETUP_NOTES 문서에 있습니다.",
       "중요한 건 그다음입니다. 원본 코드에서 버그를 하나 발견했어요.",
       "코드가 시작할 때 설정(config)을 읽기도 전에 '기본값'으로 라우터를 먼저 만들어버리는 문제였습니다.",
       "그 결과 제가 --backends나 --router 옵션을 줘도 무시되고, 백엔드가 1개만 잡히고 항상 tr 모드로만 돌았어요.",
       "즉 이걸 못 잡았으면 tr과 default를 비교한다는 것 자체가 거짓이 될 뻔했습니다.",
       "초기화 순서를 지연 import로 고쳐서 설정이 먼저 반영되게 했고, 그 전 결과는 전부 폐기하고 다시 측정했습니다.",
       "재현 연구에서는 이런 '베이스라인이 진짜 맞나'를 검증하는 게 정말 중요하다는 사례입니다."],
      [("이 버그를 상류(upstream)에 제보했나요?",
        "아직입니다. 원하시면 정리해서 이슈로 올리겠습니다. 우리 실험엔 이미 반영돼 있습니다.")],
      "약 1.5분")

# ================================================================ 7 stage 1
s = slide(); title(s, "결과 1단계 — 일반 워크로드 (짧은 컨텍스트)")
bullets(s, [
    ("설정: 짧은 컨텍스트, concurrency 8 → 128", 0),
    ("**중고부하 C=64~96에서 tr 우세** — C=96 throughput **tr 17.9 vs default 14.1 (+27%)**, p95도 tr 낮음", 0),
    ("**단, KV hit rate는 둘 다 ~0.95로 비슷** → tr 이득은 **‘부하 분산’**, 논문 핵심 **‘스래싱 방지’는 아직 안 나타남**", 0),
    ("과부하 **C=128: tr·default 둘 다 붕괴**(throughput↓·latency 급증) — 두 4090의 물리 한계", 0),
    ("**한계 발견**: KV 용량을 안 넘겨 스래싱이 없었음(Eq.6 미충족) → 2단계로", 0),
])
note(s, "★ 1단계의 한계를 발견한 것이 2단계 실험의 동기")
notes(s,
      "1단계에선 tr이 +27% 빨랐지만 KV 적중률은 비슷했다 → 이득은 부하분산이지 스래싱 방지가 아니다(=한계 발견).",
      ["첫 실험은 '평범한' 워크로드, 즉 컨텍스트가 짧은 경우입니다. 동시 프로그램 수를 8부터 128까지 올렸어요.",
       "결과, 중간~높은 부하(64~96)에서 tr이 확실히 빨랐습니다. 예를 들어 96에서 처리량이 tr 17.9 vs default 14.1로",
       "약 27% 높고, p95 지연도 tr이 낮았습니다.",
       "그런데 중요한 관찰이 있어요. KV 캐시 적중률은 tr이든 default든 둘 다 0.95 정도로 비슷했습니다.",
       "이 말은, tr이 이긴 이유가 논문 핵심인 '스래싱 방지' 때문이 아니라 그냥 '부하를 더 잘 나눠서'였다는 뜻이에요.",
       "그리고 아주 높은 부하인 128에서는 tr, default 둘 다 무너졌습니다. 이건 4090 두 장의 물리적 한계라서 라우터가",
       "어쩔 수 없는 지점입니다.",
       "그래서 여기서 '한계'를 발견합니다: 우리가 KV 용량을 안 넘겼기 때문에 애초에 스래싱이 없었던 거예요.",
       "이 발견이 바로 다음 2단계 실험을 하게 된 이유입니다."],
      [("적중률이 비슷한데 왜 tr이 빨랐죠?",
        "용량이 안 넘친 상태라 스래싱은 없었고, 남은 차이는 부하 분산 효율뿐이라 그만큼만 빨랐던 겁니다."),
       ("C=128에서 둘 다 무너진 건 실패 아닌가요?",
        "라우팅으로 못 넘는 물리 한계라 정상입니다. 오히려 '한계가 어디인가'를 보여주는 정보예요.")],
      "약 1.5분")

# ================================================================ 8 stage 2 (3 GRAPHS)
s = slide(); title(s, "결과 2단계 — 스래싱 심화 (KV 용량 압박)", accent=ORANGE)
tb = s.shapes.add_textbox(Inches(0.6), Inches(1.22), Inches(12.2), Inches(0.95))
tf = tb.text_frame; tf.word_wrap = True
_set_runs(tf.paragraphs[0], "정조준: 프로그램마다 **고유한 긴 컨텍스트**를 넣어 KV 용량을 초과 → 재프리필 유도", 15, GRAY)
_set_runs(tf.add_paragraph(), "**tr hit 0.67 vs default 0.02 (~28×)  ·  throughput +57%  ·  p95 97s vs 158s  ·  재프리필 ~10×**", 16, ORANGE)
figs = ["thrash_hit_rate.png", "thrash_throughput.png", "thrash_p95_latency.png"]
caps = ["KV hit rate (핵심)", "throughput", "p95 latency"]
w = Inches(4.25); x0 = Inches(0.15); gap = Inches(0.12); y = Inches(2.5)
for i, f in enumerate(figs):
    x = Emu(int(x0) + i * (int(w) + int(gap)))
    s.shapes.add_picture(os.path.join(FIG, f), x, y, width=w)
    caption(s, x, w, caps[i], 6.85)
note(s, "논문 대조: default 붕괴 = §3.1·Fig 1b·Fig 5의 ‘tool 중 KV evict→재프리필→스래싱’과 방향 일치", top=7.12)
notes(s,
      "KV 용량을 일부러 넘기자 default는 적중률이 붕괴(0.02)하고 tr은 유지(0.67) — 논문의 스래싱 메커니즘을 직접 재현.",
      ["2단계에서는 스래싱을 '정조준'했습니다. 프로그램마다 서로 다른 긴 컨텍스트를 넣어서, 4090의 KV 메모리 용량을",
       "일부러 넘겼어요. 그러면 놀고 있는(툴콜 중인) 프로그램의 KV가 쫓겨나고, 다음 턴에 다시 계산해야 합니다 — 이게 스래싱입니다.",
       "그래프를 봐주세요. 왼쪽이 핵심입니다. KV 적중률이 tr은 0.67로 유지되는데 default는 0.02로 완전히 붕괴합니다. 약 28배 차이예요.",
       "가운데는 처리량인데 tr이 57% 높고, 오른쪽 p95 지연은 높은 부하에서 tr 97초 vs default 158초로 크게 벌어집니다.",
       "재프리필한 토큰 양도 default가 약 10배 많았습니다. 즉 default는 매 턴 앞부분을 반복해서 다시 계산하느라 무너진 거죠.",
       "이게 바로 논문이 말한 현상입니다. 논문 3.1절, Figure 1b, Figure 5에서 'request 단위로 스케줄하면 툴 실행 중 KV가",
       "쫓겨나고 재프리필이 폭발해 적중률이 무너진다'고 했는데, 우리 default가 정확히 그 모습입니다.",
       "다시 강조하지만 숫자를 논문과 맞추는 게 아니라, '이 방향의 현상'이 재현됐다는 게 핵심입니다."],
      [("숫자가 논문(7.14×)과 다른데요?",
        "논문 7.14×는 '지연 배수', 우리 ~10×는 '재프리필 토큰 배수'로 물리량이 다릅니다. 방향만 같다고 봐야 합니다."),
       ("preemption 지표는 0이던데 스래싱 맞나요?",
        "vLLM preemption 대신 '완료 시퀀스의 prefix 캐시 블록 eviction' 형태라, 적중률 붕괴와 재프리필 급증이 스래싱 증거입니다.")],
      "약 2.5분 (오늘의 핵심 슬라이드 — 그래프 중심으로)")

# ================================================================ 9 characterization: token/turn
s = slide(); title(s, "워크로드 특성 (1) — 극단적 input-heavy", accent=GREEN)
bullets(s, [
    ("입력 **~14.5k 토큰/turn** vs 출력 **~28 토큰** → 비용이 **prefill/KV에 몰림**, KV locality가 결정적", 0),
    ("turn 0 = full prefill **~1.82s**, turn 1~3 = prefix 재사용 **~0.13s** (약 **14× 감소**)", 0),
    ("→ ‘프로그램을 같은 곳에 고정하면 왜 이득인지’를 **실측으로** 보여줌", 1),
], top=1.4, width=12.2, size=17)
s.shapes.add_picture(os.path.join(FIG, "char_tokens.png"), Inches(0.35), Inches(3.3), width=Inches(7.1))
caption(s, Inches(0.35), Inches(7.1), "input/output 토큰 분포", 6.7)
s.shapes.add_picture(os.path.join(FIG, "char_turn_breakdown.png"), Inches(7.85), Inches(3.0), width=Inches(5.15))
caption(s, Inches(7.85), Inches(5.15), "turn별 prefill/decode/tool", 6.7)
note(s, "prefill/decode는 vLLM이 요청별 분리 미제공 → 스트리밍 TTFT로 근사한 값 (c=1, 큐 오염 없음)", top=7.06, color=GRAY)
notes(s,
      "이 워크로드는 입력이 출력보다 500배 커서 비용이 prefill/KV에 쏠린다. 그래서 KV 재사용이 결정적임을 실측으로 보인다.",
      ["여기서부터는 'tr vs default 비교'가 아니라 '워크로드 자체가 어떤 성격인가'를 봅니다. 김태현 연구원님이 요청하신 특성 분석이에요.",
       "왼쪽 그래프: 한 턴에 입력이 약 1만4천5백 토큰인데 출력은 28 토큰밖에 안 됩니다. 입력이 압도적으로 커요(input-heavy).",
       "이 말은 계산 비용이 대부분 '입력을 읽어들이는 prefill'과 그걸 저장하는 KV 캐시에 쏠린다는 뜻입니다.",
       "오른쪽 그래프가 핵심입니다. 한 프로그램 안에서 첫 턴(turn 0)은 1만4천 토큰을 통째로 계산하느라 1.82초가 걸리는데,",
       "그다음 턴들(1~3)은 앞부분을 이미 캐시해뒀으니 새로 늘어난 부분만 계산해서 0.13초로 떨어집니다. 약 14배 빨라져요.",
       "즉 '프로그램을 같은 GPU에 고정해서 KV를 재사용하는 것'이 왜 이득인지를 숫자로 직접 보여주는 겁니다.",
       "정직하게 하나 짚으면, prefill과 decode 시간은 vLLM이 요청별로 딱 나눠주지 않아서, 스트리밍의 '첫 토큰까지 시간(TTFT)'으로",
       "근사한 값입니다. 큐 대기가 안 섞이게 동시성 1에서 쟀습니다."],
      [("입력이 왜 이렇게 큰가요?",
        "긴 컨텍스트(고유 필러 ~3천 단어)를 넣었는데, 숫자 토큰이 잘게 쪼개져 실제로 ~1만4천 토큰이 됐습니다. 실측값이에요."),
       ("TTFT 근사가 정확한가요?",
        "정확한 분리는 아니지만 turn0(콜드)와 turn1~3(캐시 히트)의 차이를 보기엔 충분합니다. 근사임을 명시했습니다.")],
      "약 1.5분")

# ================================================================ 10 characterization: KV capacity
s = slide(); title(s, "워크로드 특성 (2) — KV 수용량 ★ heterogeneous 근거", accent=GREEN)
bullets(s, [
    ("KV = **144 KiB/token** (Qwen3-8B config 실측 = vLLM KV풀 로그와 교차검증 일치)", 0),
    ("프로그램당 peak ≈ **2 GiB** → **4090 한 장에 동시 ~3개만 적재**", 0),
    ("§9의 c=48은 용량 **~16× 초과** → 스래싱이 필연이었음을 정량 설명", 0),
    ("★ **5090 ≈ 6.6개 [추정] vs 4090 ≈ 3개** → GPU마다 수용량이 **2배+ 다름**", 0),
], top=1.4, width=12.2, size=17)
s.shapes.add_picture(os.path.join(FIG, "char_kv.png"), Inches(1.75), Inches(3.55), width=Inches(9.8))
caption(s, Inches(1.75), Inches(9.8), "KV 누적(turn별) · GPU 수용량 (4090 실측 / 5090 추정)", 7.05)
notes(s,
      "한 프로그램이 KV로 약 2GiB를 쓰고 4090엔 3개밖에 안 올라간다. GPU마다 수용량이 달라 heterogeneous의 실측 근거가 된다.",
      ["두 번째 특성이자, 오늘 heterogeneous 논의의 '실측 근거'가 되는 슬라이드입니다.",
       "먼저 KV 캐시가 토큰당 얼마나 메모리를 쓰는지 모델 설정에서 계산했더니 토큰당 144KiB였고, vLLM이 실제로 잡은",
       "KV 풀 로그와 교차검증했더니 정확히 일치했습니다. 믿을 수 있는 숫자예요.",
       "이걸로 계산하면 프로그램 하나가 KV로 약 2기가바이트를 씁니다. 4090은 KV 풀이 약 6기가라서, 동시에 3개밖에 못 올립니다.",
       "그래서 아까 2단계에서 동시 48개를 넣은 건 용량의 약 16배를 넘긴 거였어요. 스래싱이 '필연'이었던 걸 숫자로 설명하는 겁니다.",
       "가장 중요한 마지막 줄: 같은 계산을 5090(32기가)에 적용하면 약 6.6개가 올라갑니다. 4090은 3개, 5090은 6.6개 —",
       "GPU마다 수용량이 두 배 넘게 다릅니다. 단, 5090 숫자는 아직 실측이 아니라 '추정'이라는 점을 분명히 합니다.",
       "이 '수용량이 다르다'는 사실이 다음 heterogeneous 슬라이드의 핵심 근거가 됩니다."],
      [("5090 6.6개는 어떻게 나온 건가요?",
        "가중치 등 KV 외 메모리를 고정으로 두고 32GB에 비례 계산한 추정치입니다. 실제 측정은 다음 실험에서 확인할 겁니다."),
       ("왜 4090에 3개뿐인가요?",
        "이 워크로드가 프로그램당 KV 2GiB를 쓰는데 4090 KV 풀이 6GiB라서요. 워크로드가 가벼우면 더 올라갑니다.")],
      "약 2분")

# ================================================================ 11 analysis synthesis
s = slide(); title(s, "결과 분석 종합 — 1→2단계를 논문으로 해석")
bullets(s, [
    ("**1→2 차이의 원인 = 논문 Eq.(6) 스래싱 조건** `C_total < Σ c_p` (§4.3.1)", 0),
    ("1단계: working set이 KV 풀에 **들어감** → 스래싱 없음 → 이득은 부하분산", 1),
    ("2단계: working set이 풀을 **초과** → 스래싱 → **용량 제어가 있는 tr만** 적중률 유지", 1),
    ("우리가 재현한 범위: **3대 기여 중 ① KV 스래싱(§3.1·§4.3.1)만**", 0),
    ("범위 밖(명시): ② cross-node 불균형(§3.2), ③ tool lifecycle(§3.3)", 1),
    ("homogeneous에선 tr이 두 백엔드에 **거의 반반 분배**(동일 GPU라 반반이 최적) — hetero로 가는 다리", 0),
], top=1.5, size=17)
notes(s,
      "1단계와 2단계의 차이는 논문 Eq.(6) 스래싱 조건 하나로 설명된다. 우리가 재현한 건 기여 ①뿐이다.",
      ["이제 앞의 두 결과를 논문으로 '해석'합니다. 왜 1단계에선 안 갈렸는데 2단계에선 극적으로 갈렸을까요?",
       "논문은 스래싱이 언제 생기는지를 아주 명확한 부등식으로 줍니다. 4.3.1절 식 (6): '활성 프로그램들의 KV 합이",
       "GPU 용량을 넘으면' 스래싱이다.",
       "1단계는 컨텍스트가 짧아서 그 합이 용량 안에 들어갔어요. 그래서 스래싱이 없었고, tr의 이득은 부하분산뿐이었죠.",
       "2단계는 용량을 넘겼습니다. 그래서 스래싱이 생겼고, '용량을 아는' tr만 적중률을 지킨 겁니다.",
       "즉 우리 두 실험의 차이가 논문 식 하나로 딱 설명됩니다.",
       "재현 범위도 정직하게 정리합니다. 우리가 보인 건 3대 기여 중 ①번 KV 스래싱뿐입니다. ②노드 간 불균형, ③툴 자원 관리는",
       "단일 노드·합성 툴이라 다루지 않았습니다.",
       "마지막 한 줄이 다리입니다: homogeneous에선 GPU가 같으니 tr이 두 GPU에 거의 반반 나누는 게 최적이었어요.",
       "그런데 GPU가 다르면? 이게 다음 슬라이드입니다."],
      [("Appendix D는 뭔가요?",
        "논문 부록 D인데, 툴이 짧고 예측가능하면 '스래싱 회피=높은 적중률'이 처리량을 지배한다는 내용입니다. 우리 워크로드가 딱 그 경우예요.")],
      "약 1.5분")

# ================================================================ 12 hetero connection (grounded)
s = slide(); title(s, "★ Heterogeneous로의 연결 (실측 + 논문 근거)", accent=ORANGE)
bullets(s, [
    ("GPU가 다르면(4090 vs 5090) **반반 분배는 더 이상 최적이 아님** — 성능·용량 비례로 나눠야", 0),
    ("우리 실측(§10): **4090 ≈ 3개 / 5090 ≈ 6.6개[추정]** → **스래싱 시작점이 백엔드마다 다름**", 0),
    ("논문의 한계(이 버전에서 검증된 근거):", 0),
    ("§4.3.2: restore를 **‘용량 남는 아무 replica’** 로, 재프리필 비용을 **node-agnostic 가정**", 1),
    ("Table 4(BackendState): **용량/토큰만 추적, 처리속도·대역폭 필드 없음**", 1),
    ("§5.1: 논문 하드웨어는 **동질 셋업만** — **GPU를 섞은 실험은 없음**", 1),
    ("→ **[우리 가설]** 균등/용량기반 분배는 **작은 4090을 먼저 스래싱** → **용량·속도 비례 라우팅**이 gap", 0),
], top=1.45, size=16)
note(s, "‘느린 GPU가 먼저 스래싱’은 논문 실험이 아니라 §10 실측 기반 우리 가설([추정]). 논문은 GPU 혼합 실험을 하지 않음", top=6.95)
notes(s,
      "핵심 통찰: GPU가 다르면 반반 분배가 최적이 아니다. 논문은 노드 동질을 가정했고 GPU 혼합은 다루지 않았다 = 우리 연구의 gap.",
      ["오늘의 진짜 핵심입니다. 앞에서 homogeneous에선 반반이 최적이라고 했죠. 그런데 4090과 5090처럼 GPU가 다르면",
       "반반은 더 이상 최적이 아닙니다. 성능과 용량에 '비례해서' 나눠야 해요.",
       "우리 실측 근거가 있습니다. 4090은 프로그램 3개, 5090은 6.6개가 올라가니, 스래싱이 시작되는 지점이 GPU마다 다릅니다.",
       "그럼 논문은 이걸 다뤘을까요? 이 버전 PDF를 꼼꼼히 확인한 결과, 다루지 않았습니다. 근거는 세 가지입니다.",
       "하나, 4.3.2절을 보면 프로그램을 다시 올릴 때 '용량 남는 아무 노드로' 보내고, 재계산 비용이 '어느 노드나 같다'고 가정합니다.",
       "둘, 스케줄러가 보는 노드 상태표(Table 4)에는 용량과 토큰 수만 있고 '처리 속도나 대역폭' 항목이 아예 없습니다.",
       "셋, 5.1절의 실험 하드웨어는 전부 같은 GPU로만 구성돼 있고, 서로 다른 GPU를 한 클러스터에 섞은 실험은 없습니다.",
       "그래서 우리 가설은 이렇습니다 — 이건 논문 주장이 아니라 우리 실측에 기반한 '추정'입니다 —",
       "지금 방식대로 용량만 보고 나누면, 작고 느린 4090이 먼저 스래싱해서 전체 성능을 깎을 겁니다.",
       "따라서 '용량·속도·대역폭에 비례하는 라우팅'이 필요한데, 논문 스케줄러엔 그 축이 없습니다. 여기가 우리 연구의 빈틈입니다."],
      [("논문이 서로 다른 GPU를 비교하거나 섞은 실험이 있나요?",
        "이 버전 PDF엔 GPU를 섞거나 종류별로 비교한 실험이 없습니다. 그래서 그런 근거는 인용하지 않고, 우리 §10 실측으로만 논증합니다."),
       ("왜 작은 GPU가 먼저 스래싱하죠?",
        "KV 용량이 작아 식(6)을 더 빨리 넘고, 재프리필도 느려서요. 다만 이건 아직 우리 가설이라 다음 실험에서 확인합니다.")],
      "약 2분 (핵심 통찰 — 천천히)")

# ================================================================ 13 next experiment (hypothesis + plan)
s = slide(); title(s, "다음 실험 — Heterogeneous 가설 & 검증 계획", accent=ORANGE)
bullets(s, [
    ("**① 가설 (§12)**", 0),
    ("H1 현상: 용량기반 분배 → **4090이 먼저 용량 초과(~3개) → 먼저 스래싱 → 전체가 4090 병목** [가설]", 1),
    ("H2 원인: 스케줄러가 **GPU 속도·대역폭·용량 차이를 모름** (Table 4·§4.3.2 node-agnostic = 동질 가정)", 1),
    ("H3 해법: **용량(·속도) 비례 분배 (≈2.2:1)** → 스래싱 시작점 정렬 → throughput↑ [가설]", 1),
    ("**② 검증 설계**: mango 4090 + goguma6 5090, §9 워크로드 재사용", 0),
    ("arm **(a) tr 현행 vs (c) 용량비례**(+참고 default) · 지표: **백엔드별 hit rate·스래싱 시작 C**, throughput/p95, 분배비율", 1),
    ("예상: 현행=**4090 hit 먼저 붕괴·4090서 꺾임** / 용량비례=**두 곡선 비슷·꺾임 뒤로**", 1),
    ("**③ 열린 질문**: 비례 기준(용량만? 속도·대역폭?) · locality 희생 정도 · **5090 실측** · 실제 워크로드 · 반복측정(에러바)", 0),
], top=1.4, size=15, gap=5)
notes(s,
      "핵심 가설: 이종 클러스터에서 현행 용량기반 분배는 작은 4090을 먼저 스래싱시켜 전체가 병목된다. 용량비례 분배로 이를 정렬하면 개선될 것. 다음 실험으로 검증한다.",
      ["다음 단계를 '가설 → 검증 설계 → 열린 질문' 세 부분으로 말씀드리겠습니다. 아직 안 한 계획이라 숫자는 전부 예상입니다.",
       "먼저 가설입니다. 세 단계로 나눴어요.",
       "H1(현상): 4090과 5090을 섞으면, 지금 tr은 용량만 보고 둘에 비슷하게 나눕니다. 그런데 4090은 프로그램 3개면 꽉 차니까",
       "4090이 먼저 한계를 넘겨 거기서부터 스래싱이 나고, 5090이 놀고 있어도 전체 속도가 4090에 발목 잡힙니다.",
       "H2(원인): 왜 그럴까요? 스케줄러가 보는 백엔드 상태표(Table 4)에 용량·토큰만 있고 GPU '속도·대역폭'이 없어서예요.",
       "게다가 논문 4.3.2절은 재계산 비용을 '어느 노드나 같다(node-agnostic)'고 가정합니다. 이건 GPU가 같을 때만 맞는 전제죠.",
       "H3(해법): 그러니 용량에 비례해서, 우리 §10 실측 기준 대략 5090:4090 = 2.2 대 1로 나눠주면 두 GPU가 비슷한 시점에",
       "차오르니, 한쪽만 먼저 무너지는 일이 줄어 전체 처리량이 올라갈 것이다 — 이게 우리 가설입니다.",
       "둘째, 검증 설계입니다. mango의 4090 하나와 goguma6의 5090 하나로 이종 구성을 만들고, 워크로드는 스래싱을 유도했던",
       "§9 설정을 그대로 씁니다. 비교는 최소한 (a) 지금의 tr과 (c) 우리가 제안하는 용량비례 라우팅을 대볼 겁니다.",
       "지표가 중요합니다. 전체 숫자만 보면 안 되고, 4090과 5090의 KV 적중률을 '따로' 보고 어느 쪽이 먼저 꺾이는지,",
       "그리고 실제로 각 GPU에 몇 개씩 갔는지(분배 비율)를 봅니다. 가설이 맞다면 현행 tr에선 4090 적중률이 먼저 무너지고,",
       "용량비례에선 두 곡선이 비슷해지며 꺾이는 지점이 뒤로 밀릴 겁니다. 반대로 나오면 가설을 수정해야죠.",
       "셋째, 논의하고 싶은 열린 질문입니다. 비례 기준을 용량만 볼지 속도·대역폭까지 볼지, locality를 얼마나 포기할지,",
       "5090 수용량 추정을 언제 실측할지, 실제 워크로드를 도입할지, 그리고 반복측정으로 에러바를 넣는 것입니다."],
      [("왜 '용량비례'가 답이라고 보나요?",
        "§10에서 4090 3개·5090 6.6개로 수용량이 다른 게 실측됐고, §9에서 용량 초과가 곧 스래싱임을 봤습니다. 그러니 용량에 맞춰 나누면 두 GPU의 스래싱 시작점이 정렬됩니다. 다만 이건 가설이라 (a) vs (c)로 검증합니다."),
       ("속도·대역폭은 왜 아직 안 보나요?",
        "§10에서 KV '용량'은 실측했지만 속도·대역폭의 영향은 아직 측정 못 했습니다. 그래서 1차로 용량비례부터 검증하고, 필요하면 속도항을 가중치에 더할 계획입니다(열린 질문)."),
       ("5090 실측은 언제 하나요?",
        "다음 실험 첫 스텝에서 바로 확인됩니다. 5090에 vLLM을 띄우면 시작 로그에 KV 풀 토큰 수가 찍혀서, 6.6개 추정이 맞는지 즉시 검증됩니다.")],
      "약 2분")

# ================================================================ 14 appendix
s = slide(); title(s, "부록 — 재현 방법 & 재현 안 한 기여")
bullets(s, [
    ("재현: 2× vLLM(env 우회) + ThunderAgent 프록시(tr/default) → 합성 드라이버 concurrency 스윕 → 그래프", 0),
    ("스래싱 유도: 드라이버 `--ctx-tokens` (프로그램별 고유 긴 컨텍스트) / 특성: `--stream`(TTFT 근사)", 0),
    ("**재현 안 한 논문 기여**: ② cross-node 메모리 불균형(§3.2), ③ tool lifecycle 관리(§3.3)", 0),
    ("산출물(브랜치 `yunuikang/thunderagent`): EXPERIMENT_LOG · SETUP_NOTES · figures/", 0),
])
notes(s,
      "재현 방법 요약과, 재현하지 않은 논문 기여(②③)를 명시하는 백업 슬라이드.",
      ["부록입니다. 질문이 나오면 쓰려고 둔 백업 슬라이드예요.",
       "재현 방법은 vLLM 2개와 프록시를 띄우고 합성 드라이버로 동시성을 올려가며 재는 구조입니다.",
       "스래싱은 드라이버 옵션으로 프로그램별 긴 컨텍스트를 넣어 유도했고, 특성 분석은 스트리밍으로 TTFT를 근사해 측정했습니다.",
       "그리고 다시 강조하면, 논문의 ②노드 간 불균형과 ③툴 자원 관리는 이번 범위 밖입니다.",
       "모든 산출물은 제 git 브랜치에 정리돼 있습니다."],
      [("cross-node는 왜 안 했나요?",
        "단일 노드 실험이라 노드 간 불균형 현상 자체가 생기지 않습니다. heterogeneous 다음 단계에서 자연스럽게 이어집니다.")],
      "약 0.5분 (필요 시)")

prs.save(OUT)
print("saved:", OUT, "slides:", len(prs.slides._sldIdLst))
