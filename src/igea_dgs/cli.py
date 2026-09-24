from __future__ import annotations

import argparse
import json
from pathlib import Path

from .batch import convert_selection, load_aliases
from .dataset import CymdistDataset
from .inventory import build_dataset_inventory, format_inventory_report, write_inventory
from .naming import feeder_short_name, sort_key_feeder


def _common(parser: argparse.ArgumentParser) -> None:
    """Las dos alternativas de entrada: tres TXT, o una base Access de CYMDIST."""
    src = parser.add_argument_group(
        'entrada (elija UNA alternativa)',
        'Alternativa 1 — ficheros TXT: --red --loads --equipment (no requiere CYMDIST '
        'ni driver). Alternativa 2 — base de datos Access de CYMDIST: --mdb '
        '(requiere Windows, el driver Microsoft Access y igea-dgs[access]).',
    )
    src.add_argument('--red', help='Alternativa 1: export TXT RED de IGEA/CYMDIST')
    src.add_argument('--loads', help='Alternativa 1: export TXT CARGA de IGEA/CYMDIST')
    src.add_argument('--equipment', help='Alternativa 1: export TXT BD_Equipo de IGEA/CYMDIST')
    src.add_argument('--mdb', help='Alternativa 2: base de datos de red CYMDIST (.mdb)')
    src.add_argument(
        '--equipment-mdb',
        help='Alternativa 2: base con el catálogo de equipos, si no está en --mdb',
    )
    src.add_argument(
        '--load-year', type=int,
        help='Alternativa 2: año del escenario de carga (por defecto, el más reciente '
             'de cada dispositivo, como hace el export TXT)',
    )
    src.add_argument(
        '--study',
        help='Opcional: estudio o proyecto CYMDIST (.zxst/.xst). Limita la conversión a '
             'los alimentadores que el estudio incluye',
    )


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
    conv.add_argument(
        '--catalogo', nargs='?', const='', metavar='XLSX',
        help=('Corregir las características eléctricas con el catálogo de fichas antes '
              'de escribir el DGS. Sin valor usa input/catalogo_parametros.xlsx. La '
              'identidad de cada elemento (código, material, sección) se conserva.'))
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


def load_dataset(args) -> CymdistDataset:
    """Resuelve la entrada elegida y devuelve el dataset, igual por las dos vías."""
    txt_given = any((args.red, args.loads, args.equipment))
    mdb_given = bool(args.mdb)

    if txt_given and mdb_given:
        raise SystemExit(
            'Elija UNA alternativa de entrada: los tres TXT (--red --loads --equipment) '
            'o la base Access (--mdb), no ambas.'
        )
    if not txt_given and not mdb_given:
        raise SystemExit(
            'Falta la entrada. Alternativa 1: --red --loads --equipment. '
            'Alternativa 2: --mdb  (opcionalmente --equipment-mdb, --load-year, --study).'
        )

    networks = None
    if args.study:
        from .study import StudyReadError, describe

        try:
            info = describe(args.study)
        except StudyReadError as exc:
            raise SystemExit(f'Error en el estudio: {exc}') from exc
        networks = info['networks']
        print(f"Estudio «{info['study_name']}»: {info['network_count']} alimentadores.")

    if mdb_given:
        from .access import AccessReadError, read_access_dataset

        try:
            dataset = read_access_dataset(
                args.mdb,
                equipment_db=args.equipment_mdb,
                load_year=args.load_year,
                networks=networks,
            )
        except AccessReadError as exc:
            raise SystemExit(f'Error al leer la base Access: {exc}') from exc
        print(f'Entrada: base de datos CYMDIST {Path(args.mdb).name}')
        return dataset

    if not (args.red and args.loads and args.equipment):
        raise SystemExit(
            'La entrada por TXT necesita los tres ficheros: --red, --loads y --equipment.'
        )
    try:
        _require_input_files(args.red, args.loads, args.equipment)
        dataset = CymdistDataset.from_files(args.red, args.loads, args.equipment)
    except SystemExit:
        raise
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit(f'Error al leer TXT: {exc}') from exc
    print(f'Entrada: TXT {Path(args.red).name} / {Path(args.loads).name} / {Path(args.equipment).name}')
    if networks is not None and hasattr(args, 'network'):
        # Con TXT el estudio no filtra la lectura, porque el TXT ya viene completo;
        # se aplica como selección de alimentadores.
        wanted = set(networks)
        inside = [n for n in dataset.feeder_ids() if n in wanted]
        outside = len(dataset.feeder_ids()) - len(inside)
        if outside:
            print(f'Estudio: se omitirán {outside} alimentadores fuera del estudio.')
        args.network = list(args.network) + inside
        args.all = False
    return dataset


def main(argv=None) -> int:
    args = _parser().parse_args(argv)

    if args.command == 'gui':
        from .gui import main as gui_main
        return gui_main()

    dataset = load_dataset(args)

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
        correcciones_catalogo = None
        if args.catalogo is not None:
            from .catalog import CATALOG_FILENAME, CatalogError, input_dir, leer_catalogo

            ruta = Path(args.catalogo) if args.catalogo else (
                input_dir('.') / CATALOG_FILENAME)
            try:
                correcciones_catalogo = leer_catalogo(ruta)
            except CatalogError as exc:
                raise SystemExit(f'Catálogo: {exc}') from exc
            print(f'Catálogo: {ruta} — {len(correcciones_catalogo)} tipo(s) con valor '
                  f'de ficha aplicable.', flush=True)

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
            catalog_corrections=correcciones_catalogo,
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
