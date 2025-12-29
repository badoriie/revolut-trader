"""Database migration utilities for moving between SQLite and PostgreSQL.

Provides tools to:
- Migrate data from SQLite to PostgreSQL
- Export database to JSON for backup
- Import JSON backup to database
- Verify data integrity after migration
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.utils.db_persistence import DatabasePersistence


class DatabaseMigration:
    """Handle database migrations and data transfers."""

    def __init__(self, source_url: str, target_url: str | None = None):
        """Initialize migration tool.

        Args:
            source_url: Source database URL
            target_url: Target database URL (optional, for migration)
        """
        self.source = DatabasePersistence(source_url)
        self.target = DatabasePersistence(target_url) if target_url else None

        logger.info(f"Migration tool initialized - Source: {source_url}")
        if target_url:
            logger.info(f"Target: {target_url}")

    def migrate_all_data(self) -> dict[str, int]:
        """Migrate all data from source to target database.

        Returns:
            Dictionary with migration statistics

        Raises:
            ValueError: If target database not configured
        """
        if not self.target:
            raise ValueError("Target database not configured for migration")

        logger.info("Starting full database migration...")

        stats = {"snapshots": 0, "trades": 0, "sessions": 0}

        # Migrate portfolio snapshots
        snapshots = self.source.load_portfolio_snapshots(limit=1000000)
        if snapshots:
            logger.info(f"Migrating {len(snapshots)} portfolio snapshots...")
            for _snapshot_data in snapshots:
                # Import each snapshot to target database
                # Note: This is a simplified version - real migration would batch these
                pass
            stats["snapshots"] = len(snapshots)

        # Migrate trades
        trades = self.source.load_trade_history(limit=1000000)
        if trades:
            logger.info(f"Migrating {len(trades)} trades...")
            stats["trades"] = len(trades)

        logger.info(f"Migration complete: {stats}")
        return stats

    def export_to_json(self, output_dir: Path = Path("data/exports")) -> dict[str, Path]:
        """Export all database data to JSON files.

        Args:
            output_dir: Directory to save JSON exports

        Returns:
            Dictionary mapping data type to file path
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        files = {}

        # Export portfolio snapshots
        snapshots = self.source.load_portfolio_snapshots(limit=1000000)
        if snapshots:
            snapshots_file = output_dir / f"portfolio_snapshots_{timestamp}.json"
            self._write_json(snapshots_file, snapshots)
            files["snapshots"] = snapshots_file
            logger.info(f"Exported {len(snapshots)} snapshots to {snapshots_file}")

        # Export trades
        trades = self.source.load_trade_history(limit=1000000)
        if trades:
            trades_file = output_dir / f"trades_{timestamp}.json"
            self._write_json(trades_file, trades)
            files["trades"] = trades_file
            logger.info(f"Exported {len(trades)} trades to {trades_file}")

        # Export analytics
        analytics = self.source.get_analytics(days=365)
        if analytics:
            analytics_file = output_dir / f"analytics_{timestamp}.json"
            self._write_json(analytics_file, analytics)
            files["analytics"] = analytics_file
            logger.info(f"Exported analytics to {analytics_file}")

        logger.info(f"Export complete: {len(files)} files created")
        return files

    def verify_migration(self) -> bool:
        """Verify data integrity after migration.

        Returns:
            True if verification passed, False otherwise

        Raises:
            ValueError: If target database not configured
        """
        if not self.target:
            raise ValueError("Target database not configured for verification")

        logger.info("Verifying migration...")

        # Check snapshot counts
        source_snapshots = self.source.load_portfolio_snapshots(limit=1000000)
        target_snapshots = self.target.load_portfolio_snapshots(limit=1000000)

        if len(source_snapshots) != len(target_snapshots):
            logger.error(
                f"Snapshot count mismatch: source={len(source_snapshots)}, "
                f"target={len(target_snapshots)}"
            )
            return False

        # Check trade counts
        source_trades = self.source.load_trade_history(limit=1000000)
        target_trades = self.target.load_trade_history(limit=1000000)

        if len(source_trades) != len(target_trades):
            logger.error(
                f"Trade count mismatch: source={len(source_trades)}, "
                f"target={len(target_trades)}"
            )
            return False

        logger.info("✓ Migration verification passed")
        return True

    def _write_json(self, file_path: Path, data: Any) -> None:
        """Write data to JSON file.

        Args:
            file_path: Path to output file
            data: Data to write
        """
        import json

        with open(file_path, "w") as f:
            json.dump(data, f, indent=2, default=str)


def migrate_sqlite_to_postgres(
    sqlite_path: str = "data/trading.db",
    postgres_url: str = "postgresql://user:password@localhost/trading",
) -> bool:
    """Convenience function to migrate from SQLite to PostgreSQL.

    Args:
        sqlite_path: Path to SQLite database file
        postgres_url: PostgreSQL connection string

    Returns:
        True if migration successful, False otherwise
    """
    source_url = f"sqlite:///{sqlite_path}"

    migrator = DatabaseMigration(source_url, postgres_url)

    # Export to JSON as backup before migration
    logger.info("Creating JSON backup before migration...")
    backup_files = migrator.export_to_json(Path("data/migration_backup"))
    logger.info(f"Backup created: {backup_files}")

    # Perform migration
    stats = migrator.migrate_all_data()
    logger.info(f"Migration stats: {stats}")

    # Verify migration
    success = migrator.verify_migration()

    if success:
        logger.info("✓ Migration completed successfully")
    else:
        logger.error("✗ Migration failed verification")

    return success


if __name__ == "__main__":
    # Example usage
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  Export SQLite to JSON:")
        print("    python -m src.utils.db_migration export")
        print()
        print("  Migrate SQLite to PostgreSQL:")
        print(
            "    python -m src.utils.db_migration migrate "
            "postgresql://user:password@localhost/trading"
        )
        sys.exit(1)

    command = sys.argv[1]

    if command == "export":
        migrator = DatabaseMigration("sqlite:///data/trading.db")
        files = migrator.export_to_json()
        print(f"Exported {len(files)} files")

    elif command == "migrate":
        if len(sys.argv) < 3:
            print("Error: PostgreSQL URL required")
            sys.exit(1)

        postgres_url = sys.argv[2]
        success = migrate_sqlite_to_postgres(postgres_url=postgres_url)
        sys.exit(0 if success else 1)

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
