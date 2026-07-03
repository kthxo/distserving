# 실험 저널 — ThunderAgent 이종(heterogeneous) 실험

> 작성: 강윤의 · 브랜치 `yunuikang/thunderagent` · 서버: mango1 (KAIST)
> 시작: 2026-07-03
> 근거 계획서: `../EXPERIMENT_PLAN_hetero_yunuikang.md`
> 선행 결과: `EXPERIMENT_LOG_yunuikang.md`(homo-homo 완료), `SETUP_NOTES_yunuikang.md`(환경)
> 진행 순서: Phase A → B → D(TraceLab) → C → D(SWE-bench) → E → F (한 번에 한 Phase, 사이에 확인).

---

## Phase A — replay 드라이버 (데이터셋 무관)

**목표**: 공통 스키마 trace(JSONL, 한 줄=한 턴)를 읽어 기록된 부하를 **결정적으로** 재생하는
드라이버. 기존 `workload_driver_yunuikang.py`의 metrics 델타/스트리밍(TTFT)/summary 로직 재사용.

**공통 스키마 (계획서 §2)**:
```json
{"session_id":"str","turn":0,"input_tokens":14558,"output_tokens":29,"tool_duration_s":0.41}
```

### A-0. 사전 확인 (환경)
- Qwen3-8B tokenizer 로드 성공(HF 캐시). `apply_chat_template(tokenize=True)`는 `BatchEncoding`
  반환 → 토큰 수는 `["input_ids"]` 길이. 렌더 문자열 재encode와 일치(23토큰 확인).
- **핵심 설계 근거**: replay 드라이버가 쓰는 tokenizer/chat template이 vLLM 백엔드와 **동일**하므로,
  드라이버 로컬 토큰 카운트 = 서버가 반환할 `prompt_tokens`. → 로컬에서 `input_tokens`에 맞춰
  필러를 채우면 서버에서도 그 값이 재현된다(Level 1 counts replay).

### A-1. 구현한 파일
- **`scripts/trace_replay_driver_yunuikang.py`** — 메인 replay 드라이버.
  - `load_trace()`: JSONL → `session_id` 그룹핑, 턴 `turn` 오름차순 정렬, 세션 id로 결정적 정렬.
  - `Padder`: Qwen3-8B tokenizer로 `apply_chat_template` 토큰 수를 계산해, 세션 고유 필러(중간
    vocab id를 세션시드로 뽑아 decode)를 채워 `input_tokens[t]`에 맞춤. 최대 4회 선형 보정.
  - `run_program()`: 세션=프로그램. 누적 messages(system 공유 + 이전 user/assistant + 이번 user),
    `max_tokens=output_tokens`, `program_id`, 스트리밍(옵션 TTFT), 턴 뒤 `sleep(tool_duration_s)`,
    종료 시 `POST /programs/release`. metrics 델타/summary는 기존 드라이버 로직 재사용.
  - `build_program_list()`: `num_programs`>세션수면 순환 재사용, `program_id=sid#run_idx`.
    seed는 **세션인덱스*1000+run_idx**(결정적; `hash()` PYTHONHASHSEED 의존 제거 — 아래 문제 참고).
  - `--dry-run`: HTTP 없이(GPU 불필요) 페이로드 구성·토큰매칭·투입부하만 검증.
  - steady-state: 완료순 앞뒤 `--warmup-frac`(기본 0.1) 제외 후 throughput/latency 집계.
- **`scripts/make_mini_trace_yunuikang.py`** — 검증용 합성 미니 trace(세션 20, 누적 input_tokens).

### A-2. 발생한 문제와 해결
- **비결정성 버그**: 초기엔 필러 seed에 `hash(session_id)`를 썼는데, Python 문자열 해시는
  프로세스마다 무작위화(PYTHONHASHSEED)돼 **두 실행의 총 투입 토큰이 76195 vs 76207로 갈림**
  → AC(동일 부하) 위반. → seed를 **세션인덱스·run_idx 기반 결정적 값**으로 교체해 해결.

### A-3. 검증 결과 (GPU 불필요, dry-run)
```
python scripts/make_mini_trace_yunuikang.py --sessions 20   # -> scratch/traces/mini_trace.jsonl (67턴/20세션)
python scripts/trace_replay_driver_yunuikang.py --trace mini_trace.jsonl --dry-run --concurrency 4 --router {tr|default}
```
| 항목 | 결과 |
|------|------|
| 토큰 매칭 정확도 | **within_1pct=100%**, mean_abs_err **0.27토큰**, max 2~3토큰 |
| 결정성(tr vs default 동일부하) | turns=67, in_tok=**76200 (동일)**, match_mean=0.269 (동일) ✅ **AC2 충족** |
| 세션 순환 재사용 | num_programs=30>20세션 → 99턴, program_id `sess###+run_idx`로 유일 ✅ |
| 완료/실패 | 20/20 completed, 0 failed ✅ |

### A-4. AC 상태
- ✅ **AC2** (같은 trace+C를 tr/default 두 번 → 투입 부하 동일): dry-run으로 완전 검증.
- ⏳ **AC1** (세션 20개 C=4 실제 실행 완료 + 종료 후 `/programs` 0 프로그램): 로직·완료는
  dry-run으로 검증. **실제 프록시 엔드투엔드 스모크는 vLLM+프록시 기동(GPU 점유)이 필요** →
  규칙 5에 따라 사용자 승인 대기.

### A-5. 다음 (사용자 승인 필요)
실제 프록시 대상 C=4 엔드투엔드 스모크를 위해 아래가 필요:
1. 어느 GPU 1장(또는 2장)에 vLLM을 띄울지 — 예: `CUDA_VISIBLE_DEVICES=0 vllm serve Qwen/Qwen3-8B
   --port 8000 --max-model-len 32768 --gpu-memory-utilization 0.92` (SETUP_NOTES env 적용).
2. ThunderAgent 프록시(`--router default --metrics --profile`) 기동.
3. 그 뒤: `python scripts/trace_replay_driver_yunuikang.py --trace mini_trace.jsonl --concurrency 4
   --router default --stream` 실행 → 완료 후 `GET /programs`가 0 프로그램인지 확인(AC1 마무리).

### A-6. ⏸ 일시 중단 (2026-07-03)
- 사용자 이동으로 **GPU 스모크는 진행하지 않고 여기서 일시 정지**. GPU는 4장 전부 유휴,
  vLLM/프록시 미기동(아무것도 점유 안 함).
- Phase A 상태: 코드 구현·dry-run 검증·AC2 충족·커밋(`0ccfcca`) 완료. **남은 것은 AC1(실측
  엔드투엔드 스모크)뿐이며 GPU 승인 대기.**
- 재접속 후 결정할 것: (1) GPU0 1장 스모크 / (2) GPU0+1 2장 스모크 / (3) 스킵하고 Phase B(TraceLab
  클론·정규화, GPU 불필요)로 진행. 3 선택 시 TraceLab 코딩도메인/모델 필터 방향도 함께 결정.

### A-7. 🛑 환경 블로커 발견 — NVIDIA 드라이버 다운그레이드 (2026-07-03, 재접속)
- 사용자가 **GPU0 1장 스모크** 승인 → vLLM 기동 시도.
- 실행 명령:
  ```
  CUDA_VISIBLE_DEVICES=0 vllm serve Qwen/Qwen3-8B --port 8000 \
    --max-model-len 32768 --gpu-memory-utilization 0.92   # + SETUP_NOTES env
  ```
- **엔진 초기화 실패**. 로그(`scratch/vllm_smokeA_8000.log`) 근본 원인:
  ```
  RuntimeError: The NVIDIA driver on your system is too old (found version 12060).
  ```
- 진단:
  | 항목 | 값 |
  |------|-----|
  | 현재 드라이버 | **560.35.05** (CUDA Version 12.6) |
  | SETUP_NOTES 기록 | 595.71.05 (CUDA 13세대) — **그 사이 다운그레이드됨** |
  | torch | 2.11.0+**cu130** (CUDA 13 드라이버 필요) |
  - torch(cu130)가 요구하는 CUDA 13 런타임을 현재 드라이버(12.6)가 지원 못 함 → GPU init 실패.
- 조치: 실패한 vLLM 프로세스 정리(`pkill`), GPU 4장 다시 유휴 확인. **아무 GPU도 점유 안 함.**
- **이건 사용자/관리자 결정이 필요한 블로커** → 여기서 멈추고 문의. 해결 옵션:
  - (A) 관리자에게 드라이버를 ≥580(CUDA 13)로 복원 요청 — 사용자 sudo 없음.
  - (B) venv의 torch/vLLM을 현재 드라이버(560/CUDA12.6)에 맞는 **cu12x 빌드로 재설치**
    (예: `uv pip install vllm --torch-backend=cu126`). sudo 불필요하나 재현 환경 변경 → 승인 필요.
  - (C) 드라이버가 아직 CUDA13을 지원하는 **다른 서버**(mango3/goguma6 등)에서 진행.
- Phase A 코드/AC2는 이미 완료(GPU 무관). AC1 실측만 이 블로커 해소 후 가능.

