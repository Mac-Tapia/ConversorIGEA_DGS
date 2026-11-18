"""PIT-F124 — los datos de generación del F-124, deducidos de la medición de las centrales del perfil (107:RF-9).

Centrales, medidores y curvas sintéticos: ningún nombre ni medida de una empresa real.
"""
from __future__ import annotations

import importlib
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

from convertersmartgrid.dominio.registro_normativo import cargar_registro

RAIZ = Path(__file__).resolve().parents[1]
NORMATIVA = RAIZ / 'config' / 'normativa'
FUENTE = {'nombre': 'libros de cabecera sintéticos', 'huella': 'g' * 16}
CENTRALES = {'AL-G1': {'generacion': 'MG-1', 'llegada': 'ML-1', 'salida': 'MS-1', 'nodo': ''},
             'AL-G2': {'generacion': 'MG-2', 'llegada': 'ML-2', 'salida': 'MS-2', 'nodo': ''}}
T0 = datetime(2041, 3, 1)  # noqa: DTZ001 (las curvas de cabecera van en hora local, sin zona, como el lector)


def _generacion():
    """El módulo de la tarjeta: su ausencia es la falla de la aserción, no un error de importación."""
    assert importlib.util.find_spec('convertersmartgrid.adaptadores.pit.generacion') is not None, \
        'falta convertersmartgrid.adaptadores.pit.generacion (PIT-F124)'
    return importlib.import_module('convertersmartgrid.adaptadores.pit.generacion')


def _curva(valores_kw):
    return [(T0 + i * timedelta(minutes=15), float(p), None) for i, p in enumerate(valores_kw)]


def test_107_rf9_generacion_f124_capacidad_deducida_de_la_maxima_medida_con_su_sustento():
    """107:RF-9 (PIT-F124) — por central del perfil, una fila con su medidor, un grupo medido en conjunto, la máxima
    potencia medida en MW como capacidad (anotada como deducida, no declarada) y el sustento con medidor y periodo; lo
    que la medición no da (titular, año, tipo de sistema) sale vacío con su motivo, nunca genérico."""
    mod = _generacion()
    from convertersmartgrid.adaptadores.pit.plantillas import celdas_de_formato
    datos = mod.datos_f124(CENTRALES, {'AL-G1': _curva([1200, 3450, 2000]), 'AL-G2': _curva([-800, -900])}, FUENTE,
                           area='AREA-S')
    filas = datos['bloques']['grupos']
    assert [f['capacidad_mw'] for f in filas] == [3.45, 0.9]
    assert 'MG-1' in filas[0]['central'] and filas[0]['grupo'].startswith('Grupo 1')
    assert 'MG-1' in filas[0]['sustento'] and '2041-03-01' in filas[0]['sustento'] and mod.DEDUCIDA in filas[0]['sustento']
    celdas = {c['celda']: c for c in celdas_de_formato(cargar_registro(NORMATIVA), 'F-124', datos)['celdas']}
    assert celdas['F-124!B4']['valor'] == 'AREA-S' and celdas['F-124!E9']['valor'] == 3.45
    assert celdas['F-124!E9']['traza']['calculo'] == mod.DEDUCIDA and celdas['F-124!E10']['valor'] == 0.9
    assert celdas['F-124!A9']['valor'] is None and 'titular' in celdas['F-124!A9']['traza']['motivo']
    assert 'año de ingreso' in celdas['F-124!C9']['traza']['motivo']
    assert 'SSTG' in celdas['F-124!G4']['traza']['motivo'], 'el motivo de la cabecera es el concreto, no el genérico'


def test_107_rf9_generacion_sin_curva_o_sin_centrales_sale_vacia_con_su_aviso():
    """107:RF-9 (PIT-F124) — una central sin curva de su medidor de generación queda vacía con ese motivo, y sin
    centrales en el perfil el formato sale vacío con su aviso."""
    mod = _generacion()
    datos = mod.datos_f124(CENTRALES, {'AL-G1': _curva([500])}, FUENTE)
    sin = datos['bloques']['grupos'][1]
    assert sin['capacidad_mw'] is None and 'MG-2' in sin['_motivos']['capacidad_mw']
    assert any('AL-G2' in a for a in datos['avisos'])
    vacio = mod.datos_f124({}, {}, FUENTE)
    assert vacio['bloques']['grupos'] == [] and any('centrales_termicas' in a for a in vacio['avisos'])


def test_107_rf9_generacion_lee_el_medidor_de_generacion_de_cada_central(monkeypatch):
    """107:RF-9 (PIT-F124) — la curva sale del medidor de generación de cada central, con el lector de cabecera de la
    calibración; lo que no se lee vuelve como hueco con su motivo."""
    mod = _generacion()
    from convertersmartgrid.adaptadores import pronostico_demanda
    pedidos = []

    def leer(rutas, pares, centrales=None):
        pedidos.extend(pares)
        return {'AL-G1': {'curva': _curva([10]), 'fuente': {'medidor': 'MG-1'}}}, [
            {'objetivo': 'cabecera:AL-G2', 'motivo': 'MG-2: sin curva'}]
    monkeypatch.setattr(pronostico_demanda, 'curvas_de_cabecera', leer)
    curvas, fuentes, huecos = mod.generacion_medida(['libros'], CENTRALES)
    assert pedidos == [('AL-G1', 'MG-1'), ('AL-G2', 'MG-2')] and set(curvas) == {'AL-G1'}
    assert huecos == ['cabecera:AL-G2: MG-2: sin curva'] and fuentes['AL-G1'] == {'medidor': 'MG-1'}


def test_107_rf9_generacion_el_f124_sale_llenado_y_ya_no_es_un_pendiente():
    """107:RF-9 (PIT-F124) — con la fuente de generación el F-124 sale llenado, y ya no está entre los formatos con
    causa de pendiente."""
    _generacion()
    from convertersmartgrid.adaptadores.pit import llenado
    registro = cargar_registro(NORMATIVA)
    assert 'F-124' not in llenado.CAUSAS_DE_PENDIENTE
    hecho = llenado.llenar_formatos(registro, {'generacion': {'fuente': FUENTE, 'centrales': CENTRALES,
                                                              'curvas': {'AL-G1': _curva([2000])}}})
    f124 = next(f for f in hecho['formatos'] if f['codigo'] == 'F-124')
    assert f124['estado'] == 'llenado' and 'F-124' not in hecho['pendientes_de_mapeo']
    assert any('AL-G2' in a for a in f124['avisos'])
