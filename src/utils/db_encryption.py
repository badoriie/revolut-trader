"""Database encryption utilities using Fernet symmetric encryption.

Encrypts sensitive data at the application level before storing in database.
Encryption key is securely stored in 1Password.
"""

from cryptography.fernet import Fernet, InvalidToken
from loguru import logger

from src.utils.onepassword import OnePasswordClient


class DatabaseEncryption:
    """Handle database encryption/decryption using Fernet symmetric encryption."""

    def __init__(self):
        """Initialize database encryption with key from 1Password."""
        self.op_client = OnePasswordClient()
        self._cipher: Fernet | None = None
        self._initialize_encryption()

    def _initialize_encryption(self) -> None:
        """Initialize encryption cipher with key from 1Password."""
        try:
            # Try to get existing key from 1Password
            encryption_key = self.op_client.get_field(
                field_name="database_encryption_key",
            )

            if not encryption_key:
                logger.warning("No database encryption key found in 1Password")
                logger.info("Database encryption is disabled (plaintext storage)")
                return

            # Initialize Fernet cipher with the key
            self._cipher = Fernet(encryption_key.encode())
            logger.info("✓ Database encryption initialized (1Password key)")

        except Exception as e:
            logger.error(f"Failed to initialize database encryption: {e}")
            logger.warning("Database encryption is disabled (plaintext storage)")
            self._cipher = None

    @property
    def is_enabled(self) -> bool:
        """Check if encryption is enabled.

        Returns:
            True if encryption is initialized and ready
        """
        return self._cipher is not None

    def encrypt(self, data: str) -> str:
        """Encrypt a string value.

        Args:
            data: Plain text string to encrypt

        Returns:
            Encrypted string (base64 encoded) or original if encryption disabled
        """
        if not self.is_enabled or not data:
            return data

        try:
            encrypted_bytes = self._cipher.encrypt(data.encode())  # type: ignore
            return encrypted_bytes.decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return data  # Fallback to plaintext

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt an encrypted string value.

        Args:
            encrypted_data: Encrypted string (base64 encoded)

        Returns:
            Decrypted plain text string or original if encryption disabled
        """
        if not self.is_enabled or not encrypted_data:
            return encrypted_data

        try:
            decrypted_bytes = self._cipher.decrypt(encrypted_data.encode())  # type: ignore
            return decrypted_bytes.decode()
        except InvalidToken:
            logger.warning("Failed to decrypt data (wrong key or corrupted data)")
            return encrypted_data  # Return as-is if can't decrypt
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return encrypted_data

    def encrypt_dict(self, data: dict, fields: list[str]) -> dict:
        """Encrypt specific fields in a dictionary.

        Args:
            data: Dictionary containing data to encrypt
            fields: List of field names to encrypt

        Returns:
            Dictionary with specified fields encrypted
        """
        if not self.is_enabled:
            return data

        encrypted_data = data.copy()
        for field in fields:
            if field in encrypted_data and encrypted_data[field]:
                encrypted_data[field] = self.encrypt(str(encrypted_data[field]))

        return encrypted_data

    def decrypt_dict(self, data: dict, fields: list[str]) -> dict:
        """Decrypt specific fields in a dictionary.

        Args:
            data: Dictionary containing encrypted data
            fields: List of field names to decrypt

        Returns:
            Dictionary with specified fields decrypted
        """
        if not self.is_enabled:
            return data

        decrypted_data = data.copy()
        for field in fields:
            if field in decrypted_data and decrypted_data[field]:
                decrypted_data[field] = self.decrypt(str(decrypted_data[field]))

        return decrypted_data


def generate_encryption_key() -> str:
    """Generate a new Fernet encryption key.

    Returns:
        Base64-encoded 32-byte encryption key
    """
    return Fernet.generate_key().decode()


def setup_database_encryption() -> str:
    """Setup database encryption by generating and storing key in 1Password.

    Returns:
        The generated encryption key

    Raises:
        RuntimeError: If 1Password is not available or setup fails
    """
    op_client = OnePasswordClient()

    if not op_client.is_available():
        raise RuntimeError(
            "1Password CLI not available. " "Install it with: brew install --cask 1password-cli"
        )

    # Check if key already exists
    existing_key = op_client.get_field(
        field_name="database_encryption_key",
    )

    if existing_key:
        logger.warning("Database encryption key already exists in 1Password")
        response = input("Regenerate key? This will make old encrypted data unreadable! (yes/no): ")
        if response.lower() != "yes":
            logger.info("Keeping existing encryption key")
            return existing_key

    # Generate new encryption key
    encryption_key = generate_encryption_key()

    # Store in 1Password
    op_client.set_field(
        field_name="database_encryption_key",
        value=encryption_key,
    )

    logger.info("✓ Database encryption key generated and stored in 1Password")
    logger.info("ℹ️  Key ID: " + encryption_key[:16] + "...")

    return encryption_key


if __name__ == "__main__":
    # CLI tool for setting up database encryption
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
