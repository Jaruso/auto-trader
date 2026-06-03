"""Configuration loading for deterministic market signals."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from kodiak.signals.models import SignalMonitorConfig
from kodiak.utils.paths import get_config_dir

DEFAULT_CONFIG_FILENAME = "market_signals.yaml"
EXAMPLE_CONFIG_FILENAME = "market_signals.yaml.example"


def get_market_signals_config_path(config_dir: Path | None = None) -> Path:
    """Return the active signal-monitor config path."""
    override = os.getenv("KODIAK_SIGNAL_CONFIG", "").strip()
    if override:
        return Path(override)
    base_dir = get_config_dir(config_dir)
    return base_dir / DEFAULT_CONFIG_FILENAME


def load_market_signals_config(config_dir: Path | None = None) -> SignalMonitorConfig:
    """Load the signal monitor config or return a disabled config when absent."""
    path = get_market_signals_config_path(config_dir)
    if not path.is_file():
        return SignalMonitorConfig()

    with open(path) as handle:
        payload = yaml.safe_load(handle) or {}

    config = SignalMonitorConfig.model_validate(payload)

    x_user_data_dir = os.getenv("KODIAK_X_USER_DATA_DIR", "").strip()
    x_executable_path = os.getenv("KODIAK_X_EXECUTABLE_PATH", "").strip()
    x_headless = os.getenv("KODIAK_X_HEADLESS", "").strip().lower()

    if x_user_data_dir:
        config.x.user_data_dir = x_user_data_dir
    if x_executable_path:
        config.x.executable_path = x_executable_path
    if x_headless in {"0", "1", "true", "false", "yes", "no"}:
        config.x.headless = x_headless in {"1", "true", "yes"}

    enabled_override = os.getenv("KODIAK_SIGNAL_MONITOR_ENABLED", "").strip().lower()
    if enabled_override in {"0", "1", "true", "false", "yes", "no"}:
        config.enabled = enabled_override in {"1", "true", "yes"}

    return config

