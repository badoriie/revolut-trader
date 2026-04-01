import os
from enum import StrEnum

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Deployment environment — determines which 1Password items and DB to use."""

    DEV = "dev"
    INT = "int"
    PROD = "prod"


class TradingMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class StrategyType(StrEnum):
    MARKET_MAKING = "market_making"
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    MULTI_STRATEGY = "multi_strategy"
    BREAKOUT = "breakout"
    RANGE_REVERSION = "range_reversion"


class RiskLevel(StrEnum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


# Revolut API base URLs — primary and fallback (not secrets, just constants).
# The client tries URLs in order; on connection failure it advances to the next.
REVOLUT_API_BASE_URL = "https://revx.revolut.com/api/1.0"
REVOLUT_API_BASE_URL_FALLBACK = "https://revx.revolut.codes/api/1.0"
REVOLUT_API_BASE_URLS = [REVOLUT_API_BASE_URL, REVOLUT_API_BASE_URL_FALLBACK]


def _load_optional_float(op, key: str, error_msg: str) -> float | None:
    """Load an optional positive float from 1Password.

    Args:
        op:        The onepassword module.
        key:       The 1Password config key to read.
        error_msg: Message prefix for the ValueError if the value is invalid.

    Returns:
        The float value, or None if the key is not present in the vault.
    """
    raw = op.get_optional(key)
    if raw is None:
        return None
    try:
        val = float(raw)
        if val <= 0:
            raise ValueError("must be a positive number")
        return val
    except ValueError as e:
        raise ValueError(error_msg) from e


def _load_optional_int(op, key: str, error_msg: str) -> int | None:
    """Load an optional positive integer from 1Password.

    Args:
        op:        The onepassword module.
        key:       The 1Password config key to read.
        error_msg: Message prefix for the ValueError if the value is invalid.

    Returns:
        The int value, or None if the key is not present in the vault.
    """
    raw = op.get_optional(key)
    if raw is None:
        return None
    try:
        val = int(raw)
        if val <= 0:
            raise ValueError("must be a positive integer")
        return val
    except ValueError as e:
        raise ValueError(error_msg) from e


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
    )

    # Environment — resolved from os.environ before any 1Password access.
    environment: Environment = Environment.DEV

    # Trading configuration — loaded from 1Password in model_post_init (except
    # trading_mode which is derived from environment).  These temporary defaults
    # are required by Pydantic for model construction; model_post_init overwrites
    # every one of them and raises RuntimeError if any are missing.
    trading_mode: TradingMode = TradingMode.PAPER
    default_strategy: StrategyType = StrategyType.MARKET_MAKING
    risk_level: RiskLevel = RiskLevel.CONSERVATIVE
    base_currency: str = "EUR"
    trading_pairs: list[str] = Field(default_factory=list)

    @field_validator("environment", mode="before")
    @classmethod
    def normalize_environment(cls, v):
        """Accept ENVIRONMENT in any case (DEV, Dev, dev → dev)."""
        if isinstance(v, str):
            return v.lower()
        return v

    @field_validator("trading_pairs", mode="before")
    @classmethod
    def parse_trading_pairs(cls, v):
        if isinstance(v, str):
            return [pair.strip() for pair in v.split(",")]
        return v

    def model_post_init(self, __context):
        """Load ALL configuration from 1Password. Raises if anything required is missing."""
        import src.utils.onepassword as op

        self._load_environment()
        self._load_trading_config(op)
        self._load_capital_config(op)

    def _load_environment(self) -> None:
        """Resolve and validate ENVIRONMENT from os.environ."""
        env_str = os.environ.get("ENVIRONMENT")
        if not env_str:
            raise RuntimeError(
                "ENVIRONMENT not set. Export it before running:\n"
                "  export ENVIRONMENT=dev   # or: int, prod\n"
                "Or use: make run / make run ENV=int / make run ENV=prod"
            )
        try:
            self.environment = Environment(env_str.lower())
        except ValueError as e:
            raise ValueError(
                f"Invalid ENVIRONMENT '{env_str}': must be 'dev', 'int', or 'prod'."
            ) from e

        # TRADING_MODE is derived from environment — not stored in 1Password.
        self.trading_mode = (
            TradingMode.LIVE if self.environment == Environment.PROD else TradingMode.PAPER
        )

    def _load_trading_config(self, op) -> None:
        """Load strategy, pairs, and currency config from 1Password."""
        try:
            self.risk_level = RiskLevel(op.get("RISK_LEVEL").lower())
        except ValueError as e:
            raise ValueError(
                "Invalid RISK_LEVEL in 1Password: must be 'conservative', 'moderate', or 'aggressive'."
            ) from e

        try:
            self.default_strategy = StrategyType(op.get("DEFAULT_STRATEGY").lower())
        except ValueError as e:
            raise ValueError(
                "Invalid DEFAULT_STRATEGY in 1Password: must be one of "
                "'market_making', 'momentum', 'mean_reversion', 'multi_strategy', "
                "'breakout', or 'range_reversion'."
            ) from e

        self.base_currency = op.get("BASE_CURRENCY").upper()

        pairs_str = op.get("TRADING_PAIRS")
        self.trading_pairs = [p.strip().strip("\"'") for p in pairs_str.split(",")]
        self._validate_trading_pairs()

        if self.trading_mode == TradingMode.PAPER:
            try:
                self.paper_initial_capital = float(op.get("INITIAL_CAPITAL"))
            except ValueError as e:
                raise ValueError(
                    "Invalid INITIAL_CAPITAL in 1Password: must be a positive number."
                ) from e

    def _validate_trading_pairs(self) -> None:
        """Raise ValueError if any pair's quote currency doesn't match BASE_CURRENCY."""
        mismatched = [
            p for p in self.trading_pairs if not p.upper().endswith(f"-{self.base_currency}")
        ]
        if mismatched:
            msg = (
                f"Trading pair(s) {mismatched} do not match BASE_CURRENCY '{self.base_currency}'.\n"
                f"All pairs must end with '-{self.base_currency}' (e.g. BTC-{self.base_currency}).\n"
                f"Fix with: make opconfig-set KEY=TRADING_PAIRS VALUE=BTC-{self.base_currency} ENV=<env>\n"
                f"Or update BASE_CURRENCY: make opconfig-set KEY=BASE_CURRENCY VALUE=<currency> ENV=<env>"
            )
            raise ValueError(msg)

    def _load_capital_config(self, op) -> None:
        """Load optional capital-limiting and notification config from 1Password."""
        self.max_capital = _load_optional_float(
            op,
            "MAX_CAPITAL",
            "Invalid MAX_CAPITAL in 1Password: must be a positive number.\n"
            "Set it with: make opconfig-set KEY=MAX_CAPITAL VALUE=5000 ENV=prod",
        )
        self.shutdown_trailing_stop_pct = _load_optional_float(
            op,
            "SHUTDOWN_TRAILING_STOP_PCT",
            "Invalid SHUTDOWN_TRAILING_STOP_PCT in 1Password: must be a positive number "
            "(e.g. 0.5 for 0.5%).\n"
            "Set it with: make opconfig-set KEY=SHUTDOWN_TRAILING_STOP_PCT VALUE=0.5 ENV=dev",
        )
        self.shutdown_max_wait_seconds = _load_optional_int(
            op,
            "SHUTDOWN_MAX_WAIT_SECONDS",
            "Invalid SHUTDOWN_MAX_WAIT_SECONDS in 1Password: must be a positive integer "
            "(e.g. 120 for 2 minutes).\n"
            "Set it with: make opconfig-set KEY=SHUTDOWN_MAX_WAIT_SECONDS VALUE=120 ENV=dev",
        )
        self.telegram_bot_token = op.get_optional("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = op.get_optional("TELEGRAM_CHAT_ID")

    # Logging
    log_level: str = Field(default="INFO")

    # Paper Trading (populated in model_post_init from 1Password INITIAL_CAPITAL)
    paper_initial_capital: float = Field(default=10000.0, ge=1.0)

    # Maximum capital the bot is allowed to trade with (optional).
    # If set, cash_balance is capped to this value at startup — the bot will
    # never consider more than this amount as available capital, even if the
    # account holds more.  None means "use the full available balance".
    max_capital: float | None = Field(default=None)

    # Shutdown trailing stop percentage (optional).
    # When the bot shuts down, profitable positions are held open with a trailing
    # stop this many percent below the running high-watermark price.  The position
    # is closed when the price falls back to the stop, or when shutdown_max_wait_seconds
    # expires — whichever comes first.  None disables trailing stop (immediate close).
    # Example: 0.5 = 0.5% trailing stop.
    shutdown_trailing_stop_pct: float | None = Field(default=None)

    # Maximum seconds to wait for a profitable position's trailing stop to trigger
    # before force-closing at market price.  None means "use system default of 120s".
    shutdown_max_wait_seconds: int | None = Field(default=None)

    # Telegram notifications (optional — both must be set to enable).
    # Store in 1Password with: make ops ENV=<env>                                  (bot token, concealed)
    #                          make opconfig-set KEY=TELEGRAM_CHAT_ID VALUE=<id> ENV=<env>
    telegram_bot_token: str | None = Field(default=None)
    telegram_chat_id: str | None = Field(default=None)


settings = Settings()
