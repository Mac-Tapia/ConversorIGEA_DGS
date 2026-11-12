"""Instala, actualiza y vuelve atrás ConverterSmartGrid desde un candidato armado (spec 086, RF-36, RF-38, RF-39).

Uso:
  python instalar_candidato.py instalar --candidato CANDIDATO --destino CARPETA [--puerto 8765]
  python instalar_candidato.py volver --destino CARPETA [--sin-restaurar] [--puerto 8765]
  python instalar_candidato.py estado --destino CARPETA
  python instalar_candidato.py verificar --candidato CANDIDATO

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
    os.replace(temporal, ruta)


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
    """Una versión pesa cientos de MB: quedan la actual y a la que se puede volver."""
    for carpeta in sorted((destino / 'versiones').iterdir()):
        if carpeta.is_dir() and carpeta.name not in conservar:
            shutil.rmtree(carpeta, ignore_errors=True)


def instalar(candidato: Path, destino: Path, *, puerto: int = 8765, forzar: bool = False) -> dict:
    """Primera instalación o actualización: el puntero solo cambia al final, con la versión nueva respondiendo."""
    manifiesto = verificar_candidato(candidato)
    version = manifiesto['version']
    actual = _leer(destino / ACTUAL)
    if actual == version:
        raise ErrorInstalacion(f'La versión {version} ya es la instalada.')
    if actual and _web_escuchando(puerto) and not forzar:
        raise ErrorInstalacion(f'El programa está abierto en el puerto {puerto}: ciérrelo antes de actualizar, porque '
                               'guarda sus espacios en memoria y al salir pisaría lo que se haga aquí.')
    destino.mkdir(parents=True, exist_ok=True)
    carpeta = destino / 'versiones' / version
    copia = None
    preparada = False
    try:
        python = _preparar_version(candidato, destino, manifiesto)
        preparada = True
        informe = _doctor(python)
        if actual:
            copia = _copiar_datos(python, carpeta)
    except (ErrorInstalacion, OSError, ValueError):
        # El preparador limpia sus fallos. Solo una preparación devuelta con éxito
        # nos pertenece para retirar tras un fallo del doctor o de la copia.
        if preparada:
            shutil.rmtree(carpeta, ignore_errors=True)
        raise
    _escribir_lanzadores(destino)
    if copia is not None:
        _publicar(destino / ULTIMA_COPIA, json.dumps({'desde': actual, 'hacia': version, 'copia': copia['ruta'], 'cuando': time.time()},
                                                     ensure_ascii=False, indent=2))
    if actual:
        _publicar(destino / ANTERIOR, actual + '\n')
    _publicar(destino / ACTUAL, version + '\n')
    _retirar_viejas(destino, {version, actual} - {''})
    return {'version': version, 'anterior': actual or None, 'copia': copia and copia['ruta'], 'pendientes': informe['pendientes']}


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
    _publicar(destino / ANTERIOR, actual + '\n')
    _publicar(destino / ACTUAL, anterior + '\n')
    return {'version': anterior, 'dejada': actual, 'datos_restaurados_de': restaurado}


def estado(destino: Path) -> dict:
    return {'actual': _leer(destino / ACTUAL) or None, 'anterior': _leer(destino / ANTERIOR) or None,
            'versiones': sorted(c.name for c in (destino / 'versiones').iterdir()) if (destino / 'versiones').is_dir() else []}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    orden = parser.add_subparsers(dest='orden', required=True)
    p_instalar = orden.add_parser('instalar', help='Instala, o actualiza si ya hay una versión.')
    p_instalar.add_argument('--candidato', type=Path, required=True)
    p_instalar.add_argument('--destino', type=Path, required=True)
    p_instalar.add_argument('--puerto', type=int, default=8765, help='Dónde se mira si el programa está abierto.')
    p_instalar.add_argument('--forzar', action='store_true', help='Aunque el programa parezca abierto.')
    p_volver = orden.add_parser('volver', help='Vuelve a la versión anterior, con sus datos.')
    p_volver.add_argument('--destino', type=Path, required=True)
    p_volver.add_argument('--sin-restaurar', action='store_true', help='Conserva los datos de ahora.')
    p_volver.add_argument('--puerto', type=int, default=8765)
    p_volver.add_argument('--forzar', action='store_true', help='Aunque el programa parezca abierto.')
    p_estado = orden.add_parser('estado', help='Qué versión se usa y a cuál se puede volver.')
    p_estado.add_argument('--destino', type=Path, required=True)
    p_verificar = orden.add_parser('verificar', help='Comprueba cada fichero del candidato contra su huella.')
    p_verificar.add_argument('--candidato', type=Path, required=True)
    args = parser.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass
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
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(salida, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
