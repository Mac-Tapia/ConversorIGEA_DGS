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

from cargas_pf import activar_proyecto, crear_variacion, flujo_de_carga, escribir_carga
from casos_pf import casos_del_proyecto, nombre_cargas_nuevas, nombre_caso, anio_del_plan
from estudios_pf import resumen_proyecto, geografia
from convertersmartgrid.native_action import native_action_block_report


CLASES_RED = ('ElmTerm', 'ElmLne', 'ElmTr2', 'ElmTr3', 'ElmLod', 'ElmXnet',
              'ElmSym', 'ElmGenstat', 'ElmShnt', 'ElmCoup', 'StaSwitch', 'ElmFeeder')
CAMBIOS = {'ElmLne': {'nlnum', 'typ_id', 'outserv'},
           'ElmTr2': {'ntnum', 'typ_id', 'outserv'},
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
    except Exception:  # atributos opcionales difieren entre versiones nativas
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


def _activar(obj):
    rc = obj.Activate()
    if rc not in (0, None):
        raise RuntimeError(f'no se pudo activar {_ruta(obj)}: {rc}')


def validar_plan(plan):
    """Lista cerrada: no admite demandas, coordenadas, potencias ni tipos editados."""
    if not isinstance(plan, dict) or not isinstance(plan.get('project'), str) or not plan['project'].strip():
        raise ValueError('falta el proyecto vinculado')
    if plan.get('accion', 'diagnostico') not in ('diagnostico', 'evaluar', 'aplicar'):
        raise ValueError('accion no válida')
    for clave in ('sincronizar_cargas', 'reabrir'):
        if clave in plan and not isinstance(plan[clave], bool):
            raise ValueError(f'{clave} debe ser booleano')
    ajustes = plan.get('ajustes_flujo') or {}
    if not isinstance(ajustes, dict) or set(ajustes) - AJUSTES:
        raise ValueError('ajustes_flujo solo admite iopt_lev, iopt_pq, iopt_at')
    if any(type(v) is not int or v not in (0, 1) for v in ajustes.values()):
        raise ValueError('los ajustes de flujo deben ser enteros 0/1')
    cambios = plan.get('cambios') or []
    if not isinstance(cambios, list):
        raise ValueError('cambios debe ser una lista')
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
            elif type(v) is not int or (v not in (0, 1) if a == 'outserv' else not 1 <= v <= 100):
                raise ValueError(f'{a} requiere entero físico válido')
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
        except Exception:
            fila['resultados_disponibles'] = None
    if clase.startswith('Elm'):
        fila.update(_datos(obj, ('m:Psum:bus1', 'm:Qsum:bus1', 'm:Psum:bushv',
                                'm:Qsum:bushv', 'm:Psum:buslv', 'm:Qsum:buslv')))
    conexiones = {}
    for a in REFERENCIAS:
        try:
            ref = obj.GetAttribute(a)
        except Exception:
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
        _activar(caso)
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


def _firma_cargas(app, proyecto):
    """Identidad y demanda escrita: el refuerzo no puede borrar ni reducir una carga."""
    return {_ruta(o): _datos(o, ATRIBUTOS['ElmLod'])
            for o in _inventario(app, proyecto)['ElmLod'].values()}


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
        _activar(caso)
        rutas = {_ruta(v) for v in app.GetActiveNetworkVariations() or []}
        for v in nuevas:
            if _ruta(v) in rutas:
                v.Deactivate()
        if {_ruta(v) for v in nuevas} & {_ruta(v) for v in app.GetActiveNetworkVariations() or []}:
            raise RuntimeError(f'no se pudieron aislar las obras en {_ruta(caso)}')
        verificadas.append(_ruta(caso))
    _activar(con)
    return verificadas


def ejecutar(app, plan):
    """Única entrada del arnés: valida identidad antes de activar el proyecto."""
    bloqueado = native_action_block_report(plan, ('obras',))
    if bloqueado:
        return bloqueado, 2
    out = {'project': plan.get('project'), 'accion': plan.get('accion', 'diagnostico'),
           'status': 'BLOQUEADO_DATOS', 'aceptada': False, 'variaciones_creadas': [],
           'escenario_candidato': None, 'avisos': []}
    previo_caso, previo_proyecto = app.GetActiveStudyCase(), app.GetActiveProject()
    proyecto, casos, con = None, {}, None
    fotos, nuevas, copia, copia_cargas = {}, [], None, None
    conservar = False
    try:
        validar_plan(plan)
        proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
        if proyecto is None:
            raise ValueError('no existe el proyecto vinculado')
        casos, con = _casos(app, plan)
        for nombre, caso in casos.items():
            _activar(caso)
            fotos[nombre] = {'caso': caso, 'escenario': app.GetActiveScenario(),
                'variaciones': list(app.GetActiveNetworkVariations() or []),
                'fecha': _leer(caso, 'iStudyTime'), 'etapa': app.GetRecordingStage(),
                'ldf': _datos(app.GetFromStudyCase('ComLdf'), (*sorted(AJUSTES), 'iopt_net'))}
        out['casos'], out['diferencias_cargas'] = diagnosticar(app, proyecto, casos)
        if out['accion'] == 'diagnostico':
            out['status'] = 'OK'
            return out, 0
        _activar(con)
        resueltos = _resolver_cambios(app, proyecto, plan.get('cambios') or [])
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
        firma_cargas = _firma_cargas(app, proyecto)
        for v in desactivar:
            v.Deactivate()
        _verificar_firma_cargas(app, proyecto, firma_cargas)
        if plan.get('sincronizar_cargas'):
            cargas = [v for v in activas if v.loc_name.startswith('Carga_')]
            _activar(casos[nombre_cargas])
            presentes = {_ruta(v) for v in app.GetActiveNetworkVariations() or []}
            out['cargas_sincronizadas'] = []
            for v in cargas:
                if _ruta(v) not in presentes:
                    _activar(v)
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
            _activar(copia_cargas)
            cambiadas = _copiar_nominales_al_escenario(app, proyecto, firma_cargas)
            if copia_cargas.Save() not in (0, None):
                raise RuntimeError('no se pudo guardar la copia de nominales de Cargas nuevas')
            # La igualdad debe sobrevivir a reactivar ambos escenarios, no solo al setter.
            _activar(con)
            _verificar_firma_cargas(app, proyecto, firma_cargas)
            _activar(casos[nombre_cargas])
            _verificar_nominales(app, proyecto, firma_cargas)
            out['sincronizacion_nominales'] = {'verificada': True, 'escenario': _ruta(copia_cargas),
                'origen': _ruta(con), 'cargas_copiadas': cambiadas,
                'cargas': [{'ruta': ruta, **{a: d.get(a) for a in NOMINALES}}
                           for ruta, d in firma_cargas.items()]}
            _activar(con)
        # Copia exclusiva: los datos de operación no deben ensuciar el escenario aprobado.
        original = app.GetActiveScenario()
        carpeta = app.GetProjectFolder('scen', 1)
        nombre = 'Operacion_SET_' + uuid.uuid4().hex[:12]
        copia = carpeta.AddCopy(original, nombre) if original is not None else carpeta.CreateObject('IntScenario', nombre)
        if copia is None:
            raise RuntimeError('no se pudo copiar el escenario de operación')
        if original is not None:
            original.Deactivate(0)
        _activar(copia)
        out['escenario_candidato'] = _ruta(copia)
        for i, (obj, attrs) in enumerate(resueltos, 1):
            v, etapa = crear_variacion(app, 'Obra_operacion_SET_' + uuid.uuid4().hex[:10], str(i))
            nuevas.append(v)
            out['variaciones_creadas'].append({'ruta': _ruta(v), 'nombre': v.loc_name,
                'elemento': _ruta(obj), 'atributos': {a: _ruta(x) if hasattr(x, 'GetFullName') else x for a, x in attrs.items()}})
            for atributo, valor in attrs.items():
                obj.SetAttribute(atributo, valor)
            # Deactivate/Activate de la variación termina la grabación; no se usa una
            # API hipotética de IntSstage para apagar la etapa. Las cargas siguen activas.
            v.Deactivate()
            _activar(v)
        out['casos_sin_obras_nuevas'] = _aislar_variaciones(app, con, nuevas)
        ldf = app.GetFromStudyCase('ComLdf')
        for atributo, valor in (plan.get('ajustes_flujo') or {}).items():
            ldf.SetAttribute(atributo, valor)
        if copia.Save() not in (0, None):
            raise RuntimeError('no se pudo guardar el escenario candidato')
        out['estudios'] = _estudiar(app, proyecto, plan.get('limites') or {})
        _verificar_firma_cargas(app, proyecto, firma_cargas)
        if copia.Save() not in (0, None):
            raise RuntimeError('no se pudo guardar la operación calculada del candidato')
        out['aceptada'] = all(e['aceptada'] for e in out['estudios'].values())
        if plan.get('reabrir', True):
            otro = next((c for c in casos.values() if c is not con), None)
            if otro is not None:
                _activar(otro)
            _activar(con)
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
            out['estudios_relectura'] = _estudiar(app, proyecto, plan.get('limites') or {})
            _verificar_firma_cargas(app, proyecto, firma_cargas)
            out['aceptada'] = out['aceptada'] and all(e['aceptada'] for e in out['estudios_relectura'].values())
        conservar = out['accion'] == 'aplicar' and out['aceptada']
        out['status'] = 'OK' if out['aceptada'] else 'VIOLACION_FISICA'
        out['persistida'] = conservar
        return out, 0 if out['aceptada'] else 2
    except Exception as exc:
        out.update(status='BLOQUEADO_DATOS', aceptada=False, error=str(exc), persistida=False)
        return out, 2
    finally:
        errores = []
        if proyecto is not None and con is not None and nuevas:
            try:
                _aislar_variaciones(app, con, nuevas)
            except Exception as exc:
                errores.append(f'aislamiento entre casos: {exc}')
        for nombre, foto in fotos.items():
            try:
                caso = foto['caso']
                _activar(caso)
                es_con = caso is con
                es_cargas = nombre == nombre_cargas_nuevas(anio_del_plan(plan))
                mantener = conservar and (es_con or (es_cargas and plan.get('sincronizar_cargas')))
                if not mantener:
                    for v in reversed(list(app.GetActiveNetworkVariations() or [])):
                        if v not in foto['variaciones']:
                            v.Deactivate()
                    for v in foto['variaciones']:
                        if v not in (app.GetActiveNetworkVariations() or []):
                            _activar(v)
                elif not es_con:
                    for v in nuevas:
                        if v in (app.GetActiveNetworkVariations() or []):
                            v.Deactivate()
                if not (conservar and (es_con or (es_cargas and plan.get('sincronizar_cargas')))):
                    esc = app.GetActiveScenario()
                    if esc is not foto['escenario']:
                        if esc is not None:
                            esc.Deactivate(0)
                        if foto['escenario'] is not None:
                            _activar(foto['escenario'])
                ldf = app.GetFromStudyCase('ComLdf')
                for a, valor in foto['ldf'].items():
                    if valor is not None and not (conservar and es_con and a in (plan.get('ajustes_flujo') or {})):
                        ldf.SetAttribute(a, valor)
                if foto['fecha'] is not None and _leer(caso, 'iStudyTime') != foto['fecha']:
                    caso.SetAttribute('iStudyTime', foto['fecha'])
                if foto['etapa'] is not None:
                    foto['etapa'].Activate(1)
            except Exception as exc:
                errores.append(f'{nombre}: {exc}')
        if not conservar:
            for v in reversed(nuevas):
                try:
                    v.Deactivate()
                    if out['accion'] == 'evaluar':
                        v.Delete()
                except Exception as exc:
                    errores.append(f'variación propia {_ruta(v)}: {exc}')
            for escenario_propio in (copia, copia_cargas):
                if escenario_propio is None:
                    continue
                try:
                    if _ruta(app.GetActiveScenario()) == _ruta(escenario_propio):
                        escenario_propio.Deactivate(0)
                    escenario_propio.Delete()
                except Exception as exc:
                    errores.append(f'escenario propio: {exc}')
        try:
            if previo_proyecto is not None and app.GetActiveProject() is not previo_proyecto:
                _activar(previo_proyecto)
            if previo_caso is not None:
                _activar(previo_caso)
        except Exception as exc:
            errores.append(f'estado inicial: {exc}')
        out['restauracion_errores'] = errores
        if errores:
            out.update(status='BLOQUEADO_PERSISTENCIA', aceptada=False, persistida=False)
            return out, 2


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
    except Exception as exc:
        traceback.print_exc()
        informe, codigo = {'status': 'BLOQUEADO_DATOS', 'aceptada': False, 'error': str(exc)}, 2
    if informe.get('restauracion_errores'):
        codigo = 2
    Path(args.output_json).write_text(json.dumps(informe, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Informe: {args.output_json}', flush=True)
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
