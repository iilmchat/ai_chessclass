"""S-47: RS256/JWKS, переходный HS256, role/scope/PII и аудит."""

import jwt
import sqlalchemy as sa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from core.config import settings
from core.db import session_factory
from core.security import create_access_token, decode_token, jwks
from domains.auth.models import User, UserRole
from tests.conftest import API, PASSWORD, login, make_direct_user


def _rsa_keys() -> tuple[str, str]:
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
    return private, public


def _payload() -> dict:
    return {
        "sub": "1",
        "role": "student",
        "level": "novice",
        "type": "access",
        "exp": 4102444800,
        "iat": 1700000000,
    }


def test_rs256_jwks_and_hs256_transition(monkeypatch):
    private, public = _rsa_keys()
    monkeypatch.setattr(settings, "jwt_algorithm", "RS256")
    monkeypatch.setattr(settings, "jwt_private_key", private)
    monkeypatch.setattr(settings, "jwt_public_key", public)
    monkeypatch.setattr(settings, "jwt_kid", "test-kid")
    monkeypatch.setattr(settings, "jwt_legacy_hs256", True)

    token = create_access_token(1, "student", "novice")
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "RS256" and header["kid"] == "test-kid"
    payload = decode_token(token)
    assert payload is not None and payload["sub"] == "1"

    keys = jwks()["keys"]
    assert len(keys) == 1
    assert keys[0]["kid"] == "test-kid" and keys[0]["kty"] == "RSA"

    legacy = jwt.encode(_payload(), settings.jwt_secret, algorithm="HS256")
    assert decode_token(legacy) is not None

    # confusion/algorithm: только RS256 и (legacy) HS256
    none_token = jwt.encode(_payload(), key="", algorithm="none")
    assert decode_token(none_token) is None
    other_alg = jwt.encode(_payload(), settings.jwt_secret, algorithm="HS512")
    assert decode_token(other_alg) is None

    monkeypatch.setattr(settings, "jwt_legacy_hs256", False)
    assert decode_token(legacy) is None
    assert decode_token(token) is not None


async def test_jwks_endpoint(make_client, monkeypatch):
    private, public = _rsa_keys()
    monkeypatch.setattr(settings, "jwt_algorithm", "RS256")
    monkeypatch.setattr(settings, "jwt_private_key", private)
    monkeypatch.setattr(settings, "jwt_public_key", public)
    client = await make_client()
    response = await client.get(f"{API}/auth/jwks")
    assert response.status_code == 200
    assert response.json()["keys"]
    response = await client.get("/.well-known/jwks.json")
    assert response.status_code == 200


async def test_role_change_scope_anonymize_and_audit(
    admin_client, make_client, unique_email
):
    client = await make_client()
    student_email = f"role-{unique_email}"
    await make_direct_user(student_email, UserRole.STUDENT)
    _c, _student_access, student_id = await login(client, student_email)

    # login audit (actor student)
    response = await admin_client.get(
        f"{API}/admin/audit/logs", params={"action": "auth.login.success"}
    )
    assert response.status_code == 200
    assert response.json()["total"] >= 1

    response = await admin_client.patch(
        f"{API}/admin/users/{student_id}/role", json={"role": "teacher"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "teacher"
    response = await admin_client.get(
        f"{API}/admin/audit/logs", params={"action": "auth.role.change"}
    )
    assert response.status_code == 200
    assert response.json()["total"] >= 1

    auditor_email = f"scope-{unique_email}"
    await make_direct_user(auditor_email, UserRole.AUDITOR)
    _c, auditor_access, auditor_id = await login(client, auditor_email)
    auditor_headers = {"Authorization": f"Bearer {auditor_access}"}
    response = await admin_client.patch(
        f"{API}/admin/users/{auditor_id}/auditor-scope",
        json={"scopes": {"flags": False, "audit": True, "reports": True}},
    )
    assert response.status_code == 200, response.text
    response = await client.get(
        f"{API}/admin/anticheat/flags", headers=auditor_headers
    )
    assert response.status_code == 403
    response = await client.get(f"{API}/admin/audit/logs", headers=auditor_headers)
    assert response.status_code == 200

    # PII-анонимизация: email/пароль/профиль, деактивация
    anon_email = f"anon-{unique_email}"
    await make_direct_user(anon_email, UserRole.STUDENT)
    _c, _anon_access, anon_id = await login(client, anon_email)
    response = await admin_client.post(f"{API}/admin/users/{anon_id}/anonymize")
    assert response.status_code == 200, response.text
    async with session_factory() as session:
        row = await session.get(User, anon_id)
        assert row is not None
        assert row.email.startswith("anon-") and row.is_active is False
        await session.execute(sa.delete(User).where(User.id == anon_id))
        await session.commit()
    response = await client.post(
        f"{API}/auth/login", json={"email": anon_email, "password": PASSWORD}
    )
    assert response.status_code in (401, 403)
