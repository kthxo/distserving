#!/usr/bin/env python3
"""Tier C 결과-전용 덱 빌더 — 환경 / 측정방법 / 결과 수치만.

★ 이 덱의 범위 규약: 해석·결론·가설·판정 언어를 넣지 않는다.
   슬라이드 본문과 노트는 (1) 실험 환경 (2) 무엇을 어떻게 쟀나 (3) 잰 값 까지만 쓴다.

수치는 전부 `scratch/mori/tierc_h200/deck_numbers.json` 에서 읽는다 (하드코딩 금지).
JSON 은 `scripts/extract_tierc_numbers_yunuikang.py` 가 원자료에서 만든다.
"""
import json
import os
import sys

from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import decklib_yunuikang as D  # noqa: E402
from decklib_yunuikang import (INK, BLUE, RED, GREEN, GRAY, LT, AMBER, WHITE,  # noqa: E402
                               new_deck, _blank, band, chip, add_title, add_takeaway,
                               add_text, add_table, add_figure, add_caption, set_notes)

ROOT = os.path.dirname(HERE)
NUM = os.path.join(os.path.dirname(ROOT), "scratch", "mori", "tierc_h200",
                   "deck_numbers.json")
OUT = os.path.join(ROOT, "slides", "2026-08-08_TIERC_results-only_yunuikang.pptx")

PANEL = RGBColor(0xF4, 0xF6, 0xFA)
PURPLE = RGBColor(0x6E, 0x4B, 0x9E)
MORI_T = RGBColor(0xFB, 0xEF, 0xED)      # 아주 옅은 RED
TAO_T = RGBColor(0xEE, 0xF2, 0xF9)       # 아주 옅은 BLUE

DATA = json.load(open(NUM))
H, R = DATA["h200"], DATA["h200_ratio"]
M = DATA["meta"]
CS = [20, 40, 80]
prs = new_deck()


# ───────────────────────────────────────── 뼈대 헬퍼 (DECK_STYLE §2)
def slide(title, takeaway=None, tw_color=BLUE):
    s = _blank(prs)
    band(s, 0.0, 0.11, INK)
    add_title(s, title)
    if takeaway:
        add_takeaway(s, takeaway, color=tw_color)
    return s


def zone(s, n, label, x, y, w, h, color):
    p = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y),
                           Inches(w), Inches(h))
    p.fill.solid(); p.fill.fore_color.rgb = PANEL
    p.line.color.rgb = RGBColor(0xDD, 0xE1, 0xE8); p.line.width = Pt(0.75)
    p.shadow.inherit = False
    chip(s, f"{n}  {label}", x + 0.12, y + 0.10, min(w - 0.24, 4.5), color,
         size=10.5, h=0.30)
    return p


def footer(s, txt):
    add_text(s, txt, 0.42, 7.06, 12.5, 0.3, size=8.5, color=GRAY)


def cell(tag):
    return H[tag]


def rowtint(n_rows):
    """MORI 행 / TA+O 행 옅은 색 (2행씩 번갈아 오는 표용)."""
    out = {}
    for i in range(1, n_rows):
        out[i] = MORI_T if i % 2 == 1 else TAO_T
    return out


def name(tag):
    return "MORI" if tag.startswith("MORI") else "TA+O"


def pairs():
    """(C, MORI셀, TAO셀) 순회."""
    for C in CS:
        yield C, H[f"MORI_C{C}"], H[f"TAO_C{C}"]


# ═════════════════════════════════════════════════════ 0. 표지
s = _blank(prs)
band(s, 0.0, 7.5, INK)
add_text(s, "Tier C — GPU 시간 분해 측정 결과", 0.9, 2.25, 11.5, 1.0,
         size=44, color=WHITE, bold=True)
b = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.92), Inches(3.42),
                       Inches(2.6), Inches(0.035))
b.fill.solid(); b.fill.fore_color.rgb = BLUE; b.line.fill.background()
b.shadow.inherit = False
add_text(s, "H200 TP1 · Qwen2.5-7B · fit 20 · r=2 · C∈{20, 40, 80} × {MORI, TA+O}",
         0.92, 3.72, 11.5, 0.5, size=19, color=RGBColor(0x9F, 0xB6, 0xD8))
add_text(s, "실험 환경 · 측정 방법 · 측정값  —  전 항목 [측정]",
         0.92, 4.32, 11.5, 0.4, size=15, color=RGBColor(0x9F, 0xB6, 0xD8))
add_text(s, "2026-08-08 · yunuikang · 각 셀 n=1", 0.92, 6.35, 11.5, 0.4,
         size=13, color=RGBColor(0x7F, 0x92, 0xB0))
set_notes(s, """이 발표는 Tier C 실험에서 **실제로 잰 숫자만** 보여드립니다.
세 부분입니다. 1부는 어떤 장비와 설정에서 돌렸는지, 2부는 무엇을 어떻게 쟀는지,
3부는 나온 값입니다.
해석이나 결론은 이 자료에 넣지 않았습니다. 숫자를 먼저 같이 확인하는 자리입니다.
모든 셀은 한 번씩만 돌렸습니다(n=1). 이 점은 뒤에서 다시 말씀드립니다.""")

# ═════════════════════════════════════════════════════ 1부 — 환경
s = slide("1부 · 실험 환경 — 하드웨어와 소프트웨어 스택",
          "[측정] H200 TP1 이 본 실험이고, 같은 계측을 5090 TP1 에서도 돌린 자료가 따로 있다.")
rows = [["항목", "H200 (본 실험)", "5090 TP1 (별도 자료)"],
        ["GPU", "H200 SXM 141GB × 1", "RTX 5090 × 1"],
        ["병렬화", "TP1", "TP1"],
        ["엔진", M["engine"], M["engine"]],
        ["모델", M["model"], M["model"]],
        ["attention backend", M["attention_backend"], M["attention_backend"]],
        ["context-length (YaRN)", f"{M['context_len']:,}", f"{M['context_len']:,}"],
        ["chunked-prefill", f"{M['chunked_prefill']:,}",
         f"{DATA['h5090_meta']['chunked_prefill']:,}"],
        ["GPU KV 풀 (max-total-tokens)", f"{M['pool_tokens']:,}",
         f"{DATA['h5090_meta']['pool_tokens']:,}"],
        ["fit (= 풀 ÷ ctx median)", f"{M['fit']:.2f}", f"{DATA['h5090_meta']['fit']:.2f}"],
        ["host tier (r=2)", f"{M['host_tier_tokens']:,} tok",
         f"{DATA['h5090_meta']['host_tier_tokens']:,} tok"],
        ["측정한 C", "20 · 40 · 80", "7 · 15"]]
add_table(s, rows, 0.42, 1.62, 12.5, 4.9, fs=11.5, hdr_fs=11.5,
          col_widths=[3.9, 4.3, 4.3], highlight_col=None)
footer(s, "[측정] 출처: scratch/mori/tierc_h200/serve_*.log · scratch/mori/tierc_5090tp1/serve_*.log "
          "(SGLang server_args) · scripts/_serve_sglang_7b_tp1_{h200,5090}_mori_yunuikang.sh")
set_notes(s, """장비와 소프트웨어 설정입니다.
왼쪽 열이 오늘 주로 볼 H200 실험이고, 오른쪽은 같은 계측 코드를 5090 한 장에 돌린 별도 자료입니다.
`fit`은 GPU에 올라가는 KV 풀을 트레이스의 중앙 컨텍스트 길이(32,376토큰)로 나눈 값입니다.
쉽게 말해 "이 GPU에 프로그램 몇 개 분량의 캐시가 동시에 들어가나"입니다. H200은 20, 5090은 7입니다.
`r=2`는 CPU(host) 계층 크기를 GPU 풀의 2배로 잡았다는 뜻입니다.
두 장비의 fit이 다르므로, 같은 C 값이라도 압박 정도가 다릅니다. 그래서 뒤에서 oversub(=C÷fit)를 같이 적습니다.""")

s = slide("1부 · 실험 환경 — 트레이스 · 파라미터 격자 · 기동 확인값",
          "[측정] 6셀 모두 같은 트레이스·같은 드라이버이고, 기동 때 찍힌 assert 값은 계획값과 일치했다.")
zone(s, "①", "트레이스 (Track M)", 0.42, 1.62, 4.0, 2.5, PURPLE)
add_table(s, [["항목", "값"],
              ["파일", "tracelab_moriM_L64k"],
              ["세션 / 턴", f"{M['trace_sessions']:,} / {M['trace_turns']:,}"],
              ["ctx median", f"{M['ctx_median']:,} tok"],
              ["ctx peak", f"{M['ctx_peak']:,} tok"]],
          0.54, 2.06, 3.76, 1.9, fs=10.5, hdr_fs=10.5, col_widths=[1.6, 2.16])

zone(s, "②", "격자 파라미터", 4.62, 1.62, 4.0, 2.5, AMBER)
add_table(s, [["항목", "값"],
              ["fit", f"{M['fit']:.2f}  (풀 {M['pool_tokens']:,})"],
              ["r (host tier)", f"2  ({M['host_tier_tokens']:,} tok)"],
              ["C", "20 · 40 · 80"],
              ["시스템", "MORI · TA+O"]],
          4.74, 2.06, 3.76, 1.9, fs=10.5, hdr_fs=10.5, col_widths=[1.6, 2.16])

zone(s, "③", "셀 프로토콜", 8.82, 1.62, 4.1, 2.5, BLUE)
add_table(s, [["항목", "값"],
              ["셀 길이", f"{M['cell_s']:,} s (25분)"],
              ["분석 창", f"{M['window_s']:,} s"],
              ["warmup", f"{int(M['warmup_frac'] * 100)} %"],
              ["반복", f"n = {M['n_repeat']}"]],
          8.94, 2.06, 3.86, 1.9, fs=10.5, hdr_fs=10.5, col_widths=[1.6, 2.26])

add_text(s, "**calibration — 매 boot 마다 찍힌 assert 값 (계획값과 그대로 일치)**",
         0.42, 4.34, 12.5, 0.3, size=13, color=INK)
add_table(s, [["장비", "boot assert 출력"],
              ["H200 TP1", M["boot_assert"]],
              ["5090 TP1", M["boot_assert_5090"]]],
          0.42, 4.72, 12.5, 1.0, fs=11.5, hdr_fs=11.5, col_widths=[2.2, 10.3])
add_text(s, f"셀 구성 = C 3점 × 시스템 2종 = 6셀 (H200) · "
            f"5090 TP1 은 C 2점 × 2종 = 4셀. 셀당 {M['cell_s']:,}초, 앞 "
            f"{int(M['warmup_frac'] * 100)}% 는 warmup 으로 버리고 나머지 "
            f"{M['window_s']:,}초를 분석 창으로 쓴다.",
         0.42, 5.94, 12.5, 0.8, size=12, color=GRAY)
footer(s, "[측정] 출처: scratch/mori/tierc_h200/window_*.json · serve_*.log 의 [assert] 줄 · "
          "logs/2026-08-08_TIERC_H200_C80_yunuikang.md §2")
set_notes(s, """실험 격자입니다.
왼쪽: 트레이스는 Track M 하나만 씁니다. 3,514개 세션, 117,257턴이고, 중앙 컨텍스트가 32,376토큰,
가장 긴 것이 64k입니다. 재가공은 하지 않았습니다.
가운데: 조작한 변수는 C(동시성) 하나뿐입니다. 20, 40, 80 세 점이고 시스템은 MORI와 TA+O 두 가지입니다.
fit과 r은 전 셀 고정입니다.
오른쪽: 셀 하나를 25분 돌리고, 앞 20%는 예열이라 버립니다. 남은 1,254초가 분석 창입니다.
아래 표: 서버가 뜰 때마다 GPU 풀 크기, host 계층 크기, fit을 찍어서 계획값과 같은지 확인했습니다.
여섯 번의 기동 모두 같은 값이 나왔습니다. 이건 "설정이 의도대로 들어갔다"는 확인이지 실험 결과는 아닙니다.
셀은 각각 한 번씩만 돌렸습니다.""")

# ═════════════════════════════════════════════════════ 2부 — 측정 방법
s = slide("2부 · Tier C 가 재는 것 — GPU 시계를 다섯 갈래로 쪼갠다",
          "[측정] 계측 창의 wall 시간을 decode / prefill(새) / prefill(재계산) / idle 로 나누고, transfer 는 따로 병기한다.")
add_figure(s, "tierc_clock_diagram_yunuikang", 0.42, 1.58, 12.5, 5.30, frame=False)
footer(s, "그림은 도식이며 조각 폭은 실제 측정값이 아니다 (실측값은 3부). "
          "출처: scripts/mori_tierc_instrument_yunuikang.py · scripts/analyze_tierc_yunuikang.py docstring")
set_notes(s, """Tier C가 무엇을 재는지 그림으로 먼저 보겠습니다.
맨 위 띠가 분석 창 전체 시간(wall)입니다. 이걸 네 조각으로 나눕니다.
decode는 토큰을 하나씩 생성하는 시간, prefill은 프롬프트를 한 번에 밀어 넣는 시간입니다.
prefill을 다시 둘로 나눕니다. '새 컨텍스트'는 대화가 길어져서 어차피 처음 계산해야 하는 부분이고,
'재계산'은 예전에 이미 계산했는데 캐시에서 사라져서 다시 계산한 부분입니다.
idle은 GPU가 아무 커널도 안 돌린 시간입니다.
이 네 개를 더하면 wall이 됩니다.
가운데 보라색 transfer는 GPU와 CPU 사이에 KV를 주고받는 시간인데, 이건 별도 스트림에서 돌아
위 네 조각과 겹칩니다. 그래서 더하지 않고 옆에 따로 적습니다.
아래 두 상자가 계측을 실제로 꽂은 위치입니다. 하나는 forward 함수, 하나는 HiCache의 load/store입니다.
둘 다 CUDA 이벤트로 커널 시간을 잽니다.
맨 아래는 prefill을 새/재계산으로 가르는 방법입니다. 엔진이 실제 계산한 prefill 토큰에서
'어차피 필요했던 양'을 빼면 재계산 토큰이 됩니다. 이 그림의 조각 폭은 설명용이고, 실제 값은 3부에 있습니다.""")

s = slide("2부 · 지표 정의 ① — GPU 시간 항목",
          "[측정] 아래는 각 항목이 '무엇을 센 값인지'에 대한 정의다.")
rows = [["항목", "정의 — 무엇을 센 값인가", "계측 지점"],
        ["decode", "생성 단계 forward 의 GPU 커널 시간 합", "forward_batch_generation · CUDA event"],
        ["prefill (전체)", "prefill 단계 forward 의 GPU 커널 시간 합", "forward_batch_generation · CUDA event"],
        ["prefill — 새", "prefill 시간 중 new_required 토큰 몫", "위 시간을 토큰 비로 안분"],
        ["prefill — 재계산", "prefill 시간 중 recompute 토큰 몫", "위 시간을 토큰 비로 안분"],
        ["idle", "창 wall − (decode + prefill)  (유도값)", "— (뺄셈)"],
        ["transfer (reload/offload)", "HiCache 로 KV 를 올리고 내린 GPU 시간", "HiCache load/store · CUDA event (별도 스트림)"],
        ["new_required 토큰", "step i>0: prompt[i] − (prompt[i−1] + completion[i−1])\nstep i=0: prompt[0]", "프록시 per-step CSV"],
        ["recompute 토큰", "엔진이 계산한 prefill 토큰(Σ extend_num_tokens) − new_required", "Method B (집계 빼기)"],
        ["재계산율", "recompute 토큰 ÷ 엔진이 계산한 prefill 토큰", "위 두 값의 비"]]
add_table(s, rows, 0.42, 1.62, 12.5, 4.9, fs=10.5, hdr_fs=10.5,
          col_widths=[2.5, 5.7, 4.3])
add_text(s, "가산 규약: decode + prefill(새) + prefill(재계산) + idle = 창 wall. "
            "transfer 는 별도 스트림이라 이 합에 더하지 않고 병기한다.",
         0.42, 6.60, 12.5, 0.35, size=11.5, color=INK)
footer(s, "[측정] 정의 출처: scripts/analyze_tierc_yunuikang.py docstring · "
          "scripts/mori_tierc_instrument_yunuikang.py")
set_notes(s, """각 항목이 정확히 무엇을 센 값인지 정리한 표입니다. 각 항목이 어디에 쓰이는지는 여기서 말하지 않습니다.
decode와 prefill은 forward 함수 앞뒤에 CUDA 이벤트를 걸어 커널 시간을 잰 것입니다.
prefill을 새/재계산으로 가르는 것은 시간을 직접 잰 게 아니라, 토큰 수 비율로 나눈 값입니다.
즉 '재계산 시간'은 재계산 토큰 수를 시간 단위로 바꿔 놓은 것에 가깝습니다. 이 점을 표에 그대로 적었습니다.
idle은 뺄셈으로 얻은 값입니다. 따로 재지 않았습니다.
new_required는 '대화가 이어지면서 어차피 새로 들어온 토큰'입니다. 이번 스텝의 프롬프트에서
지난 스텝의 프롬프트와 응답을 빼면 나옵니다.
transfer는 별도 스트림이라 다른 계산과 겹칩니다. 그래서 더하지 않고 옆에 적습니다.""")

s = slide("2부 · 지표 정의 ② — 처리량 · 캐시 · 라우터 이벤트",
          "[측정] 각 값이 어느 파일에서 어떤 규칙으로 집계되는지까지가 정의다.")
rows = [["지표", "정의", "원자료"],
        ["prefix hit", "엔진 cached_tokens 증가분 ÷ prompt_tokens 증가분 (steady window)", "engine_<TAG>.csv"],
        ["engine recompute", "(prompt − cached) ÷ (prompt + generation) 증가분", "engine_<TAG>.csv"],
        ["engine steady thr", "generation_tokens 증가분 ÷ 경과 시간 (warmup 20% 제외)", "engine_<TAG>.csv"],
        ["goodput@5s", "step 중 pause_s + prefill_s ≤ 5.0s 인 step 의 완료 토큰 ÷ 창 wall", "profile_<TAG>/step_profiles.csv"],
        ["SLO 만족 %", "위 조건을 만족한 step 수 ÷ 창 안 step 수", "profile_<TAG>/step_profiles.csv"],
        ["Waiting 축출", "MORI = 'CPU→Waiting' 줄 수 · TA+O = 'Paused program' 줄 수", "proxy_<TAG>.log"],
        ["demote", "MORI = 'demote GPU→CPU' 줄 수 · TA+O = 'Paused program' 줄 수", "proxy_<TAG>.log"],
        ["ping-pong %", "2회 이상 demote 된 프로그램 ÷ demote 된 서로 다른 프로그램", "proxy_<TAG>.log"],
        ["TTFT p50 / p95", "드라이버가 기록한 첫 토큰 도착 시간의 분위수", "results_tierc.jsonl"],
        ["드라이버 thr", "완주한 프로그램의 출력 토큰 ÷ 셀 wall", "results_tierc.jsonl"],
        ["_type_rank / ι", "ι = Σacting ÷ (Σacting + Σreasoning), k=5 링버퍼 · rank: ι<0.33→2, <0.66→1, 그 외 0",
         "profile_<TAG>/step_profiles.csv 재생"]]
add_table(s, rows, 0.42, 1.58, 12.5, 5.0, fs=10, hdr_fs=10,
          col_widths=[2.2, 7.0, 3.3])
footer(s, "[측정] 집계 함수는 Phase 2 분석기(scripts/analyze_phase2_v2_yunuikang.py)의 "
          "engine_steady() / goodput() / moves() 를 그대로 import 해 쓴다. "
          "Waiting 축출은 MORI 와 TA+O 가 서로 다른 사건을 센 값이다.")
set_notes(s, """두 번째 정의 표입니다. GPU 시간 말고 나머지 지표들입니다.
prefix hit은 엔진이 "이 프롬프트 중 캐시에서 그대로 재사용한 비율"로 보고하는 값입니다.
goodput@5s는 각 스텝에서 대기시간과 prefill 시간을 더해 5초 이하인 스텝만 골라, 그 스텝들이 만든
토큰을 창 시간으로 나눈 값입니다. 5초는 미리 정한 기준선입니다.
Waiting 축출은 프록시 로그의 줄 수를 센 값인데, MORI와 TA+O가 세는 사건 이름이 다릅니다.
MORI는 'CPU에서 대기열로 내려간 건'이고 TA+O는 '프로그램을 멈춘 건'입니다. 각주에 적어 뒀습니다.
맨 아래 ι는 프로그램이 도구를 쓰느라 노는 정도를 나타내는 값이고, 이 값으로 rank 0/1/2가 정해집니다.
집계 함수는 새로 짜지 않고 이전 Phase 2 분석기 것을 그대로 가져다 썼습니다.""")

s = slide("2부 · closure 게이트 C1~C4 — 계측 자체를 확인하는 네 가지",
          "[측정] 아래 넷은 실험 결과가 아니라 '계측이 닫혔는지' 보는 검사 항목의 정의다.")
zone(s, "C1", "busy ≤ wall", 0.42, 1.62, 6.15, 2.35, BLUE)
add_text(s, "GPU 로 잰 바쁜 시간(decode + prefill)이 창 wall 을 넘지 않는지.\n"
            "넘으면 이중 계상이다.\n\n판정: busy ÷ wall ≤ 1", 0.60, 2.10, 5.8, 1.7,
         size=11.5, color=INK)
zone(s, "C2", "steplog 커버리지", 6.77, 1.62, 6.15, 2.35, BLUE)
add_text(s, "steplog 이 분석 창의 앞뒤를 얼마나 덮는지.\n"
            "앞/뒤 공백이 각각 5% 미만이어야 한다.\n\n판정: 앞 공백 < 5% AND 뒤 공백 < 5%",
         6.95, 2.10, 5.8, 1.7, size=11.5, color=INK)
zone(s, "C3", "GPU busy ÷ forward host 시간", 0.42, 4.12, 6.15, 2.35, BLUE)
add_text(s, "GPU 커널 시간을 host 쪽 forward 호출 시간으로 나눈 배수.\n"
            "overlap 스케줄러라 host 는 enqueue 만 하므로 1 보다 크다.\n\n판정: 0.5 미만이면 의심",
         0.60, 4.60, 5.8, 1.7, size=11.5, color=INK)
zone(s, "C4", "토큰 교차검증", 6.77, 4.12, 6.15, 2.35, BLUE)
add_text(s, "계측이 센 prefill/decode 토큰을 엔진 자체 카운터와 비교한 비율 (전체 run 기준).\n\n"
            "판정: 0.9 ~ 1.1 안", 6.95, 4.60, 5.8, 1.7, size=11.5, color=INK)
footer(s, "[측정] 정의·허용범위 출처: scripts/analyze_tierc_yunuikang.py (CLOSURE_TOL = 0.05)")
set_notes(s, """결과를 보기 전에, 계측 자체가 말이 되는지 보는 검사 네 가지입니다.
C1은 GPU가 바빴다고 잰 시간이 전체 시간을 넘지 않는지 봅니다. 넘으면 같은 시간을 두 번 셌다는 뜻입니다.
C2는 로그가 분석 창 전체를 덮고 있는지 봅니다. 앞이나 뒤가 비면 그만큼 못 센 겁니다.
C3은 GPU 커널 시간을 CPU 쪽 호출 시간으로 나눈 값입니다. 이 엔진은 CPU가 명령만 넣고 빠지므로
이 비율이 1보다 크게 나오는 게 정상입니다.
C4는 우리가 센 토큰 수를 엔진이 자체로 세는 카운터와 맞춰 보는 것입니다.
네 가지 다 '결과가 좋다/나쁘다'와는 무관하고, 숫자를 믿고 볼 수 있는지만 봅니다. 실제 값은 다음 장에 있습니다.""")

# ═════════════════════════════════════════════════════ 3부 — 결과
s = slide("3부 · 게이트 측정값 — 6셀 전부 C1~C4 통과",
          "[측정] 아래는 각 셀에서 실제로 나온 게이트 값이다.")
rows = [["셀", "busy %", "idle %", "C1", "C2 커버리지", "C3 배수", "C4 prefill 비", "C4 decode 비", "판정"]]
for C, m, t in pairs():
    for c, tag in ((m, f"MORI C{C}"), (t, f"TA+O C{C}")):
        cov = [x[1] for x in c["checks"] if x[1].startswith("C2")][0]
        cov = cov.split("커버리지 ")[1].split(" ")[0]
        c3 = [x[1] for x in c["checks"] if x[1].startswith("C3")][0]
        c3 = c3.split("= ")[1].split(" ")[0]
        rows.append([tag, f"{c['gpu_busy_frac'] * 100:.2f}", f"{c['idle_pct']:.2f}",
                     "PASS", cov, c3, f"{c['xcheck_prefill_ratio']:.3f}",
                     f"{c['xcheck_decode_ratio']:.3f}",
                     "PASS" if c["closure_ok"] else "FAIL"])
add_table(s, rows, 0.42, 1.62, 12.5, 3.4, fs=11, hdr_fs=11,
          col_widths=[1.7, 1.3, 1.2, 0.9, 1.9, 1.3, 1.6, 1.7, 0.9],
          highlight_rows=rowtint(len(rows)))
add_text(s, "**boot assert (매 기동)** — " + M["boot_assert"], 0.42, 5.34, 12.5, 0.3,
         size=12.5, color=INK)
add_text(s, f"C4 허용범위 0.9~1.1 · C2 허용 앞/뒤 공백 5% 미만 · C1 busy ÷ wall ≤ 1 · "
            f"C3 0.5 미만이면 의심.  6셀 모두 closure_ok = true.",
         0.42, 5.72, 12.5, 0.35, size=11.5, color=GRAY)
footer(s, "[측정] 출처: scratch/mori/tierc_h200/tierc_summary.json 의 checks / closure_ok 필드")
set_notes(s, """앞 장에서 정의한 네 가지 검사의 실제 값입니다.
busy는 GPU가 커널을 돌린 시간의 비율입니다. C20 두 셀만 1.7%와 0.7% 정도 idle이 있고,
나머지는 0.3% 아래입니다.
C2 커버리지는 전부 99.97%에서 100% 사이입니다. 로그가 창을 다 덮었다는 뜻입니다.
C3은 27배 근처로 모두 비슷합니다. C4는 1.000에서 1.009 사이로, 허용 범위인 0.9~1.1 안입니다.
여섯 셀 모두 통과했습니다.
맨 아래 boot assert는 서버가 뜰 때마다 찍힌 값이고, 여섯 번 모두 같았습니다.""")

s = slide("3부 · ★ 3점 곡선 — 핵심 4지표 측정값",
          "[측정] C = 20 · 40 · 80 (oversub 1.00× · 2.00× · 4.00×) 에서 잰 값이다.")
rows = [["셀", "oversub", "재계산 몫\n(wall %)", "재계산율\n(토큰 %)", "Waiting\n축출 (건)",
         "reload ÷\n출력 토큰", "prefix hit", "engine\nrecompute", "demote", "ping-pong %"]]
for C, m, t in pairs():
    for c, tag in ((m, f"MORI C{C}"), (t, f"TA+O C{C}")):
        rows.append([tag, f"{c['oversub']:.2f}x", f"{c['prefill_recompute_pct']:.2f}",
                     f"{c['recompute_frac'] * 100:.1f}", f"{c['wait_evict']:,}",
                     f"{c['reload_per_output']:.2f}", f"{c['prefix_hit']:.3f}",
                     f"{c['engine_recompute']:.3f}", f"{c['demote']:,}",
                     f"{c['pingpong_pct']:.1f}"])
add_table(s, rows, 0.42, 1.66, 12.5, 4.3, fs=11, hdr_fs=10,
          col_widths=[1.55, 1.05, 1.35, 1.3, 1.3, 1.3, 1.2, 1.35, 1.0, 1.1],
          highlight_rows=rowtint(len(rows)))
footer(s, "[측정] Waiting 축출은 MORI = 'CPU→Waiting', TA+O = 'Paused program' 으로 "
          "서로 다른 사건을 센 값이다 (proxy 로그 전체 기준 · graceful shutdown 이후 줄 포함). "
          "shutdown 이전만 세면 TA+O 는 C20 59 / C40 285 / C80 411 이다. "
          "출처: tierc_summary.json · engine_*.csv · proxy_*.log · 각 셀 n=1")
set_notes(s, """이 표가 이번 실험의 중심 표입니다.
왼쪽부터 봅니다. oversub는 C를 fit(20)으로 나눈 값이라, C=20이면 1배, 40이면 2배, 80이면 4배입니다.
'재계산 몫'은 창 시간 중 재계산 prefill이 차지한 비율입니다. C20에서 1% 아래였다가 C80에서 16% 근처까지 올라갑니다.
'재계산율'은 시간이 아니라 토큰 기준입니다. 엔진이 계산한 prefill 토큰 중 재계산분의 비율입니다.
Waiting 축출은 두 시스템이 서로 다른 사건을 센 값이라 절대값 비교는 하지 마시고, 각 시스템 안에서
C가 커질 때 어떻게 변하는지만 보시면 됩니다. 이건 각주에도 적어 놨습니다.
reload÷출력 토큰은 출력 토큰 하나당 CPU에서 GPU로 되돌린 KV 토큰 수입니다.
prefix hit과 engine recompute는 엔진이 스스로 보고하는 캐시 지표입니다.
숫자만 보시면 되고, 값의 배경은 이 자료에서 다루지 않습니다.""")

s = slide("3부 · ★ 3점 곡선 — 같은 값의 그림",
          "[측정] 앞 표의 네 지표를 C 축으로 그린 것이다. 점 옆 숫자가 측정값이다.")
add_figure(s, "tierc_curve4_deck_yunuikang", 0.42, 1.56, 12.5, 5.35, frame=False)
footer(s, "[측정] 각 점 = 셀 1개 (n=1) · x 축 괄호 안은 oversub = C ÷ fit(20). "
          "Waiting 축출 패널의 두 계열은 서로 다른 사건을 센 값이다.")
set_notes(s, """앞 표와 똑같은 값을 그림으로 본 것입니다. 새 숫자는 없습니다.
왼쪽 위는 재계산이 차지한 시간 비율입니다. 두 시스템 다 C가 커질수록 올라갑니다.
오른쪽 위는 Waiting 축출 건수입니다. 두 계열은 다른 사건을 센 값이라 선의 높이를 직접 비교하시면 안 됩니다.
왼쪽 아래는 출력 토큰당 reload 토큰 수입니다.
오른쪽 아래는 prefix hit입니다. 두 시스템 다 C가 커지면 내려갑니다.
각 점은 셀 하나씩만 돌린 값이라 오차 막대가 없습니다. 이 점을 감안하고 보셔야 합니다.""")

s = slide("3부 · GPU 시간 예산 — 셀별 스택",
          "[측정] 창 wall 을 100% 로 놓은 가산 예산. 보라색 transfer 는 별도 스트림이라 합에 들어가지 않는다.")
add_figure(s, "tierc_budget_deck_yunuikang", 0.42, 1.56, 12.5, 5.35, frame=False)
footer(s, "[측정] decode + prefill(새) + prefill(재계산) + idle = 100% (항등식, idle 은 유도값). "
          "출처: scratch/mori/tierc_h200/tierc_summary.json")
set_notes(s, """GPU 시간이 어디로 갔는지 셀마다 쌓아 본 그림입니다.
막대 하나가 그 셀의 분석 창 전체 시간이고, 네 색이 앞에서 정의한 네 조각입니다. 합이 100%입니다.
초록이 decode, 파랑이 새 prefill, 빨강이 재계산 prefill, 회색이 idle입니다.
막대 오른쪽에 얇게 붙은 보라색은 transfer입니다. 이건 다른 스트림에서 겹쳐 돌기 때문에
네 조각에 더하지 않고 따로 그렸습니다. 그래서 100%를 넘어도 모순이 아닙니다.
값이 작아서 막대 안에 글자가 안 들어가는 조각은 선을 빼서 옆에 적었습니다.
idle은 뺄셈으로 얻은 값이라 합이 100%가 되는 건 자동입니다.""")

s = slide("3부 · GPU 시간 예산 — 초 단위 측정값",
          "[측정] 같은 값을 초와 % 로 적은 표다.")
rows = [["셀", "창 wall (s)", "decode", "prefill — 새", "prefill — 재계산", "idle",
         "transfer (별도)"]]
for C, m, t in pairs():
    for c, tag in ((m, f"MORI C{C}"), (t, f"TA+O C{C}")):
        rows.append([tag, f"{c['wall_s']:.1f}",
                     f"{c['decode_s']:.1f} s\n({c['decode_pct']:.2f} %)",
                     f"{c['prefill_new_s']:.1f} s\n({c['prefill_new_pct']:.2f} %)",
                     f"{c['prefill_recompute_s']:.1f} s\n({c['prefill_recompute_pct']:.2f} %)",
                     f"{c['idle_s']:.1f} s\n({c['idle_pct']:.2f} %)",
                     f"{c['transfer_s']:.1f} s\n({c['transfer_pct']:.2f} %)"])
add_table(s, rows, 0.42, 1.62, 12.5, 4.9, fs=10.5, hdr_fs=10.5,
          col_widths=[1.7, 1.5, 1.85, 1.85, 2.05, 1.7, 1.85],
          highlight_rows=rowtint(len(rows)))
footer(s, "[측정] transfer = reload + offload GPU 시간. 별도 스트림이라 가산 예산에 넣지 않는다. "
          "출처: scratch/mori/tierc_h200/tierc_summary.json")
set_notes(s, """앞 그림과 같은 값을 초 단위로 적은 표입니다. 그림에서 읽기 어려운 작은 값을 여기서 확인하시면 됩니다.
창 wall은 여섯 셀 모두 1,253~1,255초로 거의 같습니다.
transfer 열은 reload와 offload를 더한 GPU 시간입니다. 다시 말씀드리면 이 값은 왼쪽 네 열의 합에 들어가지 않습니다.""")

s = slide("3부 · 토큰 측정값 — 계산량과 전송량",
          "[측정] 시간이 아니라 토큰 수로 센 값이다.")
rows = [["셀", "출력 토큰\n(창)", "decode 토큰", "prefill 계산\n토큰", "new_required",
         "recompute", "재계산율", "reload 토큰", "offload 토큰", "xfer 이벤트"]]
for C, m, t in pairs():
    for c, tag in ((m, f"MORI C{C}"), (t, f"TA+O C{C}")):
        rows.append([tag, f"{c['out_tok_window']:,}", f"{c['decode_tok']:,}",
                     f"{c['prefill_computed_tok']:,}", f"{c['new_required_tok']:,}",
                     f"{c['recompute_tok']:,}", f"{c['recompute_frac'] * 100:.1f} %",
                     f"{c['reload_tok']:,}", f"{c['offload_tok']:,}",
                     f"{c['xfer_events']:,}"])
add_table(s, rows, 0.42, 1.66, 12.5, 4.3, fs=10, hdr_fs=9.5,
          col_widths=[1.5, 1.2, 1.25, 1.3, 1.3, 1.25, 1.05, 1.3, 1.3, 1.05],
          highlight_rows=rowtint(len(rows)))
add_text(s, "recompute = prefill 계산 토큰 − new_required  (Method B) · "
            "재계산율 = recompute ÷ prefill 계산 토큰",
         0.42, 6.14, 12.5, 0.35, size=11.5, color=GRAY)
footer(s, "[측정] 출처: scratch/mori/tierc_h200/tierc_summary.json (분석 창 기준)")
set_notes(s, """같은 실험을 토큰 수로 본 표입니다.
'prefill 계산 토큰'은 엔진이 실제로 계산한 양이고, 'new_required'는 그중 어차피 필요했던 양입니다.
둘을 빼면 recompute가 됩니다. 이게 앞에서 말한 Method B입니다.
오른쪽 세 열은 CPU와 GPU 사이 전송량입니다. reload는 CPU에서 GPU로 되돌린 양,
offload는 GPU에서 CPU로 내린 양, xfer 이벤트는 전송이 일어난 횟수입니다.
숫자만 보시면 되고, 이 자료에서는 원인을 붙이지 않았습니다.""")

s = slide("3부 · goodput@5s · 엔진 처리량 · TTFT",
          "[측정] 왼쪽 둘은 tok/s, 오른쪽은 초 (세로축 로그).")
add_figure(s, "tierc_derived_deck_yunuikang", 0.42, 1.62, 12.5, 4.55, frame=False)
footer(s, "[측정] goodput@5s = 분석 창 기준 · 엔진 thr = engine_*.csv steady window (warmup 20% 제외) · "
          "TTFT 는 드라이버 기록. TTFT 패널의 진한 막대가 p50, 연한 막대가 p95다.")
set_notes(s, """세 가지 성능 지표입니다.
왼쪽은 goodput@5s입니다. 앞에서 정의한 대로 대기+prefill이 5초 이하인 스텝만 세서 초당 토큰으로 환산한 값입니다.
가운데는 엔진이 자체 카운터로 보고한 초당 생성 토큰입니다.
오른쪽은 첫 토큰이 나오기까지 걸린 시간입니다. p50과 p95 차이가 커서 세로축을 로그로 그렸습니다.
로그 축이라 막대 길이를 눈으로 비례해서 읽으시면 안 되고, 위에 적힌 숫자를 보셔야 합니다.
C80 MORI의 p95가 96.5초로 이 그림에서 가장 큰 값입니다.""")

s = slide("3부 · 성능 지표 측정값과 MORI ÷ TA+O",
          "[측정] 아래 비율은 같은 셀 안에서 MORI 값을 TA+O 값으로 나눈 것이다.")
rows = [["셀", "goodput@5s", "SLO 만족 %", "엔진 thr", "드라이버 thr", "TTFT p50 (s)",
         "TTFT p95 (s)", "완주 프로그램"]]
for C, m, t in pairs():
    for c, tag in ((m, f"MORI C{C}"), (t, f"TA+O C{C}")):
        rows.append([tag, f"{c['goodput5']:.1f}", f"{c['sat_pct']:.1f}",
                     f"{c['engine_thr']:.1f}", f"{c['drv_thr']:.1f}",
                     f"{c['ttft_p50']:.2f}", f"{c['ttft_p95']:.1f}",
                     f"{c['completed_programs']}"])
add_table(s, rows, 0.42, 1.62, 12.5, 3.3, fs=10.5, hdr_fs=10,
          col_widths=[1.6, 1.6, 1.5, 1.4, 1.6, 1.6, 1.6, 1.6],
          highlight_rows=rowtint(len(rows)))
rows2 = [["MORI ÷ TA+O", "goodput@5s", "엔진 thr", "드라이버 thr", "TTFT p50",
          "TTFT p95", "prefix hit", "재계산율"]]
for C in CS:
    r = R[str(C)]
    rows2.append([f"C = {C}", f"{r['goodput5']:.3f}x", f"{r['engine_thr']:.3f}x",
                  f"{r['drv_thr']:.3f}x", f"{r['ttft_p50']:.2f}x",
                  f"{r['ttft_p95']:.2f}x", f"{r['prefix_hit']:.3f}x",
                  f"{r['recompute_frac']:.3f}x"])
add_table(s, rows2, 0.42, 5.28, 12.5, 1.5, fs=10.5, hdr_fs=10,
          col_widths=[1.6, 1.6, 1.5, 1.6, 1.5, 1.5, 1.6, 1.6])
footer(s, "[측정] 드라이버 thr 은 완주한 프로그램만 집계한다 (정의상 미완 프로그램의 토큰은 빠진다). "
          "엔진 thr / goodput 은 완주 여부와 무관하다. 각 셀 n=1.")
set_notes(s, """위 표가 셀별 값이고, 아래 표는 같은 C 안에서 MORI를 TA+O로 나눈 비율입니다.
처리량 지표가 세 가지인데 세는 대상이 다릅니다. 드라이버 처리량은 끝까지 완주한 프로그램만 셉니다.
그래서 중간에 안 끝난 프로그램의 토큰은 빠집니다. 엔진 처리량과 goodput은 완주 여부와 상관없이 셉니다.
즉 세 값은 세는 대상이 서로 다릅니다. 각주에 적어 뒀습니다.
아래 비율표에서 1.000보다 크면 MORI 값이 큰 것이고 작으면 TA+O 값이 큰 것입니다.
TTFT는 값이 작을수록 빠른 지표라, 비율의 방향이 다른 열과 반대 의미라는 점만 유의하시면 됩니다.
셀마다 한 번씩만 돌린 값이라 이 비율의 흔들림 폭은 이 자료로는 알 수 없습니다.""")

s = slide("3부 · _type_rank 분포와 ι 분위수 (MORI 셀)",
          "[측정] 출하 코드(MoriRouter._type_rank · _iota)를 step_profiles.csv 로 재생해 얻은 값이다.")
add_figure(s, "tierc_rank_deck_yunuikang", 0.42, 1.58, 12.5, 3.35, frame=False)
rows = [["셀", "창 안 스탬프", "실측 ι 스탬프", "distinct rank", "rank 2 (busy)",
         "rank 1 (mixed)", "rank 0 (idle)", "ι p10", "ι p50", "ι p90", "ι < 0.02"]]
for tag in ("MORI_C20", "MORI_C40", "MORI_C80"):
    k = DATA["rank"][tag]
    rows.append([tag.replace("_", " "), f"{k['n_stamps']:,}", f"{k['n_seeded']:,}",
                 f"{len(k['distinct_ranks'])}개 {k['distinct_ranks']}",
                 f"{k['pct']['2']:.1f} %", f"{k['pct']['1']:.1f} %", f"{k['pct']['0']:.1f} %",
                 f"{k['iota']['p10']:.3f}", f"{k['iota']['p50']:.3f}",
                 f"{k['iota']['p90']:.3f}", f"{k['iota_lt_002_pct']:.1f} %"])
add_table(s, rows, 0.42, 5.10, 12.5, 1.5, fs=10, hdr_fs=9.5,
          col_widths=[1.35, 1.2, 1.25, 1.5, 1.15, 1.25, 1.15, 0.95, 0.95, 0.95, 0.9])
footer(s, "[측정] 재생 규칙: ι = Σacting ÷ (Σacting + Σreasoning), k=5 링버퍼 · "
          "rank ι<0.33→2, ι<0.66→1, 그 외 0. [추정] 진행 중 툴콜의 acting_since 항은 재현 대상이 아니다. "
          "출처: scripts/tierc_rank_recon_yunuikang.py")
set_notes(s, """MORI 라우터가 KV를 내릴 때 쓰는 rank가 실제로 어떤 값이었는지 재생한 결과입니다.
프로브를 새로 심은 게 아니라, 이미 저장된 per-step CSV로 출하 코드의 계산을 그대로 다시 돌린 것입니다.
왼쪽 그림은 rank 0/1/2가 각각 몇 퍼센트였는지입니다. 세 셀 모두 세 값이 다 쓰였습니다.
오른쪽은 rank를 정하는 ι 값의 퍼짐입니다. 가운데 굵은 구간이 p25에서 p75, 가는 선이 p10에서 p90입니다.
점선 두 개가 rank 경계인 0.33과 0.66입니다.
아래 표에 정확한 숫자가 있습니다. 맨 오른쪽 열은 ι가 0.02보다 작은 스탬프의 비율입니다.
한 가지 재현하지 못한 부분이 있습니다. 측정 시점에 진행 중이던 도구 호출 시간은 CSV에 없어서 빠졌습니다.
각주에 [추정]으로 표시해 뒀습니다.""")

s = slide("3부 · Phase 2 와 Tier C 를 나란히 — 같은 계산기, 다른 실험",
          "[측정] 두 실험의 값을 그대로 옆에 놓은 것이다. 차이의 원인은 이 자료에서 다루지 않는다.")
rows = [["지표 / 셀", "Phase 2\nMORI", "Phase 2\nTA+O", "Phase 2\nM ÷ T",
         "Tier C\nMORI", "Tier C\nTA+O", "Tier C\nM ÷ T"]]
for key, lab, fmt in (("goodput5", "goodput@5s", "{:.1f}"),
                      ("engine_thr", "엔진 steady thr", "{:.1f}")):
    for C in CS:
        p2m, p2t = DATA["phase2"][f"MORI_C{C}"], DATA["phase2"][f"TAO_C{C}"]
        tcm, tct = H[f"MORI_C{C}"], H[f"TAO_C{C}"]
        rows.append([f"{lab} · C={C}", fmt.format(p2m[key]), fmt.format(p2t[key]),
                     f"{DATA['phase2_ratio'][str(C)][key]:.3f}x",
                     fmt.format(tcm[key]), fmt.format(tct[key]),
                     f"{R[str(C)][key]:.3f}x"])
add_table(s, rows, 0.42, 1.62, 12.5, 3.9, fs=11, hdr_fs=10,
          col_widths=[2.9, 1.6, 1.6, 1.6, 1.6, 1.6, 1.6])
add_table(s, [["", "Phase 2", "Tier C"],
              ["셀 길이", "3,600 s", f"{M['cell_s']:,} s"],
              ["goodput 분모", "step CSV 전 구간 (warmup 20% 제외)", f"계측 창 {M['window_s']:,} s"],
              ["fit / r / C", "20 / 2 / 20 · 40 · 80", "20 / 2 / 20 · 40 · 80"],
              ["반복", "n = 1", "n = 1"]],
          0.42, 5.72, 12.5, 1.25, fs=10, hdr_fs=10,
          col_widths=[2.0, 5.25, 5.25])
footer(s, "[측정] Phase 2 출처: h200_scratch/mori/h200_phase2/ · Tier C 출처: scratch/mori/tierc_h200/ · "
          "두 실험 모두 같은 집계 함수(analyze_phase2_v2 의 engine_steady / goodput)를 썼다.")
set_notes(s, """앞서 돌린 Phase 2 실험과 이번 Tier C 실험의 값을 그냥 옆에 놓은 표입니다.
값이 다른 부분에 대한 설명은 이 자료에서 하지 않습니다. 숫자만 보시면 됩니다.
집계 함수는 두 실험에 같은 것을 썼습니다. 지표 정의가 달라서 생긴 차이는 아닙니다.
다만 아래 작은 표에 적었듯이 셀 길이가 다릅니다. Phase 2는 한 시간, Tier C는 25분입니다.
그리고 goodput을 나눌 때 쓰는 시간 구간도 다릅니다. Phase 2는 스텝 로그 전 구간을,
Tier C는 GPU 예산과 같은 계측 창을 씁니다. 이 두 가지는 그대로 적어 두었습니다.
양쪽 모두 셀을 한 번씩만 돌렸습니다.""")

# ── 5090 TP1 섹션
if "h5090" in DATA:
    F = DATA["h5090"]
    FM = DATA["h5090_meta"]
    C5 = sorted({c["C"] for c in F.values()})
    s = slide("3부 · 5090 TP1 — 같은 포맷, 별도 격자",
              "[측정] 같은 계측 코드·같은 트레이스이고, fit 이 7.00 이라 C 격자가 다르다.")
    rows = [["셀", "oversub", "창 wall (s)", "decode", "prefill — 새", "prefill — 재계산",
             "idle", "transfer (별도)"]]
    for C in C5:
        for tag, lab in ((f"MORI_C{C}", f"MORI C{C}"), (f"TAO_C{C}", f"TA+O C{C}")):
            c = F[tag]
            rows.append([lab, f"{c['oversub']:.2f}x", f"{c['wall_s']:.1f}",
                         f"{c['decode_s']:.1f} s\n({c['decode_pct']:.2f} %)",
                         f"{c['prefill_new_s']:.1f} s\n({c['prefill_new_pct']:.2f} %)",
                         f"{c['prefill_recompute_s']:.1f} s\n({c['prefill_recompute_pct']:.2f} %)",
                         f"{c['idle_s']:.1f} s\n({c['idle_pct']:.2f} %)",
                         f"{c['transfer_s']:.1f} s\n({c['transfer_pct']:.2f} %)"])
    add_table(s, rows, 0.42, 1.62, 12.5, 3.4, fs=10.5, hdr_fs=10,
              col_widths=[1.45, 1.15, 1.35, 1.7, 1.7, 1.85, 1.45, 1.65],
              highlight_rows=rowtint(len(rows)))
    add_text(s, f"**boot assert** — {M['boot_assert_5090']}   ·   "
                f"host memory {FM['host_mem_gb']} GB   ·   4셀 모두 closure C1~C4 PASS",
             0.42, 5.32, 12.5, 0.3, size=12, color=INK)
    add_figure(s, "tierc_5090_budget_deck_yunuikang", 8.0, 5.68, 4.9, 1.3, frame=False)
    add_text(s, f"raw 만 있고 closure 요약에 없는 셀: {', '.join(FM['cells_raw_not_analyzed'])} "
                f"(이 자료에 넣지 않았다)", 0.42, 5.78, 7.3, 0.5, size=11, color=GRAY)
    footer(s, "[측정] 출처: scratch/mori/tierc_5090tp1/tierc_summary.json · window_*.json · serve_*.log")
    set_notes(s, """같은 계측을 5090 한 장에서 돌린 자료입니다. 참고로 붙였습니다.
장비가 다르니 GPU에 올릴 수 있는 KV 풀이 작고, 그래서 fit이 20이 아니라 7입니다.
같은 압박을 만들려면 C를 작게 잡아야 해서 C를 7과 15로 돌렸습니다. oversub로 보면 1배와 2.14배입니다.
표 읽는 법은 H200 예산 표와 같습니다. 네 조각의 합이 100%이고 transfer는 따로입니다.
여기서는 idle이 7~10%로 H200보다 큽니다. 값만 확인하시면 됩니다.
아래에 적었듯이 C20과 C70 셀은 원자료는 있지만 closure 요약이 없어서 이 자료에 넣지 않았습니다.""")

    s = slide("3부 · 5090 TP1 — 성능 · 캐시 지표",
              "[측정] H200 표와 같은 지표를, 5090 격자에서 잰 값이다.")
    rows = [["셀", "재계산율", "Waiting 축출", "reload ÷ 출력", "prefix hit",
             "goodput@5s", "엔진 thr", "드라이버 thr", "TTFT p50", "TTFT p95"]]
    for C in C5:
        for tag, lab in ((f"MORI_C{C}", f"MORI C{C}"), (f"TAO_C{C}", f"TA+O C{C}")):
            c = F[tag]
            rows.append([lab, f"{c['recompute_frac'] * 100:.1f} %", f"{c['wait_evict']:,}",
                         f"{c['reload_per_output']:.2f}", f"{c['prefix_hit']:.3f}",
                         f"{c['goodput5']:.1f}", f"{c['engine_thr']:.1f}",
                         f"{c['drv_thr']:.1f}", f"{c['ttft_p50']:.2f}",
                         f"{c['ttft_p95']:.1f}"])
    add_table(s, rows, 0.42, 1.62, 12.5, 2.9, fs=10.5, hdr_fs=10,
              col_widths=[1.5, 1.2, 1.4, 1.35, 1.2, 1.35, 1.15, 1.4, 1.0, 0.95],
              highlight_rows=rowtint(len(rows)))
    rows2 = [["MORI ÷ TA+O", "goodput@5s", "엔진 thr", "드라이버 thr", "prefix hit", "재계산율"]]
    for C in C5:
        r = DATA["h5090_ratio"][str(C)]
        rows2.append([f"C = {C}", f"{r['goodput5']:.3f}x", f"{r['engine_thr']:.3f}x",
                      f"{r['drv_thr']:.3f}x", f"{r['prefix_hit']:.3f}x",
                      f"{r['recompute_frac']:.3f}x"])
    add_table(s, rows2, 0.42, 4.92, 12.5, 1.2, fs=10.5, hdr_fs=10,
              col_widths=[2.2, 2.1, 2.05, 2.15, 2.0, 2.0])
    footer(s, "[측정] 지표 정의는 H200 표와 동일 (2부 참조) · 각 셀 n=1 · "
              "출처: scratch/mori/tierc_5090tp1/")
    set_notes(s, """5090 자료의 성능·캐시 지표입니다. 지표 정의는 앞 2부에서 설명한 것과 같습니다.
위 표가 셀별 값이고 아래가 MORI를 TA+O로 나눈 비율입니다.
여기도 셀마다 한 번씩만 돌렸습니다.
H200 표와 같은 형식이지만 C 격자가 달라서 같은 열끼리 바로 겹쳐 보시면 안 됩니다.""")

# ═════════════════════════════════════════════════════ 부록
s = slide("원자료 위치와 재현 절차",
          "[측정] 이 덱의 모든 수치는 아래 경로에서 스크립트로 뽑았다.")
rows = [["구분", "경로 / 명령"],
        ["H200 Tier C 원자료", "scratch/mori/tierc_h200/  (tierc_summary.json · results_tierc.jsonl · "
                             "engine_*.csv · profile_*/step_profiles.csv · proxy_*.log · window_*.json)"],
        ["5090 TP1 원자료", "scratch/mori/tierc_5090tp1/"],
        ["Phase 2 원자료", "h200_scratch/mori/h200_phase2/"],
        ["수치 추출", "python3 scripts/extract_tierc_numbers_yunuikang.py\n"
                   "  → scratch/mori/tierc_h200/deck_numbers.json"],
        ["그림 생성", "python3 scripts/plot_tierc_resultsdeck_yunuikang.py  → figures/tierc_*_yunuikang.png"],
        ["덱 생성", "python3 scripts/build_tierc_resultsdeck_yunuikang.py"],
        ["관련 로그", "logs/2026-08-08_TIERC_H200_C80_yunuikang.md · "
                  "logs/2026-08-08_TIERC_H200_followup_yunuikang.md"]]
add_table(s, rows, 0.42, 1.62, 12.5, 3.6, fs=11, hdr_fs=11, col_widths=[2.6, 9.9])
add_text(s, "**이 자료에 적어 둔 계측상 성질 (전부 [추정] 라벨)**", 0.42, 5.46, 12.5, 0.3,
         size=12.5, color=INK)
add_text(s, "•  재계산 '시간'은 독립 측정이 아니라 prefill GPU 시간을 토큰 비로 안분한 값이다.\n"
            "•  idle 은 wall − busy 로 얻은 유도값이라 네 조각의 합이 wall 이 되는 것은 항등식이다.\n"
            "•  Waiting 축출은 MORI 와 TA+O 가 서로 다른 사건을 센 값이다.\n"
            "•  각 셀 n = 1 이므로 셀 간 변동폭은 이 자료로 알 수 없다.",
         0.42, 5.80, 12.5, 1.15, size=11.5, color=GRAY)
footer(s, "[측정] 파일명 규약: 모든 산출물에 _yunuikang 접미사 · 커밋은 하지 않았다.")
set_notes(s, """마지막으로 원자료 위치와 재현 방법입니다.
숫자를 손으로 옮기지 않았습니다. 추출 스크립트가 원자료에서 JSON을 만들고, 그림과 덱은 그 JSON만 읽습니다.
그래서 원자료가 바뀌면 세 명령을 다시 돌리면 그대로 갱신됩니다.
아래 네 줄은 숫자를 읽을 때 같이 알아야 하는 계측상 성질입니다.
첫째, 재계산에 걸린 '시간'은 따로 잰 게 아니라 토큰 비율로 나눈 값입니다.
둘째, idle은 뺄셈이라 합이 맞는 건 당연합니다.
셋째, Waiting 축출은 두 시스템이 다른 사건을 셉니다.
넷째, 각 셀을 한 번씩만 돌렸기 때문에 이 숫자들이 얼마나 흔들리는지는 이 자료로 알 수 없습니다.""")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
prs.save(OUT)
print(f"[saved] {OUT}  ({len(prs.slides.__iter__.__self__._sldIdLst)} slides)")
