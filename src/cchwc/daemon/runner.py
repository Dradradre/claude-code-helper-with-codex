import asyncio
import logging

from cchwc.adapters.claude_adapter import ClaudeAdapter
from cchwc.adapters.codex_adapter import CodexAdapter
from cchwc.config import Settings
from cchwc.core.db import get_engine, get_session_factory
from cchwc.core.models import Base
from cchwc.indexer.scanner import initial_scan
from cchwc.indexer.watcher import SessionWatcher

logger = logging.getLogger(__name__)


async def run_daemon(settings: Settings | None = None, foreground: bool = True) -> None:
    if settings is None:
        settings = Settings()

    engine = get_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = get_session_factory(settings)
    adapters = [
        ClaudeAdapter(settings.claude_root),
        CodexAdapter(settings.codex_root),
    ]

    logger.info("Running initial scan...")
    async with session_factory() as db:
        for adapter in adapters:
            report = await initial_scan(adapter, db, settings.scan_concurrency)
            logger.info(
                "%s scan: %d files, %d parsed, %d skipped, %d errors",
                adapter.agent_type,
                report.total_files,
                report.parsed,
                report.skipped,
                report.errors,
            )

    watcher = SessionWatcher(adapters, settings.watch_debounce_ms)
    watcher.start()
    logger.info("Watching for session changes...")

    try:
        await watcher.consume_loop(session_factory)
    except asyncio.CancelledError:
        pass
    finally:
        watcher.stop()
        logger.info("Daemon stopped.")
