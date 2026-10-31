"""Реестр ORM-моделей для alembic env.py — импорт всех доменов.

Новый домен с моделями → добавить импорт сюда (один факт — одно место).
"""

from db.base import Base
from domains.auth import models as _auth_models  # noqa: F401

target_metadata = Base.metadata
