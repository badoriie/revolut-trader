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
from src.data.models import OrderSide
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
