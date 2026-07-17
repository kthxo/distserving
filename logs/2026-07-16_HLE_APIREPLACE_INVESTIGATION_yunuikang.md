# HLE(ToolOrchestra) 유료 API → GLM 등 무료/저렴 원격 API 대체 조사 (2026-07-16)

> 작성: 강윤의 · 브랜치 `yunuikang/thunderagent` · 조사 태스크(실행/유료호출 없음, 코드 정독 + 웹 조사)
> 대상 코드: `examples/inference/ToolOrchestra/evaluation/{eval_hle_local.py, LLM_CALL.py, retrieval_hle.py, model_configs/hle_local_router.json, launch_hle_inference.sh, setup_envs.sh_example}`
> 목표: HLE 도구 호출의 유료 외부 API(gpt-5 등)를 **원격 무료/저렴 API(GLM 등)로 대체** 가능한지 + 최소 변경안.

---

## 1. 유료 호출 지점 매핑 (`eval_hle_local.py` MODEL_MAPPING + dispatch + TOOL_PRICING)

| 도구(role) | 기본 모델 | provider/경로 | 유료? | 근거(코드) |
|-----------|----------|--------------|-------|-----------|
| **enhance_reasoning** (reasoner-1/2/3) | **gpt-5** | OpenAI (`get_openai_client`) | 💰💰 **최대 비용** (TOOL_PRICING: out **$10/M**) | `if "gpt-5" in model_name` 분기 |
| **search** (search-1/2/3, 쿼리작성) | **gpt-5-mini** | OpenAI | 💰 (out $2/M) | MODEL_MAPPING |
| **answer** (answer-1..4, answer-math) | **openai/gpt-oss-120b** | **Together** (`model_type="together"`) | 💰 (약 $0.3/M, 이미 저렴) | answer 분기 `elif gpt-oss-120b` |
| **retrieval** (증거검색) | 로컬 FAISS (127.0.0.1:1401) | **로컬 GPU** | ✅ 무료 | `retrieval_hle.py`(faiss) |
| web search (옵션) | Tavily | Tavily | 💰 ($0.01/search) **옵션** | `used_tavily` ~515 |
| judge (정답채점, 옵션) | gpt-5-mini | OpenAI | 💰 **기본 OFF** (`HLE_ENABLE_JUDGE=0`) | ~430–443 |
| **오케스트레이터 8B** (우리가 서빙) | Qwen3-8B/Nemotron-8B | **로컬 vLLM**(우리 GPU) | ✅ 무료 | = 우리 워크로드 |

- **비용 지배자 = gpt-5(reasoner)**. search(gpt-5-mini)·answer(gpt-oss-120b/Together)는 그 다음. judge는 기본 OFF, Tavily는 로컬 FAISS로 대체 가능(끄면 됨).
- **핵심 인사이트**: 가장 큰 비용은 gpt-5(reasoner). **reasoner/search만 대체해도 지배 비용이 사라짐.** answer의 gpt-oss-120b(Together)는 이미 $0.3/M로 저렴.

## 2. 클라이언트 구성 = 대체 난이도 (`LLM_CALL.py`)

`get_llm_response()`가 model_type / 모델명 문자열로 3(+1)개 경로 분기:
| 경로 | 클라이언트 | base_url | 비고 |
|------|-----------|----------|------|
| OpenAI | `get_openai_client()` → `OpenAI(api_key=OPENAI_API_KEY)` | **기본 OpenAI(코드상 미오버라이드)**; 키 없으면 NVIDIA Azure 폴백 | SDK가 env `OPENAI_BASE_URL`은 존중하나 코드 인자로는 안 바꿈 |
| Together | `get_together_client()` → `OpenAI(api_key=TOGETHER_API_KEY, base_url="https://api.together.xyz/v1")` | **하드코딩** | |
| 로컬 vLLM | `OpenAI(api_key="EMPTY", base_url="http://{ip}:{port}/v1")` (model_config) | 무인증·http·로컬 | GLM(https+키) 직접 불가 |
| **Nebius(선례)** | `OpenAI(base_url="https://api.tokenfactory.nebius.com/v1/", api_key=NEBIUS_API_KEY)` | 하드코딩, `qwen3-32b`+`NEBIUS_API_KEY`시 | **이미 원격 OpenAI-호환 provider가 배선된 선례** |

- **결론**: "임의 원격 provider(키+커스텀 base_url)"용 범용 분기는 없음(Together·Nebius만 하드코딩). GLM을 깨끗이 붙이려면 **작은 provider 경로 1개 추가**가 정석. (Nebius 블록이 그대로 템플릿.)
- 라우팅은 `eval_hle_local.py`의 문자열 분기(`"gpt-5" in model_name`, `"gpt-oss-120b" in model`, `model_type`)로 결정 → 모델명 바꾸면 분기도 같이 손봐야 함(=env-only 편법이 불완전한 이유).

## 3. 원격 무료/저렴 대체 후보 (웹, 2026-07)

| provider | OpenAI-호환 base_url | 무료/단가 | rate limit | 원격(stochastic 보존)? |
|----------|---------------------|-----------|-----------|----------------------|
| **Z.ai (Zhipu GLM)** | `https://api.z.ai/api/openai/v1` (또는 `open.bigmodel.cn/api/paas/v4`) | **GLM-4.7-Flash·4.5-Flash 완전 무료**, 1000 req/day 무료티어. 유료 GLM-4.7 = $0.6/M in·$2.2/M out | 무료티어 1000/day | ✅ |
| **DeepSeek** | `https://api.deepseek.com` | deepseek-v4-flash **$0.14/M in·$0.28/M out**(초저가, "GPT-5급 1/10가") | 여유 | ✅ |
| **OpenRouter** | OpenAI-호환 | `:free` 모델 ~23종(Qwen3-Coder, DeepSeek-V4-Flash, Llama-3.3-70B 등) | **~20/min·200/day** | ✅ (rate limit이 오히려 Table 6와 정합) |

- **무료티어 일일 한도 주의**: Z.ai 1000/day, OpenRouter 200/day. 스윕(동시성 24–48 × ~130분 × 여러 run)에서 호출량이 커 **무료 한도 초과 가능** → 그땐 DeepSeek/GLM **유료(센트~몇 달러 수준)** 로.
- rate-limit 스로틀은 **throughput 절대값을 낮추지만**, stochastic-tool 성격엔 부합(단 절대비교는 어차피 안 함).

## 4. 최소 변경안 (diff 수준)

**전략: gpt-5(reasoner)·gpt-5-mini(search)를 GLM/DeepSeek 원격으로, answer는 Together 유지(이미 저렴).**

1. **`LLM_CALL.py`** — provider 함수 1개 추가(Nebius/Together 블록 복제, ~15줄):
   ```python
   def get_glm_client(timeout_s=None):
       return OpenAI(api_key=os.getenv("GLM_API_KEY"),
                     base_url=os.getenv("GLM_BASE_URL","https://api.z.ai/api/openai/v1"),
                     timeout=timeout_s)
   ```
   `get_llm_response`에 `elif model_type=="glm" or "glm" in model.lower():` 분기 추가 → `get_glm_client()` 사용.
2. **`eval_hle_local.py`**:
   - `MODEL_MAPPING`: reasoner-* → `"glm-4.7-flash"`(무료), search-* → `"glm-4.5-flash"`(무료). answer-*는 gpt-oss-120b 유지(또는 deepseek-v4-flash로).
   - `enhance_reasoning`/`answer` dispatch: `"gpt-5" in model_name` 분기 옆에 `"glm" in model_name`(→ `model_type="glm"`) 분기 추가. `supported_models` assert가 remap된 이름과 맞도록 확인.
3. **env**(`setup_envs.sh`): `GLM_API_KEY` 설정. `HLE_ENABLE_JUDGE=0` 유지(judge비 0). Tavily 키 비우고 **로컬 FAISS retrieval만** 사용.
4. (선택) `TOOL_PRICING`에 glm 항목 추가 — 비용 로깅 정확도용(기능 무관).

- **더 최소(비추천): env-only** — `OPENAI_BASE_URL`+`OPENAI_API_KEY`를 GLM으로. 그러나 API에 보내는 `model="gpt-5"`를 GLM이 거부 → 모델명 바꿔야 하고, 바꾸면 `"gpt-5" in name` 분기가 깨짐. **불완전 → §4-1,2 소폭 코드수정이 견고.**

## 5. 판정

- **(a) 대체 가능? → ✅ 조건부 가능.** GLM(Z.ai) 무료 Flash 또는 DeepSeek-v4-flash(초저가)가 OpenAI-호환이라 붙음.
- **(b) 최소 변경:** `LLM_CALL.py`에 GLM provider 함수 1개 + `eval_hle_local.py` MODEL_MAPPING/분기 소폭(~수십 줄). 지배비용(gpt-5)만 갈아끼워도 대부분 절감.
- **(c) stochastic-remote 성격 → ✅ 보존.** 원격 호출 유지(네트워크 지연·rate limit). 로컬 서빙 대체는 성격 상실이라 최후.
- **(d) 남은 블로커/비용:** 오케스트레이터 checkpoint(Nemotron-8B 또는 Qwen3-8B) 다운로드, **FAISS INDEX_DIR(eval.index+eval.jsonl) 확보/구축**(retrieval 필수), conda 환경(vllm1, retriever-clean). 무료티어 일일한도 초과 시 DeepSeek/GLM 유료(총 몇 $). judge OFF·Tavily OFF로 추가비 0. Continuum은 우리 repo 미구현 → default/tr만.
- **(e) 권장:** **reasoner/search = GLM-4.7-Flash(무료) 또는 DeepSeek-v4-flash(초저가) 원격**, answer = Together 유지. 코드 소폭 수정. 무료한도 초과 시 DeepSeek 유료 폴백(스윕 전체 몇 $ 예상). **로컬 대체는 비추천(성격 상실).**

## 6. 확인 필요 (미해결)
- FAISS 인덱스(eval.index/eval.jsonl) 원본 배포처 — 레포/릴리스/별도 구축 필요 여부.
- 오케스트레이터 checkpoint: 논문 Qwen3-8B로 갈지(우리 서빙 대상=무료) vs repo 기본 Nemotron-Orchestrator-8B.
- 무료티어 실제 호출량 vs 일일한도 — 스윕 규모 확정 후 재계산(초과 시 유료 총액 산정).
- GLM 무료 Flash가 reasoner(코드 생성)·answer 품질에서 충분한지(정확도는 우리 관심 아님=throughput만, 단 tool 실패율이 워크로드 형상 바꿀 수 있어 스모크 1회 권장).
