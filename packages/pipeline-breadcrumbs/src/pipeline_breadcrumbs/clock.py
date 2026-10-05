"""An injectable clock, so elapsed times and timestamps are deterministic in tests."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import final


@final
@dataclass(frozen=True, slots=True)
class Clock:
    """Wall-clock time for timestamps, and a monotonic counter for elapsed time."""

    now: Callable[[], datetime]
    monotonic: Callable[[], float]

    @staticmethod
    def create_system_clock() -> Clock:
        """The machine's clock in its local timezone, so run folders, run ids and banner times agree.

        Timestamps stay timezone-aware: manifest times carry their UTC offset.
        """
        return Clock(now=lambda: datetime.now(tz=UTC).astimezone(), monotonic=time.perf_counter)
