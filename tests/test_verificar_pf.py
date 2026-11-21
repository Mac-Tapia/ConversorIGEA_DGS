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

SEMILLA = int(os.environ.get('CSG_SCALE_SEED', random.randrange(1 << 30)))


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


#: Lo que escribió DIgSILENT en la verificación del 2026-11-20 (``DIAG_NOCONV/corrida_2/ventana_ldf.txt``), recortado.
VENTANA_SIN_CONVERGER = (['info - Grid split into 4 isolated areas']
                         + [f'info - Load flow iteration: {i}' for i in range(76)]
                         + ['warn - Newton-Raphson Algorithm did not converge. Maximum number of iterations reached.',
                            'err  - No convergence in load flow.', 'err  - Load flow calculation not executed.'])


def _ventana_al_ejecutar(app, lineas):
    original = app.ldf.Execute

    def ejecutar():
        rc = original()
        app.salida.extend(lineas)
        return rc

    object.__setattr__(app.ldf, 'Execute', ejecutar)


def test_008_rf30_sin_converger_trae_lo_que_dice_digsilent(guion):
    """008:RF-30 / 025:RF-66 — sin convergencia, el informe dice por qué con las palabras de DIgSILENT: sus errores y
    advertencias, no las 76 líneas de iteración. El 2026-11-20 solo decía ``return_code 1``."""
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=3, bt=True, flujo=True)
    app.ldf.limite = 0.01
    _ventana_al_ejecutar(app, VENTANA_SIN_CONVERGER)
    app.escrituras.clear()                              # lo de la preparación no cuenta
    informe, rc = guion.ejecutar(app, _plan(['F1']))
    assert rc == 2 and not informe['flujo']['converged']
    assert informe.get('mensajes') == VENTANA_SIN_CONVERGER[-3:], informe.get('mensajes')
    assert app.escrituras == [] and app.creados == []


def test_008_rf30_con_convergencia_no_hay_mensajes(guion):
    """008:RF-30 — si converge, ``mensajes`` va vacío: la ventana no se lleva al informe."""
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=3, bt=True, flujo=True)
    _ventana_al_ejecutar(app, ['info - Load flow iteration: 0'])
    informe, rc = guion.ejecutar(app, _plan(['F1']))
    assert rc == 0 and informe.get('mensajes') == []


def test_008_rf31_avisa_de_sed_ntp_apagada_sin_encenderla(guion):
    """008:RF-31 / 008:RF-18 — ``SED_NTP_P`` existe y está apagada: el informe lo dice con sus transformadores y cuántos
    quedan por encima del 100 % con lo activo, sin activarla ni escribir. El 2026-11-20 eran 7, el más cargado al 2 048 %."""
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=3, bt=True, flujo=True)
    carga = next((c for c in app.GetCalcRelevantObjects('*.ElmLod') if c.loc_name == 'F1_S1'), None)
    assert carga is not None
    carga.plini = 0.3                                   # 300 kW sobre 100 kVA del archivo; con la etapa, 630 kVA
    variacion = fake_pf.variacion_del_conversor_apagada(app, 'SED_NTP_P', {'TR_F1_S1': 630.0, 'TR_F1_S2': 250.0})
    assert all(t.typ_id.strn == 0.1 for t in app.GetCalcRelevantObjects('*.ElmTr2')), 'el doble la deja apagada'
    informe, rc = guion.ejecutar(app, _plan(['F1']))
    assert rc == 0
    [fila] = informe.get('variaciones_del_conversor_apagadas') or [None]
    assert fila is not None, informe
    assert (fila['variacion'], fila['transformadores'], fila['sobre_100']) == ('SED_NTP_P', 2, 1)
    assert fila['maxima_pct'] == pytest.approx(100.0 * 300.0 / 0.95 / 100.0, rel=1e-3)
    assert fila['aviso'] in informe['avisos'] and 'SED_NTP_P' in fila['aviso'] and '2 transformadores' in fila['aviso']
    assert variacion not in app.variaciones_activas and 'SED_NTP_P' not in informe['variaciones_activas']
    assert app.escrituras == [] and app.creados == []


def test_008_rf31_activa_o_sin_variacion_no_avisa(guion):
    """008:RF-31 — sin ``Fichas_``/``SED_NTP_``, o con ellas activas, no hay aviso."""
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=3, bt=True, flujo=True)
    informe, _rc = guion.ejecutar(app, _plan(['F1']))
    assert 'variaciones_del_conversor_apagadas' not in informe and informe['avisos'] == []
    variacion = fake_pf.variacion_del_conversor_apagada(app, 'SED_NTP_P', {'TR_F1_S1': 630.0})
    variacion.Activate()
    informe, _rc = guion.ejecutar(app, _plan(['F1']))
    assert 'variaciones_del_conversor_apagadas' not in informe
