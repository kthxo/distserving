# 연구 계획 — MORI raw-event 상시로깅 · steady-state · TP1 단일 GPU (5090 / Pro6000)

> 작성: 강윤의 · 브랜치 `mori` · **2026-08-15** · **계획만(코드·trace·GPU 무수정, 승인 후 진행)**
> 저장소 `/home/yunuikang/yunuikang_work/distserving` · 서버 **goguma6(5090)** · **nutella(Pro6000)**
> 지시 출처: 김태현 연구원 (2026-08-14~15 카톡) — *"steady state를 찾고, raw event를 다 저장해 offline 후처리로 통계를 뽑자. 여러 번 안 돌려도 되게."*
> 선행 권위 문서(계승):
> - `logs/2026-08-08_5090-TP1-7B_TIERC_yunuikang.md` — 5090 TP1 자연 KV풀 247,297 tok · 시간분해 계측(MORI_TIERC) · 러너 버그 3건 수정
> - `logs/2026-08-08_TIERC_H200_followup_yunuikang.md` — Phase2↔TierC 비재현(±14% 변동) · window 5분컷 요동 → **반복셀 필요 근거**
> - `logs/2026-08-08_5090-vs-H200_ENV_DIFF_yunuikang.md` — 통제/미통제 축 카탈로그 · 데이터셋·드라이버·엔진 통제 규약
> - `logs/2026-08-08_H200_ANALYSIS_yunuikang.md` §6.3 — 다음 단계 후보 · n=1 한계
> - `plans/2026-07-30_PLAN_mori-on-thunderagent-goguma6_yunuikang.md` — MORI 3-tier·ι 정의·serve/driver 구조
>
> **원칙: baseline(SMG/TA/TA+O) 경로·원본 trace·기존 스크립트 무수정. 신규 파일 전부 `*_yunuikang`. GPU는 각 서버 지정 인덱스만. MORI 단독·TP1 단일 GPU. 본 턴은 계획 생성 외 무수정.**

---

## 0. 한 문단 요약

직전까지의 문제는 **n=1 · run 변동 ~15%** 때문에 concurrency별 경향이 run마다 뒤집혀(Phase2 C80 +14.2% ↔ TierC +2.4%, C20은 부호 반전) *"MORI가 이긴다/특정 패턴이 있다"* 를 **판정할 수 없다**는 것이었다. 김태현님 지시는 접근을 바꾼다: **짧게 여러 번 대신, 길게 한 번 돌려 steady state에 도달시키고, 가장 raw한 event를 전부 저장**한 뒤 통계는 **offline 후처리**로 뽑는다. 이러면 ① steady window를 여러 조각으로 잘라 **재실행 없이 분산**을 얻고, ② 새 지표가 필요하면 **재실행 없이 재계산**한다. 이번 배치는 **MORI 단독**을, **TP1 단일 GPU**(TP/인터커넥트 교란 제거)로, **5090과 Pro6000 각각의 자연 상황**에서, **fit 기반 세션-단위 concurrency**(C=fit·2fit·4fit, r=2)로 돌려 **각 (GPU × 압박) 상황을 있는 그대로 특성화**한다. **cap을 걸어 fit을 정렬하지 않는다** — 각 하드웨어의 자연 fit이 그 상황의 일부이기 때문. 본 계획의 중심 산출물은 **§6 raw-event 스키마**이며, 돌리기 전 이 스키마를 김태현님께 확정받는다.

### 0.1 이 계획이 답하려는 것 (판정이 아니라 특성화)

| # | 질문 | 어떻게 |
|---|---|---|
| Q1 | MORI의 **steady state**는 어디서 시작하고 어떤 값으로 안정되나 | steplog plateau 자동판정 |
| Q2 | 같은 계측을 **window로 쪼개면 분산이 얼마**인가 (반복 대체 가능한가) | steady window K분할 부트스트랩 |
| Q3 | **GPU 시간예산**(decode/prefill-new/recompute/idle)이 압박(C)에 따라 어떻게 변하나 | steplog 분해 |
| Q4 | **5090 vs Pro6000**(둘 다 TP1) — GPU 세대만 달랐을 때 위 값들이 어떻게 다른가 | 두 머신 동일 파이프라인 |
| Q5 | MORI **tier 동역학**(GPU/CPU/Waiting 점유, move rate, ι 분포)의 시계열 | events 스트림 |

> ⚠️ baseline이 없으므로 이 배치는 **MORI 내부 특성화**만 낸다. "MORI vs TA+O 델타"는 이 배치의 산출이 아니다(필요 시 동일 파이프라인으로 후속 baseline 배치). 이는 지시("각 상황을 분석")와 부합한다.

---

## 1. 배경 — 왜 접근을 바꾸나 [측정 근거]

| 확정 사실 | 근거 |
|---|---|
| Phase2(3600s)와 TierC(1500s)의 goodput 비가 **재현 안 됨**: C20 1.074→**0.928**(부호반전) · C80 1.142→**1.024** | `TIERC_H200_followup` STEP3 |
| C80 창을 5분씩 자르면 0.700/0.803/0.929/**1.539**/0.967 로 **비단조 요동** → duration이 아니라 **변동**이 주원인 | 〃 |
| goodput과 engine thr이 같은 크기로 함께 움직임 → **지표 정의 문제 아님** | 〃 |
| 반복셀(같은 격자 3회+)이 있어야 판정 가능 — 그러나 반복은 GPU 시간 비쌈 | `H200_ANALYSIS` §6.3 |
| 시간분해 계측(MORI_TIERC)은 **원본·baseline 0-diff** 로 이미 검증됨 → 상시 로깅으로 확장 가능 | `5090-TP1-7B_TIERC` §0 |

**전환:** 반복셀(비쌈) 대신 **long run 1회 + steady window 분할**로 분산을 얻고, **raw 상시로깅**으로 재실행을 없앤다.

---

## 2. 실험 환경

### 2.1 하드웨어 — 둘 다 TP1 단일 GPU

| 항목 | **Machine A — 5090** | **Machine B — Pro6000** | 확인 |
|---|---|---|---|
| 서버 | goguma6 | nutella | |
| GPU | **RTX 5090 ×1** (`CUDA_VISIBLE_DEVICES=0`) | **RTX PRO 6000 Blackwell Max-Q 96GB ×1** (`=1`) | GPU0=타 사용자 미접촉 |
| HBM (usable) | 31.84 GiB [측정] | ≈95.5 GiB [추정] | 기동 로그 재확인 |
| TP / 인터커넥트 | **TP1 · all-reduce 없음** | **TP1 · all-reduce 없음** | ✅ 교란 제거 |
| GPU↔NUMA | node-local (단일 GPU) | node-local | `topo -m` |
| CPU DRAM | 188 GiB / 185 avail [측정] | 251 GiB / 231 avail [측정, 선행문서] | `free -g` 재확인 |
| 드라이버/CUDA | 580.82.07 / 13.0 | 재확인 | |

> **왜 TP1인가:** 붕괴(0.45×)가 TP2 셀에서만 나온 소거 결과([5090-TP1-7B_TIERC] §0·§4)를 이어, 이번엔 **TP를 아예 빼서** 인터커넥트 교란 없이 각 GPU를 특성화한다. 5090 vs Pro6000 차이는 **순수 GPU 세대**로 귀속된다.

### 2.2 소프트웨어 / 모델 — 두 머신 통일

| 항목 | 값 | 비고 |
|---|---|---|
| 엔진 | **SGLang 0.5.10 + HiCache** | Pro6000 기동 스모크 필요(sm_120 동일 계열) |
| attention / sampling | triton / pytorch | ENV_DIFF 규약 |
| **모델** | **Qwen2.5-7B-Instruct** | 결정됨 |
| weights / KV밀도 | 14.19 GiB / **56 KiB/tok** (28L·4KV·128, bf16) | |
| context-length | **71,680** (YaRN 2.1875 × 32,768) | |
| GPU KV 풀 | **자연값(캡 없음)** | ★ cap 안 함 — §4 |
| 오프로딩(CPU tier) | HiCache `--hicache-ratio 2` (r=2) | 아래 §4 |
| MORI 파라미터 | k=5 · tick 5.0s · min_dwell 1 · default_iota 0.5 · reload_bw(µbench 보정) | `mori_config.py` |

> **cap 안 하는 이유(지시 반영):** *"각각의 상황을 있는 그대로 분석"* 하려는 것이므로, Pro6000의 큰 HBM→큰 fit도 그 상황의 일부다. fit 정렬용 `--max-total-tokens` 캡은 **쓰지 않는다.** GPU KV 풀 = 기동 시 SGLang이 프로파일한 자연 최대값.

---

## 3. 트레이스 전처리 — 세션째 제거 (신규, Track M과 다른 철학)

Track M은 turn-window 슬라이스 + human-wait 주입 + 300s cap으로 **가공**했다. 이번엔 **가공 없이 세션째 제거**해 남는 세션을 raw하게 둔다.

```
원본 TraceLab full
 → (필터) 세션 내 어떤 program이라도 wall ≥ 30분 → 그 세션 전체 제거
          (human-wait가 긴 program은 wall이 길어 이 규칙에 자동 포함 — 별도 임계 불필요)
 → 세션 내부는 자르지 않음 (program→program KV 누적 보존)
 → 산출: tracelab_rawfilt_yunuikang.jsonl + 세션별 (program 경계·누적 ctx) 메타
```

- **세션이 KV-locality 단위**: 세션 안에서 이전 program의 context가 다음 program KV로 누적된다(김태현님 지시). 그래서 내부를 자르면 구조가 깨진다 → **세션째 드롭**.
- 프리처리 산출 통계를 로그로 남긴다: 제거 전/후 세션·program·turn 수, 보존율, 세션 peak 누적 ctx 분포, human-wait 분포.
- 신규 스크립트 `scripts/prep_tracelab_rawfilt_yunuikang.py` (원본 trace·기존 prep 무수정).

**결정됨:** 30분 program-wall cut 하나로 일괄. human-wait 세션은 wall이 길어 자동 포함(별도 T_hw 없음).

---

## 4. Concurrency — fit 기반 · 세션 단위

concurrency가 **세션 단위**이지만, 임의 시점에 GPU가 실제로 물고 있는 것은 각 세션의 **현재 누적 context**다. steady state에서 *"C=fit이 GPU를 채운다"* 가 성립하려면 분모는 **활동중 세션이 한 순간 점유하는 대표 KV** = per-turn 누적 context(=input_tokens)의 median이어야 한다 (세션 peak는 과대추정 → fit 과소 → 압박 부족). 기존 프로젝트 `FIT_DEN=32,376`과도 연속적이다.

```
C_gpu = GPU KV 풀 [tok]                          ← 기동 로그 실측 (캡 없음)
s_ctx = per-turn 누적 context(=input_tokens) median [tok]  ← §3 필터된 trace에서 재계산
                                                   (세션 peak 분포도 함께 기록 → offline 재산정 가능)
fit   = C_gpu / s_ctx                            ← 한 순간 GPU에 들어가는 대표 세션 수
C ∈ {fit, 2·fit, 4·fit} 세션 (정수 반올림)
r = 2  → CPU tier(host) = 2 · C_gpu
```

**압박 사다리 (r=2):** GPU+CPU 총용량 = 3·C_gpu = 3·fit 세션
- **C=fit** → GPU에 딱 참 · oversub **1×** · 압박 없음
- **C=2fit** → CPU tier 필요 · oversub **2×** · GPU+CPU 안
- **C=4fit** → GPU+CPU(3fit) 초과 → Waiting 발생 · oversub **4×**

→ H200 Phase2(C 20/40/80 @ fit20, oversub 1/2/4×)와 같은 논리를 **각 GPU의 자연 fit 상대값**으로 재현.

### 4.1 자연 fit 개략치 (7B · s_ctx≈50k 가정 · **기동 시 확정**)

| GPU (TP1·7B) | C_gpu 자연 KV풀 | fit | C = fit / 2fit / 4fit | CPU tier(r2) DRAM | DRAM 여유 |
|---|---|---|---|---|---|
| **5090** | **247,297 tok** [측정] | **≈7.6** | **8 / 15 / 31** | ≈26 GiB | 185 avail ✅ |
| **Pro6000** | ≈1.34M tok [추정] | **≈41** | **41 / 83 / 166** | ≈143 GiB | 231 avail ✅ |

- 5090 자연풀 247,297은 [5090-TP1-7B_TIERC §5.6] 프로브 실측값(13.21 GiB KV).
- Pro6000은 [추정] — 95.5 GiB × mem-frac 0.90 − weights 14.19 → KV ≈ 71.6 GiB ÷ 56KiB ≈ 1.34M tok. **기동 로그 `max_total_num_tokens`로 확정.**
- s_ctx = per-turn input_tokens median (Track M 32,376 참고), **§3 필터 후 재계산**(placeholder 32k).
- **주의:** Pro6000 C=4fit≈166 세션은 `--max-num-seqs`·스케줄러 한도에 걸릴 수 있음 → 기동 시 상한 확인, `max-num-seqs` 상향(캡 아님, 동시 in-flight 상한만).

---

## 5. 실행 프로토콜

### 5.1 매트릭스 — 6 long run

```
{5090(goguma6, TP1), Pro6000(nutella, TP1)}
   × MORI
   × C ∈ {fit, 2·fit, 4·fit}      (세션 단위, r=2 고정)
= 6 runs
```

### 5.2 세션-단위 드라이버 (신규)

현재 `mori_replay_driver`는 C 워커가 **program** 순환. 세션 단위로 바꾼다:
- 동시 슬롯 C개 = **세션 C개** 동시 진행
- 세션 내부 program들은 **순차 실행**(이전 program KV 누적) → 세션이 스티키 배치 단위
- 세션 완주 → 슬롯에 새 세션 투입(무한 순환 + 사이클 셔플, 고유 세션 커버리지)
- 신규 파일 `scripts/mori_replay_driver_session_yunuikang.py` (기존 driver 무수정)

### 5.3 런 길이 · steady state

- warmup 앞 20% 제외. steady 판정은 **offline**(steplog throughput·KV-usage plateau 자동탐지).
- 길이 목표: steady 도달 + **window 분할용 충분 표본**(steady 구간에서 완주 세션 ≥ 수십, step ≥ 수만). GPU당 3런 → **각 서버 ~하루 안**.
- n=1(런 자체는 1회) — 분산은 §7 window 분할로.

---

## 6. ★ Raw-event 스키마 (중심 산출물 — 돌리기 전 확정 대상)

**설계 원칙:** ① pre-aggregation 금지 ② 모든 stream을 `(session_id, program_id, turn_id)` + `ts_mono_ns`(단조) + `ts_wall`로 join 가능 ③ **cached / new / recompute 토큰을 발생 시점에 분리 기록**(offline 복원 불가) ④ tier 이동을 토큰수와 함께 discrete event로 → KV tier 점유를 시간축으로 재구성 가능 ⑤ 빈도가 다른 stream 분리(step log 대용량).

신규 로깅 모듈 `scheduler/mori_rawlog_yunuikang.py` — 기존 MORI_TIERC monkeypatch를 상시-on 종합 로거로 확장(원본·baseline 0-diff 유지).

### 6.1 스트림 ①  `run_meta.json` (run당 1회)

HW(서버·GPU·TP·NUMA·DRAM·드라이버/CUDA) · 엔진/모델(SGLang ver·7B·KV밀도·context-length·YaRN) · **자연 KV풀·fit·r·오프로딩 config** · router=mori·MORI 파라미터(k·tick·iota·reload_bw·min_dwell) · trace 필터 파라미터(30분 program-wall)·s_ctx·C(세션) · **boot assert**(GPU풀·host tier·fit 정확 일치) · wall/mono epoch.

### 6.2 스트림 ②  `events.jsonl` (lifecycle · append-only)

공통: `ts_mono_ns, ts_wall, event_type, session_id, program_id, turn_id, gpu_id`

| event_type | payload |
|---|---|
| SESSION_ADMIT / SESSION_COMPLETE | program_count · accum_ctx_tokens(start/end) |
| PROGRAM_START / PROGRAM_END | ctx_tokens_at_start · num_turns |
| TURN_ARRIVE / TURN_ADMIT | input_tokens · queue_wait_s |
| PREFILL_START | **new_tokens · cached_tokens · recompute_tokens** |
| FIRST_TOKEN | ttft_s |
| TURN_COMPLETE | output_tokens · prefill_s · decode_s · pause_s · prefix_hit_tokens · recompute_tokens · gpu_id |
| TOOLCALL_START / TOOLCALL_END | duration_s · tool_type(human_wait/real) · is_longtail |
| TIER_TICK (MORI) | per active program: iota · tier(GPU/CPU/Waiting) · rank |
| TIER_MOVE (MORI) | from_tier→to_tier · tokens · reason |
| KV_EVICT / KV_RELOAD | program_id · tokens · tier · reload_s |
| PAUSE / RESUME | program_id · reason |

### 6.3 스트림 ③  `steps.parquet` (엔진 forward step마다 — 가장 raw한 GPU-time 단위)

`ts_mono_ns · step_idx · gpu_id · batch_size · num_prefill_tokens · prefill_new_tokens · prefill_recompute_tokens · num_decode_tokens · step_latency_s · kv_used_tokens · kv_total · kv_evictable · radix_cache_tokens · cum_cache_hit · cum_cache_miss`

→ 이 stream 하나로 offline에서 **decode/prefill-new/recompute/idle 시간예산 + steady-state 판정 + throughput 시계열** 전부 도출. (하루치 수백만 row → parquet + 회전.)

### 6.4 스트림 ④  `engine_snapshot.jsonl` (주기 ~1s)

`ts · num_running · num_waiting · num_paused · kv_usage_frac · radix_size · gen_throughput_inst · tier_occupancy(GPU/CPU/Waiting 프로그램수) · host_tier_bytes · 누적카운터(generation_tokens_total · prompt_tokens_total · cached_tokens_total · local_compute)`

### 6.5 스트림 ⑤  `gpu.jsonl` (nvidia-smi 샘플러 · GPU별 ~200ms–1s)

`ts · gpu_id · util% · mem_used_mib · power_w · sm_clock_mhz · mem_clock_mhz`

---

## 7. Offline 후처리로 뽑을 통계 (재실행 없이)

| 산출 | 입력 stream | 방법 |
|---|---|---|
| **steady-state 구간** | ③ | throughput·kv_usage plateau 자동탐지, warmup 20% 후 |
| **분산(반복 대체)** | ③②| steady를 K개 sub-window로 분할 → 각 지표 분포·CI (부트스트랩) |
| **GPU 시간예산** | ③ | decode/prefill-new/recompute/idle 분해 (C별 추세) |
| goodput@**임의 SLO** · TTFT p50/p95 | ②③ | 사후 SLO 대입 |
| prefix hit · recompute율 · reload량 | ②④ | 누적/이벤트 재집계 |
| **세션·program별 분해** | ② | context 누적 단위가 세션이므로 |
| MORI **tier 동역학** | ② | 점유 시계열 · move rate · ι 분포 |
| 5090 vs Pro6000 | 전체 | 동일 파이프라인 비교(둘 다 TP1) |

---

## 8. 결정 / 확인 항목 (승인 게이트)

| # | 항목 | 기본안 |
|---|---|---|
| 1 | **program-wall cut 임계** | ✅ **결정: 30분 일괄.** human-wait 세션은 wall이 길어 자동 포함(별도 T_hw 없음) |
| 2 | **s_ctx 정의** | ✅ **제안 채택: per-turn 누적 context(input_tokens) median.** 세션 peak 분포 병기, 필터 후 재계산 |
| 3 | **세션 계층 확인** | raw trace에 "세션 > program" 경계가 실재하는지 — 없으면 세션≡program 처리 or 재생성 → **GPU 서버 코드 조사 요청** |
| 4 | **Pro6000 `max-num-seqs`** | ✅ **결정: 상향.** C=4fit(~166)이 상한에 안 걸리게(캡 아님, in-flight 상한만) |
| 5 | **런 길이** | GPU당 3런, steady + window 충분수 기준으로 결정(~하루/서버) |
| 6 | **reload_bw µbench** | PCIe 마이크로벤치로 보정(placeholder 8.0e9 대체) |
| 7 | **step-log 회전** | parquet + 크기/시간 회전 정책 |

> **§6 스키마 확정이 진행의 전제** — 강윤의가 김태현님께 "무슨 정보 뽑을지" 보고 후 승인받고 실행.

---

## 9. 산출물 · 가드레일 · 재현

### 9.1 신규 파일 (전부 `*_yunuikang`, 기존 경로 무수정)

| 파일 | 내용 |
|---|---|
| `scripts/prep_tracelab_rawfilt_yunuikang.py` | §3 세션째 제거 프리처리 |
| `scripts/mori_replay_driver_session_yunuikang.py` | §5.2 세션-단위 드라이버 |
| `scheduler/mori_rawlog_yunuikang.py` | §6 5-stream 상시 로거(MORI_TIERC 확장) |
| `scripts/_serve_sglang_7b_tp1_{5090,pro6000}_mori_yunuikang.sh` | 단일 GPU serve(자연풀·r2) |
| `scripts/run_rawlog_matrix_yunuikang.sh` | 6런 러너(TierC 버그픽스 3건 반영) |
| `scripts/postprocess_rawlog_yunuikang.py` | §7 offline 통계 |
| `scratch/mori/rawlog_{5090,pro6000}/` | 원자료 5 stream |

### 9.2 가드레일

- baseline(SMG/TA/TA+O)·원본 trace·기존 driver/serve **무수정** — `git diff mori 기준 0줄` 기계 검증.
- MORI_TIERC 확장 로거는 **원본·baseline 0-diff** 재확인(선행 규약).
- 각 서버 지정 GPU 인덱스만. 타 사용자 GPU 미접촉.
- n=1 · window 분산 · GPU간 절대비교 caveat를 모든 산출에 명시.

### 9.3 검증 게이트 (기동 시)

boot assert: `GPU pool == 프로파일 자연값` · `host tier == r×pool` · `fit == pool/s_ctx` · closure C1~C4(busy≤wall · steplog 창 커버리지 · GPU busy÷forward host · 토큰 교차검증) 전 셀 PASS.

---

## 부록 A. fit 계산 근거 (기동 시 실측 대체)

```
B_tok(7B) = 2×28×4×128×2 = 57,344 B = 56 KiB/tok
s_ctx = per-turn 누적 context(input_tokens) median ≈ 32,376 tok (Track M 참고, 필터 후 재계산)
5090:    pool 247,297 tok(측정, 13.21 GiB) ÷ 32,376 ≈ fit 7.6  → C 8/15/31
Pro6000: pool ≈1.34M tok(추정) ÷ 32,376 ≈ fit 41   → C 41/83/166
CPU tier(r2) DRAM = 2 × pool × 56KiB :  5090 26 GiB / Pro6000 143 GiB
```
