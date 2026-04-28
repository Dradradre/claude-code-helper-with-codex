# cchwc 설치 스크립트 (Windows PowerShell)
# 사용법: irm https://raw.githubusercontent.com/.../install.ps1 | iex
#         또는: .\install.ps1

$ErrorActionPreference = "Stop"

function Write-Step { param($msg) Write-Host "`n[*] $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "    [OK] $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "    [!]  $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "    [X]  $msg" -ForegroundColor Red }

Write-Host @"
┌─────────────────────────────────────────┐
│   cchwc — Claude + Codex Session Hub    │
│   설치 스크립트 (Windows)               │
└─────────────────────────────────────────┘
"@ -ForegroundColor White

# ── 1. 의존성 체크 ─────────────────────────────────────────────────────────

Write-Step "의존성 확인"

$missing = @()

if (-not (Get-Command "node" -ErrorAction SilentlyContinue)) {
    Write-Warn "Node.js 없음 → https://nodejs.org 에서 LTS 버전 설치 필요"
    $missing += "node"
} else {
    $nodeVer = node --version
    Write-Ok "Node.js $nodeVer"
}

if (-not (Get-Command "git" -ErrorAction SilentlyContinue)) {
    Write-Warn "git 없음 → https://git-scm.com 에서 설치 필요"
    $missing += "git"
} else {
    Write-Ok "git $(git --version)"
}

# Python (uv가 자동 설치하므로 선택)
if (Get-Command "python" -ErrorAction SilentlyContinue) {
    Write-Ok "Python $(python --version)"
} else {
    Write-Warn "Python 없음 (uv가 자동 설치합니다)"
}

# ── 2. uv 설치 ──────────────────────────────────────────────────────────────

Write-Step "uv 패키지 매니저 확인"

if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
    Write-Host "    uv 설치 중..." -ForegroundColor Gray
    irm https://astral.sh/uv/install.ps1 | iex
    $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
    Write-Ok "uv 설치 완료"
} else {
    Write-Ok "uv $(uv --version)"
}

# ── 3. cchwc 소스 ───────────────────────────────────────────────────────────

Write-Step "cchwc 소스 준비"

$installDir = "$env:USERPROFILE\cchwc"

if (Test-Path $installDir) {
    Write-Host "    기존 설치 발견 → git pull" -ForegroundColor Gray
    Push-Location $installDir
    git pull
    Pop-Location
} else {
    Write-Warn "Git 저장소 URL을 입력하세요 (Enter = 건너뜀)"
    $repoUrl = Read-Host "    Repo URL"
    if ($repoUrl) {
        git clone $repoUrl $installDir
        Write-Ok "클론 완료 → $installDir"
    } else {
        Write-Warn "클론 건너뜀 — 수동으로 $installDir 에 소스를 복사하세요"
    }
}

if (Test-Path $installDir) {
    Push-Location $installDir
    uv sync
    Write-Ok "의존성 설치 완료"
    Pop-Location
}

# ── 4. Claude CLI ────────────────────────────────────────────────────────────

Write-Step "Claude CLI 확인"

if (-not (Get-Command "claude" -ErrorAction SilentlyContinue)) {
    Write-Host "    설치 중: npm install -g @anthropic-ai/claude-code" -ForegroundColor Gray
    npm install -g @anthropic-ai/claude-code
    Write-Ok "Claude CLI 설치 완료"
    Write-Warn "로그인 필요 → 아래 명령 실행: claude login"
} else {
    Write-Ok "Claude CLI $(claude --version 2>$null)"
}

# ── 5. Codex CLI ─────────────────────────────────────────────────────────────

Write-Step "Codex CLI 확인"

if (-not (Get-Command "codex" -ErrorAction SilentlyContinue)) {
    Write-Host "    설치 중: npm install -g @openai/codex" -ForegroundColor Gray
    npm install -g @openai/codex
    Write-Ok "Codex CLI 설치 완료"
    Write-Warn "로그인 필요 → 아래 명령 실행: codex login"
} else {
    Write-Ok "Codex CLI $(codex --version 2>$null)"
}

# ── 6. 초기 설정 ─────────────────────────────────────────────────────────────

Write-Step "초기 설정"

Write-Host @"

    스캔 범위를 설정합니다.
    [1] 전체 (~/.claude 전체 세션)
    [2] 현재 디렉토리만
    [3] 특정 경로 지정
"@

$choice = Read-Host "    선택 (기본: 1)"
if ($choice -eq "2") {
    $scanMode = "project"
    $scanPath = Get-Location
    Write-Warn "경로: $scanPath (나중에 cchwc config add-project <path> 로 추가 가능)"
} elseif ($choice -eq "3") {
    $scanMode = "project"
    $scanPath = Read-Host "    경로 입력"
} else {
    $scanMode = "global"
    $scanPath = $null
}

# ── 7. 초기 스캔 ─────────────────────────────────────────────────────────────

if (Test-Path $installDir) {
    Write-Step "초기 세션 스캔"
    Push-Location $installDir
    if ($scanMode -eq "global") {
        uv run cchwc scan --global
    } elseif ($scanPath) {
        uv run cchwc scan --cwd $scanPath
    } else {
        uv run cchwc scan --global
    }
    Pop-Location
}

# ── 8. 완료 ──────────────────────────────────────────────────────────────────

Write-Host @"

┌─────────────────────────────────────────┐
│   설치 완료!                            │
└─────────────────────────────────────────┘

  서버 시작:
    cd $installDir
    uv run python run.py

  브라우저: http://127.0.0.1:7878

  인증이 필요하면:
    claude login
    codex login

  스캔 범위 추가:
    uv run cchwc config add-project C:\path\to\project
    uv run cchwc scan

"@ -ForegroundColor White
