"""Normalización pura de códigos y números de medición (002 U1; 004 RF-31)."""
from __future__ import annotations

import math
import re
from typing import Any


def clave_codigo(valor: Any) -> str:
    """Código comparable entre libros: ``1234.0``, ``'1234'`` y ``' 001234'`` son el mismo.

    El mismo suministro llega como número en un libro y como texto en otro; y un medidor
    se escribe ``X-AB12`` en uno y ``x ab12`` en otro.
    """
    if valor is None or isinstance(valor, bool):
        return ''
    if isinstance(valor, float):
        if not math.isfinite(valor):
            return ''
        if valor.is_integer():
            valor = int(valor)
    texto = re.sub(r'[\s_\-.]+', '', str(valor).strip()).casefold()
    if texto.isdigit():
        texto = texto.lstrip('0') or '0'
    return texto

def numero(valor: Any) -> float | None:
    """Número finito, o ``None`` si la celda está vacía o no es un número (RF-31)."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor) if math.isfinite(valor) else None
    texto = str(valor).strip().replace(',', '.')
    try:
        v = float(texto)
    except ValueError:
        return None
    return v if math.isfinite(v) else None
