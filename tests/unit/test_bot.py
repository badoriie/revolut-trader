"""Unit tests for TradingBot orchestrator."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.config import RiskLevel, StrategyType, TradingMode


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
        trading_mode=TradingMode.PAPER,
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

        await bot._update_portfolio()
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

        await bot._update_portfolio()
        snap = bot.portfolio_snapshots[-1]
        assert snap.total_value == Decimal("57000")


class TestCheckRiskLimits:
    @pytest.mark.asyncio
    async def test_no_action_when_no_snapshots(self, bot, mock_persistence):
        from src.config import RiskLevel
        from src.risk_management.risk_manager import RiskManager

        bot.risk_manager = RiskManager(RiskLevel.MODERATE)
        await bot._check_risk_limits()  # Should not raise

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
        await bot._check_risk_limits()  # Should not raise


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
        bot.api_client = None
        await bot.stop()
        mock_persistence.end_session.assert_called_once()


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
