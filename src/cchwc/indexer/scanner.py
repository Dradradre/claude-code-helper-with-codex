import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from cchwc.adapters.base import SessionAdapter
from cchwc.indexer.parser import upsert_parsed_session

logger = logging.getLogger(__name__)


@dataclass
class ScanReport:
    total_files: int = 0
    parsed: int = 0
    skipped: int = 0
    errors: int = 0
    error_details: list[str] = field(default_factory=list)


async def initial_scan(
    adapter: SessionAdapter,
    db: AsyncSession,
    concurrency: int = 8,
) -> ScanReport:
    report = ScanReport()
    sem = asyncio.Semaphore(concurrency)
    files = list(adapter.discover_session_files())
    report.total_files = len(files)

    async def process_file(path: Path) -> None:
        async with sem:
            try:
                parsed = adapter.parse_file(path)
                if parsed is None:
                    report.skipped += 1
                    return
                await upsert_parsed_session(db, parsed)
                report.parsed += 1
            except Exception as e:
                report.errors += 1
                report.error_details.append(f"{path}: {e}")
                logger.warning("Failed to parse %s: %s", path, e)

    tasks = [process_file(f) for f in files]
    for task in tasks:
        await task

    await db.commit()
    return report
