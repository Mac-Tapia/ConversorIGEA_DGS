"""Actualiza las características eléctricas del modelo según el catálogo de fichas.

El flujo, en una línea: **el TXT o la base Access dicen qué elemento es; el catálogo
dice cómo es ese elemento según su fabricante.**

    TXT / MDB  ──►  modelo  ──►  [catálogo de fichas]  ──►  modelo corregido  ──►  DGS
                      │                                          │
              identidad intacta                        características al día

Qué se conserva, siempre
    El código del tipo, el material y la sección. Si el export dice que el tramo
    ``SEC_1234`` va con ``AA12003D`` —un AAAC de 120 mm²—, sigue yendo con
    ``AA12003D``. Lo mismo con ``NK12003D``, cable de cobre de 120 mm². Eso es el
    inventario de lo que está instalado y esta herramienta no opina sobre él.

Qué se actualiza
    Resistencia, reactancia, susceptancia y ampacidad, cuando la ficha del fabricante
    para **esa misma designación** dice otra cosa.

Por qué en ese sentido y no al revés
    Cuando ``AA01003D`` declara 10 mm² pero lleva la resistencia de un conductor de
    31 mm², hay dos lecturas posibles: o la sección está mal, o el número está mal.
    La designación viene del inventario de activos, que es lo que alguien fue a ver
    al campo; la impedancia es un campo calculado del catálogo de CYMDIST, que es
    justo donde aparecen las filas copiadas. Se conserva la designación y se corrige
    el número.

    Esto no es gratis y el informe lo dice: corregir ``AA01003D`` de 1,0891 a
    3,3776 Ω/km **triplica** la resistencia de esos tramos, y con ella sus pérdidas y
    su caída de tensión. El valor nuevo es el correcto, pero el resultado del estudio
    cambia, así que nada se aplica sin enseñarlo antes.

Uso
    Por defecto **no escribe nada**: enseña qué cambiaría. Hay que pedir el DGS
    explícitamente.

    rem Ver qué cambiaría en todos los alimentadores
    python tools\\apply_catalog_to_model.py --red R.txt --cargas C.txt --equipos E.txt

    rem Convertir a DGS con las características corregidas
    python tools\\apply_catalog_to_model.py --red R.txt --cargas C.txt --equipos E.txt ^
        --out-dir output\\corregido --escribir-dgs

    rem Desde la base Access, un solo alimentador
    python tools\\apply_catalog_to_model.py --mdb BaseDatos.mdb --feeder PA217 --escribir-dgs

Código de salida: 0 si no hay nada que corregir, 1 si hay cambios (aplicados o no),
2 si no se pudo trabajar.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

# La consola de Windows usa cp1252 y el informe lleva Ω, µ y →.
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):  # pragma: no cover
        pass

from igea_dgs.catalog import (  # noqa: E402
    CATALOG_FILENAME,
    Cambio,
    CatalogError,
    aplicar_correcciones,
    auditar,
    escribir_catalogo,
    input_dir,
    leer_catalogo,
)
from igea_dgs.model import build_feeder_model  # noqa: E402


def _cargar_dataset(args: argparse.Namespace):
    if args.mdb:
        from igea_dgs.access import read_access_dataset
        return read_access_dataset(args.mdb, equipment_path=args.equipment_mdb)
    from igea_dgs.dataset import CymdistDataset
    return CymdistDataset.from_files(args.red, args.cargas, args.equipos)


def _resolver_catalogo(args: argparse.Namespace, modelos: list) -> Path:
    """Ruta del catálogo. Si no existe y se permite, se genera con la referencia."""
    if args.catalogo:
        ruta = Path(args.catalogo)
        if not ruta.is_file():
            raise CatalogError(f'No existe el catálogo indicado: {ruta}')
        return ruta
    ruta = input_dir(args.base) / CATALOG_FILENAME
    if ruta.is_file():
        return ruta
    if not args.generar_si_falta:
        raise CatalogError(
            f'No existe {ruta}.\n'
            'Genérelo con tools/build_input_catalog.py, o pase --generar-si-falta '
            'para crearlo ahora con los valores de referencia.'
        )
    print(f'No existe {ruta}; se genera con los valores de referencia.')
    return escribir_catalogo(
        auditar(modelos), base=args.base, nominal_kv=modelos[0].nominal_kv,
    )


def _informe(cambios_por_alimentador: dict[str, list[Cambio]]) -> list[Cambio]:
    """Agrega los cambios por tipo y atributo, y los imprime ordenados por impacto."""
    agregado: dict[tuple[str, str], Cambio] = {}
    for cambios in cambios_por_alimentador.values():
        for c in cambios:
            clave = (c.codigo, c.atributo_pf)
            previo = agregado.get(clave)
            if previo is None:
                agregado[clave] = c
            else:
                agregado[clave] = Cambio(
                    c.codigo, c.atributo_pf, c.unidad, c.antes, c.despues,
                    previo.tramos + c.tramos, previo.km + c.km, c.fuente,
                )
    return sorted(agregado.values(), key=lambda c: (-c.km, c.codigo, c.atributo_pf))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    entrada = p.add_argument_group('entrada (alternativa 1: TXT, alternativa 2: Access)')
    entrada.add_argument('--red')
    entrada.add_argument('--cargas')
    entrada.add_argument('--equipos')
    entrada.add_argument('--mdb')
    entrada.add_argument('--equipment-mdb')

    cat = p.add_argument_group('catálogo')
    cat.add_argument('--catalogo', help='Por defecto input/catalogo_parametros.xlsx')
    cat.add_argument('--base', default='.', help='Carpeta que contiene input/.')
    cat.add_argument('--generar-si-falta', action='store_true',
                     help='Crear el catálogo con los valores de referencia si no existe.')
    cat.add_argument(
        '--incluir-referencia', action='store_true',
        help=('Aplicar también las filas marcadas «referencia» (valores típicos de '
              'norma, no de la ficha del equipo instalado). Fuera de lo normal.'))

    salida = p.add_argument_group('salida')
    salida.add_argument('--feeder', action='append', default=[],
                        help='Limitar a estos alimentadores. Repetible.')
    salida.add_argument('--escribir-dgs', action='store_true',
                        help='Escribir el DGS corregido. Sin esto solo informa.')
    salida.add_argument('--out-dir', default='output/catalogo',
                        help='Destino de los DGS corregidos.')
    salida.add_argument('--sin-geografia', action='store_true')
    salida.add_argument('--source-crs', default='EPSG:32718',
                        help='CRS de las coordenadas del export. Debe estar en metros.')
    salida.add_argument('--informe-json', help='Volcar los cambios a un JSON.')
    args = p.parse_args(argv)

    if not args.mdb and not (args.red and args.cargas and args.equipos):
        p.error('indique --mdb, o bien --red, --cargas y --equipos')

    ds = _cargar_dataset(args)
    modelos = []
    fallidos: list[str] = []
    for net in ds.feeder_ids():
        try:
            m = build_feeder_model(
                ds, net, strict=False,
                include_geography=not args.sin_geografia,
            )
        except Exception as exc:  # noqa: BLE001 - un alimentador roto no para el resto
            fallidos.append(f'{net}: {exc}')
            continue
        if args.feeder and m.name not in args.feeder:
            continue
        modelos.append(m)

    if not modelos:
        print('No se pudo construir ningún alimentador.', file=sys.stderr)
        for f in fallidos[:10]:
            print(f'  {f}', file=sys.stderr)
        return 2

    try:
        ruta_catalogo = _resolver_catalogo(args, modelos)
        correcciones = leer_catalogo(
            ruta_catalogo, incluir_referencia=args.incluir_referencia)
    except CatalogError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f'Catálogo:       {ruta_catalogo}')
    print(f'Alimentadores:  {len(modelos)}'
          + (f'  ({len(fallidos)} no convertibles, excluidos)' if fallidos else ''))
    print(f'Tipos con valor de ficha aplicable: {len(correcciones)}')
    if not correcciones:
        print()
        print('El catálogo no trae ninguna fila marcada «ficha» o «derivado» con un '
              'valor que aplicar.')
        print('Escriba el valor de la ficha en la columna «*_ficha_*» y ponga «ficha» '
              'en «estado».')
        return 0

    cambios_por_alimentador: dict[str, list[Cambio]] = {}
    for m in modelos:
        cambios = aplicar_correcciones(m, correcciones)
        if cambios:
            cambios_por_alimentador[m.name] = cambios

    resumen = _informe(cambios_por_alimentador)
    if not resumen:
        print()
        print('Las características del modelo ya coinciden con el catálogo. '
              'No hay nada que corregir.')
        return 0

    km_totales = sum(c.km for c in resumen)
    tipos = {c.codigo for c in resumen}
    print()
    print(f'{len(resumen)} característica(s) corregidas en {len(tipos)} tipo(s), '
          f'sobre {km_totales:,.1f} km de red '
          f'y {len(cambios_por_alimentador)} alimentador(es).')
    print()
    print('La identidad de cada elemento se conserva: el código, el material y la '
          'sección salen del export y no se tocan.')
    print()
    ancho = max(len(c.linea()) for c in resumen)
    print('  ' + '-' * min(ancho, 110))
    for c in resumen:
        print('  ' + c.linea())
    print('  ' + '-' * min(ancho, 110))

    fuertes = [c for c in resumen
               if c.variacion_pct is not None and abs(c.variacion_pct) >= 25.0]
    if fuertes:
        print()
        print('Cambios de más del 25 %. No son cosméticos: las pérdidas y la caída de '
              'tensión de esos tramos cambian en la misma proporción.')
        for c in fuertes:
            print(f'  · {c.linea()}')

    if args.informe_json:
        destino = Path(args.informe_json)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps({
            'catalogo': str(ruta_catalogo),
            'alimentadores': len(modelos),
            'km_afectados': round(km_totales, 3),
            'cambios': [
                {
                    'codigo': c.codigo, 'atributo_pf': c.atributo_pf,
                    'unidad': c.unidad, 'antes': c.antes, 'despues': c.despues,
                    'variacion_pct': (round(c.variacion_pct, 2)
                                      if c.variacion_pct is not None else None),
                    'tramos': c.tramos, 'km': round(c.km, 3), 'fuente': c.fuente,
                }
                for c in resumen
            ],
            'por_alimentador': {
                nombre: [c.linea() for c in cambios]
                for nombre, cambios in sorted(cambios_por_alimentador.items())
            },
        }, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print()
        print(f'Informe: {destino}')

    if not args.escribir_dgs:
        print()
        print('No se ha escrito ningún fichero. Añada --escribir-dgs para generar los '
              'DGS con estas características.')
        return 1

    # Se convierte por el camino normal, pasándole las correcciones. Reimplementar
    # aquí la escritura del DGS habría dejado fuera la georreferenciación, su
    # validación y la publicación atómica, y habría creado una segunda ruta de
    # conversión que se desviaría de la primera en cuanto una cambiase.
    from igea_dgs.batch import convert_selection

    out_dir = Path(args.out_dir)
    manifiesto = convert_selection(
        ds, args.feeder or None, out_dir,
        all_feeders=not args.feeder,
        strict=False,
        include_geography=not args.sin_geografia,
        source_crs=args.source_crs,
        catalog_corrections=correcciones,
    )
    hechos = [f for f in manifiesto.get('feeders', []) if f.get('status') == 'ok']
    print()
    print(f'{len(hechos)} DGS escritos en {out_dir} con las características del '
          f'catálogo.')
    print('El manifiesto del lote registra qué se corrigió en cada alimentador '
          '(«catalog_changes»).')
    print('El TXT de origen no se ha modificado.')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
