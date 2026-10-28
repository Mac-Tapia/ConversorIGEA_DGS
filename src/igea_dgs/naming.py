"""Universal naming helpers for CYMDIST/IGEA NetworkIDs and selectors.

Feeder IDs vary by utility (e.g. ``NET_2030_142_IN111``, ``ALIMENTADOR-12``,
``Feeder.A1``). Short names and selectors must not assume one company's pattern.
"""

from __future__ import annotations

import re
from functools import lru_cache

# Tokens may be separated by underscore, hyphen, dot, slash or backslash.
_TOKEN_SPLIT = re.compile(r'[_\-./\\]+')


def feeder_tokens(network_id: str) -> list[str]:
    text = (network_id or '').strip()
    if not text:
        return []
    return [part for part in _TOKEN_SPLIT.split(text) if part]


def feeder_short_name(network_id: str) -> str:
    """Display / output basename for a NetworkID (last path-like token).

    Con las siglas canónicas del perfil (022:RF-90): la SET nueva Chincha Nueva viene en la
    red de RED_231026 como CN101 a CN201 y la empresa la llama CHN101 a CHN201; la
    estructura declara ``"siglas": ["CHN", "CN"]`` y desde la carga del TXT se llama CHN101
    en el inventario, el DGS y la calibración. Sin perfil, el nombre de la red tal cual.
    """
    parts = feeder_tokens(network_id)
    nombre = parts[-1] if parts else (network_id or '').strip()
    m = re.match(r'([A-Za-z]+)(\d.*)$', nombre)
    if m:
        canonicas = _siglas_canonicas()
        if m.group(1).upper() in canonicas:
            return canonicas[m.group(1).upper()] + m.group(2)
    return nombre


def _siglas_canonicas() -> dict[str, str]:
    """``{siglas alternativas: canónicas}`` de la estructura del perfil activo, leída una vez
    por versión del perfil (ruta y fecha del fichero)."""
    try:
        from .perfil_empresa import ruta_perfil_activo

        ruta = ruta_perfil_activo()
        sello = (str(ruta), ruta.stat().st_mtime_ns if ruta.is_file() else 0)
    except OSError:
        return {}
    return _siglas_canonicas_de(sello)


_TROZO = re.compile(r'(?<![A-Za-z0-9])([A-Za-z]+)(\d+)(?![A-Za-z0-9])')


def nombre_canonico(nombre: str, canonicas: dict[str, str] | None = None) -> str:
    """El nombre con la sigla canónica en cada trozo «sigla + número» (022:RF-90, 027:T23).

    El nodo de cabecera de Chincha Nueva llegaba al DGS como ``NODE_2030_1192582_CN101``
    aunque el alimentador ya se llamaba CHN101: ``NODE_2030_1192582_CHN101``. Solo cambia las
    siglas alternativas de la estructura del perfil; sin perfil, el nombre tal cual.
    """
    canonicas = _siglas_canonicas() if canonicas is None else canonicas
    if not canonicas or not nombre:
        return nombre
    return _TROZO.sub(lambda m: canonicas.get(m.group(1).upper(), m.group(1)) + m.group(2)
                      if m.group(1).upper() in canonicas else m.group(0), nombre)


@lru_cache(maxsize=4)
def _siglas_canonicas_de(_sello: tuple[str, int]) -> dict[str, str]:
    from .estructura import EstructuraError
    from .perfil_empresa import PerfilError, estructura_empresa

    try:
        estructura = estructura_empresa()
    except (PerfilError, EstructuraError, OSError, ValueError):
        return {}
    if estructura is None:
        return {}
    return {s.upper(): st.siglas[0].upper() for st in estructura.sets.values()
            if len(st.siglas) > 1 for s in st.siglas[1:]}


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


def codigo_de_tipo_linea(nombre: str) -> str:
    """El código de conductor de un ``TypLne`` del DGS: ``AA12003D_22_9kV`` → ``AA12003D``.

    Inverso de :func:`nombre_con_tension`, y sin el ``(1)`` que DIgSILENT añade a un nombre
    repetido. Con él la calibración de «Sin proyecto» busca la ficha del conductor en el
    catálogo, que va por código (032:RF-14).
    """
    nombre = re.sub(r'\(\d+\)$', '', (nombre or '').strip())
    return re.sub(r'_\d+(?:_\d+)?kV$', '', nombre)
