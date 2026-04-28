"""cchwc 개발 서버. python run.py 로 실행."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from cchwc.server_runner import serve_all

if __name__ == "__main__":
    asyncio.run(serve_all(open_browser="--open" in sys.argv))
