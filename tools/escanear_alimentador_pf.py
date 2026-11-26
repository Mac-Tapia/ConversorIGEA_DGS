#!/usr/bin/env python
"""Escanea alimentadores de un proyecto de DIgSILENT antes de recalibrar (spec 028).

Lee, sin escribir nada en la red, lo que tiene cada alimentador en «Sin proyecto» (el de su año, si el
plan lo trae): generadores con su barra, bancos, variaciones que no son del conversor y cargas
cuya demanda difiere de la última calibración. En Nasca (2026-10-28) el usuario pone a mano la
central y los bancos de NA295; con esto la web los ve y la calibración usa su barra.

    python tools/escanear_alimentador_pf.py --plan plan.json --output-json escaneo.json

El plan: ``project``, ``folder``, ``feeders``, ``anio_casos`` (opcional),
``ultima_calibracion`` por alimentador (opcional, 014:RF-10), ``tramos_dgs``, los tramos del
DGS aceptado, para decir cuáles son nuevos (RF-17), y ``abiertos_dgs``, lo que ese DGS deja
abierto, para reconocer las transferencias del operador (098:RF-9, RF-14).

Antes de leer deja activas en «Sin» y «Con proyecto» las variaciones propias del conversor (``Fichas_``, ``SED_NTP_``)
que una orden cortada dejara apagadas, y lo dice (083:RF-36); es lo mismo que haría la calibración al empezar
(083:RF-29). Las cargas que dejó a medias una orden interrumpida salen aparte y no como cambiadas a mano (083:RF-35).

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
from _plural import cuenta  # noqa: E402

from convertersmartgrid.aplicacion.escaneo import CLASES_GENERADOR, origen_de  # noqa: E402


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


def _num_o(obj, attr: str, factor: float = 1.0, nd: int = 4):
    v = getattr(obj, attr, None)
    return round(float(v) * factor, nd) if isinstance(v, (int, float)) else None


def _foto(alims, f: str) -> dict:
    """028:RF-45: lo que hay en el alimentador ``f`` en el caso activo, para compararlo con el otro caso."""
    from convertersmartgrid.aplicacion.escaneo import CLASES_FRENTE_AL_BASE

    foto = {}
    for clase in CLASES_FRENTE_AL_BASE:
        try:
            objetos = alims.objetos(f, clase)
        except Exception:  # noqa: BLE001 - una clase que el alimentador no da no impide comparar las demás
            objetos = []
        for o in objetos:
            servicio = not int(getattr(o, 'outserv', 0) or 0)
            if clase == 'ElmLne':
                tipo = getattr(o, 'typ_id', None)
                extremos = []
                for bus in ('bus1', 'bus2'):
                    cub = getattr(o, bus, None)
                    extremos.append(getattr(getattr(cub, 'cterm', None), 'loc_name', None))
                datos = {'tipo': getattr(tipo, 'loc_name', None), 'km': _num_o(o, 'dline'), 'en_servicio': servicio,
                         'ternas': _num_o(o, 'nlnum'), 'desde': extremos[0], 'hasta': extremos[1]}
            elif clase == 'ElmTr2':
                datos = {'tipo': getattr(getattr(o, 'typ_id', None), 'loc_name', None), 'en_servicio': servicio}
            elif clase in ('ElmLod', 'ElmLodlv'):
                datos = {'p_kw': _num_o(o, 'plini', 1000.0, 3), 'q_kvar': _num_o(o, 'qlini', 1000.0, 3),
                         'en_servicio': servicio}
            elif clase == 'ElmShnt':
                datos = {'en_servicio': servicio, 'pasos': _num_o(o, 'ncapa'), 'q_kvar': _num_o(o, 'qtotn', 1000.0, 3)}
            else:
                datos = {'cerrado': bool(int(getattr(o, 'on_off', 1) or 0))}
            foto[(clase, o.loc_name)] = datos
    return foto


def _sumar_frente_al_base(fila: dict, d: dict, de_objeto: dict | None = None) -> None:
    """028:RF-45: las diferencias con el «Caso base» que son del operador, en las columnas que ya pinta la web.

    Lo que graba una variación del conversor (``Fichas_``, ``SED_NTP_``…: en SM218, 26-11, cientos de «AA05003D →
    AA05003D_FICHA») no es del operador y no sale. Las cargas tampoco: en «Sin proyecto» las escribe la calibración
    (306 en SM218), y las que cambió el operador las dice la regla de la última calibración (014:RF-10). Un banco que
    ya está en la lista lleva la marca, sin repetirse.
    """
    de_objeto = de_objeto or {}

    def del_operador(clase: str, nombre: str) -> bool:
        return origen_de(nombre, de_objeto.get((clase, nombre)))['origen'] == 'operador'

    d = {**d,
         'tramos_nuevos': [t for t in d['tramos_nuevos'] if del_operador('ElmLne', t['tramo'])],
         'tramos_cambiados': [t for t in d['tramos_cambiados'] if del_operador('ElmLne', t['tramo'])
                              and not str((t['cambios'].get('tipo') or ('', ''))[1] or '').endswith('_FICHA')],
         'tramos_quitados': [t for t in d['tramos_quitados'] if del_operador('ElmLne', t['tramo'])],
         'cargas_cambiadas': [],
         'bancos_nuevos': [b for b in d['bancos_nuevos'] if del_operador('ElmShnt', b['banco'])],
         'bancos_cambiados': [b for b in d['bancos_cambiados'] if del_operador('ElmShnt', b['banco'])],
         'sed_nuevas': [x for x in d.get('sed_nuevas', []) if del_operador('ElmTr2', x['sed'])],
         'sed_cambiadas': [x for x in d.get('sed_cambiadas', []) if del_operador('ElmTr2', x['sed'])],
         'maniobras_cambiadas': [m for m in d['maniobras_cambiadas']
                                 if del_operador('ElmCoup', m['maniobra']) and del_operador('StaSwitch', m['maniobra'])]}
    listados = {b.get('banco'): b for b in fila.get('bancos') or []}
    for b in d['bancos_nuevos']:
        if b['banco'] in listados:
            listados[b['banco']]['frente_al_caso_base'] = 'nuevo'
    d['bancos_nuevos'] = [b for b in d['bancos_nuevos'] if b['banco'] not in listados]
    ya = {t.get('tramo') for t in fila.get('tramos_nuevos') or []}
    fila['tramos_nuevos'] = list(fila.get('tramos_nuevos') or []) + [
        {**t, 'origen': 'frente al Caso base'} for t in d['tramos_nuevos'] if t['tramo'] not in ya]
    ya = {t.get('tramo') for t in fila.get('tramos_cambiados') or []}
    fila['tramos_cambiados'] = list(fila.get('tramos_cambiados') or []) + [
        {'tramo': t['tramo'], 'tipo': (t['cambios'].get('tipo') or (None, None))[1],
         'km': (t['cambios'].get('km') or (None, None))[1],
         'en_servicio': (t['cambios'].get('en_servicio') or (None, True))[1],
         'variacion': 'frente al Caso base: ' + ', '.join(f'{k} {a} → {b}' for k, (a, b) in t['cambios'].items()),
         'cambios': t['cambios']}
        for t in d['tramos_cambiados'] if t['tramo'] not in ya]
    fila['frente_al_caso_base'] = d

def ejecutar(app, plan: dict) -> tuple[dict, int]:
    """El escaneo de los alimentadores del plan. Devuelve (informe, código)."""
    from ajuste_cabecera_pf import (bancos_instalados, cambios_manuales, cargas_dejadas_a_medias, cargas_sed,
                                    variaciones_del_conversor_activas)
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
    # 083:RF-36: lo que una orden cortada dejó apagado (``Fichas_``, ``SED_NTP_``) se enciende antes de leer, como al
    # empezar la calibración (083:RF-29): con ellas apagadas no se ven la central ni los bancos y el plan sale sin ellos.
    sin = caso_del_sistema(app, 'sin', anio)
    if sin is None and anio is not None:
        # 028:RF-1 (26-11): PA217 se escaneó en «Caso base» porque no tenía «Sin proyecto 2026»; los cambios del
        # operador estaban en su «Sin proyecto» sin año. Sin el del año, el que hay: primero el sin año, luego otro año.
        from casos_pf import NOMBRES, rol_de
        carpeta = app.GetProjectFolder('study')
        otros = [c for c in (carpeta.GetContents('*.IntCase') if carpeta else [])
                 if str(rol_de(c) or '').split('@')[0] == 'sin' or c.loc_name.startswith(NOMBRES['sin'])]
        sin = (caso_del_sistema(app, 'sin', None)
               or max(otros, key=lambda c: c.loc_name, default=None))
        if sin is not None:
            informe['avisos'].append(f'no hay «{NOMBRES["sin"]} {anio}»: se lee «{sin.loc_name}», el que tiene el '
                                     'proyecto.')
    encendidas = variaciones_del_conversor_activas(app, plan['project'], sin, caso_del_sistema(app, 'con', anio))
    if encendidas:
        informe['variaciones_encendidas'] = encendidas
        informe['avisos'].append('Variaciones del conversor que estaban apagadas, activas de nuevo antes de leer: '
                                 + ', '.join(encendidas) + '.')
    base = caso_del_sistema(app, 'base')
    fotos_base = {}
    if sin is not None and base is not None and sin is not base:
        # 028:RF-45: antes de leer «Sin proyecto», lo mismo en el «Caso base», donde el operador no cambia nada.
        base.Activate()
        try:
            app.GetFromStudyCase('ComLdf').Execute()
        except Exception as exc:  # noqa: BLE001 - sin flujo se lee lo que haya
            informe['avisos'].append(f'flujo del «Caso base» antes de comparar: {exc}')
        alims_base = Alimentadores(app, proyecto, feeders)
        fotos_base = {f: _foto(alims_base, f) for f in feeders if f in alims_base.elm}
        informe['comparado_con'] = base.loc_name
    caso = sin or base
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
            # 083:RF-35: las que dejó a medias una orden interrumpida no son cambios del operador.
            a_medias, cortadas = cargas_dejadas_a_medias(plan['project'], f, cargas)
            cambiadas, _nombre = cambios_manuales(cargas, ultimas.get(f), a_medias=cortadas)
            en_barra = _en_barra_de_cabecera(alims, f, de_objeto)
            informe['alimentadores'][f] = {'generadores': _generadores(alims, f, de_objeto),
                                           'generadores_en_barra': en_barra[0], 'bancos_en_barra': en_barra[1],
                                           'bancos': bancos, 'cargas_cambiadas': cambiadas,
                                           'tramos_nuevos': _tramos_nuevos(alims, f, de_dgs, de_objeto)
                                           if de_dgs else [],
                                           'tramos_cambiados': _tramos_cambiados(alims, f, de_dgs,
                                                                                 de_objeto)}
            if a_medias:
                informe['alimentadores'][f]['cargas_de_una_orden_cortada'] = a_medias
            if f in fotos_base:                                                   # 028:RF-45
                from convertersmartgrid.aplicacion.escaneo import diferencias_frente_al_base
                _sumar_frente_al_base(informe['alimentadores'][f],
                                      diferencias_frente_al_base(fotos_base[f], _foto(alims, f)), de_objeto)
        except Exception as exc:  # noqa: BLE001 - un alimentador no tumba el escaneo (RF-8)
            informe['alimentadores'][f] = {'error': f'{type(exc).__name__}: {exc}'}
    _transferencias(app, alims, plan, informe)
    return informe, 0


def _transferencias(app, alims, plan: dict, informe: dict) -> None:
    """098:RF-9: lo que está en un alimentador porque el operador se lo transfirió desde otro.

    CA191 y CHN192 (2026-11-07): con la parte transferida pasaron EBC_1, EBC_2 y EBC_3 a CHN192; sin decirlo, parecían
    bancos que el operador había puesto en CHN192, y los tramos nuevos de la transferencia, una ampliación suya.
    """
    from transferencia_operador_pf import equipos_de_las_zonas, leer_transferencias

    from convertersmartgrid.dominio.transferencia_operador import texto_de_zona

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
    from convertersmartgrid.adaptadores.pf_arnes import PFNoDisponible, conectar

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
            nuevos, cambiados = len(d.get('tramos_nuevos') or []), len(d.get('tramos_cambiados') or [])
            print(f"  {f}: {cuenta(len(d['generadores']), 'generador', 'generadores')}, "
                  f"{cuenta(len(d['bancos']), 'banco', 'bancos')}, "
                  f"{cuenta(len(d['cargas_cambiadas']), 'carga cambiada', 'cargas cambiadas')}, "
                  f"{cuenta(nuevos, 'tramo nuevo', 'tramos nuevos')}, "
                  f"{cuenta(cambiados, 'cambiado', 'cambiados')} a mano", flush=True)
    print(f"Escaneo de {plan.get('project')}: código {codigo}")
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
