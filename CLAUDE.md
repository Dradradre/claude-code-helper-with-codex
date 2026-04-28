# CLAUDE.md — cchwc 작업 가이드

## 프로젝트 개요

Claude Code + Codex CLI 세션 통합 관리 및 에이전트 오케스트레이션 도구.
상세 계획은 `plan.md` 참고.

## 기술 스택

- Python 3.11+ / FastAPI / SQLite(WAL) / SQLAlchemy 2.x async
- 프론트: HTMX + Jinja2 + Tailwind(CDN) + Chart.js(CDN)
- 패키지: uv / CLI: Typer / 테스트: pytest / 린트: ruff

## 개발 명령어

```bash
uv sync                          # 의존성 설치
uv run pytest                    # 테스트
uv run ruff check src tests      # 린트
uv run ruff format src tests     # 포맷
uv run cchwc doctor              # 환경 점검
uv run cchwc serve               # 웹 서버
```

## 작업 규칙

- plan.md는 수정하지 않음 (별도 PR로 분리)
- Phase별 작업 브랜치: `phase-N-<short-description>`
- 모든 테스트 통과 + ruff check 통과 후 PR
- LLM 직접 호출 금지 — 모든 LLM 작업은 `claude -p` / `codex exec` 위임
- SQLite WAL 모드 + busy_timeout=5000
- async 코드는 asyncio.TaskGroup 사용 (Python 3.11+)

## 디렉토리 구조

- `src/cchwc/` — 메인 패키지
  - `config.py` — pydantic-settings 기반 설정
  - `cli.py` — Typer CLI 엔트리포인트
  - `core/` — DB, ORM 모델, Pydantic DTO, 경로 유틸
  - `adapters/` — Claude/Codex 세션 어댑터
  - `indexer/` — 풀스캔 + 증분 watch
  - `orchestrator/` — subprocess 래퍼 + 3가지 모드
  - `server/` — FastAPI 앱 + 라우터 + 템플릿
  - `daemon/` — 백그라운드 watcher
- `tests/` — unit / integration / e2e + fixtures
