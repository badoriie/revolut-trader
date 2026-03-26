"""Risk Manager Calculation Tests - CRITICAL

These tests verify mathematical correctness of:
1. Position size calculations
2. Stop loss calculations
3. Take profit calculations
4. Risk parameters by level

Critical because: Wrong calculations = wrong position sizes = potential losses

Test strategy: Use exact Decimal arithmetic to verify calculations match
expected values. Test edge cases and boundary conditions.
"""

from decimal import Decimal

from src.config import RiskLevel
from src.models.domain import OrderSide
from src.risk_management.risk_manager import RiskManager


class TestPositionSizeCalculation:
    """Tests that verify position size is calculated correctly."""

    def test_position_size_respects_portfolio_percentage(
        self, conservative_risk_manager, medium_portfolio_value
    ):
        """CRITICAL: Position size MUST respect max portfolio percentage.

        Context: Risk management requirement RM-01
        Critical because: Core risk control mechanism

        Scenario:
        - Portfolio = 10,000 EUR
        - Conservative max position = 1.5% = 150 EUR
        - BTC price = 50,000 EUR
        - Expected quantity = 150 / 50,000 = 0.003 BTC
        """
        price = Decimal("50000")
        signal_strength = 1.0  # Full strength

        quantity = conservative_risk_manager.calculate_position_size(
            portfolio_value=medium_portfolio_value,
            price=price,
            signal_strength=signal_strength,
        )

        # Conservative max = 1.5% of 10,000 = 150 EUR
        # 150 EUR / 50,000 EUR per BTC = 0.003 BTC
        expected = Decimal("0.003")

        # Allow small rounding difference due to Decimal quantization
        assert abs(quantity - expected) < Decimal("0.0000001")

    def test_position_size_with_moderate_risk(self, medium_portfolio_value):
        """Moderate risk should allow larger positions."""
        moderate_rm = RiskManager(RiskLevel.MODERATE)
        price = Decimal("50000")

        quantity = moderate_rm.calculate_position_size(
            portfolio_value=medium_portfolio_value,
            price=price,
            signal_strength=1.0,
        )

        # Moderate max = 3% of 10,000 = 300 EUR
        # 300 EUR / 50,000 EUR per BTC = 0.006 BTC
        expected = Decimal("0.006")

        assert abs(quantity - expected) < Decimal("0.0000001")

    def test_position_size_with_aggressive_risk(self, medium_portfolio_value):
        """Aggressive risk should allow largest positions."""
        aggressive_rm = RiskManager(RiskLevel.AGGRESSIVE)
        price = Decimal("50000")

        quantity = aggressive_rm.calculate_position_size(
            portfolio_value=medium_portfolio_value,
            price=price,
            signal_strength=1.0,
        )

        # Aggressive max = 5% of 10,000 = 500 EUR
        # 500 EUR / 50,000 EUR per BTC = 0.01 BTC
        expected = Decimal("0.01")

        assert abs(quantity - expected) < Decimal("0.0000001")

    def test_position_size_with_weak_signal(
        self, conservative_risk_manager, medium_portfolio_value
    ):
        """Weak signal should result in smaller position."""
        price = Decimal("50000")
        signal_strength = 0.5  # 50% strength

        quantity = conservative_risk_manager.calculate_position_size(
            portfolio_value=medium_portfolio_value,
            price=price,
            signal_strength=signal_strength,
        )

        # Conservative max = 1.5% of 10,000 = 150 EUR
        # With 50% signal: 150 * 0.5 = 75 EUR
        # 75 EUR / 50,000 EUR per BTC = 0.0015 BTC
        expected = Decimal("0.0015")

        assert abs(quantity - expected) < Decimal("0.0000001")

    def test_position_size_with_small_portfolio(self, small_portfolio_value):
        """Position sizing should work with small portfolios."""
        conservative_rm = RiskManager(RiskLevel.CONSERVATIVE)
        price = Decimal("50000")

        quantity = conservative_rm.calculate_position_size(
            portfolio_value=small_portfolio_value,  # 1,000 EUR
            price=price,
            signal_strength=1.0,
        )

        # Conservative max = 1.5% of 1,000 = 15 EUR
        # 15 EUR / 50,000 EUR per BTC = 0.0003 BTC
        expected = Decimal("0.0003")

        assert abs(quantity - expected) < Decimal("0.0000001")


class TestStopLossCalculation:
    """Tests that verify stop loss calculations are correct."""

    def test_stop_loss_buy_below_entry(self, conservative_risk_manager):
        """CRITICAL: Stop loss for BUY orders MUST be below entry price.

        Context: Risk management requirement RM-02
        Critical because: Wrong stop loss = unexpected losses

        Scenario:
        - Entry price = 50,000 EUR
        - Stop loss = 1.5% (conservative)
        - Expected = 50,000 * (1 - 0.015) = 49,250 EUR
        """
        entry_price = Decimal("50000")

        stop_loss = conservative_risk_manager.calculate_stop_loss(
            entry_price=entry_price,
            side=OrderSide.BUY,
        )

        # Conservative stop loss = 1.5%
        # 50,000 * (1 - 0.015) = 50,000 * 0.985 = 49,250
        expected = Decimal("49250.00")

        assert stop_loss == expected

    def test_stop_loss_sell_above_entry(self, conservative_risk_manager):
        """CRITICAL: Stop loss for SELL orders MUST be above entry price.

        Context: Risk management requirement RM-03
        Critical because: Protects short positions

        Scenario:
        - Entry price = 50,000 EUR
        - Stop loss = 1.5% (conservative)
        - Expected = 50,000 * (1 + 0.015) = 50,750 EUR
        """
        entry_price = Decimal("50000")

        stop_loss = conservative_risk_manager.calculate_stop_loss(
            entry_price=entry_price,
            side=OrderSide.SELL,
        )

        # For SELL, stop loss is above entry
        # 50,000 * (1 + 0.015) = 50,000 * 1.015 = 50,750
        expected = Decimal("50750.00")

        assert stop_loss == expected

    def test_stop_loss_with_custom_percentage(self, conservative_risk_manager):
        """Stop loss should accept custom percentage."""
        entry_price = Decimal("50000")
        custom_pct = 5.0  # 5% stop loss

        stop_loss = conservative_risk_manager.calculate_stop_loss(
            entry_price=entry_price,
            side=OrderSide.BUY,
            custom_pct=custom_pct,
        )

        # 50,000 * (1 - 0.05) = 47,500
        expected = Decimal("47500.00")

        assert stop_loss == expected

    def test_stop_loss_moderate_risk(self):
        """Moderate risk should have wider stop loss."""
        moderate_rm = RiskManager(RiskLevel.MODERATE)
        entry_price = Decimal("50000")

        stop_loss = moderate_rm.calculate_stop_loss(
            entry_price=entry_price,
            side=OrderSide.BUY,
        )

        # Moderate stop loss = 2.5%
        # 50,000 * (1 - 0.025) = 48,750
        expected = Decimal("48750.00")

        assert stop_loss == expected

    def test_stop_loss_aggressive_risk(self):
        """Aggressive risk should have widest stop loss."""
        aggressive_rm = RiskManager(RiskLevel.AGGRESSIVE)
        entry_price = Decimal("50000")

        stop_loss = aggressive_rm.calculate_stop_loss(
            entry_price=entry_price,
            side=OrderSide.BUY,
        )

        # Aggressive stop loss = 4%
        # 50,000 * (1 - 0.04) = 48,000
        expected = Decimal("48000.00")

        assert stop_loss == expected


class TestTakeProfitCalculation:
    """Tests that verify take profit calculations are correct."""

    def test_take_profit_buy_above_entry(self, conservative_risk_manager):
        """CRITICAL: Take profit for BUY orders MUST be above entry price.

        Context: Risk management requirement RM-04
        Critical because: Defines profit target

        Scenario:
        - Entry price = 50,000 EUR
        - Take profit = 2.5% (conservative)
        - Expected = 50,000 * (1 + 0.025) = 51,250 EUR
        """
        entry_price = Decimal("50000")

        take_profit = conservative_risk_manager.calculate_take_profit(
            entry_price=entry_price,
            side=OrderSide.BUY,
        )

        # Conservative take profit = 2.5%
        # 50,000 * (1 + 0.025) = 51,250
        expected = Decimal("51250.00")

        assert take_profit == expected

    def test_take_profit_sell_below_entry(self, conservative_risk_manager):
        """CRITICAL: Take profit for SELL orders MUST be below entry price.

        Context: Risk management requirement RM-05
        Critical because: Profit target for short positions

        Scenario:
        - Entry price = 50,000 EUR
        - Take profit = 2.5% (conservative)
        - Expected = 50,000 * (1 - 0.025) = 48,750 EUR
        """
        entry_price = Decimal("50000")

        take_profit = conservative_risk_manager.calculate_take_profit(
            entry_price=entry_price,
            side=OrderSide.SELL,
        )

        # For SELL, take profit is below entry
        # 50,000 * (1 - 0.025) = 48,750
        expected = Decimal("48750.00")

        assert take_profit == expected

    def test_take_profit_with_custom_percentage(self, conservative_risk_manager):
        """Take profit should accept custom percentage."""
        entry_price = Decimal("50000")
        custom_pct = 10.0  # 10% take profit

        take_profit = conservative_risk_manager.calculate_take_profit(
            entry_price=entry_price,
            side=OrderSide.BUY,
            custom_pct=custom_pct,
        )

        # 50,000 * (1 + 0.10) = 55,000
        expected = Decimal("55000.00")

        assert take_profit == expected

    def test_take_profit_moderate_risk(self):
        """Moderate risk should have higher take profit target."""
        moderate_rm = RiskManager(RiskLevel.MODERATE)
        entry_price = Decimal("50000")

        take_profit = moderate_rm.calculate_take_profit(
            entry_price=entry_price,
            side=OrderSide.BUY,
        )

        # Moderate take profit = 4%
        # 50,000 * (1 + 0.04) = 52,000
        expected = Decimal("52000.00")

        assert take_profit == expected

    def test_take_profit_aggressive_risk(self):
        """Aggressive risk should have highest take profit target."""
        aggressive_rm = RiskManager(RiskLevel.AGGRESSIVE)
        entry_price = Decimal("50000")

        take_profit = aggressive_rm.calculate_take_profit(
            entry_price=entry_price,
            side=OrderSide.BUY,
        )

        # Aggressive take profit = 7%
        # 50,000 * (1 + 0.07) = 53,500
        expected = Decimal("53500.00")

        assert take_profit == expected


class TestRiskParameters:
    """Tests that verify risk parameters are correct for each level."""

    def test_conservative_risk_parameters(self):
        """Conservative risk level should have most restrictive parameters."""
        rm = RiskManager(RiskLevel.CONSERVATIVE)
        params = rm.risk_params

        assert params["max_position_size_pct"] == 1.5
        assert params["max_daily_loss_pct"] == 3.0
        assert params["stop_loss_pct"] == 1.5
        assert params["take_profit_pct"] == 2.5
        assert params["max_open_positions"] == 3

    def test_moderate_risk_parameters(self):
        """Moderate risk level should have balanced parameters."""
        rm = RiskManager(RiskLevel.MODERATE)
        params = rm.risk_params

        assert params["max_position_size_pct"] == 3.0
        assert params["max_daily_loss_pct"] == 5.0
        assert params["stop_loss_pct"] == 2.5
        assert params["take_profit_pct"] == 4.0
        assert params["max_open_positions"] == 5

    def test_aggressive_risk_parameters(self):
        """Aggressive risk level should have least restrictive parameters."""
        rm = RiskManager(RiskLevel.AGGRESSIVE)
        params = rm.risk_params

        assert params["max_position_size_pct"] == 5.0
        assert params["max_daily_loss_pct"] == 10.0
        assert params["stop_loss_pct"] == 4.0
        assert params["take_profit_pct"] == 7.0
        assert params["max_open_positions"] == 8

    def test_risk_parameters_increase_with_level(self):
        """Risk parameters should increase from conservative to aggressive."""
        conservative = RiskManager(RiskLevel.CONSERVATIVE).get_risk_parameters()
        moderate = RiskManager(RiskLevel.MODERATE).get_risk_parameters()
        aggressive = RiskManager(RiskLevel.AGGRESSIVE).get_risk_parameters()

        # All parameters should increase
        assert conservative["max_position_size_pct"] < moderate["max_position_size_pct"]
        assert moderate["max_position_size_pct"] < aggressive["max_position_size_pct"]

        assert conservative["max_daily_loss_pct"] < moderate["max_daily_loss_pct"]
        assert moderate["max_daily_loss_pct"] < aggressive["max_daily_loss_pct"]

        assert conservative["max_open_positions"] < moderate["max_open_positions"]
        assert moderate["max_open_positions"] < aggressive["max_open_positions"]


class TestPositionShouldClose:
    """Tests that verify Position.should_close() triggers correctly for both sides.

    Critical because wrong stop/take-profit logic = no protection on short positions.
    """

    def test_buy_stop_loss_triggers_when_price_falls_to_stop(self):
        """CRITICAL: BUY stop loss MUST trigger when price drops to stop level.

        Context: Risk requirement RM-06
        Scenario: Bought BTC at 50,000 EUR, stop loss at 49,000 EUR.
        When price hits 49,000 EUR the position must close.
        """
        from src.models.domain import Position

        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("49000"),
            stop_loss=Decimal("49000"),
        )
        should_close, reason = position.should_close()
        assert should_close is True
        assert reason == "stop_loss"

    def test_buy_take_profit_triggers_when_price_rises_to_target(self):
        """CRITICAL: BUY take profit MUST trigger when price reaches target.

        Scenario: Bought BTC at 50,000 EUR, take profit at 51,500 EUR.
        When price hits 51,500 EUR the position must close.
        """
        from src.models.domain import Position

        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("51500"),
            take_profit=Decimal("51500"),
        )
        should_close, reason = position.should_close()
        assert should_close is True
        assert reason == "take_profit"

    def test_sell_stop_loss_triggers_when_price_rises_to_stop(self):
        """CRITICAL: SELL stop loss MUST trigger when price rises to stop level.

        Context: Risk requirement RM-07
        Critical because: For short positions the loss side is UP, not down.

        Scenario: Sold BTC at 50,000 EUR (short), stop loss at 51,000 EUR.
        When price rises to 51,000 EUR, the loss must be capped — close position.
        """
        from src.models.domain import Position

        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.SELL,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("51000"),
            stop_loss=Decimal("51000"),
        )
        should_close, reason = position.should_close()
        assert should_close is True
        assert reason == "stop_loss"

    def test_sell_take_profit_triggers_when_price_falls_to_target(self):
        """CRITICAL: SELL take profit MUST trigger when price falls to target.

        Context: Risk requirement RM-08
        Critical because: For short positions profit is captured when price falls.

        Scenario: Sold BTC at 50,000 EUR, take profit at 48,500 EUR.
        When price falls to 48,500 EUR the profit must be locked in.
        """
        from src.models.domain import Position

        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.SELL,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("48500"),
            take_profit=Decimal("48500"),
        )
        should_close, reason = position.should_close()
        assert should_close is True
        assert reason == "take_profit"

    def test_sell_no_close_when_price_between_levels(self):
        """SELL position should stay open when price is between stop and target."""
        from src.models.domain import Position

        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.SELL,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("49500"),  # Between target (48500) and stop (51000)
            stop_loss=Decimal("51000"),
            take_profit=Decimal("48500"),
        )
        should_close, reason = position.should_close()
        assert should_close is False
        assert reason == ""

    def test_buy_no_close_when_price_between_levels(self):
        """BUY position should stay open when price is between stop and target."""
        from src.models.domain import Position

        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50200"),  # Between stop (49000) and target (51500)
            stop_loss=Decimal("49000"),
            take_profit=Decimal("51500"),
        )
        should_close, reason = position.should_close()
        assert should_close is False
        assert reason == ""


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_zero_signal_strength_gives_zero_position(
        self, conservative_risk_manager, medium_portfolio_value
    ):
        """Signal strength of 0 should give position size of 0."""
        price = Decimal("50000")
        signal_strength = 0.0

        quantity = conservative_risk_manager.calculate_position_size(
            portfolio_value=medium_portfolio_value,
            price=price,
            signal_strength=signal_strength,
        )

        assert quantity == Decimal("0")

    def test_very_high_price_gives_small_quantity(
        self, conservative_risk_manager, medium_portfolio_value
    ):
        """Very expensive assets should result in small quantities."""
        price = Decimal("1000000")  # 1 million EUR per unit

        quantity = conservative_risk_manager.calculate_position_size(
            portfolio_value=medium_portfolio_value,
            price=price,
            signal_strength=1.0,
        )

        # Max position = 1.5% of 10,000 = 150 EUR
        # 150 / 1,000,000 = 0.00015
        expected = Decimal("0.00015")

        assert abs(quantity - expected) < Decimal("0.000001")

    def test_decimal_precision_maintained(self, conservative_risk_manager):
        """All calculations should use Decimal for precision."""
        entry_price = Decimal("50000.123456")

        stop_loss = conservative_risk_manager.calculate_stop_loss(
            entry_price=entry_price,
            side=OrderSide.BUY,
        )

        # Result should be Decimal type
        assert isinstance(stop_loss, Decimal)

        # Should have exactly 2 decimal places (quantized)
        assert stop_loss == stop_loss.quantize(Decimal("0.01"))

    def test_unknown_risk_level_raises_value_error(self):
        """Unknown risk level MUST raise ValueError — no silent fallback.

        Critical because: Silent fallback to conservative could mask misconfiguration
        and leave a trader believing they have conservative limits when they don't.
        """
        import pytest

        with pytest.raises(ValueError, match="Unknown risk level"):
            RiskManager._get_risk_parameters_for_level("invalid_level")  # type: ignore[arg-type]

    def test_zero_portfolio_value_rejected(self, conservative_risk_manager):
        """CRITICAL: Zero portfolio value MUST be rejected immediately.

        Context: Safety requirement SAF-11
        Critical because: Division by zero in position percentage calculation
        would crash the bot or produce nonsensical results.
        """
        is_valid, reason = conservative_risk_manager.can_open_position(
            symbol="BTC-EUR",
            quantity=Decimal("0.001"),
            price=Decimal("50000"),
            portfolio_value=Decimal("0"),
            current_positions=[],
        )
        assert not is_valid
        assert "portfolio" in reason.lower()


class TestStrategyRiskOverrides:
    """Per-strategy stop-loss, take-profit, and position-size overrides."""

    def test_market_making_has_tight_stop_loss(self):
        rm = RiskManager(RiskLevel.MODERATE, strategy="market_making")
        assert rm.risk_params["stop_loss_pct"] == 0.5

    def test_market_making_has_small_take_profit(self):
        rm = RiskManager(RiskLevel.MODERATE, strategy="market_making")
        assert rm.risk_params["take_profit_pct"] == 0.3

    def test_breakout_has_wide_stop_loss(self):
        rm = RiskManager(RiskLevel.MODERATE, strategy="breakout")
        assert rm.risk_params["stop_loss_pct"] == 3.0

    def test_breakout_has_large_take_profit(self):
        rm = RiskManager(RiskLevel.MODERATE, strategy="breakout")
        assert rm.risk_params["take_profit_pct"] == 5.0

    def test_momentum_stop_loss_wider_than_mean_reversion(self):
        rm_momentum = RiskManager(RiskLevel.MODERATE, strategy="momentum")
        rm_mean_rev = RiskManager(RiskLevel.MODERATE, strategy="mean_reversion")
        assert rm_momentum.risk_params["stop_loss_pct"] > rm_mean_rev.risk_params["stop_loss_pct"]

    def test_overrides_do_not_change_max_open_positions(self):
        rm = RiskManager(RiskLevel.MODERATE, strategy="market_making")
        assert rm.risk_params["max_open_positions"] == 5  # MODERATE default

    def test_no_strategy_uses_risk_level_defaults(self):
        rm_base = RiskManager(RiskLevel.MODERATE)
        rm_none = RiskManager(RiskLevel.MODERATE, strategy=None)
        assert rm_none.risk_params["stop_loss_pct"] == rm_base.risk_params["stop_loss_pct"]

    def test_unknown_strategy_uses_risk_level_defaults(self):
        rm_base = RiskManager(RiskLevel.MODERATE)
        rm_unknown = RiskManager(RiskLevel.MODERATE, strategy="nonexistent")
        assert rm_unknown.risk_params["stop_loss_pct"] == rm_base.risk_params["stop_loss_pct"]

    def test_calculate_stop_loss_uses_strategy_override(self):
        from src.models.domain import OrderSide

        rm = RiskManager(RiskLevel.MODERATE, strategy="market_making")
        sl = rm.calculate_stop_loss(Decimal("50000"), OrderSide.BUY)
        expected = (Decimal("50000") * (1 - Decimal("0.5") / 100)).quantize(Decimal("0.01"))
        assert sl == expected

    def test_strategy_override_applies_across_all_risk_levels(self):
        # market_making SL override is absolute, regardless of risk level
        for level in (RiskLevel.CONSERVATIVE, RiskLevel.MODERATE, RiskLevel.AGGRESSIVE):
            rm = RiskManager(level, strategy="market_making")
            assert rm.risk_params["stop_loss_pct"] == 0.5

    def test_position_size_scales_with_risk_level_for_market_making(self):
        """Position sizing must reflect the user's risk level, not a fixed strategy value.

        The backtest matrix exists to show how different risk appetites affect
        performance — if market_making always uses 2.0% regardless of risk level,
        conservative/moderate/aggressive produce identical results, defeating the
        purpose of the matrix.
        """
        rm_cons = RiskManager(RiskLevel.CONSERVATIVE, strategy="market_making")
        rm_mod = RiskManager(RiskLevel.MODERATE, strategy="market_making")
        rm_agg = RiskManager(RiskLevel.AGGRESSIVE, strategy="market_making")
        assert (
            rm_cons.risk_params["max_position_size_pct"]
            < rm_mod.risk_params["max_position_size_pct"]
        )
        assert (
            rm_mod.risk_params["max_position_size_pct"]
            < rm_agg.risk_params["max_position_size_pct"]
        )

    def test_position_size_scales_with_risk_level_for_breakout(self):
        """Position sizing must reflect the user's risk level, not a fixed strategy value."""
        rm_cons = RiskManager(RiskLevel.CONSERVATIVE, strategy="breakout")
        rm_mod = RiskManager(RiskLevel.MODERATE, strategy="breakout")
        rm_agg = RiskManager(RiskLevel.AGGRESSIVE, strategy="breakout")
        assert (
            rm_cons.risk_params["max_position_size_pct"]
            < rm_mod.risk_params["max_position_size_pct"]
        )
        assert (
            rm_mod.risk_params["max_position_size_pct"]
            < rm_agg.risk_params["max_position_size_pct"]
        )
