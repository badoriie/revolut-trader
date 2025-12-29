from enum import Enum
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class StrategyType(str, Enum):
    MARKET_MAKING = "market_making"
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    MULTI_STRATEGY = "multi_strategy"


class RiskLevel(str, Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
    )

    # All credentials are retrieved from 1Password only
    # No .env file dependency for security
    # Configuration can also be stored in 1Password (optional, falls back to defaults)

    # Revolut API
    revolut_api_key: str = Field(default="")
    revolut_private_key_path: Path = Field(default=Path("./config/revolut_private.pem"))
    revolut_api_base_url: str = Field(default="https://revx.revolut.com/api/1.0")

    # Trading configuration - MUST be set in 1Password (no code defaults for safety)
    # These are loaded from 1Password config item in model_post_init()
    # Using temporary defaults that will be overwritten - the actual validation happens in model_post_init
    trading_mode: TradingMode = TradingMode.PAPER  # Will be loaded from 1Password
    default_strategy: StrategyType = StrategyType.MARKET_MAKING  # Will be loaded from 1Password
    risk_level: RiskLevel = RiskLevel.CONSERVATIVE  # Will be loaded from 1Password
    base_currency: str = "EUR"  # Will be loaded from 1Password
    trading_pairs: list[str] = Field(default_factory=list)  # Will be loaded from 1Password

    @field_validator("trading_pairs", mode="before")
    @classmethod
    def parse_trading_pairs(cls, v):
        if isinstance(v, str):
            return [pair.strip() for pair in v.split(",")]
        return v

    def model_post_init(self, __context):
        """Load configuration from 1Password - REQUIRED for all trading config.

        All trading configuration must be stored in 1Password for safety.
        This prevents accidental use of hardcoded defaults.
        """
        from src.utils.onepassword import get_config

        # Load TRADING_MODE (REQUIRED)
        trading_mode_str = get_config("TRADING_MODE", None)
        if not trading_mode_str:
            raise RuntimeError(
                "TRADING_MODE not found in 1Password config.\n"
                "Run: make opconfig-init\n"
                "Or manually set: make opconfig-set KEY=TRADING_MODE VALUE=paper"
            )
        try:
            self.trading_mode = TradingMode(trading_mode_str.lower())
        except ValueError as e:
            raise ValueError(
                f"Invalid TRADING_MODE in 1Password: '{trading_mode_str}'. "
                f"Must be 'paper' or 'live'."
            ) from e

        # Load RISK_LEVEL (REQUIRED)
        risk_str = get_config("RISK_LEVEL", None)
        if not risk_str:
            raise RuntimeError(
                "RISK_LEVEL not found in 1Password config.\n" "Run: make opconfig-init"
            )
        try:
            self.risk_level = RiskLevel(risk_str.lower())
        except ValueError as e:
            raise ValueError(
                f"Invalid RISK_LEVEL in 1Password: '{risk_str}'. "
                f"Must be 'conservative', 'moderate', or 'aggressive'."
            ) from e

        # Load DEFAULT_STRATEGY (REQUIRED)
        strategy_str = get_config("DEFAULT_STRATEGY", None)
        if not strategy_str:
            raise RuntimeError(
                "DEFAULT_STRATEGY not found in 1Password config.\n" "Run: make opconfig-init"
            )
        try:
            self.default_strategy = StrategyType(strategy_str.lower())
        except ValueError as e:
            raise ValueError(
                f"Invalid DEFAULT_STRATEGY in 1Password: '{strategy_str}'. "
                f"Must be 'market_making', 'momentum', 'mean_reversion', or 'multi_strategy'."
            ) from e

        # Load BASE_CURRENCY (REQUIRED)
        base_curr = get_config("BASE_CURRENCY", None)
        if not base_curr:
            raise RuntimeError(
                "BASE_CURRENCY not found in 1Password config.\n" "Run: make opconfig-init"
            )
        self.base_currency = base_curr.upper()

        # Load TRADING_PAIRS (REQUIRED)
        pairs_str = get_config("TRADING_PAIRS", None)
        if not pairs_str:
            raise RuntimeError(
                "TRADING_PAIRS not found in 1Password config.\n" "Run: make opconfig-init"
            )
        self.trading_pairs = [p.strip() for p in pairs_str.split(",")]

        # Load INITIAL_CAPITAL (REQUIRED)
        capital_str = get_config("INITIAL_CAPITAL", None)
        if not capital_str:
            raise RuntimeError(
                "INITIAL_CAPITAL not found in 1Password config.\n" "Run: make opconfig-init"
            )
        try:
            self.paper_initial_capital = float(capital_str)
        except ValueError as e:
            raise ValueError(
                f"Invalid INITIAL_CAPITAL in 1Password: '{capital_str}'. "
                f"Must be a positive number."
            ) from e

    # Risk Management
    max_position_size_pct: float = Field(default=2.0, ge=0.1, le=100.0)
    max_daily_loss_pct: float = Field(default=5.0, ge=0.1, le=100.0)
    stop_loss_pct: float = Field(default=2.0, ge=0.1, le=50.0)
    take_profit_pct: float = Field(default=3.0, ge=0.1, le=100.0)

    # Telegram Notifications
    telegram_bot_token: str = Field(default="")
    telegram_chat_id: str = Field(default="")
    enable_telegram: bool = Field(default=False)

    # Logging
    log_level: str = Field(default="INFO")
    log_file: Path = Field(default=Path("./logs/trading.log"))

    # Paper Trading
    paper_initial_capital: float = Field(default=10000.0, ge=1.0)  # In base currency (EUR)

    def get_risk_parameters(self) -> dict:
        """Get risk parameters based on risk level."""
        risk_params = {
            RiskLevel.CONSERVATIVE: {
                "max_position_size_pct": 1.5,
                "max_daily_loss_pct": 3.0,
                "stop_loss_pct": 1.5,
                "take_profit_pct": 2.5,
                "max_open_positions": 3,
            },
            RiskLevel.MODERATE: {
                "max_position_size_pct": 3.0,
                "max_daily_loss_pct": 5.0,
                "stop_loss_pct": 2.5,
                "take_profit_pct": 4.0,
                "max_open_positions": 5,
            },
            RiskLevel.AGGRESSIVE: {
                "max_position_size_pct": 5.0,
                "max_daily_loss_pct": 10.0,
                "stop_loss_pct": 4.0,
                "take_profit_pct": 7.0,
                "max_open_positions": 8,
            },
        }
        return risk_params.get(self.risk_level, risk_params[RiskLevel.CONSERVATIVE])

    def get_private_key_content(self) -> str:
        """Get private key content from 1Password only (no .env fallback).

        Retrieves private key from 1Password vault.
        This is the only secure way to store credentials.

        Returns:
            PEM-encoded private key content

        Raises:
            RuntimeError: If 1Password is not available or private key not found
        """
        from src.utils.onepassword import OnePasswordClient

        client = OnePasswordClient()

        # 1Password is required - no fallback
        if not client.is_available():
            raise RuntimeError(
                "1Password is required but not available. Please:\n"
                "1. Install 1Password CLI: brew install --cask 1password-cli\n"
                "2. Sign in: eval $(op signin)\n"
                "3. Store your private key: op item edit revolut-trader-credentials "
                '--vault revolut-trader REVOLUT_PRIVATE_KEY[concealed]="$(cat config/revolut_private.pem)"\n'
            )

        private_key_pem = client.get_field("REVOLUT_PRIVATE_KEY")
        if not private_key_pem:
            raise RuntimeError(
                "Private key not found in 1Password. Please store it:\n"
                "op item edit revolut-trader-credentials --vault revolut-trader "
                'REVOLUT_PRIVATE_KEY[concealed]="$(cat config/revolut_private.pem)"'
            )

        return private_key_pem


settings = Settings()
