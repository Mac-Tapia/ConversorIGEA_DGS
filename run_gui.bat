@echo off
setlocal
cd /d "%~dp0"

rem Interfaz principal: web (API FastAPI + front React) en http://127.0.0.1:8765/
rem La interfaz de escritorio Tkinter sigue disponible en run_gui_escritorio.bat.

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY set "PY=python"

set PYTHONPATH=src
"%PY%" -m igea_dgs.web.runtime 1>nul 2>nul
if errorlevel 1 (
  echo Instalando dependencias de produccion para TXT, MDB y VNR-GIS...
  "%PY%" -m pip install -r "%~dp0requirements.txt" --disable-pip-version-check
  if errorlevel 1 goto :dependency_error
  "%PY%" -m igea_dgs.web.runtime
  if errorlevel 1 goto :dependency_error
)

rem El front se compila una vez. Hace falta Node.js solo para esto; despues, no.
if not exist "frontend\dist\index.html" (
  where npm 1>nul 2>nul
  if errorlevel 1 (
    echo.
    echo Falta compilar la interfaz web y no se encuentra Node.js ^(npm^).
    echo Instale Node.js 20 o superior y vuelva a ejecutar, o use run_gui_escritorio.bat.
    pause
    exit /b 1
  )
  echo Compilando la interfaz web ^(una sola vez^)...
  pushd frontend
  call npm install --no-audit --no-fund
  call npm run build
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
exit /b 0

:dependency_error
echo.
echo No se pudo preparar el entorno completo TXT, MDB y VNR-GIS.
echo Revise la salida anterior y AUDIT\web_runtime si existe.
pause
endlocal
exit /b 1
