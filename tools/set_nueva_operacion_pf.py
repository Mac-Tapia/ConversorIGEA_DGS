#!/usr/bin/env python
"""Diagnostica y refuerza una SET existente sin recrearla ni reducir sus cargas.

Uso: python tools/set_nueva_operacion_pf.py --plan plan.json --output-json informe.json
El plan firmado por la web usa accion diagnostico/evaluar/aplicar. Las referencias
son rutas nativas completas del proyecto vinculado; cada cambio estructural se
graba en una variación nueva. La operación usa una copia propia del escenario.
Evaluar restaura el estado y elimina solamente los objetos creados por esta llamada.
Aplicar conserva el candidato únicamente cuando ambos flujos cumplen y la relectura
confirma las cargas, los cambios y su aislamiento. No realiza aceptación en otros
motores, ni cambia coordenadas, demandas o la potencia de la SET.
"""
from __future__ import annotations

import argparse
import json
import math
import traceback
import uuid
from pathlib import Path

from cargas_pf import (
    BASE_RECORTADA,
    SUFIJO_PF,
    activar_proyecto,
    crear_variacion,
    entradas_del_indice,
    escribir_carga,
    flujo_de_carga,
    nombre_pf,
)
from casos_pf import (
    anio_del_plan,
    casos_del_proyecto,
    nombre_cargas_nuevas,
    nombre_caso,
)
from estudios_pf import geografia, resumen_proyecto
from obras_pf import construir_salida_set_existente, validar_salida_set_existente

from convertersmartgrid.native_action import native_action_block_report

CLASES_RED = ('ElmTerm', 'ElmLne', 'ElmTr2', 'ElmTr3', 'ElmLod', 'ElmXnet',
              'ElmSym', 'ElmGenstat', 'ElmShnt', 'ElmCoup', 'StaSwitch', 'ElmFeeder')
CAMBIOS = {'ElmLne': {'nlnum', 'typ_id', 'outserv'},
           'ElmTr2': {'ntnum', 'typ_id', 'outserv', 'nntap'},
           'ElmSym': {'outserv'}, 'ElmGenstat': {'outserv'}, 'ElmShnt': {'outserv'}}
AJUSTES = {'iopt_lev', 'iopt_pq', 'iopt_at'}
ATRIBUTOS = {
    'ElmTerm': ('uknom', 'iUsage', 'outserv', 'GPSlat', 'GPSlon', 'm:u',
                'm:u:A', 'm:u:B', 'm:u:C'),
    'ElmLne': ('outserv', 'nlnum', 'dline', 'fline', 'c:loading', 'm:I:bus1', 'm:I:bus2'),
    'ElmTr2': ('outserv', 'ntnum', 'nntap', 'ntrcn', 'usetp', 'c:loading',
               'm:Ssum:bushv', 'm:Ssum:buslv', 'm:I:bushv', 'm:I:buslv'),
    'ElmTr3': ('outserv', 'ntnum', 'nntap', 'c:loading'),
    'ElmLod': ('outserv', 'mode_inp', 'plini', 'qlini', 'plinir', 'plinis', 'plinit',
               'qlinir', 'qlinis', 'qlinit', 'slini', 'coslini', 'scale0', 'i_scale',
               'i_sym', 'phtech', 'aP', 'bP', 'cP', 'eP', 'aQ', 'bQ', 'cQ', 'eQ'),
    'ElmXnet': ('outserv', 'usetp', 'bustp', 'snss', 'snssmin', 'rntxn'),
    'ElmSym': ('outserv', 'pgini', 'qgini', 'sgn', 'cosn', 'usetp'),
    'ElmGenstat': ('outserv', 'pgini', 'qgini', 'sgn', 'cosn', 'usetp'),
    'ElmShnt': ('outserv', 'ncapa', 'qcapn', 'ushnm', 'shtype'),
    'ElmCoup': ('outserv', 'on_off'), 'StaSwitch': ('outserv', 'on_off'),
    'ElmFeeder': ('iorient',),
}
TIPOS = {
    'TypLne': ('uline', 'sline', 'InomAir', 'qurs', 'rline', 'xline', 'rline0',
               'xline0', 'bline', 'bline0', 'frnom', 'nlnph', 'systp', 'Ithr'),
    'TypTr2': ('strn', 'utrn_h', 'utrn_l', 'uktr', 'pcutr', 'pfe', 'curmg',
               'tr2cn_h', 'tr2cn_l', 'nt2ag', 'itapch', 'tap_side', 'dutap',
               'ntpmn', 'ntpmx', 'nntap0', 'frnom'),
    'TypLod': ('aP', 'bP', 'cP', 'eP', 'aQ', 'bQ', 'cQ', 'eQ', 'kpf', 'kqf',
               'loddy', 'phtech', 'lodzip', 'kpu0', 'kqu0'),
}
REFERENCIAS = ('bus1', 'bus2', 'bushv', 'buslv', 'busmv', 'bus0', 'obj_id', 'typ_id')


def _ruta(obj):
    return obj.GetFullName() if obj is not None else None


def _leer(obj, atributo):
    try:
        valor = obj.GetAttribute(atributo)
    except Exception:  # noqa: BLE001 - atributo opcional según clase y versión nativa; se informa None
        return None
    if valor is None or isinstance(valor, (str, bool, int)):
        return valor
    if isinstance(valor, float):
        return valor if math.isfinite(valor) else None
    if hasattr(valor, 'GetFullName'):
        return _ruta(valor)
    if isinstance(valor, (list, tuple)):
        return [(_ruta(v) if hasattr(v, 'GetFullName') else v) for v in valor
                if v is None or isinstance(v, (str, bool, int, float)) or hasattr(v, 'GetFullName')]
    return None


def _datos(obj, campos):
    return {a: _leer(obj, a) for a in campos}


def _dentro(obj, proyecto):
    ruta, raiz = _ruta(obj), _ruta(proyecto)
    return bool(ruta and raiz and (ruta == raiz or ruta.startswith(raiz + '\\')))


def _esta_activo(app, obj):
    clase = obj.GetClassName()
    if clase == 'IntCase':
        activos = [app.GetActiveStudyCase()]
    elif clase == 'IntScenario':
        activos = [app.GetActiveScenario()]
    elif clase == 'IntScheme':
        activos = app.GetActiveNetworkVariations() or []
    elif clase == 'IntPrj':
        activos = [app.GetActiveProject()]
    else:
        raise ValueError(f'clase no admitida para activar: {clase}')
    return _ruta(obj) in {_ruta(o) for o in activos if o is not None}


def _activar(app, obj):
    # PowerFactory devuelve 1 al pedir activar un caso ya activo. El código de
    # retorno no sustituye la lectura de identidad nativa; sus wrappers pueden variar.
    if _esta_activo(app, obj):
        return
    rc = obj.Activate()
    if rc not in (0, 1, None) or not _esta_activo(app, obj):
        raise RuntimeError(f'no se pudo activar {_ruta(obj)}: {rc}')


def validar_plan(plan):
    """Lista cerrada: no admite demandas, coordenadas, potencias ni tipos editados."""
    if not isinstance(plan, dict) or not isinstance(plan.get('project'), str) or not plan['project'].strip():
        raise ValueError('falta el proyecto vinculado')
    if plan.get('accion', 'diagnostico') not in ('diagnostico', 'evaluar', 'aplicar'):
        raise ValueError('accion no válida')
    for clave in ('sincronizar_cargas', 'reabrir', 'conciliar_fases', 'verificar_flujos'):
        if clave in plan and not isinstance(plan[clave], bool):
            raise TypeError(f'{clave} debe ser booleano')
    if plan.get('accion') == 'aplicar' and not plan.get('reabrir', True):
        raise ValueError('aplicar requiere reabrir=True para comprobar la persistencia')
    if plan.get('verificar_flujos'):
        if plan.get('accion', 'diagnostico') != 'diagnostico':
            raise ValueError('verificar_flujos solo se admite en diagnostico')
        if any(plan.get(c) for c in ('cambios', 'salidas', 'desactivar_variaciones', 'ajustes_flujo',
                                      'conciliar_fases', 'sincronizar_cargas')):
            raise ValueError('verificar_flujos no admite obras, ajustes ni sincronizaciones')
    previstas = plan.get('nuevas')
    if (plan.get('accion', 'diagnostico') != 'diagnostico' or plan.get('verificar_flujos')) and not previstas:
        raise ValueError('falta el manifiesto nuevas con todas las cargas previstas')
    if previstas is not None:
        if not isinstance(previstas, list):
            raise TypeError('nuevas debe ser una lista')
        for registro in previstas:
            if not isinstance(registro, dict):
                raise TypeError('cada carga prevista debe ser un objeto')
            if any(not isinstance(registro.get(a), str) or not registro[a] for a in ('sed', 'variacion', 'barra', 'alimentador')):
                raise ValueError('cada carga prevista necesita sed, variacion, barra y alimentador explícitos')
            if registro['alimentador'] not in (plan.get('feeders') or []):
                raise ValueError('carga prevista de un alimentador ajeno al contexto firmado')
            if any(isinstance(registro.get(a), bool) or not isinstance(registro.get(a), (int, float))
                   or not math.isfinite(registro[a]) for a in ('kw', 'kvar')):
                raise ValueError('cada carga prevista requiere kW/kvar nominales finitos')
            if registro['kw'] <= 0:
                raise ValueError('la carga prevista necesita potencia activa positiva')
    ajustes = plan.get('ajustes_flujo') or {}
    if not isinstance(ajustes, dict):
        raise TypeError('ajustes_flujo debe ser un objeto')
    if set(ajustes) - AJUSTES:
        raise ValueError('ajustes_flujo solo admite iopt_lev, iopt_pq, iopt_at')
    if any(type(v) is not int for v in ajustes.values()):
        raise TypeError('los ajustes de flujo deben ser enteros 0/1')
    if any(v not in (0, 1) for v in ajustes.values()):
        raise ValueError('los ajustes de flujo deben ser enteros 0/1')
    cambios = plan.get('cambios') or []
    if not isinstance(cambios, list):
        raise TypeError('cambios debe ser una lista')
    for c in cambios:
        if not isinstance(c, dict) or set(c) - {'clase', 'elemento', 'atributos'}:
            raise ValueError('cada cambio requiere clase, elemento y atributos')
        clase, ruta, attrs = c.get('clase'), c.get('elemento'), c.get('atributos')
        if clase not in CAMBIOS or not isinstance(ruta, str) or '.IntPrj\\' not in ruta or not ruta.endswith('.' + clase):
            raise ValueError('el cambio requiere clase permitida y ruta nativa completa')
        if not isinstance(attrs, dict) or not attrs or set(attrs) - CAMBIOS[clase]:
            raise ValueError('atributos del cambio fuera de la lista permitida')
        for a, v in attrs.items():
            if a == 'typ_id':
                if not isinstance(v, str) or '.IntPrj\\' not in v or not v.endswith('.' + ('TypLne' if clase == 'ElmLne' else 'TypTr2')):
                    raise ValueError('typ_id requiere ruta completa del catálogo del proyecto')
            elif type(v) is not int or (v not in (0, 1) if a == 'outserv' else
                                       not -100 <= v <= 100 if a == 'nntap' else not 1 <= v <= 100):
                raise ValueError(f'{a} requiere entero físico válido')
    salidas = plan.get('salidas') or []
    if not isinstance(salidas, list):
        raise TypeError('salidas debe ser una lista')
    for salida in salidas:
        if not isinstance(salida, dict):
            raise TypeError('cada salida debe ser un objeto')
        for campo, clase in [('origen', 'ElmTerm'), ('destino', 'ElmTerm'), ('tipo', 'TypLne')]:
            ruta = salida.get(campo)
            if not isinstance(ruta, str) or '.IntPrj\\' not in ruta or not ruta.endswith('.' + clase):
                raise ValueError(f'la salida requiere {campo} por ruta nativa completa')
        if type(salida.get('circuitos')) is not int or salida['circuitos'] < 1:
            raise ValueError('la salida necesita circuitos enteros positivos')
        if not isinstance(salida.get('nombre'), str) or not salida['nombre']:
            raise ValueError('falta el nombre explícito de la salida')
        if not isinstance(salida.get('ruta'), list) or len(salida['ruta']) < 2:
            raise ValueError('la salida requiere la polilínea GPS explícita')
    desactivar = plan.get('desactivar_variaciones') or []
    if not isinstance(desactivar, list) or any(not isinstance(v, str) or not v for v in desactivar):
        raise ValueError('desactivar_variaciones requiere nombres o rutas exactos')
    if any(not v.rsplit('\\', 1)[-1].startswith('Obra_') for v in desactivar):
        raise ValueError('solo se pueden desactivar variaciones de obra explícitas')
    limites = plan.get('limites') or {}
    if not isinstance(limites, dict) or set(limites) - {'tension_min_pu', 'tension_max_pu', 'cargabilidad_max_pct', 'origen'}:
        raise ValueError('límites no válidos')
    for k, default in [('tension_min_pu', .95), ('tension_max_pu', 1.05), ('cargabilidad_max_pct', 100.)]:
        v = limites.get(k, default)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            raise ValueError(f'límite {k} no válido')
    if limites.get('tension_min_pu', .95) >= limites.get('tension_max_pu', 1.05):
        raise ValueError('banda de tensión vacía')
    if (limites.get('tension_min_pu', .95) < .95 or limites.get('tension_max_pu', 1.05) > 1.05
            or limites.get('cargabilidad_max_pct', 100.) > 100.):
        raise ValueError('los límites no pueden relajar 0,95–1,05 pu y 100 %')
    return plan


class _RedDelProyecto:
    """Filtra resultados del motor por ascendencia nativa, no por nombres de red."""
    def __init__(self, app, proyecto):
        self.app, self.proyecto = app, proyecto

    def GetCalcRelevantObjects(self, patron):
        return [o for o in (self.app.GetCalcRelevantObjects(patron) or []) if _dentro(o, self.proyecto)]

    def __getattr__(self, nombre):
        return getattr(self.app, nombre)


def _inventario(app, proyecto):
    netdat = app.GetProjectFolder('netdat')
    objetos = {}
    for clase in CLASES_RED:
        leidos = list(app.GetCalcRelevantObjects(f'*.{clase}') or [])
        if netdat is not None:
            leidos += list(netdat.GetContents(f'*.{clase}', 1) or [])
        objetos[clase] = {_ruta(o): o for o in leidos if _dentro(o, proyecto)}
    return objetos


def _ficha(obj):
    clase = obj.GetClassName()
    fila = {'nombre': obj.loc_name, 'clase': clase, 'ruta': _ruta(obj),
            **_datos(obj, ATRIBUTOS.get(clase, TIPOS.get(clase, ())))}
    if clase in ('ElmTerm', 'ElmLne', 'ElmTr2', 'ElmTr3', 'ElmLod'):
        try:
            fila['resultados_disponibles'] = bool(obj.HasResults())
        except Exception:  # noqa: BLE001 - API opcional; se conserva la ausencia en el diagnóstico
            fila['resultados_disponibles'] = None
    if clase.startswith('Elm'):
        fila.update(_datos(obj, ('m:Psum:bus1', 'm:Qsum:bus1', 'm:Psum:bushv',
                                'm:Qsum:bushv', 'm:Psum:buslv', 'm:Qsum:buslv')))
    conexiones = {}
    for a in REFERENCIAS:
        try:
            ref = obj.GetAttribute(a)
        except Exception:  # noqa: BLE001, S112 - las conexiones disponibles dependen de cada clase nativa
            continue
        if ref is None or not hasattr(ref, 'GetFullName'):
            continue
        terminal = getattr(ref, 'cterm', None) if a != 'typ_id' else None
        conexiones[a] = {'ruta': _ruta(ref), 'nombre': ref.loc_name,
                         'terminal': _ruta(terminal), 'nombre_terminal': getattr(terminal, 'loc_name', None)}
        if a == 'typ_id':
            conexiones[a]['datos'] = _datos(ref, TIPOS.get(ref.GetClassName(), ()))
    fila['referencias'] = conexiones
    return fila


def _catalogo(app, proyecto):
    equip = app.GetProjectFolder('equip')
    return {clase: [_ficha(o) for o in sorted((equip.GetContents(f'*.{clase}', 1) or []), key=_ruta)
                    if _dentro(o, proyecto)] if equip is not None else []
            for clase in TIPOS}


def _estado_caso(app, proyecto):
    inventario = _inventario(app, proyecto)
    return {'ruta': _ruta(app.GetActiveStudyCase()), 'escenario': _ruta(app.GetActiveScenario()),
            'resultados_vigentes': bool(app.IsLdfValid()),
            'fecha_estudio': _leer(app.GetActiveStudyCase(), 'iStudyTime'),
            'ajustes_flujo': _datos(app.GetFromStudyCase('ComLdf'), (*sorted(AJUSTES), 'iopt_net', 'iopt_fls')),
            'variaciones_activas': [{'nombre': v.loc_name, 'ruta': _ruta(v),
                'etapas': [{'ruta': _ruta(e), 'tAcTime': _leer(e, 'tAcTime')}
                           for e in v.GetContents('*.IntSstage') or []]}
                for v in app.GetActiveNetworkVariations() or []],
            'objetos': {c: [_ficha(o) for o in sorted(xs.values(), key=_ruta)] for c, xs in inventario.items()},
            'catalogo': _catalogo(app, proyecto)}


def _casos(app, plan):
    anio = anio_del_plan(plan)
    roles = casos_del_proyecto(app, anio)
    deseados = [nombre_caso('sin', anio), nombre_cargas_nuevas(anio), nombre_caso('con', anio)]
    disponibles = app.GetProjectFolder('study').GetContents('*.IntCase', 1)
    out = {}
    for nombre in deseados:
        candidatos = [c for c in disponibles if c.loc_name == nombre]
        if len(candidatos) > 1:
            raise ValueError(f'caso ambiguo: {nombre}')
        if candidatos:
            out[nombre] = candidatos[0]
    con = roles.get('con') or out.get(nombre_caso('con', anio))
    if con is None:
        raise ValueError('no existe el caso Con proyecto vinculado')
    return out, con


def diagnosticar(app, proyecto, casos):
    out = {}
    for nombre, caso in casos.items():
        _activar(app, caso)
        out[nombre] = _estado_caso(app, proyecto)
    nombres = list(out)
    diferencias = {}
    for a in nombres:
        va = {v['ruta'] for v in out[a]['variaciones_activas'] if v['nombre'].startswith('Carga_')}
        for b in nombres:
            if a < b:
                vb = {v['ruta'] for v in out[b]['variaciones_activas'] if v['nombre'].startswith('Carga_')}
                diferencias[f'{a} / {b}'] = {'solo_primero': sorted(va - vb), 'solo_segundo': sorted(vb - va)}
    return out, diferencias


def validar_resultados(flujo, resumen, objetos, limites):
    """Convergencia, cobertura y consumo por carga; ningún nulo se interpreta como cero."""
    razones = []
    if not flujo.get('converged'):
        razones.append('flujo no convergido o no válido')
    if not resumen.get('cobertura_completa') or not resumen.get('balance_completo') or not resumen.get('cantidad_barras'):
        razones.append('cobertura o balance incompleto')
    barras_activas = sum(not o.get('outserv') for o in objetos.get('ElmTerm', []))
    if barras_activas != resumen.get('cantidad_barras'):
        razones.append('el resumen no cubre todas las barras activas del inventario')
    vmin, vmax = limites.get('tension_min_pu', .95), limites.get('tension_max_pu', 1.05)
    carga = limites.get('cargabilidad_max_pct', 100.)
    for clase, filas in objetos.items():
        for o in filas:
            if o.get('outserv'):
                continue
            ruta = o['ruta']
            if o.get('resultados_disponibles') is False:
                razones.append(f'{ruta}: el motor indica que no tiene resultados')
            if clase == 'ElmTerm':
                u = o.get('m:u')
                if u is None or not vmin <= u <= vmax:
                    razones.append(f'{ruta}: tensión ausente o fuera de banda')
                fases = [o.get(f'm:u:{f}') for f in 'ABC']
                if any(v is not None and not vmin <= v <= vmax for v in fases):
                    razones.append(f'{ruta}: tensión de fase fuera de banda')
            if clase in ('ElmLne', 'ElmTr2', 'ElmTr3'):
                valor = o.get('c:loading')
                if valor is None or valor > carga:
                    razones.append(f'{ruta}: cargabilidad ausente o sobre el límite')
            if clase == 'ElmLod':
                p, q, escala = o.get('plini'), o.get('qlini'), o.get('scale0')
                if p is None or q is None or escala is None:
                    razones.append(f'{ruta}: demanda escrita incompleta')
                    continue
                for attr, nominal in [('m:Psum:bus1', p * escala), ('m:Qsum:bus1', q * escala)]:
                    real = o.get(attr)
                    if real is None or not math.isfinite(real) or abs(real - nominal) > max(.001, abs(nominal) * .005):
                        razones.append(f'{ruta}: {attr} distinto de la demanda escrita por escala')
    if not objetos.get('ElmLod') or not objetos.get('ElmTerm'):
        razones.append('faltan cargas o barras en el inventario')
    return not razones, razones


def _estudiar(app, proyecto, limites):
    ldf = app.GetFromStudyCase('ComLdf')
    inicial = _leer(ldf, 'iopt_net')
    estudios = {}
    try:
        for nombre, modo in [('flujo', 0), ('flujo_desequilibrado', 1)]:
            print(f'Flujo nativo: {nombre}', flush=True)
            ldf.SetAttribute('iopt_net', modo)
            flujo = flujo_de_carga(app)
            proxy = _RedDelProyecto(app, proyecto)
            resumen = resumen_proyecto(proxy) if flujo['converged'] else {}
            objetos = _estado_caso(app, proyecto)['objetos']
            ok, razones = validar_resultados(flujo, resumen, objetos, limites)
            efectivo = _leer(ldf, 'iopt_net')
            if efectivo != modo:
                razones.append('el motor cambió el modo de flujo solicitado')
                ok = False
            estudios[nombre] = {'flujo': flujo, 'iopt_net': efectivo, 'red_proyecto': resumen,
                'geo_proyecto': geografia(None, proxy) if flujo['converged'] else {},
                'objetos': objetos, 'aceptada': ok, 'incumplimientos': razones}
    finally:
        if inicial is not None:
            ldf.SetAttribute('iopt_net', inicial)
    return estudios


def _resolver_cambios(app, proyecto, cambios):
    inventario = _inventario(app, proyecto)
    catalogo = {c: {_ruta(o): o for o in (app.GetProjectFolder('equip').GetContents(f'*.{c}', 1) or [])
                    if _dentro(o, proyecto)} for c in ('TypLne', 'TypTr2')}
    resueltos = []
    for cambio in cambios:
        obj = inventario.get(cambio['clase'], {}).get(cambio['elemento'])
        if obj is None:
            raise ValueError(f'no existe el elemento exacto en el proyecto: {cambio["elemento"]}')
        attrs = dict(cambio['atributos'])
        if 'nntap' in attrs:
            if 'typ_id' in attrs:
                raise ValueError('la toma fija no se combina con un cambio de tipo en la misma obra')
            tipo_actual = getattr(obj, 'typ_id', None)
            campos = {a: _leer(tipo_actual, a) for a in ('itapch', 'dutap', 'ntpmn', 'ntpmx')}
            if (campos['itapch'] != 1 or any(v is None or not isinstance(v, (int, float))
                                           or not math.isfinite(v) for v in campos.values())
                    or campos['dutap'] <= 0 or campos['ntpmn'] > campos['ntpmx']
                    or not campos['ntpmn'] <= attrs['nntap'] <= campos['ntpmx']):
                raise ValueError(f'toma fija fuera de la capacidad física del cambiador: {_ruta(obj)}; {campos}')
        if 'typ_id' in attrs:
            clase = 'TypLne' if cambio['clase'] == 'ElmLne' else 'TypTr2'
            tipo = catalogo[clase].get(attrs['typ_id'])
            if tipo is None:
                raise ValueError(f'tipo ausente o ajeno al catálogo del proyecto: {attrs["typ_id"]}')
            if cambio['clase'] == 'ElmTr2':
                for k in ('utrn_h', 'utrn_l'):
                    previo = _leer(getattr(obj, 'typ_id', None), k)
                    nuevo = _leer(tipo, k)
                    if previo is None or nuevo is None or abs(previo - nuevo) > .05:
                        raise ValueError('el tipo de transformador debe conservar sus tensiones')
            else:
                uline = _leer(tipo, 'uline')
                tensiones = [_leer(getattr(getattr(obj, a, None), 'cterm', None), 'uknom')
                             for a in ('bus1', 'bus2')]
                if uline is None or any(v is None or uline + .05 < v for v in tensiones):
                    raise ValueError('el conductor no acredita la tensión de ambos terminales')
            attrs['typ_id'] = tipo
        # La SET existente tiene prioridad sobre cualquier propuesta accidental.
        if cambio['clase'] == 'ElmTr2':
            hv = getattr(getattr(obj, 'bushv', None), 'cterm', None)
            if (_leer(hv, 'uknom') or 0) >= 40 and set(attrs) & {'ntnum', 'typ_id'}:
                raise ValueError('no se permite redimensionar el transformador de la SET')
        resueltos.append((obj, attrs))
    return resueltos


def _resolver_salidas(app, proyecto, salidas):
    barras = _inventario(app, proyecto)['ElmTerm']
    equip = app.GetProjectFolder('equip')
    tipos = {_ruta(o): o for o in equip.GetContents('*.TypLne', 1) or [] if _dentro(o, proyecto)} if equip else {}
    nombres, cubiculos, resueltas = set(), set(), []
    for salida in salidas:
        origen, destino, tipo = barras.get(salida['origen']), barras.get(salida['destino']), tipos.get(salida['tipo'])
        if origen is None or destino is None or tipo is None:
            raise ValueError('una referencia exacta de la salida no pertenece al inventario/catálogo del proyecto')
        datos = validar_salida_set_existente(proyecto, origen, destino, tipo, salida['nombre'],
                                             salida['circuitos'], salida['ruta'])
        if datos['nombre'] in nombres:
            raise ValueError('dos salidas del lote comparten nombre')
        for barra, nombre in zip((origen, destino), datos['nombres_cubiculos']):
            identidad = (_ruta(barra), nombre)
            if identidad in cubiculos:
                raise ValueError('dos salidas del lote comparten cubículo')
            cubiculos.add(identidad)
        nombres.add(datos['nombre'])
        resueltas.append((salida, origen, destino, tipo, datos))
    return resueltas


def _verificar_salida(app, proyecto, datos):
    inventario = _inventario(app, proyecto)
    linea, feeder = inventario['ElmLne'].get(datos['linea']), inventario['ElmFeeder'].get(datos['feeder'])
    if linea is None or feeder is None:
        raise RuntimeError('la relectura perdió la línea o el alimentador nuevo')
    if (_leer(linea, 'typ_id') != datos['tipo'] or _leer(linea, 'nlnum') != datos['circuitos']
            or _leer(linea, 'outserv') != 0
            or not math.isclose(_leer(linea, 'dline') or 0, datos['longitud_km'], rel_tol=1e-6)):
        raise RuntimeError('la salida no conserva tipo, circuitos, estado o longitud')
    gps = linea.GetAttribute('GPScoords')
    if len(gps) != len(datos['GPScoords']) or any(
            not math.isclose(v, w, rel_tol=0, abs_tol=1e-8)
            for a, b in zip(gps, datos['GPScoords']) for v, w in zip(a, b)):
        raise RuntimeError('la salida no conserva su polilínea GPS')
    for lado, (ruta_barra, ruta_cub) in enumerate(zip((datos['origen'], datos['destino']), datos['cubiculos'])):
        barra = inventario['ElmTerm'].get(ruta_barra)
        cubs = {_ruta(o): o for o in barra.GetContents('*.StaCubic') or []} if barra else {}
        cub = cubs.get(ruta_cub)
        if cub is None or _leer(cub, 'obj_id') != datos['linea'] or _leer(cub, 'obj_bus') != lado or _ruta(cub.cterm) != ruta_barra:
            raise RuntimeError('la salida no conserva los dos cubículos y sus terminales')
    if _leer(feeder, 'obj_id') != datos['cubiculos'][0] or _leer(feeder, 'iorient') != 0:
        raise RuntimeError('el alimentador nuevo no conserva su cabecera y orientación')
    return {'linea': datos['linea'], 'feeder': datos['feeder'], 'cubiculos': datos['cubiculos'], 'verificada': True}


def _firma_cargas(app, proyecto):
    """Identidad y demanda escrita: el refuerzo no puede borrar ni reducir una carga."""
    return {_ruta(o): _datos(o, ATRIBUTOS['ElmLod'])
            for o in _inventario(app, proyecto)['ElmLod'].values()}


def _conciliar_fases(app, proyecto, copia):
    """Reconcilia fases con P/Q calibrados únicamente en la copia explícita activa."""
    if copia is None or _ruta(app.GetActiveScenario()) != _ruta(copia):
        raise ValueError('conciliar fases requiere la copia propia activa')
    fijos = ('plini', 'qlini', 'scale0', 'i_scale', 'mode_inp', 'i_sym', 'outserv')
    campos = (*fijos, 'plinir', 'plinis', 'plinit', 'qlinir', 'qlinis', 'qlinit')
    pendientes = []
    cargas = _inventario(app, proyecto)['ElmLod'].values()
    objetivo_kw = 0.
    for obj in cargas:
        p, q, escala = _leer(obj, 'plini'), _leer(obj, 'qlini'), _leer(obj, 'scale0')
        if _leer(obj, 'outserv'):
            continue
        if p is None or q is None or escala is None:
            raise ValueError(f'demanda nominal incompleta para conciliar {_ruta(obj)}')
        objetivo_kw += p * escala * 1000
        if _leer(obj, 'i_sym') != 1:
            continue
        antes = _datos(obj, campos)
        fases_p, fases_q = ([antes['plini' + f] for f in 'rst'], [antes['qlini' + f] for f in 'rst'])
        if any(v is None for v in fases_p + fases_q):
            raise ValueError(f'entradas de fase incompletas en {_ruta(obj)}')
        sp, sq = sum(fases_p), sum(fases_q)
        if _igual_valor(sp, p) and _igual_valor(sq, q):
            continue
        if (abs(sp) < 1e-12 and abs(p) > 1e-12) or (abs(sq) < 1e-12 and abs(q) > 1e-12):
            raise ValueError(f'sin reparto de fases preservable en {_ruta(obj)}')
        pendientes.append((obj, antes, sp, sq))
    audit = []
    for obj, antes, sp, sq in pendientes:
        escribir_carga(obj, antes['plini'], antes['qlini'])
        despues = _datos(obj, campos)
        if any(not _igual_valor(antes[a], despues[a]) for a in fijos):
            raise RuntimeError(f'conciliar fases alteró datos nominales protegidos: {_ruta(obj)}')
        for prefijo, total, suma in [('plini', antes['plini'], sp), ('qlini', antes['qlini'], sq)]:
            valores = [despues[prefijo + f] for f in 'rst']
            if not _igual_valor(sum(valores), total):
                raise RuntimeError(f'las fases no reproducen el total calibrado: {_ruta(obj)}.{prefijo}')
            if abs(suma) > 1e-12 and any(
                    not _igual_valor(despues[prefijo + f], antes[prefijo + f] * total / suma) for f in 'rst'):
                raise RuntimeError(f'conciliar alteró el reparto relativo: {_ruta(obj)}.{prefijo}')
        audit.append({'ruta': _ruta(obj), 'antes': antes, 'despues': despues,
                      'sumas_antes': {'p': sp, 'q': sq},
                      'sumas_despues': {'p': sum(despues['plini' + f] for f in 'rst'),
                                        'q': sum(despues['qlini' + f] for f in 'rst')}})
    return {'escenario': _ruta(copia), 'cantidad': len(audit), 'demanda_objetivo_kw': objetivo_kw,
            'autoridad': 'plini/qlini calibrados; no se modifica el total ni la escala', 'cargas': audit}


def _base_nombre(nombre):
    return SUFIJO_PF.sub('', nombre)


def _terminal(obj, atributo):
    return getattr(getattr(obj, atributo, None), 'cterm', None)


def _camino_al_punto(carga, punto, variacion, inventario):
    """BT→transformador/cople de esa SED→ramal creado por su propia variación.

    El punto del registro es normalmente MT. No se busca un camino arbitrario por
    la red: solo el interior de su SED y una línea de la variación de esta carga.
    """
    inicio, destino = _ruta(_terminal(carga, 'bus1')), _ruta(punto)
    lineas_propias = {_base_nombre(o.loc_name)
                      for e in variacion.GetContents('*.IntSstage') or []
                      for o in e.GetContents('*.ElmLne', 1) or []}
    subestacion = _ruta(carga.GetParent())
    adyacentes = {}
    for clase in ('ElmTr2', 'ElmCoup', 'ElmLne'):
        for obj in inventario[clase].values():
            if _leer(obj, 'outserv') or (clase == 'ElmCoup' and _leer(obj, 'on_off') == 0):
                continue
            if clase == 'ElmLne':
                if _base_nombre(obj.loc_name) not in lineas_propias:
                    continue
                atributos = ('bus1', 'bus2')
            else:
                if _ruta(obj.GetParent()) != subestacion:
                    continue
                atributos = ('bushv', 'buslv') if clase == 'ElmTr2' else ('bus1', 'bus2')
            a, b = (_ruta(_terminal(obj, atributo)) for atributo in atributos)
            if a and b:
                adyacentes.setdefault(a, []).append((b, _ruta(obj), clase == 'ElmLne'))
                adyacentes.setdefault(b, []).append((a, _ruta(obj), clase == 'ElmLne'))
    pila = [(inicio, [], 0)]
    vistos = set()
    while pila:
        nodo, camino, lineas = pila.pop()
        if nodo == destino:
            return camino
        if len(camino) >= 3 or (nodo, lineas) in vistos:
            continue
        vistos.add((nodo, lineas))
        for vecino, elemento, es_linea in adyacentes.get(nodo, []):
            if lineas + es_linea <= 1:
                pila.append((vecino, camino + [elemento], lineas + es_linea))
    return None


def _validar_previstas(app, proyecto, previstas):
    inventario = _inventario(app, proyecto)
    activas = list(app.GetActiveNetworkVariations() or [])
    verificadas, usadas, variaciones_usadas = [], set(), set()
    for registro in previstas:
        xs = [v for v in activas if registro['variacion'] in (v.loc_name, _ruta(v))]
        if len(xs) != 1 or not xs[0].loc_name.startswith('Carga_'):
            raise ValueError(f'variación prevista ausente, inactiva o ambigua: {registro["variacion"]}')
        variacion = xs[0]
        if _ruta(variacion) in variaciones_usadas:
            raise ValueError('dos registros previstos comparten variación: no se acredita carga por carga')
        puntos = [b for b in inventario['ElmTerm'].values() if registro['barra'] in (b.loc_name, _ruta(b))]
        if len(puntos) != 1:
            raise ValueError(f'barra prevista ausente o ambigua: {registro["barra"]}')
        candidatos = []
        for obj in inventario['ElmLod'].values():
            base = _base_nombre(obj.loc_name)
            indice = {(registro['alimentador'], base): {
                'carga': obj, 'recortado': base != obj.loc_name and len(base) >= BASE_RECORTADA}}
            if not entradas_del_indice(indice, [registro['alimentador']], nombre_pf(registro['sed'])):
                continue
            camino = _camino_al_punto(obj, puntos[0], variacion, inventario)
            if camino is not None:
                candidatos.append((obj, camino))
        if len(candidatos) != 1:
            raise ValueError(f'carga física prevista ausente o ambigua en su punto explícito: {registro["sed"]}')
        obj, camino = candidatos[0]
        if _ruta(obj) in usadas:
            raise ValueError('una carga física coincide con más de un registro previsto')
        if _leer(obj, 'outserv'):
            raise ValueError(f'carga prevista fuera de servicio: {_ruta(obj)}')
        p, q, escala = _leer(obj, 'plini'), _leer(obj, 'qlini'), _leer(obj, 'scale0')
        if (p is None or q is None or escala is None or not _igual_valor(escala, 1)
                or not math.isclose(p * 1000, registro['kw'], rel_tol=1e-4, abs_tol=.01)
                or not math.isclose(q * 1000, registro['kvar'], rel_tol=1e-4, abs_tol=.01)):
            raise ValueError(f'demanda nominal prevista no coincide: {_ruta(obj)}; '
                             f'P/Q/escala={p}/{q}/{escala}; previstos={registro["kw"]}/{registro["kvar"]} kW/kvar')
        usadas.add(_ruta(obj))
        variaciones_usadas.add(_ruta(variacion))
        verificadas.append({'sed': registro['sed'], 'variacion': _ruta(variacion),
                            'carga': _ruta(obj), 'barra_prevista': _ruta(puntos[0]),
                            'barra_carga': _ruta(_terminal(obj, 'bus1')), 'camino': camino,
                            'kw': p * 1000, 'kvar': q * 1000, 'scale0': escala})
    return {'cantidad_prevista': len(previstas), 'cantidad_verificada': len(verificadas),
            'completa': bool(previstas) and len(verificadas) == len(previstas), 'cargas': verificadas}


def _verificar_firma_cargas(app, proyecto, firma):
    if _firma_cargas(app, proyecto) != firma:
        raise RuntimeError('el candidato cambia la identidad o la demanda escrita de las cargas')


def _igual_valor(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-8)
    return a == b


NOMINALES = ('plini', 'qlini', 'scale0', 'i_scale', 'i_sym', 'mode_inp', 'outserv',
             'plinir', 'plinis', 'plinit', 'qlinir', 'qlinis', 'qlinit')


def _verificar_nominales(app, proyecto, firma):
    actual = _firma_cargas(app, proyecto)
    if set(actual) != set(firma):
        raise RuntimeError('los casos proyectados no contienen los mismos objetos de carga')
    diferencias = [f'{ruta}.{a}' for ruta, datos in firma.items() for a in NOMINALES
                   if not _igual_valor(datos.get(a), actual[ruta].get(a))]
    if diferencias:
        raise RuntimeError('nominales distintos entre los casos proyectados: ' + ', '.join(diferencias[:20]))


def _copiar_nominales_al_escenario(app, proyecto, firma):
    """Copia exclusivamente entradas P/Q al escenario candidato; Con es la fuente intacta.

    scale0/i_scale y el modo pueden ser datos estáticos según la versión: si difieren,
    se rechaza antes de escribirlos en la red o en una variación anterior.
    """
    actuales = _inventario(app, proyecto)['ElmLod']
    if set(actuales) != set(firma):
        raise RuntimeError('faltan cargas para copiar los nominales de Con proyecto')
    for ruta, obj in actuales.items():
        origen = firma[ruta]
        for a in ('scale0', 'i_scale', 'i_sym', 'mode_inp', 'outserv'):
            if not _igual_valor(_leer(obj, a), origen.get(a)):
                raise RuntimeError(f'{ruta}.{a} difiere: requiere una sincronización estática aislada explícita')
        if origen.get('plini') is None or origen.get('qlini') is None:
            raise RuntimeError(f'{ruta}: falta P/Q nominal de Con proyecto')
    cambiadas = []
    for ruta, obj in actuales.items():
        origen = firma[ruta]
        if all(_igual_valor(_leer(obj, a), origen.get(a)) for a in NOMINALES):
            continue
        if origen.get('i_sym') == 1:
            for a in ('plinir', 'plinis', 'plinit', 'qlinir', 'qlinis', 'qlinit'):
                if origen.get(a) is not None:
                    obj.SetAttribute(a, origen[a])
        escribir_carga(obj, origen['plini'], origen['qlini'])
        cambiadas.append(ruta)
    _verificar_nominales(app, proyecto, firma)
    return cambiadas


def _aislar_variaciones(app, con, nuevas):
    """También Caso base y los años: ninguna obra nueva queda activa fuera de Con."""
    verificadas = []
    for caso in app.GetProjectFolder('study').GetContents('*.IntCase', 1) or []:
        if _ruta(caso) == _ruta(con):
            continue
        _activar(app, caso)
        rutas = {_ruta(v) for v in app.GetActiveNetworkVariations() or []}
        for v in nuevas:
            if _ruta(v) in rutas:
                v.Deactivate()
        if {_ruta(v) for v in nuevas} & {_ruta(v) for v in app.GetActiveNetworkVariations() or []}:
            raise RuntimeError(f'no se pudieron aislar las obras en {_ruta(caso)}')
        verificadas.append(_ruta(caso))
    _activar(app, con)
    return verificadas


def _contexto_nativo(app):
    contexto = {'caso_activo': _ruta(app.GetActiveStudyCase()),
                'escenario_activo': _ruta(app.GetActiveScenario()),
                'etapa_grabando': _ruta(app.GetRecordingStage())}
    try:
        contexto['salida_nativa'] = [str(x) for x in (app.GetOutputWindow().GetContent() or [])][-80:]
    except Exception as exc:  # noqa: BLE001 - el fallo de lectura de ventana también queda documentado
        contexto['salida_nativa'] = []
        contexto['error_lectura_ventana'] = str(exc)
    return contexto


def _guardar_escenario(app, escenario, out, motivo):
    """Guarda solo la copia propia activa y conserva evidencia del retorno nativo."""
    _activar(app, escenario)
    antes = _firma_modelo(app)
    retorno = escenario.Save()
    previo_confirmado = any(e.get('retorno') == 0 and e.get('escenario') == _ruta(escenario)
                            for e in out.get('guardados_escenarios', []))
    evidencia = {'motivo': motivo, 'escenario': _ruta(escenario), 'retorno': retorno,
                 **_contexto_nativo(app)}
    out.setdefault('guardados_escenarios', []).append(evidencia)
    if retorno == 1 and _esta_activo(app, escenario):
        # PythonReference_en.pdf 2024, impresa 529: 1 también significa que no
        # hubo modificación. Las activaciones de variaciones pueden haber guardado
        # automáticamente la copia. No se interpreta el mensaje de ventana como éxito.
        # Si esta misma llamada ya obtuvo Save=0 para la copia, se acredita ese guardado
        # y se exige reapertura idéntica de TODO el modelo. Sin ese antecedente se exige
        # además lectura de BD. No se supone que coslini pertenezca a cada subconjunto.
        try:
            lectura = [] if previo_confirmado else _verificar_bd_operacional(app, escenario)
            escenario.Deactivate(0)
            _activar(app, escenario)
            despues = _firma_modelo(app)
            if antes != despues:
                diferentes = sorted(k for k in set(antes) | set(despues) if antes.get(k) != despues.get(k))
                raise RuntimeError('reapertura de la copia cambia datos físicos o nominales: ' + ', '.join(diferentes[:10]))
            evidencia['persistencia_verificada'] = {'lectura_bd': not previo_confirmado,
                'guardado_previo_confirmado': previo_confirmado, 'reactivacion_identica': True,
                'objetos_releidos': len(despues), 'valores_bd': lectura,
                'fundamento': 'PowerFactory 2024 Python Reference, IntScenario.Save/GetOperationValue, p.529/528'}
            return
        except Exception as exc:  # el rechazo conserva evidencia y provoca rollback del candidato
            evidencia['persistencia_verificada'] = {'lectura_bd': False, 'error': str(exc)}
            raise RuntimeError(f'Save=1 sin persistencia acreditada en BD: {exc}') from exc
    if retorno != 0:
        raise RuntimeError(f'no se pudo guardar el escenario candidato: retorno={retorno}; '
                           f'escenario_activo={evidencia["escenario_activo"]}; motivo={motivo}')


def _firma_modelo(app):
    inventario = _inventario(app, app.GetActiveProject())
    return {_ruta(obj): {k: v for k, v in _ficha(obj).items()
                        if not k.startswith(('m:', 'c:')) and k != 'resultados_disponibles'}
            for objetos in inventario.values() for obj in objetos.values()}


def _verificar_bd_operacional(app, escenario):
    """Lee entradas del modo, evitando confundir Q/S derivados con datos guardados."""
    entradas = {'PQ': ('plini', 'qlini'), 'PC': ('plini', 'coslini'),
                'SC': ('slini', 'coslini'), 'SP': ('slini', 'plini'),
                'QC': ('qlini', 'coslini')}
    valores = []
    inventario = _inventario(app, app.GetActiveProject())
    for obj in inventario['ElmLod'].values():
        if _leer(obj, 'outserv'):
            continue
        modo = str(_leer(obj, 'mode_inp') or 'PC').upper()
        if modo not in entradas:
            raise RuntimeError(f'BD: modo de demanda no verificable {modo}: {_ruta(obj)}')
        campos = list(entradas[modo])
        if _leer(obj, 'scale0') is not None:
            campos.append('scale0')
        if _leer(obj, 'i_sym') == 1:
            campos.extend(('plinir', 'plinis', 'plinit', 'qlinir', 'qlinis', 'qlinit'))
        for atributo in campos:
            resultado = escenario.GetOperationValue(obj, atributo, 0)
            if not isinstance(resultado, (list, tuple)) or len(resultado) != 2 or resultado[0] != 0:
                raise RuntimeError(f'BD: no se pudo leer {_ruta(obj)}.{atributo}: {resultado}')
            actual = _leer(obj, atributo)
            if actual is None or not _igual_valor(actual, resultado[1]):
                raise RuntimeError(f'BD: {_ruta(obj)}.{atributo} no coincide: guardado={resultado[1]}, actual={actual}')
            valores.append({'objeto': _ruta(obj), 'atributo': atributo, 'valor': resultado[1]})
    if not valores:
        raise RuntimeError('BD: ninguna demanda operacional pudo verificarse')
    return valores


def _verificar_registro_etapa(etapa, obj, atributos):
    candidatos = [o for o in etapa.GetContents(f'*.{obj.GetClassName()}', 1) or []
                  if o.loc_name == obj.loc_name]
    if len(candidatos) != 1:
        raise RuntimeError(f'la etapa propia no registra inequívocamente {_ruta(obj)}')
    leidos = {a: _leer(candidatos[0], a) for a in atributos}
    esperados = {a: _ruta(v) if hasattr(v, 'GetFullName') else v for a, v in atributos.items()}
    if any(not _igual_valor(leidos[a], v) if type(v) is float else leidos[a] != v
           for a, v in esperados.items()):
        raise RuntimeError(f'los datos de la etapa propia no coinciden para {_ruta(obj)}: {leidos}')
    return {'verificado': True, 'etapa': _ruta(etapa), 'registro': _ruta(candidatos[0]),
            'elemento': _ruta(obj), 'atributos': leidos}


def _referencias_finales(app, proyecto, casos, con, plan, escenario_cargas, firma):
    """Observa Sin/Cargas sin sincronizar operación ni usar sus violaciones como gate de Con."""
    escenario_con = app.GetActiveScenario()
    referencias = {}
    anio = anio_del_plan(plan)
    try:
        for rol, nombre in [('sin', nombre_caso('sin', anio)), ('cargas', nombre_cargas_nuevas(anio))]:
            caso = casos.get(nombre)
            if caso is None:
                raise ValueError(f'falta el caso de referencia {nombre}')
            print(f'Estudios finales de referencia: {nombre}', flush=True)
            _activar(app, caso)
            if rol == 'cargas':
                if escenario_cargas is not None:
                    _activar(app, escenario_cargas)
                _verificar_nominales(app, proyecto, firma)
                _validar_previstas(app, proyecto, plan['nuevas'])
            referencias[rol] = {'nombre_caso': caso.loc_name, 'caso': _ruta(caso),
                'escenario': _ruta(app.GetActiveScenario()),
                'ajustes_flujo': _datos(app.GetFromStudyCase('ComLdf'), (*sorted(AJUSTES), 'iopt_net', 'iopt_fls')),
                'variaciones_activas': [_ruta(v) for v in app.GetActiveNetworkVariations() or []],
                'estudios': _estudiar(app, proyecto, plan.get('limites') or {}),
                'es_referencia': True}
    finally:
        _activar(app, con)
        if escenario_con is not None:
            _activar(app, escenario_con)
    _verificar_firma_cargas(app, proyecto, firma)
    return referencias


def _restaurar_casos(app, fotos, con, plan, conservar, fecha_candidata=None):
    errores = []
    for nombre, foto in fotos.items():
        try:
            caso = foto['caso']
            _activar(app, caso)
            es_con = _ruta(caso) == _ruta(con)
            es_cargas = nombre == nombre_cargas_nuevas(anio_del_plan(plan))
            mantener = conservar and (es_con or (es_cargas and plan.get('sincronizar_cargas')))
            if not mantener:
                for v in reversed(list(app.GetActiveNetworkVariations() or [])):
                    if _ruta(v) not in {_ruta(x) for x in foto['variaciones']}:
                        v.Deactivate()
                for v in foto['variaciones']:
                    if _ruta(v) not in {_ruta(x) for x in app.GetActiveNetworkVariations() or []}:
                        _activar(app, v)
            if not mantener:
                esc = app.GetActiveScenario()
                if _ruta(esc) != _ruta(foto['escenario']):
                    if esc is not None:
                        esc.Deactivate(0)
                    if foto['escenario'] is not None:
                        _activar(app, foto['escenario'])
            ldf = app.GetFromStudyCase('ComLdf')
            for a, valor in foto['ldf'].items():
                if valor is not None and not (conservar and es_con and a in (plan.get('ajustes_flujo') or {})):
                    ldf.SetAttribute(a, valor)
            if conservar and es_con:
                # IntSstage.Activate también cambia iStudyTime (PF2024, p.534).
                # El candidato conserva la fecha y la etapa verificadas; nunca se
                # reactiva la etapa original anterior a las nuevas obras.
                fecha = fecha_candidata
            else:
                if foto['etapa'] is not None:
                    foto['etapa'].Activate(1)
                fecha = foto['fecha']
            # Siempre después de activar cualquier etapa: el orden inverso rebobina.
            if fecha is not None and _leer(caso, 'iStudyTime') != fecha:
                caso.SetAttribute('iStudyTime', fecha)
            if fecha is not None and _leer(caso, 'iStudyTime') != fecha:
                raise RuntimeError('la fecha del caso no conserva el estado autorizado')
        except Exception as exc:  # noqa: BLE001 - toda restauración fallida queda expuesta al caller
            errores.append(f'{nombre}: {exc}')
    return errores


def _verificar_final(app, proyecto, casos, con, plan, copia, copia_cargas, firma, candidato):
    cargas_verificadas = False
    if plan.get('sincronizar_cargas'):
        _activar(app, casos[nombre_cargas_nuevas(anio_del_plan(plan))])
        if _ruta(app.GetActiveScenario()) != _ruta(copia_cargas):
            raise RuntimeError('el estado final perdió la copia de Cargas nuevas')
        _verificar_nominales(app, proyecto, firma)
        _validar_previstas(app, proyecto, plan['nuevas'])
        cargas_verificadas = True
    _activar(app, con)
    if _ruta(app.GetActiveScenario()) != _ruta(copia):
        raise RuntimeError('el estado final perdió el escenario candidato de Con proyecto')
    fecha = _leer(con, 'iStudyTime')
    if fecha != candidato['fecha'] or (candidato['ultima_etapa'] is not None
                                     and (fecha is None or fecha < candidato['ultima_etapa'])):
        raise RuntimeError('el estado final rebobinó o excluye etapas de las obras nuevas')
    activas = sorted(_ruta(v) for v in app.GetActiveNetworkVariations() or [])
    if activas != candidato['variaciones'] or _firma_modelo(app) != candidato['modelo']:
        raise RuntimeError('el modelo físico final difiere del candidato que pasó la relectura')
    return {'modelo_identico': True, 'fecha': fecha, 'ultima_etapa_nueva': candidato['ultima_etapa'],
            'escenario': _ruta(copia), 'variaciones_activas': activas,
            'cargas_sin_obras_verificadas': cargas_verificadas}


def ejecutar(app, plan):
    """Única entrada del arnés: valida identidad antes de activar el proyecto."""
    bloqueado = native_action_block_report(plan, ('obras',))
    if bloqueado:
        return bloqueado, 2
    out = {'project': plan.get('project'), 'accion': plan.get('accion', 'diagnostico'),
           'status': 'BLOQUEADO_DATOS', 'aceptada': False, 'variaciones_creadas': [],
           'escenario_candidato': None, 'avisos': [],
           'validacion_de_nuevas': ('no_solicitada_diagnostico_estructural'
               if plan.get('accion', 'diagnostico') == 'diagnostico' and not plan.get('verificar_flujos')
               else 'manifiesto_requerido')}
    previo_caso, previo_proyecto = app.GetActiveStudyCase(), app.GetActiveProject()
    previo_flujo_valido = None
    proyecto, casos, con = None, {}, None
    fotos, nuevas, copia, copia_cargas = {}, [], None, None
    conservar = False
    candidato = None
    codigo = 2
    try:
        consultar_flujo = getattr(app, 'IsLdfValid', None)
        if previo_proyecto is not None and previo_caso is not None and callable(consultar_flujo):
            previo_flujo_valido = bool(consultar_flujo())
        out['estado_inicial'] = {'proyecto': _ruta(previo_proyecto), 'caso': _ruta(previo_caso),
            'fecha': _leer(previo_caso, 'iStudyTime') if previo_caso is not None else None,
            'flujo_valido': previo_flujo_valido}
        validar_plan(plan)
        proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
        if proyecto is None:
            raise ValueError('no existe el proyecto vinculado')
        casos, con = _casos(app, plan)
        print('Leyendo casos, inventario y catálogos del proyecto vinculado', flush=True)
        for nombre, caso in casos.items():
            _activar(app, caso)
            fotos[nombre] = {'caso': caso, 'escenario': app.GetActiveScenario(),
                'variaciones': list(app.GetActiveNetworkVariations() or []),
                'fecha': _leer(caso, 'iStudyTime'), 'etapa': app.GetRecordingStage(),
                'ldf': _datos(app.GetFromStudyCase('ComLdf'), (*sorted(AJUSTES), 'iopt_net'))}
        out['casos'], out['diferencias_cargas'] = diagnosticar(app, proyecto, casos)
        if out['accion'] == 'diagnostico':
            out['status'] = 'OK'
            codigo = 0
            if plan.get('verificar_flujos'):
                print('Verificando ambos flujos de la operación preexistente', flush=True)
                _activar(app, con)
                firma_preexistente = _firma_cargas(app, proyecto)
                out['cargas_previstas'] = _validar_previstas(app, proyecto, plan['nuevas'])
                out['estudios'] = _estudiar(app, proyecto, plan.get('limites') or {})
                _verificar_firma_cargas(app, proyecto, firma_preexistente)
                out['relectura'] = _estado_caso(app, proyecto)
                out['aceptada'] = all(e['aceptada'] for e in out['estudios'].values())
                out['operacion_preexistente_verificada'] = out['aceptada']
                out['status'] = 'OK' if out['aceptada'] else 'VIOLACION_FISICA'
                codigo = 0 if out['aceptada'] else 2
        else:
            print('Validando referencias y preservando cargas activas', flush=True)
            _activar(app, con)
            out['cargas_previstas'] = _validar_previstas(app, proyecto, plan['nuevas'])
            resueltos = _resolver_cambios(app, proyecto, plan.get('cambios') or [])
            salidas = _resolver_salidas(app, proyecto, plan.get('salidas') or [])
            activas = list(app.GetActiveNetworkVariations() or [])
            desactivar = []
            for nombre in plan.get('desactivar_variaciones') or []:
                xs = [v for v in activas if nombre in (v.loc_name, _ruta(v))]
                if len(xs) != 1:
                    raise ValueError(f'obra activa inexistente o ambigua: {nombre}')
                desactivar.append(xs[0])
            # Validar todo antes de crear objetos o cambiar cualquier estado.
            nombre_cargas = nombre_cargas_nuevas(anio_del_plan(plan))
            if plan.get('sincronizar_cargas') and nombre_cargas not in casos:
                raise ValueError('no existe el caso Cargas nuevas que se pide sincronizar')
            # Copia exclusiva: los datos de operación no deben ensuciar el escenario aprobado.
            original = app.GetActiveScenario()
            carpeta = app.GetProjectFolder('scen', 1)
            nombre = 'Operacion_SET_' + uuid.uuid4().hex[:12]
            copia = carpeta.AddCopy(original, nombre) if original is not None else carpeta.CreateObject('IntScenario', nombre)
            if copia is None:
                raise RuntimeError('no se pudo copiar el escenario de operación')
            if original is not None:
                original.Deactivate(0)
            _activar(app, copia)
            out['escenario_candidato'] = _ruta(copia)
            if plan.get('conciliar_fases'):
                print('Conciliando fases con totales calibrados en copia propia', flush=True)
                out['conciliacion_fases'] = _conciliar_fases(app, proyecto, copia)
                if out['conciliacion_fases']['cantidad']:
                    _guardar_escenario(app, copia, out, 'entradas de fase conciliadas')
            firma_cargas = _firma_cargas(app, proyecto)
            for v in desactivar:
                v.Deactivate()
            _verificar_firma_cargas(app, proyecto, firma_cargas)
            if plan.get('sincronizar_cargas'):
                print('Sincronizando las cargas en una copia propia del escenario', flush=True)
                cargas = [v for v in activas if v.loc_name.startswith('Carga_')]
                _activar(app, casos[nombre_cargas])
                presentes = {_ruta(v) for v in app.GetActiveNetworkVariations() or []}
                out['cargas_sincronizadas'] = []
                for v in cargas:
                    if _ruta(v) not in presentes:
                        _activar(app, v)
                        out['cargas_sincronizadas'].append(_ruta(v))
                nombres_actuales = {_ruta(v) for v in app.GetActiveNetworkVariations() or []
                                    if v.loc_name.startswith('Carga_')}
                if nombres_actuales != {_ruta(v) for v in cargas}:
                    raise ValueError('Cargas nuevas contiene cargas adicionales: no se eliminan para emparejar')
                original_cargas = app.GetActiveScenario()
                carpeta_cargas = app.GetProjectFolder('scen', 1)
                nombre_sync = 'Cargas_SET_' + uuid.uuid4().hex[:12]
                copia_cargas = (carpeta_cargas.AddCopy(original_cargas, nombre_sync) if original_cargas is not None
                                else carpeta_cargas.CreateObject('IntScenario', nombre_sync))
                if copia_cargas is None:
                    raise RuntimeError('no se pudo copiar el escenario de Cargas nuevas')
                if original_cargas is not None:
                    original_cargas.Deactivate(0)
                _activar(app, copia_cargas)
                if plan.get('conciliar_fases'):
                    out['conciliacion_fases_cargas'] = _conciliar_fases(app, proyecto, copia_cargas)
                cambiadas = _copiar_nominales_al_escenario(app, proyecto, firma_cargas)
                _guardar_escenario(app, copia_cargas, out, 'nominales de Cargas nuevas')
                # La igualdad debe sobrevivir a reactivar ambos escenarios, no solo al setter.
                _activar(app, con)
                _activar(app, copia)
                _verificar_firma_cargas(app, proyecto, firma_cargas)
                _activar(app, casos[nombre_cargas])
                _verificar_nominales(app, proyecto, firma_cargas)
                out['cargas_previstas_sin_obras'] = _validar_previstas(app, proyecto, plan['nuevas'])
                out['sincronizacion_nominales'] = {'verificada': True, 'escenario': _ruta(copia_cargas),
                    'origen': _ruta(con), 'cargas_copiadas': cambiadas,
                    'cargas': [{'ruta': ruta, **{a: d.get(a) for a in NOMINALES}}
                               for ruta, d in firma_cargas.items()]}
                _activar(app, con)
                _activar(app, copia)
            if out['accion'] == 'aplicar':
                out['estudios_referencia'] = _referencias_finales(
                    app, proyecto, casos, con, plan, copia_cargas, firma_cargas)
            # UserManual 2024: con escenario inactivo el operacional queda en la etapa.
            # Se suspende SOLO la copia propia; todas las variaciones de carga siguen activas.
            copia.Deactivate(0)
            for i, (obj, attrs) in enumerate(resueltos, 1):
                print(f'Variación propia {i}/{len(resueltos)}: {_ruta(obj)}', flush=True)
                v, _etapa = crear_variacion(app, 'Obra_operacion_SET_' + uuid.uuid4().hex[:10], str(i))
                nuevas.append(v)
                out['variaciones_creadas'].append({'ruta': _ruta(v), 'nombre': v.loc_name,
                    'elemento': _ruta(obj), 'atributos': {a: _ruta(x) if hasattr(x, 'GetFullName') else x for a, x in attrs.items()}})
                if app.GetActiveScenario() is not None:
                    raise RuntimeError('un escenario está activo al grabar la obra: no se escribe en él')
                for atributo, valor in attrs.items():
                    obj.SetAttribute(atributo, valor)
                out['variaciones_creadas'][-1]['registro_etapa'] = _verificar_registro_etapa(_etapa, obj, attrs)
                # Deactivate/Activate de la variación termina la grabación; no se usa una
                # API hipotética de IntSstage para apagar la etapa. Las cargas siguen activas.
                v.Deactivate()
                _activar(app, v)
            out['salidas_creadas'] = []
            for i, (salida, origen, destino, tipo, _preflight) in enumerate(salidas, 1):
                print(f'Salida propia {i}/{len(salidas)}: {salida["nombre"]}', flush=True)
                v, etapa = crear_variacion(app, 'Obra_salida_SET_' + uuid.uuid4().hex[:10], salida['nombre'])
                nuevas.append(v)
                datos = construir_salida_set_existente(app, proyecto, origen, destino, tipo,
                    salida['nombre'], salida['circuitos'], salida['ruta'])
                out['salidas_creadas'].append(datos)
                linea = _inventario(app, proyecto)['ElmLne'].get(datos['linea'])
                if linea is None:
                    raise RuntimeError('la salida recién construida no aparece por su ruta exacta')
                atributos = {'typ_id': tipo, 'nlnum': salida['circuitos'], 'outserv': 0,
                             'dline': datos['longitud_km']}
                registro = _verificar_registro_etapa(etapa, linea, atributos)
                out['variaciones_creadas'].append({'ruta': _ruta(v), 'nombre': v.loc_name,
                    'elemento': datos['linea'], 'atributos': {a: _ruta(x) if hasattr(x, 'GetFullName') else x
                                                          for a, x in atributos.items()},
                    'registro_etapa': registro, 'salida': datos})
                _verificar_salida(app, proyecto, datos)
                v.Deactivate()
                _activar(app, v)
            _activar(app, copia)
            # El escenario también conserva la operación solicitada; una copia anterior
            # podría sobrescribir el default que acabamos de registrar en cada etapa.
            for obj, attrs in resueltos:
                for atributo in ('outserv', 'nntap'):
                    if atributo in attrs:
                        obj.SetAttribute(atributo, attrs[atributo])
            out['cambios_antes_guardar'] = [_ficha(obj) for obj, _attrs in resueltos]
            _guardar_escenario(app, copia, out, 'operación antes de cambiar de caso')
            out['casos_sin_obras_nuevas'] = _aislar_variaciones(app, con, nuevas)
            _activar(app, copia)
            out['cambios_tras_aislar'] = [_ficha(obj) for obj, _attrs in resueltos]
            ldf = app.GetFromStudyCase('ComLdf')
            for atributo, valor in (plan.get('ajustes_flujo') or {}).items():
                ldf.SetAttribute(atributo, valor)
            _guardar_escenario(app, copia, out, 'candidato antes del flujo')
            out['cargas_previstas_candidato'] = _validar_previstas(app, proyecto, plan['nuevas'])
            out['estudios'] = _estudiar(app, proyecto, plan.get('limites') or {})
            _verificar_firma_cargas(app, proyecto, firma_cargas)
            _guardar_escenario(app, copia, out, 'operación calculada')
            out['aceptada'] = all(e['aceptada'] for e in out['estudios'].values())
            if plan.get('reabrir', True):
                print('Reabriendo el caso y verificando el candidato persistido', flush=True)
                otro = next((c for c in casos.values() if _ruta(c) != _ruta(con)), None)
                if otro is not None:
                    _activar(app, otro)
                _activar(app, con)
                if _ruta(app.GetActiveScenario()) != _ruta(copia):
                    raise RuntimeError('la relectura no conserva el escenario candidato')
                out['relectura'] = _estado_caso(app, proyecto)
                activas_releidas = {v['ruta'] for v in out['relectura']['variaciones_activas']}
                if not {_ruta(v) for v in nuevas} <= activas_releidas:
                    raise RuntimeError('la relectura no conserva las variaciones nuevas')
                indice = {o['ruta']: o for xs in out['relectura']['objetos'].values() for o in xs}
                for obj, attrs in resueltos:
                    fila = indice.get(_ruta(obj))
                    if fila is None:
                        raise RuntimeError(f'elemento ausente al releer: {_ruta(obj)}')
                    for atributo, valor in attrs.items():
                        esperado = _ruta(valor) if hasattr(valor, 'GetFullName') else valor
                        actual = fila['referencias'].get('typ_id', {}).get('ruta') if atributo == 'typ_id' else fila.get(atributo)
                        if actual != esperado:
                            raise RuntimeError(f'relectura distinta: {_ruta(obj)}.{atributo}')
                out['salidas_relectura'] = [_verificar_salida(app, proyecto, d) for d in out['salidas_creadas']]
                out['cargas_previstas_relectura'] = _validar_previstas(app, proyecto, plan['nuevas'])
                out['estudios_relectura'] = _estudiar(app, proyecto, plan.get('limites') or {})
                _verificar_firma_cargas(app, proyecto, firma_cargas)
                out['aceptada'] = out['aceptada'] and all(e['aceptada'] for e in out['estudios_relectura'].values())
            if out['accion'] == 'aplicar' and out['aceptada']:
                etapas = [_leer(e, 'tAcTime') for v in nuevas for e in v.GetContents('*.IntSstage') or []]
                candidato = {'fecha': _leer(con, 'iStudyTime'), 'modelo': _firma_modelo(app),
                    'variaciones': sorted(_ruta(v) for v in app.GetActiveNetworkVariations() or []),
                    'ultima_etapa': max(etapas) if etapas and all(e is not None for e in etapas) else None}
                if etapas and (candidato['fecha'] is None or candidato['ultima_etapa'] is None
                               or candidato['fecha'] < candidato['ultima_etapa']):
                    raise RuntimeError('la fecha candidata no incluye las etapas de las obras nuevas')
            conservar = out['accion'] == 'aplicar' and out['aceptada']
            out['status'] = 'OK' if out['aceptada'] else 'VIOLACION_FISICA'
            out['persistida'] = conservar
            codigo = 0 if out['aceptada'] else 2
    except Exception as exc:  # noqa: BLE001 - fallo nativo informado; finally restaura la transacción
        out.update(status='BLOQUEADO_DATOS', aceptada=False, error=str(exc), persistida=False)
        out['contexto_error'] = _contexto_nativo(app)
        codigo = 2
    finally:
        print('Verificando aislamiento y restituyendo el estado autorizado', flush=True)
        errores = []
        if proyecto is not None and con is not None and nuevas:
            try:
                _aislar_variaciones(app, con, nuevas)
            except Exception as exc:  # noqa: BLE001 - cada fallo de restauración queda expuesto en el informe
                errores.append(f'aislamiento entre casos: {exc}')
        errores.extend(_restaurar_casos(app, fotos, con, plan, conservar,
                                        candidato['fecha'] if candidato is not None else None))
        if conservar:
            try:
                if errores:
                    raise RuntimeError('la restauración de otros casos no está completa')
                out['verificacion_final'] = _verificar_final(
                    app, proyecto, casos, con, plan, copia, copia_cargas, firma_cargas, candidato)
            except Exception as exc:  # noqa: BLE001 - fallo final obliga a revertir el candidato, nunca a publicarlo
                errores.append(f'verificación física final: {exc}')
                conservar = False
                errores.extend(_restaurar_casos(app, fotos, con, plan, False))
        if not conservar:
            for v in reversed(nuevas):
                try:
                    v.Deactivate()
                    if out['accion'] == 'evaluar':
                        v.Delete()
                except Exception as exc:  # noqa: BLE001 - limpieza propia; el informe conserva cualquier fallo nativo
                    errores.append(f'variación propia {_ruta(v)}: {exc}')
            for escenario_propio in (copia, copia_cargas):
                if escenario_propio is None:
                    continue
                try:
                    if _ruta(app.GetActiveScenario()) == _ruta(escenario_propio):
                        escenario_propio.Deactivate(0)
                    escenario_propio.Delete()
                except Exception as exc:  # noqa: BLE001 - limpieza propia; el informe conserva cualquier fallo nativo
                    errores.append(f'escenario propio: {exc}')
        try:
            if previo_proyecto is not None and _ruta(app.GetActiveProject()) != _ruta(previo_proyecto):
                _activar(app, previo_proyecto)
            if previo_caso is not None:
                _activar(app, previo_caso)
            recalculado = False
            if previo_proyecto is None:
                activo = app.GetActiveProject()
                if activo is not None:
                    if proyecto is None or _ruta(activo) != _ruta(proyecto):
                        raise RuntimeError('el proyecto activo cambió por fuera de la operación; no se desactiva')
                    rc_desactivar = activo.Deactivate()
                    if rc_desactivar not in (0, None) or app.GetActiveProject() is not None:
                        raise RuntimeError('no se pudo restituir la ausencia inicial de proyecto')
            elif previo_flujo_valido is True:
                # Los resultados son derivados del caso: recalcular el original no guarda
                # escenarios ni usa flujo_de_carga, que podría imponer otro iopt_net.
                ldf_original = app.GetFromStudyCase('ComLdf')
                retorno = ldf_original.Execute()
                valido = bool(app.IsLdfValid())
                if retorno != 0 or not valido:
                    raise RuntimeError(f'no se pudo restituir el flujo previo válido: Execute={retorno}, válido={valido}')
                recalculado = True
            out['estado_inicial_restituido'] = {'proyecto': _ruta(app.GetActiveProject()),
                'caso': _ruta(app.GetActiveStudyCase()) if app.GetActiveProject() is not None else '',
                'fecha': _leer(app.GetActiveStudyCase(), 'iStudyTime') if app.GetActiveProject() is not None else None,
                'flujo_recalculado': recalculado}
        except Exception as exc:  # noqa: BLE001 - restauración del estado inicial; error expuesto, no descartado
            errores.append(f'estado inicial: {exc}')
        out['restauracion_errores'] = errores
        if errores:
            out.update(status='BLOQUEADO_PERSISTENCIA', aceptada=False, persistida=False)
            if 'operacion_preexistente_verificada' in out:
                out['operacion_preexistente_verificada'] = False
            codigo = 2
    return out, codigo


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--output-json', required=True)
    args = parser.parse_args(argv)
    try:
        plan = json.loads(Path(args.plan).read_text(encoding='utf-8-sig'))
        validar_plan(plan)
        bloqueado = native_action_block_report(plan, ('obras',))
        if bloqueado:
            informe, codigo = bloqueado, 2
        else:
            from convertersmartgrid.pf_arnes import conectar
            print('Diagnóstico/operación de SET existente: esperando el arnés', flush=True)
            app = conectar('set_nueva_operacion_pf.py')
            informe, codigo = ejecutar(app, plan)
    except Exception as exc:  # noqa: BLE001 - borde CLI: siempre publica el informe del fallo nativo
        traceback.print_exc()
        informe, codigo = {'status': 'BLOQUEADO_DATOS', 'aceptada': False, 'error': str(exc)}, 2
    if informe.get('restauracion_errores'):
        codigo = 2
    Path(args.output_json).write_text(json.dumps(informe, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Informe: {args.output_json}', flush=True)
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
