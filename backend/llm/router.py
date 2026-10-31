"""API /api/v1/admin/models (Design §12.2): модели/цены readonly для admin."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends

from core.base import CamelModel
from domains.auth.deps import DbSession, require_role
from domains.auth.models import User, UserRole
from llm.client import OpenAICompatProvider
from llm.models_registry import MODELS

router = APIRouter(prefix="/admin", tags=["llm"])

AdminOnly = Annotated[User, Depends(require_role(UserRole.ADMIN))]


class ModelOut(CamelModel):
    tier: str
    slug: str
    display: str
    role: str
    configured: bool
    priceIn: str | None  # ₽/1M — Numeric(12,4), JSON — строка (JS-safe)
    priceOut: str | None


class ModelsOut(CamelModel):
    providerConfigured: bool
    currency: str
    models: list[ModelOut]


@router.get("/models", summary="Реестр моделей шлюза и цены (Design §8.3, admin)")
async def list_models(_guard: AdminOnly, session: DbSession) -> ModelsOut:
    _ = session  # сессия не нужна, зависимость для единообразия DI
    provider = OpenAICompatProvider()
    items = [
        ModelOut(
            tier=spec.tier,
            slug=spec.slug,
            display=spec.display,
            role=spec.role,
            configured=bool(spec.slug),
            priceIn=_fmt(spec.price_in),
            priceOut=_fmt(spec.price_out),
        )
        for spec in MODELS.values()
    ]
    return ModelsOut(
        providerConfigured=provider.is_configured(),
        currency="RUB",
        models=items,
    )


def _fmt(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.4f}"
