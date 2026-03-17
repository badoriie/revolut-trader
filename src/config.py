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


# Revolut API base URL — not a secret, just a constant.
REVOLUT_API_BASE_URL = "https://revx.revolut.com/api/1.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
    )

    # Trading configuration — loaded from 1Password in model_post_init.
    # These temporary defaults are required by Pydantic for model construction;
    # model_post_init overwrites every one of them from 1Password and raises
    # RuntimeError if any are missing.
    trading_mode: TradingMode = TradingMode.PAPER
    default_strategy: StrategyType = StrategyType.MARKET_MAKING
    risk_level: RiskLevel = RiskLevel.CONSERVATIVE
    base_currency: str = "EUR"
    trading_pairs: list[str] = Field(default_factory=list)

    @field_validator("trading_pairs", mode="before")
    @classmethod
    def parse_trading_pairs(cls, v):
        if isinstance(v, str):
            return [pair.strip() for pair in v.split(",")]
        return v

    def model_post_init(self, __context):
        """Load ALL configuration from 1Password. Raises if anything required is missing."""
        import src.utils.onepassword as op

        # TRADING_MODE
        try:
            self.trading_mode = TradingMode(op.get("TRADING_MODE").lower())
        except ValueError as e:
            raise ValueError(
                f"Invalid TRADING_MODE in 1Password: must be 'paper' or 'live'."
            ) from e

        # RISK_LEVEL
        try:
            self.risk_level = RiskLevel(op.get("RISK_LEVEL").lower())
        except ValueError as e:
            raise ValueError(
                f"Invalid RISK_LEVEL in 1Password: must be 'conservative', 'moderate', or 'aggressive'."
            ) from e

        # DEFAULT_STRATEGY
        try:
            self.default_strategy = StrategyType(op.get("DEFAULT_STRATEGY").lower())
        except ValueError as e:
            raise ValueError(
                f"Invalid DEFAULT_STRATEGY in 1Password: must be 'market_making', 'momentum', "
                f"'mean_reversion', or 'multi_strategy'."
            ) from e

        # BASE_CURRENCY
        self.base_currency = op.get("BASE_CURRENCY").upper()

        # TRADING_PAIRS
        pairs_str = op.get("TRADING_PAIRS")
        self.trading_pairs = [p.strip().strip("\"'") for p in pairs_str.split(",")]

        # INITIAL_CAPITAL
        try:
            self.paper_initial_capital = float(op.get("INITIAL_CAPITAL"))
        except ValueError as e:
            raise ValueError(
                "Invalid INITIAL_CAPITAL in 1Password: must be a positive number."
            ) from e

    # Risk Management
    max_position_size_pct: float = Field(default=2.0, ge=0.1, le=100.0)
    max_daily_loss_pct: float = Field(default=5.0, ge=0.1, le=100.0)
    stop_loss_pct: float = Field(default=2.0, ge=0.1, le=50.0)
    take_profit_pct: float = Field(default=3.0, ge=0.1, le=100.0)

    # Logging
    log_level: str = Field(default="INFO")
    log_file: Path = Field(default=Path("./logs/trading.log"))

    # Paper Trading (populated in model_post_init from 1Password INITIAL_CAPITAL)
    paper_initial_capital: float = Field(default=10000.0, ge=1.0)

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


settings = Settings()