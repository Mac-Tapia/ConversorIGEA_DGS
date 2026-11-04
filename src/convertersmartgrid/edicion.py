"""Qué edición corre: la de desarrollo o la de producto (086:RF-22).

Una sola función para preguntarlo, para que la T12 (lo que se oculta en la edición de
producto) y las salidas a la red no acaben leyendo dos variables distintas.
"""
from __future__ import annotations

import os

VARIABLE_EDICION = 'CSG_EDICION'


def es_edicion_producto() -> bool:
    """Si esto es la edición de producto. Sin la variable es desarrollo: el árbol de hoy no cambia."""
    return os.environ.get(VARIABLE_EDICION, '').strip().lower() == 'producto'
