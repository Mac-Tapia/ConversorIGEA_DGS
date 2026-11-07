"""Spec 025, T18: variantes, criterio por sorteo, sorteos con semilla, costo y elección."""
from __future__ import annotations

import random

import pytest

from convertersmartgrid import escalera_optima as eo

SEMILLAS = (3, 17, 41, 88)
PERFIL = {
    'escalera': {'cumplimiento': 0.95, 'sorteos': 200, 'semilla': 7, 'tolerancia_pu': 0.005,
                 'tolerancia_carga_pct': 1.0, 'max_variantes': 400,
                 'regulador_min_km': 0},     # estas redes sorteadas son cortas; 042:RF-49 tiene sus pruebas
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
    solas = [v for v in vs if len(v.escalones) == 1 and not v.caminos]       # 098:RF-31: las de varios caminos, aparte
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
    # 042:RF-54; 087:RF-37: y el km de alimentador nuevo, deducido del cambio de tensión, por confirmar.
    # 098:RF-35: y la sección y la terna, del km del cambio de nivel, por confirmar.
    assert set(eo.costos_de_alternativas({}, sin)) == set(eo.COSTOS_NIVEL_DE_REFERENCIA) | {'nuevo_alimentador', 'cambio_seccion',
                                                                                           'nueva_terna'}


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
    aptos = [t['nombre'] for t in eo.conductores_aptos(tipos, kv, max(float(t['corriente_a']) for t in troncal))]
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
    aptos = eo.conductores_aptos(tipos, kv, max(float(t['corriente_a']) for t in troncal))
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
    assert r['elegida'] == 'terna' and r['sin_confirmar_sorteos'] is True      # 042:RF-56: la de menor costo
    assert '063:RF-33' in next(t['motivo'] for t in r['tabla'] if t['nombre'] == 'terna')
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


def test_solo_secciones_normalizadas_y_una_por_codigo():
    """042:RF-27 — Pisco: se probaban AA095, AA150 y CU070, cada uno dos veces; ahora solo los normalizados, el de ficha."""
    from convertersmartgrid.escalera_optima import normalizados

    tipos = [{'nombre': n, 'datos': {'uline': 22.9}} for n in
             ('AA09503D_22_9kV', 'AA12003D_22_9kV', 'AA12003D_22_9kV_FICHA', 'CU07003D_22_9kV', 'AA05003D_22_9kV')]
    nombres = sorted(t['nombre'] for t in normalizados(tipos, ('AA05003D', 'AA12003D', 'AA24003D', 'N212003D')))
    assert nombres == ['AA05003D_22_9kV', 'AA12003D_22_9kV_FICHA']
    assert len(normalizados(tipos, ())) == 5


def test_el_planeamiento_limita_al_80_por_ciento():
    """042:RF-28 — con `cargabilidad_planeamiento_pct` el límite de la escalera es el 80 %, no el de los estudios."""
    from convertersmartgrid import escalera_optima as eo

    perfil = {'escalera': {'cumplimiento': 0.95, 'sorteos': 10, 'tolerancia_pu': 0.005, 'tolerancia_carga_pct': 1.0,
                           'cargabilidad_planeamiento_pct': 80, 'secciones_normalizadas': ['AA12003D']},
              'planificacion': {'tasa_regulada': 0.12, 'vida_util_anios': 30},
              'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}}
    p = eo.parametros(perfil)
    assert p.cargabilidad_max_pct == 80 and p.secciones == ('AA12003D',)
    ok, motivos = eo.cumple({'converge': True, 'u': {}, 'carga': {'L1': 50.0}},
                            {'converge': True, 'u': {}, 'carga': {'L1': 85.0}}, [], p)
    assert not ok and 'L1' in motivos[0]


def test_el_240_sale_de_su_ficha_y_va_en_doble_terna():
    """042:RF-30 — Pisco: sin tipo AL 240 en la red nunca se probó; ahora se crea de su ficha y la escalera
    propone «sección + terna» solo en el mismo camino, antes que las demás combinaciones."""
    from convertersmartgrid import escalera_optima as eo
    from convertersmartgrid.catalog import filas_de_conductores, tipo_de_ficha

    t = tipo_de_ficha('AA24003D', 22.9, filas_de_conductores())
    assert t['nombre'] == 'AA24003D_22_9kV_FICHA' and t['datos']['cohl_'] == 1
    assert 0.13 < t['datos']['rline'] < 0.15 and 500 < t['datos']['sline'] * 1000 < 600
    assert tipo_de_ficha('N212003D', 10, filas_de_conductores())['datos']['cohl_'] == 0

    troncal = [{'nombre': f'L{i}', 'largo_m': 1000.0, 'corriente_a': 300.0, 'inom_a': 340.0} for i in range(3)]
    cargas = [{'barra': 'B2', 'existe': False, 'indice_troncal': 2}, {'barra': 'B1', 'existe': False, 'indice_troncal': 1}]
    tipo = {'nombre': t['nombre'], 'clase': 'TypLne', 'datos': t['datos'], 'origen': 'otro', 'proyecto': eo.BIBLIOTECA_TIPOS}
    perfil = {'escalera': {'cumplimiento': 0.95, 'sorteos': 10, 'tolerancia_pu': 0.005, 'tolerancia_carga_pct': 1.0,
                           'max_variantes': 40, 'secciones_normalizadas': ['AA24003D']},
              'planificacion': {'tasa_regulada': 0.12, 'vida_util_anios': 30},
              'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}}
    vs, _av = eo.variantes('F', 22.9, troncal, cargas, [tipo], eo.parametros(perfil), banco_kvar=None)
    dobles = [v for v in vs if set(v.escalones) == {'seccion', 'terna'} and not v.caminos]   # 098:RF-31: aparte
    assert dobles
    for v in dobles:
        sec = next(o for o in v.obras if o['clase'] == 'seccion')
        ter = next(o for o in v.obras if o['clase'] == 'terna')
        assert set(sec['tramos']) <= set(ter['tramos'])
    solas = [v for v in vs if len(v.escalones) == 1 and not v.caminos]
    assert vs.index(dobles[0]) == len(solas), 'la doble terna va primero entre las combinaciones'


def test_en_linea_larga_el_regulador_no_queda_fuera_del_tope():
    """042:RF-35 — con el camino largo, sección + terna + regulador entran antes del tope; con el corto, no se añaden."""
    from convertersmartgrid import escalera_optima as eo
    from convertersmartgrid.catalog import filas_de_conductores, tipo_de_ficha

    t = tipo_de_ficha('AA24003D', 22.9, filas_de_conductores())
    tipo = {'nombre': t['nombre'], 'clase': 'TypLne', 'datos': t['datos'], 'origen': 'otro', 'proyecto': eo.BIBLIOTECA_TIPOS}
    perfil = {'escalera': {'cumplimiento': 0.95, 'sorteos': 10, 'tolerancia_pu': 0.005, 'tolerancia_carga_pct': 1.0,
                           'max_variantes': 12, 'consigna_regulador_pu': 1.0, 'secciones_normalizadas': ['AA24003D']},
              'planificacion': {'tasa_regulada': 0.12, 'vida_util_anios': 30},
              'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}}

    def de(largo_m):
        troncal = [{'nombre': f'L{i}', 'largo_m': largo_m, 'corriente_a': 100.0, 'inom_a': 340.0} for i in range(6)]
        return eo.variantes('F', 22.9, troncal, [{'barra': 'B', 'existe': False, 'indice_troncal': 5}], [tipo],
                            eo.parametros(perfil), banco_kvar=None)

    largas, avisos = de(4000.0)
    triple = [v for v in largas if {'seccion', 'terna', 'regulador'} == set(v.escalones)]
    assert triple and any('042:RF-35' in a for a in avisos)
    cortas, avisos_c = de(100.0)
    assert not [v for v in cortas if len(v.escalones) == 3] and not any('042:RF-35' in a for a in avisos_c)


def test_en_linea_larga_los_bancos_tambien_a_dos_tercios():
    """042:RF-37 — la barra existente a 2/3 del camino, nunca la que crea una carga nueva; en línea corta, no."""
    from convertersmartgrid import escalera_optima as eo

    tramos = [{'nombre': f'L{i}', 'largo_m': 3000.0, 'hasta': f'B{i}'} for i in range(5)]
    assert eo.nodo_a_dos_tercios(tramos) == 'B2'
    tramos[2]['hasta'] = 'NODE_T_CARGA'
    assert eo.nodo_a_dos_tercios(tramos) in ('B1', 'B3')
    perfil = {'escalera': {'cumplimiento': 0.95, 'sorteos': 10, 'tolerancia_pu': 0.005, 'tolerancia_carga_pct': 1.0,
                           'max_variantes': 40, 'modulos_max': 2},
              'planificacion': {'tasa_regulada': 0.12, 'vida_util_anios': 30},
              'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}}
    cargas = [{'barra': 'NODE_T_X', 'existe': False, 'camino': tramos}]
    vs, _a = eo.variantes('F', 22.9, tramos, cargas, [], eo.parametros(perfil), banco_kvar=450.0)
    assert [v for v in vs if '2/3' in v.nombre]
    cortos = [{**t, 'largo_m': 100.0} for t in tramos]
    vs, _a = eo.variantes('F', 22.9, cortos, [{**cargas[0], 'camino': cortos}], [], eo.parametros(perfil), banco_kvar=450.0)
    assert not [v for v in vs if '2/3' in v.nombre]


def test_las_obras_se_integran_de_tres_y_de_cuatro_sin_repetir():
    """042:RF-38 — bancos + sección + terna + regulador juntos, sección y terna en el mismo camino, ninguna repetida."""
    from convertersmartgrid import escalera_optima as eo
    from convertersmartgrid.catalog import filas_de_conductores, tipo_de_ficha

    t = tipo_de_ficha('AA24003D', 22.9, filas_de_conductores())
    tipo = {'nombre': t['nombre'], 'clase': 'TypLne', 'datos': t['datos'], 'origen': 'otro', 'proyecto': eo.BIBLIOTECA_TIPOS}
    perfil = {'escalera': {'cumplimiento': 0.95, 'sorteos': 10, 'tolerancia_pu': 0.005, 'tolerancia_carga_pct': 1.0,
                           'max_variantes': 500, 'modulos_max': 2, 'secciones_normalizadas': ['AA24003D']},
              'planificacion': {'tasa_regulada': 0.12, 'vida_util_anios': 30},
              'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}}
    troncal = [{'nombre': f'L{i}', 'largo_m': 4000.0, 'corriente_a': 100.0, 'inom_a': 340.0} for i in range(6)]
    cargas = [{'barra': 'B5', 'existe': True, 'indice_troncal': 5}, {'barra': 'B2', 'existe': True, 'indice_troncal': 2}]
    vs, _a = eo.variantes('F', 22.9, troncal, cargas, [tipo], eo.parametros(perfil), banco_kvar=450.0)
    assert len({v.nombre for v in vs}) == len(vs)
    assert [v for v in vs if set(v.escalones) == set(eo.ORDEN)]
    for v in (x for x in vs if not x.caminos):     # 098:RF-31: las de varios caminos juntan obras de caminos distintos
        sec = [o for o in v.obras if o['clase'] == 'seccion']
        ter = [o for o in v.obras if o['clase'] == 'terna']
        if sec and ter:
            assert set(sec[0]['tramos']) <= set(ter[0]['tramos'])


def test_otra_empresa_sin_perfil_y_otra_tension_tiene_todas_las_obras():
    """042:RF-39, 042:RF-40 — sin perfil y a 13,8 kV: bancos, sección, terna y regulador; lo supuesto se dice y lo propio no se pisa."""
    from convertersmartgrid import escalera_optima as eo
    from convertersmartgrid import set_nueva as sn
    from convertersmartgrid.catalog import filas_de_conductores, tipo_de_ficha
    from convertersmartgrid.perfil_empresa import (BANCOS_KVAR_DE_REFERENCIA, SECCIONES_DE_REFERENCIA,
                                                   completar_planeamiento)

    perfil, avisos = completar_planeamiento({})
    assert avisos and '042:RF-39' in avisos[0]
    p = eo.parametros(perfil)
    assert p.tension_min_pu == 0.95 and sn.parametros(perfil).anios == 5
    assert completar_planeamiento({'estudios': {'tension_min_pu': 0.9}})[0]['estudios']['tension_min_pu'] == 0.9
    filas = filas_de_conductores()
    tipos = []
    for c in SECCIONES_DE_REFERENCIA:
        t = tipo_de_ficha(c, 13.8, filas)
        assert t['datos']['uline'] == 13.8
        tipos.append({'nombre': t['nombre'], 'clase': 'TypLne', 'datos': t['datos'], 'origen': 'proyecto', 'proyecto': ''})
    banco = min(BANCOS_KVAR_DE_REFERENCIA.items(), key=lambda par: abs(par[0] - 13.8))[1]
    troncal = [{'nombre': f'L{i}', 'largo_m': 4000.0, 'corriente_a': 60.0, 'inom_a': 100.0} for i in range(6)]
    vs, _a = eo.variantes('F', 13.8, troncal, [{'barra': 'B', 'existe': True, 'indice_troncal': 5}], tipos, p, banco_kvar=banco)
    assert {e for v in vs for e in v.escalones} == set(eo.ORDEN)


def test_sin_medicion_las_obras_se_evaluan_en_la_maxima():
    """042:RF-42 — sin ningún instante con todos medidos no hay error: un solo punto, la máxima, y se dice."""
    from convertersmartgrid import escalera_optima as eo

    lista, avisos = eo.sorteos_o_maxima([], {'F1': 100.0}, 200, 1)
    assert lista == [{'instante': 'máxima', 'factores': {}}] and '042:RF-42' in avisos[0]
    lista, avisos = eo.sorteos_o_maxima([('t', {'F1': 50.0})], {'F1': 100.0}, 3, 1)
    assert len(lista) == 3 and lista[0]['factores'] == {'F1': 0.5} and not avisos


def test_cada_variante_refuerza_los_tramos_sobrecargados_de_cualquier_ramal():
    """042:RF-43 — un ramal al 141 %: un refuerzo solo y cada variante con él; sin repetir lo que ya hace la variante."""
    import math

    from convertersmartgrid import escalera_optima as eo
    from convertersmartgrid.perfil_empresa import completar_planeamiento

    perfil = completar_planeamiento({'escalera': {'cargabilidad_planeamiento_pct': 80, 'max_variantes': 500}})[0]
    troncal = [{'nombre': f'L{i}', 'largo_m': 1000.0, 'corriente_a': 50.0, 'inom_a': 340.0} for i in range(3)]
    ramal = {'nombre': 'R1', 'largo_m': 500.0, 'carga_pct': 141.0, 'nlnum': 1, 'inom_a': 100.0, 'desde': 'A', 'hasta': 'B'}
    cargas = [{'barra': 'B2', 'existe': True, 'indice_troncal': 2}]
    vs, avisos = eo.variantes('F', 22.9, troncal, cargas, [], eo.parametros(perfil), banco_kvar=450.0, sobrecargados=[ramal])
    assert any('042:RF-43' in a for a in avisos)
    assert vs[0].nombre.startswith('refuerzo de 1 tramos') and vs[0].cantidades['terna'] == 0.5
    for v in vs:
        ternas = [o for o in v.obras if o['clase'] == 'terna' and 'R1' in o['tramos']]
        assert len(ternas) == 1, v.nombre
    # Al 200 % con un límite de 80 % hacen falta 2 ternas más; si la variante ya pone una, solo falta otra.
    doble = {**ramal, 'carga_pct': 200.0}
    p = eo.parametros(perfil)
    assert math.ceil(200.0 / 80.0) - 1 == 2
    assert eo._ternas_que_faltan(doble, eo.Variante('', (), [], {}), {}, p.cargabilidad_max_pct) == 2
    con_terna = eo.Variante('t', ('terna',), [{'clase': 'terna', 'tramos': ['R1']}], {})
    assert eo._ternas_que_faltan(doble, con_terna, {}, p.cargabilidad_max_pct) == 1
    # Un conductor nuevo cinco veces mayor ya lo resuelve: no se añade terna.
    con_seccion = eo.Variante('s', ('seccion',), [{'clase': 'seccion', 'tramos': ['R1'], 'tipo': {'nombre': 'G'}}], {})
    assert eo._ternas_que_faltan(doble, con_seccion, {'G': 500.0}, p.cargabilidad_max_pct) == 0
    # Sin sobrecargas las variantes no cambian.
    limpias, _a = eo.variantes('F', 22.9, troncal, cargas, [], eo.parametros(perfil), banco_kvar=450.0)
    assert not [v for v in limpias if 'refuerzo' in v.nombre]


def test_el_camino_pasa_por_los_acopladores_y_solo_las_lineas_llevan_obra():
    """042:RF-44 — Pisco: el camino se cortaba en cada maniobra; con ella pasa, y el acoplador no se refuerza."""
    red = [{'nombre': 'L1', 'desde': 'CAB', 'hasta': 'A', 'largo_m': 100.0},
           {'nombre': 'SW', 'desde': 'A', 'hasta': 'B', 'largo_m': 0.0, 'puente': True},
           {'nombre': 'L2', 'desde': 'B', 'hasta': 'C', 'largo_m': 200.0}]
    assert eo.camino_electrico(red[:1] + red[2:], 'CAB', 'C') == []
    camino = eo.camino_electrico(red, 'CAB', 'C')
    assert [t['nombre'] for t in camino] == ['L1', 'SW', 'L2']
    assert [t['nombre'] for t in eo.solo_lineas(camino)] == ['L1', 'L2']


def _camino_que_cae():
    tensiones = [0.99, 0.98, 0.97, 0.96, 0.94, 0.92]
    barras = ['CAB'] + [f'B{i}' for i in range(len(tensiones))]
    return [{'nombre': f'L{i}', 'desde': barras[i], 'hasta': barras[i + 1], 'largo_m': 2000.0, 'corriente_a': 100.0 - 5 * i,
             'u': {barras[i + 1]: u}} for i, u in enumerate(tensiones)]


def test_el_regulador_va_donde_cae_la_tension():
    """042:RF-47 — en el primer tramo fuera del límite y a mitad de la caída; sin caída, en ninguno; nunca el de la cabecera."""
    camino = _camino_que_cae()
    assert eo.puntos_de_regulador(camino, 0.95) == [3, 4]
    assert eo.puntos_de_regulador(camino, 0.90) == []
    assert eo.puntos_de_regulador(camino, 0.995) == [1]


def test_la_unidad_lleva_la_corriente_bajo_el_limite_de_planeamiento():
    """042:RF-47 — 85 A al 80 % piden 106 A: la unidad de 150 A; las variantes van sobre el camino de la carga."""
    from convertersmartgrid.perfil_empresa import completar_planeamiento

    perfil = completar_planeamiento({'escalera': {'cargabilidad_planeamiento_pct': 80, 'max_variantes': 500, 'regulador_min_km': 0}})[0]
    p = eo.parametros(perfil)
    camino = _camino_que_cae()
    vs, _a = eo.variantes('F', 22.9, [], [{'barra': 'B5', 'existe': False, 'camino': camino}], [], p, banco_kvar=None)
    solas = [v for v in vs if v.escalones == ('regulador',)]
    assert {v.obras[0]['tramo'] for v in solas} == {'L3', 'L4'}
    en_l3 = next(v for v in solas if v.obras[0]['tramo'] == 'L3')
    assert en_l3.nombre == 'regulador 150 A en L3' and en_l3.obras[0]['tipo']['proyecto'] == eo.BIBLIOTECA_TIPOS


def _tramos_de(km_total, n=4):
    return [{'nombre': f'T{i}', 'largo_m': km_total * 1000 / n, 'corriente_a': 100.0, 'desde': f'B{i}', 'hasta': f'B{i + 1}',
             'tipo': 'X', 'inom_a': 300.0} for i in range(n)]


@pytest.mark.parametrize('km,hay', [(9.0, False), (15.0, False), (15.5, True)])
def test_el_regulador_solo_pasa_de_15_km(km, hay):
    """042:RF-49 — el regulador es un caso extremo: en 15 km justos todavía no se plantea, y queda dicho."""
    esc = {k: v for k, v in PERFIL['escalera'].items() if k != 'regulador_min_km'}
    p = eo.parametros({**PERFIL, 'escalera': esc})
    vs, avisos = eo.variantes('F1', 22.9, _tramos_de(km), [], [], p, banco_kvar=None, fuera_desde=1)
    assert any('regulador' in v.escalones for v in vs) is hay
    assert any('042:RF-49' in a for a in avisos) is not hay


def test_el_largo_del_regulador_lo_da_el_perfil():
    """042:RF-49 — otra empresa puede poner su propio largo."""
    p = eo.parametros({**PERFIL, 'escalera': {**PERFIL['escalera'], 'regulador_min_km': 5}})
    vs, _ = eo.variantes('F1', 22.9, _tramos_de(9.0), [], [], p, banco_kvar=None, fuera_desde=1)
    assert any('regulador' in v.escalones for v in vs)


NIVEL = {'salida': 'B_22', 'nodo': 'N1', 'km': 12.0, 'seds': 40, 'compartida': True}


def test_a_10_kv_el_paso_a_22_9_va_tras_los_bancos_y_antes_de_la_seccion():
    """042:RF-50, 042:RF-51 — con celda nueva en la barra de la SET; va solo y sin refuerzo."""
    vs, _ = eo.variantes('F1', 10.0, _tramos_de(5.0), [{'barra': 'B4', 'existe': True}], [], P, banco_kvar=300.0, nivel=NIVEL,
                         sobrecargados=[{'nombre': 'T1', 'largo_m': 10.0, 'corriente_a': 300.0, 'tipo': 'X', 'nlnum': 1, 'carga_pct': 120.0}])
    i = next(n for n, v in enumerate(vs) if 'nivel' in v.escalones)
    assert len([v for v in vs if 'nivel' in v.escalones]) == 1 and vs[i].escalones == ('nivel',)
    obra = vs[i].obras[0]
    assert (obra['clase'], obra['nodo'], obra['salida'], obra['kv_destino']) == ('migracion', 'N1', 'B_22', 22.9)
    assert len(vs[i].obras) == 1
    assert all('bancos' in v.escalones or 'seccion' not in v.escalones or n > i for n, v in enumerate(vs) if n)
    assert eo.rango(('bancos',)) < eo.rango(('nivel',)) < eo.rango(('seccion',)) < eo.rango(('regulador',))


def test_a_22_9_kv_no_hay_paso_de_tension():
    """042:RF-50 — solo el alimentador a la tensión que se pasa."""
    vs, _ = eo.variantes('F1', 22.9, _tramos_de(5.0), [], [], P, banco_kvar=None, nivel=NIVEL)
    assert not [v for v in vs if 'nivel' in v.escalones]


def test_sin_barra_de_destino_con_su_fuente_o_a_la_set_nueva():
    """042:RF-52, 042:RF-53 — sin cabecera compartida cambia con su fuente; compartida, lo dice y sigue la escalera."""
    solo = {'salida': '', 'nodo': '', 'km': 3.0, 'seds': 5, 'compartida': False}
    vs, _ = eo.variantes('F1', 10.0, _tramos_de(5.0), [], [], P, banco_kvar=None, nivel=solo)
    (v,) = [v for v in vs if 'nivel' in v.escalones]
    assert v.obras[0]['clase'] == 'tension' and 'celda_nivel' not in v.cantidades
    vs, avisos = eo.variantes('F1', 10.0, _tramos_de(5.0), [], [], P, banco_kvar=None, nivel={**solo, 'compartida': True})
    assert not [v for v in vs if 'nivel' in v.escalones] and any('042:RF-53' in a for a in avisos)


def test_el_paso_de_tension_se_costea_aunque_el_libro_no_lo_traiga():
    """042:RF-54 — por km, SED y celda; del cambio de sección si lo hay, o de referencia, y marcado por confirmar."""
    v = next(v for v in eo.variantes('F1', 10.0, _tramos_de(5.0), [], [], P, banco_kvar=None, nivel=NIVEL)[0]
             if 'nivel' in v.escalones)
    costos = eo.costos_de_alternativas({}, P)
    assert 'por confirmar' in costos['cambio_tension']['origen'] and costos['celda']['unidad'] == 'Und'
    inversion = eo.costo(v, costos, P, perdidas_kw=0.0, factor_perdidas=None)['inversion']
    assert inversion == pytest.approx(12 * eo.COSTOS_NIVEL_DE_REFERENCIA['cambio_tension']
                                      + 40 * eo.COSTOS_NIVEL_DE_REFERENCIA['cambio_tension_sed']
                                      + eo.COSTOS_NIVEL_DE_REFERENCIA['celda'])
    p = eo.parametros({**PERFIL, 'escalera': {**PERFIL['escalera'], 'escala_capex': 1000}})
    con_libro = eo.costos_de_alternativas({'cambio_seccion': {'costo_unitario': 50.0, 'unidad': 'km'}}, p)
    assert con_libro['cambio_tension']['costo_unitario'] == 50000.0 and 'por confirmar' in con_libro['cambio_tension']['origen']


def _opcion(nombre, escalones, anual, fraccion=None, maxima=True):
    return {'nombre': nombre, 'escalones': escalones, 'maxima': maxima, 'fraccion': fraccion, 'motivos': [],
            'costo': {'costo_anual': anual, 'inversion': anual * 10}}


def test_hasta_3_alternativas_de_menor_a_mayor_costo_anual():
    """042:RF-55, 042:RF-56, 042:RF-58 — una por clase de obra; se elige la más barata aunque la sección vaya antes."""
    d = eo.elegir([_opcion('sección', ('seccion',), 900.0, 1.0), _opcion('sección mayor', ('seccion',), 950.0),
                   _opcion('22,9 kV', ('nivel',), 700.0, 1.0), _opcion('terna', ('terna',), 1200.0),
                   _opcion('sección + terna', ('seccion', 'terna'), 1500.0), _opcion('no', ('terna',), 10.0, maxima=False)], P)
    assert d['elegida'] == '22,9 kV'
    assert [(a['numero'], a['nombre']) for a in d['alternativas']] == [(1, '22,9 kV'), (2, 'sección'), (3, 'terna')]
    assert [a['elegida'] for a in d['alternativas']] == [True, False, False]


def test_los_bancos_que_bastan_y_el_regulador_al_final_aunque_cuesten_otra_cosa():
    """042:RF-56 — bancos solos antes (063:RF-22), regulador solo si no hay otra (042:RF-49); la tabla sigue por costo."""
    d = eo.elegir([_opcion('sección', ('seccion',), 100.0, 1.0), _opcion('bancos', ('bancos',), 200.0, 1.0)], P)
    assert d['elegida'] == 'bancos' and [a['nombre'] for a in d['alternativas']] == ['sección', 'bancos']
    d = eo.elegir([_opcion('regulador', ('regulador',), 50.0, 1.0), _opcion('terna', ('terna',), 900.0, 1.0)], P)
    assert d['elegida'] == 'terna'
    assert eo.elegir([_opcion('regulador', ('regulador',), 50.0, 1.0)], P)['elegida'] == 'regulador'


def test_una_alternativa_que_los_sorteos_desmienten_no_se_presenta():
    """042:RF-57 — sin sortear sí se presenta y lo dice; con sorteos por debajo del criterio, no."""
    d = eo.elegir([_opcion('a', ('seccion',), 100.0, 0.5), _opcion('b', ('terna',), 200.0, 1.0), _opcion('c', ('nivel',), 300.0)], P)
    assert [a['nombre'] for a in d['alternativas']] == ['b', 'c'] and d['alternativas'][1]['fraccion'] is None


COMPARTIDA = {'salida': '', 'nodo': 'N1', 'km': 3.0, 'seds': 5, 'compartida': True}


def test_cabecera_compartida_sin_barra_de_destino_lleva_elevador_dedicado():
    """042:RF-61 — 100 A a 10 kV con 100 % de límite son 1,73 MVA: el de 2 MVA, costeado por MVA y por confirmar."""
    vs, avisos = eo.variantes('F1', 10.0, _tramos_de(5.0), [], [], P, banco_kvar=None, nivel=COMPARTIDA)
    (v,) = [v for v in vs if 'nivel' in v.escalones]
    obra = v.obras[0]
    assert (obra['clase'], obra['nodo'], obra['elevador_mva'], obra['kv_destino']) == ('migracion', 'N1', 2.0, 22.9)
    assert not obra.get('salida') and not any('RF-62' in a for a in avisos)
    costos = eo.costos_de_alternativas({}, P)
    assert costos['elevador']['unidad'] == 'MVA' and 'por confirmar' in costos['elevador']['origen']
    inversion = eo.costo(v, costos, P, perdidas_kw=0.0, factor_perdidas=None)['inversion']
    assert inversion == pytest.approx(3 * 40000 + 5 * 9000 + 2 * 50000)


def test_el_elevador_que_no_conviene_dice_su_motivo_y_sigue_a_la_set_nueva():
    """042:RF-62 — más de 20 MVA, o sin primer nodo: lo dice con su motivo; hay variantes de los demás escalones."""
    grande = [{**t, 'corriente_a': 2000.0} for t in _tramos_de(5.0)]
    vs, avisos = eo.variantes('F1', 10.0, grande, [], [], P, banco_kvar=None, nivel=COMPARTIDA)
    assert not [v for v in vs if 'nivel' in v.escalones]
    assert any('pasaría de 20 MVA' in a and 'RF-62' in a for a in avisos)
    _vs, avisos = eo.variantes('F1', 10.0, _tramos_de(5.0), [], [], P, banco_kvar=None, nivel={**COMPARTIDA, 'nodo': ''})
    assert any('primer nodo' in a for a in avisos)


def test_el_elevador_lleva_el_margen_de_lo_que_no_cuenta_el_crecimiento():
    """042:RF-70 — 100 A a 10 kV son 1,73 MVA, por 1,25 son 2,17: el de 3 MVA, no el de 2."""
    p = eo.parametros({**PERFIL, 'planificacion': {**PERFIL['planificacion'], 'factor_seguridad_set': 1.0,
                                                   'factor_seguridad_set_sin_tasa': 1.25}})
    assert eo.mva_del_elevador(10.0, 100.0, p) == 3.0
    assert eo.mva_del_elevador(10.0, 100.0, P) == 2.0


def test_una_alternativa_dice_si_cumple_en_valle():
    """042:RF-69 — la que no cumple en valle no se presenta; la que no se comprobó, sí, y lo dice."""
    d = eo.elegir([{**_opcion('a', ('seccion',), 100.0, 1.0), 'valle': False}, {**_opcion('b', ('terna',), 200.0, 1.0), 'valle': True},
                   _opcion('c', ('nivel',), 300.0, 1.0)], P)
    assert [(a['nombre'], a['valle']) for a in d['alternativas']] == [('b', True), ('c', None)]


def _p_con_factor():
    return eo.parametros({**PERFIL, 'planificacion': {**PERFIL['planificacion'], 'factor_seguridad_set': 1.0,
                                                      'factor_seguridad_set_sin_tasa': 1.25}})


def test_el_regulador_lleva_el_mismo_margen():
    """042:RF-71 — justo en la corriente de una unidad, sin factor basta esa; con 1,25 hace falta una mayor."""
    unidad = eo.unidad_para_corriente(22.9, 1.0)
    camino = [{**t, 'corriente_a': float(unidad.corriente_a)} for t in _camino_que_cae()]

    def nombres(p):
        return {v.nombre.split(' en ')[0] for v in eo._reguladores_en_caminos('F', 22.9, [camino], p, [])}

    assert nombres(P) == {f'regulador {unidad.corriente_a:g} A'}
    assert nombres(_p_con_factor()) and nombres(_p_con_factor()) != nombres(P)


@pytest.mark.parametrize('planificacion,factor', [({}, 1.0), ({'factor_seguridad_set': 1.1}, 1.1),
                                                  ({'factor_seguridad_set_sin_tasa': 1.25}, 1.25),
                                                  ({'factor_seguridad_set': 1.0, 'factor_seguridad_set_sin_tasa': 1.25}, 1.25)])
def test_el_factor_con_y_sin_el_dato_en_el_perfil(planificacion, factor):
    """042:RF-71 — una sola regla: sirve con un perfil parcial, y la SET da el mismo resultado sin contar la tasa."""
    from convertersmartgrid.set_nueva import Parametros, margen_sin_tasa

    p = eo.parametros({**PERFIL, 'planificacion': {**PERFIL['planificacion'], **planificacion}})
    assert p.factor_sin_tasa == factor
    assert margen_sin_tasa(planificacion.get('factor_seguridad_set_sin_tasa'), planificacion.get('factor_seguridad_set')) == factor
    if planificacion.get('factor_seguridad_set'):
        set_nueva = Parametros(5, planificacion['factor_seguridad_set'], {}, 1, planificacion.get('factor_seguridad_set_sin_tasa'))
        assert set_nueva.factor_para(0.0) == factor


def test_la_alternativa_dice_el_factor_si_lleva_regulador_o_elevador():
    """042:RF-72 — con regulador o elevador, su factor; con las demás, ninguno."""
    p = _p_con_factor()
    d = eo.elegir([_opcion('terna', ('terna',), 100.0, 1.0), _opcion('regulador', ('regulador',), 200.0, 1.0),
                   _opcion('paso con elevador dedicado', ('nivel',), 300.0, 1.0)], p)
    assert {a['nombre']: a['factor'] for a in d['alternativas']} == {'terna': None, 'regulador': 1.25, 'paso con elevador dedicado': 1.25}


def test_el_horizonte_con_la_tasa_del_alimentador_o_con_el_factor():
    """042:RF-73 — con tasa, 20, 10 y 5 años a interés compuesto; sin ella, un solo flujo con el factor."""
    p = _p_con_factor()
    h = eo.plan_de_horizonte('F1', 0.03, p)
    assert h['anios'] == [30, 15, 7] and h['factores']['30']['F1'] == pytest.approx(1.03 ** 30)
    sin = eo.plan_de_horizonte('F1', None, p)
    assert sin['anios'] == [30] and sin['factores']['30'] == {'F1': 1.25}
    assert eo.plan_de_horizonte('F1', -0.01, p)['anios'] == [30]


@pytest.mark.parametrize('medida,bien', [
    ({'converge': False}, False),
    ({'converge': True, 'u': {'A': 0.96}, 'carga': {'L': 50.0}}, True),
    ({'converge': True, 'u': {'A': 0.94}, 'carga': {}}, False),
    ({'converge': True, 'u': {'A': 1.06}, 'carga': {}}, False),
    ({'converge': True, 'u': {'A': 0.96}, 'carga': {'L': 120.0}}, False),
    ({'converge': True, 'u': {'SIN_TENSION': 0.0}, 'carga': {}}, True)])
def test_definitiva_es_en_absoluto(medida, bien):
    """042:RF-74 — todas las barras en límites y ningún tramo sobre el límite; una barra sin tensión no cuenta."""
    assert eo.definitiva(medida, P)[0] is bien


def test_el_alcance_no_cambia_ni_el_orden_ni_la_eleccion():
    """042:RF-75 — la temporal más barata sigue primera y es la elegida; cada una dice su alcance."""
    d = eo.elegir([{**_opcion('barata', ('seccion',), 100.0, 1.0), 'horizonte': {'definitiva': False, 'aguanta_anios': 5, 'motivos': ['x']}},
                   {**_opcion('cara', ('terna',), 900.0, 1.0), 'horizonte': {'definitiva': True, 'aguanta_anios': 20, 'motivos': []}},
                   _opcion('otra', ('nivel',), 950.0, 1.0)], P)
    assert d['elegida'] == 'barata'
    assert [(a['nombre'], a['definitiva'], a['aguanta_anios']) for a in d['alternativas']] == [
        ('barata', False, 5), ('cara', True, 20), ('otra', None, None)]


@pytest.mark.parametrize('sin,con,bien', [(1.049, 1.0503, True), (1.049, 1.0539, True), (1.049, 1.0545, False), (1.049, 1.057, False)])
def test_en_valle_subir_por_milesimas_no_es_culpa_de_la_obra(sin, con, bien):
    """042:RF-85 — con 0,005 p.u. de tolerancia, sobre el máximo; más que eso, sí."""
    medida = {'converge': True, 'u': {'B': con}, 'carga': {}}
    assert eo.cumple_en_valle({'u': {'B': sin}, 'carga': {}}, medida, [], P)[0] is bien
    assert eo.cumple({'u': {'B': sin}, 'carga': {}}, medida, [], P)[0] is False      # con la máxima sigue estricto


def test_en_valle_la_carga_nueva_sigue_estricta_y_por_abajo_tambien():
    """042:RF-85 — no vale para la barra de una carga nueva ni para bajar del mínimo."""
    assert eo.cumple_en_valle({'u': {'B': 1.049}, 'carga': {}}, {'converge': True, 'u': {'B': 1.051}, 'carga': {}}, ['B'], P)[0] is False
    assert eo.cumple_en_valle({'u': {'B': 0.951}, 'carga': {}}, {'converge': True, 'u': {'B': 0.948}, 'carga': {}}, [], P)[0] is False


def test_el_horizonte_usa_la_tasa_de_largo_plazo_del_perfil():
    """042:RF-86 — la del perfil; sin ella, la de referencia. No la medida, que en un alimentador salía 16,5 %."""
    p = eo.parametros({**PERFIL, 'planificacion': {**PERFIL['planificacion'], 'crecimiento_demanda_anual': 0.0346}})
    assert p.tasa_largo_plazo == 0.0346 and P.tasa_largo_plazo == 0.03
    assert eo.plan_de_horizonte('F1', p.tasa_largo_plazo, p)['factores']['30']['F1'] == pytest.approx(1.0346 ** 30)


@pytest.mark.parametrize('fraccion,medidos,seguir', [(1.0, 50, False), (0.98, 50, False), (0.96, 50, True), (0.90, 50, True),
                                                     (0.88, 50, False), (0.96, 200, False)])
def test_los_sorteos_siguen_solo_si_la_etapa_queda_cerca_del_criterio(fraccion, medidos, seguir):
    """042:RF-87 — lejos del 95 %, los demás no cambiarían la decisión; con todos medidos no hay más."""
    assert eo.hace_falta_seguir(fraccion, medidos, 200, P) is seguir


def test_la_definitiva_se_presenta_aunque_no_sea_de_las_tres_mas_baratas():
    """042:RF-91, 042:RF-93 — a la vida útil del perfil; sustituye a la tercera, y la elegida no se toca."""
    assert P.horizonte_anios == 30
    defi = {'definitiva': True, 'aguanta_anios': 30, 'motivos': []}
    d = eo.elegir([_opcion('a', ('seccion',), 100.0, 1.0), _opcion('b', ('terna',), 200.0), _opcion('c', ('nivel',), 300.0),
                   {**_opcion('d', ('seccion', 'terna'), 900.0), 'horizonte': defi}], P)
    assert [a['nombre'] for a in d['alternativas']] == ['a', 'b', 'd'] and d['elegida'] == 'a'


def test_los_bancos_segun_el_perfil_mandan_si_cumplen():
    """094:RF-18 — si la variante de bancos según el perfil cumple, es la elegida aunque otra cueste menos, y la más
    barata queda como alternativa; si no cumple, manda la escalera de siempre (AL209, 2026-11-06)."""
    perfil = {**_evaluada('bancos según perfil 4×450 kvar en A, B, C, D', True, 1.0, 4000), 'escalones': ('bancos',)}
    dos = {**_evaluada('bancos 2×450 kvar', True, 1.0, 2000), 'escalones': ('bancos',)}
    r = eo.elegir([dos, perfil], P)
    assert r['elegida'] == perfil['nombre']
    assert any(a['nombre'] == 'bancos 2×450 kvar' for a in r['alternativas'])
    mal = {**perfil, 'maxima': False, 'motivos': ['no converge']}
    assert eo.elegir([dos, mal], P)['elegida'] == 'bancos 2×450 kvar'


def test_el_refuerzo_de_un_tramo_aereo_es_primero_la_seccion():
    """042:RF-94, 042:RF-43 — PE102: el tramo aéreo al 136 % se cambia de sección; el cable y lo que ninguna sección
    resuelve van con terna."""
    import random

    from convertersmartgrid import escalera_optima as eo
    from convertersmartgrid.perfil_empresa import completar_planeamiento

    rng = random.Random(42094)
    kv = rng.choice([10.0, 13.2, 22.9])
    perfil = completar_planeamiento({'escalera': {'cargabilidad_planeamiento_pct': 100, 'max_variantes': 500}})[0]
    p = eo.parametros(perfil)
    tipos = _tipos(kv)                                       # 150, 300, 450 y 700 A, aéreos
    troncal = [{'nombre': f'L{i}', 'largo_m': 1000.0, 'corriente_a': 50.0, 'inom_a': 700.0} for i in range(3)]
    cargas = [{'barra': 'B2', 'existe': True, 'indice_troncal': 2}]
    largo = rng.uniform(100.0, 900.0)
    aereo = {'nombre': 'A1', 'largo_m': largo, 'carga_pct': 136.2, 'nlnum': 1, 'inom_a': 200.0, 'cable': False}
    cable = {'nombre': 'C1', 'largo_m': 50.0, 'carga_pct': 130.0, 'nlnum': 1, 'inom_a': 200.0, 'cable': True}
    imposible = {'nombre': 'X1', 'largo_m': 80.0, 'carga_pct': 500.0, 'nlnum': 1, 'inom_a': 200.0, 'cable': False}
    vs, _a = eo.variantes('F', kv, troncal, cargas, tipos, p, banco_kvar=450.0, sobrecargados=[aereo, cable, imposible])
    solo = vs[0]
    assert solo.nombre.startswith('refuerzo de 3 tramos sobrecargados')
    secciones = [o for o in solo.obras if o['clase'] == 'seccion']
    # 200 A × 1,362 = 272 A: el menor que lo deja bajo el 100 % es el de 300 A, no el de 450 ni el de 700.
    assert [(o['tipo']['nombre'], o['tramos']) for o in secciones] == [(tipos[1]['nombre'], ['A1'])]
    ternas = [t for o in solo.obras if o['clase'] == 'terna' for t in o['tramos']]
    assert 'A1' not in ternas and 'C1' in ternas and 'X1' in ternas
    assert abs(solo.cantidades['seccion'] - largo / 1000) < 1e-9 and 'seccion' in solo.escalones
    # Si la variante ya le pone obra al tramo, se completa con ternas como hasta ahora (RF-43).
    con_terna = eo.Variante('t', ('terna',), [{'clase': 'terna', 'tramos': ['A1']}], {})
    reforzada = eo._con_refuerzo(con_terna, 'F', [aereo], {}, p, eo.conductores_aptos(tipos, kv, None))
    assert not [o for o in reforzada.obras if o['clase'] == 'seccion']


def test_las_alternativas_se_miden_de_la_mas_barata_a_la_mas_cara():
    """042:RF-95 — de menor a mayor costo; sin costo al final y, entre iguales, el orden de la escalera."""
    import random

    from convertersmartgrid import escalera_optima as eo

    rng = random.Random(42095)
    costos = [rng.choice([None, 100.0, 250.0, 900.0, 40.0]) for _ in range(rng.randint(8, 20))]
    vs = [{'nombre': f'v{i}', 'costo_base': c} for i, c in enumerate(costos)]
    orden = eo.por_costo(vs)
    assert sorted(v['nombre'] for v in orden) == sorted(v['nombre'] for v in vs)
    claves = [(v['costo_base'] is None, v['costo_base'] or 0.0, int(v['nombre'][1:])) for v in orden]
    assert claves == sorted(claves)


# --------------------------------------------------------------------------- 042:RF-97 a RF-106
#: Conductores de una empresa ficticia (P13): tres aéreos normalizados, uno mayor sin normalizar y un cable.
CODIGOS = {'AX050': (150, 1), 'AX120': (300, 1), 'AX240': (450, 1), 'AX300': (700, 1), 'CX120': (320, 0)}


def _biblioteca_terna(kv):
    return [{'nombre': f'{c}_{kv:g}kV', 'clase': 'TypLne', 'origen': 'proyecto',
             'datos': {'uline': kv, 'sline': a / 1000, 'cohl_': cohl, 'rline': 30.0 / a, 'xline': 0.4}}
            for c, (a, cohl) in CODIGOS.items()]


def _p_terna(**escalera):
    esc = {**PERFIL['escalera'], 'secciones_normalizadas': ['AX050', 'AX120', 'AX240', 'CX120'], **escalera}
    return eo.parametros({**PERFIL, 'escalera': esc})


def _troncal_mixta(rng, n=None):
    """Tramos aéreos de 150 A (pasan a 120), de 450 A (ya mayores) y cables de 150 A, sorteados."""
    n = n or rng.randint(4, 10)
    out = []
    for i in range(n):
        cable = rng.random() < 0.3
        inom = 150.0 if cable or rng.random() < 0.6 else 450.0
        out.append({'nombre': f'T{i}', 'largo_m': rng.uniform(100, 900), 'corriente_a': 120.0, 'inom_a': inom,
                    'cable': cable, 'tipo': 'CX070' if cable else f'AX{int(inom)}'})
    return out


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_la_seccion_de_un_circuito_no_pasa_de_la_mayor_normalizada(semilla):
    """042:RF-97 — la sección llega al mayor normalizado (aquí AX240), nunca al AX300 de la biblioteca, también en el
    refuerzo de un tramo que ninguna sección resuelve y en los aptos que recibe la búsqueda del oráculo."""
    rng = random.Random(semilla)
    kv = rng.choice([10.0, 13.2, 22.9])
    p = _p_terna()
    tipos = _biblioteca_terna(kv)
    troncal = _troncal(rng, corriente=rng.uniform(100, 400))
    for t in troncal:
        t['inom_a'] = 150.0
    cargas = [{'barra': 'B', 'existe': True, 'indice_troncal': len(troncal) - 1}]
    imposible = {'nombre': 'X1', 'largo_m': 80.0, 'carga_pct': 900.0, 'nlnum': 1, 'inom_a': 150.0, 'cable': False}
    vs, _av = eo.variantes('F', kv, troncal, cargas, tipos, p, banco_kvar=None, sobrecargados=[imposible])
    usados = {o['tipo']['nombre'] for v in vs for o in v.obras if o['clase'] == 'seccion'}
    assert usados and not any(n.startswith(('AX300', 'CX')) for n in usados)
    assert any(n.startswith('AX240') for n in usados)
    aptos = [t['nombre'] for t in eo.secciones_aptas(tipos, kv, None, p)]
    assert aptos == [f'AX050_{kv:g}kV', f'AX120_{kv:g}kV', f'AX240_{kv:g}kV']


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_conductor_terna_deja_los_dos_circuitos_en_el_del_perfil(semilla):
    """042:RF-98, 042:RF-99, 042:RF-103 — el tramo más delgado pasa al conductor del perfil (aéreo o cable) y la
    terna es del mismo; el que ya lleva más corriente añade la de su tipo, con aviso; el cambio se costea como
    sección de esos tramos (PE102, 2026-11-07: «la nueva terna debe ser en 120 mm², ambas ternas»)."""
    rng = random.Random(semilla)
    kv = rng.choice([10.0, 22.9])
    p = _p_terna(conductor_terna={'aereo': 'AX120', 'cable': 'CX120'})
    troncal = _troncal_mixta(rng)
    cargas = [{'barra': 'B', 'existe': True, 'indice_troncal': len(troncal) - 1}]
    vs, av = eo.variantes('F', kv, troncal, cargas, _biblioteca_terna(kv), p, banco_kvar=None)
    (terna,) = [v for v in vs if v.escalones == ('terna',)]
    (obra,) = terna.obras
    assert obra['tipo']['nombre'] == f'AX120_{kv:g}kV' and obra['tipo_cable']['nombre'] == f'CX120_{kv:g}kV'
    esperado = {t['nombre']: (f'CX120_{kv:g}kV' if t['cable'] else f'AX120_{kv:g}kV')
                for t in troncal if t['inom_a'] < (320 if t['cable'] else 300)}
    assert obra.get('cambia_tipo', {}) == esperado
    km = sum(t['largo_m'] for t in troncal if t['nombre'] in esperado) / 1000
    assert abs(terna.cantidades.get('seccion', 0.0) - km) < 1e-9
    assert abs(terna.cantidades['terna'] - sum(t['largo_m'] for t in troncal) / 1000) < 1e-9
    for nombre in (t['nombre'] for t in troncal if t['nombre'] not in esperado):
        assert any(nombre in a and '042:RF-99' in a for a in av)
    capex = {'nueva_terna': {'costo_unitario': 100.0, 'unidad': 'km'},
             'cambio_seccion': {'costo_unitario': 40.0, 'unidad': 'km'}}
    c = eo.costo(terna, capex, p, perdidas_kw=None, factor_perdidas=None)
    assert abs(c['inversion'] - (100.0 * terna.cantidades['terna'] + 40.0 * km)) < 1e-6


def test_conductor_terna_sin_la_clave_o_sin_el_tipo_la_terna_es_como_antes():
    """042:RF-100 — sin `escalera.conductor_terna`, o sin el conductor de cable en la biblioteca, la terna es la de
    siempre en esos tramos, y se dice."""
    rng = random.Random(42100)
    kv = 22.9
    troncal = _troncal_mixta(rng, 6)
    troncal[0].update(cable=True, inom_a=150.0)
    cargas = [{'barra': 'B', 'existe': True, 'indice_troncal': len(troncal) - 1}]
    vs, av = eo.variantes('F', kv, troncal, cargas, _biblioteca_terna(kv), _p_terna(), banco_kvar=None)
    (obra,) = next(v for v in vs if v.escalones == ('terna',)).obras
    assert not {'tipo', 'tipo_cable', 'cambia_tipo'} & set(obra)
    assert any('escalera.conductor_terna' in a and '042:RF-100' in a for a in av)
    sin_cable = [t for t in _biblioteca_terna(kv) if not t['nombre'].startswith('CX')]
    p = _p_terna(conductor_terna={'aereo': 'AX120', 'cable': 'CX120'})
    vs, av = eo.variantes('F', kv, troncal, cargas, sin_cable, p, banco_kvar=None)
    (obra,) = next(v for v in vs if v.escalones == ('terna',)).obras
    assert 'tipo_cable' not in obra and troncal[0]['nombre'] not in obra.get('cambia_tipo', {})
    assert any(troncal[0]['nombre'] in a and '042:RF-100' in a for a in av)


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_conductor_terna_sin_doble_circuito_de_la_seccion(semilla):
    """042:RF-102 — con el conductor de la terna, ninguna variante pone sección y terna en el mismo tramo (el 240 va
    solo en un circuito), tampoco el refuerzo de los tramos sobrecargados; sin la clave, la doble terna de RF-30 sigue."""
    rng = random.Random(semilla)
    kv = rng.choice([10.0, 22.9])
    troncal = _troncal_mixta(rng)
    for t in troncal:
        t.update(cable=False, inom_a=150.0)
    cargas = [{'barra': 'B', 'existe': True, 'indice_troncal': len(troncal) - 1}]
    tipos = _biblioteca_terna(kv)
    sobre = [{**troncal[0], 'carga_pct': rng.uniform(150, 400), 'nlnum': 1}]
    p = _p_terna(conductor_terna={'aereo': 'AX120', 'cable': 'CX120'})
    vs, _av = eo.variantes('F', kv, troncal, cargas, tipos, p, banco_kvar=450.0, sobrecargados=sobre)
    assert vs and not any(eo.doble_con_seccion(v) for v in vs)
    assert any('terna' in v.escalones for v in vs) and any('seccion' in v.escalones for v in vs)
    vs, _av = eo.variantes('F', kv, troncal, cargas, tipos, _p_terna(), banco_kvar=450.0)
    assert any(eo.doble_con_seccion(v) for v in vs)


def test_conductor_terna_en_el_refuerzo_de_un_cable_cambia_y_suma_una():
    """042:RF-98, 042:RF-43 — un cable sobrecargado de 150 A recibe la terna del cable del perfil aunque el cambio de
    conductor bastara, porque un cable no cambia de sección solo (RF-94); el conductor cambia una vez."""
    p = _p_terna(conductor_terna={'aereo': 'AX120', 'cable': 'CX120'})
    de_terna = eo.tipos_de_terna(_biblioteca_terna(10.0), 10.0, p)
    cable = {'nombre': 'C1', 'largo_m': 50.0, 'carga_pct': 180.0, 'nlnum': 1, 'inom_a': 150.0, 'cable': True,
             'tipo': 'CX070'}
    v = eo._con_refuerzo(eo.Variante('', (), [], {}), 'F', [cable], {}, p, (), de_terna)
    ternas = [o for o in v.obras if o['clase'] == 'terna']
    assert len(ternas) == 1 and ternas[0]['cambia_tipo'] == {'C1': 'CX120_10kV'}
    v = eo._con_refuerzo(eo.Variante('', (), [], {}), 'F', [{**cable, 'carga_pct': 500.0}], {}, p, (), de_terna)
    ternas = [o for o in v.obras if o['clase'] == 'terna']
    assert len(ternas) == 2 and [bool(o.get('cambia_tipo')) for o in ternas] == [True, False]


@pytest.mark.parametrize('valor, n', [(None, 3), (3, 3), (4, 4), (6, 6)])
def test_alternativas_del_perfil_de_3_a_6(valor, n):
    """042:RF-105 — `escalera.alternativas` dice cuántas se presentan; sin ella, 3, y la definitiva sustituye a la última."""
    p = _p_terna(**({} if valor is None else {'alternativas': valor}))
    assert p.alternativas == n
    rng = random.Random(42105 + n)
    clases = [('bancos',), ('seccion',), ('terna',), ('nivel',), ('seccion', 'terna'), ('regulador',), ('bancos', 'terna')]
    opciones = [_opcion(f'o{i}', c, rng.uniform(100, 1000), 1.0) for i, c in enumerate(clases)]
    d = eo.elegir(opciones, p)
    assert len(d['alternativas']) == n
    cara = max(opciones, key=lambda o: o['costo']['costo_anual'])
    defi = {**cara, 'horizonte': {'definitiva': True, 'aguanta_anios': 30, 'motivos': []}}
    d = eo.elegir([o for o in opciones if o is not cara] + [defi], p)
    assert len(d['alternativas']) == n and any(a['nombre'] == defi['nombre'] for a in d['alternativas'])


@pytest.mark.parametrize('valor', [2, 7, 0, 3.5, '4', True])
def test_alternativas_fuera_de_3_a_6_se_rechazan(valor):
    """042:RF-106 — un valor que no es un entero de 3 a 6 es un error que nombra la clave."""
    with pytest.raises(eo.EscaleraError, match='escalera.alternativas'):
        _p_terna(alternativas=valor)
