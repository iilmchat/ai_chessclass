"""S-98: admin API legal hold + DSAR erase."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import select

from core.base import CamelModel
from core.errors import AppError
from domains.audit import service as audit_svc
from domains.auth.deps import DbSession, require_role
from domains.auth.models import User, UserRole
from domains.retention import service as retention_svc
from domains.retention.models import LegalHold

holds_router = APIRouter(prefix="/admin/legal-holds", tags=["retention"])
users_router = APIRouter(prefix="/admin/users", tags=["retention"])

AdminOnly = Annotated[User, Depends(require_role(UserRole.ADMIN))]


class LegalHoldIn(CamelModel):
    subject_type: str = Field(default="user", max_length=32)
    subject_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=2000)
    expires_at: datetime | None = None


class LegalHoldOut(CamelModel):
    id: str
    subject_type: str
    subject_id: str
    reason: str
    created_by: str | None
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    revoked_by: str | None


class EraseIn(CamelModel):
    reason: str = Field(min_length=1, max_length=2000)


class EraseOut(CamelModel):
    ok: bool = True
    erased: dict[str, int]


def _hold_out(row: LegalHold) -> LegalHoldOut:
    return LegalHoldOut(
        id=str(row.id),
        subject_type=row.subject_type,
        subject_id=row.subject_id,
        reason=row.reason,
        created_by=str(row.created_by) if row.created_by else None,
        created_at=row.created_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        revoked_by=str(row.revoked_by) if row.revoked_by else None,
    )


@holds_router.post("", response_model=LegalHoldOut, status_code=201)
async def create_legal_hold(
    body: LegalHoldIn,
    admin: AdminOnly,
    session: DbSession,
    request: Request,
) -> LegalHoldOut:
    hold = LegalHold(
        subject_type=body.subject_type.strip().lower(),
        subject_id=body.subject_id.strip(),
        reason=body.reason.strip(),
        created_by=admin.id,
        expires_at=body.expires_at,
    )
    session.add(hold)
    await session.flush()
    await audit_svc.record(
        session,
        admin,
        "legal_hold.create",
        target_type=hold.subject_type,
        target_id=hold.subject_id,
        meta={"reason": hold.reason, "expiresAt": str(hold.expires_at)},
        request=request,
    )
    await session.commit()
    return _hold_out(hold)


@holds_router.get("", response_model=list[LegalHoldOut])
async def list_legal_holds(
    admin: AdminOnly,
    session: DbSession,
    include_revoked: bool = False,
) -> list[LegalHoldOut]:
    _ = admin
    if include_revoked:
        rows = list(
            (
                await session.execute(
                    select(LegalHold).order_by(
                        LegalHold.created_at.desc(), LegalHold.id.desc()
                    )
                )
            ).scalars()
        )
    else:
        rows = await retention_svc.active_legal_holds(session)
    return [_hold_out(row) for row in rows]


@holds_router.delete("/{hold_id}", response_model=LegalHoldOut)
async def revoke_legal_hold(
    hold_id: int,
    admin: AdminOnly,
    session: DbSession,
    request: Request,
) -> LegalHoldOut:
    hold = await session.get(LegalHold, hold_id)
    if hold is None:
        raise AppError("legal_hold_not_found", "Legal hold не найден", 404)
    if hold.revoked_at is None:
        hold.revoked_at = datetime.now(UTC)
        hold.revoked_by = admin.id
        await audit_svc.record(
            session,
            admin,
            "legal_hold.revoke",
            target_type=hold.subject_type,
            target_id=hold.subject_id,
            meta={"holdId": str(hold.id)},
            request=request,
        )
        await session.commit()
    return _hold_out(hold)


@users_router.post("/{user_id}/erase", response_model=EraseOut)
async def erase_user(
    user_id: int,
    body: EraseIn,
    admin: AdminOnly,
    session: DbSession,
    request: Request,
) -> EraseOut:
    erased = await retention_svc.erase_user(
        session, user_id, reason=body.reason
    )
    await audit_svc.record(
        session,
        admin,
        "user.erased",
        target_type="user",
        target_id=user_id,
        source="api",
        meta={
            "reason": body.reason,
            "erasedAt": datetime.now(UTC).isoformat(),
            "tables": erased,
        },
        request=request,
    )
    await session.commit()
    return EraseOut(ok=True, erased=erased)
