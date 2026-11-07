"""Las obras de después de la escalera: transferir, trasladar, alimentador nuevo y SET nueva (spec 087, RF-31 a RF-38).

Pisco, 2026-11-04: cuando bancos, sección, terna y regulador no bastaban, el alimentador iba directo a la SET nueva o al
expreso, sin probar antes lo que hace un distribuidor: pasar la parte que no cabe al alimentador vecino que tiene margen
(«debe integrar como obra nuevos alimentadores, transferencias de cargas, traslado de cargas, las nuevas celdas»).

Transferir y trasladar son la misma obra física con dos alcances: un enlace del vecino a la red del que no cumple, y la
parte de aguas abajo pasa a alimentarse por él (la migración de la 016, que abre su tramo de entrada y cierra el enlace,
y cambia la tensión si el vecino tiene otra). La transferencia lleva la cola de la troncal desde donde sale de los
límites; el traslado, solo la rama de la carga nueva. Los constructores son los de ``tools/obras_pf.py`` (enlace y
migración, 016:RF-26 a RF-80); aquí solo se decide qué probar, con qué vecino y desde qué nodo.

Puro: no habla con DIgSILENT. Los vecinos los lee ``obras_pf.py --vecinos`` y las variantes se miden con la escalera.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from .escalera_optima import Parametros, Variante, conductores_aptos, nodo_a_dos_tercios
from .estudios_pf import CON_PROYECTO

#: 087:RF-31: el orden de las obras integrales; se para en la primera que cumple en DIgSILENT.
ORDEN = ('transferencia', 'traslado', 'expreso', 'set_nueva')
#: Vecinos que se prueban como mucho (087:RF-39): el más cercano con margen y uno más, no todos.
MAX_VECINOS = 2
#: De la recta a las vías hasta que el constructor mide el trazado de verdad (016:RF-81): solo para costear antes.
FACTOR_RUTA = 1.3
#: Margen que debe conservar el vecino sobre los límites para recibir carga (087:RF-32).
MARGEN_TENSION_PU = 0.01
MARGEN_CARGA_PCT = 10.0


def nodo_de_rama(camino: Sequence[Mapping[str, Any]], troncal: set[str], barra: str) -> str:
    """087:RF-33: la primera barra de la rama de la carga, fuera de la troncal; la propia barra si cuelga de ella.

    ``camino`` va de la cabecera a la carga, orientado (``desde`` → ``hasta``); la troncal, por nombres de tramo.
    """
    for t in camino:
        if str(t.get('nombre')) not in troncal:
            return str(t.get('hasta') or barra)
    return barra


def nodo_de_transferencia(camino: Sequence[Mapping[str, Any]], troncal: set[str], tension_min_pu: float) -> str | None:
    """087:RF-32: la barra de la troncal donde la tensión sale del límite; sin ella, la de 2/3 de la troncal (042:RF-37).

    Lo que se transfiere es todo lo de aguas abajo, así que solo vale una barra de la troncal: si sale de límites ya en
    la rama, la transferencia sería el traslado y no se propone dos veces.
    """
    en_troncal = [t for t in camino if str(t.get('nombre')) in troncal]
    for t in en_troncal:
        hasta = str(t.get('hasta') or '')
        u = (t.get('u') or {}).get(hasta)
        if u is not None and float(u) < tension_min_pu and not hasta.startswith('NODE_T_'):
            return hasta
    return nodo_a_dos_tercios(en_troncal)


def vecinos_con_margen(vecinos: Sequence[Mapping[str, Any]], p: Parametros, n: int = MAX_VECINOS) -> list[dict[str, Any]]:
    """087:RF-32: los más cercanos que conservan margen de tensión y de carga, como mucho ``n``.

    ``vecinos``: ``alimentador``, ``kv``, ``distancia_m`` (de su barra más cercana al nodo), ``u_min`` y
    ``carga_max_pct`` con su flujo de «Con proyecto». Sin flujo (``u_min`` nulo) no se sabe su margen: no se propone.
    """
    buenos = [dict(v) for v in vecinos
              if v.get('u_min') is not None and float(v['u_min']) >= p.tension_min_pu + MARGEN_TENSION_PU
              and float(v.get('carga_max_pct') or 0.0) <= p.cargabilidad_max_pct - MARGEN_CARGA_PCT
              and v.get('distancia_m') is not None]
    return sorted(buenos, key=lambda v: (float(v['distancia_m']), str(v['alimentador'])))[:max(0, n)]


def _tipo_del_enlace(tipos, kv: float, corriente_a: float | None) -> dict[str, Any] | None:
    aptos = conductores_aptos(tipos, kv, corriente_a)
    if not aptos:
        return None
    t = aptos[0]
    return {'nombre': t['nombre'], 'clase': 'TypLne', 'origen': t.get('origen') or 'proyecto', 'proyecto': t.get('proyecto') or ''}


def con_maniobras(camino: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """098:RF-11: los tramos del camino (sin los equipos en serie, 042:RF-44) con la maniobra que abre cada uno.

    ``maniobra`` (un interruptor o seccionador en un cubículo del tramo) ya viene de la lectura; un acoplador del camino
    pasa al tramo que lo sigue como ``maniobra_previa``: abrirlo separa desde la barra de inicio de ese tramo.
    """
    out: list[dict[str, Any]] = []
    previa = None
    for t in camino:
        if t.get('puente'):
            previa = t.get('maniobra') or None
            continue
        fila = dict(t)
        if previa is not None:
            fila['maniobra_previa'] = previa
        out.append(fila)
        previa = None
    return out


def _puntos_con_maniobra(camino: Sequence[Mapping[str, Any]], troncal: set[str]) -> list[tuple[str, Any]]:
    """Las barras de la troncal, en orden, con la maniobra que la separa de aguas arriba (o ``None``)."""
    out: list[tuple[str, Any]] = []
    for t in camino:
        if str(t.get('nombre')) not in troncal:
            continue
        if t.get('maniobra_previa') and t.get('desde'):
            out.append((str(t['desde']), t['maniobra_previa']))
        out.append((str(t.get('hasta') or ''), t.get('maniobra') or None))
    return out


def candidatos_de_transferencia(camino: Sequence[Mapping[str, Any]], troncal: set[str], tension_min_pu: float) -> list[str]:
    """087:RF-52: las barras de la troncal, en el camino de la carga, desde las que se puede transferir la cola: desde la
    que sale de límites (o la de 2/3) hasta el final de la troncal. Cuál se usa lo decide la distancia a cada vecino.

    098:RF-11: solo donde ya hay una maniobra que abrir. CA101 (2026-11-07): el operador transfiere en un punto con
    seccionador; una transferencia propuesta en una barra sin él obligaba a cortar el tramo en campo.
    """
    return [b for b, m in _desde_el_nodo(camino, troncal, tension_min_pu) if m is not None]


def _desde_el_nodo(camino, troncal, tension_min_pu) -> list[tuple[str, Any]]:
    puntos = _puntos_con_maniobra(camino, troncal)
    desde = nodo_de_transferencia(camino, troncal, tension_min_pu)
    barras = [b for b, _m in puntos]
    if desde in barras:
        puntos = puntos[barras.index(desde):]
    return [(b, m) for b, m in puntos if b and not b.startswith('NODE_T_')]


def nodo_de_traslado(camino: Sequence[Mapping[str, Any]], troncal: set[str], barra: str) -> str | None:
    """098:RF-11: el traslado sale de la primera barra de la rama con maniobra; la propia barra si cuelga de la troncal.

    Sin ninguna maniobra en la rama no se traslada (098:RF-13)."""
    rama = [t for t in camino if str(t.get('nombre')) not in troncal]
    if not rama:
        return nodo_de_rama(camino, troncal, barra)
    for t in rama:
        if t.get('maniobra_previa') and t.get('desde'):
            return str(t['desde'])
        if t.get('maniobra'):
            return str(t.get('hasta') or barra)
    return None


def nodos_de_traspaso(camino: Sequence[Mapping[str, Any]], troncal: set[str], barra_carga: str,
                      p: Parametros) -> dict[str, Any]:
    """087:RF-32, RF-33, RF-52: de dónde se puede transferir (varias barras) y desde dónde se traslada (la rama).

    098:RF-11, RF-13: solo desde barras con una maniobra; ``sin_maniobra`` dice si había barras candidatas y ninguna la
    tenía, para avisarlo."""
    traslado = nodo_de_traslado(camino, troncal, barra_carga)
    puntos = _desde_el_nodo(camino, troncal, p.tension_min_pu)
    con = [b for b, m in puntos if m is not None and b != traslado]
    rama = any(str(t.get('nombre')) not in troncal for t in camino)
    return {'transferencia': con, 'traslado': traslado,
            'sin_maniobra': {'transferencia': bool(puntos) and not [b for b, m in puntos if m is not None],
                             'traslado': rama and traslado is None}}


def variantes(alimentador: str, kv: float, camino: Sequence[Mapping[str, Any]], troncal: set[str], barra_carga: str,
              vecinos: Mapping[str, Sequence[Mapping[str, Any]]], tipos, p: Parametros) -> tuple[list[Variante], list[str]]:
    """087:RF-31 a RF-33: con cada vecino útil, la transferencia y después el traslado, en el orden de :data:`ORDEN`.

    ``vecinos``: por nodo, los que da ``obras_pf.py --vecinos``.
    """
    avisos: list[str] = []
    nodos = nodos_de_traspaso(camino, troncal, barra_carga, p)
    for clase, falta in nodos['sin_maniobra'].items():
        if falta:
            avisos.append(f'{alimentador}: ninguna barra de su {"troncal" if clase == "transferencia" else "rama"} desde '
                          f'la que hacer la {clase} tiene un interruptor o seccionador que abrir: no se propone (098:RF-13).')
    corriente = {str(t.get('hasta')): t.get('corriente_a') for t in camino}
    out: list[Variante] = []
    # 087:RF-52: por cada vecino con margen, la transferencia desde la barra de la troncal más cercana a él. CHI201 (Pisco,
    # 2026-11-04): con un único nodo fijo, la de 189 m a SC215 dejaba de proponerse en cuanto cambiaba la tensión leída.
    por_vecino: dict[str, tuple[str, dict[str, Any]]] = {}
    for nodo in nodos['transferencia']:
        for v in vecinos_con_margen(vecinos.get(nodo) or (), p, n=len(vecinos.get(nodo) or ())):
            actual = por_vecino.get(v['alimentador'])
            if actual is None or float(v['distancia_m']) < float(actual[1]['distancia_m']):
                por_vecino[v['alimentador']] = (nodo, v)
    elegidos = sorted(por_vecino.values(), key=lambda x: float(x[1]['distancia_m']))[:MAX_VECINOS]
    pedidos = [('transferencia', nodo, [v]) for nodo, v in elegidos]
    if nodos['traslado']:
        pedidos.append(('traslado', nodos['traslado'], vecinos_con_margen(vecinos.get(nodos['traslado']) or (), p)))
    if not elegidos and nodos['transferencia']:
        avisos.append(f'{alimentador}: ningún alimentador vecino de su troncal conserva margen de tensión y de carga '
                      'para recibir su transferencia (087:RF-32).')
    for clase, nodo, utiles in pedidos:
        if not utiles:
            avisos.append(f'{alimentador}: ningún alimentador vecino de {nodo} conserva margen de tensión y de carga '
                          f'para recibir su {clase} (087:RF-32).')
            continue
        for v in utiles:
            kv_v = float(v.get('kv') or kv)
            tipo = _tipo_del_enlace(tipos, kv_v, corriente.get(nodo))
            if tipo is None:
                avisos.append(f"{alimentador}: ningún conductor de {kv_v:g} kV para el enlace con {v['alimentador']} "
                              f'(087:RF-32).')
                continue
            km = float(v['distancia_m']) / 1000.0 * FACTOR_RUTA
            otra = not math.isclose(kv_v, float(kv), rel_tol=1e-3)
            texto = 'transferencia' if clase == 'transferencia' else 'traslado de la rama'
            out.append(Variante(
                f"{texto} desde {nodo} a {v['alimentador']}" + (f' ({kv_v:g} kV)' if otra else '')
                + f' con enlace de {km:.2f} km',
                (clase,),
                [{'clase': 'enlace', 'alimentador': v['alimentador'], 'cede': alimentador, 'casos': [CON_PROYECTO],
                  'destino': nodo, 'tipo': tipo},
                 {'clase': 'migracion', 'alimentador': alimentador, 'casos': [CON_PROYECTO], 'nodo': nodo,
                  'kv_destino': kv_v}],
                {clase: km}))
    return out, avisos


def variantes_por_enlace(alimentador: str, enlaces: Sequence[Mapping[str, Any]], p: Parametros) -> tuple[list[Variante], list[str]]:
    """098:RF-21, RF-22: transferir la cola por un enlace que ya existe, abriendo una maniobra que ya existe.

    CA101 y CHN102 (2026-11-07): la escalera fue al paso a 22,9 kV de 107 km y a la obra integral sin probar la
    transferencia por el enlace que ya unía los dos («ya existe el punto de enlace con CHN102»). ``enlaces``: los que
    da ``obras_pf.py --escalera-datos``, cada uno con ``enlace``, ``clase``, ``cerrado``, ``vecino`` y ``puntos`` (las
    maniobras del camino de la cabecera a su barra, en orden). Se proponen de la más cercana al enlace hacia la cabecera;
    sin línea nueva, así que sin cantidades: el costo es el de las pérdidas. Un vecino sin margen de tensión o de carga
    (087:RF-32), si se conoce, no recibe.
    """
    avisos: list[str] = []
    out: list[Variante] = []
    vistos: set[tuple[str, str]] = set()
    for e in enlaces:
        vecino = str(e.get('vecino') or '')
        if not vecino or vecino == alimentador:
            continue
        # 098:RF-43: devolver parte de la zona del operador a su alimentador se mide con los dos (098:RF-25), aunque el que
        # la recibe de vuelta no tenga margen ahora: es mover el corte de la misma transferencia.
        if (e.get('u_min') is not None and not e.get('devuelve_zona')
                and not vecinos_con_margen([{**e, 'alimentador': vecino, 'distancia_m': 0.0}], p)):
            avisos.append(f"{alimentador}: {vecino} no conserva margen de tensión y de carga para recibir por "
                          f"{e.get('enlace')} (087:RF-32, 098:RF-21).")
            continue
        puntos = [x for x in (e.get('puntos') or []) if (x.get('maniobra') or {}).get('nombre')]
        if not puntos:
            avisos.append(f"{alimentador}: ninguna maniobra en el camino hasta el enlace {e.get('enlace')} con {vecino}: "
                          'no se transfiere por él (098:RF-13).')
            continue
        # 098:RF-22: de la más cercana al enlace; 098:RF-43: al mover el corte de la zona del operador, de la más lejana,
        # la que devuelve más carga y deja pasar menos.
        for x in (puntos if e.get('devuelve_zona') else reversed(puntos)):
            m = x['maniobra']
            clave = (str(e.get('enlace')), str(m.get('ruta') or m['nombre']))
            if clave in vistos:
                continue
            vistos.add(clave)
            out.append(Variante(
                (f"otro corte de la transferencia: devolver a {vecino} por {e.get('enlace')} abriendo {m['nombre']}"
                 if e.get('devuelve_zona') else f"transferencia a {vecino} por {e.get('enlace')} abriendo {m['nombre']}")
                + (f" en {x.get('rama')}" if x.get('rama') and x.get('rama') != m['nombre'] else ''),
                ('transferencia',),
                [{'clase': 'maniobra', 'alimentador': alimentador, 'vecino': vecino, 'casos': [CON_PROYECTO],
                  'tramo': str(x.get('rama') or m['nombre']), 'barra': str(x.get('barra') or ''),
                  'maniobra': str(m['nombre']), 'maniobra_clase': str(m.get('clase') or 'StaSwitch'),
                  'maniobra_ruta': str(m.get('ruta') or ''), 'enlace': str(e.get('enlace')),
                  'enlace_clase': str(e.get('clase') or 'ElmCoup'), 'enlace_ruta': str(e.get('ruta') or ''),
                  'enlace_cerrado': bool(e.get('cerrado'))}],
                {}))
    return out, avisos


def _centro(puntos: Sequence[tuple[float, float, float]]) -> tuple[float, float] | None:
    if not puntos:
        return None
    peso = sum(w for _la, _lo, w in puntos)
    if peso <= 0:
        return (sum(la for la, _lo, _w in puntos) / len(puntos), sum(lo for _la, lo, _w in puntos) / len(puntos))
    return (sum(la * w for la, _lo, w in puntos) / peso, sum(lo * w for _la, lo, w in puntos) / peso)


def area_propuesta(nombre: str, nuevas: Sequence[Mapping[str, Any]], ramas: Sequence[Mapping[str, Any]],
                   gps: Mapping[str, Sequence[float] | None], existentes_kw: float, factor_horizonte: float,
                   anios: int) -> dict[str, Any]:
    """087:RF-38: la zona del alimentador nuevo: su centro de carga, su demanda presente y a horizonte, su contorno y las
    barras que pasarían a él.

    ``nuevas``: las cargas nuevas de la zona (``kw``, ``lat``, ``lon`` o ``barra``); ``ramas``: las que pasan, con sus
    ``barras``; ``gps``: coordenadas por barra. Solo crece la demanda registrada (042:RF-7).
    """
    puntos: list[tuple[float, float, float]] = []
    for c in nuevas:
        g = (c.get('lat'), c.get('lon')) if c.get('lat') is not None else tuple(gps.get(str(c.get('barra'))) or (None, None))
        if g[0] is not None:
            puntos.append((float(g[0]), float(g[1]), float(c.get('kw') or 0.0)))
    barras = sorted({str(b) for r in ramas for b in r.get('barras') or ()})
    contorno = [(float(gps[b][0]), float(gps[b][1])) for b in barras if gps.get(b)]
    contorno += [(la, lo) for la, lo, _w in puntos]
    nuevas_kw = sum(float(c.get('kw') or 0.0) for c in nuevas)
    # El centro de carga pesa la demanda nueva; sin coordenadas de ninguna, el centro del contorno.
    centro = _centro(puntos) if puntos else _centro([(la, lo, 0.0) for la, lo in contorno])
    caja = None
    if contorno:
        las, los = [x[0] for x in contorno], [x[1] for x in contorno]
        caja = {'lat_min': min(las), 'lat_max': max(las), 'lon_min': min(los), 'lon_max': max(los)}
    return {'alimentador': nombre, 'centro': {'lat': centro[0], 'lon': centro[1]} if centro else None, 'contorno': caja,
            'kw_presente': round(existentes_kw + nuevas_kw, 1),
            'kw_horizonte': round(existentes_kw * float(factor_horizonte) + nuevas_kw, 1), 'anios': int(anios),
            'barras': barras, 'cargas_nuevas': [str(c.get('sed') or c.get('barra') or '') for c in nuevas]}
