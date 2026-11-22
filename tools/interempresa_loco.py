"""Deja una empresa fuera cada vez y dice si la conversión VNR o el pronóstico generalizan a otra empresa (spec 112).

Uso:
    python tools/interempresa_loco.py vnr --empresas CARPETA --salida INFORME.json [--umbral 0.9] [--tolerancia 0.1]
    python tools/interempresa_loco.py pronostico --empresas CARPETA --salida INFORME.json [--margen 0.1]
    python tools/interempresa_loco.py preparar-vnr --copia COPIA.bak --destino CARPETA_DE_LA_EMPRESA [--catalogo XLSX]

``CARPETA`` tiene una subcarpeta por empresa. Para ``vnr``, cada una con el trío TXT que saca
``vnr-etl convert <paquete> --format cymdist`` del paquete público de esa empresa (``tools/vnr_publico_empresa.py`` lo
baja bajo demanda, a una carpeta fuera del programa). Para ``pronostico``, cada una con un benchmark de series de
``tools/benchmark_anonimo.py`` (``series.csv`` y ``series_objetivos.csv``).

Para cada empresa se ajusta con las demás y se mide en ella: el catálogo de fichas de conductor en la conversión, la forma
semanal de la demanda en el pronóstico. Con menos de 3 empresas el veredicto es «NO DEMOSTRADA» y el informe dice por
qué. El informe JSON no lleva el nombre de ninguna empresa (``E1…En``). Solo lee; no necesita DIgSILENT ni GPU.

Códigos de salida: 0 «DEMOSTRADA»; 3 «NO DEMOSTRADA» (informe escrito); 1 error de uso o de lectura.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog='interempresa_loco',
                                description='Dejar una empresa fuera cada vez: conversión VNR y pronóstico (spec 112).')
    sub = p.add_subparsers(dest='tarea', required=True)
    s = sub.add_parser('preparar-vnr', help='restaura la copia de SQL Server de una empresa y deja su red_vnr.json')
    s.add_argument('--copia', type=Path, required=True, help='la copia .bak de la red (con su ConfigBD.config al lado)')
    s.add_argument('--destino', type=Path, required=True, help='la subcarpeta de esa empresa en la carpeta de empresas')
    s.add_argument('--catalogo', type=Path, default=None,
                   help='catálogo universal de fichas (por defecto, el del proyecto); solo se lee')
    for nombre, ayuda in (('vnr', 'catálogo de fichas de las demás frente a los conductores de la retenida'),
                          ('pronostico', 'forma semanal de las demás frente a la base propia de la retenida')):
        s = sub.add_parser(nombre, help=ayuda)
        s.add_argument('--empresas', type=Path, required=True, help='carpeta con una subcarpeta por empresa')
        s.add_argument('--salida', type=Path, required=True, help='informe JSON que se escribe')
        if nombre == 'vnr':
            s.add_argument('--umbral', type=float, default=None, help='parte de la longitud que tiene que acertar (0,9)')
            s.add_argument('--tolerancia', type=float, default=None, help='diferencia relativa admitida en R1, X1 y A (0,1)')
        else:
            s.add_argument('--margen', type=float, default=None, help='cuánto puede empeorar el WAPE frente a la base (0,1)')
    return p.parse_args(argv)


def preparar_vnr(copia: Path, destino: Path, catalogo: Path | None = None) -> int:
    """112:RF-22 y RF-23: la copia de SQL Server del paquete público de una empresa → su ``red_vnr.json`` (tramos y fichas
    del modelo canónico de ``cargar_copia``), sin exportar a CYMDIST. Las fichas que la copia no trae se resuelven con
    el catálogo universal (053) por el mismo camino que la conversión (``fichas_del_catalogo``), que solo lo lee."""
    from convertersmartgrid.adaptadores.benchmarks.interempresa import guardar_red, red_de_modelo
    from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr
    from convertersmartgrid.adaptadores.sources import vnr as fuente_vnr
    from convertersmartgrid.aplicacion.reglas import catalogo_del_proyecto

    if not copia.is_file():
        print(f'Error: no existe la copia {copia}', file=sys.stderr)
        return 1
    ruta_catalogo = catalogo or catalogo_del_proyecto()
    if ruta_catalogo is None or not Path(ruta_catalogo).is_file():
        print(f'Error: no está el catálogo de fichas ({ruta_catalogo}); páselo con --catalogo', file=sys.stderr)
        return 1
    modelo, avisos, alcance = sqlserver_vnr.cargar_copia(copia, vecinas=[copia.parent])
    red = red_de_modelo(modelo, resolver=lambda m: fuente_vnr.fichas_del_catalogo(m, Path(ruta_catalogo)))
    if not red.tramos:
        print(f'Error: la copia {copia.name} no da ningún tramo con conductor', file=sys.stderr)
        return 1
    ruta = guardar_red(red, destino)
    c = red.cobertura()
    print(f"{c['tramos']} tramos: {c['con_ficha_propia']} con ficha propia, {c['resueltos_catalogo']} resueltos por el "
          f"catálogo y {c['no_resueltos']} sin resolver ({len(avisos)} avisos de la carga): {ruta}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    if args.tarea == 'preparar-vnr':
        return preparar_vnr(args.copia, args.destino, args.catalogo)
    from convertersmartgrid.adaptadores.benchmarks.interempresa import (SinEmpresas, escribir_informe, evaluar_pronostico,
                                                                       evaluar_vnr)
    from convertersmartgrid.dominio.benchmarks.interempresa import DEMOSTRADA

    if not args.empresas.is_dir():
        print(f'Error: no existe la carpeta {args.empresas}', file=sys.stderr)
        return 1
    opciones = {k: v for k, v in vars(args).items() if k in ('umbral', 'tolerancia', 'margen') and v is not None}
    try:
        informe = (evaluar_vnr if args.tarea == 'vnr' else evaluar_pronostico)(args.empresas, **opciones)
    except (SinEmpresas, OSError, ValueError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
    ruta = escribir_informe(informe, args.salida)
    print(f'{informe["veredicto"]}: {informe["motivo"]}')
    print(f'Informe: {ruta}')
    return 0 if informe['veredicto'] == DEMOSTRADA else 3


if __name__ == '__main__':
    sys.exit(main())
