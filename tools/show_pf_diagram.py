#!/usr/bin/env python3
"""Activate DigSilent project and show the IntGrf diagram for a feeder (e.g. AL104)."""
from __future__ import annotations

import argparse
import sys
import time


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Show IGEA feeder diagram in DigSilent PowerFactory')
    p.add_argument('--feeder', default='AL104', help='ElmNet / diagram name (default AL104)')
    p.add_argument('--project-substr', default='AL104', help='Substring to pick IntPrj')
    p.add_argument('--wait', type=float, default=3.0, help='Seconds to wait after connect')
    args = p.parse_args(argv)

    try:
        import powerfactory as pf
    except ImportError:
        print(
            'ERROR: powerfactory no disponible. '
            r'Set PYTHONPATH=C:\Program Files\DIgSILENT\PowerFactory 2024\Python\3.12',
            file=sys.stderr,
        )
        return 3

    app = pf.GetApplication()
    if app is None:
        print(
            'PowerFactory GUI no expone aún la API (GetApplication=None).\n'
            'Deje PowerFactory abierto, inicie sesión si pide licencia, y ejecute de nuevo:\n'
            r'  set PYTHONPATH=C:\Program Files\DIgSILENT\PowerFactory 2024\Python\3.12' '\n'
            f'  python tools\\show_pf_diagram.py --feeder {args.feeder}\n'
            '\nMientras tanto, en DigSilent:\n'
            f'  1) Manager → abra el proyecto *{args.project_substr}* (el más reciente IGEA_AL104)\n'
            f'  2) Active Study Case\n'
            f'  3) Network Data → ElmNet "{args.feeder}" → clic derecho → Edit Graphic / Show Diagram\n'
            '  4) O Graphics Board → diagrama AL104 → Zoom All\n',
            file=sys.stderr,
        )
        return 3

    time.sleep(args.wait)
    user = app.GetCurrentUser()
    projects = list(user.GetContents('*.IntPrj', 1) or [])
    matches = [prj for prj in projects if args.project_substr in (prj.loc_name or '')]
    print('Proyectos coincidentes:', [prj.loc_name for prj in matches[-8:]])
    if not matches:
        print('ERROR: no hay proyecto con', args.project_substr, file=sys.stderr)
        return 2

    target = matches[-1]
    print('Activando proyecto:', target.loc_name)
    app.ActivateProject(target.loc_name)
    time.sleep(0.5)

    study = app.GetProjectFolder('study')
    if study is not None:
        cases = list(study.GetContents('*.IntCase', 1) or [])
        if cases:
            try:
                cases[0].Activate()
                print('Study Case:', cases[0].loc_name)
            except Exception as exc:
                print('Study Case aviso:', exc)

    nets = list(app.GetCalcRelevantObjects('*.ElmNet') or [])
    net = next((n for n in nets if n.loc_name == args.feeder), nets[0] if nets else None)
    if net is None:
        print('ERROR: no se encontró ElmNet', args.feeder, file=sys.stderr)
        return 2
    print('Red:', net.loc_name)

    diagram = getattr(net, 'pDiagram', None)
    if diagram is None:
        print('ERROR: ElmNet.pDiagram vacío — no hay hoja gráfica.', file=sys.stderr)
        return 2
    print('Diagrama (hoja):', diagram.loc_name)

    shown = False
    try:
        diagram.Show()
        shown = True
        print('diagram.Show() OK')
    except Exception as exc:
        print('diagram.Show aviso:', exc)

    try:
        board = app.GetGraphicsBoard()
        board.Show(diagram)
        shown = True
        print('GraphicsBoard.Show(diagrama) OK')
        for zoom in ('ZoomAll', 'FitToPage', 'Rebuild'):
            if hasattr(board, zoom):
                try:
                    getattr(board, zoom)()
                    print(f'board.{zoom}() OK')
                except Exception:
                    pass
    except Exception as exc:
        print('GraphicsBoard aviso:', exc)

    try:
        app.PrintPlain(
            f'IGEA-DGS: diagrama {args.feeder} abierto — use Graphics Board / '
            'View → Zoom All para ver toda la red en la hoja.'
        )
    except Exception:
        pass

    print('LISTO' if shown else 'NO SE PUDO MOSTRAR')
    print('Mire la ventana de PowerFactory → Graphics Board (diagrama unifilar/geográfico).')
    return 0 if shown else 2


if __name__ == '__main__':
    raise SystemExit(main())
