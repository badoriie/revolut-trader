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

    # Trading - Can be overridden via 1Password
    trading_mode: TradingMode = Field(default=TradingMode.PAPER)
    default_strategy: StrategyType = Field(default=StrategyType.MARKET_MAKING)
    risk_level: RiskLevel = Field(default=RiskLevel.CONSERVATIVE)
    base_currency: str = Field(default="EUR")  # Base fiat currency for portfolio valuation
    trading_pairs: list[str] = Field(default=["BTC-EUR", "ETH-EUR"])

    @field_validator("trading_pairs", mode="before")
    @classmethod
    def parse_trading_pairs(cls, v):
        if isinstance(v, str):
            return [pair.strip() for pair in v.split(",")]
        return v

    def model_post_init(self, __context):
        """Load configuration overrides from 1Password after initialization."""
        try:
            from src.utils.onepassword import get_config

            # Try to load config from 1Password (optional - falls back to defaults)
            trading_mode_str = get_config("TRADING_MODE", self.trading_mode.value)
            if trading_mode_str and trading_mode_str != self.trading_mode.value:
                try:
                    self.trading_mode = TradingMode(trading_mode_str.lower())
                except ValueError:
                    pass  # Invalid value, keep default

            strategy_str = get_config("DEFAULT_STRATEGY", self.default_strategy.value)
            if strategy_str and strategy_str != self.default_strategy.value:
                try:
                    self.default_strategy = StrategyType(strategy_str.lower())
                except ValueError:
                    pass

            risk_str = get_config("RISK_LEVEL", self.risk_level.value)
            if risk_str and risk_str != self.risk_level.value:
                try:
                    self.risk_level = RiskLevel(risk_str.lower())
                except ValueError:
                    pass

            base_curr = get_config("BASE_CURRENCY", self.base_currency)
            if base_curr:
                self.base_currency = base_curr.upper()

            pairs_str = get_config("TRADING_PAIRS", ",".join(self.trading_pairs))
            if pairs_str:
                self.trading_pairs = [p.strip() for p in pairs_str.split(",")]

            capital_str = get_config("INITIAL_CAPITAL", str(self.paper_initial_capital))
            if capital_str:
                try:
                    self.paper_initial_capital = float(capital_str)
                except ValueError:
                    pass

        except Exception:  # nosec B110
            # If there's any error loading from 1Password, just use defaults
            # This is intentional - we want graceful degradation if 1Password is unavailable
            pass

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
