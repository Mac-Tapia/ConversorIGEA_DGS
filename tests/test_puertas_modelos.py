"""Spec 071: la PINN se queda en sus redes, puertas comparables, sin autoentrenamiento y un solo turno de GPU.

Sin GPU: las puertas y el dominio se prueban con datos puros.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from convertersmartgrid.digital_twin import oraculo as o
from convertersmartgrid.training_coordinator import BloqueoGPU
from convertersmartgrid.web import app as web_app, services

RAIZ = Path(__file__).resolve().parents[1]


def _muestra(ids):
    return SimpleNamespace(ids=list(ids), x=np.zeros((len(ids), 2)), bloqueos=(), version=o.VERSION_GRAFO)


def _pinn(redes=None):
    dominio = {'x_min': [-1.0, -1.0], 'x_max': [1.0, 1.0], 'nodos': [2, 2], 'version_grafo': o.VERSION_GRAFO}
    if redes is not None:
        dominio['redes'] = redes
    return o.OraculoPINN([], o.Entrenamiento(), dominio)


def test_red_ajena_o_sin_declarar_queda_fuera_de_dominio():
    """071:RF-2: mismos rangos y tamaño, otra red: decide la física."""
    propia, ajena = _muestra(['a', 'b']), _muestra(['c', 'd'])
    modelo = _pinn([o.red_de(propia)])
    assert modelo.fuera_de_dominio(propia) == []
    assert any('red distinta' in x for x in modelo.fuera_de_dominio(ajena))
    assert any('no declara' in x for x in _pinn().fuera_de_dominio(propia))


def test_las_redes_del_modelo_incluyen_todas_sus_particiones():
    """071:RF-1: el dominio declara también la red de prueba."""
    fuente = (RAIZ / 'src/convertersmartgrid/digital_twin/oraculo.py').read_text(encoding='utf-8')
    assert "'redes': sorted({red_de(m) for ms in grupos.values() for m in ms})" in fuente


@pytest.mark.parametrize('error, fisica, actual, texto', [
    (0.003, 0.002, None, 'no mejora al flujo'),
    (0.002, 0.002, None, 'no mejora al flujo'),
    (None, 0.002, None, 'sin medida'),
    (0.001, None, None, 'sin medida'),
    (0.0015, 0.002, 0.001, 'empeora al modelo'),
])
def test_comparacion_que_impide_promover(error, fisica, actual, texto):
    """071:RF-3, 071:RF-4: en la misma prueba, frente a la física y al modelo en uso."""
    assert any(texto in f for f in o.fallos_de_comparacion(error, fisica, actual, o.Puertas()))


def test_comparacion_que_deja_promover():
    """071:RF-3, 071:RF-4: mejora a la física y no empeora al modelo en uso."""
    assert o.fallos_de_comparacion(0.001, 0.002, 0.001, o.Puertas()) == []
    assert o.fallos_de_comparacion(0.001, 0.002, None, o.Puertas()) == []


def test_monitor_cuenta_la_pinn_del_puntero():
    """071:RF-5: solo la familia pinn, promovida y con la versión del puntero."""
    etapa = {'result': {'version': 'v1'}}
    assert services._pinn_promovida_en_uso('pinn', 'PROMOVIDO', etapa, 'v1')
    assert not services._pinn_promovida_en_uso('pinn', 'PROMOVIDO', etapa, 'v2')
    assert not services._pinn_promovida_en_uso('pinn', 'RECHAZADO', etapa, 'v1')
    assert not services._pinn_promovida_en_uso('gru', 'PROMOVIDO', etapa, 'v1')
    assert not services._pinn_promovida_en_uso('pinn', 'PROMOVIDO', {}, None)


def _vigilante(monkeypatch):
    from convertersmartgrid.asistente import vigilancia

    visto = {}
    monkeypatch.setattr(vigilancia.Vigilante, 'arrancar', lambda self: visto.setdefault('v', self))
    monkeypatch.setattr(services, 'asistente_nuevos', lambda: (30, 40))
    web_app.arrancar_vigilancia(SimpleNamespace(list=lambda: [], get=lambda _i: None))
    return visto['v']


@pytest.mark.parametrize('valor, nuevos', [(None, (0, 0)), ('0', (0, 0)), ('1', (30, 40))])
def test_vigilancia_no_entrena_sin_permiso(monkeypatch, valor, nuevos):
    """071:RF-6: sin la variable, no ve datos nuevos: ni lanza ni anuncia; lo demás sigue arrancando."""
    if valor is None:
        monkeypatch.delenv('CSG_AUTOENTRENAMIENTO', raising=False)
    else:
        monkeypatch.setenv('CSG_AUTOENTRENAMIENTO', valor)
    assert _vigilante(monkeypatch).contar_nuevos() == nuevos


def _herramienta(nombre):
    spec = importlib.util.spec_from_file_location(nombre, RAIZ / 'tools' / f'{nombre}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_turno_ocupado_no_entrena_y_lo_dice(tmp_path, monkeypatch):
    """071:RF-7: con otro dueño de la GPU, informe con el motivo y código 1, sin entrenar."""
    from convertersmartgrid.asistente import ollama

    lock = tmp_path / 'gpu.lock'
    monkeypatch.setenv('CSG_ML_GPU_LOCK', str(lock))
    monkeypatch.delenv('CSG_GPU_PARENT_TOKEN', raising=False)
    monkeypatch.setattr(ollama, 'liberar_gpu_para_entrenar', lambda: None)
    llamadas = []
    monkeypatch.setattr(o, 'entrenar', lambda *a, **k: llamadas.append(1))
    monkeypatch.setattr(o, 'entrenar_si_toca', lambda *a, **k: llamadas.append(1))
    salida = tmp_path / 'r.json'
    with BloqueoGPU(lock, 'otra-sesion'):
        codigo = _herramienta('digital_twin_entrenar').main(
            ['--forzar', '--raiz', str(tmp_path / 'twin'), '--output-json', str(salida)])
    r = json.loads(salida.read_text(encoding='utf-8'))
    assert codigo == 1 and not llamadas and not r['entrenado'] and 'GPU ocupada' in r['error']


def test_turno_comun_en_el_alumno_llm():
    """071:RF-8: sin ruta fija: respeta CSG_ML_GPU_LOCK y la guardia heredada."""
    fuente = (RAIZ / 'tools/llm_destilar.py').read_text(encoding='utf-8')
    assert fuente.count('with turno_gpu(') == 3 and 'BloqueoGPU' not in fuente
    assert 'convertersmartgrid-gpu.lock' not in fuente
