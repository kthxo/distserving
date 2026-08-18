# MORI raw-event 상시로깅 · steady-state · TP1 — Pro6000(nutella1) 결과 로그

- 작성: 강윤의 · 브랜치 `mori` · 2026-08-17 (KST)
- 서버 **nutella1** · **RTX PRO 6000 Blackwell Max-Q ×1 (GPU index 2)** · TP1 · MORI 단독
- 설계: `plans/2026-08-15_PLAN_rawlog-steadystate-mori-tp1_yunuikang.md`
- 스키마: `plans/2026-08-16_SCHEMA_rawlog_yunuikang.md`
- 측정 규격: `docs/2026-08-16_SPEC_rawlog_measurement_yunuikang.md`
- 트레이스 조사: `logs/2026-08-15_tracelab_trace_structure_yunuikang.md`

> **이 문서는 데이터 수집 기록이다.** 환경 · 무엇을 어떻게 쟀나 · 무결성 · 실패까지만 적는다.
> **결론·판정·해석·셀 간 비교는 쓰지 않는다.** 그것은 후속 분석의 몫이다.
> 라벨: **[측정]** = 로그/파일에서 직접 확인 · **[추론]** = 확인된 사실의 논리적 귀결

---

## 0. 한 눈에

| 셀 | C | 상태 | boot assert | closure C1~C4 | steady (규격 §4) | eager 낙하 |
|---|---|---|---|---|---|---|
| fit | **42** | 완주 8h · rc=0 | PASS | **전항목 PASS** | **도달** (12 bin, CV 0.047) | 1.3 % |
| 2fit | **83** | 완주 8h · rc=0 (**재실행분**) | PASS | **전항목 PASS** | **★미도달** (최장 1 bin) | 37.3 % |
| 4fit | **167** | 완주 8h · rc=0 | PASS | **전항목 PASS** | **★미도달** (최장 4 bin) | 74.2 % |

- **3셀 모두 8h 완주 · boot assert PASS · closure C1~C4 전항목 PASS · 스키마 위반 0.**
- 1차 본 런에서 **C=83이 BOOT FAIL**(§7.1)하여 재실행했다(§7.2에서 성공). C=42·C=167은 1차 런
  산출물을 그대로 쓴다.
- **steady는 C=42만 도달**했다. C=83·C=167은 규격대로 "미도달"로 기록하며 재실행하지 않는다.
- 계측 게이트 정의를 5건 수정했고 그 이력과 근거는 §6에 전부 남겼다.

총 소요: 1차 런 17.2 h (08-16 22:59 → 08-17 16:10) + C=83 재실행 8.6 h (08-17 18:27 → 08-18 03:04).

---

## 1. 환경 [측정]

### 1.1 하드웨어

| 항목 | 값 | 확인 |
|---|---|---|
| 서버 | nutella1 | `hostname` |
| GPU | **RTX PRO 6000 Blackwell Max-Q, 97,887 MiB** | `nvidia-smi` |
| **지정 인덱스** | **GPU 2** | ★ 계획서는 index 1을 지정했으나 실행 시점에 타 사용자 점유 → §1.4 |
| sm | **sm_120** (94.97 GiB usable) | torch `get_device_properties` |
| TP / 인터커넥트 | **TP1 · all-reduce 없음** | |
| GPU↔NUMA | **node 1** (CPU affinity 8–15) | `nvidia-smi topo -m` |
| CPU / DRAM | 16 core / 251 GiB (avail 226–232 GiB) | `nproc`, `free -g` |
| NUMA | node0 128,546 MB · node1 129,019 MB | `numactl --hardware` |
| 드라이버 / CUDA | **590.48.01 / 13.1** (nvcc 13.0.48) | |

### 1.2 소프트웨어 — goguma6와의 diff를 명시

nutella1에는 SGLang 환경이 **없었다**. 신규 `/home/yunuikang/yunuikang_work/.venv-sglang`을 만들었다
(기존 `.venv`(vllm 0.24.0)는 무손상).

| 항목 | nutella1 (이 배치) | goguma6 (선행) | 비고 |
|---|---|---|---|
| SGLang | **0.5.10** | 0.5.10 | 동일 |
| torch | **2.9.1+cu128** | (미기록) | sm_120 arch_list 포함 확인 [측정] |
| sgl-kernel / triton | 0.4.1 / 3.5.1 | — | |
| transformers | 5.3.0 | — | |
| flashinfer | 0.6.7.post2 | — | `--prerelease=allow` 필요(flash-attn-4 4.0.0b19) |
| **JIT 컴파일러** | **gcc-13 / g++-13** | gcc-11 / g++-11 | ★ nutella1에 gcc-11 없음. **sm_120 JIT·CUDA graph 캡처 정상 통과** [측정] |
| CUDA_HOME | /usr/local/cuda-13.0 | /usr/local/cuda-13.0 | |
| attention / sampling | triton / pytorch | triton / pytorch | 동일 |

`sglang[srt]==0.5.10`은 `flash-attn-4>=4.0.0b4`(pre-release)에 의존해 `--prerelease=allow` 없이는
설치가 해결되지 않는다 [측정]. attention backend는 triton이므로 flash-attn은 실사용되지 않는다.

### 1.3 모델 · 엔진 파라미터

| 항목 | 값 |
|---|---|
| 모델 | **Qwen2.5-7B-Instruct** (bf16, 28L · 4 KV head · head_dim 128) |
| KV 밀도 | **57,344 B/tok = 56 KiB/tok** |
| context-length | **71,680** (YaRN factor 2.1875 × 32,768) |
| weights | 14.32 GiB [측정, 기동 로그] |
| mem-fraction-static | 0.90 |
| **max_total_tokens (캡)** | **None — 캡 없음(자연 풀)** |
| max_running_requests | **1024** (C_max=167 대비 6.1× 여유) |
| radix-eviction-policy | **mori** (MORI typed eviction 패치 경유) |
| HiCache | `--enable-hierarchical-cache --hicache-ratio 2` (r=2), write_through |
| `--enable-cache-report` | **ON** (§6.2에 추가 경위) |
| chunked_prefill_size | 4,096 · max_prefill_tokens 16,384 |
| cuda graph capture bs | **[1, 2, 4, 8, 12, 16, 24, 32]** — 상한 **32** [측정] |

**YaRN 검증** [측정]: 기동 시 `User-specified context_length (71680) is greater than the derived
context_length (32768)` 경고가 뜨지만 **양성**이다. SGLang `get_context_length()`가
`original_max_position_embeddings`가 있으면 scaling factor를 1로 강제하기 때문이다(소스 확인).
override 자체는 `rope_type: yarn, factor: 2.1875`로 정상 적용된다. **47,250 tok 프롬프트에서
needle 정확 회수**로 32k 너머 동작을 실측 확인했다.

### 1.4 ★ 통제되지 않은 축 — co-tenant

**이 박스는 단독 점유가 아니었다.** 타 사용자(muchwater)가 같은 기간 GPU0/GPU1에서 별도 작업
(sglang, Qwen3.5-9B)을 상시 수행했다 [측정]. 우리는 **GPU2만** 사용했고 타 사용자 프로세스를
건드리지 않았다(`pkill`을 `-u $(id -u)`로 한정).

- 계획서 §2.1은 nutella를 `CUDA_VISIBLE_DEVICES=1`로 지정했으나, 실행 시점에 GPU1이 타 사용자
  점유 상태였다. 동일 스펙의 유휴 **GPU2**로 변경했다(승인됨).
- **CPU 16 core · DRAM · PCIe는 공유된다.** GPU 연산은 분리되지만 host 자원 경합은 통제되지 않았다.
- GPU2는 NUMA node1, 타 사용자 GPU0/1은 node0이라 CPU/메모리 지역성은 일부 분리된다 [추론].

### 1.5 ★ NUMA — host tier가 node1에 다 안 들어간다

```
host tier (r=2) = 2,640,173 tok × 56 KiB = 141.0 GiB
NUMA node1 용량 = 126 GiB          →  141.0 > 126  ✗
```

`numactl --membind=1`은 **쓸 수 없다**(할당 실패). `--preferred=1 --cpunodebind=1`로 node1을
우선하되 **node0 spill을 허용**했다 [측정].

> **caveat**: 압박이 큰 셀일수록 host tier 점유가 포화에 가까워져 node0 spill 비중이 커진다.
> 그 셀의 reload latency에는 [cross-NUMA 전송] + [co-tenant PCIe/DRAM 경합]이 섞인다.
> **C=4fit 셀의 reload 관련 수치는 과해석 금지** (교란 미통제).

---

## 2. STEP 1 — 트레이스 전처리 [측정]

신규 `scripts/prep_tracelab_rawfilt_yunuikang.py` (CPU only, 원본·기존 스크립트 무수정).

### 2.1 베이스 재생성

Track M primary(`tracelab_moriM_L64k_yunuikang.jsonl`)가 nutella1에 **없어서**, 원본
`syfi_coding_trace.jsonl.gz`에서 `prep_tracelab_mori_yunuikang.py --track M`으로 재생성했다.
결과가 문헌 기록값과 **정확히 일치**: **3,514 세션 / 117,257 턴**, hard gate 3종
(transition median 4.0 · peak ≤64k · ι-IQR 0.6919) 전부 PASS. 재현성 확인됨.

### 2.2 필터 — 세션 wall ≥ 1800s 세션째 제거

wall 정의는 상류 `prep_tracelab_mori_yunuikang.py:267`의 ι 분모와 **동일 상수를 import**해 쓴다
(drift 방지):

```
wall = Σ tool_duration_s + Σ( (input−cached)/8000 + output/152 )
                              └ REASON_PREFILL   └ REASON_DECODE  (둘 다 proxy — 트레이스에 timestamp 없음)
```

| | 세션 | 턴 |
|---|---|---|
| 필터 전 (Track M) | 3,514 | 117,257 |
| 제거 | 329 | 24,647 |
| **필터 후** | **3,185** | **92,610** |
| **보존율** | **90.64 %** | **78.98 %** |

### 2.3 s_ctx 확정 및 분포

**s_ctx = 31,650 tok** (필터 후 per-turn `input_tokens` median. 필터 전 32,376 → −726, −2.2 %)

per-turn input (kept): p10 7,232 · p25 16,007 · **p50 31,650** · p75 48,005 · p90 58,207 ·
p99 64,642 · max 65,536 → 전부 context 71,680 이내.

| 항목 | 남은 세션 (n=3,185) | 제거된 세션 (n=329) |
|---|---|---|
| wall_s p50 | 179.4 | 2,512.2 |
| wall_s p90 / max | 1,146.1 / 1,799.2 | 5,005.5 / 28,814.3 |
| session peak ctx p50 | 51,857 | 64,916 |
| 세션 턴수 p50 / max | 19 / 512 | — |

제거된 세션은 턴이 많고 컨텍스트가 이미 64k 천장에 붙은 쪽에 치우친다(peak p50 64,916 vs 51,857).
턴 손실률(21.0 %)이 세션 손실률(9.4 %)보다 큰 것이 같은 사실의 다른 표현이다. **이 편향은 사실로만
기록한다.**

산출: `scratch/traces/tracelab_rawfilt_yunuikang.jsonl`
(sha256 `631b085a215cd9bdd61045ac95bcb7d81611e8547fd9b5f8330d4525e8d907e4`) + `.meta.json`

---

## 3. STEP 2 — 자연 KV 풀 · fit · C [측정]

```
C_gpu (자연 풀, 캡 없음) = 1,320,086 tok      (K 35.25 + V 35.25 GiB, 기동 로그)
host tier (r=2)          = 2,640,173 tok      ( = 2 × C_gpu, /metrics 실측)
fit = C_gpu / s_ctx      = 1,320,086 / 31,650 = 41.7089
C   = round(fit / 2fit / 4fit)                = 42 / 83 / 167
```

계획서 §4.1의 Pro6000 추정치(풀 ≈1.34 M, fit ≈41)와 부합한다 [측정으로 대체됨].

### 3.1 boot assert 결과 — 전 셀

**★ A1 검사 정의 수정 (2026-08-16 승인)**: 풀을 하드코딩 값과 **비트일치**로 검사하지 않는다.
SGLang 풀 프로파일링은 기동마다 미세하게 흔들려 비트일치는 false FAIL을 낸다(goguma에서 이걸로
전 셀이 중단된 전례). 대신 **"캡 미적용"을 직접 검사**하고, **C를 매 기동 실측 풀로 재계산**해
승인 격자와 대조한다. 풀 편차는 참고 출력만 하고 FAIL 조건에서 뺐다.

| 검사 | C=42 | C=167 | C=83(재실행) |
|---|---|---|---|
| GPU pool (기준 대비) | 1,320,086 (**+0.000 %**) | 1,320,086 (**+0.000 %**) | (§7.2) |
| cap flag == None | ✅ | ✅ | |
| cap warn == 0건 | ✅ | ✅ | |
| host tier == r×pool | 2,640,173 vs 2,640,172 ✅ | 동일 ✅ | |
| fit | 41.7089 | 41.7089 | |
| **C 재계산 == [42,83,167]** | ✅ | ✅ | |
| **판정** | **PASS** | **PASS** | |

---

## 4. STEP 3 — raw 로깅 구현 · 0-diff 검증

### 4.1 신규 파일 (전부 `*_yunuikang`, 기존 경로 무수정)

| 파일 | 역할 |
|---|---|
| `scripts/prep_tracelab_rawfilt_yunuikang.py` | §2 세션째 제거 프리처리 |
| `scripts/mori_rawlog_yunuikang.py` | 6-stream 로거 (엔진 monkeypatch + driver writer) |
| `scripts/rawlog_hook_yunuikang/sitecustomize.py` | 훅 체이닝 (§4.3) |
| `scripts/mori_replay_driver_rawlog_yunuikang.py` | driver 래퍼 (결정 로직 0-diff) |
| `scripts/_serve_sglang_7b_tp1_pro6000_mori_yunuikang.sh` | 단일 GPU serve (자연 풀·r2) |
| `scripts/run_rawlog_matrix_yunuikang.sh` | 3셀 러너 |
| `scripts/check_rawlog_closure_yunuikang.py` | 무결성·closure C1~C4 |
| `scripts/postprocess_rawlog_yunuikang.py` | 측정 규격 구현 (§5) |
| `scripts/verify_rawlog_0diff_yunuikang.py` | 가드레일 기계 검증 |
| `docs/2026-08-16_SPEC_rawlog_measurement_yunuikang.md` | 측정 규격 |

> **경로 편차**: 지시문은 `scheduler/mori_rawlog_yunuikang.py`였으나, 이 저장소에는 최상위
> `scheduler/`가 없고(있는 것은 `ThunderAgent/scheduler/`), 로거는 sitecustomize가 `PYTHONPATH`
> 에서 import해야 하므로 기존 `mori_tierc_instrument_yunuikang.py`와 **같은 레이어인
> `scripts/`** 에 두었다.

### 4.2 0-diff 기계 검증 — PASS [측정]

`scripts/verify_rawlog_0diff_yunuikang.py`가 두 가지를 검사한다:

1. **tracked 파일 무수정** — `git status --porcelain`에 수정(non-`??`) 항목 0건.
   baseline(`ThunderAgent/scheduler/router.py`·`backend/state.py`·`profile/state.py`), 원본 trace,
   기존 driver/serve/prep 스크립트 전부 무수정.
2. **`run_session` 결정 로직 0-diff** — 래퍼의 `run_session_logged`에서 로깅 문장
   (`LOG.*(...)` 표현식문 · 로깅 전용 지역변수 대입 · 몸통이 전부 로깅인 `if`)을 **AST로 제거**한 뒤
   원본 `run_session`과 **토큰 단위 비교**. 완전 일치.

concurrency는 원본 그대로 **세션 단위 closed-loop**이며 변경하지 않았다.

### 4.3 sitecustomize 훅 체이닝 (원본 무수정)

Python은 sys.path에서 **처음 찾은** `sitecustomize` 하나만 import한다. 기존
`scripts/sitecustomize.py`(MORI 패치 + TierC)를 고치지 않기 위해, 더 앞선 경로에 새 sitecustomize를
두고 그 안에서 **원본을 경로로 직접 실행**해 기존 동작을 100 % 보존한 뒤 raw 로거를 추가로 건다.

> **1차 스모크에서 발견된 버그** [측정]: serve 스크립트가 `PYTHONPATH`에 `$REPO/scripts`를
> **앞에** 붙여 원본 sitecustomize가 먼저 잡혔고, tierc 배너만 뜨고 **kv_events가 한 줄도 나오지
> 않았다**. serve 스크립트의 export 순서를 `rawlog_hook:scripts`로 고쳐 해결.

### 4.4 시각 규약 [측정]

run origin 0.0s = `MORI_RAWLOG_T0`(unix float). 러너가 serve 기동 **전에** 정해 serve·driver 양쪽에
같은 값을 주입한다.

- **driver**: `ts = (perf_counter − pc0) + (wall0 − T0)` — 내부는 **단조시계 하나**, 원점만 shift
- **engine**(별도 프로세스): `ts = time.time() − T0`

`run_meta.clock_anchor`에 `t0_unix`·`driver_wall0_unix`·`driver_perf_counter0`·`driver_shift_s`를
남겨 사후 검증 가능하게 했다. closure가 매 셀 "driver/engine 시계 원점 일치"를 검사한다.

### 4.5 스키마 편차 (승인됨)

| 항목 | SCHEMA 원문 | 이 배치 | 사유 |
|---|---|---|---|
| join 키 | `(session_idx, program_idx, request_idx)` | **`(session_idx, cycle, turn)`** | 트레이스에 program 계층 없음(session=program 1:1). driver `program_id = sid#c{cycle}`는 세션 replay 인스턴스 |
| §2 "캡/트렁케이션 없음" | — | **무시** | 실제 베이스는 Track M(L=64k window + tool 300s clamp) + driver `--ctx-cap` |
| `tier_move` 이벤트 | 있음 | **없음** | MORI tier 이동은 evict/reload/evict_host 3종으로만 관측됨 |
| `kv_events.session_idx` | 세션 id | **항상 null** | 엔진 HiCache/radix는 **트리 노드 단위**라 그 레이어에 세션 개념이 없음. 지어내지 않는다 |

`cached_tokens`가 필요한 세션 귀속 분석은 `requests`의 `cached_tokens` + `kv_tokens_end` 궤적으로
offline 재구성한다(SCHEMA §0-5가 상정한 경로 그대로).

---

## 5. 측정 규격 (셀 공통·고정) — `docs/2026-08-16_SPEC_rawlog_measurement_yunuikang.md`

| 항목 | 규칙 |
|---|---|
| 런 길이 | **셀당 8h 고정** (`DUR=28800`), grace 2,100s |
| warmup 컷 | `max(run_start + 2400s, T_fill)` · `T_fill` = `num_used_tokens`가 post-2400s 중앙값의 95 %에 처음 도달한 시각 |
| bin | **정확히 600 s** 비중첩, 끝 자투리 버림 |
| throughput | 디코드 구간(`first_token_ts`→`end_ts`)을 bin에 **토큰 시간비례 배분** |
| steady 판정 | bin throughput이 post-warmup 중앙값 **±10 %** 이내인 **최장 연속 구간 ≥ 12 bin(2 h)** |
| 미도달 시 | 임계 완화·창 이동 **금지**, "미도달" 그대로 기록 |
| 분산 | steady bin 각각을 표본 → n·mean·sd·**CV**·CI95(정규 근사) |

> **CI95 caveat**: steady bin은 서로 독립이 아닐 수 있다(throughput 지속성/자기상관). 자기상관이
> 있으면 유효 표본수가 n보다 작아져 **정규근사 CI95는 실제보다 다소 낙관적(좁게)** 나온다.
> 이 배치는 판정이 아니라 특성화이므로 보정 없이 진행하되 **CI95를 유의성 근거로 쓰지 않는다.**

3셀에 기계적으로 동일 적용했고 셀별 튜닝은 하지 않았다.

---

## 6. 계측 게이트 정의 수정 이력 (전부 승인됨)

수치를 맞추려고 임계를 넓힌 것이 아니라, **원 정의가 이 엔진 구성에서 성립하지 않음을 실측으로
확인하고 의도를 직접 검사하도록 바꾼 것**이다. 원 지표는 참고값으로 계속 출력한다.

### 6.1 C3 — "GPU busy ÷ forward host" → "forward 계측 무결성"

1차 스모크에서 비가 **46.59×**로 FAIL. 원인 추적 [측정]:

```
host_ms median 0.4995 ms   vs   gpu_ms median 33.6085 ms
```

SGLang은 overlap 스케줄링이 기본 ON이라 `forward_batch_generation`이 커널을 forward_stream에
**enqueue만 하고 즉시 반환**한다(기존 `mori_tierc_instrument_yunuikang` docstring §1이 명시).
따라서 host 시간은 GPU 작업시간의 분모가 될 수 없고 "≈1이어야 한다"는 전제가 틀렸다.

→ **재정의**: rank 수 == TP · 음수 `gpu_ms` 0 · 60s 초과 step 0 · rank별 busy ≤ wall.
원 비율은 참고 출력 유지. C1·C4가 실질 무결성을 이미 커버한다.

### 6.2 `--enable-cache-report` 추가

1차 스모크에서 `cached_tokens`가 **1,556/1,556 전부 null**이었다 [측정]. SGLang
`usage_processor.calculate_streaming_usage`가 `enable_cache_report` 게이트 뒤에서만
`prompt_tokens_details.cached_tokens`를 채운다(소스 확인). SCHEMA §4의 핵심 필드이자 §0-5의
recompute offline 재구성이 여기 의존하므로 serve 스크립트에 플래그를 추가했다.

2차 스모크에서 null **2/1,588**로 감소. 남은 2건은 `turn:0` 첫 턴이고, SGLang
`_details_if_cached()`가 `count > 0`일 때만 필드를 내보내므로 **null ≡ prefix-hit 0**이다(소스 확인).
raw에는 null을 그대로 두고 이 의미를 기록한다.

### 6.3 C2 — 판정 구간을 측정창 내부로 한정

1차 본 런에서 C=42가 "최대구멍 300.6s"로 FAIL. 추적 [측정]: 그 구멍은 8h 측정창(28,800s)이
**끝난 뒤 grace/drain 구간**(t=30,470~30,771s)이었고 그 동안 snapshots는
`running=0 · queue=0 · used_tok=0`이었다. 세션이 전부 끝나 엔진이 할 일이 없어 forward가
호출되지 않은 **정상 유휴**이지 로깅 손실이 아니다.

→ **수정**: (a) 판정 구간을 `[run_start, run_start + duration_s]`로 한정(grace/drain 제외),
(b) 구멍이 걸친 snapshots가 전부 `running=0 & queue=0`이면 유휴로 인정.
**`running>0`인데 로그가 비어 있으면 여전히 FAIL**(진짜 손실).

재채점 결과 측정창 내 최대구멍은 C=42 **4.5s**, C=167 **3.9s**로, 유휴 인정 규칙은 실제로는 한 건도
발동하지 않았다 — 창 한정만으로 해결됐다.

### 6.4 A1 (boot assert) — 비트일치 → 캡 미적용 검사

§3.1 참조.

### 6.5 cuda-graph-max-bs — 기본값 유지 (올리지 않음)

실측 캡처 목록은 `[1,2,4,8,12,16,24,32]`로 **상한 32**다. 올리면 graph 캡처가 정적 메모리를 더 먹어
**자연 KV 풀이 줄고 fit·C(42/83/167)가 밀려** A1이 거부하고 셀 간 비교가 깨진다. 또 C=4fit의
관측 batch max 165는 어차피 못 잡는다. 따라서 기본값을 유지하고, **초과분을 사후 계량**한다(§8).

---

## 7. 실패 기록 — 숨기지 않고 그대로

### 7.1 C=83 BOOT FAIL (1차 본 런) — 셀 미실행

```
[cell C83] START 2026-08-17 07:32:51 KST
   [assert] GPU pool  = 1,009,662  (기준 1,320,086 대비 -23.515%)
   [assert] fit       = 31.9009  →  C 재계산 = 32 / 64 / 128
   [assert] FAIL: 실측 풀로 재계산한 C [32,64,128] != 승인 격자 [42,83,167]
   !! FATAL boot assert
[cell C83] BOOT FAIL
```

**근본 원인** [측정] — 직전 셀 메모리가 덜 반환된 상태에서 기동:

| | C=83 (실패) | C=167 (1분 뒤, 정상) |
|---|---|---|
| `Load weight begin` avail mem | **75.91 GB** | **94.25 GB** |
| KV Cache 할당 | 1,009,662 tok (26.96+26.96 GB) | 1,320,086 tok (35.25+35.25 GB) |

C=42 driver 종료(07:32:32) → C=83 serve 기동(07:33:23), **51초 간격**. `wait_gpu_clear`가
nvidia-smi 기준 <500 MiB를 통과했으나 **18.3 GB가 아직 반환 중**이었다. 캡이 걸린 것이 아니라
(`cap flag=None`, `cap warn=0`) **프로파일 자체가 오염**된 것이다.

A1이 풀 비트일치 대신 **C 재계산**으로 이를 잡아냈다 — 의도대로 동작했다.

실패 산출물은 `scratch/mori/rawlog_pro6000/C83_bootfail_1786919571/`에 보존했다(serve.log 포함).

**러너 버그 (동시 발견)**: 셀 실패 시 `cell()`이 1을 반환해도 for 루프가 다음 셀로 진행했다.
"실패면 정지·보고, 우회 금지" 원칙과 어긋난다. → 첫 실패에서 `break` + `exit 1`로 수정.
(완료 셀 skip 로직은 유지되므로 이어받기는 그대로 된다.)

**재발 방지** (적용됨):
- `wait_gpu_clear`: **연속 3회** clear 확인 + **settle 20s** + settle 후 재점유 감지 시 재대기
- 풀 편차 > 5 %면 오염된 기동으로 보고 **자동 1회 재기동**

### 7.2 C=83 재실행 — 성공 [측정]

2026-08-17 18:27:15 → 2026-08-18 03:04:08 KST, driver rc=0, closure 전항목 PASS.

```
[cell C83] START 18:27:15 KST  C=83 dur=28800s
   [gpu] GPU2 clear x3 (2MiB) — settle 20s        ← 강화된 teardown 대기가 작동
   READY ~63s
   [assert] GPU pool  = 1,320,086  (기준 대비 +0.000%)   ← 1차 실패 시 1,009,662 (-23.515%)
   [assert] cap flag  = None   ·  cap warn = 0 건
   [assert] host tier = 2,640,173  (r*pool = 2,640,172)
   [assert] fit       = 41.7089  →  C 재계산 = 42 / 83 / 167
   [assert] PASS
```

풀이 정확히 복구됐다. **자동 재기동(풀 편차 >5 %)은 발동하지 않았다** — 강화된 대기
(연속 3회 clear + settle 20s)만으로 정상 기동했다. 즉 §7.1의 근본 원인이 teardown 지연이었다는
진단이 실측으로 확인됐다 [추론].

### 7.3 기타 실패·미달

| 항목 | 내용 |
|---|---|
| 1차 스모크 kv_events 0줄 | sitecustomize 우선순위 버그 (§4.3). 스모크 폐기 후 재실행 |
| 1차 스모크 cached_tokens 전량 null | `--enable-cache-report` 누락 (§6.2). 스모크 폐기 후 재실행 |
| SGLang import 스모크 (STEP 0) | 최초 보고 시점엔 **환경 부재로 실행 불가 = 미달**. 설치 후 통과 |
| Track M 기준 트레이스 부재 | nutella1에 없어 재생성 (§2.1). 문헌값과 정확 일치 확인 |
| `sglang:evicted_tokens_total` 등 | 이 빌드가 노출하지 않음 [측정]. evict/reload 누적은 kv_events 창별 합산으로 대체 |

---

## 8. 셀별 산출물

경로: `scratch/mori/rawlog_pro6000/<셀>/`

### 8.1 C = 42 (fit) [측정]

기간: 2026-08-16 22:59:32 → 2026-08-17 07:32:32 KST (driver rc=0)

| 파일 | 줄 | 크기 |
|---|---|---|
| `run_meta.json` | 1 | 4,645 B |
| `requests.jsonl` | **38,594** | 19,204,875 B |
| `events.jsonl` | 37,812 | 4,510,806 B |
| `kv_events.jsonl` | **146,424** | 16,787,536 B |
| `snapshots.jsonl` | 1,515 | 933,077 B |
| `gpu.jsonl` | 30,675 | 5,861,851 B |
| `steplog.*.jsonl` (TierC) | 434,876 | 66,409,644 B |

**closure C1~C4 — 전항목 PASS**
```
C1 busy <= wall              busy 30,151.3s / wall 30,684.1s = 0.983
C2 steplog 창 커버리지        측정창 [95..28895]s · step [97..28895]s
                              최대구멍 4.5s (유휴인정 0 / 실공백 0)
C3 forward 계측 무결성        rank=[0] tp=1 · 음수 0 · 과대 0
   (참고) gpu 30,151.3s / host(enqueue만) 479.6s = 62.87x
C4 토큰 교차검증              output 5,967,028/5,966,731 = 1.000
                              input  1,248,981,791/1,248,881,816 = 1.000
스키마 위반 0 · 시계 원점 일치 PASS
```

**참고 수치**
```
requests ok 38,593 / err 1        고유 (session_idx,cycle) 1,356
session_end 1,356 (completed 1,355)   context_truncate 1   tool_call 35,096
kv_events: evict 90,756 · radix_evict_device 26,930 · reload 5,500 · radix_evict_host 23,232
num_running_reqs: p50 22 · p90 29 · max 37 · >graph상한(32) 19/1,514 = 1.3%
```

**steady (규격 §4) — 도달**
```
run [95..30779]s   warm cut 2,495s (floor 2,495 · T_fill 523)
bins 47 x 600s     median 195.8 tok/s
최장 연속 12 bin (기준 >=12)  ->  도달, 구간 [2,495..9,695]s
변동  n=12  mean 197.5  sd 9.3  CV 0.047  CI95 [192.2, 202.7]
```

### 8.2 C = 83 (2fit) [측정]

기간: 2026-08-17 18:27:15 → 2026-08-18 03:04:08 KST (driver rc=0). **재실행분**(1차는 §7.1 BOOT FAIL).

| 파일 | 줄 | 크기 |
|---|---|---|
| `run_meta.json` | 1 | 4,647 B |
| `requests.jsonl` | **27,468** | 13,673,139 B |
| `events.jsonl` | 26,733 | 3,186,421 B |
| `kv_events.jsonl` | **148,972** | 17,340,988 B |
| `snapshots.jsonl` | 1,527 | 935,984 B |
| `gpu.jsonl` | 30,891 | 5,902,796 B |
| `steplog.*.jsonl` (TierC) | 292,932 | 43,652,680 B |

**closure C1~C4 — 전항목 PASS**
```
C1 busy <= wall              busy 30,873.0s / wall 30,900.0s = 0.999
C2 steplog 창 커버리지        측정창 [112..28912]s · step [115..28911]s
                              최대구멍 4.4s (유휴인정 0 / 실공백 0)
C3 forward 계측 무결성        rank=[0] tp=1 · 음수 0 · 과대 0
   (참고) gpu 30,873.0s / host(enqueue만) 728.8s = 42.36x
C4 토큰 교차검증              output 4,310,224/4,309,557 = 1.000
                              input  894,315,780/894,186,970 = 1.000
스키마 위반 0 · 시계 원점 일치 PASS
```

**참고 수치**
```
requests ok 27,464 / err 4        고유 (session_idx,cycle) 952
session_end 947 (completed 943)   context_truncate 1   tool_call 24,828
kv_events: evict 80,594 · radix_evict_device 33,493 · reload 4,499 · radix_evict_host 30,380
num_running_reqs: p50 30 · p90 39 · max 73 · >graph상한(32) 569/1,526 = 37.3%
```

**steady (규격 §4) — ★미도달**
```
run [112..31012]s   warm cut 2,512s (floor 2,512 · T_fill 378)
bins 47 x 600s      median 138.6 tok/s
최장 연속 1 bin (기준 >=12)  ->  미도달
```

bin throughput이 median ±10 %(=[124.7, 152.5]) 밴드 안에 연속으로 머물지 않았다 [측정]:
`227 173 166 182 132 167 153 84 132 124 119 172 104 139 192 71 78 177 158 99 170 168 80 75 …`
(min 45 · max 237). KV 사용률 67–84 %, **host tier 99.9 % 포화**.

규격 §4대로 **임계 완화·창 이동 없이 "미도달"로 기록**한다.

### 8.4 post-warmup bin 기술통계 (3셀) [측정]

steady 게이트와 별개로, post-warmup 47 bin 전체의 기술통계다. **판정·비교·해석이 아니라 각 셀에서
게이트가 어떤 수치 상황에서 통과/미통과했는지의 사실 기록이다.**

| 셀 | n | mean | sd | CV | 전반 mean | 후반 mean | 후/전 | min | max | 최장연속 | steady |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C=42 | 47 | 192.6 | 37.2 | **0.193** | 203.7 | 182.0 | 0.893 | 15 | 254 | **12 bin** | **도달** |
| C=83 | 47 | 132.0 | 48.7 | **0.369** | 142.1 | 122.4 | 0.861 | 45 | 237 | 1 bin | 미도달 |
| C=167 | 47 | 55.6 | 33.2 | **0.597** | 75.2 | 36.7 | 0.488 | 31 | 192 | 4 bin | 미도달 |

> 미도달 두 셀의 수치 양상은 서로 다르다 [측정]: C=83은 후/전 0.861로 추세가 완만한데 bin 간
> 진폭이 크고(sd 48.7, min 45 ↔ max 237), C=167은 후/전 0.488로 창 내내 하강했다.
> 두 경우 모두 ±10 % 밴드에 12 bin 연속이 잡히지 않았다는 결과는 같다.
> **원인 규명·해석은 이 로그의 범위가 아니다.**

> **eager 낙하 비율은 셀마다 크게 다르다** [측정]: C=42 **1.3 %** · C=83 **37.3 %** · C=167 **74.2 %**
> (`num_running_reqs`가 cuda graph 상한 32를 넘은 snapshot 비율). 세 셀은 실행경로 구성이
> 서로 달라 **직접 비교할 수 없다.** §8.3.1 참조.

### 8.3 C = 167 (4fit) [측정]

기간: 2026-08-17 07:34:00 → 16:10:27 KST (driver rc=0)

| 파일 | 줄 | 크기 |
|---|---|---|
| `run_meta.json` | 1 | 4,648 B |
| `requests.jsonl` | **13,669** | 6,800,355 B |
| `events.jsonl` | 13,554 | 1,610,938 B |
| `kv_events.jsonl` | **157,307** | 18,687,273 B |
| `snapshots.jsonl` | 1,536 | 937,524 B |
| `gpu.jsonl` | 30,892 | 5,899,313 B |
| `steplog.*.jsonl` (TierC) | 176,963 | 25,520,367 B |

**closure C1~C4 — 전항목 PASS**
```
C1 busy <= wall              busy 30,894.7s / wall 30,900.0s = 1.000
C2 steplog 창 커버리지        측정창 [86..28886]s · step [92..28886]s
                              최대구멍 3.9s (유휴인정 0 / 실공백 0)
C3 forward 계측 무결성        rank=[0] tp=1 · 음수 0 · 과대 0
   (참고) gpu 30,894.7s / host(enqueue만) 689.5s = 44.81x
C4 토큰 교차검증              output 2,121,350/2,120,620 = 1.000
                              input  391,829,474/391,600,543 = 1.001
스키마 위반 0 · 시계 원점 일치 PASS
```

**참고 수치**
```
requests ok 13,669 / err 0        고유 (session_idx,cycle) 580
session_end 432 (completed 432)   context_truncate 0   tool_call 12,390
kv_events: evict 67,928 · radix_evict_device 43,979 · reload 3,581 · radix_evict_host 41,813
num_running_reqs: p50 36 · p90 43 · max 165 · >graph상한(32) 1,139/1,536 = 74.2%
```

**steady (규격 §4) — ★미도달**
```
run [86..30986]s   warm cut 2,486s (floor 2,486 · T_fill 294)
bins 47 x 600s     median 44.5 tok/s
최장 연속 4 bin (기준 >=12)  ->  미도달
```

bin throughput이 warmup 컷 이후에도 8h 내내 하강했다 [측정]:
`192 → 111 → 120 → 137 → 70 → 109 → … → 31~45대에서 완만히 수렴`.
±10 % 밴드에 12 bin 연속이 잡히지 않았다. KV 사용률 84–94 %, **host tier 99.9 % 포화**.

규격 §4대로 **임계 완화·창 이동 없이 "미도달"로 기록**했다. 재실행하지 않는다(§8.3.1).

#### 8.3.1 ★ C=167 caveat — 두 문제가 얽혀 있다

1. **steady 미도달**: 8h로도 수렴하지 않았다(하강 지속 · host tier 99.9 % 포화).
2. **eager 낙하 74.2 %**: `num_running_reqs` p50 36 · p90 43 · **max 165**로 cuda graph 상한 32를
   크게 넘는다. C=42의 1.3 %와 **실행경로가 상이**하다.
3. **얽힘**: 4fit 압박 → batch 폭증 → graph 상한 초과 → eager 낙하, 동시에 수렴 지연.
   두 현상이 같은 원인에서 갈라져 나오므로 분리 계량되지 않는다.
4. **완화 불가**: `--cuda-graph-max-bs`를 올려도 batch max 165는 못 잡고(4× 압박에서 eager는
   불가피), 올리면 풀이 줄어 C 격자가 밀려 A1이 거부하고 비교가 깨진다.

> **따라서 C=167 셀은 C=42와 직접 비교할 수 없다.** 이는 사실 기록이며 해석이 아니다.

---

### 8.5 무결성 최종 재검증 (3셀 일괄) [측정]

```
셀     6파일  requests   events   kv_events  snapshots   gpu   스키마위반  ts>=0  시계원점  RESULT
C42    PASS   38,594     37,812   146,424    1,515      30,675    0       PASS   겹침 30,678.9s  PASS
C83    PASS   27,468     26,733   148,972    1,527      30,891    0       PASS   겹침 30,891.3s  PASS
C167   PASS   13,669     13,554   157,307    1,536      30,892    0       PASS   겹침 30,858.4s  PASS
```
`requests end_ts >= submit_ts` 위반 0 · `cached_tokens <= input_tokens` 위반 0 (3셀 전부).

총 산출물 크기 **365 MB** (`scratch/mori/rawlog_pro6000/`). 디스크 여유 95 GB.

가드레일 최종 확인: **tracked diff 0줄** · `run_session` 결정 로직 0-diff **PASS**.
타 사용자 GPU 미접촉 유지(전 기간 GPU2만 사용, `pkill -u $(id -u)` 한정).

---

## 9. 재현

```bash
# STEP 1  트레이스 전처리 (GPU 불필요)
python scripts/prep_tracelab_mori_yunuikang.py --track M          # Track M 재생성
python scripts/prep_tracelab_rawfilt_yunuikang.py                 # 1800s 세션째 제거

# STEP 3  가드레일 기계 검증
python scripts/verify_rawlog_0diff_yunuikang.py

# STEP 5  본 런 (셀당 8h × 3, 완료 셀 자동 skip)
TIERC=1 CLIST="42 83 167" DUR=28800 bash scripts/run_rawlog_matrix_yunuikang.sh

# STEP 6  무결성 · 측정
python scripts/check_rawlog_closure_yunuikang.py --dir scratch/mori/rawlog_pro6000/C42
python scripts/postprocess_rawlog_yunuikang.py   --dir scratch/mori/rawlog_pro6000/C42 \
       --json scratch/mori/rawlog_pro6000/C42/postprocess.json
```

환경: `.venv-sglang` (SGLang 0.5.10 · torch 2.9.1+cu128 · gcc-13 JIT)
git commit: 브랜치 `mori` — tracked diff 0줄, 신규 파일 전부 untracked `*_yunuikang`

---

## 10. 이 로그가 담지 않은 것

goodput·SLO 대입, prefix hit율 집계, GPU 시간예산 분해(decode/prefill-new/recompute/idle),
MORI tier 동역학, **셀 간 비교**, 5090 대조 — 전부 후속 분석의 몫이다.
이번 배치의 산출은 **raw 수집 + 무결성 + steady 도달 여부**까지다.
