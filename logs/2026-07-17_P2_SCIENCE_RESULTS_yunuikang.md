# P2 — ScienceAgentBench serving-eval (2026-07-17)

> 작성: 강윤의 · 브랜치 `yunuikang/thunderagent` · 서버 nutella1 · **P1과 독립 로그**
> 전제 문서: 계획서 `plans/2026-07-15_PLAN_pro6000-tp-rescale_yunuikang.md` **§4-3**(ScienceAgentBench) · **§4-4-3**(P2 미해결 리스크) · P1 결과 `logs/2026-07-16_TP2_RESULTS_yunuikang.md` · 메커니즘 `logs/2026-07-06_MECHANISM_REFERENCE_yunuikang.md`
> **P1에서 이어짐(3줄)**: (1) Deployment A(TP2 Qwen3-32B, GPU1+2, KV 456,944 tok)로 TraceLab·SWE serving-eval 완료 — k_fit-flip 입증(4090 R<1 패 → Pro6000 R≥1 승), R모델 교차입증(fit=KV풀/입력크기: TraceLab fit~25→C=32 붕괴, SWE fit~58→C=64 붕괴). (2) P2 ScienceAgentBench는 **R모델의 "중간" 점**(tool 가변성: TraceLab 저듀티 — Science 중간 — SWE decode-heavy 사이)을 채운다. (3) 가드레일 P1과 동일(router.py 미수정, GPU1+2 전용·GPU0 미접촉, 격리 복사본).
> 형식: 질문 → 증거(수치·파일:라인) → 결론 → [추정]/한계.

---

## Phase A — 스코핑 (조사만, 코드 실행 없음) — 정지·보고 지점

### A-1. 하네스 이식 (최대 리스크) — 판정: **upstream 존재, 이 repo 미벤더링 → 이식 필요(중간~높은 작업량)**
- **증거**:
  - 이 repo `examples/inference/OpenHands/evaluation/benchmarks/`에 **`swe_bench`만 존재**(ScienceAgentBench 없음).
  - 단 `examples/inference/OpenHands/evaluation/README.md:132`에 **`ScienceAgentBench: evaluation/benchmarks/scienceagentbench`** 참조 → **upstream OpenHands엔 하네스 존재**(이 repo가 swe_bench만 벤더링).
  - OpenHands 버전 = **1.2.1** (`pyproject.toml:20`). 이식 시 upstream을 이 버전에 정합시켜야 함.
- **재사용 가능(변경 없음)**:
  - `evaluation/utils/shared.py`(808줄): `EvalMetadata`·`make_metadata`·`prepare_dataset`·`run_evaluation`·`process_instance_wrapper`·`get_default_sandbox_config_for_eval`·`get_openhands_config_for_eval` — 벤치 공통 인프라. SAB 하네스가 그대로 import.
  - **ThunderAgent 글루가 이미 swe_bench에 구현됨**: `benchmarks/swe_bench/run_infer.py:612-758` — `_make_thunderagent_program_id`, `OPENHANDS_PROGRAM_ID` env 주입, `_release_thunderagent_program`(POST /programs/release). → SAB run_infer.py에 이 패턴을 **그대로 이식**하면 program_id 주입/release 확보.
- **순수 신규 개발(포팅)**: SAB `run_infer.py`(upstream)의 SAB 고유 부분 — 데이터셋 로딩, instruction 구성, 샌드박스 initialize_runtime(SAB 데이터 배치), complete_runtime(SAB 출력 수집). swe_bench run_infer.py(1040줄)와 구조 유사하나 SAB 태스크 특성(입력 데이터셋 마운트, 출력 파일 규약)이 다름.
- **⚠️ upstream 정합 리스크(명시)**: upstream github의 `evaluation/benchmarks/scienceagentbench` 경로가 현재 main에서 WebFetch 404(구조 이동/브랜치 상이). OpenHands 1.2.1 태그의 정확한 하네스를 확보해야 하며, 그 하네스의 shared.py/State/runtime API가 이 repo의 벤더링본과 **버전 불일치 시 소폭 수정 필요**. 이식 충실도(upstream과 동작 동일성) 검증 필요 — **[확인 필요]**.

### A-2. ★ 데이터 blocker (Phase A 최대 발견) — **SAB 태스크 입력 데이터가 password-protected**
- **증거**:
  - SAB 공식 README(OSU-NLP-Group/ScienceAgentBench): **102 태스크**, 각 태스크 = 입력 데이터셋 + gold program + eval 아티팩트. **전체 benchmark 데이터(`datasets/`·`gold_programs/`·`eval_programs/`·`scoring_rubrics/`)는 password-protected SharePoint에서 다운로드**.
  - HF `osunlp/ScienceAgentBench`(ungated) parquet(102행) 실측 컬럼: `instance_id, domain, task_inst, domain_knowledge, dataset_folder_tree, dataset_preview, src_file_or_path, gold_program_name, output_fname, eval_script_name`. → **태스크 설명·데이터 미리보기(preview)만 있고 실제 데이터셋 파일은 없음**(dataset_preview는 CSV 앞 몇 줄 뿐).
- **함의**: 에이전트가 SAB 태스크를 실제 실행(코드 작성→샌드박스 실행→데이터 로드)하려면 **실제 입력 데이터셋 파일**이 필요. HF preview만으론 코드가 파일을 못 찾아 flail → **trace가 비대표적**(SWE 녹화가 실제 repo 컨테이너에서 돈 것과 대비). → **faithful 녹화엔 SharePoint 데이터 접근이 필수 = 사용자 결정/제공 항목.**
- **참고(무관 blocker)**: SAB 평가는 GPT-4o로 시각화 채점(유료). **우리는 correctness 평가 불필요(서빙 trace만) → GPT-4o 무관**(SWE에서 pass 평가 스킵한 것과 동일). conda 환경(sci-agent/sci-agent-eval)은 SAB 직접 실행용이나 OpenHands 하네스는 자체 runtime으로 래핑 → 우리 경로에선 OpenHands 샌드박스만.

### A-3. docker / 모델 정합 — 판정: **OK (blocker 아님)**
- docker `docker info` OK, `/home` 여유 **318GB**(P1 SWE 이미지 일부 잔존하나 SAB는 per-instance 이미지 아님 — OpenHands runtime 이미지 + 태스크 데이터 마운트라 디스크 부담 SWE보다 작음).
- Deployment A(TP2 Qwen3-32B, GPU1+2) 그대로 사용 — 서빙 대상 불변. SAB 녹화도 P1 SWE와 동일하게 프록시(:9000 default --profile) 경유.
- **[확인 필요]**: OpenHands SAB runtime 이미지(python 샌드박스) pull/build 가능성은 하네스 확보 후 실측.

### A-4. P1 교란변수 caveat (참고, 로그 상수) — 기록 완료
- Deployment A는 device mem≥70GiB라 vLLM 기본값이 **`max_num_batched_tokens=8192`**(4090의 2048 아님; startup 로그 실측)로, `max_num_seqs=1024`[추정, vLLM 기본]로 자동 설정됨. **SWE·TraceLab·Science 모두 동일 Deployment A → 워크로드 간 상수** → 정책 상대비교(default vs tr) 결론에 무해. caveat로만 기록.

---

### ★ Phase A 산출 — 사용자 결정/제공 필요 항목
1. **[결정 필요·최우선] SAB 태스크 입력 데이터 접근**: password-protected SharePoint. → (a) 접근 권한 확보(SAB 저자에 요청) 후 데이터 제공, (b) 대체 데이터 경로 확인, (c) preview-only 축소(충실도 저하 감수), (d) P2 보류 중 택일.
2. **[판단 필요] 하네스 이식 진행 승인**: upstream SAB run_infer.py를 OpenHands 1.2.1에 정합 이식 + ThunderAgent 글루 이식(중간~높은 작업량, 버전 정합 리스크). 진행 승인?

### Phase B 예상 소요 (데이터·하네스 확보 가정)
- 하네스 이식·검증: 손대는 시간 ~0.5–1일(버전 정합 따라 변동). 데이터 셋업: SharePoint 다운로드+배치(크기 미상).
- 녹화(102 태스크 또는 축소 서브셋, 32B, docker): P1 SWE(64@~95분) 기준 → ~2.5–4h[추정]. 스윕(default+tr, C=16·32·64, per-C NPROG, REPEAT=3 = 18런): SWE와 유사 ~5–8h(스래싱 C 포함).
- **총 Phase B ~1–1.5일**(데이터/하네스 확보 후).

**→ Phase A 정지. A-2(데이터)·A-1(이식 승인) 결정 대기.**

---

**→ SAB 실제 데이터가 password-protected라 사용자 신청 대기로 보류. P3(HLE)를 선행함** (2026-07-18)

---
---

# B. P2 재개 — Phase A 재확인 (2026-07-20)

## B-0. ★ 정정 기록 — 이전 Phase A의 데이터 판정 오류

**정정**: 2026-07-17 Phase A는 SAB 입력 데이터를 **"password-protected SharePoint → 접근 불가(blocker ①)"**로 판정했으나, 이는 **오판정**이었다.

- **오판 경위**: HF `osunlp/ScienceAgentBench` 데이터셋 **preview(메타데이터 parquet)만** 확인하고, 실제 데이터 폴더(`benchmark/datasets/`)는 별도 배포임을 확인하는 단계에서 SharePoint 링크의 비밀번호 요구를 "접근 권한 없음"으로 결론지었다.
- **실제**: 해당 zip은 **공개 비밀번호(`scienceagentbench`)**로 누구나 해제 가능한 배포물이었다(SAB README에 명시되는 관행적 보호 — 크롤러/LLM 학습오염 방지 목적이지 접근 제한이 아님).
- **교훈**: "비밀번호 요구 = 접근 불가"로 단정하지 말 것. 배포 문서(README/논문 부록)에서 공개 비번 여부를 먼저 확인해야 했다. **blocker ①은 실재하지 않았고, 이로 인해 P2가 3일간 불필요하게 보류**되었다.
- **현 상태**: 사용자가 데이터 확보·배치 완료 → `distserving/scratch/sab/benchmark/` → **blocker ① 해소**.

## B-1. 데이터 무결성 검증 — **판정: PASS**

| 항목 | 실측 | 판정 |
|---|---|---|
| `benchmark/datasets/` | 414 files, **3.8GB**, 최상위 76 entries | ✅ 실데이터 존재 |
| `benchmark/gold_programs/` | **102** `.py` | ✅ |
| `benchmark/eval_programs/` | 224 files, 36MB | ✅ |
| `benchmark/scoring_rubrics/` | **102** `.json` | ✅ |
| 태스크 메타(HF parquet, 캐시됨) | **102 rows × 12 cols** (`verified-00000-of-00001.parquet`) | ✅ 논문 102 태스크 일치 |

**메타 ↔ 로컬 파일 교차검증 (전수)**
- `gold_program_name` → `gold_programs/` 존재: **누락 0/102**
- `eval_script_name` → `eval_programs/` 존재: **누락 0/102**
- `dataset_folder_tree` 루트 → `datasets/<root>/` 존재: **누락 0/71**(고유 데이터폴더 71개, 태스크가 폴더를 공유)
- ※ `src_file_or_path`는 **원본 GitHub 저장소 경로**(로컬 경로 아님) — 15건 NaN. 하네스가 쓰지 않음(upstream `format_task_dict` 미참조 확인). 무해.

**도메인 분포**: Psychology/CogSci 28, GIS 27, Bioinformatics 27, Comp.Chemistry 20 (계 102).

**입력 크기(레짐 지도용 사전 재료, chars)**
| 필드 | median | p95 | max |
|---|---|---|---|
| `task_inst` | 304 | 575 | 1,075 |
| `domain_knowledge` | 534 | 1,124 | 1,753 |
| `dataset_folder_tree` | 74 | 1,165 | 2,597 |
| `dataset_preview` | 849 | 4,407 | 24,995 |
| **합산 instruction** | **1,952** | **5,415** | 25,969 |

→ instruction 토큰 ≈ **median 558 / p95 1,547**[추정, chars/3.5]. **단 fit 계산의 `program_input_tokens`는 instruction이 아니라 에이전트 궤적 누적 컨텍스트**이므로 이 값이 아님 — 녹화 실측으로 확정한다(P1 SWE: median 7,897).

## B-2. GPU 배치 — **판정: GPU1 단일-GPU 폴백 확정**

- 실측(2026-07-20): GPU0 유휴 / **GPU1 유휴(2MiB)** / **GPU2 = suuinmoon 점유**(PID 1788560 `generate_kernels_and_eval.py`, K-Search stage16, 1,044MiB, 진행중).
- 사용자 지정 규칙("GPU2 suuinmoon 아직 점유면 불가 시 GPU1 단일-GPU 32B 폴백")에 따라 **Deployment A′ = GPU1 단일-GPU Qwen3-32B**로 확정. **GPU0·GPU2 미접촉**(goguma STEP5 / K-Search 무간섭).
- **KV 축소 예상**: TP2는 KV 총 ~120GB → `C_total = 456,944 tok`. 단일 96GB는 weights ~65GB(BF16) 차감 후 KV ≈ 23GB → **C_total ≈ 85–95k tok**[추정, 기동 로그 `cache_config_info`로 확정 예정].
- **★ 실험적으로는 유리**: fit = C_total/program_input이 **TP2 대비 ~1/5**로 작아져, 낮은 C에서도 붕괴 레짐(C>fit)에 진입 가능 → **fit×d 레짐 지도에서 저-fit 구간 점 확보**(4090 앵커와 Pro6000 사이를 메움). C 범위는 기동 후 실측 fit에 맞춰 확정.
- **caveat(로그 상수)**: Deployment A′는 TP2가 아니므로 **P1(SWE·TraceLab) 절대값과 직접 비교 불가**. P2 결론은 **동일 배치 내 default vs tr 상대비교** + **fit×d 축 위치**로만 주장한다.

## B-3. 하네스 이식 스코핑 — **판정: 저위험·소규모 (진행 가능)**

- **upstream 확보 완료**: `OpenHands/OpenHands` @ tag **`1.2.1`** (repo가 `All-Hands-AI/OpenHands` → `OpenHands/OpenHands`로 이름 변경, `main`에는 `evaluation/benchmarks/` 없음 → **태그 `1.2.1` 고정 필수**). 참조본 → `scratch/sab/_upstream_ref/`(저장소 밖).
  - `run_infer.py` 9,486B / **280줄**, `Dockerfile.evaluator`, `post_proc.py`, `README.md`, `scripts/run_infer.sh`. (`Dockerfile`은 404 — 샌드박스는 배포 이미지 사용이라 불필요.)
- **버전 정합 리스크: 낮음.** upstream SAB가 import하는 `evaluation.utils.shared` 심볼 **12개 전수 존재 확인**(로컬 OpenHands 1.2.1과 동일 버전): `EvalMetadata, EvalOutput, codeact_user_response, compatibility_for_eval_history_pairs, get_default_sandbox_config_for_eval, get_metrics, get_openhands_config_for_eval, make_metadata, prepare_dataset, reset_logger_for_multiprocessing, run_evaluation, update_llm_config_for_completions_logging` → **API 시그니처 수정 불필요**.
- **재사용(수정 없음)**: `evaluation/utils/shared.py`.
- **이식(신규, ~35줄 이식)**: `swe_bench/run_infer.py:618-655,754-758`의 ThunderAgent 글루 = `_make_thunderagent_program_id`(sha1(instance_id:pid)) + `_release_thunderagent_program`(POST `/programs/release`) + `OPENHANDS_PROGRAM_ID` env 설정/복원 + `finally` 해제. **program_id prefix만 `swe-` → `sab-`로 변경.**
- **신규(SAB 고유부, upstream 그대로)**: `format_task_dict`(데이터 경로/instruction 조립), `initialize_runtime`(workspace 생성 + 데이터셋 `copy_to`), `complete_runtime`(pred program 회수), instruction 템플릿.
- **로컬 수정 필요 2건**: ① `LOCAL_DATASET_PATH`를 `scratch/sab/benchmark`로 지정, ② `load_dataset('osunlp/ScienceAgentBench', split='validation')` — 로컬 캐시 parquet은 split명 **`verified`** → 오프라인 로드 경로로 고정.
- **작업량 판정**: **~0.5일**(upstream 280줄 + 글루 35줄, API 정합 확인 완료). 이전 Phase A의 "중간~높은 작업량·버전 정합 리스크" 평가는 **하향 정정**.
- **파일명(격리)**: `evaluation/benchmarks/scienceagentbench_yunuikang/run_infer_yunuikang.py`. `scheduler/router.py` 및 기존 `swe_bench/` **무수정**.

## B-4. docker 재확인 — **판정: PASS**
- `docker 29.1.3`, `docker ps` OK, docker 그룹 소속 ✅.
- 샌드박스 이미지 `docker.io/xingyaoww/openhands-eval-scienceagentbench` **manifest 조회 성공**(11 layers, 압축 ≈**2.14GB**) → pull 가능.
- 디스크: `/` 799GB free, `/home` 223GB free ✅ (P1 SWE 이미지 2개 3.93GB씩 잔존, 무해).
- 외부망 정상(GitHub API/raw 접근 확인).

## ★ B-5. Phase A 재확인 결론 — **blocker 없음**
| Phase A 항목 | 판정 |
|---|---|
| ① 데이터 | ✅ **해소**(B-0 정정, B-1 전수 검증 PASS) |
| ② GPU 배치 | ✅ **확정**(GPU1 단일-GPU 폴백, 사전 지정 규칙 적용 — 사용자 결정 불요) |
| ③ 하네스 이식 | ✅ **저위험·~0.5일**(API 12/12 정합) |
| ④ docker | ✅ PASS |

**사용자 결정/제공 필요 항목: 없음.**
**→ Phase A 정지. 이식 착수 승인 대기.**

---

# C. Phase B 실행 (2026-07-20)

## C-1. ★ Deployment A′ 기동 — C_total 확정·고정

`scripts/_serve_vllm_gpu1_yunuikang.sh` (신규 격리본; TP2 스크립트 무수정). GPU1 단일, `CUDA_DEVICE_ORDER=PCI_BUS_ID` 명시 고정(디바이스 "1" = 96GB 카드 확정), `MML=32768 GMU=0.92`, Qwen3-32B.

| 항목 | 실측(기동 로그) |
|---|---|
| Available KV cache memory | **24.55 GiB** |
| **★ C_total (고정)** | **100,544 tokens** (`kv_cache_utils.py:2146`) |
| Max concurrency @32,768 tok/req | 3.07× |
| GPU1 점유 | 91,524 MiB / 97,887 |
| 기동 | CUDA graph capture 완료, `/health` OK, `/v1/models` = Qwen/Qwen3-32B |

- **추정 대비**: B-2의 [추정] 85–95k → **실측 100,544** (추정이 ~6% 과소). 이하 모든 fit은 **100,544**로 계산한다.
- **TP2 대비**: 456,944 → 100,544 = **×0.220**. 예상대로 fit이 ~1/4.5로 축소 → 저-fit 레짐 점 확보에 유리.

## C-2. 하네스 이식 — 완료

- 신규: `evaluation/benchmarks/scienceagentbench_yunuikang/run_infer_yunuikang.py` (+ `__init__.py`). 기존 `swe_bench/`·`scheduler/router.py` **무수정**.
- upstream(tag `1.2.1`) 대비 변경 3점: ① `LOCAL_DATASET_PATH` → `scratch/sab/benchmark`(env `SAB_BENCHMARK_PATH` 오버라이드 가능), ② `load_sab_dataset()` — 캐시 parquet 직접 로드(split명 `verified`, 오프라인·재현성), ③ ThunderAgent 글루 이식(`sab-` prefix, `finally` 해제).

## C-3. ★ 예상 못한 이슈 — OpenHands 의존성 미설치 (해결)

- **발견**: P1의 SWE 녹화는 **mini-swe-agent**(`mini-extra swebench`)로 수행되어 **OpenHands 런타임이 이 서버에서 한 번도 구동된 적 없음**. 메인 venv에 `openhands` 미설치(`ModuleNotFoundError`), `termcolor`조차 없음. → B-3의 "저위험" 판정은 **API 시그니처 정합만 근거**였고 **런타임 구동 가능성은 미검증**이었다(판정 근거의 한계를 정직히 기록).
- **의존성 규모**: pyproject `dependencies` **~85개** — `playwright`, `browsergym-core`, `poetry`, `pythonnet`, `google-cloud-aiplatform`, `kubernetes`, **`openai==2.8` 핀** 등. 메인 venv(vllm 0.24.0 / torch 2.11.0+cu130)에 설치하면 **openai 핀 충돌로 서빙 스택 파손 위험**.
- **조치**: **별도 venv 완전 격리** → `/home/yunuikang/yunuikang_work/.venv_oh_yunuikang` (Python 3.12.3)에 `pip install -e .`. 메인 venv **무변경** → vLLM 서버(:8000)와 프록시는 기존 venv 그대로 사용. 두 venv는 HTTP로만 통신하므로 결합 없음.

## C-4. 스모크 시도 — **현재 실패(미통과). 게이트 정지·보고**

이식 자체는 검증되었으나 **OpenHands 런타임 이미지 빌드**에서 막혔다. 발견 순서대로 정직히 기록한다.

### 통과한 것
| 검증 | 결과 |
|---|---|
| 격리 venv에 OpenHands 설치 | ✅ `openhands` 임포트 OK |
| 하네스 심볼 12/12 임포트 | ✅ |
| 이식 하네스 임포트·데이터 로드 | ✅ **102 태스크**, `format_task_dict` 정상(`dataset_path=/benchmark/datasets/clintox/`, `pred_program_name=pred_clintox_nn.py`) |
| SAB 샌드박스 이미지 pull | ✅ 7.29GB(압축 2.14GB) |
| 프록시 :9000 default + `--profile` | ✅ `router_mode=default` |
| Deployment A′ 백엔드 | ✅ `:8000` health, C_total 100,544 |

### 막힌 것 — 3연속 이슈 (2개 해결, 1개 미해결)

**이슈 ① upstream 하네스가 `--config-file`을 무시** → 해결
`get_llm_config_arg(args.llm_config)`가 `toml_file` 기본값 `'config.toml'`을 써서 내 격리 config를 못 찾고 `None` 반환 → `AttributeError: 'NoneType' has no attribute 'modify_params'`. **upstream 버그**(swe_bench는 `run_infer.py:849`에서 `args.config_file`을 넘김). 이식본에 동일 수정 적용(변경 ④).

**이슈 ② `docker buildx` 미설치** → 해결
`check_buildx()`가 False → OpenHands가 "컨테이너 내부라 docker 바이너리 없음"으로 **오판**하고 **호스트에서** `apt-get update`를 실행 → 비root라 exit 100. 원인은 호스트에 buildx 플러그인 부재(`docker-trust`만 존재). **root 없이 사용자 로컬 플러그인**으로 해결: `~/.docker/cli-plugins/docker-buildx` v0.35.0 설치(BuildKit v0.26.2 인식). 시스템·타 사용자 무영향.

**이슈 ③ [미해결] 런타임 이미지 빌드 실패 — poetry/uv 불일치**
`Dockerfile:182` exit **127**. 실제 실패 지점을 빌드 로그로 특정:
```
#18 1.168 Using virtualenv: /openhands/poetry/openhands-ai-5O4_aCHf-py3.12   ← poetry 정상 동작
#18 1.304 bash: line 1: poetry: command not found                            ← 여기서 죽음
```
- 앞 3개 poetry 호출(`config set`, `poetry config`, `poetry env use`)은 **모두 성공** → poetry는 micromamba env에 정상 설치됨(conda-forge `poetry-2.4.1` 확인).
- 죽는 곳은 `micromamba run -n openhands bash -lc 'test -f poetry.lock || poetry lock ...'` — **`bash -lc`(로그인 셸)이 `/etc/profile`로 PATH를 리셋**해 env의 poetry를 잃는다.
- 이 분기를 타는 이유는 **`poetry.lock` 부재**. 근본 원인: **OpenHands 1.2.1은 `uv.lock`으로 이전했는데 런타임 Dockerfile은 아직 `poetry.lock`을 전제**(repo 루트에 `uv.lock` 1.1MB 있음, `poetry.lock` 없음) → upstream 자체 불일치. `test -f poetry.lock ||` 폴백이 있으나 그 폴백이 PATH 버그로 깨져 있음.
- 우회 실현성 확인: 베이스 이미지에서 `poetry lock` 직접 시도 → **실패**(`python 3.11.10 is not supported by the project (^3.12,<3.14)`). 베이스 python이 3.11이라 컨테이너 밖 생성은 불가; python3.12+poetry 환경에서 별도 생성해야 함.

### 판단
이식 코드는 정상이고 남은 것은 **upstream 빌드 체인의 버전 불일치 1건**이다. 다만 이미 이슈 3건 연속이라, 진행 방식을 사용자와 정하는 편이 낫다고 판단 → 게이트 정지.

---

# D. 옵션 B — mini-swe-agent 스캐폴드로 전환 (2026-07-20)

## D-0. ★ 방법론 명시 (정직 기록 — 결론 해석에 필수)

**Science 점은 논문의 OpenHands CodeAct 스캐폴드가 아니라 `mini-swe-agent` 스캐폴드로 측정한다.**

- **전환 사유**: OpenHands 런타임 이미지 빌드가 upstream **poetry/uv 불일치**로 막힘(C-4 이슈 ③). 이슈 3연속(①`--config-file` 무시 ②buildx 부재 ③poetry.lock)이라 rabbit hole로 판단, 사용자 승인 하에 폐기.
- **프레이밍(이 로그·그래프·결론 전반에 적용)**:
  > **"스캐폴드를 P1 SWE와 통일해 *워크로드 효과만* 분리한다. 논문 OpenHands-on-Science의 충실 재현은 아니다."**
- **이 프레이밍이 갖는 이점**: fit×d 레짐 지도에서 SWE 점과 Science 점이 **동일 스캐폴드·동일 모델·동일 배치**를 공유하므로, 두 점의 차이는 **워크로드(버그수정 vs from-scratch 프로그램 작성)** 에서만 온다 → 스캐폴드가 교란변수가 아니다.
- **이 프레이밍이 갖는 한계**: 논문 Fig 4·5의 Science 절대값과 직접 대조 불가. Science의 d·fit은 **mini-swe 스캐폴드 조건에서의 값**으로만 해석해야 한다.

## D-1. 배선

- 신규(격리, mini-swe 패키지 **무수정**):
  - `scripts/run_sab_minisweagent_yunuikang.py` — SAB 배치 러너(`run/extra/swebench.py` 패턴 이식).
  - `scripts/sab_qwen32b_config_yunuikang.yaml` — **P1 SWE config와 system/format/observation 템플릿 동일**, instance_template만 SAB용(from-scratch 작성 워크플로)으로 교체. `step_limit=40`, `timeout=300`(과학 프로그램은 학습·플로팅으로 SWE보다 느림), `MPLBACKEND=Agg`.
  - `scripts/run_sab_record_mini_yunuikang.sh` — 프록시(:9000 default `--profile`) + 러너.
- **ThunderAgent 연동은 mini-swe에 이미 내장**되어 있었다: `models/vllm_model.py:131`이 `job_id`→`extra_body.program_id`로 보내고, `run/extra/swebench.py:231`에 `release_router_program()`이 있음. 러너에서 `job_id=instance_number`(1-based, 0은 폴백값이라 회피)로 배선하고 종료 시 release 호출. → **OpenHands 글루 이식이 불필요해짐**(옵션 B의 부수 이점).
- 데이터 접근: `scratch/sab/benchmark/datasets`를 `/benchmark/datasets:ro`로 **bind-mount**(upstream은 태스크마다 copy_to; 읽기전용 마운트는 에이전트 관점에서 동등하고 GB급 복사를 회피).
- 버그 1건 자체수정: `enumerate(df.iterrows())` 언패킹(`i,(idx,row)`).

## D-2. ★ 스모크 — **통과** (1 태스크 → 6 태스크 확대 검증)

1-태스크 스모크(`smoke1`)는 Submitted였으나 5턴으로 짧아 대표성 판정이 불가 → **6 태스크(`smoke6`, WORKERS=3, 19분 34초)로 확대**. **6/6 Submitted**, step_profiles 71 스텝.

### (a) 태스크 진행률 — 대표적임 (flail 아님)
| id | turns | obs | rc≠0 | fmt-err | py작성 | py실행 | 실행성공 |
|---|---|---|---|---|---|---|---|
| 1 | 14 | 11 | 4 | 2 | ✅ | ✅ | ✅ |
| 2 | 18 | 17 | 9 | 0 | ✅ | ✅ | ❌ |
| 3 | 12 | 9 | 4 | 2 | ✅ | ✅ | ❌ |
| 4 | 13 | 12 | 6 | 0 | ✅ | ✅ | ✅ |
| 5 | 10 | 7 | 3 | 2 | ✅ | ✅ | ❌ |
| 6 | 4 | 2 | 1 | 1 | ✅ | ✅ | ✅ |

- **프로그램 작성 6/6, python 실행 6/6, 성공 실행(rc=0) 3/6** → mini-swe가 SAB의 from-scratch 작성 워크플로를 **실제로 수행**한다. flail 아님.
- **turns median=12** (P1 SWE median=16) — 동일 자릿수. 워크로드가 SWE보다 약간 짧다.
- **format-error 궤적당 1.17** — **P1 SWE의 5.53보다 오히려 양호**. (원인은 동일: Qwen3 thinking이 `max_completion_tokens=2048`을 소진해 bash 블록을 못 뱉는 것. completion_tokens p95=2048=상한 → 절단 확인. **SWE와 동일 조건이므로 스캐폴드 통일 목적에 부합** — 수정하지 않는다.)
- **tool 실패율 46.6%(27/58)** — 높아 보이나 **워크로드 고유 성질**: (i) SAB 태스크가 요구하는 과학 패키지(`deepchem` 등)가 OpenHands 샌드박스 이미지에 없어 `ModuleNotFoundError` → 에이전트가 sklearn/rdkit 등으로 대체 구현, (ii) from-scratch 코드의 반복 디버깅. **하네스 결함이 아니라 Science 워크로드 자체의 tool 실패율**로 기록한다.
  - **caveat**: upstream SAB는 태스크별 conda 환경(`config_conda_env.py`)을 구성하나 본 실험은 단일 범용 이미지를 쓴다 → 실패율이 논문 조건보다 높을 수 있음. 서빙 측정(토큰·시간)에는 무해하나 **정확도(task success) 비교에는 쓰지 않는다.**

### (b) ★ d (reasoning duty) — **0.9347**
`Σreason(prefill+decode)=2,980.2s` / `Σtool=208.3s` → **d = 0.9347**

| 워크로드 | d | 비고 |
|---|---|---|
| TraceLab | 0.289 | tool-heavy |
| **Science** | **0.9347** | **decode-heavy (신규 점)** |
| SWE | 0.996 | 최고 decode-heavy |
| HLE | (원격 API 지배) | tool-wait 지배 |

→ Science는 **SWE와 TraceLab 사이, SWE에 훨씬 가까운 decode-heavy**. 예상("중간 듀티")보다 높다.

### (c) ★ heavy-tail — **존재하나 얇음 (HLE와 다름)**
| 지표 | tool_call_s |
|---|---|
| median | 0.08s |
| p95 | 2.51s |
| p99 | 58.81s |
| **max** | **189.56s** |
| max/median | **2,406×** |
| mean/median | 37.2× |

- 최장 스텝 = `python pred_programs/pred_mat_feature_select.py` (**실제 모델 학습·특징선택 실행**) — 과학 워크로드다운 tail.
- **단 tail이 매우 얇다**: 2위가 2.77s로 급락(189.6 → 2.77). 71스텝 중 1건만 tail.
- **HLE와의 대비**: HLE는 원격 API 지연이 상시 tail이라 tool-wait이 wall time을 지배했으나, **Science는 tail이 희소해 총 tool 비중이 6.5%(1−d)에 그친다** → **HLE에서 관찰된 "R≫1인데 U가 낮은" 실패 모드는 재현되지 않을 가능성이 높다**[추정, 본 스윕에서 실측 검증].
- **한계**: tail 표본 1건 = 6 태스크뿐. **본 녹화(더 큰 N)에서 재측정**해야 하며, tail이 두꺼워지면 결론을 갱신한다.

### (d) ★ fit 산출 (C_total=100,544 고정)
| 기준 | 값 | fit |
|---|---|---|
| 스텝 input median | 5,529 tok | **18.2** |
| 프로그램당 max input median | 7,259 tok | **13.9** |

→ **fit ≈ 14–18**. (참고: TraceLab fit≈25, SWE fit≈58 — 모두 TP2 기준이라 직접 비교 불가하나, **Deployment A′에서 Science는 저-fit 레짐**.)

### (e) 스윕 C 범위 제안 (fit을 걸치게)
**C = 8 · 16 · 24 · 32 · 48**
- `C=8` ≪ fit → **음성대조**(양쪽 여유, 동률 예상)
- `C=16` ≈ fit → 전이 개시
- `C=24·32·48` > fit → **default 스래싱 활성 구간**

**→ 스모크 게이트 정지. 진행률·d·heavy-tail 보고 완료.**

## D-3. 본 녹화 완료 (102 태스크) + d·fit·tail 확정

`run_sab_record_mini_yunuikang.sh full102` WORKERS=12, **3h40m**, 102/102 완주.
- exit: **Submitted 79 / ContextLengthExceeded 16 / LimitsExceeded 7**. 완주율 77%.
  - ContextLengthExceeded 16건: `dataset_preview`가 큰 태스크(최대 25k자)가 궤적 누적으로 32k 컨텍스트를 초과. **비정상 아님** — 긴-컨텍스트 프로그램이 trace에 포함되는 편이 서빙 측정에 대표적. (input p95=25,090 tok 확인)
- canonical trace: `scratch/sab/sab_trace_32b.jsonl` (102 세션, 1,363 턴, schema_ok). 정규화는 `prep_swebench_trace_yunuikang.py` **무수정 재사용**(step_profiles→canonical 범용).

### ★ 확정값 (C_total=100,544)
| 지표 | 스모크(6) | **본 녹화(102)** |
|---|---|---|
| 스텝 수 | 71 | **1,363** |
| **d** | 0.9347 | **0.9894** |
| step input median | 5,529 | **6,214** |
| **fit (step median)** | 18.2 | **16.2** |
| fit (prog max median 7,256) | 13.9 | **13.9** |
| **fit×d** | ~17 | **16.0** |
| tool median | 0.08s | 0.077s |
| tool p95 | 2.51s | 1.42s |
| tool p99 | 58.8s | 18.7s |
| tool max | 189.6s | **300.1s** |
| tool>10s 비율 | 1.4% | **1.3%** |
| completion 2048-절단율 | — | 20% |

- **d=0.9894**: 스모크(0.9347)보다 상승, **SWE(0.996)에 근접**. Science는 예상("중간 듀티")과 달리 **고듀티 decode-heavy**.
- **fit×d=16.0 ≫ 1**: 예측대로 **tr 지배 zone**(경계의 16배), f_sat=1/16≈0.06.

### ★ heavy-tail = **희소·극단 (HLE의 상시 tail과 구조적으로 다름)**
- max/median = **3,913×** (극단값 존재), 그러나 **>30s 스텝은 8건(0.6%), >10s는 18건(1.3%)** 뿐.
- median 0.077s, p90 0.12s → **90%의 스텝이 tool≈0**(순수 decode). tool 총합은 wall time의 **1.06%**(1−d)에 불과.
- **HLE 대비**: HLE는 원격 GLM API 지연이 *상시* tail이라 tool-wait이 wall time을 지배(d 낮음) → "R≫1인데 U 낮음" 발생. **Science는 tail이 희소해 1−d=1%** → HLE 실패 모드 **미재현 예측**(스윕에서 실측 검증 예정, 지시 4).
- 최장 tail = 실제 과학 연산: prog70 `single_cell_analysis_de.py`(300s), prog2 `mat_feature_select.py`(181s), prog51 `brain_blood_qsar.py`(103s), prog97 `formation_energy_prediction.py`(102s) — 모델 학습·특징선택 실행.

### ★ tail 경합-inflation 점검 (지시 1)
- **간접 증거는 inflation 부정**: WORKERS 3→12(경합 4배↑)인데 tail이 **오히려 얇아짐**(p95 2.51→1.42s, tool>10s 1.4→1.3%). 경합이 부풀렸다면 반대여야 함.
- **직접 검증 진행 중**: 최장 tail 4태스크(prog 70·2·51·97)를 **WORKERS=1(무경합)로 재측정** → 큰 스텝의 tool 시간이 재현되면 실제 연산(경합 아님) 확정. [결과는 D-4]

## D-4. tail 경합-inflation 점검 결과 — **경합 아님(실제 연산) 확정**

최장 tail 4태스크(inst 2·51·70·97)를 **WORKERS=1(무경합)로 재측정**(`rec_tailcheck`). ※ 러너가 job_id를 1~4로 재부여 → 매핑 tc1=inst2, tc2=inst51, tc3=inst70, tc4=inst97.

| instance | 12-way max_tool | 1-way max_tool | 판정 |
|---|---|---|---|
| 2 (`mat_feature_select`) | 180.9s | **296.0s** | **실제연산**(무경합이 오히려 김) |
| 51 (`brain_blood_qsar`) | 103.3s | 0.1s | 궤적분기(무거운 스텝 미도달) |
| 70 (`single_cell_analysis_de`) | 300.1s | 0.1s | 궤적분기 |
| 97 (`formation_energy_pred`) | 102.1s | 0.1s | 궤적분기 |

- **핵심**: 재현된 유일 케이스(inst2)가 **무경합에서 오히려 길다(296>181s)** → 경합이 부풀린 것이라면 무경합에서 짧아져야 하므로 **inflation 반증**. 무거운 tool 시간은 실제 과학 연산(모델 학습·특징선택) 실행 시간.
- inst 51·70·97은 temp=0 재실행에서도 배치 비결정성으로 에이전트가 **다른(가벼운) 궤적**을 택해 무거운 스텝에 도달 안 함(0.1s) → 가설 검증엔 부적합하나 경합 증거는 전혀 아님.
- **간접 증거도 일치**: WORKERS 3→12(경합 4배↑)에서 tail이 **얇아짐**(p95 2.51→1.42s).
- **결론**: **tail은 실제 연산, 경합-inflation 아님. 녹화 trace를 tail 포함 그대로 replay 안전**(HLE 스윕에서 24h 분포를 tail 포함 replay한 것과 동일 원칙).

## D-5. 스윕 캘리브레이션 (A안 — 실측 우선)

full 30-run 스윕 예상이 decode-heavy·단일GPU로 ~33–46h+로 커서, **tr·C=8·1 repeat만 먼저 실측**해 repeat 시간을 확정하기로 함(사용자 승인). [결과 D-6]

## D-6. 스윕 캘리브레이션 결과 + 스코프 (옵션 B 트림)

- **캘리브 실측**: tr·C=8·1repeat = **23분 56초**(NPROG=96, completed 96/96). → 비관 추정(225분) 대폭 하회.
- **full 30-run 착수했으나** default 고-C 스래싱이 예상보다 깊어(C=16 thru 0.027, repeat당 ~1h) ETA ~18–20h로 상향 → 사용자와 **옵션 B 트림** 합의:
  - default: C=8·16·24(이미 완료분) + **C=32·48 REPEAT=1**(붕괴 결정론적, 분산≈0이라 1회 충분).
  - tr: C=8·16·24·32·48 **REPEAT=3 유지**(대비 정밀도).
  - 최종 **default 9 run + tr 15 run = 24 run**. `sab_default.jsonl`, `sab_tr.jsonl`.

## ★ D-7. 스윕 결과 — tr 완승 (fit×d=16.0 tr지배 zone)

측정 프로토콜: 참 hit=`local_compute`(불변식), `--stream`, U 3중(gpu_util·b0_nrr·mem), 분위수, paused.

| C | 영역 | default thru | default hit_true | default p95 | tr thru | tr hit_true | tr p95 | **tr 처리량 이득** |
|---|---|---|---|---|---|---|---|---|
| 8 | <fit | 0.072 | 0.863 | 345s | 0.083 | 0.896 | 243s | **+15%** |
| 16 | ≈fit | 0.027 | 0.223 | 1464s | 0.089 | 0.851 | 403s | **+227%** |
| 24 | >fit | 0.025 | 0.136 | 2235s | 0.078 | 0.799 | 779s | **+216%** |
| 32 | >fit | 0.025 | 0.106 | 2912s | 0.070 | 0.739 | 1049s | **+175%** |
| 48 | >fit | 0.024 | 0.067 | 3157s | 0.072 | 0.733 | 1026s | **+196%** |

- **C=8(<fit) 음성대조**: 양쪽 정상(hit 0.86 vs 0.90), tr +15%(경미) — 스래싱 전이라 큰 차이 없음. ✅ 대조 성립.
- **C≥16(≈fit~>fit)**: default **단조 붕괴**(hit_true 0.86→0.07, p95 345→3157s = 9배), tr은 **hit 방어**(0.90→0.73) → **처리량 +175~227% 압승**.
- **P1 TraceLab/SWE 붕괴 임계 재확인**: 붕괴가 **C=fit(16)에서 개시** — fit이 붕괴 임계를 결정한다는 R모델 교차입증(TraceLab fit25→C32, SWE fit58→C64, Science fit16→C16).

### ★★ D-8. 지시 4 핵심 검증 — HLE "U 낮음" 실패 모드 **미재현 확정**

**U 3중 측정 (median)**:
| C | default gpu_util | default nrr | tr gpu_util | tr nrr | tr paused |
|---|---|---|---|---|---|
| 8 | 100% | 6 | 100% | 7 | 0 |
| 16 | 100% | 11 | 100% | 9 | **2** |
| 24 | 100% | 10 | 100% | 9 | **8** |
| 32 | 100% | 10 | 100% | 7 | **12** |
| 48 | 100% | 10 | 100% | 6 | **18** |

- **★ U=100% 양쪽 전 구간 포화** → **HLE 실패 모드 미재현 확정**.
  - HLE: R≫1인데 원격 GLM API tool-wait이 wall time 지배 → GPU idle-wait → 실측 U 낮음 → tr 이득이 throughput으로 환산 안 됨.
  - **Science: sparse tail(1−d=1.1%)이라 GPU idle-wait 없음 → U=1.0 포화 → tr이 포화된 GPU를 goodput으로 전환 → throughput 압승**(+175~227%).
  - → **예측 적중**: "true-U 발산(R≫1인데 U 낮음)은 *상시 tail*(HLE) 특유, *희소 tail*(Science)엔 없음" **확정**.
- **메커니즘 = occupancy 아니라 goodput** (P1 Pro6000 발견 재확인): default도 U=100%지만 스래싱 재프리필로 **낭비**(hit 0.07), tr은 **f(t) pause**로 resident를 fit 내로 유지(nrr 10→6, paused 0→18) → 같은 100% GPU를 **productive**하게 씀(hit 0.73).
- **f(t) 발동 정량**: tr paused가 C=8:0 → C=48:18로 단조 증가(default는 전 구간 0). C가 fit을 넘을수록 tr이 더 강하게 pause해 스래싱 억제.

### D-9. reported vs true hit 갭 (계측 정직성)
| C | default reported | default true | 갭 |
|---|---|---|---|
| 8 | 0.725 | 0.863 | +0.139 |
| 16 | 0.098 | 0.223 | +0.125 |
| 24 | 0.052 | 0.136 | +0.084 |
| 32 | 0.049 | 0.106 | +0.057 |
| 48 | 0.028 | 0.067 | +0.039 |
- default의 **reported `prefix_cache_hit_rate`가 참 hit(local_compute 기반)을 과소보고**(스래싱 하에서 최대 −0.14). tr은 갭≈0(reported≈true, 스래싱 없어 계측 일치). → HLE에서 본 "스래싱 하 reported 과소보고" 재확인. **참 hit 병기의 필요성 입증.**

### D-10. 정직 기록 (프레이밍·한계)
1. **스캐폴드**: mini-swe-agent (논문 OpenHands 아님). SWE와 통일해 워크로드 효과만 분리(D-0). **논문 Science 절대값 직접 대조 불가.**
2. **고듀티(d=0.989)**: Science는 SWE급 decode-heavy라 **crossover(fit×d<1 트레이드오프 영역) 진입 불가** — 단일-GPU로 fit을 16까지 줄여도 d가 높아 fit×d=16≫1. 저-fit×d 점 확보 기대는 부분 실현(fit은 낮췄으나 d가 높아 곱은 큼). **trade-off zone 재현은 여전히 4090·TraceLab이 유일 측정점.**
3. **tool 실패율 46.6%**: 범용 샌드박스에 태스크별 과학패키지 부재 탓(upstream은 태스크별 conda). **정확도(task success) 비교엔 미사용, 스케줄링 지표(토큰·시간)만 사용** — 서빙 결론에 무해.
4. **default C≥24 REPEAT=1**: 트림. 붕괴 분산≈0(C=16: 0.027/0.028/0.027)이라 정보 손실 미미.

### 산출물
- `figures/p2_sab_sweep.png` (throughput·true-hit·p95, default vs tr, fit선 표시)
- `scratch/sab/sab_{default,tr}.jsonl` (24 run), `sweep/sample_*.csv` (U 3중)
- STEPS_RESULTS 레짐 지도: **측정 5셀**로 확장(Science 추가, fit×d=16.0 tr지배).

**→ 게이트 정지·보고. 4워크로드(SWE·TraceLab·HLE·Science) 재현 완성.**
