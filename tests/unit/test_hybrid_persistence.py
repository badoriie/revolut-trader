"""Tests for DatabasePersistence.export_to_csv."""

from unittest.mock import MagicMock, patch


@patch("src.utils.db_persistence.DatabaseEncryption")
@patch("src.utils.db_persistence.create_db_engine")
@patch("src.utils.db_persistence.get_session_factory")
@patch("src.utils.db_persistence.init_database")
def make_db(init_db, get_sf, create_eng, db_enc):
    from src.utils.db_persistence import DatabasePersistence

    db = DatabasePersistence.__new__(DatabasePersistence)
    db.encryption = MagicMock()
    db.encryption.is_enabled = False
    return db


class TestExportToCsv:
    def test_export_creates_csv_files(self, tmp_path):
        db = make_db()
        db.load_trade_history = MagicMock(
            return_value=[
                {
                    "symbol": "BTC-EUR",
                    "side": "BUY",
                    "quantity": "0.1",
                    "price": "50000",
                    "status": "FILLED",
                    "created_at": "2024-01-01T00:00:00",
                }
            ]
        )
        db.load_portfolio_snapshots = MagicMock(
            return_value=[{"timestamp": "2024-01-01T00:00:00", "total_value": "10000"}]
        )
        db.export_to_csv(output_dir=tmp_path / "exports")
        assert len(list((tmp_path / "exports").glob("*.csv"))) == 2

    def test_export_handles_empty_data(self, tmp_path):
        db = make_db()
        db.load_trade_history = MagicMock(return_value=[])
        db.load_portfolio_snapshots = MagicMock(return_value=[])
        db.export_to_csv(output_dir=tmp_path / "exports")
        # Should not raise
