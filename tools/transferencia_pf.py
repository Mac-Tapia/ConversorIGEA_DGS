#!/usr/bin/env python
"""Transferencia de carga entre dos alimentadores en DIgSILENT (spec 011, RF-104 a RF-121).

Cuánta carga puede pasar un alimentador a otro por su punto de enlace, y hasta qué
seccionador o nodo, en los dos sentidos. DIgSILENT no tiene un comando que lo dé
(``ComTransfer`` escala cargas sin maniobrar y ``ComBbone`` solo prueba el paso del
alimentador entero), así que se construye sobre el camino que sí da (plan de la spec):

1. En cada caso pedido, ``ComBbone`` deja las troncales entre los dos alimentadores; cada
   una con su punto de enlace normalmente abierto (RF-106). Las troncales que crea el
   cálculo se borran al leerlas.
2. Por sentido y enlace, el camino es el de la troncal del que cede, del enlace a su
   cabecera (RF-108). Cada barra lleva la carga que cuelga de ella, derivaciones
   incluidas; cada seccionador del camino (``aUsage='dct'`` del DGS, o el número de
   equipo de la entrada cargada) es un punto de maniobra (RF-118, RF-128). Fusibles,
   interruptores, reconectadores y seccionalizadores no cuentan.
3. Se cierra el enlace y, uno tras otro desde el enlace hacia la cabecera, se abre cada
   punto —el seccionador, o el tramo aguas arriba de la barra fuera de servicio para el
   resultado por nodos (RF-113)— con un flujo de carga en cada paso (RF-109). La medida
   de cada paso es la del alimentador que recibe más la parte transferida.
4. ``igea_dgs.transferencia_pf`` juzga cada paso y resume el sentido (RF-110 a RF-117,
   RF-129).
5. En la configuración del seccionador viable más lejano, la capacidad del enlace: hasta
   dónde puede subir la carga de la parte transferida sin pasar un límite del que recibe
   ni de esa parte (RF-122, RF-127), y el margen sobre lo que ya transfiere (RF-123). Con
   el análisis de capacidad de transferencia de DIgSILENT (``ComTransfer``, por
   elementos, con una frontera temporal en el enlace) si la licencia lo tiene y da una
   solución viable (RF-124); si no, por flujos sucesivos subiendo el factor de escala
   de esas cargas (``scale0``), que da la misma cifra (RF-125). El informe dice el
   método. Nada del punto escalado se guarda (RF-126).

Nada se queda en el proyecto (RF-119, RF-120): las maniobras se hacen en una variación
temporal, con el escenario del caso apagado sin guardar (como las demandas de la spec
004), y al terminar cada caso se restituye cada interruptor y cada tramo, se comprueba,
se borra la variación temporal y vuelven el escenario y la etapa que grababa. También si
se cancela o algo falla.

    python tools/transferencia_pf.py --plan plan.json --output-json informe.json
        [--fichero transferencias.csv] [--cancel-file cancelar.flag]

El plan lleva ``project``, ``folder``, ``feeders`` (los dos alimentadores), ``casos``
(«Sin proyecto», «Con proyecto» o los dos), y, si se quieren, ``limites`` (los de los
estudios, RF-35) y ``seccionadores`` (números de equipo de la entrada cargada, para un
proyecto convertido antes de que el DGS distinguiera los seccionadores, RF-129).

Códigos de salida: 0 hecho, 2 no se pudo (el informe dice por qué), 3 sin API.
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import Any

from cargas_pf import (
    clave_pf,
    Alimentadores, _num, activar_proyecto, crear_variacion, error_inesperado, flujo_de_carga,
    potencia,
)
from casos_pf import NOMBRES, tres_casos
from estudios_pf import medida

from igea_dgs.estudios_pf import EstudiosError, limites_de_perfil
from igea_dgs.native_action import native_action_block_report
from igea_dgs.transferencia_pf import (
    NODO, SECCIONADOR, Punto, escribir_fichero, juzgar, margen, maximo_factor,
    pasos_del_camino, resumir_sentido,
)

#: Nombre de caso → su rol en ``casos_pf``.
ROL_DE_CASO = {nombre: rol for rol, nombre in NOMBRES.items()}
#: ``aUsage`` con que el DGS escribe un seccionador del export (011:RF-128).
USO_SECCIONADOR = 'dct'
#: Ramas de un camino que se pueden sacar de servicio para el resultado por nodos.
RAMAS = ('ElmLne', 'ElmCoup', 'ElmTr2')
#: Lo que el guion crea para ``ComTransfer`` y borra al terminar.
NOMBRE_TC = 'Capacidad_enlace_igea_dgs'
#: Opciones de ``ComTransfer`` (etiquetas de ``localisation/en-GB/data.db`` de PF 2024, en
#: su orden: la API no da los valores; los confirma la prueba real, T19).
TC_POR_ELEMENTOS = 1          # iopt_method: «Element selection»
TC_NO_GUARDAR = 0             # iSave: «Do not save» (RF-126)
TC_LIMITE_GLOBAL = 0          # iLoad e iVolt: «Global constraint for all …»


# =========================================================================== red
class Red:
    """Barras, cubículos y elementos de un alimentador, para recorrerlo.

    Las barras de baja de las SED no son del ``ElmFeeder``: se llega a ellas por el lado
    de baja de cada transformador (``buslv``), para contar las cargas que cuelgan allí.
    """

    def __init__(self, elm):
        self.elm = elm
        self.cubiculos: dict[int, list] = {}
        self.extremos: dict[int, list] = {}
        self.cargas = {clave_pf(c) for c in elm.GetObjs('ElmLod')}
        pendientes = list(elm.GetObjs('ElmTerm'))
        cabecera = getattr(getattr(elm, 'obj_id', None), 'cterm', None)
        if cabecera is not None:
            pendientes.append(cabecera)
        vistas: set[int] = set()
        while pendientes:
            barra = pendientes.pop()
            if clave_pf(barra) in vistas:
                continue
            vistas.add(clave_pf(barra))
            self.cubiculos[clave_pf(barra)] = list(barra.GetContents('*.StaCubic') or [])
            for cub in self.cubiculos[clave_pf(barra)]:
                e = getattr(cub, 'obj_id', None)
                if e is None:
                    continue
                self.extremos.setdefault(clave_pf(e), []).append((barra, cub))
                if e.GetClassName() == 'ElmTr2':
                    for lado in ('bushv', 'buslv'):
                        otra = getattr(getattr(e, lado, None), 'cterm', None)
                        if otra is not None and clave_pf(otra) not in vistas:
                            pendientes.append(otra)

    def interruptores(self) -> list:
        """Los ``StaSwitch`` de los cubículos del alimentador y sus ``ElmCoup``."""
        out = [sw for cubs in self.cubiculos.values() for c in cubs
               for sw in (c.GetContents('*.StaSwitch') or [])]
        out += [e for e in (self._elemento(i) for i in self.extremos)
                if e is not None and e.GetClassName() == 'ElmCoup']
        return out

    def _elemento(self, ident: int):
        lados = self.extremos.get(ident)
        return getattr(lados[0][1], 'obj_id', None) if lados else None

    def abierto(self, cub) -> bool:
        """Un cubículo cortado por su interruptor, o un elemento abierto o fuera de servicio."""
        if any(not getattr(sw, 'on_off', 1) for sw in cub.GetContents('*.StaSwitch') or []):
            return True
        e = getattr(cub, 'obj_id', None)
        return bool(getattr(e, 'outserv', 0)) or (
            e is not None and e.GetClassName() == 'ElmCoup' and not getattr(e, 'on_off', 1))

    def colgado(self, barra, camino: set[int]) -> tuple[float, float, list, list, list]:
        """Lo que cuelga de una barra del camino sin pasar por el camino: kW, kvar, barras,
        elementos y cargas. Es lo que pasa al otro alimentador junto con la barra."""
        kw = kvar = 0.0
        barras, elementos, cargas = [], [], []
        vistas, pendientes = {clave_pf(barra)}, [barra]
        while pendientes:
            b = pendientes.pop()
            for cub in self.cubiculos.get(clave_pf(b), []):
                e = getattr(cub, 'obj_id', None)
                if e is None or clave_pf(e) in camino or self.abierto(cub):
                    continue
                if clave_pf(e) in self.cargas:
                    p, q = potencia(e)
                    kw, kvar = kw + p, kvar + q
                    if all(clave_pf(x) != clave_pf(e) for x in cargas):
                        cargas.append(e)
                    continue
                if all(clave_pf(x) != clave_pf(e) for x in elementos):
                    elementos.append(e)
                for otra, _c in self.extremos.get(clave_pf(e), []):
                    if clave_pf(otra) not in vistas and clave_pf(otra) not in camino:
                        vistas.add(clave_pf(otra))
                        barras.append(otra)
                        pendientes.append(otra)
        return kw, kvar, barras, elementos, cargas


def es_seccionador(sw, entrada: set[str]) -> bool:
    """Seccionador por el uso que le dio el DGS o por la entrada cargada (RF-118, RF-128)."""
    return getattr(sw, 'aUsage', '') == USO_SECCIONADOR or sw.loc_name in entrada


def distingue(red: Red, entrada: set[str]) -> bool:
    """Si el proyecto distingue los seccionadores (RF-129).

    Antes de RF-128 el DGS escribía todos los equipos del export como ``cbk``: sin ningún
    otro uso entre ellos ni entrada cargada, no se sabe cuáles son seccionadores.
    """
    usos = {getattr(sw, 'aUsage', 'cbk') for sw in red.interruptores()
            if sw.GetClassName() == 'StaSwitch'}
    return bool(entrada) or not usos or usos != {'cbk'}


class Camino:
    """Del enlace hacia la cabecera del que cede, con lo que se abre en cada punto."""

    def __init__(self, red: Red, objetos: list, enlace, entrada: set[str], reconoce: bool):
        objetos = [o for o in reversed(objetos) if clave_pf(o) != clave_pf(enlace)]
        self.ids = {clave_pf(o) for o in objetos}
        self.puntos: list[Punto] = []
        self.accion: dict[str, tuple] = {}
        #: Por punto, las barras, elementos y cargas que ya han pasado al que recibe.
        self.transferido: dict[str, tuple[list, list, list]] = {}
        barras_t, elementos_t, cargas_t = [], [], []
        ultima = None
        for i, o in enumerate(objetos):
            if o.GetClassName() == 'ElmTerm':
                ultima = o
                aguas_arriba = next((r for r in objetos[i + 1:] if r.GetClassName() in RAMAS), None)
                if aguas_arriba is None:
                    continue              # la cabecera: abrir aguas arriba es el alimentador entero
                kw, kvar, barras, elementos, cargas = red.colgado(o, self.ids)
                barras_t += [o, *barras]
                elementos_t += elementos
                cargas_t += cargas
                self.puntos.append(Punto(o.loc_name, NODO, kw, kvar))
                self.accion[o.loc_name] = (aguas_arriba, 'outserv', 1)
                self.transferido[o.loc_name] = (list(barras_t), list(elementos_t), list(cargas_t))
                continue
            if ultima is None:
                continue
            elementos_t.append(o)
            if not reconoce:
                continue
            for _barra, cub in red.extremos.get(clave_pf(o), []):
                for sw in cub.GetContents('*.StaSwitch') or []:
                    if es_seccionador(sw, entrada) and sw.loc_name not in self.accion:
                        self.puntos.append(Punto(sw.loc_name, SECCIONADOR))
                        self.accion[sw.loc_name] = (sw, 'on_off', 0)
                        self.transferido[sw.loc_name] = (list(barras_t), list(elementos_t),
                                                         list(cargas_t))
            if o.GetClassName() == 'ElmCoup' and es_seccionador(o, entrada):
                self.puntos.append(Punto(o.loc_name, SECCIONADOR))
                self.accion[o.loc_name] = (o, 'on_off', 0)
                self.transferido[o.loc_name] = (list(barras_t), list(elementos_t), list(cargas_t))


# =========================================================================== cálculo
def _troncales(app, cede: str, recibe: str) -> tuple[dict[str, tuple], list]:
    """Enlace → (troncal desde ``cede``, objeto de enlace), y las troncales creadas."""
    previas = {clave_pf(b) for b in app.GetCalcRelevantObjects('*.ElmBbone')}
    bbone = app.GetFromStudyCase('ComBbone')
    if bbone is None:
        raise RuntimeError('el caso no admite la orden ComBbone: sin troncal no hay camino')
    bbone.Execute()
    creadas = [b for b in app.GetCalcRelevantObjects('*.ElmBbone') if clave_pf(b) not in previas]
    out = {}
    for b in app.GetCalcRelevantObjects('*.ElmBbone'):
        desde = getattr(getattr(b, 'pBbStart', None), 'loc_name', None)
        hasta = getattr(getattr(b, 'pBbEnd', None), 'loc_name', None)
        if (desde, hasta) != (cede, recibe):
            continue
        enlace = b.GetTieOpenPoint()
        if enlace is not None and enlace.loc_name not in out:
            out[enlace.loc_name] = (b, enlace)
    return out, creadas


def _medir(elm_recibe, transferido: tuple) -> dict[str, Any]:
    """La del que recibe (``estudios_pf.medida``) más la parte transferida (RF-111)."""
    m = medida(elm_recibe)
    nombres = {n for n, _ in m['barras']}
    for b in transferido[0]:
        u = _num(b, 'm:u') if b.HasResults() else None
        if u is not None and b.loc_name not in nombres:
            m['barras'].append((b.loc_name, u))
    vistos = {n for n, _c, _v in m['elementos']}
    for e in transferido[1]:
        carga = _num(e, 'c:loading')
        if carga is not None and e.loc_name not in vistos:
            m['elementos'].append((e.loc_name, e.GetClassName(), carga))
    return m


def _seleccion(caso, nombre: str, objetos: list):
    sel = caso.CreateObject('SetSelect', nombre)
    sel.AddRef(objetos)
    return sel


def _con_comtransfer(app, red_recibe: 'Red', transferido: tuple, resto: list, enlace,
                     limites) -> tuple[float | None, str]:
    """Capacidad del enlace con ``ComTransfer`` por elementos (RF-124), en kW, o el motivo.

    Importan las cargas de la parte transferida; exportan las del resto del que cede
    (bajarlas no limita nada del que recibe); la frontera es un ``ElmBoundary`` temporal
    con el cubículo del enlace en el lado del que recibe; las restricciones, solo sobre el
    que recibe y la parte transferida (RF-127). Todo lo creado se borra al terminar.
    """
    caso = app.GetActiveStudyCase()
    cub_enlace = next((c for _b, c in red_recibe.extremos.get(clave_pf(enlace), [])), None)
    if cub_enlace is None:
        return None, 'el enlace no tiene cubículo en el alimentador que recibe'
    creados = []
    try:
        orden = caso.CreateObject('ComTransfer', NOMBRE_TC)
        creados.append(orden)
        frontera = cub_enlace.cterm.GetParent().CreateObject('ElmBoundary', NOMBRE_TC)
        creados.append(frontera)
        frontera.AddCubicle(cub_enlace)
        vigilados = ([*red_recibe.elm.GetObjs('ElmTerm'), *red_recibe.elm.GetObjs('ElmLne'),
                      *red_recibe.elm.GetObjs('ElmTr2')] + transferido[0] + transferido[1])
        importa = _seleccion(caso, f'{NOMBRE_TC}_importa', transferido[2])
        exporta = _seleccion(caso, f'{NOMBRE_TC}_exporta', resto)
        vigila = _seleccion(caso, f'{NOMBRE_TC}_vigila', vigilados)
        creados += [importa, exporta, vigila]
        orden.iopt_method, orden.iSave = TC_POR_ELEMENTOS, TC_NO_GUARDAR
        orden.p_impElms, orden.p_expElms, orden.p_boundary = importa, exporta, frontera
        orden.isScaleLod, orden.isScaleGen = 1, 0
        orden.iopt_selreg, orden.psel_elms = 1, vigila
        orden.iopt_lodcons, orden.iopt_volcons = 1, 1
        orden.iLoad, orden.iVolt = TC_LIMITE_GLOBAL, TC_LIMITE_GLOBAL
        orden.if_load = limites.cargabilidad_max_pct
        orden.if_volmin, orden.if_volmax = limites.tension_min_pu, limites.tension_max_pu
        rc = orden.Execute()
        if rc != 0:
            return None, f'ComTransfer terminó con el código {rc}'
        if not orden.IsLastIterationFeasible():
            return None, 'ComTransfer no encontró una solución viable'
        capacidad_mw = orden.GetTransferCalcData()[0]
        return float(capacidad_mw) * 1000.0, ''
    except Exception as exc:  # noqa: BLE001 - sin licencia o sin el método: flujos sucesivos
        return None, f'ComTransfer no se pudo usar ({type(exc).__name__}: {exc})'
    finally:
        for o in reversed(creados):
            try:
                o.Delete()
            except Exception:  # noqa: BLE001
                pass


def _por_flujos(app, elm_recibe, transferido: tuple, limites, transferida_kw: float,
                paso) -> tuple[float, bool]:
    """Capacidad del enlace subiendo ``scale0`` de las cargas transferidas (RF-125), en kW."""
    cargas = transferido[2]
    originales = [(c, getattr(c, 'scale0', 1.0) or 1.0) for c in cargas]

    def es_viable(k: float) -> bool:
        for c, s0 in originales:
            c.scale0 = s0 * k
        flujo = flujo_de_carga(app)
        m = _medir(elm_recibe, transferido) if flujo['converged'] else {'converge': False}
        return juzgar(paso, m, limites)[0]

    try:
        k, tope = maximo_factor(es_viable)
    finally:
        for c, s0 in originales:
            c.scale0 = s0
    return k * transferida_kw, tope


def capacidad_del_enlace(app, alims, cede, recibe, camino, punto, paso, enlace,
                         limites) -> dict[str, Any]:
    """RF-122 a RF-127 en la configuración de ``punto`` (el seccionador viable más lejano)."""
    red_recibe = Red(alims.elm[recibe])
    transferido = camino.transferido[punto]
    pasan = {clave_pf(c) for c in transferido[2]}
    resto = [c for c in alims.elm[cede].GetObjs('ElmLod') if clave_pf(c) not in pasan]
    obj, atributo, abierto = camino.accion[punto]
    antes = getattr(obj, atributo, None)
    setattr(obj, atributo, abierto)
    try:
        capacidad, motivo = _con_comtransfer(app, red_recibe, transferido, resto, enlace, limites)
        metodo, avisos = 'ComTransfer', []
        if capacidad is None:
            metodo = 'flujos sucesivos'
            avisos.append(f'Capacidad por flujos sucesivos: {motivo}.')
            capacidad, tope = _por_flujos(app, alims.elm[recibe], transferido, limites,
                                          paso.carga_kw, paso)
            if tope:
                avisos.append('Ningún límite del que recibe hasta el tope de la búsqueda: la '
                              'capacidad es al menos la dada.')
    finally:
        setattr(obj, atributo, antes)
    return {'punto': punto, 'metodo': metodo, 'capacidad_kw': capacidad,
            'transferida_kw': paso.carga_kw, 'margen_kw': margen(capacidad, paso.carga_kw),
            'avisos': avisos}


class Foto:
    """Interruptores de los dos alimentadores y ramas del camino, para restituirlos (RF-119)."""

    def __init__(self, objetos: list[tuple[Any, str]]):
        self.valores = {(clave_pf(o), a): (o, a, getattr(o, a, None)) for o, a in objetos}

    def restituir(self) -> list[str]:
        for o, a, v in self.valores.values():
            if getattr(o, a, None) != v:
                setattr(o, a, v)
        return self.distintos()

    def distintos(self) -> list[str]:
        return sorted(f'{o.loc_name}.{a}' for o, a, v in self.valores.values()
                      if getattr(o, a, None) != v)


def _sentido(app, alims, cede, recibe, enlace_nombre, troncal, enlace, entrada, limites,
             cancelado) -> dict[str, Any]:
    red = Red(alims.elm[cede])
    reconoce = distingue(red, entrada)
    camino = Camino(red, list(troncal.GetCompleteBbPath(0, 1) or []), enlace, entrada, reconoce)
    pasos = pasos_del_camino(camino.puntos)
    enlace.on_off = 1                                                   # RF-109
    medidas = []
    for paso in pasos:
        if cancelado():
            break
        obj, atributo, abierto = camino.accion[paso.punto]
        antes = getattr(obj, atributo, None)
        setattr(obj, atributo, abierto)
        try:
            flujo = flujo_de_carga(app)
            medidas.append(_medir(alims.elm[recibe], camino.transferido[paso.punto])
                           if flujo['converged'] else {'converge': False})
        finally:
            setattr(obj, atributo, antes)
    resumen = resumir_sentido(pasos[:len(medidas)], medidas, limites,
                              seccionadores_reconocidos=reconoce)
    resumen['capacidad'] = None
    maximo = resumen['maximo_seccionador']
    if maximo is not None and not cancelado():                          # RF-122
        paso = next(p for p in pasos if p.punto == maximo['punto'])
        resumen['capacidad'] = capacidad_del_enlace(app, alims, cede, recibe, camino,
                                                    maximo['punto'], paso, enlace, limites)
    return {'cede': cede, 'recibe': recibe, 'enlace': enlace_nombre, **resumen}


def _limites(plan: dict):
    try:
        return limites_de_perfil().con(**(plan.get('limites') or {}))
    except EstudiosError as exc:
        raise RuntimeError(str(exc)) from exc


def calcular(app, plan: dict, *, cancelado=lambda: False) -> tuple[dict, int]:
    """Las transferencias del plan. Devuelve (informe, código de salida)."""
    feeders = list(dict.fromkeys(plan.get('feeders') or []))
    casos_pedidos = list(plan.get('casos') or [NOMBRES['sin']])
    informe: dict[str, Any] = {'project': plan.get('project'), 'alimentadores': feeders,
                               'casos': casos_pedidos, 'resultados': [], 'avisos': [],
                               'cancelado': False, 'restitucion': {}}
    if len(feeders) != 2:
        return {**informe, 'error': 'elija dos alimentadores distintos'}, 2
    malos = [c for c in casos_pedidos if ROL_DE_CASO.get(c) not in ('sin', 'con')]
    if malos:
        return {**informe, 'error': f'la transferencia se calcula en «{NOMBRES["sin"]}» o '
                                    f'«{NOMBRES["con"]}», no en {", ".join(malos)}'}, 2
    limites = _limites(plan)
    informe['limites'] = {'tension_min_pu': limites.tension_min_pu,
                          'tension_max_pu': limites.tension_max_pu,
                          'cargabilidad_max_pct': limites.cargabilidad_max_pct,
                          'origen': limites.origen}
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r} en DIgSILENT"}, 2
    casos = tres_casos(app)
    if not casos:
        return {**informe, 'error': 'el proyecto no tiene los casos: prepare los casos primero'}, 2
    alims = Alimentadores(app, proyecto, feeders)
    if alims.sin_elm:
        return {**informe, 'error': 'no están en el proyecto: ' + ', '.join(alims.sin_elm)}, 2
    entrada = set(plan.get('seccionadores') or [])
    inicial = app.GetActiveStudyCase()
    a, b = feeders
    sin_enlace = True
    try:
        for nombre_caso in casos_pedidos:
            if cancelado():
                informe['cancelado'] = True
                break
            caso = casos[ROL_DE_CASO[nombre_caso]]
            caso.Activate()
            informe['restitucion'][nombre_caso] = _en_un_caso(
                app, alims, a, b, nombre_caso, entrada, limites, cancelado, informe)
            if any(r['caso'] == nombre_caso for r in informe['resultados']):
                sin_enlace = False
            if any(e['caso'] == nombre_caso for e in informe.get('sin_calcular', [])):
                sin_enlace = False       # hay enlace, pero entre tensiones distintas (016:RF-63)
            if informe['cancelado']:
                break
    finally:
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()
    if sin_enlace and not informe['cancelado']:                         # RF-107
        return {**informe, 'error': f'{a} y {b} no tienen ningún punto de enlace entre ellos'}, 2
    no_vuelto = [x for r in informe['restitucion'].values() for x in r['distintos']]
    nada = not informe['resultados'] and bool(informe.get('sin_calcular'))
    return informe, 2 if no_vuelto or informe['cancelado'] or nada else 0


def tensiones_del_enlace(redes, enlace) -> list[tuple[str, float]]:
    """(barra, ``uknom``) de las barras que une el punto de enlace (016:RF-63).

    El punto es un ``ElmCoup`` o el ``StaSwitch`` del cubículo de una línea: sus barras son
    las de sus extremos en los dos alimentadores.
    """
    elemento = enlace
    if enlace.GetClassName() == 'StaSwitch':
        elemento = getattr(enlace.GetParent(), 'obj_id', None) or enlace
    out = {}
    for red in redes:
        for barra, _cub in red.extremos.get(clave_pf(elemento), []):
            kv = getattr(barra, 'uknom', None)
            if isinstance(kv, (int, float)):
                out[barra.loc_name] = float(kv)
    return sorted(out.items())


def _tensiones_distintas(redes, enlace) -> str:
    """El motivo para no cerrar el enlace, o vacío (016:RF-62, RF-63).

    IN111 es de 10 kV y TA225 de 22,9 kV: cerrado sin migrar, el flujo no converge
    (usuario, 2026-10-14). Hasta migrar la parte que pasa, la transferencia por ese enlace
    no se calcula.
    """
    tensiones = tensiones_del_enlace(redes, enlace)
    distintas = {round(kv, 6) for _b, kv in tensiones}
    if len(distintas) < 2:
        return ''
    detalle = ' y '.join(f'{b} a {kv:g} kV' for b, kv in tensiones)
    return (f'el enlace {enlace.loc_name} une barras de distinta tensión ({detalle}): no se '
            'cierra ni se calcula la transferencia por él hasta migrar la parte que pasa')


def _en_un_caso(app, alims, a, b, nombre_caso, entrada, limites, cancelado, informe) -> dict:
    """Los dos sentidos en el caso activo, en una variación temporal que se borra."""
    grababa = app.GetRecordingStage()
    escenario = app.GetActiveScenario()
    if escenario is not None:
        escenario.Deactivate(0)        # RF-120: el on_off iría al escenario; no se guarda nada
    carpeta = app.GetProjectFolder('scheme')
    previas = {clave_pf(v) for v in carpeta.GetContents('*.IntScheme', 1)}
    redes = [Red(alims.elm[a]), Red(alims.elm[b])]
    creadas: list = []
    foto = None
    temporal = None
    try:
        troncales = {}
        for cede, recibe in ((a, b), (b, a)):                           # RF-105
            enlaces, nuevas = _troncales(app, cede, recibe)
            troncales[(cede, recibe)] = enlaces
            creadas += nuevas
        objetos = [(sw, 'on_off') for r in redes for sw in r.interruptores()]
        objetos += [(enlace, 'on_off') for enlaces in troncales.values()
                    for _t, enlace in enlaces.values()]
        objetos += [(e, 'outserv') for r in redes for i in r.extremos
                    if (e := r._elemento(i)) is not None and e.GetClassName() in RAMAS]
        objetos += [(c, 'scale0') for r in redes for c in r.elm.GetObjs('ElmLod')]
        foto = Foto(objetos)
        temporal, _etapa = crear_variacion(app, 'Transferencia_temporal', nombre_caso)
        for (cede, recibe), enlaces in troncales.items():
            for nombre_enlace in sorted(enlaces):                       # RF-106
                if cancelado():
                    informe['cancelado'] = True
                    break
                troncal, enlace = enlaces[nombre_enlace]
                motivo = _tensiones_distintas(redes, enlace)
                if motivo:                                              # 016:RF-63
                    aviso = f'En «{nombre_caso}», {motivo}.'
                    if aviso not in informe['avisos']:
                        informe['avisos'].append(aviso)
                    informe.setdefault('sin_calcular', []).append(
                        {'caso': nombre_caso, 'cede': cede, 'recibe': recibe,
                         'enlace': nombre_enlace, 'motivo': motivo})
                    continue
                try:
                    r = _sentido(app, alims, cede, recibe, nombre_enlace, troncal, enlace,
                                 entrada, limites, cancelado)
                finally:
                    foto.restituir()                                    # RF-119
                informe['resultados'].append({'caso': nombre_caso, **r})
    finally:
        distintos = foto.restituir() if foto is not None else []
        for bb in creadas:
            bb.Delete()
        for v in carpeta.GetContents('*.IntScheme', 1):
            if clave_pf(v) not in previas or (temporal is not None and clave_pf(v) == clave_pf(temporal)):
                v.Deactivate()
                v.Delete()
        # Se compara antes de volver a encender el escenario: la foto se tomó con él
        # apagado, y con él encendido cada scale0 calibrado salía «distinto» (311 avisos
        # falsos en «Con proyecto» de IN111 + TA225, 2026-10-15).
        distintos = foto.distintos() if foto is not None else distintos
        if escenario is not None and app.GetActiveScenario() is None:
            escenario.Activate()
        if grababa is not None and app.GetRecordingStage() is not grababa:
            grababa.Activate(1)
    for nombre in distintos:
        informe['avisos'].append(f'En «{nombre_caso}», {nombre} no volvió a su valor.')
    return {'restituido': not distintos, 'distintos': distintos}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Transferencia de carga entre dos alimentadores '
                                            '(spec 011)')
    p.add_argument('--plan', required=True, help='Plan JSON preparado por la web')
    p.add_argument('--output-json', required=True, help='Dónde dejar el informe')
    p.add_argument('--fichero', help='CSV con una fila por caso, sentido, enlace y paso')
    p.add_argument('--cancel-file', help='Si este fichero aparece, para entre pasos')
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    blocked = native_action_block_report(plan, 'transferencia')
    if blocked:
        Path(args.output_json).write_text(
            json.dumps(blocked, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(blocked['error'])
        return 2
    # 019:RF-1 a RF-6: turno del motor de la máquina, reintento con el motor ocupado y
    # primera línea al responder, comunes a todos los guiones.
    from igea_dgs.pf_arnes import PFNoDisponible, conectar

    try:
        app = conectar('transferencia_pf.py')
    except PFNoDisponible as exc:
        print(f'ERROR: {exc}')
        return 3

    def cancelado() -> bool:
        return bool(args.cancel_file) and Path(args.cancel_file).exists()

    try:
        informe, codigo = calcular(app, plan, cancelado=cancelado)
        if args.fichero and informe.get('resultados'):
            informe['fichero'] = str(escribir_fichero(informe['resultados'], Path(args.fichero)))
    except Exception as exc:  # noqa: BLE001 - el informe dice el error en vez de perderse
        traceback.print_exc()
        informe, codigo = error_inesperado(plan, False, exc), 1
    Path(args.output_json).write_text(
        json.dumps(informe, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
    print(f'Informe: {args.output_json}')
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
