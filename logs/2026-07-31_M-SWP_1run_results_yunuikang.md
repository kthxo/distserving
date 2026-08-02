# M-SWP 헤드라인 스윕 — 결과 + 정량 진단(결함 1·2) + 수정설계 (통합 로그)

> 작성 2026-08-01 (진단·GPU util·결함2·레짐 정량·수정설계 통합 2026-08-02) · 브랜치 `mori` · **HEAD `86ec401`** · 서버 goguma6 (RTX 5090 ×2, SGLang 0.5.10 + HiCache, YaRN 64k)
> **통합 이력**: `MORI_rootcause_quant`·`MORI_reproduce_regime-match` 로그를 본 파일로 병합 후 삭제(동일 실험 = 단일 문서 규칙).
> 원시 데이터: `scratch/mori/msw/results_msw.jsonl`(18셀) · `scratch/mori/msw/gpu_*.jsonl`(util/mem CSV) · `scratch/mori/msw/serve_*.log` · Track M `scratch/traces/tracelab_moriM_L64k_yunuikang.jsonl` · 논문 `MORI.pdf`(arXiv:2606.00866v1)
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

(정량 root-cause·수정 설계는 §7·§10으로 통합.)

---

## 6. 압박 레짐 정량화 — 우리 vs 논문  [측정 + 논문-인용]

- KV 풀(device) = **262,144 tok**(pin). Track M 컨텍스트 median 32,376 / peak 65,536 → **fit 8.10 / 4.00**. **oversub = C/fit**:

| C | oversub(fit 8.1) | oversub(fit 4.0) |
|---|---|---|
| 20 | 2.5× | 5.0× |
| 50 | 6.2× | 12.5× |
| **80** | **9.9×** | **20.0×** |

- 유효 압박(idle-heavy 보정, 세션 ι mean 0.517) ≈ **4.7×** [추정]. host tier r1=524k/r2=786k tok이나 host↔device reload가 SYS/PCIe(NVLink 없음)로 느림.
- 논문 [논문-인용, PLAN §D-5]: C=20을 "겨우 fit"으로 사이징, baseline이 C=80서도 수백 tok/s(비-붕괴). 우리 C=80 baseline은 한 자릿수(6.5–14.3) → **우리가 명백히 더 빡센 초과구독**(fit 대조 + throughput 둘 다).
- **★ 레짐 정정(구 regime-match 결론 통합)**: 저-oversub(C=20·r2)에선 MORI가 오히려 **+12%(1.12× throughput)**로 논문 방향과 정합. 역전은 oversub **6~10×(논문 미검증 범위 >~4×)**에서만. 즉 관측된 역전은 **순수 코드버그가 아니라, 작은 HBM(fit 8)이 강제한 극단 레짐에서 아래 결함들이 드러난 것 = HW 레짐 한계.** 결함 1·2는 faithful 재현 시 함께 수정 대상.

## 7. 결함 1 — 승격 굶음 정량 체인 (§5 진단의 정량판)  [측정→계산/추론]

① C=80 fit 8.1 → 상주 ≈8, 승격 라운드 free slot ≈0–few. ② `_mori_promote`(`mori_router.py:274`)가 cpu_pending을 **ι 오름차순** 정렬 → 방금 툴콜 끝낸 높은-ι pending이 매 라운드 꼬리 = 굶음. ③ 관측 TTFT p95 **398s(r2)/564s(r1)** ÷ 5s tick ≈ **80/113 라운드 대기**(②와 정합). ④ 승격은 `_scheduler_loop`(`router.py:746-753`)의 5s tick에서만(event-driven 아님) → 도착즉시 승격 경로 없음. ⑤ [추론] cacheHit 78% → 엔진 prefill ~1.4s(serve log ~5000 tok/s 역산)인데 관측 p50 13.9s → **pause ≈12.4s 지배**. ⑥ [측정] 같은 엔진 TA+O p50 3.4s → **승격-대기 오버헤드 ≈10s(p50)/278s(p95)**. **원인 = 라우터 승격 정책(ι-정렬 + 5s tick), 엔진/typed eviction 아님.**

## 8. 결함 1 GPU util 근거 (샘플러 집계)  [측정]

`sample_gpu_resident_yunuikang.py`가 nvidia-smi util/mem을 셀별 `gpu_<tag>.jsonl`(CSV)에 샘플. warmup 20% 제외, 두 GPU 평균 util% (mean/median):

| system | C=20 | C=50 | C=80 (·p=avg paused) |
|---|---|---|---|
| SMG | 100/100 | 100/100 | 100/100 |
| TA | 73/100 | 82/100 | 83/100 p65 |
| **TA+O r2** | 70/100 | 67/100 | **73/100 p70** |
| **MORI r2** | 73/100 | 82/100 | **90/100 p54** |
| MORI r1 | 84/100 | 90/100 | 94/100 p60 |

- **MORI util이 TA+O보다 높은데(C80 90% vs 73%) throughput은 절반 이하** → **high-util·low-throughput = churn/recompute 낭비**(cacheHit 78 vs 87%, 3-tier thrash)와 정합. median util 전 셀 100%.
- 굶음은 **GPU idle이 아니라 프로그램-레벨 admission 지연**: paused 평균도 MORI가 낮음(C80 54 vs 70) → GPU를 비운 게 아님. 원시 `scratch/mori/msw/gpu_*.jsonl`(mem 컬럼 = KV 상주량 별도 가용).

## 9. 결함 2 — typed eviction 논문 불일치  [코드↔논문 대조]

- **논문 [논문-인용, `MORI.pdf` §4.3]**: 타입 = 스케줄러 큐 배치(GPU=busy / CPU=idle / Waiting=inactive), 축출 GPU=`inactive→idle→busy` / CPU=`inactive→busy→idle`, LRU tie-break.
- **우리 [측정]**: 타입 = ι 임계 버킷(`_type_rank` `mori_router.py:89-98`: ι<0.33→2, 0.33–0.66→**mixed=1**, ≥0.66→0), device forward / host reversed(`mori_hicache_yunuikang.py:54-66, 83-91`) → GPU `idle→mixed→busy` / CPU `busy→mixed→idle`.
- **불일치 3건**: ① **inactive 타입 누락**(양 tier inactive-first 미적용, 최대 결함) ② 타입기준 상이(큐 배치 vs ι 크기) ③ 논문에 없는 mixed 추가. (일치: tier 반전·busy↔idle 방향·LRU). 부정확 주석 `mori_hicache_yunuikang.py:21`(host를 "busy→idle→inactive"로 오기).
- 영향: cacheHit 78 vs 87% 등 **부차 효과에 국한**; 헤드라인 역전 주원인은 결함 1. 단독 기여는 MORI-a-only(EVICT=lru) ablation으로 분리.

## 10. 수정 설계 (faithful 재현 시 결함 1+2 함께 = 단일 런)  [설계, 미구현]

- **결함 1(승격)**: (a) event-driven 승격 — `update_program_before_request`에서 demote 감지 시 용량 있으면 tick 대기 없이 즉시 promote + `waiting_event.set()`; (b) pending은 ι 아닌 **aging(waiting_since) 우선** 정렬(굶음 제거), non-pending만 ι; (c) make-room = 최고-ι demote(단 pending/방금활성 제외 + `min_dwell`); (d) tick은 rebalance 안전망(5s→1–2s). `program/state.py` +`waiting_since`.
- **결함 2(typed eviction)**: `_type_rank`를 ι-버킷 → **큐 상태(GPU/CPU/Waiting→busy/idle/inactive)** 기반으로, inactive 최저 우선순위(양 tier inactive-first), mixed 제거.
- **격리**: `--router tr|default`(baseline) 무손상. 유닛테스트: 즉시-promote / pending-aging / make-room 제외 / inactive-first.
- **예상** [정성 예측]: TTFT p95 ~80 tick→≤1 tick, p50 pause ~12s→~1–2s(엔진 prefill만). P1 재역전 여부는 재런치로 검증(예측이지 보장 아님).

**다음 단계**: 교수님 방향 결정(A Pro6000 재현 / B 5090 정책수정 / C 부분종결) → faithful 재현 선택 시 **결함 1+2 함께 구현 → 격리·유닛 검증 → 최악셀 재검증 → 단일 재런치**(결과는 이 로그에 이어 기록). [GPU 후순위] MORI-a-only ablation으로 결함 2 단독 기여 분리.

---

## 11. 저동시성 진단 스윕 (MORI r2, C∈{2,4,8,10}) — oversub 곡선 접합  [측정, 2026-08-02]

원시: `scratch/mori/msw/results_msw_lowc.jsonl`(4셀, 각 1h, **fail% 0**, gate abort 없음). 목적: fit(8.1) 주변·아래 저압박 공백 메움. oversub=C/8.1.

| C | oversub | out tok/s | TTFT p50 | TTFT p95 | steady_turns | compl/steady_prog | util% mean/med |
|---|---|---|---|---|---|---|---|
| 2 | 0.25× | 2.95 | 0.59 | 1.66 | 98 | 6/3 | 7/0 |
| 4 | 0.49× | 9.06 | 0.65 | 2.34 | 563 | 25/20 | 24/0 |
| 8 | 0.99× | 21.13 | 0.80 | 2.89 | 1286 | 53/42 | 53/94 |
| 10 | 1.23× | 23.65 | 0.95 | 4.25 | 1474 | 63/47 | 59/99 |
| 20 | 2.47× | 22.2 | 2.1 | — | 1412 | — | (M-SWP §1) |
| 50 | 6.17× | 11.8 | 5.0 | — | 834 | — | (M-SWP §1) |
| 80 | 9.88× | 6.5 | 13.9 | — | 520 | — | (M-SWP §1) |

**해석**:
- **(a) oversub ≤ 1 (C≤8): MORI 정상·경쟁력.** TTFT p50 sub-초(0.59/0.65/0.80s), throughput 선형 증가(2.95→9.06→21.13), GPU util 7→53%(미포화). free slot이 있어 **굶음 없음**.
- **(b) 열화 시작 = oversub ~1.2× (C=10).** TTFT **p95가 첫 급등**(C8 2.89→C10 4.25), p50는 C=20(oversub 2.47×)서 2배(0.95→2.1). throughput은 **C=10~20서 정점(~23~24) 후 꺾임**.
- **(c) 붕괴 = oversub ≥ 2.5× (C≥20).** throughput 22.2→11.8→6.5, TTFT p50 2.1→5.0→13.9.
- **임계점**: free slot이 사라지는 **oversub≈1(C≈8~10)부터 결함 1(ι-정렬+5s tick 굶음)이 발동 시작**, oversub↑에 심화 → §7 진단과 정합("저압박 무해, 압박서 굶음"). 대조: 저C util 낮음(미포화)인데 고C(C80) util 90%(churn, §8) → **MORI는 저압박 효율적 / 고압박 낭비**.

**소표본 신뢰도**: C=2는 completed 6 / steady_prog 3 / turns 98 → 절대 throughput(2.95)은 **'미포화'(2워커·idle-heavy)**이지 열화 아님; TTFT(n=98) 추세는 유효. C=4(25/563)~C=10(63/1474)은 표본 충분. throughput이 C↑에 오르는 건 저압박 미포화 해소일 뿐(정점 C10~20).

---

> 상태: 1런 패스 + 정량 진단(결함 1·2) + 수정설계 + **저동시성 곡선(§11)** 완료·정지. **GPU 유휴, 코드 무수정.** rootcause·regime-match 로그를 본 로그로 통합(중복 제거). 구현/재런치는 방향 결정 후 승인 시.
