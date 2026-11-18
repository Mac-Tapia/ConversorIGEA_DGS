"""Spec 108 T22 — el Informe Definitivo (numeral 9.2): los documentos que lista el registro, con el informe de las
respuestas a las observaciones, cada una con su sustento y la tabla o el cálculo que cambió (108:RF-12).

Empresa, observaciones y estudio sintéticos; la lista de documentos y las tablas salen del registro real del TdR
(``config/vad``). Ningún nombre, número de oficio ni periodo de una empresa real.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from convertersmartgrid.dominio.perfil_empresa import PerfilEmpresa
from convertersmartgrid.dominio.registro_normativo import cargar_registro
from convertersmartgrid.aplicacion.vad import VadError
from convertersmartgrid.aplicacion.vad.estudio import crear_estudio
from convertersmartgrid.adaptadores.vad.observaciones import registrar_observacion, responder

RAIZ = Path(__file__).resolve().parents[1]
REGISTRO = RAIZ / 'config' / 'vad'
EMPRESA = PerfilEmpresa(nombre='Distribuidora Sintética Norte')
USOS = {'vad.frc': ('anualidad del VNR',), 'vad.igv_costos': ('costos sin IGV',)}


def _informes():
    """Lo nuevo de la T22: su ausencia es la falla de la aserción, no un error de importación."""
    assert importlib.util.find_spec('convertersmartgrid.adaptadores.vad.informes') is not None
    from convertersmartgrid.adaptadores.vad import informes
    assert hasattr(informes, 'armar_informe_definitivo'), 'falta armar_informe_definitivo en vad/informes.py (108 T22)'
    return informes


def _estudio(tmp_path):
    registro = cargar_registro(REGISTRO)
    estudio = crear_estudio(tmp_path / 'espacio', EMPRESA, grupo=1, periodo='2041-2045', version_tdr='tdr-sintetico',
                            usos=USOS)
    return tmp_path / 'espacio', estudio.id, registro


def _una_tabla(registro):
    from convertersmartgrid.adaptadores.vad.tablas_resultados import tablas_registradas
    tablas, _ = tablas_registradas(registro)
    return tablas[0]['numero']


def _pdf_falso(docx):
    return None, 'sin Word en la prueba'


def _observacion(espacio, id_estudio, registro, numero, tabla):
    registrar_observacion(espacio, id_estudio, numero=numero, fecha='2041-06-01', texto='Sustentar el metrado',
                          afecta=[{'tipo': 'tabla', 'id': tabla}, {'tipo': 'calculo', 'id': 'anualidad del VNR'}],
                          registro=registro)


def test_108_t22_el_definitivo_arma_los_documentos_del_registro_con_las_respuestas(tmp_path):
    """108:RF-12 (T22) — el Informe Definitivo lleva, en el orden del numeral 9.2 registrado, cada documento que el
    registro lista; el de las respuestas lleva cada observación con su respuesta, su sustento y lo que cambió en cada
    tabla o cálculo que afecta; sin el libro de tablas, ese documento queda nombrado como hueco."""
    from docx import Document
    inf = _informes()
    espacio, id_estudio, registro = _estudio(tmp_path)
    tabla = _una_tabla(registro)
    _observacion(espacio, id_estudio, registro, 'OBS-7', tabla)
    responder(espacio, id_estudio, 'OBS-7', respuesta='Se corrige el metrado', sustento='plano de la red, hoja 3',
              cambios={f'tabla {tabla}': 'baja el total de km', 'calculo anualidad del VNR': 'sin cambios: no depende '
                       'del metrado'})
    hecho = inf.armar_informe_definitivo(registro, espacio, id_estudio, tmp_path / 'definitivo',
                                         empresa=EMPRESA.nombre, resultados={}, estudio={}, exportar_pdf=_pdf_falso)
    esperados = registro.regla(inf.DOCUMENTOS_DEFINITIVO).regla.valor
    assert [d['documento'] for d in hecho.documentos] == esperados and len(esperados) == 4
    respuestas = next(d for d in hecho.documentos if 'Respuestas' in d['documento'])
    texto = '\n'.join(p.text for p in Document(respuestas['ruta']).paragraphs)
    celdas = [c.text for t in Document(respuestas['ruta']).tables for r in t.rows for c in r.cells]
    assert 'OBS-7' in texto and 'Sustento: plano de la red, hoja 3' in texto
    assert f'tabla {tabla}' in celdas and 'baja el total de km' in celdas
    tablas = next(d for d in hecho.documentos if 'Excel' in d['documento'])
    assert tablas['ruta'] is None and 'tablas de resultados' in tablas['motivo']
    assert any('tablas de resultados' in h for h in hecho.huecos)
    assert all(Path(d['ruta']).is_file() for d in hecho.documentos if d['ruta'])


def test_108_t22_respuesta_sin_la_tabla_o_el_calculo_que_cambio_se_rechaza(tmp_path):
    """108:RF-12 (T22) — una respuesta que no dice qué cambió en una de las tablas o cálculos que afecta rechaza el
    Informe Definitivo, nombrando la observación y el destino; también una observación sin responder."""
    inf = _informes()
    espacio, id_estudio, registro = _estudio(tmp_path)
    tabla = _una_tabla(registro)
    _observacion(espacio, id_estudio, registro, 'OBS-8', tabla)
    with pytest.raises(VadError, match='OBS-8: sin respuesta'):
        inf.armar_informe_definitivo(registro, espacio, id_estudio, tmp_path / 'd', empresa=EMPRESA.nombre,
                                     resultados={}, estudio={}, exportar_pdf=_pdf_falso)
    responder(espacio, id_estudio, 'OBS-8', respuesta='Se corrige', sustento='hoja 3',
              cambios={f'tabla {tabla}': 'baja el total de km'})
    with pytest.raises(VadError, match='OBS-8: no dice qué cambió en calculo anualidad del VNR'):
        inf.armar_informe_definitivo(registro, espacio, id_estudio, tmp_path / 'd', empresa=EMPRESA.nombre,
                                     resultados={}, estudio={}, exportar_pdf=_pdf_falso)
    assert not (tmp_path / 'd').exists() or not any((tmp_path / 'd').iterdir())


def test_108_t22_respuesta_sin_sustento_se_rechaza():
    """108:RF-12 (T22) — una respuesta sin sustento (p. ej. un observaciones.json editado a mano) no entra en el
    informe de respuestas."""
    from convertersmartgrid.adaptadores.vad.observaciones import Destino, Observacion
    inf = _informes()
    obs = Observacion(numero='OBS-9', fecha='2041-06-01', texto='Sustentar', afecta=(Destino('tabla', '12'),),
                      respuesta='Se corrige', sustento='', cambios={'tabla 12': 'baja'})
    with pytest.raises(VadError, match='OBS-9: la respuesta no trae su sustento'):
        inf.comprobar_respuestas([obs])
