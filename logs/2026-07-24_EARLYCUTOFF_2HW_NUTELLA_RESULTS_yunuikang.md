# nutella (2×RTX Pro6000 TP2) — STEP A/B 결과 (PLAN 2026-07-23 tracelab-earlycutoff-8b-2hw)

> 강윤의 · 2026-07-24 · nutella `CUDA_VISIBLE_DEVICES=1,2` (GPU1+GPU2, 각 96GB) · GPU0(Pro5000)=타 사용자(muchwater) 미접촉
> 이 문서는 goguma6(2×5090) 완료본을 nutella로 이어받아 STEP A(트레이스 재생성·재현검증) + STEP B(C_total·fit·예상시간) 실측. **게이트에서 정지.**

## STEP A — 트레이스 재생성·재현 검증 (GPU 불필요) — PASS

- 원본 `scratch/traces/tracelab_trace_full.jsonl` : md5=`c6bf9e0b17b4d0c97b66b0a4188df774`, **4,265 세션 / 357,161 턴** (goguma 기준 일치).
- 복사본 `prep_tracelab_earlycutoff_yunuikang.py`(무수정)로 L 두 버전 생성(tool clamp 300s):

| 항목 | L=40,960 (goguma) | 재현 | L=131,072 (goguma) | 재현 |
|---|---|---|---|---|
| 세션(포함률) | 3,935 (92.3%) | **3,935 (92.3%)** ✅ | 4,142 (97.1%) | **4,142 (97.1%)** ✅ |
| 턴(보존율) | 38,755 (10.9%) | **38,755 (10.9%)** ✅ | 189,431 (53.0%) | **189,431 (53.0%)** ✅ |
| peak-input median | 36,308 | **36,308** ✅ | 65,678 | **65,677.5** ✅ |
| tool clamp | 140 | **140** ✅ | 894 | **894** ✅ |
| session truncation rate | — | 68.3% | — | 23.1% |

→ **모든 값 goguma와 정확히 일치**. 출력: `tracelab_earlycutoff_40k_yunuikang.jsonl`, `tracelab_earlycutoff_128k_yunuikang.jsonl` (+ .meta.json).

## STEP B — C_total 실측 + fit·예상시간 (GPU) — 완료·GPU 반납

### 기동 (Qwen3-8B BF16 TP2, GPUS=1,2, 노브 2048/256 핀)
- **dtype=torch.bfloat16, quantization=None** (FP16, FP8 아님) 확인.
- ★ **캐시 체크포인트 불완전 발견·수리**: `models--Qwen--Qwen3-8B`의 **shard 2/5 누락**(index 5샤드 요구, 1·3·4·5만 존재)
  → q_norm/k_norm 미초기화로 로드 실패. 누락 shard2를 curl `-C -`로 이어받아 완성
  (sha256=`5991236c…f95cbf5f` 검증 일치). 이후 `HF_HUB_OFFLINE=1`로 정상 기동. (온라인 첫 시도의 "행"은 실제로는 느린 미인증 HF 15GB 다운로드였음.)
- 헬스 200, completion 정답("Paris").

### C_total 실측 (기동 로그 kv_cache_utils.py)
| max-model-len | GPU KV cache size (C_total) | Available KV | Max concurrency | weights/GPU |
|---|---|---|---|---|
| **40,960 (native)** | **1,150,112 tokens** | 78.97 GiB | 28.08× | 7.64 GiB |
| **131,072 (YaRN f=3.2)** | **1,149,216 tokens** | 78.91 GiB | 8.77× | 7.7 GiB |

- 풀은 GMU(0.92)가 결정 → 윈도우와 무관하게 ~1.15M로 동일. **YaRN 131,072 기동 가능 확인**.
- **0.8×C_total = 920,089 ≫ 윈도우(40,960 및 131,072)** → **윈도우가 항상 바인딩**(L은 윈도우 선택으로 결정, goguma 구조와 동일).

### fit·fit×d (d≈0.47 c=1 proxy, 잠정)
| L | ctx(peak-in med) | fit = C_total/ctx | fit×d | 레짐 |
|---|---|---|---|---|
| 40k | 36,308 | **31.7** | **14.9** | deep tr (전환점 0.62의 24배) |
| 128k | 65,678 | **17.5** | **8.2** | deep tr (13배) |

→ nutella는 예측(fit~16, fit×d~2.4~4.0)보다 **더 깊은 tr-zone**. (d=0.47이 구 capped d=0.196보다 높은 탓; STEP 4 실측 확정.)

### 디코드 속도 실측 (GPU-h 산출용)
- 단일 스트림 **~145 tok/s** (goguma 5090 추정 ~85보다 빠름).
- 집계: C=8 → 1,114 / C=32 → 3,406 / C=64 → 5,769 tok/s.

### 예상 소요시간 (closed-loop, tool=클라이언트 sleep; wall=max(Σtool/C, Σdecode/agg(C), 최장세션 E2E))
Cgrid(Pro6000)={8,16,32,48}, 정책2×R3=×6.

| 트레이스 | 점당 하한(최장세션 E2E) | Σtool 1패스 | full 24점 | 서브샘플 ~400세션 24점 |
|---|---|---|---|---|
| **40k** | 2.25h (tool 2.02 + dec 0.23) | 52.7h | **86 GPU-node-h** (173 GPU-h) | **54 GPU-node-h** |
| **128k** | **13.70h** (tool 12.18 + dec 1.52) | 333.6h | **540 GPU-node-h** (1,079 GPU-h) | **329 GPU-node-h** |

- **128k는 최장세션 13.7h가 점당 floor** → 24점×13.7=329h가 서브샘플 하한(세션 수 줄여도 whale이 지배). full은 540h로 비현실적.
- 40k는 고-C에서 floor 2.25h 지배 → 서브샘플 54h로 실행 가능.
- ★ 서브샘플 수치(40k=54, 128k=329)가 goguma "전체 ~53/~334 GPU-h"와 부합(Σtool·whale이 HW 무관이라 두 HW 유사).

### ★ 소스 문서 불일치 지적 (사용자 확인 요망)
- **plan §5 note 12**은 full 24점을 "40k ~567 / 128k ~3,522 GPU-h"로, task 배경은 "40k 전체 ~53 / 128k ~334 GPU-h"로 기재 → **두 수치는 서로 다른 스코프**(전자=full replay, 후자=서브샘플/Σtool)를 섞어 부른 것. 본 실측은 스코프를 분리해 위 표로 정리.

## 게이트 — 정지
STEP A 재현 PASS + STEP B 수치 보고 완료. **L(40k vs 128k) 확정과 STEP 3 스윕 착수는 사용자 승인 후.** GPU 반납 완료(GPU1·2 = 2 MiB idle).
