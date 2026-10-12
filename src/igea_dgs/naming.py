"""Universal naming helpers for CYMDIST/IGEA NetworkIDs and selectors.

Feeder IDs vary by utility (e.g. ``NET_2030_142_IN111``, ``ALIMENTADOR-12``,
``Feeder.A1``). Short names and selectors must not assume one company's pattern.
"""

from __future__ import annotations

import re

# Tokens may be separated by underscore, hyphen, dot, slash or backslash.
_TOKEN_SPLIT = re.compile(r'[_\-./\\]+')


def feeder_tokens(network_id: str) -> list[str]:
    text = (network_id or '').strip()
    if not text:
        return []
    return [part for part in _TOKEN_SPLIT.split(text) if part]


def feeder_short_name(network_id: str) -> str:
    """Display / output basename for a NetworkID (last path-like token)."""
    parts = feeder_tokens(network_id)
    return parts[-1] if parts else (network_id or '').strip()


def sort_key_feeder(network_id: str) -> str:
    return feeder_short_name(network_id).lower()


def sufijo_tension(kv: float) -> str:
    """Sufijo de tensión de los nombres del conversor: ``22_9kV``, ``10kV``.

    Vive aquí, y no en ``dgs`` ni en ``combine``, porque lo usan el DGS de la red unida
    y las copias de tipo de las obras (spec 011, RF-61): con dos reglas, el mismo
    conductor a 22,9 kV saldría con dos nombres según lo creara el DGS o una obra.
    """
    return f'{kv:g}kV'.replace('.', '_')


def nombre_con_tension(base: str, kv: float) -> str:
    """Nombre de un tipo con su tensión: ``AA12003D_22_9kV``.

    Los puntos del nombre base también pasan a ``_``, como hacía el conversor desde el
    principio; cambiarlo alteraría los ``loc_name`` de los DGS ya importados.
    """
    return f'{base}_{kv:g}kV'.replace('.', '_')
