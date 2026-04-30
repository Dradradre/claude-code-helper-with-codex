import json
from collections.abc import Awaitable, Callable

from cchwc.orchestrator.claude_runner import run_claude_p
from cchwc.orchestrator.codex_runner import run_codex_exec
from cchwc.orchestrator.judge import judge_round
from cchwc.orchestrator.modes.base import OrchestrationMode


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
        try:
            max_rounds = max(1, int(config.get("max_rounds", 3)))
        except (TypeError, ValueError):
            max_rounds = 3
        max_total_tokens = config.get("max_total_tokens", 100_000)
        timeout = config.get("timeout_per_step_sec", 600)
        convergence_after = config.get("convergence_check_after_round", 1)

        total_tokens = 0
        total_cost_usd = 0.0
        transcript: list[tuple[str, str]] = []

        for round_num in range(1, max_rounds + 1):
            await emit(json.dumps({"type": "status", "text": f"Round {round_num}/{max_rounds}"}))

            a_prompt = self._build_prompt(prompt, round_num, "A", transcript)
            await emit(json.dumps({"type": "status", "text": f"Debater A ({debater_a}) 응답 작성 중..."}))
            a_result = await self._run_streaming(debater_a, a_prompt, cwd, timeout, "debater_a", emit, config)
            total_tokens += a_result.input_tokens + a_result.output_tokens
            total_cost_usd += a_result.cost_usd
            if failure := self._agent_failure(debater_a, a_result):
                raise RuntimeError(f"Debater A failed: {failure}")
            a_response = a_result.stdout or ""
            transcript.append(("Debater A", a_response))

            b_prompt = self._build_prompt(prompt, round_num, "B", transcript)
            await emit(json.dumps({"type": "status", "text": f"Debater B ({debater_b}) 응답 작성 중..."}))
            b_result = await self._run_streaming(debater_b, b_prompt, cwd, timeout, "debater_b", emit, config)
            total_tokens += b_result.input_tokens + b_result.output_tokens
            total_cost_usd += b_result.cost_usd
            if failure := self._agent_failure(debater_b, b_result):
                raise RuntimeError(f"Debater B failed: {failure}")
            b_response = b_result.stdout or ""
            transcript.append(("Debater B", b_response))

            budget_message = self._budget_message(
                total_tokens,
                total_cost_usd,
                {**config, "max_total_tokens": max_total_tokens},
            )
            if budget_message:
                await emit(json.dumps({"type": "status", "text": budget_message}))
                break

            if round_num >= convergence_after:
                await emit(json.dumps({"type": "status", "text": "Judge evaluating..."}))
                judge_agent = config.get("judge", "claude")
                await emit(json.dumps({"type": "stream_start", "agent": judge_agent, "role": "judge"}))
                judgment = await judge_round(
                    topic=prompt,
                    a_response=a_response,
                    b_response=b_response,
                    transcript=self._format_transcript(transcript),
                    cwd=cwd,
                    judge_agent=judge_agent,
                    model=self._agent_model(judge_agent, config),
                    effort=self._agent_effort(judge_agent, config),
                    timeout_sec=timeout,
                )
                total_tokens += judgment.get("tokens", 0)
                total_cost_usd += judgment.get("cost_usd", 0.0)
                if judgment.get("error"):
                    raise RuntimeError(f"Judge failed: {judgment['error']}")
                await emit(json.dumps({
                    "type": "result",
                    "agent": judge_agent,
                    "role": "judge",
                    "text": json.dumps(judgment.get("result", {}), indent=2, ensure_ascii=False),
                    "input_tokens": judgment.get("input_tokens", 0),
                    "output_tokens": judgment.get("output_tokens", 0),
                    "cost_usd": judgment.get("cost_usd", 0.0),
                }))
                await emit(json.dumps({"type": "stream_end", "agent": judge_agent}))

                result = judgment.get("result", {})
                if not result.get("should_continue", True):
                    status = result.get("status", "converged")
                    await emit(json.dumps({"type": "status", "text": f"Debate ended: {status}"}))
                    break

        return {
            "summary": f"Debate completed after {round_num} rounds",
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost_usd,
        }

    def _build_prompt(
        self,
        topic: str,
        round_num: int,
        side: str,
        transcript: list[tuple[str, str]],
    ) -> str:
        name = f"Debater {side}"
        other = "Debater B" if side == "A" else "Debater A"
        if not transcript:
            return (
                f"Topic: {topic}\n\n"
                f"You are {name}. Start a practical, good-faith discussion about the topic.\n"
                "Do not use JSON or a fixed schema. Write naturally.\n"
                "State your initial view, the key reason for it, and what could change your mind.\n"
                "Keep it concise but specific."
            )

        return (
            f"Topic: {topic}\n\n"
            f"You are {name}. Continue the discussion with {other}.\n"
            "Goal: reach the best shared conclusion if possible, not to win.\n"
            "Read the conversation so far, respond directly to the latest points, and do one of these:\n"
            "- If you agree, say what conclusion you now share and any remaining caveat.\n"
            "- If you disagree, explain the exact remaining disagreement and propose a concrete way to resolve it.\n"
            "- If the disagreement is mostly about wording or scope, suggest a compromise formulation.\n\n"
            "Do not use JSON or a fixed schema. Write naturally.\n\n"
            f"Conversation so far:\n{self._format_transcript(transcript)}"
        )

    def _format_transcript(self, transcript: list[tuple[str, str]], limit: int = 8000) -> str:
        text = "\n\n".join(f"{speaker}:\n{message}" for speaker, message in transcript)
        if len(text) <= limit:
            return text
        return text[-limit:]

    async def _run_streaming(
        self,
        agent: str,
        prompt: str,
        cwd: str,
        timeout: int,
        role: str,
        emit,
        config: dict,
    ):
        await emit(json.dumps({"type": "stream_start", "agent": agent, "role": role}))

        async def on_chunk(text: str) -> None:
            await emit(json.dumps({"type": "chunk", "agent": agent, "text": text}))

        if agent == "claude":
            result = await run_claude_p(
                prompt,
                cwd=cwd,
                output_format="stream-json",
                model=self._agent_model("claude", config),
                effort=self._agent_effort("claude", config),
                timeout_sec=timeout,
                on_chunk=on_chunk,
            )
        else:
            result = await run_codex_exec(
                prompt,
                cwd=cwd,
                json_mode=False,
                model=self._agent_model("codex", config),
                reasoning_effort=self._agent_effort("codex", config),
                timeout_sec=timeout,
                on_chunk=on_chunk,
            )

        result.error = self._agent_failure(agent, result)
        await emit(json.dumps({
            "type": "stream_end",
            "agent": agent,
            "error": result.error,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": result.cost_usd,
        }))
        return result
