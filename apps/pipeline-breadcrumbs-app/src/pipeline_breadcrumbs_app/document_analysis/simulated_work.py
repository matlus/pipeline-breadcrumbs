"""Stand-in for real processing time."""

import asyncio


class SimulatedWork:
    """Takes a moment, the way real non-model work does.

    A real system renders PDF pages, runs text clean-up passes, or builds prompts, and each
    takes time. The demo sleeps instead, so the log appears at a believable pace and the
    sample stays free of heavy dependencies. Remove it from a real system.
    """

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self._delay_seconds: float = delay_seconds

    async def take_time(self) -> None:
        await asyncio.sleep(self._delay_seconds)
