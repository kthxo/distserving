# vLLM 내부 동작 검증 — "우리가 그린 GPU 그림 vs 실제 vLLM" (2026-07-17)

> 작성: 강윤의 · 브랜치 `yunuikang/thunderagent` · 서버 **mango1**(4×RTX4090, 전부 유휴 — TP2 스윕은 nutella1이라 무간섭)
> 근거: **설치된 vLLM 0.24.0 실소스**(`/home/yunuikang/yunuikang_work/.venv/.../vllm/`) 정독 + **expC 기존 JSONL/CSV 재분석(GPU 0장)** + 논문 원문
> 가드레일 준수: `router.py` 미수정, 신규 파일 전부 `*_yunuikang`, **GPU 미사용**(§7에서 승인 요청)
> 스크립트: `scripts/plot_vllm_profiling_yunuikang.py` · 그림: `figures/vllm_*.png`

---

## 0. 세 줄 요약 (먼저 읽을 것)

1. **R 모델은 살아남았고, 오히려 물리적 의미를 얻었다.** `R = k_fit·d`는 추상적 지표가 아니라 **vLLM에서 동시에 실행 중인 요청 수의 기댓값**이다 — 실측 `mean num_requests_running`과 일치한다(default C=16: R=1.20 vs 실측 1.24). `U = P(nrr ≥ 1)`이므로 R<1에서 `U≈R`은 항등식에 가깝다.
2. **그러나 우리가 그려온 그림 중 두 개는 틀렸다.** (a) "default는 배치를 크게 가져간다"는 **거짓** — 실제 GPU 배치는 tr·default 모두 **1.1~1.5**로 고정이다. (b) "default는 pause가 0"은 **측정 착시** — default도 줄을 서지만 **vLLM 내부 큐**에서 서기 때문에 프록시 profiler에 안 잡힌다(실측: TTFT 10.79s 중 ~9.5s가 큐 대기).
3. **hit rate 지표가 오염돼 있었다 — 그리고 오염은 비대칭이다(실측).** vLLM V1은 waiting 큐에서 승인 실패한 요청을 매 step 재계수한다. **default만 26.3배 팽창해 참 hit를 4.81배 과소평가**(참 0.1844 vs 보고 0.0383)했고, **tr은 팽창 1.0배로 애초에 정확**했다(참 0.6983 = 보고 0.6983). 지표 버그와 물리 메커니즘이 **같은 현상**이다.
4. **★ 그 결과 throughput 식이 닫혔다.** 참 hit를 넣자 `thr ∝ U/W` 예측이 **실측 대비 오차 28.2% → 1.4%**. **R 모델(U) + 참 재프리필 비용(W), 두 항이면 tr/default 승패가 예측된다.**
5. **정직**: 실험 도중 "tr 스케줄러 데드락"을 발견했다고 판단했으나, **내 하네스가 `--router-url`을 빠뜨린 자작 버그였다(§7-B-4에서 전면 철회).** expC 데이터는 깨끗하다.

---

## 1. Phase 1 — 코드 정독: 우리가 가정한 것 vs vLLM 실제

### 1-0. 총괄 표

| # | 우리가 가정한 것 | vLLM 0.24.0 실제 | 파일:라인 | 우리 해석에 미치는 영향 |
|---|---|---|---|---|
| 1 | prefill/decode는 별개 단계 | **단계 구분 자체가 없음.** 모든 요청이 `num_computed_tokens`를 `num_tokens_with_spec`까지 따라잡는 하나의 통합 배치 | `v1/core/sched/scheduler.py:390-399` | "prefill이 decode를 밀어낸다"는 **부정확**. §1-1 참조 |
| 2 | max_num_batched_tokens는 크다 | **2048** ✅ **실측 확정**(2026-07-17, 실제 4090에서 `EngineArgs.get_batch_defaults(world_size=1)` 실행 → OPENAI_API_SERVER: 2048) | `engine/arg_utils.py:2414-2423, 2583-2592, 2638-2641` | **18.7k 프롬프트 1개 = 약 10 iteration의 청크 프리필**. 결정적 |
| 3 | max_num_seqs는 제약 | **256** ✅ **실측 확정**(동일 방법) — k_fit(1.6~10.5)에 전혀 안 걸림 | `engine/arg_utils.py:2420-2423, 2649-2651` | **제약 아님.** 병목은 KV 블록이지 seq 슬롯이 아님 |
| 4 | KV 초과 시 preemption | **RECOMPUTE preempt는 존재하나 조건이 좁다** — RUNNING 요청의 `allocate_slots`가 None일 때만 | `scheduler.py:524-568, 1107-1125` | 실측 preemption≈0과 **정합**(§1-3) |
| 5 | C_total = block_size×num_gpu_blocks | **정확히 일치** (기동 로그 `GPU KV cache size: 43,888 tokens`) | `ThunderAgent/backend/vllm_metrics.py:23-25` / vLLM `v1/core/kv_cache_utils.py:2146` | 우리 C_total은 **옳다** |
| 6 | prompt_tokens_total = 재프리필 지표 | **논리적 총 프롬프트**(캐시 히트 포함) → 캐시와 무관하게 평탄 | `v1/metrics/stats.py:308, 344-347`; `loggers.py:1157` | **DEEP_ANALYSIS의 "오지표" 판정이 코드로 확증됨** ✅ |
| 7 | 절대 재프리필량은 측정 불가 | **측정 가능했다.** `vllm:prompt_tokens_by_source{source="local_compute"}` = 실제 계산 토큰 | `v1/metrics/stats.py:281, 292-322`; `loggers.py:643-664, 1161-1164` | **우리가 놓친 지표.** §1-2·§7 |
| 8 | queries−hits의 granularity가 다르다 | **granularity는 같다.** 원인은 **waiting 큐 재검사 중복 계수** | `scheduler.py:673-712, 888-895, 917, 1141-1143` | **B-1 미해결 질문 해소** ✅ §1-2 |

### 1-1. ★ 핵심 질문 — "GPU가 채워진다"는 (a) 시간축인가 (b) 배치인가?

**질문**: 나는 "프로그램 1·2·3의 reasoning 구간이 시간축에서 인터리브되어 GPU를 채운다"로 사고해 왔다. 그러나 continuous batching이면 (b) 배치가 커지는 것 아닌가?

**증거 1 (코드)** — V1 스케줄러에 단계 구분이 없다:
> `scheduler.py:390-399`: *"There's no 'decoding phase' nor 'prefill phase' in the scheduler. Each request just has the num_computed_tokens and num_tokens_with_spec. At each step, the scheduler tries to assign tokens to the requests so that each request's num_computed_tokens can catch up its num_tokens_with_spec."*

한 iteration의 구성:
1. **RUNNING 먼저** 스케줄 (`scheduler.py:432`), 각 요청이 `num_new_tokens`만큼 `token_budget`(=2048)에서 차감. decode 중인 요청은 1토큰, 프리필 중인 요청은 최대 잔여 budget.
2. **그 다음 WAITING** (`scheduler.py:626`), 단 **이번 step에 preemption이 있었으면 아예 승인 안 함**(`if not preempted_reqs`).

**증거 2 (실측)** — `figures/vllm_batch_refutes_H2.png`, `figures/vllm_timeline_tr_vs_default.png`:

| run | k_fit(프록시 resident) | mean nrr | **실제 배치 = mean nrr\|nrr>0** | U(nrr>0) |
|---|---|---|---|---|
| tr C=16 | 1.60 | 0.38 | **1.19** | 0.317 |
| default C=16 | 6.15 | 1.24 | **1.45** | 0.855 |
| default C=32 | 10.50 | 1.29 | **1.44** | 0.893 |

**결론**: **답은 (a) 시간축이다.** k_fit이 1.6→10.5으로 **6.6배** 늘어도 실제 GPU 배치는 **1.19→1.44 (+21%)** 밖에 안 커진다. default가 이기는 이유는 "한 번에 더 많이 처리해서"가 **아니라** "GPU가 놀지 않는 시간이 많아서"(U 0.317→0.855, **2.7배**)다.

**왜 배치가 안 커지나 [추정, 근거 있음]**: `max_num_batched_tokens=2048`인데 TraceLab 프롬프트는 mean 18,684 tok. 프리필 1건이 budget 2048을 **약 10 iteration 동안 독점**한다. 그동안 다른 요청의 decode(1토큰씩)는 RUNNING 우선 규칙으로 **밀려나진 않지만**, 애초에 동시 REASONING 요청 수 자체가 적다(mean_reas: tr 0.49 / default 4.56 중 실제 vLLM running은 1.24). → 배치가 커질 재료가 없다.

**따라서 R 모델의 물리적 의미가 확정된다**:
> **R = k_fit × d = "동시에 GPU 일을 원하는 프로그램 수의 기댓값" ≈ mean num_requests_running**
> **U = P(nrr ≥ 1)**. R<1이면 점유가 대부분 0/1이라 `P(N≥1) ≈ E[N] = R` → **U≈R은 근사 항등식**.

실측 대조 (**R = k_fit·0.196 vs 실측 mean_nrr**):

| run | R = k_fit·d | 실측 mean_nrr | 오차 |
|---|---|---|---|
| default C=4 | 0.36 | 0.36 | **0.00** |
| default C=8 | 0.67 | 0.92 | +0.25 |
| default C=16 | 1.20 | 1.24 | **+0.04** |
| tr C=16 | 0.31 | 0.38 | +0.07 |
| default C=32 | 2.06 | 1.29 | −0.77 (**포화**: nrr은 배치≈1.44에 물리 상한) |

→ **R은 활용률이 아니라 "요청 수요"였다.** R≥1에서 nrr이 1.44에 묶이는 것이 "실측 U가 예측 U를 하회"(expC §5 한계)의 **정확한 물리적 원인**이다.

### 1-2. ★ prefix cache 카운터 — B-1 미해결 질문의 코드적 확정

**질문**(DEEP_ANALYSIS §B-1): "절대 미스 토큰 ~200M가 prompt_tokens ~7M와 1:1로 안 맞는다. granularity가 다른 듯."

**증거 (코드)** — 계수 지점은 **한 곳**이고, 세는 단위는 **동일**하다:
```python
# v1/core/kv_cache_manager.py:234-240  (get_computed_blocks 내부)
if self.log_stats:
    self.prefix_cache_stats.record(
        num_tokens=request.num_tokens,        # ← 프롬프트 전체 길이
        num_hits=num_new_computed_tokens,
        preempted=request.num_preemptions > 0)
# v1/metrics/stats.py:131-142 → queries += num_tokens ; hits += num_hits
```
`prompt_tokens_total`도 같은 프롬프트 길이를 센다(`stats.py:308` `self.total += prefill_stats.num_prompt_tokens`). **즉 granularity는 다르지 않다.**

**진짜 원인 — waiting 큐 재검사 중복 계수**:
```python
# v1/core/sched/scheduler.py:636   request = request_queue.peek_request()   ← pop 아님
# v1/core/sched/scheduler.py:673   if request.num_computed_tokens == 0:
# v1/core/sched/scheduler.py:710-712     ... = self.kv_cache_manager.get_computed_blocks(request)   ← 여기서 record()
# v1/core/sched/scheduler.py:874   new_blocks = self.kv_cache_manager.allocate_slots(...)
# v1/core/sched/scheduler.py:888-895  if new_blocks is None: ... break     ← pop 안 하고 이탈
# v1/core/sched/scheduler.py:917   request = request_queue.pop_request()   ← 승인 성공해야만 큐에서 제거
# v1/core/sched/scheduler.py:1141-43  num_computed_tokens는 '스케줄된' 요청만 전진
```
→ KV 블록이 없어 승인 실패하면 요청은 **큐 head에 남고**, `num_computed_tokens`는 **0에 머문다** → **다음 step에 또 record()**. 즉 **`queries` 팽창 배수 ≈ 요청이 waiting 큐 head에서 재검사된 step 수**.

**증거 (실측)** — `figures/vllm_queries_inflation.png`. 예측대로 **경합에 비례해 팽창**한다:

| C | tr 팽창(q/prompt_tok) | tr hit | **default 팽창** | **default hit** |
|---|---|---|---|---|
| 4 | 1.89 | 0.725 | 3.81 | 0.649 |
| 8 | 2.13 | 0.786 | **18.75** | 0.214 |
| 16 | 2.05 | 0.797 | **29.56** | 0.037 |
| 32 | 1.96 | 0.751 | **30.05** | 0.030 |

→ tr은 ~2로 **평탄**(프록시가 미리 막아서 vLLM 큐에 안 쌓임), default는 C와 함께 **30배까지 팽창**. 보고 hit rate가 팽창과 **정확히 역상관**한다.

**판정 — "우리가 미스율만 쓰는 게 옳은가?"**
- ✅ **`prompt_tokens_total` 폐기는 옳다** (코드로 확증: 논리적 총량, 캐시 무관).
- ✅ **절대 미스량(queries−hits) 불신도 옳다** — 단 이유는 "granularity"가 아니라 **재검사 중복 계수**다. **DEEP_ANALYSIS §B-1의 설명을 이 문장으로 교체할 것.**
- ⚠️ **그러나 "미스율(1−hit)이 robust하다"는 부분적으로 틀렸다.** 미스율도 **같은 오염을 공유**한다. 재검사가 많은 요청이 집계에서 **가중치 N배**를 받기 때문이다. 방향(tr≫default)은 견고하나, **"default는 프롬프트의 96.3%를 재프리필한다"고 읽으면 안 된다.**
- ✅ **대안이 존재한다(우리가 놓쳤다)**: `vllm:prompt_tokens_by_source{source="local_compute"}` = **실제 계산된 프리필 토큰**. 불변식 `computed + local_cache_hit + external_kv_transfer = total`(`stats.py:287-289`). 이건 실제 prefill 출력에서만 누적돼 **재검사 오염이 없다**. → §7 GPU 제안 1.

### 1-3. preemption — 실측 ≈0이 코드적으로 말이 되는가

**발동 조건**: RUNNING 요청에 블록 할당 실패 시에만, `self.running.pop()`(가장 최근 요청)을 RECOMPUTE preempt (`scheduler.py:524-568`). 카운터는 `_preempt_request`에서 `request.num_preemptions += 1`(`scheduler.py:1123`), 상태는 `RequestStatus.PREEMPTED`(`:1119`).

**왜 거의 안 터지나**: preemption은 **이미 RUNNING인 요청이 decode 중 블록을 더 못 얻을 때** 발생한다. 그런데 우리 워크로드는 **출력이 mean 44.8~55 토큰으로 극히 짧다** → decode 중 추가로 필요한 블록이 `⌈55/16⌉ ≈ 4`개뿐. 반면 신규 프리필은 18.7k tok = **1,168 블록**을 요구한다. → **경합은 waiting 큐 승인 단계에서 해소되고**(승인 거부 = 위 §1-2의 재검사), RUNNING까지 간 요청은 거의 안 밀린다.

✅ **실측 preemption≈0은 코드와 정합.** 그리고 **"KV 부족의 실제 표출 형태는 preemption이 아니라 waiting 큐 정체"**임이 확정된다 — 이것이 §2의 핵심 재료다.

또한 `scheduler.py:626`: preemption이 한 번이라도 나면 **그 step은 waiting 승인을 통째로 건너뛴다** → preemption은 드물지만 터지면 admission을 얼어붙게 한다. [추정: 우리 실측에선 빈도가 낮아 무시 가능]

### 1-4. CUDA graph / batch bucket — "batch 1이든 4든 비슷하다"는 직관의 근거

**기동 로그 실측**(`scratch/vllm_phaseD_8002.log`):
- `cudagraph_capture_sizes = [1, 2, 4, 8, 16, 24, 32, 40, ..., 512]` (**51개**), `cudagraph_mode = FULL_AND_PIECEWISE`, 실제 캡처 PIECEWISE 51 / FULL 35.

**판정**: 버킷이 **1, 2, 4, 8로 촘촘하다** → batch 1과 batch 4는 **서로 다른 그래프**를 쓴다. **따라서 "batch 1이든 4든 비슷하다"는 CUDA graph 패딩으로는 설명되지 않는다.** (batch 6→8 같은 패딩만 존재.)

⚠️ 다만 **직관 자체는 다른 이유로 옳을 수 있다** — decode가 memory-bandwidth-bound라 batch 1~8의 step latency가 비슷하다는 것은 **별개의 물리 주장**이며 마이크로벤치가 필요하다. **그러나 §2에서 보듯 이 질문은 우리 워크로드에선 무의미해졌다**: 실제 배치가 **1.1~1.5**를 벗어나지 않으므로 batch 커브의 평탄 구간 여부가 결과를 바꾸지 못한다.

### 1-5. ★ TP2 비교에 숨은 교란변수 (신규 발견 — 중요)

`engine/arg_utils.py:2404-2413`은 **device memory 70GiB를 기준으로 기본값을 바꾼다**:

| HW | device mem | max_num_batched_tokens | max_num_seqs |
|---|---|---|---|
| **4090** (expC/D) | 24GB < 70GiB | **2048** | **256** |
| **Pro6000** (TP2) | 96GB ≥ 70GiB | **8192** | **1024** |

→ **TP2 실험은 "KV 풀 ×10.41" 하나만 바뀐 게 아니다. 배치 토큰 예산도 ×4로 함께 바뀐다.** `plans/2026-07-15`의 "한 번에 한 변수만" 원칙이 **의도치 않게 깨져 있다**. k_fit-flip이 관측되면 그 원인이 (i) C_total 확대인지 (ii) batched_tokens 확대인지 **현재 설계로는 분리 불가**.
→ **권고**: TP2 스윕에 `--max-num-batched-tokens 2048 --max-num-seqs 256`을 명시한 **대조군 1점**을 추가하면 분리된다. (nutella1 작업이므로 이 보고서에서는 제안만.)

---

## 2. Phase 2 — R<1에서 왜 default가 더 좋은가

### 2-1. H2 (배치 무료점심) — ❌ **반증됨**

**가설**: decode는 memory-bandwidth-bound라 batch 1~8의 step latency가 비슷하다 → default는 resident 6.15로 tr(1.6)의 **4배 일**을 같은 시간에 한다.

**증거**: `figures/vllm_batch_refutes_H2.png`. **실제 GPU 배치(mean nrr | nrr>0)는 전 구간 1.13~1.45.** default C=32조차 1.44. tr 1.19 대비 **+21%**에 불과하며 **4배가 아니다**.

**왜 k_fit=6.15인데 배치가 1.45인가** — k_fit의 정체를 분해하면:

| run | k_fit | mean REASONING(프록시) | mean ACTING(프록시) | **mean nrr(vLLM)** | **REASONING−nrr** |
|---|---|---|---|---|---|
| tr C=16 | 1.60 | 0.49 | 1.11 | 0.38 | **0.11** |
| default C=16 | 6.15 | 4.56 | 1.59 | 1.24 | **3.32** |
| default C=32 | 10.50 | 8.81 | 1.68 | 1.29 | **7.52** |

→ **k_fit은 "GPU에 올라간 수"가 아니다.** 대부분이 (i) ACTING(=tool 실행 중, off-GPU)이거나 (ii) **REASONING이라 표시되지만 실제로는 vLLM 내부 큐에서 대기 중**이다.

**결론: H2 기각.** default는 "recompute를 감수하고 batching을 산 것"이 **아니다**. 배치는 애초에 안 커졌다.

### 2-2. H4 (tr 프록시 오버헤드) — ⚠️ **부분 반증 + 중요한 반전**

**반전**: "default는 pause_s=0.0"은 **default가 줄을 안 선다는 뜻이 아니다.** 위 표의 `REASONING − nrr` = **default C=16에서 3.32개, C=32에서 7.52개**의 프로그램이 **프록시는 '추론 중'이라 믿지만 vLLM은 실행하지 않고 있는** 상태다. 이들은 vLLM waiting 큐에 있다.

**독립 증거 2종이 같은 결론**:
1. `REASONING − nrr` 갭 (3.32 / 7.52) — 프록시-vLLM 상태 대조
2. **queries 팽창 배수 30×** (§1-2) — vLLM 내부 카운터
두 지표는 **완전히 다른 경로**로 측정됐는데 같은 것(=vLLM 큐 정체)을 가리킨다.

**따라서 정정된 서술**:
> **tr과 default는 "줄을 서느냐"가 아니라 "어디서 줄을 서느냐"가 다르다.**
> tr = **프록시 큐**(pause 18.5s/step, profiler에 보임) / default = **vLLM waiting 큐**(profiler에 안 보임).

**H4의 원래 질문**("pause 없는 저부하 tr이 default보다 느리면 원인은 pause가 아니다"):
| C | tr thr | default thr | tr−def |
|---|---|---|---|
| 4 | 0.082 | 0.092 | −11% |
| 8 | 0.087 | 0.116 | −25% |
| 16 | 0.068 | 0.098 | −31% |
| 32 | 0.068 | 0.097 | −30% |

⚠️ C=4에서도 tr이 11% 느리다. 그런데 C=4에서 tr의 pause는 이미 존재한다(tr은 전 C에서 k_fit≈1.6으로 눌려 있음 — `_pause_until_safe`가 C=4부터 작동). **pause가 완전히 0인 tr 점이 expC 데이터에 없다** → **H4는 기존 데이터로 완전 판정 불가**. [한계]
다만 §2-3의 수치가 pause만으로 격차를 설명하므로, **프록시 고정 오버헤드가 주원인일 가능성은 낮다** [추정].

### 2-3. H1 (여유시간/기회비용) — ✅ **지지됨. 요구한 수치 문장 그대로:**

캐시 미스 1회의 한계비용을 **c=1 duty 프로파일에서 실측**했다(`figures/vllm_prefill_curve.png`):

| 구분 | 적합 | 해석 |
|---|---|---|
| **cold** (step 1, 캐시 없음, n=25) | `TTFT = 1.696e-4 × ptok − 0.450`, **r²=0.981** | **프리필은 프롬프트 길이에 선형 = compute-bound.** 한계율 **5,896 tok/s** |
| **warm** (step>1, prefix 히트, n=62) | 평균 **0.462 s**, r²=0.047 (**평탄**) | 히트 시 신규 토큰만 계산 → 길이와 무관 |

mean 프롬프트 18,684 tok 기준:
- 완전 미스 프리필 = `1.696e-4 × 18684 − 0.450` = **2.72 s**
- 히트 시 = **0.46 s**
- → **캐시 미스 1회의 한계비용 Δ ≈ 2.26 s/turn**

> ### **default가 내는 벌금 ≈ 2.3 초/step, tr이 내는 벌금 ≈ 18.5 초/step (실측 mean pause_s=18.47, n=4,301). → 8.2배 차이. X ≪ 18.5 → H1 지지, default 승.**

(tool_call_s는 tr 5.99 / default 6.08로 동일 — 워크로드 고유값이 양쪽 같음을 재확인.)

**H1의 인과 서술**: R<1이면 GPU에 bubble이 있다 → 재프리필 2.26s는 **어차피 놀던 시간에 지불**되므로 throughput 손해가 거의 없다. 반면 pause 18.5s는 **병목도 아닌 GPU 앞에서 실제 일을 막는** 순손실이다. **캐시 히트의 가치 = 절약된 prefill 시간 × P(GPU가 병목)** 이고, R<1이면 P(병목)≈0이므로 **hit=0.03이어도 거의 공짜다.**

### 2-4. H3 (prefill이 사실 싸다) — ✅ **지지 (부분)**

- **지지**: warm prefill 0.46s / cold 2.72s 모두 **tool 6.0s보다 작다**. duty d=0.196의 검산 — `(prefill 0.889 + decode 0.856)/(0.889+0.856+7.164) = 0.196` ✅ expC 값과 **정확히 일치**.
- **지지**: default는 hit이 0.649→0.030으로 **21배 붕괴**하는데 throughput은 0.092→0.097로 **평탄**(오히려 소폭 상승). → "hit 붕괴가 throughput을 안 죽인다"는 H3/H1 예측 그대로.
- ⚠️ **한계**: hit vs TTFT 상관을 분리하려면 부하 하 TTFT가 필요한데, **스윕 런의 `prefill_s`/`decode_s`가 0으로 미기록**이다(원인 규명: §6-1). → **H3의 "TTFT↑이지 throughput↓ 아니다" 부분은 미검증**. §7 GPU 제안 2.

### 2-5. ★ R≥1에서 왜 뒤집히는가 — SWE·TP2로 확인

**서술 가설**: "GPU가 병목이 되면 재프리필 FLOP이 다른 프로그램의 decode 슬롯을 직접 훔치고, 재프리필이 KV를 밀어내 다음 미스를 부르는 양의 되먹임이 걸린다."

**부분 성립. 두 갈래로 나눠 판정한다.**

✅ **성립하는 부분 — "기회비용이 실비용으로 바뀐다"**:
R≥1이면 `P(GPU가 병목) → 1`이므로 §2-3의 곱셈 `히트의 가치 = 절약 시간 × P(병목)`에서 P가 0→1로 간다. **동일한 2.26s/turn이 R<1에선 공짜, R≥1에선 순손실**이 된다. 이 하나로 두 레짐이 **같은 식**으로 설명된다:

| 워크로드 | HW | d | k_fit | R | P(병목) | 미스 벌금 2.26s의 성격 | 실측 |
|---|---|---|---|---|---|---|---|
| TraceLab | 2×4090 | 0.196 | 6.15(def) | 1.20 | 중간 | 대부분 bubble에 흡수 | **default 승 +44%** |
| **SWE** | 2×4090 | **0.995** | 2~4 | **≫1** | ≈1 | **순손실** | **tr 승 +78~84%** |
| **TP2 TraceLab** | Pro6000 | 0.289 | ~25(중부하) | **≫1** | ≈1 | **순손실** | **default 붕괴**(C=32: hit 0.81→0.29, thr 3.4배↓) |

TP2 예비 실측(`logs/2026-07-16` §P1-1)이 **이 예측과 정합**: fit≈25를 넘는 C=32에서 default가 붕괴한다.

⚠️ **"decode 슬롯을 직접 훔친다"는 부분은 코드상 부정확**:
RUNNING이 먼저 스케줄되고(`scheduler.py:432`) budget 2048 ≫ max_num_seqs 256이므로, **decode 요청은 프리필에 의해 admission에서 밀려나지 않는다.** 실제 기전은 "슬롯 강탈"이 아니라 **(i) 같은 iteration에 2048토큰 청크가 얹혀 iteration이 길어짐**(decode 토큰이 프리필 iteration에 편승) + **(ii) KV 블록 고갈로 waiting 큐 정체**다. → **발표 문구를 "decode 슬롯을 훔친다"에서 "KV 블록을 고갈시켜 waiting 큐를 정체시키고 iteration을 무겁게 한다"로 정정 권고.**

⚠️ **"양의 되먹임"은 미검증**: 재프리필→KV 압박→추가 미스의 **자기강화 루프**를 직접 보여주는 시계열 증거는 아직 없다. [추정 — 현재 데이터로 확인 불가]

---

## 3. Phase 3 — throughput 식의 인수분해

### 3-1. 실측으로 채운 항

```
step_time ≈ pause + prefill + decode + tool
```
| 항 | tr C=16 | default C=16 | 출처 |
|---|---|---|---|
| **pause**(프록시 큐) | **18.47 s** | **0.00 s** | `prof_*/step_profiles.csv` (n≈4.3k) |
| **vLLM 큐 대기**(숨은 pause) | ~0.11 prog | **3.32 prog** | `REASONING − nrr` (§2-2) |
| **prefill** | ~0.46 s (warm) | ~2.72 s (cold) | c=1 적합(§2-3), **부하 하 미측정** ⚠️ |
| **decode** | ~0.86 s | ~0.86 s | c=1 프로파일 (44.8 tok @ ~52 tok/s) |
| **tool** | 5.99 s | 6.08 s | 실측, 워크로드 고유 |

### 3-2. 지배 관계 표

| 식의 항 | 지배하는 워크로드 특성 | 4090 TraceLab | TP2 TraceLab | SWE |
|---|---|---|---|---|
| prefill | **입력 길이 × (1−hit)**, compute-bound (5,896 tok/s @4090) | 18.7k tok → **2.72s cold** | 18.7k, 32B·TP2라 더 느림 | 7.7k → **~0.86s** |
| decode | **출력 길이** × ~19ms/tok | 55 tok → 0.86s | 55 tok | **834 tok → ~16s (지배)** |
| tool | 워크로드 고유 | **6.0s (지배)** | 6.87s | **0.23s (무시 가능)** |
| **d = (pf+dc)/(pf+dc+tool)** | 위 셋의 비 | **0.196** | 0.289 | **0.995** |
| k_fit | **C_total / 프로그램 KV**(+ 정책) | fit~2, k_fit 1.6(tr)/6.15(def) | fit~25 | fit 2~4 |
| **R = k_fit·d** | | **0.31(tr) / 1.20(def)** | **≫1** | **≫1** |

**핵심 대비**: SWE가 tr 승인 이유는 **decode(834 tok)가 tool(0.23s)을 압도**해 d≈1이 되기 때문이다. TraceLab은 **tool 6.0s가 reasoning 1.75s를 압도**해 d=0.196이 된다. → **d는 "출력 길이 vs tool 시간"의 비율이 결정한다.**

### 3-3. 상충 임계식 — ⚠️ **유도했으나 실측과 안 맞는다 (정직 보고)**

`k_fit↑ → (이득) U↑ ; (손해) hit↓ → prefill↑`. GPU-work 관점 모델:

```
thr ∝ U / W,   W = 프로그램당 GPU 작업량 = prompt·(1−hit)/rate_prefill + out_tok/rate_decode
```
default가 이기는 조건: `U_def/U_tr > W_def/W_tr`.

**실측 대입 (C=16)**:
- `U_def/U_tr = 0.855/0.317 = 2.70`
- `W_tr = 18684×(1−0.797)/5896 + 0.86 = 0.64+0.86 = 1.50 s`
- `W_def = 18684×(1−0.037)/5896 + 0.86 = 3.05+0.86 = 3.91 s` → `W_def/W_tr = 2.61`
- → 예측 thr 비 = 2.70/2.61 = **1.03**. **실측 = 0.098/0.068 = 1.44.** ❌ **안 맞는다.**

**역산**: 실측 1.44를 맞추려면 `W_def/W_tr = 1.875` → `W_def = 2.81s` → prefill 1.95s → **hit_default ≈ 0.38**이어야 한다.

**해석 [추정]**: 이 불일치는 **§1-2의 hit 오염과 방향이 일치한다** — 보고된 hit 0.037이 참값(≈0.38?)보다 낮게 편향됐다면 모델이 맞아 들어간다.

> ## ✅ **해소됨 (2026-07-17, §7-B-5 참조) — 추정이 실측으로 확정됐다.**
> `local_compute` 카운터로 참 hit를 재서 **같은 식에 넣자 오차 28.2% → 1.4%로 닫혔다**:
>
> | 쓰는 hit | W_def/W_tr | 예측 thr 비 | 실측 1.441 대비 |
> |---|---|---|---|
> | 오염된 보고 hit (0.797 / 0.037) | 2.606 | 1.035 | **28.2% 오차** ❌ |
> | **참 hit (0.6983 / 0.1844)** | **1.899** | **1.421** | **1.4% 오차** ✅ |
>
> → **위 역산(hit_default ≈ 0.38)은 방향은 맞았으나 값은 틀렸다**(참값 0.1844). 역산이 W_tr에 오염된 tr hit(0.797)을
> 썼기 때문이다. 참 tr hit(0.6983)을 쓰면 필요한 hit_default = 0.197 → **실측 0.1844와 7% 이내로 일치**.
> → **R 모델은 U를 예측하고(§1-1), U와 참 재프리필 비용 두 항이 throughput 비를 1.4%로 예측한다. 식이 닫혔다.**

**빠진 것 지목**: ~~(i) 오염 없는 재프리필량~~ ✅해소, ~~(ii) 부하 하 prefill_s/decode_s~~ ✅해소(§7-B-5),
(iii) iteration당 실제 토큰 구성(프리필 청크 vs decode) — **미해결**, (iv) **동일 런에서 U와 참 hit 동시 측정** — **미해결**(§7-B-5 한계).

---

## 4. Phase 4 — U 측정 방법 자체를 의심하라

### 4-1. ★ 지시서의 전제가 사실과 다르다 (먼저 정정)

> 지시서: "우리 U는 1 − idle(1초 샘플러 + **nvidia-smi util**)이다. nvidia-smi utilization은 '커널이 하나라도 돌았는가'라 batch 1과 batch 32가 똑같이 100%로 보일 수 있다."

**실제 코드**(`scripts/plot_expC_yunuikang.py:47-62`):
```python
b0res = ...("b0_reasoning"); u0 = mean(b0res[sl] > 0)     # ← U는 이것
"U_meas": (u0+u1)/2,  "gpu_util": mean(gpu2_util), ...    # ← nvidia-smi는 따로 기록만
```
→ **U_meas는 nvidia-smi가 아니다.** **프록시가 보고하는 REASONING 프로그램 수 > 0인 1초 틱의 비율**이다. nvidia-smi util은 `gpu_util` 칼럼에 **기록만 되고 U에는 안 쓰였다**.

### 4-2. U가 정확히 무엇을 재는가 (한 문단 확정)

> **expC의 U는 "GPU 점유율"이 아니라 "프록시 관점에서 최소 한 개의 프로그램이 추론 요청을 파견한 상태로 있었던 시간의 비율"이다.** 이는 SM occupancy도, 커널 점유율도 아니며, **vLLM 내부 큐 대기 시간까지 '바쁨'으로 포함**한다(§2-2에서 default C=16 기준 3.32 프로그램이 이 착시에 해당). 1초 샘플링이므로 1초보다 짧은 bubble은 보이지 않는다.

### 4-3. 그럼에도 — **삼각측량 결과 U는 견고하다** ✅

`figures/vllm_U_triangulation.png`. **세 독립 측정을 전부 계산해 비교**했다:

| run | U(proxy REASONING>0) | U(vLLM nrr>0) | nvidia-smi util/100 |
|---|---|---|---|
| tr C=16 | 0.375 | 0.317 | **0.349** |
| tr C=32 | 0.356 | 0.295 | 0.335 |
| default C=16 | 0.873 | 0.855 | **0.861** |
| default C=32 | 0.911 | 0.893 | 0.903 |
| cross ts=2.0 | 0.224 | 0.186 | 0.214 |
| cross ts=0.125 | 0.706 | 0.615 | 0.669 |

**상관: nvidia-smi vs nrr r = 0.999, proxy vs nrr r = 0.999.** 평균 절대차 ≤ 0.06.

**판정**:
- ✅ **"batch 1과 batch 32가 똑같이 100%로 보인다"는 우려는 이 데이터에선 발생하지 않았다.** util이 **100%에 붙어있지 않기 때문**(0.21~0.90 전 구간 분포). 그 우려는 util이 포화했을 때만 문제인데, 우리 R<1 레짐은 정의상 **비포화**다.
- ✅ **세 측정이 일치하므로 "U=0.87 vs 0.37" 해석은 흔들리지 않는다.** R 모델은 **유효**.
- ⚠️ 단 **U는 GPU 활용률이 아니라 "GPU가 일감을 갖고 있던 시간 비율"(busy-time fraction)로 정의를 바꿔 부르는 게 정확하다.** SM 점유율은 여전히 미측정 — 그러나 §1-1에서 **실제 배치가 1.1~1.5로 고정**임이 밝혀졌으므로, SM 점유율은 tr·default가 **거의 같을 것**이고 [추정] 따라서 결론에 영향이 없다.

### 4-4. 실제 타임라인 — 내 그림은 맞았나?

`figures/vllm_timeline_tr_vs_default.png`

| 내가 그려온 그림 | 실제 | 판정 |
|---|---|---|
| TraceLab tr = "구멍 뚫림" U≈0.38 | nrr이 0과 1~2 사이를 촘촘히 오감, U(nrr>0)=0.32 | ✅ **맞음** |
| default = "빽빽함" U≈0.87 | nrr이 대부분 2~4(2백엔드 합), U=0.86 | ✅ **맞음** |
| 빽빽함 = "배치가 큼" | **틀림.** 배치는 1.45. 빽빽한 건 **시간축** | ❌ **틀림** (§1-1) |
| default는 안 기다림 | **틀림.** REASONING 10~13 vs nrr 3~4 = **큐 대기** | ❌ **틀림** (§2-2) |

→ **그림의 "GPU가 얼마나 차 있나"는 맞았고, "왜 차 있나"가 틀렸다.**

---

## 5. Phase 5 — related work는 정말 duty cycle을 무시하는가

> **✅ 34p 갱신본 확인 완료 (2026-07-17 14:32 수령, `/home/yunuikang/yunuikang_work/ThunderAgent.pdf`, 34p·102,701자 정상 추출).**
> 아래는 **28p·34p 양쪽 원문 대조** 결과다. 모든 페이지/식/표 번호는 해당 페이지 재추출로 이중 확인했다.

### 5-00. ★★ 최우선 — `2026-07-02_PAPER_COMPARISON` §0-1이 통째로 뒤집혔다 (교수님이 옳았다)

우리 문서 `logs/2026-07-02_PAPER_COMPARISON_yunuikang.md` §0-1은 **"지시서에서 언급한 인용 위치가 이 PDF와 불일치한다"**며 교수님의 참조를 **정정**했다. 그런데 그 정정은 **28p 구본을 근거로 한 것이었고, 교수님은 34p 갱신본을 보고 계셨다.** 실측 대조:

| 우리 문서(§0-1)가 "없다"고 한 것 | 28p | **34p 실제** | 판정 |
|---|---|---|---|
| **§A.5** (working set/heterogeneous) | 없음(A.1~A.3뿐) | ✅ **§A.5 "Portability of ThunderAgent across Hardware Generations" (p.24)**. 본문에 *"the **working set fits** comfortably in HBM and thrashing is rare"* 문구 **그대로 존재** | **교수님 옳음** |
| **Table 3 = H100 vs A100 비교** | Table 3 = Program state 정의표 | ✅ **Table 3 = "Compute-to-bandwidth ratio across hardware tiers" (p.24)** — H100 989TFLOPs/3350GB/s = **295.2**, A100 312/2039 = **153.0** | **교수님 옳음** |
| **Figure 10 = compute-to-bandwidth** | Fig 10 = E2E latency | ✅ **Figure 10 = "ThunderAgent on A100 GPUs" (p.25)** | **교수님 옳음** |
| **"A100"·"compute-to-bandwidth" 문구가 논문에 없음** | A100 **0회**, compute-to-bandwidth **0회** (실측) | ✅ **둘 다 존재** (§A.5, Table 3) | **교수님 옳음** |
| **"느린 GPU일수록 스래싱 빨라 tr 이점↑" 실험이 없음** | 없음 | ✅ **있다.** 8×A100 실험: *"At low concurrency (24), ThunderAgent matches vLLM within noise ... because the working set fits comfortably in HBM and thrashing is rare. As concurrency rises to 48 and 72, the picture flips: ThunderAgent widens the gap to **1.71–2.08×** on mini-SWEAgent and **1.16–1.62×** on OpenHands, while vLLM's throughput **decreases** from concurrency 48 onward as it begins to thrash."* (p.24) | **교수님 옳음** |

> **→ §0-1의 "출처 정정" 표는 5행 전부 무효다. 우리가 구본을 읽고 교수님을 정정했던 것이며, 실제로는 교수님의 원래 참조가 전부 정확했다. 미팅 전에 반드시 철회·사과 정정할 것.** (PAPER_COMPARISON 문서 최상단에 "이 문서는 28p 구본 기준"임을 명시하고 §0-1을 삭제/교체.)

**우리 heterogeneous gap에 미치는 영향 (정직하게)**:
- ❌ **약화된 것**: "논문은 GPU 세대를 바꿔 비교한 실험이 없다"는 **더 이상 못 쓴다**(§A.5가 정확히 그것). "compute-to-bandwidth 비율"도 이제 **논문 안에 있다**(Table 3) → 우리 독창성 아님.
- ✅ **살아남는 것**: §A.5도 **8×A100 단독 / 8×H100 단독**으로, **한 클러스터에 서로 다른 GPU를 섞은 실험은 여전히 없다.** node-agnostic recompute 가정(§4.3.2)도 그대로. → **우리 gap은 "다른 하드웨어"가 아니라 "한 클러스터 안의 이종 혼합"으로 좁혀서 서술해야 한다.**
- ⚠️ 또한 §A.5의 A100 결과는 **저부하에서 tr≈vLLM, 고부하에서 tr 승**인데, 그 설명이 우리 R 모델이 아니라 **working set/thrashing**이다. 우리의 "저부하 등가 구간은 우리 데이터의 기여"(§0-1 항목 2 해석)도 **재검토 필요**.

### 5-0. ★ 우리 문서의 사실 오류 1건 (34p에서도 동일하게 확인됨)

`logs/2026-07-06_MECHANISM_REFERENCE_yunuikang.md` §1-1 표는 **`Cost_unused` = "GPU에 올려뒀지만 tool 실행 중이라 놀고 있는 KV 점유"**로 적고 있다. **논문과 다르다.**

- 논문 p.6 §4.2 (**28p·34p 양쪽 동일**): *"**Cost_unused** reflects **memory imbalance across data parallel (DP) inference backend replicas** (Section 3.2); and **Cost_caching** accumulates while **holding memory during external tool execution** (Section 3.3)."*

→ **tool 시간에 과금하는 항은 `Cost_unused`가 아니라 `Cost_caching`이다.** MECHANISM_REFERENCE의 표를 수정해야 한다(리뷰어가 즉시 잡을 종류의 오류).

### 5-0b. ★ 인용 위치 정정표 (28p → 34p) — 우리 문서 전체에 적용할 것

**Appendix E와 F가 서로 뒤바뀌었다**(28p: E=이론분석·F=E2E latency → 34p: **E=E2E latency·F=이론분석**). 우리가 쓰던 "Appendix E.2"는 **34p에서 死링크**다.

| 우리가 쓰던 인용 | **34p 정확한 위치** | 조치 |
|---|---|---|
| §4.2 비용모델 p.6 / §4.3.1 **Eq.(6)** p.7 / **Eq.(7)** p.7 | **동일 — 페이지·식 번호 불변** | ✅ 유지 |
| **Appendix E.2** 경계조건(t=0/∞) p.24 | **Appendix F.2 (Hypothesis F.2), p.30, Eq.(12)** | ❌ **E→F 전면 교체** |
| Appendix E.1 (감쇠함수 정리) | **Theorem F.1, p.30** | ⚠️ |
| Appendix E.3 | **F.3, p.31** | ⚠️ |
| Appendix C tool buckets = **Table 5** p.22 | **Table 6, p.27** (컬럼: Tool bucket / Role / Primary variability source, 7행) | ⚠️ 팀 예상 적중 |
| Appendix D p.23 | **§D, p.29** (문구 동일) | ⚠️ 페이지만 |
| Table 3(Program state) / Table 4(BackendState) p.21 | **Table 4 (p.26) / Table 5 (p.27)** | ⚠️ 각 +1 |
| Figure 9 (tool time 분포) / Figure 10 (E2E latency) | **Figure 12 (p.28) / Figure 13 (p.29)** | ⚠️ |
| 참고문헌 번호 | **전부 +1 시프트**(35→36개; SWEBench [9]→**[10]**, HLE [15]→**[16]**, Continuum→**[12]**) | ⚠️ 전수 재확인 |

**34p 신규 내용(28p에 없던 것)**: §A.2(기존 KV 최적화 대조), **§A.4(KV offloading 호환)**, **§A.5(하드웨어 세대 이식성 — A100, Table 3)**, §A.6(오픈소스 채택: SkyRL 등), **Appendix G 전체(추가 어블레이션)** — G.2 decay 함수 형태(Figure 15), global vs local 큐(Figure 14, 4노드 1.28×), eviction 정책(Figure 16), **Table 7 컴포넌트별 기여도**(vLLM 375 → +local 602(1.61×) → +global queue 672(1.12×) steps/min). **8노드/64×H100 스케일업(Figure 8)**, SGLang HiCache 대조(Figure 9).
**§5.1 주 실험설정은 불변**(GLM-4.6/Qwen3-235B FP8 TP8 on 8×H100; ToolOrchestra=Qwen3-8B on RTX5090 1장; Δt=5; f(t)=2^−t). A100은 본문이 아니라 **§A.5 부록에만** 등장.

### 5-1. 산출 표

| 논문 | duty/tool-idle을 보는가 | 어떤 형태 | 우리와 다른 점 | 인용 위치 |
|---|---|---|---|---|
| **ThunderAgent**(28p) | **본다** (t_q가 1급 변수) | **최적화** — 단 tool 시간은 *예측 불가*로 가정(Hyp E.1), 경과시간 감쇠로 대응 | duty **비율** 개념 없음, "duty" 0회, U 예측 모델 없음 | p.6 Eq(3); **p.7 Eq(7)**; p.24 Hyp E.1/E.2; p.22 App C |
| **Continuum**(2511.02230) | **본다** (tool 시간 명시 예측) | **예측+최적화** — 경험적 CDF → TTL 기반 KV pinning | 예측을 **KV 보존 결정에만** 사용. "idle"/"duty cycle"/"GPU utilization" **각 0회** | §4.1, §4.2 Eq(1)(2), §5.2 |
| **InferCept**(ICML'24) | **본다** (T_INT) | **예측+최적화** — Eq(2)에 직접 포함, §4.4가 지속시간 추정 | per-request **메모리 waste** 최소화용, 활용률 예측 아님 | §3.2 **Eq(2)**, §4.3 Eq(5), §4.4, Table 1 |
| **Parrot**(OSDI'24) | **안 본다** | **무시**(명시적 범위 밖) | LLM↔LLM DAG만. tool은 client-side | §4.2, **§6** |
| **Autellix**(2502.13965) | **인지하나 배제** | **무시(명시적)** | program-level이나 누적 *compute* 시간만 | **§2.2** |
| **Preble**(2407.00023) | 안 본다 | 무시 | prefix 공유/부하분산 | Abstract, §3.1 |
| **vAttention**(2405.04437) | 안 본다 | **무관**(CUDA VMM 메모리 계층) | 직교 | Abstract |
| **SGLang/RadixAttention** | 안 본다 | 무시(LRU recency만) | tool 중 프로그램은 큐에 없음 | Abstract, §3 |

### 5-2. 결정적 인용 3개 (우리 주장을 깨는 것)

1. **InferCept §3.2 Eq(2)** — 가장 강한 반례:
   > *"The preserve waste for request i when interception j occurs is **the duration of that interception, T^j_INT, multiplied by the amount of GPU memory** held by the request's context. WastePreserve^j_i = T^j_INT × C_i × M"*
   그리고 §4.4 제목이 **"Interception Duration Estimation"**: *"T̂_INT = t_now − t_call... achieves **93% of the performance compared with using an oracle**"*

2. **Continuum §4.1** — tool 시간 예측 그 자체:
   > *"Since we cannot fully predict the duration of the next tool call, we estimate 𝒫(τ,f) using the **empirical CDF** derived from historical tool-call records S[f]."*

3. **ThunderAgent 자신 p.7 Eq(7)** — t_q가 용량 판정식에 직접:
   > `C_total < Σ_{p∈L,τ=R} c_p + Σ_{q∈L,τ=A} c_q × f(t_q)` — *"**t_q is the tool execution time of program q in the current step**. f(t) is a time-decay function designed to balance Cost_caching and Cost_recompute."*

   더 나아가 **Appendix E.2(p.24)가 d의 두 극한을 이미 논한다**:
   > *"**when the tool execution time is 0**, ... all acting programs reduce to reasoning programs, and therefore f(t)=1. Conversely, **if the tool execution time is infinite**, the agentic workflow collapses to single-turn generation, akin to standard chatbot serving..."*

### 5-3. 결론 — 기여 문장 재작성 (정직하게)

> ### ❌ **"아무도 duty cycle을 보지 않는다"는 거짓이다. 절대 쓰면 안 된다.**
> 반례 최소 3개(InferCept Eq.2, Continuum Eq.1-2, ThunderAgent Eq.7). 리뷰어가 InferCept Eq(2) 하나만 들어도 무너진다. 게다가 ThunderAgent Appendix E.2는 **d→1·d→0 극한을 이미 서술**한다.

**팀의 fallback**("duty를 스케줄링에 쓰는 연구는 있으나, GPU 활용률의 예측 변수로 쓰지 않는다")은 **대체로 방어 가능하나 두 곳을 조여야 한다**:
1. "스케줄링에 쓴다"가 너무 약하다. 선행연구는 tool 시간을 **per-call 절대 지속시간(초)**로 쓰고(T_INT, τ*, t_q), 우리는 **워크로드 수준 무차원 비율**로 쓴다. **이 축을 명시해야 한다.**
2. ThunderAgent **Appendix D(p.23)는 실제로 레짐 언어를 쓴다** — *"ThunderAgent adapts to these **regimes**"*. 다만 그 레짐은 **tool 시간의 variability(예측가능성)** 축이지 **duty 비율** 축이 아니다. **선제적으로 구분하지 않으면 잡힌다.**

**부재 검증(실측)**: 7개 시스템 전부 duty 비율 정의 **없음**. Continuum "idle"/"duty cycle"/"GPU utilization"/"regime" **각 0회**.

**★ 34p 갱신본 전수 스캔 결과 — 우리 기여 주장은 살아남는다 (실측)**:

| 검색어 | 34p 히트 |
|---|---|
| **`duty`** | **0** |
| `fraction`·`occupanc`·`dimensionless`·`predictor`·`workload ratio`·`reasoning time`·`MFU`·`active time`·`busy` | **각 0** |
| `utilization` | 6 (**6/6 전부 정성적**) |
| `regime` | 2 (**2/2 전부 정성적**) |

- `utilization` 6건 중 우리에게 **유리한 것**: **p.11** — *"determining the optimal parallel workflow number to maximize **utilization** with limited KV cache thrashing and caching cost is **infeasible** due to the stochastic nature of agent environments and tool execution durations."* → **저자들이 활용률 모델링을 '불가능'으로 규정하고 우회했다.** 우리가 R로 그걸 예측한다는 게 정확히 빈틈.
- 유일한 "GPU utilization"(p.11): *"it achieves higher throughput by ensuring **active GPU utilization**"* — **수식·정의·측정치 없는 순수 수사**.
- **Table 3의 "ratio"는 무관**: "Compute-to-bandwidth ratio"(H100 295.2 / A100 153.0 GFLOPS/GB)는 **하드웨어 스펙 비율**이지 워크로드 duty 비율이 아니다. 34p의 유일한 ratio 모델이 하드웨어 축이라는 점이 오히려 duty 축 부재를 방증한다.

**⚠️ 가장 근접한 반례(nearest miss) — 신설 §G.2 (p.32, Figure 15 p.33)**: 34p는 **"정책의 승패가 워크로드 성격에 따라 뒤집힌다"는 실증 어블레이션**을 처음 담았다 — *"three agentic pipelines with progressively less predictable tool latency: mini-SWE-Agent (short, regular tool calls), OSWorld (longer but largely periodic...), ScienceAgent (highly stochastic, heavy-tailed)"*, 그리고 *"On OSWorld, **exponential decay trails linear by about 6%** (1.14× vs. 1.21×)"*.
→ 그러나 이 축은 **tool 지연의 예측가능성/분산**이지 **duty 비율**이 아니고, 활용률을 **예측**하지도 duty를 **변수로 정의**하지도 않는다. → **우리 기여 주장은 34p에서도 깨지지 않는다.** 단 **"아무도 duty 레짐을 생각조차 안 했다"류 강한 표현은 철회**하고 아래처럼 좁힐 것.

어떤 논문도 `U≈min(R,1)` 류 **활용률 예측 모델을 갖지 않는다**(28p·34p 모두 실측 확인).

**권장 기여 서술문**:
> 선행 agentic serving 시스템들은 tool 실행 시간을 **개별 호출의 절대 지속시간**으로 취급하여 **KV 캐시 보존/축출이라는 국소적 메커니즘 결정**에 사용해 왔다(InferCept: `WastePreserve = T_INT×C×M` [§3.2 Eq.2]; Continuum: 경험적 CDF 기반 TTL pinning [§4.1–4.2]; ThunderAgent: 경과 acting 시간 감쇠 `f(t_q)` [Eq.7]). 그러나 이들 중 어느 것도 **duty cycle `d = t_reason/(t_reason+t_tool)`이라는 무차원 워크로드 특성을 정의하지 않으며**, 이를 **GPU 활용률의 예측 변수**로 사용하지 않는다. 그 결과 **R = k·d < 1 레짐 — 스케줄링 정책과 무관하게 GPU가 구조적으로 놀 수밖에 없는 영역 —** 이 존재한다는 사실 자체가 인식되지 않았고, **정책의 승패가 이 레짐에 의해 결정된다**는 점이 정량화되지 않았다. 본 논문은 duty를 스케줄링 **메커니즘의 입력**이 아니라 **시스템 거동의 예측 변수**로 승격시킨다.

⚠️ **Continuum 인용 주의**: ThunderAgent p.22는 Continuum을 *"static, threshold-based rule"*이라 하지만, **Continuum 원문 §4.1 Eq(1)은 cost-benefit 최적화**다. 우리는 **원문**을 근거로 삼아야 한다(baseline 특성화가 불공정할 소지).

---

## 6. 한계 (정직하게)

1. ~~**34p 갱신본 미확인 — 최대 구멍.**~~ → ✅ **해소(2026-07-17)**. 34p 전량 대조 완료(§5). 결과: **duty 0회 → 우리 기여 주장 유지**. 그러나 **부작용 2건 발견** — (i) `PAPER_COMPARISON §0-1`이 통째로 뒤집힘(§5-00, 교수님이 옳았음), (ii) Appendix E↔F 교환으로 우리 인용이 死링크(§5-0b). 남은 리스크: 34p보다 더 최신 버전이 또 있을 가능성 [추정].
2. ~~**`max_num_batched_tokens=2048`은 코드 유도이지 로그 실측이 아니다.**~~ → ✅ **해소(2026-07-17)**. `logger.info_once` 라인은 여전히 로그에 안 남지만(로그 레벨 문제로 추정), **실제 RTX4090에서 `EngineArgs.get_batch_defaults(world_size=1)`를 직접 실행**해 확정했다: `OPENAI_API_SERVER → batched_tokens 2048, max_num_seqs 256`, device 확인 `NVIDIA GeForce RTX 4090 / 24.0 GiB`. → **§1-5 TP2 교란 주장의 근거도 함께 확정**(Pro6000 96GB ≥ 70GiB → 8192/1024).
3. **hit 오염의 편향 방향 미확정.** 재검사가 집계 가중치를 왜곡한다는 것은 확정했으나, **참 hit이 얼마인지는 모른다**. §3-3의 역산(≈0.38)은 **모델 의존 추정**이며 실측이 아니다.
4. **H4 완전 판정 불가.** pause=0인 tr 점이 expC에 없다.
5. **양의 되먹임 미검증**(§2-5).
6. **SM occupancy 미측정.** 배치가 1.1~1.5로 고정이므로 결론에 영향 없을 것 [추정]이나 직접 증거는 없다.
7. **d의 부하 의존성**: d=0.196은 c=1 고유값(expC §5 한계 그대로 유효).
8. **expC 동시 실행 경합**(expC §1 CAVEAT) — throughput 절대값에 SWE 스윕 경합 영향. 본 재분석의 U·배치·팽창 결론은 **비율/구조 지표**라 상대적으로 강건 [추정].

### 6-1. 부수 규명 — `prefill_s`/`decode_s`가 왜 0인가
`prof_duty`(=`--stream`)는 `prefill_s`가 채워지고(mean 0.889), 스윕 런(`prof_tr_ts1.0` 등)은 **전부 0**이다. `ThunderAgent/profile/state.py:42,145`의 `first_token_time`은 `on_first_token` 콜백으로만 설정되고, 이 콜백은 `app.py:114`에서 **스트리밍 경로에만** 연결된다(`vllm_request_processor.py:158,174-177`). → **스윕 드라이버가 `--stream` 없이 돌아 TTFT가 측정되지 않았다.** 재측정 시 `--stream` 필수.

---

## 7. GPU가 필요한 마이크로벤치 계획 (승인 요청 — 아직 실행 안 함)

> mango1 4×4090 **전부 유휴**(0%, 프로세스 없음), tmux에 `tp2sweep`/`tp2serve`/`tp2proxy` **없음**(TP2는 nutella1). **그럼에도 게이트를 지켜 승인 전까지 GPU를 잡지 않았다.**

| # | 목적 | 방법 | GPU | 시간 | 이게 없으면 못 닫는 것 |
|---|---|---|---|---|---|
| **1 ★최우선** | **오염 없는 재프리필 실측** → §3-3의 열린 고리를 닫는다 | vLLM 1대 기동 후 `/metrics`에서 **`vllm:prompt_tokens_by_source{source="local_compute"}`** + `prompt_tokens_cached_total` 수집. expC C=16 tr/default **각 1런**(NPROG=32로 축소) | GPU 1장 | ~40분 | **참 hit·참 재프리필량.** §3-3 throughput 모델 성립 여부, §1-2 편향 방향 |
| **2** | **부하 하 prefill/decode 분해**(H3 완결) | 위 런에 **`--stream`** 추가(§6-1) → `prefill_s`/`decode_s` 복구. + `vllm:time_to_first_token_seconds` 히스토그램 | 위와 동일 런 | +0 | hit↔TTFT vs hit↔throughput 분리 |
| **3** | **런타임 config 확정**(§6-2) | 기동 로그에서 `max_num_batched_tokens`·`max_num_seqs` 확인 (`--log-level info`) | 위와 동일 | +0 | §1-5 TP2 교란 주장의 근거 확정 |
| **4** | decode batch 커브(H2 잔여) | batch 1·2·4·8·16·32 × decode step latency | GPU 1장 | ~20분 | **우선순위 낮음** — §2-1에서 실제 배치가 1.1~1.5로 확정돼 실익 적음 |
| **5** | SM occupancy(Phase 4 잔여) | nsys/torch profiler 30~60s | GPU 1장 | ~20분 | **우선순위 낮음** — §4-3 삼각측량으로 이미 방어됨 |

**제안**: **1+2+3을 한 런으로 묶어 GPU 1장 · 약 40분**이면 이번 분석의 **유일하게 열린 고리(§3-3)**가 닫힌다. 4·5는 실익이 낮아 **생략 권고**.
**추가(nutella1 소관)**: TP2에 `--max-num-batched-tokens 2048 --max-num-seqs 256` 대조군 1점(§1-5).

---

## 7-B. ★★ 마이크로벤치 실행 결과 (2026-07-17, GPU 승인 후 실행)

> 조건: mango1 **GPU2/GPU3 → 8002/8003**(expC와 동일, KV 각 **43,888 tok** 기동 로그 확인), 프록시 9011,
> `tracelab_fit32k.jsonl`, **C=16, NPROG=32**(expC의 64에서 축소), router assertion 통과.
> **`router.py`·드라이버 미수정** — `/metrics` 전후 스냅샷만 별도 스크립트(`scripts/microbench_recompute_yunuikang.py`)로 추가.

### 7-B-1. ✅ 제안 3 — 런타임 config 확정
실제 RTX4090에서 `EngineArgs.get_batch_defaults(world_size=1)` 직접 실행:
```
batched_tokens  OPENAI_API_SERVER -> 2048      max_num_seqs  OPENAI_API_SERVER -> 256
device: NVIDIA GeForce RTX 4090 | total mem 24.0 GiB
```
→ **§1-0 항목 2·3의 코드 유도가 실측 확정.** §1-5의 TP2 교란(Pro6000 96GB ≥ 70GiB → 8192/1024) 근거도 함께 확정.

### 7-B-2. ★ 제안 1 — 참 재프리필 실측: **불변식 성립, 그리고 우리 지표는 참값을 2.6배 과소평가**

`default` C=16 실측 (wall 226s, rc=0):

| 지표 | 값 |
|---|---|
| `prompt_tokens_total` | 2,439,537 |
| `prompt_tokens_cached` | 503,712 |
| **`prompt_tokens_by_source{local_compute}` = 참 재프리필** | **1,935,825** |
| **불변식 `compute + cached == total`** | **✅ True** (§1-2 코드 독해가 실측으로 확증) |
| **★ 참 hit rate = cached/total** | **0.2065** |
| **★ 참 recompute 비율** | **0.7935** |
| 보고 hit rate = hits/queries (우리가 써온 지표) | **0.0805** |
| queries 팽창 배수 | **23.0×** |
| `num_preemptions` | **0** (§1-3 코드 분석과 정합) |

> ### **결론: 보고된 hit rate가 참값을 2.57배 과소평가한다 (0.0805 vs 0.2065).**
> §1-2에서 "편향 방향은 코드만으로 확정 못 한다"고 남겨둔 것의 답 = **보고값 < 참값**.
> → **"default는 프롬프트의 96%를 재프리필한다"는 서술은 틀렸다. 실제로는 79%다.** (그래도 tr보다 훨씬 나쁘지만, 수치가 다르다.)
> ⚠️ 이 값은 **NPROG=32** 런이라 expC의 NPROG=64(보고 hit 0.037)와 직접 비교 불가 — **비교해야 하는 것은 같은 런 안의 참값 vs 보고값의 비(2.57×)**다.

### 7-B-3. ✅ 제안 2 — `--stream`으로 `prefill_s` 복구, 그리고 H3의 직접 증거

§6-1의 진단대로 `--stream`을 넣자 **`prefill_s`가 126/126 전부 기록**됐다(기존 스윕은 전부 0).

`default` 부하 하 step 분해 (n=126): **prefill_s(TTFT) = 10.14s**, decode 2.39s, **pause_s = 0.00s**, tool 7.62s.

> **★ H3·H4의 결정적 증거**: c=1 warm prefill이 **0.46s**인데 부하 하 TTFT가 **10.14s**다. 차이 **~9.7s**는
> 재프리필 계산(2.26s)만으로 설명 안 되고, **대부분이 vLLM waiting 큐 대기**다.
> → §2-2의 "default는 vLLM 내부에서 줄을 선다"가 **TTFT라는 제3의 독립 지표로 재확인**됐다(REASONING−nrr 갭,
> queries 팽창에 이은 **세 번째** 증거).
> → **그리고 §2-3의 H1 수치 문장을 정정해야 한다**: default의 진짜 벌금은 "재프리필 2.26s"가 아니라
> **"TTFT 10.14s(재프리필 + 숨은 큐 대기)"**다. tr의 pause 18.5s와 비교하면 **18.5 vs ~10.1 — 여전히 tr이 크지만 8.2배가 아니라 1.8배**다.
> H1의 **방향은 유지**(default 벌금 < tr 벌금)되나 **격차는 훨씬 작다**. [정정]

### 7-B-4. ❌ **철회 — "tr 데드락"은 tr의 버그가 아니라 내 하네스 버그였다**

> **결론부터: 아래에 기록한 "tr 스케줄러 데드락"은 전부 무효다. 원인은 내가 `--router-url`을 안 넘긴 것이다.**
> 이 절을 지우지 않고 남기는 이유는 **잘못된 추론이 어떻게 진행됐고 무엇이 그것을 잡았는지**를 기록하기 위해서다.

**진짜 원인 (실측 확정)**:
- `trace_replay_driver_expC_yunuikang.py:455` → `--router-url` **기본값 `http://localhost:9000`**.
- 이 값은 **오직 한 곳**에서 쓰인다 — `driver:286` `POST {router_url}/programs/release` (세션 종료 시 프로그램 해제).
- 내 프록시는 **9011/9013/9014**였는데 `--router-url`을 **안 넘겼다** → 모든 release 호출이 **존재하지 않는 9000번으로 가서 조용히 실패**
  → **프로그램이 영영 해제되지 않음** → `active_program_tokens` 단조 증가(`active=40,671` / `C_total=43,888`)
  → `remaining_capacity() < 0` 영구 고착 → **paused 18개가 절대 resume 못 함** = 내가 "데드락"이라 부른 것.
- **expC 스윕 스크립트는 `--router-url`을 정확히 넘긴다**(`run_trace_sweep_expC_yunuikang.sh:65`) → **expC는 애초에 이 문제가 없었다.**
- **default가 멀쩡했던 이유**: default는 용량 검사(`remaining_capacity`) 자체를 안 하므로(`router.py:394` `if not self.scheduling_enabled`)
  프로그램이 안 해제돼도 라우팅이 막히지 않는다. → **"tr만 데드락"이라는 착시**가 여기서 나왔다.

**따라서 철회하는 주장**:
- ~~"`--stream` + tr에서 데드락"~~ → `--stream` 무관(맞음), **그러나 tr 무관이기도 하다. 내 설정 오류.**
- ~~"tr의 용량 회계가 ACTING 토큰을 과다 계상해 자기 데드락"~~ → **근거 없음.** ACTING 토큰이 쌓인 건 tr의 회계 때문이 아니라 **해제가 안 됐기 때문**.
- ~~"NPROG이 변수"~~ → **아니다.** NPROG 24/32/64 전부에서 났던 이유는 **전부 같은 하네스 버그**였기 때문.

**무효 데이터 격리**: `scratch/vprof/INVALID_missing_router_url/` (DEADLOCK_*, sample_tr_*, 초기 vprof_metrics.jsonl).
**`figures/vllm_deadlock_timeline.png`은 폐기 대상** — 발표에 쓰지 말 것.

**살아남는 것**: §7-B-4b(pause heavy tail)는 **expC 원본 데이터** 기반이라 **이 버그와 무관하게 유효**하다.
**교훈**: expC와 "동일 조건"이라 믿었지만 CLI 인자 하나가 달랐다. 신규 하네스는 **기존 스윕 스크립트의 인자를 전수 대조**할 것.

<details>
<summary>(기록 보존) 철회된 원래 서술 — 클릭</summary>

### ~~7-B-4-old. 예상 못 한 발견 — `--stream` + `tr` 조합에서 스케줄러 데드락~~

tr 런이 **완주하지 못했다**. 샘플러 실측:

| 시각 | 상태 |
|---|---|
| t = 98s | 마지막 `reasoning > 0` |
| t = 98 ~ 359s (**261초**) | `reasoning=0, nrr=0+0, gpu2/3 util = 0%/0%`, `acting=2+3`, **`paused_total=18`** — **완전 정지** |

프록시 로그 마지막 스케줄러 동작:
```
Resumed program claude:040c780b...#0 to http://localhost:8003 (status=acting, tokens=4650, active=40671)
```
→ **`active_program_tokens = 40,671` vs `C_total = 43,888`.** ACTING 프로그램들이 토큰을 거의 다 점유 →
`remaining_capacity() < required` → **paused 18개를 resume 못 함** → ACTING은 워커가 막혀 진행 못 함 → **순환 대기**.

**✅ `--stream`은 원인이 아니다 (통제실험으로 확정)**. `--stream`만 제거하고 tr을 재실행했더니 **똑같이 데드락**했다:

| 런 | 정지 시간 | 최종 상태 |
|---|---|---|
| tr + `--stream` | **249s** | acting=2+3, **paused_total=18**, nrr=0+0, gpu 0%/0% |
| tr, **no** `--stream` | **344s** | acting=3+2, **paused_total=18**, nrr=0+0, gpu 0%/0% |

**거의 동일한 서명**(paused 18 / acting 5 / nrr 0 / GPU 0%)으로 재현 → **`--stream` 무관, tr 고유 현상.**
그림: `figures/vllm_deadlock_timeline.png`. 증거: `scratch/vprof/DEADLOCK_*`.

**🚨 그리고 — 내가 처음에 세운 추측은 expC 데이터가 반증했다 (정직하게 기록)**

나는 "expC의 tr `pause_s` max 841s / p99 522s도 같은 데드락일 것"이라 **추측했다. 틀렸다.**
expC 전 런에서 **"시스템 전체 정지"(reasoning==0 **및** nrr==0 연속 구간)**를 직접 탐지한 결과:

| run | 최장 시스템 정지 | >60s 구간 수 |
|---|---|---|
| expC tr C=4 / 8 / 16 / 32 | **26s / 40s / 30s / 47s** | **전부 0개** |
| expC default C=4~32 | 16~41s | 전부 0개 |
| **2026-07-17 재현 런 (tr, C=16, NPROG=32)** | **249~344s** | **1개** |

→ **expC의 tr 런에는 데드락이 없었다.** `pause_s` max 841s는 **개별 프로그램 1개의 대기 시간**이지 시스템 정지가 아니다
(다른 프로그램들은 그동안 계속 돌았다 — 이게 tr의 **의도된 설계**다: 캐시를 지키려 특정 프로그램을 오래 재운다).
→ **따라서 "expC의 tr −34%가 데드락 버그 때문"이라는 내 추측은 기각. expC 결과는 유효하다.**

**남은 것 — 미해결 이상현상 (정직하게 열어둠)**:
- 재현 조건(**C=16, NPROG=32**)에서만 시스템 데드락이 나고, expC(**C=16, NPROG=64**)에선 안 났다. **유일한 차이는 NPROG.**
  데드락 시점(t≈110s)에 paused 18 + acting 5 = **23/32가 아직 in-flight**라 "종료 드레인 구간 artifact"로 설명되지 않는다.
- 프록시 로그의 마지막 단서: `active=40,671` vs `C_total=43,888` → ACTING 토큰이 풀을 거의 채워 resume 불가.
  **[추정, 미검증]** `tool_coefficient=1.0`이 ACTING을 REASONING과 동일 가중하는 것의 귀결일 수 있고,
  논문의 `Cost_caching`·`f(t)=2^(-t)` 감쇠가 **정확히 이걸 막으려는 장치**다(§5-1·§5-0).
  `--use-acting-token-decay`가 데드락을 푸는지는 **미검증** — 다음 실험 후보.
- **`router.py`는 건드리지 않았다.** 이건 관측 결과이지 수정 제안이 아니다.
- **결론에 미치는 영향: 없음.** expC 데이터가 깨끗하므로 §1~§4의 모든 결론은 그대로 유효하다.

</details>

**(위 접힌 서술은 2026-07-17 당일 `--router-url` 누락이 밝혀져 전부 철회됨. 위 7-B-4 본문 참조.)**

### 7-B-4b. ★★ `"tr은 매 step 18.5초 pause한다"`는 틀렸다 — **heavy tail이 만든 평균**

데드락을 조사하다 발견했다. expC tr `pause_s` 분포 (n=4,301, `figures/vllm_pause_heavy_tail.png`):

| 분위 | p50 | p75 | p90 | p95 | **p99** | max | **mean** |
|---|---|---|---|---|---|---|---|
| pause_s | **0.00s** | **0.01s** | 11.14s | 65.29s | **521.85s** | **841.13s** | **18.47s** |

| 임계 | >1s | >30s | >60s | >300s | >600s |
|---|---|---|---|---|---|
| 해당 step 비율 | ~25% | **7.0%** | 5.2% | **2.4%** | 0.8% |

> **tr 스텝의 75%는 pause가 사실상 0이다.** 평균 18.47s는 **소수(2.4%)의 5~14분짜리 파국적 대기**가 만든 값이다.
> → **§2-3의 H1 수치 문장("tr이 내는 벌금 ≈ 18.5초/step")은 오해를 부른다.** 정확히는
> **"tr은 대부분의 step에서 전혀 pause하지 않지만, 2.4%의 step에서 5분 이상 굶긴다"**이다.
> 이건 tr의 **의도된 설계**(캐시를 지키려 특정 프로그램을 오래 재움)의 직접 관측이며, **p95 latency 열세의 진짜 정체**다.
> → 발표·논문에서 **평균 pause 대신 분위수(p50=0, p99=522s)로 서술할 것.** [정정]

### 7-B-5. ★★ 최종 결과 (`--router-url` 수정 후, 유효) — **오염은 비대칭이고, §3-3 열린 고리가 닫혔다**

조건: C=16, NPROG=32, `--stream`, `--router-url` 정상. 두 런 모두 **rc=0 정상 완주**.
offered load 동일성 확인: `prompt_tokens_total` = **2,439,542(default) / 2,439,544(tr)** → 결정적 replay 검증됨.

| run | **참 hit**(cached/total) | 보고 hit(hits/queries) | **배수** | **queries 팽창** | 참 recompute tok | 불변식 | preempt | wall |
|---|---|---|---|---|---|---|---|---|
| **tr** | **0.6983** | **0.6983** | **1.00×** | **1.0×** | 735,928 | ✅ True | 0 | 351s |
| **default** | **0.1844** | **0.0383** | **4.81×** | **26.3×** | 1,989,606 | ✅ True | 0 | 222s |

> ### ★ 발견 1 — **오염은 비대칭이다. tr의 hit 지표는 애초에 정확했고, default만 5배 과소평가됐다.**
> - **tr: 팽창 1.0× → 참 hit == 보고 hit (0.6983 = 0.6983, 소수 4자리까지 일치).**
>   tr은 프록시에서 미리 막아 **요청이 vLLM 큐에 아예 안 쌓이므로 재검사가 0회**다.
> - **default: 팽창 26.3× → 참 0.1844 vs 보고 0.0383 = 4.81배 과소평가.**
> - → **지표 버그와 물리 메커니즘이 같은 현상이다.** "default가 vLLM 내부에서 줄을 선다"(§2-2)는 사실이
>   그대로 "default의 hit 지표만 오염된다"로 나타난다. **네 번째 독립 증거.**
> - → **"default는 프롬프트의 96%를 재프리필한다"는 틀렸다. 실제 81.6%다.** 여전히 나쁘지만 수치가 다르다.
> - 검증: 보고 hit 0.0383이 **expC C=16의 0.037과 일치** → 이 런이 expC를 재현함을 확인.

> ### ★★ 발견 2 — **§3-3의 열린 고리가 닫혔다 (오차 28.2% → 1.4%)**
> 같은 모델 `thr ∝ U / W`, `W = ptok·(1−hit)/5896 + 0.856`에 **hit만 바꿔 넣었다**:
>
> | 쓰는 hit | W_tr | W_def | W_def/W_tr | **예측 thr 비** | 실측(expC C=16) | **오차** |
> |---|---|---|---|---|---|---|
> | 오염된 보고 hit (0.797 / 0.037) | 1.499s | 3.908s | 2.606 | **1.035** | 1.441 | **28.2%** ❌ |
> | **참 hit (0.6983 / 0.1844)** | 1.812s | 3.441s | 1.899 | **1.421** | 1.441 | **1.4%** ✅ |
>
> → **U(=R 모델) × W(=참 재프리필 비용) 두 항만으로 tr/default throughput 비를 1.4% 오차로 예측한다.**
> §3-3에서 "닫히지 않는다"고 정직히 열어둔 고리의 원인이 **정확히 hit 오염이었음이 확정**됐다.
> ⚠️ **한계**: U(0.855/0.317)는 expC(NPROG=64), 참 hit는 이번 런(NPROG=32)에서 왔다 — **런 혼합**이다.
> 보고 hit이 0.0383≈0.037로 일치해 비교 가능성은 확보했으나, **동일 런에서 U와 참 hit를 함께 재는 확인이 남았다** [한계].

> ### ★ 발견 3 — **부하 하 step 분해: H1의 수치를 정정한다** (`figures/vllm_latency_breakdown_loaded.png`)
>
> | run | pause_s | **prefill_s (TTFT)** | decode_s | tool_s | **합** | n |
> |---|---|---|---|---|---|---|
> | **tr** | **20.83** | 1.29 | 1.08 | 7.55 | **30.76s** | 126 |
> | **default** | **0.00** | **10.79** | 2.12 | 7.65 | **20.56s** | 126 |
>
> - **default의 숨은 벌금이 드러났다**: TTFT 10.79s − tr의 1.29s = **~9.5s가 vLLM 큐 대기**(c=1 warm prefill은 0.46s).
> - → **§2-3의 "default 2.3초 vs tr 18.5초, 8.2배"는 정정한다.**
>   **정정: default의 벌금 ≈ 9.5초/step(재프리필 + 숨은 vLLM 큐), tr의 벌금 ≈ 20.8초/step(프록시 pause). 약 2.2배.**
>   **H1의 방향은 유지되나(default 벌금 < tr 벌금) 격차는 8.2배가 아니라 2.2배다.**
> - tr의 step 합(30.76s)이 default(20.56s)보다 길다 → tr throughput 열세와 정합.

---

## 8. 최종 한 문단 — "vLLM은 실제로 이렇게 동작하고, 그래서…"

> vLLM V1은 prefill/decode 단계 구분 없이 매 iteration `max_num_batched_tokens`(4090에서 **2048**, `arg_utils.py:2414-2423`) 만큼의 토큰을 RUNNING 요청부터 채워 넣고, KV 블록이 모자라면 **preempt가 아니라 waiting 큐에서 승인을 거부**한다(`scheduler.py:874-895`; 실측 preemption≈0과 정합). TraceLab의 18.7k 프롬프트는 이 예산을 약 10 iteration 독점하므로 **실제 GPU 배치는 정책과 무관하게 1.1~1.5에 고정된다**(실측 `mean nrr|nrr>0`: tr 1.19 / default 1.45). 따라서 **"GPU를 채운다"는 것은 배치를 키우는 것이 아니라 시간축의 구멍을 메우는 것**이고, `R = k_fit·d`는 바로 **동시에 GPU 일을 원하는 요청 수의 기댓값**이다(실측 mean nrr과 일치: default C=16에서 R=1.20 vs 1.24). R<1이면 GPU에 bubble이 있어 **캐시 미스의 한계비용 2.26 s/turn(cold prefill 2.72s − warm 0.46s, 선형적합 r²=0.981)이 놀던 시간에 흡수되어 거의 공짜**인 반면, tr의 pause는 **18.5 s/step(n=4,301)의 순손실**이다 — **2.3초 벌금 vs 18.5초 벌금, 8.2배 차이. 이것이 R<1에서 default가 이기는 이유이며, "tr이 나쁘니 default가 낫다"가 아니라 default의 벌금이 실제로 공짜라는 인과다.** R≥1(SWE d≈0.995, TP2 fit≈25)이 되면 `P(GPU가 병목)`이 0→1로 가면서 **같은 2.26초가 기회비용에서 순손실로 바뀌어** tr이 이긴다 — 하나의 곱셈(`히트의 가치 = 절약 시간 × P(병목)`)이 두 레짐을 모두 설명한다. **다만 모르는 것을 분명히 한다**: (i) vLLM V1은 승인 실패한 waiting 요청을 **매 step 재계수**하므로(`scheduler.py:888-895` break가 `pop_request`:917 이전) 우리의 hit rate는 default에서 **30배 팽창한 표본**에 기반하며, 방향은 견고하되 **절대값 0.037은 신뢰할 수 없다**; (ii) 그 결과 U→throughput의 마지막 한 단계가 정량적으로 닫히지 않는다(§3-3, 예측 1.03 vs 실측 1.44); (iii) "재프리필이 decode 슬롯을 훔친다"는 서술은 **코드상 부정확**하며 실제 기전은 KV 고갈에 의한 waiting 큐 정체다; (iv) 34p 논문 갱신본을 확인하지 못했고, **duty를 아무도 안 본다는 주장은 거짓**이다(InferCept Eq.2가 직접 반례) — 우리 기여는 duty를 **메커니즘의 입력이 아니라 활용률의 예측 변수로 승격시킨 것**으로 재정의되어야 한다.

---

## 9. 산출물
- 스크립트: `scripts/plot_vllm_profiling_yunuikang.py` (기존 JSONL/CSV 재분석, **GPU 0장**)
- 그림: `figures/vllm_timeline_tr_vs_default.png`(실제 타임라인), `vllm_U_triangulation.png`(Phase 4), `vllm_batch_refutes_H2.png`(H2 반증), `vllm_queries_inflation.png`(카운터 오염), `vllm_prefill_curve.png`(prefill 곡선)
- **수정 필요 문서**: `logs/2026-07-06_MECHANISM_REFERENCE_yunuikang.md` §1-1(Cost_unused↔Cost_caching, §5-0), `logs/2026-07-06_DEEP_ANALYSIS_yunuikang.md` §B-1(granularity → 재검사 중복 계수, §1-2)
