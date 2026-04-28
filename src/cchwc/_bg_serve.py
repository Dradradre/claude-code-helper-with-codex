"""python -m cchwc._bg_serve — 백그라운드 서버 진입점."""

import asyncio

from cchwc.server_runner import serve_all

if __name__ == "__main__":
    asyncio.run(serve_all())
