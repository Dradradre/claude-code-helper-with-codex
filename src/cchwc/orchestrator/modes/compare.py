import asyncio
import json
from collections.abc import Awaitable, Callable

from cchwc.orchestrator.claude_runner import run_claude_p
from cchwc.orchestrator.codex_runner import run_codex_exec
from cchwc.orchestrator.modes.base import OrchestrationMode


class CompareMode(OrchestrationMode):
    name = "compare"

    async def execute(
        self,
        prompt: str,
        cwd: str,
        config: dict,
        run_id: int,
        emit: Callable[[str], Awaitable[None]],
    ) -> dict:
        timeout = config.get("timeout_per_step_sec", 600)

        await emit(json.dumps({"type": "status", "text": "Starting Compare mode..."}))

        claude_task = run_claude_p(prompt, cwd=cwd, timeout_sec=timeout)
        codex_task = run_codex_exec(prompt, cwd=cwd, timeout_sec=timeout)

        claude_result, codex_result = await asyncio.gather(
            claude_task, codex_task, return_exceptions=True
        )

        results = {}

        if isinstance(claude_result, Exception):
            await emit(json.dumps({"type": "error", "agent": "claude", "text": str(claude_result)}))
            results["claude"] = {"error": str(claude_result)}
        else:
            await emit(json.dumps({
                "type": "result", "agent": "claude", "role": "implementer",
                "text": claude_result.stdout[:2000] if claude_result.stdout else "(no output)",
            }))
            results["claude"] = {
                "stdout": claude_result.stdout,
                "exit_code": claude_result.exit_code,
                "duration": claude_result.duration_sec,
                "input_tokens": claude_result.input_tokens,
                "output_tokens": claude_result.output_tokens,
                "error": claude_result.error,
            }

        if isinstance(codex_result, Exception):
            await emit(json.dumps({"type": "error", "agent": "codex", "text": str(codex_result)}))
            results["codex"] = {"error": str(codex_result)}
        else:
            await emit(json.dumps({
                "type": "result", "agent": "codex", "role": "implementer",
                "text": codex_result.stdout[:2000] if codex_result.stdout else "(no output)",
            }))
            results["codex"] = {
                "stdout": codex_result.stdout,
                "exit_code": codex_result.exit_code,
                "duration": codex_result.duration_sec,
                "input_tokens": codex_result.input_tokens,
                "output_tokens": codex_result.output_tokens,
                "error": codex_result.error,
            }

        total_tokens = sum(
            r.get("input_tokens", 0) + r.get("output_tokens", 0)
            for r in results.values()
            if isinstance(r, dict)
        )

        return {
            "summary": "Compare completed",
            "total_tokens": total_tokens,
            "total_cost_usd": 0.0,
            "results": results,
        }
