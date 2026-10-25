"""Dónde guarda el asistente lo suyo, siempre en la máquina (spec 026, P9).

Ejemplos de órdenes, modelos, índice del proyecto y registros (decisiones, consultas a
internet, avisos). Los registros son JSONL de solo añadir: auditar es leerlos (RF-28,
RF-31); nada se reescribe.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

_cerrojo = threading.Lock()


def raiz() -> Path:
    """``IGEA_ASISTENTE_DATA`` o ``_asistente`` junto a los espacios de la web."""
    env = os.environ.get('IGEA_ASISTENTE_DATA', '').strip()
    if env:
        return Path(env)
    from ..web.workspace import data_root

    return data_root() / '_asistente'


def ahora() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


def anotar(registro: str, fila: dict[str, Any]) -> dict[str, Any]:
    """Añade una fila con su fecha al registro ``<registro>.jsonl``."""
    fila = {'fecha': ahora(), **fila}
    ruta = raiz() / f'{registro}.jsonl'
    with _cerrojo:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, 'a', encoding='utf-8') as f:
            f.write(json.dumps(fila, ensure_ascii=False, default=str) + '\n')
    return fila


def leer(registro: str, ultimas: int | None = None) -> list[dict[str, Any]]:
    """Las filas del registro, en orden; una línea rota se salta (un corte a mitad)."""
    ruta = raiz() / f'{registro}.jsonl'
    if not ruta.is_file():
        return []
    filas = []
    for linea in ruta.read_text(encoding='utf-8').splitlines():
        try:
            filas.append(json.loads(linea))
        except ValueError:
            continue
    return filas[-ultimas:] if ultimas else filas


def guardar_json(nombre: str, datos: Any) -> Path:
    """Escribe ``<nombre>.json`` de forma atómica."""
    ruta = raiz() / f'{nombre}.json'
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    os.replace(tmp, ruta)
    return ruta


def leer_json(nombre: str, defecto: Any = None) -> Any:
    ruta = raiz() / f'{nombre}.json'
    if not ruta.is_file():
        return defecto
    try:
        return json.loads(ruta.read_text(encoding='utf-8'))
    except ValueError:
        return defecto
