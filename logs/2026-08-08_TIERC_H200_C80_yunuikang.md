# Tier C 시간분해 — H200 C80 첫 셀 검증 (MORI vs TA+O)

- 실행: 2026-08-08 23:10 KST 시작 → 2026-08-09 00:15 KST 종료 (KST 기준)
- 머신: H200 SXM 141GB × 1 (TP1), sglang 0.5.10, Qwen2.5-7B-Instruct
- 격자: fit 20.00 (`max_total_num_tokens=647,520`) · r=2 · C=80 · 셀 1500s (창 1254s)
- 산출물: `scratch/mori/tierc_h200/` · `figures/mori_tierc_budget_yunuikang.png`
- 커밋 상태: **경로 적응은 이 인스턴스 로컬 편집만, 커밋 안 함** (지시대로)

---

## 0. 판정 — ★ 가설 기각. C40 진행 전에 멈춤

사전 가설: **MORI 가 recompute 를 reload 로 바꿔서 TA+O 보다 decode 몫이 크다 → throughput 우위.**

[측정] 계측은 정상(closure C1~C4 전부 PASS)인데, **예측한 세 가지가 모두 안 나왔다.**

| 검증 항목 | 예측 | 측정 | 판정 |
|---|---|---|---|
| closure 게이트 C1~C4 | PASS | 양쪽 arm 전부 PASS | ✅ |
| decode 몫 역전 (MORI > TA+O) | MORI ↑ | MORI **57.20%** < TA+O **63.85%** (0.896×) | ❌ **반대 방향** |
| recompute (TA+O↑ vs MORI≈0) | MORI≈0 | MORI **16.5%** vs TA+O **15.7%** — 토큰은 1.010× 로 **동일** | ❌ |
| MORI idle 낮게 유지 | MORI 낮음 | MORI 0.30% / TA+O 0.22% — **둘 다 ≈0, 변별력 없음** | ⚠️ 판정 불가 |
| recompute ↔ Waiting 상관 | Waiting≈0 → recompute≈0 | **Waiting 이 ≈0 이 아니다** (아래 §4) | ⚠️ 전제 불성립 |

**단, MORI 의 기구(機構) 자체는 확실히 작동했다.** [측정] reload 토큰이 TA+O 의 **3.909×**
(8,196,998 vs 2,097,145). 즉 typed host eviction 은 세게 돌았고, **그런데도 recompute 가
전혀 안 줄었다.** 이것이 이번 셀의 핵심 사실이다.

throughput 은 MORI 가 근소 우위지만(1.028×) TTFT 꼬리가 크게 나빠진다(p95 4.43×).

---

## 1. 경로 적응 + 환경 (이 인스턴스)

| 항목 | 값 |
|---|---|
| REPO | `/workspace/distserving` |
| VENV | `/venv/main` |
| TRACE | `scratch/traces/tracelab_moriM_L64k_yunuikang.jsonl` |
| HF_HOME | `/workspace/hf` (모델 로컬 캐시 적중 — 다운로드 없음) |
| OUT | `scratch/mori/tierc_h200` |

수정한 파일 (**로컬 전용, 커밋 금지**):

1. `scripts/run_tierc_yunuikang.sh` — `REPO`/`VENV`/`TRACE`/`OUT` 을 goguma6 하드코딩에서
   env override 가능 + 이 인스턴스 기본값으로.
2. `scripts/_serve_sglang_7b_tp1_h200_mori_yunuikang.sh` — `export HF_HOME` 1 줄 추가.
   `REPO`/`VENV` 는 **이미 이 박스 경로로 맞아 있었다**.
3. `scripts/analyze_tierc_yunuikang.py` — 폰트 폴백(`Noto Sans CJK KR` 없음 → 동봉
   `NanumGothic_yunuikang.ttf`). `--figdir` 은 CLI 로 `figures` 지정.
4. `serve_sglang_mori_launch_yunuikang.py` — **수정 불필요** (하드코딩 경로 없음).

[측정] **계획에 없던 환경 결함 1건**: `thunderagent` 가 `/venv/main` 에 설치돼 있지 않아
셀 단계에서 프록시 기동이 실패했을 것. `uv pip install -e . --no-deps` 로 해결
(deps `fastapi`/`httpx`/`uvicorn` 은 이미 존재).

[측정] `run_tierc_yunuikang.sh` 의 `wait_gpu_idle` 에 잠복 버그: `grep -c` 가 `0` 을
출력하면서 exit 1 이라 `|| echo 0` 이 한 번 더 붙어 `n="0\n0" != "0"` → 매 boot 마다
80s 루프를 항상 완주한다. 무해(총 4 boot ≈ 6 분 낭비)해서 **실행 중 편집하지 않았다.**

## 2. 기동 게이트 (MORI_C80) — 전부 PASS

```
READY ~114s
[tierc] 계측 ON · steplog=…/steplog_MORI_C80.7089.jsonl · tag='MORI_C80'
[assert] GPU=647,520 (기대 647,520) host=1,295,041 (기대 1,295,040) fit=20.00
```
- `radix_eviction_policy='mori'` · `hicache_ratio=2.0` · `context_len=71,680` (YaRN 적용됨)
- KV Cache 할당 `#tokens: 647,520` · host pool 74.26 GB
- steplog 은 스케줄러 rank 0 (pid 7314) 이 기록 — `xfer/offload` 이벤트에 `gpu_ms` 포함

## 3. 셀별 GPU 예산 스택 [측정]

창 wall 을 100% 로 놓은 가산 예산 (decode + prefill(새) + prefill(재계산) + idle = wall).

### MORI_C80 — 창 1253.7s · step: decode 32,495 / prefill 1,958 / xfer 5,106

| 구간 | 시간 | 몫 | 토큰 |
|---|---|---|---|
| decode | 717.06s | **57.20%** | 371,990 |
| prefill (새) | 326.17s | 26.02% | 2,854,919 |
| prefill (재계산) | 206.67s | 16.49% | 1,808,932 (재계산율 38.8%) |
| idle | 3.77s | 0.30% | — |
| *transfer (별도 스트림, 예산 미가산)* | *51.14s (4.08%)* | | *reload 8,196,998 / offload 5,036,170* |

### TAO_C80 — 창 1254.3s · step: decode 37,885 / prefill 1,831 / xfer 4,441

| 구간 | 시간 | 몫 | 토큰 |
|---|---|---|---|
| decode | 800.90s | **63.85%** | 361,134 |
| prefill (새) | 253.24s | 20.19% | 2,297,880 |
| prefill (재계산) | 197.45s | 15.74% | 1,791,652 (재계산율 43.8%) |
| idle | 2.74s | 0.22% | — |
| *transfer (별도 스트림, 예산 미가산)* | *20.31s (1.62%)* | | *reload 2,097,145 / offload 4,458,876* |

### closure 게이트 — 양쪽 전부 PASS

| | MORI_C80 | TAO_C80 |
|---|---|---|
| C1 busy ≤ wall | PASS (busy 99.70%) | PASS (busy 99.78%) |
| C2 steplog 커버리지 | PASS (100.00%) | PASS (99.97%) |
| C3 busy ÷ forward host | PASS (27.04×) | PASS (27.62×) |
| C4 토큰 교차검증 | PASS (prefill 1.004 / decode 1.005) | PASS (prefill 1.004 / decode 1.007) |

### 파생 지표 [측정]

| | MORI | TA+O | MORI÷TA+O |
|---|---|---|---|
| decode 효율 (tok / decode-second) | 518.8 | 450.9 | **1.150×** |
| decode step 당 토큰 | 11.45 | 9.53 | 1.201× |
| prefill 커널 속도 (tok/s) | 8,752.9 | 9,073.9 | **0.965×** |
| recompute / 출력 토큰 | 4.859 | 4.999 | 0.972× |
| reload / 출력 토큰 | 22.018 | 5.851 | **3.763×** |
| output throughput (tok/s) | 153.24 | 149.04 | 1.028× |
| steady 완료 토큰 | 192,197 | 187,275 | 1.026× |
| TTFT mean / p95 (s) | 17.4 / 96.5 | 10.8 / 21.8 | 1.61× / **4.43×** |
| 완주 프로그램 | 73 | 64 | — |

---

## 4. Waiting 상관 검증 — 전제가 성립하지 않았다 [측정]

`profile_*/step_profiles.csv` 의 `pause_s` (= 라우터 `global_waiting_queue` 대기) 를
분석 창 안에서 집계:

| | MORI_C80 | TAO_C80 |
|---|---|---|
| 창 안 step | 2,175 | 2,011 |
| `pause_s > 0.05s` 인 step | 309 (14.2%) | 222 (11.0%) |
| `pause_s` 합 | 41,499s | 23,845s |
| `pause_s` p50 / max | 0.002s / 762.7s | 0.002s / 1,118.6s |

즉 **Waiting ≈ 0 이 아니다.** 오히려 MORI 가 TA+O 보다 **더 많이** 세운다
(합 1.74×). 따라서 "Waiting≈0 → recompute≈0" 분기는 이번 셀에서 검사할 수 없고,
recompute 가 양쪽 동일한 것은 Waiting 량이 양쪽 다 유의미하게 크다는 사실과 모순되지 않는다.

## 5. MORI arm 전용 에러 — 창 밖(드레인) 산물로 확인, 오염 아님 [측정]

MORI 프록시 로그에만 `wait timeout after 1800.0s` 47건, `has no valid backend` 37건,
Traceback 18건, HTTP 500 3건 (TA+O 는 전부 0건). 오염 여부를 확인했다:

- 프록시 로그 line 7606 이 `INFO: Shutting down`, **첫 wait timeout 은 line 7726** — 즉
  전부 graceful shutdown 시작 **이후**다.
- 논리적으로도 `asyncio.wait_for(timeout=1800)` 은 1800s 경과해야 발화하는데 셀 드라이버
  wall 은 1560s 다. 창(1254s) 안에서는 발화 불가.
- HTTP 200 은 7,019건, 500 은 3건(0.04%), 드라이버 `failed_programs=0`.

→ **분석 창은 깨끗하다.** 결과 해석에 영향 없음.

## 6. 원인 정리 (왜 예측이 빗나갔나)

[측정] 확정된 사실 3개:
1. MORI 의 typed host eviction 은 **작동했다** — reload 토큰 3.909×.
2. 그런데 recompute 토큰은 **줄지 않았다** — 1.010× (사실상 동일).
3. GPU 는 양쪽 다 **포화** 상태다 — idle 0.2~0.3%.

[추론] 이 세 개를 합치면: **이 격자에서 recompute 는 "reload 로 대체 가능한 종류"가
아니다.** reload 는 라우터가 CPU tier 로 내렸다가 되돌리는 프로그램에만 효과가 있는데,
recompute 는 그와 별개로 fit 20 · C=80 · 64k 컨텍스트에서 **엔진 내부 radix cache 압박**으로
발생한다. MORI 정책은 host tier 축출 **순서**만 바꿀 뿐 device tier 압박의 **총량**을
줄이지 못한다.

[추론] MORI 가 throughput 에서 근소 우위인 실제 경로는 가설과 다르다:
- decode 몫은 **작아졌는데** decode 효율이 1.150× (step 당 토큰 1.201×) → 같은 토큰을
  더 적은 GPU 시간에 뽑는다 = **배치가 더 크다**.
- 그렇게 아낀 시간이 decode 가 아니라 **prefill(새) 로 갔다** (26.0% vs 20.2%, 새 prefill
  토큰 1.24×). 즉 MORI 는 "decode 를 더 하는" 게 아니라 **더 많은 새 일감을 받는다**.
- 그 대가가 TTFT p95 4.43× 다.

[추론] reload 가 공짜가 아닐 가능성: prefill 커널 속도가 MORI 에서 0.965× 로 **3.5% 느리다**
(동일 GPU·동일 커널·동일 attention backend). reload 트래픽이 3.9× 많으므로 HBM/PCIe
대역폭 경합 의심. 다만 배치 구성·시퀀스 길이 차이로도 설명될 수 있어 단정 못 한다.

## 7. 방법론 한계 — 결론을 읽을 때 반드시 같이 볼 것

1. [추정] **recompute 시간은 독립 측정이 아니다.** 분석기는 prefill GPU 시간을 토큰 비로
   안분한다(`analyze_tierc_yunuikang.py` docstring 명시). 실제로 두 arm 모두 prefill(새)와
   prefill(재계산)의 tok/s 가 소수점까지 같다(MORI 8752.9 / 8752.8). 따라서 "recompute 몫"은
   사실상 **recompute 토큰 수의 재표현**이다.
2. [추정] **idle 은 유도값** (`wall − busy`)이라 "decode+prefill+idle = wall" 은 항등식이다.
   idle ≈ 0 은 "GPU 가 포화"라는 뜻일 뿐, reload 가 idle 에 숨어 공짜였다는 증거가 **아니다.**
   → 검증 항목 "MORI idle 낮게 유지(reload 겹쳐 공짜)"는 이 계측 설계로는 **판정 불가**.
3. [측정] `results_tierc.jsonl` 의 `hicache_ratio` 필드가 양쪽 다 `0.0` 인데 이는 드라이버가
   인자를 안 받은 것일 뿐, 엔진 실제 값은 assert 로 r=2 확인됨(host 1,295,041).

## 8. 다음 단계 권고 (C40 은 아직 돌리지 않음)

지시대로 **C40 진행 전에 멈췄다.** 우선순위:

1. **typed 스탬프가 실제로 변별력이 있었는지 확인.** 소스 경로는 살아 있음을 확인했다
   (`serving_chat.py:318` 이 `priority=request.priority` 를 무조건 전달, `radix_cache.py:490`
   이 `enable_priority_scheduling` 과 무관하게 `req.priority` 를 읽음). 남은 위험은
   **`_type_rank` 결과가 한 값으로 쏠렸을 가능성** — 그러면 typed eviction 이 LRU 로 퇴화한다.
   라우터에 rank 분포 카운터를 찍는 게 가장 싼 결정적 검사다.
2. 그 다음에야 C40 이 의미가 있다. C40 은 압박이 낮아 recompute 자체가 줄어드는 조건이라,
   "recompute 가 압박 유래인지 라우터 유래인지"를 가르는 **대조군**으로 값어치가 있다.
3. reload 대역폭 경합 가설은 prefill 커널 속도 3.5% 차이로만 지지되므로, 확인하려면
   reload 를 끈 MORI(정책만 mori, r=0) 셀이 필요하다.
