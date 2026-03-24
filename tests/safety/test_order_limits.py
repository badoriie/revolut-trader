"""Order Safety Tests - CRITICAL

These tests verify that:
1. Orders exceeding portfolio value are rejected
2. Orders exceeding absolute max value are rejected
3. Fat finger mistakes (extra zeros) are caught
4. Daily loss limits stop trading
5. Max positions limit is enforced
6. Minimum order value is enforced

Critical because: One catastrophic order could wipe out entire portfolio.

Test strategy: Create orders that violate safety rules and verify they
are rejected with clear error messages.
"""

from decimal import Decimal

from src.config import RiskLevel
from src.models.domain import Order, OrderSide, OrderType
from src.risk_management.risk_manager import RiskManager


class TestOrderValueLimits:
    """Tests that verify order value limits are enforced."""

    def test_order_value_exceeds_portfolio_rejected(
        self, conservative_risk_manager, medium_portfolio_value
    ):
        """CRITICAL: Order worth more than entire portfolio MUST be rejected.

        Context: Safety requirement SAF-03
        Critical because: Could attempt to use leverage or cause massive loss

        Scenario: Portfolio = 10,000 EUR, try to buy 100 BTC @ 50,000 EUR
        """
        order = Order(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("100"),  # 100 BTC
            price=Decimal("50000"),  # 50,000 EUR each
        )

        # Order value = 100 * 50,000 = 5,000,000 EUR (way more than 10,000 EUR portfolio)
        current_price = Decimal("50000")

        is_valid, reason = conservative_risk_manager.validate_order_sanity(
            order=order,
            current_price=current_price,
            portfolio_value=medium_portfolio_value,
        )

        assert not is_valid
        # Order is rejected due to exceeding safety limit (checked first) or portfolio value
        assert "exceeds portfolio value" in reason or "exceeds safety limit" in reason
        assert "€5,000,000" in reason  # Should show order value

    def test_order_exceeds_max_value_limit_rejected(
        self, conservative_risk_manager, large_portfolio_value
    ):
        """CRITICAL: Order exceeding absolute max value MUST be rejected.

        Context: Safety requirement SAF-04
        Critical because: Even with large portfolio, need safety limit

        Scenario: Max limit = 10,000 EUR, try to place 50,000 EUR order
        """
        order = Order(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("1"),  # 1 BTC
            price=Decimal("50000"),  # 50,000 EUR
        )

        # Order value = 50,000 EUR > max_order_value (10,000 EUR)
        current_price = Decimal("50000")

        is_valid, reason = conservative_risk_manager.validate_order_sanity(
            order=order,
            current_price=current_price,
            portfolio_value=large_portfolio_value,  # 100,000 EUR - portfolio is large enough
        )

        assert not is_valid
        assert "exceeds safety limit" in reason
        assert "€50,000" in reason

    def test_quantity_typo_protection(self, conservative_risk_manager, medium_portfolio_value):
        """CRITICAL: Accidentally adding extra zeros MUST be caught.

        Context: Safety requirement SAF-05
        Critical because: Common human error, could cause massive loss

        Scenario: Meant to buy 0.2 BTC, accidentally typed 200 BTC
        """
        # Reasonable order: 0.2 BTC @ 50,000 EUR = 10,000 EUR (OK)
        # Typo order: 200 BTC @ 50,000 EUR = 10,000,000 EUR (NOT OK!)

        typo_order = Order(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("200"),  # Typo! Meant 0.2
            price=Decimal("50000"),
        )

        current_price = Decimal("50000")

        is_valid, reason = conservative_risk_manager.validate_order_sanity(
            order=typo_order,
            current_price=current_price,
            portfolio_value=medium_portfolio_value,
        )

        assert not is_valid
        # Order rejected for being too large (either unreasonably large or safety limit)
        assert "unreasonably large" in reason.lower() or "exceeds" in reason.lower()

    def test_minimum_order_value_enforced(self, conservative_risk_manager, medium_portfolio_value):
        """CRITICAL: Dust orders below minimum MUST be rejected.

        Context: Safety requirement SAF-06
        Critical because: Fees could exceed order value, waste resources

        Scenario: Order value = 5 EUR (below 10 EUR minimum)
        """
        # Very small order: 0.0001 BTC @ 50,000 EUR = 5 EUR
        dust_order = Order(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.0001"),
            price=Decimal("50000"),
        )

        current_price = Decimal("50000")

        is_valid, reason = conservative_risk_manager.validate_order_sanity(
            order=dust_order,
            current_price=current_price,
            portfolio_value=medium_portfolio_value,
        )

        assert not is_valid
        assert "below minimum" in reason.lower()
        assert "€5" in reason


class TestDailyLossLimits:
    """Tests that verify daily loss limits stop trading."""

    def test_daily_loss_limit_stops_trading(
        self, conservative_risk_manager, medium_portfolio_value
    ):
        """CRITICAL: Trading MUST stop when daily loss limit hit.

        Context: Safety requirement SAF-07
        Critical because: Prevents revenge trading, protects capital

        Scenario: Conservative = 3% loss limit on 10,000 EUR = 300 EUR
        After losing 300 EUR, all new orders must be rejected
        """
        # Simulate losses totaling 300 EUR (3% of 10,000)
        loss = Decimal("-300")
        conservative_risk_manager.update_daily_pnl(pnl=loss, initial_capital=medium_portfolio_value)

        # Try to open new position
        test_order = Order(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
        )

        is_valid, reason = conservative_risk_manager.validate_order(
            order=test_order,
            portfolio_value=medium_portfolio_value,
            current_positions=[],
        )

        assert not is_valid
        assert "daily loss limit" in reason.lower()
        assert "trading suspended" in reason.lower()

    def test_just_under_loss_limit_allows_trading(
        self, conservative_risk_manager, medium_portfolio_value
    ):
        """Trading should continue if just under loss limit."""
        # Loss = 290 EUR (just under 300 EUR limit)
        loss = Decimal("-290")
        conservative_risk_manager.update_daily_pnl(pnl=loss, initial_capital=medium_portfolio_value)

        # Should still allow trading
        # Conservative limit: 1.5% of 10000 = 150 EUR max position
        # 0.002 BTC * 50000 EUR = 100 EUR < 150 EUR limit
        is_valid, _reason = conservative_risk_manager.can_open_position(
            symbol="BTC-EUR",
            quantity=Decimal("0.002"),
            price=Decimal("50000"),
            portfolio_value=medium_portfolio_value,
            current_positions=[],
        )

        assert is_valid

    def test_reset_daily_limits_allows_trading_again(
        self, conservative_risk_manager, medium_portfolio_value
    ):
        """After reset (new day), trading should resume."""
        # Hit loss limit
        loss = Decimal("-300")
        conservative_risk_manager.update_daily_pnl(pnl=loss, initial_capital=medium_portfolio_value)

        # Reset for new day
        conservative_risk_manager.reset_daily_limits()

        # Should allow trading again
        # Conservative limit: 1.5% of 10000 = 150 EUR max position
        # 0.002 BTC * 50000 EUR = 100 EUR < 150 EUR limit
        is_valid, _ = conservative_risk_manager.can_open_position(
            symbol="BTC-EUR",
            quantity=Decimal("0.002"),
            price=Decimal("50000"),
            portfolio_value=medium_portfolio_value,
            current_positions=[],
        )

        assert is_valid


class TestMaxPositionsLimit:
    """Tests that verify maximum positions limit is enforced."""

    def test_max_positions_limit_enforced(
        self,
        conservative_risk_manager,
        medium_portfolio_value,
        btc_long_position,
        eth_long_position,
    ):
        """CRITICAL: Cannot exceed max open positions.

        Context: Safety requirement SAF-08
        Critical because: Too many positions = unable to manage risk

        Scenario: Conservative = max 3 positions
        Already have 3 positions, try to open 4th
        """
        # Conservative allows max 3 positions
        # Create 3 existing positions
        position_3 = btc_long_position.model_copy(update={"symbol": "SOL-EUR"})

        current_positions = [btc_long_position, eth_long_position, position_3]

        # Try to open 4th position
        is_valid, reason = conservative_risk_manager.can_open_position(
            symbol="MATIC-EUR",
            quantity=Decimal("10"),
            price=Decimal("1"),
            portfolio_value=medium_portfolio_value,
            current_positions=current_positions,
        )

        assert not is_valid
        assert "maximum" in reason.lower()
        assert "3 positions" in reason

    def test_can_open_position_when_under_limit(
        self, conservative_risk_manager, medium_portfolio_value, btc_long_position
    ):
        """Can open position when under max limit."""
        # Only 1 position open, can open another
        # Conservative limit: 1.5% of 10000 = 150 EUR max position
        # 0.04 ETH * 3000 EUR = 120 EUR < 150 EUR limit
        current_positions = [btc_long_position]

        is_valid, _ = conservative_risk_manager.can_open_position(
            symbol="ETH-EUR",
            quantity=Decimal("0.04"),
            price=Decimal("3000"),
            portfolio_value=medium_portfolio_value,
            current_positions=current_positions,
        )

        assert is_valid

    def test_different_risk_levels_have_different_limits(self, medium_portfolio_value):
        """Different risk levels should have different max positions."""
        conservative_rm = RiskManager(RiskLevel.CONSERVATIVE)
        moderate_rm = RiskManager(RiskLevel.MODERATE)
        aggressive_rm = RiskManager(RiskLevel.AGGRESSIVE)

        # Conservative = 3, Moderate = 5, Aggressive = 8
        conservative_params = conservative_rm.risk_params
        moderate_params = moderate_rm.risk_params
        aggressive_params = aggressive_rm.risk_params

        assert conservative_params["max_open_positions"] == 3
        assert moderate_params["max_open_positions"] == 5
        assert aggressive_params["max_open_positions"] == 8


class TestConcentrationRisk:
    """Tests that verify concentration risk (too much in one symbol) is prevented."""

    def test_concentration_risk_prevents_overexposure(
        self, conservative_risk_manager, medium_portfolio_value
    ):
        """CRITICAL: Total exposure to one symbol must be limited.

        Context: Safety requirement SAF-09
        Critical because: Too much in one asset = correlated risk

        Scenario:
        - Portfolio = 10,000 EUR, conservative max = 1.5%, concentration limit = 3% (300 EUR)
        - Existing BTC position: 0.004 BTC @ 50,000 EUR = 200 EUR (2% of portfolio)
        - New order: 0.003 BTC @ 50,000 EUR = 150 EUR (1.5% — within individual limit)
        - Total BTC exposure: 350 EUR = 3.5% > 3% concentration limit → REJECTED
        """
        from src.models.domain import Position

        existing_btc = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("0.004"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
        )

        is_valid, reason = conservative_risk_manager.can_open_position(
            symbol="BTC-EUR",
            quantity=Decimal("0.003"),  # 150 EUR = 1.5% — passes individual check
            price=Decimal("50000"),
            portfolio_value=medium_portfolio_value,
            current_positions=[existing_btc],
        )

        assert not is_valid
        assert "concentration" in reason.lower() or "exposure" in reason.lower()

    def test_can_open_different_symbol_with_existing_positions(
        self, conservative_risk_manager, medium_portfolio_value, btc_long_position
    ):
        """Can open position in different symbol even with existing positions."""
        # Have BTC position, open ETH position (different symbol)
        # Conservative limit: 1.5% of 10000 = 150 EUR max position
        # 0.04 ETH * 3000 EUR = 120 EUR < 150 EUR limit
        is_valid, _ = conservative_risk_manager.can_open_position(
            symbol="ETH-EUR",  # Different symbol
            quantity=Decimal("0.04"),
            price=Decimal("3000"),
            portfolio_value=medium_portfolio_value,
            current_positions=[btc_long_position],
        )

        # Should be allowed (different symbols)
        assert is_valid


class TestValidateOrderRunsSanityChecks:
    """Tests that validate_order() enforces ALL safety limits, not just position rules.

    Critical because: validate_order() is the single gate before execution. If it
    only checks position-level rules but skips absolute safety limits, an order that
    is a small fraction of a huge portfolio could still be catastrophically large
    in absolute EUR terms.
    """

    def test_validate_order_rejects_order_exceeding_max_value(self):
        """CRITICAL: validate_order() MUST reject orders over the absolute max.

        Context: Safety requirement SAF-12
        Scenario:
        - Portfolio = 2,000,000 EUR (very large)
        - Order = 0.5 BTC @ 50,000 EUR = 25,000 EUR (only 1.25% of portfolio — passes
          position-size check but exceeds absolute 10,000 EUR safety limit)
        - validate_order() MUST reject this — the safety limit exists for a reason.
        """
        rm = RiskManager(RiskLevel.CONSERVATIVE, max_order_value=10000)
        large_portfolio = Decimal("2000000")

        order = Order(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.5"),  # 0.5 * 50,000 = 25,000 EUR
            price=Decimal("50000"),
        )

        is_valid, reason = rm.validate_order(
            order=order,
            portfolio_value=large_portfolio,
            current_positions=[],
        )

        assert not is_valid
        assert "exceeds safety limit" in reason


class TestPositionSizeValidation:
    """Tests that verify position size limits are enforced."""

    def test_position_exceeds_max_percentage_rejected(
        self, conservative_risk_manager, medium_portfolio_value
    ):
        """CRITICAL: Position exceeding max % of portfolio MUST be rejected.

        Context: Safety requirement SAF-10
        Critical because: Core risk management rule

        Scenario: Conservative max = 1.5% of 10,000 EUR = 150 EUR
        Try to open 500 EUR position (5% of portfolio)
        """
        # 500 EUR position = 0.01 BTC @ 50,000 EUR
        is_valid, reason = conservative_risk_manager.can_open_position(
            symbol="BTC-EUR",
            quantity=Decimal("0.01"),  # 0.01 * 50,000 = 500 EUR
            price=Decimal("50000"),
            portfolio_value=medium_portfolio_value,
            current_positions=[],
        )

        assert not is_valid
        assert "exceeds max" in reason.lower()
        assert "1.5%" in reason or "5%" in reason

    def test_position_within_limit_accepted(
        self, conservative_risk_manager, medium_portfolio_value
    ):
        """Position within size limit should be accepted."""
        # Conservative max = 1.5% of 10,000 EUR = 150 EUR
        # 100 EUR position = well within limit
        # 100 EUR = 0.002 BTC @ 50,000 EUR

        is_valid, reason = conservative_risk_manager.can_open_position(
            symbol="BTC-EUR",
            quantity=Decimal("0.002"),
            price=Decimal("50000"),
            portfolio_value=medium_portfolio_value,
            current_positions=[],
        )

        assert is_valid
        assert "approved" in reason.lower() or reason == "Position approved"
