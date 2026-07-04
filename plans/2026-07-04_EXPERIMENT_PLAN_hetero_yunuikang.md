# ThunderAgent 이종(heterogeneous) 실험 계획 — 실행 스펙

> 대상: Claude Code (이 저장소에서 작업)
> 작성 근거: `../logs/2026-07-02_EXPERIMENT_LOG_yunuikang.md`(homo-homo 완료), `../logs/2026-07-01_SETUP_NOTES_yunuikang.md`(환경)
> 저장소(서버): `/home/yunuikang/yunuikang_work/distserving`
> 브랜치: `yunuikang/thunderagent`
> 원칙: **한 번에 한 변수만 바꾼다. 기존 스크립트/버그픽스를 재사용하고 깨지 않는다.**

---

## 0. 배경 (읽고 시작)

ThunderAgent(program-aware 스케줄러, `--router tr`)를 naive 프록시(`--router default`)와
비교해, 동시 실행 프로그램 수(concurrency)를 올릴 때 KV 캐시 스래싱을 막아 throughput을
유지하는지 검증하는 연구다. 현재까지 **homo-homo**(동일 합성 워크로드 × 동일 GPU 2×4090)만
완료. 이번 목표는 아래 2×2에서 나머지 칸을 채우는 것.

| | GPU homo (4090+4090) | GPU hetero (4090+5090) |
|---|---|---|
| 데이터 homo (동일 합성) | ✅ 완료 | homo-hetero |
| 데이터 hetero (실제 trace) | hetero-homo | hetero-hetero (보류) |

실제 데이터는 **두 종류**를 쓴다: (1) **SWE-bench Lite trace**(자가 녹화, 자율 워크로드),
(2) **SyFI TraceLab**(실제 Claude Code/Codex 사용 trace). 둘을 **공통 스키마**로 정규화해
같은 replay 드라이버로 돌려 "두 독립 실제 워크로드에서 성립"을 보인다.

핵심 연구 가설: 현재 tr의 신규 프로그램 배정은 **절대 토큰 균형**(용량 비례가 아님)이라,
이종 GPU에서 작은 4090이 먼저 포화하고 큰 5090이 덜 쓰일 것이다 → **용량 비례 라우팅**의
근거를 이종 실험으로 정량 확보한다.

---

## 1. 환경 (모든 터미널에서 먼저)

```bash
source /home/yunuikang/yunuikang_work/.venv/bin/activate
HDR=/home/yunuikang/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/include/python3.12
export CPATH="$HDR" C_INCLUDE_PATH="$HDR"
export VLLM_ATTENTION_BACKEND=FLASH_ATTN
export VLLM_USE_FLASHINFER_SAMPLER=0
```

- GPU 서버: **mango1**(4×4090), **mango3**(4×4090), **goguma6**(2×5090). 완료분은 mango1 GPU0+1.
- 스크립트: `distserving/scripts/` — `workload_driver_yunuikang.py`, `run_sweep_yunuikang.sh`,
  `plot_results_yunuikang.py`, `plot_char_yunuikang.py`, `smoke_test_yunuikang.py`.
- 결과/로그: `/home/yunuikang/yunuikang_work/scratch/`, 그래프: `distserving/figures/`.

### 절대 건드리면 안 되는 것 (guardrails)
1. `ThunderAgent/__init__.py`의 **app 지연 import 버그픽스**(PEP 562 `__getattr__`) 유지.
   되돌리면 `--backends`/`--router`가 무시됨(EXPERIMENT_LOG §6).
2. 이번 단계는 **라우터 로직(`scheduler/router.py`) 수정 없음.** 관측/측정만.
   (용량 비례 라우팅 구현은 이종 결과로 근거 확보 후 별도 단계.)
3. vLLM 실행은 반드시 `--max-model-len 32768 --gpu-memory-utilization 0.92`
   (4090에서 KV 초과 회피, SETUP_NOTES 문제2).

### 실행 CLI 레퍼런스 (`python -m ThunderAgent` = `thunderagent`)
```
--host 0.0.0.0            # cross-node는 반드시 0.0.0.0 바인드(기본값 유지)
--port 9000
--backends <csv>          # 예: http://IP1:8000,http://IP2:8000
--router tr|default
--backend-type vllm
--metrics --metrics-interval 5.0
--profile --profile-dir <DIR>   # 출력: <DIR>/step_profiles.csv
--scheduler-interval 5.0        # 논문 ∆t
--acting-token-weight 1.0
--use-acting-token-decay        # 논문 f(t)=2^(-t)
```

---

## 2. 공통 trace 스키마 (canonical)

두 데이터셋을 이 JSONL 한 줄=한 턴 형식으로 정규화한다:

```json
{"session_id": "str", "turn": 0, "input_tokens": 14558, "output_tokens": 29, "tool_duration_s": 0.41}
```

- `session_id`: 워크플로우(프로그램) 식별자. 같은 세션의 턴은 turn 오름차순.
- `input_tokens`: 그 턴 요청의 prompt 토큰 수(컨텍스트 누적 반영값).
- `output_tokens`: 그 턴 생성 토큰 수.
- `tool_duration_s`: 그 턴 뒤 도구 실행 시간(다음 턴까지의 유휴). 마지막 턴은 0.
- (선택) `cached_tokens`: 있으면 기록. 없으면 생략.

정규화 산출물 위치:
- `scratch/traces/swebench_trace.jsonl`
- `scratch/traces/tracelab_trace.jsonl`

---

## Phase A — replay 드라이버 (데이터셋 무관)

**목표**: 공통 스키마 trace를 읽어, 기록된 부하를 결정적으로 재생하는 드라이버.
기존 `workload_driver_yunuikang.py`를 확장(합성 로직 재사용).

**신규 파일**: `scripts/trace_replay_driver_yunuikang.py`

**동작**:
1. `--trace <jsonl>` 로드 → `session_id`로 그룹핑, 각 세션을 턴 리스트로 정리.
2. concurrency `C`: `asyncio.Semaphore(C)`로 항상 C개 세션만 in-flight(closed-loop).
   총 세션이 부족하면 순환 재사용하되 `program_id`에 run/round 접미사로 유일화.
3. 세션 하나 = 프로그램 하나. 각 턴마다:
   - `program_id = session_id + "#" + run_idx`
   - **입력 구성(Level 1, counts)**: 세션 공통 시스템 프롬프트(프리픽스 캐시 유도) +
     **직전 턴 프롬프트에 이어붙이는 방식**으로 컨텍스트를 누적해 `input_tokens`에 맞춘다
     (세션 내 프리픽스 공유가 실제처럼 재현되도록). 부족분은 세션 고유 필러 토큰으로 패딩.
   - `max_tokens = output_tokens`, `temperature=0`, `extra_body.program_id` 지정.
   - 요청을 프록시(`:9000`)로 전송(스트리밍, `stream_options.include_usage`).
   - 응답 후 `await asyncio.sleep(tool_duration_s)` (도구 실행 목업).
4. 세션 종료 시 `POST /programs/release {program_id}`.
5. 측정 구간(steady-state)만 집계: 워밍업/tail 제외(아래 metrics 참고).

**CLI**: `--trace, --base-url, --router-url, --model, --concurrency C, --run-tag`

**수용 기준(AC)**:
- 작은 trace(예: 세션 20개)로 `C=4` 실행 시 오류 없이 완료, `/programs`가 종료 후 0 프로그램.
- 같은 trace+같은 C를 tr/default 두 번 돌려 **투입 부하(요청 수·토큰 합)가 동일**함을 로그로 확인.

---

## Phase B — TraceLab 데이터셋 준비

**목표**: TraceLab 공개 풀을 공통 스키마로 정규화(+ human-wait 제거 → 자율화).

**신규 파일**: `scripts/prep_tracelab_yunuikang.py`

**단계**:
1. `git clone https://github.com/uw-syfi/TraceLab.git` → `scratch/TraceLab/`.
   공개 커뮤니티 풀(sanitized rows) 데이터 위치·스키마를 확인(README/toolkit 참조).
2. 필드 매핑 → 공통 스키마:
   - `session_id` ← 세션 id, `turn` ← step 순서
   - `input_tokens` ← total input tokens(=cached+append), `output_tokens` ← output tokens
   - `tool_duration_s` ← **tool latency**(human wait 아님)
3. **human-in-the-loop 제거**: user-initiated step의 사람 대기(gap)는 tool_duration에 넣지 말 것.
   tool-triggered step만 이어붙여 자율 롤아웃 형태로 재구성.
4. 코딩 도메인/모델 필터 등은 옵션 인자로.
5. 출력: `scratch/traces/tracelab_trace.jsonl`.

**AC**:
- 출력 JSONL 스키마 검증(필수 필드, turn 단조 증가, tool_duration ≥ 0).
- 요약 통계 출력: 세션 수, 세션당 평균 턴, input/output 토큰 분포, tool 시간 분포.
  (EXPERIMENT_LOG §10과 대조 가능하게.)

---

## Phase C — SWE-bench Lite trace 녹화 → 정규화  🔸보류 (다음 미팅 이후)

> **[2026-07-04 스코프 변경] 이번 실행에서는 보류(drop).** 다음 미팅에서 방향 확정 후 재개.
> 이유: 실제 데이터 검증은 Phase D(TraceLab)로 이미 확보. SWE-bench 녹화는 Docker 세팅 비용이
> 크고, 이번 스코프는 네트워크(E)·이종 GPU(F) 축 검증에 집중. 아래 내용은 재개 시 참고용으로 보존.

**목표**: SWE-bench Lite를 **한 번** 라이브 실행하며 `--profile`로 trace를 박제.
`step_profiles.csv`가 이미 필요한 필드를 모두 기록한다(아래).

`step_profiles.csv` 컬럼: `program_id, step_id, prefill_s, decode_s, pause_s, tool_call_s,
prompt_tokens, completion_tokens, cached_tokens, kv_hit_rate, completed_at`

**단계**:
1. Docker + mini-swe-agent 준비: `examples/inference/mini-swe-agent/scripts/setup/setup.sh`
   참고. (Docker 세팅은 이 Phase에서만 필요.)
2. vLLM(아무 여유 GPU 1장) + ThunderAgent `--router default --profile
   --profile-dir scratch/rec_swebench` 로 기동(녹화는 스케줄링 영향 최소화 위해 default 권장).
3. 소규모 라이브 실행(먼저 `--workers 4`로 파이프라인 검증 → 이후 수백 세션 확보):
   ```
   mini-extra swebench --subset lite --split test --workers <W> --output scratch/swebench_out
   ```
   요청이 반드시 프록시(`:9000`)를 통과하고 `extra_body.program_id`가 붙는지 확인
   (`examples/.../models/vllm_model.py`가 job_id 기반 주입).
4. 녹화된 `scratch/rec_swebench/step_profiles.csv` → 공통 스키마 변환.
   **신규 파일**: `scripts/prep_swebench_trace_yunuikang.py`
   - `session_id←program_id, turn←step_id-1, input_tokens←prompt_tokens,
     output_tokens←completion_tokens, tool_duration_s←tool_call_s, cached_tokens←cached_tokens`
   - 출력: `scratch/traces/swebench_trace.jsonl`
5. 녹화에 쓴 **모델명·workers·수집일**을 파일 헤더 주석/사이드카 JSON에 문서화.

**AC**:
- `swebench_trace.jsonl` 스키마 검증 + 요약 통계.
- (선택, 고충실도 앵커) 실제 프롬프트 텍스트도 함께 저장해 Level 2 replay 여지 남김.

---

## Phase D — hetero-homo 실험 (데이터 축만 변경)

> **[2026-07-04 스코프 변경] TraceLab 데이터셋만 수행(완료). SWE-bench 데이터셋 반복은 보류**
> (Phase C 보류와 연동). TraceLab: default/tr 각 18런(C=2·4·8·16·32·48 × 3회) 완료 —
> `../logs/2026-07-03_EXPERIMENT_LOG_hetero_yunuikang.md` §D-4·D-6 참조. 핵심: tr이 KV hit rate 유지(default 0.026 붕괴
> 대비 c=48에서 30배), 단 이 하드웨어에선 throughput/p95는 tr 불리(프로그램이 KV에 육박).

**설정**: **2×4090 단일노드(mango1 GPU0+1)** — homo-homo와 동일 인프라. 데이터만 실제 trace로.

**절차** (~~두 데이터셋 각각 반복~~ → TraceLab만; SWE-bench 보류):
1. vLLM 2개 기동(GPU0→:8000, GPU1→:8001), 프록시 `--backends :8000,:8001`.
2. concurrency 스윕을 tr/default 각각 실행. 기존 러너 재사용/확장:
   ```
   bash scripts/run_sweep_yunuikang.sh <tr|default> <out.jsonl> 8 16 32 48 64 96 128
   ```
   단, 부하원을 `trace_replay_driver_yunuikang.py --trace <swebench|tracelab>`로 교체.
3. **각 점 3회 반복**(에러바 확보 — EXPERIMENT_LOG §11 미결 항목).

**AC / 산출**:
- tr vs default: throughput(prog/s), KV hit rate, p95 latency 곡선 (데이터셋별).
- 그래프: `figures/hetero_homo_<dataset>_{throughput,hitrate,p95}.png`
  (`plot_results_yunuikang.py` 재사용).
- 기대: 실제 데이터에서도 중고부하에서 tr 우위 유지되는지 확인.

---

## Phase E — cross-node homo (네트워크 축 검증 다리)  🔸보류 (다음 미팅 이후)

> **[2026-07-04 스코프 변경] 이번 실행에서는 제외(drop).** 다음 미팅 이후 재개.
> 이유: 네트워크 축 격리 검증보다 이종 GPU(F, goguma6 5090) 결과를 우선. 아래는 재개 시 참고용.

**목적**: GPU 이종을 넣기 전에 **네트워크만** 격리 검증. GPU는 동일(4090+4090),
서버만 분리(mango1 + mango3).

**단계**:
1. mango1, mango3 각각 vLLM 기동(`--host 0.0.0.0`, 포트 8000).
   방화벽/포트 개방, VPN 도달성 확인(`curl http://<MANGO3_IP>:8000/health`).
2. 노드 간 RTT 기록: `ping <MANGO3_IP>` (단일노드 대비 오버헤드 baseline).
3. 프록시(둘에 닿는 호스트) `--backends http://<MANGO1_IP>:8000,http://<MANGO3_IP>:8000`.
4. 합성 워크로드로 concurrency 스윕(tr), **백엔드별 split 균형** 확인.

**AC**:
- 두 백엔드에 요청이 고르게 분산(split ≈ 5:5), 전역 큐가 노드 넘어 정상 동작.
- 네트워크 오버헤드(단일노드 대비 latency 증가분) 수치화.
- `<MANGO1_IP>`, `<MANGO3_IP>`는 VPN/접속가이드로 확인해 채울 것.

---

## Phase F — homo-hetero 실험 (GPU 용량 축, 핵심)

**설정**: 합성 워크로드(homo-homo와 동일) × **4090(mango) + 5090(goguma6)**.
데이터는 homo-homo와 동일하게 고정 — **바뀌는 변수는 GPU 용량뿐**.

**단계**:
1. mango(4090):8000, goguma6(5090):8000 각각 vLLM(같은 모델 `Qwen/Qwen3-8B`, 같은 플래그).
   cross-node이므로 Phase E의 네트워크 체크 선행.
2. **각 GPU의 실제 KV 풀 크기 기록**: vLLM 시작 로그 `GPU KV cache size: N tokens` 양쪽.
   (기준값: 4090≈43,888 토큰; 5090은 실측 확정 — EXPERIMENT_LOG §10-4/§10-5.)
3. 프록시 `--backends http://<MANGO_IP>:8000,http://<GOGUMA6_IP>:8000 --router tr`.
4. concurrency 스윕(tr, 그리고 대조로 default).
5. **백엔드별로 쪼갠 지표 수집**이 이 Phase의 핵심:
   - 백엔드별 split(요청량), 백엔드별 KV 사용률(`kv_cache_usage_perc` 시계열),
     백엔드별 pause 횟수(`/programs` per_backend, `get_program_stats`).

**AC / 가설 검증**:
- 4090이 5090보다 먼저 포화(pause·재프리필↑)하고 5090이 상대적으로 under-utilized인지 확인.
- 성립하면 → **용량 비례 라우팅 필요성의 정량 근거**(다음 연구 단계 입력).
- 그래프: `figures/homo_hetero_perbackend_{kv_usage,split,pause}.png`.

---

## 측정 & 분석 (공통)

- **Throughput**: prog/s(및 completion tok/s). steady-state 구간만(워밍업/ tail 제외).
- **KV hit rate**: 백엔드 `/metrics`의 `prefix_cache_hits_total / prefix_cache_queries_total`
  **델타**(구간 앞뒤 스냅샷 차). 멀티백엔드는 델타 합산.
  (프로그램 단위 hit는 `step_profiles.csv`의 `kv_hit_rate`=cached/prompt로도 확인 가능.)
- **재프리필 총량**: `prompt_tokens_total` 델타(스래싱 지표; 낮을수록 좋음).
- **Latency**: 프로그램 완료시간 mean/p50/p95/max.
- **부하분산**: 백엔드별 query 델타(split).
- 이 워크로드에선 `num_preemptions`는 0으로 잡히므로 **hit rate와 재프리필 총량**이
  스래싱의 실제 지표(EXPERIMENT_LOG §9).

---

## 실행 순서 요약 (권장)

> **[2026-07-04 갱신 v2] 이번 실행 순서**: D(TraceLab) 완료 → **F(homo-hetero, goguma6 5090 실제)**.
> **C·D(SWE-bench)·E(cross-node homo)는 모두 보류(다음 미팅 이후).**

1. ~~**Phase A** replay 드라이버~~ ✅ 완료.
2. ~~**Phase B** TraceLab 준비~~ ✅ 완료.
3. ~~**Phase D**(TraceLab) — hetero-homo~~ ✅ **완료**(default/tr 18런 + 그래프 + 요약).
4. ~~**Phase C** SWE-bench 녹화 → **Phase D**(SWE-bench)~~ 🔸**보류(다음 미팅 이후)**.
5. ~~**Phase E** cross-node homo (네트워크 다리)~~ 🔸**보류(다음 미팅 이후)**.
6. **Phase F** homo-hetero (GPU 용량 축) — mango1 4090 + goguma6 5090 실제. **핵심 결과. ← 다음**
7. hetero-hetero는 보류(미팅 후 방향 확정).

각 Phase 끝에 결과 JSONL·그래프·요약을 남기고, 완료 시 `../logs/2026-07-02_EXPERIMENT_LOG_yunuikang.md`에
섹션 추가(설정/명령/결과표/해석/한계).

---

## 미결 · 확인 필요 (사람이 채울 항목)
- `<MANGO1_IP>`, `<MANGO3_IP>`, `<MANGO_IP>`, `<GOGUMA6_IP>`: VPN/접속가이드로 확인.
- goguma6(5090) 환경: 4090과 동일 env 우회(CPATH/FLASH_ATTN/flashinfer)가 필요한지 확인.
- SWE-bench 녹화 모델: 여유 GPU/시간에 맞춰 선택 후 문서화.
- TraceLab 공개 풀의 정확한 파일 경로/필드명: clone 후 확인해 Phase B 매핑 확정.
```
