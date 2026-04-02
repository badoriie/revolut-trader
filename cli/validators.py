"""Input validation helpers for the revt CLI.

Provides validators for config values, trading pairs, and other user inputs.
"""

from __future__ import annotations

# Config fields that must be numeric
NUMERIC_FIELDS = {
    "INITIAL_CAPITAL",
    "MAX_CAPITAL",
    "SHUTDOWN_TRAILING_STOP_PCT",
    "SHUTDOWN_MAX_WAIT_SECONDS",
}


def validate_not_empty(value: str, field_name: str = "Value") -> tuple[bool, str | None]:
    """Validate that a value is not empty or whitespace-only.

    Args:
        value: The value to validate.
        field_name: Name of the field for error messages.

    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    if not value or not value.strip():
        return False, f"{field_name} cannot be empty"
    return True, None


def validate_numeric(value: str, field_name: str) -> tuple[bool, str | None]:
    """Validate that a value is numeric.

    Args:
        value: The value to validate.
        field_name: Name of the field for error messages.

    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    try:
        float(value)
        return True, None
    except ValueError:
        return False, f"{field_name} must be a number (got: {value!r})"


def validate_trading_pairs(pairs_str: str) -> tuple[bool, str | None]:
    """Validate trading pairs format (e.g., BTC-EUR,ETH-EUR).

    Args:
        pairs_str: Comma-separated trading pairs.

    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    if not pairs_str or not pairs_str.strip():
        return False, "Trading pairs cannot be empty"

    pairs = [p.strip() for p in pairs_str.split(",")]

    for pair in pairs:
        if not pair:
            return False, "Trading pairs cannot contain empty values"

        if "-" not in pair:
            return (
                False,
                f"Invalid pair format: {pair!r} (expected format: BTC-EUR,ETH-EUR)",
            )

        parts = pair.split("-")
        if len(parts) != 2:
            return (
                False,
                f"Invalid pair format: {pair!r} (must have exactly one dash)",
            )

        base, quote = parts
        if not base or not quote:
            return False, f"Invalid pair: {pair!r} (both sides must be non-empty)"

    return True, None


def validate_config_value(key: str, value: str) -> tuple[bool, str | None]:
    """Validate a config key-value pair.

    Args:
        key: The config key.
        value: The config value.

    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    # Check for empty values
    is_valid, error = validate_not_empty(value, key)
    if not is_valid:
        return is_valid, error

    # Check numeric fields
    if key in NUMERIC_FIELDS:
        is_valid, error = validate_numeric(value, key)
        if not is_valid:
            return is_valid, error

    # Check trading pairs format
    if key == "TRADING_PAIRS":
        is_valid, error = validate_trading_pairs(value)
        if not is_valid:
            return is_valid, error

    return True, None
