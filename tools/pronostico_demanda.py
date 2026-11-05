#!/usr/bin/env python
"""Dataset, backtest y competición de modelos de demanda de cabecera, clientes fijos y escaladas (spec 089).

Lee los libros de cada carpeta sin lista fija: un mes nuevo entra solo. ``--guardar-dataset`` deja el dataset limpio con su huella
y ``--dataset`` lo reabre sin volver a leer los libros. Sin ``--modelos``, compara los perfiles, sin GPU; con ``--modelos``, hace
competir a los candidatos en una clase y magnitud, por el turno de GPU si alguno la pide. No escribe en la calibración, el «Caso
base», los informes ni DIgSILENT.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
if str(REPO / 'src') not in sys.path:
    sys.path.insert(0, str(REPO / 'src'))


def _dataset(args, pd_):
    exogenas = pd_.leer_exogenas(args.exogenas) if args.exogenas else None
    if args.dataset:
        return pd_.abrir_dataset(args.dataset, exogenas)
    if not args.cabecera or not args.equivalencia:
        raise SystemExit('indique --dataset, o --cabecera y --equivalencia')
    dataset = pd_.armar_dataset(pd_.Fuentes(cabecera=args.cabecera, equivalencia=args.equivalencia, clientes=args.clientes, suministros=args.suministros,
                                            apoyo=args.apoyo, apoyo_clientes=args.apoyo_clientes, exogenas=args.exogenas))
    if args.guardar_dataset:
        dataset.huella = pd_.guardar_dataset(dataset, args.guardar_dataset)
        print(f'dataset {dataset.huella[:12]} en {args.guardar_dataset}', flush=True)
    return dataset


def _modelos(args, dataset, pd_):
    from convertersmartgrid.training_coordinator import exigir_memoria_ml
    from convertersmartgrid.trabajadores_ml import turno_gpu

    nombres = [x.strip() for x in args.modelos.split(',') if x.strip()]
    objetivos = [o for o in dataset.objetivos if o.clase == args.clase and o.magnitud == args.magnitud and o.curva]
    ajustes = {k: v for k, v in (('pasos', args.pasos), ('lote', args.lote), ('contexto_dias', args.contexto_dias)) if v}
    def correr():
        return pd_.backtest_modelos(objetivos, nombres, horizonte_dias=args.horizonte_dias or pd_.HORIZONTE_DIAS, origenes=args.origenes or pd_.ORIGENES_MODELOS,
                                    exogenas=dataset.exogenas, semilla=args.semilla, ajustes=ajustes, log=lambda m: print(m, flush=True))
    if set(nombres) & set(pd_.REDES):
        exigir_memoria_ml(3., minimo_commit_gib=6.)
        with turno_gpu('pronostico-demanda'):
            resultado = correr()
    else:
        resultado = correr()
    return {**resultado, 'clase': args.clase, 'magnitud': args.magnitud, 'huella_dataset': dataset.huella, 'ajustes': ajustes}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cabecera', type=Path, help='Carpeta o libro de la medición de cabecera')
    p.add_argument('--equivalencia', type=Path, help='Libro alimentador–medidor')
    p.add_argument('--clientes', type=Path, help='Carpeta de los libros de clientes fijos')
    p.add_argument('--suministros', type=Path, help='Libro o carpeta de suministros: alimentador y renumeración')
    p.add_argument('--apoyo', type=Path, help='Carpeta con cabecera de años anteriores, solo antes del primer dato de la base')
    p.add_argument('--apoyo-clientes', type=Path, help='Carpeta con clientes de años anteriores, con la misma regla')
    p.add_argument('--exogenas', type=Path, help='Carpeta con el calendario y la temperatura en CSV')
    p.add_argument('--guardar-dataset', type=Path, help='Carpeta donde dejar el dataset limpio con su huella')
    p.add_argument('--dataset', type=Path, help='Dataset ya guardado; no se leen los libros')
    p.add_argument('--modelos', help='Candidatos separados por coma: ' + 'nhits, nbeatsx, patchtst, tft, itransformer, timesnet, tide, tsmixerx, bitcn, gru, lightgbm')
    p.add_argument('--clase', choices=('cabecera', 'cliente', 'escaladas'), default='cabecera')
    p.add_argument('--magnitud', choices=('kW', 'kVAR'), default='kW')
    p.add_argument('--pasos', type=int, help='Pasos de entrenamiento de cada modelo')
    p.add_argument('--lote', type=int, help='Tamaño de lote de las redes')
    p.add_argument('--contexto-dias', type=int, help='Días de contexto de las redes')
    p.add_argument('--semilla', type=int, default=0)
    p.add_argument('--horizonte-dias', type=int, help='Horizonte del backtest')
    p.add_argument('--origenes', type=int, help='Orígenes del backtest; el último solo mide')
    p.add_argument('--emitir-dias', type=int, help='Días del pronóstico de perfiles que se emiten a un CSV')
    p.add_argument('--output-json', type=Path, required=True)
    args = p.parse_args(argv)

    from convertersmartgrid import pronostico_demanda as pd_
    from convertersmartgrid.trabajadores_ml import escribir_informe

    if args.output_json.exists():
        print('Informe existente conservado')
        return 2
    dataset = _dataset(args, pd_)
    if args.modelos:
        resultado = _modelos(args, dataset, pd_)
        escribir_informe(args.output_json, resultado)
        print(json.dumps({'status': resultado['status'], 'ganador': resultado['ganador'], 'motivo': resultado['motivo']}, ensure_ascii=True))
        return 0
    ajustes = {k: v for k, v in (('horizonte_dias', args.horizonte_dias), ('origenes', args.origenes)) if v}
    resultado = pd_.backtest(dataset, progreso=lambda i, n, nombre: i % 50 == 0 and print(f'{i}/{n} {nombre}', flush=True), **ajustes)
    if args.emitir_dias:
        destino = args.output_json.with_suffix('.csv')
        por_nombre = {r['objetivo']: r for r in resultado['resultados']}
        with destino.open('w', encoding='utf-8', newline='') as f:
            escritor = None
            for o in dataset.objetivos:
                for fila in pd_.pronosticar(o, por_nombre[o.nombre], dias=args.emitir_dias, exogenas=dataset.exogenas):
                    if escritor is None:
                        escritor = csv.DictWriter(f, fieldnames=list(fila))
                        escritor.writeheader()
                    escritor.writerow(fila)
        resultado['pronostico_csv'] = str(destino)
    escribir_informe(args.output_json, resultado)
    print(json.dumps({'status': resultado['status'], 'resumen': resultado['resumen']}, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
