"""Shared helpers for backtest CLI commands.

Both ``cli/commands/backtest.py`` and ``cli/commands/backtest_compare.py``
need to resolve effective backtest parameters from CLI args + 1Password
settings, and create the appropriate API client.  This module holds that
shared logic to avoid duplication.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.api import create_api_client
from src.api.client import RevolutAPIClient
from src.api.mock_client import MockRevolutAPIClient
from src.config import settings


def resolve_backtest_params(args: Any) -> dict[str, Any]:
    """Resolve effective backtest parameters from CLI args and 1Password settings.

    CLI flags take priority; missing values fall back to the 1Password-sourced
    ``settings`` object.

    Args:
        args: Parsed CLI arguments namespace (or any object with optional
            ``pairs``, ``capital``, ``days``, and ``interval`` attributes).

    Returns:
        A dict with the following keys:

        - ``symbols`` (list[str]): Trading pairs to backtest.
        - ``initial_capital`` (Decimal): Starting capital.
        - ``effective_days`` (int): Historical look-back window in days.
        - ``effective_interval`` (int): Candle width in minutes.
    """
    raw_pairs = args.pairs if args.pairs else ",".join(settings.trading_pairs)
    symbols: list[str] = raw_pairs.split(",")
    initial_capital = Decimal(
        str(args.capital if args.capital is not None else settings.paper_initial_capital)
    )
    effective_days: int = args.days if args.days is not None else settings.backtest_days
    effective_interval: int = (
        args.interval if args.interval is not None else settings.backtest_interval
    )
    return {
        "symbols": symbols,
        "initial_capital": initial_capital,
        "effective_days": effective_days,
        "effective_interval": effective_interval,
    }


def create_backtest_api_client(
    args: Any,
) -> RevolutAPIClient | MockRevolutAPIClient:
    """Create the API client appropriate for a backtest run.

    Reads ``real_data`` from *args* (defaults to ``False`` when absent) and
    forwards it as ``force_real`` to :func:`~src.api.create_api_client`.

    Args:
        args: Parsed CLI arguments namespace.  May optionally carry a
            ``real_data`` boolean attribute.

    Returns:
        A :class:`~src.api.mock_client.MockRevolutAPIClient` for dev
        environments (unless ``real_data`` is ``True``), or a
        :class:`~src.api.client.RevolutAPIClient` otherwise.
    """
    real_data: bool = getattr(args, "real_data", False)
    return create_api_client(settings.environment, force_real=real_data)
