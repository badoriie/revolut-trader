#!/usr/bin/env python3
"""Database management CLI tool."""

import json
import sys
from datetime import datetime, UTC
from pathlib import Path

from loguru import logger

from src.utils.db_persistence import DatabasePersistence
from src.utils.hybrid_persistence import HybridPersistence


def show_analytics(days: int = 30):
    """Show trading analytics for the last N days."""
    db = DatabasePersistence()
    analytics = db.get_analytics(days=days)

    if not analytics:
        print("No analytics data available")
        return

    print(f"\n Trading Analytics (Last {days} days)")
    print("=" * 50)
    print(f"Total Snapshots: {analytics.get('total_snapshots', 0)}")
    print(f"Total Trades:    {analytics.get('total_trades', 0)}")
    print(f"Winning Trades:  {analytics.get('winning_trades', 0)}")
    print(f"Win Rate:        {analytics.get('win_rate', 0):.1f}%")
    print(f"Total P&L:       ${analytics.get('total_pnl', 0):.2f}")

    if "initial_value" in analytics:
        print(f"Initial Value:   ${analytics['initial_value']:.2f}")
        print(f"Final Value:     ${analytics['final_value']:.2f}")
        print(f"Return:          {analytics.get('return_pct', 0):.2f}%")

    print("=" * 50)


def export_data(output_dir: str = "data/exports"):
    """Export all database data to JSON files."""
    print(f"\nExporting data to {output_dir}...")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    db = DatabasePersistence()
    files = {}

    snapshots = db.load_portfolio_snapshots(limit=1_000_000)
    if snapshots:
        path = out / f"portfolio_snapshots_{timestamp}.json"
        path.write_text(json.dumps(snapshots, indent=2, default=str))
        files["snapshots"] = path
        print(f"  snapshots: {path} ({len(snapshots)} records)")

    trades = db.load_trade_history(limit=1_000_000)
    if trades:
        path = out / f"trades_{timestamp}.json"
        path.write_text(json.dumps(trades, indent=2, default=str))
        files["trades"] = path
        print(f"  trades:    {path} ({len(trades)} records)")

    analytics = db.get_analytics(days=365)
    if analytics:
        path = out / f"analytics_{timestamp}.json"
        path.write_text(json.dumps(analytics, indent=2, default=str))
        files["analytics"] = path
        print(f"  analytics: {path}")

    print(f"\nExport complete: {len(files)} files created")


def export_csv():
    """Export data to CSV files."""
    print("\nExporting to CSV...")
    HybridPersistence().export_to_csv()
    print("CSV export complete")


def show_stats():
    """Show database statistics."""
    db = DatabasePersistence()

    print("\n Database Statistics")
    print("=" * 50)

    snapshots = db.load_portfolio_snapshots(limit=1_000_000)
    print(f"Portfolio Snapshots: {len(snapshots)}")

    trades = db.load_trade_history(limit=1_000_000)
    print(f"Total Trades:        {len(trades)}")

    if snapshots:
        latest = snapshots[-1]
        print("\nLatest Snapshot:")
        print(f"  Timestamp:   {latest['timestamp']}")
        print(f"  Total Value: ${latest['total_value']}")
        print(f"  P&L:         ${latest['total_pnl']}")

    if trades:
        t = trades[-1]
        print("\nLatest Trade:")
        print(f"  Symbol:   {t['symbol']}")
        print(f"  Side:     {t['side']}")
        print(f"  Quantity: {t['quantity']}")
        print(f"  Price:    ${t['price']}")

    print("=" * 50)


def show_backtest_results(limit: int = 10):
    """Show recent backtest results."""
    db = DatabasePersistence()
    runs = db.load_backtest_runs(limit=limit)

    if not runs:
        print("No backtest results found")
        return

    print(f"\n Recent Backtest Runs (Last {len(runs)})")
    print("=" * 80)

    for run in runs:
        print(f"\nID: {run['id']} | {run['run_at']}")
        print(f"Strategy: {run['strategy']} | Risk: {run['risk_level']}")
        print(f"Symbols: {', '.join(run['symbols'])} | Days: {run['days']}")
        print(f"Return: {run['return_pct']:.2f}% | Trades: {run['total_trades']}")
        print(f"Win Rate: {run['win_rate']:.1f}% | Max DD: {run['max_drawdown']:.2f}%")
        if run["profit_factor"]:
            print(f"Profit Factor: {run['profit_factor']:.2f}")

    print("=" * 80)

    analytics = db.get_backtest_analytics()
    if analytics:
        print("\n Backtest Analytics")
        print("=" * 50)
        print(f"Total Runs:    {analytics['total_runs']}")
        print(f"Profitable:    {analytics['profitable_runs']} ({analytics['success_rate']:.1f}%)")
        print(f"Avg Return:    {analytics['avg_return_pct']:.2f}%")

        if "best_run" in analytics:
            best = analytics["best_run"]
            print(f"\nBest Run: ID {best['id']}")
            print(f"  Strategy: {best['strategy']}")
            print(f"  Return:   {best['return_pct']:.2f}%")
            print(f"  Win Rate: {best['win_rate']:.1f}%")

        print("=" * 50)


def main():
    if len(sys.argv) < 2:
        print("Usage: python cli/db_manage.py <command> [options]")
        print("\nCommands:")
        print("  stats              - Show database statistics")
        print("  analytics [days]   - Show trading analytics (default: 30 days)")
        print("  backtests [limit]  - Show backtest results (default: 10)")
        print("  export [dir]       - Export data to JSON (default: data/exports)")
        print("  export-csv         - Export data to CSV")
        sys.exit(1)

    command = sys.argv[1]

    try:
        if command == "stats":
            show_stats()
        elif command == "analytics":
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            show_analytics(days)
        elif command == "backtests":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            show_backtest_results(limit)
        elif command == "export":
            output_dir = sys.argv[2] if len(sys.argv) > 2 else "data/exports"
            export_data(output_dir)
        elif command == "export-csv":
            export_csv()
        else:
            print(f"Unknown command: {command}")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Command failed: {e}", exc_info=True)
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()