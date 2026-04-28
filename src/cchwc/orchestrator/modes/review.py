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

        await emit(json.dumps({"type": "status", "text": f"Implementation by {implementer}..."}))
        impl_result = await self._run_agent(implementer, prompt, cwd, timeout)
        total_tokens += impl_result.input_tokens + impl_result.output_tokens

        await emit(json.dumps({
            "type": "result", "agent": implementer, "role": "implementer",
            "text": impl_result.stdout[:2000] if impl_result.stdout else "(no output)",
        }))

        if impl_result.error:
            return {
                "summary": f"Implementation failed: {impl_result.error}",
                "total_tokens": total_tokens,
                "total_cost_usd": 0.0,
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

            await emit(json.dumps({"type": "status", "text": f"Review round {round_num + 1} by {reviewer}..."}))
            review_result = await self._run_agent(reviewer, review_prompt, cwd, timeout)
            total_tokens += review_result.input_tokens + review_result.output_tokens

            await emit(json.dumps({
                "type": "result", "agent": reviewer, "role": "reviewer",
                "text": review_result.stdout[:2000] if review_result.stdout else "(no output)",
            }))

            if review_result.error:
                break

            verdict = self._parse_verdict(review_result.stdout)

            if verdict == "approve":
                await emit(json.dumps({"type": "status", "text": "Approved!"}))
                break

            if round_num < max_rounds - 1:
                fix_prompt = (
                    f"Fix the implementation based on review feedback.\n\n"
                    f"Original task: {prompt}\n\n"
                    f"Your implementation:\n{current_impl[:3000]}\n\n"
                    f"Review feedback:\n{review_result.stdout[:3000]}\n\n"
                    f"Provide the fixed implementation."
                )

                await emit(json.dumps({"type": "status", "text": f"Revision by {implementer}..."}))
                fix_result = await self._run_agent(implementer, fix_prompt, cwd, timeout)
                total_tokens += fix_result.input_tokens + fix_result.output_tokens
                current_impl = fix_result.stdout

                await emit(json.dumps({
                    "type": "result", "agent": implementer, "role": "implementer",
                    "text": fix_result.stdout[:2000] if fix_result.stdout else "(no output)",
                }))

        return {
            "summary": "Review completed",
            "total_tokens": total_tokens,
            "total_cost_usd": 0.0,
        }

    async def _run_agent(self, agent: str, prompt: str, cwd: str, timeout: int):
        if agent == "claude":
            return await run_claude_p(prompt, cwd=cwd, output_format="text", timeout_sec=timeout)
        else:
            return await run_codex_exec(prompt, cwd=cwd, json_mode=False, timeout_sec=timeout)

    def _parse_verdict(self, output: str) -> str:
        try:
            data = json.loads(output)
            return data.get("verdict", "request_changes")
        except (json.JSONDecodeError, TypeError):
            if "approve" in output.lower():
                return "approve"
            return "request_changes"
