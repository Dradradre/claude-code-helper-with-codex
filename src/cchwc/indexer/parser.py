from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from cchwc.core.models import Message, Project, Session
from cchwc.core.schemas import ParsedSession


def _make_naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


async def upsert_parsed_session(db: AsyncSession, parsed: ParsedSession) -> Session:
    from sqlalchemy import select

    started_at = _make_naive(parsed.started_at)
    last_message_at = _make_naive(parsed.last_message_at)

    cwd = parsed.cwd or "unknown"
    project = (await db.execute(select(Project).where(Project.cwd == cwd))).scalar_one_or_none()
    if project is None:
        display = cwd.rsplit("/", 1)[-1] if "/" in cwd else cwd.rsplit("\\", 1)[-1] if "\\" in cwd else cwd
        project = Project(
            cwd=cwd,
            display_name=display,
            machine_id="",
            first_seen_at=started_at,
            last_active_at=last_message_at,
        )
        db.add(project)
        await db.flush()
    else:
        existing_last = _make_naive(project.last_active_at) if project.last_active_at else datetime.min
        if last_message_at > existing_last:
            project.last_active_at = last_message_at

    session = (
        await db.execute(
            select(Session).where(Session.agent_type == parsed.agent_type, Session.external_id == parsed.external_id)
        )
    ).scalar_one_or_none()

    if session is None:
        session = Session(
            project_id=project.id,
            agent_type=parsed.agent_type,
            external_id=parsed.external_id,
            file_path=parsed.file_path,
            file_mtime=datetime.now().timestamp(),
            file_size=0,
            started_at=started_at,
            last_message_at=last_message_at,
            message_count=len(parsed.messages),
            total_input_tokens=parsed.total_usage.input_tokens,
            total_output_tokens=parsed.total_usage.output_tokens,
            total_cache_read_tokens=parsed.total_usage.cache_read_tokens,
            total_cache_creation_tokens=parsed.total_usage.cache_creation_tokens,
        )
        db.add(session)
        await db.flush()
    else:
        session.file_mtime = datetime.now().timestamp()
        session.last_message_at = last_message_at
        session.message_count = len(parsed.messages)
        session.total_input_tokens = parsed.total_usage.input_tokens
        session.total_output_tokens = parsed.total_usage.output_tokens
        session.total_cache_read_tokens = parsed.total_usage.cache_read_tokens
        session.total_cache_creation_tokens = parsed.total_usage.cache_creation_tokens

        existing_msgs = (await db.execute(select(Message).where(Message.session_id == session.id))).scalars().all()
        for msg in existing_msgs:
            await db.delete(msg)

    for pm in parsed.messages:
        msg = Message(
            session_id=session.id,
            sequence=pm.sequence,
            role=pm.role,
            content_text=pm.content_text,
            content_json=pm.content_json,
            timestamp=_make_naive(pm.timestamp),
            input_tokens=pm.input_tokens,
            output_tokens=pm.output_tokens,
            cache_read_tokens=pm.cache_read_tokens,
            cache_creation_tokens=pm.cache_creation_tokens,
            model=pm.model,
        )
        db.add(msg)

    return session
