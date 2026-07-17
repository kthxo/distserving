# 실험 결과 — Pro6000 TP2 축소 재현 (P0+P1) (2026-07-16)

> 작성: 강윤의 · 브랜치 `yunuikang/thunderagent` · 서버 nutella1 · 계획서 `plans/2026-07-15_PLAN_pro6000-tp-rescale_yunuikang.md`(권위 문서)
> 스코프: **P0(브링업·검증·기준측정) + P1(TraceLab·SWE 스윕)**. P2(Science)·P3(HLE)는 미착수.
> 가드레일: `scheduler/router.py` 미수정(관측·CLI·replay만), 공유 스크립트 격리 복사본, GPU1·GPU2 전용(타 프로세스 무간섭).

---

## P0 — 브링업·검증·기준측정 (Deployment A)

### P0-1. 환경 (계획 §2-5)
- venv 활성, `CPATH`(Python.h 우회 유지), `VLLM_USE_FLASHINFER_SAMPLER=0`, `CUDA_VISIBLE_DEVICES=1,2`.
- vLLM 0.24.0 / torch 2.11.0+cu130, driver 590.48.01 / CUDA 13.1, Blackwell sm_120.
- 실행 전 `nvidia-smi`: GPU0/1/2 전부 유휴(2 MiB, 0%), 타 프로세스 없음 확인 → 착수.

### P0-2. Deployment A 기동 — TP2 Qwen3-32B (신규 격리 `_serve_vllm_tp2_yunuikang.sh`)
- 명령: `CUDA_VISIBLE_DEVICES=1,2 vllm serve Qwen/Qwen3-32B --tensor-parallel-size 2 --max-model-len 32768 --gpu-memory-utilization 0.92 --port 8000` (tmux `tp2serve`).
- 가중치 66GB 다운로드(HF unauthenticated, ~1시간) 후 로드·컴파일 → **정상 기동**(Application startup complete, /health 200).
- **★ (a) 실측 KV 풀**: vLLM `cache_config_info` = **block_size=16 × num_gpu_blocks=28,559 = C_total 456,944 tokens**.
  - 계획 추정 ~401k 대비 **약간 큼(456,944)**. **vs 4090(43,888) = ×10.41**. TraceLab fit(median 18.3k) ≈ **25 프로그램**(4090은 ~2). 32k-max-context 기준 max concurrency 13.94×.
  - → **C 범위(16·32·64·128·256) 그대로 적합**(fit~25 아래 16=음성대조, ≥32 default 스래싱 예상). **재조정 불필요.**
- **★ (b) Python.h / torch.compile / CUDA-graph**: `enforce_eager=False`(compile 경로 활성)로 기동 → **이슈 없음**. inductor 컴파일 통과, **CUDA graphs(FULL) 51개 캡처 성공(8s, 0.81 GiB)**. SETUP_NOTES 문제① 미재발(CPATH 우회 유지 상태).
  - 부가: SymmMem/QuickReduce sm_120 미지원 → **CUSTOM+PYNCCL all-reduce**(SYS 경로), FLASH_ATTN v2. (계획 §2-3 정합.)

### P0-3. 프록시 + 스모크
- 프록시(tmux `tp2proxy`): `thunderagent --backend-type vllm --backends http://localhost:8000 --port 9000 --router default --metrics --profile --profile-dir scratch/tp2/prof_duty`. `/health` → router_mode=default, backends=[:8000] assertion OK.
- `smoke_test_yunuikang.py`(model Qwen3-32B) → **SMOKE TEST OK** (단일 completion + 멀티턴 program_id KV locality + release 200). 전체 ThunderAgent 경로 검증.

### P0-5. c=1 duty 프로파일 (TraceLab) — ✅ 완료
- `trace_replay_driver_expC` c=1, 25 programs, --stream, tool-scale 1.0 (wall 862s), 87 turns 기록(`scratch/tp2/duty/duty_turns.jsonl`).
- **d = Σ(ttft+decode) / Σ(ttft+decode+tool) = 243.6 / (243.6+598.0) = 0.289**. **NEED = 1/d = 3.45**.
- 입력 mean 18,684 tok(TraceLab prefill-heavy 재확인), completion mean 54.8 tok. per-turn reasoning mean 2.80s, tool mean 6.87s/median 0.54s/max 30s(cap).
- **vs 4090 expC d=0.196 → 상승(0.289)**: 예측대로 32B의 느린 reasoning(prefill 18k + decode)이 tool 대비 비중↑ → d 상승. (한계: c=1 고유값; 부하 하 d는 P1 스윕에서 교차확인.)
- **★ k_fit-flip 사전예측(R 모델)**: fit≈25(456,944/18,684). 중부하 C≤~24에서 tr k_fit≈C ≫ NEED(3.45) → **R=k_fit·d ≫ 1 → tr 승 예상**.
  - 4090: fit~2, k_fit~1.6, d=0.196 → **R=0.31<1 (패, 실측 −34%)**. Pro6000: KV ×10.4 → fit~25 → tr가 R≥1 유지 가능 → **flip(승/역전) 예측**. P1에서 실측 검증.

### P0-4. SYS 페널티 마이크로벤치 (TP2 vs TP1 decode) — ✅ 완료
- 서버 정지(GPU 해제: 2 MiB, 0%) 후 `microbench_tp_sys_yunuikang.py`, Qwen3-32B, batch32×gen256×input512.
- **TP2(GPU1+2, SYS all-reduce) = 1038.0 tok/s** vs **TP1(GPU1 단독) = 598.7 tok/s** → **TP2/TP1 = 1.73×**.
- **해석**: TP2가 단일GPU보다 **73% 빠름** — 2GPU 연산·대역폭 분할 이득이 cross-NUMA SYS all-reduce 비용을 상회. **스케일 효율 = 1.73/2.0 = 86.5%** → 이상적 선형(2×) 대비 **~13.5%가 SYS/TP 오버헤드**. → **SYS caveat는 존재하나 소폭(정성 결론 무해)**, TP2 번들은 순이득(KV 2배 + decode 1.73배). NVLink였다면 2×에 더 근접했을 것.

### P0-6b. ✅ TP2 GPU 매핑 검증 (CUDA_DEVICE_ORDER 우려 확인, 2026-07-16)
- 우려: CUDA 기본 FASTEST_FIRST면 `CUDA_VISIBLE_DEVICES=1,2`가 96GB+48GB(이종)로 잡혀 KV 축소/OOM 가능.
- 검증: **`CUDA_DEVICE_ORDER=PCI_BUS_ID` 설정 확인**(서버 env) → CUDA 순서=nvidia-smi 순서. Worker_TP0→UUID 19bd9ed4(index1 Pro6000 96G), Worker_TP1→UUID 11d628de(index2 Pro6000 96G). nvidia-smi: index0(48G)=2MiB 유휴, index1/2=각 93,250 MiB.
- 물리 증거: KV 456,944 tok = GPU당 ~93GB(60 KV+33 weights) 필요 → 두 카드 모두 93,250 MiB = 둘 다 96GB 확정(48GB는 담을 수 없음). → **대칭 TP2(96+96), 실험 유효.**

### P0-6. docker (SWE 녹화 전제) — ✅ 접근 OK
- `docker info` 정상, `docker` 그룹 소속 확인 → SWE 재녹화 unblocked.

---

## ★ 게이트 1 — P0 요약 (P1 승인 대기)

| 항목 | 결과 | 판정 |
|------|------|------|
| **실측 KV 풀 (C_total)** | **456,944 tok** (block_size16 × 28,559 blocks) | 계획 ~401k보다 큼. 4090의 **×10.41**, TraceLab fit≈**25 prog** |
| **C 범위** | 계획 16·32·64·128·256 | **그대로 적합**(fit~25: C=16 음성대조, C≥32 default 스래싱 예상). 재조정 불필요 |
| **Python.h / torch.compile** | CUDA graph 51개 캡처 성공, 이슈 **없음** | 클린(CPATH 우회 유지) |
| **SYS 페널티** | TP2 1038 / TP1 599 tok/s = **1.73×** (효율 86.5%) | 오버헤드 ~13.5%(소폭) |
| **TraceLab duty d** | **0.289** (NEED 1/d=3.45) | 4090(0.196)보다↑(32B 예측대로). **R=k_fit·d ≫1 예상 → flip 지지** |
| **스모크·프록시·docker** | SMOKE OK, router assertion OK, docker OK | 정상 |

**k_fit-flip 사전예측(핵심)**: 4090 R=0.31(패) → Pro6000 fit~25·d=0.289 → 중부하서 R≥1 → **tr 승/역전 예측**. P1이 실측 검증.

**P1 소요 재추정**: TraceLab 스윕(tr/def×C5×3=30런) ~6–10h · SWE 재녹화(stratified-64, 32B, docker) ~8–12h(게이트2에서 첫10 인스턴스로 재보정) · 풀검증 소량 · SWE 스윕 ~10–16h → **P1 총 ~25–40h GPU**(unattended, tmux).

## P1 — 착수 (게이트 1 승인됨 2026-07-16)

### P1-0. 서버 재기동 + 파이프라인 스모크
- Deployment A 재기동(캐시됨, compilation 4.74s, KV 456,928 tok). 파이프라인 스모크(`run_serving_eval` default C=16 NPROG=32 R1) → **thru=0.159p/s, p95=196s, hit=0.758, 32/32** 정상.

### P1-1. TraceLab k_fit-flip 스윕 — 실행 중 (tmux `tp2sweep`, 옵션 A)
- **초기 NPROG=256 시도 → 스래싱 C(≥32)에서 repeat당 ~90분(C=32 r1이 95분 미완)으로 전체 ~25–30h 추정** → 사용자와 협의(게이트 아님, 타이밍 이슈).
- **✅ 옵션 A 채택(2026-07-16)**: `run_serving_eval`에 **per-C NPROG=max(96, 2×C)** 추가(NPROG_MODE=scale), **C=256 제외**(default 붕괴는 C=32–64에서 이미 드러남; C=256=fit 10배 과구독은 정보량 대비 비용 과다). → NPROG: C16=96, C32=96, C64=128, C128=256. REPEAT=3.
- **2차 조정(2026-07-17)**: 스래싱 지점 실측 throughput(C=32 thru=0.039)이 예상보다 낮아 **C=128도 제외** → **C=16·32·64**로 확정(REPEAT=3 유지). flip은 C=16(대조)·32(붕괴 개시)·64(심화)로 완전 입증 가능; C≥128은 정보량 대비 비용 과다(C=256 제외와 동일 논리).
- default→tr, **C=16·32·64**, per-C NPROG=max(96,2C)=96·96·128. trace=tracelab_fit32k.jsonl. 로그 `tracelab_sweep.log`, 출력 `tracelab_{default,tr}.jsonl`, 샘플러 `sample_*_c*.csv`.
- **★ 예비 소견 (default, 유효 — k_fit-flip 신호 확인)**:
  | C | thru(p/s) | hit | p95(s) | 상태 |
  |---|-----------|-----|--------|------|
  | 16 (fit~25 미만) | 0.133 | **0.81** | 240 | 스래싱 전(정상) |
  | **32 (fit 초과)** | **0.039** | **0.29** | **1490** | **default 붕괴**(hit 0.81→0.29, thru 3.4×↓, p95 6×↑) |
  → default가 KV fit 초과 시 스래싱 붕괴 확인. **tr 절반에서 tr이 C=32·64에서 유지하면 flip 입증**(가설 지지).
- 예상 ~7h. [tr 절반 + 최종 정합 대기]

---

## 게이트 1 — [P0 완료 후 작성]

## P1 — [게이트 1 승인 후]
