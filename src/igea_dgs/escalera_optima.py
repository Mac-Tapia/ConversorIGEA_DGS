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
from .pide_economia import costo_anual

#: Orden de la escalera (RF-44): primero lo más barato.
ORDEN = ('bancos', 'regulador', 'terna', 'seccion')
#: Alternativa del PIDE de cada escalón, para su costo en el libro CAPEX (RF-53).
ALTERNATIVA = {'bancos': 'bancos', 'regulador': 'reguladores', 'terna': 'nueva_terna',
               'seccion': 'cambio_seccion'}
#: Proyecto de DIgSILENT con los reguladores de catálogo (025:RF-59).
BIBLIOTECA_TIPOS = 'IGEA_Biblioteca_tipos'
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
        cargabilidad_max_pct=float(lim['cargabilidad_max_pct']),
        precio_perdidas_kwh=_opcional(esc.get('precio_perdidas_kwh')),
        precio_perdidas_kw_mes=_opcional(esc.get('precio_perdidas_kw_mes')),
        coym_pct_anual=_opcional(esc.get('coym_pct_anual')), moneda=moneda,
        costos_unitarios={k: float(v) for k, v in (esc.get('costos_unitarios') or {}).items() if v is not None})


def _opcional(x) -> float | None:
    return None if x is None else float(x)


def _en(precio, tipo_cambio: float) -> float | None:
    return None if precio is None else float(precio) / tipo_cambio


def costos_de_alternativas(capex: Mapping[str, Mapping[str, Any]], p: Parametros) -> dict[str, dict[str, Any]]:
    """Los del libro CAPEX, y los que el perfil da para las alternativas que el libro no tiene
    (bancos y reguladores en Electro Dunas); el libro manda si tiene la alternativa."""
    out = {k: dict(v) for k, v in capex.items()}
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


def _troncal_hasta(troncal: Sequence[Mapping[str, Any]], i: int) -> list[Mapping[str, Any]]:
    return list(troncal[:i + 1])


def _km(tramos) -> float:
    return sum(float(t.get('largo_m') or 0) for t in tramos) / 1000


def _escalon_bancos(alim, barras, banco_kvar) -> list[Variante]:
    if not barras or not banco_kvar:
        return []
    out = []
    for n in (1, 2):
        obras = [{'clase': 'condensador', 'alimentador': alim, 'casos': [CON_PROYECTO], 'barra': b,
                  'q_kvar': float(banco_kvar) * n, 'escalones': n} for b in barras]
        out.append(Variante(f'bancos {n}×{banco_kvar:g} kvar', ('bancos',), obras,
                            {'bancos': float(len(barras) * n)}))
    return out


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


def _hasta_cada_carga(troncal, cargas) -> list[int]:
    return sorted({int(c['indice_troncal']) for c in cargas if c.get('indice_troncal') is not None})


def _escalon_terna(alim, troncal, cargas) -> list[Variante]:
    out = []
    for i in _hasta_cada_carga(troncal, cargas):
        tramos = _troncal_hasta(troncal, i)
        out.append(Variante(f"terna hasta {tramos[-1]['nombre']} ({_km(tramos):.2f} km)", ('terna',),
                            [{'clase': 'terna', 'alimentador': alim, 'casos': [CON_PROYECTO],
                              'tramos': [t['nombre'] for t in tramos]}], {'terna': _km(tramos)}))
    return out


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
    for i in _hasta_cada_carga(troncal, cargas):
        tramos = _troncal_hasta(troncal, i)
        corrientes = [float(t['corriente_a']) for t in tramos if t.get('corriente_a') is not None]
        aptos = _conductores(tipos, kv, max(corrientes) if corrientes else None)
        if not aptos:
            avisos.append(f"{alim}: ningún conductor aéreo de {kv:g} kV lleva la corriente hasta "
                          f"{tramos[-1]['nombre']}; no hay escalón de sección allí.")
            continue
        for tipo in aptos[:2]:
            ref = {'nombre': tipo['nombre'], 'clase': 'TypLne', 'origen': tipo.get('origen') or 'proyecto',
                   'proyecto': tipo.get('proyecto') or ''}
            out.append(Variante(f"sección {tipo['nombre']} hasta {tramos[-1]['nombre']} ({_km(tramos):.2f} km)",
                                ('seccion',),
                                [{'clase': 'seccion', 'alimentador': alim, 'casos': [CON_PROYECTO],
                                  'tramos': [t['nombre'] for t in tramos], 'tipo': ref}],
                                {'seccion': _km(tramos)}))
    return out


def variantes(alimentador: str, kv: float, troncal: Sequence[Mapping[str, Any]],
              cargas: Sequence[Mapping[str, Any]], tipos: Sequence[Mapping[str, Any]], p: Parametros, *,
              banco_kvar: float | None, fuera_desde: int | None = None) -> tuple[list[Variante], list[str]]:
    """Las variantes de un alimentador en el orden de RF-44, con sus combinaciones (RF-49).

    ``troncal``: sus tramos desde la cabecera (``nombre``, ``largo_m``, ``corriente_a`` en
    «Con proyecto»). ``cargas``: las nuevas, con ``barra``, ``existe`` (si la barra está sin
    la carga: un banco en la que crea su variación dependería de ella) e ``indice_troncal``.
    ``fuera_desde``: índice del primer tramo cuya barra queda fuera de límites.
    """
    avisos: list[str] = []
    barras = list(dict.fromkeys(str(c['barra']) for c in cargas if c.get('existe') and c.get('barra')))
    if not barras:
        avisos.append(f'{alimentador}: ninguna carga nueva está en una barra que exista sin ella; '
                      'no hay escalón de bancos.')
    elif not banco_kvar:
        avisos.append(f'{alimentador}: el perfil no da el tamaño de banco de {kv:g} kV; no hay escalón de bancos.')
    por_escalon = {
        'bancos': _escalon_bancos(alimentador, barras, banco_kvar),
        'regulador': _escalon_regulador(alimentador, kv, troncal, fuera_desde, p, avisos),
        'terna': _escalon_terna(alimentador, troncal, cargas),
        'seccion': _escalon_seccion(alimentador, kv, troncal, cargas, tipos, avisos),
    }
    solas = [v for e in ORDEN for v in por_escalon[e]]
    combinadas = []
    for i, a in enumerate(ORDEN):
        for b in ORDEN[i + 1:]:
            for va in por_escalon[a]:
                for vb in por_escalon[b]:
                    combinadas.append(Variante(f'{va.nombre} + {vb.nombre}', va.escalones + vb.escalones,
                                               va.obras + vb.obras, {**va.cantidades, **vb.cantidades}))
    todas = solas + combinadas
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
        cumple_tec = bool(e.get('maxima')) and (e.get('fraccion') or 0) >= p.cumplimiento
        con_costo = (e.get('costo') or {}).get('costo_anual') is not None
        factible = cumple_tec and con_costo
        if factible:
            motivo = ''
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
        mejor = min(factibles, key=lambda t: (t['costo']['costo_anual'], t['nombre']))
        for t in factibles:
            if t is not mejor:
                t['motivo'] = (f"cuesta más al año: {t['costo']['costo_anual']:,.0f} frente a "
                               f"{mejor['costo']['costo_anual']:,.0f}")
        return {'elegida': mejor['nombre'], 'mas_cercana': None, 'tabla': tabla}
    cercana = max(tabla, key=lambda t: (bool(t.get('maxima')), t.get('fraccion') or 0), default=None)
    return {'elegida': None, 'mas_cercana': cercana['nombre'] if cercana else None, 'tabla': tabla}
