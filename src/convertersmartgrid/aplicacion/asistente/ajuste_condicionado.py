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
#: 047:RF-62: la orden revisada por el maestro (orden del usuario del 2026-11-19). Nunca es humana (RF-67).
CALIDAD_MAESTRO_REVISADA = 'gold_maestro_revisada'
#: 047:RF-64: la base con la que se decide; sin decirla, las humanas, como siempre.
BASE_HUMANAS, BASE_MAESTRO = 'humanas', 'maestro_revisadas'


def _metrica(metricas: Mapping, clave: str) -> float | None:
    valor = metricas.get(clave)
    return float(valor) if type(valor) in (int, float) and math.isfinite(valor) and 0 <= valor <= 1 else None


def manifiesto_de_humanas(humanas: Mapping) -> dict:
    """Lo que el informe de las órdenes humanas acredita de sí mismo, sin suponer lo que no dice."""
    return {'calidades': {'gold_human': humanas.get('ejemplos', 0)}, 'ordenes_reales_distintas': humanas.get('unicos', 0),
            'sin_fuga': humanas.get('sin_fuga'), 'dataset_hash': humanas.get('dataset_hash')}


def manifiesto_de_revisadas(revisadas: Mapping, humanas_distintas: int) -> dict:
    """047:RF-64: lo que acredita la medida del conjunto sellado del maestro, con las humanas que hay aparte."""
    return {'base': BASE_MAESTRO, 'calidades': {CALIDAD_MAESTRO_REVISADA: revisadas.get('ejemplos', 0)},
            'ordenes_maestro_revisadas_distintas': revisadas.get('unicos', 0),
            'ordenes_reales_distintas': humanas_distintas, 'sin_fuga': revisadas.get('sin_fuga'),
            'dataset_hash': revisadas.get('dataset_hash'), 'origen': revisadas.get('origen'),
            'sellado': revisadas.get('sellado')}


def _entero(valor) -> int:
    return valor if type(valor) is int and valor >= 0 else 0


def evaluar_puertas_reales(metricas_reales: Mapping, dataset_manifest: Mapping) -> dict:
    """RF-9: acierto y F1 frente a las puertas, y si las órdenes medidas bastan para decir algo.

    Con la base ``maestro_revisadas`` (RF-64 a RF-66) mide el conjunto sellado del maestro mientras falten humanas; las
    humanas se siguen dando en ``ordenes_reales`` y nunca se suman a las del maestro (RF-67).
    """
    faltas = []
    base = BASE_MAESTRO if dataset_manifest.get('base') == BASE_MAESTRO else BASE_HUMANAS
    admitidas = frozenset({CALIDAD_MAESTRO_REVISADA}) if base == BASE_MAESTRO else CALIDADES_REALES
    que = 'revisadas por el maestro' if base == BASE_MAESTRO else 'reales'
    calidades = dataset_manifest.get('calidades')
    calidades = calidades if isinstance(calidades, Mapping) else {}
    ajenas = sorted(c for c, n in calidades.items() if c not in admitidas and n)
    if ajenas:
        faltas.append(f"el conjunto mezcla órdenes que no son {que}: {', '.join(ajenas)}")
    humanas = _entero(dataset_manifest.get('ordenes_reales_distintas'))
    maestro = _entero(dataset_manifest.get('ordenes_maestro_revisadas_distintas'))
    if base == BASE_MAESTRO:
        distintas = maestro
        if humanas >= MIN_ORDENES_REALES:
            faltas.append(f'hay {humanas} órdenes humanas distintas: deciden las humanas, no el maestro')
        if distintas < MIN_ORDENES_REALES:
            faltas.append(f'{distintas} órdenes revisadas por el maestro distintas de las {MIN_ORDENES_REALES} '
                          'que hacen falta')
        if dataset_manifest.get('origen') != 'maestro':
            faltas.append('el conjunto revisado no es de origen maestro')
        if dataset_manifest.get('sellado') is not True:
            faltas.append('el conjunto revisado por el maestro no consta sellado')
    else:
        distintas = humanas
        if distintas < MIN_ORDENES_REALES:
            faltas.append(f'{distintas} órdenes reales distintas de las {MIN_ORDENES_REALES} que hacen falta')
    reales = sum(n for c, n in calidades.items() if c in admitidas and type(n) is int)
    if metricas_reales.get('ejemplos') != reales:
        faltas.append('las métricas no se midieron sobre las órdenes reales del manifiesto')
    if dataset_manifest.get('sin_fuga') is not True:
        faltas.append(f'no consta que las órdenes {que} estén fuera del entrenamiento')
    if not dataset_manifest.get('dataset_hash'):
        faltas.append(f'conjunto de órdenes {que} sin huella' if base == BASE_MAESTRO else 'conjunto real sin huella')
    acierto, f1 = _metrica(metricas_reales, 'acierto_tarea'), _metrica(metricas_reales, 'f1_datos')
    if acierto is None or f1 is None:
        faltas.append('métricas ausentes o no válidas')
    incumplidas = []
    if acierto is not None and acierto < ACIERTO_REAL:
        incumplidas.append(f'acierto de tarea {acierto:.3f} bajo {ACIERTO_REAL}')
    if f1 is not None and f1 < F1_REAL:
        incumplidas.append(f'F1 de los datos {f1:.3f} bajo {F1_REAL}')
    return {'suficiente': not faltas, 'aprobada': not faltas and not incumplidas, 'faltas': faltas,
            'incumplidas': incumplidas, 'acierto_tarea': acierto, 'f1_datos': f1, 'ordenes_reales': humanas,
            'base': base, 'ordenes_evaluadas': distintas, 'ordenes_maestro_revisadas': maestro,
            'humanas_que_faltan': max(0, MIN_ORDENES_REALES - humanas),
            'dataset_hash': dataset_manifest.get('dataset_hash'),
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
    if puertas['base'] == BASE_MAESTRO:
        # RF-65: se dice con qué se decidió, que no son humanas y cuántas humanas faltan.
        if decision == 'no_necesaria':
            motivos = ['el modelo actual cumple las puertas con el conjunto revisado por el maestro: no se entrena']
        motivos = [*motivos, f"base: {puertas['ordenes_evaluadas']} órdenes revisadas por el maestro (origen "
                   f"maestro, no humanas; conjunto {puertas['dataset_hash']}); hay {puertas['ordenes_reales']} humanas "
                   f"y faltan {puertas['humanas_que_faltan']} para que decidan las humanas"]
    return {'decision': decision, 'motivos': motivos, 'evidencia': puertas, 'base': puertas['base'],
            'entrenado': False, 'promovido': False}
