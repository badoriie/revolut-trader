"""Unit tests for data models.

Covers the uncovered property accessors in BalanceData and CandleData,
plus Position helper methods.
"""

from decimal import Decimal

from src.models.domain import (
    BalanceData,
    CandleData,
    OrderBookEntry,
    OrderCreationData,
    OrderCreationResponse,
    OrderSide,
    Position,
)

# ---------------------------------------------------------------------------
# BalanceData
# ---------------------------------------------------------------------------


class TestBalanceData:
    """Tests for BalanceData matching the Revolut X API response shape.

    API returns: {"currency": "BTC", "available": "1.25", "reserved": "0.10", "staked": "0", "total": "1.35"}
    """

    def test_available_decimal(self):
        balance = BalanceData(currency="USD", available="1000.50", total="1000.50")
        assert balance.available_decimal == Decimal("1000.50")

    def test_total_decimal(self):
        balance = BalanceData(currency="BTC", available="1.00", reserved="0.10", total="1.10")
        assert balance.total_decimal == Decimal("1.10")

    def test_reserved_defaults_to_zero(self):
        balance = BalanceData(currency="ETH", available="5.0", total="5.0")
        assert balance.reserved == "0"

    def test_staked_defaults_to_zero(self):
        balance = BalanceData(currency="ETH", available="5.0", total="5.0")
        assert balance.staked == "0"

    def test_full_api_response(self):
        """All fields from a real API balance response are accepted."""
        balance = BalanceData(
            currency="BTC", available="1.25", reserved="0.10", staked="0", total="1.35"
        )
        assert balance.available_decimal == Decimal("1.25")
        assert balance.total_decimal == Decimal("1.35")


# ---------------------------------------------------------------------------
# CandleData
# ---------------------------------------------------------------------------


class TestCandleData:
    """Tests for CandleData property accessors."""

    def _make_candle(self, **overrides) -> CandleData:
        defaults = {
            "start": 1_700_000_000,
            "open": "50000",
            "high": "51000",
            "low": "49000",
            "close": "50500",
            "volume": "1.5",
        }
        defaults.update(overrides)
        return CandleData(**defaults)

    def test_timestamp_property(self):
        candle = self._make_candle(start=1_700_000_000)
        assert candle.timestamp == 1_700_000_000

    def test_open_price_property(self):
        candle = self._make_candle(open="50000.50")
        assert candle.open_price == Decimal("50000.50")

    def test_high_price_property(self):
        candle = self._make_candle(high="51000.75")
        assert candle.high_price == Decimal("51000.75")

    def test_low_price_property(self):
        candle = self._make_candle(low="49000.25")
        assert candle.low_price == Decimal("49000.25")

    def test_close_price_property(self):
        candle = self._make_candle(close="50500.10")
        assert candle.close_price == Decimal("50500.10")

    def test_volume_decimal_property(self):
        candle = self._make_candle(volume="2.75")
        assert candle.volume_decimal == Decimal("2.75")

    def test_string_values_required_per_api_docs(self):
        """API always returns string values for price/volume fields."""
        candle = CandleData(
            start=1_700_000_000,
            open="50000.0",
            high="51000.0",
            low="49000.0",
            close="50500.0",
            volume="1.5",
        )
        assert candle.open_price == Decimal("50000.0")
        assert candle.high_price == Decimal("51000.0")
        assert candle.low_price == Decimal("49000.0")
        assert candle.close_price == Decimal("50500.0")
        assert candle.volume_decimal == Decimal("1.5")


# ---------------------------------------------------------------------------
# Position helper methods
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# OrderBookEntry
# ---------------------------------------------------------------------------


class TestOrderBookEntry:
    """Tests for OrderBookEntry matching the Revolut X API response shape.

    API shape per docs:
      { "aid", "anm", "s" (SELL/BUY), "p", "pc", "q", "qc", "no", "ts", "pdt" }
    """

    def test_price_and_quantity_required(self):
        entry = OrderBookEntry(p="50000.00", q="0.5")
        assert entry.price == Decimal("50000.00")
        assert entry.quantity == Decimal("0.5")

    def test_full_ask_entry(self):
        """Full ask level as returned by the authenticated order book."""
        entry = OrderBookEntry(
            aid="BTC",
            anm="Bitcoin",
            s="SELL",
            p="51000.00",
            pc="EUR",
            q="0.1",
            qc="BTC",
            no="1",
            ts="CLOB",
            pdt=1700000000000,
        )
        assert entry.price == Decimal("51000.00")
        assert entry.quantity == Decimal("0.1")
        assert entry.s == "SELL"
        assert entry.aid == "BTC"
        assert entry.anm == "Bitcoin"
        assert entry.pc == "EUR"
        assert entry.qc == "BTC"
        assert entry.no == "1"
        assert entry.ts == "CLOB"
        assert entry.pdt == 1700000000000

    def test_full_bid_entry(self):
        """Full bid level as returned by the authenticated order book."""
        entry = OrderBookEntry(
            aid="BTC",
            anm="Bitcoin",
            s="BUY",
            p="50000.00",
            pc="EUR",
            q="0.2",
            qc="BTC",
            no="1",
            ts="CLOB",
            pdt=1700000000000,
        )
        assert entry.s == "BUY"
        assert entry.price == Decimal("50000.00")
        assert entry.quantity == Decimal("0.2")

    def test_optional_fields_default_to_none(self):
        entry = OrderBookEntry(p="100.00", q="1.0")
        assert entry.aid is None
        assert entry.anm is None
        assert entry.s is None
        assert entry.pc is None
        assert entry.qc is None
        assert entry.no is None
        assert entry.ts is None
        assert entry.pdt is None


# ---------------------------------------------------------------------------
# OrderCreationData / OrderCreationResponse
# ---------------------------------------------------------------------------


class TestOrderCreationData:
    """Tests for OrderCreationData matching the Revolut X API response shape.

    API returns:
      {"data": [{"venue_order_id": "<uuid>", "client_order_id": "<uuid>", "state": "new"}]}
    """

    def test_parses_new_state(self):
        """Newly placed working order returns state='new'."""
        data = OrderCreationData(
            venue_order_id="7a52e92e-8639-4fe1-abaa-68d3a2d5234b",
            client_order_id="984a4d8a-2a9b-4950-822f-2a40037f02bd",
            state="new",
        )
        assert data.state == "new"
        assert data.venue_order_id == "7a52e92e-8639-4fe1-abaa-68d3a2d5234b"

    def test_parses_pending_new_state(self):
        """Accepted but not yet working order returns state='pending_new'."""
        data = OrderCreationData(
            venue_order_id="abc-123",
            client_order_id="def-456",
            state="pending_new",
        )
        assert data.state == "pending_new"

    def test_order_creation_response_wraps_array(self):
        """API wraps the result in {'data': [...]} — always a single-element list."""
        response = OrderCreationResponse(
            data=[
                OrderCreationData(
                    venue_order_id="v-001",
                    client_order_id="c-001",
                    state="new",
                )
            ]
        )
        assert len(response.data) == 1
        assert response.data[0].venue_order_id == "v-001"
        assert response.data[0].state == "new"


# ---------------------------------------------------------------------------
# Position helper methods
# ---------------------------------------------------------------------------


class TestPositionUpdatePrice:
    """Tests for Position.update_price()."""

    def test_update_price_long_position_positive_pnl(self):
        pos = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
        )
        pos.update_price(Decimal("52000"))
        assert pos.current_price == Decimal("52000")
        assert pos.unrealized_pnl == Decimal("2000")

    def test_update_price_long_position_negative_pnl(self):
        pos = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
        )
        pos.update_price(Decimal("48000"))
        assert pos.unrealized_pnl == Decimal("-2000")

    def test_update_price_short_position(self):
        pos = Position(
            symbol="BTC-EUR",
            side=OrderSide.SELL,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
        )
        pos.update_price(Decimal("48000"))
        # Profit for short when price falls
        assert pos.unrealized_pnl == Decimal("2000")


class TestPositionShouldClose:
    """Tests for Position.should_close()."""

    def test_should_close_on_stop_loss(self):
        pos = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("48000"),
            stop_loss=Decimal("49000"),
        )
        should_close, reason = pos.should_close()
        assert should_close is True
        assert reason == "stop_loss"

    def test_should_close_on_take_profit(self):
        pos = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("52000"),
            take_profit=Decimal("51500"),
        )
        should_close, reason = pos.should_close()
        assert should_close is True
        assert reason == "take_profit"

    def test_should_not_close_when_within_range(self):
        pos = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50500"),
            stop_loss=Decimal("49000"),
            take_profit=Decimal("52000"),
        )
        should_close, reason = pos.should_close()
        assert should_close is False
        assert reason == ""

    def test_should_not_close_when_no_stop_or_tp(self):
        pos = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
        )
        should_close, reason = pos.should_close()
        assert should_close is False
        assert reason == ""
