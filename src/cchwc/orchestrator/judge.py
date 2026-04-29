import json

from cchwc.orchestrator.claude_runner import run_claude_p
from cchwc.orchestrator.codex_runner import run_codex_exec

JUDGE_PROMPT_TEMPLATE = """You are a debate judge. Evaluate the two responses below.

Topic: {topic}

Debater A's argument:
{a_response}

Debater B's argument:
{b_response}

Evaluate whether the debate has converged (both sides agree), diverged (widening disagreement), or reached stalemate.

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
    cwd: str = ".",
    judge_agent: str = "claude",
    timeout_sec: int = 600,
) -> dict:
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        topic=topic,
        a_response=a_response[:3000],
        b_response=b_response[:3000],
    )

    if judge_agent == "claude":
        result = await run_claude_p(prompt, cwd=cwd, output_format="text", timeout_sec=timeout_sec)
    else:
        result = await run_codex_exec(prompt, cwd=cwd, json_mode=False, timeout_sec=timeout_sec)

    tokens = result.input_tokens + result.output_tokens
    parsed = _parse_judgment(result.stdout or "")

    return {
        "result": parsed,
        "tokens": tokens,
        "raw": result.stdout,
    }


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
