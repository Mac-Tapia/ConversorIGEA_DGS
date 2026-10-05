"""Comparación incremental por ID de fuente estable (sección U16).

Clasifica cada registro entre dos entregas o entre la base de empresa y la fuente
oficial: ``ADDED``, ``REMOVED``, ``MODIFIED_GEOMETRY``, ``MODIFIED_ATTRIBUTES``,
``UNCHANGED``, ``UNRESOLVED_IDENTITY``. Nunca se muta ninguna fuente.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

CLASSES = (
    'ADDED', 'REMOVED', 'MODIFIED_GEOMETRY', 'MODIFIED_ATTRIBUTES',
    'UNCHANGED', 'UNRESOLVED_IDENTITY',
)


@dataclass
class DiffResult:
    classified: dict[str, list[str]] = field(default_factory=lambda: {c: [] for c in CLASSES})

    def as_dict(self) -> dict:
        return {c: list(v) for c, v in self.classified.items()}

    def summary(self) -> dict:
        return {c: len(v) for c, v in self.classified.items()}


def _geom_key(record: Mapping, key: str) -> str:
    value = record.get(key)
    if value is None:
        return ''
    return repr(value)


def diff_records(
    previous: Mapping[str, Mapping],
    current: Mapping[str, Mapping],
    *,
    geometry_key: str = 'geometry',
    attribute_keys: Sequence[str] = (),
) -> DiffResult:
    """Compara dos mapas ``{id_fuente: registro}``.

    Los IDs que no casan se marcan ``UNRESOLVED_IDENTITY``. Los que casan se
    comparan por geometría y por atributos.
    """
    result = DiffResult()
    prev_ids = set(previous)
    cur_ids = set(current)
    for sid in sorted(cur_ids - prev_ids):
        result.classified['ADDED'].append(sid)
    for sid in sorted(prev_ids - cur_ids):
        result.classified['REMOVED'].append(sid)
    for sid in sorted(prev_ids & cur_ids):
        before = previous[sid]
        after = current[sid]
        if _geom_key(before, geometry_key) != _geom_key(after, geometry_key):
            result.classified['MODIFIED_GEOMETRY'].append(sid)
            continue
        if any(before.get(k) != after.get(k) for k in attribute_keys):
            result.classified['MODIFIED_ATTRIBUTES'].append(sid)
            continue
        result.classified['UNCHANGED'].append(sid)
    return result


def diff_periods(
    previous: Mapping[str, Mapping],
    current: Mapping[str, Mapping],
    *,
    geometry_key: str = 'geometry',
    attribute_keys: Sequence[str] = (),
    id_resolver=None,
) -> DiffResult:
    """Versión con resolución de identidad opcional para IDs que no casan exactamente.

    ``id_resolver(a, b)`` devuelve True si ambas claves corresponden al mismo objeto.
    Los que resuelve se comparan; los que no, ``UNRESOLVED_IDENTITY``.
    """
    if id_resolver is None:
        return diff_records(previous, current, geometry_key=geometry_key, attribute_keys=attribute_keys)

    result = DiffResult()
    matched_prev: set[str] = set()
    remaining_prev = dict(previous)
    remaining_cur = set(current)
    for sid in sorted(current):
        match = next(
            (p for p in remaining_prev
             if sid != p and id_resolver(sid, p) and p not in matched_prev),
            None,
        )
        if match is not None:
            matched_prev.add(match)
            remaining_cur.discard(sid)
            before = previous[match]
            after = current[sid]
            if _geom_key(before, geometry_key) != _geom_key(after, geometry_key):
                result.classified['MODIFIED_GEOMETRY'].append(sid)
            elif any(before.get(k) != after.get(k) for k in attribute_keys):
                result.classified['MODIFIED_ATTRIBUTES'].append(sid)
            else:
                result.classified['UNCHANGED'].append(sid)
    # Tras resolver, lo que queda sin pareja se marca sin resolver.
    result.classified['UNRESOLVED_IDENTITY'].extend(sorted(remaining_cur))
    return result
