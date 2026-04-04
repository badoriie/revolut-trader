"""Comprehensive tests for cli/revt.py — the revt CLI entry point.

Covers all public functions in the module: pure helpers, 1Password wrappers,
update-check machinery, command dispatchers (run, backtest, ops, config, api,
telegram, db, update), the argparse builder, and the main() entry point.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cli.revt import (
    _build_parser,
    _check_binary_version,
    _check_for_updates,
    _check_op,
    _config_delete,
    _config_init,
    _config_set,
    _config_show,
    _detect_env,
    _env_badge,
    _get_binary_name_for_platform,
    _get_current_version_from_pyproject,
    _get_git_commits,
    _get_latest_github_release,
    _handle_live_mode_confirmation,
    _mask_secret,
    _op,
    _op_config_item,
    _op_creds_item,
    _ops_set_creds,
    _ops_show,
    _ops_status,
    _print_run_config,
    _read_update_cache,
    _resolve_env,
    _run_compare_cli,
    _setup_logger,
    _show_update_notification,
    _stash_local_changes,
    _update_from_binary,
    _update_from_source,
    _verify_git_repository,
    _write_update_cache,
    cmd_api,
    cmd_backtest,
    cmd_config,
    cmd_db,
    cmd_ops,
    cmd_run,
    cmd_telegram,
    cmd_update,
    main,
)

# ---------------------------------------------------------------------------
# Helpers to build argparse.Namespace objects quickly
# ---------------------------------------------------------------------------


def _ns(**kwargs) -> argparse.Namespace:
    """Shorthand to build an argparse.Namespace with defaults."""
    return argparse.Namespace(**kwargs)


# ---------------------------------------------------------------------------
# _detect_env
# ---------------------------------------------------------------------------


class TestDetectEnv:
    """Tests for _detect_env() — auto-detection of environment."""

    def test_frozen_binary_returns_prod(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        assert _detect_env() == "prod"

    def test_feature_branch_returns_dev(self):
        result = MagicMock(returncode=0, stdout="feature/foo\n")
        with patch("subprocess.run", return_value=result):
            assert _detect_env() == "dev"

    def test_main_branch_no_tag_returns_int(self):
        branch_result = MagicMock(returncode=0, stdout="main\n")
        tag_result = MagicMock(returncode=1)

        def side_effect(cmd, **kw):
            if "rev-parse" in cmd:
                return branch_result
            return tag_result

        with patch("subprocess.run", side_effect=side_effect):
            assert _detect_env() == "int"

    def test_main_branch_with_tag_returns_prod(self):
        branch_result = MagicMock(returncode=0, stdout="main\n")
        tag_result = MagicMock(returncode=0, stdout="v1.0.0\n")

        def side_effect(cmd, **kw):
            if "rev-parse" in cmd:
                return branch_result
            return tag_result

        with patch("subprocess.run", side_effect=side_effect):
            assert _detect_env() == "prod"

    def test_master_branch_with_tag_returns_prod(self):
        branch_result = MagicMock(returncode=0, stdout="master\n")
        tag_result = MagicMock(returncode=0, stdout="v1.0.0\n")

        def side_effect(cmd, **kw):
            if "rev-parse" in cmd:
                return branch_result
            return tag_result

        with patch("subprocess.run", side_effect=side_effect):
            assert _detect_env() == "prod"

    def test_git_not_installed_returns_prod(self):
        with patch("subprocess.run", side_effect=OSError("no git")):
            assert _detect_env() == "prod"

    def test_git_timeout_returns_prod(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 5)):
            assert _detect_env() == "prod"

    def test_unexpected_exception_returns_prod(self):
        with patch("subprocess.run", side_effect=RuntimeError("boom")):
            assert _detect_env() == "prod"

    def test_git_rev_parse_fails_returns_prod(self):
        result = MagicMock(returncode=128, stdout="")
        with patch("subprocess.run", return_value=result):
            assert _detect_env() == "prod"


# ---------------------------------------------------------------------------
# _resolve_env
# ---------------------------------------------------------------------------


class TestResolveEnv:
    """Tests for _resolve_env() — pick environment from args or detect."""

    def test_explicit_env_from_args(self, monkeypatch):
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        args = _ns(env="int")
        result = _resolve_env(args)
        assert result == "int"
        import os

        assert os.environ["ENVIRONMENT"] == "int"

    def test_falls_back_to_detect_when_no_arg(self):
        args = _ns(env=None)
        with patch("cli.revt._detect_env", return_value="dev"):
            result = _resolve_env(args)
        assert result == "dev"

    def test_no_env_attr_falls_back(self):
        args = _ns()  # no env attribute at all
        with patch("cli.revt._detect_env", return_value="prod"):
            result = _resolve_env(args)
        assert result == "prod"


# ---------------------------------------------------------------------------
# _env_badge
# ---------------------------------------------------------------------------


class TestEnvBadge:
    """Tests for _env_badge() — human-readable environment labels."""

    def test_dev(self):
        assert "mock API" in _env_badge("dev")

    def test_int(self):
        assert "real API" in _env_badge("int")
        assert "paper mode" in _env_badge("int")

    def test_prod(self):
        assert "prod" in _env_badge("prod")

    def test_unknown_returns_raw(self):
        assert _env_badge("staging") == "staging"


# ---------------------------------------------------------------------------
# _op_creds_item / _op_config_item
# ---------------------------------------------------------------------------


class TestOpItemNames:
    """Tests for 1Password item name formatters."""

    def test_creds_item_dev(self):
        assert _op_creds_item("dev") == "revolut-trader-credentials-dev"

    def test_creds_item_prod(self):
        assert _op_creds_item("prod") == "revolut-trader-credentials-prod"

    def test_config_item_int(self):
        assert _op_config_item("int") == "revolut-trader-config-int"

    def test_config_item_dev(self):
        assert _op_config_item("dev") == "revolut-trader-config-dev"


# ---------------------------------------------------------------------------
# _check_op
# ---------------------------------------------------------------------------


class TestCheckOp:
    """Tests for _check_op() — 1Password CLI availability check."""

    def test_success(self, capsys):
        result = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=result):
            assert _check_op() is True

    def test_failure_prints_message(self, capsys):
        # The global conftest patch already returns returncode=1 for op calls
        # but we override locally to be explicit.
        result = MagicMock(returncode=1)
        with patch("subprocess.run", return_value=result):
            assert _check_op() is False
        out = capsys.readouterr().out
        assert "1Password not authenticated" in out


# ---------------------------------------------------------------------------
# _op
# ---------------------------------------------------------------------------


class TestOp:
    """Tests for _op() — wrapper around the op CLI."""

    def test_runs_op_with_args(self):
        result = MagicMock(returncode=0, stdout="ok\n", stderr="")
        with patch("subprocess.run", return_value=result) as mock_run:
            r = _op("whoami")
            mock_run.assert_called_once_with(
                ["op", "whoami"], capture_output=True, text=True, timeout=15
            )
            assert r.returncode == 0


# ---------------------------------------------------------------------------
# _mask_secret
# ---------------------------------------------------------------------------


class TestMaskSecret:
    """Tests for _mask_secret() — display-safe masking of secret values."""

    def test_empty(self):
        assert _mask_secret("") == "(empty)"

    def test_short(self):
        assert _mask_secret("abc") == "abc..."

    def test_medium(self):
        assert _mask_secret("abcdefghij") == "abcdefgh..."

    def test_long(self):
        val = "x" * 150
        assert _mask_secret(val) == "<set, 150 chars>"

    def test_exactly_eight(self):
        # len == 8 → short branch (val[:4] + "...")
        assert _mask_secret("12345678") == "1234..."

    def test_exactly_nine(self):
        # len == 9 → medium branch (val[:8] + "...")
        assert _mask_secret("123456789") == "12345678..."


# ---------------------------------------------------------------------------
# _read_update_cache / _write_update_cache
# ---------------------------------------------------------------------------


class TestUpdateCache:
    """Tests for update cache read/write helpers."""

    def test_read_nonexistent_returns_none(self, tmp_path):
        assert _read_update_cache(tmp_path / "missing.json", 86400) is None

    def test_write_then_read_fresh_update(self, tmp_path):
        cache_file = tmp_path / "cache.json"
        _write_update_cache(cache_file, "1.0.0", "2.0.0", True)
        result = _read_update_cache(cache_file, 86400)
        assert result == ("1.0.0", "2.0.0")

    def test_write_then_read_no_update(self, tmp_path):
        cache_file = tmp_path / "cache.json"
        _write_update_cache(cache_file, "1.0.0", "1.0.0", False)
        result = _read_update_cache(cache_file, 86400)
        assert result is None

    def test_expired_cache_returns_none(self, tmp_path):
        cache_file = tmp_path / "cache.json"
        _write_update_cache(cache_file, "1.0.0", "2.0.0", True)
        result = _read_update_cache(cache_file, 0)  # TTL = 0 → always expired
        assert result is None

    def test_corrupt_cache_returns_none(self, tmp_path):
        cache_file = tmp_path / "cache.json"
        cache_file.write_text("not json{{{")
        assert _read_update_cache(cache_file, 86400) is None

    def test_write_creates_parent_dirs(self, tmp_path):
        cache_file = tmp_path / "a" / "b" / "cache.json"
        _write_update_cache(cache_file, "1.0.0", "2.0.0", True)
        assert cache_file.exists()

    def test_write_failure_does_not_raise(self, tmp_path):
        # Write to a path that can't be opened (directory)
        cache_file = tmp_path / "dir_as_file"
        cache_file.mkdir()
        # Should not raise
        _write_update_cache(cache_file, "1.0.0", "2.0.0", True)


# ---------------------------------------------------------------------------
# _get_current_version_from_pyproject
# ---------------------------------------------------------------------------


class TestGetCurrentVersionFromPyproject:
    """Tests for _get_current_version_from_pyproject()."""

    def test_reads_version_from_real_pyproject(self):
        # The real pyproject.toml exists in the repo
        version = _get_current_version_from_pyproject()
        assert version is not None
        assert "." in version  # looks like semver

    def test_missing_pyproject_returns_none(self):
        with patch("cli.revt._ROOT", Path("/nonexistent/path")):
            assert _get_current_version_from_pyproject() is None

    def test_malformed_pyproject_returns_none(self, tmp_path):
        bad_file = tmp_path / "pyproject.toml"
        bad_file.write_bytes(b"\x00\x01\x02")
        with patch("cli.revt._ROOT", tmp_path):
            result = _get_current_version_from_pyproject()
            assert result is None


# ---------------------------------------------------------------------------
# _get_latest_github_release
# ---------------------------------------------------------------------------


class TestGetLatestGithubRelease:
    """Tests for _get_latest_github_release()."""

    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"tag_name": "v1.2.3"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert _get_latest_github_release(timeout=1) == "1.2.3"

    def test_network_error_returns_none(self):
        with patch("urllib.request.urlopen", side_effect=Exception("network")):
            assert _get_latest_github_release(timeout=1) is None

    def test_no_tag_name_returns_empty(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert _get_latest_github_release(timeout=1) == ""


# ---------------------------------------------------------------------------
# _check_for_updates
# ---------------------------------------------------------------------------


class TestCheckForUpdates:
    """Tests for _check_for_updates() orchestration."""

    def test_skip_env_var(self, monkeypatch):
        monkeypatch.setenv("REVT_SKIP_UPDATE_CHECK", "1")
        assert _check_for_updates() is None

    def test_cached_result_returned(self, monkeypatch):
        monkeypatch.delenv("REVT_SKIP_UPDATE_CHECK", raising=False)
        with patch("cli.revt._read_update_cache", return_value=("1.0.0", "2.0.0")):
            assert _check_for_updates() == ("1.0.0", "2.0.0")

    def test_no_current_version_returns_none(self, monkeypatch):
        monkeypatch.delenv("REVT_SKIP_UPDATE_CHECK", raising=False)
        with (
            patch("cli.revt._read_update_cache", return_value=None),
            patch("cli.revt._get_current_version_from_pyproject", return_value=None),
        ):
            assert _check_for_updates() is None

    def test_no_latest_release_returns_none(self, monkeypatch):
        monkeypatch.delenv("REVT_SKIP_UPDATE_CHECK", raising=False)
        with (
            patch("cli.revt._read_update_cache", return_value=None),
            patch("cli.revt._get_current_version_from_pyproject", return_value="1.0.0"),
            patch("cli.revt._get_latest_github_release", return_value=None),
        ):
            assert _check_for_updates() is None

    def test_same_version_returns_none(self, monkeypatch):
        monkeypatch.delenv("REVT_SKIP_UPDATE_CHECK", raising=False)
        with (
            patch("cli.revt._read_update_cache", return_value=None),
            patch("cli.revt._get_current_version_from_pyproject", return_value="1.0.0"),
            patch("cli.revt._get_latest_github_release", return_value="1.0.0"),
            patch("cli.revt._write_update_cache"),
        ):
            assert _check_for_updates() is None

    def test_newer_version_returns_tuple(self, monkeypatch):
        monkeypatch.delenv("REVT_SKIP_UPDATE_CHECK", raising=False)
        with (
            patch("cli.revt._read_update_cache", return_value=None),
            patch("cli.revt._get_current_version_from_pyproject", return_value="1.0.0"),
            patch("cli.revt._get_latest_github_release", return_value="2.0.0"),
            patch("cli.revt._write_update_cache"),
        ):
            assert _check_for_updates() == ("1.0.0", "2.0.0")


# ---------------------------------------------------------------------------
# _show_update_notification
# ---------------------------------------------------------------------------


class TestShowUpdateNotification:
    """Tests for _show_update_notification()."""

    def test_prints_banner_when_update_available(self, capsys):
        with patch("cli.revt._check_for_updates", return_value=("1.0.0", "2.0.0")):
            _show_update_notification()
        out = capsys.readouterr().out
        assert "Update Available" in out
        assert "v1.0.0" in out
        assert "v2.0.0" in out

    def test_prints_nothing_when_up_to_date(self, capsys):
        with patch("cli.revt._check_for_updates", return_value=None):
            _show_update_notification()
        out = capsys.readouterr().out
        assert "Update" not in out


# ---------------------------------------------------------------------------
# _print_run_config
# ---------------------------------------------------------------------------


class TestPrintRunConfig:
    """Tests for _print_run_config() — banner display."""

    def test_with_all_args(self, capsys):
        args = _ns(strategy="momentum", risk="moderate")
        _print_run_config(args, "int", "live")
        out = capsys.readouterr().out
        assert "momentum" in out
        assert "moderate" in out
        assert "live" in out
        assert "override" in out

    def test_with_no_strategy_or_mode(self, capsys):
        args = _ns(strategy=None, risk=None)
        _print_run_config(args, "dev", None)
        out = capsys.readouterr().out
        assert "(from 1Password)" in out
        assert "defaults to paper" in out


# ---------------------------------------------------------------------------
# _handle_live_mode_confirmation
# ---------------------------------------------------------------------------


class TestHandleLiveModeConfirmation:
    """Tests for _handle_live_mode_confirmation()."""

    def test_no_warning_returns_immediately(self):
        from src.config import Settings

        with patch.object(Settings, "get_mode_warning", return_value=None):
            _handle_live_mode_confirmation(confirm_live=False)  # no exit

    def test_confirm_live_flag_skips_prompt(self, capsys):
        from src.config import Settings

        with patch.object(Settings, "get_mode_warning", return_value="DANGER"):
            _handle_live_mode_confirmation(confirm_live=True)
        out = capsys.readouterr().out
        assert "DANGER" in out

    def test_user_types_wrong_confirmation_exits(self):
        from src.config import Settings

        with (
            patch.object(Settings, "get_mode_warning", return_value="DANGER"),
            patch("builtins.input", return_value="nope"),
            pytest.raises(SystemExit) as exc_info,
        ):
            _handle_live_mode_confirmation(confirm_live=False)
        assert exc_info.value.code == 0

    def test_user_types_correct_confirmation(self, capsys):
        from src.config import Settings

        with (
            patch.object(Settings, "get_mode_warning", return_value="DANGER"),
            patch("builtins.input", return_value="I UNDERSTAND"),
        ):
            _handle_live_mode_confirmation(confirm_live=False)

    def test_keyboard_interrupt_exits(self):
        from src.config import Settings

        with (
            patch.object(Settings, "get_mode_warning", return_value="DANGER"),
            patch("builtins.input", side_effect=KeyboardInterrupt),
            pytest.raises(SystemExit) as exc_info,
        ):
            _handle_live_mode_confirmation(confirm_live=False)
        assert exc_info.value.code == 0

    def test_eof_error_exits(self):
        from src.config import Settings

        with (
            patch.object(Settings, "get_mode_warning", return_value="DANGER"),
            patch("builtins.input", side_effect=EOFError),
            pytest.raises(SystemExit) as exc_info,
        ):
            _handle_live_mode_confirmation(confirm_live=False)
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# _setup_logger
# ---------------------------------------------------------------------------


class TestSetupLogger:
    """Tests for _setup_logger()."""

    def test_default_level(self):
        # _setup_logger imports loguru.logger inside the function.
        # We verify it doesn't raise and configures the real logger.
        from loguru import logger

        _setup_logger(None)
        # After calling, the logger has at least one handler (the one just added)
        assert len(logger._core.handlers) >= 1

    def test_custom_level(self):
        from loguru import logger

        _setup_logger("DEBUG")
        assert len(logger._core.handlers) >= 1


# ---------------------------------------------------------------------------
# cmd_run
# ---------------------------------------------------------------------------


class TestCmdRun:
    """Tests for cmd_run() — the 'revt run' command."""

    def test_run_basic(self):
        args = _ns(
            env="dev",
            strategy=None,
            risk=None,
            pairs=None,
            interval=None,
            log_level=None,
            mode=None,
            confirm_live=False,
        )
        mock_run_bot = MagicMock()
        with (
            patch("cli.revt._show_update_notification"),
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("cli.revt._print_run_config"),
            patch("cli.revt._handle_live_mode_confirmation"),
            patch("cli.revt._setup_logger"),
            patch("cli.revt.TradingMode", create=True),
            patch("cli.revt.settings", create=True),
            patch.dict("sys.modules", {"cli.run": MagicMock(run_bot=mock_run_bot)}),
            patch("asyncio.run"),
        ):
            cmd_run(args)

    def test_run_invalid_pairs_exits(self, capsys):
        args = _ns(
            env="dev",
            strategy=None,
            risk=None,
            pairs="INVALID",
            interval=None,
            log_level=None,
            mode=None,
            confirm_live=False,
        )
        with (
            patch("cli.revt._show_update_notification"),
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("cli.validators.validate_trading_pairs", return_value=(False, "bad pairs")),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_run(args)
        assert exc_info.value.code == 1

    def test_run_with_mode_override(self):
        args = _ns(
            env="dev",
            strategy=None,
            risk=None,
            pairs=None,
            interval=None,
            log_level=None,
            mode="paper",
            confirm_live=False,
        )
        mock_settings = MagicMock()
        mock_run_bot = MagicMock()
        with (
            patch("cli.revt._show_update_notification"),
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("cli.revt._print_run_config"),
            patch("cli.revt._handle_live_mode_confirmation"),
            patch("cli.revt._setup_logger"),
            patch("src.config.settings", mock_settings),
            patch.dict("sys.modules", {"cli.run": MagicMock(run_bot=mock_run_bot)}),
            patch("asyncio.run"),
        ):
            cmd_run(args)
        mock_settings.override_trading_mode.assert_called_once()

    def test_run_keyboard_interrupt(self, capsys):
        args = _ns(
            env="dev",
            strategy=None,
            risk=None,
            pairs=None,
            interval=None,
            log_level=None,
            mode=None,
            confirm_live=False,
        )
        with (
            patch("cli.revt._show_update_notification"),
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("cli.revt._print_run_config"),
            patch("cli.revt._handle_live_mode_confirmation"),
            patch("cli.revt._setup_logger"),
            patch("cli.revt.TradingMode", create=True),
            patch("cli.revt.settings", create=True),
            patch.dict("sys.modules", {"cli.run": MagicMock(run_bot=MagicMock())}),
            patch("asyncio.run", side_effect=KeyboardInterrupt),
        ):
            cmd_run(args)
        out = capsys.readouterr().out
        assert "Shutdown" in out


# ---------------------------------------------------------------------------
# cmd_backtest
# ---------------------------------------------------------------------------


class TestCmdBacktest:
    """Tests for cmd_backtest() — the 'revt backtest' command."""

    def _base_args(self, **overrides):
        defaults = {
            "env": "dev",
            "strategy": None,
            "strategies": None,
            "risk": None,
            "pairs": None,
            "days": 30,
            "interval": 60,
            "capital": None,
            "log_level": None,
            "hf": False,
            "compare": False,
            "matrix": False,
        }
        defaults.update(overrides)
        return _ns(**defaults)

    def test_single_backtest(self):
        args = self._base_args()
        with (
            patch("cli.revt._show_update_notification"),
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("cli.revt._backtest_single") as mock_single,
            patch("loguru.logger"),
        ):
            cmd_backtest(args)
        mock_single.assert_called_once_with(args)

    def test_hf_backtest(self):
        args = self._base_args(hf=True)
        with (
            patch("cli.revt._show_update_notification"),
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("cli.revt._backtest_single") as mock_single,
            patch("loguru.logger"),
        ):
            cmd_backtest(args)
        mock_single.assert_called_once_with(args, interval_override=1)

    def test_compare_backtest(self):
        args = self._base_args(compare=True)
        with (
            patch("cli.revt._show_update_notification"),
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("cli.revt._run_compare_cli") as mock_compare,
            patch("loguru.logger"),
        ):
            cmd_backtest(args)
        mock_compare.assert_called_once()

    def test_matrix_backtest(self, capsys):
        args = self._base_args(matrix=True)
        with (
            patch("cli.revt._show_update_notification"),
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("cli.revt._run_compare_cli") as mock_compare,
            patch("loguru.logger"),
        ):
            cmd_backtest(args)
        mock_compare.assert_called_once()
        out = capsys.readouterr().out
        assert "MATRIX" in out

    def test_matrix_warns_about_strategy_flag(self, capsys):
        args = self._base_args(matrix=True, strategy="momentum")
        with (
            patch("cli.revt._show_update_notification"),
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("cli.revt._run_compare_cli"),
            patch("loguru.logger"),
        ):
            cmd_backtest(args)
        out = capsys.readouterr().out
        assert "ignored" in out

    def test_compare_warns_about_strategy_flag(self, capsys):
        args = self._base_args(compare=True, strategy="momentum")
        with (
            patch("cli.revt._show_update_notification"),
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("cli.revt._run_compare_cli"),
            patch("loguru.logger"),
        ):
            cmd_backtest(args)
        out = capsys.readouterr().out
        assert "ignored" in out


class TestBacktestSingle:
    """Tests for _backtest_single()."""

    def test_runs_backtest(self):
        args = _ns(
            strategy=None,
            risk=None,
            pairs=None,
            days=30,
            interval=60,
            capital=None,
            log_level=None,
        )
        mock_run_backtest = MagicMock()
        with (
            patch.dict("sys.modules", {"cli.backtest": MagicMock(run_backtest=mock_run_backtest)}),
            patch("asyncio.run"),
        ):
            from cli.revt import _backtest_single

            _backtest_single(args)

    def test_keyboard_interrupt(self, capsys):
        args = _ns(
            strategy=None,
            risk=None,
            pairs=None,
            days=30,
            interval=60,
            capital=None,
            log_level=None,
        )
        mock_run_backtest = MagicMock()
        with (
            patch.dict("sys.modules", {"cli.backtest": MagicMock(run_backtest=mock_run_backtest)}),
            patch("asyncio.run", side_effect=KeyboardInterrupt),
        ):
            from cli.revt import _backtest_single

            _backtest_single(args)
        out = capsys.readouterr().out
        assert "interrupted" in out


class TestRunCompareCli:
    """Tests for _run_compare_cli()."""

    def test_delegates_to_backtest_compare(self):
        mock_run = MagicMock()
        mock_module = MagicMock(run_compare_cli=mock_run)
        with patch.dict("sys.modules", {"cli.backtest_compare": mock_module}):
            _run_compare_cli(
                days=30,
                interval=60,
                pairs=None,
                capital=None,
                risk=None,
                risk_levels=None,
                strategies=None,
                log_level=None,
            )
        mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# cmd_ops
# ---------------------------------------------------------------------------


class TestCmdOps:
    """Tests for cmd_ops() — the 'revt ops' command."""

    def test_status(self):
        args = _ns(env="dev", status=True, show=False)
        with (
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("cli.revt._ops_status") as mock_status,
        ):
            cmd_ops(args)
        mock_status.assert_called_once_with("dev")

    def test_show(self):
        args = _ns(env="dev", status=False, show=True)
        with (
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("cli.revt._ops_show") as mock_show,
        ):
            cmd_ops(args)
        mock_show.assert_called_once_with("dev")

    def test_default_set_creds(self):
        args = _ns(env="int", status=False, show=False)
        with (
            patch("cli.revt._resolve_env", return_value="int"),
            patch("cli.revt._ops_set_creds") as mock_set,
        ):
            cmd_ops(args)
        mock_set.assert_called_once_with("int")


# ---------------------------------------------------------------------------
# _ops_status
# ---------------------------------------------------------------------------


class TestOpsStatus:
    """Tests for _ops_status()."""

    def test_cli_not_installed(self, capsys):
        with patch("cli.revt._op", return_value=MagicMock(returncode=1)):
            _ops_status("dev")
        out = capsys.readouterr().out
        assert "not installed" in out

    def test_not_authenticated(self, capsys):
        call_count = 0

        def mock_op(*args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(returncode=0, stdout="2.0.0\n")
            return MagicMock(returncode=1)

        with patch("cli.revt._op", side_effect=mock_op):
            _ops_status("dev")
        out = capsys.readouterr().out
        assert "Authenticated    no" in out

    def test_full_status(self, capsys):
        with patch("cli.revt._op", return_value=MagicMock(returncode=0, stdout="ok\n")):
            _ops_status("dev")
        out = capsys.readouterr().out
        assert "Authenticated    yes" in out


# ---------------------------------------------------------------------------
# _ops_show
# ---------------------------------------------------------------------------


class TestOpsShow:
    """Tests for _ops_show()."""

    def test_op_not_available_exits(self):
        with (
            patch("cli.revt._check_op", return_value=False),
            pytest.raises(SystemExit) as exc_info,
        ):
            _ops_show("dev")
        assert exc_info.value.code == 1

    def test_not_tty_exits(self, capsys):
        with (
            patch("cli.revt._check_op", return_value=True),
            patch("sys.stdout") as mock_stdout,
        ):
            mock_stdout.isatty.return_value = False
            with pytest.raises(SystemExit):
                _ops_show("dev")

    def test_dev_env_shows_mock_message(self, capsys):
        with (
            patch("cli.revt._check_op", return_value=True),
            patch("sys.stdout") as mock_stdout,
            patch("cli.revt._op", return_value=MagicMock(returncode=1, stdout="")),
            patch("builtins.print"),
        ):
            mock_stdout.isatty.return_value = True
            _ops_show("dev")


# ---------------------------------------------------------------------------
# _ops_set_creds
# ---------------------------------------------------------------------------


class TestOpsSetCreds:
    """Tests for _ops_set_creds()."""

    def test_op_not_available_exits(self):
        with (
            patch("cli.revt._check_op", return_value=False),
            pytest.raises(SystemExit),
        ):
            _ops_set_creds("int")

    def test_dev_env_no_creds_needed(self, capsys):
        with patch("cli.revt._check_op", return_value=True):
            _ops_set_creds("dev")
        out = capsys.readouterr().out
        assert "mock API" in out

    def test_keyboard_interrupt(self, capsys):
        with (
            patch("cli.revt._check_op", return_value=True),
            patch("getpass.getpass", side_effect=KeyboardInterrupt),
        ):
            _ops_set_creds("int")
        out = capsys.readouterr().out
        assert "Cancelled" in out

    def test_eof_error(self, capsys):
        with (
            patch("cli.revt._check_op", return_value=True),
            patch("getpass.getpass", side_effect=EOFError),
        ):
            _ops_set_creds("int")
        out = capsys.readouterr().out
        assert "Cancelled" in out

    def test_successful_set(self, capsys):
        with (
            patch("cli.revt._check_op", return_value=True),
            patch("getpass.getpass", return_value="my-api-key"),
            patch("cli.revt._op", return_value=MagicMock(returncode=0)),
        ):
            _ops_set_creds("int")
        out = capsys.readouterr().out
        assert "REVOLUT_API_KEY stored" in out

    def test_failed_set_exits(self):
        with (
            patch("cli.revt._check_op", return_value=True),
            patch("getpass.getpass", return_value="my-api-key"),
            patch("cli.revt._op", return_value=MagicMock(returncode=1, stderr="error")),
            pytest.raises(SystemExit),
        ):
            _ops_set_creds("int")

    def test_empty_api_key_still_prints_done(self, capsys):
        with (
            patch("cli.revt._check_op", return_value=True),
            patch("getpass.getpass", return_value=""),
        ):
            _ops_set_creds("int")
        out = capsys.readouterr().out
        assert "Done" in out


# ---------------------------------------------------------------------------
# cmd_config
# ---------------------------------------------------------------------------


class TestCmdConfig:
    """Tests for cmd_config() — the 'revt config' command."""

    def test_show(self):
        args = _ns(env="dev", config_cmd="show")
        with (
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("cli.revt._config_show") as mock_show,
        ):
            cmd_config(args)
        mock_show.assert_called_once_with("dev")

    def test_set(self):
        args = _ns(env="dev", config_cmd="set", key="RISK_LEVEL", value="aggressive")
        with (
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("cli.revt._config_set") as mock_set,
        ):
            cmd_config(args)
        mock_set.assert_called_once_with("dev", "RISK_LEVEL", "aggressive")

    def test_init(self):
        args = _ns(env="dev", config_cmd="init")
        with (
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("cli.revt._config_init") as mock_init,
        ):
            cmd_config(args)
        mock_init.assert_called_once_with("dev")

    def test_delete(self):
        args = _ns(env="dev", config_cmd="delete", key="MAX_CAPITAL")
        with (
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("cli.revt._config_delete") as mock_del,
        ):
            cmd_config(args)
        mock_del.assert_called_once_with("dev", "MAX_CAPITAL")

    def test_default_is_show(self):
        args = _ns(env="dev", config_cmd=None)
        with (
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("cli.revt._config_show") as mock_show,
        ):
            cmd_config(args)
        mock_show.assert_called_once()


# ---------------------------------------------------------------------------
# _config_show
# ---------------------------------------------------------------------------


class TestConfigShow:
    """Tests for _config_show()."""

    def test_op_not_available_exits(self):
        with (
            patch("cli.revt._check_op", return_value=False),
            pytest.raises(SystemExit),
        ):
            _config_show("dev")

    def test_prints_config(self, capsys):
        with (
            patch("cli.revt._check_op", return_value=True),
            patch("cli.revt._op", return_value=MagicMock(returncode=0, stdout="conservative\n")),
        ):
            _config_show("dev")
        out = capsys.readouterr().out
        assert "Configuration" in out


# ---------------------------------------------------------------------------
# _config_set
# ---------------------------------------------------------------------------


class TestConfigSet:
    """Tests for _config_set()."""

    def test_op_not_available_exits(self):
        with (
            patch("cli.revt._check_op", return_value=False),
            pytest.raises(SystemExit),
        ):
            _config_set("dev", "KEY", "VAL")

    def test_validation_failure_exits(self, capsys):
        with (
            patch("cli.revt._check_op", return_value=True),
            patch("cli.validators.validate_config_value", return_value=(False, "bad value")),
            pytest.raises(SystemExit),
        ):
            _config_set("dev", "KEY", "VAL")

    def test_successful_set(self, capsys):
        with (
            patch("cli.revt._check_op", return_value=True),
            patch("cli.validators.validate_config_value", return_value=(True, None)),
            patch("cli.revt._op", return_value=MagicMock(returncode=0)),
        ):
            _config_set("dev", "RISK_LEVEL", "aggressive")
        out = capsys.readouterr().out
        assert "RISK_LEVEL = aggressive" in out

    def test_op_edit_failure_exits(self):
        with (
            patch("cli.revt._check_op", return_value=True),
            patch("cli.validators.validate_config_value", return_value=(True, None)),
            patch("cli.revt._op", return_value=MagicMock(returncode=1, stderr="error")),
            pytest.raises(SystemExit),
        ):
            _config_set("dev", "RISK_LEVEL", "aggressive")


# ---------------------------------------------------------------------------
# _config_init
# ---------------------------------------------------------------------------


class TestConfigInit:
    """Tests for _config_init()."""

    def test_op_not_available_exits(self):
        with (
            patch("cli.revt._check_op", return_value=False),
            pytest.raises(SystemExit),
        ):
            _config_init("dev")

    def test_item_exists_user_cancels(self, capsys):
        with (
            patch("cli.revt._check_op", return_value=True),
            patch("cli.revt._op", return_value=MagicMock(returncode=0)),
            patch("builtins.input", return_value="n"),
        ):
            _config_init("dev")
        out = capsys.readouterr().out
        assert "Cancelled" in out

    def test_item_exists_user_confirms_reset(self, capsys):
        op_results = [
            MagicMock(returncode=0),  # item get (exists)
            MagicMock(returncode=0),  # item delete
        ]
        op_idx = 0

        def mock_op(*args):
            nonlocal op_idx
            r = op_results[min(op_idx, len(op_results) - 1)]
            op_idx += 1
            return r

        create_result = MagicMock(returncode=0)
        with (
            patch("cli.revt._check_op", return_value=True),
            patch("cli.revt._op", side_effect=mock_op),
            patch("builtins.input", return_value="y"),
            patch("subprocess.run", return_value=create_result),
        ):
            _config_init("dev")
        out = capsys.readouterr().out
        assert "Config item created" in out

    def test_item_exists_keyboard_interrupt(self, capsys):
        with (
            patch("cli.revt._check_op", return_value=True),
            patch("cli.revt._op", return_value=MagicMock(returncode=0)),
            patch("builtins.input", side_effect=KeyboardInterrupt),
        ):
            _config_init("dev")
        out = capsys.readouterr().out
        assert "Cancelled" in out

    def test_item_exists_eof_error(self, capsys):
        with (
            patch("cli.revt._check_op", return_value=True),
            patch("cli.revt._op", return_value=MagicMock(returncode=0)),
            patch("builtins.input", side_effect=EOFError),
        ):
            _config_init("dev")
        out = capsys.readouterr().out
        assert "Cancelled" in out

    def test_new_item_created_non_prod(self, capsys):
        create_result = MagicMock(returncode=0)
        with (
            patch("cli.revt._check_op", return_value=True),
            patch("cli.revt._op", return_value=MagicMock(returncode=1)),
            patch("subprocess.run", return_value=create_result),
        ):
            _config_init("dev")
        out = capsys.readouterr().out
        assert "Config item created" in out

    def test_new_item_created_prod_shows_tip(self, capsys):
        create_result = MagicMock(returncode=0)
        with (
            patch("cli.revt._check_op", return_value=True),
            patch("cli.revt._op", return_value=MagicMock(returncode=1)),
            patch("subprocess.run", return_value=create_result),
        ):
            _config_init("prod")
        out = capsys.readouterr().out
        assert "Tip" in out
        assert "MAX_CAPITAL" in out

    def test_create_failure_exits(self):
        with (
            patch("cli.revt._check_op", return_value=True),
            patch("cli.revt._op", return_value=MagicMock(returncode=1)),
            patch("subprocess.run", return_value=MagicMock(returncode=1, stderr="fail")),
            pytest.raises(SystemExit),
        ):
            _config_init("dev")


# ---------------------------------------------------------------------------
# _config_delete
# ---------------------------------------------------------------------------


class TestConfigDelete:
    """Tests for _config_delete()."""

    def test_op_not_available_exits(self):
        with (
            patch("cli.revt._check_op", return_value=False),
            pytest.raises(SystemExit),
        ):
            _config_delete("dev", "KEY")

    def test_successful_delete(self, capsys):
        with (
            patch("cli.revt._check_op", return_value=True),
            patch("cli.revt._op", return_value=MagicMock(returncode=0)),
        ):
            _config_delete("dev", "MAX_CAPITAL")
        out = capsys.readouterr().out
        assert "MAX_CAPITAL removed" in out

    def test_delete_failure_exits(self):
        with (
            patch("cli.revt._check_op", return_value=True),
            patch("cli.revt._op", return_value=MagicMock(returncode=1, stderr="error")),
            pytest.raises(SystemExit),
        ):
            _config_delete("dev", "MAX_CAPITAL")


# ---------------------------------------------------------------------------
# cmd_api
# ---------------------------------------------------------------------------


class TestCmdApi:
    """Tests for cmd_api() — the 'revt api' command."""

    def test_dev_env_blocked(self, capsys):
        args = _ns(env="dev", api_cmd="balance")
        with (
            patch("cli.revt._resolve_env", return_value="dev"),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_api(args)
        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert "mock" in out

    def test_test_command_delegates(self):
        args = _ns(env="int", api_cmd="test")
        mock_run = MagicMock()
        with (
            patch("cli.revt._resolve_env", return_value="int"),
            patch.dict("sys.modules", {"cli.api_test": MagicMock(run_api_command=mock_run)}),
        ):
            cmd_api(args)
        mock_run.assert_called_once_with("test")

    def test_ready_command_delegates(self):
        args = _ns(env="int", api_cmd="ready")
        mock_run = MagicMock()
        with (
            patch("cli.revt._resolve_env", return_value="int"),
            patch.dict("sys.modules", {"cli.api_test": MagicMock(run_api_command=mock_run)}),
        ):
            cmd_api(args)
        mock_run.assert_called_once_with("trade-ready")

    def test_balance_command_delegates_to_endpoint(self):
        args = _ns(
            env="int",
            api_cmd="balance",
            symbol=None,
            symbols=None,
            order_id=None,
            interval=60,
            limit=20,
            depth=20,
        )
        mock_endpoint = MagicMock()
        with (
            patch("cli.revt._resolve_env", return_value="int"),
            patch.dict("sys.modules", {"cli.api_test": MagicMock(run_api_endpoint=mock_endpoint)}),
        ):
            cmd_api(args)
        mock_endpoint.assert_called_once()

    def test_pairs_command_maps_name(self):
        args = _ns(
            env="int",
            api_cmd="pairs",
            symbol=None,
            symbols=None,
            order_id=None,
            interval=60,
            limit=20,
            depth=20,
        )
        mock_endpoint = MagicMock()
        with (
            patch("cli.revt._resolve_env", return_value="int"),
            patch.dict("sys.modules", {"cli.api_test": MagicMock(run_api_endpoint=mock_endpoint)}),
        ):
            cmd_api(args)
        mock_endpoint.assert_called_once()
        # Check that 'pairs' was mapped to 'currency-pairs'
        assert mock_endpoint.call_args.kwargs["command"] == "currency-pairs"


# ---------------------------------------------------------------------------
# cmd_telegram
# ---------------------------------------------------------------------------


class TestCmdTelegram:
    """Tests for cmd_telegram() — the 'revt telegram' command."""

    def test_start_subcommand(self):
        args = _ns(env="dev", telegram_cmd="start")
        mock_run_control_plane = MagicMock()
        with (
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("cli.revt._show_update_notification"),
            patch.dict(
                "sys.modules",
                {"cli.telegram_control": MagicMock(run_control_plane=mock_run_control_plane)},
            ),
        ):
            cmd_telegram(args)
        mock_run_control_plane.assert_called_once()

    def test_test_subcommand_missing_token(self, capsys):
        args = _ns(env="dev", telegram_cmd=None)
        mock_settings = MagicMock()
        mock_settings.telegram_bot_token = None
        mock_settings.telegram_chat_id = None
        with (
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("cli.revt.settings", mock_settings, create=True),
            patch("cli.revt.TelegramNotifier", create=True),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_telegram(args)
        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert "not configured" in out

    def test_test_subcommand_missing_chat_id_only(self, capsys):
        args = _ns(env="dev", telegram_cmd="test")
        mock_settings = MagicMock()
        mock_settings.telegram_bot_token = "token123"
        mock_settings.telegram_chat_id = None
        with (
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("cli.revt.settings", mock_settings, create=True),
            patch("cli.revt.TelegramNotifier", create=True),
            pytest.raises(SystemExit),
        ):
            cmd_telegram(args)
        out = capsys.readouterr().out
        assert "TELEGRAM_CHAT_ID" in out

    def test_test_subcommand_success(self, capsys):
        args = _ns(env="dev", telegram_cmd="test")
        mock_notifier = MagicMock()
        mock_notifier.send_test = MagicMock()
        # Patch settings attributes on the real singleton and TelegramNotifier at its source
        with (
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("src.config.settings.telegram_bot_token", new="token123"),
            patch("src.config.settings.telegram_chat_id", new="chat456"),
            patch("src.utils.telegram.TelegramNotifier", return_value=mock_notifier),
            patch("asyncio.run"),
        ):
            cmd_telegram(args)
        out = capsys.readouterr().out
        assert "test" in out.lower() or "Test" in out

    def test_test_subcommand_failure_exits(self, capsys):
        args = _ns(env="dev", telegram_cmd="test")
        mock_notifier = MagicMock()
        mock_notifier.send_test = MagicMock()
        with (
            patch("cli.revt._resolve_env", return_value="dev"),
            patch("src.config.settings.telegram_bot_token", new="token123"),
            patch("src.config.settings.telegram_chat_id", new="chat456"),
            patch("src.utils.telegram.TelegramNotifier", return_value=mock_notifier),
            patch("asyncio.run", side_effect=Exception("network error")),
            pytest.raises(SystemExit),
        ):
            cmd_telegram(args)


# ---------------------------------------------------------------------------
# cmd_db
# ---------------------------------------------------------------------------


class TestCmdDb:
    """Tests for cmd_db() — the 'revt db' command."""

    def test_stats(self):
        args = _ns(env="dev", db_cmd="stats")
        mock_show_stats = MagicMock()
        with (
            patch("cli.revt._resolve_env", return_value="dev"),
            patch.dict("sys.modules", {"cli.db_manage": MagicMock(show_stats=mock_show_stats)}),
        ):
            cmd_db(args)
        mock_show_stats.assert_called_once()

    def test_analytics(self):
        args = _ns(env="dev", db_cmd="analytics", days=60)
        mock_show_analytics = MagicMock()
        with (
            patch("cli.revt._resolve_env", return_value="dev"),
            patch.dict(
                "sys.modules", {"cli.db_manage": MagicMock(show_analytics=mock_show_analytics)}
            ),
        ):
            cmd_db(args)
        mock_show_analytics.assert_called_once_with(days=60)

    def test_backtests(self):
        args = _ns(env="dev", db_cmd="backtests", limit=5)
        mock_show = MagicMock()
        with (
            patch("cli.revt._resolve_env", return_value="dev"),
            patch.dict(
                "sys.modules", {"cli.db_manage": MagicMock(show_backtest_results=mock_show)}
            ),
        ):
            cmd_db(args)
        mock_show.assert_called_once_with(limit=5)

    def test_export(self):
        args = _ns(env="dev", db_cmd="export")
        mock_export = MagicMock()
        with (
            patch("cli.revt._resolve_env", return_value="dev"),
            patch.dict("sys.modules", {"cli.db_manage": MagicMock(export_csv=mock_export)}),
        ):
            cmd_db(args)
        mock_export.assert_called_once()

    def test_report(self):
        args = _ns(env="dev", db_cmd="report", days=30, output_dir="data/reports")
        mock_generate = MagicMock()
        with (
            patch("cli.revt._resolve_env", return_value="dev"),
            patch.dict(
                "sys.modules", {"cli.analytics_report": MagicMock(generate_report=mock_generate)}
            ),
        ):
            cmd_db(args)
        mock_generate.assert_called_once()

    def test_encrypt_setup(self):
        args = _ns(env="dev", db_cmd="encrypt-setup")
        mock_setup = MagicMock()
        with (
            patch("cli.revt._resolve_env", return_value="dev"),
            patch.dict(
                "sys.modules",
                {"src.utils.db_encryption": MagicMock(setup_database_encryption=mock_setup)},
            ),
        ):
            cmd_db(args)
        mock_setup.assert_called_once()

    def test_encrypt_status(self, capsys):
        args = _ns(env="dev", db_cmd="encrypt-status")
        mock_enc = MagicMock()
        mock_enc.is_enabled = True
        mock_enc_class = MagicMock(return_value=mock_enc)
        with (
            patch("cli.revt._resolve_env", return_value="dev"),
            patch.dict(
                "sys.modules",
                {"src.utils.db_encryption": MagicMock(DatabaseEncryption=mock_enc_class)},
            ),
        ):
            cmd_db(args)
        out = capsys.readouterr().out
        assert "enabled" in out

    def test_default_is_stats(self):
        args = _ns(env="dev", db_cmd=None)
        mock_show_stats = MagicMock()
        with (
            patch("cli.revt._resolve_env", return_value="dev"),
            patch.dict("sys.modules", {"cli.db_manage": MagicMock(show_stats=mock_show_stats)}),
        ):
            cmd_db(args)
        mock_show_stats.assert_called_once()


# ---------------------------------------------------------------------------
# _get_binary_name_for_platform
# ---------------------------------------------------------------------------


class TestGetBinaryNameForPlatform:
    """Tests for _get_binary_name_for_platform()."""

    def test_linux_arm64(self):
        with (
            patch("platform.system", return_value="Linux"),
            patch("platform.machine", return_value="aarch64"),
        ):
            assert _get_binary_name_for_platform() == "revt-linux-arm64"

    def test_linux_x86_64(self):
        with (
            patch("platform.system", return_value="Linux"),
            patch("platform.machine", return_value="x86_64"),
        ):
            assert _get_binary_name_for_platform() == "revt-linux-x86_64"

    def test_linux_amd64(self):
        with (
            patch("platform.system", return_value="Linux"),
            patch("platform.machine", return_value="amd64"),
        ):
            assert _get_binary_name_for_platform() == "revt-linux-x86_64"

    def test_linux_arm(self):
        with (
            patch("platform.system", return_value="Linux"),
            patch("platform.machine", return_value="armv7l"),
        ):
            assert _get_binary_name_for_platform() == "revt-linux-arm64"

    def test_unsupported_linux_arch_exits(self):
        with (
            patch("platform.system", return_value="Linux"),
            patch("platform.machine", return_value="ppc64le"),
            pytest.raises(SystemExit),
        ):
            _get_binary_name_for_platform()

    def test_unsupported_platform_exits(self):
        with (
            patch("platform.system", return_value="Darwin"),
            patch("platform.machine", return_value="arm64"),
            pytest.raises(SystemExit),
        ):
            _get_binary_name_for_platform()


# ---------------------------------------------------------------------------
# _check_binary_version
# ---------------------------------------------------------------------------


class TestCheckBinaryVersion:
    """Tests for _check_binary_version()."""

    def test_returns_versions(self):
        with (
            patch("cli.revt._get_current_version_from_pyproject", return_value="1.0.0"),
            patch("cli.revt._get_latest_github_release", return_value="v2.0.0"),
        ):
            current, latest = _check_binary_version()
        assert current == "1.0.0"
        assert latest == "2.0.0"

    def test_strips_v_prefix(self):
        with (
            patch("cli.revt._get_current_version_from_pyproject", return_value="1.0.0"),
            patch("cli.revt._get_latest_github_release", return_value="v1.2.3"),
        ):
            _, latest = _check_binary_version()
        assert latest == "1.2.3"

    def test_no_latest_returns_none(self):
        with (
            patch("cli.revt._get_current_version_from_pyproject", return_value="1.0.0"),
            patch("cli.revt._get_latest_github_release", return_value=None),
        ):
            current, latest = _check_binary_version()
        assert current == "1.0.0"
        assert latest is None


# ---------------------------------------------------------------------------
# _verify_git_repository
# ---------------------------------------------------------------------------


class TestVerifyGitRepository:
    """Tests for _verify_git_repository()."""

    def test_success(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            _verify_git_repository()  # should not raise

    def test_not_git_repo_exits(self):
        with (
            patch("subprocess.run", side_effect=subprocess.CalledProcessError(128, "git")),
            pytest.raises(SystemExit),
        ):
            _verify_git_repository()

    def test_git_not_found_exits(self):
        with (
            patch("subprocess.run", side_effect=FileNotFoundError),
            pytest.raises(SystemExit),
        ):
            _verify_git_repository()


# ---------------------------------------------------------------------------
# _get_git_commits
# ---------------------------------------------------------------------------


class TestGetGitCommits:
    """Tests for _get_git_commits()."""

    def test_returns_commit_shas(self):
        def side_effect(cmd, **kw):
            if "HEAD" in cmd:
                return MagicMock(stdout="abc123\n")
            return MagicMock(stdout="def456\n")

        with patch("subprocess.run", side_effect=side_effect):
            local, remote = _get_git_commits("HEAD", "origin/main")
        assert local == "abc123"
        assert remote == "def456"


# ---------------------------------------------------------------------------
# _stash_local_changes
# ---------------------------------------------------------------------------


class TestStashLocalChanges:
    """Tests for _stash_local_changes()."""

    def test_no_changes(self):
        with patch("subprocess.run", return_value=MagicMock(stdout="", returncode=0)):
            result = _stash_local_changes()
        assert result is False

    def test_has_changes_stash_succeeds(self, capsys):
        call_count = 0

        def side_effect(cmd, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # git status
                return MagicMock(stdout="M file.py\n", returncode=0)
            # git stash push
            return MagicMock(stdout="", returncode=0)

        with patch("subprocess.run", side_effect=side_effect):
            result = _stash_local_changes()
        assert result is True
        out = capsys.readouterr().out
        assert "stashed" in out.lower() or "Stash" in out or "Changes stashed" in out

    def test_stash_fails_exits(self):
        call_count = 0

        def side_effect(cmd, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(stdout="M file.py\n", returncode=0)
            return MagicMock(stdout="", stderr="conflict", returncode=1)

        with (
            patch("subprocess.run", side_effect=side_effect),
            pytest.raises(SystemExit),
        ):
            _stash_local_changes()


# ---------------------------------------------------------------------------
# _update_from_binary
# ---------------------------------------------------------------------------


class TestUpdateFromBinary:
    """Tests for _update_from_binary()."""

    def test_already_up_to_date(self, capsys):
        with (
            patch("cli.revt._check_binary_version", return_value=("1.0.0", "1.0.0")),
        ):
            _update_from_binary()
        out = capsys.readouterr().out
        assert "up to date" in out

    def test_new_version_available(self, capsys):
        with (
            patch("cli.revt._check_binary_version", return_value=("1.0.0", "2.0.0")),
            patch("cli.revt._get_binary_name_for_platform", return_value="revt-linux-x86_64"),
            patch("cli.revt._download_and_install_binary"),
        ):
            _update_from_binary()
        out = capsys.readouterr().out
        assert "New version" in out

    def test_no_version_info(self, capsys):
        with (
            patch("cli.revt._check_binary_version", return_value=(None, None)),
            patch("cli.revt._get_binary_name_for_platform", return_value="revt-linux-x86_64"),
            patch("cli.revt._download_and_install_binary"),
        ):
            _update_from_binary()
        out = capsys.readouterr().out
        assert "Downloading" in out


# ---------------------------------------------------------------------------
# _update_from_source
# ---------------------------------------------------------------------------


class TestUpdateFromSource:
    """Tests for _update_from_source()."""

    def test_already_up_to_date(self, capsys):
        with (
            patch("cli.revt._verify_git_repository"),
            patch("subprocess.run") as mock_run,
            patch("cli.revt._get_git_commits", return_value=("abc", "abc")),
        ):
            # git rev-parse --abbrev-ref HEAD
            mock_run.return_value = MagicMock(stdout="main\n", returncode=0)
            _update_from_source()
        out = capsys.readouterr().out
        assert "up to date" in out

    def test_updates_available_no_stash(self, capsys):
        with (
            patch("cli.revt._verify_git_repository"),
            patch("cli.revt._get_git_commits", return_value=("abc", "def")),
            patch("cli.revt._stash_local_changes", return_value=False),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(stdout="main\n", returncode=0)
            _update_from_source()
        out = capsys.readouterr().out
        assert "Update complete" in out


# ---------------------------------------------------------------------------
# cmd_update
# ---------------------------------------------------------------------------


class TestCmdUpdate:
    """Tests for cmd_update() — the 'revt update' command."""

    def test_frozen_delegates_to_binary(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        with patch("cli.revt._update_from_binary") as mock_bin:
            cmd_update(_ns())
        mock_bin.assert_called_once()

    def test_source_delegates_to_source(self):
        # sys.frozen is not set by default
        with patch("cli.revt._update_from_source") as mock_src:
            cmd_update(_ns())
        mock_src.assert_called_once()


# ---------------------------------------------------------------------------
# _build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    """Tests for _build_parser() — the argparse builder."""

    def test_returns_parser(self):
        parser = _build_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_run_subcommand(self):
        parser = _build_parser()
        args = parser.parse_args(["run", "--strategy", "momentum", "--risk", "moderate"])
        assert args.strategy == "momentum"
        assert args.risk == "moderate"
        assert args.func == cmd_run

    def test_backtest_subcommand(self):
        parser = _build_parser()
        args = parser.parse_args(["backtest", "--days", "60", "--hf"])
        assert args.days == 60
        assert args.hf is True
        assert args.func == cmd_backtest

    def test_ops_subcommand(self):
        parser = _build_parser()
        args = parser.parse_args(["ops", "--status"])
        assert args.status is True
        assert args.func == cmd_ops

    def test_config_subcommand(self):
        parser = _build_parser()
        args = parser.parse_args(["config", "set", "RISK_LEVEL", "aggressive"])
        assert args.config_cmd == "set"
        assert args.key == "RISK_LEVEL"
        assert args.value == "aggressive"
        assert args.func == cmd_config

    def test_api_subcommand(self):
        parser = _build_parser()
        args = parser.parse_args(["api", "balance", "--env", "int"])
        assert args.api_cmd == "balance"
        assert args.env == "int"
        assert args.func == cmd_api

    def test_db_subcommand(self):
        parser = _build_parser()
        args = parser.parse_args(["db", "stats"])
        assert args.db_cmd == "stats"
        assert args.func == cmd_db

    def test_telegram_subcommand(self):
        parser = _build_parser()
        args = parser.parse_args(["telegram", "test"])
        assert args.telegram_cmd == "test"
        assert args.func == cmd_telegram

    def test_update_subcommand(self):
        parser = _build_parser()
        args = parser.parse_args(["update"])
        assert args.func == cmd_update

    def test_no_command_has_no_func(self):
        parser = _build_parser()
        args = parser.parse_args([])
        assert not hasattr(args, "func")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for main() — the entry point."""

    def test_no_command_prints_help_and_exits(self, capsys):
        with (
            patch("sys.argv", ["revt"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 0

    def test_dispatches_to_func(self):
        mock_func = MagicMock()
        with (
            patch("cli.revt._build_parser") as mock_parser,
        ):
            mock_args = MagicMock()
            mock_args.func = mock_func
            mock_parser.return_value.parse_args.return_value = mock_args
            main()
        mock_func.assert_called_once_with(mock_args)

    def test_keyboard_interrupt(self):
        mock_func = MagicMock(side_effect=KeyboardInterrupt)
        with patch("cli.revt._build_parser") as mock_parser:
            mock_args = MagicMock()
            mock_args.func = mock_func
            mock_parser.return_value.parse_args.return_value = mock_args
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 0

    def test_system_exit_reraised(self):
        mock_func = MagicMock(side_effect=SystemExit(42))
        with patch("cli.revt._build_parser") as mock_parser:
            mock_args = MagicMock()
            mock_args.func = mock_func
            mock_parser.return_value.parse_args.return_value = mock_args
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 42

    def test_generic_exception_exits_with_1(self, capsys):
        mock_func = MagicMock(side_effect=RuntimeError("boom"))
        with patch("cli.revt._build_parser") as mock_parser:
            mock_args = MagicMock()
            mock_args.func = mock_func
            mock_parser.return_value.parse_args.return_value = mock_args
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Additional targeted tests for uncovered lines
# ---------------------------------------------------------------------------


class TestGetCurrentVersionFallbacks:
    """Cover the tomllib fallback branches (lines 180-184)."""

    def test_returns_none_when_tomllib_unavailable(self, monkeypatch):
        """When both tomllib and tomli are unavailable, returns None."""
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name in ("tomllib", "tomli"):
                raise ImportError(f"No module named '{name}'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = _get_current_version_from_pyproject()
        assert result is None


class TestOpsShowNonDev:
    """Cover _ops_show with non-dev env (lines 607-619, 631, 648)."""

    def test_shows_int_credentials(self, capsys):
        """When env=int, _ops_show queries Revolut API fields."""
        ok = subprocess.CompletedProcess([], 0, stdout="secret123\n", stderr="")

        with (
            patch("cli.revt._check_op", return_value=True),
            patch("cli.revt.sys") as mock_sys,
            patch("cli.revt._op", side_effect=lambda *a: ok),
        ):
            mock_sys.stdout.isatty.return_value = True
            _ops_show("int")

        out = capsys.readouterr().out
        assert "Credentials" in out


class TestDownloadAndInstallBinary:
    """Cover _download_and_install_binary (lines 1036-1101)."""

    def test_http_error_exits(self, tmp_path):
        import urllib.error

        from cli.revt import _download_and_install_binary

        with patch(
            "urllib.request.urlretrieve",
            side_effect=urllib.error.HTTPError(
                "url",
                404,
                "Not Found",
                {},
                None,  # type: ignore
            ),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _download_and_install_binary("https://example.com/revt", "v1.0.0")
        assert exc_info.value.code == 1

    def test_generic_exception_exits(self, tmp_path):
        from cli.revt import _download_and_install_binary

        with patch("urllib.request.urlretrieve", side_effect=RuntimeError("connection reset")):
            with pytest.raises(SystemExit) as exc_info:
                _download_and_install_binary("https://example.com/revt", "v1.0.0")
        assert exc_info.value.code == 1

    def test_successful_download_and_install(self, tmp_path):
        """Simulate a successful binary download and installation."""

        fake_binary = tmp_path / "revt"
        fake_binary.write_bytes(b"fake binary content")

        def fake_urlretrieve(url, dest):
            import shutil as sh

            sh.copy2(str(fake_binary), dest)

        fake_current = tmp_path / "revt_current"
        fake_current.write_bytes(b"old binary")

        with (
            patch("urllib.request.urlretrieve", side_effect=fake_urlretrieve),
            patch("sys.executable", str(fake_current)),
            patch("shutil.move"),
            patch("shutil.copy2"),
        ):
            from cli.revt import _download_and_install_binary

            _download_and_install_binary("https://example.com/revt", "v1.0.0")


class TestUpdateFromSourcePullFailed:
    """Cover _update_from_source pull-failed paths (lines 1281-1317)."""

    def _make_proc(self, returncode, stdout="", stderr=""):
        return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)

    def test_pull_failed_exits(self):
        """When git pull fails, sys.exit(1) is called."""
        from cli.revt import _update_from_source

        with (
            patch("cli.revt._verify_git_repository"),
            patch("cli.revt._stash_local_changes", return_value=False),
            patch("subprocess.run") as mock_sub,
        ):
            # git rev-parse --abbrev-ref HEAD → main
            # git fetch → ok
            # git rev-parse HEAD → sha1
            # git rev-parse origin/main → sha2 (different)
            # git rev-list --count → "3"
            # git pull → fail
            responses = [
                self._make_proc(0, "main\n"),  # branch
                self._make_proc(0),  # fetch
                self._make_proc(0, "abc123\n"),  # local commit
                self._make_proc(0, "def456\n"),  # remote commit
                self._make_proc(0, "3\n"),  # commits behind
                self._make_proc(1, stderr="conflict"),  # pull fails
            ]
            mock_sub.side_effect = responses
            with pytest.raises(SystemExit) as exc_info:
                _update_from_source()
        assert exc_info.value.code == 1

    def test_pull_failed_with_stashed_changes_restores(self, capsys):
        """When pull fails and had stashed changes, attempts to restore stash."""
        from cli.revt import _update_from_source

        with (
            patch("cli.revt._verify_git_repository"),
            patch("cli.revt._stash_local_changes", return_value=True),
            patch("subprocess.run") as mock_sub,
        ):
            responses = [
                self._make_proc(0, "main\n"),
                self._make_proc(0),
                self._make_proc(0, "abc\n"),
                self._make_proc(0, "def\n"),
                self._make_proc(0, "2\n"),
                self._make_proc(1, stderr="conflict"),  # pull fails
                self._make_proc(0),  # stash pop
            ]
            mock_sub.side_effect = responses
            with pytest.raises(SystemExit):
                _update_from_source()

    def test_stash_pop_conflict_warns(self, capsys):
        """When stash pop after successful pull has conflicts, prints warning."""
        with (
            patch("cli.revt._verify_git_repository"),
            patch("cli.revt._stash_local_changes", return_value=True),
            patch("subprocess.run") as mock_sub,
        ):
            responses = [
                self._make_proc(0, "main\n"),
                self._make_proc(0),
                self._make_proc(0, "abc\n"),
                self._make_proc(0, "def\n"),
                self._make_proc(0, "1\n"),
                self._make_proc(0, "Already up to date.\n"),  # pull ok
                self._make_proc(1, "CONFLICT"),  # stash pop → conflict
                self._make_proc(0),  # uv sync
            ]
            mock_sub.side_effect = responses
            from cli.revt import _update_from_source

            _update_from_source()
        out = capsys.readouterr().out
        assert "Conflict" in out or "conflict" in out.lower() or "Resolve" in out
