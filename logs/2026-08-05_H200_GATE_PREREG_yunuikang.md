# 사전 등록 — §7.1b fit 게이트 (H200)

- 작성: 2026-08-05 · 브랜치 `mori` · **이 문서는 F1 기동 *전에* 커밋된다. 커밋 타임스탬프가 사전 등록의 증빙이다.**
- 대상 계획: `plans/2026-08-04_PLAN_h200-rescale-reproduction_yunuikang.md` **rev3** (§5.1 Phase 0 · 리스크 7.1b/7.5/7.6)
- 신규 파일만 추가. 기존 스크립트·트레이스·baseline **0-line diff**.
- 라벨: **[측정]** 이 머신/파일에서 직접 확인 · **[추정]** 계산·가정

> ⚠️ 이 문서의 임계값과 probe 부하 사양은 **실행 전에 고정**된다. 결과를 본 뒤 어느 것도 바꾸지 않는다.
> 계획서 §6.3/§6.4의 판정 기준과는 별개이며, 그쪽은 이 게이트가 건드리지 않는다.

---

## 0. 이 게이트가 답하는 것

리스크 7.1b: *"`--max-total-tokens`가 안 먹거나 다른 값으로 착지 → fit 스윕이 성립 안 함 = 계획 전체 무효."*

기동 로그 한 줄(`max_total_num_tokens=N`)은 **엔진이 N이라고 말한다**를 확인할 뿐,
**할당기가 N을 강제한다**는 확인하지 못한다. 그래서 선언 → 교차출처 → 물리 → 장부 → **행동** 순으로 쌓는다.

## 1. 실행 전 실측 근거

| 항목 | 값 | 출처 |
|---|---|---|
| GPU | H200 SXM ×1 · **143,771 MiB = 140.40 GiB** · driver 580.159.03 (CUDA 13.0) | [측정] `nvidia-smi` |
| torch / sglang | 2.9.1+cu128 / **0.5.10** · transformers **5.3.0** | [측정] |
| **컨테이너 메모리 한도** | **`/sys/fs/cgroup/memory.max` = 1,101,871,972,352 B = 1,026 GiB** (현재 사용 43.7 GiB) | [측정] |
| ~~`free -g` 3,023 GiB~~ | **오독. 호스트 전체 값이고 컨테이너는 cgroup을 못 본다 — 이 수치는 쓰지 않는다.** | 정정 기록 |
| NUMA | 2노드 · **GPU0 = node 0** (cpu 0-55,112-167) · 거리 10/21 | [측정] `numactl -H` |
| 모델 config | 28L · 4kv · head_dim 128 → **56 KiB/tok** · `max_position_embeddings` 32,768 · `rope_theta` 1e6 · `rope_scaling`/`rope_parameters` **둘 다 없음** | [측정] `config.json` |
| YaRN | factor **2.1875** × 32,768 = **71,680** = `--context-length` | [측정] 계산 |
| ctx median | **32,376** = `median(input_tokens)`, 117,257턴 / 3,514세션 | [측정] 트레이스 직접 재계산 |

**DRAM 결론**: F4의 host tier 69.2 GiB + weights 14.19 GiB는 **1,026 GiB 한도 안에서 여유**.
계획서 §4.3/§8.1의 128 GiB 티어 제약은 이 머신에서 **구속력이 없다.** `r=2` 고정은 자원 사정이 아니라
5090 Phase 2의 실측 근거(§1.2)에 따른 것이므로 그대로 유지한다.

**`FIT_DEN = 32,376`을 고정하는 근거** [측정]: 트레이스는 텍스트가 아니라 **정수 토큰 수**(`input_tokens`)를
저장하고, 드라이버는 그 값을 목표치로 삼아 tokenizer를 padder로만 쓴다
(`mori_replay_driver_yunuikang.py:95,233` → `trace_replay_driver_yunuikang.py:79 Padder`).
따라서 ctx median은 **tokenizer 무관**이며 Qwen2.5-7B에서도 동일하다. 이 머신에서 재계산해 32,376을
정확히 재현했다. 5090과 같은 분모를 쓰는 것이 F1↔5090 C80 비교의 전제이므로 **변경하지 않는다.**
tokenizer가 개입하는 유일한 지점은 padder의 실현 오차뿐이고, 그것은 P-e로 기록한다.

## 2. `--max-total-tokens` 의미 [측정, sglang 0.5.10 소스]

`model_executor/model_runner_kv_cache_mixin.py:808-838`:

```
capacity = min(profiled_tokens, user_limit)      # 캡 전용 — 올릴 수 없다
capacity = capacity // page_size * page_size     # page 정렬 floor
```

요청 > 자연 풀이면 `"max_total_tokens=... is larger than the profiled value"` 경고 후
**자연 풀을 쓴다** → 게이트는 이 경고를 **FATAL로 취급**한다(G1.4).

기동 로그 형식은 `managers/scheduler.py:691`, 독립 게이지는
`sglang:max_total_num_tokens`(`observability/metrics_collector.py:267`),
I6 장부는 `sglang:cache_config_info{page_size,num_pages}`(〃:793,1087).

## 3. 사전 등록 상수 (frozen)

`scripts/fit_gate_yunuikang.py`의 `PREREG` 딕셔너리와 **일대일로 일치**하며, 게이트는 매 판정 레코드에
이 딕셔너리를 통째로 기록한다.

| 상수 | 값 | 근거 |
|---|---|---|
| `FIT_DEN` | **32,376** | 위 §1 |
| `KV_KIB_PER_TOK` | 56 | config 실측 |
| `TOL_PCT` | **±5%** | 계획 §5.1 Phase 0 |
| `FIT_MAX` | **30** | 계획 리스크 7.6 |
| `CONTEXT_LEN` | 71,680 | 계획 §5.2 |
| `HOST_TOL_PCT` | ±2% | 5090 `run_phase2_rsweep`의 기존 assert와 동일 |
| `PROBE_N_REQ` | **13** | 13 × 32,376 = 420,888 = **1.60 × N** (F1) |
| `PROBE_PROMPT_TOK` | **32,376** | ctx median — probe를 레짐 위에 둔다 |
| `PROBE_CONCURRENCY` | 4 | |
| `PROBE_MAX_NEW_TOKENS` | 8 | 출력은 검증 대상이 아니다 |
| `PROBE_SAMPLE_HZ` | 1.0 | |
| `P_B_FRAC` | **0.80** | §4 참조 — **판정 축**이다 |
| `SLOPE_TOL` | ±0.05 | G6 |

## 4. 판정 항목

### G0 부팅 전제
`/health` · `/get_model_info` 모델 = Qwen2.5-7B-Instruct · `tp_size == 1` ·
로그 `context_len == 71,680`(**YaRN이 실제로 먹었는지**. 32,768로 착지하면 워크셋이 잘려 fit 정의가 흔들린다)

### G1 선언값
1. 로그 `max_total_num_tokens=N` → `fit = N / 32,376`
2. `|N − MAXTOK| ≤ 5%`
3. `N ≤ MAXTOK` (캡 의미상 초과 불가)
4. `fit ≤ 30`
5. **`"is larger than the profiled value"` 경고 부재**

### G2 4출처 장부 일치
로그 = `sglang:max_total_num_tokens` = `cache_config_info{page_size × num_pages}`(**I6**) =
`/get_server_info`. 그리고 `N == floor(MAXTOK / page_size) × page_size` — **잔차가 page 정렬로 완전히 설명될 것.**

### G2b 물리 VRAM — **WARN 전용, 차단하지 않는다**
`nvidia-smi` used vs `weights 14.19 + N×56KiB`. F1 기대 ≈ 30~48 GiB.
**차단하지 않는 이유**: `--mem-fraction-static`이 캡과 무관하게 선예약할 수 있고, 그러면 실험은 멀쩡한데
게이트만 거짓 FAIL을 낸다. 유효한 계획을 거짓 FAIL로 죽이지 않기 위해 **기록만 하고 판단은 G4에 맡긴다.**

### G3 host tier (RATIO>0 셀만)
`hicache_host_total_tokens ≈ r × N` (±2%). F1/F4 게이트는 `RATIO=0`이라 **SKIP**;
Phase 1 셀(RATIO=2)에서 매번 돈다. 프록시측 `MORI CPU tier` 대조는 셀 시작 시점(L2)에서 수행한다.

### G4 ★ 행동(강제) 검증 — 게이트의 본체

Padder로 만든 **32,376 tok × 13개 (= 1.60 × N)**, 요청별 고유 seed로 filler를 달라지게 해
prefix 공유를 차단(공유되는 것은 ~150토큰 system prompt뿐), concurrency 4, `max_tokens=8`,
`/metrics` 1 Hz 샘플링.

> ⚠️ **P-a·P-b의 계측기는 §9.3에서 교체되었다** (2026-08-05, F1 run 직후). 아래 원문은 보존한다.
> 현행 정의는 §9.3을 보라. **분수 0.80은 바뀌지 않았다.**

| # | 조건 (원문) | **이 축만이 잡는 실패** |
|---|---|---|
| **P-a** | ~~`max(num_used_tokens) ≤ N`~~ → §9.3 | 캡 무시 — 실제 풀이 profiled 2.1M인 경우 (used가 N을 넘어간다) |
| **P-b** | ~~`max(num_used_tokens) ≥ 0.80 × N`~~ → §9.3 | **장부 > 실제.** 유일하게 이걸 잡는 축이다 |
| **P-c** | `Δevicted_tokens_total > 0` | 캡에 닿지 않음 — 압박이 없으면 P-a가 공허해진다 |
| **P-d** | 13개 전부 200 OK | 캡이 요청 실패를 유발 |
| P-e | padder `token_match_err` | 기록 전용, 판정 아님 |

**P-b의 지위 (명시적 결정)**: P-b는 **사전 등록 판정 축**이며 계측 도구가 아니다.
G2의 4출처는 전부 `max_total_num_tokens` **장부**를 읽으므로, 실제 할당기가 장부보다 작으면
(예: 장부 262,246인데 실제 100k) **P-a도 P-c도 통과해 버린다.** 아래에서 실제 용량을 장부에 고정하는
축은 P-b뿐이다. 따라서 `0.80`은 사전 등록 임계값이고, **결과를 보고 내리지 않는다.**

**probe 부하 사양도 사전 등록이다.** 13개·32,376 tok·conc 4는 §3에 고정돼 있다.
부하를 바꿔야 할 상황이 오면 그것은 **별도 라벨의 새 run으로 기록**하며, 원래 결과를 대체하지 않는다.
("계측 도구라서 조정 가능"이라는 여지를 남기지 않는다 — 그 여지가 곧 임계값을 내릴 여지다.)

### G6 2점 감도
`MAXTOK 262,246 → 647,520`에서 `ΔN / ΔMAXTOK = 1.00 ± 0.05`.
한 점만으로는 *"플래그가 듣는다"* 와 *"우연히 그 값에 착지"* 를 구분하지 못한다.

## 5. FAIL 시 행동 (사전 등록 — 임계값 조정은 어떤 경우에도 대응책이 아니다)

| 관측 | 해석 | 행동 |
|---|---|---|
| G1.5 경고 발생 | 자연 풀 < 요청 → mem-frac/weights 계산 오류 | **`MEMFRAC`만** 조정해 자연 풀 확보 후 재게이트. 계획이 gmu 0.90을 [추정]·Phase 0 확정 항목으로 명시(§4, 리스크 7.5) |
| G1.2 실패 (경고 없이 N ≪ 목표) | 예상 못 한 clamp | `/get_server_info` 덤프 기록 → **fit 스윕 중단**, 원인 규명 전까지 Phase 1 착수 금지 |
| G2 불일치 | **I6 위반** — 엔진과 장부가 어긋나면 oversub 계산이 전부 무의미 | 중단 |
| G2b 이상 | 물리 예약이 캡과 무관 | 기록만. G4로 판단 |
| **G4 P-a 실패** | **캡 미강제** | **계획 전체 무효 — 즉시 중단·보고** |
| **G4 P-b 실패** | **장부 > 실제 용량** | **중단.** fit이 장부값이 아니므로 스윕 전체가 무효 |
| G4 P-c 실패 (P-a·P-b는 통과) | 압박 미발생 → P-a가 공허 | 판정 보류. 사양 변경분은 **새 라벨 run**으로 기록 |
| G4 P-d 실패 | 캡이 요청 실패 유발 | 중단, 로그 첨부 보고 |
| G6 기울기 ≠ 1.00±0.05 | 캡이 비선형 착지 | **격자(F1~F5 MAXTOK) 전면 재산출 후 재사전등록** |
| G0.3 실패 (context_len 32,768) | YaRN override 미적용 | `YARN_KEY=rope_scaling`로 재시도 → 실패 시 `--context-length` 하향. **어느 쪽이 먹었는지 전 셀에 기록** |

## 6. 실행 계획 (별도 승인 후)

`bash scripts/run_fit_gate_f1_yunuikang.sh` — 트레이스 0 B 소비 · 드라이버 미실행 · baseline 0셀 · **측정 셀 아님**.

| 단계 | 내용 | 시간 |
|---|---|---|
| 1 | F1 기동 (`MAXTOK=262,246`, RATIO=0, EVICT=lru, MEMFRAC=0.90, TP1, triton, numactl node0) | 3~6분 |
| 2 | G0~G2b + G3(SKIP) | ~10초 |
| 3 | **G4 probe** 13 req | 3~4분 |
| 4 | F4 기동 (`MAXTOK=647,520`) + 정적 게이트 | 5분 |
| 5 | G6 기울기 | 즉시 |
| | **합계** | **≈ 17분** |

## 7. 고정 결정 (전 셀 공통, 변경 시 재사전등록)

| 항목 | 값 | 이유 |
|---|---|---|
| attention backend | **triton** | 5090 하네스와 동일. F1↔5090 C80의 차이를 **하드웨어 하나로** 묶어 두는 것이 F1 통제군의 전부다(계획 §6.2). **모든 H200 셀에서 동일하게 유지**한다 |
| TP | **1** | weights 14.19 GiB가 단일 H200에 적합 → all-reduce 소멸(§1.3). `--disable-custom-all-reduce` 불필요 |
| `--mem-fraction-static` | **0.90** | 계획 §4 [추정]. 전 fit 셀에서 **동일**해야 캡만 변수로 남는다 |
| numactl | **`--cpunodebind=0` 단독** (`--membind` 불가 — §9 개정) | GPU0 = NUMA node 0. HiCache host pool을 node-local로 |
| YaRN | factor 2.1875 / `rope_parameters` 키 | transformers 5.3.0에서 `rope_scaling` → `rope_parameters` 개명 |

## 8. 신규 파일

| 파일 | 역할 |
|---|---|
| `scripts/_serve_sglang_7b_tp1_h200_mori_yunuikang.sh` | H200 serve (env: `MAXTOK RATIO EVICT MEMFRAC PORT NUMA_NODE LOG`) |
| `scripts/fit_gate_yunuikang.py` | 게이트 본체 G0~G4 + G6. JSON 1줄 + exit 0/1. **Phase 1 전 셀 재사용** |
| `scripts/run_fit_gate_f1_yunuikang.sh` | F1 단축 검증 + 2점 감도 러너 |
| `logs/2026-08-05_H200_GATE_PREREG_yunuikang.md` | 이 문서 |

---

## 9. 개정 기록

### 9.1 (2026-08-05 16:30 UTC) numactl `--membind` 철회 — 환경 제약, **측정 이전**

**언제**: 첫 F1 기동 시도가 weights 로드 전에 죽은 직후. **측정값은 단 한 건도 나오기 전이다.**
게이트 임계값·probe 사양·판정 축은 **하나도 바뀌지 않았다.**

**무엇이 일어났나** [측정]:
```
get_mempolicy: Operation not permitted
set_mempolicy: Operation not permitted
setting membind: Operation not permitted
```
`numactl --membind` / `--preferred`는 `set_mempolicy(2)`를 요구하는데, 이 컨테이너는 unprivileged라
해당 호출이 EPERM이다. 엔진이 기동조차 못 했다.

**대체와 그 등가성** [측정]:

| 시도 | 결과 |
|---|---|
| `--cpunodebind=0 --membind=0` | EPERM |
| `--preferred=0` | EPERM |
| **`--cpunodebind=0` 단독** | **성공** |
| 기본 mempolicy (`numactl --show`) | `policy: default` · `preferred node: current` |

기본 정책이 **first-touch local 할당**이므로, 모든 스레드를 node 0에 묶으면(`--cpunodebind=0`)
할당도 node 0에 떨어진다. HiCache host pool의 NUMA 지역성(계획 §1.3 dial ③)이라는 목적에는 등가다.
**전 셀에 동일하게 적용**하며, 이후 변경 시 다시 이 절에 기록한다.

### 9.3 (2026-08-05 16:40 UTC) ★ P-a·P-b **계측기 교체** — 임계값은 불변, F1의 FAIL은 보존

**언제**: F1 run 완료 직후. **F1의 판정(P-b FAIL)은 기록에 그대로 남기고, 교체된 계측기로 도는 것은
`F1b`라는 새 라벨의 별도 run이다.** 원래 결과를 대체하지 않는다.

**무엇이 틀렸나** [측정, `managers/scheduler_runtime_checker_mixin.py:44-49`]:
```python
num_used = self.max_total_num_tokens - (available_size + evictable_size)
```
`sglang:num_used_tokens`는 **evictable(radix 캐시 상주분)을 제외**하고 in-flight 보호 KV만 센다.
그래서 두 축이 모두 무효였다:

| 축 | 무엇이 잘못됐나 | F1 실측 |
|---|---|---|
| **P-b** | in-flight는 `conc × prompt = 4 × 32,376 = 129,504`가 상한 → **`0.80 × 262,246 = 209,797`은 도달 불가능** | peak 128,705 = 상한의 **99.4%** → FAIL |
| **P-a** | `num_used ≤ N`은 **산술적 항등식**(위 식에서 자명) → 캡이 무시돼도 값은 음수로 갈 뿐 N을 넘지 않는다 | 통과했으나 **공허** |

`sglang:token_usage`도 분자가 같아 대안이 못 되고, `evictable_size`/`available_size` 게이지는 노출되지 않는다.

**교체된 계측기 — 축출 산술**. 제공된 모든 토큰은 *풀에 남아 있거나 축출되었거나* 둘 중 하나다:
```
offered_unique = Σ 프롬프트 실현 토큰 + Σ 생성 토큰 − (n_req − 1) × 공유 system prefix
resident_est   = offered_unique − Δevicted_tokens_total
```
제공량이 풀보다 크면 `resident_est`가 곧 **실제 상주 용량**이다.

| # | **현행 조건** | 잡는 실패 |
|---|---|---|
| **P-a** | `resident_est ≤ 1.05 × N` | 캡 무시 — 실제 풀이 profiled 2.1M이면 1.60×N이 통째로 들어간다 |
| **P-b** | `resident_est ≥ 0.80 × N` | **장부 > 실제** (분수 0.80 **불변**) |
| **P-c** | `Δevicted_tokens_total > 0` | 압박 미발생 — 그러면 `resident_est`는 제공량일 뿐이라 P-a·P-b가 무의미해진다 |

`P_A_UPPER = 1.05`는 이 게이트가 이미 쓰는 `TOL_PCT = ±5%`와 같은 값이며, 1 Hz 카운터 샘플링
가장자리와 공유 prefix 보정을 흡수한다. `Δevicted`는 샘플러 마지막 틱이 아니라 **probe 종료 3초 후
직접 조회**한 값을 쓴다. peak `num_used_tokens`는 계속 기록하되 **판정에 쓰지 않는다**(P-0 항목).

**왜 이것이 임계값 완화가 아닌가**: 분수 0.80은 그대로이고, 바뀐 것은 **그 분수를 적용할 양**이다.
원래 P-b가 재려던 것은 처음부터 "실제 상주 용량 대 장부"였고, `num_used_tokens`는 그 양을 재지 않았다.
F1에서 사후로 계산한 값(`420,888 − 160,570 = 260,318`, 장부의 0.9926)이 이미 기준을 넘지만
**그것은 사후 계산이므로 P-b 통과로 치지 않는다.** F1b에서 사전 등록된 식으로 다시 잰다.

### 9.2 (2026-08-05 16:30 UTC) `wait_gpu_idle` 카운트 버그 수정 — 러너 전용, 판정 무관

5090 스크립트에서 가져온 `nvidia-smi ... | grep -c . || echo 0` 관용구는 compute proc이 0일 때
grep이 "0"을 출력하면서 **exit 1**을 내므로 `|| echo 0`이 두 번째 "0"을 덧붙여 `n="0\n0"`이 된다.
그 결과 GPU가 유휴인데도 "잔존"으로 판정해 60초를 낭비했다. `awk 'NF{c++} END{print c+0}'`로 교체.
**판정 항목과 무관한 러너 편의 코드**다.
