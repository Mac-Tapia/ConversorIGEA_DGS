"""Spec 086, T90: el libro CAPEX se lee aunque el perfil no declare su hoja (prueba funcional del 19-11).

El trabajo de obras falló con «el libro no tiene la hoja «None» del perfil»: el perfil del espacio no
declaraba la hoja y el lector buscaba una llamada literalmente «None». Libros sintéticos, sin datos reales.
"""
from __future__ import annotations

import pytest
from openpyxl import Workbook

from convertersmartgrid.aplicacion import pide_economia as ec


def _libro(tmp_path, hojas):
    libro = Workbook()
    libro.remove(libro.active)
    for nombre, filas in hojas.items():
        hoja = libro.create_sheet(nombre)
        for fila in filas:
            hoja.append(fila)
    ruta = tmp_path / 'presupuesto.xlsx'
    libro.save(ruta)
    return ruta


PORTADA = [['Presupuesto de inversiones'], ['Versión', 3]]
COSTOS = [['OBRAS POR CRECIMIENTO'],
          ['', 'Proyecto', 'Zona', 'Und', 'Cantidad', 'Costo Unitario', 'Responsable'],
          ['', 'Banco de condensadores 300 kvar', 'Norte', 'Und', 2, 3000, 'Persona X'],
          ['', 'Cambio de sección AAAC 120', 'Sur', 'km', 2, 25000, 'Persona Y']]


def test_sin_hoja_en_el_perfil_se_reconoce_por_su_contenido(tmp_path):
    """086:RF-119 — sin hoja ni columnas en el perfil, la hoja de costos se encuentra entre otras."""
    ruta = _libro(tmp_path, {'Portada': PORTADA, 'Costos': COSTOS})
    obras, avisos = ec.leer_capex(ruta, {})
    assert [(o.nombre, o.alternativa, o.costo_unitario, o.unidad) for o in obras] == [
        ('Banco de condensadores 300 kvar', 'bancos', 3000, 'Und'),
        ('Cambio de sección AAAC 120', 'cambio_seccion', 25000, 'km')]
    assert not any('Persona' in str(v) for o in obras for v in o.__dict__.values())
    assert any('Costos' in a and 'contenido' in a for a in avisos)
    assert any('Portada' in a for a in avisos)
    assert not any('None' in a for a in avisos)


def test_sin_hoja_con_las_columnas_del_perfil(tmp_path):
    """086:RF-119 — sin hoja pero con columnas declaradas, se busca la hoja con esas columnas."""
    filas = [['Obra nueva', 'Precio', 'U.M.'], ['Regulador de tensión', 9000, 'Und']]
    ruta = _libro(tmp_path, {'Notas': PORTADA, 'Hoja2': filas})
    config = {'columnas': {'nombre': 'Obra nueva', 'costo_unitario': 'Precio', 'unidad': 'U.M.'}}
    obras, _ = ec.leer_capex(ruta, config)
    assert [(o.nombre, o.alternativa, o.costo_unitario) for o in obras] == [('Regulador de tensión', 'reguladores', 9000)]


def test_sin_hoja_y_ninguna_valida_dice_que_falta(tmp_path):
    """086:RF-119 — ninguna hoja con nombre y costo unitario: el error dice qué falta, nunca «None»."""
    ruta = _libro(tmp_path, {'Portada': PORTADA, 'Resumen': [['Total', 100]]})
    with pytest.raises(ec.EconomiaPideError) as error:
        ec.leer_capex(ruta, {})
    texto = str(error.value)
    assert 'None' not in texto
    assert 'Portada' in texto and 'Resumen' in texto
    assert 'Costo Unitario' in texto and 'Proyecto' in texto
    assert 'hoja' in texto and 'perfil' in texto


def test_con_hoja_declarada_nada_cambia(tmp_path):
    """086:RF-119 — con la hoja del perfil se lee solo esa, y si falta es el error de siempre."""
    otra = [['', 'Proyecto', 'Und', 'Costo Unitario'], ['', 'Nueva SED 250 kVA', 'Und', 30000]]
    ruta = _libro(tmp_path, {'Costos': COSTOS, 'Otra': otra})
    config = {'hoja': 'Costos', 'columnas': {'nombre': 'Proyecto', 'unidad': 'Und', 'costo_unitario': 'Costo Unitario'}}
    obras, avisos = ec.leer_capex(ruta, config)
    assert [o.nombre for o in obras] == ['Banco de condensadores 300 kvar', 'Cambio de sección AAAC 120']
    assert not any('contenido' in a for a in avisos)
    with pytest.raises(ec.EconomiaPideError, match='no tiene la hoja «Falta» del perfil'):
        ec.leer_capex(ruta, {**config, 'hoja': 'Falta'})
