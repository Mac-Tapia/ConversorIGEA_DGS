"""108 T24 (108:RF-21): zonificación por densidad de carga del art. 22 de la Guía del VNR (RCD 232-2017-OS/CD).

Dos concesiones sintéticas (universal): coordenadas UTM inventadas, demandas en kW.
"""
from pathlib import Path

import pytest

from convertersmartgrid.registro_normativo import cargar_registro
from convertersmartgrid.vad.vnr_guia import SedZonificable as S
from convertersmartgrid.vad.vnr_guia import (
    VnrGuiaError,
    demanda_de_alumbrado,
    zona_de_densidad,
    zonificar,
)

REGISTRO = cargar_registro(Path(__file__).resolve().parents[1] / 'config' / 'normativa' / 'rcd_232_2017.json')
ZONAS = REGISTRO.regla('vnr.zonas.densidad').regla.valor


@pytest.mark.parametrize('densidad, zona', [(4.0, 'Muy Alta'), (3.99, 'Alta 1'), (2.5, 'Alta 1'), (2.49, 'Alta 2'),
                                            (1.5, 'Alta 2'), (1.49, 'Media'), (0.25, 'Media'), (0.249, 'Baja')])
def test_108_rf21_limites_de_la_tabla_1(densidad, zona):
    assert zona_de_densidad(densidad, ZONAS) == zona


def test_108_rf21_cuadricula_de_1000_m_con_4_mw_queda_muy_alta_sin_subdividir():
    seds = [S(f'A{i}', 300_100 + 100 * i, 8_600_100, 1000.0) for i in range(4)]
    z = zonificar(seds, REGISTRO)
    (c,) = z.cuadriculas
    assert (c.lado_m, c.zona, c.x0, c.y0) == (1000, 'Muy Alta', 300_000, 8_600_000)
    assert z.citas['vnr.cuadricula.lados_m'] == 'RCD 232-2017-OS/CD, art. 22.2'


def test_108_rf21_muy_alta_en_500_y_el_resto_en_250_con_sus_zonas():
    seds = [S('M1', 500_100, 9_100_100, 3000.0),        # 3 MW en un cuarto de km²: 12 MW/km², Muy Alta en 500 m
            S('B1', 500_900, 9_100_900, 200.0),         # 0,2 MW en 0,0625 km²: 3,2 MW/km², Alta 1 en 250 m
            S('B2', 500_600, 9_100_700, 10.0)]          # 0,16 MW/km²: Baja
    z = zonificar(seds, REGISTRO)
    por_sed = {s: (c.lado_m, c.zona) for c in z.cuadriculas for s in c.seds}
    assert por_sed['M1'] == (500, 'Muy Alta')
    assert por_sed['B1'][0] == 250 and por_sed['B2'][0] == 250
    assert {c.zona_calculada or c.zona for c in z.cuadriculas if c.lado_m == 250} == {'Alta 1', 'Baja'}


def test_108_rf21_densidad_cero_eliminada_y_fuera_de_toda_cuadricula_es_baja():
    z = zonificar([S('C1', 300_100, 8_600_100, 0.0), S('C2', 310_100, 8_610_100, 100.0)], REGISTRO)
    assert [s for c in z.cuadriculas for s in c.seds] == ['C2']
    assert z.zona_en(300_100, 8_600_100) == 'Baja'  # art. 23.2
    assert z.zona_en(-1, -1) == 'Baja'


def test_108_rf21_mapa_de_bt_sin_las_sed_de_uso_industrial():
    seds = [S('I1', 300_100, 8_600_100, 5000.0, industrial=True), S('R1', 300_150, 8_600_150, 50.0)]
    mt, bt = zonificar(seds, REGISTRO, mapa='MT'), zonificar(seds, REGISTRO, mapa='BT')
    assert mt.cuadriculas[0].zona == 'Muy Alta' and 'I1' in mt.cuadriculas[0].seds
    assert all('I1' not in c.seds for c in bt.cuadriculas) and bt.cuadriculas


def _anillo(centro_kw: float, vecinas_kw: list[float]):
    """Una cuadrícula de 250 m en el centro y ocho vecinas alrededor (cada SED en el centro de su cuadrícula)."""
    seds, k = [S('X', 400_125 + 250, 8_700_125 + 250, centro_kw)], 0
    for dx in (0, 250, 500):
        for dy in (0, 250, 500):
            if (dx, dy) != (250, 250):
                seds.append(S(f'V{k}', 400_125 + dx, 8_700_125 + dy, vecinas_kw[k]))
                k += 1
    return seds


def test_108_rf21_la_aislada_adopta_la_zona_predominante_de_sus_vecinas():
    z = zonificar(_anillo(200.0, [10.0] * 8), REGISTRO)  # centro Alta 1 rodeada de Baja
    centro = next(c for c in z.cuadriculas if 'X' in c.seds)
    assert (centro.zona, centro.zona_calculada) == ('Baja', 'Alta 1')


def test_108_rf21_sin_predominante_conserva_la_suya_y_si_coincide_con_una_vecina_tambien():
    empate = zonificar(_anillo(200.0, [10.0] * 4 + [50.0] * 4), REGISTRO)  # 4 Baja y 4 Media: empate
    assert next(c for c in empate.cuadriculas if 'X' in c.seds).zona == 'Alta 1'
    con_par = zonificar(_anillo(200.0, [200.0] + [10.0] * 7), REGISTRO)
    assert next(c for c in con_par.cuadriculas if 'X' in c.seds).zona == 'Alta 1'


def test_108_rf21_alumbrado_con_fc_0_5_y_coincidencia_1_y_se_suma_a_su_sed():
    assert demanda_de_alumbrado(4380.0, REGISTRO) == pytest.approx(1.0)
    s = S('A', 0, 0, 10.0, alumbrado_kw=demanda_de_alumbrado(43800.0, REGISTRO))
    assert s.demanda_kw == pytest.approx(20.0)
    with pytest.raises(VnrGuiaError):
        demanda_de_alumbrado(-1.0, REGISTRO)


def test_108_rf21_otra_concesion_en_otro_huso_da_el_mismo_resultado_por_densidad():
    a = zonificar([S('A', 300_100, 8_600_100, 4000.0)], REGISTRO)
    b = zonificar([S('B', 700_900, 9_400_900, 4000.0)], REGISTRO)
    assert a.resumen() == b.resumen() == {'Muy Alta': 1}
