"""Реестр ORM-моделей для alembic env.py — импорт всех доменов.

Новый домен с моделями → добавить импорт сюда (один факт — одно место).
"""

from db.base import Base
from domains.anticheat import models as _anticheat_models  # noqa: F401
from domains.auth import models as _auth_models  # noqa: F401
from domains.cognitive import models as _cognitive_models  # noqa: F401
from domains.profile import models as _profile_models  # noqa: F401
from domains.python_teacher import models as _py_models  # noqa: F401
from llm import models as _llm_models  # noqa: F401

target_metadata = Base.metadata
