"""027:RF-77 — un dataset v1 dirigido al lector v2 se rechaza con su motivo antes de tomar la GPU (D0 de la auditoría
de datasets de Codex, 2026-11-18).

La ruta por defecto de ``tools/reentrenar_modelos.py --dataset`` (``<asistente>/dataset``) es, en una instalación que
viene de antes, un dataset v1. El lector v2 lo rechazaba con «registro v2 sin grupo o duplicado», sin decir que era otro
esquema, y el coordinador solo lo veía dentro del subproceso, después de liberar la GPU de Ollama.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from convertersmartgrid.aplicacion import training_coordinator
from convertersmartgrid.aplicacion.asistente import ollama
from convertersmartgrid.aplicacion.asistente.dataset_entrenamiento import ESQUEMA_DATASET
from convertersmartgrid.aplicacion.trabajadores_ml import leer_dataset_v2
from convertersmartgrid.dominio.util import PREFIJO_ESQUEMA_ANTERIOR

# 058: el nombre del esquema v1 sale de la constante del código, sin escribir aquí el prefijo antiguo.
ESQUEMA_V1 = PREFIJO_ESQUEMA_ANTERIOR + 'training-dataset-v1'


def _dataset(raiz: Path, esquema: str, filas: dict[str, list[dict]]) -> Path:
    raiz.mkdir(parents=True)
    partes = {}
    for nombre in ('train', 'validation', 'test'):
        contenido = ''.join(json.dumps(f, ensure_ascii=False) + '\n' for f in filas.get(nombre, []))
        (raiz / f'{nombre}.jsonl').write_text(contenido, encoding='utf-8', newline='\n')
        partes[nombre] = {'count': len(filas.get(nombre, [])),
                          'sha256': hashlib.sha256((raiz / f'{nombre}.jsonl').read_bytes()).hexdigest()}
    (raiz / 'manifest.json').write_text(json.dumps({'schema': esquema, 'partitions': partes}), encoding='utf-8')
    return raiz


def _v1(raiz: Path) -> Path:
    # Las filas de un v1 no tienen group_id: es lo que hacía saltar el mensaje engañoso.
    return _dataset(raiz, ESQUEMA_V1,
                    {'train': [{'texto': 'calibra el alimentador de prueba', 'tarea': 'calibrar'}]})


def _v2(raiz: Path) -> Path:
    return _dataset(raiz, ESQUEMA_DATASET, {
        'train': [{'record_id': 'r1', 'group_id': 'g1', 'texto': 'calibra el alimentador de prueba'}],
        'validation': [{'record_id': 'r2', 'group_id': 'g2', 'texto': 'convierte la red de prueba'}],
        'test': [{'record_id': 'r3', 'group_id': 'g3', 'texto': 'evalúa el gemelo de prueba'}]})


def _huella(carpeta: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(carpeta.iterdir())}


def test_027_rf77_el_lector_v2_nombra_el_esquema_v1_y_su_remedio(tmp_path):
    """027:RF-77: el rechazo dice que el dataset es v1 y cómo obtener uno v2; no habla de grupos ni duplicados."""
    with pytest.raises(ValueError, match=re.escape(ESQUEMA_V1) + r'.*construir_dataset_entrenamiento'):
        leer_dataset_v2(_v1(tmp_path / 'dataset'))


def test_027_rf77_el_lector_y_el_constructor_hablan_del_mismo_esquema():
    """027:RF-77: la constante del lector (sin importar el constructor, para no cerrar un ciclo) es la del constructor."""
    from convertersmartgrid.aplicacion import trabajadores_ml

    assert getattr(trabajadores_ml, 'ESQUEMA_DATASET_V2', None) == ESQUEMA_DATASET


def test_027_rf77_un_v2_valido_sigue_pasando(tmp_path):
    """027:RF-77: la comprobación nueva no cambia lo que el lector acepta."""
    partes, manifest = leer_dataset_v2(_v2(tmp_path / 'v2'))
    assert manifest['schema'] == ESQUEMA_DATASET and [len(partes[p]) for p in ('train', 'validation', 'test')] == [1, 1, 1]


@pytest.fixture
def sin_gpu(tmp_path, monkeypatch):
    """El coordinador y la liberación de Ollama, sustituidos: la prueba ve si se llega a ellos."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setenv('CSG_TWIN_DATA', str(tmp_path / 'gemelo'))
    llegadas: list[str] = []

    class Coordinador:
        def __init__(self, etapas, run_dir, **kw):
            llegadas.append('coordinador')

        def run(self, resume=False):
            return {'complete': True, 'stages': []}

    monkeypatch.setattr(training_coordinator, 'TrainingCoordinator', Coordinador)
    monkeypatch.setattr(ollama, 'liberar_gpu_para_entrenar', lambda *a, **k: llegadas.append('gpu'))
    return llegadas


def test_027_rf77_reentrenar_para_antes_de_la_gpu_con_un_v1(tmp_path, sin_gpu, capsys):
    """027:RF-77: con un v1 en --dataset, ``run`` sale con BLOQUEADO_POR_DATOS sin crear el coordinador, sin liberar la
    GPU y sin tocar el directorio heredado."""
    from tools.reentrenar_modelos import main

    v1 = _v1(tmp_path / 'dataset')
    antes = _huella(v1)
    rc = main(['run', '--dataset', str(v1), '--run-dir', str(tmp_path / 'run')])
    salida = json.loads(capsys.readouterr().out)
    assert rc == 2 and salida['status'] == 'BLOQUEADO_POR_DATOS' and ESQUEMA_V1 in salida['reason']
    assert sin_gpu == []
    assert _huella(v1) == antes


def test_027_rf77_con_un_v2_valido_llega_al_coordinador(tmp_path, sin_gpu, capsys):
    """027:RF-77: un dataset v2 válido pasa la comprobación y el ciclo sigue como antes."""
    from tools.reentrenar_modelos import main

    rc = main(['run', '--dataset', str(_v2(tmp_path / 'v2')), '--run-dir', str(tmp_path / 'run')])
    capsys.readouterr()
    assert rc == 0 and sin_gpu == ['coordinador']
