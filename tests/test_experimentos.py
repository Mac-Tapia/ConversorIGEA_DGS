"""043:RF-2 — identidad exacta y contrato de experimentos reproducibles."""
from dataclasses import asdict, replace
import json

import pytest

from convertersmartgrid.experimentos import (
    ContextoExperimento, ExperimentoSpec, cargar_experimento, clave_contexto,
)


def contexto():
    return ContextoExperimento(
        source_run_id='entrega-1', source_mode='txt', source_fingerprint='a' * 64,
        project='Proyecto', feeders=('F1', 'F2'), case_id='caso/2026/sin',
        case_role='sin_proyecto', year=2026, period='2026-09', criterio_fijas='coincidente',
        profile_hash='b' * 64, topology_hash='c' * 64, controls_hash='d' * 64,
        scenario_hash='e' * 64)


def test_contexto_distinto_no_reutiliza():
    """043:RF-2 — mismo nombre nunca compensa fuente o criterio distintos."""
    ctx = contexto()
    claves = {clave_contexto(ctx), clave_contexto(replace(ctx, source_run_id='entrega-2')),
              clave_contexto(replace(ctx, criterio_fijas='maximo_mes')),
              clave_contexto(replace(ctx, feeders=('F2', 'F1')))}
    assert len(claves) == 4


def test_cargar_experimento_y_hash_estable(tmp_path):
    """043:RF-2 — orden de claves JSON no altera la identidad de configuración."""
    ruta = tmp_path / 'experimento.json'
    payload = {'schema_version': 1, 'contexto': asdict(contexto()), 'algoritmo': 'gru',
               'semillas': [11, 23], 'politica': {'cobertura_objetivo': 0.9}, 'revision': 'abc123'}
    ruta.write_text(json.dumps(payload), encoding='utf-8')
    experimento = cargar_experimento(ruta)
    assert isinstance(experimento, ExperimentoSpec)
    assert experimento.contexto == contexto()
    ruta.write_text(json.dumps(payload, sort_keys=True), encoding='utf-8')
    assert cargar_experimento(ruta).huella == experimento.huella
    payload['semillas'] = [11, 37]
    ruta.write_text(json.dumps(payload), encoding='utf-8')
    assert cargar_experimento(ruta).huella != experimento.huella


@pytest.mark.parametrize('cambio', [
    {'source_run_id': ''}, {'source_mode': 'desconocido'}, {'source_fingerprint': 'abc'},
    {'feeders': ('F1', 'F1')}, {'year': True}, {'case_role': 'inventado'},
])
def test_contexto_incompleto_rechaza(cambio):
    """043:RF-2 — el contexto no se rellena con defaults que mezclen experimentos."""
    with pytest.raises(ValueError):
        replace(contexto(), **cambio)


def test_experimento_rechaza_campos_desconocidos(tmp_path):
    """043:RF-2 — una configuración no soportada no se ignora silenciosamente."""
    ruta = tmp_path / 'experimento.json'
    ruta.write_text(json.dumps({'schema_version': 99, 'otro': 1}), encoding='utf-8')
    with pytest.raises(ValueError):
        cargar_experimento(ruta)
