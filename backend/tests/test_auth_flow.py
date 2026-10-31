"""E2E auth (DoD S-02): register → verify → login → me → refresh(ротация+reuse)
→ logout; плюс дубликат email, lockout 5/мин/IP, password-reset.

Контракты — docs/SPEC.md; спецификация — Design §13.1.
"""

import httpx
from conftest import API, PASSWORD, fetch_email_token, register_verified

from domains.auth.models import EmailTokenKind


def _cookie_value(response: httpx.Response, name: str) -> str:
    raw = response.headers.get("set-cookie", "")
    for part in raw.split(";"):
        part = part.strip()
        if part.startswith(f"{name}="):
            return part.split("=", 1)[1]
    raise AssertionError(f"cookie {name} не найден: {raw!r}")


async def test_full_auth_flow(make_client, unique_email):
    client = await make_client()

    # 1. регистрация: camelCase, роль student, не верифицирован
    response = await client.post(
        f"{API}/auth/register", json={"email": unique_email, "password": PASSWORD}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == unique_email
    assert body["role"] == "student"
    assert body["emailVerified"] is False
    assert isinstance(body["id"], str) and body["id"].isdigit()

    # 2. логин до верификации → 403 (RFC 7807)
    response = await client.post(
        f"{API}/auth/login", json={"email": unique_email, "password": PASSWORD}
    )
    assert response.status_code == 403
    assert response.json()["code"] == "auth_email_not_verified"
    assert response.headers["content-type"].startswith("application/problem+json")

    # 3. верификация: токен одноразовый (консольный SMTP — в логах api)
    token = await fetch_email_token(unique_email, EmailTokenKind.VERIFY)
    response = await client.post(f"{API}/auth/verify", json={"token": token})
    assert response.status_code == 200 and response.json()["ok"] is True
    response = await client.post(f"{API}/auth/verify", json={"token": token})
    assert response.status_code == 401

    # 4. логин: access + refresh в HttpOnly-cookie (path=/api/v1/auth)
    response = await client.post(
        f"{API}/auth/login", json={"email": unique_email, "password": PASSWORD}
    )
    assert response.status_code == 200
    auth = response.json()
    assert auth["tokenType"] == "Bearer"
    assert auth["user"]["emailVerified"] is True
    access = str(auth["accessToken"])
    old_refresh = _cookie_value(response, "cc_refresh")
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "path=/api/v1/auth" in set_cookie

    # 5. /me по Bearer
    response = await client.get(
        f"{API}/auth/me", headers={"Authorization": f"Bearer {access}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == unique_email

    # 6. refresh: ротация — новая пара, старый refresh отозван
    response = await client.post(f"{API}/auth/refresh")
    assert response.status_code == 200
    new_access = str(response.json()["accessToken"])
    assert new_access != access
    new_refresh = _cookie_value(response, "cc_refresh")
    assert new_refresh != old_refresh

    # 7. reuse отозванного refresh → 401 + отзыв ВСЕХ сессий пользователя.
    #    Отдельный клиент с пустой cookie-jar: httpx склеивает явный Cookie
    #    с jar-печеньками — нужен чистый заголовок.
    replay_client = await make_client()
    response = await replay_client.post(
        f"{API}/auth/refresh", headers={"Cookie": f"cc_refresh={old_refresh}"}
    )
    assert response.status_code == 401
    response = await replay_client.post(
        f"{API}/auth/refresh", headers={"Cookie": f"cc_refresh={new_refresh}"}
    )
    assert response.status_code == 401

    # 8. повторный логин → logout → refresh 401
    response = await client.post(
        f"{API}/auth/login", json={"email": unique_email, "password": PASSWORD}
    )
    assert response.status_code == 200
    response = await client.post(f"{API}/auth/logout")
    assert response.status_code == 200
    response = await client.post(f"{API}/auth/refresh")
    assert response.status_code == 401

    # 9. /me без токена и с мусорным токеном → 401
    response = await client.get(f"{API}/auth/me")
    assert response.status_code == 401
    response = await client.get(
        f"{API}/auth/me", headers={"Authorization": "Bearer garbage"}
    )
    assert response.status_code == 401


async def test_register_duplicate_email(make_client, unique_email):
    client = await make_client()
    payload = {"email": unique_email, "password": PASSWORD}
    response = await client.post(f"{API}/auth/register", json=payload)
    assert response.status_code == 201
    response = await client.post(f"{API}/auth/register", json=payload)
    assert response.status_code == 409
    assert response.json()["code"] == "auth_email_taken"


async def test_login_lockout_after_five_failures(make_client, unique_email):
    client = await make_client()
    await register_verified(client, unique_email)

    bad = {"email": unique_email, "password": "wrong-password"}
    for _ in range(5):
        response = await client.post(f"{API}/auth/login", json=bad)
        assert response.status_code == 401

    # даже верные креды → 429 lockout (Design §13.1: 5/мин/IP → 10 мин)
    response = await client.post(
        f"{API}/auth/login", json={"email": unique_email, "password": PASSWORD}
    )
    assert response.status_code == 429
    assert response.json()["code"] == "auth_locked_out"


async def test_password_reset_flow(make_client, unique_email):
    client = await make_client()
    await register_verified(client, unique_email)

    response = await client.post(
        f"{API}/auth/password-reset", json={"email": unique_email}
    )
    assert response.status_code == 202 and response.json()["ok"] is True

    # неизвестный email — тот же ответ (не раскрываем существование)
    response = await client.post(
        f"{API}/auth/password-reset", json={"email": f"no-{unique_email}"}
    )
    assert response.status_code == 202

    token = await fetch_email_token(unique_email, EmailTokenKind.RESET)
    response = await client.post(
        f"{API}/auth/password-reset/confirm",
        json={"token": token, "newPassword": "NewPassw0rd!456"},
    )
    assert response.status_code == 200

    # старый пароль больше не входит; новый — входит
    response = await client.post(
        f"{API}/auth/login", json={"email": unique_email, "password": PASSWORD}
    )
    assert response.status_code == 401
    response = await client.post(
        f"{API}/auth/login",
        json={"email": unique_email, "password": "NewPassw0rd!456"},
    )
    assert response.status_code == 200
