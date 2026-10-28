"""Spec 027, T20: ejemplos del agente desde un corpus PIDE sintético."""
from __future__ import annotations

import json
from pathlib import Path

from igea_dgs.asistente import ejemplos_pide as ep
from igea_dgs.pide_dataset import cargar_contrato, clasificar_ruta

RAIZ = Path(__file__).resolve().parents[1]
CONTRATO = cargar_contrato(RAIZ / 'config' / 'pide_universal_2017.json')


def _jsonl(path: Path, filas: list[dict]) -> None:
    path.write_text(''.join(json.dumps(f, ensure_ascii=False) + '\n' for f in filas), encoding='utf-8')


def test_formatos_de_ruta_y_titulos():
    """027:RF-48 / 027:RF-50 — los formatos que nombra una ruta y los títulos de sección."""
    assert ep.formatos_de_ruta('X/FORMATO 3.xlsx') == ['F03']
    assert ep.formatos_de_ruta('Anexo 04 - Formato N° 10 PIDE.xlsx') == ['F10']
    assert ep.formatos_de_ruta('Formatos N° 08 al N° 15 (por sede)/a.xlsx')[0] == 'F08'
    assert len(ep.formatos_de_ruta('BASE DE DATOS K-(F) 8-13.xlsx')) == 6
    assert ep.formatos_de_ruta('Tabla N°02.xlsx') == [] and ep.formatos_de_ruta('FORMATO 22.xlsx') == []
    assert ep.titulo_de_seccion('3.1 CRITERIOS DE PLANIFICACIÓN 9') == ('3.1', 'CRITERIOS DE PLANIFICACIÓN')
    assert ep.titulo_de_seccion('1 Producto bruto interno 3,3 3,1') is None
    assert ep.titulo_de_seccion('2 China 19,5 5,0') is None


def test_diagnostico_con_tilde_se_clasifica():
    """027:RF-48 — «Diagnóstico» en la ruta da el artículo 8 (antes nunca coincidía)."""
    assert clasificar_ruta('PIDE 2026/11.2 RESULTADOS DEL DIAGNÓSTICO/x.xlsx').articulos == (8,)
    assert clasificar_ruta('PIDE 2026/Pérdidas técnicas/x.xlsx').articulos == (8,)


def test_ejemplos_por_articulo_formato_e_informe(tmp_path):
    """027:RF-47 / 027:RF-48 / 027:RF-50 — por artículo, sus ejemplos de cada PIDE; por formato,
    las hojas y columnas entregadas o dicho ausente; las secciones de 4.1 y 4.2."""
    art8 = next(a for a in CONTRATO.articulos if a.numero == 8)
    texto8 = ' '.join([art8.titulo, *art8.evidencias, *art8.entregables])
    _jsonl(tmp_path / 'fragments.jsonl', [
        {'relative_path': 'PIDE 2021/Informes/2/diag.docx', 'periodo': '2021', 'articulos': [], 'text': texto8},
        {'relative_path': 'PIDE 2026/4.1 INFORME DE LARGO PLAZO/inf.docx', 'periodo': '2026', 'articulos': [7],
         'text': '1 OBJETIVOS 3\n4 ANÁLISIS DEL MERCADO ELÉCTRICO 12\n1 Producto bruto interno 3,3 3,1'},
        {'relative_path': 'PIDE 2026/4.2 INFORME PIDE/pide.pdf', 'periodo': '2026', 'articulos': [],
         'text': '6.3 ANALISIS DE CAIDA DE TENSION 9'},
        {'relative_path': 'otro.txt', 'periodo': '', 'articulos': [], 'text': 'nada que ver'}])
    _jsonl(tmp_path / 'assets.jsonl', [
        {'kind': 'xlsx_sheet', 'relative_path': 'PIDE 2026/D.4/FORMATO 1.xlsx', 'sheet': 'SE0017',
         'cabecera': ['Nombre:', 'Año', 'Energía'], 'periodo': '2026'},
        {'kind': 'gis_layer', 'relative_path': 'GIS/capa.shp'}])
    d = ep.construir(tmp_path, CONTRATO)
    assert d['fragmentos'] == 4 and d['fragmentos_con_articulo'] >= 2
    assert d['articulos']['8']['ejemplos']['2021'][0]['fuente'] == 'PIDE 2021/Informes/2/diag.docx'
    assert d['articulos']['7']['cubierto']
    assert all((n in d['cobertura']['articulos_ausentes']) == (not a['cubierto']) for n, a in d['articulos'].items())
    f01 = d['formatos']['F01']
    assert not f01['ausente'] and f01['entregado'][0]['columnas'] == ['Nombre:', 'Año', 'Energía']
    assert d['formatos']['F02']['ausente'] and 'F02' in d['cobertura']['formatos_ausentes']
    assert [s['titulo'] for s in d['informes']['4.1']['secciones']] == ['OBJETIVOS', 'ANÁLISIS DEL MERCADO ELÉCTRICO']
    assert d['informes']['4.2']['secciones'][0]['numero'] == '6.3'
    assert 'no norma' in d['nota']
    assert any('Formatos entregados: 1 de 15' in x for x in ep.resumen(d))
