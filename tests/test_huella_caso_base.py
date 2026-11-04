"""Spec 086, T11: el guion de la calibración escribe la huella del «Caso base» (RF-14).

La guarda de 081 estaba escrita y con pruebas, pero nadie ponía ``caso_base_huella`` en el informe: no
actuaba nunca. Aquí corre el guion de verdad contra ``fake_pf``; que la huella real sea igual antes y
después de calibrar se comprueba en DIgSILENT (081 T12, en las corridas F6).
"""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from apoyo import cargar_herramienta
from test_ajuste_cabecera_guion import _carga, _caso, _con_escenario_que_manda, _plan
from test_ajuste_proyecto_guion import _de

from convertersmartgrid.comprobacion_flujo import comparar_huellas, huella_de_caso, revisar_huellas
from convertersmartgrid.web import services


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('ajuste_cabecera_pf.py', 'huella_caso_base_guion', tools_en_path=True)


@pytest.fixture()
def app(guion, monkeypatch):
    """Con los casos hechos y el escenario mandando: lo que se calibra en «Sin proyecto» no se ve desde el
    «Caso base», como en DIgSILENT. Sin esto el doble comparte la demanda, y toda huella cambiaría."""
    red = _con_escenario_que_manda(n=6)
    casos = sys.modules['casos_pf']
    monkeypatch.setattr(casos, 'activar_proyecto', lambda _a, _r, carpeta=None: red.proyecto)
    monkeypatch.setattr(guion, 'activar_proyecto', lambda _a, _r, carpeta=None: red.proyecto)
    casos.preparar_sin(red, {'project': 'P', 'feeders': ['F1'], 'caso_base_sin_verificar': {}})
    return red


def _cambia_la_red_compartida(guion, monkeypatch, nombre='F2_S1'):
    """Lo que la huella existe para detectar: el «Caso base» cambia durante la calibración."""
    original = guion._devolver_cargas_nuevas

    def devolver(a, estado):
        original(a, estado)
        activo = a.caso
        _caso(a, 'Caso base').Activate()
        _carga(a, nombre).plini *= 2
        activo.Activate()

    monkeypatch.setattr(guion, '_devolver_cargas_nuevas', devolver)


def test_una_calibracion_buena_escribe_la_misma_huella(guion, app):
    """086:RF-14, 081:RF-33 — el informe trae la huella de antes y de después, con sus cargas y su flujo, y es la misma."""
    informe, rc = guion.ejecutar(app, _plan())
    assert rc == 0, informe
    huella = informe['caso_base_huella']
    assert huella['antes']['sha256'] == huella['despues']['sha256']
    assert {'F1_S1', 'F2_S1'} <= set(huella['antes']['cargas'])
    assert huella['antes']['flujo']['converge'] is True
    assert revisar_huellas([informe]) is None


def test_el_caso_base_que_cambia_activa_la_guarda(guion, monkeypatch, app):
    """086:RF-14, 081:RF-34, 081:RF-36 — si el «Caso base» cambia, la guarda de 081 actúa: fallo grave y parcial."""
    _cambia_la_red_compartida(guion, monkeypatch)
    informe, rc = guion.ejecutar(app, _plan())
    assert rc == 0, informe
    grave = revisar_huellas([informe])
    assert grave and grave['nivel'] == 'grave' and 'F2_S1' in grave['texto'] and grave['volver']
    logs = []
    verdad = services._verdad_de_la_calibracion(SimpleNamespace(log=logs.append), [informe])
    assert verdad['estado_trabajo'] == 'parcial' and verdad['caso_base_cambio']['nivel'] == 'grave'
    assert any('FALLO GRAVE' in x for x in logs)


def test_el_proyecto_escribe_una_huella_y_deja_el_caso_activo(guion, app):
    """086:RF-14 — un proyecto, una huella: en el primer informe, sin repetir miles de cargas en cada alimentador."""
    inicial = app.GetActiveStudyCase()
    (f1, rc1), (f2, rc2) = guion.ejecutar_proyecto(app, [_de(_plan(), 'F1', 300.0), _de(_plan(), 'F2', 220.0)])
    assert (rc1, rc2) == (0, 0), (f1, f2)
    assert f1['caso_base_huella']['antes']['sha256'] == f1['caso_base_huella']['despues']['sha256']
    assert 'caso_base_huella' not in f2
    assert app.GetActiveStudyCase() is inicial
    sin = _caso(app, 'Sin proyecto')
    sin.Activate()
    assert guion._leer_huella_caso_base(app, None)['sha256'] and app.GetActiveStudyCase() is sin


def test_con_los_bancos_la_huella_de_antes_es_la_de_la_primera_pasada(guion, app):
    """086:RF-14 — con bancos el proyecto se recorre dos veces: la de antes no se vuelve a tomar en la segunda,
    que ya taparía lo que hubiera cambiado la primera."""
    plan = {**_plan(), 'completar_bancos': True}
    resultados = guion.ejecutar_proyecto(app, [plan])
    informe = resultados[0][0]
    assert informe['caso_base_huella']['antes']['sha256'] == informe['caso_base_huella']['despues']['sha256']


def test_simular_no_toma_huella(guion, app):
    """086:RF-14, 081:RF-13 — simular no escribe ni corre flujos en el «Caso base»."""
    informe, rc = guion.ejecutar(app, _plan(), simular=True)
    assert rc == 0 and 'caso_base_huella' not in informe


def test_si_no_se_puede_leer_lo_dice_y_calibra(guion, monkeypatch, app):
    """086:RF-14 — la huella vigila, no decide: sin leerla se calibra igual y se avisa."""
    def falla(*_a, **_k):
        raise RuntimeError('sin lectura')

    monkeypatch.setattr(guion, 'huella_de_caso', falla)
    informe, rc = guion.ejecutar(app, _plan())
    assert rc == 0 and informe['cuadrado'] and 'caso_base_huella' not in informe
    assert any('huella' in a for a in informe['avisos'])


def test_el_resultado_del_trabajo_no_lleva_todas_las_cargas(guion, app):
    """086:RF-14 — la huella completa queda en el informe en disco; al navegador va su resumen."""
    informe, _rc = guion.ejecutar(app, _plan())
    copia = {**informe}
    services._verdad_de_la_calibracion(SimpleNamespace(log=lambda _m: None), [copia])
    assert set(copia['caso_base_huella']['antes']) == {'sha256', 'flujo'}


def test_un_flujo_que_difiere_por_debajo_de_su_tolerancia_no_es_un_cambio():
    """086:RF-14 — dos flujos de la misma red no dan el mismo kW al decimal: eso no es un «FALLO GRAVE»."""
    cargas = [{'nombre': 'S1', 'p_kw': 10.0, 'q_kvar': 2.0, 'escala': 1.0, 'en_servicio': True}]
    a = huella_de_caso(cargas, {'converge': True, 'return_code': 0, 'kw': 1000.0})
    assert not comparar_huellas(a, huella_de_caso(cargas, {'converge': True, 'return_code': 0, 'kw': 1000.6}))['cambio']
    assert comparar_huellas(a, huella_de_caso(cargas, {'converge': True, 'return_code': 0, 'kw': 1010.0}))['cambio']
    assert comparar_huellas(a, huella_de_caso(cargas, {'converge': False, 'return_code': 1, 'kw': None}))['cambio']
