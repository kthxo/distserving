# 실험 저널 — Homogeneous 멀티 인스턴스 재현 (ThunderAgent baseline)

> 작성: 강윤의 · 브랜치 `yunuikang/thunderagent` · 서버: mango1 (KAIST)
> 최종 업데이트: 2026-07-02
> 상태: **1차 재현 성공** (tr vs default, 2백엔드) — 심화 스래싱/그래프는 `TBD`.

---

## 1. 실험 목표

ThunderAgent(ICML 2026)를 우리 랩 GPU에서 **homogeneous(동일 GPU) 멀티 인스턴스**로 돌려,
논문이 보고한 경향을 재현하는 것이 목표.

- **핵심 비교**: 같은 부하를 **`tr`(program-aware capacity scheduling, ThunderAgent 핵심)**
  vs **`default`(단순 최소부하 프록시)** 두 라우터로 돌려 성능 차이를 본다.
- **확인하고 싶은 현상**: 동시 프로그램 수(concurrency)를 올릴 때
  **처리량이 꺾이는 포화/스래싱 지점**이 생기는지, 그리고
  `default`가 먼저 무너지고 `tr`이 더 오래 버티는지 (미팅정리 §4·§6).
- 지금은 heterogeneous 이전의 **baseline 재현** 단계.

---

## 2. 실험 구성

**토폴로지: mango1 단일 노드, GPU 0+1 (둘 다 RTX 4090, homogeneous)**

```
합성 워크로드 드라이버 (workload_driver_yunuikang.py)
  │  다수 program_id, concurrency C 스윕
  ▼
ThunderAgent 프록시 (:9000, --router tr | default, --metrics --profile)
  ├─ vLLM #0  (GPU0, :8000)  Qwen/Qwen3-8B
  └─ vLLM #1  (GPU1, :8001)  Qwen/Qwen3-8B
```

| 항목 | 값 |
|------|-----|
| 모델 | `Qwen/Qwen3-8B` (bf16) |
| vLLM 인스턴스 | GPU0→:8000, GPU1→:8001, 각 `--max-model-len 32768 --gpu-memory-utilization 0.92` |
| KV 용량(백엔드당) | num_gpu_blocks 2312 × block 16 = **36,992 토큰** (합계 ≈ 74k) |
| 프록시 | ThunderAgent :9000, `--backends :8000,:8001` |
| vLLM | 0.24.0 / torch 2.11.0+cu130 |
| 필수 환경변수 | `CPATH`(uv python 헤더), `VLLM_ATTENTION_BACKEND=FLASH_ATTN`, `VLLM_USE_FLASHINFER_SAMPLER=0` |

> 세팅 상세·재현 명령은 `SETUP_NOTES_yunuikang.md` 참고.

---

## 3. 합성 워크로드 드라이버가 흉내내는 것

`scripts/workload_driver_yunuikang.py`. 실제 에이전트 워크로드(ToolOrchestra 등)는
유료 API 키·Docker가 필요해 못 쓰므로, **에이전트의 자원 사용 패턴만 합성으로 재현**한다.

- **프로그램 단위**: 프로그램 1개 = 고유 `program_id`. ThunderAgent가 이 id로 KV 캐시/라우팅을
  프로그램에 고정(sticky)한다.
- **공유 시스템 프롬프트**: 모든 프로그램이 동일한 긴 시스템 프롬프트로 시작 → **prefix 캐시** 유발.
- **멀티턴 루프** (턴 = 리즈닝 + 툴콜):
  `chat completion(리즈닝) → tool_sleep 만큼 sleep(툴콜 흉내, GPU 유휴 버블) → 툴 결과를 대화에 추가 → 다음 턴`.
  턴이 쌓이며 KV 캐시가 유기적으로 커진다(부분 프리필 상황 재현).
- **종료 시 release**: 프로그램이 끝나면 `POST /programs/release` 로 라우터에 정리 신호.
- **concurrency 스윕**: 동시에 도는 프로그램 수 `C`를 인자로 받아 올려가며 측정.
- 이번 실험 파라미터: `turns=4, tool_sleep=0.4s, max_tokens=256`, num_programs=max(64, 2·C).

---

## 4. 측정 지표와 중요성

| 지표 | 의미 | 왜 중요한가 |
|------|------|-------------|
| **Latency** (프로그램 완료 시간; mean/p50/p95/max) | 한 프로그램이 모든 턴을 끝내는 데 걸린 시간 | 포화/스래싱이 시작되면 **급증**. 급증 지점이 곧 시스템 한계. |
| **Throughput** (프로그램/초, completion 토큰/초) | 단위 시간당 처리량 | 라우팅이 좋으면 더 높은 부하까지 유지/증가, 포화 시 **감소·정체**. goodput 관점. |
| **KV cache hit rate** (prefix cache hits/queries, 백엔드 `/metrics` 델타) | 재연산 없이 캐시 재사용된 비율 | ThunderAgent 이득의 직접 지표. |
| **백엔드 분산(split)** (백엔드별 query 델타, GPU util) | 두 인스턴스에 요청이 얼마나 고르게 갔는지 | 라우터가 실제로 멀티백엔드를 쓰는지 검증(아래 버그와 직결). |

---

## 5. 진행하면서 내린 결정과 이유

- **mango1 단일 노드(GPU 0+1) 선택** — homogeneous 재현의 핵심 현상은 **백엔드(GPU) 단위**로
  일어나며 물리 서버 수와 무관. 단일 노드면 네트워크 교란 없이 깨끗하게 재현되고 즉시 실행 가능.
  (cross-node mango1+mango3, goguma6(5090)은 분산검증·heterogeneous 단계에서 투입 예정.)
- **인스턴스 2개로 시작** — tr vs default 차이는 백엔드 2개면 관측 가능. 여유 두고 빠르게 검증.
- **합성 드라이버 직접 작성** — 패키지 예제는 외부 API 키/Docker 의존. 지표 통제·스윕에 경량 드라이버가 적합.
- **컨텍스트 길이 32768로 캡** — 24GB 4090에서 KV가 기본 40960에 안 맞아 초기화 실패(§SETUP_NOTES 문제2).

---

## 6. ⚠️ 발견·수정한 버그 (중요 — 초기 결과 무효화)

**증상**: `--backends A,B --router default` 로 프록시를 띄워도, `/health`가 백엔드를 **1개(8000)만**,
`scheduling_enabled=true`(tr)로 보고. 실제로 **8001은 요청 0건**(GPU1 유휴), tr/default 결과가 동일.

**원인**: `ThunderAgent/__init__.py` 가 로드 시 `from .app import ...` 로 **app을 즉시 import**.
그런데 app.py는 모듈 레벨에서 `router = _create_router()` 를 실행 → CLI가 `set_config()`를
부르기 **전에**, 어떤 서브모듈이든 처음 import되는 순간(`ThunderAgent.__main__` 포함)
**기본 config(백엔드 1개, tr 모드)로 라우터가 굳어짐**. 그래서 `--backends`/`--router`/`--profile`이
전부 무시됨.

**수정**: `__init__.py`에서 app을 **지연 import**(PEP 562 `__getattr__`)로 바꿔, `__main__`이
`set_config()`를 먼저 실행한 뒤 라우터가 실제 CLI config로 생성되도록 함.
→ 수정 후 `/health`가 백엔드 2개·올바른 router_mode 보고, 쿼리 델타가 두 백엔드에 균등 분산됨.

> **따라서 이 수정 이전(단일 백엔드)으로 돌린 스윕 수치는 폐기.** 아래 §7 표는 모두 수정 후 유효 데이터.

---

## 7. 실행한 명령어와 결과 (유효 데이터, 2백엔드)

```bash
# 백엔드 2개 (각 GPU) — SETUP_NOTES의 환경변수 필요
CUDA_VISIBLE_DEVICES=0 vllm serve Qwen/Qwen3-8B --port 8000 --max-model-len 32768 --gpu-memory-utilization 0.92
CUDA_VISIBLE_DEVICES=1 vllm serve Qwen/Qwen3-8B --port 8001 --max-model-len 32768 --gpu-memory-utilization 0.92
# 스윕 (프록시 재기동 + concurrency 스윕 자동화)
bash scripts/run_sweep_yunuikang.sh tr      results_tr2.jsonl      8 16 32 48 64 96 128
bash scripts/run_sweep_yunuikang.sh default results_default2.jsonl 8 16 32 48 64 96 128
```

공통: turns=4, tool_sleep=0.4s, max_tokens=256. `split` = 두 백엔드가 처리한 prefix-cache
query 델타(≈ 요청량 비율).

### router = `tr`
| concurrency | throughput(prog/s) | lat mean(s) | p95(s) | KV hit rate | split (b0/b1) |
|---|---|---|---|---|---|
| 8   | 2.40  | 3.28 | 3.51 | 0.945 | 63.5k / 63.4k |
| 16  | 4.62  | 3.34 | 3.53 | 0.967 | 65.4k / 61.5k |
| 32  | 8.86  | 3.47 | 3.69 | 0.971 | 63.4k / 63.4k |
| 48  | 12.20 | 3.71 | 4.00 | 0.963 | 95.0k / 95.1k |
| 64  | **15.46** | 3.89 | 4.17 | 0.958 | 126.9k / 126.8k |
| 96  | **17.90** | 4.68 | 6.16 | 0.950 | 190.4k / 190.4k |
| 128 | 10.91 | 10.28 | 14.00 | 0.945 | 250.8k / 257.3k |

### router = `default`
| concurrency | throughput(prog/s) | lat mean(s) | p95(s) | KV hit rate | split (b0/b1) |
|---|---|---|---|---|---|
| 8   | 2.40  | 3.27 | 3.45 | 0.945 | 63.4k / 63.4k |
| 16  | 4.64  | 3.35 | 3.51 | 0.962 | 63.4k / 63.4k |
| 32  | 8.76  | 3.48 | 3.66 | 0.970 | 63.4k / 63.4k |
| 48  | 12.12 | 3.75 | 4.05 | 0.952 | 95.0k / 95.2k |
| 64  | 14.21 | 4.15 | 4.71 | 0.953 | 126.8k / 126.9k |
| 96  | 14.11 | 5.77 | 8.73 | 0.946 | 193.9k / 186.5k |
| 128 | 11.12 | 8.97 | 12.25 | 0.948 | 256.0k / 251.0k |

### tr vs default 요약 (throughput, prog/s)
| C | tr | default | tr 이득 |
|---|---|---|---|
| ≤48 | 동일 | 동일 | ~0% (저부하) |
| 64 | 15.46 | 14.21 | **+8.8%** |
| 96 | 17.90 | 14.11 | **+26.9%** |
| 128 | 10.91 | 11.12 | -1.9% (둘 다 붕괴) |

---

## 8. 관찰 / 해석 (vs 논문 경향)

**논문 경향(기대)**: 부하를 올리면 `default`가 먼저 무너지고 `tr`이 더 오래 버팀.

**우리 결과 — 경향 재현됨**:
- **저부하(C ≤ 48)**: tr ≈ default. 둘 다 두 백엔드에 균등 분산, 차이 없음(자원 여유).
- **중고부하(C = 64~96)**: **tr이 확실히 우세**. C=96에서 throughput 17.90 vs 14.11 (**+27%**),
  p95 latency 6.16s vs 8.73s. default는 C=64에서 이미 throughput 천장(≈14 p/s)에 부딪혀 C=96까지
  정체하는 반면, tr은 C=96까지 계속 증가 → **default가 먼저 포화**하는 논문 경향과 일치.
- **과부하(C = 128)**: 둘 다 붕괴(throughput↓, latency 급증). 이 지점은 두 4090의 물리 한계로,
  tr의 pause/resume 오버헤드가 이 극단에서는 이점이 되지 못함(약간 더 나쁨).
- **KV hit rate**: tr·default 모두 ~0.95로 유사. 이 워크로드에선 두 라우터 다 프로그램을 sticky하게
  유지해 캐시 재사용률 자체는 비슷하고, **차이는 부하 분산·스케줄링 효율에서 발생**.

**한 줄 결론**: homogeneous 2×4090에서 ThunderAgent(`tr`)는 중고부하(C≈64–96)에서 naive
`default` 대비 **throughput 최대 +27%, p95 latency 개선**을 재현. 논문의 정성적 경향(프로그램-어웨어
스케줄링이 더 높은 부하까지 버팀)과 부합.

> 주의/한계: (1) 합성 워크로드라 실제 에이전트와 토큰 분포·툴 지연이 다를 수 있음.
> (2) 아직 KV 용량 초과로 인한 **명시적 캐시 스래싱**(재프리필 폭증)은 강하게 유도하지 못함 —
> 지금 이점은 주로 부하분산/스케줄링에서 옴. 더 긴 컨텍스트/큰 max_tokens로 스래싱 심화 필요.

---

## 9. 다음 할 일

1. **스래싱 심화 유도**: `--max-model-len`↑ + max_tokens↑ + 긴 시스템프롬프트로 한 백엔드 KV 용량
   초과를 유발 → 재프리필/`num_preemptions` 급증과 tr의 pause/resume 이점을 더 뚜렷이.
2. **그래프화**: concurrency축 throughput/p95-latency 곡선(tr vs default 오버레이) → 미팅 슬라이드.
   (`results_tr2.jsonl`, `results_default2.jsonl` 사용.)
3. **반복 측정**: 각 점 3회 반복해 분산/에러바 확인(현재 1회).
4. **`num_preemptions`·`kv_cache_usage_perc` 시계열 수집**으로 스래싱 정량화.
5. (후속) cross-node(mango1+mango3) 분산 검증 → 이후 **heterogeneous**(goguma6 5090 ↔ mango 4090).

---

## 부록: 산출물 위치
- 워크로드 드라이버: `scripts/workload_driver_yunuikang.py`
- 스윕 러너: `scripts/run_sweep_yunuikang.sh`
- 스모크 테스트: `scripts/smoke_test_yunuikang.py`
- 버그 수정: `ThunderAgent/__init__.py` (app 지연 import)
- 결과 JSON: `../scratch/results_tr2.jsonl`, `../scratch/results_default2.jsonl`
- 분산 CSV: `../scratch/dist_tr.csv`, `../scratch/dist_default.csv`
- 서버 로그: `../scratch/vllm_serve*.log`, `../scratch/thunderagent*.log`
