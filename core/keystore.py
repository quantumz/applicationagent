"""
keystore.py — Secure API key storage using Argon2

The API key is hashed with Argon2 and stored in the settings table.
The plaintext key is held in os.environ at runtime only.
It is never written to disk as plaintext.

Cloud migration: replace set_key() / verify_key() with
Vault or AWS Secrets Manager calls. Interface unchanged.
"""
import os
import sqlite3

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

ph = PasswordHasher()


def _get_conn() -> sqlite3.Connection:
    """Get a database connection using the app's existing DB path."""
    from core.database import get_db
    return get_db()


def set_key(plaintext_key: str) -> None:
    """
    Hash the API key with Argon2 and store in settings table.
    Set os.environ for runtime use.
    Never writes plaintext to disk.
    """
    key_hash = ph.hash(plaintext_key)
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) "
            "VALUES (?, ?, datetime('now'))",
            ('api_key_hash', key_hash)
        )
        conn.commit()
    finally:
        conn.close()
    os.environ['ANTHROPIC_API_KEY'] = plaintext_key


def verify_key(plaintext_key: str) -> bool:
    """Verify a plaintext key against the stored Argon2 hash."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            ('api_key_hash',)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return False
    try:
        return ph.verify(row[0], plaintext_key)
    except (VerifyMismatchError, InvalidHashError):
        return False


def is_key_configured() -> bool:
    """Check if a key hash exists in the database."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM settings WHERE key = ?",
            ('api_key_hash',)
        ).fetchone()
    finally:
        conn.close()
    return row is not None


def clear_key() -> None:
    """Remove the key from the database and os.environ."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM settings WHERE key = ?", ('api_key_hash',))
        conn.commit()
    finally:
        conn.close()
    os.environ.pop('ANTHROPIC_API_KEY', None)


def mask_key(plaintext_key: str) -> str:
    """Return a safe display string. Never log the full key."""
    if len(plaintext_key) < 12:
        return "***"
    return plaintext_key[:12] + "..." + "*" * 8
