from enum import Enum

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
            raise ValueError("Invalid TRADING_MODE in 1Password: must be 'paper' or 'live'.") from e

        # RISK_LEVEL
        try:
            self.risk_level = RiskLevel(op.get("RISK_LEVEL").lower())
        except ValueError as e:
            raise ValueError(
                "Invalid RISK_LEVEL in 1Password: must be 'conservative', 'moderate', or 'aggressive'."
            ) from e

        # DEFAULT_STRATEGY
        try:
            self.default_strategy = StrategyType(op.get("DEFAULT_STRATEGY").lower())
        except ValueError as e:
            raise ValueError(
                "Invalid DEFAULT_STRATEGY in 1Password: must be 'market_making', 'momentum', "
                "'mean_reversion', or 'multi_strategy'."
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

    # Logging
    log_level: str = Field(default="INFO")

    # Paper Trading (populated in model_post_init from 1Password INITIAL_CAPITAL)
    paper_initial_capital: float = Field(default=10000.0, ge=1.0)


settings = Settings()
