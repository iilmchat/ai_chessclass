"""Реестр ORM-моделей для alembic env.py — импорт всех доменов.

Новый домен с моделями → добавить импорт сюда (один факт — одно место).
"""

from db.base import Base
from domains.anticheat import models as _anticheat_models  # noqa: F401
from domains.audit import models as _audit_models  # noqa: F401
from domains.auth import models as _auth_models  # noqa: F401
from domains.bot_lab import models as _bot_models  # noqa: F401
from domains.chess_lab import models as _chess_models  # noqa: F401
from domains.classes import models as _classes_models  # noqa: F401
from domains.cognitive import models as _cognitive_models  # noqa: F401
from domains.profile import models as _profile_models  # noqa: F401
from domains.progress import models as _progress_models  # noqa: F401
from domains.python_teacher import models as _py_models  # noqa: F401
from domains.reports import models as _reports_models  # noqa: F401
from domains.studies import models as _studies_models  # noqa: F401
from domains.voice import models as _voice_models  # noqa: F401
from llm import models as _llm_models  # noqa: F401
from rag import models as _rag_models  # noqa: F401

target_metadata = Base.metadata
