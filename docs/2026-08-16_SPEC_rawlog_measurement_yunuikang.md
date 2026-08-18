# 측정 프로토콜 규격 — MORI raw-log steady-state (셀 공통·고정)

> 작성: 강윤의 · 2026-08-16 (KST) · 확정: 김태현 지시 2026-08-16
> 대상: `scratch/mori/rawlog_pro6000/<C>/` 6-file raw stream
> 구현: `scripts/postprocess_rawlog_yunuikang.py` (이 문서가 유일한 규격 근거)

**이 문서는 "무엇을 어떻게 자를지"만 정한다. 판정·해석·비교는 이 문서의 범위가 아니다.**

---

## 0. 왜 고정하는가

런 길이를 셀당 8h로 **고정**했으므로 창을 정확히 끊을 필요는 없다(throughput은 rate라 런
길이에 불변). 대신 **어디를 steady로 볼지**와 **분산을 어떤 단위로 낼지**가 셀마다 다르면
셀 간 비교가 그 차이에 오염된다. 따라서 아래 규칙을 **3셀에 기계적으로 동일 적용**한다.
셀별 튜닝·눈대중 조정 금지.

---

## 1. 시간축

모든 시각은 `run_meta.clock_anchor.t0_unix`를 원점(0.0s)으로 하는 float 초.
driver stream(`requests`·`events`·`snapshots`·`gpu`)과 engine stream(`kv_events`·`steplog`)이
같은 원점을 쓴다 — closure 검사의 "driver/engine 시계 원점 일치" 항목이 이를 매 셀 검증한다.

driver 창의 시작/끝은 `events.jsonl`의 `run_start` / `run_end` 이벤트로 잡는다.

```
T_run_start = ts(run_start)
T_run_end   = ts(run_end)
```

---

## 2. warmup 컷 (고정 규칙)

```
T_warm = T_run_start + max(2400.0, T_fill)
```

- **2400 s (40분) 고정 하한.** GPU KV 풀(1.32 M tok) + host tier(2.64 M tok) 채우기 +
  radix 트리 성장까지 포함한 보수적 하한. C=fit 셀은 이보다 빨리 안정되지만 **셀 간
  동일 규칙**을 위해 낮추지 않는다.
- **`T_fill` = 데이터 기반 가드**: `snapshots.num_used_tokens` 가 **처음으로** 그 런의
  post-2400s 중앙값의 **95%** 에 도달한 시각. 아직 채워지는 중이면 40분을 넘겨 자른다.
- 둘 중 **늦은 쪽**을 쓴다. 즉 40분은 하한이지 상한이 아니다.

> warmup 구간의 raw 레코드는 **버리지 않는다**(파일에 그대로 남는다). 컷은 집계 시점의
> 필터일 뿐이며, 나중에 규칙이 바뀌어도 재실행 없이 재계산된다 — 이 배치의 목적 그 자체.

---

## 3. bin — 10분 고정

warmup 이후 구간을 **정확히 600 s** 단위 비중첩 bin으로 자른다. bin 경계는 `T_warm` 에서
시작해 앞으로 진행하고, **끝의 자투리(600 s 미만)는 버린다**.

```
bin_k = [T_warm + 600k , T_warm + 600(k+1))     k = 0,1,2,...
```

bin당 지표:

| 지표 | 산출 |
|---|---|
| `throughput_tok_s` | 그 bin과 겹치는 각 request의 **디코드 구간**(`first_token_ts`→`end_ts`)에 `output_tokens`를 **시간 비례 배분**한 뒤 합 ÷ 600 |
| `kv_usage_frac` | bin 안 `snapshots.num_used_tokens` 평균 ÷ `kv_pool.gpu_pool_tokens` |
| `host_tier_frac` | bin 안 `snapshots.hicache_host_used_tokens` 평균 ÷ `host_tier_tokens` |
| `req_done` | `end_ts` 가 bin 안에 있는 request 수 |

> throughput을 **토큰 비례 배분**으로 내는 이유: request 단위로 bin에 귀속시키면 창
> 경계에 걸친 긴 디코드가 통째로 한 bin에 들어가 bin 간 인공 변동을 만든다.

---

## 4. steady 판정 (고정 기준)

post-warmup bin들의 `throughput_tok_s` 중앙값을 `M` 이라 할 때,

```
bin_k 가 steady-후보  ⟺  |throughput_k − M| ≤ 0.10 · M      (±10 %)
```

**steady window = 후보 bin들의 최장 연속 구간.** 그 길이가

```
steady 도달  ⟺  최장 연속 구간 길이 ≥ 12 bin (= 2 h)
```

- 12 bin 미만이면 그 셀은 **"steady 미도달"** 로 기록한다. 임계를 낮추거나 창을 옮겨
  억지로 맞추지 않는다.
- 미도달이어도 raw 파일은 그대로 산출물이며, 실패 사실을 결과 로그에 그대로 적는다.

---

## 5. 분산 (반복셀 대체)

steady window 안의 **10분 bin 각각을 하나의 표본**으로 본다 (§3의 bin을 그대로 재사용).

```
n        = steady bin 수 (>= 12)
mean, sd = 그 n개 표본의 평균·표준편차
CV       = sd / mean
CI95     = mean ± 1.96 · sd / sqrt(n)          (정규 근사, n>=12 이므로)
```

부트스트랩은 이 배치에서 하지 않는다 — 목적이 "반복 런 없이 변동 크기를 보이는 것"까지이기 때문.

> ### ★ CI95 해석 caveat (확정 2026-08-16)
> 위 식은 steady bin들을 **독립 표본으로 취급**한다. 그러나 실제로는 throughput에
> **지속성(자기상관)** 이 있어 인접 bin이 서로 독립이 아닐 수 있다. 자기상관이 있으면
> 유효 표본수가 `n`보다 작아지므로 **정규근사 CI95는 실제보다 다소 낙관적(좁게)** 나온다.
>
> 이 배치는 판정이 아니라 특성화이므로 보정 없이 그대로 진행하되,
> **CI95를 유의성 근거로 쓰지 않는다.** 변동의 크기 감각(주로 `CV`)을 보는 용도다.
> 이 caveat는 `run_meta.caveats` 와 결과 로그에 모두 명시한다.

---

## 6. 셀 간 동일성 체크리스트 (본 런 전 확인)

- [ ] 3셀 모두 `DUR = 28800 s` (8 h) 로 기동
- [ ] 3셀 모두 warmup 규칙 `max(2400, T_fill)` 적용 (셀별 값은 다를 수 있음 — **규칙**이 같으면 됨)
- [ ] 3셀 모두 bin = 600 s 정확히
- [ ] 3셀 모두 steady 기준 ±10 % / ≥12 bin
- [ ] steady 미도달 셀이 있으면 그대로 기록 (보정 금지)

---

## 7. 이 문서가 정하지 않는 것

goodput·SLO 대입, prefix hit율, GPU 시간예산 분해, tier 동역학, 셀 간 비교, 5090 대조 —
전부 **후속 분석**의 몫이다. 이번 배치는 raw 수집 + 무결성 + steady 도달 여부까지다.
