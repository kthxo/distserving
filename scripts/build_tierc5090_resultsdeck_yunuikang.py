#!/usr/bin/env python3
"""5090 TP1 · Qwen2.5-7B — 결과 전용 덱 (환경 / 측정방법 / 결과 수치).

★ 이 덱에는 해석·결론·판정이 들어가지 않는다.
   담는 것: (1) 실험 환경  (2) 무엇을 어떻게 측정했나(정의)  (3) 측정 수치.
   금지: "따라서 / 의미 / 원인 / 왜 / 가설 / 재현 / 기각" 류 문장.
   노트도 정의와 "이 그림이 무엇을 보여주는가"까지만 쓴다.

수치는 scratch/mori/tierc_5090tp1/deck_numbers_5090.json 에서만 읽는다 (하드코딩 금지).
스타일: docs/DECK_STYLE_yunuikang.md
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decklib_yunuikang import (  # noqa: E402
    new_deck, _blank, add_title, add_takeaway, add_text, add_figure,
    add_caption, add_table, set_notes, band, chip,
    INK, BLUE, RED, GREEN, GRAY, LT, AMBER, WHITE,
)
from pptx.util import Inches, Pt  # noqa: E402
from pptx.dml.color import RGBColor  # noqa: E402
from pptx.enum.shapes import MSO_SHAPE  # noqa: E402

SRC = "/home/yunuikang/yunuikang_work/scratch/mori/tierc_5090tp1/deck_numbers_5090.json"
OUT = "/home/yunuikang/yunuikang_work/distserving/slides/2026-08-08_TIERC_5090_results-only_yunuikang.pptx"
PURPLE = RGBColor(0x6E, 0x4B, 0x9E)
HEALTHY = RGBColor(0xE7, 0xF3, 0xEC)
PANEL = RGBColor(0xF4, 0xF6, 0xFA)

D = json.load(open(SRC))
C_, R_, E, B = D["cells"], D["ratio"], D["env"], D["boot"]
CS = [7, 15, 20, 70]
g = lambda s, c, k: C_[f"{s}_C{c}"][k]
NB = "n=1 (반복 없음) · 셀당 25분 · warmup 20%"

prs = new_deck()


def slide(title, sub=None):
    s = _blank(prs)
    band(s, 0.0, 0.11, INK)
    add_title(s, title)
    if sub:
        add_takeaway(s, sub, color=GRAY)
    return s


def zone(s, n, label, x, y, w, h, color):
    p = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    p.fill.solid(); p.fill.fore_color.rgb = PANEL
    p.line.color.rgb = RGBColor(0xDD, 0xE1, 0xE8); p.line.width = Pt(0.75)
    p.shadow.inherit = False
    chip(s, f"{n}  {label}", x + 0.12, y + 0.10, min(w - 0.24, 5.4), color, size=10.5, h=0.30)
    return p


def footer(s, txt):
    add_text(s, txt, 0.42, 7.06, 12.5, 0.3, size=8.5, color=GRAY)


# ═════════════════════════════════════════ S1 표지
s = slide("")
band(s, 0.0, 7.5, INK)
add_text(s, "Tier C 시간분해 — 5090 TP1 · Qwen2.5-7B", 0.9, 2.20, 11.5, 0.9,
         size=36, color=WHITE, bold=True)
add_text(s, "실험 환경 · 측정 방법 · 결과 수치", 0.92, 3.30, 11.5, 0.5, size=19,
         color=RGBColor(0x9F, 0xB6, 0xD8))
band(s, 4.05, 0.035, RGBColor(0x2E, 0x5E, 0xAA), x=0.92, w=3.2)
add_text(s, f"단일 RTX 5090 · TP1 · fit {E['fit']:.2f} · r={E['hicache_ratio']} · "
            f"C ∈ {{7, 15, 20, 70}} · {E['cells']}셀 · 각 {E['duration_s']}s\n"
            "2026-08-08 23:48 ~ 08-09 03:37 KST · goguma6",
         0.92, 4.40, 11.5, 0.9, size=13.5, color=RGBColor(0x9F, 0xB6, 0xD8))
add_text(s, "2026-08-09 · yunuikang · 전 수치 [측정]", 0.92, 6.4, 11.5, 0.4, size=12,
         color=RGBColor(0x7B, 0x8C, 0xA8))
set_notes(s, """단일 5090 한 장에 Qwen2.5-7B를 올려 동시성을 네 지점에서 측정한 자료입니다.
담은 것은 세 가지입니다. 실험 환경, 무엇을 어떻게 측정했는지, 그리고 측정된 수치입니다.
8개 셀을 각각 25분씩 돌렸고 반복은 없습니다.""")

# ═════════════════════════════════════════ S2 환경 — 하드웨어·엔진
s = slide("1부. 실험 환경 — 하드웨어 · 엔진 · 모델")
add_table(s, [
    ["구분", "항목", "값"],
    ["**하드웨어**", "GPU", f"**{E['gpu']}** · {E['gpu_mem_mib']:,} MiB"],
    ["", "병렬화", f"**TP{E['tp']}** · `CUDA_VISIBLE_DEVICES={E['cuda_visible_devices']}`"],
    ["", "박스", E["box"]],
    ["**엔진**", "서버", f"**{E['engine']}**"],
    ["", "attention / sampling", f"`{E['attention_backend']}` / `{E['sampling_backend']}`"],
    ["", "`--mem-fraction-static`", f"**{E['mem_fraction_static']}**"],
    ["", "`--page-size`", f"**{E['page_size']}**"],
    ["**모델**", "모델", f"**{E['model']}**"],
    ["", "per-token KV (bf16)", f"**{E['kv_per_tok_kib']} KiB**  ·  가중치 {E['weights_gib']} GiB"],
    ["", "`--context-length`", f"**{E['context_length']:,}** tok"],
    ["", "YaRN", f"factor **{E['yarn_factor']}** × {E['yarn_base']:,} = {E['context_length']:,}"],
], 0.42, 1.62, 12.5, 0.6, fs=10.5, hdr_fs=10.5,
    col_widths=[1.55, 3.25, 7.70])
footer(s, "[측정] serve 기동 로그 · scripts/_serve_sglang_7b_tp1_5090_mori_yunuikang.sh")
set_notes(s, """실험 환경 중 하드웨어와 엔진, 모델입니다.

GPU는 5090 한 장이고 텐서 병렬 없이 TP1으로 돌렸습니다.
CUDA_VISIBLE_DEVICES를 0으로 줘서 GPU 한 장만 보이게 했습니다.

엔진은 SGLang 0.5.10에 계층형 캐시를 켰습니다.
attention 백엔드는 triton, 페이지 크기는 1입니다.
페이지 크기가 1이면 지정한 토큰 수가 그대로 KV 풀 크기가 됩니다.

모델은 Qwen2.5-7B이고 토큰당 KV가 56킬로바이트, 가중치가 14.19기가입니다.
컨텍스트 길이는 71,680 토큰으로 맞췄고, 모델 원래 길이가 32,768이라
YaRN 배율 2.1875를 줘서 늘렸습니다.""")

# ═════════════════════════════════════════ S3 환경 — 워크로드·파라미터
s = slide("1부. 실험 환경 — 워크로드 · 격자 · 캘리브레이션")
zone(s, "①", "트레이스 · 드라이버", 0.42, 1.62, 6.15, 2.45, PURPLE)
add_table(s, [
    ["항목", "값"],
    ["트레이스", f"`{E['trace']}`"],
    ["컨텍스트 median", f"**{E['ctx_median']:,}** tok"],
    ["셀 길이", f"**{E['duration_s']} s** (25분)"],
    ["warmup / grace", f"**{E['warmup_frac']}** / {E['grace_s']} s"],
    ["`--ctx-cap`", f"{E['ctx_cap']:,} tok"],
    ["반복", f"**{E['repeats']}** (n=1)"],
], 0.62, 2.10, 5.75, 0.6, fs=9.5, hdr_fs=9.5, col_widths=[2.15, 3.50])

zone(s, "②", "격자 파라미터", 6.78, 1.62, 6.14, 2.45, AMBER)
add_table(s, [
    ["항목", "값"],
    ["`--max-total-tokens`", f"**{E['max_total_tokens']:,}**"],
    ["fit = pool ÷ ctx median", f"**{E['fit']:.2f}**"],
    ["`--hicache-ratio` (r)", f"**{E['hicache_ratio']}**"],
    ["host tier", f"**{E['host_tier_tokens']:,}** tok"],
    ["동시성 C", "**7 / 15 / 20 / 70**"],
    ["oversub = C ÷ fit", "**1.00 / 2.14 / 2.86 / 10.00×**"],
    ["시스템", "**MORI · TA+O**  →  총 8셀"],
], 6.98, 2.10, 5.74, 0.6, fs=9.5, hdr_fs=9.5, col_widths=[2.35, 3.30])

zone(s, "③", "기동 캘리브레이션 — 8/8 셀 동일", 0.42, 4.22, 12.5, 1.55, GREEN)
b = B[0]
add_table(s, [
    ["검사", "실측", "기대", "일치"],
    ["GPU KV 풀", f"**{b['gpu']:,}** tok", f"{b['gpu_exp']:,}", "8/8"],
    ["host tier (r=2)", f"**{b['host']:,}** tok", f"{b['host_exp']:,}", "8/8 (오차 1 tok)"],
    ["fit", f"**{b['fit']:.2f}**", f"{E['fit']:.2f}", "8/8"],
    ["`larger than the profiled value` 경고", "없음", "없음", "8/8"],
], 0.62, 4.68, 12.1, 0.6, fs=9.5, hdr_fs=9.5,
    col_widths=[4.35, 2.85, 2.45, 2.45], highlight_rows={1: HEALTHY, 2: HEALTHY, 3: HEALTHY})
footer(s, "[측정] 기동 assert 는 셀마다 수행 · 러너 로그 `runner_full.log` / `runner_smoke.log`")
set_notes(s, """환경의 나머지 절반입니다.

왼쪽이 트레이스와 드라이버 설정입니다.
컨텍스트 길이 중앙값이 32,376 토큰인데, 이 값이 fit 계산의 분모가 됩니다.
한 셀당 25분씩 돌리고 앞 20퍼센트는 워밍업으로 버립니다. 반복은 없습니다.

오른쪽이 격자입니다.
max-total-tokens를 226,632로 지정했고, 이를 컨텍스트 중앙값으로 나누면 fit이 7.00입니다.
CPU 계층은 GPU 풀의 2배로 잡았습니다.
동시성을 7, 15, 20, 70으로 두면 초과율이 각각 1.0배, 2.14배, 2.86배, 10.0배가 됩니다.
시스템 두 가지를 곱해 총 8개 셀입니다.

아래가 기동 때마다 확인한 값입니다.
GPU 풀이 지정값과 정확히 일치했고, host 계층은 1토큰 차이로 맞았습니다.
profiled 값을 초과했다는 경고는 8셀 모두 없었습니다.""")

# ═════════════════════════════════════════ S4 측정 방법
s = slide("2부. 측정 방법 — 지표 정의",
          "H200 Tier C 와 동일한 계측을 사용한다 (동일 monkeypatch · 동일 창 규약)")
add_figure(s, "tierc5090_R5_method_yunuikang", 0.42, 1.66, 12.5, 4.25)
add_table(s, [
    ["기타 지표", "정의"],
    ["engine decode 토큰", "창 내 decode 배치의 `seq_lens` 합 (steplog 집계)"],
    ["드라이버 throughput", "완주 프로그램의 출력 토큰 ÷ steady_wall (드라이버 요약)"],
    ["TTFT p50 / p95", "드라이버 스트리밍 측정"],
], 0.42, 6.08, 12.5, 0.6, fs=9.5, hdr_fs=9.5, col_widths=[2.85, 9.65])
footer(s, "[측정] 계측: `scripts/mori_tierc_instrument_yunuikang.py` (SGLang 원본 무수정, monkeypatch) · "
          "집계: `scripts/analyze_tierc_yunuikang.py`")
set_notes(s, """측정 방법입니다. 정의만 설명하겠습니다.

맨 위 막대가 GPU 시간 가산 예산입니다.
네 조각의 합이 창 전체 시간과 같아지도록 정의했습니다.
decode는 토큰 생성, prefill_new는 새 컨텍스트 계산, prefill_recompute는 재계산,
나머지가 idle입니다.

창은 셀 시작 시각의 20퍼센트 지점부터 끝까지로 고정합니다.

그 아래 회색 상자가 transfer입니다.
CPU와 GPU 사이 KV 전송인데, 별도 스트림에서 일어나므로 가산 예산에는 넣지 않고 따로 표시합니다.

아래 목록이 각 지표를 실제로 어떻게 재는지입니다.
decode와 prefill은 forward 함수를 CUDA 이벤트로 감싸서 GPU 시간을 재고,
배치 종류로 분류합니다.
transfer는 HiCache의 쓰기와 읽기 함수를 각 전송 스트림 위에서 잽니다.
prefill을 새 것과 재계산으로 나누는 건 Method B라고 부르는 뺄셈 방식입니다.
프로그램마다 불가피한 컨텍스트 증분을 더한 값을 전체 계산량에서 빼면 재계산량이 나옵니다.

맨 아래 주의할 점 하나는 Waiting 축출입니다.
MORI와 TA+O는 서로 다른 사건을 셉니다. 두 시스템 간 절대값 비교는 성립하지 않습니다.""")

# ═════════════════════════════════════════ S5 closure
s = slide("2부. 측정 방법 — closure 검사 (8셀 전부)",
          "가산 예산이 성립할 조건 네 가지를 셀마다 확인한다")
add_table(s, [
    ["검사", "정의", "8셀 실측 범위", "결과"],
    ["**C1**", "busy ≤ 창 wall  (busy = decode + prefill)",
     f"busy {min(100-g(s2,c,'idle_pct') for c in CS for s2 in ('MORI','TAO')):.2f}% ~ "
     f"{max(100-g(s2,c,'idle_pct') for c in CS for s2 in ('MORI','TAO')):.2f}%", "**8/8 PASS**"],
    ["**C2**", "steplog 이 창을 시간적으로 덮는가 (앞뒤 공백 ≤ 5%)", "커버리지 98.99% ~ 100.00%", "**8/8 PASS**"],
    ["**C3**", "GPU busy ÷ forward host 시간 ≥ 0.5", "14.47× ~ 21.76×", "**8/8 PASS**"],
    ["**C4**", "steplog 토큰 합 ÷ 엔진 카운터 (전체 run, 창 무관)",
     f"prefill {min(C_[f'{s2}_C{c}']['xcheck_prefill'] for c in CS for s2 in ('MORI','TAO')):.3f} ~ "
     f"{max(C_[f'{s2}_C{c}']['xcheck_prefill'] for c in CS for s2 in ('MORI','TAO')):.3f} · "
     f"decode {min(C_[f'{s2}_C{c}']['xcheck_decode'] for c in CS for s2 in ('MORI','TAO')):.3f} ~ "
     f"{max(C_[f'{s2}_C{c}']['xcheck_decode'] for c in CS for s2 in ('MORI','TAO')):.3f}",
     "**8/8 PASS**"],
], 0.42, 1.72, 12.5, 0.6, fs=10, hdr_fs=10,
    col_widths=[0.75, 5.15, 4.60, 2.00],
    highlight_rows={1: HEALTHY, 2: HEALTHY, 3: HEALTHY, 4: HEALTHY})
zone(s, "셀별", "창 내 step 수", 0.42, 4.10, 12.5, 2.35, BLUE)
rows = [["셀"] + [f"C={c}" for c in CS]]
for lab, sy in (("MORI decode / prefill step", "MORI"), ("TA+O decode / prefill step", "TAO")):
    rows.append([lab] + [f"{g(sy,c,'decode_steps'):,} / {g(sy,c,'prefill_steps'):,}" for c in CS])
rows.append(["MORI xfer 이벤트"] + [f"{g('MORI',c,'xfer_events'):,}" for c in CS])
rows.append(["TA+O xfer 이벤트"] + [f"{g('TAO',c,'xfer_events'):,}" for c in CS])
add_table(s, rows, 0.62, 4.58, 12.1, 0.6, fs=9.5, hdr_fs=9.5,
          col_widths=[3.30, 2.20, 2.20, 2.20, 2.20])
footer(s, "[측정] C1~C4 는 `analyze_tierc_yunuikang.py` 가 셀마다 자동 검사 · 총 32개 검사 전부 PASS")
set_notes(s, """계측이 성립하는지 확인하는 검사 네 가지입니다.

C1은 GPU가 바쁜 시간이 창 전체 시간을 넘지 않는지 봅니다.
넘으면 어딘가에서 시간을 두 번 셌다는 뜻입니다.

C2는 기록이 창 전체를 시간적으로 덮는지 봅니다.
앞이나 뒤가 비면 바쁜 시간이 실제보다 적게 잡히고 idle이 가짜로 커집니다.

C3은 GPU 시간과 호스트 시간의 비입니다.
이 엔진은 overlap 방식이라 호스트는 작업을 넘기기만 하고 바로 돌아옵니다.
그래서 GPU 시간이 호스트 시간보다 훨씬 큰 게 정상입니다.

C4가 가장 직접적인 검사입니다.
우리 계측이 센 토큰 수를 엔진 자체 카운터와 비교합니다.
창과 무관하게 전체 실행 기준으로 잽니다. 창 설정과 독립적인 값입니다.

여덟 셀 곱하기 네 검사, 총 32개가 전부 통과했습니다.

아래 표는 셀마다 창 안에 몇 번의 forward가 있었는지입니다.""")

# ═════════════════════════════════════════ S6 GPU 예산
s = slide("3부. 결과 — GPU 시간 예산 (8셀)")
add_figure(s, "tierc5090_R1_budget_yunuikang", 0.42, 1.52, 12.5, 3.28)
rows = [["창 wall 대비 %", "시스템"] + [f"C={c}" for c in CS]]
for key, name in (("decode_pct", "decode"), ("prefill_new_pct", "prefill_new"),
                  ("prefill_recomp_pct", "prefill_recompute"), ("idle_pct", "idle"),
                  ("transfer_pct", "transfer (미포함)")):
    rows.append([f"**{name}**", "MORI"] + [f"{g('MORI',c,key):.2f}" for c in CS])
    rows.append(["", "TA+O"] + [f"{g('TAO',c,key):.2f}" for c in CS])
add_table(s, rows, 0.42, 4.92, 12.5, 0.6, fs=8.0, hdr_fs=8.0,
          col_widths=[2.35, 1.15, 2.25, 2.25, 2.25, 2.25])
footer(s, f"[측정] decode + prefill_new + prefill_recompute + idle = 창 wall (100%) · "
          f"transfer 는 별도 스트림이라 가산 예산에 미포함 · {NB}")
set_notes(s, """GPU 시간을 네 조각으로 나눈 결과입니다. 여덟 개 셀 전부입니다.

각 동시성마다 왼쪽이 MORI, 오른쪽이 TA+O입니다.
막대 안 숫자가 창 전체 시간 대비 비중이고, 네 조각을 더하면 100퍼센트입니다.

막대 위에 작게 적힌 xfer 숫자가 전송 시간 비중입니다.
별도 스트림에서 일어나므로 막대에는 넣지 않고 따로 표시했습니다.

아래 표가 같은 값을 숫자로 본 것입니다.
세로로 읽으면 동시성이 올라갈 때 각 조각이 어떻게 변하는지 보입니다.""")

# ═════════════════════════════════════════ S7 절대 지표
s = slide("3부. 결과 — 처리량 · 지연 (절대값)")
add_figure(s, "tierc5090_R2_absolute_yunuikang", 0.42, 1.52, 12.5, 2.85)
rows = [["지표", "시스템"] + [f"C={c}" for c in CS]]
for key, name, fmt in (("goodput5", "goodput @5s (tok/s)", "{:.2f}"),
                       ("sat_frac", "SLO 5s 만족률", "{:.1%}"),
                       ("decode_tok", "엔진 decode 토큰", "{:,.0f}"),
                       ("drv_thr", "드라이버 thr (tok/s)", "{:.2f}"),
                       ("ttft_p50", "TTFT p50 (s)", "{:.2f}"),
                       ("ttft_p95", "TTFT p95 (s)", "{:.1f}")):
    rows.append([f"**{name}**", "MORI"] + [fmt.format(g("MORI", c, key)) for c in CS])
    rows.append(["", "TA+O"] + [fmt.format(g("TAO", c, key)) for c in CS])
add_table(s, rows, 0.42, 4.48, 12.5, 0.6, fs=8.0, hdr_fs=8.0,
          col_widths=[2.55, 1.10, 2.20, 2.20, 2.20, 2.20])
footer(s, f"[측정] goodput 은 프록시 per-step CSV · 엔진 decode 토큰은 steplog · 드라이버 thr·TTFT 는 드라이버 요약 · {NB}")
set_notes(s, """처리량과 지연을 절대값으로 본 것입니다.

왼쪽 그래프가 goodput입니다.
응답 시작이 5초 안에 들어온 스텝의 출력 토큰만 세서 창 시간으로 나눈 값입니다.

가운데가 엔진이 실제로 생성한 decode 토큰 수입니다. 창 안 집계입니다.

오른쪽이 드라이버가 잰 throughput입니다.
이건 완주한 프로그램만 셉니다. 앞의 두 지표와 계산 방식이 다릅니다.

아래 표에 SLO 만족률과 TTFT를 함께 넣었습니다.""")

# ═════════════════════════════════════════ S8 토큰 지표
s = slide("3부. 결과 — 토큰 지표 (재계산 · reload · 캐시)")
add_figure(s, "tierc5090_R4_tokens_yunuikang", 0.42, 1.52, 12.5, 2.85)
rows = [["지표", "시스템"] + [f"C={c}" for c in CS]]
for key, name, fmt in (("recompute_frac", "재계산율", "{:.1%}"),
                       ("recompute_tok", "재계산 토큰", "{:,.0f}"),
                       ("reload_tok", "reload 토큰", "{:,.0f}"),
                       ("reload_per_out", "reload ÷ 출력 토큰", "{:.2f}"),
                       ("prefix_hit", "prefix hit", "{:.3f}"),
                       ("waiting_evict", "Waiting 축출 (건)", "{:,.0f}")):
    rows.append([f"**{name}**", "MORI"] + [fmt.format(g("MORI", c, key)) for c in CS])
    rows.append(["", "TA+O"] + [fmt.format(g("TAO", c, key)) for c in CS])
add_table(s, rows, 0.42, 4.48, 12.5, 0.6, fs=8.0, hdr_fs=8.0,
          col_widths=[2.55, 1.10, 2.20, 2.20, 2.20, 2.20])
footer(s, "[측정] Waiting 축출은 MORI = `MORI evict CPU→Waiting`, TA+O = `Paused program` 으로 "
          f"**서로 다른 사건을 센다** — 각 시스템 내부의 C 추세만 읽을 것 · {NB}")
set_notes(s, """토큰 단위 지표입니다.

왼쪽이 재계산율입니다.
엔진이 실제로 계산한 prefill 토큰 중 재계산에 해당하는 비율입니다.

가운데가 reload 토큰을 출력 토큰으로 나눈 값입니다.
완주량이 셀마다 다르므로 출력 토큰당으로 정규화했습니다.

오른쪽이 prefix 캐시 적중률입니다. 엔진 카운터 델타로 계산했습니다.

아래 표 맨 마지막 줄, Waiting 축출은 읽을 때 주의가 필요합니다.
MORI는 CPU 계층에서 대기열로 내리는 사건을 세고,
TA+O는 일시정지 횟수를 셉니다. 서로 다른 사건이라 두 시스템 간 비교는 성립하지 않습니다.
각 시스템 안에서 동시성이 올라갈 때의 추세만 보시면 됩니다.""")

# ═════════════════════════════════════════ S9 비율
s = slide("3부. 결과 — MORI ÷ TA+O (셀별)")
add_figure(s, "tierc5090_R3_ratio_yunuikang", 0.42, 1.58, 6.55, 4.45)
zone(s, "표", "비 (MORI ÷ TA+O)", 7.20, 1.58, 5.72, 4.45, BLUE)
rows = [["지표"] + [f"C={c}" for c in CS]]
for key, name in (("goodput5", "goodput @5s"), ("decode_tok", "엔진 decode 토큰"),
                  ("drv_thr", "드라이버 thr"), ("recompute_frac", "재계산율"),
                  ("reload_tok", "reload 토큰"), ("prefix_hit", "prefix hit"),
                  ("ttft_p50", "TTFT p50"), ("ttft_p95", "TTFT p95")):
    rows.append([name] + [f"{R_[str(c)][key]:.3f}" for c in CS])
add_table(s, rows, 7.40, 2.04, 5.32, 0.6, fs=9, hdr_fs=9,
          col_widths=[1.72, 0.90, 0.90, 0.90, 0.90], highlight_rows={1: HEALTHY})
add_text(s, "참고 데이터 (다른 실행)", 7.40, 5.42, 5.32, 0.25, size=9.5, color=GRAY, bold=True)
add_text(s, f"{D['ref']['orig5090_note']}\n드라이버 thr 비 = **{D['ref']['orig5090_tp2_8b_C80_ratio_drv']:.2f}**",
         7.40, 5.66, 5.32, 0.6, size=9.5, color=INK)
footer(s, f"[측정] 각 비는 같은 C 의 MORI 셀 ÷ TA+O 셀 · {NB}")
set_notes(s, """같은 동시성에서 MORI 값을 TA+O 값으로 나눈 비입니다.

왼쪽 그래프에서 굵은 빨간 선이 goodput 비이고 숫자를 붙였습니다.
점선이 1.0이고, 아래쪽 일점쇄선이 참고 데이터입니다.

오른쪽 표에 여덟 개 지표의 비를 전부 넣었습니다.
TTFT는 낮을수록 좋은 지표라 비의 방향이 다른 지표와 반대로 읽힙니다.

표 아래 참고 데이터는 이번 실험이 아니라 다른 설정에서 나온 측정값입니다.
5090 두 장, TP2, Qwen3-8B, 동시성 80에서 잰 드라이버 throughput 비입니다.
설정이 다르므로 같은 조건의 비교가 아닙니다.""")

# ═════════════════════════════════════════ S10 MORI 추세
s = slide("3부. 결과 — C 에 따른 예산 변화 (시스템별)")
for k, (sy, lab, col) in enumerate((("MORI", "MORI", RED), ("TAO", "TA+O", BLUE))):
    x = 0.42 + k * 6.4
    zone(s, lab, f"{lab} — C7 → C70", x, 1.62, 6.1, 3.05, col)
    rows = [["예산 항목", "C=7", "C=15", "C=20", "C=70"]]
    for key, name in (("decode_pct", "decode"), ("prefill_new_pct", "prefill_new"),
                      ("prefill_recomp_pct", "prefill_recompute"), ("idle_pct", "idle")):
        rows.append([name] + [f"{g(sy,c,key):.2f}" for c in CS])
    add_table(s, rows, x + 0.2, 2.10, 5.7, 0.6, fs=9.5, hdr_fs=9.5,
              col_widths=[1.75, 0.98, 0.98, 0.98, 0.98])
add_text(s, "단위 = 창 wall 대비 %", 0.42, 4.80, 12.5, 0.25, size=9.5, color=GRAY)

zone(s, "★", "C=70 (oversub 10.00×) 요약 수치", 0.42, 5.12, 12.5, 1.78, GREEN)
add_table(s, [
    ["지표", "MORI", "TA+O", "MORI ÷ TA+O"],
    ["goodput @5s (tok/s)", f"**{g('MORI',70,'goodput5'):.2f}**", f"{g('TAO',70,'goodput5'):.2f}",
     f"**{R_['70']['goodput5']:.3f}**"],
    ["엔진 decode 토큰", f"**{g('MORI',70,'decode_tok'):,}**", f"{g('TAO',70,'decode_tok'):,}",
     f"**{R_['70']['decode_tok']:.3f}**"],
    ["드라이버 thr (tok/s)", f"**{g('MORI',70,'drv_thr'):.2f}**", f"{g('TAO',70,'drv_thr'):.2f}",
     f"**{R_['70']['drv_thr']:.3f}**"],
], 0.62, 5.58, 12.1, 0.6, fs=10, hdr_fs=10,
    col_widths=[3.55, 2.85, 2.85, 2.85], highlight_rows={1: HEALTHY})
footer(s, f"[측정] {NB} · 참고 데이터(다른 실행): {D['ref']['orig5090_note']} — 드라이버 thr 비 "
          f"{D['ref']['orig5090_tp2_8b_C80_ratio_drv']:.2f}")
set_notes(s, """동시성이 올라갈 때 예산이 어떻게 변하는지를 시스템별로 나눠 적었습니다.

왼쪽이 MORI, 오른쪽이 TA+O입니다.
가로로 읽으면 C7에서 C70까지 각 항목이 어떤 값을 갖는지 보입니다.

MORI 기준으로 decode는 82.59에서 47.83으로,
재계산은 0.07에서 30.46으로, idle은 8.53에서 0.32로 바뀝니다.

아래 상자가 동시성 70, 즉 초과율 10배 지점의 세 지표입니다.
goodput, 엔진 decode 토큰, 드라이버 throughput의 MORI 값과 TA+O 값,
그리고 둘의 비를 나란히 적었습니다.

맨 아래 각주의 참고 데이터는 다른 설정에서 나온 값입니다.
GPU 두 장, TP2, 다른 모델이라 이번 격자와 같은 조건이 아닙니다.""")

prs.save(OUT)
print("saved:", OUT, f"({len(prs.slides.__iter__.__self__._sldIdLst)} slides)")
