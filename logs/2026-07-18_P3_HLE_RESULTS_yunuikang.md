# P3 — HLE / ToolOrchestra serving-eval (2026-07-18)

> 작성: 강윤의 · 브랜치 `yunuikang/thunderagent` · 서버 nutella1 · **P1/P2와 독립 로그**
> 전제 문서: 계획서 `plans/2026-07-15_PLAN_pro6000-tp-rescale_yunuikang.md` **§4-4**(HLE)·**§4-4-2**(GLM 코드변경)·**§4-4-3**(blocker) · HLE 조사 `logs/2026-07-16_HLE_APIREPLACE_INVESTIGATION_yunuikang.md` · P1 결과 `logs/2026-07-16_TP2_RESULTS_yunuikang.md`
> **이어짐(3줄)**: (1) P1 완료(k_fit-flip·R모델 교차입증), P2는 SAB 데이터 password-protected로 보류 → **P3 선행**. (2) HLE는 duty 축이 아니라 **원격·stochastic·heavy-tailed tool 축** — tr의 `f(t)=2^(-t)` pause/resume 코스트모델이 시험받는 케이스(계획 §1-2 B). 예측: tr이 KV hit 낮추고 GPU util 택함(논문 Fig 4c·5c). (3) 가드레일 P1 동일 + **GPU0은 타 사용자 가능 → 미접촉**.
> 형식: 질문 → 증거(수치·파일:라인) → 결론 → [추정]/한계.

---

## Phase A — 스코핑 (조사만, 코드 실행/GPU 미접촉) — 정지·보고 지점

### A-1. ★ GPU 가용성 (최우선) — 판정: **BLOCKER (GPU0 타 사용자 점유)**
- **증거(`nvidia-smi` 2026-07-18)**: index0(Pro5000 48G)=**46,760/48,935 MiB 점유**(타 사용자 PID 506352 `VLLM::EngineCore`, UUID 2269ba96) — **~2GB만 남음**. index1·2(Pro6000 96G)=각 93,250 MiB(내 tp2serve, Deployment A).
- **결론**: 계획의 "orchestrator=GPU0" 경로 **막힘**. Deployment B(orch + retriever, 2 GPU 필요) 배치 옵션:
  - (a) GPU0 반환 대기(타 사용자 종료 불확실).
  - (b) **★ tp2serve(A) 정지 → GPU1(orch 8B) + GPU2(retriever) 사용** — 둘 다 96GB, 8B+FAISS에 충분. **권장**(P3는 Deployment A 불필요). → **사용자 확인 필요**(tp2serve 정지 승인).
  - GPU0은 확인 전까지 미접촉 유지.

### A-2. conda 환경 — 판정: **미설치 → 구축 필요(작업량 중)**
- **증거**: `which conda` = 없음(venv만). launch 스크립트 `launch_hle_inference.sh:214,227`가 `conda activate $RETRIEVER_ENV`(retriever-clean)·`$VLLM_ENV`(vllm1) 요구.
- **결론**: (a) miniconda 설치 + `vllm1`·`retriever-clean` 생성, 또는 (b) launch 스크립트를 우리 venv로 개작(격리 복사본 `*_p3`). 내가 수행 가능(시스템 변경=miniconda는 user-space 설치라 sudo 불요). [작업량: 반나절]

### A-3. 오케스트레이터 checkpoint — 판정: **해결 (Nemotron-Orchestrator-8B, ungated)**
- **증거**: README `ToolOrchestra/README.md:101` = `git clone nvidia/Nemotron-Orchestrator-8B`(repo reproduce 레시피). launch `--model-type` 기본 `Qwen/Qwen3-8B`(아키텍처). 논문(README:119) "ToolOrchestra(HLE) – Qwen3-8B" = Qwen3-8B **base arch**. Nemotron-Orchestrator-8B = **Qwen3-8B 아키텍처를 tool-orchestration용 fine-tune**한 NVIDIA 모델. HF 둘 다 **ungated 확인**.
- **결론**: repo-tested 레시피대로 **`nvidia/Nemotron-Orchestrator-8B`**(≈16GB) 사용 = 논문 Qwen3-8B와 정합. (사용자가 순수 Qwen3-8B 선호 시 대체 가능하나 orchestration 프롬프트 정합은 Nemotron이 안전.) [확정 가능, blocker 아님]

### A-4. FAISS 인덱스 — 판정: **다운로드+설치 필요(중), blocker 아님**
- **증거**: `multi-train/index`(ungated)에 `eval.index`=**2.89GB** + `eval.jsonl`=**7.69GB**(=eval만 ~10.6GB; train/wiki는 불필요). **`faiss` 미설치**(ModuleNotFoundError) → `faiss-gpu` 설치 필요(conda 경로 권장), 리트리버 GPU 로딩 필요.
- **결론**: eval 인덱스 ~10.6GB clone(디스크 318GB 여유) + faiss-gpu 설치 + 리트리버 GPU(A-1의 GPU2). 내가 수행 가능. [작업량: 다운로드+설치 ~1–2h]

### A-5. GLM 무료 대체 — 판정: **API 키 사용자 제공 필요 + 코드변경 필요(중)**
- **증거**: `GLM_API_KEY`/`GLM_BASE_URL` env **미설정**. `LLM_CALL.py`에 **GLM 경로 없음**(grep 0건) → 계획 §4-4-2 코드변경(`get_glm_client` + `eval_hle_local.py` MODEL_MAPPING/dispatch 분기) 필요.
- **결론**: (1) **★ Z.ai GLM 무료 API 키 = 사용자 발급·제공 필요**(무료티어 1000 req/day). (2) 코드변경은 내가 수행(격리 복사본 `*_p3`, router.py 무관). [작업량: 코드변경 ~2–3h + 스모크]

### A-6. HLE 데이터셋 접근 — 판정: **gated (사용자 제공 필요)**
- **증거**: `cais/hle` **gated=auto**(HF 약관 동의 필요). 녹화하려면 HLE 문항 필요.
- **결론**: **★ 사용자가 HF에서 HLE 약관 동의 + HF_TOKEN 제공**(gated=auto라 클릭 동의 즉시 승인, SAB의 password-SharePoint보다 가벼움). [사용자 제공 항목]

---

### ★ Phase A 산출 — 사용자 결정/제공 필요 항목
| # | 항목 | 필요 |
|---|---|---|
| **1** | **tp2serve(Deployment A, GPU1+2) 정지 승인** | P3는 A 불필요·GPU0 막힘 → 정지해 GPU1(orch)+GPU2(retriever) 확보(권장). 정지할까? |
| **2** | **Z.ai GLM 무료 API 키** | 사용자 발급·제공(무료티어). tool(reasoner/search/answer) 대체용. |
| **3** | **HLE gated 접근** | HF에서 `cais/hle` 약관 동의 + HF_TOKEN 제공(gated=auto, 즉시 승인). |

**내가 수행 가능(승인 후, blocker 아님)**: conda+envs 구축, faiss-gpu 설치, FAISS eval 인덱스(~10.6GB)+Nemotron ckpt(~16GB) 다운로드, GLM 코드변경(§4-4-2), 스모크.

**checkpoint(A-3) 확정**: Nemotron-Orchestrator-8B(ungated, repo 레시피=논문 정합).

### Phase B 예상 소요 (위 3개 확보 가정)
- 셋업(conda·faiss·다운로드 ~27GB·코드변경): **~0.5–1일**. 스모크 1회(tool 실패율·포맷 준수). record→replay 녹화 + 스윕(default/tr, C=24·32·40·48, per-C NPROG, REPEAT=3 = 24런; 단일 8B라 P1 32B보다 가벼움): **~4–7h**. → **총 ~1–1.5일**.
- 한계(계획 §): Continuum 미구현 → tr vs default(vLLM)만. 논문은 HLE가 tr–Continuum 격차 최소(코스트모델 민감) 워크로드라 명시 → caveat.

**→ Phase A 정지. 위 3개(tp2serve 정지·GLM 키·HLE 접근) 결정/제공 대기.**

---

## Phase B — 진행 (승인됨 2026-07-18)

### B-0. 크레덴셜 로드 + tp2serve 정지
- `.hle_env`(chmod 600) 소싱 → GLM_API_KEY(len49)·GLM_BASE_URL·HF_TOKEN(len37) 로드 확인(값 미출력). 도구 셸 비대화형이라 사용자 export 미상속 → 파일 소싱 방식으로 해결.
- **tp2serve(Deployment A) 정지**: tmux+vllm(Qwen3-32B)만 종료. **GPU1·GPU2 해제(각 2MiB)**, **GPU0 타 사용자 PID 506352 미접촉 유지**.

### B-1. ★ GLM 엔드포인트 de-risk (스모크 전 선제 확인 — 실측)
- **[정정 필요] base URL**: 사용자 `.hle_env`의 `GLM_BASE_URL=https://api.z.ai/api/openai/v1` → **전 경로 404 NOT_FOUND**. 실측 작동 = **`https://api.z.ai/api/paas/v4`**. (curl 프로브로 확인.)
- **모델**: `glm-4.5-flash` 작동(200). `glm-4.7-flash`·`glm-4-flash`·`glm-4.6-flash` 미존재(1211 Unknown Model). → **전 tool을 `glm-4.5-flash`로 매핑**(계획 §4-4-2의 4.7-flash는 미존재라 대체).
- **★ thinking 모드**: `glm-4.5-flash`는 기본 reasoning 모델 — content 빈 채 `reasoning_content`에 사고 소진(max_tokens 전량) → tool 출력 공백 → **실패율 급증 위험**. **`thinking:{"type":"disabled"}` 추가 시 content 정상**(예: '4', out_tok 2). → **모든 GLM 호출에 thinking disabled 적용**(§4-4-1 포맷 준수 선제 해결).
- 키는 헤더/env로만, 로그에 값 미기재.

### B-2. 셋업 진행 (2026-07-18)
- **faiss-gpu**: `pip install faiss-gpu-cu12` → faiss 1.14.1(venv, **conda 불필요** — A-2 해소).
- **다운로드 완료**(`scratch/p3_assets/`): FAISS eval 인덱스 9.9GB(eval.index+eval.jsonl), HLE 데이터셋 262MB, Nemotron-Orchestrator-8B 31GB.
- **★ 추가 의존성 발견**: `retrieval_hle.py:85`가 임베더 **`Qwen/Qwen3-Embedding-8B`(~16GB)** 요구 → 다운로드 중(background, ungated).
- **GLM 코드변경(격리 복사본, §4-4-2)**: `LLM_CALL_p3_yunuikang.py`(get_glm_client + GLM 분기, thinking disabled) + `evaluation/eval_hle_local_p3_yunuikang.py`(import p3, MODEL_MAPPING 전량 `glm-4.5-flash`, dispatch: gpt-5 조건에 `or glm` 추가·search 자동 라우팅). 둘 다 py_compile OK. **원본 미변경**.
- **✅ GLM 유닛 테스트**: `get_llm_response(model="glm-4.5-flash")` → 정상 생성 + `\boxed{}` 포맷 포함(thinking disabled 효과).
- **남은 것**: 임베더 다운로드 완료 → model_config(오케스트레이터를 프록시로) + HLE example_path 배선 → launch 스크립트 venv 개작(retriever GPU2 + orchestrator GPU1 + proxy) → **스모크 1회 → tool 실패율·포맷 준수율 보고(정지)**.
- 가드레일 유지: router.py 무수정, 키 로그 미기재, GPU0 미접촉.
