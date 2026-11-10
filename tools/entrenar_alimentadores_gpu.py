#!/usr/bin/env python
"""Entrena una red de pronóstico por alimentador, uno tras otro, en la GPU (spec 089, RF-89 y RF-90).

Cada alimentador lee sus series de cabecera y escaladas con el mismo dataset de ``pronostico_demanda`` (los libros
que haya en las carpetas, sin lista fija), entrena el modelo pedido, emite su pronóstico probabilístico y lo guarda en
su propia carpeta con ``resultado.json``. Entre uno y otro libera la memoria de la GPU: con todos a la vez, 101
alimentadores no caben. Un alimentador ya entrenado se retoma y no se repite.

No elige ni promociona modelos: la competición con backtest y la puerta son de ``tools/pronostico_demanda.py``.
"""
from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / 'src') not in sys.path:
    sys.path.insert(0, str(REPO / 'src'))

from convertersmartgrid.digital_twin import pronostico as pr  # noqa: E402

CADENCIA_MIN = 15
ZONA_HORARIA = 'America/Lima'


def seleccion(puntos, pedidos: str | None, limite: int | None) -> list[str]:
    """089:RF-89: los alimentadores del libro de equivalencia, o los pedidos; sin repetir y en orden estable."""
    if pedidos:
        return list(dict.fromkeys(a.strip().upper() for a in pedidos.split(',') if a.strip()))
    todos = sorted({p.codigo for p in puntos if p.clase == 'alimentador'})
    return todos[:limite] if limite else todos


def entrenar_un_alimentador(codigo: str, fuentes_base: dict, salida_base: Path, *, algoritmo: str, pasos: int,
                            contexto_pasos: int = 672, horizonte: int = 96, semilla: int = 42) -> dict:
    """Entrena ``codigo`` y deja su modelo y su ``resultado.json``; uno ya entrenado se devuelve tal cual."""
    import numpy as np

    from convertersmartgrid.pronostico_demanda import Fuentes, armar_dataset

    salida = salida_base / codigo
    salida.mkdir(parents=True, exist_ok=True)
    reporte = salida / 'resultado.json'
    if reporte.exists():
        previo = json.loads(reporte.read_text(encoding='utf-8'))
        if previo.get('status') == 'ENTRENADO' and previo.get('algoritmo') == algoritmo:
            print(f'{codigo}: ya entrenado con {algoritmo}; se retoma.', flush=True)
            return previo
    t0 = time.time()
    ds = armar_dataset(Fuentes(alimentadores=[codigo], **fuentes_base))
    minimo = contexto_pasos + horizonte
    objetivos = [o for o in ds.objetivos if o.clase in ('cabecera', 'escaladas') and len(o.curva) > minimo]
    if not objetivos:
        res = {'alimentador': codigo, 'status': 'SIN_HISTORIA', 'algoritmo': algoritmo,
               'motivo': f'ninguna serie de cabecera o escaladas con más de {minimo} registros de {CADENCIA_MIN} min'}
        reporte.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"{codigo}: {res['motivo']}", flush=True)
        return res
    print(f'{codigo}: {len(objetivos)} series en {time.time() - t0:.1f} s; {algoritmo} en la GPU…', flush=True)
    conjunto = pr.construir_conjunto(objetivos, cadencia_min=CADENCIA_MIN, zona_horaria=ZONA_HORARIA)
    t1 = time.time()
    modelo = pr.fabrica(algoritmo, horizonte=horizonte, cadencia_min=CADENCIA_MIN, contexto_pasos=contexto_pasos,
                        pasos=pasos, lote=32, semilla=semilla)
    ajuste = modelo.ajustar(conjunto, len(conjunto.instantes) - horizonte, horizonte, semilla)
    emisiones = np.array([conjunto.ultima_emision(n, contexto_pasos) for n in conjunto.nombres])
    pred = modelo.predecir(conjunto.lote(conjunto.nombres, emisiones, contexto=contexto_pasos, horizonte=horizonte))
    modelo.guardar(salida / 'modelo_gpu')
    res = {'alimentador': codigo, 'status': 'ENTRENADO', 'algoritmo': algoritmo, 'pasos': pasos,
           'tiempo_gpu_s': round(time.time() - t1, 2), 'objetivos': list(conjunto.nombres), 'ajuste': ajuste,
           'prediccion_forma': list(pred.shape), 'valores_finitos': bool(np.isfinite(pred).all()),
           'modelo': str(salida / 'modelo_gpu')}
    reporte.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding='utf-8')
    print(f"{codigo}: entrenado en {res['tiempo_gpu_s']} s", flush=True)
    return res


def _liberar_gpu() -> None:
    """Entre alimentadores: sin esto la memoria de la GPU crece con cada uno (089:RF-89)."""
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Entrena una red de pronóstico por alimentador, uno tras otro, en la GPU '
                                            '(089:RF-89, RF-90)')
    p.add_argument('--cabecera', type=Path, required=True, help='Carpeta o libro de la medición de cabecera')
    p.add_argument('--equivalencia', type=Path, required=True, help='Libro alimentador–medidor')
    p.add_argument('--clientes', type=Path, help='Carpeta de los libros de clientes fijos')
    p.add_argument('--suministros', type=Path, help='Libro o carpeta de suministros')
    p.add_argument('--salida', type=Path, required=True, help='Carpeta de los modelos y resultados (fuera de git)')
    p.add_argument('--algoritmo', default='nhits', choices=pr.NEURONALES)
    p.add_argument('--pasos', type=int, default=150, help='Pasos de entrenamiento de cada alimentador')
    p.add_argument('--alimentadores', help='Códigos separados por coma; sin ellos, todos los del libro de equivalencia')
    p.add_argument('--limite', type=int, help='Solo los N primeros alimentadores del libro')
    args = p.parse_args(argv)

    from convertersmartgrid.pronostico_demanda import equivalencias
    from convertersmartgrid.training_coordinator import dispositivo, exigir_memoria_ml

    print(f'Dispositivo: {dispositivo()}', flush=True)       # sin CUDA, error claro (gemelo en GPU)
    exigir_memoria_ml(minimo_fisico_gib=1.0, minimo_commit_gib=4.0)
    puntos, _avisos = equivalencias(args.equivalencia)
    alimentadores = seleccion(puntos, args.alimentadores, args.limite)
    print(f'{len(alimentadores)} alimentador(es), uno tras otro.', flush=True)
    fuentes = {'cabecera': args.cabecera, 'equivalencia': args.equivalencia, 'clientes': args.clientes,
               'suministros': args.suministros}
    resultados = []
    for i, codigo in enumerate(alimentadores, start=1):
        print(f'[{i}/{len(alimentadores)}] {codigo}', flush=True)
        try:
            resultados.append(entrenar_un_alimentador(codigo, fuentes, args.salida, algoritmo=args.algoritmo,
                                                      pasos=args.pasos))
        except Exception as exc:  # noqa: BLE001 - un alimentador que falla no detiene a los demás; se informa
            print(f'{codigo}: ERROR {type(exc).__name__}: {exc}', flush=True)
            resultados.append({'alimentador': codigo, 'status': 'ERROR', 'error': f'{type(exc).__name__}: {exc}'})
        finally:
            _liberar_gpu()
    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / 'resumen.json').write_text(json.dumps(resultados, indent=2, ensure_ascii=False, default=str),
                                              encoding='utf-8')
    errores = [r['alimentador'] for r in resultados if r['status'] == 'ERROR']
    entrenados = sum(r['status'] == 'ENTRENADO' for r in resultados)
    print(f'{entrenados} entrenado(s), {len(errores)} con error{": " + ", ".join(errores) if errores else ""}.')
    # 089:RF-90: un error no se esconde en el resumen; la orden termina con código 1.
    return 1 if errores else 0


if __name__ == '__main__':
    raise SystemExit(main())
