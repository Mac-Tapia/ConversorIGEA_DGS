#!/usr/bin/env python
"""Evaluación sellada de la recuperación del asistente: BM25, híbrido y rerankers (047:RF-4, RF-27).

Usa la GPU (vectores por Ollama y rerankers en CUDA) bajo su turno exclusivo, salvo con
``--solo-conjunto``, que comprueba sin GPU ni modelos que todas las preguntas anclan en el índice.
Sin red: los rerankers salen de la caché de Hugging Face, con la revisión del catálogo.

Uso: python tools/asistente_evaluar_rag.py --datos <carpeta> --salida docs/EVALUACION_RAG_047.json
     python tools/asistente_evaluar_rag.py --datos <carpeta> --calibrar   (fija los umbrales de abstención)
     python tools/asistente_evaluar_rag.py --datos <carpeta> --sellado    (una sola vez por conjunto)

Corpus ampliado de la spec 077, con sus conjuntos nuevos, en este orden (los dos últimos, con turno de GPU):
     python tools/asistente_evaluar_rag.py --corpus 077 --datos <carpeta> --solo-conjunto
     python tools/asistente_evaluar_rag.py --corpus 077 --datos <carpeta> --calibrar
     python tools/asistente_evaluar_rag.py --corpus 077 --datos <carpeta> --sellado

Modelo de vectores (spec 097), cada candidato en su carpeta de --datos y con su calibración:
     ... --corpus 047 --datos <c> --modelo-vectores bge-m3 --calibrar --salida <cal_047.json>
     ... --elegir <cal_047_m1.json> <cal_077_m1.json> <cal_047_m2.json> ... --salida <eleccion.json>
     ... --corpus 047 --datos <c> --modelo-vectores bge-m3 --sellado --calibracion <cal_047.json> --salida <sel.json>
     ... --corpus 077 --datos <c> --modelo-vectores bge-m3 --operador docs/RAG_PREGUNTAS_OPERADOR_097.json
         --calibracion <cal_077.json> --salida <op.json>     (preguntas reales, aparte de las sintéticas: 097:RF-17)
     ... --poner-en-uso bge-m3 --sellado-047 <sel.json> --calibracion <cal_047.json> [--calibracion-077 ...]
         [--sellado-077 ...] [--aplicar]     (sin --aplicar solo comprueba la puerta: 097:RF-14)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MEMORIA_MINIMA_GIB = 2.0
if str(REPO / 'src') not in sys.path:
    sys.path.insert(0, str(REPO / 'src'))


def _resumen(informe: dict) -> dict:
    claves = ('mrr@10', 'recall@1', 'recall@5', 'recall@10', 'hit@10', 'ndcg@10', 'exact_citation@1',   # hit@10: 097:RF-23
              'abstention_accuracy', 'latencia_p95_ms', 'error')
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


def _memoria_gpu_mib(ollama, modelo: str) -> float | None:
    """Lo que ocupa en la GPU el modelo de vectores, según Ollama (/api/ps): decide entre los no separados (097:RF-11)."""
    for m in (ollama._pedir('/api/ps') or {}).get('models') or ():
        if str(m.get('name', '')).split(':')[0] == modelo.split(':')[0] and m.get('size_vram') is not None:
            return round(float(m['size_vram']) / 2**20, 1)
    return None


def _abstencion(args, evaluacion_rag, indice, reranker, escribir_informe, turno_gpu, ClienteOllama) -> int:
    """Calibra con un conjunto o mide una vez el sellado, siempre con el reranker adoptado (047:RF-34, RF-35).

    Con ``--operador``, mide las preguntas reales del operador con los umbrales calibrados, aparte (097:RF-17)."""
    ampliado = args.corpus == indice.CORPUS_AMPLIADO
    if ampliado:                                                        # 077:RF-43: nada de los conjuntos de la 047
        ruta_conjunto = reranker.CONJUNTO_CALIBRACION_077 if args.calibrar else reranker.CONJUNTO_SELLADO_077
        salida = args.salida or (reranker.CALIBRACION_077 if args.calibrar else reranker.MEDICION_077)
    else:
        ruta_conjunto = reranker.CONJUNTO_CALIBRACION if args.calibrar else REPO / 'docs' / 'RAG_ABSTENCION_SELLADO_047.json'
        salida = args.salida or (reranker.CALIBRACION if args.calibrar else REPO / 'docs' / 'EVALUACION_ABSTENCION_047.json')
    if args.operador:
        conjunto = evaluacion_rag.cargar_conjunto_operador(args.operador)
    else:
        conjunto = evaluacion_rag.cargar_conjunto(ruta_conjunto)
    if args.calibrar:                                                   # 097:RF-19, antes de ocupar la GPU
        try:
            evaluacion_rag.muestra_suficiente(conjunto)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    umbrales = None
    if args.sellado or args.operador:
        if (args.sellado and salida.is_file()
                and json.loads(salida.read_text(encoding='utf-8')).get('conjunto_sha256') == conjunto['sha256']):
            print('El conjunto sellado ya se midió: no se repite (047:RF-35).', file=sys.stderr)
            return 2
        # 097:RF-13: los umbrales de la calibración del mismo modelo de vectores; los de otro no se aceptan.
        if ampliado:
            umbrales = reranker.abstencion(args.calibracion or reranker.CALIBRACION_077, reranker.CONJUNTO_CALIBRACION_077)
        else:                                                          # sin ruta: la del puntero en uso o la de la 047
            umbrales = (reranker.abstencion(args.calibracion, reranker.CONJUNTO_CALIBRACION) if args.calibracion
                        else reranker.abstencion())
        if not umbrales.calibrada:
            print('Falta la calibración de la abstención de este modelo de vectores: no se mide.', file=sys.stderr)
            return 2
    modelo = reranker.MODELOS[1]
    revision = reranker.ficha_modelo(modelo)['revision']
    if not _memoria_suficiente('los vectores'):
        return 3
    with turno_gpu('rag'):
        ollama = ClienteOllama(tiempo_max_s=120.0)
        hecho = indice.calcular_vectores(REPO, ollama, corpus=args.corpus)
        print(json.dumps(hecho), flush=True)
        if hecho['estado'] != 'completo':
            print('Sin todos los vectores no se calibra ni se mide.', file=sys.stderr)
            return 2
        i = indice.cargar_o_construir(REPO, args.corpus)
        # 097:RF-8: en los dos corpus. El de la 047 (2026-11-08) se negaba a calibrar porque src/vnr_etl pasó a adaptadores.
        try:
            conjunto = evaluacion_rag.sin_anclas_perdidas(conjunto, i.frags)      # 077:RF-49
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        memo, latencias = {}, []

        def vector_de(pregunta: str):
            if pregunta not in memo:
                inicio = time.perf_counter()
                emb = indice._vectores_de(ollama, [indice.prefijos()[0] + pregunta])
                latencias.append((time.perf_counter() - inicio) * 1000.0)
                memo[pregunta] = emb[0] if emb else None
            return memo[pregunta]

        for fila in conjunto['preguntas']:
            vector_de(str(fila['pregunta']))
        # 097:RF-11: lo que cuesta la consulta con este modelo en este equipo, para decidir entre los no separados.
        recursos = {'latencia_consulta_p95_ms': evaluacion_rag._p95(latencias[1:] or latencias),   # sin la carga
                    'latencia_consulta_carga_ms': latencias[0] if latencias else None,
                    'memoria_gpu_mib': _memoria_gpu_mib(ollama, indice.modelo_vectores())}
        if not _memoria_suficiente('el reranker'):
            return 3
        puntuar = reranker.PuntuadorPerezoso(modelo, revision)
        if args.calibrar:
            informe = {'esquema': 'csg-calibracion-abstencion-v1', 'procedencia': conjunto['procedencia'],
                       'corpus': args.corpus, 'conjunto_sha256': conjunto['sha256'], 'modelo_reranker': modelo,
                       'revision': revision,
                       **evaluacion_rag.calibracion_con_senales(                          # 097:RF-9
                           evaluacion_rag.leer_puntuaciones(i, conjunto, vector_de, puntuar, modelo)),
                       'recursos': recursos}
            informe['conserva_hibrido'] = evaluacion_rag.conserva_con_intervalo(informe['por_pregunta'])   # 097:RF-10
            puntuar.liberar()
        else:
            informe = {**evaluacion_rag.medir_sellado(i, conjunto, vector_de, puntuar, modelo, umbrales),
                       'recursos': recursos, 'calibracion': str(args.calibracion or '')}
            if args.operador:                                          # 097:RF-17: nunca junto a las sintéticas
                informe['procedencia_medida'] = 'operador'
                informe['por_procedencia'] = evaluacion_rag.por_procedencia({'operador': {
                    m: informe['metodos'][m].get('abstention_accuracy') for m in ('reranker', 'hibrido', 'bm25')}})
    escribir_informe(salida, {**informe, 'modelo_vectores': indice.modelo_vectores()})        # 097:RF-1
    resumen = informe if args.calibrar else {
        'cumple_todos': informe['cumple_todos'], 'puerta': informe['puerta'],
        'metodos': {n: {k: m.get(k) for k in ('mrr@10', 'recall@10', 'hit@10', 'abstention_accuracy', 'abstencion_por_tipo',
                                              'con_respuesta_abstenidas', 'latencia_p95_ms', 'error')}
                    for n, m in informe['metodos'].items()}}
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    return 0


def _comprobar_conjuntos_077(evaluacion_rag, indice) -> int:
    """Solo cuenta: el conjunto sellado no se enseña ni aquí, que es donde alguien miraría qué falta (077:RF-46)."""
    from convertersmartgrid.asistente import reranker

    frags, salida, malo = indice.fragmentos(REPO, indice.CORPUS_AMPLIADO), {}, False
    for nombre, ruta in (('calibracion', reranker.CONJUNTO_CALIBRACION_077), ('sellado', reranker.CONJUNTO_SELLADO_077)):
        conjunto = evaluacion_rag.cargar_conjunto(ruta)
        pares, sin_ancla, _ = evaluacion_rag.resolver_pares(conjunto, frags)
        total = len(conjunto['preguntas'])
        salida[nombre] = {'sha256': conjunto['sha256'], 'preguntas': total, 'con_respuesta': sum(x.answerable for x in pares),
                          'sin_respuesta': sum(not x.answerable for x in pares), 'sin_ancla': len(sin_ancla),
                          'excluidas_sin_fuente_indexada': conjunto['excluidas_sin_fuente_indexada']}
        malo = malo or len(sin_ancla) / max(total, 1) > evaluacion_rag.TOPE_SIN_ANCLA
    print(json.dumps(salida, ensure_ascii=False, indent=1))
    return 2 if malo else 0


def _elegir(args) -> int:
    """097:RF-11: la regla declarada con las señales de cada calibración (047 y 077 de cada modelo)."""
    from convertersmartgrid.asistente import evaluacion_rag

    por_corpus, recursos = {}, {}
    for ruta in args.elegir:
        inf = json.loads(ruta.read_text(encoding='utf-8'))
        modelo, corpus = inf.get('modelo_vectores'), str(inf.get('corpus') or '047')
        if not modelo or 'por_pregunta' not in inf:
            print(f'{ruta}: sin modelo de vectores o sin señales por pregunta (097:RF-9).', file=sys.stderr)
            return 2
        por_corpus.setdefault(corpus, {})[modelo] = inf['por_pregunta']
        r = inf.get('recursos') or {}
        previo = recursos.setdefault(modelo, {'latencia_p95_ms': [], 'memoria_gpu_mib': []})
        previo['latencia_p95_ms'].append(r.get('latencia_consulta_p95_ms'))
        previo['memoria_gpu_mib'].append(r.get('memoria_gpu_mib'))
    # De las dos calibraciones, la peor medida de cada recurso: el modelo tiene que servir en los dos corpus.
    resumen = {m: {k: max((x for x in v if x is not None), default=float('inf')) for k, v in r.items()}
               for m, r in recursos.items()}
    decision = evaluacion_rag.elegir_con_intervalo(por_corpus, resumen, remuestreos=args.remuestreos)
    decision['fuentes'] = [str(r) for r in args.elegir]
    if args.salida:
        from convertersmartgrid.trabajadores_ml import escribir_informe

        escribir_informe(args.salida, decision)
    print(json.dumps({k: decision[k] for k in ('compiten', 'fuera', 'quedan', 'elegido', 'decide', 'recursos')} | {
        'conserva': {c: {m: d['conserva'] for m, d in v['modelos'].items()} for c, v in decision['por_corpus'].items()}},
        ensure_ascii=False, indent=1))
    return 0


def _poner_en_uso(args) -> int:
    """097:RF-14: comprueba la puerta del elegido frente al en uso y, solo con --aplicar, escribe el puntero."""
    from convertersmartgrid.asistente import indice, reranker

    medicion = json.loads(args.sellado_047.read_text(encoding='utf-8'))
    en_uso = json.loads((args.sellado_en_uso or REPO / 'docs' / 'EVALUACION_ABSTENCION_047.json').read_text(encoding='utf-8'))
    calibraciones = {'047': str(args.calibracion)} if args.calibracion else {}
    if args.calibracion_077:
        calibraciones['077'] = str(args.calibracion_077)
    mediciones = {'077': str(args.sellado_077)} if args.sellado_077 else {}
    r = indice.poner_en_uso(args.poner_en_uso, medicion, en_uso, calibraciones=calibraciones, mediciones=mediciones,
                            escribir=args.aplicar)
    import os

    os.environ[indice.VARIABLE_MODELO] = args.poner_en_uso          # la calibración se comprueba con su modelo
    r['abstencion_047_calibrada'] = reranker.abstencion(args.calibracion).calibrada if args.calibracion else False
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0 if not r['motivos'] else 2


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--preguntas', type=Path, default=REPO / 'docs' / 'RAG_PREGUNTAS_SINTETICAS_047.json')
    p.add_argument('--datos', type=Path, help='Carpeta propia del índice (CSG_ASISTENTE_DATA) para no tocar la de la web.')
    p.add_argument('--salida', type=Path, help='Informe JSON; la web lee docs/EVALUACION_RAG_047.json.')
    p.add_argument('--modelos', nargs='*', help='Rerankers a medir; por defecto, los candidatos del plan.')
    p.add_argument('--solo-conjunto', action='store_true', help='Comprueba las anclas sin GPU ni modelos.')
    p.add_argument('--calibrar', action='store_true', help='Fija los umbrales de abstención con su conjunto de calibración.')
    p.add_argument('--sellado', action='store_true', help='Mide la abstención calibrada en el conjunto sellado, una sola vez.')
    p.add_argument('--corpus', choices=('047', '077'), default='047', help='El corpus del índice; cada uno con sus conjuntos.')
    p.add_argument('--modelo-vectores', help='Modelo de Ollama para los vectores (097:RF-4); por defecto, el en uso.')
    p.add_argument('--comparar', nargs='+', type=Path,
                   help='Informes de cada modelo de vectores (sin sellar): dice cuál se elige (097:RF-4).')
    p.add_argument('--calibracion', type=Path, help='Calibración de este modelo de vectores para sellar (097:RF-13).')
    p.add_argument('--calibracion-077', type=Path, help='Con --poner-en-uso: la calibración del 077 del mismo modelo.')
    p.add_argument('--elegir', nargs='+', type=Path, help='Calibraciones 047 y 077 de cada modelo: regla de 097:RF-11.')
    p.add_argument('--remuestreos', type=int, default=2000, help='Remuestreos bootstrap de --elegir (097:RF-10).')
    p.add_argument('--operador', type=Path, help='Conjunto de preguntas reales del operador, medido aparte (097:RF-17).')
    p.add_argument('--poner-en-uso', help='Modelo de vectores a poner en uso tras su sellado (097:RF-14).')
    p.add_argument('--sellado-047', type=Path, help='Con --poner-en-uso: la medición sellada del 047 del modelo.')
    p.add_argument('--sellado-077', type=Path, help='Con --poner-en-uso: la medición sellada del 077 del modelo.')
    p.add_argument('--sellado-en-uso', type=Path, help='Medición sellada del modelo en uso (docs/EVALUACION_ABSTENCION_047.json).')
    p.add_argument('--aplicar', action='store_true', help='Con --poner-en-uso: escribe el puntero si pasa la puerta.')
    args = p.parse_args(argv)
    import os

    if args.elegir:
        return _elegir(args)

    if args.comparar:
        from convertersmartgrid.asistente import indice as _indice

        medidas = {}
        for ruta in args.comparar:
            inf = json.loads(ruta.read_text(encoding='utf-8'))
            metodo = (inf.get('metodos') or {}).get('hibrido') or {}
            medidas[inf.get('modelo_vectores') or ruta.stem] = {k: metodo.get(k) for k in ('mrr@10', 'recall@10')}
        print(json.dumps({'medidas': medidas, 'elegido': _indice.elegir_modelo_vectores(medidas)}, ensure_ascii=False,
                         indent=1))
        return 0
    if args.datos:
        os.environ['CSG_ASISTENTE_DATA'] = str(args.datos)
    if args.modelo_vectores:
        # 097:RF-4: los vectores de otro modelo se miden en la carpeta propia de --datos, sin tocar los que se sirven.
        os.environ['CSG_ASISTENTE_MODELO_VECTORES'] = args.modelo_vectores
    from convertersmartgrid.asistente import evaluacion_rag, indice

    if args.corpus == indice.CORPUS_AMPLIADO and args.solo_conjunto:
        return _comprobar_conjuntos_077(evaluacion_rag, indice)
    if args.corpus == indice.CORPUS_AMPLIADO and not (args.calibrar or args.sellado or args.operador or args.poner_en_uso):
        p.error('con --corpus 077 se usa --solo-conjunto, --calibrar, --sellado u --operador')
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

    if args.poner_en_uso:
        if not args.sellado_047:
            p.error('--poner-en-uso pide --sellado-047')
        return _poner_en_uso(args)
    if args.calibrar or args.sellado or args.operador:
        return _abstencion(args, evaluacion_rag, indice, reranker, escribir_informe, turno_gpu, ClienteOllama)
    if not args.salida:
        p.error('--salida es obligatoria al medir')
    with turno_gpu('rag'):
        ollama = ClienteOllama(tiempo_max_s=120.0)
        if not any(str(m).startswith(indice.modelo_vectores().split(':')[0]) for m in ollama.modelos() or ()):
            print('Ollama no responde con su modelo de embeddings: no se puede medir el híbrido.', file=sys.stderr)
            return 2
        hecho = indice.calcular_vectores(REPO, ollama, progreso=lambda n, t: print(f'vectores {n}/{t}', flush=True))
        print(json.dumps(hecho), flush=True)
        if hecho['estado'] != 'completo':
            print('Sin todos los vectores, la comparación no sería de los tres métodos.', file=sys.stderr)
            return 2
        i = indice.cargar_o_construir(REPO)
        try:                                                           # 097:RF-8 también sin abstención
            conjunto = evaluacion_rag.sin_anclas_perdidas(conjunto, i.frags)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

        def vector_de(pregunta: str) -> list[float] | None:
            emb = indice._vectores_de(ollama, [indice.prefijos()[0] + pregunta])
            return emb[0] if emb else None

        modelos = args.modelos if args.modelos is not None else list(reranker.MODELOS)
        revisiones = {m: reranker.ficha_modelo(m)['revision'] for m in modelos}
        informe = evaluacion_rag.evaluar(i, conjunto, vector_de,
                                         {m: reranker.PuntuadorPerezoso(m, revisiones[m]) for m in modelos}, revisiones)
    escribir_informe(args.salida, {**informe, 'modelo_vectores': indice.modelo_vectores(),   # 097:RF-1
                                   'perdidas_al_medir': conjunto.get('perdidas_al_medir', 0)})
    print(json.dumps(_resumen(informe), ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
