"""Deterministic source-monitoring services for market alerts."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from kodiak.app.notifications import get_notification_manager
from kodiak.errors import ConfigurationError, ValidationError
from kodiak.signals.config import load_market_signals_config
from kodiak.signals.models import (
    PollSourceResult,
    SignalAlert,
    SignalMonitorConfig,
    SignalRuleConfig,
    SignalSourceConfig,
    SourceItem,
    SourceRuntimeState,
)
from kodiak.signals.sources.x import XSourceCollector
from kodiak.signals.store import load_alerts, load_runtime_state, save_alerts, save_runtime_state
from kodiak.utils.logging import get_logger, log_event

logger = get_logger("kodiak.signals")
CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")


def get_signal_monitor_config(config_dir: Path | None = None) -> SignalMonitorConfig:
    """Load signal-monitor configuration."""
    return load_market_signals_config(config_dir)


def list_market_signal_alerts(
    *,
    limit: int = 20,
    bucket: str | None = None,
    data_dir: Path | None = None,
) -> list[dict[str, object]]:
    """Return recent signal alerts for dashboard/API consumption."""
    if limit < 1 or limit > 200:
        raise ValidationError("limit must be between 1 and 200", details={"limit": limit})

    alerts = sorted(load_alerts(data_dir), key=lambda item: item.created_at, reverse=True)
    if bucket:
        alerts = [alert for alert in alerts if alert.bucket == bucket]
    return [alert.model_dump(mode="json") for alert in alerts[:limit]]


def list_market_signal_sources(data_dir: Path | None = None) -> list[dict[str, object]]:
    """Return configured source statuses merged with runtime state."""
    config = get_signal_monitor_config()
    state = load_runtime_state(data_dir)
    results: list[dict[str, object]] = []
    for source in config.sources:
        runtime = state.get(source.id, SourceRuntimeState(source_id=source.id))
        results.append(
            {
                "id": source.id,
                "label": source.label or source.account,
                "provider": source.provider,
                "account": source.account,
                "enabled": source.enabled,
                "rule_count": len(source.rules),
                "capture_unmatched": source.capture_unmatched,
                "last_polled_at": runtime.last_polled_at.isoformat() if runtime.last_polled_at else None,
                "last_success_at": runtime.last_success_at.isoformat() if runtime.last_success_at else None,
                "latest_item_at": runtime.latest_item_at.isoformat() if runtime.latest_item_at else None,
                "last_error": runtime.last_error,
            }
        )
    return results


def get_market_signal_overview(data_dir: Path | None = None) -> dict[str, object]:
    """Summarize monitor configuration, recency, and alert volume."""
    config = get_signal_monitor_config()
    alerts = load_alerts(data_dir)
    state = load_runtime_state(data_dir)

    active_sources = [source for source in config.sources if source.enabled]
    latest_polled_at = _latest_timestamp(item.last_polled_at for item in state.values())
    latest_success_at = _latest_timestamp(item.last_success_at for item in state.values())
    window_start = datetime.now(UTC) - timedelta(hours=config.recent_window_hours)
    recent_alerts = [alert for alert in alerts if alert.created_at >= window_start]

    return {
        "enabled": config.enabled,
        "poll_interval_seconds": config.poll_interval_seconds,
        "recent_window_hours": config.recent_window_hours,
        "configured_source_count": len(config.sources),
        "active_source_count": len(active_sources),
        "direct_alert_count": sum(1 for alert in recent_alerts if alert.bucket == "direct"),
        "needs_inference_count": sum(
            1 for alert in recent_alerts if alert.bucket == "needs_inference"
        ),
        "last_polled_at": latest_polled_at.isoformat() if latest_polled_at else None,
        "last_success_at": latest_success_at.isoformat() if latest_success_at else None,
    }


def poll_market_signals(
    *,
    source_id: str | None = None,
    config_dir: Path | None = None,
    data_dir: Path | None = None,
) -> dict[str, object]:
    """Poll configured sources, emit deterministic alerts, and persist status."""
    config = get_signal_monitor_config(config_dir)
    if not config.enabled:
        raise ConfigurationError(
            message="Market signal monitoring is disabled",
            code="SIGNAL_MONITOR_DISABLED",
            suggestion=(
                "Create config/market_signals.yaml (or set KODIAK_SIGNAL_CONFIG) "
                "and enable the monitor."
            ),
        )

    selected_sources = [source for source in config.sources if source.enabled]
    if source_id:
        selected_sources = [source for source in selected_sources if source.id == source_id]
        if not selected_sources:
            raise ValidationError(
                f"Configured source '{source_id}' was not found or is disabled",
                details={"source_id": source_id},
            )

    alerts = load_alerts(data_dir)
    state = load_runtime_state(data_dir)
    existing_alert_ids = {alert.id for alert in alerts}
    source_results: list[PollSourceResult] = []
    new_direct = 0
    new_inference = 0

    for source in selected_sources:
        runtime = state.get(source.id, SourceRuntimeState(source_id=source.id))
        source_result = PollSourceResult(source_id=source.id)
        runtime.last_polled_at = datetime.now(UTC)

        try:
            items = _get_collector(source.provider).collect(source, config)
            source_result.fetched_count = len(items)
            for item in sorted(items, key=lambda candidate: candidate.published_at):
                if item.external_id in runtime.last_seen_item_ids:
                    continue

                alert = _evaluate_item(source, item)
                if alert is None:
                    runtime.last_seen_item_ids.insert(0, item.external_id)
                    continue

                if alert.id not in existing_alert_ids:
                    alerts.append(alert)
                    existing_alert_ids.add(alert.id)
                    if alert.bucket == "direct":
                        new_direct += 1
                        source_result.new_direct_alerts += 1
                        _notify_direct_alert(alert)
                    else:
                        new_inference += 1
                        source_result.new_inference_alerts += 1

                runtime.last_seen_item_ids.insert(0, item.external_id)
                runtime.latest_item_at = _max_timestamp(runtime.latest_item_at, item.published_at)

            runtime.last_seen_item_ids = runtime.last_seen_item_ids[:500]
            runtime.last_success_at = datetime.now(UTC)
            runtime.last_error = None
        except Exception as exc:
            runtime.last_error = str(exc)
            source_result.last_error = str(exc)
            log_event(
                logger,
                logging.WARNING,
                "signal_source_poll_failed",
                source_id=source.id,
                provider=source.provider,
            )

        state[source.id] = runtime
        source_results.append(source_result)

    alerts = sorted(alerts, key=lambda item: item.created_at, reverse=True)[: config.max_stored_alerts]
    save_alerts(alerts, data_dir)
    save_runtime_state(state, data_dir)

    result = {
        "polled_at": datetime.now(UTC).isoformat(),
        "source_count": len(selected_sources),
        "new_direct_alerts": new_direct,
        "new_inference_alerts": new_inference,
        "sources": [item.model_dump(mode="json") for item in source_results],
    }
    log_event(
        logger,
        logging.INFO,
        "signal_monitor_poll_complete",
        source_count=len(selected_sources),
        new_direct_alerts=new_direct,
        new_inference_alerts=new_inference,
    )
    return result


def _get_collector(provider: str) -> XSourceCollector:
    if provider == "x":
        return XSourceCollector()
    raise ValidationError(
        f"Unsupported signal source provider '{provider}'",
        code="UNSUPPORTED_SIGNAL_PROVIDER",
        details={"provider": provider},
    )


def _evaluate_item(source: SignalSourceConfig, item: SourceItem) -> SignalAlert | None:
    for rule in source.rules:
        match = re.search(rule.pattern, item.text, flags=re.IGNORECASE | re.MULTILINE)
        if not match:
            continue
        symbol = _resolve_symbol(rule, item, match)
        return SignalAlert(
            id=_stable_alert_id(source.id, item.external_id, rule.id),
            source_id=source.id,
            source_label=source.label or source.account,
            provider=source.provider,
            account=source.account,
            external_item_id=item.external_id,
            external_url=item.url,
            observed_at=item.published_at,
            bucket="direct",
            action=rule.action,
            symbol=symbol,
            confidence=rule.confidence,
            title=_build_alert_title(rule.action, symbol, source),
            text=item.text,
            reason=f"Matched regex rule '{rule.id}'",
            matched_rule_id=rule.id,
        )

    if not source.capture_unmatched:
        return None

    return SignalAlert(
        id=_stable_alert_id(source.id, item.external_id, "needs_inference"),
        source_id=source.id,
        source_label=source.label or source.account,
        provider=source.provider,
        account=source.account,
        external_item_id=item.external_id,
        external_url=item.url,
        observed_at=item.published_at,
        bucket="needs_inference",
        action="needs_inference",
        symbol=_extract_cashtag(item.text),
        confidence=0.0,
        title=f"Inference needed from {source.account}",
        text=item.text,
        reason="No deterministic rule matched this post",
    )


def _resolve_symbol(
    rule: SignalRuleConfig,
    item: SourceItem,
    match: re.Match[str],
) -> str | None:
    if rule.symbol:
        return rule.symbol.upper()
    if rule.symbol_capture_group and rule.symbol_capture_group in match.re.groupindex:
        value = match.group(rule.symbol_capture_group)
        if value:
            return value.upper()
    return _extract_cashtag(item.text)


def _extract_cashtag(text: str) -> str | None:
    match = CASHTAG_RE.search(text)
    if not match:
        return None
    return match.group(1).upper()


def _stable_alert_id(source_id: str, external_item_id: str, rule_id: str) -> str:
    digest = hashlib.sha256(
        f"{source_id}:{external_item_id}:{rule_id}".encode("utf-8")
    ).hexdigest()
    return digest[:24]


def _build_alert_title(action: str, symbol: str | None, source: SignalSourceConfig) -> str:
    action_label = action.upper()
    if symbol:
        return f"{action_label} {symbol} from {source.account}"
    return f"{action_label} signal from {source.account}"


def _notify_direct_alert(alert: SignalAlert) -> None:
    manager = get_notification_manager()
    if not manager.enabled:
        return

    symbol_text = f" {alert.symbol}" if alert.symbol else ""
    message = (
        f"{alert.action.upper()}{symbol_text} from {alert.source_label}\n"
        f"{alert.reason}\n"
        f"{alert.external_url}"
    )
    manager.send("market_signal_alert", {"message": message})


def _latest_timestamp(values: Iterable[datetime | None]) -> datetime | None:
    timestamps = [value for value in values if value is not None]
    return max(timestamps) if timestamps else None


def _max_timestamp(left: datetime | None, right: datetime | None) -> datetime | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)
