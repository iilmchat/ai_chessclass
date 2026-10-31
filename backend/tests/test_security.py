"""Юнит-тесты core/security: Argon2id, JWT, parse_duration."""

from datetime import timedelta

import pytest

from core.security import (
    create_access_token,
    decode_token,
    hash_password,
    parse_duration,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("S3cret-pass")
    assert hashed.startswith("$argon2id$")
    assert hashed != "S3cret-pass"
    assert verify_password("S3cret-pass", hashed)
    assert not verify_password("wrong-pass", hashed)
    assert not verify_password("S3cret-pass", "not-a-hash")


def test_parse_duration():
    assert parse_duration("15m") == timedelta(minutes=15)
    assert parse_duration("30d") == timedelta(days=30)
    assert parse_duration("45s") == timedelta(seconds=45)
    assert parse_duration("12h") == timedelta(hours=12)
    with pytest.raises(ValueError, match="длительность"):
        parse_duration("1y")


def test_access_token_roundtrip():
    token = create_access_token(42, "student", level=None)
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["role"] == "student"
    assert payload["type"] == "access"
    assert payload["level"] is None
    assert "exp" in payload and "jti" in payload


def test_access_token_expired():
    token = create_access_token(1, "student", expires_delta=timedelta(seconds=-10))
    assert decode_token(token) is None


def test_decode_garbage():
    assert decode_token("not-a-jwt") is None
    assert decode_token("") is None
