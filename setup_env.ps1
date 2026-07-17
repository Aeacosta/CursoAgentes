# setup_env.ps1 — Installs all dependencies into the existing .venv.
#
# Usage (from the project root in PowerShell):
#   .\setup_env.ps1
#
# Optional: recreate the virtual environment from scratch instead of reusing it.
#   .\setup_env.ps1 -Recreate

param(
    [switch]$Recreate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$VENV_DIR  = ".venv"
$PYTHON    = "python"
$VENV_PIP  = "$VENV_DIR\Scripts\pip.exe"
$VENV_PY   = "$VENV_DIR\Scripts\python.exe"

# ── 1. Verify system Python is available ─────────────────────────────────────
Write-Host "`n[1/5] Checking Python..." -ForegroundColor Cyan
try {
    $pyVersion = & $PYTHON --version 2>&1
    Write-Host "      Found: $pyVersion" -ForegroundColor Green
} catch {
    Write-Error "Python not found. Install Python 3.10+ and add it to PATH."
    exit 1
}

# ── 2. Create (or reuse) virtual environment ──────────────────────────────────
Write-Host "`n[2/5] Virtual environment..." -ForegroundColor Cyan
if (Test-Path $VENV_DIR) {
    if ($Recreate) {
        Write-Host "      -Recreate flag set — removing existing environment." -ForegroundColor Yellow
        Remove-Item -Recurse -Force $VENV_DIR
        & $PYTHON -m venv $VENV_DIR
        Write-Host "      Virtual environment recreated." -ForegroundColor Green
    } else {
        Write-Host "      '$VENV_DIR' already exists — reusing it." -ForegroundColor Green
    }
} else {
    & $PYTHON -m venv $VENV_DIR
    Write-Host "      Virtual environment created at '$VENV_DIR'." -ForegroundColor Green
}

# ── 3. Upgrade pip ────────────────────────────────────────────────────────────
Write-Host "`n[3/5] Upgrading pip..." -ForegroundColor Cyan
& $VENV_PY -m pip install --upgrade pip --quiet
Write-Host "      pip upgraded." -ForegroundColor Green

# ── 4. Install core pipeline dependencies ────────────────────────────────────
Write-Host "`n[4/5] Installing core dependencies from requirements.txt..." -ForegroundColor Cyan
if (-not (Test-Path "requirements.txt")) {
    Write-Error "requirements.txt not found. Run this script from the project root."
    exit 1
}
& $VENV_PIP install -r requirements.txt
Write-Host "      Core dependencies installed." -ForegroundColor Green

# ── 5. Install dashboard dependencies ────────────────────────────────────────
Write-Host "`n[5/5] Installing dashboard dependencies from dashboard/requirements.txt..." -ForegroundColor Cyan
if (Test-Path "dashboard\requirements.txt") {
    & $VENV_PIP install -r dashboard\requirements.txt
    Write-Host "      Dashboard dependencies installed." -ForegroundColor Green
} else {
    Write-Host "      dashboard/requirements.txt not found — skipping." -ForegroundColor Yellow
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host "`n✓ Environment ready." -ForegroundColor Green
Write-Host "  Activate  :  .\.venv\Scripts\Activate.ps1"  -ForegroundColor White
Write-Host "  Run agent :  .\.venv\Scripts\python.exe main.py" -ForegroundColor White
Write-Host "  Dashboard :  .\.venv\Scripts\python.exe dashboard\app.py`n" -ForegroundColor White
