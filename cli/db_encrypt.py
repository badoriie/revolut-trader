#!/usr/bin/env python3
"""Database encryption management CLI.

Manages database encryption keys and provides tools for encrypting/decrypting data.
"""

import sys

from loguru import logger

from src.utils.db_encryption import DatabaseEncryption, setup_database_encryption


def setup_encryption():
    """Setup database encryption by generating and storing key in 1Password."""
    print("🔐 Database Encryption Setup")
    print("=" * 50)
    print()
    print("This will generate an encryption key and store it in 1Password.")
    print("All sensitive data will be encrypted before storing in the database.")
    print()

    try:
        key = setup_database_encryption()
        print()
        print("✅ Database encryption setup complete!")
        print("=" * 50)
        print()
        print("✓ Encryption key generated")
        print("✓ Key stored securely in 1Password")
        print("✓ The bot will automatically use encryption on next run")
        print()
        print(f"Key ID: {key[:16]}...")
        print()

    except Exception as e:
        print()
        print(f"❌ Error: {e}")
        print()
        sys.exit(1)


def check_encryption_status():
    """Check if database encryption is enabled and working."""
    print("🔐 Database Encryption Status")
    print("=" * 50)
    print()

    db_encryption = DatabaseEncryption()

    if db_encryption.is_enabled:
        print("✅ Database encryption is ENABLED")
        print()
        print("✓ Encryption key loaded from 1Password")
        print("✓ Sensitive data will be encrypted")
        print()

        # Test encryption/decryption
        test_data = "test-encryption-12345"
        encrypted = db_encryption.encrypt(test_data)
        decrypted = db_encryption.decrypt(encrypted)

        if decrypted == test_data:
            print("✓ Encryption test PASSED")
        else:
            print("❌ Encryption test FAILED")
            sys.exit(1)

    else:
        print("⚠️  Database encryption is DISABLED")
        print()
        print("Data will be stored in PLAINTEXT (not encrypted).")
        print()
        print("To enable encryption:")
        print("  python cli/db_encrypt.py setup")
        print("  OR")
        print("  make db-encrypt-setup")
        print()


def disable_encryption():
    """Disable database encryption by removing key from 1Password."""
    print("🔓 Disable Database Encryption")
    print("=" * 50)
    print()
    print("⚠️  WARNING: This will remove the encryption key!")
    print("⚠️  Existing encrypted data will become unreadable!")
    print()

    response = input("Are you sure you want to disable encryption? (yes/no): ")

    if response.lower() != "yes":
        print("Cancelled")
        return

    # Note: 1Password CLI doesn't have a delete field command
    # We'd need to manually remove it from the 1Password app
    print()
    print("To disable encryption:")
    print("1. Open 1Password app")
    print("2. Find 'revolut-trader-credentials' item")
    print("3. Remove the 'database_encryption_key' field")
    print()


def main():
    """Main entry point for database encryption management."""
    if len(sys.argv) < 2:
        print("Database Encryption Management CLI")
        print()
        print("Usage:")
        print("  python cli/db_encrypt.py <command>")
        print()
        print("Commands:")
        print("  setup   - Setup database encryption (generate key + store in 1Password)")
        print("  status  - Check encryption status")
        print("  disable - Disable database encryption")
        print()
        print("Examples:")
        print("  python cli/db_encrypt.py setup")
        print("  python cli/db_encrypt.py status")
        print()
        print("Or use Makefile:")
        print("  make db-encrypt-setup")
        print("  make db-encrypt-status")
        sys.exit(1)

    command = sys.argv[1]

    try:
        if command == "setup":
            setup_encryption()
        elif command == "status":
            check_encryption_status()
        elif command == "disable":
            disable_encryption()
        else:
            print(f"Unknown command: {command}")
            print("Run without arguments to see available commands")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Command failed: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
