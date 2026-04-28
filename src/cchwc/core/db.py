from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cchwc.config import Settings


def get_engine(settings: Settings | None = None):
    if settings is None:
        settings = Settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_async_engine(
        f"sqlite+aiosqlite:///{settings.db_path}",
        echo=False,
        connect_args={"timeout": 5},
    )


def get_session_factory(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    engine = get_engine(settings)
    return async_sessionmaker(engine, expire_on_commit=False)
