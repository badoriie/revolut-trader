"""Unit tests for DatabaseEncryption.

Tests both the disabled (no key) and enabled (with Fernet key) paths.
"""

from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from src.utils.db_encryption import (
    DatabaseEncryption,
    generate_encryption_key,
    setup_database_encryption,
)


class TestDatabaseEncryptionDisabled:
    """When no encryption key is available, all data is passed through unchanged."""

    @pytest.fixture
    def enc(self):
        # conftest patches get_optional to return None → encryption disabled
        return DatabaseEncryption()

    def test_is_not_enabled(self, enc):
        assert enc.is_enabled is False

    def test_encrypt_returns_plaintext(self, enc):
        assert enc.encrypt("hello") == "hello"

    def test_encrypt_empty_string_passthrough(self, enc):
        assert enc.encrypt("") == ""

    def test_decrypt_returns_plaintext(self, enc):
        assert enc.decrypt("some_ciphertext") == "some_ciphertext"

    def test_decrypt_empty_string_passthrough(self, enc):
        assert enc.decrypt("") == ""

    def test_encrypt_dict_returns_original(self, enc):
        data = {"secret": "value", "public": "open"}
        result = enc.encrypt_dict(data, ["secret"])
        assert result == data

    def test_decrypt_dict_returns_original(self, enc):
        data = {"secret": "cipher", "public": "open"}
        result = enc.decrypt_dict(data, ["secret"])
        assert result == data


class TestDatabaseEncryptionEnabled:
    """When a valid Fernet key is available, data is encrypted/decrypted correctly."""

    @pytest.fixture
    def valid_key(self):
        return Fernet.generate_key().decode()

    @pytest.fixture
    def enc(self, valid_key):
        with patch("src.utils.onepassword.get_optional", return_value=valid_key):
            return DatabaseEncryption()

    def test_is_enabled(self, enc):
        assert enc.is_enabled is True

    def test_encrypt_produces_different_output(self, enc):
        plaintext = "sensitive_data"
        assert enc.encrypt(plaintext) != plaintext

    def test_decrypt_restores_plaintext(self, enc):
        plaintext = "my_secret_value"
        encrypted = enc.encrypt(plaintext)
        assert enc.decrypt(encrypted) == plaintext

    def test_encrypt_empty_string_passthrough(self, enc):
        assert enc.encrypt("") == ""

    def test_decrypt_empty_string_passthrough(self, enc):
        assert enc.decrypt("") == ""

    def test_decrypt_invalid_token_returns_original(self, enc):
        invalid = "not-a-valid-fernet-token"
        result = enc.decrypt(invalid)
        assert result == invalid

    def test_encrypt_dict_encrypts_specified_field(self, enc):
        data = {"secret": "value", "public": "open"}
        result = enc.encrypt_dict(data, ["secret"])
        assert result["secret"] != "value"
        assert result["public"] == "open"

    def test_encrypt_dict_skips_empty_field(self, enc):
        data = {"secret": "", "public": "value"}
        result = enc.encrypt_dict(data, ["secret"])
        assert result["secret"] == ""

    def test_encrypt_dict_skips_missing_field(self, enc):
        data = {"public": "value"}
        result = enc.encrypt_dict(data, ["missing"])
        assert result == data

    def test_encrypt_dict_does_not_mutate_original(self, enc):
        data = {"secret": "value"}
        enc.encrypt_dict(data, ["secret"])
        assert data["secret"] == "value"

    def test_decrypt_dict_restores_field(self, enc):
        original = {"secret": "value", "public": "open"}
        encrypted = enc.encrypt_dict(original, ["secret"])
        decrypted = enc.decrypt_dict(encrypted, ["secret"])
        assert decrypted["secret"] == "value"
        assert decrypted["public"] == "open"

    def test_decrypt_dict_skips_empty_field(self, enc):
        data = {"secret": ""}
        result = enc.decrypt_dict(data, ["secret"])
        assert result["secret"] == ""

    def test_decrypt_dict_skips_missing_field(self, enc):
        data = {"public": "value"}
        result = enc.decrypt_dict(data, ["missing"])
        assert result == data

    def test_encrypt_failure_returns_original(self, enc):
        enc._cipher = MagicMock()
        enc._cipher.encrypt.side_effect = Exception("fail")
        result = enc.encrypt("data")
        assert result == "data"

    def test_decrypt_exception_returns_original(self, enc):
        enc._cipher = MagicMock()
        enc._cipher.decrypt.side_effect = Exception("fail")
        result = enc.decrypt("data")
        assert result == "data"

    def test_initialization_failure_disables_encryption(self):
        """If Fernet init fails with a bad key, encryption is disabled."""
        with patch("src.utils.onepassword.get_optional", return_value="not-a-valid-fernet-key"):
            enc = DatabaseEncryption()
        assert enc.is_enabled is False


class TestGenerateEncryptionKey:
    def test_generates_non_empty_key(self):
        key = generate_encryption_key()
        assert len(key) > 0

    def test_generated_key_is_valid_fernet_key(self):
        key = generate_encryption_key()
        Fernet(key.encode())  # Raises if invalid

    def test_each_call_produces_unique_key(self):
        key1 = generate_encryption_key()
        key2 = generate_encryption_key()
        assert key1 != key2


class TestSetupDatabaseEncryption:
    def test_raises_when_op_unavailable(self):
        import src.utils.db_encryption as enc_module

        with patch.object(enc_module.op, "is_available", return_value=False):
            with pytest.raises(RuntimeError, match="1Password CLI not available"):
                setup_database_encryption()

    def test_generates_key_when_none_exists(self):
        import src.utils.db_encryption as enc_module

        with patch.object(enc_module.op, "is_available", return_value=True):
            with patch.object(enc_module.op, "get_optional", return_value=None):
                with patch.object(enc_module.op, "set_credential", return_value=True):
                    key = setup_database_encryption()
        assert len(key) > 0
        Fernet(key.encode())  # Valid Fernet key

    def test_returns_existing_key_when_user_declines_regeneration(self):
        import src.utils.db_encryption as enc_module

        existing = Fernet.generate_key().decode()
        with patch.object(enc_module.op, "is_available", return_value=True):
            with patch.object(enc_module.op, "get_optional", return_value=existing):
                with patch("builtins.input", return_value="no"):
                    result = setup_database_encryption()
        assert result == existing

    def test_regenerates_key_when_user_confirms(self):
        import src.utils.db_encryption as enc_module

        existing = Fernet.generate_key().decode()
        with patch.object(enc_module.op, "is_available", return_value=True):
            with patch.object(enc_module.op, "get_optional", return_value=existing):
                with patch("builtins.input", return_value="yes"):
                    with patch.object(enc_module.op, "set_credential", return_value=True):
                        result = setup_database_encryption()
        assert result != existing
        Fernet(result.encode())  # Still a valid key
