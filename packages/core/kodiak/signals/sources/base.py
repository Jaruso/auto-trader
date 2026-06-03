"""Base interfaces for monitored source collectors."""

from __future__ import annotations

from typing import Protocol

from kodiak.signals.models import SignalMonitorConfig, SignalSourceConfig, SourceItem


class SignalSourceCollector(Protocol):
    """Protocol for deterministic source collectors."""

    def collect(
        self,
        source: SignalSourceConfig,
        config: SignalMonitorConfig,
    ) -> list[SourceItem]:
        """Fetch and normalize the latest items for a source."""

