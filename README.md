<div align="center">

```
 ██████╗ ██████╗██╗  ██╗██╗    ██╗ ██████╗
██╔════╝██╔════╝██║  ██║██║    ██║██╔════╝
██║     ██║     ███████║██║ █╗ ██║██║
██║     ██║     ██╔══██║██║███╗██║██║
╚██████╗╚██████╗██║  ██║╚███╔███╔╝╚██████╗
 ╚═════╝ ╚═════╝╚═╝  ╚═╝ ╚══╝╚══╝  ╚═════╝
```

**claude-code-helper-with-codex**

Unified session hub and orchestration layer for Claude Code + Codex CLI

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![uv](https://img.shields.io/badge/uv-package%20manager-DE5FE9)](https://docs.astral.sh/uv/)

[**한국어**](README.ko.md) · [Quick Start](#-quick-start) · [Features](#-features) · [Architecture](#-architecture) · [Contributing](#-contributing)

</div>

---

## What is cchwc?

cchwc is a **local-first desktop tool** that sits alongside your Claude Code and Codex CLI workflows. It indexes every session both agents produce, visualizes your token usage over time, and — most uniquely — lets you **pit the two agents against each other** in structured orchestration modes.

> **No cloud. No API keys. No sync service.**  
> Every LLM call goes through the CLIs you already have installed.

---

## ✨ Features

<table>
<tr>
<td width="50%">

### 📚 Session Hub
Browse, search, and summarize every Claude Code and Codex session across all your projects — in one place.

- Full-text search across all messages
- Per-project and per-agent filtering
- Token usage breakdown per session

</td>
<td width="50%">

### 📊 Token Dashboard
Know exactly where your budget goes.

- Daily / model / project breakdowns
- Cache read vs creation split
- Chart.js visualizations, no build step

</td>
</tr>
<tr>
<td>

### 🔍 Session Search API
Let Claude Code query its own history.

```
GET /api/search?q=sqlalchemy+async
```

Useful in Claude Code slash commands and MCP tools to retrieve past context.

</td>
<td>

### 🤖 Agent Orchestration
Three structured multi-agent modes — all streamed live to the web UI.

| Mode | What it does |
|------|-------------|
| **Compare** | Same prompt → both agents in parallel |
| **Review** | One implements, the other critiques |
| **Debate** | Adversarial rounds + judge convergence |

</td>
</tr>
</table>

---

## 🚀 Quick Start

### Option A — Clone & run (recommended)

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

The installer will:
1. Install **uv** (Python package manager) if needed
2. Install **Claude CLI** and **Codex CLI** if needed  
3. Guide you through `claude login` / `codex login`
4. Let you choose scan scope (global or specific projects)
5. Run the initial session index
6. Install Claude Code slash commands (`/cchwc-compare` etc.)

Then open **http://127.0.0.1:7878** 🎉

### Option B — One-liner (fresh machine)

```bash
curl -LsSf https://raw.githubusercontent.com/Dradradre/claude-code-helper-with-codex/main/install.sh | bash
```

```powershell
irm https://raw.githubusercontent.com/Dradradre/claude-code-helper-with-codex/main/install.ps1 | iex
```

---

## 📋 Requirements

| Dependency | Required | Purpose |
|------------|----------|---------|
| Python 3.11+ | ✅ | Runtime (managed by uv) |
| [uv](https://docs.astral.sh/uv/) | ✅ | Package manager — auto-installed |
| Node.js + npm | ✅ | Needed to install Claude/Codex CLIs |
| [Claude Code CLI](https://docs.anthropic.com/claude-code) | ⚡ | Session indexing + orchestration |
| [Codex CLI](https://github.com/openai/codex) | ⚡ | Session indexing + orchestration |

> ⚡ The web dashboard and session viewer work without these. Orchestration modes require both CLIs to be authenticated.

---

## 🧩 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      cchwc                              │
│                                                         │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────┐  │
│  │   Indexer   │    │  Web Server  │    │  Orchestr │  │
│  │             │    │  (FastAPI)   │    │  ator     │  │
│  │ Claude ─────┼───▶│              │    │           │  │
│  │ ~/.claude/  │    │  Dashboard   │    │ Compare   │  │
│  │             │    │  Sessions    │◀───│ Review    │  │
│  │ Codex ──────┼───▶│  Tokens      │    │ Debate    │  │
│  │ ~/.codex/   │    │  Search API  │    │           │  │
│  └─────────────┘    └──────────────┘    └───────────┘  │
│         │                  │                  │         │
│         ▼                  ▼                  ▼         │
│     ┌────────────────────────────────────────────┐      │
│     │          SQLite  (~/.cchwc/cchwc.db)        │      │
│     └────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────┘
```

### Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | FastAPI + SQLAlchemy 2 async | Auto OpenAPI docs, async-first |
| Database | SQLite (WAL mode) | Zero config, single file |
| Frontend | HTMX + Jinja2 + Tailwind CDN | No build step |
| Charts | Chart.js CDN | HTMX-friendly |
| File watch | watchdog | Cross-platform |
| Packaging | uv | Fast, lockfile, no venv fuss |
| CLI | Typer | Same ecosystem as FastAPI |

---

## 🛠 Usage

### CLI Reference

```bash
# Initial scan (current project only)
cchwc scan

# Scan everything
cchwc scan --global

# Scan specific paths
cchwc scan --cwd ~/projects/my-app --cwd ~/projects/another

# Configure persistent scan scope
cchwc config add-project ~/projects/my-app
cchwc config set-global

# Start web server
cchwc serve                  # default: http://127.0.0.1:7878

# Orchestration (CLI)
cchwc compare "explain async/await in Python"
cchwc review  "implement a rate limiter"
cchwc debate  "should we use GraphQL or REST?"

# Environment check
cchwc doctor

# Install Claude Code slash commands + MCP
cchwc install-commands
```

### Claude Code Integration

After running `cchwc install-commands`, three slash commands become available globally in Claude Code:

```
/cchwc-compare <prompt>   — run Compare mode
/cchwc-review  <prompt>   — run Review mode
/cchwc-debate  <topic>    — run Debate mode
```

Or use the **MCP server** for native tool-call integration — registered automatically in `~/.claude/mcp.json`.

### Scan Scope

| Command | Scope |
|---------|-------|
| `cchwc scan` | Current working directory's sessions only |
| `cchwc scan --global` | All `~/.claude/projects` |
| `cchwc scan --cwd PATH` | Specific path(s) |
| `cchwc config add-project PATH` | Persist path to `~/.cchwc/config.toml` |

---

## 🤖 Orchestration Modes

### Compare
Sends the same prompt to Claude and Codex simultaneously. Useful for benchmarking responses or getting two independent takes.

```
User Prompt
    ├── claude -p "..." ──▶ Response A
    └── codex exec "..." ─▶ Response B
                            (shown side by side)
```

### Review
One agent implements, the other reviews. Optionally loops for revisions.

```
implementer ──▶ implementation
reviewer    ──▶ {"verdict": "request_changes", "issues": [...]}
implementer ──▶ revised implementation
```

### Debate
Adversarial multi-round discussion with a judge that checks for convergence.

```
Round N:
  debater_a ──▶ {"position", "evidence", "concedes", "challenges"}
  debater_b ──▶ {"position", "evidence", "concedes", "challenges"}
  judge     ──▶ {"status": "converged|diverged|stalemate", "should_continue": bool}
```

Stops when: judge says converged · token budget reached · 2 rounds with no concessions

---

## 🗂 Project Structure

```
cchwc/
├── src/cchwc/
│   ├── adapters/       # Claude + Codex JSONL parsers
│   ├── indexer/        # Full scan + watchdog incremental
│   ├── orchestrator/   # Compare / Review / Debate modes
│   ├── server/         # FastAPI app + HTMX templates
│   ├── daemon/         # Background watcher
│   ├── mcp_server.py   # MCP tool server
│   └── setup_wizard.py # Interactive installer
├── tests/
│   ├── fixtures/       # Sample JSONL files
│   └── unit/
├── install.sh          # macOS/Linux installer
├── install.ps1         # Windows installer
└── run.py              # Dev server entry point
```

---

## 🔒 Security Notes

- **Local only** — the web server binds to `127.0.0.1` by default. Do not expose it publicly without adding authentication.
- **Session data stays local** — nothing leaves your machine. LLM calls go through `claude -p` / `codex exec`, not direct API calls.
- **Sensitive content** — JSONL sessions may contain code, file contents, or credentials captured during tool use. The search index does not mask secrets by default.

---

## 🤝 Contributing

```bash
git clone https://github.com/Dradradre/claude-code-helper-with-codex && cd claude-code-helper-with-codex
uv sync
uv run pytest        # run tests
uv run ruff check .  # lint
uv run python run.py # dev server on :7878
```

PRs welcome. For large changes, open an issue first.

---

## 📄 License

[MIT](LICENSE) — free to use, modify, and distribute.

---

<div align="center">

Made for developers who use both Claude Code and Codex CLI daily.

[⭐ Star on GitHub](https://github.com/Dradradre/claude-code-helper-with-codex) · [🐛 Report Bug](https://github.com/Dradradre/claude-code-helper-with-codex/issues) · [💡 Request Feature](https://github.com/Dradradre/claude-code-helper-with-codex/issues)

</div>
