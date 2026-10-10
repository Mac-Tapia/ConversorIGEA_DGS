#!/usr/bin/env python3
"""Propone alias para los tipos de línea del RED que no están en el catálogo BD_Equipo.

Para cada código de tramo (``LineCableID``) sin ficha en el catálogo, busca el código
del catálogo más parecido (prefijo común y distancia de edición) y, si es único, lo
propone. El borrador se revisa a mano antes de usarlo: el modo estricto no inventa
tipos (constitución P4) y un alias equivocado cambia la impedancia sin avisar.

    python tools/suggest_line_type_aliases.py --red RED.txt --loads CARGA.txt --equipment BD.txt
    python tools/suggest_line_type_aliases.py --txt-dir CARPETA [--codes A,B] \\
        [--write-draft config/line_type_aliases.draft.json]

Sin ``--codes`` toma todos los códigos del RED que faltan en el catálogo. Antes traía
fijos tres códigos de una exportación de Electro Dunas (spec 009, RF-8).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from igea_dgs.dataset import CymdistDataset  # noqa: E402
from igea_dgs.model import suggest_catalog_code  # noqa: E402


def _paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    if args.red and args.loads and args.equipment:
        return Path(args.red), Path(args.loads), Path(args.equipment)
    root = Path(args.txt_dir or os.environ.get('IGEA_TXT_DIR', ''))
    if not root.is_dir():
        raise SystemExit('Indique --red, --loads y --equipment, o --txt-dir (o IGEA_TXT_DIR).')
    red = next(iter(sorted(root.glob('RED_*.txt'))), None)
    loads = next(iter(sorted(root.glob('CARGA_*.txt'))), None)
    equip = next(iter(sorted(root.glob('BD_Equipo*.txt'))), None)
    if not (red and loads and equip):
        raise SystemExit(f'No se encuentran RED_, CARGA_ y BD_Equipo en {root}.')
    return red, loads, equip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Alias propuestos para tipos de línea sin ficha')
    parser.add_argument('--red')
    parser.add_argument('--loads')
    parser.add_argument('--equipment')
    parser.add_argument('--txt-dir', help='Carpeta con RED_*, CARGA_* y BD_Equipo*.txt')
    parser.add_argument('--codes', default='', help='Códigos separados por comas; sin ellos, los que faltan')
    parser.add_argument('--write-draft', help='JSON de alias con las propuestas únicas')
    args = parser.parse_args(argv)

    red, loads, equip = _paths(args)
    ds = CymdistDataset.from_files(red, loads, equip)
    catalog = sorted({(row.get('ID') or '').strip()
                      for table in ('LINE', 'CONCENTRIC NEUTRAL CABLE')
                      for row in ds.equipment_tables.get(table, ())} - {''})
    if args.codes.strip():
        codes = [c.strip() for c in args.codes.split(',') if c.strip()]
    else:
        en_red = {(cfg.get('LineCableID') or '').strip() for cfg in ds.line_configurations.values()}
        codes = sorted(en_red - set(catalog) - {''})

    draft: dict[str, str] = {}
    print(f'Códigos en el catálogo: {len(catalog)} · sin ficha: {len(codes)}')
    print('=' * 72)
    for code in codes:
        suggestion = suggest_catalog_code(code, catalog)
        print(f'{code} -> {suggestion or "(ninguno o ambiguo: el modo estricto lo informa como sin resolver)"}')
        if suggestion and suggestion != code:
            draft[code] = suggestion
    if args.write_draft:
        out = Path(args.write_draft)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(draft, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(f'Escrito {out} ({len(draft)} alias)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
