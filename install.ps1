# cchwc 설치 부트스트랩 (Windows PowerShell)
# 사용: .\install.ps1  또는  irm <raw-url>/install.ps1 | iex

$ErrorActionPreference = "Stop"

# ── 필수 확인 ─────────────────────────────────────────────────────

if (-not (Get-Command "node" -ErrorAction SilentlyContinue)) {
    Write-Host "[!] Node.js가 필요합니다: https://nodejs.org" -ForegroundColor Yellow
    exit 1
}

# ── uv 설치 ──────────────────────────────────────────────────────

if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
    Write-Host "[*] uv 설치 중..." -ForegroundColor Cyan
    irm https://astral.sh/uv/install.ps1 | iex
    $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
}

# ── repo 클론 / 업데이트 ──────────────────────────────────────────

$installDir = "$env:USERPROFILE\cchwc"

if (-not (Test-Path $installDir)) {
    $repoUrl = Read-Host "[?] Git 저장소 URL (비공개 레포)"
    if ($repoUrl) {
        git clone $repoUrl $installDir
    } else {
        Write-Host "[!] URL을 입력하거나 수동으로 $installDir 에 소스를 복사하세요." -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "[*] 기존 설치 업데이트..." -ForegroundColor Cyan
    Push-Location $installDir; git pull; Pop-Location
}

# ── 의존성 설치 ───────────────────────────────────────────────────

Push-Location $installDir
uv sync
Write-Host ""

# ── 설치 마법사 실행 ─────────────────────────────────────────────

Write-Host "[*] 설치 마법사 시작..." -ForegroundColor Cyan
uv run cchwc setup
Pop-Location
