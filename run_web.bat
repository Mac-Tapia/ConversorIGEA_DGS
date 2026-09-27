@echo off
setlocal
cd /d "%~dp0"

rem Interfaz unica: web (API FastAPI + front React) en http://127.0.0.1:8765/
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY set "PY=python"

set PYTHONPATH=src
"%PY%" -c "import igea_dgs, pyproj, fastapi, uvicorn, multipart" 1>nul 2>nul
if errorlevel 1 (
  echo Instalando dependencias de produccion desde requirements.txt...
  "%PY%" -m pip install -r "%~dp0requirements.txt" --disable-pip-version-check
  if errorlevel 1 exit /b 1
)

rem El front se compila una vez. Hace falta Node.js solo para esto; despues, no.
if not exist "frontend\dist\index.html" (
  where npm 1>nul 2>nul
  if errorlevel 1 (
    echo.
    echo Falta compilar la interfaz web y no se encuentra Node.js ^(npm^).
    echo Instale Node.js 20 o superior y vuelva a ejecutar.
    pause
    exit /b 1
  )
  echo Compilando la interfaz web ^(una sola vez^)...
  pushd frontend
  call npm install --no-audit --no-fund
  if errorlevel 1 (
    popd
    exit /b 1
  )
  call npm run build
  if errorlevel 1 (
    popd
    exit /b 1
  )
  popd
)

echo Abriendo la interfaz web en el navegador...
"%PY%" -m igea_dgs.web
if errorlevel 1 (
  echo.
  echo Si faltan librerias:  "%PY%" -m pip install -r requirements.txt
  pause
)
endlocal
