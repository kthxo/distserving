# 연구 계획 — overcommit 노브(조건1) × 듀티 통제 합성(조건2)로 idle↔recompute 트레이드오프 정량화

> 작성: 강윤의 · 브랜치 `yunuikang/thunderagent` · **2026-07-19** · **플랜만(실행·구현 전 검토 대기)**
> 서버: **nutella1**(143.248.247.92, 진행중 트랙 점유) + **goguma(2×5090, 이번 신규 트랙 후보, 접근 미확인)** · 저장소: `/home/yunuikang/yunuikang_work/distserving`
> 전제 문서(먼저 읽음):
> - `../logs/2026-07-16_TP2_RESULTS_yunuikang.md` — **P1 결과**: k_fit-flip 입증(4090 R<1 패 → Pro6000 R≥1 승), fit=KV풀/입력크기가 붕괴 임계 결정(TraceLab fit~25→C=32 붕괴, SWE fit~58→C=64 붕괴), R모델 Pearson r=0.982, KV 실측 456,944 tok, SYS 1.73×.
> - `../logs/2026-07-17_VLLM_PROFILING_yunuikang.md` — **✅ 재확인(원문 대조 완료)**. 이 plan이 쓰는 핵심 수치: **R = k_fit·d ≈ mean num_requests_running**(§1-1), **U 삼각측량 견고**(proxy≈nrr≈nvidia-smi, r=0.999, §4-3), **hit 오염 비대칭**(default 4.81~26배 팽창, tr 1.0배 정확 → 참 hit는 `local_compute` 카운터로만, §1-2·7-B-5), **prefill cold 2.72s·warm 0.46s·decode 5,896 tok/s(r²=0.981)·미스 한계비용 2.26s/turn**(§2-3), **닫힌 throughput 모델 `thr ∝ U/W`(참 hit 대입 시 오차 1.4%)**(§7-B-5), **batch-token 교란**(<70GiB→2048/256, ≥70GiB→8192/1024, §1-5·7-B-1), **pause heavy-tail**(p50=0·p99=522s, 평균 18.5s는 착시, §7-B-4b). → **STEP 4 캘리브레이션·STEP 6 모델의 1차 근거**.
> - `../logs/2026-07-06_MECHANISM_REFERENCE_yunuikang.md` — cost model·policy↔코드(파일:라인). STEP 3 주입점의 권위 근거.
> - `../plans/2026-07-15_PLAN_pro6000-tp-rescale_yunuikang.md` — 형식·게이트 구조·정직성 톤의 기준 문서.
> 진행중 별도 트랙(참조·무간섭): `../logs/2026-07-18_P3_HLE_RESULTS_yunuikang.md`, `../logs/2026-07-17_P2_SCIENCE_RESULTS_yunuikang.md`.
> **원칙: 한 번에 한 변수만. 기존 스크립트/버그픽스 재사용·불파괴. plan 단계에선 `scheduler/router.py` 미수정 — 조건1 구현은 STEP 3 승인 후 격리 브랜치/복사본에서만.**

---

## 0. 한 문단 요약 (연구 목표)

ThunderAgent(`tr`)는 스래싱을 절대 안 내려고 pause만 해서(recompute만 고려) GPU가 놀고, vLLM(`default`)은 pause 없이 다 넣어(idle만 고려) recompute를 감수한다. 결국 이것은 **idle vs recompute 트레이드오프**이고, 그 사이를 잘 스케줄링하는 것이 과제다. 이 plan은 (a) 그 트레이드오프가 사는 영역을 **R_cap = fit×d < 1** 하나의 수치 기준으로 정의·검증하고(4090 인공물이 아니라 일반 문제임을 격자로 증명), (b) 그 사이를 잇는 **연속 노브 `--capacity-overcommit-factor f`**(f=1→tr, f→∞→default)를 tr에 넣어, (c) **E2E를 고정한 채 듀티만 바꾼** 합성 워크로드로 f·C를 스윕해 **두 baseline(tr·default)을 동시에 이기는 내부 최적점 f\*와 개선 여지(room for improvement)**를 정량화한다.

---

## 1. 배경 근거 (P1에서 확정된 사실 — 재검토 없이 반영)

| 확정 사실 | 근거 |
|-----------|------|
| **붕괴 임계 = fit = KV_pool / program_input** (프로그램 크기만 다르면 같은 HW에서도 임계 이동) | TP2_RESULTS §P1-3 (TraceLab fit~25→C=32 붕괴, SWE fit~58→C=64 붕괴) |
| **R = k_fit×d ≈ mean num_requests_running**, U=P(nrr≥1)≈min(R,1) — R은 추상지표가 아니라 **동시에 GPU 일을 원하는 요청 수의 기댓값**(물리적 의미 확정) | TP2_RESULTS §P1-4 r=0.982; VLLM_PROFILING §1-1 |
| **실제 GPU 배치는 정책 무관 1.1~1.5 고정** — "GPU를 채운다"는 배치 키우기가 아니라 **시간축의 bubble 메우기**. overcommit의 이득은 U↑(놀던 시간 회수)로 들어옴 | VLLM_PROFILING §1-1, §2-1 |
| tr의 pause는 k_fit를 fit 이하로 억제 → default 붕괴(**참 hit 0.18**) 구간에서 tr 승(**참 hit 0.70**). ※보고 hit는 오염(§아래) → **참 hit는 `local_compute`로만** | TP2_RESULTS §P1-1,3; VLLM_PROFILING §7-B-5 |
| **닫힌 throughput 모델**: `thr ∝ U/W`, `W = input·(1−hit)/5896 + out/decode` — 참 hit 대입 시 tr/default 비 예측 오차 **1.4%**. STEP 6의 검증된 뼈대 | VLLM_PROFILING §7-B-5 |
| **정직 caveat**: Pro6000에선 전 셀 R>1 → U 포화 → tr 우위는 occupancy가 아니라 **KV hit/goodput**. fit×d<1 영역(저듀티)에서만 U가 진짜 여유를 가짐 → 이번 plan이 그 영역을 겨냥 | TP2_RESULTS §P1-4 |
| **pause는 heavy-tail**(p50=0·p99=522s, 평균 18.5s는 소수 파국이 만든 착시) → tr의 진짜 약점은 평균 idle이 아니라 **p95 latency** | VLLM_PROFILING §7-B-4b |
| overcommit 노브 주입점 4곳 + 5-홉 배선 (아래 STEP 3) | MECHANISM_REFERENCE + 코드 실측(이전 확인) |

**이 plan의 신규 각도**: P1은 fit(KV확대)로 tr을 이기게 만들었다. 이번엔 fit×d<1 영역(tr이 스래싱 없이도 GPU를 못 채우는 곳)을 **일부러 겨냥**해, 그 안에서 overcommit로 idle을 줄여 **tr·default 둘 다를 이기는 중간점**이 있는지를 본다.

---

## 2. STEP 2 — 트레이드오프 영역은 현실적인가 (4090 인공물 반박) 【GPU 불필요·지금 가능】

### 2-0. 이 STEP이 답하는 질문
> **"tr이 TraceLab에서 진 게 4090 특수현상이냐, 일반 문제냐?"**
트레이드오프 영역(idle↔recompute)이 **발생하는 조건을 하나의 부등식으로 정의**하고, 그 영역이 **현실 하드웨어·워크로드 좌표에서 얼마나 흔한지**를 계산으로 보인다. GPU 없이 계산·플롯만.

### 2-1. 경계 — 단 하나의 수: **fit × d < 1**
- **경계식**: `fit × d < 1  ⇔  fit < NEED(=1/d)`.
- **왜 이게 경계인가(직관)**:
  - **fit×d ≥ 1** (fit ≥ NEED): tr이 **스래싱 없이도** GPU를 포화시킬 만큼 프로그램을 적재할 수 있다 → pause로 충분, **트레이드오프 없음**(tr 지배). overcommit은 스래싱만 추가.
  - **fit×d < 1** (fit < NEED): 물리적으로 다 적재해도(무-스래싱) GPU가 논다 → idle을 줄이려면 **fit을 넘겨 적재(overcommit)** 해야 하고 그 대가가 recompute → **idle↔recompute 트레이드오프가 살아있는 영역**. tr(pause만)은 여기서 진다.
- 즉 **fit×d는 "스래싱 없이 얻을 수 있는 GPU 수요의 최대치"**이고, 그게 1 미만이면 정책과 무관하게 GPU가 구조적으로 논다.

### 2-2. 구성요소 표 (각 값의 출처 명시)
| 기호 | 정의 | 단위 | 출처 |
|------|------|------|------|
| **d** (duty) | reasoning /(reasoning+tool) 시간비 | 무차원 | **측정**(c=1 프로파일: 4090 TraceLab 0.196, Pro6000 TraceLab 0.289, SWE 0.996) |
| **ctx** (프로그램KV) | 프로그램당 평균 KV 점유 ≈ 입력 median tok | tok | **측정**(TraceLab 18,684 / SWE 7,897) |
| **C_total** (KV풀) | `block_size × num_gpu_blocks` = 백엔드 KV 용량 | tok | **측정 2셀**(4090 43,888 / Pro6000 456,944), 나머지는 **추정**식(§2-4) |
| **fit** | `C_total / ctx` = 무-스래싱 최대 적재 수 | 무차원 | 파생 |
| **fit×d (=R_cap)** | 무-스래싱으로 얻는 R의 최대치 | 무차원 | 파생 |

### 2-3. 측정 4셀 검증 (fit×d ≷ 1 로 실제 승패 100% 일치)
| 셀 | HW/모델 | C_total(tok) | ctx(입력) | fit | d | **fit×d** | 실측 승패 | 경계 정합 |
|----|---------|--------------|-----------|-----|-----|-----------|-----------|-----------|
| TraceLab | 4090/8B | 43,888 | 18,684 | ~2.35 | 0.196 | **0.46** | **tr 패**(−34%) | <1 ✅ |
| SWE | 4090/8B | 43,888 | 7,897 | ~5.56 | 0.996 | **5.54** | tr 승(+78~84%) | ≥1 ✅ |
| TraceLab | Pro6000/32B | 456,944 | 18,684 | ~24.5 | 0.289 | **7.07** | tr 승(+80~87%) | ≥1 ✅ |
| SWE | Pro6000/32B | 456,944 | 7,897 | ~57.9 | 0.996 | **57.6** | tr 승(+113%) | ≥1 ✅ |
- **결론**: tr이 진 유일 셀(4090 TraceLab)이 유일하게 fit×d<1. 경계가 4셀 전부에서 승패를 가른다 → **fit×d<1이 트레이드오프 영역의 운영 정의로 타당**.
- **[추가 예정]** HLE·Science는 측정 완료 시 이 검증표에 행 추가(§2-5 placeholder 참조).

### 2-4. 격자 계산 (money figure)
- **격자**: (GPU/모델 → C_total) × (워크로드 → d, ctx).
  - C_total 추정식: `(GPU메모리 × util − weights) / (모델 KV bytes/token)`. **측정 2셀(4090 43,888 / Pro6000 456,944)로 검산** 후 나머지 셀 추정.
  - GPU 후보: **4090 · 5090 · Pro6000 · A100 · H100 · 8×H100(논문)**.
  - 워크로드: 우리 4종 + **저듀티/롱컨텍스트 에이전트 클래스**(deep-research류: d 낮고 ctx 큼).
- **보여줄 결론**: fit×d<1은 (저듀티) 또는 (긴 컨텍스트) 또는 (작은 KV) **중 하나만 세게 밀어도 진입** → **데이터센터 GPU(A100/H100)라도 저듀티 에이전트면 진입** → **4090 전용 인공물이 아니라 일반 문제**.
- **머니 피겨**: (d, fit) 평면에 **fit×d=1 쌍곡선** + 실제 시스템 점(4셀 + 격자 셀) 오버레이. 쌍곡선 아래(<1) = 트레이드오프 영역.

### 2-5. 워크로드 목록 — HLE·Science placeholder (데이터 미비, 구조만)
| 워크로드 | d | ctx | fit×d | 상태 |
|----------|-----|-----|-------|------|
| TraceLab | 0.196 / 0.289 | 18,684 | (§2-3) | ✅ 측정 완료 |
| SWE | 0.996 | 7,897 | (§2-3) | ✅ 측정 완료 |
| **HLE** | **TBD** | **TBD** | **TBD** | **duty는 P3 24h 녹화→tool 지연에서 산출 예정(수집 중)** |
| **Science** | **TBD** | **TBD** | **TBD** | **데이터 blocker로 미수집(보류)** |
| deep-research류(저듀티/롱컨텍스트) | 낮음(가정) | 큼(가정) | 격자 산출 | 대표 클래스(가정값) |
- 데이터가 생기면 위 빈 행을 채우고(§2-3 검증표에도 행 추가), 격자 CSV에는 **placeholder(NaN)** 행으로 지금부터 포함.

### 2-6. ★ R vs R_cap 관계 + "R을 올리는 두 레버" (STEP 2→3~6 논리 다리)
- **승패를 결정하는 것은 R = k_fit × d** (P1에서 r=0.982로 검증, 4셀 fit×d 정합과 일관).
- **R은 두 인자(레버)의 곱** — 합이 아니라 **곱**:
  - **A = k_fit** (실제 적재 수, **정책이 통제**) × **B = d** (듀티, **워크로드 특성**).
- **R_cap = fit × d = 스래싱 없이 얻는 R의 최대치.** k_fit ≤ fit 이므로 **무-스래싱에선 R ≤ R_cap**. 따라서 **R_cap<1이면 무-스래싱으로는 R<1 강제 → GPU 필연 idle**.
  - ※ 이 상계 `R ≤ R_cap`는 **tr(f=1)에서만 참**이다. overcommit(조건1)은 **k_fit을 fit 위로 올려 R을 R_cap 위로 미는 것**이 핵심 — 상계를 의도적으로 깨서 idle을 회수한다.
- **R<1 → R≥1로 올리는 두 레버**:
  - **레버 A(k_fit)↑ = overcommit(조건1의 f)**: k_fit을 fit 위로 → R을 R_cap 위로. 단 **fit 초과분은 스래싱(recompute)**. 포화(R=1)에 필요한 계수 **f ≈ 1/(fit×d) = 1/R_cap**(재프리필 무시 시 상한). 예: 4090 TraceLab R_cap=0.46 → **f≈2.2**. 실제 최적 **f\*는 그 이하** — recompute와의 균형에서 결정.
  - **레버 B(d)↑ = 워크로드 듀티**(조건2로 통제·연구).
- **→ 조건1 = k_fit 레버, 조건2 = d 레버.** fit×d<1 영역에서 idle을 회수하되 스래싱을 감수하는 **최적점 f\***를 찾는 것이 STEP 3~6. (이 소절이 STEP 2→3~6의 논리 다리)

### 2-7. 3~6 다리 — idle benefit vs recompute cost (직관 요약; 상세는 STEP 6)
- **k_fit을 1 더 올릴 때**:
  - **idle benefit ≈ d 만큼 점유↑**(포화 전까지 놀던 시간 회수).
  - **recompute cost ≈ ctx × P(miss) / prefill_rate** — 실측값: 미스 한계비용 **2.26 s/turn**, prefill **5,896 tok/s**(VLLM_PROFILING §2-3).
- **둘이 같아지는 지점 = 최적 overcommit f\*.** tr(f=1, overcommit 0)·default(f=∞, full)는 **양 끝**, 최적은 **중간 = room for improvement.** (닫힌식 `thr∝U/W`로 STEP 6에서 정량화.)

### 2-8. 가정 (정직)
- C_total 추정식은 weights·overhead를 단순화 → **측정 2셀로 검산**(오차 시 계수 보정). 미측정 GPU/모델 셀은 추정치임을 표기.
- ctx = 입력 median 근사(실제 KV는 prefix 공유·shared_tokens로 변동) → fit은 **차수(order) 판정용**, 정밀 임계 아님.
- d는 c=1 고유값(부하 하 변동, §4-2) → 격자는 워크로드 **성격 분류**용.

### 2-9. 산출물
- `scripts/compute_fitd_grid_yunuikang.py`(신규), `scratch/step2/fitd_grid_yunuikang.csv`(HLE·Science NaN 행 포함), `figures/step2_fitd_hyperbola_yunuikang.png`(쌍곡선+시스템 점).
- 결과 로그 `logs/2026-07-19_STEPS_RESULTS_yunuikang.md`(STEP 2 섹션; 이후 STEP 5/6 append).
- **GPU 불필요**(계산·플롯만).

### ★ 게이트 A — STEP 2 완료 후 정지
- 4셀 정합 표 + "포화 필요 f=1/R_cap" 열 + 격자 + 쌍곡선 그림 리뷰. **"트레이드오프 영역이 현실적/일반적"이 수용되면** STEP 3~6 진행 승인. 반증(격자가 전부 ≥1로 나와 영역이 비현실적)이면 연구 재프레이밍.

---

## 3. STEP 3 — 조건1: overcommit 노브를 tr에 추가 【GPU 필요(goguma) · 구현은 승인 후】

### 3-1. 노브 정의
- **`--capacity-overcommit-factor f`** (type=float, **default 1.0**). **margin = (f − 1) · C_total**.
- 의미: **f=1 → 기존 tr**(margin=0, 비트-동일 회귀 안전). **f→∞ → 사실상 default**(용량 무한 → pause 안 함, 다 적재). 이 노브 하나가 두 baseline을 잇는 **연속 축**.

### 3-2. ★ margin을 capacity 판정 **4곳 전부에 일관 적용** (이미 확정된 방향 — 재검토 없이 반영)
> 이전 확인에서 "pause만"으로 제안했으나, **연속축(tr↔default)을 만들려면 default가 용량제한이 아예 없으므로 용량 개념을 pause·resume·신규배정 전반에서 일관되게 완화**해야 한다. 그래서 **4곳 모두 `+margin`**. (배수를 C_total property에 곱하는 것과 다름 — §3-3.)

| # | 위치(파일:라인) | 함수 | 현재 | 주입 후 |
|---|-----------------|------|------|---------|
| 1 | `scheduler/router.py:770` | `_scheduled_check`(pause 트리거) | `remaining_capacity() < 0` | `remaining_capacity() + margin < 0` |
| 2 | `scheduler/router.py:780` | `_pause_until_safe`(pause 루프) | `while remaining_capacity() < 0` | `while remaining_capacity() + margin < 0` |
| 3 | `scheduler/router.py:835/837` | `_greedy_resume`(resume 용량) | `remaining = remaining_capacity[_with_decay]()` | `remaining = (...) + margin` |
| 4 | `scheduler/router.py:356` | `_select_backend_for_new_program`(신규배정) | `remaining_capacity() < required` | `remaining_capacity() + margin < required` |

- **margin 계산 위치**: 각 함수에서 `margin = (self.capacity_overcommit_factor - 1.0) * backend.cache_config.total_tokens_capacity` 로 backend별 산출(cache_config None 가드는 기존 그대로). 두 pause 지점(1,2)은 **동일 margin** 필수(트리거만 관대·루프만 엄격 시 실험 의도 붕괴).

### 3-3. ★ 금지·불변 (누수 방지 — 정직 포인트)
- **금지**: `cache_config.total_tokens_capacity` **property/C_total 자체를 부풀리지 말 것**. `calculate_shared_tokens`(`backend/vllm_metrics.py:307-311`)가 같은 값을 써서, C_total↑ → `vllm_actual_used`↑ → `shared_tokens`↓ → `used`↑ → **remaining_capacity↓(overcommit 역효과, pause 증가)**. → **반드시 각 비교 지점에서 `+margin` 형태로만**.
- **불변(안 건드리는 rubric)**: **pause 대상 선정**(작은 ACTING부터 → REASONING, `_pause_until_safe` 내부 정렬)·**decay 모양** `2^(-t)`·**BFD 배치**·**우선순위**(REASONING>NEW>ACTING)·**공정성 큐**(global_waiting_queue). 노브는 **용량 임계값(threshold)만 이동**시키고 **결정 로직(선정·정렬·순서)은 불변**.
- **회귀 안전**: default=1.0 → margin=0 → 4곳 전부 기존과 산술적으로 동일 → **비트-동일**.

### 3-4. CLI 배선 (기존 `--use-acting-token-decay`와 동형 5-홉 — 주입점만, 구현은 승인 후)
| 홉 | 파일:라인(현재) | 추가 내용 |
|----|-----------------|-----------|
| 1 | `__main__.py:32-33` 뒤 | `add_argument("--capacity-overcommit-factor", type=float, default=1.0, help=...)` |
| 2 | `__main__.py:50` 뒤 | `capacity_overcommit_factor=args.capacity_overcommit_factor` (Config 생성) |
| 3 | `config.py:29` 뒤 | `capacity_overcommit_factor: float = 1.0` 필드 |
| 4 | `app.py:246` 뒤 | `capacity_overcommit_factor=config.capacity_overcommit_factor` (Router 생성) |
| 5 | `scheduler/router.py:68` 파라미터 + `__init__`(75번대) | `capacity_overcommit_factor: float = 1.0` 파라미터 + `self.capacity_overcommit_factor = ...` |

### 3-5. 구현 가드레일·검증
- **격리**: 별도 브랜치(예 `yunuikang/overcommit`) 또는 격리 복사본. plan 단계에선 미수정.
- **회귀 테스트**: f=1로 `smoke_test_yunuikang.py` + TraceLab C=32 1런이 P1 tr 수치(thru 0.073±, hit 0.61±)와 일치 확인 → margin=0 무영향 입증.
- **연속성 스모크**: f=매우 큰 값(예 1e6)에서 tr이 default에 수렴(pause≈0, hit·thru≈default)하는지 1런.

### 3-6. 스윕 그리드(확정)
- **f ∈ {1.0, 1.25, 1.5, 2.0, 3.0, 5.0, ∞(=default 대조)}** — 1 근처 촘촘, 이후 성기게. (STEP 5에서 워크로드별 최적 근처 재세분.)

### ★ 게이트 B — STEP 3 구현·검증 후 정지
- f=1 비트-동일(회귀) + f→∞ default 수렴 스모크 통과 확인 후 STEP 5 스윕 승인.

---

## 4. STEP 4 — 조건2: 듀티를 통제한 합성 워크로드 【GPU 필요(goguma) · 설계는 지금 가능】

### 4-1. 설계 원칙 (이전 tool_scale 접근 폐기 이유)
- 이전 `tool_scale`은 tool 시간을 줄여 **전체 E2E를 단축** → throughput 상승이 자명(무의미). **이번엔 각 프로그램의 E2E latency를 고정**하고, 그 안에서 **acting:reasoning 비율(=duty d)만** 변화.
- **E2E 고정 정의**: 프로그램당 총 시간 `T = Σ(reasoning_time + tool_time)` 를 상수로 두고, `reasoning_time = d·T`, `tool_time = (1−d)·T`.

### 4-2. E2E 고정 + d 스윕 합성 방법
- **레버 2개**: (i) reasoning_time는 **입력/출력 토큰 프로파일**로 결정(모델 GPU 시간), (ii) tool_time은 **드라이버의 tool sleep**으로 결정.
- **캘리브레이션**(VLLM_PROFILING §2-3 실측값 사용): cold prefill = `1.696e-4×ptok − 0.450`(r²=0.981, 5,896 tok/s), warm prefill 0.46s, decode ~52 tok/s(c=1). 목표 turn당 reasoning_time `r`에 맞춰 입력/출력 토큰 역산, tool sleep = `r·(1−d)/d`. **turn 수·per-turn 크기를 함께 조정해 Σ가 고정 T가 되도록** 합성기가 풀이.
  - **⚠️ 부하 의존성(정직 caveat)**: 위 값은 **c=1 고유값**이다. 부하 하에서는 prefill_s(TTFT)에 **vLLM 큐 대기가 섞여** 급증한다(VLLM_PROFILING §7-B-5: default 부하 TTFT 10.79s vs c=1 warm 0.46s, ~9.5s가 큐 대기). 따라서 STEP 4 합성은 **GPU 시간(순 reasoning)** 기준으로 duty를 정의하고, 관측 E2E와의 괴리는 STEP 5 부하 하 재측정으로 교차검증(§4-2 게이트 C).
- **합성 산출**: 공통 스키마 JSONL(TraceLab replay와 동형) — 프로그램별 turn 리스트, 각 turn = (input_tokens, output_tokens, tool_sleep_s). d·C별 세트.

### 4-3. 드라이버 재사용/개작 범위
- **기존 `trace_replay_driver_expC` 재사용**(closed-loop, program_id·release 경로 그대로). 개작 = **tool sleep을 trace의 per-turn 값으로 주입**(이미 tool 지연 replay 지원 → 합성 trace가 그 필드를 채우면 됨, 드라이버 로직 변경 최소).
- 신규 **`synth_duty_trace_yunuikang.py`**: (d, T, C, turn 분포) → 합성 JSONL. **router.py 무관**.

### 4-4. 그리드
- **d 그리드**: **d ∈ {0.1, 0.2, 0.3, 0.5, 0.7, 0.9}** (fit×d<1 영역을 저듀티 쪽으로 충분히 덮음; goguma 5090 C_total로 fit 산출 후 fit×d=1 경계가 그리드 내부에 오도록 최종 확정 — STEP 4 스코핑).
- **C 그리드(프로그램 수)**: goguma fit 실측 후 `{fit/2, fit, 2·fit, 4·fit}` 근방으로 확정.
- **산출 그래프**: **비율(d)에 따른 그래프**, **프로그램 수(C)에 따른 그래프**(지시서 요구 2종).

### ★ 게이트 C — STEP 4 합성기·캘리브레이션 검증 후 정지
- 합성 trace 1세트를 c=1로 replay → **의도한 d가 실측 d와 ±5% 일치**(E2E 고정·duty 재현) 확인 후 STEP 5 승인.

---

## 5. STEP 5 — 조건1+2 핵심 스윕 【GPU 필요(goguma) · STEP 3+4 후】

### 5-1. 설계
- **조건2 합성 워크로드(여러 d) × 조건1 f-스윕 × C-스윕**. 정책=tr(f 스윕)+default(대조). REPEAT=3(에러바).
- 지표: **throughput(steps/min·programs/s)** · **KV hit**(참 hit는 §5-3) · **p95 latency** · **idle(U=1−idle_fraction)** · **R모델(k_fit·d)**.

### 5-2. ★ Falsifiable 가설 (반드시 명시)
- **(H1)** **fit×d<1 워크로드**(저듀티 d)에서는 **tr(f=1)·default(f=∞) 둘 다를 이기는 내부 최적 f\*가 존재**한다(1<f\*<∞). — idle을 조금 감수하지 않으면(tr) 놀고, 다 넣으면(default) 스래싱 → 중간이 최적.
- **(H2)** **fit×d≥1 워크로드**(고듀티/작은 프로그램)에서는 **f=1(tr)이 최선**이고 overcommit은 스래싱만 늘려 단조 손해(f\*=1).
- **반증 조건**: (H1) 어떤 저듀티 셀에서도 f\*가 경계(1 또는 ∞)에만 있으면 "중간 최적 없음" → overcommit 무용. (H2) 고듀티에서 f>1이 이득이면 모델 수정.

### 5-3. ★ 측정 프로토콜 (VLLM_PROFILING 계승 — 필수)
- **참 hit는 `vllm:prompt_tokens_by_source{source="local_compute"}`로만** 산출(불변식 `compute + cached == total` 확인). 보고 hit(hits/queries)은 **비대칭 오염**(default 최대 26배 팽창, tr 1.0배 — VLLM_PROFILING §1-2·7-B-5) → overcommit f를 키우면 스래싱↑로 오염이 f에 따라 변해 **보고 hit로는 f 비교가 왜곡됨**. 기존 `scripts/microbench_recompute_yunuikang.py`(/metrics 전후 스냅샷) 재사용.
- **`--stream` 필수**: 안 붙이면 `prefill_s`/`decode_s`가 0으로 미기록(VLLM_PROFILING §6-1). TTFT 분해(재프리필 vs 숨은 큐 대기)에 필요.
- **U는 3중 측정 병기**(proxy REASONING>0 · vLLM nrr>0 · nvidia-smi/100) — 삼각측량으로 견고성 확인(§4-3, r=0.999).
- **p95/pause는 분위수로**(p50·p95·p99) — 평균 pause는 heavy-tail 착시(§7-B-4b).

### 5-4. ★ batch-token 교란변수 통제 (신규 — VLLM_PROFILING §1-5)
- vLLM은 device mem **70GiB 경계**에서 기본값을 바꾼다: **<70GiB(4090 24G·5090 32G) → `max_num_batched_tokens=2048`/`max_num_seqs=256`**, **≥70GiB(Pro6000 96G) → 8192/1024**(실측 확정 §7-B-1).
- **함의**: goguma **5090(32GB)은 4090과 동일한 2048/256 레짐** → P1의 fit×d<1 관측(4090)과 **배치 예산이 일치** → overcommit 실험이 깨끗한 대조. 반대로 Pro6000 P1 결과와 절대 비교 시엔 배치 예산 차이를 감안.
- **통제**: 스윕 전 기동 로그에서 실제 `max_num_batched_tokens`/`max_num_seqs` 확인·고정(명시 플래그로 못박기). f 스윕은 이 값 고정 하에서만 유효(한 번에 한 변수).

### 5-5. 산출물
- `scratch/step5/synth_d{..}_f{..}_c{..}_{tr,default}.jsonl`, `step5_summary_yunuikang.csv`(참 hit·U 3종·pause 분위수 포함).
- `figures/step5_{throughput,hit,p95,U}_vs_f.png`(워크로드/ d별), `step5_optimal_f_vs_fitd.png`(★ f\* ↔ fit×d 관계 = 핵심 결과).

### ★ 게이트 D — STEP 5 완료 후 정지
- H1/H2 판정 표 + f\* 곡선 리뷰 후 STEP 6(분석) 승인.

---

## 6. STEP 6 — 분석: room for improvement 【GPU 불필요 · STEP 5 후】

### 6-1. ★ 검증된 닫힌 모델을 f의 함수로 (VLLM_PROFILING §7-B-5 뼈대 계승)
P1 프로파일링이 tr/default 두 점에서 **오차 1.4%로 닫은** 모델을 **f의 연속 함수**로 확장:
```
thr(f) ∝ U(f) / W(f)
  U(f) = min( R(f), 1 ),   R(f) = k_fit(f) · d          ← idle 측: f↑ → k_fit↑ → U↑ (1에서 포화)
  W(f) = input·(1 − hit_true(f)) / 5896  +  out / decode  ← recompute 측: f↑ → hit_true↓ → W↑
```
- **두 baseline은 이 곡선의 양 끝**: f=1(tr) = k_fit 최소·hit 최대 / f→∞(default) = k_fit 최대·hit 최소. `thr(f)`가 **내부 극대**를 가지면 그 정점이 f\*.
- **f\*의 1차 조건**: `d/df[U(f)] / U = d/df[W(f)] / W` — **marginal idle benefit(U 상승률) = marginal recompute cost(W 상승률)**. 이것이 idle↔recompute crossover의 정량 표현.
- **레짐 예측**(H1/H2와 정합): **U가 이미 1로 포화한 fit×d≥1**에서는 dU/df≈0 → 좌변 0 < 우변 → **f↑는 순손해 → f\*=1**(H2). **fit×d<1**에서는 U가 f로 실제 상승(dU/df>0) → 내부 crossover 존재 가능(H1).
- **입력**: k_fit(f)·hit_true(f)는 STEP 5 실측 곡선(참 hit는 `local_compute`). 5,896 tok/s·decode율은 §2-3 실측. **모델 예측 f\* vs STEP 5 실측 f\*** 대조로 타당성 검증.

### 6-2. 개선 여지(room for improvement) 견적
- **실측 상한**: `thr(f*) / max(thr(f=1), thr(f=∞))` — baseline 둘 다 대비 이득(%)을 워크로드/ fit×d별 표·그림.
- **이론 상한**: idle=0(U=1) ∧ recompute=0(hit=1) 이상적 스케줄러의 `thr_ideal`. `thr(f*)/thr_ideal` = 남은 gap → **정적 f 노브로 못 닫는 부분** = 향후 "적응형 f(부하·d 온라인 관측)" 연구의 정량 근거.
- **정직 caveat**: (i) STEP 5의 U와 참 hit를 **동일 런에서 함께 측정**(§7-B-5가 남긴 run-mix 한계 해소). (ii) heavy-tail pause(§7-B-4b) 때문에 throughput 이득과 p95 악화가 **동시에** 올 수 있음 → room 견적은 throughput 단독이 아니라 **(throughput, p95) 2목적**으로 병기.

### 6-3. 산출물
- `figures/step6_thr_vs_f_closedmodel.png`(모델곡선+실측점), `figures/step6_room_for_improvement.png`(f\* vs baseline·ideal), 결과 로그 **`logs/2026-07-19_STEPS_RESULTS_yunuikang.md`에 append**(STEP 2에서 신규 생성, STEP 5/6 이어 붙임 — 로그 통일).

---

## 7. 하드웨어 분배 (병렬화) 및 ★ 첫 스코핑 항목

### 7-1. 현황 (실측, nutella1)
| GPU | 카드 | 현재 점유 | 이 plan 가용? |
|-----|------|-----------|----------------|
| 0 | Pro5000 48G | **타 사용자**(VLLM EngineCore, ~46GB) | ❌ 미접촉 |
| 1 | Pro6000 96G | 내 `tp2serve`(Deployment A) | ❌(P2/P3 재사용 대기) |
| 2 | Pro6000 96G | 내 `tp2serve`(Deployment A) | ❌ |
→ **nutella1엔 이 실험용 여유 GPU 없음. 진행중 P2/P3(§7-3)와 시간대·자원 경합 → nutella1에서 신규 스윕 금지.**

### 7-2. ★ STEP 1(첫 스코핑) — goguma 접근·GPU 가용성·환경 확인 【최우선, GPU 실사용 전】
- **goguma(2×5090) SSH 접근** 가능한가 — 호스트/계정/키. **[사용자 제공 필요]**.
- `nvidia-smi`로 **2×5090 유휴 여부**, driver/CUDA, VRAM(각 32GB 추정).
- **환경 브링업**: venv/vLLM 재사용 가능한지(rsync or 재설치), Blackwell 여부(5090=sm_120, nutella1 절차 재사용 가능성).
- **5090 C_total 실측**: Qwen3-8B(또는 32B 적재 가능 여부) 기동 → `cache_config_info{num_gpu_blocks}` → fit 산출 → STEP 4 d·C 그리드 확정.
- **대안(goguma 불가 시)**: (a) nutella1에서 P2/P3 완전 종료 후 GPU1+2 시간대 분리 사용, (b) 4090 재사용(fit×d<1 자연 영역이라 오히려 적합할 수 있음 — 소모델로 저듀티 합성), (c) 다른 노드. **[사용자 결정]**.

### 7-3. 진행중 트랙 무간섭 (참조)
- **P2(Science)**: SharePoint password 데이터 blocker로 **보류**(P2_SCIENCE §A-2). **P3(HLE)**: GPU0 타사용자 + 사용자 제공항목(Z.ai키·HF HLE토큰·conda·FAISS) blocker로 **대기**(P3_HLE §A). 둘 다 nutella1 GPU1+2(tp2serve) 재사용 전제 → **이 plan은 goguma로 분리해 nutella1 자원·시간대를 건드리지 않음**. tp2serve 정지 여부는 P3 승인과 얽힘(사용자 결정, 이 plan과 독립).

---

## 8. 단계 의존성·순서·게이트

```
STEP 2 (fit×d 격자·쌍곡선) ──[게이트 A]── ┐         ← 지금 가능, GPU 불필요
STEP 1 (goguma 스코핑) ───────────────────┤         ← 지금 가능(사용자 접근 제공)
STEP 4 설계·합성기 (캘리브레이션) ─[게이트 C]┤         ← 설계 지금, 검증엔 goguma
STEP 3 (overcommit 구현·회귀) ──[게이트 B]─┤         ← goguma, 승인 후 구현
                                          ▼
STEP 5 (조건1+2 핵심 스윕) ──────────[게이트 D]── STEP 6 (분석·room)
```
- **지금 병행 가능**: STEP 2(계산), STEP 1(스코핑), STEP 4 **설계**(합성기 코드·캘리브레이션 수식).
- **goguma 확보 후**: STEP 4 검증(게이트 C) · STEP 3 구현(게이트 B).
- **STEP 5** = STEP 3 ∧ STEP 4 후. **STEP 6** = STEP 5 후.

---

## 9. 예상 소요 · 리스크 · 사용자 결정/제공 항목

### 9-1. 예상 소요 (±50%)
| STEP | 내용 | GPU? | 추정 |
|------|------|------|------|
| 1 | goguma 스코핑·브링업·C_total 실측 | 5090 소량 | 0.5–2h + 접근 대기 |
| 2 | fit×d 격자·쌍곡선 | ✗ | 2–4h |
| 3 | overcommit 구현(5-홉+4주입)·회귀·수렴 스모크 | 5090 소량 | 3–5h |
| 4 | 합성기·캘리브레이션·게이트C 검증 | 5090 소량 | 4–8h |
| 5 | 핵심 스윕(d 6 × f 7 × C 4 × 2정책 × R3) | 5090 다량 | **20–40h**(그리드 pruning 시 감소) |
| 6 | marginal 모델·room 견적·플롯 | ✗ | 3–5h |
- STEP 5는 그리드가 큼 → **게이트 D 전 파일럿(1 d × f 전체)로 f\* 대략 위치 잡고 본 스윕 pruning** 권장.

### 9-2. 리스크
1. **goguma 접근 불가/GPU 점유** → §7-2 대안(nutella1 P2/P3 종료 후, 4090 재사용). **최우선 스코핑으로 조기 발견**.
2. **E2E 고정 캘리브레이션의 부하 의존성**(부하 하 TTFT에 vLLM 큐 대기가 섞임, §7-B-5) → GPU시간 기준 duty 정의 + 게이트 C c=1 검증 + STEP 5 부하 하 교차확인, 정직 caveat.
3. **batch-token 레짐 교란**(§1-5): 5090은 2048/256(4090과 동일)이나 Pro6000 P1은 8192/1024 → **P1 절대수치와 직접 비교 금지**, 5090 내부 f 스윕은 배치값 고정 하에서만(§5-4).
4. **hit 지표 비대칭 오염**: 보고 hit로 f 비교 시 왜곡 → 반드시 `local_compute` 참 hit(§5-3). 누락 시 결론 무효.
5. **H1 반증**(내부 최적 f\* 없음) → 그 자체가 유효한 부정 결과(overcommit 무용 영역 규명). 정직 보고.
6. **5090(32GB) 소모델 fit이 작아** 저듀티라도 fit×d<1 만들기 위한 프로그램 크기 설계 필요 → STEP 4에서 입력 토큰↑로 fit↓ 조정.
7. **router.py 4곳 수정의 상호작용**(resume+신규배정에도 margin) → f→∞ 수렴 스모크로 회귀 검증(게이트 B).
8. **throughput↑ vs p95↑ 동시성**(heavy-tail pause, §7-B-4b) → room 견적을 2목적(throughput, p95)으로 병기(§6-2).

### 9-3. ★ 사용자 결정/제공 필요
- **(필수·최우선)** goguma 접근 정보(호스트·계정·키) 및 2×5090 사용 승인. 불가 시 대안 노드 결정(§7-2).
- **STEP 3 구현 착수 승인**(격리 브랜치에서 router.py 4곳 수정 — 게이트 B 전).
- STEP 5 그리드 규모(전체 vs 파일럿 후 pruning) 선호.
- tp2serve(nutella1) 정지 여부는 **이 plan과 독립**(P3 트랙 결정) — 이 plan은 무간섭 전제.

---

## 10. 가드레일 (전 단계 공통)
- **plan 단계**: `scheduler/router.py` **미수정**. STEP 3 구현은 게이트 B 승인 후 **별도 브랜치/격리 복사본**에서만, 4주입점(356·770·780·835/837) + 5-홉 배선으로 한정.
- 신규 파일은 **`*_yunuikang`** 접미사. 기존 스크립트/버그픽스 재사용·불파괴.
- **진행중 P2/P3 무간섭**: nutella1 GPU·시간대 미접촉, goguma로 분리(§7). GPU0(타 사용자) 절대 미접촉.
- **한 번에 한 변수**: STEP 3(노브)와 STEP 4(합성)는 각각 독립 검증(회귀·게이트 C) 후 STEP 5에서 교차.

---

## 11. 신규/개작 스크립트 (예정 — 구현 아님)
- **신규**: `scripts/compute_fitd_grid_yunuikang.py`(STEP2), `scripts/synth_duty_trace_yunuikang.py`(STEP4), `scripts/run_overcommit_sweep_yunuikang.sh`(STEP5), `scripts/plot_steps_yunuikang.py`(STEP2·5·6 그림).
- **개작(격리 복사본)**: `trace_replay_driver_expC`(per-turn tool sleep 주입 — 최소), overcommit 배선 5파일(`__main__.py`·`config.py`·`app.py`·`scheduler/router.py`, **게이트 B 후에만**).

---

**→ plan만 작성. 구현·실험은 게이트별 승인 후 별도 진행. 다음 행동: 사용자 검토 + STEP 1(goguma 접근) 제공 + 게이트 A(STEP 2)/B(STEP 3 구현) 승인 대기.**
