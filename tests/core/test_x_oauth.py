"""Tests for X OAuth credential storage and API-backed collection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from kodiak.signals.models import SignalMonitorConfig, SignalSourceConfig
from kodiak.signals.sources.x import XSourceCollector
from kodiak.signals.x_auth import (
    delete_x_oauth_credentials,
    load_x_oauth_credentials,
    save_x_oauth_credentials,
    x_oauth_status,
)


def test_x_oauth_credentials_round_trip(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KODIAK_API_TOKEN", "test-token")

    saved = save_x_oauth_credentials(
        x_user_id="42",
        username="signaldesk",
        access_token="access-1",
        refresh_token="refresh-1",
        token_type="bearer",
        scope="tweet.read users.read offline.access",
        expires_in=3600,
        data_dir=tmp_path,
    )
    loaded = load_x_oauth_credentials(tmp_path)

    assert loaded is not None
    assert loaded.x_user_id == "42"
    assert loaded.username == "signaldesk"
    assert loaded.refresh_token == "refresh-1"
    assert loaded.expires_at is not None
    assert loaded.expires_at > datetime.now(UTC)
    assert x_oauth_status(tmp_path)["connected"] is True
    assert delete_x_oauth_credentials(tmp_path) is True
    assert x_oauth_status(tmp_path)["connected"] is False
    assert saved.username == "signaldesk"


def test_x_source_collector_prefers_api_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeApiClient:
        def __init__(self, credentials) -> None:  # noqa: ARG002
            pass

        def fetch_home_timeline(self, max_results: int = 20):  # noqa: ARG002
            from kodiak.signals.models import SourceItem

            now = datetime.now(UTC)
            return [
                SourceItem(
                    external_id="1",
                    url="https://x.com/signaldesk/status/1",
                    published_at=now - timedelta(minutes=2),
                    author="signaldesk",
                    text="Added $NVDA",
                ),
                SourceItem(
                    external_id="2",
                    url="https://x.com/otherdesk/status/2",
                    published_at=now - timedelta(minutes=1),
                    author="otherdesk",
                    text="Ignored",
                ),
            ]

    monkeypatch.setattr(
        "kodiak.signals.sources.x.load_x_oauth_credentials",
        lambda: object(),
    )
    monkeypatch.setattr("kodiak.signals.sources.x.XApiClient", FakeApiClient)

    collector = XSourceCollector()
    source = SignalSourceConfig(
        id="x-signaldesk",
        provider="x",
        account="@signaldesk",
        max_posts=5,
    )
    config = SignalMonitorConfig(enabled=True)

    items = collector.collect(source, config)

    assert len(items) == 1
    assert items[0].author == "signaldesk"
    assert items[0].external_id == "1"
