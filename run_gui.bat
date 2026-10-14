@echo off
setlocal
cd /d "%~dp0"

rem Interfaz principal: web (API FastAPI + front React) en http://127.0.0.1:8765/
rem Conserva el nombre run_gui.bat por los accesos directos ya creados: la interfaz de
rem escritorio Tkinter se retiro (spec 001, RF-16) y esta es la unica.

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

rem El front se compila si falta o si su codigo es mas reciente que la compilacion
rem (spec 001, RF-27): antes solo si faltaba, y tras un cambio se seguia sirviendo
rem la version anterior sin avisar. Node.js solo hace falta para compilar.
"%PY%" -m igea_dgs.web.runtime --front
if errorlevel 1 (
  where npm 1>nul 2>nul
  if errorlevel 1 (
    if not exist "frontend\dist\index.html" (
      echo.
      echo Falta compilar la interfaz web y no se encuentra Node.js ^(npm^).
      echo Instale Node.js 20 o superior y vuelva a ejecutar, o convierta por consola con igea-dgs convert.
      pause
      exit /b 1
    )
    echo AVISO: no se encuentra Node.js ^(npm^); se abre la interfaz compilada anterior.
  ) else (
    echo Compilando la interfaz web...
    pushd frontend
    call npm install --no-audit --no-fund
    call npm run build
    popd
  )
)

echo Abriendo la interfaz web en el navegador...
"%PY%" -m igea_dgs.web
if errorlevel 2 (
  echo.
  echo El puerto 8765 ya esta en uso: cierre la otra ventana del Conversor y vuelva a abrirlo.
  pause
  goto :fin
)
if errorlevel 1 (
  echo.
  echo Si faltan librerias:  "%PY%" -m pip install -r requirements.txt
  pause
)
:fin
endlocal
exit /b 0

:dependency_error
echo.
echo No se pudo preparar el entorno completo TXT, MDB y VNR-GIS.
echo Revise la salida anterior y AUDIT\web_runtime si existe.
pause
endlocal
exit /b 1
