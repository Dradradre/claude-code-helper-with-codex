import traceback
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from cchwc.server.routers import fs, orchestrate, pages, search, sessions, tokens

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="cchwc", version="0.1.0", debug=True)

    @app.exception_handler(Exception)
    async def debug_exception_handler(request: Request, exc: Exception):
        tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
        return PlainTextResponse("".join(tb), status_code=500)

    app.include_router(pages.router)
    app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
    app.include_router(tokens.router, prefix="/api/tokens", tags=["tokens"])
    app.include_router(search.router, prefix="/api/search", tags=["search"])
    app.include_router(orchestrate.router, prefix="/api/orchestrate", tags=["orchestrate"])
    app.include_router(fs.router, prefix="/api/fs", tags=["fs"])

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.templates = templates

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
