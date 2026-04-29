from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from cchwc.config import Settings

# Module-level engine cache — one engine per DB path.
# NullPool: SQLite connections are opened/closed per-request, so no stale
# file handles remain after the server exits.
_engines: dict[str, AsyncEngine] = {}


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    if settings is None:
        settings = Settings()
    db_url = f"sqlite+aiosqlite:///{settings.db_path}"
    if db_url not in _engines:
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_async_engine(
            db_url,
            echo=False,
            connect_args={"timeout": 5, "check_same_thread": False},
            poolclass=NullPool,
        )

        from sqlalchemy import event

        @event.listens_for(engine.sync_engine, "connect")
        def _set_pragmas(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

        _engines[db_url] = engine
    return _engines[db_url]


def get_session_factory(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(settings), expire_on_commit=False)


async def dispose_engine(settings: Settings | None = None) -> None:
    """서버 종료 시 모든 커넥션을 명시적으로 닫습니다."""
    if settings is None:
        settings = Settings()
    db_url = f"sqlite+aiosqlite:///{settings.db_path}"
    engine = _engines.pop(db_url, None)
    if engine:
        await engine.dispose()
