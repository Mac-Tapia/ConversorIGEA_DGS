"""Spec 108 T4 — caracterización de la carga del anexo 4 desde la medición del conversor (108:RF-4).

Curvas sintéticas sorteadas de forma escalonada (base y pico en horas conocidas), cuyos factores se conocen de
antemano en forma cerrada; nada de una empresa real.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from convertersmartgrid.aplicacion.demanda_medida import Registro
from convertersmartgrid.dominio.registro_normativo import cargar_registro
from convertersmartgrid.aplicacion.vad.caracterizacion import caracterizar

RAIZ = Path(__file__).resolve().parents[1]
REGISTRO = RAIZ / 'config' / 'vad'
DIA = datetime(2031, 3, 4)  # un día útil cualquiera; el año no es de ninguna empresa


def _escalon(base, pico, desde, hasta, q=0.0):
    """Registros cada 15 min de un día: ``pico`` de ``desde`` a ``hasta`` (horas), ``base`` el resto."""
    out = []
    for k in range(96):
        t = DIA + timedelta(minutes=15 * k)
        kw = pico if desde <= t.hour < hasta else base
        out.append(Registro(fecha=t, valores={'kw': kw, 'kvar': q * kw}))
    return out


@pytest.mark.parametrize('semilla', (1, 7, 23))
def test_factores_conocidos_de_antemano(semilla):
    """108:RF-4 — factor de carga, coincidencia en punta y fuera de punta, y pérdidas, en forma cerrada."""
    rnd = random.Random(semilla)
    pa, ba, pb, bb = (rnd.uniform(50, 200), rnd.uniform(5, 40), rnd.uniform(50, 200), rnd.uniform(5, 40))
    # A pico de 18 a 20 h y B de 20 a 23 h: los dos dentro de la punta (18-23 h), sin solaparse.
    registros = {'sed-a': _escalon(ba, pa, 18, 20), 'sed-b': _escalon(bb, pb, 20, 23)}
    car = caracterizar(registros, {'sed-a': 'MT', 'sed-b': 'MT'}, cargar_registro(REGISTRO))
    assert not car.huecos and car.conforme, (car.huecos, car.motivos)
    fca = (2 * pa + 22 * ba) / (24 * pa)
    assert car.por_elemento['sed-a'].factor_carga == pytest.approx(fca)
    assert car.por_elemento['sed-a'].factor_perdidas == pytest.approx((2 + 22 * (ba / pa) ** 2) / 24)
    assert car.por_elemento['sed-a'].factor_perdidas_empirico == pytest.approx(0.3 * fca + 0.7 * fca ** 2)
    g = car.grupos['MT']
    assert g.fcpp == pytest.approx(max(pa + bb, ba + pb) / (pa + pb))
    assert g.fcfp == pytest.approx(1.0)  # fuera de punta las dos están en su base a la vez
    media = (2 * pa + 22 * ba + 3 * pb + 21 * bb) / 24
    assert g.factor_carga == pytest.approx(media / max(pa + bb, ba + pb))
    assert max(v for _, v in g.curva_pu) == pytest.approx(1.0)
    assert len(g.curva_pu) == 96


def test_mt_y_bt_por_separado():
    """108:RF-4 — las curvas MT y BT se caracterizan por separado, sin mezclarse."""
    registros = {'mt-1': _escalon(10, 100, 18, 23), 'bt-1': _escalon(1, 4, 8, 12), 'bt-2': _escalon(2, 3, 8, 12)}
    car = caracterizar(registros, {'mt-1': 'MT', 'bt-1': 'BT', 'bt-2': 'BT'}, cargar_registro(REGISTRO))
    assert set(car.grupos) == {'MT', 'BT'}
    assert car.grupos['MT'].elementos == ('mt-1',)
    assert car.grupos['BT'].elementos == ('bt-1', 'bt-2')
    assert car.grupos['BT'].fcfp == pytest.approx(1.0)


def test_sed_sin_medicion_se_nombra_sin_curva():
    """108:RF-4 — una SED sin medición se nombra; el anexo 4 transcrito no prevé darle una curva."""
    car = caracterizar({'sed-a': _escalon(5, 50, 18, 20)}, {'sed-a': 'MT', 'sed-sin': 'MT'},
                       cargar_registro(REGISTRO))
    assert 'sed-sin' not in car.por_elemento
    assert car.grupos['MT'].elementos == ('sed-a',)
    assert any('sed-sin' in h and 'sin medición' in h for h in car.huecos), car.huecos


def test_cada_factor_lleva_su_regla_citada():
    """108:RF-4, 108:RF-9 — el resultado dice de qué regla del anexo 4 sale cada factor, con su huella."""
    car = caracterizar({'x': _escalon(1, 2, 18, 19)}, {'x': 'BT'}, cargar_registro(REGISTRO))
    assert {'vad.anexo4.factor_carga', 'vad.anexo4.factor_coincidencia_punta', 'vad.anexo4.horas_punta',
            'vad.anexo4.factor_perdidas_integral', 'vad.anexo4.factor_perdidas_empirico'} <= set(car.reglas)
    assert all(len(h) == 64 for h in car.reglas.values())


def test_registros_sin_kw_no_cuentan_como_cero():
    """108:RF-4 — un registro sin kW no es un cero: queda fuera y se dice cuántos."""
    regs = _escalon(5, 50, 18, 20)
    regs[3] = Registro(fecha=regs[3].fecha, valores={'kw': None})
    car = caracterizar({'a': regs}, {'a': 'MT'}, cargar_registro(REGISTRO))
    assert car.por_elemento['a'].fuera == 1
    assert car.por_elemento['a'].factor_carga == pytest.approx((8 * 50 + 87 * 5) / 95 / 50)
