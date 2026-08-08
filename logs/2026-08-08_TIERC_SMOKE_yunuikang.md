# Tier C 시간 분해 계측 — 5090 스모크 게이트 (통과)

- 실행: 2026-08-08 21:49~22:30 KST · goguma6 RTX 5090 ×2 · TP2 · Qwen3-8B · Track M
- 목적: **H200 에서 디버깅 없이 바로 돌 수 있는지** 여기서 확인한다. 가설 검정이 아니라 **배관 검증**이다.
- 셀: C=8 · fit 8.10 (`--max-total-tokens 262,144`) · MORI/TA+O r=2 · TA r=0 · 창 150~300s
- 라벨: **[측정]** 직접 관측 · **[추론]** 해석

---

## 0. 판정

**★ 게이트 PASS — 5개 항목 전부.** 커밋·push 조건 충족.

| # | 게이트 항목 | 결과 |
|---|---|---|
| 1 | steplog jsonl 정상 기록 + 값 sane | ✅ 3셀 전부 |
| 2 | closure 통과 | ✅ C1~C4 전부 PASS |
| 3 | 오프로딩계만 transfer>0, 비오프로딩 0 | ✅ **TA(r=0) = 정확히 0** |
| 4 | analyze end-to-end (그림까지) | ✅ `figures/mori_tierc_budget_yunuikang.png` |
| 5 | (덤) 5090 Tier C 결과 확보 | ✅ 3셀 |

---

## 1. 실측 [측정]

### 1.1 GPU 가산 예산 (창 wall = 100%)

| 셀 | r | decode | prefill(새) | prefill(재계산) | idle | transfer* |
|---|---|---|---|---|---|---|
| **TA** | 0 | **33.02%** (54.0s) | 40.04% (65.5s) | 0.00% | 26.94% | **0.00%** |
| **TA+O** | 2 | 27.61% (78.1s) | 21.04% (59.5s) | **0.27%** (0.77s) | 51.07% | 0.65% |
| **MORI** | 2 | 26.60% (75.5s) | 21.55% (61.2s) | 0.00% | 51.85% | 1.36% |

\* transfer 는 **예산에 더하지 않는다** — 별도 스트림에서 compute 와 overlap 되므로 가산하면 이중 계상이다.
실제 reload stall 은 idle 에 흡수된다.

### 1.2 전송·토큰

| 셀 | xfer 이벤트 | reload tok | offload tok | 출력 tok | recompute/출력 | reload/출력 |
|---|---|---|---|---|---|---|
| TA (r=0) | **0** | **0** | **0** | 5,768 | 0.000 | 0.000 |
| TA+O | 369 | 24,123 | 232,981 | 7,264 | **0.396** | 3.32 |
| MORI | 385 | **184,428** | 233,781 | 7,405 | **0.000** | **24.91** |

### 1.3 closure 4종

| 검사 | TA | TA+O | MORI |
|---|---|---|---|
| **C1** busy ≤ wall | 73.06% | 48.93% | 48.15% |
| **C2** steplog 창 커버리지 | 99.56% | 99.85% | 95.57% |
| **C3** GPU busy ÷ forward host | 2.09× | 8.27× | 8.42× |
| **C4 ★ 토큰 교차검증** (전체 run) | prefill **1.003** · decode **1.014** | **1.002** · **1.006** | **1.000** · **1.000** |

**C4 가 계측 정확성의 핵심 근거다** [측정]: steplog 이 센 토큰이 엔진 자체 카운터
(`prompt_tokens_total − cached_tokens_total`, `generation_tokens_total`)와 **소수점 셋째 자리까지 일치**한다.
MORI 셀 전체 run: prefill 420,681 ÷ 엔진 420,673 = **1.000** · decode 9,484 ÷ 9,488 = **1.000**.

---

## 2. 스모크가 잡아낸 결함 3건 (전부 수정)

### 2.1 ★ TP2 GPU 시간 이중 계상 — **가장 컸다**

TP>1 이면 **모든 rank 가 같은 forward 를 동시에** 돈다. rank 를 구분하지 않고 합치면
GPU 시간이 rank 수만큼 부풀었다 [측정]:

```
rank A: prefill 420,681 tok · gpu 185.4s
rank B: prefill 420,681 tok · gpu 185.1s
두 rank 합 = 841,362 tok = 엔진 실측의 정확히 2.000×
```

합산 시 busy(370s) > wall(355s) → **C1 이 FAIL 했을 것**이다.
→ 수정: 레코드에 `rank` 스탬프, 집계는 **rank 0 만**. HiCache 전송도 각 rank 가 자기 KV shard 를
병렬 전송하므로 동일 처리.

> **[추론] H200 은 TP1 이라 이 증상이 안 나타났을 것이다.** 5090(TP2)에서 먼저 돌린 것이
> 값을 한 지점 — H200 에서 처음 돌렸다면 조용히 2배 틀린 수치를 얻었을 수 있다.

### 2.2 closure 검사가 항등식이었다

원안의 `decode + prefill + idle ≈ wall (±5%)` 은 **`idle := wall − busy` 로 유도**하므로
항상 성립한다 → 계측 구멍을 못 잡는다.
→ 수정: **유도가 성립할 조건**을 검사한다.

| | 무엇을 잡나 |
|---|---|
| C1 `busy ≤ wall` | 이중 계상 (idle 이 음수가 되는 경우) |
| C2 steplog 창 커버리지 | 로그가 창 일부만 덮으면 busy 과소 → idle 이 가짜로 커짐 |
| C3 GPU ÷ host | GPU 시간이 host 보다 훨씬 작으면 이벤트가 엉뚱한 스트림에 걸린 것 |
| C4 토큰 교차검증 | **창과 무관한 절대 검증** — 회계 자체가 맞는지 |

### 2.3 SIGKILL 시 창 tail 유실

러너가 `pkill -9` 로 백엔드를 죽여 `atexit` 가 안 돌았다 → 버퍼 + 미회수 CUDA event 손실.
→ 수정: flush 를 **10건/1초** 기준으로, SIGTERM 핸들러 추가, 러너를 **SIGTERM → 유예 → SIGKILL** 로.

---

## 3. 한계 — 스모크로 검정하지 **않은** 것

| 항목 | 왜 |
|---|---|
| **가설 (MORI 의 decode 몫이 크다)** | C=8 은 `oversub = 8 ÷ 8.10 = 0.99` 로 **압박이 없다.** 실측 decode 몫은 MORI 26.60% < TA+O 27.61% 로 오히려 낮다. **가설 검정은 H200 C40/C80 에서 한다** |
| **new/recompute 분해** | 압박이 없어 recompute 가 실질 0. `new_required` 가 computed 의 1.03~1.06배로 나와 clip 됐다 — "압박 없음 또는 창 경계 오차"로 명시 기록. **압박 있는 셀에서 재확인 필요** |
| 반복 | n=1 |

**[추론] TA(r=0) 이 decode 33.0% / idle 26.9% 로 오프로딩계보다 GPU 를 더 채운 것**은
오프로딩 자체가 유휴를 만든다는 뜻이 아니라, TA 셀이 150s 로 짧아 워밍업 비중이 다른 탓일 수 있다.
셀 길이가 다르므로 **TA 를 다른 두 셀과 직접 비교하지 않는다** — TA 는 "transfer=0" 대조군으로만 쓴다.

---

## 4. 산출물

| 경로 | 내용 |
|---|---|
| `scripts/mori_tierc_instrument_yunuikang.py` | 계측 몽키패치 (forward + HiCache), env 플래그 게이트 |
| `scripts/analyze_tierc_yunuikang.py` | 집계 · Method B 분해 · 그림 · closure 게이트 |
| `scripts/run_tierc_smoke_yunuikang.sh` | 5090 스모크 러너 (셀 스킵 지원) |
| `scripts/run_tierc_yunuikang.sh` | **H200 러너** — MORI·TA+O × C{40,80} @ fit 20 · 셀 25분 · 4셀 ≈ 2.5h |
| `scripts/sitecustomize.py` | 계측 훅 추가 (별도 env 게이트 — OFF 면 기존 경로 무영향) |
| `figures/mori_tierc_budget_yunuikang.png` | 예산 스택 + 정규화 비교 |
| `scratch/mori/tierc_smoke/` | 원시 steplog · window · profile · engine CSV |

**제약 준수** [측정]: baseline(`router.py`·`backend/state.py`·`profile/state.py`) **0-diff** ·
SGLang 원본 파일 **무수정**(mtime 확인) · 기존 실험 스크립트 무수정.
기존 파일 수정은 `sitecustomize.py` **한 곳뿐**이며 `MORI_TIERC` 미설정 시 완전 무동작이다.

---

## 5. H200 에서 할 것

```bash
bash scripts/run_tierc_yunuikang.sh          # C40 → C80, 4셀 ≈ 2.5h
```
셀마다 게이트(계측 배너 · pool · host tier)를 걸고, 끝나면 자동 집계한다.
**압박 있는 레짐이므로 여기서 new/recompute 분해와 가설(decode 몫)이 실제로 검정된다.**
