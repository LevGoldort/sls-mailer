"""Unit tests for password hashing utilities"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.auth_password import hash_password, verify_password, needs_rehash


class TestHashPassword:
    def test_returns_string(self):
        result = hash_password("secret123")
        assert isinstance(result, str)

    def test_hash_is_argon2_format(self):
        result = hash_password("secret123")
        assert result.startswith("$argon2")

    def test_different_hashes_for_same_password(self):
        """Соль генерируется заново при каждом вызове"""
        h1 = hash_password("secret123")
        h2 = hash_password("secret123")
        assert h1 != h2

    def test_different_passwords_give_different_hashes(self):
        h1 = hash_password("password1")
        h2 = hash_password("password2")
        assert h1 != h2

    def test_special_characters(self):
        result = hash_password("p@$$w0rd!#%^&*()")
        assert result.startswith("$argon2")

    def test_long_password(self):
        result = hash_password("a" * 256)
        assert result.startswith("$argon2")

    def test_unicode_password(self):
        result = hash_password("пароль123")
        assert result.startswith("$argon2")

    def test_empty_password_raises(self):
        with pytest.raises(ValueError, match="empty"):
            hash_password("")


class TestVerifyPassword:
    def test_correct_password_returns_true(self):
        h = hash_password("secret123")
        assert verify_password("secret123", h) is True

    def test_wrong_password_returns_false(self):
        h = hash_password("secret123")
        assert verify_password("wrong", h) is False

    def test_case_sensitive(self):
        h = hash_password("Secret123")
        assert verify_password("secret123", h) is False

    def test_extra_whitespace_returns_false(self):
        h = hash_password("secret123")
        assert verify_password("secret123 ", h) is False

    def test_special_characters_roundtrip(self):
        pwd = "p@$$w0rd!#%^&*()"
        h = hash_password(pwd)
        assert verify_password(pwd, h) is True

    def test_unicode_roundtrip(self):
        pwd = "пароль123"
        h = hash_password(pwd)
        assert verify_password(pwd, h) is True

    def test_empty_password_raises(self):
        h = hash_password("secret")
        with pytest.raises(ValueError, match="empty"):
            verify_password("", h)

    def test_empty_hash_raises(self):
        with pytest.raises(ValueError, match="empty"):
            verify_password("secret", "")

    def test_invalid_hash_returns_false(self):
        assert verify_password("secret", "not-a-valid-hash") is False

    def test_multiple_verifications_same_hash(self):
        """Один хэш можно проверять многократно"""
        h = hash_password("secret123")
        assert verify_password("secret123", h) is True
        assert verify_password("secret123", h) is True
        assert verify_password("wrong", h) is False


class TestNeedsRehash:
    def test_fresh_hash_does_not_need_rehash(self):
        h = hash_password("secret123")
        assert needs_rehash(h) is False
