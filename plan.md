# claude-code-helper-with-codex (cchwc) — 구현 계획서

> 이 문서는 새로운 Claude Code 세션이 처음부터 작업을 시작할 수 있도록 작성되었다.
> 각 Phase는 독립적으로 구현/테스트 가능하며, Phase 의존성은 명시되어 있다.

---

## 0. 프로젝트 개요

### 0.1 한 줄 요약

Claude Code와 Codex CLI 세션을 통합 관리하고, 두 에이전트를 협업/대결시키는 로컬 OSS 도구.

### 0.2 핵심 기능 (4가지)

1. **세션 관리**: Claude/Codex의 로컬 JSONL 세션 인덱싱 + 웹 뷰어 + 사용자 트리거 요약
2. **토큰 추적**: 세션별/일별/모델별 토큰 사용량 집계 + 시각화
3. **세션 검색 채널**: Claude Code가 과거 세션을 조회할 수 있는 HTTP API (CLI/MCP가 아닌 단순 REST)
4. **에이전트 오케스트레이션**: `claude -p`와 `codex exec`를 사용한 3가지 협업 모드
   - **Compare**: 같은 프롬프트 → 양쪽 결과 나란히
   - **Review**: 한쪽 구현 → 다른 쪽 리뷰 → 원작자 수정
   - **Debate**: 양쪽 토론 → judge LLM이 수렴 판정 → 종료

### 0.3 배포 방식

- npm/PyPI 배포 **안 함**.
- Git clone + `uv sync` (또는 `pip install -e .`) 형태로 지정 사용자에게 배포.
- 프라이빗 GitHub 레포로 시작, 안정화 후 퍼블릭 전환 검토.

### 0.4 비목표 (do NOT do)

- 클라우드 동기화 (Tailscale 가이드 문서로만 안내)
- LLM 직접 호출 (Anthropic/OpenAI API 키 사용 안 함; 모든 LLM 작업은 `claude -p`/`codex exec` 위임)
- 모바일 UI
- 실시간 협업 편집

---

## 1. 기술 스택 (확정)

| 영역 | 선택 | 이유 |
|---|---|---|
| 언어 | Python 3.11+ | 사용자 친숙, 라이브러리 풍부 |
| 백엔드 | FastAPI | async + 자동 OpenAPI 문서 |
| DB | SQLite (WAL 모드) | 단일 파일, 외부 의존성 없음 |
| ORM | SQLAlchemy 2.x (async) | 마이그레이션은 Alembic |
| 프론트 | HTMX + Jinja2 + Tailwind (CDN) | 빌드 스텝 없음 |
| 차트 | Chart.js (CDN) | HTMX 친화적 |
| File watch | watchdog | cross-platform |
| Process exec | asyncio.create_subprocess_exec | 비동기 stdout/stderr 캡처 |
| 패키지 매니저 | uv | 빠르고 lockfile 자동 |
| CLI | Typer | FastAPI 만든 사람과 동일, 일관성 |
| 테스트 | pytest + pytest-asyncio | |
| 린트/포맷 | ruff | 단일 도구 |

### 1.1 Python 버전 정책

- 최소 3.11 (asyncio.TaskGroup 사용)
- pyproject.toml에 `requires-python = ">=3.11"` 명시

### 1.2 외부 바이너리 의존성

- `claude` CLI (Claude Code) — 설치 안 되어 있어도 세션 인덱싱은 동작, 오케스트레이션만 비활성
- `codex` CLI — 위와 동일

런타임에 `shutil.which("claude")` / `shutil.which("codex")`로 확인하고 UI에서 상태 표시.

---

## 2. 디렉토리 구조

```
cchwc/
├── pyproject.toml
├── README.md
├── PLAN.md                        # 이 문서
├── CLAUDE.md                      # Claude Code용 가이드 (Phase 0에서 생성)
├── .gitignore
├── alembic.ini
├── alembic/
│   └── versions/
├── src/cchwc/
│   ├── __init__.py
│   ├── config.py                  # pydantic-settings 기반
│   ├── cli.py                     # Typer 엔트리포인트
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── db.py                  # SQLAlchemy engine/session
│   │   ├── models.py              # ORM 모델
│   │   ├── schemas.py             # Pydantic DTO
│   │   └── paths.py               # ~/.claude, ~/.codex 경로 해석
│   │
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py                # SessionAdapter 추상 클래스
│   │   ├── claude_adapter.py      # ~/.claude/projects/ 파싱
│   │   └── codex_adapter.py       # ~/.codex/sessions/ 파싱
│   │
│   ├── indexer/
│   │   ├── __init__.py
│   │   ├── scanner.py             # 초기 풀스캔
│   │   ├── watcher.py             # 증분 watch
│   │   └── parser.py              # JSONL → ORM 변환
│   │
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── runner.py              # subprocess 래퍼 (공통)
│   │   ├── claude_runner.py       # `claude -p` 실행
│   │   ├── codex_runner.py        # `codex exec` 실행
│   │   ├── modes/
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # OrchestrationMode 추상
│   │   │   ├── compare.py         # 모드 A
│   │   │   ├── review.py          # 모드 B
│   │   │   └── debate.py          # 모드 C
│   │   └── judge.py               # 디베이트 수렴 판정
│   │
│   ├── server/
│   │   ├── __init__.py
│   │   ├── app.py                 # FastAPI 인스턴스
│   │   ├── deps.py                # DI (DB session 등)
│   │   ├── routers/
│   │   │   ├── sessions.py        # /api/sessions
│   │   │   ├── tokens.py          # /api/tokens
│   │   │   ├── search.py          # /api/search (CC 역참조용)
│   │   │   ├── orchestrate.py     # /api/orchestrate
│   │   │   └── pages.py           # HTMX 페이지 라우트
│   │   ├── templates/
│   │   │   ├── base.html
│   │   │   ├── sessions/
│   │   │   ├── tokens/
│   │   │   └── orchestrate/
│   │   └── static/
│   │       └── (CSS/JS 없음 — 모든 게 CDN)
│   │
│   └── daemon/
│       ├── __init__.py
│       └── runner.py              # 백그라운드 watcher 데몬
│
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── sample_claude_session.jsonl
│   │   └── sample_codex_session.jsonl
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
└── docs/
    ├── architecture.md
    ├── adapters.md                # 새 에이전트 추가 가이드
    ├── orchestration.md           # 모드별 동작 설명
    └── deployment.md              # Tailscale, 멀티 PC 가이드
```

---

## 3. 데이터 모델 (SQLite 스키마)

### 3.1 핵심 테이블

```python
# src/cchwc/core/models.py 시그니처

class Project(Base):
    """프로젝트 = 작업 디렉토리"""
    id: int                      # PK
    cwd: str                     # 정규화된 절대 경로 (UNIQUE)
    display_name: str            # 사용자 지정 가능
    machine_id: str              # 호스트 식별자 (멀티 머신 대응)
    first_seen_at: datetime
    last_active_at: datetime

class Session(Base):
    """세션 = 단일 JSONL 파일"""
    id: int                      # PK
    project_id: int              # FK → Project
    agent_type: str              # "claude" | "codex"
    external_id: str             # JSONL 내부 session UUID
    file_path: str               # 절대 경로
    file_mtime: float            # 마지막 파싱 시점 (증분 인덱싱용)
    file_size: int
    started_at: datetime
    last_message_at: datetime
    message_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    total_cache_creation_tokens: int
    summary: str | None          # 사용자 트리거 요약
    summary_generated_at: datetime | None
    summary_tokens_used: int | None

    __table_args__ = (UniqueConstraint("agent_type", "external_id"),)

class Message(Base):
    """세션 내 개별 turn"""
    id: int                      # PK
    session_id: int              # FK
    sequence: int                # 세션 내 순서
    role: str                    # "user" | "assistant" | "tool_use" | "tool_result" | "system"
    content_text: str | None     # 텍스트 추출본 (검색용)
    content_json: str            # 원본 JSON (전체 보존)
    timestamp: datetime
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_creation_tokens: int | None
    model: str | None            # "claude-sonnet-4-7", "gpt-5" 등

class OrchestrationRun(Base):
    """A/B/C 모드 실행 1회"""
    id: int                      # PK
    mode: str                    # "compare" | "review" | "debate"
    user_prompt: str
    cwd: str
    started_at: datetime
    finished_at: datetime | None
    status: str                  # "running" | "completed" | "failed" | "stopped"
    total_cost_usd: float
    total_tokens: int
    config_json: str             # 모드별 설정 (max_rounds 등)
    result_summary: str | None

class OrchestrationStep(Base):
    """OrchestrationRun 내 단일 에이전트 호출"""
    id: int                      # PK
    run_id: int                  # FK
    sequence: int
    agent_type: str              # "claude" | "codex" | "judge"
    role: str                    # "implementer" | "reviewer" | "debater_a" | "debater_b" | "judge"
    prompt: str
    response: str
    started_at: datetime
    finished_at: datetime
    input_tokens: int
    output_tokens: int
    cost_usd: float
    spawned_session_id: int | None  # FK → Session (이 step이 생성한 세션 연결)
    error: str | None
```

### 3.2 인덱스

```sql
CREATE INDEX idx_session_project_active ON session(project_id, last_message_at DESC);
CREATE INDEX idx_message_session_seq ON message(session_id, sequence);
CREATE INDEX idx_message_text_fts ON message USING fts5(content_text);  -- SQLite FTS5
CREATE INDEX idx_orch_started ON orchestration_run(started_at DESC);
```

FTS5는 메시지 검색용. SQLite 기본 빌드에 포함됨.

### 3.3 마이그레이션 정책

- Alembic으로 모든 스키마 변경 관리
- `alembic upgrade head`를 daemon 시작 시 자동 실행
- 첫 릴리즈 후엔 downgrade 스크립트도 작성

---

## 4. 핵심 컴포넌트 설계

### 4.1 SessionAdapter (어댑터 패턴)

```python
# src/cchwc/adapters/base.py

class SessionAdapter(ABC):
    """에이전트별 세션 저장소를 추상화"""

    agent_type: str  # "claude" or "codex"

    @abstractmethod
    def session_root(self) -> Path:
        """세션 JSONL이 저장되는 루트 디렉토리"""

    @abstractmethod
    def discover_session_files(self) -> Iterator[Path]:
        """모든 JSONL 파일 경로 yield"""

    @abstractmethod
    def parse_file(self, path: Path) -> ParsedSession:
        """JSONL → ParsedSession 변환"""

    @abstractmethod
    def extract_cwd(self, path: Path) -> str | None:
        """JSONL 또는 경로에서 작업 디렉토리 추출"""
```

#### 4.1.1 ClaudeAdapter

- 루트: `~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl`
- cwd 추출: 디렉토리명 디코딩 (Claude Code 인코딩 규칙 역적용)
- 메시지 형식: `{"type": "user"|"assistant", "message": {...}, "uuid": ..., "parentUuid": ...}`
- usage 위치: `message.usage.{input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens}`

#### 4.1.2 CodexAdapter

- 루트: `~/.codex/sessions/YYYY/MM/DD/<rollout-*>.jsonl`
- cwd 추출: JSONL 첫 줄의 `<environment_context>` 블록에서 `cwd` 필드 파싱
- 메시지 형식: Codex 자체 포맷 (확실성 0.7 — 실제 샘플로 검증 필요)
- usage: 메시지 내부 `usage` 필드 (구조 동일성 검증 필요)

> **작업 시 주의 (Phase 1)**: 실제 JSONL 샘플을 `tests/fixtures/`에 미리 넣어두고, parser 테스트 통과를 어댑터 구현의 DoD(Definition of Done)로 삼을 것.

---

### 4.2 Indexer

#### 4.2.1 초기 풀스캔 (`scanner.py`)

```
def initial_scan(adapter: SessionAdapter, db: AsyncSession) -> ScanReport:
    """
    1. adapter.discover_session_files() 순회
    2. 각 파일의 mtime을 DB의 Session.file_mtime과 비교
    3. 변경된 파일만 파싱 → upsert
    4. 삭제된 파일은 soft-delete (또는 삭제 플래그)
    """
```

- 첫 실행 시 수천 개 세션 처리 가능 → asyncio.Semaphore로 동시 파싱 제한 (기본 8)
- 진행률 표시 (rich.Progress 사용)

#### 4.2.2 증분 watch (`watcher.py`)

```
class SessionWatcher:
    def __init__(self, adapters: list[SessionAdapter]):
        self.observer = watchdog.Observer()

    def on_modified(self, event):
        # 디바운스: 같은 파일 100ms 내 중복 이벤트 무시
        # asyncio.Queue에 푸시
        ...

    async def consume_loop(self):
        # Queue에서 꺼내서 incremental parse
        ...
```

- 파일이 작성 중일 때 fsync 전 읽으면 잘린 JSONL이 나옴 → 마지막 줄이 valid JSON 아니면 다음 라인 무시
- 디바운스 100ms (확실성 0.8 — 환경에 따라 조정)

---

### 4.3 Orchestrator

#### 4.3.1 공통 Runner

```python
# src/cchwc/orchestrator/runner.py

@dataclass
class AgentResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_sec: float
    spawned_session_id: str | None  # JSONL에서 새로 만들어진 세션 UUID
    usage: TokenUsage
    parsed_response: dict | None    # JSON 모드일 때

async def run_agent(
    cmd: list[str],
    cwd: str,
    stdin_payload: str | None,
    timeout_sec: int,
    env: dict | None = None,
) -> AgentResult:
    """공통 subprocess 실행. stdout/stderr 캡처, timeout, 강제 종료."""
```

#### 4.3.2 ClaudeRunner

```python
async def run_claude_p(
    prompt: str,
    cwd: str,
    output_format: Literal["text", "json"] = "json",
    allowed_tools: list[str] | None = None,
    max_turns: int | None = None,
    resume_session: str | None = None,
) -> AgentResult:
    """
    claude -p "<prompt>" --output-format json [--allowedTools ...] [--max-turns N]
    """
```

- `--output-format json` 강제 사용 → 파싱 안정성 확보
- Bash, Read 등 도구 허용 여부는 모드별 설정에서 받음

#### 4.3.3 CodexRunner

```python
async def run_codex_exec(
    prompt: str,
    cwd: str,
    json_mode: bool = True,
    output_schema: dict | None = None,  # JSON Schema 강제 출력
    resume_session: str | None = None,
) -> AgentResult:
    """
    codex exec --json "<prompt>"
    또는
    codex exec resume <session-id> "<prompt>"
    """
```

- Codex의 `--output-schema`는 디베이트 모드에서 강제 구조화 응답 받을 때 사용

---

### 4.4 Orchestration Modes

#### 4.4.1 ModeBase

```python
class OrchestrationMode(ABC):
    name: str

    @abstractmethod
    async def execute(
        self,
        prompt: str,
        cwd: str,
        config: ModeConfig,
        run_id: int,
        emit: Callable[[StepEvent], Awaitable[None]],  # SSE 스트리밍
    ) -> RunResult:
        ...
```

`emit`은 SSE로 웹 UI에 라이브 업데이트 전달.

#### 4.4.2 Compare 모드 (A)

```
1. claude -p "<prompt>" 와 codex exec "<prompt>" 동시 실행 (asyncio.gather)
2. 양쪽 결과를 OrchestrationStep 2개로 저장
3. RunResult 종료
```

- 가장 단순. 무한루프 위험 없음
- 실패한 쪽은 error 필드 채워서 표시

#### 4.4.3 Review 모드 (B)

```
1. implementer (claude 또는 codex) → 1차 응답
2. reviewer (다른 쪽) → 1차 응답을 컨텍스트로 리뷰
   → 응답 스키마: {"verdict": "approve|request_changes", "issues": [...], "suggestions": [...]}
3. verdict == "request_changes"이면:
   implementer에게 issues+suggestions 전달 → 수정본 생성
4. (선택) reviewer 재검토 1회 더 (config.max_review_rounds, 기본 1)
5. 종료
```

- max_review_rounds 기본값 1, 최대 2 (확실성 0.85, 그 이상은 비용 대비 효과 낮음)

#### 4.4.4 Debate 모드 (C) — 가장 복잡

```
구조화 응답 스키마 (양쪽 모두 강제):
{
  "position": "...",
  "evidence": [...],
  "concedes": [...],     # 상대 주장 중 인정하는 부분
  "challenges": [...]    # 반박할 부분
}

루프:
1. Round 1:
   - debater_a: 초기 입장
   - debater_b: 반박
2. Round N (N >= 2):
   - debater_a: 직전 b 응답 받고 재반박
   - debater_b: 직전 a 응답 받고 재반박
3. 매 라운드 후 judge 호출:
   - judge prompt: "두 응답을 비교하라. concedes/challenges 진전 평가."
   - judge 응답 스키마:
     {
       "status": "converged" | "diverged" | "stalemate",
       "agreement_points": [...],
       "disagreement_points": [...],
       "should_continue": bool,
       "synthesis": "..."   # converged/stalemate일 때만
     }
4. 종료 조건 (OR):
   - judge.should_continue == False
   - rounds_completed >= max_rounds
   - total_tokens >= max_total_tokens
   - total_cost_usd >= max_total_cost_usd
   - 양쪽 모두 concedes가 비어있는 라운드 2회 연속 (정체)
```

**Judge는 누구로 돌리나?**

옵션 A: `claude -p`로 별도 호출 (Sonnet 강제)
옵션 B: `codex exec`로 별도 호출
옵션 C: 사용자가 모드 시작 시 선택

→ **기본은 A**, config로 변경 가능 (확실성 0.7).

**디베이트 컨텍스트 누적 방지:**

매 라운드마다 직전 라운드 응답만 컨텍스트로 패스. 전체 히스토리는 patches로 압축:
```
prompt = f"""
Topic: {topic}
Your previous position summary: {summary_of_your_last_position}
Opponent's latest argument: {opponent_latest_response}

Respond using the schema: ...
"""
```

#### 4.4.5 ModeConfig 예시

```python
class ModeConfig(BaseModel):
    # 공통
    timeout_per_step_sec: int = 600
    total_timeout_sec: int = 1800
    max_total_tokens: int = 100_000
    max_total_cost_usd: float = 5.0

    # review 전용
    implementer: Literal["claude", "codex"] = "claude"
    reviewer: Literal["claude", "codex"] = "codex"
    max_review_rounds: int = 1

    # debate 전용
    debater_a: Literal["claude", "codex"] = "claude"
    debater_b: Literal["claude", "codex"] = "codex"
    judge: Literal["claude", "codex"] = "claude"
    max_rounds: int = 3
    convergence_check_after_round: int = 1  # 1라운드 끝나고부터 judge 시작
```

---

### 4.5 Web Server

#### 4.5.1 라우트 구조

```
GET  /                              → 대시보드
GET  /sessions                      → 세션 리스트 (HTMX)
GET  /sessions/{id}                 → 세션 상세 (메시지 전체)
GET  /sessions/{id}/messages        → HTMX 부분 (페이지네이션)
POST /sessions/{id}/summary         → 요약 생성 트리거
GET  /tokens                        → 토큰 대시보드
GET  /tokens/data                   → 차트 데이터 (JSON)
GET  /orchestrate                   → 오케스트레이션 UI
POST /orchestrate/runs              → 새 런 시작
GET  /orchestrate/runs              → 런 리스트
GET  /orchestrate/runs/{id}         → 런 상세
GET  /orchestrate/runs/{id}/stream  → SSE 라이브 업데이트
POST /orchestrate/runs/{id}/stop    → 강제 중단

# Claude Code 역참조용 (단순 REST, 인증 없음 — 로컬 전용)
GET  /api/search?q=...&project=...  → 메시지 풀텍스트 검색
GET  /api/sessions/{id}             → JSON으로 세션 반환
GET  /api/projects                  → 프로젝트 리스트
```

#### 4.5.2 SSE 스트리밍

오케스트레이션 진행 상황을 실시간 웹 UI에 push:

```python
@router.get("/orchestrate/runs/{run_id}/stream")
async def stream_run(run_id: int):
    async def event_generator():
        async for event in run_event_bus.subscribe(run_id):
            yield f"data: {event.model_dump_json()}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

`run_event_bus`는 in-memory pub/sub (asyncio.Queue 기반).

#### 4.5.3 HTMX 패턴

```html
<!-- 세션 리스트 -->
<div hx-get="/sessions/list" hx-trigger="load" hx-swap="innerHTML">
  Loading...
</div>

<!-- 무한 스크롤 -->
<div hx-get="/sessions/list?offset=50" hx-trigger="revealed" hx-swap="afterend">
</div>

<!-- 라이브 토큰 차트 -->
<div hx-ext="sse" sse-connect="/tokens/stream" sse-swap="message">
  <canvas id="token-chart"></canvas>
</div>
```

---

## 5. 설정 (`config.py`)

```python
class Settings(BaseSettings):
    # 경로
    db_path: Path = Path.home() / ".cchwc" / "cchwc.db"
    claude_root: Path = Path.home() / ".claude" / "projects"
    codex_root: Path = Path.home() / ".codex" / "sessions"

    # 서버
    host: str = "127.0.0.1"
    port: int = 7878

    # 데몬
    watch_debounce_ms: int = 100
    scan_concurrency: int = 8

    # 오케스트레이션 기본값
    default_max_rounds: int = 3
    default_max_cost_usd: float = 5.0
    default_max_tokens: int = 100_000

    # 도구 경로 (없으면 PATH에서 찾음)
    claude_bin: str = "claude"
    codex_bin: str = "codex"

    # 로깅
    log_level: str = "INFO"
    log_file: Path | None = None

    class Config:
        env_prefix = "CCHWC_"
        env_file = ".env"
```

`~/.cchwc/config.toml`도 지원 (환경변수보다 우선순위 낮음).

---

## 6. CLI (Typer)

```bash
# 데몬 (백그라운드 watcher)
cchwc daemon start [--foreground]
cchwc daemon stop
cchwc daemon status

# 인덱스
cchwc index scan                     # 풀스캔
cchwc index stats                    # 통계 출력

# 서버
cchwc serve [--host 127.0.0.1] [--port 7878]

# 오케스트레이션 (CLI에서 직접)
cchwc compare "prompt" [--cwd /path]
cchwc review "prompt" [--implementer claude] [--reviewer codex]
cchwc debate "prompt" [--max-rounds 3]

# 유틸
cchwc list-sessions [--agent claude] [--project /path]
cchwc show-session <id>
cchwc export-session <id> --format markdown

# 마이그레이션
cchwc db upgrade
cchwc db downgrade <revision>

# 진단
cchwc doctor                         # 환경 점검 (claude/codex 설치 여부 등)
```

---

## 7. 구현 Phase

각 Phase는 **독립 PR**로 머지. 마지막 단계는 동작하는 데모.

### Phase 0: 프로젝트 부트스트랩 (반나절)

**작업:**
- [ ] `pyproject.toml` 작성 (uv 기준)
- [ ] 디렉토리 구조 생성 (빈 `__init__.py` 포함)
- [ ] `.gitignore`, `README.md` 초안
- [ ] **`CLAUDE.md` 작성** (이 PLAN.md 요약 + 작업 시 규칙)
- [ ] ruff/pytest 설정
- [ ] 첫 커밋

**DoD:**
- `uv sync` 성공
- `pytest` 실행 (테스트 0개라도 OK)
- `ruff check src` 통과

**의존성:** 없음

---

### Phase 1: 어댑터 + 파서 (2~3일)

**작업:**
- [ ] `tests/fixtures/`에 실제 Claude/Codex JSONL 샘플 5개씩 수집 (사용자 PC에서)
- [ ] `core/models.py` ORM 모델 작성
- [ ] Alembic 초기화 + 첫 마이그레이션
- [ ] `adapters/base.py` 추상 클래스
- [ ] `adapters/claude_adapter.py` 구현
- [ ] `adapters/codex_adapter.py` 구현
- [ ] `indexer/parser.py` JSONL → ORM 변환
- [ ] 단위 테스트 (fixture 기반)

**DoD:**
- 양쪽 어댑터 모두 fixture 파싱 성공
- 토큰 합계가 ccusage 출력과 일치 (수동 검증)

**의존성:** Phase 0

**함정:**
- Claude의 cwd 인코딩 규칙: `/Users/foo/bar` → `-Users-foo-bar` (확실성 0.7, 실제 디렉토리에서 검증 필요)
- Codex의 cwd는 JSONL 내부 `<environment_context>` 첫 메시지에 있음 (확실성 0.7)
- 잘린 마지막 줄 처리: `try/except json.JSONDecodeError` 후 skip

---

### Phase 2: 인덱서 + Watcher (2일)

**작업:**
- [ ] `indexer/scanner.py` 풀스캔
- [ ] `indexer/watcher.py` watchdog 통합
- [ ] `daemon/runner.py` asyncio 데몬
- [ ] `cli.py`에 `daemon`, `index` 커맨드 추가
- [ ] 통합 테스트 (임시 디렉토리에 fixture 복사 → watch 동작 확인)

**DoD:**
- `cchwc index scan` 실행 후 SQLite에 모든 세션 적재
- 데몬 실행 중 새 JSONL 추가하면 5초 내 DB 반영

**의존성:** Phase 1

---

### Phase 3: 웹 서버 — 세션 뷰어 (2~3일)

**작업:**
- [ ] FastAPI 앱 + 라우터 구조
- [ ] Jinja2 + Tailwind base 템플릿
- [ ] `/sessions` 리스트 페이지
- [ ] `/sessions/{id}` 상세 페이지 (메시지 렌더링)
- [ ] `/api/search` FTS5 기반 검색
- [ ] 페이지네이션 (HTMX 무한 스크롤)
- [ ] `cli.py serve` 커맨드

**DoD:**
- 브라우저에서 모든 세션 탐색 가능
- 검색이 동작 (사용자 메시지 텍스트로)

**의존성:** Phase 2

**참고:** 이 단계까지 끝나면 이미 ccusage + claude-code-history-viewer 대체 가능.

---

### Phase 4: 토큰 대시보드 (1~2일)

**작업:**
- [ ] `/tokens` 페이지
- [ ] Chart.js 통합 (CDN)
- [ ] 일별/세션별/모델별 집계 쿼리
- [ ] CSV 내보내기

**DoD:**
- 7일/30일/전체 토큰 차트
- 프로젝트별 비용 추정 (대략적인 모델 가격표 내장)

**의존성:** Phase 3

---

### Phase 5: 오케스트레이션 — Compare + Review (3~4일)

**작업:**
- [ ] `orchestrator/runner.py` 공통 subprocess
- [ ] `claude_runner.py` / `codex_runner.py`
- [ ] `modes/compare.py`
- [ ] `modes/review.py`
- [ ] SSE 스트리밍 인프라
- [ ] `/orchestrate` UI (모드 선택 + 결과 라이브 뷰)
- [ ] `cli.py compare` / `cli.py review` 커맨드

**DoD:**
- 웹에서 프롬프트 입력 → 양쪽 응답 라이브 스트리밍
- Review 모드에서 reviewer가 실제로 issues 검출

**의존성:** Phase 4

**함정:**
- `claude -p`는 stateless (앞서 확인). 컨텍스트 주입은 prompt에 직접 박아야 함
- subprocess 종료 시 좀비 프로세스 방지 (process group 사용)
- stdout이 매우 클 때 buffer 부족 → asyncio.subprocess.PIPE limit 늘리기

---

### Phase 6: 오케스트레이션 — Debate (3~4일)

**작업:**
- [ ] `modes/debate.py` 핵심 루프
- [ ] `judge.py` 수렴 판정
- [ ] 구조화 응답 스키마 강제 (양쪽 모두 JSON 모드)
- [ ] hard caps (rounds, tokens, cost) 검증
- [ ] 정체 감지 (concedes 비어있는 라운드 2회 연속)
- [ ] 사용자 stop 버튼

**DoD:**
- 사전 정의된 토픽 5개로 디베이트 실행 — 모두 max_rounds 내 종료
- 비용 추정이 실제 비용과 ±10% 이내

**의존성:** Phase 5

**함정:**
- 디베이트 컨텍스트 누적 폭발 — 매 라운드 직전 응답만 패스 (전략은 4.4.4 참고)
- judge가 "should_continue: true"만 계속 뱉을 위험 → 라운드 N 도달 시 강제 종료 후 unresolved로 표기

---

### Phase 7: Polish + 문서화 (2일)

**작업:**
- [ ] `docs/architecture.md`
- [ ] `docs/adapters.md` (새 어댑터 추가 가이드)
- [ ] `docs/orchestration.md`
- [ ] `docs/deployment.md` (Tailscale 등)
- [ ] README 보강 (스크린샷)
- [ ] `cchwc doctor` 진단 커맨드
- [ ] 에러 메시지 정리

**DoD:**
- 처음 보는 사람이 README + git clone으로 시작 가능

**의존성:** Phase 6

---

## 8. 테스트 전략

### 8.1 단위 테스트
- 어댑터 파싱
- 모드별 종료 조건 로직 (mock subprocess)
- 토큰 집계 쿼리

### 8.2 통합 테스트
- Indexer + Watcher (임시 디렉토리)
- API 라우트 (TestClient)

### 8.3 E2E 테스트 (수동)
- Compare 모드 실제 실행 (`claude -p` 호출됨, API 키 소비)
- Review 모드 1회
- Debate 모드 1회

E2E는 CI에서 실행 안 함 (비용). 로컬 매뉴얼 체크리스트로 관리.

### 8.4 회귀 픽스처

각 어댑터별로 **현실 JSONL 샘플 10개** 이상 `tests/fixtures/regression/`에 보관.
새 Claude/Codex 버전이 포맷 깰 때 빠르게 감지.

---

## 9. 멀티 머신 운영 (Phase 7 이후)

### 9.1 단일 머신 (기본)

- daemon + serve를 같은 PC에서
- DB 위치: `~/.cchwc/cchwc.db`

### 9.2 멀티 머신 (집 Mac Studio가 hub)

- 각 PC에 daemon만 실행 → 로컬 SQLite에 인덱싱
- hub PC에 hub-mode serve 실행 → 다른 PC의 SQLite를 read-only로 마운트하거나 sync
- 추천: rsync/syncthing/Tailscale 가이드만 docs에 제공. 자체 sync 안 만듦.

이건 v1 이후 과제.

---

## 10. 보안 / 함정 노트

### 10.1 secret 노출
- JSONL에 API 호출 결과로 secret이 들어갈 수 있음 (.env 내용 grep, AWS 키 등)
- 검색 인덱스에서 일반적인 secret 패턴 마스킹 (확실성 0.6 — 어디까지 가능할지 불명)
- v0에선 "로컬 전용, 외부 노출 금지" 경고로 충분

### 10.2 동시성
- watcher와 scanner가 같이 돌면 race → DB write에 단일 transaction worker 두기
- SQLite WAL 모드 + busy_timeout=5000

### 10.3 LLM 명령어 변경
- `claude` / `codex` CLI는 자주 변경됨. doctor 커맨드에서 버전 체크 + 알려진 버전 호환성 표 출력
- adapter 변경 시 마이너 버전 bump

### 10.4 쿼터 폭발 (오케스트레이션)
- Compare 모드도 한 번 실행 시 두 에이전트 호출 → 사용자에게 "예상 비용" 표시 후 confirm

### 10.5 출력 파싱 실패
- LLM이 JSON 깨뜨릴 때 → fallback: 텍스트 그대로 저장 + warning 표시. 디베이트는 깨진 라운드 1회 허용 후 종료.

---

## 11. 새 Claude Code 세션이 작업 시작할 때 체크리스트

> 이 항목은 작업 시작 전 **반드시** 확인.

1. [ ] `git status` 깨끗한가? 아니면 커밋 후 시작
2. [ ] 현재 작업할 Phase 번호 확인 (PLAN.md §7)
3. [ ] 해당 Phase의 의존성 Phase가 완료됐는지 확인
4. [ ] `pytest` 실행 → 모든 테스트 통과 후 시작
5. [ ] 작업 brunch 생성: `git checkout -b phase-N-<short-description>`
6. [ ] **이 PLAN.md를 절대 수정하지 않음** (별도 PR로 분리)
7. [ ] Phase의 모든 [ ] 체크박스 충족 후 PR
8. [ ] PR 머지 후 main에서 `pytest` + `ruff` 다시 통과 확인

### 11.1 작업 중 PLAN과 다른 결정을 해야 할 때

- 작은 변경: 작업 PR에 `decisions.md` 추가하여 기록
- 구조적 변경: 별도 PR로 PLAN.md 수정 먼저 (코드 변경 PR과 분리)

### 11.2 자주 쓸 명령어

```bash
# 개발 시작
uv sync
uv run pytest
uv run ruff check src tests
uv run ruff format src tests

# 마이그레이션
uv run alembic revision --autogenerate -m "add foo"
uv run alembic upgrade head

# 데몬 + 서버 (개발)
uv run cchwc daemon start --foreground  # 터미널 1
uv run cchwc serve                       # 터미널 2

# 단일 모듈 테스트
uv run pytest tests/unit/test_claude_adapter.py -v
```

---

## 12. 미해결 결정 사항 (사용자 확인 필요)

- [ ] **이름 확정**: `claude-code-helper-with-codex` 그대로 vs `cc-codex-bridge` vs 다른 이름
- [ ] **첫 릴리즈 라이선스**: MIT? Apache-2.0?
- [ ] **judge 모델 기본값**: claude vs codex
- [ ] **요약 기능 정확한 트리거 위치**: 세션 페이지 버튼 vs CLI 커맨드 vs 둘 다
- [ ] **CC 역참조 채널 인증**: 로컬 전용이라 인증 없음 vs 토큰 헤더 강제

---

## 끝