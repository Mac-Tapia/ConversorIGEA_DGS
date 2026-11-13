#!/usr/bin/env python
"""Deja en DIgSILENT los tres casos de estudio de la spec 011.

Por qué tres casos. Los estudios solo dicen algo de la red real sobre la red calibrada
(specs 006 a 008), y lo que se evalúa de las cargas nuevas es la diferencia entre la red
con ellas y sin ellas. El usuario lo ordena así (2026-10-11):

- **Caso base**: el caso en que se calibró, renombrado, sin las variaciones del ajuste,
  de las demandas ni de las cargas nuevas: la red tal como vino (RF-2, RF-3).
- **Sin proyecto**: copia del anterior con la base calibrada activa: el último ajuste de
  cada alimentador y las demandas en bloque (RF-4, RF-7, RF-50).
- **Con proyecto**: copia de «Sin proyecto» con, además, todas las cargas nuevas de los
  alimentadores marcados (RF-5, RF-8).

En DIgSILENT las variaciones activas y el escenario son de cada caso: por eso basta con
activar el caso y activar o desactivar en él. Cada caso tiene su propio escenario de
operación (RF-46 a RF-48), para que un cambio de operación en uno no llegue a otro.

Los casos se reconocen por su nombre **y** por una marca en su descripción: un caso del
operador que se llame igual no se toca (RF-10). Si se vuelve a ejecutar, se reutilizan y
solo cambian sus variaciones activas (RF-6): así las cargas nuevas añadidas después
entran en «Con proyecto».

    python tools/casos_pf.py --plan plan.json --output-json informe.json

El plan trae el proyecto, los alimentadores marcados, la base del último ajuste (la de
``services.base_del_ajuste``) y, si la hay, la variación de las demandas en bloque.

Códigos de salida: 0 hecho, 2 no se pudo preparar (el informe dice por qué), 3 sin API.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import traceback
from pathlib import Path

from cargas_pf import activar_proyecto, error_inesperado, etapas_al_dia, nombre_pf
from convertersmartgrid.native_action import native_action_block_report
from convertersmartgrid.obras_pf import PREFIJO_VARIACION
from convertersmartgrid.valle import nombre_caso_valle

#: Rol → nombre del caso. Fijos y reutilizados (usuario, 2026-10-11).
NOMBRES = {'base': 'Caso base', 'sin': 'Sin proyecto', 'con': 'Con proyecto'}

#: Marca en la descripción de un caso creado o renombrado por el sistema.
MARCA = 'convertersmartgrid:011:'
#: La marca de los casos creados antes del cambio de nombre (058:RF-9): sin ella, ningún flujo
#: reconocía los casos de NA203 + NA205 ni de SM218 (2026-11-01, «falta Con proyecto»).
MARCA_ANTERIOR = 'igea-dgs:011:'  # legado-058
MARCAS = (MARCA, MARCA_ANTERIOR)


def nombre_caso(rol: str, anio: int | None = None) -> str:
    """Nombre del caso de un rol y un año de medición (025:RF-14, RF-17).

    Sin año, los de siempre: son los que ya tienen los proyectos (calibrados con 2026).
    Otro año tiene su «Sin proyecto <año>» y su «Con proyecto <año>»; el «Caso base», la
    red tal como vino, es el mismo para todos (usuario, 2026-10-23: 2025 aparte de 2026,
    sin mezclarse).
    """
    return f'{NOMBRES[rol]} {anio}' if anio and rol != 'base' else NOMBRES[rol]


def _clave(rol: str, anio: int | None) -> str:
    """La marca del rol: ``sin@2025``, para que un «Sin proyecto 2025» ajeno no pase por suyo."""
    return f'{rol}@{anio}' if anio and rol != 'base' else rol


def anio_del_plan(plan: dict) -> int | None:
    """El año de los casos que pide el plan (``anio_casos``); ninguno, los de siempre."""
    anio = plan.get('anio_casos')
    return int(anio) if anio else None


# =========================================================================== marcas
def _desc(obj) -> list[str]:
    """``desc`` es un vector de cadenas en DIgSILENT; en un objeto nuevo puede faltar."""
    d = getattr(obj, 'desc', None)
    if d is None:
        return []
    return [str(x) for x in d] if isinstance(d, (list, tuple)) else [str(d)]


def rol_de(caso) -> str | None:
    """El rol que el sistema dio a este caso, o ``None`` si no es uno suyo."""
    for linea in _desc(caso):
        for marca in MARCAS:
            if linea.startswith(marca):
                return linea[len(marca):]
    return None


def _marcar(caso, rol: str) -> None:
    caso.desc = [x for x in _desc(caso) if not x.startswith(MARCAS)] + [MARCA + rol]


def casos_del_proyecto(app, anio: int | None = None) -> dict[str, object]:
    """Rol → caso, de los que el sistema ya dejó en el proyecto (RF-51 a RF-54 los usan).

    Con ``anio``, el «Caso base» y los de ese año (025:RF-17); sin él, los de siempre.
    """
    carpeta = app.GetProjectFolder('study')
    claves = {_clave(rol, anio): rol for rol in NOMBRES}
    out = {}
    for caso in (carpeta.GetContents('*.IntCase') if carpeta else []):
        rol = claves.get(rol_de(caso))
        if rol is not None and caso.loc_name == nombre_caso(rol, anio):
            out[rol] = caso
    return out


def tres_casos(app, anio: int | None = None) -> dict[str, object]:
    """Los tres casos si el sistema ya los dejó todos; si falta alguno, vacío.

    Es la condición de RF-51 a RF-54: mientras no existan los tres, el ajuste y las
    cargas trabajan en el caso activo, como antes de esta spec.
    """
    casos = casos_del_proyecto(app, anio)
    return casos if len(casos) == len(NOMBRES) else {}


def ajustes_de(app, feeder: str) -> list:
    """Variaciones de ajuste (``Ajuste_<alimentador>_…``) de un alimentador."""
    carpeta = app.GetProjectFolder('scheme')
    todas = carpeta.GetContents('*.IntScheme', 1) if carpeta else []
    return [v for v in todas if _de_alimentador(v.loc_name, 'Ajuste_', [feeder])]


def _pct(x) -> str:
    return f'{x * 100:.1f}'.replace('.', ',') + ' %' if isinstance(x, (int, float)) else '?'


# =========================================================================== variaciones
def _de_alimentador(nombre: str, prefijo: str, feeders: list[str]) -> str | None:
    """El alimentador de una variación ``<prefijo>_…_<alimentador>_…`` de las specs 006 y 007."""
    if not nombre.startswith(prefijo):
        return None
    for f in feeders:
        token = nombre_pf(f)
        if nombre.startswith(f'{prefijo}{token}_') or f'_{token}_' in nombre[len(prefijo):]:
            return f
    return None


def objetos_de_variacion(variacion) -> list[tuple[str, str]]:
    """``(clase, nombre)`` de lo que graban las etapas de una variación (spec 014).

    Recursivo dentro de cada etapa: la carga nueva de la 007 cuelga de la SED que la etapa
    crea. Se lee una vez por variación y por trabajo, no por carga.
    """
    out = []
    for etapa in variacion.GetContents('*.IntSstage'):
        out += [(o.GetClassName(), o.loc_name) for o in etapa.GetContents('*', 1)]
    return out


def es_ajuste_puro(variacion) -> bool:
    """Un ``Ajuste_…`` cuyas etapas solo cambian cargas: lo dejó el ajuste y nada más.

    CA101 (2026-10-14): el operador cambió el tipo de cuatro transformadores con
    ``Ajuste_CA101_20261013_203247_3`` grabando, y los ajustes siguientes lo desactivaron
    por su nombre. Una variación así es del operador (014:RF-3).
    """
    return (variacion.loc_name.startswith('Ajuste_')
            and all(clase == 'ElmLod' for clase, _ in objetos_de_variacion(variacion)))


def es_de_carga_nueva(variacion) -> bool:
    """Variación de una carga nueva de la spec 007 (``Carga_<SED>_<alim>_…``)."""
    return variacion.loc_name.startswith('Carga_')


def es_del_catalogo(variacion) -> bool:
    """Variación de los conductores con su ficha o de los transformadores de SED (spec 032)."""
    from convertersmartgrid.escaneo import PREFIJOS_CATALOGO

    return variacion.loc_name.startswith(PREFIJOS_CATALOGO)


def es_del_operador(variacion) -> bool:
    """Ni de carga nueva, ni ajuste puro, ni del catálogo: se conserva tal como la dejó el
    operador (spec 014)."""
    return (not es_de_carga_nueva(variacion) and not es_ajuste_puro(variacion)
            and not es_del_catalogo(variacion))


def clasificar(variaciones, feeders: list[str], base: list[str], demandas: str | None) -> dict:
    """Separa las variaciones del proyecto por su papel en los casos.

    - ``base``: las del último ajuste (las que da el plan) y la de demandas.
    - ``cargas``: las de cargas nuevas de los alimentadores marcados (``Carga_<SED>_<alim>_…``,
      spec 007, RF-10).
    - ``anteriores``: otros ajustes puros de esos alimentadores (``Ajuste_<alim>_…`` que solo
      cambian cargas), que se desactivan sin borrar (RF-50).
    - ``operador``: cualquier otra, también un ajuste que grabó cambios del operador; no se
      desactiva nunca (014:RF-3, RF-15, RF-20).
    """
    nombres_base = set(base) | ({demandas} if demandas else set())
    out = {'base': [], 'cargas': [], 'anteriores': [], 'operador': []}
    for v in variaciones:
        n = v.loc_name
        if n in nombres_base:
            out['base'].append(v)
        elif es_de_carga_nueva(v):
            if _de_alimentador(n, 'Carga_', feeders):
                out['cargas'].append(v)
        elif es_ajuste_puro(v):
            if _de_alimentador(n, 'Ajuste_', feeders):
                out['anteriores'].append(v)
        else:
            out['operador'].append(v)
    for k in out:
        out[k].sort(key=lambda v: v.loc_name)
    return out


def obras_del_con_proyecto_sin_anio(app) -> list:
    """Las obras activas en «Con proyecto» sin año: ni cargas nuevas ni ajustes puros (025:RF-42).

    Las cargas nuevas reutilizadas de otro año se crearon sobre ellas: las nueve de TA225 en
    IN111 + TA225 (2026-10-23) partían tramos que solo existen con el enlace, la migración y
    la terna de 2026, y sin ellas «Con proyecto 2025» unía 10 kV con 22,9 kV. Deja activo el
    caso que lo estaba.
    """
    con = caso(app, 'con')
    if con is None:
        return []
    previo = app.GetActiveStudyCase()
    con.Activate()
    obras = [v for v in (app.GetActiveNetworkVariations() or []) if es_del_operador(v)]
    if previo is not None:
        previo.Activate()
    return obras


def cargas_que_no_convergen_juntas(app, caso, converge) -> dict | None:
    """Si el caso no converge con sus cargas nuevas, cuáles no caben juntas (025:RF-43).

    PA217 y TM105 en «Con proyecto 2025» (2026-10-23): ningún flujo convergía con todas, y
    cada carga sola sí; quitar PI_1 o PI_8 (CH_3 o CH_5) bastaba. Se prueba cada carga sola
    y el caso sin cada una, y todo queda como estaba. ``converge(app)`` corre el flujo del
    caso activo. ``None`` si converge con todas.
    """
    caso.Activate()
    cargas = [v for v in (app.GetActiveNetworkVariations() or []) if es_de_carga_nueva(v)]
    if not cargas or converge(app):
        return None
    solas_no, basta_quitar = [], []
    try:
        for v in cargas:
            for w in cargas:
                if w is not v:
                    w.Deactivate()
            if not converge(app):
                solas_no.append(v.loc_name)
            for w in cargas:
                w.Activate()
        for v in cargas:
            v.Deactivate()
            if converge(app):
                basta_quitar.append(v.loc_name)
            v.Activate()
    finally:
        activas = {v.loc_name for v in (app.GetActiveNetworkVariations() or [])}
        for v in cargas:
            if v.loc_name not in activas:
                v.Activate()
    return {'caso': caso.loc_name, 'cargas': sorted(v.loc_name for v in cargas),
            'solas_que_no_convergen': sorted(solas_no), 'basta_quitar_una_de': sorted(basta_quitar)}


def operador_a_con_proyecto(app, casos: dict, variaciones=None) -> list[str]:
    """Activa en «Con proyecto» las variaciones del operador activas en «Sin proyecto».

    014:RF-21: «Con proyecto» es «Sin proyecto» más las cargas nuevas; un cambio que el
    operador grabó en «Sin proyecto» después de copiarlo también tiene que estar. Solo
    activa, nunca apaga. Devuelve los nombres activados (014:RF-22). Deja activo el caso
    que lo estaba.
    """
    previo = app.GetActiveStudyCase()
    casos['sin'].Activate()
    # 032:RF-27: las del catálogo también; «Con proyecto» lleva los conductores con su ficha
    # y los transformadores que se calibraron en «Sin proyecto».
    en_sin = [v for v in (app.GetActiveNetworkVariations() or [])
              if es_del_operador(v) or es_del_catalogo(v)]
    if variaciones is not None:
        nombres = {v.loc_name for v in variaciones}
        en_sin = [v for v in en_sin if v.loc_name in nombres]
    casos['con'].Activate()
    ya = {v.loc_name for v in (app.GetActiveNetworkVariations() or [])}
    activadas = []
    for v in en_sin:
        if v.loc_name not in ya:
            v.Activate()
            activadas.append(v.loc_name)
    if previo is not None:
        previo.Activate()
    return sorted(activadas)


#: Datos de operación que el operador cambia a mano y que DIgSILENT guarda en el escenario
#: del caso (014:RF-32). Las cargas no: su demanda la lleva el ajuste (014:RF-4).
OPERACION = {
    'ElmShnt': ('outserv', 'ncapa'),
    'ElmCoup': ('outserv', 'on_off'),
    'StaSwitch': ('on_off',),
    # 081:RF-77: las unidades en paralelo son del escenario. PRUEBA_007 (2026-11-05): SE20497 con
    # 4 × 630 kVA en «Sin proyecto» y 1 × 630 kVA en «Con proyecto», que no convergía ni sin cargas.
    'ElmTr2': ('outserv', 'nntap', 'ntnum'),
    'ElmLne': ('outserv',),
    # La consigna de la fuente también: SM218 (2026-11-01), la recalibración dejó «Sin proyecto» a
    # 1,02 p.u. y «Con proyecto» seguía a 1,00; la escalera medía las obras dos puntos más abajo.
    'ElmXnet': ('usetp',),
}


def _foto_operacion(app) -> dict[str, tuple[object, dict]]:
    """Ruta → (objeto, datos de operación) de la red del caso activo."""
    out = {}
    for clase, attrs in OPERACION.items():
        for o in app.GetCalcRelevantObjects(f'*.{clase}') or []:
            datos = {}
            for a in attrs:
                try:
                    datos[a] = o.GetAttribute(a)
                except Exception:  # noqa: BLE001 - un atributo que la clase no tiene
                    continue
            out[o.GetFullName()] = (o, datos)
    return out


def _igual(a, b) -> bool:
    try:
        return abs(float(a) - float(b)) <= 1e-9 * max(1.0, abs(float(a)))
    except (TypeError, ValueError):
        return a == b


def sin_a_con_proyecto(app, casos: dict, excluir=()) -> dict:
    """Lo que el operador hizo a mano en «Sin proyecto», también en «Con proyecto».

    014:RF-31 a RF-34. «Con proyecto» es «Sin proyecto» más las cargas nuevas y las obras,
    pero se copia una vez y después cada caso va por su lado: en PN107 (2026-10-16) el
    operador creó un banco en «Sin proyecto» y no estaba en «Con proyecto». Se activan las
    variaciones del operador (RF-21) y, por cada dato de operación de :data:`OPERACION`
    que «Sin proyecto» cambió respecto del «Caso base» y «Con proyecto» no, se escribe en
    el escenario de «Con proyecto». Si los dos lo cambiaron distinto, manda «Con
    proyecto» (una obra) y se avisa; lo que está en «Sin proyecto» y falta en «Con
    proyecto» se lista. Deja activo el caso que lo estaba.
    """
    out = {'variaciones': [], 'copiados': [], 'conflictos': [], 'faltan': [], 'avisos': [],
           'etapas_adelantadas': []}
    if 'sin' not in casos or 'con' not in casos:
        return out
    previo = app.GetActiveStudyCase()
    try:
        out['variaciones'] = operador_a_con_proyecto(app, casos)
        # 081:RF-78: las etapas de la base (Fichas_, SED_NTP_) fechadas después de la hora de «Con
        # proyecto» no se aplican en él. PRUEBA_007 (2026-11-06): «Con proyecto» a las 15:01:13, las
        # etapas a las :14 y :15; seguía con 1 × 160 kVA en SE20497 y no convergía ni sin cargas.
        casos['con'].Activate()
        out['etapas_adelantadas'] = etapas_al_dia(app)
        if out['etapas_adelantadas']:
            out['avisos'].append('«Con proyecto» no veía las etapas de ' + ', '.join(out['etapas_adelantadas'])
                                 + ' por su fecha: se adelantan a la hora del caso (081:RF-78).')
        fotos = {}
        for rol in ('base', 'sin', 'con'):
            if rol in casos:
                casos[rol].Activate()
                fotos[rol] = _foto_operacion(app)
        base, sin, con = fotos.get('base', {}), fotos['sin'], fotos['con']
        cambios = []
        excluir = set(excluir or ())
        for ruta, (obj_sin, datos) in sorted(sin.items()):
            nombre = getattr(obj_sin, 'loc_name', ruta)
            # 098:RF-48: la transferencia del operador deshecha en «Con proyecto» como alternativa no elegida no se
            # vuelve a copiar desde «Sin proyecto». CA101 + CHN102 (2026-11-07): al aplicar la obra de CA101, esta
            # copia la reponía y CHN102 volvía a cargar la zona (0,703 p.u.) con la obra calculada sin ella.
            if nombre in excluir:
                continue
            if ruta not in con:
                out['faltan'].append(nombre)
                continue
            obj_con, en_con = con[ruta]
            en_base = base.get(ruta, (None, {}))[1]
            for attr, valor in datos.items():
                if attr not in en_con or _igual(valor, en_con[attr]):
                    continue
                if attr in en_base and not _igual(en_base[attr], en_con[attr]):
                    if not _igual(en_base[attr], valor):
                        out['conflictos'].append({'objeto': nombre, 'dato': attr,
                                                  'sin': valor, 'con': en_con[attr]})
                    continue                     # lo cambió «Con proyecto» (una obra)
                cambios.append((obj_con, nombre, attr, valor, en_con[attr]))
        if cambios:
            casos['con'].Activate()
            escenario = app.GetActiveScenario()
            if escenario is None:
                out['avisos'].append('«Con proyecto» no tiene escenario activo: no se copian '
                                     f'{len(cambios)} dato(s) de operación de «Sin proyecto».')
            else:
                for obj, nombre, attr, valor, antes in cambios:
                    obj.SetAttribute(attr, valor)
                    out['copiados'].append({'objeto': nombre, 'dato': attr,
                                            'antes': antes, 'ahora': valor})
                escenario.Save()
        if out['variaciones']:
            out['avisos'].append('Activadas en «Con proyecto» porque están activas en «Sin '
                                 'proyecto»: ' + ', '.join(out['variaciones']))
        if out['copiados']:
            out['avisos'].append(
                f"«Con proyecto» toma de «Sin proyecto» {len(out['copiados'])} dato(s) de "
                'operación cambiados a mano: ' + ', '.join(
                    f"{c['objeto']}.{c['dato']}" for c in out['copiados'][:10]) + ' (014:RF-32).')
        if out['conflictos']:
            out['avisos'].append(
                'Cambiados distinto en «Sin proyecto» y en «Con proyecto»; se deja el de «Con '
                'proyecto»: ' + ', '.join(f"{c['objeto']}.{c['dato']}" for c in out['conflictos'][:10])
                + ' (014:RF-33).')
        if out['faltan']:
            out['avisos'].append(
                'Están en «Sin proyecto» y no en «Con proyecto» (una variación de «Con proyecto» '
                'los quita o la del operador está inactiva): ' + ', '.join(out['faltan'][:10])
                + ' (014:RF-34).')
    finally:
        if previo is not None and app.GetActiveStudyCase() is not previo:
            previo.Activate()
    return out


def operacion_de_las_obras(app, casos_anio: dict) -> dict:
    """La operación que las obras de «Con proyecto» dejaron en su escenario, también en «Con
    proyecto <año>» (025:RF-42b).

    IN111 + TA225 (2026-10-23): activas las variaciones del enlace y de la migración, «Con
    proyecto 2025» convergía, pero el enlace seguía fuera de servicio y el tramo que la
    migración abre, en servicio: el ``outserv`` de una línea es dato del escenario, y el de
    2025 es copia del de «Sin proyecto 2025». IC_11, IC_12, IC_15 e IC_17 quedaban sin
    tensión (0 kW en el flujo). Por cada dato de :data:`OPERACION` que «Con proyecto»
    cambió respecto de «Sin proyecto» (lo que hacen sus obras), si «Con proyecto <año>» aún
    tiene el de «Sin proyecto <año>», se escribe en su escenario. Si el año lo cambió por su
    cuenta (una obra suya, el operador), manda el año y se avisa. Deja activo el caso que lo
    estaba.
    """
    out = {'copiados': [], 'conflictos': [], 'faltan': [], 'avisos': []}
    sin0, con0 = caso(app, 'sin'), caso(app, 'con')
    if sin0 is None or con0 is None or 'sin' not in casos_anio or 'con' not in casos_anio:
        return out
    previo = app.GetActiveStudyCase()
    try:
        fotos = {}
        for clave, c in (('sin0', sin0), ('con0', con0), ('sin', casos_anio['sin']),
                         ('con', casos_anio['con'])):
            c.Activate()
            fotos[clave] = _foto_operacion(app)
        cambios = []
        for ruta, (_obj, datos) in sorted(fotos['con0'].items()):
            en_sin0 = fotos['sin0'].get(ruta, (None, {}))[1]
            for attr, valor in datos.items():
                if attr in en_sin0 and _igual(en_sin0[attr], valor):
                    continue                            # las obras no lo cambiaron
                if ruta not in fotos['con']:
                    out['faltan'].append(getattr(_obj, 'loc_name', ruta))
                    break
                obj, en_con = fotos['con'][ruta]
                if attr not in en_con or _igual(en_con[attr], valor):
                    continue
                en_sin = fotos['sin'].get(ruta, (None, {}))[1]
                if attr in en_sin and not _igual(en_sin[attr], en_con[attr]):
                    out['conflictos'].append({'objeto': obj.loc_name, 'dato': attr,
                                              'con': valor, 'anio': en_con[attr]})
                    continue                            # lo cambió el caso del año
                cambios.append((obj, attr, valor, en_con[attr]))
        if cambios:
            casos_anio['con'].Activate()
            escenario = app.GetActiveScenario()
            if escenario is None:
                out['avisos'].append(f'«{casos_anio["con"].loc_name}» no tiene escenario activo: '
                                     f'no se copian {len(cambios)} dato(s) de operación de las obras.')
            else:
                for obj, attr, valor, antes in cambios:
                    obj.SetAttribute(attr, valor)
                    out['copiados'].append({'objeto': obj.loc_name, 'dato': attr,
                                            'antes': antes, 'ahora': valor})
                escenario.Save()
        nombre = getattr(casos_anio['con'], 'loc_name', nombre_caso('con'))
        if out['copiados']:
            out['avisos'].append(
                f"«{nombre}» toma de «{NOMBRES['con']}» la operación de sus obras: " + ', '.join(
                    f"{c['objeto']}.{c['dato']}" for c in out['copiados'][:10]) + ' (025:RF-42b).')
        if out['conflictos']:
            out['avisos'].append(
                f'Cambiados distinto por las obras de «{NOMBRES["con"]}» y en «{nombre}»; se deja '
                'el del año: ' + ', '.join(f"{c['objeto']}.{c['dato']}" for c in out['conflictos'][:10])
                + ' (025:RF-42b).')
        if out['faltan']:
            out['avisos'].append(
                f'Las obras de «{NOMBRES["con"]}» cambian objetos que no están en «{nombre}»: '
                + ', '.join(out['faltan'][:10]) + ' (025:RF-42b).')
    finally:
        if previo is not None and app.GetActiveStudyCase() is not previo:
            previo.Activate()
    return out


def _dejar_activas(app, caso, activas: list, inactivas: list) -> list[str]:
    """En ``caso``, activa ``activas`` y desactiva ``inactivas``; devuelve lo que queda activo."""
    caso.Activate()
    for v in inactivas:
        v.Deactivate()
    for v in activas:
        v.Activate()
    return sorted(v.loc_name for v in (app.GetActiveNetworkVariations() or []))


# =========================================================================== escenarios
def _escenario_propio(app, caso, rol: str, origen, anio: int | None = None) -> str:
    """Deja en ``caso`` un escenario con su nombre: copia del de ``origen`` o uno nuevo.

    Un caso reutilizado que ya tiene escenario lo conserva: puede haberlo cambiado el
    operador en DIgSILENT, y no se sobrescribe (casos límite de la spec). Con ``anio``, el
    escenario lleva el nombre del caso de ese año (025:RF-15).
    """
    nombre = nombre_caso(rol, anio)
    caso.Activate()
    actual = app.GetActiveScenario()
    if actual is not None and actual.loc_name == nombre:
        return actual.loc_name
    carpeta = app.GetProjectFolder('scen', 1)
    existente = next((e for e in carpeta.GetContents('*.IntScenario')
                      if e.loc_name == nombre), None)
    if existente is not None:
        nuevo = existente
    elif origen is not None:
        nuevo = carpeta.AddCopy(origen, nombre)
    else:
        nuevo = carpeta.CreateObject('IntScenario', nombre)
    nuevo.Activate()
    return nuevo.loc_name


def crear_con_proyecto(app, sin, anio: int | None = None):
    """«Con proyecto» como copia de «Sin proyecto», con sus variaciones activas (014:RF-18).

    Lo usan la preparación de los casos y las obras: lo que se hizo en «Sin proyecto»
    pasa a «Con proyecto» porque la copia se hace después (016:RF-12). Devuelve el caso,
    marcado y con su escenario, copia del de «Sin proyecto». Con ``anio``, el de ese año,
    copia de su «Sin proyecto <año>» (025:RF-16).
    """
    previo = app.GetActiveStudyCase()
    con = app.GetProjectFolder('study').AddCopy(sin, nombre_caso('con', anio))
    _marcar(con, _clave('con', anio))
    _escenario_propio(app, con, 'con', _escenario_de(app, sin), anio)
    # La copia tiene que ver las etapas que ve «Sin proyecto». Con CA101 + PE104 (2026-11-07) quedó en
    # 1793026149 y las etapas de la base en …150 (fichas, 707 tramos) y …151 (7 SED NTP): «activas» pero sin
    # aplicar, CA101 entero sin tensión (687 barras) y la obra inactiva (044 y 048, T4). Subir la hora del
    # caso no se mantiene (081:RF-78); se adelantan las etapas, como hace ``sin_a_con_proyecto``.
    con.Activate()
    etapas_al_dia(app)
    if previo is not None and previo is not con:
        previo.Activate()
    return con


# =========================================================================== cargas nuevas
#: Caso de diagnóstico con las cargas nuevas y sin obras (025:RF-61). No está en ``NOMBRES``:
#: los tres casos de la spec 011 siguen siendo los que decide ``tres_casos``.
NOMBRE_CARGAS = 'Cargas nuevas'
ROL_CARGAS = 'cargas'


def nombre_cargas_nuevas(anio: int | None = None) -> str:
    return f'{NOMBRE_CARGAS} {anio}' if anio else NOMBRE_CARGAS


def caso_cargas_nuevas(app, anio: int | None = None):
    """El caso «Cargas nuevas» del sistema para ese año, por su nombre y su marca, o ``None`` (037:RF-4, 086:RF-88)."""
    carpeta = app.GetProjectFolder('study')
    clave = _clave(ROL_CARGAS, anio)
    return next((c for c in (carpeta.GetContents('*.IntCase') if carpeta else [])
                 if c.loc_name == nombre_cargas_nuevas(anio) and rol_de(c) == clave), None)


def _escenario_renovado(app, caso, nombre: str, origen) -> str:
    """El escenario de ``caso``, copia nueva de ``origen`` (025:RF-62).

    Se renueva en cada inserción: es un caso de diagnóstico que nadie toca a mano, y tiene
    que mostrar la demanda de «Sin proyecto» de ese momento, también tras recalibrarlo.
    """
    caso.Activate()
    carpeta = app.GetProjectFolder('scen', 1)
    actual = app.GetActiveScenario()
    if actual is not None:
        actual.Deactivate(0)
    for e in carpeta.GetContents('*.IntScenario'):
        if e.loc_name == nombre:
            e.Delete()
    nuevo = carpeta.AddCopy(origen, nombre) if origen is not None else carpeta.CreateObject('IntScenario', nombre)
    nuevo.Activate()
    return nuevo.loc_name


#: Lo que se compara, objeto a objeto, entre «Sin proyecto» y un caso que sale de él (025:RF-81, RF-82).
#: PA217 (2026-11-12): el operador puso bancos y pasó tramos a dos conductores de 120 mm² en «Sin
#: proyecto», y «Cargas nuevas» no los tenía. Son los datos que el operador cambia: bancos (pasos y
#: potencia), tramos (tipo, conductores en paralelo, largo, servicio), transformadores (tipo, toma y
#: unidades), interruptores (estado) y cargas (potencia y escala). Un atributo que la clase no tenga
#: en esta versión de DIgSILENT se salta.
RED_COMPARADA = {
    'ElmShnt': ('outserv', 'ncapa', 'qtotn', 'qcapn'),
    'ElmLne': ('typ_id', 'nlnum', 'dline', 'outserv'),
    'ElmTr2': ('typ_id', 'nntap', 'ntnum', 'outserv'),
    'ElmCoup': ('on_off', 'outserv'),
    'StaSwitch': ('on_off',),
    'ElmLod': ('plini', 'qlini', 'scale0', 'outserv'),
}


def _valor_comparable(v):
    """Un tipo (``typ_id``) por su nombre; un vector, como tupla; lo demás, tal cual."""
    if isinstance(v, (list, tuple)):
        return tuple(_valor_comparable(x) for x in v)
    if v is None or isinstance(v, (int, float, str, bool)):
        return v
    return getattr(v, 'loc_name', str(v))


def _barra_de_interruptor(sw):
    """La barra del cubículo de un ``StaSwitch`` (interruptor → cubículo → barra), o ``None``."""
    try:
        cub = sw.GetParent()
        return cub.GetParent() if cub is not None else None
    except Exception:  # noqa: BLE001 - un interruptor suelto: no es de ningún alimentador
        return None


def foto_de_red(app, feeders=None) -> dict[str, tuple[str, str, dict]]:
    """Ruta → (clase, nombre, datos de :data:`RED_COMPARADA`) de la red del caso activo (025:RF-81).

    Con ``feeders``, solo lo de sus ``ElmFeeder`` (los interruptores, por la barra de su cubículo); si
    ninguno tiene ``ElmFeeder``, toda la red calculable. El ``ElmFeeder`` da sus objetos según la
    última topología calculada: quien llama corre antes un flujo en el caso.
    """
    elms = {f.loc_name: f for f in (app.GetCalcRelevantObjects('*.ElmFeeder') or [])}
    propios = [elms[f] for f in (feeders or []) if f in elms]
    barras = ({t.GetFullName() for e in propios for t in (e.GetObjs('ElmTerm') or [])}
              if propios else None)
    out: dict[str, tuple[str, str, dict]] = {}
    for clase, attrs in RED_COMPARADA.items():
        if clase == 'StaSwitch' or not propios:
            objetos = list(app.GetCalcRelevantObjects(f'*.{clase}') or [])
        else:
            objetos = [o for e in propios for o in (e.GetObjs(clase) or [])]
        for o in objetos:
            if clase == 'StaSwitch' and barras is not None:
                barra = _barra_de_interruptor(o)
                if barra is None or barra.GetFullName() not in barras:
                    continue
            datos = {}
            for a in attrs:
                try:
                    datos[a] = _valor_comparable(o.GetAttribute(a))
                except Exception:  # noqa: BLE001 - un atributo que la clase no tiene
                    continue
            out[o.GetFullName()] = (clase, getattr(o, 'loc_name', ''), datos)
    return out


def diferencias_de_red(ref: dict, otra: dict, nombre_ref: str, nombre_otra: str,
                       excluir=frozenset()) -> list[dict]:
    """Lo que tiene ``ref`` y no ``otra``, lo que ``otra`` tiene de más y cada dato distinto (025:RF-81).

    ``excluir`` son ``(clase, nombre)`` que se dejan fuera: lo que traen las obras y las cargas
    nuevas de «Con proyecto», que difiere a propósito (RF-82). Cada diferencia lleva su ``texto``.
    """
    out = []
    for ruta in sorted(set(ref) | set(otra)):
        clase, nombre, datos = ref.get(ruta) or otra[ruta]
        if (clase, nombre) in excluir:
            continue
        if ruta not in otra:
            out.append({'clase': clase, 'objeto': nombre, 'dato': None,
                        'texto': f'en «{nombre_ref}» hay {clase} {nombre} y en «{nombre_otra}» no'})
            continue
        if ruta not in ref:
            out.append({'clase': clase, 'objeto': nombre, 'dato': None,
                        'texto': f'en «{nombre_otra}» hay {clase} {nombre} y en «{nombre_ref}» no'})
            continue
        en_otra = otra[ruta][2]
        for attr, valor in datos.items():
            if attr in en_otra and not _igual(valor, en_otra[attr]):
                out.append({'clase': clase, 'objeto': nombre, 'dato': attr, 'ref': valor,
                            'otro': en_otra[attr],
                            'texto': f'{clase} {nombre}: {attr} es {valor} en «{nombre_ref}» y '
                                     f'{en_otra[attr]} en «{nombre_otra}»'})
    return out


def _foto_del_caso(app, caso, feeders, flujo) -> tuple[dict, tuple]:
    """:func:`foto_de_red` con ``caso`` activo y un flujo antes, para que el ``ElmFeeder`` esté al día.

    Devuelve también lo que dio el flujo: en «Cargas nuevas» es el flujo de partida (RF-65).
    """
    caso.Activate()
    resultado = flujo(app) if flujo is not None else (None, [])
    return foto_de_red(app, feeders), resultado


def _lo_de_sus_variaciones(app, caso, ref) -> set[tuple[str, str]]:
    """``(clase, nombre)`` de lo que graban las variaciones activas en ``caso`` y no en ``ref`` (RF-82)."""
    ref.Activate()
    en_ref = {v.loc_name for v in (app.GetActiveNetworkVariations() or [])}
    caso.Activate()
    out: set[tuple[str, str]] = set()
    for v in app.GetActiveNetworkVariations() or []:
        if v.loc_name not in en_ref:
            out.update(objetos_de_variacion(v))
    return out


def _aviso_diferencias(nombre_ref: str, nombre: str, difs: list[dict], rf: str, extra: str = '') -> str:
    lista = '; '.join(d['texto'] for d in difs[:10]) + (f' y {len(difs) - 10} más' if len(difs) > 10 else '')
    return f'«{nombre}» no es igual a «{nombre_ref}»{extra}: {lista} ({rf}).'


def con_frente_a_sin(app, sin, con, feeders, flujo, excluir=(), foto_sin=None) -> dict:
    """«Con proyecto» frente a «Sin proyecto», sin lo que traen sus obras y sus cargas nuevas (025:RF-82).

    Lo que «Sin proyecto» tiene y «Con proyecto» no, fuera de sus variaciones propias, es algo que no
    pasó de un caso al otro (014:RF-31 a RF-34). Solo avisa; deja activo el caso que lo estaba.
    """
    previo = app.GetActiveStudyCase()
    try:
        ref = foto_sin if foto_sin is not None else _foto_del_caso(app, sin, feeders, flujo)[0]
        fuera = _lo_de_sus_variaciones(app, con, sin) | {(c, n) for c in RED_COMPARADA for n in excluir}
        foto = _foto_del_caso(app, con, feeders, flujo)[0]
        difs = diferencias_de_red(ref, foto, sin.loc_name, con.loc_name, fuera)
    finally:
        if previo is not None and app.GetActiveStudyCase() is not previo:
            previo.Activate()
    avisos = ([_aviso_diferencias(sin.loc_name, con.loc_name, difs, '025:RF-82',
                                  ' fuera de sus obras y sus cargas nuevas')] if difs else [])
    return {'caso': con.loc_name, 'frente_a': sin.loc_name, 'iguales': not difs, 'diferencias': difs,
            'avisos': avisos}


def _borrar_caso(app, caso, sin) -> bool:
    """Borra el «Cargas nuevas» del sistema para copiarlo de nuevo (025:RF-79).

    Manual de PowerFactory 2024, 12.1: el caso guarda sus órdenes de cálculo, la hora, qué variaciones y
    qué escenario están activos, los resultados y los gráficos del estudio. Borrarlo quita solo eso: las
    variaciones (cap. 16) y los escenarios (cap. 15) están en sus carpetas y no cuelgan de él, y los
    diagramas de red están en el modelo de red. La copia nueva trae los de «Sin proyecto» (su escritorio
    con el perfil de tensión, 094:RF-15); el escenario propio lo renueva :func:`_escenario_renovado`. No
    se borra el caso activo: antes se activa «Sin proyecto». Devuelve si se borró: ``Delete`` da 0.
    """
    if app.GetActiveStudyCase() is caso:
        sin.Activate()
    try:
        return not caso.Delete()
    except Exception:  # noqa: BLE001 - DIgSILENT no lo deja borrar: se reutiliza y se avisa
        return False


def _armar_cargas_nuevas(app, sin, carpeta, nombre: str, clave: str, informe: dict, caso=None):
    """Copia fresca de «Sin proyecto» con su escenario, sus variaciones y sus etapas al día (RF-79, RF-80).

    Con ``caso``, el que no se pudo borrar: se reutiliza como antes de RF-79, en vez de dejar dos.
    """
    if caso is None:
        caso = carpeta.AddCopy(sin, nombre)
        _marcar(caso, clave)
    # RF-64: lo de «Sin proyecto», nada más: sus variaciones activas, ninguna de cargas. La copia ya
    # las trae; esto lo asegura si DIgSILENT copiara distinto.
    sin.Activate()
    de_sin = {v.loc_name for v in (app.GetActiveNetworkVariations() or []) if not es_de_carga_nueva(v)}
    esc_sin = app.GetActiveScenario()
    informe['escenario'] = _escenario_renovado(app, caso, nombre, esc_sin)
    for v in list(app.GetActiveNetworkVariations() or []):
        if es_de_carga_nueva(v) or v.loc_name not in de_sin:
            v.Deactivate()
    carpeta_var = app.GetProjectFolder('scheme')
    for v in (carpeta_var.GetContents('*.IntScheme', 1) if carpeta_var else []):
        if v.loc_name in de_sin and v not in (app.GetActiveNetworkVariations() or []):
            v.Activate()
    # RF-80: una etapa fechada después de la hora del caso no se aplica aunque su variación esté
    # activa, y DIgSILENT no avisa (SM218 y PRUEBA_007, 081:RF-78). Se adelantan antes de comparar.
    adelantadas = etapas_al_dia(app)
    informe['etapas_adelantadas'] = sorted(set(informe['etapas_adelantadas']) | set(adelantadas))
    return caso


def cargas_nuevas(app, sin, anio: int | None, variaciones: list, flujo,
                  antes=lambda _app, _v: {}, explicar=lambda v, _antes, _mensajes: {'texto': v.loc_name},
                  feeders=None, con=None, excluir_con=()) -> dict:
    """«Cargas nuevas <año>»: copia fresca de «Sin proyecto <año>» y de su escenario, con las cargas
    nuevas activadas una a una (025:RF-61 a RF-66, RF-79 a RF-83).

    En cada inserción el caso del sistema se borra y se vuelve a copiar de «Sin proyecto» (RF-79): así
    trae la hora, las variaciones, el escenario y lo que el operador cambió allí (PA217, 2026-11-12:
    bancos y tramos de dos conductores de 120 mm² que el caso reutilizado no tenía). Se adelantan sus
    etapas (RF-80) y, antes de activar ninguna carga, se compara con «Sin proyecto» objeto a objeto en
    los alimentadores ``feeders`` (RF-81); si sale distinto se rehace una vez y, si sigue distinto, se
    avisa con la lista y se sigue (RF-83). Con ``con``, también «Con proyecto» frente a «Sin proyecto»,
    sin lo que traen sus obras y sus cargas nuevas (RF-82).

    ``flujo(app)`` ejecuta el flujo del caso activo y devuelve ``(converge, mensajes)``.
    ``antes(app, v)`` lee el estado con el último flujo que convergió, antes de activar
    ``v``: al cambiar la red, DIgSILENT puede borrar esos resultados. ``explicar(v, antes,
    mensajes)`` arma el motivo de una carga que no deja converger; se desactiva y se sigue
    con la siguiente, y el caso queda siempre convergido (RF-65, RF-66).
    """
    nombre = nombre_cargas_nuevas(anio)
    carpeta = app.GetProjectFolder('study')
    clave = _clave(ROL_CARGAS, anio)
    existentes = list(carpeta.GetContents('*.IntCase'))
    caso = next((c for c in existentes if c.loc_name == nombre and rol_de(c) == clave), None)
    informe: dict = {'caso': nombre, 'creado': True, 'recreado': caso is not None, 'activas': [],
                     'no_convergen': [], 'avisos': [], 'etapas_adelantadas': []}
    if any(c.loc_name == nombre and rol_de(c) != clave for c in existentes):
        # RF-61: un caso del operador con el mismo nombre no se toca, ni se borra el del sistema para
        # copiar otro con su nombre al lado (DIgSILENT tendría dos con el mismo nombre o lo renombraría).
        informe['avisos'].append(f'Hay un caso «{nombre}» que no creó el sistema: no se toca; '
                                 'renómbrelo en DIgSILENT para tener el de diagnóstico (025:RF-61).')
        informe['converge'] = None
        informe['creado'] = informe['recreado'] = False
        return informe
    previo = app.GetActiveStudyCase()
    era_este = previo is not None and previo is caso       # se borra: al final, el nuevo
    if era_este:
        previo = sin
    try:
        difs: list[dict] = []
        partida: tuple = (None, [])
        for intento in (1, 2):                                                     # RF-83
            reutilizado = None
            if caso is not None and not _borrar_caso(app, caso, sin):
                reutilizado = caso
                informe['avisos'].append(f'DIgSILENT no dejó borrar «{nombre}» para copiarlo otra vez de '
                                         f'«{sin.loc_name}»: se reutiliza y se compara con él (025:RF-79).')
            caso = _armar_cargas_nuevas(app, sin, carpeta, nombre, clave, informe, reutilizado)
            # «Sin proyecto» se fotografía después de armar la copia: las etapas que adelanta RF-80 son de
            # variaciones que también están activas en él, y desde ese momento también las ve.
            foto_sin = _foto_del_caso(app, sin, feeders, flujo)[0]
            if con is not None and 'con_frente_a_sin' not in informe:
                informe['con_frente_a_sin'] = con_frente_a_sin(app, sin, con, feeders, flujo, excluir_con,
                                                               foto_sin=foto_sin)
            # La copia, la última: su flujo es el de partida de las cargas nuevas.
            foto, partida = _foto_del_caso(app, caso, feeders, flujo)
            difs = diferencias_de_red(foto_sin, foto, sin.loc_name, nombre)
            informe['intentos'] = intento
            if not difs:
                break
        if era_este:
            previo = caso
        informe['igualdad'] = {'frente_a': sin.loc_name, 'iguales': not difs, 'diferencias': difs}
        if difs:
            informe['avisos'].append(_aviso_diferencias(
                sin.loc_name, nombre, difs, '025:RF-83',
                ' antes de activar las cargas nuevas, ni al copiarlo otra vez; se sigue con él'))
        if informe['etapas_adelantadas']:
            informe['avisos'].append(f'«{nombre}» no veía las etapas de ' + ', '.join(informe['etapas_adelantadas'])
                                     + ' por su fecha: se adelantan a la hora del caso (025:RF-80).')
        if 'con_frente_a_sin' in informe:
            informe['avisos'] += informe['con_frente_a_sin']['avisos']
        converge, mensajes = partida                     # «Cargas nuevas» sigue activo con ese flujo
        if not converge:
            informe['avisos'].append(f'«{nombre}» no converge ni sin cargas nuevas, como «Sin proyecto»: '
                                     'no se activa ninguna (025:RF-65). DIgSILENT: ' + '; '.join(mensajes[-3:]))
            informe['converge'] = False
            return informe
        vistas: set[str] = set()
        for v in variaciones:
            if v.loc_name in vistas:
                continue
            vistas.add(v.loc_name)
            previo_estado = antes(app, v)
            v.Activate()
            converge, mensajes = flujo(app)
            if converge:
                informe['activas'].append(v.loc_name)
                continue
            v.Deactivate()                                                 # RF-65, RF-66
            informe['no_convergen'].append({'variacion': v.loc_name,
                                            **explicar(v, previo_estado, mensajes)})
            flujo(app)                       # resultados convergidos para leer la siguiente
        informe['converge'] = bool(flujo(app)[0])
        for x in informe['no_convergen']:
            informe['avisos'].append(f'«{nombre}»: {x.get("texto") or x["variacion"]} (025:RF-66).')
    finally:
        if previo is not None and app.GetActiveStudyCase() is not previo:
            previo.Activate()
    return informe


# =========================================================================== valle
ROL_VALLE = 'valle'


def caso_valle(app, sin, anio: int | None) -> dict:
    """«Valle <año>»: copia de «Sin proyecto <año>» con su propio escenario (073:RF-13, RF-14).

    Es donde irá la calibración a valle, para no tocar el caso ni el escenario de la máxima. Un caso
    reutilizado conserva su escenario; uno ajeno con ese nombre no se toca (RF-15). Deja activo el
    caso que había. Aún no lo llama ningún trabajo de la web: se prueba en DIgSILENT en la 073 T8.
    """
    nombre = nombre_caso_valle(anio)
    carpeta = app.GetProjectFolder('study')
    clave = _clave(ROL_VALLE, anio)
    casos = list(carpeta.GetContents('*.IntCase'))
    caso = next((c for c in casos if c.loc_name == nombre and rol_de(c) == clave), None)
    informe: dict = {'caso': nombre, 'escenario': None, 'creado': caso is None, 'avisos': []}
    if caso is None and any(c.loc_name == nombre for c in casos):
        informe['avisos'].append(f'Hay un caso «{nombre}» que no creó el sistema: no se toca; renómbrelo en '
                                 'DIgSILENT para tener el de valle (073:RF-15).')
        return {**informe, 'caso': None, 'creado': False}
    previo = app.GetActiveStudyCase()
    origen = _escenario_de(app, sin)
    try:
        if caso is None:
            caso = carpeta.AddCopy(sin, nombre)
            _marcar(caso, clave)
        caso.Activate()
        actual = app.GetActiveScenario()
        if actual is None or actual.loc_name != nombre:
            if actual is not None:
                actual.Deactivate(0)
            escenarios = app.GetProjectFolder('scen', 1)
            propio = next((e for e in escenarios.GetContents('*.IntScenario') if e.loc_name == nombre), None)
            if propio is None:
                propio = (escenarios.AddCopy(origen, nombre) if origen is not None
                          else escenarios.CreateObject('IntScenario', nombre))
            propio.Activate()
            actual = propio
        informe['escenario'] = actual.loc_name
    finally:
        if previo is not None and app.GetActiveStudyCase() is not previo:
            previo.Activate()
    return informe


# =========================================================================== preparar
def _sin_verificar(plan: dict, feeders: list[str]) -> list[str]:
    """Alimentadores de ``feeders`` cuyo «Caso base» no está verificado (015:RF-17).

    El estado lo pone la web desde el vínculo del proyecto (``caso_base_sin_verificar``);
    un plan que no lo trae es de antes de la spec 015 y no se da por verificado.
    """
    if 'caso_base_sin_verificar' not in plan:
        return list(feeders) or ['(sin estado del «Caso base»)']
    fuera = plan.get('caso_base_sin_verificar') or {}
    return [f for f in feeders if f in fuera]


def caso(app, rol: str, anio: int | None = None):
    """El caso del sistema con ese rol (y año, 025:RF-14), o ``None``."""
    return casos_del_proyecto(app, anio).get(rol)


def _ajenos(app, anio: int | None = None) -> list[str]:
    carpeta = app.GetProjectFolder('study')
    casos = casos_del_proyecto(app, anio)
    nombres = {nombre_caso(rol, anio) for rol in NOMBRES}
    return [c.loc_name for c in carpeta.GetContents('*.IntCase')
            if c.loc_name in nombres and c not in casos.values()]


def _de_carga_nueva(app) -> list:
    carpeta = app.GetProjectFolder('scheme')
    return [v for v in (carpeta.GetContents('*.IntScheme', 1) if carpeta else [])
            if es_de_carga_nueva(v)]


#: 094:RF-15: la página con el perfil de tensión de cada alimentador, en cada caso.
PAGINA_PERFIL = 'Perfil de tensión'


def _uno(objetos, nombre: str):
    return next((o for o in objetos if o.loc_name == nombre), None)


def grafico_perfil(app, caso, feeders: list[str]) -> list[str]:
    """Deja en ``caso`` (activo) la página «Perfil de tensión» con un VisPath por alimentador (094:RF-15).

    Usuario, 2026-11-06: «en DIgSILENT existe una herramienta para graficar el perfil de tensión, ahí se podría ver o
    comprobar». Sonda en el proyecto de prueba PRUEBA_007 (094 T10): en modo motor no hay tablero
    (``GetGraphicsBoard`` da None) y ``GetOrInsertPlot`` no crea un VisPath; se crea con ``CreateObject`` en una
    ``SetVipage`` del ``SetDesktop`` del caso y se liga por su atributo ``feeder``; ``iopt_x`` 0 es la distancia.
    Repetir reutiliza la página y cada gráfico. Devuelve los gráficos que quedaron.
    """
    escritorio = _uno(caso.GetContents('*.SetDesktop'), 'Desktop') or next(iter(caso.GetContents('*.SetDesktop')), None)
    if escritorio is None:
        escritorio = caso.CreateObject('SetDesktop', 'Desktop')
    pagina = _uno(escritorio.GetContents('*.SetVipage'), PAGINA_PERFIL) or escritorio.CreateObject('SetVipage', PAGINA_PERFIL)
    elm = {f.loc_name: f for f in app.GetCalcRelevantObjects('*.ElmFeeder')}
    hechos = []
    for f in feeders:
        if f not in elm:
            continue
        nombre = f'Perfil {f}'
        grafico = _uno(pagina.GetContents('*.VisPath'), nombre) or pagina.CreateObject('VisPath', nombre)
        grafico.SetAttribute('feeder', [elm[f]])
        grafico.SetAttribute('iopt_x', 0)
        hechos.append(nombre)
    return hechos


def _con_grafico_perfil(app, caso, plan: dict, informe: dict, rol: str) -> None:
    """094:RF-15: el gráfico informa; si DIgSILENT no lo deja crear, se avisa y el caso sigue."""
    try:
        caso.Activate()
        informe['casos'][rol]['graficos_perfil'] = grafico_perfil(app, caso, list(plan.get('feeders') or []))
    except Exception as exc:  # noqa: BLE001 - el gráfico no decide el caso
        informe['avisos'].append(f'Sin el gráfico de perfil de tensión en «{caso.loc_name}»: {type(exc).__name__}: '
                                 f'{exc} (094:RF-15).')


def preparar_sin(app, plan: dict) -> tuple[dict, int]:
    """«Sin proyecto» como copia del «Caso base» verificado (015:RF-16 a RF-18, RF-27).

    Solo con el «Caso base» verificado. Si aún no hay casos, el activo pasa a ser el
    «Caso base»; «Sin proyecto» sale de él con una copia de su escenario de operación y
    sin activar ninguna variación: las modificaciones del operador se graban en la red
    (RF-27). Una vez creado, el «Caso base» no se vuelve a tocar (RF-19).

    Con ``anio_casos`` en el plan, «Sin proyecto <año>», también copia del «Caso base» y
    nunca del «Sin proyecto» de otro año (025:RF-15): los alimentadores sin medición de ese
    año quedan con la demanda del archivo y nada de la otra calibración pasa a este.
    """
    anio = anio_del_plan(plan)
    informe = {'project': plan.get('project'), 'avisos': [], 'casos': {}}
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r} en DIgSILENT"}, 2
    fuera = _sin_verificar(plan, list(plan.get('feeders') or []))
    if fuera:
        return {**informe, 'error': 'El «Caso base» de ' + ', '.join(fuera) + ' no está '
                                    f"verificado: verifíquelo (paso 1.1) antes de crear «{nombre_caso('sin', anio)}» "
                                    '(015:RF-17).'}, 2
    ajenos = _ajenos(app, anio)
    if ajenos:
        return {**informe, 'error': 'Hay en el proyecto un caso de estudio que no creó el sistema '
                                    'con el nombre ' + ', '.join(f'«{n}»' for n in ajenos)
                                    + ': renómbrelo en DIgSILENT y vuelva a preparar.'}, 2
    carpeta = app.GetProjectFolder('study')
    casos = casos_del_proyecto(app, anio)
    inicial = app.GetActiveStudyCase()
    try:
        caso_base = casos.get('base') or inicial
        creado_base = 'base' not in casos
        sin = casos.get('sin')
        if sin is None:
            if creado_base:
                caso_base.loc_name = NOMBRES['base']
                _marcar(caso_base, 'base')
            caso_base.Activate()
            # 014:RF-16: ninguna carga nueva en el base ni, por tanto, en su copia.
            for v in _de_carga_nueva(app):
                v.Deactivate()
            if app.GetActiveScenario() is None:
                _escenario_propio(app, caso_base, 'base', None)
            sin = carpeta.AddCopy(caso_base, nombre_caso('sin', anio))
            _marcar(sin, _clave('sin', anio))
        caso_base.Activate()
        activas_base = sorted(v.loc_name for v in (app.GetActiveNetworkVariations() or []))
        esc_base = app.GetActiveScenario()
        informe['casos']['base'] = {
            'nombre': caso_base.loc_name, 'creado': creado_base, 'variaciones': activas_base,
            'escenario': esc_base.loc_name if esc_base is not None else None}
        if activas_base:
            # 015:RF-31: se avisa y no se toca; son del operador.
            informe['avisos'].append('Variaciones activas en el «Caso base»: '
                                     + ', '.join(activas_base))
        informe['casos']['sin'] = {
            'nombre': sin.loc_name, 'creado': 'sin' not in casos,
            'escenario': _escenario_propio(app, sin, 'sin', esc_base, anio),
            'variaciones': sorted(v.loc_name for v in (app.GetActiveNetworkVariations() or [])),
            'estudiable': True}
        _con_grafico_perfil(app, sin, plan, informe, 'sin')                    # 094:RF-15
    finally:
        if inicial is not None:
            inicial.Activate()
    return informe, 0


def _renovar_con_proyecto(app, con, sin, anio: int | None):
    """«Con proyecto» de nuevo como copia de «Sin proyecto»; el anterior se conserva renombrado
    y sin la marca, con su escenario (037:RF-8).

    SM218 (2026-11-01): «Con proyecto» se copió el 29-10 y la recalibración de después, con
    los cambios del operador y los bancos EBC_1, EBC_2 y ECB_3, quedó solo en «Sin proyecto»;
    su escenario mandaba con demandas viejas (SE41225 a 600 kW) y sus SED salían al 826 %.
    """
    sello = datetime.now().strftime('%Y%m%d-%H%M%S')
    con.Activate()
    anterior = app.GetActiveScenario()
    if anterior is not None:
        anterior.loc_name = f'{anterior.loc_name} anterior {sello}'
    con.loc_name = f'{con.loc_name} anterior {sello}'
    con.desc = [x for x in _desc(con) if not x.startswith(MARCAS)] + [
        f'Reemplazado el {sello} por la recalibración de «Sin proyecto» (037:RF-8).']
    sin.Activate()
    return crear_con_proyecto(app, sin, anio)


def preparar_con(app, plan: dict) -> tuple[dict, int]:
    """«Con proyecto» como copia de «Sin proyecto», antes de insertar cargas (015:RF-28).

    Con su propio escenario, copia del de «Sin proyecto». Activa las cargas nuevas de los
    alimentadores marcados y lo que el operador tenga activo en «Sin proyecto»
    (014:RF-21); los ajustes puros de antes de la spec 015 se desactivan sin borrar.
    """
    informe, rc = preparar_sin(app, plan)
    if rc:
        return informe, rc
    anio = anio_del_plan(plan)                                          # 025:RF-16
    casos = casos_del_proyecto(app, anio)
    sin = casos['sin']
    carpeta_var = app.GetProjectFolder('scheme')
    todas = carpeta_var.GetContents('*.IntScheme', 1) if carpeta_var else []
    grupos = clasificar(todas, list(plan.get('feeders') or []), [], None)
    inicial = app.GetActiveStudyCase()
    try:
        con = casos.get('con')
        if con is None:
            con = crear_con_proyecto(app, sin, anio)
        escenario_con = _escenario_propio(app, con, 'con', _escenario_de(app, sin), anio)
        _dejar_activas(app, con, grupos['cargas'], grupos['anteriores'])
        sincronia = sin_a_con_proyecto(app, {**casos, 'con': con})     # 014:RF-31 a RF-34
        con.Activate()
        con_obras = any(v.loc_name.startswith(PREFIJO_VARIACION)
                        for v in (app.GetActiveNetworkVariations() or []))
        if sincronia['faltan'] and not con_obras:
            # 037:RF-8: sin obras no hay nada propio que perder; con obras, solo el aviso (RF-34).
            viejo, faltaban = con.loc_name, list(sincronia['faltan'])
            con = _renovar_con_proyecto(app, con, sin, anio)
            escenario_con = _escenario_de(app, con).loc_name
            _dejar_activas(app, con, grupos['cargas'], grupos['anteriores'])
            sincronia = sin_a_con_proyecto(app, {**casos, 'con': con})
            informe['avisos'].append(
                f'«{viejo}» no tenía obras y le faltaba lo de la recalibración de «Sin proyecto» '
                f'({", ".join(faltaban[:10])}): se renueva como copia de ella; el anterior queda '
                'renombrado, con su escenario (037:RF-8).')
        del_operador = sincronia['variaciones']
        informe['avisos'] += [a for a in sincronia['avisos'] if not a.startswith('Activadas')]
        con.Activate()
        activas = sorted(v.loc_name for v in (app.GetActiveNetworkVariations() or []))
        # Un informe de estudio no trae cliente nuevo: lo que distingue «Con proyecto» son
        # las obras de mejora (017:RF-30). Antes solo contaban las cargas nuevas, y en CA101
        # (2026-10-15) «Con proyecto» con obras se quedaba sin estudiar.
        obras = [v for v in activas if v.startswith(PREFIJO_VARIACION)]
        estudiable = bool(grupos['cargas'] or obras)
        informe['casos']['con'] = {
            'nombre': con.loc_name, 'creado': 'con' not in casos, 'escenario': escenario_con,
            'variaciones': activas,
            'variaciones_operador_activadas': del_operador, 'estudiable': estudiable}
        _con_grafico_perfil(app, con, plan, informe, 'con')                    # 094:RF-15
        if not estudiable:
            informe['avisos'].append('Ningún alimentador marcado tiene cargas nuevas ni obras: '
                                     '«Con proyecto» queda igual que «Sin proyecto» y no se estudia.')
        if grupos['anteriores']:
            informe['avisos'].append(
                'Ajustes de antes de la spec 015 desactivados en «Con proyecto» (siguen en el '
                'proyecto): ' + ', '.join(v.loc_name for v in grupos['anteriores']))
        if del_operador:
            informe['avisos'].append('Activadas en «Con proyecto» porque están activas en «Sin '
                                     'proyecto»: ' + ', '.join(del_operador))
    finally:
        if inicial is not None:
            inicial.Activate()
    return informe, 0


def preparar(app, plan: dict) -> tuple[dict, int]:
    """Los tres casos para los estudios (spec 011 con la 015). Devuelve (informe, código).

    Los alimentadores sin calibrar quedan fuera con su motivo; el que no cuadró, con
    aviso (011:RF-14, RF-15). La calibración ya no es una variación: está en el
    escenario de «Sin proyecto» (015:RF-26).
    """
    base = plan.get('base') or {}
    marcados = list(plan.get('feeders') or [])
    ajustados = {a['feeder']: a for a in base.get('ajustes') or []}
    excluidos = list(base.get('excluidos') or [])
    ya_fuera = {x['feeder'] for x in excluidos}
    for f in marcados:
        if f not in ajustados and f not in ya_fuera:
            excluidos.append({'feeder': f, 'motivo': 'no está calibrado'})
    feeders = [f for f in marcados if f in ajustados]
    if not feeders:
        return {'project': plan.get('project'), 'avisos': [], 'excluidos': excluidos, 'casos': {},
                'error': 'Ningún alimentador marcado está calibrado: primero hay que calibrar '
                         '(paso 2).'}, 2
    informe, rc = preparar_con(app, {**plan, 'feeders': feeders})
    if not rc and plan.get('incluir_cargas_nuevas'):
        # 037:RF-2: renovar desde la calibración actual, sin las obras exclusivas de Con.
        # Los callbacks de inserción conservan el diagnóstico eléctrico de 025:RF-66.
        from cargas_pf import (Alimentadores, estado_del_alimentador, flujo_con_mensajes,
                               motivo_de_carga)

        anio = anio_del_plan(plan)
        casos = casos_del_proyecto(app, anio)
        carpeta = app.GetProjectFolder('scheme')
        grupos = clasificar(carpeta.GetContents('*.IntScheme', 1) if carpeta else [],
                            feeders, [], None)
        if grupos['cargas']:
            alims = Alimentadores(app, activar_proyecto(app, plan['project'], plan.get('folder')),
                                  feeders)
            filas = {f.get('variacion'): f for f in plan.get('nuevas') or []}

            def antes(_app, v):
                feeder = filas.get(v.loc_name, {}).get('alimentador')
                return estado_del_alimentador(alims, feeder) if feeder in alims.elm else {}

            def explicar(v, previo, mensajes):
                fila = filas.get(v.loc_name, {})
                return motivo_de_carga(fila.get('sed') or v.loc_name,
                                       fila.get('alimentador'), fila.get('kw'), previo, mensajes)

            diagnostico = cargas_nuevas(app, casos['sin'], anio,
                                        sorted(grupos['cargas'], key=lambda v: v.loc_name),
                                        flujo_con_mensajes, antes=antes, explicar=explicar,
                                        feeders=feeders, con=casos.get('con'))       # 025:RF-79 a RF-83
            informe['cargas_nuevas'] = diagnostico
            informe['avisos'] += diagnostico['avisos']
            informe['casos']['cargas'] = {
                'nombre': diagnostico['caso'], 'escenario': diagnostico.get('escenario'),
                'converge': diagnostico.get('converge'),
                'estudiable': diagnostico.get('converge') is not None}
    informe['excluidos'] = excluidos
    informe['feeders'] = feeders
    for f in feeders:
        a = ajustados[f]
        if not a.get('cuadrado'):
            d = a.get('desvio') or {}
            informe['avisos'].append(
                f"{f}: su ajuste no cuadró (error en la cabecera {_pct(d.get('kw'))} en kW, "
                f"{_pct(d.get('kvar'))} en kVAR); se estudia igual.")
    return informe, rc


def _escenario_de(app, caso):
    previo = app.GetActiveStudyCase()
    caso.Activate()
    esc = app.GetActiveScenario()
    if previo is not None:
        previo.Activate()
    return esc


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Los tres casos de estudio de la spec 011 en DIgSILENT')
    p.add_argument('--plan', required=True, help='Plan JSON preparado por la web')
    p.add_argument('--output-json', required=True, help='Dónde dejar el informe')
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    blocked = native_action_block_report(plan, 'estudios')
    if blocked:
        Path(args.output_json).write_text(
            json.dumps(blocked, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(blocked['error'])
        return 2
    # 019:RF-1 a RF-6: turno del motor de la máquina, reintento con el motor ocupado y
    # primera línea al responder, comunes a todos los guiones.
    from convertersmartgrid.pf_arnes import PFNoDisponible, conectar

    try:
        app = conectar('casos_pf.py')
    except PFNoDisponible as exc:
        print(f'ERROR: {exc}')
        return 3
    try:
        informe, codigo = preparar(app, plan)
    except Exception as exc:  # noqa: BLE001 - el informe dice el error en vez de perderse
        traceback.print_exc()
        informe, codigo = error_inesperado(plan, False, exc), 1
    Path(args.output_json).write_text(
        json.dumps(informe, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
    print(f'Informe: {args.output_json}')
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
