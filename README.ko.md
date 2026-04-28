<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0f0f0f,100:1a1a2e&height=180&section=header&text=cchwc&fontSize=72&fontColor=ffffff&fontAlignY=40&desc=claude-code-helper-with-codex&descColor=888888&descAlignY=62&descSize=16" width="100%">



Claude Code + Codex CLI를 통합 관리하고 두 에이전트를 협업·대결시키는 로컬 도구

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![uv](https://img.shields.io/badge/uv-package%20manager-DE5FE9)](https://docs.astral.sh/uv/)

[**English**](README.md) · [빠른 시작](#-빠른-시작) · [기능](#-기능) · [아키텍처](#-아키텍처) · [기여하기](#-기여하기)

</div>

---

## cchwc란?

cchwc는 Claude Code와 Codex CLI를 매일 사용하는 개발자를 위한 **로컬 전용 데스크탑 도구**입니다. 두 에이전트가 만들어내는 세션을 모두 인덱싱하고, 토큰 사용량을 시각화하며, 두 에이전트를 **구조화된 협업 모드**로 맞붙일 수 있습니다.

> **클라우드 없음. API 키 불필요. 동기화 서비스 없음.**  
> 모든 LLM 호출은 이미 설치된 CLI를 통해 이루어집니다.

---

## ✨ 기능

<table>
<tr>
<td width="50%">

### 📚 세션 허브
모든 프로젝트의 Claude Code · Codex 세션을 한 곳에서 탐색, 검색, 요약합니다.

- 전체 메시지 풀텍스트 검색
- 프로젝트/에이전트별 필터
- 세션별 토큰 사용량 분석

</td>
<td width="50%">

### 📊 토큰 대시보드
비용이 어디서 발생하는지 정확히 파악합니다.

- 일별 / 모델별 / 프로젝트별 집계
- 캐시 읽기 vs 생성 분리 표시
- Chart.js 시각화 (빌드 스텝 없음)

</td>
</tr>
<tr>
<td>

### 🔍 세션 검색 API
Claude Code가 자신의 히스토리를 조회할 수 있습니다.

```
GET /api/search?q=sqlalchemy+async
```

슬래시 커맨드나 MCP 도구에서 과거 컨텍스트를 가져올 때 유용합니다.

</td>
<td>

### 🤖 에이전트 오케스트레이션
3가지 구조화된 멀티 에이전트 모드 — 웹 UI에서 실시간 스트리밍.

| 모드 | 동작 |
|------|------|
| **Compare** | 같은 프롬프트 → 양쪽 병렬 실행 |
| **Review** | 한쪽 구현 → 다른 쪽 리뷰 → 수정 |
| **Debate** | 대립 토론 + judge 수렴 판정 |

</td>
</tr>
</table>

---

## 🚀 빠른 시작

### 방법 A — 클론 후 설치 (권장)

```bash
# macOS / Linux
git clone https://github.com/Dradradre/claude-code-helper-with-codex && cd claude-code-helper-with-codex
bash install.sh
```

```powershell
# Windows
git clone https://github.com/Dradradre/claude-code-helper-with-codex; cd claude-code-helper-with-codex
.\install.ps1
```

설치 마법사가 다음을 안내합니다:

1. **uv** 설치 (없을 경우 자동)
2. **Claude CLI** / **Codex CLI** 설치 (없을 경우)
3. `claude login` / `codex login` 인증
4. 스캔 범위 선택 (전체 or 특정 프로젝트)
5. 초기 세션 인덱싱
6. Claude Code 슬래시 커맨드 설치

완료 후 **http://127.0.0.1:7878** 접속 🎉

### 방법 B — 원클릭 (새 PC)

```bash
# macOS / Linux
curl -LsSf https://raw.githubusercontent.com/Dradradre/claude-code-helper-with-codex/main/install.sh | bash
```

```powershell
# Windows
irm https://raw.githubusercontent.com/Dradradre/claude-code-helper-with-codex/main/install.ps1 | iex
```

---

## 📋 요구사항

| 의존성 | 필수 여부 | 역할 |
|--------|-----------|------|
| Python 3.11+ | ✅ | 런타임 (uv가 자동 관리) |
| [uv](https://docs.astral.sh/uv/) | ✅ | 패키지 매니저 — 자동 설치 |
| Node.js + npm | ✅ | Claude/Codex CLI 설치에 필요 |
| [Claude Code CLI](https://docs.anthropic.com/claude-code) | ⚡ | 세션 인덱싱 + 오케스트레이션 |
| [Codex CLI](https://github.com/openai/codex) | ⚡ | 세션 인덱싱 + 오케스트레이션 |

> ⚡ CLI 없이도 웹 대시보드와 세션 뷰어는 작동합니다. 오케스트레이션 모드는 양쪽 CLI 인증 필요.

---

## 🧩 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                      cchwc                              │
│                                                         │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────┐  │
│  │   인덱서    │    │  웹 서버     │    │ 오케스트  │  │
│  │             │    │  (FastAPI)   │    │  레이터   │  │
│  │ Claude ─────┼───▶│              │    │           │  │
│  │ ~/.claude/  │    │  대시보드    │    │ Compare   │  │
│  │             │    │  세션 목록   │◀───│ Review    │  │
│  │ Codex ──────┼───▶│  토큰 차트   │    │ Debate    │  │
│  │ ~/.codex/   │    │  검색 API    │    │           │  │
│  └─────────────┘    └──────────────┘    └───────────┘  │
│         │                  │                  │         │
│         ▼                  ▼                  ▼         │
│     ┌────────────────────────────────────────────┐      │
│     │       SQLite (~/.cchwc/cchwc.db)            │      │
│     └────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────┘
```

### 기술 스택

| 레이어 | 선택 | 이유 |
|--------|------|------|
| 백엔드 | FastAPI + SQLAlchemy 2 async | 자동 OpenAPI, async 퍼스트 |
| DB | SQLite (WAL 모드) | 설정 불필요, 단일 파일 |
| 프론트 | HTMX + Jinja2 + Tailwind CDN | 빌드 스텝 없음 |
| 차트 | Chart.js CDN | HTMX 친화적 |
| 파일 감시 | watchdog | 크로스플랫폼 |
| 패키지 | uv | 빠름, 락파일, venv 불필요 |
| CLI | Typer | FastAPI와 동일 생태계 |

---

## 🛠 사용법

### CLI 레퍼런스

```bash
# 현재 프로젝트 세션만 스캔
cchwc scan

# 전체 스캔
cchwc scan --global

# 특정 경로 스캔
cchwc scan --cwd ~/projects/my-app

# 스캔 범위 영구 설정
cchwc config add-project ~/projects/my-app
cchwc config show

# 웹 서버 시작 (기본: http://127.0.0.1:7878)
cchwc serve

# 오케스트레이션 (CLI에서 직접)
cchwc compare "Python에서 async/await를 설명해줘"
cchwc review  "rate limiter 구현해줘"
cchwc debate  "GraphQL vs REST 중 무엇을 선택할까?"

# 환경 점검
cchwc doctor

# Claude Code 슬래시 커맨드 + MCP 설치
cchwc install-commands
```

### Claude Code 통합

`cchwc install-commands` 실행 후 Claude Code 어디서나 사용 가능:

```
/cchwc-compare <프롬프트>   — Compare 모드
/cchwc-review  <프롬프트>   — Review 모드
/cchwc-debate  <주제>       — Debate 모드
```

또는 **MCP 서버**를 통한 네이티브 tool call — `~/.claude/mcp.json`에 자동 등록됩니다.

---

## 🤖 오케스트레이션 모드

<details>
<summary><b>Compare — 병렬 비교</b></summary>

같은 프롬프트를 Claude와 Codex에 동시에 전송. 두 응답을 나란히 비교합니다.

```
프롬프트
    ├── claude -p "..." ──▶ 응답 A
    └── codex exec "..." ─▶ 응답 B
```
</details>

<details>
<summary><b>Review — 구현 + 리뷰</b></summary>

한 에이전트가 구현하면 다른 에이전트가 리뷰합니다. 피드백에 따라 수정 루프를 돌 수 있습니다.

```
구현자 ──▶ 초안
리뷰어 ──▶ {"verdict": "request_changes", "issues": [...]}
구현자 ──▶ 수정본
```
</details>

<details>
<summary><b>Debate — 대립 토론</b></summary>

두 에이전트가 주제를 두고 라운드별 토론을 벌이고, judge가 수렴 여부를 판정합니다.

```
라운드 N:
  토론자A ──▶ {"position", "evidence", "concedes", "challenges"}
  토론자B ──▶ {"position", "evidence", "concedes", "challenges"}
  judge   ──▶ {"status": "converged|diverged|stalemate", "should_continue": bool}
```

종료 조건: 수렴 판정 · 토큰 한도 초과 · 2라운드 연속 양보 없음
</details>

---

## 🔒 보안 주의사항

- **로컬 전용** — 웹 서버는 기본적으로 `127.0.0.1`에 바인딩됩니다. 인증 없이 외부에 노출하지 마세요.
- **데이터 로컬 유지** — 모든 데이터는 머신 안에 있습니다. LLM 호출은 `claude -p` / `codex exec`를 통해 이루어지며, API 직접 호출은 없습니다.
- **민감한 내용** — JSONL 세션에 코드, 파일 내용, 도구 실행 결과로 수집된 인증 정보가 포함될 수 있습니다. 검색 인덱스는 기본적으로 시크릿을 마스킹하지 않습니다.

---

## 🤝 기여하기

```bash
git clone https://github.com/Dradradre/claude-code-helper-with-codex && cd claude-code-helper-with-codex
uv sync
uv run pytest         # 테스트
uv run ruff check .   # 린트
uv run python run.py  # 개발 서버 (포트 7878)
```

PR은 환영합니다. 대규모 변경은 이슈를 먼저 열어 주세요.

---

## 📄 라이선스

[MIT](LICENSE) — 자유롭게 사용, 수정, 배포하세요.

---

<div align="center">

Claude Code와 Codex CLI를 매일 함께 쓰는 개발자를 위해 만들었습니다.

[⭐ GitHub에서 스타 주기](https://github.com/Dradradre/claude-code-helper-with-codex) · [🐛 버그 신고](https://github.com/Dradradre/claude-code-helper-with-codex/issues) · [💡 기능 요청](https://github.com/Dradradre/claude-code-helper-with-codex/issues)

</div>
