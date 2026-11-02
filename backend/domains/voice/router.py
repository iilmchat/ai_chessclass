"""Роутер /api/v1/voice (S-44): ElevenLabs TTS с кэшем и fallback."""

from fastapi import APIRouter, Request, Response
from pydantic import Field

from core.base import CamelModel
from domains.auth.deps import CurrentUser, DbSession
from domains.voice import service as svc

router = APIRouter(prefix="/voice", tags=["voice"])


class SpeakIn(CamelModel):
    text: str = Field(min_length=1, max_length=2000)
    voice_id: str | None = Field(default=None, max_length=64)


class VoiceStatusOut(CamelModel):
    configured: bool
    provider: str
    model_id: str
    voice_id: str


@router.get("/status", response_model=VoiceStatusOut)
async def voice_status(_user: CurrentUser) -> VoiceStatusOut:
    return VoiceStatusOut(**svc.status())


@router.post("/speak")
async def speak(
    body: SpeakIn,
    user: CurrentUser,
    session: DbSession,
    request: Request,
) -> Response:
    audio, row, cached = await svc.synthesize(
        session,
        request.app.state.redis,
        user,
        body.text,
        voice_id=body.voice_id,
    )
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={
            "X-Voice-Cached": "1" if cached else "0",
            "X-Voice-Chars": str(row.chars),
            "X-Voice-Id": str(row.id),
        },
    )
