"""Spec 021, RF-54 a RF-60: el ajuste de los alimentadores de un proyecto a la vez, en
``fake_pf``.

DIgSILENT no se ejecuta en la suite (P11). El usuario, el 2026-10-17, al ir a aplicar NA203
y después NA205: «la calibración se debe hacer por proyecto en DIgSILENT; si es un
alimentador se hace de ese y dos o más se hacen de todas según el proyecto, no de forma
independiente».
"""
from __future__ import annotations

import copy

import pytest
from apoyo import cargar_herramienta, contexto_nativo
from test_ajuste_cabecera_guion import _app, _carga, _plan
from test_ajuste_central_guion import _plan as _plan_central


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_proyecto_guion',
                              tools_en_path=True)


def _de(plan, feeder, kw):
    p = copy.deepcopy(plan)
    p['feeder'] = feeder
    p['objetivo'].update(kw=kw, medidor=f'M_{feeder}', alimentador=feeder)
    p['native_action_context'] = contexto_nativo('P', [feeder], 'ajuste')
    return p


def test_dos_alimentadores_en_los_mismos_flujos(guion):
    """021:RF-54, 021:RF-55, 021:RF-59 — una sola calibración: los dos cuadran en el mismo
    flujo final, con un factor cada uno, y cada informe dice con quién se calibró."""
    app = _app(escenario=True)
    (f1, rc1), (f2, rc2) = guion.ejecutar_proyecto(
        app, [_de(_plan(), 'F1', 300.0), _de(_plan(), 'F2', 220.0)])
    assert (rc1, rc2) == (0, 0), (f1, f2)
    assert f1['cuadrado'] and f2['cuadrado']
    assert f1['calibrado_con'] == ['F2'] and f2['calibrado_con'] == ['F1']
    assert abs(f1['desvio']['kw']) <= 0.01 and abs(f2['desvio']['kw']) <= 0.01
    assert f1['cabecera']['kw'] == pytest.approx(300.0, rel=0.01)
    assert f2['cabecera']['kw'] == pytest.approx(220.0, rel=0.01)
    assert f1['flujos'] == f2['flujos'] and f1['historial'] is f2['historial']
    assert set(f1['historial'][0]['a']) == {'F1', 'F2'}
    assert f1['validacion_posterior_nativa']['status'] == 'VALIDO'
    assert f2['resultado_carga_nativa']['status'] == 'APLICADO_Y_VALIDADO'
    assert f1['escenario'] == 'Sin proyecto' and f1['escenarios'][0]['escenario'] == 'Sin proyecto'
    assert app.carpetas['scheme'].GetContents('*.IntScheme') == []


def test_un_plan_es_el_ajuste_de_siempre(guion):
    """021:RF-60 — con un alimentador, el ajuste de siempre, sin calibración conjunta."""
    a, b = _app(escenario=True), _app(escenario=True)
    [(solo, rc)] = guion.ejecutar_proyecto(a, [_plan()])
    igual, rc_igual = guion.ejecutar(b, _plan())
    assert rc == rc_igual == 0
    assert 'calibrado_con' not in solo
    assert solo['cabecera'] == igual['cabecera'] and solo['flujos'] == igual['flujos']


def test_con_central_y_sin_ella_a_la_vez(guion):
    """021:RF-54, 021:RF-55 — F1 con central cuadra sus dos zonas y F2 su cabecera, todo en
    los mismos flujos; la central queda creada en «Sin proyecto»."""
    app = _app(escenario=True)
    central = _plan_central()
    resultados = guion.ejecutar_proyecto(app, [central, _de(_plan(), 'F2', 220.0)])
    (f1, rc1), (f2, rc2) = resultados
    assert (rc1, rc2) == (0, 0), (f1, f2)
    assert f1['criterio_cuadre'] == 'ZONAS_DE_LA_CENTRAL' and f1['central']['creado']
    z = f1['zonas']
    assert z['arriba_kw'] == pytest.approx(150.0, rel=0.01)
    assert z['abajo_kw'] == pytest.approx(900.0, rel=0.01)
    assert f2['cabecera']['kw'] == pytest.approx(220.0, rel=0.01)
    assert set(f1['historial'][0]['a']) == {'F1|arriba', 'F1|abajo', 'F2'}


def test_el_que_no_se_prepara_queda_fuera(guion):
    """021:RF-57 — un alimentador sin cabecera en el proyecto se dice en su informe y los
    demás se calibran juntos."""
    app = _app(escenario=True)
    (f9, rc9), (f1, rc1) = guion.ejecutar_proyecto(
        app, [_de(_plan(), 'F9', 100.0), _de(_plan(), 'F1', 300.0)])
    assert rc9 == 2 and 'ElmFeeder' in f9['error']
    assert rc1 == 0 and f1['cuadrado']
    assert any('F9' in a and '021:RF-57' in a for a in f1['avisos'])


def test_cancelar_deja_el_ultimo_reparto_comun(guion):
    """021:RF-58 — cancelar termina el flujo en curso y los dos quedan cancelados con el
    último reparto común que convergió."""
    app = _app(escenario=True)
    flujos = []
    antes = app.ldf.Execute

    def contar():
        flujos.append(1)
        return antes()

    app.ldf.Execute = contar
    (f1, _), (f2, _) = guion.ejecutar_proyecto(
        app, [_de(_plan(), 'F1', 300.0), _de(_plan(kw=600.0), 'F2', 600.0)],
        cancelado=lambda: len(flujos) >= 1)
    assert f1['cancelado'] and f2['cancelado'] and not f1['cuadrado']
    assert _carga(app, 'F2_S1').plini > 0


def test_proyectos_distintos_no_se_mezclan(guion):
    """021:RF-54 — se calibra un proyecto cada vez."""
    otro = _de(_plan(), 'F2', 200.0)
    otro['project'] = 'Q'
    res = guion.ejecutar_proyecto(_app(escenario=True), [_plan(), otro])
    assert all(rc == 2 and 'un mismo proyecto' in i['error'] for i, rc in res)
