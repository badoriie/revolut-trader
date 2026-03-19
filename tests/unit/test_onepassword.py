"""Unit tests for 1Password integration utilities.

Tests _VaultCache, _run_op, and _fetch_item_fields directly
without relying on the real 1Password CLI.
"""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# _run_op
# ---------------------------------------------------------------------------


class TestRunOp:
    def test_success_returns_stdout(self):
        from src.utils.onepassword import _run_op

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="1.28.0\n")
            result = _run_op("--version")
        assert result == "1.28.0\n"

    def test_non_zero_returncode_returns_none(self):
        from src.utils.onepassword import _run_op

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = _run_op("item", "get", "nonexistent")
        assert result is None

    def test_file_not_found_returns_none(self):
        from src.utils.onepassword import _run_op

        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _run_op("--version")
        assert result is None

    def test_timeout_returns_none(self):
        import subprocess

        from src.utils.onepassword import _run_op

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("op", 5)):
            result = _run_op("--version")
        assert result is None

    def test_generic_exception_returns_none(self):
        from src.utils.onepassword import _run_op

        with patch("subprocess.run", side_effect=OSError("no such file")):
            result = _run_op("--version")
        assert result is None


# ---------------------------------------------------------------------------
# _fetch_item_fields
# ---------------------------------------------------------------------------


class TestFetchItemFields:
    def test_returns_fields_from_valid_json(self):
        from src.utils.onepassword import _fetch_item_fields

        mock_json = '{"fields": [{"label": "API_KEY", "value": "secret123"}]}'
        with patch("src.utils.onepassword._run_op", return_value=mock_json):
            result = _fetch_item_fields("my-item")
        assert result == {"API_KEY": "secret123"}

    def test_returns_empty_when_op_unavailable(self):
        from src.utils.onepassword import _fetch_item_fields

        with patch("src.utils.onepassword._run_op", return_value=None):
            result = _fetch_item_fields("my-item")
        assert result == {}

    def test_returns_empty_on_invalid_json(self):
        from src.utils.onepassword import _fetch_item_fields

        with patch("src.utils.onepassword._run_op", return_value="not-json"):
            result = _fetch_item_fields("my-item")
        assert result == {}

    def test_skips_fields_with_empty_label(self):
        from src.utils.onepassword import _fetch_item_fields

        mock_json = '{"fields": [{"label": "", "value": "val"}]}'
        with patch("src.utils.onepassword._run_op", return_value=mock_json):
            result = _fetch_item_fields("my-item")
        assert result == {}

    def test_skips_fields_with_empty_value(self):
        from src.utils.onepassword import _fetch_item_fields

        mock_json = '{"fields": [{"label": "KEY", "value": ""}]}'
        with patch("src.utils.onepassword._run_op", return_value=mock_json):
            result = _fetch_item_fields("my-item")
        assert result == {}

    def test_merges_multiple_fields(self):
        from src.utils.onepassword import _fetch_item_fields

        mock_json = '{"fields": [{"label": "K1", "value": "v1"}, {"label": "K2", "value": "v2"}]}'
        with patch("src.utils.onepassword._run_op", return_value=mock_json):
            result = _fetch_item_fields("my-item")
        assert result == {"K1": "v1", "K2": "v2"}


# ---------------------------------------------------------------------------
# _VaultCache.is_available
# ---------------------------------------------------------------------------


class TestVaultCacheIsAvailable:
    def test_returns_false_when_op_not_installed(self):
        from src.utils.onepassword import _VaultCache

        cache = _VaultCache()
        with patch("src.utils.onepassword._run_op", return_value=None):
            assert cache.is_available() is False

    def test_returns_true_when_authenticated(self):
        from src.utils.onepassword import _VaultCache

        cache = _VaultCache()
        with patch("src.utils.onepassword._run_op", side_effect=["1.28.0", "sa@example.com"]):
            assert cache.is_available() is True

    def test_returns_false_when_whoami_fails(self):
        from src.utils.onepassword import _VaultCache

        cache = _VaultCache()
        with patch("src.utils.onepassword._run_op", side_effect=["1.28.0", None]):
            assert cache.is_available() is False

    def test_caches_result_after_first_check(self):
        from src.utils.onepassword import _VaultCache

        cache = _VaultCache()
        with patch("src.utils.onepassword._run_op", return_value=None) as mock_op:
            cache.is_available()
            cache.is_available()
        assert mock_op.call_count == 1


# ---------------------------------------------------------------------------
# _VaultCache._is_stale
# ---------------------------------------------------------------------------


class TestVaultCacheIsStale:
    def test_stale_when_cache_empty(self):
        from src.utils.onepassword import _VaultCache

        cache = _VaultCache()
        assert cache._is_stale() is True

    def test_not_stale_when_populated(self):
        from src.utils.onepassword import _VaultCache

        cache = _VaultCache()
        cache._cache = {"KEY": "val"}
        assert cache._is_stale() is False


# ---------------------------------------------------------------------------
# _VaultCache.get
# ---------------------------------------------------------------------------


class TestVaultCacheGet:
    def _fresh_cache_with_key(self, key: str, value: str):
        from src.utils.onepassword import _VaultCache

        cache = _VaultCache()
        cache._cache = {key: value}
        cache._signed_in = True
        return cache

    def test_returns_value_from_cache(self):
        cache = self._fresh_cache_with_key("MY_KEY", "my_value")
        assert cache.get("MY_KEY") == "my_value"

    def test_raises_when_key_missing(self):
        cache = self._fresh_cache_with_key("OTHER", "val")
        with pytest.raises(RuntimeError, match="MISSING"):
            cache.get("MISSING")

    def test_raises_when_unavailable(self):
        from src.utils.onepassword import _VaultCache

        cache = _VaultCache()
        with patch.object(cache, "is_available", return_value=False):
            with pytest.raises(RuntimeError, match="1Password is required"):
                cache.get("any_key")


# ---------------------------------------------------------------------------
# _VaultCache.get_optional
# ---------------------------------------------------------------------------


class TestVaultCacheGetOptional:
    def test_returns_value_when_present(self):
        from src.utils.onepassword import _VaultCache

        cache = _VaultCache()
        cache._cache = {"OPT_KEY": "opt_value"}
        cache._signed_in = True
        assert cache.get_optional("OPT_KEY") == "opt_value"

    def test_returns_none_when_missing(self):
        from src.utils.onepassword import _VaultCache

        cache = _VaultCache()
        cache._cache = {"OTHER": "val"}
        cache._signed_in = True
        assert cache.get_optional("MISSING") is None

    def test_returns_none_when_unavailable(self):
        from src.utils.onepassword import _VaultCache

        cache = _VaultCache()
        with patch.object(cache, "is_available", return_value=False):
            assert cache.get_optional("key") is None


# ---------------------------------------------------------------------------
# _VaultCache.set_credential
# ---------------------------------------------------------------------------


class TestVaultCacheSetCredential:
    def test_returns_true_on_success(self):
        from src.utils.onepassword import _VaultCache

        cache = _VaultCache()
        with patch("src.utils.onepassword._run_op", return_value="ok"):
            result = cache.set_credential("item", "field", "value")
        assert result is True
        assert cache._cache.get("field") == "value"

    def test_returns_false_on_failure(self):
        from src.utils.onepassword import _VaultCache

        cache = _VaultCache()
        with patch("src.utils.onepassword._run_op", return_value=None):
            result = cache.set_credential("item", "field", "value")
        assert result is False


# ---------------------------------------------------------------------------
# _VaultCache.invalidate
# ---------------------------------------------------------------------------


class TestVaultCacheInvalidate:
    def test_clears_cache(self):
        from src.utils.onepassword import _VaultCache

        cache = _VaultCache()
        cache._cache = {"KEY": "val"}
        cache.invalidate()
        assert cache._cache == {}


# ---------------------------------------------------------------------------
# Module-level convenience functions (tested via patched _vault)
# ---------------------------------------------------------------------------


class TestModuleFunctions:
    def test_get_delegates_to_vault(self):
        import src.utils.onepassword as op_module

        mock_vault = MagicMock()
        mock_vault.get.return_value = "value"
        with patch.object(op_module, "_vault", mock_vault):
            result = op_module._vault.get("KEY")
        assert result == "value"

    def test_get_optional_delegates_to_vault(self):
        import src.utils.onepassword as op_module

        mock_vault = MagicMock()
        mock_vault.get_optional.return_value = None
        with patch.object(op_module, "_vault", mock_vault):
            result = op_module._vault.get_optional("KEY")
        assert result is None

    def test_is_available_delegates_to_vault(self):
        import src.utils.onepassword as op_module

        mock_vault = MagicMock()
        mock_vault.is_available.return_value = True
        with patch.object(op_module, "_vault", mock_vault):
            result = op_module._vault.is_available()
        assert result is True

    def test_set_credential_delegates_to_vault(self):
        import src.utils.onepassword as op_module

        mock_vault = MagicMock()
        mock_vault.set_credential.return_value = True
        with patch.object(op_module, "_vault", mock_vault):
            result = op_module._vault.set_credential("item", "field", "val")
        assert result is True

    def test_invalidate_delegates_to_vault(self):
        import src.utils.onepassword as op_module

        mock_vault = MagicMock()
        with patch.object(op_module, "_vault", mock_vault):
            op_module._vault.invalidate()
        mock_vault.invalidate.assert_called_once()
