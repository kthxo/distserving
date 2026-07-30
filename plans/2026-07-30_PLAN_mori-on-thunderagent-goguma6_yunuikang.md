# 연구 계획 (goguma6 재계산판, SGLang) — MORI를 ThunderAgent 위에 구현·평가

> 작성: 강윤의 · 브랜치 `mori`(off `yunuikang/thunderagent`) · **2026-07-30** · **계획만(코드·trace·스크립트 무수정, GPU 미점유)**
> 저장소 `/home/yunuikang/yunuikang_work/distserving` · 서버 **goguma6** (실제 실험 서버)
> **base 계획서**: `plans/2026-07-30_PLAN_mori-on-thunderagent_yunuikang.md`(nutella/Pro6000/vLLM 기준). 본 문서는 하드웨어·엔진 의존 섹션을 goguma6 실측 + **SGLang 결정**으로 재작성하고, 서버·엔진 무관 설계(데이터·스케줄러 코드·계측·프로토콜)는 재활용한다.
> 논문: `MORI.pdf`(arXiv:2606.00866v1).

### ★ 2026-07-30 사용자 승인·결정 (본 문서에 반영됨)
1. **capping 미적용 + 36 GiB 재현핀** — 승인. native 압박 레짐(fit≈4) 그대로 사용.
2. **L 128k→64k** — 조건부 승인. **turn-window slicing(컨텍스트 rebase)로만, prefix truncation 금지. 전이 median ≥4 게이트 통과가 확정 조건.**
3. **엔진 = SGLang v0.5.10 + HiCache** (vLLM 아님). 재현 정합성 우선. 버전 정확 일치는 불필요(5090 지원 최소 버전 허용). **vLLM native offloading 경로(OffloadingConnector·`_CACHE_POLICIES`·OffloadKey)와 "vLLM 동일→재활용" 서술은 전부 삭제**됨.
   - sm_120(5090 Blackwell) 구동이 **최우선 롱폴**: 조기 스모크를 별도 우선 게이트로. **스모크는 GPU 사용 → 실행 전 별도 승인 후 정지.** 호환 실패 시 **조용히 vLLM로 되돌리지 말고 리포트하고 멈춘다.**
   - **Phase 1(스케줄러-only)은 엔진 무관** → SGLang 설치·호환 검증과 **병행/선행 가능**.
4. **§D 프로토콜**: run-to-completion → **고정 벽시계 창으로 승격(필수)**. duration deadline + 무한 순환 제너레이터 + 벽시계창 완료-턴 집계 + TTFT/`--stream`. 순환 제너레이터의 **corpus 다양성·사이클 셔플 검증**을 게이트에 추가(prefix cache 인위 warm 방지).
5. 20분창 = STEP1 decode tok/s 실측 후 표본 충분성 확인 **조건부 OK**. 8B 고정 OK.
6. **★ 재스코프(2026-07-30, 최종)**: **모델링 Phase 1 폐기 → 실 SGLang HiCache 위 완전 MORI(a+b) 직행.** 논문 최대 충실 재현이 목표.
   - 4종 시스템 전부 **실 HiCache** 위에서 실행. `mori_tier`의 **reload_seconds 비용모델·PCIe µbench·reload_bw 캘리브레이션 폐기** → `mori_tier`를 실 HiCache offload/reload에 매핑(idleness·router 로직은 유지). 실 reload가 측정됨.
   - **완전 MORI = (a) 스케줄러[구현됨] + (b) typed eviction[SGLang HiRadixCache, §4.3.2]**. 헤드라인 스윕은 (a+b) 단일 버전으로 SMG/TA/TA+O와 비교(스윕을 stage로 안 쪼갬). (a)-only는 (b) 배선이 막힐 때의 **중간검증·폴백**으로만 보관.
   - **Duration = 1시간**(`--duration-s 3600`), 20분창 폐기. **셀 18개**: SMG(3)+TA(3)+TA+O(6=r×C)+MORI(6=r×C), 우선 셀당 1런 → 결정 셀(C=80 등)만 repeat. r(1×/2×)은 오프로딩 시스템(TA+O·MORI)에만.
   - **하네스 임의 생성 금지 = 기존 `trace_replay_driver_yunuikang.py` 확장**(§D-1b 조사 결과). µbench 제외.
   - GPU 단계 승인 유지: 하네스 확장 + (b) 제작·리뷰(CPU) → STEP1(~15분) → 리뷰 → 완전 MORI 스모크 → 헤드라인 스윕(1h×18). 각 GPU 잡 사전 승인.

---

## 0. 한 문단 요약

goguma6는 **RTX 5090 32GB×2 = TP2 합산 HBM 63.7 GiB**(nutella 191 GiB의 0.33배)다. 그 결과 (a) native KV 풀이 이미 ~38 GiB(fit≈4)라 **capping 없이 native로 논문 압박 레짐**이 성립하고, (b) 레짐 미세조정 레버가 GPU 풀 축소 → **L(컨텍스트 예산) 축소(128k→64k)** 로 이동한다. 엔진은 사용자 결정에 따라 **SGLang v0.5.10 + HiCache**로 통일한다(논문과 동일 스택). goguma6에는 sglang이 아직 미설치이고 5090은 sm_120이라, **SGLang이 이 GPU에서 실제 구동되는지가 최우선 리스크**다 → 조기 스모크를 별도 승인 게이트로 둔다. **Phase 1(스케줄러-only)은 엔진 무관이라 SGLang 검증과 무관하게 먼저 진행**한다. 트레이스 자산은 이 서버에 존재하고 meta가 정확히 재현된다.

---

## 1. ★ nutella(base) → goguma6 변경 대조표 (전부 실측/결정 근거)

| 항목 | nutella (base) | **goguma6 (실측/결정)** | 근거 |
|---|---|---|---|
| GPU 구성 | Pro5000 48G(타인) + Pro6000 96G×2 | **RTX 5090 32G ×2, 둘 다 유휴, 타 사용자·프로세스 없음** | `nvidia-smi` |
| TP2 대상 GPU | GPU1,2 (`CUDA_VISIBLE=1,2`) | **GPU0,1 (`0,1`)** | GPU0 유휴, serve 스크립트 `GPUS=0,1` 기본 |
| GPU당 HBM / TP2 합산 | 96 / **191 GiB** | 31.84(32607MiB) / **63.68 GiB** | 실측 |
| 상호연결 | SYS, NVLink 없음 | **SYS, NVLink 없음. GPU0=NUMA0(cpu0-7,16-23), GPU1=NUMA1(cpu8-15,24-31)** | `topo -m` |
| CPU DRAM | 251 / 231 GiB | **188 / 185 GiB avail** (32코어, 2 NUMA) | `free -g`/`nproc` |
| 드라이버/CUDA/arch | — | **580.82.07 / 13.0 / sm_120 Blackwell** | `nvidia-smi` |
| **엔진** | vLLM 0.24.0 | **SGLang v0.5.10 + HiCache (신규 설치 필요, 현재 미설치)** · vLLM 0.24는 무시 | 사용자 결정 #3 |
| **오프로딩 스택** | vLLM OffloadingConnector | **SGLang HiCache(계층 radix + host tier)** | 결정 #3 |
| native C_total (8B) | 1,150,112 tok(158 GiB) | **≈270–310k tok(~38 GiB) ; STEP1 확정** | HBM 0.33× (§A-3). SGLang 기동 로그 `max_total_num_tokens`에서 |
| native fit(÷peak65.7k) | ≈17.5 — 압박 없음 | **≈4.2 — 압박 있음** | 작은 HBM |
| **capping** | 필수(158→60G) | **불필요(native가 논문 레짐)** — 재현·I6용 36 GiB 핀만 | 결정 #2 |
| C_gpu 설정 | cap 60G 강제 | **`--max-total-tokens 262144`(36 GiB) 핀 ≤ native** | cap-up 불가(작은 HBM) |
| 2× CPU tier | native 316G>231 → cap 후에만 | **native 2×≈72G < 185 → 그냥 가능** | 작은 KV 풀 |
| **L** | 128k | **64k (windowed median peak ~38–40k)** | C=20을 fit 존에(§A-3) · 결정 #2 |
| C 스윕 | 20/50/80 | **20/50/80 유지** | L로 레짐 조정 |
| 프로토콜 | run-to-completion | **고정 벽시계 창(필수 승격)** | 결정 #4, drain-bias 제거 |
| GPU-node-h | ≈38 h | **≈38 h (고정창·1노드로 동일)** + SGLang 설치/스모크 별도 | 표본충분성만 재확인 |
| gpu sampler `--gpus` | 2,3 | **0,1** | GPU 재배치 |
| decode tok/s | 145(vLLM/nutella) | **미측정 → STEP1(SGLang) 재측정** | 다른 GPU+엔진 |
| **최우선 롱폴** | (엔진 기설치) | **✅ 해소: SGLang 0.5.10 + HiCache가 2×5090 sm_120에서 실구동 확인(스모크 PASS)** | §A-2 스모크 결과. sm_120 문제 아님, 툴체인 env만 필요 |

> nutella의 숫자·엔진 서술은 복사하지 않았다. goguma6 열은 전부 실측 또는 실측 기반 재계산/결정이다.

---

## A. 실험 환경 (goguma6 + SGLang)

### A-1. git — **M0 완료**
- working tree clean, `yunuikang/thunderagent`(HEAD `46e6586`)에서 **`git checkout -b mori` 실행 완료**. MORI 작업은 이 브랜치.
- 격리 검증(매 커밋): `git diff yunuikang/thunderagent..mori -- ThunderAgent/scheduler/router.py ThunderAgent/backend/state.py` == 0줄.

### A-2. 엔진 기동 — **SGLang로 재작성** (vLLM `vllm serve` 경로 폐기)

현재 goguma6에는 **sglang 미설치**(`python -c import sglang` → ModuleNotFoundError). 신규 설치 후 기동:

```bash
# (설치는 M-SGL, GPU 스모크는 승인 후) — 5090/cu13 지원 최소 sglang + sgl-kernel/flashinfer 필요
# TA(오프로딩 없음, 논문 TA):
python -m sglang.launch_server --model-path Qwen/Qwen3-8B \
  --tp 2 --port 8100 --context-length 65536 \
  --max-total-tokens 262144            # ★ C_gpu 36GiB 핀(§A-3). --mem-fraction-static 대신 토큰 직접 고정
# env: CUDA_VISIBLE_DEVICES=0,1
```
- **하네스 변경 범위**: ThunderAgent `--backend-type vllm` → **`sglang`**. 메트릭 스크레이핑은 기존 `ThunderAgent/backend/sglang_metrics.py`(base에서 "존재하나 미사용" 확인됨) 경로로 전환. serve 스크립트 신규 격리 복제 `scripts/_serve_sglang_8b_tp2_mori_yunuikang.sh`. **원본 vLLM 스크립트 무수정.**
- **4종 시스템 매핑(SGLang)**:

| 논문 | 라우터 | SGLang 엔진 플래그 |
|------|--------|--------------------|
| **SMG**(SGLang model gateway) | `--router default`(직결 프록시) | HiCache OFF. DP=1이라 SMG ≡ 네이티브 SGLang 직결 — 논문과 **정확 일치** |
| **TA** | `--router tr` | HiCache OFF |
| **TA+O** | `--router tr`(무수정) | `--enable-hierarchical-cache --hicache-ratio R` (SGLang 네이티브 LRU가 host tier 관리) |
| **MORI** | `--router mori` | Phase1: HiCache OFF / Phase2: `--enable-hierarchical-cache --hicache-ratio R` + **typed-eviction 패치(§Phase2)** |

- DP=1이므로 affinity-aware LB(논문 §4.1)는 평가 제외(base와 동일).
- **exact 플래그명·의미는 M-SGL 스모크에서 상당 부분 확정**(아래 §A-2b server_args 실측). 나머지 evict 통합 지점은 소스 대조(OQ-E2).

### A-2b. ★ M-SGL 스모크 결과 (본 턴, GPU 승인 후 실행 — PASS)

별도 venv `/.venv-sglang`(기존 vLLM `.venv` 무손상)에 **sglang 0.5.10 / torch 2.9.1+cu130 / sgl_kernel 0.4.1 / flashinfer 0.6.7** 설치. `--prerelease=allow` 필요(sglang가 `flash-attn-4` pre-release 의존). 2×5090(sm_120, capability (12,0)) 확인.

**스모크 PASS** (TP2 + HiCache):
- 기동 `READY ~126s`, 단일 `/generate` 요청 성공(`text=" 4. Q: What is 2+3? A: 5"`).
- **HiCache offload 경로 동작**: `Allocating 9.66 GB host memory for hierarchical KV cache`(TP0·TP1), `max_total_num_tokens=65536, available_gpu_mem=17.91 GB`.
- **sm_120 비호환 아님**: 초기 실패는 flashinfer/sgl_kernel **JIT nvcc 툴체인** 문제였고(=커널은 `compute_120a,sm_120a` 정상 타겟), **환경변수만으로 해소**:

```bash
# goguma6 SGLang 기동 필수 env (전부 이미 서버에 존재, 미설정이었을 뿐):
export CUDA_HOME=/usr/local/cuda-13.0      # cuda_fp8.h 등 툴킷 헤더 (CUDA_HOME 미설정이 원인 1)
export PATH="$CUDA_HOME/bin:$PATH"
export CC=/usr/bin/gcc-11 CXX=/usr/bin/g++-11
export NVCC_PREPEND_FLAGS="-ccbin /usr/bin/g++-11"   # 기본 gcc-13 > nvcc 허용(≤11) (원인 2)
export MAX_JOBS=16
# 기동 필수 플래그:
#   --disable-custom-all-reduce   # GPU0↔GPU1 = SYS(P2P peer access 미지원) 확인됨 → 필수
#   --attention-backend triton    # 스모크는 flashinfer JIT 최소화용. 실런은 flashinfer도 위 env로 컴파일 가능(M-SGL 후속 확인)
```

**Phase 2용으로 확정된 SGLang server_args(실측)** — vLLM 대체 매핑:
| 논문/설계 개념 | SGLang 실측 인자 | 값(스모크) |
|---|---|---|
| GPU tier eviction 정책(typed 대상) | **`radix_eviction_policy`** (`--radix-eviction-policy`, 기본 `lru`) | typed eviction 등록 지점 후보 |
| CPU:GPU 용량비 | **`hicache_ratio`** (host:device) | 2.0 → host 9.66 GB 할당 확인 |
| HiCache 쓰기 정책 | `hicache_write_policy` | `write_through` |
| HiCache I/O 백엔드 | `hicache_io_backend` | `kernel` |
| HiCache 레이아웃 | `hicache_mem_layout` | `layer_first` |
| GPU 풀 핀 | **`max_total_tokens`** (`--max-total-tokens`) | §A-3 262144 핀에 사용 |

> ⚠ `hicache_ratio=2.0`인데 host 할당이 9.66 GB(device KV 풀 대비 정확히 2×인지)는 **OQ-E2에서 소스로 정합 확인** 필요(불변식 I6).

### A-3. KV 풀·CPU:GPU 비 (capping 미적용 + 36 GiB 핀) — 결정 #2 반영

**B_tok(8B) = 2×36×8×128×2 = 147,456 B = 144 KiB/tok** (모델 아키텍처 상수, 엔진 무관 — 재활용).

native KV 풀 추정:
```
TP2 usable = 63.68·0.92 ≈ 58.6 GiB − 가중치(8B bf16 ~15.3) − 오버헤드(~5) ≈ 38 GiB
→ native C_total ≈ 38·2^30/147456 ≈ 277k tok  (범위 270–310k, STEP1 SGLang 기동 로그 max_total_num_tokens로 확정)
native fit = 277k / peak(ec128k median 65,678) ≈ 4.2  → 논문 압박 레짐에 native 진입
```
⇒ **capping으로 압박을 만들 필요 없음(결정 #2).** `--max-total-tokens`를 measured native보다 약간 아래 라운드값으로 핀:
- **C_gpu = 262,144 tok = 36 GiB** (재현성·불변식 I6 정합용, 압박 생성 목적 아님).
- **C_cpu(host tier): 1× = 36 GiB(262k tok, hicache-ratio≈1) / 2× = 72 GiB(524k tok, hicache-ratio≈2).** 둘 다 0.6×185=111 GiB 이하로 안전.

**레짐 사이징 — 레버가 L로 이동(★):**
- L=128k(peak 65.7k) 유지 시 C=20 ws=1.31M > cap(2×)=3×262k=786k → C=20 이미 overflow(음성대조 상실). GPU가 작아 C_gpu를 올려 맞출 수 없음.
- ⇒ **L=64k, turn-window slicing으로 windowed median peak ≈38–40k**: C=20 ws≈780k ≈ 786k → fit(동률) ✅ / C=80 ws≈3.1M ≫ 786k → 강압박 ✅. **prefix truncation 금지(결정 #2).**
- STEP1 순서: ① 기동 로그로 native C_total 확정 → ② `--max-total-tokens` 핀 확정 → ③ L·목표 peak 확정(§C 게이트 검증).

### A-4. 하네스
`scripts/_serve_sglang_8b_tp2_mori_yunuikang.sh`(HICACHE_RATIO/MAXTOK env), `run_mori_eval_yunuikang.sh`(4종 셀렉터, `/health` router_mode·backend-type 가드), `mori_replay_driver_yunuikang.py`(§D). sampler `--gpus 0,1`.

---

## B. 코드 수정 지도 — 스케줄러부는 **[재활용] (엔진 무관)**, Phase 2만 SGLang로 재작성

### B-0~B-6. 스케줄러 설계 = base §B 그대로 (하드웨어·엔진 무관)
신규 `mori_idleness.py`(~120L)/`mori_tier.py`(~200L)/`mori_router.py`(~400L)/`mori_config.py`(~40L); 기존 순수추가 +34L(`config.py`+6/`__main__.py`+14/`app.py`+8/`program/state.py`+6); `router.py`·`backend/state.py` diff 0줄. ι 항상-on 링버퍼(진행 중 툴콜을 `now-acting_since`로 반영 — 재현 핵심), CPU tier 별도 모듈, `_pause_until_safe` lock 밖 → `mori_lock`으로 확장, `shared_tokens` dead-code 규약 통일, 불변식 I1~I5. 상세는 base §B 참조(변경 없음). **엔진 전환의 영향은 I6과 Phase 2뿐.**

### B-Phase. Phase 1 vs Phase 2 (SGLang)

> ⚠ **재스코프(결정 #6)로 이 표의 "Phase 1=모델링(reload_seconds sleep)"은 폐기됨.** 실 SGLang HiCache 위 완전 MORI(a+b) 직행. `mori_router`의 `reload_ready_at`/`reload_seconds`·`MoriConfig.reload_bw`는 M4-H에서 제거하고 `mori_tier`를 실 HiCache offload/reload에 매핑한다. 아래 표는 이력으로만 남김. §B-Phase2(typed eviction)는 여전히 유효(= M4-T의 핵심).

| | **Phase 1 — 스케줄러 전용 (엔진 무관, 先행)** | **Phase 2 — SGLang HiCache 실연동** |
|---|---|---|
| CPU tier 실체 | `mori_tier.py` 장부상 큐 | SGLang HiCache **host memory pool**(계층 radix의 host tier) |
| CPU→GPU 재로드 비용 | **비용 모델** `sleep(ctx×B_tok/BW_eff)`, BW_eff는 PCIe 마이크로벤치 실측(§D-4) | SGLang이 실제 host→device 전송으로 지불 |
| typed eviction | 없음(스케줄러 결정만) | **§Phase2 참조** — HiRadixCache 노드 타입 라벨 + 정렬키 패치 |
| 엔진 수정 | **0** (SGLang 설치조차 불필요) | SGLang 패치(monkey-patch 또는 fork) |
| **선후행** | **SGLang 검증과 무관하게 먼저 착수 가능(결정 #3)** | M-SGL 스모크 통과 후 |

**Phase 1을 먼저 하는 이유(결정 #3 명문화)**: MORI 핵심 주장(상대 idleness 랭킹 > context-length 랭킹)은 Phase 1만으로 TA vs MORI(sim) A/B로 검증 가능. SGLang sm_120 스모크가 막혀도 Phase 1은 진행된다.

### B-Phase2. ★ SGLang HiCache typed eviction (논문 §4.3.2, ~500줄) — vLLM 경로 대체

논문 §4.3.2의 typed eviction을 **SGLang HiCache의 radix tree** 위에 구현한다(vLLM `_CACHE_POLICIES`/`OffloadKey` 경로는 **삭제**):

- **자료구조**: SGLang HiCache는 prefix를 **radix tree 노드**로 보관하고, GPU(device)·CPU(host) 두 tier로 write-through/write-back 한다. 각 노드에 **program type 라벨(busy / idle / inactive)** 을 부착.
- **정렬키**: 기존 eviction은 노드 `last_access_time` 기반 **LRU**. MORI는 **type을 상위 정렬키, LRU를 tie-break**으로:
  - **GPU tier eviction 우선순위: inactive → idle → busy** (busy를 GPU에 최대한 유지)
  - **CPU(host) tier eviction: busy → idle → inactive** (반전 — host에는 곧 쓸 idle/inactive를 남김)
  - 동일 type 내부는 LRU.
- **통합 지점(설치 후 소스 대조 필수 — OQ-E2)**: HiRadixCache의 evict 함수(device evict / host evict). 노드 삽입·승격 시 소유 program의 현재 type을 스탬프. write policy(`--hicache-write-policy`)와의 상호작용 확인.
- **불변식 I6(SGLang판)**: `CpuTier.capacity_tokens == host_pool_tokens`(= `hicache-ratio × device_pool`). 기동 시 assert.

### Q4(재조사, SGLang판) — program_id→KV 스탬프 경로

- SGLang radix 노드는 **토큰-id prefix로 키잉**되며 program_id를 native로 담지 않는다(vLLM OffloadKey와 동형 문제). typed eviction을 하려면 **(request `rid` → program → type)** 매핑을 노드에 스탬프해야 함.
- 조사 대상: SGLang `Req` 객체의 `rid`/메타에서 노드 삽입 경로까지 program 라벨을 전파할 수 있는지(스케줄러가 rid↔program을 안다). **M-SGL 후, 설치된 소스에서 조사.**
- **불가 시 fallback**: Phase 2를 "**host tier 용량 제어만**(typed eviction 없이 hicache-ratio로 CPU:GPU 비만 구현)"으로 축소하고 그 사실을 §한계에 명기. (fallback도 SGLang HiCache 맥락 — vLLM으로 되돌리지 않음.)

---

## C. 데이터셋 — primary trace를 **논문 Fig.3 툴콜 분포에 최근접**시킨다

> **§C 목표 재정의(사용자 지시)**: MORI 논문 원 데이터를 못 구하므로, TraceLab primary를 논문 Fig.3 툴콜 duration 분포(human input·subagent 포함)에 **최대한 근접**시킨다. 58%(long-time-share)는 손잡이가 아니라 분포의 결과값 → **분포 자체를 맞춘다**. 논문 Fig.3이 human input을 툴콜에 포함하므로 비교는 **human-wait 포함 기준 apples-to-apples**(§C-3의 primary 채택과 정합). 최종 primary = (L=64k turn-window slicing) ∧ (툴콜 분포 매칭) 둘 다 만족(두 축 별개: KV 크기 vs 툴콜 duration).

### C-1. trace 자산 재현 확인 (본 턴, CPU-only meta 대조)
`scratch/traces/` 자산 전부 존재, meta가 base §C-1을 **정확 재현**: full 357,161턴 / ec128k 4,142세션·189,431턴·peak median **65,677.5** / ec40k 3,935·38,755·peak median **36,308**. ⇒ 서버·엔진 무관 데이터 설계(C-1~C-3) 재활용.

### C-2. goguma6 데이터 변경: **L 128k→64k (turn-window slicing 전용, 결정 #2)**
- 출력 `tracelab_mori_L64k_yunuikang.jsonl`. **prefix truncation 금지** — 중반부 보존형 turn-window slicing + 컨텍스트 rebase(SEED)만.
- base §C-3 8항목 검증표 + goguma6 추가 2항: **peak ≤ 64k**, **C=20 @ r=2 작업집합 ≤ C_gpu+C_cpu(레짐 fit)**.
- **확정 조건(결정 #2)**: 전이 median ≥ 4. ec40k가 40k에서 1.3으로 붕괴한 건 **prefix truncation**이라서였고, 우리는 turn-window slicing(중반부 보존)이므로 64k에서도 달성 가능성 높음 — **G1에서 실측 판정**(L 축소 최대 리스크).

### C-3. ★ 서브에이전트/human-wait 원본 조사 결과 (본 턴, CPU-only, `syfi_coding_trace.jsonl.gz` 120k라운드 샘플)

원본 스키마 키: `session_id, round_index, round_id, timing_events, tools[], first_input_event_type, input_tokens_total, ...`. 조사 결론:

- **서브에이전트**: 명시적 `parent_session_id`/`agent_type` 필드 **없음**. 서브에이전트 스폰은 `Agent` 툴 콜(샘플 463/120k ≈ **0.39% 라운드**)로 나타나고, **자식 실행 전체가 부모의 단일 긴 툴콜(`tool_wall_latency_ms`)로 이미 접혀 있음** → 논문 §3.1 프레이밍과 일치. **독립 program_id 분리 불가 → session=program 1:1 유지**(base option 3). 한계에 "서브에이전트 idle은 긴 `Agent` 툴 duration으로만 관찰"로 기록.
- **human-wait**: `first_input_event_type` 분포 = tool_result 87.3% / **user_message 10.4%** / None 2.3%. zero-tool 라운드 **10.2%**. prep 기본 경로는 이들의 tool_duration_s=0으로 만들어 인간 think 시간을 버리지만 —
  - **★ OQ-G 검증 완료(본 턴): `timing_events`는 실제 wall-clock 타임스탬프를 담는다 → human-wait는 "실데이터 복원"(모델링 아님).** user_message 라운드 직전 라운드의 마지막 이벤트 → 해당 user_message 이벤트의 wall gap이 실제 인간 대기: 표본에서 8.6/18.8/23.6/82.5/121.6/224.7/294.0/429.7/478.1 s 등 현실적 분포. 단 **54.7h(197,053 s) "유저 이탈" 아웃라이어** 존재.
  - **결정(사용자 규칙 "실데이터면 채택")**: human-wait를 **turn-window에 idle 구간으로 주입해 채택**. 근거: subagent가 1:1로 접힌 상황(§위)에서 human-wait까지 빼면 논문 Fig.4 idle 3대 원천 중 둘이 사라져 **idle 과소대표**.
  - **클램프**: §C-4 CAP 분석 결과 **`CAP_HARD=300 s`로 하향**(기존 1800s→300s; 논문 tail P99.95≈84s 스케일 근접 + MORI가 쓰는 분단위 idle 보존의 절충). **>12h(54.7h 등) human gap은 주입 제외**(세션 이탈, 실측 459건). 300s~12h 구간은 300s로 클램프.
  - **투명성(favorable bias)**: human-wait **유무를 ι 층화의 민감도 축**으로 두고 **양쪽 결과 병기**(§D-2 대조축). primary는 채택본, ablation으로 미주입본도 보고.

### C-4. ★ 논문 Fig.3 툴콜 분포 매칭 — 측정·gap·reshape 설계 (본 턴 CPU-only 측정)

**측정 방법**: 원본 gz(`syfi_coding_trace.jsonl.gz`, 357,161라운드/4,265세션)에서 **per-tool-call** duration(`tools[].tool_wall_latency_ms`, n=431,905 콜, subagent=`Agent`콜 1,156 포함)과 human-wait gap(timing_events wall-gap, n=33,501, >12h 459건 제외)을 산출. 가공본(ec128k/ec40k/swebench)은 per-turn `tool_duration_s`. (scratchpad 임시 측정, 원본·repo 무수정.)

**논문 target (Fig.3, n=16,886, human input·subagent 포함)**: P50 **1.096s** / P90 **2.034s** / P99 **19.98s** / P99.95 **83.63s** · 개수 short/long@2s **87/13%** · long(>2s) **time-share 58%**.

| 변형 (단위) | P50 | P90 | P99 | P99.95 | short/long@2s | long time-share |
|---|---|---|---|---|---|---|
| **논문 target** | 1.096 | 2.034 | 19.98 | 83.63 | 87/13 | **58%** |
| full per-call, tools만 | **0.196** | 8.17 | 180.0 | 1938 | 79.6/20.4 | **98.2%** |
| **full per-call, tools+human-wait (PRIMARY)** | 0.240 | 30.0 | 955.7 | 27284 | 74.2/25.8 | **99.7%** |
| full per-turn tool_s (base 98.5% 재현) | 0.188 | 10.2 | 210 | 2502 | 75.8/24.2 | 98.7% |
| ec128k per-turn | 0.155 | 7.06 | 150.8 | 300 | 79.7/20.3 | 96.3% |
| ec40k per-turn | 0.092 | 4.80 | 129.4 | 300 | 85.7/14.3 | 96.0% |
| swebench per-turn | 0.227 | 0.643 | 2.46 | 30 | 98.5/1.5 | **29.9%** |

**핵심 진단 (구조적)**:
1. **TraceLab short 콜이 너무 짧다**: P50=0.196s vs 논문 1.096s(−82%). exec_command/write_stdin 등 sub-초 콜이 과다 → **short 콜이 busy-time을 못 쌓는다**. 그래서 long-time-share가 98%+로 치솟음(논문 58%는 short 콜이 1.1s급이라 42%를 busy로 채움).
2. **human-wait 포함은 58%에서 더 멀어지게 한다**(98.2→99.7%). 그러나 이는 논문 정의(human 포함)와 정합이며, primary에서 **뺄 수 없다**(실데이터 삭제 금지). 58%는 swebench(29.9)와 full(98.5) 사이지만, TraceLab은 두 극단이 세션별로 **양극화**되어 있음(아래 층화).
3. **CAP만으로 58% 도달 불가**(아래): tail을 잘라도 long-time-share는 97~99%에서 거의 안 움직임 — 문제는 tail이 아니라 **short 콜의 빈약한 busy-time**이라서.

**human-wait gap 분포(s)**: n=33,501 · P50 **123** / P90 1,317 / P99 18,358 / P99.95 41,520 / max 43,198. `>300s 28.5%` · `>1800s 7.9%` · `>3600s 3.7%`. → 5분 넘는 human gap이 28.5%(대부분 "자리 비움") — CPU-tier가 겨냥하는 "곧 재개될 idle"이 아님.

**CAP_HARD sweep (primary per-call, 전 duration에 cap)**:
| cap | P99 | P99.95 | long time-share |
|---|---|---|---|
| 84s(논문 P99.95) | 84 | 84 | 97.2% |
| **300s (권장)** | 300 | 300 | 98.6% |
| 1800s(기존) | 956 | 1800 | 99.3% |
| no-cap | 956 | 27284 | 99.7% |

→ **CAP_HARD=300s 권장**: (a) 논문 분단위 스케일에 근접(84s보다 실데이터 존중), (b) 5분 초과 human "자리 비움"을 세션-일시정지로 처리(운영상 CPU-idle 아님), (c) MORI가 쓰는 분단위 idle은 보존. 84s는 **paper-strict ablation**로만(그 이하는 MORI가 필요로 하는 long idle을 지워 MORI에 불리·regime 파괴). **cap ∈ {300, 600} 민감도 병기.**

**ι 층화 (full, 세션 단위, human-wait 포함)** — **양극화가 핵심**:
| stratum | n | median long-time-share(세션) |
|---|---|---|
| busy-heavy ι<0.28 | 1,420 | **0.0%** (거의 전부 short 콜) |
| mixed | 1,425 | 97.5% |
| idle-heavy ι≥0.91 | 1,420 | 99.9% |
(세션 ι tercile q33=0.277 / q67=0.906, mean ι=0.574)
→ 세션이 **0% 또는 ~98%로 양극화**되어 단일 stratum이 58%에 없음. 그러나 **aggregate 58%는 busy-heavy(0%) + idle 세션을 blend**하면 조준 가능 → reshape의 세션 조합 방향(아래). **점 6 지시대로 stratum별로도 비교·보고**(저-ι stratum이 논문 유사 busy regime).

**reshape 방향 (설계만, 생성은 다음 승인)**:
- (1) **tail 정리**: `CAP_HARD=300s` 클램프(초장기·자리비움 제거). 없는 short 콜 **날조 금지**.
- (2) **세션 blend 선택**: busy-heavy stratum(0% long-share)과 idle stratum을 비율 조합해 **aggregate long-time-share를 58%에 최근접**시키는 subset을 탐색(선형 조합으로 목표값 조준). 동시에 §C-2의 전이 median≥4·L=64k 제약과 교집합.
- (3) **금지**: short 콜 길이 조작/합성. tail 정리 + 세션 선택으로 갈 수 있는 데까지만.
- (4) **투명성(구성된 매칭 명시)**: 가공 전 **원본 분포**, **blend 비율**(busy-heavy:mixed:idle 세션 몫), **소스 세션 분포**를 blend 결과와 **함께 병기**한다. "이 primary는 자연 분포가 아니라 논문 매칭을 위해 구성(constructed)된 subset"임을 meta·§한계에 명기.

**매칭 게이트(기존 게이트 병존)**:
- P50/P90/P99를 논문 대비 **best-effort 최근접**(허용오차 ±25%는 **목표치**로 보고하되, P50은 구조상 미달 가능 → **잔여 gap 수치 명기**가 통과 요건, hard-fail 아님).
- **long-time-share를 58%에 최근접**(blend 최적화 후 달성값·잔여 gap 병기).
- **CDF 거리(KS 통계) 최소화**(논문 CDF 대비).
- **기존 hard 게이트 유지**: 전이 median≥4, 동시점 ι IQR≥0.35, peak≤64k.

**정직한 한계(점 5)**: TraceLab은 논문과 다른 에이전트라 short-call busy-time이 구조적으로 빈약 → **58%·P50=1.1s에 정확히 못 맞출 수 있음**. 목표는 "**최근접 + 잔여 gap 수치 명기**", fabrication 금지. 이 gap 자체를 §한계에 정량 기록.

### C-4b. ★ reshape 1차 생성 + 감사 결과 — trilemma 발견, 2-track 결정 (본 턴)

병행 생성한 1차 primary(`tracelab_mori_L64k_yunuikang.jsonl`, 582세션/9,290턴)를 **jsonl에서 직접 재계산 감사**(에이전트 자기보고 불신):

| 게이트 | 실측(감사) | 판정 |
|---|---|---|
| 스키마/세션·턴/원본 무변경 | 0오류 / 582·9,290 / 원본 mtime 불변 | ✅ |
| peak ≤ 64k | 65,521 | ✅ PASS |
| long-time-share(per-turn) | **58.08%** | ✅ PASS (정확) |
| **전이 median ≥4** | **2.0** | ❌ FAIL |
| **ι-IQR ≥0.35 (최종 trace, per-session)** | **0.258** | ❌ FAIL |

**감사 catch (2건, 정밀 규명)**:
1. **게이트 실패는 windowing이 아니라 58% blend 선택이 유발.** ≥4턴 windowed **pool 전체(3,514세션)**는 전이 median **4.0**·ι-IQR **~0.69**로 두 hard 게이트를 이미 통과한다. 58% 조준 blend가 "mixed" 세션에 편중(선택 42:379:161)해 전이 4.0→2·ι-IQR을 붕괴시킨 것.
2. **ι-IQR은 reasoning-proxy의 uncached 정의에 민감(blend subset 한정).** 에이전트 0.643 = `uncached=claude_uncached_input_tokens`(≈3, 아주 작음), 내 감사 0.258 = `uncached=input−cached_read`. **pool에서는 두 프록시 모두 ~0.69로 무차이**; 프록시 민감성은 blend가 만든 좁은 분포에서만 증폭. **진짜 ι는 replay 시 런타임 스케줄러가 실측**(mori_idleness)하고 프록시 상수는 STEP1 보정 → **오프라인 ι-IQR 게이트는 advisory**. 전이 median은 프록시 무관(robust).

**★ 구조적 trilemma (핵심)**: **58% 매칭 ⟂ (전이≥4 ∧ ι-IQR≥0.35).** 두 극: (a) pool 그대로 → 전이 4·ι-IQR 0.69 ✅ 이나 long-share ~99% ❌; (b) 58% blend → long-share 58% ✅ 이나 전이 2·ι-IQR 붕괴 ❌. 근본 원인 §5-(12). → 단일 trace로 셋 동시 불가.

**결정 = 58% 폐기, Track M을 primary로 확정 (사용자 최종)**:
- **primary = Track M** `tracelab_moriM_L64k_yunuikang.jsonl` (3,514세션/**117,257턴**; rebase 버그 수정판, 음수 0): pool 전체(58% blend 제거) + ι-tercile 인터리브. **전이 median 4.0·ι-IQR 0.695·peak≤64k 전부 PASS**, long-share 98.8%(idle-heavy, by design). input median 32,376·max 65,536, output median 172. L=64k 유지(pool이 이미 통과 → L 조정 불필요). **재현: `python scripts/prep_tracelab_mori_yunuikang.py --track M`**.
  - **+ nohw ablation** = human-wait 미주입 동일 세션. **전이 median 2.0로 FAIL** → human-wait 주입이 전이를 2→4로 견인함이 드러남(human-wait의 기여를 정량화하는 진짜 ablation). primary는 반드시 hw-주입본.
- **Track P(58%)는 실험 arm에서 제외**(스윕 안 함). `--track P`로 재현만 가능; §5/deck에 **trilemma 증거**로 보존: "58% 강제 시 ι-IQR 0.69→0.26·전이 4→2 붕괴 — 58%는 논문 에이전트(짧은 콜 1.1s)의 창발 속성이라 우리 에이전트(0.24s)에선 재현 불가."
- 게이트 스펙(최종): **primary(Track M) hard = 전이≥4·ι-IQR≥0.35·peak≤64k**(전부 PASS). 58% 매칭은 목표에서 삭제. trilemma·분포 gap은 §5 기록.

---

## D. 스윕 + 프로토콜 (결정 #4 — 고정 벽시계 창 필수 승격)

### D-1. ★ 프로토콜 확정 — run-to-completion → 고정 벽시계 창 (필수)
`mori_replay_driver_yunuikang.py`(신규)에 **3가지 필수**:
1. **`--duration-s` deadline + 무한 순환 제너레이터**: 슬롯이 세션 완주 시 corpus에서 즉시 다음 세션 시작, deadline까지 순환.
2. **벽시계 창 내 완료-턴 단위 집계**: warmup(앞 20%) 제외 후, steady 구간의 **완료된 턴**만으로 지표 산출.
3. **TTFT 집계 + `--stream` 항상 on**: mean/p50/p95.

근거(결정 #4): run-to-completion은 **drain-bias**로 heavy-tail(=idle=MORI 우위) 세션을 통째로 버리고, 현재 하네스는 **TTFT 집계 부재**. 고정창이 이 둘을 동시 해결(+ base의 "최장세션 floor" 문제 소멸).

**게이트 추가(결정 #4)**: 무한 순환 제너레이터의 **corpus 다양성·사이클 셔플 검증** — 같은 trace 반복으로 SGLang prefix cache가 **인위적으로 warm**되지 않도록, (a) 사이클마다 세션 순서 셔플, (b) steady 구간 내 고유 세션 커버리지 ≥ 임계, (c) prefix cache hit rate가 사이클 반복으로 단조 증가하지 않음을 로그로 확인.

보고 지표(논문 §6.2와 1:1): `output_throughput_tok_s`, `step_throughput_req_s`, `ttft_mean/p95`, + `prefix_cache_hit_rate`·`local_compute` 참 recompute·GPU util(`sample_gpu_resident_yunuikang.py --gpus 0,1`)·`/health` tier 카운트.

### D-1b. ★ 기존 replay 하네스 조사 — 재사용성 (본 턴, 읽기 전용; 재발명 금지)

**base 드라이버 `scripts/trace_replay_driver_yunuikang.py`(482줄, dataset-agnostic, tool-scale 없음)가 논문 §6.1 기계를 이미 ~80% 보유** → 이걸 확장한다(expC 변형은 `--tool-scale` 있어 §1-1대로 제외).

| 논문 §6.1 요건 | 기존 위치 | 재사용 |
|---|---|---|
| 토큰 매칭(실 tokenizer로 prompt_tokens 일치) | `Padder` `:79-126` | 그대로 |
| closed-loop, 응답 후 `sleep(tool_duration)` 툴버블 | `run_program` `:278-279` | 그대로(= 논문 프로토콜) |
| 세션=프로그램, 컨텍스트 누적, `/programs/release` | `run_program` `:208-289` | 그대로 |
| TTFT 캡처(`--stream`) | `_chat_once` `:177-200` (`ttft`) | 그대로 |
| steady-state warmup 트리밍·throughput·prefix-hit | `summarize` `:376-429` | 그대로 |
| closed-loop C(Semaphore) | `build_program_list`+`main_async` `:306-359` | 오케스트레이션만 교체 |

**확장 필요(결핍 4곳만)**:
1. **고정 1h + 순환+셔플**: `main_async`(`:325`)이 **run-to-completion**(전 프로그램 gather). → C개 영속 워커가 셔플·순환 corpus에서 세션을 뽑아 `run_program`을 반복 호출, `--duration-s` deadline까지. `run_program`은 **그대로 재사용**(워커가 슬롯 역할).
2. **TTFT 집계**: `trace`에 `ttft_s`는 있으나 summary에 미집계 → steady 창의 ttft mean/p50/p95 추가(~10줄).
3. **SGLang 메트릭**: `_parse_prefix_cache`(`:131`)가 **vLLM 이름**(`vllm:prefix_cache_*`). → `ThunderAgent/backend/sglang_metrics.py:62-90`의 `sglang:cache_hit_rate/token_usage/num_used_tokens/prompt_tokens_total/generation_tokens_total`로 교체. **HiCache offload/reload 카운터는 현 클라이언트에 없음** → STEP1에서 live `/metrics`로 이름 확인 후 추가(OQ).
4. **순환 제너레이터 게이트**: 사이클마다 셔플·고유세션 커버리지·prefix-hit 비단조 로그(§D-1 게이트).

**설계**: 신규 `mori_replay_driver_yunuikang.py`가 base에서 `Padder/_chat_once/run_program/load_trace/_stats`를 **import**하고 위 4개만 추가. **원본 무수정**(베이스라인 재현). eval 러너 `run_serving_eval_yunuikang.sh`(`/health` FATAL 가드·per-C 샘플러 보유)를 `run_mori_eval_yunuikang.sh`로 복제해 `--backend-type sglang`+HiCache 플래그+시스템셀렉터+`--gpus 0,1`로 교체.

### D-2. 스윕 축·셀 (재스코프: 실 HiCache 18셀)
**실 SGLang HiCache 위 18셀**(모델링 Phase 없음): **SMG(3=C) + TA(3=C) + TA+O(6=r×C) + MORI(6=r×C)**, C{20,50,80}, r{1×,2×}는 오프로딩 시스템(TA+O·MORI)만. **MORI 셀 = 완전 MORI(a+b)** 단일 버전. **우선 셀당 1런 → 결정 셀(C=80·r=2× 등)만 repeat 추가**(non-overlap 판정용). **Duration = 1h**(`--duration-s 3600`).
- 시스템↔엔진 매핑(실 HiCache): SMG=`--router default`+HiCache OFF / TA=`--router tr`+HiCache OFF / TA+O=`--router tr`+`--enable-hierarchical-cache --hicache-ratio r` / MORI=`--router mori`+`--enable-hierarchical-cache --hicache-ratio r`+`--radix-eviction-policy mori`(typed).
- **primary = Track M**(`tracelab_moriM_L64k_yunuikang`, 전 hard 게이트 PASS) **+ nohw ablation**. Track P(58%)는 실험 arm 제외. 대조 = `ec128k`·`swebench`(저-idle). **idleness 연속 스펙트럼**: swebench(≈30%)↔Track M/ec(≈97%) + ι 3분위 층화. 엔진 재기동 최소화(HiCache OFF/1×/2× 바깥루프).
- **human-wait ablation 축(§C-3/§C-4)**: primary(주입, CAP_HARD=300s) vs ablation(미주입) **양쪽 병기**. CAP 민감도 {300,600}.
- **ι 층화 보고(점 6)**: aggregate가 idle-heavy여도 **저-ι stratum(busy-heavy)은 논문 유사 regime** → 시스템 비교를 **stratum별로도** 분해 보고(저-ι에서 MORI 이득이 논문에 가장 근접해야 함).

### D-3. GPU-node-hours (goguma6 = 1 TP2 노드, 고정창)
GPU 2개 모두 단일 TP2 replica에 소진 → 예비 없음, 직렬 스윕. 고정 20분창 × 1노드 → **구조상 nutella와 동일 ≈ 38 GPU-node-h**(Phase2 18셀×3≈19.4h + Phase1 12셀×3≈13h + 마이크로벤치·스모크·가공≈6h). **별도**: SGLang 설치·sm_120 스모크·HiCache 연동 디버깅 시간(불확실, M-SGL).
**표본 충분성(OQ-B/D)**: 20분창 완료 턴 수는 SGLang decode tok/s에 비례. 145 tok/s는 vLLM/nutella 값 → STEP1에서 SGLang/5090 실측 후 부족 시 창 연장(시간↑).

### D-4. 마이크로벤치 (base 계승, GPU 0,1)
`microbench_pcie_kv_yunuikang.py`(pinned host↔GPU0/1, KV블록 2.25MiB, 2스트림, cross-NUMA `numactl` 바인딩). Phase 1 `BW_eff` 보정.

### D-5~D-6. 예측·판정 [재활용] base §D-5/§D-6 (P1: C=80·r=2×에서 MORI≥1.15×TA+O tput & ≤0.85×TTFT; P3 위생 C=20 동률; P4 격리 tr 브랜치 무관 ±3%). 통계·무효화 동일.

---

## E. 오픈 퀘스천 · 마일스톤

### E-1. 오픈 퀘스천 (SGLang 갱신)
| Q | 내용 | 해소 시점 | 못 풀면 |
|---|------|-----------|---------|
| **OQ-A** | native C_total(KV 풀) 정확값 | STEP1 SGLang 기동 로그 `max_total_num_tokens` | 추정 38G로 진행 |
| **OQ-B** | SGLang/5090 decode tok/s | STEP1 | ι 프록시·표본 반영 |
| **OQ-C** | L 최종값(peak 목표) | trace-prep G1(OQ-A 의존) | 잠정 L=64k |
| **OQ-D** | 20분창 표본 충분? | STEP1/M4 | 창 연장 |
| ~~OQ-E1~~ | **✅ 해소**: sglang 0.5.10이 sm_120에서 실구동(§A-2b). 툴체인 env만 필요 | 완료(본 턴) | — |
| **OQ-E2** | HiRadixCache evict **통합 지점**(플래그는 §A-2b서 확정: `radix_eviction_policy`/`hicache_*`) + host 할당 정합 | M-SGL 후 소스 대조 | Phase 2 host-용량만 fallback |
| ~~OQ-F~~ | **✅ 해소(M4-T)**: SGLang에 `PriorityStrategy=(node.priority,last_access)` 존재. 라우터가 OpenAI `priority`로 타입 주입→`Req.priority`→`node.priority`(insert 시 자동 스탬프). GPU-tier 엔진패치 불요. host 역순만 `evict_host` 전략스왑 | 완료 | — |
| **OQ-F2** | 전이 시 재스탬프(host 보존). **판정(소스)**: promote→busy는 처리됨(resume 요청 priority=f(ι)+insert max). **demote→idle 즉시 재스탬프는 엔진 측 깔끔히 불가**(`cache_finished_req` 후 Req 해제·program→node 인덱스/priority-update API 없음). ι가 윈도우(k=5) 평균이라 지속 idle은 이미 high-ι→low-priority로 host 보존; 잔여=**빠른 busy→idle 전이 transient staleness**. shared-prefix max 수용 | **M-SMK 실측·게이트** | 무시 수준→정적 수용+명기 / 유의미→헤드라인 전 해결. **host 보존 깨진 채 헤드라인 금지** |
| **OQ-I** | HiCache offload/reload 메트릭명(현 sglang_metrics 클라이언트에 없음) | STEP1 live `/metrics` | driver `--hicache-metrics` 확장점 |
| **OQ-J** | ★ **64k 서빙엔 YaRN 필요**: Qwen3-8B 파생 context=**40960**, `--context-length 65536`이면 SGLang 사망(STEP1 실측). L=64k 유지=YaRN 활성(`SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=1`+rope_scaling factor≈1.6; vLLM 트랙은 YaRN 검증), 또는 L=40k로 재슬라이스 | STEP1 재기동 전 결정 | vLLM와 동일 YaRN 권장 |
| **OQ-G** | human-wait wall-gap 복원 채택? | M1 prep 설계 | 미채택 → 한계 기록 |
| **OQ-H** | Qwen3-8B HF 캐시 존재 여부 | STEP1 전 | 재다운로드(~16GB) |

### E-2. 결정 (반영 완료)
엔진 **SGLang v0.5.10+HiCache** / 모델 **8B 고정** / **duration 1h×18셀(결정셀 repeat)** / **capping 없음+36GiB 핀** / **L=64k(turn-window만)** / **모델링 Phase 1 폐기 → 완전 MORI(a+b) 실 HiCache 직행** / typed eviction=`--radix-eviction-policy mori` 등록.

### E-3. Blackwell/goguma6 위험 (SGLang 갱신)
| 위험 | 상태 | 완화 |
|------|------|------|
| ~~SGLang sm_120 미구동~~ | **✅ 해소(스모크 PASS)**. sm_120 문제 아니었음 | §A-2b env(CUDA_HOME+gcc-11) 고정, `--disable-custom-all-reduce` 필수 |
| flashinfer 어텐션 실런 컴파일(스모크는 triton) | 미확인(툴체인 해소로 가능성 높음) | M-SGL 후속: 위 env로 `--attention-backend flashinfer` 컴파일·성능 확인 |
| GPU0↔GPU1 P2P peer access 미지원(SYS) | 확인됨 | `--disable-custom-all-reduce` 필수(스모크 반영). NCCL fallback |
| Phase 1이 SGLang에 막힘 | 없음 | Phase 1은 엔진 무관 → 선행 |
| 8B 가중치+KV가 32G/GPU에 빡빡 | 8B 여유 | 8B 고정 |
| GPU0↔GPU1 SYS cross-NUMA | 실측 확인 | `numactl` 마이크로벤치 |
| serve orphan → 다음 셀 OOM | 동일 | pid kill + `nvidia-smi` 확인 |
| 순환 제너레이터 prefix 인위 warm | 신규 | §D-1 셔플·다양성 게이트 |

### E-4. 마일스톤 (SGLang 반영)
| M | 내용 | GPU | ★게이트 |
|---|------|-----|---------|
| **M0** | `mori` 브랜치 | ✕ | ✅ **완료** |
| **M1** | trace 가공(**L=64k turn-window + Fig.3 분포 매칭**). 조사·분포 측정 **본 턴 완료**(§C-3/§C-4), 가공 생성·스크립트화는 다음 승인 | ✕ | **G1**: §C-2 8항 + **매칭 게이트**(P50/P90/P99 최근접·gap 명기, long-share→58% 최근접, KS 최소) + hard(전이 median≥4·ι IQR≥0.35·peak≤64k) |
| **M-SGL** | ✅ **설치+스모크 PASS(본 턴)**. 잔여: flashinfer 실런 컴파일 확인 + 소스 대조(OQ-E2/F) | ○ | **G-SGL: 스모크부 통과**(기동+요청+HiCache host 할당 확인). 잔여는 M5 착수 전 |
| **M3** | ✅ **Phase 1 구현 완료(본 턴)**: `mori_config/idleness/tier/router` + 기존 4파일 순수추가(+수십줄) + 테스트 2개. | ✕ | **G3 통과**: `router.py`·`backend/state.py`·`profile/state.py` **diff 0줄**, 순수모듈·배선·정책(demote ι-desc/promote ι-asc/CPU-full→Waiting fallback/release)·**I1** 테스트 PASS. 잔여: 실엔진 회귀(P4)는 M4/M-SGL서 |
| **M4-H** | ✅ **완료(본 턴)**: `mori_replay_driver`(base import + 고정1h·순환셔플·TTFT집계·SGLang메트릭·순환게이트) + `run_mori_eval`(시스템셀렉터+FATAL가드) + `_serve_sglang_8b_tp2_mori`+launcher. **reload_seconds 모델 제거 → 실 HiCache 매핑.** 원본 driver 무수정 | ✕ | ✅ dry-run 토큰매칭 within_1pct=1.0 + `tr`/state diff 0 |
| **M4-T** | ✅ **완료(본 턴)**: `mori_hicache.install()` — 'priority'/'mori' 등록 + `evict_host` host-역순 전략스왑; 라우터 ι→`priority` 주입(busy=2/idle=0). OQ-F 해소(엔진패치 불요) | ✕ | ✅ `.venv-sglang` install 검증; 런타임은 M-SMK(GPU) |
| **STEP1** | native 풀→`--max-total-tokens` 핀 · decode tok/s · HiCache 메트릭명. **1차 시도(본 턴): 서버 사망**(OQ-J: context 40960<65536) → 측정 미획득. **YaRN 결정 후 재기동 필요**. 부수 성과: Track M 음수 버그 발견·수정 | ○ | 값 확정, 리뷰 |
| **M-SMK** | **완전 MORI(a+b) 실 HiCache 스모크**: offload/reload 실동작 + typed eviction 활성 + `tr` 회귀(P4) + **OQ-F2 host-evict 실측**(EVICT=mori vs priority A/B: idle-host-KV 조기 evict율·host reload율) | ○ | 정상 응답 + HiCache 카운터 + 장부↔host ±10% + **OQ-F2 판정**(무시/유의미) |
| **M-SWP** | **헤드라인 스윕 1h×18셀**(SMG/TA/TA+O/MORI(a+b)) + 결정셀 repeat + ec/swebench/nohw | ○ | §D-6 P1~P4 (두 렌즈·ι층화 병기). **전제: M-SMK에서 host 보존 무손상 확인**(OQ-F2) |
| **M7**(선택) | 32B / multi-replica / k ablation / (a)-only 대조 | ○ | — |

의존(재스코프): M0·M1·M-SGL·M3 **완료** → **M4-H ∥ M4-T (CPU, 리뷰)** → **STEP1**(GPU) → 리뷰 → **M-SMK**(GPU, 완전 MORI 검증) → **M-SWP**(GPU, 1h×18). 모델링 Phase 1(구 M4)·PCIe µbench **폐기**. (a)-only는 M4-T 막힐 때 폴백.

---

## 5. 정직 기록 (§한계)
base §5의 8개 유효(단 **엔진 항목 반전**): 이제 **엔진이 논문과 동일(SGLang+HiCache)** → 절대 수치 비교 가능성 개선. 그 외 DP=1 / L=64k 전이보존 리스크 / Phase1 비용모델 / recompute 오염 / shared_tokens dead-code / trace≠논문(idle-heavy 편향) 유효. **goguma6 추가**:
- **(9)** native HBM이 논문 압박 레짐에 근접(fit≈4)해 인위 축소 최소 — 방법론적으로 더 정직. 대신 L=64k의 전이보존 영향을 G1에서 검증.
- **(10)** ✅ SGLang sm_120 구동 확정(스모크 PASS, §A-2b). 단 goguma6는 SGLang JIT에 툴체인 env(CUDA_HOME=/usr/local/cuda-13.0, gcc-11) 고정 필요 — serve 스크립트에 반드시 박아야 함. Phase 2 남은 전제는 typed-eviction 소스 통합(OQ-E2/F).
- **(11)** 서브에이전트는 session=program 1:1(독립 분리 불가). human-wait는 실데이터로 복원해 primary 채택(§C-3).
- **(12) ★ 논문 Fig.3 분포 gap = 측정 한계로 명기(가공으로 안 메움)**: primary(Track M) long-time-share **98.9% vs 논문 58%**, 원인은 **short 콜 median 0.24s vs 논문 1.096s**(다른 에이전트 → busy-time 구조적 빈약). 58%는 논문 에이전트의 **창발 속성**이라 재현 불가로 판단, **58% 조준을 폐기**(Track P 제외). 대신 **idleness를 연속 스펙트럼으로 커버**: `swebench`(≈30%, 저-idle) ↔ `Track M`/`ec128k`(≈97–99%, 고-idle) + ι 3분위 층화 → "idleness는 스펙트럼"이라는 논문 §3.3 취지와 정합. gap 자체를 결과에 정량 병기, fabrication 없음.
- **(13) primary는 구성된(constructed) subset**: 논문 매칭용 세션 blend로 만든 것이라 자연 도착분포가 아님 — blend 비율·원본 분포·소스 세션 분포를 병기(§C-4-(4)).
- **(14) TP2 no-P2P/SYS 인터커넥트**: GPU0↔GPU1이 NVLink 없이 cross-NUMA(SYS)라 P2P peer access 미지원 → `--disable-custom-all-reduce`로 NCCL fallback. TP all-reduce·PCIe 오프로딩 대역이 느려 **절대 throughput에 하향 영향**. 단 4종 시스템 모두 동일 인터커넥트라 **상대 비교는 보존**(MORI vs TA+O 결론에 영향 없음). 절대 수치를 논문과 직접 비교하지 않는다.
- **(15) ★ 데이터 trilemma(§C-4b, 감사로 확정)**: TraceLab에서 (논문 58% regime) + (전이 median≥4) + (ι-IQR≥0.35)는 **동시 불가**. 그래서 primary를 **2-track**(Track P=58% 매칭, Track M=ι 이질성)으로 분리해 병기한다. 어느 단일 trace도 세 조건을 다 만족하지 못한다는 것 자체가 결과 해석의 전제 — MORI 이득은 두 렌즈에서 각각 보고한다.

## 6. 다음 액션
1. **(M1, CPU-only, 완료분)** 서브에이전트/human-wait 조사(§C-3)·Fig.3 분포 측정·gap·CAP·층화(§C-4) **본 턴 완료**. 남은 것: L=64k turn-window + 세션 blend **가공 생성·스크립트화 → 다음 승인**(편집금지 유지).
2. **(M-SGL)** ✅ 설치·스모크 PASS. 남은 것: flashinfer 실런 컴파일·성능 확인(GPU, 승인 시).
3. **(M3, 병행)** Phase 1 스케줄러 구현 착수 가능(엔진 무관).

> 본 계획서는 GPU 미점유(nvidia-smi/CPU-only 조사만), 코드·trace·스크립트 무수정으로 작성. `mori` 브랜치 생성 외 저장소 변경 없음.
