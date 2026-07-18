#!/usr/bin/env python3
"""slides/2026-07-17_vllm-profiling_yunuikang.pptx 생성.

원칙: 슬라이드당 메시지 1개, 본문은 그림 중심(텍스트 최소), 근거·수치·[추정]·한계는 전부 노트.
모든 사실·수치·코드 라인은 logs/2026-07-17_VLLM_PROFILING_yunuikang.md 에 실제로 쓴 것만 사용.
"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
import os

REPO = "/home/yunuikang/yunuikang_work/distserving"
FIG = f"{REPO}/figures"
OUT = f"{REPO}/slides/2026-07-17_vllm-profiling_yunuikang.pptx"

W, H = Inches(13.333), Inches(7.5)
NAVY = RGBColor(0x1F, 0x35, 0x53)
RED = RGBColor(0xC0, 0x39, 0x2B)
BLUE = RGBColor(0x2E, 0x86, 0xAB)
GREY = RGBColor(0x7F, 0x8C, 0x8D)
GREEN = RGBColor(0x1E, 0x8A, 0x5A)

prs = Presentation()
prs.slide_width, prs.slide_height = W, H
BLANK = prs.slide_layouts[6]


def add(title, subtitle=None, img=None, notes="", tcolor=NAVY, img_top=1.42, img_h=5.5):
    s = prs.slides.add_slide(BLANK)
    tb = s.shapes.add_textbox(Inches(0.52), Inches(0.30), W - Inches(1.04), Inches(0.62))
    p = tb.text_frame.paragraphs[0]
    r = p.add_run(); r.text = title
    r.font.size = Pt(27); r.font.bold = True; r.font.color.rgb = tcolor
    tb.text_frame.word_wrap = True
    if subtitle:
        sb = s.shapes.add_textbox(Inches(0.55), Inches(0.94), W - Inches(1.1), Inches(0.44))
        sp = sb.text_frame.paragraphs[0]
        sr = sp.add_run(); sr.text = subtitle
        sr.font.size = Pt(13.5); sr.font.color.rgb = GREY
        sb.text_frame.word_wrap = True
    if img:
        path = os.path.join(FIG, img)
        from PIL import Image
        iw, ih = Image.open(path).size
        maxw, maxh = W - Inches(1.1), Inches(img_h)
        scale = min(maxw / iw, maxh / ih)
        w, h = int(iw * scale), int(ih * scale)
        s.shapes.add_picture(path, int((W - w) / 2), Inches(img_top), w, h)
    s.notes_slide.notes_text_frame.text = notes
    return s


def bullets(s, items, top=1.5, left=0.7, width=11.9, size=15, gap=0.52):
    tb = s.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(gap * len(items) + 0.4))
    tf = tb.text_frame; tf.word_wrap = True
    for i, (txt, color, bold) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        r = p.add_run(); r.text = txt
        r.font.size = Pt(size); r.font.color.rgb = color; r.font.bold = bold
        p.space_after = Pt(11)
    return tb


# ------------------------------------------------------------------ 1 title
s = prs.slides.add_slide(BLANK)
tb = s.shapes.add_textbox(Inches(0.9), Inches(2.3), W - Inches(1.8), Inches(1.5))
p = tb.text_frame.paragraphs[0]
r = p.add_run(); r.text = "vLLM은 실제로 어떻게 동작하는가"
r.font.size = Pt(42); r.font.bold = True; r.font.color.rgb = NAVY
p2 = tb.text_frame.add_paragraph()
r2 = p2.add_run(); r2.text = "우리가 머릿속에 그린 GPU 그림 vs 코드·프로파일이 말하는 것"
r2.font.size = Pt(20); r2.font.color.rgb = GREY
tb2 = s.shapes.add_textbox(Inches(0.9), Inches(4.4), W - Inches(1.8), Inches(1.6))
tf = tb2.text_frame; tf.word_wrap = True
for t, c, b in [("강윤의 · 2026-07-17 · 브랜치 yunuikang/thunderagent", GREY, False),
                ("근거: vLLM 0.24.0 실소스 정독 + expC 재분석 + 마이크로벤치(GPU 승인 후 실행)", GREY, False),
                ("router.py 미수정 · 모든 수치는 실측 · 철회한 주장은 철회로 표기", GREEN, True)]:
    pp = tf.add_paragraph(); rr = pp.add_run(); rr.text = t
    rr.font.size = Pt(14); rr.font.color.rgb = c; rr.font.bold = b
s.notes_slide.notes_text_frame.text = (
    "목적: R=k_fit·d, U≈min(R,1) 현상 모델(4090에서 r=0.959)이 블랙박스였다. "
    "vLLM 내부에서 실제로 무슨 일이 일어나는지 코드와 데이터로 검증했다.\n\n"
    "환경: mango1 4×RTX4090 전부 유휴(TP2 스윕은 nutella1이라 무간섭). "
    "가드레일 준수 — GPU를 한 번도 잡지 않았고, 필요한 마이크로벤치는 마지막 슬라이드에서 승인 요청.\n\n"
    "산출물: logs/2026-07-17_VLLM_PROFILING_yunuikang.md, figures/vllm_*.png, "
    "scripts/plot_vllm_profiling_yunuikang.py + plot_vllm_diagrams_yunuikang.py")

# ------------------------------------------------------------------ 2 summary
s = add("결론", "R 모델은 살아남았고, 식이 닫혔다. 그러나 우리가 그린 그림 두 개는 틀렸다.")
bullets(s, [
    ("1.  R = k_fit·d 는 물리량이었다 — 'vLLM에서 동시 실행 중인 요청 수의 기댓값'.  실측 mean nrr과 일치 (1.20 vs 1.24)", NAVY, True),
    ("2.  틀린 그림 ①  'default는 배치를 크게 가져간다' → 거짓.  실제 배치는 tr·default 모두 1.1~1.5 고정.", RED, True),
    ("     틀린 그림 ②  'default는 pause가 0' → 착시.  default도 줄을 선다 — vLLM 내부에서 (TTFT 10.8s 중 ~9.5s).", RED, True),
    ("3.  hit 지표 오염은 비대칭이었다 (실측):   default 26.3x 팽창 → 참값 4.8배 과소평가 (0.184 vs 0.038)", RED, True),
    ("                                          tr 1.0x 팽창 → 애초에 정확 (0.698 = 0.698)", GREY, False),
    ("4.  ★ 그래서 throughput 식이 닫혔다.  참 hit 대입 →  예측 오차 28.2% → 1.4%", GREEN, True),
    ("5.  정직:  '2.3초 vs 18.5초, 8.2배'는 정정 →  9.5초 vs 20.8초, 2.2배.   'tr 데드락' 발견은 내 하네스 버그로 철회.", GREY, True),
], top=1.6, size=14.5, gap=0.46)
s.notes_slide.notes_text_frame.text = (
    "1번은 좋은 소식: R이 우연히 맞는 회귀식이 아니라 물리량이었다. R = 동시에 GPU 일을 원하는 요청 수의 기댓값, "
    "U = P(nrr>=1). R<1이면 점유가 대부분 0/1이라 P(N>=1)~E[N]=R — U~R은 근사 항등식. r=0.959의 진짜 이유.\n\n"
    "3번이 오늘의 핵심 발견이다. 오염이 비대칭인 게 결정적: tr은 프록시에서 미리 막아 요청이 vLLM 큐에 안 쌓이므로 "
    "재검사가 0회 → 팽창 1.0x → 참 hit == 보고 hit (0.6983 = 0.6983, 소수 4자리 일치). "
    "default만 26.3x 팽창 → 4.81배 과소평가. 즉 지표 버그와 물리 메커니즘이 같은 현상이다.\n\n"
    "4번: 그 덕에 Phase 3에서 '안 닫힌다'고 정직히 열어뒀던 고리가 닫혔다. hit만 참값으로 바꿔 넣으니 "
    "예측 1.035(오차 28.2%) → 1.421(오차 1.4%). 실측 1.441.\n\n"
    "5번 정직 포인트 두 가지: (a) H1의 8.2배는 재프리필 계산분만 센 것이라 정정 — 부하 하 TTFT를 재니 "
    "default의 진짜 벌금은 9.5초(숨은 큐 포함), tr은 20.8초 → 2.2배. 방향은 유지. "
    "(b) 실험 도중 'tr 스케줄러 데드락'을 발견했다고 판단했으나 내가 --router-url을 안 넘겨 "
    "/programs/release가 9000번으로 가서 실패한 자작 버그였다. 전면 철회했고 expC 데이터는 깨끗하다.\n\n"
    "결론이 뒤집힌 건 없다. tr이 R<1에서 지고 R>=1에서 이긴다는 결론은 그대로다.")

# ------------------------------------------------------------------ 3 iteration anatomy
add("한 iteration의 진실 — prefill/decode 단계 구분이 없다",
    'scheduler.py:390-399  "There\'s no decoding phase nor prefill phase in the scheduler."',
    "vllm_iteration_anatomy.png", img_top=1.5, img_h=5.4,
    notes=(
        "vLLM V1은 통합 배치다. 매 iteration마다 각 요청의 num_computed_tokens가 num_tokens_with_spec를 "
        "따라잡도록 토큰을 배분할 뿐, prefill 단계/decode 단계라는 구분 자체가 없다.\n\n"
        "핵심 수치 — max_num_batched_tokens = 2048. [코드 유도]\n"
        "  arg_utils.py:2404 이 device memory 70GiB를 기준으로 갈린다. 4090은 24GB < 70GiB → else 분기 → "
        "  OPENAI_API_SERVER 기본값 2048 (arg_utils.py:2414-2423), 이후 min(256×32768, 2048)=2048 (:2638-2641).\n"
        "  max_num_seqs = 256 (:2420-2423, :2649-2651) — k_fit 1.6~10.5에 전혀 안 걸리므로 제약이 아니다. "
        "  병목은 seq 슬롯이 아니라 KV 블록이다.\n\n"
        "✅ 실측 확정(2026-07-17): 실제 RTX4090에서 EngineArgs.get_batch_defaults(world_size=1)를 직접 실행 → "
        "OPENAI_API_SERVER: batched_tokens 2048 / max_num_seqs 256. device 확인 'NVIDIA GeForce RTX 4090, 24.0 GiB'. "
        "(logger.info_once 라인은 여전히 로그에 안 남지만 코드 경로로 확정.) Pro6000은 96GB≥70GiB → 8192/1024.\n\n"
        "순서가 중요: RUNNING을 먼저 스케줄하고(:432) 그 다음 WAITING(:626). 따라서 decode는 프리필에 의해 "
        "admission에서 밀려나지 않는다 — budget 2048 ≫ max_num_seqs 256이라 decode 1토큰짜리는 항상 들어간다. "
        "'프리필이 decode를 밀어낸다'는 우리 서술은 부정확하다.\n\n"
        "그러나 결과: TraceLab 프롬프트 18,684 tok(mean)은 2048 예산을 약 10 iteration 독점한다. "
        "이게 다음 슬라이드의 '배치가 안 커지는 이유'다.")
)

# ------------------------------------------------------------------ 4 timeline
add("★ GPU는 '배치'가 아니라 '시간축'으로 채워진다",
    "실제 타임라인 — 빨강(실제 GPU 배치)은 낮고 평평, 파랑(파견됨)만 높다",
    "vllm_timeline_tr_vs_default.png", img_top=1.5, img_h=5.4,
    notes=(
        "내 질문이었다: continuous batching이면 'GPU가 채워진다'는 (a) 시간축을 요청들이 번갈아 메우는 것인가, "
        "(b) 한 iteration의 배치가 커지는 것인가?\n\n"
        "답: (a) 시간축이다. 데이터가 명확하다.\n"
        "  k_fit(프록시 resident)  1.60(tr) → 6.15(default C=16) → 10.50(C=32)   = 6.6배\n"
        "  실제 GPU 배치           1.19    → 1.45              → 1.44           = +21%뿐\n"
        "  U(nrr>0)               0.317   → 0.855             → 0.893          = 2.7배\n\n"
        "즉 default가 이기는 이유는 '한 번에 더 많이 처리해서'가 아니라 '노는 시간이 적어서'다.\n\n"
        "그림 읽는 법: 빨간 채움 = vLLM num_requests_running(2백엔드 합). 파란 선 = 프록시가 REASONING이라 "
        "믿는 수. default 패널에서 파랑이 10~13인데 빨강이 3~4다 — 이 간격이 vLLM 내부 큐다(슬라이드 7).\n"
        "3개 블록은 REPEAT=3.\n\n"
        "내가 그려온 그림 채점: 'TraceLab tr = 구멍 뚫림 U≈0.38' ✅ 맞음. 'default = 빽빽 U≈0.87' ✅ 맞음. "
        "'빽빽함 = 배치가 큼' ❌ 틀림. → 그림의 '얼마나 차 있나'는 맞았고 '왜 차 있나'가 틀렸다.")
)

# ------------------------------------------------------------------ 5 H2 refuted
add("H2(배치 무료점심) — 반증됨", "k_fit이 6~10이어도 실제 GPU 배치는 1.1~1.5를 벗어나지 않는다",
    "vllm_batch_refutes_H2.png", img_top=1.62, img_h=5.2,
    tcolor=RED,
    notes=(
        "H2 가설: 'decode는 memory-bandwidth-bound라 batch 1~8의 step latency가 비슷하다. default는 resident "
        "6.15로 tr(1.6)의 4배 일을 같은 시간에 한다. default의 이득은 recompute를 감수하고 산 batching이다.'\n\n"
        "→ 기각. 마이크로벤치가 필요 없었다. 실제 배치(mean nrr | nrr>0)가 전 구간 1.13~1.45다. "
        "default C=32조차 1.44. tr 1.19 대비 +21%이지 4배가 아니다.\n\n"
        "왜 k_fit=6.15인데 배치가 1.45인가 — k_fit을 분해하면:\n"
        "  default C=16: k_fit 6.15 = REASONING 4.56 + ACTING 1.59.  그런데 vLLM mean nrr = 1.24.\n"
        "  → ACTING 1.59는 tool 실행 중이라 애초에 off-GPU.  REASONING 4.56 중 실제 실행은 1.24, "
        "     나머지 3.32는 vLLM 큐 대기.\n"
        "즉 k_fit은 'GPU에 올라간 수'가 아니다. 우리가 이 이름을 계속 쓰면 오해를 부른다.\n\n"
        "부수 결론: CUDA graph 버킷은 [1,2,4,8,16,24,32,...] 51개(기동 로그 실측)로 촘촘해서 batch 1과 4는 "
        "서로 다른 그래프를 쓴다. 따라서 'batch 1이든 4든 비슷하다'는 직관은 CUDA graph 패딩으로는 설명 안 된다. "
        "[추정] 다만 memory-bound 물리로는 여전히 옳을 수 있는데, 실제 배치가 1.1~1.5로 고정이라 "
        "이 질문 자체가 우리 워크로드에선 무의미해졌다 → decode batch 커브 마이크로벤치는 실익이 낮아 생략 권고.")
)

# ------------------------------------------------------------------ 6 R physical meaning
s = add("R의 물리적 의미가 확정됐다", "R = k_fit·d = 동시에 GPU 일을 원하는 요청 수의 기댓값 ≈ mean num_requests_running")
rows = [
    ("run", "R = k_fit·d", "실측 mean_nrr", "오차"),
    ("default C=4", "0.36", "0.36", "0.00"),
    ("default C=8", "0.67", "0.92", "+0.25"),
    ("default C=16", "1.20", "1.24", "+0.04"),
    ("tr C=16", "0.31", "0.38", "+0.07"),
    ("default C=32", "2.06", "1.29", "−0.77  ← 포화(배치 1.44 상한)"),
]
tbl = s.shapes.add_table(len(rows), 4, Inches(1.3), Inches(1.75), Inches(8.4), Inches(2.7)).table
for c, wdt in zip(range(4), [2.3, 2.0, 2.0, 2.1]):
    tbl.columns[c].width = Inches(wdt)
for i, row in enumerate(rows):
    for j, val in enumerate(row):
        cell = tbl.cell(i, j); cell.text = val
        pr = cell.text_frame.paragraphs[0]
        pr.alignment = PP_ALIGN.CENTER
        for rn in pr.runs:
            rn.font.size = Pt(13); rn.font.bold = (i == 0 or i == len(rows) - 1)
            rn.font.color.rgb = NAVY if i == 0 else (RED if i == len(rows) - 1 else RGBColor(0x33, 0x33, 0x33))
bullets(s, [
    ("U = P(nrr ≥ 1).   R<1이면 점유가 대부분 0/1 →  P(N≥1) ≈ E[N] = R  →  U ≈ R 은 근사 항등식", NAVY, True),
    ("R≥1에서 nrr이 1.44에 묶이는 것이 '실측 U가 예측 U를 하회'(expC §5 한계)의 정확한 물리적 원인", GREY, False),
], top=4.75, size=15)
s.notes_slide.notes_text_frame.text = (
    "이게 오늘의 가장 좋은 소식이다. R은 우연히 맞는 회귀식이 아니었다.\n\n"
    "R = k_fit × d 의 의미: k_fit개 프로그램이 각자 자기 시간의 d 비율만큼 GPU 일을 한다면, "
    "동시에 GPU 일을 원하는 프로그램 수의 기댓값 = k_fit × d. 이게 정확히 vLLM의 mean num_requests_running이다. "
    "표에서 default C=4(0.36 vs 0.36)와 C=16(1.20 vs 1.24)은 거의 완벽히 일치한다.\n\n"
    "그리고 U = P(nrr≥1) = GPU가 일감을 갖고 있던 시간 비율. R이 작으면 동시에 2개 이상 겹칠 확률이 낮아 "
    "N이 거의 0 아니면 1 → E[N] ≈ P(N≥1). 그래서 U≈R.\n\n"
    "C=32에서 R=2.06인데 nrr=1.29로 포화하는 이유: 배치가 1.44에 물리적으로 묶여 있어서(슬라이드 5). "
    "이것이 expC 한계 항목 '실측 U가 고R에서 예측 하회'의 정확한 기전이다 — 이제 설명할 수 있다.\n\n"
    "[추정] C=8에서 +0.25 오차가 상대적으로 큰데, 원인은 미규명. d=0.196이 c=1 고유값이라 부하 하에서 "
    "약간 달라지는 것일 수 있다(expC가 이미 기록한 한계).\n\n"
    "용어 권고: R을 '활용률'이라 부르지 말고 '요청 수요(demand in server-units)'라 부르는 게 정확하다.")

# ------------------------------------------------------------------ 7 where queue
add("tr과 default는 '줄을 서느냐'가 아니라 '어디서 서느냐'가 다르다",
    "default의 pause_s=0.00은 줄을 안 선다는 뜻이 아니다 — profiler가 못 볼 뿐",
    "vllm_where_queue.png", img_top=1.55, img_h=5.3, tcolor=RED,
    notes=(
        "H4(tr 프록시 오버헤드 가설)를 보다가 나온 반전이다.\n\n"
        "REASONING − nrr 갭 = 프록시는 '추론 중'이라 믿지만 vLLM은 실행하지 않는 프로그램 수:\n"
        "  tr C=16       0.11개   (프록시가 미리 막아서 vLLM 큐에 안 쌓임)\n"
        "  default C=16  3.32개\n"
        "  default C=32  7.52개\n\n"
        "완전히 다른 경로의 독립 증거 2종이 같은 결론을 가리킨다:\n"
        "  ① REASONING − nrr 갭 (프록시 상태 vs vLLM 상태 대조)\n"
        "  ② queries 팽창 30배 (vLLM 내부 카운터, 슬라이드 8)\n"
        "두 지표가 서로 무관한 계측 경로인데 같은 것(vLLM 큐 정체)을 말한다 — 그래서 신뢰할 만하다.\n\n"
        "왜 preemption이 아니라 큐 정체인가: preemption은 이미 RUNNING인 요청이 decode 중 블록을 더 못 얻을 때만 "
        "발생하는데(scheduler.py:524-568), 우리 출력은 44.8~55 토큰뿐이라 추가로 필요한 블록이 ⌈55/16⌉≈4개다. "
        "반면 신규 프리필은 18.7k tok = 1,168 블록을 요구한다. → 경합은 waiting 승인 단계에서 전부 해소되고 "
        "RUNNING까지 간 요청은 안 밀린다. 실측 preemption≈0과 정합. 우리 관찰이 코드로 설명됐다.\n\n"
        "H4 판정 한계(정직): pause가 완전히 0인 tr 점이 expC에 없다(tr은 C=4부터 이미 pause 발생). "
        "따라서 H4는 기존 데이터로 완전 판정 불가. 다만 슬라이드 9의 수치가 pause만으로 격차를 설명하므로 "
        "프록시 고정 오버헤드가 주원인일 가능성은 낮다 [추정].")
)

# ------------------------------------------------------------------ 8 counter contamination
add("우리 hit rate 지표는 오염돼 있다", "vLLM은 승인 실패한 대기 요청을 매 step 재계수한다 → default C=32에서 30배 팽창",
    "vllm_queries_inflation.png", img_top=1.6, img_h=5.2, tcolor=RED,
    notes=(
        "DEEP_ANALYSIS §B-1의 미해결 질문을 코드로 확정했다. 그런데 답이 우리 가설과 달랐다.\n\n"
        "우리 가설: 'queries≈222M vs prompt≈7M가 1:1로 안 맞는다, granularity가 다른 듯.'\n"
        "실제: granularity는 같다. 둘 다 프롬프트 전체 길이를 센다.\n"
        "  kv_cache_manager.py:236-240  record(num_tokens=request.num_tokens, ...)  ← 프롬프트 전체\n"
        "  stats.py:308                 self.total += prefill_stats.num_prompt_tokens  ← 같은 값\n\n"
        "진짜 원인 = waiting 큐 재검사 중복 계수:\n"
        "  :636  peek_request()  ← pop이 아니다\n"
        "  :673  if num_computed_tokens == 0:  →  :710 get_computed_blocks() → record() 발생\n"
        "  :888-895  allocate 실패 → break  (pop_request는 :917로 그 뒤)\n"
        "  :1141-43  num_computed_tokens는 '스케줄된' 요청만 전진 → 거부된 요청은 0에 머문다\n"
        "→ 승인될 때까지 매 step 재기록. 팽창 배수 ≈ 큐 head에서 재검사된 step 수.\n\n"
        "예측대로 경합에 비례한다: tr 1.9~2.1 평탄 / default 3.81 → 18.75 → 29.56 → 30.05.\n"
        "그리고 보고 hit rate가 팽창과 정확히 역상관(0.649→0.030).\n\n"
        "판정:\n"
        "  ✅ prompt_tokens_total 폐기는 옳았다 (코드로 확증 — 논리적 총량, 캐시 무관).\n"
        "  ✅ 절대 미스량 불신도 옳았다 — 단 이유가 'granularity'가 아니라 '재검사'다. §B-1 문장 교체 필요.\n"
        "  ⚠️ 그러나 '미스율(1−hit)은 robust하다'는 부분적으로 틀렸다. 미스율도 같은 오염을 공유한다 — "
        "     재검사 많은 요청이 집계에서 가중치 N배를 받는다.\n"
        "  ✅ 대안이 있었다(우리가 놓쳤다): vllm:prompt_tokens_by_source{source=\"local_compute\"} = 실제 계산 토큰. "
        "     불변식 computed + local_cache_hit + external_kv_transfer = total (stats.py:287-289). "
        "     실제 prefill 출력에서만 누적돼 재검사 오염이 없다.\n\n"
        "결론: 방향(tr≫default)은 견고. 절대값 0.037은 신뢰 불가.")
)

# ------------------------------------------------------------------ 9 H1
add("H1 — 답: default의 벌금이 실제로 싸다", "캐시 미스 1회의 한계비용을 c=1 프로파일에서 실측했다",
    "vllm_prefill_curve.png", img_top=1.5, img_h=4.5, tcolor=GREEN,
    notes=(
        "이게 Phase 2의 핵심 질문이었다: 'default는 hit이 0.80→0.03으로 붕괴하고 재프리필을 폭증시키는데, "
        "왜 그러고도 더 빠른가?' — 동어반복 없이 답해야 했다.\n\n"
        "실측 (c=1 duty 프로파일, prof_duty/step_profiles.csv):\n"
        "  cold (step 1, 캐시 없음, n=25):  TTFT = 1.696e-4 × ptok − 0.450,  r² = 0.981\n"
        "     → 프리필은 프롬프트 길이에 선형 = compute-bound. 한계율 5,896 tok/s.\n"
        "  warm (step>1, prefix 히트, n=62): 평균 0.462 s, r² = 0.047 (평탄)\n"
        "     → 히트 시 신규 토큰만 계산하므로 길이와 무관. TTFT가 프롬프트 길이와 무상관(r=−0.014)인 게 이 때문.\n\n"
        "mean 프롬프트 18,684 tok 기준:\n"
        "  완전 미스 = 1.696e-4 × 18684 − 0.450 = 2.72 s   /   히트 = 0.46 s\n"
        "  → 캐시 미스 1회의 한계비용 Δ ≈ 2.26 s/turn\n\n"
        "★ 최초 계산: default 벌금 ≈ 2.3초/step vs tr ≈ 18.5초/step → 8.2배.\n"
        "★★ 그러나 GPU 마이크로벤치로 정정됨(슬라이드 17): 부하 하 TTFT를 재니 default의 진짜 벌금은 "
        "9.5초/step(재프리필 2.3초 + 숨은 vLLM 큐 ~7.2초)이고 tr은 20.8초/step. → 2.2배. "
        "H1의 방향(default 벌금 < tr 벌금)은 유지되나 격차는 8.2배가 아니라 2.2배다. 발표 시 2.2배로 말할 것.\n\n"
        "인과: R<1이면 GPU에 bubble이 있다 → 재프리필 2.26s는 어차피 놀던 시간에 지불되므로 throughput 손해가 "
        "거의 없다. 반면 pause 18.5s는 병목도 아닌 GPU 앞에서 실제 일을 막는 순손실이다. "
        "캐시 히트의 가치 = 절약된 prefill 시간 × P(GPU가 병목). R<1이면 P≈0이라 hit=0.03이어도 거의 공짜다.\n\n"
        "검산: tool_call_s는 tr 5.99 / default 6.08로 동일 → 워크로드 고유값이 양쪽 같음을 재확인.\n"
        "d 검산: (0.889 + 0.856)/(0.889+0.856+7.164) = 0.196 → expC의 d와 정확히 일치.\n\n"
        "H3도 지지: default hit이 0.649→0.030으로 21배 붕괴하는데 throughput은 0.092→0.097로 평탄(오히려 소폭 상승).")
)

# ------------------------------------------------------------------ 10 Phase 4
add("U 측정은 견고하다 — 단, 지시서의 전제는 틀렸다",
    "U는 nvidia-smi가 아니었다. 그럼에도 3종 독립 측정이 일치한다 (r = 0.999)",
    "vllm_U_triangulation.png", img_top=1.6, img_h=5.1,
    notes=(
        "먼저 전제 정정. 지시서는 '우리 U는 1 − idle(1초 샘플러 + nvidia-smi util)'이라고 했지만, "
        "실제 코드(plot_expC_yunuikang.py:47-62)는 U_meas = mean(b0_reasoning > 0), 즉 프록시가 보고하는 "
        "REASONING 프로그램 수 > 0인 1초 틱의 비율이다. nvidia-smi util은 gpu_util 칼럼에 기록만 되고 "
        "U 계산에는 안 쓰였다.\n\n"
        "U가 정확히 무엇을 재는가(확정): 'GPU 점유율'이 아니라 '프록시 관점에서 최소 한 개의 프로그램이 추론 요청을 "
        "파견한 상태로 있었던 시간의 비율'이다. SM occupancy도 커널 점유율도 아니며, vLLM 내부 큐 대기 시간까지 "
        "'바쁨'으로 포함한다(default C=16 기준 3.32 프로그램이 이 착시). 1초 샘플링이라 1초보다 짧은 bubble은 안 보인다.\n\n"
        "그럼에도 견고한 이유 — 세 독립 측정을 전부 계산해 비교했다:\n"
        "  tr C=16:       proxy 0.375 / nrr 0.317 / smi 0.349\n"
        "  default C=16:  proxy 0.873 / nrr 0.855 / smi 0.861\n"
        "  cross ts=2.0:  proxy 0.224 / nrr 0.186 / smi 0.214\n"
        "  상관: smi vs nrr r=0.999, proxy vs nrr r=0.999. 평균 절대차 ≤ 0.06.\n\n"
        "'batch 1과 batch 32가 똑같이 100%로 보인다'는 우려는 이 데이터에선 발생하지 않았다 — util이 100%에 "
        "붙어있지 않기 때문(0.21~0.90 전 구간 분포). 그 우려는 util이 포화했을 때만 문제인데, "
        "우리 R<1 레짐은 정의상 비포화다. → 'U=0.87 vs 0.37' 해석은 흔들리지 않는다. R 모델 유효.\n\n"
        "다만 용어: U를 'GPU 활용률'이 아니라 'GPU가 일감을 갖고 있던 시간 비율(busy-time fraction)'로 부르는 게 정확하다.\n\n"
        "[추정] SM occupancy는 여전히 미측정. 그러나 실제 배치가 1.1~1.5로 고정임이 밝혀졌으므로 "
        "SM 점유율은 tr·default가 거의 같을 것이고 결론에 영향 없다 → nsys 프로파일은 실익 낮아 생략 권고.")
)

# ------------------------------------------------------------------ 11 regime flip
s = add("하나의 곱셈이 두 레짐을 모두 설명한다",
        "캐시 히트의 가치 = 절약된 prefill 시간 × P(GPU가 병목)", tcolor=NAVY)
rows = [
    ("워크로드", "HW", "d", "R", "P(병목)", "2.26s 미스 벌금의 성격", "실측"),
    ("TraceLab", "2×4090", "0.196", "1.20", "중간", "대부분 bubble에 흡수", "default 승 +44%"),
    ("SWE-bench", "2×4090", "0.995", "≫1", "≈1", "순손실", "tr 승 +78~84%"),
    ("TraceLab", "Pro6000 TP2", "0.289", "≫1", "≈1", "순손실", "default 붕괴 (C=32)"),
]
tbl = s.shapes.add_table(len(rows), 7, Inches(0.45), Inches(1.9), Inches(12.4), Inches(2.4)).table
for c, wdt in zip(range(7), [1.5, 1.6, 0.9, 0.9, 1.1, 3.2, 3.2]):
    tbl.columns[c].width = Inches(wdt)
for i, row in enumerate(rows):
    for j, val in enumerate(row):
        cell = tbl.cell(i, j); cell.text = val
        pr = cell.text_frame.paragraphs[0]; pr.alignment = PP_ALIGN.CENTER
        for rn in pr.runs:
            rn.font.size = Pt(12); rn.font.bold = (i == 0)
            rn.font.color.rgb = NAVY if i == 0 else (RED if i >= 2 else RGBColor(0x33, 0x33, 0x33))
bullets(s, [
    ("R≥1이 되면 P(병목)이 0→1로 간다.  동일한 2.26초가 R<1에선 공짜, R≥1에선 순손실이 된다.", NAVY, True),
    ("⚠️  단 '재프리필이 decode 슬롯을 훔친다'는 코드상 부정확 — RUNNING이 먼저 스케줄되므로 decode는 안 밀린다.", RED, False),
    ("      실제 기전 = KV 블록 고갈로 waiting 큐 정체 + iteration이 무거워짐.  발표 문구 정정 필요.", GREY, False),
], top=4.6, size=14.5)
s.notes_slide.notes_text_frame.text = (
    "이게 '두 레짐을 하나의 인과 사슬로 설명한다'는 목표의 답이다.\n\n"
    "곱셈 하나면 된다: 히트의 가치 = 절약 시간 × P(병목). 절약 시간(2.26s/turn)은 워크로드가 같으면 동일하다. "
    "바뀌는 건 P(병목)뿐이고, 그건 R이 결정한다.\n"
    "  R<1 → P≈0 → 히트는 거의 가치 없음 → 캐시를 버리고 GPU를 채우는 default 승\n"
    "  R≥1 → P≈1 → 히트가 온전한 가치 → 캐시를 지키는 tr 승\n\n"
    "TP2 예비 실측(logs/2026-07-16 §P1-1)이 이 예측과 정합: fit≈25를 넘는 C=32에서 default가 붕괴한다 "
    "(hit 0.81→0.29, thru 0.133→0.039로 3.4배↓, p95 240→1490s).\n\n"
    "정정해야 할 우리 서술: '재프리필 FLOP이 다른 프로그램의 decode 슬롯을 직접 훔친다'는 코드상 틀렸다. "
    "RUNNING이 먼저 스케줄되고(:432) budget 2048 ≫ max_num_seqs 256이므로 decode 요청은 프리필에 의해 "
    "admission에서 밀려나지 않는다. 실제 기전은 (i) 같은 iteration에 2048토큰 청크가 얹혀 iteration이 길어짐, "
    "(ii) KV 블록 고갈로 waiting 큐 정체. → '슬롯을 훔친다' 대신 'KV를 고갈시켜 큐를 정체시킨다'로 말할 것.\n\n"
    "[추정] '양의 되먹임'(재프리필→KV 압박→추가 미스의 자기강화 루프)은 미검증. 직접 보여주는 시계열 증거가 없다.")

# ------------------------------------------------------------------ 12 open gap
s = add("정직하게 — 여기서 고리가 열려 있었다", "U는 잘 예측한다. 그러나 U → throughput의 마지막 한 단계가 안 맞았다  (→ 슬라이드 17에서 해소)", tcolor=RED)
bullets(s, [
    ("모델:   thr ∝ U / W,     W = prompt·(1−hit)/5896 + out_tok/rate_decode", NAVY, True),
    ("", GREY, False),
    ("실측 대입 (C=16):    U_def/U_tr = 2.70    /    W_def/W_tr = 2.61    →   예측 thr 비 = 1.03", GREY, False),
    ("실측 thr 비 = 0.098 / 0.068 = 1.44                                          ❌  안 맞는다", RED, True),
    ("", GREY, False),
    ("역산:  실측 1.44를 맞추려면 hit_default ≈ 0.38 이어야 한다  (보고값 0.037 아님)", NAVY, True),
    ("→  불일치의 방향이 슬라이드 8의 hit 오염과 일치한다.  [추정 — 편향 방향은 코드만으로 미확정]", GREY, False),
    ("", GREY, False),
    ("→ 이 고리는 GPU 실측으로 닫혔다.  슬라이드 17 참조 (오차 28.2% → 1.4%).", GREEN, True),
], top=1.7, size=14.5, gap=0.42)
s.notes_slide.notes_text_frame.text = (
    "이 슬라이드는 '설명 못 하면 정직히 보고하라'는 지시에 대한 답이다.\n\n"
    "Phase 3은 throughput 식까지 내려가는 것이 목표였다. U는 잘 예측된다(슬라이드 6). "
    "그런데 U에서 throughput으로 가는 마지막 단계에서 모델이 깨진다.\n\n"
    "계산 상세 (C=16):\n"
    "  W_tr  = 18684×(1−0.797)/5896 + 0.86 = 0.64 + 0.86 = 1.50 s\n"
    "  W_def = 18684×(1−0.037)/5896 + 0.86 = 3.05 + 0.86 = 3.91 s\n"
    "  W_def/W_tr = 2.61,  U_def/U_tr = 0.855/0.317 = 2.70  →  예측 thr 비 1.03\n"
    "  실측 1.44. 40% 어긋난다.\n\n"
    "역산하면 W_def/W_tr = 1.875 → W_def = 2.81s → prefill 1.95s → hit_default ≈ 0.38.\n\n"
    "해석 [추정]: 보고된 hit 0.037이 참값보다 낮게 편향됐다면 모델이 맞아 들어간다. 재검사 오염은 요청당 "
    "가중치를 N배(default 30배) 주므로 대기 중 샘플이 집계를 지배한다. 다만 편향의 '방향'을 코드만으로 "
    "확정하지는 못했다 — 대기 중 hits가 어떻게 변하는지는 evict 타이밍에 의존한다. 그래서 이건 추정이지 결론이 아니다.\n\n"
    "현 시점 정직한 결론: R 모델은 U를 잘 예측하지만, U→throughput의 마지막 한 단계는 hit 지표가 오염돼 있어 "
    "닫히지 않는다. 억지로 맞추지 않고 열어둔다.\n\n"
    "빠진 것 지목: (i) 오염 없는 재프리필량, (ii) 부하 하 prefill_s/decode_s, (iii) iteration당 실제 토큰 구성.\n\n"
    "부수 규명: 스윕 런의 prefill_s/decode_s가 0인 이유를 찾았다 — profile/state.py:42,145의 first_token_time은 "
    "on_first_token 콜백으로만 설정되고, 이 콜백은 app.py:114에서 스트리밍 경로에만 연결된다. "
    "스윕 드라이버가 --stream 없이 돌아 TTFT가 측정 안 됐다. 재측정 시 --stream 필수.")

# ------------------------------------------------------------------ 13 lit review
s = add('Phase 5 — "아무도 duty를 안 본다"는 거짓이다', "28p·34p 양쪽 원문 대조 완료. 이 문장은 그대로 쓰면 리뷰어에게 즉시 잡힌다.", tcolor=RED)
rows = [
    ("논문", "duty/tool-idle을 보는가", "형태", "인용 위치"),
    ("InferCept (ICML'24)", "본다 — WastePreserve = T_INT × C × M", "예측+최적화", "§3.2 Eq(2), §4.4"),
    ("Continuum", "본다 — tool 시간 경험적 CDF → TTL pinning", "예측+최적화", "§4.1, §4.2 Eq(1)(2)"),
    ("ThunderAgent (우리 논문!)", "본다 — Σ c_q × f(t_q),  t_q = tool 실행시간", "최적화", "p.7 Eq(7), p.24 E.2"),
    ("Autellix", "인지하나 명시적 배제 — \"unrelated to LLM serving\"", "무시(명시적)", "§2.2"),
    ("Parrot / Preble / vAttention / SGLang", "안 본다", "무시 / 무관", "§6 / Abstract"),
]
tbl = s.shapes.add_table(len(rows), 4, Inches(0.45), Inches(1.75), Inches(12.4), Inches(2.9)).table
for c, wdt in zip(range(4), [3.1, 5.2, 1.9, 2.2]):
    tbl.columns[c].width = Inches(wdt)
for i, row in enumerate(rows):
    for j, val in enumerate(row):
        cell = tbl.cell(i, j); cell.text = val
        pr = cell.text_frame.paragraphs[0]
        for rn in pr.runs:
            rn.font.size = Pt(11.5); rn.font.bold = (i == 0)
            rn.font.color.rgb = NAVY if i == 0 else (RED if i <= 3 else RGBColor(0x33, 0x33, 0x33))
bullets(s, [
    ("살아남는 기여:  선행연구는 tool 시간을 per-call 절대 지속시간(초)으로 → KV 보존이라는 국소 메커니즘 결정에 쓴다.", NAVY, True),
    ("우리는 duty를 무차원 워크로드 비율로 정의하고, GPU 활용률의 예측 변수로 승격시킨다.  (부재 검증: duty 비율 정의는 7개 시스템 전부 없음)", GREEN, True),
], top=4.95, size=13.5)
s.notes_slide.notes_text_frame.text = (
    "전량 원문 대조했다. 결론: 우리가 쓰려던 문장은 거짓이다.\n\n"
    "결정적 반례 3개 (verbatim 인용):\n"
    "① InferCept §3.2 Eq(2): \"The preserve waste for request i when interception j occurs is the duration of that "
    "interception, T_INT, multiplied by the amount of GPU memory held by the request's context.\" "
    "게다가 §4.4 제목이 통째로 'Interception Duration Estimation'이고, T̂=t_now−t_call 추정으로 oracle 대비 93% 성능.\n"
    "② Continuum §4.1: \"we estimate P(τ,f) using the empirical CDF derived from historical tool-call records.\"\n"
    "③ ThunderAgent 자신 p.7 Eq(7): C_total < Σ c_p + Σ c_q × f(t_q), \"t_q is the tool execution time.\" "
    "더 나아가 Appendix E.2(p.24)가 tool time 0 / infinite 극한을 이미 논한다 = 사실상 d→1, d→0 레짐.\n\n"
    "리뷰어가 InferCept Eq(2) 하나만 들어도 무너진다.\n\n"
    "★ 우리 문서의 사실 오류 1건 발견: MECHANISM_REFERENCE §1-1 표가 Cost_unused를 'tool 실행 중 놀고 있는 KV 점유'로 "
    "적었는데, 논문 p.6은 \"Cost_unused reflects memory imbalance across data parallel (DP) replicas\"이고 "
    "tool 시간에 과금하는 항은 Cost_caching이다. 수정 필요 — 리뷰어가 즉시 잡을 종류.\n\n"
    "fallback('duty를 스케줄링에 쓰는 연구는 있으나 활용률의 예측 변수로 쓰지 않는다')은 방어 가능하나 두 곳을 조여야 한다:\n"
    "  (1) '스케줄링에 쓴다'가 너무 약하다. 선행은 per-call 절대 지속시간(초), 우리는 워크로드 수준 무차원 비율. 이 축을 명시.\n"
    "  (2) ThunderAgent Appendix D(p.23)는 실제로 레짐 언어를 쓴다('adapts to these regimes'). 다만 그 레짐은 "
    "      tool 시간의 variability 축이지 duty 비율 축이 아니다. 선제적으로 구분하지 않으면 잡힌다.\n\n"
    "부재 검증(실측): Continuum 전문에 'idle'/'duty cycle'/'GPU utilization'/'regime' 각 0회. "
    "ThunderAgent에 'duty' 0회, 'GPU utilization' 1회(p.11, 정성적). 어떤 논문도 U≈min(R,1) 류 활용률 예측 모델 없음.\n\n"
    "✅ 34p 갱신본 검증 완료(2026-07-17 수령). 전수 스캔: duty 0회, fraction/occupancy/dimensionless/predictor 각 0회, "
    "utilization 6회(6/6 정성적), regime 2회(2/2 정성적). → 우리 기여 주장은 34p에서도 유지된다.\n"
    "오히려 유리한 인용 발견(p.11): 'determining the optimal parallel workflow number to maximize utilization ... "
    "is infeasible due to the stochastic nature of agent environments and tool execution durations' "
    "— 저자들이 활용률 모델링을 '불가능'으로 규정하고 우회했다. 우리가 R로 그걸 예측한다는 게 정확히 빈틈이다.\n"
    "가장 근접한 반례: 신설 §G.2(p.32, Fig 15) — tool 지연 예측가능성 축의 어블레이션. duty 비율 축이 아니라 무해하나, "
    "'아무도 duty 레짐을 생각조차 안 했다'류 강한 표현은 철회할 것.\n\n"
    "⚠️ Continuum 인용 주의: ThunderAgent p.22는 Continuum을 'static, threshold-based rule'이라 하지만 "
    "원문 §4.1 Eq(1)은 cost-benefit 최적화다. 우리는 원문을 근거로 삼아야 한다.")

# ------------------------------------------------------------------ 14 TP2 confound
s = add("★ 부수 발견 — TP2 비교에 교란변수가 숨어 있다",
        "vLLM은 device memory 70GiB를 경계로 배치 기본값을 바꾼다 (arg_utils.py:2404-2423)", tcolor=RED)
rows = [
    ("HW", "device mem", "max_num_batched_tokens", "max_num_seqs"),
    ("4090  (expC / D)", "24 GB  < 70GiB", "2048", "256"),
    ("Pro6000  (TP2)", "96 GB  ≥ 70GiB", "8192   (×4)", "1024   (×4)"),
]
tbl = s.shapes.add_table(len(rows), 4, Inches(1.5), Inches(2.0), Inches(10.2), Inches(1.6)).table
for c, wdt in zip(range(4), [2.8, 2.6, 2.6, 2.2]):
    tbl.columns[c].width = Inches(wdt)
for i, row in enumerate(rows):
    for j, val in enumerate(row):
        cell = tbl.cell(i, j); cell.text = val
        pr = cell.text_frame.paragraphs[0]; pr.alignment = PP_ALIGN.CENTER
        for rn in pr.runs:
            rn.font.size = Pt(14); rn.font.bold = (i == 0 or i == 2)
            rn.font.color.rgb = NAVY if i == 0 else (RED if i == 2 else RGBColor(0x33, 0x33, 0x33))
bullets(s, [
    ("TP2 실험은 'KV 풀 ×10.41' 하나만 바뀐 게 아니다. 배치 토큰 예산도 ×4로 함께 바뀐다.", RED, True),
    ("k_fit-flip이 관측되면 그 원인이 (i) C_total 확대인지 (ii) batched_tokens 확대인지 현재 설계로는 분리 불가.", NAVY, False),
    ("→ 권고: TP2 스윕에  --max-num-batched-tokens 2048  --max-num-seqs 256  대조군 1점 추가하면 분리된다.", GREEN, True),
], top=4.1, size=15)
s.notes_slide.notes_text_frame.text = (
    "이건 찾으려던 게 아닌데 나왔다. 그리고 진행 중인 TP2 실험에 직접 영향이 있다.\n\n"
    "arg_utils.py:2404: if device_memory >= 70*GiB_bytes and 'a100' not in device_name → 큰 기본값.\n"
    "  4090 24GB → else 분기 → OPENAI_API_SERVER: batched_tokens 2048, seqs 256\n"
    "  Pro6000 96GB → if 분기 → OPENAI_API_SERVER: batched_tokens 8192, seqs 1024\n"
    "(TP2라도 device_memory는 카드당 96GB로 판정된다.)\n\n"
    "왜 문제인가: plans/2026-07-15의 '한 번에 한 변수만' 원칙이 의도치 않게 깨져 있다. "
    "TraceLab k_fit-flip(4090 R<1 → Pro6000 R≥1)이 관측될 때, 그게 KV 풀 확대 때문인지 "
    "배치 예산 확대 때문인지 분리할 수 없다.\n\n"
    "특히 이번 분석에서 max_num_batched_tokens=2048이 '프리필 1건이 예산을 10 iteration 독점' → "
    "'배치가 1.1~1.5에 묶임'의 직접 원인임이 드러났으므로, 이 값이 4배가 되면 배치 거동 자체가 달라질 수 있다. "
    "즉 교란이 사소하지 않다.\n\n"
    "권고: 대조군 1점이면 분리된다 — TP2에서 --max-num-batched-tokens 2048 --max-num-seqs 256으로 고정한 런 하나. "
    "그 점이 4090과 같은 배치 거동을 보이면서도 flip이 일어나면, 원인은 C_total이다.\n\n"
    "단 이건 nutella1 소관이라 이 보고서에서는 제안만 한다. 현재 tp2sweep이 돌고 있으므로 "
    "지금 손대지 말고 스윕 완료 후 추가 1점으로 붙이는 게 안전하다.\n\n"
    "✅ 2048/8192는 2026-07-17에 실측 확정(실제 4090에서 get_batch_defaults 실행). 교란은 실재한다.")

# ------------------------------------------------------------------ 15 GPU ask
s = add("GPU 실험 — 승인받아 실행 완료", "열린 고리(슬라이드 12)를 닫기 위한 최소 실험. 결과는 슬라이드 16~20.", tcolor=GREEN)
rows = [
    ("#", "목적", "방법", "비용"),
    ("1 ★", "오염 없는 재프리필 실측 → 열린 고리를 닫는다",
     "vLLM 1대 기동, /metrics에서 prompt_tokens_by_source{local_compute}\n+ prompt_tokens_cached 수집. C=16 tr/default 각 1런(NPROG=32)", "GPU 1장\n~40분"),
    ("2", "부하 하 prefill/decode 분해 (H3 완결)", "위 런에 --stream 추가 → prefill_s/decode_s 복구", "+0"),
    ("3", "런타임 config 확정 (2048/256)", "기동 로그에서 max_num_batched_tokens 확인", "+0"),
    ("4·5", "decode batch 커브 / SM occupancy", "실익 낮음 — 배치가 1.1~1.5로 확정, 삼각측량으로 방어됨", "생략 권고"),
]
tbl = s.shapes.add_table(len(rows), 4, Inches(0.45), Inches(1.75), Inches(12.4), Inches(3.4)).table
for c, wdt in zip(range(4), [0.8, 3.6, 6.3, 1.7]):
    tbl.columns[c].width = Inches(wdt)
for i, row in enumerate(rows):
    for j, val in enumerate(row):
        cell = tbl.cell(i, j); cell.text = val
        pr = cell.text_frame.paragraphs[0]
        for rn in pr.runs:
            rn.font.size = Pt(11); rn.font.bold = (i == 0 or i == 1)
            rn.font.color.rgb = NAVY if i == 0 else (GREEN if i == 1 else (GREY if i == 4 else RGBColor(0x33, 0x33, 0x33)))
bullets(s, [
    ("mango1 4×4090 전부 유휴 확인 후 승인받아 실행.  ①②③ 완료 → 슬라이드 16~20.  ④⑤는 실익이 낮아 생략(권고대로).",
     GREY, False),
], top=5.3, size=13)
s.notes_slide.notes_text_frame.text = (
    "게이트를 지켜 승인을 요청한다.\n\n"
    "GPU 상태 확인 결과(작업 시작 시): mango1 4×RTX4090 전부 0% / 1MiB / 프로세스 없음. "
    "tmux 세션은 'analysis'(7/6 생성, 유휴)와 'claude'뿐. tp2sweep/tp2serve/tp2proxy는 nutella1에서 도는 것이라 "
    "여기 GPU를 써도 TP2 스윕에 영향이 없다. 그럼에도 지시대로 승인 전에는 잡지 않았다.\n\n"
    "제안 1이 핵심이다. 이유: 슬라이드 8에서 hit 지표가 오염됐음이 확정됐고, 슬라이드 12에서 그 오염 때문에 "
    "U→throughput 모델이 안 닫힌다. vllm:prompt_tokens_by_source{source='local_compute'}는 실제 prefill 출력에서만 "
    "누적되므로 재검사 오염이 없다 = 참 재프리필량. 이거 하나면 (a) 참 hit, (b) §3-3 모델 성립 여부, "
    "(c) 오염의 편향 방향이 전부 결정된다.\n\n"
    "1·2·3은 같은 런에서 한 번에 얻는다. C=16 tr/default 각 1런, NPROG=32로 축소하면 약 40분.\n\n"
    "4·5는 생략 권고: decode batch 커브는 실제 배치가 1.1~1.5로 고정임이 확정돼 평탄 구간 여부가 결과를 못 바꾼다. "
    "SM occupancy는 3종 삼각측량(r=0.999)으로 이미 방어됐고, 배치가 같으니 tr/default 차이가 없을 것 [추정].\n\n"
    "별도(nutella1 소관): TP2에 batched_tokens 2048 대조군 1점(슬라이드 14).\n\n"
    "그리고 GPU와 무관하게 지금 할 것: 34p 논문 갱신본 확인(nutella1) — Phase 5 결론의 최대 구멍.")

# ------------------------------------------------------------------ 16 GPU result: true hit
add("★ GPU 실측 — 오염은 비대칭이었다",
    "tr의 hit 지표는 애초에 정확했고(1.0x), default만 4.8배 과소평가됐다",
    "vllm_true_vs_reported_hit.png", img_top=1.6, img_h=5.1, tcolor=GREEN,
    notes=(
        "GPU 승인 후 실행. 조건: expC와 동일(GPU2/3, KV 43,888 확인), C=16, NPROG=32, --stream, "
        "router assertion 통과, 두 런 모두 rc=0 정상 완주.\n\n"
        "offered load 동일성 검증: prompt_tokens_total = 2,439,542(default) / 2,439,544(tr) → 결정적 replay 확인.\n"
        "불변식 compute + cached == total : 양쪽 모두 True → §1-2의 코드 독해가 실측으로 확증.\n"
        "preemptions = 0 (양쪽) → §1-3의 코드 분석과 정합.\n\n"
        "실측:\n"
        "  tr      : 참 hit 0.6983 / 보고 hit 0.6983 / 배수 1.00x / 팽창 1.0x / 참 재프리필 735,928 tok\n"
        "  default : 참 hit 0.1844 / 보고 hit 0.0383 / 배수 4.81x / 팽창 26.3x / 참 재프리필 1,989,606 tok\n\n"
        "★ 왜 비대칭인가 — 이게 핵심이다. tr은 프록시에서 미리 막아 요청이 vLLM waiting 큐에 아예 안 쌓인다 "
        "→ 재검사 0회 → 팽창 1.0x → 참값 == 보고값(소수 4자리까지). default는 vLLM 큐에 쌓여 26.3회씩 재검사된다. "
        "즉 '지표가 오염되는 것'과 '내부 큐에서 줄 서는 것'이 같은 현상이다. 이것이 네 번째 독립 증거다 "
        "(앞선 셋: REASONING-nrr 갭, queries 팽창, TTFT 인플레).\n\n"
        "검증: 보고 hit 0.0383이 expC C=16의 0.037과 일치 → 이 런이 expC를 재현함을 확인.\n\n"
        "→ 'default는 프롬프트의 96%를 재프리필한다'는 틀렸다. 실제 81.6%다. 여전히 나쁘지만 수치가 다르다. "
        "tr에 대해 우리가 써온 hit 수치는 수정할 필요가 없다.")
)

# ------------------------------------------------------------------ 17 loop closed
s = add("★★ 그래서 식이 닫혔다", "같은 모델에 hit만 참값으로 바꿔 넣었다  →  예측 오차 28.2% → 1.4%", tcolor=GREEN)
rows = [
    ("쓰는 hit", "W_tr", "W_def", "W_def / W_tr", "예측 thr 비", "실측 1.441 대비"),
    ("오염된 보고 hit  (0.797 / 0.037)", "1.499s", "3.908s", "2.606", "1.035", "오차 28.2%  ✗"),
    ("참 hit  (0.6983 / 0.1844)", "1.812s", "3.441s", "1.899", "1.421", "오차 1.4%  ✓"),
]
tbl = s.shapes.add_table(len(rows), 6, Inches(0.5), Inches(2.15), Inches(12.3), Inches(1.9)).table
for c, wdt in zip(range(6), [3.5, 1.5, 1.5, 2.0, 1.9, 1.9]):
    tbl.columns[c].width = Inches(wdt)
for i, row in enumerate(rows):
    for j, val in enumerate(row):
        cell = tbl.cell(i, j); cell.text = val
        pr = cell.text_frame.paragraphs[0]; pr.alignment = PP_ALIGN.CENTER
        for rn in pr.runs:
            rn.font.size = Pt(13); rn.font.bold = (i == 0 or i == 2)
            rn.font.color.rgb = NAVY if i == 0 else (GREEN if i == 2 else RED)
bullets(s, [
    ("모델:   thr  ∝  U / W ,      W = prompt·(1−hit) / 5,896 tok/s  +  decode 0.856s", NAVY, True),
    ("U = R 모델이 예측 (mean nrr).   W = 참 재프리필 비용.   이 두 항이면 tr/default 승패가 예측된다.", GREEN, True),
    ("⚠️  한계: U는 expC(NPROG=64), 참 hit는 이번 런(NPROG=32) — 런 혼합. 동일 런에서 U와 참 hit 동시 측정이 남았다.", GREY, False),
], top=4.5, size=14.5)
s.notes_slide.notes_text_frame.text = (
    "Phase 3에서 '설명 못 하면 정직히 보고하라'는 지시에 따라 '안 닫힌다'고 열어뒀던 고리다. 그게 닫혔다.\n\n"
    "계산 (C=16):\n"
    "  W_tr  = 18684 x (1-0.6983) / 5896 + 0.856 = 0.956 + 0.856 = 1.812 s\n"
    "  W_def = 18684 x (1-0.1844) / 5896 + 0.856 = 2.585 + 0.856 = 3.441 s\n"
    "  U_def/U_tr = 0.855/0.317 = 2.697\n"
    "  예측 thr 비 = 2.697 / 1.899 = 1.421   vs   실측 0.098/0.068 = 1.441   → 오차 1.4%\n\n"
    "오염된 hit로 하면 1.035 (오차 28.2%). 즉 모델이 틀렸던 게 아니라 입력이 오염됐던 것이다.\n\n"
    "이전에 내가 역산했던 hit_default ~ 0.38은 방향은 맞았으나 값이 틀렸다(참값 0.1844). 역산이 W_tr에 "
    "오염된 tr hit(0.797)을 썼기 때문. 참 tr hit(0.6983)을 쓰면 필요한 hit_default = 0.197 → 실측 0.1844와 7% 이내 일치.\n\n"
    "한계(정직): U 값은 expC(NPROG=64) 런에서, 참 hit는 이번(NPROG=32) 런에서 왔다. 런 혼합이다. "
    "보고 hit이 0.0383 ~ 0.037로 일치해 비교 가능성은 확보했지만, 동일 런에서 U와 참 hit를 함께 재는 확인이 남았다. "
    "이건 다음 실험에서 쉽게 채울 수 있다.")

# ------------------------------------------------------------------ 18 latency breakdown
add("H1 정정 — default의 숨은 벌금이 드러났다",
    "--stream으로 prefill_s 복구.  default TTFT 10.79s 중 ~9.5s가 vLLM 큐 대기 (c=1 warm은 0.46s)",
    "vllm_latency_breakdown_loaded.png", img_top=1.6, img_h=5.0, tcolor=RED,
    notes=(
        "제안 2의 결과. §6-1의 진단대로 --stream을 넣자 prefill_s가 126/126 전부 기록됐다(기존 스윕은 전부 0). "
        "원인: profile/state.py:42,145의 first_token_time은 on_first_token 콜백으로만 설정되고, 그 콜백은 "
        "app.py:114에서 스트리밍 경로에만 연결된다(vllm_request_processor.py:158,174-177).\n\n"
        "부하 하 step 분해 (mean s, n=126):\n"
        "  tr      : pause 20.83 | prefill 1.29 | decode 1.08 | tool 7.55  ->  합 30.76s\n"
        "  default : pause  0.00 | prefill 10.79 | decode 2.12 | tool 7.65  ->  합 20.56s\n\n"
        "★ H1 수치 정정: 처음엔 'default 2.3초 vs tr 18.5초 = 8.2배'라고 했다. 그건 재프리필 '계산분'만 센 것이다. "
        "부하 하 TTFT를 실제로 재니 default는 10.79초인데 tr은 1.29초 → 차이 ~9.5초가 숨은 vLLM 큐 대기다. "
        "정정: default 벌금 ~9.5초/step, tr 벌금 ~20.8초/step → 2.2배. "
        "H1의 방향(default 벌금 < tr 벌금 → default 승)은 유지되나 격차는 훨씬 작다. 발표 시 2.2배로 말할 것.\n\n"
        "그리고 tr의 step 합(30.76s) > default(20.56s) → tr throughput 열세와 정합하게 맞아떨어진다.\n\n"
        "이것이 '어디서 줄 서는가'(슬라이드 7)의 세 번째 독립 증거다.")
)

# ------------------------------------------------------------------ 19 pause heavy tail
add("정정 — 'tr은 매 step 18.5초 pause한다'는 틀렸다",
    "중앙값은 0.00초다.  평균 18.5초는 2.4%의 파국적 stall이 만든 값이다.",
    "vllm_pause_heavy_tail.png", img_top=1.6, img_h=5.0, tcolor=RED,
    notes=(
        "expC 원본 데이터(n=4,301) 재분석. 이 발견은 마이크로벤치와 무관하게 유효하다.\n\n"
        "expC tr pause_s 분포:\n"
        "  p50 = 0.00s | p75 = 0.01s | p90 = 11.14s | p95 = 65.29s | p99 = 521.85s | max = 841.13s | mean = 18.47s\n"
        "  pause>1s: 18.2% | >30s: 7.0% | >300s: 2.4% | >600s: 0.8%\n\n"
        "즉 tr 스텝의 82%는 pause가 사실상 0이다. 평균 18.47초는 소수(2.4%)의 5~14분짜리 대기가 만든 값이다.\n\n"
        "이건 tr의 의도된 설계의 직접 관측이다 — 캐시를 지키려 특정 프로그램을 오래 재운다. "
        "그리고 이것이 tr의 p95 latency 열세의 진짜 정체다.\n\n"
        "→ 발표/논문에서 '평균 pause 18.5초' 대신 분위수로 서술할 것: "
        "'tr은 대부분의 step에서 전혀 pause하지 않지만, 2.4%의 step에서 5분 이상 굶긴다.'\n\n"
        "참고: default는 pause mean 0.00s, max 0.01s — 프록시 큐를 아예 안 쓴다(대신 vLLM 큐를 쓴다).")
)

# ------------------------------------------------------------------ 20 retraction
s = add("정직 — 철회한 발견 하나", "실험 중 'tr 스케줄러 데드락'을 발견했다고 판단했으나, 내 하네스 버그였다.", tcolor=RED)
bullets(s, [
    ("관측:  tr이 C=16에서 249~344초 동안 완전 정지 (reasoning=0, nrr=0, GPU 0%, paused=18).  2회 재현.", GREY, False),
    ("추론했던 것:  'tr의 용량 회계가 ACTING 토큰을 과다 계상해 자기 데드락'  →  그럴듯했다.", GREY, False),
    ("", GREY, False),
    ("실제 원인:  내가 드라이버에 --router-url 을 안 넘겼다.", RED, True),
    ("      기본값이 localhost:9000 인데 내 프록시는 9011.  driver:286의 POST /programs/release 가 전부 실패.", GREY, False),
    ("      → 프로그램이 영영 해제 안 됨 → active_program_tokens 누적(40,671 / 43,888) → resume 영구 불가.", GREY, False),
    ("      → default가 멀쩡했던 건 용량 검사를 안 하기 때문.  'tr만 데드락'이라는 착시가 여기서 나왔다.", GREY, False),
    ("", GREY, False),
    ("무엇이 잡았나:  expC 스윕 스크립트와 CLI 인자를 전수 대조 (run_trace_sweep_expC:65 에 --router-url 있음).", GREEN, True),
    ("expC 데이터는 깨끗하다.  §1~§4의 결론은 전부 그대로 유효하다.", GREEN, True),
], top=1.6, size=13.5, gap=0.4)
s.notes_slide.notes_text_frame.text = (
    "이 슬라이드를 넣는 이유: '가설이 반증되면 반증됐다고 그대로 써라'는 원칙 때문이고, "
    "또 이런 종류의 실수가 어떻게 논문에 들어가는지 보여주기 때문이다.\n\n"
    "위험했던 점: 데드락이 2회 재현됐고(--stream 유/무), 서명이 거의 동일했고(paused 18/acting 5/nrr 0), "
    "프록시 로그에 active=40,671 vs C_total=43,888 이라는 그럴듯한 '증거'까지 있었다. "
    "논문에 'tr은 고부하에서 데드락한다'고 쓸 뻔했다. 전부 내 설정 오류였다.\n\n"
    "무효 데이터는 scratch/vprof/INVALID_missing_router_url/ 로 격리했고, "
    "figures/vllm_deadlock_timeline.png 는 폐기 대상이다(발표에 쓰지 말 것).\n\n"
    "잡아낸 방법: expC와 '동일 조건'이라 믿었는데 왜 결과가 다른지를 추측으로 메우지 않고 "
    "expC 스윕 스크립트의 CLI 인자를 한 줄씩 대조했다. --router-url 하나가 달랐다.\n\n"
    "교훈(다음 하네스에 적용): 기존 스윕과 '같은 조건'이라고 말하려면 CLI 인자를 전수 대조할 것. "
    "그리고 '새 발견'이 기존 데이터와 모순되면 새 발견을 먼저 의심할 것 — 실제로 expC에는 "
    "시스템 정지가 최대 26~47초뿐이었고 60초 넘는 구간이 0개였다. 그 모순이 단서였다.\n\n"
    "살아남는 것: pause heavy tail(슬라이드 19)은 expC 원본 데이터 기반이라 이 버그와 무관하게 유효하다.")

# ------------------------------------------------------------------ 15b paper comparison inverted
s = add("🚨 최우선 — PAPER_COMPARISON §0-1이 뒤집혔다", "우리가 28p 구본으로 교수님을 '정정'했는데, 교수님이 옳았다.", tcolor=RED)
rows = [
    ("우리 문서가 \"없다\"고 한 것", "34p 실제", "판정"),
    ("§A.5 (working set/heterogeneous)", "§A.5 'Portability across Hardware Generations' (p.24)\n본문: \"the working set fits comfortably in HBM and thrashing is rare\"", "교수님 옳음"),
    ("Table 3 = H100 vs A100", "Table 3 'Compute-to-bandwidth ratio' (p.24)\nH100 295.2 / A100 153.0 GFLOPS/GB", "교수님 옳음"),
    ("Figure 10 = compute-to-bandwidth", "Figure 10 'ThunderAgent on A100 GPUs' (p.25)", "교수님 옳음"),
    ("\"A100\"·\"compute-to-bandwidth\" 문구 없음", "둘 다 존재 (28p엔 각 0회 — 그래서 우리가 오판)", "교수님 옳음"),
    ("느린 GPU 스래싱 비교 실험 없음", "8xA100 실험 존재: 저부하(24) tr≈vLLM,\n고부하(48·72) 1.71–2.08x (mini-SWEAgent)", "교수님 옳음"),
]
tbl = s.shapes.add_table(len(rows), 3, Inches(0.45), Inches(1.6), Inches(12.4), Inches(3.9)).table
for c, wdt in zip(range(3), [3.5, 6.9, 2.0]):
    tbl.columns[c].width = Inches(wdt)
for i, row in enumerate(rows):
    for j, val in enumerate(row):
        cell = tbl.cell(i, j); cell.text = val
        pr = cell.text_frame.paragraphs[0]
        for rn in pr.runs:
            rn.font.size = Pt(10); rn.font.bold = (i == 0 or j == 2)
            rn.font.color.rgb = NAVY if i == 0 else (RED if j == 2 else RGBColor(0x33, 0x33, 0x33))
bullets(s, [
    ("hetero gap 영향:  \"논문은 GPU 세대를 안 바꿔봤다\"는 더 이상 못 쓴다.  compute-to-bandwidth도 이제 논문 안에 있다.", RED, True),
    ("살아남는 것:  §A.5도 8xA100 단독 / 8xH100 단독 — 한 클러스터 안의 이종 혼합 실험은 여전히 없다.  gap을 여기로 좁힐 것.", GREEN, True),
], top=5.7, size=12.5)
s.notes_slide.notes_text_frame.text = (
    "이게 오늘 발견 중 미팅에 가장 위험한 것이다. 34p본을 받고 대조하자마자 나왔다.\n\n"
    "logs/2026-07-02_PAPER_COMPARISON_yunuikang.md §0-1은 '지시서에서 언급한 인용 위치가 이 PDF와 불일치한다'며 "
    "교수님의 참조 5개를 전부 정정했다. 그런데 그 근거가 28p 구본이었고, 교수님은 34p 갱신본을 보고 계셨다. "
    "28p에는 'A100' 0회, 'compute-to-bandwidth' 0회, '§A.5' 0회 — 그래서 우리가 '없다'고 판단한 것이다. "
    "34p에는 전부 있다. 실측으로 직접 확인했다(pypdf 추출, 해당 페이지 재추출로 이중 확인).\n\n"
    "→ §0-1은 폐기해야 한다. 이미 PAPER_COMPARISON 문서 최상단에 정정 공지 배너를 달아뒀다.\n\n"
    "hetero gap에 미치는 영향(정직하게):\n"
    "  약화: '논문은 GPU 세대를 바꿔 비교한 실험이 없다' → 더 이상 못 씀(§A.5가 정확히 그것). "
    "'compute-to-bandwidth 비율' 논거도 이제 논문 Table 3에 있으니 우리 독창성이 아니다.\n"
    "  살아남음: §A.5도 8xA100 단독 / 8xH100 단독이다. 한 클러스터에 서로 다른 GPU를 섞은 실험은 여전히 없고, "
    "node-agnostic recompute 가정(§4.3.2)도 그대로다. → 우리 gap을 '다른 하드웨어'가 아니라 "
    "'한 클러스터 안의 이종 혼합'으로 좁혀서 서술해야 한다.\n\n"
    "부수: Appendix E와 F가 34p에서 서로 뒤바뀌었다(E=E2E latency, F=이론분석). 우리가 쓰던 'Appendix E.2'는 "
    "34p에서 死링크다 → 'Appendix F.2 / Hypothesis F.2, p.30'으로 교체. tool buckets는 Table 5 → Table 6 (p.27). "
    "Figure 9→12, 10→13. 참고문헌 번호 전부 +1 시프트. 전체 정정표는 보고서 §5-0b에 있다.")

# ------------------------------------------------------------------ 16 closing
s = add("한 문단으로", "", tcolor=NAVY)
tb = s.shapes.add_textbox(Inches(0.65), Inches(1.35), W - Inches(1.3), Inches(5.6))
tf = tb.text_frame; tf.word_wrap = True
paras = [
    ("vLLM V1은 prefill/decode 단계 구분 없이 매 iteration 2048 토큰을 RUNNING 요청부터 채우고, KV가 모자라면 "
     "preempt가 아니라 waiting 큐에서 승인을 거부한다.  18.7k 프롬프트는 이 예산을 약 10 iteration 독점하므로 "
     "실제 GPU 배치는 정책과 무관하게 1.1~1.5에 고정된다.", RGBColor(0x33, 0x33, 0x33), False),
    ("따라서 'GPU를 채운다'는 배치를 키우는 게 아니라 시간축의 구멍을 메우는 것이고, "
     "R = k_fit·d 는 동시에 GPU 일을 원하는 요청 수의 기댓값이다 (실측 mean nrr과 일치).", NAVY, True),
    ("R<1이면 bubble이 있어 캐시 미스의 한계비용 2.26초/turn이 놀던 시간에 흡수되어 거의 공짜인 반면, "
     "tr의 pause는 18.5초/step의 순손실이다 — 2.3초 벌금 vs 18.5초 벌금, 8.2배.  이것이 R<1에서 default가 이기는 인과다.",
     RED, True),
    ("R≥1이 되면 P(GPU가 병목)이 0→1로 가면서 같은 2.26초가 기회비용에서 순손실로 바뀌어 tr이 이긴다. "
     "곱셈 하나가 두 레짐을 모두 설명한다.", GREEN, True),
    ("모르는 것:  (i) hit rate는 default에서 30배 팽창한 표본이라 절대값 0.037은 신뢰 불가.  "
     "(ii) 그 결과 U→throughput의 마지막 한 단계가 닫히지 않는다 (예측 1.03 vs 실측 1.44).  "
     "(iii) '재프리필이 decode 슬롯을 훔친다'는 코드상 부정확.  (iv) 34p 논문 미확인이고, "
     "'duty를 아무도 안 본다'는 거짓이다 — 우리 기여는 duty를 메커니즘의 입력이 아니라 활용률의 예측 변수로 "
     "승격시킨 것으로 재정의되어야 한다.", GREY, False),
]
for i, (t, c, b) in enumerate(paras):
    p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
    r = p.add_run(); r.text = t
    r.font.size = Pt(14.5); r.font.color.rgb = c; r.font.bold = b
    p.space_after = Pt(15)
s.notes_slide.notes_text_frame.text = (
    "최종 정리. 모르는 것을 마지막 문단에 명시적으로 남겼다 — 이게 이번 작업에서 제일 중요한 부분이라고 본다.\n\n"
    "요약하면: R 모델은 살아남았고 물리적 근거를 얻었다. tr이 R<1에서 지고 R≥1에서 이긴다는 결론도 그대로다. "
    "바뀐 것은 (1) '왜'에 대한 설명이 정확해졌고(시간축 vs 배치, 어디서 줄 서는가), "
    "(2) hit rate 절대값의 신뢰도가 떨어졌고, (3) 'duty를 아무도 안 본다'는 주장을 버려야 한다는 것이다.\n\n"
    "다음 단계: GPU 1장 40분(제안 1~3) + 34p 논문 확인 + 우리 문서 2건 수정"
    "(MECHANISM_REFERENCE §1-1의 Cost_unused↔Cost_caching, DEEP_ANALYSIS §B-1의 granularity→재검사 중복 계수).")

prs.save(OUT)
print("saved:", OUT, "| slides:", len(prs.slides))
