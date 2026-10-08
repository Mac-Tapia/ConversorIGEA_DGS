"""Línea base de DGS para comprobar que una reorganización no cambia ninguna salida.

Convierte todos los alimentadores de una entrega (uno por fichero y la red unida) por la
misma vía que ``igea-dgs convert --all`` y ``--unir``, y guarda el SHA-256 de cada DGS.
La prueba ``tests/test_linea_base_001.py`` regenera y compara contra este fichero.

Los parámetros van todos explícitos, sin valores por defecto del motor: la spec 002 quita
el CRS por defecto (EPSG:32718), y una línea base que dependiera de él cambiaría sola.

Los DGS salen de datos de la distribuidora: el JSON va a ``output/`` (ignorado por git) y
solo guarda hashes, nunca contenido.

Uso::

    python tools/linea_base_dgs.py --red RED.txt --loads CARGA.txt --equipment BD.txt
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / 'output' / 'linea_base_001.json'

PARAMETROS = {
    'schema_profile': 'pf21_dgs_1_8_4',
    'source_crs': 'EPSG:32718',
    'target_crs': 'EPSG:4326',
    'strict': True,
    'include_geography': True,
    'workers': 1,
    'aliases': None,
}


def _hashes_dgs(carpeta: Path) -> dict[str, str]:
    from igea_dgs.util import sha256_file

    return {p.relative_to(carpeta).as_posix(): sha256_file(p)
            for p in sorted(carpeta.rglob('*.dgs'))}


def huella_entradas(red: Path, loads: Path, equipment: Path) -> dict[str, str | None]:
    """Hash de lo que determina la salida además del código: entradas y catálogo."""
    from igea_dgs.reglas import catalogo_del_proyecto
    from igea_dgs.util import sha256_file

    catalogo = catalogo_del_proyecto()
    return {
        'red': sha256_file(red),
        'loads': sha256_file(loads),
        'equipment': sha256_file(equipment),
        'catalogo_proyecto': sha256_file(catalogo) if catalogo else None,
    }


def calcular(red: Path, loads: Path, equipment: Path, salida: Path) -> dict:
    """Convierte la entrega en ``salida`` y devuelve la línea base (sin escribirla)."""
    from igea_dgs.batch import convert_group, convert_selection
    from igea_dgs.dataset import CymdistDataset
    from igea_dgs.naming import feeder_short_name
    from igea_dgs.reglas import REGLAS_PROYECTO, catalogo_del_proyecto

    catalogo = catalogo_del_proyecto()
    p = PARAMETROS

    # Un dataset por conversión: preparar_dataset completa coordenadas y catálogo sobre
    # el propio dataset, y la red unida no debe partir de uno ya preparado por el lote.
    ds = CymdistDataset.from_files(red, loads, equipment)
    por_alimentador = salida / 'alimentadores'
    manifiesto = convert_selection(
        ds, None, por_alimentador, all_feeders=True, aliases=p['aliases'],
        strict=p['strict'], schema_profile=p['schema_profile'],
        include_geography=p['include_geography'], source_crs=p['source_crs'],
        target_crs=p['target_crs'], workers=p['workers'], reglas=REGLAS_PROYECTO,
        catalogo=catalogo,
    )

    ds = CymdistDataset.from_files(red, loads, equipment)
    selectores = [feeder_short_name(n) for n in ds.feeder_ids() if ds.feeders.get(n)]
    red_unida = salida / 'red_unida'
    grupo = convert_group(
        ds, selectores, red_unida, name='LINEA_BASE', aliases=p['aliases'],
        strict=p['strict'], schema_profile=p['schema_profile'],
        source_crs=p['source_crs'], target_crs=p['target_crs'],
        reglas=REGLAS_PROYECTO, catalogo=catalogo,
    )

    return {
        'spec': '001:RF-14',
        'parametros': {**p, 'reglas': asdict(REGLAS_PROYECTO)},
        'entradas': huella_entradas(red, loads, equipment),
        'resumen_lote': manifiesto['summary'],
        'estado_red_unida': grupo['status'],
        'dgs_alimentadores': _hashes_dgs(por_alimentador),
        'dgs_red_unida': _hashes_dgs(red_unida),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--red', type=Path, required=True)
    ap.add_argument('--loads', type=Path, required=True)
    ap.add_argument('--equipment', type=Path, required=True)
    ap.add_argument('--out', type=Path, default=DESTINO)
    args = ap.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix='igea-linea-base-') as tmp:
        base = calcular(args.red, args.loads, args.equipment, Path(tmp))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(base, indent=2, ensure_ascii=False, sort_keys=True),
                        encoding='utf-8')
    print(f"Línea base: {len(base['dgs_alimentadores'])} DGS de alimentador, "
          f"{len(base['dgs_red_unida'])} de red unida ({base['estado_red_unida']}); "
          f"lote {base['resumen_lote']}")
    print(f'Escrita en {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
