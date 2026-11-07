#!/usr/bin/env python
"""Escanea alimentadores de un proyecto de DIgSILENT antes de recalibrar (spec 028).

Lee, sin escribir nada, lo que tiene cada alimentador en «Sin proyecto» (el de su año, si el
plan lo trae): generadores con su barra, bancos, variaciones que no son del conversor y cargas
cuya demanda difiere de la última calibración. En Nasca (2026-10-28) el usuario pone a mano la
central y los bancos de NA205; con esto la web los ve y la calibración usa su barra.

    python tools/escanear_alimentador_pf.py --plan plan.json --output-json escaneo.json

El plan: ``project``, ``folder``, ``feeders``, ``anio_casos`` (opcional),
``ultima_calibracion`` por alimentador (opcional, 014:RF-10), ``tramos_dgs``, los tramos del
DGS aceptado, para decir cuáles son nuevos (RF-17), y ``abiertos_dgs``, lo que ese DGS deja
abierto, para reconocer las transferencias del operador (098:RF-9, RF-14).

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

from convertersmartgrid.escaneo import CLASES_GENERADOR, origen_de  # noqa: E402


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


def _en_barra_de_cabecera(alims, feeder: str, de_objeto: dict) -> tuple[list[dict], list[dict]]:
    """RF-29: generadores y bancos en la barra de cabecera; el ``ElmFeeder`` empieza aguas abajo de ella.

    Van aparte de los del alimentador: una central en barra no parte el alimentador en dos zonas
    (022:RF-88). La misma barra sale en cada alimentador que cuelga de ella.
    """
    from cargas_pf import _num

    cubiculo = getattr(alims.elm.get(feeder), 'obj_id', None)
    barra = getattr(cubiculo, 'cterm', None)
    generadores, bancos = [], []
    if barra is None:
        return generadores, bancos
    for cub in barra.GetContents('*.StaCubic', 0) or []:
        obj = getattr(cub, 'obj_id', None)
        clase = obj.GetClassName() if obj is not None else ''
        if clase in CLASES_GENERADOR:
            p, q = _num(obj, 'pgini'), _num(obj, 'qgini')
            variacion = de_objeto.get((clase, obj.loc_name))
            generadores.append({'generador': obj.loc_name, 'clase': clase, 'barra': barra.loc_name,
                                'kv': _num(barra, 'uknom'), 'p_kw': None if p is None else p * 1000.0,
                                'q_kvar': None if q is None else q * 1000.0,
                                'en_servicio': not int(getattr(obj, 'outserv', 0) or 0),
                                'variacion': variacion, **origen_de(obj.loc_name, variacion)})
        elif clase == 'ElmShnt':
            escalon, pasos = _num(obj, 'qcapn'), _num(obj, 'ncapa') or 1.0
            variacion = de_objeto.get(('ElmShnt', obj.loc_name))
            bancos.append({'banco': obj.loc_name, 'barra': barra.loc_name, 'kv': _num(barra, 'uknom'),
                           'q_nominal_kvar': None if escalon is None else escalon * pasos * 1000.0,
                           'en_servicio': not int(getattr(obj, 'outserv', 0) or 0),
                           'variacion': variacion, **origen_de(obj.loc_name, variacion)})
    return sorted(generadores, key=lambda x: x['generador']), sorted(bancos, key=lambda x: x['banco'])


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
            en_barra = _en_barra_de_cabecera(alims, f, de_objeto)
            informe['alimentadores'][f] = {'generadores': _generadores(alims, f, de_objeto),
                                           'generadores_en_barra': en_barra[0], 'bancos_en_barra': en_barra[1],
                                           'bancos': bancos, 'cargas_cambiadas': cambiadas,
                                           'tramos_nuevos': _tramos_nuevos(alims, f, de_dgs, de_objeto)
                                           if de_dgs else [],
                                           'tramos_cambiados': _tramos_cambiados(alims, f, de_dgs,
                                                                                 de_objeto)}
        except Exception as exc:  # noqa: BLE001 - un alimentador no tumba el escaneo (RF-8)
            informe['alimentadores'][f] = {'error': f'{type(exc).__name__}: {exc}'}
    _transferencias(app, alims, plan, informe)
    return informe, 0


def _transferencias(app, alims, plan: dict, informe: dict) -> None:
    """098:RF-9: lo que está en un alimentador porque el operador se lo transfirió desde otro.

    CA101 y CHN102 (2026-11-07): con la parte transferida pasaron EBC_1, EBC_2 y EBC_3 a CHN102; sin decirlo, parecían
    bancos que el operador había puesto en CHN102, y los tramos nuevos de la transferencia, una ampliación suya.
    """
    from transferencia_operador_pf import equipos_de_las_zonas, leer_transferencias

    from convertersmartgrid.transferencia_operador import texto_de_zona

    try:
        zonas, _objs, frente = leer_transferencias(app, alims, plan, interesan=informe['feeders'])
    except Exception as exc:  # noqa: BLE001 - el escaneo sigue sin ellas (RF-8)
        informe['avisos'].append(f'transferencias del operador: {type(exc).__name__}: {exc}')
        return
    filas = []
    for z, equipos in zip(zonas, equipos_de_las_zonas(app, zonas)):
        filas.append({**z.resumen(), **equipos})
        informe['avisos'].append(texto_de_zona(z))
        destino = informe['alimentadores'].get(z.hacia) or {}
        for b in destino.get('bancos') or []:
            if b.get('banco') in equipos['bancos']:
                b['transferido_desde'] = z.desde
        for g in destino.get('generadores') or []:
            if g.get('generador') in equipos['generadores']:
                g['transferido_desde'] = z.desde
        abiertos = {r.nombre for r in z.abrir}
        for t in destino.get('tramos_nuevos') or []:
            if t.get('tramo') in abiertos:
                t['transferencia'] = {'desde': z.desde, 'hacia': z.hacia}
    informe['transferencias'] = filas
    if frente:
        informe['frente_a_la_fuente'] = frente                   # 098:RF-17, RF-18: particiones y ramas nuevas


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Escaneo de solo lectura de alimentadores en DIgSILENT: '
                                            'generadores, bancos, variaciones y cargas cambiadas (spec 028)')
    p.add_argument('--plan', required=True)
    p.add_argument('--output-json', required=True)
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    salida = Path(args.output_json)
    from convertersmartgrid.pf_arnes import PFNoDisponible, conectar

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
