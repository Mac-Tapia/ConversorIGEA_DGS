"""Spec 072: los dos entregables salen de un mismo estudio, para una empresa de prueba."""
from __future__ import annotations

import json

import docx
import pytest

from convertersmartgrid.estudio_planeamiento import estudio_de
from convertersmartgrid.formatos_pide import formatos_del_estudio
from convertersmartgrid.informes import InformeError
from convertersmartgrid.informes_planeamiento import (
    TOPE_DE_FILAS,
    DatosPlaneamiento,
    escribir_informe_largo_plazo,
    escribir_informe_pide,
)
from convertersmartgrid.proyeccion_mercado import SerieMercado

HORIZONTE = {'ciclo_anios': 4, 'largo_plazo': [4, 8], 'detalle_pide': [4, 5]}


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
    base = {'estudio': estudio, 'formatos': formatos, 'anios': anios, 'obras': obras, 'empresa': 'Empresa de prueba',
            'proyecto': 'Proyecto de prueba', 'metodo_proyeccion': 'tasa_media',
            'con_y_sin': {'van': 123.5, 'tir': 0.1, 'avisos': ['aviso de prueba']}}
    return DatosPlaneamiento(**{**base, **extra})


def _texto(ruta):
    d = docx.Document(ruta)
    celdas = [c.text for t in d.tables for f in t.rows for c in f.cells]
    return '\n'.join([p.text for p in d.paragraphs] + celdas)


def test_el_largo_plazo_lleva_lo_que_pide_la_spec(tmp_path):
    """072:RF-13 — mercado, diagnóstico, alternativas, técnico-económico, plan de obras y F01 a F07."""
    ruta = tmp_path / 'lp.docx'
    assert escribir_informe_largo_plazo(ruta, _datos()) == []
    texto = _texto(ruta)
    for parte in ('ANÁLISIS DEL MERCADO', 'DIAGNÓSTICO', 'ALTERNATIVAS', 'PLAN DE OBRAS', 'tasa_media', 'Empresa de prueba',
                  'Sistema de prueba', 'F07 Alternativas estudio', '2030'):
        assert parte in texto, parte
    for codigo in ('F01', 'F02', 'F03', 'F04', 'F05', 'F06', 'F07'):
        assert codigo in texto, codigo
    assert 'F12 Propuesta' not in texto, 'los formatos del PIDE no van aquí'
    assert 'no lleva la baja tensión' in texto, 'F04 dice por qué está vacío'
    assert json.loads(ruta.with_suffix('.json').read_text(encoding='utf-8'))['tipo'] == 'largo_plazo'


def test_el_pide_lleva_su_periodo_y_su_evaluacion(tmp_path):
    """072:RF-14 — alternativas, con y sin proyecto, VAN, TIR, costo anual, priorización y F08 a F15."""
    ruta = tmp_path / 'pide.docx'
    escribir_informe_pide(ruta, _datos())
    texto = _texto(ruta)
    for parte in ('CON Y SIN PROYECTO', 'VAN', 'TIR', '10.00%', 'PRIORIZACIÓN', 'Costo anual US$', 'aviso de prueba',
                  'Solo mide el ahorro de pérdidas'):
        assert parte in texto, parte
    for codigo in ('F08', 'F09', 'F10', 'F11', 'F12', 'F13', 'F14', 'F15'):
        assert codigo in texto, codigo
    assert 'AL01' in texto
    assert 'AL02' not in texto, 'la obra del año 08 es de largo plazo, no del periodo del PIDE'
    assert 'F07 Alternativas' not in texto


def test_los_dos_salen_del_mismo_estudio(tmp_path):
    """072:RF-4 — con los mismos datos, el PIDE y el largo plazo dan las mismas cifras de la obra."""
    datos = _datos()
    escribir_informe_largo_plazo(tmp_path / 'lp.docx', datos)
    escribir_informe_pide(tmp_path / 'pide.docx', datos)
    lp, pide = _texto(tmp_path / 'lp.docx'), _texto(tmp_path / 'pide.docx')
    for comun in ('Año base (00): 2030', 'Empresa de prueba', '1,000.00'):
        assert comun in lp and comun in pide, comun


def test_sin_evaluacion_lo_dice_sin_inventarla(tmp_path):
    """072:RF-16 — sin caso con obras, ni VAN ni TIR: el motivo."""
    ruta = tmp_path / 'p.docx'
    escribir_informe_pide(ruta, _datos(con_y_sin={'hueco': 'faltan las pérdidas de «Con proyecto»'}, anios=[]))
    texto = _texto(ruta)
    assert 'Sin evaluar: faltan las pérdidas' in texto and 'VAN US$ (tasa regulada)' not in texto
    assert 'Sin medir' in texto


def test_lo_propio_de_la_empresa_viene_de_fuera(tmp_path):
    """072:RF-17 — sin nombre de empresa queda el hueco; el modelo es el del perfil y si falta se dice."""
    ruta = tmp_path / 'lp.docx'
    assert any('empresa' in h for h in escribir_informe_largo_plazo(ruta, _datos(empresa=None)))
    with pytest.raises(InformeError, match='No existe el modelo'):
        escribir_informe_pide(tmp_path / 'p.docx', _datos(modelos={'pide': tmp_path / 'no_esta.docx'}))
    modelo = tmp_path / 'modelo.docx'
    d = docx.Document()
    d.add_paragraph('cuerpo del modelo que se vacía')
    d.save(modelo)
    escribir_informe_pide(ruta, _datos(modelos={'pide': modelo}))
    assert 'cuerpo del modelo' not in _texto(ruta) and 'PRIORIZACIÓN' in _texto(ruta)


def test_un_formato_largo_se_corta_y_lo_avisa(tmp_path):
    """072:RF-13 — el Word no lleva miles de filas, pero dice que las demás están en el libro."""
    datos = _datos()
    largas = [['SET A', f'F{i}', None, 1.0, None, None, None, None] for i in range(TOPE_DE_FILAS + 5)]
    filas = {**datos.formatos['filas'], 'F03 Tensión MT': largas}
    ruta = tmp_path / 'lp.docx'
    escribir_informe_largo_plazo(ruta, _datos(formatos={**datos.formatos, 'filas': filas}))
    texto = _texto(ruta)
    assert f'Se muestran {TOPE_DE_FILAS} de {TOPE_DE_FILAS + 5} filas' in texto
