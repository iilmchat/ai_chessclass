"""S-31: GET /admin/llm/health — статус провайдера, слаги, FinOps-срез."""

import llm.router as llm_router
from llm.models_registry import MODELS
from tests.conftest import API, login, register_verified


class _FakeProvider:
    def __init__(self, models: list[str] | None) -> None:
        self._models = models
        self.base_url = "http://llm.test/v1"

    def is_configured(self) -> bool:
        return self._models is not None

    async def list_models(self) -> list[str]:
        assert self._models is not None
        return self._models


async def test_llm_health_echo_without_provider(admin_client, monkeypatch):
    monkeypatch.setattr(llm_router, "get_cloud_provider", lambda: _FakeProvider(None))

    response = await admin_client.get(f"{API}/admin/llm/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "echo"
    assert body["providerConfigured"] is False
    assert body["availableModels"] == []
    assert len(body["tiers"]) == len(MODELS)
    assert all(tier["available"] is None for tier in body["tiers"])
    assert body["missingModels"] == []
    assert body["lastCall"]["at"] is None or isinstance(body["lastCall"]["at"], str)
    assert body["today"]["tokensIn"] >= 0
    assert body["budgetFreeTokensDay"] > 0


async def test_llm_health_ok_when_all_slugs_available(admin_client, monkeypatch):
    models = [spec.slug for spec in MODELS.values() if spec.slug]
    monkeypatch.setattr(
        llm_router, "get_cloud_provider", lambda: _FakeProvider(models)
    )

    response = await admin_client.get(f"{API}/admin/llm/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["providerConfigured"] is True
    assert body["missingModels"] == []
    assert all(tier["available"] is True for tier in body["tiers"])
    assert body["availableModels"] == sorted(models)[:50]


async def test_llm_health_degraded_on_missing_slug(admin_client, monkeypatch):
    l1 = MODELS["L1"].slug
    monkeypatch.setattr(
        llm_router, "get_cloud_provider", lambda: _FakeProvider([l1])
    )

    response = await admin_client.get(f"{API}/admin/llm/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert l1 not in body["missingModels"]  # L1 доступен
    assert MODELS["L2"].slug in body["missingModels"]


async def test_llm_health_requires_admin(make_client, unique_email):
    client = await make_client()
    await register_verified(client, unique_email)
    _client, access, _uid = await login(client, unique_email)
    response = await client.get(
        f"{API}/admin/llm/health",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 403
