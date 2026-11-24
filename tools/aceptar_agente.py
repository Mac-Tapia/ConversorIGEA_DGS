#!/usr/bin/env python
"""Audita las 200 propuestas y evalúa el agente local por alcance (spec 047 T6).

    python tools/aceptar_agente.py preparar --destino output/aceptacion --dataset output/corpus
    python tools/aceptar_agente.py seleccionar --dataset output/corpus --destino output/seleccion
    python tools/aceptar_agente.py evaluar --corpus output/aceptacion --destino output/evaluacion --modelo llama3.1:8b --dataset output/corpus --seleccion output/seleccion/resultado.json

No ejecuta acciones nativas, no cambia pesos y conserva los informes anteriores.

Con `preparar --revisadas-maestro <almacén>/maestro_real/revisadas_047` (047:RF-64, RF-68) se copia el conjunto sellado
de órdenes revisadas por el maestro; `evaluar` lo mide aparte de las humanas, comprueba su sello y su fuga, y deja
`decision_ajuste.json` para `asistente_qlora.py --decision` y `reentrenar_modelos.py run --qlora-decision`.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / 'src') not in sys.path:
    sys.path.insert(0, str(RAIZ / 'src'))


def escribir(ruta, datos):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    contenido = json.dumps(datos, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    if ruta.exists() and ruta.read_text(encoding='utf-8') != contenido:
        raise ValueError('informe existente conservado; use otro destino')
    ruta.write_text(contenido, encoding='utf-8')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='accion', required=True)
    a = sub.add_parser('preparar'); a.add_argument('--dataset', type=Path, required=True); a.add_argument('--destino', type=Path, required=True)
    a.add_argument('--publicar', action='store_true')
    a.add_argument('--revisadas-maestro', type=Path, help='Conjunto sellado de órdenes revisadas por el maestro (047:RF-64)')
    a = sub.add_parser('seleccionar'); a.add_argument('--dataset', type=Path, required=True); a.add_argument('--destino', type=Path, required=True)
    a.add_argument('--modelos', default='qwen2.5:3b,llama3.1:8b')
    a.add_argument('--dos-etapas', action='store_true')
    a.add_argument('--sin-pensamiento', action='store_true')
    a = sub.add_parser('evaluar'); a.add_argument('--corpus', type=Path, required=True); a.add_argument('--destino', type=Path, required=True)
    a.add_argument('--modelo', required=True)
    a.add_argument('--seleccion', type=Path, required=True, help='resultado fijado antes de abrir la prueba')
    a.add_argument('--dataset', type=Path, required=True, help='corpus de entrenamiento para revalidar ausencia de fuga')
    a.add_argument('--dos-etapas', action='store_true')
    a.add_argument('--sin-pensamiento', action='store_true')
    a.add_argument('--publicar', action='store_true')
    args = p.parse_args(argv)
    try:
        from convertersmartgrid.aplicacion.asistente.aceptacion import auditar_propuestas, decidir_aceptacion, evaluar_ordenes
        from convertersmartgrid.aplicacion.asistente.destilacion_integral import leer_corpus
        from convertersmartgrid.aplicacion.asistente.propuestas_maestro import generar_propuestas, VOCABULARIO
        from convertersmartgrid.aplicacion.asistente.ollama import ClienteOllama
        from convertersmartgrid.aplicacion.training_coordinator import BloqueoGPU, ruta_guardia_gpu
        from convertersmartgrid.aplicacion.trabajadores_ml import turno_gpu
        from convertersmartgrid.aplicacion.evaluacion_modelos import huella, texto_canonico
        if args.accion == 'preparar':
            filas, meta = generar_propuestas()
            datos, fuente = leer_corpus(args.dataset)
            auditoria = auditar_propuestas(filas, [r for r in datos if r['particion'] == 'entrenamiento'])
            if not auditoria['valid']:
                raise ValueError(str(auditoria['fallos']))
            escribir(args.destino / 'propuestas.json', filas)
            escribir(args.destino / 'manifest.json', {**meta, 'auditoria': auditoria,
                'training_dataset_hash': fuente['dataset_hash']})
            escribir(args.destino / 'humanas.json', [r for r in datos if r['quality'] == 'gold_human'])
            if args.revisadas_maestro:
                # 047:RF-64: el conjunto sellado del maestro va aparte de las humanas, con su sello, y nunca se mezcla.
                from convertersmartgrid.aplicacion.asistente.ordenes_maestro import leer_revisadas
                revisadas, sello = leer_revisadas(args.revisadas_maestro)
                escribir(args.destino / 'maestro_revisadas.json', {'ordenes': revisadas, 'manifest': sello})
            if args.publicar:
                from convertersmartgrid.aplicacion.asistente import almacen
                almacen.guardar_json('aceptacion_agente', {'corpus': str(args.destino.resolve()), 'evaluacion': None})
            resultado = {**meta, 'auditoria': auditoria}
        else:
            from convertersmartgrid.aplicacion.training_coordinator import exigir_memoria_ml
            exigir_memoria_ml(4., minimo_commit_gib=6.)
            ruta_lock = ruta_guardia_gpu()
            # 106:RF-21 (2026-11-24): con BloqueoGPU directo caía al instante con «GPU ocupada» si el turno lo tenía otro (la
            # 070 T22, en su ensayo, con el gancho de un commit); turno_gpu espera con plazo y dice quién lo tiene.
            with turno_gpu('aceptacion-agente'):
                if args.accion == 'seleccionar':
                    datos, fuente = leer_corpus(args.dataset)
                    cuenta, casos = set(), []
                    for r in datos:
                        if r['particion'] == 'seleccion' and r['tarea'] not in cuenta:
                            cuenta.add(r['tarea']); casos.append(r)
                    cliente_meta = ClienteOllama(tiempo_max_s=10.)
                    modelos_instalados = {m['name']: m.get('digest') for m in
                        (cliente_meta._pedir('/api/tags') or {}).get('models', [])}
                    nombres = [n.strip() for n in args.modelos.split(',') if n.strip()]
                    if not nombres or any(n not in modelos_instalados for n in nombres):
                        raise ValueError('modelo local no instalado; selección no iniciada')
                    escribir(args.destino / 'protocolo.json', {'modelos': nombres,
                        'digests': {n: modelos_instalados[n] for n in nombres},
                        'particion': 'seleccion', 'record_ids': [r['record_id'] for r in casos],
                        'dataset_hash': fuente['dataset_hash'], 'criterio': 'acierto_tarea, despues F1; sin prueba',
                        'dos_etapas': args.dos_etapas, 'pensar': False if args.sin_pensamiento else None})
                    comparacion = []
                    for nombre in nombres:
                        cliente = ClienteOllama(modelo=nombre, tiempo_max_s=90., revisar_transformer=True,
                            dos_etapas=args.dos_etapas, pensar=False if args.sin_pensamiento else None)
                        try:
                            m = evaluar_ordenes(casos, cliente=cliente)
                        finally:
                            cliente.liberar_gpu(solo_actual=True)
                        m['modelo_digest'] = modelos_instalados[nombre]
                        escribir(args.destino / (nombre.replace(':', '_').replace('/', '_') + '.json'), m)
                        comparacion.append(m)
                    ganador = max(comparacion, key=lambda m:(m['acierto_tarea'],m['f1_datos']))
                    resultado = {'elegido': ganador['modelo_llm'], 'criterio': 'seleccion',
                                 'modelo_digest': ganador['modelo_digest'], 'dataset_hash': fuente['dataset_hash'],
                                 'dos_etapas': args.dos_etapas, 'pensar': False if args.sin_pensamiento else None,
                                 'comparacion': [{k:m[k] for k in ('modelo_llm','acierto_tarea','f1_datos','ejemplos')} for m in comparacion]}
                else:
                    seleccion = json.loads(args.seleccion.read_text(encoding='utf-8'))
                    if (seleccion.get('criterio') != 'seleccion' or seleccion.get('elegido') != args.modelo
                            or seleccion.get('dos_etapas') != args.dos_etapas
                            or seleccion.get('pensar') != (False if args.sin_pensamiento else None)):
                        raise ValueError('configuración distinta de la selección previa')
                    filas = json.loads((args.corpus / 'propuestas.json').read_text(encoding='utf-8'))
                    meta = json.loads((args.corpus / 'manifest.json').read_text(encoding='utf-8'))
                    datos, fuente = leer_corpus(args.dataset)
                    auditoria = auditar_propuestas(filas, [r for r in datos if r['particion'] == 'entrenamiento'])
                    if (huella(filas) != meta['dataset_hash'] or not auditoria['valid']
                            or fuente['dataset_hash'] != meta['training_dataset_hash']
                            or seleccion.get('dataset_hash') != fuente['dataset_hash']):
                        raise ValueError('integridad o auditoría del conjunto de propuestas inválida')
                    instalado = next((m for m in (ClienteOllama()._pedir('/api/tags') or {}).get('models', [])
                                      if m['name'] == args.modelo), {})
                    if not instalado.get('digest') or instalado['digest'] != seleccion.get('modelo_digest'):
                        raise ValueError('pesos distintos de los medidos en selección')
                    escribir(args.destino / 'protocolo.json', {'modelo': args.modelo, 'dataset_hash': meta['dataset_hash'],
                        'modelo_digest': instalado['digest'], 'seleccion_hash': huella(seleccion),
                        'dos_etapas': args.dos_etapas, 'pensar': False if args.sin_pensamiento else None,
                        'confirmacion_obligatoria': True, 'prueba_sin_entrenamiento': True})
                    cliente = ClienteOllama(modelo=args.modelo, tiempo_max_s=90., revisar_transformer=True,
                        dos_etapas=args.dos_etapas, pensar=False if args.sin_pensamiento else None)
                    try:
                        m = evaluar_ordenes(filas, cliente=cliente, vocabulario=VOCABULARIO)
                        reales = json.loads((args.corpus / 'humanas.json').read_text(encoding='utf-8'))
                        humanas = evaluar_ordenes(reales, cliente=cliente) if reales else {'ejemplos': 0}
                        # 047:RF-9: independencia comprobada aquí, donde se ve el entrenamiento; si no, queda bloqueada.
                        entrenamiento = {texto_canonico(r['texto']) for r in datos if r['particion'] == 'entrenamiento'}
                        humanas.update(dataset_hash=huella(reales), sin_fuga=not any(
                            texto_canonico(r['texto']) in entrenamiento for r in reales))
                        revisadas = None
                        ruta_revisadas = args.corpus / 'maestro_revisadas.json'
                        if ruta_revisadas.is_file():
                            # 047:RF-68: el sello se comprueba otra vez aquí, donde se ve el entrenamiento.
                            from convertersmartgrid.aplicacion.asistente.aceptacion import medida_revisadas
                            copia = json.loads(ruta_revisadas.read_text(encoding='utf-8'))
                            revisadas = medida_revisadas(
                                evaluar_ordenes(copia['ordenes'], cliente=cliente, vocabulario=VOCABULARIO),
                                copia['ordenes'], copia['manifest'], entrenamiento)
                    finally:
                        cliente.liberar_gpu(solo_actual=True)
                    m['sin_fuga'] = auditoria['sin_fuga']
                    m['modelo_digest'] = instalado['digest']
                    # Las humanas permanecen separadas; este informe no las inventa.
                    aceptacion = decidir_aceptacion(m, humanas, revisadas)
                    resultado = {'metricas': m, 'humanas': humanas, 'maestro_revisadas': revisadas,
                                 'aceptacion': aceptacion, 'manifest': meta}
                    escribir(args.destino / 'decision_ajuste.json', aceptacion['ajuste'])
            escribir(args.destino / 'resultado.json', resultado)
            if args.accion == 'evaluar' and args.publicar:
                from convertersmartgrid.aplicacion.asistente import almacen
                almacen.guardar_json('aceptacion_agente', {'corpus': str(args.corpus.resolve()),
                    'evaluacion': str((args.destino / 'resultado.json').resolve())})
        print(json.dumps(resultado, ensure_ascii=True, allow_nan=False))
        return 0
    except Exception as exc:
        fallo = {'ok': False, 'error': str(exc), 'accion': args.accion}
        try:
            escribir(args.destino / f'error_{os.getpid()}.json', fallo)
        except (OSError, ValueError):
            pass
        print(json.dumps(fallo, ensure_ascii=True))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
