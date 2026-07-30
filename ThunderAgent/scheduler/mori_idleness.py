"""Relative idleness (ι) measurement — MORI paper §4.2.

ι = T_acting / (T_reasoning + T_acting) over a sliding window of the most recent
k steps, with scheduler-imposed waiting time excluded (we only push reasoning
time measured *after* any pause). A high ι means the program spends most of its
time off-GPU executing tools (a good demotion candidate); a low ι means it is
reasoning-bound (keep on GPU).

Pure module (no engine / no asyncio) so it is unit-testable in isolation.
"""
from collections import deque
from typing import Optional


class IdlenessWindow:
    """Sliding-window relative-idleness estimator.

    push_acting / push_reasoning append durations (seconds) to two k-length ring
    buffers. ``value`` returns ι in [0, 1]; if an acting phase is currently in
    progress (``acting_since`` given) its elapsed time is added to the acting
    term so a long ongoing tool call makes ι rise monotonically — the
    "responsive" property from paper §4.2 that lets MORI demote a program that
    has just entered a long tool call.
    """

    __slots__ = ("k", "_acting", "_reasoning")

    def __init__(self, k: int = 5) -> None:
        self.k = k
        self._acting: deque = deque(maxlen=k)
        self._reasoning: deque = deque(maxlen=k)

    def push_acting(self, dt: float) -> None:
        if dt is not None and dt >= 0:
            self._acting.append(float(dt))

    def push_reasoning(self, dt: float) -> None:
        if dt is not None and dt >= 0:
            self._reasoning.append(float(dt))

    def n_samples(self) -> int:
        """Number of complete reasoning+acting observations available."""
        return min(len(self._acting), len(self._reasoning))

    def value(
        self,
        now: Optional[float] = None,
        acting_since: Optional[float] = None,
        default: float = 0.5,
    ) -> float:
        """Return ι in [0, 1].

        Args:
            now: current wall-clock (time.time()); required to count an ongoing
                tool call.
            acting_since: time.time() when the program entered ACTING, or None if
                it is currently REASONING. When set, ``now - acting_since`` is
                added to the acting term (ongoing tool call).
            default: value returned when there is no signal at all.
        """
        a = sum(self._acting)
        r = sum(self._reasoning)
        if acting_since is not None and now is not None:
            a += max(0.0, now - acting_since)
        total = a + r
        if total <= 0.0:
            return default
        return a / total
