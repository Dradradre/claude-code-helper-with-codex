import asyncio
import platform
import shutil
import time
from dataclasses import dataclass
from pathlib import Path


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


def _resolve_cmd(cmd: list[str]) -> list[str]:
    """Windows에서 .CMD/.BAT 파일은 cmd /c로 감싸야 실행 가능."""
    if platform.system() != "Windows":
        return cmd
    exe = shutil.which(cmd[0])
    if exe and Path(exe).suffix.lower() in {".cmd", ".bat"}:
        return ["cmd", "/c", *cmd]
    return cmd


async def run_agent(
    cmd: list[str],
    cwd: str = ".",
    stdin_payload: str | None = None,
    timeout_sec: int = 600,
    env: dict | None = None,
) -> AgentResult:
    start = time.monotonic()
    resolved = _resolve_cmd(cmd)
    try:
        process = await asyncio.create_subprocess_exec(
            *resolved,
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
