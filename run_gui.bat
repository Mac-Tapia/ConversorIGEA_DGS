@echo off
setlocal
cd /d "%~dp0"

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY set "PY=python"

set PYTHONPATH=src
"%PY%" -c "import igea_dgs; import pyproj" 1>nul 2>nul
if errorlevel 1 (
  echo Instalando dependencias de produccion desde requirements.txt...
  "%PY%" -m pip install -r "%~dp0requirements.txt" --disable-pip-version-check
)

echo Abriendo interfaz grafica...
"%PY%" -m igea_dgs.gui
if errorlevel 1 (
  echo.
  echo Si faltan librerias:  "%PY%" -m pip install -r requirements.txt
  echo O desactive Georreferenciacion en la GUI.
  pause
)
endlocal
