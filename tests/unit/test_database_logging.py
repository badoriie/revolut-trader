"""Tests for database logging functionality."""

import pytest
from loguru import logger

from src.bot import _setup_database_logging
from src.utils.db_persistence import DatabasePersistence


class TestDatabaseLogging:
    """Test that logs are automatically saved to the database."""

    @pytest.fixture
    def persistence(self):
        """Create a DatabasePersistence instance for testing."""
        return DatabasePersistence()

    def test_setup_database_logging_returns_sink_id(self, persistence):
        """Database logging setup should return a sink ID."""
        sink_id = _setup_database_logging(persistence, session_id=1)
        assert isinstance(sink_id, int)
        logger.remove(sink_id)

    def test_warning_logs_saved_to_database(self, persistence):
        """WARNING logs should be saved to the database."""
        session_id = 1001  # Use unique session
        sink_id = _setup_database_logging(persistence, session_id=session_id)

        # Log a warning
        test_message = "Test warning unique message 1001"
        logger.warning(test_message)

        # Query logs from database - only get recent logs to avoid old encrypted data
        all_logs = persistence.load_log_entries(since=None, level="WARNING", limit=100)

        # Filter to only logs that can be decrypted and match our session
        # (old logs from previous test runs may fail to decrypt with current key)
        valid_logs = []
        for log in all_logs:
            try:
                if log.get("session_id") == session_id and log.get("message"):
                    valid_logs.append(log)
            except Exception:
                continue  # Skip logs that can't be decrypted

        # Verify the log was saved
        assert len(valid_logs) > 0, "No logs found for this session"
        assert any(test_message in log["message"] for log in valid_logs), (
            "Test message not found in logs"
        )
        assert all(log["level"] == "WARNING" for log in valid_logs)
        assert all(log["session_id"] == session_id for log in valid_logs)

        logger.remove(sink_id)

    def test_error_logs_saved_to_database(self, persistence):
        """ERROR logs should be saved to the database."""
        session_id = 43
        sink_id = _setup_database_logging(persistence, session_id=session_id)

        # Log an error
        test_message = "This is a test error message"
        logger.error(test_message)

        # Query logs from database
        logs = persistence.load_log_entries(since=None, level="ERROR")

        # Verify the log was saved
        assert len(logs) > 0
        assert any(test_message in log["message"] for log in logs)
        assert any(log["level"] == "ERROR" for log in logs)

        logger.remove(sink_id)

    def test_critical_logs_saved_to_database(self, persistence):
        """CRITICAL logs should be saved to the database."""
        session_id = 44
        sink_id = _setup_database_logging(persistence, session_id=session_id)

        # Log a critical error
        test_message = "This is a test critical message"
        logger.critical(test_message)

        # Query logs from database
        logs = persistence.load_log_entries(since=None, level="CRITICAL")

        # Verify the log was saved
        assert len(logs) > 0
        assert any(test_message in log["message"] for log in logs)
        assert any(log["level"] == "CRITICAL" for log in logs)

        logger.remove(sink_id)

    def test_info_logs_not_saved_to_database(self, persistence):
        """INFO logs should NOT be saved to the database (only stdout)."""
        session_id = 999  # Use unique session to avoid key conflicts
        sink_id = _setup_database_logging(persistence, session_id=session_id)

        # Log an info message - it shouldn't trigger database save
        logger.info("This is a test info message that should not be saved")

        # Query logs for this specific session only
        all_logs = persistence.load_log_entries(since=None)
        session_logs = [log for log in all_logs if log.get("session_id") == session_id]

        # Verify no logs were saved for this session (INFO is filtered out)
        assert len(session_logs) == 0

        logger.remove(sink_id)

    def test_debug_logs_not_saved_to_database(self, persistence):
        """DEBUG logs should NOT be saved to the database."""
        session_id = 998  # Use unique session
        sink_id = _setup_database_logging(persistence, session_id=session_id)

        # Log a debug message - it shouldn't trigger database save
        logger.debug("This debug message should not be saved")

        # Query logs for this specific session only
        all_logs = persistence.load_log_entries(since=None)
        session_logs = [log for log in all_logs if log.get("session_id") == session_id]

        # Verify no logs were saved for this session (DEBUG is filtered out)
        assert len(session_logs) == 0

        logger.remove(sink_id)

    def test_sink_can_be_removed(self, persistence):
        """Database logging sink should be removable."""
        session_id = 997  # Use unique session
        sink_id = _setup_database_logging(persistence, session_id=session_id)

        # Remove the sink
        logger.remove(sink_id)

        # Log a warning - should not be saved after sink removal
        logger.warning("This should not be saved after sink removal")

        # Query logs for this specific session
        all_logs = persistence.load_log_entries(since=None)
        session_logs = [log for log in all_logs if log.get("session_id") == session_id]

        # Verify no logs were saved for this session (sink was removed)
        assert len(session_logs) == 0

    def test_logs_include_module_name(self, persistence):
        """Saved logs should include the module name."""
        session_id = 48
        sink_id = _setup_database_logging(persistence, session_id=session_id)

        # Log from this test module
        logger.warning("Test message with module name")

        # Query logs
        logs = persistence.load_log_entries(since=None, level="WARNING")

        # Verify module name is present
        assert len(logs) > 0
        assert any("test_database_logging" in log.get("module", "") for log in logs)

        logger.remove(sink_id)
