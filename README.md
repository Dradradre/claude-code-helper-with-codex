# cchwc (claude-code-helper-with-codex)

Claude Code와 Codex CLI 세션을 통합 관리하고, 두 에이전트를 협업/대결시키는 로컬 도구.

## 설치

```bash
git clone <repo-url>
cd cladue-code-helper-with-codex
uv sync
```

## 사용법

```bash
# 환경 점검
uv run cchwc doctor

# 웹 서버 시작
uv run cchwc serve

# 오케스트레이션
uv run cchwc compare "프롬프트"
uv run cchwc review "프롬프트"
uv run cchwc debate "프롬프트"
```

## 개발

```bash
uv sync
uv run pytest
uv run ruff check src tests
```
