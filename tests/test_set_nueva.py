"""Spec 042: diseño, módulo PIT y ubicación de la SET nueva, sin DIgSILENT.

El caso real es NA203 + NA205 (2026-10-31): 37 cargas nuevas sobre 11 MW calibrados; la SET nueva
es la Copara que Electro Dunas planifica en Nasca, con los módulos de su libro CAPEX (`PyOTx27`).
Las redes y las cargas se sortean (``CSG_SCALE_SEED``).
"""
from __future__ import annotations

import math
import os
import random

import pytest

from convertersmartgrid import set_nueva as sn

SEMILLA = int(os.environ.get('CSG_SCALE_SEED', random.randrange(1 << 30)))
openpyxl = pytest.importorskip('openpyxl')

CFG_PIT = {'hoja': 'PyOTx27', 'fila_cabecera_contiene': 'OBJETO',
           'columnas': {'descripcion': 'OBJETO', 'costo': 'VALOR TOTAL DEL CONTRATO', 'moneda': 'MONEDA'},
           'escala': 1}


def _libro(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'PyOTx27'
    ws.append([])
    ws.append(['', 'CONSECUTIVO', 'OBJETO \nCONTRACTUAL', 'MONEDA DE ORIGEN', 'VALOR TOTAL DEL CONTRATO EN MONEDA ORIGEN'])
    ws.append(['', 1, 'Transformador de reserva compartida de 60/22,9/10 de 25/25/25 MVA - SET Copara', 'Dólar', 571957.91])
    ws.append(['', 1, 'Transformador de Potencia 60/22,9/10 kV de 15/15/15 MVA - SET Palpa', 'Dólar', 766307.3])
    ws.append(['', 1, 'Segunda terna de la Línea de Transmisión 220 kV Independencia - El Ángel', 'Dólar', 1030000])
    ws.append(['', 1, 'Transformador de Potencia 60/22,9/10 kV de 40/40/40 MVA, SET Chincha Nueva', 'Dólar', 927250])
    ws.append(['', 1, 'Nueva SET Copara 60/22,9/10 kV de 25/25/25 MVA y LT 60 kV Cahuachi – Copara de 14,1 km', 'Dólar', 5748960.51])
    ruta = tmp_path / 'capex.xlsx'
    wb.save(ruta)
    return ruta


# =========================================================================== RF-7, RF-8
def test_potencia_de_diseno_con_la_tasa_ponderada_y_el_factor():
    """042:RF-7 — (trasladado × (1 + g)^n + nuevas) × FS, con g de cada alimentador ponderada por
    la demanda que traslada; las cargas nuevas no crecen; cada término sale en el resultado."""
    d = sn.potencia_de_diseno({'NA203': (3000.0, 1000.0), 'NA205': (1000.0, 0.0)},
                              (8000.0, 2000.0), {'NA203': 0.03, 'NA205': 0.01},
                              anios=30, factor_seguridad=1.25)
    trasladado = math.hypot(3000, 1000) + 1000.0
    g = (0.03 * math.hypot(3000, 1000) + 0.01 * 1000.0) / trasladado
    base = math.hypot(4000, 1000) + math.hypot(8000, 2000)
    assert d['tasa_ponderada'] == pytest.approx(g)
    assert d['kva_base'] == pytest.approx(base)
    assert d['kva_diseno'] == pytest.approx((math.hypot(4000, 1000) * (1 + g) ** 30 + math.hypot(8000, 2000)) * 1.25)
    assert d['anios'] == 30 and d['factor_seguridad'] == 1.25


def test_sin_tasa_de_un_alimentador_no_se_supone():
    """042:RF-8 — un alimentador sin tasa de la 029 se dice y no se supone ninguna."""
    with pytest.raises(sn.SetNuevaError, match='NA205'):
        sn.potencia_de_diseno({'NA203': (1.0, 0.0), 'NA205': (1.0, 0.0)}, (1.0, 0.0),
                              {'NA203': 0.02}, anios=30, factor_seguridad=1.25)


def test_parametros_del_perfil_dicen_lo_que_falta():
    """042:RF-8 — sin el factor de seguridad o sin los módulos PIT en el perfil, se dice cuál falta."""
    with pytest.raises(sn.SetNuevaError, match='factor_seguridad_set'):
        sn.parametros({'planificacion': {'vida_util_anios': 30, 'modulos_pit': CFG_PIT}})
    with pytest.raises(sn.SetNuevaError, match='modulos_pit'):
        sn.parametros({'planificacion': {'vida_util_anios': 30, 'factor_seguridad_set': 1.25}})
    p = sn.parametros({'planificacion': {'vida_util_anios': 30, 'factor_seguridad_set': 1.25,
                                         'modulos_pit': CFG_PIT}})
    assert p.anios == 30 and p.factor_seguridad == 1.25


# =========================================================================== módulos PIT
def test_modulos_pit_del_libro_capex(tmp_path):
    """042:RF-5, 042:RF-7 — del libro se leen los módulos de SET y de transformador con su
    relación de tensiones, su potencia y su costo; la línea de 220 kV no es un módulo de SET."""
    mods = sn.leer_modulos_pit(_libro(tmp_path), CFG_PIT)
    resumen = sorted((m['tipo'], m['mva'], m['kv_mt'], round(m['costo'])) for m in mods)
    assert resumen == [('set', 25.0, 22.9, 5748961), ('transformador', 15.0, 22.9, 766307),
                       ('transformador', 25.0, 22.9, 571958), ('transformador', 40.0, 22.9, 927250)]
    assert all(m['kv_at'] == 60.0 for m in mods)


def test_se_elige_el_menor_modulo_que_cubre(tmp_path):
    """042:RF-7 — la SET nueva si su módulo cubre la potencia de diseño; si no, el menor
    transformador que la cubre; si ninguno, se dice."""
    mods = sn.leer_modulos_pit(_libro(tmp_path), CFG_PIT)
    assert sn.elegir_modulo(mods, 20_000.0, 22.9)['modulo']['tipo'] == 'set'
    grande = sn.elegir_modulo(mods, 30_000.0, 22.9)['modulo']
    assert (grande['tipo'], grande['mva']) == ('transformador', 40.0)
    ninguno = sn.elegir_modulo(mods, 60_000.0, 22.9)
    assert ninguno['modulo'] is None and '60' in ninguno['motivo']
    assert sn.elegir_modulo(mods, 20_000.0, 22.9)['modulo']['unidades'] == 1


def test_transformadores_en_paralelo_si_ninguno_cubre_solo(tmp_path):
    """042:RF-14 — si ningún módulo cubre solo la potencia y el perfil admite n en paralelo, la SET
    una vez y n − 1 transformadores de su potencia; sin módulo de SET que llegue, n
    transformadores; sin el dato del perfil, uno solo. NA203 + NA205 (2026-10-31): 45,5 MVA y el
    mayor módulo de 22,9 kV era de 40."""
    mods = sn.leer_modulos_pit(_libro(tmp_path), CFG_PIT)
    copara = next(m for m in mods if m['tipo'] == 'set')
    trafo25 = next(m for m in mods if m['tipo'] == 'transformador' and m['mva'] == 25.0)
    par = sn.elegir_modulo(mods, 45_500.0, 22.9, max_unidades=2)['modulo']
    assert (par['tipo'], par['mva'], par['unidades'], par['mva_total']) == ('set', 25.0, 2, 50.0)
    assert par['costo_total'] == pytest.approx(copara['costo'] + trafo25['costo'])
    dos40 = sn.elegir_modulo(mods, 60_000.0, 22.9, max_unidades=2)['modulo']
    assert (dos40['tipo'], dos40['mva'], dos40['unidades']) == ('transformador', 40.0, 2)
    assert sn.elegir_modulo(mods, 90_000.0, 22.9, max_unidades=2)['modulo'] is None
    assert sn.elegir_modulo(mods, 45_500.0, 22.9)['modulo'] is None
    base = {'vida_util_anios': 30, 'factor_seguridad_set': 1.25, 'modulos_pit': CFG_PIT}
    assert sn.parametros({'planificacion': base}).max_unidades == 1
    assert sn.parametros({'planificacion': {**base, 'transformador_set': {'unidades_en_paralelo_max': 2}}}).max_unidades == 2


# =========================================================================== RF-1 a RF-3
def test_orden_de_mayor_a_menor_potencia():
    """042:RF-1 — de mayor a menor kW; a igual potencia, por nombre, para repetir el resultado."""
    cargas = [{'sed': 'B', 'kw': 500.0}, {'sed': 'A', 'kw': 500.0}, {'sed': 'C', 'kw': 2500.0},
              {'sed': 'D', 'kw': None}]
    assert [c['sed'] for c in sn.orden_de_cargas(cargas)] == ['C', 'A', 'B', 'D']


def test_cuantas_caben_por_biseccion():
    """042:RF-2, 042:RF-3 — el mayor k que cabe, el mismo que añadiéndolas una a una, galopando
    desde abajo y afinando por bisección: unas 2·log2(k) escaleras, ninguna dos veces, y como
    mucho dos que no caben más que las de afinar (NA203 + NA205: caben 3 de 35)."""
    rng = random.Random(SEMILLA)
    for _ in range(50):
        n = rng.randint(0, 60)
        limite = rng.randint(0, n)
        probadas = []

        def cabe(k, limite=limite, probadas=probadas):
            probadas.append(k)
            return k <= limite

        k, pruebas = sn.cuantas_caben(n, cabe)
        assert k == limite, SEMILLA
        assert len(probadas) == len(set(probadas)) == len(pruebas), SEMILLA
        assert len(probadas) <= 2 * math.ceil(math.log2(limite + 2)) + 1, SEMILLA
        no_caben = [k_ for k_ in probadas if k_ > limite]
        assert len(no_caben) <= math.ceil(math.log2(limite + 2)) + 1, SEMILLA


# =========================================================================== RF-6
def _red(enlaces):
    from convertersmartgrid.troncal import Barra, Tramo, red_de

    barras = {b for a, c in enlaces for b in (a, c)}
    return red_de([Barra(b) for b in sorted(barras)],
                  [Tramo(f'L_{a}_{c}', a, c, 100.0) for a, c in enlaces])


def test_rama_del_ancestro_comun_y_su_corte():
    """042:RF-6 — las cargas de C y D cuelgan de B: pasa la rama de B y se abre el tramo que
    llega a B; lo que queda aguas arriba no se toca."""
    red = _red([('H', 'A'), ('A', 'B'), ('B', 'C'), ('B', 'D')])
    (r,) = sn.ramas_a_trasladar(red, 'H', {'C', 'D'}, {'A': 50.0, 'B': 10.0, 'C': 5.0}, max_ramas=1)
    assert (r['nodo'], r['entrada']) == ('B', 'L_A_B')
    assert set(r['barras']) == {'B', 'C', 'D'} and r['destino'] == ['C', 'D']
    assert r['kw_existente'] == pytest.approx(15.0)


def test_rama_por_cada_salida_de_la_cabecera():
    """042:RF-6 — cargas en dos salidas de la cabecera: una rama en cada una, nunca la cabecera."""
    red = _red([('H', 'A1'), ('A1', 'A2'), ('H', 'B1'), ('B1', 'B2')])
    ramas = sn.ramas_a_trasladar(red, 'H', {'A2', 'B2'}, {}, max_ramas=1)
    assert sorted(r['nodo'] for r in ramas) == ['A2', 'B2']


def test_con_mas_alimentadores_nuevos_se_parte_la_rama_que_arrastra_mas_carga():
    """042:RF-6 — con un alimentador nuevo pasa la rama de X entera (con sus 900 kW); con dos,
    se parte en las subramas que tienen cargas nuevas y X se queda."""
    red = _red([('H', 'X'), ('X', 'Y1'), ('Y1', 'Y2'), ('X', 'Z1'), ('X', 'W')])
    kw = {'X': 900.0, 'W': 300.0, 'Y2': 10.0, 'Z1': 10.0}
    (una,) = sn.ramas_a_trasladar(red, 'H', {'Y2', 'Z1'}, kw, max_ramas=1)
    assert una['nodo'] == 'X' and una['kw_existente'] == pytest.approx(1220.0)
    dos = sn.ramas_a_trasladar(red, 'H', {'Y2', 'Z1'}, kw, max_ramas=2)
    assert sorted(r['nodo'] for r in dos) == ['Y2', 'Z1']
    assert sum(r['kw_existente'] for r in dos) == pytest.approx(20.0)


def test_ramas_sorteadas_cubren_cada_carga_una_vez():
    """042:RF-6 — en árboles sorteados: cada barra destino en una sola rama, ramas sin la
    cabecera y sin barras comunes, y no más ramas que las pedidas salvo las salidas de la cabecera."""
    rng = random.Random(SEMILLA)
    for _ in range(30):
        n = rng.randint(5, 120)
        enlaces = [(f'B{rng.randrange(i)}', f'B{i}') for i in range(1, n)]
        red = _red(enlaces)
        destino = set(rng.sample([f'B{i}' for i in range(1, n)], rng.randint(1, min(10, n - 1))))
        kw = {f'B{i}': rng.uniform(0, 500) for i in range(n)}
        maximo = rng.randint(1, 6)
        ramas = sn.ramas_a_trasladar(red, 'B0', destino, kw, max_ramas=maximo)
        vistas = [b for r in ramas for b in r['barras']]
        assert len(vistas) == len(set(vistas)) and 'B0' not in vistas, SEMILLA
        assert sorted(d for r in ramas for d in r['destino']) == sorted(destino), SEMILLA
        salidas = {b for a, b in enlaces if a == 'B0'}
        assert len(ramas) <= max(maximo, len(salidas)), SEMILLA


def test_la_rama_empieza_en_una_barra_que_existe_sin_las_cargas_nuevas():
    """042:RF-15 — la barra T la crea la variación de la carga al partir A–B: la rama sube hasta
    A, la barra existente más cercana, y lleva dentro la carga; nunca la cabecera."""
    red = _red([('H', 'A'), ('A', 'T'), ('T', 'B'), ('T', 'CARGA'), ('A', 'C')])
    (r,) = sn.ramas_a_trasladar(red, 'H', {'T'}, {'B': 40.0, 'C': 7.0}, max_ramas=3,
                                existentes={'H', 'A', 'B', 'C'})
    assert r['nodo'] == 'A' and {'T', 'CARGA', 'B'} <= set(r['barras']) and r['destino'] == ['T']
    with pytest.raises(sn.SetNuevaError, match='cabecera'):
        sn.ramas_a_trasladar(_red([('H', 'T'), ('T', 'CARGA')]), 'H', {'T'}, {}, max_ramas=1,
                             existentes={'H'})


def test_ramas_sorteadas_con_barras_nuevas_empiezan_en_existentes():
    """042:RF-15 — en árboles sorteados con barras que solo crean las cargas nuevas: toda rama
    empieza en una existente, sin barras repetidas, y cada destino queda en una rama."""
    rng = random.Random(SEMILLA)
    for _ in range(30):
        n = rng.randint(6, 120)
        enlaces = [(f'B{rng.randrange(i)}', f'B{i}') for i in range(1, n)]
        hijos_de_b0 = {f'B{i}' for i in range(1, n) if enlaces[i - 1][0] == 'B0'}
        nuevas = set(rng.sample([f'B{i}' for i in range(1, n) if f'B{i}' not in hijos_de_b0],
                                min(5, max(0, n - 1 - len(hijos_de_b0)))))
        existentes = {f'B{i}' for i in range(n)} - nuevas
        destino = set(rng.sample([f'B{i}' for i in range(1, n)], rng.randint(1, min(10, n - 1))))
        ramas = sn.ramas_a_trasladar(_red(enlaces), 'B0', destino, {}, max_ramas=rng.randint(1, 6),
                                     existentes=existentes)
        vistas = [b for r in ramas for b in r['barras']]
        assert len(vistas) == len(set(vistas)), SEMILLA
        assert all(r['nodo'] in existentes for r in ramas), SEMILLA
        assert sorted(d for r in ramas for d in r['destino']) == sorted(destino), SEMILLA


def test_una_carga_en_la_cabecera_no_se_traslada():
    """042:RF-6 — la barra de cabecera no puede pasar a otra SET: se dice."""
    with pytest.raises(sn.SetNuevaError, match='cabecera'):
        sn.ramas_a_trasladar(_red([('H', 'A')]), 'H', {'H'}, {}, max_ramas=1)


# =========================================================================== RF-9
def _sorteo_de_cargas(rng, n, centro, radio_m):
    lat0, lon0 = centro
    out = []
    for _ in range(n):
        d, a = radio_m * rng.random(), 2 * math.pi * rng.random()
        out.append((lat0 + d * math.cos(a) / 111_320.0,
                    lon0 + d * math.sin(a) / (111_320.0 * math.cos(math.radians(lat0))),
                    rng.uniform(100, 2000)))
    return out


def test_la_ubicacion_minimiza_la_suma_de_potencia_por_distancia():
    """042:RF-9 — el punto de Weber: ningún punto vecino da menos Σ P·d esperada."""
    rng = random.Random(SEMILLA)
    existentes = _sorteo_de_cargas(rng, rng.randint(20, 80), (-14.95, -74.98), 6000)
    nuevas = _sorteo_de_cargas(rng, rng.randint(5, 40), (-14.93, -74.99), 4000)
    u = sn.ubicacion_optima(existentes, nuevas, incremento_kw=rng.uniform(1000, 20000),
                            zona_m=1000.0, sorteos=50, semilla=SEMILLA)
    pesos = u['pesos']

    def costo(la, lo):
        return sum(w * sn.distancia_m((la, lo), (pa, po)) for pa, po, w in pesos)

    mejor = costo(u['lat'], u['lon'])
    for dla, dlo in ((1e-3, 0), (-1e-3, 0), (0, 1e-3), (0, -1e-3)):
        assert costo(u['lat'] + dla, u['lon'] + dlo) >= mejor - 1e-6, SEMILLA


def test_el_crecimiento_tira_hacia_donde_estan_las_cargas_nuevas():
    """042:RF-9 — con más crecimiento esperado, el punto se acerca a la zona de las cargas nuevas
    del bloque; los sorteos dan la dispersión y se repiten con la misma semilla."""
    rng = random.Random(SEMILLA)
    existentes = _sorteo_de_cargas(rng, 40, (-14.95, -74.98), 3000)
    nuevas = _sorteo_de_cargas(rng, 10, (-14.90, -74.93), 1500)
    zona = (sum(x[0] for x in nuevas) / 10, sum(x[1] for x in nuevas) / 10)
    poco = sn.ubicacion_optima(existentes, nuevas, incremento_kw=0.0, zona_m=1000.0, sorteos=30, semilla=1)
    mucho = sn.ubicacion_optima(existentes, nuevas, incremento_kw=200_000.0, zona_m=1000.0,
                                sorteos=30, semilla=1)
    assert sn.distancia_m((mucho['lat'], mucho['lon']), zona) < sn.distancia_m((poco['lat'], poco['lon']), zona)
    assert mucho['dispersion_m'] >= 0
    otra = sn.ubicacion_optima(existentes, nuevas, incremento_kw=200_000.0, zona_m=1000.0,
                               sorteos=30, semilla=1)
    assert (otra['lat'], otra['lon'], otra['dispersion_m']) == (mucho['lat'], mucho['lon'], mucho['dispersion_m'])


def test_las_cargas_se_agrupan_por_zona_geografica():
    """042:RF-21 — Pisco: Salud Huaytará a 90 km no va con las de Pisco; sin radio, una sola zona."""
    from convertersmartgrid.set_nueva import zonas_de_carga

    cargas = [{'sed': 'A', 'kw': 4900, 'lat': -13.7654, 'lon': -76.1704},
              {'sed': 'B', 'kw': 2100, 'lat': -13.7082, 'lon': -76.1582},
              {'sed': 'C', 'kw': 658, 'lat': -13.6033, 'lon': -75.3437},
              {'sed': 'D', 'kw': 300, 'lat': None, 'lon': None}]
    zonas = zonas_de_carga(cargas, 10)
    assert sorted(sorted(c['sed'] for c in z) for z in zonas) == [['A', 'B'], ['C'], ['D']]
    assert zonas_de_carga(cargas, None) == [cargas]
