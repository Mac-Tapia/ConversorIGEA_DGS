"""Spec 114, T4: el agente MASAC en sombra desde la web: propone sin aplicar, se lee y el operador decide."""
from __future__ import annotations

import pytest

pytest.importorskip('fastapi')

from apoyo import esperar_trabajo, vincular_proyecto
from fastapi.testclient import TestClient
from test_digital_twin_episode import _payload

from convertersmartgrid.adaptadores.digital_twin.buffer import BuferEpisodios
from convertersmartgrid.adaptadores.madrl_puerta import huella_grafo
from convertersmartgrid.adaptadores.masac_entorno import red_sintetica
from convertersmartgrid.dominio.digital_twin import episode as ep
from convertersmartgrid.presentacion.web import agente_sombra
from convertersmartgrid.presentacion.web.app import create_app

#: La red del juguete de la 114: un alimentador de 10 kV fuera de norma que dos bancos arreglan.
RED = red_sintetica(7, sistemas=1, sets=1, alimentadores=1, barras=7, carga_mw=0.4)


def _guardar_red(proyecto: str, grafo: dict) -> None:
    p = _payload()
    p['nativo'].update(project=proyecto, feeders=['S0T0F0'])
    p['topologia'] = {'frontera': ['SEC_1'], 'grafo': grafo}
    BuferEpisodios().guardar(ep.leer_episodio(p))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    monkeypatch.setenv('CSG_AGENTE_DATA', str(tmp_path / 'agente'))
    # La primera política se entrena en el trabajo: aquí con pocos episodios, para no alargar la suite.
    monkeypatch.setattr(agente_sombra, 'EPISODIOS_PRIMERA_POLITICA', 6)
    with TestClient(create_app(tmp_path / 'web')) as c:
        yield c


def _espacio(client, proyecto='PRUEBA114'):
    wid = client.post('/api/workspaces', json={'name': 'agente'}).json()['id']
    vincular_proyecto(client, wid, proyecto, ['S0T0F0'])
    _guardar_red(proyecto, RED)
    return wid


def test_la_web_pide_la_propuesta_en_sombra_y_la_lee_sin_aplicar_nada(client):
    """114:RF-7, 114:RF-9, 114:RF-21 — un trabajo en CPU propone junto a la regla actual (la primera vez entrena la
    política); nada se aplica ni cambia la red."""
    wid = _espacio(client)
    antes = huella_grafo(RED)
    r = client.post(f'/api/workspaces/{wid}/agente/sombra', json={'project': 'PRUEBA114', 'banco_kvar': 300})
    assert r.status_code == 202, r.text
    assert r.json()['lane'] == 'asistente'
    job = esperar_trabajo(client, r.json())
    assert job['status'] == 'done', job
    assert job['result']['aplicada'] is False and job['result']['entrenada'] is True
    assert huella_grafo(RED) == antes
    e = client.get(f'/api/workspaces/{wid}/agente/sombra', params={'project': 'PRUEBA114'})
    assert e.status_code == 200, e.text
    estado = e.json()
    assert estado['modo'] == 'sombra' and estado['hay_politica'] is True
    assert sum(estado['aciertos'].values()) == 1
    ultima = estado['propuestas'][0]
    assert ultima['regla']['obras'] and ultima['acierta'] in ('agente', 'regla', 'empate')
    assert ultima['decisiones'], 'en una red fuera de norma el agente propone algo'
    for d in ultima['decisiones']:
        assert d['estado'] == 'propuesta' and d['confirmo'] is None and d['explicacion'].startswith('Propone ')
    # Otra vez: la política ya está guardada y no se entrena de nuevo.
    job = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/agente/sombra',
                                              json={'project': 'PRUEBA114', 'banco_kvar': 300}).json())
    assert job['result']['entrenada'] is False
    marcador = client.get(f'/api/workspaces/{wid}/agente/sombra', params={'project': 'PRUEBA114'}).json()['aciertos']
    assert sum(marcador.values()) == 2


def test_el_operador_confirma_o_deshace_y_queda_en_el_registro(client):
    """114:RF-11, 114:RF-9, 114:RF-22, 114:RF-23 — la decisión del operador queda en el registro de experiencia, no
    aplica nada y no se decide dos veces."""
    wid = _espacio(client)
    esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/agente/sombra',
                                        json={'project': 'PRUEBA114', 'banco_kvar': 300}).json())
    decisiones = client.get(f'/api/workspaces/{wid}/agente/sombra',
                            params={'project': 'PRUEBA114'}).json()['propuestas'][0]['decisiones']
    primera = decisiones[0]['id']
    r = client.post(f'/api/workspaces/{wid}/agente/sombra/decisiones/{primera}', json={'accion': 'confirmar'})
    assert r.status_code == 200, r.text
    assert r.json() == {'id': primera, 'estado': 'confirmada', 'confirmo': 'operador', 'aplicada': False}
    # Ya decidida, no se decide otra vez.
    assert client.post(f'/api/workspaces/{wid}/agente/sombra/decisiones/{primera}',
                       json={'accion': 'deshacer'}).status_code == 400
    if len(decisiones) > 1:
        otra = decisiones[1]['id']
        assert client.post(f'/api/workspaces/{wid}/agente/sombra/decisiones/{otra}',
                           json={'accion': 'deshacer'}).json()['estado'] == 'deshecha'
    leidas = {d['id']: d for d in client.get(f'/api/workspaces/{wid}/agente/sombra',
                                             params={'project': 'PRUEBA114'}).json()['propuestas'][0]['decisiones']}
    assert leidas[primera]['estado'] == 'confirmada' and leidas[primera]['confirmo'] == 'operador'
    registro = agente_sombra.raiz_agente() / 'registro' / 'experiencia.jsonl'
    assert '"evento": "confirmacion"' in registro.read_text(encoding='utf-8')
    # Una acción que no es confirmar ni deshacer, o un identificador que no es de una decisión, se rechaza.
    assert client.post(f'/api/workspaces/{wid}/agente/sombra/decisiones/{primera}',
                       json={'accion': 'aplicar'}).status_code == 422
    assert client.post(f'/api/workspaces/{wid}/agente/sombra/decisiones/{"0" * 32}',
                       json={'accion': 'confirmar'}).status_code == 400


def test_sin_vinculo_o_sin_red_capturada_se_dice_antes_de_encolar(client):
    """114:RF-7 — un proyecto que el espacio no tiene, o sin red en el gemelo, responde 400 con el motivo."""
    wid = _espacio(client)
    r = client.post(f'/api/workspaces/{wid}/agente/sombra', json={'project': 'AJENO', 'banco_kvar': 300})
    assert r.status_code == 400 and 'no está vinculado' in r.json()['detail']
    vincular_proyecto(client, wid, 'SINRED', ['X1'])
    r = client.post(f'/api/workspaces/{wid}/agente/sombra', json={'project': 'SINRED', 'banco_kvar': 300})
    assert r.status_code == 400 and 'No hay red capturada' in r.json()['detail']
    r = client.post(f'/api/workspaces/{wid}/agente/sombra', json={'project': 'PRUEBA114', 'feeders': ['ZZ9']})
    assert r.status_code == 400 and 'S0T0F0' in r.json()['detail']
    assert client.post(f'/api/workspaces/{wid}/agente/sombra',
                       json={'project': 'PRUEBA114', 'banco_kvar': -1}).status_code == 422
    assert client.get(f'/api/workspaces/{wid}/agente/sombra', params={'project': 'AJENO'}).status_code == 400
