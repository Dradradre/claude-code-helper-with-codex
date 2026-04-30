import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cchwc.core.models import OrchestrationRun, OrchestrationStep
from cchwc.server.deps import get_db

router = APIRouter()

_run_events: dict[int, asyncio.Queue] = {}
_run_tasks: dict[int, asyncio.Task] = {}


class RunRequest(BaseModel):
    mode: str
    prompt: str
    cwd: str = "."
    config: dict = {}


@router.post("/runs")
async def create_run(req: RunRequest, db: AsyncSession = Depends(get_db)):
    run = OrchestrationRun(
        mode=req.mode,
        user_prompt=req.prompt,
        cwd=req.cwd,
        started_at=datetime.now(),
        status="running",
        config_json=json.dumps(req.config),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    _run_events[run.id] = asyncio.Queue()

    task = asyncio.create_task(_execute_run(run.id, req))
    _run_tasks[run.id] = task

    return {"id": run.id, "status": "running"}


@router.get("/runs")
async def list_runs(
    offset: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    query = select(OrchestrationRun).order_by(OrchestrationRun.started_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    runs = result.scalars().all()

    return [
        {
            "id": r.id,
            "mode": r.mode,
            "status": r.status,
            "started_at": r.started_at.isoformat(),
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "total_tokens": r.total_tokens,
            "result_summary": r.result_summary,
        }
        for r in runs
    ]


@router.get("/runs/partial")
async def list_runs_partial(
    request: Request,
    offset: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    query = select(OrchestrationRun).order_by(OrchestrationRun.started_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    runs = result.scalars().all()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="orchestrate/_runs_list.html",
        context={
            "runs": runs,
            "status_badge_class": status_badge_class,
            "status_label": status_label,
            "mode_label": mode_label,
            "compact_text": compact_text,
            "duration_sec": _duration_sec,
        },
    )


@router.get("/runs/{run_id}")
async def get_run(run_id: int, db: AsyncSession = Depends(get_db)):
    run = await db.get(OrchestrationRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    query = select(OrchestrationStep).where(OrchestrationStep.run_id == run_id).order_by(OrchestrationStep.sequence)
    steps = (await db.execute(query)).scalars().all()

    return {
        "id": run.id,
        "mode": run.mode,
        "user_prompt": run.user_prompt,
        "cwd": run.cwd,
        "config": _load_json(run.config_json),
        "status": run.status,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_sec": _duration_sec(run.started_at, run.finished_at),
        "total_tokens": run.total_tokens,
        "total_cost_usd": run.total_cost_usd,
        "result_summary": run.result_summary,
        "steps": [
            {
                "id": s.id,
                "sequence": s.sequence,
                "agent_type": s.agent_type,
                "role": s.role,
                "prompt": s.prompt,
                "response": s.response,
                "started_at": s.started_at.isoformat(),
                "finished_at": s.finished_at.isoformat() if s.finished_at else None,
                "input_tokens": s.input_tokens,
                "output_tokens": s.output_tokens,
                "cost_usd": s.cost_usd,
                "error": s.error,
            }
            for s in steps
        ],
    }


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: int):
    queue = _run_events.get(run_id)
    if not queue:
        raise HTTPException(status_code=404, detail="Run not found or already completed")

    async def event_generator():
        while True:
            event = await queue.get()
            if event is None:
                yield "data: {\"type\": \"done\"}\n\n"
                break
            yield f"data: {event}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/runs/{run_id}/stop")
async def stop_run(run_id: int, db: AsyncSession = Depends(get_db)):
    run = await db.get(OrchestrationRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    run.status = "stopped"
    run.finished_at = datetime.now()
    await db.commit()

    queue = _run_events.get(run_id)
    if queue:
        await queue.put(json.dumps({"type": "error", "text": "Stopped by user"}))
        await queue.put(None)

    task = _run_tasks.get(run_id)
    if task and not task.done():
        task.cancel()

    return {"id": run_id, "status": "stopped"}


async def _execute_run(run_id: int, req: RunRequest) -> None:
    from cchwc.core.db import get_session_factory
    from cchwc.orchestrator.modes.compare import CompareMode
    from cchwc.orchestrator.modes.review import ReviewMode

    session_factory = get_session_factory()
    queue = _run_events.get(run_id)
    sequence = 0
    active_steps: dict[tuple[str, str], dict] = {}
    active_by_agent: dict[str, tuple[str, str]] = {}

    async def persist_step(
        *,
        agent_type: str,
        role: str,
        response: str,
        error: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        nonlocal sequence
        sequence += 1
        now = datetime.now()
        async with session_factory() as db:
            db.add(
                OrchestrationStep(
                    run_id=run_id,
                    sequence=sequence,
                    agent_type=agent_type,
                    role=role,
                    prompt=req.prompt,
                    response=response,
                    started_at=started_at or now,
                    finished_at=finished_at or now,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    error=error,
                )
            )
            await db.commit()

    async def record_event(event_data: str) -> None:
        try:
            ev = json.loads(event_data)
        except json.JSONDecodeError:
            return

        event_type = ev.get("type")
        now = datetime.now()
        if event_type == "status":
            await persist_step(
                agent_type="system",
                role="status",
                response=ev.get("text", ""),
                started_at=now,
                finished_at=now,
            )
            return

        if event_type == "stream_start":
            agent = ev.get("agent", "unknown")
            role = ev.get("role", "unknown")
            key = (agent, role)
            active_steps[key] = {
                "started_at": now,
                "parts": [],
                "error": None,
            }
            active_by_agent[agent] = key
            return

        if event_type == "chunk":
            key = active_by_agent.get(ev.get("agent", ""))
            if key and key in active_steps:
                active_steps[key]["parts"].append(ev.get("text", ""))
            return

        if event_type == "result":
            agent = ev.get("agent", "unknown")
            role = ev.get("role", "result")
            key = (agent, role)
            step = active_steps.pop(key, None)
            if active_by_agent.get(agent) == key:
                active_by_agent.pop(agent, None)
            await persist_step(
                agent_type=agent,
                role=role,
                response=ev.get("text", ""),
                input_tokens=ev.get("input_tokens", 0),
                output_tokens=ev.get("output_tokens", 0),
                cost_usd=ev.get("cost_usd", 0.0),
                started_at=step["started_at"] if step else now,
                finished_at=now,
            )
            return

        if event_type == "stream_end":
            agent = ev.get("agent", "unknown")
            key = active_by_agent.pop(agent, None)
            step = active_steps.pop(key, None) if key else None
            if step:
                await persist_step(
                    agent_type=agent,
                    role=key[1],
                    response="".join(step["parts"]),
                    error=ev.get("error") or step.get("error"),
                    input_tokens=ev.get("input_tokens", 0),
                    output_tokens=ev.get("output_tokens", 0),
                    cost_usd=ev.get("cost_usd", 0.0),
                    started_at=step["started_at"],
                    finished_at=now,
                )
            return

        if event_type == "error":
            await persist_step(
                agent_type=ev.get("agent", "system"),
                role="error",
                response=ev.get("text", ""),
                error=ev.get("text", ""),
                started_at=now,
                finished_at=now,
            )

    try:
        if req.mode == "compare":
            mode = CompareMode()
        elif req.mode == "review":
            mode = ReviewMode()
        elif req.mode == "debate":
            from cchwc.orchestrator.modes.debate import DebateMode
            mode = DebateMode()
        else:
            raise ValueError(f"Unknown mode: {req.mode}")

        async def emit(event_data: str):
            await record_event(event_data)
            if queue:
                await queue.put(event_data)

        result = await mode.execute(
            prompt=req.prompt,
            cwd=req.cwd,
            config=req.config,
            run_id=run_id,
            emit=emit,
        )

        async with session_factory() as db:
            run = await db.get(OrchestrationRun, run_id)
            if run:
                run.status = "completed"
                run.finished_at = datetime.now()
                run.result_summary = result.get("summary", "")
                run.total_tokens = result.get("total_tokens", 0)
                run.total_cost_usd = result.get("total_cost_usd", 0.0)
                await db.commit()

    except asyncio.CancelledError:
        async with session_factory() as db:
            run = await db.get(OrchestrationRun, run_id)
            if run and run.status == "running":
                run.status = "stopped"
                run.finished_at = datetime.now()
                run.result_summary = "Stopped by user"
                await db.commit()

    except Exception as e:
        if queue:
            event_data = json.dumps({"type": "error", "text": str(e)})
            await record_event(event_data)
            await queue.put(event_data)
        async with session_factory() as db:
            run = await db.get(OrchestrationRun, run_id)
            if run:
                run.status = "failed"
                run.finished_at = datetime.now()
                run.result_summary = str(e)
                await db.commit()
    finally:
        if queue:
            await queue.put(None)
        _run_events.pop(run_id, None)
        _run_tasks.pop(run_id, None)


def _duration_sec(started_at: datetime, finished_at: datetime | None) -> float | None:
    if not finished_at:
        return None
    return max((finished_at - started_at).total_seconds(), 0.0)


def _load_json(value: str | None) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def status_badge_class(status: str) -> str:
    return {
        "completed": "bg-green-50 text-green-700 border-green-200",
        "running": "bg-amber-50 text-amber-700 border-amber-200",
        "failed": "bg-red-50 text-red-700 border-red-200",
        "stopped": "bg-gray-50 text-gray-600 border-gray-200",
    }.get(status, "bg-gray-50 text-gray-600 border-gray-200")


def status_label(status: str) -> str:
    return {
        "completed": "완료",
        "running": "실행 중",
        "failed": "실패",
        "stopped": "중지",
    }.get(status, status)


def mode_label(mode: str) -> str:
    return {
        "compare": "Compare",
        "review": "Review",
        "debate": "Debate",
    }.get(mode, mode)


def compact_text(value: str | None, limit: int = 120) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
