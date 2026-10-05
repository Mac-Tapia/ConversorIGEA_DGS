"""CLI del módulo `vnr_etl` (secciones 18, U15, D12, D16).

``python -m vnr_etl <comando>``. Los códigos de salida siguen la convención del
proyecto: ``0`` OK, ``2`` fallo de conversión, ``1`` error de uso o E/S.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC
from pathlib import Path

from . import __version__
from .config import Settings
from .doctor import doctor
from .logging import Logger, StreamSink


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='vnr_etl',
        description='ETL universal OSINERGMIN/VNRGIS/GIS -> CYMDIST / DIgSILENT',
    )
    parser.add_argument('--config', help='Ruta a un YAML de configuración (config/vnr_settings.yaml)')
    parser.add_argument('--version', action='version', version=f'vnr_etl {__version__}')
    sub = parser.add_subparsers(dest='command', required=True)

    sub.add_parser('doctor', help='Informa dependencias y capacidades')

    p = sub.add_parser('probe', help='Probar una fuente y decir qué es')
    p.add_argument('source')
    p.add_argument('--output', help='Ruta JSON opcional para el informe')

    sub.add_parser('ver', help='Versión del módulo')

    p = sub.add_parser('companies', help='Lista empresas de una fuente')
    p.add_argument('source')

    p = sub.add_parser('periods', help='Lista periodos de una fuente')
    p.add_argument('source')
    p.add_argument('--company')

    p = sub.add_parser('inventory', help='Inventario de capas/campos de una fuente')
    p.add_argument('source')

    p = sub.add_parser('inspect-sql', help='Inspecciona un volcado SQL sin ejecutarlo')
    p.add_argument('source')

    p = sub.add_parser('reconcile', help='Compara dos mapas JSON por ID estable')
    p.add_argument('previous')
    p.add_argument('current')
    p.add_argument('--geometry-key', default='geometry')
    p.add_argument('--attribute', action='append', default=[])

    p = sub.add_parser('audit', help='Auditoría de solo lectura del proyecto')
    p.add_argument('--project', default='.')

    p = sub.add_parser('plan-integration', help='Plan de integración (AUDIT/integration_plan.md)')
    p.add_argument('--project', default='.')
    p.add_argument('--output')

    p = sub.add_parser('web', help='Inicia la interfaz web del módulo')
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8776)

    p = sub.add_parser('convert', help='Convierte una fuente a modelo canónico (+export)')
    p.add_argument('source')
    p.add_argument('--company')
    p.add_argument('--period', default='latest_available')
    p.add_argument('--output', default='output/vnr')
    p.add_argument('--source-crs', default=None)
    p.add_argument('--working-crs', default=None)
    p.add_argument('--snap-m', type=float, default=None)
    p.add_argument('--no-strict', action='store_true')
    p.add_argument('--format', choices=('json', 'cymdist', 'dgs'), default='json')

    p = sub.add_parser('validate', help='Valida un modelo canónico exportado')
    p.add_argument('canonical', help='Ruta al JSON del modelo o carpeta')

    p = sub.add_parser('export-cymdist', help='Exporta CYMDIST (bloqueado sin contrato)')
    p.add_argument('canonical')
    p.add_argument('--output', default='output/vnr')

    p = sub.add_parser('export-dgs', help='Exporta DIgSILENT DGS')
    p.add_argument('canonical')
    p.add_argument('--output', default='output/vnr')

    p = sub.add_parser('search-vnr', help='Descubre publicaciones VNRGIS (no descarga)')
    p.add_argument('--company')
    p.add_argument('--all-companies', action='store_true')
    p.add_argument('--latest', action='store_true')
    p.add_argument('--source', action='append', help='Página oficial inicial (repetible)')
    p.add_argument('--catalog-dir', default='data/vnr_catalog')

    p = sub.add_parser('list-vnr', help='Lista publicaciones del catálogo local')
    p.add_argument('--company')
    p.add_argument('--catalog-dir', default='data/vnr_catalog')

    p = sub.add_parser('check-updates', help='Compara catálogo local con fuentes oficiales')
    p.add_argument('--source', action='append', help='Página oficial inicial (repetible)')
    p.add_argument('--catalog-dir', default='data/vnr_catalog')

    p = sub.add_parser('download-vnr', help='Descarga una publicación catalogada con manifiesto')
    p.add_argument('publication_id')
    p.add_argument('--catalog-dir', default='data/vnr_catalog')
    p.add_argument('--output', default='data/vnr_downloads')

    return parser


def _configure_stdout() -> None:
    """Emite UTF-8 limpio en consolas Windows que son UTF-8 (pwsh) sin romper captura.

    El intérprete por defecto usa la página de códigos del sistema (cp1252); al
    reconvertir a UTF-8, acentos y flechas salen bien. En las pruebas ``capsys``
    sustituye ``sys.stdout`` por un objeto sin ``reconfigure``, así que se ignora.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, LookupError):
            pass


def _settings(args, log: Logger) -> Settings:
    try:
        settings = Settings.load(args.config) if getattr(args, 'config', None) else Settings()
    except (OSError, TypeError, ValueError) as exc:
        raise SystemExit(f'Configuración: {exc}') from exc
    if getattr(args, 'no_strict', False):
        settings.project['strict'] = False
    return settings


def main(argv=None) -> int:
    _configure_stdout()
    args = _parser().parse_args(argv)
    log = Logger(sinks=[StreamSink()])

    if args.command == 'doctor':
        print(doctor().report())
        return 0
    if args.command == 'ver':
        print(f'vnr_etl {__version__}')
        return 0
    if args.command == 'web':
        from .web.__main__ import main as web_main
        return web_main(['--host', args.host, '--port', str(args.port)])

    if args.command == 'inspect-sql':
        from .connectors.databases import inspect_sql_dump

        try:
            report = inspect_sql_dump(args.source)
        except OSError as exc:
            raise SystemExit(f'Inspección SQL: {exc}') from exc
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == 'reconcile':
        from .reconciliation.diff import diff_records

        try:
            previous = json.loads(Path(args.previous).read_text(encoding='utf-8'))
            current = json.loads(Path(args.current).read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise SystemExit(f'Reconciliación: {exc}') from exc
        if not isinstance(previous, dict) or not isinstance(current, dict):
            raise SystemExit('Reconciliación: ambos JSON deben ser objetos {id: registro}.')
        result = diff_records(
            previous,
            current,
            geometry_key=args.geometry_key,
            attribute_keys=args.attribute,
        )
        print(json.dumps({
            'summary': result.summary(), 'classified': result.as_dict()
        }, ensure_ascii=False, indent=2))
        return 0

    if args.command in ('audit', 'plan-integration'):
        from .audit import run_audit

        try:
            written = run_audit(args.project, output_dir=getattr(args, 'output', None))
        except OSError as exc:
            raise SystemExit(f'Auditoría: {exc}') from exc
        for path in written.values():
            print(f'  {path}')
        print(f'Auditoría escrita en {Path(args.project) / "AUDIT"}.')
        return 0

    if args.command == 'probe':
        from .pipeline import probe_source

        try:
            report = probe_source(args.source)
        except (OSError, ValueError) as exc:
            raise SystemExit(f'Probe: {exc}') from exc
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.output:
            Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        return 0

    if args.command in ('inventory', 'companies', 'periods'):
        from .pipeline import discover_layers, list_companies, list_periods

        try:
            layers = discover_layers(args.source)
        except (OSError, ValueError, RuntimeError) as exc:
            raise SystemExit(f'Inventario: {exc}') from exc
        if args.command == 'inventory':
            print(json.dumps(layers, ensure_ascii=False, indent=2))
        elif args.command == 'companies':
            companies = list_companies(args.source)
            print('\n'.join(companies) if companies else '(no se detectaron capas de empresa)')
        else:
            periods = list_periods(args.source, company=args.company)
            print('\n'.join(periods) if periods else '(no se detectaron periodos)')
        report = {
            'command': args.command,
            'layers': len(layers),
            'values': companies if args.command == 'companies' else (
                periods if args.command == 'periods' else None
            ),
        }
        print(json.dumps(report, ensure_ascii=False))
        return 0

    if args.command == 'convert':
        return _convert(args, log)

    if args.command == 'validate':
        return _validate(args)

    if args.command in ('export-cymdist', 'export-dgs'):
        return _export(args, args.command)

    # search-vnr / list-vnr / check-updates
    return _discovery(args)


def _convert(args, log: Logger) -> int:
    import hashlib
    from datetime import datetime

    from .discovery import compute_schema_fingerprint, compute_source_fingerprint
    from .discovery.download import sha256_of
    from .pipeline import (
        canonicalize_sections,
        discover_layers,
        read_layer,
        select_source_scope,
    )

    settings = _settings(args, log)
    try:
        layers = discover_layers(args.source)
    except Exception as exc:
        raise SystemExit(f'No se pudo descubrir la fuente: {exc}') from exc

    sections_layer = _find_section_layer(layers)
    if sections_layer is None:
        raise SystemExit(
            'No se identificó una capa de tramos MT. Indique una fuente con '
            'polilíneas (ArcGIS Tramo Media Tensión, GeoJSON/SHP de tramos…).'
        )

    section_rows = read_layer(args.source, sections_layer.get('name') or sections_layer.get('layer_id'))
    try:
        section_rows, scope = select_source_scope(
            section_rows, company=args.company, period=args.period
        )
    except ValueError as exc:
        raise SystemExit(f'Selección empresa/periodo: {exc}') from exc
    source_crs = args.source_crs or sections_layer.get('crs')
    if not source_crs:
        raise SystemExit(
            'La fuente no declara CRS. Indíquelo explícitamente con --source-crs; '
            'no se asumirá EPSG:4326.'
        )
    result = canonicalize_sections(
        section_rows,
        source_crs=source_crs,
        working_crs=args.working_crs,
        snap_tolerance_m=args.snap_m if args.snap_m is not None else settings.gis['snap_tolerance_m'],
        source_layer=str(sections_layer.get('name') or sections_layer.get('layer_id')),
    )
    for warning in result.warnings[:10]:
        log.warning('gis', 'VNRGIS_GEOM', warning)  # noqa: PLE1205

    model = result.model
    schema_fingerprint = compute_schema_fingerprint(layers)
    source_descriptor = compute_source_fingerprint(
        source_family='ARCGIS_PUBLIC_REFERENCE' if args.source.lower().startswith('https://') else 'LOCAL_FILE',
        uri=args.source,
        company_values=[scope['company']] if scope['company'] else (),
        period_values=[scope['period']] if scope['period'] else (),
        layers=[str(sections_layer.get('name') or sections_layer.get('layer_id'))],
        crs=source_crs,
        schema_fingerprint=schema_fingerprint,
    ).as_dict()
    fingerprint_json = json.dumps(source_descriptor, sort_keys=True, ensure_ascii=False)
    source_fingerprint = hashlib.sha256(fingerprint_json.encode('utf-8')).hexdigest()
    source_path = Path(args.source)
    source_sha256 = (
        sha256_of(source_path) if source_path.is_file()
        else hashlib.sha256(
            json.dumps(section_rows, sort_keys=True, ensure_ascii=False, default=str).encode('utf-8')
        ).hexdigest()
    )
    manifest_path = source_path.with_suffix(source_path.suffix + '.manifest.json')
    manifest = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            manifest = {}
    model.metadata.update({
        'name': scope['company'] or 'VNRGIS',
        'schema_fingerprint': schema_fingerprint,
        'source_fingerprint': source_fingerprint,
        'source_publication_id': manifest.get('publication_id') or f'DIRECT-{source_fingerprint[:16]}',
        'source_company': scope['company'],
        'source_period': scope['period'],
        'source_url': manifest.get('source_url') or (
            args.source if args.source.lower().startswith('https://') else source_path.resolve().as_uri()
        ),
        'source_sha256': manifest.get('sha256') or source_sha256,
        'retrieved_at': manifest.get('retrieved_at') or datetime.now(UTC).isoformat(),
        'canonical_model_version': __version__,
        'source_descriptor': source_descriptor,
    })
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    canonical_path = out_dir / 'canonical.json'
    canonical_path.write_text(json.dumps(model.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
    print(result.as_dict())
    print(f'Modelo canónico: {canonical_path}')

    if args.format in ('dgs', 'cymdist'):
        return _run_export(model, args.format, out_dir, settings)
    return 0


def _find_section_layer(layers: list[dict]) -> dict | None:
    for layer in layers:
        name = (layer.get('name') or '').lower()
        if 'tramo' in name or 'section' in name or 'line' in name:
            return layer
    # Fallback: la primera capa con geometría polilínea.
    for layer in layers:
        gtype = (layer.get('geometry_type') or '').lower()
        if 'polyline' in gtype or 'linestring' in gtype or 'multiline' in gtype:
            return layer
    return None


def _validate(args) -> int:
    path = Path(args.canonical)
    if not path.is_file():
        raise SystemExit(f'No existe el modelo canónico: {path}')
    from .application import VnrApplicationService
    from .models import CanonicalModel

    try:
        model = CanonicalModel.from_dict(json.loads(path.read_text(encoding='utf-8')))
    except (OSError, ValueError) as exc:
        raise SystemExit(f'Modelo canónico: {exc}') from exc
    settings = _settings(args, Logger(sinks=[StreamSink()]))
    assessment = VnrApplicationService(settings).assess(model, 'dgs')
    print(json.dumps(assessment.as_dict(), ensure_ascii=False, indent=2))
    return 0 if assessment.verdict.all_passed() else 2


def _export(args, command: str) -> int:
    path = Path(args.canonical)
    if not path.is_file():
        raise SystemExit(f'No existe el modelo canónico: {path}')
    from .models import CanonicalModel

    model = CanonicalModel.from_dict(json.loads(path.read_text(encoding='utf-8')))
    settings = _settings(args, Logger(sinks=[StreamSink()]))
    return _run_export(model, 'cymdist' if command == 'export-cymdist' else 'dgs', Path(args.output), settings)


def _run_export(model, target: str, out_dir: Path, settings: Settings) -> int:
    from .application import VnrApplicationService
    from .exporters.base import ExportBlocked

    try:
        result = VnrApplicationService(settings).export(model, target, out_dir)
    except (ExportBlocked, FileNotFoundError, TypeError, ValueError) as exc:
        print(str(exc))
        return 2
    for p in result.paths:
        print(f'  {p}')
    print(f'Estado: {result.readiness}; puertas A-F verificadas localmente.')
    return 0


def _import_topology():
    import vnr_etl.topology

    from .topology import validate_topology  # noqa: F401

    return vnr_etl.topology


def _import_enrich():
    import vnr_etl.electrical

    return vnr_etl.electrical


def _import_exporters():
    import vnr_etl.exporters

    return vnr_etl.exporters


def _discovery(args) -> int:
    from .discovery import PublicationCatalog, refresh_official_catalog

    catalog_dir = getattr(args, 'catalog_dir', 'data/vnr_catalog')
    catalog = PublicationCatalog.load(catalog_dir)
    if args.command == 'list-vnr':
        pubs = catalog.publications(company=args.company)
        for pub in pubs:
            print(f'{pub.publication_id}  {pub.company or pub.company_code:20} '
                  f'{pub.publication_type:28} {pub.period_label:12} {pub.published_at}')
        print(f'{len(pubs)} publicación(es).')
        return 0
    if args.command == 'download-vnr':
        from .discovery import DownloadManager

        publication = catalog.get(args.publication_id)
        if publication is None:
            raise SystemExit(f'Publicación no encontrada: {args.publication_id}')
        if not publication.download_url:
            raise SystemExit(f'La publicación no tiene URL descargable: {args.publication_id}')
        settings = _settings(args, Logger(sinks=[StreamSink()]))
        manager = DownloadManager(
            args.output,
            retries=settings.download['retries'],
            connect_timeout_s=settings.download['connect_timeout_s'],
            read_timeout_s=settings.download['read_timeout_s'],
            max_file_size_bytes=int(settings.download['max_file_size_mb']) * 1024 * 1024,
            verify_archive=settings.download['verify_archive'],
            allowed_hosts=settings.discovery['allowed_hosts'],
        )
        file_name = Path(publication.file_name).name or f'{publication.publication_id}.bin'
        manifest = manager.download(
            publication.download_url,
            Path(args.output) / file_name,
            publication_id=publication.publication_id,
            company=publication.company or publication.company_code,
            period=publication.period_label,
        )
        print(json.dumps(manifest.as_dict(), ensure_ascii=False, indent=2))
        return 0

    before = {publication.publication_id for publication in catalog.publications()}
    catalog, report = refresh_official_catalog(
        catalog_dir,
        pages=getattr(args, 'source', None),
    )
    after = {publication.publication_id for publication in catalog.publications()}
    report['new_publication_ids'] = sorted(after - before)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.command == 'search-vnr':
        pubs = catalog.publications(company=args.company)
        for pub in pubs:
            print(f'{pub.publication_id}  {pub.publication_type:30} '
                  f'{pub.period_label:8} {pub.title}')
    return 2 if report['errors'] and not after else 0


if __name__ == '__main__':
    raise SystemExit(main())
