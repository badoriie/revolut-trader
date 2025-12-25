import asyncio
from datetime import datetime
from decimal import Decimal

from loguru import logger

from src.api.client import RevolutAPIClient
from src.config import RiskLevel, StrategyType, TradingMode, settings
from src.data.models import MarketData, PortfolioSnapshot
from src.execution.executor import OrderExecutor
from src.notifications.telegram import TelegramNotifier
from src.risk_management.risk_manager import RiskManager
from src.strategies.base_strategy import BaseStrategy
from src.strategies.market_making import MarketMakingStrategy
from src.strategies.mean_reversion import MeanReversionStrategy
from src.strategies.momentum import MomentumStrategy
from src.strategies.multi_strategy import MultiStrategy


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
        self.api_client: RevolutAPIClient | None = None
        self.risk_manager: RiskManager | None = None
        self.executor: OrderExecutor | None = None
        self.notifier: TelegramNotifier | None = None
        self.strategy: BaseStrategy | None = None

        # State
        self.is_running = False
        self.cash_balance = Decimal(str(settings.paper_initial_capital))
        self.portfolio_snapshots: list[PortfolioSnapshot] = []

        logger.info("Trading Bot initialized")
        logger.info(f"Strategy: {self.strategy_type}")
        logger.info(f"Risk Level: {self.risk_level}")
        logger.info(f"Trading Mode: {self.trading_mode}")
        logger.info(f"Trading Pairs: {self.trading_pairs}")

    async def start(self):
        """Initialize and start the trading bot."""
        logger.info("Starting trading bot...")

        # Initialize API client
        self.api_client = RevolutAPIClient()
        await self.api_client.initialize()

        # Initialize risk manager
        self.risk_manager = RiskManager(risk_level=self.risk_level)

        # Initialize order executor
        self.executor = OrderExecutor(
            api_client=self.api_client,
            risk_manager=self.risk_manager,
            trading_mode=self.trading_mode,
        )

        # Initialize notifications
        self.notifier = TelegramNotifier()

        # Initialize strategy
        self.strategy = self._create_strategy(self.strategy_type)

        # Get initial balance
        if self.trading_mode == TradingMode.LIVE:
            try:
                balance_data = await self.api_client.get_balance()
                # Extract USD or appropriate currency balance
                self.cash_balance = Decimal(str(balance_data.get("availableBalance", 10000)))
                logger.info(f"Live account balance: ${self.cash_balance}")
            except Exception as e:
                logger.error(f"Failed to get account balance: {e}")
                logger.info(f"Using default balance: ${self.cash_balance}")

        self.is_running = True
        logger.info("Trading bot started successfully!")

        # Send startup notification
        await self.notifier.send_message(
            f"🤖 *Trading Bot Started*\n\n"
            f"Mode: {self.trading_mode.value}\n"
            f"Strategy: {self.strategy_type.value}\n"
            f"Risk Level: {self.risk_level.value}\n"
            f"Balance: ${self.cash_balance}\n"
            f"Pairs: {', '.join(self.trading_pairs)}"
        )

    async def stop(self):
        """Stop the trading bot gracefully."""
        logger.info("Stopping trading bot...")
        self.is_running = False

        if self.api_client:
            await self.api_client.close()

        await self.notifier.send_message("🛑 *Trading Bot Stopped*")
        logger.info("Trading bot stopped")

    def _create_strategy(self, strategy_type: StrategyType) -> BaseStrategy:
        """Create strategy instance based on type."""
        strategies = {
            StrategyType.MARKET_MAKING: MarketMakingStrategy(),
            StrategyType.MOMENTUM: MomentumStrategy(),
            StrategyType.MEAN_REVERSION: MeanReversionStrategy(),
            StrategyType.MULTI_STRATEGY: MultiStrategy(),
        }
        return strategies.get(strategy_type, MarketMakingStrategy())

    async def run_trading_loop(self, interval: int = 60):
        """
        Main trading loop.

        Args:
            interval: Seconds between iterations
        """
        logger.info(f"Starting trading loop (interval: {interval}s)")

        iteration = 0
        while self.is_running:
            try:
                iteration += 1
                logger.info(f"=== Trading Iteration {iteration} ===")

                # Process each trading pair
                for symbol in self.trading_pairs:
                    await self._process_symbol(symbol)

                # Update portfolio snapshot
                await self._update_portfolio()

                # Check risk limits
                await self._check_risk_limits()

                # Wait for next iteration
                await asyncio.sleep(interval)

            except KeyboardInterrupt:
                logger.info("Received shutdown signal")
                break
            except Exception as e:
                logger.error(f"Error in trading loop: {str(e)}", exc_info=True)
                await self.notifier.notify_error(f"Trading loop error: {str(e)}")
                await asyncio.sleep(interval)

    async def _process_symbol(self, symbol: str):
        """Process a single trading pair."""
        try:
            # Get market data
            market_data = await self._fetch_market_data(symbol)
            if not market_data:
                return

            # Update positions with current price
            await self.executor.update_market_prices(symbol, market_data.last)

            # Get current portfolio value
            portfolio_value = await self.executor.get_portfolio_value(self.cash_balance)

            # Get trading signal from strategy
            signal = await self.strategy.analyze(
                symbol=symbol,
                market_data=market_data,
                positions=self.executor.get_positions(),
                portfolio_value=portfolio_value,
            )

            if signal:
                logger.info(f"Signal generated: {signal.signal_type} {symbol} - {signal.reason}")
                await self.notifier.notify_signal(signal)

                # Execute signal
                order = await self.executor.execute_signal(signal, portfolio_value)

                if order:
                    await self.notifier.notify_order(order)

                    # Update cash balance if order filled
                    if order.status.value == "FILLED":
                        order_value = order.price * order.filled_quantity
                        if order.side.value == "BUY":
                            self.cash_balance -= order_value
                        else:
                            self.cash_balance += order_value

        except Exception as e:
            logger.error(f"Error processing {symbol}: {str(e)}", exc_info=True)

    async def _fetch_market_data(self, symbol: str) -> MarketData | None:
        """Fetch current market data for a symbol."""
        try:
            if self.trading_mode == TradingMode.PAPER:
                # In paper mode, simulate with random-ish data
                # In production, you'd want to use historical data or a price feed
                import random

                base_price = Decimal(str(random.uniform(40000, 50000)))
                spread = base_price * Decimal("0.001")

                return MarketData(
                    symbol=symbol,
                    timestamp=datetime.utcnow(),
                    bid=base_price - spread,
                    ask=base_price + spread,
                    last=base_price,
                    volume_24h=Decimal("1000000"),
                    high_24h=base_price * Decimal("1.05"),
                    low_24h=base_price * Decimal("0.95"),
                )
            else:
                # Live mode - fetch from API
                ticker_data = await self.api_client.get_ticker(symbol)

                return MarketData(
                    symbol=symbol,
                    timestamp=datetime.utcnow(),
                    bid=Decimal(str(ticker_data.get("bid", 0))),
                    ask=Decimal(str(ticker_data.get("ask", 0))),
                    last=Decimal(str(ticker_data.get("last", 0))),
                    volume_24h=Decimal(str(ticker_data.get("volume", 0))),
                    high_24h=Decimal(str(ticker_data.get("high", 0))),
                    low_24h=Decimal(str(ticker_data.get("low", 0))),
                )

        except Exception as e:
            logger.error(f"Failed to fetch market data for {symbol}: {str(e)}")
            return None

    async def _update_portfolio(self):
        """Update and save portfolio snapshot."""
        positions = self.executor.get_positions()

        positions_value = sum(pos.quantity * pos.current_price for pos in positions)
        unrealized_pnl = sum(pos.unrealized_pnl for pos in positions)
        realized_pnl = sum(pos.realized_pnl for pos in positions)
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
            f"Portfolio: ${total_value:.2f} | "
            f"Cash: ${self.cash_balance:.2f} | "
            f"Positions: ${positions_value:.2f} | "
            f"P&L: ${snapshot.total_pnl:.2f}"
        )

    async def _check_risk_limits(self):
        """Check and enforce risk limits."""
        if not self.portfolio_snapshots:
            return

        current_snapshot = self.portfolio_snapshots[-1]

        # Update risk manager with daily P&L
        self.risk_manager.update_daily_pnl(
            current_snapshot.daily_pnl, Decimal(str(settings.paper_initial_capital))
        )

        # Check if daily loss limit hit
        if self.risk_manager.daily_loss_limit_hit:
            await self.notifier.notify_risk_alert(
                f"Daily loss limit reached! P&L: ${current_snapshot.daily_pnl}\n"
                f"Trading suspended until reset."
            )
            logger.critical("Daily loss limit hit - trading suspended")


async def main():
    """Main entry point for the trading bot."""
    bot = TradingBot()

    try:
        await bot.start()
        await bot.run_trading_loop(interval=60)
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
