"""Async SQLAlchemy Engine/Session. Siehe docs/Datenmodell.md fuer das Schema."""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from homedms.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-Dependency: liefert eine DB-Session pro Request."""
    async with async_session_factory() as session:
        yield session
