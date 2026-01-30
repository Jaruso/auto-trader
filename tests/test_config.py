"""Tests for configuration module."""

import os
from unittest.mock import patch

import pytest

from trader.utils.config import Config, Environment, load_config


def test_environment_enum() -> None:
    """Test Environment enum values."""
    assert Environment.PAPER.value == "paper"
    assert Environment.PROD.value == "prod"


def test_config_is_paper() -> None:
    """Test is_paper property."""
    config = Config(
        env=Environment.PAPER,
        broker="alpaca",
        alpaca_api_key="test",
        alpaca_secret_key="test",
        base_url="https://paper-api.alpaca.markets",
        enable_prod=False,
        data_dir=None,  # type: ignore
        log_dir=None,  # type: ignore
    )
    assert config.is_paper is True
    assert config.is_prod is False


def test_config_is_prod_disabled() -> None:
    """Test is_prod when enable_prod is False."""
    config = Config(
        env=Environment.PROD,
        broker="alpaca",
        alpaca_api_key="test",
        alpaca_secret_key="test",
        base_url="https://api.alpaca.markets",
        enable_prod=False,
        data_dir=None,  # type: ignore
        log_dir=None,  # type: ignore
    )
    assert config.is_paper is False
    assert config.is_prod is False  # disabled even though env is PROD


def test_config_is_prod_enabled() -> None:
    """Test is_prod when enable_prod is True."""
    config = Config(
        env=Environment.PROD,
        broker="alpaca",
        alpaca_api_key="test",
        alpaca_secret_key="test",
        base_url="https://api.alpaca.markets",
        enable_prod=True,
        data_dir=None,  # type: ignore
        log_dir=None,  # type: ignore
    )
    assert config.is_paper is False
    assert config.is_prod is True


def test_load_config_defaults() -> None:
    """Test load_config with default values."""
    with patch.dict(os.environ, {}, clear=True):
        config = load_config("paper")

    assert config.env == Environment.PAPER
    assert config.broker == "alpaca"
    assert "paper-api.alpaca.markets" in config.base_url
    assert config.enable_prod is False
