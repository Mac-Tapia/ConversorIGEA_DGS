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
set PYTHONDONTWRITEBYTECODE=1
rem 086:RF-39: arrancar nunca instala. Instalaba de internet lo que faltara, y un paquete mas nuevo o una red
rem cortada cambiaba el programa o lo dejaba a medias en mitad de un arranque.
"%PY%" -m convertersmartgrid.web.runtime
if errorlevel 1 goto :dependency_error

rem El front se compila si falta o si su codigo es mas reciente que la compilacion
rem (spec 001, RF-27): antes solo si faltaba, y tras un cambio se seguia sirviendo
rem la version anterior sin avisar. Node.js solo hace falta para compilar, y sus paquetes
rem se instalan aparte: compilar no sale a internet (086:RF-39).
"%PY%" -m convertersmartgrid.web.runtime --front
if errorlevel 1 (
  where npm 1>nul 2>nul
  if errorlevel 1 (
    echo.
    echo Falta una compilacion completa y actual de la interfaz y no se encuentra Node.js ^(npm^).
    echo Instale la version de Node.js declarada en frontend/package.json y vuelva a ejecutar.
    goto :front_error
  ) else (
    echo Compilando la interfaz web...
    if not exist "frontend\node_modules\" (
      echo Faltan los paquetes del front. Instalelos una vez con:  cd frontend ^&^& npm ci
      goto :front_error
    )
    pushd frontend
    if errorlevel 1 goto :front_error
    call npm run build
    if errorlevel 1 (
      popd
      goto :front_error
    )
    popd
    "%PY%" -m convertersmartgrid.web.runtime --front-integrity
    if errorlevel 1 goto :front_error
  )
)

echo Abriendo la interfaz web en el navegador...
rem Con el puerto ocupado, convertersmartgrid.web reutiliza el Conversor abierto, reemplaza el de
rem otra version o cambia de puerto (spec 001, RF-28 a RF-31): ya no hace falta pausa.
rem 3 = otra version con trabajos en curso, abierta en el navegador: se deja leer el
rem aviso y la ventana se cierra sola.
"%PY%" -m convertersmartgrid.web
set "WEB_EXITCODE=%ERRORLEVEL%"
if "%WEB_EXITCODE%"=="3" (
  call timeout /t 20
  goto :fin
)
if "%WEB_EXITCODE%"=="2" (
  echo.
  echo El puerto 8765 y los siguientes estan en uso: arriba se indica que proceso lo tiene y como cerrarlo.
  pause
  goto :fin
)
if not "%WEB_EXITCODE%"=="0" (
  echo.
  echo Si faltan librerias:  "%PY%" -m pip install -r requirements.txt
  pause
)
:fin
endlocal & exit /b %WEB_EXITCODE%

:dependency_error
echo.
echo El entorno no esta completo: arriba se indica que falta. Este lanzador no instala nada.
echo Instale las dependencias con:  "%PY%" -m pip install -r requirements.txt
pause
endlocal
exit /b 1

:front_error
echo.
echo No se pudo preparar o compilar la interfaz web. No se abre una compilacion anterior.
echo Revise el error de npm anterior y vuelva a ejecutar el acceso directo.
pause
endlocal
exit /b 1
