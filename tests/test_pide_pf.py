"""Spec 024, T13: ``tools/pide_pf.py`` contra ``fake_pf`` (cada año del horizonte escalado)."""
from __future__ import annotations

import fake_pf
import pytest
from apoyo import cargar_herramienta, contexto_nativo

LIM = {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100,
       'transformador_max_pct': 80}


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('pide_pf.py', 'pide_pf_guion', tools_en_path=True)


def _app():
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=3, bt=True, flujo=True)
    app.carpetas['study'].CreateObject('IntCase', 'Sin proyecto')
    object.__setattr__(app.ldf, 'scLoadFac', 100.0)
    app.creados.clear()
    return app


def _plan(**extra):
    plan = {'project': 'P', 'feeders': ['F1'], 'case': 'sin_proyecto', 'tasa': 0.05,
            'anios': [0, 4, 8, 20], 'limites': LIM,
            'native_action_context': contexto_nativo('P', ['F1'], 'pide')}
    plan.update(extra)
    return plan


def test_cada_anio_con_la_demanda_escalada(guion):
    """024:RF-53 — cada año del horizonte se calcula en DIgSILENT con la demanda de ese año,
    y el factor de escala vuelve a su valor."""
    app = _app()
    informe, rc = guion.ejecutar(app, _plan())
    assert rc == 0, informe
    assert [a['anio'] for a in informe['anios']] == [0, 4, 8, 20]
    assert informe['anios'][3]['factor'] == pytest.approx(1.05 ** 20)
    minimas = [a['vm_min'] for a in informe['anios']]
    assert minimas == sorted(minimas, reverse=True)
    assert app.ldf.scLoadFac == 100.0 and app.creados == []


def test_sin_tasa_no_se_supone(guion):
    """024:RF-51 — sin tasa de crecimiento no se inventa una: código 2 y el motivo."""
    informe, rc = guion.ejecutar(_app(), _plan(tasa=None))
    assert rc == 2 and 'tasa' in informe['error']


def test_el_anio_que_no_converge_se_dice(guion):
    """024:RF-53 — si con la demanda de un año no converge, ese año lo dice y se sigue."""
    app = _app()
    app.ldf.limite = 0.2
    informe, rc = guion.ejecutar(app, _plan(anios=[0, 20]))
    assert rc == 0
    assert informe['anios'][0]['converge'] and not informe['anios'][1]['converge']
    assert app.ldf.scLoadFac == 100.0
