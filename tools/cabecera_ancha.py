"""Pasa la medición de cabecera «a lo ancho» al formato que lee la calibración (spec 051).

Lee libros con una columna por alimentador (fecha y hora, hojas de activa y de reactiva) y
tablas de máximas mensuales por salida, y escribe en ``--salida`` un libro de cabecera por año
(una hoja por código: Fecha, kW, kVAR) y el libro de medidores. Cada empresa, sola: no se
mezcla con la medición de otra (051:RF-7).

Uso:
    python tools/cabecera_ancha.py --ancho <carpeta o libros> --alimentador W12882=NJA202 \
        --salida <carpeta del espacio>
    python tools/cabecera_ancha.py --mensual <libro> --alimentador L14243=R5 --salida <carpeta>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Medición de cabecera en libro ancho al formato de la '
                                            'calibración (spec 051)')
    p.add_argument('--ancho', nargs='*', default=[], help='Libros o carpetas con una columna por alimentador')
    p.add_argument('--mensual', nargs='*', default=[], help='Libros con máximas mensuales por salida')
    p.add_argument('--unidad', choices=('mw', 'kw'), help='Unidad de las máximas mensuales si la tabla no la dice')
    p.add_argument('--alimentador', nargs='+', required=True,
                   help='NOMBRE_EN_DIGSILENT=CODIGO_DE_LA_MEDICION (R205=R5); solo CODIGO si son iguales')
    p.add_argument('--fp', nargs='*', default=[],
                   help='CODIGO=FP para una medición sin reactiva (R5=0.98): la Q sale de ese FP (051:RF-11)')
    p.add_argument('--salida', required=True, help='Carpeta del espacio de trabajo donde escribir (nunca la de los datos de la distribuidora)')
    args = p.parse_args(argv)

    from igea_dgs.cabecera_ancha import Lectura, escribir, leer_ancho, leer_maximas_mensuales
    from igea_dgs.demanda_medida import DemandaError

    medidores = {}
    for par in args.alimentador:
        nombre, _, codigo = par.partition('=')
        medidores[nombre.strip()] = (codigo or nombre).strip()
    codigos = sorted(set(medidores.values()))
    if not args.ancho and not args.mensual:
        p.error('indique --ancho o --mensual')
    try:
        lectura = Lectura()
        if args.ancho:
            leer_ancho(args.ancho, codigos, lectura)
        if args.mensual:
            leer_maximas_mensuales(args.mensual, codigos, unidad=args.unidad, lectura=lectura)
        fps = {}
        for par in args.fp:
            codigo, _, valor = par.partition('=')
            try:
                fps[codigo.strip()] = float(valor.replace(',', '.'))
            except ValueError:
                p.error(f'--fp {par}: el factor de potencia va como CODIGO=0.98')
        escritos = escribir(lectura, args.salida, medidores, fps)
        for codigo, v in fps.items():
            # El aviso de RF-9 («no se supone ningún FP») ya no vale para este código: lo da el usuario.
            lectura.avisos = [a for a in lectura.avisos if not (a.startswith(f'{codigo}:') and '051:RF-9' in a)]
            lectura.avisos.append(f'{codigo}: sin reactiva medida; la Q sale del FP {v:g} que dio el usuario '
                                  '(051:RF-11).')
    except DemandaError as exc:
        print(f'ERROR: {exc}')
        return 2
    for aviso in dict.fromkeys(lectura.avisos):
        print(f'  aviso: {aviso}')
    for codigo in codigos:
        serie = lectura.series.get(codigo) or {}
        if not serie:
            print(f'  {codigo}: no aparece en ningún libro (051:RF-5).')
            continue
        t, (kw, kvar) = max(serie.items(), key=lambda x: x[1][0] if x[1][0] is not None else float('-inf'))
        print(f'  {codigo}: {len(serie)} registros de {min(serie):%Y-%m-%d} a {max(serie):%Y-%m-%d}; '
              f'máxima {kw:.0f} kW' + (f', {kvar:.0f} kVAR' if kvar is not None else ', sin kVAR')
              + f' el {t:%Y-%m-%d %H:%M}')
    for ruta in escritos:
        print(f'Escrito: {ruta}')
    return 0 if not lectura.faltan(codigos) else 1


if __name__ == '__main__':
    sys.exit(main())
