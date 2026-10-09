"""Spec 004, demanda medida: la API (libros por subida o ruta, medidores, cabecera, cruce, Excel)."""
from __future__ import annotations

import io
from datetime import datetime, timedelta

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx2')
pytest.importorskip('python_calamine')
openpyxl = pytest.importorskip('openpyxl')

from fastapi.testclient import TestClient  # noqa: E402

from apoyo import esperar_trabajo  # noqa: E402
from igea_dgs.web.app import create_app  # noqa: E402

T0 = datetime(2026, 7, 1)


def _xlsx(hojas: dict[str, list[list]]) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nombre, filas in hojas.items():
        h = wb.create_sheet(nombre)
        for f in filas:
            h.append(f)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


MEDIDORES = {'h': [['codigo alimentador', 'Medidor'], ['A1', 'M1'], ['A1', 'M2'], ['A2', 'M3']]}
CABECERA = {
    'M1': [['Local Time', 'kVAR tot', 'kW tot', 'PF lag mean']] +
          [[T0 + timedelta(minutes=15 * i), 10.0, 100.0 + i, 95.0] for i in range(8)],
    'M2': [['Local Time', 'kW tot mean']] + [[T0, 7.0]],
}
SUMINISTROS = {'s': [['Suministro', 'Suministro Act', 'SED', 'RADIAL'], [11, 9011, 'E1', 'A1'],
                     [12, 9012, '', 'A2']]}
CLIENTES = {'resumen': [['x'], ['Nis', 'EA', 'ERI', 'Pot'], [11, 10.0, 2.0, 5.0], [9012, 1.0, 1.0, 1.0],
                        [777, 1.0, 1.0, 1.0]]}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as c:
        yield c


def _wid(client):
    return client.post('/api/workspaces').json()['id']


def _subir(client, wid, tipo, hojas, nombre='libro.xlsx'):
    r = client.post(f'/api/workspaces/{wid}/demanda/{tipo}', files=[('files', (nombre, _xlsx(hojas)))])
    assert r.status_code == 200, r.text
    return r.json()


def test_medidores_por_alimentador(client):
    """004:RF-22 / RF-23 — el alimentador da sus medidores; uno que no está, vacío."""
    wid = _wid(client)
    _subir(client, wid, 'medidores', MEDIDORES)
    r = client.get(f'/api/workspaces/{wid}/demanda/medidores', params={'alimentador': 'a1'}).json()
    assert r == {'alimentador': 'a1', 'medidores': ['M1', 'M2'], 'encontrado': True}
    r = client.get(f'/api/workspaces/{wid}/demanda/medidores', params={'alimentador': 'ZZ'}).json()
    assert r['encontrado'] is False and r['medidores'] == []


def test_sin_libro_es_error_de_usuario(client):
    """004:RF-23 — sin libro de medidores, se dice cuál falta."""
    wid = _wid(client)
    r = client.get(f'/api/workspaces/{wid}/demanda/medidores', params={'alimentador': 'A1'})
    assert r.status_code == 400 and 'medidor por alimentador' in r.json()['detail']


def test_maxima_de_cabecera_es_un_trabajo(client):
    """004:RF-27 a RF-29 — trabajo del carril engine; un resultado por medidor."""
    wid = _wid(client)
    r = client.post(f'/api/workspaces/{wid}/demanda/cabecera',
                    files=[('files', ('SISTEMA A.xlsx', _xlsx({'M1': CABECERA['M1']}))),
                           ('files', ('SISTEMA B.xlsx', _xlsx({'M2': CABECERA['M2']})))])
    assert r.status_code == 200
    assert r.json()['demanda']['cabecera']['libros'] == ['SISTEMA A.xlsx', 'SISTEMA B.xlsx']
    job = client.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json={'medidores': [
        {'alimentador': 'A1', 'medidor': 'M1'}, {'alimentador': 'A1', 'medidor': 'M2'},
        {'alimentador': 'A1', 'medidor': 'NO'}]})
    assert job.status_code == 202 and job.json()['lane'] == 'engine'
    estado = esperar_trabajo(client, job.json())
    assert estado['status'] == 'done', estado
    res = estado['result']['resultados']
    assert [(x['medidor'], x['kw']) for x in res] == [('M1', 107.0), ('M2', 7.0), ('NO', None)]
    assert res[0]['fecha'] == (T0 + timedelta(minutes=105)).isoformat(sep=' ')
    assert res[0]['fp'] == pytest.approx(0.95) and res[0]['kvar'] == 10.0
    assert 'no está' in res[2]['error']


def test_cabecera_por_ruta_de_carpeta(client, tmp_path):
    """004:RF-39 — en local, la cabecera se indica como carpeta del servidor."""
    carpeta = tmp_path / 'cabecera'
    carpeta.mkdir()
    (carpeta / 'SISTEMA A.xlsx').write_bytes(_xlsx(CABECERA))
    (carpeta / 'notas.txt').write_text('no es un libro')
    wid = _wid(client)
    r = client.post(f'/api/workspaces/{wid}/demanda/cabecera/path', json={'path': str(carpeta)})
    assert r.status_code == 200, r.text
    assert r.json()['demanda']['cabecera']['libros'] == ['SISTEMA A.xlsx']
    assert 'path' not in r.json()['demanda']['cabecera']
    r = client.post(f'/api/workspaces/{wid}/demanda/suministros/path', json={'path': str(carpeta)})
    assert r.status_code == 400, 'solo la cabecera admite carpeta'


def test_rutas_cerradas_si_escucha_en_red(tmp_path, monkeypatch):
    """004:RF-39 — la ruta del servidor solo en local (como 001:RF-15)."""
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web', host='0.0.0.0')) as c:
        wid = _wid(c)
        r = c.post(f'/api/workspaces/{wid}/demanda/cabecera/path', json={'path': str(tmp_path)})
    assert r.status_code == 403


def test_cruce_de_clientes(client):
    """004:RF-35 a RF-37 — por código actual o anterior; los demás aparte con su motivo."""
    wid = _wid(client)
    _subir(client, wid, 'suministros', SUMINISTROS)
    _subir(client, wid, 'clientes', CLIENTES, 'ci.xlsb.xlsx')
    r = client.post(f'/api/workspaces/{wid}/demanda/clientes/cruzar')
    assert r.status_code == 200, r.text
    body = r.json()
    assert [(c['codigo'], c['cruzado_por'], c['sed']) for c in body['cruzados']] == [('11', 'anterior', 'E1')]
    assert {c['codigo'] for c in body['no_cruzados']} == {'9012', '777'}
    assert body['totales'] == {'clientes': 3, 'cruzados': 1, 'no_cruzados': 2,
                               'por_actual': 0, 'por_anterior': 1}


def test_excel_de_lo_mostrado(client):
    """004:RF-38 — el Excel se arma con lo que se manda, en tres hojas."""
    wid = _wid(client)
    r = client.post(f'/api/workspaces/{wid}/demanda/excel', json={
        'cabecera': [{'alimentador': 'A1', 'medidor': 'M1', 'kw': 1.0}],
        'clientes': [{'codigo': '11', 'sed': 'E1'}], 'no_cruzados': []})
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ['Cabecera', 'Clientes', 'No cruzados']
    assert wb['Cabecera']['B2'].value == 'M1'


def test_libros_se_conservan_y_se_quitan(client):
    """004:RF-39 — el libro queda en el espacio hasta quitarlo; un tipo desconocido es 422."""
    wid = _wid(client)
    _subir(client, wid, 'medidores', MEDIDORES)
    assert client.get(f'/api/workspaces/{wid}').json()['demanda']['medidores']['name'] == 'libro.xlsx'
    assert client.delete(f'/api/workspaces/{wid}/demanda/medidores').json()['demanda'] == {}
    r = client.post(f'/api/workspaces/{wid}/demanda/otra', files=[('files', ('x.xlsx', b'x'))])
    assert r.status_code == 422
