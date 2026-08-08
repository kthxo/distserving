# 5090 실험 vs H200 실험 — 실험 환경 세팅 차이 정리

- 작성: 2026-08-08 · 브랜치 `mori` · **읽기 전용 정리. 새 실험 없음.**
- 대상 문서
  - **5090**: `logs/2026-07-31_M-SWP_1run_results_yunuikang.md` · `logs/2026-08-04_MORI_VERIFICATION_yunuikang.md` ·
    `logs/2026-08-05_MORI_PHASE2_C50-pivot_yunuikang.md` · `plans/2026-07-30_PLAN_mori-on-thunderagent-goguma6_yunuikang.md`
  - **H200**: `logs/2026-08-05_H200_PREREG_yunuikang.md` · `logs/2026-08-05_H200_RESULTS_yunuikang.md` ·
    `logs/2026-08-08_H200_ANALYSIS_yunuikang.md` · `plans/2026-08-04_PLAN_h200-rescale-reproduction_yunuikang.md` (rev4)
  - 서브 스크립트: `scripts/_serve_sglang_8b_tp2_mori_yunuikang.sh` (5090) ·
    `scripts/_serve_sglang_{7b,8b}_tp1_h200_mori_yunuikang.sh` (H200)
- 라벨: **[측정]** 문서·스크립트에서 직접 확인 · **[추론]** 해석

---

## 0. 한 눈 요약

| 축 | 5090 | H200 | 같나 |
|---|---|---|---|
| **데이터셋 (트레이스)** | Track M · 3,514세션 / 117,257턴 | **완전 동일** (재가공 없음) | ✅ |
| **드라이버·프로토콜** | `mori_replay_driver` · 1h 셀 · ctx-cap 69,632 | 동일 (7B F1만 30분) | ✅ (1건 예외) |
| **엔진** | SGLang 0.5.10 + HiCache | 동일 버전 | ✅ |
| **context-length** | 71,680 (YaRN) | 71,680 (YaRN, factor만 다름) | ✅ |
| **GPU / 병렬화** | RTX 5090 ×2 · **TP2** · SYS · cross-NUMA | H200 SXM ×1 · **TP1** · node-local | ❌ |
| **모델 / KV밀도** | Qwen3-8B / 144 KiB/tok | **Phase별로 다름** (7B 56 / 8B 144) | ⚠️ |
| **GPU KV 풀 (fit)** | 262,144 tok · **fit 8.10 고정 (조작 불가)** | `--max-total-tokens`로 **8.10 → 20 조작** | ❌ |
| **host DRAM** | 188 GiB (r=4에서 여유 38 GiB) | 컨테이너 1,026 GiB (사실상 무제약) | ❌ |
| **MORI 코드 버전** | M-SWP는 **A7c 수정 전** / Phase 2는 수정 후 | **전부 수정 후** | ⚠️ |
| **비교 시스템 수** | M-SWP 4종 / Phase 2 **2종** | Phase 1 **2종** / Phase 2 **4종** | ⚠️ |

**핵심 [추론]**: **데이터셋·드라이버·엔진·컨텍스트 길이는 완전히 통제**됐고, 달라진 것은
**① 하드웨어(GPU·TP·인터커넥트·DRAM) ② `fit` 조작 가능성 ③ 모델(Phase에 따라) ④ MORI 코드 버전(앵커 한정)** 이다.
계획서(rev4 §0.6)가 *"F1은 하드웨어만 다른 통제군이 아니었다"* 라고 스스로 정정한 것이 바로 ③ 때문이고,
④는 어느 H200 문서에도 명시돼 있지 않다 → **§7 주의사항**.

---

## 1. 하드웨어

| 항목 | **5090 (goguma6)** [측정] | **H200 (렌트 컨테이너)** [측정] |
|---|---|---|
| GPU | **RTX 5090 ×2** (sm_120 Blackwell) | **H200 SXM ×1** |
| HBM | 32 GB ×2 = 64 GB (**TP2 합산 63.7 GiB**) | **143,771 MiB = 140.40 GiB** |
| 병렬화 | **TP2** (`CUDA_VISIBLE_DEVICES=0,1`) | **TP1** — all-reduce 자체가 없음 |
| GPU 간 인터커넥트 | **SYS · NVLink 없음** · P2P peer access 미지원 → `--disable-custom-all-reduce` **필수** | 해당 없음 (1장) |
| GPU ↔ NUMA | **GPU0=NUMA0 · GPU1=NUMA1 → cross-NUMA** | **GPU0 = NUMA node 0** (cpu 0-55,112-167) · **node-local** |
| host 링크 | PCIe (SYS 경유, cross-NUMA 페널티) | PCIe 5.0 x16 (~63 GB/s 이론치 [추정]) |
| CPU | **32코어 · 2 NUMA** | 2 NUMA 노드 · node0만 cpu 0-55,112-167 (≥168 스레드) |
| host DRAM | **188 GiB** (185 avail, `free -g`) | **컨테이너 cgroup `memory.max` = 1,026 GiB** |
| 드라이버 / CUDA | **580.82.07 / 13.0** | **580.159.03 / 13.0** |
| 실행 환경 | 베어 서버 | **unprivileged 컨테이너** — `numactl --membind`가 `set_mempolicy` EPERM으로 **철회됨** (H200 PREREG §D.1) |

> ⚠️ H200 PREREG가 스스로 정정한 항목: `free -g`의 3,023 GiB는 **호스트 전체 값**이라 쓰지 않고,
> cgroup 한도 1,026 GiB만 근거로 삼았다 [측정].

**[추론] 하드웨어 차이가 만든 것**: 5090의 `fit=8.10`은 HBM 32 GB에 **못박힌 값**이라 원리적으로 못 움직였다.
H200은 HBM이 4.4배라 `--max-total-tokens`로 fit을 연속 조작할 수 있고, 이것이 H200으로 간 **유일한 이유**다
(계획 §1.1: *"H200은 '더 좋은 GPU'로 쓰는 게 아니라 fit을 움직일 수 있는 유일한 장비로 쓴다"*).

---

## 2. 소프트웨어 스택

| 항목 | 5090 [측정] | H200 [측정] | 같나 |
|---|---|---|---|
| 엔진 | **SGLang 0.5.10 + HiCache** | **SGLang 0.5.10** | ✅ |
| torch | **2.9.1+cu130** | **2.9.1+cu128** | ⚠️ CUDA 빌드만 다름 |
| transformers | (미기록) | **5.3.0** | — |
| 기타 | sgl_kernel 0.4.1 · flashinfer 0.6.7 · 별도 venv `.venv-sglang` | — | — |
| attention backend | **triton** | **triton** | ✅ |
| sampling backend | pytorch | pytorch | ✅ |
| `--mem-fraction-static` | **0.85** | **0.90** (단일 GPU 여유) | ❌ |
| `--disable-custom-all-reduce` | **필수** (SYS P2P 미지원) | **불필요** (TP1) | ❌ |
| 빌드 env | `CUDA_HOME=/usr/local/cuda-13.0` · `CC=gcc-11` · `NVCC_PREPEND_FLAGS=-ccbin g++-11` **필요** | 불필요 | ❌ |
| YaRN 오버라이드 키 | `rope_parameters` | `rope_parameters` (transformers 5.3.0, `rope_scaling` 폴백 준비) | ✅ |

---

## 3. 모델 — **여기가 가장 헷갈리는 축**

| | **5090 전체** | **H200 Phase 1 (7B)** | **H200 Phase 1 (8B 재실행)** | **H200 Phase 2** |
|---|---|---|---|---|
| 모델 | **Qwen3-8B** | Qwen2.5-7B-Instruct | **Qwen3-8B** | Qwen2.5-7B-Instruct |
| 레이어 / kv헤드 / head_dim | 36 / 8 / 128 | 28 / 4 / 128 | 36 / 8 / 128 | 28 / 4 / 128 |
| **per-tok KV (bf16)** | **144 KiB** | **56 KiB** | **144 KiB** | **56 KiB** |
| weights | 15.26 GiB (TP2 분산) | 14.19 GiB | 15.26 GiB | 14.19 GiB |
| YaRN factor × base | **1.75 × 40,960** | **2.1875 × 32,768** | 1.75 × 40,960 | 2.1875 × 32,768 |
| **최종 context-length** | **71,680** | **71,680** | **71,680** | **71,680** |

**[측정] 왜 이렇게 됐나** (계획 rev4 §2 박스):

| | Phase 1 | Phase 2 |
|---|---|---|
| 대조군 위치 | **5090** (다른 머신·과거 측정) | **같은 머신 안** (SMG·TA·TA+O 동시 실행) |
| 필요한 것 | **5090과의 외부 일치** → 모델을 8B로 맞춤 | **내부 일관성**만 있으면 됨 → 7B 유지 |

> ⚠️ **H200 Phase 1의 7B 2셀은 "5090과 하드웨어만 다른 통제군"이 아니었다.**
> 계획 §4.1의 그 표현을 rev4가 *"엄밀히는 사실이 아니다"* 로 자기 정정했다 [측정].
> 8B 재실행(2셀)은 **바로 이 모델 교란을 제거하려고 계획 밖에서 추가**된 것이다.
> **두 Phase의 비율을 한 표에 합치면 안 된다** — 모델이 다르므로 서로 다른 실험의 값이다.

**공통점 [측정]**: `fit`의 분모 `FIT_DEN = 32,376`(ctx median)은 두 머신에서 **동일**하다.
트레이스가 텍스트가 아니라 **정수 토큰 수**(`input_tokens`)를 저장하고 드라이버가 tokenizer를 padder로만
쓰기 때문에 **tokenizer 무관**이며, H200에서 재계산해 32,376을 정확히 재현했다.
→ 모델이 달라도 `fit` 값은 같은 자로 잰 것이다.

---

## 4. 데이터셋 — **완전히 동일 (유일하게 100% 통제된 축)**

| 특성 | 값 | 두 실험 |
|---|---|---|
| 트레이스 | **Track M** (`scratch/traces/tracelab_moriM_L64k_yunuikang.jsonl`) | **동일 파일, 재가공 0** |
| 규모 | **3,514 세션 / 117,257 턴** | 동일 |
| long-time-share | **98.9%** | 동일 |
| 전이 median | **4.0** (hard ≥4 PASS) | 동일 |
| 동시점 ι-IQR | **0.694** (hard ≥0.35 PASS) — degenerate 아님 | 동일 |
| 세션 ι mean | **0.517** (idle-heavy) | 동일 |
| **ctx median / peak** | **32,376 / 65,536 tok** | 동일 |
| p999 input+output | 67,928 tok → context-length 71,680 근거 | 동일 |
| 드라이버 | `mori_replay_driver_yunuikang.py` · **C 워커 순환셔플** · warmup 20% · `--ctx-cap 69632` | 동일 |

**[측정] 계획서 명문 제약**: *"baseline / 원본 trace / 기존 스크립트 무수정. Track M 트레이스 재가공 없음."*
→ 데이터셋은 두 실험에서 **한 글자도 다르지 않다.**

> ⚠️ 단서 [측정]: ι·ι-IQR은 프록시 상수(`REASON_DECODE=145`, nutella 값)에 의존하는 **잠정치**다
> (`M4_PARAMS:125`). H200의 실측 decode 속도로 재산출하면 ι 절대값이 바뀔 수 있으나
> **상대 랭킹(= MORI가 실제로 쓰는 것)에는 영향이 작다** [추론]. 전이 median 4.0은 프록시 무관 robust.

---

## 5. 조작 변수 · 레짐 설정

| 항목 | **5090** [측정] | **H200** [측정] |
|---|---|---|
| GPU KV 풀 | **262,144 tok = 36.0 GiB 고정 핀** (native 265,651의 아래) | **`--max-total-tokens`가 조작 변수** — F1 262,246 (36.0 GiB) → Phase 2 **647,520** (34.6 GiB @7B) |
| **fit** (풀 ÷ 32,376) | **8.10 고정 · 조작 불가** (HBM 한계) | **8.10 (F1) → 20.0 (Phase 2)** |
| 자연 풀 (캡 없을 때) | 265,651 tok (핀과 거의 같음) | 7B: fit **64.9** → 압박이 안 생겨 **캡 필수** / 8B: 809,006 tok (fit 25.0) |
| **oversub** | C80에서 **9.88× 고정** | F1 **9.88×** (5090 일치) · Phase 2 C{20,40,80} → **1.00 / 2.00 / 4.00×** |
| **`r`** (host tier 배수) | M-SWP **r∈{1,2}** · Phase 2 **r∈{2,3,4}** ← **조작 변수** | **전 셀 r=2 고정** — **r 축을 한 점도 측정 안 함** |
| host tier 크기 | r2 = 72.0 GiB / r3 = 108 / **r4 = 144 GiB (DRAM 188에서 여유 38 GiB — 빡빡)** | r2 @fit20 = 69.2 GiB (1,026 GiB 한도에서 **비구속**) |
| **C** (동시성) | M-SWP {20,50,80} · Phase 2 앵커 20 / pivot 32 / **본 실험 50** | Phase 1 **C=80** · Phase 2 **{20,40,80}** ← **조작 변수** |
| 조작한 자원 | **CPU tier (DRAM)** — `r` 스윕 | **GPU 풀 (HBM)** — `fit` 스윕 (F1에서 중단) → 이후 **C 스윕** |

**[추론] 두 실험은 서로 다른 자원을 조작한 대칭 실험이다.**
5090 Phase 2 = *"CPU를 키우면 회복되나"*(→ 아니오, DRAM 기각) ·
H200 Phase 1 = *"GPU를 키우면 회복되나"*(→ 하한에서 이미 이겨서 fit 기각).

---

## 6. 실험 설계 · 프로토콜

| 항목 | **5090** | **H200** |
|---|---|---|
| 비교 시스템 | M-SWP **4종** (SMG/TA/TA+O/MORI) · **Phase 2는 2종**(MORI·TA+O만) | Phase 1 **2종**(TA+O·MORI) · Phase 2 **4종** |
| 셀 수 | M-SWP **18셀** · Phase 2 **6셀** (+앵커·pivot) | 게이트 3 · Phase 1 **2+2셀** · Phase 2 **12셀** = 16셀 |
| **셀 길이** | **전부 1시간** (`--duration-s 3600`) — 20분 셀은 MORI 편향(−72.9%) 발견 후 **폐기** | **1시간**, 단 **7B F1 2셀만 30분** ⚠️ |
| 반복 | **n=1** | **n=1** |
| GPU 시간 | M-SWP ≈18h · Phase 2 ≈8h | **≈16.1h** |
| **1차 판정 지표** | 엔진 steady-window tok/s · Waiting 축출 · goodput@5s (불편향 3종) | Phase 1 = **드라이버 thr(주) + 엔진 thr(부)** · Phase 2 = **goodput@5s 점추정** |
| goodput 계측기 | `--profile` per-step `pause_s+prefill_s ≤ SLO` | Phase 1 = **순서통계 구간(50–95%)** · Phase 2 = **점추정** ⚠️ 두 Phase가 서로 다름 |
| **사전 등록** | Phase 2 문서 내 "판정 로직 (사전 등록)" 절 — **별도 파일 없음** | **별도 PREREG 파일 + 커밋 타임스탬프 4/4 선행** ✅ |
| 데이터 위생 게이트 | `fail% >1% AND failed≥3` → 조기중단 | fit 게이트 G0~G6 (오차 0.000% PASS) |
| 원시 데이터 경로 | `scratch/mori/msw/` · `scratch/mori/phase2_*` | **`~/yunuikang_work/h200_scratch/mori/h200_*`** (RESULTS의 `scratch/mori/h200_*` 표기는 오기) |
| 그림 | `figures/` 91개 (전부 5090) | 신규 제작분 (`plot_h200_*.py`) |

---

## 7. ⚠️ 비교할 때 반드시 붙여야 하는 단서 4가지

### 7.1 5090 앵커 `0.45×`는 **A7c 수정 전 코드**로 잰 값이다 [측정]

| 출처 | 코드 | 값 |
|---|---|---|
| M-SWP `MORI_r2_C20` | **A7c 수정 전** | 22.2 (TA+O 19.9 → **1.12×**) |
| Phase 2 앵커 (같은 셀 재측정) | **수정 후** | 25.73 (**1.29×**) — **+15.9%** |
| **M-SWP `MORI_r2_C80` = 0.45× 앵커** | **A7c 수정 전** | 6.47 vs 14.28 |

H200 실험은 **전부 수정 후 코드**다. 즉 *"5090 0.45× → H200 1.405×"* 대조에는
**하드웨어 + 모델 + 코드 버전**이 함께 바뀌어 있다. C50-pivot 문서는 이 사실을
*"M-SWP 옛 수치 재사용 금지 — 비율은 같은 세션의 MORI÷TA+O 로만 판정"* 으로 명문화했지만,
**H200 문서 어디에도 이 단서가 적혀 있지 않다** [측정].
→ [추론] 방향은 MORI에 **유리**(수정이 MORI를 +15.9% 올림)하므로 *"붕괴가 재현되지 않았다"* 를
**약화시키는 쪽**이다. 결론을 뒤집지는 않지만 **PPT에 명시해야 정직하다.**

### 7.2 7B F1 2셀만 30분이다
5090은 20분 셀이 MORI에 **−72.9%** 편향을 준다는 것을 실측했다. 30분도 같은 방향의 편향이므로
*"MORI가 이겼다"* 는 **편향을 거스르고 얻은 결과**다 → 결론을 약화시키지 않는다. 8B 재실행은 60분으로 맞췄다.

### 7.3 Phase 1과 Phase 2는 goodput 계측기가 다르다
Phase 1 = 순서통계 구간 / Phase 2 = 점추정. **한 그림·한 표에 섞으면 안 된다.**

### 7.4 Waiting 축출은 시스템 간 절대값 비교 불가
MORI는 `CPU→Waiting`, SMG/TA/TA+O는 `Paused program` — **다른 사건**이다.
각 시스템 내부의 C 추세만 읽어야 한다. 두 머신 공통 규약.

---

## 8. 한 표로 — "무엇이 통제됐고 무엇이 안 됐나"

| 축 | 통제 여부 | 근거 |
|---|---|---|
| 데이터셋(Track M) · 드라이버 · ctx-cap · 순환셔플 · warmup | ✅ **완전 통제** | 재가공 0 · 스크립트 무수정 |
| context-length 71,680 · `FIT_DEN` 32,376 | ✅ 통제 | YaRN factor는 다르나 착지값 동일 |
| 엔진(SGLang 0.5.10) · attention backend(triton) | ✅ 통제 | |
| 셀 길이 1h · n=1 · 4종 정의 | ✅ 대체로 통제 | 7B F1 30분만 예외 |
| **모델 / KV밀도** | ⚠️ **Phase 1(8B)만 통제, Phase 2(7B)는 미통제** | rev4가 8B 재실행으로 교정 |
| **`fit` / GPU 풀** | ❌ 조작 변수 (H200에서만 움직임) | 5090은 HBM 한계로 고정 |
| **`r` / host DRAM** | ❌ 5090에서만 조작, H200은 r=2 고정 | H200에서 r 축 **미측정** |
| **GPU 세대 · TP · 인터커넥트 · NUMA** | ❌ **묶여서 바뀜, 분리 불가** | H200 1장이라 TP2 불가 |
| **MORI 코드 버전 (A7c)** | ❌ 앵커(M-SWP)만 수정 전 | §7.1 — H200 문서 미기록 |
| 실행 환경 (베어 vs 컨테이너) | ❌ | `numactl --membind` 사용 불가 |
| `--mem-fraction-static` | ❌ 0.85 vs 0.90 | |

**[추론] 결론**: 이 두 실험은 *"데이터·워크로드·엔진을 완전히 고정하고 하드웨어와 자원 축만 바꾼 대조"* 에
**거의** 성공했다. 남은 미통제 요인은 **(a) 하드웨어 3요소가 묶여 있는 것**(GPU 세대 · TP · 인터커넥트),
**(b) Phase 2의 모델 차이**, **(c) 앵커의 코드 버전**이며, (a)를 가르려면 **5090에서 TP1 재실행**이
가장 싸다(H200 렌트 불필요 · 2h) — H200 ANALYSIS §6.3의 후보 A와 같은 결론이다.
