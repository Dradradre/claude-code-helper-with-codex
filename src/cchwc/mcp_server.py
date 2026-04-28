"""MCP 서버 — Claude Code에서 compare/review/debate를 네이티브 tool call로 사용."""

import json

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "cchwc",
    description="Claude + Codex 에이전트 오케스트레이션 (compare / review / debate)",
)


def _make_emitter(chunks: list[str]):
    async def emit(data: str) -> None:
        ev = json.loads(data)
        t = ev.get("type")
        if t == "result":
            agent = ev.get("agent", "").upper()
            role = ev.get("role", "")
            text = ev.get("text", "")
            chunks.append(f"## [{agent}] {role}\n\n{text}")
        elif t == "status":
            chunks.append(f"> {ev.get('text', '')}")
        elif t == "error":
            chunks.append(f"**Error ({ev.get('agent', '')}):** {ev.get('text', '')}")
    return emit


@mcp.tool()
async def compare(prompt: str, cwd: str = ".") -> str:
    """Claude와 Codex에 같은 프롬프트를 동시에 보내고 두 응답을 나란히 반환합니다.

    Args:
        prompt: 두 에이전트에 전달할 프롬프트
        cwd: 작업 디렉토리 (기본: 현재 디렉토리)
    """
    from cchwc.orchestrator.modes.compare import CompareMode

    chunks: list[str] = []
    await CompareMode().execute(
        prompt=prompt, cwd=cwd, config={}, run_id=0, emit=_make_emitter(chunks)
    )
    return "\n\n---\n\n".join(chunks) if chunks else "(출력 없음)"


@mcp.tool()
async def review(
    prompt: str,
    implementer: str = "claude",
    reviewer: str = "codex",
    cwd: str = ".",
) -> str:
    """한 에이전트가 구현하고 다른 에이전트가 리뷰합니다.

    Args:
        prompt: 구현할 내용
        implementer: 구현 담당 에이전트 ("claude" | "codex")
        reviewer: 리뷰 담당 에이전트 ("claude" | "codex")
        cwd: 작업 디렉토리
    """
    from cchwc.orchestrator.modes.review import ReviewMode

    chunks: list[str] = []
    await ReviewMode().execute(
        prompt=prompt,
        cwd=cwd,
        config={"implementer": implementer, "reviewer": reviewer},
        run_id=0,
        emit=_make_emitter(chunks),
    )
    return "\n\n---\n\n".join(chunks) if chunks else "(출력 없음)"


@mcp.tool()
async def debate(
    topic: str,
    max_rounds: int = 3,
    cwd: str = ".",
) -> str:
    """두 에이전트가 주제를 놓고 토론하고 judge가 수렴 여부를 판정합니다.

    Args:
        topic: 토론 주제 또는 설계 결정 사항
        max_rounds: 최대 토론 라운드 수
        cwd: 작업 디렉토리
    """
    from cchwc.orchestrator.modes.debate import DebateMode

    chunks: list[str] = []
    await DebateMode().execute(
        prompt=topic,
        cwd=cwd,
        config={"max_rounds": max_rounds},
        run_id=0,
        emit=_make_emitter(chunks),
    )
    return "\n\n---\n\n".join(chunks) if chunks else "(출력 없음)"


def run() -> None:
    mcp.run()
