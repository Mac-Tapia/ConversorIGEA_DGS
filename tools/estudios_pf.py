#!/usr/bin/env python
"""Ejecuta UN estudio de la spec 011 en UN caso («Sin proyecto» o «Con proyecto»).

La web lanza este guion una vez por estudio y caso, cada vez en su proceso, con un
límite de tiempo (RF-39, RF-40): un contingencias que se cuelga cuesta ese estudio y no
el resto, como en ``run_one_study.py``.

Lo que hace, en orden:

1. Activa el caso y, en él, ejecuta el flujo de carga **sin escalado por alimentador**
   (``ComLdf.iopt_fls`` = 0, RF-20): la demanda que entra por la cabecera tiene que
   seguir siendo la del ajuste. Si no converge, no ejecuta el estudio (RF-17).
2. En «Sin proyecto», compara cada cabecera con el objetivo de su ajuste y avisa si se
   aparta más que la tolerancia (RF-21).
3. Ejecuta el estudio con el escenario del caso activo (RF-49).
4. Mide cada alimentador: convergencia, tensiones extremas, elemento más cargado,
   cabecera, pérdidas y la lista de barras y elementos que juzga la web (RF-31, RF-33).

Por qué los optimizadores (punto de apertura, perfil de tensión, balance de fases) se
ejecutan dentro de una variación temporal: el manual (§41.6 a §41.8) da sus opciones de
guardado —``ComTieopt.iopt_result`` «Saving of solution», ``ComBalance.storage``
«Representation of solution»— pero no los valores de cada opción, y el punto de apertura
graba en el escenario si hay uno activo. En vez de apostar por un valor, todo lo que el
estudio cambie de red cae en esa variación, que se borra al terminar junto con cualquier
otra que el estudio cree; y el estado de los interruptores y las demandas se fotografía
antes y se restituye después (RF-22, RF-26). Lo que proponía el estudio se lee antes de
deshacerlo, y va al informe.

    python tools/estudios_pf.py --plan plan.json --output-json informe.json
    python tools/estudios_pf.py --guion --plan plan.json --output-json informe.json

Con ``--guion`` trabaja con los guiones DPL y Python del operador (RF-27 a RF-30): sin
``guion`` en el plan los lista, con sus parámetros de entrada (``IntName``, ``IntType``,
``IntExpr``, ``IntUnit``, ``IntDesc``) y objetos externos (``obj_name``), los atributos
de ``ComDpl`` y ``ComPython`` en ``datascheme.db`` de PF 2024; con él, lo ejecuta en el
caso del plan con los valores del operador (``SetInputParameterInt/Double/String``,
``SetExternalObject``) y devuelve su código y su ventana de salida.

Las contingencias N-1 (RF-36, RF-43 a RF-45) son una por tramo de la troncal de cada
alimentador marcado: se calcula antes la troncal (``ComBbone``) y, de cada una, se toma la
parte del camino que es del alimentador (``ElmBbone.GetCompleteBbPath(0, 1)``). Las
calcula el módulo de contingencias de DIgSILENT (usuario, 2026-10-11: todos los estudios
con los módulos de DIgSILENT): un ``ComSimoutage`` propio en el caso, para no tocar las
contingencias del operador, con un ``ComOutage`` por tramo (``SetObjs``). Cada
contingencia se lee con la traza del propio módulo (``StartTrace``, ``ContinueTrace``
hasta el último paso, medir, ``StopTrace``, referencia de Python §5.4.30), que deja la
red en su estado posterior a la falta con los resultados del módulo: así da las mismas
medidas que el resto de estudios. Al terminar se borra el ``ComSimoutage`` creado.

Códigos de salida: 0 hecho, 2 no se pudo (el informe dice por qué), 3 sin API.
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

from cargas_pf import (
    Alimentadores, _num, activar_proyecto, cabecera_de, crear_variacion, error_inesperado,
    flujo_de_carga, gps_de, leer_cabecera, potencia, trazado_de, variaciones_activas,
)
from casos_pf import NOMBRES, casos_del_proyecto, sin_a_con_proyecto

from igea_dgs.obras_pf import PREFIJO_VARIACION
from igea_dgs.native_action import native_action_block_report

#: Estudio → orden de DIgSILENT. Los dos flujos usan el ``ComLdf`` del caso.
ORDENES = {
    'flujo': 'ComLdf', 'flujo_desequilibrado': 'ComLdf', 'contingencias': 'ComSimoutage',
    'troncal': 'ComBbone', 'punto_apertura': 'ComTieopt', 'perfil_tension': 'ComVoltplan',
    'balance_fases': 'ComBalance',
}
#: Los que proponen cambios en la red: se ejecutan en una variación temporal (RF-26).
OPTIMIZADORES = ('punto_apertura', 'perfil_tension', 'balance_fases')

#: ``ComLdf.iopt_net``: 1 es el flujo trifásico desequilibrado.
FLUJO_DESEQUILIBRADO = 1
#: Clases cuyo estado de maniobra se fotografía y se restituye.
INTERRUPTORES = ('StaSwitch', 'ElmCoup')
#: Líneas de la ventana de salida que se guardan como resumen de un optimizador.
MAX_SALIDA = 60
#: Pasos de traza de una contingencia, como tope: una de un tramo tiene uno o dos.
MAX_PASOS_TRAZA = 50
#: Nombre del ``ComSimoutage`` que crea el N-1 en el caso, y que borra al terminar.
NOMBRE_N1 = 'N1_troncal_igea_dgs'
#: Guiones del operador (RF-27): DPL y Python, en el caso o en la carpeta ``script``.
CLASES_GUION = ('ComDpl', 'ComPython')
#: Casos donde se ejecutan los guiones del operador (RF-28): nunca en el «Caso base».
ROLES_GUION = ('sin', 'con')
#: Un guion del operador escribe lo que quiere: su salida entera, hasta este tope.
MAX_SALIDA_GUION = 2000


# =========================================================================== medidas
#: Saltos que se recorren desde la barra de un banco hasta un nodo de la red con nombre.
MAX_SALTOS_BANCO = 6


def _generica(nombre: str | None) -> bool:
    """Barra con el nombre que pone DIgSILENT al crearla a mano («Terminal», «Terminal(1)»)."""
    return not nombre or nombre.split('(')[0].strip().lower() in ('terminal', 'node', 'nodo', 'bus')


def _nodo_de_banco(barra) -> tuple[str | None, list[float] | None]:
    """El nodo de la red donde está un banco y su GPS (017, usuario 2026-10-16: «se debe
    mencionar los bancos existentes y en qué nodos están»).

    En CA101 los tres bancos cuelgan de barras «Terminal» y «Terminal(1)» creadas a mano:
    ese nombre no dice dónde están. Se sube a la subestación que la contiene o se recorre
    la red desde la barra hasta el primer nodo con nombre propio.
    """
    if barra is None:
        return None, None
    gps = gps_de(barra)
    if not _generica(barra.loc_name):
        return barra.loc_name, list(gps) if gps else None
    padre = barra.GetParent() if hasattr(barra, 'GetParent') else None
    if padre is not None and padre.GetClassName() in ('ElmSubstat', 'ElmTrfstat'):
        return padre.loc_name, list(gps) if gps else None
    vistos, frontera = {id(barra)}, [barra]
    for _ in range(MAX_SALTOS_BANCO):
        siguiente = []
        for b in frontera:
            try:
                elementos = list(b.GetConnectedElements(1, 1, 0) or [])
            except Exception:  # noqa: BLE001 - sin el método (versiones viejas): sin nodo
                elementos = []
            for el in elementos:
                if el.GetClassName() == 'ElmTerm':
                    terminales = [el]
                else:
                    try:
                        terminales = [t for t in (el.GetConnectedElements(1, 1, 0) or [])
                                      if t.GetClassName() == 'ElmTerm']
                    except Exception:  # noqa: BLE001
                        terminales = []
                for t in terminales:
                    if id(t) in vistos:
                        continue
                    vistos.add(id(t))
                    if not _generica(t.loc_name):
                        g = gps or gps_de(t)
                        return t.loc_name, list(g) if g else None
                    siguiente.append(t)
        frontera = siguiente
    return None, list(gps) if gps else None


def medida(elm, app=None) -> dict:
    """Lo que la web necesita de un alimentador tras un flujo (RF-31, RF-33).

    Con ``app``, los objetos son los de toda la red calculable del proyecto en vez de los
    del ``ElmFeeder``. El medidor de CA101 alimenta dos troncales desde la misma barra
    (006:RF-11) y el ``ElmFeeder`` solo abarca una: el 2026-10-15 la medida dejó fuera
    1900 kW de cargas y daba un 43 % de pérdidas. ``medidas`` lo pasa cuando el proyecto
    es de un solo alimentador.
    """
    def objetos(clase):
        return list(app.GetCalcRelevantObjects(f'*.{clase}')) if app is not None else list(elm.GetObjs(clase))

    barras = sorted((b.loc_name, _num(b, 'm:u')) for b in objetos('ElmTerm'))
    barras = [(n, u) for n, u in barras if u is not None]
    elementos = []
    for clase in ('ElmLne', 'ElmTr2'):
        for o in objetos(clase):
            carga = _num(o, 'c:loading')
            if carga is not None:
                elementos.append((o.loc_name, clase, carga))
    elementos.sort()
    out = {'converge': True, 'barras': barras, 'elementos': elementos,
           'vm_min': None, 'vm_min_barra': None, 'vm_max': None, 'vm_max_barra': None,
           'mas_cargado': None, 'cargabilidad_max': None,
           'cabecera_kw': None, 'cabecera_kvar': None, 'perdidas_kw': None, 'perdidas_kvar': None,
           'vm_min_fases': None, 'bancos': []}
    # Los bancos de condensadores que existen en la red entran en la calibración y el
    # informe los nombra con su nodo y sus kvar, tal como están en DIgSILENT (el usuario,
    # 2026-10-15: CA101 tiene tres en la troncal que va a Casa Blanca).
    for sh in objetos('ElmShnt'):
        cub = getattr(sh, 'bus1', None)
        barra = cub.GetParent() if cub is not None else None
        # «qcapn» es la potencia de un escalón; la del banco es «qtotn» o escalón × conectados.
        q = _num(sh, 'qtotn')
        if q is None and _num(sh, 'qcapn') is not None:
            q = _num(sh, 'qcapn') * (_num(sh, 'ncapa') or 1.0)
        nodo, gps = _nodo_de_banco(barra)
        out['bancos'].append({'nombre': sh.loc_name, 'barra': getattr(barra, 'loc_name', None),
                              'nodo': nodo, 'gps': gps,
                              'kvar': q * 1000.0 if q is not None else None,
                              'escalones': _num(sh, 'ncapx'), 'en_servicio': not getattr(sh, 'outserv', 0),
                              'q_flujo_kvar': (-_num(sh, 'm:Qsum:bus1') * 1000.0
                                               if _num(sh, 'm:Qsum:bus1') is not None else None)})
    out['bancos'].sort(key=lambda x: (str(x['barra']), x['nombre']))
    if barras:
        lo = min(barras, key=lambda b: b[1])
        hi = max(barras, key=lambda b: b[1])
        out.update(vm_min=lo[1], vm_min_barra=lo[0], vm_max=hi[1], vm_max_barra=hi[0])
        # El informe da la mínima de cada fase en el flujo desequilibrado (017:RF-17); en el
        # equilibrado DIgSILENT no tiene tensiones por fase y queda en None.
        fases = {}
        for fase in 'ABC':
            valores = [(u, b.loc_name) for b in objetos('ElmTerm')
                       if (u := _num(b, f'm:u:{fase}')) is not None]
            if valores:
                fases[fase] = min(valores)
        out['vm_min_fases'] = fases if len(fases) == 3 else None
    if elementos:
        peor = max(elementos, key=lambda e: e[2])
        out.update(mas_cargado=peor[0], cargabilidad_max=peor[2])
    if getattr(elm, 'obj_id', None) is not None:
        cab = leer_cabecera(elm)
        if cab.converge:
            out.update(cabecera_kw=cab.kw, cabecera_kvar=cab.kvar)
            # Pérdidas = cabecera − lo que consumen de verdad cargas y bancos en el flujo
            # («m:Psum:bus1», como el ajuste). Con la P escrita en las cargas, CA101 dio el
            # 2026-10-15 un 39 % de pérdidas: a 0,65 p.u. las cargas consumen mucho menos de
            # lo escrito. Si a alguna le falta el resultado no se estima: queda en None.
            consumos = []
            for o in [*objetos('ElmLod'), *objetos('ElmShnt')]:
                if getattr(o, 'outserv', 0):
                    continue
                p, q = _num(o, 'm:Psum:bus1'), _num(o, 'm:Qsum:bus1')
                if p is None or q is None:
                    consumos = None
                    break
                consumos.append((p * 1000.0, q * 1000.0))
            if consumos is not None:
                out['perdidas_kw'] = cab.kw - sum(p for p, _ in consumos)
                if cab.kvar is not None:
                    out['perdidas_kvar'] = cab.kvar - sum(q for _, q in consumos)
    return out


def geografia(elm, app=None) -> dict:
    """Barras y tramos con su GPS y su resultado del flujo, para las imágenes del informe.

    DIgSILENT sin ventana no dibuja (``WriteWMF`` vacío), así que el informe de estudio
    dibuja el alimentador con esto (017:RF-11b): ``barras`` ``[nombre, lat, lon, u, kv]``
    y ``tramos`` ``[nombre, [[lat, lon], ...], carga_%]``. Con ``app``, toda la red
    calculable, como :func:`medida`.
    """
    def objetos(clase):
        return list(app.GetCalcRelevantObjects(f'*.{clase}')) if app is not None else list(elm.GetObjs(clase))

    barras = []
    for b in objetos('ElmTerm'):
        g = gps_de(b)
        if g is not None:
            u = _num(b, 'm:u')
            barras.append([b.loc_name, round(g[0], 7), round(g[1], 7),
                           None if u is None else round(u, 4), float(getattr(b, 'uknom', 0) or 0)])
    tramos = []
    for ln in objetos('ElmLne'):
        puntos = trazado_de(ln)
        if not puntos:
            extremos = [gps_de(getattr(getattr(ln, c, None), 'cterm', None))
                        for c in ('bus1', 'bus2')]
            puntos = tuple(p for p in extremos if p is not None)
        if len(puntos) >= 2:
            carga = _num(ln, 'c:loading')
            # 017:RF-131: barras, tipo y longitud, para decir desde dónde hasta dónde va el
            # cambio de conductor (CA101, 2026-10-16: 21 tramos sin más que su nombre).
            barras_ln = [getattr(getattr(getattr(ln, c, None), 'cterm', None), 'loc_name', None)
                         for c in ('bus1', 'bus2')]
            tipo = getattr(getattr(ln, 'typ_id', None), 'loc_name', None)
            km = _num(ln, 'dline')
            tramos.append([ln.loc_name, [[round(a, 7), round(o, 7)] for a, o in puntos],
                           None if carga is None else round(carga, 2), barras_ln[0], barras_ln[1],
                           tipo, None if km is None else round(km, 4)])
    # 017:RF-132: los acoples cerrados unen barras sin ser líneas. Sin ellos, el cambio de
    # conductor de CA101 (2026-10-16) salía en 10 trechos, cuatro de 0,00 a 0,02 km,
    # cortados en cada seccionador de la troncal.
    acoples = []
    for c in objetos('ElmCoup'):
        if getattr(c, 'on_off', 1) and not getattr(c, 'outserv', 0):
            extremos = [getattr(getattr(getattr(c, k, None), 'cterm', None), 'loc_name', None)
                        for k in ('bus1', 'bus2')]
            if all(extremos):
                acoples.append([c.loc_name, extremos[0], extremos[1]])
    cabecera = cabecera_de(elm) if elm is not None else None
    return {'barras': sorted(barras), 'tramos': sorted(tramos, key=lambda t: t[0]),
            'acoples': sorted(acoples), 'cabecera': getattr(cabecera, 'loc_name', None)}


def medidas(alims: Alimentadores, feeders: list[str], converge: bool) -> dict:
    if not converge:
        return {f: {'converge': False} for f in feeders}
    # Proyecto de un solo alimentador: toda su red, con todas las troncales de la cabecera.
    app = alims.app if len(alims.elm) == 1 else None
    return {f: medida(alims.elm[f], app) if alims.elm.get(f) is not None
            else {'converge': False, 'motivo': 'sin ElmFeeder'} for f in feeders}


def desvios_de_cabecera(med: dict, objetivos: dict, tolerancia: float) -> list[str]:
    """Avisos de RF-21: cabeceras de «Sin proyecto» que se apartan del objetivo del ajuste."""
    avisos = []
    for f, obj in sorted(objetivos.items()):
        m = med.get(f) or {}
        kw = m.get('cabecera_kw')
        if kw is None or not obj.get('kw'):
            continue
        rel = (kw - obj['kw']) / obj['kw']
        if abs(rel) > tolerancia:
            avisos.append(f'{f}: la cabecera da {kw:,.1f} kW y el ajuste se hizo a '
                          f"{obj['kw']:,.1f} kW ({rel:+.1%}): algo cambió la demanda calibrada.")
    return avisos


# =========================================================================== protección
class Foto:
    """Interruptores y demandas de los alimentadores antes del estudio (RF-22, RF-26)."""

    def __init__(self, alims: Alimentadores, feeders: list[str]):
        self.interruptores = {}
        self.cargas = {}
        for f in feeders:
            elm = alims.elm.get(f)
            if elm is None:
                continue
            for clase in INTERRUPTORES:
                for o in elm.GetObjs(clase):
                    self.interruptores[id(o)] = (o, getattr(o, 'on_off', None))
            for o in elm.GetObjs('ElmLod'):
                self.cargas[id(o)] = (o, potencia(o))

    def maniobras(self) -> list[dict]:
        """Interruptores que el estudio cambió: es la propuesta del punto de apertura."""
        out = []
        for o, antes in self.interruptores.values():
            ahora = getattr(o, 'on_off', None)
            if ahora != antes:
                out.append({'elemento': o.loc_name, 'clase': o.GetClassName(),
                            'accion': 'cerrar' if ahora else 'abrir'})
        return sorted(out, key=lambda x: x['elemento'])

    def restituir(self) -> list[str]:
        """Devuelve cada interruptor a su estado y dice qué demanda no volvió."""
        for o, antes in self.interruptores.values():
            if antes is not None and getattr(o, 'on_off', None) != antes:
                o.on_off = antes
        movidas = []
        for o, (kw, kvar) in self.cargas.values():
            ahora = potencia(o)
            if abs(ahora[0] - kw) > 1e-6 or abs(ahora[1] - kvar) > 1e-6:
                movidas.append(o.loc_name)
        return sorted(movidas)


def _salida(app, tope: int = MAX_SALIDA) -> list[str]:
    try:
        return [str(x) for x in (app.GetOutputWindow().GetContent() or [])][-tope:]
    except Exception:  # noqa: BLE001 - versiones sin ventana accesible: sin resumen
        return []


def _clave_nativa(obj):
    """Identidad persistente aunque PowerFactory entregue un wrapper Python nuevo."""
    try:
        return 'pf', str(obj.GetFullName())
    except Exception:  # noqa: BLE001
        return 'py', id(obj)


def _limpiar_salida(app) -> None:
    try:
        app.GetOutputWindow().Clear()
    except Exception:  # noqa: BLE001
        pass


def _tomas(alims: Alimentadores, feeders: list[str]) -> list[dict]:
    """Tomas recomendadas por el perfil de tensión (``c:nntap``, manual §41.8.5)."""
    out = []
    for f in feeders:
        elm = alims.elm.get(f)
        for clase in ('ElmLod', 'ElmTr2'):
            for o in (elm.GetObjs(clase) if elm is not None else []):
                t = _num(o, 'c:nntap')
                if t is not None:
                    out.append({'alimentador': f, 'elemento': o.loc_name, 'toma': int(round(t))})
    return sorted(out, key=lambda x: (x['alimentador'], x['elemento']))


# =========================================================================== estudio
def _optimizador(app, plan, alims, feeders, orden, informe) -> None:
    """RF-26: ejecuta en una variación temporal, lee la propuesta y lo deshace todo."""
    if plan['estudio'] == 'balance_fases' and len(feeders) == 1:
        # PowerFactory no toma el alimentador del caso ni del ElmFeeder activo: ComBalance
        # exige explícitamente ``startElm`` y termina con código 1 si queda vacío.
        orden.startElm = alims.elm.get(feeders[0])
    carpeta = app.GetProjectFolder('scheme')
    previas = {_clave_nativa(v) for v in carpeta.GetContents('*.IntScheme', 1)}
    foto = Foto(alims, feeders)
    temporal, _etapa = crear_variacion(app, f"Estudio_{plan['estudio']}", plan.get('stamp') or '')
    try:
        _limpiar_salida(app)
        rc = orden.Execute()
        informe['codigo_orden'] = rc
        propuesta = {'resumen': _salida(app), 'maniobras': foto.maniobras()}
        if plan['estudio'] == 'perfil_tension':
            propuesta['tomas'] = _tomas(alims, feeders)
        informe['propuesta'] = propuesta
    finally:
        movidas = foto.restituir()
        clave_temporal = _clave_nativa(temporal)
        for v in carpeta.GetContents('*.IntScheme', 1):
            if _clave_nativa(v) not in previas or _clave_nativa(v) == clave_temporal:
                v.Deactivate()
                v.Delete()
        if movidas:
            informe['avisos'].append('El estudio cambió la demanda de estas cargas y no se pudo '
                                     'deshacer: ' + ', '.join(movidas))


def _troncal(app, feeders: list[str]) -> list[dict]:
    """Troncales que dejó ``ComBbone``: alimentadores que une y su punto de enlace."""
    out = []
    for b in app.GetCalcRelevantObjects('*.ElmBbone'):
        try:
            enlace = b.GetTieOpenPoint()
        except Exception:  # noqa: BLE001
            enlace = None
        inicio = getattr(getattr(b, 'pBbStart', None), 'loc_name', None)
        fin = getattr(getattr(b, 'pBbEnd', None), 'loc_name', None)
        if inicio in feeders or fin in feeders:
            out.append({'troncal': b.loc_name, 'desde': inicio, 'hasta': fin,
                        'enlace': getattr(enlace, 'loc_name', None)})
    return sorted(out, key=lambda x: x['troncal'])


def tramos_troncales(app, feeders: list[str]) -> tuple[dict[str, list], list[str]]:
    """Por alimentador marcado, las líneas de su parte de la troncal (RF-43).

    Un alimentador puede tener varias troncales (una por enlace): sus tramos se juntan sin
    repetir. Los que no tienen ninguna van aparte (RF-45).
    """
    por_feeder: dict[str, dict[int, object]] = {f: {} for f in feeders}
    for b in app.GetCalcRelevantObjects('*.ElmBbone'):
        inicio = getattr(getattr(b, 'pBbStart', None), 'loc_name', None)
        if inicio not in por_feeder:
            continue
        try:
            camino = b.GetCompleteBbPath(0, 1) or []
        except Exception:  # noqa: BLE001 - troncal inválida: no aporta tramos
            camino = []
        for o in camino:
            if o.GetClassName() == 'ElmLne':
                por_feeder[inicio][id(o)] = o
    tramos = {f: sorted(d.values(), key=lambda o: o.loc_name) for f, d in por_feeder.items() if d}
    return tramos, [f for f in feeders if f not in tramos]


def _contingencias(app, plan, alims, feeders, informe) -> str | None:
    """RF-36, RF-43 a RF-45: troncal primero y N-1 de sus tramos con ``ComSimoutage``.

    Devuelve el motivo si no se puede calcular.
    """
    bbone = app.GetFromStudyCase('ComBbone')
    if bbone is None:
        return 'el caso no admite la orden ComBbone: sin troncal no hay N-1'
    informe['codigo_troncal'] = bbone.Execute()                     # RF-44
    informe['troncales'] = _troncal(app, feeders)
    tramos, sin_troncal = tramos_troncales(app, feeders)
    for f in sin_troncal:                                           # RF-45
        informe['avisos'].append(f'{f}: sin troncal calculada, queda fuera del N-1.')
    informe['sin_troncal'] = sin_troncal
    informe['contingencias'] = []
    if not tramos:
        return None
    caso = app.GetActiveStudyCase()
    orden = caso.CreateObject('ComSimoutage', NOMBRE_N1)
    if orden is None:
        return 'no se pudo crear el análisis de contingencias en el caso'
    try:
        faltas = []
        for f, lineas in sorted(tramos.items()):
            for ln in lineas:
                falta = orden.CreateObject('ComOutage', ln.loc_name)
                falta.SetObjs([ln])
                faltas.append((f, ln, falta))
        informe['codigo_orden'] = orden.Execute()
        for f, ln, falta in faltas:
            informe['contingencias'].append(_traza(app, alims, feeders, f, ln, falta))
    finally:
        orden.Delete()
    return None


def _traza(app, alims, feeders, feeder: str, linea, falta) -> dict:
    """Estado posterior a la falta de una contingencia, leído con la traza del módulo."""
    fila = {'contingencia': linea.loc_name, 'alimentador': feeder}
    if falta.StartTrace() != 0:
        return {**fila, 'converge': False, 'medidas': medidas(alims, feeders, False),
                'motivo': 'DIgSILENT no pudo trazar la contingencia'}
    try:
        for _ in range(MAX_PASOS_TRAZA):
            if falta.ContinueTrace() != 0:
                break
        converge = bool(app.IsLdfValid())
        return {**fila, 'converge': converge, 'medidas': medidas(alims, feeders, converge)}
    finally:
        falta.StopTrace(0)


def _alternativas(app, alims, feeders, alternativas: list[dict], todo, avisos: list) -> list[dict]:
    """017:RF-130: cada alternativa medida con solo las variaciones de sus obras activas.

    En CA101 (2026-10-16) «Con proyecto» tenía los bancos, la consigna y el cambio de
    sección a la vez y el informe no podía decir qué lograban los bancos solos. Se mide en
    la misma ejecución, con el mismo caso y escenario; solo se apartan variaciones de obras
    (prefijo de la spec 011), nunca las del operador ni las de las cargas. Al terminar se
    reactivan las que estaban, en su orden.
    """
    carpeta = app.GetProjectFolder('scheme')
    obras = {v.loc_name: v for v in carpeta.GetContents('*.IntScheme', 1)
             if v.loc_name.startswith(PREFIJO_VARIACION)}
    activas = set(variaciones_activas(app))
    estaban = [v for n, v in sorted(obras.items()) if n in activas]
    nombres = {v.loc_name for v in estaban}
    out = []
    try:
        for alt in alternativas:
            queridas = set(alt.get('variaciones') or [])
            # Solo las que el caso tenía activas: una obra apartada a mano no entra.
            faltan = sorted(queridas - nombres)
            for v in estaban:
                if v.loc_name not in queridas and v.loc_name in set(variaciones_activas(app)):
                    v.Deactivate()
                elif v.loc_name in queridas and v.loc_name not in set(variaciones_activas(app)):
                    v.Activate()
            flujo = flujo_de_carga(app)
            fila = {'clave': alt.get('clave'), 'variaciones': sorted(queridas & nombres),
                    'faltan': faltan, 'medidas': medidas(alims, feeders, flujo['converged'])}
            if flujo['converged']:
                fila['geo'] = {f: geografia(alims.elm[f], todo) for f in feeders
                               if alims.elm.get(f) is not None}
            if faltan:
                avisos.append(f"Alternativa {alt.get('clave')}: no están activas en el caso las "
                              'variaciones ' + ', '.join(faltan))
            out.append(fila)
    finally:
        actuales = set(variaciones_activas(app))
        for v in estaban:
            if v.loc_name not in actuales:
                v.Activate()
        # Deja el flujo como lo midió el estudio, con todas las obras.
        flujo_de_carga(app)
    return out


def ejecutar(app, plan: dict) -> tuple[dict, int]:
    """Un estudio en un caso. Devuelve (informe, código de salida)."""
    estudio, rol = plan['estudio'], plan['caso']
    informe = {'project': plan.get('project'), 'estudio': estudio, 'caso': NOMBRES.get(rol),
               'avisos': [], 'medidas': {}}
    if estudio not in ORDENES:
        return {**informe, 'error': f'estudio desconocido: {estudio!r}'}, 2
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r} en DIgSILENT"}, 2
    casos = casos_del_proyecto(app)
    caso = casos.get(rol)
    if caso is None:
        return {**informe, 'error': f'el proyecto no tiene el caso «{NOMBRES.get(rol, rol)}»: '
                                    'prepare los casos primero'}, 2
    feeders = list(plan['feeders'])
    inicial = app.GetActiveStudyCase()
    ldf = None                      # el del caso: se toma con el caso ya activo
    guardados: dict = {}
    try:
        if rol == 'con':                                         # 014:RF-31 a RF-34
            informe['sin_a_con'] = sin_a_con_proyecto(app, casos)
            informe['avisos'] += informe['sin_a_con']['avisos']
        caso.Activate()
        ldf = app.GetFromStudyCase('ComLdf')
        # Los dos existen siempre en DIgSILENT, con 0 por defecto (sin escalado, equilibrado).
        guardados = {'iopt_fls': getattr(ldf, 'iopt_fls', 0), 'iopt_net': getattr(ldf, 'iopt_net', 0)}
        ldf.iopt_fls = 0                                   # RF-20
        esc = app.GetActiveScenario()
        informe['escenario'] = esc.loc_name if esc is not None else None      # RF-49
        informe['variaciones_activas'] = variaciones_activas(app)             # RF-38
        informe['obras_activas'] = [v for v in informe['variaciones_activas']   # RF-68
                                    if v.startswith(PREFIJO_VARIACION)]
        alims = Alimentadores(app, proyecto, feeders)

        flujo = flujo_de_carga(app)                        # RF-17
        if not flujo['converged']:
            informe['medidas'] = medidas(alims, feeders, False)
            return {**informe, 'error': 'el flujo de carga del caso no converge: no se ejecuta '
                                        'el estudio'}, 2
        base = medidas(alims, feeders, True)
        if rol == 'sin':
            informe['avisos'] += desvios_de_cabecera(
                base, plan.get('objetivos') or {}, float(plan.get('tolerancia', 0.01)))

        if estudio == 'flujo':
            informe['medidas'] = base
        elif estudio == 'flujo_desequilibrado':
            ldf.iopt_net = FLUJO_DESEQUILIBRADO
            flujo = flujo_de_carga(app)
            informe['medidas'] = medidas(alims, feeders, flujo['converged'])
            if not flujo['converged']:
                informe['avisos'].append('El flujo desequilibrado no converge.')
        if estudio in ('flujo', 'flujo_desequilibrado') and flujo['converged']:
            # 017:RF-11b: la geografía con los resultados, para las imágenes del informe.
            todo = alims.app if len(alims.elm) == 1 else None
            informe['geo'] = {f: geografia(alims.elm[f], todo) for f in feeders
                              if alims.elm.get(f) is not None}
            if rol == 'con' and plan.get('alternativas'):
                informe['alternativas'] = _alternativas(app, alims, feeders, plan['alternativas'],
                                                        todo, informe['avisos'])
        elif estudio == 'contingencias':
            motivo = _contingencias(app, plan, alims, feeders, informe)
            informe['medidas'] = base
            if motivo:
                return {**informe, 'error': motivo}, 2
        else:
            orden = app.GetFromStudyCase(ORDENES[estudio])
            if orden is None:
                return {**informe, 'error': f'el caso no admite la orden {ORDENES[estudio]}'}, 2
            if estudio in OPTIMIZADORES:
                _optimizador(app, plan, alims, feeders, orden, informe)
            else:
                informe['codigo_orden'] = orden.Execute()
                informe['troncales'] = _troncal(app, feeders)
            # Las medidas son las de la red tal como queda: sin la propuesta aplicada.
            flujo = flujo_de_carga(app)
            informe['medidas'] = medidas(alims, feeders, flujo['converged'])
    finally:
        if ldf is not None:
            for k, v in guardados.items():
                setattr(ldf, k, v)
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()
    return informe, 0


# =========================================================================== guiones
def _vector(obj, atributo) -> list:
    v = getattr(obj, atributo, None)
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


def _guiones_en(carpeta) -> list:
    if carpeta is None:
        return []
    return [g for clase in CLASES_GUION for g in carpeta.GetContents(f'*.{clase}', 1)]


def _ficha(g, origen: str) -> dict:
    """Lo que la web necesita para pedir los valores de un guion (RF-27, RF-28)."""
    nombres = [str(x) for x in _vector(g, 'IntName')]
    columnas = [_vector(g, a) for a in ('IntType', 'IntExpr', 'IntUnit', 'IntDesc')]
    parametros = [{'nombre': n, **{k: str(c[i]) if i < len(c) else ''
                                   for k, c in zip(('tipo', 'valor', 'unidad', 'descripcion'),
                                                   columnas)}}
                  for i, n in enumerate(nombres)]
    return {'nombre': g.loc_name, 'clase': g.GetClassName(), 'origen': origen, 'casos': [],
            'parametros': parametros, 'objetos': [str(x) for x in _vector(g, 'obj_name')]}


def listar_guiones(app, casos: dict) -> list[dict]:
    """RF-27: los guiones de «Sin proyecto» y «Con proyecto» y los de la carpeta de guiones.

    Un guion de un caso solo se puede ejecutar en los casos que lo tienen: se dice cuáles.
    Los de la carpeta del proyecto valen para los dos.
    """
    fichas: dict[tuple, dict] = {}
    for rol in ROLES_GUION:
        for g in _guiones_en(casos[rol]):
            ficha = fichas.setdefault(('caso', g.loc_name), _ficha(g, 'caso'))
            ficha['casos'].append(rol)
    for g in _guiones_en(app.GetProjectFolder('script')):
        fichas.setdefault(('proyecto', g.loc_name), {**_ficha(g, 'proyecto'),
                                                     'casos': list(ROLES_GUION)})
    return sorted(fichas.values(), key=lambda f: (f['origen'], f['nombre']))


def _objeto_de_red(app, valor: str):
    """El objeto que el operador escribió como ``nombre.Clase``, si hay uno y solo uno."""
    nombre, _, clase = str(valor).rpartition('.')
    if not nombre or not clase:
        return None
    hallados = [o for o in app.GetCalcRelevantObjects(f'*.{clase}') if o.loc_name == nombre]
    return hallados[0] if len(hallados) == 1 else None


def poner_parametros(app, g, valores: dict) -> str | None:
    """RF-28: cada valor del operador, convertido al tipo del parámetro. Devuelve el motivo
    del primero que no vale, sin ejecutar nada; los de antes ya quedan puestos, pero el
    guion no se ejecuta con ellos."""
    ficha = _ficha(g, '')
    tipos = {p['nombre']: p['tipo'] for p in ficha['parametros']}
    for nombre, valor in sorted(valores.items()):
        if nombre in ficha['objetos']:
            obj = _objeto_de_red(app, valor)
            if obj is None:
                return f'{nombre}: no hay un único objeto {valor!r} en la red del caso'
            rc = g.SetExternalObject(nombre, obj)
        elif nombre in tipos:
            tipo = tipos[nombre].lower()
            try:
                if tipo == 'int':
                    rc = g.SetInputParameterInt(nombre, int(str(valor).strip()))
                elif tipo == 'double':
                    rc = g.SetInputParameterDouble(nombre, float(str(valor).replace(',', '.')))
                else:
                    rc = g.SetInputParameterString(nombre, str(valor))
            except ValueError:
                return f'{nombre}: {valor!r} no es un valor de tipo {tipo}'
        else:
            return f'{nombre}: el guion {g.loc_name} no tiene ese parámetro'
        if rc:
            return f'{nombre}: DIgSILENT no aceptó el valor {valor!r}'
    return None


def ejecutar_guion(app, plan: dict) -> tuple[dict, int]:
    """Guiones del operador (RF-27 a RF-30). Sin ``plan['guion']``, los lista; con él,
    ejecuta ese guion en ``plan['caso']`` con ``plan['parametros']``.

    No se protege la red como en los estudios: el guion es del operador y lo que haga es
    cosa suya. Sí se vuelve al caso del principio, para que el estudio siguiente del
    mismo trabajo empiece donde los demás (RF-30).
    """
    pedido = plan.get('guion')
    informe = {'project': plan.get('project'), 'avisos': []}
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r} en DIgSILENT"}, 2
    casos = casos_del_proyecto(app)
    if any(rol not in casos for rol in ROLES_GUION):
        return {**informe, 'error': 'el proyecto no tiene los casos «Sin proyecto» y «Con '
                                    'proyecto»: prepare los casos primero'}, 2
    if not pedido:
        return {**informe, 'guiones': listar_guiones(app, casos)}, 0

    rol, nombre, origen = plan['caso'], pedido['nombre'], pedido.get('origen', 'caso')
    informe.update(caso=NOMBRES.get(rol), guion=nombre, origen=origen)
    if rol not in ROLES_GUION:
        return {**informe, 'error': f'caso desconocido: {rol!r}'}, 2
    carpeta = casos[rol] if origen == 'caso' else app.GetProjectFolder('script')
    hallados = [g for g in _guiones_en(carpeta) if g.loc_name == nombre]
    if len(hallados) != 1:
        donde = f'el caso «{NOMBRES[rol]}»' if origen == 'caso' else 'la carpeta de guiones'
        cuantos = 'no está' if not hallados else f'hay {len(hallados)} con ese nombre'
        return {**informe, 'error': f'el guion {nombre}: {cuantos} en {donde}'}, 2
    g = hallados[0]
    inicial = app.GetActiveStudyCase()
    try:
        if rol == 'con':                                         # 014:RF-31 a RF-34
            informe['sin_a_con'] = sin_a_con_proyecto(app, casos)
            informe['avisos'] += informe['sin_a_con']['avisos']
        casos[rol].Activate()
        motivo = poner_parametros(app, g, plan.get('parametros') or {})
        if motivo:
            return {**informe, 'error': f'no se ejecuta el guion {nombre}: {motivo}'}, 2
        _limpiar_salida(app)
        codigo = g.Execute()
        informe['codigo_guion'] = codigo                              # RF-29
        informe['salida'] = _salida(app, MAX_SALIDA_GUION)
    finally:
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()
    if codigo:                                                        # RF-30
        return {**informe, 'error': f'el guion {nombre} terminó con el código {codigo} en '
                                    f'«{NOMBRES[rol]}»'}, 2
    return informe, 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Un estudio de la spec 011 en un caso de DIgSILENT')
    p.add_argument('--plan', required=True, help='Plan JSON preparado por la web')
    p.add_argument('--output-json', required=True, help='Dónde dejar el informe')
    p.add_argument('--guion', action='store_true',
                   help='Guiones del operador: lista los del proyecto o ejecuta el del plan')
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    blocked = native_action_block_report(plan, ('estudios', 'guion'))
    if blocked:
        Path(args.output_json).write_text(
            json.dumps(blocked, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(blocked['error'])
        return 2
    # 019:RF-1 a RF-6: turno del motor de la máquina, reintento con el motor ocupado y
    # primera línea al responder, comunes a todos los guiones.
    from igea_dgs.pf_arnes import PFNoDisponible, conectar

    try:
        app = conectar('estudios_pf.py')
    except PFNoDisponible as exc:
        print(f'ERROR: {exc}')
        return 3
    try:
        informe, codigo = (ejecutar_guion if args.guion else ejecutar)(app, plan)
    except Exception as exc:  # noqa: BLE001 - el informe dice el error en vez de perderse
        traceback.print_exc()
        informe, codigo = error_inesperado(plan, False, exc), 1
    Path(args.output_json).write_text(
        json.dumps(informe, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
    print(f'Informe: {args.output_json}')
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
