#!/usr/bin/env python
"""Cortocircuito y simulación cuasi-dinámica con lo que el operador cargó en la web (spec 012,
RF-83 a RF-86).

``cortocircuito`` y ``cuasi_dinamica`` son claves del ``ejecutar`` de ``tools/estudios_pf.py``:
ese guion activa el caso («Sin proyecto», «Cargas nuevas» o «Con proyecto», nunca el «Caso
base»), comprueba que el flujo converge y llama aquí, dentro de ``_estudio_de_red``, que al
terminar comprueba que ninguna demanda, variación, hora ni etapa quedó cambiada (RF-60, spec 064).

Por qué en una variación temporal: la sonda del 2026-11-13 en CA101_CHN102 mostró una red externa
por alimentador («External Grid CA101», en la barra de cabecera de 10 kV) con los valores por
defecto de DIgSILENT (``snss`` = 10 000 MVA, ``rntxn`` = 0,1, ``snssmin`` = 8 000). La Pcc
confirmada en la web se escribe en esa red externa dentro de una variación que graba solo durante
el estudio y se borra al terminar: la red, y con ella el «Caso base», vuelve a lo que era, y se
comprueba atributo por atributo. Las características de tiempo de la cuasi-dinámica se crean en una
carpeta propia de la biblioteca del proyecto, se asignan a las cargas y se borran al terminar,
igual que la orden ``ComStatsim`` propia del caso.

Los códigos de ``ChaTime`` son los de las curvas de la biblioteca global de PF 2024 que se leyeron
en esa sonda («Winter_Werktag»: ``source`` 0 tabla, ``repeat`` 0 diaria, ``unit`` 0 con
``stepSize`` 15 para sus 96 valores de 15 minutos, ``usage`` 1). Por eso esta iteración admite
solo perfiles de un día; uno más largo lo dice el informe en vez de escribirse con un código que
nadie comprobó.

    python tools/estudios_entradas_pf.py --help     (lo ejecuta tools/estudios_pf.py)
"""

from __future__ import annotations

import argparse

from convertersmartgrid import entradas_estudios as ee

#: Nombres de lo que crea el estudio en el proyecto; todo se borra al terminar.
NOMBRE_SHC = 'CSG_cortocircuito'
NOMBRE_STATSIM = 'CSG_cuasi_dinamica'
CARPETA_PERFILES = 'CSG_perfiles_temporales'
#: Atributos de ``ElmXnet`` que se fotografían y se comparan al terminar (datascheme.db de PF 2024).
ATRIBUTOS_XNET = ('snss', 'rntxn', 'snssmin', 'rntxnmin', 'x0tx1', 'r0tx0')
#: Códigos de ``ChaTime`` leídos en la biblioteca global de PF 2024 (sonda del 2026-11-13).
CHATIME = {'source': 0, 'repeat': 0, 'unit': 0, 'usage': 1}
#: ``ComShc.iopt_allbus``: falla en barras **y nodos de unión**. La orden nueva trae 2 (solo barras), y en la
#: copia de CA101_CHN102 (2026-11-13) dejó sin calcular los 385 nodos de media tensión del alimentador,
#: también la barra de cabecera: solo salían las barras de baja de las SED.
FALLA_EN_BARRAS_Y_NODOS = 1
#: Resultados del cortocircuito por barra: corriente inicial y potencia (manual §25).
VARIABLES_SHC = ('m:Ikss', 'm:Skss')


def _num(obj, atributo):
    from cargas_pf import _num as num

    return num(obj, atributo)


def nombres_xnet(x) -> list[str]:
    """Con qué nombres puede venir una red externa en la tabla del operador: el suyo, el del
    alimentador que alimenta («External Grid CA101» → «CA101»), el de su barra y el de la
    subestación que la contiene."""
    nombres = [x.loc_name]
    if x.loc_name.lower().startswith('external grid '):
        nombres.append(x.loc_name[len('external grid '):])
    bus = getattr(x, 'bus1', None)
    term = getattr(bus, 'cterm', None) if bus is not None else None
    if term is not None:
        nombres.append(term.loc_name)
        padre = term.GetParent() if hasattr(term, 'GetParent') else None
        if padre is not None and padre.GetClassName() in ('ElmSubstat', 'ElmTrfstat'):
            nombres.append(padre.loc_name)
    return nombres


def redes_externas(app) -> list:
    return [x for x in (app.GetCalcRelevantObjects('*.ElmXnet') or []) if not getattr(x, 'outserv', 0)]


def _foto_xnet(xnets) -> dict:
    return {x.loc_name: {a: getattr(x, a, None) for a in ATRIBUTOS_XNET} for x in xnets}


def _temporal(app, estudio: str, stamp: str):
    from cargas_pf import crear_variacion

    carpeta = app.GetProjectFolder('scheme')
    previas = {v.GetFullName() for v in carpeta.GetContents('*.IntScheme', 1)}
    caso = app.GetActiveStudyCase()
    hora = getattr(caso, 'iStudyTime', None) if caso is not None else None
    grabando = app.GetRecordingStage()
    variacion, _etapa = crear_variacion(app, f'Estudio_{estudio}', stamp or '')
    return {'carpeta': carpeta, 'previas': previas, 'caso': caso, 'hora': hora, 'grabando': grabando,
            'variacion': variacion}


def _deshacer(app, t: dict) -> None:
    """Borra la variación temporal (y cualquiera que el estudio creara) y devuelve hora y etapa."""
    nombre = t['variacion'].GetFullName() if t['variacion'] is not None else None
    for v in t['carpeta'].GetContents('*.IntScheme', 1):
        if v.GetFullName() not in t['previas'] or v.GetFullName() == nombre:
            v.Deactivate()
            v.Delete()
    if t['caso'] is not None and t['hora'] is not None and getattr(t['caso'], 'iStudyTime', None) != t['hora']:
        t['caso'].iStudyTime = t['hora']
    if t['grabando'] is not None and app.GetRecordingStage() is not t['grabando']:
        t['grabando'].Activate(1)


def cortocircuito(app, plan: dict, alims, feeders: list[str], informe: dict) -> str | None:
    """RF-83: Pcc confirmada en cada red externa, ``ComShc`` propio y corrientes por barra.

    Si una red externa del caso no tiene su Pcc cargada, no se estudia: con los 10 000 MVA por
    defecto saldrían corrientes de falla que no son las de esa SET, y el informe las mostraría
    junto a las reales sin distinguirlas.
    """
    registro = ((plan.get('entradas') or {}).get('impedancia') or {}).get('registro')
    if not registro:
        return 'falta la potencia de cortocircuito de las SET de cabecera: cárguela en la web'
    from confiabilidad_pf import orden_propia
    from estudios_pf import _limpiar_salida, _salida

    xnets = redes_externas(app)
    asignadas, sin = {}, []
    for x in xnets:
        d = ee.impedancia_para(registro, nombres_xnet(x))
        (asignadas.__setitem__(x.loc_name, (x, d)) if d is not None else sin.append(x.loc_name))
    if sin:
        return ('faltan las Pcc de ' + ', '.join(sorted(sin)) + ': no se estudia con los valores por defecto '
                'de DIgSILENT')
    antes = _foto_xnet(xnets)
    t = _temporal(app, 'cortocircuito', plan.get('stamp') or '')
    orden = None
    try:
        escritos = {}
        for nombre, (x, d) in asignadas.items():
            escritos[nombre] = {}
            for atributo, valor in ee.atributos_xnet(d).items():
                if x.HasAttribute(atributo):
                    setattr(x, atributo, valor)
                    escritos[nombre][atributo] = valor
            escritos[nombre]['fila'] = d.get('fila')
        informe['pcc_aplicada'] = escritos
        orden = orden_propia(app, 'ComShc', NOMBRE_SHC)
        if orden.HasAttribute('iopt_allbus'):
            orden.iopt_allbus = FALLA_EN_BARRAS_Y_NODOS
        informe['opciones_shc'] = {a: getattr(orden, a, None) for a in ('iopt_mde', 'iopt_shc', 'iopt_cur', 'iopt_allbus')}
        _limpiar_salida(app)
        rc = informe['codigo_orden'] = orden.Execute()
        if rc:
            informe['salida'] = _salida(app)
            return f'ComShc terminó con el código {rc}'
        informe['cortocircuito'] = {f: resumen_cortocircuito(alims.objetos(f, 'ElmTerm')) for f in feeders}
        # La corriente en la barra de cada red externa: la que se compara con la del COES.
        informe['cabeceras'] = {}
        for nombre, (x, _d) in asignadas.items():
            term = getattr(getattr(x, 'bus1', None), 'cterm', None)
            if term is not None:
                informe['cabeceras'][nombre] = {'barra': term.loc_name, 'ikss_ka': _num(term, 'm:Ikss'),
                                                'skss_mva': _num(term, 'm:Skss')}
    finally:
        if orden is not None:
            orden.Delete()
        _deshacer(app, t)
        despues = _foto_xnet(redes_externas(app))
        cambiadas = sorted(n for n in antes if antes[n] != despues.get(n))
        if cambiadas:
            # spec 064: el estado se restituye; si la variación no bastó, se escribe lo de antes.
            for x in redes_externas(app):
                for a, v in antes.get(x.loc_name, {}).items():
                    if v is not None and getattr(x, a, None) != v:
                        setattr(x, a, v)
            informe['fiable'] = False
            informe['avisos'].append('La Pcc de ' + ', '.join(cambiadas) + ' no volvió sola al borrar la '
                                     'variación temporal; se escribió la de antes y el resultado queda como no fiable.')
    return None


def resumen_cortocircuito(terminales) -> dict:
    """Corriente y potencia de falla por barra, de mayor a menor, y los extremos.

    Una barra con Ik" = 0 no tiene falla calculada (sin tensión, o fuera de la selección de la orden;
    CA101, 2026-11-13): se cuenta aparte y no es la mínima, que es la que decide el ajuste de protecciones.
    """
    barras, sin_tension = [], []
    for b in terminales:
        ik, sk = (_num(b, v) for v in VARIABLES_SHC)
        if ik is None:
            continue
        if ik <= 0:
            sin_tension.append(b.loc_name)
            continue
        barras.append([b.loc_name, round(ik, 6), None if sk is None else round(sk, 6)])
    barras.sort(key=lambda r: (-r[1], r[0]))
    minima = min(barras, key=lambda r: (r[1], r[0])) if barras else None
    return {'barras': barras, 'sin_corriente': sorted(sin_tension),
            'ikss_max_ka': barras[0][1] if barras else None, 'barra_max': barras[0][0] if barras else None,
            'ikss_min_ka': minima[1] if minima else None, 'barra_min': minima[0] if minima else None}


def _cargas_con_perfil(alims, feeders, registro) -> tuple[list, list[str]]:
    con, sin = [], []
    for f in feeders:
        for c in alims.objetos(f, 'ElmLod'):
            tipo = getattr(getattr(c, 'typ_id', None), 'loc_name', None)
            p = ee.perfil_para(registro, [f, tipo])
            (con.append((c, p)) if p is not None else sin.append(c.loc_name))
    return con, sorted(set(sin))


def cuasi_dinamica(app, plan: dict, alims, feeders: list[str], informe: dict) -> str | None:
    """RF-84: perfiles confirmados como características de tiempo de las cargas y ``ComStatsim``.

    Cada carga sin perfil lo dice: correrla constante sería suponerle una curva plana.
    """
    registro = ((plan.get('entradas') or {}).get('perfiles') or {}).get('registro')
    if not registro:
        return 'faltan los perfiles de carga: cárguelos en la web'
    largos = sorted(p['perfil'] for p in (registro.get('perfiles') or {}).values() if p['horas'] != 24)
    if largos:
        return ('esta iteración usa perfiles de un día (24 h); estos traen otra duración: ' + ', '.join(largos))
    from cargas_pf import nombre_pf
    from confiabilidad_pf import orden_propia
    from estudios_pf import _limpiar_salida, _salida

    con, sin = _cargas_con_perfil(alims, feeders, registro)
    # CA101_CHN102 (2026-11-13): 204 cargas en la red y 203 en sus dos ElmFeeder; la que queda
    # fuera sigue constante, y se dice en vez de callarlo.
    fuera = len(app.GetCalcRelevantObjects('*.ElmLod') or []) - len(con) - len(sin)
    if fuera > 0:
        informe['avisos'].append(f'{fuera} carga(s) fuera de los alimentadores estudiados quedan con su demanda '
                                 'constante en la cuasi-dinámica.')
    if sin:
        return (f'{len(sin)} carga(s) sin perfil de su alimentador ni de su tipo: ' + ', '.join(sin[:20])
                + ('…' if len(sin) > 20 else ''))
    biblioteca = app.GetProjectFolder('chars') or app.GetProjectFolder('lib')
    if biblioteca is None:
        return 'el proyecto no tiene carpeta de características'
    t = _temporal(app, 'cuasi_dinamica', plan.get('stamp') or '')
    carpeta, refs, orden = None, [], None
    try:
        carpeta = biblioteca.CreateObject('IntFolder', CARPETA_PERFILES)
        caracteristicas = {}
        for _c, p in con:
            if p['perfil'] in caracteristicas:
                continue
            ch = carpeta.CreateObject('ChaTime', nombre_pf(p['perfil']))
            for a, v in CHATIME.items():
                setattr(ch, a, v)
            ch.stepSize = p['paso_min']
            ch.vector = list(p['pu'])
            caracteristicas[p['perfil']] = ch
        for c, p in con:
            for atributo in ('plini', 'qlini'):
                ref = c.CreateObject('ChaRef', atributo)
                ref.typ_id = caracteristicas[p['perfil']]
                refs.append(ref)
        informe['perfiles_aplicados'] = {n: sum(1 for _c, p in con if p['perfil'] == n) for n in caracteristicas}
        orden = orden_propia(app, 'ComStatsim', NOMBRE_STATSIM)
        informe['opciones_statsim'] = {a: getattr(orden, a, None) for a in ('calcPeriod', 'stepSize', 'stepUnit')}
        _limpiar_salida(app)
        rc = informe['codigo_orden'] = orden.Execute()
        informe['salida'] = _salida(app)
        if rc:
            return f'ComStatsim terminó con el código {rc}'
        informe['cuasi_dinamica'] = leer_resultados(getattr(orden, 'results', None), feeders)
    finally:
        for ref in refs:
            ref.Delete()
        if orden is not None:
            orden.Delete()
        if carpeta is not None:
            carpeta.Delete()
        _deshacer(app, t)
    return None


def leer_resultados(res, feeders: list[str]) -> dict:
    """Mínimo, máximo y media de cada variable que ``ComStatsim`` dejó en su ``ElmRes``, por objeto.

    No se presupone qué variables graba: se leen las que hay (``GetNumberOfColumns``,
    ``GetObject``, ``GetVariable``, ``GetValue``, referencia de Python de PF 2024).
    """
    if res is None:
        return {'variables': [], 'aviso': 'ComStatsim no dejó fichero de resultados'}
    res.Load()
    filas, columnas = res.GetNumberOfRows(), res.GetNumberOfColumns()
    salida = []
    for col in range(columnas):
        obj = res.GetObject(col)
        valores = []
        for fila in range(filas):
            err, v = res.GetValue(fila, col)
            if not err and v is not None:
                valores.append(float(v))
        if valores:
            salida.append({'objeto': getattr(obj, 'loc_name', None), 'clase': obj.GetClassName() if obj else None,
                           'variable': res.GetVariable(col), 'min': min(valores), 'max': max(valores),
                           'media': sum(valores) / len(valores), 'pasos': len(valores)})
    por_alimentador = {}
    for v in salida:
        if v['clase'] == 'ElmFeeder' and v['objeto'] in feeders:
            por_alimentador.setdefault(v['objeto'], {})[v['variable']] = {k: v[k] for k in ('min', 'max', 'media')}
    return {'variables': salida, 'pasos': filas, 'por_alimentador': por_alimentador}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Cortocircuito y cuasi-dinámica con las entradas cargadas en la web '
                                            '(spec 012); los ejecuta tools/estudios_pf.py')
    p.parse_args(argv)
    p.error('este guion no se ejecuta solo: lo llama tools/estudios_pf.py con los estudios «cortocircuito» y '
            '«cuasi_dinamica»')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
