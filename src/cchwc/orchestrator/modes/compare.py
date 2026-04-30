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
        claude_model = self._agent_model("claude", config)
        codex_model = self._agent_model("codex", config)
        claude_effort = self._agent_effort("claude", config)
        codex_effort = self._agent_effort("codex", config)

        await emit(json.dumps({"type": "status", "text": "Claude와 Codex에 동시 요청 중..."}))

        results: dict = {}

        async def _run(agent_name: str, coro_fn) -> None:
            await emit(json.dumps({"type": "stream_start", "agent": agent_name, "role": "implementer"}))

            async def on_chunk(text: str) -> None:
                await emit(json.dumps({"type": "chunk", "agent": agent_name, "text": text}))

            try:
                result = await coro_fn(on_chunk)
            except Exception as e:
                await emit(json.dumps({"type": "stream_end", "agent": agent_name, "error": str(e)}))
                results[agent_name] = {"error": str(e)}
                return

            error = self._agent_failure(agent_name, result)
            result.error = error
            await emit(json.dumps({
                "type": "stream_end",
                "agent": agent_name,
                "error": error,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cost_usd": result.cost_usd,
            }))
            results[agent_name] = {
                "stdout": result.stdout,
                "exit_code": result.exit_code,
                "duration": result.duration_sec,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cost_usd": result.cost_usd,
                "error": result.error,
            }

        async with asyncio.TaskGroup() as tg:
            tg.create_task(_run(
                "claude",
                lambda cb: run_claude_p(
                    prompt,
                    cwd=cwd,
                    output_format="stream-json",
                    model=claude_model,
                    effort=claude_effort,
                    timeout_sec=timeout,
                    on_chunk=cb,
                ),
            ))
            tg.create_task(_run(
                "codex",
                lambda cb: run_codex_exec(
                    prompt,
                    cwd=cwd,
                    model=codex_model,
                    reasoning_effort=codex_effort,
                    timeout_sec=timeout,
                    on_chunk=cb,
                ),
            ))

        total_tokens = sum(
            r.get("input_tokens", 0) + r.get("output_tokens", 0)
            for r in results.values()
            if isinstance(r, dict)
        )
        errors = [f"{agent}: {r['error']}" for agent, r in results.items() if isinstance(r, dict) and r.get("error")]
        if errors:
            raise RuntimeError("; ".join(errors))
        total_cost_usd = sum(r.get("cost_usd", 0.0) for r in results.values() if isinstance(r, dict))
        if budget_message := self._budget_message(total_tokens, total_cost_usd, config):
            await emit(json.dumps({"type": "status", "text": budget_message}))

        return {
            "summary": "Compare completed",
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost_usd,
            "results": results,
        }
