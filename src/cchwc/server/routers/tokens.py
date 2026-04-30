from collections import defaultdict
from datetime import date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cchwc.core.models import Message, OrchestrationRun, OrchestrationStep, Project, Session
from cchwc.server.deps import get_db
from cchwc.server.usage_status import get_cli_limit_status

router = APIRouter()

_ORCH_AGENT_TYPES = {"claude", "codex"}


@router.get("/daily")
async def daily_tokens(
    days: int = 30,
    agent_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    date_col = func.date(Session.started_at)
    session_q = (
        select(
            date_col.label("date"),
            Session.agent_type,
            func.sum(Session.total_input_tokens).label("input_tokens"),
            func.sum(Session.total_output_tokens).label("output_tokens"),
            func.sum(Session.total_cache_read_tokens).label("cache_read_tokens"),
            func.sum(Session.total_cache_creation_tokens).label("cache_creation_tokens"),
        )
        .group_by(date_col, Session.agent_type)
        .order_by(date_col.desc())
        .limit(days * 2)
    )
    if agent_type:
        session_q = session_q.where(Session.agent_type == agent_type)

    orch_date_col = func.date(OrchestrationStep.started_at)
    orch_q = (
        select(
            orch_date_col.label("date"),
            OrchestrationStep.agent_type,
            func.sum(OrchestrationStep.input_tokens).label("input_tokens"),
            func.sum(OrchestrationStep.output_tokens).label("output_tokens"),
        )
        .where(OrchestrationStep.agent_type.in_(_ORCH_AGENT_TYPES))
        .group_by(orch_date_col, OrchestrationStep.agent_type)
        .order_by(orch_date_col.desc())
        .limit(days * 2)
    )
    if agent_type:
        orch_q = orch_q.where(OrchestrationStep.agent_type == agent_type)

    session_rows = (await db.execute(session_q)).all()
    orch_rows = (await db.execute(orch_q)).all()

    def _zero() -> dict:
        return {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_creation_tokens": 0}

    # Merge by (date, agent_type)
    merged: dict[tuple, dict] = defaultdict(_zero)
    for r in session_rows:
        key = (str(r.date), r.agent_type)
        merged[key]["input_tokens"] += r.input_tokens or 0
        merged[key]["output_tokens"] += r.output_tokens or 0
        merged[key]["cache_read_tokens"] += r.cache_read_tokens or 0
        merged[key]["cache_creation_tokens"] += r.cache_creation_tokens or 0
    for r in orch_rows:
        key = (str(r.date), r.agent_type)
        merged[key]["input_tokens"] += r.input_tokens or 0
        merged[key]["output_tokens"] += r.output_tokens or 0

    return [
        {
            "date": date,
            "agent_type": atype,
            "input_tokens": v["input_tokens"],
            "output_tokens": v["output_tokens"],
            "cache_read_tokens": v["cache_read_tokens"],
            "cache_creation_tokens": v["cache_creation_tokens"],
        }
        for (date, atype), v in sorted(merged.items(), reverse=True)
    ]


@router.get("/by-model")
async def tokens_by_model(db: AsyncSession = Depends(get_db)):
    # Claude: per-message token counts are stored accurately
    claude_q = (
        select(
            Message.model,
            func.sum(case((Message.input_tokens.is_not(None), Message.input_tokens), else_=0)).label("input_tokens"),
            func.sum(case((Message.output_tokens.is_not(None), Message.output_tokens), else_=0)).label("output_tokens"),
            func.count(Message.id).label("message_count"),
        )
        .join(Session, Session.id == Message.session_id)
        .where(Message.model.is_not(None))
        .where(Session.agent_type != "codex")
        .group_by(Message.model)
    )

    # Codex: only session-level totals exist; assign them to the session's model
    # (determined by the first model seen in messages for that session)
    codex_model_subq = (
        select(
            Message.session_id,
            func.min(Message.model).label("model"),
        )
        .join(Session, Session.id == Message.session_id)
        .where(Message.model.is_not(None))
        .where(Session.agent_type == "codex")
        .group_by(Message.session_id)
        .subquery()
    )
    codex_q = (
        select(
            codex_model_subq.c.model,
            func.sum(Session.total_input_tokens).label("input_tokens"),
            func.sum(Session.total_output_tokens).label("output_tokens"),
            func.count(Session.id).label("message_count"),
        )
        .join(codex_model_subq, codex_model_subq.c.session_id == Session.id)
        .where(Session.agent_type == "codex")
        .group_by(codex_model_subq.c.model)
    )

    claude_rows = (await db.execute(claude_q)).all()
    codex_rows = (await db.execute(codex_q)).all()

    return [
        {
            "model": r.model,
            "input_tokens": r.input_tokens or 0,
            "output_tokens": r.output_tokens or 0,
            "message_count": r.message_count,
        }
        for r in (*claude_rows, *codex_rows)
    ]


@router.get("/by-project")
async def tokens_by_project(db: AsyncSession = Depends(get_db)):
    query = (
        select(
            Project.display_name,
            Project.cwd,
            func.sum(Session.total_input_tokens).label("input_tokens"),
            func.sum(Session.total_output_tokens).label("output_tokens"),
            func.sum(Session.total_cache_read_tokens).label("cache_read_tokens"),
            func.count(Session.id).label("session_count"),
        )
        .join(Session, Session.project_id == Project.id)
        .group_by(Project.id)
        .order_by(func.sum(Session.total_input_tokens + Session.total_output_tokens).desc())
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "project": r.display_name,
            "cwd": r.cwd,
            "input_tokens": r.input_tokens or 0,
            "output_tokens": r.output_tokens or 0,
            "cache_read_tokens": r.cache_read_tokens or 0,
            "session_count": r.session_count,
        }
        for r in rows
    ]


@router.get("/summary")
async def token_summary(db: AsyncSession = Depends(get_db)):
    session_row = (
        await db.execute(
            select(
                func.sum(Session.total_input_tokens).label("total_input"),
                func.sum(Session.total_output_tokens).label("total_output"),
                func.sum(Session.total_cache_read_tokens).label("total_cache_read"),
                func.sum(Session.total_cache_creation_tokens).label("total_cache_creation"),
                func.count(Session.id).label("total_sessions"),
            )
        )
    ).one()

    orch_row = (
        await db.execute(
            select(
                func.sum(OrchestrationStep.input_tokens).label("total_input"),
                func.sum(OrchestrationStep.output_tokens).label("total_output"),
            ).where(OrchestrationStep.agent_type.in_(_ORCH_AGENT_TYPES))
        )
    ).one()

    return {
        "total_input_tokens": (session_row.total_input or 0) + (orch_row.total_input or 0),
        "total_output_tokens": (session_row.total_output or 0) + (orch_row.total_output or 0),
        "total_cache_read_tokens": session_row.total_cache_read or 0,
        "total_cache_creation_tokens": session_row.total_cache_creation or 0,
        "total_sessions": session_row.total_sessions,
    }


@router.get("/live")
async def live_usage(refresh_status: bool = False, db: AsyncSession = Depends(get_db)):
    today = date.today().isoformat()
    agents = {
        "claude": _empty_live_agent(),
        "codex": _empty_live_agent(),
    }

    session_rows = (
        await db.execute(
            select(
                Session.agent_type,
                func.sum(Session.total_input_tokens).label("input_tokens"),
                func.sum(Session.total_output_tokens).label("output_tokens"),
                func.sum(Session.total_cache_read_tokens).label("cache_read_tokens"),
                func.sum(Session.total_cache_creation_tokens).label("cache_creation_tokens"),
                func.count(Session.id).label("session_count"),
                func.max(Session.last_message_at).label("last_activity_at"),
            )
            .where(Session.agent_type.in_(agents.keys()))
            .where(func.date(Session.last_message_at) == today)
            .group_by(Session.agent_type)
        )
    ).all()

    orch_rows = (
        await db.execute(
            select(
                OrchestrationStep.agent_type,
                func.sum(OrchestrationStep.input_tokens).label("input_tokens"),
                func.sum(OrchestrationStep.output_tokens).label("output_tokens"),
                func.sum(OrchestrationStep.cost_usd).label("cost_usd"),
                func.count(OrchestrationStep.id).label("step_count"),
                func.max(OrchestrationStep.finished_at).label("last_activity_at"),
            )
            .where(OrchestrationStep.agent_type.in_(agents.keys()))
            .where(func.date(OrchestrationStep.started_at) == today)
            .group_by(OrchestrationStep.agent_type)
        )
    ).all()

    running_runs = (
        await db.execute(
            select(func.count(OrchestrationRun.id)).where(OrchestrationRun.status == "running")
        )
    ).scalar() or 0

    for row in session_rows:
        usage = agents[row.agent_type]
        usage["input_tokens"] += row.input_tokens or 0
        usage["output_tokens"] += row.output_tokens or 0
        usage["cache_read_tokens"] += row.cache_read_tokens or 0
        usage["cache_creation_tokens"] += row.cache_creation_tokens or 0
        usage["session_count"] += row.session_count or 0
        usage["last_activity_at"] = _latest_iso(usage["last_activity_at"], row.last_activity_at)

    for row in orch_rows:
        usage = agents[row.agent_type]
        usage["input_tokens"] += row.input_tokens or 0
        usage["output_tokens"] += row.output_tokens or 0
        usage["cost_usd"] += row.cost_usd or 0.0
        usage["orchestration_step_count"] += row.step_count or 0
        usage["last_activity_at"] = _latest_iso(usage["last_activity_at"], row.last_activity_at)

    total_tokens = 0
    for usage in agents.values():
        usage["total_tokens"] = (
            usage["input_tokens"]
            + usage["output_tokens"]
            + usage["cache_read_tokens"]
            + usage["cache_creation_tokens"]
        )
        total_tokens += usage["total_tokens"]

    return {
        "as_of": datetime.now().isoformat(),
        "date": today,
        "running_orchestrations": running_runs,
        "total_tokens": total_tokens,
        "agents": agents,
        "limits": await get_cli_limit_status(force_refresh=refresh_status),
    }


@router.get("/status")
async def cli_limit_status(refresh: bool = False):
    return await get_cli_limit_status(force_refresh=refresh)


def _empty_live_agent() -> dict:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "session_count": 0,
        "orchestration_step_count": 0,
        "last_activity_at": None,
    }


def _latest_iso(current: str | None, candidate: datetime | None) -> str | None:
    if candidate is None:
        return current
    candidate_iso = candidate.isoformat()
    if current is None or candidate_iso > current:
        return candidate_iso
    return current
