"""Spec 012, T5: lo que los estudios de confiabilidad y capacidad deciden sin DIgSILENT.

Resultados sorteados con la forma que devuelven los guiones; ningún número de una red real.
"""

from __future__ import annotations

import random

import pytest

from igea_dgs import estudios_red_pf as er
from igea_dgs.estudios_pf import CON_PROYECTO, DIFERENCIA, SIN_PROYECTO, escribir_csv

SEMILLAS = [random.randrange(10**6) for _ in range(4)]


def _cargas(rng, n=None, clientes=None):
    out = []
    for i in range(n or rng.randint(2, 12)):
        k = clientes if clientes is not None else rng.randint(1, 400)
        lpif, lpit = rng.uniform(0, 3), rng.uniform(0.1, 10)
        out.append({'nombre': f'L{i}', 'nrcust': k, 'tcif': lpif * k, 'tcit': lpit * k,
                    'lpens': rng.uniform(0.01, 5)})
    return out


def _leido(rng, **extra):
    cargas = _cargas(rng)
    s = er.indices_de_cargas(cargas)
    ind = {'SAIFI': s['saifi'], 'SAIDI': s['saidi'], 'CAIDI': s['caidi'], 'ENS': s['ens_kwh'] / 1000,
           'MAIFI': rng.choice([None, rng.uniform(0, 2)])}
    aportes = [{'elemento': f'E{i}', 'clase': 'ElmLne', 'ens_mwh': rng.uniform(0, 3), 'pct': 1.0}
               for i in range(rng.randint(0, 12))]
    return {'cargas': cargas, 'indices': ind, 'aportes': aportes, **extra}


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_indices_por_alimentador_y_suma_por_cargas(semilla):
    """012:RF-30, 012:RF-67 — SAIFI, SAIDI, CAIDI, ENS en kWh/a y MAIFI por alimentador; la suma
    del manual por cargas coincide y, si no, se avisa."""
    rng = random.Random(semilla)
    leido = _leido(rng)
    fila = er.confiabilidad('F1', leido)
    s = er.indices_de_cargas(leido['cargas'])
    assert fila['saifi'] == pytest.approx(s['saifi']) and fila['ens_kwh'] == pytest.approx(s['ens_kwh'])
    assert fila['caidi'] == pytest.approx(fila['saidi'] / fila['saifi'])
    assert not any('no coincide' in a for a in fila['avisos'])
    if leido['indices']['MAIFI'] is None:
        assert fila['maifi'] is None and any('MAIFI' in a for a in fila['avisos'])
    leido['indices']['SAIDI'] *= 2
    assert any('saidi' in a and 'no coincide' in a for a in er.confiabilidad('F1', leido)['avisos'])


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_los_cinco_que_mas_aportan(semilla):
    """012:RF-32 — los cinco elementos que más aportan a la ENS, de mayor a menor, en kWh/a."""
    rng = random.Random(semilla)
    elems = [{'elemento': f'E{i}', 'ens_mwh': rng.choice([0.0, rng.uniform(0.01, 9)])}
             for i in range(rng.randint(0, 15))]
    top = er.aportes(elems)
    positivos = sorted((e['ens_mwh'] * 1000 for e in elems if e['ens_mwh'] > 0), reverse=True)
    assert [t['ens_kwh'] for t in top] == pytest.approx(positivos[:5])


def test_sin_tension_o_con_tasas_cero_no_da_ceros():
    """012:RF-71, 012:RF-33 — sin tensión antes de la falla, o con todas las tasas a cero, no
    hay índices y se dice por qué."""
    rng = random.Random(1)
    for clave, texto in (('sin_tension', 'sin tensión'), ('tasas_cero', 'tasas de falla son cero')):
        fila = er.confiabilidad('F1', _leido(rng, **{clave: True}))
        assert all(fila[k] is None for k in er.INDICES) and texto in fila['motivo'] and not fila['fiable']


def test_cargas_sin_clientes_y_todas_con_uno():
    """012:RF-25, 012:RF-70 — se cuentan las cargas sin clientes; si todas tienen uno, se avisa
    que el número probablemente no llegó."""
    rng = random.Random(2)
    leido = _leido(rng)
    leido['cargas'][0]['nrcust'] = 0
    leido['cargas'][1]['nrcust'] = None
    assert er.confiabilidad('F1', leido)['cargas_sin_clientes'] == 2
    uno = {'cargas': _cargas(rng, clientes=1), 'indices': {}}
    assert any('un solo cliente' in a for a in er.confiabilidad('F1', uno)['avisos'])


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_diferencias_y_ens_total(semilla):
    """012:RF-31, 012:RF-67, 012:RF-68 — con − sin por alimentador; ENS total de los marcados y
    su diferencia en kWh/a y en %; uno sin índices no cuenta como cero."""
    rng = random.Random(semilla)
    feeders = [f'F{i}' for i in range(rng.randint(2, 6))]
    sin = {f: er.confiabilidad(f, _leido(rng)) for f in feeders}
    con = {f: er.confiabilidad(f, _leido(rng)) for f in feeders}
    sin[feeders[0]] = er.confiabilidad(feeders[0], _leido(rng, sin_tension=True))
    c = er.comparar(sin, con)
    for f in feeders[1:]:
        assert c['por_alimentador'][f]['ens_kwh'] == pytest.approx(con[f]['ens_kwh'] - sin[f]['ens_kwh'])
        assert c['por_alimentador'][f]['ens_pct'] == pytest.approx(
            100 * (con[f]['ens_kwh'] - sin[f]['ens_kwh']) / sin[f]['ens_kwh'])
    assert c['por_alimentador'][feeders[0]]['ens_kwh'] is None
    t_sin = sum(sin[f]['ens_kwh'] for f in feeders[1:])
    t_con = sum(con[f]['ens_kwh'] for f in feeders)
    assert c['ens_total_kwh'] == pytest.approx({SIN_PROYECTO: t_sin, CON_PROYECTO: t_con})
    assert c['ens_total_diferencia_kwh'] == pytest.approx(t_con - t_sin)
    assert c['ens_total_diferencia_pct'] == pytest.approx(100 * (t_con - t_sin) / t_sin)


def test_mejora_de_la_ventana_de_salida_con_coma_decimal():
    """012:RF-39 — la mejora de la ENS que escribe la ubicación de reconectadores, en kWh/a."""
    lineas = ['info - otra cosa',
              'info - The ENS is reduced by 1,25 MWh/a (Before: 10,50 MWh/a, After: 9,25 MWh/a).']
    assert er.mejora_de_salida(lineas) == pytest.approx(
        {'reduccion_kwh': 1250.0, 'antes_kwh': 10500.0, 'despues_kwh': 9250.0})
    assert er.mejora_de_salida(['nada']) is None


def test_reconectadores_por_alimentador_y_sin_candidatos():
    """012:RF-39 — cada propuesto con su alimentador; un alimentador sin candidatos se dice."""
    r = er.reconectadores([{'alimentador': 'F1', 'elemento': 'SW2'}, {'alimentador': 'F1', 'elemento': 'SW1'}],
                          {'F1': 3, 'F2': 0}, ['F1', 'F2'])
    assert [p['elemento'] for p in r['por_alimentador']['F1']] == ['SW1', 'SW2']
    assert r['por_alimentador']['F2'] == [] and any('F2' in a and 'candidato' in a for a in r['avisos'])


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_capacidad_por_nodo_motivo_y_extremos(semilla, tmp_path):
    """012:RF-47, 012:RF-48, 012:RF-49, 012:RF-72 — por nodo la generación y la carga máximas,
    el elemento que limita y su motivo; un nodo sin carga conectada no es capacidad cero;
    por alimentador la menor y la mayor; fichero con una fila por caso y nodo."""
    rng = random.Random(semilla)
    nodos = []
    for f in [f'F{i}' for i in range(rng.randint(1, 4))]:
        for i in range(rng.randint(1, 8)):
            carga = rng.choice([[1, 0.0, 0.0, None], [rng.choice([1, 2, 3]), rng.uniform(0, 5), 0.0, f'L{i}']])
            nodos.append(er.nodo_de_capacidad(f, f'{f}_B{i}', [rng.choice([1, 2, 3]), rng.uniform(0, 9), 0.0, f'L{i}'],
                                              carga))
    for n in nodos:
        assert n['gd_motivo'] in er.MOTIVOS_ALOJAMIENTO.values()
        if n['carga_limita'] is None:
            assert n['carga_kw'] is None and n['carga_motivo'] == er.SIN_CARGA
    for f, d in er.extremos(nodos).items():
        gds = [n['gd_kw'] for n in nodos if n['alimentador'] == f]
        assert d['capacidad_gd_min_kw'] == min(gds) and d['capacidad_gd_max_kw'] == max(gds)
    filas = er.filas_capacidad(SIN_PROYECTO, nodos)
    assert len(filas) == len(nodos) and all(f['caso'] == SIN_PROYECTO for f in filas)
    ruta = escribir_csv(filas, er.COLUMNAS_CAPACIDAD, tmp_path / 'cap.csv')
    assert ruta.read_text(encoding='utf-8-sig').splitlines()[0] == ';'.join(er.COLUMNAS_CAPACIDAD)


def test_resumen_y_margen_de_la_curva_pv():
    """012:RF-52, 012:RF-53 — demanda inicial y crítica, barra y contingencia crítica de la
    ventana de salida (coma decimal) y el margen en kW y en %."""
    lineas = ['info - Initial scalable demand for this case: 2,00 MW (total demand of the system: 2,00 MW).',
              'info - Total critical demand of the scaled loads: 5,40 MW.',
              'info - - Contingency              Critical bus               Critical scalable demand -',
              'info -  Base Case                F1_B3                               5,40',
              'info -  F1_L2                    F1_B2                               4,10']
    r = er.resumen_pv(lineas)
    assert r['inicial_kw'] == pytest.approx(2000) and r['critica_kw'] == pytest.approx(4100)
    assert (r['barra_critica'], r['contingencia_critica']) == ('F1_B2', 'F1_L2')
    assert er.margen_pv(r['inicial_kw'], r['critica_kw']) == pytest.approx({'margen_kw': 2100, 'margen_pct': 105})
    solo = er.resumen_pv(lineas[:4])
    assert solo['contingencia_critica'] is None and solo['critica_kw'] == pytest.approx(5400)


def test_informe_de_bancos_con_su_coste_y_sin_propuesta():
    """012:RF-56, 012:RF-57, 012:RF-66 — cada banco con nodo, kvar, pasos, inversión, vida, tasa
    y coste anual, y el ahorro frente al coste; sin propuesta, se dice por alimentador."""
    rng = random.Random(4)
    libro = [{'potencia_kvar': 150.0, 'inversion': rng.uniform(100, 900), 'vida_anios': 20, 'coste_anual': 50.0}]
    r = er.informe_bancos('F1', [{'nodo': 'B3', 'kvar_paso': 150.0, 'pasos': 2}], libro, 100.0, 70.0, 'M', 0.1)
    (b,) = r['bancos']
    assert (b['kvar'], b['inversion'], b['vida_anios'], b['tasa_descuento'], b['coste_anual']) == (
        300.0, libro[0]['inversion'], 20, 0.1, 50.0)
    assert r['ahorro_anual'] == pytest.approx(30.0) and r['coste_anual'] == 50.0 and r['aviso'] is None
    vacio = er.informe_bancos('F2', [], libro, 100.0, 100.0, 'M', 0.1)
    assert vacio['bancos'] == [] and 'ningún banco' in vacio['aviso']


def test_comprobacion_de_estado():
    """012:RF-60 — demanda cambiada, variación nueva (salvo «Datos de confiabilidad»), hora de
    estudio y etapa de grabación se nombran; sin cambios, nada."""
    antes = {'demandas': {'L1': (0.1, 0.02)}, 'variaciones': ['V'], 'hora': 1, 'etapa': None}
    assert er.cambios_de_estado(antes, antes) == []
    despues = {'demandas': {'L1': (0.2, 0.02)}, 'variaciones': ['V', 'Opri', er.VARIACION_DATOS],
               'hora': 2, 'etapa': 'E'}
    assert er.cambios_de_estado(antes, despues) == [
        'la demanda de L1', 'la variación Opri', 'la hora de estudio del caso', 'la etapa de grabación']


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_filas_de_resultados_con_la_diferencia(semilla, tmp_path):
    """012:RF-59 — una fila por caso, alimentador y estudio, y la diferencia de la confiabilidad;
    el fichero sale igual byte a byte con los mismos resultados en otro orden."""
    rng = random.Random(semilla)
    res = []
    for caso in (SIN_PROYECTO, CON_PROYECTO):
        for f in ('F1', 'F2'):
            res.append({'caso': caso, 'alimentador': f, 'estudio': 'fiabilidad',
                        **er.confiabilidad(f, _leido(rng))})
            for e in ('alojamiento', 'curvas_pv'):
                res.append({'caso': caso, 'alimentador': f, 'estudio': e, 'fiable': True})
    filas = er.filas_red(res)
    assert len(filas) == len(res) + 2 and sum(f['caso'] == DIFERENCIA for f in filas) == 2
    a = escribir_csv(filas, er.COLUMNAS_RED, tmp_path / 'a.csv').read_bytes()
    b = escribir_csv(er.filas_red(list(reversed(res))), er.COLUMNAS_RED, tmp_path / 'b.csv').read_bytes()
    assert a == b
