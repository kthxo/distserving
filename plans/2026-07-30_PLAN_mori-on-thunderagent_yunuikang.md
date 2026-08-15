# 연구 계획 — MORI(Relative Idleness 3-tier 오프로딩)를 ThunderAgent 위에 구현·평가

> 작성: 강윤의 · 브랜치 `yunuikang/thunderagent` → 신규 `mori` · **2026-07-30** · **계획만(코드 편집 없음, 본 턴은 읽기 전용 탐색만 수행)**
> 저장소 `/home/yunuikang/yunuikang_work/distserving` (기존 fork, 재clone 금지) · 서버 **nutella**
> 논문: `/home/yunuikang/yunuikang_work/MORI.pdf` (arXiv:2606.00866v1, 15p) — 본 계획서의 모든 논문 인용은 이 PDF 전문을 직접 읽고 대조함
> 선행 권위 문서(계승):
> - `logs/2026-07-24_EARLYCUTOFF_2HW_NUTELLA_RESULTS_yunuikang.md` — nutella C_total=1,150,112 tok(8B/40k), 디코드 145 tok/s, 기동 gotcha
> - `plans/2026-07-23_PLAN_tracelab-earlycutoff-8b-2hw_yunuikang.md` — early-cutoff prep 설계·게이트 형식
> - `logs/2026-07-19_STEPS_RESULTS_yunuikang.md` — 전환점 fit×d\*=0.62, 참 hit는 `local_compute`로만, goodput 사용
>
> **원칙: 기존 `router_mode="tr"`·`"default"` 경로와 원본 trace/스크립트 무수정. MORI는 신규 모듈 + 런타임 선택 플래그로 격리. 신규 파일 전부 `*_yunuikang` 또는 `mori_*`. GPU는 1·2번만(GPU0 = 타 사용자 muchwater, 미접촉).**

---

## 0. 한 문단 요약

MORI는 ThunderAgent 스케줄러에 (1) 프로그램별 상대 idleness ι = T_acting/(T_reasoning+T_acting) (최근 k=5 스텝 윈도우, 스케줄러 pause 시간 제외), (2) GPU/CPU/Waiting **3-tier 큐**, (3) sticky 배치 + typed eviction 세 가지를 얹은 시스템이다. 현재 ThunderAgent에는 GPU(=`BackendState._programs`)와 Waiting(=`global_waiting_queue`) 2단만 있고 **그 사이 CPU tier가 통째로 없다**. 본 계획은 이를 신규 모듈 `scheduler/mori_*.py` + `MoriRouter(MultiBackendRouter)` 서브클래스로 추가하여, 한 코드베이스에서 플래그만 바꿔 **SMG / TA / TA+O / MORI 4종**을 A/B 한다. 구현은 **Phase 1(스케줄러 전용, 재로드 비용 모델로 CPU tier 시뮬레이션, 엔진 무수정)** → **Phase 2(vLLM 네이티브 KV 오프로딩 실물 연동 + typed eviction)** 2단계로 나눈다.

**이번 탐색에서 드러난 사용자 요약 대비 4개 중대 정정**은 §1에 먼저 정리한다. 이것들은 계획 전체를 바꾸는 사실들이므로 먼저 읽어야 한다.

---

## 1. ★ 사용자 요약 대비 정정 사항 (실측/실제 코드 근거)

| # | 사용자 요약 | **실제(근거)** | 계획에 미치는 영향 |
|---|-------------|---------------|-------------------|
| **1** | "인퍼런스 엔진: SGLang (v0.5.10 + HiCache)" | **SGLang은 설치되어 있지 않음.** `pip show sglang` → 없음. 실제 엔진은 **vLLM 0.24.0** (`.venv`), 하네스 전부 `--backend-type vllm`, 기동 스크립트 전부 `vllm serve`. `ThunderAgent/backend/sglang_metrics.py`는 존재하지만 이 환경에서 한 번도 쓰인 적 없음(scripts 전체 grep 결과 sglang 참조는 deck 빌더 1개뿐) | **SGLang으로 갈아타지 않는다.** vLLM 0.24가 이미 **네이티브 CPU KV 오프로딩**을 가지고 있음: `--kv-offloading-size <GiB>` / `--kv-offloading-backend {native,lmcache}` → `OffloadingConnector` + `vllm/v1/kv_offload/cpu/`. HiCache의 대체물로 이것을 쓴다(§A-3, §B-Phase2) |
| **2** | "GPU: RTX 5090 × 2, 각 32GB, TP=2" | `nvidia-smi`: **GPU0 = RTX PRO 5000 Blackwell 48GB(타 사용자), GPU1/GPU2 = RTX PRO 6000 Blackwell Max-Q 96GB × 2**. 즉 TP2 = GPU1+2 = **HBM 191 GiB**. CPU DRAM = **251 GiB total / 231 GiB available** | **CPU:GPU 2× 비율이 물리적으로 불가능**해질 수 있음. 8B 풀 GMU 0.92 = KV 158 GiB → 2× = 316 GiB > 231 GiB DRAM. → GPU KV 풀을 `--kv-cache-memory-bytes`로 **의도적으로 축소**해야 1×/2× 두 축이 모두 성립(§A-4). 동시에 이것이 MORI가 필요한 메모리 압박 레짐을 만드는 유일한 방법이기도 함 |
| **3** | "기존 전처리가 `--cap-tool-s`·session-drop·early-cutoff로 heavy tail을 잘라낸다" | **부분적으로만 맞음.** 실측(§C-1): tool clamp는 실제로 tail을 자름(full P99.9=971 s, max=154,089 s → ec 계열은 300 s에서 클램프). 그러나 **early-cutoff가 진짜로 파괴하는 것은 tail이 아니라 "세션당 turn 수 = phase 전이"**다. full=17.6 전이/세션(54.8% 세션), **ec40k=1.3 전이/세션(35%)**, ec128k=8.6(55.5%) | tail 보존만으로는 부족. **turn 수(=phase 전이) 보존이 더 중요한 제약**. 그래서 prefix-truncation이 아니라 **turn-window slicing** 신규 prep을 제안(§C-3) |
| **4** | "profile_enabled일 때만 켜지므로 항상-on 경로 필요 여부 판단" | **항상-on 경로가 필요함이 확정.** `router.get_or_create_program:316`에서 `profile_enabled`일 때만 `ProfileState` 생성. 게다가 `ProfileState.on_request_end`는 **매 스텝 CSV append I/O**를 하므로 스케줄링 의존물로 쓰기 부적절 | ProfileState를 손대지 않고, `Program`에 **경량 idleness ring buffer**를 별도 추가. 계측점은 ProfileState와 동일한 지점(항상 호출되는 `update_program_before/after_request`)을 재사용(§B-2) |

### 1-1. 부수적으로 확인된 사실 (계획에 반영)

- **`BackendState.update_shared_tokens()`는 아무도 호출하지 않음** (`grep` 결과 정의부 1곳뿐). 즉 `shared_tokens`는 영구히 0이고, `remaining_capacity()`/`capacity_overflow()`는 **prefix 공유를 전혀 반영하지 않는다.** 기존 tr 베이스라인의 실제 동작이므로 **고치지 않는다**(베이스라인 무수정 원칙). 단 MORI의 CPU tier 용량 회계도 같은 규약(공유 무시)을 써야 TA+O와 공정 비교가 됨 → §B-3 불변식에 명시.
- `--router`의 `choices=["default","tr"]` (`__main__.py:16`) → `"mori"` 추가 필요.
- `app.py`는 `router_mode == "tr"` 로만 `scheduling_enabled`를 정함(`app.py:242`). MORI는 여기 분기 추가가 유일한 app.py 수정.
- 기존 replay driver(`trace_replay_driver_yunuikang.py`)의 종료 조건은 **고정 프로그램 수**다 — `asyncio.gather(*[run_program(...) for progs])` over `--num-programs`(`:349-357`). `--duration`/deadline/`time_limit` 인자도, 러너 셸의 `timeout` 래퍼도 **어디에도 없다**(세 드라이버 + 4개 러너 grep 확인). `wall`은 부과값이 아니라 측정값. → 기존 로그의 "128k는 최장세션 E2E 13.7 h가 점당 floor"가 정확히 이 구조 때문. **단, 슬롯 동작 자체는 이미 MORI와 동일**하다(§D-1 대조표) — 다른 것은 종료 조건과 집계 창 두 가지뿐이므로 신규 드라이버는 재작성이 아니라 **3가지 추가**로 끝난다.
- 기존 driver는 `--stream`으로 turn별 `ttft_s`를 기록하지만 **summary에 TTFT 집계가 없음**. MORI 3대 지표 중 하나이므로 신규 driver에 집계 추가 필요.
- `--tool-scale`은 expC driver에만 있음. **MORI 평가에서는 tool 시간 스케일링 금지**(idleness 구조 자체를 왜곡).

---

## A. 실험 환경·셋업

### A-1. git / 브랜치 전략

`distserving`은 **이미 git repo**다(재init 불필요).

```
origin  git@github.com:kthxo/distserving.git
현재 브랜치: yunuikang/thunderagent (origin과 동기, HEAD=3801143 "tracelab cutoff plans scripts")
untracked: logs/2026-07-24_EARLYCUTOFF_2HW_NUTELLA_RESULTS_yunuikang.md  (1개)
.gitignore: scratch/, slides/, .venv/, *.egg-info/  → trace 자산·결과는 비추적(정상)
```

절차:
1. untracked 로그 1건을 먼저 커밋해 baseline을 깨끗이 만든다 (`git add logs/2026-07-24_*.md && git commit`).
2. `git checkout -b mori` — 이 브랜치에서만 작업. `yunuikang/thunderagent`는 TA/TA+O 베이스라인의 **비교 기준(무수정 증거)**으로 보존.
3. MORI 코드가 기존 경로를 건드리지 않았다는 것을 매 커밋마다 기계적으로 검증:
   `git diff yunuikang/thunderagent..mori -- ThunderAgent/scheduler/router.py ThunderAgent/backend/state.py` 의 diff가 **0줄**이어야 함(§B의 설계는 이를 만족하도록 짜여 있음). config.py/`__main__.py`/app.py는 각각 +6/+14/+8줄 이내 순수 추가만 허용.

### A-2. 엔진 기동 — 현재 플래그와 MORI용 확장

현재(= 논문의 **TA**, 오프로딩 없음). `scripts/_serve_vllm_8b_tp2_yunuikang.sh` 기준:

```bash
CUDA_VISIBLE_DEVICES=1,2 vllm serve Qwen/Qwen3-8B \
  --tensor-parallel-size 2 --port 8100 \
  --max-model-len 40960 --gpu-memory-utilization 0.92 \
  --max-num-batched-tokens 2048 --max-num-seqs 256
# env: VLLM_USE_FLASHINFER_SAMPLER=0, VLLM_ATTENTION_BACKEND=FLASH_ATTN,
#      HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1  (체크포인트 shard gotcha 회피)
```
→ **오프로딩 플래그 없음이 확인됨. 현재 상태 = TA이지 TA+O가 아니다(사용자 판단 맞음).**

MORI/TA+O용 추가 플래그(vLLM 0.24 실측 확인):

| 플래그 | 의미(소스 근거) | MORI 용도 |
|--------|-----------------|-----------|
| `--kv-offloading-size <GiB>` | `CacheConfig.kv_offloading_size`. **TP>1일 때 전 랭크 합산 총량**(`config/cache.py:176-180`). 설정 시 `kv_transfer_config.kv_connector="OffloadingConnector"`, `cpu_bytes_to_use = size<<30` (`config/vllm.py:782-798`) | CPU tier 물리 용량. 1×/2× 축을 여기서 만든다 |
| `--kv-offloading-backend native` | `native`(vLLM 자체 CPU 오프로딩) / `lmcache` | `native` 사용(외부 의존 없음) |
| `--kv-cache-memory-bytes` | GMU와 무관하게 KV 풀 크기를 직접 고정 | GPU tier 용량을 실험 변수로 만듦(§A-4) |

관련 vLLM 내부 구조(Phase 2 연동 지점, 실측 확인):
- `vllm/v1/kv_offload/cpu/manager.py:29` — `_CACHE_POLICIES = {"lru": LRUCachePolicy, "arc": ARCCachePolicy}` **정책 레지스트리(문자열 → 클래스)**. HiCache typed eviction의 vLLM 대응물을 여기에 `"mori"`로 등록 가능.
- `vllm/v1/kv_offload/cpu/policies/base.py` — `CachePolicy` ABC: `get/insert/remove/touch/evict(n, protected)/clear`. `evict`가 유일한 정책 결정점 → **type을 상위 정렬키로, LRU를 tie-break으로** 만들면 논문 §4.3.2가 그대로 재현됨.
- ⚠ **제약**: `OffloadKey = block_hash(bytes) + group_idx` (`kv_offload/base.py:31-38`) — **program_id를 담고 있지 않다.** typed eviction을 하려면 (request → program → type) 매핑을 `OffloadingConnectorScheduler`(Request 객체 접근 가능) 단에서 블록에 스탬프해야 함. → §E 오픈 퀘스천 Q4.

### A-3. 베이스라인 4종 = (라우터 모드 × 엔진 오프로딩) 2×2 조합

| 논문 시스템 | 라우터 플래그 | 엔진 플래그 | 근거 |
|-------------|--------------|------------|------|
| **SMG** (SGLang model gateway) | `--router default` (순수 프록시) | 오프로딩 OFF | 논문 §6.1: "In the DP=1 configurations, this reduces to directly forwarding requests to the inference engine" — DP=1에서 SMG ≡ 직결 포워딩. 우리 `default` 모드가 정확히 그것 |
| **TA** | `--router tr` | 오프로딩 OFF | 논문의 ThunderAgent 그대로 = 현재 상태 |
| **TA+O** | `--router tr` (무수정) | `--kv-offloading-size R` | 논문 §6.1: 스케줄러는 TA의 context-length 기반 GPU eviction 유지, CPU tier는 엔진 LRU가 독립 관리 |
| **MORI** | `--router mori --mori-cpu-capacity-ratio R` | Phase1: OFF / Phase2: `--kv-offloading-size R` (+ `--kv-offloading-policy mori`) | 신규 |

→ **한 코드베이스, 플래그 3개(라우터 모드 / 오프로딩 크기 / 정책)만으로 4종 전환.** 엔진 재기동이 필요한 축은 오프로딩 크기뿐이므로, 스윕 순서를 "엔진 config 바깥 루프"로 잡아 재기동 횟수를 3회/repeat로 최소화(§D-2).

주의: DP=1이므로 논문의 **affinity-aware load balancing(§4.1, Fig.10)은 평가 대상에서 제외**된다. 우리 하네스는 백엔드 1개(serving-eval 재프레이밍, `logs/2026-07-16` 결정)를 쓴다. multi-replica는 §E 마일스톤 M5(선택).

### A-4. KV 풀 크기와 CPU:GPU 용량비 (1× / 2×) 설정법 — ★ 가장 중요한 셋업 결정

**문제**: nutella는 GPU가 너무 크다. 8B TP2 GMU 0.92 → C_total = 1,150,112 tok(실측) ≈ **158 GiB KV**. 이 상태에서
- 2× CPU tier = 316 GiB > 231 GiB 가용 DRAM → **물리적으로 불가능**
- 게다가 `fit = C_total/입력크기 = 31.7` (실측) → 메모리 압박이 아예 없어 **MORI가 할 일이 없다**(논문도 C=20에서 MORI vs TA+O 격차 2%라고 명시)

**해결**: `--kv-cache-memory-bytes`로 GPU KV 풀을 **의도적으로 축소**해 논문의 레짐(H200 80 GB급 압박)을 에뮬레이션한다. 논문 자신도 §6.1에서 "H200 (80 GB) configuration emulates H100-class memory capacity by capping an H200's available HBM"라고 같은 짓을 한다 → **방법론적으로 정당**.

사이징 공식(토큰 단위로 통일):

```
C_gpu  [tok] = kv_cache_memory_bytes / B_tok        # B_tok = 토큰당 KV 바이트(TP 전체 합)
C_cpu  [tok] = r × C_gpu ,  r ∈ {1, 2}
kv_offloading_size [GiB] = C_cpu × B_tok / 2^30     # DRAM 소요. ≤ 0.6 × 231 GiB 여야 안전

B_tok = 2(K,V) × L층 × H_kv × d_head × 2 bytes
      Qwen3-8B : 2×36×8×128×2 = 147,456 B = 144 KiB/tok   (계산치, STEP 1에서 기동 로그로 검증)
      Qwen3-32B: 2×64×8×128×2 = 262,144 B = 256 KiB/tok   (계산치)
```

레짐 선택 기준(논문 Fig.7~9의 모양을 재현하려면):
- **C=20에서는 GPU+CPU 안에 대체로 들어가야** 한다 → 모든 오프로딩 시스템이 동률(논문: 2% 차)
- **C=80에서는 GPU+CPU를 확실히 초과**해야 한다 → eviction 정책이 성능을 가름

⇒ 목표: `C_gpu × (1+r) ≈ Σ_{i=1..20} peak_ctx_i` (r=2 기준)

ec128k 트레이스 실측 median peak context = 65,678 tok → C=20 작업집합 ≈ 1.31 M tok
⇒ **C_gpu ≈ 1.31M / 3 ≈ 437 k tok = 60 GiB (8B)**, CPU 1×=60 GiB / 2×=120 GiB DRAM. 231 GiB 안에 여유 있게 들어감. ✅
C=80이면 작업집합 5.25 M tok ≫ 용량 1.31 M → 강한 압박. ✅

**권장 시작점(STEP 1에서 확정)**: 8B / `--kv-cache-memory-bytes 64424509440`(60 GiB) / `--kv-offloading-size {60,120}`.
32B로 갈 경우 B_tok이 1.78배라 같은 토큰 수에 107 GiB 필요 → 2×가 214 GiB로 DRAM 한계 → **32B는 C_gpu를 더 줄여야 함**. 초기 실험은 **8B 고정**을 권장(기존 early-cutoff 트랙과 자산·측정치 재사용 가능).

### A-5. 하네스에서 4종을 같은 방식으로 돌리기

기존 `scripts/run_serving_eval_yunuikang.sh`(단일 백엔드 + :9000 프록시, 프록시 모드 검증 후 스윕)의 골격을 그대로 계승하되, MORI용으로 **격리 복제**한다:

- `scripts/_serve_vllm_8b_tp2_mori_yunuikang.sh` — 기존 8b_tp2 스크립트의 복제 + `KVOFF`(GiB, 0이면 미지정), `KVBYTES` env 추가. **원본 무수정.**
- `scripts/run_mori_eval_yunuikang.sh <system: smg|ta|tao|mori> <out.jsonl> <trace> [C...]` — system → (라우터 모드, 오프로딩 크기) 매핑을 스크립트 안에서 하고, `/health`로 `router_mode`를 재확인(기존 스크립트의 FATAL 가드 계승).
- `scripts/mori_replay_driver_yunuikang.py` — §D-1의 **고정 시간창 closed-loop** 드라이버(신규).

---

## B. 코드 수정 지도

### B-0. 격리 구조 (기존 파일 diff 최소화가 설계 목표)

```
신규 (전부 새 파일):
  ThunderAgent/scheduler/mori_idleness.py   ~120 L   ι 링버퍼·윈도우 계산
  ThunderAgent/scheduler/mori_tier.py       ~200 L   CPU tier 자료구조 + 용량 회계
  ThunderAgent/scheduler/mori_router.py     ~400 L   MoriRouter(MultiBackendRouter) 서브클래스
  ThunderAgent/scheduler/mori_config.py     ~40  L   MoriConfig 데이터클래스(k, tier 용량, PCIe BW, ...)

기존 파일 수정 (순수 추가만, 총 +40줄 이내):
  ThunderAgent/config.py       +6   MoriConfig 필드 4개
  ThunderAgent/__main__.py     +14  --router에 "mori" 추가 + --mori-* 인자
  ThunderAgent/app.py          +8   _create_router()에서 router_mode=="mori" → MoriRouter
  ThunderAgent/program/state.py +6  Program에 기본값 있는 필드 3개 추가(동작 변화 0)

수정 금지 (diff 0줄이어야 함):
  ThunderAgent/scheduler/router.py      ← MoriRouter가 서브클래싱만 함
  ThunderAgent/backend/state.py         ← CPU tier는 mori_tier.py가 별도 보유
  ThunderAgent/profile/state.py
  scripts/prep_tracelab*_yunuikang.py, scripts/trace_replay_driver*_yunuikang.py
  scratch/traces/*  (원본 trace)
```

핵심: `MultiBackendRouter`의 스케줄링 진입점 5개가 전부 **메서드**라서, 서브클래스 오버라이드만으로 정책을 통째로 갈아끼울 수 있다 — `_scheduled_check`, `_pause_until_safe`, `_greedy_resume`, `update_program_before_request`, `update_program_after_request`. `app.py`의 라우트 등록은 `ta_router` 인스턴스를 인자로 받으므로(`register_routes(app, ta_router, config)`) 서브클래스가 그대로 꽂힌다.

### B-1. `ThunderAgent/program/state.py` — idleness 원자료 보관소

사용자 요약 검증: ✅ `ProgramStatus.REASONING/ACTING`(11-19), `Program(status, acting_since, context_len, total_tokens, step_count)`(33-47) 전부 존재. `origin_backend`, `marked_for_pause`, `waiting_event`도 있음.

추가(전부 기본값 있음 → 기존 경로 동작 불변):
```python
idle_window: Optional[object] = None   # mori_idleness.IdlenessWindow, mori 모드에서만 생성
tier: str = "gpu"                       # "gpu" | "cpu" | "waiting" — mori 모드에서만 갱신
reason_started_at: Optional[float] = None  # 현재 REASONING 구간 시작(항상-on 계측용)
```
리스크: **낮음**(dataclass 필드 추가, 기본값 존재). 불변식 I4(§B-6)로 tr 경로 무영향을 테스트로 고정.

### B-2. idleness 계측 — 어디서 시간을 재는가 (★ 정정 4의 해결)

`profile/state.py` 검증 결과(사용자 요약 대체로 맞음, 단서 있음):
- `StepMetrics`에 `prefill_time / decode_time / pause_time / tool_call_time` **분리 기록됨**(20-23). ✅
- `tool_call_time`은 `on_request_arrive`에서 `now - last_request_end_time`으로 계산되고, `on_request_arrive`는 `app.py:72`에서 **pause 체크 이전**에 호출된다 → **순수 툴 시간**. ✅
- `pause_time`은 `on_request_start`(app.py:79, pause 이후)에서 arrive→start 차이 → **스케줄러가 강제한 대기**. ✅ 논문 §4.1의 "waiting time is excluded from both" 요건과 계측점이 정확히 일치.
- ❌ 그러나 `ProfileState`는 `profile_enabled`일 때만 생성되고, `on_request_end`마다 **CSV 파일 append**를 한다. 스케줄링 핫패스 의존물로 부적합.

**설계**: `ProfileState`를 건드리지 않고, `MoriRouter`가 **동일한 계측점**에서 경량 링버퍼를 갱신한다. `update_program_before/after_request`는 profile 여부와 무관하게 **항상** 호출되므로 여기서 다 된다.

```
MoriRouter.update_program_before_request(pid, state, payload):
    t_arrive = time.time()                       # 툴 갭 종료 시점(= 순수 acting 끝)
    if state.last_response_end is not None:
        state.idle_window.push_acting(t_arrive - state.last_response_end)
    rv = await super().update_program_before_request(...)   # ← 이 안에서 pause 대기 발생 가능
    state.reason_started_at = time.time()        # pause 이후 = reasoning 시작 → pause 자동 제외
    return rv

MoriRouter.update_program_after_request(pid, state, total, prompt):
    now = time.time()
    state.idle_window.push_reasoning(now - state.reason_started_at)
    state.last_response_end = now
    super().update_program_after_request(...)
```

- `T_reasoning`은 prefill+decode를 따로 재지 않고 **요청 서비스 시간 전체**로 잡는다. 스트리밍 콜백(`on_first_token`) 없이도 동작하고, 논문 정의("time spent in Reasoning status")와 일치. prefill/decode 분해가 필요하면 `--profile`을 켜서 `ProfileState`로 별도 획득(측정용, 스케줄링과 무관).
- **진행 중인 툴 콜의 반영**: 논문 §4.2의 "responsive" 성질("ongoing tool call's elapsed time keeps increasing and soon dominates")은 push 시점에만 갱신하면 재현되지 않는다. → `IdlenessWindow.value(now)`가 **현재 ACTING 중이면 `now - acting_since`를 진행 중 항으로 더해서** ι를 계산해야 한다. **이것이 MORI 재현의 핵심 디테일**이며, 빠뜨리면 "긴 툴콜에 들어간 프로그램을 demote"하는 동작 자체가 안 생긴다.
- 링버퍼 크기 k=5(논문 전 실험 고정). `--mori-k`로 노출(민감도 ablation용).

`mori_idleness.py` API:
```python
class IdlenessWindow:
    def __init__(self, k: int = 5)
    def push_acting(self, dt: float) -> None
    def push_reasoning(self, dt: float) -> None
    def value(self, now: float, acting_since: Optional[float]) -> float   # 0..1, 표본 없으면 0.5
    def n_samples(self) -> int
```
예상 diff: **신규 120줄**. 리스크: 낮음(순수 함수). 단위 테스트로 (a) 전부 짧은 툴 → ι→0, (b) 긴 툴 진행 중 → ι가 시간에 따라 단조증가, (c) 긴 툴 1회 outlier가 짧은 툴 5회에 희석 검증.

### B-3. CPU tier — `mori_tier.py` (`backend/state.py` 무수정)

사용자 요약 검증: ✅ `BackendState._programs`가 GPU tier(50), `capacity_overflow`/`remaining_capacity`/`shared_tokens`(165-214), `BUFFER_PER_PROGRAM=100`(23). 
단, §1-1대로 `shared_tokens`는 항상 0(호출자 없음).

**설계**: `BackendState`에 필드를 추가하는 대신, `MoriRouter`가 backend_url → `CpuTier` 매핑을 **자기 안에** 들고 있는다. 이러면 `backend/state.py` diff가 0이 되고, tr 경로의 용량 계산식이 한 글자도 안 바뀐다.

```python
class CpuTier:
    url: str
    capacity_tokens: int                 # = ratio × backend.cache_config.total_tokens_capacity
    _programs: Dict[str, Program]
    def used_tokens(self) -> int         # Σ total_tokens + n × BUFFER_PER_PROGRAM (GPU와 동일 규약)
    def remaining(self) -> int
    def admit(self, pid, state) -> bool  # 용량 검사 후 등록
    def evict_candidates(self) -> List   # ι 최소순(=promote 후보) / inactive→busy→idle 순
```
- 용량 회계는 **GPU tier와 동일 규약**(prefix 공유 무시, 프로그램당 버퍼 100)으로 통일 → TA+O와의 비교가 회계 방식 차이로 오염되지 않음. **불변식 I2.**
- Phase 1에서 `capacity_tokens`는 순수 스케줄러 측 숫자(실제 DRAM 미사용). Phase 2에서 `--kv-offloading-size`와 **반드시 같은 값**으로 맞춘다(불일치 시 스케줄러는 여유가 있다고 믿는데 엔진은 이미 축출 → 조용한 성능 붕괴). 기동 시 검증 assert 추가.

예상 diff: **신규 200줄**.

### B-4. 스케줄링 정책 — `mori_router.py`

사용자 요약 검증(전부 실제 코드로 확인):

| 사용자 요약 | 실제 위치 | 판정 |
|-------------|-----------|------|
| `global_waiting_queue` = Waiting tier | `router.py:93` `Dict[str, PausedInfo]` | ✅ |
| `_scheduler_loop`/`_scheduled_check` 5 s tick | `746-771`, interval은 config(기본 5.0) | ✅ (논문 tick 기본 5 s와 동일) |
| `_pause_until_safe`가 demotion, 현재 `total_tokens` 최소순 | `773-805`: ACTING 우선(`ascending=True`=**작은 것부터**), 그 다음 REASONING mark | ✅ |
| `_greedy_resume`이 promotion + BFD | `807-932`: 우선순위 REASONING(step>1) → NEW(step=1) → ACTING, 각 그룹 토큰 오름차순, 그 후 BFD 배치 | ✅ |
| `update_program_before/after_request`가 상태 전이 훅 | `371-458`, `460-498` | ✅ |

**MORI 정책 매핑** (논문 §4.3.1 ↔ 우리 코드):

| 논문 | ThunderAgent 대응 | MoriRouter 오버라이드 |
|------|-------------------|----------------------|
| Demotion from GPU: ACTING 우선, 동일 status 내 **ι 최대** 먼저 | `_pause_until_safe`의 정렬키 `total_tokens` 오름차순 | **정렬키를 ι 내림차순으로 교체.** 목적지가 다름: 기존은 Waiting(KV 폐기), MORI는 **CPU tier 우선, 불가 시 Waiting** |
| Lazy demotion (REASONING은 현재 스텝 완료 후) | `_mark_program_for_pause` + `update_program_after_request`의 `marked_for_pause` 처리 | **기존 메커니즘 그대로 재사용**(이미 lazy) — 다만 pause 시 목적지를 CPU로 |
| Promotion to GPU 우선순위: (1) 툴콜 끝난 CPU 큐 (2) Waiting returning (3) 신규 small-context. 각 레벨 내 **ι 최소** | `_greedy_resume`의 3그룹 + 토큰 오름차순 | **CPU tier를 최상위 우선순위 그룹으로 추가**, 각 그룹 정렬키를 ι 오름차순으로. BFD 배치는 DP=1이므로 실질 무의미(그대로 둠) |
| Sticky: 매 tick 재배치 금지, mismatch일 때만 이동 | 기존도 사실상 sticky(용량 위반 시에만 pause) | **명시적으로 유지.** 추가 제약: 한 tick에서 같은 프로그램의 demote+promote 금지(진동 방지), tier 이동 후 `min_dwell_ticks=1` 쿨다운 |
| CPU→GPU 재로드 비용 | 없음 | **Phase 1: 비용 모델 sleep** / Phase 2: 엔진이 실제 지불 |

`_scheduled_check` 오버라이드 골자:
```
1. fetch_metrics (super와 동일)
2. 모든 program의 ι를 now 기준으로 1회 스냅샷 → 랭킹 (tick 내 일관성 보장)
3. GPU 용량 위반 시 demote:  ACTING(ι 내림차순) → REASONING(ι 내림차순, lazy)
     목적지: CPU tier.admit() 성공 → tier="cpu"; 실패 → Waiting(기존 _pause_program)
4. CPU 용량 위반 시 demote:  CPU tier에서 ι **최대**부터 Waiting으로(KV 폐기)
5. GPU 여유 시 promote:  [CPU∧요청대기] → [Waiting∧returning] → [Waiting∧신규] 순,
     각 그룹 ι 오름차순. CPU→GPU는 재로드 비용 지불 후 waiting_event.set()
```

⚠ **동시성 위험(가장 큰 구현 리스크)**: 기존 코드는 `pause_resume_lock`으로 `global_waiting_queue` 접근만 보호한다(`_greedy_resume`는 lock 안, `_pause_until_safe`는 **lock 밖**). CPU tier가 추가되면 (GPU, CPU, Waiting) 3자 간 이동이 생겨 lock 범위를 넓혀야 한다. → **`_scheduled_check` 전체를 하나의 `mori_lock` 안에서** 돌리고, 데이터 플레인(`update_program_before_request`)은 tier 조회만 lock-free로 하되 이동은 스케줄러 tick에만 일어나도록 제한(= 논문의 "periodic control loop"와도 일치).

예상 diff: **신규 400줄**.

### B-5. Phase 1 vs Phase 2

| | **Phase 1 — 스케줄러 전용 (엔진 무수정)** | **Phase 2 — 실물 오프로딩 연동** |
|---|---|---|
| CPU tier 실체 | 스케줄러 장부상의 큐. 실제 KV는 GPU에 남아 있거나(엔진 prefix cache에) 사라짐 | vLLM `OffloadingConnector`가 실제로 DRAM에 저장 |
| CPU→GPU 재로드 비용 | **비용 모델**: `sleep(ctx_tokens × B_tok / BW_eff)`를 promote 시 지불. `BW_eff`는 마이크로벤치로 실측(§D-3) | 엔진이 실제 PCIe 전송으로 지불 |
| Waiting→GPU 비용 | 자연스럽게 full prefill로 지불 — **단 caveat**: 라우터가 pause해도 엔진 prefix cache가 블록을 들고 있으면 실제 recompute가 안 일어나 비용이 과소평가됨(기존 트랙에서 이미 알려진 문제, `VLLM_PROFILING §1-2`). `local_compute` 카운터로 참 recompute를 검증해야 함 | 동일 caveat |
| typed eviction | 없음(스케줄러 결정만) | `_CACHE_POLICIES["mori"]` 신규 `CachePolicy` 등록. GPU: inactive→idle→busy, CPU: inactive→busy→idle, 동타입 LRU |
| 엔진 수정 | **0** | vLLM 패치 필요(monkey-patch 또는 fork). §E Q4 |
| 얻는 것 | 논문 §4.2/§4.3.1(ι 지표 + 3-tier 정책)의 효과를 **엔진 변수 없이** 격리 측정 | 논문 §4.3.2 포함 완전 재현 |
| 리스크 | 비용 모델의 타당성이 결론을 좌우 | Blackwell sm_120에서 OffloadingConnector 동작 미확인 |

**Phase 1을 먼저 하는 이유**: Phase 2가 막히더라도(§E Q1 리스크) MORI의 핵심 주장(상대 idleness 랭킹이 context-length 랭킹보다 낫다)은 Phase 1만으로도 TA vs MORI 비교로 검증 가능하다. 또 Phase 1은 TA+O 없이 **TA vs MORI(sim)** 라는 깨끗한 A/B를 준다.

### B-6. 불변식 (테스트로 고정)

| ID | 불변식 | 검증 방법 |
|----|--------|-----------|
| **I1** | 모든 program은 정확히 한 tier. `GPU._programs ∪ CpuTier._programs ∪ global_waiting_queue` 는 서로소이고 합집합 = `router.programs` | 매 tick 끝에 assert(디버그 빌드) + `/health`에 tier별 카운트 노출 |
| **I2** | `Σtok(GPU)+n·100 ≤ C_gpu` 이고 `Σtok(CPU)+m·100 ≤ C_cpu` (tick 종료 시점) | tick 종료 assert. **용량 초과 방지가 MORI의 admission control 그 자체** |
| **I3** | `waiting_event`는 **GPU tier로 promote될 때만** set. CPU tier에 있는 프로그램의 요청은 계속 블록 | 논문 §4.1 "Incoming requests are gated until the program is promoted back to the GPU queue" |
| **I4** | `--router tr|default`로 띄우면 MORI 코드가 **전혀 실행되지 않음** | `MoriRouter`는 `router_mode=="mori"`일 때만 생성. + `git diff`로 router.py/backend/state.py 0줄 확인 |
| **I5** | 한 tick 안에서 같은 프로그램이 demote+promote 되지 않음 | tick 내 이동 프로그램 집합 추적 |
| **I6** | Phase 2에서 `CpuTier.capacity_tokens × B_tok == kv_offloading_size` | 기동 시 assert (불일치 시 FATAL) |

---

## C. 데이터셋 점검·사용법

### C-1. 서버 trace 자산 목록화 + 실측 특성 (본 턴에서 직접 측정)

위치: `/home/yunuikang/yunuikang_work/scratch/traces/` (git 비추적)

| 파일 | 세션/턴 | tool_s P50 / P90 / P99 / P99.9 / max | >2 s 턴 비율 / 그 tool-time 점유 | 세션 ι(mean) | 윈도우 ι(k=5) busy<0.2 / idle>0.8 | busy phase P50/P90 | 전이/세션 | MORI 적합성 |
|------|---------|--------------------------------------|-------------------------------|-------------|-----------------------------------|--------------------|-----------|-------------|
| `tracelab_trace_full.jsonl` (**cap 없음**) | 4,265 / 357,161 | 0.169 / 10.0 / 180.9 / 971.3 / **154,089** | 22.0% / **98.5%** | 0.341 | 49.6% / 19.2% | 9.6 s / 77.7 s | **17.6** | ★ 원본. tail·전이 모두 보존 |
| `tracelab_earlycutoff_128k_yunuikang.jsonl` (cap 300) | 4,142 / 189,431 | 0.155 / 7.06 / 150.8 / 300 / 300 | 20.3% / 96.3% | 0.335 | 51.7% / 17.7% | 9.5 s / 73.1 s | **8.6** | ○ 차선. 전이 절반 보존 |
| `tracelab_earlycutoff_40k_yunuikang.jsonl` (cap 300) | 3,935 / 38,755 | 0.092 / 4.80 / 129.4 / 300 / 300 | 14.3% / 96.0% | 0.256 | 59.9% / 12.1% | 8.2 s / 38.9 s | **1.3** | ✕ **전이 붕괴**(세션 median 5턴) |
| `tracelab_fit32k.jsonl` (cap 30 + session-drop) | 982 / 6,107 | 0.047 / 9.97 / 30 / 30 / **30** | 19.8% / 95.9% | 0.289 | 56.9% / 16.8% | 4.6 s / 29.8 s | 0.9 | ✕ tail·전이 모두 파괴 |
| `swebench_trace.jsonl` (cap 30) | 64 / 1,388 | 0.227 / 0.641 / 2.42 / 30 / 30 | 1.5% / 29.9% | **0.042** | **99.0% / 0.0%** | 98.2 s / 301 s | 0.6 | ✕ **degenerate**(d=0.958, 사용자 지적 확인) |
| `syfi_coding_trace.jsonl.gz` (51 MB) | 원본(TraceLab/SyFI 릴리스) | — | — | — | — | — | — | 재가공 소스 |
| `mini_trace.jsonl`, `tracelab_char25_notool.jsonl` | 소형 | — | — | — | — | — | — | 스모크용 |

측정 스크립트: `/tmp/.../scratchpad/char_traces.py` (본 턴 임시본) → **정식 버전을 `scripts/char_mori_trace_yunuikang.py`로 커밋 예정**(읽기 전용, 원본 미변경).
ι 계산 시 T_reasoning은 `uncached_input/8000 + output/145` [s] 프록시(디코드 145 tok/s는 nutella 실측). 프록시 상수는 §C-4에서 실측으로 교정.

**논문 트레이스와의 대조** (논문 Fig.3/§3.3 vs TraceLab full):

| | 논문(Claude Code, SWE-bench Pro, n=16,886) | TraceLab full(n=357,161) | 해석 |
|---|---|---|---|
| tool P50 | 1,096 ms | **169 ms** | TraceLab의 짧은 콜이 훨씬 더 짧음 |
| tool P90 / P99 | 2,034 ms / 19,980 ms | **10,008 ms / 180,883 ms** | TraceLab tail이 **9배 무거움** |
| 긴 콜(>2 s) 비율 / tool-time 점유 | 13% / 58% | **22% / 98.5%** | TraceLab이 **더 idle-heavy** |
| busy phase P50 / P90 | 20 s / 81 s (2 s 임계) | **9.6 s / 77.7 s** | P90 거의 동일, P50은 절반 |

→ **결론: TraceLab full은 MORI 평가에 논문 트레이스보다 오히려 유리하다**(idle 창이 더 크고 더 자주 온다). "high/mixed idleness" 요건 충족. 사용자의 우려("기존 전처리가 idle 창을 지운다")는 **가공본에 대해서는 맞고, 원본에 대해서는 문제없음**.

### C-2. 반드시 점검할 것 — 전처리가 실제로 무엇을 지우는가

`scripts/prep_tracelab_yunuikang.py` / `prep_tracelab_earlycutoff_yunuikang.py` 코드 감사 결과:

1. **`--cap-tool-s`** (`:102-103` `td = min(td, cap)`): 값만 클램프, 턴은 유지. ec 계열은 300 s → 189,431턴 중 894개(0.47%)만 클램프. **tail 손상은 생각보다 작다.** 단 fit32k의 30 s 클램프는 P90(10 s) 바로 위를 자르므로 **치명적**.
2. **`--max-input-tokens` = session-drop** (`:93-95`): 한 턴이라도 초과하면 **세션 전체 삭제**. fit32k가 4,265→982 세션(77% 소실). idle-heavy 세션은 대개 긴 세션이므로 **선택 편향**이 생김.
3. **early-cutoff = prefix truncation**: 세션은 다 살리지만 뒤를 자른다. **이게 진짜 문제**: ec40k는 세션당 median 17턴 → **5턴**, 전이 17.6 → **1.3**. 논문이 요구하는 "programs alternate between busy and idle phases"가 **거의 사라진다**.
4. **★ human-in-the-loop 대기가 원천 제거됨**: prep docstring — "rounds that open a human turn carry no tools[], so their tool_duration_s is 0". full에서 zero-tool 턴이 **13.6%**. 논문 §3.3이 드는 idle phase 3대 원인(긴 툴콜 / **인간 상호작용** / 서브에이전트) 중 하나가 통째로 빠져 있다. → §E Q5.

### C-3. ★ MORI용 trace 가공 절차 (신규, 원본 무수정)

목표 3요건:
- **(a) tail 보존** — 긴 툴콜이 실제 idle 창을 만들어야 함
- **(b) 프로그램 내 busy↔idle 전이** — sticky 배치와 ι 응답성이 발동하려면 필수
- **(c) 동시점 프로그램 간 ι 이질성** — "상대" 랭킹이 의미를 가지려면 필수

prefix truncation으로는 (b)를 못 지킨다(§C-2.3). 대신 **turn-window slicing**을 쓴다.

신규 스크립트 `scripts/prep_tracelab_mori_yunuikang.py` (원본 두 prep 파일 무수정, 함수만 import 재사용):

```
입력: tracelab_trace_full.jsonl (cap 없음, 4,265 세션 / 357,161 턴)

STEP 1  이상치 제거(최소한만)
  - tool_duration_s > CAP_HARD(기본 1800 s = 30분)인 값만 클램프.
    full 기준 >300 s가 0.655%, >60 s가 3.46% → 1800 s 클램프는 사실상 42.8 h 단일 outlier만 제거.
    (ec 계열의 300 s 대신 1800 s를 쓰는 이유: 논문 §3.3 "extend to minutes in the tail"을 보존)

STEP 2  turn-window slicing  ← prefix truncation 대체
  각 세션에서 "연속 turn 윈도우 [i, j]" 중 다음을 만족하는 최장 윈도우를 고른다:
      max_{t∈[i,j]} input_tokens[t] - (input_tokens[i] - SEED) <= L
  즉 윈도우 시작점의 누적 컨텍스트를 SEED(기본 4096 tok)로 rebase 하고,
  그 윈도우 안에서의 컨텍스트 증가분이 L 안에 들어가게 한다.
  → 세션 앞부분이 아니라 "컨텍스트 예산 안에 들어가는 가장 긴 구간"을 취하므로,
    긴 세션의 중반부(전이가 많은 구간)를 살릴 수 있다.
  구현 주의: driver가 컨텍스트를 누적 생성하므로, rebase는 "큰 seed 프롬프트로 시작하는
  세션"으로 재현된다. prefix 공유 의미론은 보존됨(윈도우 내부 누적은 원본 그대로).

STEP 3  세션 선별 + ι 층화 (요건 b, c)
  - 필터: 윈도우 턴수 >= MIN_TURNS(기본 12) AND busy<->idle 전이 >= MIN_TRANS(기본 2)
  - 층화: 세션 ι를 3분위(busy-heavy ι<0.2 / mixed 0.2~0.6 / idle-heavy >0.6)로 나누고
    각 1/3씩 샘플링 → 동시 실행 집합의 ι 이질성을 설계로 보장
  - driver가 세션을 라운드로빈으로 슬롯에 배정하므로, 출력 파일의 세션 순서를
    3분위 인터리브로 써 둔다(같은 시점에 세 부류가 공존하도록)

출력: scratch/traces/tracelab_mori_L{L}_yunuikang.jsonl  + .meta.json (기존 meta 스키마 계승)
```

**검증 기준(게이트 2에서 이 표를 채워 통과 판정)**:

| 항목 | 합격선 | 근거 |
|------|--------|------|
| tool_s P99 | ≥ 60 s | full=180.9 s. tail 보존 |
| tool_s P90 | ≥ 5 s | full=10.0 s |
| >2 s 콜의 tool-time 점유 | ≥ 80% | full=98.5%, 논문=58% |
| 세션당 busy↔idle 전이 | median ≥ 4 | full=17.6, ec128k=8.6, **ec40k=1.3(불합격)** |
| 세션당 턴 수 | median ≥ 12 | full=17 |
| 윈도우 ι(k=5) 분포 | busy(<0.2) ≥ 35% **AND** idle(>0.8) ≥ 12% | full=49.6/19.2 |
| **동시점 ι 이질성** | 드라이런 replay 시뮬레이션에서, 임의 시각의 활성 프로그램 ι **IQR ≥ 0.35** | 단일 duty 상수 합성 trace는 IQR≈0 → degenerate 배제 |
| peak context | ≤ L (전 세션) | 서빙 가능성 |

마지막 항목(동시점 ι IQR)은 **신규 지표**다. 사용자가 지적한 "단일 duty 상수 합성 trace는 degenerate"를 정량적으로 배제하는 유일한 검사이므로, `char_mori_trace_yunuikang.py`에 replay 시뮬레이터(툴 sleep + 추정 reasoning 시간으로 타임라인 재구성)를 넣어 측정한다.

**L 선택**: `L = min(모델 윈도우, 0.5 × C_gpu)`. 8B native 윈도우는 40,960이지만 **YaRN 131,072 기동이 이미 검증됨**(nutella STEP B, C_total=1,149,216). §A-4 권장 C_gpu=60 GiB=437 k tok이면 `L = min(131072, 218k) = 131,072`. → **L=128k 권장.** 단 §E Q6(YaRN이 품질/속도에 주는 영향)을 스모크로 확인.

### C-4. 서브에이전트 → 별도 program_id

논문 §3.1: "Each subagent is an independent program separate from the parent process... From the parent agent's perspective, the subagent's entire execution could be treated as a single (potentially long) tool call." 즉 **서브에이전트는 부모의 긴 툴콜 = idle 창의 3대 원인 중 하나**다.

TraceLab이 부모/자식 세션을 어떻게 표현하는지는 **미확인**(§E Q5). 확인 절차:
1. `syfi_coding_trace.jsonl.gz` 원본 레코드의 필드 전체를 덤프해 `parent_session_id`/`agent_type`/Task-tool 흔적을 찾는다.
2. 있으면: 자식 세션을 **독립 program_id**로 replay하고, 부모의 해당 턴 `tool_duration_s`를 자식 세션의 wall span으로 맞춘다(현재도 그렇게 기록됐다면 그대로).
3. 없으면: 현재대로 세션 = 프로그램 1:1을 유지하고, "서브에이전트 idle은 긴 tool_duration_s로만 관찰된다"고 §한계에 기록.

DP=1이므로 서브에이전트의 multi-replica 함의(논문 §6.2.2 churn)는 이번 범위 밖.

---

## D. 실험 스윕 + 예상 소요시간 및 결과

### D-1. ★ 측정 프로토콜을 논문식 "고정 시간창"으로 전환

논문 §6.1: "Each concurrency slot is a closed-loop client that replays a single Claude Code trace... Once a trace completes, the client immediately starts a new one from the trace corpus. **All experiments run for a fixed duration of one hour**, and we report metrics aggregated over the entire run."

**★ 기존 드라이버와의 정확한 차이 (코드 확인 결과 — 생각보다 작다)**:

| 항목 | 기존 `trace_replay_driver_yunuikang.py` | MORI 논문 §6.1 | 판정 |
|------|------------------------------------------|----------------|------|
| 동시성 모델 | `asyncio.Semaphore(C)` closed-loop (`:337,350`) | closed-loop slot | ✅ 동일 |
| 슬롯 재사용 | 프로그램 완주 → 세마포어 해제 → 대기 중 다음 프로그램 즉시 시작 | "Once a trace completes, the client immediately starts a new one from the trace corpus" | ✅ **동일** |
| 툴 갭 재현 | `await asyncio.sleep(tool_duration_s)` (`:301`) | "sleeping for the recorded duration" | ✅ 동일 |
| 프로그램 단위 | 세션 1개 = program_id 1개, 끝나면 `/programs/release` | 동일 | ✅ 동일 |
| **종료 조건** | **완주 프로그램 수** — `gather` over `--num-programs` (`:349-357`). deadline 인자 없음, 러너에 `timeout` 래퍼 없음 | **고정 1시간** | ❌ **여기만 다름** |
| **집계 창** | 완주 **순서** 기준 앞뒤 `--warmup-frac`(0.1) 절단, `steady_wall = max(finished_at) − min(finished_at)` (`:376-413`) — 파생 창이지 벽시계 창이 아님 | 전 구간 시간 집계 | ❌ 다름 |
| TTFT | turn별 `ttft_s`는 기록하나 **summary 집계 없음** (`:275`) | mean TTFT 보고 | ❌ 없음 |

즉 문제는 **종료 조건 하나**다. run-to-completion이라 **최장 세션 E2E가 셀당 시간 하한**이 된다(2026-07-24 로그: 128k는 셀당 13.7 h → 서브샘플조차 329 h). 부수적으로, 끝물에 프로그램이 소진되며 실효 동시성이 C 아래로 내려가는 **드레인 구간 편향**이 생기는데, 순서 기준 트리밍은 이를 부분적으로만 걷어낸다(느린 heavy-tail 세션이 정의상 뒤쪽에 몰려 있어 뒤 10% 절단이 그 세션들을 통째로 버릴 수 있음).

⇒ 신규 드라이버 `scripts/mori_replay_driver_yunuikang.py`는 **재작성이 아니라 3가지 추가**다(원본 무수정, 복제 후 수정):

1. `--duration-s`(기본 1200) — `run_program` 루프 진입 시 deadline 체크, 초과 시 슬롯 종료. 코퍼스 소진 방지를 위해 `build_program_list`를 **무한 순환 제너레이터**로 교체(현재도 `run_idx` 접미사로 세션 재사용을 하므로 로직 그대로 확장).
2. **시간 기준 집계 창** — `--warmup-frac`(순서 기준) 대신 `[t0 + 0.2·D, t0 + D]` 벽시계 창 안에서 **완료된 턴 단위**로 집계(프로그램 완주 단위가 아니라). 이러면 창 끝에 걸친 미완 프로그램이 결과를 왜곡하지 않는다.
3. **TTFT 집계 추가**(mean/p50/p95) + `--stream` 강제 on.
- 보고 지표(논문 §6.2와 1:1):
  - `output_throughput_tok_s` = Σcompletion_tokens / steady_wall
  - `step_throughput_req_s` = Σcompleted turns / steady_wall
  - `ttft_mean_s`, `ttft_p95_s`
  - 부가(우리 트랙 계승): `prefix_cache_hit_rate`, `local_compute` 기반 참 recompute, GPU util 샘플(`sample_gpu_resident_yunuikang.py --gpus 1,2`), `/health` tier 카운트 타임시리즈

### D-2. 스윕 축과 셀 수

| 축 | 값 | 비고 |
|----|----|------|
| 시스템 | SMG / TA / TA+O / MORI | §A-3 |
| 동시성 C | 20 / 50 / 80 | 논문과 동일 |
| CPU:GPU 비 r | 1× / 2× | **오프로딩 있는 시스템(TA+O, MORI)에만 적용** |
| trace | `tracelab_mori_L128k` (주) / `ec128k` (대조) | 주 결과는 신규 가공본, ec128k는 "전이가 반쯤 파괴된 트레이스에서는 격차가 줄어든다"를 보이는 대조군 |
| Phase | 1(sim) / 2(real) | Phase 1은 TA vs MORI(sim)만 |

셀 수(Phase 2, 주 trace 기준): `3 C × (SMG 1 + TA 1 + TA+O 2 + MORI 2) = 3 × 6 = 18 셀`.

**엔진 재기동 최소화 순서**(재기동은 셀당 ~5분, 모델 로드+컴파일 포함):
```
for engine_cfg in [offload=OFF, offload=1×, offload=2×]:     # 3회 재기동
  for C in [20, 50, 80]:
    for system in engine_cfg에 해당하는 라우터 모드들:        # 프록시만 재시작(수초)
      run(duration_s)
```

### D-3. 선행 마이크로벤치 (Phase 1 비용 모델 보정)

Phase 1의 재로드 비용 `sleep(ctx × B_tok / BW_eff)`가 결론을 좌우하므로 `BW_eff`를 실측한다.
- `scripts/microbench_pcie_kv_yunuikang.py`(신규): pinned host memory ↔ GPU1/GPU2 H2D/D2H를 KV 블록 크기(vLLM block_size=16 기준 16×144 KiB=2.25 MiB)로 chunked 전송, 동시 전송 2스트림(TP2) 기준 유효 대역폭 측정.
- 기존 `microbench_recompute_yunuikang.py`(recompute 비용)와 짝을 이뤄 **"재로드 vs 재연산" 손익분기 컨텍스트 길이**를 산출 → 이 값이 MORI의 CPU tier가 이득인 구간을 예측한다. Phase 2 결과와 대조할 예측치가 된다.
- ⚠ Pro6000 Max-Q는 PCIe 5.0 x16(이론 63 GB/s)이지만 GPU1↔GPU2가 **cross-NUMA(SYS)**임이 기록되어 있음(메모리). 실측 필수.

### D-4. 예상 소요시간

`duration_s`별 (18셀 × repeat, 셀당 오버헤드 프록시 재시작 30 s + 엔진 재기동 3회×5 min 분할 ≈ 셀당 +1.5 min):

| duration | 1 repeat | 3 repeats | 판정 |
|----------|----------|-----------|------|
| 20 min | 6.5 h | **19.4 h** | ★ 권장 |
| 30 min | 9.5 h | 28.4 h | 여유 있으면 |
| 60 min(논문) | 18.5 h | 55.4 h | 과함(단일 GPU 노드 공유 환경) |

+ Phase 1(오프로딩 OFF 단일 엔진 config, TA vs MORI × 3 C × 2 r_sim = 12셀): 20 min × 3 repeats ≈ **13 h**
+ 마이크로벤치·스모크·trace 가공: **~6 h**
**총계: ≈ 38 h GPU-node-time** (3 repeats, 20 min 창 기준). 기존 트랙의 86~329 h 대비 현실적.

### D-5. 각 셀의 예상 방향성 (§예측 — 결과와 대조할 것)

| 조건 | 예측 | 근거 |
|------|------|------|
| C=20, 모든 시스템 | 오프로딩 4종 격차 ≤ 5%. SMG/TA는 이미 여기서 뒤처지기 시작 | 논문: C=20에서 MORI vs TA+O 2% (546 vs 534 tok/s). §A-4에서 C=20이 용량에 겨우 들어가게 사이징했으므로 재현되어야 함 |
| C=50 | MORI가 TA+O 대비 +10~25% | 논문 30B 30% 구간 |
| **C=80, r=1×** | **MORI ≥ TA+O +20%**, TTFT −20% | 논문 20~71% / 18~43% |
| **C=80, r=2×** | 격차가 1×보다 **더 벌어짐**. TA+O는 2×로 가도 거의 개선 없음 | 논문: B200 80프로그램에서 TA+O TTFT 56→58 s(무변), MORI 38→33 s. 이유는 TA+O가 CPU tier를 조율하지 않아 여분 용량을 못 씀 |
| TA+O의 C 스케일링 | **비단조**(C=50 > C=80) 가능 | 논문 B200 1×: 147→181→146 tok/s. eviction thrashing |
| MORI의 C 스케일링 | 단조 비감소 | 논문 136→191→189 |
| trace를 ec40k로 바꾸면 | MORI 이득이 **크게 축소** | 전이 1.3/세션 → sticky·ι 랭킹이 발동할 기회 자체가 없음. **이것이 §C-3 가공의 필요성을 증명하는 대조 실험** |
| trace를 swebench로 바꾸면 | MORI ≈ TA+O (차이 무의미) | ι mean 0.042 → idle 창 부재 |
| Phase 1 vs Phase 2 (MORI) | Phase 1이 Phase 2보다 낙관적 | 비용 모델이 전송/스케줄 오버헤드·대역 경합을 과소 반영 |

### D-6. 성공 판정 기준 / 통계

- **주 판정(P1)**: C=80, r=2×, 주 trace에서 `MORI output_throughput ≥ 1.15 × TA+O` **AND** `MORI ttft_mean ≤ 0.85 × TA+O`. (논문 하한 20%/18%보다 완화 — 우리는 DP=1·다른 HW·다른 trace)
- **보조(P2)**: MORI가 C에 대해 단조 비감소인 반면 TA+O는 그렇지 않음(비단조 재현).
- **위생(P3)**: C=20에서 MORI와 TA+O 차이가 ±5% 이내(과적합/버그 탐지용 음성 대조).
- **격리(P4)**: `--router tr` 결과가 `mori` 브랜치와 `yunuikang/thunderagent` 브랜치에서 통계적으로 동일(±3%) — 기존 베이스라인 무오염 증명.
- **통계**: repeat 3회. 셀당 `mean ± half-range` 보고. **승리 선언은 non-overlapping일 때만**(min(MORI 3회) > max(TA+O 3회)). 겹치면 "차이 미확정"으로 정직하게 기록(기존 트랙 톤 계승).
- **무효화 조건**: 어떤 셀에서든 (a) 요청 실패율 > 1%, (b) `_wait_for_resume` 타임아웃(1800 s) 발생, (c) `capacity timeout` 발생 시 그 셀은 무효 처리하고 원인 기록(기존 STEP5에서 tr이 3~10% timeout을 낸 전력 있음 — MORI는 tier가 하나 더 생겨 대기 경로가 길어지므로 **더 위험**).

---

## E. 오픈 퀘스천 · 마일스톤

### E-1. 내 요약과 실제 코드/논문이 어긋난 점 (§1 재게 + 잔여)

§1의 4개 정정(엔진=vLLM / GPU=Pro6000 96GB×2+Pro5000 / 전처리가 죽이는 건 tail보다 전이 / 항상-on 경로 필요)이 핵심. 그 외:
- 코드 매핑 5개 파일 지목은 **전부 정확**했다(§B-1~B-4의 검증 표). 다만 `_pause_until_safe`가 lock 밖에서 돈다는 점, `update_shared_tokens`가 dead code라는 점은 요약에 없었고 구현에 영향이 있다.
- 논문의 tick 기본 5 s가 우리 `scheduler_interval` 기본값과 **우연히 동일** → 하이퍼파라미터 정합 확인됨.
- 논문 구현 규모 "ThunderAgent 스케줄러에 ~3,300 L, SGLang cache에 500 L". 우리 Phase 1+2 추정 ~760 L + 엔진 패치 ~200 L. **논문보다 훨씬 작다** → 논문이 multi-replica·affinity·운영 코드를 포함하기 때문으로 보이나, 우리가 뭔가를 빠뜨렸을 가능성도 있음. Phase 1 완료 후 재점검.

### E-2. 결정이 필요한 선택지 (사용자 승인 필요)

| Q | 선택지 | 권고 |
|---|--------|------|
| **Q1. 엔진** | (a) vLLM 0.24 네이티브 오프로딩 유지 (b) SGLang 0.5.10+HiCache 신규 설치로 논문과 동일 환경 | **(a) 권고.** (b)는 Blackwell sm_120 빌드 리스크 + 하네스(metrics client는 있으나 스크립트·측정 프로토콜 전부 vLLM 기준) 전면 재작성 비용. 단 (a)는 "논문과 다른 엔진"이라는 한계를 §한계에 명기 |
| **Q2. 모델** | (a) Qwen3-8B (b) Qwen3-32B | **(a) 권고.** early-cutoff 트랙의 C_total·디코드 속도·기동 절차가 이미 실측되어 있어 STEP 1을 건너뛸 수 있음. 32B는 M5에서 "모델 크기 축" 추가 시 |
| **Q3. duration** | 20 min / 30 min / 60 min | **20 min × 3 repeats** (§D-4) |
| **Q4. Phase 2 엔진 패치 방식** | (a) `_CACHE_POLICIES`에 monkey-patch로 `"mori"` 등록 (b) vLLM fork | **(a) 권고** — `scripts/mori_vllm_patch_yunuikang.py`를 `VLLM_PLUGINS` 또는 서버 기동 전 import로 주입. 단 `OffloadKey`에 program_id가 없으므로(§A-2) **program→block 스탬프 경로를 먼저 조사**해야 함. 조사 결과 불가하면 Phase 2는 "CPU 용량만 제어, typed eviction 없음"으로 축소하고 그 사실을 명기 |
| **Q5. 서브에이전트/human-wait** | 원본 gz 조사 후 결정 | 조사(반나절)를 M1에 포함. 없으면 §한계 기록 |
| **Q6. 컨텍스트 예산 L** | 40,960(native) / 131,072(YaRN) | **131,072 권고**(전이 보존). YaRN 품질·속도 영향은 스모크로 확인 |

### E-3. 5090/Blackwell·SGLang 호환성 위험

| 위험 | 영향 | 완화 |
|------|------|------|
| vLLM `OffloadingConnector`가 Blackwell sm_120 + TP2에서 미검증 | Phase 2 전체 블록 | **M2 게이트에서 최소 스모크 먼저**(작은 `--kv-offloading-size 8`, C=4, 10분). 실패 시 Phase 1 결과만으로 논문 대비 부분 재현 보고 |
| `swap_blocks_triton.py` 커널이 sm_120에서 컴파일 실패 가능 | 동일 | 위와 동일. `VLLM_ATTENTION_BACKEND=FLASH_ATTN` 고정 유지 |
| `--kv-offloading-size`가 TP 전 랭크 **합산** 총량이라는 규약 오해 | CPU tier 용량이 2배/절반으로 잘못 설정 → 조용한 성능 오염 | 불변식 I6 assert + 기동 로그에서 실제 CPU 블록 수 확인 |
| GPU1↔GPU2 NVLink 없음 + cross-NUMA(SYS) | TP all-reduce 느림(기록됨) + PCIe 오프로딩 대역이 NUMA에 따라 비대칭 | `numactl` 바인딩 실험을 마이크로벤치에 포함 |
| 체크포인트 shard 누락 gotcha 재발 | 기동 실패를 "느림"으로 오진 | `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` 고정(기록된 해법) |
| vLLM `serve` 종료 시 EngineCore/Worker orphan이 GPU 점유 | 다음 셀 OOM | 스윕 러너에 pid 직접 kill + `nvidia-smi` 확인 루틴(기록된 해법) |
| GPU0(Pro5000)는 타 사용자 | — | `CUDA_VISIBLE_DEVICES=1,2` 고정, 매 셀 전 `nvidia-smi`로 유휴 확인 |

### E-4. 마일스톤 · 검증 게이트

| M | 내용 | GPU | 산출물 | ★게이트(통과 조건) |
|---|------|-----|--------|-------------------|
| **M0** | git `mori` 브랜치 생성, baseline 커밋 | ✕ | 브랜치 | `git diff` 기준선 확보 |
| **M1** | trace 가공: `char_mori_trace_yunuikang.py` + `prep_tracelab_mori_yunuikang.py`, 원본 gz 서브에이전트/human-wait 조사 | ✕ | `tracelab_mori_L128k_yunuikang.jsonl` + meta | **G1**: §C-3 검증표 8항목 전원 합격(특히 전이 median ≥ 4, 동시점 ι IQR ≥ 0.35) |
| **M2** | 엔진 스모크: `--kv-offloading-size 8`로 TP2 기동, C=4 10분 | ○ | 기동 로그, CPU 블록 수 | **G2**: 정상 응답 + `/metrics`에 오프로딩 카운터 증가. **실패 시 Phase 2 범위 축소 결정** |
| **M3** | **Phase 1 구현**: `mori_idleness/mori_tier/mori_router` + 단위테스트 + I1~I5 assert | ✕ | 코드, 테스트 | **G3**: `--router tr` 회귀 없음(P4), `git diff`로 router.py/backend/state.py 0줄 |
| **M4** | 마이크로벤치(PCIe BW) + **Phase 1 스윕** (TA vs MORI-sim, 12셀×3) | ○ | `logs/2026-08-XX_MORI_PHASE1_RESULTS` | **G4**: MORI-sim이 C=80에서 TA 대비 유의미 개선. 없으면 ι 지표/정책 재검토(설계 결함 조기 발견) |
| **M5** | **Phase 2 구현**: 엔진 오프로딩 연동 + typed eviction(가능 시) + I6 | ○ | 코드, 패치 스크립트 | **G5**: 스케줄러 tier 장부와 엔진 실제 CPU 점유가 ±10% 내 일치 |
| **M6** | **Phase 2 본 스윕** 18셀 × 3 repeats + ec40k/swebench 대조 | ○ | `logs/..._MORI_PHASE2_RESULTS` | **G6**: §D-6 P1~P4 판정 |
| **M7**(선택) | 확장 축: 32B 모델 / DP=3 multi-replica(affinity·churn) / k 민감도 ablation | ○ | — | — |

의존: M0 → M1 →(G1)→ M3 →(G3)→ M4 →(G4)→ M5. M2는 M1과 병렬(GPU 유휴 시). M2 실패해도 M3/M4는 진행 가능(Phase 1은 엔진 무수정).

---

## 5. 정직 기록 (§한계)

1. **엔진이 논문과 다르다**(vLLM 0.24 native offloading vs SGLang 0.5.10 HiCache). 절대 수치는 논문과 비교 불가, **시스템 간 상대 비교만** 유효.
2. **DP=1**이므로 논문 §6.2.2(multi-replica affinity·churn, 54~79% 이득)는 재현 범위 밖.
3. **HBM이 논문 대비 과잉**이라 `--kv-cache-memory-bytes`로 인위 축소한다. 논문도 같은 에뮬레이션을 하지만(H200→H100급), 우리는 축소폭이 더 크다.
4. **trace가 논문과 다르다**(TraceLab/SyFI vs 자체 수집 Claude Code + SWE-bench Pro). §C-1 대조표대로 TraceLab이 더 idle-heavy → **MORI에 유리한 방향의 편향**임을 명시해야 한다.
5. **human-in-the-loop idle이 전처리 단계에서 이미 제거**되어 있다(§C-2.4). 논문 idle 3대 원인 중 하나 부재.
6. **Phase 1의 재로드 비용은 모델**이지 실측이 아니다. Phase 2 결과와 반드시 대조하고, 어긋나면 Phase 1 결론을 철회한다.
7. **참 recompute 측정 오염**: 라우터 pause 후에도 엔진 prefix cache가 블록을 들고 있으면 Waiting tier의 재연산 비용이 과소 측정된다(`VLLM_PROFILING §1-2` 기록). `local_compute` 카운터로 교차 검증하고, 불가하면 한계로 기록.
8. `shared_tokens` dead code(§1-1) 때문에 모든 시스템의 용량 회계가 prefix 공유를 무시한다. 4종 전부 동일 규약이라 비교는 공정하나, **절대 용량은 보수적으로 과대 계상**되어 있다.

---

## 6. 신규 파일 목록 (예정 — 본 턴에서는 생성하지 않음)

```
ThunderAgent/scheduler/mori_idleness.py        신규 ~120 L
ThunderAgent/scheduler/mori_tier.py            신규 ~200 L
ThunderAgent/scheduler/mori_router.py          신규 ~400 L
ThunderAgent/scheduler/mori_config.py          신규  ~40 L
tests/test_mori_idleness_yunuikang.py          신규  ~80 L
tests/test_mori_invariants_yunuikang.py        신규 ~120 L
scripts/char_mori_trace_yunuikang.py           신규 (trace 특성 + 동시점 ι IQR 시뮬레이터)
scripts/prep_tracelab_mori_yunuikang.py        신규 (turn-window slicing)
scripts/mori_replay_driver_yunuikang.py        신규 (고정 시간창 closed-loop + TTFT 집계)
scripts/run_mori_eval_yunuikang.sh             신규 (4종 시스템 셀렉터 + 스윕)
scripts/_serve_vllm_8b_tp2_mori_yunuikang.sh   신규 (KVOFF/KVBYTES env 추가한 격리 복제)
scripts/microbench_pcie_kv_yunuikang.py        신규 (재로드 비용 모델 보정)
scripts/mori_vllm_patch_yunuikang.py           신규 (Phase 2, _CACHE_POLICIES["mori"] 주입)

기존 수정(순수 추가, 총 +34 L):
ThunderAgent/config.py  +6 / __main__.py +14 / app.py +8 / program/state.py +6
```

---

## 7. 다음 액션 (승인 후)

1. `git add logs/2026-07-24_*.md && git commit` → `git checkout -b mori` (M0)
2. `syfi_coding_trace.jsonl.gz` 원본 필드 조사 (Q5) + `char_mori_trace_yunuikang.py` 작성 (M1)
3. **게이트 G1 보고 후 정지** — trace 검증표 8항목을 채워 사용자 확인 받고 M3 착수.

> 본 계획서는 GPU를 한 번도 점유하지 않고(읽기 전용 탐색만) 작성되었으며, 코드·trace·스크립트를 일절 수정하지 않았다.
