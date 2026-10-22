#!/usr/bin/env python
"""Verifica en DIgSILENT cada año del horizonte del PIDE (spec 024, T13, RF-51 a RF-53).

Para cada año pedido escala la demanda con el factor de escala de cargas del ``ComLdf``
((1 + tasa)^año), ejecuta el flujo en el caso pedido y diagnostica con la norma del perfil
(``igea_dgs.pide``). Al terminar devuelve el factor a su valor: no crea ni guarda nada en
el proyecto.

    python tools/pide_pf.py --plan plan.json --output-json informe.json

El plan: ``{"project", "folder", "feeders", "case", "tasa", "anios": [0, 4, 8, ...],
"limites": {...}, "native_action_context"}``.

Códigos de salida: 0 leído (con o sin problemas), 2 sin proyecto, sin caso o sin tasa,
1 error inesperado, 3 sin API.
"""
from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

from cargas_pf import activar_proyecto, clave_pf, flujo_de_carga
from digital_twin_snapshot_pf import CASOS, _caso, resultados
from estudios_pf import _num

from igea_dgs.digital_twin.native_snapshot import identidad_nativa
from igea_dgs.native_action import native_action_block_report
from igea_dgs.pide import diagnosticar


def ejecutar(app, plan: dict) -> tuple[dict, int]:
    """Diagnóstico de cada año con la demanda escalada. Devuelve (informe, código)."""
    informe = {'project': plan['project'], 'case': plan.get('case'), 'anios': [], 'avisos': []}
    tasa = plan.get('tasa')
    if tasa is None:
        return {**informe, 'error': 'falta la tasa de crecimiento de la demanda (RF-51)'}, 2
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r}"}, 2
    nombre_caso = CASOS.get(plan.get('case') or '', plan.get('case'))
    if nombre_caso:
        caso = _caso(app, nombre_caso)
        if caso is None:
            return {**informe, 'error': f'el proyecto no tiene el caso «{nombre_caso}»'}, 2
        caso.Activate()
    ldf = app.GetFromStudyCase('ComLdf')
    original = getattr(ldf, 'scLoadFac', None)
    if original is None:
        return {**informe, 'error': 'este DIgSILENT no da el factor de escala de cargas del ComLdf'}, 2
    raiz = clave_pf(proyecto)
    lim = plan['limites']
    # Alimentador y tensión de cada barra y línea: con ellos se construye la obra que
    # resuelve el problema (banco en su barra, terna en su tramo; 024:RF-45, RF-47).
    barras, de_linea = {}, {}
    elms = {f.loc_name: f for f in proyecto.GetContents('*.ElmFeeder', 1)}
    for feeder in plan.get('feeders') or []:
        elm = elms.get(feeder)
        if elm is None:
            continue
        for b in elm.GetObjs('ElmTerm'):
            barras[identidad_nativa('ElmTerm', clave_pf(b), raiz)] = {
                'nombre': b.loc_name, 'kv': _num(b, 'uknom'), 'alimentador': feeder}
        for ln in elm.GetObjs('ElmLne'):
            de_linea[ln.loc_name] = feeder
    por_nombre = {v['nombre']: v for v in barras.values()}
    informe['barras_mt'] = sorted(v['nombre'] for v in barras.values() if (v['kv'] or 0) >= 1)
    try:
        for anio in plan.get('anios') or [0]:
            factor = (1 + float(tasa)) ** int(anio)
            ldf.scLoadFac = float(original) * factor
            flujo = flujo_de_carga(app)
            fila = {'anio': int(anio), 'factor': factor, 'converge': flujo['converged']}
            if flujo['converged']:
                lectura = {'flujo': resultados(app, proyecto, raiz, list(plan.get('feeders') or [])),
                           'topologia': {'barras': barras}}
                problemas = diagnosticar(lectura, **lim)
                fila['problemas'] = []
                for p in problemas:
                    sitio = por_nombre.get(p.elemento) or {}
                    linea = p.elemento.removesuffix('.ElmLne')
                    fila['problemas'].append({**p.__dict__, 'kv': sitio.get('kv'),
                                              'alimentador': sitio.get('alimentador') or de_linea.get(linea)})
                tensiones = lectura['flujo']['tensiones']['valores']
                fila['vm_min'] = min(tensiones.values()) if tensiones else None
                fila['cabeceras_kw'] = lectura['flujo']['balance']['valores']['cabeceras']
            else:
                fila['problemas'] = [{'tipo': 'flujo', 'elemento': 'red', 'causa': 'no_converge',
                                      'evidencia': 'el flujo no converge con esta demanda'}]
            informe['anios'].append(fila)
    finally:
        ldf.scLoadFac = original
    return informe, 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Cada año del horizonte del PIDE en DIgSILENT, con la '
                                            'demanda escalada y el diagnóstico de la norma (spec 024)')
    p.add_argument('--plan', required=True)
    p.add_argument('--output-json', required=True)
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    salida = Path(args.output_json)
    blocked = native_action_block_report(plan, 'pide')
    if blocked:
        salida.write_text(json.dumps(blocked, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(blocked['error'])
        return 2
    from igea_dgs.pf_arnes import PFNoDisponible, conectar

    try:
        app = conectar('pide_pf.py')
    except PFNoDisponible as exc:
        print(f'ERROR: {exc}')
        return 3
    try:
        informe, codigo = ejecutar(app, plan)
    except Exception as exc:  # noqa: BLE001 - el informe queda siempre escrito (008:RF-17)
        informe, codigo = {'project': plan.get('project'), 'error': repr(exc),
                           'traza': traceback.format_exc()}, 1
    salida.write_text(json.dumps(informe, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"PIDE de {plan.get('project')}: código {codigo}")
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
