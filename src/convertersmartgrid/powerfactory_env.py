"""Dónde está la API de PowerFactory y qué intérprete puede cargarla.

Vivía en ``gui.py``. Se saca aquí porque ahora la usan dos interfaces —la web y la de
escritorio— y ninguna de las dos debe importar la otra: la API web no puede arrastrar
Tk, y la lógica no puede existir en dos copias que acaben divergiendo.
"""

from __future__ import annotations

import os
import re
import shutil
import string
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .runtime_paths import raiz_programa

#: 103:RF-6: donde el instalador deja los intérpretes embebidos, uno por versión (``python_pf/3.9/python.exe``).
CARPETA_PYTHON_EMBEBIDOS = 'python_pf'
_VERSION_PF = re.compile(r'PowerFactory\s+(\d{4})(?:\s*SP\s*(\d+))?', re.IGNORECASE)


@dataclass(frozen=True)
class InstalacionPF:
    """103:RF-1: una PowerFactory instalada, con las carpetas de su API que traen la extensión, de mayor a menor."""

    carpeta: Path
    version: tuple[int, int]
    apis: tuple[Path, ...]

    @property
    def nombre(self) -> str:
        return self.carpeta.name


def project_root() -> Path:
    """La carpeta de lo que se lee: el repositorio o, instalado, la del paquete (086:RF-36)."""
    return raiz_programa()


def tools_dir() -> Path:
    return project_root() / 'tools'


def version_key(path: Path) -> tuple[int, ...]:
    """Ordena carpetas de versión por número, no por texto.

    ``sorted(..., reverse=True)`` sobre los nombres elegía «3.9» antes que «3.12»,
    porque '9' > '1' carácter a carácter. En una instalación con 3.8, 3.9, 3.10, 3.11
    y 3.12 eso seleccionaba la carpeta equivocada y la API fallaba con «DLL load
    failed», que no dice nada sobre la causa real.
    """
    partes = []
    for trozo in path.name.strip().split('.'):
        partes.append(int(trozo) if trozo.isdigit() else -1)
    return tuple(partes)


def raices_habituales() -> list[Path]:
    """103:RF-1: ``DIgSILENT`` en ``Program Files`` de cada unidad: no se supone la C."""
    raices = []
    for letra in string.ascii_uppercase:
        for programas in ('Program Files', 'Program Files (x86)'):
            raiz = Path(f'{letra}:/') / programas / 'DIgSILENT'
            try:
                if raiz.is_dir():
                    raices.append(raiz)
            except OSError:
                continue
    return raices


def carpetas_del_registro() -> list[str]:
    """103:RF-1: las ``InstallDir`` de ``HKLM\\SOFTWARE\\DIgSILENT GmbH\\PowerFactory …`` (así registra la 2024)."""
    try:
        import winreg
    except ImportError:
        return []
    salida = []
    for vista in ('SOFTWARE\\DIgSILENT GmbH', 'SOFTWARE\\WOW6432Node\\DIgSILENT GmbH'):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, vista) as clave:
                for i in range(winreg.QueryInfoKey(clave)[0]):
                    nombre = winreg.EnumKey(clave, i)
                    if not nombre.lower().startswith('powerfactory'):
                        continue
                    try:
                        with winreg.OpenKey(clave, nombre) as sub:
                            salida.append(str(winreg.QueryValueEx(sub, 'InstallDir')[0]))
                    except OSError:
                        continue
        except OSError:
            continue
    return salida


def _instalacion(carpeta: Path) -> InstalacionPF | None:
    m = _VERSION_PF.search(carpeta.name)
    if not m or not carpeta.is_dir():
        return None
    apis = sorted((p for p in (carpeta / 'Python').glob('3.*') if (p / 'powerfactory.pyd').is_file()),
                  key=version_key, reverse=True)
    return InstalacionPF(carpeta, (int(m.group(1)), int(m.group(2) or 0)), tuple(apis))


def instalaciones(raices: list[Path] | None = None, registro: list[str] | tuple[str, ...] | None = None
                  ) -> list[InstalacionPF]:
    """103:RF-1: todas las PowerFactory instaladas, de la más nueva a la más antigua, sin repetir ninguna."""
    candidatas: list[Path] = []
    for raiz in (raices_habituales() if raices is None else raices):
        try:
            candidatas.extend(sorted(raiz.glob('PowerFactory *')))
        except OSError:
            continue
    candidatas.extend(Path(c.rstrip('\\/')) for c in (carpetas_del_registro() if registro is None else registro))
    vistas, salida = set(), []
    for carpeta in candidatas:
        try:
            clave = os.path.normcase(str(carpeta.resolve()))
        except OSError:
            continue
        if clave in vistas:
            continue
        vistas.add(clave)
        inst = _instalacion(carpeta)
        if inst is not None and inst.apis:
            salida.append(inst)
    return sorted(salida, key=lambda i: i.version, reverse=True)


def _python_actual() -> str:
    return f'{sys.version_info.major}.{sys.version_info.minor}'


def _sondear_py(version: str) -> Path | None:
    """El intérprete que da el lanzador ``py -X.Y``, si lo hay."""
    launcher = shutil.which('py')
    if not launcher:
        return None
    try:
        probe = subprocess.run([launcher, f'-{version}', '-c', 'import sys; print(sys.executable)'],
                               capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    candidato = Path((probe.stdout or '').strip())
    return candidato if probe.returncode == 0 and candidato.is_file() else None


def interprete_para(version: str) -> tuple[Path | None, str]:
    """103:RF-2: un intérprete de esta versión: el del programa, el embebido del instalador o el de la máquina."""
    if version == _python_actual():
        return Path(sys.executable), f'interprete actual ({version})'
    # Instalado, van junto al Python del programa (``versiones/<v>/python_pf``); en desarrollo, en la raíz.
    for base in (Path(sys.executable).resolve().parent.parent, raiz_programa()):
        embebido = base / CARPETA_PYTHON_EMBEBIDOS / version / 'python.exe'
        if embebido.is_file():
            return embebido, f'Python {version} embebido del programa'
    override = os.environ.get('CSG_PF_INTERPRETER', '').strip()
    if override and Path(override).is_file():
        return Path(override), f'CSG_PF_INTERPRETER ({override})'
    lanzado = _sondear_py(version)
    if lanzado is not None:
        return lanzado, f'py -{version}'
    major, minor = version.split('.')
    local = os.environ.get('LOCALAPPDATA', '')
    candidatos = [Path(rf'C:\Python{major}{minor}\python.exe'), Path(rf'C:\Program Files\Python{major}{minor}\python.exe')]
    if local:
        candidatos.insert(0, Path(local) / 'Programs' / 'Python' / f'Python{major}{minor}' / 'python.exe')
    for candidato in candidatos:
        if candidato.is_file():
            return candidato, f'instalacion local {version}'
    return None, f'no se encontro Python {version}'


def interpretes_embebidos() -> list[str]:
    """103:RF-6: las versiones de Python para PowerFactory que trae el programa (``python_pf/3.x``)."""
    vistas: set[str] = set()
    for base in (Path(sys.executable).resolve().parent.parent, raiz_programa()):
        for exe in (base / CARPETA_PYTHON_EMBEBIDOS).glob('3.*/python.exe'):
            vistas.add(exe.parent.name)
    return sorted(vistas, key=lambda v: tuple(int(x) for x in v.split('.')))


def elegir_api(inst: InstalacionPF, interprete: Callable[[str], tuple[Path | None, str]] = interprete_para
               ) -> tuple[Path, Path, str] | None:
    """103:RF-2: la carpeta de la API con intérprete; primero la del Python del programa, luego de mayor a menor.

    Elegir la más alta y exigir después su intérprete dejaba fuera a una PowerFactory con API para 3.13 aunque trajera
    la de 3.12, que es la del programa.
    """
    actual = _python_actual()
    orden = sorted(inst.apis, key=lambda a: (a.name != actual, tuple(-x for x in version_key(a))))
    for api in orden:
        ruta, motivo = interprete(api.name)
        if ruta is not None:
            return api, ruta, motivo
    return None


def ruta_eleccion() -> Path:
    """103:RF-3: la PowerFactory elegida en esta máquina, en la carpeta local, que una actualización no borra (086:RF-38)."""
    from .runtime_paths import raiz_local
    return raiz_local() / 'config' / 'powerfactory.json'


def eleccion_guardada() -> Path | None:
    """La carpeta de la API que eligió el operador, si sigue instalada con su extensión; si no, ninguna."""
    import json
    try:
        datos = json.loads(ruta_eleccion().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    carpeta = Path(str(datos.get('carpeta_api') or ''))
    return carpeta if str(carpeta) not in ('', '.') and (carpeta / 'powerfactory.pyd').is_file() else None


def guardar_eleccion(carpeta_api: Path | None) -> None:
    """103:RF-3: recuerda la elección del operador; ``None`` vuelve a la más nueva que funcione."""
    import json
    ruta = ruta_eleccion()
    if carpeta_api is None:
        ruta.unlink(missing_ok=True)
        return
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({'carpeta_api': str(carpeta_api)}, ensure_ascii=False) + '\n', encoding='utf-8')


def pf_python_dir() -> Path | None:
    """La carpeta de la API que se usa: ``PF_PYTHON``; la elegida por el operador; la de la más nueva que funciona.

    103:RF-3: sin ninguna que funcione, la carpeta más alta de la más nueva, para que el diagnóstico diga qué falta.
    """
    env = os.environ.get('PF_PYTHON', '').strip()
    if env:
        path = Path(env)
        return path if path.is_dir() else None
    elegida = eleccion_guardada()
    if elegida is not None:
        return elegida
    encontradas = instalaciones()
    for inst in encontradas:
        elegida = elegir_api(inst)
        if elegida is not None:
            return elegida[0]
    return encontradas[0].apis[0] if encontradas else None


def resumen_instalaciones(encontradas: list[InstalacionPF] | None = None,
                          interprete: Callable[[str], tuple[Path | None, str]] = interprete_para) -> list[str]:
    """103:RF-4: una línea por PowerFactory encontrada: con qué Python carga o qué Python le falta."""
    lineas = []
    for inst in instalaciones() if encontradas is None else encontradas:
        elegida = elegir_api(inst, interprete)
        if elegida is not None:
            lineas.append(f'{inst.nombre}: API {elegida[0].name} con {elegida[2]}.')
        else:
            faltan = ', '.join(a.name for a in inst.apis)
            lineas.append(f'{inst.nombre}: falta un intérprete de Python {faltan} para cargar su API.')
    return lineas


def pf_api_version(pf_dir: Path | None) -> str | None:
    """Versión de Python de la carpeta de la API («3.12» de ``Python\\3.12``)."""
    if pf_dir is None:
        return None
    parts = pf_dir.name.strip().split('.')
    if len(parts) == 2 and all(p.isdigit() for p in parts):
        return pf_dir.name.strip()
    return None


def python_for_pf(pf_dir: Path | None) -> tuple[Path | None, str]:
    """Intérprete capaz de cargar ``powerfactory.pyd`` de esa carpeta, y por qué se eligió.

    ``powerfactory.pyd`` es una extensión compilada contra una versión concreta de CPython y solo carga en esa versión.
    """
    wanted = pf_api_version(pf_dir)
    if wanted is None:
        return Path(sys.executable), f'interprete actual ({_python_actual()})'
    return interprete_para(wanted)


def carpeta_del_paquete() -> Path:
    """La carpeta que contiene el paquete ``convertersmartgrid``: ``src`` en desarrollo, ``site-packages`` instalado."""
    return Path(__file__).resolve().parent.parent


def pf_subprocess_env(pf_dir: Path | None, interprete: Path | None = None) -> dict[str, str]:
    """Entorno para un guion que importa ``powerfactory`` en otro proceso.

    103:RF-2, RF-6: con un intérprete que no es el del programa (el 3.9 de PowerFactory 2021), el guion necesita el
    paquete del conversor, que es código puro, y el ``numpy`` de su propia versión. El orden decide: la API, las
    librerías de ese intérprete y luego la carpeta del paquete; al revés cargaría el ``numpy`` compilado para el
    Python del programa, que no carga en otra versión.
    """
    env = os.environ.copy()
    if pf_dir is None:
        return env
    if interprete is None:
        interprete = python_for_pf(pf_dir)[0]
    rutas = [str(pf_dir)]
    if interprete is not None and os.path.normcase(str(Path(interprete).resolve())) != os.path.normcase(
            str(Path(sys.executable).resolve())):
        rutas += [str(Path(interprete).parent / 'Lib' / 'site-packages'), str(carpeta_del_paquete())]
        # El lanzador del programa fija PYTHONHOME en su Python 3.12: heredado, el 3.9 tomaba esa carpeta como
        # sys.prefix y «site» habría añadido las librerías del 3.12 (QA del rc4, 2026-11-11).
        env.pop('PYTHONHOME', None)
        env['PYTHONNOUSERSITE'] = '1'
    env['PYTHONPATH'] = os.pathsep.join([*rutas, *([env['PYTHONPATH']] if env.get('PYTHONPATH') else [])])
    env['PF_PYTHON'] = str(pf_dir)
    return env


# ---------------------------------------------------------------------------
# Guiones de PowerFactory que quedaron vivos
# ---------------------------------------------------------------------------


def procesos() -> list[dict]:
    """``[{pid, ppid, name, cmd}]`` de los procesos del equipo; ``[]`` si no se averigua."""
    import json

    sin_ventana = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        if os.name == 'nt':
            r = subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 'Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,'
                 'Name,CommandLine | ConvertTo-Json -Compress'],
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                timeout=20, creationflags=sin_ventana)
            filas = json.loads(r.stdout or '[]')
            filas = [filas] if isinstance(filas, dict) else filas
            return [{'pid': f.get('ProcessId'), 'ppid': f.get('ParentProcessId'),
                     'name': f.get('Name') or '', 'cmd': f.get('CommandLine') or ''}
                    for f in filas]
        r = subprocess.run(['ps', '-eo', 'pid=,ppid=,comm=,args='], capture_output=True,
                           text=True, timeout=20)
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    salida = []
    for linea in r.stdout.splitlines():
        campos = linea.split(None, 3)
        if len(campos) >= 3 and campos[0].isdigit() and campos[1].isdigit():
            salida.append({'pid': int(campos[0]), 'ppid': int(campos[1]), 'name': campos[2],
                           'cmd': campos[3] if len(campos) > 3 else ''})
    return salida


def guiones_pf_huerfanos(lista: list[dict], guiones: set[str], propio: int) -> list[dict]:
    """Guiones de ``tools/`` cuyo padre ya no existe: nadie los espera ni los cortará.

    2026-10-14: «Leer proyectos» agotó sus 180 s sin que PowerFactory diera el usuario,
    y a mano el mismo guion conectaba en 25 s. Un guion de una sesión anterior (la web
    reiniciada, o una prueba cortada) seguía vivo con el motor de DIgSILENT, que solo
    admite un proceso a la vez. Solo cuentan los huérfanos: un guion que alguien lanzó
    desde su consola tiene padre y no se toca.
    """
    vivos = {p['pid'] for p in lista}
    # 019:RF-7: el proceso que se queda abierto vive sin su cliente a propósito; se cierra
    # solo tras 2 minutos sin órdenes, o lo cierra la web si corta una orden.
    return [p for p in lista
            if p['pid'] != propio and p['ppid'] not in vivos
            and 'tools/pf_servidor.py' not in p['cmd'].replace(chr(92), '/')
            and 'python' in p['name'].lower()
            and any(f'tools/{g}' in p['cmd'].replace('\\', '/') for g in guiones)]


def terminar_arbol(pid: int) -> None:
    """Termina ``pid`` **con sus hijos**.

    ``.venv\\Scripts\\python.exe`` es un lanzador que arranca el Python real como hijo:
    ``Popen.terminate`` solo mataba el lanzador y el hijo seguía con PowerFactory.
    """
    if os.name == 'nt':
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(pid)], capture_output=True,
                       timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return
    import signal

    for p in procesos():
        if p['ppid'] == pid:
            terminar_arbol(p['pid'])
    try:
        os.kill(pid, getattr(signal, 'SIGKILL', signal.SIGTERM))
    except OSError:
        pass


def cerrar_guiones_pf_huerfanos() -> list[dict]:
    """Cierra los guiones de PowerFactory huérfanos y devuelve los que cerró."""
    guiones = {f.name for f in tools_dir().glob('*.py')}
    huerfanos = guiones_pf_huerfanos(procesos(), guiones, os.getpid())
    for p in huerfanos:
        try:
            terminar_arbol(p['pid'])
        except (OSError, subprocess.SubprocessError):
            pass
    return huerfanos


def powerfactory_abierto(lista: list[dict] | None = None) -> list[int]:
    """PID de las ventanas de PowerFactory abiertas: tienen el usuario y no se cierran solas."""
    return [p['pid'] for p in (procesos() if lista is None else lista)
            if p['name'].lower() == 'powerfactory.exe']
