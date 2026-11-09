#!/usr/bin/env python
"""Un dataset v2 único para las familias de lenguaje, desde varios datasets v2 ya construidos (050:RF-24).

Une sus registros con los lectores y el particionador existentes y escribe en una carpeta nueva. Un registro que
cambiara de partición, o una prueba humana que dejara de serlo, bloquea: unir no puede mover reservas.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
if str(REPO / 'src') not in sys.path:
    sys.path.insert(0, str(REPO / 'src'))


def unir(origenes: list[Path], destino: Path) -> dict:
    from convertersmartgrid.asistente.dataset_entrenamiento import (
        RegistroEntrenamiento, escribir_particiones, particionar_dataset)
    from convertersmartgrid.trabajadores_ml import leer_dataset_v2
    if destino.exists() and any(destino.iterdir()):
        raise ValueError(f'{destino}: el dataset anterior no se pisa')
    registros: dict[str, RegistroEntrenamiento] = {}
    lugares: dict[str, str] = {}
    manifiestos = {}
    for origen in origenes:
        partes, manifiesto = leer_dataset_v2(origen)
        manifiestos[str(origen)] = manifiesto['sha256']
        for parte, filas in partes.items():
            for fila in filas:
                registro = RegistroEntrenamiento(**fila)
                previo = lugares.setdefault(registro.record_id, parte)
                if previo != parte:
                    raise ValueError(f'{registro.record_id}: en {previo} y en {parte} según el dataset de origen')
                registros[registro.record_id] = registro
    nuevas = particionar_dataset(tuple(registros.values()))
    movidos = [(r.record_id, r.quality, lugares[r.record_id], p) for p, filas in nuevas.items() for r in filas
               if lugares[r.record_id] != p]
    if movidos:
        cuenta = Counter((q, a, b) for _, q, a, b in movidos)
        raise ValueError(f'unir movería {len(movidos)} registros de partición: {dict(cuenta)}')
    manifiesto = escribir_particiones(nuevas, destino)
    releidas, _ = leer_dataset_v2(destino)
    return {'destino': str(destino), 'sha256': manifiesto['sha256'], 'origenes': manifiestos,
            'particiones': {p: dict(Counter(f"{f['tipo']}/{f['quality']}" for f in filas)) for p, filas in releidas.items()},
            'particiones_conservadas': True}


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument('--origen', type=Path, action='append', required=True, help='Dataset v2; repetible')
    a.add_argument('--destino', type=Path, required=True, help='Carpeta nueva, fuera de git')
    args = a.parse_args(argv)
    try:
        informe = unir(args.origen, args.destino)
    except (OSError, ValueError, TypeError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(informe, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
