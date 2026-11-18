"""Las rutas de fichero de antes de 002 T7 en los conjuntos sellados y en los documentos fechados (002:RF-1, RF-21).

Los conjuntos de evaluación del asistente están sellados por su huella: no se reescriben cuando un módulo cambia de
carpeta. Al leerlos, cada ruta ``src/convertersmartgrid/…`` que ya no existe se traduce con
``docs/architecture/rutas_antes_002.json`` (ruta vieja → ruta nueva, por el prefijo más largo). Lo que no está en el mapa
se deja como venía.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

PREFIJO = 'src/convertersmartgrid/'


def _raiz() -> Path:
    return Path(__file__).resolve().parents[4]


@lru_cache(maxsize=4)
def _mapa(raiz: str) -> tuple[tuple[str, str], ...]:
    ruta = Path(raiz) / 'docs' / 'architecture' / 'rutas_antes_002.json'
    if not ruta.is_file():
        return ()
    rutas = json.loads(ruta.read_text(encoding='utf-8')).get('rutas') or {}
    return tuple(sorted(rutas.items(), key=lambda kv: -len(kv[0])))


def ruta_vigente(ruta: str, raiz: Path | None = None) -> str:
    """La ruta de hoy de una ruta del repositorio escrita antes de 002 T7 (con su «:línea» o su ancla detrás)."""
    if not isinstance(ruta, str) or not ruta.startswith(PREFIJO):
        return ruta
    for viejo, nuevo in _mapa(str(raiz or _raiz())):
        if ruta == viejo or ruta.startswith((viejo + '/', viejo + '.py', viejo + ':')):
            return nuevo + ruta[len(viejo):]
    return ruta


def traducir(datos: Any, raiz: Path | None = None) -> Any:
    """``datos`` con cada cadena que es ruta del repositorio traducida (listas y diccionarios, a cualquier altura)."""
    if isinstance(datos, str):
        return ruta_vigente(datos, raiz)
    if isinstance(datos, Mapping):
        return {k: traducir(v, raiz) for k, v in datos.items()}
    if isinstance(datos, list):
        return [traducir(v, raiz) for v in datos]
    return datos
