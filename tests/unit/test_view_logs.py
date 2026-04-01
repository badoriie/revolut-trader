"""Test the view_logs CLI script."""

from datetime import UTC, datetime

from cli.view_logs import format_log_entry


class TestFormatLogEntry:
    """Tests for format_log_entry function."""

    def test_formats_warning_with_session(self) -> None:
        """Test formatting a WARNING log with session ID."""
        log = {
            "timestamp": "2026-04-01 12:00:00",
            "level": "WARNING",
            "module": "src.bot",
            "message": "Something went wrong",
            "session_id": 42,
        }
        result = format_log_entry(log)

        assert "2026-04-01 12:00:00" in result
        assert "[WARNING" in result
        assert "src.bot" in result
        assert "Something went wrong" in result
        assert "(session: 42)" in result

    def test_formats_error_without_session(self) -> None:
        """Test formatting an ERROR log without session ID."""
        log = {
            "timestamp": "2026-04-01 13:00:00",
            "level": "ERROR",
            "module": "src.api.client",
            "message": "API call failed",
            "session_id": None,
        }
        result = format_log_entry(log)

        assert "2026-04-01 13:00:00" in result
        assert "[ERROR" in result
        assert "src.api.client" in result
        assert "API call failed" in result
        assert "(session:" not in result

    def test_formats_critical_log(self) -> None:
        """Test formatting a CRITICAL log."""
        log = {
            "timestamp": "2026-04-01 14:00:00",
            "level": "CRITICAL",
            "module": "src.execution.executor",
            "message": "Critical failure",
            "session_id": 1,
        }
        result = format_log_entry(log)

        assert "2026-04-01 14:00:00" in result
        assert "[CRITICAL" in result
        assert "src.execution.executor" in result
        assert "Critical failure" in result

    def test_handles_datetime_object(self) -> None:
        """Test formatting with datetime object instead of string."""
        log = {
            "timestamp": datetime(2026, 4, 1, 15, 30, 45, tzinfo=UTC),
            "level": "WARNING",
            "module": "test",
            "message": "Test message",
        }
        result = format_log_entry(log)

        # Should convert to string format
        assert "2026-04-01 15:30:45" in result
