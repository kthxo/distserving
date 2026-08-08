#!/usr/bin/env python3
"""H200 결과 — 데이터 전용 덱 (조건 · 표 · 경향).

시행착오·서사·판정 논쟁을 뺀다. 담는 것은 세 가지뿐:
  ① 어떤 조건으로 돌렸나 (하드웨어 · 엔진 설정 · 토큰 제한 · 트레이스 · 드라이버)
  ② 결과 수치 (정확한 값, 전 셀 전 지표)
  ③ 경향 (그래프)

수치는 ~/yunuikang_work/h200_scratch/mori/ 원시 JSONL/CSV 에서만 읽는다.
스타일: docs/DECK_STYLE_yunuikang.md
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decklib_yunuikang import (  # noqa: E402
    new_deck, _blank, add_title, add_takeaway, add_text, add_figure,
    add_caption, add_table, set_notes, band, chip,
    INK, BLUE, RED, GREEN, GRAY, LT, AMBER, WHITE,
)
from plot_h200_lib_yunuikang import phase1, phase2, engine_delta, gpu_util  # noqa: E402
from pptx.util import Inches, Pt  # noqa: E402
from pptx.dml.color import RGBColor  # noqa: E402
from pptx.enum.shapes import MSO_SHAPE  # noqa: E402

OUT = "/home/yunuikang/yunuikang_work/distserving/slides/2026-08-08_MORI-H200-data_yunuikang.pptx"
PURPLE = RGBColor(0x6E, 0x4B, 0x9E)
HEALTHY = RGBColor(0xE7, 0xF3, 0xEC)
EXTREME = RGBColor(0xFB, 0xE9, 0xE7)
PANEL = RGBColor(0xF4, 0xF6, 0xFA)

P1_7B, P1_8B, P2 = phase1("h200_phase1"), phase1("h200_phase1_8b"), phase2()
CS = [20, 40, 80]
SYS = ["SMG", "TA", "TAO", "MORI"]
LBL = {"SMG": "SMG", "TA": "TA", "TAO": "TA+O", "MORI": "MORI"}

E = {(s, c): engine_delta(f"{s}_C{c}") for s in SYS for c in CS}
U = {(s, c): gpu_util(f"{s}_C{c}") for s in SYS for c in CS}
g = lambda s, c: P2[(s, c)]["goodput_5s"]

prs = new_deck()


def slide(title, takeaway=None, tw_color=BLUE):
    s = _blank(prs)
    band(s, 0.0, 0.11, INK)
    add_title(s, title)
    if takeaway:
        add_takeaway(s, takeaway, color=tw_color)
    return s


def zone(s, n, label, x, y, w, h, color):
    p = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    p.fill.solid(); p.fill.fore_color.rgb = PANEL
    p.line.color.rgb = RGBColor(0xDD, 0xE1, 0xE8); p.line.width = Pt(0.75)
    p.shadow.inherit = False
    chip(s, f"{n}  {label}", x + 0.12, y + 0.10, min(w - 0.24, 5.2), color, size=10.5, h=0.30)
    return p


def footer(s, txt):
    add_text(s, txt, 0.42, 7.06, 12.5, 0.3, size=8.5, color=GRAY)


# ═══════════════════════════════════════════════ S1 표지
s = slide("")
band(s, 0.0, 7.5, INK)
add_text(s, "MORI on H200 — 실험 조건과 결과", 0.9, 2.20, 11.5, 0.8, size=40, color=WHITE, bold=True)
add_text(s, "데이터 시트 · 조건 / 수치 / 경향", 0.92, 3.25, 11.5, 0.5, size=19,
         color=RGBColor(0x9F, 0xB6, 0xD8))
band(s, 4.02, 0.035, RGBColor(0x2E, 0x5E, 0xAA), x=0.92, w=3.2)
add_text(s, "H200 SXM ×1 · TP1 · SGLang 0.5.10 + HiCache · Track M 트레이스\n"
            "총 16셀 · GPU 16.1시간 · 2026-08-05 ~ 08-06 (UTC)",
         0.92, 4.35, 11.5, 0.8, size=13.5, color=RGBColor(0x9F, 0xB6, 0xD8))
add_text(s, "2026-08-08 · yunuikang", 0.92, 6.4, 11.5, 0.4, size=12, color=RGBColor(0x7B, 0x8C, 0xA8))
set_notes(s, """H200에서 돌린 실험의 조건과 결과만 정리한 자료입니다.
과정이나 해석은 빼고, 어떤 설정으로 돌렸을 때 숫자가 어떻게 나왔는지만 담았습니다.
총 16개 셀을 GPU 시간 16시간에 걸쳐 돌렸습니다.""")

# ═══════════════════════════════════════════════ S2 하드웨어 · 소프트웨어
s = slide("실험 환경 — 하드웨어 · 소프트웨어",
          "H200 SXM 1장 · TP1 · 단일 노드 — 5090 ×2 TP2 대비 all-reduce 와 cross-NUMA 가 없다")
add_table(s, [
    ["구분", "항목", "값"],
    ["**하드웨어**", "GPU", "**NVIDIA H200 SXM ×1** (141 GB HBM3e, sm_90)"],
    ["", "병렬화", "**TP1** — all-reduce 없음"],
    ["", "NUMA", "`numactl --cpunodebind=0` (membind 는 컨테이너 제약으로 미적용)"],
    ["**엔진**", "서버", "SGLang **0.5.10** + HiCache (계층형 캐시)"],
    ["", "attention / sampling", "`triton` / `pytorch`"],
    ["", "`--mem-fraction-static`", "**0.90**"],
    ["", "`--page-size`", "**1** → `pool == max-total-tokens` 정확히 일치"],
    ["**모델**", "Phase 2 · Phase 1(7B)", "**Qwen2.5-7B-Instruct** — 28층 · kv 4 · head 128 → **56 KiB/tok**"],
    ["", "Phase 1(8B)", "**Qwen3-8B** — 36층 · kv 8 · head 128 → **144 KiB/tok**"],
    ["", "가중치 (bf16)", "14.19 GiB (7B) / 15.26 GiB (8B)"],
    ["**컨텍스트**", "`--context-length`", "**71,680** tok"],
    ["", "YaRN factor", "**2.1875** × 32,768 (7B) · **1.75** × 40,960 (8B)"],
], 0.42, 1.66, 12.5, 0.6, fs=10, hdr_fs=10,
    col_widths=[1.45, 3.15, 7.90])
footer(s, "5090 대조 환경: RTX 5090 ×2 · TP2 · NVLink 없음(SYS) · cross-NUMA · Qwen3-8B · 동일 트레이스·드라이버   [측정]")
set_notes(s, """실험 환경입니다.

GPU는 H200 한 장을 썼고 텐서 병렬 없이 TP1으로 돌렸습니다.
5090 두 장으로 돌리던 기존 환경과 비교하면 GPU 사이 통신이 아예 없어집니다.

엔진은 SGLang 0.5.10에 계층형 캐시 기능을 켰습니다.
페이지 크기를 1로 둬서 우리가 지정한 토큰 수가 그대로 풀 크기가 되게 했습니다.

모델은 두 가지입니다. 주로 쓴 건 Qwen2.5-7B이고, 토큰당 KV가 56킬로바이트입니다.
비교용으로 Qwen3-8B도 썼는데 이건 토큰당 144킬로바이트로 두 배 반 무겁습니다.

컨텍스트 길이는 71,680 토큰으로 맞췄습니다.
모델마다 원래 길이가 달라서 YaRN 배율을 따로 줬습니다.""")

# ═══════════════════════════════════════════════ S3 워크로드 · 드라이버
s = slide("실험 환경 — 워크로드 · 측정 방법",
          "트레이스·드라이버·측정 규약은 전 셀 동일 — 바꾼 것은 **토큰 제한 · 동시성 · 시스템** 뿐이다")
zone(s, "①", "트레이스 (Track M — 재가공 없음)", 0.42, 1.62, 6.15, 2.6, PURPLE)
add_table(s, [
    ["특성", "값"],
    ["규모", "**3,514 세션 / 117,257 턴**"],
    ["long-time-share", "**98.9%** (긴 툴콜이 시간을 지배)"],
    ["세션당 phase 전이 median", "**4.0**"],
    ["동시점 ι-IQR", "**0.694** (이질성 충족)"],
    ["컨텍스트 median / peak", "**32,376 / 65,536** tok"],
    ["p999 input+output", "67,928 tok"],
], 0.62, 2.10, 5.75, 0.6, fs=9.5, hdr_fs=9.5, col_widths=[3.05, 2.60])

zone(s, "②", "드라이버 · 셀 규약", 6.78, 1.62, 6.14, 2.6, AMBER)
add_table(s, [
    ["항목", "값"],
    ["셀 길이", "**3,600 s** (Phase 1 7B 만 1,800 s)"],
    ["warmup / grace", "**0.2** / 60 s"],
    ["`--ctx-cap`", "69,632 tok"],
    ["부하 형태", "closed-loop · C 워커 순환셔플"],
    ["셀마다 백엔드 재기동", "**한다** (Phase 2)"],
    ["반복", "**없음 (n=1)** · run 변동 ~15%"],
], 6.98, 2.10, 5.74, 0.6, fs=9.5, hdr_fs=9.5, col_widths=[2.55, 3.10],
    highlight_rows={6: EXTREME})

zone(s, "③", "측정 지표 정의", 0.42, 4.38, 12.5, 2.5, GREEN)
add_table(s, [
    ["지표", "정의", "출처"],
    ["**goodput @SLO**", "`Σ completion_tokens (TTFT ≤ SLO 인 스텝) ÷ steady_wall`  ·  TTFT = `pause_s + prefill_s`",
     "프록시 `--profile` per-step CSV"],
    ["엔진 throughput", "`generation_tokens_total` 델타 ÷ 고정 steady 창", "`/metrics` 5초 폴링"],
    ["드라이버 throughput", "완주 프로그램의 출력 토큰 ÷ steady_wall", "드라이버 요약"],
    ["TTFT p50 / p95", "드라이버 스트리밍 측정", "드라이버 요약"],
    ["prefix hit", "`cached_tokens` 델타 ÷ `prompt_tokens` 델타", "`/metrics`"],
    ["GPU util", "`nvidia-smi` 1 Hz, steady 창 평균", "gpu jsonl"],
], 0.62, 4.86, 12.1, 0.6, fs=9.5, hdr_fs=9.5,
    col_widths=[2.15, 7.20, 2.75], highlight_rows={1: HEALTHY})
add_text(s, "고정 steady 창 = `[t_start + 0.2 × DUR,  t_start + DUR]`  — 전 지표 공통",
         0.62, 6.52, 12.1, 0.3, size=10, color=INK, bold=True)
footer(s, "트레이스 통계 [측정] logs/2026-07-30_M4_PARAMS_yunuikang.md:76-79, 92 · 드라이버 `scripts/mori_replay_driver_yunuikang.py`")
set_notes(s, """워크로드와 측정 방법입니다.

왼쪽이 트레이스입니다. 실제 에이전트 세션 3,514개, 턴으로는 11만 7천 개입니다.
중요한 특성은 긴 툴 호출이 전체 시간의 98.9퍼센트를 차지한다는 점입니다.
컨텍스트 길이 중앙값이 32,376 토큰인데, 이 값이 나중에 fit 계산의 분모가 됩니다.

오른쪽이 셀 규약입니다. 한 셀당 한 시간씩 돌렸습니다.
앞 20퍼센트는 워밍업으로 버리고 나머지만 집계합니다.
그리고 셀마다 백엔드를 껐다 켜서 앞 시스템의 캐시가 뒤로 넘어가지 않게 했습니다.
반복은 없습니다. 셀마다 한 번씩만 돌렸고, 실행마다 15퍼센트 정도 변동이 있습니다.

아래가 지표 정의입니다. 제일 중요한 게 첫 줄 goodput입니다.
단순 처리량이 아니라, 응답 시작이 SLO 안에 들어온 스텝의 출력 토큰만 셉니다.
즉 "제때 도착한 유용한 산출"입니다.""")

# ═══════════════════════════════════════════════ S4 실험 격자
s = slide("실험 격자 — 무엇을 바꿨나",
          "**토큰 제한(`--max-total-tokens`)** 으로 fit 을, **동시성 C** 로 압박을 조절한다")
add_text(s, "fit = GPU KV 풀 토큰 ÷ 컨텍스트 median(32,376)      ·      oversub = C ÷ fit      ·      "
            "host tier = r × GPU 풀  (r = `--hicache-ratio`)",
         0.42, 1.64, 12.5, 0.35, size=11.5, bold=True, color=INK)

zone(s, "A", "Phase 1 — 토큰 제한 스윕 (fit 축)", 0.42, 2.10, 6.15, 2.35, RED)
add_table(s, [
    ["모델", "`--max-total-tokens`", "fit", "oversub", "C · r", "셀"],
    ["Qwen2.5-7B", "**262,246**", "**8.10**", "**9.88×**", "80 · 2", "2"],
    ["Qwen3-8B", "**262,246**", "**8.10**", "**9.88×**", "80 · 2", "2"],
], 0.62, 2.58, 5.75, 0.6, fs=9, hdr_fs=9,
    col_widths=[1.20, 1.55, 0.60, 0.80, 0.85, 0.45])
add_text(s, "계획된 F2·F3·F4 (388,512 / 518,016 / 647,520)는 **실행하지 않았다** — "
            "사전 등록된 중단 규칙 적용.",
         0.62, 3.62, 5.75, 0.6, size=9.5, color=GRAY)

zone(s, "B", "Phase 2 — 동시성 스윕 (C 축)", 6.78, 2.10, 6.14, 2.35, BLUE)
add_table(s, [
    ["모델 / 토큰 제한", "C", "oversub", "시스템", "셀"],
    ["Qwen2.5-7B\n**647,520** (fit **20.00**) · r=2", "**20**", "1.00×", "SMG · TA\nTA+O · MORI", "4"],
    ["", "**40**", "2.00×", "〃", "4"],
    ["", "**80**", "4.00×", "〃", "4"],
], 6.98, 2.58, 5.74, 0.6, fs=9, hdr_fs=9,
    col_widths=[2.35, 0.62, 0.90, 1.35, 0.45])

zone(s, "C", "시스템 4종 설정 — 무엇이 켜져 있나", 0.42, 4.62, 12.5, 2.3, GREEN)
add_table(s, [
    ["시스템", "router", "`--hicache-ratio` (r)", "`--radix-eviction-policy`", "무엇을 더한 것인가"],
    ["**SMG**", "`default`", "0 (HiCache off)", "lru", "기본 — admission control 없음"],
    ["**TA**", "`tr`", "0 (HiCache off)", "lru", "+ 스케줄러 (admission control)"],
    ["**TA+O**", "`tr`", "**2**", "lru", "+ CPU 오프로딩 (HiCache)"],
    ["**MORI**", "`mori`", "**2**", "**mori**", "+ MORI 정책 (typed eviction · 3-tier · ι 랭킹)"],
], 0.62, 5.10, 12.1, 0.6, fs=9.5, hdr_fs=9.5,
    col_widths=[1.15, 1.05, 2.05, 2.55, 5.30], highlight_rows={4: HEALTHY})
footer(s, "Phase 2 host tier = 2 × 647,520 = **1,295,041** tok · Phase 1 host tier = 2 × 262,246 = **524,493** tok · "
          "게이트에서 셀마다 실측 확인 (오차 0.000%)   [측정]")
set_notes(s, """실험에서 바꾼 변수입니다.

맨 위 공식 세 개를 먼저 봐 주십시오.
fit은 GPU 메모리 풀에 컨텍스트가 몇 개나 들어가는지입니다.
동시성을 fit으로 나눈 게 oversub, 즉 얼마나 초과된 상태인지입니다.
그리고 r은 CPU 쪽 계층을 GPU 풀의 몇 배로 잡을지입니다.

왼쪽 A가 첫 번째 실험입니다. 토큰 제한을 26만으로 걸어서 fit을 8.1로 만들었습니다.
이건 5090과 똑같은 조건입니다. 계획상 여기서 토큰 제한을 올려가며 네 점을 볼 예정이었는데
첫 점에서 미리 정해 둔 중단 규칙에 걸려서 나머지는 안 돌렸습니다.

오른쪽 B가 두 번째 실험입니다. 토큰 제한을 64만 7천으로 고정해서 fit을 20으로 만들고
동시성만 20, 40, 80으로 올렸습니다. 각 동시성마다 시스템 네 개씩, 총 12셀입니다.

아래 C가 시스템 네 종류의 차이입니다. 위에서 아래로 갈수록 기능이 하나씩 더해집니다.
SMG는 아무것도 없고, TA는 스케줄러가 붙고, TA+O는 CPU 오프로딩이 붙고,
MORI는 거기에 정책이 붙습니다. 이렇게 층을 나눠야 뭐가 얼마나 기여했는지 볼 수 있습니다.""")

# ═══════════════════════════════════════════════ S5 Phase 2 결과 표 (핵심)
s = slide("결과 표 ① — Phase 2 (동시성 스윕, 12셀)",
          "Qwen2.5-7B · fit 20.00 · r=2 · 60분 · 12/12 완료 (SKIP · CRASH · 실패 프로그램 **0**)")
rows = [["시스템", "C", "**goodput\n@5s**", "goodput\n@2s", "드라이버\nthr", "엔진\nthr",
         "TTFT\np50", "TTFT\np95", "ping\n%", "prefix\nhit", "GPU\nutil%", "Waiting\n축출", "steady\n턴", "load_back\n(M tok)"]]
hl = {}
for i, C in enumerate(CS):
    for j, sy in enumerate(SYS):
        r, e, u = P2[(sy, C)], E[(sy, C)], U[(sy, C)]
        rows.append([f"**{LBL[sy]}**", str(C), f"**{r['goodput_5s']:.2f}**", f"{r['goodput_2s']:.2f}",
                     f"{r['driver_thr_tok_s']:.2f}", f"{r['engine_thr_tok_s']:.2f}",
                     f"{r['ttft_p50_s']:.3f}", f"{r['ttft_p95_s']:.2f}", f"{r['pingpong_pct']:.1f}",
                     f"{e['hit']:.3f}", f"{u:.1f}", str(r['waiting_evict']),
                     str(r['steady_turns']), f"{e['load_back']/1e6:.2f}"])
        n = len(rows) - 1
        if sy == "MORI":
            hl[n] = HEALTHY
        elif sy == "SMG" and C > 20:
            hl[n] = EXTREME
add_table(s, rows, 0.42, 1.62, 12.5, 0.6, fs=9.6, hdr_fs=9.4,
          col_widths=[0.88, 0.46, 1.06, 0.90, 0.96, 0.86, 0.78, 0.78, 0.70, 0.80, 0.76, 0.90, 0.84, 1.12],
          highlight_rows=hl)
add_text(s, "MORI ÷ TA+O (goodput @5s):   "
            f"C=20 **{g('MORI',20)/g('TAO',20):.3f}**   ·   C=40 **{g('MORI',40)/g('TAO',40):.3f}**   ·   "
            f"C=80 **{g('MORI',80)/g('TAO',80):.3f}**      "
            "→ 압박이 커질수록 격차 확대",
         0.42, 6.10, 12.5, 0.35, size=12.5, bold=True, color=INK)
add_text(s, "GPU util 은 goodput 0.00 인 SMG C80 을 포함해 전 셀 97~100% — 사용률만으로는 유용한 일의 양을 가릴 수 없다.",
         0.42, 6.56, 12.5, 0.35, size=10.5, color=GRAY)
footer(s, "Waiting 축출은 **시스템 간 비교 불가** — MORI 는 `CPU→Waiting`, 나머지는 `Paused program` 으로 사건이 다르다. "
          "각 시스템 내부의 C 추세만 읽을 것. n=1 · run 변동 ~15%   [측정]")
set_notes(s, """Phase 2 결과 전체입니다. 12개 셀의 모든 지표를 한 표에 담았습니다.

초록색 줄이 MORI, 분홍색 줄이 SMG가 무너진 셀입니다.

세로로 goodput 열을 따라가 보시면,
MORI는 167, 185, 210으로 계속 올라가고
TA+O는 156, 176, 184로 올라가되 MORI보다 완만합니다.
TA는 157에서 159로 거의 평평하고,
SMG는 158에서 0.21, 0으로 떨어집니다.

맨 아래 줄이 MORI와 TA+O의 비율입니다.
동시성 20에서 1.074, 40에서 1.051, 80에서 1.142입니다.
동시성이 높을수록 격차가 커집니다.

몇 가지 눈여겨볼 열이 있습니다.
GPU 사용률 열을 보시면 전부 97에서 100퍼센트입니다.
goodput이 0인 SMG도 GPU는 100퍼센트로 돌고 있습니다.
즉 GPU 사용률만 보면 아무것도 판단할 수 없습니다.

prefix hit 열도 흥미롭습니다. MORI가 0.827로 제일 낮은데 goodput은 1등입니다.

맨 아래 각주 하나만 주의해 주십시오.
Waiting 축출 숫자는 시스템끼리 비교하면 안 됩니다.
MORI는 CPU에서 대기열로 내리는 사건을 센 거고
나머지는 그냥 일시정지 횟수를 센 거라 서로 다른 사건입니다.""")

# ═══════════════════════════════════════════════ S6 Phase 1 결과 표
s = slide("결과 표 ② — Phase 1 (토큰 제한 26만 = fit 8.10, 4셀)",
          "5090 과 동일한 oversub 9.88× · r=2 조건. 두 모델 모두 **MORI 가 앞선다**")
rows = [["모델 / 셀길이", "지표", "TA+O", "MORI", "MORI ÷ TA+O"]]
for lab, p, dur in (("Qwen2.5-7B\n30분", P1_7B, 1800), ("Qwen3-8B\n60분", P1_8B, 3600)):
    e_t, e_m = engine_delta(f"TAO_F1", "h200_phase1" if "7B" in lab else "h200_phase1_8b"), \
               engine_delta(f"MORI_F1", "h200_phase1" if "7B" in lab else "h200_phase1_8b")
    sub = "h200_phase1" if "7B" in lab else "h200_phase1_8b"
    u_t, u_m = gpu_util("TAO_F1", sub), gpu_util("MORI_F1", sub)
    rows += [
        [f"**{lab}**", "드라이버 thr (tok/s)", f"{p['TAO']['driver_thr_tok_s']:.2f}",
         f"**{p['MORI']['driver_thr_tok_s']:.2f}**", f"**{p['MORI']['ratio_driver_mori_over_tao']:.3f}**"],
        ["", "엔진 thr (tok/s)", f"{p['TAO']['engine_thr_tok_s']:.2f}",
         f"**{p['MORI']['engine_thr_tok_s']:.2f}**", f"**{p['MORI']['ratio_engine_mori_over_tao']:.3f}**"],
        ["", "TTFT p50 (s)", f"**{p['TAO']['ttft_p50_s']:.2f}**", f"{p['MORI']['ttft_p50_s']:.2f}",
         f"{p['MORI']['ttft_p50_s']/p['TAO']['ttft_p50_s']:.2f}"],
        ["", "TTFT p95 (s)", f"**{p['TAO']['ttft_p95_s']:.2f}**", f"{p['MORI']['ttft_p95_s']:.2f}",
         f"{p['MORI']['ttft_p95_s']/p['TAO']['ttft_p95_s']:.2f}"],
        ["", "ping-pong % / prefix hit", f"{p['TAO']['pingpong_pct']:.1f} / {e_t['hit']:.3f}",
         f"{p['MORI']['pingpong_pct']:.1f} / {e_m['hit']:.3f}", "—"],
        ["", "GPU util % / steady 턴", f"{u_t:.1f} / {p['TAO']['steady_turns']}",
         f"{u_m:.1f} / {p['MORI']['steady_turns']}", "—"],
    ]
add_table(s, rows, 0.42, 1.66, 12.5, 0.6, fs=9.5, hdr_fs=9.5,
          col_widths=[1.75, 3.35, 2.45, 2.45, 2.10],
          highlight_rows={1: HEALTHY, 2: HEALTHY, 7: HEALTHY, 8: HEALTHY})
add_text(s, "참고 — 동일 조건 5090 대조군 [측정]:   TA+O 드라이버 **14.28** · MORI 드라이버 **6.47** tok/s   →   "
            "MORI ÷ TA+O = **0.450**",
         0.42, 6.42, 12.5, 0.35, size=11.5, bold=True, color=INK)
footer(s, "Phase 1 은 드라이버가 per-turn 을 저장하지 않아 **goodput 점추정이 불가**했다 — Phase 2 표와 **계측기가 달라 직접 비교하지 않는다**. "
          "n=1 · run 변동 ~15%   [측정]")
set_notes(s, """Phase 1 결과입니다. 토큰 제한을 26만으로 걸어서 fit을 8.1로 만든 조건입니다.

이 조건이 왜 중요하냐면, 5090에서 돌렸을 때와 초과율이 9.88배로 똑같기 때문입니다.

표를 보시면 두 모델 모두 MORI가 처리량에서 앞섭니다.
7B는 드라이버 기준 1.405배, 8B는 1.080배입니다.
엔진 기준으로는 각각 1.145배, 1.458배입니다.

반대로 응답 시간은 두 모델 모두 MORI가 뒤집니다.
7B에서 p50이 0.59초 대 0.67초, 8B에서 0.78초 대 1.50초입니다.
꼬리 지연은 차이가 더 큽니다.

아래 참고 줄을 봐 주십시오.
같은 조건을 5090에서 돌렸을 때는 MORI가 베이스라인의 0.45배였습니다.
지금은 1.0을 넘습니다. 하드웨어가 바뀌면서 관계가 뒤집혔습니다.

맨 아래 각주 하나만 주의하겠습니다.
Phase 1에서는 goodput을 점으로 못 냈습니다. 드라이버가 턴별 기록을 남기지 않아서입니다.
그래서 Phase 2 표의 goodput 숫자와 직접 비교하면 안 됩니다.""")

# ═══════════════════════════════════════════════ S7 경향 ① C 곡선
s = slide("경향 ① — 동시성에 따른 goodput",
          "MORI 가 모든 C 에서 1등 · 압박이 커질수록 격차가 벌어진다 (+7.4% → +5.1% → **+14.2%**)")
add_figure(s, "mori_h200_f4_curve_yunuikang", 0.42, 1.66, 12.5, 4.15)
add_caption(s, "좌: 4종 전체 (SMG 절벽 때문에 로그축)   ·   우: 3종 확대 (선형축)   — 단위가 다르지 않으므로 이중축 대신 패널을 나눴다",
            0.42, 5.94, 12.5, size=10)
footer(s, "goodput @SLO 5s · Qwen2.5-7B · fit 20.00 · r=2 · 60분 · n=1 · run 변동 ~15%   [측정]")
set_notes(s, """앞 표의 goodput 열을 그림으로 본 겁니다.

왼쪽은 네 시스템 전부입니다. SMG가 너무 크게 떨어져서
보통 축으로 그리면 나머지 셋이 한 줄로 뭉갭니다. 그래서 로그 축을 썼습니다.

오른쪽은 그 세 시스템만 확대한 겁니다.
빨간 MORI가 세 지점 모두 제일 위에 있고,
파란 TA+O와의 간격이 오른쪽으로 갈수록 벌어집니다.
7.4퍼센트에서 시작해 동시성 80에서 14.2퍼센트가 됩니다.

주황색 TA는 거의 평평합니다. 스케줄러만 있으면 동시성이 네 배가 돼도
성능이 유지된다는 뜻이고, 오프로딩과 MORI 정책의 이득은 이 평평한 선 위에 얹힙니다.""")

# ═══════════════════════════════════════════════ S8 경향 ② 비율 + 층위
s = slide("경향 ② — 우위 폭과 층위별 기여")
add_figure(s, "mori_h200_f5_ratio_yunuikang", 0.42, 1.60, 5.9, 3.6)
add_caption(s, "MORI ÷ TA+O — 압박이 커질수록 우위가 커진다", 0.42, 5.30, 5.9, size=10)
add_figure(s, "mori_h200_f7_layers_yunuikang", 6.55, 1.72, 6.37, 3.4)
add_caption(s, "층위별 기여 — 세 층 모두 압박에 비례해 값을 낸다", 6.55, 5.30, 6.37, size=10)
add_table(s, [
    ["층위", "무엇의 값인가", "C=20", "C=40", "C=80"],
    ["**스케줄러** (SMG→TA)", "admission control", "−0.4%", "**0.21 → 157.42**", "**0.00 → 158.90**"],
    ["**오프로딩** (TA→TA+O)", "HiCache", "−1.2%", "**+11.5%**", "**+15.7%**"],
    ["**MORI 정책** (TA+O→MORI)", "typed eviction · 3-tier", "**+7.4%**", "+5.1%", "**+14.2%**"],
], 0.42, 5.70, 12.5, 0.6, fs=9.5, hdr_fs=9.5,
    col_widths=[2.85, 3.15, 1.75, 2.40, 2.35], highlight_rows={3: HEALTHY})
footer(s, "스케줄러 층은 C40 에서 +74,867% 라 % 축에 표시할 수 없어 절대값으로 적었다. n=1 · run 변동 ~15%   [측정]")
set_notes(s, """왼쪽은 MORI와 TA+O의 비율만 뽑은 겁니다.
점선이 1.0, 즉 동률이고 초록 점선이 논문 기준 하한인 1.10입니다.
동시성 80에서 1.142로 그 선을 넘습니다.

오른쪽과 아래 표는 층위별로 누가 얼마나 기여했는지입니다.
동시성 20에서는 스케줄러와 오프로딩이 오히려 마이너스입니다.
압박이 없으니 관리 비용만 드는 겁니다.
동시성 40, 80으로 가면 전부 플러스로 바뀌고 계속 커집니다.

스케줄러 층은 퍼센트로 표시할 수가 없습니다.
동시성 40에서 0.21이 157로 뛰는데 퍼센트로 하면 7만 4천 퍼센트가 나옵니다.
그래서 절대값으로 적었습니다.""")

# ═══════════════════════════════════════════════ S9 경향 ③ TTFT + 캐시
s = slide("경향 ③ — 지연 시간과 캐시 적중률")
add_figure(s, "mori_h200_f6_ttft_yunuikang", 0.42, 1.60, 7.3, 3.9)
add_caption(s, "TTFT 비 — 네 조건 전부에서 MORI 가 느리다 (배율 1.14 ~ 4.09×)", 0.42, 5.58, 7.3, size=10)
add_figure(s, "mori_h200_f9_hit_yunuikang", 7.95, 1.72, 4.97, 3.7)
add_caption(s, "캐시 적중률이 낮은 MORI 가 goodput 은 1등", 7.95, 5.58, 4.97, size=10)
add_table(s, [
    ["조건", "TTFT p50 (MORI÷TA+O)", "TTFT p95", "goodput / thr 우열"],
    ["5090 C80 · 8B · TP2", "4.09×", "3.31×", "MORI 패 (0.450)"],
    ["H200 F1 · 7B · fit 8.1", "1.14×", "4.21×", "MORI 승 (drv 1.405)"],
    ["H200 F1 · 8B · fit 8.1", "1.93×", "1.48×", "MORI 승 (drv 1.080)"],
    ["H200 Phase 2 · C80 · fit 20", "**1.21×**", "1.44×", "**MORI 승 (goodput 1.142)**"],
], 0.42, 6.02, 12.5, 0.6, fs=9.5, hdr_fs=9.5,
    col_widths=[3.55, 3.15, 2.35, 3.45], highlight_rows={4: HEALTHY})
footer(s, "TTFT 는 낮을수록 좋다 — 네 조건 모두 1.0 초과. n=1 · run 변동 ~15%   [측정]")
set_notes(s, """왼쪽은 응답 시작 시간입니다. 낮을수록 좋은 지표입니다.

네 가지 조건을 나란히 놨습니다. 하드웨어도 다르고 모델도 다르고 설정도 다른데
여덟 개 막대가 전부 1.0 선 위에 있습니다.
즉 MORI는 어떤 조건에서든 응답 시작이 베이스라인보다 느립니다.
배율은 1.14배에서 4.09배 사이로 흔들리지만 방향은 한 번도 안 바뀌었습니다.

오른쪽은 캐시 적중률과 goodput의 관계입니다.
보통 캐시가 잘 맞으면 빠를 거라고 생각하는데 반대로 나왔습니다.
MORI가 적중률은 0.827로 제일 낮은데 goodput은 210으로 1등입니다.

아래 표가 두 그림을 합친 겁니다.
정리하면, MORI는 처리량을 얻는 대신 응답 시작 시간을 내주는 구조입니다.""")

# ═══════════════════════════════════════════════ S10 요약
s = slide("한 장 요약 — 조건과 결과",
          "fit 20 · r=2 · 60분 · n=1 기준 · goodput @SLO 5s")
zone(s, "조건", "핵심 설정", 0.42, 1.62, 6.15, 2.55, PURPLE)
add_table(s, [
    ["항목", "값"],
    ["GPU / 병렬화", "H200 SXM ×1 / **TP1**"],
    ["모델 / KV/tok", "Qwen2.5-7B / **56 KiB**"],
    ["`--max-total-tokens`", "**647,520** → fit **20.00**"],
    ["`--hicache-ratio` (r)", "**2** → host tier 1,295,041 tok"],
    ["`--context-length`", "71,680 (YaRN 2.1875)"],
    ["동시성 C", "**20 / 40 / 80** → oversub 1.00 / 2.00 / 4.00×"],
    ["셀 길이 · 반복", "3,600 s · **n=1**"],
], 0.62, 2.10, 5.75, 0.6, fs=9.5, hdr_fs=9.5, col_widths=[2.25, 3.40])

zone(s, "결과", "goodput @5s (tok/s)", 6.78, 1.62, 6.14, 2.55, GREEN)
add_table(s, [
    ["시스템", "C=20", "C=40", "C=80"],
    ["SMG", f"{g('SMG',20):.2f}", f"**{g('SMG',40):.2f}**", f"**{g('SMG',80):.2f}**"],
    ["TA", f"{g('TA',20):.2f}", f"{g('TA',40):.2f}", f"{g('TA',80):.2f}"],
    ["TA+O", f"{g('TAO',20):.2f}", f"{g('TAO',40):.2f}", f"{g('TAO',80):.2f}"],
    ["**MORI**", f"**{g('MORI',20):.2f}**", f"**{g('MORI',40):.2f}**", f"**{g('MORI',80):.2f}**"],
    ["**MORI ÷ TA+O**", f"**{g('MORI',20)/g('TAO',20):.3f}**", f"**{g('MORI',40)/g('TAO',40):.3f}**",
     f"**{g('MORI',80)/g('TAO',80):.3f}**"],
], 6.98, 2.10, 5.74, 0.6, fs=9.5, hdr_fs=9.5,
    col_widths=[1.55, 1.35, 1.35, 1.35], highlight_rows={4: HEALTHY, 5: HEALTHY})

zone(s, "경향", "세 줄 요약", 0.42, 4.34, 12.5, 2.35, BLUE)
add_text(s, "①  **MORI 가 모든 동시성에서 goodput 1등**이고, 압박이 커질수록 격차가 벌어진다 "
            "(+7.4% → +5.1% → **+14.2%**)\n\n"
            "②  **MORI 는 처리량을 얻고 지연을 내준다** — TTFT p50 은 네 조건 전부에서 TA+O 보다 느리다 "
            "(**+13% ~ +309%**)\n\n"
            "③  **GPU util 은 전 셀 97~100%** — goodput 0 인 SMG 포함. 사용률만으로는 아무것도 가릴 수 없다",
         0.62, 4.82, 12.1, 1.7, size=12)
footer(s, "원시 데이터: ~/yunuikang_work/h200_scratch/mori/{h200_gate, h200_phase1, h200_phase1_8b, h200_phase2}   [측정]")
set_notes(s, """한 장으로 정리하겠습니다.

왼쪽이 조건입니다. H200 한 장, TP1, Qwen2.5-7B입니다.
토큰 제한을 64만 7천으로 걸어서 fit이 20이 되게 했고,
CPU 계층은 GPU 풀의 두 배로 잡았습니다.
동시성을 20, 40, 80으로 올리면 초과율이 1배, 2배, 4배가 됩니다.

오른쪽이 결과입니다. goodput 숫자만 뽑았습니다.
맨 아래 줄 비율을 보시면 1.074, 1.051, 1.142입니다.

아래 세 줄이 경향입니다.

첫째, MORI가 모든 동시성에서 1등이고 압박이 커질수록 격차가 벌어집니다.

둘째, 대신 응답 시작 시간은 항상 뒤집니다. 이건 네 가지 조건에서 전부 확인됐습니다.
처리량과 지연 사이의 거래 관계라고 보시면 됩니다.

셋째, GPU 사용률은 전 셀에서 97에서 100퍼센트입니다.
goodput이 0인 SMG도 100퍼센트로 돌고 있습니다.
그러니까 GPU가 바쁘다는 것만으로는 아무것도 알 수 없습니다.

마지막으로, 모든 셀이 한 번씩만 돌았습니다.
실행마다 15퍼센트 정도 변동이 있으니 그 폭을 감안해서 봐 주십시오.""")

prs.save(OUT)
print("saved:", OUT, f"({len(prs.slides.__iter__.__self__._sldIdLst)} slides)")
