[CmdletBinding()]
param(
    [switch]$SkipPowerFactoryCheck
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$Constraints = Join-Path $ProjectRoot 'constraints.txt'
$Requirements = Join-Path $ProjectRoot 'requirements-dev.txt'
$PowerFactoryModule = 'C:\Program Files\DIgSILENT\PowerFactory 2024\Python\3.12\powerfactory.pyd'

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    py -3.12 -m venv (Join-Path $ProjectRoot '.venv')
}

$Runtime = & $Python -c "import json, platform, struct, sys; print(json.dumps({'version': list(sys.version_info[:2]), 'bits': struct.calcsize('P') * 8, 'implementation': platform.python_implementation()}))" | ConvertFrom-Json
if ($Runtime.version[0] -ne 3 -or $Runtime.version[1] -ne 12 -or $Runtime.bits -ne 64) {
    throw "Se requiere Python CPython 3.12 x64; encontrado $($Runtime.implementation) $($Runtime.version -join '.') $($Runtime.bits)-bit."
}

& $Python -m pip install --disable-pip-version-check --upgrade pip

$ConstraintArgs = @()
$PinnedLines = Get-Content -LiteralPath $Constraints | Where-Object {
    $Line = $_.Trim()
    $Line -and -not $Line.StartsWith('#')
}
if ($PinnedLines) {
    $ConstraintArgs = @('-c', $Constraints)
}
& $Python -m pip install --disable-pip-version-check -r $Requirements @ConstraintArgs

& $Python -c "import fastapi, geopandas, hypothesis, httpx, leafmap, mypy, openpyxl, pandas, platformdirs, pydantic, pyproj, pytest, shapely, uvicorn"

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw 'Se requiere Node.js con npm para construir la interfaz React.'
}
& npm --prefix (Join-Path $ProjectRoot 'web') ci
if ($LASTEXITCODE) { throw "npm ci falló con código $LASTEXITCODE" }

if (-not $SkipPowerFactoryCheck -and -not (Test-Path -LiteralPath $PowerFactoryModule -PathType Leaf)) {
    throw "No se encontró la API PowerFactory 2024/Python 3.12 en: $PowerFactoryModule"
}

Write-Host "Bootstrap OK: Python 3.12 x64 y dependencias verificadas."
if (-not $SkipPowerFactoryCheck) {
    Write-Host "PowerFactory API detectada: $PowerFactoryModule"
}
