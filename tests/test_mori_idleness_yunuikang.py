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


def test_reload_cost_model():
    c = MoriConfig(reload_bw_bytes_per_s=8e9, bytes_per_token=147456)
    assert c.reload_seconds(0) == 0.0
    assert abs(c.reload_seconds(262144) - 262144 * 147456 / 8e9) < 1e-9


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("all idleness/tier/config tests passed")
