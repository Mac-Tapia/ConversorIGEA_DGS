"""Spec 066: el libro de cada informe, con un modelo pequeño y un sustituto de Excel que aplica el plan."""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import docx
import openpyxl

from convertersmartgrid.libro_informe import (ConfigLibro, comprobar_libro, generar_libro, plan_del_libro,
                                              rellenar_con_excel)

PERFIL = {'informes': {'modelo_libro': 'modelo.xlsx', 'libro_informe': {
    'celdas': {'cliente': 'Informe!C4', 'alimentador': 'Informe!C8', 'precio_compra': 'Informe!G9',
               'conclusion': ['Informe!B20', 'Otra!B1'], 'expediente': 'Informe!C10'},
    'textos': {'Informe!B2': 'RED {alimentador}'}, 'formulas': {'Informe!E5': '=Datos!A1'},
    'bloque_hoja': 'Datos', 'desplazamiento': 10, 'bloque': {'kw': 'A1', 'perdidas_mwh': 'A2'},
    'imagenes': {'actual.tension': 'Informe!E30'}, 'vaciar': ['Informe!B30'],
    'sin_dato': {'capacidad': ['Informe!H1']}, 'borrar_hojas': ['Oculta'], 'sin_imagenes': ['Informe'],
    'catalogo': ['Catalogo'], 'prohibidos': ['EMAPICA'], 'control': {'actual': 'Informe!G11'}}}}
RESUMEN = {'solicitud': {'cliente': 'CLIENTE X', 'alimentador': 'AL01', 'tension_kv': 10.0, 'expediente': None},
           'libro': {'precio_compra': 0.2},
           'actual': {'converge': True, 'fuente': {'kw': 100.0, 'kvar': 0.0}, 'perdidas': {'kw': 5.0, 'kvar': 1.0},
                      'tension_min': {'trifásica': {'valor': 0.96, 'donde': 'N1'}}, 'tension_max': {'valor': 1.02, 'donde': 'C'}},
           'proyectado': {'converge': True, 'fuente': {'kw': 120.0, 'kvar': 0.0}, 'perdidas': {'kw': 6.0, 'kvar': 1.0}},
           'perdidas': {'actual': {'perdidas_kwh': 2000.0, 'energia_kwh': 438000.0, 'maxima_kw': 100.0,
                                   'no_reconocida_soles': 50.0}}}


def _config(tmp_path):
    return ConfigLibro.de_perfil(PERFIL, tmp_path)


def _modelo(tmp_path):
    libro = openpyxl.Workbook()
    i = libro.active
    i.title = 'Informe'
    i['C4'], i['B2'], i['B30'], i['H1'], i['G9'] = 'EMAPICA', 'RED LL202', 'dato de EMAPICA', 240, 0.5
    i['F7'] = '=C4'                                                 # una fórmula que el perfil no declara
    i['G11'] = 50.0
    for nombre in ('Datos', 'Otra', 'Oculta', 'Catalogo'):
        libro.create_sheet(nombre)
    libro['Oculta']['A1'] = 'EMAPICA'
    libro['Catalogo']['A1'] = 'EMAPICA'
    libro.save(tmp_path / 'modelo.xlsx')


def _excel_de_prueba(orden):
    """Aplica el plan con openpyxl: en las pruebas no hay Excel, y aquí no importa lo que pierde al guardar."""
    plan = json.loads(Path(re.search(r"-LiteralPath '([^']+)'", orden).group(1)).read_text(encoding='utf-8'))
    libro = openpyxl.load_workbook(plan['modelo'])
    for h in plan['borrar_hojas']:
        del libro[h]

    def celda(ref):
        hoja, c = ref.rsplit('!', 1)
        return libro[hoja], c

    for ref in plan['vaciar']:
        hoja, c = celda(ref)
        hoja[c] = None
    for e in plan['escribir']:
        hoja, c = celda(e['celda'])
        hoja[c] = e['valor']
    for e in plan['formulas']:
        hoja, c = celda(e['celda'])
        hoja[c] = e['formula']
    libro.save(plan['destino'])
    return SimpleNamespace(returncode=0, stderr='')


def _word(tmp_path):
    d = docx.Document()
    d.add_paragraph('2. DESCRIPCIÓN')
    d.add_paragraph('3. CONCLUSIONES')
    d.add_paragraph('La conexión es factible.')
    ruta = tmp_path / 'informe.docx'
    d.save(ruta)
    return ruta


def test_sin_seccion_en_el_perfil_no_hay_libro(tmp_path):
    """066:RF-2 — el libro es de una empresa: otra no lo hereda ni lo ve como hueco."""
    assert ConfigLibro.de_perfil({'informes': {'norma': 'X'}}, tmp_path) is None
    assert ConfigLibro.de_perfil({}, tmp_path) is None


def test_las_celdas_salen_del_perfil_y_lo_que_falta_es_hueco(tmp_path):
    """066:RF-1, 066:RF-4, 066:RF-8 — otro plano, otras celdas; el expediente vacío se nombra y su celda se vacía."""
    plan = plan_del_libro(_config(tmp_path), RESUMEN, destino=tmp_path / 'a.xlsx', conclusion='Factible.')
    escrito = {e['celda']: e['valor'] for e in plan['escribir']}
    assert escrito['Informe!C4'] == 'CLIENTE X' and escrito['Informe!G9'] == 0.2 and escrito['Informe!B2'] == 'RED AL01'
    assert escrito['Datos!A1'] == 100.0 and escrito['Datos!A11'] == 120.0, 'el bloque proyectado va desplazado'
    assert escrito['Otra!B1'] == 'Factible.' and escrito['Informe!B20'] == 'Factible.'
    assert 'Informe!C10' in plan['vaciar'] and 'expediente' in plan['huecos'] and 'capacidad' in plan['huecos']
    otro = {'informes': {'modelo_libro': 'm.xlsx', 'libro_informe': {'celdas': {'cliente': 'Hoja!Z9'}}}}
    assert plan_del_libro(ConfigLibro.de_perfil(otro, tmp_path), RESUMEN, destino=tmp_path / 'b.xlsx')['escribir'] == [
        {'celda': 'Hoja!Z9', 'valor': 'CLIENTE X'}]


def test_los_datos_de_fichas_llenan_el_grupo_sin_dato(tmp_path):
    """066:RF-13: con los datos en el informe, se escriben, su celda no se vacía y deja de ser hueco."""
    r = {**RESUMEN, 'datos_sin_dato': {'capacidad': {'Informe!H1': 370}}}
    plan = plan_del_libro(_config(tmp_path), r, destino=tmp_path / 'f.xlsx')
    assert {'celda': 'Informe!H1', 'valor': 370} in plan['escribir']
    assert 'Informe!H1' not in plan['vaciar'] and 'capacidad' not in plan['huecos']
    sin = plan_del_libro(_config(tmp_path), RESUMEN, destino=tmp_path / 'g.xlsx')
    assert 'Informe!H1' in sin['vaciar'] and 'capacidad' in sin['huecos']


def test_libro_generado_sin_nada_del_modelo_y_con_sus_formulas(tmp_path):
    """066:RF-1, 066:RF-5, 066:RF-6, 066:RF-7 — hoja oculta fuera, texto del modelo vacío, fórmula ajena intacta."""
    _modelo(tmp_path)
    hecho = generar_libro(_config(tmp_path), _word(tmp_path), RESUMEN, ejecutar=_excel_de_prueba)
    assert hecho.ruta == tmp_path / 'informe.xlsx' and hecho.motivo == ''
    assert hecho.avisos == (), 'el catálogo de la empresa puede nombrar a EMAPICA; lo demás no'
    libro = openpyxl.load_workbook(hecho.ruta)
    assert 'Oculta' not in libro.sheetnames and libro['Informe']['F7'].value == '=C4'
    assert libro['Informe']['B30'].value is None and libro['Informe']['H1'].value is None
    assert libro['Informe']['B20'].value == 'La conexión es factible.', 'dice lo mismo que el Word'


def test_lo_que_queda_del_modelo_y_los_errores_se_avisan(tmp_path):
    """066:RF-7 — nombra la hoja y la celda."""
    libro = openpyxl.Workbook()
    libro.active.title = 'Informe'
    libro['Informe']['B3'], libro['Informe']['B4'] = 'Bomba de EMAPICA', '#REF!'
    libro.create_sheet('Catalogo')['A1'] = 'EMAPICA'
    libro['Informe']['G11'] = 50.0
    libro.save(tmp_path / 'x.xlsx')
    avisos = comprobar_libro(_config(tmp_path), tmp_path / 'x.xlsx', RESUMEN)
    assert any('Informe!B3' in a for a in avisos) and any('Informe!B4 da #REF!' in a for a in avisos)
    assert not any('Catalogo' in a for a in avisos)


def test_el_importe_que_no_cuadra_con_el_informe_se_avisa(tmp_path):
    """066:RF-10 — el mismo cálculo no puede dar dos importes; 1 S/. de margen."""
    libro = openpyxl.Workbook()
    libro.active.title = 'Informe'
    libro['Informe']['G11'] = 50.5
    libro.save(tmp_path / 'x.xlsx')
    assert comprobar_libro(_config(tmp_path), tmp_path / 'x.xlsx', RESUMEN) == []
    libro['Informe']['G11'] = 80.0
    libro.save(tmp_path / 'x.xlsx')
    assert any('Informe!G11 da 80' in a for a in comprobar_libro(_config(tmp_path), tmp_path / 'x.xlsx', RESUMEN))


def test_sin_excel_se_dice_el_motivo(tmp_path):
    """066:RF-9 — el Word no se pierde; tampoco vale un libro de otra vez."""
    _modelo(tmp_path)
    falla = lambda _o: SimpleNamespace(returncode=1, stderr='sin Excel')
    w = _word(tmp_path)
    hecho = generar_libro(_config(tmp_path), w, RESUMEN, ejecutar=falla)
    assert hecho.ruta is None and hecho.motivo == 'sin Excel' and w.is_file()
    assert generar_libro(ConfigLibro.de_perfil({'informes': {'libro_informe': {}}}, tmp_path), w, RESUMEN).ruta is None
    def rota(_o):
        raise OSError('no hay PowerShell')
    assert 'no se pudo abrir Excel' in rellenar_con_excel({'destino': str(tmp_path / 'z.xlsx')}, ejecutar=rota)[1]


def test_estudio_toma_la_ultima_etapa(tmp_path):
    """066:RF-12 — el informe de estudio no tiene ``proyectado``: su estado final es la última etapa."""
    r = {'alimentadores': ['AL01'], 'actual': RESUMEN['actual'], 'etapas': [
        {'caso': {'converge': True, 'fuente': {'kw': 1.0, 'kvar': 0.0}, 'perdidas': {'kw': 0.1, 'kvar': 0.0}}},
        {'caso': RESUMEN['proyectado']}]}
    escrito = {e['celda']: e['valor'] for e in plan_del_libro(_config(tmp_path), r, destino=tmp_path / 'e.xlsx')['escribir']}
    assert escrito['Datos!A11'] == 120.0 and escrito['Informe!C8'] == 'AL01'


def test_web_ofrece_el_libro_junto_al_word():
    """066:RF-11 — el enlace y los avisos están en el resultado del informe."""
    raiz = Path(__file__).resolve().parents[1]
    front = (raiz / 'frontend/src/components/InformesPF.tsx').read_text(encoding='utf-8')
    assert 'Descargar libro' in front and 'Sin libro:' in front and 'Revise el libro:' in front
    servicios = (raiz / 'src/convertersmartgrid/web/services.py').read_text(encoding='utf-8')
    assert servicios.count('_libro_del_informe(ctx, destino,') == 2
    assert 'celda_precio' not in servicios and 'G183' not in servicios, 'las celdas van en el perfil'
