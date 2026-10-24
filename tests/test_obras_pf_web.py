"""Spec 011, T16: la API de las obras de mejora (espacio, bibliotecas, simular y aplicar)."""
from __future__ import annotations

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx2')

from fastapi.testclient import TestClient  # noqa: E402

from apoyo import esperar_trabajo, vincular_proyecto  # noqa: E402
from apoyo_pf_web import guion_falso  # noqa: E402,F401
from igea_dgs.web.app import create_app  # noqa: E402

TERNA = {'clase': 'terna', 'alimentador': 'A1', 'casos': ['Sin proyecto', 'Con proyecto'],
         'tramos': ['L1']}
BANCO = {'clase': 'condensador', 'alimentador': 'A1', 'casos': ['Con proyecto'],
         'barra': 'B1', 'q_kvar': 600, 'escalones': 3}


@pytest.fixture()
def client(tmp_path, monkeypatch, guion_falso):
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as c:
        yield c


def _espacio(client):
    wid = client.post('/api/workspaces').json()['id']
    vincular_proyecto(client, wid, 'P', ['A1'])
    return wid


def _trabajo(client, r):
    assert r.status_code == 202, r.text
    return esperar_trabajo(client, r.json())


def test_obras_guardadas_en_el_espacio_hasta_aplicarlas(client, tmp_path):
    """011:RF-95, 011:RF-70 — cada obra del formulario se valida y queda en el espacio, también
    después de reiniciar el servidor; se puede quitar."""
    wid = _espacio(client)
    a = client.post(f'/api/workspaces/{wid}/obras', json=TERNA)
    b = client.post(f'/api/workspaces/{wid}/obras', json=BANCO)
    assert a.status_code == b.status_code == 201
    assert a.json()['id'] != b.json()['id'] and a.json()['tramos'] == ['L1']
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as otro:
        guardadas = otro.get(f'/api/workspaces/{wid}/obras').json()
    assert [o['clase'] for o in guardadas] == ['terna', 'condensador']
    assert client.delete(f"/api/workspaces/{wid}/obras/{a.json()['id']}").status_code == 204
    assert [o['clase'] for o in client.get(f'/api/workspaces/{wid}/obras').json()] == ['condensador']
    assert client.delete(f"/api/workspaces/{wid}/obras/{a.json()['id']}").status_code == 400


@pytest.mark.parametrize('obra, falta', [
    ({'clase': 'condensador', 'alimentador': 'A1', 'casos': ['Con proyecto'], 'barra': 'B1',
      'q_kvar': -1, 'escalones': 1}, 'potencia'),
    ({**TERNA, 'casos': ['Caso base']}, 'Caso base'),
])
def test_obra_no_valida_se_rechaza_al_definirla(client, obra, falta):
    """011:RF-70, 011:RF-58 — el formulario no guarda una obra que no se podría aplicar."""
    wid = _espacio(client)
    r = client.post(f'/api/workspaces/{wid}/obras', json=obra)
    assert r.status_code == 400 and falta in r.json()['detail']
    assert client.get(f'/api/workspaces/{wid}/obras').json() == []


def test_bibliotecas_en_el_carril_de_powerfactory_y_guardadas(client):
    """011:RF-88, 011:RF-91 — la lectura de tipos es un trabajo del carril de DIgSILENT; lleva
    el otro proyecto y queda guardada para el formulario."""
    wid = _espacio(client)
    estado = _trabajo(client, client.post(f'/api/workspaces/{wid}/pf/obras/bibliotecas', json={
        'project': 'P', 'feeders': ['A1'], 'otro_proyecto': 'Otro'}))
    assert estado['status'] == 'done', estado
    assert estado['lane'] == 'powerfactory'
    recibido = estado['result']['informe']['recibido']
    assert recibido['otro_proyecto'] == 'Otro' and recibido['feeders'] == ['A1'] and 'folder' in recibido
    leidas = client.get(f'/api/workspaces/{wid}/pf/obras/bibliotecas').json()
    assert leidas['project'] == 'P' and leidas['tipos'][0]['nombre'] == 'AAAC_70'


def test_simular_no_toca_las_obras_guardadas(client):
    """011:RF-69, 011:RF-95 — simular manda las obras al guion y no las quita del espacio."""
    wid = _espacio(client)
    for obra in (TERNA, BANCO):
        client.post(f'/api/workspaces/{wid}/obras', json=obra)
    estado = _trabajo(client, client.post(f'/api/workspaces/{wid}/pf/obras/simular',
                                          json={'project': 'P', 'feeders': ['A1']}))
    assert estado['status'] == 'done', estado
    assert estado['result']['informe']['modo'] == 'simular'
    assert [o['clase'] for o in estado['result']['informe']['recibido']['obras']] == ['terna', 'condensador']
    assert 'id' not in estado['result']['informe']['recibido']['obras'][0]
    assert len(client.get(f'/api/workspaces/{wid}/obras').json()) == 2


def test_aplicar_quita_las_creadas_y_deja_las_que_fallaron(client):
    """011:RF-95 — al aplicar, las obras que quedaron en el proyecto salen del espacio; la que
    no se pudo crear se queda para corregirla."""
    wid = _espacio(client)
    buena = client.post(f'/api/workspaces/{wid}/obras', json=TERNA).json()
    mala = client.post(f'/api/workspaces/{wid}/obras', json={**BANCO, 'barra': 'NO_EXISTE'}).json()
    estado = _trabajo(client, client.post(f'/api/workspaces/{wid}/pf/obras/aplicar',
                                          json={'project': 'P', 'feeders': ['A1']}))
    assert estado['status'] == 'done', estado
    assert estado['result']['aplicadas'] == [buena['id']]
    assert [o['id'] for o in client.get(f'/api/workspaces/{wid}/obras').json()] == [mala['id']]


def test_aplicar_solo_las_elegidas(client):
    """011:RF-95 — con ``ids`` se aplican solo esas obras."""
    wid = _espacio(client)
    a = client.post(f'/api/workspaces/{wid}/obras', json=TERNA).json()
    client.post(f'/api/workspaces/{wid}/obras', json=BANCO)
    estado = _trabajo(client, client.post(f'/api/workspaces/{wid}/pf/obras/aplicar',
                                          json={'project': 'P', 'ids': [a['id']]}))
    assert [o['clase'] for o in estado['result']['informe']['recibido']['obras']] == ['terna']


def test_sin_obras_no_hay_nada_que_aplicar(client):
    """011:RF-95 — sin obras guardadas, el trabajo lo dice."""
    wid = _espacio(client)
    estado = _trabajo(client, client.post(f'/api/workspaces/{wid}/pf/obras/aplicar',
                                          json={'project': 'P'}))
    assert estado['status'] == 'failed' and 'defina alguna' in estado['error']


def test_escalera_es_un_trabajo_de_digsilent_con_su_anio(client, monkeypatch):
    """025:RF-44 — la escalera va al carril de DIgSILENT con el año de los casos; un año
    fuera de rango se rechaza antes de empezar."""
    from igea_dgs.web import services

    vistos = []

    def escalera(ws, ctx, project, feeders, *, anio_casos=None, tipo_cambio=None, capex=''):
        vistos.append((project, feeders, anio_casos, tipo_cambio, capex))
        return {'project': project, 'anio_casos': anio_casos, 'alimentadores': []}

    monkeypatch.setattr(services, 'obras_escalera', escalera)
    wid = _espacio(client)
    url = f'/api/workspaces/{wid}/pf/obras/escalera'
    assert client.post(url, json={'project': 'P', 'feeders': ['A1'], 'anio_casos': 99999}).status_code == 422
    # 025:RF-67: el tipo de cambio lo escribe el operador; uno no positivo se rechaza.
    assert client.post(url, json={'project': 'P', 'feeders': ['A1'], 'tipo_cambio': 0}).status_code == 422
    r = client.post(url, json={'project': 'P', 'feeders': ['A1'], 'anio_casos': 2025, 'tipo_cambio': 3.495,
                               'capex': 'D:/libros/capex.xlsx'})
    assert r.json()['lane'] == 'powerfactory'
    estado = _trabajo(client, r)
    assert estado['status'] == 'done', estado
    # 025:RF-53: el libro CAPEX llega por su ruta.
    assert vistos == [('P', ['A1'], 2025, 3.495, 'D:/libros/capex.xlsx')] and estado['result']['anio_casos'] == 2025


def test_escalera_sin_tipo_de_cambio_no_empieza(client, monkeypatch):
    """025:RF-68 — precios de pérdidas en otra moneda y sin tipo de cambio: la escalera no
    toca DIgSILENT y el trabajo dice qué falta."""
    from igea_dgs.web import services

    perfil = {'escalera': {'cumplimiento': 0.95, 'sorteos': 10, 'tolerancia_pu': 0.005,
                           'tolerancia_carga_pct': 1, 'moneda': 'USD', 'moneda_precios_perdidas': 'PEN',
                           'precio_perdidas_kwh': 0.14},
              'planificacion': {'tasa_regulada': 0.12, 'vida_util_anios': 30},
              'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}}
    monkeypatch.setattr('igea_dgs.perfil_empresa.datos_perfil', lambda *a, **k: perfil)
    tocado = []
    monkeypatch.setattr(services, 'obras_bibliotecas', lambda *a, **k: tocado.append(1) or {'informe': {}})
    wid = _espacio(client)
    estado = _trabajo(client, client.post(f'/api/workspaces/{wid}/pf/obras/escalera',
                                          json={'project': 'P', 'feeders': ['A1']}))
    assert estado['status'] == 'failed' and 'tipo de cambio' in estado['error'] and not tocado