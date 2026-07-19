# STEPS 결과 — overcommit×duty 트레이드오프 연구 (STEP 2~6)

> 작성: 강윤의 · 브랜치 `yunuikang/thunderagent` · 서버 nutella1(계산은 GPU 무관) · 2026-07-19
> 권위 문서: `plans/2026-07-19_PLAN_overcommit-and-duty-tradeoff_yunuikang.md`
> 형식: 질문 → 증거(수치·파일:라인) → 결론 → [추정]/한계
> 가드레일: `scheduler/router.py` 미수정, 신규 파일 `*_yunuikang`, 진행중 P2/P3·goguma 무관. **STEP 2는 GPU 불필요(계산·플롯).**
> 이 파일은 STEP 2에서 신규 생성, STEP 5/6 결과를 **이어서 append**(로그 통일).

---

## STEP 2 — 트레이드오프 영역은 현실적인가 (4090 인공물 반박) ✅ 완료 · 게이트 A 정지

### Q. 질문
> **tr이 TraceLab에서 진 게 4090 특수현상이냐, 일반 문제냐?**
트레이드오프 영역(idle↔recompute)의 발생 조건을 부등식으로 정의하고, 현실 좌표에서 얼마나 흔한지 계산으로 보인다.

### 경계 (단 하나의 수)
`fit × d < 1  ⇔  fit < NEED(=1/d)`
- **fit×d ≥ 1**: tr이 스래싱 없이 GPU 포화 가능 → 트레이드오프 없음(tr 지배).
- **fit×d < 1**: 물리적으로 다 적재해도(무-스래싱) GPU가 논다 → idle 회수엔 overcommit(→recompute) 필요 → **트레이드오프 영역**. tr(pause만)은 여기서 진다.
- 즉 **fit×d = 스래싱 없이 얻는 GPU 수요의 최대치(=R_cap)**. <1이면 정책 무관 GPU 구조적 idle.

### 증거 1 — 구성요소·출처
| 기호 | 정의 | 출처 |
|------|------|------|
| d (duty) | reasoning/(reasoning+tool) | **측정**(c=1 프로파일) |
| ctx (프로그램KV) | 프로그램당 KV ≈ 입력 median tok | **측정** |
| C_total (KV풀) | block_size×num_gpu_blocks | **측정 2셀** + 나머지 추정 |
| fit | C_total/ctx | 파생 |
| fit×d (R_cap) | 무-스래싱 R 최대치 | 파생 |

KV/token(로컬 config.json 실측): **Qwen3-8B 147,456 B**(36L·8KV·128·BF16), **Qwen3-32B 262,144 B**(64L·8KV·128).

### 증거 2 — C_total 추정식 검산 (측정 2셀로 EFF 보정)
`C_total = (mem×EFF − weights) × 1e9 / (KV bytes/token)`, EFF = 유효 사용률.

| 셀 | 측정 C_total | KV(GB) | 도출 EFF |
|----|--------------|--------|----------|
| 4090/Qwen3-8B | 43,888 | 6.47 | 0.9530 |
| Pro6000×2/Qwen3-32B | 456,944 | 119.79 | 0.9655 |
| **채택(평균)** | — | — | **0.9593** |

**재현 잔차**: 4090 +2.3%, Pro6000 −1.0% → **±2.3% 이내**. C_total 추정식 타당.

### 증거 3 — ★ 측정 4셀 정합 (fit×d ≷ 1 로 실측 승패 100% 일치) + 포화 필요 f=1/R_cap
| 셀 | fit | d | **fit×d** | 영역 | **f_sat=1/R_cap** | 실측 승패 | 정합 |
|----|-----|-----|-----------|------|-------------------|-----------|------|
| 4090·SWE | 5.56 | 0.996 | **5.54** | tr지배 | 0.18 | tr 승(+78~84%) | ✅ |
| 4090·TraceLab | 2.35 | 0.196 | **0.46** | **트레이드오프** | **2.17** | **tr 패(−34%)** | ✅ |
| Pro6000×2·SWE | 57.9 | 0.996 | **57.6** | tr지배 | 0.02 | tr 승(+113%) | ✅ |
| Pro6000×2·TraceLab | 24.5 | 0.289 | **7.07** | tr지배 | 0.14 | tr 승(+80~87%) | ✅ |
- **경계가 4셀 전부에서 승패를 가른다.** tr이 진 유일 셀(4090 TraceLab)이 유일하게 fit×d<1이고, f_sat=2.17(≈2.2)만큼 overcommit해야 포화.

### 증거 4 — 격자 (7 GPU/모델 × 워크로드), `scratch/step2/fitd_grid_yunuikang.csv`(42행)
트레이드오프 영역(fit×d<1)에 든 셀 **14개**. 발췌:
| GPU/모델 | 워크로드 | fit×d | f_sat |
|----------|----------|-------|-------|
| 4090/8B | TraceLab | 0.46 | 2.17 |
| **A100-80G/32B** | **TraceLab(중듀티 0.289)** | **0.66** | **1.52** |
| **H100-80G/32B** | **TraceLab(중듀티 0.289)** | **0.66** | **1.52** |
| 5090/8B | longctx(d0.15) | 0.45 | 2.20 |
| Pro6000×1/32B | longctx | 0.47 | 2.11 |
| Pro6000×2/32B | deep-research(d0.10) | 0.71 | 1.40 |
| 4090·A100·H100 | deep-research(d0.10) | 0.07 | ~15 |
| 8×H100/235B | (전 워크로드) | **모두 ≥1** | — |
- 경계 근처(참고): **5090/8B·TraceLab = 1.02**(딱 경계 위) → goguma 5090에서 zone 진입하려면 **저듀티 합성(STEP 4)** 필요(TraceLab-8B는 경계).

### 머니 피겨
`figures/step2_fitd_hyperbola_yunuikang.png` — (d, fit) 평면에 fit×d=1 쌍곡선 + 시스템 점(별=측정4셀, 원=추정격자, 삼각=가정 저듀티/롱컨텍스트). 쌍곡선 아래(빨강)=트레이드오프, 위(파랑)=tr 지배.

### 결론 — **트레이드오프 영역은 현실적이고 일반적이다 (4090 인공물 아님)** ✅
1. **경계 검증**: fit×d<1이 측정 4셀의 승패를 100% 설명. tr이 지는 곳 = fit×d<1 유일.
2. **일반성 3경로**: fit×d<1은 **(저듀티)** 또는 **(긴 컨텍스트)** 또는 **(작은 KV/프로그램)** 중 하나만 세게 밀어도 진입.
   - ★ **데이터센터 GPU도 진입**: **A100/H100 단일 80GB에 Qwen3-32B·중듀티(0.289) TraceLab이 fit×d=0.66<1** — 소비자 GPU 전용 현상이 아님을 정면 반박.
   - 저듀티 에이전트(deep-research류 d≈0.1)는 **거의 모든 GPU에서** 진입(4090~Pro6000).
3. **경계의 견고성**: 8×H100/235B(초대형 KV풀)만 전 워크로드 ≥1 — 즉 트레이드오프는 "충분히 큰 KV풀+고듀티"에서만 사라짐. 이는 오히려 경계식이 말이 됨을 방증(무한 KV면 idle 없음).
→ **게이트 A 판정: "현실적/일반적" 수용 근거 충분.** STEP 3~6(노브·합성·스윕·분석) 진행 정당.

### [추정]/한계
- **C_total 추정치**(5090·A100·H100·8×H100): 측정 아님, EFF=0.959 외삽. 잔차 ±2.3%(측정 2셀). fit은 **차수(order) 판정용**이지 정밀 임계 아님.
- **8×H100/235B는 [ROUGH]**: MoE·FP8 아키텍처 근사(94L·4KV·128, weights 235GB). 절대값 신뢰도 낮음 — "≥1(zone 밖)" 방향만 사용.
- **ctx = 입력 median 근사**: 실제 KV는 prefix 공유·shared_tokens로 변동 → fit은 근사.
- **d는 c=1 고유값**: 부하 하 변동(플랜 §4-2) → 격자는 워크로드 **성격 분류**용.
- **가정 워크로드**(deep-research류 d0.10·ctx64k, longctx d0.15·ctx32k): 실측 아님, 클래스 대표 가정값. 실데이터로 대체 예정.
- **8×A100 고부하 스래싱(논문 §A.5)과의 구분**: 그건 fit×d≥1에서 C≫fit일 때 default가 스래싱하는 축(=tr가 이기는 영역). 본 STEP의 fit×d<1은 **C를 아무리 올려도 무-스래싱으론 GPU를 못 채우는** 별개 축. 상호보완적.

### Placeholder (데이터 생기면 채움)
- **HLE**: d·ctx TBD — P3 24h 녹화→tool 지연에서 duty 산출 예정(수집 중). 격자 CSV에 NaN 행으로 포함.
- **Science**: d·ctx TBD — 데이터 blocker(SharePoint password)로 미수집(보류). NaN 행 포함.
- 측정 완료 시 §증거3(4셀 검증표)에 행 추가.

### 산출물
- 스크립트: `scripts/compute_fitd_grid_yunuikang.py`(신규, GPU 불필요)
- 데이터: `scratch/step2/fitd_grid_yunuikang.csv`(42행, HLE·Science NaN 포함)
- 그림: `figures/step2_fitd_hyperbola_yunuikang.png`

### ★ 게이트 A — 정지
STEP 2 완료. 플랜 §2 재서술 + 격자·쌍곡선·4셀 정합 산출. **STEP 3(overcommit 노브 구현, goguma 필요)·이후는 승인 후 진행.** 정지·보고.

---

<!-- STEP 5/6 결과는 이 아래에 append -->
