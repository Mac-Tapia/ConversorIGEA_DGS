"""108 T26 y T27 (108:RF-24, 108:RF-25): formatos A1 y D1 del Anexo 5 de la Guía del VNR (RCD 232-2017-OS/CD), su libro
Excel, y las altas y bajas del art. 18 con su efecto en el VNR. Tabla de costos sintética con la interfaz del SICODI."""
from dataclasses import dataclass
from pathlib import Path

import pytest

from convertersmartgrid.registro_normativo import cargar_registro
from convertersmartgrid.vad.vnr_formatos import escribir_formatos
from convertersmartgrid.vad.vnr_guia import (
    ItemMetrado,
    VnrGuiaError,
    altas_y_bajas,
    calcular_vnr,
    cargar_anexo2,
    cargar_anexo5,
    formato_ine,
    formato_resumen,
)

RAIZ = Path(__file__).resolve().parents[1]
REG = cargar_registro(RAIZ / 'config' / 'normativa' / 'rcd_232_2017.json')
A2 = cargar_anexo2(RAIZ / 'config' / 'vnr' / 'anexo2_codigos.json')
A5 = cargar_anexo5(RAIZ / 'config' / 'vnr' / 'anexo5_formatos.json')


@dataclass(frozen=True)
class _Costo:
    componentes: dict


class _Tabla:
    def __init__(self, costos):
        self.filas = {k: _Costo({'total': v}) for k, v in costos.items()}

    def resolver(self, codigo, tension, estructura, sector, subfamilia='', tipo=''):
        return self.filas.get((codigo, tension, estructura, sector)), ''


TABLA = _Tabla({('AA05003', 'D', 'C', 'ST2'): 20_000.0, ('NA07003', 'D', 'X', 'ST2'): 100_000.0,
                ('SM03004', 'D', 'X', 'ST2'): 5_000.0, ('AS03513', 'X', 'C', 'ST2'): 8_000.0})


def test_108_rf24_formato_a1_agrupa_por_subcomponente_con_costo_y_subtotal_en_miles():
    r = calcular_vnr([ItemMetrado('AA05003', 2.0, 'D', 'C'), ItemMetrado('NA07003', 0.5, 'D', 'X'),
                      ItemMetrado('SM03004', 4, 'D', 'X'), ItemMetrado('AS03513', 3.0, 'X', 'C')], TABLA, 'ST2', REG)
    f = formato_resumen(r, A2, A5, codigo='A1', ambito='Empresa sintética', moneda='USD')
    fila = {(x.grupo, x.item): x for x in f.filas}
    assert fila[('1', 'A1')].cantidad == 2.0 and fila[('1', 'A1')].subtotal_miles == pytest.approx(40.0)
    assert fila[('1', 'A1')].costo_unitario == pytest.approx(20_000.0)
    assert fila[('1', 'B')].subtotal_miles == pytest.approx(50.0)          # red subterránea de MT
    assert fila[('2', 'A1')].cantidad == 4 and fila[('2', 'A1')].subtotal_miles == pytest.approx(20.0)
    assert fila[('3', 'A1.1')].subtotal_miles == pytest.approx(24.0)
    assert f.total_miles == pytest.approx(134.0) and f.titulo == 'Resumen del VNR a nivel de Empresa'
    assert all(x.grupo != '4' for x in f.filas)


def test_108_rf24_fila_con_partida_sin_costo_lleva_su_hueco_y_el_formato_no_tiene_total():
    r = calcular_vnr([ItemMetrado('AA05003', 1.0, 'D', 'C'), ItemMetrado('AA07003', 1.0, 'D', 'C')], TABLA, 'ST2', REG)
    f = formato_resumen(r, A2, A5)
    fila = next(x for x in f.filas if (x.grupo, x.item) == ('1', 'A1'))
    assert fila.subtotal_miles is None and 'AA07003' in fila.huecos[0] and f.total_miles is None


def test_108_rf24_formato_d1_de_ine_por_rubro_y_rubro_ajeno_rechazado():
    f = formato_ine({'A': (500.0, 100_000.0), 'C': (3, 90_000.0)}, A5, ambito='UG Norte', moneda='USD')
    fila = {x.item: x for x in f.filas}
    assert fila['A'].unidad == 'm2' and fila['A'].costo_unitario == pytest.approx(200.0)
    assert f.total_miles == pytest.approx(190.0) and len(f.filas) == 8
    with pytest.raises(VnrGuiaError, match='no están en el Formato'):
        formato_ine({'Z': (1, 1.0)}, A5)


def test_108_rf24_libro_excel_de_los_formatos_con_total_por_formula(tmp_path):
    from openpyxl import load_workbook
    r = calcular_vnr([ItemMetrado('AA05003', 2.0, 'D', 'C')], TABLA, 'ST2', REG)
    ruta = escribir_formatos([formato_resumen(r, A2, A5, codigo='A1'), formato_resumen(r, A2, A5, codigo='C1',
                                                                                        ambito='SE sintético')],
                             tmp_path / 'vnr.xlsx', notas=A5['notas'])
    libro = load_workbook(ruta)
    assert libro.sheetnames == ['A1', 'C1']
    total = [c.value for c in libro['A1']['G'] if isinstance(c.value, str) and c.value.startswith('=SUM(')]
    assert len(total) == 1
    assert any('(2) Se calcula dividiendo' in str(c.value) for c in libro['A1']['A'])


def test_108_rf25_altas_bajas_y_modificadas_con_su_efecto_en_el_vnr():
    """108:RF-25 — altas, bajas y modificadas del art. 18, valoradas con la misma tabla."""
    antes = {'T1': ItemMetrado('AA05003', 1.0, 'D', 'C'), 'T2': ItemMetrado('AA05003', 2.0, 'D', 'C'),
             'S1': ItemMetrado('SM03004', 1, 'D', 'X')}
    ahora = {'T1': ItemMetrado('AA05003', 1.0, 'D', 'C'), 'T2': ItemMetrado('AA05003', 2.5, 'D', 'C'),
             'T3': ItemMetrado('NA07003', 0.2, 'D', 'X')}
    ab = altas_y_bajas(antes, ahora, TABLA, 'ST2', REG)
    assert (ab.altas, ab.bajas, ab.modificadas) == (('T3',), ('S1',), ('T2',))
    assert ab.efecto == pytest.approx(20_000.0 - 5_000.0 + 10_000.0)


def test_108_rf25_efecto_sin_total_si_una_alta_no_tiene_costo():
    """108:RF-25 — un alta sin costo estándar deja el efecto sin total (hueco nombrado)."""
    ab = altas_y_bajas({}, {'X': ItemMetrado('CU03503', 1.0, 'D', 'C')}, TABLA, 'ST2', REG)
    assert ab.altas == ('X',) and ab.efecto is None


def test_108_rf24_partida_sobre_estructura_sp_va_a_la_fila_a1_3_por_su_subfamilia():
    tabla = _Tabla({('AS07012', 'X', 'C', 'ST2'): 4_000.0})
    r = calcular_vnr([ItemMetrado('AS07012', 1.0, 'X', 'C', subfamilia='RED AÉREA SERVICIO PARTICULAR - SOBRE '
                                                                     'ESTRUCTURA SP')], tabla, 'ST2', REG)
    fila = {(x.grupo, x.item): x for x in formato_resumen(r, A2, A5).filas}
    assert fila[('3', 'A1.3')].subtotal_miles == pytest.approx(4.0) and fila[('3', 'A1.1')].cantidad == 0
