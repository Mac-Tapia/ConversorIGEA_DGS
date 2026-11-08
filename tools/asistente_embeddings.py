#!/usr/bin/env python
"""Ajuste y evaluacion de embeddings locales con particiones trazables (043/047).

Uso: python tools/asistente_embeddings.py --help
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[1]
if str(REPO/'src') not in sys.path:sys.path.insert(0,str(REPO/'src'))


def cargar_dataset(dataset: Path, *, entrenamiento: bool):
    """043/050: un solo lector para preparación y trabajador del recuperador."""
    from convertersmartgrid.asistente.embeddings import cargar_dataset_recuperacion
    return cargar_dataset_recuperacion(dataset, entrenamiento=entrenamiento)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('accion',choices=('entrenar','evaluar'))
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--destino',type=Path,required=True)
    p.add_argument('--modelo',default='intfloat/multilingual-e5-base')
    p.add_argument('--epocas',type=int,default=1)
    args=p.parse_args(argv)
    from convertersmartgrid.trabajadores_ml import escribir_informe,fallo,turno_gpu
    if args.destino.exists() and (not args.destino.is_dir() or any(args.destino.iterdir())):
        print('Destino existente conservado');return 2
    args.destino.mkdir(parents=True,exist_ok=True)
    try:
        frags,pares=cargar_dataset(args.dataset,entrenamiento=args.accion=='entrenar')
        from convertersmartgrid.asistente.embeddings import entrenar_recuperador,cargar_encoder,protocolo_encoder,evaluar_recuperador,guardar_indice_versionado,reabrir_indice_versionado
        with turno_gpu('embeddings'):
            if args.accion=='entrenar':resultado=entrenar_recuperador(pares,args.destino,modelo_base=args.modelo,epocas=args.epocas)
            else:
                from convertersmartgrid.asistente.indice import Indice
                modelo=cargar_encoder(args.modelo)
                protocolo=protocolo_encoder(args.modelo)
                prefijos=(protocolo['query_prefix'],protocolo['passage_prefix'])
                corpus=modelo.encode([prefijos[1]+f.texto for f in frags],normalize_embeddings=True).tolist()
                indice=Indice(frags,corpus);base=Indice(frags)
                consultas={p.pregunta for p in pares}
                vectores=dict(zip(sorted(consultas),modelo.encode([prefijos[0]+q for q in sorted(consultas)],normalize_embeddings=True).tolist(),strict=True))
                def buscar(q,k):
                    filas=indice.buscar(q,k,vectores[q])
                    return filas if filas and (filas[0]['bm25']>=2. or filas[0]['coseno']>=.55) else []
                metricas=evaluar_recuperador(pares,buscar)
                referencia=evaluar_recuperador(pares,lambda q,k:base.buscar(q,k))
                guardar_indice_versionado(frags,corpus,args.destino/'indice',modelo=args.modelo,segmentacion={'dataset':'v2'})
                recargado=reabrir_indice_versionado(args.destino/'indice')
                q=next(iter(vectores))
                if recargado.buscar(q,10,vectores[q])!=indice.buscar(q,10,vectores[q]):raise RuntimeError('indice recargado distinto')
                resultado={'status':'RECHAZADO','promovido':False,'training_completed':False,'evaluation_completed':True,
                    'metricas':metricas,'baseline_bm25':referencia,'active_index_changed':False,
                    'smoke_reload':{'ok':True,'tipo':'indice_en_mismo_proceso'},'gates':{'approved':False},
                    'reason':'evaluacion conservada; publicacion conjunta y puertas pendientes'}
        codigo=0
    except Exception as exc:resultado=fallo(exc);codigo=2
    escribir_informe(args.destino/'decision.json',resultado)
    print(json.dumps({k:v for k,v in resultado.items() if k not in ('metricas','baseline_bm25')},ensure_ascii=True))
    return codigo


if __name__=='__main__':raise SystemExit(main())
