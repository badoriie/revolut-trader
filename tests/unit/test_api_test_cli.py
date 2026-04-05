"""Tests for cli/commands/api.py — API readiness checks."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cli.commands.api import (
    check_connection,
    check_trade_ready,
    run_api_command,
)


def _make_asyncio_run_mock(exc=None):
    """Return a side_effect for asyncio.run that closes the coroutine before optionally raising."""

    def _handler(coro):
        if hasattr(coro, "close"):
            coro.close()
        if exc is not None:
            raise exc

    return _handler


@pytest.fixture
def mock_api_client():
    """Create a mock API client."""
    client = MagicMock()
    client.initialize = AsyncMock()
    client.close = AsyncMock()
    client.check_permissions = AsyncMock()
    client.get_balance = AsyncMock()
    return client


# ---------------------------------------------------------------------------
# check_trade_ready
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_trade_ready_full_access(mock_api_client, capsys):
    """Full access — both view and trade permissions granted."""
    mock_api_client.check_permissions.return_value = {"view": True, "trade": True}

    await check_trade_ready(mock_api_client)

    out = capsys.readouterr().out
    assert "READY" in out
    assert "Full access" in out


@pytest.mark.asyncio
async def test_check_trade_ready_read_only(mock_api_client, capsys):
    """Read-only key — view granted, trade denied."""
    mock_api_client.check_permissions.return_value = {"view": True, "trade": False}

    await check_trade_ready(mock_api_client)

    out = capsys.readouterr().out
    assert "Read-only key" in out
    assert "paper/simulation mode available" in out


@pytest.mark.asyncio
async def test_check_trade_ready_no_access(mock_api_client, capsys):
    """Deactivated key — both permissions denied, exits 1."""
    mock_api_client.check_permissions.return_value = {
        "view": False,
        "trade": False,
        "view_error": "deactivated",
    }

    with pytest.raises(SystemExit) as exc_info:
        await check_trade_ready(mock_api_client)

    assert exc_info.value.code == 1
    assert "No market data access" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# check_connection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_connection_success(mock_api_client, capsys):
    """Successful connection shows account summary."""
    mock_api_client.get_balance.return_value = {
        "base_currency": "EUR",
        "balances": {"EUR": 1000.0, "BTC": 0.1},
        "total_eur": 2500.0,
    }

    await check_connection(mock_api_client)

    out = capsys.readouterr().out
    assert "Authentication successful" in out
    assert "API connection working" in out
    assert "EUR" in out


@pytest.mark.asyncio
async def test_check_connection_empty_response(mock_api_client, capsys):
    """Empty balance response warns but does not exit."""
    mock_api_client.get_balance.return_value = {}

    await check_connection(mock_api_client)

    assert "Connected but received empty response" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_check_connection_failure(mock_api_client):
    """Connection error propagates as exception."""
    mock_api_client.get_balance.side_effect = Exception("Connection failed")

    with pytest.raises(Exception, match="Connection failed"):
        await check_connection(mock_api_client)


# ---------------------------------------------------------------------------
# run_api_command
# ---------------------------------------------------------------------------


def test_run_api_command_test(mock_api_client):
    """run_api_command('test') invokes asyncio.run."""
    with patch("cli.commands.api.RevolutAPIClient", return_value=mock_api_client):
        with patch(
            "cli.commands.api.asyncio.run", side_effect=_make_asyncio_run_mock()
        ) as mock_run:
            run_api_command("test")
            assert mock_run.called


def test_run_api_command_keyboard_interrupt(mock_api_client):
    """KeyboardInterrupt exits with code 1."""
    with patch("cli.commands.api.RevolutAPIClient", return_value=mock_api_client):
        with patch(
            "cli.commands.api.asyncio.run", side_effect=_make_asyncio_run_mock(KeyboardInterrupt())
        ):
            with pytest.raises(SystemExit) as exc_info:
                run_api_command("test")
            assert exc_info.value.code == 1


def test_run_api_command_exception(mock_api_client):
    """Unexpected exception exits with code 1."""
    with patch("cli.commands.api.RevolutAPIClient", return_value=mock_api_client):
        with patch(
            "cli.commands.api.asyncio.run",
            side_effect=_make_asyncio_run_mock(Exception("boom")),
        ):
            with pytest.raises(SystemExit) as exc_info:
                run_api_command("test")
            assert exc_info.value.code == 1
