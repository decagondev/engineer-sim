# One-command setup for Windows (PowerShell).
# If you get a script-blocked error, run PowerShell once as:
#   powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Setting up the Engineering Flight Simulator..." -ForegroundColor Cyan
Write-Host ""

$py = "python"
if (-not (Get-Command $py -ErrorAction SilentlyContinue)) { $py = "py" }
if (-not (Get-Command $py -ErrorAction SilentlyContinue)) {
  Write-Host "Python is not installed. Get it from https://www.python.org/downloads/ (tick 'Add Python to PATH')." -ForegroundColor Yellow
  exit 1
}

& $py -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip | Out-Null
Write-Host "Installing dependencies (this can take a minute)..."
pip install -r requirements.txt | Out-Null
Write-Host "Done installing." -ForegroundColor Green
Write-Host ""

python doctor.py

Write-Host ""
Write-Host "------------------------------------------------------------"
Write-Host "Next time, activate the environment first:"
Write-Host "    .\.venv\Scripts\Activate.ps1"
Write-Host "Then start it with the command the check suggested above."
Write-Host "------------------------------------------------------------"
