"""Spec 024, T10: escenarios y aprendizaje activo, puro y contra ``fake_pf``."""
from __future__ import annotations

import random

import fake_pf
import pytest
from apoyo import cargar_herramienta, contexto_nativo

from igea_dgs.digital_twin import escenarios as es


def test_matriz_con_demanda_y_n_menos_1():
    """024:RF-11 — alrededor del estado base, factores de demanda intacto y con un tramo fuera;
    misma semilla, misma matriz."""
    m = es.matriz(['L1', 'L2', 'L3'], factores=(0.9, 1.0, 1.1), contingencias=2, semilla=7)
    assert len(m) == 3 + 2 * 3
    assert {e.tramos_abiertos for e in m} >= {()}
    assert m == es.matriz(['L3', 'L1', 'L2'], factores=(0.9, 1.0, 1.1), contingencias=2, semilla=7)


def test_familia_entera_en_una_particion():
    """024:RF-12 — las variantes de una maniobra comparten familia y partición; la demanda no
    cambia la familia."""
    a = {'nativo': {'project': 'P', 'feeders': ['F1']}, 'accion': {'escenario': {'factor_carga': 0.8, 'tramos_abiertos': ['L1']}}}
    b = {'nativo': {'project': 'P', 'feeders': ['F1']}, 'accion': {'escenario': {'factor_carga': 1.3, 'tramos_abiertos': ['L1']}}}
    c = {'nativo': {'project': 'P', 'feeders': ['F1']}, 'accion': {'escenario': {'factor_carga': 0.8, 'tramos_abiertos': ['L2']}}}
    assert es.familia(a) == es.familia(b) != es.familia(c)
    assert es.particion(es.familia(a)) == es.particion(es.familia(b))
    semilla = random.randrange(1 << 30)
    rnd = random.Random(semilla)
    cuenta = {'entrenamiento': 0, 'validacion': 0, 'prueba': 0}
    for _ in range(3000):
        cuenta[es.particion(f'{rnd.getrandbits(64):016x}')] += 1
    assert 0.6 < cuenta['entrenamiento'] / 3000 < 0.8, f'semilla {semilla}'


def test_eleccion_activa_por_incertidumbre_o_diversidad():
    """024:RF-40 — con oráculo, primero donde más duda; sin él, los más distintos; nunca lo ya
    simulado."""
    m = es.matriz(['L1', 'L2'], factores=(0.7, 1.0, 1.3), contingencias=2)
    hecho = m[1].clave
    por_duda = es.elegir(m, 2, incertidumbre=lambda e: e.factor_carga, hechos=[hecho])
    assert all(e.factor_carga == 1.3 for e in por_duda)
    diversos = es.elegir(m, 3, hechos=[hecho])
    assert len({(e.factor_carga, e.tramos_abiertos) for e in diversos}) == 3
    assert hecho not in {e.clave for e in diversos}


def test_presupuesto_de_licencia():
    """024:RF-41 — el aprendizaje activo para cuando se acaba su presupuesto."""
    t = [0.0]
    p = es.Presupuesto(100, reloj=lambda: t[0])
    assert p.alcanza(60)
    t[0] = 50
    assert not p.alcanza(60) and p.restante == 50


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('escenarios_pf.py', 'escenarios_pf_guion', tools_en_path=True)


def _app():
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=3, bt=True, flujo=True)
    app.carpetas['study'].CreateObject('IntCase', 'Sin proyecto')
    object.__setattr__(app.ldf, 'scLoadFac', 100.0)
    return app


def _plan(**extra):
    plan = {'project': 'P', 'feeders': ['F1'], 'case': 'sin_proyecto',
            'native_action_context': contexto_nativo('P', ['F1'], 'gemelo_escenarios')}
    plan.update(extra)
    return plan


def test_tramos_y_grafo_base(guion):
    """024:RF-11 — los tramos para la matriz y el grafo con R, X, corriente nominal y demanda;
    la copia del proyecto se borra al terminar."""
    app = _app()
    informe, rc = guion.ejecutar(app, _plan(solo_tramos=True))
    assert rc == 0 and informe['tramos'] == ['F1_L1', 'F1_L2', 'F1_L3']
    g = informe['grafo']
    lineas = [r for r in g['ramas'] if r['clase'] == 'ElmLne']
    assert len(lineas) == 3 and all(r['r_ohm'] > 0 and r['x_ohm'] > 0 for r in lineas)
    assert any(r['clase'] == 'ElmTr2' for r in g['ramas'])
    assert any(n['fuente'] for n in g['nodos'].values())
    assert sum(n['p_mw'] for n in g['nodos'].values()) == pytest.approx(0.15)
    assert any(o.loc_name.startswith('P_gemelo_') for o in app.borrados)


def test_escenarios_simulados_y_restituidos(guion):
    """024:RF-11 / 024:RF-40 — cada escenario con su demanda y sus tramos abiertos; tras él,
    todo vuelve a su valor."""
    app = _app()
    escenarios = [{'factor_carga': 1.0, 'tramos_abiertos': []},
                  {'factor_carga': 1.3, 'tramos_abiertos': ['F1_L3']}]
    informe, rc = guion.ejecutar(app, _plan(escenarios=escenarios))
    assert rc == 0 and len(informe['escenarios']) == 2
    a, b = (f['lectura'] for f in informe['escenarios'])
    assert len(b['topologia']['componentes']) == len(a['topologia']['componentes']) + 1
    carga_a = sum(n['p_mw'] for n in a['topologia']['grafo']['nodos'].values())
    carga_b = sum(n['p_mw'] for n in b['topologia']['grafo']['nodos'].values())
    assert carga_b == pytest.approx(1.3 * carga_a)
    assert app.ldf.scLoadFac == 100.0
    assert all(not ln.outserv for ln in app.proyecto.GetContents('*.ElmLne', 1))


def test_cancelar_para_entre_escenarios(guion):
    """024:RF-41 — cancelar para antes del siguiente escenario y lo dice."""
    informe, rc = guion.ejecutar(_app(), _plan(escenarios=[{'factor_carga': 1.0}] * 3), lambda: True)
    assert rc == 0 and informe['escenarios'] == [] and informe['avisos']


def test_el_grafo_trae_los_acopladores_y_la_version(guion):
    """024:RF-11 — los acopladores cerrados son ramas del grafo: sin ellos la cabecera,
    interruptor en su SET, dejaba la red sin fuente (IN111–TA225, 2026-10-22)."""
    from igea_dgs.digital_twin.oraculo import VERSION_GRAFO

    app = _app()
    red = next(o for o in app.proyecto.GetContents('*.ElmNet', 1))
    b0, b1 = (next(o for o in app.proyecto.GetContents('*.ElmTerm', 1) if o.loc_name == n) for n in ('F1_B0', 'F1_B1'))
    cp = red.CreateObject('ElmCoup', 'CB_F1')
    for lado, barra in ((1, b0), (2, b1)):
        cub = barra.CreateObject('StaCubic', f'c_cb{lado}')
        cub.obj_id = cp
        object.__setattr__(cp, f'bus{lado}', cub)
    cp.on_off = 1
    informe, rc = guion.ejecutar(app, _plan(solo_tramos=True))
    g = informe['grafo']
    assert rc == 0 and g['version'] == VERSION_GRAFO
    assert [r['clase'] for r in g['ramas']].count('ElmCoup') == 1


def test_hipercubo_latino_del_rango_medido():
    """027:RF-4 — los factores cubren el rango medido del total coincidente, del valle a la
    punta con su margen, uno por franja; misma semilla, mismos factores."""
    import random as _r

    semilla = _r.randrange(1 << 30)
    rnd = _r.Random(semilla)
    curvas = [[rnd.uniform(200, 1000) for _ in range(96)] for _ in range(rnd.randint(1, 5))]
    lo, hi = es.rango_medido(curvas, margen=0.1)
    total = [sum(c[i] for c in curvas) for i in range(96)]
    assert lo == pytest.approx(min(total) / max(total)) and hi == pytest.approx(1.1)
    n = rnd.randint(3, 12)
    f = es.factores_hipercubo(lo, hi, n, semilla)
    ancho = (hi - lo) / n
    assert len(f) == n and list(f) == sorted(f)
    assert all(lo + k * ancho - 1e-4 <= x <= lo + (k + 1) * ancho + 1e-4 for k, x in enumerate(f)), semilla
    assert f == es.factores_hipercubo(lo, hi, n, semilla)
    assert es.rango_medido([]) is None and es.factores_hipercubo(1.0, 1.0, 3) == ()
    m = es.matriz(['L1'], factores=f, contingencias=1)
    assert {e.factor_carga for e in m} == set(f)


def test_la_web_usa_el_rango_de_la_ultima_maxima(monkeypatch):
    """027:RF-4 — el servicio arma la matriz con los factores del hipercubo del rango medido
    en las curvas de la última máxima buscada."""
    from datetime import datetime
    from threading import Lock
    from types import SimpleNamespace

    from igea_dgs import perfil_empresa
    from igea_dgs.digital_twin import buffer, oraculo
    from igea_dgs.web import services

    t0 = datetime(2026, 7, 1)
    curva = [(t0, kw, 0.0) for kw in (300.0, 600.0, 1000.0, 500.0)]
    ws = SimpleNamespace(lock=Lock(), curvas_cabecera={'J': {'M1': {'curva': curva}}})
    pedidas = []
    monkeypatch.setattr(services, 'native_action_context', lambda *a: {'feeders': ['F1']})
    monkeypatch.setattr(services, 'carpeta_pf', lambda: 'c')
    monkeypatch.setattr(services, '_guion_pf', lambda *a, **k: (0, {'tramos': ['L1'], 'grafo': {}}, None))
    monkeypatch.setattr(perfil_empresa, 'datos_perfil', lambda *a, **k: {'gemelo': {'puntos_de_carga': 4}})
    monkeypatch.setattr(buffer, 'BuferEpisodios', lambda *a, **k: SimpleNamespace(consultar=lambda _c: []))
    monkeypatch.setattr(oraculo, 'incertidumbre_de_escenarios', lambda _g: None)
    monkeypatch.setattr(es, 'elegir', lambda m, *a, **k: pedidas.extend(m) or [])
    r = services.gemelo_aprender(ws, SimpleNamespace(log=lambda _m: None), "P", ["F1"], n=3)
    assert r['simulados'] == 0
    factores = sorted({e.factor_carga for e in pedidas})
    assert len(factores) == 4 and 0.3 <= factores[0] < 0.5 and factores[-1] <= 1.1
