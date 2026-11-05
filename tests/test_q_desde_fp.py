"""Spec 088: la Q negativa desde el factor de potencia."""
from __future__ import annotations

import math
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from openpyxl import Workbook

from convertersmartgrid.demanda_medida import Cabecera

RAIZ = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 3, 6, 18, 0)
TITULOS = ['Local Time', 'kVA tot mean', 'kVAR tot mean', 'kW tot mean', 'PF lag mean', 'PF lead mean']


def _libro(tmp_path: Path, filas: list[tuple], hoja: str = 'MED1') -> Path:
    """Filas ``(kW, kVAR de la columna, PF lag, PF lead, kVA)``, cada 15 minutos."""
    wb = Workbook()
    ws = wb.active
    ws.title = hoja
    ws.append(TITULOS)
    for i, (kw, kvar, lag, lead, *kva) in enumerate(filas):
        ws.append([T0 + timedelta(minutes=15 * i), kva[0] if kva else None, kvar, kw, lag, lead])
    ruta = tmp_path / 'cabecera.xlsx'
    wb.save(ruta)
    return ruta


def _maxima(tmp_path: Path, filas: list[tuple]):
    return Cabecera([_libro(tmp_path, filas)]).maxima('MED1')


def _q(kw: float, fp_pct: float) -> float:
    return abs(kw) * math.tan(math.acos(fp_pct / 100))


def test_capacitivo_da_q_negativa(tmp_path):
    """088:RF-1, 088:RF-2 — kVAR negativo y FP capacitivo: |kW|·tan(acos(FP)), negativa."""
    r = _maxima(tmp_path, [(500.0, -1.0, None, 80.0), (900.0, -2.0, None, 95.0)])
    assert r.kvar == pytest.approx(-_q(900.0, 95.0))


def test_inductivo_da_q_positiva(tmp_path):
    """088:RF-3 — kVAR negativo y FP inductivo: la Q pasa a positiva."""
    r = _maxima(tmp_path, [(900.0, -2.0, 90.0, None), (500.0, -1.0, None, 80.0)])
    assert r.kvar == pytest.approx(_q(900.0, 90.0))


def test_medidor_en_sentido_contrario_conserva_q_con_el_signo_de_p(tmp_path):
    """088:RF-3 — con kW negativo e inductivo, Q lleva el signo de P: invertida, queda positiva."""
    r = _maxima(tmp_path, [(-900.0, -2.0, 90.0, None), (-500.0, -1.0, 80.0, None)])
    assert r.curva[0][2] == pytest.approx(-_q(-900.0, 90.0))


def test_capacitivo_con_kw_negativo_lleva_el_signo_contrario(tmp_path):
    """088:RF-2 — con kW negativo y capacitivo, Q lleva el signo contrario al de P."""
    r = _maxima(tmp_path, [(-900.0, -2.0, None, 90.0), (-500.0, -1.0, None, 80.0)])
    assert r.curva[0][2] == pytest.approx(_q(-900.0, 90.0))


def test_sin_lead_ni_lag_usa_kw_entre_kva(tmp_path):
    """088:RF-4 — sin FP de adelanto o atraso, FP = |kW|/kVA y el signo negativo se conserva."""
    r = _maxima(tmp_path, [(800.0, -5.0, None, None, 1000.0), (100.0, -1.0, None, None, 200.0)])
    assert r.kvar == pytest.approx(-600.0)


@pytest.mark.parametrize('fila', [(900.0, -7.0, None, None), (900.0, -7.0, None, 0.0), (900.0, -7.0, None, None, 500.0)])
def test_sin_fp_calculable_conserva_la_columna(tmp_path, fila):
    """088:RF-5, 088:RF-6 — sin FP mayor que 0, ni kVA coherente, sigue el kVAR y se cuenta en los avisos."""
    r = _maxima(tmp_path, [fila, (500.0, -1.0, None, 80.0)])
    assert r.kvar == -7.0
    assert any('1 registro' in a and 'kVAR' in a for a in r.avisos)


def test_kw_cero_conserva_la_columna(tmp_path):
    """088:RF-1, 088:RF-5 — con kW cero el FP no dice nada: no se borra la Q que dio el medidor."""
    r = _maxima(tmp_path, [(0.0, -7.0, None, 95.0), (10.0, 3.0, None, None)])
    assert r.curva[0][2] == -7.0


def test_q_positiva_sigue_con_su_columna(tmp_path):
    """088:RF-7 — sin kVAR negativo, la Q es la de la columna, sin avisos ni rótulo nuevos."""
    r = _maxima(tmp_path, [(900.0, 7.0, None, 95.0), (800.0, 0.0, 95.0, None)])
    assert [q for _t, _p, q in r.curva] == [7.0, 0.0]
    assert r.columnas['kvar'] == 'kVAR tot mean'
    assert not r.avisos


def test_el_kw_no_cambia(tmp_path):
    """088:RF-8 — la regla solo toca la Q: máxima y curva conservan su kW."""
    r = _maxima(tmp_path, [(500.0, -1.0, None, 80.0), (900.0, -2.0, None, 95.0)])
    assert r.kw == 900.0
    assert [p for _t, p, _q2 in r.curva] == [500.0, 900.0]


def test_maxima_y_curva_llevan_la_q_calculada(tmp_path):
    """088:RF-9 — máxima y curva dan la misma Q calculada, registro a registro."""
    r = _maxima(tmp_path, [(500.0, -1.0, None, 80.0), (900.0, -2.0, None, 95.0)])
    assert [q for _t, _p, q in r.curva] == pytest.approx([-_q(500.0, 80.0), -_q(900.0, 95.0)])
    assert r.kvar == pytest.approx(r.curva[1][2])


def test_las_columnas_dicen_que_la_q_es_calculada(tmp_path):
    """088:RF-10 — el resultado no atribuye a la columna una Q que no salió de ella."""
    assert 'calculad' in _maxima(tmp_path, [(900.0, -2.0, None, 95.0)] * 3).columnas['kvar']


def test_sin_medidores_de_una_empresa_en_el_codigo():
    """088:RF-11 — la regla vale para cualquier medidor: el código no nombra ninguno."""
    for modulo in ('demanda_medida.py',):
        assert not re.search('CHB2T1|L6616|L2130', (RAIZ / 'src/convertersmartgrid' / modulo).read_text(encoding='utf-8'))


def test_medicion_real():
    """088:RF-1, 088:RF-2, 088:RF-8 — CHB2T1 real: capacitivo, el kW igual y la Q cerca de lo medido."""
    carpeta = os.environ.get('CSG_DEMANDA_DIR')
    if not carpeta:
        pytest.skip('CSG_DEMANDA_DIR no definida')
    libros = sorted(Path(carpeta, '2.-medicioncabecera/2026').glob('*Pisco*'))
    if not libros:
        pytest.skip('sin el libro de cabecera de ese sistema en CSG_DEMANDA_DIR')
    r = Cabecera(libros).maxima('CHB2T1')
    assert r.kw == pytest.approx(1884.458, abs=.01)
    assert r.kvar == pytest.approx(-220.34, abs=.01)
    assert 'calculad' in r.columnas['kvar']


def test_q_calculada_imposible_conserva_la_columna(tmp_path):
    """088:RF-12 — un FP medio bajo en un intervalo con maniobra da más Q que kVA: eso no es físico."""
    r = _maxima(tmp_path, [(900.0, -7.0, None, 10.0, 1000.0), (500.0, -1.0, None, 80.0, 700.0)])
    assert r.kvar == -7.0
    assert any('1 registro' in a for a in r.avisos)
