# ThunderAgent 메커니즘 레퍼런스 — cost model·policy ↔ 코드 (Phase 0)

> ## 🚨 2026-07-17 정정 — **§1-1 표의 `Cost_unused` 설명이 논문과 다르다.**
> 아래 §1-1은 `Cost_unused`를 *"GPU에 올려뒀지만 tool 실행 중이라 놀고 있는 KV 점유"* 로 적었으나, **논문 p.6 §4.2 원문은**
> (28p·34p **양쪽 동일**, 실측 확인):
> > *"**Cost_unused** reflects **memory imbalance across data parallel (DP) inference backend replicas** (Section 3.2);
> > and **Cost_caching** accumulates while **holding memory during external tool execution** (Section 3.3)."*
>
> → **tool 시간에 과금하는 항은 `Cost_unused`가 아니라 `Cost_caching`이다.** §1-1·§1-3 표의 "unused" 행을 **`Cost_caching`으로 교체**할 것.
> (코드의 `tool_coefficient`·`2^(-t)` 감쇠가 대응하는 논문 항도 `Cost_caching`이다.) 리뷰어가 즉시 잡을 종류의 오류.
> 근거·전체 정정표: `logs/2026-07-17_VLLM_PROFILING_yunuikang.md` §5-0·§5-0b. 또한 **"Appendix E.2" 인용은 34p본에서 `Appendix F.2`로 바뀌었다**(E↔F 교환).

> 작성: 강윤의 · 브랜치 `yunuikang/thunderagent` · 2026-07-06
> 목적: 지도교수 피드백 (a) "알고리즘(cost model·policy)을 먼저 정확히 이해→그 로직으로 결과 설명".
> 이 문서는 **논문 §4 ↔ 실제 코드(파일:라인) 1:1 매핑**이며, 이후 D/F/G 및 실험 C·D의 모든 해석은
> 여기 정의된 판단 로직을 인용해 "tr이 이렇게 판단→이렇게 행동→그래서 이 현상"으로 서술한다.
> 근거 코드: `ThunderAgent/scheduler/router.py`, `backend/state.py`, `backend/vllm_metrics.py`,
> `program/state.py`, `config.py`. 근거 논문: `assets/paper/_Arxiv__ThunderAgent.pdf` §4.

---

## 0. 한 줄 요약

ThunderAgent(`--router tr`)는 논문의 연속-시간 **STP 비용(5항)을 직접 최소화하지 않는다.** 대신
그 비용을 **하나의 용량-실현가능성 부등식**(Eq.6의 운영판)으로 이산화해서, "백엔드의 활성 프로그램 KV 합이
KV 풀을 넘으면 스래싱"이라는 조건을 매 `--scheduler-interval`(기본 5s)마다 검사하고,
**pause(내보내기) / resume(다시 넣기) / 신규배정**의 세 가지 행동으로 그 부등식을 유지한다.
`--router default`는 이 로직을 **전부 끄고** 최소부하 백엔드로 프록시만 한다.

---

## 1. Cost model: 논문 §4.2 STP(5항) ↔ 코드의 용량 부등식

### 1-1. 논문이 말하는 것 (의도)
논문 §4.2는 스케줄링 품질을 **STP(Scheduling Time Penalty)** = 아래 5개 시간/토큰 비용의 합으로 정의하고,
스케줄러는 이 합을 **최소화**하는 방향으로 프로그램을 배치·pause·resume한다:

| STP 항 | 의미 | 최소화하려는 것 |
|--------|------|-----------------|
| **decode** | 생성(디코드) 시간 | 정상 진행(불가피) |
| **prefill** | 프롬프트 프리필 시간 | 첫 진입 비용(불가피) |
| **recompute** | 캐시가 evict돼 **다시 프리필**하는 비용 | ★ 스래싱의 핵심 낭비 — 줄여야 함 |
| **unused** | GPU에 올려뒀지만 tool 실행(ACTING) 중이라 **놀고 있는** KV 점유 | ★ 과점유 낭비 — 줄여야 함 |
| **caching** | prefix 캐시로 **절약된** 비용(음의 비용) | ★ 늘려야 함(재사용 이득) |

즉 STP 최소화 = **recompute(재프리필)·unused(놀고있는 점유)를 줄이고 caching(재사용)을 늘린다.**

### 1-2. 코드가 실제로 하는 것 (구현)
코드는 5항을 각각 적분하지 않는다. 대신 **백엔드별 용량 부등식** 하나로 그 취지를 근사한다.

`backend/state.py`의 핵심 3식:

```
active_program_tokens = reasoning_tokens + tool_coefficient · acting_tokens      # state.py:104-107
shared_tokens         = max(0, reasoning_tokens − kv_cache_usage_perc · C_total)  # vllm_metrics.py:294-311
remaining_capacity    = C_total − (active_program_tokens − shared_tokens + buffer) # state.py:185-194
```
- `C_total` = `block_size × num_gpu_blocks` = 백엔드 KV 풀 토큰 용량(4090=43,888, 5090=89,040 실측).
- `buffer` = `active_program_count × BUFFER_PER_PROGRAM(=100)` — 프로그램당 디코드 여유.
- **스래싱 판정** = `remaining_capacity() < 0` ⇔ `active_tokens − shared_tokens + buffer > C_total`
  = **논문 Eq.(6)** `Σ c_p > C_total`의 운영판. (`_scheduled_check` router.py:770)

### 1-3. 5항 ↔ 코드 대응 (이 표가 핵심)

| STP 항 | 코드에서 어떻게 반영되나 | 근거 |
|--------|--------------------------|------|
| **recompute** | 부등식을 위반하면 pause해서 **애초에 evict가 안 나게** 함 → recompute를 사전 차단. (evict=재프리필은 조사 A 참조) | `_pause_until_safe` router.py:773 |
| **unused** | ACTING 프로그램 토큰에 `tool_coefficient`(=`--acting-token-weight`, 기본 1.0) 가중. resume 판정에선 `2^(-t)` 감쇠로 "곧 안 돌아올 ACTING은 덜 센다" | `active_program_tokens` state.py:107; `remaining_capacity_with_decay` state.py:196-214 |
| **caching** | `shared_tokens`(prefix 캐시로 절약된 실측 토큰)를 **used에서 빼줌** → 재사용이 많을수록 용량이 넉넉해짐 | `calculate_shared_tokens` vllm_metrics.py:294 |
| **decode/prefill** | 불가피 비용이라 별도 최소화 안 함. `buffer`(프로그램당 100토큰)로 디코드 여유만 확보 | `BUFFER_PER_PROGRAM` state.py:23 |

**★ 정직 포인트(발표 시 명시)**: 논문은 "가중 5항 비용을 최소화"라고 서술하지만, **이 구현은 그 비용을
최소화하는 최적화 문제를 풀지 않는다.** 대신 "스래싱 부등식을 위반하면 위반이 사라질 때까지 가장 작은
프로그램부터 pause"라는 **탐욕적 feasibility 유지**로 대체한다. 따라서 우리가 "cost model" 을 말할 때는
(i) **의도** = STP 5항, (ii) **구현** = 용량 부등식 + 탐욕 pause/resume 을 구분해서 말해야 한다.
이 간극이 D에서 tr이 throughput을 잃는 이유와 직접 연결된다(§4).

---

## 2. Policy: 세 가지 결정의 "목적"과 코드

스케줄러 루프(`_scheduler_loop` → `_scheduled_check`, router.py:746-771)는 매 5s:
1. 백엔드 metrics fetch, 2. `_greedy_resume()`(넣기), 3. 각 백엔드 `remaining_capacity()<0`이면 `_pause_until_safe()`(빼기).
데이터플레인(`update_program_before_request`, router.py:371-458)은 요청 도착 시 신규배정/대기를 처리.

### 2-1. 신규 프로그램 배정 — "절대 토큰 균형"(용량 비례 아님) ★
`_select_backend_for_new_program` (router.py:330-362):
```
if len(global_waiting_queue) > 0: return None      # 대기 큐 있으면 무조건 대기(공정성)
required = estimated_tokens + BUFFER_PER_PROGRAM
후보 = 건강 && remaining_capacity() ≥ required 인 백엔드
선택 = 후보 중 active_program_tokens 가 최소인 백엔드      # ← L358
```
- **목적(의도)**: 어떤 백엔드도 혼자 과부하되지 않게 토큰을 고르게 분산.
- **★ 핵심 관찰**: 선택 기준이 `active_program_tokens`의 **절대값 최소**이고 **`C_total`로 나누지 않는다.**
  즉 5090(큰 풀)과 4090(작은 풀)을 **같은 절대 토큰 기준**으로 취급 → 용량이 2배인 5090에 2배 더
  보내지 **않는다.** 이것이 F/G에서 관측된 "tr split ≈ 1:1 ≪ 용량비 1:2.03, 5090 과소활용"의 **직접 원인**.
- **대조 default**: `select_backend_for_new_program_default` (router.py:252-271) — **프로그램 개수**가 최소인
  백엔드(토큰 무관, 용량 무관). 더 단순한 절대 균형.

### 2-2. pause — "스래싱이면 ACTING부터, 작은 것부터" ★
`_pause_until_safe(backend)` (router.py:773-805), `remaining_capacity()<0`인 동안 반복:
```
1순위: ACTING 프로그램들 중 total_tokens 최소 → _pause_program (즉시 GPU에서 빼기)
2순위: (ACTING 없으면) REASONING 최소 → _mark_program_for_pause (다음 ACTING 될 때 빼도록 예약)
```
- **목적**: Eq.6 위반(스래싱) 해소. **ACTING 먼저** 빼는 이유 = ACTING은 tool 실행 중이라 지금 GPU를
  안 쓰므로(=unused 항) 빼도 진행 손해가 가장 적음. **작은 것부터** 빼는 이유 = 최소 개수 pause로 부등식 회복.
- **행동 결과**: `_pause_program`(router.py:631-658)은 백엔드에서 unregister + `global_waiting_queue`에 넣고
  `backend_url=None`. 그 프로그램의 다음 요청은 `update_program_before_request`에서 `_wait_for_resume`로
  **프록시에서 블록**(router.py:416-419) → GPU에 안 감 → **resident(동시 실행) 수가 줄어든다.**
  이게 "tr이 병렬성을 희생"의 메커니즘.

### 2-3. resume — "대기중 요청 우선(REASONING) + BFD 배치" ★
`_greedy_resume()` (router.py:807-932):
```
용량 = Σ 백엔드 remaining_capacity (decay 켜면 remaining_capacity_with_decay)   # 낙관적
우선순위 = REASONING(step>1) > NEW(step=1) > ACTING, 각 그룹 토큰 오름차순
1단계: 우선순위 순서로 누적토큰 ≤ 총용량 인 최대집합 선택
2단계: BFD — 선택된 것을 토큰 내림차순, 가장 여유 큰 백엔드에 배치, 배치할 때마다 재정렬
```
- **목적**: 용량이 생기면 **대기중(pending 요청 있는=REASONING) 프로그램을 먼저** 되살려 지연을 줄이고,
  bin-packing(BFD)으로 조각화를 줄여 최대한 많이 넣는다.
- **decay(`--use-acting-token-decay`, 논문 f(t)=2^(-t))**: resume **용량 추정에만** 적용. ACTING 프로그램은
  tool 시작 후 시간이 지날수록(t↑) 곧 GPU를 비울 것으로 보고 그 토큰을 `2^(-t)`로 할인 →
  **더 낙관적으로 더 많이 resume**. pause 판정(`_scheduled_check` step3)은 감쇠 없는 원래 용량 사용(보수적).

### 2-4. migration — "paused는 아무 여유 백엔드로"
`_resume_program(state, target_backend)` (router.py:692-725)은 `target`이 `origin`과 **달라도** 된다.
BFD가 origin이 아닌 백엔드를 고르면 그게 곧 migration.
- **목적/전제**: 논문 §4.3.2 — paused 프로그램의 KV는 이미 evict됐다고 가정하므로 **재프리필 비용이
  노드 무관(node-agnostic)** → "어디로 restore해도 같다" → 용량·부하만 보고 배치. (조사 A에서 이 전제가
  우리 이종 환경에서 왜 문제인지, 논문 비교문서 §4-2와 연결.)

---

## 3. 요청 생애주기 상태기계 (그림 대체)

```
       요청 도착 (update_program_before_request)
              │
              ▼
        [REASONING]  ── GPU에서 vLLM 추론(프리필+디코드) ──►  응답 완료
        (status)                                                │
              ▲                                                 ▼
     resume   │                                       [ACTING] status
   (_greedy_  │                                    (off-GPU, tool 실행/유휴)
    resume)   │                                                 │
              │                                    scheduler: Eq.6 위반이면
        [PAUSED] state ◄── _pause_program ◄────────  가장 작은 ACTING pause
    (global_waiting_queue,                                      │
     backend_url=None,                              _wait_for_resume 로
     다음 요청은 프록시 블록)                          다음 요청 블록됨
```
- **status**(무엇을 하는가): REASONING(GPU 추론) ↔ ACTING(tool/유휴). `program/state.py:11-18`.
- **state**(생애): ACTIVE → PAUSED(큐에서 대기) → resume 시 ACTIVE / release 시 TERMINATED. `state.py:21-31`.
- default 모드는 PAUSED/큐/scheduler가 전부 없음 — 항상 ACTIVE, 최소부하 백엔드로 직행(router.py:394-406).

---

## 4. 이 로직으로 기존 결과 재서술 (템플릿)

이후 모든 해석은 아래 흐름을 따른다. 예시(D −34%):

> **판단**: median 18k 프로그램이 4090 KV풀(43,888 tok)에 ~2개만 적재(조사 B) → c≥8에서
> `remaining_capacity()<0`(Eq.6 위반, §1-2). **행동**: `_pause_until_safe`가 가장 작은 ACTING을 pause
> (§2-2) → 그 요청이 `_wait_for_resume`로 프록시에서 블록(§2-3) → **resident 수↓**. **현상**: GPU가 덜
> 채워져 throughput↓·pause 대기로 p95↑, 그러나 evict를 사전 차단해 **hit rate 0.77 유지**(§1-3 recompute 차단).
> **인과 확정(실험 C 예정)**: `--use-acting-token-decay`로 resume를 더 낙관적으로(§2-3) 만들면 resident↑ →
> throughput이 default 쪽으로 회복되는지로 "pause가 원인"임을 증명.

그리고 F/G의 "5090 과소활용"은 §2-1(신규배정이 용량 비례가 아니라 절대 토큰 균형, L358)이 직접 원인 —
**용량 비례 라우팅**이 필요하다는 연구 방향의 코드적 근거가 바로 이 한 줄이다.

---

## 부록: 파일:라인 인덱스 (빠른 참조)

| 개념 | 파일:라인 |
|------|-----------|
| 용량 부등식(Eq.6 운영판) | `backend/state.py:185-194` (`remaining_capacity`) |
| caching 항(shared_tokens) | `backend/vllm_metrics.py:294-311` |
| unused 항(acting 가중) | `backend/state.py:104-107`; decay `state.py:196-214` |
| 신규배정=절대토큰균형 ★ | `scheduler/router.py:358` (`_select_backend_for_new_program`) |
| default 신규배정=프로그램수 | `scheduler/router.py:252-271` |
| pause(ACTING·최소부터) | `scheduler/router.py:773-805` (`_pause_until_safe`) |
| resume(REASONING우선·BFD) | `scheduler/router.py:807-932` (`_greedy_resume`) |
| migration(origin≠target) | `scheduler/router.py:692-725` (`_resume_program`) |
| pause 시 요청 블록 | `scheduler/router.py:416-419` (`_wait_for_resume`) |
| 스케줄러 루프(5s) | `scheduler/router.py:746-771` |
| tr/default 분기 | `scheduler/router.py:394` (`if not self.scheduling_enabled`) |
