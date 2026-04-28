from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cchwc.core.models import Base, Message, Project, Session
from cchwc.core.schemas import ParsedMessage, ParsedSession, TokenUsage
from cchwc.indexer.parser import upsert_parsed_session


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.mark.asyncio
async def test_upsert_creates_project_and_session(db: AsyncSession):
    parsed = ParsedSession(
        agent_type="claude",
        external_id="sess-001",
        file_path="/tmp/test.jsonl",
        cwd="/home/user/project",
        started_at=datetime(2026, 4, 20, 10, 0),
        last_message_at=datetime(2026, 4, 20, 10, 5),
        messages=[
            ParsedMessage(
                sequence=0,
                role="user",
                content_text="hello",
                content_json='{"role":"user","content":"hello"}',
                timestamp=datetime(2026, 4, 20, 10, 0),
            ),
            ParsedMessage(
                sequence=1,
                role="assistant",
                content_text="hi there",
                content_json='{"role":"assistant","content":"hi there"}',
                timestamp=datetime(2026, 4, 20, 10, 5),
                input_tokens=100,
                output_tokens=20,
                model="claude-sonnet-4-6",
            ),
        ],
        total_usage=TokenUsage(input_tokens=100, output_tokens=20),
    )

    session = await upsert_parsed_session(db, parsed)
    await db.commit()

    assert session.id is not None
    assert session.message_count == 2
    assert session.total_input_tokens == 100

    projects = (await db.execute(select(Project))).scalars().all()
    assert len(projects) == 1
    assert projects[0].cwd == "/home/user/project"

    messages = (await db.execute(select(Message).where(Message.session_id == session.id))).scalars().all()
    assert len(messages) == 2


@pytest.mark.asyncio
async def test_upsert_updates_existing_session(db: AsyncSession):
    parsed1 = ParsedSession(
        agent_type="claude",
        external_id="sess-002",
        file_path="/tmp/test2.jsonl",
        cwd="/home/user/project",
        started_at=datetime(2026, 4, 20, 10, 0),
        last_message_at=datetime(2026, 4, 20, 10, 5),
        messages=[
            ParsedMessage(
                sequence=0,
                role="user",
                content_text="msg1",
                content_json="{}",
                timestamp=datetime(2026, 4, 20, 10, 0),
            ),
        ],
        total_usage=TokenUsage(input_tokens=50, output_tokens=10),
    )

    await upsert_parsed_session(db, parsed1)
    await db.commit()

    parsed2 = ParsedSession(
        agent_type="claude",
        external_id="sess-002",
        file_path="/tmp/test2.jsonl",
        cwd="/home/user/project",
        started_at=datetime(2026, 4, 20, 10, 0),
        last_message_at=datetime(2026, 4, 20, 10, 10),
        messages=[
            ParsedMessage(
                sequence=0,
                role="user",
                content_text="msg1",
                content_json="{}",
                timestamp=datetime(2026, 4, 20, 10, 0),
            ),
            ParsedMessage(
                sequence=1,
                role="assistant",
                content_text="msg2",
                content_json="{}",
                timestamp=datetime(2026, 4, 20, 10, 10),
                input_tokens=100,
                output_tokens=30,
            ),
        ],
        total_usage=TokenUsage(input_tokens=100, output_tokens=30),
    )

    session = await upsert_parsed_session(db, parsed2)
    await db.commit()

    assert session.message_count == 2
    assert session.total_input_tokens == 100

    sessions = (await db.execute(select(Session))).scalars().all()
    assert len(sessions) == 1
