"""Spec 108 T20 — las Tablas de Resultados que liste el TdR registrado, en Excel (108:RF-11, aclaración del
2026-11-14).

El número de tablas sale del registro: un registro sintético de 16 (el número del TdR 2026) y otro de 3, con títulos
inventados. Dos empresas sintéticas con sistemas y cifras distintas.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import openpyxl
import pytest

from convertersmartgrid.libro_informe import ERRORES_DE_FORMULA
from convertersmartgrid.registro_normativo import cargar_registro
from convertersmartgrid.vad import VadError
from convertersmartgrid.vad.tablas_resultados import HOJA_INDICE, TablaDatos, escribir_tablas, tablas_registradas

RAIZ = Path(__file__).resolve().parents[1]


def _registro(tmp_path, n):
    lista = [{'numero': str(i), 'titulo': f'Título sintético {i}'} for i in range(1, n + 1)]
    datos = {'esquema': 'registro_normativo_v1', 'normas': [{
        'acto': 'tdr-sintetico', 'titulo': 'TdR sintético', 'estado_juridico': 'vigente_comprobada',
        'sha256': '1' * 64, 'reglas': [{'clave': 'vad.tablas_resultados', 'valor': lista,
                                        'cita_literal': '«tablas»', 'lineas': '40-60',
                                        'articulo_o_anexo': 'Numeral sintético'}]}]}
    ruta = tmp_path / f'reg{n}' / 'tdr.json'
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    return cargar_registro(ruta.parent)


EMPRESAS = {
    'norte': [{'sistema': 'SN1', 'VNR': 120.5, 'Clientes': 300}, {'sistema': 'SN2', 'VNR': 80.0, 'Clientes': 150}],
    'sur': [{'sistema': 'SS1', 'VNR': 10.0, 'Clientes': 7}],
}


def _celdas(ruta):
    libro = openpyxl.load_workbook(ruta)
    return libro, [c.value for h in libro.worksheets for fila in h.iter_rows() for c in fila]


def _sin_errores(ruta):
    _, valores = _celdas(ruta)
    assert not [v for v in valores if isinstance(v, str) and any(e in v for e in ERRORES_DE_FORMULA)]


@pytest.mark.parametrize('empresa', sorted(EMPRESAS))
@pytest.mark.parametrize('n', [16, 3])
def test_una_hoja_por_tabla_del_registro(tmp_path, empresa, n):
    """108:RF-11 — con 16 tablas en el registro salen 16 hojas (y con 3, tres) más el índice, en el orden y con el
    título del registro, con su fuente y sin errores de fórmula."""
    reg = _registro(tmp_path, n)
    datos = {'2': TablaDatos(['VNR', 'Clientes'], EMPRESAS[empresa])}
    r = escribir_tablas(reg, datos, tmp_path / empresa / f'tablas_{n}.xlsx')
    libro, _ = _celdas(r.ruta)
    assert libro.sheetnames == [HOJA_INDICE] + [f'Tabla {i}' for i in range(1, n + 1)]
    assert libro['Tabla 2']['A1'].value == 'Tabla 2. Título sintético 2'
    assert 'tdr-sintetico' in libro['Tabla 2']['A2'].value and '40-60' in libro['Tabla 2']['A2'].value
    _sin_errores(r.ruta)


def test_total_con_formulas_vivas(tmp_path):
    """108:RF-11 — el total de cada columna numérica es una fórmula =SUM sobre las filas de los sistemas."""
    r = escribir_tablas(_registro(tmp_path, 3), {'1': TablaDatos(['VNR', 'Clientes'], EMPRESAS['norte'])},
                        tmp_path / 'x.xlsx')
    hoja = openpyxl.load_workbook(r.ruta)['Tabla 1']
    filas = list(hoja.iter_rows(min_row=4, values_only=True))
    assert filas[0] == ('Sistema eléctrico', 'VNR', 'Clientes')
    assert [f[0] for f in filas[1:]] == ['SN1', 'SN2', 'Total']
    assert filas[-1][1] == '=SUM(B5:B6)' and filas[-1][2] == '=SUM(C5:C6)'
    assert re.fullmatch(r'=SUM\([A-Z]+\d+:[A-Z]+\d+\)', filas[-1][1])


def test_tabla_sin_datos_es_hueco_nombrado(tmp_path):
    """108:RF-11 — una tabla sin datos sale con «Sin datos» y su motivo, y el índice la marca como hueco."""
    r = escribir_tablas(_registro(tmp_path, 3), {'1': TablaDatos(['VNR', 'Clientes'], EMPRESAS['sur']),
                                                 '3': TablaDatos(['X'], [], motivo_sin_datos='falta el anexo 5')},
                        tmp_path / 'h.xlsx')
    libro = openpyxl.load_workbook(r.ruta)
    assert libro['Tabla 3']['A4'].value == 'Sin datos: falta el anexo 5'
    assert libro['Tabla 2']['A4'].value.startswith('Sin datos')
    estados = {f[0]: f[2] for f in libro[HOJA_INDICE].iter_rows(min_row=2, values_only=True)}
    assert estados == {'1': 'con datos', '2': 'hueco', '3': 'hueco'}
    assert any('Tabla 3' in h and 'anexo 5' in h for h in r.huecos)


def test_celda_sin_valor_es_hueco_y_su_columna_no_suma(tmp_path):
    """108:RF-11 — una celda sin valor se nombra como hueco y su columna no lleva un total engañoso."""
    filas = [{'sistema': 'A', 'VNR': 1.0}, {'sistema': 'B', 'VNR': None}]
    r = escribir_tablas(_registro(tmp_path, 1), {'1': TablaDatos(['VNR'], filas)}, tmp_path / 'c.xlsx')
    assert any('sistema B' in h and 'VNR' in h for h in r.huecos)
    hoja = openpyxl.load_workbook(r.ruta)['Tabla 1']
    assert hoja.cell(7, 1).value == 'Total' and hoja.cell(7, 2).value is None


@pytest.mark.parametrize('datos,texto', [
    ({'9': TablaDatos(['V'], [{'sistema': 'A', 'V': 1}])}, 'no lista: 9'),
    ({'1': TablaDatos([], [{'sistema': 'A'}])}, 'columnas con nombre'),
    ({'1': TablaDatos(['V'], [{'V': 1}])}, 'sistema eléctrico'),
    ({'1': TablaDatos(['V'], [{'sistema': 'A', 'W': 1}])}, 'no declara'),
    ({'1': TablaDatos(['V'], [{'sistema': 'A', 'V': [1]}])}, 'no admitido'),
    ({'1': TablaDatos(['V'], [{'sistema': 'A', 'V': 1}, {'sistema': 'A', 'V': 2}])}, 'repite sistemas'),
    ({'1': TablaDatos(['V'], [])}, 'ni dice por qué'),
])
def test_datos_invalidos_se_rechazan(tmp_path, datos, texto):
    """108:RF-11 — una tabla que el registro no lista, sin columnas, sin sistema o con valores no admitidos se
    rechaza con mensaje, y no se escribe nada."""
    destino = tmp_path / 'no.xlsx'
    with pytest.raises(VadError, match=texto):
        escribir_tablas(_registro(tmp_path, 3), datos, destino)
    assert not destino.exists()


def test_registro_real_lista_sus_tablas():
    """108:RF-11, 108:RF-13 — el TdR registrado lista sus Tablas de Resultados con número y título, sin repetir."""
    tablas, rv = tablas_registradas(cargar_registro(RAIZ / 'config' / 'vad'))
    assert tablas and rv.obligatoria and len({t['numero'] for t in tablas}) == len(tablas)
