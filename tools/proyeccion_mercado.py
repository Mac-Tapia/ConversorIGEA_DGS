#!/usr/bin/env python
"""Compara métodos de proyección anual contra lo ocurrido, con la historia del Formato 01 (spec 072).

Corta la historia de cada sistema en varios años, pronostica sin ver lo siguiente y mide el error. Solo
lee el libro; no calibra ni escribe en DIgSILENT.

Uso:
    python tools/proyeccion_mercado.py --formato-01 <libro.xlsx> --horizonte 4 --salida <json>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Compara métodos de proyección anual contra lo ocurrido (spec 072).')
    p.add_argument('--formato-01', type=Path, required=True, help='Libro con las hojas del Formato 01')
    p.add_argument('--horizonte', type=int, default=4, help='Años que se pronostican desde cada corte')
    p.add_argument('--salida', type=Path, help='JSON con el resultado')
    args = p.parse_args(argv)

    from convertersmartgrid.proyeccion_mercado import MercadoError, comparar_metodos, leer_formato_01

    try:
        r = comparar_metodos(leer_formato_01(args.formato_01), horizonte=args.horizonte)
    except MercadoError as exc:
        print(f'ERROR: {exc}')
        return 2
    print(f"{r['sistemas']} sistemas, {r['perfiles']} perfiles distintos, horizonte {r['horizonte']} años; "
          'mediana de error y perfiles en que gana:')
    for metodo, error in sorted(r['mediana_error_pct'].items(), key=lambda x: x[1]):
        print(f"  {metodo}: {error:.2f} %, gana en {r['victorias'][metodo]}")
    print(f"Ganador: {r['ganador']} (referencia: {r['referencia']})")
    if args.salida:
        args.salida.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
