#!/usr/bin/env python3
"""Suggest BD_Equipo targets for unresolved CYMDIST line-type codes.

Requires the three TXT paths (or IGEA_TXT_DIR) so the real catalog is used.

  set PYTHONPATH=src
  python tools/suggest_line_type_aliases.py --red RED.txt --loads CARGA.txt --equipment BD_Equipo.txt
  python tools/suggest_line_type_aliases.py ... --write-draft config/line_type_aliases.draft.json
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

# Default codes seen missing in one historical export; override with --codes
DEFAULT_CODES = ('AA05001D', 'CU02502D', 'N203506D')


def _paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    if args.red and args.loads and args.equipment:
        return Path(args.red), Path(args.loads), Path(args.equipment)
    root = Path(args.txt_dir or os.environ.get('IGEA_TXT_DIR', ''))
    if not root.is_dir():
        raise SystemExit('Provide --red/--loads/--equipment or --txt-dir / IGEA_TXT_DIR')
    red = next(iter(sorted(root.glob('RED_*.txt'))), None)
    loads = next(iter(sorted(root.glob('CARGA_*.txt'))), None)
    equip = next(iter(sorted(root.glob('BD_Equipo*.txt'))), None)
    if not (red and loads and equip):
        raise SystemExit(f'Could not find RED/CARGA/BD_Equipo under {root}')
    return red, loads, equip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--red')
    parser.add_argument('--loads')
    parser.add_argument('--equipment')
    parser.add_argument('--txt-dir', help='Folder with RED_/CARGA_/BD_Equipo*.txt')
    parser.add_argument('--codes', default=','.join(DEFAULT_CODES))
    parser.add_argument('--write-draft', help='Write aliases JSON for unique suggestions')
    args = parser.parse_args(argv)

    red, loads, equip = _paths(args)
    ds = CymdistDataset.from_files(red, loads, equip)
    catalog: list[str] = []
    for table in ('LINE', 'CONCENTRIC NEUTRAL CABLE'):
        for row in ds.equipment_tables.get(table, ()):
            code = (row.get('ID') or '').strip()
            if code and code not in catalog:
                catalog.append(code)
    catalog.sort()

    codes = [c.strip() for c in args.codes.split(',') if c.strip()]
    draft: dict[str, str] = {}
    print(f'Catalog IDs: {len(catalog)}')
    print('=' * 72)
    for code in codes:
        suggestion = suggest_catalog_code(code, catalog)
        print(f'{code} -> {suggestion or "(ambiguous or none; converter will use DEFAULT)"}')
        if suggestion and suggestion != code:
            draft[code] = suggestion
    if args.write_draft:
        out = Path(args.write_draft)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(draft, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(f'Wrote {out} ({len(draft)} mappings)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
