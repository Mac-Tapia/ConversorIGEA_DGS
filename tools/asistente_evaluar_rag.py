#!/usr/bin/env python
"""Evaluación sellada de la recuperación del asistente: BM25, híbrido y rerankers (047:RF-4, RF-27).

Usa la GPU (vectores por Ollama y rerankers en CUDA) bajo su turno exclusivo, salvo con
``--solo-conjunto``, que comprueba sin GPU ni modelos que todas las preguntas anclan en el índice.
Sin red: los rerankers salen de la caché de Hugging Face, con la revisión del catálogo.

Uso: python tools/asistente_evaluar_rag.py --datos <carpeta> --salida docs/EVALUACION_RAG_047.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / 'src') not in sys.path:
    sys.path.insert(0, str(REPO / 'src'))


def _resumen(informe: dict) -> dict:
    claves = ('mrr@10', 'recall@1', 'recall@5', 'recall@10', 'ndcg@10', 'exact_citation@1', 'abstention_accuracy',
              'latencia_p95_ms', 'error')
    return {'conjunto_sha256': informe['conjunto_sha256'], 'cobertura_vectores': informe['cobertura_vectores'],
            'metodos': {n: {c: m[c] for c in claves if c in m} for n, m in informe['metodos'].items()},
            'decision': informe['decision']}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--preguntas', type=Path, default=REPO / 'docs' / 'RAG_PREGUNTAS_SINTETICAS_047.json')
    p.add_argument('--datos', type=Path, help='Carpeta propia del índice (CSG_ASISTENTE_DATA) para no tocar la de la web.')
    p.add_argument('--salida', type=Path, help='Informe JSON; la web lee docs/EVALUACION_RAG_047.json.')
    p.add_argument('--modelos', nargs='*', help='Rerankers a medir; por defecto, los candidatos del plan.')
    p.add_argument('--solo-conjunto', action='store_true', help='Comprueba las anclas sin GPU ni modelos.')
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
    if not args.salida:
        p.error('--salida es obligatoria al medir')
    from convertersmartgrid.asistente import reranker
    from convertersmartgrid.asistente.ollama import ClienteOllama
    from convertersmartgrid.trabajadores_ml import escribir_informe, turno_gpu

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
