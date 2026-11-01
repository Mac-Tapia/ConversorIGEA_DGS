"""043:RF-8 — el estado visible necesita evidencia, no el fin de un proceso."""
import json

from fastapi.testclient import TestClient

from igea_dgs.web.app import create_app


def test_modelos_web_no_infiere_promocion(tmp_path, monkeypatch):
    """043:RF-8 — un informe sin candidato íntegro no prueba promoción."""
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    ruta = tmp_path / 'asistente/training/report.json'
    ruta.parent.mkdir(parents=True)
    ruta.write_text(json.dumps({'complete': True, 'stages': [
        {'model': 'gru', 'status': 'PROMOVIDO'}]}), encoding='utf-8')
    with TestClient(create_app(tmp_path / 'web')) as client:
        respuesta = client.get('/api/asistente/modelos')
    assert respuesta.status_code == 200
    payload = respuesta.json()
    assert payload['schema_version'] == 1
    assert len(payload['familias']) == 7
    gru = next(f for f in payload['familias'] if f['familia'] == 'gru')
    assert gru['estado'] is None
    assert gru['bloqueos']
    assert not payload['complete']


def test_ausencia_de_informe_es_pendiente(tmp_path, monkeypatch):
    """043:RF-8 — la ausencia no se inventa como etapa entrenada ni rechazada."""
    from igea_dgs.web import services
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    payload = services.asistente_estado_modelos()
    assert all(f['estado'] is None for f in payload['familias'])
    assert not payload['complete']


def test_candidato_bloqueado_visible_sin_informe_global(tmp_path, monkeypatch):
    """043:RF-8 — la destilación registra su decisión sin fingir siete entrenamientos."""
    from igea_dgs.model_registry import RegistroModelo
    from igea_dgs.web import services
    from test_model_registry import _payload
    raiz = tmp_path / 'asistente'
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(raiz))
    registro = RegistroModelo(raiz / 'model_registry')
    datos = _payload(tmp_path)
    datos['decision'] = {'status': 'BLOQUEADO_POR_DATOS', 'gates': {'approved': False},
                         'fallos': ['tres órdenes humanas independientes']}
    c = registro.registrar_candidato('transformer', **datos)
    fila = next(f for f in services.asistente_estado_modelos()['familias'] if f['familia'] == 'transformer')
    assert fila['estado'] == 'BLOQUEADO_POR_DATOS' and fila['candidate_id'] == c['candidate_id']
    assert registro.activo('transformer') is None


def test_decision_reciente_no_queda_oculta_por_informe_viejo(tmp_path, monkeypatch):
    """043:RF-8 — se distingue última decisión de candidato y modelo que sigue activo."""
    import os
    from igea_dgs.model_registry import RegistroModelo
    from igea_dgs.web import services
    from test_model_registry import _payload
    raiz = tmp_path / 'asistente'
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(raiz))
    registro = RegistroModelo(raiz / 'model_registry')
    viejo = registro.registrar_candidato('transformer', **_payload(tmp_path))
    registro.promover('transformer', viejo['candidate_id'])
    reporte = raiz / 'training/report.json'; reporte.parent.mkdir()
    reporte.write_text(json.dumps({'stages': [{'model': 'transformer', 'status': 'PROMOVIDO',
                          'candidate_id': viejo['candidate_id']}]}), encoding='utf-8')
    os.utime(reporte, (1, 1))
    datos = _payload(tmp_path)
    datos['decision'] = {'status': 'BLOQUEADO_POR_DATOS', 'gates': {'approved': False}}
    nuevo = registro.registrar_candidato('transformer', **datos)
    fila = next(f for f in services.asistente_estado_modelos()['familias'] if f['familia'] == 'transformer')
    assert fila['estado'] == 'BLOQUEADO_POR_DATOS' and fila['candidate_id'] == nuevo['candidate_id']
    assert registro.activo('transformer')['candidate_id'] == viejo['candidate_id']


def test_consulta_modelos_no_relee_pesos_en_http(tmp_path, monkeypatch):
    """043:RF-8 — consultar estado usa manifiestos; no bloquea HTTP leyendo GB de pesos."""
    from pathlib import Path
    from igea_dgs.model_registry import RegistroModelo
    from igea_dgs.web import services
    from test_model_registry import _payload
    raiz = tmp_path / 'asistente'
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(raiz))
    registro = RegistroModelo(raiz / 'model_registry')
    candidato = registro.registrar_candidato('gru', **_payload(tmp_path))
    registro.promover('gru', candidato['candidate_id'])
    ruta = raiz / 'training/report.json'
    ruta.parent.mkdir()
    ruta.write_text(json.dumps({'complete': False, 'stages': [{
        'model': 'gru', 'status': 'PROMOVIDO', 'candidate_id': candidato['candidate_id']}]}), encoding='utf-8')
    original = Path.open
    def abrir(path, *args, **kwargs):
        if path.name == 'pesos.bin':
            pytest.fail('la petición HTTP abrió los pesos')
        return original(path, *args, **kwargs)
    import pytest
    monkeypatch.setattr(Path, 'open', abrir)
    fila = next(f for f in services.asistente_estado_modelos()['familias'] if f['familia'] == 'gru')
    assert fila['estado'] == 'PROMOVIDO'


def test_puntero_activo_corrupto_no_rompe_consulta(tmp_path, monkeypatch):
    """043:RF-8 — un registro ilegible se muestra bloqueado en vez de lanzar HTTP 500."""
    from igea_dgs.web import services
    raiz = tmp_path / 'asistente'
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(raiz))
    ruta = raiz / 'training/report.json'
    ruta.parent.mkdir(parents=True)
    ruta.write_text(json.dumps({'complete': False, 'stages': [{
        'model': 'gru', 'status': 'PROMOVIDO', 'candidate_id': 'a' * 64}]}), encoding='utf-8')
    activo = raiz / 'model_registry/gru/active.json'
    activo.parent.mkdir(parents=True)
    activo.write_text('[1]', encoding='utf-8')
    fila = next(f for f in services.asistente_estado_modelos()['familias'] if f['familia'] == 'gru')
    assert fila['estado'] is None and fila['bloqueos']
