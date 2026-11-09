#!/usr/bin/env python
"""Pronostica todos los años de un estudio del PIDE con el mejor modelo por métricas (spec 031).

Lee la medición de cabecera y los clientes una vez, o reabre un dataset guardado; sin Formato 01 de la empresa, lo construye con la
cabecera. Hace competir a los candidatos por clase y magnitud y escribe ``proyeccion.json`` y ``evaluacion.json`` con el formato que lee
``leer_proyeccion_anual``. Sin ``--aceptar``, la evaluación queda sin aceptar salvo que todo su horizonte esté validado. No escribe en la
calibración, el «Caso base» ni DIgSILENT.

Uso:
    python tools/proyeccion_anual.py --cabecera <carpeta> --equivalencia <libro> --clientes <carpeta> --suministros <libro> \\
        --alimentadores A,B --proyecto P --anio-base 2030 --anio-corto 4 --anio-fin 20 --empresa "Empresa" --salida <carpeta>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
if str(REPO / 'src') not in sys.path:
    sys.path.insert(0, str(REPO / 'src'))


def _lista(texto: str | None) -> list[str]:
    return [x.strip() for x in (texto or '').split(',') if x.strip()]


def _estructura(args):
    """Los alimentadores y sus sistemas de la estructura del perfil, sin nombres de empresa en el código."""
    if not args.perfil:
        return None
    from convertersmartgrid.estructura import estructura_de_perfil

    return estructura_de_perfil(json.loads(args.perfil.read_text(encoding='utf-8')), args.perfil.parent)


def _alimentadores(args, estructura) -> list[str]:
    pedidos = _lista(args.alimentadores)
    if args.zonal:
        if estructura is None:
            raise SystemExit('--zonal necesita --perfil, con la estructura de la empresa')
        sets = {k for k, v in estructura.sets.items() if v.zonal.casefold() == args.zonal.casefold()}
        pedidos += [a for a, fila in estructura.alimentadores.items() if fila.set_codigo in sets]
        if not pedidos:
            raise SystemExit(f'el zonal {args.zonal} no tiene alimentadores en la estructura')
    return list(dict.fromkeys(pedidos))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--cabecera', type=Path, action='append', help='Carpeta o libro de la medición de cabecera; se puede repetir')
    p.add_argument('--equivalencia', type=Path, help='Libro alimentador–medidor')
    p.add_argument('--clientes', type=Path, help='Carpeta de los libros de clientes')
    p.add_argument('--suministros', type=Path, help='Libro o carpeta de suministros')
    p.add_argument('--dataset', type=Path, help='Dataset guardado de la 089; no se leen los libros')
    p.add_argument('--perfil', type=Path, help='Perfil de la empresa con su estructura')
    p.add_argument('--zonal', help='Zonal de la estructura del perfil')
    p.add_argument('--alimentadores', help='Alimentadores separados por coma')
    p.add_argument('--empresa', help='Empresa del estudio: un Formato 01 de otra no se usa')
    p.add_argument('--formato-01', type=Path, help='Formato 01 de la propia empresa; sin él se construye con la cabecera')
    p.add_argument('--cargas', type=Path, help='JSON con [{carga, alimentador, potencia_kva, serie}]; sin él, una fila por objetivo')
    p.add_argument('--proyecto', required=True, help='Proyecto de DIgSILENT del estudio')
    p.add_argument('--anio-base', type=int, required=True, help='Año calendario del año 00 del estudio')
    p.add_argument('--anio-corto', type=int, required=True, help='Último año relativo del corto plazo')
    p.add_argument('--anio-fin', type=int, required=True, help='Último año relativo del horizonte')
    p.add_argument('--modelos', help='Modelos que también compiten: lightgbm, sin GPU, o las redes si hay GPU; lightgbm con una red en el mismo proceso abortó con el código 139 en una corrida real: en corridas separadas')
    p.add_argument('--pasos', type=int, help='Pasos de entrenamiento de cada modelo')
    p.add_argument('--paso-meses', type=int, default=1, help='Un origen cada tantos meses')
    p.add_argument('--semilla', type=int, default=0)
    p.add_argument('--aceptar', metavar='OPERADOR', help='Orden expresa del operador: acepta la proyección y queda escrito quién y cuánto falta por validar')
    p.add_argument('--motivo-aceptar', default='', help='Motivo de la orden de aceptar')
    p.add_argument('--fecha-aceptar', default='', help='Fecha de la orden de aceptar')
    p.add_argument('--salida', type=Path, required=True, help='Carpeta de salida')
    args = p.parse_args(argv)

    from convertersmartgrid import proyeccion_anual as pa
    from convertersmartgrid.pronostico_demanda import Fuentes, abrir_dataset

    estructura = _estructura(args)
    feeders = _alimentadores(args, estructura)
    sistema_de = {a: fila.sistema for a in feeders if estructura is not None and (fila := estructura.alimentador(a)) is not None and fila.sistema}
    sistemas = {} if estructura is None else {k: {'nombre': v.nombre, 'sector': v.sector} for k, v in estructura.sistemas.items()}
    dataset = abrir_dataset(args.dataset) if args.dataset else None
    if dataset is None and (not args.cabecera or not args.equivalencia):
        raise SystemExit('indique --dataset, o --cabecera y --equivalencia')
    if dataset is not None and feeders:
        pedidos = set(feeders)
        dataset.objetivos = [o for o in dataset.objetivos if (o.fuente.get('alimentador') or o.ident) in pedidos]
    fuentes = None if dataset is not None else Fuentes(cabecera=args.cabecera, equivalencia=args.equivalencia, clientes=args.clientes, suministros=args.suministros,
                                                       alimentadores=feeders or None)
    cargas = None
    if args.cargas:
        cargas = [pa.Carga(c['carga'], c['alimentador'], c.get('potencia_kva'), c.get('serie')) for c in json.loads(args.cargas.read_text(encoding='utf-8'))]
    orden = {'operador': args.aceptar, 'motivo': args.motivo_aceptar, 'fecha': args.fecha_aceptar} if args.aceptar else None
    ajustes = {'pasos': args.pasos} if args.pasos else None
    hecho = pa.pronosticar_estudio(fuentes, carpeta=args.salida, proyecto=args.proyecto, anio_base=args.anio_base, anio_corto=args.anio_corto, anio_fin=args.anio_fin,
                                   empresa=args.empresa, sistema_de=sistema_de, sistemas=sistemas, formato_01=args.formato_01, cargas=cargas, modelos=_lista(args.modelos),
                                   semilla=args.semilla, paso_meses=args.paso_meses, ajustes=ajustes, orden=orden, dataset=dataset, log=lambda m: print(m, flush=True))
    print(json.dumps(hecho['referencia'], ensure_ascii=True))
    evaluacion = hecho.get('evaluacion')
    if evaluacion:
        print(json.dumps({k: evaluacion[k] for k in ('estado', 'ganadores', 'horizonte_anios', 'horizonte_validado_anios', 'horizonte_validado_meses')}, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
