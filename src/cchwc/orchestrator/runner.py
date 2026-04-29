import asyncio
import platform
import shutil
import time
from collections.abc import Awaitable, Callable
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
    on_chunk: Callable[[str], Awaitable[None]] | None = None,
) -> AgentResult:
    start = time.monotonic()
    resolved = _resolve_cmd(cmd)
    try:
        process = await asyncio.create_subprocess_exec(
            *resolved,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE if stdin_payload else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        if stdin_payload:
            process.stdin.write(stdin_payload.encode())
            await process.stdin.drain()
            process.stdin.close()

        stdout_parts: list[str] = []
        stderr_parts: list[str] = []

        async def _drain_stdout() -> None:
            while True:
                chunk = await process.stdout.read(4096)
                if not chunk:
                    break
                decoded = chunk.decode(errors="replace")
                stdout_parts.append(decoded)
                if on_chunk:
                    await on_chunk(decoded)

        async def _drain_stderr() -> None:
            data = await process.stderr.read()
            if data:
                stderr_parts.append(data.decode(errors="replace"))

        try:
            await asyncio.wait_for(
                asyncio.gather(_drain_stdout(), _drain_stderr()),
                timeout=timeout_sec,
            )
            await process.wait()
        except TimeoutError:
            process.kill()
            await process.wait()
            return AgentResult(
                exit_code=-1,
                duration_sec=time.monotonic() - start,
                error=f"Timed out after {timeout_sec}s",
            )

        return AgentResult(
            stdout="".join(stdout_parts),
            stderr="".join(stderr_parts),
            exit_code=process.returncode or 0,
            duration_sec=time.monotonic() - start,
        )

    except Exception as e:
        return AgentResult(
            exit_code=-1,
            duration_sec=time.monotonic() - start,
            error=str(e),
        )
