"""108 T26 (108:RF-23, RF-24): cálculo del VNR según la Guía (RCD 232-2017-OS/CD, art. 17.2) con los códigos del Anexo 2,
las claves del Anexo 3 y una tabla de costos con la interfaz del SICODI; anualidad del VNR real con los factores del VAD.
La tabla de costos es sintética: el libro real del SICODI no entra en la suite."""
from dataclasses import dataclass
from pathlib import Path

import pytest

from convertersmartgrid.dominio.registro_normativo import cargar_registro
from convertersmartgrid.adaptadores.vad.costos import anualidad_vnr_real
from convertersmartgrid.aplicacion.vad.vnr_guia import (
    ItemMetrado,
    Tramo,
    VnrGuiaError,
    adaptar_red_bt,
    adaptar_red_mt,
    calcular_vnr,
    cargar_anexo2,
    cargar_anexo6,
    codigo_de_red,
    codigo_de_sed,
    items_de_red,
)

RAIZ = Path(__file__).resolve().parents[1]
REG = cargar_registro(RAIZ / 'config' / 'normativa' / 'rcd_232_2017.json')
REG_VAD = cargar_registro(RAIZ / 'config' / 'vad', RAIZ / 'config' / 'normativa')
A2 = cargar_anexo2(RAIZ / 'config' / 'vnr' / 'anexo2_codigos.json')
A6 = cargar_anexo6(RAIZ / 'config' / 'vnr' / 'anexo6_equivalencias.json')


@dataclass(frozen=True)
class _Costo:
    componentes: dict


@dataclass(frozen=True)
class _Fuente:
    huella: str = 'h' * 64


class _Tabla:
    """La interfaz de costos_fuentes.TablaCostos que usa el cálculo: ``filas`` (para los sectores) y ``resolver``."""

    def __init__(self, costos: dict):
        self.filas = {k: _Costo({'total': v}) for k, v in costos.items()}
        self.fuente = _Fuente()

    def resolver(self, codigo, tension, estructura, sector, subfamilia='', tipo=''):
        return self.filas.get((codigo, tension, estructura, sector)), ''


@pytest.mark.parametrize('nivel, sub, material, mm2, codigo', [
    ('MT', False, 'AA Desnudo', 50, 'AA05003'), ('MT', False, 'CU Desnudo', 35, 'CU03503'),
    ('MT', True, 'NA2XSY', 70, 'NA07003'), ('BT', False, 'AL Autoportante', 35, 'AS03513'),
    ('BT', True, 'NA2XY', 16, 'ND01613')])
def test_108_rf23_codigo_vnr_de_cada_red_adaptada_segun_el_anexo_2(nivel, sub, material, mm2, codigo):
    assert codigo_de_red(A2, nivel, sub, material, mm2) == codigo


def test_108_rf23_codigo_de_red_inexistente_o_material_sin_raiz_se_dice():
    with pytest.raises(VnrGuiaError, match='sin código'):
        codigo_de_red(A2, 'MT', False, 'AA Desnudo', 51)
    with pytest.raises(VnrGuiaError, match='sin raíz'):
        codigo_de_red(A2, 'MT', False, 'Fibra', 50)


def test_108_rf23_sed_un_solo_transformador_con_la_menor_capacidad_que_cubre_el_kva_adaptado():
    assert codigo_de_sed(A2, 'Monoposte 3ø', 27) == ('SM03004', 30.0)
    assert codigo_de_sed(A2, 'Compacta Pedestal 3ø', 300) == ('SP30004', 300.0)
    assert codigo_de_sed(A2, 'Monoposte 1ø', 20) == ('SM02001', 20.0)  # «1x20 kVA», nunca un banco 2x o 3x
    with pytest.raises(VnrGuiaError, match='llega a'):
        codigo_de_sed(A2, 'Monoposte 3ø', 10_000)


def test_108_rf23_vnr_es_metrado_por_costo_estandar_mas_ine_con_su_formula_citada():
    tabla = _Tabla({('AA05003', 'D', 'C', 'ST2'): 20_000.0, ('SM03004', 'D', 'X', 'ST2'): 5_000.0})
    r = calcular_vnr([ItemMetrado('AA05003', 1.5, 'D', 'C'), ItemMetrado('SM03004', 2, 'D', 'X')], tabla, 'ST2', REG,
                     ine=[('almacén', 100.0, 50.0)])
    assert r.vnr_ie == pytest.approx(40_000.0) and r.vnr_ine == pytest.approx(5_000.0)
    assert r.total == pytest.approx(45_000.0) and r.completo
    assert r.formula == 'VNR = MIE * CEIE + MINE * CINE (RCD 232-2017-OS/CD, art. 17.2)'
    assert r.huella_costos == 'h' * 64


def test_108_rf23_partida_sin_costo_estandar_es_hueco_nombrado_y_no_hay_total():
    tabla = _Tabla({('AA05003', 'D', 'C', 'ST2'): 20_000.0})
    r = calcular_vnr([ItemMetrado('AA05003', 1.0, 'D', 'C'), ItemMetrado('CU03503', 2.0, 'D', 'C')], tabla, 'ST2', REG)
    (h,) = r.huecos
    assert h.item.codigo == 'CU03503' and h.subtotal is None and 'sin costo estándar' in h.motivo
    assert r.total is None and r.vnr_ie == pytest.approx(20_000.0)


def test_108_rf23_sector_que_la_tabla_no_tiene_se_rechaza():
    with pytest.raises(VnrGuiaError, match='sector típico ST9'):
        calcular_vnr([], _Tabla({('AA05003', 'D', 'C', 'ST2'): 1.0}), 'ST9', REG)


def test_108_rf23_partidas_de_red_en_km_con_su_estructura():
    mt = adaptar_red_mt([Tramo('M1', 'CU Protegido', 50, 1500.0, False, 'Media', False),
                         Tramo('M2', 'N2XSY', 50, 500.0, True, 'Alta 1', False)], 'urbano_alta', REG, A6)
    items = {i.codigo: i for i in items_de_red(mt, A2, 'MT', 'D')}
    aa = next(i for c, i in items.items() if c.startswith('AA'))
    na = next(i for c, i in items.items() if c.startswith('NA'))
    assert (aa.cantidad, aa.secundario) == (pytest.approx(1.5), 'C') and (na.cantidad, na.secundario) == (0.5, 'X')
    bt = adaptar_red_bt([Tramo('B1', 'NYY - Unipolar o Tripolar', 70, 71.0, True, 'Media', False, sed='S1',
                               sed_adaptada='Biposte 3ø'),
                         Tramo('B2', 'NYY - Unipolar o Tripolar', 35, 29.0, True, 'Media', False, fases=2, sed='S1',
                               sed_adaptada='Biposte 3ø')], 'urbano_alta', REG, A6)
    items_bt = items_de_red(bt, A2, 'BT', 'X')
    assert {i.secundario for i in items_bt} == {'C'}  # ambas sobre postes de concreto
    assert {i.subfamilia for i in items_bt} == {'RED AÉREA SERVICIO PARTICULAR',
                                               'RED AÉREA SERVICIO PARTICULAR - SOBRE ESTRUCTURA SP'}


def test_108_rf24_anualidad_del_vnr_real_con_los_factores_del_vad_y_sin_ella_si_hay_huecos():
    tabla = _Tabla({('AA05003', 'D', 'C', 'ST2'): 20_000.0})
    r = calcular_vnr([ItemMetrado('AA05003', 2.0, 'D', 'C')], tabla, 'ST2', REG)
    a = anualidad_vnr_real(r, registro=REG_VAD)
    assert a.vnr == pytest.approx(40_000.0) and a.anualidad == pytest.approx(40_000.0 * a.factor_anualidad)
    assert 0 < a.factor_anualidad < 1 and a.vida_util_anios > 0 and a.criterios and a.huella_costos == 'h' * 64
    incompleto = calcular_vnr([ItemMetrado('CU03503', 1.0, 'D', 'C')], tabla, 'ST2', REG)
    b = anualidad_vnr_real(incompleto, registro=REG_VAD)
    assert b.anualidad is None and b.huecos and 'CU03503' in b.huecos[0]


def test_108_rf23_equivalencia_sin_codigo_en_el_anexo_2_es_hueco_de_su_partida_y_no_aborta():
    mt = adaptar_red_mt([Tramo('M3', 'N2XSY', 240, 200.0, True, 'Alta 1', False)], 'urbano_alta', REG, A6)
    (item,) = items_de_red(mt, A2, 'MT', 'D')
    assert item.codigo.startswith('SIN CÓDIGO: NA2XSY') and 'sin código en el Anexo 2' in item.origen
    r = calcular_vnr([item], _Tabla({('AA05003', 'D', 'C', 'ST2'): 1.0}), 'ST2', REG)
    assert r.total is None and r.huecos[0].motivo == item.origen
