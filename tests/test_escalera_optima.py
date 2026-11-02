"""Spec 025, T18: variantes, criterio por sorteo, sorteos con semilla, costo y elección."""
from __future__ import annotations

import random

import pytest

from convertersmartgrid import escalera_optima as eo

SEMILLAS = (3, 17, 41, 88)
PERFIL = {
    'escalera': {'cumplimiento': 0.95, 'sorteos': 200, 'semilla': 7, 'tolerancia_pu': 0.005,
                 'tolerancia_carga_pct': 1.0, 'max_variantes': 400},
    'planificacion': {'tasa_regulada': 0.12, 'vida_util_anios': 30},
    'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100},
}
P = eo.parametros(PERFIL)
#: 025:RF-44: el regulador entra por defecto; un perfil puede quitarlo (``escalera.con_regulador``).
P_REG = P
P_SIN_REG = eo.parametros({**PERFIL, 'escalera': {**PERFIL['escalera'], 'con_regulador': False}})


def _troncal(rng, n=None, corriente=None):
    n = n or rng.randint(4, 12)
    i0 = corriente or rng.uniform(150, 400)
    return [{'nombre': f'T{i}', 'largo_m': rng.uniform(100, 900), 'corriente_a': i0 * (1 - i / (n + 1))}
            for i in range(n)]


def _tipos(kv):
    return [{'nombre': f'AAAC_{s}', 'clase': 'TypLne', 'origen': 'proyecto',
             'datos': {'uline': kv, 'sline': s / 1000, 'cohl_': 1}} for s in (150, 300, 450, 700)]


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_variantes_en_el_orden_de_la_escalera_y_combinadas(semilla):
    """025:RF-44, 025:RF-49 — bancos, regulador, terna y sección, en ese orden, varias de cada
    una y sus combinaciones; bancos solo en barras que existen sin la carga."""
    rng = random.Random(semilla)
    kv = rng.choice([10.0, 22.9])
    troncal = _troncal(rng)
    cargas = [{'barra': 'B_EXISTE', 'existe': True, 'indice_troncal': len(troncal) - 1},
              {'barra': 'NODE_T_X', 'existe': False, 'indice_troncal': len(troncal) // 2}]
    vs, avisos = eo.variantes('F1', kv, troncal, cargas, _tipos(kv), P_REG, banco_kvar=450)
    solas = [v for v in vs if len(v.escalones) == 1]
    orden = [v.escalones[0] for v in solas]
    assert orden == sorted(orden, key=eo.ORDEN.index) and set(orden) == set(eo.ORDEN)
    assert sum(e == 'terna' for e in orden) == 2 and sum(e == 'bancos' for e in orden) == 2
    assert any(len(v.escalones) == 2 for v in vs)
    for v in vs:
        for o in v.obras:
            assert o['casos'] == ['Con proyecto'] and o['alimentador'] == 'F1'
            if o['clase'] == 'condensador':
                assert o['barra'] == 'B_EXISTE'


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_regulador_antes_de_la_caida_y_con_la_corriente_del_tramo(semilla):
    """025:RF-60, 025:RF-59 — el regulador va en tramos antes del primero fuera de límites,
    con la unidad de catálogo más chica que lleva su corriente; la consigna es el centro de
    la banda del perfil."""
    rng = random.Random(semilla)
    troncal = _troncal(rng, n=10, corriente=rng.uniform(150, 450))
    fuera = rng.randint(3, 9)
    vs, _ = eo.variantes('F1', 22.9, troncal, [{'barra': 'B', 'existe': True, 'indice_troncal': 9}],
                         [], P_REG, banco_kvar=None, fuera_desde=fuera)
    regs = [o for v in vs if v.escalones == ('regulador',) for o in v.obras]
    assert regs and len(regs) <= 3
    por_nombre = {t['nombre']: (i, t) for i, t in enumerate(troncal)}
    for o in regs:
        i, t = por_nombre[o['tramo']]
        assert i < fuera
        corriente = int(o['tipo']['nombre'].split('_')[-1].rstrip('A'))
        assert corriente >= t['corriente_a'] and o['consigna_pu'] == pytest.approx(1.0)
        assert o['tipo']['proyecto'] == eo.BIBLIOTECA_TIPOS


def test_regulador_sin_corriente_admisible_se_dice():
    """025:RF-60 — si ningún tramo lleva una corriente que admita un regulador, se dice."""
    troncal = [{'nombre': 'T0', 'largo_m': 100, 'corriente_a': 900}]
    vs, avisos = eo.variantes('F1', 22.9, troncal, [], [], P_REG, banco_kvar=None)
    assert not any(v.escalones == ('regulador',) for v in vs)
    assert any('regulador' in a for a in avisos)


def _flujo(u, carga, converge=True):
    return {'converge': converge, 'u': u, 'carga': carga}


def test_cumple_no_empeorar_y_tension_de_las_cargas():
    """025:RF-50 — converge, cada carga nueva entre los límites y nada peor que «Sin proyecto»:
    lo que estaba dentro sigue dentro y lo que estaba fuera no empeora más que la tolerancia."""
    sin = _flujo({'A': 0.97, 'B': 0.90, 'C': 0.92}, {'L1': 80, 'L2': 130})
    bien = _flujo({'A': 0.96, 'B': 0.897, 'C': 0.95, 'N': 0.96}, {'L1': 99, 'L2': 130.5, 'LN': 50})
    assert eo.cumple(sin, bien, ['N'], P) == (True, [])
    for con, pista in ((_flujo({'A': 0.94}, {}), 'sale de los límites'),
                       (_flujo({'B': 0.89}, {}), 'baja más'),
                       (_flujo({'N': 0.93}, {}), 'carga nueva'),
                       (_flujo({}, {'L1': 101}), 'pasa al'),
                       (_flujo({}, {'L2': 135}), 'se carga más'),
                       (_flujo({}, {}, converge=False), 'no converge')):
        ok, motivos = eo.cumple(sin, con, ['N'], P)
        assert not ok and any(pista in m for m in motivos), (pista, motivos)


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_sorteos_de_la_curva_con_semilla(semilla):
    """025:RF-51, 025:RF-58 — instantes de la curva del año comunes a todos los alimentadores,
    cada uno con su potencia entre su máxima; con la misma semilla, los mismos."""
    rng = random.Random(semilla)
    maximas = {'F1': 8000.0, 'F2': 4000.0}
    curva = [(f'2025-01-{d:02d} {h:02d}:00', {'F1': rng.uniform(2000, 8000), 'F2': rng.uniform(1000, 4000)})
             for d in range(1, 29) for h in range(24)]
    curva.append(('2025-02-01 00:00', {'F1': 5000.0}))                    # falta F2: no cuenta
    a = eo.sorteos(curva, maximas, 200, semilla)
    assert a == eo.sorteos(curva, maximas, 200, semilla) and len(a) == 200
    assert all(set(s['factores']) == {'F1', 'F2'} and 0 < s['factores']['F1'] <= 1 for s in a)
    assert a != eo.sorteos(curva, maximas, 200, semilla + 1)
    with pytest.raises(eo.EscaleraError, match='RF-51'):
        eo.sorteos([('t', {'F1': 1.0})], maximas, 10, 1)


COSTOS = {'bancos': {'costo_unitario': 9000, 'unidad': 'Und'},
          'reguladores': {'costo_unitario': 60000, 'unidad': 'Und'},
          'nueva_terna': {'costo_unitario': 40000, 'unidad': 'km'},
          'cambio_seccion': {'costo_unitario': 30, 'unidad': 'm'}}


def test_costo_con_el_capex_y_el_art_14():
    """025:RF-53 — inversión con los costos unitarios del CAPEX (km o m) y costo anual con la
    anualidad del perfil; sin COyM ni precio de pérdidas, lo dice."""
    v = eo.Variante('x', ('terna', 'seccion'), [], {'terna': 2.0, 'seccion': 1.5})
    c = eo.costo(v, COSTOS, P, perdidas_kw=100, factor_perdidas=0.4)
    assert c['inversion'] == pytest.approx(2 * 40000 + 1500 * 30)
    assert c['costo_anual'] == pytest.approx(c['anualidad']) and len(c['avisos']) == 2
    con_todo = eo.parametros({**PERFIL, 'escalera': {**PERFIL['escalera'], 'precio_perdidas_kwh': 0.1,
                                                     'precio_perdidas_kw_mes': 22, 'coym_pct_anual': 2}})
    c2 = eo.costo(v, COSTOS, con_todo, perdidas_kw=100, factor_perdidas=0.4)
    assert c2['costo_anual'] == pytest.approx(c['anualidad'] + 0.02 * c['inversion']
                                              + 100 * 0.4 * 8760 * 0.1 + 100 * 12 * 22)
    assert c2['avisos'] == []


def test_falta_un_dato_se_dice_y_no_se_supone():
    """025:RF-57 — sin la fracción, la tasa o el costo de una alternativa, se dice cuál."""
    with pytest.raises(eo.EscaleraError, match='escalera.cumplimiento.*planificacion.tasa_regulada'):
        eo.parametros({**PERFIL, 'escalera': {**PERFIL['escalera'], 'cumplimiento': None},
                       'planificacion': {'vida_util_anios': 30}})
    with pytest.raises(eo.EscaleraError, match='reguladores'):
        eo.costo(eo.Variante('r', ('regulador',), [], {'regulador': 1}), {}, P,
                 perdidas_kw=None, factor_perdidas=None)


def _evaluada(nombre, maxima, fraccion, costo_anual):
    return {'nombre': nombre, 'maxima': maxima, 'fraccion': fraccion,
            'costo': {'costo_anual': costo_anual}, 'motivos': [] if maxima else ['no converge']}


def test_elige_la_de_menor_costo_entre_las_que_cumplen():
    """025:RF-53, 025:RF-55, 025:RF-52b — gana la más barata de las que cumplen con la máxima y
    en el 95 % de los sorteos; cada otra dice por qué no."""
    r = eo.elegir([_evaluada('cara', True, 1.0, 900), _evaluada('barata', True, 0.97, 300),
                   _evaluada('poca', True, 0.80, 100), _evaluada('mala', False, None, 50)], P)
    assert r['elegida'] == 'barata' and r['mas_cercana'] is None
    motivos = {t['nombre']: t['motivo'] for t in r['tabla']}
    assert 'cuesta más' in motivos['cara'] and '80 %' in motivos['poca']
    assert 'no cumple con la máxima' in motivos['mala'] and motivos['barata'] == ''


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_primero_bancos_luego_seccion_luego_terna(semilla):
    """063:RF-21, 063:RF-22 — INKA en SM218 (2026-11-01): 128 m de conductor salen más baratos que
    los bancos, pero si los bancos ya dejan la red en norma, se quedan los bancos; solo se sube de
    escalón si el anterior no cumple, y dentro del escalón gana la más barata."""
    rng = random.Random(semilla)
    assert eo.ORDEN[:3] == ('bancos', 'seccion', 'terna')
    for _ in range(50):
        precio = {e: rng.uniform(10, 1000) for e in ('b1', 'b2', 't', 'bs')}
        bancos = [dict(_evaluada('b1', True, 1.0, precio['b1']), escalones=('bancos',)),
                  dict(_evaluada('b2', True, 1.0, precio['b2']), escalones=('bancos',))]
        seccion = dict(_evaluada('s', True, 1.0, min(precio.values()) / 2), escalones=('seccion',))
        terna = dict(_evaluada('t', True, 1.0, precio['t']), escalones=('terna',))
        mixta = dict(_evaluada('bs', True, 1.0, precio['bs']), escalones=('bancos', 'seccion'))
        r = eo.elegir(bancos + [seccion, terna, mixta], P)
        assert r['elegida'] == min(('b1', 'b2'), key=precio.get), semilla
        motivos = {t['nombre']: t['motivo'] for t in r['tabla']}
        assert 'no hace falta' in motivos['s'] and 'no hace falta' in motivos['t']
        sin_bancos = [dict(b, maxima=False, motivos=['0,93 p.u.']) for b in bancos]
        r = eo.elegir(sin_bancos + [seccion, terna, mixta], P)
        assert r['elegida'] == 's', semilla              # la sección sola es la más barata del escalón
    assert eo.rango(()) < eo.rango(('bancos',)) < eo.rango(('seccion',)) < eo.rango(('terna',))
    assert eo.rango(('bancos', 'terna')) == eo.rango(('terna',))


def test_ninguna_cumple_dice_la_mas_cercana():
    """025:RF-56 — si ninguna cumple (ni con la máxima, 063:RF-33), no se elige ninguna y se dice
    la que más se acerca."""
    r = eo.elegir([_evaluada('a', False, 0.5, 1), _evaluada('b', False, 0.9, 2),
                   _evaluada('c', False, None, 0)], P)
    assert r['elegida'] is None and r['mas_cercana'] == 'b'


def test_precios_de_perdidas_a_la_moneda_de_trabajo():
    """025:RF-67, 025:RF-68 — los precios de pérdidas, publicados en soles, pasan a dólares con
    el tipo de cambio que da el operador, no el perfil; sin él, se dice que falta."""
    esc = {**PERFIL['escalera'], 'moneda': 'USD', 'moneda_precios_perdidas': 'PEN',
           'precio_perdidas_kwh': 0.1443, 'precio_perdidas_kw_mes': 22.06,
           'tipo_cambio_precios_perdidas': 9.99}                       # del perfil: no cuenta
    p = eo.parametros({**PERFIL, 'escalera': esc}, tipo_cambio=3.495)
    assert p.moneda == 'USD' and p.precio_perdidas_kwh == pytest.approx(0.1443 / 3.495)
    assert p.precio_perdidas_kw_mes == pytest.approx(22.06 / 3.495)
    for tc in (None, 0):
        with pytest.raises(eo.EscaleraError, match='tipo de cambio.*RF-68'):
            eo.parametros({**PERFIL, 'escalera': esc}, tipo_cambio=tc)


def test_costos_que_el_libro_no_tiene_vienen_del_perfil_y_sin_ellos_no_se_elige():
    """025:RF-53, 025:RF-56, 025:RF-57 — bancos y reguladores sin costo en el CAPEX: los da el
    perfil si los tiene; sin ninguno, la variante que cumple no se elige y dice por qué."""
    p = eo.parametros({**PERFIL, 'escalera': {**PERFIL['escalera'], 'escala_capex': 1,
                                               'costos_unitarios': {'bancos': 9000, 'reguladores': None}}})
    costos = eo.costos_de_alternativas({'nueva_terna': {'costo_unitario': 40000, 'unidad': 'km'}}, p)
    assert costos['bancos']['costo_unitario'] == 9000 and costos['bancos']['origen'] == 'perfil'
    assert 'reguladores' not in costos and costos['nueva_terna']['costo_unitario'] == 40000
    r = eo.elegir([{'nombre': 'reg', 'maxima': True, 'fraccion': 1.0, 'costo': None,
                    'sin_costo': 'el libro CAPEX no tiene costo de «reguladores»'},
                   {'nombre': 'terna', 'maxima': True, 'fraccion': 0.99, 'costo': {'costo_anual': 5.0}}], p)
    assert r['elegida'] == 'terna'
    assert 'sin costo' in next(t['motivo'] for t in r['tabla'] if t['nombre'] == 'reg')


def test_el_libro_capex_pasa_a_la_moneda_de_trabajo_con_su_escala():
    """025:RF-77 — un libro en miles (kUSD) se multiplica por la escala del perfil; los costos del
    perfil no se tocan; sin escala, con costos en el libro, se dice y no se costea."""
    libro = {'nueva_terna': {'costo_unitario': 60.9, 'unidad': 'KM'}}
    p = eo.parametros({**PERFIL, 'escalera': {**PERFIL['escalera'], 'escala_capex': 1000,
                                               'costos_unitarios': {'bancos': 8000}}})
    costos = eo.costos_de_alternativas(libro, p)
    assert costos['nueva_terna']['costo_unitario'] == pytest.approx(60900)
    assert costos['bancos']['costo_unitario'] == 8000
    sin = eo.parametros({**PERFIL, 'escalera': {k: v for k, v in PERFIL['escalera'].items() if k != 'escala_capex'}})
    with pytest.raises(eo.EscaleraError, match='escala_capex'):
        eo.costos_de_alternativas(libro, sin)
    assert eo.costos_de_alternativas({}, sin) == {}


def test_sin_regulador_salvo_que_el_perfil_lo_pida():
    """063:RF-26 (aclaración), 025:RF-44 — por defecto el regulador entra, al final del orden; un
    perfil con ``escalera.con_regulador: false`` lo quita."""
    rng = random.Random(SEMILLAS[0])
    troncal = _troncal(rng, n=10, corriente=300.0)
    carga = [{'barra': 'B', 'existe': True, 'indice_troncal': 9}]
    sin, _ = eo.variantes('F1', 22.9, troncal, carga, _tipos(22.9), P_SIN_REG, banco_kvar=450, fuera_desde=4)
    con, _ = eo.variantes('F1', 22.9, troncal, carga, _tipos(22.9), P, banco_kvar=450, fuera_desde=4)
    assert not any('regulador' in v.escalones for v in sin)
    assert any('regulador' in v.escalones for v in con)
    assert any(v.escalones == ('bancos',) for v in sin)


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_la_seccion_sube_de_una_en_una(semilla):
    """063:RF-27 — SM218 (2026-11-01): el cambio de sección no salta a la mayor; las variantes de
    sección van de la menor apta a la mayor, todas, y si cumplen varias se queda la menor."""
    rng = random.Random(semilla)
    kv = rng.choice([10.0, 22.9])
    troncal = _troncal(rng)
    carga = [{'barra': 'B', 'existe': True, 'indice_troncal': len(troncal) - 1}]
    tipos = _tipos(kv)
    vs, _ = eo.variantes('F1', kv, troncal, carga, tipos, P, banco_kvar=None)
    secciones = [v for v in vs if v.escalones == ('seccion',)]
    nombres = [v.obras[0]['tipo']['nombre'] for v in secciones]
    aptos = [t['nombre'] for t in eo._conductores(tipos, kv, max(float(t['corriente_a']) for t in troncal))]
    assert nombres == aptos and len(nombres) == len(set(nombres)), semilla
    evaluadas = [{'nombre': v.nombre, 'maxima': True, 'fraccion': 1.0, 'escalones': v.escalones,
                  'costo': {'costo_anual': 100.0 * (i + 1)}, 'motivos': []} for i, v in enumerate(secciones)]
    if evaluadas:
        assert eo.elegir(evaluadas, P)['elegida'] == secciones[0].nombre


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_la_seccion_solo_cambia_los_tramos_mas_delgados(semilla):
    """063:RF-30 — SM218 (2026-11-01): «sección CU 50 mm²» reemplazaba los 10,32 km y bajaba casi
    toda la troncal; ahora cada conductor solo cambia los tramos de menor corriente nominal, y
    no se propone si no mejora ninguno."""
    rng = random.Random(semilla)
    kv = 22.9
    troncal = _troncal(rng)
    tipos = _tipos(kv)
    aptos = eo._conductores(tipos, kv, max(float(t['corriente_a']) for t in troncal))
    if not aptos:
        pytest.skip('sin conductor apto en el sorteo')
    inoms = sorted({float(t['datos']['sline']) * 1000 for t in aptos})
    for t in troncal:
        t['inom_a'] = rng.choice([inoms[0] / 2, inoms[-1] * 2])         # delgado o más grueso que todos
    carga = [{'barra': 'B', 'existe': True, 'indice_troncal': len(troncal) - 1}]
    vs, _ = eo.variantes('F1', kv, troncal, carga, tipos, P, banco_kvar=None)
    delgados = {t['nombre'] for t in troncal if t['inom_a'] < inoms[0]}
    for v in (v for v in vs if v.escalones == ('seccion',)):
        assert set(v.obras[0]['tramos']) == delgados, semilla
    if not delgados:
        assert not any(v.escalones == ('seccion',) for v in vs)


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_obras_sobre_el_camino_electrico_de_la_carga(semilla):
    """063:RF-32 — INKA en SM218 (2026-11-01) colgaba de un ramal a 17 km, no de la troncal más
    larga: el camino se busca por la red, y sección y terna van sobre él; la sección solo cambia
    sus tramos más delgados y que pueda llevar."""
    rng = random.Random(semilla)
    n = rng.randint(6, 40)
    red = [{'nombre': f'L{i}', 'desde': f'B{rng.randrange(i)}' if i else 'CAB', 'hasta': f'B{i}',
            'largo_m': rng.uniform(10, 900), 'corriente_a': rng.uniform(5, 80),
            'inom_a': rng.choice([106.0, 140.0, 340.0])} for i in range(n)]
    destino = f'B{n - 1}'
    camino = eo.camino_electrico(red, 'CAB', destino)
    assert camino and camino[0]['desde'] == 'CAB' and camino[-1]['hasta'] == destino, semilla
    assert all(a['hasta'] == b['desde'] for a, b in zip(camino, camino[1:])), semilla
    assert eo.camino_electrico(red, 'CAB', 'NO_EXISTE') == []
    carga = [{'barra': destino, 'existe': True, 'indice_troncal': None, 'camino': camino}]
    vs, _ = eo.variantes('F1', 22.9, [], carga, _tipos(22.9), P, banco_kvar=450)
    nombres_camino = {t['nombre'] for t in camino}
    for v in vs:
        for o in v.obras:
            if o['clase'] in ('terna', 'seccion'):
                assert set(o['tramos']) <= nombres_camino, semilla
            if o['clase'] == 'seccion':
                nueva = next(float(t['datos']['sline']) * 1000 for t in _tipos(22.9)
                             if t['nombre'] == o['tipo']['nombre'])
                assert all(next(t for t in camino if t['nombre'] == n_)['inom_a'] < nueva for n_ in o['tramos'])
    assert any(o['clase'] == 'terna' for v in vs for o in v.obras), semilla


def test_con_solucion_en_la_maxima_no_se_pasa_a_otras_obras():
    """063:RF-33 — SM218 (2026-11-01): banco + AA 120 mm² cumplía con la máxima y los sorteos daban
    94,5 %; se elige la primera por prioridad, se avisa, y no se sigue a la terna ni a la SET nueva."""
    tabla = [dict(_evaluada('banco+seccion', True, 0.945, 500.0), escalones=('bancos', 'seccion')),
             dict(_evaluada('terna', True, 0.945, 300.0), escalones=('terna',)),
             dict(_evaluada('banco', False, None, 50.0), escalones=('bancos',))]
    r = eo.elegir(tabla, P)
    assert r['elegida'] == 'banco+seccion' and r['sin_confirmar_sorteos'] is True
    assert '063:RF-33' in next(t['motivo'] for t in r['tabla'] if t['nombre'] == 'banco+seccion')
    sin_maxima = eo.elegir([_evaluada('a', False, None, 10.0)], P)
    assert sin_maxima['elegida'] is None and 'sin_confirmar_sorteos' not in sin_maxima


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_cada_obra_dice_su_nodo_de_mt_o_sus_nodos_de_inicio_y_fin(semilla):
    """063:RF-31 — el banco dice el nodo de MT donde va; la sección y la terna, cada tramo con su
    nodo de inicio y su nodo final, y la obra entera desde el primero hasta el último, en orden
    de la cabecera a la carga (SM218, 2026-11-01: el informe no decía dónde iba cada obra)."""
    rng = random.Random(semilla)
    n = rng.randint(4, 30)
    red = [{'nombre': f'L{i}', 'desde': f'B{i - 1}' if i else 'CAB', 'hasta': f'B{i}',
            'largo_m': rng.uniform(10, 900), 'corriente_a': rng.uniform(5, 60),
            'inom_a': rng.choice([106.0, 140.0])} for i in range(n)]
    destino = f'B{n - 1}'
    camino = eo.camino_electrico(red, 'CAB', destino)
    carga = [{'barra': destino, 'existe': True, 'indice_troncal': None, 'camino': camino,
              'banco_en': f'B{n - 2}' if n > 1 else 'CAB'}]
    vs, _ = eo.variantes('F1', 22.9, [], carga, _tipos(22.9), P, banco_kvar=450)
    vistas = set()
    for v in vs:
        for o in v.obras:
            texto = eo.ubicacion(o)
            vistas.add(o['clase'])
            if o['clase'] == 'condensador':
                assert f"nodo de MT {o['barra']}" in texto, semilla
            elif o['clase'] in ('seccion', 'terna'):
                nodos = o['nodos']
                assert [x['tramo'] for x in nodos] == o['tramos'], semilla
                assert all(x['desde'] and x['hasta'] for x in nodos), semilla
                assert f"desde el nodo {nodos[0]['desde']} hasta el nodo {nodos[-1]['hasta']}" in texto
                assert nodos[-1]['hasta'] == destino or o['clase'] == 'seccion', semilla
    assert {'terna'} <= vistas, semilla
