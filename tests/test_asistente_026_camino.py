"""Spec 026, RF-48 (T22): el asistente decide el camino del trabajo (qué etapa sigue, con qué entradas del espacio y con
qué parámetros según la norma y el perfil de la empresa) y lo propone entero con su motivo; el operador confirma lo que
escribe o envía, y lo demás lo hace el asistente solo (usuario, 2026-11-18: «el asistente debe controlar el
SmartConverter de punta a punta»).

Es la prueba del planificador: el camino sale de la misma lista que confirma el operador (067:RF-37), de la biblioteca
normativa real del programa y de un perfil sintético; no calcula ni ejecuta nada.
"""
from __future__ import annotations

import pytest

PERFIL = {'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100},
          'planificacion': {'anio_presentacion': 2027}}
DATOS = {'sistema': 'S1', 'periodo': '2026-07', 'ruta': 'G:/libros'}
CONTEXTO = {'workspace_id': 'w1', 'source_fingerprint': 'f1', 'source_mode': 'txt'}


def _orquestador():
    from convertersmartgrid.aplicacion.asistente import orquestador

    assert hasattr(orquestador, 'camino_de'), 'el asistente no propone el camino entero con su motivo'
    return orquestador


def _camino(control=None, perfil=PERFIL, datos=DATOS):
    o = _orquestador()
    lista = o.lista_de_etapas(datos, control or {}, CONTEXTO)
    return o, lista, o.camino_de(lista, datos, norma=o.norma_de_la_biblioteca('2026-11-19'), perfil=perfil)


def test_026_rf48_propone_la_siguiente_etapa_y_el_camino_entero_con_su_motivo():
    """026:RF-48 — en un espacio sin hacer nada, sigue la fuente; cada etapa dice por qué va y con qué entradas."""
    _o, lista, camino = _camino()
    assert camino['siguiente'] == 'fuente' and 'fuente' in camino['motivo'] and 'primera sin hacer' in camino['motivo']
    assert [f['etapa'] for f in camino['etapas']] == [e['nombre'] for e in lista['etapas']]
    assert all(f['motivo'] for f in camino['etapas']), 'una etapa sin motivo'
    sistema = next(f for f in camino['etapas'] if f['etapa'] == 'sistema')
    assert sistema['entradas'] == {'sistema': 'S1', 'periodo': '2026-07', 'ruta': 'G:/libros'}
    cargas = next(f for f in camino['etapas'] if f['etapa'] == 'cargas_nuevas')
    assert cargas['estado'] == 'se_omitira' and 'se salta' in cargas['motivo']
    assert camino['confirmacion'] == lista['confirmacion'] and camino['calcula'] is False


def test_026_rf48_los_parametros_salen_de_la_norma_vigente_y_del_perfil():
    """026:RF-48 — la tolerancia de tensión y el horizonte del PIDE, de la norma vigente con su acto; la cargabilidad y
    el año de presentación, del perfil de la empresa."""
    _o, _lista, camino = _camino()
    por = {f['etapa']: {p['parametro']: p for p in f['parametros']} for f in camino['etapas']}
    tolerancia = por['estudios']['tolerancia_tension']
    assert tolerancia['de'] == 'norma' and tolerancia['valor']['general'] == 0.05 and tolerancia['acto']
    assert por['pide']['horizonte_anios']['valor'] == 20 and por['pide']['horizonte_anios']['acto']
    assert por['estudios']['cargabilidad_max_pct'] == {'parametro': 'cargabilidad_max_pct', 'de': 'perfil',
                                                       'clave': 'estudios.cargabilidad_max_pct', 'valor': 100}
    assert por['pide']['anio_presentacion']['valor'] == 2027 and camino['parametros_que_faltan'] == []


def test_026_rf48_lo_que_no_esta_en_el_perfil_no_se_inventa():
    """026:RF-48 — sin el año de presentación en el perfil, el parámetro queda como falta con su motivo."""
    _o, _lista, camino = _camino(perfil={'estudios': PERFIL['estudios']})
    pide = {p['parametro']: p for p in next(f for f in camino['etapas'] if f['etapa'] == 'pide')['parametros']}
    assert pide['anio_presentacion']['valor'] is None and 'perfil' in pide['anio_presentacion']['falta']
    assert any(f.startswith('pide:') for f in camino['parametros_que_faltan'])


def test_026_rf48_retoma_donde_quedo_y_dice_que_confirma_el_operador():
    """026:RF-48 — con la fuente y el sistema hechos, sigue el «Caso base» con el proyecto que dejó el sistema; lo que
    escribe lo confirma el operador, y una etapa que solo lee la hace el asistente solo."""
    control = {'etapas': {'fuente': {'estado': 'hecha'}, 'sistema': {'estado': 'hecha'}},
               'datos': {**DATOS, 'proyecto': 'P_S1', 'alimentadores': ['F1', 'F2']}}
    o, _lista, camino = _camino(control=control)
    assert camino['siguiente'] == 'caso_base'
    caso = next(f for f in camino['etapas'] if f['etapa'] == 'caso_base')
    assert caso['entradas'] == {'proyecto': 'P_S1'} and caso['confirma_el_operador'] is True
    hechas = [f for f in camino['etapas'] if f['estado'] == 'hecha']
    assert [f['etapa'] for f in hechas] == ['fuente', 'sistema'] and all('no se repite' in f['motivo'] for f in hechas)
    assert 'estudios' in camino['confirma_el_operador'] and 'fuente' not in camino['confirma_el_operador']
    lectura = o.Etapa('lectura', 'estado')
    lista = o.lista_de_etapas({}, {}, CONTEXTO, etapas=(lectura,))
    solo = o.camino_de(lista, {}, etapas=(lectura,))
    assert solo['lo_hace_el_asistente_solo'] == ['lectura'] and solo['confirma_el_operador'] == []


def test_026_rf48_sin_un_dato_obligatorio_lo_pide_y_no_sigue():
    """026:RF-48 — sin el informe hecho y sin el formulario, el camino lo dice como lo que falta, no como un error."""
    o = _orquestador()
    etapas = (o.Etapa('estudios', 'estudios', ('proyecto',)), o.Etapa('informe', 'informe_estudio', ('proyecto', 'formulario')))
    lista = o.lista_de_etapas({'proyecto': 'P1'}, {'etapas': {'estudios': {'estado': 'hecha'}}}, CONTEXTO, etapas=etapas)
    camino = o.camino_de(lista, {'proyecto': 'P1'}, etapas=etapas)
    assert lista['etapas'][1]['estado'] == 'falta_dato'
    assert camino['siguiente'] == 'informe' and 'falta formulario' in camino['motivo']
    assert camino['confirma_el_operador'] == [], 'una etapa a la que le falta su dato no se ofrece para confirmar'


@pytest.mark.parametrize('clave', ['calidad.tension.tolerancia_ntcse', 'vinculo.pide.horizonte_estudio_anios'])
def test_026_rf48_la_norma_se_lee_de_la_biblioteca_con_su_acto(clave):
    """026:RF-48 — los parámetros de la norma son reglas vigentes de la biblioteca normativa (107), con su acto."""
    regla = _orquestador().norma_de_la_biblioteca('2026-11-19')(clave)
    assert regla is not None and regla['acto'] and regla['valor'] is not None
    assert _orquestador().norma_de_la_biblioteca('2026-11-19')('clave.que.no.existe') is None
