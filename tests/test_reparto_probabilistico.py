"""Spec 041: reparto probabilístico de las SED escaladas y SED medidas en «3.1 Demandas en bloque»."""
from __future__ import annotations

import random

import pytest

from convertersmartgrid.ajuste_cabecera import (
    AjusteError, Fija, Objetivo, Probabilistico, montecarlo, muestra_de_reparto, percentil,
    probabilistico_de_fijas, probabilistico_del_perfil, reparto_inicial)


def _reparto(n_fijas=6, n_esc=8, pendiente_real=0.3):
    """Fijas con utilización = 0,4 × (kVA/100)^pendiente_real, sin ruido; escaladas por kVA."""
    objetivo = Objetivo(kw=3000.0, kvar=600.0, medidor='M')
    fijas, cargas, kva = {}, {}, {}
    for i in range(1, n_fijas + 1):
        k = 50.0 * 2 ** (i % 5)
        s = f'FX{i}'
        fijas[s] = Fija(s, kw=k * 0.4 * (k / 100.0) ** pendiente_real, kvar=10.0)
        cargas[s], kva[s] = (0.0, 0.0), k
    for i in range(1, n_esc + 1):
        s = f'ES{i}'
        cargas[s], kva[s] = (0.0, 0.0), 25.0 * i
    return reparto_inicial(objetivo, fijas, cargas, kva, fp=0.98)


def test_dispersion_y_pendiente_salen_de_las_fijas():
    """041:RF-2, 041:RF-3 — de la utilización de las fijas frente a su kVA: la pendiente con la
    potencia y, de lo que queda, la dispersión; con menos de cinco fijas, nada."""
    prob = probabilistico_de_fijas(_reparto(pendiente_real=0.3), n=50, semilla=7)
    assert prob.pendiente == pytest.approx(0.3, abs=1e-9) and prob.dispersion == pytest.approx(0.0, abs=1e-9)
    assert prob.n == 50 and prob.semilla == 7 and prob.fuente.startswith('fijas')
    assert probabilistico_de_fijas(_reparto(n_fijas=4)) is None
    # La pendiente no baja de cero: a más potencia, nunca menos probabilidad de ir cargada.
    assert probabilistico_de_fijas(_reparto(pendiente_real=-0.5)).pendiente == 0.0


def test_el_perfil_solo_si_lo_dice_y_bien_escrito():
    """041:RF-3 — sin la sección del perfil, nada; con ella, sus números; mal escrita, error."""
    assert probabilistico_del_perfil({'calibracion': {}}) is None
    prob = probabilistico_del_perfil({'calibracion': {'reparto_probabilistico': {
        'dispersion': 0.35, 'pendiente': 0.2, 'n': 80}}}, semilla=3)
    assert (prob.dispersion, prob.pendiente, prob.n, prob.semilla) == (0.35, 0.2, 80, 3)
    with pytest.raises(AjusteError):
        probabilistico_del_perfil({'calibracion': {'reparto_probabilistico': {'dispersion': -1}}})


def test_cada_muestra_conserva_el_total_y_la_mayor_potencia_va_mas_cargada():
    """041:RF-1, 041:RF-2, 041:RF-7 — cada SED escalada con su factor propio y la misma P base
    total; con la misma semilla, la misma muestra; y de mayor a menor potencia, más utilización
    esperada por kVA en las grandes."""
    rep = _reparto()
    prob = Probabilistico(dispersion=0.3, pendiente=0.4, n=1, semilla=11)
    m1 = muestra_de_reparto(rep, prob, random.Random(11))
    m2 = muestra_de_reparto(rep, prob, random.Random(11))
    assert m1.base == m2.base and m1.fijas == rep.fijas
    assert sum(p for p, _ in m1.base.values()) == pytest.approx(sum(p for p, _ in rep.base.values()))
    for s, (p, q) in m1.base.items():
        assert q / p == pytest.approx(rep.base[s][1] / rep.base[s][0])          # mismo FP
    azar = random.Random(5)
    util = {s: 0.0 for s in rep.base}
    for _ in range(400):
        m = muestra_de_reparto(rep, prob, azar)
        for s, (p, _q) in m.base.items():
            util[s] += p / rep.kva[s] / 400
    assert util['ES8'] > util['ES4'] > util['ES1']


def test_montecarlo_da_percentiles_por_potencia_y_el_p50():
    """041:RF-1, 041:RF-5, 041:RF-6, 041:RF-7 — N repartos cuadrados; por SED, de mayor a menor
    potencia, P05 ≤ P50 ≤ P95 de kW y de carga y la probabilidad de pasar del 100 %; el reparto
    P50 lleva la mediana de cada una; la misma semilla repite el resultado."""
    rep = _reparto()
    prob = Probabilistico(dispersion=0.4, pendiente=0.2, n=60, semilla=21)

    def cuadrar_muestra(m):
        carga = {s: 100.0 * m.a * p / rep.kva[s] * 2.2 for s, (p, _q) in m.base.items()}
        return m, {'carga': carga, 'fuera_de_banda': max(carga.values()) > 150.0}

    resumen, p50 = montecarlo(rep, prob, cuadrar_muestra)
    assert resumen['muestras'] == resumen['validas'] == 60 and resumen['semilla'] == 21
    assert [x['sed'] for x in resumen['sed']] == [f'ES{i}' for i in range(8, 0, -1)]
    for x in resumen['sed']:
        assert x['kw_p05'] <= x['kw_p50'] <= x['kw_p95'] and x['carga_p05'] <= x['carga_p95']
        assert 0.0 <= x['prob_sobrecarga'] <= 1.0
    assert 0.0 <= resumen['prob_tension_fuera'] <= 1.0
    for x in resumen['sed']:
        assert p50.demandas[x['sed']].kw == pytest.approx(x['kw_p50'])
    otra, _ = montecarlo(rep, prob, cuadrar_muestra)
    assert otra == resumen


def test_percentil_interpola():
    """041:RF-6 — percentil lineal, ``None`` sin valores."""
    assert percentil([], 0.5) is None
    assert percentil([1.0, 2.0, 3.0, 4.0], 0.5) == pytest.approx(2.5)
    assert percentil([5.0], 0.95) == 5.0


# ------------------------------------------------------------------ el guion de DIgSILENT
from apoyo import cargar_herramienta  # noqa: E402
from test_ajuste_cabecera_guion import _app, _plan, _sed  # noqa: E402


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_cabecera_pf_041', tools_en_path=True)


def _plan_prob(**kw):
    return {**_plan(kw=300.0, kvar=60.0), 'probabilistico': {
        'n': 12, 'semilla': 99, 'perfil': {'dispersion': 0.3, 'pendiente': 0.2}},
        'banda_tension': [0.95, 1.05], **kw}


def test_el_guion_escribe_el_p50_y_reproduce_con_la_semilla(guion):
    """041:RF-3, 041:RF-4, 041:RF-5, 041:RF-6, 041:RF-7, 041:RF-8 — sin fijas bastantes, con el
    perfil: N repartos cuadrados en el mismo caso, el P50 cuadrado queda escrito y validado, y
    la misma semilla da el mismo resumen."""
    informe, rc = guion.ejecutar(_app(), _plan_prob())
    assert rc == 0, informe
    prob = informe['probabilistico']
    assert prob['fuente'] == 'perfil de empresa' and prob['muestras'] == 12 and prob['escrito'] == 'P50'
    assert prob['validas'] == 12 and prob['semilla'] == 99
    kvas = [x['kva'] for x in prob['sed']]
    assert kvas == sorted(kvas, reverse=True)
    assert informe['cuadrado'] and abs(informe['cabecera']['kw'] - 300.0) <= 0.01 * 300.0
    otro, _ = guion.ejecutar(_app(), _plan_prob())
    assert [(x['sed'], x['kw_p50']) for x in otro['probabilistico']['sed']] == \
        [(x['sed'], x['kw_p50']) for x in prob['sed']]


def test_sin_fijas_ni_perfil_no_se_sortea_y_se_dice(guion):
    """041:RF-3 — sin fijas bastantes ni perfil, el reparto es el determinista y se dice."""
    informe, rc = guion.ejecutar(_app(), {**_plan(kw=300.0, kvar=60.0),
                                          'probabilistico': {'n': 5, 'semilla': 1, 'perfil': None}})
    assert rc == 0 and 'probabilistico' not in informe
    assert any('041:RF-3' in a for a in informe['avisos'])


def test_la_sed_medida_en_31_queda_fija_y_fuera_del_sorteo(guion):
    """041:RF-9 — la SED con su demanda medida en «3.1 Demandas en bloque» entra fija a escala 1
    con esa medida, y no aparece en el reparto probabilístico."""
    informe, rc = guion.ejecutar(_app(), _plan_prob(sed_medidas=[
        {'sed': 'F1_S3', 'hoja': 'F1', 'kw': 42.0, 'kvar': 8.0}]))
    assert rc == 0, informe
    fila = _sed(informe, 'F1_S3')
    assert fila['origen'] != 'escala' and fila['despues']['kw'] == pytest.approx(42.0)
    assert informe['sed_medidas'][0]['sed'] == 'F1_S3'
    assert 'F1_S3' not in {x['sed'] for x in informe['probabilistico']['sed']}
    assert any('041:RF-9' in a for a in informe['avisos'])


# ------------------------------------------------------------------ la web
def test_el_plan_guarda_las_medidas_de_31_y_las_da_al_alimentador(tmp_path):
    """041:RF-9 — el libro de 3.1 se guarda por proyecto y el plan de la calibración lleva solo
    las SED de ese alimentador; sin libro, ninguna."""
    from convertersmartgrid.web import services
    from convertersmartgrid.web.workspace import Workspace

    ws = Workspace(id='w', root=tmp_path / 'ws')
    assert services.sed_medidas_de(ws, 'P', ['SE1']) == []
    services._guardar_sed_medidas(ws, 'P', [
        {'sed': 'SE1', 'hoja': 'A1', 'kw': 10.0, 'kvar': 2.0, 'fp': 0.98},
        {'sed': 'SE9', 'hoja': 'B1', 'kw': 5.0, 'kvar': 1.0, 'fp': 0.98}])
    assert services.sed_medidas_de(ws, 'P', ['se1', 'SE2']) == [
        {'sed': 'SE1', 'hoja': 'A1', 'kw': 10.0, 'kvar': 2.0}]
    assert services.sed_medidas_de(ws, 'OTRO', ['SE1']) == []
