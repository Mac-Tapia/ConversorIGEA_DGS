#!/usr/bin/env python
"""Ajuste generativo real del alumno NF4 fijado; conserva candidato sin activarlo (043/047)."""
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
    a=sub.add_parser('preflight')
    a.add_argument('--dataset',type=Path,required=True)
    a.add_argument('--salida',type=Path,required=True)
    args=p.parse_args(argv)
    from convertersmartgrid.trabajadores_ml import escribir_informe,fallo,turno_gpu
    reporte=args.salida/'training_manifest.json'
    if args.salida.exists() and (not args.salida.is_dir() or any(args.salida.iterdir())):
        print(json.dumps({'error':'salida existente conservada'}));return 2
    args.salida.mkdir(parents=True,exist_ok=True)
    try:
        from convertersmartgrid.asistente.llm_destilacion import auditar_fuentes_corpus,entrenar_epoca,ficha_base
        if not args.dataset.is_dir():raise ValueError('no existe el corpus generativo sellado')
        auditoria=auditar_fuentes_corpus(args.dataset)
        base=ficha_base()
        if args.accion=='preflight':
            resultado={'status':'RECHAZADO','reason':'preflight de datos; entrenamiento no solicitado',
                'training_completed':False,'promovido':False,'auditoria':auditoria,'base':base}
        else:
            if (args.modelo is not None and args.modelo!=base['id']) or (args.revision is not None and args.revision!=base['revision']):
                raise ValueError('modelo o revision distintos de la base NF4 fijada')
            if args.epocas not in (1,2) or args.semilla<0:raise ValueError('presupuesto de una o dos epocas y semilla no negativa')
            checkpoints=[];desde=None
            with turno_gpu('qlora-generativo'):
                for epoca in range(1,args.epocas+1):
                    estado=entrenar_epoca(args.dataset,args.salida/f'epoca_{epoca}',epoca=epoca,
                                         desde=desde,semilla=args.semilla)
                    desde=Path(estado['checkpoint']);checkpoints.append(estado)
            resultado={'status':'RECHAZADO','candidate_status':'CANDIDATO','entrenado':True,
                'training_completed':True,'promovido':False,'base':base,'auditoria':auditoria,
                'checkpoints':checkpoints,'gates':{'approved':False},
                'reason':'pesos conservados; faltan seleccion, recarga/exportacion y aceptacion independiente'}
        codigo=0
    except Exception as exc:
        resultado=fallo(exc);codigo=2
    escribir_informe(reporte,resultado)
    print(json.dumps({k:v for k,v in resultado.items() if k not in ('base','checkpoints','auditoria')},ensure_ascii=True))
    return codigo


if __name__=='__main__':raise SystemExit(main())
