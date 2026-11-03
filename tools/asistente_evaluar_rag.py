#!/usr/bin/env python
"""Evaluación sellada de la recuperación del asistente: BM25, híbrido y rerankers (047:RF-4, RF-27).

Usa la GPU (vectores por Ollama y rerankers en CUDA) bajo su turno exclusivo, salvo con
``--solo-conjunto``, que comprueba sin GPU ni modelos que todas las preguntas anclan en el índice.
Sin red: los rerankers salen de la caché de Hugging Face, con la revisión del catálogo.

Uso: python tools/asistente_evaluar_rag.py --datos <carpeta> --salida docs/EVALUACION_RAG_047.json
     python tools/asistente_evaluar_rag.py --datos <carpeta> --calibrar   (fija los umbrales de abstención)
     python tools/asistente_evaluar_rag.py --datos <carpeta> --sellado    (una sola vez por conjunto)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MEMORIA_MINIMA_GIB = 2.0
if str(REPO / 'src') not in sys.path:
    sys.path.insert(0, str(REPO / 'src'))


def _resumen(informe: dict) -> dict:
    claves = ('mrr@10', 'recall@1', 'recall@5', 'recall@10', 'ndcg@10', 'exact_citation@1', 'abstention_accuracy',
              'latencia_p95_ms', 'error')
    return {'conjunto_sha256': informe['conjunto_sha256'], 'cobertura_vectores': informe['cobertura_vectores'],
            'metodos': {n: {c: m[c] for c in claves if c in m} for n, m in informe['metodos'].items()},
            'decision': informe['decision']}


def _memoria_suficiente(paso: str) -> bool:
    """Antes de cada paso de GPU: la Fase 2 bajó a 0,43 GiB disponibles al cargar el reranker."""
    import psutil

    disponible = psutil.virtual_memory().available / 2**30
    print(f'memoria antes de {paso}: {disponible:.2f} GiB disponibles', flush=True)
    if disponible < MEMORIA_MINIMA_GIB:
        print(f'Hacen falta {MEMORIA_MINIMA_GIB} GiB para {paso}: espere y repita.', file=sys.stderr)
    return disponible >= MEMORIA_MINIMA_GIB


def _abstencion(args, evaluacion_rag, indice, reranker, escribir_informe, turno_gpu, ClienteOllama) -> int:
    """Calibra con un conjunto o mide una vez el sellado, siempre con el reranker adoptado (047:RF-34, RF-35)."""
    ruta_conjunto = reranker.CONJUNTO_CALIBRACION if args.calibrar else REPO / 'docs' / 'RAG_ABSTENCION_SELLADO_047.json'
    salida = args.salida or (reranker.CALIBRACION if args.calibrar else REPO / 'docs' / 'EVALUACION_ABSTENCION_047.json')
    conjunto = evaluacion_rag.cargar_conjunto(ruta_conjunto)
    if args.sellado:
        if salida.is_file() and json.loads(salida.read_text(encoding='utf-8')).get('conjunto_sha256') == conjunto['sha256']:
            print('El conjunto sellado ya se midió: no se repite (047:RF-35).', file=sys.stderr)
            return 2
        if not reranker.abstencion().calibrada:
            print('Falta la calibración de la abstención: no se abre el conjunto sellado.', file=sys.stderr)
            return 2
    modelo = reranker.MODELOS[1]
    revision = reranker.ficha_modelo(modelo)['revision']
    if not _memoria_suficiente('los vectores'):
        return 3
    with turno_gpu('rag'):
        ollama = ClienteOllama(tiempo_max_s=120.0)
        hecho = indice.calcular_vectores(REPO, ollama)
        print(json.dumps(hecho), flush=True)
        if hecho['estado'] != 'completo':
            print('Sin todos los vectores no se calibra ni se mide.', file=sys.stderr)
            return 2
        i = indice.cargar_o_construir(REPO)
        memo = {}

        def vector_de(pregunta: str):
            if pregunta not in memo:
                emb = ollama.embeddings([indice.PREFIJO_CONSULTA + pregunta])
                memo[pregunta] = emb[0] if emb else None
            return memo[pregunta]

        for fila in conjunto['preguntas']:
            vector_de(str(fila['pregunta']))
        if not _memoria_suficiente('el reranker'):
            return 3
        puntuar = reranker.PuntuadorPerezoso(modelo, revision)
        if args.calibrar:
            informe = {'esquema': 'csg-calibracion-abstencion-v1', 'procedencia': conjunto['procedencia'],
                       'conjunto_sha256': conjunto['sha256'], 'modelo_reranker': modelo, 'revision': revision,
                       **evaluacion_rag.calibrar(evaluacion_rag.leer_puntuaciones(i, conjunto, vector_de, puntuar, modelo))}
            puntuar.liberar()
        else:
            informe = evaluacion_rag.medir_sellado(i, conjunto, vector_de, puntuar, modelo, reranker.abstencion())
    escribir_informe(salida, informe)
    resumen = informe if args.calibrar else {
        'cumple_todos': informe['cumple_todos'], 'puerta': informe['puerta'],
        'metodos': {n: {k: m.get(k) for k in ('mrr@10', 'recall@10', 'abstention_accuracy', 'abstencion_por_tipo',
                                              'con_respuesta_abstenidas', 'latencia_p95_ms', 'error')}
                    for n, m in informe['metodos'].items()}}
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--preguntas', type=Path, default=REPO / 'docs' / 'RAG_PREGUNTAS_SINTETICAS_047.json')
    p.add_argument('--datos', type=Path, help='Carpeta propia del índice (CSG_ASISTENTE_DATA) para no tocar la de la web.')
    p.add_argument('--salida', type=Path, help='Informe JSON; la web lee docs/EVALUACION_RAG_047.json.')
    p.add_argument('--modelos', nargs='*', help='Rerankers a medir; por defecto, los candidatos del plan.')
    p.add_argument('--solo-conjunto', action='store_true', help='Comprueba las anclas sin GPU ni modelos.')
    p.add_argument('--calibrar', action='store_true', help='Fija los umbrales de abstención con su conjunto de calibración.')
    p.add_argument('--sellado', action='store_true', help='Mide la abstención calibrada en el conjunto sellado, una sola vez.')
    args = p.parse_args(argv)
    import os

    if args.datos:
        os.environ['CSG_ASISTENTE_DATA'] = str(args.datos)
    from convertersmartgrid.asistente import evaluacion_rag, indice

    conjunto = evaluacion_rag.cargar_conjunto(args.preguntas)
    if args.solo_conjunto:
        pares, sin_ancla, codigos = evaluacion_rag.resolver_pares(conjunto, indice.fragmentos(REPO))
        print(json.dumps({'sha256': conjunto['sha256'], 'procedencia': conjunto['procedencia'],
                          'preguntas': len(pares), 'con_respuesta': sum(x.answerable for x in pares),
                          'de_codigo': len(codigos), 'sin_ancla': sin_ancla}, ensure_ascii=False, indent=1))
        return 0 if not sin_ancla else 2
    from convertersmartgrid.asistente import reranker
    from convertersmartgrid.asistente.ollama import ClienteOllama
    from convertersmartgrid.trabajadores_ml import escribir_informe, turno_gpu

    if args.calibrar or args.sellado:
        return _abstencion(args, evaluacion_rag, indice, reranker, escribir_informe, turno_gpu, ClienteOllama)
    if not args.salida:
        p.error('--salida es obligatoria al medir')
    with turno_gpu('rag'):
        ollama = ClienteOllama(tiempo_max_s=120.0)
        if not any(str(m).startswith(indice.MODELO_EMBEDDINGS) for m in ollama.modelos() or ()):
            print('Ollama no responde con su modelo de embeddings: no se puede medir el híbrido.', file=sys.stderr)
            return 2
        hecho = indice.calcular_vectores(REPO, ollama, progreso=lambda n, t: print(f'vectores {n}/{t}', flush=True))
        print(json.dumps(hecho), flush=True)
        if hecho['estado'] != 'completo':
            print('Sin todos los vectores, la comparación no sería de los tres métodos.', file=sys.stderr)
            return 2
        i = indice.cargar_o_construir(REPO)

        def vector_de(pregunta: str) -> list[float] | None:
            emb = ollama.embeddings([indice.PREFIJO_CONSULTA + pregunta])
            return emb[0] if emb else None

        modelos = args.modelos if args.modelos is not None else list(reranker.MODELOS)
        revisiones = {m: reranker.ficha_modelo(m)['revision'] for m in modelos}
        informe = evaluacion_rag.evaluar(i, conjunto, vector_de,
                                         {m: reranker.PuntuadorPerezoso(m, revisiones[m]) for m in modelos}, revisiones)
    escribir_informe(args.salida, informe)
    print(json.dumps(_resumen(informe), ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
