#!/usr/bin/env python
"""Ajuste generativo de un alumno NF4 fijado; conserva candidato sin activarlo (043/047).

Uso: python tools/asistente_qlora.py --help
El corpus de redacción del PIDE sellado (072:RF-50, RF-51) se audita con lo suyo y entrena con su propio prompt.
`evaluar` examina el modelo de redacción en las particiones selladas de selección y prueba frente a la base NF4 y decide
aprobado o rechazado (072:RF-53 a RF-57): 0 aprobado, 1 rechazado, 2 error; no promueve ni activa nada.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[1]
if str(REPO/'src') not in sys.path:sys.path.insert(0,str(REPO/'src'))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='accion',required=True)
    a=sub.add_parser('entrenar')
    a.add_argument('--dataset',type=Path,required=True)
    a.add_argument('--salida',type=Path,required=True)
    a.add_argument('--modelo')
    a.add_argument('--revision')
    a.add_argument('--epocas',type=int,default=1)
    a.add_argument('--semilla',type=int,default=11)
    # 047:RF-59: el corpus de órdenes solo se ajusta con la decisión de decidir_ajuste («necesaria») o con un
    # experimento autorizado por su id (plan de la 047, T7); la decisión real del 2026-11-03 es «bloqueada».
    a.add_argument('--decision',type=Path,help='JSON de decidir_ajuste/decidir_aceptacion (047:RF-59)')
    a.add_argument('--experimento-autorizado',help='Id del experimento autorizado en el plan (p. ej. 047-T7)')
    a=sub.add_parser('preflight')
    a.add_argument('--dataset',type=Path,required=True)
    a.add_argument('--salida',type=Path,required=True)
    a=sub.add_parser('evaluar',help='puertas del modelo de redacción del PIDE')
    a.add_argument('--dataset',type=Path,required=True,help='corpus de redacción sellado con el que se entrenó')
    a.add_argument('--salida',type=Path,required=True)
    a.add_argument('--adaptador',type=Path,help='carpeta adaptador del checkpoint final: mide la pérdida (y redacta '
                   'si no hay --modelo-ollama)')
    a.add_argument('--modelo-ollama',help='modelo publicado en Ollama que redacta las salidas que se revisan')
    a.add_argument('--catalogo',type=Path,help='JSON de nombres con el que se selló el corpus')
    a.add_argument('--informe-ordenes',type=Path,help='resultado.json de llm_destilar.py evaluar --parte prueba del '
                   'candidato, solo si se quiere usar también como intérprete de órdenes')
    a.add_argument('--informe-ordenes-en-uso',type=Path,help='el mismo informe del intérprete en uso')
    a.add_argument('--semilla',type=int,default=11)
    args=p.parse_args(argv)
    from convertersmartgrid.aplicacion.trabajadores_ml import escribir_informe,fallo,turno_gpu
    reporte=args.salida/'training_manifest.json'
    if args.salida.exists() and (not args.salida.is_dir() or any(args.salida.iterdir())):
        print(json.dumps({'error':'salida existente conservada'}));return 2
    args.salida.mkdir(parents=True,exist_ok=True)
    try:
        from convertersmartgrid.aplicacion.asistente.llm_destilacion import auditar_fuentes_corpus,entrenar_epoca,ficha_base
        from convertersmartgrid.aplicacion.asistente.corpus_redaccion import (TIPO_CORPUS,auditar_corpus_redaccion,
            leer_particion_redaccion,tipo_corpus)
        # 072:RF-51: el lector de cada tipo de corpus; sin tipo, el de órdenes de siempre.
        lectores={TIPO_CORPUS:leer_particion_redaccion}
        if not args.dataset.is_dir():raise ValueError('no existe el corpus generativo sellado')
        if args.accion=='evaluar':
            reporte=args.salida/'evaluacion_redaccion.json'
            if tipo_corpus(args.dataset)!=TIPO_CORPUS:
                raise ValueError('evaluar examina el corpus de redacción del PIDE; el de órdenes se examina con '
                                 'llm_destilar.py evaluar')
        if tipo_corpus(args.dataset)==TIPO_CORPUS:
            # 072:RF-50: el corpus de redacción del PIDE tiene su auditoría; entrenar_epoca usa su prompt sellado.
            auditoria=auditar_corpus_redaccion(args.dataset)
        else:
            # 047:RF-69: el corpus v7 de órdenes se audita con su validador.
            from convertersmartgrid.aplicacion.asistente.corpus_contrato_llm import auditar_v7,es_v7
            auditoria=auditar_v7(args.dataset) if es_v7(args.dataset) else auditar_fuentes_corpus(args.dataset)
        base=ficha_base()
        if args.accion=='evaluar':
            reporte=args.salida/'evaluacion_redaccion.json'
            resultado=_evaluar(args,auditoria,turno_gpu)
            escribir_informe(reporte,resultado)
            print(json.dumps({k:resultado[k] for k in ('status','motivos','promovido','activado')},ensure_ascii=True))
            return 0 if resultado['aprobado'] else 1
        if args.accion=='preflight':
            resultado={'status':'RECHAZADO','reason':'preflight de datos; entrenamiento no solicitado',
                'training_completed':False,'promovido':False,'auditoria':auditoria,'base':base}
        else:
            if (args.modelo is not None and args.modelo!=base['id']) or (args.revision is not None and args.revision!=base['revision']):
                raise ValueError('modelo o revision distintos de la base NF4 fijada')
            if args.epocas not in (1,2) or args.semilla<0:raise ValueError('presupuesto de una o dos epocas y semilla no negativa')
            decision_ajuste=None
            if tipo_corpus(args.dataset)!=TIPO_CORPUS:
                if args.decision is not None:
                    decision_ajuste=json.loads(args.decision.read_text(encoding='utf-8'))
                d=(decision_ajuste or {}).get('decision')
                if d!='necesaria' and not args.experimento_autorizado:
                    raise ValueError('decidir_ajuste no dice «necesaria» (%s): el ajuste de órdenes pide esa decisión '
                                     'o --experimento-autorizado'%(d or 'sin decisión'))
            checkpoints=[];desde=None
            with turno_gpu('qlora-generativo'):
                for epoca in range(1,args.epocas+1):
                    estado=entrenar_epoca(args.dataset,args.salida/f'epoca_{epoca}',epoca=epoca,
                                         desde=desde,semilla=args.semilla,lectores=lectores)
                    desde=Path(estado['checkpoint']);checkpoints.append(estado)
            resultado={'status':'RECHAZADO','candidate_status':'CANDIDATO','entrenado':True,
                'training_completed':True,'promovido':False,'base':base,'auditoria':auditoria,
                'checkpoints':checkpoints,'gates':{'approved':False},
                'decision_ajuste':decision_ajuste,'experimento_autorizado':args.experimento_autorizado,
                'reason':'pesos conservados; faltan seleccion, recarga/exportacion y aceptacion independiente'}
        codigo=0
    except Exception as exc:
        resultado=fallo(exc);codigo=2
    escribir_informe(reporte,resultado)
    print(json.dumps({k:v for k,v in resultado.items() if k not in ('base','checkpoints','auditoria')},ensure_ascii=True))
    return codigo


def _evaluar(args,auditoria,turno_gpu):
    """Las puertas del modelo de redacción: pérdida frente a la base, salidas limpias e intérprete (072:RF-53 a RF-57)."""
    from convertersmartgrid.aplicacion.asistente.corpus_redaccion import (TIPO_CORPUS,PARTES_EVALUACION,DECODIFICACION,
        NO_REPETIR_NGRAMA,catalogo_sellado,decidir_redaccion,leer_particion_redaccion,puerta_interprete)
    from convertersmartgrid.aplicacion.asistente import llm_destilacion
    if args.adaptador is None and not args.modelo_ollama:
        raise ValueError('evaluar pide --adaptador, --modelo-ollama o los dos')
    if args.adaptador is not None and not (args.adaptador/'adapter_config.json').is_file():
        raise ValueError('el adaptador no es la carpeta adaptador de un checkpoint')
    catalogo=json.loads(args.catalogo.read_text(encoding='utf-8')) if args.catalogo else None
    catalogo=catalogo_sellado(args.dataset,catalogo)
    def leer(ruta):
        return json.loads(ruta.read_text(encoding='utf-8')) if ruta else None
    interprete=(puerta_interprete(leer(args.informe_ordenes),leer(args.informe_ordenes_en_uso))
                if args.informe_ordenes or args.informe_ordenes_en_uso else None)
    medida={};ollama=None;salidas={}
    with turno_gpu('evaluacion-redaccion-pide'):  # 071:RF-8: la medida y la redacción usan la GPU
        if args.adaptador is not None:
            medida=llm_destilacion.medir_redaccion(args.dataset,args.adaptador,
                lectores={TIPO_CORPUS:leer_particion_redaccion},partes=PARTES_EVALUACION,
                generar=not args.modelo_ollama,semilla=args.semilla,
                # 072:RF-59: la misma penalización de repeticiones que lleva el modelo publicado.
                muestreo={'temperature':DECODIFICACION['temperature'],'top_p':DECODIFICACION['top_p'],
                          'repetition_penalty':DECODIFICACION['repeat_penalty'],
                          'no_repeat_ngram_size':NO_REPETIR_NGRAMA})
            salidas=dict(medida.get('salidas') or {})
        if args.modelo_ollama:
            from convertersmartgrid.aplicacion.asistente.ollama import ClienteOllama
            cliente=ClienteOllama(modelo=args.modelo_ollama,tiempo_max_s=180,pensar=False)
            instalado=next((m for m in (cliente._pedir('/api/tags') or {}).get('models') or []
                            if m.get('name')==args.modelo_ollama),None)
            if instalado is None:raise ValueError('el modelo de Ollama no está instalado o Ollama no responde')
            ollama={'modelo':args.modelo_ollama,'digest':instalado.get('digest')}
            try:
                for parte in PARTES_EVALUACION:
                    registros,meta=leer_particion_redaccion(args.dataset,parte)
                    salidas[parte]=[cliente.redactar(meta['sistema'],r['texto'],semilla=args.semilla+i,
                                        temperatura=DECODIFICACION['temperature'],top_p=DECODIFICACION['top_p'],
                                        repeat_penalty=DECODIFICACION['repeat_penalty'],
                                        repeat_last_n=DECODIFICACION['repeat_last_n'])
                                    for i,r in enumerate(registros)]
            finally:
                cliente.liberar_gpu(solo_actual=True)
    resultado=decidir_redaccion(args.dataset,medida.get('perdidas') or {},salidas,catalogo=catalogo,
                                interprete=interprete)
    resultado.update(auditoria=auditoria,ollama=ollama,
                     medida={k:medida.get(k) for k in ('adaptador','checkpoint','base','device')} if medida else None,
                     redactado_por='ollama' if ollama else ('adaptador' if medida else None),
                     catalogo={'nombres':sum(len(v) for v in catalogo.values())},semilla=args.semilla)
    return resultado


if __name__=='__main__':raise SystemExit(main())
