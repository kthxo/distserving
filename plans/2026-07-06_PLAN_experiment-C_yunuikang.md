# 실험 C 상세 계획 — R 모델로 "tr의 GPU 활용률"을 예측·검증 (D에서 왜 지는가)

> 작성: 강윤의 · 브랜치 `yunuikang/thunderagent` · 2026-07-06(v2, R 모델 통합) · **플랜만(실행 전 검토 대기)**
> 전제 문서: `../logs/2026-07-06_MECHANISM_REFERENCE_yunuikang.md`(Phase 0),
> `../logs/2026-07-06_DEEP_ANALYSIS_yunuikang.md`(조사 A·B).
> 대응 피드백: (d) "D에서 tr이 throughput·latency 지는 원인을 **가설이 아니라 수치로** 증명".
> v2 변경: 원인 사슬(C1~C7)은 그대로 두고, 그 위에 **정량 예측 모델(R)**을 중심 가설로 얹음.

---

## 1. 한눈에 — 무엇을 증명하나 (R 모델이 중심)

### 1-1. 중심 예측 가설 — R 모델
tr의 GPU 활용률(occupancy) **U**는 아래 한 식으로 예측된다:

> **U ≈ min(R, 1),  R = k_fit × d**
> - **d = duty_cycle = reasoning / (reasoning + tool)** — 프로그램이 GPU 연산을 **실제 쓰는 시간 비율**
>   (reasoning = prefill+decode 시간, tool = 도구/유휴 시간). 워크로드 고유값.
> - **k_fit = 평균 resident(동시 적재) 프로그램 수** — tr이 KV 용량 안에 유지하는 프로그램 수.
> - **R ≥ 1 → GPU 가득(U≈1) → tr 우세**;  **R < 1 → bubble 발생 → U≈R → tr 열세.**

**직관(Little's law류)**: resident 프로그램 각각은 wall-time의 `d`만 GPU에서 연산하고 나머지는 tool로
GPU를 비운다. 따라서 `k_fit`개가 GPU를 채우는 시간 비율 ≈ `k_fit×d`. 이 곱이 1을 넘으면 GPU가 항상 바쁘고,
1 미만이면 그만큼 GPU에 **구멍(bubble)**이 생겨 U가 딱 R로 떨어진다. → **tr의 throughput은 U에 비례하므로
R<1이면 반드시 진다.** D는 R≈0.37이라 진다.

### 1-2. 사전 등록 예측 (기존 4칸이 이미 R 모델과 정합) ★
아래는 **실험 전 미리 계산한 예측**. 실험 C에서 U를 실측해 이 예측선 위에 놓이는지 검증한다.
(d는 워크로드별 c=1 프로파일로 확정 예정, k_fit은 프로그램 KV / 백엔드 KV풀 또는 실측 resident.)

| 셀 | 데이터/GPU | d (duty) | k_fit (백엔드별) | **R = k_fit·d** | 예측 U | 관측된 tr vs default |
|----|-----------|----------|------------------|-----------------|--------|----------------------|
| §9 | 합성·2×4090 | ~0.56 | ~3 | **~1.7** | ~1.0 | **+57% (승)** ✓ |
| **D** | 실제·2×4090 | ~0.18 | ~2 | **~0.37** | ~0.37 | **−34% (패)** ✓ |
| F | 합성·4090+5090 | ~0.56 | ~3 / ~6 | **>1 둘 다** | ~1.0 | **+100% (승)** ✓ |
| G | 실제·4090+5090 | ~0.18 | ~2 / ~4 | **0.37 / 0.72** | 0.37/0.72 | **−8% (부분회복)** ✓ |
- **G의 부분회복이 R로 설명됨**: 큰 5090은 k_fit이 커(≈4) R이 0.72로 1에 근접 → D보다 U↑ → 적자 34%→8%.
- ⚠️ 이 표는 **가설**이다. 실험 C의 임무 = d·k_fit·U를 실측해 이 숫자를 **채우고 예측선을 검증**하는 것.

### 1-3. "지금까지(현상만)" vs "이번(예측·인과)"
| | 지금까지 (D 로그) | 이번 실험 C |
|---|---|---|
| throughput tr<default | **관측만** (0.067 vs 0.102) | **R<1 예측**을 실측 U로 검증 + resident↓→idle↑ 사슬 |
| latency tr>default | p95 숫자만 | prefill/decode/**pause 대기**로 **분해** (C5) |
| 원인 | "pause로 병렬성 희생"(가설) | **R을 두 축(k_fit·d)으로 움직여 R=1을 넘겨 인과 확정** |
| 일반성 | D 한 점 | **4칸 전부를 R 하나로 예측**(교차검증) |

**증명의 3층**: (1) 원인 사슬 C1~C7을 시계열로(정성), (2) R 모델이 U를 정량 예측(4칸 교차), (3) R을
1 위로 넘겨 회복/역전(인과 결정타). 아래 §5 표가 이 세 층을 한데 묶는다.

---

## 2. 설정 (한 변수만, 재현)

- **HW(주 실험)**: mango1 2×4090 (GPU0:8000, GPU1:8001). KV 각 43,888 tok. (D와 동일 인프라.)
- **워크로드**: `scratch/traces/tracelab_fit32k.jsonl` (982세션, D와 **완전 동일**).
- **부하원**: `trace_replay_driver_yunuikang.py`, NPROG=64, REPEAT=3 (D와 동일). **신규 `--tool-scale`**(§4-B2).
- **concurrency**: **C = 8, 16, 32** (tr이 지는 구간). 저부하 대조 **c=4**(음성 대조 C0).
- **교차검증(R2)만** F/G(4090+5090)·§9(합성) 셀을 포함 — 각 셀 대표점 1개를 샘플러로 재측정(경량, §4-C).
  *(주 인과 실험은 2×4090 한정, 교차검증에 한해 F/G/§9 포함 — 원 계획의 "2×4090 한정" 메모를 이렇게 수정.)*
- **가드레일**: `scheduler/router.py` **로직 미수정**(관측 + CLI 노브 + replay 옵션만), `__init__.py` 지연 import
  픽스 유지, vLLM `--max-model-len 32768 --gpu-memory-utilization 0.92`.

---

## 3. 측정 인프라 (무엇을 어떻게 기록하나)

3종을 **동시에** 수집. 프로파일러는 기존 코드로 충분, 샘플러·d측정·tool-scale만 신규.

### 3-1. Latency 분해 — 프로파일러(기존, 신규 계측 0)
- 프록시 `--profile --profile-dir scratch/expC/<router>_c<C>` → `step_profiles.csv`에 per-step
  **`prefill_s, decode_s, pause_s, tool_call_s, prompt_tokens, cached_tokens, kv_hit_rate`** 자동 기록.
- `pause_s` = `on_request_arrive`↔`on_request_start` 차 = **프록시 큐 대기시간**(profile/state.py:106-143).
- **분해**: 완료 latency = Σ(prefill+decode+pause+tool_call). tr 초과분이 **어디서** 오는지(C5).

### 3-2. GPU util·resident 시계열 — 신규 샘플러 `scripts/sample_gpu_resident_yunuikang.py`
- 1초 간격 백그라운드: `nvidia-smi --query-gpu=index,utilization.gpu,memory.used ...`(GPU0/1) +
  프록시 `/health` per_backend `reasoning`/`acting`/`paused` count.
- 출력 CSV: `t, gpu0_util, gpu0_mem, gpu1_util, gpu1_mem, b0_reasoning, b0_acting, b1_reasoning, b1_acting, paused`.
- **resident = reasoning + acting count** per backend. **REASONING = 실제 GPU 추론 중**.

### 3-3. 파생 지표 (R 모델 변수 포함)
- **k_fit(R의 입력)** = 측정구간 평균 resident 수(백엔드별). C2의 resident 시계열 평균.
- **d = duty_cycle(R의 입력)** = **c=1 프로파일**에서 `Σ(prefill_s+decode_s) / Σ(prefill_s+decode_s+tool_call_s)`
  (contention·pause 없는 워크로드 고유값; §D-char의 c=1 데이터 재활용 가능하나 정확도 위해 재측정 권장).
  ※ **시간가중 평균(mean)** 사용 — d는 시간 비율이므로 median 아님(tool 꼬리 반영).
- **U_measured(예측 대상)** = **GPU 점유율 = 1 − idle_fraction**, idle_fraction = (REASONING count==0 인 시간)/전체.
  ← R이 예측하는 것은 "GPU가 바쁜 시간 비율"이므로 이 정의가 정확. nvidia-smi util%는 **보조**(decode는
  memory-bound라 SM%가 100 미만이어도 바쁠 수 있음 → 점유율과 구분).
- **R = k_fit × d** → **예측 U = min(R, 1)**. 실측 U와 대조가 R1의 핵심.
- **NEED vs FIT = R의 다른 표현(정식화)**: NEED = 1/d(GPU 채우는 데 필요한 동시성), FIT = k_fit.
  **NEED > FIT ⟺ 1/d > k_fit ⟺ k_fit·d < 1 ⟺ R < 1** (정확한 동치). → C6과 R은 같은 명제.

---

## 4. 실험 매트릭스 (정확히 무엇을 돌리나)

### 4-A. 기본 비교 + R 변수 측정 (원인 사슬 + R1) — GPU ~4h
tr·default 각각 C=4,8,16,32, REPEAT=3, 3종 계측 동시. **여기서 d·k_fit·U를 모두 실측**.
```
# (env: SETUP_NOTES 4줄). 백엔드 2개(GPU0:8000, GPU1:8001) 기동.
python scripts/sample_gpu_resident_yunuikang.py --out scratch/expC/sample_<router>_c<C>.csv &   # 백그라운드
NPROG=64 REPEAT=3 bash scripts/run_trace_sweep_yunuikang.sh <tr|default> \
    scratch/expC/expC_<router>.jsonl $T 4 8 16 32
# run_trace_sweep 확장: --profile-dir·샘플러 시작/종료 훅.
# d 측정용 c=1 프로파일(1회, tool 유지): trace 첫 25세션 --concurrency 1 --stream --profile.
```

### 4-B. R을 움직이는 두 축 (노브 ablation, R3) — 고정 C=16
**router.py 미수정. (1) CLI 노브 = k_fit 축, (2) replay 옵션 = duty_cycle 축.**

#### 4-B1. k_fit 축 (기존 노브 유지) — GPU ~2h
tr을 C=16에서 3설정 ×3회. pause 완화 → resident↑ → k_fit↑ → R↑.
| 설정 | 플래그 | 예측 |
|------|--------|------|
| tr-base | (기본) | k_fit≈2, R≈0.37 |
| tr-decay | `--use-acting-token-decay` | resume 낙관↑ → k_fit↑ → R↑ (단 hit↓) |
| tr-weight0.5 | `--acting-token-weight 0.5` | ACTING 과소평가 → pause 완화 → k_fit↑ (단 hit↓) |
- **★ 사전 예측(정직)**: 4090 KV가 프로그램 ~2개로 물리적 상한 → **k_fit 축 단독으로는 R=1 도달 어려움**
  (R=1엔 k_fit≈1/d≈5.5 필요, 물리적으로 스래싱 없이는 불가). 즉 이 축은 **U를 올리되 hit를 희생**
  (=default화). → "회복은 되지만 캐시 이득을 잃는 나쁜 회복"임을 보임.

#### 4-B2. duty_cycle 축 (신규 `--tool-scale`) — GPU ~2h
`trace_replay_driver`에 **`--tool-scale S`** 추가: 재생 시 `tool_duration_s ×= S`. tool↓ → d↑ → R↑,
**hit는 유지**(캐시 안 건드림). tr, C=16에서 S ∈ {2, 1, 0.5, 0.25}(필요시 0.2, 0.125) ×3회.
- **★ 사전 예측(임계 계산)**: D는 s=1에서 d≈0.18 → tool/reasoning 시간비 ≈ 4.56. R=1(k_fit≈2 → d=0.5)
  이려면 `S ≤ reasoning/tool ≈ 1/4.56 ≈ 0.22`. 예측 R:
  | S | 예측 d | 예측 R=2·d | 예측 U |
  |---|--------|------------|--------|
  | 2 | 0.10 | 0.20 | 0.20 |
  | 1 | 0.18 | 0.37 | 0.37 |
  | 0.5 | 0.31 | 0.61 | 0.61 |
  | 0.25 | 0.47 | 0.93 | 0.93 |
  | **0.2** | **0.52** | **1.05** | **~1.0 ← R=1 교차** |
  | 0.125 | 0.64 | 1.28 | ~1.0 (포화) |
- → **duty_cycle 축이 hit 손실 없이 R=1을 넘는 깨끗한 축**임을 예측. (k_fit 축과 대비.)

### 4-C. 4칸 교차검증 (R2) — 경량 재측정 — GPU ~1.5h
§9(합성)·F·G 각 셀의 **대표점 1개**(예: c=16 또는 c=32)를 샘플러 켜고 tr로 1~2회만 재실행 → **실측 U**
확보. §9·D·F·G 각각 (d, k_fit, R, 실측 U) 한 점씩 → **예측 U vs 실측 U 산점도**에 4셀(백엔드별이면 6점) 표시.
- 재실행 최소화: throughput/hit는 **기존 스윕 데이터 재활용**, 이번엔 **U(=1−idle)만** 새로 필요해 짧게.
- (대안: 재실행 없이 k_fit을 프로그램KV/풀로 추정하고 U는 D만 실측 → 예측 검증은 D 중심 + 나머지는 방향성.)

---

## 5. 증명 논리 표 (C1~C7 유지 + R 행 추가)

| # | 가설(사슬/모델) | 측정 지표 | 예상 결과 | 증명하는 것 |
|---|-------------------|-----------|-----------|-------------|
| C1 | tr이 pause한다 | paused peak, 프록시 Paused 로그 | tr>0, default=0 | pause가 tr에서만 발생 |
| C2 | pause→resident↓ (=k_fit) | resident 시계열 평균 | tr < default | 동시 실행 수 감소 |
| C3 | resident↓→GPU idle↑ | GPU 점유율, **idle 비율** | tr idle% > default | **starvation 정량 증명** |
| C4 | idle↑→throughput↓ | throughput vs idle% | 음의 상관 | idle이 throughput 손실 원인 |
| C5 | latency 초과분=대기 | latency 분해(prefill/decode/**pause**/tool) | tr 초과=pause_s; default=prefill(재계산) | "tr지연=큐대기, default지연=재프리필" |
| C6 | GPU가 굶는다 = **R<1** | NEED=1/d vs FIT=k_fit | NEED>FIT ⟺ R<1 | pause가 과해 GPU 미충족(=R<1) |
| C7 | 인과(노브) | 4-B 노브 throughput | 노브로 완화 시 throughput↑ | pause가 원인 |
| C0 | 음성 대조 | c=4 tr vs default | 차이 거의 없음(R≥1) | 저부하선 사슬 미발동 |
| **R1** | **R이 U를 예측** | d·k_fit 측정→R, 실측 U(=1−idle) | **U ≈ min(R,1)** (D: R≈0.37→U≈0.37) | **정량 모델이 맞다** |
| **R2** | **R이 4칸 전부 예측** | §9·D·F·G의 (R, 실측 U) | 4셀이 U=min(R,1) 선 위 | **모델 일반성**(현상→법칙) |
| **R3** | **R의 두 축** | k_fit축(4-B1)·duty축(4-B2)의 R,U,hit | 둘 다 U↑; **단 k_fit축은 hit↓, duty축은 hit 유지** | U의 원인이 R임 + "좋은/나쁜 회복" 구분 |
| **R4** | **R=1 넘기(결정타)** | tool-scale로 R을 1 위로(예측 S≈0.2) | R<1→U≈R(패), R≥1→U≈1(승) **역전** | **"R<1이 D 열세의 원인"을 인과 확정** |

- **핵심은 R4**: D(R≈0.37)에서 duty_cycle 축으로 R을 예측대로 1 위로 넘기면 tr의 U·throughput이
  **default를 역전**(hit는 유지)해야 한다. 예측한 임계(S≈0.2)에서 실제로 교차하면 → 모델이 인과적으로 옳다.
- **R3의 대비**가 부가 통찰: k_fit 축(pause 완화)은 U를 올리되 **hit를 잃어**(=default화) — "나쁜 회복",
  duty 축은 **hit 유지하며** 회복 — "좋은 회복". → 진짜 해법은 pause 완화가 아니라 **워크로드 duty(또는
  용량 비례 라우팅으로 k_fit↑)**임을 시사.

---

## 6. 산출물 (그래프·표·문서)

- 그래프(`figures/`):
  - `expC_latency_breakdown.png` — 스택바(prefill/decode/pause/tool), tr vs default, C별. **[C5]**
  - `expC_gpu_util_timeline.png` — GPU0/1 점유 시계열 tr vs default(대표 C=16). **[C3]**
  - `expC_resident_timeline.png` — resident(k_fit) 시계열. **[C2]**
  - `expC_idle_fraction.png` — idle 비율 막대(tr vs default, C별). **[C3]**
  - `expC_throughput_vs_idle.png` — 산점도. **[C4]**
  - `expC_pred_vs_meas_U.png` — **예측 U(=min(R,1)) vs 실측 U** (D 스윕 각 점). **[R1]** ★
  - `expC_R_across_cells.png` — **§9·D·F·G의 (R, 실측 U)**가 U=min(R,1) 선 위에. **[R2]** ★
  - `expC_knob_two_axes.png` — k_fit축·duty축 각각의 (R, U, hit) — U↑ 공통, hit는 duty만 유지. **[R3]** ★
  - `expC_R1_crossing.png` — tool-scale S vs (U, throughput, hit), 예측 R=1 교차선(S≈0.2). **[R4]** ★
  - `expC_knob_tradeoff.png` — 노브별 (throughput, hit) 트레이드오프. **[C7]**
  - `expC_need_vs_fit.png` — NEED=1/d vs FIT=k_fit 막대(= R≷1). **[C6]**
- 문서: `../logs/2026-07-06_DEEP_ANALYSIS_yunuikang.md`에 "실험 C" 섹션 추가(설정/명령/결과표/해석/한계),
  §1-2 사전예측표를 실측으로 채우고, §5 표 각 행을 실측으로 채움.
- 신규 스크립트: `scripts/sample_gpu_resident_yunuikang.py`(샘플러), `scripts/plot_expC_yunuikang.py`(분석·플롯),
  `trace_replay_driver_yunuikang.py`에 **`--tool-scale`**(부하원 옵션, 스케줄러 불변),
  `run_trace_sweep_yunuikang.sh` 확장(--profile-dir·샘플러 훅). **router.py 불변.**

---

## 7. 소요·리스크·승인

- **GPU**: 4-A ~4h + 4-B1 ~2h + 4-B2 ~2h + 4-C ~1.5h ≈ **~9.5h**(+ c=1 d측정 ~0.3h). 손대는 시간 ~1.5일
  (스크립트: 샘플러·tool-scale·플롯 + 분석). **duty 축(4-B2)·교차검증(4-C)이 v1 대비 추가분(~3.5h).**
- **리스크**: (1) D-5처럼 SSH/tmux crash → **tmux 필수**, 각 점 즉시 append(부분 보존). (2) 프로파일러 영향
  미미(tr/default 동일 조건). (3) nvidia-smi 1s 오버헤드 무시가능. (4) **d의 부하-의존성**: c=1 d가 부하 하
  d와 다를 수 있음(경합으로 reasoning 시간 늘어남) → c=1을 워크로드 고유값으로 쓰되, 부하 하 실측 d도
  프로파일러로 교차확인(한계로 명기). (5) k_fit이 시간에 따라 변동 → 평균+분산 함께 보고.
- **승인 필요**: GPU ~9.5h. 기존 tmux 인프라·`run_trace_sweep`·백엔드 재사용.

## 8. 실행 체크리스트 (승인 후)
1. `sample_gpu_resident_yunuikang.py` 작성 + dry(GPU 없이 헤더/폴링). `--tool-scale` 추가 + dry(부하량 스케일 확인).
2. `run_trace_sweep` 확장(--profile-dir, 샘플러 훅).
3. tmux `expC`: 백엔드 2개(GPU0/1), KV 43,888 확인. **stale 프록시(pid 250595) 정리**.
4. c=1 d측정 → 4-A 스윕(tr→default, C=4·8·16·32) → 4-B1 k_fit노브(C=16) → 4-B2 tool-scale(C=16) → 4-C 교차검증(§9/F/G 대표점).
5. `plot_expC_yunuikang.py` → 그래프 11종 + §1-2·§5 표 채움 → 로그 섹션 작성.
6. 서버 정리, GPU 유휴 복귀.

## 9. 미결(검토받을 것)
- **d·k_fit 초기값 확정**: §1-2 표의 d≈0.18/0.56·k_fit≈2/3은 §D-char 기반 추정 — c=1 프로파일로 확정 필요.
- **교차검증 범위(4-C)**: §9·F·G 전부 재측정(권장, U 실측) vs D만 실측+나머지 추정(GPU 절약).
- k_fit 축 노브: decay+weight0.5만(권장) vs scheduler-interval 추가.
- tool-scale 그리드: {2,1,0.5,0.25}만 vs {…,0.2,0.125}까지(R=1 확실히 넘기려면 후자 권장).
- c=32 대신 c=48도 넣을지(시간 +).
