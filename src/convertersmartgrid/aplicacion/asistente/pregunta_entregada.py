"""«Pregunta» en el programa instalado: BM25 sobre los manuales y notas que se entregan, con su abstención calibrada.

Decisión del usuario (2026-11-13): en el instalado, «pregunta» responde con la abstención calibrada sobre el corpus que
se entrega, calibrada al construir el candidato, con un conjunto sin fuga (097:RF-19) y su mínimo de muestra. Hasta
entonces el paquete no traía ni la calibración ni los documentos que la 047 indexa (specs, CODIGO_FUENTE), y la web servía
una abstención sin calibrar: «No lo sé» a todo.

Sin modelo de vectores ni reranker en el complemento, el instalado decide solo por BM25 (``umbral_bm25_solo``). La
muestra mínima y la comprobación de que ninguna pregunta está en el corpus son las de la tarjeta de la fuga del 077
(``evaluacion_rag.muestra_suficiente``, ``fuga_evaluacion.fugas``): se reutilizan, no se repiten aquí.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from ...dominio.util import write_json_atomic
from . import evaluacion_rag, indice

CORPUS = 'entrega'
#: Dentro de ``_programa``: los manuales y las notas que también van a «documentos» del candidato.
CARPETA = 'documentos'
CONJUNTO = 'CONJUNTO_ABSTENCION_ENTREGA.json'
CALIBRACION = 'CALIBRACION_ABSTENCION_ENTREGA.json'
#: El error que se admite al abstenerse (la 047 calibró a 0,95).
ALFA = 0.05


def objetivo(sin_respuesta: int, alfa: float = ALFA) -> float:
    """La abstención exigida con n preguntas sin respuesta: ⌈(n+1)(1−α)⌉/n (097:RF-19; Angelopoulos y Bates,
    arXiv 2107.07511, corrección de muestra finita). Con n=110 y α=0,05 es 105/110."""
    return min(1.0, math.ceil((sin_respuesta + 1) * (1 - alfa)) / sin_respuesta)


def calibrar(raiz: Path) -> dict[str, Any]:
    """Calcula y escribe la calibración del corpus entregado en ``raiz/documentos``; un error si no se puede.

    ``raiz`` es la carpeta ``_programa`` del paquete que se está armando (o una con su misma forma).
    """
    from . import fuga_evaluacion

    carpeta = raiz / CARPETA
    conjunto = evaluacion_rag.cargar_conjunto(carpeta / CONJUNTO)
    muestra = evaluacion_rag.muestra_suficiente(conjunto)                        # 097:RF-19
    frags = indice.fragmentos(raiz, CORPUS)
    if not frags:
        raise ValueError(f'No hay manuales ni notas en {carpeta}: no hay corpus que calibrar.')
    candidatas = [fuga_evaluacion.Pregunta(CORPUS, str(f['pregunta'])) for f in conjunto['preguntas']]
    fugas = fuga_evaluacion.fugas(fuga_evaluacion.textos_por_fichero(frags), candidatas, min_palabras=1)['fugas']
    if fugas:
        raise ValueError(f'{len(fugas)} preguntas de la calibración están literales en el corpus entregado: '
                         + '; '.join(sorted({h["pregunta"] for h in fugas})[:5]))
    pares, sin_ancla, _ = evaluacion_rag.resolver_pares(conjunto, frags)
    if sin_ancla:
        raise ValueError(f'{len(sin_ancla)} preguntas perdieron su ancla en los manuales: ' + '; '.join(sin_ancla[:5]))
    buscador = indice.Indice(frags, corpus=CORPUS)
    filas = []
    for par in pares:
        hallados = buscador.buscar(par.pregunta, indice.CANDIDATOS, None)
        filas.append({'responde': par.answerable, 'codigo': False,
                      'bm25': max((h['bm25'] for h in hallados), default=float('-inf')),
                      'coseno': float('-inf'), 'reranker': float('-inf')})
    meta = objetivo(muestra['sin_respuesta'])
    medido = evaluacion_rag.calibrar(filas, objetivo=meta)
    umbral = medido['umbrales'].get('bm25_solo')
    if umbral is None:
        raise ValueError(f'Ningún umbral de BM25 llega a una abstención de {meta:.3f} con este conjunto.')
    datos = {'esquema': 'csg-calibracion-abstencion-entrega-v1', 'corpus': CORPUS, 'conjunto_sha256': conjunto['sha256'],
             'umbrales': {'bm25_solo': umbral}, 'modelo_reranker': None, 'revision': None, 'alfa': ALFA,
             'objetivo': meta, 'muestra': muestra, 'en_calibracion': medido['en_calibracion'].get('bm25_solo'),
             'ficheros': sorted({str(f.fuente).rsplit(':', 1)[0] for f in frags}), 'trozos': len(frags)}
    write_json_atomic(carpeta / CALIBRACION, datos)  # 001:RF-5: la escritura atómica única
    return datos
