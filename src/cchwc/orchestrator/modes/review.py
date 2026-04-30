import json
from collections.abc import Awaitable, Callable

from cchwc.orchestrator.claude_runner import run_claude_p
from cchwc.orchestrator.codex_runner import run_codex_exec
from cchwc.orchestrator.modes.base import OrchestrationMode


class ReviewMode(OrchestrationMode):
    name = "review"

    async def execute(
        self,
        prompt: str,
        cwd: str,
        config: dict,
        run_id: int,
        emit: Callable[[str], Awaitable[None]],
    ) -> dict:
        implementer = config.get("implementer", "claude")
        reviewer = config.get("reviewer", "codex")
        max_rounds = config.get("max_review_rounds", 1)
        timeout = config.get("timeout_per_step_sec", 600)
        total_tokens = 0
        total_cost_usd = 0.0

        await emit(json.dumps({"type": "status", "text": f"{implementer} 구현 중..."}))
        impl_result = await self._run_streaming(implementer, prompt, cwd, timeout, "implementer", emit, config)
        total_tokens += impl_result.input_tokens + impl_result.output_tokens
        total_cost_usd += impl_result.cost_usd

        if failure := self._agent_failure(implementer, impl_result):
            raise RuntimeError(f"Implementation failed: {failure}")
        if budget_message := self._budget_message(total_tokens, total_cost_usd, config):
            await emit(json.dumps({"type": "status", "text": budget_message}))
            return {
                "summary": f"Review stopped: {budget_message}",
                "total_tokens": total_tokens,
                "total_cost_usd": total_cost_usd,
            }

        current_impl = impl_result.stdout

        for round_num in range(max_rounds):
            review_prompt = (
                f"Review the following implementation and provide feedback.\n\n"
                f"Original task: {prompt}\n\n"
                f"Implementation:\n{current_impl[:5000]}\n\n"
                f'Respond with JSON: {{"verdict": "approve" or "request_changes", '
                f'"issues": [...], "suggestions": [...]}}'
            )

            await emit(json.dumps({"type": "status", "text": f"{reviewer} 리뷰 중 (round {round_num + 1})..."}))
            review_result = await self._run_streaming(reviewer, review_prompt, cwd, timeout, "reviewer", emit, config)
            total_tokens += review_result.input_tokens + review_result.output_tokens
            total_cost_usd += review_result.cost_usd

            if failure := self._agent_failure(reviewer, review_result):
                raise RuntimeError(f"Review failed: {failure}")
            if budget_message := self._budget_message(total_tokens, total_cost_usd, config):
                await emit(json.dumps({"type": "status", "text": budget_message}))
                break

            verdict = self._parse_verdict(review_result.stdout)

            if verdict == "approve":
                await emit(json.dumps({"type": "status", "text": "승인됨!"}))
                break

            if round_num < max_rounds - 1:
                fix_prompt = (
                    f"Fix the implementation based on review feedback.\n\n"
                    f"Original task: {prompt}\n\n"
                    f"Your implementation:\n{current_impl[:3000]}\n\n"
                    f"Review feedback:\n{review_result.stdout[:3000]}\n\n"
                    f"Provide the fixed implementation."
                )

                await emit(json.dumps({"type": "status", "text": f"{implementer} 수정 중..."}))
                fix_result = await self._run_streaming(
                    implementer,
                    fix_prompt,
                    cwd,
                    timeout,
                    "implementer",
                    emit,
                    config,
                )
                total_tokens += fix_result.input_tokens + fix_result.output_tokens
                total_cost_usd += fix_result.cost_usd
                if failure := self._agent_failure(implementer, fix_result):
                    raise RuntimeError(f"Fix failed: {failure}")
                if budget_message := self._budget_message(total_tokens, total_cost_usd, config):
                    await emit(json.dumps({"type": "status", "text": budget_message}))
                    break
                current_impl = fix_result.stdout

        return {
            "summary": "Review completed",
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost_usd,
        }

    async def _run_streaming(
        self,
        agent: str,
        prompt: str,
        cwd: str,
        timeout: int,
        role: str,
        emit: Callable[[str], Awaitable[None]],
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

    def _parse_verdict(self, output: str) -> str:
        for candidate in [output]:
            try:
                data = json.loads(candidate)
                return data.get("verdict", "request_changes")
            except (json.JSONDecodeError, TypeError):
                pass
        if "approve" in output.lower():
            return "approve"
        return "request_changes"
