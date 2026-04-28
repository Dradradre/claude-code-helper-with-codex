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
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

    return {
        "status": "stalemate",
        "agreement_points": [],
        "disagreement_points": ["Could not parse judgment"],
        "should_continue": False,
        "synthesis": text[:500] if text else "No judgment produced",
    }
