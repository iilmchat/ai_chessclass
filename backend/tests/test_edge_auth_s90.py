"""S-90: реальный IP за прокси, per-account lockout, edge rate-limit."""

from pathlib import Path

import jwt
from fastapi import Request
from fastapi.testclient import TestClient

from app.main import app
from core.config import settings
from tests.conftest import PASSWORD, login, register_verified

_MOUNT = Path("/repo")
ROOT = _MOUNT if (_MOUNT / "deploy").is_dir() else Path(__file__).resolve().parents[2]


def test_proxy_headers_use_forwarded_for_from_trusted_proxy():
    """Доверенный edge передаёт X-Forwarded-For → request.client.host реальный."""
    path = "/__s90_client_ip"

    async def _client_ip(request: Request) -> dict:
        return {"ip": request.client.host if request.client else None}

    app.add_api_route(path, _client_ip, methods=["GET"], include_in_schema=False)
    try:
        with TestClient(app, client=("127.0.0.1", 50000)) as client:
            response = client.get(path, headers={"X-Forwarded-For": "1.2.3.4"})
            assert response.status_code == 200
            assert response.json()["ip"] == "1.2.3.4"

        if settings.proxy_trusted_hosts.strip() != "*":
            # Недоверенный клиент не может подделать IP заголовком.
            with TestClient(app, client=("203.0.113.10", 50000)) as client:
                response = client.get(path, headers={"X-Forwarded-For": "6.6.6.6"})
                assert response.status_code == 200
                assert response.json()["ip"] == "203.0.113.10"
    finally:
        app.router.routes = [
            route
            for route in app.router.routes
            if getattr(route, "path", None) != path
        ]


async def test_account_lockout_does_not_block_other_account(
    make_client, unique_email, redis_client
):
    """5 неудач user_a → 429 только user_a; user_b с того же IP входит."""
    client = await make_client()
    email_a = f"lock-a-{unique_email}"
    email_b = f"lock-b-{unique_email}"
    await register_verified(client, email_a)
    await register_verified(client, email_b)

    bad_a = {"email": email_a, "password": "wrong-password"}
    for _ in range(5):
        response = await client.post("/api/v1/auth/login", json=bad_a)
        assert response.status_code == 401

    # Отдельный аккаунт заблокирован, IP — ещё нет (5 < 50).
    assert await redis_client.exists(f"lockout:account:{email_a}") == 1
    assert await redis_client.exists("lockout:ip:testclient") == 0

    response = await client.post(
        "/api/v1/auth/login", json={"email": email_a, "password": PASSWORD}
    )
    assert response.status_code == 429
    assert response.json()["code"] == "auth_locked_out"

    # Тот же IP, другой аккаунт — вход успешен.
    _c, access, _user_id = await login(client, email_b)
    assert access


def test_hs256_rejected_when_legacy_disabled(monkeypatch):
    """S-90: при JWT_LEGACY_HS256=false старый HS256-токен не принимается."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from core.security import create_access_token, decode_token

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    monkeypatch.setattr(settings, "jwt_algorithm", "RS256")
    monkeypatch.setattr(settings, "jwt_private_key", private)
    monkeypatch.setattr(settings, "jwt_public_key", public)
    monkeypatch.setattr(settings, "jwt_legacy_hs256", False)

    payload = {
        "sub": "1",
        "role": "student",
        "type": "access",
        "exp": 4102444800,
        "iat": 1700000000,
    }
    legacy = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    assert decode_token(legacy) is None
    assert decode_token(create_access_token(1, "student", "novice")) is not None


def test_edge_nginx_auth_rate_limit_and_forwarded_headers():
    """S-90: edge-nginx имеет лимиты auth/API, 429 и X-Forwarded-For."""
    edge = (ROOT / "deploy/nginx/edge.conf").read_text(encoding="utf-8")
    assert "limit_req_zone $binary_remote_addr zone=auth_rl:10m rate=10r/m;" in edge
    assert "limit_req_zone $binary_remote_addr zone=api_rl:10m rate=60r/m;" in edge
    assert "location /api/v1/auth/" in edge
    assert "limit_req zone=auth_rl burst=9 nodelay;" in edge
    assert "limit_req_status 429;" in edge
    assert "limit_req zone=api_rl burst=30 nodelay;" in edge
    assert edge.count("X-Forwarded-For $proxy_add_x_forwarded_for") >= 4
    assert edge.count("X-Real-IP $remote_addr") >= 4

    web = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    assert "X-Forwarded-For $proxy_add_x_forwarded_for" in web
    assert "X-Real-IP $remote_addr" in web
