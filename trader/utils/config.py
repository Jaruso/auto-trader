"""Configuration management for AutoTrader."""

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


class Environment(Enum):
    """Trading environment."""

    PAPER = "paper"
    PROD = "prod"


@dataclass
class Config:
    """Application configuration."""

    env: Environment
    broker: str
    alpaca_api_key: str
    alpaca_secret_key: str
    base_url: str
    enable_prod: bool
    data_dir: Path
    log_dir: Path

    @property
    def is_paper(self) -> bool:
        """Check if running in paper trading mode."""
        return self.env == Environment.PAPER

    @property
    def is_prod(self) -> bool:
        """Check if running in production mode."""
        return self.env == Environment.PROD and self.enable_prod


def load_config(env: Optional[str] = None) -> Config:
    """Load configuration from environment variables.

    Args:
        env: Environment to load ('paper' or 'prod'). If None, uses TRADER_ENV.

    Returns:
        Config object with loaded settings.

    Raises:
        ValueError: If required configuration is missing.
    """
    project_root = Path(__file__).parent.parent.parent

    # Determine which env file to load
    env_name = env or os.getenv("TRADER_ENV", "paper")
    env_file = project_root / f".env.{env_name}"

    if env_file.exists():
        load_dotenv(env_file)
    else:
        # Fall back to .env
        load_dotenv(project_root / ".env")

    # Parse environment
    try:
        environment = Environment(env_name.lower())
    except ValueError:
        environment = Environment.PAPER

    # Get required values
    alpaca_api_key = os.getenv("ALPACA_API_KEY", "")
    alpaca_secret_key = os.getenv("ALPACA_SECRET_KEY", "")

    if not alpaca_api_key or not alpaca_secret_key:
        # Allow running without keys for status checks
        pass

    # Set up directories
    data_dir = project_root / "data"
    log_dir = project_root / "logs"

    return Config(
        env=environment,
        broker=os.getenv("BROKER", "alpaca"),
        alpaca_api_key=alpaca_api_key,
        alpaca_secret_key=alpaca_secret_key,
        base_url=os.getenv("BASE_URL", "https://paper-api.alpaca.markets"),
        enable_prod=os.getenv("ENABLE_PROD", "false").lower() == "true",
        data_dir=data_dir,
        log_dir=log_dir,
    )
