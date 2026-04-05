"""Tests for cli/validators.py module."""

from __future__ import annotations

import pytest

from cli.utils.validators import (
    NUMERIC_FIELDS,
    validate_config_value,
    validate_not_empty,
    validate_numeric,
    validate_trading_pairs,
)


class TestValidateNotEmpty:
    """Tests for validate_not_empty function."""

    def test_valid_value(self):
        """Test with valid non-empty value."""
        is_valid, error = validate_not_empty("test_value", "TestField")
        assert is_valid is True
        assert error is None

    def test_empty_string(self):
        """Test with empty string."""
        is_valid, error = validate_not_empty("", "TestField")
        assert is_valid is False
        assert error == "TestField cannot be empty"

    def test_whitespace_only(self):
        """Test with whitespace-only string."""
        is_valid, error = validate_not_empty("   ", "TestField")
        assert is_valid is False
        assert error == "TestField cannot be empty"

    def test_whitespace_with_content(self):
        """Test with whitespace plus content."""
        is_valid, error = validate_not_empty("  test  ", "TestField")
        assert is_valid is True
        assert error is None


class TestValidateNumeric:
    """Tests for validate_numeric function."""

    def test_valid_integer(self):
        """Test with valid integer string."""
        is_valid, error = validate_numeric("42", "TestNumber")
        assert is_valid is True
        assert error is None

    def test_valid_float(self):
        """Test with valid float string."""
        is_valid, error = validate_numeric("3.14", "TestNumber")
        assert is_valid is True
        assert error is None

    def test_negative_number(self):
        """Test with negative number."""
        is_valid, error = validate_numeric("-10.5", "TestNumber")
        assert is_valid is True
        assert error is None

    def test_zero(self):
        """Test with zero."""
        is_valid, error = validate_numeric("0", "TestNumber")
        assert is_valid is True
        assert error is None

    def test_invalid_text(self):
        """Test with non-numeric text."""
        is_valid, error = validate_numeric("not_a_number", "TestNumber")
        assert is_valid is False
        assert "must be a number" in error
        assert "not_a_number" in error

    def test_empty_string(self):
        """Test with empty string."""
        is_valid, error = validate_numeric("", "TestNumber")
        assert is_valid is False
        assert "must be a number" in error

    def test_scientific_notation(self):
        """Test with scientific notation."""
        is_valid, error = validate_numeric("1e5", "TestNumber")
        assert is_valid is True
        assert error is None


class TestValidateTradingPairs:
    """Tests for validate_trading_pairs function."""

    def test_valid_single_pair(self):
        """Test with valid single trading pair."""
        is_valid, error = validate_trading_pairs("BTC-EUR")
        assert is_valid is True
        assert error is None

    def test_valid_multiple_pairs(self):
        """Test with valid multiple trading pairs."""
        is_valid, error = validate_trading_pairs("BTC-EUR,ETH-EUR,SOL-EUR")
        assert is_valid is True
        assert error is None

    def test_valid_pairs_with_whitespace(self):
        """Test with valid pairs containing whitespace."""
        is_valid, error = validate_trading_pairs("BTC-EUR , ETH-EUR , SOL-EUR")
        assert is_valid is True
        assert error is None

    def test_empty_string(self):
        """Test with empty string."""
        is_valid, error = validate_trading_pairs("")
        assert is_valid is False
        assert "cannot be empty" in error

    def test_whitespace_only(self):
        """Test with whitespace-only string."""
        is_valid, error = validate_trading_pairs("   ")
        assert is_valid is False
        assert "cannot be empty" in error

    def test_missing_dash(self):
        """Test with pair missing dash separator."""
        is_valid, error = validate_trading_pairs("BTCEUR")
        assert is_valid is False
        assert "Invalid pair format" in error
        assert "BTCEUR" in error

    def test_multiple_dashes(self):
        """Test with pair having multiple dashes."""
        is_valid, error = validate_trading_pairs("BTC-EUR-USD")
        assert is_valid is False
        assert "exactly one dash" in error

    def test_empty_base_currency(self):
        """Test with empty base currency."""
        is_valid, error = validate_trading_pairs("-EUR")
        assert is_valid is False
        assert "both sides must be non-empty" in error

    def test_empty_quote_currency(self):
        """Test with empty quote currency."""
        is_valid, error = validate_trading_pairs("BTC-")
        assert is_valid is False
        assert "both sides must be non-empty" in error

    def test_empty_element_in_list(self):
        """Test with empty element in comma-separated list."""
        is_valid, error = validate_trading_pairs("BTC-EUR,,ETH-EUR")
        assert is_valid is False
        assert "cannot contain empty values" in error

    def test_trailing_comma(self):
        """Test with trailing comma."""
        is_valid, error = validate_trading_pairs("BTC-EUR,")
        assert is_valid is False
        assert "cannot contain empty values" in error


class TestValidateConfigValue:
    """Tests for validate_config_value function."""

    def test_valid_non_numeric_field(self):
        """Test with valid non-numeric config field."""
        is_valid, error = validate_config_value("STRATEGY", "momentum")
        assert is_valid is True
        assert error is None

    def test_valid_numeric_field(self):
        """Test with valid numeric config field."""
        is_valid, error = validate_config_value("INITIAL_CAPITAL", "1000")
        assert is_valid is True
        assert error is None

    def test_invalid_numeric_field(self):
        """Test with invalid numeric config field."""
        is_valid, error = validate_config_value("INITIAL_CAPITAL", "not_a_number")
        assert is_valid is False
        assert "must be a number" in error

    def test_empty_value(self):
        """Test with empty value."""
        is_valid, error = validate_config_value("STRATEGY", "")
        assert is_valid is False
        assert "cannot be empty" in error

    def test_valid_trading_pairs(self):
        """Test with valid trading pairs."""
        is_valid, error = validate_config_value("TRADING_PAIRS", "BTC-EUR,ETH-EUR")
        assert is_valid is True
        assert error is None

    def test_invalid_trading_pairs(self):
        """Test with invalid trading pairs."""
        is_valid, error = validate_config_value("TRADING_PAIRS", "BTCEUR")
        assert is_valid is False
        assert "Invalid pair format" in error

    @pytest.mark.parametrize(
        "field_name",
        [
            "INITIAL_CAPITAL",
            "MAX_CAPITAL",
            "SHUTDOWN_TRAILING_STOP_PCT",
            "SHUTDOWN_MAX_WAIT_SECONDS",
        ],
    )
    def test_all_numeric_fields_validated(self, field_name):
        """Test that all numeric fields are properly validated."""
        assert field_name in NUMERIC_FIELDS

        # Valid numeric value
        is_valid, error = validate_config_value(field_name, "100")
        assert is_valid is True
        assert error is None

        # Invalid numeric value
        is_valid, error = validate_config_value(field_name, "invalid")
        assert is_valid is False
        assert "must be a number" in error

    def test_risk_level_field(self):
        """Test with risk level field."""
        is_valid, error = validate_config_value("RISK_LEVEL", "moderate")
        assert is_valid is True
        assert error is None

    def test_arbitrary_string_field(self):
        """Test with arbitrary string field."""
        is_valid, error = validate_config_value("CUSTOM_FIELD", "custom_value")
        assert is_valid is True
        assert error is None


class TestNumericFieldsConstant:
    """Tests for NUMERIC_FIELDS constant."""

    def test_numeric_fields_set_contains_expected_fields(self):
        """Test that NUMERIC_FIELDS contains expected config keys."""
        expected_fields = {
            "INITIAL_CAPITAL",
            "MAX_CAPITAL",
            "SHUTDOWN_TRAILING_STOP_PCT",
            "SHUTDOWN_MAX_WAIT_SECONDS",
        }
        assert expected_fields == NUMERIC_FIELDS

    def test_numeric_fields_is_set(self):
        """Test that NUMERIC_FIELDS is a set."""
        assert isinstance(NUMERIC_FIELDS, set)
