@echo off
setlocal
cd /d "%~dp0.."

rem DigSilent PowerFactory 2024 Python API (adjust version if needed)
if not defined PF_PYTHON set "PF_PYTHON=C:\Program Files\DIgSILENT\PowerFactory 2024\Python\3.12"
if exist "%PF_PYTHON%\powerfactory.pyd" set "PYTHONPATH=%PF_PYTHON%;%PYTHONPATH%"

if "%~1"=="" (
  echo Uso:
  echo   tools\run_powerfactory_gate.bat output\gui\AL104.dgs output\gui\AL104_geography.json
  echo.
  echo Requiere PowerFactory instalado/licenciado. Preferible tener PF abierto.
  exit /b 1
)

set "DGS=%~1"
set "MANIFEST=%~2"
if "%MANIFEST%"=="" (
  echo Falta manifest geography.json
  exit /b 1
)

python tools\powerfactory_acceptance.py --import-dgs "%DGS%" --manifest "%MANIFEST%" --require-diagram --run-load-flow --fix-until-converge --ensure-scenario
set ERR=%ERRORLEVEL%
endlocal & exit /b %ERR%
