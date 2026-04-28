import json
from collections.abc import Awaitable, Callable

from cchwc.orchestrator.claude_runner import run_claude_p
from cchwc.orchestrator.codex_runner import run_codex_exec
from cchwc.orchestrator.judge import judge_round
from cchwc.orchestrator.modes.base import OrchestrationMode

DEBATER_SCHEMA = """{
  "position": "your position on the topic",
  "evidence": ["supporting evidence 1", "..."],
  "concedes": ["points from opponent you agree with"],
  "challenges": ["points from opponent you dispute"]
}"""


class DebateMode(OrchestrationMode):
    name = "debate"

    async def execute(
        self,
        prompt: str,
        cwd: str,
        config: dict,
        run_id: int,
        emit: Callable[[str], Awaitable[None]],
    ) -> dict:
        debater_a = config.get("debater_a", "claude")
        debater_b = config.get("debater_b", "codex")
        max_rounds = config.get("max_rounds", 3)
        max_total_tokens = config.get("max_total_tokens", 100_000)
        timeout = config.get("timeout_per_step_sec", 600)
        convergence_after = config.get("convergence_check_after_round", 1)

        total_tokens = 0
        a_position = ""
        b_position = ""
        empty_concedes_streak = 0

        for round_num in range(1, max_rounds + 1):
            await emit(json.dumps({"type": "status", "text": f"Round {round_num}/{max_rounds}"}))

            a_prompt = self._build_prompt(prompt, round_num, a_position, b_position, is_first=round_num == 1)
            await emit(json.dumps({"type": "status", "text": f"Debater A ({debater_a}) arguing..."}))
            a_result = await self._run_agent(debater_a, a_prompt, cwd, timeout)
            total_tokens += a_result.input_tokens + a_result.output_tokens
            a_response = a_result.stdout or ""

            await emit(json.dumps({
                "type": "result", "agent": debater_a, "role": "debater_a",
                "text": a_response[:2000],
            }))

            b_prompt = self._build_prompt(prompt, round_num, b_position, a_response, is_first=round_num == 1)
            await emit(json.dumps({"type": "status", "text": f"Debater B ({debater_b}) arguing..."}))
            b_result = await self._run_agent(debater_b, b_prompt, cwd, timeout)
            total_tokens += b_result.input_tokens + b_result.output_tokens
            b_response = b_result.stdout or ""

            await emit(json.dumps({
                "type": "result", "agent": debater_b, "role": "debater_b",
                "text": b_response[:2000],
            }))

            a_parsed = self._parse_structured(a_response)
            b_parsed = self._parse_structured(b_response)

            a_concedes = a_parsed.get("concedes", []) if a_parsed else []
            b_concedes = b_parsed.get("concedes", []) if b_parsed else []

            if not a_concedes and not b_concedes:
                empty_concedes_streak += 1
            else:
                empty_concedes_streak = 0

            if empty_concedes_streak >= 2:
                await emit(json.dumps({"type": "status", "text": "Stalemate detected (no concessions for 2 rounds)"}))
                break

            a_position = a_response
            b_position = b_response

            if total_tokens >= max_total_tokens:
                await emit(json.dumps({"type": "status", "text": f"Token limit reached ({total_tokens:,})"}))
                break

            if round_num >= convergence_after:
                await emit(json.dumps({"type": "status", "text": "Judge evaluating..."}))
                judgment = await judge_round(
                    topic=prompt,
                    a_response=a_response,
                    b_response=b_response,
                    cwd=cwd,
                    judge_agent=config.get("judge", "claude"),
                    timeout_sec=timeout,
                )
                total_tokens += judgment.get("tokens", 0)

                await emit(json.dumps({
                    "type": "result", "agent": config.get("judge", "claude"), "role": "judge",
                    "text": json.dumps(judgment.get("result", {}), indent=2, ensure_ascii=False),
                }))

                result = judgment.get("result", {})
                if not result.get("should_continue", True):
                    status = result.get("status", "converged")
                    await emit(json.dumps({"type": "status", "text": f"Debate ended: {status}"}))
                    break

        return {
            "summary": f"Debate completed after {round_num} rounds",
            "total_tokens": total_tokens,
            "total_cost_usd": 0.0,
        }

    def _build_prompt(self, topic: str, round_num: int, my_prev: str, opponent_latest: str, is_first: bool) -> str:
        if is_first:
            return (
                f"Topic: {topic}\n\n"
                f"Present your position on this topic. Respond with this JSON structure:\n{DEBATER_SCHEMA}"
            )
        return (
            f"Topic: {topic}\n\n"
            f"Your previous position summary: {my_prev[:2000]}\n"
            f"Opponent's latest argument: {opponent_latest[:2000]}\n\n"
            f"Respond with this JSON structure:\n{DEBATER_SCHEMA}"
        )

    async def _run_agent(self, agent: str, prompt: str, cwd: str, timeout: int):
        if agent == "claude":
            return await run_claude_p(prompt, cwd=cwd, output_format="text", timeout_sec=timeout)
        else:
            return await run_codex_exec(prompt, cwd=cwd, json_mode=False, timeout_sec=timeout)

    def _parse_structured(self, text: str) -> dict | None:
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
        return None
