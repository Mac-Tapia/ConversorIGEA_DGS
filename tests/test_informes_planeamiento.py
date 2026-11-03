"""Spec 072: un documento ligero por módulo, todos de un mismo estudio y para una empresa de prueba."""
from __future__ import annotations

import json
from pathlib import Path

import docx
import pytest

from convertersmartgrid.estudio_planeamiento import estudio_de
from convertersmartgrid.formatos_pide import formatos_del_estudio
from convertersmartgrid.informes import InformeError
from convertersmartgrid.informes_planeamiento import (
    MODULOS,
    TAMANO_DE_TABLA,
    TOPE_DE_FILAS,
    DatosPlaneamiento,
    escribir_modulo,
    escribir_modulos,
)
from convertersmartgrid.pide import FORMATOS
from convertersmartgrid.proyeccion_mercado import SerieMercado

METODOLOGIA = json.loads((Path(__file__).resolve().parent.parent / 'config/pide_universal_2017.json').read_text(encoding='utf-8'))
HORIZONTE = {'ciclo_anios': 4, 'largo_plazo': [4, 8], 'detalle_pide': [4, 5]}
MODULO = {m.clave: m for m in MODULOS}


def _obra(codigo, anio, ci=1000.0, prioridad=1, **extra):
    return {'codigo': codigo, 'anio': anio, 'alternativa': 'bancos', 'rubro': 'calidad', 'alimentador': 'F1', 'elemento': 'B9',
            'causa': 'caida_de_tension', 'denominacion': None, 'ci': ci, 'kw_nuevos': 100.0, 'energia_kwh': 400000.0,
            'indicadores': {}, 'privada': None, 'descartada': False, 'sobredimensionada': False, 'prioridad': prioridad,
            'puntaje': 0.5, 'regulada': {'anualidad': ci * 0.12, 'costo_anual': ci * 0.13}, **extra}


def _datos(**extra):
    estudio = estudio_de(2031, HORIZONTE)
    obras = [_obra('AL01', 4, variacion_autonoma='V1'), _obra('AL02', 8, prioridad=2)]
    anios = [{'anio': 0, 'converge': True, 'vm_min': 0.95, 'problemas': 2, 'perdidas_kw': 40.0, 'cabeceras_kw': {'F1': 1000.0}},
             {'anio': 4, 'converge': True, 'vm_min': 0.93, 'problemas': 3, 'perdidas_kw': 55.0, 'cabeceras_kw': {'F1': 1200.0},
              'con_proyecto': {'obras': ['V1'], 'converge': True, 'problemas': [], 'perdidas_kw': 50.0}}]
    serie = SerieMercado('SE1', 'Sistema de prueba', 'ST2', {2028: 100.0, 2029: 110.0, 2030: 121.0})
    formatos = formatos_del_estudio(obras, anios, estudio=estudio, series=[serie], factor_carga=0.5,
                                    sistema_de={'F1': 'SE1'}, centro_de={'F1': 'SET A'})
    base = {'estudio': estudio, 'formatos': formatos, 'articulos': METODOLOGIA['articulos'], 'anios': anios, 'obras': obras,
            'empresa': 'Empresa de prueba', 'proyecto': 'Proyecto de prueba', 'metodo_proyeccion': 'tasa_media',
            'con_y_sin': {'van': 123.5, 'tir': 0.1, 'avisos': ['aviso de prueba']}}
    return DatosPlaneamiento(**{**base, **extra})


def _texto(ruta):
    d = docx.Document(ruta)
    celdas = [c.text for t in d.tables for f in t.rows for c in f.cells]
    return '\n'.join([p.text for p in d.paragraphs] + celdas)


def _modulo(tmp_path, clave, **extra):
    ruta = tmp_path / f'{clave}.docx'
    escribir_modulo(ruta, MODULO[clave], _datos(**extra))
    return _texto(ruta)


def test_los_modulos_en_el_orden_del_usuario_y_con_los_formatos_de_la_metodologia():
    """072:RF-21 — dos del plan y cinco del PIDE; ningún formato se queda sin módulo ni va en dos."""
    assert [m.clave for m in MODULOS] == ['diagnostico', 'alternativas', 'formulacion_pide', 'evaluacion_tecnica',
                                          'evaluacion_economica', 'priorizacion', 'propuesta_pide']
    assert [m.entregable for m in MODULOS] == ['Plan de largo plazo'] * 2 + ['PIDE'] * 5
    formatos = [f for m in MODULOS for f in m.formatos]
    assert sorted(formatos) == sorted(n.split()[0] for n in FORMATOS)
    articulos = {a['numero']: a for a in METODOLOGIA['articulos']}
    for m in MODULOS:
        de_sus_articulos = {x for n in m.articulos for x in articulos[n]['entregables'] if x in {f.split()[0] for f in FORMATOS}}
        assert de_sus_articulos == set(m.formatos), m.clave


def test_cada_modulo_sigue_su_articulo_paso_a_paso(tmp_path):
    """072:RF-21 — con las palabras de la metodología, y solo las suyas."""
    texto = _modulo(tmp_path, 'evaluacion_tecnica')
    assert 'simular y verificar solución de restricciones' in texto and 'convergencia, límites y lectura posterior' in texto
    assert 'calcular indicadores con moneda y año base' not in texto, 'ese paso es de la evaluación económica'


def test_el_diagnostico_lleva_sus_formatos_y_es_ligero(tmp_path):
    """072:RF-13 / 072:RF-21 — mercado y diagnóstico con F01 a F06; nada de los otros módulos."""
    texto = _modulo(tmp_path, 'diagnostico')
    for parte in ('mercado', 'tasa_media', 'Sistema de prueba', 'Empresa de prueba', '2030', 'no lleva la baja tensión',
                  'F01', 'F02', 'F03', 'F04', 'F05', 'F06'):
        assert parte in texto, parte
    assert 'F07' not in texto and 'AL01' not in texto and 'Prioridad' not in texto


def test_las_alternativas_con_su_formato_y_plan(tmp_path):
    """072:RF-13 — F07 con todas las obras y el plan de largo plazo, también la posterior al PIDE."""
    texto = _modulo(tmp_path, 'alternativas')
    assert 'F07 Alternativas estudio' in texto and 'Plan de obras' in texto and 'AL01' in texto and 'AL02' in texto


@pytest.mark.parametrize('clave, formatos', [('formulacion_pide', ('F08',)), ('evaluacion_economica', ('F09',)),
                                             ('propuesta_pide', ('F10', 'F11', 'F12', 'F13', 'F14', 'F15'))])
def test_el_pide_se_queda_con_su_periodo(tmp_path, clave, formatos):
    """072:RF-14 — la obra del año 04 sí; la del año 08 es de largo plazo."""
    texto = _modulo(tmp_path, clave)
    for codigo in formatos:
        assert codigo in texto, codigo
    assert 'AL01' in texto and 'AL02' not in texto


def test_evaluacion_tecnica_compara_con_y_sin_obras(tmp_path):
    """072:RF-14 — los dos casos del mismo año, y sin obras aplicadas lo dice."""
    texto = _modulo(tmp_path, 'evaluacion_tecnica')
    assert 'Problemas con obras' in texto and 'V1' in texto and '50.00' in texto and '55.00' in texto
    assert 'Sin medir' in _modulo(tmp_path, 'evaluacion_tecnica', anios=[])


def test_evaluacion_economica_con_y_sin_datos(tmp_path):
    """072:RF-14 / 072:RF-16 — VAN, TIR y su alcance; sin caso con obras, el motivo y ninguna cifra."""
    texto = _modulo(tmp_path, 'evaluacion_economica')
    for parte in ('VAN', '10.00%', 'Costo anual US$', 'aviso de prueba', 'Solo mide el ahorro de pérdidas'):
        assert parte in texto, parte
    sin = _modulo(tmp_path, 'evaluacion_economica', con_y_sin={'hueco': 'faltan las pérdidas de «Con proyecto»'})
    assert 'Sin evaluar: faltan las pérdidas' in sin and 'VAN US$ (tasa regulada)' not in sin


def test_priorizacion_conserva_lo_descartado(tmp_path):
    """072:RF-14 — el art. 15 pide conservar las alternativas rechazadas."""
    estudio = _datos()
    obras = [_obra('AL01', 4), _obra('AL03', 4, prioridad=2, descartada=True)]
    texto = _modulo(tmp_path, 'priorizacion', obras=obras, formatos=estudio.formatos)
    assert 'seleccionada' in texto and 'descartada' in texto and 'AL03' in texto


def test_todos_salen_del_mismo_estudio(tmp_path):
    """072:RF-4 — una sola llamada escribe los siete con las mismas cifras de la obra."""
    hechos, fallos = escribir_modulos(tmp_path, 'prueba', _datos())
    assert fallos == [] and len(hechos) == len(MODULOS) and hechos[0] == '1_diagnostico_prueba.docx'
    alternativas, propuesta = _texto(tmp_path / hechos[1]), _texto(tmp_path / hechos[6])
    assert '1,000.00' in alternativas and '1,000.00' in propuesta
    for nombre in hechos:
        assert 'Año base (00): 2030' in _texto(tmp_path / nombre)
        resumen = json.loads((tmp_path / nombre).with_suffix('.json').read_text(encoding='utf-8'))
        assert resumen['modulo'] in MODULO


def test_lo_propio_de_la_empresa_viene_de_fuera(tmp_path):
    """072:RF-17 — sin nombre de empresa queda el hueco; el modelo es el del perfil y si falta se dice."""
    assert any('empresa' in h for h in escribir_modulo(tmp_path / 'a.docx', MODULOS[0], _datos(empresa=None)))
    with pytest.raises(InformeError, match='No existe el modelo'):
        escribir_modulo(tmp_path / 'b.docx', MODULOS[0], _datos(modelo=tmp_path / 'no_esta.docx'))
    hechos, fallos = escribir_modulos(tmp_path, 'x', _datos(modelo=tmp_path / 'no_esta.docx'))
    assert hechos == [] and len(fallos) == len(MODULOS), 'un fallo se informa, no se traga'
    modelo = tmp_path / 'modelo.docx'
    d = docx.Document()
    d.add_paragraph('cuerpo del modelo que se vacía')
    d.save(modelo)
    escribir_modulo(tmp_path / 'c.docx', MODULO['priorizacion'], _datos(modelo=modelo))
    assert 'cuerpo del modelo' not in _texto(tmp_path / 'c.docx')


def test_lo_que_falta_es_ligero_y_de_lo_que_se_muestra(tmp_path):
    """072:RF-16 / 072:RF-21 — un motivo por formato, y el PIDE no cuenta las obras fuera de su periodo."""
    ruta = tmp_path / 'p.docx'
    escribir_modulo(ruta, MODULO['propuesta_pide'], _datos())
    d = docx.Document(ruta)
    faltan = d.tables[-1]
    assert [c.text for c in faltan.rows[0].cells] == ['Formato', 'Campos', 'Motivo']
    filas_f13 = [f for f in faltan.rows if f.cells[0].text == 'F13 Detalle de costos']
    assert len(filas_f13) == 1 and 'LP, RP, Reforzamiento' in filas_f13[0].cells[1].text
    resumen = json.loads(ruta.with_suffix('.json').read_text(encoding='utf-8'))
    assert {h['filas'] for h in resumen['huecos'] if h['formato'] == 'F13 Detalle de costos'} == {1}


def test_las_tablas_anchas_caben(tmp_path):
    """072:RF-21 — en blanco va apaisado y las tablas con letra menor: F13 tiene 15 columnas."""
    ruta = tmp_path / 'p.docx'
    escribir_modulo(ruta, MODULO['propuesta_pide'], _datos())
    d = docx.Document(ruta)
    assert d.sections[0].page_width > d.sections[0].page_height
    trozo = d.tables[0].rows[0].cells[0].paragraphs[0].runs[0]
    assert trozo.font.size.pt == TAMANO_DE_TABLA


def test_un_formato_largo_se_corta_y_lo_avisa(tmp_path):
    """072:RF-21 — el Word no lleva miles de filas, pero dice que las demás están en el libro."""
    datos = _datos()
    largas = [['SET A', f'F{i}', None, 1.0, None, None, None, None] for i in range(TOPE_DE_FILAS + 5)]
    filas = {**datos.formatos['filas'], 'F03 Tensión MT': largas}
    texto = _modulo(tmp_path, 'diagnostico', formatos={**datos.formatos, 'filas': filas})
    assert f'Se muestran {TOPE_DE_FILAS} de {TOPE_DE_FILAS + 5} filas' in texto
