"""API readiness checks for Revolut Trader."""

import asyncio
import sys

from loguru import logger

from cli.utils.env_detect import set_env as _set_env

_set_env()

from src.api.client import RevolutAPIClient

_VIEW_ERROR_HINTS: dict[str, str] = {
    "deactivated": (
        "API key is invalid or deactivated.\n"
        "        → Re-activate the key in Revolut X, or run 'revt ops' to set a new one."
    ),
    "forbidden": (
        "API key lacks read permissions.\n"
        "        → Create a key with at least 'Read' scope in Revolut X."
    ),
    "unreachable": (
        "Cannot reach the Revolut X API.\n        → Check your internet connection and try again."
    ),
    "unknown": (
        "Unexpected error during authentication.\n        → Run 'revt api ready' for details."
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
            f"HTTP error: {view_error}.\n        → Run 'revt api ready' for details.",
        )
        print(f"STATUS: No market data access — {hint}")
        sys.exit(1)


async def check_connection(api_client: RevolutAPIClient) -> None:
    """Test API connection using a truly authenticated endpoint (/balances).

    The public order-book endpoint ignores auth headers and will succeed even
    with a deactivated key, so it cannot be used as a connection test.
    """
    print("\n🔑 Testing API Connection")
    print("=" * 50)

    try:
        balance_data = await api_client.get_balance()

        if balance_data:
            print("\n✅ Authentication successful")
            print("✅ API connection working")

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


async def _run_command(command: str) -> None:
    """Run the specified API readiness command."""
    api_client = RevolutAPIClient()
    await api_client.initialize()

    try:
        if command == "trade-ready":
            await check_trade_ready(api_client)
        else:
            await check_connection(api_client)
    finally:
        await api_client.close()


def run_api_command(command: str) -> None:
    """Run an API readiness command (test or trade-ready).

    Args:
        command: Either ``"test"`` (connection check) or ``"trade-ready"`` (permissions check).
    """
    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    try:
        asyncio.run(_run_command(command))
    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Command failed: {e!s}", exc_info=True)
        print(f"\n❌ Error: {e}")
        sys.exit(1)
