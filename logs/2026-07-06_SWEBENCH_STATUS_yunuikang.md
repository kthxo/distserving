# 실험 D (SWE-bench) — 스코핑 + 🛑 Docker 블로커 (2026-07-06)

> 작성: 강윤의 · 브랜치 `yunuikang/thunderagent` · 2026-07-06
> 목적: 논문 SWE-Agent/OpenHands 워크로드와 정렬해 **두 번째 독립 실제 워크로드**로 결론 검증.
> 상태: **환경 블로커로 실행 불가 — 사용자/관리자 결정 대기.** 아래는 조사 결과 + 블로커 + 옵션.

---

## 1. 하려던 것 (워크플로 — reproduce 스크립트 기반, 우리 HW로 축소)

`examples/inference/mini-swe-agent/scripts/reproduce/reproduce_glm4.6.sh`가 정본. 그대로 축소:
1. vLLM serve **Qwen/Qwen3-8B**(우리 다른 실험과 동일 모델), 여유 4090 1장, `--max-model-len 32768`.
2. ThunderAgent 프록시 `--router default --metrics --profile --profile-dir scratch/rec_swebench`
   (녹화는 스케줄링 영향 최소화 위해 default 권장).
3. `mini-extra swebench --subset lite --split test --workers W --output scratch/swebench_out`
   → 요청이 프록시(:8000/:9000) 통과, `extra_body.program_id` 부착.
4. 녹화된 `step_profiles.csv` → 공통 스키마 JSONL로 정규화(신규 `prep_swebench_trace_yunuikang.py`).
5. 정규화 trace로 `trace_replay_driver`를 tr/default 스윕(Phase D-SWE) → 2×2를 SWE 데이터로 재현.

**program_id 주입 확인**(코드): `src/minisweagent/models/vllm_model.py:130-139` —
`extra_body = {"program_id": str(job_id or n_calls+1), ...}`, `base_url`·`model_name` config 가능.
→ 우리 프록시로 향하게 하고 program 단위 추적이 되는 구조 확인함.

---

## 2. 🛑 블로커 — 컨테이너 런타임 전무 (SWE-bench 실행 불가)

SWE-bench Lite는 각 인스턴스를 **사전빌드 Docker 이미지**(`docker.io/swebench/sweb.eval.x86_64.<id>:latest`,
`swebench.py:98-116`) 안에서 실행한다(=/testbed에 해당 repo가 정확한 커밋·의존성으로 준비됨). 이게 있어야
에이전트의 bash 도구 실행이 현실적으로 동작.

우리 환경 실측:
| 런타임 | 상태 |
|--------|------|
| docker | 설치됨(v29.6.1)이나 **권한 없음**(docker.sock permission denied, **docker 그룹 미소속**) |
| singularity / apptainer | **없음** |
| podman | **없음** |
| bubblewrap(bwrap) | 있음 — **그러나 swebench 이미지를 못 받음**(Docker 레지스트리 이미지 필요) → 무용 |
| passwordless sudo | **없음** (스스로 docker 그룹 추가 불가) |

- `environment_class`는 docker/singularity/local 지원하나, **local**은 호스트에서 직접 실행 → SWE-bench의
  /testbed(사전빌드 repo 환경)가 없어 태스크가 성립 안 함(에이전트가 flail). → **실질적으로 컨테이너 필수.**
- **결론**: 지금 이 서버(mango1)에서 SWE-bench Lite를 **실행할 수 없다.** GPU/모델 문제 아님, **컨테이너 접근** 문제.

---

## 3. 옵션 (사용자/관리자 결정)

| # | 옵션 | 필요 | 장단 |
|---|------|------|------|
| **A** | 관리자에게 **docker 그룹 추가** 요청 | 관리자(드라이버 복원 선례처럼) | 실제 SWE-bench Lite 실행→**충실한 trace**. 가장 깔끔. |
| **B** | **docker 되는 다른 서버**에서 녹화 | 그 서버 IP·GPU·/home | 실행 가능하나 환경 이동(재현성 관리 필요) |
| **C** | **공개 SWE-agent trajectory 정규화**(TraceLab처럼 replay만) | 데이터셋 조사·다운로드 | Docker 불필요. 단 per-turn 토큰/tool 시간 추출 가능 여부 불확실(조사 필요) |
| **D** | **이번엔 보류**, 다음 미팅 이후(원 계획서 Phase C 보류와 동일) | — | 리스크 회피. TraceLab로 실제 데이터 검증은 이미 확보 |

- ⚠️ 정직: 옵션 C(공개 trace)는 "논문과 동일 하네스로 우리가 직접 돌린" 것이 아니라 남의 로그 재생이라
  충실도가 A/B보다 낮다. 대신 Docker 없이 "SWE-bench 도메인" 비교는 가능.

## 4. Docker 없이 지금 준비 가능한 것 (블로커와 무관, 승인 시 즉시)
- `scripts/prep_swebench_trace_yunuikang.py`(step_profiles.csv → canonical JSONL 정규화기) 선작성.
- mini-swe-agent 설치(`uv pip install -e examples/inference/mini-swe-agent datasets huggingface_hub`) —
  단 **venv 변경**이라 승인 후.
- (옵션 C 택 시) 공개 trajectory 데이터셋 후보 조사.

## 5. 권장
- **옵션 A**(관리자 docker 그룹 추가)를 권장 — driver 복원처럼 한 번 요청으로 해결되고 가장 충실한 결과.
  불가 시 **B**(다른 서버). 둘 다 어려우면 **C 조사** 후 판단, 최후 **D 보류**.

---

## 6. ✅ 결정: 옵션 A (2026-07-06) — 관리자 docker 그룹 요청

사용자가 **옵션 A** 선택. 관리자에게 보낼 요청 메시지(초안):

> **[요청] mango1 서버 docker 그룹 추가 (SWE-bench 평가용)**
>
> 안녕하세요. mango1(143.248.53.25)에서 ThunderAgent 연구용으로 SWE-bench Lite 평가를 돌리려는데,
> 각 태스크가 사전빌드 Docker 이미지(`docker.io/swebench/...`) 안에서 실행돼야 합니다. 현재 계정
> `yunuikang`이 **docker 그룹에 없어** `/var/run/docker.sock` 접근이 거부됩니다(permission denied).
>
> 아래처럼 docker 그룹에 추가 부탁드립니다:
> ```
> sudo usermod -aG docker yunuikang
> ```
> 적용 후 저는 재로그인(또는 `newgrp docker`)하면 됩니다. 확인은 `docker info`가 데몬에 붙으면 완료입니다.
> (지난번 드라이버 595 복원 감사했습니다. 이번엔 컨테이너 접근만 있으면 됩니다.)

**요청 후 대기 항목**(관리자 조치 완료되면 알려주기): `docker info` 성공 여부.
- 해제되면 즉시(승인 하) 진행: (1) mini-swe-agent 설치
  (`uv pip install -e examples/inference/mini-swe-agent datasets huggingface_hub`),
  (2) vLLM(Qwen3-8B, 1×4090) + 프록시 `--profile` 기동,
  (3) `mini-extra swebench --subset lite --workers 4`로 파이프라인 검증 → 확대 녹화,
  (4) `scripts/prep_swebench_trace_yunuikang.py`(✅ 작성·스모크 통과)로 정규화,
  (5) Phase D-SWE 스윕.

## 7. Docker 없이 이미 준비 완료된 것 (2026-07-06)
- ✅ `scripts/prep_swebench_trace_yunuikang.py` — step_profiles.csv → canonical JSONL 정규화기.
  스모크 테스트 통과(turn 0-index 재인덱싱, 마지막 턴 tool=0, `--cap-tool-s`/`--max-input-tokens` 지원,
  schema_ok). mini-swe-agent `vllm_model.py`의 program_id 주입과 정합.
- ✅ 워크플로·program_id 주입 경로·환경 클래스 조사 완료(위 §1·§2).

---

## 8. ✅ Docker 해제 + 파이프라인 검증 통과 (2026-07-07)

- **Docker 사용 가능**: 관리자가 docker 그룹 추가 → `docker info` OK, `/home` 여유 1.4T.
- **설치**: `uv pip install -e examples/inference/mini-swe-agent datasets huggingface_hub` 완료
  (mini-swe-agent 1.14.4, litellm 등). vLLM/ThunderAgent import 정상(무파손).
- **오버라이드 config**: `scripts/swebench_qwen_config_yunuikang.yaml` — swebench.yaml의 model 블록을
  **Qwen/Qwen3-8B + base_url http://localhost:9000/v1(우리 프록시)** 로 교체. `job_id=instance_number`로
  program_id 주입(vllm_model.py:130-139).
- **검증 런**(2 인스턴스, workers=1, step_limit=20, `--router default --profile`):
  - astropy__astropy-12907(5스텝, 57s), astropy__astropy-14182(18스텝, 320s) — 컨테이너 실행·trajectory
    저장·**step_profiles.csv에 program_id 1·2로 per-step 기록** 확인. 파이프라인 end-to-end 입증.
  - **워크로드 실측**: decode/스텝 **median 17.5s(스텝당 973토큰)** → **decode-heavy**(TraceLab prefill-heavy와
    정반대, 흥미로운 대비점). prefill ~0.05s, tool ~0.2-0.6s(입력 2-6k로 작음). SWE 이미지 ~2.7GB/인스턴스.
  - ⚠️ `cached_tokens`/`kv_hit_rate`는 빈칸(응답 usage에 prompt_tokens_details.cached_tokens 미포함) —
    canonical 스키마에선 optional이라 무영향. 필요시 vllm_model/응답 파싱 확인.

## 9. ✅ 확정: 권장 시나리오 = stratified-64 녹화 + 축소 스윕 (2026-07-07)

사용자 검토로 아래를 확정(이전 "head-64" 암묵안은 **폐기** — 대표성 없음).

### 9-1. 규모 (전체 대비)
- Lite test: **레포(종류) 12개, 태스크(=프로그램/세션) 300개**(dev split 23은 별도).
- 녹화 = **64 태스크 = 300의 21.3%**. 스윕 NPROG=64 = **녹화한 64를 그대로 재생**(각 세션 1회, 순환 없음).

### 9-2. 선택 = 레포별 계층적(stratified) 비례 샘플 — **신규 `scripts/sample_swebench_stratified_yunuikang.py`**
- **문제**: 데이터셋이 instance_id 알파벳 정렬 → head-64는 astropy(6)+django(58)만, 10개 레포 누락. 폐기.
- **해법**: 원본 300 레포 분포를 유지하도록 레포별 비례 배분(largest-remainder) + 각 레포 최소 1개 보장,
  레포 내부 시드 고정 랜덤. **결정적**(seed=20260707).
- **실측 배분(64개)** — 12개 레포 전부 커버, 표본%가 원본% 근접:
  | repo | orig% → samp% | | repo | orig% → samp% |
  |---|---|---|---|---|
  | django 21 | 38.0→32.8 | | sphinx 4 | 5.3→6.2 |
  | sympy 15 | 25.7→23.4 | | astropy/requests/pylint/xarray 2씩 | 2.0→3.1 |
  | matplotlib/sklearn 5씩 | 7.7→7.8 | | seaborn/flask 1씩 | 1.3/1.0→1.6 |
  | pytest 4 | 5.7→6.2 | | **분포 L1 drift** | **14.7%p (양호)** |
  - 편차 원인(정직): min-per-repo=1이 작은 레포를 소폭 상향 → django가 38→32.8로 하향. 커버리지 vs
    엄밀비례의 트레이드오프. 순수 비례 원하면 `--min-per-repo 0`(작은 레포 일부 0). 난이도 stratify는
    Lite에 난이도 라벨 없어 미적용(레포가 컨텍스트 특성 좌우 → 레포 stratify로 충분하다는 판단).
- 산출: `scratch/traces/swebench_stratified64.{txt,filter.txt,meta.json}`. 녹화 시 `--filter "$(cat ...filter.txt)"`.

### 9-3. 각 축 축소 근거 (임의 부분 명시)
- **instances 300→64**: 임의 아님 — NPROG=64에 결속(순환 없이 딱 채움, TraceLab 스윕과 일관).
- **step_limit 135→40**: **절반 임의**. 목적이 풀이(pass)가 아니라 서빙 trace라 135 불필요. **왜곡 리스크**:
  per-turn decode 특성은 절단 무관(온전 기록)이나 **프로그램 lifetime(턴수) 상단 꼬리가 clip**됨.
  → **완화: 녹화 후 clip rate(40에서 잘린 태스크 %) 보고**, >30%면 60~80으로 상향. 무왜곡 원하면 135 유지(시간 급증).
- **workers 12**: **경험적 임의**. 녹화 총량엔 무관, 벽시계만 단축 → 8~16 무방(민감도 낮음).

### 9-4. 축소 스윕 조건
- **C = 4·8·16·32** (풀 2·4·8·16·32·48에서 c=2·48 제거, **c=4는 음성대조로 복원** ← 사용자 지적 반영):
  - c=2·48 제거: 저부하(c=2)는 Eq.6 미발동으로 tr≈default(정보 적음), c=48은 c=32에서 포화 확인 시 추세 중복.
  - **c=4 유지**: 저부하 등가(자원 여유→tr=default) **음성 대조**(실험 C의 C0 역할). ← 축소해도 대조점 보존.
  - C가 통제하는 변수 = **offered load(동시성)**: tr/default가 언제 갈라지는지(스래싱 임계) 관측.
- **3회 반복**: 에러바(tr pause 타이밍 반복 편차). 기존 D/F/G와 일관(관례적 최소, 값은 임의).
- **2라우터(tr, default)**: 핵심 통제 비교 = 독립변수. 같은 load·trace에서 스케줄러만 바꿔 tr 효과 격리.

### 9-5. 예상 소요 (검증 실측 기반, ±50% 변동)
- 녹화(64, step_limit 40, workers 12): **~2.5–3.5h**(decode 지배 + docker pull). 스윕(C=4·8·16·32×3×2=24런,
  2×4090): **~4–6h**. **총 ~7–9h GPU**(대부분 unattended, tmux). 손대는 시간 ~0.5일(정규화기·스크립트 완료).

### 9-6. 실행 체크리스트 (승인 후)
1. step_limit 40으로 config 확정(검증용 20 복원). stratified 샘플러 출력(64 id + filter) 생성 완료.
2. tmux `recSWE`: vLLM(Qwen3-8B, 1×4090:8000) + 프록시(:9000 `--router default --profile
   --profile-dir scratch/rec_swebench`) — **현재 기동 상태 재사용 가능**.
3. `mini-extra swebench --subset lite --split test --filter "$(cat swebench_stratified64.filter.txt)"
   --workers 12 --config scripts/swebench_qwen_config_yunuikang.yaml --environment-class docker
   --cleanup-images --output scratch/swebench_out` → 녹화. **첫 ~10인스턴스 후 시간 재보정.**
4. clip rate 확인 → `prep_swebench_trace_yunuikang.py`로 정규화(+ `--max-input-tokens 32768` 옵션 검토).
5. 워크로드 characterization(§D-char 방식, decode-heavy 대비) → Phase D-SWE 스윕(C=4·8·16·32, 2×4090).
6. 서버·컨테이너 정리.

### 9-7. 현재 상태 (2026-07-07)
- vLLM(:8000, GPU0)·프록시(:9000 default `--profile`) **기동 유지 중**(검증 런은 중지·컨테이너 정리 완료).
- **본 녹화 착수는 사용자 최종 승인 대기**(GPU ~7–9h). 샘플러·config·정규화기 모두 준비 완료.
