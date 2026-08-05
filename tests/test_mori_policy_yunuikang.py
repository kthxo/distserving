"""A1~A7: MORI 스케줄러 **정책 충실성** 합성(known-answer) 테스트.

정답의 근거는 "현재 코드가 내는 값"이 아니라 **논문 정책 스펙**이다.
각 테스트는 세팅 -> 기대(스펙) -> assert 구조이며, 정책이 틀렸다면 반드시 실패하도록
구성했다(반례 정책이 다른 답을 내는 픽스처를 골랐다).

실행:
    python tests/test_mori_policy_yunuikang.py          # 자체 러너 (이 환경엔 pytest 미설치)
    python -m pytest tests/test_mori_policy_yunuikang.py -v   # pytest가 있으면 그대로 동작

STEP 1 감사 결과 반영된 판정 기준:
  * A3b (promote 그룹 우선순위 > ι): 논문 §4.3.1이 "그룹 우선순위(툴콜 완료 CPU -> 복귀 Waiting
    -> 신규), 각 레벨 내에서 ι 최저"를 명시 => **PASS 기준**. 관측값은 기록만.
  * A6 (ι = 합의 비, ratio-of-sums): 논문 식(1)이 곧 합의 비 => **PASS 기준**.
    average-of-ratios가 오히려 스펙 이탈. crossover는 responsiveness의 정상 특성으로 기록.
  * A7: typed eviction의 엔진측 정렬 함수는 sglang 클로저-로컬이고 sglang 미설치 =>
    격리 호출 불가. 재구현하지 않고 우리 코드(_type_rank, _mori_evict_cpu)만 검증.
"""
import os
import sys
import time

# `python tests/xxx.py`(sys.path[0]=tests/)와 `python -m pytest`(cwd=repo root) 양쪽에서
# ThunderAgent / mori_harness_yunuikang 를 모두 임포트할 수 있게 한다.
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from ThunderAgent.program.state import ProgramState, ProgramStatus
from ThunderAgent.scheduler.mori_idleness import IdlenessWindow

from mori_harness_yunuikang import (  # noqa: E402
    BUFFER_PER_PROGRAM,
    MoriHarness,
    make_harness,
    make_program,
    slots,
)

# 보고서에 실을 [측정] 관측 기록
OBS: list = []


def obs(test_id: str, text: str) -> None:
    OBS.append((test_id, text))
    print(f"    [측정] {test_id}: {text}")


# =============================================================================
# A1 — 스티키 배치: 압박이 없으면 ι가 변해도 재배치하지 않는다
# =============================================================================

def test_A1_sticky_no_rebalance_without_pressure():
    """스펙: 프로그램은 (a) 용량 위반 강제 demote 또는 (b) 상위 tier 여유로 promote
    되기 전까지 현재 tier에 머문다. ι가 변했다는 이유만으로 매 틱 재배치하지 않는다.

    세팅: GPU 4칸에 A,B 2개만 (여유 2칸). 10틱 동안 A의 ι를 0.1 <-> 0.9로 진동.
    기대: tier 이동 0회, pause 마킹 0회.
    실패하면: ι 기반 매틱 재배치(스티키 위반).
    """
    h = make_harness(gpu_slots=4, cpu_slots=2, min_dwell_ticks=1)
    try:
        a = h.place_gpu(make_program("A", tokens=400, iota=0.1))
        b = h.place_gpu(make_program("B", tokens=400, iota=0.5))

        before = h.snapshot()
        moves = 0
        iota_trace = []
        for i in range(10):
            # ι를 흔든다: A는 매 틱 busy <-> idle 왕복
            from mori_harness_yunuikang import set_iota
            set_iota(a, 0.9 if i % 2 else 0.1)
            h.tick()
            iota_trace.append(round(h.iota(a), 2))
            if h.snapshot() != before:
                moves += 1

        gpu, cpu, wait = h.tiers()
        obs("A1", f"10틱 ι 궤적 A={iota_trace} -> tier 이동 {moves}회, "
                  f"gpu={sorted(gpu)}, cpu={sorted(cpu)}, waiting={sorted(wait)}, "
                  f"marked A={a.marked_for_pause} B={b.marked_for_pause}, "
                  f"moved_tick A={a.moved_tick} B={b.moved_tick}, tick={h.router._tick}")

        assert moves == 0, f"압박 없는데 tier가 {moves}회 바뀜 (스티키 위반)"
        assert gpu == {"A", "B"}, f"두 프로그램 모두 GPU 잔류해야 함, 실제 gpu={gpu}"
        assert not a.marked_for_pause and not b.marked_for_pause, "압박 없는데 pause 마킹됨"
        assert a.moved_tick is None and b.moved_tick is None, "이동이 없었는데 moved_tick이 찍힘"
    finally:
        h.close()


# =============================================================================
# A2 — Demotion: ι가 가장 높은 프로그램을 내린다 (+ ACTING 우선 + REASONING lazy)
# =============================================================================

def test_A2a_demote_picks_highest_iota():
    """스펙: demote가 필요하면 **idleness(ι)가 가장 높은** 프로그램을 GPU->CPU로 내린다.

    세팅: GPU 2칸(=1000tok). A(400tok, i=0.1) B(250tok, i=0.9) C(250tok, i=0.2) 모두 ACTING.
          used = 900 + 3x100 = 1200 > 1000 -> 1개 demote 강제.
    기대: B(최고 ι)가 내려가고 A는 유지.
    반례 구분: context-length 내림차순 정책이면 A(400tok, 최대)를 내린다 -> 다른 답.
               LRU/FIFO 정책이면 A(첫 등록)를 내린다 -> 다른 답.
    """
    h = MoriHarness(gpu_capacity=1000, cpu_capacity=slots(3, 400))
    try:
        a = h.place_gpu(make_program("A", tokens=400, iota=0.1))
        b = h.place_gpu(make_program("B", tokens=250, iota=0.9))
        c = h.place_gpu(make_program("C", tokens=250, iota=0.2))
        obs("A2a", f"틱 전: gpu_remaining={h.gpu_remaining()} (음수=초과), "
                   f"i(A)={h.iota(a):.2f} i(B)={h.iota(b):.2f} i(C)={h.iota(c):.2f}, "
                   f"tokens A=400 B=250 C=250")

        h.tick()

        gpu, cpu, wait = h.tiers()
        demoted = sorted(cpu | wait)
        obs("A2a", f"틱 후: demote된 pid={demoted} "
                   f"(i={[round(h.iota(h.router.programs[p]), 2) for p in demoted]}), "
                   f"gpu={sorted(gpu)}, gpu_remaining={h.gpu_remaining()}")

        assert len(demoted) == 1, f"1개만 내려가면 충분한데 {len(demoted)}개 내려감: {demoted}"
        assert demoted == ["B"], f"최고 ι(B, 0.9)가 내려가야 함. 실제 내려간 것: {demoted}"
        assert a.tier == "gpu", "최저 ι인 A가 GPU에 남아야 함 (context-len 정책이면 A가 내려감)"
        assert c.tier == "gpu"
        assert h.gpu_remaining() >= 0, "demote 후에도 GPU 용량 초과"
    finally:
        h.close()


def test_A2b_acting_demoted_before_reasoning():
    """스펙(§4.3.1): demote 후보는 ACTING(툴 실행 중, off-GPU)을 REASONING보다 **먼저** 고른다.

    세팅: GPU 2칸(=1000tok). R(250tok, i=0.99, REASONING) A(400tok, i=0.5, ACTING)
          C(250tok, i=0.2, ACTING). used=1200 > 1000.
    기대: 전체 최고 ι는 R(0.99)이지만 **ACTING 중 최고 ι인 A**가 먼저 내려간다.
          R은 GPU에 남고 마킹도 되지 않는다(1개 내리면 용량이 해소되므로).
    반례 구분: 상태 무시하고 전역 ι 정렬이면 R이 먼저 마킹/이동 -> 다른 답.
    """
    h = MoriHarness(gpu_capacity=1000, cpu_capacity=slots(3, 400))
    try:
        r = h.place_gpu(make_program("R", tokens=250, iota=0.99, status=ProgramStatus.REASONING))
        a = h.place_gpu(make_program("A", tokens=400, iota=0.5, status=ProgramStatus.ACTING))
        c = h.place_gpu(make_program("C", tokens=250, iota=0.2, status=ProgramStatus.ACTING))
        obs("A2b", f"틱 전: i(R)={h.iota(r):.2f}(REASONING, 전역 최고) "
                   f"i(A)={h.iota(a):.2f}(ACTING) i(C)={h.iota(c):.2f}(ACTING), "
                   f"gpu_remaining={h.gpu_remaining()}")

        h.tick()

        gpu, cpu, wait = h.tiers()
        obs("A2b", f"틱 후: gpu={sorted(gpu)}, cpu={sorted(cpu)}, waiting={sorted(wait)}, "
                   f"R.marked_for_pause={r.marked_for_pause}, R.tier={r.tier}")

        assert a.tier != "gpu", ("ACTING 중 최고 ι인 A가 먼저 내려가야 함. "
                                 f"실제 A.tier={a.tier}")
        assert r.tier == "gpu", f"REASONING인 R은 ACTING 후보가 남아있는 한 유지되어야 함 (실제 {r.tier})"
        assert not r.marked_for_pause, ("ACTING 1개로 용량이 해소됐으므로 REASONING R은 "
                                        "마킹조차 되면 안 됨 (전역 ι 정렬 정책이면 R이 먼저 걸림)")
    finally:
        h.close()


def test_A2c_reasoning_only_is_lazy_demotion():
    """스펙(§4.3.1): ACTING 후보가 없으면 REASONING을 **lazy demotion**한다 —
    현재 스텝을 끝내고(=ACTING이 될 때) 이동하며, 틱 안에서 즉시 KV를 뺏지 않는다.

    세팅: GPU 1칸 상당(=900tok)에 REASONING만 둘: R1(400, i=0.8) R2(400, i=0.2). used=1000>900.
    기대: (1) 틱 안에서 R1/R2가 tier 이동을 하지 않는다 (여전히 gpu, ACTIVE, backend에 등록됨).
          (2) 대신 marked_for_pause가 서고 future_paused_tokens가 잡힌다.
          (3) 최고 ι(R1)가 먼저 마킹된다.
          (4) 마킹된 프로그램이 ACTING이 되면(_clear_mark_and_pause) 그때 CPU tier로 간다.
    """
    h = MoriHarness(gpu_capacity=900, cpu_capacity=slots(3, 400))
    try:
        r1 = h.place_gpu(make_program("R1", tokens=400, iota=0.8, status=ProgramStatus.REASONING))
        r2 = h.place_gpu(make_program("R2", tokens=400, iota=0.2, status=ProgramStatus.REASONING))
        backend = h.router.backends[h.urls[0]]

        h.tick()

        gpu, cpu, wait = h.tiers()
        n_marked = int(r1.marked_for_pause) + int(r2.marked_for_pause)
        obs("A2c", f"틱 후(즉시 이동 없음 확인): gpu={sorted(gpu)}, cpu={sorted(cpu)}, "
                   f"waiting={sorted(wait)}, marked R1={r1.marked_for_pause} R2={r2.marked_for_pause}, "
                   f"future_paused_tokens={backend.future_paused_tokens}, "
                   f"R1.state={r1.state.value}")

        # (1) lazy: 틱 안에서 이동하지 않았다
        assert r1.tier == "gpu" and r2.tier == "gpu", "REASONING이 틱 안에서 즉시 이동함 (lazy 위반)"
        assert r1.state is ProgramState.ACTIVE, "REASONING이 틱 안에서 PAUSED로 전환됨 (lazy 위반)"
        assert backend._programs.get("R1") is r1, "REASONING이 틱 안에서 backend에서 해제됨 (lazy 위반)"
        # (2)(3) 마킹은 되어야 하고, 최고 ι가 먼저
        assert r1.marked_for_pause, "용량 초과인데 REASONING이 pause 마킹조차 안 됨"
        assert backend.future_paused_tokens > 0, "future_paused_tokens 회계 누락"

        # (4) ACTING 전환 시점에 실제 이동 (데이터플레인 경로의 실제 코드)
        r1.status = ProgramStatus.ACTING
        h.router._clear_mark_and_pause("R1", r1)
        obs("A2c", f"_clear_mark_and_pause 후: R1.tier={r1.tier}, R1.state={r1.state.value}, "
                   f"cpu_tier={sorted(h.router.cpu_tiers[h.urls[0]]._programs)}, "
                   f"future_paused_tokens={backend.future_paused_tokens}")
        assert r1.tier == "cpu", (f"마킹된 프로그램은 ACTING 전환 시 CPU tier로 가야 함 "
                                  f"(KV 보존). 실제 {r1.tier}")
        assert not r1.marked_for_pause, "이동 후에도 마킹이 남음"

        # 관측: REASONING만 남았을 때 몇 개가 마킹됐는지 (over-marking 여부)
        obs("A2c", f"[특성] 초과분은 100tok(1개 마킹이면 충분)인데 실제 마킹된 REASONING 수 = "
                   f"{n_marked} / 2 (R2.marked={r2.marked_for_pause}) — "
                   f"remaining_capacity()가 future_paused_tokens를 차감하지 않아 "
                   f"(backend/state.py:185-194) 마킹 루프가 REASONING 전부를 훑는다")
    finally:
        h.close()


# =============================================================================
# A3 — Promotion: (그룹 우선순위) 그 다음 그룹 내 ι 최소
# =============================================================================

def test_A3_promote_picks_lowest_iota_within_group():
    """스펙(§4.3.1): GPU 용량이 나면 각 레벨(그룹) 내에서 **ι가 최소인** 프로그램을 올린다.

    세팅: GPU 2칸(=1000tok)에 X(400, i=0.5) 상주 -> 여유 1칸(remaining=500).
          CPU tier: C(400, i=0.8) D(400, i=0.3). **둘 다 ACTING** = 동일 그룹(cpu_idle).
    기대: 그룹이 같으므로 순수 ι 최소인 D가 올라간다. C는 CPU 잔류(자리 없음).
    반례 구분: ι 내림차순이면 C, 삽입순(FIFO)이면 C(먼저 admit) -> 다른 답.
    """
    h = MoriHarness(gpu_capacity=1000, cpu_capacity=slots(3, 400))
    try:
        x = h.place_gpu(make_program("X", tokens=400, iota=0.5))
        c = h.place_cpu(make_program("C", tokens=400, iota=0.8, status=ProgramStatus.ACTING))
        d = h.place_cpu(make_program("D", tokens=400, iota=0.3, status=ProgramStatus.ACTING))
        obs("A3", f"틱 전: gpu_remaining={h.gpu_remaining()} (필요={400 + BUFFER_PER_PROGRAM}), "
                  f"CPU tier(admit 순서)=[C(i={h.iota(c):.2f}), D(i={h.iota(d):.2f})] 둘 다 ACTING")

        h.tick()

        gpu, cpu, wait = h.tiers()
        obs("A3", f"틱 후: promote된 pid={sorted(gpu - {'X'})}, gpu={sorted(gpu)}, "
                  f"cpu={sorted(cpu)}, gpu_remaining={h.gpu_remaining()}, D.moved_tick={d.moved_tick}")

        assert d.tier == "gpu", (f"그룹 내 ι 최소인 D(0.3)가 올라가야 함. "
                                 f"실제 D.tier={d.tier}, C.tier={c.tier}")
        assert c.tier == "cpu", f"자리가 1칸뿐이므로 C(0.8)는 CPU 잔류해야 함. 실제 {c.tier}"
        assert d.state is ProgramState.ACTIVE and d.backend_url == h.urls[0]
        assert h.gpu_remaining() >= 0, "promote가 GPU 용량을 초과시킴 (admission control 위반)"
        assert x.tier == "gpu"
    finally:
        h.close()


def test_A3b_group_priority_precedes_iota():
    """스펙(§4.3.1): 레벨(그룹) 우선순위가 ι보다 **앞선다** —
    툴콜을 마치고 요청이 걸린 CPU 프로그램(cpu_pending) > 유휴 CPU 프로그램(cpu_idle).
    ι는 각 레벨 **내부**의 정렬키다.

    세팅: GPU 여유 1칸. CPU tier: P(i=0.9, REASONING=요청 대기중=cpu_pending),
          Q(i=0.1, ACTING=cpu_idle).
    기대: ι는 P가 훨씬 높지만 **P가 먼저** 올라간다 (그룹 우선순위).
    반례 구분: 그룹 무시하고 순수 ι 최소면 Q -> 다른 답.
    """
    h = MoriHarness(gpu_capacity=1000, cpu_capacity=slots(3, 400))
    try:
        h.place_gpu(make_program("X", tokens=400, iota=0.5))
        p = h.place_cpu(make_program("P", tokens=400, iota=0.9, status=ProgramStatus.REASONING))
        q = h.place_cpu(make_program("Q", tokens=400, iota=0.1, status=ProgramStatus.ACTING))
        obs("A3b", f"틱 전: P(i={h.iota(p):.2f}, REASONING=cpu_pending) vs "
                   f"Q(i={h.iota(q):.2f}, ACTING=cpu_idle), gpu_remaining={h.gpu_remaining()}")

        h.tick()

        obs("A3b", f"틱 후: promote된 것 = {'P' if p.tier == 'gpu' else ('Q' if q.tier == 'gpu' else '없음')}"
                   f" -> P.tier={p.tier}(i={h.iota(p):.2f}), Q.tier={q.tier}(i={h.iota(q):.2f})")

        assert p.tier == "gpu", (f"§4.3.1: 요청이 걸린 CPU 프로그램(cpu_pending)이 ι가 높아도 "
                                 f"먼저 올라가야 함. 실제 P.tier={p.tier}")
        assert q.tier == "cpu", f"자리 1칸 — 하위 그룹 Q는 잔류. 실제 {q.tier}"
    finally:
        h.close()


# =============================================================================
# A4 — Admission control: 두 tier를 용량까지 채우는 것이 곧 admission control
# =============================================================================

def test_A4_both_tiers_bounded_and_full():
    """스펙: GPU/CPU 각 tier를 용량까지 채우는 것이 admission control. 두 tier 모두 유한.

    세팅: 프로그램 6개(각 400tok, i=0.1..0.6, 전부 ACTING)를 전부 GPU에 얹고 1틱.
          GPU 2칸(=1000tok), CPU 2칸(=1000tok).
    기대: GPU 2 + CPU 2 + waiting 2. 어느 tier도 용량 초과 없음. 두 tier 모두 '꽉 참'
          (400짜리 하나 더 못 들어감). GPU에 남는 것은 ι 최소 2개.
    """
    h = make_harness(gpu_slots=2, cpu_slots=2, tokens=400)
    try:
        progs = {}
        for i, io in enumerate([0.1, 0.2, 0.3, 0.4, 0.5, 0.6], start=1):
            progs[f"P{i}"] = h.place_gpu(make_program(f"P{i}", tokens=400, iota=io))
        obs("A4", f"틱 전: 6개 전부 GPU, gpu_remaining={h.gpu_remaining()} (초과), "
                  f"GPU cap={slots(2, 400)}, CPU cap={slots(2, 400)}")

        h.tick()

        gpu, cpu, wait = h.tiers()
        need = 400 + BUFFER_PER_PROGRAM
        obs("A4", f"틱 후: gpu={sorted(gpu)} cpu={sorted(cpu)} waiting={sorted(wait)}; "
                  f"gpu_remaining={h.gpu_remaining()}, cpu_remaining={h.cpu_remaining()}, "
                  f"한 칸 더 필요량={need}")

        assert len(gpu) == 2, f"GPU는 2칸 -> 2개여야 함. 실제 {sorted(gpu)}"
        assert len(cpu) == 2, f"CPU는 2칸 -> 2개여야 함. 실제 {sorted(cpu)}"
        assert len(wait) == 2, f"나머지 2개는 waiting이어야 함. 실제 {sorted(wait)}"
        # 어느 tier도 초과하지 않는다
        assert h.gpu_remaining() >= 0, f"GPU 용량 초과: remaining={h.gpu_remaining()}"
        assert h.cpu_remaining() >= 0, f"CPU tier 용량 초과: remaining={h.cpu_remaining()}"
        # 두 tier 모두 꽉 찼다 (admission control이 과소 수용하지 않았다)
        assert h.gpu_remaining() < need, f"GPU에 자리가 남는데 안 채움: remaining={h.gpu_remaining()}"
        assert h.cpu_remaining() < need, f"CPU에 자리가 남는데 안 채움: remaining={h.cpu_remaining()}"
        # GPU에 남은 것은 ι 최소 2개
        assert gpu == {"P1", "P2"}, f"GPU에는 ι 최소 2개(P1,P2)가 남아야 함. 실제 {sorted(gpu)}"
    finally:
        h.close()


# =============================================================================
# A5 — Relative (논문 제목): 용량비가 바뀌면 분할 경계가 따라 움직인다
# =============================================================================

def _run_A5(gpu_slots: int):
    h = make_harness(gpu_slots=gpu_slots, cpu_slots=4, tokens=400)
    try:
        for name, io in [("A", 0.1), ("B", 0.4), ("C", 0.6), ("D", 0.9)]:
            h.place_gpu(make_program(name, tokens=400, iota=io))
        h.tick()
        gpu, cpu, wait = h.tiers()
        return gpu, cpu, wait, h.gpu_remaining()
    finally:
        h.close()


def test_A5_partition_boundary_adapts_to_capacity():
    """스펙: 프로그램을 **상대적** ι로 랭크하고, GPU:CPU 용량비가 바뀌면 분할 경계가
    적응한다(하드웨어별 튜닝 없이). 고정 임계/고정 비율이 아니다.

    세팅: 동일한 프로그램 집합 A/B/C/D (i=0.1/0.4/0.6/0.9)를 GPU 2칸, 그 다음 GPU 3칸으로 두 번.
    기대: 2칸 -> GPU={A(.1), B(.4)}; 3칸 -> GPU={A(.1), B(.4), C(.6)}. 경계가 용량 따라 이동.
    반례 구분: 고정 ι 임계(예: 0.5)면 두 경우 모두 같은 분할({A,B}) -> 실패.
    """
    gpu2, cpu2, wait2, rem2 = _run_A5(gpu_slots=2)
    gpu3, cpu3, wait3, rem3 = _run_A5(gpu_slots=3)
    obs("A5", f"GPU 2칸 -> gpu={sorted(gpu2)} cpu={sorted(cpu2)} (remaining={rem2})")
    obs("A5", f"GPU 3칸 -> gpu={sorted(gpu3)} cpu={sorted(cpu3)} (remaining={rem3})")
    obs("A5", f"분할 경계: 2칸에서는 i<=0.4까지, 3칸에서는 i<=0.6까지 GPU 유지 "
              f"-> 경계가 용량에 따라 이동={gpu2 != gpu3}")

    assert gpu2 == {"A", "B"}, f"GPU 2칸이면 ι 최소 2개. 실제 {sorted(gpu2)}"
    assert gpu3 == {"A", "B", "C"}, f"GPU 3칸이면 ι 최소 3개. 실제 {sorted(gpu3)}"
    assert gpu2 != gpu3, ("용량을 바꿨는데 분할이 동일 -> 고정 임계 기반 (상대성 위반)")
    assert gpu2 < gpu3, "경계는 용량이 늘면 확장되어야 함 (포함관계)"


# =============================================================================
# A6 — Idleness 지표: robust + responsive (+ now 주입 진행중 콜)
# =============================================================================

def test_A6a_robust_single_outlier_does_not_flip_to_idle():
    """스펙: robust — busy phase 중 **긴 콜 1회 같은 outlier에 흔들리지 않는다**.

    세팅(k=5): reasoning 10s x5 고정. acting = [0.5, 0.5, 5.0, 0.5, 0.5]
               (짧은 콜 0.5s 사이에 5s 짜리 한 번 = 10배 outlier).
    기대: ι가 여전히 busy 쪽 — _type_rank가 busy(=2)를 유지하고 ι < 0.33.
    """
    base = IdlenessWindow(k=5)
    for _ in range(5):
        base.push_acting(0.5)
        base.push_reasoning(10.0)
    i_base = base.value()

    w = IdlenessWindow(k=5)
    for dt in (0.5, 0.5, 5.0, 0.5, 0.5):
        w.push_acting(dt)
        w.push_reasoning(10.0)
    i_out = w.value()

    # 완전 idle 프로그램(비교군)
    idle = IdlenessWindow(k=5)
    for _ in range(5):
        idle.push_acting(30.0)
        idle.push_reasoning(10.0)
    i_idle = idle.value()

    h = make_harness(gpu_slots=2, cpu_slots=2)
    try:
        p = make_program("O", iota=0.0)
        p.idle_window = w
        rank = h.router._type_rank(p, time.time())
    finally:
        h.close()

    obs("A6a", f"busy 기준선 i={i_base:.4f}; outlier 1회(5s) 포함 i={i_out:.4f} "
               f"(delta={i_out - i_base:+.4f}); 완전 idle i={i_idle:.4f}; "
               f"_type_rank(outlier)={rank} (2=busy,1=mixed,0=idle)")

    assert i_out < 0.33, f"outlier 1회로 busy 구간(<0.33)을 벗어남: i={i_out:.4f}"
    assert rank == 2, f"outlier 1회로 타입이 busy(2)에서 이탈: rank={rank}"
    assert i_out < i_idle / 2, (f"outlier 1회 프로그램이 진짜 idle 프로그램에 근접함 "
                                f"(i_out={i_out:.4f}, i_idle={i_idle:.4f})")


def test_A6b_responsive_ongoing_tool_call_raises_iota():
    """스펙: responsive — 진행 중인 긴 tool call이 ι를 시간에 따라 올려야 한다
    (스케줄러가 '지금 막 긴 콜에 들어간' 프로그램을 demote할 수 있게).
    now 주입으로 확인 (IdlenessWindow는 time.time()을 직접 부르지 않는다).

    세팅: busy 윈도우(acting 0.5 x5 / reasoning 10 x5)에서 t0에 툴콜 진입.
    기대: ι(now)가 경과시간에 대해 **단조 증가**하고, 충분히 길어지면 idle 쪽으로 넘어간다.
    """
    w = IdlenessWindow(k=5)
    for _ in range(5):
        w.push_acting(0.5)
        w.push_reasoning(10.0)
    t0 = 1_000_000.0
    xs = [0, 1, 5, 20, 60, 120, 300]
    vals = [w.value(now=t0 + x, acting_since=t0) for x in xs]
    obs("A6b", "진행중 콜 경과(s)->i: " + ", ".join(f"{x}s={v:.3f}" for x, v in zip(xs, vals)))

    assert all(b > a for a, b in zip(vals, vals[1:])), f"진행 중 콜인데 ι가 단조 증가하지 않음: {vals}"
    assert vals[0] < 0.1, f"콜 직후에는 busy여야 함: {vals[0]:.3f}"
    assert vals[-1] > 0.66, f"충분히 긴 진행중 콜이면 idle로 분류돼야 함: {vals[-1]:.3f}"

    # 특성 기록: busy->idle 넘어가는 경과시간 (responsiveness 지표)
    cross = next((x for x in range(0, 601) if w.value(now=t0 + x, acting_since=t0) >= 0.5), None)
    obs("A6b", f"[특성] busy 기준선(reasoning 10s x5)에서 진행중 콜이 i>=0.5를 넘기는 경과시간 "
               f"= {cross}s (논문 식(1) 합의 비의 정상 responsiveness)")


def test_A6c_responsive_phase_shift_within_k_ticks():
    """스펙: responsive — 오래된 표본을 폐기(k=5 슬라이딩)해 **phase 전환에 빠르게 반응**.

    세팅: busy 5스텝(acting 0.5/reasoning 10) 이후 idle 스텝(acting 30/reasoning 10)을 순차 push.
    기대: k=5 push 안에 ι가 busy(<0.1)에서 idle(>0.66)로 상승하고, 매 push마다 비감소.
          5회 push 후에는 옛 표본이 완전히 폐기되어 ι가 순수 idle 값이 된다.
    """
    w = IdlenessWindow(k=5)
    for _ in range(5):
        w.push_acting(0.5)
        w.push_reasoning(10.0)
    start = w.value()
    traj = [start]
    for _ in range(5):
        w.push_acting(30.0)
        w.push_reasoning(10.0)
        traj.append(w.value())
    obs("A6c", f"phase 전환 궤적 (push 0..5): {[round(v, 3) for v in traj]}")

    assert start < 0.1, f"시작이 busy가 아님: {start:.3f}"
    assert all(b >= a - 1e-12 for a, b in zip(traj, traj[1:])), f"ι가 비단조: {traj}"
    assert traj[-1] > 0.66, f"k=5 push 안에 idle로 못 올라감: {traj}"
    # 옛 표본 폐기 확인: 순수 idle 값 = 150/(150+50) = 0.75
    assert abs(traj[-1] - 0.75) < 1e-9, (f"k개 push 후에도 옛 표본 잔존 "
                                         f"(기대 0.75, 실제 {traj[-1]:.6f})")
    obs("A6c", f"[특성] k=5 push 후 i={traj[-1]:.4f} == 150/200 -> 옛 busy 표본 완전 폐기 확인. "
               f"i>0.5 도달까지 필요한 push 수 = "
               f"{next(i for i, v in enumerate(traj) if v > 0.5)}")


# =============================================================================
# A7 — Typed eviction (tier 내부 축출 순서)
#      주: 엔진(sglang)측 실제 축출 정렬 함수는 격리 호출 불가 -> §보고서 참조.
#          여기서는 우리 코드에 실재하는 순서 로직만 검증한다.
# =============================================================================

def test_A7a_type_rank_orders_busy_over_idle():
    """스펙: 타입 우선순위 — busy 계열이 idle/inactive 계열보다 GPU에 오래 남는다.
    구현: MoriRouter._type_rank(state, now) -> 높을수록 GPU 잔류 (payload["priority"]로 전달).

    기대: rank(busy) > rank(mixed) > rank(idle), 그리고 ι에 대해 비증가(monotone non-increasing).
    """
    h = make_harness(gpu_slots=2, cpu_slots=2)
    try:
        now = time.time()
        ranks = {}
        for io in [0.0, 0.1, 0.32, 0.34, 0.5, 0.65, 0.67, 0.9, 1.0]:
            p = make_program(f"t{io}", iota=io)
            ranks[io] = h.router._type_rank(p, now)
        obs("A7a", "i -> rank: " + ", ".join(f"{k}->{v}" for k, v in ranks.items()))

        assert ranks[0.1] > ranks[0.5] > ranks[0.9], (
            f"busy > mixed > idle 순서 위반: {ranks}")
        seq = [ranks[k] for k in sorted(ranks)]
        assert all(b <= a for a, b in zip(seq, seq[1:])), f"ι가 커질수록 rank가 비증가해야 함: {seq}"
    finally:
        h.close()


def test_A7b_cpu_tier_eviction_orders_by_type():
    """스펙: tier 내부 축출은 타입 우선순위를 따른다.
    구현: MoriRouter._mori_evict_cpu — CPU tier 초과 시 ι 최고(=idle 계열)부터 Waiting으로 축출.

    세팅: CPU tier 2칸(=1000tok)에 3개(각 400tok) 강제 admit -> 1개 축출 필요.
          E_idle(i=0.9), E_mixed(i=0.5), E_busy(i=0.1).
    기대: E_idle이 먼저 축출되고 busy/mixed는 잔류.
    반례 구분: 삽입순(FIFO)이면 E_idle이 마지막에 admit되므로 다른 답이 나오도록 순서를 뒤집어 둔다.
    """
    h = MoriHarness(gpu_capacity=0, cpu_capacity=1000)
    try:
        # admit 순서를 ι와 반대로: busy 먼저, idle 마지막
        e_busy = h.place_cpu(make_program("E_busy", tokens=400, iota=0.1))
        e_mixed = h.place_cpu(make_program("E_mixed", tokens=400, iota=0.5))
        e_idle = h.place_cpu(make_program("E_idle", tokens=400, iota=0.9))
        tier = h.router.cpu_tiers[h.urls[0]]
        obs("A7b", f"축출 전: admit 순서={[p for p, _ in tier.items()]}, "
                   f"cpu_remaining={tier.remaining()} (음수=초과)")

        h.router._mori_evict_cpu(tier, time.time())

        remaining = [p for p, _ in tier.items()]
        obs("A7b", f"축출 후: cpu tier={remaining}, "
                   f"축출된 것={[p for p in ('E_busy', 'E_mixed', 'E_idle') if p not in remaining]} "
                   f"(i: busy={h.iota(e_busy):.2f} mixed={h.iota(e_mixed):.2f} idle={h.iota(e_idle):.2f}), "
                   f"cpu_remaining={tier.remaining()}")

        assert e_idle.tier == "waiting", (f"idle 계열(i=0.9)이 먼저 축출돼야 함. "
                                          f"실제 남은 것={remaining}")
        assert e_busy.tier == "cpu" and e_mixed.tier == "cpu", "busy/mixed가 잘못 축출됨"
        assert tier.remaining() >= 0, "축출 후에도 CPU tier 용량 초과"
    finally:
        h.close()


def test_A7c_same_type_tie_break_is_lru():
    """스펙: 타입 우선순위 + **동타입 LRU tie-break**.

    세팅: CPU tier 2칸에 ι가 **모두 동일(0.5, 같은 타입)** 인 3개를 admit.
          최근 접근 시각(Program.last_response_end)만 다르게: NEW=3000, MID=2000, OLD=1000.
          admit 순서를 [NEW, MID, OLD]로 둬서 삽입순(FIFO)과 LRU가 서로 다른 답을 내게 한다.
    기대(논문): 가장 오래 접근되지 않은 OLD가 축출된다.
    실패하면: tie-break에 LRU가 없다(삽입순/임의 순서).
    """
    h = MoriHarness(gpu_capacity=0, cpu_capacity=1000)
    try:
        new = h.place_cpu(make_program("NEW", tokens=400, iota=0.5, last_response_end=3000.0))
        mid = h.place_cpu(make_program("MID", tokens=400, iota=0.5, last_response_end=2000.0))
        old = h.place_cpu(make_program("OLD", tokens=400, iota=0.5, last_response_end=1000.0))
        tier = h.router.cpu_tiers[h.urls[0]]
        obs("A7c", f"축출 전: admit 순서={[p for p, _ in tier.items()]}, "
                   f"i 전부 동일={[round(h.iota(p), 2) for p in (new, mid, old)]}, "
                   f"last_response_end NEW=3000 MID=2000 OLD=1000")

        h.router._mori_evict_cpu(tier, time.time())

        remaining = [p for p, _ in tier.items()]
        evicted = [p for p in ("NEW", "MID", "OLD") if p not in remaining]
        obs("A7c", f"축출 후: 남은 것={remaining}, 축출된 것={evicted}")

        assert old.tier == "waiting", (
            f"동타입(i 동일)에서는 LRU(가장 오래된 last_response_end=OLD)가 축출돼야 함. "
            f"실제 축출={evicted} — 삽입순 FIFO면 NEW가 축출된다")
        assert new.tier == "cpu" and mid.tier == "cpu"
    finally:
        h.close()


def test_A7d_lru_tiebreak_does_not_outrank_type():
    """회귀 방지: LRU는 **tie-break일 뿐** 타입 우선순위를 덮어써서는 안 된다.

    세팅: E_idle(i=0.9, last_access=3000 = 가장 최근) vs E_busy(i=0.1, last_access=1000 = 가장 오래됨).
          CPU tier 1칸 초과 -> 1개 축출.
    기대: 타입이 1차 키이므로 **E_idle**이 축출된다 (LRU상으론 E_busy가 후보인데도).
    실패하면: 정렬키 순서가 뒤집혀 LRU가 타입보다 우선함.
    """
    h = MoriHarness(gpu_capacity=0, cpu_capacity=1000)
    try:
        e_idle = h.place_cpu(make_program("E_idle", tokens=400, iota=0.9, last_response_end=3000.0))
        e_busy = h.place_cpu(make_program("E_busy", tokens=400, iota=0.1, last_response_end=1000.0))
        e_mid = h.place_cpu(make_program("E_mid", tokens=400, iota=0.5, last_response_end=2000.0))
        tier = h.router.cpu_tiers[h.urls[0]]

        h.router._mori_evict_cpu(tier, time.time())

        remaining = [p for p, _ in tier.items()]
        obs("A7d", f"i/last_access: idle(0.9/3000) mid(0.5/2000) busy(0.1/1000) -> "
                   f"남은 것={remaining}, 축출된 것="
                   f"{[p for p in ('E_idle', 'E_mid', 'E_busy') if p not in remaining]}")

        assert e_idle.tier == "waiting", (
            f"타입(i)이 1차 키여야 함 — LRU가 타입을 덮어쓰면 E_busy가 축출된다. "
            f"실제 남은 것={remaining}")
        assert e_busy.tier == "cpu" and e_mid.tier == "cpu"
    finally:
        h.close()


def test_A7e_lru_stamp_survives_missing_last_response_end():
    """회귀 방지: last_response_end가 None(응답 이력 없는 신규 프로그램)이어도
    LRU 장부가 유효한 값을 갖고 축출이 죽지 않는다.
    표본이 없는 프로그램은 ι가 전부 default_iota(0.5)로 동률이 되므로 이 경로가 자주 탄다.
    """
    h = MoriHarness(gpu_capacity=0, cpu_capacity=1000)
    try:
        tier = h.router.cpu_tiers[h.urls[0]]
        made = []
        for name in ("N1", "N2", "N3"):
            p = make_program(name, tokens=400, iota=0.5, last_response_end=None)
            p.idle_window = None              # 표본 전무 -> _iota가 default_iota(0.5)를 반환
            h.place_cpu(p)
            made.append(p)
        stamps = [tier.last_access(p.program_id) for p in made]
        obs("A7e", f"last_response_end=None 3개 admit -> last_access 스탬프={[round(s, 3) for s in stamps]}, "
                   f"i(default)={h.iota(made[0]):.2f}")

        assert all(s not in (None, float("-inf")) for s in stamps), f"스탬프 누락: {stamps}"
        assert all(a <= b for a, b in zip(stamps, stamps[1:])), (
            f"admit 순서대로 스탬프가 증가해야 함 (LRU 의미 유지): {stamps}")

        h.router._mori_evict_cpu(tier, time.time())
        remaining = [p for p, _ in tier.items()]
        obs("A7e", f"축출 후 남은 것={remaining} (기대: 가장 먼저 admit된 N1이 LRU로 축출)")
        assert tier.remaining() >= 0, "축출 후에도 용량 초과"
        assert made[0].tier == "waiting", f"동-ι에서 가장 오래된 N1이 축출돼야 함. 남은 것={remaining}"
    finally:
        h.close()


def test_A7f_remove_clears_lru_bookkeeping():
    """회귀 방지: tier에서 빠진 프로그램의 LRU 스탬프가 남아 누수되지 않는다
    (promote/release 후 재-admit 시 옛 스탬프가 되살아나면 LRU가 오염된다)."""
    h = MoriHarness(gpu_capacity=0, cpu_capacity=slots(4, 400))
    try:
        tier = h.router.cpu_tiers[h.urls[0]]
        p = h.place_cpu(make_program("Z", tokens=400, iota=0.5, last_response_end=1000.0))
        assert tier.last_access("Z") == 1000.0
        tier.remove("Z")
        obs("A7f", f"remove 후 last_access('Z')={tier.last_access('Z')} (미등록 = -inf 기대), "
                   f"내부 장부 크기={len(tier._last_access)}")
        assert tier.last_access("Z") == float("-inf"), "remove 후에도 옛 스탬프가 남음"
        assert len(tier._last_access) == 0, "LRU 장부 누수"

        p.last_response_end = 5000.0
        tier.admit("Z", p)
        assert tier.last_access("Z") == 5000.0, "재-admit 시 새 스탬프가 반영되지 않음"
    finally:
        h.close()


# =============================================================================
# 자체 러너 (이 환경에는 pytest / pip 가 없음)
# =============================================================================

def _main() -> int:
    import traceback

    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    results = []
    for name, fn in tests:
        print(f"\n=== {name}")
        try:
            fn()
            print(f"    -> PASS")
            results.append((name, "PASS", ""))
        except AssertionError as e:
            print(f"    -> FAIL: {e}")
            results.append((name, "FAIL", str(e)))
        except Exception:
            tb = traceback.format_exc()
            print(f"    -> ERROR:\n{tb}")
            results.append((name, "ERROR", tb.strip().splitlines()[-1]))

    print("\n" + "=" * 78)
    npass = sum(1 for _, s, _ in results if s == "PASS")
    for name, status, msg in results:
        print(f"{status:5s}  {name}" + (f"\n       {msg.splitlines()[0]}" if msg else ""))
    print(f"\n{npass}/{len(results)} passed")
    print("=" * 78)
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(_main())
