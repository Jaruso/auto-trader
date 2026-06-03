"""Models for deterministic source-driven market alerts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class SignalRuleConfig(BaseModel):
    """Regex rule that turns source text into a direct trading signal."""

    id: str
    pattern: str
    action: Literal["buy", "sell"]
    symbol: str | None = None
    symbol_capture_group: str = "symbol"
    confidence: float = Field(default=0.99, ge=0.0, le=1.0)
    notes: str | None = None


class SignalSourceConfig(BaseModel):
    """Configured upstream source to monitor."""

    id: str
    provider: Literal["x"]
    account: str
    label: str | None = None
    enabled: bool = True
    max_posts: int = Field(default=5, ge=1, le=20)
    capture_unmatched: bool = True
    rules: list[SignalRuleConfig] = Field(default_factory=list)


class XCollectorConfig(BaseModel):
    """Playwright-backed X collector settings."""

    enabled: bool = False
    user_data_dir: str | None = None
    executable_path: str | None = None
    headless: bool = True
    timeout_seconds: int = Field(default=30, ge=5, le=180)


class SignalMonitorConfig(BaseModel):
    """Top-level market signal monitor configuration."""

    enabled: bool = False
    poll_interval_seconds: int = Field(default=300, ge=30, le=3600)
    recent_window_hours: int = Field(default=24, ge=1, le=168)
    max_stored_alerts: int = Field(default=500, ge=20, le=5000)
    x: XCollectorConfig = Field(default_factory=XCollectorConfig)
    sources: list[SignalSourceConfig] = Field(default_factory=list)


class SourceItem(BaseModel):
    """Normalized item fetched from an external monitored source."""

    external_id: str
    url: str
    published_at: datetime
    author: str
    text: str


class SignalAlert(BaseModel):
    """Stored alert emitted from a source item."""

    id: str
    source_id: str
    source_label: str
    provider: str
    account: str
    external_item_id: str
    external_url: str
    observed_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    bucket: Literal["direct", "needs_inference"]
    action: Literal["buy", "sell", "needs_inference"]
    symbol: str | None = None
    confidence: float = Field(default=0.99, ge=0.0, le=1.0)
    title: str
    text: str
    reason: str
    matched_rule_id: str | None = None
    notification_sent_at: datetime | None = None


class SourceRuntimeState(BaseModel):
    """Persisted runtime status for a monitored source."""

    source_id: str
    last_polled_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    last_seen_item_ids: list[str] = Field(default_factory=list)
    latest_item_at: datetime | None = None


class PollSourceResult(BaseModel):
    """Per-source outcome from a monitoring poll."""

    source_id: str
    fetched_count: int = 0
    new_direct_alerts: int = 0
    new_inference_alerts: int = 0
    last_error: str | None = None

