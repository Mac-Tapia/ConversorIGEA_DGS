#!/usr/bin/env python
"""El corpus ampliado del asistente sin GPU: su tamaño, su recuperación BM25 y sus conjuntos nuevos (spec 077).

Subórdenes:
  medir         Trozos, caracteres, vectores previstos, memoria y tiempo de los dos corpus (077:RF-14).
  recuperacion  BM25 de los dos corpus con el reparto `corpus` de la 076; nunca abre el reparto `sellado` (077:RF-50).
  conjuntos     Forma docs/CONJUNTO_ABSTENCION_{CALIBRACION,SELLADO}_077.json. Solo cuenta filas y no enseña ninguna (077:RF-44).

Cada una se ejecuta sobre una carpeta de datos propia, para no tocar la de la web.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / 'src') not in sys.path:
    sys.path.insert(0, str(REPO / 'src'))
ENTREGABLES = REPO / 'docs' / 'asistente' / 'preguntas_entregables.jsonl'
FUERA = REPO / 'docs' / 'CONJUNTO_FUERA_077.json'


def _filas() -> list[dict]:
    with ENTREGABLES.open(encoding='utf-8') as f:
        return [json.loads(linea) for linea in f if linea.strip()]


def _medir(indice, corpus_proyecto) -> dict:
    salida = {}
    consultas = ('como se reinicia la web', 'que hace el escaneo del alimentador', 'calibracion por proyecto y alimentador')
    for corpus in (indice.CORPUS_047, indice.CORPUS_AMPLIADO):
        def hacer(c=corpus):
            return indice.Indice(indice.fragmentos(REPO, c), corpus=c)

        fila = corpus_proyecto.medir_tamano(hacer, lambda i: [f.texto for f in i.frags])
        i = hacer()
        latencias = []
        for consulta in consultas:
            inicio = time.perf_counter()
            i.bm25(consulta)
            latencias.append((time.perf_counter() - inicio) * 1000)
        fila['bm25_ms_mediana'] = round(statistics.median(latencias), 1)
        fila['ficheros'] = len(indice._ficheros_de(REPO, corpus))
        fila['historicos'] = sum(f.vigencia == 'historico' for f in i.frags)
        salida[corpus] = fila
    return salida


def _metricas(posiciones: dict) -> dict:
    total = max(len(posiciones), 1)
    return {'preguntas': len(posiciones), 'recall@10': round(sum(p is not None for p in posiciones.values()) / total, 3),
            'mrr@10': round(sum(1 / p for p in posiciones.values() if p) / total, 3)}


def _recuperacion(indice, evaluacion_rag) -> dict:
    """Con la abstención desactivada: mide si el trozo está entre los hallados, no si se atreve a responder."""
    corpus_076 = [f for f in _filas() if f['reparto'] == 'corpus']
    salida, por_corpus = {}, {}
    for corpus in (indice.CORPUS_047, indice.CORPUS_AMPLIADO):
        i = indice.Indice(indice.fragmentos(REPO, corpus), corpus=corpus)
        conjunto = evaluacion_rag.conjunto_de_entregables(corpus_076, 'corpus', i.frags, ())
        pares, sin_ancla, _ = evaluacion_rag.resolver_pares(conjunto, i.frags)
        posiciones = {}
        for par in (p for p in pares if p.answerable):
            fuentes = [h['fuente'] for h in i.buscar(par.pregunta, 10)]
            posiciones[par.pregunta] = next((n for n, f in enumerate(fuentes, 1) if f in set(par.positive_ids)), None)
        por_corpus[corpus] = posiciones
        salida[corpus] = {'excluidas_sin_fuente_indexada': conjunto['excluidas_sin_fuente_indexada'],
                          'sin_ancla': len(sin_ancla), **_metricas(posiciones)}
    # Las mismas preguntas en los dos: con conjuntos distintos, las cifras de arriba no se comparan entre sí.
    comunes = set(por_corpus[indice.CORPUS_047]) & set(por_corpus[indice.CORPUS_AMPLIADO])
    salida['mismas_preguntas'] = {c: _metricas({q: por_corpus[c][q] for q in comunes}) for c in por_corpus}
    return salida


def _conjuntos(indice, evaluacion_rag, reranker) -> dict:
    frags = indice.fragmentos(REPO, indice.CORPUS_AMPLIADO)
    filas, fuera = _filas(), json.loads(FUERA.read_text(encoding='utf-8'))
    salida = {}
    for reparto, ruta, clave in (('corpus', reranker.CONJUNTO_CALIBRACION_077, 'calibracion'),
                                 ('sellado', reranker.CONJUNTO_SELLADO_077, 'sellado')):
        if ruta.is_file():
            salida[clave] = {'estado': 'ya existe: un conjunto sellado no se vuelve a formar', 'sha256': reranker.sha256_de(ruta)}
            continue
        conjunto = evaluacion_rag.conjunto_de_entregables(filas, reparto, frags, fuera[clave])
        ruta.write_text(json.dumps(conjunto, ensure_ascii=False, indent=0, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
        salida[clave] = {'preguntas': len(conjunto['preguntas']), 'excluidas_sin_fuente_indexada': conjunto['excluidas_sin_fuente_indexada'],
                         'sha256': reranker.sha256_de(ruta)}
    return salida


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('orden', choices=('medir', 'recuperacion', 'conjuntos'))
    args = p.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix='csg-indice-077-') as datos:
        os.environ['CSG_ASISTENTE_DATA'] = datos
        from convertersmartgrid.asistente import (
            corpus_proyecto,
            evaluacion_rag,
            indice,
            reranker,
        )

        if args.orden == 'medir':
            salida = _medir(indice, corpus_proyecto)
        elif args.orden == 'recuperacion':
            salida = _recuperacion(indice, evaluacion_rag)
        else:
            salida = _conjuntos(indice, evaluacion_rag, reranker)
    print(json.dumps(salida, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
