#!/usr/bin/env bash
# cchwc 설치 부트스트랩 (macOS / Linux)
# 사용: bash install.sh  또는  curl -LsSf <raw-url>/install.sh | bash

set -e

# ── 필수 확인 ─────────────────────────────────────────────────────

if ! command -v node &>/dev/null; then
  echo "[!] Node.js가 필요합니다: https://nodejs.org"
  exit 1
fi

# ── uv 설치 ──────────────────────────────────────────────────────

if ! command -v uv &>/dev/null; then
  echo "[*] uv 설치 중..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# ── repo 클론 / 업데이트 ──────────────────────────────────────────

INSTALL_DIR="$HOME/cchwc"

if [ ! -d "$INSTALL_DIR" ]; then
  read -rp "[?] Git 저장소 URL (비공개 레포): " REPO_URL
  if [ -n "$REPO_URL" ]; then
    git clone "$REPO_URL" "$INSTALL_DIR"
  else
    echo "[!] URL을 입력하거나 수동으로 $INSTALL_DIR 에 소스를 복사하세요."
    exit 1
  fi
else
  echo "[*] 기존 설치 업데이트..."
  git -C "$INSTALL_DIR" pull
fi

# ── 의존성 설치 ───────────────────────────────────────────────────

cd "$INSTALL_DIR"
uv sync

# ── 설치 마법사 실행 ─────────────────────────────────────────────

echo ""
echo "[*] 설치 마법사 시작..."
uv run cchwc setup
