"""Tests for deterministic market-signal ingestion."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import yaml

from kodiak.app.signals import (
    get_market_signal_overview,
    list_market_signal_alerts,
    list_market_signal_sources,
    poll_market_signals,
)
from kodiak.signals.models import SourceItem


class _FakeCollector:
    def __init__(self, items: list[SourceItem]) -> None:
        self.items = items

    def collect(self, source: object, config: object) -> list[SourceItem]:  # noqa: ARG002
        return list(self.items)


def test_poll_market_signals_creates_direct_and_inference_alerts(
    monkeypatch,
    tmp_path,
) -> None:
    config_path = tmp_path / "market_signals.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "enabled": True,
                "poll_interval_seconds": 120,
                "recent_window_hours": 24,
                "sources": [
                    {
                        "id": "x-trader",
                        "provider": "x",
                        "account": "@signaldesk",
                        "label": "Signal Desk",
                        "capture_unmatched": True,
                        "rules": [
                            {
                                "id": "buy-rule",
                                "pattern": r"added\s+\$(?P<symbol>[A-Z]{1,5})",
                                "action": "buy",
                            }
                        ],
                    }
                ],
            }
        )
    )
    monkeypatch.setenv("KODIAK_SIGNAL_CONFIG", str(config_path))
    monkeypatch.setenv("NOTIFICATIONS_ENABLED", "false")

    now = datetime.now(UTC)
    items = [
        SourceItem(
            external_id="111",
            url="https://x.com/signaldesk/status/111",
            published_at=now - timedelta(minutes=4),
            author="signaldesk",
            text="We added $NVDA this morning.",
        ),
        SourceItem(
            external_id="112",
            url="https://x.com/signaldesk/status/112",
            published_at=now - timedelta(minutes=2),
            author="signaldesk",
            text="Watching semis here without a direct action yet.",
        ),
    ]
    monkeypatch.setattr("kodiak.app.signals._get_collector", lambda provider: _FakeCollector(items))

    result = poll_market_signals(data_dir=tmp_path / "data")

    assert result["new_direct_alerts"] == 1
    assert result["new_inference_alerts"] == 1

    alerts = list_market_signal_alerts(limit=10, data_dir=tmp_path / "data")
    assert len(alerts) == 2
    assert alerts[0]["bucket"] == "needs_inference"
    assert alerts[1]["action"] == "buy"
    assert alerts[1]["symbol"] == "NVDA"

    overview = get_market_signal_overview(data_dir=tmp_path / "data")
    assert overview["enabled"] is True
    assert overview["direct_alert_count"] == 1
    assert overview["needs_inference_count"] == 1

    sources = list_market_signal_sources(data_dir=tmp_path / "data")
    assert len(sources) == 1
    assert sources[0]["last_error"] is None


def test_poll_market_signals_deduplicates_seen_posts(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "market_signals.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "enabled": True,
                "sources": [
                    {
                        "id": "x-trader",
                        "provider": "x",
                        "account": "@signaldesk",
                        "capture_unmatched": False,
                        "rules": [
                            {
                                "id": "sell-rule",
                                "pattern": r"trimmed\s+\$(?P<symbol>[A-Z]{1,5})",
                                "action": "sell",
                            }
                        ],
                    }
                ],
            }
        )
    )
    monkeypatch.setenv("KODIAK_SIGNAL_CONFIG", str(config_path))
    monkeypatch.setenv("NOTIFICATIONS_ENABLED", "false")

    item = SourceItem(
        external_id="221",
        url="https://x.com/signaldesk/status/221",
        published_at=datetime.now(UTC) - timedelta(minutes=1),
        author="signaldesk",
        text="We trimmed $TSLA into strength.",
    )
    monkeypatch.setattr(
        "kodiak.app.signals._get_collector",
        lambda provider: _FakeCollector([item]),
    )

    first = poll_market_signals(data_dir=tmp_path / "data")
    second = poll_market_signals(data_dir=tmp_path / "data")

    assert first["new_direct_alerts"] == 1
    assert second["new_direct_alerts"] == 0
    assert len(list_market_signal_alerts(limit=10, data_dir=tmp_path / "data")) == 1
