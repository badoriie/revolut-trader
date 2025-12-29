#!/usr/bin/env python3
"""Database management CLI tool.

Provides commands to manage the trading bot database:
- Export data to JSON/CSV
- Migrate between SQLite and PostgreSQL
- Show analytics and statistics
- Backup and restore data
"""

import sys
from pathlib import Path

from loguru import logger

from src.utils.db_migration import DatabaseMigration
from src.utils.db_persistence import DatabasePersistence
from src.utils.hybrid_persistence import HybridPersistence


def show_analytics(days: int = 30):
    """Show trading analytics for the last N days."""
    db = DatabasePersistence()
    analytics = db.get_analytics(days=days)

    if not analytics:
        print("No analytics data available")
        return

    print(f"\n📊 Trading Analytics (Last {days} days)")
    print("=" * 50)
    print(f"Total Snapshots: {analytics.get('total_snapshots', 0)}")
    print(f"Total Trades: {analytics.get('total_trades', 0)}")
    print(f"Winning Trades: {analytics.get('winning_trades', 0)}")
    print(f"Win Rate: {analytics.get('win_rate', 0):.1f}%")
    print(f"Total P&L: ${analytics.get('total_pnl', 0):.2f}")

    if "initial_value" in analytics:
        print(f"Initial Value: ${analytics['initial_value']:.2f}")
        print(f"Final Value: ${analytics['final_value']:.2f}")
        print(f"Return: {analytics.get('return_pct', 0):.2f}%")

    print("=" * 50)


def export_data(output_dir: str = "data/exports"):
    """Export all database data to JSON files."""
    print(f"\n📤 Exporting data to {output_dir}...")

    migrator = DatabaseMigration("sqlite:///data/trading.db")
    files = migrator.export_to_json(Path(output_dir))

    print(f"\n✓ Export complete: {len(files)} files created")
    for data_type, file_path in files.items():
        print(f"  - {data_type}: {file_path}")


def export_csv():
    """Export data to CSV files for analysis."""
    print("\n📊 Exporting to CSV...")

    persistence = HybridPersistence()
    persistence.export_to_csv()

    print("✓ CSV export complete")


def migrate_to_postgres(postgres_url: str):
    """Migrate SQLite database to PostgreSQL."""
    print("\n🔄 Migrating SQLite to PostgreSQL...")
    print(f"Target: {postgres_url}")

    from src.utils.db_migration import migrate_sqlite_to_postgres

    success = migrate_sqlite_to_postgres(postgres_url=postgres_url)

    if success:
        print("\n✓ Migration completed successfully")
    else:
        print("\n✗ Migration failed - check logs for details")
        sys.exit(1)


def show_stats():
    """Show database statistics."""
    db = DatabasePersistence()

    print("\n📈 Database Statistics")
    print("=" * 50)

    # Count snapshots
    snapshots = db.load_portfolio_snapshots(limit=1000000)
    print(f"Portfolio Snapshots: {len(snapshots)}")

    # Count trades
    trades = db.load_trade_history(limit=1000000)
    print(f"Total Trades: {len(trades)}")

    # Recent activity
    if snapshots:
        latest = snapshots[-1]
        print("\nLatest Snapshot:")
        print(f"  Timestamp: {latest['timestamp']}")
        print(f"  Total Value: ${latest['total_value']}")
        print(f"  P&L: ${latest['total_pnl']}")

    if trades:
        latest_trade = trades[-1]
        print("\nLatest Trade:")
        print(f"  Symbol: {latest_trade['symbol']}")
        print(f"  Side: {latest_trade['side']}")
        print(f"  Quantity: {latest_trade['quantity']}")
        print(f"  Price: ${latest_trade['price']}")

    print("=" * 50)


def main():
    """Main entry point for database management CLI."""
    if len(sys.argv) < 2:
        print("Database Management CLI")
        print("\nUsage:")
        print("  python cli/db_manage.py <command> [options]")
        print("\nCommands:")
        print("  stats              - Show database statistics")
        print("  analytics [days]   - Show trading analytics (default: 30 days)")
        print("  export [dir]       - Export data to JSON (default: data/exports)")
        print("  export-csv         - Export data to CSV for analysis")
        print("  migrate <pg_url>   - Migrate SQLite to PostgreSQL")
        print("\nExamples:")
        print("  python cli/db_manage.py stats")
        print("  python cli/db_manage.py analytics 7")
        print("  python cli/db_manage.py export data/backup")
        print("  python cli/db_manage.py migrate postgresql://user:pass@localhost/trading")
        sys.exit(1)

    command = sys.argv[1]

    try:
        if command == "stats":
            show_stats()

        elif command == "analytics":
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            show_analytics(days)

        elif command == "export":
            output_dir = sys.argv[2] if len(sys.argv) > 2 else "data/exports"
            export_data(output_dir)

        elif command == "export-csv":
            export_csv()

        elif command == "migrate":
            if len(sys.argv) < 3:
                print("Error: PostgreSQL URL required")
                print("Example: postgresql://user:password@localhost/trading")
                sys.exit(1)
            postgres_url = sys.argv[2]
            migrate_to_postgres(postgres_url)

        else:
            print(f"Unknown command: {command}")
            print("Run without arguments to see available commands")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Command failed: {e}", exc_info=True)
        print(f"\n✗ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
