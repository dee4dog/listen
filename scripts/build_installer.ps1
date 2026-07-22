# Builds a native Windows installer for Listen:
#   1. PyInstaller freezes the app into dist\Listen (onedir bundle).
#   2. Inno Setup compiles that folder into dist_installer\Listen-Setup-<version>.exe
#
# Requires .\scripts\setup.ps1 to have been run already, and Inno Setup 6
# installed (winget install JRSoftware.InnoSetup).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path .venv)) {
    Write-Host "Virtual environment not found. Run .\scripts\setup.ps1 first."
    exit 1
}

Write-Host "Installing/upgrading PyInstaller..."
.\.venv\Scripts\python -m pip install --upgrade pyinstaller | Out-Null

if (-not (Test-Path assets\icon.ico)) {
    Write-Host "Generating assets\icon.ico from assets\icon.png..."
    .\.venv\Scripts\python -c "from PIL import Image; Image.open('assets/icon.png').save('assets/icon.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
}

Write-Host "Removing previous build output..."
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

Write-Host "Freezing the app with PyInstaller (this can take several minutes)..."
.\.venv\Scripts\pyinstaller.exe scripts\listen.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

$iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    # winget may install Inno Setup machine-wide or per-user, so check both.
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    $iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $iscc) {
    Write-Host "Inno Setup (ISCC.exe) not found. Install it with:"
    Write-Host "  winget install JRSoftware.InnoSetup"
    exit 1
}

Write-Host "Compiling the installer with Inno Setup..."
& $iscc scripts\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compile failed." }

Write-Host ""
Write-Host "Done. Installer written to dist_installer\"
Get-ChildItem dist_installer\*.exe | ForEach-Object { Write-Host "  $($_.FullName)" }
