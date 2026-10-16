"""Spec 008: ``tools/verificar_pf.py`` contra un DIgSILENT simulado (``fake_pf``).

La verificación no escribe en el proyecto: ejecuta el flujo con lo que esté activo y
mide la cabecera de cada alimentador pedido. La prueba real la hace el usuario (T7).
"""
from __future__ import annotations

import json
import os
import random
import sys
import types

import pytest

import fake_pf
from apoyo import cargar_herramienta, contexto_nativo

SEMILLA = int(os.environ.get('IGEA_SCALE_SEED', random.randrange(1 << 30)))


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('verificar_pf.py', 'verificar_pf_guion', tools_en_path=True)


def _alimentadores():
    rnd = random.Random(SEMILLA)
    return tuple(f'F{i}' for i in range(1, rnd.randint(2, 7)))


def _plan(feeders):
    return {'project': 'P', 'feeders': list(feeders),
            'native_action_context': contexto_nativo('P', list(feeders), 'verificar')}


def test_converge_y_mide_cada_cabecera(guion):
    """008:RF-18 / 008:RF-19 — converge, tensiones extremas y la cabecera de cada alimentador,
    sin escribir en el proyecto."""
    feeders = _alimentadores()
    app = fake_pf.proyecto(alimentadores=feeders, cargas_por_alim=3, bt=True, flujo=True)
    informe, rc = guion.ejecutar(app, _plan(feeders))
    assert rc == 0, f'semilla {SEMILLA}: {informe}'
    assert informe['flujo']['converged'] and informe['flujo']['vm_min'] is not None
    assert [f['feeder'] for f in informe['feeders']] == list(feeders)
    for fila in informe['feeders']:
        # 3 cargas de 50 kW más las pérdidas del doble.
        assert fila['cabecera']['kw'] > 150.0 and fila['motivo'] is None
    assert app.escrituras == [] and app.creados == []
    assert informe['variaciones_activas'] == []


def test_no_converge(guion):
    """008:RF-19 — sin convergencia no hay cabecera, y el código lo dice."""
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=3, bt=True, flujo=True)
    app.ldf.limite = 0.01
    informe, rc = guion.ejecutar(app, _plan(['F1']))
    assert rc == 2 and not informe['flujo']['converged']
    assert informe['feeders'][0]['cabecera'] is None
    assert 'no converge' in informe['feeders'][0]['motivo']


def test_alimentador_sin_cabecera(guion):
    """008:RF-19 — un alimentador sin ElmFeeder con cabecera se informa, sin tumbar la verificación."""
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=2, bt=True, flujo=True)
    informe, rc = guion.ejecutar(app, _plan(['F1', 'NOEXISTE']))
    assert rc == 0
    fila = informe['feeders'][1]
    assert fila['cabecera'] is None and 'ElmFeeder' in fila['motivo']


def test_main_escribe_informe_tambien_si_revienta(guion, tmp_path, monkeypatch):
    """008:RF-17 — un error inesperado de la verificación queda en el informe."""
    app = fake_pf.proyecto(alimentadores=('F1',), bt=True, flujo=True)
    monkeypatch.setitem(sys.modules, 'powerfactory', types.SimpleNamespace(GetApplicationExt=lambda: app))
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps(_plan(['F1'])), encoding='utf-8')
    salida = tmp_path / 'informe.json'
    assert guion.main(['--plan', str(plan), '--output-json', str(salida)]) == 0
    assert json.loads(salida.read_text(encoding='utf-8'))['flujo']['converged']

    monkeypatch.setattr(guion, 'ejecutar', lambda *_a: 1 / 0)
    assert guion.main(['--plan', str(plan), '--output-json', str(salida)]) == 1
    informe = json.loads(salida.read_text(encoding='utf-8'))
    assert informe['modo'] == 'verificar' and 'ZeroDivisionError' in informe['error']
