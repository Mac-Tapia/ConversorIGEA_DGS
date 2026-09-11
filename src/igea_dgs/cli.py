from __future__ import annotations

import argparse
import json
from pathlib import Path

from .batch import convert_selection, load_aliases
from .dataset import CymdistDataset
from .inventory import build_dataset_inventory, format_inventory_report, write_inventory
from .naming import feeder_short_name, sort_key_feeder


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--red', required=True, help='IGEA/CYMDIST RED TXT export')
    parser.add_argument('--loads', required=True, help='IGEA/CYMDIST CARGA TXT export')
    parser.add_argument('--equipment', required=True, help='IGEA/CYMDIST BD_Equipo TXT export')


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Universal IGEA/CYMDIST TXT to DIgSILENT DGS converter')
    sub = parser.add_subparsers(dest='command', required=True)

    list_p = sub.add_parser('list', help='List feeders and print deep TXT inventory')
    _common(list_p)
    list_p.add_argument(
        '--inventory-json',
        help='Optional path to write dataset_inventory.json',
    )

    conv = sub.add_parser('convert', help='Convert one, several, or all feeders')
    _common(conv)
    conv.add_argument('--feeder', action='append', default=[], help='Short feeder name; repeat for several feeders')
    conv.add_argument('--network', action='append', default=[], help='Full NetworkID; repeat for several feeders')
    conv.add_argument('--all', action='store_true', help='Convert every feeder independently')
    conv.add_argument('--out-dir', required=True)
    conv.add_argument('--aliases', help='Optional JSON string->string line-type aliases (applied before catalog auto-map)')
    conv.add_argument('--schema-profile', default='pf21_dgs_1_8_4')
    conv.add_argument('--source-crs', default='EPSG:32718', help='CRS of CoordX/CoordY in the loaded TXT (any EPSG; example EPSG:32718)')
    conv.add_argument('--target-crs', default='EPSG:4326', help='Target geographic CRS for GPSlat/GPSlon')
    conv.add_argument('--no-geography', action='store_true', help='Disable GPS/diagram generation')
    conv.add_argument('--non-strict', action='store_true', help='Omit unsupported topology/load/switch rows instead of failing; line types always auto-resolve')
    conv.add_argument('--export-xlsx', action='store_true', help='Also write multi-sheet Excel (.xlsx) from DGS tables (needs igea-dgs[xlsx])')
    conv.add_argument('--export-tsv', action='store_true', help='Also write one TSV per DGS table under {feeder}_dgs_tables/')
    conv.add_argument('--preview', action='store_true', help='Write interactive map HTML (+ GeoJSON) before DGS (requires geography)')
    conv.add_argument(
        '--preview-backend',
        default='auto',
        choices=('auto', 'leafmap', 'leaflet'),
        help='Map renderer: leafmap (@opengeos) or Leaflet CDN fallback',
    )

    sub.add_parser('gui', help='Open the graphical interface for selecting TXT inputs and converting')
    return parser


def _require_input_files(red: str, loads: str, equipment: str) -> None:
    missing = []
    for label, path in (('RED', red), ('CARGA', loads), ('BD_Equipo', equipment)):
        if not Path(path).is_file():
            missing.append(f'{label}: {path}')
    if missing:
        raise SystemExit('Archivos de entrada no encontrados:\n  - ' + '\n  - '.join(missing))


def main(argv=None) -> int:
    args = _parser().parse_args(argv)

    if args.command == 'gui':
        from .gui import main as gui_main
        return gui_main()

    try:
        _require_input_files(args.red, args.loads, args.equipment)
        dataset = CymdistDataset.from_files(args.red, args.loads, args.equipment)
    except SystemExit:
        raise
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit(f'Error al leer TXT: {exc}') from exc

    if args.command == 'list':
        inventory = build_dataset_inventory(dataset)
        print(format_inventory_report(inventory))
        if args.inventory_json:
            path = write_inventory(inventory, args.inventory_json)
            print(f'Inventory JSON: {path}')
        return 0 if inventory['integrity']['errors'] == 0 else 2

    selectors = list(args.feeder) + list(args.network)
    if args.all and selectors:
        raise SystemExit('--all cannot be combined with --feeder/--network')
    if not args.all and not selectors:
        raise SystemExit('Use --feeder/--network at least once, or use --all')

    try:
        aliases = load_aliases(args.aliases)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f'Error en aliases: {exc}') from exc

    if args.preview and args.no_geography:
        raise SystemExit('--preview requiere geografía; no combine con --no-geography')

    def _progress(network_id: str, index: int, total: int) -> None:
        feeder = feeder_short_name(network_id)
        print(f'[{index}/{total}] {feeder}…', flush=True)

    try:
        # Persist inventory alongside conversion outputs for auditability.
        inventory = build_dataset_inventory(dataset)
        write_inventory(inventory, Path(args.out_dir) / 'dataset_inventory.json')
        print(format_inventory_report(inventory))
        print(
            f"Conversión planificada: {inventory['conversion']['expected_dgs_files']} "
            f"DGS de {inventory['totals']['feeders']} alimentadores leídos.",
            flush=True,
        )
        manifest = convert_selection(
            dataset,
            selectors if not args.all else None,
            args.out_dir,
            all_feeders=args.all,
            aliases=aliases,
            strict=not args.non_strict,
            schema_profile=args.schema_profile,
            include_geography=not args.no_geography,
            source_crs=args.source_crs,
            target_crs=args.target_crs,
            export_xlsx=args.export_xlsx,
            export_tsv=args.export_tsv,
            write_preview=args.preview,
            preview_backend=args.preview_backend,
            on_progress=_progress,
        )
    except (OSError, ValueError, ImportError) as exc:
        raise SystemExit(f'Error de conversión: {exc}') from exc

    print(f"Requested: {manifest['summary']['requested']}")
    print(f"OK: {manifest['summary']['ok']}")
    print(f"Skipped: {manifest['summary'].get('skipped', 0)}")
    print(f"Failed: {manifest['summary']['failed']}")
    print(f"Manifest: {Path(args.out_dir) / 'batch_manifest.json'}")
    return 0 if manifest['summary']['failed'] == 0 else 2


if __name__ == '__main__':
    raise SystemExit(main())
