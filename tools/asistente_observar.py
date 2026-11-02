"""Incorpora copias de informes locales al monitor del conversor sin activar pesos (061:RF-8).

Uso: python tools/asistente_observar.py registrar --help
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def main(argv=None):
    from convertersmartgrid.asistente import almacen
    from convertersmartgrid.training_coordinator import ORDEN_MODELOS
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='accion',required=True)
    a=sub.add_parser('registrar')
    a.add_argument('--informe',type=Path,required=True)
    a.add_argument('--familia',choices=ORDEN_MODELOS,required=True)
    a.add_argument('--etiqueta',required=True)
    a.add_argument('--raiz',type=Path)
    a=sub.add_parser('listar');a.add_argument('--raiz',type=Path)
    args=p.parse_args(argv)
    from convertersmartgrid.asistente.observacion import registrar_evidencia,leer_evidencias
    try:
        raiz=args.raiz or almacen.raiz()
        r=(registrar_evidencia(raiz,args.informe,familia=args.familia,etiqueta=args.etiqueta)
            if args.accion=='registrar' else leer_evidencias(raiz))
        print(json.dumps(r,ensure_ascii=True,allow_nan=False));return 0
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=True));return 2


if __name__=='__main__':raise SystemExit(main())
