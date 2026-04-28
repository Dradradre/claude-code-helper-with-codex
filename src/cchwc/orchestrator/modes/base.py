from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable


class OrchestrationMode(ABC):
    name: str

    @abstractmethod
    async def execute(
        self,
        prompt: str,
        cwd: str,
        config: dict,
        run_id: int,
        emit: Callable[[str], Awaitable[None]],
    ) -> dict:
        ...
