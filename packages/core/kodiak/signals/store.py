"""Persistence helpers for market-signal alerts and runtime state."""

from __future__ import annotations

import json
from pathlib import Path

from kodiak.signals.models import SignalAlert, SourceRuntimeState
from kodiak.utils.paths import get_data_dir

ALERTS_FILENAME = "alerts.json"
STATE_FILENAME = "state.json"


def get_signals_data_dir(data_dir: Path | None = None) -> Path:
    """Return the on-disk directory for signal-monitor state."""
    base_dir = get_data_dir(data_dir)
    signals_dir = base_dir / "signals"
    signals_dir.mkdir(parents=True, exist_ok=True)
    return signals_dir


def _write_json(path: Path, payload: object) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    temp_path.replace(path)


def load_alerts(data_dir: Path | None = None) -> list[SignalAlert]:
    """Load stored alerts from disk."""
    path = get_signals_data_dir(data_dir) / ALERTS_FILENAME
    if not path.is_file():
        return []
    payload = json.loads(path.read_text() or "[]")
    return [SignalAlert.model_validate(item) for item in payload]


def save_alerts(alerts: list[SignalAlert], data_dir: Path | None = None) -> None:
    """Persist alerts to disk."""
    path = get_signals_data_dir(data_dir) / ALERTS_FILENAME
    _write_json(path, [alert.model_dump(mode="json") for alert in alerts])


def load_runtime_state(data_dir: Path | None = None) -> dict[str, SourceRuntimeState]:
    """Load per-source runtime state."""
    path = get_signals_data_dir(data_dir) / STATE_FILENAME
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text() or "{}")
    return {
        source_id: SourceRuntimeState.model_validate(item)
        for source_id, item in payload.items()
    }


def save_runtime_state(
    state: dict[str, SourceRuntimeState],
    data_dir: Path | None = None,
) -> None:
    """Persist per-source runtime state."""
    path = get_signals_data_dir(data_dir) / STATE_FILENAME
    _write_json(
        path,
        {source_id: item.model_dump(mode="json") for source_id, item in state.items()},
    )

