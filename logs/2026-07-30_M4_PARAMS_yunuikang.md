# M4 스윕 직전 파라미터 스냅샷

> 작성 2026-07-30 · 브랜치 `mori` · **HEAD `bf97437`** (직전: `a7426d3`, `916c200`, `0a1c064`, `15ae981`)
> 계획서: `plans/2026-07-30_PLAN_mori-on-thunderagent-goguma6_yunuikang.md`
> 범위: 읽기 전용 스냅샷(코드·trace·GPU 무수정). 값은 계획서 §·실제 config/스크립트에서 직접 읽음. 확인 불가는 TBD.
> 상태 코드: **SET**=확정 · **TBD-STEP1**=STEP1 GPU 실측 보정 필요 · **TBD-µbench**=PCIe 마이크로벤치 보정 · **미결정**=설계 결정 대기

---

## A. 실험 프로토콜 / 스윕 축

| 항목 | 값 | 출처 | 상태 |
|---|---|---|---|
| 고정 벽시계 창 | 20 분(`--duration-s 1200`) | §D-1/§D-4 | SET (STEP1 표본 충분성 확인 조건부) |
| warmup 제외 | 앞 20% | §D-1 | SET |
| repeats | 3 | §D-2/§D-4 | SET |
| concurrency C | 20 / 50 / 80 | §D-2 | SET |
| CPU:GPU 비 r | 1× / 2× (오프로딩 시스템만) | §D-2/§A-3 | SET |
| 시스템: SMG | `--router default` (순수 프록시) | §A-3 · `__main__.py:16` | SET |
| 시스템: TA | `--router tr` + HiCache OFF | §A-3 | SET |
| 시스템: TA+O | `--router tr` + `--enable-hierarchical-cache --hicache-ratio r` | §A-3/§A-2 | SET (Phase1에선 HiCache OFF→TA와 동일, 아래 불일치) |
| 시스템: MORI | `--router mori` (+Phase2 typed eviction) | §A-3 · `__main__.py:16` | SET |
| trace 소진 시 재투입·순환 | 무한 순환 제너레이터 + 사이클 셔플 + 고유세션 커버리지 게이트 | §D-1 | 설계 SET / 구현 TBD(드라이버 미제작) |
| 총 셀 수 (Phase 1 제안) | `{SMG,TA,MORI@1×,MORI@2×}×C{20,50,80}`=12 + nohw(C=80)=4 → **16셀×3rep** | 본 계획(제안) | **미결정**(24셀/ TA+O 포함 여부) |
| 예상 GPU-node-h | ≈18–19 h (STEP1+16셀×3+µbench) | §D-3 추정 | 미결정(셀수 확정 후) |

## B. 하드웨어 / 엔진

| 항목 | 값 | 출처 | 상태 |
|---|---|---|---|
| GPU | RTX 5090 ×2, TP2, 각 32607 MiB, 합산 HBM **63.68 GiB** | `nvidia-smi`(본 세션)·§1 | SET |
| GPU 인덱스 | `CUDA_VISIBLE_DEVICES=0,1` | §A-2 · serve script `:9` | SET |
| 인터커넥트 | SYS(no-NVLink, cross-NUMA); **`--disable-custom-all-reduce` 필수** | §A-2b(스모크)·`topo -m` | SET |
| CPU DRAM | 188 GiB total / 185 avail (32 core, 2 NUMA) | `free -g`·§1 | SET |
| venv (SGLang) | `/home/yunuikang/yunuikang_work/.venv-sglang` | §A-2b | SET |
| 엔진 | **SGLang 0.5.10** / torch 2.9.1+cu130 / sgl_kernel 0.4.1 / flashinfer 0.6.7 | §A-2b(스모크 PASS) | SET |
| 어텐션 백엔드 | `--attention-backend triton`(스모크); flashinfer 실런은 툴체인 env로 재확인 | §A-2b·§E-3 | 미결정(triton vs flashinfer 실런) |
| HiCache 플래그 | `--enable-hierarchical-cache` · `--hicache-ratio {1,2}` · `hicache_write_policy=write_through` · `hicache_io_backend=kernel` | §A-2b server_args 실측 | SET |
| GPU KV 풀 핀 | `--max-total-tokens` = **262144 tok = 36 GiB**(≤ native) | §A-3 | **TBD-STEP1**(native 실측 후 확정) |
| GPU eviction 정책 | `--radix-eviction-policy lru`(baseline); `mori`(Phase2 typed) | §A-2b/§B-Phase2 | SET(lru) / Phase2 미구현 |
| 툴체인 env(필수) | `CUDA_HOME=/usr/local/cuda-13.0`, `CC/CXX=gcc-11`, `NVCC_PREPEND_FLAGS=-ccbin g++-11` | §A-2b·memory | SET |

## C. 모델 / 메모리 레짐

| 항목 | 값 | 출처 | 상태 |
|---|---|---|---|
| 모델 | `Qwen/Qwen3-8B` | serve script `:8`·§A-2 | SET |
| dtype | bf16 (16-bit weights+KV) | serve script 헤더 주석·§A-3 | SET |
| B_tok (KV/tok, TP합산) | 147,456 B = 144 KiB | `mori_config.py:13`·§A-3 | SET |
| native KV 풀 | ≈277k tok (범위 270–310k) ≈ 38 GiB | §A-3(추정) | **TBD-STEP1**(기동 로그 `max_total_num_tokens`) |
| 36 GiB 재현핀 | 262,144 tok (압박 생성 아님) | §A-3 | SET(목표)/토큰 정밀치 TBD-STEP1 |
| fit (÷peak 65.7k) | ≈4.2 | §A-3(추정) | TBD-STEP1(native 확정 시) |
| C_cpu | 1×=36 GiB(262k) / 2×=72 GiB(524k) | §A-3 | SET (DRAM 185 안전) |
| L (컨텍스트 예산) | 65,536 (64k) | `prep_...:52`·§C-2 | SET |
| peak 제약 | ≤ 64k (실측 primary 65,536) | `prep_...`(best_window)·§C-4b | SET |

## D. MORI 스케줄러 파라미터

| 항목 | 값 | 출처 | 상태 |
|---|---|---|---|
| k (idleness 윈도우) | 5 | `mori_config.py:31`·`config.py:33`·`__main__.py:18` | SET |
| 제어 루프 tick | 5.0 s | `config.py:28`·`__main__.py:36` | SET (논문 tick과 동일) |
| cpu_capacity_ratio | 1.0 기본(스윕 1×/2×) | `mori_config.py:32`·`config.py:34` | SET |
| reload 비용모델 | `reload_seconds(t)=t×147456/reload_bw` | `mori_config.py:38-42` | SET(식) |
| reload_bw | 8.0e9 B/s (placeholder) | `mori_config.py:33`·`config.py:35` | **TBD-µbench** |
| BUFFER_PER_PROGRAM | 100 tok | `backend/state.py:23` | SET (CpuTier 동일 규약) |
| DECODE_BUFFER | 512 | `backend/state.py:17` | SET |
| min_dwell_ticks | 1 | `mori_config.py:35`·`config.py:36` | SET |
| default_iota (무표본) | 0.5 | `mori_config.py:36` | SET |

## E. 데이터셋 / 트레이스

| 항목 | 값 | 출처 | 상태 |
|---|---|---|---|
| **primary = Track M** | `tracelab_moriM_L64k_yunuikang.jsonl` | §C-4b·§D-2 | SET |
| ─ 규모 | 3,514 세션 / 117,257 턴 (rebase 버그 수정판; 이전 275,591은 음수 46% 포함) | 실측(`wc -l`) | SET |
| ─ long-time-share | 98.9% (by design) | prep 실행·§C-4b | SET |
| ─ 전이 median | **4.0** (hard≥4 PASS) | prep 실행·§C-4b | SET |
| ─ ι-IQR(per-session) | **0.694** (hard≥0.35 PASS) | prep 실행·§C-4b | SET(프록시 의존, advisory) |
| ─ peak | 65,536 (≤64k PASS) | prep 실행 | SET |
| ─ 재현 | `python scripts/prep_tracelab_mori_yunuikang.py --track M` | `prep_...:565+` | SET |
| ablation = nohw | `tracelab_moriM_L64k_nohw_yunuikang.jsonl` 117,257턴, long 96.8%, **전이 2.0(FAIL)** | prep 실행 | SET (human-wait 기여 입증) |
| 대조 저-idle | `swebench_trace.jsonl` 64세션/1,388턴, long 29.9% | §C-1 meta | SET |
| 대조 고-idle | `tracelab_earlycutoff_128k` 4,142/189,431, long 96.3%, peak median 65,678 | §C-1 meta | SET |
| CAP_HARD | 300.0 s (모든 duration) | `prep_...:53`·§C-4 | SET (600 민감도 실행 여부 미결정) |
| human gap 제외 | ≥ 12h (43,200 s) | `prep_...:54` | SET |
| Track P(58%) | `--track P`, 582/9,290, 58.08% — **실험 arm 제외**, trilemma 증거 보관 | §C-4b·`prep_...:279` | SET(제외) |

## F. 지표 (측정 정의)

| 지표 | 정의 | 출처 | 상태 |
|---|---|---|---|
| output throughput | Σcompletion_tokens / steady_wall [tok/s] | §D-1 | SET(정의)/드라이버 TBD |
| step throughput | Σ완료 턴 / steady_wall [req/s] | §D-1 | SET(정의)/드라이버 TBD |
| TTFT | mean / p50 / p95 [s], `--stream` 항상 on | §D-1 | SET(정의)/드라이버 TBD |
| 집계 규약 | warmup 20% 제외 후 **창 내 완료 턴**만 집계 | §D-1 | SET |
| 부가 | prefix_cache_hit_rate · local_compute(참 recompute) · GPU util(`--gpus 0,1`) · `/health` tier 카운트 | §D-1 | SET(정의) |

## G. STEP1에서 보정될 TBD 목록 (스윕 전 확정 필요)

| 항목 | 현재값(출처) | 확정 방법 |
|---|---|---|
| decode tok/s | 145 (nutella/vLLM 값; `prep_...:58` `REASON_DECODE`) | STEP1 SGLang/5090 실측 |
| ι reasoning proxy 상수 | prefill 8000 · decode 145 (`prep_...:57-58`) | STEP1 실측으로 교정(ι값·IQR 재산출) |
| native KV 풀 | ≈277k 추정(§A-3) | 기동 로그 `max_total_num_tokens` |
| `--max-total-tokens` 핀 | 262,144(목표, §A-3) | native 확정 후 ≤native로 고정 |
| reload_bw → reload_seconds | 8.0e9 placeholder(`mori_config.py:33`) | PCIe 마이크로벤치(numactl) |
| 20분창 표본 충분성 | 미확정(§D-3) | STEP1 처리량으로 완료 턴 수 검증(부족 시 창 연장) |
| I6 정합(host 할당 vs ratio) | hicache-ratio 2 → host 9.66 GB(스모크) | 소스 대조로 `capacity_tokens×B_tok==host_pool` 확인 |

---

## 요약

### ① 아직 값이 안 정해진 항목 (스윕 전 확정 필요)
- **STEP1 실측 대기**: native KV 풀 → `--max-total-tokens` 정밀 핀, decode tok/s, ι 프록시 상수(145/8000), 20분창 표본 충분성.
- **µbench 대기**: `reload_bw`(현재 8.0e9 placeholder) → Phase-1 reload 비용모델.
- **설계 미결정**: Phase-1 셀 수(16 vs 24 / TA+O 포함 여부), CAP 600s 민감도 실행 여부, 실런 어텐션 백엔드(triton vs flashinfer).

### ② 계획서 ↔ config/스크립트 불일치 (M4 전 정리 필요)
1. **엔진 불일치(가장 큼)**: 계획/결정은 **SGLang**이나 현존 serve 스크립트는 **vLLM**(`_serve_vllm_8b_tp2_yunuikang.sh`, `MML=131072`, `GMU=0.92`). **SGLang serve 스크립트 미제작** → `--max-total-tokens`/`--hicache-ratio`/툴체인 env/`--disable-custom-all-reduce` 반영본을 새로 만들어야 함.
2. **컨텍스트 길이 불일치**: prep `L=65536`(64k, `:52`) vs vLLM serve `MML=131072`(128k). SGLang serve의 `--context-length`를 64k 계열로 맞춰야 함.
3. **하네스 공백**: `mori_replay_driver`·`run_mori_eval`·`_serve_sglang_*`·`microbench_pcie_kv` **전부 미제작**(§6 예정 목록에만 존재) → 지표·순환셔플·µbench가 아직 실행 불가.
4. **Phase-1 TA+O 축소**: §A-3은 TA+O를 별도 시스템으로 두나 Phase-1은 엔진 오프로딩 OFF라 **TA+O ≡ TA** → 셀 정의에서 명시적 처리 필요(중복/생략).
5. **nutella 잔재 상수**: ι 프록시 `REASON_DECODE=145`는 nutella 값 — goguma6 실측 전까지 Track M의 ι/ι-IQR은 잠정(단 전이 median은 프록시 무관 robust).

> 이 시트 확정·수정 후 M4(하네스 제작 → STEP1 → 스윕)로 진행. 본 파일 생성 외 코드·trace·GPU 무수정.
