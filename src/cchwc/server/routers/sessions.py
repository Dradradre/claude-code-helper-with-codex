from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cchwc.core.models import Message, Project, Session
from cchwc.server.deps import get_db

router = APIRouter()


@router.get("")
async def list_sessions(
    agent_type: str | None = None,
    project: str | None = None,
    offset: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    query = select(Session).join(Project)
    if agent_type:
        query = query.where(Session.agent_type == agent_type)
    if project:
        query = query.where(Project.cwd.contains(project))
    query = query.order_by(Session.last_message_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    sessions = result.scalars().all()

    count_query = select(func.count(Session.id))
    if agent_type:
        count_query = count_query.where(Session.agent_type == agent_type)
    total = (await db.execute(count_query)).scalar() or 0

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "id": s.id,
                "agent_type": s.agent_type,
                "external_id": s.external_id,
                "project_id": s.project_id,
                "started_at": s.started_at.isoformat(),
                "last_message_at": s.last_message_at.isoformat(),
                "message_count": s.message_count,
                "total_input_tokens": s.total_input_tokens,
                "total_output_tokens": s.total_output_tokens,
                "total_cache_read_tokens": s.total_cache_read_tokens,
                "total_cache_creation_tokens": s.total_cache_creation_tokens,
                "summary": s.summary,
            }
            for s in sessions
        ],
    }


@router.get("/{session_id}")
async def get_session(session_id: int, db: AsyncSession = Depends(get_db)):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    project = await db.get(Project, session.project_id)
    messages = (
        (await db.execute(select(Message).where(Message.session_id == session_id).order_by(Message.sequence)))
        .scalars()
        .all()
    )

    return {
        "id": session.id,
        "agent_type": session.agent_type,
        "external_id": session.external_id,
        "project": {"id": project.id, "cwd": project.cwd, "display_name": project.display_name} if project else None,
        "started_at": session.started_at.isoformat(),
        "last_message_at": session.last_message_at.isoformat(),
        "message_count": session.message_count,
        "total_input_tokens": session.total_input_tokens,
        "total_output_tokens": session.total_output_tokens,
        "summary": session.summary,
        "messages": [
            {
                "id": m.id,
                "sequence": m.sequence,
                "role": m.role,
                "content_text": m.content_text,
                "timestamp": m.timestamp.isoformat(),
                "model": m.model,
                "input_tokens": m.input_tokens,
                "output_tokens": m.output_tokens,
            }
            for m in messages
        ],
    }
