# MORI 저성능 진단 — TTFT 분해 + promote 방식 (무료, GPU 0)

> 작성 2026-08-01 · 브랜치 `mori` · HEAD `b311273` · 데이터 `scratch/mori/msw/results_msw.jsonl`
> 목적: M-SWP에서 MORI < TA+O(P1 역방향 FAIL, throughput 0.45×·TTFT 4.1×)의 원인 규명. GPU 무증분(기존 데이터+코드).

## 결론 (두 조건 모두 성립)
**MORI 저성능 = tick-driven 승격(5s) + ι-우선순위로 인한 재개 대기(pause) 지배.** 엔진 prefill/reload나 typed eviction이 주범 아님.

## (b) promote는 tick-driven [코드 확정]
- `MultiBackendRouter._scheduler_loop` (`scheduler/router.py:746-753`): `await asyncio.sleep(self._scheduler_interval)`(=5.0s) 후 `_scheduled_check()`.
- `MoriRouter._scheduled_check` → `_mori_promote` (`mori_router.py:201,274`): 승격은 **5s tick에서만**.
- demote된 프로그램에 요청 도착 → `update_program_before_request`가 `waiting_event`에서 블록 → **다음 tick의 _mori_promote가 set할 때까지 대기**. event-driven 아님. (모듈 docstring: "all tier moves happen in the periodic tick".)

## (a) TTFT는 pause 지배 [근거 추론]
| 셀 | ttft p50(s) | mean | p95 | cacheHit | out tok/s |
|---|---|---|---|---|---|
| TAO_r2_C50 | 2.1 | 26.9 | 52.2 | 88% | 16.1 |
| TAO_r2_C80 | 3.4 | 53.4 | 120.6 | 87% | 14.3 |
| MORI_r2_C50 | 5.0 | 43.9 | 119.7 | 84% | 11.8 |
| **MORI_r2_C80** | **13.9** | 94.9 | **398.7** | 78% | 6.5 |
| MORI_r1_C80 | 9.1 | 100.4 | **563.8** | 68% | 7.4 |

- cacheHit 78–88% 높음 → 재개 요청의 **엔진 prefill/reload는 작음(대부분 캐시 히트 → ~1–2s backend TTFT)**.
- 그럼에도 MORI p50=13.9s, **p95=398–564s** → **TTFT ≈ pause + ~2s prefill**, 즉 **pause 지배**.
- p95 ~400s = **약 80 tick(×5s) 대기 = starvation**(수십 tick 동안 승격 못 받음).
- TA+O(같은 tick·엔진)는 p50 3.4s → 차이는 **MoriRouter 3-tier churn + ι-우선 승격이 갓-활성(high windowed-ι) 프로그램을 뒤로 미룸** → 재개 지연.
- 부차: MORI cacheHit(78%) < TAO(87%) — typed eviction(host busy-first)이 유용 KV를 일부 축출한 흔적(부차적, ablation서 확인).

## 수정안 (재런치 전 리뷰용, 미구현)
**event-driven 승격** — 요청 도착 시 tick 대기 없이 즉시 처리:
1. `update_program_before_request`에서 demote 상태 감지 시 `pause_resume_lock` 하에 `backend.remaining_capacity() ≥ total_tokens+BUFFER`이면 **즉시 promote**(register+`waiting_event.set()`) → tick 대기 제거.
2. 용량 부족 시, GPU 내 **최고-ι 프로그램의 ι가 요청 프로그램보다 크면(더 idle)** 그것을 demote해 자리 확보 후 승격(상대-idleness 입장제어를 도착 시점 적용).
3. 불가 시 tick 폴백(드묾). 주기 tick은 rebalance 안전망 유지(간격 5s→1–2s 병행 고려).
4. pending(요청 대기) 프로그램은 windowed-ι와 무관하게 승격 우선순위 최상(갓-활성 starvation 방지).

## 다음
- 수정은 **리뷰 후 구현→재런치**(승인 대기). pause 지배가 명확하므로 event-driven 수정 우선.
- [GPU, 후순위] MORI-a-only ablation(router=mori+EVICT=lru): typed eviction 기여 분리 — 수정 전/후 비교 또는 확정용.
