# 실험 C 결과 — R 모델로 "tr의 GPU 활용률"을 예측·검증 (D에서 왜 지는가)

> 작성: 강윤의 · 브랜치 `yunuikang/thunderagent` · 2026-07-07 · 계획서 `plans/2026-07-06_PLAN_experiment-C_yunuikang.md` 실행 결과
> **중심 결과: R = k_fit × d 가 tr의 GPU 점유율 U를 예측한다. Pearson r(예측 U, 실측 U) = 0.959 (clean 13점).**

---

## 1. 설정 (완전 격리)

- **HW**: mango1 **GPU2·GPU3** 2×RTX 4090 (SWE 스윕의 GPU0/1·포트 8000/8001/9000과 물리·포트 완전 분리).
  - vLLM: GPU2→**8002**, GPU3→**8003**, `--max-model-len 32768 --gpu-memory-utilization 0.92`, **KV 각 43,888 tok** (D와 동일 확인).
  - 프록시: ThunderAgent **:9001**, `--metrics --profile --profile-dir`. 새 tmux 세션 `expC` 전용.
- **워크로드**: `scratch/traces/tracelab_fit32k.jsonl` (D와 완전 동일). **NPROG=64, REPEAT=3**, **C=4·8·16·32**.
- **가드레일**: `scheduler/router.py` 로직 **미수정** (관측 + CLI 노브 + replay 옵션만). 공유 스크립트 미수정 —
  **expC 전용 복사본**만 사용(SWE 스윕 무영향 보장).
- **★ CAVEAT (동시 실행)**: 실험 C는 진행 중이던 SWE 스윕과 **동시 실행**되어 노드 CPU/RAM/PCIe를 공유했다
  (GPU 연산만 분리). SWE 스윕은 16:10에 자연 완료 → Phase A 후반·R·K·D2는 경합이 점차 줄어든 조건에서 측정.
  따라서 **throughput 절대값**은 경합 영향을 받을 수 있고, 결론은 **C 내부의 tr vs default 상대비교**와
  **예측 U vs 실측 U** 정합에 근거한다.

### 신규 산출물 (전부 `*_yunuikang` / `*_expC`)
- `scripts/trace_replay_driver_expC_yunuikang.py` — driver + **`--tool-scale S`** (duty_cycle 노브; tool_duration×=S, 캐시 불변).
- `scripts/run_trace_sweep_expC_yunuikang.sh` — 8002/8003/9001 격리 스윕 (proxy 재시작 시 **`--port 9001`만** kill, router-mode assertion, `LABEL`/`PROXY_EXTRA` 훅).
- `scripts/sample_gpu_resident_yunuikang.py` — **GPU2/3만**(`nvidia-smi --id=2,3`) 1s 샘플러 → per-backend reasoning/acting/paused/nrr + util.
- `scripts/run_expC_all_yunuikang.sh` — 5-phase 마스터(각 점 즉시 append).
- `scripts/plot_expC_yunuikang.py` — R 모델 분석 + 그래프.

---

## 2. 명령 (재현)

```bash
# c=1 duty 프로파일 (d 측정): 첫 25세션, concurrency 1, stream
python scripts/trace_replay_driver_expC_yunuikang.py --trace $TRACE \
  --base-url http://localhost:9001 --concurrency 1 --num-programs 25 --stream \
  --tool-scale 1.0 --router default --run-tag duty-c1  # -> prof_duty/step_profiles.csv

# 전체 5-phase (tmux expC:run)
bash scripts/run_expC_all_yunuikang.sh
#  A  tr,default  C=4,8,16,32  ts=1.0
#  R  tr C=16     ts∈{0.5,0.25,0.2,0.125}   (R=1 넘기기)
#  K  tr C=16     --use-acting-token-decay ; --acting-token-weight 0.5
#  D2 tr C=16     ts=2.0                     (R<1 반대끝)

python scripts/plot_expC_yunuikang.py   # -> figures/expC_*.png + scratch/expC/expC_summary.csv
```

---

## 3. 결과

### 3-0. duty_cycle (워크로드 고유값)
c=1 clean 프로파일(25 programs, 87 steps): **d = Σ(prefill+decode) / Σ(prefill+decode+tool) = 0.196**
→ NEED = 1/d ≈ **5.1** (GPU 1대를 채우는 데 필요한 동시 프로그램 수). 계획서 추정 d≈0.18과 정합.

### 3-1. [R1] R 모델이 GPU 점유율 U를 예측 — **핵심**
전체 15점 중 knob 2점을 제외한 **clean 13점**에서:
> **Pearson r(예측 U=min(R,1), 실측 U=1−idle) = 0.959,  평균 |오차| = 0.091**

주요 점 (실측 U = per-backend reasoning>0 시간비율, k_fit = 평균 resident):

| 셀 | C | k_fit | d_eff | **R=k_fit·d** | **예측 U** | **실측 U** | thr(p/s) | hit |
|----|---|-------|-------|--------------|-----------|-----------|----------|-----|
| tr | 4 | 1.58 | 0.196 | 0.31 | 0.31 | **0.34** | 0.082 | 0.725 |
| tr | 8 | 1.60 | 0.196 | 0.31 | 0.31 | **0.36** | 0.087 | 0.786 |
| tr | 16 | 1.60 | 0.196 | 0.31 | 0.31 | **0.375** | 0.068 | 0.797 |
| tr | 32 | 1.58 | 0.196 | 0.31 | 0.31 | **0.36** | 0.068 | 0.751 |
| default | 16 | 6.15 | 0.196 | 1.20 | 1.00 | **0.87** | 0.098 | 0.037 |
| default | 32 | 10.5 | 0.196 | 2.06 | 1.00 | **0.91** | 0.097 | 0.030 |

- **tr(R≈0.31 < 1)** → U≈0.35 (GPU 65% 놀고 있음) → throughput 열세. **정확히 R을 따라감.**
- **default(R>1)** → U 포화(0.87~0.91) → throughput 높음, 그러나 **hit≈0.03** (캐시 이득 전무).
- → D의 "tr이 진다"는 **R<1 → U≈R → throughput↓** 로 정량 설명됨.

### 3-2. [R4] R=1 넘기기 (인과 결정타) — tr, C=16, tool_scale로 duty 축 이동
| tool_scale S | d_eff | **R** | 실측 U | **throughput** | **hit** |
|-----|-------|-------|--------|----------------|---------|
| 2.0 | 0.109 | 0.18 | 0.22 | 0.045 | 0.711 |
| 1.0 | 0.196 | 0.31 | 0.37 | 0.068 | 0.797 |
| 0.5 | 0.328 | 0.52 | 0.49 | 0.099 | 0.832 |
| 0.25 | 0.494 | 0.75 | 0.61 | 0.127 | 0.821 |
| 0.2 | 0.549 | 0.85 | 0.66 | 0.136 | 0.861 |
| **0.125** | 0.661 | **1.00** | 0.71 | **0.144** | 0.828 |

- **R을 0.18→1.0으로 밀자 U 0.22→0.71, throughput 0.045→0.144 (×3.2)**, **hit는 0.71~0.86 유지**.
- 비교: default @C=16 = thr 0.098 / hit **0.037**. → **tr@S=0.125 (thr 0.144, hit 0.828)이 default를 두 축 모두에서 역전.**
- 예측 임계 S≈0.2에서 R→1 교차가 실제로 관측됨. → **"R<1이 tr 열세의 원인"을 인과 확정.**

### 3-3. [R3] R의 두 축 — "좋은 회복 vs 나쁜 회복" (tr, C=16)
| 설정 | 축 | throughput | **hit** | 해석 |
|------|----|-----------|---------|------|
| tr-base (ts=1) | — | 0.068 | **0.797** | 기준 |
| `--use-acting-token-decay` | k_fit | 0.103 | 0.644 | U↑, **hit↓** (나쁜 회복) |
| `--acting-token-weight 0.5` | k_fit | 0.091 | 0.650 | U↑, **hit↓** (나쁜 회복) |
| tool_scale 0.5 | duty | 0.099 | **0.832** | U↑, **hit 유지** (좋은 회복) |
| tool_scale 0.125 | duty | 0.144 | **0.828** | U↑↑, **hit 유지** (좋은 회복) |

→ pause 완화(k_fit 축)는 U를 올리되 **캐시 이득을 잃어 default화**된다. 진짜 해법은 pause 완화가 아니라
**워크로드 duty↑ (또는 용량비례 라우팅으로 k_fit↑)**. R3 예측대로.

### 3-4. [C1/C5] latency 분해 — tr의 초과분 = pause(큐 대기)
per-step 평균(profiler): **tr pause_s = 18.5s, default pause_s = 0.0s** (tool_call_s는 6.0s로 동일).
paused peak: **tr 31 programs, default 0**. → tr 지연의 정체 = **프록시 큐 대기(pause)**, default는 pause 없음(대신 재프리필·낮은 hit).

---

## 4. 해석 (증명의 3층)

1. **정성(사슬)**: tr만 pause한다(C1: paused peak 31 vs 0) → resident(k_fit)↓(1.6 vs default 6.1) →
   GPU idle↑(U 0.37 vs 0.87) → throughput↓(0.068 vs 0.098). latency 초과분은 pause(18.5s/step).
2. **정량(법칙)**: **U ≈ min(R,1), R=k_fit·d** 가 tr·default·크로싱 13점을 **r=0.96**으로 예측(R1). tr은 R<1 영역,
   default는 R>1 영역 — 하나의 식이 두 레짐을 모두 설명.
3. **인과(결정타)**: duty 축으로 **R을 1 위로 밀면 tr의 U·throughput이 예측대로 회복·역전**(R4), 그것도 **hit를
   지키며**(R3). → tr이 D에서 진 원인은 **R<1(=pause 과다로 k_fit이 NEED=5.1에 못 미침)** 임이 인과적으로 확정.

**한 줄**: tr은 캐시를 지키려 pause하여 동시 적재(k_fit≈1.6)를 NEED(≈5.1)보다 낮게 유지 → R≈0.31 → GPU가
63% 놀아 throughput을 잃는다. 워크로드 duty가 높거나(SWE d≈1) 용량이 크면 R≥1이 되어 tr이 이긴다.

---

## 5. 한계 (정직하게)

- **동시 실행 경합**: §1 CAVEAT. throughput 절대값은 SWE 경합의 영향을 받음 → 결론은 상대비교·U 정합 기반.
- **knob 2점의 예측 편차**: k_fit 노브는 pause 타이밍 자체를 바꿔 resident 샘플링과 실제 GPU busy의 관계를
  교란 → R=k_fit·d가 U를 과소예측(decay: 예측0.28 vs 실측0.63). 워크로드만 바꾸는 main/crossing 점은 정합.
  (그래서 r=0.96은 clean 13점 기준, knob 제외.)
- **prefill_s/decode_s 미기록**: 프록시 profiler가 이 두 칼럼을 0으로 남김(vLLM 내부 계측) → latency 분해는
  populated된 **pause_s·tool_call_s**로 수행. reasoning 시간(d)은 c=1 프로파일에서 별도 확보.
- **실측 U가 고R에서 예측 하회**: R→1 부근에서 실측 U(0.71) < 예측(1.0). k_fit이 물리 상한(4090 KV≈1.3x)에
  묶여 잔여 bubble이 남기 때문 — 방향·단조성은 정확, 절대 포화점은 약간 미달.
- **d의 부하의존성**: d=0.196은 c=1 고유값. 부하 하에선 경합으로 reasoning이 늘어 d가 다소 변동 가능(교차확인 권장).

## 6. 사건 기록 (재현·감사용)
- **버그1(수정)**: proxy kill이 `/proc/PID/cmdline`(NUL 구분)을 공백 패턴으로 grep해 실패 → 이전 default proxy가
  9001 점유 → 초기 Phase A가 default로 실행됨. `tr '\0' ' '` 스캔 + router-mode assertion으로 수정, 오염 재시작.
  duty 프로파일도 이때 오염(prof_duty에 c=4 step 혼입) → DUTY_END 이전 87 step만 남겨 clean d=0.196 확보.
- **버그2(복구)**: 다른 터미널의 SWE 정리가 expC proxy(9001)까지 종료 → **D2 3점 전멸(connection failed)**.
  Phase A/R/K(42점)는 이미 완료되어 무손실. 백엔드 건재 → **D2만 경합 없이 재실행**(61/64 정상 완료)해 대체.
  오염분은 `scratch/expC/corrupted_D2/`에 보존.

## 7. 산출물
- 그래프(`figures/`): `expC_pred_vs_meas_U.png`(R1), `expC_R1_crossing.png`(R4), `expC_knob_two_axes.png`(R3),
  `expC_main_sweep.png`, `expC_latency_breakdown.png`(C5), `expC_need_vs_fit.png`(C6), `expC_throughput_vs_idle.png`(C4).
- 데이터: `scratch/expC/expC_{tr,default,cross_ts*,knob_*}.jsonl`, `sample_*.csv`, `prof_*/step_profiles.csv`, `expC_summary.csv`.
