# 실험 D — SWE-bench Lite 결과 (녹화 + characterization + Phase D-SWE 스윕) (2026-07-07)

> 작성: 강윤의 · 브랜치 `yunuikang/thunderagent` · 2026-07-07
> 전제: `2026-07-06_SWEBENCH_STATUS_yunuikang.md`(세팅·블로커·stratified-64),
> `2026-07-06_MECHANISM_REFERENCE_yunuikang.md`(Phase 0), `plans/2026-07-06_PLAN_experiment-C_yunuikang.md`(R 모델).
> 목적: 논문 SWE-Agent 워크로드와 정렬한 **두 번째 독립 실제 워크로드**로 결론 일반성 검증.

---

## 1. 녹화 (Phase C)
- **세팅**: mini-swe-agent 1.14.4, **Qwen/Qwen3-8B**(1×4090:8000) → ThunderAgent 프록시(:9000 `--router default
  --profile`) → docker 컨테이너. stratified-64(레포 비례, seed=20260707). step_limit=40, workers=12.
- **결과**: **64/64 성공**(exit status Submitted 등), ~3h6m. 프로그램당 평균 **21.7턴**(median 20, max 40).
  - **clip rate 20.3%**(13/64가 40턴 도달) — <30%라 계획대로 스윕 진행. **한계**: 어려운 django/sympy 태스크의
    lifetime 상단 꼬리가 40에서 절단됨(프로그램 lifetime 분포만 영향, per-turn 특성은 무관).
- 산출: `scratch/traces/swebench_trace.jsonl`(64세션/1388턴, schema_ok), program_id→instance_id 매핑
  `swebench_stratified64.order.txt`.

## 2. Characterization (§D-char 방식) — **SWE는 decode-heavy** ★
`scripts/char_swebench_yunuikang.py`. 그래프 `figures/char_swebench_{tokens,lifetime,turn_breakdown,by_repo}.png`.

**3-way 워크로드 대비 (median):**
| 특성 | **SWE-bench** | TraceLab | 합성 §9 |
|------|---------------|----------|---------|
| input tok/turn | 7,702 | 18,275 | 14,558 |
| output tok/turn | **834** | 144 | ~28 |
| tool s/turn | 0.23 | 0.047 | 0.4 |
| turns/session | **20** | 9.5 | 3 |
| **성격** | **decode-heavy** | prefill-heavy | balanced |

- **★ duty_cycle d = reasoning/(reasoning+tool) = 0.995**(aggregate)/0.996(프로그램 median). SWE 에이전트는
  wall-time의 **99.5%를 토큰 생성(decode)**에 쓰고 tool(bash)은 0.5%뿐. (TraceLab d≈0.18, 합성 d≈0.56와 극명한 대비.)
- 세 워크로드가 **서로 다른 축(decode/prefill/balanced)을 자극** → 결론 일반성 검증에 이상적.
- **레포 귀속**(stratified 확인): django 21세션/377턴, sympy 15/410, matplotlib 5, sklearn 5, pytest 4,
  sphinx 4, astropy 2, requests 2, xarray 2, pylint 2, seaborn 1, flask 1 — 12개 레포 전부 커버.

## 3. ★ 사전 등록 예측 (R 모델, 스윕 전에 계산) — 스윕이 검증
R 모델(`plans/2026-07-06_PLAN_experiment-C`): **U ≈ min(R,1), R = k_fit × d**.
- SWE **d ≈ 0.995**(거의 1). 4090(43,888 tok)에 프로그램(input median 7.7k, 후반 턴 최대 30k) → k_fit ≈ 2–4.
- → **R = k_fit × 0.995 ≈ 2–4 ≫ 1** → **예측: tr이 2×4090에서 U≈1로 default 대비 이긴다(또는 최소 동률).**
- **핵심 대비**: 같은 2×4090에서 **TraceLab(D)는 d=0.18 → R≈0.37<1 → tr 패(−34%)**였는데, **SWE는 d≈0.995 →
  R≫1 → tr 승 예측**. 즉 "왜 D에선 지고 SWE에선 이기나"를 **duty_cycle 하나로 예측** → R 모델의 강력한 검증.
- (hit rate는 4칸 모두처럼 tr 우세 예상 — 스래싱 억제.)

## 4. Phase D-SWE 스윕 결과 (2026-07-07, 완료)
- 설정: 2×4090(GPU0:8000+GPU1:8001, 각 KV 43,888), replay=`swebench_trace.jsonl`, router default→tr,
  **C=4·8·16·32, NPROG=64, REPEAT=3**(24런). 실측 소요 **302분(~5h)**. 각 런 62–64/64 완료.
- 그래프: `figures/swebench_{throughput,hitrate,p95}.png`.

**결과 (3회 평균, tr vs default):**
| C | thru tr/def | tr 이득 | p95 tr/def | hit tr/def |
|---|-------------|---------|------------|------------|
| 4 | 0.099/0.104 | −4% (동률) | 82/76s | 0.917/0.833 |
| 8 | 0.133/0.127 | +5% | 119/144s | 0.841/0.458 |
| 16 | 0.116/**0.065** | **+78%** | 233/**448s** (0.52×) | 0.798/**0.083** |
| 32 | 0.109/**0.059** | **+84%** | 459/**782s** (0.59×) | 0.807/**0.065** |

**해석:**
- **tr이 2×4090에서 이긴다** (c≥16 throughput +78~84%, p95도 0.5~0.6× = 더 빠름). 저부하(c=4·8)는 동률
  (음성 대조 성립 — 자원 여유라 미분기).
- **hit rate: tr 압승 유지**(0.80~0.92 평탄) vs default 붕괴(0.83→0.065). 4칸+SWE 모두 일관.
- default는 c=8→16에서 스래싱 시작(hit 0.46→0.08), throughput 절벽.

## 5. ★ 결론 — R 모델의 duty_cycle 예측 검증 + 두 번째 실데이터 재현
- **§3 예측 적중**: SWE d≈0.995 → R = k_fit·d ≫ 1 → **tr이 2×4090에서 승**(예측대로).
- **★ 결정적 대비 (같은 하드웨어, 정반대 결과, duty_cycle이 설명)**:
  | 워크로드 | HW | d | R=k_fit·d | tr vs default | R 예측 |
  |----------|-----|-----|-----------|---------------|--------|
  | TraceLab (D) | 2×4090 | 0.18 | ~0.37 <1 | **−34% (패)** | 패 ✓ |
  | **SWE-bench** | 2×4090 | **0.995** | **≫1** | **+78~84% (승)** | 승 ✓ |
  → **동일 2×4090에서 D는 지고 SWE는 이긴다 — 유일한 차이는 duty_cycle d.** R 모델이 "언제 tr이
  이기고 지는지"를 **워크로드 하나의 값(d)으로 예측**함을 두 실데이터로 입증. (k_fit·GPU 용량은 D와 동일.)
- **논문 정렬**: SWE-Agent류 decode-heavy 워크로드에서 program-aware(tr)가 스래싱 억제→throughput·latency
  우위. 우리 결과는 이 경향을 재현(절대수치 비교는 하지 않음, HW·모델 상이).
- **2×2+ 종합**: tr의 KV hit 우세는 5개 셀(§9·D·F·G·SWE) 전부 일관. throughput 승패는 **R=k_fit·d**로 통일 설명 —
  R<1이면 패(D), R≥1이면 승(§9·F·SWE). **이것이 실험 C(2×4090 D)에서 정량 검증할 중심 가설**이며, SWE가 그
  duty_cycle 축을 **실데이터로 미리 확증**해준 셈.
- **한계**: (1) clip rate 20.3%(lifetime 상단 절단), (2) 각 점 3회(편차), (3) d는 녹화(부하 하) 측정이라
  c=1 고유값과 소폭 차이 가능(단 tool≪reasoning라 d≈1 결론은 강건), (4) Qwen3-8B는 논문 모델과 다름.
