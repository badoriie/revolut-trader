import os
from dataclasses import dataclass
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


@dataclass(frozen=True)
class RiskLevelConfig:
    """Risk parameters for a single risk level, sourced from 1Password.

    These values control position sizing, daily loss limits, and stop-loss /
    take-profit percentages for the given risk level.  They are stored in
    ``revolut-trader-risk-{level}`` items in 1Password (no env suffix — the
    same risk parameters apply across dev, int, and prod).
    """

    max_position_size_pct: float
    """Maximum position size as a percentage of portfolio value."""

    max_daily_loss_pct: float
    """Maximum daily loss as a percentage of initial capital before trading is suspended."""

    stop_loss_pct: float
    """Default stop-loss percentage for this risk level."""

    take_profit_pct: float
    """Default take-profit percentage for this risk level."""

    max_open_positions: int
    """Maximum number of concurrent open positions."""


# Fallback defaults — used when the 1Password risk item is absent or a field is
# missing.  make setup creates every risk item with these values so in normal
# operation the vault always wins.  The fallback is purely a safety net for
# installations that have not yet run make setup after this change.
_RISK_LEVEL_CONFIG_DEFAULTS: dict[str, RiskLevelConfig] = {
    "conservative": RiskLevelConfig(
        max_position_size_pct=1.5,
        max_daily_loss_pct=3.0,
        stop_loss_pct=1.5,
        take_profit_pct=2.5,
        max_open_positions=3,
    ),
    "moderate": RiskLevelConfig(
        max_position_size_pct=3.0,
        max_daily_loss_pct=5.0,
        stop_loss_pct=2.5,
        take_profit_pct=4.0,
        max_open_positions=5,
    ),
    "aggressive": RiskLevelConfig(
        max_position_size_pct=5.0,
        max_daily_loss_pct=10.0,
        stop_loss_pct=4.0,
        take_profit_pct=7.0,
        max_open_positions=8,
    ),
}


@dataclass(frozen=True)
class StrategyConfig:
    """Tunable parameters for a single trading strategy, sourced from 1Password."""

    interval: int
    """Polling interval in seconds between trading loop iterations."""

    min_signal_strength: float
    """Minimum signal confidence (0.0–1.0) required to place an order."""

    order_type: str
    """Preferred order type: ``"limit"`` or ``"market"``."""

    stop_loss_pct: float | None = None
    """Stop-loss percentage override for this strategy (None = use risk-level default)."""

    take_profit_pct: float | None = None
    """Take-profit percentage override for this strategy (None = use risk-level default)."""

    # === Strategy-internal calibration parameters ===
    # All optional: None means "use the strategy's own hardcoded default".
    # When set in 1Password, they override the strategy's constructor defaults so
    # users can calibrate without touching code.

    # market_making
    spread_threshold: float | None = None
    """Minimum bid-ask spread (fraction) required to trade (default 0.0005)."""

    inventory_target: float | None = None
    """Target inventory ratio 0–1; 0.5 = balanced long/short (default 0.5)."""

    # momentum / breakout / range_reversion share RSI params
    rsi_period: int | None = None
    """RSI look-back period (default varies by strategy: 14 for momentum/breakout, 7 for range_reversion)."""

    rsi_overbought: float | None = None
    """RSI level above which the market is considered overbought."""

    rsi_oversold: float | None = None
    """RSI level below which the market is considered oversold."""

    # momentum
    fast_period: int | None = None
    """Fast EMA period for momentum strategy (default 12)."""

    slow_period: int | None = None
    """Slow EMA period for momentum strategy (default 26)."""

    # mean_reversion / breakout
    lookback_period: int | None = None
    """Number of price samples defining the recent range/mean (default 20)."""

    # mean_reversion
    num_std_dev: float | None = None
    """Number of standard deviations for Bollinger Bands (default 2.0)."""

    min_deviation: float | None = None
    """Minimum price deviation from mean required to trade (default 0.01 = 1%)."""

    # breakout
    breakout_threshold: float | None = None
    """Fractional distance price must exceed the range to confirm a breakout (default 0.002 = 0.2%)."""

    # range_reversion
    buy_zone: float | None = None
    """Bottom fraction of daily range that triggers buy signals (default 0.20 = bottom 20%)."""

    sell_zone: float | None = None
    """Top fraction of daily range that triggers sell signals (default 0.80 = top 20%)."""

    rsi_confirmation_oversold: float | None = None
    """RSI must be ≤ this level to confirm a buy (range reversion, default 40.0)."""

    rsi_confirmation_overbought: float | None = None
    """RSI must be ≥ this level to confirm a sell (range reversion, default 60.0)."""

    min_range_pct: float | None = None
    """Minimum daily range as a fraction of price; filters illiquid markets (default 0.01 = 1%)."""

    # multi_strategy
    min_consensus: float | None = None
    """Minimum weighted consensus score (0–1) required to produce a signal (default 0.6)."""

    weight_momentum: float | None = None
    """Weight for momentum sub-strategy in multi-strategy voting (default 0.30)."""

    weight_breakout: float | None = None
    """Weight for breakout sub-strategy (default 0.25)."""

    weight_market_making: float | None = None
    """Weight for market-making sub-strategy (default 0.20)."""

    weight_mean_reversion: float | None = None
    """Weight for mean-reversion sub-strategy (default 0.15)."""

    weight_range_reversion: float | None = None
    """Weight for range-reversion sub-strategy (default 0.10)."""


# Fallback defaults — used when the 1Password strategy item is absent or a field is
# missing.  make setup creates every strategy item with these values so in normal
# operation the vault always wins.  The fallback is purely a safety net for
# installations that have not yet run make setup after this change.
_STRATEGY_CONFIG_DEFAULTS: dict[str, StrategyConfig] = {
    "market_making": StrategyConfig(5, 0.3, "limit", 0.5, 0.3),
    "momentum": StrategyConfig(10, 0.6, "market", 2.5, 4.0),
    "breakout": StrategyConfig(5, 0.7, "market", 3.0, 5.0),
    "mean_reversion": StrategyConfig(15, 0.5, "limit", 1.0, 1.5),
    "range_reversion": StrategyConfig(15, 0.5, "limit", 1.0, 1.5),
    "multi_strategy": StrategyConfig(10, 0.55, "limit", None, None),
}


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


def _load_optional_nonneg_float(op, key: str, error_msg: str) -> float | None:
    """Load an optional non-negative float from 1Password (0.0 is allowed).

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
        if val < 0:
            raise ValueError("must be a non-negative number")
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
        self._load_risk_configs(op)
        self._load_strategy_configs(op)

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
        """Load optional capital-limiting, notification, fee, and safety-limit config from 1Password."""
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
        self.backtest_days = (
            _load_optional_int(
                op,
                "BACKTEST_DAYS",
                "Invalid BACKTEST_DAYS in 1Password: must be a positive integer.\n"
                "Set it with: make opconfig-set KEY=BACKTEST_DAYS VALUE=30 ENV=dev",
            )
            or self.backtest_days
        )
        raw_backtest_interval = op.get_optional("BACKTEST_INTERVAL")
        if raw_backtest_interval is not None:
            _valid_intervals = {1, 5, 15, 30, 60, 240, 1440, 2880, 5760, 10080, 20160, 40320}
            try:
                val = int(raw_backtest_interval)
                if val not in _valid_intervals:
                    raise ValueError("not a valid choice")
            except ValueError as e:
                raise ValueError(
                    f"Invalid BACKTEST_INTERVAL in 1Password: '{raw_backtest_interval}' is not valid. "
                    f"Must be one of: {sorted(_valid_intervals)}.\n"
                    "Set it with: make opconfig-set KEY=BACKTEST_INTERVAL VALUE=60 ENV=dev"
                ) from e
            self.backtest_interval = val
        raw_log_level = op.get_optional("LOG_LEVEL")
        if raw_log_level is not None:
            normalized = raw_log_level.upper()
            if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
                raise ValueError(
                    f"Invalid LOG_LEVEL in 1Password: '{raw_log_level}' is not valid. "
                    "Must be one of: DEBUG, INFO, WARNING, ERROR.\n"
                    "Set it with: make opconfig-set KEY=LOG_LEVEL VALUE=INFO ENV=dev"
                )
            self.log_level = normalized
        self.interval = _load_optional_int(
            op,
            "INTERVAL",
            "Invalid INTERVAL in 1Password: must be a positive integer (seconds).\n"
            "Set it with: make opconfig-set KEY=INTERVAL VALUE=30 ENV=dev",
        )

        # Fee rates — can change if Revolut updates its schedule.
        # Default: 0% maker (LIMIT), 0.09% taker (MARKET).
        maker_fee = _load_optional_nonneg_float(
            op,
            "MAKER_FEE_PCT",
            "Invalid MAKER_FEE_PCT in 1Password: must be a non-negative number "
            "(e.g. 0 or 0.0001).\n"
            "Set it with: make opconfig-set KEY=MAKER_FEE_PCT VALUE=0 ENV=dev",
        )
        if maker_fee is not None:
            self.maker_fee_pct = maker_fee

        taker_fee = _load_optional_nonneg_float(
            op,
            "TAKER_FEE_PCT",
            "Invalid TAKER_FEE_PCT in 1Password: must be a non-negative number "
            "(e.g. 0.0009 for 0.09%).\n"
            "Set it with: make opconfig-set KEY=TAKER_FEE_PCT VALUE=0.0009 ENV=dev",
        )
        if taker_fee is not None:
            self.taker_fee_pct = taker_fee

        # Order safety limits — set by users who want tighter or looser absolute caps.
        raw_max_order = op.get_optional("MAX_ORDER_VALUE")
        if raw_max_order is not None:
            try:
                val_f = float(raw_max_order)
                if val_f <= 0:
                    raise ValueError("must be positive")
                self.max_order_value = val_f
            except ValueError as e:
                raise ValueError(
                    f"Invalid MAX_ORDER_VALUE in 1Password: '{raw_max_order}'.\n"
                    "Must be a positive number (e.g. 10000).\n"
                    "Set it with: make opconfig-set KEY=MAX_ORDER_VALUE VALUE=10000 ENV=dev"
                ) from e

        raw_min_order = op.get_optional("MIN_ORDER_VALUE")
        if raw_min_order is not None:
            try:
                val_f = float(raw_min_order)
                if val_f <= 0:
                    raise ValueError("must be positive")
                self.min_order_value = val_f
            except ValueError as e:
                raise ValueError(
                    f"Invalid MIN_ORDER_VALUE in 1Password: '{raw_min_order}'.\n"
                    "Must be a positive number (e.g. 10).\n"
                    "Set it with: make opconfig-set KEY=MIN_ORDER_VALUE VALUE=10 ENV=dev"
                ) from e

    def _load_risk_configs(self, op) -> None:
        """Load per-risk-level parameters from 1Password risk items.

        Each risk level has its own 1Password item (``revolut-trader-risk-{level}``)
        whose fields are loaded into the vault cache with a ``RISK_{LEVEL_UPPER}_``
        prefix.  When a field is absent the hardcoded default from
        ``_RISK_LEVEL_CONFIG_DEFAULTS`` is used so existing installations keep working
        before ``make setup`` is re-run.
        """
        configs: dict[str, RiskLevelConfig] = {}
        for level in RiskLevel:
            name = level.value
            prefix = f"RISK_{name.upper()}"
            defaults = _RISK_LEVEL_CONFIG_DEFAULTS[name]

            # MAX_POSITION_SIZE_PCT
            raw = op.get_optional(f"{prefix}_MAX_POSITION_SIZE_PCT")
            if raw is not None:
                try:
                    max_pos_pct = float(raw)
                    if max_pos_pct <= 0:
                        raise ValueError("must be positive")
                except ValueError as e:
                    raise ValueError(
                        f"Invalid {prefix}_MAX_POSITION_SIZE_PCT in 1Password: {e}.\n"
                        f"Update: revolut-trader-risk-{name} → MAX_POSITION_SIZE_PCT"
                    ) from e
            else:
                max_pos_pct = defaults.max_position_size_pct

            # MAX_DAILY_LOSS_PCT
            raw = op.get_optional(f"{prefix}_MAX_DAILY_LOSS_PCT")
            if raw is not None:
                try:
                    max_loss_pct = float(raw)
                    if max_loss_pct <= 0:
                        raise ValueError("must be positive")
                except ValueError as e:
                    raise ValueError(
                        f"Invalid {prefix}_MAX_DAILY_LOSS_PCT in 1Password: {e}.\n"
                        f"Update: revolut-trader-risk-{name} → MAX_DAILY_LOSS_PCT"
                    ) from e
            else:
                max_loss_pct = defaults.max_daily_loss_pct

            # STOP_LOSS_PCT
            raw = op.get_optional(f"{prefix}_STOP_LOSS_PCT")
            if raw is not None:
                try:
                    stop_loss_pct = float(raw)
                    if stop_loss_pct <= 0:
                        raise ValueError("must be positive")
                except ValueError as e:
                    raise ValueError(
                        f"Invalid {prefix}_STOP_LOSS_PCT in 1Password: {e}.\n"
                        f"Update: revolut-trader-risk-{name} → STOP_LOSS_PCT"
                    ) from e
            else:
                stop_loss_pct = defaults.stop_loss_pct

            # TAKE_PROFIT_PCT
            raw = op.get_optional(f"{prefix}_TAKE_PROFIT_PCT")
            if raw is not None:
                try:
                    take_profit_pct = float(raw)
                    if take_profit_pct <= 0:
                        raise ValueError("must be positive")
                except ValueError as e:
                    raise ValueError(
                        f"Invalid {prefix}_TAKE_PROFIT_PCT in 1Password: {e}.\n"
                        f"Update: revolut-trader-risk-{name} → TAKE_PROFIT_PCT"
                    ) from e
            else:
                take_profit_pct = defaults.take_profit_pct

            # MAX_OPEN_POSITIONS
            raw = op.get_optional(f"{prefix}_MAX_OPEN_POSITIONS")
            if raw is not None:
                try:
                    max_positions = int(raw)
                    if max_positions <= 0:
                        raise ValueError("must be positive")
                except ValueError as e:
                    raise ValueError(
                        f"Invalid {prefix}_MAX_OPEN_POSITIONS in 1Password: {e}.\n"
                        f"Update: revolut-trader-risk-{name} → MAX_OPEN_POSITIONS"
                    ) from e
            else:
                max_positions = defaults.max_open_positions

            configs[name] = RiskLevelConfig(
                max_position_size_pct=max_pos_pct,
                max_daily_loss_pct=max_loss_pct,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                max_open_positions=max_positions,
            )

        self.risk_configs = configs

    def _load_strategy_configs(self, op) -> None:
        """Load per-strategy tuning constants from 1Password strategy items.

        Each strategy has its own 1Password item (``revolut-trader-strategy-{name}``)
        whose fields are loaded into the vault cache with a ``STRATEGY_{NAME_UPPER}_``
        prefix.  When a field is absent the hardcoded default from
        ``_STRATEGY_CONFIG_DEFAULTS`` is used so existing installations keep working
        before ``make setup`` is re-run.

        Internal calibration parameters (RSI periods, EMA windows, thresholds, etc.)
        are also loaded from the same 1Password item.  When absent they are stored as
        ``None`` — the strategy's own constructor defaults apply in that case.
        """
        configs: dict[str, StrategyConfig] = {}
        for strategy in StrategyType:
            name = strategy.value
            prefix = f"STRATEGY_{name.upper()}"
            defaults = _STRATEGY_CONFIG_DEFAULTS[name]

            # INTERVAL
            raw = op.get_optional(f"{prefix}_INTERVAL")
            if raw is not None:
                try:
                    interval = int(raw)
                    if interval <= 0:
                        raise ValueError("must be positive")
                except ValueError as e:
                    raise ValueError(
                        f"Invalid {prefix}_INTERVAL in 1Password: {e}.\n"
                        f"Update: revolut-trader-strategy-{name} → INTERVAL"
                    ) from e
            else:
                interval = defaults.interval

            # MIN_SIGNAL_STRENGTH
            raw = op.get_optional(f"{prefix}_MIN_SIGNAL_STRENGTH")
            if raw is not None:
                try:
                    min_signal = float(raw)
                    if not (0.0 <= min_signal <= 1.0):
                        raise ValueError("must be between 0.0 and 1.0")
                except ValueError as e:
                    raise ValueError(
                        f"Invalid {prefix}_MIN_SIGNAL_STRENGTH in 1Password: {e}.\n"
                        f"Update: revolut-trader-strategy-{name} → MIN_SIGNAL_STRENGTH"
                    ) from e
            else:
                min_signal = defaults.min_signal_strength

            # ORDER_TYPE
            raw = op.get_optional(f"{prefix}_ORDER_TYPE")
            if raw is not None:
                order_type = raw.lower()
                if order_type not in ("limit", "market"):
                    raise ValueError(
                        f"Invalid {prefix}_ORDER_TYPE in 1Password: '{raw}'. "
                        "Must be 'limit' or 'market'.\n"
                        f"Update: revolut-trader-strategy-{name} → ORDER_TYPE"
                    )
            else:
                order_type = defaults.order_type

            # STOP_LOSS_PCT (optional)
            raw = op.get_optional(f"{prefix}_STOP_LOSS_PCT")
            if raw is not None:
                try:
                    stop_loss_pct: float | None = float(raw)
                    if stop_loss_pct <= 0:  # type: ignore[operator]
                        raise ValueError("must be positive")
                except ValueError as e:
                    raise ValueError(
                        f"Invalid {prefix}_STOP_LOSS_PCT in 1Password: {e}.\n"
                        f"Update: revolut-trader-strategy-{name} → STOP_LOSS_PCT"
                    ) from e
            else:
                stop_loss_pct = defaults.stop_loss_pct

            # TAKE_PROFIT_PCT (optional)
            raw = op.get_optional(f"{prefix}_TAKE_PROFIT_PCT")
            if raw is not None:
                try:
                    take_profit_pct: float | None = float(raw)
                    if take_profit_pct <= 0:  # type: ignore[operator]
                        raise ValueError("must be positive")
                except ValueError as e:
                    raise ValueError(
                        f"Invalid {prefix}_TAKE_PROFIT_PCT in 1Password: {e}.\n"
                        f"Update: revolut-trader-strategy-{name} → TAKE_PROFIT_PCT"
                    ) from e
            else:
                take_profit_pct = defaults.take_profit_pct

            # === Internal calibration parameters (all optional, None = use strategy default) ===

            spread_threshold = self._load_strategy_float(
                op, f"{prefix}_SPREAD_THRESHOLD", name, "SPREAD_THRESHOLD", positive=True
            )
            inventory_target = self._load_strategy_float(
                op, f"{prefix}_INVENTORY_TARGET", name, "INVENTORY_TARGET", positive=True
            )
            rsi_period = self._load_strategy_int(op, f"{prefix}_RSI_PERIOD", name, "RSI_PERIOD")
            rsi_overbought = self._load_strategy_float(
                op, f"{prefix}_RSI_OVERBOUGHT", name, "RSI_OVERBOUGHT", positive=True
            )
            rsi_oversold = self._load_strategy_float(
                op, f"{prefix}_RSI_OVERSOLD", name, "RSI_OVERSOLD", positive=True
            )
            fast_period = self._load_strategy_int(op, f"{prefix}_FAST_PERIOD", name, "FAST_PERIOD")
            slow_period = self._load_strategy_int(op, f"{prefix}_SLOW_PERIOD", name, "SLOW_PERIOD")
            lookback_period = self._load_strategy_int(
                op, f"{prefix}_LOOKBACK_PERIOD", name, "LOOKBACK_PERIOD"
            )
            num_std_dev = self._load_strategy_float(
                op, f"{prefix}_NUM_STD_DEV", name, "NUM_STD_DEV", positive=True
            )
            min_deviation = self._load_strategy_float(
                op, f"{prefix}_MIN_DEVIATION", name, "MIN_DEVIATION", positive=True
            )
            breakout_threshold = self._load_strategy_float(
                op, f"{prefix}_BREAKOUT_THRESHOLD", name, "BREAKOUT_THRESHOLD", positive=True
            )

            # buy_zone and sell_zone must be in [0, 1]
            buy_zone = self._load_strategy_zone(op, f"{prefix}_BUY_ZONE", name, "BUY_ZONE")
            sell_zone = self._load_strategy_zone(op, f"{prefix}_SELL_ZONE", name, "SELL_ZONE")

            rsi_confirmation_oversold = self._load_strategy_float(
                op,
                f"{prefix}_RSI_CONFIRMATION_OVERSOLD",
                name,
                "RSI_CONFIRMATION_OVERSOLD",
                positive=True,
            )
            rsi_confirmation_overbought = self._load_strategy_float(
                op,
                f"{prefix}_RSI_CONFIRMATION_OVERBOUGHT",
                name,
                "RSI_CONFIRMATION_OVERBOUGHT",
                positive=True,
            )
            min_range_pct = self._load_strategy_float(
                op, f"{prefix}_MIN_RANGE_PCT", name, "MIN_RANGE_PCT", positive=False
            )
            min_consensus = self._load_strategy_zone(
                op, f"{prefix}_MIN_CONSENSUS", name, "MIN_CONSENSUS"
            )
            weight_momentum = self._load_strategy_float(
                op, f"{prefix}_WEIGHT_MOMENTUM", name, "WEIGHT_MOMENTUM", positive=True
            )
            weight_breakout = self._load_strategy_float(
                op, f"{prefix}_WEIGHT_BREAKOUT", name, "WEIGHT_BREAKOUT", positive=True
            )
            weight_market_making = self._load_strategy_float(
                op, f"{prefix}_WEIGHT_MARKET_MAKING", name, "WEIGHT_MARKET_MAKING", positive=True
            )
            weight_mean_reversion = self._load_strategy_float(
                op, f"{prefix}_WEIGHT_MEAN_REVERSION", name, "WEIGHT_MEAN_REVERSION", positive=True
            )
            weight_range_reversion = self._load_strategy_float(
                op,
                f"{prefix}_WEIGHT_RANGE_REVERSION",
                name,
                "WEIGHT_RANGE_REVERSION",
                positive=True,
            )

            configs[name] = StrategyConfig(
                interval=interval,
                min_signal_strength=min_signal,
                order_type=order_type,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                spread_threshold=spread_threshold,
                inventory_target=inventory_target,
                rsi_period=rsi_period,
                rsi_overbought=rsi_overbought,
                rsi_oversold=rsi_oversold,
                fast_period=fast_period,
                slow_period=slow_period,
                lookback_period=lookback_period,
                num_std_dev=num_std_dev,
                min_deviation=min_deviation,
                breakout_threshold=breakout_threshold,
                buy_zone=buy_zone,
                sell_zone=sell_zone,
                rsi_confirmation_oversold=rsi_confirmation_oversold,
                rsi_confirmation_overbought=rsi_confirmation_overbought,
                min_range_pct=min_range_pct,
                min_consensus=min_consensus,
                weight_momentum=weight_momentum,
                weight_breakout=weight_breakout,
                weight_market_making=weight_market_making,
                weight_mean_reversion=weight_mean_reversion,
                weight_range_reversion=weight_range_reversion,
            )

        self.strategy_configs = configs

    @staticmethod
    def _load_strategy_float(
        op, key: str, strategy_name: str, field_name: str, positive: bool = True
    ) -> float | None:
        """Load an optional float from a strategy item in 1Password.

        Args:
            op:            The onepassword module.
            key:           Full vault key (e.g. ``STRATEGY_MOMENTUM_RSI_OVERBOUGHT``).
            strategy_name: Strategy name for error messages (e.g. ``"momentum"``).
            field_name:    Field name for error messages (e.g. ``"RSI_OVERBOUGHT"``).
            positive:      If True, value must be > 0.  If False, value must be >= 0.

        Returns:
            The float value, or None if absent.
        """
        raw = op.get_optional(key)
        if raw is None:
            return None
        try:
            val = float(raw)
            if positive and val <= 0:
                raise ValueError("must be positive")
            if not positive and val < 0:
                raise ValueError("must be non-negative")
            return val
        except ValueError as e:
            raise ValueError(
                f"Invalid {key} in 1Password: {e}.\n"
                f"Update: revolut-trader-strategy-{strategy_name} → {field_name}"
            ) from e

    @staticmethod
    def _load_strategy_int(op, key: str, strategy_name: str, field_name: str) -> int | None:
        """Load an optional positive integer from a strategy item in 1Password.

        Args:
            op:            The onepassword module.
            key:           Full vault key.
            strategy_name: Strategy name for error messages.
            field_name:    Field name for error messages.

        Returns:
            The int value, or None if absent.
        """
        raw = op.get_optional(key)
        if raw is None:
            return None
        try:
            val = int(raw)
            if val <= 0:
                raise ValueError("must be positive")
            return val
        except ValueError as e:
            raise ValueError(
                f"Invalid {key} in 1Password: {e}.\n"
                f"Update: revolut-trader-strategy-{strategy_name} → {field_name}"
            ) from e

    @staticmethod
    def _load_strategy_zone(op, key: str, strategy_name: str, field_name: str) -> float | None:
        """Load an optional float that must be in [0.0, 1.0].

        Args:
            op:            The onepassword module.
            key:           Full vault key.
            strategy_name: Strategy name for error messages.
            field_name:    Field name for error messages.

        Returns:
            The float value in [0.0, 1.0], or None if absent.
        """
        raw = op.get_optional(key)
        if raw is None:
            return None
        try:
            val = float(raw)
            if not (0.0 <= val <= 1.0):
                raise ValueError("must be between 0.0 and 1.0")
            return val
        except ValueError as e:
            raise ValueError(
                f"Invalid {key} in 1Password: {e}.\n"
                f"Update: revolut-trader-strategy-{strategy_name} → {field_name}"
            ) from e

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

    # Trading loop interval in seconds (optional).
    # When set, overrides the strategy-dependent default interval for every run.
    # None means "use the strategy default" (market_making/breakout=5s, momentum=10s, etc.).
    interval: int | None = Field(default=None)

    # Backtest defaults — populated from 1Password; CLI flags override per-run.
    backtest_days: int = Field(default=30)
    backtest_interval: int = Field(default=60)

    # Per-risk-level parameters — populated from 1Password risk items
    # (revolut-trader-risk-{level}) in _load_risk_configs.
    risk_configs: dict[str, RiskLevelConfig] = Field(default_factory=dict)

    # Per-strategy tuning constants — populated from 1Password strategy items
    # (revolut-trader-strategy-{name}) in _load_strategy_configs.
    strategy_configs: dict[str, StrategyConfig] = Field(default_factory=dict)

    # Fee rates — loaded from 1Password config item; default to published Revolut X schedule.
    # LIMIT orders (maker): 0% — no fee when providing liquidity.
    # MARKET orders (taker): 0.09% — fee charged when taking liquidity.
    maker_fee_pct: float = Field(default=0.0)
    taker_fee_pct: float = Field(default=0.0009)

    # Order safety limits — hard caps applied in validate_order_sanity().
    # max_order_value: absolute maximum order size in base currency (default €10,000).
    # min_order_value: minimum order size to prevent dust orders (default €10).
    max_order_value: float = Field(default=10000.0)
    min_order_value: float = Field(default=10.0)

    # Telegram notifications (optional — both must be set to enable).
    # Store in 1Password with: make ops ENV=<env>                                  (bot token, concealed)
    #                          make opconfig-set KEY=TELEGRAM_CHAT_ID VALUE=<id> ENV=<env>
    telegram_bot_token: str | None = Field(default=None)
    telegram_chat_id: str | None = Field(default=None)


settings = Settings()
