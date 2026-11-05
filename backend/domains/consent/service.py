"""Родительское согласие (S-74, ADR-019).

Минор (age_group child/teen) запрашивает согласие, родитель получает
одноразовую ссылку (7 дней), подтверждает её, после чего статус `granted`.
Токен в БД — только SHA-256; согласие можно отозвать, история сохраняется.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.errors import AppError
from domains.consent.models import ConsentStatus, ParentalConsent
from domains.profile.models import AgeGroup, UserProfile

REQUIRED_AGE_GROUPS = frozenset({AgeGroup.CHILD, AgeGroup.TEEN})


@dataclass(frozen=True, slots=True)
class ConsentState:
    required: bool
    status: str
    policy_version: str
    parent_email: str | None
    requested_at: datetime | None
    confirmed_at: datetime | None
    revoked_at: datetime | None
    expires_at: datetime | None


def _now() -> datetime:
    return datetime.now(UTC)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def consent_required(age_group: AgeGroup | None) -> bool:
    return age_group in REQUIRED_AGE_GROUPS


async def processing_allowed(session: AsyncSession, user_id: int) -> bool:
    """True для adult/unknown или для child/teen с действующим `granted`."""
    state = await get_state(session, user_id)
    return not state.required or state.status == ConsentStatus.GRANTED.value


async def ensure_processing_allowed(session: AsyncSession, user_id: int) -> None:
    """S-75: 403, если ребёнок/подросток без подтверждённого согласия."""
    if not await processing_allowed(session, user_id):
        raise AppError(
            "parental_consent_required",
            "Для обработки данных ребёнка нужно согласие родителя "
            "(раздел «Согласие»)",
            403,
        )


async def _latest(
    session: AsyncSession, user_id: int
) -> ParentalConsent | None:
    return (
        await session.execute(
            select(ParentalConsent)
            .where(ParentalConsent.user_id == user_id)
            .order_by(ParentalConsent.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def get_state(session: AsyncSession, user_id: int) -> ConsentState:
    profile = await session.get(UserProfile, user_id)
    required = consent_required(profile.age_group if profile else None)
    row = await _latest(session, user_id)
    version = settings.parental_consent_policy_version

    if not required:
        return ConsentState(
            required=False,
            status="not_required",
            policy_version=version,
            parent_email=None,
            requested_at=None,
            confirmed_at=None,
            revoked_at=None,
            expires_at=None,
        )

    if row is None:
        status = "none"
    elif row.status is ConsentStatus.PENDING and row.expires_at < _now():
        status = ConsentStatus.EXPIRED.value
    else:
        status = row.status.value

    return ConsentState(
        required=True,
        status=status,
        policy_version=row.policy_version if row else version,
        parent_email=row.parent_email if row else None,
        requested_at=row.requested_at if row else None,
        confirmed_at=row.confirmed_at if row else None,
        revoked_at=row.revoked_at if row else None,
        expires_at=row.expires_at if row else None,
    )


async def request_consent(
    session: AsyncSession, user_id: int, parent_email: str
) -> tuple[ParentalConsent, str]:
    """Создать pending-согласие и вернуть (row, raw token)."""
    state = await get_state(session, user_id)
    if not state.required:
        raise AppError(
            "consent_not_required",
            "Возрастная группа не требует родительского согласия",
            409,
        )

    now = _now()
    # Старые pending-ссылки становятся недействительными.
    old_rows = (
        await session.execute(
            select(ParentalConsent).where(
                ParentalConsent.user_id == user_id,
                ParentalConsent.status == ConsentStatus.PENDING,
            )
        )
    ).scalars()
    for old in old_rows:
        old.status = ConsentStatus.EXPIRED
        old.expires_at = now

    raw = secrets.token_urlsafe(32)
    row = ParentalConsent(
        user_id=user_id,
        token_hash=_hash_token(raw),
        parent_email=parent_email.strip().lower(),
        policy_version=settings.parental_consent_policy_version,
        status=ConsentStatus.PENDING,
        expires_at=now + timedelta(days=settings.parental_consent_ttl_days),
    )
    session.add(row)
    await session.flush()
    return row, raw


async def confirm_consent(session: AsyncSession, raw_token: str) -> ParentalConsent:
    row = (
        await session.execute(
            select(ParentalConsent).where(
                ParentalConsent.token_hash == _hash_token(raw_token),
                ParentalConsent.status == ConsentStatus.PENDING,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise AppError(
            "consent_invalid_token",
            "Ссылка согласия недействительна или уже использована",
            410,
        )
    now = _now()
    if row.expires_at < now:
        raise AppError("consent_expired", "Срок действия ссылки истёк", 410)
    row.status = ConsentStatus.GRANTED
    row.confirmed_at = now
    await session.flush()
    return row


async def revoke_consent(session: AsyncSession, user_id: int) -> ConsentState:
    now = _now()
    rows = (
        await session.execute(
            select(ParentalConsent).where(
                ParentalConsent.user_id == user_id,
                ParentalConsent.status.in_(
                    (ConsentStatus.PENDING, ConsentStatus.GRANTED)
                ),
            )
        )
    ).scalars()
    for row in rows:
        row.status = ConsentStatus.REVOKED
        row.revoked_at = now
    await session.flush()
    return await get_state(session, user_id)


def confirm_url(raw_token: str) -> str:
    return f"{settings.web_base_url}/consent?token={raw_token}"
