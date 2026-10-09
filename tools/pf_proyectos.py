#!/usr/bin/env python
"""Lista los proyectos de la carpeta de importación de DIgSILENT y sus alimentadores.

Alimenta el desplegable de la web: el operador elige el proyecto que ya existe en
DIgSILENT y, dentro de él, en qué alimentadores aplicar las cargas.

Solo mira la carpeta donde quedan los proyectos importados desde DGS (spec 005) y sus
subcarpetas. Antes recorría todos los proyectos del usuario y, en cada uno, todo su
árbol: el 2026-10-09 la lectura seguía a los seis minutos con 3,7 GB de memoria. Cada
proyecto sale con su ruta relativa a la carpeta, que es lo que lo identifica.

Los alimentadores son los ``ElmFeeder`` de los datos de red del proyecto: el DGS crea
uno por alimentador, también en una red unida. Un proyecto sin ``ElmFeeder`` (hecho a
mano) muestra sus ``ElmNet``.

No crea ni modifica nada, tampoco la carpeta si falta, y no activa ningún proyecto.
Se ejecuta con el Python que exige la API.

    python tools/pf_proyectos.py --output-json proyectos.json [--carpeta NOMBRE]

Códigos de salida: 0 bien, 2 nombre de carpeta inválido, 3 API de PowerFactory no
disponible.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from igea_dgs.carpeta_pf import (  # noqa: E402
    CarpetaError, alimentadores_de, buscar_carpeta, nombre_de_perfil, proyectos_de,
    validar_nombre,
)


def leer(app, carpeta: str) -> dict:
    """``{'folder', 'exists', 'aviso', 'projects': [{name, path, feeders}]}``."""
    destino = buscar_carpeta(app.GetCurrentUser(), carpeta)
    if destino is None:
        return {'folder': carpeta, 'exists': False, 'projects': [],
                'aviso': (f'No existe la carpeta {carpeta!r} en DIgSILENT; se crea al '
                          'importar el primer DGS.')}
    proyectos = []
    for ruta, prj in proyectos_de(destino):
        try:
            feeders, nota = alimentadores_de(prj)
        except Exception as exc:          # un proyecto dañado no tumba la lista
            print(f'  {ruta}: no se pudo leer ({exc})')
            feeders, nota = [], None
        if nota:
            print(f'  AVISO {nota}')
        proyectos.append({'name': prj.loc_name, 'path': ruta, 'feeders': feeders})
        print(f'  {ruta}: {len(feeders)} alimentador(es)')
    return {'folder': carpeta, 'exists': True, 'aviso': None, 'projects': proyectos}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Proyectos de la carpeta de importación de PowerFactory')
    p.add_argument('--output-json', required=True)
    p.add_argument('--carpeta', help='Carpeta de DIgSILENT. Por defecto, la del perfil de '
                                     'empresa o «Conversor IGEA-DGS» (spec 005).')
    args = p.parse_args(argv)
    try:
        carpeta = validar_nombre(args.carpeta) if args.carpeta is not None else nombre_de_perfil()
    except CarpetaError as exc:
        print(f'ERROR: {exc}')
        return 2
    try:
        import powerfactory
    except ImportError as exc:
        print(f'ERROR: API de PowerFactory no disponible ({exc}).')
        return 3
    try:
        app = powerfactory.GetApplicationExt()
    except Exception as exc:
        print(f'ERROR: no se pudo conectar a PowerFactory: {exc}')
        return 3

    print(f'Carpeta de DIgSILENT: {carpeta}')
    datos = leer(app, carpeta)
    if datos['aviso']:
        print(f'AVISO: {datos["aviso"]}')
    Path(args.output_json).write_text(
        json.dumps(datos, indent=2, ensure_ascii=False) + '\n', encoding='utf-8',
    )
    print(f'{len(datos["projects"])} proyecto(s) en {carpeta!r}.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
