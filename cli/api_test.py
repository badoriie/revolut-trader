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
    print(f"\n📈 Recent Candles: {symbol} ({interval}min)")
    print("=" * 50)

    candles = await api_client.get_candles(symbol, interval, limit)

    if candles:
        print(f"\nShowing last {len(candles)} candles:\n")
        print(
            f"{'Timestamp':<20} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10} {'Volume':>12}"
        )
        print("-" * 80)

        for candle in reversed(candles[-10:]):  # Show most recent first
            timestamp = candle["timestamp"].strftime("%Y-%m-%d %H:%M")
            print(
                f"{timestamp:<20} "
                f"{candle['open']:>10.2f} "
                f"{candle['high']:>10.2f} "
                f"{candle['low']:>10.2f} "
                f"{candle['close']:>10.2f} "
                f"{candle['volume']:>12.4f}"
            )
    else:
        print(f"\n❌ Failed to fetch candles for {symbol}")


async def test_connection(api_client: RevolutAPIClient) -> None:
    """Test API connection."""
    print("\n🔌 Testing API Connection")
    print("=" * 50)

    # Try to fetch ticker as a connection test (known working endpoint)
    try:
        ticker = await api_client.get_ticker("BTC-EUR")

        if ticker:
            print("\n✅ API Connection Successful")
            print("✓ Authentication working")
            print("✓ API endpoints accessible")
            print(f"✓ BTC-EUR current price: €{ticker['last']:.2f}")
        else:
            print("\n❌ API Connection Failed")
            print("Check your credentials in 1Password")
            sys.exit(1)
    except Exception as e:
        print("\n❌ API Connection Failed")
        print(f"Error: {e}")
        print("Check your credentials in 1Password")
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


async def run_command(args) -> None:
    """Run the specified API command."""
    # Initialize API client
    api_client = RevolutAPIClient()
    await api_client.initialize()

    try:
        if args.command == "balance":
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

    finally:
        await api_client.close()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="API Testing CLI for Revolut Trader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test API connection
  python cli/api_test.py test

  # Get account balance
  python cli/api_test.py balance

  # Get ticker for BTC-EUR
  python cli/api_test.py ticker --symbol BTC-EUR

  # Get multiple tickers
  python cli/api_test.py tickers --symbols BTC-EUR,ETH-EUR,SOL-EUR

  # Get recent candles
  python cli/api_test.py candles --symbol BTC-EUR --interval 60 --limit 10
        """,
    )

    parser.add_argument(
        "command",
        choices=["test", "balance", "ticker", "tickers", "candles"],
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
        "--interval",
        "-i",
        type=int,
        default=60,
        choices=[5, 15, 30, 60, 240, 1440],
        help="Candle interval in minutes (default: 60)",
    )

    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=10,
        help="Number of candles to fetch (default: 10)",
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
