# Create the project-local Python environment (.venv) for tools/collect.
# Usage (repo root):  pwsh tools/setup.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".venv"

if (-not (Test-Path $venv)) {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) { & $py.Source -m venv $venv } else { & (Get-Command py -ErrorAction Stop).Source -3 -m venv $venv }
}
$python = Join-Path $venv "Scripts\python.exe"
& $python -m pip install --quiet --upgrade pip
& $python -m pip install --quiet -r (Join-Path $PSScriptRoot "requirements.txt")

$envFile = Join-Path $root ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $root ".env.example") $envFile
    Write-Host "Created .env from .env.example. Set EDINET_API_KEY if available."
}
& $python -I (Join-Path $PSScriptRoot "collect\preflight.py")
