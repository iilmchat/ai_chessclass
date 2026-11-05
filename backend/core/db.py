"""Подключение к PostgreSQL и контекст RLS-тенанта (S-72).

Политики RLS читают `app.current_user_id` / `app.current_user_role` и
фильтруют строки по владельцу-ученику и его классу (ADR-015, S-72).
Контекст ставится через `set_config(..., is_local=true)` в событии
`after_begin`: это эквивалент `SET LOCAL`, привязанный именно к тому
соединению из пула, которое выдано сессии. По завершении транзакции
PostgreSQL сам сбрасывает local-настройки, поэтому контекст не «протекает»
на следующий запрос или в соседнюю задачу.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Final

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from core.config import settings

#: Роли, которым разрешено попадать в контекст БД. `anonymous` — fail-closed:
#: RLS-таблицы не видны, пока middleware/воркер не установит принципала.
ALLOWED_DB_ROLES: Final[frozenset[str]] = frozenset(
    {"student", "teacher", "admin", "auditor", "anonymous"}
)

#: Непривилегированная роль БД: приложение переключается на неё в каждой
#: транзакции. Владелец схемы (POSTGRES_USER) — суперпользователь, а
#: суперпользователи обходят RLS даже при FORCE ROW LEVEL SECURITY.
RLS_APP_ROLE: Final[str] = "chess_app"

#: Контекст по умолчанию — fail-closed anonymous. HTTP-middleware выставляет
#: принципала запроса, а фоновые задачи/системные скрипты, которым нужен
#: доступ ко всем данным, проставляют admin явно через `db_context`.
_DEFAULT_CONTEXT = "anonymous"


@dataclass(frozen=True)
class DBContext:
    """Принципал, от имени которого выполняется текущая транзакция."""

    user_id: int | None = None
    role: str = _DEFAULT_CONTEXT


_db_context: ContextVar[DBContext | None] = ContextVar(
    "chessclass_db_context", default=None
)


def current_db_context() -> DBContext:
    """Текущий контекст БД (для тестов/диагностики)."""
    return _db_context.get() or DBContext()


def _make_context(user_id: int | None, role: str) -> DBContext:
    if role not in ALLOWED_DB_ROLES:
        raise ValueError(f"Недопустимая роль для RLS-контекста: {role!r}")
    if user_id is not None and (isinstance(user_id, bool) or user_id <= 0):
        raise ValueError(f"Недопустимый user_id для RLS-контекста: {user_id!r}")
    return DBContext(user_id=user_id, role=role)


def set_db_context(
    user_id: int | None, role: str
) -> Token[DBContext | None]:
    """Установить контекст без автоматического сброса (низкоуровневый API)."""
    return _db_context.set(_make_context(user_id, role))


def reset_db_context(token: Token[DBContext | None]) -> None:
    """Сбросить контекст, установленный через `set_db_context`."""
    _db_context.reset(token)


@asynccontextmanager
async def db_context(user_id: int | None, role: str) -> AsyncIterator[None]:
    """Временный контекст БД: HTTP-запрос, фоновая задача или тест."""
    token = set_db_context(user_id, role)
    try:
        yield
    finally:
        reset_db_context(token)


@event.listens_for(Session, "after_begin")
def _apply_rls_context(session: Session, transaction, connection) -> None:  # type: ignore[no-untyped-def]
    """Выполнить `SET LOCAL`-эквивалент на соединении начинающейся транзакции.

    `set_config(..., true)` — транзакционно-локальный вариант `SET LOCAL`.
    Параметры биндятся драйвером (без конкатенации SQL), значения приходят
    из проверенного `DBContext`. Событие срабатывает на каждой новой
    транзакции, поэтому смена контекста между запросами не оставляет
    «хвостов» на переиспользуемом соединении пула.
    """
    del session, transaction  # сигнатура события SQLAlchemy
    # SET LOCAL ROLE сбрасывается вместе с транзакцией: приложение не остаётся
    # суперпользователем на переиспользуемом соединении пула.
    connection.execute(text(f"SET LOCAL ROLE {RLS_APP_ROLE}"))
    ctx = _db_context.get() or DBContext()
    connection.execute(
        text(
            "SELECT set_config('app.current_user_id', :user_id, true), "
            "set_config('app.current_user_role', :role, true)"
        ),
        {
            "user_id": "" if ctx.user_id is None else str(ctx.user_id),
            "role": ctx.role,
        },
    )


is_prod = settings.app_env == "prod"

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    echo=settings.db_echo,
    # в prod миграции прогоняются на старте (guarded) — см. Design §15.3
)

session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI-зависимость: сессия на запрос. Роллбэк при исключении."""
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
