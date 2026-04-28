"""cchwc 개발 서버. python run.py 로 실행."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import uvicorn

from cchwc.config import Settings
from cchwc.core.db import get_engine
from cchwc.core.models import Base
from cchwc.server.app import create_app


async def init_db():
    settings = Settings()
    engine = get_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    asyncio.run(init_db())
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=7878, log_level="info")
