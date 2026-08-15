# Raw-event 로깅 스키마 (JSON) — MORI TP1 steady-state 실험

> 작성: 강윤의 · 2026-08-16
> **실험 설계 기준**: `plans/2026-08-15_PLAN_rawlog-steadystate-mori-tp1_yunuikang.md` — **5090 + Pro6000 · TP1 단일 GPU · MORI 단독 · 7B · 30분 program-wall 세션 드롭 · 자연 fit(캡 없음) · 세션 단위 concurrency**
> **형식(JSON 구조·조직 방식) 참고**: 김태현 2026-08-15 피드백 — 원시 이벤트 저장 + 사후 groupby, driver 단조시계, discriminated 이벤트.
> 목적: **집계값이 아니라 원시 이벤트를 저장**하고 통계는 전부 offline groupby. long run 1회 → steady window 분할로 분산.

---

## 0. 조직 결정 (형식을 어떻게 정리할지 — 핵심 6개)

| # | 선택 | **채택** | 이유 |
|---|---|---|---|
| 1 | 이벤트 한 파일 vs 빈도/출처별 분리 | **라이프사이클(`events`) / 고빈도 KV사건(`kv_events`) 분리** | tier_move·evict·reload는 초당 수백건(engine 출처) → 세션/tool 이벤트(driver)와 섞으면 drill-down 파일 비대 |
| 2 | 저장 포맷 | **런 중 JSONL append(크래시 안전) → 분석용 Parquet 변환** | 스트리밍 안전 + columnar groupby |
| 3 | 시각 규약 | **driver 단조시계, run origin=0.0s. server값은 duration(초)** | server timestamp 신뢰 불가(클럭 스큐) |
| 4 | join 키 | **`(session_idx, program_idx, request_idx)` 전 파일 공통** + 원본 `trace_session_id` | 세션 재현성 분석 |
| 5 | recompute(step log 없이) | **request `cached_tokens`+`kv_tokens_end` 궤적 + kv_events(evict/reload)로 offline 재구성**, snapshot 누적카운터로 교차검증 | per-step parquet 없이 GPU 시간예산 도출(§8) |
| 6 | 경계 분석 | request에 **`program_boundary`·`session_first` 플래그** 내장 | boundary cache hit/miss를 groupby 없이 filter로 |

+ `schema_version`·`pool_sha256`·`git_commit`을 run_meta에 → 파서/재현 안정성.

---

## 1. 파일 구성

| 파일 | 단위 | 빈도 | 출처 | 포맷 |
|---|---|---|---|---|
| `run_meta.json` | run 1개 | 1회 | driver | JSON |
| `requests.jsonl` | request(turn) | request마다 | driver+engine | JSONL→Parquet |
| `events.jsonl` | 라이프사이클 사건 | 중 | driver | JSONL |
| `kv_events.jsonl` | KV tier 사건 | **고** | engine(MORI) | JSONL→Parquet |
| `snapshots.jsonl` | 엔진 상태 | 10–30s | engine | JSONL |
| `gpu.jsonl` | GPU 하드웨어 | 0.2–1s | nvidia-smi | JSONL |

---

## 2. 공통 규약

- **시각**: 모든 `*_ts`·`ts` = run origin(0.0s)부터의 **float 초**, driver 단조시계. wall-clock은 `run_meta.wall_clock_origin`에만.
- **duration**: server 내부 측정(`queue_s`·`prefill_s`·`reload_s`·`tool_s`)은 초 단위 duration. (파생: `ttft=first_token_ts−submit_ts`, `decode_s=end_ts−first_token_ts`.)
- **토큰**: 정수 tok. `input_tokens`=그 턴 full prompt(=세션 누적 context). `cached_tokens`=prefix 히트분. `output_tokens`=디코드 생성분.
- **join 키**: `session_idx`(pool 셔플 순서 인덱스, 전 run 고정)·`program_idx`(세션 내)·`request_idx`(program 내). 원본 `trace_session_id`.
- **null 정책**: 미측정은 키 생략이 아니라 `null`. 측정창 밖 여부는 저장 안 하고 `ts`로 offline 판정.
- **캡/트렁케이션 없음**: 이 설계는 30분 program-wall 세션 **드롭**만 하고 tool/human-wait cap·turn-window truncation을 하지 않는다 → 관련 이벤트 필드 없음. human-wait·긴 tool은 남은 세션에서 **원본 그대로 재생**(idleness가 연구 대상).

---

## 3. `run_meta.json`

```json
{
  "schema_version": "1.0",
  "run_id": "5090_c15_pool_v1_seed1",
  "gpu": "5090",
  "tp": 1,
  "git_commit": "3801143",
  "engine": {"name": "sglang", "version": "0.5.10", "attention_backend": "triton",
             "flags": {"tp_size": 1, "mem_fraction_static": 0.85,
                       "max_num_seqs": 256, "hierarchical_cache": true, "hicache_ratio": 2,
                       "disable_custom_all_reduce": true}},
  "model": {"name": "Qwen2.5-7B-Instruct", "dtype": "bf16",
            "num_layers": 28, "kv_heads": 4, "head_dim": 128,
            "kv_bytes_per_token": 57344, "context_length": 71680},
  "router": {"mode": "mori",
             "mori_params": {"k": 5, "tick_s": 5.0, "iota_default": 0.5,
                             "min_dwell_ticks": 1, "reload_bw_Bps": 8.0e9,
                             "cpu_capacity_ratio_r": 2}},
  "kv_pool": {"gpu_pool_tokens": 247297, "host_tier_tokens": 494594, "r": 2, "capped": false},
  "regime": {"fit": 7.6, "s_ctx_tokens": 32376, "concurrency_level": "2fit"},
  "concurrency": 15,
  "dataset": {"pool_id": "rawfilt_v1", "pool_file": "scratch/traces/tracelab_rawfilt_yunuikang.jsonl",
              "pool_sha256": "…", "num_sessions": 400, "seed": 1, "shuffle_order_ref": "rawfilt_v1.order"},
  "preprocessing": {"filter": "drop_session_if_any_program_wall_ge",
                    "program_wall_threshold_s": 1800},
  "timing": {"wall_clock_origin": "2026-08-16T00:00:00+09:00",
             "warmup_plan_s": 900, "duration_s": 14400,
             "measurement_window": {"start_s": 900, "end_s": 4500}},
  "sampler": {"snapshot_interval_s": 20, "gpu_interval_s": 0.5}
}
```

> Pro6000 run은 `gpu`·`gpu_pool_tokens`(≈1.34M)·`fit`(≈41)·`concurrency`만 바뀜. 두 머신 다 TP1.

---

## 4. `requests.jsonl` (주 데이터 — request/turn당 1줄)

| 필드 | 타입 | 단위 | 설명 |
|---|---|---|---|
| session_idx / program_idx / request_idx | int | — | join 키 |
| trace_session_id | str | — | 원본 세션 id |
| program_boundary | bool | — | program의 첫 request |
| session_first | bool | — | 세션의 첫 request |
| submit_ts / first_token_ts / end_ts | float | s | driver 관측 |
| queue_s / prefill_s | float | s | server duration |
| input_tokens / cached_tokens / output_tokens | int | tok | cached≤input |
| kv_tokens_end | int | tok | 이 턴 후 세션 KV 점유(누적) |
| gpu_id | int | — | 현재 0 |
| status | enum | — | `ok`/`error`/`aborted`/`preempted` |

```json
{"session_idx": 42, "program_idx": 3, "request_idx": 7, "trace_session_id": "s_00420",
 "program_boundary": false, "session_first": false,
 "submit_ts": 5023.10, "first_token_ts": 5024.90, "end_ts": 5031.20,
 "queue_s": 0.85, "prefill_s": 0.92,
 "input_tokens": 28210, "cached_tokens": 27800, "output_tokens": 312,
 "kv_tokens_end": 28522, "gpu_id": 0, "status": "ok"}
```

```json
{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object",
 "required":["session_idx","program_idx","request_idx","submit_ts","end_ts",
             "input_tokens","cached_tokens","output_tokens","status"],
 "properties":{
   "session_idx":{"type":"integer"},"program_idx":{"type":"integer"},"request_idx":{"type":"integer"},
   "trace_session_id":{"type":"string"},
   "program_boundary":{"type":"boolean"},"session_first":{"type":"boolean"},
   "submit_ts":{"type":"number"},"first_token_ts":{"type":["number","null"]},"end_ts":{"type":"number"},
   "queue_s":{"type":["number","null"]},"prefill_s":{"type":["number","null"]},
   "input_tokens":{"type":"integer"},"cached_tokens":{"type":"integer"},"output_tokens":{"type":"integer"},
   "kv_tokens_end":{"type":["integer","null"]},"gpu_id":{"type":"integer"},
   "status":{"enum":["ok","error","aborted","preempted"]}},
 "additionalProperties":false}
```

---

## 5. `events.jsonl` (라이프사이클 — discriminated union on `event`)

공통: `ts`(float s) · `event`(str) · `session_idx`.

| event | 추가 필드 |
|---|---|
| `session_start` | trace_session_id |
| `program_start` / `program_end` | program_idx |
| `human_wait` | after_program_idx · wait_s (원본 그대로, 캡 없음) |
| `tool_call` | program_idx · after_request_idx · tool_s (원본 그대로) |
| `session_end` | reason(`completed`/`window_drain`) |

```json
{"ts": 4980.0, "event": "session_start", "session_idx": 42, "trace_session_id": "s_00420"}
{"ts": 5020.5, "event": "program_start", "session_idx": 42, "program_idx": 3}
{"ts": 5100.2, "event": "tool_call", "session_idx": 42, "program_idx": 3, "after_request_idx": 7, "tool_s": 30.0}
{"ts": 5320.5, "event": "program_end", "session_idx": 42, "program_idx": 3}
{"ts": 5320.5, "event": "human_wait", "session_idx": 42, "after_program_idx": 3, "wait_s": 184.2}
{"ts": 9100.0, "event": "session_end", "session_idx": 42, "reason": "completed"}
```

---

## 6. `kv_events.jsonl` (고빈도 KV tier 사건 — MORI engine)

공통: `ts` · `event` · `session_idx`(가능 시 `program_idx`).

| event | 추가 필드 | 비고 |
|---|---|---|
| `evict` | kv_tokens · to(`cpu`/`discard`) | radix/HiCache 축출 |
| `reload` | kv_tokens · from(`cpu`) · reload_s | CPU→GPU 복원 |
| `tier_move` | from_tier · to_tier(`gpu`/`cpu`/`waiting`) · kv_tokens · reason | MORI 정책 |

```json
{"ts": 5200.0, "event": "evict", "session_idx": 42, "kv_tokens": 28522, "to": "cpu"}
{"ts": 5260.0, "event": "reload", "session_idx": 42, "kv_tokens": 28522, "from": "cpu", "reload_s": 0.41}
{"ts": 5262.0, "event": "tier_move", "session_idx": 42, "from_tier": "cpu", "to_tier": "gpu", "kv_tokens": 28522, "reason": "sticky_admit"}
```

---

## 7. `snapshots.jsonl` (엔진 상태, 10–30s) · `gpu.jsonl` (nvidia-smi, 0.2–1s)

```json
{"ts": 5040.0, "kv_usage_pct": 91.2, "kv_used_tokens": 225000, "kv_total_tokens": 247297,
 "num_running": 12, "num_waiting": 3, "num_paused": 0,
 "active_sessions": 15, "active_programs": 9,
 "tier_occupancy": {"gpu": 12, "cpu": 6, "waiting": 2}, "host_tier_bytes": 28360000000,
 "radix_cache_tokens": 190000,
 "cum": {"generation_tokens": 3200000, "prompt_tokens": 11000000,
         "cached_tokens": 9800000, "recompute_tokens": 850000,
         "evict_count": 1200, "reload_count": 1150}}
```
```json
{"ts": 5040.0, "gpu_id": 0, "util_pct": 99.4, "mem_used_mib": 31200, "power_w": 560, "sm_clock_mhz": 2500, "mem_clock_mhz": 14000}
```

- `cum.*` 누적카운터 **델타**로 창 기반 throughput·재계산율·hit율 계산(창 경계는 offline `ts` 기준).
- `active_programs` 분포(mean/p10/p90) 보고 → 순간 활성 program 수(세션 슬롯 C보다 작고 출렁임 = offloading 기회).

---

## 8. 스키마 → 분석 커버리지 (사후 groupby)

| 분석 | 쓰는 필드 | 방법 |
|---|---|---|
| 창 기반 throughput(무편향) | requests `end_ts·first_token_ts·output_tokens` | 디코딩 구간 ∩ 창 **토큰 비례 배분** |
| TTFT 분해 | `submit/first_token_ts·queue_s·prefill_s` | ttft=queue+prefill |
| **GPU 시간예산(decode/prefill-new/recompute/idle)** | requests `input−cached`·`kv_tokens_end` + kv_events `evict/reload` + snapshots `cum.recompute` | offline 재구성(§0-5) |
| program latency·goodput@SLO | `groupby(session_idx,program_idx)` | 사용자 체감 단위 |
| boundary cache hit/miss | requests `program_boundary`+`cached/input` | filter |
| context 누적 궤적 | requests `kv_tokens_end` | 세션별 시계열 |
| idleness ι·d·R 재산출 | events `tool_call/human_wait` + requests `prefill_s+decode` | 창 k=5 |
| steady state 판정 · 분산 | snapshots `kv_usage`·`cum` + requests | plateau 탐지 → window K분할 |
| **drill-down** | snapshots 이상 bin → kv_events(evict storm) → 원인 program requests | 하강 경로 |

---

## 9. 미확정 / 구현 노트

1. **recompute 직접 태깅 여부**: offline 재구성(채택) vs SGLang HiCache가 request별 recompute를 직접 노출 시 `requests.recompute_tokens` 추가. 기동 시 확인.
2. **세션 계층**: raw trace에 "세션 > program" 경계 실재 여부 → GPU 서버 코드 조사 결과 대기(§3 필드 `program_idx` 전제).
3. **Parquet 파티셔닝**: requests/kv_events는 `session_idx` 또는 시간 bin으로 row-group flush.
4. **계측 격리**: 로거는 원본·baseline 경로 **0-diff**(MORI_TIERC 규약 계승) — 신규 `scheduler/mori_rawlog_yunuikang.py`.
5. **context-length**: 남은 세션에 turn input > 71,680(YaRN)이 있으면 서빙 불가 → 그런 세션 존재 여부는 §3 필터 후 프리처리 로그로 확인(트렁케이션은 이 설계 범위 밖).
```
