#!/usr/bin/env python3
"""
API Testing CLI for Revolut Trader
Essential commands to test API connectivity and permissions
"""

import argparse
import asyncio
import sys
from typing import Any

from loguru import logger

from src.api.client import RevolutAPIClient

_VIEW_ERROR_HINTS: dict[str, str] = {
    "deactivated": (
        "API key is invalid or deactivated.\n"
        "        → Re-activate the key in Revolut X, or run 'make ops' to set a new one."
    ),
    "forbidden": (
        "API key lacks read permissions.\n"
        "        → Create a key with at least 'Read' scope in Revolut X."
    ),
    "unreachable": (
        "Cannot reach the Revolut X API.\n        → Check your internet connection and try again."
    ),
    "unknown": (
        "Unexpected error during authentication.\n        → Run 'make api-test' for details."
    ),
}


async def check_trade_ready(api_client: RevolutAPIClient) -> None:
    """Report API key permissions and which modes are available.

    Exits with code 1 only if VIEW fails (no market data = nothing works).
    A read-only key exits 0 — paper/simulation mode is fully supported.
    """
    print("\n=== API Status Check ===\n")

    print("Checking permissions...")
    perms = await api_client.check_permissions()
    view_ok = perms["view"]
    trade_ok = perms["trade"]
    view_error: str | None = perms.get("view_error")

    print()
    print(f"  View  (market data) : {'READY' if view_ok else 'FAIL'}")
    print(f"  Trade (place orders): {'READY' if trade_ok else 'READ-ONLY'}")
    print()
    print(f"  Paper / simulation  : {'AVAILABLE' if view_ok else 'NOT AVAILABLE'}")
    print(f"  Live trading        : {'AVAILABLE' if trade_ok else 'NOT AVAILABLE (read-only key)'}")
    print()

    if view_ok and trade_ok:
        print("STATUS: Full access — paper and live modes available.")
    elif view_ok:
        print("STATUS: Read-only key — paper/simulation mode available.")
        print("        Real market data will be used; orders are simulated locally.")
        print("        To enable live trading, create a key with trading permissions in Revolut X.")
    else:
        hint = _VIEW_ERROR_HINTS.get(
            view_error or "",
            f"HTTP error: {view_error}.\n        → Run 'make api-test' for details.",
        )
        print(f"STATUS: No market data access — {hint}")
        sys.exit(1)


async def test_connection(api_client: RevolutAPIClient) -> None:
    """Test API connection using a truly authenticated endpoint (/balances).

    The public order-book endpoint ignores auth headers and will succeed even
    with a deactivated key, so it cannot be used as a connection test.
    """
    print("\n🔑 Testing API Connection")
    print("=" * 50)

    try:
        # Test balance endpoint as a simple connectivity check
        balance_data = await api_client.get_balance()

        if balance_data:
            print("\n✅ Authentication successful")
            print("✅ API connection working")

            # Show basic account info
            if balance_data.get("balances"):
                base_currency = balance_data.get("base_currency", "EUR")
                balances = balance_data["balances"]
                total_key = f"total_{base_currency.lower()}"
                total_base = balance_data.get(total_key, 0.0)

                currency_symbols = {"EUR": "€", "USD": "$", "GBP": "£"}
                symbol = currency_symbols.get(base_currency, base_currency)

                print("\n📊 Account Summary:")
                print(f"   Base Currency: {base_currency}")
                print(f"   Currencies: {', '.join(balances.keys())}")
                if total_base > 0:
                    print(f"   Total Value: {symbol}{total_base:,.2f}")
        else:
            print("⚠️  Connected but received empty response")

    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        raise


async def run_command(args) -> None:
    """Run the specified API command."""
    api_client = RevolutAPIClient()
    await api_client.initialize()

    try:
        if args.command == "trade-ready":
            await check_trade_ready(api_client)
        elif args.command == "test":
            await test_connection(api_client)
        else:
            print(f"Unknown command: {args.command}")
            sys.exit(1)
    finally:
        await api_client.close()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="API Testing CLI for Revolut Trader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli/api_test.py test          # Test authenticated connection
  python cli/api_test.py trade-ready   # Check API permissions (view + trade)
        """,
    )

    parser.add_argument(
        "command",
        choices=["trade-ready", "test"],
        help="Command to execute",
    )

    args = parser.parse_args()

    # Call the new function
    run_api_command(args.command)


def run_api_command(command: str) -> None:
    """Run an API test command.

    This function can be called directly from other modules without
    needing to patch sys.argv.

    Args:
        command: The API command to run (test, trade-ready, etc.)
    """
    from types import SimpleNamespace

    # Reduce logging noise
    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    # Create a namespace object with the command
    args = SimpleNamespace(command=command)

    # Run command
    try:
        asyncio.run(run_command(args))
    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Command failed: {e!s}", exc_info=True)
        print(f"\n❌ Error: {e}")
        sys.exit(1)


async def _execute_api_command(
    api_client: RevolutAPIClient,
    command: str,
    symbol: str | None,
    symbols: str | None,
    order_id: str | None,
    interval: int | None,
    limit: int | None,
    depth: int | None,
) -> dict[str, Any] | list[dict[str, Any]] | None:
    """Execute the API command and return the result.

    Extracted to reduce cognitive complexity of run_api_endpoint.
    """
    # Commands requiring symbol
    if command in ("ticker", "order-book", "candles", "trades", "public-trades") and not symbol:
        print(f"❌ Error: {command} command requires --symbol")
        sys.exit(1)

    # Command requiring order_id
    if command == "order" and not order_id:
        print("❌ Error: order command requires --order-id")
        sys.exit(1)

    # Simple commands (no parameters)
    if command == "balance":
        return await api_client.get_balance()
    if command == "currencies":
        return await api_client.get_currencies()
    if command == "currency-pairs":
        return await api_client.get_currency_pairs()
    if command == "open-orders":
        return await api_client.get_open_orders()
    if command == "orders":
        return await api_client.get_historical_orders()

    # Ticker commands
    if command == "ticker":
        assert symbol is not None  # Validated above
        return await api_client.get_ticker(symbol)
    if command in ("tickers", "all-tickers"):
        if symbols:
            symbol_list = [s.strip() for s in symbols.split(",")]
            return await api_client.get_tickers(symbol_list)
        return await api_client.get_tickers()

    # Symbol-based data commands
    if command == "order-book":
        assert symbol is not None  # Validated above
        return await api_client.get_order_book(symbol, depth=depth or 10)
    if command == "candles":
        assert symbol is not None  # Validated above
        return await api_client.get_candles(symbol, interval=interval or 60, limit=limit or 100)
    if command == "trades":
        assert symbol is not None  # Validated above
        return await api_client.get_trades(symbol=symbol, limit=limit or 100)
    if command == "public-trades":
        assert symbol is not None  # Validated above
        return await api_client.get_public_trades(symbol, limit=limit or 100)

    # Order lookup
    if command == "order":
        assert order_id is not None  # Validated above
        return await api_client.get_order(order_id)

    print(f"❌ Unknown command: {command}")
    sys.exit(1)

    return None


def run_api_endpoint(
    *,
    command: str,
    symbol: str | None = None,
    symbols: str | None = None,
    order_id: str | None = None,
    interval: int | None = None,
    limit: int | None = None,
    depth: int | None = None,
) -> None:
    """Run an API endpoint command with the given parameters.

    This function provides a direct interface to API endpoints without
    needing to patch sys.argv. It's a simple proxy to the API client.

    Args:
        command: The API command to run (balance, ticker, tickers, etc.)
        symbol: Symbol for single-symbol commands
        symbols: Comma-separated symbols for multi-symbol commands
        order_id: Order ID for order-specific commands
        interval: Candle interval in minutes
        limit: Result limit
        depth: Order book depth
    """
    import json

    # Reduce logging noise
    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    async def _run_endpoint():
        """Run the API endpoint and display results."""
        api_client = RevolutAPIClient()
        await api_client.initialize()

        try:
            result = await _execute_api_command(
                api_client, command, symbol, symbols, order_id, interval, limit, depth
            )

            # Display results as formatted JSON
            if result:
                print(json.dumps(result, indent=2, default=str))

        finally:
            await api_client.close()

    try:
        asyncio.run(_run_endpoint())
    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Command failed: {e!s}", exc_info=True)
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
