#!/usr/bin/env python
"""Pronóstico del PIDE en la GPU en un paso: quinquenio y largo plazo con el mejor modelo por métricas (031:RF-17, RF-18).

Comprueba antes de leer nada que haya CUDA y memoria, y pasa a ``tools/proyeccion_anual.py`` con las redes neuronales
como candidatos y el horizonte del PIDE (5 años de corto plazo y 30 de largo, si no se dice otro). El ganador lo elige la
competición con su regla escrita antes de medir; aquí no se fija ninguno. Sin libros ni dataset no corre: no hay modo de
demostración con series inventadas.

Uso:
    python tools/lanzar_pronostico_pide_gpu.py --cabecera <carpeta> --equivalencia <libro> --clientes <carpeta> \\
        --suministros <libro> --proyecto P --anio-base 2026 --salida <carpeta> [--modelos nhits,tide] [otras de proyeccion_anual]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / 'src') not in sys.path:
    sys.path.insert(0, str(REPO / 'src'))

#: Las redes que compiten si no se dicen otras: las de la 089 que corren en CUDA (iTransformer y TSMixer, multivariantes,
#: también, pero con todas las series a la vez: se piden con ``--modelos``).
REDES = ('nhits', 'tft', 'patchtst', 'tide')
ANIO_CORTO, ANIO_FIN = 5, 30


def argumentos(argv: list[str] | None) -> tuple[argparse.Namespace, list[str]]:
    p = argparse.ArgumentParser(description='Pronóstico del PIDE en la GPU en un paso, con el mejor modelo por métricas '
                                            '(031:RF-17, RF-18); las demás opciones pasan a proyeccion_anual.py')
    p.add_argument('--modelos', default=','.join(REDES), help=f'Redes que compiten (por defecto {",".join(REDES)})')
    p.add_argument('--anio-corto', type=int, default=ANIO_CORTO, help='Último año relativo del corto plazo (quinquenio)')
    p.add_argument('--anio-fin', type=int, default=ANIO_FIN, help='Último año relativo del horizonte (largo plazo)')
    p.add_argument('--minimo-fisico-gib', type=float, default=1.0)
    p.add_argument('--minimo-commit-gib', type=float, default=4.0)
    args, resto = p.parse_known_args(argv)
    if not any(a in resto for a in ('--dataset', '--cabecera')):
        p.error('indique los libros (--cabecera y --equivalencia) o --dataset: no se pronostica con series inventadas')
    return args, resto


def main(argv=None) -> int:
    args, resto = argumentos(argv)
    from convertersmartgrid.training_coordinator import dispositivo, exigir_memoria_ml

    # 031:RF-18: sin CUDA o sin memoria se dice antes de leer los libros, no a mitad de la competición.
    print(f'Dispositivo: {dispositivo()}', flush=True)
    exigir_memoria_ml(minimo_fisico_gib=args.minimo_fisico_gib, minimo_commit_gib=args.minimo_commit_gib)
    sys.path.insert(0, str(REPO / 'tools'))
    import proyeccion_anual

    return proyeccion_anual.main([*resto, '--modelos', args.modelos, '--anio-corto', str(args.anio_corto),
                                  '--anio-fin', str(args.anio_fin)])


if __name__ == '__main__':
    raise SystemExit(main())
