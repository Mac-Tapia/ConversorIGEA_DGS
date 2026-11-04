#!/usr/bin/env python
"""Estadística de las órdenes de DIgSILENT: descriptiva, contraste entre versiones y fallos repetidos (081:RF-72 a RF-74).

    python tools/estadistica_ordenes.py [--desde 2026-11-02] [--guion obras_pf.py] [--corte 2026-11-03T20:35]
                                         [--alfa 0.05] [--json salida.json]

Con ``--corte``, A son las órdenes de antes y B las de después, y se contrasta H1 «B tarda menos y falla menos».
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE.parent / 'src'):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from convertersmartgrid import estadistica_ordenes as eo  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Estadística de las órdenes de DIgSILENT (081:RF-72 a RF-74)')
    p.add_argument('--cola', help='Carpeta de la cola de DIgSILENT (por defecto, la de esta máquina)')
    p.add_argument('--desde', default='', help='Fecha ISO desde la que contar')
    p.add_argument('--guion', default='', help='Solo las órdenes de este guion')
    p.add_argument('--corte', default='', help='Fecha ISO que separa la versión A (antes) de la B (después)')
    p.add_argument('--alfa', type=float, default=eo.ALFA, help='Nivel de significación')
    p.add_argument('--json', help='Escribe aquí el resumen en JSON')
    args = p.parse_args(argv)
    # La consola de Windows es cp1252: sin esto, «α» tumbaba el resumen al final (2026-11-03).
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if args.cola:
        cola = Path(args.cola)
    else:
        from convertersmartgrid import pf_arnes
        cola = pf_arnes.ruta_cola()
    filas = [f for f in eo.leer(cola) if f['fecha'] >= args.desde and (not args.guion or f['guion'] == args.guion)]
    if not filas:
        print('Sin órdenes en el periodo.')
        return 0
    horas = sum(float(f['segundos']) for f in filas) / 3600
    fallos = sum(1 for f in filas if int(f.get('codigo') or 0))
    print(f'{len(filas)} órdenes, {fallos} fallidas ({fallos / len(filas):.0%}), {horas:.1f} h de DIgSILENT')
    tabla = eo.descriptiva(filas)
    print(f"{'guion':30s} {'n':>5s} {'fallos':>7s} {'horas':>6s} {'mediana s':>9s} {'IC95 mediana':>15s} {'p90 s':>6s} {'máx s':>6s}")
    for r in tabla:
        lo, hi = r['ic95_mediana_s']
        print(f"{r['guion']:30s} {r['n']:5d} {r['tasa_fallos']:7.0%} {r['horas']:6.2f} {r['mediana_s']:9.0f} "
              f"{f'{lo:.0f}–{hi:.0f}':>15s} {r['p90_s']:6.0f} {r['max_s']:6.0f}")
    rep = eo.repetidos(filas)
    if rep:
        print('\nFallos que se repiten (081:RF-74):')
        for g, causa, n in rep[:15]:
            print(f'  {n}× {g}: {causa}')
    resumen: dict[str, Any] = {'ordenes': len(filas), 'fallos': fallos, 'horas': horas, 'por_guion': tabla,
               'repetidos': [list(x) for x in rep]}
    if args.corte:
        a = [f for f in filas if f['fecha'] < args.corte]
        b = [f for f in filas if f['fecha'] >= args.corte]
        c = resumen['contraste'] = eo.contrastar(a, b, args.alfa)
        d, fz = c['duracion'], c.get('fallos') or {}
        print(f"\nH1 (α={args.alfa}): B tarda menos y falla menos que A. A n={c['n_a']}, B n={c['n_b']}")
        print(f"  duración: mediana {c['mediana_a_s']} → {c['mediana_b_s']} s; "
              + (f"p={d['p']:.4f}, {'se demuestra' if d['demostrado'] else 'no se demuestra'}" if d['p'] is not None
                 else d['motivo']))
        if fz:
            print(f"  fallos: {c['tasa_fallos_a']:.0%} → {c['tasa_fallos_b']:.0%}; p={fz['p']:.4f}, "
                  f"{'se demuestra' if fz['demostrado'] else 'no se demuestra'}")
    if args.json:
        Path(args.json).write_text(json.dumps(resumen, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
