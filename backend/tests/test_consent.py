"""S-74: parental consent workflow (COPPA/GDPR-K)."""

import hashlib

import sqlalchemy as sa

from core.db import session_factory
from domains.consent.models import ParentalConsent
from tests.conftest import API, login, register_verified

PARENT = "parent@example.com"


async def _child_client(make_client, unique_email):
    client = await make_client()
    registered = await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)
    headers = {"Authorization": f"Bearer {access}"}
    response = await client.patch(
        f"{API}/profile/me", json={"ageGroup": "child"}, headers=headers
    )
    assert response.status_code == 200, response.text
    return client, headers, int(registered["id"])


async def test_child_consent_request_confirm_and_revoke(make_client, unique_email):
    client, headers, user_id = await _child_client(make_client, unique_email)

    response = await client.get(f"{API}/consent/status", headers=headers)
    assert response.status_code == 200
    assert response.json()["required"] is True
    assert response.json()["status"] == "none"

    response = await client.post(
        f"{API}/consent/request",
        json={"parentEmail": PARENT},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    requested = response.json()
    assert requested["status"] == "pending"
    assert requested["devToken"]
    assert "/consent?token=" in requested["confirmUrl"]

    # В БД только SHA-256, исходный токен не сохраняется.
    async with session_factory() as session:
        row = (
            await session.execute(
                sa.select(ParentalConsent).where(
                    ParentalConsent.user_id == user_id
                )
            )
        ).scalar_one()
        assert row.token_hash == hashlib.sha256(
            requested["devToken"].encode()
        ).hexdigest()
        assert row.token_hash != requested["devToken"]
        assert row.parent_email == PARENT

    response = await client.post(
        f"{API}/consent/confirm", json={"token": requested["devToken"]}
    )
    assert response.status_code == 200, response.text
    confirmed = response.json()
    assert confirmed["status"] == "granted"
    assert confirmed["confirmedAt"] is not None

    response = await client.get(f"{API}/consent/status", headers=headers)
    assert response.json()["status"] == "granted"

    response = await client.post(f"{API}/consent/revoke", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "revoked"
    assert response.json()["revokedAt"] is not None


async def test_adult_does_not_need_consent(make_client, unique_email):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)
    headers = {"Authorization": f"Bearer {access}"}
    await client.patch(f"{API}/profile/me", json={"ageGroup": "adult"}, headers=headers)

    status = (await client.get(f"{API}/consent/status", headers=headers)).json()
    assert status["required"] is False
    assert status["status"] == "not_required"

    response = await client.post(
        f"{API}/consent/request",
        json={"parentEmail": PARENT},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["code"] == "consent_not_required"


async def test_consent_token_single_use_and_invalid(make_client, unique_email):
    client, headers, _uid = await _child_client(make_client, unique_email)
    requested = (
        await client.post(
            f"{API}/consent/request",
            json={"parentEmail": PARENT},
            headers=headers,
        )
    ).json()
    token = requested["devToken"]

    first = await client.post(f"{API}/consent/confirm", json={"token": token})
    assert first.status_code == 200
    second = await client.post(f"{API}/consent/confirm", json={"token": token})
    assert second.status_code == 410
    assert second.json()["code"] == "consent_invalid_token"

    invalid = await client.post(
        f"{API}/consent/confirm", json={"token": "x" * 32}
    )
    assert invalid.status_code == 410


async def test_consent_status_isolated_per_user(make_client, unique_email):
    _client_a, headers_a, _uid_a = await _child_client(
        make_client, f"a-{unique_email}"
    )
    _client_b, headers_b, _uid_b = await _child_client(
        make_client, f"b-{unique_email}"
    )
    requested = (
        await _client_a.post(
            f"{API}/consent/request",
            json={"parentEmail": PARENT},
            headers=headers_a,
        )
    ).json()
    await _client_a.post(
        f"{API}/consent/confirm", json={"token": requested["devToken"]}
    )

    status_b = (await _client_b.get(f"{API}/consent/status", headers=headers_b)).json()
    assert status_b["status"] == "none"
    assert status_b["confirmedAt"] is None
