"""Intérprete híbrido de órdenes (spec 026, RF-2 a RF-4).

Primero el Transformer propio; si su confianza no llega al umbral, el modelo local de
Ollama; si ninguno llega, no se adivina: se devuelve sin tarea para preguntar al operador
(RF-4). Unas reglas fijas completan lo que tiene forma inequívoca (un periodo, una ruta),
sin depender de ningún modelo.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .maestro_real import NINGUNA
from .sinteticos import MESES, normalizar
from .contratos_salida import validar_orden
from .tareas import TAREAS

UMBRAL_TRANSFORMER = 0.85
UMBRAL_OLLAMA = 0.6
#: 075:RF-37: hasta qué lugar de las opciones del modelo se le cree a «esto no es una orden» cuando duda.
PUESTO_CHARLA = 2

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


def _prediccion_valida(prediccion) -> bool:
    """047:RF-1: valida también predicciones de modelos locales cargados de disco."""
    try:
        # «ninguna» es una respuesta válida del modelo: para el contrato, una orden sin tarea (069:RF-15).
        tarea = None if prediccion['tarea'] == NINGUNA else prediccion['tarea']
        validar_orden({'tarea': tarea, 'confianza': prediccion['confianza'],
                       'datos': {t: [d['valor'] for d in valores]
                                 for t, valores in prediccion['datos'].items()}})
        return True
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


_PREGUNTA = re.compile(r'^\W*(como|que|por que|porque|cual|cuales|cuando|donde|explica|explicame)\b')


def _por_frase_literal(texto: str, transformer: Any) -> str | None:
    """La tarea que el modelo en uso no conoce y la orden nombra (067:RF-36). Sin esto, las tareas
    nuevas no se alcanzarían hasta que un candidato pase las puertas: el modelo en uso entendía
    «haz la escalera de …» como ``obras``, que aplica otra cosa. Una pregunta sobre ella no es una orden."""
    t = normalizar(texto)
    pregunta = '?' in texto or bool(_PREGUNTA.search(t))
    conocidas = set(getattr(transformer, 'tareas', None) or ())
    for tarea in TAREAS.values():
        if pregunta and not tarea.literal_en_pregunta:
            continue
        if tarea.nombre not in conocidas and any(re.search(f, t) for f in tarea.frases_literales):
            return tarea.nombre
    return None


def charla_cerca(modelo: Any, texto: str) -> bool:
    """Si el modelo tiene «ninguna» entre sus primeras opciones; el que no tiene esa clase no opina (075:RF-41)."""
    puesto = getattr(modelo, 'puesto_ninguna', None)
    lugar = puesto(texto) if callable(puesto) else None
    return type(lugar) is int and lugar <= PUESTO_CHARLA


def interpretar(texto: str, *, transformer: Any = None, ollama: Any = None,
                umbral: float = UMBRAL_TRANSFORMER, umbral_ollama: float = UMBRAL_OLLAMA,
                contexto: Sequence[str] = (), umbrales: Mapping[str, float] | None = None) -> Interpretacion:
    """La tarea y los datos de la orden, con quién la entendió (RF-7)."""
    texto = texto.strip()
    consultados = []
    previa = None
    if transformer is not None:
        previa = transformer.predecir(texto)
        valida = _prediccion_valida(previa)
        version = previa.get('version') if isinstance(previa, Mapping) else None
        consultados.append(f"Transformer {version or ''}".strip() +
                           ('' if valida else ' (salida inválida)'))
        if not valida:
            previa = None
    if (literal := _por_frase_literal(texto, transformer)) is not None:
        # Los datos los sigue marcando el modelo si los ve; el plan los contrasta o los toma del texto.
        return _con_reglas(Interpretacion(texto, literal, 1.0, 'catalogo', dict((previa or {}).get('datos') or {}), [],
                                          [*consultados, f'frase literal de «{literal}»']))
    if previa is not None and previa['tarea'] == NINGUNA:
        # 069:RF-15: el modelo dice que esto no es una orden. La charla pasaba el umbral y proponía
        # tareas (62,6 % de los mensajes reales, 2026-11-02): ni se adivina ni se le pregunta a otro.
        return Interpretacion(texto, None, previa['confianza'], 'ninguno', {}, list(previa.get('alternativas') or []),
                              consultados, 'no parece una orden del catálogo')
    if transformer is not None:
        # 069:RF-26: el umbral calibrado del modelo, si lo trae, en vez del fijo; 027:RF-38: el de su tarea, si lo hay.
        calibrado = getattr(transformer, 'umbral', None)
        minimo = calibrado if type(calibrado) is float and umbral == UMBRAL_TRANSFORMER else umbral
        exigida = None if previa is None else (umbrales or {}).get(previa['tarea'], minimo)
        if (previa is not None and not getattr(ollama, 'revisar_transformer', False)
                and previa['confianza'] >= exigida):
            return _con_reglas(Interpretacion(texto, previa['tarea'], previa['confianza'], 'transformer',
                                              previa['datos'], previa.get('alternativas') or [], consultados))
        if (ollama is not None and previa is not None and previa['confianza'] < exigida
                and charla_cerca(transformer, texto)):
            # 075:RF-37: «muchas gracias» a secas cayó bajo el umbral y Ollama impuso `estado` con confianza 1,0
            # (web, 2026-11-02). El modelo ya dudaba de que fuera una orden: se le pregunta al operador, no a otro modelo.
            return Interpretacion(texto, None, previa['confianza'], 'ninguno', {},
                                  [(previa['tarea'], previa['confianza']), *(previa.get('alternativas') or [])],
                                  [*consultados, 'sin Ollama: el modelo duda de que sea una orden'],
                                  'puede que no sea una orden del catálogo')
    if ollama is not None:
        # 027:RF-37, RF-39: con órdenes parecidas y notas de fallos, si las hay.
        r = ollama.interpretar(texto, contexto=list(contexto)) if contexto else ollama.interpretar(texto)
        consultados.append(f'Ollama {ollama.modelo}' + ('' if r is not None else ' (no respondió)'))
        if r is not None and _prediccion_valida(r) and r.get('tarea') and r['confianza'] >= umbral_ollama:
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
