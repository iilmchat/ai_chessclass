"""Реестр ORM-моделей для alembic env.py — импорт всех доменов.

Новый домен с моделями → добавить импорт сюда (один факт — одно место).
"""

from db.base import Base
from domains.auth import models as _auth_models  # noqa: F401
from domains.cognitive import models as _cognitive_models  # noqa: F401
from domains.profile import models as _profile_models  # noqa: F401

target_metadata = Base.metadata
