# 실험 저널 — Homogeneous 멀티 인스턴스 재현 (ThunderAgent baseline)

> 작성: 강윤의 · 브랜치 `yunuikang/thunderagent` · 서버: mango1 (KAIST)
> 최종 업데이트: 2026-07-02
> 상태: **재현 성공 + 스래싱 심화 실험 성공** (tr vs default, 2백엔드, 그래프 포함).
> 남은 것: 반복측정(에러바), cross-node/heterogeneous는 `TBD`.

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

> 세팅 상세·재현 명령은 `2026-07-01_SETUP_NOTES_yunuikang.md` 참고.

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

## 9. 심화 실험: KV 캐시 스래싱 강하게 유도 (보완 실험)

§8의 한계("명시적 스래싱 미유도")를 보완하기 위해, **프로그램마다 고유한 긴 컨텍스트**를
주입해 두 4090의 KV 용량을 초과시키고 재프리필이 폭증하는 구간을 만들었다.

**방법 (핵심)**: 공유 시스템 프롬프트는 prefix 캐시로 dedup되어 메모리를 안 늘리므로,
각 프로그램 첫 user 메시지에 **프로그램별 고유 필러(~3000 토큰)** 를 넣어 **프로그램별 distinct
KV** 를 크게 만들었다(`--ctx-tokens 3000`). 그러면 동시 프로그램 몇 개만으로 백엔드당 KV
용량(36,992 토큰)을 초과 → 유휴(툴콜 중) 프로그램의 KV 블록이 eviction → 다음 턴에 재프리필.

- 파라미터: `ctx_tokens=3000, turns=3, tool_sleep=0.5s, max_tokens=96`, 프로그램/런 = 48.
- 실행: `CTX=3000 TURNS=3 SLEEP=0.5 MAXTOK=96 NPROG_MULT=2 NPROG_CAP=48 bash scripts/run_sweep_yunuikang.sh <tr|default> <out> 8 16 24 32 48`
- 주: 여기서 스래싱은 "완료된 시퀀스의 prefix-cache 블록 eviction"이라 vLLM `num_preemptions`
  는 0으로 잡힘 → **KV hit rate와 총 재프리필 토큰(split 합)** 이 스래싱의 실제 지표.

### 결과 (2×4090, 유효)

| C | tr hit | default hit | tr thru(p/s) | default thru | tr p95(s) | default p95(s) |
|---|---|---|---|---|---|---|
| 8  | 0.280 | 0.044 | 0.46 | 0.30 | 30.6 | 28.2 |
| 16 | **0.673** | 0.024 | 0.49 | 0.30 | 60.8 | 53.9 |
| 24 | **0.673** | 0.024 | 0.49 | 0.30 | 60.9 | 81.5 |
| 32 | **0.673** | 0.024 | 0.49 | 0.30 | 79.8 | 106.1 |
| 48 | **0.673** | 0.024 | 0.47 | 0.30 | 97.1 | **158.4** |

**재프리필 총량(= 백엔드 query 토큰 합, 낮을수록 좋음)**: tr ≈ 2.0–2.5M/런 vs
default ≈ 25M/런 → default가 **약 10배 더 재프리필**(스래싱). default의 split은 심하게
불균형(≈16.6M/8.9M)이라 부하분산도 무너짐.

### 그래프 (figures/)
- `figures/thrash_hit_rate.png` — **핵심**: tr ~0.67 유지 vs default ~0.02 붕괴.
- `figures/thrash_throughput.png` — tr ~0.49 vs default ~0.30 (tr +57%).
- `figures/thrash_p95_latency.png` — 고부하에서 tr이 훨씬 낮음(C=48: 97s vs 158s).

### 해석
KV 용량을 초과시키자 두 라우터가 **명확히 갈림**:
- **`default`**: 프로그램을 용량 고려 없이 밀어넣어 유휴 프로그램 KV가 계속 eviction →
  hit rate **~0.02로 붕괴**, 매 턴 재프리필 폭증 → throughput 정체(0.30), latency는 부하에
  따라 급격히 악화(C=48에서 158s).
- **`tr`**: capacity-aware 스케줄링(용량 초과 시 pause/queue 후 resume)으로 활성 working set을
  용량 안에 유지 → hit rate **~0.67 유지**, 재프리필 ~1/10, throughput +57%, latency도 완만.

**→ 논문의 핵심 주장("program-aware 스케줄링이 KV 캐시 스래싱을 막아 hit rate·throughput을
지킨다")을 우리 환경에서 정량적으로 재현.** 이번엔 §7(가벼운 워크로드)과 달리 hit rate가
극적으로 갈리는 진짜 스래싱 구간을 확보.

> 한계: (1) 각 점 1회 측정(반복/에러바 필요). (2) tr c=8의 hit(0.280)이 c≥16(0.673)보다 낮은데,
> 저부하 소표본 측정 아티팩트로 보임 → 반복측정으로 확인. (3) 합성 필러라 실제 에이전트
> 토큰 분포와는 다름.

---

## 10. 워크로드 characterization (특성 분석)

> 김태현 연구원 요청: tr vs default **비교**가 아니라 **워크로드 자체의 기본 특성**을 뽑는다.
> 특성은 라우터와 무관하므로 **단일 vLLM 백엔드(포트 8000, GPU 1장)** 에 직접 측정.
> 측정 config: `ctx=3000` 필러, `turns=4`, `tool_sleep=0.4s`, `max_tokens=256`.
> 부하 하 분포/lifetime/KV는 **c=8**(48 프로그램), 순수 prefill/decode는 **c=1**(8 프로그램, 큐 오염 없음)로 측정.

### 10-0. 측정 소스와 방법 (뽑을 수 있는 값 vs 근사)

| 항목 | 소스 | 가능성 |
|------|------|--------|
| input/output 토큰 | 응답 `usage`(`prompt_tokens`/`completion_tokens`) | ✅ **정확 측정** |
| task lifetime, turn 수 | 드라이버 클라이언트 타이머 | ✅ **정확 측정** |
| tool 시간 | 우리가 넣은 `sleep` 값 | ✅ 정확(설계값) |
| **prefill** | 스트리밍 **TTFT**(첫 토큰 도착) | ⚠️ **근사** — 큐 대기 포함 → c=1에서 측정 |
| **decode** | `turn_latency − TTFT` | ⚠️ **근사** |
| KV bytes/token, GPU 수용량 | Qwen3-8B config + vLLM 시작 로그 KV풀 | 🧮 config 기반 계산(토큰 수는 측정) |

- vLLM은 **요청별** prefill/decode를 분리 제공하지 않음(/metrics 히스토그램은 집계값). 그래서 클라이언트 스트리밍 TTFT로 근사.
- 계측: `workload_driver_yunuikang.py`에 `--stream`(TTFT 캡처, `stream_options.include_usage`) 과 `--trace-out`(turn별 JSONL) 추가.

### 10-1. input / output 토큰 분포  → `figures/char_tokens.png`
- **input(turn당)**: 평균 **14,558 토큰** (min 14,310 / max 14,762). ⚠️ `ctx=3000`은 "필러 단어 3000개"인데 5자리 숫자가 여러 토큰으로 쪼개져 **실제 ~14.5k 토큰**이 됨 → §9 스래싱 실험의 실제 turn 입력이 ~14.5k였음을 확인.
- **output(turn당)**: 평균 **28.6 토큰** (8–47). `/no_think` + 짧은 질문이라 매우 짧음.
- **output(프로그램당)**: 평균 **114 토큰** (4턴 합).

### 10-2. task(프로그램) lifetime  → `figures/char_lifetime.png`
- 프로그램 생존시간(첫 turn ~ release): 평균 **63.8s**, p50 64.6s, p95 68.7s (min 52.2 / max 70.8) — c=8 부하 기준.
- turn 수: **4 (고정 파라미터)** → 분포는 단일값.

### 10-3. turn 단계별 시간 분해 (prefill/decode/tool)  → `figures/char_turn_breakdown.png`
c=1(순수) 기준, turn index별 평균:
| turn | prefill(~TTFT) | decode | tool | 합 |
|------|------|------|------|------|
| 0 | **≈1.82s** (cold, 14.4k 토큰 full prefill) | ≈0.8s | 0.4s | 3.0s |
| 1 | **≈0.13s** (prefix 캐시 히트) | ≈0.7s | 0.4s | 1.2s |
| 2 | ≈0.13s | ≈0.4s | 0.4s | 0.9s |
| 3 | ≈0.13s | ≈0.2s | 0.0s(마지막) | 0.3s |
- **핵심**: turn 0만 14.4k 토큰 전체를 prefill(≈1.8s), turn 1–3은 **자기 프로그램의 prefix를 재사용**해 새 토큰(~60개)만 prefill → TTFT가 **~14배** 짧아짐(1.82s→0.13s). **KV locality가 왜 중요한지**를 워크로드 수준에서 실측으로 보여줌.
- decode: ~28토큰에 ~0.5s → **≈18 ms/token** (4090 기준 타당).
- TTFT 통계(c=1): mean 0.549 / median 0.133 (median=warm turn, 꼬리=cold turn0).

### 10-4. KV 캐시 필요량 & GPU 수용량  → `figures/char_kv.png`
- **KV bytes/token = 2(K,V) × 36 layers × 8 KV heads × 128 head_dim × 2B(bf16) = 147,456 B = 144 KiB** (config.json 실측).
- **turn별 누적**: 시퀀스 길이(=KV 발자국)가 turn마다 증가 → 프로그램 **peak ≈ 14,668 토큰 ≈ 2.01 GiB**.
- **4090 KV 풀(실측, vLLM 시작 로그)**: `Available KV cache memory: 6.03 GiB`, `GPU KV cache size: 43,888 tokens`, `Maximum concurrency ... 1.34x`.
  - 교차검증: 43,888 × 144 KiB = **정확히 6.03 GiB** → KV/token 계산 확인 ✅
- **→ 4090 한 장에 동시 적재 가능 프로그램 = 43,888 / 14,668 ≈ 2.99 ≈ 3개.**
  - 즉 §9에서 c=48로 밀어넣으면 용량의 **~16배 초과** → 필연적 스래싱. characterization이 §9의 스래싱을 **정량적으로 설명**함.
- **5090(32GB) 추정(ESTIMATE, 미측정)**: 비-KV(가중치+활성+오버헤드) 고정 가정 시 KV 풀 ≈ **13.39 GiB ≈ 97,481 토큰 → ~6.6개 프로그램**. → hetero에서 5090이 4090보다 ~2.2배 더 담지만, 그래도 절대량은 작음(둘 다 쉽게 초과) → **작은 GPU가 먼저 스래싱**한다는 §해석과 직결.

### 10-5. 시사점 (다음 단계 연결)
- 이 워크로드는 **input-heavy**(입력 14.5k ≫ 출력 28): 비용은 거의 prefill/KV에 있고, KV locality가 결정적.
- 프로그램당 2 GiB, 4090엔 3개뿐 → homogeneous에서도 concurrency가 조금만 올라도 KV 초과. hetero에선 **GPU별 수용량(4090≈3, 5090≈6.6)이 다르므로**, 균등 분배(tr의 현재 가정)로는 작은 GPU가 먼저 터진다 → **용량 비례 라우팅** 필요성의 실측 근거.

---

## 11. 다음 할 일

1. ~~스래싱 심화 유도~~ ✅ 완료 (§9) — 고유 컨텍스트로 KV 초과, hit rate 갈림 확인.
2. ~~그래프화~~ ✅ 완료 (§9, `figures/thrash_*.png`).
3. **반복 측정**: 각 점 3회 반복해 분산/에러바 확인(현재 1회). tr c=8 아티팩트 재확인.
4. **`kv_cache_usage_perc` 시계열 수집**으로 스래싱 정량화(용량 초과 순간 시각화).
5. **논문 정독**(계획서 STEP 1) — 논문 워크로드·지표와 우리 합성 워크로드 대조.
6. (후속) cross-node(mango1+mango3) 분산 검증 → 이후 **heterogeneous**(goguma6 5090 ↔ mango 4090) — **가설·설계는 §12 참조.**

---

## 12. Heterogeneous 가설 및 연구 계획

> ⚠️ **이 섹션은 아직 실행하지 않은 계획이다.** 아래 수치는 전부 **가설/예상/기존 근거의 재인용**이며,
> heterogeneous 실측 데이터는 없다(실측 시 별도 섹션으로 추가). 논문 주장과 우리 추정을 구분해 표기한다.
>
> 근거 요약: §9(용량 초과 시 default hit 0.02 붕괴·tr 0.67 유지), §10(4090 KV풀 43,888토큰=프로그램 **~3개** 실측 /
> 5090 **~6.6개[추정]**, KV 144 KiB/token), 논문 §4.3.2(restore를 "용량 남는 아무 replica"로·재프리필 **node-agnostic 가정**),
> 논문 Table 4(BackendState에 **속도·대역폭 필드 없음**), 논문 §5.1(하드웨어가 **동질 셋업만**, GPU 혼합 실험 없음).

### 12-1. 가설 (현상 → 원인 → 해법)

- **H1 (현상)**: 4090+5090 **이종** 클러스터에서 현행 `tr`의 **용량기반 restore**는 두 GPU에 프로그램을
  비슷하게 배분한다. 그러면 용량이 작은 **4090이 자기 한계(~3 프로그램, §10 실측)를 먼저 초과** →
  **4090에서 먼저 KV 스래싱**(§9에서 본 hit rate 붕괴 패턴) → 5090에 여유가 남아도 **전체 throughput이
  4090 병목에 묶인다.** *(가설)*
- **H2 (원인)**: 스케줄러의 백엔드 상태(논문 **Table 4** BackendState)에는 `active_program_tokens`·`cache_config`
  (용량)만 있고 **GPU별 처리속도·메모리 대역폭 필드가 없다.** 또 §4.3.2는 일시정지된 프로그램의 재프리필 비용을
  **"node-agnostic"(어느 노드나 동일)** 으로 가정한다. 이 두 전제는 **노드가 동질일 때만 성립**하며(논문 §5.1도
  동질 하드웨어만 사용), **이종에서 붕괴**한다. *(논문 근거 + 우리 해석)*
- **H3 (해법)**: 배분을 **GPU별 용량(가능하면 처리속도·대역폭까지)에 비례**시키면(예: **5090:4090 ≈ 6.6:3 ≈ 2.2:1**,
  §10 기반) 두 GPU의 **스래싱 시작점이 정렬**되어 어느 한쪽이 먼저 무너지지 않고 **전체 throughput·hit rate가
  개선**될 것이다. *(가설)*

### 12-2. 검증 실험 설계

- **세팅**: **mango(4090) + goguma6(5090)** 2개 백엔드 이종 구성. 워크로드·측정 파이프라인은 **§9 스래싱 유도
  구성을 그대로 재사용**(프로그램별 고유 긴 컨텍스트로 KV 용량 압박, concurrency 스윕). 모델·프록시 동일.
- **비교 조건(arm)** — 최소 (a) vs (c):
  - (a) **tr 현행** — 용량기반/사실상 균등 restore (baseline)
  - (b) **default** — 단순 최소부하 프록시 (참고용)
  - (c) **[우리 제안] 용량비례 라우팅** — GPU별 수용량에 비례해 배분 (H3 검증)
- **측정 지표**:
  - **백엔드별** KV hit rate (4090 vs 5090 **따로**) — 스래싱이 어느 쪽에서 먼저 오는지
  - **백엔드별 스래싱 시작 concurrency** (hit rate가 꺾이기 시작하는 C)
  - 전체 **throughput / p95 latency**
  - **실제 분배 비율**(각 GPU가 받은 프로그램 수) 및 **GPU별 활용도**
- **예상 결과 (가설이 맞다면)**:
  - **(a) 현행 tr**: **4090의 hit rate가 5090보다 먼저·더 크게** 떨어지고, 전체 throughput이 **4090 포화 지점에서 꺾임**.
  - **(c) 용량비례**: 두 GPU **hit rate 곡선이 비슷**해지고, 꺾이는 지점이 **뒤로 밀림**(전체 throughput 상단·p95 개선).
  - *(반증 조건)*: 만약 (a)에서 4090·5090 hit rate가 비슷하게 떨어지거나 (c)가 (a)를 못 이기면 H1/H3는 기각/수정.

### 12-3. 열린 질문 (미팅 논의용)

1. **비례의 기준을 무엇으로?** KV 용량만인가, **처리속도·대역폭까지** 반영할까? — §10은 **용량은 실측**했지만
   **속도/대역폭 영향은 미측정**. (우선 용량비례부터, 이후 속도항 추가가 현실적일 듯 — *제안*)
2. **KV locality를 얼마나 희생?** 부하를 옮기면 재프리필이 생김 — **locality vs balancing 트레이드오프가 이종에서
   어떻게 달라지는지** 아직 모름.
3. **5090 수용량(~6.6개)은 추정치** → **실측 필요**(첫 실험에서 vLLM KV풀 로그로 바로 확인 가능).
4. **실제 워크로드(ToolOrchestra 등) 도입 여부·우선순위** — 합성 워크로드의 한계를 어디까지 보완할지.
5. **측정 신뢰도** — 현재 각 점 **1회** → **반복측정(에러바)** 필요.

---

## 부록: 산출물 위치
- 워크로드 드라이버: `scripts/workload_driver_yunuikang.py` (`--ctx-tokens`로 KV 압박)
- 스윕 러너: `scripts/run_sweep_yunuikang.sh` (CTX/TURNS/SLEEP/MAXTOK 등 env로 조절)
- 그래프 스크립트: `scripts/plot_results_yunuikang.py` (tr vs default), `scripts/plot_char_yunuikang.py` (characterization)
- 그래프(PPT용): `figures/thrash_hit_rate.png`, `figures/thrash_throughput.png`, `figures/thrash_p95_latency.png`
- characterization 그래프(§10): `figures/char_tokens.png`, `figures/char_lifetime.png`, `figures/char_turn_breakdown.png`, `figures/char_kv.png`
- characterization 원시데이터: `../scratch/char_trace.jsonl`(turn별, c=8), `../scratch/char_trace_c1.jsonl`(c=1), `../scratch/char_summary.jsonl`
- 스모크 테스트: `scripts/smoke_test_yunuikang.py`
- 버그 수정: `ThunderAgent/__init__.py` (app 지연 import)
- 결과 JSON(가벼운 §7): `../scratch/results_tr2.jsonl`, `../scratch/results_default2.jsonl`
- 결과 JSON(스래싱 §9): `../scratch/thrash_tr.jsonl`, `../scratch/thrash_default.jsonl`
- 서버 로그: `../scratch/vllm_serve*.log`, `../scratch/thunderagent*.log`
