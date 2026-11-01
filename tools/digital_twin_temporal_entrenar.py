#!/usr/bin/env python
"""Trabajador de series observadas y GRU causal; conserva candidatos y permite recarga (043/046)."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[1]
if str(REPO/'src') not in sys.path:sys.path.insert(0,str(REPO/'src'))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    entrada=p.add_mutually_exclusive_group(required=True)
    entrada.add_argument('--cabeceras',type=Path)
    entrada.add_argument('--reabrir',type=Path)
    p.add_argument('--raiz',type=Path,required=True)
    p.add_argument('--output-json',type=Path,required=True)
    p.add_argument('--semillas',default='11,23,37,53,71')
    p.add_argument('--epocas',type=int,default=40)
    p.add_argument('--zona-horaria')
    p.add_argument('--codigos',help='Codigos explicitos de las columnas del libro ancho, separados por coma')
    args=p.parse_args(argv)
    from convertersmartgrid.trabajadores_ml import escribir_informe,fallo,semillas_de,turno_gpu,sha_archivo
    if args.output_json.exists():print('Informe existente conservado');return 2
    try:
        from convertersmartgrid.digital_twin.temporal_entrenamiento import cargar_cabeceras,entrenar_temporal,reabrir_temporal
        if args.cabeceras:
            series,procedencia=cargar_cabeceras(args.cabeceras,zona_horaria=args.zona_horaria,
                codigos=tuple(v.strip() for v in (args.codigos or '').split(',') if v.strip()))
            semillas=semillas_de(args.semillas)
            if args.epocas<1:raise ValueError('epocas positivas obligatorias')
        from convertersmartgrid.training_coordinator import exigir_memoria_ml
        exigir_memoria_ml(3.,minimo_commit_gib=6.)
        with turno_gpu('gru-temporal'):
            if args.reabrir:resultado=reabrir_temporal(args.reabrir)
            else:
                resultado=entrenar_temporal(series,args.raiz,semillas=semillas,procedencia=procedencia,epocas=args.epocas)
                if sha_archivo(args.cabeceras)!=procedencia['sha256']:raise ValueError('el libro cambio durante el ajuste')
        codigo=0
    except Exception as exc:resultado=fallo(exc);codigo=2
    escribir_informe(args.output_json,resultado)
    print(json.dumps({k:v for k,v in resultado.items() if k not in ('seleccion','prueba','baseline_estacional')},ensure_ascii=True))
    return codigo


if __name__=='__main__':raise SystemExit(main())
