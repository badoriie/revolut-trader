#!/usr/bin/env python3
"""CI-oriented backtest runner that outputs a Markdown report.

Used by the ``backtest-matrix`` GitHub Actions workflow to run a single
strategy and emit results as a Markdown table row.  The workflow
collects rows from all matrix jobs and posts them as a PR comment.

Environment variables
---------------------
ENVIRONMENT : str
    Must be ``dev`` so that the mock API client is used (no credentials).
"""

import argparse
import asyncio
import io
import json
import sys
from decimal import Decimal

from loguru import logger

from src.api import create_api_client
from src.backtest.engine import BacktestEngine
from src.config import RiskLevel, StrategyType, settings


def setup_logging() -> None:
    """Minimal logging — only errors to stderr so stdout stays clean."""
    logger.remove()
    logger.add(sys.stderr, level="WARNING")


async def run(strategy: str, risk: str, days: int, capital: float) -> None:
    """Run a single backtest and print a JSON result line to stdout."""
    strategy_type = StrategyType(strategy)
    risk_level = RiskLevel(risk)
    initial_capital = Decimal(str(capital))

    api_client = create_api_client(settings.environment)
    await api_client.initialize()

    engine = BacktestEngine(
        api_client=api_client,
        strategy_type=strategy_type,
        risk_level=risk_level,
        initial_capital=initial_capital,
    )

    try:
        # Suppress print_summary() output — the engine writes it to stdout
        real_stdout = sys.stdout
        sys.stdout = io.StringIO()
        results = await engine.run(
            symbols=["BTC-EUR", "ETH-EUR"],
            days=days,
            interval=60,
        )
        sys.stdout = real_stdout

        output = {
            "strategy": strategy,
            "risk": risk,
            "initial_capital": float(initial_capital),
            "final_capital": float(results.final_capital),
            "total_pnl": float(results.total_pnl),
            "return_pct": round(results.return_pct, 2),
            "total_trades": results.total_trades,
            "win_rate": round(results.win_rate, 2),
            "profit_factor": round(results.profit_factor, 2),
            "max_drawdown": float(results.max_drawdown),
            "max_drawdown_pct": round(results.max_drawdown_pct, 2),
            "sharpe_ratio": round(results.sharpe_ratio, 3),
            "status": "ok",
        }
    except Exception as e:
        sys.stdout = real_stdout
        output = {
            "strategy": strategy,
            "risk": risk,
            "status": "error",
            "error": str(e),
        }
    finally:
        await api_client.close()

    # Single JSON line to stdout — collected by the workflow
    print(json.dumps(output))


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="CI backtest runner")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--risk", default="conservative")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--capital", type=float, default=10000.0)
    args = parser.parse_args()

    setup_logging()

    try:
        asyncio.run(run(args.strategy, args.risk, args.days, args.capital))
    except Exception as e:
        print(
            json.dumps(
                {"strategy": args.strategy, "risk": args.risk, "status": "error", "error": str(e)}
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
