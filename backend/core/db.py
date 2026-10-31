from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import settings

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
