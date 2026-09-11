from __future__ import annotations

import argparse
from pathlib import Path

from .batch import convert_selection, load_aliases
from .dataset import CymdistDataset


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
    conv.add_argument('--aliases', help='External JSON mapping for explicitly approved line-type aliases')
    conv.add_argument('--schema-profile', default='pf21_dgs_1_8_4')
    conv.add_argument('--source-crs', default='EPSG:32718', help='CRS of CoordX/CoordY, e.g. EPSG:32718')
    conv.add_argument('--target-crs', default='EPSG:4326', help='Target geographic CRS for GPSlat/GPSlon')
    conv.add_argument('--no-geography', action='store_true', help='Disable GPS/diagram generation')
    conv.add_argument('--non-strict', action='store_true', help='Allow unsupported/unresolved records to be omitted; not recommended for production studies')

    sub.add_parser('gui', help='Open the graphical interface for selecting TXT inputs and converting')
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)

    if args.command == 'gui':
        from .gui import main as gui_main
        return gui_main()

    dataset = CymdistDataset.from_files(args.red, args.loads, args.equipment)

    if args.command == 'list':
        for network_id in sorted(dataset.feeder_ids(), key=lambda x: x.rsplit('_', 1)[-1]):
            name = network_id.rsplit('_', 1)[-1]
            source = dataset.sources.get(network_id, {})
            print(f'{name}\t{network_id}\t{source.get("DesiredVoltage", "")} kV\t{len(dataset.feeders[network_id])} sections')
        return 0

    selectors = list(args.feeder) + list(args.network)
    if args.all and selectors:
        raise SystemExit('--all cannot be combined with --feeder/--network')
    if not args.all and not selectors:
        raise SystemExit('Use --feeder/--network at least once, or use --all')
    aliases = load_aliases(args.aliases)
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
    )
    print(f"Requested: {manifest['summary']['requested']}")
    print(f"OK: {manifest['summary']['ok']}")
    print(f"Failed: {manifest['summary']['failed']}")
    print(f"Manifest: {Path(args.out_dir) / 'batch_manifest.json'}")
    return 0 if manifest['summary']['failed'] == 0 else 2


if __name__ == '__main__':
    raise SystemExit(main())
