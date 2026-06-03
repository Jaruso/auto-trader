"""Configuration management for Kodiak."""

import os
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv


class Environment(Enum):
    """Trading environment."""

    PAPER = "paper"
    PROD = "prod"


class Service(Enum):
    """Supported broker services."""

    ALPACA = "alpaca"
    # Future: SCHWAB = "schwab"


# Service URLs - hardcoded, not configurable
SERVICE_URLS: dict[Service, dict[Environment, str]] = {
    Service.ALPACA: {
        Environment.PAPER: "https://paper-api.alpaca.markets",
        Environment.PROD: "https://api.alpaca.markets",
    },
    # Future:
    # Service.SCHWAB: {
    #     Environment.PAPER: "https://sandbox.schwab.com",
    #     Environment.PROD: "https://api.schwab.com",
    # },
}

# Default service
DEFAULT_SERVICE = Service.ALPACA


@dataclass
class StrategyDefaults:
    """Default values for strategy parameters.

    These can be overridden per-strategy via CLI options.
    """

    trailing_stop_pct: Decimal = Decimal("5.0")
    take_profit_pct: Decimal = Decimal("10.0")
    stop_loss_pct: Decimal = Decimal("5.0")
    default_quantity: int = 10

    # Default scale-out tranches: sell 33% at +5%, 33% at +10%, 34% at +15%
    scale_tranches: list[dict] = field(default_factory=lambda: [
        {"pct": 33, "target_pct": 5},
        {"pct": 33, "target_pct": 10},
        {"pct": 34, "target_pct": 15},
    ])

    # Grid defaults
    grid_levels: int = 5
    grid_spacing_pct: Decimal = Decimal("2.0")
    grid_qty_per_level: int = 10


@dataclass
class DataCacheConfig:
    """Cache settings for historical data providers."""

    enabled: bool
    backend: str
    directory: Path
    ttl_minutes: int


@dataclass
class DataConfig:
    """Data provider configuration."""

    source: str
    csv_dir: Path
    alpaca_feed: str | None
    cache: DataCacheConfig


def _default_data_config() -> DataConfig:
    return DataConfig(
        source="csv",
        csv_dir=Path("data") / "historical",
        alpaca_feed=None,
        cache=DataCacheConfig(
            enabled=True,
            backend="parquet",
            directory=Path("data") / "cache",
            ttl_minutes=60,
        ),
    )


@dataclass
class Config:
    """Application configuration."""

    env: Environment
    service: Service
    base_url: str
    alpaca_api_key: str
    alpaca_secret_key: str
    data_dir: Path
    log_dir: Path
    strategy_defaults: StrategyDefaults
    data: DataConfig = field(default_factory=_default_data_config)

    @property
    def is_paper(self) -> bool:
        """Check if running in paper trading mode."""
        return self.env == Environment.PAPER

    @property
    def is_prod(self) -> bool:
        """Check if running in production mode."""
        return self.env == Environment.PROD


def load_config(
    service: str | None = None,
    prod: bool = False,
) -> Config:
    """Load configuration.

    Args:
        service: Broker service to use ('alpaca', etc.). Defaults to alpaca.
        prod: If True, use production environment. Defaults to False (paper).

    Returns:
        Config object with loaded settings.
    """
    from kodiak.utils.paths import get_config_dir, get_project_root
    project_root = get_project_root()

    # Load .env files: project root, CWD, then config .env (so CLI-set values are used).
    config_parent = get_config_dir().parent
    for candidate in [
        project_root / ".env",
        project_root.parent / ".env",
        Path.cwd() / ".env",
        config_parent / ".env",
        Path.home() / ".kodiak" / ".env",
    ]:
        if candidate.is_file():
            load_dotenv(candidate)

    # Determine service
    if service:
        try:
            svc = Service(service.lower())
        except ValueError:
            raise ValueError(f"Unknown service: {service}. Supported: {[s.value for s in Service]}")
    else:
        svc = DEFAULT_SERVICE

    # Determine environment
    environment = Environment.PROD if prod else Environment.PAPER

    # Get URL for this service/environment (env override for Alpaca)
    base_url = SERVICE_URLS[svc][environment]
    if svc == Service.ALPACA:
        override = os.getenv("ALPACA_PAPER_BASE_URL" if environment == Environment.PAPER else "ALPACA_PROD_BASE_URL")
        if override and override.strip():
            base_url = override.strip()

    # Get API credentials - use different env vars for prod vs paper
    if prod:
        alpaca_api_key = os.getenv("ALPACA_PROD_API_KEY", "")
        alpaca_secret_key = os.getenv("ALPACA_PROD_SECRET_KEY", "")
    else:
        alpaca_api_key = os.getenv("ALPACA_API_KEY", "")
        alpaca_secret_key = os.getenv("ALPACA_SECRET_KEY", "")

    # Set up directories - use user directories when installed, project dirs in dev
    from kodiak.utils.paths import get_config_dir, get_data_dir, get_log_dir

    # Check if we're in development mode (config dir exists in project root)
    is_dev_mode = (project_root / "config" / "strategies.yaml").exists() or (project_root / "pyproject.toml").exists()

    if is_dev_mode:
        # Development mode - use project directories
        data_dir = project_root / "data"
        log_dir = project_root / "logs"
    else:
        # Installed mode - use user directories
        data_dir = get_data_dir()
        log_dir = get_log_dir()

    # Data provider config
    data_source = os.getenv("DATA_SOURCE", "csv")
    csv_dir = Path(os.getenv("HISTORICAL_DATA_DIR", str(data_dir / "historical")))
    alpaca_feed = os.getenv("ALPACA_DATA_FEED") or None

    cache_enabled = os.getenv("DATA_CACHE_ENABLED", "true").lower() in {"1", "true", "yes"}
    cache_backend = os.getenv("DATA_CACHE_BACKEND", "parquet")
    cache_dir = Path(os.getenv("DATA_CACHE_DIR", str(data_dir / "cache")))
    cache_ttl_minutes = int(os.getenv("DATA_CACHE_TTL_MINUTES", "60"))

    data_config = DataConfig(
        source=data_source,
        csv_dir=csv_dir,
        alpaca_feed=alpaca_feed,
        cache=DataCacheConfig(
            enabled=cache_enabled,
            backend=cache_backend,
            directory=cache_dir,
            ttl_minutes=cache_ttl_minutes,
        ),
    )

    # Load strategy defaults from environment
    strategy_defaults = StrategyDefaults(
        trailing_stop_pct=Decimal(os.getenv("STRATEGY_TRAILING_STOP_PCT", "5.0")),
        take_profit_pct=Decimal(os.getenv("STRATEGY_TAKE_PROFIT_PCT", "10.0")),
        stop_loss_pct=Decimal(os.getenv("STRATEGY_STOP_LOSS_PCT", "5.0")),
        default_quantity=int(os.getenv("STRATEGY_DEFAULT_QTY", "10")),
    )

    return Config(
        env=environment,
        service=svc,
        base_url=base_url,
        alpaca_api_key=alpaca_api_key,
        alpaca_secret_key=alpaca_secret_key,
        data_dir=data_dir,
        log_dir=log_dir,
        strategy_defaults=strategy_defaults,
        data=data_config,
    )
