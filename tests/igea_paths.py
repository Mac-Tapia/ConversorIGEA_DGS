"""Locate IGEA/CYMDIST TXT exports for integration tests."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RED_NAMES = (
    'RED_030826(1).txt',
    'RED_030826.txt',
)
LOAD_NAMES = (
    'CARGA_030826(1).txt',
    'CARGA_030826.txt',
)
EQUIP_NAMES = (
    'BD_Equipo_V261124 (1)(1).txt',
    'BD_Equipo_V261124.txt',
    'BD_Equipo.txt',
)

SKIP_MSG = (
    'TXT IGEA no encontrados. Defina IGEA_TXT_DIR (carpeta con RED_*.txt, '
    'CARGA_*.txt, BD_Equipo*.txt) o IGEA_RED / IGEA_LOADS / IGEA_EQUIPMENT.'
)


def first_existing(directory: Path, names: tuple[str, ...]) -> Path | None:
    if not directory.is_dir():
        return None
    for name in names:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    patterns = {
        RED_NAMES: 'RED_*.txt',
        LOAD_NAMES: 'CARGA_*.txt',
        EQUIP_NAMES: 'BD_Equipo*.txt',
    }
    pattern = patterns.get(names)
    if pattern:
        matches = sorted(directory.glob(pattern))
        if matches:
            return matches[0]
    return None


def search_roots() -> list[Path]:
    roots: list[Path] = []
    env_dir = os.environ.get('IGEA_TXT_DIR', '').strip()
    if env_dir:
        roots.append(Path(env_dir))
    roots.extend(
        [
            Path('/mnt/data'),
            Path(r'\\mnt\data'),
            PROJECT_ROOT / 'data',
            PROJECT_ROOT / 'fixtures',
        ]
    )
    seen: set[Path] = set()
    unique: list[Path] = []
    for root in roots:
        try:
            key = root.resolve()
        except OSError:
            key = root
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def resolve_igea_txt_paths(
    roots: list[Path] | None = None,
) -> tuple[Path, Path, Path] | None:
    """Return (RED, CARGA, BD_Equipo) or None if unavailable."""
    env_red = os.environ.get('IGEA_RED', '').strip()
    env_loads = os.environ.get('IGEA_LOADS', '').strip()
    env_equip = os.environ.get('IGEA_EQUIPMENT', '').strip()
    if env_red and env_loads and env_equip:
        red, loads, equip = Path(env_red), Path(env_loads), Path(env_equip)
        if red.is_file() and loads.is_file() and equip.is_file():
            return red, loads, equip

    for root in roots if roots is not None else search_roots():
        red = first_existing(root, RED_NAMES)
        loads = first_existing(root, LOAD_NAMES)
        equip = first_existing(root, EQUIP_NAMES)
        if red and loads and equip:
            return red, loads, equip
    return None
