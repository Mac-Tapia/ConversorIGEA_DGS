"""Dónde está la API de PowerFactory y qué intérprete puede cargarla.

La detección vive en un módulo independiente para que la usen la web, la aceptación y
los comandos sin duplicar rutas ni decisiones de versión.
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
