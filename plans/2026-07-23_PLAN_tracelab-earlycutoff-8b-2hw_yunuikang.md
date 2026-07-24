# 연구 계획 — 원본 full TraceLab(early-cutoff) × Qwen3-8B TP2 × HW 2종으로 flip 궤적 실데이터 검증

> 작성: 강윤의 · 브랜치 `yunuikang/thunderagent` · **2026-07-23** · **플랜만(GPU 기동은 STEP 1 승인 후)**
> HW 2종(같은 문서로 각각): **goguma6 = 2×RTX5090(TP2)**, **nutella = 2×RTX Pro6000(TP2)** · 저장소 `/home/yunuikang/yunuikang_work/distserving`
> 권위 문서(먼저 읽음, 재검토 없이 계승):
> - `logs/2026-07-19_STEPS_RESULTS_yunuikang.md` — **전환점 fit×d\* = 0.62 ±0.03** 확정(84점 본 스윕), 비용모델 `wall ∝ S·W/U`가 **0.625 예측**(오차 0.9%), **최적 정책은 이진**(H1 반증: 중간 f 최적 없음, Table B), tr 신뢰성(전환점 근처/아래 3~10% capacity timeout, default 0%), heavy-tail은 mean-U 모델 한계(§6-5-3).
> - `plans/2026-07-19_PLAN_overcommit-and-duty-tradeoff_yunuikang.md` — 형식·게이트·정직성 톤의 기준. §5-3 측정 프로토콜(참 hit `local_compute`·U 3중·`--stream`·분위수) 계승.
> - `logs/2026-07-16_TP2_RESULTS_yunuikang.md` — P1: fit=KV풀/입력크기가 붕괴 임계, R=k_fit·d ≈ mean nrr(r=0.982). 4090 원점(fit×d=0.46, default 승).
> - `logs/2026-07-17_VLLM_PROFILING_yunuikang.md` — 참 hit 오염 비대칭·batch-token 70GiB 경계·pause heavy-tail.
> 진행중 별도 트랙(무간섭): `logs/2026-07-18_P3_HLE_RESULTS_yunuikang.md`, `logs/2026-07-17_P2_SCIENCE_RESULTS_yunuikang.md`.
> **원칙: 한 번에 한 변수. `scheduler/router.py` 미수정(본 실험은 f=1 tr vs f=∞ default 이진뿐 — overcommit 노브는 STEP 3에서 이미 구현·검증됨, 여기선 양 끝만 사용). 신규 파일 전부 `*_yunuikang`. 원본 트레이스·스크립트 무수정. GPU 기동 전 유휴·타 사용자 확인.**

---

## 0. 한 문단 요약 (연구 목표)

STEP 5/6에서 전환점 fit×d\*=0.62를 **합성 duty trace(단일 ctx 프로파일)**로 확정했다. 남은 두 비판은 (a) "4090 원점(fit×d=0.46)은 트레이스를 인위 capping(session-drop)해서 만든 아티팩트다", (b) "합성 워크로드라 실 heavy-tail에서 성립하는지 불명"이다. 이 plan은 **원본 full TraceLab을 세션 삭제 없이 early-cutoff(누적 컨텍스트가 min(128k, 0.8×C_total) 넘기 직전 step에서 종료)로 두 종류 HW(2×5090·2×Pro6000)·Qwen3-8B·TP2에 올려**, 같은 워크로드·모델로 **HW(=KV 풀 크기=fit)만 바꾸면 승자가 default→tr로 뒤집히는 flip 궤적**을 실데이터로 검증한다. 궤적: **4090(0.46 default) → 5090(~0.8 tr) → Pro6000(~3.3 tr)**. capping 아티팩트 비판은 "모든 세션이 물리적으로 GPU에 들어간다(100% 포함)"로 정면 반박한다.

---

## 1. 배경 근거 (STEP 5/6·P1에서 확정 — 재검토 없이 계승)

| 확정 사실 | 근거 |
|-----------|------|
| **전환점 fit×d\* = 0.62 ±0.03**: <0.62 default(f=∞) 승, >0.62 tr(f=1, program-aware pause) 승 | STEPS §STEP5 본 스윕(84점), 선형보간 fd=0.60→0.65 |
| **비용모델 `wall ∝ S·W/U`가 fd\*=0.625 예측**(실측 0.62, 오차 0.9%). S_tr=1.75·W_def/W_tr=5.86×·U 선형적합 | STEPS §STEP6 §1 |
| **최적 정책은 이진**(f=1 or f=∞) — 중간 f 최적점 부재, H1 반증 | STEPS §STEP5 Table B(6 duty행 전부 f=1 또는 f=∞가 최고 goodput) |
| **전환은 완만**(cliff 아님)·**C-안정**(fit×d가 정책 선택의 충분통계량) | STEPS §STEP5 결론 2·3 |
| **tr 신뢰성 위험**: 전환점 근처/아래에서 tr 3~10% capacity timeout, **default 0%**(전 84 runs) | STEPS §STEP5 증거 5 |
| **참 hit는 `local_compute` 카운터로만**(보고 hit는 default 최대 26배 오염). raw tok/s는 recompute 낭비를 세어 오도 → **goodput(=completed/makespan) 사용** | VLLM_PROFILING §1-2·7-B-5; STEPS §STEP5확장 지표주의 |
| **batch-token 70GiB 경계**: <70GiB→2048/256, ≥70GiB→8192/1024. **본 실험은 노브 핀으로 2048/256 고정**(교란 제거) | VLLM_PROFILING §1-5 |
| 4090 원점 fit×d=0.46 → default 승(−34%). 방향이 5090 본 스윕 fd=0.50(default +12%)과 일치 | STEPS §STEP5 결론 4 |

**이 plan의 신규 각도**: STEP 5/6은 **duty(d)를 합성으로 흔들어** 전환점을 잡았다. 이번엔 **워크로드·모델 고정, HW만 흔들어**(fit을 KV 풀 크기로 스캔) 같은 전환점을 **실 heavy-tail 데이터**에서 재현한다. 이는 STEP 6 §5-3이 남긴 한계("heavy-tail은 mean-U 모델 과대 추정 가능")를 실측으로 검증·보정하는 자리이기도 하다.

---

## 2. prep 스크립트 감사 (STEP 2 선결 질문 — ★ 확인 완료)

> 사용자 지시: "먼저 기존 prep_tracelab_yunuikang.py가 '누적 컨텍스트 넘기 직전 step에서 truncate'를 지원하는지 확인."

| 항목 | 결과 | 근거(파일:라인) |
|------|------|-----------------|
| `--max-input-tokens` | **세션 삭제(session-drop)** — 어느 턴이든 입력이 cap 초과면 **세션 전체를 버림** | `prep_tracelab_yunuikang.py:93-95` `max(...) > cap → continue` |
| early-cutoff(누적 넘기 직전 truncate) | **미지원** | 위 로직만 존재. 턴 단위 절단 코드 없음 |
| tool>300s clamp | **지원(재사용 가능)** | `:102-103` `td = min(td, cap_tool_s)` |
| reasoning 포함 | 지원 | `:99` `--include-reasoning` |

**★ 판정**: early-cutoff는 **신규 격리 모드를 추가해야 함**(STEP 2). 세션 삭제 모드(`--max-input-tokens`)와는 **의미가 정반대**(삭제 vs 앞부분 보존). tool clamp는 기존 `--cap-tool-s 300` 재사용. 원본 `prep_tracelab_yunuikang.py`는 **무수정** — 신규 스크립트 `prep_tracelab_earlycutoff_yunuikang.py`로 격리하거나 신규 서브커맨드/모드 플래그로 추가(원본 함수 재사용, 원본 파일 미변경).

---

## 3. 공통 뼈대 vs HW별 값 (두 HW 같은 문서로 실행)

이 plan은 **공통 프로토콜 + HW별 값 표**로 구성된다. HW별 값은 **STEP 1 실측으로 채운다**(아래 표의 `TBD`). 두 HW(goguma6 5090, nutella Pro6000)에서 **같은 STEP 1~4를 각각** 돈다. plan 확정 후 nutella로 복사해 양쪽 실행.

| 기호/파라미터 | 정의 | 2×5090 (goguma6) | 2×Pro6000 (nutella) | 채움 시점 |
|---------------|------|-------------------|----------------------|-----------|
| C_total | KV 풀 = block_size×num_gpu_blocks (기동 로그) | **298,400 ✅실측** | **TBD** (예상 ~1.1M) | STEP 1 |
| 모델 윈도우 | Qwen3-8B 네이티브 max_position_embeddings | **40,960 ✅**(128k 아님!) | 40,960 | STEP 1 |
| ctx | 프로그램당 peak input median (early-cutoff 후) | L=40k→**36,308** / L=128k→**65,678** ✅ | ~동일(윈도우 공유 시) | STEP 2 |
| fit | C_total / ctx | L=40k→**8.2** / L=128k→**4.5** ✅ | **TBD** (예상 ~16) | STEP 1+2 |
| early-cutoff 한계 L | min(모델윈도우, 0.8×C_total) | **40,960**(네이티브) 또는 131,072(YaRN) — ★결정 필요 | 동상 | STEP 1 |
| d | reasoning/(reasoning+tool), c=1 실측 | **TBD**(c1 proxy≈0.47, 300s clamp로 상승) | **TBD** | STEP 4 |
| fit×d | 무-스래싱 R 최대치 | **TBD**(L·d 의존, 아래 §5-9) | **TBD** (예상 2.4~4.0) | STEP 4 |
| C 그리드 | fit을 걸치도록 | L=40k→{4,8,16,32} / L=128k→{2,4,8,16} | {8,16,32,48} | STEP 3 |
| max_num_batched_tokens | 노브 핀 | **2048 ✅** | 2048 | STEP 1 확인 |
| max_num_seqs | 노브 핀 | **256 ✅** | 256 | STEP 1 확인 |

> ※ TP2에서 `max_num_batched_tokens` 기본값은 world_size에 따라 달라질 수 있음(VLLM_PROFILING §7-B-1은 world_size=1 기준 2048). Pro6000(96GB×2)은 device mem이 70GiB 경계를 넘어 **8192/1024로 기본 전환될 위험** → STEP 1에서 기동 로그로 확인하고, 교란 제거를 위해 **명시 플래그 `--max-num-batched-tokens 2048 --max-num-seqs 256`로 양쪽 핀**(사용자 노브 지시와 일치). 5090은 `compile_ranges_endpoints=[2048]` 확인(오버라이드 없음), dtype=bfloat16(FP8 아님).

---

## STEP 0 — full 트레이스 분포 (이미 완료 · 재사용)

> `scripts/inspect_tracelab_full_yunuikang.py`, `scratch/traces/tracelab_trace_full.jsonl`(357,161턴, meta 확인). HW·모델 무관이라 그대로 유효.

- 4,265 세션 / 357,161 턴. peak input/프로그램 **median 67,572 · max 999,888**.
- tool **median 0.169s · max 154,089s(42.8h) · >300s 0.65% · >3600s 0.028%**.
- **함의**: (a) ctx(fit 분모) ≈ 67,572 → HW별 fit는 C_total로 결정. (b) tool 42.8h outlier가 wall-clock을 폭발시킴 → **>300s clamp**(전체 0.65%만, heavy-tail·턴 순서 보존)로 제거. (c) peak median 67,572 < 128k라 **early-cutoff 한계(128k)에 걸리는 건 소수 whale뿐** → early-cut 비율 STEP 2에서 실측(예상 ~25% 세션이 후반 턴 일부 절단).

---

## STEP 1 — HW 스코핑·C_total 실측 (각 HW, GPU) 【게이트 1】

### Q. 질문
> **각 HW에서 8B FP16 TP2를 기동할 수 있는가? C_total은? fit·early-cutoff 한계·batch 노브 레짐은?**

### 절차 (각 HW 동일)
1. **유휴·타 사용자 확인**: `nvidia-smi` — 2장 유휴(0%, 프로세스 없음) 확인. **아니면 정지·보고**(GPU 기동 금지).
2. **환경 확인**: venv·vLLM·PyTorch·Qwen3-8B 캐시·`router.py` baseline(미수정) — STEPS §STEP1 절차 재사용. Blackwell(5090 sm_120) 환경변수(`VLLM_USE_FLASHINFER_SAMPLER=0`, `VLLM_ATTENTION_BACKEND=FLASH_ATTN`, `CPATH`) 확인.
3. **신규 격리 serve 스크립트** `scripts/_serve_vllm_8b_tp2_yunuikang.sh`(기존 `_serve_vllm_tp2_yunuikang.sh` 참고, **원본 무수정**): Qwen3-8B **FP16 유지**(weights+KV, FP8 아님), **TP2**, `--max-model-len 131072`(128k, early-cutoff 한계와 정합), `--gpu-memory-utilization 0.92`, **`--max-num-batched-tokens 2048 --max-num-seqs 256` 명시 핀**.
4. **C_total 실측**: 기동 로그 `GPU KV cache size: N tokens`(kv_cache_utils.py) 기록. weights·overhead도 로그에서.
5. **파생**: fit = C_total/67,572, early-cutoff 한계 = min(131072, 0.8×C_total), batch 노브 2048/256 실제 적용 확인(기동 로그 `EngineArgs`).
6. **추론 확인**: `curl /health` + 1 completion.

### 참고 예상(실측으로 확정)
- 2×5090 8B FP16 C_total **~280k**(단일 5090 89,040의 대략 3배+; TP2로 weights 분산·KV 2배 풀) → fit ~4.1 → fit×d ~0.6~1.0 = **전환점 근처**.
- 2×Pro6000 8B FP16 **~1.1M**(96GB×2, 8B weights 작아 KV 방대) → fit ~16 → fit×d ~2.4~4.0 = **deep tr**.
- 8B는 양쪽 다 0.8×C_total > 128k → **early-cutoff 한계 = 128k(모델 윈도우)로 수렴 예상** → 확인.

### 산출물 / ★ 게이트 1
- `scripts/_serve_vllm_8b_tp2_yunuikang.sh`(신규). §3 HW 값 표의 C_total·fit·early-cutoff 한계·batch 노브 칸 채움.
- **정지·보고**. STEP 2(GPU 불필요) 착수는 승인 후. (기동은 이 STEP이 최초 GPU 사용 — 유휴 확인 필수.)

---

## STEP 2 — early-cutoff prep 구현·검증 (GPU 불필요) 【게이트 2】

### Q. 질문
> **원본 full 트레이스를 "세션 삭제 없이, 누적 컨텍스트가 한계를 넘기 직전 step에서 종료"로 정규화할 수 있는가? early-cut 비율은?**

### 구현 (신규 격리, 원본 `prep_tracelab_yunuikang.py` 무수정)
- 신규 `scripts/prep_tracelab_earlycutoff_yunuikang.py`(또는 원본에 **읽기 전용 재사용**하는 신규 모드 함수). 로직:
  - 세션별 턴을 round_index 정렬. `input_tokens`(누적 컨텍스트)가 **한계 L=min(128k, 0.8×C_total)** 를 **넘기 직전 턴까지만 보존**, 그 이후 턴은 **버림(세션 전체 삭제 아님)**. 내용 편집·요약 금지 — 앞부분 턴을 원본 그대로.
  - `input_tokens > L`인 **첫 턴 직전에서 절단**. 첫 턴부터 이미 L 초과인 세션(존재하면)은 최소 1턴 보존 정책 명시(예상: median 67,572 < 128k라 거의 없음).
  - **tool>300s clamp**: 기존 `--cap-tool-s 300` 로직 재사용(값만 clamp, 턴 제거 아님).
  - 마지막 보존 턴의 `tool_duration_s=0`(trailing tool wait 없음, 원본 규약 계승).
- **세션 삭제(`--max-input-tokens`)와의 차이 명시**: 삭제 모드는 whale 세션을 통째로 버려 **분포를 왜곡**(capping 아티팩트). early-cutoff는 **전 세션(100%) 포함**, whale은 앞부분만 보존 → "모든 세션의 앞부분"으로 프레이밍(§한계).

### 검증
- `schema_ok`(기존 validator 재사용: 필드·turn 단조·양수 input).
- **early-cut 비율**: (절단된 세션 수)/(전 세션), (버려진 턴 수)/(전 턴). 예상 ~25% 세션이 후반 일부 절단.
- **분포 보존 확인**: 절단 후 peak input median이 여전히 ~67,572(변동 없음, whale만 128k로 수렴), tool 분포 heavy-tail 보존(median 0.169s).
- L은 HW별로 다를 수 있으나 8B 양쪽 128k 수렴 예상 → **한 번 생성으로 양 HW 공유 가능**(STEP 1 확인 후 확정).

### 산출물 / ★ 게이트 2
- `scripts/prep_tracelab_earlycutoff_yunuikang.py`(신규), `scratch/traces/tracelab_earlycutoff_128k_yunuikang.jsonl` + `.meta.json`(early-cut 비율 포함).
- **정지·보고**(schema_ok + early-cut 비율 + 분포 보존). STEP 3(GPU 스윕) 착수는 승인 후.

---

## STEP 3 — default vs tr 스윕 (각 HW, GPU) 【게이트 3】

### Q. 질문
> **early-cutoff full 트레이스를 각 HW에 replay 시, C 그리드 전반에서 tr(f=1) vs default(f=∞)의 goodput·p95·참 hit·U·실패율은? 어느 쪽이 이기는가?**

### 설계
- 정책: **f=1 tr vs f=1e6 default 이진**(STEP 3 overcommit 노브의 양 끝, 중간 f 없음 — H1 반증 계승). `router.py` 무수정.
- **C 그리드(STEP 1 fit 걸치게)**: 5090 fit~4 → **C{2,4,8,16}**; Pro6000 fit~16 → **C{8,16,32,48}**. (C<fit 음성대조 + C>fit 활성.)
- REPEAT=3(에러바).

### 측정 프로토콜 (STEP 5 계승 — 필수)
- **vLLM restart + clean prefix cache per point**(각 점 독립, 캐시 오염 방지).
- **참 hit = `vllm:prompt_tokens_by_source{source="local_compute"}`**(불변식 compute+cached==total 확인), 보고 hit 병기.
- **U 3중**: proxy nrr(REASONING>0) · `nvidia-smi dmon 1s` · mem — 삼각측량.
- **goodput = completed/makespan**(prog/s). raw tok/s는 recompute 낭비 오도 → 안 씀(병기만).
- **`--stream` 필수**(prefill_s/decode_s 기록).
- **p50/p95** 분위수, **tr paused(mean/max)**(heavy-tail 착시 주의).
- **tr/def fail rate**(capacity timeout) — tr 신뢰성 지표.
- 기동 로그 C_total·batch 노브 매 점 확인(런타임 변동 기록).

### 러너 (신규 격리)
- `scripts/sweep_earlycutoff_2hw_yunuikang.py`(기존 `sweep_main_yunuikang.py` 참고, **원본 무수정**). closed-loop 드라이버로 early-cutoff 트레이스 replay.
- **★ 스케일/런타임 정직 caveat(사용자 결정 필요)**: full 4,265 세션 × C 그리드 × 2정책 × R3를 매 점 전량 replay하면 점당 수 시간~수십 시간(heavy-tail). **선택지**: (a) 벽시계 예산 고정(점당 N분 후 makespan 산출), (b) **peak-input CDF 보존 층화 서브샘플**(예 300~500 세션, 100% 프레이밍은 "포함 가능성" 근거로 유지하되 스윕은 대표 표본), (c) 전량(시간 허용 시). **게이트 3 전 사용자 결정** — 기본 제안: (b) 층화 서브샘플(분포 보존) + 전량 1점 spot-check로 정합.

### 산출물 / ★ 게이트 3
- `scripts/sweep_earlycutoff_2hw_yunuikang.py`, `scratch/step_ec/<hw>/sweep_results.jsonl`, per-run turns/vllm/ta/nvsmi 로그.
- **원시 표 보고**(C별 tr/def goodput·p95·hit·U·fail). **정지**. STEP 4(분석) 착수는 승인 후.

---

## STEP 4 — d 실측·fit×d 산출·flip 검증·비용모델 대조 (분석) 【게이트 4】

### Q. 질문
> **각 HW의 fit×d는? 전환점 0.62 예측과 승자(goodput·p95)가 일치하는가? flip 궤적(4090→5090→Pro6000)이 실데이터로 성립하는가?**

### 절차
1. **d 실측**: 각 HW에서 early-cutoff 트레이스 **c=1 replay** → reasoning/(reasoning+tool). tool 300s clamp·8B 속도로 변동 → 여기서 확정.
2. **fit×d 산출**: STEP 1 fit × STEP 4 d. §3 표 채움.
3. **flip 검증**: fit×d를 0.62와 대조 → 예측 승자(default if <0.62 else tr) vs 실측 승자(STEP 3 goodput·p95). 두 HW + 4090 원점(0.46)으로 **궤적 표**.
4. **비용모델 대조**: `wall ∝ S·W/U`(S_tr·W_def/W_tr·U는 STEP 3 실측) → 예측 wall ratio vs 실측. **heavy-tail에서 mean-U 모델이 과대 추정하는지**(STEP 6 §5-3 한계) 정량.
5. **레짐 지도 셀 추가**: `figures/step5_transition_yunuikang.png`(또는 신규 오버레이 그림)에 실데이터 셀 2개 오버레이. 결과 로그 append.

### 예상 결과 (§예측)
- **2×5090(fit~4, fit×d~0.6~1.0)**: 전환점 근처 → **tr 근소~중간 승(+10~40%)**, 전환점 근처라 **tr 3~10% capacity timeout 가능**.
- **2×Pro6000(fit~16, fit×d~2.4~4.0)**: deep tr-zone → 고-C에서 default 붕괴 시 **tr 압도(+100~200%)**, 저-C(C<fit)는 음성대조(tr≈default 또는 근소).
- **궤적**: 4090(0.46, default) → 5090(~0.8, tr) → Pro6000(~3.3, tr) = **HW만 키워 flip + tr 단조 우위**.

### 산출물 / ★ 게이트 4
- 분석 스크립트 `scripts/analyze_earlycutoff_flip_yunuikang.py`(신규), 궤적 그림, `logs/2026-07-19_STEPS_RESULTS_yunuikang.md`에 **append**(또는 신규 결과 로그 `logs/2026-07-23_EARLYCUTOFF_2HW_RESULTS_yunuikang.md`).
- **정지·보고**. 논문 정리/추가 셀은 승인 후.

---

## 4. 예측 (plan §예측 — STEP 4에서 대조)

| HW | 예상 C_total | 예상 fit | 예상 d | 예상 fit×d | 예측 승자 | 예측 tr fail |
|----|-------------|---------|--------|-----------|-----------|-------------|
| 4090(원점) | 43,888(실측) | 2.35 | 0.196 | **0.46** | default(−34% 실측) | — |
| 2×5090 | ~280k | ~4.1 | 0.15~0.24 | **~0.6~1.0** | **tr 근소~중간(+10~40%)** | 3~10%(전환점 근처) |
| 2×Pro6000 | ~1.1M | ~16 | 0.15~0.24 | **~2.4~4.0** | **tr 압도(+100~200%)** | ~0%(deep zone) |

→ **HW만 키워 default→tr flip**. 전환점 0.62를 5090이 걸침(근소 승 or 근처), Pro6000이 깊이 넘김(압도).

---

## 5. 정직 기록 (§한계)

1. **C_total·d 실측 전 예측**(fit×d ±). d는 8B 빠름 + tool 300s clamp로 변동 → **STEP 4 확정**. 5090 예상 fit×d~0.8은 전환점(0.62) 위지만 **근소**라 승패 마진이 작을 수 있음(전환은 완만, STEPS §STEP5 결론 2).
2. **cross-method**: 4090 원점은 **session-drop**(capping), 신규는 **early-cutoff** → 방법이 다름. 방향(default 승) 일치가 핵심이나, 엄밀 정합을 원하면 **4090 early-cutoff 재run**(선택적 확장).
3. **"전체 데이터"=세션 100% 포함**이나 whale 후반 턴은 128k에서 잘림 → **"모든 세션의 앞부분"으로 프레이밍**(session-drop이 세션을 통째 버리는 것과 대비). early-cut 비율(STEP 2) 명시.
4. **heavy-tail vs mean-U 비용모델**: 이 워크로드는 STEP 6 §5-3이 "mean-U 모델 과대 추정 가능"으로 flag한 바로 그 heavy-tail 영역 → **검증이자 잠재적 모델 보정(tail-aware U)** 자리. 예측 wall ratio 오차가 커지면 그 자체가 유효 결과.
5. **스윕 스케일**: full 4,265 세션 전량 replay는 점당 수 시간 → 서브샘플/벽시계예산 결정(STEP 3 게이트). 서브샘플 시 "100% 포함"은 **물리적 적재 가능성**(early-cutoff 보장) 근거로 유지하고, 스윕은 분포 보존 대표 표본임을 명시.
6. **TP2 batch 노브**: Pro6000(96GB×2)은 70GiB 경계 넘어 8192/1024 기본 전환 위험 → **명시 핀 2048/256**으로 교란 제거(STEP 1 확인). 4090/5090 레짐과 배치 예산 정합.
7. **신규 둘 다 tr-zone**(fit×d>0.62 예상): default-zone(<0.62) 실데이터 점은 없음 → 필요 시 **`--gpu-memory-utilization` 축소로 KV 풀 인위 축소**(HLE에서 검증된 기법)로 fit↓ → fit×d<0.62 점 확보(선택적 확장).
8. **ctx=peak input median 근사**: 실제 KV는 prefix 공유·shared_tokens로 변동 → fit은 차수 판정용(STEP 2 §2-8 계승).

### ★ STEP 1/2 실측으로 드러난 프레이밍 정정 (2026-07-23)
9. **모델 윈도우 = 40,960 ≠ 128k**(Qwen3-8B `max_position_embeddings=40960`). 확정 프레이밍의 "모델 윈도우 128k"·"0.8×pool>128k라 한계=128k 수렴"은 **오류**. 128k는 YaRN rope-scaling(비-기본, factor≈3.2)을 켜야만 가능. 따라서 early-cutoff 한계 L은 **(A) 네이티브 40,960** 또는 **(B) YaRN 131,072** 중 결정 필요. C_total(298,400)의 0.8배=238,720이라 **모델 윈도우가 항상 바인딩**(구조는 프레이밍대로이나 숫자가 40,960).
10. **"전 세션 100% 포함" 불성립** — **첫 턴(turn 0) 입력이 윈도우를 초과하는 세션**은 단일 요청이 max_model_len 초과라 vLLM이 거부(내용 편집 금지). 실측 포함률: **L=40,960 → 92.3%**(330 드롭) / **L=131,072 → 97.1%**(123 드롭). → 프레이밍을 "**첫 프롬프트가 윈도우에 맞는 세션 전부 포함(N% 드롭은 첫 프롬프트가 윈도우 초과)**"로 정정.
11. **early-cut 비율 ~25% 예상은 L=128k에서만 성립**: L=131,072 → 세션 절단율 **23.1%**·턴 보존 53%(예상 부합). L=40,960 → 절단율 **68.3%**·턴 보존 **10.9%**(대폭 초과, capping에 가까움) → 40k 채택 시 "아티팩트 반박" 힘 약화.
12. **full 트레이스 replay 비현실적(★ 서브샘플 필수)**: 24점 그리드(C4×정책2×R3) 전량 replay 추정 = **40k 트레이스 ~567 GPU-h / 128k 트레이스 ~3,522 GPU-h**(Σtool만 각 52.7h·333.6h, 단일 최장 세션 E2E 2.4h·14.8h가 점당 하한). → 고정 seed 층화 서브샘플(peak-input CDF 보존) 필수, 128k는 Σtool이 커 특히 무거움.
13. **c=1 proxy d≈0.47**(tool 300s clamp가 heavy-tail 제거→듀티 상승): 구 capped TraceLab d=0.196보다 높음 → 5090이 "전환점 근처(~0.8)"가 아니라 **명확한 tr-zone**(fit×d≈1.4~3.9)일 가능성. STEP 4 실측이 확정(현재는 러프 레이트 기반 proxy).

---

## 6. 하드웨어·무간섭·가드레일

- **HW**: goguma6(2×5090), nutella(2×Pro6000). **GPU 기동 전 매번 `nvidia-smi` 유휴·타 사용자 확인** — 아니면 정지·보고. nutella는 진행중 P2/P3(tp2serve) 트랙과 자원·시간대 경합 주의 → **STEP 1에서 여유 GPU 확인, 없으면 정지**.
- **router.py 미수정**: 본 실험은 f=1 tr vs f=∞ default 이진뿐(overcommit 노브는 STEP 3에서 구현·게이트 B 통과 완료, 여기선 양 끝만 사용).
- **신규 파일 전부 `*_yunuikang`**. **원본 트레이스(`tracelab_trace_full.jsonl`)·원본 스크립트(`prep_tracelab_yunuikang.py`·`sweep_main_yunuikang.py`·serve 스크립트) 무수정** — 전부 신규 격리 복사/모드.
- **한 번에 한 변수**: STEP 1(C_total)·STEP 2(early-cutoff)·STEP 3(스윕)·STEP 4(분석) 각 게이트 정지.
- **plan 확정 후 nutella로 복사**해 양쪽에서 실행.

---

## 7. 신규 스크립트 (예정 — 구현 아님)

| 스크립트 | STEP | 용도 |
|----------|------|------|
| `scripts/_serve_vllm_8b_tp2_yunuikang.sh` | 1 | 8B FP16 TP2 격리 serve(batch 노브 핀) |
| `scripts/prep_tracelab_earlycutoff_yunuikang.py` | 2 | early-cutoff 정규화(원본 무수정) |
| `scripts/sweep_earlycutoff_2hw_yunuikang.py` | 3 | tr vs default 스윕 러너 |
| `scripts/analyze_earlycutoff_flip_yunuikang.py` | 4 | d·fit×d·flip·비용모델·그림 |

---

## 8. 단계 의존성·게이트

```
STEP 1 (각 HW C_total 실측, GPU) ──[게이트 1]── ┐   ← 유휴 확인 후, 승인 후 착수
STEP 2 (early-cutoff prep, GPU 불필요) ─[게이트 2]┤   ← STEP 1 C_total(한계 L) 후
STEP 3 (tr vs default 스윕, GPU) ──[게이트 3]───┤   ← STEP 1∧2 후, 서브샘플 결정
                                                ▼
STEP 4 (d·fit×d·flip·비용모델, 분석) ──────[게이트 4]
```
각 STEP·각 HW마다 정지·보고. GPU 기동(STEP 1·3)은 유휴 확인 + 승인 후.

---

**→ plan만 작성. STEP 1(GPU 기동) 착수는 승인 후. 정지·보고.**
