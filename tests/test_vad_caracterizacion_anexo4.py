"""Spec 108 T4 — caracterización del Anexo 4: lo que la prueba de tests/test_vad_caracterizacion.py no cubre (108:RF-4).

Pérdidas con la corriente cuando el factor de potencia varía, máximas del FCPP dentro de la punta, resultado por
opción tarifaria, por las siete agrupaciones y por sistema o sector, el hueco de la BT5I, la curva del día útil
representativo y el aviso cuando la RM de horas de punta vigente no coincide con el TdR. Curvas sintéticas; nada de
una empresa real.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from convertersmartgrid.demanda_medida import Registro
from convertersmartgrid.registro_normativo import cargar_registro
from convertersmartgrid.vad.caracterizacion import caracterizar

RAIZ = Path(__file__).resolve().parents[1]
VAD = RAIZ / 'config' / 'vad'
NORMATIVA = RAIZ / 'config' / 'normativa'
DIA = datetime(2031, 3, 4)  # martes; el año no es de ninguna empresa


def _escalon(base, pico, desde, hasta, dia=DIA, q=None):
    """96 registros de un día: ``pico`` de ``desde`` a ``hasta`` (horas), ``base`` el resto; ``q(t, kw)`` da los kvar."""
    out = []
    for k in range(96):
        t = dia + timedelta(minutes=15 * k)
        kw = pico if desde <= t.hour < hasta else base
        valores = {'kw': kw} if q is None else {'kw': kw, 'kvar': q(t, kw)}
        out.append(Registro(fecha=t, valores=valores))
    return out


def test_perdidas_con_la_corriente_cuando_el_fp_varia():
    """108:RF-4 — el Anexo integra I²: con kvar se usa √(P²+Q²), y con un FP variable no da lo mismo que con solo kW."""
    def q(t, kw):
        return 0.0 if 18 <= t.hour < 20 else kw  # FP 1 en el pico, 0,707 fuera de él
    car = caracterizar({'a': _escalon(20, 100, 18, 20, q=q)}, {'a': 'MT'}, cargar_registro(VAD))
    a = car.por_elemento['a'] if 'a' in car.por_elemento else None
    assert a is not None, car.huecos
    con_corriente = (8 * 100 ** 2 + 88 * 2 * 20 ** 2) / 96 / 100 ** 2
    solo_kw = (8 * 100 ** 2 + 88 * 20 ** 2) / 96 / 100 ** 2
    assert a.base_perdidas == 'corriente'
    assert a.factor_perdidas == pytest.approx(con_corriente)
    assert a.factor_perdidas != pytest.approx(solo_kw)
    sin = caracterizar({'a': _escalon(20, 100, 18, 20)}, {'a': 'MT'}, cargar_registro(VAD))
    assert 'a' in sin.por_elemento, sin.huecos
    assert sin.por_elemento['a'].base_perdidas == 'potencia_activa'
    assert sin.por_elemento['a'].factor_perdidas == pytest.approx(solo_kw)
    assert any('factor de potencia constante' in x and 'a' in x for x in sin.avisos), sin.avisos


def test_fcpp_con_las_maximas_dentro_de_la_punta():
    """108:RF-4 — FCPP: la coincidente y las máximas de cada uno, las dos dentro de 18:00-23:00 (Anexo 4-13)."""
    registros = {'a': _escalon(10, 300, 10, 12), 'b': _escalon(10, 100, 19, 21)}
    car = caracterizar(registros, {'a': 'BT', 'b': 'BT'}, cargar_registro(VAD))
    assert 'BT' in car.grupos, car.huecos
    assert car.grupos['BT'].fcpp == pytest.approx((10 + 100) / (10 + 100))  # con las máximas del día: 110/400
    assert car.grupos['BT'].fcfp == pytest.approx((300 + 10) / (300 + 10))
    regla = cargar_registro(VAD).regla('vad.anexo4.factor_coincidencia_punta').regla
    assert 'Anexo 4-13' in regla.interpretacion and '18:00 a 23:00' in regla.interpretacion


def _clasificados():
    registros = {n: _escalon(5, 50, 18, 20) for n in ('a', 'b', 'c', 'd')}
    clases = {'a': {'opcion': 'MT2', 'sistema': 'S1', 'sector': '2'},
              'b': {'opcion': 'MT3P', 'sistema': 'S1', 'sector': '3'},
              'c': {'opcion': 'MT4FP', 'sistema': 'S2', 'sector': '2'},
              'd': {'nivel': 'BT', 'opcion': 'BT5B', 'sistema': 'S2', 'sector': '2'}}
    return caracterizar(registros, clases, cargar_registro(VAD))


def test_por_opcion_tarifaria_y_por_agrupacion():
    """108:RF-4 — el resultado sale por opción tarifaria y por las agrupaciones del Anexo 4, cada una de un nivel."""
    car = _clasificados()
    assert set(car.por_opcion) == {'MT2', 'MT3P', 'MT4FP', 'BT5B'}, car.huecos
    assert car.por_opcion['MT3P'].elementos == ('b',)
    assert car.por_opcion['BT5B'].nivel == 'BT'
    assert 'NHUBTPP y NHUBTFP' in car.por_opcion['BT5B'].no_aplica
    assert 'NHUBT' in car.por_opcion['BT5B'].no_calculados
    assert {k: g.elementos for k, g in car.por_agrupacion.items()} == {
        'MT1+MT2+MT3P+MT3FP+MT4P+MT4FP': ('a', 'b', 'c'), 'MT2+MT3P+MT3FP+MT4P+MT4FP': ('a', 'b', 'c'),
        'MT2+MT3P+MT4P': ('a', 'b'), 'MT2+MT3FP+MT4FP': ('a', 'c')}
    assert car.grupos['MT'].elementos == ('a', 'b', 'c') and car.grupos['BT'].elementos == ('d',)
    assert not car.huecos


def test_por_sistema_y_por_sector_tipico():
    """108:RF-4 — si la clasificación trae el sistema eléctrico o el sector típico, el resultado sale también así."""
    car = _clasificados()
    assert set(car.por_sistema) == {'S1', 'S2'}
    assert car.por_sistema['S1'].grupos['MT'].elementos == ('a', 'b')
    assert set(car.por_sistema['S2'].grupos) == {'MT', 'BT'}
    assert car.por_sistema['S2'].por_opcion['MT4FP'].elementos == ('c',)
    assert set(car.por_sector) == {'2', '3'}
    assert car.por_sector['2'].por_agrupacion['MT2+MT3FP+MT4FP'].elementos == ('a', 'c')


def test_clasificacion_que_no_encaja_es_un_hueco():
    """108:RF-4 — una opción que no está en el cuadro, o de otro nivel que el declarado, se nombra; no se adivina."""
    registros = {n: _escalon(5, 50, 18, 20) for n in ('x', 'y', 'z')}
    clases = {'x': {'nivel': 'BT', 'opcion': 'MT2'}, 'y': {'nivel': 'MT', 'opcion': 'ZZ9'}, 'z': 'AT'}
    car = caracterizar(registros, clases, cargar_registro(VAD))
    assert any('x' in h and 'MT2' in h for h in car.huecos), car.huecos
    assert any('y' in h and 'ZZ9' in h for h in car.huecos), car.huecos
    assert any(h.startswith('z:') for h in car.huecos), car.huecos
    assert set(car.por_elemento) == {'y'} and set(car.grupos) == {'MT'}
    assert not car.conforme


def test_bt5i_horas_de_uso_son_un_hueco_nombrado():
    """108:RF-4 — NHUBTIP, NHUBTIB y NHUBTIM (BT5I) están definidos sin fórmula ni bloques: hueco, ningún valor."""
    car = caracterizar({'i': _escalon(1, 3, 18, 20)}, {'i': {'opcion': 'BT5I'}}, cargar_registro(VAD))
    assert any(all(s in h for s in ('BT5I', 'NHUBTIP', 'NHUBTIB', 'NHUBTIM', 'Anexo 4-12')) for h in car.huecos), \
        car.huecos
    assert not car.conforme
    assert 'BT5I' in car.por_opcion and car.por_opcion['BT5I'].factor_carga is not None


def test_sed_con_todos_los_registros_vacios_es_sin_medicion():
    """108:RF-4 — si ningún registro trae kW, la SED no tiene medición: se nombra y no recibe curva."""
    vacios = [Registro(fecha=r.fecha, valores={'kw': None}) for r in _escalon(1, 2, 18, 20)]
    car = caracterizar({'v': vacios, 'a': _escalon(1, 2, 18, 20)}, {'v': 'BT', 'a': 'BT'}, cargar_registro(VAD))
    assert any(h.startswith('v:') and 'sin medición' in h for h in car.huecos), car.huecos
    assert 'v' not in car.por_elemento and 'BT' in car.grupos and car.grupos['BT'].elementos == ('a',)


def test_curva_por_unidad_del_dia_util_representativo():
    """108:RF-4 — la curva por unidad (base: su máxima) es la del día útil de demanda media más cercana a la media."""
    lunes = datetime(2031, 3, 3)
    regs = (_escalon(10, 20, 18, 20, dia=lunes) + _escalon(20, 40, 18, 20, dia=lunes + timedelta(days=1))
            + _escalon(60, 120, 18, 20, dia=lunes + timedelta(days=2))
            + _escalon(90, 900, 18, 20, dia=lunes + timedelta(days=6)))  # el domingo no es día útil
    car = caracterizar({'a': regs}, {'a': 'MT'}, cargar_registro(VAD))
    assert 'a' in car.por_elemento, car.huecos
    a = car.por_elemento['a']
    assert a.dia_tipico == '2031-03-04'
    curva = dict(a.curva_pu)
    assert len(curva) == 96 and max(curva.values()) == pytest.approx(1.0)
    assert curva['18:00'] == pytest.approx(1.0) and curva['00:00'] == pytest.approx(0.5)


@pytest.mark.parametrize('dia, esperado', [
    (datetime(2025, 5, 30), 'RM 153-2021-MINEM/DM'),  # antes del 2025-06-01: la RM vigente da 17:00-23:00
    (datetime(2025, 6, 2), None),                    # después: la RM 189-2025 da 18:00-23:00, como el TdR
    (datetime(2029, 6, 4), 'ninguna RM'),            # sin RM vigente en el registro
])
def test_horas_de_punta_del_tdr_con_aviso_de_la_rm(dia, esperado):
    """108:RF-4 (condición de 28) — la punta es la del TdR (Anexo 4-13) aunque la RM vigente en la fecha de la medición
    dé otra; entonces avisa con las dos ventanas y sus citas, y también si no hay ninguna RM vigente."""
    registros = {'a': _escalon(10, 300, 17, 18, dia=dia), 'b': _escalon(10, 100, 20, 21, dia=dia)}
    car = caracterizar(registros, {'a': 'MT', 'b': 'MT'}, cargar_registro(VAD, NORMATIVA))
    avisos = [x for x in car.avisos if x.startswith('Horas de punta')]
    if esperado is None:
        assert not avisos, avisos
    else:
        assert len(avisos) == 1 and esperado in avisos[0], car.avisos
        assert '18:00-23:00' in avisos[0] and 'Anexo 4-13' in avisos[0], avisos
        if esperado.startswith('RM'):
            assert '17:00-23:00' in avisos[0] and 'Artículo 1' in avisos[0], avisos
    assert 'MT' in car.grupos, car.huecos
    # Con 17:00-23:00 el pico de «a» (17-18 h) entraría en la punta y el FCPP bajaría a 310/400.
    assert car.grupos['MT'].fcpp == pytest.approx(1.0)
