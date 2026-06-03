"""Background loop for deterministic market-signal polling."""

from __future__ import annotations

import asyncio
import logging

from kodiak.app.signals import poll_market_signals
from kodiak.utils.logging import get_logger, log_event

logger = get_logger("kodiak_server.monitoring.signals")


class SignalMonitor:
    """Simple asyncio loop that polls configured market-signal sources."""

    def __init__(self, interval_seconds: int) -> None:
        self.interval_seconds = interval_seconds
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        log_event(
            logger,
            logging.INFO,
            "signal_monitor_started",
            interval_seconds=self.interval_seconds,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        log_event(logger, logging.INFO, "signal_monitor_stopped")

    async def _loop(self) -> None:
        while self._running:
            try:
                await asyncio.to_thread(poll_market_signals)
            except Exception:
                log_event(logger, logging.WARNING, "signal_monitor_tick_failed")
            await asyncio.sleep(self.interval_seconds)

