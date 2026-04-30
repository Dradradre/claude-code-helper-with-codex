import json
import shutil
from collections.abc import Awaitable, Callable

from cchwc.config import Settings
from cchwc.orchestrator.runner import AgentResult, run_agent


def is_available() -> bool:
    return shutil.which(Settings().codex_bin) is not None


async def run_codex_exec(
    prompt: str,
    cwd: str = ".",
    json_mode: bool = False,
    model: str | None = None,
    reasoning_effort: str | None = None,
    timeout_sec: int = 600,
    on_chunk: Callable[[str], Awaitable[None]] | None = None,
) -> AgentResult:
    settings = Settings()
    cmd = [settings.codex_bin, "exec", "--json"]
    selected_model = (model or settings.codex_model or "").strip()
    if selected_model:
        cmd.extend(["--model", selected_model])
    selected_effort = (reasoning_effort or settings.codex_reasoning_effort or "").strip()
    if selected_effort:
        cmd.extend(["-c", f'model_reasoning_effort="{selected_effort}"'])
    cmd.append("-")

    raw_buffer = ""

    async def on_raw_chunk(text: str) -> None:
        nonlocal raw_buffer
        if on_chunk is None:
            return

        raw_buffer += text
        while "\n" in raw_buffer:
            line, raw_buffer = raw_buffer.split("\n", 1)
            delta = _extract_agent_message(line)
            if delta:
                await on_chunk(delta)

    result = await run_agent(
        cmd,
        cwd=cwd,
        stdin_payload=prompt,
        timeout_sec=timeout_sec,
        on_chunk=on_raw_chunk,
    )

    if result.error:
        return result

    if result.stdout:
        parsed = _parse_jsonl(result.stdout)
        result.parsed_response = parsed if json_mode else None
        if parsed.get("text"):
            result.stdout = parsed["text"]
        result.input_tokens = parsed.get("input_tokens", 0)
        result.output_tokens = parsed.get("output_tokens", 0)

    if result.exit_code != 0 and not result.stdout and result.stderr:
        result.error = result.stderr[:500]

    return result


def _extract_agent_message(line: str) -> str:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return ""

    if event.get("type") != "item.completed":
        return ""

    item = event.get("item") or {}
    if item.get("type") != "agent_message":
        return ""
    return item.get("text") or ""


def _parse_jsonl(stdout: str) -> dict:
    text_parts: list[str] = []
    input_tokens = 0
    output_tokens = 0

    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        if event.get("type") == "item.completed":
            item = event.get("item") or {}
            if item.get("type") == "agent_message":
                text_parts.append(item.get("text") or "")
        elif event.get("type") == "turn.completed":
            usage = event.get("usage") or {}
            input_tokens = usage.get("input_tokens", input_tokens)
            output_tokens = usage.get("output_tokens", output_tokens)

    return {
        "text": "\n".join(part for part in text_parts if part),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
