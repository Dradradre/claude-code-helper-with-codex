#!/usr/bin/env bash
# cchwc 설치 스크립트 (macOS / Linux)
#
# 사용법 A — 클론 후:
#   git clone https://github.com/YOUR/cchwc && cd cchwc && bash install.sh
#
# 사용법 B — 원클릭 (클론 포함):
#   curl -LsSf https://raw.githubusercontent.com/YOUR/cchwc/main/install.sh | bash

set -e

REPO_URL="https://github.com/YOUR/cchwc"  # TODO: 실제 URL로 교체
INSTALL_DIR="$HOME/cchwc"

# ── 이미 repo 안에서 실행 중인지 확인 ────────────────────────────
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || pwd)"
if [ -f "$SELF_DIR/pyproject.toml" ]; then
  INSTALL_DIR="$SELF_DIR"
fi

# ── Node.js 확인 ──────────────────────────────────────────────────
if ! command -v node &>/dev/null; then
  echo "[!] Node.js가 필요합니다: https://nodejs.org"
  exit 1
fi

# ── uv 설치 ──────────────────────────────────────────────────────
if ! command -v uv &>/dev/null && ! [ -x "$HOME/.local/bin/uv" ]; then
  echo "[*] uv 패키지 매니저 설치 중..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

export PATH="$HOME/.local/bin:$PATH"

# ── repo 클론 (필요한 경우만) ─────────────────────────────────────
if [ ! -f "$INSTALL_DIR/pyproject.toml" ]; then
  if [ -z "$CCHWC_REPO" ]; then
    read -rp "[?] Git 저장소 URL [$REPO_URL]: " input
    CCHWC_REPO="${input:-$REPO_URL}"
  fi
  git clone "$CCHWC_REPO" "$INSTALL_DIR"
fi

# ── 의존성 설치 ───────────────────────────────────────────────────
cd "$INSTALL_DIR"
uv sync

# ── 설치 마법사 ──────────────────────────────────────────────────
echo ""
uv run cchwc setup
