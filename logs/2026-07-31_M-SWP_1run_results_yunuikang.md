# M-SWP 1런 패스 중간 리포트

> 작성 2026-08-01 · 브랜치 `mori` · **HEAD `86ec401`** · 서버 goguma6 (RTX 5090 ×2, SGLang 0.5.10 + HiCache, YaRN 64k)
> 원시 데이터: `/home/yunuikang/yunuikang_work/scratch/mori/msw/results_msw.jsonl` (18/18 셀, 셀당 1런)
> 무효(pre-fix) 참고본: `.../results_msw_INVALID_prefix_0334.jsonl` (context/timeout 버그 시기 5셀, 폐기)
> 프로토콜: 고정 1h(`--duration-s 3600`, hard-deadline+grace) · Track M primary(117,257턴, decode152) · pin `--max-total-tokens 262144` · context-length 71680(YaRN factor 1.75) · warmup 20% · C 워커 순환셔플
> **failure-rate 게이트**: `fail% >1% AND failed_programs ≥3` → 조기중단(systematic만). 1–2건 transient는 관용 + failure_types 기록.
> **데이터 위생**: 18셀 중 **TA_r0_C50만 실패 1건**(=2.3%, `http_500` **transient**, 게이트 관용). 나머지 17셀 fail% 0%. systematic abort 없음.

---

## 0. 시스템 정의 — 4종 무엇이 다른가

한 코드베이스에서 **플래그 3개**(라우터 모드 / HiCache 오프로딩 / eviction 정책)만 바꿔 4종을 A/B 한다. 각 시스템은 앞 시스템에 기능을 하나씩 얹는 **누적(ablation) 구조**다.

| 시스템 | 프록시 라우터 | 엔진 HiCache | eviction 정책 | 핵심: 무엇을 더하나 |
|---|---|---|---|---|
| **SMG** | `--router default` (순수 프록시, 스케줄링 없음) | OFF | (engine LRU) | 아무 제어 없음. DP=1이라 요청을 엔진에 직결 포워딩. **하한 baseline** |
| **TA** | `--router tr` (용량 스케줄링) | OFF | (engine LRU) | + **스케줄러**: GPU 용량 초과 시 프로그램을 pause(Waiting 큐, KV 폐기)·resume(admission control). 오프로딩은 없음 |
| **TA+O** | `--router tr` (동일) | **ON** `--hicache-ratio r` | engine LRU(native) | + **오프로딩**: 엔진이 GPU에서 밀린 KV를 host DRAM(HiCache)로 내림→재사용. 스케줄러는 TA와 동일, host tier는 엔진이 LRU로 자율 관리 |
| **MORI** | `--router mori` (ι 3-tier) | **ON** `--hicache-ratio r` | **`mori`** (typed) | + **(a) ι-스케줄러**: 상대 idleness(ι=acting/(acting+reasoning))로 GPU/CPU/Waiting **3-tier** demote(ι 큰 것 먼저)/promote(ι 작은 것 먼저) + **(b) typed eviction**: program 타입(busy/idle)을 KV 노드에 스탬프해 host는 busy 먼저 축출(idle KV 보존) |

**누적 분해(각 단계가 무엇을 격리)**:
- SMG → TA: **스케줄러(admission control)** 의 가치
- TA → TA+O: **KV 오프로딩(host tier)** 의 가치
- TA+O → MORI: **ι-배치 + typed eviction** 의 추가 가치 (= 논문 헤드라인 주장, **P1**)

**r1 / r2 (CPU:GPU 용량비)** — 오프로딩 시스템(TA+O·MORI)에만 적용:
- HiCache **host tier 크기 = r × device KV 풀**. `r1` = host 1×(≈device), `r2` = host 2×.
- device 풀은 `--max-total-tokens 262144`(≈36 GiB)로 고정, host는 r1≈262k tok / r2≈524k tok.
- r↑ = 더 많은 KV가 host에 상주 가능(재계산↓) — 단 host↔device 재적재(load_back) 트래픽↑(goguma6은 NVLink 없는 SYS/PCIe라 이 비용이 큼).
- SMG·TA는 오프로딩이 없어 r 축이 없다(표에서 `r0`로 표기).

**공통 조건**(전 시스템 동일): Qwen3-8B TP2(GPU0,1) · YaRN 64k(context-length 71680) · pin `--max-total-tokens 262144` · primary trace = Track M(117k턴) · 고정 1h · C{20,50,80} · 동일 드라이버(순환셔플·ctx-cap 69632). → 차이는 오직 위 3개 플래그이므로 **상대 비교가 시스템 효과를 격리**한다.

## 1. 전 18셀 결과 (out tok/s | ttft_p50 s | steady_turns)

| 시스템 | C=20 | C=50 | C=80 |
|---|---|---|---|
| SMG (router=default, HiCache OFF) | 3.8 / 37.2 / 223 | 2.7 / 121.9 / 180 | 3.0 / 188.6 / 175 |
| TA (router=tr, HiCache OFF) | 21.8 / 2.0 / 1363 | 12.8 / 2.5 / 859¹ | 11.4 / 2.7 / 729 |
| TA+O r1 (tr, HiCache r1) | 19.7 / 1.8 / 1247 | 14.6 / 2.6 / 943 | 8.9 / 3.9 / 629 |
| **TA+O r2** (tr, HiCache r2) | 19.9 / 1.8 / 1307 | 16.1 / 2.1 / 994 | **14.3 / 3.4 / 888** |
| MORI r1 (mori, HiCache r1, EVICT=mori) | 16.2 / 2.5 / 1035 | 8.5 / 5.6 / 602 | 7.4 / 9.1 / 498 |
| **MORI r2** (mori, HiCache r2, EVICT=mori) | 22.2 / 2.1 / 1412 | 11.8 / 5.0 / 834 | **6.5 / 13.9 / 520** |

¹ TA_r0_C50: 1 transient http_500 (fail% 2.3%), 게이트 관용. 지표는 완료 43 프로그램 기준.
보조 지표(step req/s·cacheHit·load_back·evicted)는 `results_msw.jsonl` 참조.

## 2. P1~P4 판정 (초안)

- **P1 (C=80·r=2, MORI vs TA+O) — ❌ FAIL (역방향)**: throughput MORI/TA+O = **6.47/14.28 = 0.45** (MORI가 2.2× **느림**; 기대 ≥1.15). TTFT p50 **13.9 vs 3.4s = 4.1× 악화**; ttft_mean 94.9 vs 53.4s(1.8×); step req/s 0.18 vs 0.32(0.56×). 헤드라인 가설과 정반대.
- **P2 (C 단조성) — 미성립**: TA+O r2도 **단조↓**(19.9→16.1→14.3), MORI r2도 단조↓이나 **더 급격**(22.2→11.8→6.5). "TA+O 비단조를 MORI가 개선"이 관측되지 않음. (r1 TA+O는 C80서 소폭 꺾임 8.9<14.6이나, 헤드라인 r=2는 단조.)
- **P3 (C=20 동률) — ~성립**: MORI_r2(22.2) ≈ TA(21.8) ≈ TA+O_r2(19.9). 저압박에선 유사.
- **P4 (tr 무손상) — ✅**: TA/SMG baseline 정상 구동, 크래시·회귀 없음(격리 diff 0줄은 별도 검증됨).

## 3. 서브 결론 (예상 방향은 재현)

- **TA ≫ SMG**: 스케줄러 admission control 이득 뚜렷 — throughput 3–6×, TTFT 14–70× 개선. SMG는 admission control 부재로 C↑에 TTFT 37→189s 폭증.
- **TA+O r2 > TA**: HiCache 오프로딩 이득 — C80 14.3 vs 11.4, cacheHit ~88%. r2(host 2×) > r1(특히 C80: 14.3 vs 8.9).
- **MORI < TA+O**: MORI의 3-tier(ι 배치 + CPU tier) 스케줄링이 **압박에서 지연 유발** — TTFT가 C↑에 2.1→14s 급증 → throughput 붕괴(6.5 @ C80·r2).

## 4. token drift 규명 (요청 4항)

- within_1pct **96–98%** → **drift>1% 턴 ≈ 2–4%**. 시스템별: SMG 2.0–3.3%, TA 3.0–3.4%, TA+O 2.9–4.2%, MORI 1.9–3.4%.
- **전 시스템 균일**(특정 시스템/peak-압박 regime 편향 없음) → **상대 비교를 왜곡하지 않음**.
- 원인: 컨텍스트 누적 drift + ctx-cap 트림(64k 창에 맞춰 oldest turn 제거, 실행 보장 대가로 일부 세션의 컨텍스트가 트레이스와 불일치).
- 판정: <1%는 아니고 ~3%이나 **균일 적용** → **§5 fidelity 한계로 기록**. MORI 저성능을 설명하지 못함(균일하므로).

## 5. 진단 — TTFT 분해 + promote 방식 (무료, GPU 0; 2026-08-01)

**결론: MORI 저성능 = tick-driven 승격(5s) + ι-우선순위로 인한 재개 대기(pause) 지배.** 엔진 prefill/reload·typed eviction 아님.

**(b) promote는 tick-driven [코드 확정]**: `MultiBackendRouter._scheduler_loop`(`scheduler/router.py:746-753`)가 `sleep(scheduler_interval=5s)` 후 `_scheduled_check`→`MoriRouter._mori_promote`(`mori_router.py:201,274`). 승격은 **5s tick에서만**. demote된 프로그램의 요청은 `update_program_before_request`에서 `waiting_event` 블록 → 다음 tick까지 대기(event-driven 아님).

**(a) TTFT는 pause 지배 [근거 추론]**:
| 셀 | ttft p50 | mean | p95 | cacheHit |
|---|---|---|---|---|
| TAO_r2_C80 | 3.4 | 53.4 | 120.6 | 87% |
| MORI_r2_C80 | 13.9 | 94.9 | **398.7** | 78% |
| MORI_r1_C80 | 9.1 | 100.4 | **563.8** | 68% |
- cacheHit 78–88% → 재개 요청의 엔진 prefill/reload 작음(~1–2s). 그런데 p50 13.9s·**p95 398–564s(≈80 tick×5s = starvation)** → **TTFT ≈ pause + ~2s prefill**, pause 지배.
- TA+O(같은 tick·엔진) p50 3.4s → 차이는 MoriRouter 3-tier churn + ι-우선 승격이 **갓-활성(high windowed-ι) 프로그램을 뒤로 밀어** 재개 지연. cacheHit MORI(78%)<TAO(87%)는 typed eviction의 부차 흔적.

**수정안(리뷰 후 구현, 미구현) — event-driven 승격**:
1. `update_program_before_request`에서 demote 감지 시 `pause_resume_lock` 하에 `remaining_capacity ≥ total_tokens+BUFFER`이면 **즉시 promote**(tick 대기 제거).
2. 용량 부족 시 GPU 내 **최고-ι(더 idle) 프로그램이 요청 프로그램보다 idle하면 demote**해 자리 확보 후 승격(상대-idleness 입장제어를 도착 시점 적용).
3. 불가 시 tick 폴백(드묾). pending은 windowed-ι 무관 승격 최우선(starvation 방지). 주기 tick은 rebalance 안전망(5s→1–2s 병행 고려).

**다음 단계**:
- **event-driven 수정 우선**(pause 지배 명확) → 리뷰 후 구현·재런치.
- [GPU, 후순위] MORI-a-only ablation(router=mori+EVICT=lru, C=80·r{1,2}): typed eviction 기여 분리(수정 전/후 비교 또는 확정용).
- repeat는 후순위(패턴 단조·일관, 노이즈 아님).

---

> 상태: 1런 패스 완료 + 진단 완료·정지. GPU 유휴. event-driven 수정 구현/재런치는 별도 승인 후.
