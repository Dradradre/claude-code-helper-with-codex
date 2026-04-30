import asyncio
import platform
import shutil
import subprocess
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AgentResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_sec: float = 0.0
    command: list[str] | None = None
    spawned_session_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    parsed_response: dict | None = None
    error: str | None = None


def _resolve_cmd(cmd: list[str]) -> list[str]:
    """Windows에서 .CMD/.BAT 파일은 cmd /c로 감싸야 실행 가능."""
    if platform.system() != "Windows":
        return cmd

    command = Path(cmd[0])
    if not command.suffix:
        for ext in (".cmd", ".bat"):
            shim = shutil.which(f"{cmd[0]}{ext}")
            if shim:
                return ["cmd", "/d", "/s", "/c", shim, *cmd[1:]]

            sibling = command.with_suffix(ext)
            if command.parent != Path(".") and sibling.exists():
                return ["cmd", "/d", "/s", "/c", str(sibling), *cmd[1:]]

    exe = shutil.which(cmd[0])
    if exe and Path(exe).suffix.lower() in {".cmd", ".bat"}:
        return ["cmd", "/d", "/s", "/c", exe, *cmd[1:]]
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
        try:
            process = await asyncio.create_subprocess_exec(
                *resolved,
                cwd=cwd,
                stdin=asyncio.subprocess.PIPE if stdin_payload else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except NotImplementedError:
            return await _run_agent_blocking(
                resolved=resolved,
                cwd=cwd,
                stdin_payload=stdin_payload,
                timeout_sec=timeout_sec,
                env=env,
                on_chunk=on_chunk,
                start=start,
            )

        stdout_parts: list[str] = []
        stderr_parts: list[str] = []

        async def _write_stdin() -> None:
            if stdin_payload and process.stdin:
                try:
                    process.stdin.write(stdin_payload.encode())
                    await process.stdin.drain()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    process.stdin.close()
                    with suppress(BrokenPipeError, ConnectionResetError, OSError):
                        await process.stdin.wait_closed()

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
                asyncio.gather(_write_stdin(), _drain_stdout(), _drain_stderr()),
                timeout=timeout_sec,
            )
            await process.wait()
        except TimeoutError:
            process.kill()
            await process.wait()
            return AgentResult(
                exit_code=-1,
                duration_sec=time.monotonic() - start,
                command=resolved,
                error=f"Timed out after {timeout_sec}s",
            )

        return AgentResult(
            stdout="".join(stdout_parts),
            stderr="".join(stderr_parts),
            exit_code=process.returncode or 0,
            duration_sec=time.monotonic() - start,
            command=resolved,
        )

    except Exception as e:
        return AgentResult(
            exit_code=-1,
            duration_sec=time.monotonic() - start,
            command=resolved,
            error=str(e),
        )


async def _run_agent_blocking(
    resolved: list[str],
    cwd: str,
    stdin_payload: str | None,
    timeout_sec: int,
    env: dict | None,
    on_chunk: Callable[[str], Awaitable[None]] | None,
    start: float,
) -> AgentResult:
    loop = asyncio.get_running_loop()

    def _run() -> AgentResult:
        try:
            run_kwargs = {
                "cwd": cwd,
                "capture_output": True,
                "env": env,
                "timeout": timeout_sec,
                "check": False,
            }
            if stdin_payload is not None:
                run_kwargs["input"] = stdin_payload.encode()
            else:
                run_kwargs["stdin"] = subprocess.DEVNULL

            completed = subprocess.run(
                resolved,
                **run_kwargs,
            )
        except subprocess.TimeoutExpired as e:
            stdout = _decode_timeout_output(e.stdout)
            stderr = _decode_timeout_output(e.stderr)
            return AgentResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=-1,
                duration_sec=time.monotonic() - start,
                command=resolved,
                error=f"Timed out after {timeout_sec}s",
            )
        except Exception as e:
            return AgentResult(
                exit_code=-1,
                duration_sec=time.monotonic() - start,
                command=resolved,
                error=str(e),
            )

        stdout = completed.stdout.decode(errors="replace")
        stderr = completed.stderr.decode(errors="replace")
        if on_chunk and stdout:
            future = asyncio.run_coroutine_threadsafe(on_chunk(stdout), loop)
            future.result()

        return AgentResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=completed.returncode or 0,
            duration_sec=time.monotonic() - start,
            command=resolved,
        )

    return await asyncio.to_thread(_run)


def _decode_timeout_output(output: bytes | str | None) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    return output.decode(errors="replace")
