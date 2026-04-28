from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from cchwc.config import Settings
from cchwc.core.db import get_session_factory

_settings = Settings()
_session_factory = get_session_factory(_settings)


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with _session_factory() as session:
        yield session


def get_settings() -> Settings:
    return _settings
