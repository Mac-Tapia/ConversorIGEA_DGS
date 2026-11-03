"""Spec 072: los quince formatos con cada hueco nombrado, y la evaluación con y sin proyecto."""
from __future__ import annotations

import pytest
from openpyxl import load_workbook

from convertersmartgrid import pide_economia as ec
from convertersmartgrid.estudio_planeamiento import estudio_de
from convertersmartgrid.formatos_pide import (
    MOTIVO_DEL_CAMPO,
    MOTIVO_DEL_FORMATO,
    filas_de_calidad,
    filas_de_metrados,
    filas_de_obras,
    filas_de_perdidas,
    filas_de_proyeccion,
    formatos_del_estudio,
    huecos_de,
)
from convertersmartgrid.pide import FORMATOS, escribir_formatos
from convertersmartgrid.proyeccion_mercado import SerieMercado

HORIZONTE = {'ciclo_anios': 4, 'largo_plazo': [4, 8], 'detalle_pide': [4]}
PLAN = {'tasa_regulada': 0.12, 'vida_util_anios': 30, 'horizonte_anios': 20}


def _obra(codigo='AL01', ci=1000.0, descartada=False, alimentador='F1', kw=100.0):
    return {'codigo': codigo, 'anio': 4, 'alternativa': 'bancos', 'rubro': 'calidad', 'alimentador': alimentador,
            'elemento': 'B9', 'causa': 'caida_de_tension', 'denominacion': None, 'ci': ci, 'kw_nuevos': kw,
            'energia_kwh': kw * 4000, 'indicadores': {'costo_kw': 10.0}, 'privada': None, 'descartada': descartada,
            'sobredimensionada': False, 'regulada': {'anualidad': ci * 0.12, 'costo_anual': ci * 0.13}}


def test_cada_formato_y_cada_campo_tiene_su_motivo():
    """072:RF-16 — ningún hueco posible se queda sin decir por qué."""
    assert set(MOTIVO_DEL_FORMATO) == set(FORMATOS)
    assert {c for campos in FORMATOS.values() for c in campos} <= set(MOTIVO_DEL_CAMPO)


def test_un_formato_vacio_y_un_campo_vacio_se_nombran():
    """072:RF-16 — el formato sin filas con su motivo; el campo, con cuántas filas le faltan."""
    filas = {'F06 Calidad suministro': [['SET', 'F1', 1.0, None, 3, '']]}
    huecos = huecos_de(filas)
    assert {'formato': 'F01 Proyección', 'campo': None, 'filas': 0, 'motivo': MOTIVO_DEL_FORMATO['F01 Proyección']} in huecos
    de_f06 = {h['campo']: h['filas'] for h in huecos if h['formato'] == 'F06 Calidad suministro'}
    assert de_f06 == {'SAIDI': 1, 'D': 1}
    # Un cero medido es un dato, no un hueco.
    assert not [h for h in huecos_de({'F06 Calidad suministro': [['S', 'F1', 0.0, 0.0, 0, 0]]})
                if h['formato'] == 'F06 Calidad suministro']


def test_una_obra_sin_costo_no_vale_cero():
    """072:RF-16 — sin CAPEX, inversión y costo anual quedan vacíos, no en 0."""
    filas = filas_de_obras([_obra(ci=0.0)], [])
    assert filas['F12 Propuesta proyecto'][0][5] is None and filas['F12 Propuesta proyecto'][0][8] is None
    assert filas['F09 Evaluación económica'][0][4] is None and filas['F15 Ficha económica'][0][3] is None
    assert filas['F10 Propuesta empresa'][0][5] is None
    assert any(h['campo'] == 'Inversión US$' for h in huecos_de(filas))


def test_el_alimentador_no_se_escribe_como_sistema():
    """072:RF-14 — F12 va por sistema eléctrico; sin estructura queda el hueco."""
    con = filas_de_obras([_obra()], [], {'F1': 'SE1'})
    assert con['F12 Propuesta proyecto'][0][0] == 'SE1' and con['F11 Propuesta sistema'][0][0] == 'SE1'
    assert filas_de_obras([_obra()], [])['F12 Propuesta proyecto'][0][0] is None


def test_la_cartera_deja_fuera_lo_descartado_pero_el_estudio_lo_conserva():
    """072:RF-14 — F07 a F09 conservan las alternativas rechazadas; F10 a F15, solo la cartera."""
    filas = filas_de_obras([_obra(), _obra('AL02', descartada=True)], [], {'F1': 'SE1'})
    assert [f[2] for f in filas['F07 Alternativas estudio']] == ['AL01', 'AL02']
    assert [f[3] for f in filas['F12 Propuesta proyecto']] == ['AL01']
    assert filas['F10 Propuesta empresa'] == [[4, 'calidad', None, 100.0, 400000.0, 1000.0, 120.0, None, 130.0]]
    assert filas['F11 Propuesta sistema'] == [['SE1', 4, 'calidad', 1000.0, 120.0, None, 130.0]]
    assert len(filas['F11 Propuesta sistema'][0]) == len(FORMATOS['F11 Propuesta sistema'])
    assert [f[0] for f in filas['F14 Ficha técnica']] == ['AL01']
    assert [f[2] for f in filas['F15 Ficha económica']] == ['Inversión', 'Anualidad']


def test_cada_fila_tiene_las_columnas_de_su_formato():
    """072:RF-13 — una columna de más o de menos corre los valores bajo otro encabezado."""
    filas = filas_de_obras([_obra()], [{'cabeceras_kw': {'F1': 1000.0}, 'vm_min': 0.9}], {'F1': 'SE1'}, {'F1': 'SET A'})
    for nombre, datos in filas.items():
        assert all(len(f) == len(FORMATOS[nombre]) for f in datos), nombre


def test_la_tension_de_toda_la_red_no_se_atribuye_a_cada_alimentador():
    """072:RF-16 — vm_min es global: con uno solo vale; con dos, sería el mismo valor falso en ambos."""
    uno = filas_de_obras([], [{'cabeceras_kw': {'F1': 2000.0}, 'vm_min': 0.95}], {}, {'F1': 'SET A'})
    assert uno['F03 Tensión MT'] == [['SET A', 'F1', None, 2.0, None, None, None, 5.0]]
    dos = filas_de_obras([], [{'cabeceras_kw': {'F1': 1000.0, 'F2': 1000.0}, 'vm_min': 0.95}])
    assert [f[7] for f in dos['F03 Tensión MT']] == [None, None]


def test_f01_proyecta_hasta_el_ultimo_anio_del_estudio():
    """072:RF-10 — historia y proyección; la demanda solo con factor de carga, como en los entregables."""
    s = SerieMercado('SE1', 'Sistema Uno', 'ST2', {2023: 100.0, 2024: 110.0, 2025: 121.0})
    filas = filas_de_proyeccion([s], estudio_de(2027, HORIZONTE), metodo='tasa_de_un_anio', factor_carga=0.5)
    assert [f[1] for f in filas] == list(range(2023, 2035))
    por_anio = {f[1]: f for f in filas}
    assert por_anio[2026][2] == pytest.approx(133.1) and por_anio[2026][4] == pytest.approx(10.0)
    assert por_anio[2026][3] == pytest.approx(133.1 / (8760 * 0.5)) and por_anio[2025][3] is None
    assert por_anio[2023][4] is None
    sin = filas_de_proyeccion([s], estudio_de(2027, HORIZONTE), metodo='tasa_media', factor_carga=None)
    assert all(f[3] is None for f in sin)
    # Sin estudio no hay horizonte: queda la historia, sin inventar años.
    assert [f[1] for f in filas_de_proyeccion([s], None, metodo='tasa_media', factor_carga=None)] == [2023, 2024, 2025]


def test_f02_suma_por_sistema_y_nombra_lo_que_no_tiene_codigo():
    """072:RF-15 — los km sin código no se reparten entre los demás."""
    m = {'por_codigo': {'AA035G': {'km': 2.0}, 'DEFAULT': {'km': 1.0}}, 'sin_codigo': ['T9'], 'km_sin_codigo': 0.5}
    filas, huecos = filas_de_metrados([('SE1', m), ('SE1', m)])
    assert ['SE1', 'G', 'AA035G', 'km', 4.0] in filas and ['SE1', None, 'DEFAULT', 'km', 2.0] in filas
    assert huecos[0]['filas'] == 1 and '0.50 km' in huecos[0]['motivo']


def test_f05_y_f06_solo_con_lo_medido():
    """072:RF-16 — pérdidas e índices medidos; sin ellos, sin filas."""
    assert filas_de_perdidas([{'perdidas_kw': 50.0, 'cabeceras_kw': {'F1': 1000.0}}], 'SE1')[0][4] == pytest.approx(5.0)
    assert filas_de_perdidas([{'cabeceras_kw': {'F1': 1000.0}}], 'SE1') == []
    assert filas_de_calidad(None) == []
    assert filas_de_calidad({'F1': {'SAIFI': 2.0}}, {'F1': 'SET A'}) == [['SET A', 'F1', 2.0, None, None, None]]


def test_el_estudio_entero_cabe_en_el_libro_y_sus_huecos_quedan_escritos(tmp_path):
    """072:RF-13 / 072:RF-14 / 072:RF-16 — todo formato tiene filas o motivo, y el libro lo dice."""
    s = SerieMercado('SE1', 'Sistema Uno', 'ST2', {2023: 100.0, 2024: 110.0, 2025: 121.0})
    r = formatos_del_estudio([_obra()], [{'cabeceras_kw': {'F1': 1000.0}, 'vm_min': 0.9, 'perdidas_kw': 40.0}],
                             estudio=estudio_de(2027, HORIZONTE), series=[s], factor_carga=0.5,
                             sistema_de={'F1': 'SE1'}, centro_de={'F1': 'SET A'})
    sin_filas = {h['formato'] for h in r['huecos'] if h['campo'] is None}
    assert sin_filas == {'F02 Metrados', 'F04 Tensión BT', 'F06 Calidad suministro'}
    for nombre in FORMATOS:
        assert r['filas'].get(nombre) or nombre in sin_filas
    assert r['filas']['F05 Pérdidas'][0][0] == 'SE1'
    libro = load_workbook(escribir_formatos(tmp_path / 'f.xlsx', r['filas'], r['huecos']))
    assert len(libro.sheetnames) == 16 and libro.sheetnames[-1] == 'Huecos'
    assert libro['F04 Tensión BT'].cell(2, 1).value == MOTIVO_DEL_FORMATO['F04 Tensión BT']
    assert libro['Huecos'].max_row == len(r['huecos']) + 1


def test_con_y_sin_proyecto_mide_el_ahorro_de_perdidas():
    """072:RF-14 — el beneficio es la diferencia entre los dos casos del mismo año, nunca un supuesto."""
    r = ec.evaluar_con_y_sin({0: 1000.0}, {0: 100.0, 4: 140.0}, {0: 100.0, 4: 100.0}, PLAN, factor_carga=0.5, precio_compra_kwh=0.1)
    por_kw = 8760 * (0.3 * 0.5 + 0.7 * 0.25) * 0.1
    assert r['ahorro_kw'][1] == pytest.approx(10.0) and r['ahorro_kw'][4] == pytest.approx(40.0)
    assert r['ahorro_kw'][20] == pytest.approx(40.0)
    assert r['flujos'][0] == -1000.0 and r['flujos'][4] == pytest.approx(40.0 * por_kw)
    assert r['van'] == pytest.approx(ec.van(r['flujos'], 0.12)) and r['tir'] == pytest.approx(ec.tir(r['flujos']))
    assert any('se mantiene' in a for a in r['avisos'])


def test_la_obra_se_paga_en_su_anio_y_solo_cuentan_las_aplicadas():
    """072:RF-14 — la inversión del año 04 va en el año 04; una obra sin aplicar no entra en el costo."""
    r = ec.evaluar_con_y_sin({4: 1000.0}, {0: 100.0}, {0: 100.0}, PLAN, factor_carga=0.5, precio_compra_kwh=0.1)
    assert r['flujos'][0] == 0.0 and r['flujos'][4] == pytest.approx(-1000.0)
    anios = [{'anio': 0, 'perdidas_kw': 100.0, 'con_proyecto': {'perdidas_kw': 90.0}}]
    obras = [{'anio': 4, 'ci': 1000.0, 'variacion_autonoma': 'V1'}, {'anio': 4, 'ci': 9000.0}]
    r = ec.con_y_sin_de_las_aplicadas(obras, anios, PLAN, factor_carga=0.5, precio_compra_kwh=0.1)
    assert r['flujos'][4] == pytest.approx(10 * 8760 * (0.3 * 0.5 + 0.7 * 0.25) * 0.1 - 1000.0)
    assert 'costo' in ec.con_y_sin_de_las_aplicadas(obras[1:], anios, PLAN, factor_carga=0.5, precio_compra_kwh=0.1)['hueco']


@pytest.mark.parametrize('ci, con, fc, palabra', [({}, {0: 90.0}, 0.5, 'costo'), ({0: 1000.0}, {}, 0.5, 'Con proyecto'),
                                                  ({0: 1000.0}, {0: 90.0}, None, 'factor de carga')])
def test_con_y_sin_proyecto_sin_datos_lo_dice(ci, con, fc, palabra):
    """072:RF-16 — sin costo, sin el caso con obras o sin factor de carga, no hay resultado inventado."""
    r = ec.evaluar_con_y_sin(ci, {0: 100.0}, con, PLAN, factor_carga=fc, precio_compra_kwh=0.1)
    assert palabra in r['hueco'] and 'van' not in r
