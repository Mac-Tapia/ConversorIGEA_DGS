"""Carpeta de DIgSILENT donde quedan los proyectos importados desde DGS (spec 005).

Cada DGS importado creaba un proyecto suelto en la raíz del usuario, junto a los hechos a
mano, y «Leer proyectos» tenía que abrirlos todos: en la prueba del 2026-10-09 seguía a
los seis minutos con 3,7 GB de memoria. Los proyectos del conversor van ahora a una
carpeta propia, y la lectura solo mira esa carpeta.

El nombre de la carpeta es una convención de cada empresa (constitución P13): sale de
``config/perfil_empresa.json``, local y fuera de git, como ``demanda_medida_alias.json``.
Sin perfil, la carpeta se llama :data:`NOMBRE_POR_DEFECTO`.

Este módulo no importa ``powerfactory``: la web valida el nombre antes de abrir
DIgSILENT (RF-4), y los guiones de ``tools/`` lo usan con el Python de la API.
"""
from __future__ import annotations

import json
from pathlib import Path

NOMBRE_POR_DEFECTO = 'Conversor IGEA-DGS'
#: Clave del perfil de empresa. Cuando exista el perfil de la spec 002 (RF-31), la
#: clave pasa a él con el mismo nombre.
CLAVE_PERFIL = 'carpeta_proyectos_pf'
#: DIgSILENT corta ``loc_name`` a 40 caracteres; un nombre más largo dejaría la carpeta
#: con otro nombre y la siguiente lectura no la encontraría.
LARGO_MAXIMO = 40
#: Los que Windows no admite en un nombre de fichero, más el punto, que DIgSILENT usa
#: para separar el nombre de la clase («SI213.IntPrj»). Por comprobar en PF 2024 (T12).
NO_ADMITIDOS = frozenset('\\/:*?"<>|.')


class CarpetaError(ValueError):
    """El nombre de la carpeta o el perfil de empresa no son válidos."""


def ruta_perfil() -> Path:
    from .powerfactory_env import project_root

    return project_root() / 'config' / 'perfil_empresa.json'


def validar_nombre(nombre: object) -> str:
    """El nombre limpio de espacios en los extremos, o :class:`CarpetaError` que lo nombra."""
    if not isinstance(nombre, str):
        raise CarpetaError(f'El nombre de la carpeta de DIgSILENT debe ser un texto, no {nombre!r}.')
    limpio = nombre.strip()
    if not limpio:
        raise CarpetaError(f'El nombre de la carpeta de DIgSILENT está vacío: {nombre!r}.')
    if len(limpio) > LARGO_MAXIMO:
        raise CarpetaError(
            f'El nombre de la carpeta de DIgSILENT supera {LARGO_MAXIMO} caracteres: {nombre!r}.')
    malos = sorted({c for c in limpio if c in NO_ADMITIDOS or not c.isprintable()})
    if malos:
        raise CarpetaError(
            f'El nombre de la carpeta de DIgSILENT lleva caracteres no admitidos '
            f'({" ".join(repr(c) for c in malos)}): {nombre!r}.')
    return limpio


def nombre_de_perfil(ruta: Path | None = None) -> str:
    """Nombre de la carpeta según el perfil de empresa, o el de por defecto si no lo da."""
    ruta = ruta_perfil() if ruta is None else Path(ruta)
    if not ruta.is_file():
        return NOMBRE_POR_DEFECTO
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise CarpetaError(f'No se pudo leer el perfil de empresa {ruta.name}: {exc}') from exc
    if not isinstance(datos, dict):
        raise CarpetaError(f'El perfil de empresa {ruta.name} debe ser un objeto JSON.')
    nombre = datos.get(CLAVE_PERFIL)
    if nombre is None:
        return NOMBRE_POR_DEFECTO
    try:
        return validar_nombre(nombre)
    except CarpetaError as exc:
        raise CarpetaError(f'{exc} (perfil {ruta.name}, clave {CLAVE_PERFIL!r})') from exc
