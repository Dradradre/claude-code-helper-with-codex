import asyncio
import time
from dataclasses import dataclass


@dataclass
class AgentResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_sec: float = 0.0
    spawned_session_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    parsed_response: dict | None = None
    error: str | None = None


async def run_agent(
    cmd: list[str],
    cwd: str = ".",
    stdin_payload: str | None = None,
    timeout_sec: int = 600,
    env: dict | None = None,
) -> AgentResult:
    start = time.monotonic()
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE if stdin_payload else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        stdin_bytes = stdin_payload.encode() if stdin_payload else None
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(stdin_bytes),
            timeout=timeout_sec,
        )

        duration = time.monotonic() - start
        return AgentResult(
            stdout=stdout_bytes.decode(errors="replace") if stdout_bytes else "",
            stderr=stderr_bytes.decode(errors="replace") if stderr_bytes else "",
            exit_code=process.returncode or 0,
            duration_sec=duration,
        )

    except TimeoutError:
        process.kill()
        await process.wait()
        return AgentResult(
            exit_code=-1,
            duration_sec=time.monotonic() - start,
            error=f"Timed out after {timeout_sec}s",
        )
    except Exception as e:
        return AgentResult(
            exit_code=-1,
            duration_sec=time.monotonic() - start,
            error=str(e),
        )
