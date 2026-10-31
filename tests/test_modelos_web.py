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
