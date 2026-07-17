# 실험 계획 — Pro6000 축소 재현: 논문 serving eval(4워크로드, HLE 무료화) + R모델(k_fit 축) 검증

> 작성: 강윤의 · 브랜치 `yunuikang/thunderagent` · 2026-07-15 (v3, 2026-07-16 4워크로드 최종본) · **플랜만(실행 전 검토 대기)**
> 서버: **nutella1**(143.248.247.92) · 저장소: `/home/yunuikang/yunuikang_work/distserving`
> **v3 변경 요약**(v2 대비): (1) **4워크로드 최종 확정** — SWE-bench·ScienceAgentBench·HLE(논문 3종) + TraceLab. (2) **TraceLab = closed-loop 그대로 유지**(open-loop/client-time 반영 **철회** — 근거 §4-1). (3) **SWE-bench = stratified 축소본 유지 + 풀 불변성(pool 32 vs 64) 검증**(전체 300 **폐기** — 근거 §4-2). (4) **HLE = 유료 도구 전량 무료 GLM 대체**(총 API 비용 $0, 후보 선정·근거 §4-4). (5) ScienceAgentBench 신규 추가.
> 전제 문서:
> - `../logs/2026-07-16_HLE_APIREPLACE_INVESTIGATION_yunuikang.md`(**HLE 유료→무료 GLM 대체 조사 — §4-4의 1차 근거**)
> - `../logs/2026-07-07_EXPERIMENT_C_RESULTS_yunuikang.md`(R 모델 검증, 4090 2×, r=0.959)
> - `../logs/2026-07-07_SWEBENCH_RESULTS_yunuikang.md`(SWE decode-heavy, d≈0.995, tr 승)
> - `../logs/2026-07-06_MECHANISM_REFERENCE_yunuikang.md`(cost model·policy↔코드, Phase 0)
> - `../logs/2026-07-03_EXPERIMENT_LOG_hetero_yunuikang.md` **§B-1**(TraceLab 정규화)
> - `../logs/2026-07-01_SETUP_NOTES_yunuikang.md` **§3**(ToolOrchestra 유료 API키+FAISS, 나머지 Docker)
> - 논문(**갱신본** `/home/yunuikang/yunuikang_work/ThunderAgent.pdf`, 34p, 2026-07-16 확인) **§5.1·Fig4·5(a–f)·Appendix C(Table 6 "Tool buckets")·Appendix D**. (repo 내 구 `assets/paper/_Arxiv__ThunderAgent.pdf`는 tool buckets가 Table 5인 이전 버전 — 갱신본 기준 Table 6로 통일.)
> 원칙: **한 번에 한 변수만. 기존 스크립트/버그픽스 재사용·불파괴. `scheduler/router.py` 로직 미수정(관측·CLI 노브·replay 옵션만).**

---

## 0. 논문 세팅의 정정된 이해 (이 프레이밍으로 계획)

ThunderAgent 논문 실험은 두 종류다. 우리가 4090에서 하던 "백엔드 2개로 라우팅"은 **serving eval이 아니라 rollout 구조**였다. 이번엔 **serving eval**(단일 deployment + 동시성 스윕 + 정책 비교)을 축소 재현한다.

| 논문 실험 | 구조 | 하드웨어 | 우리 대응 |
|-----------|------|----------|-----------|
| **Serving 평가(Fig 4·5, main eval)** | **단일 deployment 1개** + 동시성 스윕 + 정책 비교 | 8×H100 TP8 인스턴스 1개(GLM-4.6 355B/Qwen3-235B) 또는 **RTX5090 1장(Qwen3-8B, ToolOrchestra)** | **← 이번에 재현(4워크로드)** |
| RL rollout(Table 2) | 멀티노드(2×8×H100 DP) cross-node 마이그레이션 | 2노드, vLLM+SGLang Gateway baseline | (범위 밖 — 4090 2백엔드가 이 구조였음) |

**논문 main eval = 3 데이터셋 × 4 워크로드 × 3 모델 (Fig 4·5, 서브그림 a–f)** + **우리 TraceLab**:
| 서브그림 | 워크로드 | 데이터셋 | 논문 모델 | 논문 HW | tool 성격 |
|----------|----------|----------|-----------|---------|-----------|
| a,d | mini-SWEAgent | SWEBench-Lite | GLM-4.6 / Qwen3-235B | 8×H100 TP8 | 로컬 경량(예측가능, decode-heavy) |
| b,e | OpenHands(code) | SWEBench-Lite | GLM-4.6 / Qwen3-235B | 8×H100 TP8 | 로컬, heavy-init(>10GB/sandbox) |
| **c** | **ToolOrchestra** | **HLE** | **Qwen3-8B** | **RTX5090 1장** | **원격 API(검색·model-as-tool), heavy-tailed·stochastic** |
| f | OpenHands | ScienceAgentBench | GLM-4.6 | 8×H100 TP8 | 샌드박스/파이썬 실행(다소 가변) |
| — | (우리) TraceLab | SyFI coding trace | — | — | prefill-heavy·저듀티(k_fit-flip 전용) |

**핵심 구조 변경(이전 4090 2백엔드 대비)**: 이전은 vLLM 2개를 프록시가 **라우팅**했다(=rollout류). 이번은 **vLLM 인스턴스 1개** 앞단에 ThunderAgent 프록시를 둔다. 백엔드 1개라 cross-backend 마이그레이션은 무의미하나, **serving eval 핵심 메커니즘 pause/resume(스래싱 억제)은 그대로 단일 인스턴스 KV 풀에 작동** → 논문 main eval 의미론과 일치.

**우리 deployment 2종 + GPU 할당(nutella1)** — 논문이 워크로드별 다른 HW를 쓴 것을 반영:
| Deployment | 구성 | GPU 할당 | 워크로드 |
|-----------|------|----------|----------|
| **A(번들)** | **TP2 Qwen3-32B** | **GPU1+GPU2**(2×Pro6000, `CUDA_VISIBLE_DEVICES=1,2`) | SWE-bench·ScienceAgentBench·TraceLab |
| **B(HLE)** | **Qwen3-8B 오케스트레이터(단일 GPU) + FAISS 리트리버(별도 GPU)** | **오케스트레이터=GPU0(Pro5000 48G, 논문 5090 대응) + 리트리버=GPU1(Pro6000)**, **번들과 시간대 분리** | HLE/ToolOrchestra |
- B는 A와 **시간대 분리**(동시 미가동): HLE 실행 시 GPU1+GPU2 유휴 → 리트리버가 GPU1 사용, 오케스트레이터는 GPU0(otherwise 미사용). launch 스크립트 `--retrieval-gpu`로 리트리버 GPU 지정.

- x축 = **parallel workflow number(C)**, y축 = **throughput(steps/min)** 또는 **KV hit rate**.
- 정책: **`--router default` ≈ 논문 vLLM baseline**, **`--router tr` ≈ ThunderAgent(Ours)**. Continuum은 repo 미구현(§6-1, 전 워크로드 N/A).
- 하이퍼파라미터: **Δt = 5(scheduler-interval 5s)**, **decay f(t)=2^(−t)**(`--use-acting-token-decay`), `--acting-token-weight 1.0`.
- **throughput 지표 = steps/min**(논문 정의: 1 step = reasoning+acting 1회).

---

## 1. 목표 & 가설

### 1-1. 목표
논문 serving eval을 **Pro6000 축소 인스턴스**에서 **4워크로드**로 재현하고, 두 축을 검증한다:
1. **k_fit 축(KV 용량)** — 4090에서 R<1로 졌던 **TraceLab**이 KV **~9배 확대(96GB×2)**에서 **R≥1로 뒤집히는가**.
2. **stochastic 축(원격 tool)** — **HLE(원격 API heavy-tailed)**에서 **f(t)=2^(−t) pause/resume 코스트모델이 진짜 시험받는가**(tr이 KV hit을 희생하고 GPU 활용률을 택하는가).

### 1-2. 워크로드별 성격 = 자극하는 스케줄러 측면 ★
| 워크로드 | 성격 | 자극하는 스케줄러 측면 | 우리 예측 |
|----------|------|------------------------|-----------|
| **SWE-bench** | decode-heavy, 로컬툴 결정적(d≈0.99) | **KV pin → hit↑ → tr 압승** | tr ≫ default(throughput·hit 모두) |
| **ScienceAgentBench** | 샌드박스/파이썬, 다소 가변 | **중간**(로컬이나 SWE보다 가변) | tr 우세(SWE보다 격차 작음) |
| **HLE(ToolOrchestra)** | 원격 API, heavy-tailed·긴 지연·stochastic | **f(t) pause/resume 트레이드오프**(tr이 hit 희생, util 택함) | tr > default(throughput), **hit는 낮음** |
| **TraceLab** | prefill-heavy·저듀티(d≈0.196) | **k_fit-flip 핵심**(KV 용량이 R을 좌우) | 4090 R<1(패) → Pro6000 R≥1(승/역전) |

### 1-3. 중심 가설 (R 모델, 실험 C에서 4090에서 r=0.959로 검증됨)
> **U ≈ min(R, 1),  R = k_fit × d** — d=duty=reasoning/(reasoning+tool), k_fit=평균 resident 수. R≥1→GPU 포화→tr 우세; R<1→bubble→U≈R→tr 열세.

**(A) k_fit 축 예측(핵심)**: 4090 TraceLab는 KV 43,888에 median 18.3k 프로그램 ~2개만 → tr k_fit≈1.6, **R≈0.31<1 → 패(−34%)**. Pro6000 TP2 KV **~401k(§3, 실측 재확인)** → 물리 fit **~22**. 중부하(C≤~22)에서 tr은 pause 없이 k_fit≈C → **R≫1 → U≈1 → TraceLab에서도 tr 승/역전**.

| 워크로드 | HW | KV(tok) | d | 물리 fit | 예측 tr@중부하 |
|----------|-----|---------|-----|---------|----------------|
| TraceLab(D) | 2×4090 | 43,888 | 0.196 | ~2 | R≈0.31 → 패(실측 −34%) |
| **TraceLab(이번)** | Pro6000 TP2 | ~401k | 0.196 | ~22 | **R≥1 → 승/역전(가설)** |
| SWE-bench | 2×4090 | 43,888 | 0.995 | ~2–4 | R≫1 → 승(실측 +78~84%) |
| **SWE-bench(이번)** | Pro6000 TP2 | ~401k | ~0.99 | 큼 | 계속 tr 우세(decode-heavy) |

**(B) stochastic 축 예측 — 교수님이 특히 궁금해한 지점 ★**: 논문 Appendix C·D + Fig 4c·5c·f 정리:
- **예측가능 tool(SWE·Science 로컬)**: acting phase가 KV를 짧게 점유 → Cost_caching 작음 → **스래싱 회피가 지배 → hit↑ = throughput↑**. tr이 KV pin으로 hit·throughput 모두 우세.
- **stochastic·긴 tool(HLE 원격 API, heavy-tailed p95≫median)**: TTL 예측형(Continuum)은 긴 tool의 KV를 pin → recompute↓(hit↑)하나 **Cost_caching↑(놀고 있는 KV 점유) → throughput↓**. **tr의 f(t)=2^(−t)는 long-idle acting 프로그램의 메모리 우선순위를 점진 하향 → 그 KV를 evict**해 idle-caching 비용을 줄이고 GPU를 active하게 유지. **결과(논문 Fig 5c·f): tr은 Continuum보다 KV hit은 낮지만 throughput은 높음**(GPU active 유지). ← **f(t) 코스트모델이 진짜 시험받는 케이스**.
  - 정직: 논문 Fig 4c 배속(1.48× vs vLLM / 0.65× vs Continuum)은 **HLE에서 tr–Continuum 격차가 가장 좁고 지점에 따라 역전 가능** → HLE는 tr 우위가 가장 약한(코스트모델 민감) 워크로드. 우리는 Continuum 미구현이라 **tr vs default(vLLM) 재현**에 집중, Continuum 대비는 논문 인용. **가설: HLE에서 tr은 default 대비 throughput 우세, hit는 낮음**(stochastic idle이 duty 지배).

---

## 2. 하드웨어 / 환경 (nutella1, 실측 재검증 완료)

### 2-1. GPU 구성 (`nvidia-smi topo -m` 실측)
| GPU | 카드 | VRAM | NUMA | 링크 | 용도 |
|-----|------|------|------|------|------|
| **0** | RTX PRO 5000 | 48 GB | NUMA0 | GPU0↔1=NODE | **Deployment B 오케스트레이터(HLE, 논문 5090 대응)** |
| **1** | RTX PRO 6000 | 96 GB | NUMA0 | GPU1↔2=**SYS** | **A(TP2)** + B 리트리버(시간대 분리) |
| **2** | RTX PRO 6000 | 96 GB | NUMA1 | GPU1↔2=**SYS** | **A(TP2)** |

- **Deployment A(번들)** = GPU1+GPU2 TP2, `CUDA_VISIBLE_DEVICES=1,2`(합 192GB).
- **⚠️ 링크 caveat**: GPU1↔GPU2 = **NVLink 없음 + cross-NUMA(SYS)** → TP all-reduce 느림(논문 8×H100 NVSwitch보다 나쁨) → **throughput 절대값에 오버헤드(정성 결론 무해, 상대비교·U정합 기반)**. GPU0(48GB)+GPU1(=NODE 더 좋은 링크)은 메모리 비대칭이라 TP 불가 → SYS 감수하고 96+96 선택. **마이크로벤치로 실측(§4-6).**

### 2-2. 드라이버/런타임 (실측)
- **driver 590.48.01 / CUDA 13.1**, Blackwell **sm_120**(cap (12,0)). **환경 이미 브링업**: `.venv` 정상, **vLLM 0.24.0 / torch 2.11.0+cu130**, GPU 인식 OK.

### 2-3. ✅ Blackwell 브링업 feasibility — TP2 스모크 통과 (2026-07-16 실측)
`CUDA_VISIBLE_DEVICES=1,2` + Qwen3-0.6B TP2 `enforce_eager`: **engine init 79.5s → generate 정답**. **NVLink 없는 cross-NUMA(SYS) TP2 NCCL all-reduce가 Blackwell sm_120에서 작동**(NCCL 2.28.9, SymmMem/QuickReduce 미지원→CUSTOM+PYNCCL 폴백=정상).
- **SETUP_NOTES 이슈 변화**: ③ flashinfer JIT 컴파일 실패 **미재발**(FLASH_ATTN 자동, autotuning 통과). `VLLM_ATTENTION_BACKEND`는 0.24.0에서 **무시**(무해). `VLLM_USE_FLASHINFER_SAMPLER=0` **여전히 존중**(유지). ① `Python.h`(torch.compile 경로)는 스모크가 eager라 미발동 → **본 기동(compile/CUDA-graph)에서 재발 가능, CPATH 우회 유지·첫 non-eager 기동 로그 확인(확인 필요)**.

### 2-4. docker (SWE·Science 필수)
- 현재 **permission denied**(docker 그룹 미소속), **사용자 sudo 권한 있음**: `sudo usermod -aG docker $USER` 후 재로그인 → `docker info` OK.
- 논문은 agent Docker를 별도 CPU 클러스터로 offload → 우리는 한 노드에서 GPU/컨테이너 자원 분리 개념만(SWE·Science 컨테이너=CPU/RAM, 서빙=GPU). 디스크 `/home` 여유 **403GB**(mini-SWE ~2GB/inst, **OpenHands >10GB/sandbox**, 모델 66GB).

### 2-5. 환경 브링업 절차 (모든 터미널 공통)
```bash
source /home/yunuikang/yunuikang_work/.venv/bin/activate
HDR=/home/yunuikang/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/include/python3.12
export CPATH="$HDR" C_INCLUDE_PATH="$HDR"       # ① Python.h 우회(유지·첫 기동 확인)
export VLLM_USE_FLASHINFER_SAMPLER=0            # 존중됨(유지)
export CUDA_VISIBLE_DEVICES=1,2                 # Deployment A(TP2). B는 오케스트레이터=0, 리트리버=1
```
- 레포/venv 이미 존재(재설치 불필요). 결측 시 이전 방법(rsync + `uv pip install vllm --torch-backend=auto` + `pip install -e ./distserving`).
- **HLE(B)는 별도 conda 환경 필요**(launch 스크립트 기본 `vllm1`·`retriever-clean`) → §4-4 blocker.

---

## 3. 모델 — 워크로드별(논문 방식) 확정

| Deployment | 모델(서빙 대상) | 정밀도 | 워크로드 | 근거 |
|-----------|----------------|--------|----------|------|
| **A(TP2, GPU1+2)** | **Qwen3-32B** | **BF16** | SWE-bench·ScienceAgentBench·TraceLab | k_fit flip 최선 검증 + 확실 구동 |
| **B(TP1, GPU0)** | **Qwen3-8B 오케스트레이터** | FP16 | HLE/ToolOrchestra | **논문 "Qwen3-8B on 1×RTX5090" 직접 대응** |

### 3-1. Deployment A 모델 = Qwen3-32B (확정, 근거)
| 후보 | weights | KV 풀(계산) | vs 4090 | k_fit@TraceLab | vLLM 지원 | 판정 |
|------|---------|-------------|---------|----------------|-----------|------|
| **Qwen3-32B** | ~66GB | **~401k tok** | **×9.1** | ~22 | ✅ `Qwen3ForCausalLM`(스모크) | **✅ 확정** |
| GLM-4.5-Air(FP8) | ~106GB | ~343k | ×7.8 | ~19 | ✅ `Glm4MoeForCausalLM` | 스트레치(§3-3) |
- KV/token(Qwen3-32B 64층·8KV·128)=256 KiB; usable(0.92×192)177 − weights 66 − overhead ~6 = **KV 105GB → ~401k tok**(4090 8B 43,888 tok로 공식 검산 정합). **실측은 기동 시 `vllm:cache_config_info{num_gpu_blocks}` 확인**(`C_total=block_size×num_gpu_blocks`, `backend/vllm_metrics.py:25`).
- **왜 32B**: 최소 weights → KV 여유 최대(×9.1) = k_fit flip 최선 검증; dense·BF16 = 구동 확실·MoE/EP 교란 없음; Qwen3 연속성(8B→32B). 단일 96GB에도 적재되나 TP2로 KV를 2GPU 분산(=번들 추상화 + KV 풀 확대).

### 3-2. Deployment B 모델 = Qwen3-8B 오케스트레이터 (HLE, 논문 대응)
- 논문 §5.1: "ToolOrchestra는 **Qwen3-8B FP16 on one RTX5090**". 우리는 **단일 Pro5000(GPU0) TP1**로 대응(RTX5090≈단일 Blackwell 48GB). 서빙 대상 = 오케스트레이터(우리 GPU에 뜨는 유일 모델); 도구 호출은 원격 GLM/로컬 FAISS(§4-4). **오케스트레이터 checkpoint 택**: 논문 `Qwen3-8B` vs repo 기본 `Nemotron-Orchestrator-8B`(§4-4 blocker, 확인 필요).

### 3-3. 스케일 스트레치(문서화, 별도 승인 시 승격) — GLM-4.5-Air (106B MoE, FP8)
- 가벼운 검증: `Glm4MoeForCausalLM` vLLM 0.24.0 **등록**, `zai-org/GLM-4.5-Air-FP8` **ungated 존재**. BF16(212GB)은 192GB 초과 → **FP8 필수**. 실 로드 스모크는 106GB 다운로드 필요(가벼운 feasibility 초과) → **별도 무거운 창 승인 시 Deployment A 대체 후보**(GLM 계열=논문 근접, 스케일 갭 축소).

---

## 4. 워크로드 (논문 3종 + TraceLab) + 마이크로벤치

방법론 공통: **record→replay**(이전 로그 근거) — tr/default가 **동일 offered load를 결정적으로 재생**(라이브 스윕은 에이전트/원격 tool 편차로 정책 비교 오염). 각 워크로드를 공통 스키마 JSONL로 정규화 후 `trace_replay_driver_expC`로 스윕.

### 4-1. TraceLab (k_fit 축, 핵심) — 기존 그대로(closed-loop) 유지
- **base trace**: `scratch/traces/tracelab_fit32k.jsonl`(982세션, model-agnostic replay) **그대로 재사용**. Deployment A. **정규화기·드라이버 수정 없음**(기존 closed-loop).
- **★ open-loop/client-time 반영 안 함 — 결정 근거**:
  - (a) **목적은 논문 재현**이고, client-idle이 자극하는 "긴 stochastic idle → f(t) pause/resume" 메커니즘은 **HLE(원격 API heavy-tailed)가 이미 정면으로 커버**(§4-4). TraceLab에까지 open-loop을 넣는 것은 축이 중복.
  - (b) open-loop(client_wait 복원+드라이버 open-loop 모드)은 **wall-clock·엔지니어링 비용 큼**(heavy-tail cap 설계, active/open concurrency 분리, 측정창 왜곡 관리 등).
  - → TraceLab은 그대로 두고 **k_fit-flip(4090 R<1 → Pro6000 R≥1) 검증 전용**으로 유지. (client-time 복원 자체는 feasible함을 v2에서 확인했으나 이번 스코프에서 제외 — §10 미결에 백로그로만 남김.)

### 4-2. SWE-bench (예측가능·decode-heavy, 일반성) — 축소 유지 + steady-state 검증
- **mini-SWEAgent 우선**(lightweight ~2GB), OpenHands는 옵션(heavy-init >10GB/sandbox). Deployment A, Docker.
- **워크로드 풀 = stratified 축소본 유지(전체 300 폐기)**: `sample_swebench_stratified_yunuikang.py`(seed=20260707, 레포 비례 stratified-64). **모델 8B→32B 변경으로 재녹화 필요**(출력 토큰·턴수·decode 특성 변동) → **stratified-64를 Qwen3-32B로 재녹화**. `swebench_qwen_config`의 model을 **Qwen3-32B + base_url=프록시**로 교체, `prep_swebench_trace`·`char_swebench` 재사용, clip rate<30% 재확인.
- **★ 풀 크기 불변성 검증(신규)**: 고정 동시성(예 C=64)에서 **pool=32 vs pool=64** 두 녹화본으로 replay → **steady-state throughput이 같은지** 확인. 같으면 축소본 확정, 다르면 상향(stratified-128).
- **근거(왜 전체 300 불필요)**: 이 실험의 관측 대상은 **"동시성↑ 시 steady-state 유지(tr) vs 붕괴(default)"뿐** → 풀의 대표성(전체 300)이 아니라 **"측정창 동안 파이프가 차 있느냐(정상상태)"만 중요**. 풀 불변성 검증으로 이를 직접 확인 → **32B×300 재녹화(수십 시간) 비용 회피**. record→replay + Docker + 32B 재녹화(축소본만) 유지.

### 4-3. ScienceAgentBench (샌드박스·다소 가변) — 신규 추가
- **OpenHands** on ScienceAgentBench. Deployment A(32B TP2 번들), **Docker**(샌드박스 >10GB로 무거움). record→replay 유지. tool(Table 6 SAB buckets): execute-bash(샌드박스/IO), execute-ipython(program runtime), str-replace-editor·task-tracker(로컬 FS) → **로컬이나 SWE보다 다소 가변**(중간). 논문 모델 GLM-4.6 → 우리 32B. **무료**(Docker+로컬모델).
- **✅ feasibility(2026-07-16)**: 데이터셋 `osunlp/ScienceAgentBench` **ungated 존재**. **⚠️ OpenHands eval 하네스는 repo에 `swe_bench`만 있고 ScienceAgentBench 미포함**(`examples/inference/OpenHands/evaluation/benchmarks/`) → **하네스 추가 필요(upstream OpenHands/ScienceAgentBench 이식, 확인 필요)**.

### 4-4. HLE / ToolOrchestra (원격 API·heavy-tailed·stochastic) — **유료 도구 전량 무료 GLM 대체** ★
> 1차 근거: `../logs/2026-07-16_HLE_APIREPLACE_INVESTIGATION_yunuikang.md`.

- **deployment(§0·§2-1)**: **Qwen3-8B 오케스트레이터(GPU0 Pro5000, 논문 5090 대응) + FAISS 리트리버(GPU1 Pro6000)**, 번들과 **시간대 분리**. `examples/inference/ToolOrchestra/evaluation/launch_hle_inference.sh`가 오케스트레이터 vLLM(:8100) + ThunderAgent 라우터(:8000) + 리트리버(:1401, `--retrieval-gpu`) 파이프라인을 이미 배선.
- **유료 도구 전량 무료 GLM 대체(총 API 비용 $0)**: reasoner(gpt-5)·search(gpt-5-mini)·answer(gpt-oss-120b) 전부 → **Z.ai GLM 무료 Flash(GLM-4.7-Flash / 4.5-Flash)**. **judge OFF**(`HLE_ENABLE_JUDGE=0`), **Tavily OFF**(로컬 FAISS retrieval만) → 유료 호출 제거. (오케스트레이터 8B는 우리 GPU=무료.)

#### 4-4-1. ★ 도구 모델 후보 선정 (조사 로그 §3 근거)
**후보 4종 및 선정 기준(① 완전 무료 ② 원격이라 stochastic-remote 성격 보존 ③ OpenAI-호환 ④ 충분한 context/용량 ⑤ 안정성·rate limit):**

| 후보 | 무료? | 원격(stochastic 보존) | OpenAI-호환 | rate limit | 판정 |
|------|-------|----------------------|-------------|-----------|------|
| **(i) GLM 무료 Flash (Z.ai)** | ✅ 완전 무료(1000 req/day) | ✅ | ✅ `api.z.ai/api/openai/v1` | 무료티어 1000/day | **✅ 채택** |
| (ii) DeepSeek-v4-flash | ❌ 초저가 **유료**($0.14/M in) | ✅ | ✅ | 여유 | 폴백(무료 아님) |
| (iii) OpenRouter :free | ✅ 무료 | ✅ | ✅ | ❌ **~20/min·200/day 빡셈** | 탈락(throughput 상한 큼) |
| (iv) 로컬 서빙 오픈모델 | ✅ | ❌ **tool이 빠르고 결정적 → stochastic-remote 상실** + GPU 추가 | ✅ | — | 최후·비채택(성격 훼손) |

- **왜 GLM 무료 Flash 채택**: **완전 무료(1000 req/day 무료티어)** + **OpenAI-호환**(`https://api.z.ai/api/openai/v1`) + 대용량 context + **원격이라 stochastic 성격 보존**.
- **왜 나머지 탈락**: **DeepSeek** = 원격·초저가지만 **유료**(완전무료 아님) → 무료한도 초과 시 폴백. **OpenRouter** = 무료지만 **200 req/day·20/min 빡센 rate limit**으로 스윕 throughput 상한이 큼. **로컬 서빙** = 무료지만 **tool이 빠르고 결정적이 되어 stochastic-remote 성격 상실 + GPU 추가 필요 → HLE 재현 목적 훼손**(그래서 최후·비채택).
- **caveat/리스크**:
  - **GLM 무료 1000 req/day 일일 한도** — 스윕(동시성 24–48 × ~130분 × 여러 run) 호출량이 초과 가능 → 초과 시 (a) **DeepSeek-v4-flash 유료 폴백**(총 몇 $) 또는 (b) **서브셋/동시성 축소로 한도 내 유지**. **record→replay로 GLM 호출을 1회 녹화분에 고정**하면 스윕 반복이 GLM을 재호출하지 않아 한도 압박 크게 완화(권장, §4-4-3).
  - **rate-limit 스로틀**은 throughput 절대값을 낮추나 **stochastic 성격엔 부합**(절대비교 안 하므로 무해).
  - **무료 Flash의 tool 출력 품질**: 정확도(정답률)는 우리 관심 아님(throughput만) — 단 **tool 실패율(코드 생성·`<answer>`/`\boxed` 포맷 준수 실패)이 워크로드 형상을 바꿀 수 있어** **스모크 1회로 확인**.

#### 4-4-2. 코드 변경 (조사 로그 §4 근거 — 계획엔 what/where만, 실제 수정은 실행 단계)
- **`examples/inference/ToolOrchestra/LLM_CALL.py`**: `get_glm_client(base_url=env GLM_BASE_URL)` 추가(Nebius/Together 블록 복제 ~15줄) + `get_llm_response`에 `elif model_type=="glm" or "glm" in model.lower():` 분기.
- **`examples/inference/ToolOrchestra/evaluation/eval_hle_local.py`**: `MODEL_MAPPING`(reasoner-*→`glm-4.7-flash`, search-*→`glm-4.5-flash`; answer-*는 gpt-oss-120b 유지 또는 GLM으로) + `enhance_reasoning`/`answer` dispatch에 `"glm" in model_name` 분기 + `supported_models` assert remap 정합.
- **env**(`setup_envs.sh`): `GLM_API_KEY`/`GLM_BASE_URL` 설정, `HLE_ENABLE_JUDGE=0` 유지, Tavily 비움(로컬 FAISS만).
- (env-only 편법은 `model="gpt-5"`를 GLM이 거부 → 분기 깨짐 → 위 소폭 코드수정이 견고, 조사 §4-6.)

#### 4-4-3. 남은 블로커 (확인 필요)
- **FAISS 인덱스**: ✅ **해소** — `multi-train/index`(HF dataset, ungated)에 **`eval.index`+`eval.jsonl` 존재 확인**(2026-07-16). clone 후 `INDEX_DIR` 지정 + `faiss-gpu`.
- **오케스트레이터 checkpoint 택**: 논문 `Qwen3-8B`(우리 서빙=무료) vs repo 기본 `Nemotron-Orchestrator-8B`(config default). **확인 필요**(논문 정합이면 Qwen3-8B).
- **conda 환경**: launch 스크립트 기본 `vllm1`(오케스트레이터)·`retriever-clean`(FAISS) — 우리는 venv 기반이라 **conda 환경 구축 필요**(확인 필요).
- **Continuum 미구현** → default/tr만.

#### 4-4-4. 스윕/지표
- 동시성 스윕(**논문 5090 케이스 C=24·32·40·48 참조**), **default vs tr**, throughput(**steps/min**) **windowed**(정상상태 구간). record→replay로 GLM tool 지연을 1회 녹화 후 replay(권장, 한도 완화). 기대: stochastic tool → **tr이 KV hit 희생하고 util 택함**(Fig 4c·5c).

### 4-5. 스윕 조건 (독립변수 = 동시성)
- **C 범위**(논문 parallel workflow number 참조):
  - **Deployment A(32B, SWE·Science·TraceLab)**: **C = 16·32·64·128·256**(물리 fit~22 아래 16=음성 대조, ≥32 default 붕괴 재포착).
  - **Deployment B(8B, HLE)**: **C = 24·32·40·48**(논문 HLE 범위).
- **NPROG**: 정상상태 위해 C 이상. TraceLab NPROG=256(982 중), **SWE NPROG = 풀 불변성 검증 결과(§4-2, 기본 stratified-64; C>64는 순환 시 run 접미사)**. REPEAT=3(에러바). 2정책(tr,default).

### 4-6. SYS 페널티 마이크로벤치 (신규) — decode throughput
- **TP2(GPU1+2) vs TP1(GPU1)** 동일 모델·배치 decode tok/s → all-reduce over SYS 페널티 실측(%). throughput 절대값 해석 caveat 상수.

---

## 5. 측정 & R 모델 계측 (실험 C 인프라 재사용)

3종 동시 수집. `router.py` 미수정.

### 5-1. 지표
- **Throughput = steps/min**(논문 정의, 1 step=reasoning+acting) **및** programs/s(드라이버). **KV hit rate**(`/metrics` prefix_cache 델타). **p95 latency**. **HLE는 windowed**(정상상태 구간, rate-limit 스로틀 영향 구간 제외).

### 5-2. R 모델 변수 (예측 U vs 실측 U)
- **d(duty)**: c=1 프로파일(`--concurrency 1 --stream --profile`) = `Σ(prefill+decode)/Σ(prefill+decode+tool)`. HLE는 원격 tool이 길어 d 낮음(stochastic idle).
- **k_fit**: `sample_gpu_resident_yunuikang.py`(**`--gpus 1,2`** for A; HLE는 오케스트레이터 GPU) 평균 resident.
- **U_measured** = 1 − idle_fraction(REASONING count==0 시간비율). **R = k_fit×d → 예측 U=min(R,1)**. k_fit flip(4090 R=0.31 → Pro6000 R≥1)을 예측선에 얹어 검증(TraceLab 중심).

---

## 6. 비교 시스템 & 산출물

### 6-1. 비교
- **default(≈vLLM) vs tr(≈ThunderAgent Ours)** — **전 워크로드 필수**.
- **Continuum**: 논문 SOTA baseline(tool 지연 예측 + KV pin). **현 repo `--router`는 {default, tr}만**(`__main__.py:16`) → **미구현 → 전 워크로드 N/A**. HLE의 tr–Continuum 대비(교수님 관심)는 논문 인용으로 서술.

### 6-2. 산출물 경로
- 데이터: `scratch/tp2/{tracelab,swe,science,hle}_{tr,default}_c*.jsonl`, `sample_*.csv`, `prof_*/step_profiles.csv`, `tp2_summary.csv`.
- 그래프(`figures/`): 워크로드별 `tp2_<wl>_{throughput_stepsmin,hitrate,p95}.png`; `tp2_pred_vs_meas_U.png`(R1); `tp2_kfit_flip_4090_vs_pro6000.png`(★ TraceLab flip); `tp2_hle_hit_vs_throughput.png`(stochastic: hit↓·throughput 유지 ★); `tp2_swe_pool32_vs_64.png`(풀 불변성); `tp2_sys_microbench.png`.
- 문서: `../logs/2026-07-1x_TP2_RESULTS_yunuikang.md`(설정/명령/결과표/해석/한계) + §1 예측표 실측 채움.

---

## 7. 예상 소요 · Phase 재구성 · 리스크 · 한계

### 7-1. Phase 재구성
| Phase | 내용 | Deployment | 의존/blocker | 비용 |
|-------|------|-----------|--------------|------|
| **P0** | 브링업·모델 확정·KV 실측·SYS 마이크로벤치·c=1 duty | A | — | 무료 |
| **P1(무료·핵심)** | **TraceLab 스윕(k_fit flip)** + **SWE 재녹화(축소본)·풀검증·스윕** | A | docker(SWE) | 무료 |
| **P2(무료)** | ScienceAgentBench 스윕 | A | docker + **하네스 이식** | 무료 |
| **P3(무료 GLM)** | HLE/ToolOrchestra 스윕 | B | **FAISS·checkpoint·conda·GLM 코드변경** | **$0**(GLM 무료; 한도 초과 시 소액) |

### 7-2. 예상 GPU 시간 (±50%)
| 단계 | 추정 |
|------|------|
| P0(브링업·32B 66GB 다운로드·스모크·마이크로벤치·duty) | ~1.5–2h |
| P1 SWE 재녹화(stratified-64, 32B, docker) + 풀검증(32 vs 64) | ~8–12h |
| P1 SWE 스윕(30런, 32B) | ~10–16h |
| P1 TraceLab 스윕(tr/default × C5 × 3 = 30런) | ~6–10h |
| P2 Science(하네스 이식 후 녹화+스윕) | ~8–14h |
| P3 HLE(GLM 무료, 단일 8B, C4점 × 2정책 × 3) | ~4–8h + **$0(무료 한도 내)** |
| **총(P0–P1)** | **~26–40h GPU**(핵심, 무료) |
| **총(P0–P3)** | **~40–60h GPU**(+ Science 하네스 개발·HLE 셋업, 전부 무료) |
- **SWE 재녹화 시간 근거**: 이전 Qwen3-8B×stratified-64 = ~3h6m → 32B decode ~2–3배 느림(+TP2-SYS) → **~8–12h**(축소본 유지라 전체 300의 ~25–45h 대비 대폭 절감). 이전 4090 실험보다 증가하나(4워크로드·32B) **전부 무료**.

### 7-3. 리스크
1. **모델 스케일 미달**(32B/8B ≪ 논문 235B/355B) → 절대수치 비교 안 함, 상대·R정합·정성만.
2. **TP-SYS 오버헤드** → 마이크로벤치 상수화.
3. **Blackwell 빌드**: TP2 스모크 de-risk 완료. 잔여 `Python.h`(non-eager 첫 기동 확인).
4. **docker**(SWE·Science) 그룹 추가 필요(sudo).
5. **ScienceAgentBench 하네스 미포함** → 이식 개발 필요(스코프·시간 리스크).
6. **GLM 무료 일일한도(1000 req/day)** — 스윕 호출량 초과 가능 → record→replay로 GLM 재호출 최소화, 초과 시 DeepSeek 유료 폴백(소액) 또는 서브셋 축소.
7. **FAISS 인덱스 확보**: ✅ `multi-train/index`에 eval.index/eval.jsonl 확인 → clone·faiss-gpu 셋업만 남음.
8. **tool 실패율 ↔ 워크로드 형상**: GLM 무료 Flash의 tool 출력 포맷 실패가 트레이스 형상을 바꿀 수 있음 → 스모크 1회 확인.
9. **HLE GPU 할당**: 오케스트레이터 GPU0 + 리트리버 GPU1, 번들과 시간대 분리 필수(동시 가동 시 GPU1 경합).
10. **Continuum 미구현** → tr–Continuum 대비 정량 재현 불가(논문 인용 보완).

### 7-4. 한계 (정직하게)
- k_fit 축은 고R에서 실측 U가 예측 하회 가능(잔여 bubble). 방향·단조성 위주.
- HLE는 GLM 무료 Flash 대체라 **논문의 gpt-5/gpt-oss-120b와 tool 지연 분포가 다를 수 있음**(둘 다 원격 heavy-tailed지만 provider별 상이) → 절대비교 안 하고 stochastic 정성만.
- ScienceAgentBench 하네스 이식의 충실도(upstream과 정합) 확인 필요.
- TraceLab open-loop(client-time)은 이번 스코프 제외(§4-1) → session/open-loop 축은 미검증(백로그).

---

## 8. 재사용 / 수정 / 신규 스크립트

### 8-1. 그대로 재사용
- `scratch/traces/tracelab_fit32k.jsonl`(TraceLab, 수정 없음), `scripts/{sample_swebench_stratified,prep_swebench_trace,char_swebench,plot_expC,smoke_test}_yunuikang.py`.

### 8-2. 수정
- **`sample_gpu_resident_yunuikang.py`**: `--gpus 2,3`→**`--gpus 1,2`**(A) / HLE는 오케스트레이터 GPU.
- **`swebench_qwen_config_yunuikang.yaml`**: model Qwen3-8B→**Qwen3-32B**, base_url=프록시.
- **`_serve_vllm_yunuikang.sh`**: Deployment A(`--tensor-parallel-size 2`, CUDA 1,2, Qwen3-32B) 프로파일.
- **`plot_expC_yunuikang.py`**: steps/min 파생 + kfit-flip·hle-hit-vs-thru·pool32-vs-64 그래프.
- **`examples/inference/ToolOrchestra/LLM_CALL.py`** + **`.../evaluation/eval_hle_local.py`**: **GLM provider 경로·MODEL_MAPPING·dispatch 분기 추가**(§4-4-2, 무료화).

### 8-3. 신규
- **`run_serving_eval_yunuikang.sh`**: `run_trace_sweep_expC`를 **단일 백엔드(:8000) + 프록시(:9000)** 구조로 개작(백엔드 2→1, 샘플러 `--gpus 1,2`, C=16·32·64·128·256, 워크로드 인자).
- **`swe_pool_invariance_yunuikang.sh`**(신규): 고정 C에서 pool=32 vs 64 steady-state throughput 비교(§4-2).
- **`microbench_tp_sys_yunuikang.py`**: TP2 vs TP1 decode 벤치.
- **ScienceAgentBench 하네스 이식**(P2): OpenHands eval에 SAB 벤치 + `science_qwen_config_yunuikang.yaml` + `prep_science_trace_yunuikang.py`.
- **HLE launch config**(P3): `setup_envs.sh`(GLM_API_KEY·GLM_BASE_URL·INDEX_DIR·CKPT_DIR, judge/Tavily OFF) + `prep_hle_trace_yunuikang.py`(원격 tool 지연 녹화→canonical) + 오케스트레이터 8B(GPU0)+리트리버(GPU1) 기동 프로파일(launch_hle_inference.sh 래핑).

---

## 9. 실행 전 체크리스트 (승인 후)
1. **환경**(§2-5). `docker info` OK. **Deployment A 기동**(`CUDA_VISIBLE_DEVICES=1,2 vllm serve Qwen/Qwen3-32B --tensor-parallel-size 2 --max-model-len 32768 --gpu-memory-utilization 0.92 --port 8000`) → **첫 로그에서 실측 KV 풀(num_gpu_blocks)·Python.h/compile 이슈 확인**.
2. **프록시**: `thunderagent --backend-type vllm --backends http://localhost:8000 --port 9000 --router tr|default --metrics --profile --profile-dir scratch/tp2/prof_<...>` → router_mode assertion.
3. **P0**(마이크로벤치·duty) → **P1**(TraceLab 스윕 + SWE 재녹화·풀검증·스윕) → **P2**(Science, 하네스 이식 후) → **P3**(HLE: FAISS clone·conda·GLM 코드변경·스모크 → 스윕).
4. `plot` → 결과 로그 → 서버·컨테이너 정리.

## 10. 미결(검토받을 것)
- **스코프/타임라인**: 4워크로드 **한 번에 다** vs **단계적(P1 우선)**. GPU ~40–60h(전부 무료).
- **SWE 풀 크기**: pool 32 vs 64 steady-state 검증 결과에 따라 축소본 확정/상향.
- **HLE GLM 무료한도 실측**: 스윕 규모 확정 후 호출량 vs 1000/day 재계산(초과 시 DeepSeek 유료 폴백 소액 or 서브셋 축소). record→replay로 재호출 최소화.
- **HLE checkpoint 택**: 논문 Qwen3-8B vs repo Nemotron-Orchestrator-8B.
- **HLE tool 실패율**: GLM 무료 Flash 스모크 1회로 포맷 준수·실패율 확인(워크로드 형상 영향).
- **ScienceAgentBench 하네스 이식** 여부·범위(개발 비용).
- **실측 KV 풀**이 ~401k과 다르면 C 범위 재조정.
- **워크로드별 모델(32B/8B) vs 단일 통일**: 논문은 워크로드별 상이 → per-workload(A=32B, B=8B) 유지 제안.
- **(백로그)** TraceLab open-loop(client-time): 복원 feasible(v2 확인) but 이번 스코프 제외 — 향후 session/open-loop 축 필요 시 재개.
- **GLM-4.5-Air 스트레치 승격**(별도 106GB feasibility 창 승인 시).
</content>
