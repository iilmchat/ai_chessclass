"""Безопасность: Argon2id-пароли и access-JWT (Design §13.1).

Refresh-токены — opaque, хранятся хэшем в БД (domains/auth/service.py);
здесь только утилиты без доменных зависимостей (порт teacher security.py
с заменой bcrypt → Argon2id, UUID → BIGINT).
"""

import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from jwt.algorithms import RSAAlgorithm

from core.config import settings

_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}

_password_hasher = PasswordHasher(
    time_cost=settings.argon2_time_cost,
    memory_cost=settings.argon2_memory_cost,
    parallelism=settings.argon2_parallelism,
)


def parse_duration(value: str) -> timedelta:
    """Человекочитаемая длительность ('15m', '30d', '45s', '12h') → timedelta."""
    match = re.fullmatch(r"(\d+)\s*([smhd])", value.strip().lower())
    if match is None:
        raise ValueError(f"Некорректная длительность: {value!r}")
    amount, unit = int(match.group(1)), match.group(2)
    return timedelta(seconds=amount * _DURATION_UNITS[unit])


def hash_password(password: str) -> str:
    """Argon2id-хэш (параметры — из config)."""
    return _password_hasher.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Проверка пароля по Argon2id-хэшу; любые ошибки → False."""
    try:
        return _password_hasher.verify(password_hash, plain_password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def _read_key(value: str, path: str) -> str:
    """PEM из env или файла; поддерживает \\n в env."""
    if path:
        return Path(path).read_text(encoding="utf-8").strip()
    return value.replace("\\n", "\n").strip() if value else ""


def _jwt_algorithm() -> str:
    return settings.jwt_algorithm.upper()


def _signing_key() -> Any:
    if _jwt_algorithm() == "RS256":
        key = _read_key(settings.jwt_private_key, settings.jwt_private_key_path)
        if not key:
            raise RuntimeError(
                "JWT_ALGORITHM=RS256, но JWT_PRIVATE_KEY/JWT_PRIVATE_KEY_PATH не задан"
            )
        return key
    return settings.jwt_secret


def _verification_key(algorithm: str) -> Any:
    if algorithm == "RS256":
        key = _read_key(settings.jwt_public_key, settings.jwt_public_key_path)
        if not key:
            raise RuntimeError(
                "JWT_ALGORITHM=RS256, но JWT_PUBLIC_KEY/JWT_PUBLIC_KEY_PATH не задан"
            )
        return key
    return settings.jwt_secret


def create_access_token(
    user_id: int,
    role: str,
    level: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Access-JWT: sub, role, level, type=access (Design §13.1).

    RS256 при `JWT_ALGORITHM=RS256` (ключи из env/файлов), иначе HS256.
    """
    now = datetime.now(UTC)
    expire = now + (expires_delta or parse_duration(settings.jwt_ttl))
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "level": level,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    algorithm = _jwt_algorithm()
    headers = {"kid": settings.jwt_kid} if algorithm == "RS256" else None
    return str(
        jwt.encode(
            payload,
            _signing_key(),
            algorithm=algorithm,
            headers=headers,
        )
    )


def decode_token(token: str) -> dict[str, Any] | None:
    """Проверка подписи/TTL; RS256 + переходный HS256 (legacy)."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        return None
    algorithm = str(header.get("alg") or "")
    configured = _jwt_algorithm()
    allowed = {configured}
    if settings.jwt_legacy_hs256:
        allowed.add("HS256")
    if algorithm not in allowed:
        return None
    try:
        payload = jwt.decode(
            token,
            _verification_key(algorithm),
            algorithms=[algorithm],
            options={"require": ["exp", "sub", "type"]},
        )
    except (jwt.PyJWTError, RuntimeError, OSError):
        return None
    if payload.get("type") != "access":
        return None
    return dict(payload)


def jwks() -> dict:
    """Публичный JWKS для RS256; для HS256 — пустой набор."""
    if _jwt_algorithm() != "RS256":
        return {"keys": []}
    key = _read_key(settings.jwt_public_key, settings.jwt_public_key_path)
    if not key:
        return {"keys": []}
    try:
        key_obj = load_pem_public_key(key.encode())
        if not isinstance(key_obj, RSAPublicKey):
            return {"keys": []}
        jwk = RSAAlgorithm.to_jwk(key_obj, as_dict=True)
    except (jwt.PyJWTError, ValueError):
        return {"keys": []}
    jwk.update({"kid": settings.jwt_kid, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}
