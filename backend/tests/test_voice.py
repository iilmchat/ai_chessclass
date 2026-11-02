"""S-44: озвучка — кэш, квота и fallback без ключа."""

from pathlib import Path

import pytest
import sqlalchemy as sa

from core.config import settings
from core.db import session_factory
from domains.auth.models import User, UserRole
from domains.voice.models import VoiceAudio
from domains.voice.service import synthesize
from tests.conftest import API, login, make_direct_user


async def _user(unique_email: str) -> User:
    await make_direct_user(unique_email, UserRole.STUDENT)
    async with session_factory() as session:
        user = await session.get(User, int(
            (await session.execute(
                sa.select(User.id).where(User.email == unique_email)
            )).scalar_one()
        ))
        assert user is not None
        return user


async def test_voice_cache_and_quota(
    make_client, unique_email, redis_client, tmp_path, monkeypatch
):
    _ = make_client
    user = await _user(unique_email)
    monkeypatch.setattr(settings, "voice_api_key", "test-key")
    monkeypatch.setattr(settings, "voice_cache_dir", str(tmp_path))
    monkeypatch.setattr(settings, "voice_daily_chars", 1000)
    calls: list[str] = []

    async def fake_provider(text: str, voice: str, model: str) -> bytes:
        calls.append(text)
        return b"ID3-fake-audio"

    text = f"Озвучка для {unique_email}"
    async with session_factory() as session:
        audio, row, cached = await synthesize(
            session, redis_client, user, text, provider=fake_provider
        )
        assert audio == b"ID3-fake-audio"
        assert cached is False
        assert row.chars == len(text)
        assert Path(row.path).is_file()
        await session.commit()
        first_id = row.id

    async with session_factory() as session:
        audio, row, cached = await synthesize(
            session, redis_client, user, text, provider=fake_provider
        )
        assert audio == b"ID3-fake-audio"
        assert cached is True
        assert row.id == first_id
        assert len(calls) == 1
        await session.commit()

    # квота: новый текст не проходит дневной лимит
    monkeypatch.setattr(settings, "voice_daily_chars", 3)
    async with session_factory() as session:
        with pytest.raises(Exception) as exc_info:
            await synthesize(
                session, redis_client, user, "ещё текст", provider=fake_provider
            )
        assert getattr(exc_info.value, "code", "") == "voice_quota"

    # cleanup cache row
    async with session_factory() as session:
        await session.execute(
            sa.delete(VoiceAudio).where(VoiceAudio.id == first_id)
        )
        await session.commit()


async def test_voice_without_key_is_text_fallback(
    make_client, unique_email, redis_client, tmp_path, monkeypatch
):
    _ = make_client
    user = await _user(unique_email)
    monkeypatch.setattr(settings, "voice_api_key", "")
    monkeypatch.setattr(settings, "voice_cache_dir", str(tmp_path))
    async with session_factory() as session:
        with pytest.raises(Exception) as exc_info:
            await synthesize(session, redis_client, user, "текст без ключа")
        assert getattr(exc_info.value, "code", "") == "voice_unavailable"


async def test_voice_status_and_api_fallback(make_client, unique_email, monkeypatch):
    client = await make_client()
    await make_direct_user(unique_email, UserRole.STUDENT)
    _c, access, _uid = await login(client, unique_email)
    headers = {"Authorization": f"Bearer {access}"}
    monkeypatch.setattr(settings, "voice_api_key", "")
    response = await client.get(f"{API}/voice/status", headers=headers)
    assert response.status_code == 200
    assert response.json()["configured"] is False
    response = await client.post(
        f"{API}/voice/speak", json={"text": "привет"}, headers=headers
    )
    assert response.status_code == 503
    assert response.json()["code"] == "voice_unavailable"
