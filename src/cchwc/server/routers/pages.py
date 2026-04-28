from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cchwc.core.models import Message, Project, Session
from cchwc.server.deps import get_db

router = APIRouter()

PAGE_SIZE = 50


@router.get("/")
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    templates = request.app.state.templates

    total_sessions = (await db.execute(select(func.count(Session.id)))).scalar() or 0
    total_projects = (await db.execute(select(func.count(Project.id)))).scalar() or 0
    total_messages = (await db.execute(select(func.count(Message.id)))).scalar() or 0
    total_input = (await db.execute(select(func.sum(Session.total_input_tokens)))).scalar() or 0
    total_output = (await db.execute(select(func.sum(Session.total_output_tokens)))).scalar() or 0

    recent_sessions = (
        (await db.execute(select(Session).join(Project).order_by(Session.last_message_at.desc()).limit(10)))
        .scalars()
        .all()
    )

    sessions_data = []
    for s in recent_sessions:
        p = await db.get(Project, s.project_id)
        sessions_data.append({"session": s, "project": p})

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "total_sessions": total_sessions,
            "total_projects": total_projects,
            "total_messages": total_messages,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "recent_sessions": sessions_data,
        },
    )


@router.get("/sessions")
async def sessions_page(request: Request, db: AsyncSession = Depends(get_db)):
    templates = request.app.state.templates
    return templates.TemplateResponse(request=request, name="sessions/list.html")


@router.get("/sessions/partial")
async def sessions_partial(
    request: Request,
    agent_type: str = "",
    q: str = "",
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    templates = request.app.state.templates

    query = select(Session).join(Project)
    if agent_type:
        query = query.where(Session.agent_type == agent_type)

    if q:
        from sqlalchemy import exists
        query = query.where(
            exists(
                select(Message.id).where(
                    Message.session_id == Session.id,
                    Message.content_text.contains(q),
                )
            )
        )

    total_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(total_query)).scalar() or 0

    query = query.order_by(Session.last_message_at.desc()).offset(offset).limit(PAGE_SIZE)
    sessions = (await db.execute(query)).scalars().all()

    items = []
    for s in sessions:
        p = await db.get(Project, s.project_id)
        items.append({"session": s, "project": p})

    next_offset = offset + PAGE_SIZE
    return templates.TemplateResponse(
        request=request,
        name="sessions/partial_rows.html",
        context={
            "items": items,
            "has_more": next_offset < total,
            "next_offset": next_offset,
            "agent_type": agent_type,
            "q": q,
        },
    )


@router.get("/sessions/{session_id}")
async def session_detail_page(request: Request, session_id: int, db: AsyncSession = Depends(get_db)):
    templates = request.app.state.templates
    session = await db.get(Session, session_id)
    if not session:
        return templates.TemplateResponse(request=request, name="404.html", status_code=404)

    project = await db.get(Project, session.project_id)
    messages = (
        (await db.execute(select(Message).where(Message.session_id == session_id).order_by(Message.sequence)))
        .scalars()
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="sessions/detail.html",
        context={"session": session, "project": project, "messages": messages},
    )


@router.get("/tokens")
async def tokens_page(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request=request, name="tokens/dashboard.html")


@router.get("/orchestrate")
async def orchestrate_page(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request=request, name="orchestrate/index.html")
