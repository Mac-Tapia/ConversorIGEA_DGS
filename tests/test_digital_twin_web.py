"""Spec 024, T7: consulta del búfer del gemelo desde la web y con la herramienta."""
from __future__ import annotations

import json

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx2')

from apoyo import cargar_herramienta, vincular_proyecto
from fastapi.testclient import TestClient
from test_digital_twin_episode import _payload

from igea_dgs.digital_twin import episode as ep
from igea_dgs.digital_twin.buffer import BuferEpisodios
from igea_dgs.web.app import create_app


def _episodio(proyecto='P', caso='sin_proyecto', clase='accepted', feeders=('A1', 'A2')):
    p = _payload(caso=caso, clase=clase)
    p['nativo'].update(project=proyecto, feeders=list(feeders))
    return BuferEpisodios().guardar(ep.leer_episodio(p)).stem


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as c:
        yield c


def _wid(client):
    return client.post('/api/workspaces', json={'name': 'gemelo'}).json()['id']


def test_lista_y_detalle_de_los_proyectos_vinculados(client):
    """024:RF-8 — la web lista y muestra los episodios de los proyectos vinculados, con
    filtros; los de otro proyecto no se ven."""
    wid = _wid(client)
    vincular_proyecto(client, wid, 'P', ['A1', 'A2'])
    mio = _episodio('P')
    con = _episodio('P', caso='con_proyecto', clase='converged_with_violations')
    _episodio('AJENO')
    r = client.get(f'/api/workspaces/{wid}/digital-twin/episodes')
    assert r.status_code == 200
    assert {e['episode_id'] for e in r.json()} == {mio, con}
    r = client.get(f'/api/workspaces/{wid}/digital-twin/episodes', params={'caso': 'con_proyecto'})
    assert [e['episode_id'] for e in r.json()] == [con]
    r = client.get(f'/api/workspaces/{wid}/digital-twin/episodes', params={'alimentador': 'A2'})
    assert len(r.json()) == 2
    detalle = client.get(f'/api/workspaces/{wid}/digital-twin/episodes/{mio}')
    assert detalle.status_code == 200 and detalle.json()['episode_id'] == mio


def test_detalle_ajeno_o_invalido_es_404(client):
    """024:RF-8 — un episodio de otro proyecto, inexistente o con un identificador que no es
    una huella responde 404."""
    wid = _wid(client)
    vincular_proyecto(client, wid, 'P', ['A1'])
    ajeno = _episodio('AJENO')
    for ident in (ajeno, 'c' * 64, '..%2F..%2Fsecreto'):
        assert client.get(f'/api/workspaces/{wid}/digital-twin/episodes/{ident}').status_code == 404


@pytest.fixture(scope='module')
def herramienta():
    return cargar_herramienta('digital_twin_buffer.py', 'digital_twin_buffer_cli')


def test_herramienta_registra_lista_y_rehace(herramienta, tmp_path, capsys):
    """024:RF-6 / 024:RF-8 / 024:RF-9 — registrar dos veces es idempotente; se lista con
    filtros y se rehace el índice; un manifiesto no válido sale con código 2."""
    raiz = tmp_path / 'twin'
    manifiesto = tmp_path / 'e.json'
    manifiesto.write_text(json.dumps(_payload()), encoding='utf-8')
    assert herramienta.main(['--raiz', str(raiz), 'validate', str(manifiesto)]) == 0
    assert herramienta.main(['--raiz', str(raiz), 'register', str(manifiesto)]) == 0
    assert herramienta.main(['--raiz', str(raiz), 'register', str(manifiesto)]) == 0
    capsys.readouterr()
    assert herramienta.main(['--raiz', str(raiz), 'list', '--caso', 'sin_proyecto']) == 0
    assert len(capsys.readouterr().out.strip().splitlines()) == 1
    assert herramienta.main(['--raiz', str(raiz), 'rebuild-index']) == 0
    assert 'índice rehecho con 1' in capsys.readouterr().out
    malo = tmp_path / 'malo.json'
    malo.write_text(json.dumps(_payload(caso='raro')), encoding='utf-8')
    assert herramienta.main(['--raiz', str(raiz), 'register', str(malo)]) == 2
    assert herramienta.main(['--raiz', str(raiz), 'show', 'no-es-huella']) == 2
