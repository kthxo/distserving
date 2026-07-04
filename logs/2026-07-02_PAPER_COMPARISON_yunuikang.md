# 논문 ↔ 우리 실험 정밀 대조 (ThunderAgent)

> 작성: 강윤의 · 브랜치 `yunuikang/thunderagent` · 2026-07-02
> 대상 논문 PDF: `assets/paper/_Arxiv__ThunderAgent.pdf` (28쪽 버전, 본 문서의 모든 인용은 이 파일 기준)
> 대상 실험: `2026-07-02_EXPERIMENT_LOG_yunuikang.md` (§7 일반 워크로드, §9 스래싱 심화, §10 characterization)

---

## 0. 대조 원칙 & 방법 (먼저 읽어주세요)

1. **절대 수치 비교 금지.** 워크로드(우리=합성 sleep 기반 / 논문=SWE-Agent·OpenHands·ToolOrchestra 실제 에이전트)와
   하드웨어(우리=RTX 4090×2 / 논문=8×H100 클러스터 + RTX 5090 1장)가 달라 숫자 직접 비교는 무의미.
   **오직 "경향·메커니즘의 방향"만 대조**한다.
2. **라우터 매핑**: 우리 `default`(단순 최소부하 프록시) ↔ 논문의 **vLLM(request-aware) baseline**,
   우리 `tr`(program-aware) ↔ **ThunderAgent**. **Continuum 축은 우리가 비교하지 않았으므로 다루지 않는다.**
   - ⚠️ 매핑 주의: 논문의 vLLM baseline은 "request-aware **엔진**" 자체다. 우리 `default`는 vLLM 백엔드 위에
     얹힌 **naive 라우팅 프록시**(각 백엔드는 여전히 prefix 캐시 사용)다. 둘 다 "프로그램 단위 용량 인지 없이
     밀어넣어 스래싱"이라는 **동일한 실패 메커니즘**을 갖지만, 완전히 동일한 시스템은 아님(유비).
3. **추정 표기**: 논문에 근거가 있으면 (섹션/그림/쪽) 을 달고, 우리 추론이면 **[추정]** 으로 표시한다.

### ⚠️ 0-1. 출처 정정 (미팅 전 반드시 확인)

지시서에서 지목한 인용 위치 중 **이 PDF 버전과 불일치하는 것**이 있어 바로잡는다. (미팅에서 잘못 인용하지 않도록)

| 지시서에서 언급 | 이 PDF의 실제 내용 | 근거(쪽) |
|---|---|---|
| **§A.5** (working set/heterogeneous) | 부록은 **A.1~A.3까지만 존재**. §A.4·§A.5 **없음** | 목차상 A.1(p19), A.2(p19), A.3(p19), 이후 B·C·D·E·F |
| **Table 3 = H100 vs A100 비교** | Table 3 = **"Program state and status definitions"** (스케줄러 상태 정의표) | p21, Table 3 |
| **Figure 10 = compute-to-bandwidth** | Figure 10 = **"End-to-End latency comparison"** (GLM4.6·Qwen3-235B, mini-SWEAgent·OpenHands, **단일 H100**, 저/고부하) | p26–28, Fig 10 |
| **"compute-to-bandwidth 비율 / A100"** | 논문 전체에 **"A100"·"compute-to-bandwidth" 문구 없음.** 하드웨어는 8×H100 + RTX 5090 1장뿐 | p9 §5.1(l.558–568), p2 Fig 1 caption |
| **"느린 GPU일수록 스래싱 빨라 tr 이점↑"** 실험 | 이 PDF엔 **GPU 세대를 바꿔 스래싱 시점을 비교한 실험이 없음** | 전 부록 확인 |

> **→ 결론**: item 3·4에서 의도하신 논지 자체는 타당하고 **논문에 근거가 실재하지만**, 그 위치는 §A.5/Table3/Fig10이
> **아니라** §4.3.1 Eq.(6) · §4.3.2 · Table 4 다. 아래에서 **정확한 위치로 다시 매핑**해 대조한다.
> 혹시 §A.5가 있는 **다른/최신 버전**을 갖고 계시면 공유해 주시면 item 3·4를 그 버전 기준으로 다시 맞춰드리겠다.

---

## 항목 1 — KV 스래싱 메커니즘

| | 내용 | 근거 |
|---|---|---|
| **논문 주장** | request-level 스케줄링은 각 step을 독립·stateless 요청으로 처리 → 고동시성에서 **tool 실행 중 KV가 evict** → tool 완료 시 **전체 히스토리 재프리필(re-prefill)** → **hit rate 붕괴 → 재프리필 폭증 → throughput 붕괴**. 이 재프리필이 request end-to-end latency를 **최대 7.14× 증가**시킴. 스래싱은 **동시 워크플로 수가 늘수록 심화**. | §3.1 (p4, l.236–244); Fig 1b caption (p2); intro l.110; Fig 5 (p10) "hit rate >90%→≈60%"(l.666) |
| **우리 결과 (§9)** | KV 용량 초과를 강제하니 `default` hit rate **~0.02로 붕괴**, `tr`는 **~0.67 유지**. 총 재프리필 토큰 `default ≈25M` vs `tr ≈2–2.5M` → **약 10× 차이**. p95 latency `default 158s` vs `tr 97s`(C=48). | EXPERIMENT_LOG §9 |
| **판정** | ✅ **방향 일치.** "request/program-unaware → tool 중 evict → 재프리필 폭증 → hit rate·throughput 붕괴"라는 인과 사슬이 우리 환경에서 그대로 재현됨. | |
| **해석/주의** | 논문의 **7.14×는 latency 배수**, 우리 **~10×는 재프리필 토큰 배수** → **서로 다른 물리량**이라 크기 직접 비교 불가(원칙 1). "재프리필이 폭증하고 latency가 치솟는다"는 **경향의 방향만** 일치한다고 말해야 함. 또한 우리 §9의 스래싱은 vLLM `num_preemptions`=0으로, **완료 시퀀스의 prefix-cache 블록 eviction** 형태라 논문이 말한 "acting 중 evict"와 기전이 100% 동일하진 않음(둘 다 재프리필을 유발한다는 상위 메커니즘은 동일). | |

---

## 항목 2 — 부하에 따른 분기 패턴

| | 내용 | 근거 |
|---|---|---|
| **논문 주장** | 스래싱은 **parallel workflow number가 커질수록 심화**되고, baseline은 **메모리 한계를 넘는 순간 throughput이 붕괴(collapse)**하는 반면 ThunderAgent는 그 이후에도 throughput을 유지. | Fig 1 caption "as the parallel workflow number increases"(p2); §3.1 l.241; §5.2 "throughput collapse once the workload exceeds memory limits"(p10, l.670–673) |
| **우리 결과 (§7)** | **저부하(C≤48)**: `tr ≈ default`(자원 여유, 차이 ~0%). **중고부하(C=64~96)**: `tr` 우세 — C=96에서 throughput 17.9 vs 14.1(**+27%**), p95 6.16s vs 8.73s. `default`는 C=64에서 이미 천장(~14 p/s)에 부딪혀 정체. | EXPERIMENT_LOG §7 |
| **판정** | ✅ **방향 일치.** "저부하엔 방법 간 차이가 작고 부하가 오를수록 벌어진다"는 경향 재현. `default`가 먼저 포화하고 `tr`이 더 버팀. | |
| **해석/주의** | 논문 Figure 4의 x축은 이미 24~96(상당한 고부하) 구간이라, "아주 낮은 부하에서 동일"을 **논문 그림이 직접 보여주진 않음** → 이 부분은 우리 §7이 **논문보다 낮은 부하 영역까지 채워** 경향의 시작점을 보강한 셈. [경향 자체는 Fig 1b·§5.2로 뒷받침, 저부하 등가 구간은 우리 데이터의 기여] | |

---

## 항목 3 ★ — §7(안 갈림)과 §9(갈림)의 차이를 논문으로 설명

**우리 관찰**: §7(일반 워크로드)에선 hit rate가 `tr`·`default` 둘 다 **~0.95로 안 갈림**. §9(프로그램별 긴 고유 컨텍스트)에선
`tr 0.67` vs `default 0.02`로 **극적으로 갈림**. 왜?

**논문의 설명 (정확한 위치)**: 논문은 스래싱의 **발생 조건을 부등식으로 명시**한다 —

> **Eq.(6)**: 백엔드 L이 스래싱 상태 ⇔ `C_total < Σ_{p∈L} c_p`
> (`C_total` = 백엔드 KV 풀의 고정 토큰 용량, `c_p` = 프로그램 p의 컨텍스트 토큰 수) — **§4.3.1, p7 (l.379–384)**

즉 **활성 프로그램들의 KV 합이 풀 용량을 넘을 때만** 스래싱이 발생한다. 이걸 우리 두 실험에 대입하면:

| | working set (Σc_p) vs 용량 | 스래싱? | tr vs default |
|---|---|---|---|
| **§7** | 짧은 컨텍스트 → Σc_p가 백엔드 KV 풀(§10 실측 43,888 tok) **안에 수용** → **Eq.(6) 미충족** | ❌ 거의 없음 | hit rate 둘 다 ~0.95, 차이는 **부하분산/스케줄링 효율**에서만 발생 |
| **§9** | 프로그램당 peak **~14,668 tok**(§10), C 몇 개만으로 Σc_p ≫ 43,888 → **Eq.(6) 충족(수십 배 초과)** | ✅ 강함 | **program-aware 용량 제어가 있는 tr만** working set을 용량 내로 유지 → hit rate 갈림 |

- **판정**: ✅ **논문이 정확히 설명함.** "working set이 KV 풀에 들어가면 스래싱이 드물어 tr 이점이 작다"는
  지시서의 취지는 **Eq.(6)의 부등식 그 자체**다(§A.5가 아니라 §4.3.1).
- **보강 근거**: 논문 Appendix D(p23, l.1228–1238)는 "tool call이 짧고 예측가능할 때는 스래싱 회피(=높은 hit rate)가
  throughput을 지배한다"고 서술 → 우리 워크로드(§10에서 확인한 짧은 tool sleep·짧은 output)가 정확히 이 레짐이라,
  **스래싱만 제거하면(=tr) hit rate·throughput이 곧바로 개선**되는 §9 결과와 정합.
- **우리 §10이 이 설명을 정량화**: 4090 KV 풀 43,888 tok, 프로그램 peak ~14,668 tok → **한 장에 ~3개만 적재**.
  §9에서 C=48로 밀면 용량의 **~16배 초과** → Eq.(6)이 큰 폭으로 충족 → 필연적 스래싱. **[논문 부등식 + 우리 실측의 결합]**

---

## 항목 4 ★★ — Heterogeneous 연결 (미팅 핵심)

> 지시서의 "논문 A.5(Table 3/Fig 10, H100 vs A100 compute-to-bandwidth)" 서술은 **이 PDF에 없다**(§0-1).
> 그러나 heterogeneous 연구의 **틈새(gap)를 뒷받침하는 근거는 논문에 분명히 실재**하며, 그 위치는 아래와 같다.
> 이 항목은 미팅 핵심이므로 "논문이 여기까지 봤고, 우리는 여기서 더 나아간다"를 논문 근거로 정확히 세운다.

### 4-1. 논문이 실제로 가정한 것 (= homogeneity 가정의 위치)

1. **Restore는 "용량 있는 아무 백엔드"로.** §4.3.1 Eq.(4)(p6, l.367–369): paused 프로그램을
   *"a backend L′ with available capacity"* 에 배정. **선택 기준은 "여유 용량"뿐.**
2. **재프리필 비용을 node-agnostic으로 가정.** §4.3.2 (p8, l.459–466):
   > *"once a program is paused, its KV cache is assumed to be evicted, making its **recomputation cost node-agnostic**. … The restore policy aligns with **load balancing** rather than strict KV-aware routing, enabling paused programs to be dispatched to **any replica with available memory capacity**."*
   → **핵심**: 논문은 "재프리필 비용이 어느 노드든 같다"고 명시적으로 가정하고, restore 목적지를 **용량·부하 균형**으로만 고른다.
   Cost_unused 상한도 `c_min·Δt`로 **모든 노드에 대칭**으로 잡는다(l.464).
3. **스케줄러가 보는 백엔드 상태에 "속도" 필드가 없음.** Table 4 `BackendState`(p21, l.1187–1193)의 필드 =
   `url, healthy, cache_config(용량), active_program_tokens(현재 토큰)`. → **KV 용량은 추적하지만 compute 처리량·대역폭·prefill 속도는 추적하지 않는다.**
4. **하드웨어는 셋업마다 동질(homogeneous).** §5.1(p9, l.558–568): 서빙/롤아웃은 **전부 8×H100**(또는 2×8×H100),
   ToolOrchestra만 **RTX 5090 1장** — 즉 **한 클러스터 안엔 항상 같은 GPU**. 서로 다른 GPU를 **섞은 실험은 없음**.

**정리**: 논문의 스케줄링은 **"노드들이 서로 교체 가능(interchangeable)"** 이라는 homogeneity 가정 위에 서 있다.
용량 차이는 노드별 `C_total`(Eq.6)로 **부분적으로** 표현 가능하지만, **처리 속도·대역폭 차이는 모델에 아예 없다.**

### 4-2. 우리가 가려는 곳 (= 논문이 안 다룬 heterogeneous 클러스터)

우리 목표: **한 클러스터에 서로 다른 GPU(4090 + 5090)가 섞인** heterogeneous 환경. 같은 모델이므로 **KV/token은 동일(144 KiB)**
이지만(§10), 세 축이 노드마다 다르다:

| 축 | 4090 | 5090 | 근거 |
|---|---|---|---|
| KV 용량(동시 적재 프로그램) | **~3개** (43,888 tok, 6.03 GiB, 실측) | **~6.6개** [추정] (~97,481 tok, 13.39 GiB) | §10-4 |
| prefill/decode 속도 | 느림 | 빠름 | [추정] 하드웨어 스펙 |
| HBM 대역폭 | 낮음 | 높음 | [추정] 하드웨어 스펙 |

이 환경에서 **논문의 두 가정이 깨진다**:

- **가정 ②(node-agnostic recompute)의 붕괴**: 같은 프로그램을 재프리필해도 **4090에선 더 오래** 걸린다 →
  재프리필 비용이 노드마다 다름 → "어디로 restore해도 같다"는 전제 실패. **[논문 §4.3.2 가정에 대한 직접적 반례, 추정 크기]**
- **가정 ①(any replica with capacity)의 비최적성**: 4090에 빈 슬롯이 생기면 논문 정책은 거기로 restore하지만,
  4090은 **용량이 작아(~3개) 금방 다시 Eq.(6)을 넘겨 먼저 스래싱**하고, 재프리필도 느리다 →
  같은 프로그램을 **5090으로 보내는 편이 전역적으로 더 낫다.** 즉 **용량·부하만 보는 restore는 heterogeneous에서 최적이 아님.**
- **결과 [추정]**: 균등/용량기반 분배는 **작은·느린 GPU(4090)를 먼저 스래싱**시키고 큰 GPU(5090)를 저활용 →
  전역 throughput 손실. **필요한 것은 "용량 + 처리속도 + 대역폭에 비례하는(capacity-and-speed-proportional) 라우팅"**,
  이는 논문 global waiting queue가 **가지고 있지 않은** 축이다.

### 4-3. "논문은 여기까지, 우리는 여기서 더" (미팅 문장)

- **논문**: program-aware 스케줄링으로 **동질 클러스터 안에서** KV 스래싱(§4.3.1)과 **노드 간 메모리 불균형**(§4.3.2)을 해결.
  단, restore를 **용량·부하 기준**으로만 하고 재프리필 비용을 **node-agnostic**으로 가정 → **노드가 동질이라는 전제.**
- **우리(gap)**: 노드가 **이질적(4090+5090)** 이면 그 전제가 깨진다. 같은 program-aware 뼈대 위에서
  **노드별 KV 용량·속도·대역폭을 반영한 restore/라우팅**으로 확장하는 것이 우리 연구의 자리.
  §10 실측(4090≈3, 5090≈6.6 프로그램)이 "왜 균등 분배가 안 되는가"의 **정량 근거**를 이미 제공한다.
- ⚠️ 정직성: "느린 GPU가 먼저 스래싱한다"는 **논문이 실험으로 보인 주장이 아니라**, 논문 Eq.(6)(용량 조건) +
  §4.3.2(node-agnostic 가정) + 우리 §10 실측을 근거로 한 **우리의 추론([추정])** 이다. 미팅에선 이렇게 구분해 말하는 게 안전.

---

## 항목 5 — 우리가 재현하지 않은 논문의 기여 (재현 범위 밖)

논문의 3대 기여 중 우리는 **① KV 스래싱만** 재현했다.

| 논문 기여 | 위치 | 우리 재현? | 비고 |
|---|---|---|---|
| **① KV cache thrashing 완화** (program-aware waiting queue) | §3.1, §4.3.1, Fig 1b/5 | ✅ **재현** (§9) | 본 문서 항목 1·3 |
| **② Cross-node memory imbalance** (global queue, dynamic migration) | §3.2, §4.3.2, Fig 2a | ❌ **범위 밖** | 우리는 단일 노드 2×4090 + sticky 라우팅. 노드 간 마이그레이션·불균형(90분간 20%+ 격차, peak 51%) 현상 자체를 만들지 않음. §9에서 본 split 불균형(16.6M/8.9M)은 **라우팅 부작용**이지 논문의 cross-node 현상이 아님 |
| **③ Tool lifecycle 관리** (GC·async env prep) | §3.3, §4.4, Fig 2b/2c, Fig 9 | ❌ **범위 밖** | 우리 tool은 `sleep` 합성이라 Docker/sandbox·디스크 누수·환경 준비 오버랩을 다루지 않음. Fig 9의 tool 시간 heavy-tail도 미재현(우리는 고정 sleep) |

> heterogeneous(항목 4)는 논문 ②(cross-node)의 **연장선**이지만, 논문 ②는 **동질 노드 가정**이므로 우리 heterogeneous는
> ②의 재현이 아니라 **②를 이질 하드웨어로 확장하는 새 문제**로 보는 것이 정확하다.

---

## 6. 한 줄 요약 (미팅용)

- **메커니즘(항목 1)·부하 분기(항목 2)·스래싱 발생 조건(항목 3)** 은 논문의 정성적 경향을
  우리 2×4090 환경에서 **방향 일치로 재현**했다. (절대 수치 비교는 하지 않음)
- **항목 3**의 "§7은 안 갈리고 §9는 갈린다"는 논문 **Eq.(6) 스래싱 부등식**으로 정확히 설명되며,
  우리 §10 characterization(4090에 프로그램 ~3개)이 이를 정량화한다.
- **항목 4(핵심)**: 논문은 **동질 클러스터**에서 restore를 **용량·부하 기준**으로만 하고 재프리필을 **node-agnostic**으로
  가정한다(§4.3.2, Table 4). **이질 GPU(4090+5090)** 에선 이 전제가 깨져 **용량·속도·대역폭 비례 라우팅**이 필요하다 —
  **이 지점이 논문이 다루지 않은 우리 연구의 gap.**

---

## 부록: 논문 하드웨어·구조 팩트체크 (검증용)

- **하드웨어**: 서빙 = **8×H100**(FP8, TP8); RL 롤아웃 = **2×8×H100**; ToolOrchestra(Qwen3-8B, FP16) = **RTX 5090 1장**.
  A100·4090 없음. (§5.1 p9, l.558–568; Fig 1 caption p2) — **한 클러스터 내 GPU 혼합 없음.**
- **baseline**: vLLM(request-aware 엔진), Continuum(tool 시간 예측 기반 KV pinning), vLLM+SGLang Gateway(분산 롤아웃). (§5.1 l.574–581)
- **부록 구성**: A(A.1 KV Cache Optimization, A.2 KV offloading 확장결과, A.3 Scaling up/heterogeneous **allocation**), B(portability), C(tool time 변동성), D(hit rate 해석), E(이론증명), F(E2E latency). **A.4·A.5 없음.**
- **A.3의 "heterogeneous"**: MegaFlow·RollArt 등 **inference/env 분리(disaggregation) 프레임워크**를 논한 것이지 **GPU 이종성**이 아님. (p19, l.1140–1151) — 우리의 GPU heterogeneous와 **다른 의미**이므로 혼동 주의.
- **Figure 1** = throughput/hit rate/speedup vs batch size (8×H100); **Fig 4** = throughput(6개 워크로드); **Fig 5** = KV hit rate; **Fig 7** = LMCache offloading & PD disaggregation ablation; **Fig 10** = per-step E2E latency(단일 H100). **Table 3** = ProgramState/Status 정의; **Table 4** = BackendState 필드.
- **핵심 인용 재확인**: 7.14×(l.110, l.244), Eq.(6) 스래싱 조건(l.379–384), node-agnostic recompute & "any replica with available memory capacity"(l.459–466).
