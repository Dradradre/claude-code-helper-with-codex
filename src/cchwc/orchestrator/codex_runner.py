import json
import shutil
from collections.abc import Awaitable, Callable

from cchwc.orchestrator.runner import AgentResult, run_agent


def is_available() -> bool:
    return shutil.which("codex") is not None


async def run_codex_exec(
    prompt: str,
    cwd: str = ".",
    json_mode: bool = False,
    timeout_sec: int = 600,
    on_chunk: Callable[[str], Awaitable[None]] | None = None,
) -> AgentResult:
    cmd = ["codex", "exec", prompt]

    result = await run_agent(cmd, cwd=cwd, timeout_sec=timeout_sec, on_chunk=on_chunk)

    if result.error:
        return result

    if json_mode and result.stdout:
        try:
            parsed = json.loads(result.stdout)
            result.parsed_response = parsed
        except json.JSONDecodeError:
            pass

    if result.exit_code != 0 and not result.stdout and result.stderr:
        result.error = result.stderr[:500]

    return result
