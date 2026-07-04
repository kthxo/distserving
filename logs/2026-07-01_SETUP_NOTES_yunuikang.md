# ThunderAgent + vLLM 환경 세팅 노트 (강윤의)

> 브랜치: `yunuikang/thunderagent`
> 목표: heterogeneous 에이전트 서빙 연구의 베이스라인인 ThunderAgent를
> 우리 랩 GPU(4× RTX 4090)에서 8B 모델로 일단 돌아가게 만들기 (재현 1차).
> 저장소 위치: `/home/yunuikang/yunuikang_work/distserving`

---

## 1. 최종적으로 성공한 환경 구성

### 하드웨어 / 시스템
- GPU: **RTX 4090 × 4** (각 24 GB), 드라이버 595.71.05 (CUDA 13 세대)
- 시스템 Python 3.12.3, gcc 13.3, **passwordless sudo 없음**
- 시스템 CUDA 툴킷은 12.1 (`/usr/local/cuda` → nvcc 12.1), 단 torch는 cu130

### 소프트웨어 / 버전
| 항목 | 값 |
|------|-----|
| Python venv | `/home/yunuikang/yunuikang_work/.venv` (시스템 python 3.12로 생성) |
| vLLM | **0.24.0** (`uv pip install vllm --torch-backend=auto`) |
| torch | **2.11.0+cu130** |
| ThunderAgent | 소스 editable 설치 (`pip install -e ./distserving`), deps: fastapi/httpx/uvicorn |
| uv 관리 Python(헤더용) | cpython-3.12.13 (`uv python install 3.12`) — 아래 문제 1 참고 |

### 모델 / 포트 구성
| 항목 | 값 |
|------|-----|
| 모델 | `Qwen/Qwen3-8B` (bf16, GPU 0에서 서빙) |
| vLLM 백엔드 | 포트 **8000**, `--max-model-len 32768`, `--gpu-memory-utilization 0.92` |
| ThunderAgent 프록시 | 포트 **9000**, `--router tr`(program-aware), `--metrics --profile` |
| 요청 흐름 | 클라이언트 → **9000(프록시)** → 8000(vLLM). 요청에 `extra_body.program_id` 필수 |
| GPU 사용 | GPU 0만 사용(≈22.4 GB). GPU 1–3은 유휴 → 멀티 인스턴스 재현에 사용 예정 |

---

## 2. 겪은 문제들과 해결 방법 (순서대로)

### 문제 1 — `fatal error: Python.h: No such file or directory`
- **원인**: vLLM이 torch.compile/Triton으로 런타임에 작은 CUDA 헬퍼(`cuda_utils.c`)를
  컴파일하는데 CPython **개발 헤더**(`python3.12-dev`)가 필요. 시스템에 없고 sudo도 없어 apt 불가.
- **우회**: `uv`가 관리하는 독립 실행형 CPython 3.12(헤더 포함)를 설치하고,
  그 헤더 경로를 컴파일러 검색경로(`CPATH`)에 넣어줌. venv 재생성 없이 해결.
  ```bash
  uv python install 3.12
  HDR=/home/yunuikang/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/include/python3.12
  export CPATH="$HDR" C_INCLUDE_PATH="$HDR"
  ```

### 문제 2 — KV 캐시 메모리 초과로 엔진 초기화 실패
- **원인**: Qwen3-8B 기본 컨텍스트 길이 40960에는 KV 캐시 약 5.62 GiB가 필요한데,
  24 GB 카드에서 가중치(≈16 GB) 로드 후 남는 KV 여유가 약 4.61 GiB뿐 → 거부됨.
  (vLLM이 추정한 최대 길이 ≈ 33568)
- **우회**: 컨텍스트 길이를 낮추고 메모리 활용도를 약간 올림.
  ```bash
  --max-model-len 32768 --gpu-memory-utilization 0.92
  ```

### 문제 3 — flashinfer JIT 컴파일 실패 (nvcc ↔ gcc 버전 충돌)
- **원인**: flashinfer가 샘플링 커널을 시스템 **nvcc 12.1**로 JIT 컴파일하는데,
  nvcc 12.1은 **gcc 13을 거부**함(`unsupported GNU version! gcc versions later than 12`).
  게다가 torch는 cu130이라 nvcc 12.1과 애초에 불일치.
- **우회**: flashinfer JIT 경로를 아예 피하고 vLLM에 **미리 컴파일된 백엔드**를 쓰게 함.
  어텐션은 `FLASH_ATTN`(휠에 포함, nvcc 불필요), 샘플러는 네이티브 torch 샘플러 사용.
  ```bash
  export VLLM_ATTENTION_BACKEND=FLASH_ATTN
  export VLLM_USE_FLASHINFER_SAMPLER=0
  ```

> 참고(부차적): 프록시로 `GET /v1/models` 호출 시 404가 남(백엔드 `/models`로 전달됨).
> 동작에는 영향 없음 — 핵심 경로인 `POST /v1/chat/completions`는 정상.

---

## 3. 처음부터 다시 띄우는 재현 명령어

### 0) 공통 환경 준비 (모든 터미널에서 먼저)
```bash
source /home/yunuikang/yunuikang_work/.venv/bin/activate
HDR=/home/yunuikang/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/include/python3.12
export CPATH="$HDR" C_INCLUDE_PATH="$HDR"
export VLLM_ATTENTION_BACKEND=FLASH_ATTN
export VLLM_USE_FLASHINFER_SAMPLER=0
```

### 1) vLLM 백엔드 실행 (GPU 0, 포트 8000)
```bash
CUDA_VISIBLE_DEVICES=0 vllm serve Qwen/Qwen3-8B \
  --port 8000 \
  --gpu-memory-utilization 0.92 \
  --max-model-len 32768
# 준비 확인: curl -sf http://localhost:8000/health && echo OK
```

### 2) ThunderAgent 프록시 실행 (포트 9000)
```bash
thunderagent \
  --backend-type vllm \
  --backends http://localhost:8000 \
  --port 9000 \
  --router tr \
  --metrics --profile
```

### 3) 동작 테스트
빠른 확인 (curl):
```bash
curl -s http://localhost:9000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"Qwen/Qwen3-8B",
       "messages":[{"role":"user","content":"hello /no_think"}],
       "max_tokens":32,"temperature":0,"program_id":"curl-smoke-1"}'
```
전체 스모크 테스트 (단일 요청 → 같은 program_id 멀티턴 → program release):
```bash
python /home/yunuikang/yunuikang_work/distserving/scripts/smoke_test_yunuikang.py \
  --base-url http://localhost:9000/v1 \
  --router-url http://localhost:9000 \
  --model Qwen/Qwen3-8B
# 성공 시 마지막에 "SMOKE TEST OK" 출력
```

### 종료 방법
```bash
pkill -f "vllm serve Qwen/Qwen3-8B"
pkill -f "thunderagent"
```

---

## 4. 다음에 이어서 할 일

1. **Homogeneous 멀티 인스턴스 재현** (핵심 다음 단계)
   - GPU 1~3에 vLLM을 추가로 띄우고(`CUDA_VISIBLE_DEVICES=1` 등, 포트 8001/8002…),
     ThunderAgent에 여러 백엔드를 넘김:
     `thunderagent --backends http://localhost:8000,http://localhost:8001,... --router tr`
   - `--router tr`(program-aware) vs `--router default`(단순 프록시) 비교가 핵심.
2. **지표 측정**: latency, throughput(goodput), KV cache hit rate.
   - 동시 요청 수(concurrency)/워크플로우 수를 늘려가며 **KV 캐시 스래싱으로 latency가
     급증하는 지점**이 논문처럼 재현되는지 확인 (미팅정리 문서 §4 참고).
   - 프로파일 CSV 출력 위치/포맷 확인 (`--profile-dir`, 기본 `/tmp/thunderagent_profiles`).
3. **실제 에이전트 워크로드**: `examples/inference/` (ToolOrchestra/OpenHands/mini-swe-agent).
   - 단, ToolOrchestra는 유료 API 키(OpenAI/Together/Tavily)+FAISS 인덱스, 나머지는 Docker 필요.
   - 키/도커 확보 후 진행. 지금 단계에서는 위 스모크 테스트가 "예제 워크로드" 역할.
4. **라우팅 코드 파악**: 나중에 우리가 수정할 핵심은 **`ThunderAgent/scheduler/router.py`**.
   - DeepWiki(`deepwiki.com/ThunderAgent-org/ThunderAgent`)로 전체 구조 훑기.
5. **Heterogeneous 방향**(미팅 안건): 인스턴스별 GPU 성능이 다를 때 `tr` 라우터가
   놓치는 병목 가설 메모 (compute/bandwidth/capacity 차이 반영 라우팅).

---

## 참고 파일
- 스모크 테스트: `scripts/smoke_test_yunuikang.py`
- 로그(재현 세션 기준): `../scratch/vllm_serve.log`, `../scratch/thunderagent.log`
