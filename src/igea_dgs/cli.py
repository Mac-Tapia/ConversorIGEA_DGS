from __future__ import annotations

import argparse
import json
from pathlib import Path

from .batch import convert_selection, load_aliases
from .dataset import CymdistDataset
from .naming import feeder_short_name, sort_key_feeder


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--red', required=True, help='IGEA/CYMDIST RED TXT export')
    parser.add_argument('--loads', required=True, help='IGEA/CYMDIST CARGA TXT export')
    parser.add_argument('--equipment', required=True, help='IGEA/CYMDIST BD_Equipo TXT export')


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Universal IGEA/CYMDIST TXT to DIgSILENT DGS converter')
    sub = parser.add_subparsers(dest='command', required=True)

    list_p = sub.add_parser('list', help='List feeders available in the TXT dataset')
    _common(list_p)

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
        for network_id in sorted(dataset.feeder_ids(), key=sort_key_feeder):
            name = feeder_short_name(network_id)
            source = dataset.sources.get(network_id, {})
            print(f'{name}\t{network_id}\t{source.get("DesiredVoltage", "")} kV\t{len(dataset.feeders[network_id])} sections')
        return 0

    selectors = list(args.feeder) + list(args.network)
    if args.all and selectors:
        raise SystemExit('--all cannot be combined with --feeder/--network')
    if not args.all and not selectors:
        raise SystemExit('Use --feeder/--network at least once, or use --all')

    try:
        aliases = load_aliases(args.aliases)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f'Error en aliases: {exc}') from exc

    def _progress(network_id: str, index: int, total: int) -> None:
        feeder = feeder_short_name(network_id)
        print(f'[{index}/{total}] {feeder}…', flush=True)

    try:
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
            on_progress=_progress,
        )
    except (OSError, ValueError, ImportError) as exc:
        raise SystemExit(f'Error de conversión: {exc}') from exc

    print(f"Requested: {manifest['summary']['requested']}")
    print(f"OK: {manifest['summary']['ok']}")
    print(f"Failed: {manifest['summary']['failed']}")
    print(f"Manifest: {Path(args.out_dir) / 'batch_manifest.json'}")
    return 0 if manifest['summary']['failed'] == 0 else 2


if __name__ == '__main__':
    raise SystemExit(main())
