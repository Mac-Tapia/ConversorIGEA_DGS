#!/usr/bin/env python
"""Verifica la convergencia de un proyecto de DIgSILENT antes de integrar cargas (spec 008).

El operador calibra los alimentadores a su máxima (spec 006) y, antes de integrar
demandas o cargas nuevas, comprueba que la red resuelve (RF-18). Este guion activa el
proyecto, ejecuta el flujo de carga con lo que esté activo —variaciones y escenario,
tal como los dejó el operador— y mide lo que entra por la cabecera de cada alimentador
pedido (RF-19). No crea variación ni escribe nada en el proyecto.

    python tools/verificar_pf.py --plan plan.json --output-json informe.json

El plan: ``{"project": ruta, "folder": carpeta, "feeders": [...]}``.

Códigos de salida: 0 converge, 2 no converge o sin proyecto, 1 error inesperado, 3 sin API.
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

from cargas_pf import activar_proyecto, error_inesperado, flujo_de_carga, leer_cabecera
from igea_dgs.native_action import native_action_block_report


def ejecutar(app, plan: dict) -> tuple[dict, int]:
    """Flujo de carga con lo activo y cabecera de cada alimentador. Devuelve (informe, código)."""
    informe = {'project': plan['project'], 'modo': 'verificar', 'avisos': [], 'feeders': []}
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r} en la carpeta "
                                    f"{plan.get('folder')!r} de DIgSILENT"}, 2
    variaciones = app.GetActiveNetworkVariations() or []
    informe['variaciones_activas'] = sorted(v.loc_name for v in variaciones)
    escenario = app.GetActiveScenario()
    informe['escenario'] = escenario.loc_name if escenario is not None else None
    informe['flujo'] = flujo = flujo_de_carga(app)
    elms = {f.loc_name: f for f in proyecto.GetContents('*.ElmFeeder', 1)}
    for feeder in plan.get('feeders') or []:
        fila = {'feeder': feeder, 'cabecera': None, 'motivo': None}
        elm = elms.get(feeder)
        if elm is None or getattr(elm, 'obj_id', None) is None:
            fila['motivo'] = 'sin ElmFeeder con cabecera: no se puede medir lo que entra por ella'
        elif not flujo['converged']:
            fila['motivo'] = 'el flujo de carga no converge'
        else:
            medida = leer_cabecera(elm)
            if medida.converge:
                fila['cabecera'] = {'kw': medida.kw, 'kvar': medida.kvar}
            else:
                fila['motivo'] = medida.motivo
        informe['feeders'].append(fila)
    return informe, (0 if flujo['converged'] else 2)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Convergencia de un proyecto de DIgSILENT')
    p.add_argument('--plan', required=True)
    p.add_argument('--output-json', required=True)
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    blocked = native_action_block_report(plan, 'verificar')
    if blocked:
        Path(args.output_json).write_text(
            json.dumps(blocked, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(blocked['error'])
        return 2
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
    # Primera línea solo con DIgSILENT ya respondiendo: la web la espera un tiempo
    # limitado y, si no llega, corta el guion en vez de dejar ocupado el carril (005:RF-21).
    print(f'Conectado a DIgSILENT como {getattr(app.GetCurrentUser(), "loc_name", "?")}.',
          flush=True)
    try:
        informe, codigo = ejecutar(app, plan)
    except Exception as exc:  # noqa: BLE001 - el informe dice el error (RF-17)
        traceback.print_exc()
        informe, codigo = {**error_inesperado(plan, False, exc), 'modo': 'verificar'}, 1
    Path(args.output_json).write_text(
        json.dumps(informe, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
    flujo = informe.get('flujo') or {}
    print(f"Flujo de carga: {'converge' if flujo.get('converged') else 'no converge'}")
    print(f'Informe: {args.output_json}')
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
