"""Convierte TODOS los alimentadores a una sola grid y la importa en PowerFactory.

Por qué una sola grid. Hasta ahora cada alimentador iba a su propio DGS y a su propio
proyecto: 96 redes que no se ven entre sí. Con eso no se puede ni formular la pregunta
de si un alimentador puede respaldar a otro, ni dónde conviene el punto de apertura,
porque el respaldo y la reconfiguración ocurren **entre** alimentadores. En el export
real hay 40 nodos compartidos —los puntos de enlace de la media tensión— que ningún
modelo por separado contiene.

    rem Solo el DGS
    python tools\\build_system_grid.py --red R.txt --cargas C.txt --equipos E.txt

    rem DGS e importación en PowerFactory, con flujo de potencia
    python tools\\build_system_grid.py --red R.txt --cargas C.txt --equipos E.txt ^
        --importar --run-load-flow

    rem Desde la base Access
    python tools\\build_system_grid.py --mdb BaseDatos.mdb --importar

La importación necesita Python 3.12, que es el entorno fijado del proyecto.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):  # pragma: no cover
        pass

from igea_dgs.combine import build_combined  # noqa: E402
from igea_dgs.dgs import write_dgs  # noqa: E402


def _cargar_dataset(args: argparse.Namespace):
    if args.mdb:
        from igea_dgs.access import read_access_dataset
        return read_access_dataset(args.mdb, equipment_path=args.equipment_mdb)
    from igea_dgs.dataset import CymdistDataset
    return CymdistDataset.from_files(args.red, args.cargas, args.equipos)


def _importar_en_powerfactory(dgs: Path, nombre: str, *, run_ldf: bool) -> int:
    """Importa el DGS como un proyecto nuevo y, si se pide, corre el flujo.

    La importación la hace ``powerfactory_acceptance.import_dgs_file``, que ya está
    probada con el orden de atributos que exige ``ComImport`` —``iopt_prj``,
    ``targname``, ``dgsFormat``, ``fFile``, tomado del ejemplo de la API—. Escribir
    aquí una segunda versión habría significado dos implementaciones de lo mismo, y la
    que se usa menos es la que se rompe sin que nadie se entere.
    """
    pf_dir = Path(r'C:\Program Files\DIgSILENT\PowerFactory 2024\Python\3.12')
    if not (pf_dir / 'powerfactory.pyd').is_file():
        print(f'No se encontró la API en {pf_dir}', file=sys.stderr)
        return 3
    if sys.version_info[:2] != (3, 12):
        print(f'Este intérprete es {sys.version_info.major}.{sys.version_info.minor}; '
              'la API de PowerFactory 2024 pide 3.12. El entorno del proyecto ya es '
              '3.12: use .venv\\Scripts\\python.exe', file=sys.stderr)
        return 3
    sys.path.insert(0, str(pf_dir))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import powerfactory  # type: ignore

    from powerfactory_acceptance import import_dgs_file  # type: ignore

    app = powerfactory.GetApplication()
    if app is None:
        print('PowerFactory no respondió. ¿Está abierto en otra sesión?', file=sys.stderr)
        return 3

    print()
    print(f'Importando en PowerFactory como «{nombre}»…')
    try:
        info = import_dgs_file(app, dgs, project_name=nombre)
    except Exception as exc:  # noqa: BLE001 - la API lanza tipos propios
        print(f'La importación falló: {exc}', file=sys.stderr)
        return 4

    proyecto = app.GetActiveProject()
    print(f'Proyecto importado: {proyecto.loc_name if proyecto else "?"}')
    if isinstance(info, dict) and info.get('errors'):
        print(f'  avisos de importación: {info["errors"][:3]}')
    barras = app.GetCalcRelevantObjects('ElmTerm')
    barras = app.GetCalcRelevantObjects('ElmTerm')
    lineas = app.GetCalcRelevantObjects('ElmLne')
    cargas = app.GetCalcRelevantObjects('ElmLod')
    redes = app.GetCalcRelevantObjects('ElmNet')
    print(f'  ElmNet (grids) : {len(redes)}')
    print(f'  Barras         : {len(barras):,}')
    print(f'  Tramos         : {len(lineas):,}')
    print(f'  Cargas         : {len(cargas):,}')

    if not run_ldf:
        return 0

    print()
    print('Flujo de potencia…')
    ldf = app.GetFromStudyCase('ComLdf')
    rc = ldf.Execute()
    if rc != 0:
        print(f'El flujo NO convergió (rc={rc}).', file=sys.stderr)
        return 5
    tensiones = [b.GetAttribute('m:u') for b in barras
                 if b.HasResults() and b.GetAttribute('m:u') is not None]
    if tensiones:
        print(f'Convergió. Tensión: mínima {min(tensiones):.4f} p.u., '
              f'máxima {max(tensiones):.4f} p.u., barras con resultado '
              f'{len(tensiones):,} de {len(barras):,}')
    else:
        print('Convergió, pero ninguna barra devolvió tensión.')
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--red')
    p.add_argument('--cargas')
    p.add_argument('--equipos')
    p.add_argument('--mdb')
    p.add_argument('--equipment-mdb')
    p.add_argument('--nombre', default='SISTEMA', help='Nombre de la red unida.')
    p.add_argument('--feeder', action='append', default=[],
                   help='Limitar a estos alimentadores. Repetible. Por defecto, todos.')
    p.add_argument('--out', help='Ruta del DGS. Por defecto output/sistema/<nombre>.dgs')
    p.add_argument('--sin-geografia', action='store_true')
    p.add_argument('--source-crs', default='EPSG:32718')
    p.add_argument('--catalogo', nargs='?', const='', metavar='XLSX',
                   help='Corregir las características con el catálogo de fichas.')
    p.add_argument('--importar', action='store_true',
                   help='Importar el DGS en PowerFactory como proyecto nuevo.')
    p.add_argument('--run-load-flow', action='store_true')
    p.add_argument('--informe-json')
    args = p.parse_args(argv)

    if not args.mdb and not (args.red and args.cargas and args.equipos):
        p.error('indique --mdb, o bien --red, --cargas y --equipos')

    ds = _cargar_dataset(args)
    modelo, informe = build_combined(
        ds, selectors=args.feeder or None, strict=False,
        include_geography=not args.sin_geografia, name=args.nombre,
    )

    if args.catalogo is not None:
        from igea_dgs.catalog import (
            CATALOG_FILENAME, CatalogError, aplicar_correcciones, input_dir,
            leer_catalogo,
        )
        ruta = Path(args.catalogo) if args.catalogo else input_dir('.') / CATALOG_FILENAME
        try:
            cambios = aplicar_correcciones(modelo, leer_catalogo(ruta))
        except CatalogError as exc:
            print(f'Catálogo: {exc}', file=sys.stderr)
            return 2
        print(f'Catálogo aplicado: {len(cambios)} característica(s) corregidas.')

    print(informe.text())
    if informe.voltage_conflicts:
        print()
        for w in informe.warnings[:informe.voltage_conflicts]:
            print(f'  AVISO: {w}')
    if informe.skipped:
        print()
        print(f'  {len(informe.skipped)} alimentador(es) no convertibles, excluidos:')
        for s in informe.skipped[:5]:
            print(f'    {s}')

    geografia = None
    if not args.sin_geografia:
        from igea_dgs.geography import assert_metre_source_crs, build_geography
        assert_metre_source_crs(args.source_crs)
        geografia = build_geography(ds, modelo, source_crs=args.source_crs)

    destino = Path(args.out) if args.out else Path('output/sistema') / f'{args.nombre}.dgs'
    destino.parent.mkdir(parents=True, exist_ok=True)
    write_dgs(modelo, destino, geography=geografia)
    print()
    print(f'DGS de la red unida: {destino}  ({destino.stat().st_size / 1e6:.1f} MB)')

    if args.informe_json:
        salida = Path(args.informe_json)
        salida.parent.mkdir(parents=True, exist_ok=True)
        info = modelo.combined
        salida.write_text(json.dumps({
            'nombre': args.nombre,
            'alimentadores': informe.feeders,
            'nodos_por_separado': informe.nodes_in,
            'nodos_unidos': informe.nodes_out,
            'puntos_de_enlace': {n: f for n, f in info.tie_nodes.items()},
            'conflictos_de_tension': info.voltage_conflicts,
            'tensiones': {str(k): v for k, v in informe.voltages.items()},
            'tramos': informe.lines, 'cargas': informe.loads, 'seds': informe.seds,
            'omitidos': informe.skipped,
        }, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(f'Informe: {salida}')

    if not args.importar:
        return 0
    return _importar_en_powerfactory(
        destino.resolve(), args.nombre, run_ldf=args.run_load_flow)


if __name__ == '__main__':
    raise SystemExit(main())
