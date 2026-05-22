# Miser v1.5 Windows installer (PowerShell)
# Usage: powershell -ExecutionPolicy Bypass -File install.ps1
# Automates: Python check, Ollama detection, service registration, CLAUDE.md patch

$ErrorActionPreference = "Stop"
$MISER_DIR = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

function Write-Green  { Write-Host $args -ForegroundColor Green }
function Write-Yellow { Write-Host $args -ForegroundColor Yellow }
function Write-Red    { Write-Host $args -ForegroundColor Red }
function Write-Bold   { Write-Host $args -ForegroundColor Cyan }

Write-Bold "=========================================="
Write-Bold "   Miser v1.5  -  Windows Installer"
Write-Bold "=========================================="
Write-Host ""

# ── 1. Python check ──────────────────────────────────────────────────────
Write-Yellow "-> Checking Python..."
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $python) {
    Write-Red "X Python 3.10+ not found."
    Write-Host "  Install from: https://python.org/downloads/ (check 'Add to PATH')"
    Write-Host "  Or run: winget install Python.Python.3.12"
    exit 1
}
$pyVer = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Green "  OK Python $pyVer"

# ── 2. Pip dependencies ──────────────────────────────────────────────────
Write-Yellow "-> Installing Python dependencies..."
& $python -m pip install --quiet flask requests rich
Write-Green "  OK flask requests rich"

# ── 3. Ollama check ──────────────────────────────────────────────────────
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    Write-Red "X Ollama not found."
    Write-Host "  Download: https://ollama.com/download/windows"
    Write-Host "  Or run: winget install Ollama.Ollama"
    Write-Host "  After installing, re-run: install.ps1"
    exit 1
}
Write-Green "  OK Ollama detected"

# ── 4. Pull default model ────────────────────────────────────────────────
Write-Yellow "-> Pulling qwen3.5:4b (~3.4 GB)..."
$models = & ollama list 2>$null
if ($models -match "qwen3.5:4b") {
    Write-Green "  OK qwen3.5:4b already installed"
} else {
    & ollama pull qwen3.5:4b
    Write-Green "  OK qwen3.5:4b ready"
}

# ── 5. Register Windows Task Scheduler for auto-start ────────────────────
Write-Yellow "-> Creating scheduled task for auto-start..."
$taskName = "Miser"
$taskExists = schtasks /query /tn $taskName 2>$null
if ($taskExists) {
    Write-Yellow "  Task already exists, updating..."
    schtasks /delete /tn $taskName /f 2>$null | Out-Null
}
$action = New-ScheduledTaskAction -Execute $python.Source -Argument "`"$MISER_DIR\miser.py`"" -WorkingDirectory $MISER_DIR
$trigger = New-ScheduledTaskTrigger -AtLogon
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Green "  OK Miser will start automatically on login"

# ── 6. Patch CLAUDE.md ───────────────────────────────────────────────────
$CLAUDE_MD = "$env:USERPROFILE\.claude\CLAUDE.md"
if (-not (Test-Path (Split-Path $CLAUDE_MD))) {
    New-Item -ItemType Directory -Path (Split-Path $CLAUDE_MD) -Force | Out-Null
}

if ((Test-Path $CLAUDE_MD) -and (Get-Content $CLAUDE_MD -Raw) -match "miser-block") {
    Write-Yellow "  CLAUDE.md already patched, skipping"
} else {
    $block = @"

<!-- miser-block -->
## Miser - Local Token-Saver

Miser runs at http://localhost:7860.

import sys; sys.path.insert(0, r'$MISER_DIR')
from client import W

Auto-start: Miser launches at Windows login via Task Scheduler.
Check status: curl http://localhost:7860/health
Full API: $MISER_DIR\docs\MISER_FOR_CLAUDE.md
<!-- end-miser-block -->
"@
    Add-Content -Path $CLAUDE_MD -Value $block
    Write-Green "  OK Patched CLAUDE.md"
}

# ── 7. Start Miser now ───────────────────────────────────────────────────
Write-Yellow "-> Starting Miser..."
Start-Process -FilePath $python.Source -ArgumentList "$MISER_DIR\miser.py" -WindowStyle Hidden
Start-Sleep -Seconds 3
try {
    $status = Invoke-RestMethod -Uri "http://localhost:7860/health" -Method Get -TimeoutSec 5
    Write-Green "  OK Miser running (model: $($status.model))"
} catch {
    Write-Yellow "  Miser may still be starting. Check: http://localhost:7860/health"
}

Write-Host ""
Write-Bold "=========================================="
Write-Bold "   Miser v1.5 installed successfully"
Write-Bold "=========================================="
Write-Host "  Status : http://localhost:7860/health"
Write-Host "  Stop   : schtasks /end /tn Miser"
Write-Host "  Remove : scripts\uninstall.ps1 (or: schtasks /delete /tn Miser /f)"
Write-Host ""
Write-Green "Restart Claude Code - Miser will be used automatically."
