[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$InputDir,
    [Parameter(Mandatory=$true)][string]$OutputDir,
    [switch]$RunPowerFactory
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$ResolvedInput = (Resolve-Path -LiteralPath $InputDir).Path
$ResolvedOutput = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputDir))
New-Item -ItemType Directory -Force -Path $ResolvedOutput | Out-Null

$Red = Get-ChildItem -LiteralPath $ResolvedInput -File -Filter '*.txt' | Where-Object Name -Match 'RED' | Select-Object -First 1
$Loads = Get-ChildItem -LiteralPath $ResolvedInput -File -Filter '*.txt' | Where-Object Name -Match 'CARGA' | Select-Object -First 1
$Equipment = Get-ChildItem -LiteralPath $ResolvedInput -File -Filter '*.txt' | Where-Object Name -Match 'BD.*EQUIPO|EQUIPO' | Select-Object -First 1
$ReportPath = Join-Path $ResolvedOutput 'acceptance_status.json'

if (-not $Red -or -not $Loads -or -not $Equipment) {
    @{
        status = 'blocked'
        gate = 'G1'
        code = 'INPUT_TXT_MISSING'
        input_dir = $ResolvedInput
        required = @('RED TXT', 'CARGA TXT', 'BD_Equipo TXT')
        powerfactory_executed = $false
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ReportPath -Encoding utf8
    Write-Warning "Aceptación bloqueada: faltan TXT. Evidencia: $ReportPath"
    exit 2
}

& $Python -m igea_dgs.cli inspect --red $Red.FullName --loads $Loads.FullName --equipment $Equipment.FullName --inventory-json (Join-Path $ResolvedOutput 'inventory.json') --json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -m igea_dgs.cli convert --red $Red.FullName --loads $Loads.FullName --equipment $Equipment.FullName --all --out-dir $ResolvedOutput --json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($RunPowerFactory) {
    Write-Warning 'La ejecución PowerFactory exige selección explícita del proyecto/caso administrado; use docs/POWERFACTORY_ACCEPTANCE.md.'
}
@{ status='converted'; gate='G4'; powerfactory_executed=$false; output_dir=$ResolvedOutput } |
    ConvertTo-Json | Set-Content -LiteralPath $ReportPath -Encoding utf8
