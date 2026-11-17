"""Spec 107, RF-20 (T32) — lo que la Norma Tarifas fija para el PIT sale del registro normativo real y no de la
entrada: los años de la programación (art. 5.9.4) y el horizonte de las alternativas (art. 3.14), el factor de
potencia de las barras de MT (art. 12.1.8.c), el N-1 solo donde la norma lo exige (art. 12.3.1, RCD 018-2018) y las
reglas de la comparación (5.9.3, 11.3, 17.2 y 24.2), citadas en el expediente. Red y demanda sintéticas."""
from __future__ import annotations

import copy
import importlib
import importlib.util
import json
import math
from pathlib import Path

from test_pit_armado import _armar, _caso
from test_pit_formatos import NORMATIVA

from convertersmartgrid.registro_normativo import cargar_registro

CLAVES_DIAGNOSTICO = ('pit.anios_programacion_demanda', 'pit.factor_potencia_barras_mt', 'pit.n1_demanda_min_mw')
CLAVES_COMPARACION = ('pit.criterio_alternativas', 'pit.costo_total', 'pit.coym_metodo', 'pit.tasa_actualizacion_fuente')


def _norma():
    assert importlib.util.find_spec('convertersmartgrid.pit.norma') is not None, 'falta el módulo pit.norma'
    return importlib.import_module('convertersmartgrid.pit.norma')


def _diagnostico(r) -> dict:
    return json.loads(Path(r['salidas']['diagnostico']).read_text(encoding='utf-8'))


def _proyeccion_con_q(proyeccion, factor):
    """La misma P con otra Q por alimentador: ``factor`` × P."""
    out = copy.deepcopy(proyeccion)
    for f in out:
        f['q_kvar'] = round(f['p_kw'] * factor, 1)
    return out


def _proyeccion_hasta(proyeccion, anios):
    """La demanda del primer año repetida en los años que faltan, con el crecimiento de un 3 % al año."""
    primero = min(f['anio_calendario'] for f in proyeccion)
    filas = [f for f in proyeccion if f['anio_calendario'] == primero]
    return [{**f, 'anio_calendario': a, 'p_kw': round(f['p_kw'] * 1.03 ** (a - primero), 1),
             'q_kvar': round(f['q_kvar'] * 1.03 ** (a - primero), 1)} for a in anios for f in filas]


def test_107_rf20_los_anios_del_diagnostico_son_los_de_la_programacion(tmp_path):
    """107:RF-20 — pedidos siete años seguidos, se diagnostican los de la programación (1 a 5 del horizonte): el 6 y
    el 7 no se diagnostican y se avisa, y también los años 8 y 10 que faltan."""
    x = _caso(tmp_path)
    a0 = x['caso']['anios'][0]
    pedidos = list(range(a0, a0 + 7))
    r = _armar(x, anios=pedidos, proyeccion=_proyeccion_hasta(x['caso']['proyeccion'], pedidos))
    d = _diagnostico(r)
    diagnosticados = sorted([a['anio'] for a in d['anios']] + d['sin_demanda'])
    assert diagnosticados == list(range(a0, a0 + 5))
    avisos = ' '.join(d['avisos'])
    assert '5.9.4' in avisos and str([a0 + 5, a0 + 6]) in avisos and str([a0 + 7, a0 + 9]) in avisos


def test_107_rf20_la_q_de_las_barras_de_mt_sale_del_factor_de_la_norma(tmp_path):
    """107:RF-20 — con dos proyecciones de igual P y distinta Q, el diagnóstico es el mismo: la Q de cada barra de MT
    sale de su P con el factor de potencia del registro (0,95), no de la entrada."""
    x = _caso(tmp_path)
    anios = x['caso']['anios'][:2]
    sin_q = _diagnostico(_armar(x, anios=anios, proyeccion=_proyeccion_con_q(x['caso']['proyeccion'], 0.0)))
    (tmp_path / 'otra').mkdir()
    x2 = _caso(tmp_path / 'otra')
    con_q = _diagnostico(_armar(x2, anios=anios, proyeccion=_proyeccion_con_q(x2['caso']['proyeccion'], 1.0)))
    assert sin_q['anios'] == con_q['anios']
    fp = _norma().factor_potencia(x['registro'])
    assert fp == 0.95 and math.isclose(_norma().q_con_factor(10.0, fp), 10.0 * math.tan(math.acos(0.95)))


def test_107_rf20_el_n1_solo_donde_la_norma_lo_exige(tmp_path):
    """107:RF-20 — ningún elemento de la red sintética atiende más de 30 MW en el caso base: no se corre su N-1 y el
    diagnóstico lo dice con el artículo; sin la regla en el registro, el N-1 se corre en todos, como antes."""
    x = _caso(tmp_path)
    d = _diagnostico(_armar(x))
    assert d['anios'] and all(a['contingencias'] == [] for a in d['anios'])
    assert any('12.3.1' in v and 'N-1' in v for v in d['avisos'])
    norma = _norma()
    flujos = {'L1': (45.0, 5.0), 'L2': (-31.0, 2.0), 'T1': (12.0, 1.0)}
    exigen, aviso = norma.elementos_con_n1(x['registro'], flujos, ['L1', 'L2', 'T1', 'T9'])
    assert exigen == ['L1', 'L2'] and '30' in aviso and '2 quedan fuera' in aviso
    todos, aviso = norma.elementos_con_n1(None, flujos, ['L1', 'T1'])
    assert todos == ['L1', 'T1'] and aviso == ''


def test_107_rf20_el_expediente_cita_las_reglas_de_la_norma(tmp_path):
    """107:RF-20 — las reglas de los años, el factor de potencia, el N-1 y las de la comparación (criterio, costo
    total, COyM y fuente de la tasa) se leen del registro y figuran en las reglas aplicadas del expediente."""
    x = _caso(tmp_path)
    r = _armar(x)
    reglas = {g['clave']: g for g in json.loads(Path(r['salidas']['reglas']).read_text(encoding='utf-8'))}
    assert set(CLAVES_DIAGNOSTICO + CLAVES_COMPARACION) <= set(reglas)
    assert reglas['pit.factor_potencia_barras_mt']['valor'] == 0.95
    assert reglas['pit.criterio_alternativas']['valor'] == _norma().CRITERIO_DEL_CODIGO


def test_107_rf20_horizonte_y_criterio_desde_el_registro_real():
    """107:RF-20 — con el registro real: el horizonte de las alternativas deja fuera lo que pasa de 10 años; las cuatro
    reglas de la comparación están y el criterio es el que aplica el código, sin avisos."""
    norma = _norma()
    registro = cargar_registro(NORMATIVA)
    dentro, avisos = norma.anios_de_alternativas(registro, [2030, 2035, 2039, 2040, 2045])
    assert dentro == [2030, 2035, 2039] and '3.14' in avisos[0] and '[2040, 2045]' in avisos[0]
    citadas, avisos = norma.reglas_citadas(registro)
    assert citadas == list(CLAVES_COMPARACION) and avisos == []
    usados, avisos = norma.anios_de_programacion(registro, [2030, 2031, 2032, 2033, 2034, 2037, 2039])
    assert usados == [2030, 2031, 2032, 2033, 2034, 2037, 2039] and avisos == []
    sin, avisos = norma.anios_de_programacion(None, [2031, 2030])
    assert sin == [2030, 2031] and avisos == []
