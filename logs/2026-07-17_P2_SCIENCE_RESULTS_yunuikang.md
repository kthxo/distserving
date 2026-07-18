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
