"""047:RF-8 y RF-9 — las puertas de 027:RF-18 sobre órdenes reales, y si eso justifica ajustar el LLM.

La evaluación de las 200 propuestas del maestro dio 188 aciertos sobre 200, y ese déficit es de propuestas: no dice
nada de las órdenes reales, de las que solo hay unas pocas. Aquí se separan las dos cosas: sin órdenes reales suficientes
e independientes, la decisión es ``bloqueada`` (falta evidencia), nunca ``necesaria`` ni ``no_necesaria``.

Decide y no ejecuta: la decisión no es un estado terminal del registro de modelos ni activa ni entrena nada.
"""
from __future__ import annotations

from collections.abc import Mapping
import math

#: Las puertas de 027:RF-18 y el mínimo de 027:RF-19 viven aquí, sin dependencias, y de aquí las toman el Transformer y la
#: auditoría del gemelo: estaban escritas en tres sitios y este módulo no podía importar ninguno sin crear un ciclo.
ACIERTO_REAL = 0.98
F1_REAL = 0.95
MIN_ORDENES_REALES = 200
#: Lo único que cuenta como orden real: la que escribió y confirmó el operador (027:RF-34).
CALIDADES_REALES = frozenset({'gold_human'})


def _metrica(metricas: Mapping, clave: str) -> float | None:
    valor = metricas.get(clave)
    return float(valor) if type(valor) in (int, float) and math.isfinite(valor) and 0 <= valor <= 1 else None


def manifiesto_de_humanas(humanas: Mapping) -> dict:
    """Lo que el informe de las órdenes humanas acredita de sí mismo, sin suponer lo que no dice."""
    return {'calidades': {'gold_human': humanas.get('ejemplos', 0)}, 'ordenes_reales_distintas': humanas.get('unicos', 0),
            'sin_fuga': humanas.get('sin_fuga'), 'dataset_hash': humanas.get('dataset_hash')}


def evaluar_puertas_reales(metricas_reales: Mapping, dataset_manifest: Mapping) -> dict:
    """RF-9: acierto y F1 frente a las puertas, y si las órdenes medidas bastan para decir algo."""
    faltas = []
    calidades = dataset_manifest.get('calidades')
    calidades = calidades if isinstance(calidades, Mapping) else {}
    ajenas = sorted(c for c, n in calidades.items() if c not in CALIDADES_REALES and n)
    if ajenas:
        faltas.append(f"el conjunto mezcla órdenes que no son reales: {', '.join(ajenas)}")
    distintas = dataset_manifest.get('ordenes_reales_distintas')
    distintas = distintas if type(distintas) is int and distintas >= 0 else 0
    if distintas < MIN_ORDENES_REALES:
        faltas.append(f'{distintas} órdenes reales distintas de las {MIN_ORDENES_REALES} que hacen falta')
    reales = sum(n for c, n in calidades.items() if c in CALIDADES_REALES and type(n) is int)
    if metricas_reales.get('ejemplos') != reales:
        faltas.append('las métricas no se midieron sobre las órdenes reales del manifiesto')
    if dataset_manifest.get('sin_fuga') is not True:
        faltas.append('no consta que las órdenes reales estén fuera del entrenamiento')
    if not dataset_manifest.get('dataset_hash'):
        faltas.append('conjunto real sin huella')
    acierto, f1 = _metrica(metricas_reales, 'acierto_tarea'), _metrica(metricas_reales, 'f1_datos')
    if acierto is None or f1 is None:
        faltas.append('métricas ausentes o no válidas')
    incumplidas = []
    if acierto is not None and acierto < ACIERTO_REAL:
        incumplidas.append(f'acierto de tarea {acierto:.3f} bajo {ACIERTO_REAL}')
    if f1 is not None and f1 < F1_REAL:
        incumplidas.append(f'F1 de los datos {f1:.3f} bajo {F1_REAL}')
    return {'suficiente': not faltas, 'aprobada': not faltas and not incumplidas, 'faltas': faltas,
            'incumplidas': incumplidas, 'acierto_tarea': acierto, 'f1_datos': f1, 'ordenes_reales': distintas,
            'minimo': MIN_ORDENES_REALES, 'puertas': {'acierto_tarea': ACIERTO_REAL, 'f1_datos': F1_REAL}}


def decidir_ajuste(metricas_reales: Mapping, dataset_manifest: Mapping) -> dict:
    """RF-8: ``necesaria`` solo con el incumplimiento medido sobre un conjunto real suficiente."""
    puertas = evaluar_puertas_reales(metricas_reales, dataset_manifest)
    if not puertas['suficiente']:
        decision, motivos = 'bloqueada', puertas['faltas']
    elif puertas['incumplidas']:
        decision, motivos = 'necesaria', puertas['incumplidas']
    else:
        decision, motivos = 'no_necesaria', ['el modelo actual cumple las puertas con el conjunto real: no se entrena']
    return {'decision': decision, 'motivos': motivos, 'evidencia': puertas, 'entrenado': False, 'promovido': False}
