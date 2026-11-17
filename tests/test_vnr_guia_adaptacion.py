"""108 T25 (108:RF-22): adaptación de las instalaciones por sector típico (arts. 23 a 44) con las tablas del Anexo 6 de
la Guía del VNR (RCD 232-2017-OS/CD). Tramos y SED sintéticos; registro y Anexo 6 reales del repositorio."""
from pathlib import Path

import pytest

from convertersmartgrid.registro_normativo import cargar_registro
from convertersmartgrid.vad.vnr_guia import (
    SedZonificable,
    Tramo,
    VnrGuiaError,
    adaptar_equipo,
    adaptar_luminaria,
    adaptar_red_bt,
    adaptar_red_mt,
    adaptar_sed,
    adaptar_tramo_mt,
    cargar_anexo6,
    es_corrosivo,
    kva_adaptado,
    porciones_por_zona,
    zonificar,
)

RAIZ = Path(__file__).resolve().parents[1]
REG = cargar_registro(RAIZ / 'config' / 'normativa' / 'rcd_232_2017.json')
A6 = cargar_anexo6(RAIZ / 'config' / 'vnr' / 'anexo6_equivalencias.json')


def _tabla(n):
    return next(t for t in A6['tablas'] if t['tabla'] == n)


def _celda(n, origen, mm2, columna):
    """El valor del Anexo 6 buscado a mano en el JSON, sin el motor."""
    t = _tabla(n)
    fila = next(f for f in t['filas'] if f['origen'] == origen and f['seccion_mm2'] == mm2)
    return fila['valores'][[c.casefold() for c in t['columnas']].index(columna.casefold())]


def T(codigo='T1', material='CU Protegido', mm2=50, largo=100.0, sub=False, zona='Media', corr=False, **kw):
    return Tramo(codigo, material, mm2, largo, sub, zona, corr, **kw)


# ---------------------------------------------------------------- MT, sector urbano de alta densidad (art. 23)

def test_108_rf22_mt_alta_aerea_en_muy_alta_pasa_a_na2xsy():
    a = adaptar_tramo_mt(T(zona='Muy Alta'), 'urbano_alta', REG, A6)
    assert (a.material, a.seccion_mm2) == ('NA2XSY', _celda(4, 'CU Protegido', 50, 'NA2XSY'))
    assert a.regla == 'RCD 232-2017-OS/CD, art. 23'


@pytest.mark.parametrize('corrosivo, destino', [(True, 'CU Desnudo'), (False, 'AA Desnudo')])
def test_108_rf22_mt_alta_aerea_protegida_pasa_a_desnudo_segun_ambiente(corrosivo, destino):
    a = adaptar_tramo_mt(T(zona='Media', corr=corrosivo), 'urbano_alta', REG, A6)
    assert (a.material, a.seccion_mm2, a.subterranea) == (destino, _celda(4, 'CU Protegido', 50, destino), False)


def test_108_rf22_mt_alta_autoportante_de_cobre_pasa_a_aluminio_en_alta_y_se_mantiene_en_media():
    alta = adaptar_tramo_mt(T(material='CU Autoportante', mm2=50, zona='Alta 1'), 'urbano_alta', REG, A6)
    assert alta.material.casefold() == 'al autoportante'
    assert alta.seccion_mm2 == _celda(4, 'CU Autoportante', 50, 'Al Autoportante')
    media = adaptar_tramo_mt(T(material='CU Autoportante', mm2=50, zona='Media'), 'urbano_alta', REG, A6)
    assert (media.material, media.seccion_mm2) == ('CU Autoportante', 50)


def test_108_rf22_mt_alta_subterranea_en_media_menor_de_95_pasa_a_aerea_y_mayor_queda_na2xsy():
    mm2 = next(f['seccion_mm2'] for f in _tabla(5)['filas'] if f['origen'] == 'N2XSY'
               and isinstance(f['valores'][3], int) and f['valores'][3] < 95)  # NA2XSY equivalente < 95 mm2
    delgado = adaptar_tramo_mt(T(material='N2XSY', mm2=mm2, sub=True, zona='Baja'), 'urbano_alta', REG, A6)
    assert (delgado.material, delgado.subterranea) == ('AA Desnudo', False)
    grueso = adaptar_tramo_mt(T(material='N2XSY', mm2=240, sub=True, zona='Baja'), 'urbano_alta', REG, A6)
    assert grueso.subterranea and grueso.seccion_mm2 >= 95
    alta2 = adaptar_tramo_mt(T(material='N2XSY', mm2=mm2, sub=True, zona='Alta 2'), 'urbano_alta', REG, A6)
    assert (alta2.material, alta2.subterranea) == ('NA2XSY', True)


def test_108_rf22_mt_de_5_8_kv_se_adapta_a_10_kv_por_potencia_constante_antes_del_cambio_de_tecnologia():
    a = adaptar_tramo_mt(T(material='AA Desnudo', mm2=185, kv=5.8, zona='Media'), 'urbano_alta', REG, A6)
    assert (a.material, a.seccion_mm2) == ('AA Desnudo', _tabla(1)['filas'][10]['valores'][1])
    assert _tabla(1)['filas'][10]['seccion_mm2'] == 185


# ---------------------------------------------------------------- MT, otros sectores (arts. 28, 33, 38, 43)

def test_108_rf22_mt_media_baja_tope_del_14_por_ciento_empieza_por_las_secciones_mas_delgadas():
    tramos = [T('A', 'AA Desnudo', 70, 700.0, zona='Media'),
              T('S1', 'N2XSY', 120, 100.0, sub=True), T('S2', 'N2XSY', 35, 100.0, sub=True),
              T('S3', 'N2XSY', 70, 100.0, sub=True)]
    a = {x.existente.codigo: x for x in adaptar_red_mt(tramos, 'urbano_media_baja', REG, A6)}
    assert not a['S2'].subterranea and not a['S3'].subterranea and a['S1'].subterranea  # 300 → 100 m (≤ 14 %)
    assert a['S2'].material == 'AA Desnudo' and a['S2'].regla.endswith('(28.7)')
    assert a['S1'].material == 'NA2XSY'


@pytest.mark.parametrize('sector', ['urbano_rural', 'rural_ser'])
def test_108_rf22_mt_urbano_rural_y_rural_toda_la_red_a_desnudo_por_ambiente(sector):
    sub = adaptar_tramo_mt(T(material='N2XSY', mm2=70, sub=True, corr=True), sector, REG, A6)
    assert (sub.material, sub.subterranea) == ('CU Desnudo', False)
    assert sub.regla.endswith({'urbano_rural': 'art. 33', 'rural_ser': 'art. 38'}[sector])


def test_108_rf22_mt_zona_historica_reconoce_la_subterranea_instalada_como_na2xsy():
    a = adaptar_tramo_mt(T(material='N2XSY', mm2=50, sub=True, zona='Baja', especial='historica'), 'urbano_alta',
                         REG, A6)
    assert (a.material, a.subterranea, a.regla) == ('NA2XSY', True, 'RCD 232-2017-OS/CD, art. 43')


# ---------------------------------------------------------------- BT (arts. 26, 31, 36, 41)

def test_108_rf22_bt_usa_las_tablas_de_bt_y_no_las_de_mt():
    (a,) = adaptar_red_bt([T(material='CU Protegido', mm2=50, zona='Media')], 'urbano_alta', REG, A6)
    assert a.material.casefold() == 'al autoportante'
    assert a.seccion_mm2 == _celda(8, 'CU Protegido', 50, 'AL Autoportante')


def test_108_rf22_bt_alta_muy_alta_a_na2xy_y_subterranea_de_sed_aerea_a_autoportante_con_71_29():
    (m,) = adaptar_red_bt([T(material='CU Desnudo', mm2=35, zona='Muy Alta')], 'urbano_alta', REG, A6)
    assert m.material == 'NA2XY'
    tramos = [T('B1', 'NYY - Unipolar o Tripolar', 70, 71.0, sub=True, fases=3, sed='S1', sed_adaptada='Biposte 3ø'),
              T('B2', 'NYY - Unipolar o Tripolar', 35, 29.0, sub=True, fases=2, sed='S1', sed_adaptada='Biposte 3ø')]
    a = {x.existente.codigo: x for x in adaptar_red_bt(tramos, 'urbano_alta', REG, A6)}
    assert a['B2'].subcomponente == 'A.1.3' and a['B1'].subcomponente == 'A.1.1'  # 29 %: primero las bifásicas
    assert not a['B1'].subterranea and a['B1'].material.casefold() == 'al autoportante'
    (c,) = adaptar_red_bt([T('C', 'NYY - Unipolar o Tripolar', 70, 10.0, sub=True, sed_adaptada='Compacta Pedestal 3ø')],
                          'urbano_alta', REG, A6)
    assert (c.material, c.subterranea) == ('NA2XY', True)


def test_108_rf22_bt_media_baja_tope_del_2_por_ciento_bifasicas_primero():
    tramos = [T('A', 'CU Desnudo', 35, 980.0), T('S3', 'NYY - Unipolar o Tripolar', 35, 20.0, sub=True, fases=3),
              T('S2', 'NYY - Unipolar o Tripolar', 70, 20.0, sub=True, fases=2)]
    a = {x.existente.codigo: x for x in adaptar_red_bt(tramos, 'urbano_media_baja', REG, A6)}
    assert not a['S2'].subterranea and a['S3'].subterranea  # 40 de 1020 m → 20 (≤ 2 %)


@pytest.mark.parametrize('sector', ['urbano_rural', 'rural_ser'])
def test_108_rf22_bt_urbano_rural_y_rural_todo_a_autoportante_de_aluminio(sector):
    (a,) = adaptar_red_bt([T(material='NYY - Unipolar o Tripolar', mm2=35, sub=True)], sector, REG, A6)
    assert (a.material.casefold(), a.subterranea) == ('al autoportante', False)


# ---------------------------------------------------------------- SED, equipos y alumbrado

def test_108_rf22_kva_adaptado_con_fp_y_fu_de_cada_sector():
    assert kva_adaptado(67.5, 'urbano_alta', REG) == pytest.approx(100.0)        # 0,9 × 0,75
    assert kva_adaptado(76.5, 'urbano_media_baja', REG) == pytest.approx(100.0)  # 0,9 × 0,85
    assert kva_adaptado(81.0, 'rural_ser', REG) == pytest.approx(100.0)          # 0,9 × 0,9


@pytest.mark.parametrize('tipo, kva, fases, zona, sector, esperado', [
    ('Convencional', 500, 3, 'Muy Alta', 'urbano_alta', 'Compacta Pedestal 3ø'),
    ('Convencional', 800, 3, 'Muy Alta', 'urbano_alta', 'Convencional 3ø'),
    ('Biposte', 100, 3, 'Media', 'urbano_alta', 'Biposte 3ø'),
    ('Monoposte', 300, 3, 'Media', 'urbano_media_baja', 'Compacta Pedestal 3ø'),
    ('Monoposte', 30, 1, 'Media', 'urbano_media_baja', 'Monoposte 1ø'),
    ('Convencional', 80, 3, 'Baja', 'urbano_rural', 'Biposte 3ø'),
    ('Monoposte', 50, 1, 'Baja', 'rural_ser', 'Monoposte 3ø')])
def test_108_rf22_tipo_de_sed_adaptada_por_su_tabla(tipo, kva, fases, zona, sector, esperado):
    assert adaptar_sed(tipo, kva, fases, zona, sector, REG)[0] == esperado


def test_108_rf22_equipos_de_proteccion_y_lo_que_la_guia_no_reconoce():
    assert adaptar_equipo('Reconectador', False, 'urbano_alta', REG)[0] == 'Reconectador SF6'
    assert adaptar_equipo('Seccionador fusible (cut-out)', False, 'rural_ser', REG)[0] == 'Seccionador fusible (cut-out)'
    assert adaptar_equipo('Interruptor', True, 'urbano_media_baja', REG)[0] == 'Interruptor SF6'
    with pytest.raises(VnrGuiaError, match='no lo reconoce'):
        adaptar_equipo('Seccionador bajo carga', False, 'urbano_rural', REG)


def test_108_rf22_alumbrado_a_sodio_o_led_con_las_potencias_maximas_rurales():
    assert adaptar_luminaria('Mercurio', 125, 'rural_ser', REG, A6)[:2] == ('Sodio', 50)
    assert adaptar_luminaria('LED', 60, 'urbano_rural', REG, A6)[:2] == ('LED', 40)
    assert adaptar_luminaria('Mercurio', 125, 'urbano_alta', REG, A6)[:2] == ('Sodio', 125)


# ---------------------------------------------------------------- ambiente y porciones

def test_108_rf22_ambiente_corrosivo_7_km_salvo_las_provincias_de_la_tabla_14():
    assert es_corrosivo(5, REG, A6) and not es_corrosivo(8, REG, A6)
    assert not es_corrosivo(4, REG, A6, departamento='Ancash', provincia='Santa')  # 0-3, 5-7, 10-16
    assert es_corrosivo(12, REG, A6, departamento='Ancash', provincia='Santa')
    assert not es_corrosivo(1, REG, A6, departamento='Piura', provincia='Paita')   # 0 km
    assert es_corrosivo(13, REG, A6, departamento='Lambayeque', provincia='Chiclayo')


def test_108_rf22_un_tramo_se_reparte_por_las_zonas_que_cruza():
    z = zonificar([SedZonificable('M', 300_500, 8_600_500, 4000.0)], REG)  # una cuadrícula de 1 km Muy Alta
    p = porciones_por_zona([(299_500, 8_600_500), (300_500, 8_600_500)], z)
    assert p == pytest.approx({'Baja': 500.0, 'Muy Alta': 500.0})


def test_108_rf22_sector_desconocido_y_equivalencia_inexistente_se_dicen():
    with pytest.raises(VnrGuiaError, match='sector típico'):
        adaptar_tramo_mt(T(), 'urbano', REG, A6)
    with pytest.raises(VnrGuiaError, match='sin equivalencia'):
        adaptar_tramo_mt(T(material='AA Protegido', mm2=50), 'urbano_alta', REG, A6)
