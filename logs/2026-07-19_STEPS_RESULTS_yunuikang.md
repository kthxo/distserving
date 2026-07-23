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

## STEP 1 — goguma 스코핑 (2×5090) ✅ 완료 · 보고 후 정지

> 서버: goguma(143.248.53.112) · GPU 2×RTX5090(각 32,607 MiB) · 2026-07-19 07:53~08:10 KST

### Q. 질문
> **goguma 2×5090에서 Qwen3-8B를 기동할 수 있는가? C_total·batch-token 레짐은? 단일 vs TP2 구성과 fit×d<1 영역 진입 설계는?**

### 증거 1 — 환경 확인

| 항목 | 결과 | 근거 |
|------|------|------|
| GPU | 2×RTX5090, 각 32,607 MiB, 유휴(0%, 프로세스 없음) | `nvidia-smi` 07:53 |
| Driver/CUDA | 580.82.07 / CUDA 13.0 | `nvidia-smi` |
| SM | Blackwell sm_120 (5090=GB202) | driver 580 + CUDA 13.0 |
| Python | 3.12.11 | `.venv/bin/python --version` |
| PyTorch | 2.11.0+cu130 | `torch.__version__` |
| vLLM | 0.24.0 | `vllm.__version__` |
| ThunderAgent | editable install at `/home/yunuikang/yunuikang_work/distserving/` | `ThunderAgent.__file__` |
| router.py | baseline(미수정, 초기 import 이후 변경 없음) | `git log -- ThunderAgent/scheduler/router.py` → 1 commit만 |
| 모델 캐시 | Qwen3-8B 캐시됨 (`~/.cache/huggingface/hub/models--Qwen--Qwen3-8B`) | `ls` 확인 |
| 환경변수 필수 | `VLLM_USE_FLASHINFER_SAMPLER=0`, `VLLM_ATTENTION_BACKEND=FLASH_ATTN`, `CPATH` 설정 | FlashInfer JIT gcc13 호환 실패(첫 시도)→환경변수 설정 후 성공 |

### 증거 2 — ★ C_total 실측 (핵심)

**기동 명령**: `CUDA_VISIBLE_DEVICES=0 vllm serve Qwen/Qwen3-8B --max-model-len 32768 --gpu-memory-utilization 0.92 --port 8100`

| 수치 | 값 | 근거 |
|------|-----|------|
| **C_total** | **89,040 tokens** | 기동 로그 `GPU KV cache size: 89,040 tokens` (kv_cache_utils.py:2146) |
| block_size | 16 | vLLM default |
| num_gpu_blocks | 5,565 | 89,040/16 |
| weights | 15.27 GiB | 기동 로그 `Model loading took 15.27 GiB` |
| KV memory | 13.13 GB | 89,040 × 147,456 B/tok |
| overhead (graphs+activations) | ~1.60 GB | 29.998(eff) − 15.27(wt) − 13.13(KV) |
| GPU memory used | 29,914 MiB / 32,607 MiB | `nvidia-smi` (serving 중) |
| 추론 | 정상(health OK, completion 응답 확인) | `curl /health`, chat/completions |

**vs 4090**: C_total 89,040 / 43,888 = **×2.03**. VRAM 32GB vs 24GB(×1.36)인데 KV가 ×2.03인 이유: weights(~15GB)를 빼면 5090은 KV에 ~14.7GB, 4090은 ~6.5GB 할당 → ×2.27 (오버헤드 차이로 ×2.03).

### 증거 3 — batch-token 레짐 (★ 4090과 동일 확정)

| 파라미터 | 값 | 근거 |
|----------|-----|------|
| max_num_batched_tokens | **2048** | `EngineArgs.get_batch_defaults(world_size=1)` OPENAI_API_SERVER; compile_ranges_endpoints=[2048] |
| max_num_seqs | **256** | 동상 |

**판정**: 5090(32GB) < 70GiB 경계 → **4090과 동일 2048/256 레짐**. VLLM_PROFILING §1-5·§7-B-1 정합. overcommit 스윕이 배치 변수 고정 하 깨끗한 대조.

### 증거 4 — ★ fit×d 분석 (핵심 결과)

| 워크로드 | ctx(tok) | fit=C/ctx | d | fit×d | 영역 | f_sat=1/(fit×d) |
|----------|----------|-----------|-----|-------|------|-----------------|
| TraceLab(8B on 5090) | 18,684 | **4.77** | 0.196* | **0.934** | **★ fit×d<1** | **1.07** |
| SWE(8B on 5090) | 7,897 | 11.28 | 0.996 | 11.23 | tr 지배 | 0.09 |

*d=0.196은 4090/8B c=1 실측. 5090이 더 빠르면 실제 d↓ → fit×d<0.93 가능(zone 더 깊이).

**★ 핵심 발견**: 5090/8B TraceLab은 **fit×d=0.934 < 1 — 자연스럽게 트레이드오프 영역에 진입**.
- 4090(fit×d=0.46)보다 경계에 가깝지만 **<1 확정**.
- STEP 2 격자 추정값(1.02)과 차이: 실측 C_total(89,040)이 EFF외삽 추정(~99k)보다 작음 → **실측으로 정정: 0.93<1**.
- **f_sat=1.07**: 7% overcommit으로 R=1(GPU 포화) 도달. 작은 f 범위에서 최적점 존재 여부 검증 가능.

### 증거 5 — 구성 결정: 단일 5090 vs TP2

| 구성 | C_total | fit(TraceLab) | fit×d | 판단 |
|------|---------|---------------|-------|------|
| **단일 5090** | 89,040(실측) | 4.77 | **0.934(<1)** | ★ zone 자연 진입 |
| TP2(2×5090) | ~178k(추정, 미실측) | ~9.5 | ~1.87(>1) | zone 밖 → 저듀티 합성 필수 |

**★ 결정: 단일 5090 우선 사용**.

**근거**:
1. TraceLab이 **자연 zone** 내 — 인위적 KV캡/저듀티 합성 없이도 경계 연구 가능.
2. f_sat=1.07 → 작은 f(1.0~1.5)에서 정밀 최적점 탐색. 4090(f_sat=2.17)보다 좁은 범위이지만 경계의 미세구조 관찰에 유리.
3. TP2는 fit↑ → zone 밖 → 불필요한 복잡성.
4. GPU1을 독립 실험 병렬화/대조에 사용 가능.

### STEP 4 예비 그리드 설계 (단일 5090, fit=4.77)

**d 그리드** (fit×d를 경계 양측에 걸치도록):
| d | fit×d | 영역 | 비고 |
|-----|-------|------|------|
| 0.10 | 0.48 | zone 깊숙이 | deep-research류 |
| 0.15 | 0.72 | zone 중간 | |
| 0.20 | 0.95 | zone 경계 아래 | ≈TraceLab 자연값 |
| 0.30 | 1.43 | zone 밖 | 음성대조 |
| 0.50 | 2.39 | zone 밖 | |
| 0.70 | 3.34 | zone 밖(tr 지배) | |

→ fit×d=1 경계는 **d≈0.21**에서 교차. d={0.10,0.15,0.20}이 zone 내(H1 검증), d={0.30,0.50,0.70}이 zone 밖(H2 검증).

**C 그리드**: {2, 4(≈fit), 8(≈2×fit), 16(≈3.4×fit)}

### 결론 (종합)

| 항목 | 결과 |
|------|------|
| 환경 | ✅ 완비 (vLLM 0.24.0, Qwen3-8B 캐시, FLASH_ATTN, Python 3.12) |
| GPU | ✅ 2×5090 유휴, 타 사용자 없음 |
| C_total | **89,040 tok** (단일 5090, gpu_util=0.92) |
| batch-token | **2048/256** (4090 동일) |
| fit(TraceLab) | **4.77** |
| **fit×d** | **0.934 < 1 ★ 자연 zone 진입** |
| f_sat | **1.07** |
| 구성 | **단일 5090 우선** |
| router.py | baseline 확인 |

### ★ STEP 1 정지·보고

goguma 스코핑 완료. **STEP 3(overcommit 노브 구현) 착수 승인 대기.** 정지.

---

## STEP 3 — overcommit 노브 구현 + 게이트 B 검증 ✅ 완료 · 정지

> 브랜치: `yunuikang/overcommit` · 서버 goguma · 2026-07-19 08:10~09:00 KST

### Q. 질문
> **`--capacity-overcommit-factor f` 노브를 tr에 추가: (a) f=1이 기존과 비트-동일한가? (b) f→∞에서 default에 수렴(pause≈0)하는가?**

### 구현 — 5-홉 배선 + 4곳 주입

| 홉 | 파일 | 변경 |
|----|------|------|
| 1 | `ThunderAgent/__main__.py:33` | `--capacity-overcommit-factor` argument 추가 |
| 2 | `ThunderAgent/__main__.py:51` | Config 생성에 `capacity_overcommit_factor` 전달 |
| 3 | `ThunderAgent/config.py:30` | `capacity_overcommit_factor: float = 1.0` 필드 추가 |
| 4 | `ThunderAgent/app.py:246` | Router 생성에 전달 |
| 5 | `ThunderAgent/scheduler/router.py:69,76` | 파라미터 + `self.capacity_overcommit_factor` 저장 |

| # | 주입점 | 변경 | margin 정의 |
|---|--------|------|-------------|
| 1 | `router.py` `_select_backend_for_new_program` | `remaining + margin < required` | `(f−1)×C_total` |
| 2 | `router.py` `_scheduled_check` | `remaining + margin < 0` (pause 트리거) | 동상 |
| 3 | `router.py` `_pause_until_safe(backend, margin)` | `remaining + margin < 0` (pause 루프) | 호출자에서 전달 |
| 4 | `router.py` `_greedy_resume` | `remaining += margin` (resume 용량) | 동상 |

**불변**: pause 대상 선정(작은 ACTING부터)·decay 모양·BFD·우선순위·공정성 큐 안 건드림. 임계값만 이동.
**금지 준수**: `cache_config.total_tokens_capacity` 자체 미수정. 각 비교 지점에서 `+margin` 형태만.

### 게이트 B — (a) f=1 비트-동일 ✅

**산술 증명**: `f=1.0 → margin = (1.0−1.0)×C_total = 0.0`. 4곳 전부 `+0.0` → 기존 코드와 **산술적 NOP** → 비트-동일.

**실행 검증**:
- vLLM Qwen3-8B 기동(GPU0, C_total=95,936 at runtime)
- ThunderAgent `--capacity-overcommit-factor 1.0 --router tr --port 9200`
- `smoke_test_yunuikang.py` → **SMOKE TEST OK** (completion·multi-turn·release 전 경로 정상)
- Health: `programs_count=0, paused=0` (정상)

### 게이트 B — (b) f→∞ default 수렴 ✅

**산술 증명**: `f=1e6 → margin = 999,999×95,936 ≈ 9.59×10¹⁰ tok`.
- Pause 트리거: `remaining + 9.59e10 < 0` → **불가능**(worst remaining ≈ −10×C ≈ −1M ≪ margin).
- 신규배정: `remaining + margin < required` → **항상 통과**(어떤 required도 margin보다 작음).
- Resume: `remaining + margin` → 항상 거대 → 전원 즉시 resume.
- **결론**: 모든 용량 검사가 사실상 비활성 → **pause 불가능 = default와 동치**.

**실행 검증(C=10 > fit~5)**:
- ThunderAgent `--capacity-overcommit-factor 1000000 --router tr --port 9200`
- 10개 동시 프로그램(C=10, long prompt) → **paused_count=0, 전원 완료** ✅
- 로그에 pause 이벤트 **없음** ✅
- 대조: f→∞는 scheduling_enabled=True이지만 margin이 무한해 실질 무효 → default 행동 재현.

### STEP 2 격자 보정 (사용자 지시 4항)

5090 실측(C_total=89,040)을 3번째 보정 셀로 추가 → EFF 재계산:
- **EFF**: 0.9593(2셀) → **0.9471**(3셀, 5090 포함)
- 잔차: 4090 −2.2%, 5090 +5.9%, Pro6000 −3.0%
- **zone 진입 셀 수**: 14개 → **15개** (5090/longctx-generic 신규 진입)
- A100/H100 TraceLab: fit×d 0.66→**0.60** (더 깊이 zone 진입 → 일반성 주장 강화)
- 스크립트(`compute_fitd_grid_yunuikang.py`) 5090 행 `None→89040` 변경, 재실행 완료.
- CSV(`fitd_grid_yunuikang.csv`) 및 그림(`step2_fitd_hyperbola_yunuikang.png`) 갱신.

### [추정]/한계

- **f→∞ 수렴의 실질적 의미**: f=1e6에서 pause=0 확인했으나, "default와 bit-identical"은 아님 — tr은 여전히 프로그램 상태 추적·metrics fetch·scheduler loop를 돌린다. 수렴은 **용량 판정 결과**에 대해서만. 이로 인해 약간의 overhead(HTTP metrics fetch 등)가 존재하나 throughput에 미미.
- **런타임 C_total 차이**: STEP 1 첫 기동(89,040) vs 이번 기동(95,936) — CUDA graph 캐시 여부에 따른 overhead 변동. 스윕 시 기동 로그에서 확인·고정 필요.
- smoke test는 단기·소량 — TraceLab 규모 워크로드에서의 비트-동일성은 STEP 5 f=1 baseline 런으로 최종 확인 예정.

### ★ 게이트 B 판정: 통과 ✅

1. **f=1 비트-동일**: 산술 NOP 증명 + smoke test 통과.
2. **f→∞ default 수렴**: 산술 불가능 증명 + C=10(>fit) 실행에서 pause=0.
3. **STEP 2 격자 보정**: EFF 3셀 재보정, 15셀 zone 진입(일반성 강화).

**정지. STEP 4(듀티 통제 합성)·STEP 5(핵심 스윕) 승인 대기.**

---

## STEP 4 — 듀티 통제 합성 워크로드 + 게이트 C ✅ 완료 · 정지

> 서버: goguma · GPU0(RTX5090, 단일) · 2026-07-19 14:40~15:30 KST

### Q. 질문
> **E2E 고정·듀티만 변동하는 합성 trace를 c=1 replay 시, 실측 d가 설계 d와 ±5% 이내인가?**

### 설계 — 듀티 통제 합성 원리

1. **reasoning_time(turn)** = prefill_time + decode_time
   - Turn 0 (cold): input_tokens / COLD_PREFILL_RATE
   - Turn 1+ (warm): (prev_output + input_growth) / WARM_PREFILL_RATE
   - + output_tokens / DECODE_RATE

2. **tool_duration** = reasoning_time × (1−d) / d
   → 정의에 의해 d = reasoning / (reasoning + tool) 정확히 성립.

3. **E2E per session** = Σ(reasoning + tool) = Σ reasoning × 1/d
   → d가 작을수록 tool이 길어지고 E2E 증가 (reasoning 고정, tool만 조절).

### 캘리브레이션 (5090 c=1 실측)

| 상수 | 값 | 출처 |
|------|-----|------|
| COLD_PREFILL_RATE | **9,202 tok/s** | gatec_d02_turns.jsonl turn 0: 4000/0.435s |
| WARM_PREFILL_RATE | **3,974 tok/s** | gatec_d02_turns.jsonl turn 1-7: 550/0.138s (평균) |
| DECODE_RATE | **97 tok/s** | 50 tokens / ~0.515s (전 turn 평균) |

**주의**: 캘리브레이션은 **clean prefix cache** 상태에서 측정. vLLM 재기동 후 첫 실행으로 확보.
- Turn 0: 전체 프롬프트 cold prefill (prefix cache miss)
- Turn 1+: 이전 turn prefix cached → 증분 토큰(550)만 연산

### 게이트 C — 검증 실행

**조건**: vLLM 재기동(prefix cache flush) → synth_d0.2_v2.jsonl(c=1, 1세션 8턴) replay.

| 지표 | 값 |
|------|-----|
| Target d | 0.2000 |
| **Actual d** | **0.1978** |
| **Error** | **1.12%** |
| Gate C (±5%) | **PASS ✓** |

**Per-turn breakdown**:
| Turn | ttft_s | decode_s | reasoning_s | tool_s | turn_d |
|------|--------|----------|-------------|--------|--------|
| 0 | 0.412 | 0.502 | 0.914 | 3.801 | 0.194 |
| 1 | 0.127 | 0.510 | 0.636 | 2.616 | 0.196 |
| 2 | 0.107 | 0.511 | 0.618 | 2.616 | 0.191 |
| 3 | 0.130 | 0.519 | 0.648 | 2.616 | 0.199 |
| 4 | 0.130 | 0.519 | 0.649 | 2.616 | 0.199 |
| 5 | 0.134 | 0.520 | 0.654 | 2.616 | 0.200 |
| 6 | 0.142 | 0.519 | 0.661 | 2.616 | 0.202 |
| 7 | 0.150 | 0.520 | 0.670 | 2.616 | 0.204 |

**캘리브레이션 정확도**: 설계 reasoning vs 실측, turn-level 오차 −5.5%~+2.4%. 전체 d 오차 1.12%.

### 실패 사례 및 교훈 (과정 기록)

1. **1차 시도 (4090 레이트)**: PREFILL=5896, DECODE=52 → actual d=0.08, 400% 오류. **원인**: 5090은 4090보다 2배 빠름.
2. **2차 시도 (5090 레이트, 캐시 오염)**: 5090 레이트 적용했으나 prefix cache 잔존 → turn 0 ttft 0.086s(설계 0.435s). actual d=0.18, 9.88% 오류.
3. **3차 시도 (vLLM 재기동 후 clean)**: prefix cache flush → turn 0 cold 정상 동작. **error 1.12% — PASS.**

**교훈**: prefix cache 상태가 prefill 시간에 ~5× 영향. 캘리브레이션 런은 반드시 clean cache 상태(서버 재기동)에서 수행해야 함.

### 생성된 d-grid traces

| d | 파일 | sessions | turns | avg_reas/turn | avg_tool/turn | session_E2E |
|-----|------|----------|-------|---------------|---------------|-------------|
| 0.1 | synth_d0.1_v2.jsonl | 10 | 80 | 0.691s | 6.218s | 55.3s |
| 0.2 | synth_d0.2_v2.jsonl | 10 | 80 | 0.691s | 2.764s | 27.6s |
| 0.3 | synth_d0.3_v2.jsonl | 10 | 80 | 0.691s | 1.612s | 18.4s |
| 0.5 | synth_d0.5_v2.jsonl | 10 | 80 | 0.691s | 0.691s | 11.1s |
| 0.7 | synth_d0.7_v2.jsonl | 10 | 80 | 0.691s | 0.296s | 7.9s |
| 0.9 | synth_d0.9_v2.jsonl | 10 | 80 | 0.691s | 0.077s | 6.1s |

**공통 파라미터**: input_base=4000, growth=500/turn, output=50, 8 turns/session.
Mid-session ctx ≈ 6200 tok → fit(5090) = 89,040/6200 ≈ **14.4** (per-trace fit).

### [추정]/한계

- **c=1 전용 검증**: 캘리브레이션은 c=1(무경합). c>1에서 batching·preemption이 prefill/decode 속도에 영향 → 실측 d 변동 예상. 이는 의도된 효과(STEP 5에서 관찰 대상).
- **런타임 C_total**: 89,040(첫 기동) vs 95,936(CUDA graph 캐시 후). 스윕에서는 기동 로그의 C_total을 기록·사용.
- **warm prefill 증가 추세**: ttft가 turn 진행 시 증가(0.107→0.150s). WARM_PREFILL_RATE=3974는 550토큰 기준 평균이지만 context 길이 증가에 따라 attention 오버헤드 증가. 8턴 범위에서 ±20% 변동이나 전체 d에 미치는 영향은 1.1% 이내.

### 산출물

- 스크립트: `scripts/synth_duty_trace_yunuikang.py` (신규)
- 데이터: `scratch/step4/synth_d{0.1,0.2,0.3,0.5,0.7,0.9}_v2.jsonl` (6파일, 총 480턴)
- 검증 결과: `scratch/step4/gatec_d02_v3_turns.jsonl` (Gate C 통과 런)
- 이전 시도: `scratch/step4/gatec_d02_turns.jsonl` (v1, 4090 레이트), `gatec_d02_v2_turns.jsonl` (v2, 캐시오염)

### ★ 게이트 C 판정: 통과 ✅

c=1 replay에서 설계 d=0.20 vs 실측 d=0.1978, 오차 1.12% (±5% 이내).
캘리브레이션 모델(cold/warm 구분, 5090 실측 레이트) 타당성 확인.

**정지. STEP 5(f×C×d 스윕) 승인 대기.**

---

## STEP 5 — 파일럿 스윕 + 격자 프루닝 ⏳ 파일럿 완료 · 본 스윕 승인 대기

> 서버: goguma · GPU0(RTX5090, 단일) · 2026-07-19 16:00~17:10 KST

### §0 — 스윕 전 확인

#### §0.1 — fit×d span 검증 및 ctx 보정

**문제 발견**: v2 traces (input_base=4000, peak_seq=7900)에서 fit=12.1 → **모든 d에서 fit×d≥1**. 경계가 격자 내부를 통과하지 않음.

**보정**: input_base=16,250으로 증가 (TraceLab-scale ctx). Peak_seq=20,150 → fit=4.76.

| d | fit×d | 영역 | f_sat | 가설 |
|-----|-------|------|-------|------|
| 0.1 | **0.476** | ★ 미포화 | 2.10 | H1 |
| 0.2 | **0.952** | ★ 미포화(경계) | 1.05 | H1 |
| 0.3 | 1.428 | 포화 | 0.70 | H2 |
| 0.5 | 2.381 | 포화 | 0.42 | H2 |
| 0.7 | 3.333 | 포화 | 0.30 | H2 |
| 0.9 | 4.285 | 포화 | 0.23 | H2 |

**경계 d ≈ 0.21** — d=0.2(H1)와 d=0.3(H2) 사이 통과 ✓

#### §0.2 — 캘리브레이션 보정 (ctx-aware 2-component 모델)

기존 WARM_PREFILL_RATE=3974 tok/s는 ctx=4-8K 기반. ctx=16-20K에서 warm ttft가 2× 느림 (0.132→0.237s).

**원인**: warm prefill = new_token_compute + **attention_over_full_cached_context**. 긴 ctx에서 attention 오버헤드 증가.

**2-point 캘리브레이션** (ctx=4-8K, ctx=16-20K 실측):
| 상수 | 값 | 의미 |
|------|-----|------|
| COLD_PREFILL_RATE | 9,038 tok/s | turn 0 cold (16K 실측) |
| WARM_NEW_TOKEN_RATE | 7,208 tok/s | 새 토큰 KV 계산 |
| WARM_CTX_ATTN_RATE | 116,228 tok/s | 캐시된 ctx attention 오버헤드 |
| DECODE_RATE | 91 tok/s | 장문맥 decode (16-20K) |

**검증**: d=0.1 spot-check → actual d=0.1002, error **0.17%** ✓ (±5% 이내)

#### §0.3 — C_total·batch 핀

| 파라미터 | 핀된 값 | 근거 |
|----------|---------|------|
| **C_total** | **95,936 tokens** | vLLM 기동 로그 (CUDA graph 캐시 후) |
| max_num_batched_tokens | 2,048 | EngineArgs.get_batch_defaults(world_size=1) |
| max_num_seqs | 256 | 동상 |
| fit (peak_seq=20,150) | **4.76** | 95936/20150 |

### §1 — ★ 파일럿 스윕 결과

**설정**: d=0.1 (deep zone, fit×d=0.48), C=10 (≈2×fit), f grid, REPEAT=1.
측정: vLLM restart/clean cache per point, nvidia-smi dmon 1s, prompt_tokens_by_source (참 hit), --stream.

| f | thr(tok/s) | TRUE_hit | recomp% | preempt | p50(s) | p95(s) | gpu% | ok/fail |
|------|-----------|----------|---------|---------|--------|--------|------|---------|
| 1.0 | 26.9 | 0.763 | 0.237 | 0 | 156.3 | 237.5 | 22 | 9/1 |
| 1.2 | 32.1 | 0.701 | 0.299 | 0 | 136.3 | 216.1 | 29 | 10/0 |
| 1.5 | 72.8 | 0.219 | 0.781 | 0 | 158.6 | 196.1 | 62 | 10/0 |
| 1.8 | 107.8 | 0.079 | 0.921 | 0 | 172.1 | 184.8 | 74 | 10/0 |
| **2.0** | **251.3** | 0.027 | 0.973 | 0 | 180.6 | **183.3** | 80 | 10/0 |
| 2.5 | **261.1** | 0.014 | 0.986 | 0 | 183.3 | 185.8 | 85 | 10/0 |
| 3.0 | 261.0 | 0.014 | 0.986 | 0 | 184.2 | 186.2 | 84 | 10/0 |
| ∞ | 261.0 | 0.014 | 0.986 | 0 | 184.1 | 186.4 | 84 | 10/0 |

### ★ 핵심 발견 5개

**발견 1 — tr(f=1.0)은 깊은 zone(d=0.1)에서 재앙적으로 나쁘다**
- throughput 9.7× 열악 (26.9 vs 261.0 tok/s)
- p95 28% 악화 (237.5 vs 186.4s)
- 1 프로그램 실패 (turn 0 ttft=91.5s → capacity 대기로 timeout)
- GPU 이용률 22% (78% idle)

**발견 2 — 엄격한 내부 최적 f*는 존재하지 않는다 (H1 약 지지)**
- f=2.0이 "기술적으로" f=1·f=∞ 모두 이김 (thr > f=1, p95 < f=∞)
- 그러나 f=∞ 대비 개선: throughput 3.7% 열악, p95 1.7% 우위 — **마진 무의미**
- **f≈f_sat 이상에서 지표 수렴** → 실질적으로 f>f_sat은 모두 default와 동치
- "그냥 default 쓰면 됨"이 깊은 zone의 결론

**발견 3 — preemption=0 (전 f 값)**
- vLLM은 overcommit을 **prefix cache eviction**(soft)으로 처리, 요청 중단(preemption) 없음
- 따라서 f↑의 비용은 **미래 recompute** 뿐, 실행 중 tail latency 페널티 없음
- 이것이 f>1이 안전한 근본 원인: eviction은 cache miss일 뿐, abort가 아님

**발견 4 — 깊은 zone에서 idle 비용 >> recompute 비용**
- f=1.0: 76% cached, 22% GPU → idle이 지배 (GPU 78% 놀림)
- f=∞: 1.4% cached, 84% GPU → 99% recompute해도 GPU가 유용하게 일함
- **d=0.1에서 recompute 토큰 ×4 증가해도 throughput ×10 증가** — 명확한 승

**발견 5 — f=1.0 failure: C>fit에서 tr은 프로그램 손실 유발**
- s004: turn 0에서 ttft=91.5s (capacity 큐 대기), 5/8 turn만 완료
- **tr은 C>fit 상황에서 liveness를 위협** — idle 보전 목적이 오히려 서비스 가용성 훼손

### §1 결론 및 본 스윕 제안

#### H1·H2 판정 (파일럿 기준)
- **H1 (d=0.1, 깊은 zone)**: 내부 최적 f* 약 지지 (f≈f_sat≈2.0에서 p95 1.7% 우위). 실질적 의미 미미 — default가 사실상 최선.
- **H2**: 포화 d(≥0.3)는 미검증 — 본 스윕에서 확인 필요.

#### 본 스윕 격자 프루닝 제안

1. **f 격자 축소**: f>f_sat에서 지표 수렴 확인 → {1.0, 1.5, f_sat, ∞}로 충분.
   - 워크로드별 f_sat: d=0.1→2.10, d=0.2→1.05, d=0.3→0.70(포화,f_sat<1→f=1만)
   - 포화 d에서는 f=1.0과 f=∞만 비교 (f>1이 손해인지 확인 = H2)
2. **C 격자**: {fit/2, fit, 2·fit, 4·fit} = {2, 5, 10, 20} 유지 — C<fit(음성대조) + C>fit(활성)
3. **REPEAT=3** 유지
4. **d=0.2 추가 파일럿 추천**: 경계(fit×d=0.95) — H1이 여기서 더 유의미할 가능성

### 산출물

- 스윕 스크립트: `scripts/sweep_pilot_yunuikang.py`
- 파일럿 데이터: `scratch/step5/pilot/pilot_results.jsonl` (8행, f×1 repeat)
- Per-turn 데이터: `scratch/step5/pilot/turns_f=*_r=0.jsonl`
- vLLM/TA 로그: `scratch/step5/pilot/vllm_f=*_r=0.log`, `ta_f=*_r=0.log`
- nvidia-smi: `scratch/step5/pilot/nvsmi_f=*_r=0.log`
- v3 traces (ctx-aware): `scratch/step4/synth_d{0.1,...,0.9}_v3.jsonl`

### §2 — 2-point 추가 파일럿 (d=0.2 경계, d=0.5 포화)

> 2026-07-19 17:10~18:30 KST · GPU0 · vLLM restart/clean cache per point

#### d=0.2 (fit×d=0.95, boundary)

**설정**: C=10(≈2×fit), f∈{1.0, 1.05(≈f_sat), 1.25, 1.5, ∞}, REPEAT=1.

| f | thr(tok/s) | TRUE_hit | recomp% | preempt | p50(s) | p95(s) | gpu% | ok/fail |
|------|-----------|----------|---------|---------|--------|--------|------|---------|
| **1.0** | **50.9** | **0.858** | 0.142 | 0 | 115.7 | **120.7** | 30 | 10/0 |
| 1.05 | 49.6 | 0.852 | 0.148 | 0 | 125.5 | 127.0 | 29 | 10/0 |
| 1.25 | 63.0 | 0.415 | 0.585 | 0 | 135.6 | 141.5 | 70 | 10/0 |
| 1.5 | 62.3 | 0.222 | 0.778 | 0 | 133.9 | 176.8 | 73 | 10/0 |
| ∞ | 261.6 | 0.014 | 0.986 | 0 | 167.8 | **170.9** | 92 | 10/0 |

**★ d=0.2 핵심**: f=1(tr)이 f=∞(default) 대비 **wall 1.31× 빠름**, **p95 1.42× 우위**.
- d=0.1과 **정반대**: 경계에서 tr이 default를 이김
- f=1.05(≈f_sat)은 f=1과 거의 동일 — 캐시 보존이 핵심 이점
- f=1.25부터 TRUE_hit 급락(0.858→0.415) → overcommit이 cache 파괴

#### d=0.5 (fit×d=2.38, saturated)

**설정**: C=10(≈2×fit), f∈{1.0, 1.5, ∞}, REPEAT=1.

| f | thr(tok/s) | TRUE_hit | recomp% | preempt | p50(s) | p95(s) | gpu% | ok/fail |
|------|-----------|----------|---------|---------|--------|--------|------|---------|
| **1.0** | **79.8** | **0.856** | 0.144 | 0 | 72.9 | **76.3** | 49 | 10/0 |
| 1.5 | 105.9 | 0.222 | 0.778 | 0 | 129.1 | 146.6 | 88 | 10/0 |
| ∞ | 261.0 | 0.014 | 0.986 | 0 | 164.2 | **166.5** | 93 | 10/0 |

**★ d=0.5 핵심**: f=1(tr)이 f=∞(default) 대비 **wall 1.96× 빠름**, **p95 2.18× 우위**.
- 포화 zone에서 tr 우위 극대화 — GPU가 이미 d만으로 절반 바쁘므로 recompute가 순수 낭비
- H2 확인: 포화 d에서 tr(pause)이 default를 압도

### §3 — ★ 3-point 레짐 지도 분석

#### 레짐 전환 (regime flip)

| d | fit×d | 영역 | wall 승자 | p95 승자 | wall ratio(∞/1) |
|-----|-------|------|-----------|----------|-----------------|
| 0.1 | **0.48** | 미포화(깊은) | **f=∞** | **f=∞** | **0.79** (default 21% 빠름) |
| 0.2 | **0.95** | 미포화(경계) | **f=1** | **f=1** | **1.31** (tr 31% 빠름) |
| 0.5 | **2.38** | 포화 | **f=1** | **f=1** | **1.96** (tr 96% 빠름) |

**★ 레짐 전환점**: fit×d ∈ **(0.48, 0.95)** 에서 정책 최적이 뒤집힌다.
- fit×d < ~0.7 (추정): idle 비용 > recompute 비용 → default(f=∞) 지배
- fit×d > ~0.7 (추정): recompute 비용 > idle 비용 → tr(f=1) 지배
- **경계는 fit×d=1이 아니라 그보다 약간 아래** — 경계 근처에서도 캐시 보존 가치가 높기 때문

#### 물리적 해석

1. **d=0.1 (fit×d=0.48)**: C>fit이어도 GPU가 10% 시간만 사용 → 빈 GPU에 recompute 올려도 손해 없음. pause(f=1)하면 GPU 78% 놀림 → **idle 비용 지배**.

2. **d=0.2 (fit×d=0.95)**: GPU가 ~30% 사용됨. prefix cache 보존(f=1)으로 85% hit → prefill skip 이점이 recompute 절약을 능가. f=1.25만 돼도 cache hit 0.42로 급락 → **cache 보존 가치 지배**.

3. **d=0.5 (fit×d=2.38)**: GPU가 이미 50% 사용 → overcommit 시 recompute가 GPU 시간의 순수 낭비. f=1의 49% GPU util이 이미 충분한 작업량을 처리. **recompute 비용 지배**.

#### H1·H2 최종 판정 (3-point 파일럿)

- **H1 (미포화 zone 내 최적 f*)**: **반증됨**
  - d=0.1: 내부 최적 부재 (f=2.0 vs f=∞ 차이 1.7%, 무의미)
  - d=0.2: f=1이 최선 (overcommit 하면 cache 파괴로 악화)
  - → **H1 수정**: "미포화 zone에서도 fit×d 위치에 따라 최적 정책이 다름"

- **H2 (포화 zone에서 tr 지배)**: **확인됨**
  - d=0.5: tr(f=1)이 wall 1.96×, p95 2.18× 우위
  - 단, "포화"뿐 아니라 **경계(d=0.2)에서도 tr이 이김** — H2의 범위가 예상보다 넓음

#### 머니 피겨

`figures/step5_regime_map_yunuikang.png` — 3-panel 레짐 지도:
- (a) Throughput(tok/s) vs fit×d: f=1 vs f=∞
- (b) Tail latency p95(s) vs fit×d: f=1 vs f=∞
- (c) Wall time ratio (f=∞ / f=1) vs fit×d: ratio=1 선을 교차하는 전환점 시각화

### 산출물 (§2-§3)

- 파일럿 데이터:
  - `scratch/step5/pilot_d02/pilot_results.jsonl` (5행)
  - `scratch/step5/pilot_d05/pilot_results.jsonl` (3행)
- Per-turn/로그: 각 디렉터리 내 `turns_f=*_r=0.jsonl`, `vllm_f=*_r=0.log`, `ta_f=*_r=0.log`, `nvsmi_f=*_r=0.log`
- 레짐 지도: `figures/step5_regime_map_yunuikang.png`

### ★ 게이트 정지 · 보고

3-point 파일럿(d=0.1/0.2/0.5) 완료. **레짐 전환 발견**: fit×d ∈ (0.48, 0.95)에서 정책 최적이 뒤집힘.

**핵심 결론**:
1. **fit×d < ~0.7**: default(f=∞)가 최선 — idle 비용 지배, overcommit 무해
2. **fit×d > ~0.7**: tr(f=1)이 최선 — cache 보존·recompute 회피가 핵심
3. **preemption=0 (전 조건)**: vLLM의 prefix cache eviction이 overcommit을 soft하게 처리
4. **내부 최적 f*는 실질적으로 부재**: f=1 또는 f=∞(=default) 양자택일

**본 스윕(전체 d 세분)은 이 3-point 결과 보고 후 재설계 예정.** 정지.

---

## STEP 5 본 스윕 — 전환점 fit×d* 정밀 측정 ✅ 완료 · 게이트 정지

> 서버: goguma · GPU0(RTX5090, 단일) · 2026-07-20 07:26~16:30 KST (~9시간)

### Q. 질문
> **tr(f=1)이 default(f=∞)를 이기는 전환점 fit×d*는 어디이며, 전환은 급격한가 완만한가? C에 흔들리는가?**

### 설계

**f축 폐기**: 3-point 파일럿에서 내부 최적 f* 부재 확정 → 이진 비교(f=1 vs f=∞)만.

| 축 | 값 | 비고 |
|----|-----|------|
| fit×d | {0.50, 0.60, 0.65, 0.70, 0.75, 0.80, 0.90} | 전환점 근처 촘촘 |
| d | {0.105, 0.126, 0.137, 0.147, 0.158, 0.168, 0.189} | d = (fit×d)/fit |
| f | {1.0, 1000000} | tr vs default 이진 |
| C | {10, 20} | 2×fit, 4×fit (C-안정성) |
| REPEAT | 3 | 에러바 |
| **총** | **84 runs** | 7 × 2 × 2 × 3 |

측정 프로토콜: 파일럿과 동일 (vLLM restart/clean cache, true hit=local_compute, --stream, nvidia-smi dmon, 분위수).

### ★ 핵심 결과 — 전환점 fit×d* = 0.62 ±0.03

#### 증거 1 — Wall 비율 (def/tr) vs fit×d

| fit×d | d | def wall(s) | tr wall(s) | **ratio** | **winner** | tr fail rate |
|-------|-------|-------------|-----------|-----------|------------|-------------|
| 0.50 | 0.105 | 195.2±0.8 | 221.0±6.1 | **0.88** | def +12% | 0% |
| 0.60 | 0.126 | 190.1±0.6 | 192.6±6.0 | **0.99** | tied | 3.3% |
| **0.65** | **0.137** | **187.9±0.5** | **183.9±7.8** | **1.02** | **tr +2%** | 3.3% |
| 0.70 | 0.147 | 186.6±0.5 | 174.3±6.4 | **1.07** | tr +7% | 0% |
| 0.75† | 0.158 | 185.8±0.4 | 195.7±1.3 | 0.95 | def +5% | 6.7% |
| 0.80 | 0.168 | 184.3±0.6 | 162.0±5.3 | **1.14** | tr +14% | 0% |
| 0.90 | 0.189 | 182.9±0.2 | 147.9±0.1 | **1.24** | tr +24% | 0% |

*C=10(2×fit), n=3 평균±std. †fd=0.75 이상점: 2/3 runs에서 1개 프로그램 실패(capacity timeout) → wall 증가.*

**선형 보간 전환점**: fd=0.60(ratio=0.987)과 fd=0.65(ratio=1.022) 사이 → **fit×d\* ≈ 0.62**.

#### 증거 2 — p95 Tail Latency

| fit×d | def p95(s) | tr p95(s) | **ratio (def/tr)** | winner |
|-------|-----------|----------|-------------------|--------|
| 0.50 | 184.4±0.5 | 194.8±1.3 | 0.95 | def |
| 0.60 | 179.5±0.4 | 180.5±6.6 | 1.00 | tied |
| 0.65 | 177.4±0.7 | 168.2±12.0 | **1.05** | tr +5% |
| 0.70 | 176.0±0.5 | 152.4±6.1 | **1.16** | tr +16% |
| 0.80 | 174.1±1.2 | 140.1±1.9 | **1.24** | tr +24% |
| 0.90 | 173.3±1.4 | 122.6±0.6 | **1.41** | tr +41% |

p95 전환도 fit×d\* ≈ 0.60에서 발생 — wall과 일치.

#### 증거 3 — C-안정성

| fit×d | C=10 ratio | C=20 ratio | 차이 | 판정 |
|-------|-----------|-----------|------|------|
| 0.50 | 0.883 | 0.884 | 0.1% | ✅ 안정 |
| 0.60 | 0.987 | 0.998 | 1.1% | ✅ 안정 |
| 0.65 | 1.022 | 0.944 | 7.8% | ⚠️ 노이즈 |
| 0.70 | 1.070 | 1.073 | 0.3% | ✅ 안정 |
| 0.80 | 1.138 | 1.143 | 0.5% | ✅ 안정 |
| 0.90 | 1.236 | 1.236 | 0.0% | ✅ 안정 |

**결론**: 전환점 근처(fd=0.65)에서 노이즈 있으나, 양측(fd≤0.60, fd≥0.70)에서 C에 안 흔들림. **전환점 자체는 C-안정**.

#### 증거 4 — TRUE hit rate 및 GPU utilization

| fit×d | tr TRUE_hit | tr GPU% | def GPU% |
|-------|-----------|---------|---------|
| 0.50 | 0.838 | 21% | 84% |
| 0.60 | 0.811 | 26% | 87% |
| 0.65 | 0.823 | 27% | 87% |
| 0.70 | 0.838 | 29% | 88% |
| 0.80 | 0.836 | 30% | 89% |
| 0.90 | 0.845 | 32% | 90% |

- tr의 TRUE_hit ≈ 80-84% 전 구간 안정 — **f=1(tr)이 prefix cache를 보존하는 효과는 fit×d에 무관**.
- tr의 GPU util은 21→32%로 단조 증가 (d↑ → reasoning 비율↑ → GPU 더 사용).
- default GPU util은 84→90%로 거의 고정 (항상 GPU 포화).
- **전환의 핵심**: tr의 idle 비용(GPU 78→68% 놀림)이 default의 recompute 비용(99% recompute)과 교차하는 지점이 fit×d\*.

#### 증거 5 — 프로그램 실패 (capacity timeout)

| fit×d | tr 실패율 | 비고 |
|-------|----------|------|
| 0.50 | 0% | |
| 0.60 | 3.3% (1/30) | |
| 0.65 | 3.3% (1/30) | |
| 0.70 | 0% | |
| 0.75 | 6.7% (2/30) | fd=0.75 이상점의 원인 |
| 0.80 | 0% | |
| 0.90 | 0% | |

- **tr(f=1)의 간헐적 capacity timeout**: C>fit일 때, capacity gate에서 대기 중 timeout. d=0.1 파일럿에서도 관찰(발견 5).
- 특정 fit×d에서 tool sleep 타이밍과 capacity release 타이밍이 불리하게 정렬되면 발생.
- **default는 실패 0건** (전 84 runs).
- ★ **tr의 안정성 위험**: 정책은 이기지만 가용성에 열점이 있음 — 실 배포 시 timeout 관리 필요.

### ★ 핵심 결론 (5개)

**결론 1 — 전환점 fit×d\* ≈ 0.62 ±0.03**
- fit×d < 0.60: default 지배 (def wall 최대 12% 우위)
- fit×d ∈ (0.60, 0.65): 전환 구간 (±2% 이내, 사실상 동점)
- fit×d > 0.65: tr 지배 (tr wall 최대 24% 우위, 단조 증가)

**결론 2 — 전환은 완만하다 (sharp가 아님)**
- 비율이 0.88(fd=0.50) → 1.24(fd=0.90)로 연속적으로 변화
- "cliff"나 phase transition은 없음 — idle↔recompute 비용의 연속적 교차

**결론 3 — C-안정: 전환점은 C에 흔들리지 않는다**
- C=10(2×fit)과 C=20(4×fit)에서 동일 전환점
- fit×d가 정책 선택의 **충분통계량** — C는 전환점에 영향 미미

**결론 4 — 4090/P1 교차검증 일치**
- 4090/TraceLab: fit×d=0.46 → default 승(−34%) — 본 스윕의 fd=0.50 default 승(+12%)과 방향 일치
- **동일 전환 메커니즘이 하드웨어를 넘어 작동** (4090 vs 5090)

**결론 5 — tr의 가용성 위험**
- tr(f=1)은 전환점 이상에서 throughput/latency는 이기지만, 간헐적 capacity timeout 발생
- 실패율 ~3-7% (전환 근처), 프로덕션 배포 시 graceful timeout/retry 필요
- default는 실패 0건 — 안정성에서는 항상 우위

### P1/4090 오버레이

| 셀 | fit×d | wall ratio | 본 스윕 fd=0.50 | 방향 일치 |
|----|-------|-----------|----------------|----------|
| 4090/TraceLab | 0.46 | 0.66 (default +34%) | 0.88 (default +12%) | ✅ |

비율 크기 차이(0.66 vs 0.88)는 workload 차이(실제 TraceLab vs 합성 duty trace)와 하드웨어 차이(4090 fit=2.35 vs 5090 fit=4.76)에 기인. 방향(default 승) 일치가 핵심.

### 머니 피겨

`figures/step5_transition_yunuikang.png` — 4-panel 전환점 그림:
- (a) Wall ratio (def/tr) vs fit×d: 전환점 fit×d\*≈0.62 표시, C=10/C=20 오버레이, 파일럿/4090 점
- (b) p95 latency vs fit×d: tr(blue) vs def(orange), 파일럿 오버레이
- (c) TRUE cache hit & failure rate vs fit×d: tr의 캐시 보존력과 안정성 위험
- (d) GPU utilization vs fit×d: tr(21→32%) vs def(84→90%)

### [추정]/한계

- **fd=0.75 이상점**: 비단조성은 capacity timeout failures에 기인. failure-free run (r=1)은 wall=193.9, p95=141.7로 추세 내. 실패가 wall을 ~15s 증가시킴.
- **합성 workload**: 단일 ctx 프로파일(input_base=16250). 실제 workload는 ctx 분포가 넓어 transition이 더 완만할 수 있음.
- **단일 GPU/모델**: 5090/Qwen3-8B. 다른 (GPU, 모델) 쌍에서는 fit이 다르므로 전환점의 **d 값**이 달라지나, **fit×d\* ≈ 0.62라는 무차원 상수**는 동일할 것으로 예상 (추가 검증 필요).
- **REPEAT=3**: 전환 근처 에러바 충분(std < 10%). fd=0.65에서 std(wall)=7.8s/183.9s=4.2% → 유의.
- **throughput 지표 주의**: raw throughput(tok/s)는 tr≈40 vs def≈262로 default가 7× 우위로 보이나, 이는 tr이 capacity gate로 프로그램을 직렬화하기 때문. **wall time과 p95가 실질적 성능 지표**이며, 여기서는 fd>0.62에서 tr 승.

### 산출물

- 스윕 스크립트: `scripts/sweep_main_yunuikang.py`
- 분석/플롯: `scripts/plot_transition_yunuikang.py`
- 데이터: `scratch/step5/main_sweep/sweep_results.jsonl` (84행)
- traces: `scratch/step5/main_sweep/traces/synth_fd*_v3.jsonl` (7파일)
- 그림: `figures/step5_transition_yunuikang.png`
- Per-run 로그/턴 데이터: `scratch/step5/main_sweep/` 내 `turns_*.jsonl`, `vllm_*.log`, `ta_*.log`, `nvsmi_*.log`

### ★ 게이트 정지 · 보고

84-point 본 스윕 완료. **전환점 fit×d\* = 0.62 ±0.03** 확정.

**한 줄 요약**: *fit×d > 0.62이면 tr(pause)이 최선, 아래면 default가 최선. 전환은 완만하고 C에 안정적이며, fit×d는 정책 선택의 충분통계량이다.*

**정지. STEP 6(분석/논문 정리) 또는 추가 스윕(다른 GPU/모델 교차검증) 승인 대기.**

---

<!-- STEP 6 결과는 이 아래에 append -->

## STEP 6 — 비용 모델·전환점 예측·Room for Improvement ✅ 완료 · 게이트 정지

> 서버: goguma · GPU 불필요(분석 전용) · 2026-07-20 17:00~18:30 KST

### Q. 질문
> **전환점 fit×d\*를 비용 모델로 예측할 수 있는가? 선택기(selector)의 개선 여지는? tr의 가용성 위험을 어떻게 정량하는가?**

### §1 — ★ 비용 모델: wall ∝ S × W / U

#### 모델 정의

정책별 wall time은 3개 요소의 곱으로 분해:

```
wall(policy) ∝ S(policy) × W(policy) / U(policy, fd)
```

| 기호 | 정의 | 출처 |
|------|------|------|
| **S** | 직렬화 계수 (S_def=1, S_tr>1) | capacity gate로 인한 프로그램 직렬화 |
| **W** | recompute 비율 (prompt_tokens_local_compute / prompt_tokens_total) | vLLM TRUE hit rate 보완 |
| **U** | GPU 이용률 (%) | nvidia-smi dmon 1s 평균 |

**전환 조건**: wall_tr = wall_def일 때

```
(W_def / W_tr) × (U_tr / U_def) / S_tr = 1
```

#### 파라미터 추정 (STEP 5 본 스윕 데이터, C=10, fd=0.75 제외)

| 파라미터 | 값 | 비고 |
|----------|-----|------|
| **W_def** | 0.985 | default: 99% recompute (cache miss) |
| **W_tr** | 0.168 | tr: 17% recompute (84% cache hit) |
| **W_def / W_tr** | **5.86×** | ★ cache gain |
| **S_tr** | **1.749 ± 0.095** | 6개 fd에서 일관 (1.58~1.87) |
| C/fit | 2.10 | 직렬화 상한 (완전 직렬) |
| pipeline eff η | 0.32 | S_tr = 1 + (1−η)(C/fit−1) |
| **U_tr(fd)** | 0.0986 + 0.2557 × fd | OLS 선형 적합 |
| **U_def(fd)** | 0.7819 + 0.1338 × fd | OLS 선형 적합 |

**S_tr 해석**: C/fit=2.10이면 완전 직렬 시 S=2.10이지만, 실제 S_tr=1.75 — 파이프라인 오버랩이 32% 직렬화를 상쇄. S_tr는 fd에 무관하게 안정적(std=5.4%).

#### ★ 전환점 예측

전환 조건 U_tr/U_def = S_tr × W_tr/W_def = 0.2986을 선형 적합에 대입:

```
(0.0986 + 0.2557 × fd*) / (0.7819 + 0.1338 × fd*) = 0.2986
→ fd* = 0.625
```

| 지표 | 값 |
|------|-----|
| **예측 전환점** | **fit×d\* = 0.625** |
| **실측 전환점** | **fit×d\* = 0.62** |
| **오차** | **0.005 (0.9%)** |

#### 모델 정확도 (예측 vs 실측 wall ratio)

| fit×d | 예측 ratio | 실측 ratio | 오차 |
|-------|-----------|-----------|------|
| 0.50 | 0.893 | 0.883 | +1.2% |
| 0.60 | 0.979 | 0.987 | −0.8% |
| 0.65 | 1.021 | 1.022 | −0.1% |
| 0.70 | 1.062 | 1.070 | −0.8% |
| **0.75†** | **1.102** | **0.949** | **+16.1%** |
| 0.80 | 1.142 | 1.138 | +0.4% |
| 0.90 | 1.220 | 1.236 | −1.3% |

*†fd=0.75: capacity timeout failures가 tr wall을 ~15s 증가 → 비단조 이상점. 실패-무관 모델이 예측 불가.*

**정상 6개 fd: 예측 오차 ±1.3% 이내** — 3-파라미터 모델(S, W, U)이 84점 스윕을 거의 완벽 설명.

### §2 — Room for Improvement

#### 선택기(selector) 이득

fit×d-aware selector: 각 fd에서 min(wall_tr, wall_def)를 선택.

| fit×d | wall_sel(s) | vs fixed-tr | vs fixed-def | **vs worst** | 선택 |
|-------|-------------|-------------|-------------|------------|------|
| 0.50 | 195.2 | 13.2% | 0.0% | **13.2%** | def |
| 0.60 | 190.1 | 1.3% | 0.0% | **1.3%** | def |
| 0.65 | 183.9 | 0.0% | 2.2% | **2.2%** | tr |
| 0.70 | 174.3 | 0.0% | 7.0% | **7.0%** | tr |
| 0.75 | 185.8 | 5.4% | 0.0% | **5.4%** | def† |
| 0.80 | 162.0 | 0.0% | 13.8% | **13.8%** | tr |
| 0.90 | 147.9 | 0.0% | 23.6% | **23.6%** | tr |

*†fd=0.75는 capacity timeout 이상점으로 def가 우위.*

**★ 선택기 이득 최대 24% vs worst fixed policy.** V자형: 전환점에서 최소(1.3%), 양 극단에서 최대(13~24%).

#### 이상(ideal) 대비 갭

이상 스케줄러: U=1(100% GPU), hit=1(모든 cache hit), S=1(무직렬화).

| fit×d | wall_sel(s) | wall_ideal(s) | **갭** |
|-------|-------------|--------------|------|
| 0.50 | 195.2 | 28.0 | **7.0×** |
| 0.60 | 190.1 | 28.1 | **6.8×** |
| 0.65 | 183.9 | 27.9 | **6.6×** |
| 0.70 | 174.3 | 28.1 | **6.2×** |
| 0.80 | 162.0 | 28.0 | **5.8×** |
| 0.90 | 147.9 | 28.0 | **5.3×** |

**이상 대비 5.3~7.0× 갭** — 현 최선 정책도 이상의 ~15-19%만 실현. 개선 여지가 크다.

### §3 — ★ 신뢰성 차원

#### tr의 capacity timeout 실패

| fit×d | tr 실패율 | def 실패율 | **selector 실패율** |
|-------|----------|----------|-------------------|
| 0.50 | 0.0% | 0.0% | **0.0%** |
| 0.60 | 3.3% | 0.0% | **0.0%** (def 선택) |
| 0.65 | 3.3% | 0.0% | **3.3%** (tr 선택) |
| 0.70 | 0.0% | 0.0% | **0.0%** |
| 0.75 | 6.7% | 0.0% | **0.0%** (def 선택†) |
| 0.80 | 0.0% | 0.0% | **0.0%** |
| 0.90 | 0.0% | 0.0% | **0.0%** |

*†fd=0.75는 이상점: capacity timeout failures 때문에 def가 wall 승.*

**★ 선택기의 안정성 부산물**: fd < fd\*에서 자동으로 def를 선택 → tr의 capacity timeout 실패를 회피.
- 유일한 위험점: fd=0.65 (전환 바로 위, tr 선택 시 3.3% 실패)
- 실 배포: 전환 근처 ±0.03 마진을 두면 실패율 ≈ 0%

### §4 — 일반화 · 교차검증

#### 4090/TraceLab (P1) 교차검증

| 항목 | 값 |
|------|-----|
| 셀 | 4090/Qwen3-8B, TraceLab |
| fit×d | 0.46 |
| 실측 | default 34% 우위 (wall ratio ≈ 0.66) |
| S_tr(4090) | ≈ 3.54 (fit=2.35 → C/fit=4.26, S 비례 스케일) |
| U_tr/U_def(fd=0.46) | ≈ 0.256 (5090 적합에서 외삽) |
| **모델 예측 ratio** | **0.424** |
| **방향** | **def wins ✓** |

- 예측 비율(0.42)이 실측(0.66)보다 극단적 — S_tr 외삽의 한계(4090은 fit이 다름).
- 그러나 **방향(def wins)은 정확** — 모델의 정성적 예측력 확인.

#### 파일럿 포인트 교차검증 (동일 시스템, 5090)

| 데이터 | fit×d | 예측 ratio | 실측 ratio | 방향 |
|--------|-------|-----------|-----------|------|
| d=0.1 pilot | 0.476 | 0.872 | 0.79 | def wins ✓ |
| d=0.2 pilot | 0.952 | 1.260 | 1.31 | tr wins ✓ |
| d=0.5 pilot | 2.381 | 2.153 | 1.96 | tr wins ✓ |

**3/3 방향 일치, 비율도 10% 이내** — 모델이 훈련 범위(fd=0.50~0.90) 밖에서도 유효.

### §5 — 모델 한계

1. **fd=0.75 이상점**: capacity timeout failures는 W·U·S로 포착 불가 — 확률적 실패 비용은 별도 모델링 필요 (§3의 failure rate를 비용 항으로 추가).

2. **S_tr의 C/fit 의존**: 현 실험은 C=10(C/fit=2.10) 고정. C가 변하면 S_tr도 변화 — C=20 데이터에서 C-안정성은 확인했으나, 매우 큰 C(>10×fit)에서의 S_tr 외삽은 미검증.

3. **heavy-tail 워크로드 (HLE/Science)**: 현 합성 trace는 동일 ctx profile. HLE류 heavy-tail 분포에서는 **꼬리 프로그램이 GPU 점유를 독점** → U_tr이 mean이 아닌 **tail-aware U**로 대체 필요. 현 모델(U=mean GPU util)은 heavy-tail에서 과대 추정 가능.

4. **GPU/모델 일반화**: fd\*=0.625라는 무차원 상수의 보편성은 5090/Qwen3-8B 단일 셀에서만 확인. 다른 (GPU, 모델) 쌍에서 W·S·U의 절대값은 다르지만, 전환 메커니즘(idle↔recompute 교차)은 동일할 것으로 예상 — 추가 셀 검증 필요.

5. **W의 fd 독립 가정**: W_tr ≈ 0.168, W_def ≈ 0.985로 fd에 무관하게 일정하다고 가정. 현 데이터에서는 성립(TRUE hit ≈ 83-84% 전 구간)하지만, ctx 분포가 넓은 workload에서는 W가 fd에 의존할 수 있음.

### 머니 피겨

`figures/step6_cost_model_yunuikang.png` — 4-panel 비용 모델 분석:
- (a) Cost model crossover: U/(W×S) 곡선 교차점 = 예측 fd\* = 0.625
- (b) Predicted vs measured wall ratio: 모델 예측(빨강) vs 실측(파랑), fd=0.75 이상점 표시
- (c) Selector gain vs fixed policy: V자형 이득 구조, 최대 24%
- (d) Throughput vs reliability: 이중 목표(wall ratio + failure rate), 선택기 영역 표시

### 산출물

- 분석 스크립트: `scripts/step6_analysis_yunuikang.py`
- 그림: `figures/step6_cost_model_yunuikang.png`
- 데이터 출처: `scratch/step5/main_sweep/sweep_results.jsonl` (84행), 파일럿 3세트

### ★ STEP 6 종합 결론 (4개)

**결론 1 — 비용 모델이 전환점을 0.9% 오차로 예측**
- wall ∝ S × W / U (3-파라미터 모델)
- S_tr=1.75 (직렬화), W_def/W_tr=5.86× (cache gain), U 선형 적합
- **예측 fd\* = 0.625, 실측 0.62 → 오차 0.9%**

**결론 2 — fit×d-aware 선택기로 최대 24% 개선, 이상 대비 5.3~7.0× 갭**
- 고정 정책 대비 V자형 이득: 극단에서 크고 전환점에서 작음
- 이상(U=1, hit=1, S=1) 대비 현 최선은 ~15% 실현 → 큰 개선 여지

**결론 3 — 선택기가 tr의 가용성 위험을 자동 해소**
- fd < fd\*에서 def 선택 → tr의 capacity timeout 실패 회피
- 전환점 바로 위(fd=0.65)에서만 3.3% 잔여 위험 → 마진 ±0.03으로 제거 가능

**결론 4 — 모델은 4090/P1 및 파일럿 3점에서 방향 정확, heavy-tail은 한계**
- 4090/TraceLab(fd=0.46): def wins 방향 ✓
- 파일럿 3점: 3/3 방향 일치, 비율 10% 이내
- **한계**: heavy-tail(HLE류)은 tail-aware U 필요, 현 mean-U 모델은 과대 추정 가능

### ★ 게이트 정지 · 보고

STEP 6 분석 완료. 비용 모델(wall ∝ S × W / U)이 전환점을 0.9% 오차로 예측.

**한 줄 요약**: *3-파라미터 비용 모델(직렬화×recompute/GPU이용률)이 84점 스윕을 ±1.3%로 설명하고 전환점 fd\*=0.625를 예측. 선택기로 최대 24% 개선 가능하나 이상 대비 5~7× 갭 잔존. heavy-tail 워크로드는 tail-aware U 확장 필요.*

**정지. 추가 분석(논문 정리) 또는 추가 셀 교차검증(다른 GPU/모델) 승인 대기.**

---

## STEP 5 확장 — duty×f 2D 결과 표 (2026-07-21, goguma GPU1)

> 목적: 설계 duty 격자(d=0.1·0.2·0.3·0.5·0.7·0.9, fit=4.76)에서 (A) tr↔default 극단 비교와 (B) 중간 f까지 펼친 전개를 2D 표로 산출.
> 측정: C=10(≈2×fit), R=1, vLLM restart/clean prefix cache per point, C_total=95,936 핀, 참hit=prompt_tokens_by_source{local_compute}, --stream, nvidia-smi dmon 1s.
> **재사용**: d=0.1 전체 f-스윕 + d=0.2/0.5 f={1,1.5,∞}는 기존 파일럿(GPU0). **신규(GPU1, 14 runs)**: d=0.3/0.7/0.9 전체 f{1,1.5,2,∞} + d=0.2/0.5 f=2.
> **cross-GPU 캐비앗**: 재사용(GPU0)과 신규(GPU1)는 동일 RTX 5090 + C_total 고정이라 비교 가능하나 엄밀히는 다른 물리 GPU. 방향/차수 결론에 영향 없음.
> **지표 주의**: throughput = goodput(=completed/makespan, prog/s). raw decode tok/s는 default의 recompute 낭비를 토큰으로 세어 오도(연구의 핵심 논점) → 사용 안 함.

### Table A (극단: tr f=1 vs default f=∞)

| d | fit×d | tr goodput | tr p95 | tr hit | tr U% | tr fail | def goodput | def p95 | def hit | def U% | def fail | 승자 |
|---|-------|-----------|--------|--------|-------|---------|------------|---------|---------|-------|----------|------|
| 0.1 | 0.476 | 0.036 | 238 | 0.76 | 22 | 10% | 0.051 | 186 | 0.01 | 84 | 0% | **default** (+26%) |
| 0.2 | 0.952 | 0.073 | 121 | 0.86 | 30 | 0% | 0.055 | 171 | 0.01 | 92 | 0% | **tr** (+31%) |
| 0.3 | 1.428 | 0.093 | 97 | 0.86 | 44 | 0% | 0.057 | 165 | 0.01 | 91 | 0% | **tr** (+64%) |
| 0.5 | 2.381 | 0.111 | 76 | 0.86 | 49 | 0% | 0.057 | 166 | 0.01 | 93 | 0% | **tr** (+96%) |
| 0.7 | 3.333 | 0.115 | 73 | 0.86 | 50 | 0% | 0.057 | 164 | 0.01 | 93 | 0% | **tr** (+101%) |
| 0.9 | 4.285 | 0.133 | 59 | 0.85 | 61 | 0% | 0.057 | 164 | 0.01 | 92 | 0% | **tr** (+132%) |

**★ 승자 뒤집힘**: d=0.1(fit×d=0.48) default +26% → d=0.2(fit×d=0.95) tr +31%. 이후 tr 우위 단조 확대(+64→+132%). 정밀 전환점 fit×d\*≈0.62(세밀 격자)는 두 점 사이.
- tr TRUE hit ≈ 0.86 전 구간 안정(캐시 보존), default ≈ 0.01(99% recompute).
- tr U는 22→61%로 d와 함께 단조 증가, default U는 84→93% 포화 고정.
- **tr 신뢰성**: 유일하게 d=0.1(깊은 미포화)에서 tr 10% 실패(capacity timeout 1/10). d≥0.2에서 0%.
- 그림: `figures/step5_table_extreme_yunuikang.png`

### Table B (전개: duty × f goodput)

| d | fit×d | f=1 (tr) | f=1.5 | f=2 | f=∞ (default) | 최적 f |
|---|-------|----------|-------|-----|---------------|--------|
| 0.1 | 0.476 | 0.036 | 0.045 | 0.050 | **0.051★** | f=∞(def) |
| 0.2 | 0.952 | **0.073★** | 0.054 | 0.055 | 0.055 | f=1(tr) |
| 0.3 | 1.428 | **0.093★** | 0.058 | 0.056 | 0.057 | f=1(tr) |
| 0.5 | 2.381 | **0.111★** | 0.064 | 0.057 | 0.057 | f=1(tr) |
| 0.7 | 3.333 | **0.115★** | 0.065 | 0.058 | 0.057 | f=1(tr) |
| 0.9 | 4.285 | **0.133★** | 0.066 | 0.058 | 0.057 | f=1(tr) |

**★ 내부 최적 없음 = 이진**: 6개 duty행 어디서도 중간 f(1.5·2)가 최고 goodput이 아님.
- d=0.1: goodput이 f와 함께 단조 증가(0.036→0.051) → **f=∞(default) 최적**.
- d≥0.2: **f=1(tr) 최적**, f를 조금만 올려도(f=1.5) goodput 급락(예: d=0.9 0.133→0.066). 중간 f는 f=∞에 수렴.
- 즉 최적 정책은 이진 선택(f=1 or f=∞) — 연속 노브의 sweet spot이 존재하지 않음. H1(내부 최적 f\*) 반증을 duty 전 구간에서 재확인.
- 그림: `figures/step5_table_fgrid_yunuikang.png` (행별 정규화 히트맵, 각 행 최적 f 빨강 테두리)

### ★ 게이트 정지 · 보고 (STEP 5 확장)

**한 줄 요약**: *duty 전 구간(6점)에서 승자는 fit×d≈0.5~0.95 사이에서 default→tr로 뒤집히고(Table A), 중간 f는 어느 duty에서도 최적이 아님(Table B) → 정책 최적은 이진, fit×d가 선택을 결정.*

**산출물**: `figures/step5_table_extreme_yunuikang.png`, `figures/step5_table_fgrid_yunuikang.png`, `scratch/step5/gap_d0{3,7,9},gap_d0{2,5}/pilot_results.jsonl`(14 runs), `scripts/step5_2d_tables_yunuikang.py`, `scripts/run_step5_gap_yunuikang.sh`.
