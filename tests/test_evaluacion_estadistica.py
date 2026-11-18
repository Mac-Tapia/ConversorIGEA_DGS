"""044:RF-12: la estadística común de la evaluación final, cada contraste contra un valor de referencia publicado.

Los valores fijos de este fichero se sacaron de las bibliotecas o artículos que se citan en cada prueba, con el guion
versionado ``tests/fixtures/estadistica/referencias.py`` (statsmodels 0.15.0, krippendorff 0.8.1, pingouin 0.5.5,
instalados aparte con ``pip --target`` y no en ``.venv``; la carpeta se le pasa con ``--libs``). Sus salidas están al lado,
en ``referencias.json`` y ``referencias_hac.json``, y una prueba las contrasta con el módulo. Lo que está en scipy o
scikit-learn, que sí están en ``.venv``, se compara en vivo.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import pytest
from scipy import stats

from convertersmartgrid.dominio.evaluacion_harness import estadistica as es

#: Las salidas versionadas del guion de referencia.
REFERENCIAS = Path(__file__).resolve().parent / 'fixtures' / 'estadistica'

# Serie determinista de las pruebas de la varianza HAC (la misma del guion de referencia).
SERIE_HAC = [round(math.sin(t / 3) + 0.5 * math.cos(1.7 * t) + t / 60, 6) for t in range(60)]

# Bland y Altman, «Statistical methods for assessing agreement between two methods of clinical measurement», Lancet
# 1986; 327(8476):307-310, tabla 1: primera lectura de PEFR (l/min) con el medidor Wright grande y con el mini Wright.
PEFR_GRANDE = [494, 395, 516, 434, 476, 557, 413, 442, 650, 433, 417, 656, 267, 478, 178, 423, 427]
PEFR_MINI = [512, 430, 520, 428, 500, 600, 364, 380, 658, 445, 432, 626, 260, 477, 259, 350, 451]


def test_wilson_reproduce_newcombe_y_statsmodels():
    """044:RF-12: Wilson de 81/263 es 0,2553-0,3662 (Newcombe, Stat Med 17:857, 1998, ej. del método 3) y statsmodels."""
    inf, sup = es.intervalo_wilson(81, 263)
    assert inf == pytest.approx(0.2552885198782742, abs=1e-9)        # statsmodels proportion_confint(method='wilson')
    assert sup == pytest.approx(0.36620957698280004, abs=1e-9)
    assert es.intervalo_wilson(0, 10) == pytest.approx((0.0, 0.27753279986288926), abs=1e-9)
    assert es.intervalo_wilson(0, 0) == (0.0, 1.0)


def test_wilson_del_asistente_es_el_comun():
    """044:RF-12: el límite de Wilson de la 069:RF-37 sale del módulo común, sin una copia propia."""
    from convertersmartgrid.aplicacion.asistente import destilacion_integral as di
    assert di.limite_inferior_wilson(1373, 1400) == es.intervalo_wilson(1373, 1400, z=1.96)[0]
    assert di.limite_inferior_wilson(0, 0) == 0.


def test_holm_como_statsmodels():
    """044:RF-12: Holm (Scand J Stat 6:65, 1979) da lo mismo que statsmodels multipletests(method='holm')."""
    p = {'a': 0.01, 'b': 0.04, 'c': 0.03, 'd': 0.005, 'e': 0.2}
    ajustado = es.ajustar_holm(p)
    assert [ajustado[k] for k in 'abcde'] == pytest.approx([0.04, 0.09, 0.09, 0.025, 0.2])
    from convertersmartgrid.aplicacion.asistente import embeddings
    assert embeddings.ajustar_holm is es.ajustar_holm


def test_mcnemar_exacta_como_binomtest():
    """044:RF-12: McNemar exacto (069:RF-38) es la binomial de las discordantes, igual que scipy.stats.binomtest."""
    for b, c in ((9, 2), (5, 5), (0, 4), (12, 3)):
        assert es.mcnemar_exacta(b, c, alternativa='mayor') == pytest.approx(
            stats.binomtest(b, b + c, 0.5, alternative='greater').pvalue)
        assert es.mcnemar_exacta(b, c) == pytest.approx(stats.binomtest(b, b + c, 0.5).pvalue)
    assert es.mcnemar_exacta(0, 0) == 1.0


def test_hac_de_newey_west_como_statsmodels():
    """044:RF-12: varianza HAC de la media con Bartlett (Newey y West, Econometrica 55:703, 1987) y uniforme, statsmodels."""
    ref = {('bartlett', 0): 0.010400718427040174, ('bartlett', 1): 0.017637552208631314,
           ('bartlett', 3): 0.027951966993979296, ('uniforme', 1): 0.024874385990222455,
           ('uniforme', 3): 0.04329920413158862}
    for (nucleo, retardos), valor in ref.items():
        assert es.varianza_hac_media(SERIE_HAC, retardos, nucleo=nucleo) == pytest.approx(valor, rel=1e-9)


def test_diebold_mariano_hln_con_h1_es_el_t_pareado():
    """044:RF-12: con h = 1, DM con la corrección de Harvey, Leybourne y Newbold (IJF 13:281, 1997) es el t pareado de scipy."""
    rnd = random.Random(3)
    e1 = [rnd.gauss(0, 1) for _ in range(40)]
    e2 = [rnd.gauss(0, 1.2) for _ in range(40)]
    la, lb = [x * x for x in e1], [x * x for x in e2]
    dm = es.diebold_mariano(la, lb, horizonte=1)
    t = stats.ttest_rel(la, lb)
    assert dm['estadistico'] == pytest.approx(t.statistic, rel=1e-9)
    assert dm['p'] == pytest.approx(t.pvalue, rel=1e-9)
    assert dm['gl'] == 39 and dm['n'] == 40


def test_diebold_mariano_hln_con_h_mayor():
    """044:RF-12: con h > 1, DM usa la varianza HAC de h-1 retardos y el factor HLN, con t de n-1 grados de libertad."""
    cero = [0.0] * len(SERIE_HAC)
    h, n = 4, len(SERIE_HAC)
    dm = es.diebold_mariano(SERIE_HAC, cero, horizonte=h)
    media = sum(SERIE_HAC) / n
    var = 0.04329920413158862                      # statsmodels, núcleo uniforme con h-1 = 3 retardos
    esperado = media / math.sqrt(var) * math.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    assert dm['estadistico'] == pytest.approx(esperado, rel=1e-9)
    assert dm['p'] == pytest.approx(2 * stats.t.sf(abs(esperado), n - 1), rel=1e-9)
    assert dm['nucleo'] == 'uniforme'
    nw = es.diebold_mariano(SERIE_HAC, cero, horizonte=h, nucleo='bartlett')
    assert nw['estadistico'] == pytest.approx(
        media / math.sqrt(0.027951966993979296) * math.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n), rel=1e-9)


def test_diebold_mariano_rechaza_series_desiguales_o_cortas():
    """044:RF-12: DM compara las mismas fechas; series de distinto largo o de menos de 3 puntos no se contrastan."""
    with pytest.raises(ValueError):
        es.diebold_mariano([1, 2, 3], [1, 2])
    with pytest.raises(ValueError):
        es.diebold_mariano([1, 2], [2, 1])


def test_wilcoxon_y_biserial_como_r_y_pingouin():
    """044:RF-12: Wilcoxon pareado de Hollander y Wolfe (1973, p. 29; ejemplo de wilcox.test de R: V = 40, p = 0,03906).

    La correlación biserial de rangos es (T+ - T-)/(T+ + T-) (Kerby, Compr Psychol 3:11, 2014); pingouin 0.5.5 da 0,7778.
    """
    x = [1.83, 0.50, 1.62, 2.48, 1.68, 1.88, 1.55, 3.06, 1.30]
    y = [0.878, 0.647, 0.598, 2.05, 1.06, 1.29, 1.06, 3.14, 1.29]
    r = es.wilcoxon_pareado(x, y)
    assert r['t_mas'] == 40 and r['t_menos'] == 5
    assert r['p'] == pytest.approx(0.0390625)
    assert r['p'] == pytest.approx(stats.wilcoxon(x, y).pvalue)
    assert r['rango_biserial'] == pytest.approx(0.7777777777777777)
    assert es.wilcoxon_pareado(y, x)['rango_biserial'] == pytest.approx(-0.7777777777777777)


def test_tost_pareado_como_statsmodels():
    """044:RF-12: TOST pareado (Schuirmann, J Pharmacokinet Biopharm 15:657, 1987; Lakens 2017) como statsmodels ttost_paired."""
    x = [5.1, 4.9, 5.3, 5.0, 5.2, 4.8, 5.1, 5.0, 4.9, 5.2]
    y = [5.0, 5.0, 5.2, 5.1, 5.1, 4.9, 5.0, 5.1, 5.0, 5.1]
    r = es.tost_pareado(x, y, -0.2, 0.2)
    assert r['t_inf'] == pytest.approx(6.0) and r['t_sup'] == pytest.approx(-6.0)
    assert r['p'] == pytest.approx(0.00010124966103381999, rel=1e-6)
    assert r['equivalente'] is True
    assert es.tost_pareado(x, y, -0.001, 0.001)['equivalente'] is False


def test_bland_altman_reproduce_el_articulo_de_1986():
    """044:RF-12: con k = 2, sesgo -2,1, límites -79,7 y 75,5 y sus IC (Bland y Altman, Lancet 1986, PEFR)."""
    r = es.bland_altman(PEFR_GRANDE, PEFR_MINI, k=2.0)
    assert r['n'] == 17
    assert r['sesgo'] == pytest.approx(-2.1, abs=0.06)
    assert r['de'] == pytest.approx(38.8, abs=0.06)
    assert r['lim_inf'] == pytest.approx(-79.7, abs=0.1)
    assert r['lim_sup'] == pytest.approx(75.5, abs=0.1)
    # El artículo redondea los errores estándar (9,4 y 16,3) y t = 2,12 antes de multiplicar.
    assert r['ic95_sesgo'] == pytest.approx([-22.0, 17.8], abs=0.15)
    assert r['ic95_lim_inf'] == pytest.approx([-114.3, -45.1], abs=0.3)
    assert r['ic95_lim_sup'] == pytest.approx([40.9, 110.1], abs=0.3)


def test_kappa_de_cohen_como_sklearn_y_statsmodels():
    """044:RF-12: kappa de Cohen (Educ Psychol Meas 20:37, 1960) como sklearn cohen_kappa_score; tabla 20/5/10/15 = 0,40."""
    from sklearn.metrics import cohen_kappa_score
    a = ['s'] * 20 + ['s'] * 5 + ['n'] * 10 + ['n'] * 15
    b = ['s'] * 20 + ['n'] * 5 + ['s'] * 10 + ['n'] * 15
    assert es.kappa_cohen(a, b) == pytest.approx(0.4)                   # statsmodels cohens_kappa
    rnd = random.Random(5)
    x = [rnd.choice('abc') for _ in range(80)]
    y = [v if rnd.random() < .6 else rnd.choice('abc') for v in x]
    assert es.kappa_cohen(x, y) == pytest.approx(cohen_kappa_score(x, y))


def test_alfa_de_krippendorff_reproduce_su_ejemplo():
    """044:RF-12: el ejemplo de Krippendorff («Computing Krippendorff's Alpha-Reliability», 2011): nominal 0,743.

    Cuatro codificadores y doce unidades con huecos; el paquete krippendorff 0.8.1 da 0,743421 (nominal) y 0,849107 (intervalo).
    """
    datos = [[1, 2, 3, 3, 2, 1, 4, 1, 2, None, None, None],
             [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, None, 3],
             [None, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, None],
             [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, None]]
    assert es.alfa_krippendorff(datos) == pytest.approx(0.743421052631579)
    assert es.alfa_krippendorff(datos, nivel='intervalo') == pytest.approx(0.8491071428571428)


def test_bootstrap_agrupado_remuestrea_grupos_enteros():
    """044:RF-12: el bootstrap agrupado (Field y Welsh, JRSS B 69:369, 2007) remuestrea grupos, no filas sueltas."""
    valores = [1.0, 1.0, 1.0, 1.0, 5.0, 5.0, 5.0, 5.0]
    grupos = ['a', 'a', 'a', 'a', 'b', 'b', 'b', 'b']
    r = es.bootstrap_agrupado(valores, grupos, remuestras=500, semilla=1)
    assert r['grupos'] == 2 and r['n'] == 8 and r['valor'] == pytest.approx(3.0)
    # Con dos grupos, cada remuestra tiene la media de a, la de b o la mitad: las filas no se separan de su grupo.
    assert r['ic95'][0] == pytest.approx(1.0) and r['ic95'][1] == pytest.approx(5.0)
    assert es.bootstrap_agrupado(valores, grupos, remuestras=500, semilla=1) == r
    assert es.bootstrap_agrupado([1.0, 2.0], ['a', 'a'])['status'] == 'BLOQUEADO_POR_DATOS'


def test_bootstrap_agrupado_con_un_dato_por_grupo_cubre_como_scipy():
    """044:RF-12: con un dato por grupo es el bootstrap percentil ordinario; su IC se acerca al de scipy.stats.bootstrap."""
    rnd = random.Random(11)
    x = [rnd.gauss(10, 2) for _ in range(60)]
    r = es.bootstrap_agrupado(x, list(range(60)), remuestras=4000, semilla=2)
    ref = stats.bootstrap((x,), lambda v: sum(v) / len(v), vectorized=False, method='percentile',
                          n_resamples=4000, random_state=2).confidence_interval
    assert r['ic95'][0] == pytest.approx(ref.low, abs=0.12)
    assert r['ic95'][1] == pytest.approx(ref.high, abs=0.12)


def test_las_referencias_fijas_salen_del_guion_versionado():
    """044:RF-12: los valores fijos tienen su procedencia en el repositorio, no en una carpeta de la máquina del desarrollo.

    El guion ``tests/fixtures/estadistica/referencias.py`` y sus salidas están versionados; el módulo da lo mismo que esas
    salidas, de modo que cualquiera puede repetir el cálculo y comparar.
    """
    guion = REFERENCIAS / 'referencias.py'
    assert guion.is_file(), f'falta el guion de referencia {guion}'
    ref = json.loads((REFERENCIAS / 'referencias.json').read_text(encoding='utf-8'))
    hac = json.loads((REFERENCIAS / 'referencias_hac.json').read_text(encoding='utf-8'))
    assert ref['versiones']['statsmodels'] == hac['statsmodels'] == '0.15.0'
    assert es.intervalo_wilson(81, 263) == pytest.approx(tuple(ref['wilson_81_263']), abs=1e-9)
    assert es.intervalo_wilson(0, 10) == pytest.approx(tuple(ref['wilson_0_10']), abs=1e-9)
    ajustado = es.ajustar_holm(dict(zip('abcde', (0.01, 0.04, 0.03, 0.005, 0.2))))
    assert [ajustado[k] for k in 'abcde'] == pytest.approx(ref['holm'])
    x = [5.1, 4.9, 5.3, 5.0, 5.2, 4.8, 5.1, 5.0, 4.9, 5.2]
    y = [5.0, 5.0, 5.2, 5.1, 5.1, 4.9, 5.0, 5.1, 5.0, 5.1]
    tost = es.tost_pareado(x, y, -0.2, 0.2)
    assert tost['p'] == pytest.approx(ref['tost']['p'], rel=1e-6)
    assert (tost['t_inf'], tost['t_sup']) == pytest.approx((ref['tost']['t_inf'], ref['tost']['t_sup']))
    a = ['s'] * 25 + ['n'] * 25
    b = ['s'] * 20 + ['n'] * 5 + ['s'] * 10 + ['n'] * 15
    assert es.kappa_cohen(a, b) == pytest.approx(ref['kappa_tabla']['kappa'])
    datos = [[1, 2, 3, 3, 2, 1, 4, 1, 2, None, None, None],
             [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, None, 3],
             [None, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, None],
             [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, None]]
    assert es.alfa_krippendorff(datos) == pytest.approx(ref['krippendorff_nominal'])
    assert es.alfa_krippendorff(datos, nivel='intervalo') == pytest.approx(ref['krippendorff_intervalo'])
    w = es.wilcoxon_pareado([1.83, 0.50, 1.62, 2.48, 1.68, 1.88, 1.55, 3.06, 1.30],
                            [0.878, 0.647, 0.598, 2.05, 1.06, 1.29, 1.06, 3.14, 1.29])
    assert w['t_menos'] == ref['wilcoxon']['W']
    assert w['p'] == pytest.approx(ref['wilcoxon']['p'])
    assert w['rango_biserial'] == pytest.approx(ref['wilcoxon']['rbc'])
    assert sum(SERIE_HAC) / len(SERIE_HAC) == pytest.approx(hac['media'], rel=1e-12)
    for nucleo, nombre in (('bartlett', 'bartlett'), ('uniforme', 'uniform')):
        for retardos in (0, 1, 3):
            assert es.varianza_hac_media(SERIE_HAC, retardos, nucleo=nucleo) == pytest.approx(
                hac[f'{nombre}_L{retardos}'], rel=1e-9), (nucleo, retardos)
