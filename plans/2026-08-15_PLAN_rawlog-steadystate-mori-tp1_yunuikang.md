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
> - `logs/2026-08-15_tracelab_trace_structure_yunuikang.md` — **트레이스 조사**: session=program 2단(program_id 없음)·KV는 세션 내 턴간 누적·driver 이미 세션 closed-loop·timestamp 없음·30분드롭=세션9.5%/시간46%·per-turn median 32,376
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

Track M의 windowing·cap은 **유지**(context 물리한계상 필수)하되, 추가로 30분↑ 세션을 드롭한다. fit32k식 "컨텍스트 초과 세션 드롭"(selection bias)은 하지 않는다.

```
베이스 = Track M primary (turn-window L=64k · tool cap 300s · s_ctx median 32,376)
   ※ 원본 full은 per-turn input median 124k → 모델 context 71,680 초과 → windowing 물리적 필수
     (human-wait는 Track M 유지 = idleness 연구대상, 30분↑만 아래서 드롭)
 → (필터) 세션 wall ≥ 30분(1800s)인 세션 전체 제거   [session=program 1:1]
 → 세션 내부는 자르지 않음 (세션 내 턴 간 KV 누적 보존)
 → 산출: tracelab_rawfilt_yunuikang.jsonl + 필터 통계(보존율·s_ctx·wall 분포)
```

- **세션이 KV-locality 단위**: 세션 안에서 턴을 거치며 context가 연속 누적된다(트레이스 실측: input_tokens 단조 증가). 내부를 자르면 구조가 깨진다 → **세션째 드롭**.
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

### 4.1 자연 fit 개략치 (7B · s_ctx≈32,376[측정] · **기동 시 필터 후 재확정**)

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

### 5.2 드라이버 — concurrency는 이미 세션 단위 (변경 불필요)

트레이스 조사로 확인: **기존 `mori_replay_driver`가 이미 세션 단위 closed-loop**이다 — C개 영속 워커가 각각 세션 하나를 끝까지(턴 순차) 돌린 뒤 다음 세션을 뽑는다. 트레이스는 session=program 1:1, KV는 세션 내 **턴 간** 연속 누적. → **concurrency 단위 변경 불필요.**

신규로 필요한 것은 concurrency가 아니라:
- (a) 30분-드롭 필터 trace (§3)
- (b) raw 상시로깅 훅 (§6)
- (c) `deadline_grace_s` 상향/해제 — 30분 드롭으로 세션이 이미 ≤30분이므로 즉시취소(현재 45s) 방지
- driver의 `program_id = session#cycle`은 **세션 replay 인스턴스** id일 뿐(세션 내 하위 program 아님)

### 5.3 런 길이 · steady state

- **셀당 6–8h**: warmup ~30–40min(앞 20% 제외) + 측정 창 ~5.5–7h. steady 판정은 offline(steplog throughput·KV-usage plateau).
- **5090(goguma6)·Pro6000(nutella)는 서버가 달라 동시 실행.** 각 서버가 자기 GPU의 3셀을 순차로.
- **서버당 3셀 × 6–8h ≈ 18–24h**, 두 서버 병행 → 전체 ~하루+.
- 첫 셀을 캘리브레이션 겸용(warmup 길이·창 위치 민감도).
- `deadline_grace_s` 상향/해제(§5.2c) — 30분 드롭으로 세션 ≤30분이라 완주 가능하게.
- n=1(런 1회), 분산은 §7 window 분할.

---

## 6. ★ Raw-event 스키마 (중심 산출물 — 돌리기 전 확정 대상)

**최신·확정 스키마는 별도 문서**: `plans/2026-08-16_SCHEMA_rawlog_yunuikang.md`. 6개 파일 — `run_meta.json` · `requests.jsonl` · `events.jsonl` · `kv_events.jsonl` · `snapshots.jsonl` · `gpu.jsonl`.

핵심 규약(트레이스 조사 반영):
- **driver 단조시계 단일**(run origin 0.0s), server값은 duration. (트레이스에 timestamp 없음 → 이게 유일 시간원)
- join 키 `(session_idx, cycle, turn)` — **program 하위레이어 없음**(session=program 1:1). driver `program_id=session#cycle`은 세션 replay 인스턴스.
- `cached_tokens`는 트레이스값이 아니라 **엔진 replay 시점 prefix-hit**을 로깅(트레이스 cached_tokens 미사용 확인).
- **`context_truncate` 이벤트 로깅** — driver `--ctx-cap` trim이 실제로 자르므로 재생 KV 곡선 추적에 필요.
- recompute는 step log 없이 `cached_tokens`+`kv_tokens_end` 궤적 + kv_events(evict/reload)로 offline 재구성, snapshot 누적카운터로 교차검증.

신규 로깅 모듈 `scheduler/mori_rawlog_yunuikang.py` — 기존 MORI_TIERC monkeypatch를 상시-on 로거로 확장(원본·baseline 0-diff 유지).

---

## 7. Offline 후처리로 뽑을 통계 (재실행 없이)

| 산출 | 입력 stream | 방법 |
|---|---|---|
| **steady-state 구간** | ③ | throughput·kv_usage plateau 자동탐지, warmup 20% 후 |
| **분산(반복 대체)** | ③②| steady를 K개 sub-window로 분할 → 각 지표 분포·CI (부트스트랩) |
| **GPU 시간예산** | ③ | decode/prefill-new/recompute/idle 분해 (C별 추세) |
| goodput@**임의 SLO** · TTFT p50/p95 | ②③ | 사후 SLO 대입 |
| prefix hit · recompute율 · reload량 | ②④ | 누적/이벤트 재집계 |
| **세션(session#cycle)별 분해** | ② | context 누적 단위가 세션이므로 |
| MORI **tier 동역학** | ② | 점유 시계열 · move rate · ι 분포 |
| 5090 vs Pro6000 | 전체 | 동일 파이프라인 비교(둘 다 TP1) |

---

## 8. 결정 / 확인 항목 (승인 게이트)

| # | 항목 | 기본안 |
|---|---|---|
| 1 | **program-wall cut 임계** | ✅ **결정: 30분 일괄.** human-wait 세션은 wall이 길어 자동 포함(별도 T_hw 없음) |
| 2 | **s_ctx 정의** | ✅ **제안 채택: per-turn 누적 context(input_tokens) median.** 세션 peak 분포 병기, 필터 후 재계산 |
| 3 | **세션 계층** | ✅ **확정: session=program 2단**(트레이스 조사). driver가 이미 세션 closed-loop → concurrency 변경 불필요 |
| 4 | **Pro6000 `max-num-seqs`** | ✅ **결정: 상향.** C=4fit(~166)이 상한에 안 걸리게(캡 아님, in-flight 상한만) |
| 5 | **런 길이** | ✅ **셀당 6–8h**(warmup ~30–40min + 측정 ~5.5–7h). 5090·Pro6000 서버 병행. 서버당 3셀 ≈ 18–24h · deadline_grace 상향 |
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
