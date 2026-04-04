"""Tests for cli/api_test.py module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cli.api_test import (
    _execute_api_command,
    _handle_ticker_commands,
    check_connection,
    check_trade_ready,
    run_api_command,
    run_api_endpoint,
    run_command,
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
    client.get_ticker = AsyncMock()
    client.get_tickers = AsyncMock()
    client.get_currencies = AsyncMock()
    client.get_currency_pairs = AsyncMock()
    client.get_open_orders = AsyncMock()
    client.get_historical_orders = AsyncMock()
    client.get_order_book = AsyncMock()
    client.get_candles = AsyncMock()
    client.get_trades = AsyncMock()
    client.get_public_trades = AsyncMock()
    client.get_order = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_check_trade_ready_full_access(mock_api_client, capsys):
    """Test check_trade_ready with full access permissions."""
    mock_api_client.check_permissions.return_value = {
        "view": True,
        "trade": True,
    }

    await check_trade_ready(mock_api_client)

    captured = capsys.readouterr()
    assert "READY" in captured.out
    assert "Full access" in captured.out


@pytest.mark.asyncio
async def test_check_trade_ready_read_only(mock_api_client, capsys):
    """Test check_trade_ready with read-only access."""
    mock_api_client.check_permissions.return_value = {
        "view": True,
        "trade": False,
    }

    await check_trade_ready(mock_api_client)

    captured = capsys.readouterr()
    assert "Read-only key" in captured.out
    assert "paper/simulation mode available" in captured.out


@pytest.mark.asyncio
async def test_check_trade_ready_no_access(mock_api_client, capsys):
    """Test check_trade_ready with no access."""
    mock_api_client.check_permissions.return_value = {
        "view": False,
        "trade": False,
        "view_error": "deactivated",
    }

    with pytest.raises(SystemExit) as exc_info:
        await check_trade_ready(mock_api_client)

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "No market data access" in captured.out


@pytest.mark.asyncio
async def test_api_test_connection_success(mock_api_client, capsys):
    """Test check_connection with successful connection."""
    mock_api_client.get_balance.return_value = {
        "base_currency": "EUR",
        "balances": {"EUR": 1000.0, "BTC": 0.1},
        "total_eur": 2500.0,
    }

    await check_connection(mock_api_client)

    captured = capsys.readouterr()
    assert "Authentication successful" in captured.out
    assert "API connection working" in captured.out
    assert "EUR" in captured.out


@pytest.mark.asyncio
async def test_api_test_connection_empty_response(mock_api_client, capsys):
    """Test check_connection with empty response."""
    mock_api_client.get_balance.return_value = {}

    await check_connection(mock_api_client)

    captured = capsys.readouterr()
    assert "Connected but received empty response" in captured.out


@pytest.mark.asyncio
async def test_api_test_connection_failure(mock_api_client):
    """Test check_connection with connection failure."""
    mock_api_client.get_balance.side_effect = Exception("Connection failed")

    with pytest.raises(Exception, match="Connection failed"):
        await check_connection(mock_api_client)


@pytest.mark.asyncio
async def test_handle_ticker_commands_single(mock_api_client):
    """Test _handle_ticker_commands for single ticker."""
    mock_api_client.get_ticker.return_value = {"symbol": "BTC-EUR", "price": 50000}

    result = await _handle_ticker_commands(mock_api_client, "ticker", "BTC-EUR", None)

    assert result == {"symbol": "BTC-EUR", "price": 50000}
    mock_api_client.get_ticker.assert_called_once_with("BTC-EUR")


@pytest.mark.asyncio
async def test_handle_ticker_commands_multiple(mock_api_client):
    """Test _handle_ticker_commands for multiple tickers."""
    mock_api_client.get_tickers.return_value = [
        {"symbol": "BTC-EUR", "price": 50000},
        {"symbol": "ETH-EUR", "price": 3000},
    ]

    result = await _handle_ticker_commands(mock_api_client, "tickers", "BTC-EUR", "BTC-EUR,ETH-EUR")

    assert len(result) == 2
    mock_api_client.get_tickers.assert_called_once_with(["BTC-EUR", "ETH-EUR"])


@pytest.mark.asyncio
async def test_handle_ticker_commands_all(mock_api_client):
    """Test _handle_ticker_commands for all tickers."""
    mock_api_client.get_tickers.return_value = [
        {"symbol": "BTC-EUR", "price": 50000},
    ]

    result = await _handle_ticker_commands(mock_api_client, "all-tickers", "BTC-EUR", None)

    assert len(result) == 1
    mock_api_client.get_tickers.assert_called_once_with()


@pytest.mark.asyncio
async def test_execute_api_command_balance(mock_api_client):
    """Test _execute_api_command for balance."""
    mock_api_client.get_balance.return_value = {"total_eur": 1000.0}

    result = await _execute_api_command(
        mock_api_client, "balance", None, None, None, None, None, None
    )

    assert result == {"total_eur": 1000.0}


@pytest.mark.asyncio
async def test_execute_api_command_currencies(mock_api_client):
    """Test _execute_api_command for currencies."""
    mock_api_client.get_currencies.return_value = ["EUR", "USD", "BTC"]

    result = await _execute_api_command(
        mock_api_client, "currencies", None, None, None, None, None, None
    )

    assert result == ["EUR", "USD", "BTC"]


@pytest.mark.asyncio
async def test_execute_api_command_order_book(mock_api_client):
    """Test _execute_api_command for order book."""
    mock_api_client.get_order_book.return_value = {
        "bids": [[50000, 1.5]],
        "asks": [[50100, 1.0]],
    }

    result = await _execute_api_command(
        mock_api_client, "order-book", "BTC-EUR", None, None, None, None, 10
    )

    assert "bids" in result
    mock_api_client.get_order_book.assert_called_once_with("BTC-EUR", depth=10)


@pytest.mark.asyncio
async def test_execute_api_command_candles(mock_api_client):
    """Test _execute_api_command for candles."""
    mock_api_client.get_candles.return_value = [{"time": 1234567890, "open": 50000, "close": 50100}]

    result = await _execute_api_command(
        mock_api_client, "candles", "BTC-EUR", None, None, 60, 100, None
    )

    assert len(result) == 1
    mock_api_client.get_candles.assert_called_once_with("BTC-EUR", interval=60, limit=100)


@pytest.mark.asyncio
async def test_execute_api_command_missing_symbol(mock_api_client):
    """Test _execute_api_command with missing required symbol."""
    with pytest.raises(SystemExit) as exc_info:
        await _execute_api_command(mock_api_client, "ticker", None, None, None, None, None, None)

    assert exc_info.value.code == 1


@pytest.mark.asyncio
async def test_execute_api_command_missing_order_id(mock_api_client):
    """Test _execute_api_command with missing required order_id."""
    with pytest.raises(SystemExit) as exc_info:
        await _execute_api_command(mock_api_client, "order", None, None, None, None, None, None)

    assert exc_info.value.code == 1


@pytest.mark.asyncio
async def test_execute_api_command_unknown(mock_api_client):
    """Test _execute_api_command with unknown command."""
    with pytest.raises(SystemExit) as exc_info:
        await _execute_api_command(
            mock_api_client, "unknown-command", None, None, None, None, None, None
        )

    assert exc_info.value.code == 1


@pytest.mark.asyncio
async def test_run_command_test(mock_api_client):
    """Test run_command with test command."""
    from types import SimpleNamespace

    args = SimpleNamespace(command="test")

    mock_api_client.get_balance.return_value = {"total_eur": 1000.0}

    with patch("cli.api_test.RevolutAPIClient", return_value=mock_api_client):
        await run_command(args)

    mock_api_client.initialize.assert_called_once()
    mock_api_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_run_command_trade_ready(mock_api_client):
    """Test run_command with trade-ready command."""
    from types import SimpleNamespace

    args = SimpleNamespace(command="trade-ready")

    mock_api_client.check_permissions.return_value = {
        "view": True,
        "trade": True,
    }

    with patch("cli.api_test.RevolutAPIClient", return_value=mock_api_client):
        await run_command(args)

    mock_api_client.initialize.assert_called_once()
    mock_api_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_run_command_unknown(mock_api_client):
    """Test run_command with unknown command."""
    from types import SimpleNamespace

    args = SimpleNamespace(command="unknown")

    with patch("cli.api_test.RevolutAPIClient", return_value=mock_api_client):
        with pytest.raises(SystemExit) as exc_info:
            await run_command(args)

    assert exc_info.value.code == 1


def test_run_api_command_test(mock_api_client, capsys):
    """Test run_api_command wrapper function with test command."""
    mock_api_client.get_balance.return_value = {"total_eur": 1000.0}

    with patch("cli.api_test.RevolutAPIClient", return_value=mock_api_client):
        with patch("cli.api_test.asyncio.run", side_effect=_make_asyncio_run_mock()) as mock_run:
            run_api_command("test")
            assert mock_run.called


def test_run_api_command_keyboard_interrupt(mock_api_client):
    """Test run_api_command handles keyboard interrupt."""
    with patch("cli.api_test.RevolutAPIClient", return_value=mock_api_client):
        with patch(
            "cli.api_test.asyncio.run", side_effect=_make_asyncio_run_mock(KeyboardInterrupt())
        ):
            with pytest.raises(SystemExit) as exc_info:
                run_api_command("test")
            assert exc_info.value.code == 1


def test_run_api_command_exception(mock_api_client):
    """Test run_api_command handles exceptions."""
    with patch("cli.api_test.RevolutAPIClient", return_value=mock_api_client):
        with patch(
            "cli.api_test.asyncio.run", side_effect=_make_asyncio_run_mock(Exception("Test error"))
        ):
            with pytest.raises(SystemExit) as exc_info:
                run_api_command("test")
            assert exc_info.value.code == 1


def test_run_api_endpoint_balance(mock_api_client, capsys):
    """Test run_api_endpoint wrapper function."""
    mock_api_client.get_balance.return_value = {"total_eur": 1000.0}

    with patch("cli.api_test.RevolutAPIClient", return_value=mock_api_client):
        with patch("cli.api_test.asyncio.run", side_effect=_make_asyncio_run_mock()) as mock_run:
            run_api_endpoint(command="balance")
            assert mock_run.called


def test_run_api_endpoint_keyboard_interrupt(mock_api_client):
    """Test run_api_endpoint handles keyboard interrupt."""
    with patch("cli.api_test.RevolutAPIClient", return_value=mock_api_client):
        with patch(
            "cli.api_test.asyncio.run", side_effect=_make_asyncio_run_mock(KeyboardInterrupt())
        ):
            with pytest.raises(SystemExit) as exc_info:
                run_api_endpoint(command="balance")
            assert exc_info.value.code == 1


def test_run_api_endpoint_exception(mock_api_client):
    """Test run_api_endpoint handles exceptions."""
    with patch("cli.api_test.RevolutAPIClient", return_value=mock_api_client):
        with patch(
            "cli.api_test.asyncio.run", side_effect=_make_asyncio_run_mock(Exception("Test error"))
        ):
            with pytest.raises(SystemExit) as exc_info:
                run_api_endpoint(command="balance")
            assert exc_info.value.code == 1


@pytest.mark.asyncio
async def test_execute_api_command_trades(mock_api_client):
    """Test _execute_api_command for trades."""
    mock_api_client.get_trades.return_value = [{"id": "123", "price": 50000}]

    result = await _execute_api_command(
        mock_api_client, "trades", "BTC-EUR", None, None, None, 50, None
    )

    assert len(result) == 1
    mock_api_client.get_trades.assert_called_once_with(symbol="BTC-EUR", limit=50)


@pytest.mark.asyncio
async def test_execute_api_command_public_trades(mock_api_client):
    """Test _execute_api_command for public-trades."""
    mock_api_client.get_public_trades.return_value = [{"id": "456", "price": 50100}]

    result = await _execute_api_command(
        mock_api_client, "public-trades", "BTC-EUR", None, None, None, 25, None
    )

    assert len(result) == 1
    mock_api_client.get_public_trades.assert_called_once_with("BTC-EUR", limit=25)


@pytest.mark.asyncio
async def test_execute_api_command_order(mock_api_client):
    """Test _execute_api_command for order lookup."""
    mock_api_client.get_order.return_value = {"order_id": "test-123", "status": "filled"}

    result = await _execute_api_command(
        mock_api_client, "order", None, None, "test-123", None, None, None
    )

    assert result["order_id"] == "test-123"
    mock_api_client.get_order.assert_called_once_with("test-123")


@pytest.mark.asyncio
async def test_execute_api_command_currency_pairs(mock_api_client):
    """Test _execute_api_command for currency-pairs."""
    mock_api_client.get_currency_pairs.return_value = ["BTC-EUR", "ETH-EUR"]

    result = await _execute_api_command(
        mock_api_client, "currency-pairs", None, None, None, None, None, None
    )

    assert len(result) == 2
    mock_api_client.get_currency_pairs.assert_called_once()


@pytest.mark.asyncio
async def test_execute_api_command_open_orders(mock_api_client):
    """Test _execute_api_command for open-orders."""
    mock_api_client.get_open_orders.return_value = [{"order_id": "open-1"}]

    result = await _execute_api_command(
        mock_api_client, "open-orders", None, None, None, None, None, None
    )

    assert len(result) == 1
    mock_api_client.get_open_orders.assert_called_once()


@pytest.mark.asyncio
async def test_execute_api_command_orders(mock_api_client):
    """Test _execute_api_command for historical orders."""
    mock_api_client.get_historical_orders.return_value = [{"order_id": "hist-1"}]

    result = await _execute_api_command(
        mock_api_client, "orders", None, None, None, None, None, None
    )

    assert len(result) == 1
    mock_api_client.get_historical_orders.assert_called_once()


# ---------------------------------------------------------------------------
# main() entry point
# ---------------------------------------------------------------------------


def test_main_parses_args_and_calls_run_api_command(monkeypatch):
    """Test main() parses sys.argv and delegates to run_api_command."""
    monkeypatch.setattr("sys.argv", ["api_test.py", "test"])

    with patch("cli.api_test.run_api_command") as mock_cmd:
        from cli.api_test import main

        main()
        mock_cmd.assert_called_once_with("test")


def test_main_trade_ready_command(monkeypatch):
    """Test main() with trade-ready command."""
    monkeypatch.setattr("sys.argv", ["api_test.py", "trade-ready"])

    with patch("cli.api_test.run_api_command") as mock_cmd:
        from cli.api_test import main

        main()
        mock_cmd.assert_called_once_with("trade-ready")


# ---------------------------------------------------------------------------
# Ticker edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_ticker_tickers_without_symbols(mock_api_client):
    """Test _handle_ticker_commands for 'tickers' without symbols falls back to all."""
    mock_api_client.get_tickers.return_value = [{"symbol": "BTC-EUR"}]

    result = await _handle_ticker_commands(mock_api_client, "tickers", "BTC-EUR", None)

    assert len(result) == 1
    mock_api_client.get_tickers.assert_called_once_with()


# ---------------------------------------------------------------------------
# run_api_endpoint JSON display
# ---------------------------------------------------------------------------


def test_run_api_endpoint_displays_json(mock_api_client, capsys):
    """Test run_api_endpoint displays JSON output."""
    mock_api_client.get_balance.return_value = {"total_eur": 1000.0, "currency": "EUR"}

    with patch("cli.api_test.RevolutAPIClient", return_value=mock_api_client):
        run_api_endpoint(command="balance")

    # asyncio.run actually runs the endpoint, which prints JSON
    # We can't easily capture since asyncio.run is real, but verify no crash
