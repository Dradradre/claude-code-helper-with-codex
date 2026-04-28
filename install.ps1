# cchwc 설치 스크립트 (Windows PowerShell)
#
# 사용법 A — 클론 후:
#   git clone https://github.com/Dradradre/claude-code-helper-with-codex; cd cchwc; .\install.ps1
#
# 사용법 B — 원클릭 (클론 포함):
#   irm https://raw.githubusercontent.com/Dradradre/claude-code-helper-with-codex/main/install.ps1 | iex

$ErrorActionPreference = "Stop"
$REPO_URL = "https://github.com/Dradradre/claude-code-helper-with-codex"  

# ── 이미 repo 안에서 실행 중인지 확인 ────────────────────────────
$SelfDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $SelfDir) { $SelfDir = Get-Location }
$InstallDir = if (Test-Path "$SelfDir\pyproject.toml") { $SelfDir } else { "$env:USERPROFILE\cchwc" }

# ── Node.js 확인 ──────────────────────────────────────────────────
if (-not (Get-Command "node" -ErrorAction SilentlyContinue)) {
    Write-Host "[!] Node.js가 필요합니다: https://nodejs.org" -ForegroundColor Yellow
    exit 1
}

# ── uv 설치 ──────────────────────────────────────────────────────
$uvPath = (Get-Command "uv" -ErrorAction SilentlyContinue)?.Source
if (-not $uvPath) { $uvPath = "$env:USERPROFILE\.local\bin\uv.exe" }

if (-not (Test-Path $uvPath)) {
    Write-Host "[*] uv 패키지 매니저 설치 중..." -ForegroundColor Cyan
    irm https://astral.sh/uv/install.ps1 | iex
    $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
}

$env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"

# ── repo 클론 (필요한 경우만) ─────────────────────────────────────
if (-not (Test-Path "$InstallDir\pyproject.toml")) {
    $input = Read-Host "[?] Git 저장소 URL [$REPO_URL]"
    if ($input) { $REPO_URL = $input }
    git clone $REPO_URL $InstallDir
}

# ── 의존성 설치 ───────────────────────────────────────────────────
Push-Location $InstallDir
uv sync

# ── 설치 마법사 ──────────────────────────────────────────────────
Write-Host ""
uv run cchwc setup
Pop-Location
