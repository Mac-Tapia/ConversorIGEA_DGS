#!/usr/bin/env python
"""Órdenes de aceptación de la restitución del servidor de DIgSILENT (spec 064, T7).

Cuatro acciones, cada una una orden del servidor (``GUIONES_SERVIBLES``), para recorrer la
cadena real: web → ``pf_cliente`` → ``pf_servidor.atender`` → foto, orden y restitución.

- ``copiar``: copia ``origen`` como ``PRUEBA064_<hora>`` en su carpeta y la deja activa.
- ``alterar_y_fallar``: en la copia activa cambia el caso, la hora del caso de partida, el
  escenario y una variación, y termina con código 1 a propósito: el servidor debe reponerlo.
- ``leer``: la foto del estado activo de la copia, para comprobar la restitución.
- ``borrar``: desactiva y borra la copia.

Solo altera o borra proyectos cuyo nombre empieza por ``PRUEBA064_``: el original se copia y
no se toca (los proyectos trabajados, como SM218, nunca se modifican en una prueba).

    python tools/restitucion_pf.py --plan plan.json --output-json informe.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE.parent / 'src'):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

#: Prefijo de las copias que esta orden puede alterar o borrar.
PREFIJO = 'PRUEBA064_'


def _foto_legible(app) -> dict:
    from convertersmartgrid import pf_estado

    f = pf_estado.fotografiar(app)
    if f is None:
        return {'proyecto': None}
    return {'proyecto': getattr(f.proyecto, 'loc_name', None),
            'caso': getattr(f.caso, 'loc_name', None), 'hora': f.hora,
            'escenario': getattr(f.escenario, 'loc_name', None),
            'variaciones': sorted(getattr(v, 'loc_name', '') for v in f.variaciones)}


def _exigir_copia(app, plan: dict):
    proyecto = app.GetActiveProject()
    nombre = getattr(proyecto, 'loc_name', '')
    if proyecto is None or not nombre.startswith(PREFIJO) or nombre != plan.get('copia'):
        raise SystemExit(f'ERROR: el proyecto activo es {nombre!r}, no la copia {plan.get("copia")!r}; '
                         f'esta orden solo altera proyectos {PREFIJO}*.')
    return proyecto


def copiar(app, plan: dict) -> dict:
    from convertersmartgrid.carpeta_pf import buscar_carpeta, proyectos_de

    carpeta = buscar_carpeta(app.GetCurrentUser(), plan['folder'])
    original = dict(proyectos_de(carpeta) if carpeta else []).get(plan['origen'])
    if original is None:
        raise SystemExit(f"ERROR: no está el proyecto {plan['origen']!r} en la carpeta {plan['folder']!r}")
    if app.GetActiveProject() is not None:
        app.GetActiveProject().Deactivate()
    copia = original.GetParent().AddCopy(original, f'{PREFIJO}{time.strftime("%H%M%S")}')
    if copia is None or copia.Activate() != 0:
        raise SystemExit('ERROR: no se pudo copiar o activar la copia')
    casos = app.GetProjectFolder('study').GetContents('*.IntCase', 1)
    sin = next((c for c in casos if c.loc_name.startswith('Sin proyecto')), casos[0] if casos else None)
    if sin is not None:
        sin.Activate()
    print(f'Copia {copia.loc_name} de {plan["origen"]}, activa.', flush=True)
    return {'copia': copia.loc_name, 'foto': _foto_legible(app)}


def alterar_y_fallar(app, plan: dict) -> dict:
    _exigir_copia(app, plan)
    antes = _foto_legible(app)
    caso = app.GetActiveStudyCase()
    caso.iStudyTime = int(caso.iStudyTime) - 10**6
    casos = app.GetProjectFolder('study').GetContents('*.IntCase', 1)
    otro = next((c for c in casos if c.loc_name != caso.loc_name), None)
    if otro is not None:
        otro.Activate()
    # Un escenario distinto del de partida (no del activo tras cambiar de caso): en SM218 y en
    # 0205 el elegido coincidía con el inicial y la restitución del escenario no se probaba.
    escenarios = app.GetProjectFolder('scen', 1).GetContents('*.IntScenario', 1)
    otro_esc = next((e for e in escenarios if e.loc_name != antes.get('escenario')), None)
    if otro_esc is not None:
        otro_esc.Activate()
    activas = {v.loc_name for v in app.GetActiveNetworkVariations() or []}
    variaciones = app.GetProjectFolder('scheme').GetContents('*.IntScheme', 1)
    inactiva = next((v for v in variaciones if v.loc_name not in activas), None)
    if inactiva is not None:
        inactiva.Activate()
    alterado = _foto_legible(app)
    print(f'Estado alterado a propósito: {alterado}', flush=True)
    print('La orden termina con código 1 para que el servidor restituya (064:T7).', flush=True)
    return {'antes': antes, 'alterado': alterado, 'codigo_buscado': 1}


def leer(app, plan: dict) -> dict:
    _exigir_copia(app, plan)
    return {'foto': _foto_legible(app)}


def borrar(app, plan: dict) -> dict:
    proyecto = _exigir_copia(app, plan)
    proyecto.Deactivate()
    nombre = proyecto.loc_name
    borrada = proyecto.Delete() == 0
    print(f'{"Borrada" if borrada else "NO se pudo borrar"} la copia {nombre}.', flush=True)
    return {'borrada': borrada, 'copia': nombre}


ACCIONES = {'copiar': copiar, 'alterar_y_fallar': alterar_y_fallar, 'leer': leer, 'borrar': borrar}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Órdenes de aceptación de la restitución (spec 064, T7)')
    p.add_argument('--plan', required=True, help='JSON con accion, origen, copia y folder')
    p.add_argument('--output-json', required=True, help='Dónde dejar el informe de la orden')
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    accion = ACCIONES.get(plan.get('accion'))
    if accion is None:
        print(f"ERROR: acción desconocida {plan.get('accion')!r}")
        return 2
    from convertersmartgrid.pf_arnes import PFNoDisponible, conectar

    try:
        app = conectar('restitucion_pf.py')
    except PFNoDisponible as exc:
        print(f'ERROR: {exc}')
        return 3
    informe = {'accion': plan['accion'], **accion(app, plan)}
    Path(args.output_json).write_text(json.dumps(informe, indent=2, ensure_ascii=False) + '\n',
                                      encoding='utf-8')
    return int(informe.get('codigo_buscado') or 0)


if __name__ == '__main__':
    raise SystemExit(main())
