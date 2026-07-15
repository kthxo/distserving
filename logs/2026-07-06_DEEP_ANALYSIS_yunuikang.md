# 심화 분석 — 조사 A(eviction 경로) + 조사 B(재프리필 재정의·메모리 지표) (2026-07-06)

> 작성: 강윤의 · 브랜치 `yunuikang/thunderagent` · 2026-07-06
> 전제 문서: `2026-07-06_MECHANISM_REFERENCE_yunuikang.md`(Phase 0). 이 문서는 그 로직으로 결과를 재서술.
> 근거: 코드 + 기존 결과 JSONL(재분석, **새 GPU 실행 없음**) + vLLM 시작 로그.
> 대응 피드백: (e) KV 초과 처리(swap 여부), (b) 재프리필 정확히 뭔지·왜 쟀나, (c) 용량을 메모리 지표로.

---

## 조사 A — KV가 GPU 메모리 초과 시 실제 처리: **eviction = 재프리필** (CPU swap 아님) 확정

### A-1. 질문
active KV 수요 > GPU KV 풀일 때 경로가 (a) pause+KV 폐기→재프리필 / (b) vLLM이 CPU로 swap(offload) /
(c) 둘 다 중 무엇인가? (모든 재프리필 해석의 전제)

### A-2. 증거 4종
1. **코드에 swap 설정이 없다.** `grep -r swap scripts/ ThunderAgent/` → 0건. vLLM serve 명령
   (`--max-model-len 32768 --gpu-memory-utilization 0.92`)에 `--swap-space` 미지정.
2. **vLLM V1 엔진은 CPU swap을 아예 안 쓴다.** 시작 로그: `Initializing a V1 LLM engine (v0.24.0)`.
   config dump에 **`swap_space` 필드 자체가 없음**(V1은 KV를 CPU로 내리는 swap을 폐기하고 **재계산
   (recompute) 기반 preemption**만 사용). `num_cpu_blocks`/`CPU KV cache` 로그도 없음. → offload 경로 부재.
3. **tr의 pause는 vLLM에 아무 신호를 안 준다.** `_pause_program`(router.py:631-658)은 백엔드 추적에서
   unregister만 하고, paused 프로그램의 다음 요청은 `update_program_before_request`에서 `_wait_for_resume`로
   **프록시에서 블록**(router.py:416-419) → vLLM은 그 요청을 **아예 못 본다**. 즉 pause는 애플리케이션
   레벨 큐잉이고, 그 사이 vLLM의 prefix-cache 블록은 **다른 요청에 밀려 LRU로 자연 evict**된다.
4. **preemption이 실측상 ≈0.** D(2×4090) 18런의 `num_preemptions_delta`: tr {0, 최대 0.3}, default {0,1,2}.
   수백만 토큰 처리 중 최대 2회 → vLLM 자체 preempt/swap은 **사실상 미발동**.

### A-3. 결론 (전제 확정)
- **경로 (a) 확정, (b)/(c) 배제.** KV 초과분은 CPU로 내려가지 않는다. 처리 경로는:
  - **default**: 프로그램 단위 통제 없음 → 새 요청이 KV 풀을 채우며 **다른 프로그램의 prefix 블록을
    LRU로 덮어씀** → tool 뒤 다음 턴에 그 프로그램 전체 컨텍스트를 **재프리필**(recompute).
  - **tr**: Eq.6 위반이면 가장 작은 프로그램을 **pause(프록시 큐)** → GPU 밖에서 대기 → 캐시 소실을
    사전 차단. (단 resume 시 이미 evict됐으면 재프리필. 논문 §4.3.2 node-agnostic 가정과 정합.)
- **따라서 "재프리필"은 vLLM swap-in/out이 아니라 prefix-cache LRU eviction의 결과**다. 논문 p19의
  "swap-in/out latency penalty"는 **우리 스택(V1, swap 미설정)엔 적용되지 않음** — 이 점을 발표에서 구분.
- ⚠️ 정직: preemption이 정확히 0은 아니다(default 최대 2회). 그러나 재프리필의 지배 원인은 preemption이
  아니라 **턴 간 prefix 블록 eviction**임을 아래 조사 B가 수치로 뒷받침.

---

## 조사 B — 재프리필 재정의 + 용량 논의를 "메모리 지표"로

### B-1. 재프리필이 정확히 무엇을 세는가 (코드로 규명)
vLLM `/metrics` 카운터(`vllm_metrics.py`):
| 카운터 | 의미 | 재프리필 지표로 적합? |
|--------|------|----------------------|
| `prompt_tokens_total` | 처리한 **논리적 프롬프트 토큰** 총량 | ❌ **아니다** — 캐시 히트/미스와 무관하게 거의 일정 |
| `prefix_cache_queries` | prefix 캐시에 조회된 토큰(블록) 수 | 분모(조회량) |
| `prefix_cache_hits` | 그중 캐시에서 찾은 수 | 절약분 |
| **`queries − hits`** | **캐시 미스 = 다시 프리필해야 하는 양** | ✅ **재프리필(recompute)의 방향 지표** |
| `hit_rate = hits/queries` | 캐시 재사용률 | ✅ **미스율 = 1−hit = 재계산 압력**(robust) |

**★ 발견/수정(중요)**: 기존 로그(§D-6, F/G)가 "재프리필"로 표기한 **`prompt_tokens_total` 델타는 실제
재계산량이 아니다.** D에서 그 값은 tr/default·전 concurrency에서 **~7.3M로 평탄**(= offered 입력량):

```
D (2x4090, real) — c별  reprefill_miss(=q−h)   prompt_tokens_total   hit(tr/def)
  c=2   1.30 / 1.30 M        7.35 / 7.35 M       0.823 / 0.823
  c=8   (미스율로)            7.30 / 7.34 M       0.800 / 0.210
  c=16                        7.34 / 7.34 M       0.799 / 0.047
  c=48                        7.32 / 7.33 M       0.772 / 0.026
```
- `prompt_tokens_total`이 평탄한데 hit rate는 0.80→0.026으로 붕괴 → **prompt_tokens_total로는 스래싱이
  안 보인다.** 재프리필은 반드시 **미스율(1−hit)** 또는 미스량(queries−hits)으로 봐야 한다.
- ⚠️ **정직/한계**: 절대 미스 토큰(`queries−hits`)은 default에서 ~200M로 나오나, 이는 `prompt_tokens_total`
  (~7M)과 **1:1로 안 맞는다**(vLLM V1의 `prefix_cache_queries`가 prompt_tokens와 **다른 granularity**,
  블록/스텝 단위 누적으로 추정). 따라서 **절대 미스량은 신뢰하지 않고, 미스율(1−hit)만** 지표로 쓴다.
  → 그래프 `figures/deepB_D_missrate.png`: default 미스율 0.18→**0.97**, tr 평탄 ~0.20-0.23.

### B-2. 왜 쟀나 · 용량비와 무슨 인과인가
- **왜**: 재프리필(미스)은 **Eq.6 위반(스래싱)의 관측 가능한 결과**다(Phase 0 §1-2). tool 중 KV가 evict→
  다음 턴 미스→재계산. 미스율이 곧 "스래싱이 얼마나 심한가".
- **용량비 인과**: 프로그램 peak KV(§D-char median 2.87 GiB) ÷ 백엔드 KV 풀(4090 6.03 GiB / 5090 12.23 GiB)
  → **동시 resident 상한 4090≈2, 5090≈4**. offered concurrency가 이 상한을 넘으면:
  - default: 초과분이 KV를 밀어내 미스 폭증(위 0.97).
  - tr: 초과분을 pause로 빼 resident를 상한 이내로 유지 → 미스 억제(0.2).

### B-3. 용량을 "메모리 지표"로 — 단, 사용률만으로는 부족(정직한 정교화) ★
피드백 (c)는 "용량을 프리필 말고 메모리 지표로"였다. 직접 메모리 지표 = **`kv_cache_usage_perc`**.
그런데 F/G 재분석 결과(그래프 `deepB_{F,G}_kv_usage_peak.png`):

```
F (합성, 4090+5090) KV usage peak — tr / default
  c=8 : 4090 0.99/0.99   5090 0.93/0.65
  c≥16: 4090 0.99/0.99   5090 0.96/0.96
G (실제, 4090+5090) KV usage peak — tr / default
  c≥8 : 4090 0.95-0.96/0.98-0.99   5090 0.86-0.96/0.89-0.99
```
- **핵심 관찰**: KV usage(포화도)는 **tr·default 둘 다 거의 1.0으로 포화**한다. 즉 "메모리가 얼마나 찼나"
  **하나만으로는 tr과 default가 구별되지 않는다.** 둘 다 풀을 꽉 채운다.
- **진짜 차이는 "그 메모리가 무엇을 담고 있나"**: default는 계속 덮어써지는 쓰레기(hit 0.03), tr은 재사용
  가능한 캐시(hit 0.77). → **용량을 제대로 보려면 (i) kv_usage(포화) + (ii) hit rate(캐시 유효성) +
  (iii) pause(tr의 통제 행동) + (iv) resident 수를 함께** 봐야 한다. 사용률 단독은 오해를 부른다.
- **pause(메모리 통제 행동)**: `deepB_{F,G}_pause_peak.png`. tr은 pause>0(F/G 모두 저부하 4090, 고부하 5090에
  소수 분산), **default는 전 구간 pause=0**(통제 없음). → tr이 "메모리를 pause로 능동 관리"함을 직접 보임.

### B-4. 5090 과소활용 = 신규배정 로직의 직접 결과 (메모리 지표로 재확인)
`deepB_{F,G}_split_vs_capacity.png`: tr이 5090으로 보내는 비율 vs 용량 비례선(0.67).
- 용량 비례라면 5090에 **0.67**을 보내야 하나, tr 실측은 F ~0.6, G ~0.5(±). → **5090 과소활용.**
- **원인은 Phase 0 §2-1**: `_select_backend_for_new_program`이 `active_program_tokens` **절대 최소**(용량
  비례 아님, router.py:358)를 고르기 때문. 즉 "메모리 여유가 2배인 5090을 2배 활용하지 않는다".
  → **용량 비례 라우팅 필요성**의 코드적·메모리지표적 근거.

### B-5. 조사 B 산출물
- 스크립트: `scripts/plot_deepB_yunuikang.py`(기존 JSONL 재분석, GPU 0).
- 그래프(7종): `figures/deepB_F_kv_usage_peak.png`, `deepB_F_pause_peak.png`, `deepB_F_split_vs_capacity.png`,
  `deepB_G_*`(동일 3종), `deepB_D_missrate.png`.
- **재프리필 주지표 = 미스율(1−hit)**, kv_usage·pause·split = 메모리/통제 지표, prompt_tokens_total = 폐기(오지표).

---

## 종합 — 이 두 조사가 확정한 것 (실험 C·재서술의 토대)
1. **eviction=재프리필**(CPU swap 아님, V1). → "재프리필"은 prefix-cache LRU eviction의 결과.
2. **재프리필의 올바른 척도 = 미스율(1−hit)**. prompt_tokens_total은 스래싱을 못 보여줌(폐기).
3. **메모리 사용률(kv_usage)은 tr·default 둘 다 포화 → 단독으로 무의미**; hit·pause·resident와 함께 봐야 함.
4. **5090 과소활용 = 절대-토큰 균형 배정(router.py:358)의 직접 결과** — 용량 비례 라우팅 근거.
- ⏳ 아직 못 한 것(→ 실험 C): **resident 수 시계열·GPU util·idle(starvation)·pause 대기시간**은 기존 JSONL에
  없어 재실행 필요. D의 per-backend kv_usage 시계열도 D 재실행(profile+촘촘 샘플링)에서 확보.
