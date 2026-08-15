# TraceLab 리플레이 트레이스 구조 조사 (읽기 전용)

- 작성: 2026-08-15 (KST)
- 범위: 코드 수정 없음. 트레이스 파일은 읽기만 함.
- 대상: `scripts/mori_replay_driver_yunuikang.py`, `scripts/trace_replay_driver_yunuikang.py`,
  `scripts/prep_tracelab_mori_yunuikang.py`, `/home/yunuikang/yunuikang_work/scratch/traces/*.jsonl`

라벨: **[측정]** = 파일/데이터에서 직접 확인, **[추론]** = 확인된 사실의 논리적 귀결, **[추정]** = 근거 약함.

---

## 1. 트레이스 경로와 레코드 스키마

**[측정]** 경로는 하드코딩이 아니라 `--trace` 필수 인자다
(`scripts/mori_replay_driver_yunuikang.py:404`, base는 `scripts/trace_replay_driver_yunuikang.py`).
`scripts/run_mori_eval_yunuikang.sh:68`이 `--trace "$TRACE"`로 넘긴다.
실제 코퍼스는 `/home/yunuikang/yunuikang_work/scratch/traces/*.jsonl`.

**[측정]** 파서는 `load_trace` (`scripts/trace_replay_driver_yunuikang.py:47-66`).
필수 필드 검증은 4개뿐: `session_id`, `turn`, `input_tokens`, `output_tokens`
(`trace_replay_driver_yunuikang.py:56-58`).

**[측정]** `tracelab_moriM_L64k_yunuikang.jsonl` 117,257줄 **전부** 동일한 6-키 스키마:

```json
{"session_id": "codex:3f8293ac-...", "turn": 0, "input_tokens": 4096,
 "output_tokens": 147, "tool_duration_s": 0.0, "cached_tokens": 3431}
```

emit 지점: `scripts/prep_tracelab_mori_yunuikang.py:257-263`
(문서화는 `prep_tracelab_mori_yunuikang.py:23-24`).

| 필드 | 의미 | 드라이버에서 쓰이는 곳 |
|---|---|---|
| `session_id` | 세션 키 (그룹핑 단위) | `trace_replay_driver_yunuikang.py:59` |
| `turn` | 세션 내 0-based 턴 인덱스 | `mori_replay_driver_yunuikang.py:97,98` |
| `input_tokens` | 그 턴의 **누적** 프롬프트 토큰 (절대값, 증분 아님) | `mori_replay_driver_yunuikang.py:95` |
| `output_tokens` | 그 턴 디코드 토큰 | `mori_replay_driver_yunuikang.py:95` |
| `tool_duration_s` | tool span + human-wait, 300s clamp | `mori_replay_driver_yunuikang.py:96,129-130` |
| `cached_tokens` | prefix-cache read 토큰 | **어느 드라이버도 읽지 않음** (grep 0 hit) |

**[측정]** **없는 것**: `program_id` 없음, `timestamp`/`arrival_time` 없음, `project` 없음,
`tool_call` 개별 항목 없음(턴당 1개 스칼라로 합쳐짐, `prep_tracelab_mori_yunuikang.py:27-30` 주석).

**[측정]** `turn`은 모든 3,514 세션에서 `0..n-1` 연속 (불연속 세션 0개).

---

## 2. 계층 구조: 세션 ≈ 프로그램 (1:1)

**[측정]** 트레이스에 `program_id`가 **존재하지 않는다**. 드라이버가 실행 시 합성한다:

- MORI: `pid = f"{sid}#c{cycle}"` (`mori_replay_driver_yunuikang.py:205`)
- base: `pid = f"{sid}#{run_idx}"` (`trace_replay_driver_yunuikang.py:316`)

**[측정]** `run_session` docstring이 명시적으로 `"""One session=program."""`
(`mori_replay_driver_yunuikang.py:85`). 그 `program_id`가 그대로 요청 payload
(`mori_replay_driver_yunuikang.py:114`)와 `/programs/release`
(`mori_replay_driver_yunuikang.py:133`)로 라우터에 간다. 라우터 쪽 수신부는
`ThunderAgent/app.py:15-31,67-68,138-152`, 상태 객체는 `ThunderAgent/program/state.py:34-56`.

**[측정]** 단, **원본** 트레이스에는 상위 계층이 있다.
`scratch/traces/syfi_coding_trace.jsonl.gz` 레코드에 `project` 필드가 있고
(예: `"project": "project_316d74f4"`), 357,161 rows / 4,265 sessions / **187 projects**.
project당 세션 수 p50=4, p90=32, max=288, 단일 세션 project 49개(26.2%).
(단 216,823 rows에는 `project` 키 자체가 없다 — 부분적으로만 채워진 필드.)

**[측정]** `prep_tracelab_mori_yunuikang.py`는 `session_id`로만 그룹핑하고
(`prep_tracelab_mori_yunuikang.py:148`) `project`를 **버린다**. 출력 스키마에도 없다.

> **결론(2)**: 현재 처리된 트레이스는 **세션 = 프로그램 1:1**, 계층은 `session → turn` 2단계뿐.
> `session → program → turn` 3단계는 원본에 재료(`project`)가 있으나 지금 트레이스에는 없다.

---

## 3. ★ context/KV 누적 여부

### 3-1. 턴 사이 — 누적된다 [측정]

`input_tokens`는 증분이 아니라 **그 턴 시점의 누적 프롬프트 크기**다.
드라이버가 `messages` 리스트를 세션 내내 유지하고
(`mori_replay_driver_yunuikang.py:90` 초기화 → `:104` user append → `:128` assistant append),
`Padder.build_user`가 **이미 쌓인 messages를 세어서** 부족분만 filler로 채운다
(`trace_replay_driver_yunuikang.py:107-113`, "already-accumulated prior messages").

실측 시퀀스 (`tracelab_moriM_L64k_yunuikang.jsonl`, 세션 `claude:00169aa8-...`, 49턴):

```
turn : input_tokens : cached_tokens : out  : tool_s
   0 :   4096 :      0 :  311 :   0.05
   1 :   6183 :   4095 :  179 :   0.03
   2 :   7130 :   6182 :  184 :   0.02
   3 :   8195 :   7129 :  557 :   0.03
   4 :  10312 :   8194 : 2419 :   0.01
   5 :  14459 :  10311 :  120 :   0.01
   6 :  16111 :  10311 :  209 :   0.04
   7 :  16682 :  16110 :  143 :   0.04
   8 :  16840 :  16110 :  150 :   0.03
   9 :  17460 :  16839 :  121 :   0.02
  10 :  19099 :  16839 :  218 :   0.02
  ...  (38턴 더) → 마지막 턴 input_tokens = 61925
```

`cached_tokens[t] ≈ input_tokens[t-1]` 패턴이 그대로 보인다 → 앞 턴 KV 재사용 구조.

**[측정]** 단조성 통계:

| 트레이스 | 세션 | input_tokens 단조 비감소 세션 |
|---|---|---|
| `tracelab_moriM_L64k_yunuikang.jsonl` | 3,514 | 2,869 (**81.6%**) |
| `tracelab_moriM_L64k_nohw_yunuikang.jsonl` | 3,514 | 2,869 (81.6%) |
| `tracelab_mori_L64k_yunuikang.jsonl` | 582 | 561 (**96.4%**) |

**[측정]** 나머지 18.4%는 감소 구간이 있다 (상대 낙폭 p50=13.4%, max=93.2%).
원인은 원본의 컨텍스트 비단조(compaction/트렁케이션)이고, prep이 이를 인정하고 처리한다:
윈도우 **최솟값** 기준으로 rebase한다 (`prep_tracelab_mori_yunuikang.py:205-207`,
주석: "context is non-monotonic"). 그래서 moriM은 turn0 값이 52가지(4096~31046)로 흩어지고,
`tracelab_mori_L64k`는 turn0이 전부 4096으로 딱 떨어진다.

### 3-2. 프로그램 사이 — 누적되지 않는다 (누적할 대상이 없다) [측정+추론]

**[측정]** 한 세션당 프로그램은 하나뿐이므로(§2) "프로그램을 넘는 누적"이 정의되지 않는다.
**[측정]** 같은 세션이 다음 cycle에 재사용될 때는 `program_id`가 `#c0 → #c1`로 바뀌고
(`mori_replay_driver_yunuikang.py:205`), `run_session`이 `messages`를 system 프롬프트 하나로
**리셋**한다 (`mori_replay_driver_yunuikang.py:90`). seed도 cycle마다 달라져
filler가 dedup되지 않는다 (`:205`, base 주석 `trace_replay_driver_yunuikang.py:317-319`).
→ **cycle 간 KV 이월 0**. 오히려 의도적으로 warm-cache를 막는 설계
(`mori_replay_driver_yunuikang.py:196-198`).

**[측정, 정황]** 원본에는 세션 시작 시점의 외부 컨텍스트 상속 흔적이 있다:
round_index=0인 4,265 세션 중 **3,110개(72.9%)가 `prefix_tokens > 0`** (양수 중앙값 10,176).
**[추정]** 이건 project 내 세션 간 캐시 공유 또는 resume/compact의 결과일 수 있으나,
`prefix_tokens` 정의를 확인하지 않았으므로 단정하지 않는다.

---

## 4. 리플레이 드라이버의 concurrency 단위

**[측정] 단위 = 세션(=프로그램) 전체.** 턴 단위가 아니다.

MORI 드라이버(고정 1시간 closed-loop):
- `--concurrency C` (`mori_replay_driver_yunuikang.py:411`) 만큼 **영속 워커** 생성
  (`:265-269`).
- 각 워커 루프: `deadline` 전이면 제너레이터에서 세션 하나를 뽑아
  **끝까지 실행**하고 다음 세션을 뽑음 (`_worker`, `:209-215`).
- 코퍼스는 무한 cycler, cycle마다 순서 셔플 (`corpus_cycler`, `:193-206`).
- 세션 내부는 턴 순차 `for rec in turns` — 턴 병렬 없음 (`run_session`, `:94`).
- `deadline + deadline_grace_s`(기본 45s)에 in-flight 세션 강제 취소, 부분 세션은 미집계
  (`:270-279`).

**[측정] 버그성 관찰**: `asyncio.Semaphore(args.concurrency)`를 만들어(`:262`)
`_worker`에 넘기지만(`:267`) `_worker`/`run_session` 어디서도 `sem`을 쓰지 않는다
(`:209-215`, `:84-139`). 동시성은 **워커 개수로만** 강제된다. 결과값은 같지만 죽은 인자다.
(base 드라이버는 반대로 `async with sem`을 실제로 쓴다 — `trace_replay_driver_yunuikang.py:211`.)

**[측정]** base 드라이버는 run-to-completion: `build_program_list`로 프로그램 리스트를 만들고
(`trace_replay_driver_yunuikang.py:306-322`) `asyncio.gather` + Semaphore(C)
(`:337-341`, `:350-354`).

---

## 5. wall 시간 계산 필드 (30분 cut용)

**[측정]** 트레이스에 timestamp가 없으므로 **실측 wall은 트레이스만으로 구할 수 없다**.
대신 두 성분으로 **추정 가능**하고, prep이 실제로 그렇게 한다:

- `T_acting` = `sum(tool_duration_s)` — 이미 필드에 있음 (`prep_tracelab_mori_yunuikang.py:260`)
- `T_reasoning` proxy = `uncached/8000 + output/152`
  (`prep_tracelab_mori_yunuikang.py:57-58`, `:255`)
  — `uncached = input_tokens - cached_tokens`로 트레이스에서 복원 가능.
  (meta.json에는 `"reasoning_proxy": "uncached/8000 + output/145"`로 옛 상수가 남아있음.)

**[측정]** 런타임 쪽에는 `program_latency_s`가 있다 (`mori_replay_driver_yunuikang.py:137`)
— 실제 실행 후에만 얻어진다.

### tool 시간 분포 (`tracelab_moriM_L64k_yunuikang.jsonl`, n=117,257턴)

| | zero | p50 | p90 | p99 | max | 합계 |
|---|---|---|---|---|---|---|
| primary (human-wait 포함) | 11.0% | 0.195s | 30.01s | 300.0s | 300.0s | 1,998,282s |
| nohw (ablation) | 15.1% | 0.123s | 6.66s | 159.6s | 300.0s | 775,076s |
| `tracelab_mori_L64k` (구 트레이스) | 6.8% | 0.179s | 1.91s | 9.9s | 32.3s | 7,794s |

human-wait 주입이 **tool 시간 총합을 2.6배**로 키운다. 300s는 `CAP_HARD` clamp
(`prep_tracelab_mori_yunuikang.py:53`)이고 p99가 정확히 300.0이라 **꼬리가 clamp에 붙어있다**.

### 세션 단위 (moriM primary, 3,514 세션)

| 성분 | p50 | p90 | p99 | max |
|---|---|---|---|---|
| `sum(tool_duration_s)` | 147.1s | 1,520.8s | 4,565.6s | 28,670s |
| reasoning proxy | 74.8s | 261.5s | 414.7s | 910.8s |
| **추정 wall (합)** | **251.9s** | **1,748.8s** | **4,859.0s** | **28,820.8s** |

**[측정]** 추정 wall > 1800s인 세션 = **333/3,514 (9.5%)**, 그런데 이들이
전체 추정 시간의 **46.4%**를 차지한다. 전체 코퍼스 추정 시간 합 = 662.5시간.

> **[추론]** 30분 cut을 적용하면 세션 수는 9.5%만 잘리지만 **시간의 46%가 잘린다.**
> 1시간 closed-loop에서 `--concurrency 20`이면 워커 슬롯 20 × 3600s = 20시간 예산인데,
> p90 세션 하나가 1,749s(29분)라 워커 하나가 1시간 동안 세션 2개 정도만 소화한다.
> 현재 `deadline_grace_s=45s`(`mori_replay_driver_yunuikang.py:413`)는 max 28,820s 세션에
> 비하면 사실상 즉시 취소이므로, 긴 세션은 거의 항상 미완료로 버려진다.

---

## 6. input_tokens 분포

**[측정]** `tracelab_moriM_L64k_yunuikang.jsonl` (117,257턴 / 3,514세션):

| 항목 | p50 | p90 | p99 | max |
|---|---|---|---|---|
| per-turn `input_tokens` | 32,376 | 58,613 | 64,748 | 65,536 |
| 세션 peak 누적 context | 54,986 | 65,244 | 65,519 | 65,536 |
| 세션당 턴 수 | 21 | 75 | — | 512 (min 4) |
| 세션 `sum(output_tokens)` | 9,672 | 34,927 | — | 129,154 |

per-turn 평균 32,819. peak는 `L=65536` 상한에 딱 붙어 잘려 있다
(`prep_tracelab_mori_yunuikang.py:52` 부근 `L`, 윈도우 조건은 `:156-158`).

**[측정]** `tracelab_mori_L64k_yunuikang.jsonl` (9,290턴 / 582세션): per-turn p50=27,922,
peak p50=44,156, 턴 수 p50=11. moriM이 세션 수 6배·턴 수 2배로 훨씬 큰 코퍼스다.

**[추론]** 세션 peak p50이 55k / p90이 65k인데 드라이버 기본 `--ctx-cap 65536`
(`mori_replay_driver_yunuikang.py:415`)이므로, 상당수 세션이 실행 중
"trim oldest (user,assistant) pairs" 경로(`:101-103`)를 탄다 → **재생된 KV가 트레이스의
누적 곡선을 그대로 따라가지 않고 중간에 앞턴이 잘려 나간다.**

---

## 판정

### Q: "세션 안에서 프로그램들이 순차로 돌고 KV가 누적되는" 구조를 데이터가 지원하는가?

**아니오 — 지금 트레이스로는 안 된다. 재생성/가공이 필요하다.**

근거:

1. **[측정]** 트레이스에 `program_id`가 아예 없다. 6-키 스키마에 없고
   (117,257줄 전수 확인), `prep_tracelab_mori_yunuikang.py:257-263` 출력에도 없다.
   `program_id`는 드라이버가 `f"{sid}#c{cycle}"`로 **합성**한다
   (`mori_replay_driver_yunuikang.py:205`).
2. **[측정]** 코드가 `"""One session=program."""`이라고 명시한다
   (`mori_replay_driver_yunuikang.py:85`). 계층은 `session → turn` 2단계.
3. **[측정]** 누적은 **턴 사이에만** 일어난다 (81.6% 단조 비감소, `cached_tokens[t] ≈
   input_tokens[t-1]`). cycle이 바뀌면 `messages`가 리셋되어
   (`mori_replay_driver_yunuikang.py:90`) 프로그램 간 이월은 0이고, 이는 버그가 아니라
   prefix-cache 인위적 warm을 막으려는 **의도된 설계**다 (`:196-198`, `:349-358` gate).
4. **[측정]** 현재 concurrency 단위는 **이미 세션 단위**다 (`_worker`가 세션 하나를
   끝까지 잡음, `:209-215`). 즉 "세션 단위 concurrency"만 원한다면 **추가 작업 불필요**.

### 그럼 무엇이 필요한가

**[추론]** "세션 안에 프로그램 여러 개"를 원한다면 3단계 계층을 새로 만들어야 하고,
**재료는 원본에 있다**:

- `syfi_coding_trace.jsonl.gz`의 `project`(187개) → 새 `session_id`
- 원본 `session_id`(4,265개) → 새 `program_id`
- 원본 `round_index` → `turn`

즉 `prep_tracelab_mori_yunuikang.py:148`의 그룹핑 키를 `session_id` → `project`로 바꾸고
`program_id`를 emit하는 **새 prep 스크립트**(기존 파일 수정 금지 규칙에 따라 신규 파일)를
만들면 된다. 다만 주의:

- **[측정]** 원본 rows의 60.7%(216,823/357,161)에 `project` 키가 **없다** → 그 rows는
  버리거나 별도 처리해야 하고, 코퍼스가 크게 줄어든다.
- **[측정]** project당 세션 p50=4지만 26.2%는 단일 세션 → 그 project는 여전히 1:1.
- **[추론]** 프로그램 간 KV 누적을 실제로 재생하려면 `mori_replay_driver`의
  `messages` 리셋 지점(`:90`)을 프로그램 경계가 아니라 세션 경계로 옮겨야 하는데,
  그러면 64k `ctx_cap`이 훨씬 빨리 포화해 trim 경로(`:101-103`)가 지배적이 된다.
  peak p50이 이미 55k이므로 프로그램 2개만 이어붙여도 상한을 넘는다 → `--ctx-cap`
  상향(엔진 재기동)이 동반돼야 한다.
