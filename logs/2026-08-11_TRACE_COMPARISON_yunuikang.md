# TraceLab 3종 데이터셋 특성 비교 — 원본 full / Track M / fit32k

- 작성: **2026-08-11 KST 17:40** · 브랜치 `mori` · HEAD `f2f3655`
- 범위: **읽기 전용 분석. 원본 트레이스·기존 prep 스크립트 0-diff. GPU 미사용.**
- 신규 산출물 (분석·플롯 전용):
  - `scripts/char_traces3_yunuikang.py` — 3종 동일-규약 측정기
  - `scripts/plot_traces3_cdf_yunuikang.py` — 분포 오버레이 플롯
  - `figures/trace3_{context_cdf,tool_cdf,turns_hist,panels}_yunuikang.png`
- 재현:
  ```
  python3 scripts/char_traces3_yunuikang.py --out <json> --npz <npz>
  python3 scripts/plot_traces3_cdf_yunuikang.py --npz <npz>
  ```
- 라벨: **[측정]** 본 턴 직접 계산 · **[교차검증]** 기존 문서와 대조 · **[추론]** 해석

---

## 0. 한 눈 요약

| | **원본 full** | **Track M (현재 사용)** | **fit32k (7월 초 컷)** |
|---|---|---|---|
| 파일 | `tracelab_trace_full.jsonl` | `tracelab_moriM_L64k_yunuikang.jsonl` | `tracelab_fit32k.jsonl` |
| 가공 | 없음 (cap 없음) | turn-window(L=64k) + human-wait 주입 + CAP 300s | max-input 32,768 **세션 드롭** + cap 30s |
| 세션 / 턴 | **4,265 / 357,161** | **3,514 / 117,257** | **982 / 6,107** |
| 보존율 (vs full) | — | 세션 82.4% / 턴 32.8% | 세션 23.0% / **턴 1.71%** |
| 전이/세션 median | 1 | **4** | **0** |
| 세션 ι mean | 0.345 | **0.554** | 0.292 |
| 판정 | ★ 원본. tail·전이 모두 보존 | ★ 중반부 전이·idle 창 **증폭** | ✕ tail·전이 **모두 파괴** |

**핵심 [추론]**: fit32k 는 "컨텍스트를 줄이는" 컷이 아니라 **턴의 98.3%를 버리는** 컷이었다
(세션 단위 드롭이므로 긴 세션이 통째로 사라진다). 그 결과 전이 median 이 0 이 되어
busy↔idle 전환을 전제로 하는 스케줄러 실험 자체가 불가능하다.
Track M 은 반대로 턴을 33% 보존하면서 **전이 median 을 1 → 4 로 올렸다** —
이는 turn-window 슬라이싱이 아니라 **human-wait 주입**이 만든 효과다(§4).

---

## 1. 측정 규약 (3종 전부 동일 적용)

공정 비교를 위해 세 파일에 **완전히 같은 규약**을 적용했다. [측정]

| 항목 | 정의 | 근거 |
|---|---|---|
| 스키마 | `{session_id, turn, input_tokens, output_tokens, tool_duration_s, cached_tokens}` | 3종 전부 **동일 6키**, 결측 0 (전수 스캔 확인) |
| `uncached_input` | `max(input_tokens - cached_tokens, 0)` | **파일에 없어 파생.** 원본 gz 의 `claude_uncached_input_tokens` 는 emit 시 버려짐 |
| `T_acting`(턴) | `tool_duration_s` | — |
| `T_reasoning`(턴) | `uncached_input/8000 + output_tokens/152` [s] | `prep_tracelab_mori_yunuikang.py:57-58` 와 동일 상수 |
| ι | `T_acting / (T_acting + T_reasoning)` | `ThunderAgent/scheduler/mori_idleness.py` |
| busy/idle 라벨 | `tool_duration_s > 2.0s` | `LONG_THRESH` |
| 전이 | 라벨 변화 횟수 / 세션 | `prep_...:482 transitions_median()` |
| 윈도우 ι(k=5) | 최근 5턴 rolling | `IdlenessWindow(k=5)` 와 동일 정의 |

> ⚠️ 단서 1 [측정]: **디코드 상수 152 vs 145.** 코드 실측값은 `REASON_DECODE = 152.0`(goguma6/SGLang)인데
> `moriM_L64k_yunuikang.meta.json` 은 `"uncached/8000 + output/145"` 문자열을 하드코딩해 **meta 쪽이 stale**이다
> (`prep_...:757`). 본 표는 **152 기준**이며, §2 에 145 기준 감도도 함께 싣는다 (ι 계열만 영향, 그 외 지표는 무관).

> ⚠️ 단서 2 [측정]: **마지막 턴 zero 강제는 3종 공통 아티팩트.** 세 파일 모두 각 세션 마지막 턴의
> `tool_duration_s` 를 0.0 으로 강제한다(`prep_tracelab_yunuikang.py:118`, `prep_...mori...:236-248`).
> 따라서 zero-tool 비율은 **raw / 마지막턴 제외** 두 가지로 모두 보고한다.

> ⚠️ 단서 3 [측정]: `uncached` 를 `input - cached` 로 파생했기 때문에 ι 는 원본 gz 의 실제
> uncached 필드를 쓴 meta 값과 미세하게 다르다 (Track M: 본 측정 ι-IQR 0.696 vs meta 0.692).
> **전이 median 은 프록시와 무관하게 robust** 하므로 판정 근거로는 전이를 우선한다.

---

## 2. 3열 비교 표 (본체)

### 2-1. 규모 · 세션 구조 [측정]

| 지표 | 원본 full | Track M | fit32k |
|---|---|---|---|
| 파일 크기 | 60.6 MB | 21.0 MB | 1.01 MB |
| md5 | `c6bf9e0b17b4d0c9…` | `dd2c679ad7563352…` | `348e089be4ea03df…` |
| mtime (KST) | 2026-07-03 15:08 | **2026-07-31 01:44** | 2026-07-03 15:15 |
| **세션(프로그램) 수** | **4,265** | **3,514** | **982** |
| **총 turn 수** | **357,161** | **117,257** | **6,107** |
| 세션당 turn min / p10 / p25 | 1 / 1 / 6 | **4** / 6 / 11 | 1 / 1 / 1 |
| **세션당 turn median** | **17** | **21** | **4** |
| 세션당 turn p75 / p90 / p99 | 51 / 157 / 1,176 | 47 / 75 / 148 | 8 / 15 / 32 |
| 세션당 turn max / mean | **7,610** / 83.7 | 512 / 33.4 | 81 / 6.2 |

> `--min-turns 4` 때문에 Track M 의 세션당 turn 최소가 4 다 (751 세션이 이 조건으로 제외). [측정]

### 2-2. 컨텍스트 길이 [측정]

per-turn `input_tokens` 분포:

| 지표 | 원본 full | Track M | fit32k |
|---|---|---|---|
| min | 0 | **4,096** (SEED) | 402 |
| p10 | 38,900 | 7,610 | 7,717 |
| p25 | 71,130 | 16,560 | 13,230 |
| **p50** | **124,018** | **32,376** | **18,275** |
| p75 | 186,200 | 48,670 | 23,280 |
| p90 | 256,800 | 58,610 | 27,450 |
| p99 | 822,900 | 64,750 | 31,670 |
| max | **999,888** | **65,536** (L) | **32,753** |
| mean | 153,708 | 32,819 | 18,002 |

세션 peak context 분포:

| 지표 | 원본 full | Track M | fit32k |
|---|---|---|---|
| p10 / p25 | 19,580 / 35,580 | 15,920 / 32,020 | 9,154 / 14,760 |
| **p50** | **67,572** | **54,986** | **20,914** |
| p75 / p90 / p99 | 132,400 / 224,200 / 418,300 | 64,250 / 65,240 / 65,520 | 26,470 / 30,380 / 32,570 |
| max | **999,888** | **65,536** | **32,753** |

> [교차검증] full ctx median **124,018** = `logs/2026-07-03_EXPERIMENT_LOG_hetero_yunuikang.md` §B-6 값과 **정확 일치**.
> Track M **32,376** = `logs/2026-08-05_H200_PREREG_yunuikang.md` 의 `FIT_DEN` 과 **정확 일치**.
> fit32k **18,275** = 같은 로그 Phase D-char 값과 **정확 일치**.

### 2-3. 시간 · 툴콜 [측정]

| 지표 | 원본 full | Track M | fit32k |
|---|---|---|---|
| **tool_s P50** | 0.169 | 0.195 | **0.047** |
| **tool_s P90** | 10.008 | 30.011 | 9.984 |
| **tool_s P99** | 180.9 | **300 (cap)** | **30 (cap)** |
| tool_s P99.9 | 971.3 | 300 | 30 |
| **tool_s max** | **154,088.9** (≈42.8 h) | 300 | 30 |
| tool_s mean | 16.00 | 17.04 | 3.13 |
| **세션 wall median** (툴+추론) | 108.5 s | **247.4 s** | 20.8 s |
| 세션 wall p90 / max | 2,123 s / 344,000 s | 1,742 s / 28,810 s | 97.6 s / 293 s |
| **툴콜 시간 점유율** | 78.97% | **84.36%** | **53.90%** |
| **zero-tool turn % (raw)** | 13.56% | 11.01% | **31.72%** |
| zero-tool turn % (마지막턴 제외) | 12.51% | 8.26% | 18.63% |
| **긴콜(>2s) 턴 비율** | 22.02% | **28.22%** | 19.85% |
| **긴콜의 tool-time 점유** | 98.54% | 98.82% | 95.88% |

### 2-4. phase 전이 · idleness [측정]

| 지표 | 원본 full | Track M | fit32k |
|---|---|---|---|
| **전이/세션 median** | **1** | **4** | **0** |
| 전이/세션 mean | 17.56 | 8.41 | 0.89 |
| 전이/세션 p75 / p90 / max | 9 / 32 / 1,884 | 12 / 22 / 280 | 1 / 2 / 14 |
| **세션 ι mean** | 0.345 | **0.554** | 0.292 |
| 세션 ι median | 0.222 | 0.678 | 0.067 |
| **세션 ι-IQR** | 0.622 | **0.696** | 0.660 |
| **윈도우 ι(k=5) busy(<0.2) %** | 49.04% | **36.06%** | 56.59% |
| **윈도우 ι(k=5) idle(>0.8) %** | 19.53% | **34.78%** | 17.21% |
| 윈도우 ι median | 0.212 | 0.490 | 0.129 |
| **동시점 ι-IQR** (k=8 슬롯 시뮬) | 0.297 | **0.126** | 0.800 |

**145 기준 감도** (§C-1 원본 규약, ι 계열만 해당) [측정]:

| | full | Track M | fit32k |
|---|---|---|---|
| 세션 ι mean (145 / 152) | 0.341 / 0.345 | 0.549 / 0.554 | 0.289 / 0.292 |
| 윈도우 busy% (145 / 152) | 49.57 / 49.04 | 36.47 / 36.06 | 56.93 / 56.59 |
| 윈도우 idle% (145 / 152) | 19.15 / 19.53 | 34.30 / 34.78 | 16.83 / 17.21 |

> [교차검증] **145 기준 결과가 계획서 §C-1 특성표를 재현한다**:
> full ι mean 0.341 (§C-1: 0.341) · busy 49.57% (49.6%) · idle 19.15% (19.2%) · 전이 mean 17.56 (17.6);
> fit32k ι mean 0.289 (0.289) · busy 56.93% (56.9%) · idle 16.83% (16.8%) · 전이 mean 0.894 (0.9);
> full tool P50/P90/P99/P99.9/max = 0.169/10.008/180.9/971.3/154,089 — **전항 일치**.
> Track M 은 meta 와 대조: 전이 median 4.0 ✅ · 전이 mean 8.411 ✅ · long_pct 28.22 ✅ ·
> long-time-share 98.82 (meta 98.817) ✅ · tool mean 17.04 ✅ · peak max 65,536 ✅.
> **→ 신규 측정기가 기존 두 계보를 모두 재현하므로 3열 수치를 그대로 신뢰 가능.**
>
> 단 §C-1 의 "전이/세션" 열은 **median 이 아니라 mean** 이다 (본 표는 둘 다 싣는다).

---

## 3. 각 가공이 무엇을 보존/파괴했나

### full → fit32k (cap 30s + max-input 세션 드롭) — **파괴적** [추론]

> **한 줄: 컨텍스트를 32k 로 맞추려다 턴의 98.3%와 busy↔idle 전이를 통째로 잃었다.**

- **세션 4,265 → 982 (23.0%), 턴 357,161 → 6,107 (1.71%).** 세션 단위 드롭이라
  "어느 한 턴이라도 32,768 초과"면 세션 전체가 사라진다 → **긴 세션이 선택적으로 전멸**.
  세션당 turn median 17 → **4**.
- **전이 median 1 → 0, mean 17.56 → 0.89 (−94.9%).** 세션 절반 이상이 전이 0회 →
  스케줄러가 관측할 상태 변화 자체가 없다.
- **tail 파괴**: tool_s max 154,089 s → 30 s, P99 180.9 → 30 (cap 에 붙음).
  긴콜 tool-time 점유는 98.5% → 95.9% 로 남았지만, **긴콜의 절대 길이가 30s 로 잘려**
  demotion 이득이 나올 구간이 사라졌다.
- **툴 시간 점유율 79.0% → 53.9%**: idle-heavy 워크로드가 아니게 됐다. zero-tool 턴이 31.7% 로 급증.
- 유일한 보존: 컨텍스트가 vLLM `--max-model-len 32768` 에 맞는다 (애초의 목적).

### full → Track M (turn-window + human-wait 주입 + CAP 300s) — **중반부 보존 + idle 증폭** [추론]

> **한 줄: 세션 82%·턴 33%를 남기면서 컨텍스트를 64k 로 접고, human-wait 을 주입해 전이를 1 → 4 로 올렸다.**

- **보존**: 세션 4,265 → 3,514 (82.4%), 턴 → 117,257 (**32.8%** — fit32k 의 19배).
  세션당 turn median 17 → **21** (오히려 증가: `min_turns 4` 로 1-턴 세션을 걸러서).
  fit32k 처럼 세션을 버리는 대신 **각 세션의 연속 구간(window)을 잘라내 중반부를 살렸다.**
- **컨텍스트 재기준화**: prefix 절단이 아니라 window 최솟값 기준 rebase(SEED=4096) →
  ctx median 124k → 32,376, peak ≤ 65,536 **엄격 준수**. 누적 컨텍스트 증가 패턴은 유지.
- **추가된 것 = human-wait**: 9,829 턴에 실제 측정된 사람 대기시간이 `tool_duration_s` 에 가산됐다
  (≥12h 갭 92건 제외). `_nohw` 동일-세션 ablation 과 직접 대조 [측정]:

  | | Track M (primary) | `_nohw` ablation | 차이 |
  |---|---|---|---|
  | 세션 / 턴 | 3,514 / 117,257 | **동일** | — |
  | **전이 median** | **4.0** | **2.0** | **human-wait 이 2배로** |
  | 전이 mean | 8.41 | 6.18 | +36% |
  | 세션 ι mean | 0.554 | 0.387 | +0.167 |
  | 총 acting 시간 | 1,998,282 s | 775,076 s | **human-wait 이 61.2%** |
  | tool P50 / P90 | 0.195 / 30.01 | 0.123 / 6.66 | — |

  **→ 전이 median ≥ 4 게이트를 통과시킨 것은 turn-window 가 아니라 human-wait 주입이다.** [측정]
- **idle 창 확대**: 윈도우 ι idle(>0.8) 19.5% → **34.8%**, busy(<0.2) 49.0% → **36.1%**.
  세션 ι mean 0.345 → 0.554 로 idle-heavy 쪽으로 이동.
- **잃은 것**: tail. tool_s max 154,089 → 300 (CAP_HARD), P99 180.9 → 300 에 붙음.
  전이 mean 은 17.56 → 8.41 로 절반 (세션이 512턴에서 잘리므로 총 전이 횟수 자체는 감소).
  즉 **전이의 "밀도"(median)는 올랐지만 "총량"(mean·max)은 줄었다.**

> ⚠️ [측정] **동시점 ι-IQR 은 Track M 이 가장 낮다 (0.126, full 0.297, fit32k 0.800).**
> Track M 이 idle-heavy 로 균질화된 결과로, meta 도 이 값을 0.1175 로 기록하며
> "time-domination biased, 참고용" 이라 단서를 달았다. **세션 ι-IQR(0.696)이 게이트 근거**이고
> 동시점 값은 보조 지표다 — 두 지표가 반대 방향을 가리키므로 인용 시 반드시 구분할 것.

---

## 4. 분포 그림

`figures/trace3_panels_yunuikang.png` (1×3 통합) 및 개별 파일
`trace3_context_cdf_yunuikang.png` · `trace3_tool_cdf_yunuikang.png` · `trace3_turns_hist_yunuikang.png`.

3 데이터셋 오버레이. 읽는 법 [측정]:

1. **컨텍스트 CDF** — 세 곡선이 서로 평행 이동. fit32k 는 32,753 에서, Track M 은 65,536 에서
   수직 절단(cap 이 만든 벽). full 만 10⁶ 까지 완만히 이어진다.
2. **툴콜 duration CDF** — 좌측 y-절편이 zero-tool 비율(full 13.6% / Track M 11.0% / fit32k 31.7%).
   우측에서 fit32k 는 30s, Track M 은 300s 에서 수직으로 서고, full 만 10⁵ s 까지 뻗는다.
   중앙 0.1–1 s 구간은 세 곡선이 거의 겹친다 → **짧은 콜의 모양은 가공이 건드리지 않았다.**
3. **세션당 turn 히스토그램** — fit32k 는 1–8턴에 25% 가 몰린 좌측 절벽,
   Track M 은 4턴 하한에서 10–60턴에 봉우리, full 은 7,610턴까지 이어지는 긴 꼬리.

> 플롯 규격: 팔레트 `#4A7FD0/#1E9E74/#B8860B` — dataviz `validate_palette.js` **6검사 전항 PASS**
> (light, surface `#fcfcfb`, 최악 인접쌍 protan ΔE 9.0 / normal ΔE 17.3), 시리즈별 마커 2차 인코딩 병행.
> turn 히스토그램은 turn 이 정수라 log 빈 폭이 1 미만이면 빗살 아티팩트가 생겨 **정수 경계로 유일화**했다.

---

## 5. 한계

- [측정] `uncached_input` 은 파생값(`input - cached`)이다. 원본 `syfi_coding_trace.jsonl.gz` 의
  `claude_uncached_input_tokens` 를 쓰면 ι 가 소폭 달라진다 (Track M ι-IQR 0.696 vs meta 0.692).
- [측정] **툴콜 개수·타임스탬프·arrival time 은 세 파일 어디에도 없다.** `tool_duration_s` 는
  턴 단위 **집계**(병렬 콜은 wall span 으로 1회 계산)이므로 "툴콜 duration"은 엄밀히
  "턴당 툴 구간 길이"다. per-call 분해가 필요하면 원본 gz 로 돌아가야 한다.
- [측정] Track M 의 `tool_duration_s` 에는 human-wait 이 **섞여 있어 분리 불가**하다.
  본 보고의 분리는 `_nohw` ablation 과의 차분으로만 가능했다.
- [추론] `T_reasoning` 은 프록시다. 세 데이터셋에 **동일 상수**를 적용했으므로 *상대 비교*는
  타당하나, ι 의 절대값은 잠정이다. 전이 median 은 프록시와 무관.
