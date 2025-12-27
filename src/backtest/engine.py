"""Backtesting engine for strategy validation using historical data."""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from loguru import logger

from src.api.client import RevolutAPIClient
from src.config import RiskLevel, StrategyType
from src.data.models import MarketData, Order, OrderSide, OrderStatus, Position
from src.risk_management.risk_manager import RiskManager
from src.strategies.base_strategy import BaseStrategy
from src.strategies.market_making import MarketMakingStrategy
from src.strategies.mean_reversion import MeanReversionStrategy
from src.strategies.momentum import MomentumStrategy
from src.strategies.multi_strategy import MultiStrategy


class BacktestResults:
    """Results from a backtest run."""

    def __init__(self):
        self.initial_capital: Decimal = Decimal("10000")
        self.final_capital: Decimal = Decimal("10000")
        self.total_trades: int = 0
        self.winning_trades: int = 0
        self.losing_trades: int = 0
        self.total_pnl: Decimal = Decimal("0")
        self.max_drawdown: Decimal = Decimal("0")
        self.sharpe_ratio: float = 0.0
        self.trades: list[dict[str, Any]] = []
        self.equity_curve: list[tuple[datetime, Decimal]] = []

    @property
    def win_rate(self) -> float:
        """Calculate win rate percentage."""
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100

    @property
    def profit_factor(self) -> float:
        """Calculate profit factor (gross profit / gross loss)."""
        gross_profit = sum(t["pnl"] for t in self.trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in self.trades if t["pnl"] < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return float(gross_profit / gross_loss)

    @property
    def return_pct(self) -> float:
        """Calculate total return percentage."""
        if self.initial_capital == 0:
            return 0.0
        return float((self.final_capital - self.initial_capital) / self.initial_capital * 100)

    def print_summary(self):
        """Print backtest summary."""
        print("\n" + "=" * 60)
        print("BACKTEST RESULTS")
        print("=" * 60)
        print(f"Initial Capital:    ${self.initial_capital:,.2f}")
        print(f"Final Capital:      ${self.final_capital:,.2f}")
        print(f"Total P&L:          ${self.total_pnl:,.2f}")
        print(f"Return:             {self.return_pct:.2f}%")
        print(f"Total Trades:       {self.total_trades}")
        print(f"Winning Trades:     {self.winning_trades}")
        print(f"Losing Trades:      {self.losing_trades}")
        print(f"Win Rate:           {self.win_rate:.2f}%")
        print(f"Profit Factor:      {self.profit_factor:.2f}")
        print(f"Max Drawdown:       ${self.max_drawdown:,.2f}")
        print("=" * 60 + "\n")


class BacktestEngine:
    """Engine for backtesting trading strategies on historical data."""

    def __init__(
        self,
        api_client: RevolutAPIClient,
        strategy_type: StrategyType,
        risk_level: RiskLevel,
        initial_capital: Decimal = Decimal("10000"),
    ):
        self.api_client = api_client
        self.strategy_type = strategy_type
        self.risk_level = risk_level
        self.initial_capital = initial_capital

        # Initialize components
        self.risk_manager = RiskManager(risk_level=risk_level)
        self.strategy = self._create_strategy(strategy_type)

        # Backtest state
        self.cash_balance = initial_capital
        self.positions: dict[str, Position] = {}
        self.results = BacktestResults()
        self.results.initial_capital = initial_capital

    def _create_strategy(self, strategy_type: StrategyType) -> BaseStrategy:
        """Create strategy instance."""
        strategies = {
            StrategyType.MARKET_MAKING: MarketMakingStrategy(),
            StrategyType.MOMENTUM: MomentumStrategy(),
            StrategyType.MEAN_REVERSION: MeanReversionStrategy(),
            StrategyType.MULTI_STRATEGY: MultiStrategy(),
        }
        return strategies.get(strategy_type, MarketMakingStrategy())

    async def fetch_historical_data(
        self,
        symbol: str,
        days: int = 30,
        interval: int = 60,
    ) -> list[dict[str, Any]]:
        """Fetch historical candle data.

        Args:
            symbol: Trading pair (e.g., "BTC-USD")
            days: Number of days of history to fetch
            interval: Candle interval in minutes

        Returns:
            List of candle data
        """
        # Calculate start timestamp
        since = int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)

        logger.info(f"Fetching {days} days of historical data for {symbol} ({interval}min candles)")
        candles = await self.api_client.get_candles(
            symbol=symbol,
            interval=interval,
            since=since,
            limit=None,  # Get all available
        )

        logger.info(f"Retrieved {len(candles)} candles")
        return candles

    def _candle_to_market_data(self, candle: dict[str, Any], symbol: str) -> MarketData:
        """Convert candle data to MarketData object."""
        close_price = Decimal(str(candle.get("close", 0)))
        high_price = Decimal(str(candle.get("high", close_price)))
        low_price = Decimal(str(candle.get("low", close_price)))
        volume = Decimal(str(candle.get("volume", 0)))

        # Estimate bid/ask from close price (use realistic spread of 0.3%)
        # Market making requires minimum 0.2% spread, so use 0.3% for realistic simulation
        spread = close_price * Decimal("0.003")

        return MarketData(
            symbol=symbol,
            timestamp=datetime.fromtimestamp(int(candle.get("start", 0)) / 1000),
            bid=close_price - spread / 2,
            ask=close_price + spread / 2,
            last=close_price,
            volume_24h=volume,
            high_24h=high_price,
            low_24h=low_price,
        )

    def _execute_backtest_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        price: Decimal,
        timestamp: datetime,
    ) -> bool:
        """Execute a simulated order in backtest.

        Returns:
            True if order was executed successfully
        """
        order_value = quantity * price

        if side == OrderSide.BUY:
            if self.cash_balance < order_value:
                logger.warning(f"Insufficient funds for BUY: need ${order_value}, have ${self.cash_balance}")
                return False

            self.cash_balance -= order_value

            # Create or update position
            if symbol in self.positions:
                pos = self.positions[symbol]
                total_cost = (pos.quantity * pos.entry_price) + (quantity * price)
                total_quantity = pos.quantity + quantity
                pos.entry_price = total_cost / total_quantity
                pos.quantity = total_quantity
                pos.current_price = price
            else:
                self.positions[symbol] = Position(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    entry_price=price,
                    current_price=price,
                    stop_loss=price * Decimal("0.985"),
                    take_profit=price * Decimal("1.025"),
                )

        else:  # SELL
            if symbol not in self.positions:
                logger.warning(f"Cannot SELL {symbol}: no position exists")
                return False

            if self.positions[symbol].quantity < quantity:
                logger.warning(f"Insufficient position to SELL {symbol}: need {quantity}, have {self.positions[symbol].quantity}")
                return False

            pos = self.positions[symbol]
            self.cash_balance += order_value

            # Calculate P&L
            pnl = (price - pos.entry_price) * quantity

            # Record trade
            self.results.trades.append({
                "timestamp": timestamp,
                "symbol": symbol,
                "side": "SELL",
                "quantity": float(quantity),
                "price": float(price),
                "pnl": float(pnl),
            })

            self.results.total_pnl += pnl
            self.results.total_trades += 1

            if pnl > 0:
                self.results.winning_trades += 1
            else:
                self.results.losing_trades += 1

            # Update or close position
            pos.quantity -= quantity
            if pos.quantity <= 0:
                del self.positions[symbol]

        return True

    async def run(
        self,
        symbols: list[str],
        days: int = 30,
        interval: int = 60,
    ) -> BacktestResults:
        """Run backtest on historical data.

        Args:
            symbols: List of trading pairs to test
            days: Number of days of history
            interval: Candle interval in minutes

        Returns:
            BacktestResults object with performance metrics
        """
        logger.info("=" * 60)
        logger.info("STARTING BACKTEST")
        logger.info("=" * 60)
        logger.info(f"Strategy: {self.strategy_type.value}")
        logger.info(f"Risk Level: {self.risk_level.value}")
        logger.info(f"Initial Capital: ${self.initial_capital}")
        logger.info(f"Symbols: {', '.join(symbols)}")
        logger.info(f"Period: {days} days, {interval}min candles")
        logger.info("=" * 60)

        # Fetch historical data for all symbols
        historical_data = {}
        for symbol in symbols:
            candles = await self.fetch_historical_data(symbol, days, interval)
            if candles:
                historical_data[symbol] = candles

        if not historical_data:
            logger.error("No historical data available")
            return self.results

        # Find common timestamps across all symbols
        all_timestamps = set()
        for candles in historical_data.values():
            all_timestamps.update(c.get("start") for c in candles)

        sorted_timestamps = sorted(all_timestamps)

        logger.info(f"Processing {len(sorted_timestamps)} time periods...")

        # Iterate through time
        for idx, timestamp in enumerate(sorted_timestamps):
            if idx % 100 == 0:
                logger.info(f"Progress: {idx}/{len(sorted_timestamps)} ({idx/len(sorted_timestamps)*100:.1f}%)")

            # Process each symbol at this timestamp
            for symbol in symbols:
                # Find candle for this timestamp
                candle = next(
                    (c for c in historical_data.get(symbol, []) if c.get("start") == timestamp),
                    None,
                )

                if not candle:
                    continue

                # Convert to MarketData
                market_data = self._candle_to_market_data(candle, symbol)

                # Update position prices
                if symbol in self.positions:
                    self.positions[symbol].current_price = market_data.last

                # Get portfolio value
                positions_value = sum(
                    pos.quantity * pos.current_price for pos in self.positions.values()
                )
                portfolio_value = self.cash_balance + positions_value

                # Get trading signal from strategy
                signal = await self.strategy.analyze(
                    symbol=symbol,
                    market_data=market_data,
                    positions=list(self.positions.values()),
                    portfolio_value=portfolio_value,
                )

                if signal:
                    # Determine order side
                    side = OrderSide.BUY if signal.signal_type == "BUY" else OrderSide.SELL

                    # Calculate position size
                    quantity = self.risk_manager.calculate_position_size(
                        portfolio_value=portfolio_value,
                        price=signal.price,
                        signal_strength=signal.strength,
                    )

                    # Create temporary order for validation
                    from src.data.models import Order, OrderType, OrderStatus
                    temp_order = Order(
                        symbol=symbol,
                        side=side,
                        order_type=OrderType.LIMIT,
                        quantity=quantity,
                        price=signal.price,
                        status=OrderStatus.PENDING,
                    )

                    # Check risk limits
                    is_valid, reason = self.risk_manager.validate_order(
                        temp_order, portfolio_value, list(self.positions.values())
                    )
                    if not is_valid:
                        logger.debug(f"Order rejected: {reason}")
                        continue

                    # Execute order
                    self._execute_backtest_order(
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        price=signal.price,
                        timestamp=market_data.timestamp,
                    )

            # Record equity
            positions_value = sum(pos.quantity * pos.current_price for pos in self.positions.values())
            equity = self.cash_balance + positions_value
            self.results.equity_curve.append((datetime.fromtimestamp(timestamp / 1000), equity))

            # Calculate drawdown
            if self.results.equity_curve:
                peak = max(e for _, e in self.results.equity_curve)
                drawdown = peak - equity
                if drawdown > self.results.max_drawdown:
                    self.results.max_drawdown = drawdown

        # Close all remaining positions at final prices
        for symbol, pos in list(self.positions.items()):
            self._execute_backtest_order(
                symbol=symbol,
                side=OrderSide.SELL if pos.side == OrderSide.BUY else OrderSide.BUY,
                quantity=pos.quantity,
                price=pos.current_price,
                timestamp=datetime.utcnow(),
            )

        # Calculate final capital
        self.results.final_capital = self.cash_balance

        logger.info("Backtest complete!")
        self.results.print_summary()

        return self.results
