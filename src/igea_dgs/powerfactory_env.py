"""Dónde está la API de PowerFactory y qué intérprete puede cargarla.

Vivía en ``gui.py``. Se saca aquí porque ahora la usan dos interfaces —la web y la de
escritorio— y ninguna de las dos debe importar la otra: la API web no puede arrastrar
Tk, y la lógica no puede existir en dos copias que acaben divergiendo.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Carpeta por defecto de la API Python de PowerFactory (se sobrescribe con PF_PYTHON).
DEFAULT_PF_PYTHON = Path(r'C:\Program Files\DIgSILENT\PowerFactory 2024\Python\3.12')


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


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


def pf_python_dir() -> Path | None:
    env = os.environ.get('PF_PYTHON', '').strip()
    if env:
        path = Path(env)
        return path if path.is_dir() else None
    if DEFAULT_PF_PYTHON.is_dir():
        return DEFAULT_PF_PYTHON
    # Carpetas de versión hermanas bajo la instalación de DIgSILENT.
    root = Path(r'C:\Program Files\DIgSILENT')
    if root.is_dir():
        candidates = sorted(root.glob('PowerFactory */Python/3.*'),
                            key=version_key, reverse=True)
        # Primero el que trae la extensión; solo si ninguno la tiene se acepta otro.
        for candidate in candidates:
            if candidate.is_dir() and (candidate / 'powerfactory.pyd').is_file():
                return candidate
        for candidate in candidates:
            if candidate.is_dir():
                return candidate
    return None


def pf_api_version(pf_dir: Path | None) -> str | None:
    """Versión de Python que exige la API de PowerFactory ('3.12' en PF 2024)."""
    if pf_dir is None:
        return None
    parts = pf_dir.name.strip().split('.')
    if len(parts) == 2 and all(p.isdigit() for p in parts):
        return pf_dir.name.strip()
    return None


def python_for_pf(pf_dir: Path | None) -> tuple[Path | None, str]:
    """Intérprete capaz de cargar ``powerfactory.pyd``, y por qué se eligió.

    ``powerfactory.pyd`` es una extensión binaria compilada contra una versión
    concreta de CPython: solo carga en esa versión (PowerFactory 2024 llega a 3.12).
    Lanzar el script de aceptación con ``sys.executable`` falla con «DLL load failed»
    en cuanto el entorno del conversor usa un Python más nuevo, por ejemplo 3.14.

    Prioridad: el intérprete actual si ya coincide, ``IGEA_PF_INTERPRETER``,
    el lanzador ``py -X.Y``, y por último rutas de instalación habituales.
    """
    wanted = pf_api_version(pf_dir)
    current = f'{sys.version_info.major}.{sys.version_info.minor}'
    if wanted is None or wanted == current:
        return Path(sys.executable), f'interprete actual ({current})'

    override = os.environ.get('IGEA_PF_INTERPRETER', '').strip()
    if override and Path(override).is_file():
        return Path(override), f'IGEA_PF_INTERPRETER ({override})'

    launcher = shutil.which('py')
    if launcher:
        try:
            probe = subprocess.run(
                [launcher, f'-{wanted}', '-c', 'import sys; print(sys.executable)'],
                capture_output=True, text=True, timeout=20, check=False,
            )
            candidate = Path((probe.stdout or '').strip())
            if probe.returncode == 0 and candidate.is_file():
                return candidate, f'py -{wanted}'
        except (OSError, subprocess.SubprocessError):
            pass

    major, minor = wanted.split('.')
    local = os.environ.get('LOCALAPPDATA', '')
    candidates = [
        Path(rf'C:\Python{major}{minor}\python.exe'),
        Path(rf'C:\Program Files\Python{major}{minor}\python.exe'),
    ]
    if local:
        candidates.insert(0, Path(local) / 'Programs' / 'Python' / f'Python{major}{minor}' / 'python.exe')
    for candidate in candidates:
        if candidate.is_file():
            return candidate, f'instalacion local {wanted}'

    return None, f'no se encontro Python {wanted}'


def pf_subprocess_env(pf_dir: Path | None) -> dict[str, str]:
    """Entorno para un guion que importa ``powerfactory`` en otro proceso."""
    env = os.environ.copy()
    if pf_dir is not None:
        env['PYTHONPATH'] = str(pf_dir) + os.pathsep + env.get('PYTHONPATH', '')
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
