"""Instala, actualiza y vuelve atrás ConverterSmartGrid desde un candidato armado (spec 086, RF-36, RF-38, RF-39).

Uso:
  python instalar_candidato.py instalar --candidato CANDIDATO --destino CARPETA [--puerto 8765]
  python instalar_candidato.py volver --destino CARPETA [--sin-restaurar] [--puerto 8765]
  python instalar_candidato.py estado --destino CARPETA
  python instalar_candidato.py verificar --candidato CANDIDATO

Con ``--registro FICHERO``, en cualquier orden, si no se puede el motivo queda también en ese fichero (UTF-8 con BOM):
el instalador lo corre sin consola y lo lee de ahí para su registro y su aviso (RF-57).

Al instalar sobre otra versión, la que estaba queda en ``anterior.txt`` para volver, aunque no lo registrara (086:RF-94).
Los documentos del candidato pasan a ``documentos/`` solo cuando la instalación termina bien (086:RF-97); los de la
versión anterior quedan en ``documentos.anterior`` y vuelven con ella al volver atrás (086:RF-98, RF-99).

Lo corre el instalador con el Python que viene en el candidato: solo usa la biblioteca estándar y no sale a la
red. Cada versión queda en ``versiones/<versión>``, con su Python y sus librerías, y ``actual.txt`` dice cuál se
usa: actualizar es preparar la nueva al lado y cambiar ese puntero solo si responde, y volver atrás es cambiarlo
de vuelta. Los datos del operador nunca están aquí; antes de cambiar de versión se copian (RF-38).

Códigos de salida: 0 bien, 1 no se pudo, y lo instalado sigue como estaba.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ACTUAL = 'actual.txt'
ANTERIOR = 'anterior.txt'
ULTIMA_COPIA = 'ultima_copia.json'
#: 086:RF-97 a RF-99: los manuales y las notas del programa, los de la versión anterior y dos carpetas de paso; el .iss
#: las quita al desinstalar.
DOCUMENTOS = 'documentos'
DOCUMENTOS_PREPARANDO = 'documentos.preparando'
DOCUMENTOS_ANTERIORES = 'documentos.anterior'
DOCUMENTOS_RETIRAR = 'documentos.retirar'
LANZADOR = 'ConverterSmartGrid.cmd'
ORDEN = 'csg.cmd'
HERRAMIENTA_COPIA = Path('Lib', 'site-packages', 'convertersmartgrid', '_programa', 'tools', 'copia_datos.py')

_CABECERA_CMD = """@echo off
rem Generado por el instalador. No instala nada al arrancar: eso solo se hace al instalar (086:RF-39).
setlocal
set /p VERSION=<"%~dp0actual.txt"
set "PYDIR=%~dp0versiones\\%VERSION%\\python"
set "PY=%PYDIR%\\python.exe"
set "APP=%~dp0."
rem Sin PYTHONHOME, este Python mezcla en su ruta las carpetas de cualquier Python del registro de Windows.
set "PYTHONHOME=%PYDIR%"
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "CSG_EDICION=producto"
if not defined CSG_DATOS_HOME set "CSG_DATOS_HOME=%LOCALAPPDATA%\\ConverterSmartGrid\\datos"
if not exist "%CSG_DATOS_HOME%" mkdir "%CSG_DATOS_HOME%"
rem La carpeta del programa se sustituye al actualizar: se trabaja en la de datos.
cd /d "%CSG_DATOS_HOME%"
"""
# -P: con «-m», Python añade a su ruta la carpeta de trabajo, y aquí es la de datos: un json.py suelto se importaría.
_PIE_WEB = """"%PY%" -P -m convertersmartgrid.web %*
set "CODIGO=%ERRORLEVEL%"
if "%CODIGO%"=="3" (
  call timeout /t 20
) else if not "%CODIGO%"=="0" (
  echo.
  echo No se pudo abrir el programa. Para saber que falta, ejecute: csg.cmd doctor
  pause
)
endlocal & exit /b %CODIGO%
"""
_PIE_ORDEN = """"%PY%" -P -m convertersmartgrid.cli %*
endlocal & exit /b %ERRORLEVEL%
"""
_TOOLS = '%PYDIR%\\Lib\\site-packages\\convertersmartgrid\\_programa\\tools'
_PIE_VOLVER = f""""%PY%" "{_TOOLS}\\instalar_candidato.py" volver --destino "%APP%" %*
endlocal & exit /b %ERRORLEVEL%
"""
_PIE_COPIA = f""""%PY%" "{_TOOLS}\\copia_datos.py" %*
endlocal & exit /b %ERRORLEVEL%
"""
#: La ruta más larga que Windows carga como DLL sin configurar nada en el equipo.
LONGITUD_MAXIMA_RUTA = 259


class ErrorInstalacion(RuntimeError):
    """Lo instalado sigue como estaba; el mensaje dice por qué no se siguió."""


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open('rb') as f:
        for trozo in iter(lambda: f.read(1 << 20), b''):
            h.update(trozo)
    return h.hexdigest()


def leer_manifiesto(candidato: Path) -> dict:
    try:
        return json.loads((candidato / 'manifiesto_candidato.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ErrorInstalacion(f'El candidato {candidato} no tiene un manifiesto legible: {exc}') from exc


def verificar_candidato(candidato: Path) -> dict:
    """RF-39: antes de tocar nada, cada fichero contra su huella. Devuelve el manifiesto."""
    manifiesto = leer_manifiesto(candidato)
    malos = []
    if manifiesto.get('tipo') == 'complemento-ia':
        declaradas = {f['ruta'] for f in manifiesto['ficheros'] if f['ruta'].endswith('.whl')}
        presentes = {p.relative_to(candidato).as_posix() for p in candidato.rglob('*.whl')}
        if presentes != declaradas:
            raise ErrorInstalacion('El complemento contiene ruedas extra o no declaradas, o faltan ruedas.')
    for fichero in manifiesto['ficheros']:
        ruta = candidato / fichero['ruta']
        if not ruta.is_file():
            malos.append(f'{fichero["ruta"]} (falta)')
        elif _sha256(ruta) != fichero['sha256']:
            malos.append(f'{fichero["ruta"]} (otra huella)')
    if malos:
        raise ErrorInstalacion('El candidato está alterado o incompleto, no se instala: ' + ', '.join(malos[:10])
                               + (f' y {len(malos) - 10} más' if len(malos) > 10 else ''))
    return manifiesto


def _entorno_limpio(python: Path) -> dict[str, str]:
    """Otro Python de la máquina no puede decidir qué se instala; pip no sale a internet ni con una caché ajena.

    PYTHONHOME es lo que impide que este Python añada a su ruta las carpetas que el registro de Windows dice de otro:
    en un equipo con otro 3.12 cargaba de allí sus DLL. Un ``._pth`` lo impediría sin variable, pero también le quitaría
    PYTHONPATH, que es como un guion encuentra la API de DIgSILENT.
    """
    # El ejecutable base que nos ejecuta puede proceder de PCbuild/amd64: su Lib
    # está en la raíz de fuentes, no junto al exe. Esa base ya está identificada
    # por este intérprete; los demás destinos mantienen su aislamiento local.
    base_actual = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
    casa_python = Path(sys.base_prefix) if python.resolve() == base_actual else python.parent
    entorno = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'VIRTUAL_ENV', 'PIP_INDEX_URL', 'PIP_EXTRA_INDEX_URL')}
    entorno.update(PYTHONHOME=str(casa_python), PYTHONNOUSERSITE='1', PYTHONSAFEPATH='1', PIP_NO_INDEX='1', PIP_CONFIG_FILE=os.devnull,
                   PIP_DISABLE_PIP_VERSION_CHECK='1', PYTHONUTF8='1', PIP_NO_INPUT='1')
    return entorno


def _web_escuchando(puerto: int) -> bool:
    with socket.socket() as conexion:
        conexion.settimeout(0.5)
        return conexion.connect_ex(('127.0.0.1', puerto)) == 0


def _publicar(ruta: Path, texto: str) -> None:
    temporal = ruta.with_name(ruta.name + '.nuevo')
    with temporal.open('w', encoding='utf-8', newline='\n') as f:
        f.write(texto)
        f.flush()
        os.fsync(f.fileno())
    # 086:RF-104: el mismo reintento que las carpetas; Defender o un visor también tienen abierto un momento actual.txt.
    # Si no se puede, el temporal se quita: un «.nuevo» suelto era lo único que quedaba distinto tras deshacer.
    try:
        _reemplazar(temporal, ruta)
    except BaseException:
        temporal.unlink(missing_ok=True)
        raise


#: 086:RF-105: lo que hay que saber aunque se instale bien; ``main`` lo deja en ``--registro``, que el .iss vuelca en su log.
AVISOS: list[str] = []


def _avisar(texto: str) -> None:
    AVISOS.append(texto)
    print(texto, file=sys.stderr, flush=True)


#: 086:RF-104: intentos de renombrar una carpeta en uso y la primera espera, que se dobla en cada uno: 0,2 + 0,4 + 0,8 +
#: 1,6 = 3 s en total. pip hace lo mismo con os.replace (``retry(stop_after_delay=1, wait=0.25)``, en
#: https://github.com/pypa/pip/blob/26.2.1/src/pip/_internal/utils/filesystem.py) y con rmtree (3 s, en misc.py); CPython
#: en sus pruebas de Windows espera con retroceso exponencial hasta ~1 s (``_waitfor``, Lib/test/support/os_helper.py).
INTENTOS_RENOMBRAR = 5
ESPERA_INICIAL_S = 0.2
#: Inyectable: las pruebas la sustituyen para no dormir.
_esperar = time.sleep


def _reemplazar(origen: Path, hacia: Path) -> None:
    """086:RF-104: ``os.replace`` de una carpeta o de un puntero, con unos pocos reintentos si Windows lo tiene en uso.

    Windows no deja renombrar una carpeta con un fichero abierto dentro: ERROR_SHARING_VIOLATION (WinError 32, «el proceso
    no tiene acceso al archivo porque está siendo utilizado por otro proceso») o ERROR_ACCESS_DENIED (5), que CPython
    traduce a EACCES (PC/errmap.h) y por tanto a ``PermissionError``. Lo provocan el manual o las notas abiertos en un
    visor, Defender al revisar los ficheros nuevos u OneDrive y Drive al sincronizarlos; casi siempre es un momento. La
    documentación de ``os.replace`` solo promete el renombrado atómico como requisito POSIX
    (https://docs.python.org/3.12/library/os.html#os.replace): en Windows, sobre carpetas, puede fallar a medias.
    """
    espera = ESPERA_INICIAL_S
    for intento in range(1, INTENTOS_RENOMBRAR + 1):
        try:
            os.replace(origen, hacia)
            return
        except PermissionError as exc:
            if intento == INTENTOS_RENOMBRAR:
                raise ErrorInstalacion(
                    f'Windows no deja mover {origen} a {hacia.name}: está en uso ({exc}). Cierre los '
                    'documentos de ConverterSmartGrid abiertos (manual, notas) y vuelva a intentarlo; si ya están cerrados, '
                    'espere a que el antivirus o la sincronización de OneDrive o Drive terminen con esa carpeta.'
                ) from exc
            _esperar(espera)
            espera *= 2


def _borrar_o_avisar(carpeta: Path) -> None:
    """086:RF-105: borra una carpeta de paso; si no puede, no falla, pero lo dice con su ruta.

    Antes, ``shutil.rmtree(..., ignore_errors=True)`` callaba el fallo y ``documentos.retirar``, ``documentos.preparando`` o
    ``documentos.anterior`` se quedaban sin que nadie lo supiera. ``onexc`` es de Python 3.12, el del candidato.
    """
    if not carpeta.exists():
        return
    fallos: list[str] = []
    shutil.rmtree(carpeta, onexc=lambda _funcion, ruta, exc: fallos.append(f'{ruta}: {exc}'))
    if fallos:
        _avisar(f'No se pudo borrar {carpeta} (la instalación sigue bien): {fallos[0]}. Bórrela a mano cuando no haya '
                'ningún documento de ConverterSmartGrid abierto.')


def _leer(ruta: Path) -> str:
    return ruta.read_text(encoding='utf-8').strip() if ruta.is_file() else ''


def _python_de(destino: Path, version: str) -> Path:
    return destino / 'versiones' / version / 'python' / 'python.exe'


def _instalar_python_pf(candidato: Path, carpeta: Path) -> None:
    """103:RF-6: los Python de PowerFactory 2021 a 2023 junto al del programa, cada uno con su ``numpy`` por su huella.

    Van en ``versiones/<versión>/python_pf/<3.x>``, donde los busca el programa al lado de su propio Python.
    """
    origen = candidato / 'terceros' / 'python_pf'
    if not origen.is_dir():
        return
    huellas = json.loads((origen / 'huellas.json').read_text(encoding='utf-8'))
    destino = carpeta / 'python_pf'
    for version, h in sorted(huellas.items()):
        rueda = origen / 'ruedas' / h['numpy']
        if hashlib.sha256(rueda.read_bytes()).hexdigest() != h['sha256']:
            raise ErrorInstalacion(f'{rueda.name} no coincide con su huella: el candidato está alterado.')
        shutil.copytree(origen / version, destino / version)
        with zipfile.ZipFile(rueda) as z:
            z.extractall(destino / version / 'Lib' / 'site-packages')


def _preparar_version(candidato: Path, destino: Path, manifiesto: dict) -> Path:
    """Copia el Python del candidato e instala con huella y sin red: el lock exige que coincida cada rueda."""
    version = manifiesto['version']
    carpeta = destino / 'versiones' / version
    # La reserva exclusiva fija la propiedad: un rechazo por carpeta preexistente
    # nunca autoriza a retirarla (rc6 retenida tras volver a rc5).
    try:
        carpeta.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ErrorInstalacion(f'La versión {version} ya está en {carpeta}: no se pisa. Use «volver» o desinstale antes.') from exc
    try:
        shutil.copytree(candidato / 'terceros' / 'python', carpeta / 'python')
        python = carpeta / 'python' / 'python.exe'
        pips = sorted((candidato / 'terceros' / 'wheels').glob('pip-*.whl'))
        if not pips:
            raise ErrorInstalacion('El candidato no trae pip para instalar sus ruedas.')
        orden = [str(python), '-m', 'pip', 'install', '--no-index', '--require-hashes', '--no-cache-dir',
                 '--no-warn-script-location', '--find-links', str(candidato / 'terceros' / 'wheels'),
                 '--find-links', str(candidato / 'programa'), '-r', str(candidato / 'terceros' / 'instalacion.lock')]
        # pip corre desde su rueda, por PYTHONPATH: con «rueda/pip» como guion, en Windows se niega a instalarse a sí mismo.
        r = subprocess.run(orden, env={**_entorno_limpio(python), 'PYTHONPATH': str(pips[0])}, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', check=False)
        if r.returncode:
            raise ErrorInstalacion(f'pip no pudo instalar con las huellas del candidato:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}')
        _instalar_python_pf(candidato, carpeta)                                        # 103:RF-6
        larga = max((str(f) for f in carpeta.rglob('*.pyd')), key=len, default='')
        if len(larga) > LONGITUD_MAXIMA_RUTA:
            # Sale en la última línea de un error que solo dice «nombre demasiado largo» al importar geopandas.
            raise ErrorInstalacion(f'La carpeta de instalación es demasiado larga: alguna ruta llega a {len(larga)} caracteres, y Windows no carga '
                                   f'una librería de más de {LONGITUD_MAXIMA_RUTA}. Elija una carpeta más corta.')
        return python
    except BaseException:
        # Solo se limpia la carpeta cuya reserva exclusiva obtuvo esta llamada.
        shutil.rmtree(carpeta, ignore_errors=True)
        raise


def _doctor(python: Path) -> dict:
    """La versión nueva tiene que responder antes de dejarla como la que se usa."""
    entorno = {**_entorno_limpio(python), 'CSG_EDICION': 'producto'}
    r = subprocess.run([str(python), '-m', 'convertersmartgrid.cli', 'doctor', '--json'], env=entorno, capture_output=True,
                       text=True, encoding='utf-8', errors='replace', check=False)
    try:
        informe = json.loads(r.stdout)
    except ValueError as exc:
        raise ErrorInstalacion(f'La versión instalada no responde:\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}') from exc
    if r.returncode or not informe.get('listo'):
        faltan = [c['nombre'] for c in informe.get('comprobaciones', ()) if c['obligatoria'] and not c['ok']]
        raise ErrorInstalacion(f'A la versión instalada le falta algo imprescindible: {", ".join(faltan)}.')
    return informe


def _copiar_datos(python: Path, carpeta_version: Path) -> dict | None:
    """RF-38: antes de cambiar de versión. Sin datos todavía no hay nada que copiar."""
    programa = carpeta_version / 'python' / HERRAMIENTA_COPIA
    entorno = {**_entorno_limpio(python), 'CSG_EDICION': 'producto'}
    datos = _raiz_de_datos(entorno)
    destino = datos / 'copias_actualizacion'
    r = subprocess.run([str(python), str(programa), 'crear', '--destino', str(destino)], env=entorno, capture_output=True,
                       text=True, encoding='utf-8', errors='replace', check=False)
    if r.returncode:
        raise ErrorInstalacion(f'No se pudo copiar los datos antes de actualizar: no se sigue.\n{r.stdout[-1000:]}\n{r.stderr[-1000:]}')
    return json.loads(r.stdout)


def _raiz_de_datos(entorno: dict[str, str]) -> Path:
    otra = entorno.get('CSG_DATOS_HOME', '').strip()
    if otra:
        return Path(otra)
    return Path(entorno.get('LOCALAPPDATA') or Path.home()) / 'ConverterSmartGrid' / 'datos'


def _escribir_lanzadores(destino: Path) -> None:
    for nombre, pie in ((LANZADOR, _PIE_WEB), (ORDEN, _PIE_ORDEN), ('volver_atras.cmd', _PIE_VOLVER), ('copia_datos.cmd', _PIE_COPIA)):
        temporal = destino / f'{nombre}.nuevo'
        # cmd.exe lee estos ficheros en la página de la consola y exige CRLF: solo ASCII en lo que se ejecuta.
        temporal.write_bytes((_CABECERA_CMD + pie).replace('\n', '\r\n').encode('cp1252', 'replace'))
        os.replace(temporal, destino / nombre)


def _retirar_viejas(destino: Path, conservar: set[str]) -> None:
    """Una versión pesa cientos de MB: quedan la actual y a la que se puede volver.

    086:RF-105: una que no se deja borrar (un ``.pyd`` de su Python embebido cargado) se avisa; callada, cada
    actualización dejaba otra y el disco del cliente crecía sin que nadie lo supiera.
    """
    for carpeta in sorted((destino / 'versiones').iterdir()):
        if carpeta.is_dir() and carpeta.name not in conservar:
            _borrar_o_avisar(carpeta)


def _clave_de_version(version: str) -> tuple:
    """Orden de versiones sin ``packaging`` (aquí solo hay biblioteca estándar): 1.0.0rc5 < 1.0.0rc10 < 1.0.0."""
    hallada = re.fullmatch(r'(\d+(?:\.\d+)*)(?:(a|b|rc)(\d+))?', version)
    if not hallada:
        return (0, (), 0, 0, version)
    numeros = tuple(int(n) for n in hallada.group(1).split('.'))
    previa = {'a': 0, 'b': 1, 'rc': 2, None: 3}[hallada.group(2)]
    return (1, numeros, previa, int(hallada.group(3) or 0), version)


def version_instalada(destino: Path) -> str:
    """086:RF-94, RF-95: la versión que hay ahora, a la que se podrá volver; ``''`` si no hay ninguna con su Python.

    Manda ``actual.txt`` si su versión tiene su Python. Sin él, o con uno que nombra una versión que ya no está, se toma la
    más reciente de ``versiones/`` que conserve su Python: antes eso pasaba por una primera instalación, no se copiaban los
    datos, no quedaba anterior y ``_retirar_viejas`` borraba justo la versión a la que había que volver.
    """
    actual = _leer(destino / ACTUAL)
    if actual and _python_de(destino, actual).is_file():
        return actual
    carpeta = destino / 'versiones'
    con_python = [c.name for c in carpeta.iterdir() if c.is_dir() and _python_de(destino, c.name).is_file()] if carpeta.is_dir() else []
    return max(con_python, key=_clave_de_version, default='')


def _preparar_documentos(candidato: Path, destino: Path) -> Path | None:
    """086:RF-97: los documentos del candidato, copiados al lado de los publicados; aún no son los del programa."""
    origen = candidato / DOCUMENTOS
    if not origen.is_dir():
        return None
    preparacion = destino / DOCUMENTOS_PREPARANDO
    _borrar_o_avisar(preparacion)                                   # restos de una vez que se cortó (086:RF-105)
    shutil.copytree(origen, preparacion)
    return preparacion


_SIN_CAMBIO = object()


def _cambiar_de_version(destino: Path, renombrados: list[tuple[str, str]], punteros: dict[str, object]) -> None:
    """086:RF-97, RF-98, RF-101: documentos y punteros cambian juntos; si algo falla, queda exactamente lo que había.

    ``renombrados`` son pares (origen, destino) de carpetas de ``destino``; los que no existen se saltan. ``punteros``
    da a cada fichero (``actual.txt``, ``anterior.txt``, ``ultima_copia.json``) su texto nuevo, ``None`` para quitarlo
    o ``_SIN_CAMBIO``. Son renombrados en la misma carpeta, y por tanto en el mismo volumen: ``os.replace`` no pisa una
    carpeta con contenido y en Windows no promete un cambio atómico de varias, así que cada paso hecho se deshace al
    revés. Lo retirado espera en ``documentos.retirar`` y solo se borra cuando todo quedó escrito.
    """
    _borrar_o_avisar(destino / DOCUMENTOS_RETIRAR)                         # restos de una vez que se cortó
    previos = {n: _leer_crudo(destino / n) for n, v in punteros.items() if v is not _SIN_CAMBIO}
    hechos: list[tuple[str, str]] = []
    escritos: list[str] = []
    try:
        for origen, hacia in renombrados:
            if (destino / origen).exists():
                _reemplazar(destino / origen, destino / hacia)
                hechos.append((origen, hacia))
        for nombre, texto in punteros.items():
            if texto is None:
                (destino / nombre).unlink(missing_ok=True)
            elif texto is not _SIN_CAMBIO:
                _publicar(destino / nombre, str(texto))
            else:
                continue
            escritos.append(nombre)
    except BaseException as original:
        # Solo se repone lo que llegó a cambiar: _publicar escribe aparte y sustituye al final, y si falla no tocó nada.
        # 086:RF-103: cada paso del deshacer va por su cuenta. Antes, si uno fallaba (un fichero que el antivirus tenía
        # abierto), su excepción tapaba la original y los pasos que faltaban no se hacían: documentos de una versión con
        # punteros de la otra, el estado mezclado que RF-97 y RF-98 impiden. Se sigue con los demás, se relanza la
        # original y cada paso que no se pudo va en sus notas (BaseException.add_note) y en el aviso, con sus rutas.
        pendientes: list[tuple[str, str]] = []

        def reponer(que: str, a_mano: str, paso) -> None:
            try:
                paso()
            except Exception as exc:                                   # noqa: BLE001 — se anota y se sigue deshaciendo
                pendientes.append((f'{que}: {exc}', a_mano))

        for nombre in reversed(escritos):
            ruta, texto = destino / nombre, previos[nombre]
            if texto is None:
                reponer(f'quitar {ruta}', f'borre {ruta}', lambda r=ruta: r.unlink(missing_ok=True))
            else:
                reponer(f'reponer {ruta}', f'deje en {ruta} este texto: {texto.strip()!r}',
                        lambda r=ruta, t=texto: _publicar(r, t))
        for origen, hacia in reversed(hechos):
            de, a = destino / hacia, destino / origen
            reponer(f'devolver {de} a {a}', f'renombre la carpeta {de} a {a.name}', lambda d=de, h=a: _reemplazar(d, h))
        if pendientes:
            for que, _ in pendientes:
                original.add_note(f'No se pudo deshacer: {que}')
            _avisar('El cambio de versión (instalar o volver atrás) no terminó y no se pudo deshacer del todo; queda a medias:\n'
                    + '\n'.join(f'- {que}. Arréglelo a mano: {a_mano}.' for que, a_mano in pendientes)
                    + f'\nDespués, «instalar_candidato.py estado --destino {destino}» debe nombrar la versión que tenía.')
        raise
    _borrar_o_avisar(destino / DOCUMENTOS_RETIRAR)                         # 086:RF-105


def _leer_crudo(ruta: Path) -> str | None:
    """El texto tal cual, saltos de línea incluidos, para reponerlo byte a byte con ``_publicar``."""
    if not ruta.is_file():
        return None
    with ruta.open(encoding='utf-8', newline='') as f:
        return f.read()


def instalar(candidato: Path, destino: Path, *, puerto: int = 8765, forzar: bool = False) -> dict:
    """Primera instalación o actualización: el puntero solo cambia al final, con la versión nueva respondiendo.

    Sobre otra versión, esa queda en ``anterior.txt`` para volver atrás, aunque la que estaba no registrara ninguna (el rc5
    de este equipo, 2026-11-13, no tenía ``anterior.txt``): lo escribe la versión que se instala, no la que estaba.
    """
    manifiesto = verificar_candidato(candidato)
    version = manifiesto['version']
    actual = version_instalada(destino)                                                    # 086:RF-94, RF-95
    if actual == version:
        raise ErrorInstalacion(f'La versión {version} ya es la instalada.')
    if actual and _web_escuchando(puerto) and not forzar:
        raise ErrorInstalacion(f'El programa está abierto en el puerto {puerto}: ciérrelo antes de actualizar, porque '
                               'guarda sus espacios en memoria y al salir pisaría lo que se haga aquí.')
    destino.mkdir(parents=True, exist_ok=True)
    carpeta = destino / 'versiones' / version
    # 086:RF-102: la que volver atrás dejó apartada, con su Python, vuelve a ponerse en uso como en una actualización.
    # Antes se respondía «ya está» y para volver a ella había que desinstalar. No se prepara de nuevo ni se pisa: la
    # carpeta no es de esta llamada y nada de ella se borra si algo falla. Una carpeta sin Python sigue sin pisarse.
    reactivada = _python_de(destino, version).is_file()
    copia = None
    preparada = False
    documentos = None
    try:
        if reactivada:
            python = _python_de(destino, version)
        else:
            python = _preparar_version(candidato, destino, manifiesto)
            preparada = True
        informe = _doctor(python)
        if actual:
            copia = _copiar_datos(python, carpeta)
        documentos = _preparar_documentos(candidato, destino)                              # 086:RF-97
    except (ErrorInstalacion, OSError, ValueError):
        # El preparador limpia sus fallos. Solo una preparación devuelta con éxito
        # nos pertenece para retirar tras un fallo del doctor o de la copia.
        if preparada:
            shutil.rmtree(carpeta, ignore_errors=True)
        _borrar_o_avisar(destino / DOCUMENTOS_PREPARANDO)                                 # 086:RF-105
        raise
    _escribir_lanzadores(destino)
    # 086:RF-97, RF-99: los documentos cambian con los punteros y no antes. El .iss los vaciaba y copiaba en [InstallDelete]
    # y [Files], antes de saber si esto terminaba; tras un fallo, el programa que seguía tenía los de la versión nueva. Los
    # de la versión que estaba quedan en documentos.anterior, para volver atrás con ellos; los de antes de esa se retiran.
    # anterior.txt y ultima_copia.json entran en el mismo cambio: escritos antes del puntero, un fallo dejaba anterior.txt
    # igual a actual.txt y la nota de la copia de otra actualización, y volver atrás ya no restauraba los datos.
    renombrados = [(DOCUMENTOS_ANTERIORES, DOCUMENTOS_RETIRAR), (DOCUMENTOS, DOCUMENTOS_ANTERIORES)]
    if documentos is not None:
        renombrados.append((DOCUMENTOS_PREPARANDO, DOCUMENTOS))
    punteros: dict[str, object] = {
        ULTIMA_COPIA: _SIN_CAMBIO if copia is None else json.dumps(
            {'desde': actual, 'hacia': version, 'copia': copia['ruta'], 'cuando': time.time()}, ensure_ascii=False, indent=2),
        ANTERIOR: actual + '\n' if actual else _SIN_CAMBIO,
        ACTUAL: version + '\n',
    }
    try:
        _cambiar_de_version(destino, renombrados, punteros)
    except BaseException:
        # La versión preparada es de esta llamada y se retira (086:RF-100); la reactivada no, sigue apartada (086:RF-102).
        if preparada:
            shutil.rmtree(carpeta, ignore_errors=True)
        raise
    finally:
        _borrar_o_avisar(destino / DOCUMENTOS_PREPARANDO)                                 # 086:RF-105
    if not actual:
        # Primera instalación: no hay versión a la que volver, ni documentos que guardar para ella.
        _borrar_o_avisar(destino / DOCUMENTOS_ANTERIORES)                                 # 086:RF-105
    _retirar_viejas(destino, {version, actual} - {''})
    return {'version': version, 'anterior': actual or None, 'copia': copia and copia['ruta'], 'pendientes': informe['pendientes'],
            'reactivada': reactivada}


def volver(destino: Path, *, restaurar: bool = True, puerto: int = 8765, forzar: bool = False) -> dict:
    """Vuelve a la versión anterior y, por defecto, a sus datos de antes: lo actual se aparta, no se borra.

    Una versión vieja no abre un espacio migrado por una nueva (086:RF-5): de poco sirve volver al programa y no a
    sus datos. Con ``restaurar=False`` se conservan los de ahora, si la actualización no los llegó a tocar.
    """
    actual, anterior = _leer(destino / ACTUAL), _leer(destino / ANTERIOR)
    if not anterior or not _python_de(destino, anterior).is_file():
        raise ErrorInstalacion('No hay una versión anterior a la que volver.')
    if _web_escuchando(puerto) and not forzar:
        raise ErrorInstalacion(f'El programa está abierto en el puerto {puerto}: ciérrelo antes de volver atrás.')
    apuntes = json.loads(_leer(destino / ULTIMA_COPIA) or '{}')
    restaurado = None
    if restaurar and apuntes.get('copia') and apuntes.get('desde') == anterior:
        # La copia la creó la versión actual: la anterior puede no entender su formato.
        python = _python_de(destino, actual)
        programa = python.parent / HERRAMIENTA_COPIA
        r = subprocess.run([str(python), str(programa), 'restaurar', '--copia', apuntes['copia'], '--puerto', str(puerto),
                            *(['--forzar'] if forzar else [])],
                           env={**_entorno_limpio(python), 'CSG_EDICION': 'producto'}, capture_output=True, text=True, encoding='utf-8',
                           errors='replace', check=False)
        if r.returncode:
            raise ErrorInstalacion(f'No se pudo restaurar la copia {apuntes["copia"]}; sigue la versión {actual}.\n{r.stdout[-1000:]}\n{r.stderr[-1000:]}')
        restaurado = apuntes['copia']
    # 086:RF-98, RF-100, RF-101: vuelven a la vez la versión anterior y sus documentos; los de la que se deja se retiran
    # (su programa se aparta, no se borra). Sin anterior.txt después, una segunda vuelta atrás dice que no hay a cuál
    # volver en vez de alternar entre las dos. Si algo falla a mitad, queda exactamente lo que había.
    _cambiar_de_version(destino, [(DOCUMENTOS, DOCUMENTOS_RETIRAR), (DOCUMENTOS_ANTERIORES, DOCUMENTOS)],
                        {ANTERIOR: None, ACTUAL: anterior + '\n'})
    return {'version': anterior, 'dejada': actual, 'datos_restaurados_de': restaurado}


def estado(destino: Path) -> dict:
    return {'actual': _leer(destino / ACTUAL) or None, 'anterior': _leer(destino / ANTERIOR) or None,
            'versiones': sorted(c.name for c in (destino / 'versiones').iterdir()) if (destino / 'versiones').is_dir() else []}


def _dejar_motivo(registro: Path | None, motivo: str | None) -> None:
    """086:RF-57: el motivo, donde lo lee el instalador; sin motivo, se quita el de una vez anterior.

    086:RF-105: si todo fue bien pero hubo avisos (una carpeta de paso que no se pudo borrar), van aquí también: el
    instalador los copia a su registro.

    El instalador corre este guion oculto: lo que escribe en la consola se perdía, y su registro solo decía «1» (rc5,
    2026-11-12: el programa estaba abierto en el puerto 8765). El BOM es para que Inno lo lea como UTF-8 sin dudar.
    """
    if registro is None:
        return
    try:
        if motivo is None:
            registro.unlink(missing_ok=True)
        else:
            registro.write_text(motivo + '\n', encoding='utf-8-sig')
    except OSError as exc:
        print(f'No se pudo escribir el motivo en {registro}: {exc}', file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    comun = argparse.ArgumentParser(add_help=False)
    comun.add_argument('--registro', type=Path, help='Fichero donde dejar el motivo si no se puede (lo lee el instalador).')
    orden = parser.add_subparsers(dest='orden', required=True)
    p_instalar = orden.add_parser('instalar', parents=[comun], help='Instala, o actualiza si ya hay una versión.')
    p_instalar.add_argument('--candidato', type=Path, required=True)
    p_instalar.add_argument('--destino', type=Path, required=True)
    p_instalar.add_argument('--puerto', type=int, default=8765, help='Dónde se mira si el programa está abierto.')
    p_instalar.add_argument('--forzar', action='store_true', help='Aunque el programa parezca abierto.')
    p_volver = orden.add_parser('volver', parents=[comun], help='Vuelve a la versión anterior, con sus datos.')
    p_volver.add_argument('--destino', type=Path, required=True)
    p_volver.add_argument('--sin-restaurar', action='store_true', help='Conserva los datos de ahora.')
    p_volver.add_argument('--puerto', type=int, default=8765)
    p_volver.add_argument('--forzar', action='store_true', help='Aunque el programa parezca abierto.')
    p_estado = orden.add_parser('estado', parents=[comun], help='Qué versión se usa y a cuál se puede volver.')
    p_estado.add_argument('--destino', type=Path, required=True)
    p_verificar = orden.add_parser('verificar', parents=[comun], help='Comprueba cada fichero del candidato contra su huella.')
    p_verificar.add_argument('--candidato', type=Path, required=True)
    args = parser.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass
    AVISOS.clear()
    try:
        if args.orden == 'instalar':
            salida = instalar(args.candidato, args.destino, puerto=args.puerto, forzar=args.forzar)
        elif args.orden == 'volver':
            salida = volver(args.destino, restaurar=not args.sin_restaurar, puerto=args.puerto, forzar=args.forzar)
        elif args.orden == 'estado':
            salida = estado(args.destino)
        else:
            salida = {'version': verificar_candidato(args.candidato)['version'], 'huellas': 'correctas'}
    except (ErrorInstalacion, OSError, ValueError) as exc:
        # 086:RF-103: el motivo lleva también las notas de lo que no se pudo deshacer y los avisos con las rutas que
        # arreglar a mano; str(exc) no trae las notas, y el instalador solo enseña lo que hay en este fichero.
        motivo = '\n'.join([str(exc), *getattr(exc, '__notes__', ()), *AVISOS])
        print(motivo, file=sys.stderr)
        _dejar_motivo(args.registro, motivo)
        return 1
    _dejar_motivo(args.registro, '\n'.join(AVISOS) or None)                 # 086:RF-105: avisos de una vez que fue bien
    print(json.dumps(salida, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
