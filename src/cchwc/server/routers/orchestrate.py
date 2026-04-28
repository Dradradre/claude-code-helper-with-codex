import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cchwc.core.models import OrchestrationRun, OrchestrationStep
from cchwc.server.deps import get_db

router = APIRouter()

_run_events: dict[int, asyncio.Queue] = {}


class RunRequest(BaseModel):
    mode: str
    prompt: str
    cwd: str = "."
    config: dict = {}


@router.post("/runs")
async def create_run(req: RunRequest, db: AsyncSession = Depends(get_db)):
    import json

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

    asyncio.create_task(_execute_run(run.id, req))

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
        "status": run.status,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "total_tokens": run.total_tokens,
        "total_cost_usd": run.total_cost_usd,
        "result_summary": run.result_summary,
        "steps": [
            {
                "id": s.id,
                "sequence": s.sequence,
                "agent_type": s.agent_type,
                "role": s.role,
                "prompt": s.prompt[:200],
                "response": s.response[:500] if s.response else None,
                "input_tokens": s.input_tokens,
                "output_tokens": s.output_tokens,
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
        await queue.put(None)

    return {"id": run_id, "status": "stopped"}


async def _execute_run(run_id: int, req: RunRequest) -> None:
    from cchwc.core.db import get_session_factory
    from cchwc.orchestrator.modes.compare import CompareMode
    from cchwc.orchestrator.modes.review import ReviewMode

    session_factory = get_session_factory()
    queue = _run_events.get(run_id)

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

    except Exception as e:
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
