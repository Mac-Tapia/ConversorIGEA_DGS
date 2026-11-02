#!/usr/bin/env python
"""Capacidad de alojamiento, curvas PV y ubicación de condensadores de la spec 012.

No se ejecuta solo: ``alojamiento``, ``curvas_pv`` y ``condensadores`` son claves del
``ejecutar`` de ``tools/estudios_pf.py``, que activa el caso, apaga el escalado por
alimentador (``ComHostcap`` y ``ComCapo`` lo exigen apagado, ``err_fls``), comprueba el
flujo y llama aquí (RF-2).

Lo que dio DIgSILENT en la prueba del 2026-10-12 (plan de la spec 012) y se sigue aquí:

- ``ComHostcap.CalcMaxHostedPower(barra)`` → ``[código, P MW, Q, elemento que limita]``; en
  carga, un nodo sin carga conectada da ``[1, 0, 0, None]``: sin elemento no hay límite
  (RF-72). ``objective`` 0 generación, 1 carga. La selección de cargas que crecen a la vez
  es ``selLod`` con ``ioptUsrLod`` («Consider user-defined load selection»,
  ``datascheme.db`` y ``data.db`` de PF 2024): con ella solo crecen las escalables (RF-45).
- ``ComPvcurves`` deja vacío su ``ElmRes`` principal: el resumen se lee de la ventana de
  salida. Con contingencias pide licencia propia (``cCntLic``): sin ella, se calcula sin
  contingencias y se dice (plan, T1).
- ``ComCapo`` con ``iopt_con=1`` instala los bancos; dentro de una variación temporal, al
  borrarla no queda ninguno (RF-55). Sus bancos van en ``shnt*``, con el coste anual que
  calcula ``datos_empresa.anualidad`` (RF-64).

Las opciones enteras que no están en ningún fichero local van por el orden del diálogo (la
primera, 0) y las confirma la prueba real (T13); están juntas en ``OPCIONES_*``.
"""

from __future__ import annotations

import argparse

from cargas_pf import crear_variacion, nombre_libre
from confiabilidad_pf import orden_propia, sin_licencia

from convertersmartgrid import estudios_red_pf as er

#: ``ComHostcap.objective``: 0 generación distribuida, 1 carga nueva (plan).
OBJETIVOS = {'gd': 0, 'carga': 1}
#: ``ioptLoads``: 0 «All loads simultaneously», 1 «Each load separately» (orden del diálogo).
CARGAS_A_LA_VEZ, CARGAS_POR_SEPARADO = 0, 1
#: Solo límites térmicos y de tensión (RF-43): lo demás, apagado.
OPCIONES_HOSTCAP = {'iLoad': 1, 'iVolt': 1, 'ioptProt': 0, 'ioptPqual': 0, 'iopt_shc': 0,
                    'ioptTrip': 0, 'ioptRevFlow': 0, 'ioptFlicker': 0}
#: Por debajo de esta tensión (kV) una barra no es un sitio de media tensión (RF-42).
KV_MINIMO_MT = 1.0
NOMBRE_HOSTCAP = 'Alojamiento_convertersmartgrid'
NOMBRE_PV = 'CurvasPV_convertersmartgrid'
NOMBRE_CAPO = 'Condensadores_convertersmartgrid'
#: ``ComCapo.shnttech``: 0 trifásico, 1 monofásico (orden del diálogo).
TECNOLOGIA = {True: 0, False: 1}


def escalables(elm) -> list:
    """Cargas que crecen: las escalables de la spec 011 (``i_scale`` = 1, RF-19)."""
    return [c for c in elm.GetObjs('ElmLod') if getattr(c, 'i_scale', 1) and not getattr(c, 'outserv', 0)]


def barras_mt(elm) -> list:
    return sorted((b for b in elm.GetObjs('ElmTerm') if (getattr(b, 'uknom', 0) or 0) >= KV_MINIMO_MT),
                  key=lambda b: b.loc_name)


def _seleccion(app, nombre: str, objs: list):
    caso = app.GetActiveStudyCase()
    sel = caso.CreateObject('SetSelect', nombre_libre(caso, 'SetSelect', nombre))
    sel.AddRef(objs)
    return sel


def _limites(orden, plan: dict, pares: dict) -> None:
    lim = plan.get('limites') or {}
    for atributo, clave in pares.items():
        if lim.get(clave) is not None:
            setattr(orden, atributo, float(lim[clave]))


# =========================================================================== alojamiento
def alojamiento(app, plan: dict, alims, feeders: list[str], informe: dict) -> str | None:
    """RF-41 a RF-49, RF-72: generación y carga máximas nodo a nodo, y el crecimiento
    conjunto de las escalables si el operador lo pide."""
    from estudios_pf import _limpiar_salida, _salida

    conjunto = bool((plan.get('opciones') or {}).get('conjunto'))
    orden = orden_propia(app, 'ComHostcap', NOMBRE_HOSTCAP)
    selecciones = []
    try:
        for k, v in OPCIONES_HOSTCAP.items():
            setattr(orden, k, v)
        _limites(orden, plan, {'if_volmin': 'tension_min_pu', 'if_volmax': 'tension_max_pu',
                               'if_load': 'cargabilidad_max_pct'})                         # RF-3
        nodos = []
        for f in feeders:
            elm = alims.elm.get(f)
            if elm is None:
                continue
            for b in barras_mt(elm):
                res = {}
                for clave, objetivo in OBJETIVOS.items():
                    orden.objective = objetivo
                    orden.ioptLoads, orden.ioptUsrLod = CARGAS_POR_SEPARADO, 0           # RF-44
                    _limpiar_salida(app)
                    r = orden.CalcMaxHostedPower(b)
                    if (not r or r[0] == 0) and sin_licencia(_salida(app)):
                        informe['sin_licencia'] = 'ComHostcap'
                        return 'la licencia de DIgSILENT no incluye el módulo ComHostcap'
                    res[clave] = r
                fila = er.nodo_de_capacidad(f, b.loc_name, res['gd'], res['carga'])
                if conjunto:                                                            # RF-45
                    if not selecciones or selecciones[-1][0] != f:
                        selecciones.append((f, _seleccion(app, f'Escalables_{f}', escalables(elm))))
                    orden.objective = OBJETIVOS['carga']
                    orden.ioptLoads, orden.ioptUsrLod, orden.selLod = CARGAS_A_LA_VEZ, 1, selecciones[-1][1]
                    r = orden.CalcMaxHostedPower(b)
                    c = er.nodo_de_capacidad(f, b.loc_name, None, r)
                    fila.update(conjunto_kw=c['carga_kw'], conjunto_motivo=c['carga_motivo'])
                nodos.append(fila)
        informe['nodos'] = nodos
        informe['red'] = {f: d for f, d in er.extremos(nodos).items()}
    finally:
        for _f, s in selecciones:
            s.Delete()
        orden.Delete()
    return None


# =========================================================================== curvas PV
def curvas_pv(app, plan: dict, alims, feeders: list[str], informe: dict) -> str | None:
    """RF-50 a RF-53: una curva PV por alimentador, solo con sus escalables, y con las N-1 de
    su troncal si el operador lo pide y la licencia lo cubre."""
    from estudios_pf import NOMBRE_N1, _limpiar_salida, _salida, tramos_troncales

    contingencias = bool((plan.get('opciones') or {}).get('contingencias'))
    tramos = {}
    if contingencias:
        bbone = app.GetFromStudyCase('ComBbone')
        if bbone is not None:
            bbone.Execute()
            tramos, sin_troncal = tramos_troncales(app, feeders)
            informe['avisos'] += [f'{f}: sin troncal calculada, su curva PV va sin contingencias.'
                                  for f in sin_troncal]
    informe['red'] = {}
    for f in feeders:
        elm = alims.elm.get(f)
        if elm is None:
            continue
        orden = orden_propia(app, 'ComPvcurves', nombre_libre(app.GetActiveStudyCase(), 'ComPvcurves',
                                                              NOMBRE_PV))
        cargas = _seleccion(app, f'PV_cargas_{f}', escalables(elm))
        barras = _seleccion(app, f'PV_barras_{f}', barras_mt(elm))
        n1 = None
        try:
            orden.frLoads, orden.pSel_Load = 1, cargas                                  # RF-51
            orden.frSel_Busb, orden.pSel_Busb = 1, barras
            if tramos.get(f):                                                           # RF-53
                n1 = app.GetActiveStudyCase().CreateObject('ComSimoutage', f'{NOMBRE_N1}_{f}')
                for ln in tramos[f]:
                    n1.CreateObject('ComOutage', ln.loc_name).SetObjs([ln])
                orden.calcCont, orden.pInputCont = 1, n1
            _limpiar_salida(app)
            rc = orden.Execute()
            if rc and n1 is not None and sin_licencia(_salida(app)):
                informe['avisos'].append(f'{f}: la licencia no cubre las curvas PV con contingencias; '
                                         'se calcula sin ellas.')
                informe.setdefault('no_disponible', []).append('curvas PV con contingencias')
                orden.calcCont = 0
                _limpiar_salida(app)
                rc = orden.Execute()
            if rc and sin_licencia(_salida(app)):
                informe['sin_licencia'] = 'ComPvcurves'
                return 'la licencia de DIgSILENT no incluye el módulo ComPvcurves'
            r = er.resumen_pv(_salida(app))
            m = er.margen_pv(r['inicial_kw'], r['critica_kw'])
            informe['red'][f] = {'demanda_inicial_kw': r['inicial_kw'], 'demanda_critica_kw': r['critica_kw'],
                                 **m, 'barra_critica': r['barra_critica'],
                                 'contingencia_critica': r['contingencia_critica'], 'codigo_orden': rc}
        finally:
            for o in (orden, cargas, barras, n1):
                if o is not None:
                    o.Delete()
    return None


# =========================================================================== condensadores
def _shunts(elm) -> dict[str, object]:
    """Bancos del alimentador por su nombre completo: ``ComCapo`` instala en el que optimiza."""
    return {o.GetFullName(): o for o in elm.GetObjs('ElmShnt')}


def _barra_de(sh) -> str | None:
    cub = getattr(sh, 'bus1', None)
    term = cub.GetParent() if cub is not None else None
    return getattr(term, 'loc_name', None)


def condensadores(app, plan: dict, alims, feeders: list[str], informe: dict) -> str | None:
    """RF-54 a RF-57, RF-66: ``ComCapo`` por alimentador en una variación temporal que se
    borra; se leen los bancos que instaló y el coste de pérdidas antes y después."""
    from estudios_pf import _limpiar_salida, _salida

    libro = plan.get('libro') or {}
    bancos = list(libro.get('bancos') or ())
    informe['red'] = {}
    carpeta = app.GetProjectFolder('scheme')
    for f in feeders:
        elm = alims.elm.get(f)
        if elm is None:
            continue
        previas = {v.loc_name for v in carpeta.GetContents('*.IntScheme', 1)}
        antes = _shunts(elm)
        orden = orden_propia(app, 'ComCapo', nombre_libre(app.GetActiveStudyCase(), 'ComCapo', NOMBRE_CAPO))
        try:
            crear_variacion(app, f'Condensadores_temporal_{f}', plan.get('stamp') or 'capo')   # RF-55
            orden.feeder, orden.iopt_con = getattr(elm, 'crudo', elm), 1
            orden.ecost = float(libro.get('coste_energia_kwh') or 0.0)                       # RF-15
            _limites(orden, plan, {'vmin': 'tension_min_pu', 'vmax': 'tension_max_pu'})       # RF-3
            orden.shntqstep = [b['potencia_kvar'] / 1000.0 for b in bancos]
            orden.shntmxsteps = [int(b['pasos']) for b in bancos]
            orden.shntswitch = [1 if int(b['pasos']) > 1 else 0 for b in bancos]
            orden.shnttech = [TECNOLOGIA[bool(b['trifasico'])] for b in bancos]
            orden.shntcost = [float(b['coste_anual'] or 0.0) for b in bancos]               # RF-64
            orden.shntignored = [0 for _ in bancos]
            coste_antes = orden.TotalLossCost()
            _limpiar_salida(app)
            rc = orden.Execute()
            if rc and sin_licencia(_salida(app)):
                informe['sin_licencia'] = 'ComCapo'
                return 'la licencia de DIgSILENT no incluye el módulo ComCapo'
            coste_despues = orden.TotalLossCost()
            nuevos = [o for k, o in _shunts(elm).items() if k not in antes]
            instalados = [{'nodo': _barra_de(sh), 'kvar_paso': float(getattr(sh, 'qcapn', 0.0) or 0.0) * 1000.0,
                           'pasos': int(getattr(sh, 'ncapa', 0) or getattr(sh, 'ncapx', 0) or 0)}
                          for sh in nuevos]
            fila = er.informe_bancos(f, instalados, bancos, coste_antes, coste_despues,
                                     str(libro.get('moneda') or ''), libro.get('tasa_descuento'))
            fila['codigo_orden'] = rc
            informe['red'][f] = fila
            if fila['aviso']:
                informe['avisos'].append(fila['aviso'])
        finally:
            for v in carpeta.GetContents('*.IntScheme', 1):
                if v.loc_name not in previas:
                    v.Deactivate()
                    v.Delete()
            orden.Delete()
    return None


def main(argv=None) -> int:
    """Sin uso propio: lo dice y remite a ``tools/estudios_pf.py``."""
    p = argparse.ArgumentParser(description='Capacidad de alojamiento, curvas PV y condensadores '
                                            '(spec 012). Se ejecutan con tools/estudios_pf.py, '
                                            'estudios alojamiento, curvas_pv y condensadores.')
    p.parse_args(argv)
    print('Use tools/estudios_pf.py con el estudio alojamiento, curvas_pv o condensadores.')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
