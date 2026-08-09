# Tier C 결과-전용 발표덱 제작 — 수치 추출 · 대조 검증 기록

- 작업: 2026-08-09 (KST) · **새 실험 없음. 기존 원자료 재집계 + 덱 생성만.**
- 산출물
  - 덱 `slides/2026-08-08_TIERC_results-only_yunuikang.pptx` (20장)
  - 수치 `scratch/mori/tierc_h200/deck_numbers.json`
  - 추출 `scripts/extract_tierc_numbers_yunuikang.py`
  - 그림 `scripts/plot_tierc_resultsdeck_yunuikang.py` → `figures/tierc_*_yunuikang.png` (6장)
  - 빌더 `scripts/build_tierc_resultsdeck_yunuikang.py`
- 커밋 없음.

---

## 0. 덱 범위 규약 (지시)

**해석·결론·가설·판정 언어 금지.** 슬라이드 본문과 노트는 (1) 실험 환경 (2) 무엇을 어떻게
쟀나 (3) 잰 값 까지만. 결론/요약 슬라이드 없음.

- 빌드 후 금칙어 스캔(따라서 / 의미 / 왜 / 결론 / 해석 / 가설 / 반증 / 기각 / 우위 / 붕괴 /
  잡음 / 원인 / 이긴·진다 …)을 돌려 전 슬라이드 본문·노트를 훑었다. 남은 히트는 전부
  ① 범위 고지 문장("해석이나 결론은 이 자료에 넣지 않았습니다")
  ② 오탐("패널", "closure 요약", 정의를 설명하는 "때문") 이다.
- `pptx` 스킬은 이 머신에 없다 (`~/.claude/skills/` 비어 있음). 지시에 있었으나
  하우스 툴체인(`decklib_yunuikang.py` + python-pptx)으로 진행했다 — DECK_STYLE §0 규약.

## 1. 덱 구성 (20장)

| 부 | 장 | 내용 |
|---|---|---|
| 표지 | 1 | — |
| 1부 환경 | 2–3 | HW/SW 스택 (H200 + 5090 열) · 트레이스·격자·boot assert |
| 2부 방법 | 4–7 | GPU 시계 다이어그램 · 지표 정의 ①(시간) · ②(처리량/캐시/라우터) · closure C1~C4 정의 |
| 3부 결과 | 8–17 | 게이트 측정값 · ★3점 곡선 표/그림 · GPU 예산 그림/표 · 토큰 표 · 파생지표 그림/표+비율 · rank 분포 · Phase 2 나란히 |
| 3부 (5090) | 18–19 | 5090 TP1 예산 · 성능·캐시 지표 |
| 부록 | 20 | 원자료 경로 · 재현 명령 · 계측상 성질 4가지 |

## 2. 대조 검증 — 원자료 재계산 vs 덱 표 [측정]

`deck_numbers.json` 을 거치지 않고 **원자료에서 독립 재계산**한 값이 덱 표 셀에
문자열로 존재하는지 대조했다.

| 대상 | 검증 항목 | 불일치 |
|---|---|---|
| H200 6셀 (예산·토큰·엔진·goodput·라우터·드라이버·closure) | 216 | **0** |
| 5090 TP1 4셀 | 56 | **0** |
| Phase 2 6셀 (엔진 thr · goodput) | 12 | **0** |
| `_type_rank` 재생 3셀 | 21 | **0** |
| **합계** | **305** | **0** |

레이아웃 QA: `deck_qa_yunuikang.py` → **실질 문제: 0** · 리터럴 `**` 0개 ·
노트 없는 슬라이드 없음. 그림 6장 전부 Read 로 육안 확인.

## 3. followup 로그와 값이 갈린 두 곳 — 덱은 원자료 정의를 따랐다 [측정]

### 3.1 goodput@5s — 분모 창

`2026-08-08_TIERC_H200_followup` STEP 2 표의 goodput 값과 1% 안팎 차이가 난다.

원인은 분모다. Phase 2 의 `goodput()` 은 `step_profiles.csv` **전 구간**을 분모로 쓰는데,
Tier C 의 MORI 셀은 드레인 꼬리가 창 밖으로 길게 남는다 (csv span: MORI_C40 **2,184.6s** ·
MORI_C80 **1,960.4s** vs 계측 창 1,254s). 그 함수를 그대로 쓰면 MORI 분모가 창의 1.6~1.7 배가
된다 (MORI_C40 goodput 114.4 / MORI_C80 138.8).

덱은 GPU 예산·closure 와 **같은 계측 창**(`window_<TAG>.json`, warmup 20% 이후 ~ t_end)으로
잘라 계산한다 (`goodput_window()`).

| 셀 | followup 로그 | 덱 (창 기준) | Phase 2 함수 그대로 (참고) |
|---|---|---|---|
| MORI C20 | 178.2 | **176.4** | 177.3 |
| TA+O C20 | 192.1 | **192.6** | 192.8 |
| MORI C40 | 247.0 | **247.3** | 114.4 |
| TA+O C40 | 195.0 | **192.4** | 192.1 |
| MORI C80 | 249.6 | **248.3** | 138.8 |
| TA+O C80 | 243.7 | **240.8** | 242.7 |

비율(MORI÷TA+O): 로그 0.928 / 1.267 / 1.024 → 덱 **0.916 / 1.286 / 1.031**.

### 3.2 TA+O Waiting 축출 건수 — shutdown 이후 줄 포함 여부

`proxy_TAO_*.log` 의 `Paused program` 줄 수는 로그 표와 두 셀에서 다르다.

| 셀 | 전체 | graceful shutdown 이전 | followup 로그 표 |
|---|---|---|---|
| TA+O C20 | 59 | 59 | 59 |
| TA+O C40 | **297** | 285 | 285 |
| TA+O C80 | 425 | **411** | 425 |

즉 로그 표는 C40 에 shutdown-이전 값을, C80 에 전체 값을 썼다 (표 안에서 규칙이 섞였다).
덱은 출하 집계 함수(`analyze_phase2_v2.moves()`)의 정의 그대로 **전체(59 / 297 / 425)** 를
쓰고, 각주에 shutdown 이전 값(59 / 285 / 411)을 병기했다.

MORI 쪽은 두 기준이 같다 (evict 0 / 0 / 1 · demote 29 / 312 / 481).

### 3.3 "thr tok/s" 열의 정체

followup STEP 2 두 번째 표의 `thr tok/s` (142.7 / 186.0 / 142.0 / 133.1 / 153.2 / 149.0) 는
`results_tierc.jsonl` 의 **드라이버** throughput 과 소수점까지 같다. 엔진
steady-window thr 은 별개 값이다 (178.8 / 194.8 / 266.8 / 214.9 / 295.0 / 288.9).
덱은 두 열을 **따로, 이름을 달아** 싣는다.

## 4. 5090 TP1 섹션 — 넣은 것과 뺀 것 [측정]

`scratch/mori/tierc_5090tp1/` 에 같은 계측 산출물이 있다.

- 격자: RTX 5090 ×1 TP1 · Qwen2.5-7B · `max_total_tokens=226,632` → **fit 7.00** ·
  r=2 (host 453,265) · boot assert PASS · host memory 25.99 GB · chunked-prefill 2,048.
- `tierc_summary.json` 에 있는 셀 = **MORI/TA+O × C{7, 15}** 4셀, 전부 closure PASS.
  oversub 1.00× / 2.14×.
- **뺀 것**: `MORI_C20` · `TAO_C20` · `MORI_C70` 은 `window_*.json` 과 engine csv 는 있으나
  closure 요약에 없다 → 덱에 넣지 않고, 그 사실만 슬라이드에 적었다.

C 격자가 다르므로(fit 7 vs 20) H200 표와 같은 열을 겹쳐 읽으면 안 된다는 문구를 노트에 넣었다.

## 5. 덱에 그대로 적어 둔 계측상 성질 (부록 장)

1. [추정] 재계산 **시간**은 독립 측정이 아니라 prefill GPU 시간의 토큰 비 안분이다.
2. [추정] idle 은 `wall − busy` 유도값이라 네 조각의 합 = wall 은 항등식이다.
3. [측정] Waiting 축출은 MORI(`CPU→Waiting`)와 TA+O(`Paused program`)가 서로 다른 사건이다.
4. [측정] 각 셀 n=1 이라 셀 간 변동폭은 이 자료로 알 수 없다.

## 6. 재현

```bash
cd ~/yunuikang_work/distserving
python3 scripts/extract_tierc_numbers_yunuikang.py       # 원자료 -> deck_numbers.json
python3 scripts/plot_tierc_resultsdeck_yunuikang.py      # -> figures/tierc_*_yunuikang.png
python3 scripts/build_tierc_resultsdeck_yunuikang.py     # -> slides/2026-08-08_TIERC_results-only_yunuikang.pptx
python3 scripts/deck_qa_yunuikang.py slides/2026-08-08_TIERC_results-only_yunuikang.pptx
```
