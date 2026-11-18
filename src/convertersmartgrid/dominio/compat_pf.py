"""Lo que cargan los guiones de DIgSILENT vale en el Python más antiguo de las PowerFactory soportadas (spec 103, RF-5).

PowerFactory 2021 carga su API solo con Python 3.9. Con un 3.9 real (el embebido oficial de python.org), 12 de los 22
guiones de ``tools/`` no llegaban a cargar por ``itertools.pairwise`` (3.10), y ``zip(..., strict=...)`` (3.10) fallaba al
ejecutarse. Aquí van sus equivalentes; en 3.10 o posterior se usan los nativos.
"""
from __future__ import annotations

import sys
from collections.abc import Iterable, Iterator
from itertools import tee
from typing import Any


def pairwise(iterable: Iterable[Any]) -> Iterator[tuple[Any, Any]]:
    """``itertools.pairwise`` (3.10): (a, b), (b, c), …"""
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)


def zip_estricto(*iterables: Iterable[Any]) -> Iterator[tuple[Any, ...]]:
    """``zip(..., strict=True)`` (3.10): falla si las secuencias no tienen el mismo largo."""
    if sys.version_info >= (3, 10):
        yield from zip(*iterables, strict=True)
        return
    iteradores = [iter(i) for i in iterables]
    while True:
        fila, agotados = [], 0
        for it in iteradores:
            try:
                fila.append(next(it))
            except StopIteration:
                agotados += 1
        if agotados == len(iteradores):
            return
        if agotados:
            raise ValueError('zip_estricto: las secuencias tienen distinto largo')
        yield tuple(fila)
