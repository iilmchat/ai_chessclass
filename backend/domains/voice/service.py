"""S-44: озвучка ElevenLabs с кэшем, квотой и graceful fallback."""

import hashlib
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.errors import AppError
from domains.audit import service as audit_svc
from domains.auth.models import User
from domains.voice.models import VoiceAudio
from domains.voice.usage import VoiceUsage

logger = logging.getLogger(__name__)

MAX_TEXT_CHARS = 2000
FALLBACK_HEADERS = {"X-Voice-Fallback": "text"}
ProviderFn = Callable[[str, str, str], Awaitable[bytes]]


def _hash(text: str, voice_id: str, model_id: str) -> str:
    return hashlib.sha256(
        f"{voice_id}|{model_id}|{text}".encode()
    ).hexdigest()


async def _fetch_audio(text: str, voice_id: str, model_id: str) -> bytes:
    """ElevenLabs TTS; ключ не логируется."""
    if not settings.voice_api_key:
        raise AppError(
            "voice_unavailable",
            "Озвучка не настроена: VOICE_API_KEY пуст",
            503,
            headers=FALLBACK_HEADERS,
        )
    url = f"{settings.voice_base_url.rstrip('/')}/v1/text-to-speech/{voice_id}"
    headers = {"xi-api-key": settings.voice_api_key}
    from core.egress import hostname_of, make_egress_hook

    async with httpx.AsyncClient(
        timeout=settings.voice_timeout_s,
        event_hooks={
            # S-61: egress allowlist (voice_base_url разрешён как настроенный)
            "request": [make_egress_hook(hostname_of(settings.voice_base_url) or "")]
        },
    ) as client:
        response = await client.post(
            url,
            headers=headers,
            json={"text": text, "model_id": model_id},
        )
    if response.status_code == 429:
        logger.warning("voice: ElevenLabs quota 429")
        raise AppError(
            "voice_quota",
            "Провайдер озвучки исчерпал квоту; используйте текст",
            429,
            headers=FALLBACK_HEADERS,
        )
    if response.status_code >= 400:
        logger.warning("voice: ElevenLabs HTTP %s", response.status_code)
        raise AppError(
            "voice_provider_error",
            "Провайдер озвучки вернул ошибку; используйте текст",
            502,
            headers=FALLBACK_HEADERS,
        )
    return response.content


async def _quota(
    redis, user: User, chars: int
) -> None:
    """Проверить/учесть дневную квоту символов (Redis)."""
    if redis is None:
        return
    key = f"voice:chars:{user.id}:{datetime.now(UTC).date().isoformat()}"
    used = int(await redis.get(key) or 0)
    if used + chars > settings.voice_daily_chars:
        raise AppError(
            "voice_quota",
            f"Дневной лимит озвучки: {settings.voice_daily_chars} символов",
            429,
            headers=FALLBACK_HEADERS,
        )
    await redis.incrby(key, chars)
    await redis.expire(key, 2 * 24 * 3600)


async def synthesize(
    session: AsyncSession,
    redis,
    user: User,
    text: str,
    *,
    voice_id: str | None = None,
    provider: ProviderFn | None = None,
) -> tuple[bytes, VoiceAudio, bool]:
    """Вернуть (audio, metadata, cached); кэш — по voice+model+text."""
    clean = text.strip()
    if not clean:
        raise AppError("voice_text_empty", "Текст для озвучки пуст", 422)
    if len(clean) > MAX_TEXT_CHARS:
        raise AppError(
            "voice_text_too_long",
            f"Текст для озвучки > {MAX_TEXT_CHARS} символов",
            422,
        )
    voice = voice_id or settings.voice_id
    model = settings.voice_model_id
    digest = _hash(clean, voice, model)

    cached = (
        await session.execute(
            select(VoiceAudio).where(VoiceAudio.text_hash == digest)
        )
    ).scalar_one_or_none()
    if cached is not None:
        path = Path(cached.path)
        if path.is_file():
            session.add(
                VoiceUsage(
                    user_id=user.id,
                    chars=len(clean),
                    cost=Decimal("0"),
                    cached=True,
                )
            )
            await session.flush()
            await audit_svc.record(
                session,
                user,
                "voice.speak",
                target_type="voice",
                target_id=cached.id,
                meta={"chars": cached.chars, "cached": True},
            )
            return path.read_bytes(), cached, True

    await _quota(redis, user, len(clean))
    fetcher = provider or _fetch_audio
    try:
        audio = await fetcher(clean, voice, model)
    except Exception:
        if redis is not None:
            key = f"voice:chars:{user.id}:{datetime.now(UTC).date().isoformat()}"
            await redis.decrby(key, len(clean))
        raise
    if not audio:
        raise AppError(
            "voice_provider_error",
            "Пустой ответ озвучки; используйте текст",
            502,
            headers=FALLBACK_HEADERS,
        )

    cache_dir = Path(settings.voice_cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{digest}.mp3"
    path.write_bytes(audio)
    cost = (
        Decimal(str(len(clean))) / Decimal("1000")
        * Decimal(str(settings.voice_cost_per_1k_rub))
    )
    row: VoiceAudio
    if cached is not None:
        cached.path = str(path)
        cached.chars = len(clean)
        cached.cost = cost
        row = cached
    else:
        row = VoiceAudio(
            text_hash=digest,
            voice_id=voice,
            model_id=model,
            path=str(path),
            chars=len(clean),
            cost=cost,
            provider="elevenlabs",
        )
        session.add(row)
    await session.flush()
    session.add(
        VoiceUsage(
            user_id=user.id,
            chars=len(clean),
            cost=cost,
            cached=False,
        )
    )
    await session.flush()
    await audit_svc.record(
        session,
        user,
        "voice.speak",
        target_type="voice",
        target_id=row.id,
        meta={"chars": len(clean), "cached": False},
    )
    return audio, row, False


def status() -> dict:
    return {
        "configured": bool(settings.voice_api_key),
        "provider": "elevenlabs",
        "modelId": settings.voice_model_id,
        "voiceId": settings.voice_id,
    }
