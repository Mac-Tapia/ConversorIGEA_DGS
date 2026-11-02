#!/usr/bin/env python
"""Prepara, entrena y verifica el alumno del maestro de sesión (spec 047 T5).

    python tools/asistente_destilar.py preparar --destino output/corpus
    python tools/asistente_destilar.py entrenar --dataset output/corpus --destino output/alumno
    python tools/asistente_destilar.py verificar --modelo output/alumno/alumno

Las etiquetas del maestro son sintéticas; no acreditan órdenes humanas. El
entrenamiento respeta la exclusión GPU y conserva el modelo activo.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / 'src') not in sys.path:
    sys.path.insert(0, str(RAIZ / 'src'))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='accion', required=True)
    preparar = sub.add_parser('preparar')
    preparar.add_argument('--destino', type=Path, required=True)
    preparar.add_argument('--vocabulario', type=Path)
    preparar.add_argument('--por-familia', type=int, default=40)
    entrenar = sub.add_parser('entrenar')
    entrenar.add_argument('--dataset', type=Path, required=True)
    entrenar.add_argument('--destino', type=Path, required=True)
    entrenar.add_argument('--registro', type=Path)
    entrenar.add_argument('--semillas', default='11,23,37')
    entrenar.add_argument('--epocas', type=int, default=24)
    verificar = sub.add_parser('verificar')
    verificar.add_argument('--modelo', type=Path, required=True)
    verificar.add_argument('--familia', choices=('transformer', 'clasificador'), default='transformer')
    ensayar = sub.add_parser('ensayar')
    ensayar.add_argument('--modelo', type=Path, required=True)
    ensayar.add_argument('--ollama', help='Modelo local para probar también el fallback híbrido')
    ensayar.add_argument('--output-json', type=Path, required=True)
    evaluar = sub.add_parser('evaluar')
    evaluar.add_argument('--modelo', type=Path, required=True)
    evaluar.add_argument('--dataset', type=Path, required=True)
    evaluar.add_argument('--ollama', help='Modelo local del fallback híbrido')
    evaluar.add_argument('--por-tarea', type=int, default=1)
    evaluar.add_argument('--output-json', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        from convertersmartgrid.asistente.destilacion_integral import (
            entrenar_destilacion, guardar_corpus, preparar_corpus, verificar_reapertura)
        if args.accion == 'preparar':
            from convertersmartgrid.asistente import almacen
            vocab = json.loads(args.vocabulario.read_text(encoding='utf-8')) if args.vocabulario else {}
            filas, meta = preparar_corpus(vocab, almacen.leer('ejemplos'), por_familia=args.por_familia)
            guardar_corpus(args.destino, filas, meta)
            resultado = {'ok': True, **meta}
        elif args.accion == 'entrenar':
            from convertersmartgrid.asistente.transformer import Configuracion
            from convertersmartgrid.training_coordinator import BloqueoGPU
            if args.epocas < 1:
                raise ValueError('épocas positivas obligatorias')
            semillas = tuple(int(s) for s in args.semillas.split(',') if s.strip())
            ruta = Path(os.environ.get('CSG_ML_GPU_LOCK') or str(Path(tempfile.gettempdir()) / 'convertersmartgrid-gpu.lock'))
            with BloqueoGPU(ruta, 'destilacion-integral'):
                resultado = entrenar_destilacion(args.dataset, args.destino,
                    cfg=Configuracion(epocas=args.epocas), semillas=semillas, registro=args.registro)
        elif args.accion == 'verificar':
            if args.familia == 'clasificador':                       # 067:RF-26
                from convertersmartgrid.asistente.clasificador import verificar_reapertura as reabrir_clasificador
                resultado = reabrir_clasificador(args.modelo)
            else:
                resultado = verificar_reapertura(args.modelo)
        else:
            from convertersmartgrid.asistente.destilacion_integral import cargar_alumno, ensayar_funcionamiento, evaluar_agente, leer_corpus
            from convertersmartgrid.asistente.ollama import ClienteOllama
            from convertersmartgrid.training_coordinator import BloqueoGPU
            ruta = Path(os.environ.get('CSG_ML_GPU_LOCK') or str(Path(tempfile.gettempdir()) / 'convertersmartgrid-gpu.lock'))
            with BloqueoGPU(ruta, 'ensayo-agente-integral'):
                cliente = ClienteOllama(modelo=args.ollama, tiempo_max_s=60.) if args.ollama else None
                try:
                    modelo = cargar_alumno(args.modelo)
                    resultado = (ensayar_funcionamiento(modelo, ollama=cliente) if args.accion == 'ensayar'
                        else evaluar_agente(modelo, leer_corpus(args.dataset)[0], ollama=cliente, por_tarea=args.por_tarea))
                finally:
                    if cliente is not None:
                        cliente.liberar_gpu()
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(resultado, ensure_ascii=True, allow_nan=False))
        return 0 if resultado.get('ok', True) else 2
    except Exception as exc:
        error = {'ok': False, 'training_completed': False, 'status': 'ERROR_ENTORNO',
                 'error': str(exc), 'traza': traceback.format_exc()}
        if args.accion == 'entrenar':
            args.destino.mkdir(parents=True, exist_ok=True)
            # No reemplazar la decisión de una ejecución previa.
            ruta_error = args.destino / f'error-{os.getpid()}.json'
            ruta_error.write_text(json.dumps(error, ensure_ascii=False, indent=2), encoding='utf-8')
        elif args.accion in {'ensayar', 'evaluar'}:
            ruta_error = args.output_json
            if ruta_error.exists():
                ruta_error = ruta_error.with_name(f'{ruta_error.stem}.error-{os.getpid()}.json')
            ruta_error.parent.mkdir(parents=True, exist_ok=True)
            error['report_path'] = str(ruta_error)
            ruta_error.write_text(json.dumps(error, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(error, ensure_ascii=True))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
