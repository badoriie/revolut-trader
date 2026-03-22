"""Tests to cover remaining gaps in test coverage.

Targets the specific uncovered lines across multiple modules to push
coverage as high as possible.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.mock_client import MockRevolutAPIClient
from src.backtest.engine import BacktestEngine
from src.config import RiskLevel, StrategyType
from src.models.domain import (
    CandleData,
    MarketData,
    Order,
    OrderSide,
    OrderType,
    Signal,
)

# ---------------------------------------------------------------------------
# MockRevolutAPIClient — uncovered edge cases
# ---------------------------------------------------------------------------


class TestMockClientUnsupportedOrderType:
    """Line 297: unsupported order_type raises ValueError."""

    @pytest.mark.asyncio
    async def test_create_order_unsupported_type_raises(self):
        client = MockRevolutAPIClient()
        await client.initialize()
        with pytest.raises(ValueError, match="Unsupported order_type"):
            await client.create_order(
                symbol="BTC/EUR",
                side="buy",
                order_type="stop_loss",
                quantity="0.1",
                price="50000",
            )
        await client.close()


class TestMockClientOrderFilters:
    """Lines 376, 378, 380, 382: filtering orders by symbols/states/types/sides."""

    @pytest.mark.asyncio
    async def test_get_open_orders_filter_by_symbols(self):
        client = MockRevolutAPIClient()
        await client.initialize()
        await client.create_order("BTC/EUR", "buy", "limit", "0.1", "50000")
        await client.create_order("ETH/EUR", "buy", "limit", "1.0", "3000")

        result = await client.get_open_orders(symbols=["BTC/EUR"])
        assert all(o["symbol"] == "BTC/EUR" for o in result["data"])

        await client.close()

    @pytest.mark.asyncio
    async def test_get_open_orders_filter_by_states(self):
        client = MockRevolutAPIClient()
        await client.initialize()
        await client.create_order("BTC/EUR", "buy", "limit", "0.1", "50000")

        result = await client.get_open_orders(states=["new"])
        assert len(result["data"]) >= 1

        result_none = await client.get_open_orders(states=["filled"])
        assert len(result_none["data"]) == 0

        await client.close()

    @pytest.mark.asyncio
    async def test_get_open_orders_filter_by_types(self):
        client = MockRevolutAPIClient()
        await client.initialize()
        await client.create_order("BTC/EUR", "buy", "limit", "0.1", "50000")

        result = await client.get_open_orders(types=["limit"])
        assert len(result["data"]) >= 1

        result_none = await client.get_open_orders(types=["market"])
        assert len(result_none["data"]) == 0

        await client.close()

    @pytest.mark.asyncio
    async def test_get_open_orders_filter_by_sides(self):
        client = MockRevolutAPIClient()
        await client.initialize()
        await client.create_order("BTC/EUR", "buy", "limit", "0.1", "50000")

        result = await client.get_open_orders(sides=["buy"])
        assert len(result["data"]) >= 1

        result_none = await client.get_open_orders(sides=["sell"])
        assert len(result_none["data"]) == 0

        await client.close()


class TestMockClientOrderLookupHistorical:
    """Lines 432-436: get_order looks in _historical_orders."""

    @pytest.mark.asyncio
    async def test_get_order_from_historical(self):
        client = MockRevolutAPIClient()
        await client.initialize()
        result = await client.create_order("BTC/EUR", "buy", "limit", "0.1", "50000")
        order_id = result["venue_order_id"]
        # Cancel moves it to historical
        await client.cancel_order(order_id)
        # Should find in historical
        order = await client.get_order(order_id)
        assert order["id"] == order_id
        assert order["status"] == "cancelled"
        await client.close()

    @pytest.mark.asyncio
    async def test_get_order_not_found_raises(self):
        client = MockRevolutAPIClient()
        await client.initialize()
        with pytest.raises(ValueError, match="Order not found"):
            await client.get_order("nonexistent-id")
        await client.close()


class TestMockClientCancelNotFound:
    """Line 452: cancel_order raises if not found."""

    @pytest.mark.asyncio
    async def test_cancel_order_not_found_raises(self):
        client = MockRevolutAPIClient()
        await client.initialize()
        with pytest.raises(ValueError, match="Order not found"):
            await client.cancel_order("nonexistent-id")
        await client.close()


class TestMockClientGetTickersFiltered:
    """Line 642: get_tickers filters by symbol list."""

    @pytest.mark.asyncio
    async def test_get_tickers_filtered(self):
        client = MockRevolutAPIClient()
        await client.initialize()
        result = await client.get_tickers(symbols=["BTC-EUR"])
        assert len(result) == 1
        assert result[0]["symbol"] == "BTC/EUR"
        await client.close()


# ---------------------------------------------------------------------------
# RevolutAPIClient — uncovered edge cases (mocked HTTP)
# ---------------------------------------------------------------------------


class TestRevolutAPIClientInit:
    """Lines 62-63, 66: __aenter__ / __aexit__."""

    @pytest.mark.asyncio
    async def test_context_manager(self):
        from src.api.client import RevolutAPIClient

        client = RevolutAPIClient.__new__(RevolutAPIClient)
        client.client = MagicMock()
        client.client.aclose = AsyncMock()
        client._private_key = None
        client.initialize = AsyncMock()
        client.close = AsyncMock()

        result = await client.__aenter__()
        assert result is client
        client.initialize.assert_called_once()

        await client.__aexit__(None, None, None)
        client.close.assert_called_once()


class TestRevolutAPIClientKeyLoading:
    """Lines 75-88: initialize loads Ed25519 key."""

    @pytest.mark.asyncio
    async def test_initialize_invalid_key_raises(self):
        from src.api.client import RevolutAPIClient

        client = RevolutAPIClient.__new__(RevolutAPIClient)
        client._private_key = None
        with patch("src.utils.onepassword.get", return_value="not-a-pem-key"):
            with pytest.raises(ValueError, match="Failed to load private key"):
                await client.initialize()

    @pytest.mark.asyncio
    async def test_initialize_non_ed25519_key_raises(self):
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
        )

        from src.api.client import RevolutAPIClient

        rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        rsa_pem = rsa_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()

        client = RevolutAPIClient.__new__(RevolutAPIClient)
        client._private_key = None
        with patch("src.utils.onepassword.get", return_value=rsa_pem):
            with pytest.raises(ValueError, match="Ed25519"):
                await client.initialize()


class TestRevolutAPIClientGenerateSignature:
    """Line 103: _generate_signature raises if private key not loaded."""

    def test_signature_without_key_raises(self):
        from src.api.client import RevolutAPIClient

        client = RevolutAPIClient.__new__(RevolutAPIClient)
        client._private_key = None
        with pytest.raises(RuntimeError, match="Private key not loaded"):
            client._generate_signature("ts", "GET", "/path")


class TestRevolutAPIClientExtractApiMessage:
    """Lines 132-133: _extract_api_message fallback."""

    def test_fallback_when_json_fails(self):
        from src.api.client import RevolutAPIClient

        mock_response = MagicMock()
        mock_response.json.side_effect = Exception("not json")

        error = MagicMock(spec=Exception)
        error.response = mock_response
        error.__str__ = lambda self: "raw error"

        result = RevolutAPIClient._extract_api_message(error)
        assert result == "raw error"


class TestRevolutAPIClientPublicRequest:
    """Lines 211, 225-230: _public_request edge cases."""

    @pytest.mark.asyncio
    async def test_public_request_exhausts_all_urls(self):
        """When all base URLs fail with ConnectError, raises the last error."""
        import httpx

        from src.api.client import RevolutAPIClient

        client = RevolutAPIClient.__new__(RevolutAPIClient)
        client._base_urls = ["https://url1.com/api/1.0", "https://url2.com/api/1.0"]
        client.base_url = client._base_urls[0]
        mock_http_client = MagicMock()
        mock_http_client.request = AsyncMock(side_effect=httpx.ConnectError("fail"))
        client.client = mock_http_client

        with pytest.raises(httpx.ConnectError):
            await client._public_request("/test")

    @pytest.mark.asyncio
    async def test_public_request_generic_exception_reraises(self):
        """Non-HTTP exceptions are re-raised immediately."""
        from src.api.client import RevolutAPIClient

        client = RevolutAPIClient.__new__(RevolutAPIClient)
        client._base_urls = ["https://url1.com/api/1.0"]
        client.base_url = client._base_urls[0]
        mock_http_client = MagicMock()
        mock_http_client.request = AsyncMock(side_effect=RuntimeError("unexpected"))
        client.client = mock_http_client

        with pytest.raises(RuntimeError, match="unexpected"):
            await client._public_request("/test")


class TestRevolutAPIClientGetTickers:
    """Lines 849, 873-874: get_tickers edge cases."""

    @pytest.mark.asyncio
    async def test_get_tickers_unexpected_type_raises(self):
        from src.api.client import RevolutAPIClient
        from src.utils.rate_limiter import RateLimiter

        client = RevolutAPIClient.__new__(RevolutAPIClient)
        client.rate_limiter = RateLimiter(max_requests=60, time_window=60.0)
        client._request = AsyncMock(return_value="not-a-dict-or-list")
        with pytest.raises(ValueError, match="Unexpected /tickers response type"):
            await client.get_tickers()

    @pytest.mark.asyncio
    async def test_get_ticker_malformed_order_book_raises(self):
        from src.api.client import RevolutAPIClient

        client = RevolutAPIClient.__new__(RevolutAPIClient)
        client.get_order_book = AsyncMock(return_value={"bad": "data"})
        with pytest.raises(ValueError, match="Malformed order book"):
            await client.get_ticker("BTC-EUR")


# ---------------------------------------------------------------------------
# BacktestEngine — SL/TP, signal execution, drawdown, force-close
# ---------------------------------------------------------------------------


def _make_candle(start: int, close: str) -> CandleData:
    return CandleData(start=start, open=close, high=close, low=close, close=close, volume="10")


def _candle_to_dict(c: CandleData) -> dict:
    return {
        "start": c.start,
        "open": c.open,
        "high": c.high,
        "low": c.low,
        "close": c.close,
        "volume": c.volume,
    }


class TestBacktestEngineStopLossTrigger:
    """Lines 560-577: SL/TP triggered positions during run."""

    @pytest.mark.asyncio
    async def test_stop_loss_closes_position_during_run(self):
        mock_api = MagicMock()

        engine = BacktestEngine(
            api_client=mock_api,
            strategy_type=StrategyType.MOMENTUM,
            risk_level=RiskLevel.MODERATE,
            initial_capital=Decimal("10000"),
        )

        # Manually open a position that will be stop-lossed
        from src.models.domain import Position

        pos = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
            stop_loss=Decimal("48000"),
        )
        engine.positions["BTC-EUR"] = pos
        engine.cash_balance = Decimal("5000")

        # Candle drops below stop loss
        candles = [_make_candle(1_700_000_000_000, "47000")]
        mock_api.get_candles = AsyncMock(return_value=[_candle_to_dict(c) for c in candles])

        results = await engine.run(["BTC-EUR"], days=1, interval=60)
        assert engine.positions == {}
        assert results.total_trades >= 1


class TestBacktestEngineSignalExecution:
    """Lines 593-617: strategy signal -> risk validation -> execution path."""

    @pytest.mark.asyncio
    async def test_buy_signal_executes_trade(self):
        mock_api = MagicMock()

        engine = BacktestEngine(
            api_client=mock_api,
            strategy_type=StrategyType.MOMENTUM,
            risk_level=RiskLevel.MODERATE,
            initial_capital=Decimal("10000"),
        )

        mock_signal = Signal(
            symbol="BTC-EUR",
            signal_type="BUY",
            price=Decimal("50000"),
            strength=Decimal("0.8"),
            strategy="momentum",
            reason="test",
        )
        engine.strategy.analyze = AsyncMock(return_value=mock_signal)

        candles = [_make_candle(1_700_000_000_000 + i * 60_000, "50000") for i in range(5)]
        mock_api.get_candles = AsyncMock(return_value=[_candle_to_dict(c) for c in candles])

        results = await engine.run(["BTC-EUR"], days=1, interval=60)
        assert results.total_trades >= 1

    @pytest.mark.asyncio
    async def test_rejected_signal_does_not_execute(self):
        mock_api = MagicMock()

        engine = BacktestEngine(
            api_client=mock_api,
            strategy_type=StrategyType.MOMENTUM,
            risk_level=RiskLevel.MODERATE,
            initial_capital=Decimal("10000"),
        )

        # SELL signal with no position — will be rejected by execute_backtest_order
        mock_signal = Signal(
            symbol="BTC-EUR",
            signal_type="SELL",
            price=Decimal("50000"),
            strength=Decimal("0.8"),
            strategy="momentum",
            reason="test",
        )
        engine.strategy.analyze = AsyncMock(return_value=mock_signal)

        candles = [_make_candle(1_700_000_000_000, "50000")]
        mock_api.get_candles = AsyncMock(return_value=[_candle_to_dict(c) for c in candles])

        results = await engine.run(["BTC-EUR"], days=1, interval=60)
        assert results.total_trades == 0


class TestBacktestEngineForceClose:
    """Lines 643-644: force-close open positions at end of backtest."""

    @pytest.mark.asyncio
    async def test_open_positions_force_closed_at_end(self):
        mock_api = MagicMock()
        engine = BacktestEngine(
            api_client=mock_api,
            strategy_type=StrategyType.MOMENTUM,
            risk_level=RiskLevel.MODERATE,
            initial_capital=Decimal("20000"),
        )

        mock_signal = Signal(
            symbol="BTC-EUR",
            signal_type="BUY",
            price=Decimal("50000"),
            strength=Decimal("0.8"),
            strategy="momentum",
            reason="test",
        )
        call_count = 0

        async def signal_once(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_signal
            return None

        engine.strategy.analyze = AsyncMock(side_effect=signal_once)

        candles = [
            _make_candle(1_700_000_000_000, "50000"),
            _make_candle(1_700_000_060_000, "51000"),
        ]
        mock_api.get_candles = AsyncMock(return_value=[_candle_to_dict(c) for c in candles])

        results = await engine.run(["BTC-EUR"], days=1, interval=60)
        assert engine.positions == {}
        assert results.total_trades >= 1


class TestBacktestEngineDrawdownUpdate:
    """Lines 633, 637-639: drawdown peak tracking and max_drawdown_pct."""

    @pytest.mark.asyncio
    async def test_drawdown_tracks_equity_changes(self):
        mock_api = MagicMock()
        engine = BacktestEngine(
            api_client=mock_api,
            strategy_type=StrategyType.MOMENTUM,
            risk_level=RiskLevel.MODERATE,
            initial_capital=Decimal("10000"),
        )

        # Strategy returns None (no trades), drawdown from flat equity = 0
        engine.strategy.analyze = AsyncMock(return_value=None)

        candles = [
            _make_candle(1_700_000_000_000, "50000"),
            _make_candle(1_700_000_060_000, "50000"),
            _make_candle(1_700_000_120_000, "50000"),
        ]
        mock_api.get_candles = AsyncMock(return_value=[_candle_to_dict(c) for c in candles])

        results = await engine.run(["BTC-EUR"], days=1, interval=60)
        assert results.max_drawdown >= Decimal("0")
        assert len(results.equity_curve) == 3


# ---------------------------------------------------------------------------
# RiskManager — uncovered edge cases
# ---------------------------------------------------------------------------


class TestRiskManagerEdgeCases:
    """Lines 233, 242, 352, 355."""

    def test_order_exceeds_portfolio_value(self):
        from src.risk_management.risk_manager import RiskManager

        rm = RiskManager(RiskLevel.MODERATE)
        order = Order(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("100"),
            price=Decimal("50000"),
        )
        is_valid, reason = rm.validate_order_sanity(order, order.price, Decimal("1000"))
        assert is_valid is False
        assert "exceeds" in reason.lower()

    def test_order_quantity_unreasonably_large(self):
        """Quantity sanity check triggers when qty > portfolio/price * multiplier."""
        from src.risk_management.risk_manager import RiskManager

        rm = RiskManager(RiskLevel.MODERATE)
        # To reach check 3, we need: value < 10k AND value < portfolio
        # Then qty > portfolio/price * max_quantity_multiplier (1000)
        # Set multiplier low so we can trigger with reasonable values
        rm.max_quantity_multiplier = Decimal("1")
        # max_reasonable = 100000 / 0.001 * 1 = 100_000_000
        # Need qty > 100_000_000, value = qty * 0.001 → need value < 10k
        # qty = 9_999_000 → value = 9999 < 10k, max_reasonable = 100_000_000 — still under
        # Use even smaller multiplier
        rm.max_quantity_multiplier = Decimal("0.001")
        # max_reasonable = 100000 / 1 * 0.001 = 100
        # qty = 200, value = 200 < 10k < portfolio(100k) — passes checks 1,2
        order = Order(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("200"),
            price=Decimal("1"),
        )
        is_valid, reason = rm.validate_order_sanity(order, order.price, Decimal("100000"))
        assert is_valid is False
        assert "unreasonably large" in reason.lower()

    def test_validate_order_zero_price(self):
        from src.risk_management.risk_manager import RiskManager

        rm = RiskManager(RiskLevel.MODERATE)
        order = Order(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("1"),
            price=Decimal("0"),
        )
        is_valid, reason = rm.validate_order(order, Decimal("10000"), [])
        assert is_valid is False

    def test_validate_order_zero_quantity(self):
        from src.risk_management.risk_manager import RiskManager

        rm = RiskManager(RiskLevel.MODERATE)
        order = Order(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0"),
            price=Decimal("50000"),
        )
        is_valid, reason = rm.validate_order(order, Decimal("10000"), [])
        assert is_valid is False


# ---------------------------------------------------------------------------
# MarketMakingStrategy — zero mid price guard
# ---------------------------------------------------------------------------


class TestMarketMakingZeroMidPrice:
    """Lines 46-47: zero mid price returns None."""

    @pytest.mark.asyncio
    async def test_negative_mid_price_returns_none(self):
        from src.strategies.market_making import MarketMakingStrategy

        strategy = MarketMakingStrategy()
        market_data = MarketData(
            symbol="BTC-EUR",
            bid=Decimal("-1"),
            ask=Decimal("1"),
            last=Decimal("0"),
            volume_24h=Decimal("100"),
            high_24h=Decimal("1"),
            low_24h=Decimal("-1"),
            timestamp=datetime.now(UTC),
        )
        result = await strategy.analyze("BTC-EUR", market_data, [], Decimal("10000"))
        assert result is None


# ---------------------------------------------------------------------------
# OrderExecutor — _close_position in LIVE mode
# ---------------------------------------------------------------------------


class TestExecutorClosePositionLivePath:
    """Line 290: _close_position in LIVE mode."""

    @pytest.mark.asyncio
    async def test_close_position_live_mode(self):
        from src.config import RiskLevel, TradingMode
        from src.execution.executor import OrderExecutor
        from src.models.domain import Position
        from src.risk_management.risk_manager import RiskManager

        rm = RiskManager(RiskLevel.MODERATE)
        mock_api = MagicMock()
        mock_api.create_order = AsyncMock(
            return_value={
                "data": [
                    {
                        "venue_order_id": "test-id",
                        "client_order_id": "test-client-id",
                        "state": "new",
                    }
                ]
            }
        )
        executor = OrderExecutor(mock_api, rm, TradingMode.LIVE)
        executor.positions["BTC-EUR"] = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("49000"),
        )

        await executor._close_position("BTC-EUR", Decimal("49000"), "stop_loss")
        mock_api.create_order.assert_called_once()


# ---------------------------------------------------------------------------
# RSI indicator — fallback during initialization
# ---------------------------------------------------------------------------


class TestRSIFallback:
    """Line 140: RSI returns 50 during initialization period."""

    def test_rsi_returns_fifty_before_warmup(self):
        from src.utils.indicators import RSI

        rsi = RSI(period=14)
        # First update — not enough data yet, returns neutral
        result = rsi.update(Decimal("100"))
        assert result == Decimal("50")

    def test_rsi_returns_fifty_during_warmup(self):
        """During warmup (2nd to period-th update), RSI returns 50."""
        from src.utils.indicators import RSI

        rsi = RSI(period=14)
        rsi.update(Decimal("100"))
        # 2nd update — still in warmup
        result = rsi.update(Decimal("101"))
        assert result == Decimal("50")


# ---------------------------------------------------------------------------
# DatabasePersistence — backtest query filter by strategy
# ---------------------------------------------------------------------------


class TestDbPersistenceBacktestFilter:
    """Line 498: load_backtest_runs filters by strategy."""

    def test_load_backtest_runs_with_strategy_filter(self):
        from src.utils.db_persistence import DatabasePersistence

        db = DatabasePersistence()
        results = db.load_backtest_runs(strategy="momentum", limit=5)
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Bot — read-only API key log, trade history log
# ---------------------------------------------------------------------------


class TestBotReadOnlyApiKey:
    """Line 119: bot logs when API key is read-only."""

    @pytest.mark.asyncio
    async def test_start_with_read_only_key(self, monkeypatch):
        mock_persistence = MagicMock()
        mock_persistence.load_portfolio_snapshots.return_value = []
        mock_persistence.load_trade_history.return_value = []
        mock_persistence.get_analytics.return_value = {"total_trades": 0}
        mock_persistence.start_session.return_value = 1
        monkeypatch.setattr("src.bot.DatabasePersistence", lambda *a, **kw: mock_persistence)

        from src.bot import TradingBot

        bot = TradingBot(
            strategy_type=StrategyType.MOMENTUM,
            risk_level=RiskLevel.MODERATE,
            trading_pairs=["BTC-EUR"],
        )

        mock_api = MagicMock()
        mock_api.initialize = AsyncMock()
        mock_api.close = AsyncMock()
        mock_api.check_permissions = AsyncMock(return_value={"view": True, "trade": False})

        with patch("src.bot.create_api_client", return_value=mock_api):
            await bot.start()

        assert bot.is_running is True
        await bot.stop()

    @pytest.mark.asyncio
    async def test_load_historical_data_with_trades(self, monkeypatch):
        mock_persistence = MagicMock()
        mock_persistence.load_portfolio_snapshots.return_value = []
        mock_persistence.load_trade_history.return_value = [{"id": 1}]
        mock_persistence.get_analytics.return_value = {"total_trades": 0}
        monkeypatch.setattr("src.bot.DatabasePersistence", lambda *a, **kw: mock_persistence)

        from src.bot import TradingBot

        bot = TradingBot(
            strategy_type=StrategyType.MOMENTUM,
            risk_level=RiskLevel.MODERATE,
            trading_pairs=["BTC-EUR"],
        )
        bot._load_historical_data()
        mock_persistence.load_trade_history.assert_called_once()


# ---------------------------------------------------------------------------
# Config — edge cases
# ---------------------------------------------------------------------------


class TestConfigEdgeCases:
    """Lines 68, 74: environment normalization and pair parsing."""

    def test_trading_pairs_are_parsed(self):
        from src.config import settings

        assert isinstance(settings.trading_pairs, list)
        assert all(isinstance(p, str) for p in settings.trading_pairs)
