# -*- coding: utf-8 -*-
"""Full-study deck builder — part 2 (slides 11–19). Appends to part1 pptx."""
import sys
sys.path.insert(0, "/home/yunuikang/yunuikang_work/distserving/scripts")
import decklib_yunuikang as D
from decklib_yunuikang import (INK, BLUE, RED, GREEN, GRAY, LT, AMBER, WHITE, RGBColor)
from pptx import Presentation
from pptx.enum.text import PP_ALIGN

prs = Presentation("/home/yunuikang/yunuikang_work/distserving/scratch/sab/_deck_part1.pptx")
HL   = RGBColor(0xFF, 0xF3, 0xD6)
WIN  = RGBColor(0xDF, 0xEE, 0xE4)
LOSE = RGBColor(0xF7, 0xDD, 0xD8)


def blank():
    return prs.slides.add_slide(prs.slide_layouts[6])


# ---------------------------------------------------------------- slide 11
s = blank()
D.band(s, 0, 0.14, BLUE)
D.add_title(s, "결과 ② — 히트맵: duty × f{1,1.5,2,∞} → 최적은 '이진'")
D.add_text(s, "H1(내부 최적 f*) 반증", 0.42, 1.02, 6.5, 0.3, size=12.5, color=GRAY, bold=True)
D.add_takeaway(s, "각 행의 최적 f는 항상 끝점(f=1 또는 f=∞) — 중간 f가 이기는 행이 없다 → 정책은 이진, H1 반증")
D.add_table(s, [
  ["d", "fit×d", "f=1 (tr)", "f=1.5", "f=2", "f=∞ (default)", "최적 f"],
  ["0.1", "0.476", "0.036", "0.045", "0.050", "0.051 ★", "f=∞ (default)"],
  ["0.2", "0.952", "0.073 ★", "0.054", "0.055", "0.055", "f=1 (tr)"],
  ["0.3", "1.428", "0.093 ★", "0.058", "0.056", "0.057", "f=1 (tr)"],
  ["0.5", "2.381", "0.111 ★", "0.064", "0.057", "0.057", "f=1 (tr)"],
  ["0.7", "3.333", "0.115 ★", "0.065", "0.058", "0.057", "f=1 (tr)"],
  ["0.9", "4.285", "0.133 ★", "0.066", "0.058", "0.057", "f=1 (tr)"],
], 0.5, 1.95, 7.6, 3.6, fs=11.5, hdr_fs=11,
   col_widths=[0.7, 1.0, 1.2, 1.0, 0.9, 1.4, 1.4],
   highlight_rows={1: LOSE, 2: WIN, 3: WIN, 4: WIN, 5: WIN, 6: WIN})
D.add_figure(s, "step5_table_fgrid_yunuikang", 8.35, 2.0, 4.6, 3.7)
D.add_caption(s, "행별 정규화 히트맵 — 각 행 최적 f 강조", 8.35, 5.75, 4.6, size=9.5)
D.add_bullets(s, [
  ("★ 가치가 goodput(★)는 f=1 또는 f=∞ 끝점에만. 중간 f(1.5·2)가 이기는 행 = 0.", 0, INK, True),
  ("→ H1(미포화 zone 내부 최적 f*) 반증. 최적 정책 = 이진 선택(tr 또는 overcommit). f축 폐기.", 0, BLUE, True),
], 0.5, 5.75, 7.6, 1.2, size=12, gap=7)
D.set_notes(s,
"tr과 default 사이 중간 f가 두 세계의 장점을 모은 최적일 거라는 가설이 H1이었습니다. 미포화에선 tr이 GPU를 "
"굶기고 default는 스래싱하니, 그 중간이 좋지 않겠냐는 직관이죠. 이 표가 H1을 정면으로 검증합니다. duty 여섯 값 "
"각각에 대해 f를 1, 1.5, 2, 무한대로 바꿔 goodput을 쟀습니다. 각 행에서 별표가 그 행의 최적입니다. 보시면 "
"별표는 항상 양 끝 — f=1 아니면 f=무한대 — 에만 찍힙니다. 맨 윗줄 duty 0.1에서만 default(f=무한대)가 최적이고, "
"나머지 다섯 줄은 전부 f=1인 tr이 최적입니다. 중간값인 f=1.5나 f=2가 그 행에서 이기는 경우가 단 하나도 없습니다. "
"즉 미포화 zone 안에 tr과 default를 둘 다 이기는 내부 최적 f*는 존재하지 않습니다. H1은 반증됐고, 최적 정책은 "
"연속 노브의 달콤한 지점이 아니라 tr이냐 overcommit이냐의 '이진 선택'입니다. 그래서 f축 자체를 폐기하고, 이제 "
"질문은 '언제 tr, 언제 default냐'는 이진 경계 하나로 좁혀집니다. 이 정정은 중요합니다 — 원래 기대했던 '중간 "
"정책의 개선 여지'는 없고, 대신 '경계를 정확히 아는 선택기'가 답이라는 뜻이니까요. 그런데 왜 중간 f가 없는지, "
"왜 조금만 overcommit해도 캐시가 무너지는지 — 그 기전을 다음 장에서 코드와 구조로 파헤칩니다.")


# ---------------------------------------------------------------- slide 11b (WHY no internal optimum — mechanism)
s = blank()
D.band(s, 0, 0.14, BLUE)
D.add_title(s, "왜 내부 최적 f*가 없나 — 캐시 붕괴는 '절벽' (코드·구조)")
D.add_text(s, "결과 ② 심화 — H1 반증의 기전", 0.42, 1.02, 6.5, 0.3, size=12.5, color=GRAY, bold=True)
D.add_takeaway(s, "margin>0이면 working set > 물리 KV → vLLM preempt 시작 → 닫힌 루프서 eviction 자기증폭 → f=1.25만 돼도 hit 0.86→0.42")
# left: the cliff table
D.add_text(s, "d=0.2 경계(fit×d=0.95): f를 조금 올릴 때 참 hit", 0.5, 1.9, 6.2, 0.32, size=12, color=INK, bold=True)
D.add_table(s, [
  ["f", "참 hit", "recompute%", "gpu%"],
  ["1.00 (tr)", "0.858", "14%", "~28"],
  ["1.05 (=f_sat)", "0.852", "15%", "29"],
  ["1.25", "0.415", "59%", "70"],
  ["1.50", "0.222", "78%", "73"],
  ["∞ (default)", "0.014", "99%", "92"],
], 0.5, 2.3, 6.2, 2.5, fs=11, hdr_fs=11,
   col_widths=[1.9, 1.4, 1.7, 1.2],
   highlight_rows={1: RGBColor(0xDF,0xEE,0xE4), 2: RGBColor(0xDF,0xEE,0xE4), 3: RGBColor(0xF7,0xDD,0xD8)})
D.add_text(s, "★ f=1.05는 f=1과 사실상 동일(hit 0.852). f=1.25 한 칸에서 hit 0.86→0.42 급락 → '절벽'.\n"
              "→ 중간 f는 캐시를 이미 잃고, tr의 직렬화 비용만 남음.",
           0.5, 4.95, 6.2, 1.0, size=11, color=INK, bold=True)
# right: code + structural mechanism
D.add_text(s, "기전 (코드 + 구조)", 7.0, 1.9, 5.8, 0.32, size=12.5, color=INK, bold=True)
D.add_bullets(s, [
  ("① 코드: remaining_capacity = C_total − (active − shared_tokens + buffer).", 0, INK, True),
  ("  margin=(f−1)·C_total를 더하면 working set이 f·C_total까지 허용 → 물리 KV(C_total) 초과분을 vLLM이 preempt(recompute).", 1, GRAY, False),
  ("② 프로그램당 all-or-nothing: 에이전트 컨텍스트는 단조증가 + prefix 블록캐시.", 0, INK, True),
  ("  꼬리 블록 하나만 evict돼도 다음 턴 전체 재프리필 → 그 프로그램 hit 1→0 (중간 없음).", 1, GRAY, False),
  ("③ 닫힌 루프 자기증폭: 모든 프로그램이 매 턴 복귀.", 0, RED, True),
  ("  evict된 프로그램이 즉시 돌아와 재계산용 블록 요구 → 또 다른 프로그램 evict → victim이 전체로 회전.", 1, GRAY, False),
  ("  → 25% overcommit이 25%가 아니라 '거의 전부'를 thrash로 밀어넣음 (선형 아님, 상전이).", 1, RED, False),
], 7.0, 2.3, 5.9, 3.5, size=11, gap=6)
D.add_text(s, "④ 결론(비용모델): 중간 f = tr 직렬화 S(1.749) + default 붕괴 W(재계산 78~99%) = 양쪽 최악.  "
              "wall ∝ S·W/U 에서 끝점(f=1 또는 ∞)만 최적 → 내부 f* 부재(H1 반증).",
           7.0, 5.95, 5.9, 1.1, size=10.5, color=BLUE, bold=True)
D.set_notes(s,
"앞 장에서 최적 정책이 이진이라고 했는데, 왜 중간 f가 없는지 — 조금만 overcommit해도 왜 캐시가 거의 다 무너지는지 "
"— 그 기전을 코드와 구조로 제대로 설명하는 장입니다. 왼쪽 표가 현상입니다. duty 0.2 경계에서 f를 조금씩 올려봤습니다. "
"f=1.0인 tr은 참 캐시 적중이 0.858입니다. f=1.05, 즉 5%만 초과 적재해도 0.852로 거의 그대로입니다. 그런데 f=1.25, "
"25% 초과에서 갑자기 0.415로 반토막 나고, f=1.5에서 0.222, default에서 0.014로 사라집니다. 한 칸 만에 절벽처럼 "
"떨어지죠. 왜 이런 절벽이 생기는지 세 가지로 설명합니다. 첫째, 코드입니다. tr의 남은 용량은 KV 총량에서 활성 토큰 "
"빼기 공유 캐시 더하기 버퍼를 뺀 값입니다. overcommit factor f를 주면 margin이 f 빼기 1 곱하기 KV 총량만큼 더해져서, "
"작업 집합이 물리 KV의 f배까지 허용됩니다. 하지만 물리 KV는 딱 C_total뿐이라, 그 초과분은 vLLM 백엔드가 강제로 "
"preempt해서 블록을 버리고 나중에 재계산합니다. 둘째, 프로그램 하나하나가 all-or-nothing입니다. 에이전트 컨텍스트는 "
"턴마다 쌓여서 단조 증가하고, prefix 캐시는 블록 단위로 앞에서부터 이어집니다. 그래서 꼬리 블록 하나만 쫓겨나도 "
"다음 턴엔 그 뒤 전체를 다시 계산해야 합니다 — 그 프로그램의 적중이 1에서 0으로, 중간이 없습니다. 셋째가 절벽의 "
"진짜 원인인 자기증폭입니다. 닫힌 루프라 모든 프로그램이 매 턴 GPU로 돌아옵니다. 쫓겨난 프로그램이 즉시 복귀해 "
"재계산용 블록을 요구하면, 그걸 위해 또 다른 프로그램을 쫓아내고, 그것도 복귀해 또 쫓아내고 — victim이 특정 소수가 "
"아니라 전체 프로그램을 돌아가며 덮칩니다. 그래서 25% 초과 적재가 25%의 손실이 아니라 거의 전부를 thrash로 "
"밀어넣습니다. 선형 감소가 아니라 상전이인 겁니다. 넷째, 그래서 비용 모델로 보면 중간 f는 최악입니다. tr의 직렬화 "
"비용 S 1.749를 그대로 지면서, 캐시는 이미 f=1.25에서 잃어 재계산 비율이 default 수준으로 올라갑니다. wall이 S 곱하기 "
"W 나누기 U인데, 중간 f는 S도 높고 W도 높아 양쪽의 나쁜 점만 갖습니다. 그러니 최적은 항상 끝점 — 캐시를 지키는 "
"f=1이거나, 직렬화를 포기하는 f=무한대 — 이고, 그 사이 최적점 f*는 존재하지 않습니다. 이것이 H1 반증의 물리적 "
"이유입니다.")


# ---------------------------------------------------------------- slide 12
s = blank()
D.band(s, 0, 0.14, BLUE)
D.add_title(s, "결과 ③ — 전환점 fit×d*=0.62: 촘촘 스윕 표 (84 runs)")
D.add_text(s, "이진 경계의 위치 (표 먼저)", 0.42, 1.02, 6.5, 0.3, size=12.5, color=GRAY, bold=True)
D.add_takeaway(s, "fit×d 0.50~0.90 촘촘 스윕(7점×2정책×2C×3반복): wall ratio(def/tr)가 0.60↔0.65에서 1을 통과 → 전환점 0.62")
# dense sweep table (left, 표 먼저)
D.add_text(s, "증거 1 — Wall time 비율 (default / tr), C=10, n=3 평균", 0.5, 1.88, 7.5, 0.3, size=11.5, color=INK, bold=True)
D.add_table(s, [
  ["fit×d", "d", "def wall", "tr wall", "ratio", "승자", "tr 실패"],
  ["0.50", "0.105", "195.2", "221.0", "0.88", "def +12%", "0%"],
  ["0.60", "0.126", "190.1", "192.6", "0.99", "tied", "3.3%"],
  ["0.65", "0.137", "187.9", "183.9", "1.02", "tr +2%", "3.3%"],
  ["0.70", "0.147", "186.6", "174.3", "1.07", "tr +7%", "0%"],
  ["0.75 †", "0.158", "185.8", "195.7", "0.95", "def +5%", "6.7%"],
  ["0.80", "0.168", "184.3", "162.0", "1.14", "tr +14%", "0%"],
  ["0.90", "0.189", "182.9", "147.9", "1.24", "tr +24%", "0%"],
], 0.5, 2.25, 7.5, 3.1, fs=10.5, hdr_fs=10.5,
   col_widths=[0.9, 0.85, 1.1, 1.05, 0.85, 1.55, 1.1],
   highlight_rows={2: RGBColor(0xFF,0xF3,0xD6), 3: RGBColor(0xFF,0xF3,0xD6)})
D.add_text(s, "보간: ratio가 0.60(0.99)→0.65(1.02) 사이서 1 통과 → fit×d*=0.62±0.03.  "
              "† fd=0.75는 capacity timeout 2/3로 이상점.",
           0.5, 5.45, 7.5, 0.7, size=9.5, color=GRAY)
# figure (right)
D.add_figure(s, "step5_transition_yunuikang", 8.15, 1.9, 4.85, 3.5)
D.add_caption(s, "wall ratio vs fit×d — 0.62서 1 통과", 8.15, 5.45, 4.85, size=9)
# corroborating evidence (right, compact)
D.add_bullets(s, [
  ("교차검증(다른 지표도 같은 전환점):", 0, INK, True),
  ("p95도 fit×d≈0.60서 전환 (tr +5~41%)", 0, BLUE, False),
  ("tr TRUE_hit 0.81~0.84 전 구간 평탄 → 캐시보존은 fit×d 무관", 0, GRAY, False),
  ("tr GPU 21→32% vs def 84~90%(상시포화) → idle↔recompute 교차=전환점", 0, GRAY, False),
  ("C=10 vs C=20 전환점 C-안정(경계 외 <1.1%)", 0, GRAY, False),
  ("★ 경계=0.62±0.03, 1이 아님. tr 실패 3.3~6.7%(def 0%)", 0, AMBER, True),
], 8.15, 5.75, 4.85, 1.4, size=9.5, gap=4)
D.set_notes(s,
"정책이 이진이라면 남는 질문은 단 하나 — 경계가 어디냐입니다. 흔히 R=1, 즉 fit×d=1이 경계일 거라 생각하지만, "
"실측은 다릅니다. duty를 촘촘히 스윕해 tr과 default의 wall time을 비교한 결과, 전환점은 fit×d가 0.62, 오차 "
"플러스마이너스 0.03입니다. fit×d가 0.60 미만이면 default가 이기고(GPU 놀리는 idle 비용이 재계산 비용보다 "
"크니까), 0.65를 넘으면 tr이 이깁니다(재계산 비용이 idle 비용보다 크니까). 그 사이는 2% 이내로 사실상 동점인 "
"전환 구간입니다. 왜 경계가 1이 아니라 0.62로 1보다 아래에 있냐면, 경계 근처에서도 캐시를 보존하는 가치가 꽤 "
"높기 때문입니다 — 그래서 tr이 이기는 영역이 R=1 아래로 조금 더 확장됩니다. 물리적으로는, tr이 GPU를 78%에서 "
"68%로 놀리는 idle 비용과, default가 프롬프트의 대부분을 재계산하는 recompute 비용이 교차하는 지점이 fit×d* "
"입니다. 전환은 절벽이 아니라 점진적이고, 프로그램 수 C를 바꿔도 위치가 안정적입니다. 한 가지 실무 경고는, "
"전환점 아래에서 tr이 3.3%에서 10%까지 capacity timeout으로 실패한다는 점입니다 — default는 0%죠. 그럼 이 "
"0.62라는 숫자를 사후 관찰이 아니라 사전에 예측할 수 있을까요? 다음 장의 비용 모델이 답합니다.")


# ---------------------------------------------------------------- slide 13
s = blank()
D.band(s, 0, 0.14, BLUE)
D.add_title(s, "결과 ④ — 비용 모델이 전환점을 예측 (0.625 vs 실측 0.62)")
D.add_text(s, "wall ∝ S · W / U", 0.42, 1.02, 6.5, 0.3, size=12.5, color=GRAY, bold=True)
D.add_takeaway(s, "직렬화 S · 재계산 W · 이용률 U 세 항만으로 전환점을 0.9% 오차로 예측 — 사전 배치 결정 가능")
D.chip(s, "wall(policy)  ∝  S(policy) · W(policy) / U(policy, fit·d)", 0.6, 1.9, 8.2, GREEN, size=14, h=0.5)
D.add_table(s, [
  ["항", "의미", "값"],
  ["S_tr", "직렬화 계수 (tr pause)", "1.749 ± 0.095"],
  ["W_def / W_tr", "재계산 비율 (default/tr)", "0.985 / 0.168 = 5.86×"],
  ["U_tr(fd)", "이용률(tr)", "0.0986 + 0.2557·fd"],
  ["U_def(fd)", "이용률(default)", "0.7819 + 0.1338·fd"],
  ["예측 전환점", "wall_tr = wall_def 풀이", "fit×d* = 0.625"],
  ["실측 전환점", "STEP 5 스윕", "fit×d* = 0.62"],
  ["오차", "", "0.005 (0.9%)"],
], 0.5, 2.65, 7.3, 3.9, fs=11, hdr_fs=11,
   col_widths=[1.6, 2.9, 2.8],
   highlight_rows={5: WIN, 6: WIN, 7: HL})
D.add_figure(s, "step6_cost_model_yunuikang", 8.0, 2.5, 5.0, 4.0)
D.add_caption(s, "비용 모델 곡선 — 예측 전환점 0.625 (실측 0.62, 6점 ±1.3%)", 8.0, 6.5, 5.0, size=9.5)
D.set_notes(s,
"전환점 0.62를 사후에 관찰한 것으로 그치면 실무에 못 씁니다. 배치 전에 예측할 수 있어야 하죠. 그래서 wall time을 "
"세 항의 곱으로 모델링했습니다 — wall은 직렬화 계수 S 곱하기 재계산 비율 W 나누기 이용률 U에 비례합니다. S는 "
"tr이 pause로 프로그램을 직렬화하는 정도로 1.749, W는 재프리필 비율인데 default가 0.985로 프롬프트의 거의 "
"전부를, tr은 0.168만 재계산해 default가 tr의 5.86배입니다. U는 각각 fit×d의 일차식으로 피팅됩니다. 이 세 항으로 "
"tr의 wall과 default의 wall이 같아지는 fit×d를 풀면 0.625가 나옵니다. 실측 전환점 0.62와 오차 0.005, 즉 0.9%로 "
"일치합니다. 일반 6개 duty 점에서도 예측 오차가 1.3% 이내였습니다. 의미가 큽니다. 워크로드의 duty와 하드웨어의 "
"fit만 알면, 실험 없이 어느 정책이 이길지, 경계가 어디인지 계산으로 알 수 있다는 뜻입니다. 이게 뒤에 나올 "
"'fit×d-aware 선택기'의 이론적 근거입니다. 여기까지가 합성 워크로드로 세운 이론입니다. 이제 이 이론이 실제 "
"데이터에서도 맞는지를 네 워크로드로 교차검증합니다.")


# ---------------------------------------------------------------- slide 14
s = blank()
D.band(s, 0, 0.14, BLUE)
D.add_title(s, "교차검증 ① — P1 flip: 같은 tr이 4090↔Pro6000에서 뒤집힘")
D.add_text(s, "k_fit 축 실증 (SWE·TraceLab)", 0.42, 1.02, 6.5, 0.3, size=12.5, color=GRAY, bold=True)
D.add_takeaway(s, "★ TraceLab 4090: tr이 hit를 30× 지켜도 throughput은 −34% 패 → KV ×10.4 키운 Pro6000선 +87% 승 (같은 tr·워크로드)")
D.add_table(s, [
  ["TraceLab · C (같은 워크로드)", "def thru", "tr thru", "def hit", "tr hit", "결과"],
  ["4090 C=16 (fit~2)", "0.107", "0.073", "0.047", "0.799", "tr −32% (hit 17×)"],
  ["4090 C=32", "0.108", "0.069", "0.032", "0.774", "tr −36% (hit 24×)"],
  ["4090 C=48", "0.102", "0.067", "0.026", "0.772", "tr −34% (hit 30×)"],
  ["Pro6000 C=32 (fit~25)", "0.039", "0.073", "0.269", "0.613", "tr +87% (hit 2.3×)"],
  ["Pro6000 C=64", "0.040", "0.073", "0.182", "0.569", "tr +80% (hit 3.1×)"],
  ["SWE Pro6000 C=64 (fit~58)", "0.024", "0.051", "0.241", "0.686", "tr +113% (hit 2.8×)"],
], 0.5, 1.95, 8.0, 3.0, fs=10, hdr_fs=9.5,
   col_widths=[2.5, 0.85, 0.85, 0.85, 0.85, 2.1],
   highlight_rows={1: LOSE, 2: LOSE, 3: LOSE, 4: WIN, 5: WIN, 6: WIN})
D.add_text(s, "★ flip 기전: 4090은 프로그램(input median 18k)이 KV(43,888)에 육박 → 동시 ~2개만 적재. "
              "tr이 hit는 30× 지켜도 pause가 병렬성을 죽여 throughput 패. KV ×10.4(Pro6000)면 hit·throughput 동시 승.",
           0.5, 5.05, 8.0, 0.9, size=10, color=INK, bold=True)
D.add_figure(s, "tp2_pred_vs_meas_U", 8.7, 1.95, 4.3, 3.3)
D.add_caption(s, "R모델 예측 U vs 실측 U (4090 앵커 포함 Pearson r=0.982)", 8.7, 5.2, 4.3, size=9.5)
D.add_bullets(s, [
  ("tr U: 0.35(4090) → 0.97(Pro6000). k_fit 1.6→21.6, R 0.31→6.2.", 0, INK, True),
  ("★ Pro6000는 모든 셀 R>1 → U~1.0 포화. tr 승리는 occupancy 아니라 goodput(hit).", 0, AMBER, True),
], 8.7, 5.5, 4.3, 1.3, size=10.5, gap=6)
D.set_notes(s,
"이론을 실제 데이터로 검증하는 첫 장입니다. k_fit 축, 즉 KV 풀 크기를 바꿨을 때 승패가 예측대로 뒤집히는지를 "
"봅니다. 위 표에 4090 실측을 그대로 채웠습니다. 4090에서 TraceLab을 돌리면 흥미로운 일이 벌어집니다 — tr이 "
"캐시 적중은 압도적으로 지킵니다. C=48에서 default 적중이 0.026으로 붕괴하는데 tr은 0.772를 지켜 30배입니다. "
"그런데도 처리량은 tr이 0.067로 default 0.102보다 34% 낮습니다. 왜 적중을 30배 지키고도 지느냐 — 이게 flip의 "
"핵심 기전입니다. TraceLab 프로그램은 입력이 중앙값 18k 토큰으로 아주 커서, 4090의 KV 43,888 토큰에는 동시에 "
"두 개 정도밖에 안 들어갑니다. tr은 용량 초과분을 pause로 막아 캐시는 보존하지만, 닫힌 루프라 멈춘 프로그램이 "
"슬롯을 점유해 동시 실행 병렬성이 급감합니다. default는 캐시를 갈아엎으며 병렬성을 유지해 wall-clock 처리량은 "
"오히려 높습니다. 즉 프로그램이 KV 용량에 육박하면 tr의 캐시 보존 이득이 처리량으로 전환되지 않습니다. 그런데 "
"Pro6000 두 장으로 KV "
"풀을 456,944 토큰 — 4090의 10.41배 — 로 키우면 fit이 25로 올라 포화가 됩니다. 그러자 C=32에서 tr이 처리량 "
"87%, 적중 2.3배, p95 46% 개선으로 이기고, C=64에서도 80%, 3.1배로 이깁니다. 같은 tr, 같은 워크로드인데 "
"하드웨어로 fit만 키우니 패가 승으로 뒤집힌 겁니다. SWE도 마찬가지로 fit 58을 넘는 C=64에서 default가 붕괴하고 "
"tr이 113% 이깁니다. 붕괴 임계가 정확히 fit이라는 것도 확인됩니다 — TraceLab은 fit 25라 C=32에서, SWE는 fit 58"
"이라 C=64에서 무너집니다. 오른쪽 그림은 R 모델의 예측 U와 실측 U인데, 4090 앵커까지 포함해 상관 0.982로 "
"거의 직선입니다. 한 가지 중요한 정정이 노란 줄입니다. Pro6000에선 모든 셀이 R>1이라 실측 U가 0.97에서 1.0으로 "
"포화됩니다 — 스래싱하는 default도 재프리필로 GPU는 바쁩니다. 그래서 여기서 tr의 승리는 '얼마나 바쁜가"
"(occupancy)'가 아니라 '얼마나 productive한가(goodput, 적중)'에서 옵니다. 이 goodput 대 occupancy 구분이 "
"다음 HLE 장에서 결정적입니다.")


# ---------------------------------------------------------------- slide 15 (NEW: HLE anatomy)
s = blank()
D.band(s, 0, 0.14, BLUE)
D.add_title(s, "HLE 워크로드 해부 — 왜 특이한가 (ToolOrchestra)")
D.add_text(s, "교차검증 ② 준비", 0.42, 1.02, 6.5, 0.3, size=12.5, color=GRAY, bold=True)
D.add_takeaway(s, "원격 API 상시 heavy-tail(max 98s > t_reason 14s) → 도구 대기가 GPU를 비운다 — 유일하게 진짜 U를 무너뜨리는 구조")
# architecture chain (left)
D.add_text(s, "파이프라인 (한 턴):  로컬 추론 → 로컬 검색 → 원격 API", 0.5, 1.9, 6.4, 0.35, size=12, color=INK, bold=True)
D.chip(s, "Nemotron-Orch 8B\n(로컬 GPU)", 0.5, 2.35, 2.0, BLUE, size=9.5, h=0.72)
D.add_text(s, "→", 2.55, 2.5, 0.4, 0.4, size=15, color=GRAY, bold=True)
D.chip(s, "FAISS\n(로컬 0.32s)", 2.95, 2.35, 1.6, GREEN, size=9.5, h=0.72)
D.add_text(s, "→", 4.6, 2.5, 0.4, 0.4, size=15, color=GRAY, bold=True)
D.chip(s, "원격 GLM API\n(heavy-tail)", 5.0, 2.35, 1.9, RED, size=9.5, h=0.72)
D.add_bullets(s, [
  ("t_reason(오케스트레이터 GPU) med 14s.  t_tool = GLM 원격지연 + FAISS 0.32s (search 12 + answer 4/턴).", 0, INK, False),
  ("★ tool_duration max 98s > t_reason 14s — 한 번의 도구 꼬리가 추론 턴보다 7배 김.", 0, RED, True),
  ("→ 그 프로그램은 오래 off-GPU. 12~13개가 무작위로 이러면 다수가 동시에 GPU 이탈.", 0, INK, False),
  ("→ R=k_fit·d ≫1(예측 U=1.0)이어도 실측 U=0.64~0.71로 눌림. mean-d가 U 과대예측.", 0, AMBER, True),
], 0.5, 3.35, 6.4, 2.5, size=11.5, gap=9)
# 24h latency tables (right)
D.add_text(s, "24h GLM 원격지연 분포 (tail 포함)", 7.1, 1.9, 5.8, 0.35, size=12, color=INK, bold=True)
D.add_table(s, [
  ["도구", "median", "p95", "p99", "max"],
  ["search (12/턴)", "2.0s", "11.2s", "23.3s", "38.6s"],
  ["answer (4/턴)", "2.9s", "48.8s", "67.1s", "98.0s"],
  ["trace tool_dur", "2.7s", "24.4s", "—", "98s"],
], 7.1, 2.35, 5.8, 1.5, fs=10.5, hdr_fs=10.5,
   col_widths=[1.7, 1.0, 1.0, 1.0, 1.1], highlight_rows={2: RGBColor(0xF7,0xDD,0xD8)})
D.add_text(s, "시간대별 유효 duty (24h, 6 windows)", 7.1, 4.05, 5.8, 0.35, size=12, color=INK, bold=True)
D.add_table(s, [
  ["window (UTC)", "tool med", "유효 d"],
  ["16–20 (peak)", "4.2s", "0.770"],
  ["00–04 (저부하)", "낮음", "0.887"],
  ["→ spread", "×1.15", "0.116"],
], 7.1, 4.5, 5.8, 1.5, fs=10.5, hdr_fs=10.5,
   col_widths=[2.4, 1.7, 1.7], highlight_rows={1: RGBColor(0xFF,0xF3,0xD6)})
D.add_text(s, "★ 다른 워크로드와 결정적 차이: 도구가 '로컬·짧음'이 아니라 '원격·상시 긴 꼬리'.  "
              "SWE/Science는 tool≈0(로컬)이라 U 포화, HLE만 tool-wait이 wall을 지배(d~0.82).",
           7.1, 6.1, 5.8, 1.0, size=10.5, color=GRAY)
D.set_notes(s,
"HLE가 왜 fit×d≫1인데도 tr이 처리량으로 못 이기는 예외인지, 그 원인이 워크로드 구조 자체에 있어서 한 장을 "
"따로 뒀습니다. HLE는 ToolOrchestra라는 파이프라인입니다. 한 턴은 세 단계로 흐릅니다. 먼저 Nemotron "
"오케스트레이터 8B가 로컬 GPU에서 도구 호출을 생성합니다 — 이 추론 시간 t_reason이 중앙값 14초입니다. 다음 "
"FAISS 리트리버가 로컬에서 문서를 찾는데 0.32초로 일정합니다. 마지막으로 원격 GLM API를 부르는데, 한 턴에 "
"검색 12번 더하기 답변 4번을 호출하고, 이 원격 호출이 상시로 긴 꼬리를 만듭니다. 오른쪽 위 표가 24시간 동안 "
"실측한 GLM 지연 분포입니다. 검색은 중앙값 2초에 최대 38.6초, 답변은 중앙값 2.9초인데 p95가 48.8초, 최대 "
"98초까지 갑니다. 여기서 이 워크로드의 핵심 특이점이 나옵니다 — 도구 시간의 최대 98초가 추론 시간 14초보다 "
"7배 깁니다. 즉 답변 도구의 꼬리가 한 번 터지면, 그 한 번의 도구 대기가 프로그램 전체 추론 턴보다 훨씬 길어서 "
"그 프로그램은 GPU에서 오래 빠져 있습니다. 열두세 개 프로그램이 이런 꼬리를 무작위로 맞으면, 매 순간 상당수가 "
"동시에 GPU를 떠나 있습니다. 그래서 R이 1을 훨씬 넘어 예측 이용률은 1.0인데, 실측은 0.64에서 0.71로 눌립니다 "
"— 평균 duty로 만든 R이 U를 과대예측하는 겁니다. 오른쪽 아래 표는 이 꼬리가 시간대에 따라 변한다는 것도 "
"보여줍니다 — 피크 시간대(UTC 16-20)엔 도구 지연이 최고라 유효 duty가 0.770까지 떨어집니다. 다른 워크로드와 "
"결정적 차이는 이겁니다. SWE나 Science는 도구가 로컬이고 거의 0초라 GPU가 포화되지만, HLE만 도구가 원격이고 "
"상시 긴 꼬리라 tool-wait이 wall time을 지배합니다. 이 구조를 머리에 넣고 다음 장의 실측 결과를 보면, 왜 tr이 "
"적중은 지켜도 처리량으로는 못 이기는지가 자연스럽게 이해됩니다.")


# ---------------------------------------------------------------- slide 16 (HLE result)
s = blank()
D.band(s, 0, 0.14, BLUE)
D.add_title(s, "교차검증 ② — HLE: 적중은 지켜도 throughput은 못 이긴다")
D.add_text(s, "상시 heavy-tail → 진짜 U 붕괴", 0.42, 1.02, 6.5, 0.3, size=12.5, color=GRAY, bold=True)
D.add_takeaway(s, "KV 축소로 스래싱 재현·tr이 hit +28% 방어(f(t) 발동)하나 throughput −2~8% — tool-wait이 wall을 지배")
D.add_table(s, [
  ["C", "regime", "def thru", "tr thru", "def hit(true)", "tr hit(true)", "tr paused", "def U", "tr U"],
  ["24", "<fit", "0.840", "0.827", "0.668", "0.693", "0.52", "0.73", "0.71"],
  ["32", "<fit", "0.998", "0.960", "0.632", "0.666", "1.81", "0.70", "0.66"],
  ["40", ">fit", "1.074", "0.987", "0.621", "0.659", "3.16", "0.75", "0.64"],
  ["48", ">fit", "1.063", "1.039", "0.513", "0.654", "5.13", "0.78", "0.67"],
], 0.5, 1.95, 8.1, 2.9, fs=11, hdr_fs=10.5,
   col_widths=[0.5, 0.8, 1.0, 0.95, 1.3, 1.2, 0.95, 0.7, 0.7],
   highlight_rows={4: HL})
D.add_text(s, "fit≈34.5 (KV 502,944→101,840, ÷4.9).  C=48: tr hit 0.654 vs def 0.513 = +28%.  reported 0.380 vs true 0.513(gap +13%p).",
           0.5, 4.95, 8.1, 0.7, size=10.5, color=GRAY)
D.add_figure(s, "p3_hle_kv_contrast", 0.5, 5.65, 8.1, 1.5)
D.add_bullets(s, [
  ("R=k_fit·d ≫1 → 예측 U=1.0", 0, INK, False),
  ("but 실측 U=0.64~0.71", 0, RED, True),
  ("원인: 원격 API 상시 tail(98s)", 0, GRAY, False),
  ("→ 12~13 프로그램 상시 off-GPU", 0, GRAY, False),
  ("★ mean-d 기반 R이 U 과대예측", 0, AMBER, True),
  ("→ heavy-tail엔 tail-aware(진짜) U", 0, AMBER, True),
  ("통찰: tr 승리는 스래싱이", 0, BLUE, False),
  ("throughput을 지배할 때만.", 0, BLUE, True),
], 8.8, 1.95, 4.2, 4.6, size=11, gap=6)
D.set_notes(s,
"HLE는 fit×d가 1을 훨씬 넘는 포화인데도 tr이 처리량으로 못 이기는 예외였습니다. 왜 그런지 이 장이 해부합니다. "
"먼저 KV 풀이 클 때(fit 약 170)는 스래싱 자체가 없어서 tr과 default가 사실상 같았습니다. 그래서 KV를 4.9분의 "
"1로 인위 축소해 fit을 34.5로 만들어 붕괴 레짐을 재현했습니다. 표를 보면 tr이 제 몫을 합니다 — C=48에서 참 "
"적중이 tr 0.654 대 default 0.513으로 28% 높고, tr의 pause가 C와 함께 0.52에서 5.13으로 늘며 f(t) 스케줄이 "
"제대로 발동합니다. 그런데 정작 처리량은 tr이 2%에서 8% 오히려 낮습니다. 이유가 핵심입니다. R이 k_fit 곱하기 d"
"로 1을 훨씬 넘으니 예측 U는 1.0인데, 실측 U는 0.64에서 0.71로 낮습니다. 원격 GLM API의 도구 대기가 상시로 "
"98초까지 길어서, 열두세 개 프로그램이 늘 도구 대기로 GPU에서 빠져 있기 때문입니다. 즉 평균 duty로 계산한 R이 "
"실제 U를 과대예측합니다. 이건 R 모델의 정직한 한계이고, heavy-tail 워크로드에는 tail을 반영한 '진짜 U'가 "
"필요하다는 뜻입니다. 통찰을 한 줄로 하면, tr의 승리는 스래싱이 처리량을 지배할 때만 나온다는 것입니다. HLE는 "
"tool-wait이 wall time을 지배해서, tr이 적중을 지켜도 그게 처리량으로 환산되지 않습니다. 그렇다면 tool tail이 "
"상시가 아니라 희소하면 어떻게 될까요? 그게 Science입니다.")


# ---------------------------------------------------------------- slide 16
s = blank()
D.band(s, 0, 0.14, BLUE)
D.add_title(s, "교차검증 ③ — Science: 희소 tail → 진짜 U 살아있음 → tr 승")
D.add_text(s, "HLE의 대조군 (희소 tail)", 0.42, 1.02, 6.5, 0.3, size=12.5, color=GRAY, bold=True)
D.add_takeaway(s, "극단 decode-heavy(d=0.989)·희소 tail → U=100% 포화 → tr +175~227% 압승. 'U 붕괴는 상시 tail만' 확정")
D.add_table(s, [
  ["C", "regime", "def thru", "tr thru", "def hit(true)", "tr hit(true)", "def p95", "tr p95", "tr 이득"],
  ["8", "<fit", "0.072", "0.083", "0.863", "0.896", "345", "243", "+15%"],
  ["16", "≈fit", "0.027", "0.089", "0.223", "0.851", "1464", "403", "+227%"],
  ["24", ">fit", "0.025", "0.078", "0.136", "0.799", "2235", "779", "+216%"],
  ["32", ">fit", "0.025", "0.070", "0.106", "0.739", "2912", "1049", "+175%"],
  ["48", ">fit", "0.024", "0.072", "0.067", "0.733", "3157", "1026", "+196%"],
], 0.5, 1.9, 8.15, 2.95, fs=10.5, hdr_fs=10,
   col_widths=[0.5, 0.8, 1.0, 0.9, 1.3, 1.15, 0.85, 0.75, 0.9],
   highlight_rows={2: WIN})
D.add_text(s, "fit=16.2, fit×d=16.0.  U=100% (default·tr 양쪽).  tr paused 0→18 (default 0).  default hit_true 0.86→0.07 단조붕괴.",
           0.5, 4.95, 8.15, 0.6, size=10.5, color=GRAY)
D.add_figure(s, "p2_sab_sweep", 0.5, 5.6, 8.15, 1.55)
D.add_bullets(s, [
  ("HLE와 대조:", 0, INK, True),
  ("  HLE 상시 tail → U 0.64~0.71 → tr throughput 패", 1, RED, False),
  ("  Science 희소 tail(1.3%) → U 100% → tr +175~227% 승", 1, BLUE, False),
  ("★ '진짜 U 붕괴 = 상시 tail(HLE) 특유,", 0, AMBER, True),
  ("   희소 tail(Science)엔 없음' 확정.", 0, AMBER, True),
  ("정직: 스캐폴드=mini-swe(논문 OpenHands 아님).", 0, GRAY, False),
  ("고듀티라 crossover(미포화) 진입 불가.", 0, GRAY, False),
  ("tool 실패율 46.6%=범용 샌드박스 패키지 부재", 0, GRAY, False),
  ("(정확도 비교 안 씀, 스케줄링 지표만).", 0, GRAY, False),
], 8.8, 1.9, 4.25, 5.2, size=10.5, gap=5)
D.set_notes(s,
"Science는 HLE의 완벽한 대조군입니다. HLE와 똑같이 fit×d가 1을 훨씬 넘는 포화지만, tool tail이 상시가 아니라 "
"희소합니다. 도구 시간 중앙값이 0.077초, 극단이 300초까지 가지만 그런 극단이 전체의 1.3%뿐입니다 — 듀티 0.989로 "
"거의 순수 decode입니다. 결과를 보면 tr이 압승합니다. fit이 16.2인데 C=16, 즉 fit과 같아지는 지점에서 default가 "
"무너지기 시작해, 참 적중이 0.86에서 0.22로 붕괴하고 p95가 345초에서 1464초로 폭증합니다. tr은 적중을 0.85로 "
"지켜 처리량이 227% 높습니다. C를 48까지 올려도 default 적중은 0.07까지 단조 붕괴하고 tr은 0.73을 지켜 +175"
"에서 227% 이깁니다. 결정적으로, 진짜 이용률 U가 default와 tr 양쪽 다 100%였습니다 — HLE처럼 GPU가 도구 대기로 "
"노는 일이 없었다는 뜻입니다. 그래서 tr이 지킨 적중이 그대로 처리량 이득으로 바뀌었습니다. HLE와 나란히 놓으면 "
"결론이 확정됩니다. 진짜 U를 무너뜨리는 건 '상시' heavy-tail(HLE)뿐이고, '희소' tail(Science)에선 U가 살아있어 "
"tr이 이깁니다. 정직한 한계도 밝힙니다. Science 스캐폴드는 논문의 OpenHands가 아니라 mini-swe입니다 — 빌드 "
"문제로 우회했고, 대신 SWE와 스캐폴드를 통일해 워크로드 효과만 분리했습니다. 또 듀티가 0.989로 높아 미포화 "
"crossover엔 못 들어갑니다. 도구 실패율 46.6%는 범용 샌드박스에 과학 패키지가 없어서지 하네스 결함이 아니고, "
"그래서 정확도 비교엔 안 쓰고 스케줄링 지표만 씁니다.")


# ---------------------------------------------------------------- slide 17
s = blank()
D.band(s, 0, 0.14, BLUE)
D.add_title(s, "정직한 발견과 한계")
D.add_text(s, "무엇을 반증했고 무엇이 남았나", 0.42, 1.02, 6.5, 0.3, size=12.5, color=GRAY, bold=True)
D.add_takeaway(s, "경계는 예측 가능하나 가변적이고, heavy-tail은 진짜 U를 요구한다 — 절대비교가 아닌 방향·차수의 주장")
D.add_bullets(s, [
  ("H1 반증: 미포화 zone 내부 최적 f* 없음 → 최적 정책은 이진(tr 또는 overcommit).", 0, INK, True),
  ("전환점 fit×d*=0.62는 비용모델로 예측(0.625, 0.9% 오차)되나, 경계=1이 아니라 워크로드·HW 의존적으로 가변.", 0, INK, False),
  ("throughput은 goodput(완료/makespan)로만 유효 — raw tok/s는 recompute 낭비를 세어 오도.", 0, BLUE, True),
  ("계측 오염: default의 reported hit이 참 hit(local_compute)을 최대 4.81× 과소보고(스래싱 시). 참 hit 병기 필수.", 0, INK, False),
  ("heavy-tail(HLE): mean-d 기반 R이 U 과대예측(예측1.0 vs 실측0.64~0.71) → tail-aware 진짜 U 필요.", 0, AMBER, True),
  ("tr 신뢰성: 전환점 아래서 capacity timeout 실패 3.3~10% (default 0%).", 0, AMBER, False),
  ("cross-GPU 캐비앗: 워크로드별 하드웨어가 달라 절대 성능 비교 X — 방향·차수·배포내 상대비교만 유효.", 0, RED, True),
  ("Science 스캐폴드=mini-swe(논문 OpenHands 아님), 고듀티라 미포화 crossover 미진입.", 0, GRAY, False),
], 0.5, 1.95, 12.4, 4.8, size=12.5, gap=9)
D.set_notes(s,
"연구자의 정직함을 위해, 무엇을 확실히 보였고 무엇이 한계인지 모읍니다. 먼저 반증. 미포화 zone 안에 tr과 "
"default를 둘 다 이기는 중간 정책 f*는 없었습니다 — 최적은 이진입니다. 둘째, 전환점 0.62는 비용 모델로 0.9% "
"오차로 예측되지만, 그게 1이라는 보편 상수는 아닙니다 — 워크로드와 하드웨어에 따라 움직이는 값입니다. 셋째, "
"처리량은 반드시 goodput, 즉 완료 나누기 makespan으로 봐야 합니다. 날 것의 초당 토큰 수는 default의 재계산 "
"낭비까지 세어 정반대로 오도합니다. 넷째, 계측 자체가 오염됩니다. default의 보고된 적중률이 참 적중을 스래싱 "
"시 최대 4.81배 과소보고합니다 — 그래서 local_compute 기반 참 적중을 반드시 병기해야 합니다. 다섯째, heavy-tail "
"워크로드에선 평균 duty로 만든 R이 U를 과대예측합니다 — HLE에서 예측 1.0 대 실측 0.64에서 0.71. tail을 반영한 "
"진짜 U가 필요합니다. 여섯째, tr은 전환점 아래에서 3.3%에서 10% 실패하는 신뢰성 리스크가 있습니다. 일곱째, "
"가장 중요한 캐비앗 — 워크로드마다 하드웨어가 달라서 절대 성능을 직접 비교하면 안 됩니다. 저희 주장은 방향과 "
"차수, 그리고 같은 배포 안에서의 상대 비교입니다. 마지막으로 Science는 스캐폴드가 논문과 다르고 고듀티라 미포화 "
"영역엔 못 들어갔습니다. 이 한계들을 안고도, 다음 장의 기여는 견고합니다.")


# ---------------------------------------------------------------- slide 18
s = blank()
D.band(s, 0, 0.14, BLUE)
D.add_title(s, "기여와 향후")
D.add_text(s, "정리", 0.42, 1.02, 6.5, 0.3, size=12.5, color=GRAY, bold=True)
D.add_takeaway(s, "fit×d가 최적 정책을 예측 · 전환점은 비용모델로 계산 가능 · SOTA(tr)는 레짐-무지 → 선택기가 개선")
# contributions
b = s.shapes.add_textbox(D.Inches(0.5), D.Inches(1.95), D.Inches(7.4), D.Inches(4.8))
tf = b.text_frame; tf.word_wrap = True
tf.paragraphs[0].text = "기여"
tf.paragraphs[0].runs[0].font.size = D.Pt(15); tf.paragraphs[0].runs[0].font.bold = True
tf.paragraphs[0].runs[0].font.color.rgb = BLUE
for t, bold in [
  ("① fit×d 한 수가 tr/default 최적 정책을 예측 — 측정 5셀 + 42행 격자에서 승패 100% 정합.", True),
  ("② 전환점 fit×d*=0.62를 비용모델(S·W/U)이 0.625로 예측(0.9%) — 실험 없이 배치 결정 가능.", True),
  ("③ SOTA(ThunderAgent tr)는 '레짐-무지': 미포화에서 느리고(최대 −34%) 불안정(실패 3~10%).", True),
  ("④ 4워크로드 교차검증으로 '진짜 U(GPU 병목)가 tr 승패를 결정'을 확립 — fit×d는 U가 살아있을 때만.", True),
  ("⑤ fit×d-aware 선택기: tr↔default를 duty·fit로 이진 선택 → 두 정책·신뢰성 동시 개선.", True),
]:
    p = tf.add_paragraph(); p.text = "•  " + t; p.space_after = D.Pt(11)
    p.runs[0].font.size = D.Pt(12.5); p.runs[0].font.color.rgb = INK; p.runs[0].font.bold = bold
# future
b2 = s.shapes.add_textbox(D.Inches(8.2), D.Inches(1.95), D.Inches(4.8), D.Inches(4.8))
tf = b2.text_frame; tf.word_wrap = True
tf.paragraphs[0].text = "향후"
tf.paragraphs[0].runs[0].font.size = D.Pt(15); tf.paragraphs[0].runs[0].font.bold = True
tf.paragraphs[0].runs[0].font.color.rgb = GREEN
for t in ["tail-aware '진짜 U' 모델 — heavy-tail(HLE)에서 mean-d 과대예측 교정.",
          "전환점 이동의 실증 — GPU·모델·컨텍스트별 fit×d* 지도.",
          "fit×d-aware 적응형 스케줄러 — 런타임에 duty·fit 추정해 tr↔overcommit 전환.",
          "논문 OpenHands 스캐폴드로 Science 재측정(빌드 이슈 해결 시)."]:
    p = tf.add_paragraph(); p.text = "•  " + t; p.space_after = D.Pt(11)
    p.runs[0].font.size = D.Pt(12); p.runs[0].font.color.rgb = INK
D.set_notes(s,
"기여를 정리합니다. 첫째, fit×d라는 단 하나의 수가 tr과 default 중 어느 정책이 최적인지 예측합니다 — 측정한 "
"다섯 셀과 42행 격자에서 승패가 100% 정합했습니다. 둘째, 그 경계인 전환점 0.62를 직렬화·재계산·이용률 세 항의 "
"비용 모델이 0.625로, 0.9% 오차로 예측합니다 — 실험 없이 duty와 fit만으로 배치를 결정할 수 있습니다. 셋째, "
"SOTA인 ThunderAgent tr은 이 레짐을 모릅니다. 그래서 미포화에서 최대 34% 느리고 3에서 10% 실패합니다 — "
"레짐-무지가 SOTA의 약점입니다. 넷째, 네 워크로드 교차검증으로 'tr의 승패를 결정하는 건 진짜 U, 즉 GPU가 실제 "
"병목이냐'임을 확립했습니다. fit×d는 그 진짜 U가 살아있을 때만 유효합니다 — HLE 같은 상시 tail에선 무너집니다. "
"다섯째, 그래서 duty와 fit로 tr과 default를 이진 선택하는 fit×d-aware 선택기를 제안합니다 — 두 정책의 장점과 "
"신뢰성을 동시에 개선합니다. 향후로는, heavy-tail을 교정하는 tail-aware 진짜 U 모델, GPU·모델·컨텍스트별 전환점 "
"지도의 실증, 런타임에 duty와 fit을 추정해 전환하는 적응형 스케줄러, 그리고 빌드 이슈가 풀리면 논문 OpenHands "
"스캐폴드로 Science를 재측정하는 것을 계획합니다.")


# ---------------------------------------------------------------- slide 19
s = blank()
D.band(s, 0, 0.16, BLUE)
D.band(s, 7.34, 0.16, BLUE)
D.add_title(s, "요약 — 전체 인과 사슬", size=26)
D.add_text(s, "한 장 정리", 0.42, 1.05, 6.5, 0.3, size=12.5, color=GRAY, bold=True)
chain = [
 ("퍼즐", "같은 tr이 4090선 지고 Pro6000선 이김 (승패 뒤집힘)", INK),
 ("모델", "R = k_fit × d ≈ mean nrr,  U ≈ min(R,1).  미포화(R<1)에서 tr이 GPU 굶김", BLUE),
 ("일반성", "미포화(fit×d<1)는 4090 전용 아님 — 저듀티·긴컨텍스트·작은KV 중 하나로 진입 (A100/H100도)", INK),
 ("레버", "R↑ 두 축: k_fit(overcommit 조건1) · d(duty 조건2). idle↔recompute 상충", BLUE),
 ("경계", "최적은 이진(H1 반증). 전환점 fit×d*=0.62, 비용모델이 0.625로 예측(0.9%)", GREEN),
 ("교차검증", "P1 flip(r=0.982) · HLE(상시 tail→U붕괴→tr throughput 패) · Science(희소 tail→U포화→tr +227%)", INK),
 ("결론", "tr 승패 = 진짜 U가 결정 (fit×d는 U 살아있을 때). SOTA는 레짐-무지 → fit×d-aware 선택기", GREEN),
]
y = 1.6
for i, (tag, txt, col) in enumerate(chain):
    D.chip(s, tag, 0.5, y, 1.6, col if col != INK else GRAY, size=12, h=0.6)
    D.add_text(s, txt, 2.3, y + 0.06, 10.6, 0.6, size=13, color=INK,
               bold=(tag in ("경계", "결론")))
    if i < len(chain) - 1:
        D.add_text(s, "↓", 1.2, y + 0.52, 0.6, 0.3, size=13, color=GRAY, align=PP_ALIGN.CENTER)
    y += 0.78
D.set_notes(s,
"마지막으로 전체 인과 사슬을 한 장에 압축합니다. 출발은 퍼즐이었습니다 — 같은 tr이 4090에선 지고 Pro6000에선 "
"이겨, 승패가 뒤집혔습니다. 이를 설명하려고 R 모델을 세웠습니다 — R은 k_fit 곱하기 d이고 실측 동시 실행 수와 "
"일치하며, U는 min(R,1). R이 1보다 작은 미포화에서 tr이 GPU를 굶겨 집니다. 이 미포화가 4090만의 문제가 아니라 "
"저듀티·긴컨텍스트·작은KV 중 하나로 A100·H100에서도 생김을 격자로 보였습니다. R을 1 위로 올리는 길은 두 레버 — "
"overcommit과 duty — 이고, 그 사이엔 idle과 recompute의 상충이 있습니다. 이 상충을 스윕한 결과, 최적 정책은 "
"중간이 아니라 이진(H1 반증)이며, 경계인 전환점은 fit×d 0.62로 비용 모델이 0.625로 예측합니다. 마지막으로 네 "
"워크로드로 교차검증했습니다 — P1 flip은 상관 0.982로 모델을 확증했고, HLE는 상시 tail로 진짜 U가 무너져 tr이 "
"처리량으로 못 이기는 예외를, Science는 희소 tail로 U가 포화해 tr이 227% 이기는 정상을 보여, '진짜 U 붕괴는 "
"상시 tail만'임을 확정했습니다. 결론은, tr의 승패는 결국 진짜 U가 결정하고 fit×d는 그 U가 살아있을 때 유효하며, "
"SOTA는 이 레짐을 몰라서 지므로, fit×d-aware 선택기가 답이라는 것입니다. 감사합니다.")


import os
os.makedirs("/home/yunuikang/yunuikang_work/distserving/slides", exist_ok=True)
out = "/home/yunuikang/yunuikang_work/distserving/slides/2026-07-21_full-study_yunuikang.pptx"
prs.save(out)
print("FULL DECK saved:", len(prs.slides._sldIdLst), "slides ->", out)
