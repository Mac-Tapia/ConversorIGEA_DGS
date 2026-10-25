"""Intérprete híbrido de órdenes (spec 026, RF-2 a RF-4).

Primero el Transformer propio; si su confianza no llega al umbral, el modelo local de
Ollama; si ninguno llega, no se adivina: se devuelve sin tarea para preguntar al operador
(RF-4). Unas reglas fijas completan lo que tiene forma inequívoca (un periodo, una ruta),
sin depender de ningún modelo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .sinteticos import MESES, normalizar

UMBRAL_TRANSFORMER = 0.85
UMBRAL_OLLAMA = 0.6

_NUMEROS = {'uno': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6, 'siete': 7, 'ocho': 8,
            'nueve': 9, 'diez': 10, 'quince': 15, 'veinte': 20, 'treinta': 30, 'cuarenta': 40, 'cincuenta': 50}


@dataclass
class Interpretacion:
    texto: str
    tarea: str | None
    confianza: float
    modelo: str
    datos: dict[str, list[dict]] = field(default_factory=dict)
    alternativas: list[tuple[str, float]] = field(default_factory=list)
    consultados: list[str] = field(default_factory=list)
    razon: str = ''


def periodo_de(texto: str) -> str | None:
    """«2026-07», «julio de 2026», «julio 2026», «el año 2025» o «2025» → AAAA-MM o AAAA."""
    t = normalizar(texto)
    m = re.search(r'\b(20\d{2})[-/](0?[1-9]|1[0-2])\b', t)
    if m:
        return f'{m.group(1)}-{int(m.group(2)):02d}'
    for i, mes in enumerate(MESES):
        m = re.search(rf'\b{mes}\s+(?:del?\s+)?(20\d{{2}})\b', t)
        if m:
            return f'{m.group(1)}-{i + 1:02d}'
    m = re.search(r'(?<![\w-])(20\d{2})(?![\w-])', t)
    return m.group(1) if m else None


def numero_de(texto: str) -> int | None:
    t = normalizar(texto)
    m = re.search(r'\b(\d{1,4})\b', t)
    if m:
        return int(m.group(1))
    for palabra, n in _NUMEROS.items():
        if re.search(rf'\b{palabra}\b', t):
            return n
    return None


_RUTA = re.compile(r'"([^"]+)"|([A-Za-z]:[\\/][^"]*?\.(?:xlsx|xls|csv|txt|mdb|bak)\b|[A-Za-z]:[\\/][^\s"]+)')


def ruta_de(texto: str) -> str | None:
    m = _RUTA.search(texto)
    return (m.group(1) or m.group(2)) if m else None


def _por_reglas(texto: str) -> dict[str, list[dict]]:
    datos: dict[str, list[dict]] = {}
    if (r := ruta_de(texto)) is not None:
        datos['ruta'] = [{'valor': r, 'confianza': 1.0, 'origen': 'regla'}]
    sin_ruta = texto.replace(r, ' ') if r else texto
    if (p := periodo_de(sin_ruta)) is not None:
        datos['periodo'] = [{'valor': p, 'confianza': 1.0, 'origen': 'regla'}]
    return datos


def interpretar(texto: str, *, transformer: Any = None, ollama: Any = None,
                umbral: float = UMBRAL_TRANSFORMER, umbral_ollama: float = UMBRAL_OLLAMA) -> Interpretacion:
    """La tarea y los datos de la orden, con quién la entendió (RF-7)."""
    texto = texto.strip()
    consultados = []
    previa = None
    if transformer is not None:
        previa = transformer.predecir(texto)
        consultados.append(f"Transformer {previa.get('version') or ''}".strip())
        if previa['confianza'] >= umbral:
            return _con_reglas(Interpretacion(texto, previa['tarea'], previa['confianza'], 'transformer',
                                              previa['datos'], previa.get('alternativas') or [], consultados))
    if ollama is not None:
        r = ollama.interpretar(texto)
        consultados.append(f'Ollama {ollama.modelo}' + ('' if r is not None else ' (no respondió)'))
        if r is not None and r.get('tarea') and r['confianza'] >= umbral_ollama:
            return _con_reglas(Interpretacion(texto, r['tarea'], r['confianza'], r['modelo'], r['datos'],
                                              [], consultados, r.get('razon') or ''))
    alternativas = []
    if previa is not None:
        alternativas = [(previa['tarea'], previa['confianza'])] + list(previa.get('alternativas') or [])
    return Interpretacion(texto, None, previa['confianza'] if previa else 0.0, 'ninguno', {}, alternativas,
                          consultados)


def _con_reglas(i: Interpretacion) -> Interpretacion:
    """Lo que tiene forma inequívoca manda sobre lo que marcó el modelo."""
    for tipo, valores in _por_reglas(i.texto).items():
        i.datos[tipo] = valores
    return i
