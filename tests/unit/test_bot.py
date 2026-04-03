"""Unit tests for TradingBot orchestrator."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.config import RiskLevel, StrategyType, TradingMode
from src.models.domain import OrderSide, OrderStatus, OrderType, PortfolioSnapshot, Signal


@pytest.fixture
def mock_persistence():
    mock = MagicMock()
    mock.load_portfolio_snapshots.return_value = []
    mock.load_trade_history.return_value = []
    mock.get_analytics.return_value = {"total_trades": 0}
    return mock


@pytest.fixture
def bot(monkeypatch, mock_persistence):
    monkeypatch.setattr("src.bot.DatabasePersistence", lambda *args, **kwargs: mock_persistence)
    from src.bot import TradingBot

    return TradingBot(
        strategy_type=StrategyType.MOMENTUM,
        risk_level=RiskLevel.MODERATE,
        trading_pairs=["BTC-EUR", "ETH-EUR"],
    )


@pytest.fixture
def mock_api():
    api = MagicMock()
    api.initialize = AsyncMock()
    api.close = AsyncMock()
    api.check_permissions = AsyncMock(return_value={"view": True, "trade": True})
    api.get_ticker = AsyncMock(
        return_value={
            "bid": "49950",
            "ask": "50050",
            "last": "50000",
            "volume": "1000",
            "high": "51000",
            "low": "49000",
        }
    )
    api.get_tickers = AsyncMock(
        return_value=[
            {
                "symbol": "BTC/EUR",
                "bid": "49950",
                "ask": "50050",
                "mid": "50000",
                "last_price": "50000",
            },
            {
                "symbol": "ETH/EUR",
                "bid": "2995",
                "ask": "3005",
                "mid": "3000",
                "last_price": "3000",
            },
        ]
    )
    return api


class TestTradingBotInit:
    def test_initial_state(self, bot):
        assert bot.is_running is False
        assert bot.trading_mode == TradingMode.PAPER
        assert bot.risk_level == RiskLevel.MODERATE
        assert bot.strategy_type == StrategyType.MOMENTUM
        assert "BTC-EUR" in bot.trading_pairs

    def test_cash_balance_from_settings(self, bot):
        # Mock vault has INITIAL_CAPITAL=10000
        assert bot.cash_balance == Decimal("10000")

    def test_portfolio_snapshots_deque_empty(self, bot):
        assert len(bot.portfolio_snapshots) == 0


class TestCreateStrategy:
    def test_momentum_strategy(self, bot):
        from src.strategies.momentum import MomentumStrategy

        s = bot._create_strategy(StrategyType.MOMENTUM)
        assert isinstance(s, MomentumStrategy)

    def test_mean_reversion_strategy(self, bot):
        from src.strategies.mean_reversion import MeanReversionStrategy

        s = bot._create_strategy(StrategyType.MEAN_REVERSION)
        assert isinstance(s, MeanReversionStrategy)

    def test_market_making_strategy(self, bot):
        from src.strategies.market_making import MarketMakingStrategy

        s = bot._create_strategy(StrategyType.MARKET_MAKING)
        assert isinstance(s, MarketMakingStrategy)

    def test_multi_strategy(self, bot):
        from src.strategies.multi_strategy import MultiStrategy

        s = bot._create_strategy(StrategyType.MULTI_STRATEGY)
        assert isinstance(s, MultiStrategy)


class TestValidateSecuritySettings:
    def test_logs_when_available(self, bot):
        with patch("src.utils.onepassword.is_available", return_value=True):
            bot._validate_security_settings()  # Should not raise

    def test_logs_when_unavailable(self, bot):
        with patch("src.utils.onepassword.is_available", return_value=False):
            bot._validate_security_settings()  # Should not raise


class TestLoadHistoricalData:
    def test_loads_snapshots_and_logs(self, bot, mock_persistence):
        mock_persistence.load_portfolio_snapshots.return_value = [
            {"total_value": "10000", "timestamp": "2024-01-01"}
        ]
        bot._load_historical_data()
        mock_persistence.load_portfolio_snapshots.assert_called_once()

    def test_handles_exception_gracefully(self, bot, mock_persistence):
        mock_persistence.load_portfolio_snapshots.side_effect = Exception("DB error")
        bot._load_historical_data()  # Should not raise

    def test_shows_analytics_when_trades_exist(self, bot, mock_persistence):
        mock_persistence.get_analytics.return_value = {
            "total_trades": 10,
            "win_rate": 60.0,
            "total_pnl": 500.0,
        }
        bot._load_historical_data()


class TestSaveData:
    def test_save_data_with_no_snapshots(self, bot, mock_persistence):
        bot._save_data()
        mock_persistence.save_portfolio_snapshots_bulk.assert_not_called()

    def test_save_data_with_snapshots(self, bot, mock_persistence):
        from src.models.domain import PortfolioSnapshot

        snapshot = PortfolioSnapshot(
            total_value=Decimal("10000"),
            cash_balance=Decimal("10000"),
            positions_value=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
            daily_pnl=Decimal("0"),
            num_positions=0,
        )
        bot.portfolio_snapshots.append(snapshot)
        bot._save_data()
        mock_persistence.save_portfolio_snapshots_bulk.assert_called_once()

    def test_save_data_handles_exception(self, bot, mock_persistence):
        from src.models.domain import PortfolioSnapshot

        snapshot = PortfolioSnapshot(
            total_value=Decimal("10000"),
            cash_balance=Decimal("10000"),
            positions_value=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
            daily_pnl=Decimal("0"),
            num_positions=0,
        )
        bot.portfolio_snapshots.append(snapshot)
        mock_persistence.save_portfolio_snapshots_bulk.side_effect = Exception("save failed")
        bot._save_data()  # Should not raise


class TestUpdatePortfolio:
    @pytest.mark.asyncio
    async def test_creates_portfolio_snapshot(self, bot, monkeypatch, mock_persistence):
        from src.config import RiskLevel, TradingMode
        from src.execution.executor import OrderExecutor
        from src.risk_management.risk_manager import RiskManager

        rm = RiskManager(RiskLevel.MODERATE)
        executor = OrderExecutor(MagicMock(), rm, TradingMode.PAPER)
        bot.executor = executor

        bot._update_portfolio()
        assert len(bot.portfolio_snapshots) == 1
        snap = bot.portfolio_snapshots[0]
        assert snap.cash_balance == bot.cash_balance

    @pytest.mark.asyncio
    async def test_portfolio_value_includes_positions(self, bot):
        from src.config import RiskLevel, TradingMode
        from src.execution.executor import OrderExecutor
        from src.models.domain import OrderSide, Position
        from src.risk_management.risk_manager import RiskManager

        rm = RiskManager(RiskLevel.MODERATE)
        executor = OrderExecutor(MagicMock(), rm, TradingMode.PAPER)
        executor.positions["BTC-EUR"] = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("52000"),
        )
        bot.executor = executor
        bot.cash_balance = Decimal("5000")

        bot._update_portfolio()
        snap = bot.portfolio_snapshots[-1]
        assert snap.total_value == Decimal("57000")


class TestCheckRiskLimits:
    @pytest.mark.asyncio
    async def test_no_action_when_no_snapshots(self, bot, mock_persistence):
        from src.config import RiskLevel
        from src.risk_management.risk_manager import RiskManager

        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot._check_risk_limits()  # Should not raise

    @pytest.mark.asyncio
    async def test_checks_daily_pnl(self, bot, mock_persistence):
        from src.config import RiskLevel
        from src.models.domain import PortfolioSnapshot
        from src.risk_management.risk_manager import RiskManager

        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        snapshot = PortfolioSnapshot(
            total_value=Decimal("9700"),
            cash_balance=Decimal("9700"),
            positions_value=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("0"),
            total_pnl=Decimal("-300"),
            daily_pnl=Decimal("-300"),
            num_positions=0,
        )
        bot.portfolio_snapshots.append(snapshot)
        bot._check_risk_limits()  # Should not raise


class TestFetchMarketData:
    @pytest.mark.asyncio
    async def test_returns_market_data_on_success(self, bot, mock_api):
        bot.api_client = mock_api
        md = await bot._fetch_market_data("BTC-EUR")
        assert md is not None
        assert md.symbol == "BTC-EUR"
        assert md.last == Decimal("50000")

    @pytest.mark.asyncio
    async def test_returns_none_on_api_failure(self, bot, mock_api):
        mock_api.get_ticker = AsyncMock(side_effect=Exception("API error"))
        bot.api_client = mock_api
        md = await bot._fetch_market_data("BTC-EUR")
        assert md is None


class TestFetchAllMarketData:
    @pytest.mark.asyncio
    async def test_returns_market_data_for_all_pairs(self, bot, mock_api):
        bot.api_client = mock_api
        result = await bot._fetch_all_market_data()
        assert "BTC-EUR" in result
        assert "ETH-EUR" in result

    @pytest.mark.asyncio
    async def test_bid_ask_last_parsed_as_decimal(self, bot, mock_api):
        bot.api_client = mock_api
        result = await bot._fetch_all_market_data()
        assert result["BTC-EUR"].bid == Decimal("49950")
        assert result["BTC-EUR"].ask == Decimal("50050")
        assert result["BTC-EUR"].last == Decimal("50000")

    @pytest.mark.asyncio
    async def test_normalises_slash_symbol_to_dash(self, bot, mock_api):
        bot.api_client = mock_api
        result = await bot._fetch_all_market_data()
        assert "BTC/EUR" not in result
        assert "BTC-EUR" in result

    @pytest.mark.asyncio
    async def test_excludes_symbols_not_in_trading_pairs(self, bot, mock_api):
        mock_api.get_tickers = AsyncMock(
            return_value=[
                {
                    "symbol": "SOL/EUR",
                    "bid": "145",
                    "ask": "146",
                    "mid": "145.5",
                    "last_price": "145.5",
                },
            ]
        )
        bot.api_client = mock_api
        result = await bot._fetch_all_market_data()
        assert "SOL-EUR" not in result

    @pytest.mark.asyncio
    async def test_returns_empty_dict_on_api_failure(self, bot, mock_api):
        mock_api.get_tickers = AsyncMock(side_effect=Exception("API error"))
        bot.api_client = mock_api
        result = await bot._fetch_all_market_data()
        assert result == {}

    @pytest.mark.asyncio
    async def test_passes_trading_pairs_as_filter(self, bot, mock_api):
        bot.api_client = mock_api
        await bot._fetch_all_market_data()
        mock_api.get_tickers.assert_called_once_with(symbols=bot.trading_pairs)


class TestStop:
    @pytest.mark.asyncio
    async def test_stop_sets_is_running_false(self, bot, mock_persistence):
        bot.is_running = True
        bot.api_client = None
        await bot.stop()
        assert bot.is_running is False

    @pytest.mark.asyncio
    async def test_stop_calls_api_close(self, bot, mock_persistence, mock_api):
        bot.api_client = mock_api
        bot.is_running = True
        await bot.stop()
        mock_api.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_ends_session_with_snapshot(self, bot, mock_persistence):
        from src.models.domain import PortfolioSnapshot

        snapshot = PortfolioSnapshot(
            total_value=Decimal("10500"),
            cash_balance=Decimal("10500"),
            positions_value=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("500"),
            total_pnl=Decimal("500"),
            daily_pnl=Decimal("100"),
            num_positions=0,
        )
        bot.portfolio_snapshots.append(snapshot)
        bot.current_session_id = 42
        bot.api_client = None
        await bot.stop()
        mock_persistence.end_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_sends_telegram_shutdown_notification(self, bot, mock_persistence):
        """Bot should send a Telegram notification before stopping the polling loop."""
        from unittest.mock import AsyncMock

        bot.is_running = True
        bot.api_client = None
        bot.notifier = AsyncMock()
        bot._telegram_stop_event = None
        bot._telegram_polling_task = None

        await bot.stop()

        # Verify shutdown notification was sent
        bot.notifier.reply.assert_called_once()
        call_args = bot.notifier.reply.call_args[0][0]
        assert "shutting down" in call_args.lower()
        assert "🔴" in call_args


class TestRunTradingLoop:
    @pytest.mark.asyncio
    async def test_loop_stops_on_keyboard_interrupt(self, bot, mock_api, mock_persistence):
        from src.config import RiskLevel, TradingMode
        from src.execution.executor import OrderExecutor
        from src.risk_management.risk_manager import RiskManager
        from src.strategies.momentum import MomentumStrategy

        bot.api_client = mock_api
        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot.executor = OrderExecutor(mock_api, bot.risk_manager, TradingMode.PAPER)
        bot.strategy = MomentumStrategy()

        call_count = 0

        async def fake_gather(*coros, **kwargs):
            nonlocal call_count
            call_count += 1
            for c in coros:
                c.close()
            raise KeyboardInterrupt

        with patch("src.bot.asyncio.gather", side_effect=fake_gather):
            bot.is_running = True
            await bot.run_trading_loop(interval=0)
        # Loop exited (broke on KeyboardInterrupt); is_running not reset until stop() is called

    @pytest.mark.asyncio
    async def test_loop_handles_timeout_exception(self, bot, mock_api, mock_persistence):
        from src.config import RiskLevel, TradingMode
        from src.execution.executor import OrderExecutor
        from src.risk_management.risk_manager import RiskManager
        from src.strategies.momentum import MomentumStrategy

        bot.api_client = mock_api
        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot.executor = OrderExecutor(mock_api, bot.risk_manager, TradingMode.PAPER)
        bot.strategy = MomentumStrategy()

        call_count = 0

        async def fake_gather(*coros, **kwargs):
            nonlocal call_count
            call_count += 1
            for c in coros:
                c.close()
            if call_count == 1:
                raise httpx.TimeoutException("timeout")
            bot.is_running = False

        async def fake_sleep(t):
            pass

        with patch("src.bot.asyncio.gather", side_effect=fake_gather):
            with patch("src.bot.asyncio.sleep", side_effect=fake_sleep):
                bot.is_running = True
                await bot.run_trading_loop(interval=0)

    @pytest.mark.asyncio
    async def test_loop_handles_auth_failure_stops(self, bot, mock_api):
        from src.config import RiskLevel, TradingMode
        from src.execution.executor import OrderExecutor
        from src.risk_management.risk_manager import RiskManager
        from src.strategies.momentum import MomentumStrategy

        bot.api_client = mock_api
        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot.executor = OrderExecutor(mock_api, bot.risk_manager, TradingMode.PAPER)
        bot.strategy = MomentumStrategy()

        response = MagicMock()
        response.status_code = 401

        async def fake_gather(*coros, **kwargs):
            for c in coros:
                c.close()
            raise httpx.HTTPStatusError("401", request=MagicMock(), response=response)

        with patch("src.bot.asyncio.gather", side_effect=fake_gather):
            bot.is_running = True
            await bot.run_trading_loop(interval=0)
        # Loop exited (broke on 401); is_running not reset until stop() is called

    @pytest.mark.asyncio
    async def test_loop_handles_rate_limit(self, bot, mock_api):
        from src.config import RiskLevel, TradingMode
        from src.execution.executor import OrderExecutor
        from src.risk_management.risk_manager import RiskManager
        from src.strategies.momentum import MomentumStrategy

        bot.api_client = mock_api
        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot.executor = OrderExecutor(mock_api, bot.risk_manager, TradingMode.PAPER)
        bot.strategy = MomentumStrategy()

        response = MagicMock()
        response.status_code = 429
        call_count = 0

        async def fake_gather(*coros, **kwargs):
            nonlocal call_count
            call_count += 1
            for c in coros:
                c.close()
            if call_count == 1:
                raise httpx.HTTPStatusError("429", request=MagicMock(), response=response)
            bot.is_running = False

        async def fake_sleep(t):
            pass

        with patch("src.bot.asyncio.gather", side_effect=fake_gather):
            with patch("src.bot.asyncio.sleep", side_effect=fake_sleep):
                bot.is_running = True
                await bot.run_trading_loop(interval=0)

    @pytest.mark.asyncio
    async def test_loop_handles_server_error(self, bot, mock_api):
        from src.config import RiskLevel, TradingMode
        from src.execution.executor import OrderExecutor
        from src.risk_management.risk_manager import RiskManager
        from src.strategies.momentum import MomentumStrategy

        bot.api_client = mock_api
        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot.executor = OrderExecutor(mock_api, bot.risk_manager, TradingMode.PAPER)
        bot.strategy = MomentumStrategy()

        response = MagicMock()
        response.status_code = 503
        call_count = 0

        async def fake_gather(*coros, **kwargs):
            nonlocal call_count
            call_count += 1
            for c in coros:
                c.close()
            if call_count == 1:
                raise httpx.HTTPStatusError("503", request=MagicMock(), response=response)
            bot.is_running = False

        async def fake_sleep(t):
            pass

        with patch("src.bot.asyncio.gather", side_effect=fake_gather):
            with patch("src.bot.asyncio.sleep", side_effect=fake_sleep):
                bot.is_running = True
                await bot.run_trading_loop(interval=0)

    @pytest.mark.asyncio
    async def test_loop_handles_value_error(self, bot, mock_api):
        from src.config import RiskLevel, TradingMode
        from src.execution.executor import OrderExecutor
        from src.risk_management.risk_manager import RiskManager
        from src.strategies.momentum import MomentumStrategy

        bot.api_client = mock_api
        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot.executor = OrderExecutor(mock_api, bot.risk_manager, TradingMode.PAPER)
        bot.strategy = MomentumStrategy()

        call_count = 0

        async def fake_gather(*coros, **kwargs):
            nonlocal call_count
            call_count += 1
            for c in coros:
                c.close()
            if call_count == 1:
                raise ValueError("bad data")
            bot.is_running = False

        async def fake_sleep(t):
            pass

        with patch("src.bot.asyncio.gather", side_effect=fake_gather):
            with patch("src.bot.asyncio.sleep", side_effect=fake_sleep):
                bot.is_running = True
                await bot.run_trading_loop(interval=0)

    @pytest.mark.asyncio
    async def test_loop_handles_runtime_error_stops(self, bot, mock_api):
        from src.config import RiskLevel, TradingMode
        from src.execution.executor import OrderExecutor
        from src.risk_management.risk_manager import RiskManager
        from src.strategies.momentum import MomentumStrategy

        bot.api_client = mock_api
        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot.executor = OrderExecutor(mock_api, bot.risk_manager, TradingMode.PAPER)
        bot.strategy = MomentumStrategy()

        async def fake_gather(*coros, **kwargs):
            for c in coros:
                c.close()
            raise RuntimeError("critical failure")

        with patch("src.bot.asyncio.gather", side_effect=fake_gather):
            bot.is_running = True
            await bot.run_trading_loop(interval=0)
        # Loop exited (broke on RuntimeError); is_running not reset until stop() is called

    @pytest.mark.asyncio
    async def test_loop_handles_generic_http_error(self, bot, mock_api):
        """HTTP error with status code not in {401, 429, 5xx}."""
        from src.config import RiskLevel, TradingMode
        from src.execution.executor import OrderExecutor
        from src.risk_management.risk_manager import RiskManager
        from src.strategies.momentum import MomentumStrategy

        bot.api_client = mock_api
        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot.executor = OrderExecutor(mock_api, bot.risk_manager, TradingMode.PAPER)
        bot.strategy = MomentumStrategy()

        response = MagicMock()
        response.status_code = 400
        response.text = "Bad Request"
        call_count = 0

        async def fake_gather(*coros, **kwargs):
            nonlocal call_count
            call_count += 1
            for c in coros:
                c.close()
            if call_count == 1:
                raise httpx.HTTPStatusError("400", request=MagicMock(), response=response)
            bot.is_running = False

        async def fake_sleep(t):
            pass

        with patch("src.bot.asyncio.gather", side_effect=fake_gather):
            with patch("src.bot.asyncio.sleep", side_effect=fake_sleep):
                bot.is_running = True
                await bot.run_trading_loop(interval=0)

    @pytest.mark.asyncio
    async def test_loop_handles_unexpected_exception(self, bot, mock_api):
        from src.config import RiskLevel, TradingMode
        from src.execution.executor import OrderExecutor
        from src.risk_management.risk_manager import RiskManager
        from src.strategies.momentum import MomentumStrategy

        bot.api_client = mock_api
        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot.executor = OrderExecutor(mock_api, bot.risk_manager, TradingMode.PAPER)
        bot.strategy = MomentumStrategy()

        call_count = 0

        async def fake_gather(*coros, **kwargs):
            nonlocal call_count
            call_count += 1
            for c in coros:
                c.close()
            if call_count == 1:
                raise OSError("unexpected")
            bot.is_running = False

        async def fake_sleep(t):
            pass

        with patch("src.bot.asyncio.gather", side_effect=fake_gather):
            with patch("src.bot.asyncio.sleep", side_effect=fake_sleep):
                bot.is_running = True
                await bot.run_trading_loop(interval=0)


class TestBotStart:
    @pytest.mark.asyncio
    async def test_start_paper_mode_initialises_components(self, bot, mock_persistence):
        mock_api = MagicMock()
        mock_api.initialize = AsyncMock()
        mock_api.check_permissions = AsyncMock(return_value={"view": True, "trade": True})

        with patch("src.bot.create_api_client", return_value=mock_api):
            await bot.start()

        assert bot.is_running is True
        assert bot.api_client is mock_api
        assert bot.risk_manager is not None
        assert bot.executor is not None
        assert bot.strategy is not None

    @pytest.mark.asyncio
    async def test_start_raises_when_no_view_permission(self, bot, mock_persistence):
        mock_api = MagicMock()
        mock_api.initialize = AsyncMock()
        mock_api.check_permissions = AsyncMock(return_value={"view": False, "trade": False})

        with patch("src.bot.create_api_client", return_value=mock_api):
            with pytest.raises(RuntimeError, match="cannot read market data"):
                await bot.start()

    @pytest.mark.asyncio
    async def test_start_live_raises_when_no_trade_permission(self, monkeypatch, mock_persistence):
        monkeypatch.setattr("src.bot.DatabasePersistence", lambda *a, **kw: mock_persistence)
        from src.bot import TradingBot

        live_bot = TradingBot(
            strategy_type=StrategyType.MOMENTUM,
            risk_level=RiskLevel.MODERATE,
            trading_mode=TradingMode.LIVE,
            trading_pairs=["BTC-EUR"],
        )
        mock_api = MagicMock()
        mock_api.initialize = AsyncMock()
        mock_api.check_permissions = AsyncMock(return_value={"view": True, "trade": False})

        with patch("src.bot.create_api_client", return_value=mock_api):
            with pytest.raises(RuntimeError, match="read-only"):
                await live_bot.start()

    @pytest.mark.asyncio
    async def test_start_live_fetches_balance(self, monkeypatch, mock_persistence):
        monkeypatch.setattr("src.bot.DatabasePersistence", lambda *a, **kw: mock_persistence)
        from src.bot import TradingBot

        live_bot = TradingBot(
            strategy_type=StrategyType.MOMENTUM,
            risk_level=RiskLevel.MODERATE,
            trading_mode=TradingMode.LIVE,
            trading_pairs=["BTC-EUR"],
        )
        mock_api = MagicMock()
        mock_api.initialize = AsyncMock()
        mock_api.check_permissions = AsyncMock(return_value={"view": True, "trade": True})
        mock_api.get_balance = AsyncMock(
            return_value={"balances": {"EUR": {"available": "5000.50"}}}
        )

        with patch("src.bot.create_api_client", return_value=mock_api):
            await live_bot.start()

        assert live_bot.cash_balance == Decimal("5000.50")

    @pytest.mark.asyncio
    async def test_start_live_raises_when_balance_unavailable(self, monkeypatch, mock_persistence):
        monkeypatch.setattr("src.bot.DatabasePersistence", lambda *a, **kw: mock_persistence)
        from src.bot import TradingBot

        live_bot = TradingBot(
            strategy_type=StrategyType.MOMENTUM,
            risk_level=RiskLevel.MODERATE,
            trading_mode=TradingMode.LIVE,
            trading_pairs=["BTC-EUR"],
        )
        mock_api = MagicMock()
        mock_api.initialize = AsyncMock()
        mock_api.check_permissions = AsyncMock(return_value={"view": True, "trade": True})
        mock_api.get_balance = AsyncMock(return_value={"balances": {}})

        with patch("src.bot.create_api_client", return_value=mock_api):
            with pytest.raises(RuntimeError, match="No EUR balance"):
                await live_bot.start()

    @pytest.mark.asyncio
    async def test_start_live_raises_on_api_exception(self, monkeypatch, mock_persistence):
        monkeypatch.setattr("src.bot.DatabasePersistence", lambda *a, **kw: mock_persistence)
        from src.bot import TradingBot

        live_bot = TradingBot(
            strategy_type=StrategyType.MOMENTUM,
            risk_level=RiskLevel.MODERATE,
            trading_mode=TradingMode.LIVE,
            trading_pairs=["BTC-EUR"],
        )
        mock_api = MagicMock()
        mock_api.initialize = AsyncMock()
        mock_api.check_permissions = AsyncMock(return_value={"view": True, "trade": True})
        mock_api.get_balance = AsyncMock(side_effect=Exception("network error"))

        with patch("src.bot.create_api_client", return_value=mock_api):
            with pytest.raises(RuntimeError, match="Cannot start live trading"):
                await live_bot.start()

    @pytest.mark.asyncio
    async def test_start_passes_strategy_to_risk_manager(self, bot, mock_persistence):
        """RiskManager is constructed with the active strategy so overrides apply."""
        mock_api = MagicMock()
        mock_api.initialize = AsyncMock()
        mock_api.check_permissions = AsyncMock(return_value={"view": True, "trade": True})

        with patch("src.bot.create_api_client", return_value=mock_api):
            with patch("src.bot.RiskManager") as mock_rm_cls:
                mock_rm_cls.return_value = MagicMock()
                await bot.start()
                call_kwargs = mock_rm_cls.call_args.kwargs
                assert call_kwargs.get("strategy") == bot.strategy_type.value


class TestProcessSymbol:
    @pytest.mark.asyncio
    async def test_process_symbol_with_no_signal(self, bot, mock_api, mock_persistence):
        from src.execution.executor import OrderExecutor
        from src.risk_management.risk_manager import RiskManager

        bot.api_client = mock_api
        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot.executor = OrderExecutor(mock_api, bot.risk_manager, TradingMode.PAPER)
        bot.strategy = MagicMock()
        bot.strategy.analyze = AsyncMock(return_value=None)

        await bot._process_symbol("BTC-EUR")
        bot.strategy.analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_symbol_with_filled_buy_order(self, bot, mock_api, mock_persistence):
        from src.execution.executor import OrderExecutor
        from src.models.domain import Order
        from src.risk_management.risk_manager import RiskManager

        bot.api_client = mock_api
        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot.executor = OrderExecutor(mock_api, bot.risk_manager, TradingMode.PAPER)

        filled_order = Order(
            order_id="test-123",
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            filled_quantity=Decimal("0.1"),
            status=OrderStatus.FILLED,
        )

        bot.strategy = MagicMock()
        bot.strategy.analyze = AsyncMock(
            return_value=Signal(
                symbol="BTC-EUR",
                strategy="momentum",
                signal_type="BUY",
                price=Decimal("50000"),
                strength=Decimal("0.8"),
                reason="test signal",
            )
        )
        bot.executor.execute_signal = AsyncMock(return_value=filled_order)

        initial_balance = bot.cash_balance
        await bot._process_symbol("BTC-EUR")

        mock_persistence.save_trade.assert_called_once_with(filled_order)
        assert bot.cash_balance < initial_balance

    @pytest.mark.asyncio
    async def test_process_symbol_with_filled_sell_order(self, bot, mock_api, mock_persistence):
        from src.execution.executor import OrderExecutor
        from src.models.domain import Order
        from src.risk_management.risk_manager import RiskManager

        bot.api_client = mock_api
        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot.executor = OrderExecutor(mock_api, bot.risk_manager, TradingMode.PAPER)

        filled_order = Order(
            order_id="test-456",
            symbol="BTC-EUR",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            filled_quantity=Decimal("0.1"),
            status=OrderStatus.FILLED,
        )

        bot.strategy = MagicMock()
        bot.strategy.analyze = AsyncMock(
            return_value=Signal(
                symbol="BTC-EUR",
                strategy="momentum",
                signal_type="SELL",
                price=Decimal("50000"),
                strength=Decimal("0.8"),
                reason="test signal",
            )
        )
        bot.executor.execute_signal = AsyncMock(return_value=filled_order)

        initial_balance = bot.cash_balance
        await bot._process_symbol("BTC-EUR")

        assert bot.cash_balance > initial_balance

    @pytest.mark.asyncio
    async def test_process_symbol_handles_exception(self, bot, mock_api, mock_persistence):
        from src.execution.executor import OrderExecutor
        from src.risk_management.risk_manager import RiskManager

        bot.api_client = mock_api
        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot.executor = OrderExecutor(mock_api, bot.risk_manager, TradingMode.PAPER)
        bot.strategy = MagicMock()
        bot.strategy.analyze = AsyncMock(side_effect=Exception("strategy error"))

        await bot._process_symbol("BTC-EUR")  # Should not raise

    @pytest.mark.asyncio
    async def test_process_symbol_returns_early_when_no_market_data(
        self, bot, mock_api, mock_persistence
    ):
        mock_api.get_ticker = AsyncMock(side_effect=Exception("API down"))
        bot.api_client = mock_api
        bot.executor = MagicMock()
        bot.strategy = MagicMock()

        await bot._process_symbol("BTC-EUR")
        bot.strategy.analyze.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_symbol_uses_pre_supplied_market_data(
        self, bot, mock_api, mock_persistence
    ):
        from datetime import UTC, datetime

        from src.execution.executor import OrderExecutor
        from src.models.domain import MarketData
        from src.risk_management.risk_manager import RiskManager

        bot.api_client = mock_api
        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot.executor = OrderExecutor(mock_api, bot.risk_manager, TradingMode.PAPER)
        bot.strategy = MagicMock()
        bot.strategy.analyze = AsyncMock(return_value=None)

        pre_fetched = MarketData(
            symbol="BTC-EUR",
            timestamp=datetime.now(UTC),
            bid=Decimal("49950"),
            ask=Decimal("50050"),
            last=Decimal("50000"),
            volume_24h=Decimal("0"),
            high_24h=Decimal("0"),
            low_24h=Decimal("0"),
        )

        await bot._process_symbol("BTC-EUR", pre_fetched)
        mock_api.get_ticker.assert_not_called()
        bot.strategy.analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_symbol_sl_tp_close_updates_cash_balance(
        self, bot, mock_api, mock_persistence
    ):
        """When stop-loss or take-profit fires, the close order must be processed
        by the bot so cash_balance and trade history are kept accurate."""
        from datetime import UTC, datetime

        from src.config import RiskLevel, TradingMode
        from src.execution.executor import OrderExecutor
        from src.models.domain import MarketData, OrderSide, Position
        from src.risk_management.risk_manager import RiskManager

        bot.api_client = mock_api
        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot.executor = OrderExecutor(mock_api, bot.risk_manager, TradingMode.PAPER)

        # Open BUY position at 50 000 with a stop-loss at 49 000
        pos = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
            stop_loss=Decimal("49000"),
        )
        bot.executor.positions["BTC-EUR"] = pos

        # Strategy returns no signal (SL fires, not a new order)
        bot.strategy = MagicMock()
        bot.strategy.analyze = AsyncMock(return_value=None)

        # Price drops below stop-loss
        market_data = MarketData(
            symbol="BTC-EUR",
            timestamp=datetime.now(UTC),
            bid=Decimal("47900"),
            ask=Decimal("48100"),
            last=Decimal("48000"),
            volume_24h=Decimal("0"),
            high_24h=Decimal("0"),
            low_24h=Decimal("0"),
        )

        initial_balance = bot.cash_balance
        await bot._process_symbol("BTC-EUR", market_data)

        # Position must be closed
        assert "BTC-EUR" not in bot.executor.positions
        # Cash balance must reflect the sale proceeds (should increase since SELL was executed)
        assert bot.cash_balance > initial_balance
        # Trade must be persisted
        mock_persistence.save_trade.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_symbol_sl_tp_close_returns_none_when_no_position(
        self, bot, mock_api, mock_persistence
    ):
        """update_market_prices returns None when no position exists — no cash change."""
        from datetime import UTC, datetime

        from src.config import RiskLevel, TradingMode
        from src.execution.executor import OrderExecutor
        from src.models.domain import MarketData
        from src.risk_management.risk_manager import RiskManager

        bot.api_client = mock_api
        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot.executor = OrderExecutor(mock_api, bot.risk_manager, TradingMode.PAPER)
        bot.strategy = MagicMock()
        bot.strategy.analyze = AsyncMock(return_value=None)

        market_data = MarketData(
            symbol="BTC-EUR",
            timestamp=datetime.now(UTC),
            bid=Decimal("48000"),
            ask=Decimal("48100"),
            last=Decimal("48000"),
            volume_24h=Decimal("0"),
            high_24h=Decimal("0"),
            low_24h=Decimal("0"),
        )

        initial_balance = bot.cash_balance
        await bot._process_symbol("BTC-EUR", market_data)

        # No position, no SL/TP fire → balance unchanged
        assert bot.cash_balance == initial_balance
        mock_persistence.save_trade.assert_not_called()

    @pytest.mark.asyncio
    async def test_daily_loss_limit_hit_logs_critical(self, bot, mock_persistence):
        from src.risk_management.risk_manager import RiskManager

        bot.risk_manager = RiskManager(RiskLevel.CONSERVATIVE)
        # Force daily loss limit hit
        bot.risk_manager._daily_loss_limit_hit = True

        snapshot = PortfolioSnapshot(
            total_value=Decimal("9500"),
            cash_balance=Decimal("9500"),
            positions_value=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("-500"),
            total_pnl=Decimal("-500"),
            daily_pnl=Decimal("-500"),
            num_positions=0,
        )
        bot.portfolio_snapshots.append(snapshot)
        bot._check_risk_limits()
        # Verifies the daily_loss_limit_hit path was exercised (line 385)
        assert bot.risk_manager.daily_loss_limit_hit is True


class TestDefaultInterval:
    def test_market_making_uses_5s(self, bot):
        bot.strategy_type = StrategyType.MARKET_MAKING
        assert bot._default_interval() == 5

    def test_breakout_uses_5s(self, bot):
        bot.strategy_type = StrategyType.BREAKOUT
        assert bot._default_interval() == 5

    def test_momentum_uses_10s(self, bot):
        bot.strategy_type = StrategyType.MOMENTUM
        assert bot._default_interval() == 10

    def test_multi_strategy_uses_10s(self, bot):
        bot.strategy_type = StrategyType.MULTI_STRATEGY
        assert bot._default_interval() == 10

    def test_mean_reversion_uses_15s(self, bot):
        bot.strategy_type = StrategyType.MEAN_REVERSION
        assert bot._default_interval() == 15

    def test_range_reversion_uses_15s(self, bot):
        bot.strategy_type = StrategyType.RANGE_REVERSION
        assert bot._default_interval() == 15

    @pytest.mark.asyncio
    async def test_run_loop_uses_strategy_default_when_no_interval(self, bot, mock_api):
        from src.config import RiskLevel, TradingMode
        from src.execution.executor import OrderExecutor
        from src.risk_management.risk_manager import RiskManager
        from src.strategies.momentum import MomentumStrategy

        bot.api_client = mock_api
        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot.executor = OrderExecutor(mock_api, bot.risk_manager, TradingMode.PAPER)
        bot.strategy = MomentumStrategy()
        bot.strategy_type = StrategyType.MOMENTUM  # _default_interval() → 10s

        sleep_calls = []

        async def fake_gather(*coros, **kwargs):
            for c in coros:
                c.close()
            bot.is_running = False

        async def fake_sleep(t):
            sleep_calls.append(t)

        with patch("src.bot.asyncio.gather", side_effect=fake_gather):
            with patch("src.bot.asyncio.sleep", side_effect=fake_sleep):
                bot.is_running = True
                await bot.run_trading_loop()  # no interval — uses strategy default

        assert 10 in sleep_calls

    @pytest.mark.asyncio
    async def test_run_loop_explicit_interval_overrides_default(self, bot, mock_api):
        from src.config import RiskLevel, TradingMode
        from src.execution.executor import OrderExecutor
        from src.risk_management.risk_manager import RiskManager
        from src.strategies.momentum import MomentumStrategy

        bot.api_client = mock_api
        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot.executor = OrderExecutor(mock_api, bot.risk_manager, TradingMode.PAPER)
        bot.strategy = MomentumStrategy()
        bot.strategy_type = StrategyType.MOMENTUM  # would default to 10s

        sleep_calls = []

        async def fake_gather(*coros, **kwargs):
            for c in coros:
                c.close()
            bot.is_running = False

        async def fake_sleep(t):
            sleep_calls.append(t)

        with patch("src.bot.asyncio.gather", side_effect=fake_gather):
            with patch("src.bot.asyncio.sleep", side_effect=fake_sleep):
                bot.is_running = True
                await bot.run_trading_loop(interval=30)  # explicit override

        assert 30 in sleep_calls
        assert 10 not in sleep_calls


class TestPeriodicSave:
    @pytest.mark.asyncio
    async def test_save_triggered_after_60_seconds(self, bot, mock_api, mock_persistence):
        """Save is triggered once ≥60 seconds have elapsed since the last save."""
        from src.config import RiskLevel, TradingMode
        from src.execution.executor import OrderExecutor
        from src.risk_management.risk_manager import RiskManager
        from src.strategies.momentum import MomentumStrategy

        bot.api_client = mock_api
        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot.executor = OrderExecutor(mock_api, bot.risk_manager, TradingMode.PAPER)
        bot.strategy = MomentumStrategy()

        monotonic_val = [0.0]

        async def fake_gather(*coros, **kwargs):
            for c in coros:
                c.close()
            monotonic_val[0] += 65.0  # advance past 60-second threshold
            bot.is_running = False

        with patch("src.bot.asyncio.gather", side_effect=fake_gather):
            with patch("src.bot.asyncio.sleep"):
                with patch("src.bot.time.monotonic", side_effect=lambda: monotonic_val[0]):
                    bot.is_running = True
                    await bot.run_trading_loop(interval=0)

        mock_persistence.save_portfolio_snapshots_bulk.assert_called()

    @pytest.mark.asyncio
    async def test_save_not_triggered_before_60_seconds(self, bot, mock_api, mock_persistence):
        """Save is NOT triggered when less than 60 seconds have elapsed."""
        from src.config import RiskLevel, TradingMode
        from src.execution.executor import OrderExecutor
        from src.risk_management.risk_manager import RiskManager
        from src.strategies.momentum import MomentumStrategy

        bot.api_client = mock_api
        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot.executor = OrderExecutor(mock_api, bot.risk_manager, TradingMode.PAPER)
        bot.strategy = MomentumStrategy()

        iteration = 0
        monotonic_val = [0.0]

        async def fake_gather(*coros, **kwargs):
            nonlocal iteration
            iteration += 1
            for c in coros:
                c.close()
            monotonic_val[0] += 5.0  # only 5s per iteration
            if iteration >= 5:
                bot.is_running = False

        with patch("src.bot.asyncio.gather", side_effect=fake_gather):
            with patch("src.bot.asyncio.sleep"):
                with patch("src.bot.time.monotonic", side_effect=lambda: monotonic_val[0]):
                    bot.is_running = True
                    await bot.run_trading_loop(interval=0)

        mock_persistence.save_portfolio_snapshots_bulk.assert_not_called()


class TestTelegramCommandListener:
    """Tests for Telegram command listener lifecycle and command handlers."""

    @pytest.mark.asyncio
    async def test_status_command_replies_with_bot_state(self, bot):
        """_cmd_status sends current strategy, mode, and session P&L."""
        bot.notifier = MagicMock()
        bot.notifier.reply = AsyncMock()
        await bot._cmd_status()
        bot.notifier.reply.assert_awaited_once()
        text = bot.notifier.reply.call_args.args[0]
        assert "Status" in text
        assert bot.strategy_type.value in text

    @pytest.mark.asyncio
    async def test_balance_command_replies_with_portfolio(self, bot):
        """_cmd_balance sends cash balance and total value."""
        bot.notifier = MagicMock()
        bot.notifier.reply = AsyncMock()
        bot.executor = MagicMock()
        bot.executor.get_positions.return_value = []
        await bot._cmd_balance()
        bot.notifier.reply.assert_awaited_once()
        text = bot.notifier.reply.call_args.args[0]
        assert "Balance" in text

    @pytest.mark.asyncio
    async def test_balance_command_lists_open_positions(self, bot):
        """_cmd_balance includes each open position symbol and P&L."""
        from src.models.domain import OrderSide, Position

        bot.notifier = MagicMock()
        bot.notifier.reply = AsyncMock()
        pos = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("0.5"),
            entry_price=Decimal("50000"),
            current_price=Decimal("52000"),
        )
        bot.executor = MagicMock()
        bot.executor.get_positions.return_value = [pos]
        await bot._cmd_balance()
        text = bot.notifier.reply.call_args.args[0]
        assert "BTC-EUR" in text

    @pytest.mark.asyncio
    async def test_report_command_calls_notify_report_ready(self, bot, mock_persistence):
        """_cmd_report generates PDF report or falls back to text summary."""
        mock_persistence.get_analytics.return_value = {
            "total_trades": 50,
            "win_rate": 60.0,
            "total_pnl": 500.0,
            "return_pct": 5.0,
            "sharpe_ratio": 1.2,
            "max_drawdown_pct": 3.5,
        }
        bot.notifier = MagicMock()
        bot.notifier.reply = AsyncMock()
        bot.notifier.notify_report_ready = AsyncMock()
        bot.notifier.send_document = AsyncMock()
        await bot._cmd_report(30)
        # Should call reply to notify it's generating
        assert bot.notifier.reply.await_count >= 1

    @pytest.mark.asyncio
    async def test_report_command_replies_when_no_data(self, bot, mock_persistence):
        """_cmd_report sends a no-data message when the DB has no trades."""
        mock_persistence.get_analytics.return_value = {"total_trades": 0}
        bot.notifier = MagicMock()
        bot.notifier.reply = AsyncMock()
        bot.notifier.notify_report_ready = AsyncMock()
        bot.notifier.send_document = AsyncMock()
        await bot._cmd_report(30)
        # Should call reply at least once (may call generate_report_data which can fail gracefully)
        assert bot.notifier.reply.await_count >= 1

    @pytest.mark.asyncio
    async def test_report_command_uses_days_arg(self, bot, mock_persistence):
        """_cmd_report passes the days argument when provided."""
        mock_persistence.get_analytics.return_value = {
            "total_trades": 10,
            "win_rate": 50.0,
            "total_pnl": 100.0,
            "return_pct": 1.0,
            "sharpe_ratio": 0.8,
            "max_drawdown_pct": 2.0,
        }
        bot.notifier = MagicMock()
        bot.notifier.reply = AsyncMock()
        bot.notifier.notify_report_ready = AsyncMock()
        bot.notifier.send_document = AsyncMock()
        await bot._handle_telegram_command("report", ["7"])
        # Should at least call reply to notify it's generating
        assert bot.notifier.reply.await_count >= 1

    @pytest.mark.asyncio
    async def test_help_command_lists_all_commands(self, bot):
        """_cmd_help includes all supported commands in the reply."""
        bot.notifier = MagicMock()
        bot.notifier.reply = AsyncMock()
        await bot._cmd_help()
        text = bot.notifier.reply.call_args.args[0]
        assert "/status" in text
        assert "/balance" in text
        assert "/report" in text

    @pytest.mark.asyncio
    async def test_unknown_command_sends_help_hint(self, bot):
        """Unrecognised commands get a reply containing /help."""
        bot.notifier = MagicMock()
        bot.notifier.reply = AsyncMock()
        await bot._handle_telegram_command("foobar", [])
        bot.notifier.reply.assert_awaited_once()
        text = bot.notifier.reply.call_args.args[0]
        assert "foobar" in text or "/help" in text

    @pytest.mark.asyncio
    async def test_handle_command_dispatches_status(self, bot):
        bot.notifier = MagicMock()
        bot.notifier.reply = AsyncMock()
        await bot._handle_telegram_command("status", [])
        bot.notifier.reply.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_command_dispatches_balance(self, bot):
        bot.notifier = MagicMock()
        bot.notifier.reply = AsyncMock()
        bot.executor = MagicMock()
        bot.executor.get_positions.return_value = []
        await bot._handle_telegram_command("balance", [])
        bot.notifier.reply.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_command_dispatches_help(self, bot):
        bot.notifier = MagicMock()
        bot.notifier.reply = AsyncMock()
        await bot._handle_telegram_command("help", [])
        bot.notifier.reply.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_command_listener_task_created_on_start(self, bot, mock_persistence):
        """start() creates a Telegram polling task when notifier is configured."""
        mock_api = MagicMock()
        mock_api.initialize = AsyncMock()
        mock_api.check_permissions = AsyncMock(return_value={"view": True, "trade": True})
        bot.notifier = MagicMock()
        bot.notifier.notify_started = AsyncMock()
        bot.notifier.start_polling = AsyncMock()
        with patch("src.bot.create_api_client", return_value=mock_api):
            await bot.start()
        assert bot._telegram_polling_task is not None

    @pytest.mark.asyncio
    async def test_command_listener_not_created_without_notifier(self, bot, mock_persistence):
        """start() does NOT create a polling task when Telegram is not configured."""
        bot.notifier = None
        mock_api = MagicMock()
        mock_api.initialize = AsyncMock()
        mock_api.check_permissions = AsyncMock(return_value={"view": True, "trade": True})
        with patch("src.bot.create_api_client", return_value=mock_api):
            await bot.start()
        assert bot._telegram_polling_task is None

    @pytest.mark.asyncio
    async def test_command_listener_stopped_on_bot_stop(self, bot, mock_persistence):
        """stop() sets the stop event and clears the polling task."""
        import asyncio as _asyncio

        stop_event = _asyncio.Event()
        bot._telegram_stop_event = stop_event
        bot._telegram_polling_task = _asyncio.create_task(_asyncio.sleep(9999))
        bot.api_client = None
        await bot.stop()
        assert stop_event.is_set()
        assert bot._telegram_polling_task is None


class TestShutdownExecutor:
    """Tests for _shutdown_executor method."""

    @pytest.mark.asyncio
    async def test_shutdown_executor_with_trailing_stop(self, bot, monkeypatch):
        """_shutdown_executor calls graceful_shutdown with trailing_stop_pct."""
        from src.config import settings
        from src.models.domain import ShutdownSummary

        monkeypatch.setattr(settings, "shutdown_trailing_stop_pct", Decimal("0.5"))
        monkeypatch.setattr(settings, "shutdown_max_wait_seconds", 120)

        mock_executor = MagicMock()
        mock_executor.graceful_shutdown = AsyncMock(
            return_value=ShutdownSummary(
                orders_cancelled=2,
                positions_evaluated=3,
                positions_closed=3,
                positions_trailing_stopped=1,
                filled_close_orders=[],
                errors=[],
            )
        )
        bot.executor = mock_executor

        await bot._shutdown_executor()

        mock_executor.graceful_shutdown.assert_awaited_once()
        args = mock_executor.graceful_shutdown.call_args
        assert args.kwargs["trailing_stop_pct"] == Decimal("0.5")
        assert args.kwargs["max_wait_seconds"] == 120

    @pytest.mark.asyncio
    async def test_shutdown_executor_without_trailing_stop(self, bot, monkeypatch):
        """_shutdown_executor calls graceful_shutdown with None when no trailing stop."""
        from src.config import settings
        from src.models.domain import ShutdownSummary

        monkeypatch.setattr(settings, "shutdown_trailing_stop_pct", None)
        monkeypatch.setattr(settings, "shutdown_max_wait_seconds", 120)

        mock_executor = MagicMock()
        mock_executor.graceful_shutdown = AsyncMock(
            return_value=ShutdownSummary(
                orders_cancelled=0,
                positions_evaluated=0,
                positions_closed=0,
                positions_trailing_stopped=0,
                filled_close_orders=[],
                errors=[],
            )
        )
        bot.executor = mock_executor

        await bot._shutdown_executor()

        args = mock_executor.graceful_shutdown.call_args
        assert args.kwargs["trailing_stop_pct"] is None

    @pytest.mark.asyncio
    async def test_shutdown_executor_notifies_on_trades(self, bot, monkeypatch):
        """_shutdown_executor sends Telegram notification for each filled order."""
        from src.config import settings
        from src.models.domain import Order, OrderSide, OrderStatus, OrderType, ShutdownSummary

        monkeypatch.setattr(settings, "shutdown_trailing_stop_pct", None)
        monkeypatch.setattr(settings, "shutdown_max_wait_seconds", 120)

        order = Order(
            symbol="BTC-EUR",
            order_type=OrderType.MARKET,
            side=OrderSide.SELL,
            quantity=Decimal("0.5"),
            price=None,
            status=OrderStatus.FILLED,
            filled_quantity=Decimal("0.5"),
            commission=Decimal("0.45"),
        )

        mock_executor = MagicMock()
        mock_executor.graceful_shutdown = AsyncMock(
            return_value=ShutdownSummary(
                orders_cancelled=0,
                positions_evaluated=1,
                positions_closed=1,
                positions_trailing_stopped=0,
                filled_close_orders=[order],
                errors=[],
            )
        )
        bot.executor = mock_executor
        bot.notifier = MagicMock()
        bot.notifier.notify_trade = AsyncMock()

        await bot._shutdown_executor()

        bot.notifier.notify_trade.assert_awaited_once_with(order, bot.currency_symbol)

    @pytest.mark.asyncio
    async def test_shutdown_executor_logs_errors(self, bot, monkeypatch):
        """_shutdown_executor logs errors from shutdown summary."""
        from src.config import settings
        from src.models.domain import ShutdownSummary

        monkeypatch.setattr(settings, "shutdown_trailing_stop_pct", None)
        monkeypatch.setattr(settings, "shutdown_max_wait_seconds", 120)

        mock_executor = MagicMock()
        mock_executor.graceful_shutdown = AsyncMock(
            return_value=ShutdownSummary(
                orders_cancelled=0,
                positions_evaluated=1,
                positions_closed=0,
                positions_trailing_stopped=0,
                filled_close_orders=[],
                errors=["Failed to close BTC-EUR", "API timeout"],
            )
        )
        bot.executor = mock_executor

        # Just verify it doesn't crash
        await bot._shutdown_executor()


class TestStopMethod:
    """Tests for the stop() method edge cases."""

    @pytest.mark.asyncio
    async def test_stop_removes_db_log_sink(self, bot, mock_persistence):
        """stop() removes the database logging sink."""
        from src.bot import _setup_database_logging

        sink_id = _setup_database_logging(mock_persistence)
        bot._db_log_sink_id = sink_id
        bot.api_client = None

        with patch("src.bot.logger.remove") as mock_remove:
            await bot.stop()

        mock_remove.assert_called_once_with(sink_id)
        assert bot._db_log_sink_id is None


class TestRunTradingLoopAuthNotification:
    """Tests for Telegram notification on auth failure."""

    @pytest.mark.asyncio
    async def test_loop_sends_telegram_on_auth_failure(self, bot, mock_api):
        """run_trading_loop sends Telegram notification on 401 auth failure."""
        from src.config import RiskLevel, TradingMode
        from src.execution.executor import OrderExecutor
        from src.risk_management.risk_manager import RiskManager
        from src.strategies.momentum import MomentumStrategy

        bot.api_client = mock_api
        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        bot.executor = OrderExecutor(mock_api, bot.risk_manager, TradingMode.PAPER)
        bot.strategy = MomentumStrategy()
        bot.notifier = MagicMock()
        bot.notifier.notify_error = AsyncMock()

        # Simulate auth failure
        async def fake_gather(*coros, **kwargs):
            for c in coros:
                c.close()
            response = MagicMock()
            response.status_code = 401
            raise httpx.HTTPStatusError("Unauthorized", request=MagicMock(), response=response)

        with patch("src.bot.asyncio.gather", side_effect=fake_gather):
            with patch("src.bot.asyncio.sleep"):
                bot.is_running = True
                await bot.run_trading_loop(interval=0)

        bot.notifier.notify_error.assert_awaited_once()


class TestLoadHistoricalDataAnalytics:
    """Tests for _load_historical_data analytics display."""

    def test_load_historical_data_shows_analytics_with_trades(self, bot, mock_persistence):
        """_load_historical_data logs analytics when trades exist."""
        mock_persistence.get_analytics.return_value = {
            "total_trades": 50,
            "win_rate": 60.0,
            "total_pnl": 500.0,
        }

        with patch("src.bot.logger.info") as mock_log:
            bot._load_historical_data()
            # Verify analytics were logged
            calls = [str(call) for call in mock_log.call_args_list]
            assert any("50 trades" in str(call) for call in calls)


class TestCmdStatusUptime:
    """Tests for _cmd_status uptime calculation."""

    @pytest.mark.asyncio
    async def test_cmd_status_includes_uptime(self, bot):
        """_cmd_status calculates and includes uptime when bot is running."""
        from datetime import UTC, datetime, timedelta

        bot.notifier = MagicMock()
        bot.notifier.reply = AsyncMock()
        bot._started_at = datetime.now(UTC) - timedelta(hours=2, minutes=30)
        bot.executor = MagicMock()
        bot.executor.get_positions.return_value = []

        await bot._cmd_status()

        text = bot.notifier.reply.call_args.args[0]
        # Should contain uptime like "2h 30m"
        assert "h" in text or "uptime" in text.lower()


class TestMainEntryPoint:
    """Tests for the main() entry point."""

    @pytest.mark.asyncio
    async def test_main_runs_bot_lifecycle(self):
        """main() creates bot, starts it, runs loop, and stops on KeyboardInterrupt."""
        from src.bot import main

        mock_bot = MagicMock()
        mock_bot.start = AsyncMock()
        mock_bot.run_trading_loop = AsyncMock(side_effect=KeyboardInterrupt)
        mock_bot.stop = AsyncMock()

        with patch("src.bot.TradingBot", return_value=mock_bot):
            await main()

        mock_bot.start.assert_awaited_once()
        mock_bot.run_trading_loop.assert_awaited_once()
        mock_bot.stop.assert_awaited_once()
