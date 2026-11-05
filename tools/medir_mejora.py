#!/usr/bin/env python
"""Cuánto mejora una versión o un método de «Con proyecto»: registrar una corrida y comparar dos (spec 087, RF-21 a RF-27).

    python tools/medir_mejora.py registrar --trabajo trabajo.json --sistema NOMBRE --metodo escalera --revision 18e5bc66 \\
        [--desde 2026-11-04T06:05:00] [--junit pytest.xml]
    python tools/medir_mejora.py comparar --sistema NOMBRE --campo metodo --a escalera --b oraculo [--json salida.json]

``registrar`` añade la fila de un trabajo ya terminado, leído de la API (``GET /api/jobs/<id>``); cada «Con proyecto» de la web la añade solo.
``comparar`` da la diferencia de cada medida y, con al menos 5 corridas por grupo, el contraste de hipótesis.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE.parent / 'src'):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from convertersmartgrid import estadistica_ordenes as eo  # noqa: E402
from convertersmartgrid import medicion_obras as mo  # noqa: E402
from convertersmartgrid.perfil_empresa import completar_planeamiento, datos_perfil  # noqa: E402


def _ruta(args) -> Path:
    if args.registro:
        return Path(args.registro)
    from convertersmartgrid import pf_arnes

    return pf_arnes.ruta_cola().parent / mo.REGISTRO


def registrar(args) -> int:
    trabajo = json.loads(Path(args.trabajo).read_text(encoding='utf-8'))
    inicio, fin = trabajo.get('started_at'), trabajo.get('finished_at')
    desde = args.desde or (time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(inicio)) if inicio else '')
    hasta = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(fin)) if fin else '9999'
    if args.cola:
        cola = Path(args.cola)
    else:
        from convertersmartgrid import pf_arnes
        cola = pf_arnes.ruta_cola()
    ordenes = [o for o in eo.leer(cola) if desde <= o['fecha'] <= hasta]
    perfil = completar_planeamiento(datos_perfil())[0]
    lim, esc = perfil['estudios'], perfil['escalera']
    fila = mo.fila_de_corrida(
        sistema=args.sistema, revision=args.revision, metodo=args.metodo, estado=str(trabajo.get('status')), fecha=desde,
        resultado=trabajo.get('result') or {}, tiempo_s=(fin - inicio) if inicio and fin else 0.0, ordenes=ordenes,
        tension_min=float(lim['tension_min_pu']), tension_max=float(lim['tension_max_pu']),
        carga_max=float(esc.get('cargabilidad_planeamiento_pct') or lim['cargabilidad_max_pct']),
        secciones=tuple(esc.get('secciones_normalizadas') or ()),
        pruebas=mo.pruebas_de_junit(args.junit) if args.junit else None)
    mo.anadir(_ruta(args), fila)
    print(json.dumps(fila, ensure_ascii=False, indent=1, default=str))
    return 0


def comparar(args) -> int:
    r = mo.comparar(mo.leer(_ruta(args)), args.sistema, args.campo, args.a, args.b)
    print(f"{args.sistema}: {args.campo} {args.a} (A, {r['corridas_a']} corridas) frente a {args.b} (B, {r['corridas_b']} corridas)")
    print(f"{'medida':18s} {'A':>12s} {'B':>12s} {'diferencia':>12s} {'%':>8s}")
    for m, d in r['medidas'].items():
        fila = [('—' if d[k] is None else f'{d[k]:.2f}') for k in ('a', 'b', 'diferencia', 'porcentaje')]
        print(f'{m:18s} {fila[0]:>12s} {fila[1]:>12s} {fila[2]:>12s} {fila[3]:>8s}')
    print('Normas (cumplen / no cumplen / sin dato):')
    for n, g in r['normas'].items():
        print(f"  {n:20s} A {g['a']['cumplen']}/{g['a']['no_cumplen']}/{g['a']['sin_dato']}   B {g['b']['cumplen']}/{g['b']['no_cumplen']}/{g['b']['sin_dato']}")
    print(r['motivo'] if r['contraste'] is None else f"Contraste: {json.dumps(r['contraste'], ensure_ascii=False)}")
    if args.json:
        Path(args.json).write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    return 0


def main(argv=None) -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    p = argparse.ArgumentParser(description='Cuánto mejora una versión o un método de «Con proyecto» (087:RF-21 a RF-27)')
    p.add_argument('--registro', help='Fichero de corridas (por defecto, el de esta máquina)')
    sub = p.add_subparsers(dest='orden', required=True)
    r = sub.add_parser('registrar', help='Añade la fila de un trabajo terminado')
    r.add_argument('--trabajo', required=True, help='JSON del trabajo, de GET /api/jobs/<id>')
    r.add_argument('--sistema', required=True)
    r.add_argument('--metodo', required=True, help='escalera u oraculo')
    r.add_argument('--revision', required=True, help='Commit del código de la corrida')
    r.add_argument('--desde', help='Fecha ISO desde la que contar las órdenes de DIgSILENT')
    r.add_argument('--cola', help='Carpeta de la cola de DIgSILENT')
    r.add_argument('--junit', help='Informe JUnit de pytest de esa revisión')
    r.set_defaults(accion=registrar)
    c = sub.add_parser('comparar', help='B frente a A en un mismo sistema')
    c.add_argument('--sistema', required=True)
    c.add_argument('--campo', default='metodo', help='metodo o revision')
    c.add_argument('--a', required=True)
    c.add_argument('--b', required=True)
    c.add_argument('--json', help='Escribe aquí el resultado')
    c.set_defaults(accion=comparar)
    args = p.parse_args(argv)
    return args.accion(args)


if __name__ == '__main__':
    raise SystemExit(main())
