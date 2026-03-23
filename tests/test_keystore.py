"""
Tests for core/keystore.py — Argon2-based API key storage.

Uses the shared `test_db` fixture which patches DB_PATH to a temp file
and calls init_db(), so the settings table is always present.
"""
import os
import pytest
import core.database as db_module
from core import keystore


@pytest.fixture(autouse=True)
def clean_environ():
    """Remove ANTHROPIC_API_KEY from os.environ before and after each test."""
    os.environ.pop('ANTHROPIC_API_KEY', None)
    yield
    os.environ.pop('ANTHROPIC_API_KEY', None)


# ── set_key ───────────────────────────────────────────────────────────────────

class TestSetKey:

    def test_sets_environ(self, test_db):
        keystore.set_key('sk-ant-test-key-abc123')
        assert os.environ.get('ANTHROPIC_API_KEY') == 'sk-ant-test-key-abc123'

    def test_stores_hash_not_plaintext(self, test_db):
        keystore.set_key('sk-ant-test-key-abc123')
        conn = db_module.get_db()
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = 'api_key_hash'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[0] != 'sk-ant-test-key-abc123'
        assert row[0].startswith('$argon2')

    def test_overwrites_existing_hash(self, test_db):
        keystore.set_key('sk-ant-first-key')
        keystore.set_key('sk-ant-second-key')
        conn = db_module.get_db()
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM settings WHERE key = 'api_key_hash'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert count == 1
        assert os.environ.get('ANTHROPIC_API_KEY') == 'sk-ant-second-key'


# ── verify_key ────────────────────────────────────────────────────────────────

class TestVerifyKey:

    def test_correct_key_returns_true(self, test_db):
        keystore.set_key('sk-ant-verify-me')
        assert keystore.verify_key('sk-ant-verify-me') is True

    def test_wrong_key_returns_false(self, test_db):
        keystore.set_key('sk-ant-verify-me')
        assert keystore.verify_key('sk-ant-wrong-key') is False

    def test_no_key_configured_returns_false(self, test_db):
        assert keystore.verify_key('sk-ant-anything') is False


# ── is_key_configured ─────────────────────────────────────────────────────────

class TestIsKeyConfigured:

    def test_false_when_no_key(self, test_db):
        assert keystore.is_key_configured() is False

    def test_true_after_set_key(self, test_db):
        keystore.set_key('sk-ant-configured')
        assert keystore.is_key_configured() is True


# ── clear_key ─────────────────────────────────────────────────────────────────

class TestClearKey:

    def test_removes_from_environ(self, test_db):
        keystore.set_key('sk-ant-clear-me')
        keystore.clear_key()
        assert 'ANTHROPIC_API_KEY' not in os.environ

    def test_removes_from_db(self, test_db):
        keystore.set_key('sk-ant-clear-me')
        keystore.clear_key()
        assert keystore.is_key_configured() is False

    def test_clear_with_no_key_is_safe(self, test_db):
        keystore.clear_key()  # should not raise


# ── mask_key ──────────────────────────────────────────────────────────────────

class TestMaskKey:

    def test_masks_normal_key(self):
        result = keystore.mask_key('sk-ant-api03-abc')
        assert result.startswith('sk-ant-api03')
        assert '...' in result
        assert 'abc' not in result

    def test_short_key_returns_stars(self):
        assert keystore.mask_key('short') == '***'

    def test_full_key_never_returned(self):
        key = 'sk-ant-api03-abcdefghijklmnop'
        result = keystore.mask_key(key)
        assert result != key
