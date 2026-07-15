# 심화 분석 계획 — 인과 설명 강화 + SWE-bench (지도교수 피드백 반영)

> 작성: 강윤의 · 브랜치 `yunuikang/thunderagent` · 서버: mango1 (+ goguma6 5090) · 2026-07-06
> 선행: `../logs/2026-07-03_EXPERIMENT_LOG_hetero_yunuikang.md`(2×2 완료), `2026-07-02_PAPER_COMPARISON_yunuikang.md`
> 상태: **플랜만 — 실행 전 지도교수/사용자 검토 대기.** GPU 장시간 점유 작업은 명시 승인 후 실행.

---

## 0. 피드백 → 이 플랜의 매핑 (왜 이 구조인가)

지도교수 피드백은 "현상은 찾았으나 **ThunderAgent가 어떤 목적으로·왜 그렇게 판단·행동하는지**에 기반한 인과
설명이 없다"는 것. 이를 6개 작업으로 분해한다. 각 작업은 **[읽기/측정/실행] → [답할 질문] → [증명]** 구조.

| 피드백 | 대응 작업 |
|---|---|
| (a) 알고리즘(cost model·policy) 먼저 정확히 이해→그 로직으로 결과 설명 | **Phase 0** |
| (e) KV가 GPU 메모리 넘으면 어떻게 처리(CPU swap/offload 여부) | **조사 A** |
| (b) 재프리필이 정확히 뭔지·왜 쟀는지·용량비와 인과 / (c) 용량은 프리필 말고 메모리 지표로 | **조사 B** |
| (d) D(실데이터 2×4090)에서 tr이 throughput·latency 지는 원인을 수치로 증명 | **실험 C (핵심)** |
| (f) SWE-bench도 실험(논문 비교) | **실험 D** |
| 모든 결과를 판단 로직 흐름으로 재서술 | **재분석 원칙 (전 작업 공통)** |

**전제 확인(코드 선독으로 이미 파악, Phase 0에서 문서화):**
- 용량 판정은 **이미 실제 메모리 지표**(`kv_cache_usage_perc`)를 씀 → 조사 B는 "새 지표 도입"이 아니라
  "결과 서술을 프리필 대신 이 메모리 지표 중심으로 재정렬".
- pause 시 vLLM에 요청을 안 보내고 프록시가 붙잡음 → **eviction=재프리필**이 코드상 참일 가능성 큼(조사 A에서 확정).
- 프로파일러가 이미 per-step `prefill/decode/pause/tool_call` 분해 기록 → 실험 C는 **신규 계측 거의 불필요**.

---

## Phase 0 — 알고리즘 정밀 이해 (모든 분석의 전제) · 산출물: "메커니즘 레퍼런스" 문서

**목적**: 논문 §4(cost model·policy) ↔ 코드(파일:라인)를 1:1로 매핑해, 이후 모든 결과 해석을
"tr이 cost model·policy상 이렇게 판단→이렇게 행동→그래서 이 현상"으로 서술할 근거 문서를 만든다.
GPU 불필요(순수 코드/논문 독해).

### 0-1. Cost model (논문 §4.2 STP 5항) ↔ 코드
- **읽기**: 논문 §4.2(STP = decode+prefill+recompute+unused+caching 5비용항), Eq.(6) 스래싱 조건.
  코드: `backend/state.py`(`active_program_tokens` L104-107, `remaining_capacity` L185-194,
  `remaining_capacity_with_decay` L196-214, `has_capacity`/`capacity_overflow`),
  `backend/vllm_metrics.py`(`calculate_shared_tokens` L294-311).
- **답할 질문**: 논문의 연속-시간 5항 비용식을 코드는 무엇으로 근사하는가?
- **증명/정리**할 내용(문서에 표로):
  - 코드는 5항 적분을 **용량-실현가능성(capacity feasibility) 판정**으로 이산화: 스래싱 회피 =
    `active_tokens − shared_tokens + buffer ≤ C_total`(Eq.6의 운영판).
  - `shared_tokens = reasoning_tokens − kv_cache_usage_perc·C_total` = **prefix 캐시로 절약된 토큰**
    (caching 항). `tool_coefficient·acting_tokens`(=acting weight) = ACTING 프로그램의 미래 재점유
    비용 반영(unused/recompute 항의 근사). `2^(-t)` 감쇠 = 논문 f(t), **resume 판정에만** 적용.
  - **정직 포인트**: 코드는 5항을 명시적으로 최소화하지 않고 **feasibility 부등식**으로 대체함 →
    "무엇을 최소화하는가"는 논문 의도(가중 5항 비용), "어떻게 구현되나"는 용량 부등식 — 이 간극을 명시.

### 0-2. Policy 결정 3종 ↔ 코드 (각 결정의 "목적"을 논문↔라인으로)
| 결정 | 코드 | 목적(논문 의도) |
|---|---|---|
| **신규 배정** | `_select_backend_for_new_program` router.py:330-362 | 큐 비었고 용량 있으면 **`active_program_tokens` 최소** 백엔드로 = **절대-토큰 균형**(용량 비례 아님). 큐 있으면 대기(공정성). |
| **pause** | `_pause_until_safe` router.py:773-805 | `remaining_capacity()<0`(=Eq.6 위반)이면 스래싱 → **ACTING 먼저(작은 것부터)**, 없으면 REASONING mark. 목적: working set을 C_total 이내로. |
| **resume** | `_greedy_resume` router.py:807-932 | 우선순위 **REASONING>NEW>ACTING**(대기중 요청 우선), 총용량 내 최대집합 선택 후 **BFD**(큰 프로그램→여유 큰 백엔드). |
| **migration** | `_resume_program(target≠origin)` router.py:692-725 | paused KV는 evicted 가정 → **아무 여유 백엔드로 restore 가능**(논문 §4.3.2 node-agnostic). |
- **답할 질문**: "왜 tr이 D에서 병렬성을 희생하나?"의 코드적 근거는? → `_pause_until_safe`가 Eq.6 위반 시
  ACTING을 pause하고, 그 요청이 `update_program_before_request`에서 `_wait_for_resume`로 **블록**되기 때문.
- **증명**: 신규 배정이 `min(active_program_tokens)`이며 **`C_total`로 나누지 않음** → 코드 L358 인용으로
  "절대-토큰 균형(용량 비례 아님)" 확정. 이게 F/G의 "tr split≈1:1 ≪ 용량비 1:2.03"의 직접 원인임을 라인으로 증명.

### 0-3. 산출물
- **신규 문서** `../logs/2026-07-06_MECHANISM_REFERENCE_yunuikang.md`: (표1) STP 5항↔코드, (표2) policy 3종↔라인,
  (그림) 요청 생애주기 상태기계(REASONING↔ACTING, ACTIVE→PAUSED→resume). 이후 D/F/G 재서술이 이 문서를 인용.
- **소요**: 손대는 시간 ~4h(독해+작성), **GPU 0h**.

---

## 조사 A — KV가 GPU 메모리 초과 시 실제 처리 (피드백 e)

**목적**: active KV 수요 > GPU KV풀일 때 처리 경로가 (a)pause+KV 완전폐기(→재프리필) / (b)vLLM CPU swap /
(c)둘 다 중 무엇인지 확정. "eviction=재프리필" 전제(모든 재프리필 해석의 뿌리)를 코드·실측으로 규명.

- **읽기**:
  - 코드: `update_program_before_request`(router.py:416-448) — PAUSED면 `_wait_for_resume`로 **요청을 프록시에서
    블록**(vLLM 미도달). `_pause_program`(L631-658) — 백엔드 추적에서 unregister만, vLLM엔 아무 신호 없음.
  - grep 결과: `scripts/`·`ThunderAgent/`에 **`swap` 문자열 없음** → ThunderAgent가 vLLM swap을 켜거나 트리거하지 않음.
  - 논문 p19 "swap-in/out latency penalty", §A.1/A.2(KV offloading) — 논문은 offload를 논하나 **우리 config엔 미적용**.
- **측정(짧은 GPU, 기존 백엔드 재사용)**:
  1. vLLM 시작 로그에서 `swap_space`/`num_cpu_blocks` 확인(기본값 유지 여부). `--swap-space` 플래그 미사용 확인.
  2. D 재현 부하(c=16, tracelab)를 잠깐 걸고 `/metrics`의 **`vllm:num_preemptions_total`** 관찰
     — homo-homo §9에서 0이었음(swap/preempt 미발생 지표). tr/default 둘 다 0인지 재확인.
  3. tr에서 pause 발생 시 해당 프로그램의 **다음 턴 `prompt_tokens` vs `cached_tokens`**(profiler `kv_hit_rate`)를
     보고 "재프리필 발생(캐시 소실)"을 직접 관측.
- **답할 질문**: KV 초과분은 폐기+재프리필인가, CPU로 swap되나?
- **증명**: (i) 코드상 swap 미사용 + (ii) `num_preemptions=0`(vLLM 자체 swap/preempt 미발동) + (iii) pause된
  프로그램이 resume 후 hit rate 급락 → **경로 (a) "pause=KV 폐기→재프리필" 확정, (b)/(c) 배제**. 이 결론을
  메커니즘 레퍼런스에 "재프리필 해석의 전제"로 명시.
- **소요**: 손 ~1.5h, **GPU ~0.3h**(기존 백엔드 살아있으면 거의 0).

---

## 조사 B — 재프리필 재정의 + 용량 서술을 "메모리 지표"로 (피드백 b·c)

**목적**: "재프리필(prefix-cache queries)"이 정확히 무엇을 세는지·왜 쟀는지 코드로 규명하고, 용량 논의를
프리필/queries 대신 **직접 메모리 지표**(kv_cache_usage_perc·resident 수·pause량)로 재정렬. 재프리필은 보조로.

- **읽기**:
  - `vllm_metrics.py`: `prefix_cache_queries`(L124)·`prefix_cache_hits`(L128)는 vLLM **토큰 단위 lookup 카운터**,
    `prefix_cache_hit_rate = hits/queries`(L82-86). `prompt_tokens_total`(L133) = 실제 prefill한 토큰 누적.
  - `run_hetero_sweep_yunuikang.py`: split을 `queries` 델타로 근사(F/G 한계로 기재됨)·`prompt_tokens` 델타=reprefill.
- **정의 확정(문서화)**:
  - **재프리필량(스래싱 강도)** = `prompt_tokens_total` 델타(실제 prefill 연산). ← 주지표.
  - **hit rate** = `prefix_cache_hits/queries`(토큰 단위 캐시 재사용률). ← 스래싱 억제 성공도.
  - **왜 쟀나**: Eq.6 위반→tool 중 KV evict→다음 턴 전체 히스토리 재프리필, 즉 재프리필=Eq.6 위반의 **관측 가능한 결과**.
  - **용량비와의 인과**: 프로그램 peak KV(§D-char median 2.87GiB) / 백엔드 KV풀(4090 6.03GiB, 5090 12.23GiB)
    → 동시 resident 상한(4090≈2, 5090≈4). resident<offered면 나머지는 pause(tr) 또는 evict-재프리필(default).
- **측정/재분석(대부분 기존 JSONL 재활용, GPU 최소)**:
  - 기존 `hetero_homo_tracelab_{tr,default}.jsonl`·`hetero_hetero_*`에서 **백엔드별 `kv_cache_usage_perc` 시계열,
    동시 resident 프로그램 수(proxy `/health` per_backend total), pause peak, `prompt_tokens` 델타**를 뽑아
    재프리필 대신 **메모리 점유 중심 그래프**로 재작성. (run_hetero_sweep가 이미 kv_usage peak/mean·paused peak 샘플링.)
  - 부족하면 D 재실행(실험 C와 합침)에서 kv_usage를 **더 촘촘히**(interval↓) 샘플링해 시계열 확보.
- **답할 질문**: 용량 얘기를 프리필 없이 메모리로 말할 수 있나? 재프리필과 용량비의 인과 사슬은?
- **증명**: (kv_usage 시계열: default 4090 즉시 ~0.99 포화 vs tr 유지) + (resident 수: tr이 더 적게 유지) +
  (pause량: tr>0, default≈0) 3종으로 "**용량 초과→(tr)pause로 resident 억제 / (default)재프리필 폭증**"을
  메모리 지표만으로 서술. 재프리필 표는 보조.
- **소요**: 손 ~2.5h(재플롯), **GPU 0h**(기존 데이터) ~ +실험 C에 흡수 시 추가 0.

---

## 실험 C — D(실데이터 2×4090)에서 tr 열세 원인을 수치 증명 (핵심, 피드백 d)

**목적**: "tr이 캐시 보호 위해 **활성(resident) 수를 제한→GPU util↓→throughput↓**"를 가설이 아니라
수치·그래프로 입증. D의 tr thru −34%·p95 열세의 인과를 코드 결정(_pause_until_safe→_wait_for_resume)까지 연결.

**설정**: 2×4090(mango1 GPU0+1), 데이터=`tracelab_fit32k.jsonl`(D와 동일). 손실 구간 집중이라
**전체 스윕 대신 C=8·16·32**(D에서 tr이 지기 시작~심화하는 지점) 3회. 프록시 `--profile` + kv_usage 촘촘 샘플링.

### C-1. Latency 분해 (프로파일러 재활용 — 신규 계측 불필요)
- **측정**: tr·default 각각 `--profile`로 `step_profiles.csv` 수집 → per-step `prefill_s/decode_s/pause_s/tool_call_s`
  (profile/state.py: `pause_s`는 on_request_arrive↔on_request_start 차 = **프록시 대기시간** 실측).
- **답할 질문**: tr의 latency 증가분이 **어디서** 오나(prefill? decode? pause 대기?).
- **증명**: tr의 p95 초과분이 **pause_s(대기)**에 몰림 vs default는 prefill_s(재프리필)에 몰림 →
  "tr은 지연이 큐 대기, default는 재프리필"을 분해로 증명. 그래프: `figures/expC_latency_breakdown.png`(스택바).

### C-2. GPU util·resident·idle(starvation) 시계열
- **측정**: 스윕 중 (1) `nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv -l 1`(GPU0/1 각),
  (2) proxy `/health` per_backend **REASONING 수**(=실제 GPU에서 도는 프로그램) 시계열,
  (3) **GPU idle 비율** = REASONING=0인 시간 분율(starvation 지표).
- **답할 질문**: tr에서 GPU가 굶는가(REASONING 프로그램 부족으로 util↓)?
- **증명**: tr의 GPU util·resident가 default보다 낮고 idle 비율↑ → **starvation 정량 증명**. 백엔드별로
  4090 각각. 그래프: `figures/expC_gpu_util_timeline.png`, `expC_resident_timeline.png`.

### C-3. pause/resume 횟수·대기시간
- **측정**: 프록시 로그(`Paused/Resumed` INFO)·`get_program_stats` 폴링으로 pause/resume 카운트,
  C-1의 `pause_s` 분포(mean/p95).
- **증명**: pause 빈도·누적 대기시간이 throughput 손실과 상관. "몇 번 pause가 몇 초 GPU idle을 낳았나" 산출.

### C-4. 인과 노브 (원인 확정 — ablation)
- **실행**: 동일 c=16에서 스케줄러 파라미터를 바꿔 throughput 회복 여부로 **"이 결정 때문"**을 인과 확인:
  - `--use-acting-token-decay` **on/off** (resume 낙관도 변화 → resident 상한 변화).
  - `--acting-token-weight` 조정(예: 1.0→0.5) (ACTING 비용 과소평가 → pause 완화 → resident↑).
  - (선택) `--scheduler-interval` 변화(pause/resume 반응성).
  - ⚠️ **가드레일**: router.py 로직 **미수정**, CLI 노브만. 관측 실험.
- **답할 질문**: pause 공격성을 줄이면(=resident 상한↑) tr throughput이 default 쪽으로 회복되나?
- **증명**: decay-off 또는 weight↓에서 tr thru↑·hit↓ 트레이드오프가 나오면 → "tr 열세의 원인 = 캐시 보호를 위한
  pause(resident 제한)"를 **인과적으로** 확정(단순 상관 아님). 그래프: `figures/expC_knob_tradeoff.png`.

### C-5. NEED vs FIT 격차
- **산출**: **NEED** = GPU를 채우는 데 필요한 동시성(tool-idle 기반: 프로그램이 tool 실행(ACTING)으로 GPU를
  비우는 비율을 고려한 목표 resident) vs **FIT** = 실제 resident 수. §D-char의 프로그램 lifetime·tool 비율로 NEED 추정.
- **증명**: NEED > FIT면 GPU가 놀고 있음 = tr의 pause가 과함. 이 격차가 throughput gap을 설명.

- **종합 증명 서술**: "Eq.6 위반→`_pause_until_safe`가 ACTING pause→요청 `_wait_for_resume` 블록→resident↓→
  GPU idle↑→throughput↓, 대신 캐시 보존→hit↑" — 코드 라인 + C-1~C-5 수치로 end-to-end 인과.
- **소요**: 손 ~1일(스크립트 확장+분석). **GPU ~5–6h**(3 conc × 2 router × 3회 + 노브 ablation; D 전체 8.75h의 절반↓).
  - ⚠️ **GPU 장시간 점유 → 명시 승인 필요.** 기존 tmux `phaseD` 인프라/스크립트 재사용.

---

## 실험 D — SWE-bench (논문 비교 필수, 피드백 f)

**목적**: 논문의 SWE-Agent/OpenHands 워크로드와 정렬해 두 번째 **독립 실제 워크로드**로 결론 검증.
계획서 Phase C(녹화)+D-SWE(스윕)를 이번엔 실행. Docker 세팅 필요.

### D-1. Phase C — SWE-bench Lite trace 녹화 (`--profile`)
- **읽기/준비**: `examples/inference/mini-swe-agent/scripts/setup/setup.sh`, `.../models/vllm_model.py`(program_id 주입).
- **실행**: Docker+mini-swe-agent 준비 → vLLM 1장 + 프록시 `--router default --profile --profile-dir scratch/rec_swebench`
  → `mini-extra swebench --subset lite --split test --workers W --output scratch/swebench_out`(먼저 W=4 파이프라인 검증→확대).
  요청이 프록시(:9000) 통과 + `extra_body.program_id` 부착 확인.
- **정규화**: 신규 `scripts/prep_swebench_trace_yunuikang.py`: `step_profiles.csv` → canonical JSONL
  (`session_id←program_id, turn←step_id-1, input←prompt_tokens, output←completion_tokens, tool←tool_call_s`).
  출력 `scratch/traces/swebench_trace.jsonl` + 사이드카(모델·workers·수집일).
- **답할 질문**: SWE-bench 워크로드의 토큰/tool/KV 분포는 TraceLab과 어떻게 다른가(§10식 characterization)?
- **증명(AC)**: 스키마 검증 + 요약통계 + §D-char식 특성표(TraceLab·합성과 3자 비교).
- **소요**: 손 ~1일(Docker+파이프라인), **GPU ~2–4h**(녹화 규모 의존). Docker 리스크 있음.

### D-2. Phase D-SWE — 스윕 (2×2를 SWE 데이터로 재실행)
- **실행**: `trace_replay_driver`로 `swebench_trace.jsonl` 재생, 2×4090 및 (가능하면) 4090+5090에서
  tr/default 스윕(C 축 D와 동일, 3회). `run_trace_sweep`/`run_hetero_sweep` 재사용.
- **답할 질문**: TraceLab에서 본 결론(hit rate tr 압승, throughput은 KV비율 좌우)이 **두 번째 실데이터에서도** 성립?
- **증명**: SWE-bench에서도 (a) tr hit rate 유지 vs default 붕괴, (b) throughput은 프로그램/KV 비율대로 —
  두 독립 워크로드 재현으로 결론 일반화. 논문 SWE-Agent/OpenHands 경향과 방향 대조(절대수치 비교 금지 원칙 유지).
- **소요**: 손 ~0.5일, **GPU ~6–9h**(스윕). 승인 필요.
- **주의**: Docker/모델 선택 리스크가 크면 D-1만 먼저 하고 D-2는 별도 승인. mini-swe-agent가 안 뜨면 삽질 금지, 블로커 정리 후 멈춤.

---

## 재분석 원칙 (전 작업 공통)

모든 결과를 아래 흐름으로 **재서술**(기존 로그 §D/F/G 해석을 이 틀로 다시 씀, 메커니즘 레퍼런스 인용):

> **tr이 (cost model·policy상) 이렇게 판단** → **이렇게 행동**(pause/resume/배정, 코드 라인) → **그래서 이 현상**(수치/그래프).

- 예) D −34%: "median 18k 프로그램이 4090 KV(43,888tok)에 ~2개(조사 B, §D-char) → c≥8에서 Eq.6 위반
  (Phase 0) → `_pause_until_safe`가 ACTING pause(코드) → 요청 `_wait_for_resume` 블록 → resident↓·GPU idle↑
  (실험 C-2) → throughput↓·pause 대기 latency↑(C-1) → 대신 hit rate 0.77 유지. **decay-off로 pause 완화 시
  회복**(C-4)이 인과 확정."

---

## 실행 순서·승인 게이트 (권장)

| 순서 | 작업 | 손 시간 | GPU 시간 | 승인 |
|---|---|---|---|---|
| 1 | **Phase 0** 메커니즘 레퍼런스 | ~4h | 0 | 불필요(코드/논문) |
| 2 | **조사 A** eviction=재프리필 확정 | ~1.5h | ~0.3h | 짧은 GPU |
| 3 | **조사 B** 메모리지표 재정렬(기존 데이터) | ~2.5h | 0 | 불필요 |
| 4 | **실험 C** tr 열세 인과 증명(핵심) | ~1일 | ~5–6h | **필요(장시간)** |
| 5 | **실험 D-1** SWE 녹화+characterization | ~1일 | ~2–4h | **필요(+Docker)** |
| 6 | **실험 D-2** SWE 스윕 | ~0.5일 | ~6–9h | **필요(장시간)** |

- **1→3은 GPU 없이 즉시 착수 가능**(피드백 a·b·c·e 대부분 여기서 해결). **4가 피드백 d의 핵심 증명.**
- **가드레일 불변**: router.py 로직 미수정(관측/CLI 노브만), `__init__.py` 지연 import 픽스 유지,
  vLLM `--max-model-len 32768 --gpu-memory-utilization 0.92`.
- 각 작업 완료 시 로그에 섹션 추가(설정/명령/결과표/해석/한계) + 그래프 `figures/`.

## 미결 · 사용자 결정 필요
1. **실행 범위**: 1–3(무GPU)만 먼저 하고 검토받을지, 4(실험 C)까지 한 번에 승인할지.
2. **SWE-bench(실험 D)**: 이번에 포함할지(Docker 비용·리스크) vs 다음 미팅 이후로 다시 미룰지. 모델(Qwen3-8B 유지?)·workers·subset 규모.
3. **실험 C 노브 범위**: decay on/off + acting-token-weight만 vs scheduler-interval까지.
4. **인프라**: goguma6(5090)를 실험 C에는 안 씀(2×4090). 실험 D-2 이종까지 갈지.
