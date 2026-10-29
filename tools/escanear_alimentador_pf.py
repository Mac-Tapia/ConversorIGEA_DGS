#!/usr/bin/env python
"""Escanea alimentadores de un proyecto de DIgSILENT antes de recalibrar (spec 028).

Lee, sin escribir nada, lo que tiene cada alimentador en «Sin proyecto» (el de su año, si el
plan lo trae): generadores con su barra, bancos, variaciones que no son del conversor y cargas
cuya demanda difiere de la última calibración. En Nasca (2026-10-28) el usuario pone a mano la
central y los bancos de NA205; con esto la web los ve y la calibración usa su barra.

    python tools/escanear_alimentador_pf.py --plan plan.json --output-json escaneo.json

El plan: ``project``, ``folder``, ``feeders``, ``anio_casos`` (opcional),
``ultima_calibracion`` por alimentador (opcional, 014:RF-10) y ``tramos_dgs``, los tramos del
DGS aceptado, para decir cuáles son nuevos (RF-17).

Códigos de salida: 0 bien, 1 error inesperado, 2 proyecto que no existe, 3 API de
PowerFactory no disponible.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ / 'src'), str(RAIZ / 'tools')]

from igea_dgs.escaneo import CLASES_GENERADOR, origen_de  # noqa: E402


def _variaciones(app) -> tuple[list[dict], dict[tuple[str, str], str]]:
    """Las variaciones del proyecto con su origen (RF-5) y, por objeto, la que lo graba."""
    from casos_pf import objetos_de_variacion

    carpeta = app.GetProjectFolder('scheme')
    activas = {v.loc_name for v in (app.GetActiveNetworkVariations() or [])}
    filas, de_objeto = [], {}
    for v in (carpeta.GetContents('*.IntScheme', 1) if carpeta else []):
        objetos = objetos_de_variacion(v)
        for clave in objetos:
            de_objeto.setdefault(clave, v.loc_name)
        filas.append({'variacion': v.loc_name, 'activa': v.loc_name in activas,
                      'objetos': len(objetos), **origen_de(v.loc_name)})
    return sorted(filas, key=lambda x: x['variacion']), de_objeto


def _generadores(alims, feeder: str, de_objeto: dict) -> list[dict]:
    """RF-2, RF-3: cada generador del alimentador con su barra, P y Q y de quién es."""
    from cargas_pf import _num

    filas = []
    for clase in CLASES_GENERADOR:
        for g in alims.objetos(feeder, clase):
            barra = getattr(getattr(g, 'bus1', None), 'cterm', None)
            variacion = de_objeto.get((clase, g.loc_name))
            p, q = _num(g, 'pgini'), _num(g, 'qgini')
            filas.append({'generador': g.loc_name, 'clase': clase,
                          'barra': getattr(barra, 'loc_name', None),
                          'kv': _num(barra, 'uknom') if barra is not None else None,
                          'p_kw': None if p is None else p * 1000.0,
                          'q_kvar': None if q is None else q * 1000.0,
                          'en_servicio': not int(getattr(g, 'outserv', 0) or 0),
                          'variacion': variacion, **origen_de(g.loc_name, variacion)})
    return sorted(filas, key=lambda x: (str(x['barra']), x['generador']))


def _tramos_nuevos(alims, feeder: str, de_dgs: set[str], de_objeto: dict) -> list[dict]:
    """RF-17: los tramos del alimentador que no venían en el DGS aceptado."""
    from cargas_pf import _num

    filas = []
    for ln in alims.objetos(feeder, 'ElmLne'):
        if ln.loc_name in de_dgs:
            continue
        lados = [getattr(getattr(ln, f'bus{k}', None), 'cterm', None) for k in (1, 2)]
        variacion = de_objeto.get(('ElmLne', ln.loc_name))
        filas.append({'tramo': ln.loc_name, 'desde': getattr(lados[0], 'loc_name', None),
                      'hasta': getattr(lados[1], 'loc_name', None), 'km': _num(ln, 'dline'),
                      'en_servicio': not int(getattr(ln, 'outserv', 0) or 0), 'variacion': variacion,
                      **origen_de(ln.loc_name, variacion)})
    return sorted(filas, key=lambda x: x['tramo'])


def _tramos_cambiados(alims, feeder: str, de_dgs: set[str], de_objeto: dict) -> list[dict]:
    """RF-26: los tramos del DGS aceptado que graba una variación del operador.

    El operador actualiza en DIgSILENT tramos y ternas según lo instalado en campo (usuario,
    2026-10-28: «todas esas modificaciones manuales debe reconocerlas al momento de
    recalibrar»). Los nuevos ya salen en RF-17; estos son los del archivo que él cambió.
    Los de una variación del conversor («Fichas_», obras) no son suyos y no salen.
    """
    from cargas_pf import _num

    filas = []
    for ln in alims.objetos(feeder, 'ElmLne'):
        variacion = de_objeto.get(('ElmLne', ln.loc_name))
        if ln.loc_name not in de_dgs or variacion is None:
            continue
        if origen_de('', variacion)['origen'] != 'operador':
            continue
        filas.append({'tramo': ln.loc_name, 'variacion': variacion,
                      'tipo': getattr(getattr(ln, 'typ_id', None), 'loc_name', None),
                      'km': _num(ln, 'dline'),
                      'en_servicio': not int(getattr(ln, 'outserv', 0) or 0)})
    return sorted(filas, key=lambda x: x['tramo'])


def ejecutar(app, plan: dict) -> tuple[dict, int]:
    """El escaneo de los alimentadores del plan. Devuelve (informe, código)."""
    from ajuste_cabecera_pf import bancos_instalados, cambios_manuales, cargas_sed
    from cargas_pf import Alimentadores, activar_proyecto
    from casos_pf import anio_del_plan
    from casos_pf import caso as caso_del_sistema

    feeders = [str(f) for f in plan.get('feeders') or []]
    informe = {'project': plan.get('project'), 'feeders': feeders, 'caso': None,
               'alimentadores': {}, 'variaciones': [], 'avisos': []}
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r}"}, 2
    anio = anio_del_plan(plan)
    caso = caso_del_sistema(app, 'sin', anio) or caso_del_sistema(app, 'base')
    if caso is None:
        informe['avisos'].append('el proyecto no tiene «Sin proyecto» ni «Caso base»: se lee el caso activo')
    else:
        caso.Activate()
        informe['caso'] = caso.loc_name
    # Los ElmFeeder dan sus objetos con la última topología calculada (021:RF-38).
    try:
        app.GetFromStudyCase('ComLdf').Execute()
    except Exception as exc:  # noqa: BLE001 - sin flujo se lee lo que haya
        informe['avisos'].append(f'flujo antes de leer: {exc}')
    informe['variaciones'], de_objeto = _variaciones(app)
    alims = Alimentadores(app, proyecto, feeders)
    ultimas = plan.get('ultima_calibracion') or {}
    de_dgs = set(plan.get('tramos_dgs') or [])
    for f in feeders:
        if f not in alims.elm:                                              # RF-8
            informe['alimentadores'][f] = {'error': f'el alimentador {f} no está en el proyecto'}
            continue
        try:
            bancos = [{**b, **origen_de(b['banco'], de_objeto.get(('ElmShnt', b['banco'])))}
                      for b in bancos_instalados(alims, f)]
            cargas, _sin = cargas_sed(alims, f)
            cambiadas, _nombre = cambios_manuales(cargas, ultimas.get(f))
            informe['alimentadores'][f] = {'generadores': _generadores(alims, f, de_objeto),
                                           'bancos': bancos, 'cargas_cambiadas': cambiadas,
                                           'tramos_nuevos': _tramos_nuevos(alims, f, de_dgs, de_objeto)
                                           if de_dgs else [],
                                           'tramos_cambiados': _tramos_cambiados(alims, f, de_dgs,
                                                                                 de_objeto)}
        except Exception as exc:  # noqa: BLE001 - un alimentador no tumba el escaneo (RF-8)
            informe['alimentadores'][f] = {'error': f'{type(exc).__name__}: {exc}'}
    return informe, 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Escaneo de solo lectura de alimentadores en DIgSILENT: '
                                            'generadores, bancos, variaciones y cargas cambiadas (spec 028)')
    p.add_argument('--plan', required=True)
    p.add_argument('--output-json', required=True)
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    salida = Path(args.output_json)
    from igea_dgs.pf_arnes import PFNoDisponible, conectar

    try:
        app = conectar('escanear_alimentador_pf.py')
    except PFNoDisponible as exc:
        print(f'ERROR: {exc}')
        return 3
    try:
        informe, codigo = ejecutar(app, plan)
    except Exception as exc:  # noqa: BLE001 - el informe queda siempre escrito (008:RF-17)
        informe, codigo = {'project': plan.get('project'), 'error': repr(exc),
                           'traza': traceback.format_exc()}, 1
    salida.write_text(json.dumps(informe, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    for f, d in (informe.get('alimentadores') or {}).items():
        if d.get('error'):
            print(f"  {f}: {d['error']}", flush=True)
        else:
            print(f"  {f}: {len(d['generadores'])} generador(es), {len(d['bancos'])} banco(s), "
                  f"{len(d['cargas_cambiadas'])} carga(s) cambiada(s), "
                  f"{len(d.get('tramos_nuevos') or [])} tramo(s) nuevo(s), "
                  f"{len(d.get('tramos_cambiados') or [])} cambiado(s) a mano", flush=True)
    print(f"Escaneo de {plan.get('project')}: código {codigo}")
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
