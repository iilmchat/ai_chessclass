"""DTO домена profile: camelCase JSON (Design §12.1, SPEC.md §3.2)."""

from datetime import datetime
from typing import Any

from pydantic import Field

from core.base import CamelModel
from core.levels import Level
from domains.auth.models import UserRole
from domains.profile.models import AgeGroup, BillingTier


class ProfileOut(CamelModel):
    id: str  # user id
    email: str
    role: UserRole
    displayName: str | None
    # null возможен только у легаси-юзеров (до backfill 0003); для новых — всегда
    level: Level | None
    billingTier: BillingTier | None
    ageGroup: AgeGroup
    emailVerified: bool
    isActive: bool
    prefs: dict[str, Any]
    createdAt: datetime


class ProfileUpdateIn(CamelModel):
    """PATCH /profile/me: только свои данные. Level меняет admin (SPEC §3.2)."""

    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    prefs: dict[str, Any] | None = None
    age_group: AgeGroup | None = None


class LevelUpdateIn(CamelModel):
    level: Level


# пагинация — общий контракт: PageOut живёт в core.base (SPEC §1)
from core.base import PageOut as PageOut  # noqa: E402, F401
