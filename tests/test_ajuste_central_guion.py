"""Spec 021, RF-35 a RF-45: el ajuste de un alimentador con central en ``fake_pf``.

DIgSILENT no se ejecuta en la suite (P11). El doble calcula el flujo de cada línea del
alimentador en cadena (B0…B6, con una SED en cada barra) y la inyección de la central;
lo que DIgSILENT hace de verdad con un ``ElmGenstat`` lo dio la sonda del 2026-10-17 en
una copia de NA203 + NA205 (inyecta lo escrito; su etapa sigue grabando aunque se
desactive y active la variación).
"""
from __future__ import annotations

import fake_pf
import pytest
from apoyo import cargar_herramienta, contexto_nativo


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_central_guion',
                              tools_en_path=True)


def _app():
    return fake_pf.proyecto(alimentadores=('F1', 'F2'), cargas_por_alim=6, bt=True, flujo=True,
                            escenario=True, kva=lambda f, i: 100.0 * i)


def _plan(nodo='F1_B3', arriba=150.0, abajo=900.0, generacion=600.0, clientes=()):
    maxima = {'alimentador': 'F1', 'fecha': '2026-08-20 16:45:00',
              'demanda_kw': arriba + abajo, 'arriba_kw': arriba, 'arriba_kvar': 30.0,
              'abajo_kw': abajo, 'abajo_kvar': 180.0, 'generacion_kw': generacion,
              'generacion_kvar': -40.0, 'cabecera_kw': arriba + abajo - generacion,
              'cabecera_kvar': 200.0, 'error': None}
    return {'project': 'P', 'feeder': 'F1', 'stamp': '20261017_120000',
            'objetivo': {'kw': arriba + abajo - generacion, 'kvar': 200.0, 'medidor': 'M1',
                         'alimentador': 'F1', 'fecha': '2026-08-20 16:45:00'},
            'central': {'nodo': nodo, 'maxima': maxima},
            'clientes': list(clientes), 'kva_entrada': {}, 'tolerancia': 0.01,
            'project_binding': {'native_reread': {
                'status': 'VERIFICADO_PERSISTENCIA',
                'capacitor_reread': {'status': 'VERIFICADO_PERSISTENCIA', 'expected': 3}}},
            'native_action_context': contexto_nativo('P', ['F1'], 'ajuste'),
            'caso_base_sin_verificar': {}}


def _gens(app):
    """Los generadores que creó el guion, estén o no activos en el caso de ahora."""
    return [o for o in app.creados if o._clase == 'ElmGenstat']


def _visibles_en(app, caso):
    """Los generadores que calcula ``caso`` (sus variaciones activas)."""
    c = next(x for x in app.carpetas['study'].GetContents('*.IntCase') if x.loc_name == caso)
    c.Activate()
    return [o.loc_name for o in app.GetCalcRelevantObjects('*.ElmGenstat')]


def test_crea_la_central_en_su_barra_con_la_p_y_q_medidas(guion):
    """021:RF-35, RF-37 — un generador estático en la barra declarada, con la P y Q de la
    generación del registro objetivo, en su propia variación; el «Caso base» no se toca."""
    app = _app()
    informe, rc = guion.ejecutar(app, _plan())
    assert rc == 0, informe
    [gen] = _gens(app)
    assert gen.loc_name == 'Central_F1' and gen.bus1.cterm.loc_name == 'F1_B3'
    assert (gen.pgini, gen.qgini) == (pytest.approx(0.6), pytest.approx(-0.04))
    c = informe['central']
    assert c['creado'] and c['barra'] == 'F1_B3' and c['variacion'].startswith('Central_F1')
    variacion = next(v for v in app.carpetas['scheme'].GetContents('*.IntScheme', 1)
                     if v.loc_name == c['variacion'])
    etapa = variacion.GetContents('*.IntSstage')[0]
    creados = {o.loc_name for o in etapa._creados}
    assert creados == {'Central_F1', 'Cub_Central_F1'}, 'en su variación solo la central'
    assert _visibles_en(app, 'Sin proyecto') == ['Central_F1']
    assert _visibles_en(app, 'Caso base') == [], 'el «Caso base» no tiene la central (RF-37)'


def test_cada_zona_cuadra_con_su_factor(guion):
    """021:RF-39, RF-40, RF-41, RF-43, RF-44 — las cargas de B1 y B2 son de aguas arriba y
    las de B3 a B6 de aguas abajo; cada zona cuadra con su factor de escala y el informe
    dice los factores, la cabecera calculada y la medida."""
    app = _app()
    informe, rc = guion.ejecutar(app, _plan())
    assert rc == 0 and informe['cuadrado'], informe
    assert (informe['central']['cargas_aguas_arriba'],
            informe['central']['cargas_aguas_abajo']) == (2, 4)
    z = informe['zonas']
    assert abs(z['arriba_kw'] - 150.0) <= 0.01 * 150.0
    assert abs(z['abajo_kw'] - 900.0) <= 0.01 * 900.0
    assert z['factor_arriba'] != pytest.approx(z['factor_abajo'])
    assert z['cabecera_medida_kw'] == 450.0 and z['cabecera_calculada_kw'] is not None
    assert any('Cabecera calculada' in a for a in informe['avisos'])
    s1 = next(o for o in app.proyecto.GetContents('*.ElmLod', 1) if o.loc_name == 'F1_S1')
    s4 = next(o for o in app.proyecto.GetContents('*.ElmLod', 1) if o.loc_name == 'F1_S4')
    assert s1.scale0 == pytest.approx(z['factor_arriba'])
    assert s4.scale0 == pytest.approx(z['factor_abajo'])


def test_las_fijas_conservan_su_p_y_q_en_su_zona(guion):
    """021:RF-42 — un cliente importante de aguas arriba lleva su P y Q con factor 1."""
    app = _app()
    cliente = {'codigo': '9', 'sed': 'F1_S2', 'pot': 40.0, 'ea': 1.0, 'eri': 0.2}
    informe, rc = guion.ejecutar(app, _plan(clientes=[cliente]))
    assert rc == 0, informe
    s2 = next(x for x in informe['sed'] if x['sed'] == 'F1_S2')
    assert s2['origen'] == 'cliente' and s2['despues']['kw'] == pytest.approx(40.0)


def test_la_segunda_calibracion_reutiliza_la_central(guion):
    """021:RF-36 — si la central ya está, solo se le escribe la P y Q; no se crea otra."""
    app = _app()
    guion.ejecutar(app, _plan())
    informe, rc = guion.ejecutar(app, _plan(generacion=500.0))
    assert rc == 0, informe
    assert len(_gens(app)) == 1 and not informe['central']['creado']
    assert _gens(app)[0].pgini == pytest.approx(0.5)


def test_un_nodo_fuera_del_alimentador_se_rechaza(guion):
    """021:RF-38 — el plan se rechaza nombrando el nodo y el alimentador."""
    app = _app()
    informe, rc = guion.ejecutar(app, _plan(nodo='NO_EXISTE'))
    assert rc == 2 and 'NO_EXISTE' in informe['error'] and 'F1' in informe['error']
    assert _gens(app) == []


def test_simular_no_crea_la_central(guion):
    """021:RF-35 — al simular se dice el reparto por zonas sin tocar DIgSILENT."""
    app = _app()
    informe, rc = guion.ejecutar(app, _plan(), simular=True)
    assert rc == 0, informe
    assert set(informe['zonas']) == {'arriba', 'abajo'} and _gens(app) == []


def test_sin_central_el_plan_de_siempre(guion):
    """021:RF-46 — un plan sin ``central`` no crea generador ni calibra por zonas."""
    app = _app()
    plan = _plan()
    plan.pop('central')
    plan['objetivo']['kw'] = 300.0
    informe, _rc = guion.ejecutar(app, plan)
    assert _gens(app) == [] and 'zonas' not in informe
