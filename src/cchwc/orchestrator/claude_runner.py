import json
import shutil

from cchwc.orchestrator.runner import AgentResult, run_agent


def is_available() -> bool:
    return shutil.which("claude") is not None


async def run_claude_p(
    prompt: str,
    cwd: str = ".",
    output_format: str = "text",
    allowed_tools: list[str] | None = None,
    max_turns: int | None = None,
    timeout_sec: int = 600,
) -> AgentResult:
    cmd = ["claude", "-p", prompt, "--output-format", output_format]
    if allowed_tools:
        for tool in allowed_tools:
            cmd.extend(["--allowedTools", tool])
    if max_turns:
        cmd.extend(["--max-turns", str(max_turns)])

    result = await run_agent(cmd, cwd=cwd, timeout_sec=timeout_sec)

    if result.error:
        return result

    if output_format == "json" and result.stdout:
        try:
            parsed = json.loads(result.stdout)
            result.parsed_response = parsed
            # claude -p json 응답 구조: {"type":"result", "result": "...", "usage": {...}}
            result.stdout = parsed.get("result") or parsed.get("content") or result.stdout
            usage = parsed.get("usage", {})
            result.input_tokens = usage.get("input_tokens", 0)
            result.output_tokens = usage.get("output_tokens", 0)
        except json.JSONDecodeError:
            pass

    if result.exit_code != 0 and not result.stdout and result.stderr:
        result.error = result.stderr[:500]

    return result
