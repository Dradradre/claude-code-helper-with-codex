#!/usr/bin/env bash
# cchwc installer for macOS / Linux
#
# Clone first:
#   git clone https://github.com/Dradradre/claude-code-helper-with-codex && cd claude-code-helper-with-codex && bash install.sh
#
# One-liner:
#   curl -LsSf https://raw.githubusercontent.com/Dradradre/claude-code-helper-with-codex/main/install.sh | bash

set -Eeuo pipefail

DEFAULT_REPO_URL="https://github.com/Dradradre/claude-code-helper-with-codex"
REPO_URL="${CCHWC_REPO:-$DEFAULT_REPO_URL}"

log() {
  printf '[*] %s\n' "$1"
}

warn() {
  printf '[!] %s\n' "$1" >&2
}

is_cchwc_repo() {
  local dir="$1"
  [ -f "$dir/pyproject.toml" ] && grep -Eq 'name[[:space:]]*=[[:space:]]*"cchwc"' "$dir/pyproject.toml"
}

script_dir() {
  local source="${BASH_SOURCE[0]:-$0}"
  if [ -n "$source" ] && [ "$source" != "bash" ] && [ -f "$source" ]; then
    cd "$(dirname "$source")" >/dev/null 2>&1 && pwd
  fi
}

SELF_DIR="$(script_dir || true)"
if [ -n "${CCHWC_INSTALL_DIR:-}" ]; then
  INSTALL_DIR="$CCHWC_INSTALL_DIR"
elif [ -n "$SELF_DIR" ] && is_cchwc_repo "$SELF_DIR"; then
  INSTALL_DIR="$SELF_DIR"
else
  INSTALL_DIR="$HOME/cchwc"
fi
INSTALL_PARENT="$(dirname "$INSTALL_DIR")"
mkdir -p "$INSTALL_PARENT"
INSTALL_DIR="$(cd "$INSTALL_PARENT" && pwd)/$(basename "$INSTALL_DIR")"

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
  log "Installing uv package manager"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

if ! command -v uv >/dev/null 2>&1; then
  warn "uv install failed. Install manually: https://docs.astral.sh/uv/"
  exit 1
fi

if ! is_cchwc_repo "$INSTALL_DIR"; then
  if ! command -v git >/dev/null 2>&1; then
    warn "git is required to clone cchwc: https://git-scm.com/downloads"
    exit 1
  fi

  if [ -e "$INSTALL_DIR" ] && [ "$(find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 2>/dev/null | head -n 1)" ]; then
    warn "Install directory exists but is not cchwc: $INSTALL_DIR"
    warn "Remove it, choose CCHWC_INSTALL_DIR, or run install.sh inside a cloned repo."
    exit 1
  fi

  log "Cloning $REPO_URL to $INSTALL_DIR"
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

export UV_CACHE_DIR="${UV_CACHE_DIR:-$INSTALL_DIR/.uv-cache}"
mkdir -p "$UV_CACHE_DIR"

cd "$INSTALL_DIR"

log "Installing Python dependencies from uv.lock"
uv sync --frozen --no-dev

log "Starting setup wizard"
uv run --no-dev cchwc setup --skip-deps
