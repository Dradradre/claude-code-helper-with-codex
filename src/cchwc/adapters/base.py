from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path

from cchwc.core.schemas import ParsedSession


class SessionAdapter(ABC):
    agent_type: str

    @abstractmethod
    def session_root(self) -> Path:
        ...

    @abstractmethod
    def discover_session_files(self) -> Iterator[Path]:
        ...

    @abstractmethod
    def parse_file(self, path: Path) -> ParsedSession | None:
        ...

    @abstractmethod
    def extract_cwd(self, path: Path) -> str | None:
        ...
