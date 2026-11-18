"""PIT-F123 — los mapas de densidad de carga del F-123 (107:RF-9): años de la nota de la plantilla, cuadrículas y zonas
de la Tabla N.º 2, plano (PNG), DXF para AutoCAD y base de datos de sustento (CSV). SED y puntos sintéticos.
"""
from __future__ import annotations

import csv
import importlib
import importlib.util
from pathlib import Path

import pytest

from convertersmartgrid.dominio.registro_normativo import cargar_registro

RAIZ = Path(__file__).resolve().parents[1]
NORMATIVA = RAIZ / 'config' / 'normativa'


def _densidad():
    """El módulo de la tarjeta: su ausencia es la falla de la aserción, no un error de importación."""
    assert importlib.util.find_spec('convertersmartgrid.adaptadores.pit.densidad') is not None, \
        'falta convertersmartgrid.adaptadores.pit.densidad (PIT-F123)'
    return importlib.import_module('convertersmartgrid.adaptadores.pit.densidad')


#: Dos SED en la misma cuadrícula de 1 km (4,5 MW: «Muy Alta») y una sola en otra (0,3 MW: «Media»), y una sin punto.
SEDS = [{'este': 500100.0, 'norte': 8500100.0, 'kw': 3000.0, 'sistema': 'SIS-1'},
        {'este': 500900.0, 'norte': 8500900.0, 'kw': 1500.0, 'sistema': 'SIS-1'},
        {'este': 503500.0, 'norte': 8500500.0, 'kw': 300.0, 'sistema': 'SIS-1'},
        {'este': None, 'norte': None, 'kw': 100.0, 'sistema': 'SIS-1'}]


def test_107_rf9_densidad_los_anios_salen_de_la_nota_de_la_plantilla():
    """107:RF-9 (PIT-F123) — los años de los mapas son los de la nota (2) del F-123 transcrito, no del código."""
    mod = _densidad()
    assert mod.anios_del_formato(cargar_registro(NORMATIVA)) == [0, 1, 2, 3, 4, 10, 15, 20, 25, 30]


def test_107_rf9_densidad_mapa_por_anio_con_sus_zonas_su_dxf_y_su_sustento(tmp_path):
    """107:RF-9 (PIT-F123) — por año, la demanda de cada SED crece con el factor regulatorio de su sistema, se
    cuadricula con su zona de la Tabla N.º 2 y deja el PNG, el DXF (una capa por zona) y el CSV de sustento; un usuario
    entra como carga concentrada y la SED sin punto se avisa."""
    import ezdxf
    mod = _densidad()
    registro = cargar_registro(NORMATIVA)
    factores = {'SIS-1': [1.0 + 0.1 * i for i in range(31)]}
    usuarios = [{'este': 503600.0, 'norte': 8500600.0, 'potencia_mw': [0.0] * 4 + [2.0] * 27}]
    mapas = mod.mapas_f123(registro, SEDS, factores, tmp_path, usuarios=usuarios, area='AREA-S')
    assert sorted(mapas['anios']) == [0, 1, 2, 3, 4, 10, 15, 20, 25, 30] and any('sin punto' in a for a in mapas['avisos'])
    cero, diez = mapas['anios'][0], mapas['anios'][10]
    assert cero['zonas'] == {'Muy Alta': 1, 'Media': 1} and diez['zonas'] == {'Muy Alta': 1, 'Alta 1': 1}
    with Path(diez['csv']).open(encoding='utf-8') as fh:
        filas = list(csv.DictReader(fh))
    lejana = next(f for f in filas if float(f['este']) == 503000.0)
    assert float(lejana['mw']) == pytest.approx(0.3 * 2.0 + 2.0) and float(lejana['mw_concentradas']) == pytest.approx(2.0)
    assert Path(cero['png']).stat().st_size > 1000
    capas = {e.dxf.layer for e in ezdxf.readfile(cero['dxf']).modelspace().query('SOLID')}
    assert capas == {'DENSIDAD_MUY_ALTA', 'DENSIDAD_MEDIA'}
    assert mapas['calculo'] == mod.DEDUCIDA


def test_107_rf9_densidad_factores_del_f110_y_resultado_con_una_hoja_por_anio(tmp_path):
    """107:RF-9 (PIT-F123) — el factor de cada sistema es la F-110 del año entre la del año 0; el F-123 lleva un año por
    hoja con su imagen, pide las copias de la hoja y el plan del libro las nombra en lugar de escribir sin ellas."""
    mod = _densidad()
    from convertersmartgrid.adaptadores.pit import llenado
    from convertersmartgrid.dominio.pit.ambito import PitError
    from convertersmartgrid.adaptadores.pit.cuadros import plan_de_formatos
    cadena = {'filas': {'F-110': [{'sistema': 'S', 'potencia_mw': [2.0, 3.0]}, {'sistema': 'S', 'potencia_mw': [2.0, 1.0]}]}}
    assert mod.factores_por_sistema(cadena) == {'S': [1.0, 1.0]}
    registro = cargar_registro(NORMATIVA)
    mapas = mod.mapas_f123(registro, SEDS[:1], {'SIS-1': [1.0] * 31}, tmp_path, area='AREA-S')
    hecho = llenado.llenar_formatos(registro, {'densidad': {'fuente': {'nombre': 'x', 'huella': 'y'}, 'mapas': mapas,
                                                            'area': 'AREA-S'}})
    f123 = hecho['resultados']['F-123']
    assert next(f for f in hecho['formatos'] if f['codigo'] == 'F-123')['estado'] == 'llenado'
    celdas = {c['celda']: c['valor'] for c in f123['celdas']}
    assert celdas['F-123!B4'] == 'AREA-S' and celdas['F-123!H4'] == 0 and celdas['F-123 (10)!H4'] == 30
    assert f123['imagenes'][0] == {'celda': 'F-123!A6', 'ruta': mapas['anios'][0]['png']}
    assert len(f123['hojas_a_copiar']) == 9 and 'F-123' not in llenado.CAUSAS_DE_PENDIENTE
    with pytest.raises(PitError, match=r'F-123 \(2\)'):
        plan_de_formatos([f123], modelo=tmp_path / 'm.xlsx', destino=tmp_path / 'd.xlsx')
    solo = {**f123, 'hojas_a_copiar': []}
    assert plan_de_formatos([solo], modelo=tmp_path / 'm.xlsx', destino=tmp_path / 'd.xlsx')['imagenes'][0]['celda'] == 'F-123!A6'
