#!/usr/bin/env python
"""Verifica en DIgSILENT cada año del horizonte del PIDE (spec 024, T13, RF-51 a RF-53).

Para cada año pedido escala la demanda con el factor de escala de cargas del ``ComLdf``
((1 + tasa)^año), ejecuta el flujo en el caso pedido y diagnostica con la norma del perfil
(``convertersmartgrid.pide``). Al terminar devuelve el factor a su valor. Con
``casos_por_anio`` conserva casos/escenarios propios; ``modo=anual`` continúa las
copias del corto plazo, con una proyección anual aceptada y obras físicas declaradas.
Nunca cambia los casos originales ni sustituye un perfil anual ausente por la tasa.

    python tools/pide_pf.py --plan plan.json --output-json informe.json

El plan: ``{"project", "folder", "feeders", "case", "tasa", "anios": [0, 4, 8, ...],
"limites": {...}, "native_action_context"}``.
El modo anual recibe además ``estudio_id``, ``corto_plazo``, ``anio_fin`` y
``proyeccion_anual`` (ruta/SHA del perfil con su evaluación). La spec 072 y
``leer_proyeccion_anual`` documentan el contrato; 089 a 28 días no lo satisface.

Códigos de salida: 0 leído (con o sin problemas), 2 sin proyecto, sin caso o sin tasa,
1 error inesperado, 3 sin API.
"""
from __future__ import annotations

import argparse
import json
import traceback
import math
import re
from pathlib import Path

from cargas_pf import Alimentadores, activar_proyecto, clave_pf, flujo_de_carga, escribir_carga, error_relectura, crear_variacion, foto_carga
from casos_pf import (
    _escenario_de,
    _marcar,
    anio_del_plan,
    es_de_carga_nueva,
    nombre_cargas_nuevas,
    objetos_de_variacion,
)
from casos_pf import caso as caso_del_sistema
from digital_twin_snapshot_pf import CASOS, _caso, resultados
from estudios_pf import _num

from convertersmartgrid.digital_twin.native_snapshot import identidad_nativa
from convertersmartgrid.native_action import native_action_block_report
from convertersmartgrid.pide import PideError, diagnosticar, leer_json_con_huella, leer_proyeccion_anual
from convertersmartgrid.comprobacion_flujo import comprobar_tras_flujo, texto_tras_flujo, UMBRAL_PU, UMBRAL_MW


#: Los casos de cada año del PIDE, con su papel y su nombre (030:RF-1).
CASOS_DEL_ANIO = (('sin', 'Sin proyecto'), ('cargas', 'Cargas nuevas'), ('con', 'Con proyecto'))


def _carpeta(padre, nombre: str):
    """La subcarpeta ``nombre`` de ``padre``, creada si falta."""
    return next((x for x in padre.GetContents('*.IntFolder') if x.loc_name == nombre), None) \
        or padre.CreateObject('IntFolder', nombre)


def origenes_del_pide(app, plan: dict) -> dict:
    """Los casos del proyecto que se copian a cada año: «Sin proyecto», «Cargas nuevas» y «Con
    proyecto», los del año de medición si los hay (030:RF-1)."""
    anio = anio_del_plan(plan)
    out = {}
    sin = caso_del_sistema(app, 'sin', anio) or _caso(app, 'Sin proyecto')
    if sin is not None:
        out['sin'] = sin
    cargas = _caso(app, nombre_cargas_nuevas(anio))
    if cargas is not None:
        out['cargas'] = cargas
    con = caso_del_sistema(app, 'con', anio)
    if con is not None:
        out['con'] = con
    return out


def fraccion_en(perfil, anio: int) -> float:
    """La fracción del total de una carga nueva en el año ``anio`` del PIDE: la acumulada de sus
    partes hasta él, 0 antes de la primera (030:RF-11, RF-15). ``perfil``: ``[[año, acumulada]]``."""
    vistas = [f for a, f in sorted(perfil or [[0, 1.0]]) if a <= anio]
    return float(vistas[-1]) if vistas else 0.0


def cargas_nuevas_del_proyecto(app, pedidas: list | None = None) -> dict[str, list]:
    """Las cargas (``ElmLod``) de las variaciones de carga nueva con su perfil de ingreso: el de
    ``pedidas`` (``[{'variacion', 'perfil'}]``) o entera en el año 00 (030:RF-9, RF-11, RF-15)."""
    perfiles = {str(p['variacion']): p.get('perfil') or [[int(p.get('anio') or 0), 1.0]]
                for p in pedidas or [] if p.get('variacion')}
    carpeta = app.GetProjectFolder('scheme')
    out: dict[str, list] = {}
    for v in (carpeta.GetContents('*.IntScheme', 1) if carpeta else []):
        if not es_de_carga_nueva(v):
            continue
        perfil = next((x for nombre, x in perfiles.items()
                       if v.loc_name == nombre or v.loc_name.startswith(nombre + '(')), [[0, 1.0]])
        for clase, nombre in objetos_de_variacion(v):
            if clase == 'ElmLod':
                out[nombre] = perfil
    return out


def _exigir_destino_anual(copia, origen, carpeta, nombre, clase):
    """072:RF-23/28: AddCopy no autoriza escribir sin identificar su destino nuevo."""
    if (copia is None or copia.GetClassName() != clase
            or clave_pf(copia) == clave_pf(origen)
            or clave_pf(copia.GetParent()) != clave_pf(carpeta) or copia.loc_name != nombre):
        raise PideError(f'no se creó una copia anual independiente de {clase}')


def _comprobar_copia_activa(app, caso, escenario):
    actual, esc_actual = app.GetActiveStudyCase(), app.GetActiveScenario()
    if (actual is None or clave_pf(actual) != clave_pf(caso) or escenario is None
            or esc_actual is None or clave_pf(esc_actual) != clave_pf(escenario)):
        raise PideError('el caso y escenario activos no son la copia anual identificada')


def casos_del_anio(app, origenes: dict, anio: int, factor_de, base: dict | None = None,
                   nuevas: dict[str, list] | None = None, *, estudio_id: str | None = None) -> dict:
    """«PIDE/Año NN» en casos y en escenarios, con un caso y un escenario por papel; la demanda de
    cada carga, por el factor de su alimentador (030:RF-1 a RF-3, RF-5, RF-8). ``factor_de(elm)``:
    el factor del año del ``ElmFeeder``; ``base``: el ``scale0`` de cada carga antes del PIDE, sobre
    el que se aplica, para que un año nunca escale el de otro."""
    base = base if base is not None else {}
    nuevas = nuevas or {}
    if estudio_id:
        for origen in origenes.values():
            if origen.Activate() != 0 or clave_pf(app.GetActiveStudyCase()) != clave_pf(origen):
                raise PideError('no se activó el origen de la copia anual')
    etiqueta = f'Año {anio:02d}'
    raiz_casos = _carpeta(app.GetProjectFolder('study'), 'PIDE')
    raiz_escenarios = _carpeta(app.GetProjectFolder('scen', 1), 'PIDE')
    if estudio_id:
        raiz_casos, raiz_escenarios = _carpeta(raiz_casos, estudio_id), _carpeta(raiz_escenarios, estudio_id)
    casos = _carpeta(raiz_casos, etiqueta)
    escenarios = _carpeta(raiz_escenarios, etiqueta)
    out = {}
    for rol, nombre in CASOS_DEL_ANIO:
        origen = origenes.get(rol)
        if origen is None:
            continue
        esc_origen = None if estudio_id else _escenario_de(app, origen)
        rc_origen = origen.Activate()           # el de una corrida anterior no puede estar activo
        if estudio_id and (rc_origen != 0 or clave_pf(app.GetActiveStudyCase()) != clave_pf(origen)):
            raise PideError('no se reabrió el origen de la copia anual')
        if estudio_id:
            esc_origen = app.GetActiveScenario()
            if esc_origen is None:
                raise PideError('el origen anual no tiene escenario identificado')
        for x in casos.GetContents('*.IntCase'):
            if x.loc_name == nombre:
                if estudio_id:
                    raise PideError('la copia anual ya existe; no se sobrescribe')
                x.Delete()                      # RF-5: se renueva, sin duplicar
        for x in escenarios.GetContents('*.IntScenario'):
            if x.loc_name == nombre:
                if estudio_id:
                    raise PideError('el escenario anual ya existe; no se sobrescribe')
                x.Delete()
        caso = casos.AddCopy(origen, nombre)
        if estudio_id:
            _exigir_destino_anual(caso, origen, casos, nombre, 'IntCase')
        rc_caso = caso.Activate()
        if estudio_id and (rc_caso != 0 or clave_pf(app.GetActiveStudyCase()) != clave_pf(caso)):
            raise PideError('no se activó la nueva copia anual')
        _marcar(caso, f'pide_{anio:02d}_{rol}')                              # RF-8
        actual = app.GetActiveScenario()
        if actual is not None:
            rc_esc = actual.Deactivate(0)
            if estudio_id and (rc_esc != 0 or app.GetActiveScenario() is not None):
                raise PideError('no se apartó el escenario antes de crear la copia anual')
        esc = escenarios.AddCopy(esc_origen, nombre) if esc_origen is not None \
            else escenarios.CreateObject('IntScenario', nombre)
        if estudio_id:
            _exigir_destino_anual(esc, esc_origen, escenarios, nombre, 'IntScenario')
        rc_esc = esc.Activate()
        if estudio_id:
            if rc_esc != 0:
                raise PideError('no se activó el nuevo escenario anual')
            _comprobar_copia_activa(app, caso, esc)
        for elm in app.GetActiveProject().GetContents('*.ElmFeeder', 1):
            f = factor_de(elm)
            if f is None:
                continue
            for c in elm.GetObjs('ElmLod'):
                if c.loc_name in nuevas:
                    continue                                                 # RF-9: constante
                b = base.setdefault(clave_pf(c), float(getattr(c, 'scale0', 1.0) or 1.0))
                c.scale0 = b * f                                             # RF-3, en su escenario
        if rol in ('cargas', 'con') and nuevas:
            # RF-11, RF-15: la carga nueva lleva lo que entró hasta este año, sin crecimiento;
            # antes de su primera parte, fuera de servicio.
            for c in app.GetCalcRelevantObjects('*.ElmLod') or []:
                if c.loc_name not in nuevas:
                    continue
                f = fraccion_en(nuevas[c.loc_name], anio)
                b = base.setdefault(clave_pf(c), float(getattr(c, 'scale0', 1.0) or 1.0))
                c.outserv = 0 if f > 0 else 1
                if f > 0:
                    c.scale0 = b * f
        if estudio_id:
            _comprobar_copia_activa(app, caso, esc)
        if esc.Save() != 0:
            raise PideError(f'no se guardó el escenario {clave_pf(esc)}')
        ruta = '/'.join(['PIDE', *([estudio_id] if estudio_id else []), etiqueta, nombre])
        out[rol] = {'caso': ruta, 'escenario': ruta, 'objeto': caso}
        if estudio_id:
            out[rol]['objeto_escenario'] = esc
    return out


def _inventario_anual(app, proyecto, plan, cargas):
    """El alcance se relee: una maniobra puede trasladar cargas entre los alimentadores elegidos."""
    alims = Alimentadores(app, proyecto, plan['feeders'])
    inventario = {c: {} for c in ('ElmTerm', 'ElmLne', 'ElmTr2', 'ElmTr3', 'ElmLod')}
    raiz = clave_pf(proyecto) + '\\'
    for nombre in plan['feeders']:
        for clase, objetos in inventario.items():
            for obj in alims.elm[nombre].GetObjs(clase):
                key = clave_pf(obj)
                if not key.startswith(raiz):
                    raise PideError(f'objeto ajeno al proyecto en el alcance anual: {key}')
                objetos[key] = obj
    if not inventario['ElmTerm'] or set(inventario['ElmLod']) != set(cargas):
        faltan = sorted(set(cargas) - set(inventario['ElmLod']))
        nuevas = sorted(set(inventario['ElmLod']) - set(cargas))
        raise PideError(f'cambió la cobertura física anual: cargas ausentes {faltan}, no previstas {nuevas}')
    # Un ElmFeeder puede omitir la BT de una carga que sí enumera. Su terminal
    # conectado también pertenece al alcance; no desaparece por esa omisión.
    for carga, _nombre in cargas.values():
        barra = getattr(getattr(carga, 'bus1', None), 'cterm', None)
        if barra is not None:
            key = clave_pf(barra)
            if not key.startswith(raiz):
                raise PideError(f'conexión ajena al proyecto de una carga anual: {key}')
            inventario['ElmTerm'][key] = barra
    return inventario


def _comprobar_demanda_anual(cargas, filas, representacion):
    for key, (carga, _nombre) in cargas.items():
        por_fase = int(getattr(carga, 'i_sym', 0) or 0) == 1
        unidades = {'plini': 'MW', 'qlini': 'Mvar'}
        if por_fase:
            unidades.update({f'{a}{f}': u for f in 'rst' for a, u in (('plini', 'MW'), ('qlini', 'Mvar'))})
        entradas = {a: _num(carga, a) for a in (*unidades, 'scale0')}
        # El corto plazo todavía no tiene filas de proyección: sus agregados
        # finitos no acreditan las seis entradas por fase que consumirá el motor.
        if any(v is None for v in entradas.values()):
            raise PideError(f'la demanda nativa anual no es finita o está incompleta: {key}')
        try:
            correctas = all(str(carga.GetAttributeUnit(a)) == u for a, u in unidades.items())
        except Exception as exc:
            raise PideError(f'unidades de demanda anual no verificadas: {key}') from exc
        if not correctas:
            raise PideError(f'unidades de demanda anual no verificadas: {key}')
        for prefijo in ('plini', 'qlini'):
            total = sum(entradas[f'{prefijo}{f}'] for f in 'rst') if por_fase else entradas[prefijo]
            if not math.isfinite(total * entradas['scale0']):
                raise PideError(f'la demanda efectiva anual por fase o escala no es finita: {key}')
        if int(getattr(carga, 'outserv', 0) or 0):
            raise PideError(f'carga anual retirada de servicio: {key}')
        if representacion is not None and any(getattr(carga, a, None) != v for a, v in representacion[key].items()):
            raise PideError(f'cambió la representación física de la carga anual: {key}')
        if filas is None:
            continue
        fila = filas[key]
        if carga.scale0 != 1.0 or error_relectura(carga, fila['p_kw'] / 1000.0, fila['q_kvar'] / 1000.0):
            raise PideError(f'la obra o el flujo cambiaron la demanda anual aceptada: {key}')
        if int(getattr(carga, 'i_sym', 0) or 0) == 1:
            foto = foto_carga(carga)
            if any(not math.isclose(float(foto[f'{attr}{f}']), fila['fases'][f][campo] / 1000.0,
                       abs_tol=1e-9, rel_tol=1e-6)
                   for f in 'rst' for attr, campo in (('plini', 'p_kw'), ('qlini', 'q_kvar'))):
                raise PideError(f'la obra o el flujo cambiaron las fases anuales aceptadas: {key}')


def _servicio_anual(inventario, cargas, limites):
    """Lectura nativa por identidad; el dictamen BT/consumo sigue siendo el común de 081."""
    barras = [{'nombre': key, 'uknom_kv': _num(b, 'uknom'), 'u_pu': _num(b, 'm:u')}
              for key, b in inventario['ElmTerm'].items() if not getattr(b, 'outserv', 0)]
    demandas, problemas = [], []
    for key, (carga, _nombre) in cargas.items():
        barra = getattr(getattr(carga, 'bus1', None), 'cterm', None)
        if barra is None or clave_pf(barra) not in inventario['ElmTerm']:
            raise PideError(f'falta la conexión física de la carga anual: {key}')
        if int(getattr(barra, 'outserv', 0) or 0):
            # PF puede conservar m:u y consumo de un cálculo previo. Esas
            # magnitudes no vuelven a poner en servicio el terminal retirado.
            problemas.append({'causa': 'conexion_fuera_de_servicio', 'elemento': key,
                              'barra': clave_pf(barra)})
        p, q = _num(carga, 'm:Psum:bus1'), _num(carga, 'm:Qsum:bus1')
        if p is None or q is None:
            raise PideError(f'falta lectura de consumo P/Q de la carga anual: {key}')
        por_fase = int(getattr(carga, 'i_sym', 0) or 0) == 1
        programada = (sum(float(getattr(carga, f'plini{f}')) for f in 'rst') if por_fase else float(carga.plini)) * float(carga.scale0)
        reactiva = (sum(float(getattr(carga, f'qlini{f}')) for f in 'rst') if por_fase else float(carga.qlini)) * float(carga.scale0)
        if por_fase:
            for fase, nativa in zip('rst', 'ABC'):
                if max(abs(float(getattr(carga, f'{a}{fase}'))) for a in ('plini', 'qlini')) <= UMBRAL_MW:
                    continue  # una fase declarada sin demanda no inventa una fase física activa
                u = _num(barra, f'm:u:{nativa}')
                if u is None:
                    raise PideError(f'falta tensión de la fase {nativa} requerida por {key}')
                if not limites['tension_min_pu'] <= u <= limites['tension_max_pu'] or u <= UMBRAL_PU:
                    problemas.append({'causa': 'fase_no_servida_o_fuera_de_banda', 'elemento': key,
                                      'fase': nativa, 'valor': u})
        demandas.append({'nombre': key, 'barra': clave_pf(barra), 'programada_mw': programada,
                         'consumo_mw': p, 'en_servicio': True})
        if ((_num(barra, 'm:u') or 0) <= UMBRAL_PU
                or (abs(reactiva) > UMBRAL_MW and abs(q) < UMBRAL_MW)):
            problemas.append({'causa': 'carga_no_servida', 'elemento': key})
    tras = comprobar_tras_flujo(barras, demandas)
    if not tras['limpio']:
        problemas.append({'causa': 'servicio_incompleto', 'evidencia': texto_tras_flujo(tras)})
    return problemas


def _medida_anual(app, proyecto, plan: dict, barras: dict, *, por_fase: bool = False,
                  demanda_absoluta: bool = True, cargas=None, filas=None, representacion=None,
                  comprobar_cancelacion=None) -> dict:
    """072:RF-25 — converger y cumplir son resultados distintos de una relectura."""
    if not cargas:
        raise PideError('falta el inventario de cargas del estudio anual')
    _comprobar_demanda_anual(cargas, filas, representacion)
    ldf = app.GetFromStudyCase('ComLdf')
    if demanda_absoluta:
        ldf.scLoadFac = 100.0
    if demanda_absoluta and ldf.scLoadFac != 100.0:
        raise PideError('no se fijó el flujo al 100 % de las demandas anuales absolutas')
    if comprobar_cancelacion is not None:
        comprobar_cancelacion()  # la lectura nativa previa puede haber tardado; aún no comenzó el motor
    flujo = flujo_de_carga(app, monofasicos=True if por_fase else None)
    if not flujo['converged']:
        return {'converge': False, 'cumple': False, 'problemas': [{'causa': 'no_converge'}]}
    lectura = {'flujo': resultados(app, proyecto, clave_pf(proyecto), plan['feeders']),
               'topologia': {'barras': barras}}
    inventario = _inventario_anual(app, proyecto, plan, cargas)
    _comprobar_demanda_anual(cargas, filas, representacion)
    lectura['topologia']['barras'] = {identidad_nativa('ElmTerm', key, clave_pf(proyecto)):
        {'nombre': b.loc_name, 'kv': _num(b, 'uknom')} for key, b in inventario['ElmTerm'].items()}
    tensiones, capacidad = lectura['flujo'].get('tensiones') or {}, lectura['flujo'].get('cargabilidad') or {}
    if tensiones.get('unidad') != 'p.u.' or capacidad.get('unidad') != '%':
        raise PideError('unidades de tensión/cargabilidad anual no verificadas')
    valores, sin_tension = tensiones.get('valores') or {}, set(tensiones.get('sin_tension') or [])
    esperadas = {identidad_nativa('ElmTerm', key, clave_pf(proyecto))
                 for key, b in inventario['ElmTerm'].items() if not getattr(b, 'outserv', 0)}
    if not esperadas or esperadas - (set(valores) | sin_tension):
        raise PideError('faltan tensiones para cubrir el inventario físico anual')
    valores = {key: valores[key] if key in valores else 0.0 for key in esperadas}
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in valores.values()):
        raise PideError('faltan tensiones finitas para aceptar el año')
    grupos = capacidad.get('valores') or {}
    medidas = {'lineas': {}, 'transformadores': {}}
    for clase, grupo in (('ElmLne', 'lineas'), ('ElmTr2', 'transformadores'), ('ElmTr3', 'transformadores')):
        for key, obj in inventario[clase].items():
            if getattr(obj, 'outserv', 0):
                continue
            ident = identidad_nativa(clase, key, clave_pf(proyecto))
            # El lector común actualmente cubre Tr2; Tr3 exige su lectura nativa,
            # nunca se omite por no existir una entrada en ese lector.
            valor = _num(obj, 'c:loading') if clase == 'ElmTr3' else (grupos.get(grupo) or {}).get(ident)
            if type(valor) not in (int, float) or not math.isfinite(valor):
                raise PideError(f'falta cargabilidad finita del inventario anual: {key}')
            medidas[grupo][ident] = valor
    lectura['flujo']['tensiones'] = {**tensiones, 'valores': valores, 'sin_tension': sorted(esperadas & sin_tension)}
    lectura['flujo']['cargabilidad'] = {**capacidad, 'valores': medidas}
    problemas = diagnosticar(lectura, **plan['limites'])
    problemas = [p.__dict__ for p in problemas] + _servicio_anual(inventario, cargas, plan['limites'])
    return {'converge': True, 'cumple': not problemas, 'problemas': problemas,
            'vm_min': min(valores.values()),
            'perdidas_kw': ((lectura['flujo'].get('perdidas') or {}).get('valores') or {}).get('total')}


def _demanda_del_anio(app, caso, origen, filas, cargas, estudio, anio, rol, variaciones_demanda,
                      *, escenario_esperado=None) -> None:
    """072:RF-24/27 — P/Q por fase quedan en una variación propia, nunca en la red global.

    Los totales equilibrados usan el escritor común. Las fases explícitas se
    escriben literalmente, sin el reparto proporcional de la calibración.
    La variación de demanda del año anterior se sustituye, no cuenta como obra.
    """
    if caso.Activate() != 0 or clave_pf(app.GetActiveStudyCase()) != clave_pf(caso):
        raise PideError('no se activó la copia anual')
    _comprobar_copia_activa(app, caso, escenario_esperado)
    for v in list(app.GetActiveNetworkVariations() or []):
        if clave_pf(v) in variaciones_demanda and v.Deactivate() != 0:
            raise PideError('no se apartó la demanda por fases del año anterior')
    por_fase = any(int(getattr(cargas[key][0], 'i_sym', 0) or 0) == 1 for key in filas)
    if por_fase:
        variacion, _etapa = crear_variacion(app, f'PIDE_demanda_{estudio}_{anio}_{rol}', f'{estudio}_{anio}_{rol}')
        variaciones_demanda.add(clave_pf(variacion))
    for key, fila in filas.items():
        _comprobar_copia_activa(app, caso, escenario_esperado)
        carga = cargas[key][0]
        carga.scale0 = 1.0
        if int(getattr(carga, 'i_sym', 0) or 0) == 1:
            for f, valores in fila['fases'].items():
                setattr(carga, f'plini{f}', valores['p_kw'] / 1000.0)
                setattr(carga, f'qlini{f}', valores['q_kvar'] / 1000.0)
        else:
            escribir_carga(carga, fila['p_kw'] / 1000.0, fila['q_kvar'] / 1000.0)
        error = error_relectura(carga, fila['p_kw'] / 1000.0, fila['q_kvar'] / 1000.0)
        if error:
            raise PideError(error)
    escenario = app.GetActiveScenario()
    _comprobar_copia_activa(app, caso, escenario_esperado)
    if escenario.Save() != 0:
        raise PideError(f'no se guardó el escenario anual {anio}')
    if origen.Activate() != 0 or clave_pf(app.GetActiveStudyCase()) != clave_pf(origen):
        raise PideError('no se reabrió el origen antes de releer la copia anual')
    if caso.Activate() != 0 or clave_pf(app.GetActiveStudyCase()) != clave_pf(caso):
        raise PideError('no se reabrió la copia anual')
    _comprobar_copia_activa(app, caso, escenario_esperado)
    for key, fila in filas.items():
        carga = cargas[key][0]
        if error_relectura(carga, fila['p_kw'] / 1000.0, fila['q_kvar'] / 1000.0) or carga.scale0 != 1.0:
            raise PideError(f'la relectura anual no conserva P/Q de {key}')
        if int(getattr(carga, 'i_sym', 0) or 0) == 1:
            foto = foto_carga(carga)
            if any(not math.isclose(float(foto[f'{attr}{f}']), fila['fases'][f][campo] / 1000.0, abs_tol=1e-9, rel_tol=1e-6)
                   for f in 'rst' for attr, campo in (('plini', 'p_kw'), ('qlini', 'q_kvar'))):
                raise PideError(f'la relectura anual no conserva las fases de {key}')


class _PideCancelado(Exception):
    """072:RF-27: salida cooperativa que conserva la restitución del finally."""


def ejecutar_anual(app, plan: dict, *, cancelado=None) -> tuple[dict, int]:
    """072:RF-27: conserva por separado el proyecto estudiado y el contexto inicial."""
    inicial = (app.GetActiveProject(), app.GetActiveStudyCase(), app.GetActiveScenario())
    variaciones = list(app.GetActiveNetworkVariations() or [])
    etapa = app.GetRecordingStage()
    hora = getattr(inicial[1], 'iStudyTime', None) if inicial[1] else None
    informe = {'project': plan.get('project'), 'modo': 'anual', 'estado': 'bloqueado',
               'anios': [], 'aceptacion_nativa': False, 'avisos': []}
    codigo = 2
    try:
        leer_proyeccion_anual(plan)
        if cancelado is not None and cancelado():
            informe['estado'], codigo = 'cancelado', 0
        else:
            objetivo = activar_proyecto(app, plan['project'], plan.get('folder'))
            if objetivo is None or app.GetActiveProject() is None or clave_pf(app.GetActiveProject()) != clave_pf(objetivo):
                raise PideError('no se activó el proyecto anual solicitado')
            # La captura interior ocurre DESPUÉS de activar el objetivo. Así no
            # se usan fotos del proyecto A para certificar restaurar el B.
            informe, codigo = _ejecutar_anual_en_activo(app, plan, cancelado=cancelado)
    except Exception as exc:  # borde nativo: también restituye si falló activar el objetivo
        informe['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        diferencias = []
        objetivo_restituido = informe.get('restitucion')
        try:
            proyecto, caso, escenario = inicial
            if proyecto is not None and proyecto.Activate() != 0:
                raise PideError('no se restituyó el proyecto inicial')
            if caso is not None and caso.Activate() != 0:
                raise PideError('no se restituyó el caso inicial')
            elif caso is None and app.GetActiveStudyCase() is not None and app.GetActiveStudyCase().Deactivate() != 0:
                raise PideError('no se desactivó el caso temporal')
            if escenario is not None and escenario.Activate() != 0:
                raise PideError('no se restituyó el escenario inicial')
            elif escenario is None and app.GetActiveScenario() is not None and app.GetActiveScenario().Deactivate(0) != 0:
                raise PideError('no se desactivó el escenario temporal')
            for v in reversed(app.GetActiveNetworkVariations() or []):
                if v.Deactivate() != 0:
                    raise PideError('no se apartó una variación del contexto temporal')
            for v in variaciones:
                if v.Activate() != 0:
                    raise PideError('no se restituyó una variación inicial')
            if etapa is not None and etapa.Activate(1) != 0:
                raise PideError('no se restituyó la etapa inicial')
            if hora is not None:
                caso.iStudyTime = hora
                if caso.iStudyTime != hora:
                    diferencias.append('hora inicial')
            if proyecto is None and app.GetActiveProject() is not None and app.GetActiveProject().Deactivate() != 0:
                raise PideError('no se desactivó el proyecto temporal')
            for esperado, actual, nombre in zip(inicial,
                    (app.GetActiveProject(), app.GetActiveStudyCase(), app.GetActiveScenario()),
                    ('proyecto inicial', 'caso inicial', 'escenario inicial')):
                if (clave_pf(esperado) if esperado else None) != (clave_pf(actual) if actual else None):
                    diferencias.append(nombre)
            if {clave_pf(v) for v in app.GetActiveNetworkVariations() or []} != {clave_pf(v) for v in variaciones}:
                diferencias.append('variaciones iniciales')
            actual = app.GetRecordingStage()
            if (clave_pf(actual) if actual else None) != (clave_pf(etapa) if etapa else None):
                diferencias.append('etapa inicial')
        except Exception as exc:
            diferencias.append(f'{type(exc).__name__}: {exc}')
        if objetivo_restituido and not objetivo_restituido['ok']:
            diferencias.extend(objetivo_restituido['diferencias'])
        informe['restitucion'] = {'ok': not diferencias, 'diferencias': diferencias,
                                  'objetivo': objetivo_restituido}
        if diferencias:
            informe['estado'], codigo = 'bloqueado_restitucion', 2
            informe['error'] = 'no se pudo confirmar la restitución del objetivo y del contexto inicial'
    return informe, codigo


def _ejecutar_anual_en_activo(app, plan: dict, *, cancelado=None) -> tuple[dict, int]:
    """072:RF-23 a RF-28 — continúa copias del corto plazo con demanda anual aceptada.

    Las variaciones son obras físicas preparadas por la vía de obras existente.
    Su ausencia no se cubre con una propuesta textual ni con parámetros inventados.
    La conservación se comprueba incluso al fallar entre dos años.
    """
    informe = {'project': plan.get('project'), 'modo': 'anual', 'estado': 'bloqueado', 'anios': [],
               'primer_anio_incumplimiento': None, 'aceptacion_nativa': False, 'avisos': []}
    inicial_proyecto, inicial_caso, inicial_escenario = app.GetActiveProject(), app.GetActiveStudyCase(), app.GetActiveScenario()
    variaciones_iniciales = list(app.GetActiveNetworkVariations() or [])
    etapa_inicial = app.GetRecordingStage()
    hora_inicial = getattr(inicial_caso, 'iStudyTime', None) if inicial_caso else None
    cargas_iniciales = list(inicial_proyecto.GetContents('*.ElmLod', 1)) if inicial_proyecto else []
    fotos = {clave_pf(c): (c, float(c.plini), float(c.qlini), float(c.scale0), getattr(c, 'pf_recap', None)) for c in cargas_iniciales}
    fisica = [(obj, atributo, clave_pf(getattr(obj, atributo)) if atributo == 'typ_id' else getattr(obj, atributo))
              for clase, atributos in (('ElmTr2', ('typ_id',)), ('ElmLne', ('typ_id', 'dline')),
                                        ('ElmCoup', ('on_off',)), ('StaSwitch', ('on_off',)),
                                        ('ElmLod', ('i_sym', 'phtech', 'pf_recap', 'plinir', 'plinis', 'plinit', 'qlinir', 'qlinis', 'qlinit')))
              for obj in (inicial_proyecto.GetContents(f'*.{clase}', 1) if inicial_proyecto else [])
              for atributo in atributos if getattr(obj, atributo, None) is not None]
    ldf_inicial = app.GetFromStudyCase('ComLdf')
    factor_inicial = getattr(ldf_inicial, 'scLoadFac', None)
    modo_flujo_inicial = getattr(ldf_inicial, 'iopt_net', None)
    fechas_etapas = []
    codigo = 2
    def comprobar_cancelacion():
        if cancelado is not None and cancelado():
            raise _PideCancelado()
    try:
        comprobar_cancelacion()
        datos = leer_proyeccion_anual(plan)
        comprobar_cancelacion()
        estudio = str(plan.get('estudio_id') or '')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', estudio) or estudio in ('.', '..'):
            raise PideError('falta un identificador de estudio nuevo y válido')
        proyecto = app.GetActiveProject()
        if proyecto is None:
            raise PideError('no existe el proyecto anual solicitado')
        fechas_etapas = [(s, getattr(s, 'tAcTime', None)) for s in app.GetProjectFolder('scheme').GetContents('*.IntSstage', 1)]
        for folder in (app.GetProjectFolder('study'), app.GetProjectFolder('scen', 1)):
            for pide in folder.GetContents('*.IntFolder'):
                if pide.loc_name == 'PIDE' and any(x.loc_name == estudio for x in pide.GetContents('*.IntFolder')):
                    raise PideError(f'el estudio {estudio} ya existe; no se sobrescribe')
        corto = plan['corto_plazo']
        evidencia = leer_json_con_huella(corto['evidencia'], 'aceptación del corto plazo')
        if evidencia.get('estado') != 'aceptado' or any(evidencia.get(k) != corto.get(k) for k in ('caso', 'escenario', 'anio', 'anio_base', 'variaciones')):
            raise PideError('la aceptación del corto plazo no corresponde al caso, escenario y obras solicitados')
        comprobar_cancelacion()
        origenes = [c for c in app.GetProjectFolder('study').GetContents('*.IntCase', 1) if clave_pf(c) == corto['caso']]
        if len(origenes) != 1:
            raise PideError('el caso de corto plazo no tiene una identidad completa única')
        previo = origenes[0]
        if previo.Activate() != 0 or clave_pf(app.GetActiveScenario()) != corto['escenario']:
            raise PideError('no se reabrió el escenario de corto plazo declarado')
        activas_corto = {clave_pf(v) for v in app.GetActiveNetworkVariations() or []}
        acumuladas = set(corto['variaciones'])
        if not acumuladas.issubset(activas_corto):
            raise PideError('faltan obras de corto plazo activas en el caso declarado')
        feeders = set(plan['feeders'])
        candidatos = [f for f in proyecto.GetContents('*.ElmFeeder', 1) if f.loc_name in feeders]
        encontrados = {f.loc_name: f for f in candidatos}
        if len(encontrados) != len(candidatos):
            raise PideError('identidad ambigua de alimentador dentro del proyecto')
        if set(encontrados) != feeders or not feeders:
            raise PideError('faltan alimentadores del estudio anual')
        alims = Alimentadores(app, proyecto, sorted(feeders))
        cargas, barras = {}, {}
        for nombre in sorted(encontrados):
            feeder = alims.elm[nombre]
            for carga in feeder.GetObjs('ElmLod'):
                key = clave_pf(carga)
                if key in cargas:
                    raise PideError('una carga pertenece a más de un alimentador del plan')
                cargas[key] = (carga, nombre)
                if any(str(carga.GetAttributeUnit(a)) != unidad for a, unidad in (('plini', 'MW'), ('qlini', 'Mvar'))):
                    raise PideError(f'unidades no verificadas MW/Mvar en {key}')
            for barra in feeder.GetObjs('ElmTerm'):
                barras[identidad_nativa('ElmTerm', clave_pf(barra), clave_pf(proyecto))] = {
                    'nombre': barra.loc_name, 'kv': _num(barra, 'uknom'), 'alimentador': nombre}
        for anio, filas in datos['por_anio'].items():
            if set(filas) != set(cargas):
                raise PideError(f'año {anio}: la proyección no cubre exactamente las cargas físicas del estudio')
            for key, fila in filas.items():
                carga, feeder = cargas[key]
                if fila['alimentador'] != feeder:
                    raise PideError(f'la proyección de {key} pertenece a otro alimentador')
                if int(getattr(carga, 'i_sym', 0) or 0) == 1:
                    if not fila.get('fases'):
                        raise PideError(f'falta proyección por fase compatible de {key}; no se reparten totales')
                    if any(str(carga.GetAttributeUnit(f'{a}{f}')) != unidad for f in 'rst' for a, unidad in (('plini', 'MW'), ('qlini', 'Mvar'))):
                        raise PideError(f'unidades por fase no verificadas en {key}')
                modo = str(getattr(carga, 'mode_inp', '')).upper()
                if int(getattr(carga, 'i_sym', 0) or 0) == 0 and modo in ('PC', 'SC', 'QC') and int(getattr(carga, 'pf_recap', 0) or 0) != int(fila['q_kvar'] < 0):
                    raise PideError(f'falta representación de Q con su signo en el escenario de {key}')
        variaciones = {clave_pf(v): v for v in app.GetProjectFolder('scheme').GetContents('*.IntScheme', 1)}
        representacion = {key: {a: getattr(c, a, None) for a in ('i_sym', 'phtech', 'mode_inp')}
                          for key, (c, _f) in cargas.items()}
        obras = {}
        declaradas = set()
        for obra in plan.get('obras_por_anio') or []:
            anio, identidad = obra['anio'], obra['variacion']
            if type(anio) is not int or anio not in datos['por_anio'] or identidad not in variaciones:
                raise PideError(f'obra anual sin variación física identificada: {identidad}')
            if identidad in activas_corto or identidad in declaradas:
                raise PideError(f'obra anual ya activa o declarada dos veces: {identidad}')
            declaradas.add(identidad)
            obras.setdefault(anio, []).append(identidad)
        informe['proyeccion'] = {'modelo': datos['modelo'], 'dataset_sha256': datos['dataset_sha256'],
                                  'archivo_sha256': plan['proyeccion_anual']['sha256'], 'anio_base': datos['anio_base']}
        # La aceptación documental no cubre un cambio posterior de la red: el
        # corto plazo debe seguir cumpliendo antes de crear las copias anuales.
        ldf_corto = app.GetFromStudyCase('ComLdf')
        opciones_corto = {k: getattr(ldf_corto, k, None) for k in ('scLoadFac', 'iopt_net')}
        try:
            comprobar_cancelacion()
            informe['corto_plazo'] = _medida_anual(app, proyecto, plan, barras,
                por_fase=any(int(getattr(c, 'i_sym', 0) or 0) == 1 for c, _f in cargas.values()),
                demanda_absoluta=False, cargas=cargas, representacion=representacion,
                comprobar_cancelacion=comprobar_cancelacion)
        finally:
            for k, v in opciones_corto.items():
                if v is not None and getattr(ldf_corto, k, None) != v:
                    setattr(ldf_corto, k, v)
                    if getattr(ldf_corto, k, None) != v:
                        raise PideError('no se conservaron las opciones del flujo de corto plazo')
        if not informe['corto_plazo']['cumple']:
            raise PideError('el caso de corto plazo no cumple actualmente; debe resolverse antes del PIDE anual')
        variaciones_demanda = set()
        for anio, filas in datos['por_anio'].items():
            comprobar_cancelacion()
            origen = previo
            casos = casos_del_anio(app, {'sin': origen, 'con': origen}, anio, lambda _f: None, estudio_id=estudio)
            for rol in ('sin', 'con'):
                comprobar_cancelacion()
                caso = casos[rol]['objeto']
                _demanda_del_anio(app, caso, origen, filas, cargas, estudio, anio, rol, variaciones_demanda,
                                  escenario_esperado=casos[rol]['objeto_escenario'])
            comprobar_cancelacion()
            por_fase = any(int(getattr(c, 'i_sym', 0) or 0) == 1 for c, _f in cargas.values())
            antes = _medida_anual(app, proyecto, plan, barras, por_fase=por_fase,
                cargas=cargas, filas=filas, representacion=representacion,
                comprobar_cancelacion=comprobar_cancelacion)
            fila_anual = {'anio': anio, 'anio_calendario': datos['anio_base'] + anio, 'antes': antes,
                          'casos': {r: c['caso'] for r, c in casos.items()}, 'obras_aplicadas': []}
            informe['anios'].append(fila_anual)
            comprobar_cancelacion()
            if not antes['cumple']:
                if informe['primer_anio_incumplimiento'] is None:
                    informe['primer_anio_incumplimiento'] = anio
                if not obras.get(anio):
                    raise PideError(f'año {anio}: falta una obra física para los incumplimientos medidos')
                for identidad in obras[anio]:
                    comprobar_cancelacion()
                    if identidad not in acumuladas:
                        if variaciones[identidad].Activate() != 0:
                            raise PideError(f'no se activó la obra {identidad}')
                        fila_anual['obras_aplicadas'].append(identidad)
                activas = {clave_pf(v) for v in app.GetActiveNetworkVariations() or []} - variaciones_demanda
                if not (acumuladas | set(obras[anio])).issubset(activas):
                    raise PideError('la relectura no conserva las obras acumuladas')
                acumuladas |= set(obras[anio])
            comprobar_cancelacion()
            fila_anual['despues'] = _medida_anual(app, proyecto, plan, barras, por_fase=por_fase,
                cargas=cargas, filas=filas, representacion=representacion,
                comprobar_cancelacion=comprobar_cancelacion)
            fila_anual['obras_acumuladas'] = sorted(acumuladas)
            if not fila_anual['despues']['cumple']:
                raise PideError(f'año {anio}: las obras declaradas no resuelven el incumplimiento')
            previo = casos['con']['objeto']
            comprobar_cancelacion()
        informe['estado'], codigo = 'completo', 0
    except _PideCancelado:
        informe['estado'], codigo = 'cancelado', 0
        informe['avisos'].append('Cancelación solicitada: no se inicia otra etapa; se restituyó el estado original si la relectura lo confirma.')
    except Exception as exc:  # borde nativo: conservar también los años ya medidos ante errores de la API
        informe['error'] = f'{type(exc).__name__}: {exc}'
        informe['estado'] = 'incompleto' if informe['anios'] else 'bloqueado'
    finally:
        diferencias = []
        try:
            for etapa, fecha in fechas_etapas:
                if fecha is not None and etapa.tAcTime != fecha:
                    etapa.tAcTime = fecha
                    if etapa.tAcTime != fecha:
                        diferencias.append(f'fecha de {clave_pf(etapa)}')
            if inicial_proyecto is not None and inicial_proyecto.Activate() != 0:
                raise PideError('no se restituyó el proyecto inicial')
            if inicial_caso is not None and inicial_caso.Activate() != 0:
                raise PideError('no se restituyó el caso inicial')
            elif inicial_caso is None and app.GetActiveStudyCase() is not None:
                if app.GetActiveStudyCase().Deactivate() != 0:
                    raise PideError('no se desactivó el caso temporal')
            actual = app.GetActiveScenario()
            if inicial_escenario is not None:
                if inicial_escenario.Activate() != 0:
                    raise PideError('no se restituyó el escenario inicial')
            elif actual is not None and actual.Deactivate(0) != 0:
                raise PideError('no se desactivó el escenario temporal')
            deseadas = {clave_pf(v) for v in variaciones_iniciales}
            # Reaplicar la pila completa evita que quitar una obra tardía sobre
            # el mismo equipo deshaga también la obra corta que debe conservarse.
            for v in reversed(app.GetActiveNetworkVariations() or []):
                if v.Deactivate() != 0:
                    raise PideError('no se desactivó una variación durante la restitución')
            for v in variaciones_iniciales:
                if v.Activate() != 0:
                    raise PideError('no se restituyó una variación original')
            if etapa_inicial is not None and etapa_inicial.Activate(1) != 0:
                raise PideError('no se restituyó la etapa que grababa')
            if hora_inicial is not None:
                inicial_caso.iStudyTime = hora_inicial
                if inicial_caso.iStudyTime != hora_inicial:
                    diferencias.append('hora del caso')
            for key, (carga, p, q, escala, recap) in fotos.items():
                if (float(carga.plini), float(carga.qlini), float(carga.scale0)) != (p, q, escala):
                    if int(getattr(carga, 'i_sym', 0) or 0) == 0:
                        if recap is not None:
                            carga.pf_recap = recap
                        escribir_carga(carga, p, q)
                        carga.scale0 = escala
                if (float(carga.plini), float(carga.qlini), float(carga.scale0)) != (p, q, escala):
                    diferencias.append(key)
            if factor_inicial is not None:
                ldf_inicial.scLoadFac = factor_inicial
                if ldf_inicial.scLoadFac != factor_inicial:
                    diferencias.append('factor del flujo')
            if modo_flujo_inicial is not None:
                ldf_inicial.iopt_net = modo_flujo_inicial
                if ldf_inicial.iopt_net != modo_flujo_inicial:
                    diferencias.append('modo del flujo')
            if inicial_proyecto is None and app.GetActiveProject() is not None:
                if app.GetActiveProject().Deactivate() != 0:
                    diferencias.append('proyecto temporal')
            for esperado, actual, etiqueta in ((inicial_proyecto, app.GetActiveProject(), 'proyecto'),
                    (inicial_caso, app.GetActiveStudyCase(), 'caso'), (inicial_escenario, app.GetActiveScenario(), 'escenario')):
                if (clave_pf(esperado) if esperado else None) != (clave_pf(actual) if actual else None):
                    diferencias.append(etiqueta)
            if {clave_pf(v) for v in app.GetActiveNetworkVariations() or []} != deseadas:
                diferencias.append('variaciones')
            etapa_actual = app.GetRecordingStage()
            if (clave_pf(etapa_inicial) if etapa_inicial else None) != (clave_pf(etapa_actual) if etapa_actual else None):
                diferencias.append('etapa que graba')
            for obj, atributo, esperado in fisica:
                actual = clave_pf(getattr(obj, atributo)) if atributo == 'typ_id' else getattr(obj, atributo)
                if actual != esperado:
                    diferencias.append(f'{clave_pf(obj)}:{atributo}')
        except Exception as exc:  # el fallo de restitución forma parte del informe, nunca se oculta
            diferencias.append(f'{type(exc).__name__}: {exc}')
        informe['restitucion'] = {'ok': not diferencias, 'diferencias': diferencias}
        if diferencias:
            informe['error'] = 'no se pudo confirmar la restitución del estado original'
            informe['estado'], codigo = 'bloqueado_restitucion', 2
    return informe, codigo


def ejecutar(app, plan: dict, *, cancelado=None) -> tuple[dict, int]:
    """Diagnóstico de cada año con la demanda escalada. Devuelve (informe, código)."""
    if plan.get('modo') == 'anual':
        return ejecutar_anual(app, plan, cancelado=cancelado)
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
        informe.setdefault('km_por_alimentador', {})[feeder] = sum(float(getattr(ln, 'dline', 0) or 0)
                                                                   for ln in elm.GetObjs('ElmLne'))
    por_nombre = {v['nombre']: v for v in barras.values()}
    informe['barras_mt'] = sorted(v['nombre'] for v in barras.values() if (v['kv'] or 0) >= 1)
    # 029:RF-4: con tasa por alimentador, cada uno escala sus cargas con la suya (``scale0``) y el
    # factor del flujo queda en 1; al terminar, cada carga vuelve a su valor.
    por_alim = {str(a): float(x) for a, x in (plan.get('tasa_por_alimentador') or {}).items()}
    if plan.get('casos_por_anio'):
        return _por_anios(app, plan, informe, proyecto, raiz, lim, barras, de_linea, por_nombre, float(tasa),
                          por_alim)
    cargas = {a: list(elms[a].GetObjs('ElmLod')) for a in por_alim if a in elms}
    base_scale = {clave_pf(c): float(getattr(c, 'scale0', 1.0) or 1.0) for cs in cargas.values() for c in cs}
    try:
        for anio in plan.get('anios') or [0]:
            factor = (1 + float(tasa)) ** int(anio)
            if cargas:
                for a, cs in cargas.items():
                    f = (1 + por_alim[a]) ** int(anio)
                    for c in cs:
                        c.scale0 = base_scale[clave_pf(c)] * f
                # Los alimentadores sin tasa propia, con la del sistema; los demás ya escalados.
                for a, elm in elms.items():
                    if a in cargas or a not in (plan.get('feeders') or []):
                        continue
                    for c in elm.GetObjs('ElmLod'):
                        base_scale.setdefault(clave_pf(c), float(getattr(c, 'scale0', 1.0) or 1.0))
                        c.scale0 = base_scale[clave_pf(c)] * factor
                ldf.scLoadFac = float(original)
            else:
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
                _anotar_la_red(informe, fila, lectura, barras)
            else:
                fila['problemas'] = [{'tipo': 'flujo', 'elemento': 'red', 'causa': 'no_converge',
                                      'evidencia': 'el flujo no converge con esta demanda'}]
            informe['anios'].append(fila)
    finally:
        ldf.scLoadFac = original
        for elm in elms.values():
            for c in elm.GetObjs('ElmLod'):
                if clave_pf(c) in base_scale:
                    c.scale0 = base_scale[clave_pf(c)]
    if por_alim:
        informe['tasa_por_alimentador'] = por_alim
    return informe, 0


def resumen_de_la_red(tensiones: dict, barras: dict, fps: dict, km_de: dict) -> tuple[dict, list[dict]]:
    """La tensión por alimentador y por barra de baja de cada SED (072:RF-16).

    La tensión mínima global se repetía en cada alimentador de F03, y el DGS sí crea una barra
    ``{sed}_BT`` por SED: con la barra se puede decir de qué alimentador o SED es cada medida.
    """
    por_alim: dict[str, dict] = {}
    baja: list[dict] = []
    for ident, u in tensiones.items():
        b = barras.get(ident)
        if b is None:
            continue
        a = b['alimentador']
        fila = por_alim.setdefault(a, {'kv': None, 'vm_min': None, 'fp': fps.get(a), 'km': km_de.get(a)})
        if (b['kv'] or 0) >= 1:
            fila['kv'] = max(fila['kv'] or 0, b['kv'])
            fila['vm_min'] = min(fila['vm_min'] if fila['vm_min'] is not None else u, u)
        else:
            baja.append({'sed': b['nombre'].removesuffix('_BT'), 'alimentador': a, 'kv': b['kv'], 'vm': u})
    return por_alim, baja


def _anotar_la_red(informe: dict, fila: dict, lectura: dict, barras: dict) -> None:
    """F03, F04 y F05 de un año; las barras de baja solo en el primero, que es el diagnóstico de F04."""
    flujo = lectura['flujo']
    # F05 y la evaluación con y sin proyecto (072:RF-14): sin dato, queda vacío y se nombra.
    fila['perdidas_kw'] = ((flujo.get('perdidas') or {}).get('valores') or {}).get('total')
    fila['por_alimentador'], baja = resumen_de_la_red(flujo['tensiones']['valores'], barras,
                                                      flujo['balance'].get('fp_cabeceras') or {},
                                                      informe.get('km_por_alimentador') or {})
    if not informe['anios']:
        fila['sed_bt'] = baja


def obras_del_anio(obras: list[dict], anio: int) -> tuple[list[str], list[str]]:
    """Las variaciones de obra que ya entraron en ``anio`` y las que aún no (072:RF-12).

    Cada año conserva las obras de los anteriores. La copia de «Con proyecto» las trae todas: sin esto,
    el año 04 se calculaba con las obras del año 16 y parecía resuelto antes de construirlas.
    """
    entrada: dict[str, int] = {}
    for o in obras:
        nombre, a = str(o['variacion']), int(o['anio'])
        entrada[nombre] = min(a, entrada.get(nombre, a))
    return sorted(n for n, a in entrada.items() if a <= anio), sorted(n for n, a in entrada.items() if a > anio)


def _con_obras_del_anio(app, proyecto, raiz, caso, plan, anio, lim, barras) -> dict:
    """«Con proyecto» de un año con sus obras: las variaciones son del caso copiado, no del proyecto.

    Lo aplicado se relee de DIgSILENT en vez de suponerlo, y una variación que ya no exista se nombra:
    el operador pudo borrarla, y eso no invalida el año (cambios manuales: aviso, no bloqueo).
    """
    caso.Activate()
    carpeta = app.GetProjectFolder('scheme')
    todas = {v.loc_name: v for v in (carpeta.GetContents('*.IntScheme', 1) if carpeta else [])}
    entran, salen = obras_del_anio(plan['obras_por_anio'], anio)
    activas = {v.loc_name for v in (app.GetActiveNetworkVariations() or [])}
    for nombre in salen:
        if nombre in activas and nombre in todas:
            todas[nombre].Deactivate()
    for nombre in entran:
        if nombre not in activas and nombre in todas:
            todas[nombre].Activate()
    activas = {v.loc_name for v in (app.GetActiveNetworkVariations() or [])}
    out = {'obras': sorted(n for n in entran if n in activas), 'sin_aplicar': sorted(n for n in entran if n not in activas)}
    flujo = flujo_de_carga(app)
    out['converge'] = flujo['converged']
    if flujo['converged']:
        lectura = {'flujo': resultados(app, proyecto, raiz, list(plan.get('feeders') or [])),
                   'topologia': {'barras': barras}}
        out['problemas'] = [{'causa': p.causa, 'elemento': p.elemento} for p in diagnosticar(lectura, **lim)]
        out['perdidas_kw'] = ((lectura['flujo'].get('perdidas') or {}).get('valores') or {}).get('total')
    return out


def _por_anios(app, plan, informe, proyecto, raiz, lim, barras, de_linea, por_nombre, tasa, por_alim):
    """030:RF-1 a RF-7: cada año en su carpeta, con sus casos y escenarios, y su diagnóstico en el
    «Sin proyecto» del año. El caso que estaba activo vuelve a estarlo al terminar (RF-6)."""
    inicial = app.GetActiveStudyCase()
    origenes = origenes_del_pide(app, plan)
    if 'sin' not in origenes:
        return {**informe, 'error': 'el proyecto no tiene «Sin proyecto» para copiar a los años del PIDE'}, 2
    feeders = set(plan.get('feeders') or [])
    nuevas = cargas_nuevas_del_proyecto(app, plan.get('cargas_nuevas'))           # RF-9, RF-11
    if nuevas:
        informe['cargas_nuevas'] = nuevas
    origenes['sin'].Activate()
    elms = [e for e in proyecto.GetContents('*.ElmFeeder', 1) if e.loc_name in feeders]
    base = {clave_pf(c): float(getattr(c, 'scale0', 1.0) or 1.0) for e in elms for c in e.GetObjs('ElmLod')}
    try:
        for anio in plan.get('anios') or [0]:
            def factor_de(elm, anio=anio):
                if elm.loc_name not in feeders:
                    return None
                return (1 + por_alim.get(elm.loc_name, tasa)) ** int(anio)

            casos = casos_del_anio(app, origenes, int(anio), factor_de, base, nuevas)
            casos['sin']['objeto'].Activate()
            flujo = flujo_de_carga(app)
            fila = {'anio': int(anio), 'factor': (1 + tasa) ** int(anio), 'converge': flujo['converged'],
                    'casos': {r: {k: v for k, v in c.items() if k != 'objeto'} for r, c in casos.items()}}   # RF-7
            if flujo['converged']:
                lectura = {'flujo': resultados(app, proyecto, raiz, list(plan.get('feeders') or [])),
                           'topologia': {'barras': barras}}
                fila['problemas'] = []
                for p in diagnosticar(lectura, **lim):
                    sitio = por_nombre.get(p.elemento) or {}
                    linea = p.elemento.removesuffix('.ElmLne')
                    fila['problemas'].append({**p.__dict__, 'kv': sitio.get('kv'),
                                              'alimentador': sitio.get('alimentador') or de_linea.get(linea)})
                tensiones = lectura['flujo']['tensiones']['valores']
                fila['vm_min'] = min(tensiones.values()) if tensiones else None
                fila['cabeceras_kw'] = lectura['flujo']['balance']['valores']['cabeceras']
                _anotar_la_red(informe, fila, lectura, barras)
            else:
                fila['problemas'] = [{'tipo': 'flujo', 'elemento': 'red', 'causa': 'no_converge',
                                      'evidencia': 'el flujo no converge con esta demanda'}]
            if plan.get('obras_por_anio') and 'con' in casos:
                fila['con_proyecto'] = _con_obras_del_anio(app, proyecto, raiz, casos['con']['objeto'], plan,
                                                           int(anio), lim, barras)
            informe['anios'].append(fila)
    finally:
        # RF-6: los casos del proyecto con su demanda de antes. En DIgSILENT cada escenario guarda
        # la suya y esto no cambia nada; si algo escribió fuera de su escenario, lo deshace.
        for origen in origenes.values():
            origen.Activate()
            for e in elms:
                for c in e.GetObjs('ElmLod'):
                    if clave_pf(c) in base and float(getattr(c, 'scale0', 1.0) or 1.0) != base[clave_pf(c)]:
                        c.scale0 = base[clave_pf(c)]
        if inicial is not None:
            inicial.Activate()
    if por_alim:
        informe['tasa_por_alimentador'] = por_alim
    return informe, 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Cada año del horizonte del PIDE en DIgSILENT, con la '
                                            'demanda escalada y el diagnóstico de la norma (spec 024)')
    p.add_argument('--plan', required=True)
    p.add_argument('--output-json', required=True)
    p.add_argument('--cancel-file', help='PIDE anual: cancelar entre etapas y restituir antes de salir')
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    salida = Path(args.output_json)
    flag = Path(args.cancel_file) if args.cancel_file else None
    if flag is not None:
        print('PIDE: protocolo de cancelación cooperativa listo; la restitución precede a la salida.', flush=True)
        if flag.exists():
            salida.write_text(json.dumps({'project': plan.get('project'), 'modo': plan.get('modo'),
                'estado': 'cancelado', 'anios': [], 'aceptacion_nativa': False,
                'restitucion': {'ok': True, 'diferencias': [], 'sin_abrir_motor': True}},
                ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            return 0
    blocked = native_action_block_report(plan, 'pide')
    if blocked:
        salida.write_text(json.dumps(blocked, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(blocked['error'])
        return 2
    from convertersmartgrid.pf_arnes import PFNoDisponible, conectar

    try:
        app = conectar('pide_pf.py')
    except PFNoDisponible as exc:
        print(f'ERROR: {exc}')
        return 3
    try:
        informe, codigo = ejecutar(app, plan, cancelado=(lambda: flag.exists()) if flag else None)
    except Exception as exc:  # noqa: BLE001 - el informe queda siempre escrito (008:RF-17)
        informe, codigo = {'project': plan.get('project'), 'error': repr(exc),
                           'traza': traceback.format_exc()}, 1
    salida.write_text(json.dumps(informe, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"PIDE de {plan.get('project')}: código {codigo}")
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
