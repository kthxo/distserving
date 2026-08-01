# MORI 역전 정량 root-cause 분석 + 수정 계획 (설계, 구현 전)

> 작성 2026-08-01 · 브랜치 `mori` · HEAD `b311273` · 서버 goguma6(RTX 5090 ×2, SGLang 0.5.10+HiCache, YaRN 64k)
> 원시 데이터: `scratch/mori/msw/results_msw.jsonl`(18셀) · `scratch/mori/msw/serve_mori_r{1,2}.log`(엔진 prefill 처리량) · Track M 트레이스 `scratch/traces/tracelab_moriM_L64k_yunuikang.jsonl`
> **측정 vs 추론 vs 논문**을 라벨로 구분. 논문 수치는 `plans/2026-07-30_PLAN_mori-on-thunderagent_yunuikang.md §D-5`가 인용한 값(**PDF 재검증 안 함 → 논문-인용**). ProfileState(--profile)는 스윕에서 **미실행** → pause/prefill 분해는 **추론**.
> 문제: M-SWP에서 MORI < TA+O (P1 역방향, C80·r2 throughput 0.45×·TTFT p50 4.1×).

---

## A. 압박 레짐 정량화 — 우리 vs 논문

### A-1. 우리 (goguma6) [측정]
- KV 풀(device) = **262,144 tok**(pin, 실측 `max_total_num_tokens`). Track M 컨텍스트 **median 32,376 / peak 65,536 tok**(실측).
- **fit = 풀 / 컨텍스트**: median → **8.10**, peak → **4.00**.
- **oversubscription = C / fit**:

| C | oversub(fit median 8.1) | oversub(fit peak 4.0) |
|---|---|---|
| 20 | 2.5× | 5.0× |
| 50 | 6.2× | 12.5× |
| **80** | **9.9×** | **20.0×** |

- **유효 압박(idle-heavy 보정)** [추정]: Track M 세션 ι mean=0.517(prep meta) → 순간 reasoning 비율 ≈0.48 → C=80 유효 동시 GPU 수요 ≈38 vs device slot ≈8(fit median) → **유효 oversub ≈4.7×**(추정). 즉 idle-heavy를 감안해도 **승격 경로에 항상 pending이 free slot의 수 배 쌓임**.
- host tier: r1=524,288 / r2=786,432 tok. **단 host↔device reload가 SYS/PCIe(NVLink 없음)로 느려**, 라우터의 GPU admission은 device 262k 기준으로 걸림(host는 재계산 회피용).

### A-2. 논문 [논문-인용 + 추정]
- 구성: H200 80GB 급(base 계획서 §A-4: "H200(80GB)로 H100-class emulate"). 정확한 KV 풀·모델 B_tok은 **PDF 재검증 안 함 → 추정**: 80GB − weights(~14GB) ≈ 66GB KV. 논문 컨텍스트 ~32K(§2.1 언급, 추정). → **논문 fit·oversub은 불확실**(정량 단정 회피).
- **로버스트 경험 증거(측정 대조)**: 논문 baseline throughput(§D-5 인용) — C=20 MORI 546 / TA+O 534 tok/s, B200 1× 시리즈 147→181→189 tok/s(수백 tok/s대, **붕괴 아님**). **우리**(측정): C=80 MORI r2 **6.5** / TA+O r2 **14.3** tok/s(한 자릿수). → **출력이 ~10–30× 낮음**.
- 이 격차는 HW(5090 vs H200/B200)·클라이언트 병목도 섞여 있어 "regime N×"로 단정하지 않는다. **정량 주장은 fit-기반 oversub(A-1)**, throughput 대조는 **정성 corroboration**.

### A-3. 결론(수치)
- **우리 C=80 oversub = 9.9×(fit median) / 20×(peak) / ~4.7×(유효, 추정).** 논문은 C=20을 "겨우 fit"으로 사이징(§A-4) → 논문 대비 우리가 **명백히 더 빡센 초과구독 레짐**(fit 대조 + baseline throughput 한 자릿수 둘 다로 뒷받침).

---

## B. 정량적 root-cause 체인 (숫자로 연결)

**① 극단 oversubscription → free slot 극소** [측정→계산]
C=80 device fit 8.1 → 상주 ≈8, pending(요청 도착·demote됨) 다수 → 한 승격 라운드의 free slot ≈0–few.

**② 승격이 pending을 ι 오름차순 정렬 → 높은-ι가 매 라운드 뒤로** [코드]
`MoriRouter._mori_promote`(`mori_router.py:274`)는 `cpu_pending`을 **ι ascending** 정렬. 방금 긴 툴콜 끝낸(=windowed-ι 높은) pending이 **매 라운드 리스트 꼬리** → free slot 부족(①)과 겹쳐 **굶음**.

**③ 굶음 정량화** [측정→교차검증]
관측 TTFT **p95 = 398s(MORI r2 C80) / 564s(r1 C80)**(results_msw.jsonl), tick=5s → **≈80 / 113 라운드 대기**. 이는 "높은-ι pending이 ~80라운드 뒤로 밀렸다"(②)와 **정합**.

**④ tick 5s 기여** [코드]
승격은 `_scheduler_loop`(`router.py:746-753`)의 `sleep(5s)` 루프에서만(event-driven 아님) → 모든 재개에 **최소 ~1 tick** + ③의 굶음. 도착 즉시 승격 경로 없음.

**⑤ TTFT 분해 = pause 지배** [추론; --profile 미실행]
- 엔진 prefill 처리량 **~5,000 tok/s**(serve_mori_r2.log 실측: 4920–7141 tok/s 대). cacheHit(MORI r2 C80) **78%**(측정) → 재개 요청 uncached ≈0.22×32k ≈7k tok → prefill ≈**1.4s** + first decode ≈0 → **backend TTFT ≈1–2s**(추론).
- 관측 TTFT p50 **13.9s** → **pause ≈ 12.4s**(추론). p95 398s → **거의 전부 pause**(추론). → **TTFT는 승격 대기(pause)가 지배**, prefill/reload 아님.

**⑥ 대조: TA+O** [측정]
TA+O r2 C80 TTFT p50 **3.4s**(cacheHit 87%, backend TTFT ~1s 추론 → pause ~2.4s). → **승격-대기 오버헤드 = MORI − TA+O ≈ 10s(p50) / 278s(p95)**. TA+O는 tr 라우터가 admission만 하고 **엔진이 on-demand reload를 투명 처리**(라우터가 개별 요청을 CPU tier로 재-block하지 않음) → 굶음 없음.

**정리(한 문단)**: 우리 레짐은 논문 대비 훨씬 빡센 초과구독(C=80 oversub 9.9×, 유효 ~4.7×)이라 승격 라운드마다 free slot이 극소다(①). 논문에도 있는 **ι-정렬 승격**(②)이 이 slot 기근과 겹치면서, 방금 활성화된 높은-ι pending이 **~80라운드(p95 398s÷5s) 굶었다**(③). 물려받은 **5s tick**(④)은 event-driven 승격 부재로 이를 악화. cacheHit 78%로 엔진 prefill은 ~1–2s에 불과한데(⑤) 관측 TTFT p50 13.9s → **대부분이 승격 대기**이고, 같은 엔진의 TA+O는 3.4s(⑥) → 격차 ≈10s가 곧 MORI 승격-대기 오버헤드다. **원인은 typed eviction/엔진이 아니라 라우터 승격 정책(ι-정렬 + tick).**

---

## C. 수정 계획 (설계만; 구현·GPU 전 정지)

### C-1. 설계 원칙 (논문 §4.3.1 복원 + 우리 레짐 적응)
1. **Pending 최상위 + 굶음 제거**: pending(툴콜 끝나 추론 대기)은 승격 최상위 레벨. **극단 압박에서 pending은 ι가 아니라 "대기시간/ready" 우선**(가장 오래 기다린 것 먼저 = FIFO/aging) → ②의 높은-ι 굶음 제거. **ι는 non-pending 배치 결정에만** 사용(논문 §4.3.1의 "각 레벨 내 ι" 취지는 유지하되, pending 레벨은 aging 우선).
2. **Event-driven 승격**: `update_program_before_request`에서 demote 감지 시 tick을 기다리지 않고 즉시 승격 시도 — `remaining_capacity ≥ total_tokens+BUFFER`이면 그 자리에서 register+`waiting_event.set()`.
3. **Make-room**: 자리 부족 시 GPU 내 **최고-ι 프로그램을 demote**해 확보 — 단 **pending·방금-활성 프로그램은 demote 금지** + `min_dwell_ticks`(sticky)로 ping-pong 방지.
4. **tick 유지**: 주기 tick은 **rebalance 안전망**으로 존치(간격 5s→1–2s 검토; event-driven이 주 경로이므로 tick은 보조).
5. **격리**: `--router tr|default`(baseline) 경로 무손상 — 변경은 `MoriRouter` 내부에만.

### C-2. 의사코드 (event-driven 승격, MoriRouter)
```
async def update_program_before_request(pid, state, payload):
    now=time.time(); update idle_window(push_acting)      # 기존
    if state.tier in ("cpu","waiting"):                    # demote 상태 = 재개 필요
        async with pause_resume_lock:
            b = best_backend_with_capacity(state.total_tokens+BUFFER)
            if b is None:                                  # make-room
                victim = highest_iota_resident(excluding pending/just-active, dwell_ok)
                if victim and iota(victim) > iota(state):  # 이 요청보다 더 idle할 때만
                    demote(victim); b = its_backend
            if b is not None:
                promote(pid, state, b)                     # register + waiting_event.set()  (즉시)
            # else: fall through → 기존 _wait_for_resume (tick 폴백, 드묾)
    rv = await super().update_program_before_request(...)  # (여기서 event set됐으면 즉시 통과)
    ...
# _mori_promote(tick): pending은 aging(대기시간) 우선 정렬, non-pending만 ι 정렬
#   cpu_pending.sort(key=lambda s: s.waiting_since)   # ι 아님 (굶음 제거)
#   cpu_idle/wait_*.sort(key=iota)
```

### C-3. 파일별 diff 계획 (예상)
- `scheduler/mori_router.py`: (a) `update_program_before_request`에 event-driven 승격 블록 추가(~25L), (b) `_mori_promote`의 cpu_pending 정렬키를 ι→`waiting_since`(aging)로, non-pending은 ι 유지(~5L), (c) make-room 헬퍼(최고-ι victim, pending/dwell 제외)(~15L). `Program`에 `waiting_since`(demote 시각) 필드 추가 → `program/state.py` +1L.
- `router.py`·`backend/state.py`·baseline: **무수정**(격리 유지).
- 테스트: `tests/test_mori_invariants` 확장 — (i) 용량 있으면 도착 시 즉시 promote(tick 불필요), (ii) pending은 aging 우선(높은-ι pending이 낮은-ι보다 먼저), (iii) make-room이 pending/방금활성 demote 안 함.

### C-4. 예상 효과 [정성 예측]
- 재개가 event-driven → **TTFT p95가 ~80 tick(398s)에서 ~0–1 tick(≤5s, 대개 즉시)로** 축소 예상(굶음 제거 + tick 대기 제거). p50도 pause ~12s→~1–2s(엔진 prefill만) 접근 예상.
- throughput은 재개 지연 해소로 상승 예상. **P1(MORI vs TA+O) 재역전 여부는 재런치로 검증**(예측이지 보장 아님). typed eviction의 부차 효과(cacheHit 78 vs 87%)는 MORI-a-only ablation으로 별도 확인.

---

> 상태: 분석·설계 완료. **구현·GPU 없음.** 리뷰 후 승인 시 C-2/C-3 구현 → 격리·유닛 검증 → 재검증(최악셀) → 재런치. (동일 M-SWP 실험의 후속 재런치 결과는 이 실험 로그 계열에 이어 기록.)
