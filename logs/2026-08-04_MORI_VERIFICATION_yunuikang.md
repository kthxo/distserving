# MORI 코드 검증 종합 보고서

- 작성: 2026-08-04 / 브랜치: `mori` (distserving) / **커밋 없음** — 워킹트리 유지
- 대상: MORI 논문("Idleness is Relative: Exploiting Tool-Call Idle Windows for Offloading",
  arXiv:2606.00866)을 ThunderAgent + SGLang(HiCache) 위에 구현한 코드
- 하드웨어: goguma6, RTX 5090 ×2 (sm_120), Qwen3-8B TP2, SGLang HiCache 실엔진
- 이 문서는 STEP 1~7의 원본 로그 5개를 **통합**한 것이다(요약 아님). 원본은 그대로 보존한다 — §8.3.
- 라벨 규율: **[측정]** = 실행/코드 열람으로 관측한 값 · **[추론]** = 관측으로부터의 해석 ·
  **[논문-인용]** = 논문 §번호 근거

---

# 0. 한 페이지 요약

## 0.1 검증 목표
**"코드가 MORI 논문 정책대로 작동하는가"**만 본다. 과거 실험 결과(특정 throughput 등)를
정당화하려는 것이 **아니다**. 테스트의 정답은 "현재 코드가 내는 값"이 아니라 **논문 정책 스펙**이며,
현재 동작을 역으로 베껴 무조건 통과하는 테스트를 만들지 않았음을 mutation testing으로 증명했다(§1.2).

## 0.2 결론

| 계층 | 범위 | 결과 |
|---|---|---|
| **A — 정책 충실성** (white-box, known-answer) | A1~A7f 17개 | **17/17 PASS** (최초 13/14 → A7c 수정 후 17/17) |
| **B — 거시 행동** (black-box, 실측) | B0~B3 | 핵심 3개 ✅ PASS, 1개 ⚠️ 미확정 |
| **C — 유용한 일** (goodput/시간분해) | ①~⑤ | 전 항목 산출, C80 thrashing 정량 확정 |

**A 계층 [측정]**: 논문 §4.2(idleness 식1) / §4.3.1(demote·promote 랭킹) / §4.3.2(typed eviction)의
정책이 코드에 충실히 구현돼 있다. 스티키 배치, ι 최고 demote, ACTING 우선, REASONING lazy demotion,
그룹 우선순위 후 그룹 내 ι 최소 promote, 양쪽 tier admission control, **논문 제목의 상대성
(GPU 2칸→3칸에서 분할 경계가 ι≤0.4 → ι≤0.6으로 실제 이동)** 이 모두 확인됐다.

**B 계층 [측정]**: MORI의 심장이 실런에서 작동한다 — cpu_tier가 0→1이 되는 **바로 그 시각**에
GPU KV가 6,258 토큰 감소(해당 프로그램 KV 6,583과 일치)했고, promote 시각에 host→device reload가
+13,240 토큰 발생했으며, CPU→Waiting 축출은 C≤10에서 **0건**(전 구간 ≤1.3%)이었다.

**C 계층 [측정]**: 건강 구간(oversub 1.0~1.2×)에서 MORI는 SLO 5초 만족률 **99.6%**,
goodput ≈ throughput, pause 점유 **0.9%**로 오프로딩이 지연 비용 없이 작동한다.
극단 구간(9.9×)에서는 분당 27.7회 tier 왕복(ping-pong 90.7%)으로 prefix cache가 붕괴(0.944→0.600),
토큰 작업의 40%가 recompute, 요청의 75%가 스케줄러 대기(중앙값 38.3초)에 묶여
**GPU util 90.5%가 유용한 일의 지표가 아니었음**이 확정됐다.

## 0.3 발견 목록

| # | 발견 | 판정 | 조치 |
|---|---|---|---|
| F1 | **CPU tier 축출에 동타입 LRU tie-break 없음** (동ι는 삽입순 FIFO) | ❌ 논문 §4.3.2 위반 | ✅ **수정 완료** (§4.2). A7c FAIL→PASS |
| F2 | REASONING 압박 시 **과잉 마킹** (초과 100tok에 2/2 마킹) | baseline 상속, 비교 중립 | 무수정 (격리 원칙, §4.1) |
| F3 | **빈 틈보다 큰 프로그램의 영구 기아** (promote가 선점 안 함) | tr/MORI 공통, 비교 중립 | 기록만 (§5.3) |
| F4 | demote를 촉발하는 건 신규 도착이 아니라 **상주 컨텍스트 성장** | 메커니즘 특성 | 기록만 (§5.3) |
| F5 | 엔진측 typed eviction 정렬 함수가 **격리 호출 불가** (sglang 클로저-로컬 + 미설치) | testability 한계 | 재구현 안 함, 범위 축소 (§2.6) |
| F6 | `router.py:798` **주석과 코드 불일치** (future_paused_tokens "accounted" 주장) | baseline 문서 결함 | 무수정 (§4.1) |
| F7 | 라우터 `_mori_evict_cpu`(idle부터)와 hicache host tier(busy부터) **축출 방향 반대** | 판정 보류 | §4.3.2 원문 대조 필요 (§7) |

## 0.4 미해결 항목 (각 한 줄)
1. **B1(b) "busy는 GPU에 남는다"** — 통제 run에서 압박 세기를 분리 조건에 맞추지 못해 미확정 (§7.1).
2. **엔진측 typed eviction 실제 축출 효과** — sglang 미설치 + 클로저-로컬이라 격리 호출 불가, 실런 필요 (§7.2).
3. **데이터플레인 ι 측정 경로 / "pause 시간 ι 제외"** — 코드 읽기로만 확인, 실행 검증 미완 (§7.3).
4. **F7 축출 방향 반대** — 논문 §4.3.2 원문 대조 후 판정해야 함 (§7.4).
5. **demote/promote 랭킹의 동률 규칙** — 논문에 명시가 없어 tie-break를 확대 적용하지 않음 (§7.5).

---

# 1. 방법론

## 1.1 A / B / C 3계층 분리

| 계층 | 성격 | 무엇을 mock했나 | 정답의 근거 |
|---|---|---|---|
| **A — 정책 충실성** | white-box, **known-answer** 합성 시나리오 | `BackendState.metrics_client` **단 하나** | 논문 정책 스펙 (§4.2/§4.3.1/§4.3.2) |
| **B — 거시 행동** | black-box, 실엔진 실측 | 없음 (실 GPU·실 SGLang) | 논문이 주장하는 메커니즘 행동 |
| **C — 유용한 일** | 기존 로그 재집계 + 최소 profile run | 없음 | decode=산출 / prefill=준비 / recompute·왕복=낭비 |

**A 계층의 핵심 설계** [측정]: mock한 엔진 경계는 **정확히 하나** — `BackendState.metrics_client`
(`healthy` / `cache_config` / `fetch_metrics()` 세 표면이 전부 여기로 위임:
`ThunderAgent/backend/state.py:73-80`, `:244-246`). 그 외에는 전부 실제 코드다:
실제 `MoriRouter`, 실제 `MoriRouter._scheduled_check()` 틱, 실제 `BackendState` 용량 회계,
실제 `CpuTier`, 실제 `IdlenessWindow`. **정책은 한 줄도 재구현하지 않았다.**

## 1.2 Falsifiability — mutation testing (M1~M8)

"현재 코드 동작을 역으로 베껴 무조건 통과하는 테스트 금지" 제약을 증명하기 위해,
**소스는 그대로 두고 런타임 몽키패치로 정책을 그럴듯한 대안으로 바꿔** 각 테스트가 실제로
깨지는지 확인했다 (스크립트는 scratchpad, 리포에 남기지 않음).

| Mutant | 정책 바꿔치기 | 깨진 테스트 |
|---|---|---|
| **M1** | `_iota` → context-length 랭킹 | A2a, A3, A4, A5, A7a, A7b |
| **M2** | `_iota` → ι 랭킹 반전 (1−ι) | A2a, A2b, A3, A4, A5, A6a, A7a, A7b, **A7d** |
| **M3** | `remaining_capacity` → 항상 초과 (용량 게이팅 제거 = 매틱 재배치) | **A1**, A2a, A2b, A3, A3b, A4, A5 |
| **M4** | `value()` → 진행 중 tool call 무시 | **A6b** |
| **M5** | `IdlenessWindow` → 옛 표본 미폐기(무한 윈도우) | **A6c** |
| **M6** | `_mark_program_for_pause` → 즉시 demote (lazy 제거) | **A2c** |
| **M7** | tie-break을 MRU로 반전 (`last_access` 부호 반전) | **A7c, A7e, A7f** |
| **M8** | tie-break 제거 (스탬프를 상수로 = 수정 전 상태로 회귀) | **A7c, A7f** |

**[측정] 17개 테스트 전부가 최소 1개 mutant에서 FAIL한다.** → 통과가 자명하지 않음이 확인됐다.
특히 A7c 수정은 **양방향으로** 검출된다(MRU로 뒤집혀도 FAIL, tie-break를 없애도 FAIL).

## 1.3 ι 주입 방법 — 구현 계산식을 베끼지 않았다는 근거

`_iota`가 `idle_window.value()`를 부르므로 ι를 직접 세팅할 수 없다. 윈도우에 **동일 표본 k쌍**
(`push_acting(x)` / `push_reasoning(1-x)`)을 push한다.

[추론] k개 동일 표본에서는 **ratio-of-sums(논문 식1)와 average-of-ratios가 둘 다 정확히 x**이므로,
이 주입은 구현의 계산식을 테스트에 역으로 베끼는 것이 **아니다**.
`acting_since=None`으로 둬서 "진행 중 tool call" 항이 주입값을 오염시키지 않게 했다.

## 1.4 실행 환경 제약 [측정]

| 항목 | 상태 | 대응 |
|---|---|---|
| `pytest` | **없음** — venv 3곳(`.venv`, `ta_goguma6/.venv`, `/usr/bin/python3`) 모두 미설치, **`pip` 자체도 없음**(`No module named pip`) | 테스트를 pytest 호환 형태(`test_*` 함수, 평범한 `assert`)로 쓰고 **자체 러너** 병행 |
| `sglang` | **없음** (A 계층 환경) | `scripts/mori_hicache_yunuikang.py:install()` import 불가 → A7 범위 축소 (§2.6) |
| python | `/home/yunuikang/yunuikang_work/.venv/bin/python`, `ThunderAgent` import OK | 리포 루트에서 실행 |

→ `pytest tests/... -v`를 **실행하지 못했다.** 대신:
```
$ python tests/test_mori_policy_yunuikang.py     # (cwd = distserving/)
17/17 passed
```

---

# 2. STEP 1 — 코드 대조 (symbol audit)

목적: STEP 2~4 테스트를 짜기 **전에** 실제 시그니처·필드·정렬키를 확정한다.
계획서(`plans/2026-07-30_PLAN_*`) API와 다르면 **실제 코드를 정답으로** 삼는다.

## 2.1 `IdlenessWindow` — `ThunderAgent/scheduler/mori_idleness.py`

| 심볼 | 위치 | 시그니처 |
|---|---|---|
| `IdlenessWindow` | `mori_idleness.py:15` | `__init__(self, k: int = 5)` |
| `push_acting` | `:33` | `(dt: float) -> None` — `dt >= 0`만 append |
| `push_reasoning` | `:37` | `(dt: float) -> None` |
| `n_samples` | `:41` | `() -> int` = `min(len(_acting), len(_reasoning))` |
| **`value`** | `:45` | `(now: Optional[float]=None, acting_since: Optional[float]=None, default: float=0.5) -> float` |

내부 상태: `_acting`, `_reasoning` = **서로 독립인 두 개의 `deque(maxlen=k)`** (`:30-31`).
즉 (acting, reasoning) 쌍이 하나의 레코드로 묶여 있지 않다.

**ι 계산식 [측정] (`:61-68`)**
```
a = sum(self._acting);  r = sum(self._reasoning)
if acting_since is not None and now is not None:  a += max(0.0, now - acting_since)
return default if (a + r) <= 0 else a / (a + r)
```

### 검증에 중요한 4가지
1. **`time.time()` 직접 호출 없음** [측정]. `now`는 전부 인자로 주입된다(호출자 `MoriRouter._iota`가
   `time.time()`을 넘김) → **A6의 now 주입 테스트 가능, mock/monkeypatch 불필요.**
2. **진행 중 tool call을 ι에 반영함** [측정] (`:63-64`): `acting_since`가 세팅돼 있으면
   `now - acting_since`를 acting 항에 더한다 → 긴 콜이 진행될수록 ι 단조 증가.
   **[논문-인용] §4.2 "responsive"에 해당.**
3. **"윈도우 평균"의 구현 = 합의 비(ratio-of-sums)이지 스텝별 비율의 평균(mean-of-ratios)이 아님** [측정].
   두 해석은 표본이 균일하면 일치하지만 **outlier가 있으면 크게 갈린다**:
   - 예: reasoning 10s ×5, acting `[0.5, 0.5, L, 0.5, 0.5]`
   - ratio-of-sums = `(2+L)/(52+L)` → `L=100s`면 **0.67 (idle로 분류)**
   - mean-of-ratios = `(4·0.0476 + L/(L+10))/5` → `L→∞`에도 **최대 0.238 (절대 0.5를 못 넘음)**
   - **판정 [논문-인용]: 논문 식(1)이 곧 합의 비이므로 "식(1)에 충실"** — average-of-ratios가
     오히려 스펙 이탈이다. crossover는 responsiveness의 정상 동작으로 특성 기록 (§3.2 A6b).
4. **스케줄러 강제 대기(pause) 제외** [측정, 부분]: acting 표본은
   `MoriRouter.update_program_before_request`(`mori_router.py:71-73`)에서 `now - state.last_response_end`로
   push된다. 이 push는 `super()` 호출 **이전**이고, PAUSED 대기(`router.py:416-419` `_wait_for_resume`)는
   `super()` **안**에서 발생 → 대기 시간이 acting 표본에 안 들어간다.
   [추론] `push_reasoning`도 `reason_started_at`(`mori_router.py:86`, 대기 종료 후 스탬프) 기준이라 대기 제외.
   이 경로는 데이터플레인이라 본 검증(틱 격리 호출)에서는 **직접 실행하지 않았다** → **미검증** (§7.3).

## 2.2 `MoriRouter` — `ThunderAgent/scheduler/mori_router.py`

### 틱 진입점 [측정] `_scheduled_check(self) -> None` (async, `:201`)
`MultiBackendRouter._scheduled_check`(`router.py:759`)를 **오버라이드**. 순서:
```
for backend: await backend.fetch_metrics()          # :202-203  ← 유일한 엔진 경계. mock 대상.
async with self.pause_resume_lock:                  # :205
    self._tick += 1 ; now = time.time()             # :206-207
    (1) remaining_capacity() < 0  -> _mori_pause_until_safe(backend, now)   # :211-213
    (2) 각 CpuTier            -> _mori_evict_cpu(tier, now)                 # :216-217
    (3)                        -> _mori_promote(now)                        # :221
```
[추론] **엔진 강결합 없음.** `fetch_metrics()` 하나만 가짜로 채우면 `_scheduled_check`를 통째로
격리 호출 가능 → "정책 재구현" 상황이 아님. 정책 헬퍼(`_mori_promote` 등)도 개별 호출 가능.

### 결정 메서드와 정렬키 [측정]

| 메서드 | 위치 | 대상 | 정렬키 | 방향 | 목적지 |
|---|---|---|---|---|---|
| `_mori_pause_until_safe(backend, now)` | `:237` | ① `ProgramStatus.ACTING` on backend (`:242`) | `self._iota(state, now)` (`:243`) | **descending** (`reverse=True`) | `_demote` → CPU, 불가시 Waiting |
| ″ | | ② `REASONING and not marked_for_pause` (`:254`) | `_iota` (`:256`) | **descending** | `_mark_program_for_pause` (지연 pause) |
| `_mori_evict_cpu(tier, now)` | `:262` | CpuTier 전체 (`:266`) | `_iota` (`:270`) | **descending** | `_evict_cpu_to_waiting` |
| `_mori_promote(now)` | `:274` | 5개 그룹 (아래) | `_iota` (`:297`) | **ascending** | GPU (best-fit backend) |

- **demote = 최고 ι** ✅ (`reverse=True`), **promote = 최저 ι** ✅ (ascending) — 스펙과 방향 일치 [측정].
- ①→② 순서: ACTING을 먼저 다 내린 뒤에야 REASONING을 마킹. 루프는 `remaining_capacity() >= 0`이 될
  때까지 1개씩 반복(`:239`, guard 100000).

### `_mori_promote` 그룹 우선순위 [측정] (`:296-299`)
```python
for group in (cpu_pending, wait_reasoning, wait_new, cpu_idle, wait_acting):
    group.sort(key=lambda x: self._iota(x[1], now))      # ascending
order = cpu_pending + wait_reasoning + wait_new + cpu_idle + wait_acting
```
- `cpu_pending` = CPU tier에 있고 `status == REASONING`(요청 대기 중), `cpu_idle` = 그 외 (`:279`).
- **ι는 그룹 *내부*에서만 정렬키다.** 그룹 우선순위가 ι보다 앞선다 → `cpu_pending`(ι=0.9)가
  `cpu_idle`(ι=0.1)보다 먼저 승격된다.
- **판정 [논문-인용]: 논문 §4.3.1이 "그룹 우선순위(툴콜 완료 CPU → 복귀 Waiting → 신규),
  각 레벨 내에서 ι 최저"를 명시하므로 코드가 §4.3.1에 충실**하다. 관측값은 A3b로 기록 (§3.2).

배치는 **best-fit** (`:304-313`): `remaining_capacity() >= total_tokens + BUFFER_PER_PROGRAM`을
만족하는 backend 중 `remaining`이 가장 큰 것. **고정 임계/고정 비율 없음** → A5 상대성 테스트가 유의미.

### 보조 메서드 [측정]

| 심볼 | 위치 | 내용 |
|---|---|---|
| `_iota(state, now)` | `:111` | `idle_window is None` → `mori.default_iota`; else `idle_window.value(now=now, acting_since=state.acting_since, default=...)` |
| `_dwell_ok(state)` | `:118` | `moved_tick is None or (self._tick - moved_tick) >= mori.min_dwell_ticks` — **스티키(anti-thrash) 게이트** |
| `_type_rank(state, now)` | `:89` | ι<0.33→**2**(busy), ι<0.66→**1**(mixed), else→**0**(idle). 높을수록 GPU 잔류 |
| `_demote(pid, state, backend)` | `:144` | `tier.can_admit` → `_demote_to_cpu`, 아니면 `_pause_program`(base) + `tier="waiting"` |
| `_demote_to_cpu` | `:128` | `backend.unregister_program` → `tier.admit` → `origin_backend=url`, `backend_url=None`, `state=PAUSED`, `tier="cpu"`, `moved_tick=_tick`, `waiting_event` 생성/clear |
| `_promote_from_cpu(pid, state, backend, now)` | `:166` | `tier.remove` → `backend.register_program` → `tier="gpu"`, `state=ACTIVE`, `waiting_event.set()` |
| `_evict_cpu_to_waiting(tier, pid, state, now)` | `:183` | `tier.remove` → `global_waiting_queue[pid] = PausedInfo(...)`, `tier="waiting"` |
| `_clear_mark_and_pause` | `:154` | base 오버라이드 — 마킹된 프로그램을 Waiting이 아니라 **CPU tier로** 내림 (데이터플레인 경로) |
| `_acting_on_backend` / `_reasoning_unmarked_on_backend` | `:223` / `:229` | 후보 수집 |

### 스티키 배치 [측정+추론]
스펙("용량 위반 또는 상위 tier 여유 발생 전까지 이동 없음")은 **두 겹으로** 구현됨:
1. **구조적**: demote는 `remaining_capacity() < 0`일 때만 호출됨(`:212`). ι가 변해도 여유가 있으면 무동작.
2. **명시적**: `_dwell_ok` / `min_dwell_ticks`(기본 **1**) — 같은 틱 내 demote↔promote 왕복 차단.
   [추론] `moved_tick`이 demote 시점에 `_tick`으로 세팅되므로 3단계 `_mori_promote`가 방금 내린
   프로그램을 같은 틱에 되올리지 못한다. **A1/A5는 shipped default(`min_dwell_ticks=1`)로 돌렸다.**

## 2.3 `CpuTier` — `ThunderAgent/scheduler/mori_tier.py`

| 심볼 | 위치 | 시그니처 / 식 |
|---|---|---|
| `__init__` | `:28` | `(url: str, capacity_tokens: int)` |
| `used_tokens` | `:34` | `Σ p.total_tokens + len(_programs) * BUFFER_PER_PROGRAM` |
| `remaining` | `:38` | `capacity_tokens - used_tokens()` |
| `can_admit` | `:41` | `remaining() >= state.total_tokens + BUFFER_PER_PROGRAM` |
| `admit` | `:45` | `(program_id, state) -> None` |
| `remove` | `:48` | `(program_id) -> Optional[Program]` |
| `contains` / `items` / `count` | `:51`/`:54`/`:57` | `items()` = `list(dict.items())` (= **삽입 순서**) |

- ✅ 용량 회계식은 스펙의 `Σtotal_tokens + n×BUFFER` 규약 그대로 [측정].
- ⚠️ **`evict_candidates`는 존재하지 않는다** [측정]. CPU tier 축출 *순서*는 `CpuTier`가 아니라
  `MoriRouter._mori_evict_cpu`(`:262`)에 있다. 계획서 API와 다름.
- ⚠️ **CpuTier에 last-access 타임스탬프 필드가 없다** [측정] → 동타입 LRU tie-break의 소스 부재.
  `_mori_evict_cpu`가 ι 하나로만 정렬하고 Python sort는 stable이므로 **동ι는 admit 삽입 순서(FIFO)로
  축출된다**. → **A7에서 정면 검증 → F1으로 확정 → §4.2에서 수정.**

*(§4.2 수정 후 위 표는 `admit(program_id, state, now=None)` / `touch()` / `last_access()` 추가로 바뀐다.)*

## 2.4 `MoriConfig` — `ThunderAgent/scheduler/mori_config.py` [측정]
```python
k: int = 5                      # :25  ✅ 논문 k=5
cpu_capacity_ratio: float = 1.0 # :26  CPU capacity = ratio × GPU pool (start()에서 적용, mori_router.py:57)
min_dwell_ticks: int = 1        # :27  스티키 쿨다운
default_iota: float = 0.5       # :28  표본 없을 때
```
(계획서에 있던 `reload_seconds`는 제거됨 — docstring `:14-16`이 "reload는 HiCache가 실제로 지불"이라 명시.)

## 2.5 `Program` — `ThunderAgent/program/state.py` [측정]

기존 필드(`:36-47`): `program_id`, `backend_url`, `origin_backend`, `status`(`ProgramStatus.REASONING|ACTING`),
`state`(`ProgramState.ACTIVE|PAUSED|TERMINATED`), `context_len`, `total_tokens`, `step_count`, `profile`,
`waiting_event`, `marked_for_pause`, `acting_since`.

MORI 추가 필드(`:50-54`):

| 필드 | 기본값 | 용도 |
|---|---|---|
| `idle_window` | `None` | `IdlenessWindow` (mori 모드에서 lazy 생성) |
| `tier` | `"gpu"` | `"gpu" \| "cpu" \| "waiting"` |
| `reason_started_at` | `None` | REASONING 시작(대기 이후) |
| `last_response_end` | `None` | 직전 응답 종료 — pure-acting gap 측정 |
| `moved_tick` | `None` | 마지막 tier 이동 틱 (스티키) |

⚠️ **`ProgramStatus`에는 `PAUSED`류가 없다** — 대신 `ProgramState`가 라이프사이클을 든다(두 enum 분리).
따라서 픽스처는 `status` / `state` / `tier` **3개를 다** 세팅해야 한다.

## 2.6 Typed eviction — `scripts/mori_hicache_yunuikang.py` ⚠️ (경로부터 다름)

- 계획서의 `ThunderAgent/scheduler/mori_hicache.py`는 **존재하지 않는다**. 실제는
  `scripts/mori_hicache_yunuikang.py` (93줄), sglang을 런타임 몽키패치하는 `install()` [측정].
- 타입 표현: 정수 rank. 라우터가 `payload["priority"] = self._type_rank(state, now)`
  (`mori_router.py:84`)로 스탬프 → SGLang `Req.priority` → `node.priority`.
- 축출 순서 결정 지점 2곳 [측정]:
  - **device(GPU) tier**: sglang 순정 `EP.PriorityStrategy.get_priority(node) = (node.priority, node.last_access_time)`.
    `"mori"` 정책명은 `_rc_init`(`:61-70`)에서 `"priority"`로 치환 → 낮은 rank 먼저 축출 + 동rank LRU.
  - **host(CPU) tier**: `_MoriHostStrategy.get_priority(node) = (-node.priority, node.last_access_time)` (`:54-55`)
    — 순서를 **반전**해 busy부터 축출, LRU tie-break 유지.

### ★ Testability 발견 (F5)
`_MoriHostStrategy`는 **`install()` 함수 본문 안에 정의된 클로저-로컬 클래스**(`:51`)이고,
`install()`은 첫 줄부터 `from sglang.srt import server_args` (`:42`)를 한다. 이 환경에 **sglang이 없다**
→ **모듈 임포트만으로는 정렬 함수에 도달할 수 없고, 격리 호출이 불가능**하다.

→ **방침: 정렬 로직을 재구현하지 않는다.** A7은 우리 코드에 실재하는 두 조각만 검증한다:
1. `MoriRouter._type_rank` — 타입 우선순위 산출 (실코드, 격리 호출 가능)
2. `MoriRouter._mori_evict_cpu` — CPU tier 축출 *순서* (실코드, 격리 호출 가능; LRU tie-break 유무 검증)

엔진측 실제 축출 효과(GPU/host radix node 축출)는 **"다음 단계(실런 필요)"**로 명시 (§7.2).

### ★ 부가 관측 (보고 대상, 테스트 대상 아님)
`_type_rank`의 컷은 **하드코딩 상수 0.33 / 0.66** (`mori_router.py:95-98`). 논문 제목의 "Relative"
(상대 랭킹, 고정 임계 없음)와 결이 다르다. 단 이건 *tier 배치*가 아니라 *tier 내부 축출 타입 라벨*이고,
tier 배치(`_mori_promote`/`_mori_pause_until_safe`)는 순수 상대 랭킹이라 A5는 영향 없음 [추론].

## 2.7 용량 회계 — 테스트 픽스처 환산 (A1~A7 공통)

[측정] `backend/state.py`:
- `BUFFER_PER_PROGRAM = 100` (`:23`)
- `remaining_capacity()` (`:185-194`) = `cache_config.total_tokens_capacity - (active_program_tokens - shared_tokens + active_program_count*100)`
- `active_program_tokens` (`:105-107`) = `reasoning_tokens + tool_coefficient * acting_tokens`

[추론] 기본 `acting_token_weight=1.0` (`router.py:67`)이고 테스트에서 `shared_tokens=0` 유지 →
**GPU 회계 = `Σtotal_tokens + n×100` = CpuTier 회계와 동일한 규약** (불변식 I2와 일치).

→ **"슬롯 n칸" 환산: `total_tokens_capacity = n × (T + 100)`, 프로그램당 `total_tokens = T`.**
   기본 픽스처: `T = 400`, GPU 2칸 → `cap_gpu = 1000`, CPU 2칸 → `cap_cpu = 1000`.

## 2.8 하네스 설계 (STEP 2 입력)

```python
r = MoriRouter(["u"], backend_type="sglang", mori=MoriConfig(...))   # httpx client만 생성, 네트워크 없음
r.backends["u"].metrics_client = FakeMetricsClient(cap_gpu)          # healthy/cache_config/fetch_metrics
r.cpu_tiers["u"].capacity_tokens = cap_cpu                           # start() 안 부르므로 직접 세팅
asyncio.run(r._scheduled_check())                                    # waiting_event(asyncio.Event) 때문에 루프 필요
```
⚠️ 구현 주의 [측정]: `asyncio.Lock`/`Event`는 **최초 사용 시점의 루프에 바인딩**되므로
(CPython `_LoopBoundMixin`), 틱마다 `asyncio.run()`을 새로 부르면 두 번째 틱에서
"bound to a different event loop"로 죽는다 → 하네스가 **루프를 하나만 만들어 재사용**한다.

## 2.9 계획서 ↔ 실제 차이 요약

| 계획서 | 실제 | 조치 |
|---|---|---|
| `IdlenessWindow` ι 게터 | `value(now, acting_since, default)` | 실제 이름 사용 |
| `CpuTier.evict_candidates` | **없음**. 축출 순서는 `MoriRouter._mori_evict_cpu` | 라우터 메서드를 테스트 |
| `ThunderAgent/scheduler/mori_hicache.py` | **없음**. `scripts/mori_hicache_yunuikang.py` (sglang 몽키패치) | A7 범위 축소 + F5 보고 |
| `MoriConfig.reload_seconds` | 제거됨 (HiCache가 실제 지불) | 무관 |
| `Program.status`에 tier 상태 | `status`(REASONING/ACTING) / `state`(ACTIVE/PAUSED) / `tier`(str) **3분리** | 픽스처에서 3개 다 세팅 |

## 2.10 테스트 사전 등록 (결과를 보고 사후에 바꾸지 않기 위해)

| ID | 겨냥 코드 | 통과 기준(논문 스펙) | 실패 시 의미 |
|---|---|---|---|
| A1 | `_scheduled_check` 전체 | 여유 있을 때 ι 진동 10틱 → tier 이동 0, 마킹 0 | 매틱 재배치 |
| A2 | `_mori_pause_until_safe:243` | 최고 ι가 내려감 (토큰 최대 프로그램은 잔류) | context-len/LRU 랭킹 |
| A3 | `_mori_promote:297` | 최저 ι가 올라감 | 랭킹 반대/무시 |
| A3b | `_mori_promote:296-299` | 그룹 우선순위 후 그룹 내 최저 ι (§4.3.1) | 관측 후 판단 보고 |
| A4 | `_demote:147` + `can_admit` | GPU 2 / CPU 2 / waiting 2, 초과 0 | admission control 누수 |
| A5 | `_mori_pause_until_safe` (cap 2 vs 3) | 경계가 용량 따라 이동 (.1.4 → .1.4.6) | 고정 임계 |
| A6 | `IdlenessWindow.value` | robust(outlier에 임계 안 넘김) + responsive(k틱 내 상승) + now 주입 단조증가 | ratio-of-sums 이슈 노출 |
| A7 | `_type_rank`, `_mori_evict_cpu` | 타입 우선순위 + **동타입 LRU** tie-break | last-access 부재 노출 |

## 2.11 STEP 1 결론
1. [측정] **정책 결정 로직은 엔진과 강결합돼 있지 않다** — `metrics_client` 하나만 가짜로 채우면
   실제 `_scheduled_check`를 통째로 격리 호출 가능. "재구현" 상황 아님.
2. [측정] demote=ι descending / promote=ι ascending / 양 tier 유한 용량 / 고정 임계 없는 best-fit —
   **큰 골격은 스펙과 일치**. 세부 3곳이 검증 가치가 있다:
   promote 그룹 우선순위(§2.2), ι의 합의-비 계산(§2.1), CPU tier LRU tie-break 부재(§2.3).
3. ⚠️ **A7은 범위 축소 불가피** (F5).
4. ⚠️ **pytest 미설치** — 자체 러너 병행.

---

# 3. STEP 2~4 — A 계층 정책 충실성 (A1~A7)

## 3.1 결과표 — **17/17 PASS**

| ID | 항목 | 논문 근거 | 결과 |
|---|---|---|---|
| A1 | 스티키 배치 (압박 없으면 ι가 변해도 재배치 X) | §4.3 | **PASS** |
| A2a | Demotion = ι 최고 | §4.3.1 | **PASS** |
| A2b | ACTING을 REASONING보다 먼저 demote | §4.3.1 | **PASS** |
| A2c | REASONING만 남으면 lazy demotion | §4.3.1 | **PASS** |
| A3 | Promotion = 그룹 내 ι 최소 | §4.3.1 | **PASS** |
| A3b | 그룹 우선순위가 ι보다 앞섬 | §4.3.1 | **PASS** |
| A4 | 양쪽 tier admission control | §4.1 | **PASS** |
| A5 | ★ Relative — 용량비 바뀌면 분할 경계 이동 | 논문 제목/§4.3 | **PASS** |
| A6a | 지표 robust (outlier 1회에 안 흔들림) | §4.2 식(1) | **PASS** |
| A6b | 지표 responsive (진행중 콜이 ι 상승, now 주입) | §4.2 | **PASS** |
| A6c | 지표 responsive (옛 표본 폐기 → phase 전환 반응) | §4.2 (k=5) | **PASS** |
| A7a | typed eviction — 타입 우선순위 | §4.3.2 | **PASS** |
| A7b | typed eviction — tier 내부 타입 순서 | §4.3.2 | **PASS** |
| A7c | typed eviction — **동타입 LRU tie-break** | §4.3.2 | ~~FAIL~~ → **PASS** (§4.2에서 수정) |
| A7d | (회귀) LRU가 타입 우선순위를 덮어쓰지 않음 | §4.3.2 | **PASS** |
| A7e | (회귀) `last_response_end=None`에서도 LRU 스탬프 유효 | — | **PASS** |
| A7f | (회귀) `remove` 시 LRU 장부 누수 없음 | — | **PASS** |

**최초 검증: 13/14 PASS (유일한 FAIL = A7c). STEP 5 수정 후 현재: 17/17 PASS.**

## 3.2 각 테스트: 세팅 → 관측된 실제 결정

### A1 — 스티키 배치 · **PASS**
세팅: GPU 4칸에 A,B 2개만(여유 2칸). 10틱 동안 A의 ι를 0.1↔0.9 진동.

> [측정] 10틱 ι 궤적 A=`[0.1, 0.9, 0.1, 0.9, 0.1, 0.9, 0.1, 0.9, 0.1, 0.9]`
> → **tier 이동 0회**, gpu=`['A','B']`, cpu=`[]`, waiting=`[]`,
> marked A=False B=False, moved_tick A=None B=None, tick=10

[추론] ι가 매 틱 극단을 오가도 아무 일도 일어나지 않는다. 스티키의 1차 근거는
`_scheduled_check`가 `remaining_capacity() < 0`일 때만 demote를 호출하는 구조(`mori_router.py:212`),
2차 근거가 `min_dwell_ticks`(기본 1) 쿨다운.

### A2a — Demotion = ι 최고 · **PASS**
세팅: GPU 2칸(1000tok). A(400tok, ι=0.1) B(**250tok**, ι=0.9) C(250tok, ι=0.2) 전부 ACTING.
used=1200 → 200 초과. **토큰 수와 ι를 반대 방향으로 배치**(반례 정책 구분용).

> [측정] 틱 전 gpu_remaining=**-200**, ι(A)=0.10 ι(B)=0.90 ι(C)=0.20 / tokens A=400 B=250 C=250
> 틱 후 **demote된 pid=`['B']` (ι=0.9)**, gpu=`['A','C']`, gpu_remaining=150

[추론] context-length 내림차순이면 A(400tok)를, LRU/FIFO면 A(첫 등록)를 내렸을 것이다.
실제로는 B가 내려갔다 → **ι 랭킹으로 결정된 것이 맞다.** 1개만 내려 용량 해소(과잉 demote 없음).

### A2b — ACTING 우선 (§4.3.1) · **PASS**
세팅: GPU 2칸. R(250tok, **ι=0.99, REASONING** = 전역 최고) A(400tok, ι=0.5, ACTING) C(250tok, ι=0.2, ACTING).

> [측정] 틱 후 gpu=`['C','R']`, cpu=`['A']`, waiting=`[]`, **R.marked_for_pause=False**, R.tier=gpu

[추론] 전역 최고 ι는 R(0.99)인데 내려간 것은 **ACTING 중 최고 ι인 A(0.5)**다. R은 마킹조차 안 됐다
→ 상태(ACTING/REASONING)가 ι보다 상위 기준으로 올바르게 작동. 전역 ι 정렬이었다면 R이 먼저 걸렸다.

### A2c — REASONING lazy demotion · **PASS** (+ 특성 관측 1건 = F2)
세팅: GPU 900tok에 REASONING만 둘. R1(400, ι=0.8) R2(400, ι=0.2). used=1000 → 100 초과.

> [측정] 틱 후: gpu=`['R1','R2']`, cpu=`[]`, waiting=`[]`,
> marked R1=**True** R2=**True**, future_paused_tokens=800, R1.state=**active**
> `_clear_mark_and_pause("R1")` 호출 후: R1.tier=**cpu**, R1.state=paused,
> cpu_tier=`['R1']`, future_paused_tokens=400

[추론] 틱 안에서는 **아무도 이동하지 않았다**(tier=gpu, state=ACTIVE, backend에 등록 유지) —
lazy demotion이 맞다. 실제 이동은 ACTING 전환 시점(`_clear_mark_and_pause`)에 일어나고,
목적지는 Waiting이 아니라 **CPU tier**(KV 보존)다 — 논문 3-tier 구조와 일치.

> ⚠️ **[측정] 특성 관측 (FAIL 아님) = F2**: 초과분이 100tok이라 1개만 마킹해도 충분한데
> **REASONING 2개가 모두 마킹**됐다(`future_paused_tokens=800`).
> [추론] 원인은 `BackendState.remaining_capacity()`(`backend/state.py:185-194`)가
> `future_paused_tokens`를 차감하지 않기 때문. `_mori_pause_until_safe`의 while 루프
> (`mori_router.py:239`)는 `remaining_capacity() < 0`을 조건으로 도는데 마킹은 이 값을 바꾸지 않으므로,
> 루프가 REASONING 후보를 **전부** 소진할 때까지 마킹한다
> (`_reasoning_unmarked_on_backend`가 비면 break, `mori_router.py:254-260`).
> → **STEP 5에서 baseline 대조 완료 (§4.1): baseline 상속으로 판정.**

### A3 — Promotion = 그룹 내 ι 최소 · **PASS**
세팅: GPU 2칸에 X(400) 상주 → 여유 1칸(remaining=500, 필요=500).
CPU tier에 **admit 순서 [C, D]**로 C(400, ι=0.8) D(400, ι=0.3), **둘 다 ACTING**(동일 그룹 `cpu_idle`).

> [측정] 틱 후 **promote된 pid=`['D']`**(ι=0.3), gpu=`['D','X']`, cpu=`['C']`,
> gpu_remaining=**0**, D.moved_tick=1

[추론] 삽입순(FIFO)이면 C가, ι 내림차순이면 C가 올라갔을 것이다. **D가 올라갔으므로 ι 오름차순이 맞다.**
promote 후 remaining=0으로 정확히 맞아떨어졌다(용량 초과 없음).

### A3b — 그룹 우선순위 > ι (§4.3.1) · **PASS**
세팅: GPU 여유 1칸. CPU tier에 P(**ι=0.9**, REASONING = 요청 대기 = `cpu_pending`),
Q(**ι=0.1**, ACTING = `cpu_idle`).

> [측정] 틱 후 **promote된 것 = P** → P.tier=gpu(ι=0.90), Q.tier=cpu(ι=0.10)

[논문-인용] ι만 보면 Q(0.1)가 압도적으로 유리한데 P가 올라갔다. **논문 §4.3.1이 명시한
"그룹 우선순위(툴콜 완료 CPU → 복귀 Waiting → 신규), 각 레벨 내에서 ι 최저"와 일치** →
**§4.3.1에 충실**로 판정. 코드의 그룹 순서(`mori_router.py:296-299`):
`cpu_pending → wait_reasoning → wait_new → cpu_idle → wait_acting`.
**ι는 각 그룹 *내부*의 정렬키다.**

### A4 — 양쪽 tier admission control · **PASS**
세팅: 프로그램 6개(각 400tok, ι=0.1~0.6, 전부 ACTING)를 전부 GPU에 얹고 1틱. GPU 2칸 / CPU 2칸.

> [측정] 틱 전 gpu_remaining=**-2000**(초과)
> 틱 후 gpu=`['P1','P2']` cpu=`['P5','P6']` waiting=`['P3','P4']`;
> gpu_remaining=**0**, cpu_remaining=**0**, 한 칸 더 필요량=500

[추론] GPU 2 + CPU 2 + waiting 2 ✅. **어느 tier도 초과하지 않고**(둘 다 remaining ≥ 0),
**두 tier 모두 꽉 찼다**(remaining=0 < 필요량 500 → 과소 수용 없음).
GPU에 남은 건 ι 최소 2개(P1=0.1, P2=0.2) ✅. CPU에는 먼저 내려간(=ι 최고) P6, P5가 들어가고
CPU가 차자 나머지 P4, P3은 Waiting으로 흘렀다 — `_demote`의 CPU→Waiting 폴백
(`mori_router.py:147-152`)이 의도대로 동작.

### A5 — ★ Relative (분할 경계가 용량에 적응) · **PASS**
세팅: **동일한** 프로그램 집합 A/B/C/D (ι=0.1/0.4/0.6/0.9, 각 400tok)를 GPU 2칸, 그 다음 3칸으로 두 번.

> [측정] GPU **2칸** → gpu=`['A','B']` cpu=`['C','D']` (remaining=0)
> [측정] GPU **3칸** → gpu=`['A','B','C']` cpu=`['D']` (remaining=0)
> [측정] 분할 경계: 2칸에서는 ι≤0.4까지, 3칸에서는 ι≤0.6까지 GPU 유지 → **경계 이동 = True**

[추론] 논문 제목의 "Idleness is **Relative**" 성질이 실제로 성립한다. 고정 ι 임계(예: 0.5)를
쓰는 구현이면 두 경우 모두 `{A,B}`가 나와 실패한다. 코드에는 tier 배치용 고정 임계가 없고
(`_mori_pause_until_safe`는 순수 상대 랭킹 + `remaining_capacity()`), 배치는 best-fit
(`mori_router.py:304-313`) → **하드웨어별 튜닝 없이 용량비에 적응**.

### A6a — 지표 robust · **PASS**
세팅(k=5): reasoning 10s×5 고정. acting = `[0.5, 0.5, 5.0, 0.5, 0.5]` (짧은 콜 0.5s 사이에 **10배 outlier** 1회).

> [측정] busy 기준선 ι=**0.0476**; outlier 1회 포함 ι=**0.1228** (Δ=+0.0752);
> 완전 idle ι=**0.7500**; `_type_rank(outlier)`=**2 (busy)**

[추론] outlier 1회가 ι를 0.0476→0.1228로 올렸지만 busy 구간(<0.33)을 벗어나지 않았고
타입도 busy(2) 유지 → **busy phase 중 긴 콜 1회에 흔들리지 않는다** ✅.
완전 idle(0.75)과의 거리도 6배 이상 유지.

### A6b — 지표 responsive (진행 중 콜, now 주입) · **PASS**
세팅: busy 윈도우(acting 0.5×5 / reasoning 10×5)에서 t0에 툴콜 진입. `value(now=t0+x, acting_since=t0)`.

> [측정] 경과(s)→ι: `0s=0.048, 1s=0.065, 5s=0.130, 20s=0.310, 60s=0.556, 120s=0.710, 300s=0.858`
> [측정] [특성] 진행중 콜이 ι≥0.5를 넘기는 경과시간 = **48s**

[추론] `IdlenessWindow`는 `time.time()`을 직접 부르지 않고 `now`를 인자로 받으므로
(`mori_idleness.py:45-64`) **monkeypatch 없이 시간 주입 테스트가 된다**. 진행 중 콜이 ι를
단조 증가시키며, 충분히 길면 idle로 넘어간다 → 방금 긴 콜에 진입한 프로그램을 스케줄러가
demote할 수 있다 ✅. **48s crossover는 논문 식(1)(합의 비)의 정상 responsiveness 특성으로 기록**
(average-of-ratios였다면 이 baseline에서 ι가 이론상 0.238을 못 넘어 영원히 demote 대상이 안 된다).

### A6c — 지표 responsive (phase 전환) · **PASS**
세팅: busy 5스텝(acting 0.5/reasoning 10) 후 idle 스텝(acting 30/reasoning 10)을 순차 push.

> [측정] 궤적 (push 0..5): `[0.048, 0.39, 0.552, 0.645, 0.707, 0.75]`
> [측정] [특성] k=5 push 후 ι=**0.7500 == 150/200** → 옛 busy 표본 완전 폐기 확인.
> ι>0.5 도달까지 필요한 push 수 = **2**

[추론] k=5 슬라이딩 윈도우가 옛 표본을 정확히 폐기한다(5회 push 후 값이 순수 idle 값과
부동소수점 오차 내 일치) → phase 전환에 **2 스텝 만에** 반응 ✅.

### A7a — 타입 우선순위 · **PASS**
> [측정] ι → rank: `0.0→2, 0.1→2, 0.32→2, 0.34→1, 0.5→1, 0.65→1, 0.67→0, 0.9→0, 1.0→0`

[추론] busy(2) > mixed(1) > idle(0), ι에 대해 비증가 ✅. 이 rank가 `payload["priority"]`로 실려
SGLang `Req.priority` → `node.priority`가 된다 (`mori_router.py:84`).

### A7b — tier 내부 타입 순서 · **PASS**
세팅: CPU tier 2칸(1000tok)에 3개(각 400tok) 강제 admit → 1개 축출 필요.
**admit 순서를 ι와 반대로**: E_busy(0.1) → E_mixed(0.5) → E_idle(0.9).

> [측정] 축출 전 admit 순서=`['E_busy','E_mixed','E_idle']`, cpu_remaining=**-500**
> 축출 후 cpu tier=`['E_busy','E_mixed']`, **축출된 것=`['E_idle']`**, cpu_remaining=0

[추론] 삽입순(FIFO)이면 E_busy가 축출됐을 것이다. E_idle이 축출됐으므로 **타입(ι) 기준이 맞다** ✅.

### A7c — 동타입 LRU tie-break · ❌ **FAIL (최초)** → ✅ **PASS (§4.2 수정 후)**
세팅: CPU tier 2칸에 **ι가 전부 동일(0.5 = 같은 타입)** 인 3개.
최근 접근 시각(`Program.last_response_end`)만 다르게: NEW=3000, MID=2000, OLD=1000.
**admit 순서를 [NEW, MID, OLD]**로 둬서 삽입순(FIFO)과 LRU가 서로 다른 답을 내게 함.

> [측정] **수정 전**: 축출 전 admit 순서=`['NEW','MID','OLD']`, ι 전부 동일=`[0.5, 0.5, 0.5]`
> → 축출 후 남은 것=`['MID','OLD']`, **축출된 것=`['NEW']`** ❌
>
> [측정] **수정 후**: 동일 세팅 → 축출 후 남은 것=`['NEW','MID']`, **축출된 것=`['OLD']`** ✅

**논문은 X를 요구, 코드는 Y를 함 (수정 전):**
- **논문(X) [논문-인용] §4.3.2 "within each type, LRU breaks ties"** → 가장 오래 접근되지 않은 `OLD`가 축출.
- **코드(Y)**: 가장 **먼저 admit된** `NEW`가 축출 (삽입순 FIFO).

**관련 코드 위치 (수정 전):**
- `ThunderAgent/scheduler/mori_router.py:270`
  ```python
  items.sort(key=lambda x: self._iota(x[1], now), reverse=True)
  ```
  **정렬키가 ι 단독이고 2차 키가 없다.** Python `sort`는 stable이므로 동ι 항목은
  `tier.items()`(= `dict` 삽입 순서, `mori_tier.py:54-55`) 그대로 유지 → FIFO.
- `ThunderAgent/scheduler/mori_tier.py:25-58`
  **`CpuTier`에 last-access 타임스탬프 필드 자체가 없다.** LRU를 넣으려면 필드부터 필요하다.

**대조 — 엔진측에는 LRU tie-break가 있다** [측정, 코드 읽기]:
`scripts/mori_hicache_yunuikang.py:55` `get_priority(node) = (-node.priority, node.last_access_time)`,
그리고 device tier의 sglang 순정 `PriorityStrategy = (node.priority, node.last_access_time)`.
→ **누락된 곳은 라우터의 CPU tier 장부 축출(CPU→Waiting) 한 군데다.**

[추론] **영향 범위**: 이 경로는 "어느 프로그램의 KV를 완전히 포기할지"(CPU→Waiting, 재개 시 full
recompute)를 정한다. ι가 정확히 같은 경우는 실제 워크로드에서 드물어 실효 빈도는 낮을 수 있으나,
**표본이 없어 `default_iota=0.5`로 동률이 되는 신규/저스텝 프로그램들 사이에서는 흔하게 발생한다**
(`mori_config.py:28`, `mori_router.py:112-113`). 이 경우 "가장 먼저 CPU로 내려온 프로그램"이
축출되는데, 이는 LRU의 정확히 **반대**에 가깝다.

## 3.3 A 계층으로 확인된 것

1. **[측정] MORI 스케줄링 정책의 핵심 5개가 코드에 충실히 구현돼 있다** — 스티키 배치(A1),
   ι 최고 demote(A2a) + ACTING 우선(A2b) + REASONING lazy(A2c), 그룹 우선순위 후 그룹 내
   ι 최소 promote(A3/A3b, §4.3.1), 양쪽 tier admission control(A4), **상대성(A5)**.
2. **[측정] ι 지표(식1, 합의 비)는 robust와 responsive를 둘 다 만족한다** — 10배 outlier 1회로는
   busy 타입 유지(A6a), 진행 중 긴 콜은 ι 단조 상승(A6b, 48s에 0.5 통과),
   k=5 윈도우가 옛 표본을 정확히 폐기해 phase 전환에 2스텝 만에 반응(A6c).
3. **[측정] 유일한 정책 이탈이었던 A7c는 §4.2에서 수정되어 닫혔다.**

---

# 4. STEP 5 — A2c baseline 대조 + A7c LRU 수정

## 4.1 과제 A — A2c 과잉 마킹: **baseline 상속으로 판정** (F2)

- 결론: **baseline 상속 성질. MORI 고유 이탈이 아니다. 격리 원칙(I4)상 무수정이 맞다.**
- 신규 파일: `tests/test_mori_a2c_baseline_yunuikang.py` (+ 하네스에 baseline 라우터 경로 추가).
  **코드 수정 없음** — 판정만. 실행: **4/4 passed**

### 대조 실험 [측정]
동일한 합성 상태를 두 경로에 각각 먹였다. mock한 것은 `metrics_client` 하나뿐이고 두 라우터 모두
실제 코드다. base 경로임은 런타임에 확인했다
(`type(router) is MultiBackendRouter`, `router._pause_until_safe.__func__ is MultiBackendRouter._pause_until_safe`).

| 경로 | 호출한 실제 메서드 | 틱 전 `remaining_capacity` | **마킹된 REASONING 수** | `future_paused_tokens` | 마킹 후 `remaining_capacity` |
|---|---|---|---|---|---|
| **MORI** | `MoriRouter._mori_pause_until_safe` | −100 | **2 / 2** | 800 | −100 (변화 없음) |
| **tr (base)** | `MultiBackendRouter._pause_until_safe` | −100 | **2 / 2** | 800 | −100 (변화 없음) |

> [측정] 초과분은 100tok이라 1개 마킹이면 충분하다. **양쪽 모두 2개를 마킹했다.**

**용량 회계 동일성 [측정]**: 동일 상태에서 `remaining_capacity`: MORI=**−100**, tr=**−100** → 일치.
[추론] 불변식 I2("MORI와 TA+O를 동일한 회계로 비교")가 실제로 성립하며, 과잉 마킹은 **양쪽에 똑같이**
나타나므로 두 스케줄러 비교에서는 **중립**이다.

### 근본 원인 — 직접 확인 [측정]
> `future_paused_tokens`를 0 → 400으로 바꿨을 때
> `remaining_capacity()`: −100 → **−100 (변화 없음)**
> `capacity_overflow(include_future_release=True)`: 100 → **0 (반응함)**

**`BackendState.remaining_capacity()` (`backend/state.py:185-194`, frozen baseline)**
```python
buffer = self.active_program_count * BUFFER_PER_PROGRAM
used = self.active_program_tokens - self.shared_tokens + buffer
return self.cache_config.total_tokens_capacity - used     # future_paused_tokens 미참조
```

두 경로의 while 루프가 **모두** 이 값을 조건으로 쓴다. 마킹(`_mark_program_for_pause`)은
`future_paused_tokens`만 늘리고 `active_program_tokens`/`active_program_count`는 건드리지 않으므로,
루프 조건이 전혀 움직이지 않아 **후보가 소진될 때까지 계속 마킹**한다.

| | MORI | tr (base) |
|---|---|---|
| 루프 조건 | `mori_router.py:239` `while backend.remaining_capacity() < 0` | `router.py:780` `while backend.remaining_capacity() < 0` |
| REASONING 후보 | `mori_router.py:254` (`marked_for_pause` 제외) | `router.py:792` → `_get_reasoning_programs_sorted` (`router.py:627`에서 `marked_for_pause` 제외) |
| 마킹 | `mori_router.py:258` `_mark_program_for_pause` | `router.py:795` **동일 메서드** |
| 종료 | 후보 리스트가 비면 `break` (`:260`) | 후보 리스트가 비면 `break` (`:802`) |

**구조가 동일하다.** MORI가 base에서 바꾼 것은 *정렬 기준*뿐이다
(base: 토큰 수 오름차순 `router.py:792` / MORI: ι 내림차순 `mori_router.py:256`).
**루프 종료 조건과 과잉 마킹 성질은 base 그대로 상속**했다.

> ⚠️ **[측정] F6**: `router.py:798`의 주석은
> `# After marking, we've accounted for future_paused_tokens, continue checking`
> 라고 적혀 있으나, 실제 루프 조건인 `remaining_capacity()`는 그 값을 참조하지 않는다.
> **주석과 코드가 불일치**한다 (baseline 코드이므로 이번 범위에서는 수정하지 않음).

[추론] baseline에는 future-aware 회계 함수가 **이미 있다** —
`capacity_overflow(include_future_release=True)` (`backend/state.py:170-183`)는 위 실험에서
100 → 0으로 정상 반응했다. 즉 **함수가 없어서가 아니라, pause 루프가 그 함수를 쓰지 않아서** 생기는 문제다.

### 남는 영향 [추론]
과잉 마킹 자체는 공통이지만 **마킹 이후 목적지는 다르다**:
- tr: `_clear_mark_and_pause` → `_pause_program` → **Waiting (KV 폐기)**
- MORI: 오버라이드된 `_clear_mark_and_pause` (`mori_router.py:154-164`) → `_demote` → **CPU tier (KV 보존)**

→ 과잉 마킹의 *비용*은 MORI 쪽이 더 낮다(재개 시 reload vs full recompute).
다만 **필요 이상으로 GPU를 비우는 것**은 사실이다.

### 하지 않은 것
`remaining_capacity()`를 future-aware로 바꾸는 것은 **baseline 수정**이라 제약 위반이다.
MORI 쪽에서만 우회하는 것도 **불변식 I2(동일 회계로 비교)를 깨뜨리므로** 하지 않았다.
두 경로가 똑같이 동작하는 현재 상태가 비교 실험 관점에서 올바르다.

## 4.2 과제 B — A7c LRU tie-break 수정 (F1 닫음)

정답의 근거는 **[논문-인용] §4.3.2 "within each type, LRU breaks ties"**이고,
**테스트 A7c가 oracle**이다 (테스트를 코드에 맞춘 것이 아니라, 이미 FAIL하던 테스트를 통과시키도록
코드를 고쳤다).

### 변경 1 — `ThunderAgent/scheduler/mori_tier.py`: `CpuTier`에 last-access 장부 추가

| 위치 | 내용 |
|---|---|
| `mori_tier.py:39` | `self._last_access: Dict[str, float] = {}` — 상주 프로그램별 최근 접근 시각 |
| `mori_tier.py:53-55` | `admit(program_id, state, now=None)` — `now` 인자 추가(기본 None, **기존 호출부와 하위 호환**), admit 시 `touch()` 호출 |
| `mori_tier.py:57-59` | `remove()` — 장부에서도 pop (누수 방지) |
| `mori_tier.py:71-91` | `touch(program_id, now=None, state=None)` — 스탬프 우선순위: ① 명시적 `now` → ② `state.last_response_end`(이 프로그램이 마지막으로 GPU에서 KV를 쓴 시각 = 여기서의 "last used") → ③ wall-clock(응답 이력이 없는 신규 프로그램) |
| `mori_tier.py:93-95` | `last_access(program_id)` — 미등록 id는 `-inf`(가장 오래된 것으로 정렬) |

### 변경 2 — `ThunderAgent/scheduler/mori_router.py:270`: 정렬키에 2차 키 추가
```diff
-            # Evict highest-ι first (least likely to resume soon on GPU).
-            items.sort(key=lambda x: self._iota(x[1], now), reverse=True)
+            # Typed eviction (paper §4.3.2): highest-ι first ... **within the same
+            # type, LRU breaks ties** — the least-recently-used program is evicted first.
+            items.sort(key=lambda x: (-self._iota(x[1], now), tier.last_access(x[0])))
```
[추론] **`reverse=True`를 없애고 ι를 부호 반전**했다. `reverse=True`를 유지한 채 튜플
`(ι, last_access)`를 쓰면 2차 키까지 내림차순이 되어 tie-break가 **LRU가 아니라 MRU**로 뒤집힌다.
부호를 1차 키에만 넣으면 두 항 모두 의도한 방향(ι 내림차순 / last_access 오름차순)이 된다.

### 검증 [측정]
```
$ python tests/test_mori_policy_yunuikang.py
17/17 passed          # A7c FAIL -> PASS, A1~A7b 회귀 없음
$ python tests/test_mori_idleness_yunuikang.py     -> all idleness/tier/config tests passed
$ python tests/test_mori_invariants_yunuikang.py   -> all invariant/policy tests passed
$ python tests/test_mori_a2c_baseline_yunuikang.py -> 4/4 passed
```
- **A7c** [측정]: 동일 세팅에서 축출 대상이 `NEW`(삽입순) → **`OLD`(LRU)**로 바뀜.
- **A7d (신규 회귀)** [측정]: `idle(ι .9/last 3000)` `mid(.5/2000)` `busy(.1/1000)` →
  축출된 것 = **`E_idle`**. LRU상으론 `E_busy`가 가장 오래됐지만 **타입이 1차 키**로 유지됨 ✅
- **A7e (신규 회귀)** [측정]: `last_response_end=None` + `idle_window=None`(ι 전부 `default_iota=0.5`
  동률)인 3개 → 스탬프가 admit 순으로 증가하고, 가장 오래된 `N1`이 축출 ✅
- **A7f (신규 회귀)** [측정]: `remove` 후 `last_access('Z')` = `-inf`, 내부 장부 크기 = 0 → 누수 없음.
  재-admit 시 새 `last_response_end`(5000)가 반영됨 ✅

### 수정의 falsifiability [측정]
M7(MRU로 반전) → **A7c, A7e, A7f** FAIL / M8(tie-break 제거 = 수정 전 회귀) → **A7c, A7f** FAIL /
M2(ι 랭킹 반전) → **A7d** 포함 FAIL. → 수정이 **양방향으로** 검출된다.

### 변경 범위 [측정]
```
$ git diff --stat
 ThunderAgent/scheduler/mori_router.py | 10 +++++++--
 ThunderAgent/scheduler/mori_tier.py   | 41 +++++++++++++++++++++++++++++++++--
 2 files changed, 47 insertions(+), 4 deletions(-)
$ git diff --stat -- ThunderAgent/scheduler/router.py ThunderAgent/backend/state.py \
                     ThunderAgent/profile/state.py ThunderAgent/program/state.py ThunderAgent/app.py
 (없음)
```
**baseline 0-line diff 유지. 커밋하지 않음.**

### 이번 수정에서 하지 않은 것 (범위 명시)
- `_mori_pause_until_safe`(demote 선택)와 `_mori_promote`(승격 선택)의 정렬에는 tie-break을
  넣지 않았다. **§4.3.2의 LRU tie-break는 축출(eviction) 규정**이고, §4.3.1의 demote/promote 랭킹에는
  동률 규칙이 명시돼 있지 않다. 근거 없이 확대 적용하지 않았다 → §7.5.
- `touch()`는 공개 API로 추가했지만 `admit` 외의 새 호출부는 만들지 않았다.
  [추론] 잠재적 추가 지점: `_mori_promote`에서 `cpu_pending`으로 분류됐으나 자리가 없어 승격되지
  못한 경우 — "최근 사용됨"으로 볼 여지가 있다. 행동 변화를 동반하므로 이번 범위에서 미적용.

---

# 5. STEP 6 — B 계층 실동작 (B0~B3)

- 목적: **논문이 주장하는 메커니즘 행동이 실런에서 실제로 나타나는지** 확인.
- 제약 준수: baseline / 원본 trace / 기존 스크립트 **무수정**. 기존 하네스
  (`_serve_sglang_8b_tp2_mori_yunuikang.sh`, `run_msw_*`) 재사용, 신규는 **계측·분석 스크립트만**.

## 5.0 계측 방법의 중요한 제약 2가지 [측정]

1. **nvidia-smi memory로는 KV 해제를 볼 수 없다.** SGLang이 KV 풀을 정적 선점하므로
   `gpu0_mem`이 모든 셀에서 **27.7GB 상수**다(§5.4 표). → GPU KV 점유는 **`sglang:num_used_tokens`**로 관측.
2. **`/health`는 `cpu_tier`를 노출하지 않는다.** `MoriRouter.get_program_stats()`가 값을 만들지만
   `app.py:159-170`이 특정 키만 골라 반환한다. `app.py`를 고치지 않기 위해 **파생**했다:
   `cpu_tier = programs_count − Σ per_backend[url].total − paused_count`
   (CPU tier 프로그램은 `backend_url=None`이라 `per_backend`에서 빠지고,
   `paused_count = len(global_waiting_queue)`에는 CPU tier가 안 들어간다 — `router.py:958-986`).
   **run2에서 이 파생값이 프록시 로그의 demote/promote 이벤트와 일치함을 확인했다.**

## 5.1 B0 — 기존 로그 채굴 (새 GPU run 없이 답한 것)

`scratch/mori/msw/`에 M-SWP 30셀이 이미 있었다: `results_msw{,_lowc}.jsonl`,
`gpu_<tag>.jsonl`(util 시계열 1Hz), `proxy_<tag>.log`(MORI tier 이동 이벤트).
**B2·B3는 전부 여기서 답했고, 새 run은 B1에만 썼다.**

> ⚠️ [측정] `hicache_extra`의 sglang 카운터는 **백엔드 부팅 이후 누적값**이다
> (`mori_replay_driver_yunuikang.py:367`이 델타를 안 남긴다). 분석 스크립트가 같은 부팅을 공유하는
> 셀들 사이에서 차분하고, 카운터가 감소하면 재부팅 경계로 처리한다. 아래 수치는 **셀별 델타**다.

### B0-1 MORI tier 이동 실측 [측정]

| 셀 | oversub | demote GPU→CPU | promote CPU→GPU | **evict CPU→Waiting** | demote/완료턴 |
|---|---|---|---|---|---|
| MORI_r2_C2 | 0.2× | **0** | 0 | 0 | 0.000 |
| MORI_r2_C4 | 0.5× | **0** | 0 | 0 | 0.000 |
| MORI_r2_C8 | 1.0× | 22 | 22 | **0** | 0.017 |
| MORI_r2_C10 | 1.2× | 131 | 128 | **0** | 0.089 |
| MORI_r2_C20 | 2.5× | 375 | 358 | 2 | 0.266 |
| MORI_r2_C50 | 6.2× | 598 | 576 | 4 | 0.717 |
| MORI_r2_C80 | 9.9× | 690 | 648 | 9 | 1.327 |

(oversub = C / fit median 8.1)

**[측정] 3가지가 바로 읽힌다:**
1. **C2/C4(무압박)에서 tier 이동이 정확히 0.** ι는 계속 변하는데도 아무도 안 움직였다
   → **A1 스티키 정책이 실런에서 그대로 성립**한다.
2. **demote ≈ promote** (22/22, 131/128, 690/648) → 일방향 방출이 아니라 **왕복 오프로딩**이다.
3. **CPU→Waiting 축출이 극히 드물다** (C≤10에서 0, C80에서도 690건 중 9건 = 1.3%)
   → 내려간 KV의 **98.7% 이상이 CPU tier에 보존**된다. §5.5의 근거.

## 5.2 B1 — 메커니즘 핵심: idle은 GPU를 떠나고 busy는 남는가 (통제 run)

### 설계
프로그램 N개가 비슷한 컨텍스트를 유지해 GPU tier 압박을 만들고, 그중 **LONG 1개**만 지정 시점에
**90초 tool call**에 들어간다(나머지 SHORT는 1초 콜 유지). `MAXTOK=32768`로 KV 풀을 작게 핀해
**소수 프로그램으로** 압박을 만든다 (M-SWP의 262144 대신).

### 4회 run 요약 [측정]

| run | 설정 | demote/promote/evict | 결과 |
|---|---|---|---|
| 1 | SYSTOK 6000, 6 프로그램, 컨텍스트 성장 허용 | 4 / 2 / 0 | LONG demote 확인. 2개가 CPU tier에 **27분간 갇힘**(교착) |
| **2** | SYSTOK 9000, 6 프로그램, 성장 허용 | **7 / 5 / 0** | **주 결과** — LONG demote→promote 왕복 관측 |
| 3 | +컨텍스트 트리밍, LONG 14k/SHORT 9k, 6개 | 0 / 0 / 0 | 압박 소멸 → 이동 없음 |
| 4 | 트리밍, LONG 20k/SHORT 6k, 9개 | 0 / 0 / 0 | LONG이 **한 번도 입장 못 함**(400초) |

run 1의 교착으로 메모리 상 샘플을 통째로 잃어 **샘플 스트리밍 + 하드 데드라인**을 프로브에 추가했다.

### (a) idle 프로그램이 GPU를 떠나 HBM(KV)이 비는가 — ✅ **PASS** [측정, run 2]

프록시 로그의 tier 이동과 `sglang:num_used_tokens`가 **같은 시각에 일치**한다:

| t (s) | cpu_tier(파생) | gpu_resident | **num_used_tokens** | hicache_host_used |
|---|---|---|---|---|
| 73.1 | 0 | 5 | 32,139 | 32,150 |
| **81.0** | **0 → 1** | 5 → **4** | **32,589 → 26,331** | 32,804 |
| 91.1 | 1 | 4 | 20,585 | 33,863 |
| **156.4** | **1 → 2** | 4 → **3** | 32,637 | 39,419 |

- **[측정] cpu_tier가 0→1이 되는 바로 그 시각에 GPU KV가 32,589 → 26,331 토큰으로 6,258 감소**했다.
  프록시 로그의 해당 demote 이벤트는 `MORI demote GPU->CPU b1-LONG (tokens=6583)` —
  **감소폭 6,258 ≈ 그 프로그램의 KV 6,583**. 우연이 아니다.
- [측정] 같은 구간에 `hicache_host_used`가 32,150 → 33,863으로 증가 → KV가 **호스트로 옮겨간 것**이지
  버려진 게 아니다.
- **[논문-인용] §3.4의 "idle을 CPU로 offload해 HBM 확보"가 실제로 일어난다.**

### (b) busy(짧은 콜) 프로그램은 GPU 잔류인가 — ⚠️ **미확정**

- [측정] run 2에서 **LONG은 확실히 demote됐다** (`MORI demote GPU->CPU b1-LONG` →
  이후 `MORI promote CPU->GPU b1-LONG`).
- 그러나 압박이 과해서 **SHORT들도 함께 내려갔다** (`b1-SHORT1~4`도 demote 로그에 등장,
  gpu_resident 5→4→3). 따라서 "busy는 남는다"를 **분리해서 보이지 못했다**.
- run 3/4에서 압박을 정밀 조정하려 했으나 **압박 자체가 사라져** 검증 대상이 없어졌다.
- **[측정] 정직한 결론: (b)는 이번 run들로 확인되지 않았다.** 합성 테스트(A2a/A5)에서 ι 랭킹이
  정확히 동작함은 확인됐으므로, 남은 것은 "실런에서 ι 분리가 충분히 생기는가"이며 이건 미확인이다 → §7.1.

## 5.3 B1 부수 발견 2건

### F4 — demote를 촉발하는 것은 신규 도착이 아니라 상주 컨텍스트 성장 [측정→추론]
run 3에서 대화를 슬라이딩 윈도우로 잘라 **컨텍스트 길이를 일정하게** 만들자 tier 이동이
**정확히 0**이 됐다 (SHORT 4,661 tok / LONG 7,157 tok 고정, 합계 26,301 < 32,768).

[추론]
- 신규 도착은 admission control이 막는다(`_select_backend_for_new_program`이 안 맞으면 waiting으로).
  즉 새 프로그램 때문에 GPU tier가 초과되는 일은 없다.
- GPU tier가 `remaining_capacity() < 0`이 되는 유일한 경로는 **이미 올라간 프로그램들의
  `total_tokens`가 턴마다 커지는 것**이다.
- M-SWP에서 C≥8부터 demote가 나타난 것(C8=22, C10=131)과 정합적 — 세션이 길어질수록 컨텍스트가 자란다.

### F3 — 큰 프로그램의 영구 기아 (starvation) [측정, run 1·2·4 공통]
- **[측정] run 4**: LONG(추정 ~10.4k tok)이 **400초 내내 한 번도 GPU에 입장하지 못했다.**
  turns 기록에 `b1-LONG` 항목이 아예 없다. 그동안 SHORT 8개(각 ~3.1k)는 129~134턴씩 정상 수행.
  `gpu_resident=8, waiting=1`이 전 구간 고정.
- **[측정] run 1**: 2개 프로그램이 CPU tier에 갇혀 27분간 진행 없음.
  **run 2**: t≈217초 이후 `gpu_resident=3, cpu_tier=2, waiting=1`로 완전 정지,
  `num_used_tokens=0`(엔진 유휴).

**원인** [추론]: promote는 **기회적(opportunistic)**이다 — `_mori_promote`(`mori_router.py:304-313`)는
`remaining_capacity() >= total_tokens + BUFFER`인 backend를 찾을 뿐, **자리를 만들기 위해
상주 프로그램을 내리지 않는다.**

**이것은 MORI 고유가 아니다** [측정]: baseline `_greedy_resume`(`router.py:885-905`)도 동일하다 —
`if required_tokens > max_backend_capacity: continue`로 **건너뛸 뿐 선점하지 않는다**.
→ **tr/MORI 공통 성질이며 비교에는 중립이다.**

**M-SWP 실런에서 이 교착이 안 보인 이유** [추론]: 실제 trace에서는 프로그램이 **완료되고 release되어
용량이 회전**한다. 프로브는 프로그램이 끝나지 않는 무한 루프라 회전이 없어 정지가 드러났다.
→ **스트레스 조건에서만 나타나는 edge case이며, 평가 run의 결함이라는 증거는 아니다.**

## 5.4 B2 — GPU util vs concurrency [측정, 기존 로그 채굴]

steady 구간(후반 80%) `gpu0_util` 평균 + 같은 셀의 output throughput.
(TA = offloading 없음, TA+O = offloading + LRU 축출, MORI = offloading + typed 축출; r=2)

| C | oversub | TA util% / thr | TA+O util% / thr | **MORI util% / thr** | 레짐 |
|---|---|---|---|---|---|
| 2 | 0.2× | 7.3 / 3.0 | 7.2 / 3.0 | 6.7 / 3.0 | under-load |
| 4 | 0.5× | 25.3 / 9.1 | 24.5 / 9.0 | 24.2 / 9.1 | under-load |
| **8** | **1.0×** | 50.8 / 20.3 | 46.1 / 20.6 | **53.2 / 21.1** | **건강** |
| **10** | **1.2×** | 60.8 / 22.3 | 56.1 / 23.3 | **58.7 / 23.7** | **건강** |
| 20 | 2.5× | 71.0 / 21.8 | 70.0 / 19.9 | **73.0 / 22.2** | 중간 |
| 50 | 6.2× | 81.4 / 12.8 | 66.6 / 16.1 | 82.5 / **11.8** | 극단 |
| 80 | 9.9× | 82.9 / 11.4 | 73.3 / **14.3** | **90.5** / **6.5** | 극단 |

### 판정
- **건강 구간(C=8·10) — ✅ PASS** [측정]: MORI가 GPU util(53.2 / 58.7)과 throughput(21.1 / 23.7)
  **둘 다 세 시스템 중 최고이거나 동급 최고**. C=8에서 MORI는 TA+O보다 util **+7.1%p**, throughput **+2.4%**.
- **극단 구간(C=50·80) — ⚠️ 레짐 효과, 정책 오구현 아님** [추론]:
  C80에서 MORI는 **util은 최고(90.5%)인데 throughput은 최저(6.5)**.
  **높은 util ≠ 높은 처리량.** 같은 구간 prefix hit이 0.600까지 떨어지고 demote/완료턴이 1.327로
  폭증한 것과 정합적 → 오프로딩 왕복 자체가 GPU를 점유하는 thrash 레짐. **§6에서 정량 분해.**
- **대조군 SMG**: C20/50/80 모두 util **100.0%**인데 throughput은 3.8 / 2.7 / 3.0.
  [추론] util 단독은 시스템 품질의 지표가 될 수 없음을 보여주는 반례 → 표를 **util+throughput 병기**로 제시.

> ⚠️ **[논문-인용] §2의 "높은 C에서도 MORI는 util 유지, phase-oblivious는 붕괴" 주장과 대조**:
> **util 유지 부분은 재현된다**(MORI가 C20~C80 전 구간에서 TA+O보다 util이 높다).
> 그러나 **극단 oversub에서 throughput은 역전**된다. 이 두 사실을 모두 기록한다.

## 5.5 B3 — 재개는 reload지 recompute가 아님 [측정, 기존 로그 채굴]

| 셀 | oversub | prefix hit | **load_back (reload)** | evicted | CPU→Waiting 축출 |
|---|---|---|---|---|---|
| TA_r0_C8 (offload 없음) | 1.0× | 0.920 | **0.00M** | 8.30M | n/a |
| TAO_r2_C8 (LRU) | 1.0× | 0.949 | 2.92M | 8.66M | n/a |
| **MORI_r2_C8** | 1.0× | 0.944 | **7.88M** | 13.99M | **0** |
| TA_r0_C10 | 1.2× | 0.916 | **0.00M** | 10.74M | n/a |
| TAO_r2_C10 | 1.2× | 0.943 | 4.11M | 11.87M | n/a |
| **MORI_r2_C10** | 1.2× | 0.945 | **12.83M** | 20.75M | **0** |
| MORI_r2_C20 | 2.5× | 0.882 | 10.25M | 30.94M | 2 |
| MORI_r2_C50 | 6.2× | 0.789 | 11.31M | 35.49M | 4 |
| MORI_r2_C80 | 9.9× | 0.600 | 7.25M | 37.84M | 9 |

### 판정 — ✅ **PASS (건강 구간)**
- **[측정] MORI는 CPU tier를 실제로 쓴다** — 건강 구간에서 reload가 TAO의 **2.7~3.1배**
  (C8: 7.88M vs 2.92M, C10: 12.83M vs 4.11M). offloading 없는 TA는 정확히 0.00M.
- **[측정] 내려간 KV가 폐기되지 않는다** — CPU→Waiting 축출이 C≤10에서 **0건**, C80에서도 1.3%.
  → 재개는 거의 전부 **host pool reload 경로**. **[논문-인용] §4.1의 offloading 존재 이유가 성립.**
- **[측정] B1 run 2에서 개별 이벤트로도 확인**: `load_back_tokens_total`이 t=151.95s에
  **660 → 13,900 (+13,240 tok)** 점프. 당시 promote된 프로그램 2개의 KV 합(6,583 × 2 = 13,166)과 일치
  → **promote가 곧 reload다.**
- **[측정] prefix hit이 건강 구간에서 0.94~0.95로 유지**되고 극단 구간에서만 0.600으로 붕괴.

## 5.6 B 계층 종합

| 항목 | 레짐 | 판정 | 핵심 관측 |
|---|---|---|---|
| B0 스티키 | 무압박(C2/C4) | ✅ PASS | tier 이동 **정확히 0** |
| B0 왕복성 | 전 구간 | ✅ PASS | demote≈promote, CPU→Waiting 축출 ≤1.3% |
| B1 (a) idle이 GPU를 떠남 | 압박 | ✅ PASS | cpu_tier 0→1 시각에 GPU KV **−6,258 tok** (= 해당 프로그램 6,583) |
| B1 (b) busy는 잔류 | 압박 | ⚠️ **미확정** | LONG은 확실히 내려갔으나 SHORT도 함께 내려가 분리 실패 |
| B1 (c) 재개=reload | 압박 | ✅ PASS | promote 시각에 load_back **+13,240 tok** |
| B2 GPU util | 건강(1.0~1.2×) | ✅ PASS | MORI util 53.2/58.7 + thr 21.1/23.7 = 동급 최고 |
| B2 GPU util | 극단(6~10×) | ⚠️ 레짐 효과 | util 최고(90.5%)인데 thr 최저(6.5) — thrash |
| B3 reload vs recompute | 건강 | ✅ PASS | reload가 TAO의 2.7~3.1배, TA는 0 |

---

# 6. STEP 7 — "유용한 일" 정량화 (①~⑤)

- 목적: **GPU가 바쁜 것(util)과 유용한 일을 하는 것을 구분**한다. §5.4의
  "MORI C80: util 최고(90.5%)인데 throughput 최저(6.5)"를 지표로 분해.
- 개념 근거: decode(출력) = 진짜 산출물 / prefill = 준비 비용 / recompute·왕복 = 낭비.
  goodput = SLO를 만족한 산출만.

## 6.0 데이터 한계 (결론 해석에 필수) [측정]

1. **per-turn 레코드가 저장되지 않았다.** 드라이버가 turn별 `ttft_s`/`completion_tokens`를 메모리에
   모아 `mean/p50/p95/n`만 남기고 버린다
   (`mori_replay_driver_yunuikang.py:320-345` 집계 → `:433-437` 요약만 기록).
   → **정확한 goodput은 기존 로그로 계산 불가.** ③은 **순서통계 구간**으로 냈고,
   ⑤(d)의 `--profile` per-step CSV가 프로파일 셀에 한해 실측으로 대체한다.
2. **프록시 로그에 타임스탬프가 없다** → ping-pong의 *시간 간격*은 못 재고 *횟수·순서*만 잰다 (④).
3. **util은 nvidia-smi 1Hz 샘플**이라 거친 지표다. ①의 분모로 쓰되 절대값이 아니라
   **같은 C에서의 시스템 간 비교**로만 읽어야 한다.
4. 셀 선택: hicache ratio **r2 고정**(headline 설정, low-C 스윕과 동일). throughput 최대로 고르면
   C별로 r1/r2가 섞여 §5.4 보고와 어긋나므로 고정했다. ④에는 r1도 함께 싣는다.

## 6.1 ① 생산성 비율 = throughput ÷ mean_gpu_util [측정]

| C | oversub | SMG thr/util/**비율** | TA thr/util/**비율** | TA+O thr/util/**비율** | **MORI** thr/util/**비율** |
|---|---|---|---|---|---|
| 2 | 0.2× | — | 3.0 / 7.3 / **40.7** | 3.0 / 7.2 / **41.9** | 3.0 / 6.7 / **43.9** |
| 4 | 0.5× | — | 9.1 / 25.3 / **36.2** | 9.0 / 24.5 / **36.5** | 9.1 / 24.2 / **37.5** |
| **8** | **1.0×** | — | 20.3 / 50.8 / **39.9** | 20.6 / 46.1 / **44.6** | 21.1 / 53.2 / **39.7** |
| **10** | **1.2×** | — | 22.3 / 60.8 / **36.6** | 23.3 / 56.1 / **41.5** | 23.7 / 58.7 / **40.3** |
| 20 | 2.5× | 3.8 / 100.0 / **3.8** | 21.8 / 71.0 / **30.8** | 19.9 / 70.0 / **28.4** | 22.2 / 73.0 / **30.4** |
| 50 | 6.2× | 2.7 / 100.0 / **2.7** | 12.8 / 81.4 / **15.8** | 16.1 / 66.6 / **24.2** | 11.8 / 82.5 / **14.3** |
| **80** | **9.9×** | 3.0 / 100.0 / **3.0** | 11.4 / 82.9 / **13.7** | 14.3 / 73.3 / **19.5** | 6.5 / 90.5 / **7.2** |

**[측정] 핵심:**
- **MORI C80의 생산성 비율은 7.2 — 전 시스템 중 최저**(SMG 제외). 건강 구간(C8 39.7 / C10 40.3)
  대비 **5.6배 하락**. 같은 C80에서 TA+O는 19.5로 MORI의 **2.7배**.
- **SMG는 util 100%인데 비율 2.7~3.8** — util 단독이 지표가 될 수 없음을 보여주는 극단 반례.
- [측정] 건강 구간에서 MORI 비율(39.7 / 40.3)은 TA(39.9 / 36.6)와 동급이고
  **TA+O(44.6 / 41.5)보다는 약간 낮다**. [추론] MORI는 C8에서 util이 더 높아(53.2 vs 46.1)
  절대 산출은 더 크지만, *바쁜 1초당* 효율은 TA+O가 조금 낫다. **두 사실 모두 기록한다.**

## 6.2 ② prefill vs decode + prefill 3분해 [측정]

- `prefill` = `sglang:prompt_tokens_total` 델타, `decode` = `generation_tokens_total` 델타
- **`recompute` = prefill − cached** (캐시에 없어 다시 계산 = **낭비**)
- **`reload`** = `load_back_tokens_total` 델타 (cached 중 호스트에서 끌어온 몫 = **쌈**)
- **`gpu_hit`** = cached − reload (이미 GPU radix에 있어 **공짜**)
- **낭비율 = recompute ÷ (decode + prefill)**

| 셀 | C | decode | prefill | dec:pre | gpu_hit | reload | **RECOMPUTE** | hit | **낭비율** |
|---|---|---|---|---|---|---|---|---|---|
| SMG_r0_C80 | 80 | 0.05M | 19.72M | 1:399 | 0.32M | 0.00M | **19.40M** | 0.016 | **0.981** |
| TA_r0_C8 | 8 | 0.08M | 51.22M | 1:655 | 47.14M | 0.00M | 4.07M | 0.920 | 0.079 |
| TAO_r2_C8 | 8 | 0.08M | 54.23M | 1:666 | 48.52M | 2.92M | 2.79M | 0.949 | 0.051 |
| **MORI_r2_C8** | **8** | 0.10M | 52.90M | 1:553 | 42.06M | **7.88M** | 2.96M | 0.944 | **0.056** |
| **MORI_r2_C10** | **10** | 0.10M | 69.54M | 1:672 | 52.85M | **12.83M** | 3.85M | 0.945 | **0.055** |
| MORI_r2_C20 | 20 | 0.11M | 68.94M | 1:641 | 50.53M | 10.25M | 8.16M | 0.882 | 0.118 |
| MORI_r2_C50 | 50 | 0.10M | 56.93M | 1:573 | 33.63M | 11.31M | 12.00M | 0.789 | 0.210 |
| **MORI_r2_C80** | **80** | 0.08M | 38.01M | 1:482 | 15.55M | 7.25M | **15.21M** | 0.600 | **0.399** |
| TA_r0_C80 | 80 | 0.11M | 53.98M | 1:498 | 42.15M | 0.00M | 11.83M | 0.781 | 0.219 |
| TAO_r2_C80 | 80 | 0.12M | 63.42M | 1:534 | 42.64M | 10.23M | 10.55M | 0.834 | 0.166 |

**[측정] 핵심:**
- **이 워크로드는 압도적으로 prefill 지배적이다** — decode:prefill이 모든 셀에서 **1:400~1:730**.
  [추론] 에이전트 워크로드(긴 컨텍스트, 짧은 출력)의 본질이며, 그래서 **prefix cache 재사용이
  성능을 좌우**한다. 캐시가 무너지면 곧바로 recompute 낭비가 된다.
- **MORI C80: 낭비율 0.399** — 전체 토큰 작업의 **40%가 recompute**. 건강 구간(0.056 / 0.055) 대비 **7배**.
  같은 C80에서 TA+O 0.166, TA 0.219보다 훨씬 나쁘다.
- **MORI C80의 prefix hit이 0.600으로 붕괴**(TA+O 0.834). recompute 절대량 15.21M > TA+O 10.55M인데
  **prefill 총량은 오히려 적다**(38.01M vs 63.42M) → **일을 덜 하면서 더 많이 버렸다.**
- [측정] 건강 구간에서는 **MORI의 reload가 TA+O의 2.7~3.1배**인데 **낭비율은 동등하거나 더 낮다**
  (0.056 / 0.055 vs 0.051 / 0.057). [추론] CPU tier를 훨씬 적극적으로 쓰면서도 recompute가 안 늘었다
  = **오프로딩이 생산적으로 작동한다**.
- SMG는 hit 0.016, 낭비율 **0.981** — 사실상 전부 recompute. util 100%의 정체.

## 6.3 ③ goodput (SLO 만족 산출만) [측정 — 구간]

⚠️ per-turn 미저장이라 **분포 가정 없는 순서통계 구간**:
SLO ≥ p95 → 만족률 ≥95% / p50 ≤ SLO < p95 → [50%, 95%) / SLO < p50 → <50%.
goodput = 만족률 × throughput (턴당 출력 토큰이 ttft와 무관하다는 가정 — 이 부분은 **[추론]**).

| 셀 | C | ttft_p50 | ttft_p95 | thr | **SLO 2s: 만족률 / goodput** | **SLO 5s: 만족률 / goodput** |
|---|---|---|---|---|---|---|
| TA_r0_C8 | 8 | 0.83 | 5.15 | 20.3 | [50,95)% / [10.1, 19.3) | [50,95)% / [10.1, 19.3) |
| TAO_r2_C8 | 8 | 0.81 | 3.15 | 20.6 | [50,95)% / [10.3, 19.5) | **[95,100)% / [19.5, 20.6)** |
| **MORI_r2_C8** | 8 | 0.80 | **2.89** | 21.1 | [50,95)% / [10.6, 20.1) | **[95,100)% / [20.1, 21.1)** |
| TA_r0_C10 | 10 | 1.03 | 8.05 | 22.3 | [50,95)% / [11.1, 21.2) | [50,95)% / [11.1, 21.2) |
| TAO_r2_C10 | 10 | 0.97 | 4.97 | 23.3 | [50,95)% / [11.6, 22.1) | **[95,100)% / [22.1, 23.3)** |
| **MORI_r2_C10** | 10 | 0.95 | **4.25** | 23.7 | [50,95)% / [11.8, 22.5) | **[95,100)% / [22.5, 23.7)** |
| MORI_r2_C20 | 20 | 2.08 | 30.62 | 22.2 | [0,50)% / [0.0, 11.1) | [50,95)% / [11.1, 21.1) |
| MORI_r2_C50 | 50 | 4.96 | 119.67 | 11.8 | [0,50)% / [0.0, 5.9) | [50,95)% / [5.9, 11.2) |
| **MORI_r2_C80** | **80** | **13.93** | **398.71** | 6.5 | [0,50)% / [0.0, 3.2) | **[0,50)% / [0.0, 3.2)** |
| TA_r0_C80 | 80 | 2.72 | 113.21 | 11.4 | [0,50)% / [0.0, 5.7) | [50,95)% / [5.7, 10.8) |
| TAO_r2_C80 | 80 | 3.40 | 120.59 | 14.3 | [0,50)% / [0.0, 7.1) | [50,95)% / [7.1, 13.6) |

**[측정] 핵심:**
- **건강 구간에서 MORI가 최고다.** C8/C10에서 **SLO 5s 만족률 ≥95%**를 달성한 것은 MORI와 TA+O뿐이고,
  MORI의 goodput 하한이 가장 높다(≥20.1 / ≥22.5). TA(오프로딩 없음)는 p95가 5.15 / 8.05로 5s를 못 맞춘다
  → **오프로딩이 꼬리 지연을 줄인다**. MORI의 ttft_p95(2.89 / 4.25)가 TA+O(3.15 / 4.97)보다도 낮다.
- **MORI C80은 유일하게 SLO 5s에서도 p50을 못 맞춘다**(p50 = 13.93s) → goodput < 3.2 tok/s.
  같은 C80에서 TA+O ≥7.1, TA ≥5.7.
- MORI의 ttft_p95가 C80에서 **398.71초** — TA+O(120.59)의 **3.3배**.
  [추론] 꼬리가 무너진 것이 goodput 붕괴의 직접 원인이다.

## 6.4 ④ thrashing 탐지: 승격당 출력 / 이동률 / ping-pong [측정]

`출력/promote` = "한 번 GPU로 올려서 실제로 뽑아낸 출력 토큰".
`ping-pong%` = 같은 프로그램이 **2회 이상 강등**된 비율 (로그 순서 기반; 타임스탬프 없어 간격은 불가).

| 셀 | C | oversub | demote | promote | evict | 출력tok | **출력/promote** | **이동/분** | **ping-pong%** |
|---|---|---|---|---|---|---|---|---|---|
| MORI_r2_C2 | 2 | 0.2× | 0 | 0 | 0 | 4,385 | n/a | **0.00** | 0.0 |
| MORI_r2_C4 | 4 | 0.5× | 0 | 0 | 0 | 26,151 | n/a | **0.00** | 0.0 |
| **MORI_r2_C8** | 8 | 1.0× | 22 | 22 | 0 | 61,216 | **2,783** | 0.91 | 50.0 |
| **MORI_r2_C10** | 10 | 1.2× | 131 | 128 | 0 | 66,391 | **519** | 5.54 | 85.0 |
| MORI_r1_C20 | 20 | 2.5× | 212 | 200 | 3 | 47,398 | 237 | 8.45 | 79.1 |
| MORI_r2_C20 | 20 | 2.5× | 375 | 358 | 2 | 63,887 | 178 | 15.29 | 75.9 |
| MORI_r1_C50 | 50 | 6.2× | 462 | 443 | 5 | 24,559 | 55 | 18.72 | 84.1 |
| MORI_r2_C50 | 50 | 6.2× | 598 | 576 | 4 | 33,436 | 58 | 24.89 | 81.5 |
| MORI_r1_C80 | 80 | 9.9× | 520 | 486 | 12 | 21,776 | 45 | 20.59 | 86.2 |
| **MORI_r2_C80** | **80** | 9.9× | 690 | 648 | 9 | 18,740 | **29** | **27.73** | **90.7** |

**[측정] 핵심 — thrashing이 정량적으로 확정된다:**
- **출력/promote가 2,783 → 29로 96배 붕괴** (C8 → C80). C80에서는 한 프로그램을 GPU로 올릴 때마다
  **평균 29 토큰**만 뽑고 다시 내려간다.
- **이동률 0.91 → 27.73회/분** (30배). **ping-pong 50.0% → 90.7%** — C80에서는 강등된 프로그램의
  **10 중 9개가 두 번 이상 강등**된다.
- **[추론] ②의 prefix hit 붕괴(0.944 → 0.600)와 정확히 같은 원인**: 프로그램을 계속 왕복시키면
  KV가 안정적으로 GPU에 머물지 못해 재사용이 깨지고, 그 자리를 recompute가 채운다.
- **[측정] C2/C4는 이동이 정확히 0** — 무압박에서는 왕복 자체가 없다 (A1 스티키의 실런 확인).

## 6.5 Part A 종합 — C80은 어디가 낮은가

| 지표 | 건강 C8 | 건강 C10 | **극단 C80** | 배율 | 같은 C80의 TA+O |
|---|---|---|---|---|---|
| GPU util | 53.2% | 58.7% | **90.5%** | ▲1.7배 | 73.3% |
| ① 생산성 비율 (thr÷util) | 39.7 | 40.3 | **7.2** | ▼5.6배 | **19.5** |
| ② 낭비율 (recompute 비중) | 0.056 | 0.055 | **0.399** | ▲7.2배 | **0.166** |
| ② prefix hit | 0.944 | 0.945 | **0.600** | ▼ | **0.834** |
| ③ goodput @5s | ≥20.1 | ≥22.5 | **<3.2** | ▼7배+ | **≥7.1** |
| ④ 출력/promote | 2,783 | 519 | **29** | ▼96배 | n/a |
| ④ ping-pong% | 50.0 | 85.0 | **90.7** | ▲ | n/a |

**[추론] 한 문장**: C80에서 MORI의 GPU는 **분당 27.7회의 tier 왕복(90.7% ping-pong)으로
prefix cache를 무너뜨리고(hit 0.600), 전체 토큰 작업의 40%를 recompute에 쓰느라 바쁜 것**이며,
그 결과 바쁜 1초당 산출은 7.2(TA+O의 37%), SLO 5s goodput은 3.2 미만(TA+O의 45% 미만)이다.
**util 90.5%는 유용한 일의 지표가 아니었다.**

**[측정] 반대로 건강 구간에서는 모든 지표가 MORI에 유리하다**: 낭비율 최저 수준(0.056/0.055),
SLO 5s 만족률 ≥95%(TA는 미달), goodput 하한 최고(≥20.1/≥22.5), 오프로딩을 TA+O의 3배 쓰면서도
낭비가 늘지 않았다.

## 6.6 ⑤ 시간 분해 (Part B) — `--profile` 최소 run [측정]

- **3셀만** (스윕 아님): `MORI_r2_C10`(건강 1.2×) / `MORI_r2_C80`(극단 9.9×) / `TAO_r2_C80`(극단 대조).
  기존 serve 스크립트·드라이버 무수정, `--profile --profile-dir <셀별>`만 추가.
- 데이터: `step_profiles.csv` — `prefill_s / decode_s / pause_s / tool_call_s / prompt_tokens /
  completion_tokens / completed_at` (`ThunderAgent/profile/state.py:66-104`). warmup 앞 25% 제외.
- 총 **927 스텝** 기록 (C10: 378, MORI C80: 317, TAO C80: 232 — 헤더 포함).

> ⚠️ **해석 주의 4가지**
> 1. `prefill_s`/`decode_s`는 **요청별 wall-clock 국면**이지 GPU 배타 점유 시간이 아니다.
>    동시 요청이 겹치므로 Σ(prefill+decode)는 벽시계보다 크고, 둘 다 엔진 큐잉/배칭 대기를 포함한다
>    → **국면 간 비율 비교**로만 읽어야 한다.
> 2. 이 run은 **420초**다(M-SWP는 3600초). C80은 짧은 run에서 오히려 **더** 열화됐다
>    (드라이버 기준 throughput **1.19** vs M-SWP 6.5, steady_turns **25**뿐). ⑤의 절대값을
>    ①~④ 표와 직접 비교하지 말고 **같은 run 안의 셀 간 비교**로 읽어야 한다.
> 3. (d)의 throughput은 **스텝 단위 출력률**(모든 스텝 ÷ CSV 창)이고, 드라이버의 throughput은
>    **완료 프로그램 기준**이라 정의가 다르다. (d) 안에서는 분자·분모가 일관되므로
>    같은 C에서의 MORI↔TAO 비교는 동일 기준이다.
> 4. `cached_tokens`가 비어 있다 — 이 SGLang 버전이 `usage.prompt_tokens_details.cached_tokens`를
>    안 채운다. per-step `kv_hit_rate`는 n/a이고, 캐시 히트는 ②의 엔진 카운터로 본다.

### (a)(c) 요청 처리 시간 분해

| 셀 | 스텝 | prefill 합 | decode 합 | **decode%** | prefill% | avg prefill | avg decode |
|---|---|---|---|---|---|---|---|
| **MORI_r2_C10** (건강) | 267 | 249.1s | 322.1s | **56.4%** | 43.6% | **0.933s** | **1.206s** |
| **MORI_r2_C80** (극단) | 176 | 2912.5s | 2950.6s | **50.3%** | 49.7% | **16.548s** | **16.765s** |
| **TAO_r2_C80** (대조) | 305 | 2448.8s | 1861.8s | **43.2%** | 56.8% | **8.029s** | **6.104s** |

**[측정]**
- **decode 비율은 C80에서 오히려 떨어지지 않는다** (56.4% → 50.3%). 예상과 다르다.
- 실제로 무너진 것은 **비율이 아니라 절대 속도**: MORI의 스텝당 prefill이 0.93s → **16.55s (17.7배)**,
  decode가 1.21s → **16.77s (13.9배)**.
- **같은 C80에서 MORI는 TAO보다 스텝당 2~3배 느리다** (prefill 16.55 vs 8.03, decode 16.77 vs 6.10).
  같은 시간에 TAO는 305스텝, MORI는 176스텝 — **TAO가 1.7배 더 많은 스텝을 처리했다**.
- [추론] ①의 "TA+O의 바쁜 시간이 더 생산적"은 **decode 비중 차이가 아니라 스텝당 처리 속도 차이** 때문이다.

### (b) ★ TTFT 분해 — "pause가 TTFT를 지배한다"를 [추론] → **[측정] 확정**

체감 TTFT = `pause_s`(스케줄러 대기, GPU 시간 아님) + `prefill_s`(실제 프리필).

| 셀 | ttft_p50 | └ pause_p50 | └ prefill_p50 | ttft_p95 | └ pause_p95 | └ prefill_p95 | **pause 점유** | **pause>0 스텝%** |
|---|---|---|---|---|---|---|---|---|
| **MORI_r2_C10** | 0.64s | **0.00s** | 0.63s | 2.67s | 0.01s | 2.67s | **0.9%** | **0.4%** |
| **MORI_r2_C80** | 45.83s | **38.30s** | 15.29s | 149.70s | 127.87s | 33.60s | **68.4%** | **75.0%** |
| **TAO_r2_C80** | 5.95s | **0.00s** | 4.31s | 110.76s | 88.87s | 26.12s | 69.7% | **35.7%** |

**[측정] 가장 결정적인 수치:**
- **건강 구간(C10)에서 pause는 사실상 0** — 중앙값 0.00초, 전체 TTFT의 **0.9%**, 스텝의 **0.4%**만
  대기를 겪었다 → **오프로딩이 지연을 만들지 않는다.**
- **극단 구간(MORI C80)에서 pause가 TTFT의 84%를 차지한다** (중앙값 45.83초 중 **38.30초**).
  스텝의 **75.0%**가 스케줄러 대기를 겪는다. **이제 이건 추론이 아니라 실측이다.**
- **★ MORI와 TAO의 결정적 차이는 "얼마나 자주 세우는가"다.** 같은 C80에서 TAO의 **중앙값 스텝은
  pause가 0.00초**이고 대기 스텝이 **35.7%**뿐인데, MORI는 중앙값 **38.30초**에 **75.0%**가 대기한다.
  (pause '점유율'은 68.4% vs 69.7%로 비슷해 보이지만, 이는 TAO의 대기가 소수 꼬리에 집중된 반면
  MORI는 전면적이라는 사실을 가린다 — **중앙값과 비율을 함께 봐야 하는 이유**.)
- [추론] 이것이 ④의 thrashing이 성능으로 나타나는 **경로**다: 왕복이 잦을수록 요청이
  `waiting_event`에서 대기하고, 그 대기가 곧 TTFT가 된다. 같은 420초 run에서 MORI C80의 tier 이동은
  **demote 218 / promote 202** (C10은 11 / 11)였다.

### (d) ★ 정확 goodput — ③의 구간을 실측으로 대체

SLO 만족 스텝(= `pause_s + prefill_s ≤ SLO`)의 `completion_tokens` 합 ÷ 창 길이.

| 셀 | thr (스텝기준) | **SLO 2s: 만족% / goodput** | **SLO 5s: 만족% / goodput** |
|---|---|---|---|
| **MORI_r2_C10** (건강) | 35.3 | **91.0% / 32.0** | **99.6% / 35.1** |
| **MORI_r2_C80** (극단) | 22.3 | 3.4% / **0.4** | 5.7% / **0.7** |
| **TAO_r2_C80** (대조) | 39.1 | 23.9% / **8.4** | 45.2% / **17.1** |

**[측정]**
- **건강 구간 MORI는 SLO 5초를 99.6% 만족**하고 goodput이 throughput과 거의 같다(35.1 / 35.3)
  → 이 레짐에서는 **처리량이 곧 유용한 산출**이다.
- **극단 구간 MORI의 goodput은 0.7 tok/s** — throughput 22.3의 **3%**만 SLO를 만족한다.
  Part A ③의 순서통계 상한 "<3.2"를 실측이 훨씬 아래에서 확정했다.
- **같은 C80에서 TAO의 goodput은 17.1로 MORI의 24배**다. raw throughput 격차는 39.1 vs 22.3 = **1.8배**에
  불과한데 **goodput 격차는 24배**로 벌어진다 → **throughput만 보면 격차를 13배 과소평가하게 된다.**

### ⑤ 종합
1. **[측정] 건강 구간(C10): pause 0.9%, SLO 5s 만족 99.6%, goodput ≈ throughput.** 오프로딩이
   지연 비용 없이 작동한다.
2. **[측정] 극단 구간(MORI C80): pause가 TTFT의 84%(중앙값 38.3s), 스텝의 75%가 대기,
   goodput 0.7 = throughput의 3%.** GPU가 90.5% 바쁜 시간의 정체는 여기서 완결된다.
3. **[측정] MORI↔TAO 차이의 실체는 "정지 빈도"다** — 중앙값 pause 38.30s vs 0.00s,
   대기 스텝 비율 75.0% vs 35.7%, 스텝당 처리 2~3배 느림. ①의 생산성 격차(7.2 vs 19.5)의 직접 원인.
4. **[측정] 예상과 달리 decode 비중은 안 떨어졌다** (56.4% → 50.3%). 무너진 건 비율이 아니라
   스텝당 절대 속도(prefill 17.7배, decode 13.9배 증가)다.

---

# 7. 미해결 & 다음 단계

## 7.1 B1(b) "busy는 GPU에 남는다" — 미확정
[측정] run 2에서 LONG은 확실히 demote됐지만 압박이 과해 SHORT들도 함께 내려가 분리 실패.
run 3/4에서는 압박 자체가 사라졌다.
**재시도법**: ι 분리가 큰 워크로드(예: SHORT의 tool call을 0.1초로)로 ι 격차를 키우고,
오버플로가 **정확히 LONG 1개분**이 되게 정밀 사이징한다. F4(컨텍스트 성장이 압박의 원천)를
감안하면 트리밍을 끄고 성장에 맡기되, 성장 속도를 관측해 사이징을 맞춰야 한다.

## 7.2 엔진측 typed eviction 실제 축출 효과 — 미검증 (F5)
sglang 미설치 + `_MoriHostStrategy`가 `install()` 클로저-로컬(`scripts/mori_hicache_yunuikang.py:51`)이라
격리 호출 불가. **재구현하지 않았다.** 검증하려면 sglang이 설치된 환경에서 실런하며
radix node 축출 순서를 직접 관측해야 한다.

## 7.3 데이터플레인 ι 측정 경로 / "pause 시간 ι 제외" — 코드 읽기로만 확인
`update_program_before_request` / `update_program_after_request` 경로는 실제 요청/응답이 필요해
틱 격리 호출로는 실행되지 않는다. [추론] `push_acting`이 `super()` 호출 이전(`mori_router.py:71-73`)이고
PAUSED 대기는 `super()` 안(`router.py:416-419`)이라 제외되는 것으로 **읽힌다**.
⑤에서 `pause_s`가 독립 필드로 측정된 것은 이 경로의 *간접* 방증이지만, ι 표본에서 실제로
빠지는지는 여전히 미검증이다.

## 7.4 F7 — 축출 방향 반대, 논문 §4.3.2 원문 대조 필요
라우터 `_mori_evict_cpu`는 **ι 최고(idle)부터** 축출하는데, hicache의 host tier `_MoriHostStrategy`는
`-priority`로 **busy부터** 축출한다(docstring이 §4.3.2 인용). 두 객체는 서로 다른 것
(라우터 장부 tier vs 엔진 host KV pool)이라 모순이 아닐 수 있으나, 방향이 반대이므로
**논문 §4.3.2 원문 대조가 필요**하다. 이번 검증에서는 판정하지 않았다.

## 7.5 demote/promote 랭킹의 동률 규칙 — 논문에 명시 없음
§4.3.2의 LRU tie-break는 **축출 규정**이고, §4.3.1의 demote/promote 랭킹에는 동률 규칙이 없다.
근거 없이 확대 적용하지 않았다. 원문 대조 후 판단할 항목.
관련: `touch()`의 잠재적 추가 호출 지점(`_mori_promote`에서 `cpu_pending`인데 자리가 없어
승격 못 한 경우)도 행동 변화를 동반하므로 미적용.

## 7.6 잔여 baseline 이슈 (수정 안 함이 맞음)
- **F2 과잉 마킹**: tr/MORI 공통, 회계식 동일(둘 다 −100) → 비교에 중립.
  `remaining_capacity()`를 고치는 것은 baseline 수정이고, MORI만 우회하면 불변식 I2가 깨진다.
- **F6 주석/코드 불일치** (`router.py:798`): baseline 문서 결함, 이번 범위 밖.
- **F3 기아**: baseline `_greedy_resume`(`router.py:885-905`)도 동일 → tr/MORI 공통, 비교 중립.
  실 trace에서는 프로그램 완료·release로 용량이 회전해 드러나지 않는다.

## 7.7 극단 레짐 개선 방향 (검증 아님, 관측에서 도출된 가설) [추론]
④·⑤가 가리키는 것은 **oversub가 커질수록 이동 자체가 비용이 된다**는 점이다
(출력/promote 29, ping-pong 90.7%, pause 중앙값 38.3s). `min_dwell_ticks`를 부하에 따라 키우거나
oversub 임계 이상에서 오프로딩을 자제하는 것이 자연스러운 방향이지만,
**논문에 그런 규정이 없으므로 이번 검증 범위에서는 제안만 기록한다.**

---

# 8. 부록

## 8.1 신규 파일 (전부 `_yunuikang` 접미사)

### 테스트 (A 계층)
| 파일 | 역할 |
|---|---|
| `tests/mori_harness_yunuikang.py` | scheduler-in-a-box 하네스 (MoriRouter + baseline 라우터 양쪽) |
| `tests/test_mori_policy_yunuikang.py` | A1~A7f 17개 정책 테스트 + 자체 러너 |
| `tests/test_mori_a2c_baseline_yunuikang.py` | A2c baseline 대조 4개 |

### 계측·분석 스크립트 (B/C 계층)
| 파일 | 역할 |
|---|---|
| `scripts/mori_analyze_behavior_yunuikang.py` | B0/B2/B3 — 기존 M-SWP 로그 채굴 (읽기 전용) |
| `scripts/mori_b1_probe_yunuikang.py` | B1 — 통제 워크로드 + `/health`·`/metrics` 샘플러 |
| `scripts/mori_analyze_b1_yunuikang.py` | B1 산출물 분석 |
| `scripts/run_mori_b1_yunuikang.sh` | B1 런처 (기존 serve 스크립트를 env로만 호출) |
| `scripts/mori_usefulwork_yunuikang.py` | STEP 7 Part A ①~④ (읽기 전용 재집계) |
| `scripts/run_mori_profile_yunuikang.sh` | STEP 7 Part B — `--profile` 3셀 런처 |
| `scripts/mori_analyze_profile_yunuikang.py` | STEP 7 ⑤ 분석 (시간 분해 + 정확 goodput) |

### 수정된 파일 — **2개뿐** (§4.2의 A7c 수정)
```
 ThunderAgent/scheduler/mori_router.py | 10 +++++++--
 ThunderAgent/scheduler/mori_tier.py   | 41 +++++++++++++++++++++++++++++++++--
 2 files changed, 47 insertions(+), 4 deletions(-)
```
**baseline 0-line diff 확인 완료**: `ThunderAgent/scheduler/router.py`, `ThunderAgent/backend/state.py`,
`ThunderAgent/profile/state.py`, `ThunderAgent/program/state.py`, `ThunderAgent/app.py`,
`scripts/_serve_sglang_8b_tp2_mori_yunuikang.sh`, `scripts/mori_replay_driver_yunuikang.py`,
`scripts/sample_gpu_resident_yunuikang.py`, `scripts/run_msw_*.sh` — 전부 무수정. **커밋 없음.**

### 기존 테스트 (본 검증 전부터 존재, 회귀 확인용)
`tests/test_mori_idleness_yunuikang.py`, `tests/test_mori_invariants_yunuikang.py`

## 8.2 재현 커맨드

```bash
cd /home/yunuikang/yunuikang_work/distserving

# --- A 계층 (GPU 불필요, pytest 없어도 동작) ---
python tests/test_mori_policy_yunuikang.py           # 17/17 passed
python tests/test_mori_a2c_baseline_yunuikang.py     # 4/4 passed
python tests/test_mori_idleness_yunuikang.py         # 회귀 확인
python tests/test_mori_invariants_yunuikang.py       # 회귀 확인
# pytest가 설치된 환경이라면 그대로 호환:
#   python -m pytest tests/test_mori_policy_yunuikang.py -v

# --- B/C 계층 분석 (GPU 불필요, 기존 로그 재집계) ---
python scripts/mori_analyze_behavior_yunuikang.py    # B0 tier이동 / B2 util / B3 reload
python scripts/mori_usefulwork_yunuikang.py          # STEP 7 ①~④
python scripts/mori_analyze_profile_yunuikang.py     # STEP 7 ⑤ (profile run 산출물 필요)

# --- B1 통제 run (GPU 필요, ~10분) ---
TAG=b1_mori NSHORT=5 SYSTOK=9000 WARM=90 LONG=90 TAIL=30 DEADLINE=420 \
  bash scripts/run_mori_b1_yunuikang.sh
python scripts/mori_analyze_b1_yunuikang.py \
  --prefix ~/yunuikang_work/scratch/mori/b1/b1_mori \
  --proxy-log ~/yunuikang_work/scratch/mori/b1/proxy_b1_mori.log

# --- STEP 7 Part B profile run (GPU 필요, 3셀 ~27분) ---
bash scripts/run_mori_profile_yunuikang.sh
```

## 8.3 원본 로그 5개 (보존, 수정/삭제하지 않음)

| 파일 | STEP | 내용 |
|---|---|---|
| `logs/mori_verify_symbol_audit_yunuikang.md` | 1 | 코드 대조 (symbol audit) — 본 문서 §2 |
| `logs/mori_verify_policy_results_yunuikang.md` | 2~5 | A 계층 A1~A7 + A7c 수정 — 본 문서 §3, §4.2 |
| `logs/mori_verify_A2c_baseline_yunuikang.md` | 5 | A2c baseline 대조 — 본 문서 §4.1 |
| `logs/mori_verify_behavior_results_yunuikang.md` | 6 | B 계층 실동작 — 본 문서 §5 |
| `logs/mori_verify_usefulwork_yunuikang.md` | 7 | 유용한 일 ①~⑤ — 본 문서 §6 |

## 8.4 실험 데이터 위치

| 경로 | 내용 |
|---|---|
| `~/yunuikang_work/scratch/mori/msw/` | M-SWP 30셀 (results_msw{,_lowc}.jsonl, gpu_*.jsonl, proxy_*.log) |
| `~/yunuikang_work/scratch/mori/b1/` | B1 통제 run 4회 (samples.csv / turns.jsonl / summary.json / ARCHIVE 로그) |
| `~/yunuikang_work/scratch/mori/prof/` | STEP 7 Part B profile run 3셀 (profile_*/step_profiles.csv, results_prof.jsonl) |
| `~/yunuikang_work/scratch/mori/b0_summary.json`, `usefulwork_A.json`, `usefulwork_B.json` | 분석 스크립트 JSON 덤프 |

## 8.5 환경
- 하드웨어: goguma6, RTX 5090 ×2 (sm_120)
- 모델/엔진: Qwen/Qwen3-8B, TP2, SGLang (HiCache, `--radix-eviction-policy mori`)
- python: `/home/yunuikang/yunuikang_work/.venv` (프록시/분석), `.venv-sglang` (엔진)
- ⚠️ **pytest / pip 미설치** — 테스트는 자체 러너로 실행 (§1.4)
- SGLang 툴체인 (goguma6): `CUDA_HOME=/usr/local/cuda-13.0`, gcc-11, `--disable-custom-all-reduce`
