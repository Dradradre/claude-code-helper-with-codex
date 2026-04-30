import json

from cchwc.orchestrator.claude_runner import run_claude_p
from cchwc.orchestrator.codex_runner import run_codex_exec

JUDGE_PROMPT_TEMPLATE = """You are a debate judge. Evaluate whether this discussion should continue.

Topic: {topic}

Conversation so far:
{transcript}

Latest Debater A response:
{a_response}

Latest Debater B response:
{b_response}

Classify the state:
- "converged": they now share a practical conclusion, even if minor caveats remain.
- "diverged": there is a substantive unresolved disagreement and another round could clarify it.
- "stalemate": they are repeating positions or the remaining disagreement is not productive.

Set should_continue to false for converged or stalemate.
Set should_continue to true only when the disagreement is specific and another round is likely to improve the answer.

Respond with this JSON:
{{
  "status": "converged" | "diverged" | "stalemate",
  "agreement_points": ["points both agree on"],
  "disagreement_points": ["remaining disagreements"],
  "should_continue": true or false,
  "synthesis": "if converged or stalemate, summarize the conclusion"
}}"""


async def judge_round(
    topic: str,
    a_response: str,
    b_response: str,
    transcript: str = "",
    cwd: str = ".",
    judge_agent: str = "claude",
    model: str | None = None,
    effort: str | None = None,
    timeout_sec: int = 600,
) -> dict:
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        topic=topic,
        transcript=(transcript or "(no prior conversation)")[:8000],
        a_response=a_response[:3000],
        b_response=b_response[:3000],
    )

    if judge_agent == "claude":
        result = await run_claude_p(
            prompt,
            cwd=cwd,
            output_format="json",
            model=model,
            effort=effort,
            timeout_sec=timeout_sec,
        )
    else:
        result = await run_codex_exec(
            prompt,
            cwd=cwd,
            json_mode=False,
            model=model,
            reasoning_effort=effort,
            timeout_sec=timeout_sec,
        )

    tokens = result.input_tokens + result.output_tokens
    error = _agent_failure(judge_agent, result)
    if error:
        return {
            "result": {},
            "tokens": tokens,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "raw": result.stdout,
            "error": error,
        }

    parsed = _parse_judgment(result.stdout or "")

    return {
        "result": parsed,
        "tokens": tokens,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "cost_usd": result.cost_usd,
        "raw": result.stdout,
    }


def _agent_failure(agent: str, result) -> str | None:
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


def _parse_judgment(text: str) -> dict:
    for candidate in _json_candidates(text):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and "status" in parsed:
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

    # Fallback: synthesize from raw text
    text_lower = (text or "").lower()
    if "converged" in text_lower:
        status = "converged"
        should_continue = False
    elif "stalemate" in text_lower:
        status = "stalemate"
        should_continue = False
    else:
        status = "diverged"
        should_continue = True

    return {
        "status": status,
        "agreement_points": [],
        "disagreement_points": [],
        "should_continue": should_continue,
        "synthesis": text[:800] if text else "No judgment produced",
    }


def _json_candidates(text: str) -> list[str]:
    import re

    candidates = []
    # Markdown code blocks: ```json ... ``` or ``` ... ```
    for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text):
        candidates.append(m.group(1).strip())
    # Raw braces
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        candidates.append(text[start:end])
    # Whole text
    candidates.append(text)
    return candidates
