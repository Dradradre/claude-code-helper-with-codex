import asyncio
import logging
from pathlib import Path

from watchdog.events import FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from cchwc.adapters.base import SessionAdapter
from cchwc.indexer.parser import upsert_parsed_session

logger = logging.getLogger(__name__)


class _Handler(FileSystemEventHandler):
    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        self._queue = queue
        self._loop = loop

    def on_modified(self, event):
        if isinstance(event, FileModifiedEvent) and event.src_path.endswith(".jsonl"):
            self._loop.call_soon_threadsafe(self._queue.put_nowait, Path(event.src_path))

    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(".jsonl"):
            self._loop.call_soon_threadsafe(self._queue.put_nowait, Path(event.src_path))


class SessionWatcher:
    def __init__(self, adapters: list[SessionAdapter], debounce_ms: int = 100):
        self._adapters = adapters
        self._debounce = debounce_ms / 1000.0
        self._queue: asyncio.Queue[Path] = asyncio.Queue()
        self._observer = Observer()
        self._adapter_map: dict[str, SessionAdapter] = {}

    def start(self) -> None:
        loop = asyncio.get_event_loop()
        handler = _Handler(self._queue, loop)
        for adapter in self._adapters:
            root = adapter.session_root()
            if root.exists():
                self._observer.schedule(handler, str(root), recursive=True)
            for p in adapter.discover_session_files():
                self._adapter_map[str(p)] = adapter
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join()

    def _find_adapter(self, path: Path) -> SessionAdapter | None:
        if str(path) in self._adapter_map:
            return self._adapter_map[str(path)]
        for adapter in self._adapters:
            try:
                path.relative_to(adapter.session_root())
                self._adapter_map[str(path)] = adapter
                return adapter
            except ValueError:
                continue
        return None

    async def consume_loop(self, session_factory) -> None:
        pending: dict[str, float] = {}
        while True:
            try:
                path = await asyncio.wait_for(self._queue.get(), timeout=self._debounce)
                pending[str(path)] = asyncio.get_event_loop().time()
            except TimeoutError:
                pass

            now = asyncio.get_event_loop().time()
            ready = [p for p, t in pending.items() if now - t >= self._debounce]

            for path_str in ready:
                del pending[path_str]
                path = Path(path_str)
                adapter = self._find_adapter(path)
                if adapter is None:
                    continue
                try:
                    parsed = adapter.parse_file(path)
                    if parsed:
                        async with session_factory() as db:
                            await upsert_parsed_session(db, parsed)
                            await db.commit()
                        logger.info("Indexed: %s", path.name)
                except Exception:
                    logger.exception("Watch handler failed: %s", path)
