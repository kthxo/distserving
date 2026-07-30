"""Unit tests for MORI pure modules (idleness / tier / config).

Run: `python -m pytest tests/test_mori_idleness_yunuikang.py`
 or: `python tests/test_mori_idleness_yunuikang.py`
CPU-only, no engine, no network.
"""
from ThunderAgent.scheduler.mori_idleness import IdlenessWindow
from ThunderAgent.scheduler.mori_config import MoriConfig
from ThunderAgent.scheduler.mori_tier import CpuTier
from ThunderAgent.program.state import Program


def test_iota_short_tools_low():
    w = IdlenessWindow(k=5)
    for _ in range(5):
        w.push_acting(0.05)
        w.push_reasoning(2.0)
    assert w.value(default=0.5) < 0.1


def test_iota_ongoing_tool_monotone():
    w = IdlenessWindow(k=5)
    w.push_reasoning(1.0)
    t0 = 1000.0
    early = w.value(now=t0 + 1, acting_since=t0)
    late = w.value(now=t0 + 30, acting_since=t0)
    assert late > early


def test_iota_no_samples_default():
    assert IdlenessWindow().value(default=0.5) == 0.5
    assert IdlenessWindow().n_samples() == 0


def test_cputier_capacity_convention():
    t = CpuTier("u", capacity_tokens=1000)
    p1 = Program(program_id="p1", total_tokens=400)
    assert t.can_admit(p1)
    t.admit("p1", p1)
    assert t.used_tokens() == 500          # 400 + BUFFER_PER_PROGRAM(100)
    p2 = Program(program_id="p2", total_tokens=600)
    assert not t.can_admit(p2)             # 500 + 700 > 1000
    assert t.remove("p1") is p1
    assert t.count() == 0


def test_mori_config_fields():
    # Re-scope: reload cost model removed (CPU tier = real HiCache host pool).
    c = MoriConfig(k=5, cpu_capacity_ratio=2.0, min_dwell_ticks=1)
    assert c.k == 5 and c.cpu_capacity_ratio == 2.0 and c.default_iota == 0.5
    assert not hasattr(c, "reload_seconds")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("all idleness/tier/config tests passed")
