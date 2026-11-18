"""Cuándo construir cada obra: árbol de decisión y proceso de decisión de Markov (spec 087, RF-14 a RF-16, RF-29).

La escalera dice qué obra cumple hoy con las cargas nuevas, no cuándo conviene la de un alimentador que aún tiene margen.
Un planificador lo decide bajo incertidumbre: cuánto crecerá la demanda y hasta cuándo aguanta la red.

Incumplir no tiene precio inventado: es una restricción. Cuando la demanda pasa del margen, la obra se construye ese año.
Lo que se decide es cuánto se puede diferir, y el costo de cada año cuenta solo desde que está construida.

Puro: no habla con DIgSILENT. El margen lo da el oráculo; los costos, la escalera.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

#: Reparto de referencia alrededor de la tasa medida (087:RF-14): se dice en el resultado (RF-16).
FACTORES_ESCENARIO = (('baja', 0.5, 0.25), ('media', 1.0, 0.5), ('alta', 1.5, 0.25))
#: Probabilidad de seguir en el mismo régimen de crecimiento al año siguiente (087:RF-15).
PERSISTENCIA = 0.7
#: Resolución del crecimiento acumulado en el proceso de decisión: 0,5 % de demanda.
PASO_DEMANDA = 0.005


def escenarios_de_demanda(tasa: float) -> list[dict[str, float | str]]:
    """087:RF-14: demanda baja, media y alta alrededor de la tasa anual de crecimiento."""
    return [{'nombre': n, 'tasa': float(tasa) * f, 'probabilidad': p} for n, f, p in FACTORES_ESCENARIO]


def anio_limite(margen: float | None, tasa: float) -> int | None:
    """El primer año en que la demanda pasa del margen; 0 si ya no cumple; ``None`` si no llega nunca."""
    if margen is None or margen <= 0:
        return 0
    if tasa <= 0:
        return None
    return math.floor(math.log1p(margen) / math.log1p(tasa)) + 1


def _valor(costo: float, desde: int, horizonte: int, descuento: float) -> float:
    """El costo anual desde el año de construcción hasta el horizonte, en valor presente."""
    return sum(costo / (1 + descuento) ** t for t in range(desde, horizonte))


def arbol_de_decision(nombre: str, costo_anual: float, margen: float | None, escenarios: Sequence[Mapping[str, Any]],
                      horizonte: int, descuento: float) -> dict[str, Any]:
    """087:RF-14: construir ahora o diferir hasta que cada escenario lo exija, con su valor esperado."""
    ahora = _valor(costo_anual, 0, horizonte, descuento)
    ramas, diferir = [], 0.0
    for e in escenarios:
        limite = anio_limite(margen, float(e['tasa']))
        anio = horizonte if limite is None else min(limite, horizonte)
        valor = _valor(costo_anual, anio, horizonte, descuento)
        diferir += float(e['probabilidad']) * valor
        ramas.append({'escenario': e['nombre'], 'probabilidad': e['probabilidad'], 'tasa': e['tasa'],
                      'anio_de_construccion': None if limite is None or limite >= horizonte else anio, 'valor': round(valor, 2)})
    decision = 'construir_ahora' if (margen is None or margen <= 0 or ahora <= diferir) else 'diferir'
    return {'obra': nombre, 'decision': decision, 'valor_ahora': round(ahora, 2), 'valor_esperado_diferir': round(diferir, 2),
            'ahorro_esperado': round(ahora - diferir, 2), 'ramas': ramas}


def proceso_de_decision(nombre: str, costo_anual: float, margen: float | None, escenarios: Sequence[Mapping[str, Any]],
                        horizonte: int, descuento: float, *, persistencia: float = PERSISTENCIA,
                        paso: float = PASO_DEMANDA) -> dict[str, Any]:
    """087:RF-15, RF-16: el año de construcción, por inducción hacia atrás.

    Estado: el año, el régimen de crecimiento (una cadena de Markov) y la demanda acumulada, en pasos de ``paso``.
    Los valores están en valor presente del año 0.
    """
    n = len(escenarios)
    otros = (1.0 - persistencia) / (n - 1) if n > 1 else 0.0
    transicion = [[1.0]] if n == 1 else [[persistencia if i == j else otros for j in range(n)] for i in range(n)]
    salto = [round(math.log1p(float(e['tasa'])) / math.log1p(paso)) for e in escenarios]
    tope = -1 if margen is None or margen <= 0 else math.floor(math.log1p(margen) / math.log1p(paso))
    valores: dict[tuple[int, int, int], float] = {}
    construir: dict[tuple[int, int, int], bool] = {}

    def valor(t: int, r: int, nivel: int) -> float:
        if t >= horizonte:
            return 0.0
        clave = (t, r, nivel)
        if clave in valores:
            return valores[clave]
        ya = _valor(costo_anual, t, horizonte, descuento)
        if nivel > tope:
            construir[clave] = True                    # incumplir no es una opción: restricción, no un precio
            valores[clave] = ya
            return ya
        esperar = sum(transicion[r][s] * valor(t + 1, s, nivel + salto[s]) for s in range(n))
        construir[clave] = ya < esperar
        valores[clave] = min(ya, esperar)
        return valores[clave]

    total = sum(float(e['probabilidad']) * valor(0, r, 0) for r, e in enumerate(escenarios))
    distribucion = {(r, 0): float(e['probabilidad']) for r, e in enumerate(escenarios)}
    por_anio = [0.0] * horizonte
    for t in range(horizonte):
        siguiente: dict[tuple[int, int], float] = {}
        for (r, nivel), prob in distribucion.items():
            valor(t, r, nivel)
            if construir[(t, r, nivel)]:
                por_anio[t] += prob
                continue
            for s in range(n):
                clave = (s, nivel + salto[s])
                siguiente[clave] = siguiente.get(clave, 0.0) + prob * transicion[r][s]
        distribucion = siguiente
    construida = sum(por_anio)
    esperado = sum(t * x for t, x in enumerate(por_anio)) / construida if construida > 1e-12 else None
    return {'obra': nombre, 'valor': round(total, 2), 'anio_esperado': None if esperado is None else round(esperado, 2),
            'probabilidad_por_anio': [round(x, 4) for x in por_anio], 'probabilidad_sin_construir': round(1.0 - construida, 4),
            'transicion': transicion, 'escenarios': [dict(e) for e in escenarios], 'persistencia': persistencia}


def plan_por_etapas(obras: Sequence[Mapping[str, Any]], tasa: float, horizonte: int, descuento: float) -> list[dict[str, Any]]:
    """087:RF-14, RF-15: de cada obra (``nombre``, ``costo_anual``, ``margen``), el árbol y el proceso de decisión."""
    escenarios = escenarios_de_demanda(tasa)
    return [{'alimentador': o.get('alimentador'),
             'arbol': arbol_de_decision(o['nombre'], float(o['costo_anual']), o.get('margen'), escenarios, horizonte, descuento),
             'proceso': proceso_de_decision(o['nombre'], float(o['costo_anual']), o.get('margen'), escenarios, horizonte, descuento)}
            for o in obras if o.get('costo_anual') is not None]
