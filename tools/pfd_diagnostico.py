#!/usr/bin/env python
"""Importa un fichero ``.pfd`` en DIgSILENT y diagnostica en solo lectura cómo está hecho (spec 004, RF-81 a RF-107).

Un ``.pfd`` (PIT, PIDE u otro estudio) trae sus redes, sus casos de estudio, sus escenarios de operación y las
variaciones donde se hacen los proyectos nuevos. El guion lo importa en un proyecto nuevo de la carpeta de
proyectos del conversor (spec 005) y dice, sin escribir nada en él ni calcular:

- las redes (``ElmNet``) con sus alimentadores (``ElmFeeder``, en la carpeta «Feeders» de los datos de red);
- cada caso de estudio con su escenario, sus variaciones activas y su hora de estudio, y cuál estaba activo;
- cada escenario de operación con los casos que lo usan;
- cada variación con sus etapas, su fecha, lo que cada etapa da de alta, de baja o cambia, y en qué caso y con qué
  escenario se estudia;
- las cargas de cada caso (P, Q, escala, característica y alimentador), con sus totales y las diferencias entre
  casos;
- el recuento de elementos de red y de tipos (``Typ*``) por clase, y el aviso de una exportación reducida.

Cada ``.pfd`` se identifica por su huella (sha256), no por su nombre: con la misma huella se reutiliza el proyecto
ya importado (y se avisa si cambió en DIgSILENT después); con el mismo nombre y otra huella es una versión nueva, que
va a un proyecto nuevo con el nombre base y dice qué cambió frente a la anterior, cuyo proyecto se renombra con
``_anterior_<sha10>_<AAAAMMDD-HHMMSS>`` y se conserva (nunca se borra). ``--reimportar`` crea siempre otro proyecto
con su sufijo.

Propiedades de ``ComPfdimport`` (ayuda de PowerFactory 2024): ``GetImportedObjects()`` en la Python Reference,
§5.4.31; ``g_file`` («PFD file»), ``g_target`` («New Path») y ``activatePrj`` («Activate project after import») en el
diálogo del User Manual, §8.1.4.3, con el nombre de atributo de los textos de la ayuda (``localisation/<idioma>/
data.db``). En una etapa, ``IntSdel`` es un «Delete Object» y ``root_id`` («Original Location») el objeto que cambia.

El JSON y el informe de texto se reescriben tras cada sección y en la salida, también si algo revienta (008:RF-17).
Al terminar quedan activos el proyecto y el caso que lo estaban antes. Se ejecuta con el Python que exige la API.

    python tools/pfd_diagnostico.py --pfd ESTUDIO.pfd --output-json diagnostico.json
           [--informe diagnostico.txt] [--carpeta NOMBRE] [--reimportar]

Códigos de salida: 0 bien (puede haber avisos); 1 error al leer el proyecto o al restaurar el activo (el informe
lleva lo leído y el error); 2 uso: el fichero no existe, no es ``.pfd`` o la carpeta no es válida; 3 API de
PowerFactory no disponible; 4 la importación falló.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from convertersmartgrid.carpeta_pf import (  # noqa: E402
    LARGO_MAXIMO, NO_ADMITIDOS, CarpetaError, alimentadores_de, asegurar_carpeta, nombre_de_perfil, nombre_libre,
    proyectos_de, validar_nombre,
)

ESQUEMA = 'csg-pfd-diagnostico-v1'
#: Prefijo de la marca que el guion deja en ``desc`` del proyecto que importa (RF-82, RF-101).
MARCA = 'CSG_PFD:'
#: Diferencia de P o Q (MW, Mvar) a partir de la cual dos casos difieren (RF-95).
TOLERANCIA = 1e-6
#: Con tantas etapas vigentes de la misma fecha en un caso, DIgSILENT no aplica ninguna (medido el 2026-10-15).
ETAPAS_EMPATADAS = 3

USO, SIN_API, IMPORTACION = 2, 3, 4


class ErrorDeUso(ValueError):
    """Fichero o carpeta que no se pueden usar: código 2."""


class ErrorDeImportacion(RuntimeError):
    """``ComPfdimport`` no dejó un proyecto: código 4."""


# --------------------------------------------------------------------------- utilidades
def huella_fichero(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, 'rb') as f:
        for bloque in iter(lambda: f.read(1 << 20), b''):
            h.update(bloque)
    return h.hexdigest()


def _nombre(obj) -> str:
    return str(getattr(obj, 'loc_name', '') or '') if obj is not None else ''


def _ruta(obj) -> str:
    try:
        return str(obj.GetFullName() or '')
    except Exception:  # noqa: BLE001 - un objeto sin ruta no se puede comparar
        return ''


def _clase(obj) -> str:
    try:
        return str(obj.GetClassName())
    except Exception:  # noqa: BLE001
        return ''


def _misma(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    ra = _ruta(a)
    return bool(ra) and ra == _ruta(b)


def _numero(obj, atributo):
    try:
        valor = getattr(obj, atributo)
    except Exception:  # noqa: BLE001  # justificado: la API de PowerFactory lanza errores distintos según la versión (AttributeError, RuntimeError de COM); un atributo que no se puede leer es «sin dato», y el diagnóstico lo dice como ausente
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _contenido(obj, patron='*', recursivo=0) -> list:
    return list(obj.GetContents(patron, recursivo) or []) if obj is not None else []


def _fecha(segundos):
    """``(fecha ISO, año)`` de un instante de DIgSILENT en segundos, o ``(None, None)``."""
    if segundos is None:
        return None, None
    try:
        dt = datetime.fromtimestamp(float(segundos), tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None, None
    return dt.strftime('%Y-%m-%d %H:%M:%S'), dt.year


def _carpetas(prj, tipo: str) -> list:
    """Carpetas del proyecto con ``iopt_typ`` ``tipo``, en el proyecto o un nivel por debajo (nunca el árbol)."""
    hallados = []
    for c in _contenido(prj, '*.IntPrjfolder'):
        if getattr(c, 'iopt_typ', None) == tipo:
            hallados.append(c)
        for d in _contenido(c, '*.IntPrjfolder'):
            if getattr(d, 'iopt_typ', None) == tipo:
                hallados.append(d)
    return hallados


def _de_carpetas(prj, tipo: str, clase: str) -> list:
    vistos, salida = set(), []
    for carpeta in _carpetas(prj, tipo):
        for o in _contenido(carpeta, f'*.{clase}', 1):
            clave = _ruta(o) or id(o)
            if clave not in vistos:
                vistos.add(clave)
                salida.append(o)
    return sorted(salida, key=lambda o: _nombre(o).lower())


def _datos_de_red(prj) -> list:
    return _carpetas(prj, 'netdat') or [prj]


def marca_de(prj) -> dict | None:
    """La marca ``CSG_PFD:`` de ``desc`` del proyecto, o None si no la tiene."""
    desc = getattr(prj, 'desc', None)
    lineas = desc if isinstance(desc, (list, tuple)) else [desc] if desc else []
    for linea in lineas:
        if isinstance(linea, str) and linea.startswith(MARCA):
            try:
                return json.loads(linea[len(MARCA):])
            except ValueError:
                return None
    return None


def _escribir_marca(prj, datos: dict) -> None:
    desc = getattr(prj, 'desc', None)
    lineas = [x for x in (desc if isinstance(desc, (list, tuple)) else [desc] if desc else [])
              if not (isinstance(x, str) and x.startswith(MARCA))]
    prj.desc = lineas + [MARCA + json.dumps(datos, sort_keys=True, ensure_ascii=False)]


def nombre_base(fichero: str, sha: str, indice: int, total: int) -> str:
    """``<fichero>_<huella[:10]>`` (y ``_<n>`` si el ``.pfd`` trae varios proyectos), en 40 caracteres (RF-81)."""
    limpio = ''.join('_' if ch in NO_ADMITIDOS else ch for ch in Path(fichero).stem).strip() or 'pfd'
    cola = f'_{sha[:10]}' + (f'_{indice + 1}' if total > 1 else '')
    # Se reservan 3 caracteres para el sufijo de ``nombre_libre`` (RF-84).
    return limpio[:LARGO_MAXIMO - len(cola) - 3] + cola


# --------------------------------------------------------------------------- activar y restaurar
def _activar_proyecto(app, prj) -> None:
    if _misma(app.GetActiveProject(), prj):
        return
    rc = prj.Activate()
    if rc not in (None, 0, 1) or not _misma(app.GetActiveProject(), prj):
        raise RuntimeError(f'Activate devolvió {rc}; no se confirmó el proyecto {_ruta(prj)}')


def _activar_caso(app, caso) -> bool:
    if not _misma(app.GetActiveStudyCase(), caso):
        caso.Activate()
    return _misma(app.GetActiveStudyCase(), caso)


def _volver_al_caso(app, caso) -> None:
    """Deja activo ``caso`` o, si era None, ninguno (RF-100). No toca escenarios: ``Deactivate`` sin argumento descarta."""
    activo = app.GetActiveStudyCase()
    if caso is None:
        if activo is not None:
            activo.Deactivate()
        return
    if not _activar_caso(app, caso):
        raise RuntimeError(f'No se pudo volver al caso {_nombre(caso)!r}')


def restaurar(app, proyecto, caso) -> None:
    """Deja activos el proyecto y el caso de antes (RF-100)."""
    if proyecto is None:
        activo = app.GetActiveProject()
        if activo is not None:
            activo.Deactivate()
        if app.GetActiveProject() is not None:
            raise RuntimeError('No se pudo dejar DIgSILENT sin proyecto activo, como estaba')
        return
    _activar_proyecto(app, proyecto)
    _volver_al_caso(app, caso)


# --------------------------------------------------------------------------- lectura
def _red_de(alim):
    """La ``ElmNet`` de un alimentador: subiendo desde él o desde la barra de su cubículo de cabecera."""
    for inicio in (alim, getattr(getattr(alim, 'obj_id', None), 'cterm', None)):
        actual, pasos = inicio, 0
        while actual is not None and pasos < 50:
            if _clase(actual) == 'ElmNet':
                return actual
            actual, pasos = actual.GetParent(), pasos + 1
    return None


def leer_redes(prj) -> dict:
    """RF-86: redes con sus alimentadores; los que no cuelgan de ninguna red, aparte."""
    datos = _datos_de_red(prj)
    redes = {}
    for d in datos:
        for net in _contenido(d, '*.ElmNet', 1):
            if 'summary' not in _nombre(net).lower():
                redes.setdefault(_ruta(net), {'red': _nombre(net), 'alimentadores': []})
    sin_red = []
    for d in datos:
        for alim in _contenido(d, '*.ElmFeeder', 1):
            net = _red_de(alim)
            if net is not None and _ruta(net) in redes:
                redes[_ruta(net)]['alimentadores'].append(_nombre(alim))
            else:
                sin_red.append(_nombre(alim))
    salida = sorted(redes.values(), key=lambda r: r['red'].lower())
    for r in salida:
        r['alimentadores'].sort(key=str.lower)
    nombres, nota = alimentadores_de(prj)
    return {'redes': salida, 'alimentadores_sin_red': sorted(set(sin_red), key=str.lower),
            'alimentadores': nombres, 'nota': nota}


def _cambio_de_etapa(obj) -> dict:
    """RF-91: alta, baja o cambio de un objeto de la etapa, con la clase y el nombre del elemento."""
    raiz = getattr(obj, 'root_id', None)
    if _clase(obj) == 'IntSdel':
        objetivo = raiz if raiz is not None else obj
        return {'tipo': 'baja', 'clase': _clase(raiz) if raiz is not None else None, 'nombre': _nombre(objetivo)}
    if raiz is not None:
        return {'tipo': 'cambio', 'clase': _clase(raiz), 'nombre': _nombre(raiz)}
    return {'tipo': 'alta', 'clase': _clase(obj), 'nombre': _nombre(obj)}


def leer_variaciones(prj) -> list[dict]:
    """RF-90, RF-91: variaciones con sus etapas, la fecha de cada etapa y lo que da de alta, de baja o cambia."""
    salida = []
    for v in _de_carpetas(prj, 'scheme', 'IntScheme'):
        etapas = []
        for s in sorted(_contenido(v, '*.IntSstage', 1), key=lambda e: (_numero(e, 'tAcTime') or 0, _nombre(e))):
            t = _numero(s, 'tAcTime')
            fecha, anio = _fecha(t)
            try:
                excluida = bool(int(s.IsExcluded() or 0)) if hasattr(s, 'IsExcluded') else False
            except Exception:  # noqa: BLE001 - versiones sin el método
                excluida = False
            cambios = sorted((_cambio_de_etapa(o) for o in _contenido(s)
                              if _clase(o) not in ('IntSstage', 'IntScheme')),
                             key=lambda c: (str(c['tipo']), str(c['clase'] or ''), str(c['nombre'])))
            etapas.append({'etapa': _nombre(s), 'ruta': _ruta(s), 'instante': t, 'fecha': fecha, 'anio': anio,
                           'excluida': excluida, 'cambios': cambios,
                           'altas': sum(c['tipo'] == 'alta' for c in cambios),
                           'bajas': sum(c['tipo'] == 'baja' for c in cambios),
                           'cambiados': sum(c['tipo'] == 'cambio' for c in cambios)})
        salida.append({'variacion': _nombre(v), 'ruta': _ruta(v), 'etapas': etapas})
    return salida


def leer_recuento(prj) -> dict:
    """RF-96: elementos de red (``Elm*``, ``Sta*``) y tipos (``Typ*``) del proyecto, por clase."""
    elementos, usados = {}, {}
    for d in _datos_de_red(prj):
        for o in _contenido(d, '*', 1):
            clase = _clase(o)
            if clase.startswith(('Elm', 'Sta')):
                elementos[clase] = elementos.get(clase, 0) + 1
                tipo = getattr(o, 'typ_id', None)
                if tipo is not None and _clase(tipo).startswith('Typ'):
                    usados.setdefault(_clase(tipo), set()).add(_ruta(tipo) or id(tipo))
    tipos = {}
    for carpeta in _carpetas(prj, 'lib'):
        for o in _contenido(carpeta, '*', 1):
            if _clase(o).startswith('Typ'):
                tipos[_clase(o)] = tipos.get(_clase(o), 0) + 1
    return {'elementos': dict(sorted(elementos.items())), 'tipos': dict(sorted(tipos.items())),
            'tipos_usados': {k: len(v) for k, v in sorted(usados.items())}}


def _caracteristicas(carga) -> list[dict]:
    salida = []
    for ref in _contenido(carga, '*.ChaRef'):
        tipo = getattr(ref, 'typ_id', None)
        salida.append({'parametro': _nombre(ref), 'caracteristica': _nombre(tipo) or None,
                       'clase': _clase(tipo) or None})
    return sorted(salida, key=lambda c: str(c['parametro']))


def leer_cargas(app, prj) -> list[dict]:
    """RF-93: cargas del caso activo con P, Q, escala, característica y alimentador."""
    de_alimentador = {}
    for d in _datos_de_red(prj):
        for alim in _contenido(d, '*.ElmFeeder', 1):
            for c in list(alim.GetObjs('ElmLod') or []):
                de_alimentador.setdefault(_ruta(c), _nombre(alim))
    cargas = []
    for c in list(app.GetCalcRelevantObjects('*.ElmLod') or []):
        fuera = _numero(c, 'outserv')
        cargas.append({'carga': _nombre(c), 'ruta': _ruta(c), 'alimentador': de_alimentador.get(_ruta(c)),
                       'p_mw': _numero(c, 'plini'), 'q_mvar': _numero(c, 'qlini'), 'escala': _numero(c, 'scale0'),
                       'fuera_de_servicio': bool(fuera) if fuera is not None else None,
                       'caracteristicas': _caracteristicas(c)})
    return sorted(cargas, key=lambda c: str(c['ruta']))


def totales(cargas: list[dict]) -> dict:
    """RF-94: P y Q por alimentador y del proyecto (las de fuera de servicio no suman)."""
    por = {}
    total = {'p_mw': 0.0, 'q_mvar': 0.0, 'cargas': 0}
    for c in cargas:
        if c.get('fuera_de_servicio'):
            continue
        clave = c['alimentador'] or '(sin alimentador)'
        t = por.setdefault(clave, {'p_mw': 0.0, 'q_mvar': 0.0, 'cargas': 0})
        for d in (t, total):
            d['p_mw'] += c['p_mw'] or 0.0
            d['q_mvar'] += c['q_mvar'] or 0.0
            d['cargas'] += 1
    redondeo = lambda d: {k: (round(v, 9) if isinstance(v, float) else v) for k, v in d.items()}  # noqa: E731
    return {'por_alimentador': {k: redondeo(v) for k, v in sorted(por.items())}, 'proyecto': redondeo(total)}


def diferencias(referencia: dict, otro: dict) -> dict:
    """RF-95: cargas que solo están en uno de los dos casos o cuya P o Q difieren."""
    a = {c['ruta']: c for c in referencia['cargas']}
    b = {c['ruta']: c for c in otro['cargas']}
    distintas = []
    for ruta in sorted(set(a) & set(b)):
        for k in ('p_mw', 'q_mvar'):
            va, vb = a[ruta][k], b[ruta][k]
            if va is None or vb is None or abs(va - vb) > TOLERANCIA:
                if va != vb:
                    distintas.append({'carga': a[ruta]['carga'], 'magnitud': k, 'referencia': va, 'caso': vb})
    return {'caso': otro['caso'], 'referencia': referencia['caso'],
            'solo_en_el_caso': sorted(b[r]['carga'] for r in set(b) - set(a)),
            'solo_en_la_referencia': sorted(a[r]['carga'] for r in set(a) - set(b)),
            'distintas': distintas}


# --------------------------------------------------------------------------- diagnóstico
def diagnosticar(app, prj, guardar=lambda: None, diag: dict | None = None) -> dict:
    """RF-85 a RF-97: diagnóstico de solo lectura del proyecto ``prj``; ``diag`` se rellena por secciones."""
    diag = {} if diag is None else diag
    diag.update({'proyecto': _nombre(prj), 'ruta': _ruta(prj), 'avisos': []})
    avisos = diag['avisos']
    _activar_proyecto(app, prj)
    caso_inicial = app.GetActiveStudyCase()
    diag['caso_activo'] = _nombre(caso_inicial) or None                                    # RF-88
    try:
        diag['red'] = leer_redes(prj)                                                      # RF-86
        if diag['red']['nota']:
            avisos.append(diag['red']['nota'])
        guardar()
        diag['variaciones'] = leer_variaciones(prj)                                        # RF-90, RF-91
        diag['recuento'] = leer_recuento(prj)                                              # RF-96
        diag['recuento']['caso'] = diag['caso_activo']
        escenarios = _de_carpetas(prj, 'scen', 'IntScenario')
        diag['escenarios'] = [{'escenario': _nombre(e), 'ruta': _ruta(e), 'casos': []} for e in escenarios]
        diag['casos'] = []
        guardar()
        for caso in _de_carpetas(prj, 'study', 'IntCase'):                                 # RF-87, RF-93
            if not _activar_caso(app, caso):
                avisos.append(f'No se pudo activar el caso {_nombre(caso)!r}: no se lee.')
                continue
            t = _numero(caso, 'iStudyTime')
            fecha, _anio = _fecha(t)
            esc = app.GetActiveScenario()
            variaciones = list(app.GetActiveNetworkVariations() or [])
            cargas = leer_cargas(app, prj)
            diag['casos'].append({
                'caso': _nombre(caso), 'ruta': _ruta(caso), 'hora_estudio': t, 'fecha_estudio': fecha,
                'escenario': _nombre(esc) or None, 'escenario_ruta': _ruta(esc) or None,
                'variaciones_activas': sorted(_nombre(v) for v in variaciones),
                'variaciones_rutas': sorted(_ruta(v) for v in variaciones),
                'cargas': cargas, 'totales': totales(cargas)})                             # RF-94
            guardar()
    finally:
        _volver_al_caso(app, caso_inicial)
    _completar(diag)
    guardar()
    return diag


def _completar(diag: dict) -> None:
    """Lo que sale de cruzar lo leído: escenarios por caso, vigencias, diferencias y aviso de exportación reducida."""
    casos, avisos = diag['casos'], diag['avisos']
    por_ruta = {e['ruta']: e for e in diag['escenarios']}
    for c in casos:                                                                         # RF-89
        if c['escenario_ruta'] in por_ruta:
            por_ruta[c['escenario_ruta']]['casos'].append(c['caso'])
    for v in diag['variaciones']:                                                           # RF-92
        for e in v['etapas']:
            e['estudiada_en'] = [
                {'caso': c['caso'], 'escenario': c['escenario']} for c in casos
                if v['ruta'] in c['variaciones_rutas'] and not e['excluida']
                and (e['instante'] is None or c['hora_estudio'] is None or e['instante'] <= c['hora_estudio'])]
    for c in casos:
        fechas = {}
        for v in diag['variaciones']:
            for e in v['etapas']:
                if any(x['caso'] == c['caso'] for x in e.get('estudiada_en', [])):
                    fechas.setdefault(e['instante'], []).append(f"{v['variacion']}/{e['etapa']}")
        for t, nombres in sorted(fechas.items(), key=lambda kv: kv[0] or 0):
            if len(nombres) >= ETAPAS_EMPATADAS:
                avisos.append(f"Caso {c['caso']!r}: {len(nombres)} etapas vigentes con la misma fecha "
                              f"({_fecha(t)[0]}): DIgSILENT no aplica ninguna ({', '.join(sorted(nombres))}).")
    if casos:                                                                               # RF-95
        ref = next((c for c in casos if c['caso'] == diag['caso_activo']), casos[0])
        diag['caso_referencia'] = ref['caso']
        if diag['caso_activo'] is None:
            avisos.append(f"Ningún caso estaba activo; la referencia de las diferencias es {ref['caso']!r}.")
        diag['diferencias'] = [diferencias(ref, c) for c in casos if c is not ref]
    else:
        diag['caso_referencia'], diag['diferencias'] = None, []
    if len(casos) == 1 and not diag['escenarios'] and not diag['variaciones']:             # RF-97
        diag['exportacion_reducida'] = True
        avisos.append('El proyecto trae un solo caso de estudio, ningún escenario de operación y ninguna '
                      'variación: puede venir de una exportación reducida (instantánea). No trae los casos, '
                      'escenarios ni variaciones inactivos del original, y no se inventan.')
    else:
        diag['exportacion_reducida'] = False


def huella_diagnostico(diag: dict) -> str:
    """Huella de lo que el proyecto trae, sin el caso activo ni los avisos (RF-82, RF-83)."""
    contenido = {k: diag.get(k) for k in ('red', 'variaciones', 'recuento', 'escenarios', 'casos')}
    contenido['recuento'] = {k: v for k, v in (contenido['recuento'] or {}).items() if k != 'caso'}
    crudo = json.dumps(contenido, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)
    return hashlib.sha256(crudo.encode('utf-8')).hexdigest()


def resumen(diag: dict) -> dict:
    """Lo que se compara entre versiones de un ``.pfd`` (RF-102)."""
    return {
        'casos': sorted(c['caso'] for c in diag.get('casos', [])),
        'escenarios': sorted(e['escenario'] for e in diag.get('escenarios', [])),
        'variaciones': {v['variacion']: sorted(e['etapa'] for e in v['etapas']) for v in diag.get('variaciones', [])},
        'cargas_por_alimentador': {c['caso']: c['totales']['por_alimentador'] for c in diag.get('casos', [])},
        'recuento': (diag.get('recuento') or {}).get('elementos', {}),
    }


def comparar_versiones(anterior: dict, actual: dict) -> dict:
    """RF-102: qué cambió de la versión anterior a la actual."""
    def listas(clave):
        a, b = set(anterior.get(clave) or []), set(actual.get(clave) or [])
        return {'nuevos': sorted(b - a), 'quitados': sorted(a - b)}

    va, vb = anterior.get('variaciones') or {}, actual.get('variaciones') or {}
    variaciones = {'nuevas': sorted(set(vb) - set(va)), 'quitadas': sorted(set(va) - set(vb)),
                   'con_otras_etapas': sorted(k for k in set(va) & set(vb) if va[k] != vb[k])}
    cargas = []
    ca, cb = anterior.get('cargas_por_alimentador') or {}, actual.get('cargas_por_alimentador') or {}
    for caso in sorted(set(ca) | set(cb)):
        fa, fb = ca.get(caso) or {}, cb.get(caso) or {}
        for alim in sorted(set(fa) | set(fb)):
            pa, pb = (fa.get(alim) or {}).get('p_mw'), (fb.get(alim) or {}).get('p_mw')
            qa, qb = (fa.get(alim) or {}).get('q_mvar'), (fb.get(alim) or {}).get('q_mvar')
            if pa is None or pb is None or qa is None or qb is None or abs(pa - pb) > TOLERANCIA \
                    or abs(qa - qb) > TOLERANCIA:
                cargas.append({'caso': caso, 'alimentador': alim, 'p_mw_antes': pa, 'p_mw_ahora': pb,
                               'q_mvar_antes': qa, 'q_mvar_ahora': qb})
    ra, rb = anterior.get('recuento') or {}, actual.get('recuento') or {}
    recuento = {k: {'antes': ra.get(k, 0), 'ahora': rb.get(k, 0)}
                for k in sorted(set(ra) | set(rb)) if ra.get(k, 0) != rb.get(k, 0)}
    return {'casos': listas('casos'), 'escenarios': listas('escenarios'), 'variaciones': variaciones,
            'cargas_por_alimentador': cargas, 'recuento': recuento}


# --------------------------------------------------------------------------- importación
def importados(destino) -> list[tuple[str, object, dict]]:
    """``(ruta, proyecto, marca)`` de los proyectos de la carpeta importados por este guion (sin activarlos)."""
    salida = []
    for ruta, prj in proyectos_de(destino):
        m = marca_de(prj)
        if m:
            salida.append((ruta, prj, m))
    return salida


def nombre_anterior(fichero: str, sha_anterior: str, sello: str) -> str:
    """RF-103: ``<fichero>_anterior_<sha10>_<AAAAMMDD-HHMMSS>`` en 40 caracteres; se recorta el fichero, no el sufijo."""
    limpio = ''.join('_' if ch in NO_ADMITIDOS else ch for ch in Path(fichero).stem).strip() or 'pfd'
    cola = f'_anterior_{sha_anterior[:10]}_{sello}'
    return limpio[:max(0, LARGO_MAXIMO - len(cola))] + cola


def renombrar_anteriores(app, destino, anteriores, fichero: str, sha: str, informe: dict) -> None:
    """RF-103, RF-105, RF-106: la versión anterior se renombra y se conserva; si está activa, se desactiva antes.

    Solo cambia el nombre y añade ``anterior`` a su marca, para no renombrarla otra vez con la versión siguiente.
    Nunca se borra ni se mueve (los duplicados de DGS de la web siguen 005:RF-22; los ``.pfd`` versionados, no).
    """
    sello = time.strftime('%Y%m%d-%H%M%S')
    for ruta, prj, marca in anteriores:
        antes = _nombre(prj)
        activo = _misma(app.GetActiveProject(), prj)
        if activo:
            prj.Deactivate()
        ahora = nombre_libre(destino, nombre_anterior(fichero, str(marca.get('sha256') or ''), sello))
        prj.loc_name = ahora
        _escribir_marca(prj, dict(marca, anterior={'nombre_antes': antes, 'renombrado': sello, 'por_sha256': sha}))
        informe['renombrados'].append({'antes': antes, 'ahora': ahora, 'sha256': marca.get('sha256'),
                                       'estaba_activo': activo})
        if activo:
            informe['avisos'].append(f'El proyecto {ruta!r} de la versión anterior estaba activo: se desactivó antes '
                                     f'de renombrarlo a {ahora!r}.')


def importar(app, usuario, destino, pfd: Path, sha: str, antes_de_nombrar=None, avisos=None) -> list:
    """RF-81, RF-84, RF-101: ``ComPfdimport`` en una carpeta provisional; cada proyecto, con su nombre, a ``destino``.

    ``antes_de_nombrar`` se llama cuando el ``.pfd`` ya se importó y antes de dar nombre a los proyectos nuevos: ahí
    se renombra la versión anterior (RF-103), que así no cambia si la importación falla. Con él, el proyecto nuevo
    toma el nombre base sin sufijo (RF-104) y, si otro lo ocupa, el sufijo libre, con un aviso.
    """
    n = 1
    ocupados = {_nombre(o).lower() for o in _contenido(destino)}
    provisional = f'_csg_pfd_{sha[:8]}'
    while provisional.lower() in ocupados:
        n += 1
        provisional = f'_csg_pfd_{sha[:8]}_{n}'
    carpeta = destino.CreateObject('IntFolder', provisional)
    if carpeta is None:
        raise ErrorDeImportacion('DIgSILENT no dejó crear la carpeta provisional de la importación.')
    com = usuario.CreateObject('ComPfdimport', f'CSG_pfd_{sha[:8]}')
    if com is None:
        raise ErrorDeImportacion('DIgSILENT no dejó crear el comando ComPfdimport.')
    try:
        com.g_file = str(pfd)          # «PFD file»
        com.g_target = carpeta         # «New Path»
        com.activatePrj = 0            # «Activate project after import»: no
        rc = com.Execute()
        objetos = list(com.GetImportedObjects() or [])
    finally:
        try:
            com.Delete()
        except Exception as exc:  # noqa: BLE001 - un comando que queda en el usuario no estorba; se dice
            print(f'AVISO: no se pudo borrar el comando de importación: {exc}', flush=True)
    proyectos = [o for o in objetos if _clase(o) == 'IntPrj'] or _contenido(carpeta, '*.IntPrj')
    if rc not in (None, 0) or not proyectos:
        if not _contenido(carpeta):
            carpeta.Delete()
        raise ErrorDeImportacion(f'ComPfdimport.Execute() devolvió {rc} y dejó {len(proyectos)} proyecto(s); '
                                 'mire la ventana de salida de DIgSILENT.')
    if antes_de_nombrar is not None:
        antes_de_nombrar()
    movidos = []
    for i, prj in enumerate(sorted(proyectos, key=lambda p: _nombre(p).lower())):
        if _misma(app.GetActiveProject(), prj):
            prj.Deactivate()          # un proyecto activo no se mueve
        original = _nombre(prj)
        base = nombre_base(pfd.name, sha, i, len(proyectos))
        prj.loc_name = nombre_libre(destino, base)
        if antes_de_nombrar is not None and prj.loc_name != base and avisos is not None:
            avisos.append(f'El nombre {base!r} ya lo tenía otro proyecto de la carpeta: el nuevo es {prj.loc_name!r}.')
        if int(destino.Move(prj) or 0) != 0:
            raise ErrorDeImportacion(f'No se pudo mover el proyecto importado {original!r} a la carpeta '
                                     f'{_nombre(destino)!r}; queda en {provisional!r}.')
        movidos.append((prj, original))
    if not _contenido(carpeta):
        carpeta.Delete()
    return movidos


def ejecutar(app, pfd: Path, carpeta: str, reimportar: bool, informe: dict, guardar) -> int:
    usuario = app.GetCurrentUser()
    destino = asegurar_carpeta(usuario, carpeta)
    sha = informe['sha256']
    previos = importados(destino)
    mismos = [(r, p, m) for r, p, m in previos if m.get('sha256') == sha]
    anteriores = [(r, p, m) for r, p, m in previos if m.get('sha256') != sha and m.get('fichero') == pfd.name]
    avisos = informe['avisos']
    if mismos and not reimportar:                                                           # RF-82, RF-83
        informe['modo'] = 'reutilizado'
        for ruta, prj, marca in sorted(mismos, key=lambda x: x[2].get('indice', 0)):
            diag = {}
            informe['proyectos'].append(diag)
            diagnosticar(app, prj, guardar, diag)
            if marca.get('huella') != huella_diagnostico(diag):
                aviso = (f'El proyecto {ruta!r} cambió en DIgSILENT después de importarlo: se diagnostica tal como '
                         'está y no se importa encima. Para partir del fichero, pida reimportar (proyecto nuevo).')
                diag['cambio_tras_importar'] = True
                diag['avisos'].append(aviso)
                avisos.append(aviso)
            else:
                diag['cambio_tras_importar'] = False
        return 0
    informe['modo'] = 'reimportado' if mismos else 'version_nueva' if anteriores else 'importado'
    if mismos:
        anteriores = []          # reimportar la misma huella no es una versión nueva (RF-84)
    vigentes = [x for x in anteriores if not x[2].get('anterior')]
    renombrar = (lambda: renombrar_anteriores(app, destino, vigentes, pfd.name, sha, informe)) if vigentes else None
    nuevos = importar(app, usuario, destino, pfd, sha, renombrar, avisos)                 # RF-81, RF-84, RF-101, RF-103
    informe['importados'] = [{'proyecto': _nombre(p), 'nombre_en_el_fichero': o} for p, o in nuevos]
    guardar()
    for i, (prj, original) in enumerate(nuevos):
        diag = {}
        informe['proyectos'].append(diag)
        diagnosticar(app, prj, guardar, diag)
        r = resumen(diag)
        # La marca es lo único que se escribe en el proyecto, y solo en el recién importado (RF-82).
        _escribir_marca(prj, {'sha256': sha, 'fichero': pfd.name, 'indice': i, 'nombre_en_el_fichero': original,
                              'importado': time.strftime('%Y-%m-%d %H:%M:%S'), 'huella': huella_diagnostico(diag),
                              'resumen': r})
        if anteriores:                                                                      # RF-102, RF-107
            base = vigentes or anteriores
            candidatos = [x for x in base if x[2].get('indice', 0) == i] or base
            ruta_ant, prj_ant, marca_ant = max(candidatos, key=lambda x: (str(x[2].get('importado', '')), x[0]))
            diag['version_anterior'] = {'proyecto': _nombre(prj_ant), 'nombre_antes': ruta_ant.split('/')[-1],
                                        'sha256': marca_ant.get('sha256'),
                                        'cambios': comparar_versiones(marca_ant.get('resumen') or {}, r)}
    for x in informe['renombrados']:                                                        # RF-107
        avisos.append('Versión nueva del fichero: el proyecto nuevo es '
                      + ', '.join(_nombre(p) for p, _o in nuevos)
                      + f"; el de la versión anterior, {x['antes']!r}, se renombró a {x['ahora']!r} y se conserva.")
    return 0


# --------------------------------------------------------------------------- informe
def informe_texto(informe: dict) -> str:
    """RF-98: el informe legible, sacado solo del JSON de la corrida."""
    lineas = [f"Diagnóstico de {informe.get('fichero')} (sha256 {str(informe.get('sha256'))[:16]}…)",
              f"Carpeta: {informe.get('carpeta')} · modo: {informe.get('modo')} · código {informe.get('codigo')}"]
    for e in informe.get('errores', []):
        lineas.append(f'ERROR: {e}')
    for a in informe.get('avisos', []):
        lineas.append(f'AVISO: {a}')
    for x in informe.get('renombrados', []):
        lineas.append(f"Versión anterior renombrada: {x['antes']} -> {x['ahora']}"
                      + (' (estaba activa; se desactivó antes)' if x.get('estaba_activo') else ''))
    for d in informe.get('proyectos', []):
        lineas += ['', f"== Proyecto {d.get('proyecto')} (caso activo al empezar: {d.get('caso_activo')})"]
        for a in d.get('avisos', []):
            lineas.append(f'  AVISO: {a}')
        red = d.get('red') or {}
        for r in red.get('redes', []):
            lineas.append(f"  Red {r['red']}: {len(r['alimentadores'])} alimentador(es): {', '.join(r['alimentadores'])}")
        if red.get('alimentadores_sin_red'):
            lineas.append(f"  Alimentadores sin red: {', '.join(red['alimentadores_sin_red'])}")
        for c in d.get('casos', []):
            t = c['totales']['proyecto']
            lineas.append(f"  Caso {c['caso']}: escenario {c['escenario']}, hora {c['fecha_estudio']}, variaciones "
                          f"{', '.join(c['variaciones_activas']) or '—'}; {t['cargas']} cargas, "
                          f"P {t['p_mw']:.6g} MW, Q {t['q_mvar']:.6g} Mvar")
            for alim, ta in c['totales']['por_alimentador'].items():
                lineas.append(f"    {alim}: {ta['cargas']} cargas, P {ta['p_mw']:.6g} MW, Q {ta['q_mvar']:.6g} Mvar")
        for e in d.get('escenarios', []):
            lineas.append(f"  Escenario {e['escenario']}: casos {', '.join(e['casos']) or '—'}")
        for v in d.get('variaciones', []):
            lineas.append(f"  Variación {v['variacion']}: {len(v['etapas'])} etapa(s)")
            for e in v['etapas']:
                donde = '; '.join(f"{x['caso']} ({x['escenario']})" for x in e.get('estudiada_en', [])) or 'ningún caso'
                lineas.append(f"    Etapa {e['etapa']} ({e['fecha']}, año {e['anio']}): {e['altas']} alta(s), "
                              f"{e['bajas']} baja(s), {e['cambiados']} cambio(s); se estudia en {donde}")
                for x in e['cambios']:
                    lineas.append(f"      {x['tipo']}: {x['clase']} {x['nombre']}")
        for dif in d.get('diferencias', []):
            lineas.append(f"  {dif['caso']} frente a {dif['referencia']}: {len(dif['solo_en_el_caso'])} carga(s) solo "
                          f"en el caso, {len(dif['solo_en_la_referencia'])} solo en la referencia, "
                          f"{len(dif['distintas'])} valor(es) distinto(s)")
        rec = d.get('recuento') or {}
        if rec:
            lineas.append('  Elementos: ' + ', '.join(f'{k} {v}' for k, v in rec.get('elementos', {}).items()))
            lineas.append('  Tipos: ' + ', '.join(f'{k} {v}' for k, v in rec.get('tipos', {}).items()))
        va = d.get('version_anterior')
        if va:
            lineas.append(f"  Frente a la versión anterior ({va['proyecto']}, antes {va.get('nombre_antes')}): "
                          + json.dumps(va['cambios'], ensure_ascii=False, sort_keys=True))
    if informe.get('traza'):
        lineas += ['', informe['traza']]
    return '\n'.join(lineas) + '\n'


def _escribir(ruta: Path, texto: str) -> None:
    temporal = ruta.with_name(ruta.name + '.tmp')
    temporal.write_text(texto, encoding='utf-8')
    os.replace(temporal, ruta)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Importa un .pfd en DIgSILENT y diagnostica en solo lectura sus redes, '
                                            'casos, escenarios, variaciones y cargas (spec 004, RF-81 a RF-107).')
    p.add_argument('--pfd', required=True, help='Fichero .pfd que se importa.')
    p.add_argument('--output-json', required=True, help='JSON del diagnóstico (se escribe aunque algo falle).')
    p.add_argument('--informe', help='Informe de texto; por defecto, el JSON con extensión .txt.')
    p.add_argument('--carpeta', help='Carpeta de DIgSILENT. Por defecto, la del perfil de empresa (spec 005).')
    p.add_argument('--reimportar', action='store_true',
                   help='Importa siempre en un proyecto nuevo, aunque ya haya uno con la misma huella.')
    args = p.parse_args(argv)
    salida = Path(args.output_json)
    texto = Path(args.informe) if args.informe else salida.with_suffix('.txt')
    pfd = Path(args.pfd)
    informe: dict[str, Any] = {'esquema': ESQUEMA, 'fichero': pfd.name, 'sha256': None, 'carpeta': None, 'modo': None,
               'proyectos': [], 'renombrados': [], 'avisos': [], 'errores': [], 'codigo': None}

    def guardar() -> None:
        _escribir(salida, json.dumps(informe, indent=2, ensure_ascii=False, default=str) + '\n')
        _escribir(texto, informe_texto(informe))

    codigo = 1
    try:
        try:
            if not pfd.is_file():
                raise ErrorDeUso(f'No existe el fichero {str(pfd)!r}.')
            if pfd.suffix.lower() != '.pfd':
                raise ErrorDeUso(f'{pfd.name!r} no es un fichero .pfd.')
            informe['carpeta'] = validar_nombre(args.carpeta) if args.carpeta is not None else nombre_de_perfil()
            informe['sha256'] = huella_fichero(pfd)
        except (ErrorDeUso, CarpetaError) as exc:
            informe['errores'].append(str(exc))
            codigo = USO
            return codigo
        from convertersmartgrid.pf_arnes import PFNoDisponible, conectar

        try:
            app = conectar('pfd_diagnostico.py')
        except PFNoDisponible as exc:
            informe['errores'].append(str(exc))
            codigo = SIN_API
            return codigo
        print(f"Carpeta: {informe['carpeta']} · {pfd.name} ({informe['sha256'][:16]}…)", flush=True)
        anterior, caso_anterior = app.GetActiveProject(), app.GetActiveStudyCase()
        try:
            codigo = ejecutar(app, pfd.resolve(), informe['carpeta'], args.reimportar, informe, guardar)
        except ErrorDeImportacion as exc:
            informe['errores'].append(str(exc))
            codigo = IMPORTACION
        except Exception as exc:  # noqa: BLE001 - el informe queda siempre escrito (008:RF-17, 004:RF-99)
            informe['errores'].append(f'{type(exc).__name__}: {exc}')
            informe['traza'] = traceback.format_exc()
            codigo = 1
        finally:
            try:
                restaurar(app, anterior, caso_anterior)                                     # RF-100
            except Exception as exc:  # noqa: BLE001 - se informa: el operador lo deja como estaba a mano
                informe['errores'].append(f'No se pudo restaurar el proyecto y el caso activos: {exc}')
                codigo = codigo or 1
        return codigo
    finally:
        informe['codigo'] = codigo
        guardar()
        for e in informe['errores']:
            print(f'ERROR: {e}', flush=True)
        for a in informe['avisos']:
            print(f'AVISO: {a}', flush=True)
        print(f"Diagnóstico de {pfd.name}: {len(informe['proyectos'])} proyecto(s), código {codigo}.", flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
