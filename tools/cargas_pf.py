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
from contextlib import contextmanager
import re
import sys
import traceback
from collections import Counter
from pathlib import Path

from igea_dgs.native_action import native_action_block_report
from igea_dgs.troncal import Barra, Red, Tramo, cortar_trazado, punto_en_troncal, red_de
from igea_dgs.troncal import troncal as troncal_de

MAX_NOMBRE = 40               # loc_name de DIgSILENT
REFERENCIAS_DIBUJO = 12       # barras dibujadas cercanas con que se mide la escala
RADIO_TIERRA_M = 6_371_000.0
# Baja tensión hasta 1 kV (IEC 60038), en cualquier empresa: una carga nueva se engancha
# en media, nunca en la barra de BT de una SED existente (RF-48).
MAX_BT_KV = 1.0
# 016:RF-88: la SED nueva cuelga del nodo de media si su punto queda a 25 m o menos; a
# más, un cable desde el nodo hasta su punto, al lado de alta de la SED (usuario,
# 2026-10-16). Antes se tendía cable con cualquier distancia, de 1 m incluso.
CABLE_MINIMO_M = 25.0
# DIgSILENT guarda lo que crea la etapa en una sola carpeta y renombra lo que repite
# nombre: la SED «CH_9», su barra «CH_9(1)» y la carga «CH_9(2)» (PN107, 2026-10-16).
SUFIJO_PF = re.compile(r'\(\d+\)$')
# 014:RF-30: a esta distancia o menos de una carga nueva ya creada, la fila del libro es
# esa misma carga aunque traiga otro nombre (usuario, 2026-10-16: «por el nombre y el
# mismo punto de coordenadas»). El libro da el punto con 6 decimales, unos 0,1 m.
MISMO_PUNTO_M = 1.0


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


# =========================================================================== red (spec 016)
def cabecera_de(elm):
    """La barra de la cabecera: la del cubículo con que se define el ``ElmFeeder``."""
    cubiculo = getattr(elm, 'obj_id', None)
    return getattr(cubiculo, 'cterm', None) if cubiculo is not None else None


def clave_pf(obj) -> str:
    """Identidad estable de un objeto de DIgSILENT: su nombre completo.

    La API de PF 2024 devuelve un envoltorio de Python nuevo en cada acceso, así que ni
    ``id()`` ni ``is`` reconocen el mismo objeto: con ``id()``, los dos extremos de cada
    línea de IN111 quedaron separados y la red salió sin tramos (copia de IN111_TA225,
    2026-10-15). El doble de las pruebas reutiliza el objeto y no lo notaba.
    """
    return obj.GetFullName()


def es_cable(linea) -> bool:
    """El tipo dice si es cable (``cohl_`` = 0, como lo escribe el DGS); sin él, ``inAir``."""
    cohl = getattr(getattr(linea, 'typ_id', None), 'cohl_', None)
    if cohl is not None:
        return int(cohl) == 0
    en_aire = getattr(linea, 'inAir', None)
    return en_aire is not None and int(en_aire) == 0


def trazado_de(linea) -> tuple[tuple[float, float], ...]:
    """``GPScoords`` de la línea, (latitud, longitud) por fila; vacío si no tiene dos puntos."""
    try:
        filas = linea.GetAttribute('GPScoords') or []
    except Exception:  # noqa: BLE001 - un elemento sin el atributo no tiene trazado
        filas = []
    puntos = tuple((float(f[0]), float(f[1])) for f in filas
                   if len(f) >= 2 and not (float(f[0]) == 0 and float(f[1]) == 0))
    return puntos if len(puntos) >= 2 else ()


def _cerrado(objeto, cubiculos) -> bool:
    """En servicio y sin un interruptor abierto en sus cubículos (016:RF-4)."""
    if int(getattr(objeto, 'outserv', 0) or 0):
        return False
    if objeto.GetClassName() == 'ElmCoup' and int(getattr(objeto, 'on_off', 1) or 0) == 0:
        return False
    return all(int(getattr(sw, 'on_off', 1) or 0) != 0
               for cub in cubiculos for sw in (cub.GetContents('*.StaSwitch') or []))


def leer_red(elm, cabecera=None) -> Red:
    """La red del alimentador en el caso activo, para ``igea_dgs.troncal`` (016:RF-2).

    Tramos son sus líneas y sus acopladores: un seccionador ``ElmCoup`` cerrado une dos
    barras igual que una línea, y abierto corta el camino. Los extremos salen de los
    cubículos de sus barras (``obj_bus`` 0 es ``bus1``, desde donde ``SplitLine`` cuenta el
    porcentaje). Un elemento con un extremo fuera del alimentador (un enlace con otro) no
    es un tramo suyo.
    """
    barras = list(elm.GetObjs('ElmTerm'))
    if cabecera is not None and all(clave_pf(b) != clave_pf(cabecera) for b in barras):
        barras.append(cabecera)
    extremos: dict[str, list] = {}
    objetos: dict[str, object] = {}
    for barra in barras:
        for cub in barra.GetContents('*.StaCubic') or []:
            o = getattr(cub, 'obj_id', None)
            if o is None or o.GetClassName() not in ('ElmLne', 'ElmCoup'):
                continue
            clave = clave_pf(o)
            objetos[clave] = o
            extremos.setdefault(clave, []).append((int(getattr(cub, 'obj_bus', 0) or 0), barra, cub))
    tramos = []
    for clave, lados in extremos.items():
        if len(lados) != 2:
            continue
        o = objetos[clave]
        (_, desde, c1), (_, hasta, c2) = sorted(lados, key=lambda x: x[0])
        linea = o.GetClassName() == 'ElmLne'
        tramos.append(Tramo(o.loc_name, desde.loc_name, hasta.loc_name,
                            float(getattr(o, 'dline', 0.0) or 0.0) * 1000.0 if linea else 0.0,
                            cerrado=_cerrado(o, (c1, c2)), cable=linea and es_cable(o),
                            trazado=trazado_de(o) if linea else ()))
    return red_de([Barra(b.loc_name, getattr(b, 'uknom', None), gps_de(b)) for b in barras], tramos)


def partir_tramo(app, linea, fraccion: float, nombre: str, gps=None):
    """Parte ``linea`` con ``Application.SplitLine`` en la variación que graba (016:RF-16 a RF-22).

    ``fraccion`` se cuenta desde ``bus1``. DIgSILENT deja a las dos mitades el tipo, las
    ternas, el estado y la longitud repartida (RF-17, RF-18), pero llama ``Terminal`` a la
    barra, la deja sin GPS y da a las dos el trazado entero (sonda del 2026-10-14, T1 de la
    016): el nombre, las coordenadas y el trazado de cada mitad se ponen aquí (RF-19).
    Devuelve (barra nueva, mitad nueva).
    """
    if app.GetRecordingStage() is None:
        raise RuntimeError(f'no hay una variación grabando: el tramo {linea.loc_name} se parte '
                           'solo dentro de la de la obra o de la carga')
    if int(getattr(linea, 'outserv', 0) or 0):
        raise RuntimeError(f'el tramo {linea.loc_name} está fuera de servicio: no se parte')
    if not 0 < fraccion < 1:
        raise RuntimeError(f'el punto del tramo {linea.loc_name} es un extremo: se conecta en su '
                           'barra, sin partirlo')
    trazado = trazado_de(linea)
    barra = app.SplitLine(linea, 100.0 * fraccion, 0, 0, 0)
    if not barra:
        raise RuntimeError(f'DIgSILENT no partió el tramo {linea.loc_name}')
    barra.loc_name = nombre
    mitades = cortar_trazado(trazado, fraccion) if trazado else None
    punto = gps or (mitades[0][-1] if mitades else None)
    if punto is not None:
        barra.GPSlat, barra.GPSlon = float(punto[0]), float(punto[1])
    copia = next((c.obj_id for c in barra.GetContents('*.StaCubic') or []
                  if getattr(c, 'obj_id', None) is not None
                  and clave_pf(c.obj_id) != clave_pf(linea)
                  and c.obj_id.GetClassName() == 'ElmLne'), None)
    if mitades and copia is not None:
        linea.SetAttribute('GPScoords', [list(q) for q in mitades[0]])
        copia.SetAttribute('GPScoords', [list(q) for q in mitades[1]])
    return barra, copia


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
    from igea_dgs.carpeta_pf import activar_proyecto as activar
    from igea_dgs.carpeta_pf import nombre_de_perfil

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
    """kW y kVAR que tiene escritos la carga en el escenario activo, los que usa el flujo.

    En una carga desequilibrada (``i_sym=1``) las fases son dato de la red, que comparten
    los casos, y ``plini`` lo deriva DIgSILENT en el escenario activo al escribirlas. En
    CA101 (2026-10-15) las fases valían lo calibrado en los tres casos, pero «Con proyecto»
    conservaba en su escenario la ``plini`` del archivo (SE20250: 98 kW en fases, 32,4 kW
    en ``plini``) y el flujo usaba esa. Antes se sumaban las fases y no se veía. Solo sin
    ``plini`` se suman las fases.
    """
    p, q = getattr(obj, 'plini', None), getattr(obj, 'qlini', None)
    if p is None and int(getattr(obj, 'i_sym', 0) or 0) == 1:
        p = sum(float(getattr(obj, f'plini{f}', 0.0) or 0.0) for f in 'rst')
        q = sum(float(getattr(obj, f'qlini{f}', 0.0) or 0.0) for f in 'rst')
    return float(p or 0.0) * 1000.0, float(q or 0.0) * 1000.0


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


def _frontera_cabecera(elm):
    """Cubículo medido, método, troncales y fuentes activas de la barra de cabecera."""
    cub_feeder = elm.obj_id
    rama = getattr(cub_feeder, 'obj_id', None)
    if rama is not None and rama.GetClassName() == 'ElmCoup':
        # 022:RF-22: en la red unida por SET el ElmFeeder está en el interruptor de
        # cabecera, en la barra de la SET que comparten varios alimentadores. Lo que entra
        # en este es lo que pasa por su interruptor; la red externa de la barra sumaría
        # todos ellos (con «FUENTE_UNICA»).
        return cub_feeder, 'INTERRUPTOR_DE_CABECERA', [], []
    try:
        barra = cub_feeder.GetParent()
        cubiculos = [c for c in barra.GetContents('*.StaCubic')
                     if getattr(c, 'obj_id', None) is not None
                     and not int(getattr(c.obj_id, 'outserv', 0) or 0)]
    except Exception:  # noqa: BLE001 - proyectos antiguos conservan la rama ElmFeeder
        return cub_feeder, 'RAMA_ELMFEEDER', [], []
    fuentes = [c for c in cubiculos if c.obj_id.GetClassName() == 'ElmXnet']
    clases_troncal = {'ElmLne', 'ElmTr2', 'ElmTr3'}
    troncales = [c for c in cubiculos if c.obj_id.GetClassName() in clases_troncal]
    if len(troncales) < 2:
        return cub_feeder, 'RAMA_ELMFEEDER', troncales, fuentes
    if len(fuentes) == 1:
        return fuentes[0], 'FUENTE_UNICA', troncales, fuentes
    # Nunca usar una sola rama como sustituto de una cabecera multitroncal: sin una
    # frontera común única, el objetivo del medidor no puede reconciliarse con toda la red.
    return cub_feeder, 'MULTITRONCAL_SIN_MEDIDOR_UNICO', troncales, fuentes


def _leer_cubiculo(cub, signo: float):
    rama = cub.obj_id
    lado = int(getattr(cub, 'obj_bus', 0) or 0) + 1
    p, q = _num(rama, f'm:Psum:bus{lado}'), _num(rama, f'm:Qsum:bus{lado}')
    return rama, p, q, lado, signo


def _signo_fuente(cub, troncales) -> float:
    """Signo del ElmXnet que hace su P coherente con la suma de salidas de la barra."""
    _rama, p, _q, _lado, _ = _leer_cubiculo(cub, 1.0)
    salidas = [_leer_cubiculo(c, 1.0)[1] for c in troncales]
    salidas = [x for x in salidas if x is not None]
    if p is None or not salidas:
        return 1.0
    total = sum(salidas)
    return 1.0 if abs(p - total) <= abs(-p - total) else -1.0


def leer_cabecera(elm):
    """Lo que entra por la cabecera según el último flujo, sin volver a ejecutarlo.

    La verificación de la spec 008 mide varios alimentadores con un solo flujo.
    """
    from igea_dgs.ajuste_cabecera import Medida

    cub, metodo, troncales, fuentes = _frontera_cabecera(elm)
    # Un ``ElmFeeder`` puede apuntar solo a una de varias troncales que salen de la
    # misma barra (CA101: dos salidas y un solo medidor). Cuando hay una única fuente
    # externa en esa barra, su cubículo es la frontera medida común y agrega todas las
    # troncales. PowerFactory no conserva la misma convención de signo del ElmXnet en
    # todos los proyectos; se elige la que coincide con la suma de salidas de la barra.
    if metodo == 'FUENTE_UNICA':
        signo = _signo_fuente(cub, troncales)
        rama, p, q, _lado, _signo = _leer_cubiculo(cub, signo)
        if p is None or q is None:
            return Medida(False, motivo=f'sin resultados en la fuente ({rama.loc_name})')
        return Medida(True, signo * p * 1000.0, signo * q * 1000.0)
    if metodo == 'MULTITRONCAL_SIN_MEDIDOR_UNICO':
        return Medida(
            False,
            motivo=(f'{len(troncales)} troncales en la barra de cabecera, pero se '
                    f'detectaron {len(fuentes)} fuentes ElmXnet: no se puede demostrar '
                    'un medidor común único y no se calibrará con una rama parcial'),
        )

    rama, p, q, _lado, _signo = _leer_cubiculo(cub, 1.0)
    if p is None or q is None:
        return Medida(False, motivo=f'sin resultados en la cabecera ({rama.loc_name})')
    signo = -1.0 if int(getattr(elm, 'iorient', 0) or 0) == 1 else 1.0
    return Medida(True, signo * p * 1000.0, signo * q * 1000.0)


def detalle_cabecera(elm) -> dict:
    """Frontera de medición y flujo individual de las troncales, para auditoría."""
    cub, metodo, troncales, fuentes = _frontera_cabecera(elm)
    signo_fuente = _signo_fuente(cub, troncales) if metodo == 'FUENTE_UNICA' else 1.0
    rama, p, q, lado, signo = _leer_cubiculo(
        cub, signo_fuente if metodo == 'FUENTE_UNICA' else
        (-1.0 if int(getattr(elm, 'iorient', 0) or 0) == 1 else 1.0))
    filas = []
    for troncal in troncales:
        elemento, tp, tq, tlado, _ = _leer_cubiculo(troncal, 1.0)
        filas.append({
            'cubiculo': str(getattr(troncal, 'loc_name', '') or ''),
            'elemento': str(getattr(elemento, 'loc_name', '') or ''),
            'clase': str(elemento.GetClassName()), 'lado': tlado,
            'kw': None if tp is None else tp * 1000.0,
            'kvar': None if tq is None else tq * 1000.0,
        })
    return {
        'metodo': metodo,
        'barra': str(getattr(cub.GetParent(), 'loc_name', '') or ''),
        'cubiculo_medidor': str(getattr(cub, 'loc_name', '') or ''),
        'elemento_medidor': str(getattr(rama, 'loc_name', '') or ''),
        'clase_medidor': str(rama.GetClassName()), 'lado_medidor': lado,
        'kw': None if p is None or metodo == 'MULTITRONCAL_SIN_MEDIDOR_UNICO'
        else signo * p * 1000.0,
        'kvar': None if q is None or metodo == 'MULTITRONCAL_SIN_MEDIDOR_UNICO'
        else signo * q * 1000.0,
        'cantidad_fuentes': len(fuentes),
        'cantidad_troncales': len(filas), 'troncales': filas,
    }


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
        if clave_pf(obj) in usados:
            omitidas.append({'sed': sed, 'motivo': f'repetida en el libro (ya en la hoja {usados[clave_pf(obj)]})'})
            continue
        usados[clave_pf(obj)] = fila.get('hoja')
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


def grabar_en_escenario(app, filas, apagar=()) -> dict | None:
    """Escribe las demandas también en el escenario activo y lo guarda (006:RF-27, 004:RF-54).

    La potencia de una carga es dato de operación: con un escenario activo, DIgSILENT usa
    la que guarda él y no la de la variación. SI213 (2026-10-12) cuadró a 1.622 kW con el
    escenario apagado y, al restaurarlo, la cabecera daba 229 kW, los de antes del ajuste.
    ``filas``: ``(nombre, carga, p_mw, q_mvar)``; ``apagar``: ``(nombre, carga)`` que
    quedan fuera de servicio. Sin escenario activo, ``None``.
    """
    esc = app.GetActiveScenario()
    if esc is None:
        return None
    fallos = []
    for nombre, obj, p_mw, q_mvar in filas:
        try:
            escribir_carga(obj, p_mw, q_mvar)
            error = error_relectura(obj, p_mw, q_mvar)
        except Exception as exc:  # noqa: BLE001 - una SED no tumba las demás
            error = f'{type(exc).__name__}: {exc}'
        if error:
            fallos.append({'sed': nombre, 'error': f'en el escenario {esc.loc_name}: {error}'})
    for nombre, obj in apagar:
        try:
            obj.outserv = 1
        except Exception as exc:  # noqa: BLE001
            fallos.append({'sed': nombre, 'error': f'en el escenario {esc.loc_name}: '
                                                   f'{type(exc).__name__}: {exc}'})
    esc.Save()
    return {'escenario': esc.loc_name, 'cargas': len(filas), 'fallos': fallos}


# =========================================================================== cargas nuevas
def _tipo_de_barra(barra):
    """Tipo de una línea que llega a la barra: tiene su R y X reales (RF-12)."""
    for cub in barra.GetContents('*.StaCubic'):
        obj = getattr(cub, 'obj_id', None)
        if obj is not None and obj.GetClassName() == 'ElmLne' and getattr(obj, 'typ_id', None) is not None:
            return obj.typ_id
    return None


def _tipo_del_alimentador(alims, feeder, barra):
    """Tipo de línea más usado del alimentador a la tensión de la barra (RF-39).

    A igual número de líneas, el de nombre menor, para que dos ejecuciones elijan el mismo.
    """
    kv = float(getattr(barra, 'uknom', 0) or 0)
    cuenta: dict[str, list] = {}
    for linea in alims.objetos(feeder, 'ElmLne'):
        tipo = getattr(linea, 'typ_id', None)
        if tipo is None:
            continue
        nominal = float(getattr(tipo, 'uline', 0) or 0)
        if kv and nominal and abs(nominal - kv) > 0.2 * kv:
            continue
        cuenta.setdefault(tipo.loc_name, [0, tipo])[0] += 1
    if not cuenta:
        return None
    _nombre, (_n, tipo) = min(cuenta.items(), key=lambda kv_: (-kv_[1][0], kv_[0]))
    return tipo


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
    return min(tensiones.items(), key=lambda kv: (-kv[1], kv[0]))[0]


def _de_media(barra) -> bool:
    """Barra donde se puede enganchar una SED nueva por cercanía (RF-48).

    El conversor da a la barra de BT de cada SED el GPS de su nodo de MT: sin este filtro
    la «más cercana» podía ser una de 0,38 kV, y la línea de enlace de media acababa en ella.
    """
    try:
        return float(getattr(barra, 'uknom', 0) or 0) > MAX_BT_KV
    except (TypeError, ValueError):
        return False


def _en_sed(barra) -> bool:
    try:
        padre = barra.GetParent()
        return padre is not None and padre.GetClassName() == 'ElmSubstat'
    except Exception:  # noqa: BLE001
        return False


def indice_de_cargas_nuevas(app, feeders) -> dict[tuple[str, str], dict]:
    """``(alimentador, nombre)`` → variaciones de carga nueva que guardan esa carga (014:RF-23).

    Se recorren una vez por trabajo todas las variaciones ``Carga_…`` del proyecto,
    activas o no: ``ElmFeeder.GetObjs`` solo ve la red del caso activo, y una carga creada
    antes en una variación apagada no se veía y se volvía a crear.
    """
    c011 = _casos_011()
    carpeta = app.GetProjectFolder('scheme')
    out: dict[tuple[str, str], dict] = {}
    for v in (carpeta.GetContents('*.IntScheme', 1) if carpeta else []):
        if not c011.es_de_carga_nueva(v):
            continue
        feeder = c011._de_alimentador(v.loc_name, 'Carga_', list(feeders))
        if feeder is None:
            continue
        for etapa in v.GetContents('*.IntSstage'):
            for carga in etapa.GetContents('*.ElmLod', 1):
                # Por el nombre sin el sufijo que pone la etapa (014:RF-29): con «CH_9(2)»
                # no se reconocía CH_9, se creaba otra que partía de nuevo el trozo de la
                # primera y «Con proyecto» no ejecutaba el flujo («Cubicle/Feeder Not
                # found» en NODE_T_CH_9, PN107, 2026-10-16).
                nombre = SUFIJO_PF.sub('', carga.loc_name)
                d = out.setdefault((feeder, nombre), {'variaciones': [], 'carga': carga})
                if v.loc_name not in d['variaciones']:
                    d['variaciones'].append(v.loc_name)
    return out


def nombres_en_red(app, alims: Alimentadores, caso) -> set[str]:
    """Cargas y SED de los alimentadores en la red de ``caso`` (014:RF-25), sin la caché."""
    previo = app.GetActiveStudyCase()
    if caso is not None and previo is not caso:
        caso.Activate()
    nombres: set[str] = set()
    for f in alims.elegidos:
        elm = alims.elm.get(f)
        for clase in ('ElmLod', 'ElmSubstat'):
            objs = (list(elm.GetObjs(clase)) if elm is not None
                    else list(app.GetCalcRelevantObjects(f'*.{clase}')))
            # Sin el sufijo de la etapa: la carga activa de CH_9 se llama «CH_9(2)» (014:RF-29).
            nombres.update(SUFIJO_PF.sub('', o.loc_name) for o in objs)
    if previo is not None and app.GetActiveStudyCase() is not previo:
        previo.Activate()
    return nombres


def _diferencias_con_la_fila(sed: str, carga, fila: dict) -> list[str]:
    """014:RF-28: la carga ya creada no se cambia; solo se dice en qué difiere del libro."""
    avisos = []
    try:
        kw = potencia(carga)[0]
    except Exception:  # noqa: BLE001 - sin potencia legible no hay con qué comparar
        kw = None
    if kw is not None and fila.get('kw') is not None and not math.isclose(
            kw, float(fila['kw']), rel_tol=1e-3, abs_tol=0.01):
        avisos.append(f"{sed}: ya creada con {kw:.1f} kW y el libro da {float(fila['kw']):.1f} kW; "
                      'no se crea otra (014:RF-28).')
    lat, lon = getattr(carga, 'GPSlat', None), getattr(carga, 'GPSlon', None)
    if fila.get('lat') is not None and lat is not None and (
            abs(float(lat) - float(fila['lat'])) > 1e-6 or abs(float(lon) - float(fila['lon'])) > 1e-6):
        avisos.append(f"{sed}: ya creada en ({float(lat):.6f}, {float(lon):.6f}) y el libro la da en "
                      f"({float(fila['lat']):.6f}, {float(fila['lon']):.6f}); no se crea otra (014:RF-28).")
    return avisos


def _en_el_punto(carga, punto: tuple[float, float]) -> bool:
    """La carga ya creada está a :data:`MISMO_PUNTO_M` o menos de ``punto`` (014:RF-30)."""
    lat, lon = getattr(carga, 'GPSlat', None), getattr(carga, 'GPSlon', None)
    if not lat or not lon:
        return False
    return distancia_m((float(lat), float(lon)), punto) <= MISMO_PUNTO_M


def ya_creada(fila: dict, candidatos: list[str], existentes: set[str], ya: dict | None):
    """La carga del libro ya existe: ``(no_creada, avisos)``, o ``None`` si hay que crearla.

    014:RF-24 a RF-27: por su nombre en su alimentador; en una variación de carga nueva se
    reutiliza esa variación, en dos o más no se toca ninguna, y en la red de «Con
    proyecto» fuera de una variación tampoco se crea.
    """
    sed = fila['sed']
    nombre = nombre_pf(sed)
    indice = (ya or {}).get('indice') or {}
    en_red = (ya or {}).get('red')
    halladas = [indice[(f, nombre)] for f in candidatos if (f, nombre) in indice]
    criterio = 'ya existe'
    if not halladas and fila.get('lat') is not None:
        punto = (float(fila['lat']), float(fila['lon']))
        halladas = [d for (f, _n), d in sorted(indice.items(), key=lambda x: x[0])
                    if f in candidatos and _en_el_punto(d['carga'], punto)]
        if halladas:
            otros = ', '.join(sorted({SUFIJO_PF.sub('', d['carga'].loc_name) for d in halladas}))
            criterio = f'ya existe en el mismo punto, como {otros} (014:RF-30),'
    variaciones = sorted({v for d in halladas for v in d['variaciones']})
    if len(variaciones) > 1:
        return ({'sed': sed, 'motivo': f'{criterio} en varias variaciones de carga nueva: no se crea '
                                       'otra ni se cambia cuál está activa (014:RF-26)',
                 'variaciones': variaciones},
                [f"{sed}: está en {len(variaciones)} variaciones de carga nueva "
                 f"({', '.join(variaciones)}); revise cuál vale (014:RF-26)."])
    if variaciones:
        return ({'sed': sed, 'motivo': f'{criterio} en la variación {variaciones[0]}: se reutiliza, '
                                       'activa en «Con proyecto» (014:RF-24)',
                 'variacion': variaciones[0], 'reutilizada': True},
                _diferencias_con_la_fila(sed, halladas[0]['carga'], fila))
    if sed in existentes:
        return {'sed': sed, 'motivo': 'ya existe en el alimentador (RF-15)'}, []
    if en_red is not None and nombre in en_red:
        return ({'sed': sed, 'motivo': 'ya existe en la red de «Con proyecto», fuera de una '
                                       'variación de carga nueva (014:RF-25)'}, [])
    return None


def _troncales(alims: Alimentadores):
    """Alimentador → (red, tramos de su troncal, líneas por nombre), calculado una vez.

    ``None`` si no hay ``ElmFeeder`` o no dice su cabecera: sin ellos no hay troncal, y la
    carga va a la barra más cercana, como antes de la spec 016.
    """
    cache: dict[str, tuple | None] = {}

    def de(f: str):
        if f not in cache:
            elm = alims.elm.get(f)
            cabecera = cabecera_de(elm) if elm is not None else None
            if cabecera is None:
                cache[f] = None
            else:
                red = leer_red(elm, cabecera)
                lineas = {ln.loc_name: ln for ln in elm.GetObjs('ElmLne')}
                # 016:RF-78 (cambia RF-45): cualquier tramo de media, no solo la troncal.
                # Con solo la troncal, IC_11, IC_12, IC_15 e IC_17 de TA225 caían en el
                # mismo punto de SEC_1091_815724, a 5-7 km de sus coordenadas (usuario,
                # 2026-10-15: «ubicadas de acuerdo a su punto de coordenada»).
                # Ni el enlace entre alimentadores (016, normalmente abierto): IC_13 caía en
                # Enlace_TA225_IN111, a 720 m de su punto (2026-10-15).
                tramos = tuple(n for n in sorted(lineas)
                               if not int(getattr(lineas[n], 'outserv', 0) or 0)
                               and not n.startswith('Enlace_'))
                cache[f] = (red, tramos, lineas)
        return cache[f]
    return de


def resolver_nuevas(alims: Alimentadores, proyecto, nuevas: list[dict], ya: dict | None = None,
                    minima_m: float | None = None):
    """Cada carga nueva → cómo se conecta, o el motivo para no crearla. Solo lectura.

    Devuelve (resueltas por alimentador, no creadas, avisos). Solo se buscan barras en
    los alimentadores marcados (spec 007, RF-25). Una fila cuyo alimentador (TRONCAL) no
    está marcado no se crea (RF-29): el libro de planificación trae las cargas de todos
    los alimentadores, y con SI213 marcado se colgaban de su barra más cercana las 27 de
    otros alimentadores, una a 216 km (2026-10-13). Sin alimentador en la fila, el más
    cercano entre los marcados (RF-36).

    Spec 016: la carga con coordenadas y sin barra va al punto más cercano de la troncal
    (016:RF-45), no a la barra existente más cercana: en SI213 esa barra era el nodo de una
    SED, que solo tenía su seccionador (007:RF-39). Si el punto cae dentro de un tramo, la
    carga lo parte al crearse, en su variación (RF-46); a menos de ``minima_m`` de una
    barra, se engancha en ella (RF-20).
    """
    tipos = {t.loc_name: t for t in proyecto.GetContents('*.TypLne', 1)}
    troncales = _troncales(alims)
    sin_troncal_gps: set[str] = set()
    existentes = {o.loc_name for f in alims.elegidos for clase in ('ElmLod', 'ElmSubstat')
                  for o in alims.objetos(f, clase)}
    barras = {f: alims.objetos(f, 'ElmTerm') for f in alims.elegidos}
    # RF-48: por cercanía solo barras de media, y a igual distancia la de la red antes que
    # la barra MT interna de una SED, que en un proyecto convertido tiene el mismo GPS.
    cercanas = {f: [(b, pos, _en_sed(b)) for b in barras[f] if _de_media(b)
                    for pos in [gps_de(b)] if pos is not None] for f in alims.elegidos}
    resueltas = {f: [] for f in alims.elegidos}
    no_creadas, avisos = [], []
    # RF-28: un alimentador sin barras con GPS se dice una vez, no carga por carga.
    sin_gps = {f for f in alims.elegidos if not cercanas[f]}
    avisados = set()
    # El libro escribe la TRONCAL a mano: «si213 » es SI213.
    marcados = {str(f).strip().upper(): f for f in alims.elegidos}
    de_otros: dict[str, int] = {}
    for fila in nuevas:
        sed = fila['sed']
        candidatos = list(alims.elegidos)
        suyo = str(fila.get('alimentador') or '').strip()
        if suyo:
            if suyo.upper() not in marcados:
                de_otros[suyo] = de_otros.get(suyo, 0) + 1
                no_creadas.append({'sed': sed, 'motivo': f'el libro la da en {suyo}, que no está '
                                                         'entre los alimentadores marcados (RF-29)'})
                continue
            candidatos = [marcados[suyo.upper()]]
        repetida = ya_creada(fila, candidatos, existentes, ya)
        if repetida is not None:
            no_creadas.append(repetida[0])
            avisos += repetida[1]
            continue
        punto = (fila['lat'], fila['lon']) if fila.get('lat') is not None else None
        eleccion = None
        sobre_barra = ''
        if fila.get('barra'):
            halladas = [(f, b) for f in candidatos for b in barras[f] if b.loc_name == fila['barra']]
            if len(halladas) > 1:
                por_hoja = [h for h in halladas if h[0] == fila.get('hoja')]
                halladas = por_hoja if len(por_hoja) == 1 else halladas
            if len(halladas) != 1:
                motivo = (f"la barra {fila['barra']} no está en los alimentadores elegidos" if not halladas
                          else f"la barra {fila['barra']} está en varios alimentadores")
                # RF-50: un libro de planificación llama «BARRA» a la de la subestación, no
                # a una barra del proyecto (SI213, 2026-10-12); con coordenadas, se ubica por ellas.
                if punto is None:
                    no_creadas.append({'sed': sed, 'motivo': motivo})
                    continue
                sobre_barra = f'{motivo}: se ubica por sus coordenadas (RF-50)'
            else:
                feeder, barra = halladas[0]
                pos = gps_de(barra)
                dist = distancia_m(pos, punto) if (pos and punto) else None
                eleccion = (feeder, barra, dist, 'barra indicada')
        conexion = None
        if eleccion is None and punto is not None:
            mejor = None
            clave_mejor = None
            for f in candidatos:
                t = troncales(f)
                if t is not None:                                       # 016:RF-45
                    c = punto_en_troncal(t[0], t[1], punto, minima_m)
                    if c is None:
                        sin_troncal_gps.add(f)
                        continue
                    clave = (c.distancia_m, False, f, c.tramo)
                    if clave_mejor is None or clave < clave_mejor:
                        mejor, clave_mejor = (f, c), clave
                    continue
                for b, pos, interna in cercanas[f]:
                    d = distancia_m(pos, punto)
                    clave = (d, interna, f, b.loc_name)
                    if clave_mejor is None or clave < clave_mejor:
                        mejor, clave_mejor = (f, b, d), clave
            if mejor is None:
                nuevos = sorted((set(candidatos) & sin_gps | set(candidatos) & sin_troncal_gps) - avisados)
                if nuevos:
                    avisos.append(f"Ninguna barra de media ni tramo de la troncal de {', '.join(nuevos)} tiene "
                                  'coordenadas en DIgSILENT: no se conecta por coordenadas ninguna carga '
                                  'suya (007:RF-28, 016:RF-50).')
                    avisados.update(nuevos)
                no_creadas.append({'sed': sed, 'motivo': 'ninguna barra de los alimentadores tiene GPS'})
                continue
            if len(mejor) == 2:
                f, conexion = mejor
                _red, _tramos, lineas = troncales(f)
                tramo = _red.por_nombre()[conexion.tramo]
                extremo = conexion.barra or tramo.desde
                barra_ref = next((b for b in barras[f] if b.loc_name == extremo), None)
                if barra_ref is None:
                    barra_ref = next(b for b in barras[f] if b.loc_name in (tramo.desde, tramo.hasta))
                criterio = ('barra de la troncal más cercana' if conexion.barra
                            else 'punto de la troncal más cercano')
                eleccion = (f, barra_ref, conexion.distancia_m, criterio)
                if conexion.barra:
                    conexion = None                       # se engancha en la barra, sin partir
                else:
                    conexion = {'linea': lineas[conexion.tramo], 'tramo': conexion.tramo,
                                'fraccion': conexion.fraccion, 'gps': conexion.gps}
            else:
                eleccion = (*mejor, 'barra más cercana por GPS')
        elif eleccion is None:
            no_creadas.append({'sed': sed, 'motivo': 'sin barra ni coordenadas'})
            continue
        feeder, barra, dist, criterio = eleccion
        tipo, origen_tipo = None, ''
        if con_cable(dist):                        # hace falta una línea de enlace (RF-88)
            if fila.get('tipo_linea') and fila['tipo_linea'] in tipos:
                tipo, origen_tipo = tipos[fila['tipo_linea']], 'de la fila'
            elif conexion is not None:
                tipo, origen_tipo = getattr(conexion['linea'], 'typ_id', None), 'del tramo que se parte'
            else:
                tipo, origen_tipo = _tipo_de_barra(barra), 'de la red'
            if tipo is None:
                # RF-39: SI213, 2026-10-13: la barra más cercana a «SU Fundo El Eden» era el
                # nodo de una SED sin línea propia (solo su seccionador) y la única carga del
                # libro para SI213 no se creó. Se toma el tipo más usado del alimentador.
                tipo = _tipo_del_alimentador(alims, feeder, barra)
                origen_tipo = 'el más usado del alimentador' if tipo is not None else ''
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
            'partir': conexion,
            'nota': sobre_barra or None,
            'tipo': tipo, 'origen_tipo': origen_tipo,
            'tension_mt_kv': float(getattr(barra, 'uknom', 0) or 0),
            'tension_bt_kv': float(bt), 'red': red,
            'frecuencia_hz': float(getattr(red, 'frnom', 0) or 0) if red is not None else 0.0,
        })
        existentes.add(sed)
    # 016:RF-47 (cambia con RF-77): dos cargas en el mismo tramo lo parten una tras otra;
    # la segunda parte el trozo que dejó la primera, con su variación activa.
    for f, lista in resueltas.items():
        por_tramo: dict[str, list[str]] = {}
        for r in lista:
            if r['partir']:
                por_tramo.setdefault(r['partir']['tramo'], []).append(r['fila']['sed'])
        for tramo, seds in sorted(por_tramo.items()):
            if len(seds) > 1:
                avisos.append(f"{', '.join(seds)} caen en el mismo tramo {tramo}: la primera lo "
                              'parte y las demás se conectan en un extremo existente del tramo, '
                              'cada una independiente (025:RF-47).')
    if de_otros:
        total = sum(de_otros.values())
        detalle = ', '.join(f'{f} ({n})' for f, n in sorted(de_otros.items()))
        avisos.append(f'{total} carga(s) nueva(s) del libro son de alimentadores no marcados '
                      f'({detalle}): no se crean (RF-29).')
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


def con_cable(distancia_m: float | None) -> bool:
    """016:RF-88: cable hasta el punto de la carga solo a más de :data:`CABLE_MINIMO_M`."""
    return (distancia_m or 0.0) > CABLE_MINIMO_M


def crear_carga(alims, proyecto, typ_folder, diagrama, feeder, r) -> dict:
    """Crea la carga resuelta en la etapa que graba. Devuelve lo creado (RF-14).

    Si la carga va dentro de un tramo de la troncal, primero lo parte en esta misma
    variación (016:RF-46) y se engancha en la barra nueva.
    """
    fila, barra, red = r['fila'], r['barra'], r['red']
    sed = fila['sed']
    contenedor = red if red is not None else barra.GetParent()
    partido = None
    if r.get('partir'):
        p = r['partir']
        nombre = nombre_libre(p['linea'].GetParent(), 'ElmTerm', f'NODE_T_{sed}')
        barra, _ = partir_tramo(alims.app, p['linea'], p['fraccion'], nombre, gps=p['gps'])
        p['barra_nueva'] = barra
        partido = {'tramo': p['tramo'], 'fraccion': round(p.get('fraccion_tramo', p['fraccion']), 4)}
    mt, bt = r['tension_mt_kv'], r['tension_bt_kv']
    enganche, linea, nueva_barra = barra, None, None
    if con_cable(r['distancia_m']):                                      # 016:RF-88
        nueva_barra = contenedor.CreateObject('ElmTerm', nombre_pf(f'NODE_{sed}'))
        nueva_barra.uknom, nueva_barra.iUsage, nueva_barra.outserv = mt, 1, 0
        nueva_barra.GPSlat, nueva_barra.GPSlon = float(fila['lat']), float(fila['lon'])
        linea = contenedor.CreateObject('ElmLne', nombre_pf(f'LNE_{sed}'))
        linea.typ_id = r['tipo']
        linea.dline = max(r['distancia_m'] / 1000.0, 1e-6)
        linea.nlnum = 1
        # 016:RF-89: el cable con su trazado, del nodo al punto; sin él los cables de
        # IN111 + TA225 tenían 0 vértices (2026-10-16).
        if gps_de(barra) is not None:
            linea.SetAttribute('GPScoords', [list(gps_de(barra)), [float(fila['lat']), float(fila['lon'])]])
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
    # RF-49: sin GPS, la SED nueva no salía en el diagrama geográfico aunque la fila
    # trajera sus coordenadas; el conversor pone el de su nodo a la SED y a sus barras.
    punto = ((float(fila['lat']), float(fila['lon'])) if fila.get('lat') is not None
             else gps_de(barra))
    if punto is not None:
        for obj in (sub, b_mt, b_bt, carga):
            try:
                obj.GPSlat, obj.GPSlon = punto
            except Exception:  # noqa: BLE001, S110 - una clase sin GPS no impide crearla
                pass
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
        'tramo_partido': partido, 'cable': con_cable(r['distancia_m']),
    }


# =========================================================================== dibujo
class Diagrama:
    """Símbolos ya dibujados del proyecto, para situar la carga nueva en el unifilar."""

    def __init__(self, proyecto):
        self.proyecto = proyecto
        self.por_obj, self.tamanos = {}, {}
        for grfnet in proyecto.GetContents('*.IntGrfnet', 1):
            for grf in grfnet.GetContents('*.IntGrf'):
                obj = getattr(grf, 'pDataObj', None)
                if obj is not None:
                    # Por la clave y no por id(): la API de DIgSILENT da un objeto Python
                    # nuevo en cada llamada, y ninguna carga nueva de IN111 + TA225 se
                    # dibujaba («no está en ningún diagrama», 2026-10-15).
                    self.por_obj[clave_pf(obj)] = (grf, grfnet, obj)
                sym = getattr(grf, 'sSymNam', '')
                if sym and sym not in self.tamanos:
                    self.tamanos[sym] = (grf.rSizeX, grf.rSizeY)

    def _pos(self, obj):
        hallado = self.por_obj.get(clave_pf(obj))
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
            rot = round(math.degrees(math.atan2(destino[1] - ancla[1], destino[0] - ancla[0]))) % 360
            g = self._simbolo(grfnet, f'G_{linea.loc_name}', 'd_lin', linea, centro, rot)
            for nr, extremo in ((0, ancla), (1, destino)):
                con = g.CreateObject('IntGrfcon', nombre_pf(f'GCO_{nr + 1}_{linea.loc_name}'))
                con.iDatConNr = nr
                largo = con.GetAttributeLength('rX') or 20
                for attr, valores in (('rX', [centro[0], extremo[0]]), ('rY', [centro[1], extremo[1]])):
                    con.SetAttribute(attr, [float(v) for v in valores] + [-1.0] * (largo - 2))
        self._simbolo(grfnet, f'gnoT {sub.loc_name}', 'SecSubProd', sub, destino)
        return {'dibujada': True, 'x': destino[0], 'y': destino[1]}

    def completar(self, app, *, simular: bool = False) -> dict:
        """Dibuja lo que la red activa tiene con GPS y sin símbolo (016:RF-89).

        ``SplitLine`` y la obra de enlace crean barras y líneas sin símbolo: en IN111 +
        TA225 (2026-10-16) el enlace por la vía, de 6,3 km y 140 vértices, estaba en «Con
        proyecto» y no se veía en el diagrama, ni la mitad nueva de cada tramo partido ni
        su nodo. Se dibujan como el DGS (spec 010): la barra en su punto y la línea por su
        trazado, con los extremos en sus barras. Los símbolos no van en la variación: en
        los casos sin ella DIgSILENT los muestra sin datos. Las barras de dentro de una SED
        y los tramos de 1 m o menos no se dibujan, como en el DGS.
        """
        hechos = {'barras': [], 'lineas': []}
        for b in sorted(app.GetCalcRelevantObjects('*.ElmTerm') or [], key=lambda o: o.loc_name):
            if clave_pf(b) in self.por_obj or _en_sed(b) or gps_de(b) is None:
                continue
            if simular or self._barra(b):
                hechos['barras'].append(b.loc_name)
        for ln in sorted(app.GetCalcRelevantObjects('*.ElmLne') or [], key=lambda o: o.loc_name):
            if clave_pf(ln) in self.por_obj or float(getattr(ln, 'dline', 0) or 0) * 1000.0 <= 1.0:
                continue
            if simular or self._linea(ln):
                hechos['lineas'].append(ln.loc_name)
        return hechos

    def _referencias(self):
        """(GPS, posición, diagrama) de lo dibujado, leído una vez."""
        if getattr(self, '_refs', None) is None:
            self._refs = [(gps, (grf.rCenterX, grf.rCenterY), net)
                          for grf, net, obj in self.por_obj.values()
                          for gps in [gps_de(obj)] if gps is not None]
        return self._refs

    def _al_diagrama(self, punto):
        """Terreno → diagrama alrededor de ``punto`` y el diagrama de lo más cercano."""
        refs = self._referencias()
        if not refs:
            return None, None
        net = min(refs, key=lambda r: distancia_m(r[0], punto))[2]
        escala = self._escala(punto)
        if escala is None:
            return None, None
        return (lambda q: escala(*a_metros(punto, q))), net

    def _registrar(self, grf, net, obj):
        self.por_obj[clave_pf(obj)] = (grf, net, obj)
        gps = gps_de(obj)
        if gps is not None and getattr(self, '_refs', None) is not None:
            self._refs.append((gps, (grf.rCenterX, grf.rCenterY), net))

    def _barra(self, barra) -> bool:
        punto = gps_de(barra)
        mapa, net = self._al_diagrama(punto)
        if mapa is None:
            return False
        grf = self._simbolo(net, f'G_{barra.loc_name}', 'PointTerm', barra, mapa(punto))
        self._registrar(grf, net, barra)
        return True

    def _linea(self, linea) -> bool:
        from igea_dgs.dgs import PUNTOS_POR_CONECTOR_PF, _line_irot, _puntos_que_dan_la_forma

        if hasattr(linea, 'bus1'):
            cubiculos = [getattr(linea, 'bus1', None), getattr(linea, 'bus2', None)]
        else:       # el doble de las pruebas: los cubículos del proyecto que la apuntan
            cubiculos = sorted((c for c in self.proyecto.GetContents('*.StaCubic', 1)
                                if getattr(c, 'obj_id', None) is linea),
                               key=lambda c: getattr(c, 'obj_bus', 0))
        extremos = [c.cterm for c in cubiculos if c is not None and getattr(c, 'cterm', None) is not None]
        if len(extremos) != 2:
            return False
        trazado = list(trazado_de(linea)) or [g for g in map(gps_de, extremos) if g is not None]
        if len(trazado) < 2:
            return False
        medio = trazado[len(trazado) // 2]
        mapa, net = self._al_diagrama(medio)
        if mapa is None:
            return False
        camino = [mapa(q) for q in trazado]
        # Los extremos, en el símbolo de cada barra; el trazado puede ir de bus2 a bus1.
        pos = [self._pos(b)[0] or mapa(gps_de(b) or trazado[0]) for b in extremos]
        def d2(a, b):
            return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
        if d2(camino[0], pos[0]) + d2(camino[-1], pos[1]) > d2(camino[0], pos[1]) + d2(camino[-1], pos[0]):
            pos.reverse()
        camino[0], camino[-1] = pos[0], pos[1]
        if len(camino) == 2:
            camino.insert(1, ((camino[0][0] + camino[1][0]) / 2, (camino[0][1] + camino[1][1]) / 2))
        mitad = len(camino) // 2
        centro = camino[mitad]
        grf = self._simbolo(net, f'G_{linea.loc_name}', 'd_lin', linea, centro, _line_irot(camino))
        for nr, puntos in ((0, list(reversed(camino[:mitad + 1]))), (1, camino[mitad:])):
            puntos = _puntos_que_dan_la_forma(puntos, PUNTOS_POR_CONECTOR_PF)
            con = grf.CreateObject('IntGrfcon', nombre_pf(f'GCO_{nr + 1}_{linea.loc_name}'))
            con.iDatConNr = nr
            largo = con.GetAttributeLength('rX') or PUNTOS_POR_CONECTOR_PF
            for attr, valores in (('rX', [p[0] for p in puntos]), ('rY', [p[1] for p in puntos])):
                con.SetAttribute(attr, [float(v) for v in valores] + [-1.0] * (largo - len(valores)))
        self._registrar(grf, net, linea)
        return True


def completar_diagrama(app, proyecto) -> dict:
    """016:RF-89 con el caso activo; un fallo del dibujo no tumba lo que ya se creó."""
    try:
        return Diagrama(proyecto).completar(app)
    except Exception as exc:  # noqa: BLE001 - sin dibujo la red calcula igual
        return {'error': f'{type(exc).__name__}: {exc}'}


# =========================================================================== variación
#: Las etapas del conversor van, en segundos, entre la hora del estudio menos esto y ella.
VENTANA_ETAPAS_S = 1_000_000


def fecha_de_etapa_nueva(carpeta, hora_estudio: int) -> int:
    """La fecha de activación de una etapa nueva: la siguiente libre antes del estudio.

    Con tres o más etapas activas de la misma fecha, DIgSILENT no aplica ninguna, y sin
    avisar: IN111 + TA225 (2026-10-15, sonda en el proyecto), con las nueve cargas nuevas
    de TA225 en la fecha del estudio, «Con proyecto» calculaba sin ninguna carga ni obra;
    con dos, sí entraban. Cada etapa toma su segundo, en el orden en que se crea, de modo
    que la más nueva (una obra sobre las cargas) se aplica la última, y todas antes de la
    hora del estudio para que estén activas.
    """
    desde = hora_estudio - VENTANA_ETAPAS_S
    usadas = [int(s.tAcTime) for v in (carpeta.GetContents('*.IntScheme', 1) if carpeta else [])
              for s in v.GetContents('*.IntSstage') if desde <= int(s.tAcTime) < hora_estudio]
    return min(max(usadas) + 1, hora_estudio - 1) if usadas else desde


def crear_variacion(app, nombre_base: str, etiqueta_etapa: str):
    """Variación nueva con nombre libre y una etapa que **graba** (RF-3, RF-4)."""
    carpeta = app.GetProjectFolder('scheme')
    nombre = nombre_libre(carpeta, 'IntScheme', nombre_base)
    variacion = carpeta.CreateObject('IntScheme', nombre)
    if variacion is None:
        raise RuntimeError(f'no se pudo crear la variación {nombre}')
    caso = app.GetActiveStudyCase()
    hora = int(getattr(caso, 'iStudyTime', 0) or 0)
    instante = fecha_de_etapa_nueva(carpeta, hora)
    nombre_etapa = nombre_pf(f'Etapa_{etiqueta_etapa}')
    # NewStage(…, 1) activa la variación y deja la etapa grabando; devuelve un entero.
    variacion.NewStage(nombre_etapa, instante, 1)
    # Y lleva la hora del caso a la de la etapa: con la fecha propia de RF-74, cada carga
    # nueva la retrasaba y las etapas anteriores quedaban después de la hora del estudio,
    # inactivas aunque su variación lo estuviera (IN111 + TA225, 2026-10-15: 29 etapas
    # retrasaron «Con proyecto» 335 días y el nodo del enlace no existía).
    if caso is not None and int(getattr(caso, 'iStudyTime', 0) or 0) != hora:
        caso.iStudyTime = hora
    etapa = next((s for s in variacion.GetContents('*.IntSstage') if s.loc_name == nombre_etapa), None)
    if etapa is not None and not _misma(app.GetRecordingStage(), etapa):
        etapa.Activate(1)
    otras = []
    if etapa is not None and not _misma(app.GetRecordingStage(), etapa):
        # Con otras etapas activas de la misma fecha PF puede no dejar grabando ninguna, ni
        # con Activate(1) (manual de PF 2024, 16.5). SI213, 2026-10-12, en una copia del
        # proyecto: con sus cuatro ajustes activos no grababa; sola, la etapa nueva graba y
        # sigue grabando al reactivar las otras… hasta la cuarta. Qué combinación lo impide
        # no lo dice el manual: se prueba y se comprueba al final, sin suponerlo.
        otras = [v for v in app.GetActiveNetworkVariations() if not _misma(v, variacion)]
        for v in otras:
            v.Deactivate()
        etapa.Activate(1)
        for v in otras:
            v.Activate()
    if etapa is None or not _misma(app.GetRecordingStage(), etapa):
        # Activa y vacía, se sumaría a las etapas de la misma fecha que ya impidieron grabar
        # y el siguiente intento fallaría igual. Inactiva tampoco sirve: la obra de enlace
        # de IN111 + TA225 (2026-10-15) se negaba a repetirse porque «ya hay una» con ese
        # nombre; vacía no guarda nada del operador y se borra.
        variacion.Deactivate()
        variacion.Delete()
        detalle = (': DIgSILENT no la deja grabar con estas variaciones activas en la misma '
                   'fecha; desactive las que no hagan falta y repita: '
                   + ', '.join(v.loc_name for v in otras)) if otras else ''
        raise RuntimeError(f'la etapa de {nombre} no quedó grabando: no se escribe nada'
                           + detalle)
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
            except Exception:  # noqa: BLE001, S110
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
    except Exception:  # noqa: BLE001, S110
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
    """Lo que se haría con la carga (RF-18; 016:RF-49: el tramo y si se parte)."""
    partir = r.get('partir')
    return {'sed': r['fila']['sed'], 'barra': r['barra'].loc_name, 'criterio': r['criterio'],
            'tramo': partir['tramo'] if partir else None, 'parte': bool(partir),
            'fraccion': round(partir['fraccion'], 4) if partir else None,
            'distancia_m': r['distancia_m'], 'cable': con_cable(r['distancia_m']),
            'tipo_linea': getattr(r['tipo'], 'loc_name', None),
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
    # 015:RF-16, RF-17, RF-28: las demandas van a «Sin proyecto» y las cargas nuevas a «Con
    # proyecto», que se crean si faltan, solo con el «Caso base» verificado (014:RF-19).
    # Al simular no se crea nada.
    c011 = _casos_011()
    # 025:RF-36, RF-38: con la base calibrada en un año, en los casos de ese año; los de
    # otro año no se tocan.
    anio = c011.anio_del_plan(plan)
    nombre_sin, nombre_con = c011.nombre_caso('sin', anio), c011.nombre_caso('con', anio)
    casos = c011.tres_casos(app, anio)
    if not simular and not casos and (plan.get('nuevas') or plan.get('demandas')):
        pedido = {'project': plan['project'], 'folder': plan.get('folder'),
                  'feeders': list(plan['feeders']), 'anio_casos': anio}
        if 'caso_base_sin_verificar' in plan:
            pedido['caso_base_sin_verificar'] = plan['caso_base_sin_verificar']
        preparados, rc = c011.preparar_con(app, pedido)
        if rc:
            return {**informe, 'error': preparados.get('error')}, 2
        if any((preparados.get('casos') or {}).get(r, {}).get('creado') for r in ('sin', 'con')):
            informe['casos_preparados'] = preparados.get('casos')
        casos = c011.tres_casos(app, anio)
    if casos and not simular:
        # 014:RF-31 a RF-34: lo hecho a mano en «Sin proyecto», también en «Con proyecto»,
        # antes de apagar ningún escenario para escribir.
        informe['sin_a_con'] = c011.sin_a_con_proyecto(app, casos)
        informe['avisos'] += informe['sin_a_con']['avisos']
    # 014:RF-23: una vez por trabajo, no por carga.
    ya = {'indice': indice_de_cargas_nuevas(app, alims.elegidos),
          'red': nombres_en_red(app, alims, casos['con']) if casos else None}
    resueltas, no_creadas, avisos = resolver_nuevas(alims, proyecto, plan.get('nuevas') or [], ya,
                                                    minima_m=plan.get('minima_m'))
    informe['reutilizadas'] = [x for x in no_creadas if x.get('reutilizada')]
    duplicadas = {n for x in no_creadas for n in x.get('variaciones') or []}
    por_nombre_var = {v.loc_name: v for v in (app.GetProjectFolder('scheme').GetContents('*.IntScheme', 1)
                                              if app.GetProjectFolder('scheme') else [])}
    reutilizadas = [por_nombre_var[x['variacion']] for x in informe['reutilizadas']
                    if x['variacion'] in por_nombre_var] if casos else []
    informe['sin_alimentador'], informe['ambiguas'], informe['no_creadas'] = omitidas, ambiguas, no_creadas
    informe['avisos'] += avisos
    carpeta = app.GetProjectFolder('scheme')
    stamp = plan.get('stamp') or ''
    nombre_demandas = plan.get('variacion_demandas') or plan.get('variacion') or f'Demandas_{stamp}'

    if simular:
        usados: set[str] = set()
        if any(asignadas.values()):
            # 015:RF-27: las demandas, en el escenario de «Sin proyecto», sin variación.
            informe['demandas_en'] = nombre_sin
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
        if reutilizadas:
            # 014:RF-24: todas las del libro ya existían; sus variaciones, activas en «Con
            # proyecto» igualmente.
            previo = app.GetActiveStudyCase()
            casos['con'].Activate()
            _obras_de_las_reutilizadas(app, c011, anio, casos, informe)
            for v in reutilizadas:
                v.Activate()
            if previo is not None:
                previo.Activate()
        # Sin esto la web decía «al terminar: ninguna» con el ajuste aún activo (2026-10-13).
        informe['variaciones_activas_fin'] = variaciones_activas(app)
        return informe, 0

    # Con un escenario activo, los datos de operación (las demandas) irían a él y no a
    # la variación. Se desactiva sin guardar —este proceso no tiene cambios propios en
    # él— y se vuelve a activar al final. Con los tres casos de la spec 011, cada caso
    # tiene el suyo, y se apaga el del caso en que se escribe.
    inicial = app.GetActiveStudyCase()
    apagados: list = []
    esc_con = None

    def entrar(caso):
        if caso is not None:
            caso.Activate()
        esc = app.GetActiveScenario()
        if esc is not None:
            esc.Deactivate(0)
            apagados.append((caso, esc))

    if casos:
        informe['casos'] = {'demandas': nombre_sin, 'cargas': nombre_con}
        informe['anio_casos'] = anio            # 025:RF-44: la escalera, en los casos de ese año
        # 015:RF-27: en «Sin proyecto» las demandas se escriben con su escenario activo,
        # que es donde quedan; ninguna variación graba allí.
        casos['sin'].Activate()
    else:
        entrar(None)
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

        # Fase 1, demandas (RF-19, RF-35): con los tres casos, en el escenario de «Sin
        # proyecto» (015:RF-27); sin ellos, en su variación, como antes de la 015.
        if any(asignadas.values()) and not casos:
            variacion, _etapa = crear_variacion(app, nombre_demandas, stamp)
            dem_var = variacion
            informe['variacion'] = informe['variacion_demandas'] = variacion.loc_name
        elif any(asignadas.values()):
            informe['demandas_en'] = nombre_sin
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
            # 014:RF-21, RF-22: antes, lo que el operador tiene activo en «Sin proyecto».
            # (sin_a_con_proyecto, al empezar, ya las activó y lo dijo)
            informe['variaciones_operador_activadas'] = (informe.get('sin_a_con') or {}).get(
                'variaciones', [])
            entrar(casos['con'])
            for v in variaciones_base + ([dem_var] if dem_var is not None else []):
                v.Activate()
            todas = carpeta.GetContents('*.IntScheme', 1) if carpeta else []
            previas_con = c011.clasificar(todas, list(alims.elegidos), [], None)['cargas']
            activas_con_antes = {v.loc_name for v in previas_con if v in app.GetActiveNetworkVariations()}
            # 014:RF-26: una carga repetida en varias variaciones no cambia cuáles están activas.
            previas_con = [v for v in previas_con
                           if v.loc_name not in duplicadas or v.loc_name in activas_con_antes]
            for v in previas_con:
                v.Deactivate()
        esc_con = next((e for c, e in apagados if casos and c is casos['con']), None)
        if con_cargas and not informe['cancelado']:
            with _con_escenario(esc_con):
                sin = medir_estado(app, alims, con_cargas)      # RF-32: una vez, como referencia
            informe['sin_proyecto'] = sin
            typ_folder = app.GetProjectFolder('equip') or proyecto
            diagrama = Diagrama(proyecto)
            usados: set[str] = set()
            tramos: dict = {}                     # 016:RF-77: tramo → variaciones que lo parten
            # 025:RF-47: también las cargas nuevas de otra tanda que ya parten un tramo; una
            # nueva en ese tramo va a su extremo, no lo parte otra vez.
            carpeta_var = app.GetProjectFolder('scheme')
            for v in (carpeta_var.GetContents('*.IntScheme', 1) if carpeta_var else []):
                if c011.es_de_carga_nueva(v):
                    for clase, n in c011.objetos_de_variacion(v):
                        if clase == 'ElmLne':
                            tramos.setdefault(n, []).append((v, None))
            for feeder in con_cargas:
                for r in resueltas[feeder]:
                    if cancelado():
                        informe['cancelado'] = True
                        informe['avisos'].append(f"Cancelado: no se empezó {r['fila']['sed']} ni las siguientes.")
                        break
                    creada = _una_carga(app, plan, alims, proyecto, typ_folder, diagrama, feeder, r,
                                        nombre_de_carga(carpeta, r['fila']['sed'], feeder, stamp, usados),
                                        sin, de_cargas, tramos, esc_con)
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
        # El flujo que queda: la base y las demandas, sin ninguna carga nueva (RF-17), con
        # el escenario que guarda las demandas calibradas (016:RF-79).
        with _con_escenario(esc_con):
            informe['flujo'] = flujo_de_carga(app)
        # Solo las que se escribieron bien en la variación: la que falló, falla igual.
        bien = {(f, x['sed']) for f in empezados for x in por_feeder[f]['actualizadas']}
        actualizadas = [(fila['sed'], obj, float(fila['plini_mw']), float(fila['qlini_mvar']))
                        for f in empezados for fila, obj in asignadas[f]
                        if (f, fila['sed']) in bien]
        if actualizadas:
            informe['escenarios'] = _demandas_al_escenario(app, casos, apagados, actualizadas)
            for g in informe['escenarios']:
                informe['avisos'] += [f"{x['sed']}: {x['error']}" for x in g['fallos']]
    finally:
        # RF-17: también si algo revienta, ninguna variación de carga queda activa.
        for v in de_cargas:
            try:
                v.Deactivate()
            except Exception:  # noqa: BLE001, S110 - se informa en variaciones_activas_fin
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
            # 014:RF-24: la variación de una carga que ya existía queda activa en «Con
            # proyecto», también si no se creó ninguna otra.
            if reutilizadas:
                _obras_de_las_reutilizadas(app, c011, anio, casos, informe)
            for v in reutilizadas:
                v.Activate()
            if informe['cargas'] or reutilizadas:
                informe['dibujo'] = completar_diagrama(app, proyecto)       # 016:RF-89
                # 025:RF-43: si no converge con todas, qué cargas no caben juntas.
                juntas = c011.cargas_que_no_convergen_juntas(
                    app, casos['con'], lambda a: bool(flujo_de_carga(a).get('converged')))
                if juntas:
                    informe['no_convergen_juntas'] = juntas
                    solas = juntas['solas_que_no_convergen']
                    informe['avisos'].append(
                        f"«{juntas['caso']}» no converge con sus {len(juntas['cargas'])} cargas nuevas"
                        + (f"; solas tampoco: {', '.join(solas)}" if solas else '; cada una sola, sí')
                        + (f"; basta quitar una de: {', '.join(juntas['basta_quitar_una_de'])}"
                           if juntas['basta_quitar_una_de'] else '')
                        + '. Hacen falta obras: la escalera de obras (025:RF-44).')
            if inicial is not None:
                inicial.Activate()
        informe['variaciones_activas_fin'] = variaciones_activas(app)
    informe['feeders'] = [por_feeder[f] for f in empezados]
    fallos = sum(len(f['fallos']) for f in informe['feeders'])
    print(f'  fallos {fallos}')
    return informe, (2 if fallos else 0)


def _obras_de_las_reutilizadas(app, c011, anio, casos, informe) -> None:
    """Con el caso «Con proyecto <año>» activo, las obras sobre las que se crearon las cargas
    reutilizadas de los casos sin año, activas también aquí (025:RF-42), con la operación
    que dejaron en el escenario de «Con proyecto» (025:RF-42b). Sin año, nada: son del
    mismo «Con proyecto»."""
    if not anio:
        return
    activo = app.GetActiveStudyCase()
    obras = c011.obras_del_con_proyecto_sin_anio(app)
    if activo is not None:
        activo.Activate()
    ya = {v.loc_name for v in (app.GetActiveNetworkVariations() or [])}
    nuevas = [v for v in obras if v.loc_name not in ya]
    for v in nuevas:
        v.Activate()
    informe['obras_activadas'] = sorted(v.loc_name for v in nuevas)
    if nuevas:
        informe['avisos'].append(
            f"Las cargas reutilizadas se crearon sobre obras de «{c011.NOMBRES['con']}»; activas "
            f"también en «{c011.nombre_caso('con', anio)}»: " + ', '.join(informe['obras_activadas'])
            + ' (025:RF-42).')
    if obras and casos:
        # También si ya estaban activas: la operación del escenario no la trae la variación.
        operacion = c011.operacion_de_las_obras(app, casos)
        informe['operacion_de_las_obras'] = operacion
        informe['avisos'] += operacion['avisos']


def _demandas_al_escenario(app, casos, apagados, filas) -> list[dict]:
    """Las demandas también en el escenario de operación (RF-54, RF-55).

    Se escriben en la variación con el escenario apagado (RF-3) pero, al restaurarlo,
    manda la potencia que guarda él (spec 006, RF-27). Con los tres casos, en los de «Sin
    proyecto» y «Con proyecto»; el del «Caso base» guarda el ajuste y no se toca.
    """
    previo = app.GetActiveStudyCase()
    grabados = []
    for caso in ([casos['sin'], casos['con']] if casos else [None]):
        if caso is not None:
            caso.Activate()
        if app.GetActiveScenario() is None:
            # El que se apagó para escribir en la variación vuelve ya, para grabar en él.
            esc = next((e for c, e in apagados if c is caso), None)
            if esc is not None:
                esc.Activate()
        g = grabar_en_escenario(app, filas)
        if g is not None:
            grabados.append(g)
    if previo is not None and app.GetActiveStudyCase() is not previo:
        previo.Activate()
    return grabados


@contextmanager
def _con_escenario(escenario):
    """Mide con el escenario de operación encendido y lo vuelve a apagar sin guardar.

    Se apaga para que lo escrito vaya a la variación, pero las demandas calibradas están
    en él: sin él, «Con proyecto» de IN111 + TA225 sumaba 45,8 MW de datos del elemento en
    vez de 13,7 calibrados y no convergía, y todas las medidas de las cargas salían sin
    flujo (2026-10-15).
    """
    if escenario is not None:
        escenario.Activate()
    try:
        yield
    finally:
        if escenario is not None:
            escenario.Deactivate(0)


def _a_un_extremo(r: dict, quien: str) -> dict:
    """La conexión de ``r`` cuando otra carga nueva ya parte su tramo (025:RF-47).

    Usuario, 2026-10-23: «cada carga debe ser totalmente independiente». Antes se conectaba
    en el nodo que dejó la otra carga (016:RF-77), y CH_8 de TM105 colgaba de NODE_T_CH_3:
    al desactivar CH_3, CH_8 se quedaba sin conexión. Partir otra vez el mismo tramo en otra
    variación tampoco vale: juntas lo dejaban partido dos veces sobre la misma línea y el
    flujo no se ejecutaba (IN111 + TA225, 2026-10-15). Se conecta en la barra existente más
    cercana de los dos extremos del tramo original, con su propia línea hasta su punto: no
    toca nada que cree otra variación.
    """
    p = r['partir']
    linea, fila = p['linea'], r['fila']
    extremos = [t for t in (getattr(getattr(linea, lado, None), 'cterm', None) for lado in ('bus1', 'bus2'))
                if t is not None]
    if not extremos:
        raise RuntimeError(f"el tramo {p['tramo']} no tiene barras en sus extremos")
    punto = (float(fila['lat']), float(fila['lon']))
    con_gps = [(distancia_m(gps_de(t), punto), t) for t in extremos if gps_de(t)]
    if con_gps:
        dist, barra = min(con_gps, key=lambda x: x[0])
    else:
        dist, barra = r['distancia_m'], extremos[0 if p.get('fraccion', 0) < 0.5 else -1]
    tipo = r.get('tipo') or getattr(linea, 'typ_id', None)
    return {**r, 'partir': None, 'barra': barra, 'distancia_m': dist, 'tipo': tipo,
            'origen_tipo': r.get('origen_tipo') or 'del tramo que se parte',
            'criterio': f"extremo existente de {p['tramo']} (ese tramo ya lo parte {quien})"}


def _una_carga(app, plan, alims, proyecto, typ_folder, diagrama, feeder, r, nombre, sin, de_cargas,
               tramos=None, escenario=None) -> dict:
    """Una carga en su variación: crear, medir con proyecto, evaluar y desactivar (RF-11 a RF-15, RF-22).

    025:RF-47 y RF-48 (cambian 016:RF-77): si otra carga nueva ya partió su tramo, esta va a
    un extremo existente (:func:`_a_un_extremo`) y se mide con las variaciones de las demás
    cargas inactivas. Colgar del nodo de otra dejaba a CH_8 de TM105 sin red al desactivar
    CH_3 (2026-10-23); partir otra vez el tramo original lo dejaba partido dos veces en
    «Con proyecto» (IN111 + TA225, 2026-10-15) y el flujo no convergía.
    """
    tramos = {} if tramos is None else tramos
    p = r.get('partir')
    # 025:RF-47: con el tramo ya partido por otra carga, esta va a un extremo existente y no
    # se activa ninguna variación ajena: cada carga se mide y se desactiva sola.
    otras = [v for v, _ in tramos.get(p['tramo'], [])] if p else []
    if otras:
        r = _a_un_extremo(r, ', '.join(v.loc_name for v in otras))
    variacion, etapa = crear_variacion(app, nombre, plan.get('stamp') or '')
    de_cargas.append(variacion)
    try:
        creada = crear_carga(alims, proyecto, typ_folder, diagrama, feeder, r)
    except Exception as exc:  # noqa: BLE001 - sin la carga, su variación no sirve
        variacion.Deactivate()
        de_cargas.remove(variacion)
        try:
            variacion.Delete()
        except Exception:  # noqa: BLE001, S110
            pass
        return {'error': f'{type(exc).__name__}: {exc}'}
    if p and r.get('partir') is not None:
        tramos.setdefault(p['tramo'], []).append((variacion, r['partir'].get('barra_nueva')))
    elif p:
        tramos[p['tramo']].append((variacion, r['barra']))
    nota = r.get('nota')
    if otras:
        nota = ((nota + ' ') if nota else '') + (
            f"El tramo {p['tramo']} ya lo parte {', '.join(v.loc_name for v in otras)}: se conecta "
            f"en su extremo {getattr(r['barra'], 'loc_name', r['barra'])}, independiente de esa "
            'carga (025:RF-47).')
    creada.update(variacion=variacion.loc_name, nota=nota)
    if plan.get('costos'):
        from igea_dgs.economia import CostosUnitarios, datos_etapa

        eco = datos_etapa([{'sed_code': creada['sed'], 'installed_kva': creada['kva_instalado'],
                            'length_km': (creada['distancia_m'] or 0) / 1000.0}],
                          CostosUnitarios(**plan['costos']))
        for attr in ('InvCosts', 'OrigVal', 'ScrVal', 'AddCosts', 'LifeSpan'):
            etapa.SetAttribute(attr, eco[attr])
        creada['economia'] = eco
    with _con_escenario(escenario):
        con = medir_estado(app, alims, [feeder])            # RF-13: base + esta carga
        creada['con_proyecto'] = con
        creada['delta'] = diferencia(con, sin, feeder)    # RF-33
        if plan.get('tec'):
            creada['tecnico_economico'] = tecnico_economico(app, plan['tec'])   # RF-22, RF-23
    variacion.Deactivate()                                # RF-12: la siguiente no la ve
    print(f"  {creada['sed']} → {creada['barra']} en {variacion.loc_name}")
    return creada


def deshacer(app, plan: dict, aplicado: dict, *, simular: bool) -> tuple[dict, int]:
    """Borra lo que creó una aplicación anterior, según su informe (spec 007, RF-38).

    SI213 (2026-10-13) creó 28 cargas nuevas, 27 de otros alimentadores (RF-29). Cada
    carga vive en su variación y se va con ella; los símbolos del diagrama y los tipos
    de transformador nuevos no están en la variación y se borran aparte. Un tipo que use
    todavía algún transformador del proyecto se deja.
    """
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {'error': f"no existe el proyecto {plan['project']!r} en la carpeta "
                         f"{plan.get('folder')!r} de DIgSILENT"}, 2
    if aplicado.get('project') and aplicado['project'] != proyecto.loc_name:
        return {'error': f"el informe es del proyecto {aplicado['project']!r}, no de "
                         f'{proyecto.loc_name!r}: no se borra nada'}, 2
    creadas = [c for f in aplicado.get('feeders') or [] for c in f.get('creadas') or []]
    nombres = list(dict.fromkeys(c['variacion'] for c in creadas if c.get('variacion')))
    carpeta = app.GetProjectFolder('scheme')
    por_nombre = {v.loc_name: v for v in (carpeta.GetContents('*.IntScheme', 1) if carpeta else [])}
    informe = {'project': proyecto.loc_name, 'modo': 'simular' if simular else 'deshacer',
               'variaciones': [], 'no_estaban': [n for n in nombres if n not in por_nombre],
               'simbolos': [], 'tipos': [], 'tipos_en_uso': []}
    for nombre in nombres:
        v = por_nombre.get(nombre)
        if v is None:
            continue
        if not simular:
            v.Deactivate()
            v.Delete()
        informe['variaciones'].append(nombre)
    # Los nombres que da ``Diagrama.dibujar``.
    simbolos = set()
    for c in creadas:
        if (c.get('dibujo') or {}).get('dibujada'):
            sed = nombre_pf(c['sed'])
            simbolos |= {nombre_pf(f'G_{nombre_pf(f"NODE_{sed}")}'),
                         nombre_pf(f'G_{nombre_pf(f"LNE_{sed}")}'), nombre_pf(f'gnoT {sed}')}
    for grfnet in proyecto.GetContents('*.IntGrfnet', 1) if simbolos else []:
        for grf in grfnet.GetContents('*.IntGrf'):
            if grf.loc_name in simbolos:
                informe['simbolos'].append(grf.loc_name)
                if not simular:
                    grf.Delete()
    nuevos = {c['tipo_trafo'] for c in creadas if c.get('tipo_trafo_nuevo') and c.get('tipo_trafo')}
    if nuevos:
        en_uso = {getattr(getattr(t, 'typ_id', None), 'loc_name', None)
                  for t in proyecto.GetContents('*.ElmTr2', 1)}
        typ_folder = app.GetProjectFolder('equip') or proyecto
        for tipo in typ_folder.GetContents('*.TypTr2', 1):
            if tipo.loc_name not in nuevos:
                continue
            if tipo.loc_name in en_uso:
                informe['tipos_en_uso'].append(tipo.loc_name)
                continue
            informe['tipos'].append(tipo.loc_name)
            if not simular:
                tipo.Delete()
    informe['variaciones_activas_fin'] = variaciones_activas(app)
    return informe, 0


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
    p.add_argument('--deshacer', metavar='INFORME',
                   help='Borra lo que creó la aplicación de ese informe (spec 007, RF-38)')
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    blocked = native_action_block_report(plan, 'cargas')
    if blocked:
        Path(args.output_json).write_text(
            json.dumps(blocked, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(blocked['error'])
        return 2
    # 019:RF-1 a RF-6: turno del motor de la máquina, reintento con el motor ocupado y
    # primera línea al responder, comunes a todos los guiones.
    from igea_dgs.pf_arnes import PFNoDisponible, conectar

    try:
        app = conectar('cargas_pf.py')
    except PFNoDisponible as exc:
        print(f'ERROR: {exc}')
        return 3
    if args.deshacer:
        aplicado = json.loads(Path(args.deshacer).read_text(encoding='utf-8'))
        informe, codigo = deshacer(app, plan, aplicado, simular=args.simular)
        Path(args.output_json).write_text(
            json.dumps(informe, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
        print(json.dumps(informe, indent=2, ensure_ascii=False, default=str))
        return codigo
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
