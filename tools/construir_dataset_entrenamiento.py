#!/usr/bin/env python
"""Dataset de entrenamiento del asistente y del gemelo, y si está completo (043:RF-14, RF-15).

El constructor existía, pero ninguna orden lo lanzaba: el dataset quedó en el del 2026-10-25, anterior a
las specs 054 a 064, sin que nada lo dijera. Esta orden importa el historial de la web, construye las
particiones en una carpeta nueva (nunca pisa una anterior) y mide los umbrales de la spec 027: 200
órdenes reales y 10 episodios. Los registros sintéticos o de contexto no cuentan como reales. Los
episodios guardan su proyecto en ``sistema``: el mínimo se mide por proyecto y el informe lo dice así.

    python tools/construir_dataset_entrenamiento.py [--destino CARPETA] [--output-json INFORME.json]

Códigos de salida: 0 hecho, también si no está completo (lo dice el informe); 1 error.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / 'src') not in sys.path:
    sys.path.insert(0, str(_REPO / 'src'))

#: Umbrales de la spec 027 (RF-3, RF-19, RF-33).
ORDENES_REALES_MINIMAS = 200
EPISODIOS_POR_PROYECTO = 10


def veredicto(registros, *, ordenes_minimas: int = ORDENES_REALES_MINIMAS,
              episodios_minimos: int = EPISODIOS_POR_PROYECTO) -> dict:
    """Lo que falta para dar el dataset por completo; solo cuentan los datos reales revisados."""
    ordenes = sum(1 for r in registros if r.tipo == 'orden' and r.quality == 'gold_human')
    # Un episodio en cuarentena no entra en ninguna partición: no cuenta.
    por_proyecto = Counter(r.sistema or '(sin proyecto)' for r in registros
                           if r.tipo == 'episodio' and r.quality == 'gold_native')
    faltan = []
    if ordenes < ordenes_minimas:
        faltan.append(f'{ordenes_minimas - ordenes} órdenes reales revisadas ({ordenes} de {ordenes_minimas})')
    if not por_proyecto:
        faltan.append('episodios del gemelo: no hay ninguno')
    for proyecto, n in sorted(por_proyecto.items()):
        if n < episodios_minimos:
            faltan.append(f'{episodios_minimos - n} episodios de {proyecto} ({n} de {episodios_minimos})')
    return {'completo': not faltan, 'faltan': faltan, 'ordenes_reales': ordenes,
            'episodios_por_proyecto': dict(sorted(por_proyecto.items())),
            'calidades': dict(sorted(Counter(r.quality for r in registros).items()))}


def construir(raiz_web: Path, raiz_asistente: Path, raiz_gemelo: Path, destino: Path) -> dict:
    from convertersmartgrid.asistente.dataset_entrenamiento import (
        construir_dataset, escribir_particiones, importar_historial_web, particionar_dataset,
    )

    if destino.exists() and any(destino.iterdir()):
        raise ValueError(f'{destino} ya tiene contenido: el dataset anterior no se pisa.')
    historial = importar_historial_web(raiz_web, raiz_asistente / 'conversion_outbox')
    normativa = raiz_asistente / 'normativa'
    hecho = construir_dataset(raiz_asistente, raiz_gemelo,
                              raiz_normativa=normativa if normativa.is_dir() else None)
    manifiesto = escribir_particiones(particionar_dataset(hecho.registros), destino)
    return {'destino': str(destino), 'historial': historial, 'manifiesto_sha256': manifiesto['sha256'],
            'particiones': {k: v['count'] for k, v in manifiesto['partitions'].items()},
            **veredicto(hecho.registros)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Construye el dataset de entrenamiento y dice si está completo')
    p.add_argument('--destino', type=Path, help='Carpeta nueva; por defecto, dataset_<fecha> en el almacén')
    p.add_argument('--output-json', type=Path, help='Dónde dejar el informe')
    args = p.parse_args(argv)
    from convertersmartgrid.asistente import almacen
    from convertersmartgrid.digital_twin.buffer import raiz_buffer

    asistente = almacen.raiz()
    try:
        informe = construir(asistente.parent, asistente, raiz_buffer(),
                            args.destino or asistente / f'dataset_{date.today():%Y%m%d}')
    except (OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    texto = json.dumps(informe, indent=2, ensure_ascii=False, default=str)
    if args.output_json:
        args.output_json.write_text(texto + '\n', encoding='utf-8')
    print(texto)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
