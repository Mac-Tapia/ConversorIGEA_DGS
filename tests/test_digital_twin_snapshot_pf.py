"""Spec 024, T5: lectura nativa de solo lectura tras reabrir, contra ``fake_pf``.

La prueba en DIgSILENT del caso dorado es la T8; aquí, que la lectura no escribe nada,
reabre el proyecto, separa las islas por los tramos abiertos y devuelve el flujo con
unidades en la forma que espera ``capture.py``.
"""
from __future__ import annotations

import json
import os
import random

import fake_pf
import pytest
from apoyo import cargar_herramienta, contexto_nativo

from igea_dgs.digital_twin.episode import RESULTADOS_FLUJO
from igea_dgs.digital_twin.native_snapshot import (
    componentes,
    huella_gps,
    identidad_nativa,
)

SEMILLA = int(os.environ.get('IGEA_SCALE_SEED', random.randrange(1 << 30)))


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('digital_twin_snapshot_pf.py', 'digital_twin_snapshot_guion',
                              tools_en_path=True)


def _alimentadores():
    rnd = random.Random(SEMILLA)
    return tuple(f'F{i}' for i in range(1, rnd.randint(2, 6)))


def _app(feeders, caso='Con proyecto'):
    app = fake_pf.proyecto(alimentadores=feeders, cargas_por_alim=3, bt=True, flujo=True)
    if caso:
        app.carpetas['study'].CreateObject('IntCase', caso)
    app.escrituras.clear()
    app.creados.clear()
    return app


def _plan(feeders, **extra):
    plan = {'project': 'P', 'feeders': list(feeders), 'case': 'con_proyecto',
            'native_action_context': contexto_nativo('P', list(feeders), 'obras_ejecutar')}
    plan.update(extra)
    return plan


def test_identidad_huella_e_islas_puras():
    """024:RF-2 / 024:RF-3 — identidad por ruta y clase, huella del trazado e islas por
    tramos cerrados, sin suponer red radial."""
    assert identidad_nativa('ElmTerm', 'U\\P.IntPrj\\Red\\B1', 'U\\P.IntPrj') == 'ElmTerm:Red\\B1'
    assert huella_gps([[-14.0, -75.7], [-14.1, -75.8]]) == huella_gps([[-14.0, -75.7], [-14.1, -75.8]])
    assert huella_gps([[-14.0, -75.7]]) != huella_gps([[-14.0, -75.70001]])
    islas = componentes(['a', 'b', 'c', 'd'], [('a', 'b', True), ('b', 'c', False), ('c', 'd', True)])
    assert islas == [['a', 'b'], ['c', 'd']]
    assert componentes(['a', 'b'], [('a', 'b', True), ('b', 'a', True)]) == [['a', 'b']]


def test_lee_sin_escribir_y_con_reapertura(guion):
    """024:RF-27 / 024:RF-28 — reabre el proyecto, activa el caso y devuelve tensiones,
    cargabilidad, cabeceras y pérdidas con unidades, sin escribir nada."""
    feeders = _alimentadores()
    app = _app(feeders)
    lectura, rc = guion.ejecutar(app, _plan(feeders))
    assert rc == 0, f'semilla {SEMILLA}: {lectura}'
    assert app.escrituras == [] and app.creados == []
    assert lectura['reopen_verified'] is True
    assert lectura['feeders'] == list(feeders)
    assert set(lectura['flujo']) == set(RESULTADOS_FLUJO)
    assert lectura['flujo']['tensiones']['unidad'] == 'p.u.'
    assert lectura['flujo']['tensiones']['valores']
    # El flujo del doble solo deja ``c:loading`` en los transformadores.
    assert lectura['flujo']['cargabilidad']['valores']['transformadores']
    assert set(lectura['flujo']['balance']['valores']['cabeceras']) == set(feeders)
    assert 'ausente' in lectura['flujo']['confiabilidad']


def test_la_lectura_trae_el_grafo_y_el_episodio_entrena(guion):
    """027:RF-1 — la lectura tras una acción trae el grafo eléctrico con los mismos
    identificadores que las tensiones, y el episodio que se arma con ella es entrenable:
    los de las calibraciones de Nasca y Chincha (2026-10-28) traían tensiones y no grafo."""
    from igea_dgs.digital_twin.oraculo import VERSION_GRAFO, muestra

    feeders = _alimentadores()
    lectura, rc = guion.ejecutar(_app(feeders), _plan(feeders))
    assert rc == 0, f'semilla {SEMILLA}: {lectura}'
    grafo = lectura['topologia']['grafo']
    assert grafo['version'] == VERSION_GRAFO and grafo['nodos'] and grafo['ramas']
    tensiones = lectura['flujo']['tensiones']['valores']
    assert set(tensiones) <= set(grafo['nodos']), 'mismos identificadores'
    m = muestra(grafo, tensiones)
    assert m.mascara.sum() == len(tensiones) and len(m.z) > 0


def test_tramo_abierto_es_frontera_y_parte_la_isla(guion):
    """024:RF-2 — un tramo abierto queda en la frontera y separa sus dos lados."""
    feeders = ('F1',)
    app = _app(feeders)
    cerrado, _ = guion.ejecutar(app, _plan(feeders))
    linea = next(o for o in app.proyecto.GetContents('*.ElmLne', 1) if o.loc_name == 'F1_L2')
    linea.outserv = 1
    abierto, _ = guion.ejecutar(app, _plan(feeders))
    assert any('F1_L2' in f for f in abierto['topologia']['frontera'])
    assert len(abierto['topologia']['componentes']) == len(cerrado['topologia']['componentes']) + 1


def test_huella_del_trazado_pedido(guion):
    """024:RF-3 / 024:RF-25 — la huella del trazado de cada elemento pedido."""
    feeders = ('F1',)
    app = _app(feeders)
    lectura, _ = guion.ejecutar(app, _plan(feeders, huellas_gps_de=['F1_L1']))
    linea = next(o for o in app.proyecto.GetContents('*.ElmLne', 1) if o.loc_name == 'F1_L1')
    assert lectura['topologia']['huellas_gps'] == {'F1_L1': huella_gps(linea.GPScoords)}


def test_variacion_esperada_que_no_esta_no_es_reapertura(guion):
    """024:RF-27 — si tras reabrir falta una variación que la acción dejó, no vale."""
    feeders = ('F1',)
    lectura, _ = guion.ejecutar(_app(feeders), _plan(feeders, variaciones_esperadas=['IGEA obra 1']))
    assert lectura['reopen_verified'] is False and lectura['avisos']


def test_sin_el_caso_pedido(guion):
    """024:RF-9 — sin el caso pedido no hay lectura que valga."""
    lectura, rc = guion.ejecutar(_app(('F1',), caso=None), _plan(('F1',)))
    assert rc == 2 and 'Con proyecto' in lectura['error']


def test_sin_converger_no_hay_flujo(guion):
    """024:RF-4 — si no converge tras reabrir, la lectura lo dice y no trae resultados."""
    app = _app(('F1',))
    app.ldf.limite = 0.01
    lectura, rc = guion.ejecutar(app, _plan(('F1',)))
    assert rc == 2 and lectura['flujo'] is None


def test_main_bloquea_un_plan_sin_contexto(guion, tmp_path):
    """024:RF-1 — sin contexto firmado no se abre DIgSILENT."""
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps({'project': 'P', 'feeders': ['F1']}), encoding='utf-8')
    salida = tmp_path / 'lectura.json'
    assert guion.main(['--plan', str(plan), '--output-json', str(salida)]) == 2
    assert json.loads(salida.read_text(encoding='utf-8'))['status'] == 'BLOQUEADO_DATOS'
