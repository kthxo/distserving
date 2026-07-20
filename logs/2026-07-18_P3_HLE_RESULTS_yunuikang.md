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

### B-3. ★ 스모크 → tool 100% 실패 진단·수정 (하네스 debugging)
- **1차 스모크**: orchestrator tool call 전부 "342 invalid"(len 0) → GLM·검색 미발동. 프록시·orchestrator·GLM은 직접 테스트 정상(무죄) → eval 하네스 문제로 격리.
- **원인(파일:라인)**: `LLM_CALL_p3_yunuikang.py:919` `send_tools_to_vllm = bool(tools) and os.path.exists(str(model))` — tools를 **model이 파일 경로일 때만** 전달. 우리는 `--served-model-name orchestrator`(경로 아님) → `os.path.exists("orchestrator")=False` → **tools 미전달** → orchestrator가 tool 못 부름.
- **수정(격리본)**: `os.path.exists(model) or str(model) in {"orchestrator"}` 로 orchestrator 이름도 허용.
- **검증(1문항 재스모크)**: **tool call 0→2 유효**(search+answer), retriever 쿼리 수신(13줄), 2-round 완료(무효 30-round 루프 해소). GLM·FAISS 실제 발동 확인.

### B-4. ★ 스모크 게이트 통과 (수정 후 5문항, 2026-07-18)
- **tool 실패율: 100% → 0%** (16 tool call 전부 유효, responses 16/16, 에러 0).
- **tool 분포**: search 12 + answer 4 → 원격-tool 축 발동. tool 응답에 `"model":"glm-4.5-flash"` = **GLM 실사용 확인**.
- **FAISS 검색 실작동**: search 응답 `context_str="Documents: Doc 1..."` (문서 반환).
- **포맷 준수**: GLM 출력에 `\boxed` 9회·`<answer>` 1회 → 기대 포맷. 최종 pred 정상 추출('D','18','yeyo','Z+Z+Z+Z+Z').
- 속도: round당 ~4–31s(Nemotron decode). 문항당 ~40s–3min. (5문항 중 4 완료; 1개 slow/미완 — 경미.)
- **판정: 스모크 PASS** — 워크로드가 HLE 원격-tool 축(GLM tools + FAISS retrieval)을 정상 자극. **스윕 진행 가능(사용자 승인 대기).**

### B-5. ★ 다중-window 녹화 — 1·2단계 (패턴 확보 + 샘플러 기동) (2026-07-18)
계획서 §4-4-4(개정) A/B/C 실행. 게이트 준수: 샘플러만 띄우고 정지.
- **1. 패턴 확보(GPU 잠깐)**: 스모크 파이프라인 재사용, `LLM_CALL_p3`에 env-gated 캡처 로깅(`P3_GLM_CAPTURE`) 추가 → HLE 5문항 실행으로 **GLM 호출 프롬프트 26개 캡처**(`glm_prompts_captured.jsonl`). 대표 subset **4개**(search sm/lg + answer md/lg, 실제 max_tokens 유지) → `glm_prompts_sampler.jsonl`.
- **FAISS 검색 지연(결정적 상수)**: `/retrieve` 8콜 측정 → **median 319ms, 312–331ms(매우 타이트)** → 상수로 둠(t_tool = GLM지연 + FAISS 0.32s).
- **2. 24h 샘플러 기동(unattended, GPU 해제)**: `glm_latency_sampler_p3_yunuikang.py`(신규) — 고정 4프롬프트를 GLM API에 **15분 간격 24h** 발사, 지연+timestamp 로깅(호출별 latency·kind·성공/재시도·ts·out_tokens). **GPU 미사용**, daily-cap 800(<1000/day), 429 백오프. tmux `p3sampler`, 출력 `glm_latency_24h.jsonl`.
  - **orchestrator(GPU1)·retriever(GPU2) 정지 → GPU1·2 해제**(각 2MiB). GPU0 타 사용자(506352) 미접촉.
  - **★ 시간변동 조기 확인**: 1-tick 검증(search 1.6–3.6s) → 기동 첫 tick(search 7.6–11.3s) — 같은 프롬프트인데 지연 상승(=측정 대상 현상).
- **판정: 1·2단계 완료, 정지.** 24h 후 사용자 재호출 시 3단계(window별 분포·d·성공률 표 + 게이트).
- 가드레일: router.py 무수정, 격리 복사본(*_p3), 키 미기재(env·헤더만), GPU0 미접촉.

### B-6. ★ 3단계 — 녹화 분석 + 게이트 (2026-07-20, GPU 미사용)
384샘플(search 192 + answer 192, 24h, 15분 간격, 성공 100%)을 UTC 4h window(6개)로 분할. `figures/p3_hle_window_latency.png`.
- **t_reason(Nemotron-8B 턴 GPU 시간) = median 14.0s**(스모크 48샘플). **FAISS = 0.32s 상수**. t_tool = GLM지연 + (search면 FAISS).

**window별 지연(median/p95, robust) + 유효 d = t_reason/(t_reason+t_tool):**
| window(UTC) | n | srch med/p95 | ans med/p95 | tool med | **eff d** |
|---|---|---|---|---|---|
| 00–04 | 64 | 1.5/5.6 | 1.5/57.5 | 1.8 | **0.887** |
| 04–08 | 64 | 3.2/9.9 | 2.8/30.6 | 2.9 | 0.830 |
| 08–12 | 64 | 1.9/9.4 | 3.0/26.4 | 2.7 | 0.839 |
| 12–16 | 64 | 3.3/4.6 | 3.0/30.6 | 3.1 | 0.820 |
| **16–20** | 64 | 3.9/11.5 | 4.0/51.8 | 4.2 | **0.770** (peak, 최저 d) |
| 20–24 | 64 | 1.7/4.5 | 2.1/45.3 | 2.0 | 0.876 |
- **전체 24h tail(표본 두꺼움)**: search med 2.0 p95 11.2 p99 23.3 max 38.6 / answer med 2.9 p95 **48.8** p99 **67.1** max **98.0**.

**게이트 판정:**
- **(a) window 간 d 변동**: **유의미하나 median 기준 moderate** — d 0.770~0.887(spread 0.116, ×1.15). **peak(16–20)에서 tool 지연 최고(med 4.2s)→d 최저(0.770), off-peak(00–04·20–24)에서 최저 지연→d 최고**(peak/off-peak 패턴 뚜렷). 단 **median d 변동이 작은 이유 = t_reason(14s)이 median t_tool(2–4s)을 지배**. **★ 진짜 stochastic은 tail**: answer p95가 window별 26→57s로 크게 변동, 개별 spike 최대 98s(t_reason 초과) — 이 tail 이벤트가 tr의 f(t)를 시험.
- **(b) R모델 시험 셋업 가능**: d가 window간 이동(0.77~0.89) + tail 분포가 window별 상이 → **per-window replay로 "d/지연분포가 이동할 때 tr/default가 R=k_fit·d 예측대로 움직이나" 시험 가능**. (k_fit·U는 스윕에서 실측; 여기선 d축 lever 확보.)

**→ 3단계 완료·정지. replay 스윕은 별도 승인 대기.** (스윕 승인 시 orchestrator/retriever 재기동 → 통합분포 주 비교 + window별 개별 replay + R모델.)

### B-7. replay 스윕 — 실행 중 (2026-07-20)
- **재기동**: 오케스트레이터(Nemotron-8B) GPU1 단독(replay는 tool=sleep이라 retriever/GLM 불필요, GPU2 미사용). **GPU 유휴 확인**: GPU1 유휴 확인 후 기동, GPU0 유휴(타 사용자 종료)·GPU2 타 사용자(suuinmoon/K-Search) 미접촉. **KV 풀 = 502,944 tok**(block16×31434).
- **HLE 트레이스**(`prep_hle_trace_p3`, 신규): smoke5b 턴 구조(N search 1~9 + 1 answer + final) + **24h 지연 분포 그대로 sampling(tail 보존, max 98s)** + input 성장(150→15k tok). 256세션/1271턴, tool_duration median 2.7s·p95 24.4s·max 98s. 고정 seed → tr/default 동일 트레이스(공정).
- **스윕**(`run_serving_eval_hle_p3`, 신규 격리): default vs tr, **C=24·32·40·48, NPROG=96, REPEAT=3**, --stream. 참 hit=`local_compute` 병기, 샘플러 --gpus 1(U). 
- **⚠️ 정직한 사전관찰**: input median 2952 → **fit ~170 ≫ C=48** → default 스래싱 약할 수 있음(단 후반 턴 15k context×C에서 압박 가능). 스모크: default C=24 thru 0.745p/s·hit 0.737. **tr≥default 예상하되 gap은 KV 여유로 작을 수 있음 → 실측·정직 기록.**

### B-8. ★ replay 스윕 결과 + 게이트 (2026-07-20) — 정직한 null-ish
`figures/p3_hle_sweep.png`. 3회 평균, 참 hit=local_compute(=reported hit, 괴리 없음).
| C | def thru | tr thru | Δ | def hit | tr hit | def p95 | tr p95 | def U | tr U | tr k_fit |
|---|----------|---------|---|---------|--------|---------|--------|-------|------|----------|
| 24 | 0.905 | 0.901 | −0% | 0.918 | 0.934 | 52.9 | 52.8 | 0.70 | 0.66 | 17.6 |
| 32 | 1.163 | 1.159 | −0% | 0.959 | 0.941 | 52.7 | 53.5 | 0.68 | 0.70 | 21.3 |
| 40 | 1.269 | 1.257 | −1% | 0.937 | 0.962 | 46.3 | 47.4 | 0.68 | 0.67 | 23.3 |
| 48 | 1.330 | 1.308 | −2% | 0.947 | 0.939 | 48.2 | 46.3 | 0.66 | 0.67 | 25.4 |

**결과 해석 (정직):**
- **tr ≈ default (Δthru −0~−2%, hit 양쪽 0.92~0.96 高, p95 46~53s 동일)** — **tr≥default(item2)는 성립(tr 열세 아님)하나 gap≈0**.
- **원인 = 스래싱 없음**: HLE input median 2952 → **fit≈170 ≫ C=48**(KV 502,944). default가 KV 과구독 안 함 → hit 붕괴 없음 → **tr이 막을 스래싱이 없음** → tr=default. (참 hit=reported hit 확인 → 숨은 스래싱 없음.) → **R모델 핵심 주장과 정합**: "tr은 default가 스래싱할 때만 이긴다", 여기선 default 무붕괴.
- **item3(tail의 f(t)) — 관찰 불가·정직 기록**: KV 여유(fit≫C)라 긴 acting(최대 98s) 프로그램도 KV에 여유롭게 잔류 → **tr의 f(t) evict/감쇠가 발동할 압력 자체가 없음**. → 논문의 f(t) regime(5090 작은 KV=스래싱)을 이 HW(8B on 96GB)에서 재현하려면 **KV 축소(gpu-mem-util↓로 fit≈C)** 필요(후속 옵션).
- **★ R모델 한계(heavy-tail) 발견**: R=k_fit·d ≫1(14.5~20.8) → U≈1 예측이나 **실측 U≈0.67**. **heavy-tail(98s acting) 때문에 순간순간 다수 프로그램이 off-GPU → mean-d 기반 R이 U를 과대예측**. → R모델은 heavy-tail 워크로드에서 mean-d로는 U를 못 맞춤(정직한 한계, tail-aware duty 필요).
- **item4(window별 replay)**: median d-lever ×1.15로 약한 데다 **주 결과가 무붕괴(tr=default)라 window별로도 tr=default** → R모델 d-축 검증 **불가(참고용, 정직 기록)**.

**→ P3 replay 스윕 완료·게이트 정지.** 핵심: 이 HW에선 HLE 무붕괴 → tr=default(R모델 정합), f(t) tail-handling은 KV 축소해야 관찰 가능(후속).

### B-9. ★ KV-축소 후속 스윕 — 붕괴 레짐 재현 (2026-07-20)
**KV 축소**: gpu-mem-util 0.90→**0.32** → **C_total 502,944 → 101,840 tok**(1/4.9), **fit≈34.5**(C=24·32 이하 / C=40·48 초과 = 걸침). 동일 24h tail 트레이스·동일 스윕 dims. `figures/p3_hle_kv_contrast.png`.

| C | 레짐 | def thru | tr thru | Δ | def hit(true) | tr hit(true) | Δhit | def U | tr U | **tr paused(mean/max)** | def paused |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 24 | <fit | 0.840 | 0.827 | −2% | 0.668 | 0.693 | +4% | 0.73 | 0.71 | 0.52 / 9 | 0.00 |
| 32 | <fit | 0.998 | 0.960 | −4% | 0.632 | 0.666 | +5% | 0.70 | 0.66 | 1.81 / 14 | 0.00 |
| 40 | >fit | 1.074 | 0.987 | −8% | 0.621 | 0.659 | +6% | 0.75 | 0.64 | 3.16 / 22 | 0.00 |
| **48** | **>fit** | 1.063 | 1.039 | −2% | **0.513** | **0.654** | **+28%** | 0.78 | 0.67 | **5.13 / 20** | 0.00 |

**(a) C>fit에서 flip? — hit는 YES, throughput은 NO(정직)**
- **default hit 붕괴 재현**: C=48(>fit)에서 true hit **0.62→0.513**(reported 0.38). **tr은 전 C에서 hit 평탄(0.65~0.69)** → **C=48에서 tr +28%**. → **논문의 "tr이 스래싱 억제" 재현.**
- **그러나 throughput은 tr이 −2~−8%로 열세**(논문 Fig4c의 tr 1.48× 이득 **미재현**). **원인(메커니즘)**: HLE는 **tool-wait이 wall-time을 지배**(tool median 2.7s·tail 98s, d~0.82) → KV 스래싱의 재프리필 비용이 throughput에 미치는 영향이 작음 → tr이 hit를 지켜도 throughput으로 환산 안 됨. 반면 TraceLab/SWE는 prefill/decode-bound라 스래싱이 throughput을 직접 붕괴시켜 tr이 크게 이겼음. **→ "tr 승리는 스래싱이 throughput을 지배할 때만"**(R모델의 조건부성을 워크로드 축으로 보강).

**(b) f(t) tail 처리 — ★ 발동 확인**
- **tr paused가 C와 함께 증가(0.52→1.81→3.16→5.13, max 20~22), default는 항상 0.00.** tr acting≈12~13(긴 tool-wait 프로그램 상주). → **KV 압력 상승 시 tr의 f(t)가 실제로 프로그램을 pause/evict해 resident를 용량 내로 유지** → hit 방어. **큰-KV(무붕괴)에선 발동 안 하던 메커니즘이 축소-KV에서 정상 작동**.

**(c) R모델 heavy-tail 한계 — 붕괴 레짐에서도 지속**
- R=k_fit·d=14.0~15.7 ≫1 → 예측 U=1.00, **실측 U=0.64~0.71**. 두 레짐 모두 과대예측. **원인: heavy-tail acting(12~13 프로그램이 상시 tool-wait, tail 98s)로 순간 off-GPU 비율이 큼** → mean-d 기반 R이 U를 못 맞춤. **→ heavy-tail 워크로드엔 tail-aware duty 필요(모델 한계 확정).**

**(d) 방법론 발견 — reported hit의 default 과소보고 실증**
- C=48 default: **reported 0.380 vs true(local_compute) 0.513 (gap +13.3%p)**. 스래싱 시에만 발생(C≤40은 gap≈0). → **reported hit만 쓰면 default 붕괴를 과장**. P1 발견을 정량 확인, 참 hit 병기의 필요성 입증.

**→ 대조 결론**: 같은 워크로드·트레이스에서 **KV만 1/4.9로 줄이자 무붕괴(tr=default) → 붕괴(default hit 0.513 vs tr 0.654, f(t) 발동)**로 전환. **fit이 C를 넘는지가 tr 개입 여부를 결정**(R모델 정합). 단 HLE에선 tool-wait 지배로 **hit 방어가 throughput 이득으로 전환되지 않음**(논문 대비 정직한 차이).
