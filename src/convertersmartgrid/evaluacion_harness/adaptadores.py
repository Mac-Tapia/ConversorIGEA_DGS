"""Adaptadores aditivos: los evaluadores del dominio mantienen sus políticas."""
from __future__ import annotations

import math
from copy import deepcopy

from .contratos import canonico, huella
from .metricas import clasificacion, entidades


def desde_ordenes(informe: dict) -> dict:
    if not isinstance(informe, dict):
        raise TypeError('informe de órdenes debe ser objeto JSON')
    casos = informe.get('casos')
    if not isinstance(casos, list) or not casos or informe.get('ejemplos') != len(casos):
        raise ValueError('informe de órdenes incompleto')
    ids = [c.get('record_id') for c in casos]
    if any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids):
        raise ValueError('casos de órdenes sin identidad única')
    for c in casos:
        if type(c.get('correcto')) is not bool or c['correcto'] != (c['esperado'] == c['obtenido']):
            raise ValueError('acierto contradictorio')
    ent = entidades(casos)
    clases = sorted({c['esperado'] for c in casos} | {c['obtenido'] for c in casos if c['obtenido'] is not None})
    tareas = clasificacion(casos, clases)
    f1_historico = ent['f1'] if ent['f1'] is not None else 1.
    for nombre, esperado in (('f1_datos', f1_historico), ('acierto_tarea', tareas['acierto'])):
        valor = informe.get(nombre)
        if type(valor) not in (int, float) or not math.isfinite(valor) or not math.isclose(valor, esperado):
            raise ValueError('resumen contradictorio: '+nombre)
    return {'entidades': ent, 'clasificacion': tareas, 'casos': deepcopy(casos),
            'historico': {'f1_datos': informe['f1_datos'], 'acierto_tarea': informe['acierto_tarea']},
            'source_hash': huella(informe), 'modo': 'replay', 'promocion_permitida': False}


def evaluar_electrico(metricas: dict, *, politica) -> dict:
    from ..evaluacion_modelos import evaluar_candidato
    r = evaluar_candidato(metricas, politica)
    return {'metricas': r, 'aprobado': r['approved'], 'politica_hash': r['politica_hash'],
            'aceptacion_nativa': False, 'clase_evidencia': 'evaluacion_metricas',
            'motivo': 'el contraste de métricas no ejecuta ni reabre PowerFactory'}


def importar_upstream(payload: dict, *, herramienta: str, commit: str, lock: dict) -> dict:
    """Importa resultados auxiliares; no confunde el formato externo con un caso gold.

    Ragas recibe la exportación explícita ``{"scores": EvaluationResult.scores}``.
    Promptfoo admite EvaluateSummaryV3 o el wrapper CLI con ese objeto en results.
    EleutherAI admite el mapa ``results`` por tarea; no traduce accuracy a recall.
    """
    if not isinstance(payload, dict) or not isinstance(lock, dict):
        raise TypeError('salida upstream y lock deben ser objetos JSON')
    canonico(payload)
    repos = [r for r in lock.get('repositories', []) if r.get('id') == herramienta]
    if len(repos) != 1 or commit != repos[0].get('commit'):
        raise ValueError('herramienta/commit no coincide con la revisión fijada')
    if herramienta == 'promptfoo':
        resumen = payload.get('results') if isinstance(payload.get('results'), dict) else payload
        filas = resumen.get('results')
        if (resumen.get('version') != 3 or not isinstance(filas, list) or not filas
                or any(not isinstance(f, dict) or type(f.get('success')) is not bool for f in filas)):
            raise ValueError('se requiere EvaluateSummaryV3 completo con success booleano')
        medido = {'casos': len(filas), 'correctos': sum(f['success'] for f in filas)}
    elif herramienta == 'lm_evaluation_harness':
        tareas = payload.get('results')
        if (not isinstance(tareas, dict) or not tareas
                or any(not isinstance(m, dict) or not m for m in tareas.values())):
            raise ValueError('se requiere results por tarea de lm-evaluation-harness')
        medido = {'tareas': len(tareas), 'metricas_originales': deepcopy(tareas)}
    elif herramienta == 'ragas':
        filas = payload.get('scores')
        if not isinstance(filas, list) or not filas or any(not isinstance(f, dict) or not f for f in filas):
            raise ValueError('se requiere exportación explícita de EvaluationResult.scores')
        medido = {'casos': len(filas), 'scores': deepcopy(filas)}
    else:
        raise ValueError('herramienta sin adaptador explícito')
    return {'schema_version': 1, 'herramienta': herramienta, 'commit': commit,
            'original': deepcopy(payload), 'original_hash': huella(payload), 'resumen': medido,
            'alcance': 'auxiliar_importado', 'modo': 'replay', 'verdad_experta': False,
            'promocion_permitida': False, 'aceptacion_electrica': False}
