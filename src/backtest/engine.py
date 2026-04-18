"""Backtesting engine for strategy validation using historical OHLCV data.

Simulates realistic execution against Revolut X candle data:
- Paginated candle fetching (API hard limit: 1 000 candles per request)
- Bid/ask slippage — buys fill at ask, sells fill at bid
- Fee deduction on every fill via ``calculate_fee()``: taker rate (0.09 %) for
  MARKET orders, maker rate (0 %) for LIMIT orders — matches live trading costs
- Stop-loss / take-profit levels derived from the active RiskManager
- SL/TP checked on every bar so open positions exit at the correct candle
- O(1) candle lookup via pre-indexed dicts (was O(n) per bar)
- O(1) drawdown tracking via running peak (was O(n) per bar)
- Annualised Sharpe ratio computed from the equity curve
"""

from __future__ import annotations

import math
import statistics
from collections import deque
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from loguru import logger

from src.api.client import RevolutAPIClient
from src.api.mock_client import MockRevolutAPIClient
from src.config import RiskLevel, StrategyType, settings
from src.execution.executor import (
    _DEFAULT_MIN_SIGNAL_STRENGTH,
    _DEFAULT_ORDER_TYPE,
)
from src.models.domain import (
    CandleData,
    MarketData,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)
from src.risk_management.risk_manager import RiskManager
from src.strategies.base_strategy import BaseStrategy
from src.strategies.breakout import BreakoutStrategy
from src.strategies.market_making import MarketMakingStrategy
from src.strategies.mean_reversion import MeanReversionStrategy
from src.strategies.momentum import MomentumStrategy
from src.strategies.multi_strategy import MultiStrategy
from src.strategies.range_reversion import RangeReversionStrategy
from src.utils.fees import calculate_fee

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Revolut X API — only these candle widths (minutes) are accepted
VALID_INTERVALS: frozenset[int] = frozenset(
    {1, 5, 15, 30, 60, 240, 1440, 2880, 5760, 10080, 20160, 40320}
)

# API constraint: (until − since) / interval_ms ≤ 1 000 candles per request
MAX_CANDLES_PER_REQUEST: int = 1000

# Simulated bid/ask half-spread applied to every candle close price (0.1 %)
# Matches real Revolut X bid-ask spreads (~0.05-0.1 %) for representative P&L.
SPREAD_PCT: Decimal = Decimal("0.001")


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


class BacktestResults:
    """Aggregated statistics from a completed backtest run."""

    def __init__(self) -> None:
        self.initial_capital: Decimal = Decimal("10000")
        self.final_capital: Decimal = Decimal("10000")
        self.total_trades: int = 0
        self.winning_trades: int = 0
        self.losing_trades: int = 0
        self.total_pnl: Decimal = Decimal("0")
        self.total_fees: Decimal = Decimal("0")
        self.max_drawdown: Decimal = Decimal("0")
        self.max_drawdown_pct: float = 0.0
        self.sharpe_ratio: float = 0.0
        self.trades: list[dict[str, Any]] = []
        self.equity_curve: list[tuple[datetime, Decimal]] = []

    # ------------------------------------------------------------------
    # Computed metrics
    # ------------------------------------------------------------------

    @property
    def win_rate(self) -> float:
        """Win rate as a percentage of closed trades."""
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100

    @property
    def profit_factor(self) -> float:
        """Gross profit divided by gross loss.

        Returns ``inf`` when there are no losing trades and at least one
        winning trade; returns ``0.0`` when there are no trades at all.
        """
        gross_profit = sum(t["pnl"] for t in self.trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in self.trades if t["pnl"] < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return float(gross_profit / gross_loss)

    @property
    def return_pct(self) -> float:
        """Total return as a percentage of initial capital."""
        if self.initial_capital == 0:
            return 0.0
        return float((self.final_capital - self.initial_capital) / self.initial_capital * 100)

    # ------------------------------------------------------------------
    # Sharpe ratio
    # ------------------------------------------------------------------

    def compute_sharpe_ratio(self, risk_free_rate: float = 0.0) -> None:
        """Compute and store the annualised Sharpe ratio from the equity curve.

        Uses per-bar returns and annualises by the estimated number of bars
        per calendar year based on the equity curve spacing.  Requires at
        least two data points; silently returns when there are fewer.

        Args:
            risk_free_rate: Per-bar risk-free rate (default 0.0).
        """
        if len(self.equity_curve) < 2:
            return

        values = [float(v) for _, v in self.equity_curve]
        returns = [
            (values[i] - values[i - 1]) / values[i - 1]
            for i in range(1, len(values))
            if values[i - 1] != 0
        ]

        if len(returns) < 2:
            return

        mean_r = statistics.mean(returns)
        std_r = statistics.stdev(returns)

        if std_r == 0:
            return

        # Annualise: √(bars per year) where bars_per_year = 525 960 / bar_minutes
        delta = self.equity_curve[1][0] - self.equity_curve[0][0]
        bar_minutes = max(delta.total_seconds() / 60, 1)
        bars_per_year = 525_960 / bar_minutes  # minutes per calendar year

        self.sharpe_ratio = (mean_r - risk_free_rate) / std_r * math.sqrt(bars_per_year)

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def print_summary(self, currency_symbol: str = "€") -> None:
        """Print a formatted summary table to stdout.

        Args:
            currency_symbol: Display symbol for the base currency (e.g. "€").
        """
        sym = currency_symbol
        print("\n" + "=" * 60)
        print("BACKTEST RESULTS")
        print("=" * 60)
        gross_pnl = self.total_pnl + self.total_fees
        print(f"Initial Capital:    {sym}{self.initial_capital:,.2f}")
        print(f"Final Capital:      {sym}{self.final_capital:,.2f}")
        print(f"Gross P&L:          {sym}{gross_pnl:,.2f}")
        print(f"Total Fees:         -{sym}{self.total_fees:,.2f}")
        print(f"Net P&L:            {sym}{self.total_pnl:,.2f}")
        print(f"Return:             {self.return_pct:.2f}%")
        print(f"Total Trades:       {self.total_trades}")
        print(f"Winning Trades:     {self.winning_trades}")
        print(f"Losing Trades:      {self.losing_trades}")
        print(f"Win Rate:           {self.win_rate:.2f}%")
        print(f"Profit Factor:      {self.profit_factor:.2f}")
        print(f"Max Drawdown:       {sym}{self.max_drawdown:,.2f} ({self.max_drawdown_pct:.2f}%)")
        print(f"Sharpe Ratio:       {self.sharpe_ratio:.3f}")
        print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class BacktestEngine:
    """Simulate a trading strategy against historical Revolut X candle data.

    Key design decisions
    --------------------
    * Candles are fetched in paginated chunks (≤ 1 000 per request) then
      indexed by start-timestamp for O(1) lookup during simulation.
    * Each bar checks open positions for SL/TP triggers *before* asking the
      strategy for a new signal, matching live-trading behaviour.
    * Execution uses bid/ask spread and deducts a taker fee on every fill so
      that the simulated P&L is representative of real trading costs.
    * Drawdown is tracked with a running peak variable — O(1) per bar.
    """

    def __init__(
        self,
        api_client: RevolutAPIClient | MockRevolutAPIClient,
        strategy_type: StrategyType,
        risk_level: RiskLevel,
        initial_capital: Decimal = Decimal("10000"),
    ) -> None:
        self.api_client = api_client
        self.strategy_type = strategy_type
        self.risk_level = risk_level
        self.initial_capital = initial_capital

        self.risk_manager = RiskManager(risk_level=risk_level, strategy=strategy_type.value)
        self.strategy: BaseStrategy = self._create_strategy(strategy_type)

        # Simulation state
        self.cash_balance: Decimal = initial_capital
        self.positions: dict[str, Position] = {}
        self.results = BacktestResults()
        self.results.initial_capital = initial_capital

        # Running peak for O(1) drawdown tracking
        self._equity_peak: Decimal = initial_capital

        # Rolling 24h high/low buffers — keyed by symbol, sized in run()
        self._high_low_buffer: dict[str, deque[tuple[Decimal, Decimal]]] = {}
        self._bars_per_24h: int = 24  # updated when run() is called with the actual interval

    # ------------------------------------------------------------------
    # Strategy factory
    # ------------------------------------------------------------------

    def _create_strategy(self, strategy_type: StrategyType) -> BaseStrategy:
        """Instantiate the strategy corresponding to *strategy_type*."""
        strategies: dict[StrategyType, BaseStrategy] = {
            StrategyType.MARKET_MAKING: MarketMakingStrategy(),
            StrategyType.MOMENTUM: MomentumStrategy(),
            StrategyType.MEAN_REVERSION: MeanReversionStrategy(),
            StrategyType.MULTI_STRATEGY: MultiStrategy(),
            StrategyType.BREAKOUT: BreakoutStrategy(),
            StrategyType.RANGE_REVERSION: RangeReversionStrategy(),
        }
        return strategies.get(strategy_type, MarketMakingStrategy())

    # ------------------------------------------------------------------
    # Historical data fetching
    # ------------------------------------------------------------------

    async def fetch_historical_data(
        self,
        symbol: str,
        days: int = 30,
        interval: int = 60,
    ) -> list[CandleData]:
        """Fetch historical candles, paginating across the API's 1 000-candle limit.

        The Revolut X API enforces ``(until − since) / interval ≤ 1 000`` per
        request.  This method transparently splits the window into chunks of
        exactly ``MAX_CANDLES_PER_REQUEST`` bars, merges the results, and
        returns them deduplicated and sorted chronologically.

        Args:
            symbol:   Trading pair (e.g. ``"BTC-EUR"``).
            days:     Look-back window in calendar days.
            interval: Candle width in minutes.  Must be one of
                      ``VALID_INTERVALS`` (1, 5, 15, 30, 60, 240, …).

        Returns:
            Chronologically sorted, deduplicated list of ``CandleData`` objects.

        Raises:
            ValueError: If *interval* is not supported by the Revolut X API.
        """
        if interval not in VALID_INTERVALS:
            raise ValueError(
                f"Unsupported candle interval: {interval} minutes. "
                f"Must be one of {sorted(VALID_INTERVALS)}."
            )

        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        start_ms = int((datetime.now(UTC) - timedelta(days=days)).timestamp() * 1000)
        interval_ms = interval * 60 * 1000
        chunk_ms = MAX_CANDLES_PER_REQUEST * interval_ms

        approx_bars = days * 24 * 60 // interval
        logger.info(
            f"Fetching {days}d of {symbol} candles ({interval}min, ~{approx_bars} bars expected)"
        )

        all_candles: list[CandleData] = []
        chunk_start = start_ms

        while chunk_start < now_ms:
            chunk_end = min(chunk_start + chunk_ms, now_ms)
            raw = await self.api_client.get_candles(
                symbol=symbol,
                interval=interval,
                since=chunk_start,
                until=chunk_end,
                limit=MAX_CANDLES_PER_REQUEST,
            )
            if raw:
                all_candles.extend(CandleData(**c) for c in raw)
            chunk_start = chunk_end

        # Deduplicate and sort by start timestamp
        seen: set[int] = set()
        unique: list[CandleData] = []
        for candle in sorted(all_candles, key=lambda c: c.start):
            if candle.start not in seen:
                seen.add(candle.start)
                unique.append(candle)

        logger.info(f"Retrieved {len(unique)} unique candles for {symbol}")
        return unique

    # ------------------------------------------------------------------
    # Candle → MarketData conversion
    # ------------------------------------------------------------------

    def _candle_to_market_data(self, candle: CandleData, symbol: str) -> MarketData:
        """Convert a ``CandleData`` to a ``MarketData`` snapshot.

        The close price is used as the reference price.  A synthetic bid/ask
        spread of ``SPREAD_PCT`` (0.3 %) is applied symmetrically around the
        close — realistic for liquid BTC/ETH pairs on Revolut X.

        The timestamp is UTC-aware, matching what the live bot produces.
        """
        close = candle.close_price
        half_spread = close * SPREAD_PCT / 2

        # Maintain a per-symbol rolling window of (high, low) pairs covering
        # the last 24 hours.  This gives strategies an accurate 24h range
        # instead of the single-candle high/low.
        buf = self._high_low_buffer.get(symbol)
        if buf is None:
            buf = deque(maxlen=self._bars_per_24h)
            self._high_low_buffer[symbol] = buf
        buf.append((candle.high_price, candle.low_price))
        high_24h = max(h for h, _ in buf)
        low_24h = min(lo for _, lo in buf)

        return MarketData(
            symbol=symbol,
            timestamp=datetime.fromtimestamp(candle.start / 1000, tz=UTC),
            bid=close - half_spread,
            ask=close + half_spread,
            last=close,
            volume_24h=candle.volume_decimal,
            high_24h=high_24h,
            low_24h=low_24h,
        )

    # ------------------------------------------------------------------
    # Simulated order execution
    # ------------------------------------------------------------------

    def _execute_buy(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        exec_price: Decimal,
        fee: Decimal,
        order_value: Decimal,
    ) -> bool:
        """Execute a simulated buy order.

        Args:
            symbol:     Trading pair.
            side:       ``BUY``.
            quantity:   Order quantity in base currency units.
            exec_price: Execution price after slippage.
            fee:        Fee for this fill (taker or maker rate).
            order_value: ``quantity × exec_price``.

        Returns:
            ``True`` if the order was filled; ``False`` if rejected.
        """
        total_cost = order_value + fee
        if self.cash_balance < total_cost:
            logger.warning(
                f"Insufficient funds for BUY {symbol}: "
                f"need {total_cost:.2f}, have {self.cash_balance:.2f}"
            )
            return False

        self.cash_balance -= total_cost
        self.results.total_fees += fee

        sl_pct = Decimal(str(self.risk_manager.risk_params["stop_loss_pct"])) / 100
        tp_pct = Decimal(str(self.risk_manager.risk_params["take_profit_pct"])) / 100

        if symbol in self.positions:
            pos = self.positions[symbol]
            total_cost_basis = pos.quantity * pos.entry_price + quantity * exec_price
            new_qty = pos.quantity + quantity
            pos.entry_price = total_cost_basis / new_qty
            pos.quantity = new_qty
            pos.current_price = exec_price
            pos.stop_loss = pos.entry_price * (1 - sl_pct)
            pos.take_profit = pos.entry_price * (1 + tp_pct)
        else:
            self.positions[symbol] = Position(
                symbol=symbol,
                side=side,
                quantity=quantity,
                entry_price=exec_price,
                current_price=exec_price,
                stop_loss=exec_price * (1 - sl_pct),
                take_profit=exec_price * (1 + tp_pct),
            )
        return True

    def _execute_sell(
        self,
        symbol: str,
        quantity: Decimal,
        exec_price: Decimal,
        fee: Decimal,
        order_value: Decimal,
        timestamp: datetime,
    ) -> bool:
        """Execute a simulated sell order.

        Args:
            symbol:      Trading pair.
            quantity:    Order quantity in base currency units.
            exec_price:  Execution price after slippage.
            fee:         Fee for this fill (taker or maker rate).
            order_value: ``quantity × exec_price``.
            timestamp:   Bar timestamp for the trade log.

        Returns:
            ``True`` if the order was filled; ``False`` if rejected.
        """
        if symbol not in self.positions:
            logger.debug(f"Cannot SELL {symbol}: no open position")
            return False

        pos = self.positions[symbol]
        if pos.quantity < quantity:
            logger.debug(
                f"Insufficient position for SELL {symbol}: have {pos.quantity}, need {quantity}"
            )
            return False

        self.cash_balance += order_value - fee
        self.results.total_fees += fee

        pnl = (exec_price - pos.entry_price) * quantity - fee
        self.results.trades.append(
            {
                "timestamp": timestamp.isoformat(),
                "symbol": symbol,
                "side": "SELL",
                "quantity": float(quantity),
                "price": float(exec_price),
                "entry_price": float(pos.entry_price),
                "pnl": float(pnl),
                "fee": float(fee),
            }
        )

        self.results.total_pnl += pnl
        self.results.total_trades += 1
        if pnl > 0:
            self.results.winning_trades += 1
        else:
            self.results.losing_trades += 1

        pos.quantity -= quantity
        if pos.quantity <= Decimal("0"):
            del self.positions[symbol]

        return True

    def _execute_backtest_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        price: Decimal,
        timestamp: datetime,
        market_data: MarketData | None = None,
        order_type: OrderType = OrderType.MARKET,
    ) -> bool:
        """Simulate a fill with slippage and taker fee.

        Execution price
        ~~~~~~~~~~~~~~~
        MARKET orders: buys fill at ask, sells at bid — modelling taker spread cost.
        LIMIT orders:  buys fill at *price* (not ask) only if ``market_data.low ≤ price``;
        sells fill at *price* only if ``market_data.high ≥ price``.  When
        *market_data* is ``None`` (end-of-backtest force-close), the supplied
        *price* is used directly regardless of order type.

        Fee
        ~~~
        ``calculate_fee()`` is used: taker rate (0.09 %) for MARKET orders,
        maker rate (0 %) for LIMIT orders.  Matches live trading costs exactly.

        Stop-loss / take-profit
        ~~~~~~~~~~~~~~~~~~~~~~~
        SL/TP levels are set from ``RiskManager.risk_params`` so they match
        the live trading configuration for the chosen risk level.

        Args:
            symbol:      Trading pair.
            side:        ``BUY`` or ``SELL``.
            quantity:    Order quantity in base currency units.
            price:       Reference price / limit price.
            timestamp:   Bar timestamp recorded in the trade log.
            market_data: Current bar's bid/ask/high/low; enables slippage and
                         LIMIT fill verification.
            order_type:  ``MARKET`` fills immediately at bid/ask; ``LIMIT``
                         only fills when the candle range includes the limit price.

        Returns:
            ``True`` if the order was filled; ``False`` if it was rejected
            (insufficient funds, no open position to sell, or LIMIT price not reached).
        """
        if market_data is None:
            # End-of-backtest force-close: use supplied price directly.
            exec_price = price
        elif order_type == OrderType.LIMIT:
            # LIMIT fill verification: the price must have been reached during the bar.
            if side == OrderSide.BUY:
                if market_data.low_24h > price:
                    logger.debug(
                        f"{symbol}: LIMIT BUY at {price} not filled "
                        f"(candle low {market_data.low_24h} > limit price)"
                    )
                    return False
                exec_price = price  # fill at limit, not at ask
            else:  # SELL
                if market_data.high_24h < price:
                    logger.debug(
                        f"{symbol}: LIMIT SELL at {price} not filled "
                        f"(candle high {market_data.high_24h} < limit price)"
                    )
                    return False
                exec_price = price  # fill at limit, not at bid
        else:
            # MARKET order: always fills at bid/ask (taker cost).
            exec_price = market_data.ask if side == OrderSide.BUY else market_data.bid

        order_value = quantity * exec_price
        fee = calculate_fee(order_value, order_type)

        if side == OrderSide.BUY:
            return self._execute_buy(symbol, side, quantity, exec_price, fee, order_value)
        return self._execute_sell(symbol, quantity, exec_price, fee, order_value, timestamp)

    # ------------------------------------------------------------------
    # Main simulation loop
    # ------------------------------------------------------------------

    def _check_and_exit_position(self, symbol: str, market_data: MarketData) -> bool:
        """Check whether an open position should be closed this bar and execute the exit.

        Checks intra-bar SL/TP extremes first (mirrors live bot's frequent polling),
        then falls back to a close-price check.  SL takes precedence over TP when
        both are triggered by the same candle (conservative / worst-case assumption).

        Args:
            symbol:      Trading pair.
            market_data: Current bar's market snapshot (provides low/high/close).

        Returns:
            ``True`` if the position was closed this bar; ``False`` otherwise.
        """
        if symbol not in self.positions:
            return False

        pos = self.positions[symbol]

        # Intra-bar SL/TP: check the bar's low/high BEFORE updating to close price.
        if pos.stop_loss is not None or pos.take_profit is not None:
            sl_hit = (
                pos.stop_loss is not None
                and pos.side == OrderSide.BUY
                and market_data.low_24h <= pos.stop_loss
            )
            tp_hit = (
                pos.take_profit is not None
                and pos.side == OrderSide.BUY
                and market_data.high_24h >= pos.take_profit
            )
            if sl_hit or tp_hit:
                exit_price = pos.stop_loss if sl_hit else pos.take_profit
                exit_reason = "Stop-loss" if sl_hit else "Take-profit"
                assert exit_price is not None  # narrowing for type checker
                logger.debug(
                    f"{exit_reason} triggered intra-bar for {symbol} at {exit_price:.4f} "
                    f"(bar low={market_data.low_24h:.4f}, high={market_data.high_24h:.4f})"
                )
                self._execute_backtest_order(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    quantity=pos.quantity,
                    price=exit_price,
                    timestamp=market_data.timestamp,
                    market_data=None,  # fill at exact SL/TP price, not bid
                )
                return True

        # No intra-bar exit: update to close price and run the close-price check.
        pos.update_price(market_data.last)
        should_exit, exit_reason = pos.should_close()
        if should_exit:
            logger.debug(f"{exit_reason} triggered for {symbol} at {market_data.last:.4f}")
            self._execute_backtest_order(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=pos.quantity,
                price=market_data.last,
                timestamp=market_data.timestamp,
                market_data=market_data,
            )
            return True

        return False

    async def _process_bar_symbol(
        self,
        symbol: str,
        market_data: MarketData,
    ) -> None:
        """Process a single symbol for one bar: update position, check SL/TP, generate signal.

        Args:
            symbol:      Trading pair.
            market_data: Current bar's market snapshot.
        """
        # 1. Check whether an open position should exit this bar.
        if self._check_and_exit_position(symbol, market_data):
            return

        # 2. Ask the strategy for a signal
        positions_value = sum(p.quantity * p.current_price for p in self.positions.values())
        portfolio_value = self.cash_balance + positions_value

        signal = await self.strategy.analyze(
            symbol=symbol,
            market_data=market_data,
            positions=list(self.positions.values()),
            portfolio_value=portfolio_value,
        )
        if signal is None:
            return

        # Mirror the live-trading signal strength filter from OrderExecutor.
        strategy_key = signal.strategy.lower().replace(" ", "_").replace("-", "_")
        _scfg = settings.strategy_configs.get(strategy_key)
        min_strength = _scfg.min_signal_strength if _scfg else _DEFAULT_MIN_SIGNAL_STRENGTH
        if float(signal.strength) < min_strength:
            logger.debug(
                f"{symbol}: signal strength {signal.strength:.2f} below threshold "
                f"{min_strength} for strategy '{signal.strategy}' — skipped"
            )
            return

        # Mirror the live executor's SELL guard: never try to sell a symbol the bot
        # has not opened a position in.  Without this check, strategies that emit SELL
        # signals on price momentum (not inventory) would reach _execute_backtest_order
        # and log spurious WARNING messages for every bar.
        if signal.signal_type == "SELL" and symbol not in self.positions:
            logger.debug(
                f"{symbol}: SELL signal skipped — no open position (mirrors live SELL guard)"
            )
            return

        side = OrderSide.BUY if signal.signal_type == "BUY" else OrderSide.SELL

        # Mirror the live executor's per-strategy order type selection.
        # Momentum/breakout → MARKET (speed-critical, fills at ask/bid).
        # All others → LIMIT (patient fills, only when price is reached).
        order_type = OrderType(_scfg.order_type.upper()) if _scfg else _DEFAULT_ORDER_TYPE

        quantity = self.risk_manager.calculate_position_size(
            portfolio_value=portfolio_value,
            price=signal.price,
            signal_strength=signal.strength,
        )

        # 3. Validate with risk manager
        temp_order = Order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=signal.price,
            status=OrderStatus.PENDING,
        )
        is_valid, reason = self.risk_manager.validate_order(
            temp_order, portfolio_value, list(self.positions.values())
        )
        if not is_valid:
            logger.debug(f"Order rejected ({symbol}): {reason}")
            return

        # 4. Execute
        self._execute_backtest_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=signal.price,
            timestamp=market_data.timestamp,
            market_data=market_data,
            order_type=order_type,
        )

    def _update_equity_snapshot(self, ts_ms: int) -> None:
        """Record an equity snapshot and update the running drawdown peak.

        Args:
            ts_ms: Bar timestamp in milliseconds.
        """
        positions_value = sum(p.quantity * p.current_price for p in self.positions.values())
        equity = self.cash_balance + positions_value
        bar_time = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
        self.results.equity_curve.append((bar_time, equity))

        if equity > self._equity_peak:
            self._equity_peak = equity

        drawdown = self._equity_peak - equity
        if drawdown > self.results.max_drawdown:
            self.results.max_drawdown = drawdown
            if self._equity_peak > 0:
                self.results.max_drawdown_pct = float(drawdown / self._equity_peak * 100)

    def _force_close_positions(self) -> None:
        """Force-close any positions still open at the end of the test period."""
        for symbol, pos in self.positions.copy().items():
            close_side = OrderSide.SELL if pos.side == OrderSide.BUY else OrderSide.BUY
            self._execute_backtest_order(
                symbol=symbol,
                side=close_side,
                quantity=pos.quantity,
                price=pos.current_price,
                timestamp=datetime.now(UTC),
                market_data=None,
            )

    async def run(
        self,
        symbols: list[str],
        days: int = 30,
        interval: int = 60,
    ) -> BacktestResults:
        """Run the backtest and return aggregated results.

        For each bar, in order:
        1. Update open position prices.
        2. Check whether any position's SL/TP was breached (force-close if so).
        3. Ask the strategy for a signal on the remaining positions.
        4. Validate the proposed order with the risk manager.
        5. Execute the order (with slippage + fee).
        6. Record the equity snapshot and update the running drawdown peak.

        After all bars, open positions are force-closed at their last known
        price, the Sharpe ratio is computed, and the summary is printed.

        Args:
            symbols:  Trading pairs to backtest (e.g. ``["BTC-EUR"]``).
            days:     Historical look-back in calendar days.
            interval: Candle width in minutes (must be in ``VALID_INTERVALS``).

        Returns:
            Populated ``BacktestResults`` instance.
        """
        from src.config import settings

        currency_symbols = {"EUR": "€", "USD": "$", "GBP": "£"}
        currency_symbol = currency_symbols.get(settings.base_currency, settings.base_currency)

        logger.info("=" * 60)
        logger.info("STARTING BACKTEST")
        logger.info("=" * 60)
        logger.info(f"Strategy:        {self.strategy_type.value}")
        logger.info(f"Risk Level:      {self.risk_level.value}")
        logger.info(f"Initial Capital: {currency_symbol}{self.initial_capital:,.2f}")
        logger.info(f"Symbols:         {', '.join(symbols)}")
        logger.info(f"Period:          {days}d × {interval}min candles")
        logger.info("=" * 60)

        self._bars_per_24h = max(1, 24 * 60 // interval)
        self._high_low_buffer.clear()

        indexed: dict[str, dict[int, CandleData]] = {}
        for symbol in symbols:
            candles = await self.fetch_historical_data(symbol, days, interval)
            if candles:
                indexed[symbol] = {c.start: c for c in candles}

        if not indexed:
            logger.error("No historical data fetched — aborting backtest")
            return self.results

        all_timestamps = sorted(
            {ts for symbol_candles in indexed.values() for ts in symbol_candles}
        )
        total = len(all_timestamps)
        logger.info(f"Processing {total} bars across {len(indexed)} symbol(s)…")

        for idx, ts_ms in enumerate(all_timestamps):
            if total > 0 and idx % 100 == 0:
                logger.debug(f"Progress: {idx}/{total} ({idx / total * 100:.1f}%)")

            for symbol in symbols:
                candle = indexed.get(symbol, {}).get(ts_ms)
                if candle is None:
                    continue
                await self._process_bar_symbol(symbol, self._candle_to_market_data(candle, symbol))

            self._update_equity_snapshot(ts_ms)

        self._force_close_positions()
        self.results.final_capital = self.cash_balance
        self.results.compute_sharpe_ratio()

        logger.info("Backtest complete!")
        self.results.print_summary(currency_symbol=currency_symbol)

        return self.results
