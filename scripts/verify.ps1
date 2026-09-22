[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw 'Falta .venv. Ejecute scripts/bootstrap.ps1 primero.'
}

Push-Location $ProjectRoot
try {
    & $Python -m ruff check src tests --select E9,F63,F7,F82
    if ($LASTEXITCODE) { throw "Ruff falló con código $LASTEXITCODE" }

    # Los modulos monoliticos heredados tienen una deuda basal registrada (95 errores).
    # La puerta estricta cubre todos los paquetes nuevos; los heredados se incorporan
    # conforme se migren en las tareas funcionales del plan.
    $LegacyModules = '(^|[\\/])(model|geography|dgs|validate|batch|gui)\.py$'
    & $Python -m mypy src/igea_dgs --ignore-missing-imports --exclude $LegacyModules
    if ($LASTEXITCODE) { throw "Mypy falló con código $LASTEXITCODE" }

    # El inventario basal contiene hallazgos informativos de severidad baja.
    # La puerta bloquea severidad media/alta; los bajos siguen visibles en auditorias completas.
    & $Python -m bandit -r src -q -ll
    if ($LASTEXITCODE) { throw "Bandit falló con código $LASTEXITCODE" }

    & $Python -m pytest --cov=igea_dgs --cov-report=term-missing
    if ($LASTEXITCODE) { throw "Pytest falló con código $LASTEXITCODE" }

    & $Python -m pip check
    if ($LASTEXITCODE) { throw "pip check falló con código $LASTEXITCODE" }

    & npm --prefix web run lint
    if ($LASTEXITCODE) { throw "ESLint falló con código $LASTEXITCODE" }
    & npm --prefix web run typecheck
    if ($LASTEXITCODE) { throw "TypeScript falló con código $LASTEXITCODE" }
    & npm --prefix web test -- --run
    if ($LASTEXITCODE) { throw "Vitest falló con código $LASTEXITCODE" }
    & npm --prefix web run build
    if ($LASTEXITCODE) { throw "Vite build falló con código $LASTEXITCODE" }
}
finally {
    Pop-Location
}
