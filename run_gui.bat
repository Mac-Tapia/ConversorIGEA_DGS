@echo off
setlocal
cd /d "%~dp0"

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY set "PY=python"

set PYTHONPATH=src
"%PY%" -c "import igea_dgs" 1>nul 2>nul
if errorlevel 1 (
  echo Instalando paquete en modo editable...
  "%PY%" -m pip install -e ".[dev]" --disable-pip-version-check
)

echo Abriendo interfaz grafica...
"%PY%" -m igea_dgs.gui
if errorlevel 1 (
  echo.
  echo Si falta pyproj:  "%PY%" -m pip install pyproj
  pause
)
endlocal
