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

No crea ni modifica nada, tampoco la carpeta si falta. Para demostrar que el proyecto
sigue siendo el aceptado, activa cada proyecto solo durante su lectura, calcula una
huella sin P/Q operativo y restaura al final el proyecto que estaba activo.
Se ejecuta con el Python que exige la API.

    python tools/pf_proyectos.py --output-json proyectos.json [--carpeta NOMBRE]

Códigos de salida: 0 bien, 2 nombre de carpeta inválido, 3 API de PowerFactory no
disponible.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from igea_dgs.carpeta_pf import (  # noqa: E402
    CarpetaError, alimentadores_de, buscar_carpeta, nombre_de_perfil, proyectos_de,
    validar_nombre,
)
from igea_dgs.powerfactory_binding import native_inventory_evidence  # noqa: E402


def leer(app, carpeta: str) -> dict:
    """``{'folder', 'exists', 'aviso', 'projects': [{name, path, feeders}]}``."""
    destino = buscar_carpeta(app.GetCurrentUser(), carpeta)
    if destino is None:
        return {'folder': carpeta, 'exists': False, 'projects': [],
                'aviso': (f'No existe la carpeta {carpeta!r} en DIgSILENT; se crea al '
                          'importar el primer DGS.')}
    proyectos = []
    anterior = app.GetActiveProject()
    for ruta, prj in proyectos_de(destino):
        try:
            feeders, nota = alimentadores_de(prj)
        except Exception as exc:          # un proyecto dañado no tumba la lista
            print(f'  {ruta}: no se pudo leer ({exc})')
            feeders, nota = [], None
        if nota:
            print(f'  AVISO {nota}')
        native_hash = None
        native_manifest = None
        native_reread_at = None
        native_warning = None
        try:
            if app.GetActiveProject() is not prj:
                rc = prj.Activate()
                if rc not in (None, 0):
                    raise RuntimeError(f'Activate devolvió {rc}')
            native_hash, native_manifest = native_inventory_evidence(app, feeders)
            native_reread_at = time.time()
        except Exception as exc:
            native_warning = f'No se pudo releer la identidad nativa: {exc}'
        proyectos.append({
            'name': prj.loc_name, 'path': ruta, 'feeders': feeders,
            'native_inventory_sha256': native_hash,
            'native_inventory_manifest': native_manifest,
            'native_reread_at': native_reread_at,
            'native_warning': native_warning,
        })
        print(f'  {ruta}: {len(feeders)} alimentador(es)')
    active = app.GetActiveProject()
    if active is not None and active is not anterior:
        active.Deactivate()
    if anterior is not None and app.GetActiveProject() is not anterior:
        anterior.Activate()
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

    # Primera línea de la salida solo con PowerFactory ya respondiendo: la web espera esta
    # línea un tiempo limitado (spec 005, RF-21). El 2026-10-14 una sesión se quedó
    # parada justo en ``GetCurrentUser``, sin escribir nada.
    usuario = app.GetCurrentUser()
    print(f'Conectado a DIgSILENT como {getattr(usuario, "loc_name", "?")}. '
          f'Carpeta: {carpeta}', flush=True)
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
