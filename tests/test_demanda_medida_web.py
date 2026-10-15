"""Spec 004, demanda medida: la API (libros por subida o ruta, medidores, cabecera, cruce, Excel)."""
from __future__ import annotations

import io
import json
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


def _perfil_clientes_mensuales(tmp_path, monkeypatch):
    """Perfil mínimo real: el resultado mensual depende del perfil, no del nombre codificado."""
    from igea_dgs.perfil_empresa import VARIABLE_RUTA

    perfil = tmp_path / 'perfil-mensual.json'
    perfil.write_text(json.dumps({
        'patron_libro_clientes': (
            r'(?i)^(?P<mes>0[1-9]|1[0-2])(?P<anio>\d{2})'
            r'clientesImportantes\.(?:xlsb|xlsx)$'
        ),
    }), encoding='utf-8')
    monkeypatch.setenv(VARIABLE_RUTA, str(perfil))


def _indexar_clientes(client, wid):
    respuesta = client.post(f'/api/workspaces/{wid}/demanda/clientes/indexar')
    assert respuesta.status_code == 202, respuesta.text
    assert respuesta.json()['lane'] == 'engine'
    estado = esperar_trabajo(client, respuesta.json())
    assert estado['status'] == 'done', estado
    return client.get(f'/api/workspaces/{wid}').json()


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
    assert r.status_code == 400, 'solo cabecera y clientes admiten carpeta'


def test_clientes_por_carpeta_publica_catalogo_mensual_sin_rutas(client, tmp_path, monkeypatch):
    """013:RF-1 / 013:RF-2 — la carpeta queda elegida y todos sus libros aparecen en el catálogo."""
    _perfil_clientes_mensuales(tmp_path, monkeypatch)
    carpeta = tmp_path / '4.-clientesimportantes'
    carpeta.mkdir()
    (carpeta / '0126clientesImportantes.xlsb').write_bytes(b'el nombre evita abrirlo')
    (carpeta / '0726clientesImportantes.xlsx').write_bytes(b'el nombre evita abrirlo')
    (carpeta / 'notas.txt').write_text('ignorado', encoding='utf-8')
    wid = _wid(client)

    asignada = client.post(
        f'/api/workspaces/{wid}/demanda/clientes/path', json={'path': str(carpeta)})
    assert asignada.status_code == 200, asignada.text
    assert asignada.json()['demanda']['clientes']['name'] == carpeta.name

    estado = _indexar_clientes(client, wid)
    meta = estado['demanda']['clientes']
    assert meta['source_kind'] == 'folder'
    assert meta['libros'] == [
        '0126clientesImportantes.xlsb', '0726clientesImportantes.xlsx']
    assert [(x['nombre'], x['mes'], x['origen_mes'], x['activo']) for x in meta['catalogo']] == [
        ('0126clientesImportantes.xlsb', '2026-01', 'nombre', True),
        ('0726clientesImportantes.xlsx', '2026-07', 'nombre', True),
    ]
    assert all(set(x) == {'nombre', 'mes', 'origen_mes', 'activo', 'avisos'}
               for x in meta['catalogo'])
    assert str(carpeta) not in json.dumps(meta)


def test_clientes_subidos_admiten_varios_libros(client, tmp_path, monkeypatch):
    """013:RF-1 / 013:RF-2 — la alternativa de subida conserva todos los libros mensuales."""
    _perfil_clientes_mensuales(tmp_path, monkeypatch)
    wid = _wid(client)
    respuesta = client.post(f'/api/workspaces/{wid}/demanda/clientes', files=[
        ('files', ('0126clientesImportantes.xlsb', b'enero')),
        ('files', ('0226clientesImportantes.xlsx', b'febrero')),
    ])
    assert respuesta.status_code == 200, respuesta.text

    meta = _indexar_clientes(client, wid)['demanda']['clientes']
    assert meta['source_kind'] == 'folder'
    assert meta['libros'] == [
        '0126clientesImportantes.xlsb', '0226clientesImportantes.xlsx']
    assert [x['mes'] for x in meta['catalogo']] == ['2026-01', '2026-02']


def test_actualizar_indice_detecta_libros_agregados_y_retirados(client, tmp_path, monkeypatch):
    """013:RF-6 — reusar la carpeta detecta altas y bajas sin volver a seleccionarla."""
    _perfil_clientes_mensuales(tmp_path, monkeypatch)
    carpeta = tmp_path / 'clientes'
    carpeta.mkdir()
    enero = carpeta / '0126clientesImportantes.xlsx'
    julio = carpeta / '0726clientesImportantes.xlsx'
    enero.write_bytes(b'enero')
    wid = _wid(client)
    assert client.post(f'/api/workspaces/{wid}/demanda/clientes/path',
                       json={'path': str(carpeta)}).status_code == 200
    assert _indexar_clientes(client, wid)['demanda']['clientes']['libros'] == [enero.name]

    julio.write_bytes(b'julio')
    enero.unlink()
    meta = _indexar_clientes(client, wid)['demanda']['clientes']
    assert meta['libros'] == [julio.name]
    assert meta['catalogo'][0]['mes'] == '2026-07'


def test_carpeta_con_un_mes_puede_cruzar_y_con_varios_exige_elegir(client, tmp_path, monkeypatch):
    """013:RF-1 — una carpeta no llega accidentalmente al lector como si fuera un Excel."""
    _perfil_clientes_mensuales(tmp_path, monkeypatch)
    carpeta = tmp_path / 'clientes'
    carpeta.mkdir()
    (carpeta / '0126clientesImportantes.xlsx').write_bytes(_xlsx(CLIENTES))
    wid = _wid(client)
    _subir(client, wid, 'suministros', SUMINISTROS)
    assert client.post(f'/api/workspaces/{wid}/demanda/clientes/path',
                       json={'path': str(carpeta)}).status_code == 200
    _indexar_clientes(client, wid)
    assert client.post(f'/api/workspaces/{wid}/demanda/clientes/cruzar').status_code == 200

    (carpeta / '0226clientesImportantes.xlsx').write_bytes(_xlsx(CLIENTES))
    _indexar_clientes(client, wid)
    respuesta = client.post(f'/api/workspaces/{wid}/demanda/clientes/cruzar')
    assert respuesta.status_code == 400
    assert 'elija un mes' in respuesta.json()['detail'].lower()


def test_cruce_con_el_mes_elegido_dice_su_libro(client, tmp_path, monkeypatch):
    """013:RF-12 y RF-16 — con varios meses se cruza el libro del mes elegido y se dice cuál."""
    _perfil_clientes_mensuales(tmp_path, monkeypatch)
    carpeta = tmp_path / 'clientes'
    carpeta.mkdir()
    (carpeta / '0126clientesImportantes.xlsx').write_bytes(_xlsx(CLIENTES))
    (carpeta / '0226clientesImportantes.xlsx').write_bytes(_xlsx(CLIENTES))
    wid = _wid(client)
    _subir(client, wid, 'suministros', SUMINISTROS)
    assert client.post(f'/api/workspaces/{wid}/demanda/clientes/path',
                       json={'path': str(carpeta)}).status_code == 200
    _indexar_clientes(client, wid)
    url = f'/api/workspaces/{wid}/demanda/clientes/cruzar'

    body = client.post(url, json={'periodo': '2026-02'}).json()
    assert (body['libro'], body['mes']) == ('0226clientesImportantes.xlsx', '2026-02')
    assert body['totales']['cruzados'] == 1

    sin_libro = client.post(url, json={'periodo': '2026-03'})
    assert sin_libro.status_code == 400 and '2026-03' in sin_libro.json()['detail']
    assert client.post(url, json={'periodo': 'febrero'}).status_code == 422


def test_indice_de_clientes_rechaza_carpeta_sin_libros(client, tmp_path, monkeypatch):
    """013:RF-2 — una carpeta vacía falla explícitamente en vez de aparentar estar lista."""
    _perfil_clientes_mensuales(tmp_path, monkeypatch)
    carpeta = tmp_path / 'vacia'
    carpeta.mkdir()
    wid = _wid(client)
    assert client.post(f'/api/workspaces/{wid}/demanda/clientes/path',
                       json={'path': str(carpeta)}).status_code == 200

    respuesta = client.post(f'/api/workspaces/{wid}/demanda/clientes/indexar')
    assert respuesta.status_code == 202
    estado = esperar_trabajo(client, respuesta.json())
    assert estado['status'] == 'failed'
    assert 'No hay libros' in estado['error']


def test_indice_detecta_si_la_carpeta_cambia_durante_el_escaneo(client, tmp_path, monkeypatch):
    """013:RF-6 — una carrera no publica como vigente una instantánea que ya cambió."""
    from igea_dgs import demanda_medida as dm

    _perfil_clientes_mensuales(tmp_path, monkeypatch)
    carpeta = tmp_path / 'clientes'
    carpeta.mkdir()
    (carpeta / '0126clientesImportantes.xlsx').write_bytes(b'enero')
    real = dm.catalogar_libros_clientes

    def catalogar_y_cambiar(*args, **kwargs):
        catalogo = real(*args, **kwargs)
        (carpeta / '0226clientesImportantes.xlsx').write_bytes(b'febrero')
        return catalogo

    monkeypatch.setattr(dm, 'catalogar_libros_clientes', catalogar_y_cambiar)
    wid = _wid(client)
    assert client.post(f'/api/workspaces/{wid}/demanda/clientes/path',
                       json={'path': str(carpeta)}).status_code == 200

    meta = _indexar_clientes(client, wid)['demanda']['clientes']
    assert meta['vigente'] is False
    assert any('cambió' in aviso and 'Actualizar índice' in aviso for aviso in meta['avisos'])


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
                               'por_actual': 0, 'por_anterior': 1, 'de_otros': 0}


def test_lista_de_alimentadores(client):
    """004:RF-42 — los alimentadores del libro de medidores, sin repetir, para elegir."""
    wid = _wid(client)
    hojas = {'h': MEDIDORES['h'] + [['a 1', 'M9']]}
    _subir(client, wid, 'medidores', hojas)
    r = client.get(f'/api/workspaces/{wid}/demanda/alimentadores')
    assert r.status_code == 200 and r.json() == {'alimentadores': ['A1', 'A2']}


def test_cruce_solo_del_alimentador_de_la_maxima(client):
    """004:RF-43 — con el alimentador de la máxima, solo sus clientes; los que no están en
    suministros siguen aparte porque no se sabe de qué alimentador son."""
    wid = _wid(client)
    sumi = {'s': SUMINISTROS['s'] + [[13, 9013, 'E3', 'A2']]}
    _subir(client, wid, 'suministros', sumi)
    _subir(client, wid, 'clientes', {'resumen': CLIENTES['resumen'] + [[13, 3.0, 1.0, 2.0]]})
    url = f'/api/workspaces/{wid}/demanda/clientes/cruzar'
    body = client.post(url, json={'alimentadores': ['a-2']}).json()
    assert [c['codigo'] for c in body['cruzados']] == ['13']
    assert {c['codigo'] for c in body['no_cruzados']} == {'9012', '777'}
    assert body['alimentadores'] == ['a-2'] and body['totales']['de_otros'] == 1
    body = client.post(url, json={'alimentadores': ['A1']}).json()
    assert [c['codigo'] for c in body['cruzados']] == ['11']
    assert {c['codigo'] for c in body['no_cruzados']} == {'777'}, 'el sin SED de A2 no es de A1'
    assert len(client.post(url, json={'alimentadores': []}).json()['cruzados']) == 2


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


# =========================================================================== curva (spec 006)
def _buscar(client, wid, medidores=('M1', 'M2')):
    job = client.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json={'medidores': [
        {'alimentador': 'A1', 'medidor': m} for m in medidores]})
    estado = esperar_trabajo(client, job.json())
    assert estado['status'] == 'done', estado
    return estado


def _curva(client, wid, job_id, **params):
    return client.get(f'/api/workspaces/{wid}/demanda/cabecera/{job_id}/curva', params=params)


def test_curva_entera_del_medidor(client):
    """006:RF-31 / RF-32 — la curva del registro entero, del primer dato al último, aparte
    del resultado del trabajo, con la máxima para marcarla."""
    wid = _wid(client)
    _subir(client, wid, 'cabecera', CABECERA)
    estado = _buscar(client, wid)
    assert 'curva' not in estado['result']['resultados'][0]
    r = _curva(client, wid, estado['id'], medidor='M1')
    assert r.status_code == 200, r.text
    c = r.json()
    assert c['medidor'] == 'M1' and c['total'] == 8 and c['reducida'] is False
    assert c['inicio'] == T0.isoformat() and c['fin'] == (T0 + timedelta(minutes=105)).isoformat()
    assert c['puntos'][0] == [T0.isoformat(), 100.0, 10.0]
    assert [p[1] for p in c['puntos']] == [100.0 + i for i in range(8)]
    assert c['maxima'] == {'fecha': (T0 + timedelta(minutes=105)).isoformat(), 'kw': 107.0}
    assert c['fuera_de_curva'] == 0


def test_curva_por_tramo(client):
    """006:RF-35 — con desde y hasta, solo ese tramo; el inicio y el fin siguen siendo los
    del registro entero, para volver a «Ver todo»."""
    wid = _wid(client)
    _subir(client, wid, 'cabecera', CABECERA)
    estado = _buscar(client, wid)
    c = _curva(client, wid, estado['id'], medidor='M1', desde=(T0 + timedelta(minutes=30)).isoformat(),
               hasta=(T0 + timedelta(minutes=60)).isoformat()).json()
    assert [p[1] for p in c['puntos']] == [102.0, 103.0, 104.0] and c['total'] == 3
    assert c['inicio'] == T0.isoformat()
    r = _curva(client, wid, estado['id'], medidor='M1', desde=(T0 + timedelta(hours=1)).isoformat(),
               hasta=T0.isoformat())
    assert r.status_code == 422


def test_curva_de_cada_medidor_del_alimentador(client):
    """006:RF-38 — cada medidor del alimentador tiene su curva; uno que no está, 404."""
    wid = _wid(client)
    _subir(client, wid, 'cabecera', CABECERA)
    estado = _buscar(client, wid)
    assert _curva(client, wid, estado['id'], medidor='M2').json()['total'] == 1
    assert _curva(client, wid, estado['id'], medidor='m1').json()['medidor'] == 'M1'
    assert _curva(client, wid, estado['id'], medidor='NO').status_code == 404


def test_curva_solo_del_ultimo_trabajo(client):
    """006:RF-31 — se guarda la curva de la última búsqueda: la de una anterior ya no está."""
    wid = _wid(client)
    _subir(client, wid, 'cabecera', CABECERA)
    viejo = _buscar(client, wid)
    nuevo = _buscar(client, wid, ('M1',))
    assert _curva(client, wid, nuevo['id'], medidor='M1').status_code == 200
    r = _curva(client, wid, viejo['id'], medidor='M1')
    assert r.status_code == 404 and 'vuelva a buscar' in r.json()['detail']


def test_curva_reducida_conserva_la_maxima(client, monkeypatch):
    """006:RF-39 — por encima del tope de puntos se reduce sin perder la máxima."""
    from igea_dgs.web import services
    monkeypatch.setattr(services, 'CURVA_MAX_PUNTOS', 4)
    wid = _wid(client)
    _subir(client, wid, 'cabecera', CABECERA)
    estado = _buscar(client, wid)
    c = _curva(client, wid, estado['id'], medidor='M1').json()
    assert c['reducida'] is True and c['total'] == 8 and len(c['puntos']) <= 4
    assert max(p[1] for p in c['puntos']) == 107.0
