import asyncio
import contextlib
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
from src.models.domain import MarketData, Order, OrderStatus, PortfolioSnapshot
from src.risk_management.risk_manager import RiskManager
from src.strategies.base_strategy import BaseStrategy
from src.strategies.breakout import BreakoutStrategy
from src.strategies.market_making import MarketMakingStrategy
from src.strategies.mean_reversion import MeanReversionStrategy
from src.strategies.momentum import MomentumStrategy
from src.strategies.multi_strategy import MultiStrategy
from src.strategies.range_reversion import RangeReversionStrategy
from src.utils.db_persistence import DatabasePersistence
from src.utils.telegram import TelegramNotifier


def _setup_database_logging(persistence: DatabasePersistence, session_id: int | None = None) -> int:
    """Configure loguru to save WARNING+ logs to the encrypted database.

    Returns the sink_id so it can be removed later.

    Args:
        persistence: Database persistence instance.
        session_id: Optional trading session ID to associate with logs.

    Returns:
        The loguru sink ID (use logger.remove(sink_id) to stop).
    """

    def database_sink(message: object) -> None:
        """Loguru sink that persists WARNING+ logs to the database."""
        record = message.record  # type: ignore[attr-defined]
        # Only save WARNING, ERROR, and CRITICAL to avoid filling the database
        if record["level"].no >= 30:
            persistence.save_log_entry(
                level=record["level"].name,
                message=record["message"],
                module=record["name"],
                session_id=session_id,
            )

    # Add database sink for WARNING+ logs
    return logger.add(database_sink, level="WARNING", format="{message}")


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

        # Telegram notifier — active only when both token and chat_id are configured.
        self.notifier: TelegramNotifier | None = (
            TelegramNotifier(
                token=settings.telegram_bot_token,
                chat_id=settings.telegram_chat_id,
            )
            if settings.telegram_bot_token and settings.telegram_chat_id
            else None
        )

        # Currency display
        currency_symbols = {"EUR": "€", "USD": "$", "GBP": "£"}
        self.currency_symbol = currency_symbols.get(settings.base_currency, settings.base_currency)

        # State
        self.is_running = False
        self._daily_loss_notified = False  # prevents repeated Telegram alerts per session
        self.cash_balance = Decimal(str(settings.paper_initial_capital))
        self._started_at: datetime | None = None
        self._telegram_stop_event: asyncio.Event | None = None
        self._telegram_polling_task: asyncio.Task[None] | None = None
        self._db_log_sink_id: int | None = None  # loguru sink ID for database logging
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

    async def _initialize_balance(self) -> None:
        """Fetch live balance and apply MAX_CAPITAL cap if configured."""
        # Get initial balance (live mode fetches real balance from the API)
        if self.trading_mode == TradingMode.LIVE:
            self.cash_balance = await self._fetch_live_balance()

        # Apply MAX_CAPITAL cap — limits how much money the bot can trade with.
        if settings.max_capital is not None:
            max_cap = Decimal(str(settings.max_capital))
            if self.cash_balance > max_cap:
                logger.info(
                    f"MAX_CAPITAL cap applied: {self.currency_symbol}{self.cash_balance:,.2f} "
                    f"→ {self.currency_symbol}{max_cap:,.2f}"
                )
                self.cash_balance = max_cap

    async def _start_telegram_command_listener(self) -> None:
        """Start background Telegram command listener task."""
        if self.notifier:
            await self.notifier.notify_started(
                strategy=self.strategy_type.value,
                risk_level=self.risk_level.value,
                pairs=self.trading_pairs,
                mode=self.trading_mode.value,
            )
            self._telegram_stop_event = asyncio.Event()
            self._telegram_polling_task = asyncio.create_task(
                self.notifier.start_polling(
                    self._handle_telegram_command, self._telegram_stop_event
                )
            )
            logger.info("Telegram command listener started")

    async def start(self, start_command_listener: bool = True) -> None:
        """Initialize and start the trading bot.

        Args:
            start_command_listener: When True (default), starts the background
                Telegram command polling task.  Pass False when an external
                control plane (e.g. TelegramControlPlane) already owns the
                single Telegram polling loop so there are no duplicate handlers.
        """
        logger.info("Starting trading bot...")

        # Show LIVE mode warning if active
        warning = settings.get_mode_warning()
        if warning:
            logger.warning(warning)

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

        # Enable database logging for WARNING+ messages
        self._db_log_sink_id = _setup_database_logging(
            self.persistence, session_id=self.current_session_id
        )
        logger.info("Database logging enabled for WARNING+ messages")

        # Initialize API client (mock for dev, real for int/prod)
        self.api_client = create_api_client(settings.environment)
        await self.api_client.initialize()

        # Check key permissions before going further
        await self._validate_permissions()

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

        # Fetch balance and apply capital cap
        await self._initialize_balance()

        self.is_running = True
        self._started_at = datetime.now(UTC)
        logger.info("Trading bot started successfully!")

        # Start Telegram command listener if requested
        if start_command_listener and self.notifier:
            await self._start_telegram_command_listener()

    async def _validate_permissions(self) -> None:
        """Check API key permissions and raise RuntimeError if they are insufficient.

        Requires ``self.api_client`` to be initialised.  Raises if the key cannot
        read market data, or if the key is read-only in LIVE mode.  In paper mode
        a read-only key is allowed — orders will not be sent to the exchange.
        """
        assert self.api_client is not None
        perms = await self.api_client.check_permissions()
        if not perms["view"]:
            raise RuntimeError(
                "API key cannot read market data. Check credentials with 'make api-ready'."
            )
        if self.trading_mode == TradingMode.LIVE and not perms["trade"]:
            raise RuntimeError(
                "API key is read-only — cannot start in LIVE mode.\n"
                "Switch to paper mode ('make run ENV=int' / 'revt run --env int') or create a key with "
                "trading permissions in Revolut X."
            )
        if not perms["trade"]:
            logger.info(
                "API key is read-only — running in simulation mode (orders will not be sent to exchange)"
            )

    async def _fetch_live_balance(self) -> Decimal:
        """Fetch and return the available base-currency balance from the live API.

        Only called in LIVE mode.  Raises RuntimeError if the balance cannot be
        retrieved — trading must not start without accurate balance information.

        Returns:
            Available base-currency balance as a Decimal.
        """
        assert self.api_client is not None
        try:
            balance_data = await self.api_client.get_balance()
            # get_balance() returns {"balances": {currency: {available, ...}}, ...}
            base = settings.base_currency
            available = balance_data.get("balances", {}).get(base, {}).get("available")
            if available is None:
                raise RuntimeError(f"No {base} balance found. Ensure the account holds {base}.")
            balance = Decimal(str(available))
            logger.info(f"Live account balance: {self.currency_symbol}{balance:,.2f}")
            return balance
        except RuntimeError:
            raise
        except Exception as e:
            logger.critical(f"CRITICAL: Failed to get account balance in LIVE mode: {e}")
            logger.critical("Cannot start live trading without accurate balance information!")
            raise RuntimeError(
                "Cannot start live trading without account balance. "
                "Please check API connection and credentials."
            ) from e

    async def _shutdown_executor(self) -> None:
        """Cancel orders, close all positions, and process shutdown results.

        Runs the executor's graceful shutdown sequence, then updates cash balance
        for each position closed during shutdown and notifies on each filled order.
        Any shutdown errors are logged.
        """
        assert self.executor is not None
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

        for order in shutdown_summary.filled_close_orders:
            self._process_filled_order(order)
            if self.notifier:
                await self.notifier.notify_trade(order, self.currency_symbol)

        if shutdown_summary.errors:
            for error in shutdown_summary.errors:
                logger.error(f"Shutdown error: {error}")

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

        # Notify via Telegram before shutting down the polling loop
        if self.notifier:
            await self.notifier.reply("🔴 Trading bot is shutting down...")

        # Stop Telegram command listener before shutdown notifications
        if self._telegram_stop_event:
            self._telegram_stop_event.set()
        if self._telegram_polling_task:
            self._telegram_polling_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._telegram_polling_task
            self._telegram_polling_task = None

        # Remove database logging sink
        if self._db_log_sink_id is not None:
            logger.remove(self._db_log_sink_id)
            self._db_log_sink_id = None

        # Graceful shutdown: cancel orders, close ALL positions.
        # Profitable positions wait for a trailing stop (if configured) before closing.
        if self.executor:
            await self._shutdown_executor()

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

        if self.notifier:
            realized_pnl = (
                self.portfolio_snapshots[-1].realized_pnl
                if self.portfolio_snapshots
                else Decimal("0")
            )
            await self.notifier.notify_stopped(
                session_id=self.current_session_id,
                realized_pnl=realized_pnl,
                currency_symbol=self.currency_symbol,
            )

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

        if (
            self.notifier
            and self.risk_manager is not None
            and self.risk_manager.daily_loss_limit_hit
            and not self._daily_loss_notified
            and self.portfolio_snapshots
        ):
            self._daily_loss_notified = True
            await self.notifier.notify_daily_loss_limit(
                self.portfolio_snapshots[-1].daily_pnl,
                self.currency_symbol,
            )

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
        cfg = settings.strategy_configs.get(self.strategy_type.value)
        return cfg.interval if cfg else 10

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
                    if (
                        self.notifier
                        and isinstance(e, httpx.HTTPStatusError)
                        and e.response.status_code == 401
                    ):
                        await self.notifier.notify_error(
                            "Authentication failed! Check API credentials."
                        )
                    break
                await asyncio.sleep(sleep_time)

    def _process_filled_order(self, order: Order) -> None:
        """Persist a filled order and update the cash balance.

        Cash accounting includes trading fees so the balance reflects the true
        cost of each trade:
          - BUY:  deduct order value + fee (cash spent to acquire the asset)
          - SELL: add order value - fee (cash received minus exchange fee)

        Args:
            order: The filled order to process.
        """
        self.persistence.save_trade(order)
        if order.price is not None:
            order_value = order.price * order.filled_quantity
            fee = order.commission
            if order.side.value == "BUY":
                self.cash_balance -= order_value + fee
            else:
                self.cash_balance += order_value - fee

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

            # update_market_prices returns a filled close order when SL/TP fires.
            # Process it immediately so cash balance and trade history stay accurate.
            close_order = await self.executor.update_market_prices(symbol, market_data.last)
            if close_order and close_order.status == OrderStatus.FILLED:
                self._process_filled_order(close_order)
                if self.notifier:
                    await self.notifier.notify_trade(close_order, self.currency_symbol)

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
                if order and order.status == OrderStatus.FILLED:
                    self._process_filled_order(order)
                    if self.notifier:
                        await self.notifier.notify_trade(order, self.currency_symbol)

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

    async def _handle_telegram_command(self, command: str, args: list[str]) -> None:
        """Dispatch an incoming Telegram bot command to the appropriate handler.

        Args:
            command: Command name without the leading slash (e.g. ``"status"``).
            args:    Space-separated arguments following the command.
        """
        assert self.notifier is not None
        if command == "status":
            await self._cmd_status()
        elif command == "balance":
            await self._cmd_balance()
        elif command == "report":
            days = int(args[0]) if args and args[0].isdigit() else 30
            await self._cmd_report(days)
        elif command in ("help", "start"):
            await self._cmd_help()
        else:
            await self.notifier.reply(
                f"Unknown command: /{command}\nUse /help to see available commands."
            )

    async def _cmd_status(self) -> None:
        """Reply with current bot state: strategy, mode, uptime, positions, P&amp;L."""
        assert self.notifier is not None
        uptime = ""
        if self._started_at:
            delta = datetime.now(UTC) - self._started_at
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            uptime = f"{hours}h {minutes}m"
        positions = self.executor.get_positions() if self.executor else []
        snapshot = self.portfolio_snapshots[-1] if self.portfolio_snapshots else None
        pnl = snapshot.total_pnl if snapshot else Decimal("0")
        pnl_sign = "+" if pnl >= 0 else ""
        mode_label = "🔴 LIVE" if self.trading_mode == TradingMode.LIVE else "🟡 Paper"
        lines = [
            "🤖 <b>Bot Status</b>",
            f"Strategy: {self.strategy_type.value}",
            f"Risk: {self.risk_level.value}",
            f"Mode: {mode_label}",
            f"Pairs: {', '.join(self.trading_pairs)}",
            f"Uptime: {uptime}" if uptime else "Uptime: N/A",
            f"Open Positions: {len(positions)}",
            f"Session P&amp;L: {pnl_sign}{self.currency_symbol}{abs(pnl):,.2f}",
        ]
        await self.notifier.reply("\n".join(lines))

    async def _cmd_balance(self) -> None:
        """Reply with portfolio breakdown: cash, open positions, and total value."""
        assert self.notifier is not None
        positions = self.executor.get_positions() if self.executor else []
        positions_value = sum((p.quantity * p.current_price for p in positions), Decimal("0"))
        total_value = self.cash_balance + positions_value
        lines = [
            "💰 <b>Portfolio Balance</b>",
            f"Cash: {self.currency_symbol}{self.cash_balance:,.2f}",
            f"Positions: {self.currency_symbol}{positions_value:,.2f}",
            f"Total: {self.currency_symbol}{total_value:,.2f}",
        ]
        if positions:
            lines.append("")
            lines.append("<b>Open Positions:</b>")
            for pos in positions:
                pnl_sign = "+" if pos.unrealized_pnl >= 0 else ""
                lines.append(
                    f"• {pos.symbol}: {pos.quantity} @ "
                    f"{self.currency_symbol}{pos.current_price:,.2f} "
                    f"({pnl_sign}{self.currency_symbol}{pos.unrealized_pnl:,.2f})"
                )
        await self.notifier.reply("\n".join(lines))

    async def _cmd_report(self, days: int) -> None:
        """Reply with a comprehensive analytics report as PDF.

        Generates a full PDF report with charts and suggestions using the same
        logic as ``make db-report``.  Falls back to text summary if PDF generation
        fails or fpdf2 is not installed.

        Args:
            days: Look-back window in calendar days.
        """
        assert self.notifier is not None

        from pathlib import Path

        from cli.utils.analytics_report import generate_report_data

        try:
            await self.notifier.reply(f"📊 Generating {days}-day analytics report...")

            # Generate report data and PDF (safe to call from async context)
            result = generate_report_data(
                days=days,
                output_dir=Path("revt-data/reports"),
            )

            if not result.get("pdf_bytes"):
                # Fall back to text summary if PDF generation failed
                analytics = self.persistence.get_analytics(days=days)
                if not analytics or analytics.get("total_trades", 0) == 0:
                    await self.notifier.reply(f"📊 No trading data for the last {days} days.")
                    return

                total_pnl = Decimal(str(analytics.get("total_pnl", 0)))
                await self.notifier.notify_report_ready(
                    days=days,
                    total_trades=int(analytics.get("total_trades", 0)),
                    total_pnl=total_pnl,
                    return_pct=float(analytics.get("return_pct", 0.0)),
                    win_rate=float(analytics.get("win_rate", 0.0)),
                    sharpe_ratio=float(analytics.get("sharpe_ratio") or 0.0),
                    max_drawdown_pct=float(analytics.get("max_drawdown_pct", 0.0)),
                    report_path="(fpdf2 not installed - run `revt db report` for full PDF)",
                    currency_symbol=self.currency_symbol,
                )
                return

            # Send PDF via Telegram
            total_pnl = result["metrics"]["total_pnl"]
            pnl_sign = "+" if total_pnl >= 0 else ""
            caption = (
                f"📊 **Analytics Report - Last {days} Days**\n\n"
                f"📈 Total P&L: {pnl_sign}€{total_pnl:,.2f}\n"
                f"📉 Return: {result['metrics']['return_pct']:.2f}%\n"
                f"✅ Win Rate: {result['metrics']['win_rate']:.1f}%\n"
                f"📊 Sharpe Ratio: {result['metrics']['sharpe_ratio']:.2f}\n"
                f"📉 Max Drawdown: {result['metrics']['max_drawdown_pct']:.1f}%"
            )

            await self.notifier.send_document(
                document=result["pdf_bytes"],
                filename="analytics_report.pdf",
                caption=caption,
            )

        except Exception as exc:
            logger.warning(f"Failed to generate /report response: {exc}", exc_info=True)
            await self.notifier.reply("⚠️ Failed to generate report. Try `revt db report`.")

    async def _cmd_help(self) -> None:
        """Reply with the list of available bot commands."""
        assert self.notifier is not None
        await self.notifier.reply(
            "📋 <b>Available Commands</b>\n"
            "/status — current bot state and session P&amp;L\n"
            "/balance — portfolio breakdown with open positions\n"
            "/report [days] — analytics summary (default: 30 days)\n"
            "/help — show this message"
        )

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
