#!/usr/bin/env python
"""Cargabilidad del transformador de la SET en el proyecto de transmisión (spec 017, T10).

En el proyecto de transmisión (en Electro Dunas, ``AD08_MPIT25-29_v4``) no hay redes de
media tensión ni una carga por alimentador: la sonda del 2026-10-15 dio 859 cargas por
barra de SET y tensión (``LElCarmen10`` en ``CAR10A``, con CA101 y los demás alimentadores
de 10 kV de El Carmen dentro). Por eso, decidido por el usuario ese día:

* Sin proyecto: el caso de estudio tal cual.
* Con proyecto: a la carga de la barra se le suma el Δ P/Q de cabecera «Con − Sin
  proyecto» del alimentador, de los flujos que ya guardó el paso de estudios. Nada se
  vuelve a simular en el proyecto del alimentador (el usuario: «no hacer dobles trabajos»).

Un flujo de carga por estado. Nada se guarda (RF-68): la P y la Q de la carga se
restituyen y se comprueban al terminar, también si algo falla. No se descarta el
escenario de operación (``Deactivate(0)``): perdería cambios del operador sin guardar.

    python tools/transformador_set_pf.py --plan plan.json --output-json informe.json [--listar]

Con ``--listar``, las cargas del proyecto con su barra, su tensión y el transformador del
que cuelgan, y los casos de estudio, para que el operador elija. Sin él, el plan lleva
``project``, ``folder``, ``caso`` (nombre del caso de estudio; vacío, el activo), ``carga``
(nombre exacto) y ``delta_kw``/``delta_kvar``.

Códigos de salida: 0 hecho, 2 no se pudo (el informe dice por qué), 3 sin API.
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import Any

from cargas_pf import _num, activar_proyecto, flujo_de_carga

#: Lados de cada clase de transformador y el atributo de su potencia nominal en el tipo.
LADOS = {'ElmTr2': (('bushv', 'strn'), ('buslv', 'strn')),
         'ElmTr3': (('bushv', 'strn3_h'), ('busmv', 'strn3_m'), ('buslv', 'strn3_l'))}


def _barra(carga):
    cub = getattr(carga, 'bus1', None)
    return cub.GetParent() if cub is not None else None


def trafos_de(barra) -> list[tuple[Any, str, str]]:
    """``(trafo, lado, atributo de su potencia nominal)`` de cada transformador conectado a
    ``barra`` por el lado que da a ella: el devanado que alimenta la carga."""
    # La API da un envoltorio nuevo en cada llamada: ``is`` entre el padre del cubículo y la
    # barra fue falso en AD08 (2026-10-15) y no salía ningún transformador. Por nombre completo.
    destino = barra.GetFullName()
    out = []
    for t in barra.GetConnectedElements():
        for lado, nominal in LADOS.get(t.GetClassName(), ()):
            cub = getattr(t, lado, None)
            padre = cub.GetParent() if cub is not None else None
            if padre is not None and padre.GetFullName() == destino:
                out.append((t, lado, nominal))
    return out


def medir(app, carga) -> dict:
    """Flujo de carga y cargabilidad de cada devanado que alimenta la barra de ``carga``.

    La del devanado es su potencia aparente entre la nominal de ese devanado; ``c:loading``
    del transformador es la de su devanado más cargado, que en uno de tres devanados puede
    ser otro.
    """
    flujo = flujo_de_carga(app)
    barra = _barra(carga)
    out = {'converge': flujo['converged'], 'trafos': []}
    if not flujo['converged'] or barra is None:
        return out
    for t, lado, nominal in trafos_de(barra):
        s = _num(t, f'm:S:{lado}')
        tipo = getattr(t, 'typ_id', None)
        sn = _num(tipo, nominal) if tipo is not None else None
        out['trafos'].append({
            'nombre': t.loc_name, 'clase': t.GetClassName(), 'lado': lado,
            'kv': _num(barra, 'uknom'),
            'devanado_pct': 100.0 * s / sn if s is not None and sn else None,
            'loading_pct': _num(t, 'c:loading'),
        })
    return out


def listar(app) -> dict:
    """Cargas con su barra y el transformador del que cuelgan, y los casos de estudio."""
    estudios = app.GetProjectFolder('study')
    activo = app.GetActiveStudyCase()
    cargas = []
    for o in app.GetCalcRelevantObjects('*.ElmLod'):
        barra = _barra(o)
        if barra is None:
            continue
        trafos = [t.loc_name for t, _, _ in trafos_de(barra)]
        if not trafos:
            continue  # sin transformador en su barra no hay devanado que medir
        cargas.append({'nombre': o.loc_name, 'barra': barra.loc_name, 'kv': _num(barra, 'uknom'),
                       'trafos': trafos})
    return {'casos': sorted(c.loc_name for c in estudios.GetContents('*.IntCase', 1)) if estudios else [],
            'caso_activo': getattr(activo, 'loc_name', None),
            'cargas': sorted(cargas, key=lambda c: c['nombre'])}


def calcular(app, plan: dict) -> tuple[dict, int]:
    """Cargabilidad sin y con proyecto del devanado que alimenta la carga del plan."""
    informe: dict[str, Any] = {'project': plan.get('project'), 'carga': plan.get('carga'),
                               'caso': None, 'avisos': []}
    previo = app.GetActiveStudyCase()
    caso_pedido = str(plan.get('caso') or '').strip()
    try:
        if caso_pedido:
            estudios = app.GetProjectFolder('study')
            caso = next((c for c in (estudios.GetContents('*.IntCase', 1) if estudios else [])
                         if c.loc_name == caso_pedido), None)
            if caso is None:
                informe['error'] = f'El proyecto no tiene el caso de estudio {caso_pedido!r}.'
                return informe, 2
            caso.Activate()
        informe['caso'] = getattr(app.GetActiveStudyCase(), 'loc_name', None)
        carga = next((o for o in app.GetCalcRelevantObjects('*.ElmLod') if o.loc_name == plan.get('carga')), None)
        if carga is None:
            informe['error'] = (f'No está la carga {plan.get("carga")!r} en el caso '
                                f'{informe["caso"]!r}: elíjala de la lista.')
            return informe, 2
        p0, q0 = float(carga.plini), float(carga.qlini)
        informe['carga_mw'] = {'p': p0, 'q': q0}
        try:
            informe['sin'] = medir(app, carga)
            carga.plini = p0 + float(plan.get('delta_kw') or 0.0) / 1000.0
            carga.qlini = q0 + float(plan.get('delta_kvar') or 0.0) / 1000.0
            informe['con'] = medir(app, carga)
        finally:
            carga.plini, carga.qlini = p0, q0
            # RF-68: comprobado, no supuesto.
            informe['restituida'] = abs(float(carga.plini) - p0) < 1e-9 and abs(float(carga.qlini) - q0) < 1e-9
        if not informe['restituida']:
            informe['error'] = f'La carga {carga.loc_name} no volvió a su P y Q: revísela en DIgSILENT.'
            return informe, 2
        if not (informe['sin']['converge'] and informe['con']['converge']):
            informe['avisos'].append('El flujo de carga del proyecto de transmisión no convergió.')
        return informe, 0
    finally:
        if caso_pedido and previo is not None and app.GetActiveStudyCase() is not previo:
            previo.Activate()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Cargabilidad del transformador de la SET (spec 017, T10)')
    p.add_argument('--plan', required=True)
    p.add_argument('--output-json', required=True)
    p.add_argument('--listar', action='store_true', help='Solo listar cargas y casos')
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    try:
        import powerfactory
    except ImportError as exc:
        print(f'ERROR: API de DIgSILENT no disponible ({exc}).')
        return 3
    try:
        app = powerfactory.GetApplicationExt()
    except Exception as exc:  # noqa: BLE001
        print(f'ERROR: no se pudo conectar a DIgSILENT: {exc}')
        return 3
    print(f'Conectado a DIgSILENT como {getattr(app.GetCurrentUser(), "loc_name", "?")}.', flush=True)
    try:
        if activar_proyecto(app, plan['project'], plan.get('folder')) is None:
            informe, codigo = {'error': f'No se encontró el proyecto {plan["project"]!r}.'}, 2
        elif args.listar:
            informe, codigo = listar(app), 0
        else:
            informe, codigo = calcular(app, plan)
    except Exception as exc:  # noqa: BLE001 - el informe dice el error en vez de perderse
        traceback.print_exc()
        informe, codigo = {'error': f'Error inesperado: {exc}'}, 1
    Path(args.output_json).write_text(
        json.dumps(informe, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
    print(f'Informe: {args.output_json}')
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
