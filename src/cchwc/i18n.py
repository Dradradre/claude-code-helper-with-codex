"""다국어 지원 — 현재 EN / KO."""

from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        # ── wizard steps ──────────────────────────────────────────
        "select_language":       "Select language",
        "welcome_subtitle":      "Setup Wizard",
        "welcome_tagline":       (
            "Unified session hub for Claude Code + Codex CLI.\n"
            "This wizard will configure everything — takes about 2 minutes."
        ),
        "step_prereqs":          "Checking prerequisites",
        "step_uv":               "Installing uv",
        "step_deps":             "Installing dependencies",
        "step_claude":           "Claude CLI",
        "step_codex":            "Codex CLI",
        "step_scope":            "Scan scope",
        "step_autostart":        "Auto-start",
        "step_integrations":     "Claude Code integration",
        "step_scan":             "Initial scan",
        "step_done":             "Setup complete",
        # ── prereqs ───────────────────────────────────────────────
        "node_missing":          "Node.js is required → https://nodejs.org (LTS)",
        "uv_install_prompt":     "uv package manager not found. Install it now?",
        "uv_install_failed":     "uv installation failed. Install manually: https://docs.astral.sh/uv/",
        # ── claude / codex ────────────────────────────────────────
        "install_claude_prompt": "Claude CLI not found. Install it? (npm install -g @anthropic-ai/claude-code)",
        "install_codex_prompt":  "Codex CLI not found. Install it? (npm install -g @openai/codex)",
        "install_failed":        "Installation failed. Check npm output above.",
        "login_required":        "Login required. Open browser now?",
        "login_hint_claude":     "Run manually:  claude login",
        "login_hint_codex":      "Run manually:  codex login",
        "login_ok":              "Claude already authenticated",
        "login_manual":          "Run this in a NEW terminal window (outside Claude Code):",
        "login_manual_hint":     "Claude Code intercepts interactive commands — open a separate terminal.",
        "login_press_key":       "Press any key once you've logged in…",
        # ── scope ────────────────────────────────────────────────
        "scope_prompt":          "Which sessions should cchwc index?",
        "scope_global":          "Global  — everything in ~/.claude/projects (all projects)",
        "scope_current":         "Current — only this directory's sessions",
        "scope_custom":          "Custom  — enter specific project paths",
        "scope_path_prompt":     "Project path (press Enter when done, empty = stop)",
        "scope_no_paths":        "No paths entered — falling back to current directory.",
        # ── autostart ────────────────────────────────────────────
        "autostart_prompt":      "Register cchwc to start automatically on login?",
        "autostart_ok":          "Auto-start registered. cchwc will run on every login.",
        "autostart_skip":        "Skipped. Run manually:  cchwc serve",
        "autostart_failed":      "Auto-start registration failed. Run manually: cchwc serve",
        # ── integrations ─────────────────────────────────────────
        "slash_prompt":          "Install Claude Code slash commands? (/cchwc-compare, /cchwc-review, /cchwc-debate)",
        "mcp_prompt":            "Register MCP server? (native tool-call in Claude Code)",
        "integration_ok":        "Installed.",
        # ── scan ─────────────────────────────────────────────────
        "scanning":              "Indexing sessions…",
        "scan_result":           "{agent}: {parsed} sessions indexed",
        # ── done ─────────────────────────────────────────────────
        "done_autostart_on":     "cchwc starts automatically on login.",
        "done_autostart_off":    "Start server:   cchwc serve",
        "done_url":              "Dashboard:      http://127.0.0.1:7878",
        "done_slash":            "Slash commands: /cchwc-compare  /cchwc-review  /cchwc-debate",
        "done_tip":              "Tip: bookmark http://127.0.0.1:7878",
        # ── misc ─────────────────────────────────────────────────
        "yes":                   "Yes",
        "no":                    "No, skip",
        "found":                 "found",
        "not_found":             "not found",
        "installing":            "Installing…",
        "done":                  "Done",
        "error":                 "Error",
    },
    "ko": {
        "select_language":       "언어를 선택하세요",
        "welcome_subtitle":      "설치 마법사",
        "welcome_tagline":       (
            "Claude Code + Codex CLI 통합 세션 허브.\n"
            "이 마법사가 모든 설정을 완료합니다 — 약 2분 소요."
        ),
        "step_prereqs":          "시스템 요구사항 확인",
        "step_uv":               "uv 설치",
        "step_deps":             "의존성 설치",
        "step_claude":           "Claude CLI",
        "step_codex":            "Codex CLI",
        "step_scope":            "스캔 범위 설정",
        "step_autostart":        "자동 시작 등록",
        "step_integrations":     "Claude Code 연동",
        "step_scan":             "초기 세션 인덱싱",
        "step_done":             "설치 완료",
        "node_missing":          "Node.js가 필요합니다 → https://nodejs.org (LTS)",
        "uv_install_prompt":     "uv 패키지 매니저가 없습니다. 지금 설치할까요?",
        "uv_install_failed":     "uv 설치 실패. 수동 설치: https://docs.astral.sh/uv/",
        "install_claude_prompt": "Claude CLI가 없습니다. 설치할까요? (npm install -g @anthropic-ai/claude-code)",
        "install_codex_prompt":  "Codex CLI가 없습니다. 설치할까요? (npm install -g @openai/codex)",
        "install_failed":        "설치 실패. npm 출력을 확인하세요.",
        "login_required":        "로그인이 필요합니다. 브라우저를 열까요?",
        "login_hint_claude":     "수동 실행:  claude login",
        "login_hint_codex":      "수동 실행:  codex login",
        "login_ok":              "Claude 로그인 확인됨",
        "login_manual":          "새 터미널 창을 열고 (Claude Code 밖에서) 아래 명령을 실행하세요:",
        "login_manual_hint":     "Claude Code 안에서는 대화형 명령 실행이 불가합니다.",
        "login_press_key":       "로그인 완료 후 아무 키나 누르세요…",
        "scope_prompt":          "어떤 세션을 인덱싱할까요?",
        "scope_global":          "전체  — ~/.claude/projects 전체 (모든 프로젝트)",
        "scope_current":         "현재  — 현재 디렉토리 프로젝트만",
        "scope_custom":          "지정  — 특정 경로를 직접 입력",
        "scope_path_prompt":     "프로젝트 경로 (완료 시 Enter, 빈 값 = 종료)",
        "scope_no_paths":        "경로가 없습니다 — 현재 디렉토리로 설정합니다.",
        "autostart_prompt":      "로그인 시 cchwc를 자동으로 시작할까요?",
        "autostart_ok":          "자동 시작 등록 완료. 로그인할 때마다 cchwc가 시작됩니다.",
        "autostart_skip":        "건너뜀. 수동 실행:  cchwc serve",
        "autostart_failed":      "자동 시작 등록 실패. 수동 실행: cchwc serve",
        "slash_prompt":          "Claude Code 슬래시 커맨드를 설치할까요? (/cchwc-compare 등)",
        "mcp_prompt":            "MCP 서버를 등록할까요? (Claude Code에서 네이티브 tool call 사용)",
        "integration_ok":        "설치 완료.",
        "scanning":              "세션 인덱싱 중…",
        "scan_result":           "{agent}: {parsed}개 세션 인덱싱 완료",
        "done_autostart_on":     "cchwc가 로그인 시 자동으로 시작됩니다.",
        "done_autostart_off":    "서버 시작:  cchwc serve",
        "done_url":              "대시보드:   http://127.0.0.1:7878",
        "done_slash":            "슬래시 커맨드: /cchwc-compare  /cchwc-review  /cchwc-debate",
        "done_tip":              "팁: http://127.0.0.1:7878 를 브라우저에 북마크하세요",
        "yes":                   "예",
        "no":                    "건너뜀",
        "found":                 "설치됨",
        "not_found":             "없음",
        "installing":            "설치 중…",
        "done":                  "완료",
        "error":                 "오류",
    },
}


_lang = "en"


def set_lang(lang: str) -> None:
    global _lang
    _lang = lang if lang in STRINGS else "en"


def t(key: str, **kwargs) -> str:
    text = STRINGS[_lang].get(key) or STRINGS["en"].get(key, key)
    return text.format(**kwargs) if kwargs else text
