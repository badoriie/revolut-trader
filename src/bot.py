import asyncio
import time
from collections import deque
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from loguru import logger

from src.api import create_api_client
from src.api.client import RevolutAPIClient
from src.api.mock_client import MockRevolutAPIClient
from src.config import RiskLevel, StrategyType, TradingMode, settings
from src.execution.executor import OrderExecutor
from src.models.domain import MarketData, Order, PortfolioSnapshot
from src.risk_management.risk_manager import RiskManager
from src.strategies.base_strategy import BaseStrategy
from src.strategies.breakout import BreakoutStrategy
from src.strategies.market_making import MarketMakingStrategy
from src.strategies.mean_reversion import MeanReversionStrategy
from src.strategies.momentum import MomentumStrategy
from src.strategies.multi_strategy import MultiStrategy
from src.strategies.range_reversion import RangeReversionStrategy
from src.utils.db_persistence import DatabasePersistence

# Recommended polling interval per strategy — balances signal freshness against API cost.
# Market-making and breakout react to order-book changes in seconds; mean-reversion and
# range-reversion operate on slower statistical drift.  Override with --interval if needed.
_STRATEGY_INTERVALS: dict[StrategyType, int] = {
    StrategyType.MARKET_MAKING: 5,
    StrategyType.BREAKOUT: 5,
    StrategyType.MOMENTUM: 10,
    StrategyType.MULTI_STRATEGY: 10,
    StrategyType.MEAN_REVERSION: 15,
    StrategyType.RANGE_REVERSION: 15,
}


class TradingBot:
    """Main trading bot orchestrating all components."""

    def __init__(
        self,
        strategy_type: StrategyType | None = None,
        risk_level: RiskLevel | None = None,
        trading_mode: TradingMode | None = None,
        trading_pairs: list | None = None,
    ):
        # Configuration
        self.strategy_type = strategy_type or settings.default_strategy
        self.risk_level = risk_level or settings.risk_level
        self.trading_mode = trading_mode or settings.trading_mode
        self.trading_pairs = trading_pairs or settings.trading_pairs

        # Components (initialized in start())
        self.api_client: RevolutAPIClient | MockRevolutAPIClient | None = None
        self.risk_manager: RiskManager | None = None
        self.executor: OrderExecutor | None = None
        self.strategy: BaseStrategy | None = None
        self.persistence = DatabasePersistence()
        self.current_session_id: int | None = None

        # Currency display
        currency_symbols = {"EUR": "€", "USD": "$", "GBP": "£"}
        self.currency_symbol = currency_symbols.get(settings.base_currency, settings.base_currency)

        # State
        self.is_running = False
        self.cash_balance = Decimal(str(settings.paper_initial_capital))
        # Use deque with maxlen to prevent unbounded memory growth
        # Keeps last 1000 snapshots (~16 hours at 1min intervals, or ~7 days at 10min intervals)
        self.portfolio_snapshots: deque[PortfolioSnapshot] = deque(maxlen=1000)
        # Time-based periodic save: triggers _save_data() every 60 seconds.
        # Initialised to 0.0 so the first iteration always saves (monotonic() >> 60).
        self._last_saved_at: float = 0.0

        logger.info("Trading Bot initialized")
        logger.info(f"Strategy: {self.strategy_type}")
        logger.info(f"Risk Level: {self.risk_level}")
        logger.info(f"Trading Mode: {self.trading_mode}")
        logger.info(f"Trading Pairs: {self.trading_pairs}")

    def _validate_security_settings(self):
        """Validate that 1Password is available before starting bot."""
        from src.utils.onepassword import is_available

        if is_available():
            logger.info("✓ 1Password configured and available (secure mode)")
        else:
            logger.error(
                "✗ 1Password is required but not available!\n"
                "  Install 1Password CLI: brew install --cask 1password-cli\n"
                "  Authenticate:         export OP_SERVICE_ACCOUNT_TOKEN=ops_xxxx..."
            )
            # Will fail when trying to initialize API client

    async def start(self):
        """Initialize and start the trading bot."""
        logger.info("Starting trading bot...")

        # Validate 1Password configuration for production
        self._validate_security_settings()

        # Load historical data if available
        self._load_historical_data()

        # Start database session tracking
        self.current_session_id = self.persistence.create_session(
            strategy=self.strategy_type.value,
            risk_level=self.risk_level.value,
            trading_mode=self.trading_mode.value,
            trading_pairs=self.trading_pairs,
            initial_balance=self.cash_balance,
        )
        logger.info(f"Trading session started: {self.current_session_id}")

        # Initialize API client (mock for dev, real for int/prod)
        self.api_client = create_api_client(settings.environment)
        await self.api_client.initialize()

        # Check key permissions before going further
        perms = await self.api_client.check_permissions()
        if not perms["view"]:
            raise RuntimeError(
                "API key cannot read market data. Check credentials with 'make api-ready'."
            )
        if self.trading_mode == TradingMode.LIVE and not perms["trade"]:
            raise RuntimeError(
                "API key is read-only — cannot start in LIVE mode.\n"
                "Switch to paper mode ('make run-paper') or create a key with "
                "trading permissions in Revolut X."
            )
        if not perms["trade"]:
            logger.info(
                "API key is read-only — running in simulation mode (orders will not be sent to exchange)"
            )

        # Initialize risk manager with strategy so per-strategy overrides apply.
        self.risk_manager = RiskManager(
            risk_level=self.risk_level, strategy=self.strategy_type.value
        )

        # Initialize order executor
        self.executor = OrderExecutor(
            api_client=self.api_client,
            risk_manager=self.risk_manager,
            trading_mode=self.trading_mode,
        )

        # Initialize strategy
        self.strategy = self._create_strategy(self.strategy_type)

        # Get initial balance
        if self.trading_mode == TradingMode.LIVE:
            try:
                balance_data = await self.api_client.get_balance()
                # Extract base currency available balance from the balances dict.
                # get_balance() returns {"balances": {currency: {available, ...}}, ...}
                base = settings.base_currency
                base_balances = balance_data.get("balances", {}).get(base, {})
                available = base_balances.get("available")
                if available is None:
                    raise RuntimeError(f"No {base} balance found. Ensure the account holds {base}.")
                self.cash_balance = Decimal(str(available))
                logger.info(f"Live account balance: {self.currency_symbol}{self.cash_balance:,.2f}")
            except RuntimeError:
                raise
            except Exception as e:
                logger.critical(f"CRITICAL: Failed to get account balance in LIVE mode: {e}")
                logger.critical("Cannot start live trading without accurate balance information!")
                raise RuntimeError(
                    "Cannot start live trading without account balance. "
                    "Please check API connection and credentials."
                ) from e

        # Apply MAX_CAPITAL cap — limits how much money the bot can trade with.
        if settings.max_capital is not None:
            max_cap = Decimal(str(settings.max_capital))
            if self.cash_balance > max_cap:
                logger.info(
                    f"MAX_CAPITAL cap applied: {self.currency_symbol}{self.cash_balance:,.2f} "
                    f"→ {self.currency_symbol}{max_cap:,.2f}"
                )
                self.cash_balance = max_cap

        self.is_running = True
        logger.info("Trading bot started successfully!")

    async def stop(self):
        """Stop the trading bot gracefully.

        Shutdown sequence:
          1. Cancel all pending orders and close losing positions.
          2. Update cash balance for any positions closed during shutdown.
          3. Save final portfolio state to the database.
          4. End the database session with final metrics.
          5. Close the API client connection.
        """
        logger.info("Stopping trading bot...")
        logger.info("Please wait — cancelling orders and closing all positions before exit...")
        self.is_running = False

        # Graceful shutdown: cancel orders, close ALL positions.
        # Profitable positions wait for a trailing stop (if configured) before closing.
        if self.executor:
            trailing_pct = (
                Decimal(str(settings.shutdown_trailing_stop_pct))
                if settings.shutdown_trailing_stop_pct is not None
                else None
            )
            shutdown_summary = await self.executor.graceful_shutdown(
                trailing_stop_pct=trailing_pct,
                max_wait_seconds=settings.shutdown_max_wait_seconds,
            )
            logger.info(
                f"Shutdown: {shutdown_summary.orders_cancelled} orders cancelled, "
                f"{shutdown_summary.positions_closed}/{shutdown_summary.positions_evaluated} "
                f"positions closed "
                f"({shutdown_summary.positions_trailing_stopped} via trailing stop)"
            )

            # Update cash balance for positions closed during shutdown
            for order in shutdown_summary.filled_close_orders:
                self._process_filled_order(order)

            if shutdown_summary.errors:
                for error in shutdown_summary.errors:
                    logger.error(f"Shutdown error: {error}")

        # Save final state and end session
        self._save_data()

        # End database session
        current_snapshot = self.portfolio_snapshots[-1] if self.portfolio_snapshots else None
        if current_snapshot and self.current_session_id is not None:
            total_trades = len(self.persistence.load_trade_history(limit=100000))
            self.persistence.end_session(
                session_id=self.current_session_id,
                final_balance=self.cash_balance,
                total_pnl=current_snapshot.total_pnl,
                total_trades=total_trades,
            )
            logger.info(f"Trading session ended: {self.current_session_id}")

        if self.api_client:
            await self.api_client.close()

        logger.info("Trading bot stopped")

    def _create_strategy(self, strategy_type: StrategyType) -> BaseStrategy:
        """Create strategy instance based on type."""
        strategies = {
            StrategyType.MARKET_MAKING: MarketMakingStrategy(),
            StrategyType.MOMENTUM: MomentumStrategy(),
            StrategyType.MEAN_REVERSION: MeanReversionStrategy(),
            StrategyType.MULTI_STRATEGY: MultiStrategy(),
            StrategyType.BREAKOUT: BreakoutStrategy(),
            StrategyType.RANGE_REVERSION: RangeReversionStrategy(),
        }
        return strategies.get(strategy_type, MarketMakingStrategy())

    @staticmethod
    def _handle_http_error(e: httpx.HTTPStatusError) -> int | None:
        """Handle HTTP status errors and return the retry delay, or None to stop.

        Args:
            e: The HTTP status error from the API.

        Returns:
            Seconds to sleep before retrying, or ``None`` to break the loop.
        """
        status_code = e.response.status_code
        if status_code == 401:
            logger.critical("Authentication failed! Check API credentials.")
            return None  # Stop trading - auth is broken
        if status_code == 429:
            logger.warning("⚠️  Rate limited by API, backing off...")
            return 60
        if status_code >= 500:
            logger.error(f"🔧 API server error ({status_code}), waiting 30s...")
            return 30
        logger.error(f"❌ HTTP error {status_code}: {e.response.text}")
        return -1  # Sentinel: use default interval

    async def _run_iteration(self, iteration: int) -> None:
        """Execute a single trading iteration.

        Args:
            iteration: The current iteration number (for logging).
        """
        logger.info(f"=== Trading Iteration {iteration} ===")

        market_data_map = await self._fetch_all_market_data()

        await asyncio.gather(
            *[
                self._process_symbol(symbol, market_data_map.get(symbol))
                for symbol in self.trading_pairs
            ],
            return_exceptions=True,
        )

        self._update_portfolio()

        if self.portfolio_snapshots:
            self.persistence.save_portfolio_snapshot(
                snapshot=self.portfolio_snapshots[-1],
                strategy=self.strategy_type.value,
                risk_level=self.risk_level.value,
                trading_mode=self.trading_mode.value,
            )

        now = time.monotonic()
        if now - self._last_saved_at >= 60.0:
            self._save_data()
            self._last_saved_at = now

        self._check_risk_limits()

    def _handle_loop_exception(self, error: Exception, interval: int) -> tuple[bool, int]:
        """Classify a trading-loop exception into a retry decision.

        Args:
            error:    The exception raised during the iteration.
            interval: Default sleep interval in seconds.

        Returns:
            ``(should_continue, sleep_seconds)`` — *should_continue* is ``False``
            when the loop must stop.
        """
        if isinstance(error, httpx.TimeoutException):
            logger.warning(f"⏱️  API timeout in trading loop: {error}")
            logger.info("Retrying next iteration...")
            return True, interval

        if isinstance(error, httpx.HTTPStatusError):
            delay = self._handle_http_error(error)
            if delay is None:
                return False, 0
            return True, interval if delay == -1 else delay

        if isinstance(error, ValueError):
            logger.error(f"📊 Data validation error: {error}")
            logger.info("Likely malformed market data, continuing...")
            return True, interval

        if isinstance(error, RuntimeError):
            logger.critical(f"Runtime error: {error}")
            return False, 0

        logger.critical(
            f"Unexpected error in trading loop: {type(error).__name__}: {error}", exc_info=True
        )
        return True, interval

    def _default_interval(self) -> int:
        """Return the recommended loop interval in seconds for the active strategy.

        Faster strategies (market making, breakout) need fresh order-book data
        every 5 seconds.  Trend-following strategies (momentum, multi) are
        comfortable at 10 seconds.  Statistical strategies (mean reversion,
        range reversion) operate on slower drift and run at 15 seconds.

        Returns:
            Recommended polling interval in seconds.
        """
        return _STRATEGY_INTERVALS.get(self.strategy_type, 10)

    async def run_trading_loop(self, interval: int | None = None):
        """Main trading loop.

        Args:
            interval: Seconds between iterations.  Pass ``None`` (default) to
                      let the bot pick the optimal interval for the active
                      strategy via :meth:`_default_interval`.  Pass an explicit
                      value to override (e.g. ``--interval 30`` from the CLI).
        """
        effective_interval = interval if interval is not None else self._default_interval()
        logger.info(f"Starting trading loop (interval: {effective_interval}s)")

        iteration = 0
        while self.is_running:
            try:
                iteration += 1
                await self._run_iteration(iteration)
                await asyncio.sleep(effective_interval)
            except KeyboardInterrupt:
                logger.info("Received shutdown signal")
                break
            except Exception as e:
                should_continue, sleep_time = self._handle_loop_exception(e, effective_interval)
                if not should_continue:
                    break
                await asyncio.sleep(sleep_time)

    def _process_filled_order(self, order: Order) -> None:
        """Persist a filled order and update the cash balance.

        Args:
            order: The filled order to process.
        """
        self.persistence.save_trade(order)
        if order.price is not None:
            order_value = order.price * order.filled_quantity
            if order.side.value == "BUY":
                self.cash_balance -= order_value
            else:
                self.cash_balance += order_value

    async def _process_symbol(self, symbol: str, market_data: MarketData | None = None):
        """Process a single trading pair.

        Args:
            symbol:      Trading pair (e.g. ``"BTC-EUR"``).
            market_data: Pre-fetched MarketData from the batch call, or ``None``
                         to trigger a per-symbol fallback fetch.
        """
        assert self.executor is not None
        assert self.strategy is not None
        try:
            if market_data is None:
                market_data = await self._fetch_market_data(symbol)
            if not market_data:
                return

            await self.executor.update_market_prices(symbol, market_data.last)
            portfolio_value = await self.executor.get_portfolio_value(self.cash_balance)

            signal = await self.strategy.analyze(
                symbol=symbol,
                market_data=market_data,
                positions=self.executor.get_positions(),
                portfolio_value=portfolio_value,
            )

            if signal:
                logger.info(f"Signal generated: {signal.signal_type} {symbol} - {signal.reason}")
                order = await self.executor.execute_signal(signal, portfolio_value)
                if order and order.status.value == "FILLED":
                    self._process_filled_order(order)

        except Exception as e:
            logger.error(f"Error processing {symbol}: {e!s}", exc_info=True)

    async def _fetch_all_market_data(self) -> dict[str, "MarketData"]:
        """Fetch market data for all trading pairs in a single batch API call.

        Uses GET /tickers to retrieve all pairs with one request instead of
        one GET /order-book/{symbol} request per pair, reducing API call count
        from N (pairs) to 1 per iteration.

        Returns:
            Dict mapping normalised symbol (``"BTC-EUR"``) to MarketData.
            Returns an empty dict if the API call fails — callers fall back
            to per-symbol fetches in that case.
        """
        assert self.api_client is not None
        try:
            tickers = await self.api_client.get_tickers(symbols=self.trading_pairs)
            result: dict[str, MarketData] = {}
            now = datetime.now(UTC)
            for ticker in tickers:
                raw_symbol = ticker.get("symbol", "")
                # API returns "BTC/EUR"; trading_pairs use "BTC-EUR"
                symbol = raw_symbol.replace("/", "-")
                if symbol not in self.trading_pairs:
                    continue
                last = Decimal(str(ticker.get("last_price") or ticker.get("last", 0)))
                result[symbol] = MarketData(
                    symbol=symbol,
                    timestamp=now,
                    bid=Decimal(str(ticker.get("bid", 0))),
                    ask=Decimal(str(ticker.get("ask", 0))),
                    last=last,
                    volume_24h=Decimal("0"),
                    high_24h=Decimal("0"),
                    low_24h=Decimal("0"),
                )
            return result
        except Exception as e:
            logger.error(f"Failed to batch fetch market data: {e!s}")
            return {}

    async def _fetch_market_data(self, symbol: str) -> MarketData | None:
        """Fetch current market data for a symbol.

        Both paper and live modes use real market data from the Revolut API.
        The difference is in execution: paper mode simulates orders, live mode executes them.
        """
        assert self.api_client is not None
        try:
            # Fetch real market data from API (used in both paper and live modes)
            ticker_data = await self.api_client.get_ticker(symbol)

            return MarketData(
                symbol=symbol,
                timestamp=datetime.now(UTC),
                bid=Decimal(str(ticker_data.get("bid", 0))),
                ask=Decimal(str(ticker_data.get("ask", 0))),
                last=Decimal(str(ticker_data.get("last", 0))),
                volume_24h=Decimal(str(ticker_data.get("volume", 0))),
                high_24h=Decimal(str(ticker_data.get("high", 0))),
                low_24h=Decimal(str(ticker_data.get("low", 0))),
            )

        except Exception as e:
            logger.error(f"Failed to fetch market data for {symbol}: {e!s}")
            return None

    def _update_portfolio(self) -> None:
        """Update and save portfolio snapshot."""
        assert self.executor is not None
        positions = self.executor.get_positions()

        positions_value = sum((pos.quantity * pos.current_price for pos in positions), Decimal("0"))
        unrealized_pnl = sum((pos.unrealized_pnl for pos in positions), Decimal("0"))
        realized_pnl = sum((pos.realized_pnl for pos in positions), Decimal("0"))
        total_value = self.cash_balance + positions_value

        snapshot = PortfolioSnapshot(
            total_value=total_value,
            cash_balance=self.cash_balance,
            positions_value=positions_value,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=realized_pnl,
            total_pnl=unrealized_pnl + realized_pnl,
            daily_pnl=Decimal("0"),  # Would calculate from previous day
            num_positions=len(positions),
        )

        self.portfolio_snapshots.append(snapshot)

        logger.info(
            f"Portfolio: {self.currency_symbol}{total_value:.2f} | "
            f"Cash: {self.currency_symbol}{self.cash_balance:.2f} | "
            f"Positions: {self.currency_symbol}{positions_value:.2f} | "
            f"P&L: {self.currency_symbol}{snapshot.total_pnl:.2f}"
        )

    def _check_risk_limits(self) -> None:
        """Check and enforce risk limits."""
        if not self.portfolio_snapshots:
            return

        current_snapshot = self.portfolio_snapshots[-1]

        assert self.risk_manager is not None
        # Update risk manager with daily P&L
        self.risk_manager.update_daily_pnl(
            current_snapshot.daily_pnl, Decimal(str(settings.paper_initial_capital))
        )

        if self.risk_manager.daily_loss_limit_hit:
            logger.critical(
                f"Daily loss limit reached! P&L: {self.currency_symbol}{current_snapshot.daily_pnl:.2f}. "
                "Trading suspended until reset."
            )

    def _load_historical_data(self) -> None:
        """Load historical portfolio snapshots and trade history from database."""
        try:
            # Load recent snapshots from database (last 1000)
            snapshots_data = self.persistence.load_portfolio_snapshots(limit=1000)
            if snapshots_data:
                logger.info(f"Loaded {len(snapshots_data)} historical snapshots from database")

            # Load trade history (just log count)
            trades = self.persistence.load_trade_history(limit=100)
            if trades:
                logger.info(f"Loaded {len(trades)} recent trades from database")

            # Show analytics for last 7 days
            analytics = self.persistence.get_analytics(days=7)
            if analytics and analytics.get("total_trades", 0) > 0:
                logger.info(
                    f"Last 7 days: {analytics['total_trades']} trades, "
                    f"Win rate: {analytics['win_rate']:.1f}%, "
                    f"Total P&L: {self.currency_symbol}{analytics['total_pnl']:.2f}"
                )

        except Exception as e:
            logger.warning(f"Could not load historical data: {e}")
            logger.info("Starting with fresh state")

    def _save_data(self) -> None:
        """Save current portfolio snapshots to database."""
        try:
            # Bulk save snapshots to database periodically
            if self.portfolio_snapshots:
                metadata = {
                    "strategy": self.strategy_type.value,
                    "risk_level": self.risk_level.value,
                    "trading_mode": self.trading_mode.value,
                    "trading_pairs": self.trading_pairs,
                }
                self.persistence.save_portfolio_snapshots_bulk(
                    list(self.portfolio_snapshots), metadata
                )

            logger.debug("Saved portfolio data to database")

        except Exception as e:
            logger.error(f"Failed to save data: {e}")


async def main():
    """Main entry point for the trading bot."""
    bot = TradingBot()

    try:
        await bot.start()
        await bot.run_trading_loop()  # interval chosen from strategy
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
