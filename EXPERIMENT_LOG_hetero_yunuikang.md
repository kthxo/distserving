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

---

## Phase B — TraceLab 데이터셋 준비 (GPU 불필요, 블로커 우회하며 진행)

> GPU 드라이버 블로커(A-7)와 무관하게 진행 가능한 작업이라 idle 중 착수. 정규화 파이프라인을
> 구현·검증했고, **전체 데이터셋 다운로드·필터 확정은 사용자 결정 대기**(B-4).

### B-1. TraceLab 클론 + 데이터 위치·스키마 파악
- `git clone --depth 1 https://github.com/uw-syfi/TraceLab.git` → `scratch/TraceLab/`.
- 저장소 내 실제 per-turn 데이터: **`example_sessions/sanitized/round_trace.jsonl`** (공개 배포 형태,
  id 가명화·경로/도구입력 제거). 19턴 / **2세션**(Claude 10라운드 `claude-opus-4-8`, Codex 9라운드 `gpt-5.4`).
- **전체 공개 데이터셋은 저장소에 없음** — GitHub releases의 `syfi_coding_trace.jsonl.gz`(정규화 JSONL,
  동일 row 스키마) / `syfi_coding_trace.duckdb` 별도 다운로드.
- 필드 매핑(계획서 §2 canonical): `session_id←session_id`, `turn←round_index`,
  `input_tokens←input_tokens_total`(=prefix+newly_append, 누적 반영), `output_tokens←output_tokens`,
  `cached_tokens←claude_cache_read_input_tokens/prefix_tokens`.
- **tool_duration_s**: 각 라운드 `tools[]`의 wall span `max(result_at)−min(emitted_at)`(병렬 도구
  중복 회피), 도구 없으면 0. → **human-in-the-loop 대기 자동 제외**: 사람이 여는 라운드
  (`first_input_event_type=user_message`)는 tools 비어 있어 0. 세션 마지막 턴도 0으로 강제.

### B-2. 구현한 파일
- **`scripts/prep_tracelab_yunuikang.py`** — round_trace(.jsonl/.jsonl.gz) → canonical JSONL.
  - 필터: `--provider {all|claude|codex}`, `--model <substr>`, `--min-turns`, `--include-reasoning`.
  - 필터 후 세션별 `turn` 0..n-1 재인덱싱(단조 보장), 스키마 검증(`validate()`), 요약통계 출력,
    사이드카 `*.meta.json`(소스·필터·행수) 기록.

### B-3. 검증 결과 (2세션 샘플, GPU 불필요)
```
python scripts/prep_tracelab_yunuikang.py    # -> scratch/traces/tracelab_trace.jsonl
```
- **스키마 검증 통과**(violations 0), turn 단조 증가, tool_duration ≥ 0. ✅ **AC(스키마) 충족**.
- 요약통계(§10과 대조):
  | 지표 | min | median | max | mean |
  |------|-----|--------|-----|------|
  | 세션당 턴수 | 9 | 9.5 | 10 | 9.5 |
  | input_tokens | 9,324 | 32,272 | 48,305 | 27,053 |
  | output_tokens | 49 | 273 | 2,475 | 597 |
  | tool_duration_s | 0.0 | 0.145 | 21.467 | 4.21 |
  | cached_tokens | 3,456 | 27,217 | 47,506 | 24,924 |
- **실제 워크로드 특성**(합성 대비): 합성은 input~14.5k 균일·output~28 고정·tool 0.4s 설계값이었으나,
  실제는 input **9.3k~48.3k 가변**, output **49~2475**(실제 reasoning 길이), tool **0~21.5s 실측 지연**.
  → 실제 데이터에서 KV 압박·재프리필이 훨씬 불균일. (Phase D에서 tr 이점 재확인 대상.)
- **replay 드라이버 왕복 검증**(dry-run, tracelab_trace 입력): 19턴, token_match within_1pct 0.89,
  평균오차 44토큰(≈27k 프롬프트의 0.16%). 큰 타깃에서 필러 보정이 잘 수렴함 확인.

### B-4. ⏳ 사용자 결정 대기 (Phase B 마무리 조건)
1. **전체 데이터셋 다운로드 여부**: 지금은 저장소 내 **2세션 샘플**뿐. Phase D 실험에 쓰려면
   releases의 `syfi_coding_trace.jsonl.gz`(전체 sanitized all-user trace) 다운로드가 필요.
   → 다운로드할지, 어느 정도 규모면 되는지 결정 필요(네트워크·용량).
2. **필터 확정**: `--provider`(claude/codex/all), `--model`, `--include-reasoning`(Codex reasoning
   토큰을 output에 포함할지) 기본값을 무엇으로 할지. 현재 스크립트 기본=all·미포함.
3. (B-3 파이프라인은 전체 데이터셋에도 그대로 적용 가능 — 파일 경로만 `--in ...jsonl.gz`로 교체.)

### B-5. 전체 데이터셋 다운로드 완료 (2026-07-03)
- 사용자 승인 → releases `v2026-06-08-syfi-trace`의 **`syfi_coding_trace.jsonl.gz` (53.6 MB)** 다운로드.
  경로: `scratch/traces/syfi_coding_trace.jsonl.gz`.
- 검증: **357,161턴 / 4,265세션**. provider: claude 140,338 / codex 216,823.
  top models: gpt-5.5(103k), claude-opus-4-7(88.6k), gpt-5.4(56.5k), gpt-5.3-codex(29.7k),
  claude-opus-4-6, claude-haiku-4-5, claude-sonnet-4-6, claude-opus-4-8 등.
- 정규화(Phase D용)는 필터 확정(B-4-2) 후 `--in syfi_coding_trace.jsonl.gz`로 실행 예정.

---

## A-8. 🔴 드라이버 블로커 심화 — torch cu126 성공했으나 vLLM 0.24.0이 CUDA13 빌드 (2026-07-03)

> 사용자 승인: "1은 torch 재설치". 진행 결과, torch 교체는 됐으나 **vLLM 바이너리 자체가 CUDA13**
> 이라 driver 560에서 여전히 실행 불가 — "torch 재설치"를 넘어서는 결정 필요.

### 진행 & 발견
1. **롤백 스냅샷**: `uv pip freeze > scratch/pip_freeze_before_cu126.txt` (torch/vllm cu130 원본 기록).
2. **torch cu126 재설치 성공**: `uv pip install torch==2.11.0 torchvision==0.26.0 torchaudio==2.11.0
   --torch-backend=cu126 --reinstall-package torch|torchvision|torchaudio`.
   → `torch 2.11.0+cu126`, nvidia-*-cu12(12.6) 설치. **`torch.cuda.is_available()=True`,
   4×4090 인식, GPU matmul 성공** — driver 560과 torch는 이제 정상.
3. **그러나 vLLM 기동 실패**: `ImportError: libcudart.so.13: cannot open shared object file`.
   → vLLM 0.24.0의 컴파일 확장 `vllm._C_stable_libtorch`가 **CUDA 13 런타임(libcudart.so.13)**에 링크됨.
4. **vLLM cu126 재설치 시도도 실패**: `uv pip install vllm==0.24.0 --torch-backend=cu126
   --reinstall-package vllm` 후에도 `import vllm._C_stable_libtorch` → 동일 `libcudart.so.13` 에러.
   → **PyPI의 vllm 0.24.0 휠은 CUDA13 단일 빌드**. `--torch-backend`는 torch 인덱스만 바꿀 뿐 vLLM
   바이너리의 CUDA 링크는 안 바뀜. cu12 빌드가 인덱스에 없음.
5. libcudart.so.13을 억지로 제공해도 4090은 forward-compat 미지원 → 실제 GPU 호출에서 driver
   major 불일치로 실패. **결론: vLLM 0.24.0(CUDA13)은 driver 560(CUDA12.6)에서 실행 불가.**

### 현재 상태
- torch=cu126(정상), vLLM=cu13(실행불가). 롤백은 `pip_freeze_before_cu126.txt`로 즉시 가능.
- GPU 4장 유휴, 서버 미기동.

### 🛑 사용자 결정 필요 (torch 재설치 범위 초과)
- (1) **드라이버 ≥580 복원(관리자)** — 기존 재현 스택(torch cu130 + vllm cu13) 그대로 유지.
  homo-homo 결과와 **완전 동일 환경** 보장. *권장(결과 비교가능성 최상).* → 이 경우 torch cu130 롤백.
- (2) **vLLM을 CUDA12.x 빌드 버전으로 다운그레이드** — torch cu126 유지. 단 vLLM 버전이 바뀌어
  **homo-homo baseline과 환경 불일치**(동작/성능 차이 가능), ThunderAgent 호환성 재확인 필요.
  (driver 560=CUDA12.6이므로 cu126 이하 빌드 필요 → 상당히 오래된 vLLM일 수 있어 리스크.)
- (3) **다른 서버(mango3/goguma6)** 에서 진행 — 드라이버가 CUDA13 지원하면 기존 스택 그대로.
  서버 IP·GPU 지정 필요.
- **사용자 결정(2026-07-03)**: 처음엔 (3) 다른 서버 선택했으나, 이후 **(1) 관리자에게 드라이버
  복원 요청**하기로 방향 전환(관리자 문의 메시지 작성 중). mango1 드라이버를 595.71.05(CUDA13)로
  복원되면 기존 재현 스택 그대로 사용. → 복원 후 torch를 cu130으로 롤백 예정
  (`scratch/pip_freeze_before_cu126.txt`).

### B-6. 전체 데이터셋 규모 분석 + 하드웨어 fit 서브셋 (2026-07-03, GPU 불필요)
- 전체 정규화(all providers) 결과 요약: **4,265세션 / 357,161턴**. 그러나 **실제 대용량 컨텍스트**라
  4090으로 그대로 재생 불가:
  | 지표 | median | p95 | max |
  |------|--------|-----|-----|
  | 세션당 턴수 | 17 | 315 | 7,610 |
  | input_tokens | 124,018 | 406,015 | 999,888 |
  | output_tokens | 214 | 1,993 | 64,000 |
  | tool_duration_s | 0.169 | 30.2 | **154,088 (≈42h)** |
- **핵심 발견**: turn의 **92.5%가 vLLM `--max-model-len 32768` 초과**. 전 구간 ≤32768인 세션은
  **23%(982개)** 뿐(≤16k 7.5%, ≤8k 2.1%). input_tokens=0 무효행 12개. tool wall>300s 2,368턴.
  → 실제 워크로드를 4090(32k/KV~44k)에 맞추려면 **fitting 전략(설계 결정)** 필요.
- **prep 스크립트 확장**: 무효행(input≤0) 자동 제거 + `--max-input-tokens N`(어느 턴이든 N 초과 시
  세션 통째 제외; 누적 컨텍스트 무결성 보존) + `--cap-tool-s S`(멀티시간 유휴 갭 클립).
- **Phase-D fit 서브셋 생성**(바로 사용 가능):
  `prep_tracelab_yunuikang.py --in syfi_coding_trace.jsonl.gz --out tracelab_fit32k.jsonl
   --max-input-tokens 32768 --cap-tool-s 30` → **982세션 / 6,107턴**, input median 18k(max 32,753),
  tool median 0.047s(cap 30s). schema_ok ✅.
  - 산출물: `scratch/traces/tracelab_fit32k.jsonl`(+`.meta.json`), 전체: `tracelab_trace_full.jsonl`.
- **⏳ 남은 설계 결정(사용자/지도교수)**: fitting 전략을 (a) ≤32768 세션만(현 fit 서브셋, 실제이나
  짧은 세션 편향) / (b) 턴별 클립 / (c) 토큰 스케일다운 중 무엇으로 할지, provider 필터(claude/codex),
  include-reasoning 여부. 4090 KV(~44k)로는 32k 프로그램 1개가 거의 KV를 다 차지 → 달성 가능
  concurrency 범위가 좁음(스래싱은 c=2에서도 유발되나 스윕 폭 제한) — 이 점도 함께 판단 필요.

---

## A-9. ✅ 드라이버 복원 → 환경 복구 → Phase A 실측 스모크 통과 (2026-07-03)

- **관리자가 드라이버 복원**: `nvidia-smi` → **595.71.05 (CUDA 13.2)**. (다운그레이드됐던 560→595 복귀.)
- **환경 롤백**: torch를 cu126→**cu130으로 복원**(`--torch-backend=cu130 --reinstall-package
  torch|torchvision|torchaudio`, uv 캐시라 즉시). 이유: cu126 스택은 CUDA13 런타임(libcudart.so.13)을
  제거해 vLLM(cu13 빌드)이 여전히 실패 → cu130 복원으로 nvidia-cu13 런타임 재설치.
  - 검증: `torch 2.11.0+cu130`, `cuda.is_available()=True`(4 devs), **`import vllm._C_stable_libtorch` OK**
    (libcudart.so.13 에러 해소).
- **vLLM 기동 성공**(GPU0, :8000): `GPU KV cache size: 43,888 tokens`(§10 4090 기준값과 정확히 일치),
  `Maximum concurrency ... 1.34x`. (경고 `libnvrtc.so.13`은 flashinfer JIT 관련 비치명적 — env 우회로 무해.)
- **ThunderAgent 프록시**(:9000, `--router default --metrics --profile`): 기동 OK,
  `router_mode=default`, backend 1개, 지연 import 버그픽스 정상 작동.
- **Phase A 실측 스모크**(mini_trace 20세션, C=4, stream):
  ```
  python scripts/trace_replay_driver_yunuikang.py --trace mini_trace.jsonl \
    --base-url http://localhost:9000 --backends http://localhost:8000 \
    --concurrency 4 --router default --stream --run-tag smokeA
  ```
  | 항목 | 결과 |
  |------|------|
  | completed / failed | **20 / 0** ✅ |
  | token_match | **within_1pct=1.0, max_abs_err=1토큰** (라이브 서버 prompt_tokens = 우리 목표) ✅ |
  | prefix_cache_hit_rate | 0.68 (누적 컨텍스트로 실제 KV 재사용 관측) |
  | 종료 후 `/programs` | **`{}` (programs_count=0)** — 전부 정상 release ✅ |
  - 산출물: `scratch/smokeA_replay.jsonl`.
- **→ Phase A AC1 충족**(무오류 완료 + 종료 후 0 프로그램). **AC2는 이미 충족(A-3).
  ⟹ Phase A 완전 완료.**
- 스모크 후 서버 정리, GPU 4장 유휴 복귀.

### 상태 요약 (2026-07-03 현재)
- **환경**: 정상 복구(driver 595/CUDA13, torch cu130, vLLM 0.24.0 동작). homo-homo와 동일 재현 스택.
- **Phase A**: ✅ 완료. **Phase B**: 파이프라인·전체 데이터셋·fit 서브셋 준비 완료, 단 **fitting 전략·필터
  최종 결정(B-6)만 남음**.
- **다음**: 계획서 순서상 **Phase D(TraceLab, 2×4090 mango1 GPU0+1)**. 단 (1) fitting 전략 확정,
  (2) 대규모 concurrency 스윕은 GPU 장시간 점유 → **사용자 명시 승인 필요**.

---

## Phase D — hetero-homo (TraceLab, 2×4090) — 셋업 완료, 스윕 대기 (2026-07-03)

- **사용자 결정**: fitting 전략 **(a) fit32k 서브셋**(`scratch/traces/tracelab_fit32k.jsonl`,
  982세션/6,107턴, input≤32k, tool cap 30s), Phase D 진행 승인, **tmux로 실행**.

### D-0. 준비한 스크립트 (신규)
- **`scripts/_serve_vllm_yunuikang.sh <GPU> <PORT>`** — env 우회 포함 단일 vLLM 백엔드 기동 헬퍼.
- **`scripts/run_trace_sweep_yunuikang.sh <tr|default> <out.jsonl> <trace.jsonl> [C...]`** —
  2백엔드 프록시를 해당 router로 재기동 후 concurrency 스윕, **각 점 REPEAT회 반복**(기본 3, 에러바).
  부하원 = `trace_replay_driver_yunuikang.py`. env knobs: `NPROG`(점당 프로그램, 기본 64),
  `REPEAT`(기본 3), `TAG`(데이터셋 태그). 결과: 점·반복마다 JSON 1줄 append.

### D-1. 현재 기동 상태 (이 세션에서 띄워둠 — 계속 살아있음)
- **tmux 세션 `phaseD`**: window `gpu0`=vLLM :8000(GPU0), `gpu1`=vLLM :8001(GPU1).
  둘 다 `GPU KV cache size: 43,888 tokens`(4090 기준 일치). `tmux attach -t phaseD`로 확인.
- **프록시**: nohup `thunderagent :9000 --router default --metrics --profile`, 2백엔드 연결(up).
- 검증: `default c=8, 48프로그램` 1회 실행이 **2분 초과**(실제 대용량 프롬프트+tool sleep) →
  전체 스윕은 길다(≈36런). **tmux 실행 필수 확인.**

### D-2. ⏭ 이어서 실행할 스윕 (tmux에서)
사용자가 Claude를 tmux에 넣고 이어갈 예정. 백엔드/프록시는 이미 up이므로 아래로 스윕 시작:
```
cd /home/yunuikang/yunuikang_work/distserving
S=/home/yunuikang/yunuikang_work/scratch
T=$S/traces/tracelab_fit32k.jsonl
# default → tr 순차 (각 점 3회, 64프로그램, C=2..48). run_trace_sweep이 프록시를 해당 router로 재기동함.
NPROG=64 REPEAT=3 TAG=tracelab bash scripts/run_trace_sweep_yunuikang.sh default $S/hetero_homo_tracelab_default.jsonl $T 2 4 8 16 32 48
NPROG=64 REPEAT=3 TAG=tracelab bash scripts/run_trace_sweep_yunuikang.sh tr      $S/hetero_homo_tracelab_tr.jsonl      $T 2 4 8 16 32 48
```
- 주의: 저부하 점(c=2,4)은 프로그램 직렬화로 느릴 수 있음 — 필요시 `2 4` 빼고 `8 16 32 48`부터,
  또는 `NPROG=48`로 시간 단축. tool cap은 fit32k에 이미 30s 적용됨.
- 스윕 후: `plot_results_yunuikang.py`로 tr vs default 그래프
  (`figures/hetero_homo_tracelab_{throughput,hitrate,p95}.png`) — plot 스크립트 입력포맷 확인 필요.

### D-3. ⏸ 일시 중단 (사용자 요청: Claude를 tmux에 넣기 위해 커밋/로그 후 정지)
- 서버(tmux `phaseD` 2백엔드 + 프록시)는 **켜둔 채로** 멈춤 → 재개 시 바로 D-2 스윕 실행 가능.
  (GPU 점유 중. 오래 방치하려면 `tmux kill-session -t phaseD; pkill -f bin/thunderagent`로 정리.)

### D-4. ▶ 스윕 실행 재개 (tmux 안, unattended) — default 완료 (2026-07-03)
- 설정: `NPROG=64 REPEAT=3 TAG=tracelab`, trace=`tracelab_fit32k.jsonl`(982세션), C=2 4 8 16 32 48.
- **default 스윕 완료**: 18런(6×3) 전부 성공, 실질 에러 없음(HF 토큰 경고만). 결과 파일:
  `scratch/hetero_homo_tracelab_default.jsonl`.

**default 결과 (3회 평균)**:
| C | thru(p/s) | p95(s) | KV hit | completed(/64) |
|---|-----------|--------|--------|----------------|
| 2  | 0.048 | 110.0 | **0.823** | 62 |
| 4  | 0.093 | 112.9 | 0.611 | 62 |
| 8  | 0.120 | 153.4 | 0.210 | 62 |
| 16 | 0.107 | 289.1 | 0.047 | 62 |
| 32 | 0.108 | 418.2 | 0.032 | 61 |
| 48 | 0.102 | 480.7 | 0.026 | 62 |

- **관찰**: 실제 대용량 컨텍스트(median 18k) 워크로드라 4090 2장(KV 각 43,888토큰)엔 동시 ~2–4개만
  적재 → **c가 오르면 hit rate 급락(0.82→0.026), p95 폭증(110→481s)**. throughput은 c=8(0.12p/s)에서
  천장 후 정체. §9 합성 스래싱과 같은 패턴을 **실제 trace에서 재현**(default는 용량 무시로 붕괴).
- tr 스윕은 이어서 실행 → 완료 후 비교표 추가 예정.

### D-5. 🔻 세션 crash 로 tr 스윕 중단 → 재기동 (2026-07-03)
- **사건**: tr 스윕 실행 중 세션(tmux/SSH)이 죽어 tmux `phaseD`·vLLM 2백엔드·프록시·tr 드라이버가
  전부 종료. `hetero_homo_tracelab_tr.jsonl`은 부분(1,332 bytes)만 기록됨.
- **원인 파악 (OOM 여부)**: `dmesg`·`journalctl -k` **접근 불가**(sudo 없음, dmesg 0 라인) → 커널 OOM
  흔적 직접 확인 불가. 그러나 **호스트 RAM 503 GiB 중 471 GiB 여유**(free -h)로 호스트 메모리 OOM
  가능성 낮음. GPU도 default 스윕(동일 설정) 18런 내내 정상이었음 → **GPU OOM보다 세션(SSH/tmux)
  종료로 자식 프로세스가 함께 죽은 것**으로 추정. **확정적 OOM 근거 없음.**
- **조치**: OOM 근거가 없으므로 **NPROG=64 유지**(default와 동일 파라미터 → tr vs default 비교 일관성).
  default 결과(18/18, 커밋 `02b7f6e`)는 보존, 손대지 않음.
- **재기동 절차**(전부 tmux `phaseD` 안):
  1. 백엔드 2개 새 창(gpu0:8000, gpu1:8001)에 env 우회 + `--host 0.0.0.0` 적용해 재기동
     (`_serve_vllm_yunuikang.sh`에 `--host 0.0.0.0` 추가).
  2. 프록시(:9000, 2백엔드) 재기동.
  3. 부분 파일 `hetero_homo_tracelab_tr.jsonl`·`sweep_tr.out` 삭제(클린 데이터).
  4. tr 스윕 처음부터: C=2 4 8 16 32 48, REPEAT=3, NPROG=64.

### D-6. ✅ tr 스윕 완료 + tr vs default 비교 (2026-07-04)
- 재기동 후 tr 스윕 18런(6×3) 전부 성공, 실질 에러 없음. 결과: `scratch/hetero_homo_tracelab_tr.jsonl`.
- 서버는 계속 유지(tmux `phaseD` 2백엔드 + 프록시). 백엔드 KV 각 43,888토큰 동일.

**tr vs default (3회 평균, tracelab fit32k, 2×4090):**
| C | thru(p/s) def/tr | p95(s) def/tr | **KV hit def/tr** |
|---|------------------|---------------|-------------------|
| 2  | 0.048 / 0.048 | 110 / 110 | 0.823 / 0.823 |
| 4  | 0.093 / 0.084 | 113 / 132 | 0.611 / **0.786** |
| 8  | 0.120 / 0.078 | 153 / 184 | 0.210 / **0.800** |
| 16 | 0.107 / 0.073 | 289 / 595 | 0.047 / **0.799** (17×) |
| 32 | 0.108 / 0.069 | 418 / 660 | 0.032 / **0.774** (24×) |
| 48 | 0.102 / 0.067 | 481 / 727 | 0.026 / **0.772** (30×) |

**해석 (실제 데이터 — 합성 §9와 다른 뉘앙스, 중요):**
- **KV hit rate: tr이 압도적 유지**. 부하가 올라도 tr은 ~0.77–0.80을 지키는 반면 default는
  0.82→**0.026으로 붕괴**(c=48에서 tr이 **30배**). → ThunderAgent 핵심 주장(program-aware
  capacity scheduling이 KV 스래싱을 막는다)을 **실제 TraceLab 데이터에서 재현**. ✅
- **그러나 throughput·p95는 tr이 오히려 불리**(c=48: thru 0.067 vs 0.102, p95 727s vs 481s).
  합성 §9(tr이 thru +57%·p95 낮음)와 **정반대**. 원인 추정: 실제 프로그램이 매우 큼(input median
  18k, 최대 32k)이라 4090 KV(43,888토큰)에 **동시 ~2개**만 적재 → tr은 용량 초과분을 적극
  pause/queue하여 **캐시는 보존하나 동시 실행 병렬성이 급감**(closed-loop이라 paused 프로그램이 slot
  점유) → throughput 제한·대기지연↑. default는 캐시를 갈아엎으며(reprefill 폭증) 병렬성을 유지해
  **wall-clock throughput은 더 높음**.
- **시사점**: 프로그램 크기가 KV 용량에 육박하는 하드웨어에서는 tr의 캐시 보존 이득이
  throughput/latency로 **전환되지 않음**. 이는 KV 용량이 결속 제약임을 보여주며 → **용량 비례
  라우팅·이종 GPU(더 큰 KV) 필요성**의 근거를 오히려 강화(§12 가설과 연결). *한계*: 각 점 3회지만
  tr은 반복 간 hit 편차가 있음(스케줄러 pause 타이밍 의존); NPROG=64 고정 offered load.

### D-7. Phase D(TraceLab) AC 상태
- ✅ tr vs default throughput/KV hit/p95 곡선 확보(데이터셋=TraceLab). 결과 JSONL 2개 저장.
- ⏳ 그래프(`figures/hetero_homo_tracelab_*.png`)는 다음 단계에서 `plot_results_yunuikang.py`로 생성 예정.
- 기대치("중고부하 tr 우위") 대비: **hit rate에서는 확실한 tr 우위, throughput/p95에서는 아님**(위 해석).

