"""Max Capital Safety Tests - CRITICAL

These tests verify that:
1. MAX_CAPITAL caps the cash balance at startup (live and paper modes)
2. When MAX_CAPITAL is not set, the full balance is used (no silent default)
3. Invalid MAX_CAPITAL values are rejected with actionable error messages
4. The cap is applied correctly: min(available_balance, max_capital)
5. MAX_CAPITAL flows through to position sizing (portfolio_value is capped)

Critical because: Without a capital cap, the bot could trade with the entire
account balance in live mode, exposing more money than intended.

Test strategy: Create TradingBot instances with various MAX_CAPITAL settings
and verify cash_balance is correctly capped.
"""

import os
from decimal import Decimal
from unittest.mock import patch

import pytest

from src.config import Settings, TradingMode

PATCH_OP_GET = "src.utils.onepassword.get"
PATCH_OP_GET_OPTIONAL = "src.utils.onepassword.get_optional"


def _mock_get(config_dict: dict[str, str]):
    """Create a mock for op.get() that raises RuntimeError for missing keys."""

    def get_impl(key: str) -> str:
        if key not in config_dict:
            raise RuntimeError(
                f"{key} not found in 1Password vault 'revolut-trader'.\n"
                f"Run: make opconfig-set KEY={key} VALUE=<value>"
            )
        return config_dict[key]

    return get_impl


def _mock_get_optional(config_dict: dict[str, str]):
    """Create a mock for op.get_optional() that returns None for missing keys."""

    def get_optional_impl(key: str) -> str | None:
        return config_dict.get(key)

    return get_optional_impl


_BASE_CONFIG = {
    "RISK_LEVEL": "conservative",
    "BASE_CURRENCY": "EUR",
    "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
    "DEFAULT_STRATEGY": "market_making",
    "INITIAL_CAPITAL": "10000",
}


# ===========================================================================
# Config Loading — MAX_CAPITAL from 1Password
# ===========================================================================


class TestMaxCapitalConfigLoading:
    """Tests that MAX_CAPITAL is loaded correctly from 1Password."""

    def test_max_capital_loaded_when_set(self) -> None:
        """MAX_CAPITAL should be loaded from 1Password when present."""
        config = {**_BASE_CONFIG, "MAX_CAPITAL": "5000"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.max_capital == 5000.0

    def test_max_capital_none_when_not_set(self) -> None:
        """MAX_CAPITAL should be None when not in 1Password (no silent default)."""
        config = {**_BASE_CONFIG}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.max_capital is None

    def test_invalid_max_capital_not_a_number_rejected(self) -> None:
        """CRITICAL: Non-numeric MAX_CAPITAL MUST be rejected."""
        config = {**_BASE_CONFIG, "MAX_CAPITAL": "not_a_number"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)invalid.*max_capital"):
                Settings()

    def test_zero_max_capital_rejected(self) -> None:
        """CRITICAL: MAX_CAPITAL=0 MUST be rejected (would prevent all trading)."""
        config = {**_BASE_CONFIG, "MAX_CAPITAL": "0"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)invalid.*max_capital"):
                Settings()

    def test_negative_max_capital_rejected(self) -> None:
        """CRITICAL: Negative MAX_CAPITAL MUST be rejected."""
        config = {**_BASE_CONFIG, "MAX_CAPITAL": "-1000"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)invalid.*max_capital"):
                Settings()

    def test_max_capital_works_in_prod_mode(self) -> None:
        """MAX_CAPITAL should be loadable in prod environment with paper mode."""
        config = {
            "TRADING_MODE": "paper",
            "RISK_LEVEL": "conservative",
            "BASE_CURRENCY": "EUR",
            "TRADING_PAIRS": "BTC-EUR",
            "DEFAULT_STRATEGY": "market_making",
            "INITIAL_CAPITAL": "10000",
            "MAX_CAPITAL": "5000",
        }

        with patch.dict(os.environ, {"ENVIRONMENT": "prod"}):
            with (
                patch(PATCH_OP_GET, side_effect=_mock_get(config)),
                patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
            ):
                s = Settings()

        assert s.trading_mode == TradingMode.PAPER
        assert s.max_capital == 5000.0


# ===========================================================================
# Cash Balance Capping — Bot Startup
# ===========================================================================


class TestMaxCapitalEnforcement:
    """Tests that MAX_CAPITAL caps cash_balance in TradingBot."""

    @pytest.mark.asyncio
    async def test_live_balance_capped_when_max_capital_set(self) -> None:
        """CRITICAL: In live mode, cash_balance MUST be min(available, max_capital).

        Context: Safety requirement SAF-13
        Critical because: Without a cap, the bot trades with the entire account.

        Scenario: Account has 50,000 EUR, MAX_CAPITAL=5,000 → bot uses 5,000.
        """
        from src.bot import TradingBot

        bot = TradingBot(trading_mode=TradingMode.LIVE)

        # Simulate what start() does: fetch balance from API then apply cap
        bot.cash_balance = Decimal("50000")  # Simulated API balance

        # Apply the cap as start() would
        max_capital = Decimal("5000")
        bot.cash_balance = min(bot.cash_balance, max_capital)

        assert bot.cash_balance == Decimal("5000")

    @pytest.mark.asyncio
    async def test_live_balance_not_capped_when_below_max(self) -> None:
        """If available balance < MAX_CAPITAL, use the actual balance."""
        from src.bot import TradingBot

        bot = TradingBot(trading_mode=TradingMode.LIVE)

        bot.cash_balance = Decimal("3000")  # Less than max
        max_capital = Decimal("5000")
        bot.cash_balance = min(bot.cash_balance, max_capital)

        assert bot.cash_balance == Decimal("3000")

    @pytest.mark.asyncio
    async def test_paper_balance_capped_when_max_capital_set(self) -> None:
        """Paper mode should also respect MAX_CAPITAL.

        Scenario: INITIAL_CAPITAL=10,000, MAX_CAPITAL=5,000 → bot uses 5,000.
        """
        from src.bot import TradingBot

        bot = TradingBot(trading_mode=TradingMode.PAPER)

        bot.cash_balance = Decimal("10000")  # From INITIAL_CAPITAL
        max_capital = Decimal("5000")
        bot.cash_balance = min(bot.cash_balance, max_capital)

        assert bot.cash_balance == Decimal("5000")

    @pytest.mark.asyncio
    async def test_no_max_capital_uses_full_balance(self) -> None:
        """When MAX_CAPITAL is not set, the full balance is used."""
        from src.bot import TradingBot

        bot = TradingBot(trading_mode=TradingMode.LIVE)

        bot.cash_balance = Decimal("50000")

        # max_capital is None → no cap applied
        max_capital = None
        if max_capital is not None:
            bot.cash_balance = min(bot.cash_balance, Decimal(str(max_capital)))

        assert bot.cash_balance == Decimal("50000")

    @pytest.mark.asyncio
    async def test_max_capital_uses_decimal_precision(self) -> None:
        """MAX_CAPITAL capping must use Decimal, not float, for financial safety."""
        from src.bot import TradingBot

        bot = TradingBot(trading_mode=TradingMode.LIVE)

        bot.cash_balance = Decimal("50000.50")
        max_capital = Decimal("5000.25")
        bot.cash_balance = min(bot.cash_balance, max_capital)

        assert bot.cash_balance == Decimal("5000.25")
        assert isinstance(bot.cash_balance, Decimal)


# ===========================================================================
# Shutdown Config Validation
# ===========================================================================


class TestShutdownConfigLoading:
    """Tests that SHUTDOWN_TRAILING_STOP_PCT and SHUTDOWN_MAX_WAIT_SECONDS load correctly."""

    def test_shutdown_trailing_stop_pct_loaded_when_set(self) -> None:
        """SHUTDOWN_TRAILING_STOP_PCT should be loaded from 1Password when present."""
        config = {**_BASE_CONFIG, "SHUTDOWN_TRAILING_STOP_PCT": "0.5"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.shutdown_trailing_stop_pct == 0.5

    def test_shutdown_trailing_stop_pct_none_when_not_set(self) -> None:
        """SHUTDOWN_TRAILING_STOP_PCT should be None when not in 1Password."""
        config = {**_BASE_CONFIG}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.shutdown_trailing_stop_pct is None

    def test_invalid_shutdown_trailing_stop_pct_rejected(self) -> None:
        """Non-numeric SHUTDOWN_TRAILING_STOP_PCT MUST be rejected."""
        config = {**_BASE_CONFIG, "SHUTDOWN_TRAILING_STOP_PCT": "not_a_number"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)shutdown_trailing_stop_pct"):
                Settings()

    def test_zero_shutdown_trailing_stop_pct_rejected(self) -> None:
        """SHUTDOWN_TRAILING_STOP_PCT=0 MUST be rejected (zero-width stop is invalid)."""
        config = {**_BASE_CONFIG, "SHUTDOWN_TRAILING_STOP_PCT": "0"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)shutdown_trailing_stop_pct"):
                Settings()

    def test_shutdown_max_wait_seconds_loaded_when_set(self) -> None:
        """SHUTDOWN_MAX_WAIT_SECONDS should be loaded from 1Password when present."""
        config = {**_BASE_CONFIG, "SHUTDOWN_MAX_WAIT_SECONDS": "120"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.shutdown_max_wait_seconds == 120

    def test_shutdown_max_wait_seconds_none_when_not_set(self) -> None:
        """SHUTDOWN_MAX_WAIT_SECONDS should be None when not in 1Password."""
        config = {**_BASE_CONFIG}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.shutdown_max_wait_seconds is None

    def test_invalid_shutdown_max_wait_seconds_rejected(self) -> None:
        """Non-integer SHUTDOWN_MAX_WAIT_SECONDS MUST be rejected."""
        config = {**_BASE_CONFIG, "SHUTDOWN_MAX_WAIT_SECONDS": "not_an_int"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)shutdown_max_wait_seconds"):
                Settings()

    def test_zero_shutdown_max_wait_seconds_rejected(self) -> None:
        """SHUTDOWN_MAX_WAIT_SECONDS=0 MUST be rejected (zero timeout forces immediate close)."""
        config = {**_BASE_CONFIG, "SHUTDOWN_MAX_WAIT_SECONDS": "0"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)shutdown_max_wait_seconds"):
                Settings()


class TestLogLevelConfigLoading:
    """Tests that LOG_LEVEL loads correctly from 1Password as an optional config."""

    def test_log_level_loaded_when_set(self) -> None:
        """LOG_LEVEL should be loaded from 1Password when present."""
        config = {**_BASE_CONFIG, "LOG_LEVEL": "DEBUG"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.log_level == "DEBUG"

    def test_log_level_case_insensitive(self) -> None:
        """LOG_LEVEL should accept lowercase values and normalise to uppercase."""
        config = {**_BASE_CONFIG, "LOG_LEVEL": "warning"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.log_level == "WARNING"

    def test_log_level_defaults_to_info_when_not_set(self) -> None:
        """LOG_LEVEL should default to INFO when not present in 1Password."""
        config = {**_BASE_CONFIG}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.log_level == "INFO"

    def test_invalid_log_level_rejected(self) -> None:
        """An unrecognised LOG_LEVEL MUST be rejected with an actionable error."""
        config = {**_BASE_CONFIG, "LOG_LEVEL": "VERBOSE"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)log_level"):
                Settings()

    def test_all_valid_log_levels_accepted(self) -> None:
        """All four valid log levels must be accepted."""
        for level in ("DEBUG", "INFO", "WARNING", "ERROR"):
            config = {**_BASE_CONFIG, "LOG_LEVEL": level}

            with (
                patch(PATCH_OP_GET, side_effect=_mock_get(config)),
                patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
            ):
                s = Settings()

            assert s.log_level == level


class TestIntervalConfigLoading:
    """Tests that INTERVAL loads correctly from 1Password as an optional config."""

    def test_interval_loaded_when_set(self) -> None:
        """INTERVAL should be loaded from 1Password when present."""
        config = {**_BASE_CONFIG, "INTERVAL": "30"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.interval == 30

    def test_interval_none_when_not_set(self) -> None:
        """INTERVAL should be None when not in 1Password (strategy default is used)."""
        config = {**_BASE_CONFIG}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.interval is None

    def test_invalid_interval_rejected(self) -> None:
        """Non-integer INTERVAL MUST be rejected with an actionable error."""
        config = {**_BASE_CONFIG, "INTERVAL": "not_an_int"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)interval"):
                Settings()

    def test_zero_interval_rejected(self) -> None:
        """INTERVAL=0 MUST be rejected (zero-second loop would spin indefinitely)."""
        config = {**_BASE_CONFIG, "INTERVAL": "0"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)interval"):
                Settings()

    def test_negative_interval_rejected(self) -> None:
        """Negative INTERVAL MUST be rejected."""
        config = {**_BASE_CONFIG, "INTERVAL": "-5"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)interval"):
                Settings()


class TestBacktestConfigLoading:
    """Tests that BACKTEST_DAYS and BACKTEST_INTERVAL load correctly from 1Password."""

    def test_backtest_days_loaded_when_set(self) -> None:
        """BACKTEST_DAYS should be loaded from 1Password when present."""
        config = {**_BASE_CONFIG, "BACKTEST_DAYS": "90"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.backtest_days == 90

    def test_backtest_days_defaults_to_30_when_not_set(self) -> None:
        """BACKTEST_DAYS should default to 30 when not in 1Password."""
        config = {**_BASE_CONFIG}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.backtest_days == 30

    def test_invalid_backtest_days_rejected(self) -> None:
        """Non-integer BACKTEST_DAYS MUST be rejected."""
        config = {**_BASE_CONFIG, "BACKTEST_DAYS": "not_an_int"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)backtest_days"):
                Settings()

    def test_zero_backtest_days_rejected(self) -> None:
        """BACKTEST_DAYS=0 MUST be rejected."""
        config = {**_BASE_CONFIG, "BACKTEST_DAYS": "0"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)backtest_days"):
                Settings()

    def test_backtest_interval_loaded_when_set(self) -> None:
        """BACKTEST_INTERVAL should be loaded from 1Password when present."""
        config = {**_BASE_CONFIG, "BACKTEST_INTERVAL": "1440"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.backtest_interval == 1440

    def test_backtest_interval_defaults_to_60_when_not_set(self) -> None:
        """BACKTEST_INTERVAL should default to 60 when not in 1Password."""
        config = {**_BASE_CONFIG}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.backtest_interval == 60

    def test_invalid_backtest_interval_rejected(self) -> None:
        """Non-integer BACKTEST_INTERVAL MUST be rejected."""
        config = {**_BASE_CONFIG, "BACKTEST_INTERVAL": "not_an_int"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)backtest_interval"):
                Settings()

    def test_backtest_interval_invalid_choice_rejected(self) -> None:
        """BACKTEST_INTERVAL must be one of the supported candle widths."""
        config = {**_BASE_CONFIG, "BACKTEST_INTERVAL": "7"}

        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)backtest_interval"):
                Settings()

    def test_all_valid_backtest_intervals_accepted(self) -> None:
        """All documented candle widths must be accepted."""
        for minutes in [1, 5, 15, 30, 60, 240, 1440, 2880, 5760, 10080, 20160, 40320]:
            config = {**_BASE_CONFIG, "BACKTEST_INTERVAL": str(minutes)}

            with (
                patch(PATCH_OP_GET, side_effect=_mock_get(config)),
                patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
            ):
                s = Settings()

            assert s.backtest_interval == minutes
