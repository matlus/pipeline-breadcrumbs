from datetime import UTC, datetime, timedelta

from pipeline_breadcrumbs import Clock


class ClockTesting:
    """A clock that moves only when a test says so, so every elapsed time in an assertion is exact."""

    def __init__(self) -> None:
        self._monotonic_seconds: float = 1000.0
        self._current_time: datetime = datetime(2026, 10, 3, 14, 3, 22, tzinfo=UTC)

    def advance(self, seconds: float) -> None:
        self._monotonic_seconds += seconds
        self._current_time += timedelta(seconds=seconds)

    @property
    def clock(self) -> Clock:
        return Clock(now=lambda: self._current_time, monotonic=lambda: self._monotonic_seconds)
