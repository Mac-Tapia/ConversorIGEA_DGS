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
    src.add_argument(
        '--equipment-extra', action='append', default=[], metavar='TXT',
        help=('Completar el catálogo con otro BD_Equipo cuando el de la entrega '
              'llega incompleto. Solo rellena los códigos que faltan; lo cargado '
              'nunca se sobrescribe. Repetible.'))
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
    parser = argparse.ArgumentParser(
        prog='igea-dgs',
        description='Conversor universal IGEA/CYMDIST (TXT o Access) a DGS de DIgSILENT PowerFactory',
    )
    sub = parser.add_subparsers(dest='command', required=True)

    list_p = sub.add_parser('list', help='Listar los alimentadores e imprimir el inventario detallado de la entrada')
    _common(list_p)
    list_p.add_argument(
        '--inventory-json',
        help='Opcional: ruta donde escribir dataset_inventory.json',
    )

    conv = sub.add_parser('convert', help='Convertir uno, varios o todos los alimentadores')
    _common(conv)
    conv.add_argument('--feeder', action='append', default=[], help='Nombre corto del alimentador; repetir para varios')
    conv.add_argument('--network', action='append', default=[], help='NetworkID completo; repetir para varios')
    conv.add_argument('--all', action='store_true', help='Convertir todos los alimentadores, cada uno por separado')
    conv.add_argument('--out-dir', required=True, help='Carpeta de salida')
    conv.add_argument('--aliases', help='Opcional: JSON de alias de tipos de línea, texto→texto (se aplica antes de buscar en el catálogo)')
    conv.add_argument(
        '--catalogo', nargs='?', const='', metavar='XLSX',
        help=('Corregir las características eléctricas con el catálogo de fichas antes '
              'de escribir el DGS. Sin valor usa input/catalogo_parametros.xlsx. La '
              'identidad de cada elemento (código, material, sección) se conserva.'))
    conv.add_argument('--schema-profile', default='pf21_dgs_1_8_4', help='Perfil de esquema DGS')
    conv.add_argument('--source-crs', default='EPSG:32718', help='CRS de CoordX/CoordY de la entrada (cualquier EPSG en metros; p. ej. EPSG:32718)')
    conv.add_argument('--target-crs', default='EPSG:4326', help='CRS geográfico de destino para GPSlat/GPSlon')
    conv.add_argument('--no-geography', action='store_true', help='No generar GPS ni diagrama')
    conv.add_argument('--non-strict', action='store_true', help='Omitir filas de topología, carga o maniobra no admitidas en vez de fallar; los tipos de línea se resuelven siempre')
    conv.add_argument('--export-xlsx', action='store_true', help='Escribir además un Excel (.xlsx) con una hoja por tabla DGS')
    conv.add_argument('--export-tsv', action='store_true', help='Escribir además un TSV por tabla DGS en {alimentador}_dgs_tables/')
    conv.add_argument('--preview', action='store_true', help='Escribir un mapa HTML interactivo (+ GeoJSON) antes del DGS (requiere geografía)')
    conv.add_argument(
        '--preview-backend',
        default='auto',
        choices=('auto', 'leafmap', 'leaflet'),
        help='Motor del mapa: leafmap (@opengeos) o Leaflet por CDN',
    )
    conv.add_argument(
        '--hoja', default=None, choices=('A0', 'A1', 'A2', 'A3', 'A4'),
        help='Formato fijo de hoja PowerFactory. Por defecto se ajusta a la red a escala real.',
    )
    conv.add_argument(
        '--unir', metavar='NOMBRE',
        help='Unir los alimentadores elegidos en UN solo DGS con este nombre (red unida).',
    )
    conv.add_argument(
        '--literal', action='store_true',
        help='Convertir sin las reglas del proyecto (sin fundir puentes, con trafomix, '
             'sin redimensionar SED, escala NA205). Solo para comparar con la entrada.',
    )
    conv.add_argument(
        '--workers', type=int, default=1,
        help='Procesos en paralelo: 1 en serie (por defecto), N hasta N, 0 automático. '
             'El resultado es idéntico; cada proceso guarda una copia del dataset en memoria.',
    )

    sub.add_parser('gui', help='Abrir la interfaz de escritorio (Tkinter, heredada)')
    web = sub.add_parser('web', help='Arrancar la interfaz web (FastAPI + React) y abrir el navegador')
    web.add_argument('--host', default='127.0.0.1', help='Interfaz de escucha')
    web.add_argument('--port', type=int, default=8765, help='Puerto')
    web.add_argument('--no-browser', action='store_true', help='No abrir el navegador')
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

    # Catálogo incompleto: se completa con otras entregas si se indicaron, y en
    # cualquier caso se dice cuánta red se quedaría con la impedancia de DEFAULT. Un
    # catálogo que no corresponde con la red no rompe nada visible —el modelo converge
    # igual—, así que si no se avisa aquí no se avisa en ninguna parte.
    from .catalog_merge import completar, diagnosticar

    extra = list(getattr(args, 'equipment_extra', ()) or ())
    if extra:
        informe_cat = completar(dataset, extra)
        print(informe_cat.texto())
    else:
        informe_cat = diagnosticar(dataset)
        if informe_cat.cobertura_final < 0.5:
            print(
                f'AVISO: solo el {informe_cat.cobertura_final * 100:.0f} % de los tipos '
                f'de línea tiene catálogo. El resto tomará la impedancia de DEFAULT. '
                f'Use --equipment-extra con el BD_Equipo de otra entrega.'
            )
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
    if args.command == 'web':
        from .web.__main__ import main as web_main
        argv_web = ['--host', args.host, '--port', str(args.port)]
        if args.no_browser:
            argv_web.append('--no-browser')
        return web_main(argv_web)

    dataset = load_dataset(args)

    if args.command == 'list':
        inventory = build_dataset_inventory(dataset)
        print(format_inventory_report(inventory))
        if args.inventory_json:
            path = write_inventory(inventory, args.inventory_json)
            print(f'Inventario JSON: {path}')
        return 0 if inventory['integrity']['errors'] == 0 else 2

    selectors = list(args.feeder) + list(args.network)
    if args.all and selectors:
        raise SystemExit('--all no se puede combinar con --feeder/--network')
    if not args.all and not selectors:
        raise SystemExit('Indique al menos un --feeder/--network, o use --all')

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
        # Reglas del proyecto (igea_dgs.reglas): siempre, salvo --literal. El catálogo
        # del proyecto completa conductores, da los transformadores y sus fichas.
        from dataclasses import replace as _replace

        from .reglas import REGLAS_PROYECTO, SIN_REGLAS, catalogo_del_proyecto

        reglas = SIN_REGLAS if args.literal else _replace(REGLAS_PROYECTO, hoja=args.hoja)
        catalogo = None if args.literal else catalogo_del_proyecto()
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
            catalogo = ruta if not args.literal else None

        if args.unir:
            from .batch import convert_group

            if args.all:
                selectors = [feeder_short_name(n) for n in dataset.feeder_ids() if dataset.feeders.get(n)]
            if len(selectors) < 2:
                raise SystemExit('--unir necesita al menos dos alimentadores (--feeder … --feeder …).')
            grupo = convert_group(
                dataset, selectors, args.out_dir, name=args.unir, aliases=aliases,
                strict=not args.non_strict, schema_profile=args.schema_profile,
                source_crs=args.source_crs, target_crs=args.target_crs,
                catalog_corrections=correcciones_catalogo, reglas=reglas, catalogo=catalogo,
                on_progress=_progress,
            )
            comp = grupo.get('completitud') or {}
            print(f"Red unida {grupo['name']}: {grupo['status']} — "
                  f"{grupo.get('errors_total')} errores de validación, completitud "
                  f"{'OK' if not comp.get('fallos') else comp['fallos']}")
            if grupo.get('error'):
                print(f"  {grupo['error']}")
            print(f"Manifiesto: {Path(args.out_dir) / (grupo['name'] + '_manifest.json')}")
            return 0 if grupo['status'] == 'ok' else 2

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
            workers=args.workers,
            reglas=reglas,
            catalogo=catalogo,
        )
    except (OSError, ValueError, ImportError) as exc:
        raise SystemExit(f'Error de conversión: {exc}') from exc

    print(f"Pedidos: {manifest['summary']['requested']}")
    print(f"OK: {manifest['summary']['ok']}")
    print(f"Omitidos: {manifest['summary'].get('skipped', 0)}")
    print(f"Fallidos: {manifest['summary']['failed']}")
    print(f"Manifiesto: {Path(args.out_dir) / 'batch_manifest.json'}")
    return 0 if manifest['summary']['failed'] == 0 else 2


if __name__ == '__main__':
    raise SystemExit(main())
