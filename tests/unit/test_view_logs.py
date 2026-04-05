"""Test the view_logs CLI script."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from cli.utils.view_logs import follow_logs, format_log_entry, view_logs


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

    def test_missing_optional_fields_defaults(self) -> None:
        """Test that missing module and message use defaults."""
        log = {
            "timestamp": "2026-04-01 12:00:00",
            "level": "ERROR",
        }
        result = format_log_entry(log)
        assert "unknown" in result


class TestViewLogs:
    """Tests for view_logs function."""

    def _make_log(self, msg: str, session_id=None, log_id: int = 1) -> dict:
        return {
            "id": log_id,
            "timestamp": "2026-04-01 12:00:00",
            "level": "ERROR",
            "module": "src.bot",
            "message": msg,
            "session_id": session_id,
        }

    def test_no_logs_found(self, capsys) -> None:
        """Empty DB prints no-logs message."""
        persistence = MagicMock()
        persistence.load_log_entries.return_value = []
        view_logs(persistence)
        assert "No logs found." in capsys.readouterr().out

    def test_shows_valid_logs(self, capsys) -> None:
        """Normal logs are displayed."""
        persistence = MagicMock()
        persistence.load_log_entries.return_value = [self._make_log("connection error")]
        view_logs(persistence)
        out = capsys.readouterr().out
        assert "connection error" in out
        assert "Showing 1 log entries" in out

    def test_skips_encrypted_messages(self, capsys) -> None:
        """Logs with Fernet-encrypted messages (gAAAAA prefix) are skipped."""
        persistence = MagicMock()
        persistence.load_log_entries.return_value = [self._make_log("gAAAAAbaddata==")]
        view_logs(persistence)
        assert "No logs found." in capsys.readouterr().out

    def test_skips_empty_messages(self, capsys) -> None:
        """Logs with empty message strings are skipped."""
        persistence = MagicMock()
        persistence.load_log_entries.return_value = [self._make_log("")]
        view_logs(persistence)
        assert "No logs found." in capsys.readouterr().out

    def test_skips_none_messages(self, capsys) -> None:
        """Logs with None message are skipped."""
        persistence = MagicMock()
        log = self._make_log("placeholder")
        log["message"] = None
        persistence.load_log_entries.return_value = [log]
        view_logs(persistence)
        assert "No logs found." in capsys.readouterr().out

    def test_session_filter_includes_matching(self, capsys) -> None:
        """Only logs with the given session_id are shown."""
        persistence = MagicMock()
        persistence.load_log_entries.return_value = [
            self._make_log("session1 msg", session_id=1, log_id=1),
            self._make_log("session2 msg", session_id=2, log_id=2),
        ]
        view_logs(persistence, session_id=1)
        out = capsys.readouterr().out
        assert "session1 msg" in out
        assert "session2 msg" not in out

    def test_limit_caps_output(self, capsys) -> None:
        """At most `limit` logs are shown."""
        persistence = MagicMock()
        logs = [self._make_log(f"msg{i}", log_id=i) for i in range(10)]
        persistence.load_log_entries.return_value = logs
        view_logs(persistence, limit=3)
        out = capsys.readouterr().out
        assert "Showing 3 log entries" in out

    def test_session_filter_uses_larger_load_limit(self) -> None:
        """When session_id is provided, load_limit is multiplied to account for skipped rows."""
        persistence = MagicMock()
        persistence.load_log_entries.return_value = []
        view_logs(persistence, limit=5, session_id=99)
        call_kwargs = persistence.load_log_entries.call_args
        assert call_kwargs.kwargs["limit"] == 100  # 5 * 20


class TestFollowLogs:
    """Tests for follow_logs function."""

    def test_follow_exits_on_keyboard_interrupt(self, capsys) -> None:
        """KeyboardInterrupt stops following and prints exit message."""
        persistence = MagicMock()
        persistence.load_log_entries.return_value = [
            {
                "id": 1,
                "timestamp": "2026-04-01 12:00:00",
                "level": "ERROR",
                "module": "test",
                "message": "initial",
                "session_id": None,
            },
        ]

        with patch("cli.utils.view_logs.time.sleep", side_effect=KeyboardInterrupt):
            follow_logs(persistence)

        out = capsys.readouterr().out
        assert "Following logs" in out
        assert "Stopped following logs." in out

    def test_follow_displays_new_logs(self, capsys) -> None:
        """New log entries (id > last_id) are printed."""
        persistence = MagicMock()
        # First call (limit=1) sets last_id=1; second call (limit=100) returns new log with id=2.
        call_results = [
            [
                {
                    "id": 1,
                    "timestamp": "2026-04-01 12:00:00",
                    "level": "ERROR",
                    "module": "test",
                    "message": "old",
                    "session_id": None,
                }
            ],
            [
                {
                    "id": 1,
                    "timestamp": "2026-04-01 12:00:00",
                    "level": "ERROR",
                    "module": "test",
                    "message": "old",
                    "session_id": None,
                },
                {
                    "id": 2,
                    "timestamp": "2026-04-01 12:00:01",
                    "level": "ERROR",
                    "module": "test",
                    "message": "new_log_msg",
                    "session_id": None,
                },
            ],
        ]
        call_iter = iter(call_results)

        def load_side_effect(*args, **kwargs):
            try:
                return next(call_iter)
            except StopIteration:
                raise KeyboardInterrupt from None

        persistence.load_log_entries.side_effect = load_side_effect

        with patch("cli.utils.view_logs.time.sleep"):
            follow_logs(persistence)

        assert "new_log_msg" in capsys.readouterr().out

    def test_follow_applies_session_filter(self, capsys) -> None:
        """follow_logs filters by session_id when provided."""
        persistence = MagicMock()
        call_results = [
            [],  # initial limit=1 call
            [
                {
                    "id": 1,
                    "timestamp": "2026-04-01 12:00:00",
                    "level": "ERROR",
                    "module": "test",
                    "message": "s1_msg",
                    "session_id": 1,
                },
                {
                    "id": 2,
                    "timestamp": "2026-04-01 12:00:01",
                    "level": "ERROR",
                    "module": "test",
                    "message": "s2_msg",
                    "session_id": 2,
                },
            ],
        ]
        call_iter = iter(call_results)

        def load_side_effect(*args, **kwargs):
            try:
                return next(call_iter)
            except StopIteration:
                raise KeyboardInterrupt from None

        persistence.load_log_entries.side_effect = load_side_effect

        with patch("cli.utils.view_logs.time.sleep"):
            follow_logs(persistence, session_id=1)

        out = capsys.readouterr().out
        assert "s1_msg" in out
        assert "s2_msg" not in out

    def test_follow_skips_undecryptable_logs(self, capsys) -> None:
        """Logs that raise exceptions during formatting are silently skipped."""
        persistence = MagicMock()
        call_results = [
            [],
            [{"id": 1, "timestamp": None, "level": None, "module": None, "message": "bad"}],
        ]
        call_iter = iter(call_results)

        def load_side_effect(*args, **kwargs):
            try:
                return next(call_iter)
            except StopIteration:
                raise KeyboardInterrupt from None

        persistence.load_log_entries.side_effect = load_side_effect

        with (
            patch("cli.utils.view_logs.time.sleep"),
            patch("cli.utils.view_logs.format_log_entry", side_effect=Exception("decrypt error")),
        ):
            follow_logs(persistence)  # should not raise


class TestViewLogsMain:
    """Tests for main() entry point."""

    def _run_main(self, argv, mock_logs=None):
        from cli.utils.view_logs import main

        if mock_logs is None:
            mock_logs = []
        with (
            patch.object(sys, "argv", argv),
            patch("cli.utils.view_logs.DatabasePersistence") as mock_db_cls,
        ):
            mock_db_cls.return_value.load_log_entries.return_value = mock_logs
            mock_db_cls.return_value.load_log_entries.return_value = mock_logs
            main()
            return mock_db_cls

    def test_main_default_shows_view_logs(self, capsys) -> None:
        """main() with no args runs view_logs and prints no-logs message."""
        self._run_main(["view_logs"])
        assert "No logs found." in capsys.readouterr().out

    def test_main_follow_flag_calls_follow_logs(self, capsys) -> None:
        """--follow flag invokes follow_logs."""
        with (
            patch.object(sys, "argv", ["view_logs", "--follow"]),
            patch("cli.utils.view_logs.DatabasePersistence") as mock_db_cls,
            patch("cli.utils.view_logs.follow_logs") as mock_follow,
        ):
            mock_db_cls.return_value.load_log_entries.return_value = []
            from cli.utils.view_logs import main

            main()
        mock_follow.assert_called_once()

    def test_main_level_and_limit_args(self, capsys) -> None:
        """--level and --limit are passed through to view_logs."""
        with (
            patch.object(sys, "argv", ["view_logs", "--level", "ERROR", "--limit", "5"]),
            patch("cli.utils.view_logs.DatabasePersistence") as mock_db_cls,
            patch("cli.utils.view_logs.view_logs") as mock_view,
        ):
            mock_db_cls.return_value.load_log_entries.return_value = []
            from cli.utils.view_logs import main

            main()
        mock_view.assert_called_once()
        _, kwargs = mock_view.call_args
        assert kwargs["level"] == "ERROR"
        assert kwargs["limit"] == 5

    def test_main_session_arg(self, capsys) -> None:
        """--session is passed through to view_logs."""
        with (
            patch.object(sys, "argv", ["view_logs", "--session", "42"]),
            patch("cli.utils.view_logs.DatabasePersistence") as mock_db_cls,
            patch("cli.utils.view_logs.view_logs") as mock_view,
        ):
            mock_db_cls.return_value.load_log_entries.return_value = []
            from cli.utils.view_logs import main

            main()
        _, kwargs = mock_view.call_args
        assert kwargs["session_id"] == 42

    def test_main_sets_environment_if_missing(self) -> None:
        """main() sets ENVIRONMENT from git detection when not already set."""
        import os

        from cli.utils.view_logs import main

        original = os.environ.pop("ENVIRONMENT", None)
        try:
            with (
                patch.object(sys, "argv", ["view_logs"]),
                patch("cli.utils.view_logs._detect_env", return_value="dev"),
                patch("cli.utils.view_logs.DatabasePersistence") as mock_db_cls,
            ):
                mock_db_cls.return_value.load_log_entries.return_value = []
                main()
            assert os.environ.get("ENVIRONMENT") == "dev"
        finally:
            if original is not None:
                os.environ["ENVIRONMENT"] = original
            else:
                os.environ.pop("ENVIRONMENT", None)
