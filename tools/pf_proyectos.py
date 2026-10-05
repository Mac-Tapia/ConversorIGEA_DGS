#!/usr/bin/env python
"""Lista los proyectos de PowerFactory del usuario y los alimentadores de cada uno.

Alimenta el desplegable de la web: el operador elige el proyecto que ya existe en
DIgSILENT y, dentro de él, en qué alimentadores aplicar las cargas. Antes el proyecto
se deducía de lo que se hubiera importado desde ese mismo espacio de trabajo, y un
proyecto importado otro día, o a mano, no se podía usar.

Los alimentadores son los ``ElmFeeder`` del proyecto: el DGS crea uno por alimentador,
también en una red unida, con el nombre del alimentador. Un proyecto sin ``ElmFeeder``
(hecho a mano) muestra sus ``ElmNet``.

No activa ningún proyecto: solo lee. Se ejecuta con el Python que exige la API.

    python tools/pf_proyectos.py --output-json proyectos.json

Códigos de salida: 0 bien, 3 API de PowerFactory no disponible.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def alimentadores_de(proyecto) -> list[str]:
    nombres = {f.loc_name for f in proyecto.GetContents('*.ElmFeeder', 1)}
    if not nombres:
        nombres = {
            n.loc_name for n in proyecto.GetContents('*.ElmNet', 1)
            if 'summary' not in n.loc_name.lower()
        }
    return sorted(nombres)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Proyectos de PowerFactory y sus alimentadores')
    p.add_argument('--output-json', required=True)
    args = p.parse_args(argv)
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

    proyectos = []
    for prj in sorted(app.GetCurrentUser().GetContents('*.IntPrj'), key=lambda x: x.loc_name):
        try:
            feeders = alimentadores_de(prj)
        except Exception as exc:          # un proyecto dañado no tumba la lista
            print(f'  {prj.loc_name}: no se pudo leer ({exc})')
            feeders = []
        proyectos.append({'name': prj.loc_name, 'feeders': feeders})
        print(f'  {prj.loc_name}: {len(feeders)} alimentador(es)')
    Path(args.output_json).write_text(
        json.dumps({'projects': proyectos}, indent=2, ensure_ascii=False) + '\n', encoding='utf-8',
    )
    print(f'{len(proyectos)} proyecto(s) en PowerFactory.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
