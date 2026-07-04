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

### D-8. 스코프 변경 + D(TraceLab) 마무리 (2026-07-04)
- **스코프 변경(사용자 지시)**: Phase C(SWE-bench 녹화)·D(SWE-bench)는 **보류(다음 미팅 이후)**.
  이번 실행 순서 = **D(TraceLab) 마무리 → E(cross-node homo 풀 스윕) → F(homo-hetero, goguma6 5090)**.
  - 계획서 `../EXPERIMENT_PLAN_hetero_yunuikang.md` 갱신함(Phase C·D 헤더에 보류 표기, 실행순서 갱신).
    ⚠️ 단 계획서는 **git repo 밖**(상위 `yunuikang_work`, 비-git)이라 **커밋 불가** — 디스크 저장으로만 반영.
- **D(TraceLab) 결과 확인**: default/tr 각 **18런**(C=2·4·8·16·32·48 × 3회), concurrency 전 구간 커버.
  런당 실패 ~2/64 프로그램(경미, completed 62/64) — offered load 충분.
- **그래프 생성**(3회 평균 집계 후): `plot_results_yunuikang.py`로
  `figures/hetero_homo_tracelab_{throughput,p95_latency,hit_rate}.png` 3종.
  - hit_rate 그래프가 핵심: **tr ~0.8 평탄 유지 vs default 급락(0.82→0.026)**.
  - 집계 입력: `scratch/agg_tracelab_{tr,default}.jsonl`.
- **→ Phase D(TraceLab) 완료.** (SWE-bench는 보류.) 다음: Phase E(cross-node homo).

---

## Phase E — cross-node homo (mango1 + mango3, 둘 다 4090) — 시작 (2026-07-04)

- **목적**: GPU 이종 전에 **네트워크 축만** 격리 검증. GPU 동일(4090+4090), 서버만 분리.
- **노드 IP**(사용자 제공): mango1=`143.248.53.25`, mango3=`143.248.53.58`, goguma6=`143.248.53.112`.
- **접근 방식 (b)**: mango1→mango3 SSH 키 세팅 안 함. **사용자가 mango3에 직접 SSH해 vLLM 기동**,
  Claude는 mango3 실행 명령을 출력 + mango1 쪽(프록시·스윕·RTT)만 담당.
- **토폴로지**: 노드당 vLLM 1개 — mango1:8000(GPU0, 이미 기동 중 재사용) + mango3:8000.
  프록시(mango1:9000) `--backends http://143.248.53.25:8000,http://143.248.53.58:8000`.

### E-0. mango3 실행 명령 출력 → 사용자 실행 대기
- mango3에 낸 명령: env 우회 4줄 + `vllm serve --host 0.0.0.0 --port 8000 --max-model-len 32768
  --gpu-memory-utilization 0.92` (아래 대화에 전문). **전제**: mango3에 `/home` 공유(venv/repo/모델
  동일 경로) + 드라이버 CUDA13(≥580). 사용자가 `/home` 공유 여부 확인해서 알려주기로 함.
- **대기 항목(사용자 보고)**: (1) mango3 드라이버/CUDA 버전, (2) `/home` 공유 여부(venv 보임?),
  (3) 기동 후 `GPU KV cache size: N tokens` 로그 + `/health` OK.

### E-drop. 🔸 Phase E 제외 (2026-07-04, 스코프 재변경)
- 사용자 지시로 **Phase E(cross-node homo)도 이번엔 제외(보류, 다음 미팅 이후)**. mango3 기동은 진행 안 함.
- 계획서 순서 재갱신: **D(TraceLab) 완료 → F(goguma6 5090)**. (계획서 파일 수정함, git 밖이라 커밋 불가.)

---

## Phase F — homo-hetero (mango1 4090 + goguma6 5090, 실제) — 시작 (2026-07-04)

- **목적**: 바뀌는 변수는 **GPU 용량뿐**(데이터=합성, homo-homo와 동일). 4090+5090 이종에서 tr의
  절대-토큰 균형 배분이 작은 4090을 먼저 포화시키는지(§12 H1) 정량 확인.
- **노드 IP**: mango1=`143.248.53.25`(4090), goguma6=`143.248.53.112`(5090, Blackwell).
- **접근 (b)**: goguma6는 **/home 비공유 + SSH 키 없음** → 사용자가 goguma6에 직접 붙어 세팅/기동.
  Claude는 goguma6 셋업 스크립트 제공 + mango1 쪽(백엔드·프록시·스윕) 담당.
- **토폴로지**: mango1:8000(4090, `--host 0.0.0.0`, 이미 기동 중) + goguma6:8000(5090).
  프록시(mango1:9000) `--backends http://143.248.53.25:8000,http://143.248.53.112:8000`.

### F-0. goguma6 셋업 스크립트 제공 → 사용자 실행 대기
- **신규 파일**: `scripts/setup_goguma6_yunuikang.sh` — /home 비공유 별도 노드용 from-scratch:
  uv 설치 → standalone Python 3.12(헤더 포함) → venv → `uv pip install vllm --torch-backend=auto`
  → env 우회(CPATH=sysconfig include, FLASH_ATTN, flashinfer sampler off) → 모델 다운로드 →
  `vllm serve --host 0.0.0.0 --port 8000 --max-model-len 32768 --gpu-memory-utilization 0.92`.
- **Blackwell(sm_120) 리스크**: vLLM 0.24.0/torch cu13이 5090 커널을 포함해야 함. 안 뜨면 삽질 금지 —
  스크립트 하단 "IF IT FAILS" grep 결과를 받아 우회(다른 attention backend / 최신 vLLM 등) 정리 후 멈춤.
- **대기 항목(사용자 보고)**: goguma6 nvidia-smi CUDA 버전, torch/vllm import 성공 여부,
  기동 시 `GPU KV cache size: N tokens`(5090 실측 — §10-4 추정 ~97k 검증), `/health` OK.

### F-1. goguma6(5090) 기동 성공 + cross-node 검증 + 스모크 (2026-07-04)
- **goguma6 vLLM 정상 기동**(사용자 실행): `/health` OK. **GPU KV cache size = 89,040 tokens
  (Available KV 12.23 GiB)**. Blackwell(sm_120)에서 vLLM 0.24.0/cu13 스택이 **문제없이 동작**
  (셋업 스크립트 `--torch-backend=auto`로 자동 해결, 별도 우회 불필요).
- **5090 KV 실측 vs §10-4 추정**: 실측 **89,040** vs 추정 ~97,481 → 근접. **4090(43,888) 대비 2.03×**
  (§10-5 추정 ~2.2× 근접). → 이종 용량비 **5090:4090 ≈ 2:1** 확정(실측).
- **cross-node 검증(mango1에서)**: goguma6:8000·mango1:8000 둘 다 IP로 도달 OK, 동일 모델
  `Qwen/Qwen3-8B`, **RTT 0.196ms**(동일 LAN, 오버헤드 무시가능).
- **프록시**(mango1:9000) `--backends http://143.248.53.25:8000,http://143.248.53.112:8000` 기동.
- **오케스트레이터**(신규 `scripts/run_hetero_sweep_yunuikang.py`): 실행 중 백엔드별
  `kv_cache_usage_perc`·프록시 `paused` 샘플링 + 백엔드별 split/hit/reprefill 집계.
- **스모크(tr, c=8, 16프로그램)** — **가설 즉시 확인**:
  | GPU | KV usage peak | hit rate | pause | queries(재프리필) |
  |-----|---------------|----------|-------|-------------------|
  | **4090** | **0.98 (포화)** | 0.19 | **4** | 1.18M |
  | **5090** | 0.80 | 0.63 | 0 | 0.42M |
  → 작은 **4090이 먼저 KV 포화·스래싱(hit↓)·pause**, 5090은 여유. **§12 H1 실측 확인.**
- **전체 스윕 실행 중**(background): tr→default, C=8·16·24·32·48 × 3회(30런), §9 합성 workload
  (ctx=3000, turns=3, sleep=0.5, maxtok=96, nprog=48). 예상 ~45–60분. 출력: `homo_hetero_{tr,default}.jsonl`.

### F-2. ✅ Phase F 스윕 완료 + 결과·해석 (2026-07-04)
- 두 스윕 각 **15런(5×3) 완료, 전 런 48/48 성공**. 출력: `scratch/homo_hetero_{tr,default}.jsonl`.

**전역 (tr vs default, 3회 평균):**
| C | thru tr/def | 전역 hit tr/def |
|---|-------------|-----------------|
| 8  | 0.67 / 0.62 | 0.56 / 0.23 |
| 16 | 0.64 / 0.34 | 0.67 / 0.03 |
| 24 | 0.63 / 0.32 | 0.67 / 0.02 |
| 32 | 0.64 / 0.35 | 0.67 / 0.03 |
| 48 | 0.64 / 0.32 | 0.67 / 0.02 |
→ **tr이 고부하에서 throughput ~2배(0.64 vs 0.32), 전역 hit 0.67 vs 0.02.** (§9 homo 2×4090 tr~0.49
대비 hetero+5090에서 tr~0.64, +31% — 큰 GPU 추가 효과.)

**전역 p95 latency (3회 평균, 사후 집계 — 각 런 `latency_p95_s` 이미 기록됨, 재실행 불필요):**
| C | p95 tr | p95 def | tr/def |
|---|--------|---------|--------|
| 8  | 20.6s | 25.7s | 0.80× |
| 16 | 34.9s | 52.2s | 0.67× |
| 32 | 55.1s | 99.0s | 0.56× |
| 48 | 70.2s | 149.0s | **0.47×** |
→ **F에서는 tr이 p95도 우세**(부하 오를수록 격차 확대, c48에서 tr이 default의 절반 이하 = 2.1배 빠름).
**D(실데이터 2×4090)에서 tr이 p95 열세(727 vs 481s)였던 것과 정반대** — 큰 5090이 붙으니 tr의 pause가
throughput뿐 아니라 지연에서도 이득으로 전환. 그래프 `figures/homo_hetero_p95.png`(+ 덱 슬라이드9 표).

**백엔드별 (핵심 — 4090 vs 5090):**
| | tr 4090 | tr 5090 | default 4090 | default 5090 |
|---|---------|---------|--------------|--------------|
| KV usage peak (c≥16) | 0.99 | 0.96 | 0.99 | 0.96 |
| hit rate (c≥16) | **0.67** | **0.67** | **0.02** | **0.02–0.05** |
| hit rate (c=8) | 0.48 | 0.64 | **0.08** | 0.67 |
| 재프리필 queries(M, c≥16) | 0.80 | 1.29 | **9.2** | 2.2 |

**해석 (가설 검증 — H1은 예상과 다르게 나옴, 정직하게 기록):**
- **default(naive)가 작은 4090을 파국적으로 혹사**: c=8에서 이미 4090 hit **0.08**(스래싱)인데 5090은 0.67
  (여유). 고부하에선 4090 재프리필이 5090의 **~4배**(9.2M vs 2.2M). → "작은 GPU가 먼저·더 심하게
  스래싱"하는 현상은 **default에서 발생**.
- **tr은 두 GPU를 균형 유지**: 4090·5090 hit rate가 **둘 다 ~0.67로 수렴**(발산 안 함). 오히려 tr은
  **큰 5090에 더 많이 라우팅**(queries 4090:5090 ≈ 0.8M:1.3M ≈ 1:1.6). pause도 저부하선 4090,
  고부하선 5090에 소수 분산.
- **⚠️ §12 H1 기각/수정**: H1은 "tr의 절대-토큰 균형 배분이 작은 4090을 먼저 포화시킨다"였으나,
  실측상 tr의 4090·5090 hit rate가 **유사(≈0.67)** → §12-2에 미리 정한 **반증 조건**("tr에서 두 GPU
  hit가 비슷하면 H1 기각/수정")에 해당. **tr은 H1이 우려한 소형-GPU 혹사를 하지 않는다.** 소형-GPU
  혹사 병리는 **default의 문제**.
- **수정된 연구 방향(시사점)**: tr split ≈ 1:1.6 vs 실제 용량비 1:2.03 → tr이 **큰 5090을 완전히는
  활용 못 함**(throughput가 5090 추가 용량(+51%)만큼 오르지 않고 +31%에 그침). 즉 다음 과제는
  "tr이 소형 GPU를 혹사한다"를 고치는 게 아니라 **대형 GPU의 여유를 더 적극 활용(용량 비례 배분으로
  throughput 상단 끌어올리기)**. (약한 소형-GPU-우선 효과는 tr c=8에서만: 4090 hit 0.48 vs 5090 0.64.)

**그래프**(`figures/`, 신규 `scripts/plot_hetero_yunuikang.py`):
- `homo_hetero_perbackend_hitrate.png` — **핵심**: tr 4090·5090 둘 다 ~0.67 vs default 4090 즉시 붕괴.
- `homo_hetero_throughput.png` — tr ~0.64 평탄 vs default 0.62→0.32 붕괴.
- `homo_hetero_perbackend_reprefill.png` — default 4090 재프리필 폭증(9M).
- `homo_hetero_perbackend_kv_usage.png` — 백엔드별 peak KV.

**한계**: (1) 각 점 3회(반복 간 편차 존재, 특히 tr pause 타이밍). (2) 합성 §9 workload(실제 분포와 다름).
(3) split을 queries(재프리필 포함)로 근사 — 순수 라우팅 프로그램 수와는 다름.

### F-3. Phase F AC 상태
- ✅ 백엔드별 KV사용률·split·pause·hit rate 수집(양쪽 GPU 따로). tr/default 비교 곡선·그래프 확보.
- ✅ 양쪽 실제 KV 풀 기록: 4090=43,888 / 5090=89,040 tokens (2.03×).
- ✅ 가설 검증: H1은 반증(수정) — 소형-GPU 혹사는 default 병리, tr은 균형 유지·대형 GPU 과소활용.
  → **용량 비례 라우팅의 근거는 "tr의 대형 GPU 활용 개선" 방향으로 재정의.**
- **→ Phase F 완료.** (이번 스코프 D(TraceLab)+F 종료. C·D(SWE)·E는 보류.)

---

## Phase D-char — TraceLab 워크로드 characterization (§10 방식, 미팅덱용) (2026-07-04)

> homo-homo §10과 동일 방식으로 TraceLab 실제 워크로드 특성을 뽑아 D 결과의 **원인**을 설명.
> 각 항목에 homo-homo 합성(§10) 비교값 병기. 그래프: `figures/char_tracelab_*.png`.

### 재료·방법
- 정적(서버 불필요): `tracelab_fit32k.jsonl`(982세션/6,107턴)에서 토큰·tool·KV 분포.
- 프로파일(c=1 측정): 첫 25세션 zero-tool 복사본(`tracelab_char25_notool.jsonl`)을 **4090(mango1:8000)
  직접, `--stream`** 로 c=1 재생 → per-turn TTFT(prefill)/decode 측정(`char_tracelab_c1.trace.jsonl`,
  24/25 완료, 1건 400=누적 컨텍스트 초과). §10처럼 vLLM이 요청별 prefill/decode 미제공 → 클라이언트
  스트리밍 TTFT로 근사. **lifetime = 측정 compute(turn_latency) + 원본 trace의 tool_duration 재합산**
  (profiling 시간 단축 위해 tool sleep은 측정 중 제거, tool은 분석에서 다시 더함 — 방식 명시).

### 결과 (TraceLab vs homo-homo 합성 §10)
| 특성 | TraceLab (실측) | homo-homo 합성 §10 |
|------|-----------------|--------------------|
| input tokens/turn | median **18,275**, p95 29,212 | ~14,558 (균일) |
| output tokens/turn | median **144**, p95 1,387, max 14,641 | ~28.6 (거의 고정) |
| tool time/turn | median 0.047s, **p95 30s**(cap) | 0.4s (설계값) |
| 프로그램 peak KV | median **2.87 GiB**, p95 4.35, max 4.50 | ~2.01 GiB |
| 프로그램 lifetime(c=1) | median **34.6s**, p95 150, max 173 | ~63.8s (c=8) |
| turn0 prefill(cold) | **1.89s** | 1.82s |
| warm prefill(turn>0) | 0.40s | 0.13s |
| decode(median) | 1.16s | ~0.5s |

### 해석 (D 결과와의 인과)
- **prefill-heavy**: 입력 18k ≫ 출력 144(median). 비용은 prefill/KV에 집중 → KV locality가 결정적.
  (단 출력 꼬리가 큼: max 14,641 토큰 → 일부 turn은 decode가 지배.)
- **KV 그래프가 D 결과의 원인**: 프로그램 1개가 **2.87 GiB(median)** → **4090 풀(6.03 GiB)에 ~2.1개**,
  5090(12.23)에 ~4.3개만 적재. → §D-6에서 tr이 pause로 병렬성을 희생한 이유(프로그램이 KV에 육박)를
  워크로드 수준에서 정량 설명. 합성(2.01 GiB)보다 크고 **가변적**이라 실제 KV 압박이 더 불균일.
- **turn0만 cold prefill(1.89s), 이후 warm(0.40s)**: 세션 내 prefix 재사용(KV locality) 실측 —
  homo §10과 동일 패턴(warm이 §10 0.13s보다 큰 건 실제 turn당 신규 토큰이 더 많기 때문).

### 산출물
- 그래프: `figures/char_tracelab_{tokens,kv,lifetime,turn_breakdown}.png`
- 스크립트: `scripts/plot_char_tracelab_yunuikang.py`
- 원시: `scratch/char_tracelab_c1.trace.jsonl`(per-turn), `scratch/char_tracelab_c1.summary.jsonl`

---

## 미팅 덱 빌드 (2026-07-04)
- **`scripts/make_deck_hetero_yunuikang.py`** (python-pptx 1.0.2, 기존 make_deck 스타일 재사용) →
  **`meeting_hetero_yunuikang.pptx` (14슬라이드, 507KB, figures/ 실제 PNG 임베드)**.
- 구성: 타이틀 / 배경·목표(2×2) / 방법(HW·KV풀) / **워크로드 특성 3장**(tokens·lifetime+breakdown·KV)
  / **D 결과 2장**(hit rate 압승 → throughput·p95 반전) / **F 결과 3장**(전역 2배·백엔드별 핵심·H1 반증)
  / 종합 비교표(homo §9 +57% ↔ D −34% ↔ F +100%) / 시사점(용량 비례 라우팅) / 한계·TODO.
- 톤: 워크로드 특성(4~6) → D 결과(7~8) 인과 연결, homo-homo 비교(12)로 "언제 tr이 이기고 지는지".
- 검증: 14슬라이드, overflow 0, 참조 PNG 9종 존재 확인. (렌더러(libreoffice) 부재로 시각 최종확인은
  사용자 열람 필요.)
- **발표자 노트 추가**(14슬라이드 전부): 청중=지도교수 대상 구어체 대본. 각 노트 = (보여주는 것 →
  왜 중요/핵심 숫자 → so-what → 예상질문 대비). 특히 D②(throughput 반전)·F③(H1 반증)에 정직 포인트와
  예상질문 답변 포함. 스크립트 `make_deck_hetero_yunuikang.py`의 `NOTES` 리스트로 재현 가능.
- **결과 슬라이드 표 확장**: 슬7·8(D)에 C=2·4·8·16·32·48 전부, 슬9(F)에 C=8·16·24·32·48 통합표
  (thru·hit·p95). **F p95 사후집계**(각 런 `latency_p95_s` 기록됨): c48 tr 70.2 vs def 149.0s(0.47×) —
  F에선 tr이 p95도 우세(D와 반대). 그래프 `homo_hetero_p95.png`·전역 `homo_hetero_hitrate.png` 추가.

---

## Phase G — hetero-hetero (실제 TraceLab × 4090+5090) — 스윕 실행 중 (2026-07-04)

- **목표**: 2×2 매트릭스 마지막 칸. 데이터=실제 TraceLab fit32k(D와 동일), GPU=4090+5090(F와 동일).
  핵심 질문: D(2×4090)에서 tr이 throughput 잃은 원인(프로그램이 4090에 ~2개)을, 큰 5090(89,040토큰,
  ~4개) 추가로 **실데이터에서 tr이 회복하는가**.
- **인프라 재사용**: mango1 4090:8000 + goguma6 5090:8000 (둘 다 up 확인, 재기동 불필요).
  프록시 `--backends http://143.248.53.25:8000,http://143.248.53.112:8000`. KV 4090=43,888 / 5090=89,040.
- **오케스트레이터 확장**: `run_hetero_sweep_yunuikang.py`에 `--trace` 부하원 옵션 추가
  (trace_replay_driver 사용, 백엔드별 kv_usage·split·hit·reprefill·pause 샘플링은 F와 동일).
- **스윕**: workload=`tracelab_fit32k.jsonl`(D와 동일). router tr→default, **C=2·4·8·16·32·48(D와 동일 축),
  3회, NPROG=64** = 36런. 출력: `scratch/hetero_hetero_{tr,default}.jsonl`.
- **예상 ~7–9시간**(D 실측 8.75h 기준; decode·tool sleep 지배적). background 실행, 완료 시 분석.
- 시작 검증: 프록시 tr 재기동 OK, trace_replay_driver 구동 확인(--trace 경로 정상). ⏳ 진행 중.

### G-1. ✅ Phase G 완료 + 세 방향 비교 (2026-07-04)
- 두 스윕 각 **18런(6×3) 완료**, 전 런 ~61-62/64 성공. 실제 소요는 예상(8h)보다 빠름(5090이 스래싱을
  줄여 완료 가속). 출력: `scratch/hetero_hetero_{tr,default}.jsonl`.

**전역 (3회 평균):**
| C | thru tr/def | p95 tr/def | 전역 hit tr/def |
|---|-------------|------------|-----------------|
| 8  | 0.126/0.154 | 141/125 | 0.774/0.386 |
| 16 | 0.116/0.143 | 358/230 | 0.742/0.073 |
| 32 | 0.116/0.132 | 429/339 | 0.733/0.030 |
| 48 | 0.115/0.125 | 438/368 | 0.679/**0.033** |

**백엔드별 hit (4090/5090) + tr split(q4:q5):**
| C | tr 4090/5090 | def 4090/5090 | tr split |
|---|--------------|---------------|----------|
| 8  | 0.81/0.73 | **0.36**/0.67 | 1:0.94 |
| 16 | 0.74/0.70 | **0.06**/0.16 | 1:1.49 |
| 32 | 0.80/0.67 | **0.02**/0.08 | 1:1.13 |
| 48 | 0.69/0.67 | **0.03**/0.06 | 1:0.94 |

**해석 — 세 방향 (계획서 분석 항목):**
1. **vs D(2×4090): tr throughput 회복하는가? → YES(부분).** tr throughput **G/D = 1.60~1.72×**
   (D tr 0.067~0.078 → G tr 0.115~0.126). 큰 5090이 붙자 D에서 잃었던 throughput을 대폭 회복.
   default와의 격차도 축소: D는 tr/def≈0.66(c48), **G는 0.92(c48)** — 적자 34%→8%로 줄었으나
   **완전 역전은 아님**(default가 여전히 근소 우위). p95는 tr이 여전히 열세(c48 438 vs 368) —
   D 패턴 지속(F 합성과 다름). **hit rate는 tr 압승 유지**(0.68~0.83 vs default 0.033).
2. **vs F(합성 이종): 백엔드별 패턴 유지되는가? → YES(대부분).** default가 **작은 4090을 가장 먼저·심하게
   혹사**(c8 4090 hit 0.36 vs 5090 0.67; 고부하 4090 0.02~0.06 < 5090 0.06~0.16) — F 패턴 실데이터 확인.
   tr은 4090·5090 균형(둘 다 ~0.67~0.87). **단 tr의 5090-편향 split은 실데이터에선 약함**: F는 1:1.6,
   G는 **~1:1(0.75~1.49, noisy)** — 실제 trace에선 tr이 5090에 더 보내는 경향이 뚜렷하지 않음.
3. **5090 활용·용량 비례 라우팅 필요성 → 재확인·강화.** tr split ~1:1 ≪ 용량비 1:2.03 → **실데이터에서
   5090 과소활용이 F보다 더 큼**. 그럼에도 throughput은 +72%(용량 +51% 대비 초선형) 회복 — 5090이
   스래싱을 덜 겪어 균등 분배로도 총량이 늘었기 때문. **→ split을 5090으로 더 밀면(용량 비례) default를
   넘어설 여지**가 실데이터로 재확인.

**그래프**(`figures/hetero_hetero_*.png`): throughput, p95, hitrate(전역), perbackend_hitrate(핵심:
tr 균형 vs default 4090 최악 붕괴), perbackend_reprefill, perbackend_kv_usage.

### G-2. 2×2 매트릭스 완성 — 종합
| | 2×4090 (homo GPU) | 4090+5090 (hetero GPU) |
|---|---|---|
| **합성 데이터** | §9: tr thru **+57%**, hit 압승 | F: tr thru **+100%**, hit 압승, p95도 우위 |
| **실제 TraceLab** | D: tr thru **−34%**, hit 압승(30×) | G: tr thru **−8%**(D서 회복), hit 압승, p95 열세 |
- **일관**: tr의 KV hit(스래싱 억제)은 4칸 모두 압승. default는 어디서나 작은 GPU부터 붕괴.
- **가변(throughput)**: 프로그램이 KV에 육박하는 실데이터에선 tr이 pause로 병렬성을 희생 → default에
  근소 뒤짐. 큰 GPU(5090)를 붙이면 그 적자가 34%→8%로 축소(G). **tr 이득은 프로그램/KV 비율·GPU
  용량에 좌우**된다는 결론을 실데이터 이종으로 최종 확인.
- **한계**: 각 점 3회(편차 있음), split=queries 근사, fit32k 짧은세션 편향(동일).
- **→ Phase G 완료. 이번 스코프의 2×2 4칸 모두 채움**(C·D-SWE·E는 보류 유지).

