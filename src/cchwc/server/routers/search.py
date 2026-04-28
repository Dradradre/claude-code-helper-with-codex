from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cchwc.core.models import Message, Project, Session
from cchwc.server.deps import get_db

router = APIRouter()


@router.get("")
async def search_messages(
    q: str = Query(..., min_length=1),
    project: str | None = None,
    agent_type: str | None = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Message, Session.external_id, Session.agent_type)
        .join(Session, Message.session_id == Session.id)
        .where(Message.content_text.contains(q))
        .order_by(Message.timestamp.desc())
        .limit(limit)
    )

    if agent_type:
        query = query.where(Session.agent_type == agent_type)
    if project:
        query = query.join(Project, Session.project_id == Project.id).where(Project.cwd.contains(project))

    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "message_id": msg.id,
            "session_id": msg.session_id,
            "session_external_id": external_id,
            "agent_type": a_type,
            "role": msg.role,
            "content_text": msg.content_text[:500] if msg.content_text else None,
            "timestamp": msg.timestamp.isoformat(),
        }
        for msg, external_id, a_type in rows
    ]
