#!/usr/bin/env python3
"""
API Testing CLI for Revolut Trader
Quick commands to test API connectivity and fetch common data
"""

import argparse
import asyncio
import sys

from loguru import logger

from src.api.client import RevolutAPIClient


async def get_balance(api_client: RevolutAPIClient) -> None:
    """Get and display account balance."""
    print("\n💰 Account Balances")
    print("=" * 50)

    try:
        balance_data = await api_client.get_balance()

        if balance_data and balance_data.get("balances"):
            balances = balance_data["balances"]
            base_currency = balance_data.get("base_currency", "EUR")
            total_key = f"total_{base_currency.lower()}"
            total_base = balance_data.get(total_key, 0.0)

            # Currency symbol mapping
            currency_symbols = {"EUR": "€", "USD": "$", "GBP": "£"}
            symbol = currency_symbols.get(base_currency, base_currency)

            print(f"\n{'Currency':<10} {'Available':>15} {'Reserved':>15} {'Total':>15}")
            print("-" * 60)

            for currency, balance in balances.items():
                print(
                    f"{currency:<10} "
                    f"{balance['available']:>15.8f} "
                    f"{balance['reserved']:>15.8f} "
                    f"{balance['total']:>15.8f}"
                )

            if total_base > 0:
                print("-" * 60)
                print(f"\nTotal {base_currency} Value: {symbol}{total_base:,.2f}")

            print(f"\nCurrencies: {', '.join(balance_data['currencies'])}")
        else:
            print("\n❌ No balances found")
    except Exception as e:
        print("\n❌ Failed to fetch balances")
        print(f"Error: {e}")
        print("\nTip: Make sure your API key has the required permissions.")


async def get_ticker(api_client: RevolutAPIClient, symbol: str) -> None:
    """Get and display ticker/price for a symbol."""
    print(f"\n📊 Ticker: {symbol}")
    print("=" * 50)

    ticker = await api_client.get_ticker(symbol)

    if ticker:
        # Determine currency symbol from trading pair (e.g., BTC-EUR -> €)
        currency_symbols = {"EUR": "€", "USD": "$", "GBP": "£"}
        quote_currency = symbol.split("-")[-1] if "-" in symbol else "EUR"
        symbol_char = currency_symbols.get(quote_currency, quote_currency)

        print(f"\nBid:   {symbol_char}{ticker['bid']:.2f}")
        print(f"Ask:   {symbol_char}{ticker['ask']:.2f}")
        print(f"Last:  {symbol_char}{ticker['last']:.2f}")
        spread = ticker["ask"] - ticker["bid"]
        spread_pct = (spread / ticker["last"]) * 100 if ticker["last"] > 0 else 0
        print(f"Spread: {symbol_char}{spread:.2f} ({spread_pct:.3f}%)")
    else:
        print(f"\n❌ Failed to fetch ticker for {symbol}")


async def get_candles(
    api_client: RevolutAPIClient, symbol: str, interval: int = 60, limit: int = 10
) -> None:
    """Get and display recent candles."""
    from datetime import datetime

    print(f"\n📈 Recent Candles: {symbol} ({interval}min)")
    print("=" * 50)

    candles = await api_client.get_candles(symbol, interval, limit=limit)

    if candles:
        print(f"\nShowing last {len(candles)} candles:\n")
        print(
            f"{'Timestamp':<20} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10} {'Volume':>12}"
        )
        print("-" * 80)

        # Show most recent candles first (limit to requested amount)
        display_candles = candles[-limit:] if len(candles) > limit else candles
        for candle in reversed(display_candles):
            # Convert Unix timestamp (milliseconds) to datetime
            timestamp = datetime.fromtimestamp(int(candle["start"]) / 1000).strftime(
                "%Y-%m-%d %H:%M"
            )
            # Convert string values to float
            open_price = float(candle["open"])
            high_price = float(candle["high"])
            low_price = float(candle["low"])
            close_price = float(candle["close"])
            volume = float(candle["volume"])

            print(
                f"{timestamp:<20} "
                f"{open_price:>10.2f} "
                f"{high_price:>10.2f} "
                f"{low_price:>10.2f} "
                f"{close_price:>10.2f} "
                f"{volume:>12.4f}"
            )
    else:
        print(f"\n❌ Failed to fetch candles for {symbol}")


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
        "Cannot reach the Revolut X API.\n"
        "        → Check your internet connection and try again."
    ),
    "unknown": (
        "Unexpected error during authentication.\n"
        "        → Run 'make api-test' for details."
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
    view_ok   = perms["view"]
    trade_ok  = perms["trade"]
    view_error: str | None = perms.get("view_error")

    print()
    print(f"  View  (market data) : {'READY'     if view_ok  else 'FAIL'}")
    print(f"  Trade (place orders): {'READY'     if trade_ok else 'READ-ONLY'}")
    print()
    print(f"  Paper / simulation  : {'AVAILABLE' if view_ok  else 'NOT AVAILABLE'}")
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
        ) if view_error else "Unknown error.\n        → Run 'make api-test' for details."
        print(f"STATUS: No market data access — {hint}")
        sys.exit(1)


async def test_connection(api_client: RevolutAPIClient) -> None:
    """Test API connection using a truly authenticated endpoint (/balances).

    The public order-book endpoint ignores auth headers and will succeed even
    with a deactivated key, so it cannot be used as a connection test.
    """
    print("\nTesting API Connection")
    print("=" * 50)

    try:
        balance = await api_client.get_balance()
        if "currencies" in balance:
            print("\nPASS — Authentication successful")
            print(f"     — Account has {len(balance['currencies'])} currencies")
        else:
            print("\nFAIL — Unexpected balance response")
            sys.exit(1)
    except Exception as e:
        print("\nFAIL — Authentication failed")
        print(f"       {e}")
        print("\nRun 'make ops' to update credentials.")
        sys.exit(1)


async def get_multiple_tickers(api_client: RevolutAPIClient, symbols: list[str]) -> None:
    """Get tickers for multiple symbols."""
    print("\n📊 Multiple Tickers")
    print("=" * 50)

    currency_symbols = {"EUR": "€", "USD": "$", "GBP": "£"}

    print(f"\n{'Symbol':<12} {'Bid':>10} {'Ask':>10} {'Last':>10} {'Spread %':>10}")
    print("-" * 60)

    for symbol in symbols:
        ticker = await api_client.get_ticker(symbol)
        if ticker:
            # Get currency symbol from pair
            quote_currency = symbol.split("-")[-1] if "-" in symbol else "EUR"
            curr_symbol = currency_symbols.get(quote_currency, quote_currency + " ")

            spread = ticker["ask"] - ticker["bid"]
            spread_pct = (spread / ticker["last"]) * 100 if ticker["last"] > 0 else 0
            print(
                f"{symbol:<12} "
                f"{curr_symbol}{ticker['bid']:>8.2f} "
                f"{curr_symbol}{ticker['ask']:>8.2f} "
                f"{curr_symbol}{ticker['last']:>8.2f} "
                f"{spread_pct:>9.3f}%"
            )
        else:
            print(f"{symbol:<12} {'ERROR':>10}")


async def get_order_book(api_client: RevolutAPIClient, symbol: str, depth: int = 20) -> None:
    """Display raw order book snapshot (bids and asks)."""
    from datetime import datetime

    print(f"\n📖 Order Book: {symbol}  (depth={depth})")
    print("=" * 60)

    try:
        book = await api_client.get_order_book(symbol, limit=depth)
        asks = book.get("data", {}).get("asks", [])
        bids = book.get("data", {}).get("bids", [])
        ts = book.get("metadata", {}).get("timestamp")
        if ts:
            print(f"Snapshot: {datetime.fromtimestamp(int(ts) / 1000).strftime('%Y-%m-%d %H:%M:%S')}\n")

        col = f"{'Price':>14}  {'Qty':>14}"
        print(f"  {'ASKS':^31}")
        print(f"  {col}")
        print("  " + "-" * 31)
        for a in asks[:depth]:
            print(f"  {float(a['p']):>14.4f}  {float(a['q']):>14.8f}")

        print(f"\n  {'BIDS':^31}")
        print(f"  {col}")
        print("  " + "-" * 31)
        for b in bids[:depth]:
            print(f"  {float(b['p']):>14.4f}  {float(b['q']):>14.8f}")

        if asks and bids:
            spread = float(asks[0]["p"]) - float(bids[0]["p"])
            mid = (float(asks[0]["p"]) + float(bids[0]["p"])) / 2
            print(f"\n  Best ask: {float(asks[0]['p']):,.4f}  Best bid: {float(bids[0]['p']):,.4f}")
            print(f"  Spread:   {spread:.4f}  ({spread / mid * 100:.3f}%)")
    except Exception as e:
        print(f"\n❌ Failed: {e}")


async def get_all_tickers(api_client: RevolutAPIClient) -> None:
    """Display all tickers from the /tickers endpoint in a single call."""
    print("\n📊 All Tickers  (GET /tickers)")
    print("=" * 60)

    try:
        tickers = await api_client.get_tickers()
        if not tickers:
            print("No tickers returned.")
            return

        currency_symbols = {"EUR": "€", "USD": "$", "GBP": "£"}
        print(f"\n{'Symbol':<14} {'Bid':>12} {'Ask':>12} {'Last':>12} {'Spread %':>10}")
        print("-" * 65)
        for t in sorted(tickers, key=lambda x: x.get("symbol", "")):
            sym = t.get("symbol", "?")
            quote = sym.split("-")[-1] if "-" in sym else ""
            c = currency_symbols.get(quote, "")
            bid = t.get("bid") or t.get("bestBid") or "0"
            ask = t.get("ask") or t.get("bestAsk") or "0"
            last = t.get("last") or t.get("lastPrice") or "0"
            bid_f, ask_f, last_f = float(bid), float(ask), float(last)
            spread_pct = (ask_f - bid_f) / last_f * 100 if last_f else 0
            print(
                f"{sym:<14} {c}{bid_f:>11.2f} {c}{ask_f:>11.2f} "
                f"{c}{last_f:>11.2f} {spread_pct:>9.3f}%"
            )
        print(f"\nTotal pairs: {len(tickers)}")
    except Exception as e:
        print(f"\n❌ Failed: {e}")


async def get_open_orders(
    api_client: RevolutAPIClient, symbol: str | None = None
) -> None:
    """Display active (open) orders."""
    from datetime import datetime

    label = f"  [{symbol}]" if symbol else ""
    print(f"\n📋 Open Orders{label}")
    print("=" * 60)

    try:
        symbols = [symbol] if symbol else None
        result = await api_client.get_open_orders(symbols=symbols)
        orders = result.get("data", [])

        if not orders:
            print("No open orders.")
            return

        print(f"\n{'ID':<38} {'Symbol':<10} {'Side':<6} {'Type':<8} {'Qty':>10} {'Price':>12} {'Status'}")
        print("-" * 100)
        for o in orders:
            ts = o.get("created_date") or o.get("created_at", "")
            ts_str = datetime.fromtimestamp(int(ts) / 1000).strftime("%H:%M:%S") if ts else ""
            print(
                f"{o.get('id', '?'):<38} "
                f"{o.get('symbol', '?'):<10} "
                f"{o.get('side', '?'):<6} "
                f"{o.get('type', '?'):<8} "
                f"{float(o.get('quantity', 0)):>10.8f} "
                f"{float(o.get('price') or 0):>12.2f} "
                f"{o.get('status', '?')}  {ts_str}"
            )

        next_cursor = result.get("metadata", {}).get("next_cursor")
        if next_cursor:
            print(f"\n(more results — next_cursor: {next_cursor})")
    except Exception as e:
        print(f"\n❌ Failed: {e}")


async def get_historical_orders(
    api_client: RevolutAPIClient, symbol: str | None = None, limit: int = 20
) -> None:
    """Display completed/cancelled orders."""
    from datetime import datetime

    label = f"  [{symbol}]" if symbol else ""
    print(f"\n📜 Historical Orders{label}  (limit={limit})")
    print("=" * 60)

    try:
        symbols = [symbol] if symbol else None
        result = await api_client.get_historical_orders(symbols=symbols, limit=limit)
        orders = result.get("data", [])

        if not orders:
            print("No historical orders found.")
            return

        print(f"\n{'ID':<38} {'Symbol':<10} {'Side':<6} {'Type':<8} {'Qty':>10} {'Price':>12} {'Status'}")
        print("-" * 100)
        for o in orders:
            print(
                f"{o.get('id', '?'):<38} "
                f"{o.get('symbol', '?'):<10} "
                f"{o.get('side', '?'):<6} "
                f"{o.get('type', '?'):<8} "
                f"{float(o.get('quantity', 0)):>10.8f} "
                f"{float(o.get('price') or 0):>12.2f} "
                f"{o.get('status', '?')}"
            )
    except Exception as e:
        print(f"\n❌ Failed: {e}")


async def get_trades(
    api_client: RevolutAPIClient, symbol: str, limit: int = 20
) -> None:
    """Display private trade history for a symbol."""
    from datetime import datetime

    print(f"\n💱 Trade History: {symbol}  (limit={limit})")
    print("=" * 60)

    try:
        result = await api_client.get_trades(symbol, limit=limit)
        trades = result.get("data", [])

        if not trades:
            print("No trades found.")
            return

        print(f"\n{'Time':<20} {'Side':<6} {'Price':>12} {'Qty':>14} {'Trade ID'}")
        print("-" * 80)
        for t in trades:
            ts = t.get("tdt", "")
            ts_str = datetime.fromtimestamp(int(ts) / 1000).strftime("%Y-%m-%d %H:%M:%S") if ts else ""
            print(
                f"{ts_str:<20} "
                f"{t.get('s', '?'):<6} "
                f"{float(t.get('p', 0)):>12.4f} "
                f"{float(t.get('q', 0)):>14.8f} "
                f"{t.get('tid', '?')}"
            )

        next_cursor = result.get("metadata", {}).get("next_cursor")
        if next_cursor:
            print(f"\n(more results — next_cursor: {next_cursor})")
    except Exception as e:
        print(f"\n❌ Failed: {e}")


async def get_order(api_client: RevolutAPIClient, order_id: str) -> None:
    """Display details for a specific order."""
    from datetime import datetime

    print(f"\n🔍 Order: {order_id}")
    print("=" * 60)

    try:
        o = await api_client.get_order(order_id)
        created = o.get("created_date") or o.get("created_at", "")
        updated = o.get("updated_date") or o.get("updated_at", "")
        fmt = lambda ts: datetime.fromtimestamp(int(ts) / 1000).strftime("%Y-%m-%d %H:%M:%S") if ts else "?"  # noqa: E731

        print(f"\n  Venue ID:       {o.get('id', '?')}")
        print(f"  Client ID:      {o.get('client_order_id', '?')}")
        print(f"  Symbol:         {o.get('symbol', '?')}")
        print(f"  Side:           {o.get('side', '?')}")
        print(f"  Type:           {o.get('type', '?')}")
        print(f"  Status:         {o.get('status', '?')}")
        print(f"  Quantity:       {o.get('quantity', '?')}")
        print(f"  Filled qty:     {o.get('filled_quantity', '?')}")
        print(f"  Price:          {o.get('price', '?')}")
        print(f"  Avg fill price: {o.get('average_fill_price', '?')}")
        print(f"  Created:        {fmt(created)}")
        print(f"  Updated:        {fmt(updated)}")
    except Exception as e:
        print(f"\n❌ Failed: {e}")


async def run_command(args) -> None:
    """Run the specified API command."""
    # Initialize API client
    api_client = RevolutAPIClient()
    await api_client.initialize()

    try:
        if args.command == "trade-ready":
            await check_trade_ready(api_client)

        elif args.command == "balance":
            await get_balance(api_client)

        elif args.command == "ticker":
            if not args.symbol:
                print("❌ Error: --symbol required for ticker command")
                sys.exit(1)
            await get_ticker(api_client, args.symbol)

        elif args.command == "candles":
            if not args.symbol:
                print("❌ Error: --symbol required for candles command")
                sys.exit(1)
            await get_candles(api_client, args.symbol, args.interval, args.limit)

        elif args.command == "test":
            await test_connection(api_client)

        elif args.command == "tickers":

            symbols = args.symbols.split(",") if args.symbols else ["BTC-EUR", "ETH-EUR", "SOL-EUR"]
            await get_multiple_tickers(api_client, symbols)

        elif args.command == "order-book":
            if not args.symbol:
                print("❌ Error: --symbol required for order-book command")
                sys.exit(1)
            await get_order_book(api_client, args.symbol, depth=args.depth)

        elif args.command == "all-tickers":
            await get_all_tickers(api_client)

        elif args.command == "open-orders":
            await get_open_orders(api_client, symbol=args.symbol)

        elif args.command == "historical-orders":
            await get_historical_orders(api_client, symbol=args.symbol, limit=args.limit)

        elif args.command == "trades":
            if not args.symbol:
                print("❌ Error: --symbol required for trades command")
                sys.exit(1)
            await get_trades(api_client, args.symbol, limit=args.limit)

        elif args.command == "order":
            if not args.order_id:
                print("❌ Error: --order-id required for order command")
                sys.exit(1)
            await get_order(api_client, args.order_id)

    finally:
        await api_client.close()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="API Testing CLI for Revolut Trader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli/api_test.py trade-ready                          # check permissions
  python cli/api_test.py test                                 # auth check
  python cli/api_test.py balance                              # account balances
  python cli/api_test.py ticker --symbol BTC-EUR              # single ticker
  python cli/api_test.py tickers --symbols BTC-EUR,ETH-EUR    # multiple tickers (order-book)
  python cli/api_test.py all-tickers                          # all pairs (GET /tickers)
  python cli/api_test.py order-book --symbol BTC-EUR          # raw order book
  python cli/api_test.py order-book --symbol BTC-EUR --depth 5
  python cli/api_test.py candles --symbol BTC-EUR --interval 60 --limit 10
  python cli/api_test.py open-orders                          # all active orders
  python cli/api_test.py open-orders --symbol BTC-EUR         # filtered by pair
  python cli/api_test.py historical-orders --limit 20         # completed orders
  python cli/api_test.py trades --symbol BTC-EUR              # trade history
  python cli/api_test.py order --order-id <uuid>              # single order details
        """,
    )

    parser.add_argument(
        "command",
        choices=[
            "trade-ready", "test", "balance",
            "ticker", "tickers", "all-tickers",
            "order-book",
            "candles",
            "open-orders", "historical-orders",
            "trades",
            "order",
        ],
        help="Command to execute",
    )

    parser.add_argument(
        "--symbol",
        "-s",
        type=str,
        help="Trading symbol (e.g., BTC-EUR, ETH-EUR)",
    )

    parser.add_argument(
        "--symbols",
        type=str,
        help="Comma-separated trading symbols (e.g., BTC-EUR,ETH-EUR,SOL-EUR)",
    )

    parser.add_argument(
        "--order-id",
        type=str,
        help="Venue order ID (UUID) for order/order-fills commands",
    )

    parser.add_argument(
        "--depth",
        type=int,
        default=20,
        help="Order book depth (1-20, default: 20)",
    )

    parser.add_argument(
        "--interval",
        "-i",
        type=int,
        default=60,
        choices=[1, 5, 15, 30, 60, 240, 1440],
        help="Candle interval in minutes (default: 60)",
    )

    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=20,
        help="Number of results to fetch (default: 20)",
    )

    args = parser.parse_args()

    # Reduce logging noise
    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    # Run command
    try:
        asyncio.run(run_command(args))
    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Command failed: {str(e)}", exc_info=True)
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
