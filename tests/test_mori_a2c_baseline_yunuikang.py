"""STEP 5 과제 A — A2c 과잉 마킹이 MORI 고유인가, baseline 상속인가.

배경 (STEP 4 A2c 관측):
    GPU 900tok에 REASONING 2개(각 400tok, used=1000 -> 100tok 초과)를 두고 MORI 틱을 돌리면
    **1개만 마킹하면 충분한데 2개 전부** 마킹된다 (future_paused_tokens=800).

가설:
    근본 원인은 ``BackendState.remaining_capacity()`` (backend/state.py:185-194)가
    ``future_paused_tokens``를 차감하지 않는 것이고, MORI/base 둘 다 이 값을 while 루프
    조건으로 쓰므로 **양쪽 모두** 과잉 마킹할 것이다.
    => 그렇다면 MORI 고유 이탈이 아니라 baseline 상속 성질이며, 격리 원칙(I4)상 무수정이 맞다.

판정 방법 (코드 무수정, 엔진 없음):
    동일한 합성 상태를 (1) MoriRouter._mori_pause_until_safe 와
    (2) base MultiBackendRouter._pause_until_safe 에 각각 먹여 마킹 수를 대조한다.
    metrics_client 하나만 mock. 두 라우터 모두 **실제 코드**.

실행:
    python tests/test_mori_a2c_baseline_yunuikang.py
"""
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from ThunderAgent.program.state import ProgramStatus  # noqa: E402

from mori_harness_yunuikang import (  # noqa: E402
    MoriHarness,
    make_baseline_harness,
    make_program,
    slots,
)

OBS: list = []


def obs(tag: str, text: str) -> None:
    OBS.append((tag, text))
    print(f"    [측정] {tag}: {text}")


# A2c와 **동일한** 합성 상태
GPU_CAP = 900          # REASONING 2개(각 400tok) -> used = 800 + 2x100 = 1000 -> 100tok 초과
TOKENS = 400
N_REASONING = 2


def _count_marked(router) -> int:
    return sum(1 for p in router.programs.values() if p.marked_for_pause)


def test_mori_marks_all_reasoning():
    """MORI 경로: _mori_pause_until_safe 가 REASONING을 몇 개 마킹하는가."""
    h = MoriHarness(gpu_capacity=GPU_CAP, cpu_capacity=slots(4, TOKENS))
    try:
        for i, io in enumerate([0.8, 0.2], start=1):
            h.place_gpu(make_program(f"R{i}", tokens=TOKENS, iota=io,
                                     status=ProgramStatus.REASONING))
        b = h.router.backends[h.urls[0]]
        before = b.remaining_capacity()

        h.router._mori_pause_until_safe(b, time.time())

        n = _count_marked(h.router)
        obs("MORI", f"GPU cap={GPU_CAP}, REASONING {N_REASONING}개(각 {TOKENS}tok) -> "
                    f"틱 전 remaining_capacity={before} (초과분 {-before}tok, 1개 마킹이면 충분), "
                    f"**마킹된 수={n}/{N_REASONING}**, future_paused_tokens={b.future_paused_tokens}, "
                    f"마킹 후 remaining_capacity={b.remaining_capacity()} (변화 없음)")
        assert n == N_REASONING, f"MORI 관측 재현 실패: marked={n}"
        return n
    finally:
        h.close()


def test_baseline_tr_marks_all_reasoning():
    """baseline 'tr' 경로: base MultiBackendRouter._pause_until_safe (MORI 오버라이드 아님).

    이 테스트가 통과하면(= tr도 전부 마킹) A2c 과잉 마킹은 **baseline 상속 성질**이다.
    """
    h = make_baseline_harness(gpu_capacity=GPU_CAP)
    try:
        for i in (1, 2):
            h.place_gpu(make_program(f"R{i}", tokens=TOKENS, iota=0.5,
                                     status=ProgramStatus.REASONING))
        b = h.router.backends[h.urls[0]]
        before = b.remaining_capacity()

        # base 경로임을 명시적으로 확인 (MORI 오버라이드가 아님)
        from ThunderAgent.scheduler.router import MultiBackendRouter
        assert type(h.router) is MultiBackendRouter
        assert h.router._pause_until_safe.__func__ is MultiBackendRouter._pause_until_safe

        h.call(h.router._pause_until_safe(b))

        n = _count_marked(h.router)
        obs("tr(base)", f"GPU cap={GPU_CAP}, REASONING {N_REASONING}개(각 {TOKENS}tok) -> "
                        f"틱 전 remaining_capacity={before} (초과분 {-before}tok), "
                        f"**마킹된 수={n}/{N_REASONING}**, future_paused_tokens={b.future_paused_tokens}, "
                        f"마킹 후 remaining_capacity={b.remaining_capacity()} (변화 없음)")
        assert n == N_REASONING, (
            f"baseline tr은 {n}개만 마킹 -> 과잉 마킹이 MORI 고유일 가능성. "
            f"mori_router.py:254-260 을 재검토할 것")
        return n
    finally:
        h.close()


def test_root_cause_remaining_capacity_ignores_future_paused():
    """근본 원인 직접 확인: remaining_capacity()가 future_paused_tokens에 반응하지 않는다.

    (backend/state.py:185-194 — frozen baseline. capacity_overflow()는 반대로 반응하므로 대조.)
    """
    h = make_baseline_harness(gpu_capacity=GPU_CAP)
    try:
        h.place_gpu(make_program("R1", tokens=TOKENS, status=ProgramStatus.REASONING))
        h.place_gpu(make_program("R2", tokens=TOKENS, status=ProgramStatus.REASONING))
        b = h.router.backends[h.urls[0]]

        rc0 = b.remaining_capacity()
        ov0 = b.capacity_overflow(include_future_release=True)
        b.future_paused_tokens = 400          # R1을 마킹한 것과 동일한 회계 효과
        rc1 = b.remaining_capacity()
        ov1 = b.capacity_overflow(include_future_release=True)
        b.future_paused_tokens = 0

        obs("근본원인", f"future_paused_tokens 0->400 일 때 "
                        f"remaining_capacity: {rc0} -> {rc1} (**변화 없음**), "
                        f"capacity_overflow(include_future_release=True): {ov0} -> {ov1} (반응함)")
        assert rc0 == rc1, "remaining_capacity가 future_paused_tokens에 반응함 (가설과 다름)"
        assert ov0 != ov1, "capacity_overflow도 반응 안 함 (대조군 실패)"
    finally:
        h.close()


def test_mori_and_tr_share_the_same_capacity_accounting():
    """MORI와 tr의 GPU 용량 회계식이 동일한 값을 낸다 (불변식 I2 확인)."""
    hm = MoriHarness(gpu_capacity=GPU_CAP, cpu_capacity=slots(4, TOKENS))
    hb = make_baseline_harness(gpu_capacity=GPU_CAP)
    try:
        for h in (hm, hb):
            for i in (1, 2):
                h.place_gpu(make_program(f"R{i}", tokens=TOKENS, iota=0.5,
                                         status=ProgramStatus.REASONING))
        rm = hm.router.backends[hm.urls[0]].remaining_capacity()
        rb = hb.router.backends[hb.urls[0]].remaining_capacity()
        obs("회계식", f"동일 상태에서 remaining_capacity: MORI={rm}, tr={rb} -> 일치={rm == rb}")
        assert rm == rb, f"MORI와 tr의 용량 회계가 다름: {rm} vs {rb} (불변식 I2 위반)"
    finally:
        hm.close()
        hb.close()


def _main() -> int:
    import traceback
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    results = []
    for name, fn in tests:
        print(f"\n=== {name}")
        try:
            fn()
            print("    -> PASS")
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
