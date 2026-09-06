# PowerShell bootstrap script for TraceFace (Windows)
# Creates a Python virtual environment, installs dependencies, runs diagnostics.

# Stop on errors
$ErrorActionPreference = "Stop"

# Navigate to repository root (parent of scripts/ directory)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
Set-Location $RepoRoot

Write-Host "TraceFace Setup — Windows" -ForegroundColor Cyan
Write-Host "Repository root: $RepoRoot"

# Check Python is available
try {
    $pyVersion = python --version 2>&1
    Write-Host "Found: $pyVersion"
} catch {
    Write-Host "ERROR: Python is not installed or not in PATH." -ForegroundColor Red
    Write-Host "Download Python 3.10–3.12 from https://www.python.org/downloads/"
    exit 1
}

# Create virtual environment if it does not exist
if (-Not (Test-Path -Path ".venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}

# Activate the environment
& ".\.venv\Scripts\Activate.ps1"

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Run diagnostics (allow non-zero exit — just report)
Write-Host "`nRunning environment diagnostics..." -ForegroundColor Cyan
python main.py doctor
$doctorExit = $LASTEXITCODE

Write-Host ""
if ($doctorExit -eq 0) {
    Write-Host "Setup complete! All checks passed." -ForegroundColor Green
} else {
    Write-Host "Setup complete with warnings. Review the doctor output above." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Next steps:"
Write-Host "  .\.venv\Scripts\Activate.ps1                              # activate venv"
Write-Host "  python main.py proof-verify fixtures\demo_evidence.json   # verify published proof"
Write-Host "  python main.py --image path\to\face.jpg --no-blockchain   # live mode"
