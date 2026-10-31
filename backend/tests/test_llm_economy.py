"""Экономика (DoD S-05): llm_calls заполняется; квота/бюджет режет выдачу;
downgrade до L1; judge — zero-квота; fallback на local; FinOps-эндпоинт."""

from datetime import UTC, datetime

import httpx
import sqlalchemy as sa

from core.config import settings
from core.db import session_factory
from core.levels import Level
from core.security import hash_password
from domains.auth.models import User, UserRole
from domains.profile.models import BillingTier, UserProfile
from llm import economy
from llm.base import LLMMessage
from llm.client import OpenAICompatProvider
from llm.gateway import LLMCallContext, llm_generate
from llm.models import LLMCall, UsageDaily
from tests.conftest import API, PASSWORD, login, register_verified


def _ok_provider(calls: list[str], content: str = "Готово.") -> OpenAICompatProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.read().decode())
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
            request=httpx.Request("POST", "http://llm.test/chat/completions"),
        )

    return OpenAICompatProvider(
        base_url="http://llm.test/v1",
        api_key="k",
        transport=httpx.MockTransport(handler),
    )


def _failing_provider(calls: list[str]) -> OpenAICompatProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.read().decode())
        return httpx.Response(500, request=request)

    return OpenAICompatProvider(
        base_url="http://llm.test/v1",
        api_key="k",
        transport=httpx.MockTransport(handler),
    )


async def _make_user(email: str, billing: BillingTier = BillingTier.FREE) -> int:
    async with session_factory() as session:
        user = User(
            email=email,
            password_hash=hash_password(PASSWORD),
            role=UserRole.STUDENT,
            email_verified_at=datetime.now(UTC),
        )
        session.add(user)
        await session.flush()
        session.add(UserProfile(user_id=user.id, level=Level.NOVICE, billing_tier=billing))
        await session.commit()
        return int(user.id)


async def test_call_recorded_quota_and_daily(redis_client, unique_email):
    user_id = await _make_user(unique_email)
    provider = _ok_provider([])
    async with session_factory() as session:
        result = await llm_generate(
            session,
            redis_client,
            route="python_teacher.comment",
            level=Level.NOVICE,
            messages=[LLMMessage(role="user", content="Проверь код")],
            ctx=LLMCallContext(user_id=user_id, billing_tier="free"),
            provider=provider,
        )
        assert result.status == "ok" and result.model_used == settings.llm_model_l1
        # llm_calls: tokens, ₽ (Numeric), latency
        row = (
            await session.execute(
                sa.select(LLMCall).where(LLMCall.user_id == user_id)
            )
        ).scalar_one()
        assert row.status == "ok"
        assert row.model_requested == settings.llm_model_l1
        assert row.model_used == settings.llm_model_l1
        assert row.tokens_in == 10 and row.tokens_out == 5
        assert row.cost_in is not None and row.cost_out is not None
        assert row.cost_in > 0 and row.cost_out > 0
        assert row.latency_ms >= 0
        # usage_daily агрегат
        daily = (
            await session.execute(
                sa.select(UsageDaily).where(UsageDaily.user_id == user_id)
            )
        ).scalar_one()
        assert daily.tokens_in == 10 and daily.tokens_out == 5
        assert daily.cost_total > 0
        await session.commit()
    # квота дня в Redis = сумма токенов
    assert int(await redis_client.get(economy.quota_key(user_id))) == 15


async def test_quota_exhausted_cuts_to_echo(redis_client, unique_email):
    user_id = await _make_user(unique_email)
    await economy.set_quota_for_tests(redis_client, user_id, 50_000)  # free-бюджет исчерпан
    calls: list[str] = []
    provider = _failing_provider(calls)  # облако не должно вызываться вовсе
    async with session_factory() as session:
        result = await llm_generate(
            session,
            redis_client,
            route="python_teacher.comment",
            level=Level.NOVICE,
            messages=[LLMMessage(role="user", content="Проверь код")],
            ctx=LLMCallContext(user_id=user_id, billing_tier="free"),
            provider=provider,
        )
        assert result.status == "echo"
        assert result.fallback_from == "quota_exhausted"
        assert "[echo]" in result.text
        assert calls == []  # облако не трогали
        row = (
            await session.execute(
                sa.select(LLMCall).where(LLMCall.user_id == user_id)
            )
        ).scalar_one()
        assert row.status == "echo" and row.model_used == "echo"
        assert row.tokens_in == 0 and row.tokens_out == 0
        # usage_daily для echo не создаётся
        daily = (
            await session.execute(
                sa.select(UsageDaily).where(UsageDaily.user_id == user_id)
            )
        ).scalar_one_or_none()
        assert daily is None


async def test_downgrade_to_l1_near_budget(redis_client, unique_email):
    user_id = await _make_user(unique_email)
    # остаток 100 токенов; сообщение ~ (408//4+16) ≈ 118 → не влезает в L2
    await economy.set_quota_for_tests(redis_client, user_id, 49_900)
    big_text = "x" * 408
    calls: list[str] = []
    provider = _ok_provider(calls)
    async with session_factory() as session:
        result = await llm_generate(
            session,
            redis_client,
            route="chess_lab.insight",  # L2
            level=Level.INTERMEDIATE,
            messages=[LLMMessage(role="user", content=big_text)],
            ctx=LLMCallContext(user_id=user_id, billing_tier="free"),
            provider=provider,
        )
        assert result.tier == "L1"  # downgrade
        assert result.model_requested == settings.llm_model_l2
        assert result.model_used == settings.llm_model_l1
        assert result.fallback_from == "quota_downgrade:L2"
        # облако вызывали с L1-слагом
        assert calls and settings.llm_model_l1 in calls[0]
        row = (
            await session.execute(
                sa.select(LLMCall).where(LLMCall.user_id == user_id)
            )
        ).scalar_one()
        assert row.model_requested == settings.llm_model_l2
        assert row.model_used == settings.llm_model_l1


async def test_judge_route_ignores_quota(redis_client, unique_email):
    user_id = await _make_user(unique_email)
    await economy.set_quota_for_tests(redis_client, user_id, 50_000)  # исчерпан
    calls: list[str] = []
    provider = _ok_provider(calls)
    async with session_factory() as session:
        result = await llm_generate(
            session,
            redis_client,
            route="anticheat.judge_explain",  # zero-квота (Design §8.5)
            level=Level.NOVICE,
            messages=[LLMMessage(role="user", content="Объясни код")],
            ctx=LLMCallContext(user_id=user_id, billing_tier="free"),
            provider=provider,
        )
        assert result.status == "ok"
        assert result.tier == "judge"
        assert result.model_used == settings.llm_model_judge
        assert calls and settings.llm_model_judge in calls[0]
        row = (
            await session.execute(
                sa.select(LLMCall).where(LLMCall.user_id == user_id)
            )
        ).scalar_one()
        assert row.status == "ok"


async def test_fallback_to_local_lmstudio(redis_client, unique_email, monkeypatch):
    monkeypatch.setattr(settings, "llm_local_fallback", True)
    user_id = await _make_user(unique_email)
    cloud_calls: list[str] = []
    failing_cloud = _failing_provider(cloud_calls)
    local_calls: list[str] = []
    local_provider = _ok_provider(local_calls)

    async with session_factory() as session:
        result = await llm_generate(
            session,
            redis_client,
            route="python_teacher.comment",
            level=Level.NOVICE,
            messages=[LLMMessage(role="user", content="Проверь код")],
            ctx=LLMCallContext(user_id=user_id, billing_tier="free"),
            provider=failing_cloud,
            local_provider=local_provider,
        )
        assert result.status == "ok"
        assert result.model_used == "lmstudio"
        assert result.fallback_from == settings.llm_model_l1
        assert cloud_calls and local_calls  # сначала облако (упало), потом local
        row = (
            await session.execute(
                sa.select(LLMCall).where(LLMCall.user_id == user_id)
            )
        ).scalar_one()
        assert row.model_used == "lmstudio"
        assert row.fallback_from == settings.llm_model_l1


async def test_finops_usage_endpoint(admin_client, make_client, unique_email, redis_client):
    _ = admin_client
    client = await make_client()
    registered = await register_verified(client, unique_email)
    user_id = int(registered["id"])
    provider = _ok_provider([])
    async with session_factory() as session:
        await llm_generate(
            session,
            redis_client,
            route="reports.parent_summary",
            level=Level.NOVICE,
            messages=[LLMMessage(role="user", content="Отчёт")],
            ctx=LLMCallContext(user_id=user_id, billing_tier="free"),
            provider=provider,
        )
        await session.commit()

    response = await admin_client.get(f"{API}/admin/finops/usage", params={"days": 7})
    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "RUB"
    assert body["days"], "ожидаем хотя бы один день с расходом"
    today = body["days"][0]
    assert today["tokensIn"] >= 10 and today["tokensOut"] >= 5
    assert float(today["costTotal"]) > 0

    # student → 403
    _c, student_access, _uid = await login(client, unique_email)
    response = await client.get(
        f"{API}/admin/finops/usage",
        headers={"Authorization": f"Bearer {student_access}"},
    )
    assert response.status_code == 403
