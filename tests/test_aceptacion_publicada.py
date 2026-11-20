"""Spec 072 T13 y T11: valorar una obra publicada con la base vigente y comparar los dos entregables con los custodiados.

Orden del usuario del 2026-11-19: lo que publique o no el regulador no es requisito de cierre. La base de módulos que
sustituya a la vigente entra por su huella cuando se descargue; la obra y los entregables de referencia son los ya
publicados o custodiados. Aquí todo es SINTÉTICO con la forma oficial (cabeceras de dos filas, notas, estilos de
título); los códigos y nombres son inventados. La corrida real se hace fuera de git.
"""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest

from convertersmartgrid.aplicacion.costos_fuentes import CostosError, leer_modulos_transmision

MODULO = 'convertersmartgrid.adaptadores.aceptacion_publicada'
SHA_A, SHA_B = 'a' * 64, 'b' * 64


def _ap():
    """La ausencia del módulo es la falla de la aserción (rojo), no un error de importación."""
    assert importlib.util.find_spec(MODULO) is not None, 'falta el módulo de aceptación con lo publicado (072 T11/T13)'
    return importlib.import_module(MODULO)


def test_la_base_vigente_es_la_ultima_por_vigencia_y_la_siguiente_entra_por_su_huella():
    """072:RF-9 (T13) — una base nueva (otra huella) pasa a vigente y la anterior se conserva; la misma huella no duplica."""
    ap = _ap()
    anterior = {'resolucion': 'R-1', 'sha256': SHA_A, 'vigencia_desde': '2030-07-26', 'fecha_descarga': '2030-08-01'}
    r = ap.base_vigente([anterior, dict(anterior)])
    assert r['vigente']['sha256'] == SHA_A and r['anteriores'] == []
    assert 'la siguiente entra por su huella' in r['aviso']
    nueva = {'resolucion': 'R-2', 'sha256': SHA_B, 'vigencia_desde': '2030-10-01'}
    r = ap.base_vigente([nueva, anterior])
    assert r['vigente']['resolucion'] == 'R-2' and [v['resolucion'] for v in r['anteriores']] == ['R-1']
    assert '1 versión anterior conservada; lo valorado con ella queda marcado' in r['aviso']  # 086:RF-110
    with pytest.raises(CostosError, match='huella'):
        ap.base_vigente([{'resolucion': 'R-3', 'sha256': 'x', 'vigencia_desde': '2030-01-01'}])
    with pytest.raises(CostosError, match='vigencia'):
        ap.base_vigente([{'resolucion': 'R-3', 'sha256': SHA_A}])


def _formatos(tmp_path: Path) -> Path:
    """F-301 y F-302 de una alternativa con la forma oficial: cabecera de dos filas, totales al pie y notas."""
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet('F-301 Alt1')
    ws.append(['OSINERGMIN'])
    ws.append(['VALORIZACIÓN DE INVERSIÓN DE LÍNEAS DE TRANSMISIÓN'])
    ws.append([None, None, 'NOMBRE DE LÍNEA', None, None, None, 'TENSIÓN', 'Nro.', 'LONGITUD', None,
               'COSTO UNITARIO MÓDULO', None, None, None, 'VALORIZACIÓN', None, None, None, 'FACTOR', 'TOTAL'])
    ws.append(['AÑO', 'CÓDIGO', None, None, 'TRAMO', 'TITULAR', 'NOMINAL', 'DE TERNAS', '(km)', 'MÓDULO'])
    ws.append([None, None, 'S.E. Inicio', 'S.E. Llegada'])
    ws.append([2031, 'L-1', 'SET P', 'SET Q', 1, 'TIT', 1, 1, 10.0, 'LT-AAA1'] + [0] * 8 + [0.5, 4000.0])
    ws.append([2031, 'L-2', 'SET Q', 'SET R', 1, 'TIT', 1, 1, 2.0, 'XX'] + [0] * 8 + [1, 50.0])
    ws.append(['TOTAL'] + [None] * 18 + [4050.0])
    ws.append(['(1) Factor Costo: nota de la plantilla.'])
    ws = wb.create_sheet('F-302 Alt1')
    ws.append(['OSINERGMIN'])
    ws.append(['VALORIZACIÓN DE INVERSIÓN EN SUBESTACIONES (US$)'])
    ws.append(['CODIGO', None, None, None, None, 'BÁSICO', None, None, None, 'SERVICIOS AUXILIARES', None, None, None,
               'COSTOS COMUNES', None, None, None, 'COSTOS INDIRECTOS', None, None, None, 'TOTAL ELEMENTOS'])
    ws.append(['ELEMENTO', None, 'DESCRIPCIÓN', 'TENSIÓN', 'MÓDULO'] + ['Moneda'] * 20 + ['Total', 'TITULAR'])
    ws.append([None, 1, 'SET P'])
    ws.append(['E-1', 2031, 'Celda de línea', 1, 'CE-BBB2', 300.0, 200.0, 0, 0] + [0] * 8 + [0, 100.0, 0, 0]
              + [0] * 4 + [600.0, 'TIT'])
    ws.append(['E-2', 2031, 'Transformador', 1, 'TP-NOEXISTE', 50.0, 0, 0, 0] + [0] * 16 + [50.0, 'TIT'])
    ws.append([None, None, 'Costos Indirectos (total) (2)', None, None, 0, 100.0])
    ws.append([None, None, 'Costo del Terreno', None, 'm2', 0, 0])
    ws.append([None, None, 'Gastos Financieros', 0.01, 'XYZ', 0, 7.0])
    ws.append([None, None, 'TOTAL SUBESTACIÓN', None, None, 350.0, 300.0] + [0] * 18 + [650.0])
    wb.create_sheet('RESUMEN MODULOS X')
    ruta = tmp_path / 'inversion.xlsx'
    wb.save(ruta)
    return ruta


def _base(tmp_path: Path):
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    for hoja, filas in (('LIN', [('LT-AAA1', 'Línea sintética', 1000.0)]), ('EQ', [('CE-BBB2', 'Celda sintética', 450.0)])):
        ws = wb.create_sheet(hoja)
        ws.append(['Resumen'])
        ws.append(['CODIGO', 'Descripción', 'TOTAL GENERAL (USD)'])
        for f in filas:
            ws.append(list(f))
    ruta = tmp_path / 'base.xlsx'
    wb.save(ruta)
    return leer_modulos_transmision(ruta, columnas={'codigo': 'CODIGO', 'nombre': 'Descripción',
                                                    'total': 'TOTAL GENERAL (USD)'},
                                    resolucion='R-2', anio=2030, moneda='USD', url='https://ejemplo.invalid/base',
                                    fecha_descarga='2030-10-02', hoja=['LIN', 'EQ'], unidad={'LIN': 'km', 'EQ': 'u'})


def test_la_obra_publicada_sale_de_sus_formatos_con_sus_huecos_nombrados(tmp_path):
    """072:RF-6, RF-15, RF-16 (T13) — líneas por km y elementos por unidad, con su cifra publicada; sin módulo, hueco."""
    ap = _ap()
    obra = ap.obra_desde_formatos_inversion(_formatos(tmp_path), 'Alt1')
    por = {e['elemento']: e for e in obra['elementos']}
    assert set(por) == {'L-1', 'E-1', 'E-2'}
    assert por['L-1']['cantidad'] == 10.0 and por['L-1']['unidad'] == 'km' and por['L-1']['factor_publicado'] == 0.5
    assert por['L-1']['publicado'] == 4000.0 and por['L-1']['fila'] == 6
    assert por['E-1']['unidad'] == 'u' and por['E-1']['publicado'] == 600.0 and por['E-1']['publicado_basico'] == 500.0
    huecos = {h['elemento'] for h in obra['huecos']}
    assert 'L-2' in huecos and 'Costos Indirectos (total) (2)' in huecos and 'Gastos Financieros' in huecos
    assert 'TOTAL SUBESTACIÓN' not in huecos and 'Costo del Terreno' not in huecos   # sin cifra: nada que nombrar
    assert obra['hojas_de_modulos'] == ['RESUMEN MODULOS X']
    with pytest.raises(CostosError, match='F-301'):
        ap.obra_desde_formatos_inversion(_formatos(tmp_path), 'Alt9')


def test_la_obra_se_valora_con_la_base_vigente_y_cada_diferencia_dice_su_causa(tmp_path):
    """072:RF-6, RF-8, RF-9, RF-16 (T13) — metrado × módulo vigente, sin factores supuestos y con el módulo ausente nombrado."""
    ap = _ap()
    obra = ap.obra_desde_formatos_inversion(_formatos(tmp_path), 'Alt1')
    r = ap.comparar_valoracion(obra, _base(tmp_path), obra['hojas_de_modulos'])
    por = {e['elemento']: e for e in r['elementos']}
    assert por['L-1']['conversor'] == pytest.approx(10_000.0)          # el factor 0,5 no se aplica solo
    assert por['L-1']['publicado_comparable'] == pytest.approx(8000.0)   # 4000 / 0,5
    assert any('factor de costo 0.5' in c for c in por['L-1']['causas'])
    assert por['E-1']['conversor'] == pytest.approx(450.0) and por['E-1']['relacion_comparable'] == pytest.approx(0.9)
    assert any('costo básico' in c for c in por['E-1']['causas'])
    assert all(any('RESUMEN MODULOS X' in c for c in e['causas']) for e in r['elementos'] if e['conversor'])
    assert r['completa'] is False and [s['elemento'] for s in r['sin_costo']] == ['E-2']
    assert r['total_por_moneda'] == {'USD': pytest.approx(10_450.0)} and r['base']['resolucion'] == 'R-2'


def _docx(ruta: Path, titulos, estilo=True) -> Path:
    import docx
    d = docx.Document()
    for nivel, texto in titulos:
        if estilo:
            d.add_heading(texto, level=nivel)
        else:
            d.add_paragraph().add_run(texto).bold = True
        d.add_paragraph('Texto del capítulo.')
    d.save(ruta)
    return ruta


def test_los_titulos_se_leen_del_nivel_que_usa_el_documento(tmp_path):
    """072:RF-21 (T11) — capítulos con «Heading 2» o en negrita: el nivel no se supone."""
    ap = _ap()
    oficial = _docx(tmp_path / 'oficial.docx', [(2, 'OBJETIVO'), (3, 'Detalle'), (2, 'EVALUACIÓN ECONÓMICA')])
    assert [t['titulo'] for t in ap.titulos_de_docx(oficial)] == ['OBJETIVO', 'EVALUACIÓN ECONÓMICA']
    assert len(ap.titulos_de_docx(oficial, niveles=2)) == 3
    propio = _docx(tmp_path / 'propio.docx', [(1, 'PIDE: EVALUACIÓN ECONÓMICA'), (1, 'Metodología')], estilo=False)
    assert [t['titulo'] for t in ap.titulos_de_docx(propio)] == ['PIDE: EVALUACIÓN ECONÓMICA', 'Metodología']


def test_el_acta_dice_que_capitulo_oficial_cubre_cada_modulo_y_nombra_los_huecos():
    """072:RF-4, RF-13, RF-14, RF-21 (T11) — cada capítulo oficial, cubierto por un módulo o hueco nombrado; con origen."""
    ap = _ap()
    oficiales = {'Plan de largo plazo': [{'nivel': 1, 'titulo': 'DIAGNÓSTICO DE LOS SISTEMAS EXISTENTES'},
                                         {'nivel': 1, 'titulo': 'CRITERIOS Y METODOLOGÍAS'},
                                         {'nivel': 1, 'titulo': 'ANTECEDENTES'}],
                 'PIDE': [{'nivel': 1, 'titulo': 'EVALUACION ECONOMICA'}]}
    conversor = {'1_diagnostico': ['PLAN DE LARGO PLAZO: DIAGNÓSTICO', 'Metodología', 'Resultados'],
                 '5_evaluacion': ['PIDE: EVALUACIÓN ECONÓMICA', 'Metodología'],
                 '9_otro': ['PIDE: PROPUESTA']}
    acta = ap.acta_de_estructura(oficiales, conversor, revisor='revisor-b', fecha='2030-01-15')
    por = {c['capitulo']: c for c in acta['capitulos']}
    assert por['DIAGNÓSTICO DE LOS SISTEMAS EXISTENTES']['modulo'] == '1_diagnostico'
    assert por['CRITERIOS Y METODOLOGÍAS']['modulo'] in ('1_diagnostico', '5_evaluacion')  # plural = singular
    assert por['EVALUACION ECONOMICA']['modulo'] == '5_evaluacion'
    assert acta['huecos'] == ['ANTECEDENTES'] and por['ANTECEDENTES']['estado'].startswith('hueco nombrado')
    assert acta['modulos_sin_capitulo'] == ['9_otro'] and acta['origen'] == 'maestro/revisor independiente'
    with pytest.raises(ValueError, match='revisor'):
        ap.acta_de_estructura(oficiales, conversor, revisor='', fecha='2030-01-15')
