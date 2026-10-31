"""Безопасность: Argon2id-пароли и access-JWT (Design §13.1).

Refresh-токены — opaque, хранятся хэшем в БД (domains/auth/service.py);
здесь только утилиты без доменных зависимостей (порт teacher security.py
с заменой bcrypt → Argon2id, UUID → BIGINT).
"""

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

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


def create_access_token(
    user_id: int,
    role: str,
    level: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """HS256 access-JWT: sub, role, level, type=access (Design §13.1).

    `level` заполняется из user_profiles в S-03; до тех пор — None.
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
    return str(jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm))


def decode_token(token: str) -> dict[str, Any] | None:
    """Декодирование с проверкой подписи и TTL; любая ошибка → None."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError:
        return None
    return dict(payload)
