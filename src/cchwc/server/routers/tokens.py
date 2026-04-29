from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cchwc.core.models import Message, Project, Session
from cchwc.server.deps import get_db

router = APIRouter()


@router.get("/daily")
async def daily_tokens(
    days: int = 30,
    agent_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    date_col = func.date(Session.started_at)
    query = (
        select(
            date_col.label("date"),
            Session.agent_type,
            func.sum(Session.total_input_tokens).label("input_tokens"),
            func.sum(Session.total_output_tokens).label("output_tokens"),
            func.sum(Session.total_cache_read_tokens).label("cache_read_tokens"),
            func.sum(Session.total_cache_creation_tokens).label("cache_creation_tokens"),
            func.count(Session.id).label("session_count"),
        )
        .group_by(date_col, Session.agent_type)
        .order_by(date_col.desc())
        .limit(days * 2)
    )
    if agent_type:
        query = query.where(Session.agent_type == agent_type)

    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "date": str(r.date),
            "agent_type": r.agent_type,
            "input_tokens": r.input_tokens or 0,
            "output_tokens": r.output_tokens or 0,
            "cache_read_tokens": r.cache_read_tokens or 0,
            "cache_creation_tokens": r.cache_creation_tokens or 0,
            "session_count": r.session_count,
        }
        for r in rows
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
    result = await db.execute(
        select(
            func.sum(Session.total_input_tokens).label("total_input"),
            func.sum(Session.total_output_tokens).label("total_output"),
            func.sum(Session.total_cache_read_tokens).label("total_cache_read"),
            func.sum(Session.total_cache_creation_tokens).label("total_cache_creation"),
            func.count(Session.id).label("total_sessions"),
        )
    )
    row = result.one()
    return {
        "total_input_tokens": row.total_input or 0,
        "total_output_tokens": row.total_output or 0,
        "total_cache_read_tokens": row.total_cache_read or 0,
        "total_cache_creation_tokens": row.total_cache_creation or 0,
        "total_sessions": row.total_sessions,
    }
