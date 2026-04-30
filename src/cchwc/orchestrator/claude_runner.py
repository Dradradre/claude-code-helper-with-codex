import json
import shutil
from collections.abc import Awaitable, Callable

from cchwc.config import Settings
from cchwc.orchestrator.runner import AgentResult, run_agent


def is_available() -> bool:
    return shutil.which(Settings().claude_bin) is not None


async def run_claude_p(
    prompt: str,
    cwd: str = ".",
    output_format: str = "text",
    allowed_tools: list[str] | None = None,
    max_turns: int | None = None,
    model: str | None = None,
    effort: str | None = None,
    timeout_sec: int = 600,
    on_chunk: Callable[[str], Awaitable[None]] | None = None,
) -> AgentResult:
    # 프롬프트는 stdin으로 전달 — Windows cmd /c 환경에서 멀티라인 인자가 깨지는 문제 우회
    settings = Settings()
    cmd = [settings.claude_bin, "-p", "--output-format", output_format]
    selected_model = (model or settings.claude_model or "").strip()
    if selected_model:
        cmd.extend(["--model", selected_model])
    selected_effort = (effort or settings.claude_effort or "").strip()
    if selected_effort:
        cmd.extend(["--effort", selected_effort])
    if output_format == "stream-json":
        cmd.extend(["--verbose", "--include-partial-messages"])
    if allowed_tools:
        for tool in allowed_tools:
            cmd.extend(["--allowedTools", tool])
    if max_turns:
        cmd.extend(["--max-turns", str(max_turns)])

    raw_buffer = ""

    async def on_raw_chunk(text: str) -> None:
        nonlocal raw_buffer
        if output_format != "stream-json" or on_chunk is None:
            if on_chunk:
                await on_chunk(text)
            return

        raw_buffer += text
        while "\n" in raw_buffer:
            line, raw_buffer = raw_buffer.split("\n", 1)
            delta = _extract_stream_delta(line)
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

    if output_format == "stream-json" and result.stdout:
        parsed = _parse_stream_json(result.stdout)
        result.parsed_response = parsed
        result.stdout = parsed.get("text", "") or result.stdout
        result.input_tokens = parsed.get("input_tokens", 0)
        result.output_tokens = parsed.get("output_tokens", 0)
        result.cost_usd = parsed.get("cost_usd", 0.0)
        result.spawned_session_id = parsed.get("session_id")
        return result

    if output_format == "json" and result.stdout:
        try:
            parsed = json.loads(result.stdout)
            result.parsed_response = parsed
            # claude -p json 응답 구조: {"type":"result", "result": "...", "usage": {...}}
            result.stdout = parsed.get("result") or parsed.get("content") or result.stdout
            usage = parsed.get("usage", {})
            result.input_tokens = _claude_input_tokens(usage)
            result.output_tokens = usage.get("output_tokens", 0)
            result.cost_usd = parsed.get("total_cost_usd", 0.0) or 0.0
            result.spawned_session_id = parsed.get("session_id")
        except json.JSONDecodeError:
            pass

    if result.exit_code != 0 and not result.stdout and result.stderr:
        result.error = result.stderr[:500]

    return result


def _extract_stream_delta(line: str) -> str:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return ""

    if event.get("type") != "stream_event":
        return ""

    inner = event.get("event") or {}
    if inner.get("type") != "content_block_delta":
        return ""

    delta = inner.get("delta") or {}
    if delta.get("type") != "text_delta":
        return ""
    return delta.get("text") or ""


def _parse_stream_json(stdout: str) -> dict:
    text_parts: list[str] = []
    final_text = ""
    input_tokens = 0
    output_tokens = 0
    cost_usd = 0.0
    session_id = None

    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        if not session_id:
            session_id = event.get("session_id")

        event_type = event.get("type")
        if event_type == "stream_event":
            inner = event.get("event") or {}
            if inner.get("type") == "content_block_delta":
                delta = inner.get("delta") or {}
                if delta.get("type") == "text_delta":
                    text_parts.append(delta.get("text") or "")
            elif inner.get("type") == "message_delta":
                usage = inner.get("usage") or {}
                input_tokens = _claude_input_tokens(usage) or input_tokens
                output_tokens = usage.get("output_tokens", output_tokens)

        elif event_type == "assistant" and not final_text:
            message = event.get("message") or {}
            final_text = _text_from_content(message.get("content"))
            usage = message.get("usage") or {}
            input_tokens = _claude_input_tokens(usage) or input_tokens
            output_tokens = usage.get("output_tokens", output_tokens)

        elif event_type == "result":
            final_text = event.get("result") or final_text
            usage = event.get("usage") or {}
            input_tokens = _claude_input_tokens(usage) or input_tokens
            output_tokens = usage.get("output_tokens", output_tokens)
            cost_usd = event.get("total_cost_usd", cost_usd) or cost_usd
            session_id = event.get("session_id") or session_id

    return {
        "text": final_text or "".join(text_parts),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "session_id": session_id,
    }


def _text_from_content(content: object) -> str:
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(item.get("text") or "")
    return "".join(parts)


def _claude_input_tokens(usage: dict) -> int:
    return (
        usage.get("input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
    )
