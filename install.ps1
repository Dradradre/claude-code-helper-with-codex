# cchwc installer for Windows PowerShell 5.1+
#
# Clone first:
#   git clone https://github.com/Dradradre/claude-code-helper-with-codex; cd claude-code-helper-with-codex; .\install.ps1
#
# One-liner:
#   irm https://raw.githubusercontent.com/Dradradre/claude-code-helper-with-codex/main/install.ps1 | iex

$ErrorActionPreference = "Stop"

$DefaultRepoUrl = "https://github.com/Dradradre/claude-code-helper-with-codex"
$RepoUrl = if ($env:CCHWC_REPO) { $env:CCHWC_REPO } else { $DefaultRepoUrl }

function Write-Step($Message) {
    Write-Host "[*] $Message" -ForegroundColor Cyan
}

function Write-Fail($Message) {
    Write-Host "[!] $Message" -ForegroundColor Yellow
}

function Get-CommandPath($Name) {
    $cmd = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Test-CchwcRepo($Path) {
    $pyproject = Join-Path $Path "pyproject.toml"
    if (-not (Test-Path $pyproject)) { return $false }
    return [bool](Select-String -Path $pyproject -Pattern 'name\s*=\s*"cchwc"' -Quiet)
}

function Invoke-Checked($FilePath, [string[]]$Arguments) {
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

function Get-ScriptDirectory {
    if ($PSScriptRoot) { return $PSScriptRoot }
    if ($MyInvocation.MyCommand.Path) {
        return Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    return $null
}

$SelfDir = Get-ScriptDirectory
if ($env:CCHWC_INSTALL_DIR) {
    $InstallDir = $env:CCHWC_INSTALL_DIR
} elseif ($SelfDir -and (Test-CchwcRepo $SelfDir)) {
    $InstallDir = $SelfDir
} else {
    $InstallDir = Join-Path $env:USERPROFILE "cchwc"
}
$InstallDir = [System.IO.Path]::GetFullPath($InstallDir)

$UvPath = Get-CommandPath "uv"
if (-not $UvPath) {
    $UvPath = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
}

if (-not (Test-Path $UvPath)) {
    Write-Step "Installing uv package manager"
    irm https://astral.sh/uv/install.ps1 | iex
    $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
    $UvPath = Get-CommandPath "uv"
    if (-not $UvPath) {
        $UvPath = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
    }
}

if (-not (Test-Path $UvPath)) {
    Write-Fail "uv install failed. Install manually: https://docs.astral.sh/uv/"
    exit 1
}

if (-not (Test-CchwcRepo $InstallDir)) {
    $GitPath = Get-CommandPath "git"
    if (-not $GitPath) {
        Write-Fail "git is required to clone cchwc: https://git-scm.com/download/win"
        exit 1
    }

    if (Test-Path $InstallDir) {
        $items = Get-ChildItem -LiteralPath $InstallDir -Force -ErrorAction SilentlyContinue
        if ($items) {
            Write-Fail "Install directory exists but is not cchwc: $InstallDir"
            Write-Fail "Remove it, choose CCHWC_INSTALL_DIR, or run install.cmd inside a cloned repo."
            exit 1
        }
    }

    Write-Step "Cloning $RepoUrl to $InstallDir"
    Invoke-Checked $GitPath @("clone", $RepoUrl, $InstallDir)
}

if (-not $env:UV_CACHE_DIR) {
    $env:UV_CACHE_DIR = Join-Path $InstallDir ".uv-cache"
}
New-Item -ItemType Directory -Force -Path $env:UV_CACHE_DIR | Out-Null

Push-Location $InstallDir
try {
    Write-Step "Installing Python dependencies from uv.lock"
    Invoke-Checked $UvPath @("sync", "--frozen", "--no-dev")

    Write-Step "Registering cchwc command"
    Invoke-Checked $UvPath @("tool", "install", "--editable", ".")

    Write-Step "Starting setup wizard"
    Invoke-Checked $UvPath @("run", "--no-dev", "cchwc", "setup", "--skip-deps")
} finally {
    Pop-Location
}
