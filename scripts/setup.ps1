# One-time setup: creates a virtual environment and installs dependencies.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path .venv)) {
    Write-Host "Creating virtual environment..."
    py -3 -m venv .venv
}

Write-Host "Installing dependencies (this downloads PyTorch and may take a while)..."
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\pip install -r requirements.txt

Write-Host ""
Write-Host "Setup complete. Start the app with: .\scripts\run.ps1"
