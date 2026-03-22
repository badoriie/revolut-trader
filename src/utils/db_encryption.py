"""Database encryption utilities using Fernet symmetric encryption.

Encrypts sensitive data at the application level before storing in database.
Encryption key is stored in 1Password under field DATABASE_ENCRYPTION_KEY
in the revolut-trader-credentials item.
"""

from cryptography.fernet import Fernet, InvalidToken
from loguru import logger

import src.utils.onepassword as op


class DatabaseEncryption:
    """Handle database encryption/decryption using Fernet symmetric encryption."""

    def __init__(self):
        """Initialize database encryption with key from 1Password."""
        self._cipher: Fernet | None = None
        self._initialize_encryption()

    def _initialize_encryption(self) -> None:
        """Initialize encryption cipher with key from 1Password.

        If no key exists yet, one is generated and stored automatically so
        that encryption is always active.  Raises ``RuntimeError`` if
        1Password is unavailable, because running without encryption is not
        allowed.
        """
        if not op.is_available():
            raise RuntimeError(
                "1Password CLI is required for database encryption. "
                "Install it with: brew install --cask 1password-cli"
            )

        encryption_key = op.get_optional("DATABASE_ENCRYPTION_KEY")
        if not encryption_key:
            logger.info("No DATABASE_ENCRYPTION_KEY found — generating one now...")
            encryption_key = generate_encryption_key()
            op.set_credential(op.get_credentials_item(), "DATABASE_ENCRYPTION_KEY", encryption_key)
            logger.info("✓ New encryption key generated and stored in 1Password")

        try:
            self._cipher = Fernet(encryption_key.encode())
        except Exception as exc:
            raise RuntimeError(
                "DATABASE_ENCRYPTION_KEY in 1Password is invalid. "
                "Run 'make db-encrypt-setup' to regenerate it."
            ) from exc
        logger.info("✓ Database encryption initialised (1Password key)")

    @property
    def is_enabled(self) -> bool:
        """Check if encryption is enabled."""
        return self._cipher is not None

    def encrypt(self, data: str) -> str:
        """Encrypt a string value. Returns original if encryption is disabled."""
        if not self.is_enabled or not data:
            return data
        try:
            return self._cipher.encrypt(data.encode()).decode()  # type: ignore
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return data

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt an encrypted string value. Returns original if encryption is disabled."""
        if not self.is_enabled or not encrypted_data:
            return encrypted_data
        try:
            return self._cipher.decrypt(encrypted_data.encode()).decode()  # type: ignore
        except InvalidToken:
            logger.warning("Failed to decrypt data (wrong key or corrupted data)")
            return encrypted_data
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return encrypted_data

    def encrypt_dict(self, data: dict, fields: list[str]) -> dict:
        """Encrypt specific fields in a dictionary."""
        if not self.is_enabled:
            return data
        encrypted_data = data.copy()
        for field in fields:
            if field in encrypted_data and encrypted_data[field]:
                encrypted_data[field] = self.encrypt(str(encrypted_data[field]))
        return encrypted_data

    def decrypt_dict(self, data: dict, fields: list[str]) -> dict:
        """Decrypt specific fields in a dictionary."""
        if not self.is_enabled:
            return data
        decrypted_data = data.copy()
        for field in fields:
            if field in decrypted_data and decrypted_data[field]:
                decrypted_data[field] = self.decrypt(str(decrypted_data[field]))
        return decrypted_data


def generate_encryption_key() -> str:
    """Generate a new Fernet encryption key."""
    return Fernet.generate_key().decode()


def setup_database_encryption() -> str:
    """Setup database encryption by generating and storing key in 1Password.

    Returns:
        The generated encryption key

    Raises:
        RuntimeError: If 1Password is not available or setup fails
    """
    if not op.is_available():
        raise RuntimeError(
            "1Password CLI not available. Install it with: brew install --cask 1password-cli"
        )

    existing_key = op.get_optional("DATABASE_ENCRYPTION_KEY")
    if existing_key:
        logger.warning("DATABASE_ENCRYPTION_KEY already exists in 1Password")
        response = input("Regenerate key? This will make old encrypted data unreadable! (yes/no): ")
        if response.lower() != "yes":
            logger.info("Keeping existing encryption key")
            return existing_key

    encryption_key = generate_encryption_key()
    op.set_credential(op.get_credentials_item(), "DATABASE_ENCRYPTION_KEY", encryption_key)
    logger.info("✓ Database encryption key generated and stored in 1Password")
    logger.info("ℹ️  Key ID: " + encryption_key[:16] + "...")
    return encryption_key


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        try:
            key = setup_database_encryption()
            print("\n✅ Database encryption setup complete!")
            print("ℹ️  Encryption key stored securely in 1Password")
            print("ℹ️  The bot will automatically use encryption on next run")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            sys.exit(1)
    else:
        print("Usage: python -m src.utils.db_encryption setup")
        sys.exit(1)
