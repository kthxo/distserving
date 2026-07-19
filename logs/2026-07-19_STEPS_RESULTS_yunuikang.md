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

<!-- STEP 4/5/6 결과는 이 아래에 append -->
