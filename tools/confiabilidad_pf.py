#!/usr/bin/env python
"""Confiabilidad y ubicación de reconectadores de la spec 012 en DIgSILENT.

Dos usos:

``--aplicar-datos``: escribe el libro de la empresa en el proyecto (RF-20 a RF-27, RF-69,
RF-70). Crea un modelo ``Sto*`` por clase y por tipo con fila propia, en una carpeta de la
biblioteca del proyecto, y en la variación «Datos de confiabilidad», activa en «Sin
proyecto» y «Con proyecto» y nunca en el «Caso base», asigna los modelos a los elementos
(``pStoch``), configura los equipos de maniobra y, si la cabecera no tiene un interruptor
con protección, crea uno. Ningún tipo existente se toca (RF-22): un tipo no lo graba ninguna
variación y llegaría también al «Caso base».

``fiabilidad`` y ``reconectadores`` son claves del ``ejecutar`` de ``tools/estudios_pf.py``
(RF-2): ese guion activa el caso, comprueba el flujo y llama aquí.

Lo que dio DIgSILENT en la prueba del 2026-10-12 (plan de la spec 012) y se sigue aquí:

- Sin interruptor de cabecera, ``ComRel3`` descarta todas las fallas de línea («No
  protection devices to clear the faults»): el DGS une la red externa al primer tramo.
- Los índices por alimentador están en ``ElmFeeder`` (``c:SAIFI``…); el aporte de cada
  elemento, en ``c:C_ENS`` de líneas y transformadores tras ``ComRel3``.
- ``ComOpri`` con ``recResults=2`` graba su propuesta en una variación y cambia la hora del
  caso: la variación se borra y la hora se restituye (RF-38, RF-60).

Las tasas de interruptores, reconectadores, fusibles y seccionadores se leen del libro
(RF-10) pero no tienen dónde asignarse: ni ``StaSwitch`` ni ``ElmCoup`` tienen ``pStoch`` en
``datascheme.db`` de PF 2024. Su clase decide qué despeja y qué solo aísla (RF-27). El tiempo
de localización va en ``ElmTerm.AccessTime`` («First manual switch action after the fault»)
y la maniobra manual en ``ElmTerm.LocAccTime`` y en el ``Tswitch`` de cada equipo
(``localisation/en-GB/data.db`` de PF 2024).

Los enteros de las opciones de ``ComRel3`` no están en ningún fichero local: se usa el orden
del diálogo (la primera, 0), como con ``ComHostcap`` en el plan, y la prueba real (T13) lo
confirma. Todos están en ``OPCIONES_REL3``.

    python tools/confiabilidad_pf.py --aplicar-datos --plan plan.json --output-json informe.json

Códigos de salida: 0 hecho, 2 no se pudo (el informe dice por qué), 3 sin API.
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

from cargas_pf import _num, activar_proyecto, crear_variacion, error_inesperado, nombre_libre
from casos_pf import NOMBRES, casos_del_proyecto

from convertersmartgrid import datos_empresa as de
from convertersmartgrid import estudios_red_pf as er
from convertersmartgrid.native_action import native_action_block_report

#: Variación propia de la spec 012 (RF-21).
VARIACION = er.VARIACION_DATOS
#: Carpeta de la biblioteca del proyecto con los modelos ``Sto*`` y su prefijo (RF-23).
CARPETA_MODELOS = 'CSG_confiabilidad'
PREFIJO_MODELO = 'CSG012_'
#: Interruptor de cabecera que crea RF-69.
NOMBRE_CABECERA = 'CSG012_cabecera'
#: Nombres anteriores a la spec 058, solo para reconocer lo que ya está en los proyectos de
#: DIgSILENT (no se renombran, 058:RF-9): sin esto, sus modelos y su cabecera se tomarían
#: por ajenos.
PREFIJO_ANTERIOR = 'IGEA012_'  # legado-058
PREFIJOS_MODELO = (PREFIJO_MODELO, PREFIJO_ANTERIOR)
NOMBRES_CABECERA = (NOMBRE_CABECERA, PREFIJO_ANTERIOR + 'cabecera')
#: Clase de modelo de falla por clase de elemento.
MODELO = {'linea': 'StoTyplne', 'cable': 'StoTyplne', 'transformador': 'StoTyptrf', 'barra': 'StoTypbar'}
#: Clases con modelo de falla asignable; las demás solo deciden el despeje (RF-27).
CON_MODELO = tuple(MODELO)
#: Clase del equipo en el export (tablas del catálogo de equipos) → clase del libro.
CLASE_EXPORT = {'BREAKER': 'interruptor', 'RECLOSER': 'reconectador', 'FUSE': 'fusible',
                'SWITCH': 'seccionador', 'SECTIONALIZER': 'seccionador'}
#: ``aUsage`` del DGS que ya dice la clase (011:RF-128): seccionador y seccionalizador.
CLASE_POR_USO = {'dct': 'seccionador', 'swt': 'seccionador'}
INTERRUPTORES = ('StaSwitch', 'ElmCoup')
#: ``ComRel3``: análisis por flujo de carga y red de distribución (RF-28), orden del diálogo.
OPCIONES_REL3 = {'iopt_type': 1, 'iopt_net': 1}
#: ``ComOpri.objective`` (plan: 0 ENS, 1 SAIDI); ``locations`` 1 = con protección.
OBJETIVO_OPRI = {'ens': 0, 'saidi': 1}
NOMBRE_REL3 = 'Confiabilidad_convertersmartgrid'
NOMBRE_OPRI = 'Reconectadores_convertersmartgrid'


# =========================================================================== clases
def _es_interno_de_sed(sw) -> bool:
    """El acoplador interno de una SED que crea el conversor (``SW_<sed>`` dentro de su
    ``ElmSubstat``): protege el transformador y nunca es candidato a reconectador (RF-35)."""
    padre = sw.GetParent()
    return padre is not None and padre.GetClassName() == 'ElmSubstat'


def clase_de_equipo(sw, clases_entrada: dict[str, str]) -> str | None:
    """Clase del libro de un equipo de maniobra, o ``None`` si el proyecto no la dice (RF-26).

    La entrada cargada manda (el DGS escribe interruptores, reconectadores y fusibles como
    ``cbk``); sin ella, solo seccionadores y seccionalizadores se reconocen por su ``aUsage``.
    """
    if sw.loc_name.startswith(NOMBRES_CABECERA) or _es_interno_de_sed(sw):
        return 'interruptor'
    if sw.loc_name in clases_entrada:
        return CLASE_EXPORT.get(str(clases_entrada[sw.loc_name]).upper())
    return CLASE_POR_USO.get(str(getattr(sw, 'aUsage', '') or ''))


def interruptores_de(elm) -> list:
    out = []
    for clase in INTERRUPTORES:
        out += elm.GetObjs(clase)
    return out


def clase_de_linea(ln) -> str:
    """Línea aérea o cable por su tipo (``TypLne.cohl_``: 1 aérea, 0 cable)."""
    tipo = getattr(ln, 'typ_id', None)
    return 'cable' if tipo is not None and getattr(tipo, 'cohl_', 1) == 0 else 'linea'


def elementos_por_clase(elm) -> dict[str, list]:
    """Elementos de un alimentador con modelo de falla, por clase del libro."""
    out: dict[str, list] = {c: [] for c in CON_MODELO}
    for ln in elm.GetObjs('ElmLne'):
        out[clase_de_linea(ln)].append(ln)
    out['transformador'] = list(elm.GetObjs('ElmTr2'))
    out['barra'] = list(elm.GetObjs('ElmTerm'))
    return out


def _tipo_de(obj) -> str:
    tipo = getattr(obj, 'typ_id', None)
    return getattr(tipo, 'loc_name', '') if tipo is not None else ''


# =========================================================================== aplicar datos
def _carpeta_modelos(app):
    equip = app.GetProjectFolder('equip')
    carpeta = next((c for c in equip.GetContents('*.IntFolder') if c.loc_name == CARPETA_MODELOS), None)
    return carpeta or equip.CreateObject('IntFolder', CARPETA_MODELOS)


def escribir_modelos(app, libro: de.Libro) -> dict[str, object]:
    """Un ``Sto*`` por clase y por tipo con fila (RF-11); los de un libro anterior que ya no
    tienen fila se borran y los que siguen se reescriben, sin acumularse (RF-23)."""
    carpeta = _carpeta_modelos(app)
    queridos: dict[str, tuple[str, de.Tasa]] = {}
    for clase, tasa in libro.tasas.items():
        if clase in MODELO:
            queridos[f'{PREFIJO_MODELO}{clase}'] = (MODELO[clase], tasa)
    for tipo, tasa in libro.tasas_por_tipo.items():
        queridos[f'{PREFIJO_MODELO}tipo_{tipo}'] = (MODELO[tasa.clase], tasa)
    existentes = {o.loc_name: o for o in carpeta.GetContents('*')
                  if o.loc_name.startswith(PREFIJOS_MODELO)}
    for nombre, o in existentes.items():
        if nombre not in queridos or o.GetClassName() != queridos[nombre][0]:
            o.Delete()
    modelos = {}
    for nombre, (clase_pf, tasa) in sorted(queridos.items()):
        o = existentes.get(nombre)
        if o is None or o.GetClassName() != clase_pf:
            o = carpeta.CreateObject(clase_pf, nombre)
        # Por km y año en líneas y cables, tal cual: el manual (§45.3.1.2) da la del
        # elemento como la del tipo y DIgSILENT la multiplica por la longitud (plan, T1).
        if clase_pf == 'StoTypbar':
            o.DnFr1 = tasa.permanente
        else:
            o.DnFr = tasa.permanente
        o.RepMu = tasa.reparacion_h
        if clase_pf == 'StoTyplne' and tasa.transitoria is not None:
            o.trans_ff = tasa.transitoria
        modelos[nombre] = o
    return modelos


def _modelo_de(modelos, libro: de.Libro, clase: str, obj):
    tipo = _tipo_de(obj) if clase in de.POR_KM else ''
    if tipo and tipo in libro.tasas_por_tipo:
        return modelos.get(f'{PREFIJO_MODELO}tipo_{tipo}')
    return modelos.get(f'{PREFIJO_MODELO}{clase}')


def _variacion_existente(app):
    carpeta = app.GetProjectFolder('scheme')
    return next((v for v in carpeta.GetContents('*.IntScheme', 1) if v.loc_name == VARIACION), None)


def _cabecera_protegida(elm) -> bool:
    """¿Hay en el cubículo de la cabecera un interruptor automático con protección? (RF-69)"""
    cub = getattr(elm, 'obj_id', None)
    if cub is None:
        return False
    return any(getattr(sw, 'aUsage', 'cbk') == 'cbk' and getattr(sw, 'rel_hasProt', 0)
               for sw in cub.GetContents('*.StaSwitch'))


def _bloqueos(libro, elms, feeders, clases_entrada) -> tuple[list[str], dict[str, list[str]]]:
    """Clases de la red que el libro no trae (RF-17) y equipos sin clase (RF-26)."""
    conteo: dict[str, int] = {}
    sin_clase: dict[str, list[str]] = {}
    for f in feeders:
        for clase, objs in elementos_por_clase(elms[f]).items():
            conteo[clase] = conteo.get(clase, 0) + sum(
                1 for o in objs if not (clase in de.POR_KM and _tipo_de(o) in libro.tasas_por_tipo))
        for sw in interruptores_de(elms[f]):
            if clase_de_equipo(sw, clases_entrada) is None:
                sin_clase.setdefault(f, []).append(sw.loc_name)
    return de.clases_que_faltan(libro, conteo), sin_clase


def _escribir_alimentador(elm, libro, modelos, clases_entrada) -> dict:
    """Modelos, tiempos y equipos de un alimentador, en la etapa que graba (RF-22, RF-27, RF-69)."""
    t, tele = libro.tiempos_min, set(libro.telemandados)
    fila = {'asignados': {}, 'interruptor_cabecera': False}
    for clase, objs in elementos_por_clase(elm).items():
        n = 0
        for o in objs:
            m = _modelo_de(modelos, libro, clase, o)
            if m is not None:
                o.pStoch = m
                n += 1
            if clase == 'barra':                                             # RF-12
                o.AccessTime = t.get('localizacion', 0.0)
                o.LocAccTime = t.get('manual', 0.0)
        fila['asignados'][clase] = n
    for sw in interruptores_de(elm):                                         # RF-27, RF-13
        clase = clase_de_equipo(sw, clases_entrada)
        sw.rel_hasProt = 1 if clase in de.DESPEJAN else 0
        sw.rel_hasRecl = 1 if clase == 'reconectador' else 0
        if clase == 'seccionador':
            sw.iRestore = 1
        sw.Tswitch = t.get('telemandada', 0.0) if sw.loc_name in tele else t.get('manual', 0.0)
    cub = getattr(elm, 'obj_id', None)
    if cub is not None and not _cabecera_protegida(elm):                     # RF-69
        cab = cub.CreateObject('StaSwitch', nombre_libre(cub, 'StaSwitch', NOMBRE_CABECERA))
        cab.aUsage, cab.on_off, cab.rel_hasProt, cab.rel_hasRecl = 'cbk', 1, 1, 0
        cab.Tswitch = t.get('manual', 0.0)
        fila['interruptor_cabecera'] = True
    cargas = elm.GetObjs('ElmLod')                                           # RF-24, RF-25
    fila['cargas_sin_clientes'] = sum(1 for c in cargas if not (getattr(c, 'NrCust', 0) or 0))
    fila['un_cliente'] = bool(cargas) and all(int(getattr(c, 'NrCust', 0) or 0) == 1 for c in cargas)
    return fila


def aplicar_datos(app, plan: dict) -> tuple[dict, int]:
    """El libro en el proyecto (RF-20 a RF-27, RF-69); bloquea sin escribir nada si falta una
    clase de la red (RF-17) o el proyecto no distingue la clase de sus equipos (RF-26)."""
    informe: dict = {'project': plan.get('project'), 'modo': 'aplicar_datos', 'avisos': [],
                     'libro': (plan.get('libro') or {}).get('nombre'), 'alimentadores': {}}
    libro = de.Libro.desde_dict(plan.get('libro') or {})
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r} en DIgSILENT"}, 2
    casos = casos_del_proyecto(app)
    if 'sin' not in casos:
        return {**informe, 'error': f"el proyecto no tiene «{NOMBRES['sin']}»: prepare los casos primero"}, 2
    feeders = list(plan.get('feeders') or [])
    clases_entrada = dict(plan.get('clases_equipo') or {})
    inicial = app.GetActiveStudyCase()
    try:
        casos['sin'].Activate()
        anterior = _variacion_existente(app)
        if anterior is not None:            # RF-23: se lee la red sin la que se va a reemplazar
            anterior.Deactivate()
        elms = {f.loc_name: f for f in proyecto.GetContents('*.ElmFeeder', 1)}
        faltan = [f for f in feeders if f not in elms]
        if faltan:
            return {**informe, 'error': 'no están en el proyecto: ' + ', '.join(faltan)}, 2
        faltan_clases, sin_clase = _bloqueos(libro, elms, feeders, clases_entrada)
        if faltan_clases or sin_clase:
            if anterior is not None:
                anterior.Activate()
            if faltan_clases:                                                # RF-17
                return {**informe, 'error': 'el libro no trae estas clases que tiene la red: '
                                            + '; '.join(faltan_clases)}, 2
            return {**informe, 'sin_clase': sin_clase,                       # RF-26
                    'error': 'el proyecto no distingue la clase de estos equipos de maniobra ('
                             + '; '.join(f'{f}: {len(v)}' for f, v in sorted(sin_clase.items()))
                             + '): vuelva a convertir el alimentador o cargue su entrada'}, 2
        if anterior is not None:
            # Fuera de todos los casos antes de borrarla: activa en «Con proyecto», DIgSILENT
            # seguiría apuntando a ella desde ese caso.
            for caso in casos.values():
                caso.Activate()
                anterior.Deactivate()
            casos['sin'].Activate()
            anterior.Delete()
        modelos = escribir_modelos(app, libro)
        variacion, _etapa = crear_variacion(app, VARIACION, 'confiabilidad')
        for f in feeders:
            fila = informe['alimentadores'][f] = _escribir_alimentador(elms[f], libro, modelos, clases_entrada)
            if fila['un_cliente']:                                           # RF-70
                informe['avisos'].append(f'{f}: todas sus cargas tienen un solo cliente; SAIFI y SAIDI '
                                         'quedarán ponderados por carga, no por cliente.')
            if fila['cargas_sin_clientes']:                                  # RF-25
                informe['avisos'].append(f"{f}: {fila['cargas_sin_clientes']} cargas sin número de "
                                         'clientes; no pesan en SAIFI ni en SAIDI.')
        sin_sitio = [de.CLASES[c] for c in de.CLASES if c in libro.tasas and c not in MODELO]
        if sin_sitio:
            informe['avisos'].append('Las tasas de ' + ', '.join(sin_sitio) + ' no tienen dónde ir en '
                                     'DIgSILENT (StaSwitch y ElmCoup no tienen modelo de falla): su '
                                     'clase decide qué despeja la falla y qué solo aísla.')
        # RF-21: activa en «Sin proyecto» y «Con proyecto»; nunca en el «Caso base».
        for rol, caso in casos.items():
            caso.Activate()
            if rol in ('sin', 'con'):
                variacion.Activate()
            else:
                variacion.Deactivate()
        informe.update(variacion=variacion.loc_name, modelos=sorted(modelos),
                       casos=[NOMBRES[r] for r in ('sin', 'con') if r in casos])
    finally:
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()
    return informe, 0


# =========================================================================== estudios
def con_datos(app) -> bool:
    """¿Está activa en el caso la variación «Datos de confiabilidad»?"""
    return any(v.loc_name == VARIACION for v in app.GetActiveNetworkVariations() or [])


def sin_tension(elm) -> bool:
    """Un alimentador sin tensión antes de la falla da índices cero (RF-71): se mira en el flujo."""
    return not any((_num(b, 'm:u') or 0) > 0 for b in elm.GetObjs('ElmTerm'))


def _tasas_cero(elm) -> bool:
    for objs in elementos_por_clase(elm).values():
        for o in objs:
            m = getattr(o, 'pStoch', None)
            if m is not None and ((_num(m, 'DnFr') or 0) > 0 or (_num(m, 'DnFr1') or 0) > 0):
                return False
    return True


def leer_confiabilidad(elm) -> dict:
    """Lo que dejó ``ComRel3`` en un alimentador: índices, cargas y aportes (RF-30, RF-32)."""
    cargas = [{'nombre': c.loc_name, 'nrcust': _num(c, 'NrCust'), 'tcif': _num(c, 'c:TCIF'),
               'tcit': _num(c, 'c:TCIT'), 'lpens': _num(c, 'c:LPENS')} for c in elm.GetObjs('ElmLod')]
    aportes = [{'elemento': o.loc_name, 'clase': o.GetClassName(), 'ens_mwh': _num(o, 'c:C_ENS'),
                'pct': _num(o, 'c:CpENS')}
               for clase in ('ElmLne', 'ElmTr2') for o in elm.GetObjs(clase)]
    return {'indices': {k: _num(elm, f'c:{k}') for k in ('SAIFI', 'SAIDI', 'CAIDI', 'ENS', 'MAIFI')},
            'cargas': cargas, 'aportes': aportes}


def orden_propia(app, clase: str, nombre: str):
    """Orden creada en el caso, para no tocar las que el operador tenga configuradas."""
    orden = app.GetActiveStudyCase().CreateObject(clase, nombre)
    if orden is None:
        raise RuntimeError(f'no se pudo crear la orden {clase} en el caso')
    return orden


def sin_licencia(salida: list[str]) -> bool:
    """¿Rechazó DIgSILENT la orden por licencia? (RF-4)"""
    return any('licen' in linea.lower() for linea in salida)


def fiabilidad(app, plan: dict, alims, feeders: list[str], informe: dict) -> str | None:
    """RF-28 a RF-33, RF-71: ``ComRel3`` propio en el caso y lectura por alimentador."""
    from estudios_pf import _limpiar_salida, _salida

    if not con_datos(app):
        return f'«{VARIACION}» no está activa en el caso: aplique primero el libro de la empresa'
    previos = {f: sin_tension(alims.elm[f]) for f in feeders if f in alims.elm}
    orden = orden_propia(app, 'ComRel3', NOMBRE_REL3)
    try:
        for k, v in OPCIONES_REL3.items():
            setattr(orden, k, v)
        _limpiar_salida(app)
        rc = informe['codigo_orden'] = orden.Execute()
        if rc and sin_licencia(_salida(app)):
            informe['sin_licencia'] = 'ComRel3'
            return 'la licencia de DIgSILENT no incluye el módulo ComRel3'
        informe['red'] = {}
        for f in feeders:
            elm = alims.elm.get(f)
            if elm is None:
                continue
            leido = {**leer_confiabilidad(elm), 'sin_tension': previos[f], 'tasas_cero': _tasas_cero(elm)}
            informe['red'][f] = er.confiabilidad(f, leido)
            informe['avisos'] += informe['red'][f]['avisos']
    finally:
        orden.Delete()
    return None


def candidatos(elm, clases_entrada: dict[str, str]) -> tuple[list, list]:
    """Candidatos a reconectador (RF-35) y los demás interruptores, que se excluyen."""
    si, no = [], []
    for sw in interruptores_de(elm):
        clase = clase_de_equipo(sw, clases_entrada)
        candidato = (clase in ('interruptor', 'reconectador') and not _es_interno_de_sed(sw)
                     and not sw.loc_name.startswith(NOMBRES_CABECERA))
        (si if candidato else no).append(sw)
    return si, no


def _tramo_de(sw) -> str | None:
    """La línea en cuyo cubículo está el equipo: la obra «Reconectador» va en un tramo (RF-40)."""
    cub = sw.GetParent() if sw.GetClassName() == 'StaSwitch' else None
    rama = getattr(cub, 'obj_id', None) if cub is not None else None
    return rama.loc_name if rama is not None and rama.GetClassName() == 'ElmLne' else None


def reconectadores(app, plan: dict, alims, feeders: list[str], informe: dict) -> str | None:
    """RF-34 a RF-39: ``ComOpri`` con los candidatos filtrados; lo que propone queda en una
    variación temporal que se lee y se borra (RF-38)."""
    from estudios_pf import _limpiar_salida, _salida

    if not con_datos(app):
        return f'«{VARIACION}» no está activa en el caso: aplique primero el libro de la empresa'
    opciones = plan.get('opciones') or {}
    clases_entrada = dict(plan.get('clases_equipo') or {})
    cand, excluidos, por_alim, alim_de = [], [], {}, {}
    for f in feeders:
        elm = alims.elm.get(f)
        if elm is None:
            continue
        si, no = candidatos(elm, clases_entrada)
        cand += si
        excluidos += no
        por_alim[f] = len(si)
        alim_de.update({sw.loc_name: f for sw in si})
    informe['candidatos'] = por_alim
    if not cand:
        informe['propuesta'] = er.reconectadores([], por_alim, por_alim)
        informe['avisos'] += informe['propuesta']['avisos']
        return None
    caso = app.GetActiveStudyCase()
    # ComOpri cambia la hora del caso y deja su variación grabando (prueba en DIgSILENT del
    # 2026-10-12): se guardan aquí y se devuelven al terminar.
    hora, etapa = getattr(caso, 'iStudyTime', None), app.GetRecordingStage()
    antes = {sw.loc_name: getattr(sw, 'rel_hasRecl', 0) for sw in cand}
    carpeta = app.GetProjectFolder('scheme')
    previas = {v.loc_name for v in carpeta.GetContents('*.IntScheme', 1)}
    seleccion = caso.CreateObject('SetSelect', nombre_libre(caso, 'SetSelect', 'Excluidos_convertersmartgrid'))
    seleccion.AddRef(excluidos)
    orden = orden_propia(app, 'ComOpri', NOMBRE_OPRI)
    nombre_var = nombre_libre(carpeta, 'IntScheme', 'Reconectadores_temporal')
    try:
        orden.objective = OBJETIVO_OPRI.get(str(opciones.get('objetivo') or 'ens'), 0)    # RF-37
        orden.locations, orden.exclCableProt = 1, 1                                     # RF-35, RF-36
        orden.excludedSwts = seleccion
        orden.nrOfRecl = int(opciones.get('max_total') or 3)
        orden.maxNrPerFeeder = int(opciones.get('max_por_alimentador') or 1)
        orden.recResults, orden.variationName = 2, nombre_var                           # RF-38
        _limpiar_salida(app)
        rc = informe['codigo_orden'] = orden.Execute()
        salida = _salida(app)
        if rc and sin_licencia(salida):
            informe['sin_licencia'] = 'ComOpri'
            return 'la licencia de DIgSILENT no incluye el módulo ComOpri'
        # ComOpri da la mejora del conjunto propuesto, no la de cada reconectador.
        informe['mejora'] = er.mejora_de_salida(salida)
        propuestos = [{'alimentador': alim_de[sw.loc_name], 'elemento': sw.loc_name,
                       'clase': clase_de_equipo(sw, clases_entrada), 'tramo': _tramo_de(sw)}
                      for sw in cand if getattr(sw, 'rel_hasRecl', 0) and not antes[sw.loc_name]]
        informe['propuesta'] = er.reconectadores(propuestos, por_alim, por_alim)
        informe['avisos'] += informe['propuesta']['avisos']
    finally:
        for v in carpeta.GetContents('*.IntScheme', 1):
            if v.loc_name not in previas:
                v.Deactivate()
                v.Delete()
        for sw in cand:                      # lo que ComOpri hubiera grabado fuera de su variación
            if getattr(sw, 'rel_hasRecl', 0) != antes[sw.loc_name]:
                sw.rel_hasRecl = antes[sw.loc_name]
        orden.Delete()
        seleccion.Delete()
        if hora is not None and getattr(caso, 'iStudyTime', None) != hora:
            caso.iStudyTime = hora
        if etapa is not None and app.GetRecordingStage() is not etapa:
            etapa.Activate(1)
    return None


# =========================================================================== main
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Datos de confiabilidad de la spec 012 en DIgSILENT')
    p.add_argument('--plan', required=True, help='Plan JSON preparado por la web')
    p.add_argument('--output-json', required=True, help='Dónde dejar el informe')
    p.add_argument('--aplicar-datos', action='store_true',
                   help='Escribir el libro de la empresa en la variación «Datos de confiabilidad»')
    args = p.parse_args(argv)
    if not args.aplicar_datos:
        p.error('use --aplicar-datos; los estudios los ejecuta tools/estudios_pf.py')
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    blocked = native_action_block_report(plan, ('confiabilidad', 'estudios'))
    if blocked:
        Path(args.output_json).write_text(json.dumps(blocked, indent=2, ensure_ascii=False) + '\n',
                                          encoding='utf-8')
        print(blocked['error'])
        return 2
    from convertersmartgrid.pf_arnes import PFNoDisponible, conectar

    try:
        app = conectar('confiabilidad_pf.py')
    except PFNoDisponible as exc:
        print(f'ERROR: {exc}')
        return 3
    try:
        informe, codigo = aplicar_datos(app, plan)
    except Exception as exc:  # noqa: BLE001 - el informe dice el error en vez de perderse
        traceback.print_exc()
        informe, codigo = error_inesperado(plan, False, exc), 1
    Path(args.output_json).write_text(
        json.dumps(informe, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
    print(informe.get('error') or f"Datos de confiabilidad aplicados en {informe.get('variacion')}")
    print(f'Informe: {args.output_json}')
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
