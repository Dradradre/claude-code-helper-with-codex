from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable


class OrchestrationMode(ABC):
    name: str

    def _agent_failure(self, agent: str, result) -> str | None:
        if result.error:
            return result.error
        if result.exit_code != 0:
            detail = (result.stderr or result.stdout or "").strip()
            if detail:
                return detail[:800]
            command = " ".join(result.command or [])
            if command:
                return f"{agent} exited with code {result.exit_code}: {command}"
            return f"{agent} exited with code {result.exit_code}"
        if not (result.stdout or "").strip():
            return f"{agent} produced no output"
        return None

    def _budget_message(self, total_tokens: int, total_cost_usd: float, config: dict) -> str | None:
        max_tokens = _as_int(config.get("max_total_tokens"), 0)
        max_cost = _as_float(config.get("max_cost_usd"), 0.0)
        if max_tokens > 0 and total_tokens >= max_tokens:
            return f"Token budget reached ({total_tokens:,}/{max_tokens:,})"
        if max_cost > 0 and total_cost_usd >= max_cost:
            return f"Cost budget reached (${total_cost_usd:.4f}/${max_cost:.4f})"
        return None

    def _agent_model(self, agent: str, config: dict) -> str | None:
        value = config.get(f"{agent}_model")
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value or None

    def _agent_effort(self, agent: str, config: dict) -> str | None:
        key = "codex_reasoning_effort" if agent == "codex" else f"{agent}_effort"
        value = config.get(key)
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value or None

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


def _as_int(value, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _as_float(value, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback
