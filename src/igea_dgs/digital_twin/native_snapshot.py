"""Piezas puras de la lectura nativa del gemelo digital (spec 024, T5).

La lectura con DIgSILENT vive en ``tools/digital_twin_snapshot_pf.py``; aquí queda lo que
no necesita la API: la identidad estable de un objeto, la huella de un trazado y las
islas eléctricas a partir de los tramos cerrados.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence


def identidad_nativa(clase: str, nombre_completo: str, raiz: str = '') -> str:
    """``Clase:ruta`` relativa al proyecto.

    La API devuelve un envoltorio nuevo en cada acceso, así que ni ``id()`` ni el nombre
    corto sirven: dos SED de alimentadores distintos se llaman igual y, con ``id()``, los
    extremos de las líneas de IN111 no se reconocían (copia de IN111_TA225, 2026-10-15).
    """
    ruta = nombre_completo
    if raiz and ruta.startswith(raiz):
        ruta = ruta[len(raiz):].lstrip('\\/')
    return f'{clase}:{ruta}'


def huella_gps(puntos: Sequence[Sequence[float]]) -> str:
    """SHA-256 del trazado redondeado a 1e-8 grados (≈ 1 mm), para notar si cambió (RF-3)."""
    filas = [[round(float(p[0]), 8), round(float(p[1]), 8)] for p in puntos]
    return hashlib.sha256(json.dumps(filas, separators=(',', ':')).encode('utf-8')).hexdigest()


def componentes(barras: Iterable[str], tramos: Iterable[tuple[str, str, bool]]) -> list[list[str]]:
    """Islas eléctricas: barras unidas por tramos cerrados, cada una ordenada (RF-2).

    No supone red radial ni una sola tensión: un enlace cerrado entre 10 y 22,9 kV dejaría
    una isla con las dos, que es justo lo que el episodio tiene que mostrar.
    """
    padre: dict[str, str] = {b: b for b in barras}

    def raiz(b: str) -> str:
        while padre[b] != b:
            padre[b] = padre[padre[b]]
            b = padre[b]
        return b

    for u, v, cerrado in tramos:
        if not cerrado:
            continue
        padre.setdefault(u, u)
        padre.setdefault(v, v)
        ru, rv = raiz(u), raiz(v)
        if ru != rv:
            padre[max(ru, rv)] = min(ru, rv)
    grupos: dict[str, list[str]] = {}
    for b in padre:
        grupos.setdefault(raiz(b), []).append(b)
    return sorted(sorted(g) for g in grupos.values())
