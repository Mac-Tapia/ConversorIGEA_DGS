#!/usr/bin/env python
"""Demandas y cargas nuevas en un proyecto existente de DIgSILENT (spec 004).

Recibe el plan de ``igea_dgs.cargas_pf.armar_plan``: el proyecto, los alimentadores
elegidos en orden, las demandas por SED y las cargas nuevas. No necesita nada de la
conversión: qué carga coincide y dónde se conecta cada carga nueva se decide aquí,
mirando el proyecto (RF-1).

Sustituye a tres guiones que hacían lo mismo con distinta envoltura, y corrige lo que
encontró la revisión del 2026-10-08:

- Todo va a **una variación nueva** con nombre libre (RF-3, RF-4). Antes: un escenario
  por alimentador, que nunca pueden estar activos a la vez, o la red base sin vuelta
  atrás.
- Una SED sin coincidencia se **omite** y se informa; no es un error ni deshace nada
  (RF-7).
- La línea de enlace usa un **tipo que ya existe** en el proyecto, con su R y X (RF-12).
  Antes se creaba un ``TypLne`` con R y X a cero si el código no estaba.
- La carga nueva se escribe **como una demanda**: solo los datos de su modo y releída
  (RF-14). Antes se escribían P, Q, cos φ y S, y en modo P–cos φ DIgSILENT recalculaba P.
- Tensiones y frecuencia salen del proyecto (RF-13), no de 22,9 kV, 0,22 kV y 60 Hz.
- Se cancela **entre alimentadores** (RF-19): la web crea ``--cancel-file`` y el guion
  termina el alimentador en curso.

    python tools/cargas_pf.py --plan plan.json --output-json informe.json \\
        [--simular] [--cancel-file cancelar.flag]

Spec 011: si el proyecto ya tiene los casos «Caso base», «Sin proyecto» y «Con
proyecto», las demandas se escriben en «Sin proyecto» (RF-51) y las cargas nuevas en
«Con proyecto» (RF-52), con el escenario de cada caso apagado mientras se escribe
(RF-55); la variación de las demandas queda activa también en «Con proyecto» (RF-54) y,
al terminar, «Con proyecto» tiene activas todas las cargas nuevas (011:RF-8). El «Caso
base» no se toca (RF-53).

Códigos de salida: 0 hecho, 2 algún fallo al escribir o crear, 3 sin API.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import traceback
from collections import Counter
from pathlib import Path

from igea_dgs.native_action import native_action_block_report

MAX_NOMBRE = 40               # loc_name de DIgSILENT
REFERENCIAS_DIBUJO = 12       # barras dibujadas cercanas con que se mide la escala
RADIO_TIERRA_M = 6_371_000.0


# =========================================================================== nombres
def nombre_pf(texto: str) -> str:
    """DIgSILENT admite 40 caracteres y no acepta . / \\ ni otros signos en loc_name."""
    return re.sub(r'[^A-Za-z0-9_\-]', '_', texto)[:MAX_NOMBRE]


def nombre_libre(folder, clase: str, base: str) -> str:
    """``base`` o, si ya existe, ``base_2``, ``base_3``… sin pasar de 40 caracteres (RF-4).

    Con la hora al minuto y el nombre recortado, dos ejecuciones daban el mismo nombre,
    y deshacer por nombre podía borrar el trabajo de la otra.
    """
    base = nombre_pf(base)
    usados = {o.loc_name for o in folder.GetContents(f'*.{clase}')}
    if base not in usados:
        return base
    n = 2
    while True:
        sufijo = f'_{n}'
        candidato = base[:MAX_NOMBRE - len(sufijo)] + sufijo
        if candidato not in usados:
            return candidato
        n += 1


# =========================================================================== geometría
def gps_de(obj) -> tuple[float, float] | None:
    try:
        lat, lon = float(obj.GPSlat), float(obj.GPSlon)
    except (AttributeError, TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)) or (lat == 0 and lon == 0):
        return None      # DIgSILENT deja 0,0 cuando no hay posición
    return lat, lon


def distancia_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Haversine entre dos (lat, lon)."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * RADIO_TIERRA_M * math.asin(math.sqrt(h))


def a_metros(origen: tuple[float, float], punto: tuple[float, float]) -> tuple[float, float]:
    """(lat, lon) → metros locales este/norte respecto a ``origen``; basta para dibujar."""
    norte = math.radians(punto[0] - origen[0]) * RADIO_TIERRA_M
    este = math.radians(punto[1] - origen[1]) * RADIO_TIERRA_M * math.cos(math.radians(origen[0]))
    return este, norte


# =========================================================================== proyecto
def activar_proyecto(app, ruta: str, carpeta: str | None = None):
    """Activa el proyecto de ``ruta`` en la carpeta de importación (spec 005, RF-16).

    Antes buscaba por nombre en la raíz del usuario; los proyectos importados están ahora
    en la carpeta, y en la raíz puede quedar uno antiguo con el mismo nombre. Sin carpeta
    en el plan (planes anteriores a la spec 005), la del perfil de empresa. Respeta el
    caso de estudio activo del proyecto.
    """
    from igea_dgs.carpeta_pf import activar_proyecto as activar, nombre_de_perfil

    proyecto = activar(app, ruta, carpeta or nombre_de_perfil())
    if proyecto is None:
        return None
    if app.GetActiveStudyCase() is None:
        estudios = app.GetProjectFolder('study')
        casos = list(estudios.GetContents('*.IntCase')) if estudios else []
        if casos:
            casos[0].Activate()
    return proyecto


class Alimentadores:
    """Objetos de cada alimentador elegido, por clase. Sin ``ElmFeeder``, todo el proyecto."""

    def __init__(self, app, proyecto, elegidos):
        self.app = app
        self.elegidos = list(elegidos)
        self.elm = {f.loc_name: f for f in proyecto.GetContents('*.ElmFeeder', 1)}
        self.sin_elm = [f for f in self.elegidos if f not in self.elm]
        self._cache = {}

    def objetos(self, feeder: str, clase: str) -> list:
        clave = (feeder, clase)
        if clave not in self._cache:
            elm = self.elm.get(feeder)
            objs = []
            if elm is not None:
                try:
                    objs = list(elm.GetObjs(clase))
                except Exception:  # noqa: BLE001 - se cae a todo el proyecto
                    objs = []
            if not objs and elm is None:
                objs = list(self.app.GetCalcRelevantObjects(f'*.{clase}'))
            self._cache[clave] = objs
        return self._cache[clave]


# =========================================================================== medidas
# De ``ajuste_cabecera_pf.py`` (spec 006): la spec 007 mide la cabecera con y sin cada
# carga nueva, y el ajuste ya importa de aquí; al revés sería una importación circular.
def _num(obj, attr) -> float | None:
    try:
        v = float(obj.GetAttribute(attr))
    except Exception:  # noqa: BLE001 - atributo sin resultados o que no existe
        try:
            v = float(getattr(obj, attr))
        except Exception:  # noqa: BLE001
            return None
    return v if math.isfinite(v) else None


def potencia(obj) -> tuple[float, float]:
    """kW y kVAR que tiene escritos la carga, también si es desequilibrada."""
    if int(getattr(obj, 'i_sym', 0) or 0) == 1:
        p = sum(float(getattr(obj, f'plini{f}', 0.0) or 0.0) for f in 'rst')
        q = sum(float(getattr(obj, f'qlini{f}', 0.0) or 0.0) for f in 'rst')
    else:
        p, q = float(obj.plini or 0.0), float(obj.qlini or 0.0)
    return p * 1000.0, q * 1000.0


def medir_cabecera(app, elm):
    """Ejecuta el flujo y devuelve lo que entra por la cabecera del alimentador.

    La cabecera es la rama del cubículo ``obj_id`` del ``ElmFeeder``, en el lado de ese
    cubículo. ``m:Psum:busN`` es lo que sale de la barra hacia la rama: si el alimentador
    está orientado hacia la barra (``iorient`` = 1), lo que entra en él es lo contrario.
    """
    from igea_dgs.ajuste_cabecera import Medida

    ldf = app.GetFromStudyCase('ComLdf')
    rc = ldf.Execute()
    if rc != 0 or not app.IsLdfValid():
        return Medida(False, motivo=f'el flujo de carga no converge (código {rc})')
    return leer_cabecera(elm)


def leer_cabecera(elm):
    """Lo que entra por la cabecera según el último flujo, sin volver a ejecutarlo.

    La verificación de la spec 008 mide varios alimentadores con un solo flujo.
    """
    from igea_dgs.ajuste_cabecera import Medida

    cub = elm.obj_id
    rama = cub.obj_id
    lado = int(getattr(cub, 'obj_bus', 0) or 0) + 1
    p, q = _num(rama, f'm:Psum:bus{lado}'), _num(rama, f'm:Qsum:bus{lado}')
    if p is None or q is None:
        return Medida(False, motivo=f'sin resultados en la cabecera ({rama.loc_name})')
    signo = -1.0 if int(getattr(elm, 'iorient', 0) or 0) == 1 else 1.0
    return Medida(True, signo * p * 1000.0, signo * q * 1000.0)


# =========================================================================== demandas
def resolver_demandas(alims: Alimentadores, demandas: list[dict]):
    """Cada fila → (alimentador, ElmLod) o un motivo. Solo lectura (RF-6, RF-7, RF-8).

    La SED se busca en los alimentadores elegidos. Si está en dos (red unida), decide la
    hoja del libro si se llama como uno de ellos; si no, es ambigua.
    """
    indice = {}
    for feeder in alims.elegidos:
        por_nombre = {}
        for obj in alims.objetos(feeder, 'ElmLod'):
            por_nombre.setdefault(obj.loc_name, []).append(obj)
        indice[feeder] = por_nombre
    asignadas = {f: [] for f in alims.elegidos}
    omitidas, ambiguas = [], []
    usados = {}
    for fila in demandas:
        sed = fila['sed']
        donde = [(f, indice[f][sed]) for f in alims.elegidos if sed in indice[f]]
        if not donde:
            omitidas.append({'sed': sed, 'motivo': 'no está en los alimentadores elegidos'})
            continue
        if len(donde) > 1:
            por_hoja = [d for d in donde if d[0] == fila.get('hoja')]
            if len(por_hoja) != 1:
                ambiguas.append({'sed': sed, 'motivo': 'está en ' + ', '.join(f for f, _ in donde)})
                continue
            donde = por_hoja
        feeder, objs = donde[0]
        if len(objs) > 1:
            ambiguas.append({'sed': sed, 'motivo': f'{len(objs)} cargas con ese nombre en {feeder}'})
            continue
        obj = objs[0]
        if id(obj) in usados:
            omitidas.append({'sed': sed, 'motivo': f'repetida en el libro (ya en la hoja {usados[id(obj)]})'})
            continue
        usados[id(obj)] = fila.get('hoja')
        asignadas[feeder].append((fila, obj))
    return asignadas, omitidas, ambiguas


def foto_carga(obj) -> dict:
    nombres = ('mode_inp', 'i_sym', 'plini', 'qlini', 'slini', 'coslini', 'pf_recap',
               'plinir', 'plinis', 'plinit', 'qlinir', 'qlinis', 'qlinit')
    return {n: getattr(obj, n, None) for n in nombres}


def escribir_carga(obj, p_mw: float, q_mvar: float) -> None:
    """Escribe solo las ENTRADAS del modo de la carga (``mode_inp``), con el signo de Q.

    De P, Q, S y cos φ solo dos son datos y el resto se deriva: asignar los cuatro hacía
    que DIgSILENT recalculara P desde la S anterior y el cambio se perdía (RF-9).
    """
    s = math.hypot(p_mw, q_mvar)
    cos = abs(p_mw) / s if s else 1.0
    if int(getattr(obj, 'i_sym', 0) or 0) == 1:
        # Desequilibrada: P y Q por fase son los datos; se conserva el reparto.
        fases = ('r', 's', 't')
        p_old = [float(getattr(obj, f'plini{f}', 0.0) or 0.0) for f in fases]
        q_old = [float(getattr(obj, f'qlini{f}', 0.0) or 0.0) for f in fases]
        sp, sq = sum(p_old), sum(q_old)
        p_new = [x * p_mw / sp for x in p_old] if sp else [p_mw / 3.0] * 3
        q_new = [x * q_mvar / sq for x in q_old] if sq else [q_mvar / 3.0] * 3
        for f, pv, qv in zip(fases, p_new, q_new):
            setattr(obj, f'plini{f}', pv)
            setattr(obj, f'qlini{f}', qv)
        return
    modo = str(getattr(obj, 'mode_inp', '') or 'PC').upper()
    if modo == 'PQ':
        obj.plini, obj.qlini = p_mw, q_mvar
    elif modo == 'SC':
        obj.slini, obj.coslini = s, cos
    elif modo == 'SP':
        obj.slini, obj.plini = s, p_mw
    elif modo == 'QC':
        obj.qlini, obj.coslini = q_mvar, cos
    else:
        obj.plini, obj.coslini = p_mw, cos
    if modo in ('PC', 'SC', 'QC') and hasattr(obj, 'pf_recap'):
        obj.pf_recap = 1 if q_mvar < 0 else 0      # 1 = capacitiva


def error_relectura(obj, p_mw: float, q_mvar: float) -> str:
    """Vacío si DIgSILENT dejó lo pedido; si no, qué dejó. Recalcular no es aplicar."""
    foto = foto_carga(obj)
    if int(foto.get('i_sym') or 0) == 1:
        p = sum(float(foto.get(n) or 0.0) for n in ('plinir', 'plinis', 'plinit'))
        q = sum(float(foto.get(n) or 0.0) for n in ('qlinir', 'qlinis', 'qlinit'))
    else:
        p, q = float(foto.get('plini') or 0.0), float(foto.get('qlini') or 0.0)
    if abs(p - p_mw) > 1e-6 + 1e-4 * abs(p_mw) or abs(q - q_mvar) > 1e-6 + 1e-4 * abs(q_mvar):
        return f'DIgSILENT dejó P/Q={p:.6f}/{q:.6f} MW/Mvar (pedido {p_mw:.6f}/{q_mvar:.6f})'
    return ''


# =========================================================================== cargas nuevas
def _tipo_de_barra(barra):
    """Tipo de una línea que llega a la barra: tiene su R y X reales (RF-12)."""
    for cub in barra.GetContents('*.StaCubic'):
        obj = getattr(cub, 'obj_id', None)
        if obj is not None and obj.GetClassName() == 'ElmLne' and getattr(obj, 'typ_id', None) is not None:
            return obj.typ_id
    return None


def _red_de(obj):
    actual = obj
    while actual is not None:
        try:
            if actual.GetClassName() == 'ElmNet':
                return actual
            actual = actual.GetParent()
        except Exception:  # noqa: BLE001
            break
    return None


def _tension_bt(alims: Alimentadores, feeder: str) -> float | None:
    """BT más frecuente de los transformadores de SED del alimentador (RF-13)."""
    tensiones = Counter()
    for tr in alims.objetos(feeder, 'ElmTr2'):
        typ = getattr(tr, 'typ_id', None)
        valor = getattr(typ, 'utrn_l', None) if typ is not None else None
        if valor:
            tensiones[round(float(valor), 4)] += 1
    if not tensiones:
        return None
    return sorted(tensiones.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def resolver_nuevas(alims: Alimentadores, proyecto, nuevas: list[dict]):
    """Cada carga nueva → cómo se conecta, o el motivo para no crearla. Solo lectura.

    Devuelve (resueltas por alimentador, no creadas, avisos). Solo se buscan barras en
    los alimentadores marcados (spec 007, RF-25): las cargas del libro vienen aprobadas
    para ellos, y una fila que dice otro alimentador se conecta igual y se anota (RF-29).
    Con varios marcados, el de su columna si está entre ellos o, si no, el de la barra
    más cercana (RF-36).
    """
    tipos = {t.loc_name: t for t in proyecto.GetContents('*.TypLne', 1)}
    existentes = {o.loc_name for f in alims.elegidos for clase in ('ElmLod', 'ElmSubstat')
                  for o in alims.objetos(f, clase)}
    barras = {f: alims.objetos(f, 'ElmTerm') for f in alims.elegidos}
    resueltas = {f: [] for f in alims.elegidos}
    no_creadas, avisos = [], []
    # RF-28: un alimentador sin barras con GPS se dice una vez, no carga por carga.
    sin_gps = {f for f in alims.elegidos if not any(gps_de(b) for b in barras[f])}
    avisados = set()
    for fila in nuevas:
        sed = fila['sed']
        if sed in existentes:
            no_creadas.append({'sed': sed, 'motivo': 'ya existe en el alimentador (RF-15)'})
            continue
        candidatos = list(alims.elegidos)
        otro = ''
        if fila.get('alimentador'):
            if fila['alimentador'] in candidatos:
                candidatos = [fila['alimentador']]
            else:
                otro = fila['alimentador']
        punto = (fila['lat'], fila['lon']) if fila.get('lat') is not None else None
        eleccion = None
        if fila.get('barra'):
            halladas = [(f, b) for f in candidatos for b in barras[f] if b.loc_name == fila['barra']]
            if len(halladas) > 1:
                por_hoja = [h for h in halladas if h[0] == fila.get('hoja')]
                halladas = por_hoja if len(por_hoja) == 1 else halladas
            if len(halladas) != 1:
                motivo = (f"la barra {fila['barra']} no está en los alimentadores elegidos" if not halladas
                          else f"la barra {fila['barra']} está en varios alimentadores")
                no_creadas.append({'sed': sed, 'motivo': motivo})
                continue
            feeder, barra = halladas[0]
            pos = gps_de(barra)
            dist = distancia_m(pos, punto) if (pos and punto) else None
            eleccion = (feeder, barra, dist, 'barra indicada')
        elif punto is not None:
            mejor = None
            for f in candidatos:
                for b in barras[f]:
                    pos = gps_de(b)
                    if pos is None:
                        continue
                    d = distancia_m(pos, punto)
                    if mejor is None or (d, f, b.loc_name) < (mejor[2], mejor[0], mejor[1].loc_name):
                        mejor = (f, b, d)
            if mejor is None:
                nuevos = sorted(set(candidatos) & sin_gps - avisados)
                if nuevos:
                    avisos.append(f"Ninguna barra de {', '.join(nuevos)} tiene coordenadas en DIgSILENT: "
                                  'no se conecta por coordenadas ninguna carga suya (RF-28).')
                    avisados.update(nuevos)
                no_creadas.append({'sed': sed, 'motivo': 'ninguna barra de los alimentadores tiene GPS'})
                continue
            eleccion = (*mejor, 'barra más cercana por GPS')
        else:
            no_creadas.append({'sed': sed, 'motivo': 'sin barra ni coordenadas'})
            continue
        feeder, barra, dist, criterio = eleccion
        tipo, origen_tipo = None, ''
        if dist:                                   # hace falta una línea de enlace
            if fila.get('tipo_linea') and fila['tipo_linea'] in tipos:
                tipo, origen_tipo = tipos[fila['tipo_linea']], 'de la fila'
            else:
                tipo, origen_tipo = _tipo_de_barra(barra), 'de la red'
            if tipo is None:
                no_creadas.append({'sed': sed, 'motivo': f'ninguna línea llega a {barra.loc_name} y '
                                                         'la fila no da un tipo de línea del proyecto'})
                continue
        bt = fila.get('tension_bt_kv') or _tension_bt(alims, feeder)
        if not bt:
            no_creadas.append({'sed': sed, 'motivo': 'sin tensión de baja: ni en la fila ni en '
                                                     'los transformadores del alimentador'})
            continue
        red = _red_de(barra)
        resueltas[feeder].append({
            'fila': fila, 'barra': barra, 'distancia_m': dist, 'criterio': criterio,
            'nota': (f'el libro la da en {otro}, que no está marcado: se conecta a {feeder} (RF-29)'
                     if otro else None),
            'tipo': tipo, 'origen_tipo': origen_tipo,
            'tension_mt_kv': float(getattr(barra, 'uknom', 0) or 0),
            'tension_bt_kv': float(bt), 'red': red,
            'frecuencia_hz': float(getattr(red, 'frnom', 0) or 0) if red is not None else 0.0,
        })
        existentes.add(sed)
    return resueltas, no_creadas, avisos


def _tipo_trafo(alims, feeder, typ_folder, kva: float, mt: float, bt: float, frecuencia: float):
    """Tipo de transformador: el del alimentador que ya coincide o uno hecho a su imagen.

    Antes se creaba un ``TypTr2`` por SED con uk 4 % y Dyn5 fijos. Ahora se reutiliza el
    que tenga la misma potencia y tensiones; si no, se copia la impedancia y el grupo de
    conexión del más parecido del alimentador.
    """
    strn = kva / 1000.0
    tipos = [getattr(tr, 'typ_id', None) for tr in alims.objetos(feeder, 'ElmTr2')]
    tipos = [t for t in tipos if t is not None]
    for t in tipos:
        if (abs(float(t.strn) - strn) < 1e-9 and abs(float(t.utrn_h) - mt) < 1e-6
                and abs(float(t.utrn_l) - bt) < 1e-6):
            return t, False, ''
    modelo = min(tipos, key=lambda t: abs(float(t.strn) - strn), default=None)
    nombre = nombre_pf(f'TR_{kva:g}kVA_{mt:g}_{bt:g}kV')
    ya = [t for t in typ_folder.GetContents('*.TypTr2') if t.loc_name == nombre]
    if ya:
        return ya[0], False, ''
    nuevo = typ_folder.CreateObject('TypTr2', nombre)
    nuevo.nt2ph, nuevo.strn, nuevo.utrn_h, nuevo.utrn_l = 3, strn, mt, bt
    if frecuencia:
        nuevo.frnom = frecuencia
    aviso = ''
    if modelo is not None:
        escala = strn / float(modelo.strn) if float(modelo.strn) else 1.0
        for attr in ('uktr', 'tr2cn_h', 'tr2cn_l', 'nt2ag'):
            setattr(nuevo, attr, getattr(modelo, attr))
        nuevo.pcutr = float(getattr(modelo, 'pcutr', 0) or 0) * escala
    else:
        nuevo.uktr, nuevo.tr2cn_h, nuevo.tr2cn_l, nuevo.nt2ag = 4.0, 'D', 'YN', 5
        nuevo.pcutr = max(strn * 10.0, 0.1)
        aviso = (f'{nombre}: el alimentador no tiene transformadores de referencia; '
                 'uk 4 % y Dyn5 típicos, revíselos')
    return nuevo, True, aviso


def crear_carga(alims, proyecto, typ_folder, diagrama, feeder, r) -> dict:
    """Crea la carga resuelta en la etapa que graba. Devuelve lo creado (RF-14)."""
    fila, barra, red = r['fila'], r['barra'], r['red']
    sed = fila['sed']
    contenedor = red if red is not None else barra.GetParent()
    mt, bt = r['tension_mt_kv'], r['tension_bt_kv']
    enganche, linea, nueva_barra = barra, None, None
    if r['distancia_m']:
        nueva_barra = contenedor.CreateObject('ElmTerm', nombre_pf(f'NODE_{sed}'))
        nueva_barra.uknom, nueva_barra.iUsage, nueva_barra.outserv = mt, 1, 0
        nueva_barra.GPSlat, nueva_barra.GPSlon = float(fila['lat']), float(fila['lon'])
        linea = contenedor.CreateObject('ElmLne', nombre_pf(f'LNE_{sed}'))
        linea.typ_id = r['tipo']
        linea.dline = max(r['distancia_m'] / 1000.0, 1e-6)
        linea.nlnum = 1
        for extremo, (term, lado) in enumerate(((barra, 0), (nueva_barra, 1)), start=1):
            cub = term.CreateObject('StaCubic', nombre_pf(f'Cub{extremo}_LNE_{sed}'))
            cub.obj_id, cub.obj_bus = linea, lado
        enganche = nueva_barra
    sub = contenedor.CreateObject('ElmSubstat', nombre_pf(sed))
    sub.sShort, sub.sType = 'T', f"{fila['kva_instalado']:g} kVA"
    b_mt = sub.CreateObject('ElmTerm', nombre_pf(sed))
    b_mt.uknom, b_mt.iUsage = mt, 0
    b_bt = sub.CreateObject('ElmTerm', nombre_pf(f'{sed}_BT'))
    b_bt.uknom, b_bt.iUsage = bt, 0
    tipo_tr, tipo_nuevo, aviso = _tipo_trafo(alims, feeder, typ_folder, float(fila['kva_instalado']),
                                             mt, bt, r['frecuencia_hz'])
    tr = sub.CreateObject('ElmTr2', nombre_pf(f'TR_{sed}'))
    tr.typ_id, tr.ntnum, tr.outserv = tipo_tr, 1, 0
    for term, lado, nombre in ((b_mt, 0, 'Cub1_TR'), (b_bt, 1, 'Cub2_TR')):
        cub = term.CreateObject('StaCubic', nombre_pf(f'{nombre}_{sed}'))
        cub.obj_id, cub.obj_bus = tr, lado
    sw = sub.CreateObject('ElmCoup', nombre_pf(f'SW_{sed}'))
    sw.on_off, sw.aUsage, sw.nphase = 1, 'cbk', 3
    for term, lado, nombre in ((enganche, 0, 'Cub1_SW'), (b_mt, 1, 'Cub2_SW')):
        cub = term.CreateObject('StaCubic', nombre_pf(f'{nombre}_{sed}'))
        cub.obj_id, cub.obj_bus = sw, lado
    carga = sub.CreateObject('ElmLod', nombre_pf(sed))
    carga.mode_inp, carga.i_sym, carga.outserv = 'PC', 0, 0
    escribir_carga(carga, float(fila['plini_mw']), float(fila['qlini_mvar']))
    cub = b_bt.CreateObject('StaCubic', nombre_pf(f'Cub_{sed}'))
    cub.obj_id, cub.obj_bus = carga, 0
    error = error_relectura(carga, float(fila['plini_mw']), float(fila['qlini_mvar']))
    dibujo = None
    if diagrama is not None:
        try:
            dibujo = diagrama.dibujar(r, nueva_barra, linea, sub)
        except Exception as exc:  # noqa: BLE001 - sin dibujo la carga calcula igual
            dibujo = {'error': f'{type(exc).__name__}: {exc}'}
    return {
        'sed': sed, 'alimentador': feeder, 'barra': barra.loc_name, 'criterio': r['criterio'],
        'distancia_m': r['distancia_m'], 'tipo_linea': getattr(r['tipo'], 'loc_name', None),
        'origen_tipo_linea': r['origen_tipo'] or None, 'tension_mt_kv': mt, 'tension_bt_kv': bt,
        'kva_instalado': fila['kva_instalado'], 'kw': fila['kw'], 'kvar': fila['kvar'],
        'tipo_trafo': tipo_tr.loc_name, 'tipo_trafo_nuevo': tipo_nuevo,
        'aviso': aviso or None, 'error_relectura': error or None, 'dibujo': dibujo,
    }


# =========================================================================== dibujo
class Diagrama:
    """Símbolos ya dibujados del proyecto, para situar la carga nueva en el unifilar."""

    def __init__(self, proyecto):
        self.por_obj, self.tamanos = {}, {}
        for grfnet in proyecto.GetContents('*.IntGrfnet', 1):
            for grf in grfnet.GetContents('*.IntGrf'):
                obj = getattr(grf, 'pDataObj', None)
                if obj is not None:
                    self.por_obj[id(obj)] = (grf, grfnet, obj)
                sym = getattr(grf, 'sSymNam', '')
                if sym and sym not in self.tamanos:
                    self.tamanos[sym] = (grf.rSizeX, grf.rSizeY)

    def _pos(self, obj):
        hallado = self.por_obj.get(id(obj))
        return ((hallado[0].rCenterX, hallado[0].rCenterY), hallado[1]) if hallado else (None, None)

    def _escala(self, punto):
        """Terreno (m) → diagrama por mínimos cuadrados con las barras dibujadas más cercanas."""
        refs = []
        for grf, _net, obj in self.por_obj.values():
            gps = gps_de(obj)
            if gps is not None:
                refs.append((distancia_m(gps, punto), gps, (grf.rCenterX, grf.rCenterY)))
        refs = sorted(refs, key=lambda r: r[0])[:REFERENCIAS_DIBUJO]
        if len(refs) < 2:
            return None
        pts = [(*a_metros(punto, gps), gx, gy) for _d, gps, (gx, gy) in refs]
        mx = sum(p[0] for p in pts) / len(pts)
        my = sum(p[1] for p in pts) / len(pts)
        mgx = sum(p[2] for p in pts) / len(pts)
        mgy = sum(p[3] for p in pts) / len(pts)
        den = sum((p[0] - mx) ** 2 + (p[1] - my) ** 2 for p in pts)
        if den < 1.0:
            return None
        s = sum((p[0] - mx) * (p[2] - mgx) + (p[1] - my) * (p[3] - mgy) for p in pts) / den
        return None if s <= 0 else (lambda x, y: (s * (x - mx) + mgx, s * (y - my) + mgy))

    def _simbolo(self, grfnet, nombre, sym, obj, xy, rot=0):
        grf = grfnet.CreateObject('IntGrf', nombre_pf(nombre))
        grf.sSymNam, grf.pDataObj = sym, obj
        grf.rCenterX, grf.rCenterY = float(xy[0]), float(xy[1])
        grf.rSizeX, grf.rSizeY = map(float, self.tamanos.get(sym, (1.0, 1.0)))
        grf.iRot, grf.iVis, grf.iLevel, grf.iCol = rot, 1, 1, 1
        return grf

    def dibujar(self, r, nueva_barra, linea, sub):
        ancla, grfnet = self._pos(r['barra'])
        if ancla is None:
            return {'dibujada': False, 'motivo': f"{r['barra'].loc_name} no está en ningún diagrama"}
        fila = r['fila']
        destino = None
        if fila.get('lat') is not None:
            escala = self._escala((fila['lat'], fila['lon']))
            if escala is not None:
                destino = escala(0.0, 0.0)
        if destino is None:
            paso = 3 * self.tamanos.get('SecSubProd', (1.0, 1.0))[0]
            destino = (ancla[0] + paso, ancla[1] - paso)
        if nueva_barra is not None and linea is not None:
            self._simbolo(grfnet, f"G_{nueva_barra.loc_name}", 'PointTerm', nueva_barra, destino)
            centro = ((ancla[0] + destino[0]) / 2, (ancla[1] + destino[1]) / 2)
            rot = int(round(math.degrees(math.atan2(destino[1] - ancla[1], destino[0] - ancla[0])))) % 360
            g = self._simbolo(grfnet, f'G_{linea.loc_name}', 'd_lin', linea, centro, rot)
            for nr, extremo in ((0, ancla), (1, destino)):
                con = g.CreateObject('IntGrfcon', nombre_pf(f'GCO_{nr + 1}_{linea.loc_name}'))
                con.iDatConNr = nr
                largo = con.GetAttributeLength('rX') or 20
                for attr, valores in (('rX', [centro[0], extremo[0]]), ('rY', [centro[1], extremo[1]])):
                    con.SetAttribute(attr, [float(v) for v in valores] + [-1.0] * (largo - 2))
        self._simbolo(grfnet, f'gnoT {sub.loc_name}', 'SecSubProd', sub, destino)
        return {'dibujada': True, 'x': destino[0], 'y': destino[1]}


# =========================================================================== variación
def crear_variacion(app, nombre_base: str, etiqueta_etapa: str):
    """Variación nueva con nombre libre y una etapa que **graba** (RF-3, RF-4)."""
    carpeta = app.GetProjectFolder('scheme')
    nombre = nombre_libre(carpeta, 'IntScheme', nombre_base)
    variacion = carpeta.CreateObject('IntScheme', nombre)
    if variacion is None:
        raise RuntimeError(f'no se pudo crear la variación {nombre}')
    caso = app.GetActiveStudyCase()
    instante = int(getattr(caso, 'iStudyTime', 0) or 0)
    nombre_etapa = nombre_pf(f'Etapa_{etiqueta_etapa}')
    # NewStage(…, 1) activa la variación y deja la etapa grabando; devuelve un entero.
    variacion.NewStage(nombre_etapa, instante, 1)
    etapa = next((s for s in variacion.GetContents('*.IntSstage') if s.loc_name == nombre_etapa), None)
    if etapa is not None and not _misma(app.GetRecordingStage(), etapa):
        etapa.Activate(1)
    if etapa is None or not _misma(app.GetRecordingStage(), etapa):
        raise RuntimeError(f'la etapa de {nombre} no quedó grabando: no se escribe nada')
    return variacion, etapa


def _misma(a, b) -> bool:
    if a is None or b is None:
        return False
    try:
        return a.GetFullName() == b.GetFullName()
    except Exception:  # noqa: BLE001
        return a is b


def flujo_de_carga(app) -> dict:
    """``ComLdf`` con lo activo; convergencia y tensiones extremas (RF-18)."""
    ldf = app.GetFromStudyCase('ComLdf')
    ret = ldf.Execute()
    valido = app.IsLdfValid()
    out = {'return_code': ret, 'ldf_valid': bool(valido), 'converged': ret == 0 and bool(valido)}
    if out['converged']:
        tensiones = []
        for bus in app.GetCalcRelevantObjects('*.ElmTerm'):
            try:
                if bus.HasResults():
                    tensiones.append((bus.GetAttribute('m:u'), bus.loc_name))
            except Exception:  # noqa: BLE001
                pass
        if tensiones:
            tensiones.sort()
            out.update(vm_min=tensiones[0][0], vm_min_bus=tensiones[0][1],
                       vm_max=tensiones[-1][0], vm_max_bus=tensiones[-1][1])
    return out


def tecnico_economico(app, tec: dict) -> dict:
    """``ComTececo`` sobre las variaciones activas del caso, como hacía el lote.

    Solo se sobrescriben los ajustes que decide el plan; el resto queda como lo dejó el
    operador (manual, 12.8).
    """
    orden = app.GetFromStudyCase('ComTececo')
    if orden is None:
        return {'ok': False, 'error': 'el caso de estudio no admite la orden ComTececo'}
    for attr, valor in (tec.get('comtececo') or {}).items():
        orden.SetAttribute(attr, valor)
    ventana = app.GetOutputWindow()
    try:
        ventana.Clear()
    except Exception:  # noqa: BLE001
        pass
    rc = orden.Execute()
    lineas = [str(x) for x in (ventana.GetContent() or [])]
    resumen = [ln for ln in lineas
               if any(k in ln for k in ('NPV', 'Net Present', 'Total', 'Error', 'error'))][-40:]
    return {'ok': rc == 0, 'return_code': rc, 'parametros': tec.get('parametros'), 'resumen': resumen}


# =========================================================================== base (spec 007)
def variaciones_activas(app) -> list[str]:
    """Nombres de las variaciones activas, para el informe (spec 007, RF-8)."""
    try:
        return sorted(v.loc_name for v in (app.GetActiveNetworkVariations() or []))
    except Exception:  # noqa: BLE001 - versiones sin el método: no se informa
        return []


def variaciones_de_la_base(app, base: dict | None) -> tuple[list, list[str]]:
    """Las variaciones de la base que existen y los nombres de las que no (RF-7)."""
    if not base:
        return [], []
    carpeta = app.GetProjectFolder('scheme')
    por_nombre = {v.loc_name: v for v in (carpeta.GetContents('*.IntScheme', 1) if carpeta else [])}
    nombres = list(base.get('variaciones') or [])
    return [por_nombre[n] for n in nombres if n in por_nombre], [n for n in nombres if n not in por_nombre]


def nombre_de_carga(carpeta, sed: str, feeder: str, stamp: str, usados: set[str]) -> str:
    """``Carga_<SED>_<alimentador>_<stamp>``, sin repetir una variación existente (RF-10).

    ``usados`` lleva los nombres ya dados en esta ejecución: al simular no se crea nada,
    y dos cargas no pueden anunciar el mismo nombre.
    """
    base = nombre_pf(f'Carga_{sed}_{feeder}_{stamp}')
    existentes = {o.loc_name for o in carpeta.GetContents('*.IntScheme')} | usados if carpeta else usados
    nombre, n = base, 2
    while nombre in existentes:
        sufijo = f'_{n}'
        nombre, n = base[:MAX_NOMBRE - len(sufijo)] + sufijo, n + 1
    usados.add(nombre)
    return nombre


def medir_estado(app, alims: Alimentadores, feeders: list[str]) -> dict:
    """Un flujo y, por alimentador, su cabecera, sus pérdidas y su tensión mínima.

    Pérdidas = kW que entra por la cabecera − Σ kW de sus cargas (plan de la spec 007).
    Las cargas y barras se piden al ``ElmFeeder`` en cada medida, sin la caché de
    ``Alimentadores``: la carga nueva solo existe mientras su variación está activa.
    """
    flujo = flujo_de_carga(app)
    out = {'converged': flujo['converged'], 'vm_min': flujo.get('vm_min'),
           'vm_min_bus': flujo.get('vm_min_bus'), 'feeders': {}}
    for feeder in feeders:
        fila = {'cabecera': None, 'perdidas_kw': None, 'vm_min': None, 'vm_min_bus': None, 'motivo': None}
        elm = alims.elm.get(feeder)
        if not flujo['converged']:
            fila['motivo'] = 'el flujo de carga no converge'
        elif elm is None or getattr(elm, 'obj_id', None) is None:
            fila['motivo'] = 'sin ElmFeeder con cabecera'
        else:
            medida = leer_cabecera(elm)
            if medida.converge:
                kw_cargas = sum(potencia(o)[0] for o in elm.GetObjs('ElmLod')
                                if not getattr(o, 'outserv', 0))
                fila.update(cabecera={'kw': medida.kw, 'kvar': medida.kvar},
                            perdidas_kw=medida.kw - kw_cargas)
            else:
                fila['motivo'] = medida.motivo
            tensiones = sorted((_num(b, 'm:u'), b.loc_name) for b in elm.GetObjs('ElmTerm')
                               if b.HasResults() and _num(b, 'm:u') is not None)
            if tensiones:
                fila['vm_min'], fila['vm_min_bus'] = tensiones[0]
        out['feeders'][feeder] = fila
    return out


def _resta(x, y):
    return None if x is None or y is None else x - y


def diferencia(con: dict, sin: dict | None, feeder: str) -> dict | None:
    """Con proyecto menos sin proyecto en la cabecera, las pérdidas y la tensión mínima (RF-33)."""
    a = (con.get('feeders') or {}).get(feeder) or {}
    b = ((sin or {}).get('feeders') or {}).get(feeder) or {}
    if not a.get('cabecera') or not b.get('cabecera'):
        return None
    return {'kw': a['cabecera']['kw'] - b['cabecera']['kw'],
            'kvar': a['cabecera']['kvar'] - b['cabecera']['kvar'],
            'perdidas_kw': _resta(a.get('perdidas_kw'), b.get('perdidas_kw')),
            'vm_min': _resta(a.get('vm_min'), b.get('vm_min'))}


# =========================================================================== orquestación
def _crearian(r: dict, variacion: str) -> dict:
    return {'sed': r['fila']['sed'], 'barra': r['barra'].loc_name, 'criterio': r['criterio'],
            'distancia_m': r['distancia_m'], 'tipo_linea': getattr(r['tipo'], 'loc_name', None),
            'origen_tipo_linea': r['origen_tipo'] or None, 'tension_mt_kv': r['tension_mt_kv'],
            'tension_bt_kv': r['tension_bt_kv'], 'variacion': variacion, 'nota': r.get('nota')}


def _casos_011():
    """``tools/casos_pf.py``, que importa este módulo: por eso no se importa arriba."""
    try:
        import casos_pf
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import casos_pf
    return casos_pf


def ejecutar(app, plan: dict, *, simular: bool, cancelado=lambda: False) -> tuple[dict, int]:
    """Aplica (o simula) el plan en el proyecto. Devuelve (informe, código de salida).

    Spec 007: la base (las variaciones del ajuste) se activa primero; las demandas van a
    su variación, que forma con la base el estado sin proyecto; se mide ese estado una
    vez, y cada carga nueva se crea en su propia variación, se mide con proyecto y se
    desactiva antes de la siguiente. Al terminar queda activa la base y ninguna carga.
    """
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {'error': f"no existe el proyecto {plan['project']!r} en la carpeta "
                         f"{plan.get('folder')!r} de DIgSILENT"}, 2
    alims = Alimentadores(app, proyecto, plan['feeders'])
    base = plan.get('base') or None
    informe = {
        'project': proyecto.loc_name, 'project_path': plan['project'],
        'modo': 'simular' if simular else 'aplicar',
        'feeders': [], 'avisos': list(plan.get('avisos') or []), 'cancelado': False,
        'sin_alimentador': [], 'ambiguas': [], 'no_creadas': [], 'cargas': [],
        'base': base, 'variaciones_activas_inicio': variaciones_activas(app),
        'calibradas_cambiadas': list(plan.get('calibradas_cambiadas') or []),
    }
    variaciones_base, faltan = variaciones_de_la_base(app, base)
    if faltan:
        # RF-7: sin su base, las cargas se sumarían a otra red: no se aplica nada.
        return {**informe, 'error': f"la variación base {', '.join(faltan)} ya no existe en el "
                                    'proyecto: no se aplica nada'}, 2
    if alims.sin_elm:
        informe['avisos'].append('sin ElmFeeder (se buscó en todo el proyecto): '
                                 + ', '.join(alims.sin_elm))
    asignadas, omitidas, ambiguas = resolver_demandas(alims, plan.get('demandas') or [])
    resueltas, no_creadas, avisos = resolver_nuevas(alims, proyecto, plan.get('nuevas') or [])
    informe['sin_alimentador'], informe['ambiguas'], informe['no_creadas'] = omitidas, ambiguas, no_creadas
    informe['avisos'] += avisos
    carpeta = app.GetProjectFolder('scheme')
    stamp = plan.get('stamp') or ''
    nombre_demandas = plan.get('variacion_demandas') or plan.get('variacion') or f'Demandas_{stamp}'

    if simular:
        usados: set[str] = set()
        if any(asignadas.values()):
            informe['variacion_demandas'] = nombre_libre(carpeta, 'IntScheme', nombre_demandas)
        for feeder in alims.elegidos:
            informe['feeders'].append({
                'feeder': feeder,
                'actualizarian': [{'sed': f['sed'], 'antes': foto_carga(o),
                                   'despues': {'kw': f['kw'], 'kvar': f['kvar']}}
                                  for f, o in asignadas[feeder]],
                # RF-18: la barra, el criterio y la variación que tendría cada carga.
                'crearian': [_crearian(r, nombre_de_carga(carpeta, r['fila']['sed'], feeder, stamp, usados))
                             for r in resueltas[feeder]],
            })
        return informe, 0

    if not any(asignadas.values()) and not any(resueltas.values()):
        informe['avisos'].append('Nada que aplicar: ninguna fila coincide en el proyecto.')
        return informe, 0

    # Con un escenario activo, los datos de operación (las demandas) irían a él y no a
    # la variación. Se desactiva sin guardar —este proceso no tiene cambios propios en
    # él— y se vuelve a activar al final. Con los tres casos de la spec 011, cada caso
    # tiene el suyo, y se apaga el del caso en que se escribe.
    c011 = _casos_011()
    casos = c011.tres_casos(app)
    inicial = app.GetActiveStudyCase()
    apagados: list = []

    def entrar(caso):
        if caso is not None:
            caso.Activate()
        esc = app.GetActiveScenario()
        if esc is not None:
            esc.Deactivate(0)
            apagados.append((caso, esc))

    if casos:
        informe['casos'] = {'demandas': c011.NOMBRES['sin'], 'cargas': c011.NOMBRES['con']}
    entrar(casos['sin'] if casos else None)
    dem_var = None
    previas_con: list = []
    fallos = 0
    de_cargas: list = []
    por_feeder = {f: {'feeder': f, 'actualizadas': [], 'creadas': [], 'fallos': []} for f in alims.elegidos}
    empezados: list[str] = []
    try:
        # RF-6: la base, antes de crear ninguna variación.
        for v in variaciones_base:
            v.Activate()
        informe['base_activada'] = [v.loc_name for v in variaciones_base]

        # Fase 1, demandas (RF-19, RF-35): su variación queda activa, en el estado sin proyecto.
        if any(asignadas.values()):
            variacion, _etapa = crear_variacion(app, nombre_demandas, stamp)
            dem_var = variacion
            informe['variacion'] = informe['variacion_demandas'] = variacion.loc_name
        for feeder in alims.elegidos:
            if cancelado():
                informe['cancelado'] = True
                informe['avisos'].append(f'Cancelado: no se empezó {feeder} ni los siguientes.')
                break
            empezados.append(feeder)
            print(f'== {feeder}')
            r_feeder = por_feeder[feeder]
            for fila, obj in asignadas[feeder]:
                antes = foto_carga(obj)
                try:
                    escribir_carga(obj, float(fila['plini_mw']), float(fila['qlini_mvar']))
                    error = error_relectura(obj, float(fila['plini_mw']), float(fila['qlini_mvar']))
                except Exception as exc:  # noqa: BLE001 - una SED no tumba el alimentador
                    error = f'{type(exc).__name__}: {exc}'
                if error:
                    r_feeder['fallos'].append({'sed': fila['sed'], 'error': error})
                else:
                    r_feeder['actualizadas'].append({'sed': fila['sed'], 'antes': antes,
                                                     'despues': foto_carga(obj)})

        # Fase 2, una variación por carga nueva (RF-9 a RF-17).
        con_cargas = [f for f in empezados if resueltas[f]]
        if con_cargas and not informe['cancelado'] and casos:
            # RF-52: las cargas en «Con proyecto», sobre la base y las demandas. Las cargas
            # de otras aplicaciones se apagan mientras tanto: la referencia sin proyecto
            # de cada carga es la base (007:RF-32), y se vuelven a encender al final.
            entrar(casos['con'])
            for v in variaciones_base + ([dem_var] if dem_var is not None else []):
                v.Activate()
            todas = carpeta.GetContents('*.IntScheme', 1) if carpeta else []
            previas_con = c011.clasificar(todas, list(alims.elegidos), [], None)['cargas']
            for v in previas_con:
                v.Deactivate()
        if con_cargas and not informe['cancelado']:
            sin = medir_estado(app, alims, con_cargas)          # RF-32: una vez, como referencia
            informe['sin_proyecto'] = sin
            typ_folder = app.GetProjectFolder('equip') or proyecto
            diagrama = Diagrama(proyecto)
            usados: set[str] = set()
            for feeder in con_cargas:
                for r in resueltas[feeder]:
                    if cancelado():
                        informe['cancelado'] = True
                        informe['avisos'].append(f"Cancelado: no se empezó {r['fila']['sed']} ni las siguientes.")
                        break
                    creada = _una_carga(app, plan, alims, proyecto, typ_folder, diagrama, feeder, r,
                                        nombre_de_carga(carpeta, r['fila']['sed'], feeder, stamp, usados),
                                        sin, de_cargas)
                    if creada.get('error'):
                        por_feeder[feeder]['fallos'].append({'sed': r['fila']['sed'], 'error': creada['error']})
                        continue
                    if creada['error_relectura']:
                        por_feeder[feeder]['fallos'].append({'sed': creada['sed'], 'error': creada['error_relectura']})
                    por_feeder[feeder]['creadas'].append(creada)
                    informe['cargas'].append({k: creada.get(k) for k in (
                        'sed', 'alimentador', 'variacion', 'barra', 'criterio', 'distancia_m', 'nota',
                        'con_proyecto', 'delta', 'economia', 'tecnico_economico')})
                if informe['cancelado']:
                    break
            print(f"  cargas nuevas: {len(informe['cargas'])}, cada una en su variación")
        # El flujo que queda: la base y las demandas, sin ninguna carga nueva (RF-17).
        informe['flujo'] = flujo_de_carga(app)
    finally:
        # RF-17: también si algo revienta, ninguna variación de carga queda activa.
        for v in de_cargas:
            try:
                v.Deactivate()
            except Exception:  # noqa: BLE001 - se informa en variaciones_activas_fin
                pass
        # Y el escenario del operador no se queda apagado, en ningún caso.
        for caso, esc in apagados:
            if caso is not None:
                caso.Activate()
            if app.GetActiveScenario() is None:
                esc.Activate()
                informe['avisos'].append(
                    f'El escenario {esc.loc_name} vuelve a estar activo: sus demandas '
                    'mandan sobre las de la variación mientras esté activo.')
        if casos:
            # RF-54 y 011:RF-8: «Con proyecto» con las demandas y con todas las cargas.
            casos['con'].Activate()
            for v in ([dem_var] if dem_var is not None else []) + previas_con + de_cargas:
                v.Activate()
            if inicial is not None:
                inicial.Activate()
        informe['variaciones_activas_fin'] = variaciones_activas(app)
    informe['feeders'] = [por_feeder[f] for f in empezados]
    fallos = sum(len(f['fallos']) for f in informe['feeders'])
    print(f'  fallos {fallos}')
    return informe, (2 if fallos else 0)


def _una_carga(app, plan, alims, proyecto, typ_folder, diagrama, feeder, r, nombre, sin, de_cargas) -> dict:
    """Una carga en su variación: crear, medir con proyecto, evaluar y desactivar (RF-11 a RF-15, RF-22)."""
    variacion, etapa = crear_variacion(app, nombre, plan.get('stamp') or '')
    de_cargas.append(variacion)
    try:
        creada = crear_carga(alims, proyecto, typ_folder, diagrama, feeder, r)
    except Exception as exc:  # noqa: BLE001 - sin la carga, su variación no sirve
        variacion.Deactivate()
        de_cargas.remove(variacion)
        try:
            variacion.Delete()
        except Exception:  # noqa: BLE001
            pass
        return {'error': f'{type(exc).__name__}: {exc}'}
    creada.update(variacion=variacion.loc_name, nota=r.get('nota'))
    if plan.get('costos'):
        from igea_dgs.economia import CostosUnitarios, datos_etapa

        eco = datos_etapa([{'sed_code': creada['sed'], 'installed_kva': creada['kva_instalado'],
                            'length_km': (creada['distancia_m'] or 0) / 1000.0}],
                          CostosUnitarios(**plan['costos']))
        for attr in ('InvCosts', 'OrigVal', 'ScrVal', 'AddCosts', 'LifeSpan'):
            etapa.SetAttribute(attr, eco[attr])
        creada['economia'] = eco
    con = medir_estado(app, alims, [feeder])                # RF-13: base + esta carga
    creada['con_proyecto'] = con
    creada['delta'] = diferencia(con, sin, feeder)        # RF-33
    if plan.get('tec'):
        creada['tecnico_economico'] = tecnico_economico(app, plan['tec'])   # RF-22, RF-23
    variacion.Deactivate()                                # RF-12: la siguiente no la ve
    print(f"  {creada['sed']} → {creada['barra']} en {variacion.loc_name}")
    return creada


def error_inesperado(plan: dict, simular: bool, exc: BaseException) -> dict:
    """Informe de un guion que revienta: el error con su tipo, para que la web lo muestre."""
    informe = {'project': plan.get('project'), 'modo': 'simular' if simular else 'aplicar',
               'avisos': [], 'cancelado': False,
               'error': f'error inesperado del guion: {type(exc).__name__}: {exc}'}
    if plan.get('feeder'):
        informe['feeder'] = plan['feeder']
    return informe


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Cargas en un proyecto existente de DIgSILENT')
    p.add_argument('--plan', required=True)
    p.add_argument('--output-json', required=True)
    p.add_argument('--simular', action='store_true', help='Informa sin escribir (RF-17)')
    p.add_argument('--cancel-file', help='Si aparece, no se empieza otro alimentador (RF-19)')
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    blocked = native_action_block_report(plan, 'cargas')
    if blocked:
        Path(args.output_json).write_text(
            json.dumps(blocked, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(blocked['error'])
        return 2
    try:
        import powerfactory
    except ImportError as exc:
        print(f'ERROR: API de DIgSILENT no disponible ({exc}).')
        return 3
    try:
        app = powerfactory.GetApplicationExt()
    except Exception as exc:  # noqa: BLE001
        print(f'ERROR: no se pudo conectar a DIgSILENT: {exc}')
        return 3
    flag = Path(args.cancel_file) if args.cancel_file else None
    try:
        informe, codigo = ejecutar(app, plan, simular=args.simular,
                                   cancelado=lambda: bool(flag and flag.exists()))
    except Exception as exc:  # noqa: BLE001 - el informe dice el error en vez de perderse
        # «Ajustar SI213 a la máxima» (2026-10-10) acabó con el código 1 y sin informe: la
        # web solo podía decir «vea el Registro». La traza sigue yendo al Registro.
        traceback.print_exc()
        informe, codigo = error_inesperado(plan, args.simular, exc), 1
    informe['plan_errores_de_fila'] = plan.get('row_errors') or []
    Path(args.output_json).write_text(
        json.dumps(informe, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
    print(f'Informe: {args.output_json}')
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
