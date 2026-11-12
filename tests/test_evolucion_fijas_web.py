"""Spec 105: la API de la evolución de los clientes fijos y de la carpeta de archivo."""
from __future__ import annotations

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx2')
pytest.importorskip('python_calamine')
pytest.importorskip('openpyxl')
pytest.importorskip('pandas')

from fastapi.testclient import TestClient  # noqa: E402

from apoyo import esperar_trabajo  # noqa: E402
from test_evolucion_clientes_fijos import _mes  # noqa: E402
from test_pronostico_demanda import _libro_clientes, _suministros  # noqa: E402

from convertersmartgrid import archivo_informes as ar  # noqa: E402
from convertersmartgrid.web.app import create_app  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    monkeypatch.setattr(ar, 'ruta_config', lambda: tmp_path / 'config' / 'archivo.json')
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as c:
        yield c


def _espacio_con_libros(client, tmp_path) -> str:
    for mes, base in (('2026-01', 100.0), ('2026-02', 110.0), ('2026-03', 121.0)):
        _libro_clientes(tmp_path / 'cli' / '2026' / f'{mes[5:]}26clientes.xlsx',
                        {'900' if mes > '2026-01' else '111': _mes(mes, base), '555': _mes(mes, base / 10)})
    sumi = _suministros(tmp_path / 'sum' / 'sum.xlsx', [('111', '900', 'S1', 'F1'), ('555', '555', 'S5', 'F2')])
    wid = client.post('/api/workspaces').json()['id']
    for tipo, ruta in (('suministros', sumi), ('clientes', tmp_path / 'cli')):
        r = client.post(f'/api/workspaces/{wid}/demanda/{tipo}/path', json={'path': str(ruta)})
        assert r.status_code == 200, r.text
    esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/demanda/clientes/indexar').json())
    return wid


def test_estado_dice_lo_que_falta_sin_libros(client):
    """105:RF-1, 105:RF-18 — sin libros asignados no hay alimentadores y se dice qué falta."""
    wid = client.post('/api/workspaces').json()['id']
    r = client.get(f'/api/workspaces/{wid}/clientes-fijos/evolucion')
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['alimentadores'] == [] and d['resultado'] is None and d['archivo'] is None
    assert d['faltan'] == ['el libro de clientes importantes', 'el libro de suministros']
    assert client.post(f'/api/workspaces/{wid}/clientes-fijos/evolucion',
                       json={'alimentadores': ['F1'], 'desde': '2026-01', 'hasta': '2026-02'}).status_code == 400


def test_peticion_invalida_422(client, tmp_path):
    """105:RF-19 — rango al revés, mes mal escrito o sin alimentadores: 422."""
    wid = _espacio_con_libros(client, tmp_path)
    ruta = f'/api/workspaces/{wid}/clientes-fijos/evolucion'
    for cuerpo in ({'alimentadores': ['F1'], 'desde': '2026-03', 'hasta': '2026-01'},
                   {'alimentadores': ['F1'], 'desde': '2026-13', 'hasta': '2026-12'},
                   {'alimentadores': [], 'desde': '2026-01', 'hasta': '2026-02'},
                   {'alimentadores': ['  '], 'desde': '2026-01', 'hasta': '2026-02'}):
        assert client.post(ruta, json=cuerpo).status_code == 422, cuerpo


def test_trabajo_libro_resultado_curva_y_archivo(client, tmp_path):
    """105:RF-17, 105:RF-18, 105:RF-20, 105:RF-27, 105:RF-30 — el trabajo deja el libro en «Resultados», el último
    resultado, la curva del cliente y la copia en el archivo."""
    wid = _espacio_con_libros(client, tmp_path)
    (tmp_path / 'archivo').mkdir()
    assert client.put('/api/archivo', json={'ruta': str(tmp_path / 'archivo')}).json() == {
        'ruta': (tmp_path / 'archivo').as_posix()}
    estado = client.get(f'/api/workspaces/{wid}/clientes-fijos/evolucion').json()
    assert estado['alimentadores'] == ['F1', 'F2'] and estado['meses'] == ['2026-01', '2026-02', '2026-03']
    assert estado['faltan'] == [] and estado['cabecera'] is False
    job = client.post(f'/api/workspaces/{wid}/clientes-fijos/evolucion',
                      json={'alimentadores': ['F1'], 'desde': '2026-01', 'hasta': '2026-03'})
    assert job.status_code == 202, job.text
    final = esperar_trabajo(client, job.json(), timeout=120)
    assert final['status'] == 'done', final
    rel = 'clientes_fijos/F1_2026-01_a_2026-03/F1_clientes_fijos_2026-01_a_2026-03.xlsx'
    assert final['result']['libro'] == rel
    assert rel in [o['path'] for o in client.get(f'/api/workspaces/{wid}/outputs').json()]
    archivado = tmp_path / 'archivo' / 'informes' / 'clientes_fijos' / 'F1' / '2026-01_a_2026-03' / rel.split('/')[-1]
    assert archivado.is_file() and final['result']['archivo']['ruta'] == archivado.as_posix()
    d = client.get(f'/api/workspaces/{wid}/clientes-fijos/evolucion').json()['resultado']
    assert [c['codigo'] for c in d['clientes']] == ['900'] and d['renumeraciones'][0]['anterior'] == '111'
    curva = client.get(f'/api/workspaces/{wid}/clientes-fijos/evolucion/curva', params={'cliente': '900'}).json()
    assert curva['puntos'][0][0] == '2026-01-01T00:15' and len(curva['puntos']) == (31 + 28 + 31) * 96
    assert client.get(f'/api/workspaces/{wid}/clientes-fijos/evolucion/curva',
                      params={'cliente': '555'}).status_code == 400


def test_archivo_que_falla_no_pierde_el_libro(client, tmp_path):
    """105:RF-31 — con la carpeta de archivo desconectada, el libro queda en la salida y se avisa."""
    wid = _espacio_con_libros(client, tmp_path)
    carpeta = tmp_path / 'unidad'
    carpeta.mkdir()
    client.put('/api/archivo', json={'ruta': str(carpeta)})
    carpeta.rmdir()                                       # la unidad se desconecta
    final = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/clientes-fijos/evolucion', json={
        'alimentadores': ['F2'], 'desde': '2026-01', 'hasta': '2026-02', 'con_cabecera': False}).json(), timeout=120)
    assert final['status'] == 'done', final
    assert final['result']['archivo']['ruta'] is None and 'no está disponible' in final['result']['archivo']['aviso']
    assert final['result']['libro'] in [o['path'] for o in client.get(f'/api/workspaces/{wid}/outputs').json()]


def test_poner_y_quitar_la_carpeta_de_archivo(client, tmp_path):
    """105:RF-28, 105:RF-29 — sin ruta, ninguna; una que no existe, 400; vacía, se quita."""
    assert client.get('/api/archivo').json() == {'ruta': None}
    assert client.put('/api/archivo', json={'ruta': str(tmp_path / 'no')}).status_code == 400
    (tmp_path / 'a').mkdir()
    assert client.put('/api/archivo', json={'ruta': str(tmp_path / 'a')}).json()['ruta'] == (tmp_path / 'a').as_posix()
    assert client.put('/api/archivo', json={'ruta': ''}).json() == {'ruta': None}
    assert client.get('/api/archivo').json() == {'ruta': None}
