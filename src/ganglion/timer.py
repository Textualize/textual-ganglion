from __future__ import annotations

import asyncio
from time import monotonic
from typing import Callable, Coroutine

from logging import getLogger

import rich.repr

log = getLogger("ganglion")


@rich.repr.auto
class Timer:
    """Run a callback at regular intervals."""

    def __init__(
        self, period: float, callback: Callable[[], Coroutine], name: str = "timer"
    ) -> None:
        """Construct a timer.

        Args:
            period: Time in seconds between callbacks.
            callback: Callback (coroutine).
            name: Name of timer (for debugging purposes).
        """
        self.period = period
        self.callback = callback
        self.name = name
        self._task: asyncio.Task | None = None

    def __rich_repr__(self) -> rich.repr.Result:
        yield self.period
        yield self.callback
        yield "name", self.name, "timer"

    def start(self) -> None:
        """Start the timer."""
        assert self._task is None
        self._task = asyncio.create_task(self.run())

    async def run(self) -> None:
        """Main coroutine run in a task."""
        try:
            count = 0
            start_time = monotonic()
            while True:
                count += 1
                next_callback_time = start_time + count * self.period
                if next_callback_time < monotonic():
                    await asyncio.sleep(0)
                else:
                    await asyncio.sleep(next_callback_time - monotonic())
                    try:
                        await asyncio.shield(self.callback())
                    except Exception:
                        log.exception("error in %r callback", self)
        except asyncio.CancelledError:
            return

    async def stop(self) -> None:
        """Stop the timer."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            await self._task
            self._task = None
