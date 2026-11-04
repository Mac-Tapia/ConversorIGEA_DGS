"""Escalera optimizada de obras sobre «Con proyecto <año>» (spec 025, RF-44, RF-49 a RF-60).

Usuario, 2026-10-24: «primero se debe probar bancos, después nueva terna, cambio de sección
de cable, donde se debe iterar varias veces hasta obtener la mejor solución según la
optimización y cálculos estocásticos»; la mejor, la de menor costo anual; se sortea la
demanda existente por la curva de cabecera del año; vale si cumple en el 95 % de 200
sorteos; en «Sin proyecto» no se corrige nada, así que «cumplir» es no dejar la red peor
que allí y dar a cada carga nueva su tensión.

Puro: arma las variantes, juzga cada flujo, sortea, costea y elige. Medir en DIgSILENT es de
``tools/obras_pf.py`` (``--evaluar``). Ningún valor de una empresa: todo sale del perfil
(``escalera`` y ``planificacion``), de las bibliotecas y del libro CAPEX.
"""
from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .catalogo_reguladores import CatalogoError, unidad_para_corriente, unidades_para
from .estudios_pf import CON_PROYECTO
from .instalacion_ternas import capacidad_de_tramos
from .pide_economia import costo_anual

#: Orden de la escalera: bancos, cambio de sección, terna y, al final, regulador (063:RF-21; cambia
#: 025:RF-44). Usuario, 2026-11-01: «primero debe comenzar con bancos y luego con cambio de sección
#: y una terna después, pero si y solo si se requiere».
ORDEN = ('bancos', 'seccion', 'terna', 'regulador')


def rango(escalones) -> int:
    """El escalón más alto que usa una variante; sin escalones (sin obras), antes de todos (063:RF-22)."""
    return max((ORDEN.index(e) for e in escalones if e in ORDEN), default=-1)
#: Alternativa del PIDE de cada escalón, para su costo en el libro CAPEX (RF-53).
ALTERNATIVA = {'bancos': 'bancos', 'regulador': 'reguladores', 'terna': 'nueva_terna',
               'seccion': 'cambio_seccion'}
#: Módulos de banco que se prueban sin valle medido ni ``escalera.modulos_max`` (073:RF-24). Es la
#: regla anterior a la spec 073, por compatibilidad, y solo vale marcada «no comprobado en valle».
MODULOS_SIN_VALLE = 2
#: Proyecto de DIgSILENT con los reguladores de catálogo (025:RF-59).
BIBLIOTECA_TIPOS = 'CSG_Biblioteca_tipos'
HORAS_ANIO = 8760


class EscaleraError(ValueError):
    """Falta un dato del perfil o del libro CAPEX: se dice cuál y no se supone (RF-57)."""


@dataclass(frozen=True)
class Parametros:
    cumplimiento: float
    sorteos: int
    semilla: int
    tolerancia_pu: float
    tolerancia_carga_pct: float
    max_variantes: int
    tasa: float
    vida: int
    tension_min_pu: float
    tension_max_pu: float
    cargabilidad_max_pct: float
    precio_perdidas_kwh: float | None = None
    precio_perdidas_kw_mes: float | None = None
    coym_pct_anual: float | None = None
    moneda: str = ''
    costos_unitarios: dict = field(default_factory=dict)       # alternativa → costo en ``moneda``
    escala_capex: float | None = None                          # ``moneda`` por unidad del libro CAPEX
    #: 025:RF-44: el regulador entra en la escalera, al final del orden (aclaración de 063:RF-26);
    #: un perfil puede quitarlo con ``escalera.con_regulador: false``.
    con_regulador: bool = True
    #: 073:RF-19, RF-24: techo del perfil para los módulos de banco; sin él, los del valle.
    modulos_max: int | None = None
    #: 084:RF-16: ``planificacion.ternas_subterraneas`` del perfil, con la capacidad por configuración.
    ternas: Mapping[str, Any] = field(default_factory=dict)
    #: 042:RF-27: los conductores normalizados de la empresa (prefijo del tipo); vacío, todos.
    secciones: tuple[str, ...] = ()
    #: 042:RF-35: desde este largo del camino a una carga, el regulador va por delante del tope de variantes.
    linea_larga_km: float = 10.0

    @property
    def consigna_regulador_pu(self) -> float:
        """El centro de la banda de tensión del perfil: sin un valor propio de la empresa."""
        return (self.tension_min_pu + self.tension_max_pu) / 2


def parametros(perfil: Mapping[str, Any], tipo_cambio: float | None = None) -> Parametros:
    """Los de la escalera, de ``escalera``, ``planificacion`` y ``estudios`` del perfil (RF-57).

    ``tipo_cambio``: unidades de la moneda de los precios de pérdidas por una de la moneda de
    trabajo, el que escribe el operador en la web (RF-67); no sale del perfil.
    """
    esc = dict(perfil.get('escalera') or {})
    plan = dict(perfil.get('planificacion') or {})
    lim = dict(perfil.get('estudios') or {})
    pedidos = {'escalera.cumplimiento': esc.get('cumplimiento'), 'escalera.sorteos': esc.get('sorteos'),
               'escalera.tolerancia_pu': esc.get('tolerancia_pu'),
               'escalera.tolerancia_carga_pct': esc.get('tolerancia_carga_pct'),
               'planificacion.tasa_regulada': plan.get('tasa_regulada'),
               'planificacion.vida_util_anios': plan.get('vida_util_anios'),
               'estudios.tension_min_pu': lim.get('tension_min_pu'),
               'estudios.tension_max_pu': lim.get('tension_max_pu'),
               'estudios.cargabilidad_max_pct': lim.get('cargabilidad_max_pct')}
    faltan = [k for k, v in pedidos.items() if v is None]
    if faltan:
        raise EscaleraError('el perfil de empresa no da ' + ', '.join(faltan) + ' (025:RF-57)')
    if not 0 < float(esc['cumplimiento']) <= 1 or int(esc['sorteos']) < 1:
        raise EscaleraError('escalera.cumplimiento va entre 0 y 1 y escalera.sorteos es al menos 1')
    # Los precios de pérdidas, en la moneda en que se publican; el costo, en la de trabajo
    # (usuario, 2026-10-24: «trabaja en dólares»), con el tipo de cambio que escribe el
    # operador en la web («la tasa de cambio de dólar debe ingresar por la web»).
    moneda = str(esc.get('moneda') or '')
    de = str(esc.get('moneda_precios_perdidas') or moneda)
    tc = 1.0
    if de != moneda and (esc.get('precio_perdidas_kwh') is not None or esc.get('precio_perdidas_kw_mes') is not None):
        if not tipo_cambio or float(tipo_cambio) <= 0:
            raise EscaleraError(f'los precios de pérdidas están en {de} y se trabaja en {moneda}: escriba en '
                                f'la web el tipo de cambio ({de} por {moneda}) (025:RF-68)')
        tc = float(tipo_cambio)
    esc = {**esc, 'precio_perdidas_kwh': _en(esc.get('precio_perdidas_kwh'), tc),
           'precio_perdidas_kw_mes': _en(esc.get('precio_perdidas_kw_mes'), tc)}
    return Parametros(
        cumplimiento=float(esc['cumplimiento']), sorteos=int(esc['sorteos']),
        semilla=int(esc.get('semilla') or 0), tolerancia_pu=float(esc['tolerancia_pu']),
        tolerancia_carga_pct=float(esc['tolerancia_carga_pct']),
        max_variantes=int(esc.get('max_variantes') or 40), tasa=float(plan['tasa_regulada']),
        vida=int(plan['vida_util_anios']), tension_min_pu=float(lim['tension_min_pu']),
        tension_max_pu=float(lim['tension_max_pu']),
        cargabilidad_max_pct=float(esc.get('cargabilidad_planeamiento_pct') or lim['cargabilidad_max_pct']),   # 042:RF-28
        precio_perdidas_kwh=_opcional(esc.get('precio_perdidas_kwh')),
        precio_perdidas_kw_mes=_opcional(esc.get('precio_perdidas_kw_mes')),
        coym_pct_anual=_opcional(esc.get('coym_pct_anual')), moneda=moneda,
        costos_unitarios={k: float(v) for k, v in (esc.get('costos_unitarios') or {}).items() if v is not None},
        escala_capex=_opcional(esc.get('escala_capex')), con_regulador=bool(esc.get('con_regulador', True)),
        modulos_max=None if esc.get('modulos_max') is None else int(esc['modulos_max']),
        ternas=dict(plan.get('ternas_subterraneas') or {}),
        secciones=tuple(str(x) for x in esc.get('secciones_normalizadas') or ()),
        linea_larga_km=float(esc.get('linea_larga_km') or 10.0))


def _opcional(x) -> float | None:
    return None if x is None else float(x)


def _en(precio, tipo_cambio: float) -> float | None:
    return None if precio is None else float(precio) / tipo_cambio


def costos_de_alternativas(capex: Mapping[str, Mapping[str, Any]], p: Parametros) -> dict[str, dict[str, Any]]:
    """Los del libro CAPEX, y los que el perfil da para las alternativas que el libro no tiene
    (bancos y reguladores en Electro Dunas); el libro manda si tiene la alternativa.

    RF-77: el libro se pasa a la moneda de trabajo con ``escalera.escala_capex``. El de Electro
    Dunas está en miles de dólares y la escalera lo tomaba en dólares: la terna salía a 60,9 por
    km y SI213 eligió terna y sección por las pérdidas (2026-10-24).
    """
    if any(v.get('costo_unitario') for v in capex.values()) and not p.escala_capex:
        raise EscaleraError('el perfil no dice en qué escala está el libro CAPEX respecto de la moneda '
                            f'de trabajo ({p.moneda}): escalera.escala_capex, p. ej. 1000 si está en miles '
                            '(025:RF-77)')
    out = {k: {**v, 'costo_unitario': (float(v['costo_unitario']) * p.escala_capex
                                       if v.get('costo_unitario') else v.get('costo_unitario')),
               'origen': v.get('origen') or 'capex'}
           for k, v in capex.items()}
    for alt, costo_u in p.costos_unitarios.items():
        if alt not in out or not out[alt].get('costo_unitario'):
            out[alt] = {'costo_unitario': costo_u, 'unidad': 'Und' if alt in ('bancos', 'reguladores') else 'km',
                        'origen': 'perfil'}
    return out


# --------------------------------------------------------------------------- variantes
@dataclass
class Variante:
    """Una combinación de obras de la escalera, con lo que hace falta para costearla."""
    nombre: str
    escalones: tuple[str, ...]
    obras: list[dict[str, Any]]
    cantidades: dict[str, float] = field(default_factory=dict)       # escalón → unidades o km
    #: 073:RF-20: un módulo más de los que admite el valle: se mide para dejar constancia, sin combinar.
    solo_evidencia: bool = False


def _troncal_hasta(troncal: Sequence[Mapping[str, Any]], i: int) -> list[Mapping[str, Any]]:
    return list(troncal[:i + 1])


def _km(tramos) -> float:
    return sum(float(t.get('largo_m') or 0) for t in tramos) / 1000


def _nodos(tramos) -> list[dict[str, Any]]:
    """063:RF-31: cada tramo de una obra con su nodo de inicio y su nodo final, de la cabecera a
    la cola; sin esos datos (una lectura anterior), solo el tramo."""
    return [{'tramo': t['nombre'], 'desde': t.get('desde'), 'hasta': t.get('hasta')} for t in tramos]


def ubicacion(obra: Mapping[str, Any]) -> str:
    """Dónde va la obra en la red de media tensión, en una frase (063:RF-31).

    SM218 (2026-11-01, usuario): «en el cambio de tramos de cable y la ubicación de bancos deben
    indicarse los nodos de inicio y el nodo de MT donde se ubica el banco y los tramos».
    """
    if obra.get('clase') == 'condensador':
        return f"banco de {float(obra.get('q_kvar') or 0):g} kvar en el nodo de MT {obra.get('barra')}"
    nodos = list(obra.get('nodos') or [])
    que = (f"sección {(obra.get('tipo') or {}).get('nombre', '')}" if obra.get('clase') == 'seccion'
           else str(obra.get('clase') or 'obra'))
    if nodos and nodos[0].get('desde') and nodos[-1].get('hasta'):
        return (f"{que} desde el nodo {nodos[0]['desde']} hasta el nodo {nodos[-1]['hasta']} "
                f"({len(nodos)} tramos: " + ', '.join(
                    f"{n['tramo']} {n.get('desde') or '?'}→{n.get('hasta') or '?'}" for n in nodos) + ')')
    return f"{que} en los tramos " + ', '.join(str(t) for t in obra.get('tramos') or [])


def _bancos_en(alim, barras, banco_kvar, n: int, solo_evidencia: bool = False) -> Variante:
    # 063:RF-31: la barra del banco es el nodo de MT existente donde se instala.
    obras = [{'clase': 'condensador', 'alimentador': alim, 'casos': [CON_PROYECTO], 'barra': b,
              'q_kvar': float(banco_kvar) * n, 'escalones': n} for b in barras]
    return Variante(f'bancos {n}×{banco_kvar:g} kvar', ('bancos',), obras, {'bancos': float(len(barras) * n)},
                    solo_evidencia)


def _escalon_bancos(alim, barras, banco_kvar, modulos: int) -> list[Variante]:
    if not barras or not banco_kvar:
        return []
    return [_bancos_en(alim, barras, banco_kvar, n) for n in range(1, int(modulos) + 1)]


def nodo_a_dos_tercios(tramos: Sequence[Mapping[str, Any]]) -> str | None:
    """042:RF-37: la barra existente más cercana a 2/3 del camino; la de una carga nueva solo existe con ella."""
    total = _km(tramos)
    if total <= 0:
        return None
    acumulado, mejor = 0.0, None
    for t in tramos:
        acumulado += float(t.get('largo_m') or 0.0) / 1000.0
        hasta = str(t.get('hasta') or '')
        if hasta and not hasta.startswith('NODE_T_'):
            distancia = abs(acumulado - 2.0 * total / 3.0)
            if mejor is None or distancia < mejor[0]:
                mejor = (distancia, hasta)
    return mejor[1] if mejor else None


def _escalon_regulador(alim, kv, troncal, fuera_desde, p: Parametros, avisos) -> list[Variante]:
    """Hasta tres sitios en la troncal, antes de la primera barra fuera de límites, con la
    unidad más chica que lleva la corriente del tramo (RF-60)."""
    try:
        unidades_para(kv)
    except CatalogoError as exc:
        avisos.append(f'{alim}: {exc}; no hay escalón de regulador.')
        return []
    hasta = len(troncal) if fuera_desde is None else max(0, int(fuera_desde))
    candidatos = []
    for i, t in enumerate(troncal[:hasta]):
        corriente = t.get('corriente_a')
        if corriente is None:
            continue
        unidad = unidad_para_corriente(kv, float(corriente))
        if unidad is not None:
            candidatos.append((i, t, unidad))
    if not candidatos:
        avisos.append(f'{alim}: ningún tramo de la troncal antes de la caída lleva una corriente '
                      'que admita un regulador del catálogo; no hay escalón de regulador.')
        return []
    elegidos = sorted({candidatos[min(len(candidatos) - 1, int(f * len(candidatos)))][0]
                       for f in (1 / 3, 1 / 2, 2 / 3)})
    out = []
    for i in elegidos:
        _, t, unidad = next(c for c in candidatos if c[0] == i)
        obra = {'clase': 'regulador', 'alimentador': alim, 'casos': [CON_PROYECTO], 'tramo': t['nombre'],
                'consigna_pu': p.consigna_regulador_pu, 'rango_pct': 10.0, 'pasos': 16,
                'tipo': {'nombre': unidad.nombre, 'clase': 'TypVoltreg', 'origen': 'otro',
                         'proyecto': BIBLIOTECA_TIPOS}}
        out.append(Variante(f"regulador {unidad.corriente_a:g} A en {t['nombre']}", ('regulador',),
                            [obra], {'regulador': 1.0}))
    return out


def camino_electrico(tramos: Sequence[Mapping[str, Any]], origen: str, destino: str) -> list[dict]:
    """Los tramos de ``origen`` a ``destino`` por la red (``desde``, ``hasta``), en orden (063:RF-32).

    El camino más corto en número de tramos, sin pasar dos veces por una barra; vacío si no hay.
    SM218 (2026-11-01): INKA cuelga de un ramal a 17,08 km de la cabecera, no de la troncal más
    larga a 10,32 km donde la ponía la cercanía GPS; las obras se probaban donde no hacía falta.
    """
    from collections import defaultdict, deque

    ady: dict[str, list[tuple[str, Mapping[str, Any]]]] = defaultdict(list)
    for t in tramos:
        ady[str(t['desde'])].append((str(t['hasta']), t))
        ady[str(t['hasta'])].append((str(t['desde']), t))
    previo: dict[str, tuple[str, Mapping[str, Any]] | None] = {origen: None}
    cola = deque([origen])
    while cola and destino not in previo:
        n = cola.popleft()
        for m, t in sorted(ady[n], key=lambda x: str(x[1].get('nombre'))):
            if m not in previo:
                previo[m] = (n, t)
                cola.append(m)
    if destino not in previo:
        return []
    out, n = [], destino
    while previo[n] is not None:
        a, t = previo[n]
        out.append({**t, 'desde': a, 'hasta': n})
        n = a
    return out[::-1]


def _caminos(troncal, cargas) -> list[list[Mapping[str, Any]]]:
    """Por carga, los tramos donde van sección y terna: su camino eléctrico si la lectura lo da
    (063:RF-32); si no, la troncal hasta su índice (025:RF-44). Sin repetir caminos."""
    vistos, out = set(), []
    for c in cargas:
        tramos = list(c.get('camino') or [])
        if not tramos and c.get('indice_troncal') is not None:
            tramos = _troncal_hasta(troncal, int(c['indice_troncal']))
        clave = tuple(t['nombre'] for t in tramos)
        if tramos and clave not in vistos:
            vistos.add(clave)
            out.append(tramos)
    return out


def _escalon_terna(alim, troncal, cargas, ternas=None) -> list[Variante]:
    out = []
    for tramos in _caminos(troncal, cargas):                               # 063:RF-32
        out.append(Variante(f"terna hasta {tramos[-1]['nombre']} ({_km(tramos):.2f} km)", ('terna',),
                            [{'clase': 'terna', 'alimentador': alim, 'casos': [CON_PROYECTO],
                              'tramos': [t['nombre'] for t in tramos], 'nodos': _nodos(tramos),
                              **capacidad_de_tramos(tramos, ternas)}],
                            {'terna': _km(tramos)}))
    return out


def normalizados(tipos, secciones: Sequence[str]) -> list[Mapping[str, Any]]:
    """042:RF-27: solo los conductores normalizados, uno por código (el de ficha si existe); sin lista, todos."""
    if not secciones:
        return list(tipos)
    por_codigo: dict[tuple, Mapping[str, Any]] = {}
    for t in tipos:
        nombre = str(t.get('nombre') or '')
        codigo = next((s for s in secciones if nombre.upper().startswith(s.upper())), None)
        if codigo is None:
            continue
        clave = (codigo, round(float((t.get('datos') or {}).get('uline') or 0), 1))
        if clave not in por_codigo or nombre.upper().endswith('_FICHA'):
            por_codigo[clave] = t
    return list(por_codigo.values())


def _conductores(tipos, kv, corriente_a) -> list[Mapping[str, Any]]:
    """Aéreos de la tensión del alimentador (±10 %) que llevan la corriente, de menor a mayor."""
    out = []
    for t in tipos:
        d = t.get('datos') or {}
        uline, sline = d.get('uline'), d.get('sline')
        if t.get('clase') != 'TypLne' or d.get('cohl_') != 1 or not isinstance(uline, (int, float)):
            continue
        if not isinstance(sline, (int, float)) or abs(float(uline) - kv) > 0.1 * kv:
            continue
        if corriente_a is None or float(sline) * 1000 >= corriente_a:
            out.append(t)
    return sorted(out, key=lambda t: (t['datos']['sline'], t['nombre']))


def _escalon_seccion(alim, kv, troncal, cargas, tipos, avisos) -> list[Variante]:
    out = []
    for tramos in _caminos(troncal, cargas):                               # 063:RF-32
        # 063:RF-30: cada conductor cambia solo los tramos más delgados que él, y tiene que llevar
        # su corriente; por eso aquí se piden todos los de la tensión, sin filtrar por la corriente
        # del tramo más cargado del camino (que ya es de mayor sección).
        delgados = [t for t in tramos if t.get('inom_a') is not None]
        corrientes = [float(t['corriente_a']) for t in tramos if t.get('corriente_a') is not None]
        aptos = _conductores(tipos, kv, None if delgados else (max(corrientes) if corrientes else None))
        if not aptos:
            avisos.append(f"{alim}: ningún conductor aéreo de {kv:g} kV lleva la corriente hasta "
                          f"{tramos[-1]['nombre']}; no hay escalón de sección allí.")
            continue
        # 063:RF-27: todas las aptas, de menor a mayor: se sube de sección en sección y se queda
        # la menor que cumple (antes, las dos primeras; SM218 saltaba a AA 120 mm²).
        for tipo in aptos:
            ref = {'nombre': tipo['nombre'], 'clase': 'TypLne', 'origen': tipo.get('origen') or 'proyecto',
                   'proyecto': tipo.get('proyecto') or ''}
            # 063:RF-30: solo los tramos de menor corriente nominal que la del conductor nuevo; los
            # de igual o mayor sección se quedan. Sin el dato del tramo (una lectura anterior), todos.
            nueva_a = float(tipo['datos']['sline']) * 1000
            cambian = [t for t in tramos if t.get('inom_a') is None or float(t['inom_a']) < nueva_a]
            if not cambian or any(float(t.get('corriente_a') or 0) > nueva_a for t in cambian):
                continue
            out.append(Variante(f"sección {tipo['nombre']} en {len(cambian)} tramos hasta {tramos[-1]['nombre']} "
                                f"({_km(cambian):.2f} km)",
                                ('seccion',),
                                [{'clase': 'seccion', 'alimentador': alim, 'casos': [CON_PROYECTO],
                                  'tramos': [t['nombre'] for t in cambian], 'tipo': ref,
                                  'nodos': _nodos(cambian)}],
                                {'seccion': _km(cambian)}))
    return out


def variantes(alimentador: str, kv: float, troncal: Sequence[Mapping[str, Any]],
              cargas: Sequence[Mapping[str, Any]], tipos: Sequence[Mapping[str, Any]], p: Parametros, *,
              banco_kvar: float | None, fuera_desde: int | None = None, modulos_valle: int | None = None,
              evidencia: bool = True) -> tuple[list[Variante], list[str]]:
    """Las variantes de un alimentador en el orden de RF-44, con sus combinaciones (RF-49).

    ``troncal``: sus tramos desde la cabecera (``nombre``, ``largo_m``, ``corriente_a`` en
    «Con proyecto»). ``cargas``: las nuevas, con ``barra``, ``existe`` (si la barra está sin
    la carga: un banco en la que crea su variación dependería de ella) e ``indice_troncal``.
    ``fuera_desde``: índice del primer tramo cuya barra queda fuera de límites.
    ``modulos_valle``: cuántos módulos de banco admite el valle (073:RF-19); con ``evidencia`` se
    mide también uno más (RF-20), salvo que el tope lo ponga el perfil. Sin él, 073:RF-24.
    """
    avisos: list[str] = []
    barras = list(dict.fromkeys(str(c['barra']) for c in cargas if c.get('existe') and c.get('barra')))
    if not barras:
        avisos.append(f'{alimentador}: ninguna carga nueva está en una barra que exista sin ella; '
                      'no hay escalón de bancos.')
    elif not banco_kvar:
        avisos.append(f'{alimentador}: el perfil no da el tamaño de banco de {kv:g} kV; no hay escalón de bancos.')
    modulos = (modulos_valle if modulos_valle is not None
               else p.modulos_max if p.modulos_max is not None else MODULOS_SIN_VALLE)
    if modulos_valle is not None and barras and banco_kvar:
        avisos.append(f'{alimentador}: el valle admite {modulos_valle} módulos de {banco_kvar:g} kvar en cada barra (073:RF-19).'
                      if modulos_valle else
                      f'{alimentador}: el valle no admite ningún módulo de {banco_kvar:g} kvar (073:RF-19).')
    por_escalon = {
        'bancos': _escalon_bancos(alimentador, barras, banco_kvar, modulos),
        # 025:RF-44: el regulador entra, al final del orden; el perfil puede quitarlo.
        'regulador': (_escalon_regulador(alimentador, kv, troncal, fuera_desde, p, avisos)
                      if p.con_regulador else []),
        'terna': _escalon_terna(alimentador, troncal, cargas, p.ternas),
        'seccion': _escalon_seccion(alimentador, kv, troncal, cargas, normalizados(tipos, p.secciones), avisos),
    }
    solas = [v for e in ORDEN for v in por_escalon[e]]
    if modulos_valle is not None and evidencia and barras and banco_kvar:
        solas.insert(len(por_escalon['bancos']), _bancos_en(alimentador, barras, banco_kvar, modulos + 1, True))
    combinadas, dobles = [], []
    for i, a in enumerate(ORDEN):
        for b in ORDEN[i + 1:]:
            for va in por_escalon[a]:
                for vb in por_escalon[b]:
                    v = Variante(f'{va.nombre} + {vb.nombre}', va.escalones + vb.escalones,
                                 va.obras + vb.obras, {**va.cantidades, **vb.cantidades})
                    if {a, b} == {'seccion', 'terna'}:
                        # 042:RF-30: sección y terna en caminos distintos no se refuerzan; en el mismo, son la
                        # doble terna del conductor nuevo, y van antes que el resto (el tope de variantes).
                        sec, ter = (va, vb) if a == 'seccion' else (vb, va)
                        if not set(sec.obras[0]['tramos']) <= set(ter.obras[0]['tramos']):
                            continue
                        dobles.append(v)
                    else:
                        combinadas.append(v)
    caminos = _caminos(troncal, cargas)
    largo_km = max((_km(c) for c in caminos), default=0.0)
    if largo_km >= p.linea_larga_km and banco_kvar:
        # 042:RF-37: en línea larga, también donde más rinde el banco; SI112 no tenía ninguno, su carga parte un tramo.
        nodo = nodo_a_dos_tercios(max(caminos, key=_km))
        if nodo and nodo not in barras:
            en_nodo = [_bancos_en(alimentador, [nodo], banco_kvar, n) for n in range(1, int(modulos) + 1)]
            for v in en_nodo:
                v.nombre = f'{v.nombre} a 2/3 de la línea en {nodo}'
            solas[len(por_escalon['bancos']):len(por_escalon['bancos'])] = en_nodo
    if por_escalon['regulador'] and largo_km >= p.linea_larga_km:
        # 042:RF-35: en línea larga, el regulador no puede quedar detrás del tope; también con la doble terna más larga.
        mas_largas = sorted(dobles, key=lambda v: -float(v.cantidades.get('terna') or 0.0))[:3]
        triples = [Variante(f'{d.nombre} + {r.nombre}', d.escalones + r.escalones, d.obras + r.obras,
                            {**d.cantidades, **r.cantidades}) for d in mas_largas for r in por_escalon['regulador']]
        combinadas = (triples + [v for v in combinadas if 'regulador' in v.escalones]
                      + [v for v in combinadas if 'regulador' not in v.escalones])
        avisos.append(f'{alimentador}: línea de {largo_km:.1f} km: se plantean reguladores, también con la doble terna (042:RF-35).')
    todas = solas + dobles + combinadas
    if len(todas) > p.max_variantes:
        avisos.append(f'{alimentador}: {len(todas)} variantes; se prueban las {p.max_variantes} primeras '
                      'en el orden de la escalera (escalera.max_variantes del perfil).')
    return todas[:p.max_variantes], avisos


# --------------------------------------------------------------------------- criterio
def cumple(sin: Mapping[str, Any], con: Mapping[str, Any], barras_cargas: Sequence[str],
           p: Parametros) -> tuple[bool, list[str]]:
    """Si un flujo con la variante cumple (RF-50): converge, cada carga nueva con su tensión
    y nada peor que en «Sin proyecto» con la misma demanda.

    ``sin`` y ``con``: ``converge``, ``u`` (barra → p.u.) y ``carga`` (elemento → %).
    """
    if not con.get('converge'):
        return False, ['no converge']
    motivos = []
    lo, hi = p.tension_min_pu, p.tension_max_pu
    u_con, u_sin = con.get('u') or {}, sin.get('u') or {}
    for b in barras_cargas:
        u = u_con.get(b)
        if u is None or not lo <= u <= hi:
            motivos.append(f'la carga nueva en {b} queda a {u if u is not None else "?"} p.u.')
    for b, u in u_con.items():
        s = u_sin.get(b)
        if s is None or b in barras_cargas:
            continue
        if lo <= s <= hi and not lo <= u <= hi:
            motivos.append(f'{b} sale de los límites: {s:.3f} → {u:.3f} p.u.')
        elif s < lo and u < s - p.tolerancia_pu:
            motivos.append(f'{b} baja más: {s:.3f} → {u:.3f} p.u.')
        elif s > hi and u > s + p.tolerancia_pu:
            motivos.append(f'{b} sube más: {s:.3f} → {u:.3f} p.u.')
    lim = p.cargabilidad_max_pct
    c_sin = sin.get('carga') or {}
    for e, c in (con.get('carga') or {}).items():
        s = c_sin.get(e)
        if s is None or s <= lim:
            if c > lim:
                motivos.append(f'{e} pasa al {c:.0f} %')
        elif c > s + p.tolerancia_carga_pct:
            motivos.append(f'{e} se carga más: {s:.0f} → {c:.0f} %')
    return not motivos, motivos[:5]


# --------------------------------------------------------------------------- sorteos
def sorteos(curva: Sequence[tuple[Any, Mapping[str, float]]], maximas: Mapping[str, float],
            n: int, semilla: int) -> list[dict[str, Any]]:
    """``n`` instantes de la curva de cabecera del año, con reemplazo, y el factor de cada
    alimentador: su potencia en ese instante entre su máxima (RF-51). Un instante común a
    todos los alimentadores del proyecto (021:RF-50); con la misma semilla, lo mismo (RF-58).
    """
    puntos = [(t, {f: float(kw) / float(maximas[f]) for f, kw in por.items()
                   if f in maximas and maximas[f] and kw is not None and math.isfinite(float(kw))})
              for t, por in curva]
    puntos = [(t, fs) for t, fs in puntos if set(fs) == set(maximas)]
    if not puntos:
        raise EscaleraError('la curva de cabecera del año no tiene ningún instante con todos los '
                            'alimentadores medidos: no se puede sortear (025:RF-51)')
    rng = random.Random(semilla)
    return [{'instante': str(t), 'factores': fs} for t, fs in rng.choices(puntos, k=int(n))]


# --------------------------------------------------------------------------- costo y elección
def _cantidad_en(unidad: str, cantidad: float, escalon: str) -> float:
    u = (unidad or '').strip().lower()
    if escalon in ('terna', 'seccion'):
        if u in ('m', 'metro', 'metros', 'ml'):
            return cantidad * 1000
        return cantidad                                                  # km, o sin unidad
    return cantidad


def costo(v: Variante, costos_alternativa: Mapping[str, Mapping[str, Any]], p: Parametros, *,
          perdidas_kw: float | None, factor_perdidas: float | None) -> dict[str, Any]:
    """Inversión con los costos unitarios del CAPEX y costo anual del art. 14 (RF-53)."""
    ci, avisos = 0.0, []
    for escalon, cantidad in v.cantidades.items():
        alt = ALTERNATIVA[escalon]
        c = costos_alternativa.get(alt)
        if not c or not c.get('costo_unitario'):
            raise EscaleraError(f'el libro CAPEX no tiene costo de «{alt}» para {escalon} (025:RF-57)')
        ci += _cantidad_en(c.get('unidad') or '', cantidad, escalon) * float(c['costo_unitario'])
    coym = ci * p.coym_pct_anual / 100 if p.coym_pct_anual is not None else None
    # Energía perdida en el año (kW de la máxima por el factor de pérdidas) a su precio, y la
    # potencia de la máxima a su precio por mes (precios en barra del perfil).
    cp = (perdidas_kw * factor_perdidas * HORAS_ANIO * p.precio_perdidas_kwh
          + perdidas_kw * 12 * (p.precio_perdidas_kw_mes or 0.0)
          if None not in (perdidas_kw, factor_perdidas, p.precio_perdidas_kwh) else None)
    if coym is None:
        avisos.append('sin COyM (escalera.coym_pct_anual del perfil)')
    if cp is None:
        avisos.append('sin costo de pérdidas (escalera.precio_perdidas_kwh del perfil o factor de pérdidas)')
    out = costo_anual(ci, coym, cp, tasa=p.tasa, vida=p.vida)
    return {**out, 'inversion': ci, 'avisos': avisos}


def elegir(evaluadas: Sequence[Mapping[str, Any]], p: Parametros) -> dict[str, Any]:
    """La de menor costo anual entre las que cumplen con la máxima y en la fracción de sorteos
    del perfil (RF-52b, RF-53); si ninguna, la que más se acerca, sin aplicarla (RF-56).

    Cada evaluada: ``nombre``, ``maxima`` (cumple con la máxima), ``fraccion`` (de sorteos que
    cumplen; ``None`` sin sortear), ``costo`` (de :func:`costo`) y ``motivos``.
    """
    tabla = []
    for e in evaluadas:
        # 073:RF-17, RF-18: en valle se cumple o no; la fracción de sorteos no lo compensa. Sin valle
        # medido (``None``) no se bloquea, y queda dicho (RF-24).
        en_valle = e.get('valle')
        cumple_tec = bool(e.get('maxima')) and (e.get('fraccion') or 0) >= p.cumplimiento and en_valle is not False
        con_costo = (e.get('costo') or {}).get('costo_anual') is not None
        factible = cumple_tec and con_costo
        if e.get('maxima') and en_valle is False:
            motivo = ('cumple con la máxima; en valle no: ' + '; '.join(e.get('valle_motivos') or [])
                      + ' (073:RF-17)')
        elif factible:
            # 073:RF-40: bancos y proyectos: toda obra que se vaya a implementar.
            motivo = 'no comprobado en valle' if en_valle is None and e.get('escalones') else ''
        elif cumple_tec:
            motivo = 'cumple, pero sin costo: ' + str(e.get('sin_costo') or 'falta su costo unitario')
        elif e.get('maxima') and e.get('fraccion') is None:
            motivo = 'cumple con la máxima; ' + str(e.get('sin_sortear') or 'no se sorteó')    # RF-71
        elif not e.get('maxima'):
            motivo = 'no cumple con la máxima: ' + '; '.join(e.get('motivos') or [])
        else:
            motivo = (f"cumple en el {100 * (e.get('fraccion') or 0):.0f} % de los sorteos "
                      f"(pide {100 * p.cumplimiento:.0f} %)")
        tabla.append({**e, 'factible': factible, 'motivo': motivo})
    factibles = [t for t in tabla if t['factible']]
    if factibles:
        # 063:RF-22: el primer escalón que cumple; dentro de él, la de menor costo anual. En SM218
        # (2026-11-01) 128 m de conductor salían más baratos que los bancos, y el usuario pide los
        # bancos si ya bastan.
        mejor = min(factibles, key=lambda t: (rango(t.get('escalones') or ()), t['costo']['costo_anual'],
                                              t['nombre']))
        for t in factibles:
            if t is mejor:
                continue
            if rango(t.get('escalones') or ()) > rango(mejor.get('escalones') or ()):
                t['motivo'] = f"no hace falta: «{mejor['nombre']}» ya cumple en un escalón anterior"
            else:
                t['motivo'] = (f"cuesta más al año: {t['costo']['costo_anual']:,.0f} frente a "
                               f"{mejor['costo']['costo_anual']:,.0f}")
        return {'elegida': mejor['nombre'], 'mas_cercana': None, 'tabla': tabla, **_marcas_de_valle(mejor, tabla)}
    # 063:RF-33: si alguna cumple con la máxima en DIgSILENT y tiene costo, se elige la primera por
    # el orden de prioridad aunque los sorteos no la confirmen, y se avisa para revisarlos; no se
    # pasa a otras obras ni a la SET nueva. SM218 (2026-11-01): banco 450 kvar + AA 120 mm² cumplía
    # con la máxima y los sorteos daban 94,5 % por un defecto de la evaluación, y el flujo saltaba
    # a la SET nueva.
    # 073:RF-18: aquí no entra lo que no cumple en valle.
    con_maxima = [t for t in tabla if t.get('maxima') and t.get('valle') is not False
                  and (t.get('costo') or {}).get('costo_anual') is not None]
    if con_maxima:
        mejor = min(con_maxima, key=lambda t: (rango(t.get('escalones') or ()), t['costo']['costo_anual'],
                                               t['nombre']))
        mejor['motivo'] = (f"cumple con la máxima en DIgSILENT; los sorteos dieron "
                           f"{100 * (mejor.get('fraccion') or 0):.1f} % (pide {100 * p.cumplimiento:.0f} %): "
                           'se elige y hay que revisar los sorteos (063:RF-33)')
        return {'elegida': mejor['nombre'], 'mas_cercana': None, 'tabla': tabla, 'sin_confirmar_sorteos': True,
                **_marcas_de_valle(mejor, tabla)}
    cercana = max(tabla, key=lambda t: (bool(t.get('maxima')) and t.get('valle') is not False, t.get('fraccion') or 0),
                  default=None)
    return {'elegida': None, 'mas_cercana': cercana['nombre'] if cercana else None, 'tabla': tabla,
            **_marcas_de_valle(None, tabla)}


def _marcas_de_valle(mejor: Mapping[str, Any] | None, tabla: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Lo que la elección dice del valle: la elegida sin comprobar (073:RF-24) y que el valle no
    aguanta los bancos que pide la máxima, con el hueco de los bancos por pasos (RF-20, RF-27)."""
    out: dict[str, Any] = {}
    if mejor is not None and mejor.get('valle') is None and mejor.get('escalones'):
        out['sin_comprobar_valle'] = True
    solo_bancos = [t for t in tabla if tuple(t.get('escalones') or ()) == ('bancos',)]
    if not any(t.get('factible') for t in solo_bancos):
        rechazadas = [t['nombre'] for t in solo_bancos if t.get('maxima') and t.get('valle') is False]
        if rechazadas:
            out['aviso_valle'] = (f"la máxima pide {', '.join(rechazadas)} y el valle no lo aguanta: sigue la escalera "
                                  '(073:RF-20). La obra de banco por pasos existe (011:RF-71, RF-72), pero esta '
                                  'escalera no la genera ni el oráculo la mide (073:RF-27).')
    return out
