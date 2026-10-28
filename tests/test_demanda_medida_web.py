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


def test_suministros_por_carpeta_descubre_el_vigente(client, tmp_path):
    """004:RF-58/RF-61 — API acepta carpeta y publica la selección universal."""
    carpeta = tmp_path / 'entregas-comerciales'
    carpeta.mkdir()
    (carpeta / 'entrega-inicial.xlsx').write_bytes(_xlsx({'datos': [
        ['Suministro Act', 'SED'], ['1', 'E1'],
    ]}))
    vigente = carpeta / 'nombre-libre.xlsx'
    vigente.write_bytes(_xlsx({'control': [
        ['NIS [act]', 'Subestacion'], ['1', 'E1'], ['2', 'E2'],
    ]}))
    (carpeta / 'notas.xlsx').write_bytes(_xlsx({'hoja': [['sin contrato']]}))
    wid = _wid(client)

    respuesta = client.post(
        f'/api/workspaces/{wid}/demanda/suministros/path', json={'path': str(carpeta)})

    assert respuesta.status_code == 200, respuesta.text
    meta = respuesta.json()['demanda']['suministros']
    assert meta['source_kind'] == 'folder'
    assert meta['seleccion'] == vigente.name
    assert meta['libros'] == ['entrega-inicial.xlsx', 'nombre-libre.xlsx']



def test_suministros_libro_explicito_se_conserva(client, tmp_path):
    """004:RF-60 — un libro indicado por el operador se usa tal cual, aunque a su lado
    haya otro más completo."""
    (tmp_path / 'mas-completo.xlsx').write_bytes(_xlsx({'datos': [
        ['Suministro Act', 'SED'], ['1', 'E1'], ['2', 'E2'], ['3', 'E3'],
    ]}))
    elegido = tmp_path / 'del-operador.xlsx'
    elegido.write_bytes(_xlsx({'datos': [['Suministro Act', 'SED'], ['1', 'E1']]}))
    wid = _wid(client)

    respuesta = client.post(
        f'/api/workspaces/{wid}/demanda/suministros/path', json={'path': str(elegido)})

    assert respuesta.status_code == 200, respuesta.text
    meta = respuesta.json()['demanda']['suministros']
    assert meta['source_kind'] == 'file' and meta['seleccion'] == elegido.name

def test_suministros_admite_varios_archivos_subidos(client):
    """004:RF-59/RF-61 — múltiples candidatos no bloquean: se elige el más completo."""
    wid = _wid(client)
    respuesta = client.post(f'/api/workspaces/{wid}/demanda/suministros', files=[
        ('files', ('inicial.xlsx', _xlsx({'datos': [
            ['Suministro Act', 'SED'], ['1', 'E1'],
        ]}))),
        ('files', ('vigente.xlsx', _xlsx({'datos': [
            ['Suministro Act', 'SED'], ['1', 'E1'], ['2', 'E2'],
        ]}))),
    ])

    assert respuesta.status_code == 200, respuesta.text
    meta = respuesta.json()['demanda']['suministros']
    assert meta['source_kind'] == 'folder'
    assert meta['seleccion'] == 'vigente.xlsx'


def test_suministros_subidos_con_libros_de_clientes_avisa_en_el_hueco(client):
    """004:RF-63 — desde la interfaz: los libros de clientes subidos en «Suministros» no son
    candidatos y el hueco los nombra."""
    clientes = {'Resumen': [['SUMINISTRO', 'EA_TOTAL', 'ERI_TOTAL', 'POT_MAX'], ['9011', 1.0, 1.0, 1.0]],
                'detalle': [['SUMINISTRO', 'SED'], ['9011', 'E1'], ['9012', 'E2']]}
    wid = _wid(client)
    respuesta = client.post(f'/api/workspaces/{wid}/demanda/suministros', files=[
        ('files', ('0926clientesImportantes.xlsx', _xlsx(clientes))),
        ('files', ('0926 Clientes_spl.xlsx', _xlsx({'datos': [['Suministro Act', 'SED'], ['1', 'E1']]}))),
    ])
    assert respuesta.status_code == 200, respuesta.text
    meta = respuesta.json()['demanda']['suministros']
    assert meta['seleccion'] == '0926 Clientes_spl.xlsx'
    assert meta['libros'] == ['0926 Clientes_spl.xlsx']
    assert any('0926clientesImportantes.xlsx' in a and 'Clientes importantes' in a for a in meta['avisos'])

    # 004:RF-64 — solo libros de clientes: no se rechaza; el hueco queda sin libro elegido,
    # con el aviso, y el cruce lo trata como si faltaran los suministros.
    wid = _wid(client)
    solo = client.post(f'/api/workspaces/{wid}/demanda/suministros', files=[
        ('files', ('0526clientesImportantes.xlsx', _xlsx(clientes))),
        ('files', ('0626clientesImportantes.xlsx', _xlsx(clientes))),
    ])
    assert solo.status_code == 200, solo.text
    meta = solo.json()['demanda']['suministros']
    assert meta['seleccion'] is None and meta['libros'] == []
    assert any('Clientes importantes' in a for a in meta['avisos'])
    assert any('factor de escala' in a for a in meta['avisos'])
    _subir(client, wid, 'clientes', clientes, 'ci.xlsx')
    cruce = client.post(f'/api/workspaces/{wid}/demanda/clientes/cruzar', json={})
    assert cruce.status_code == 400 and 'Ningún libro de suministros' in cruce.json()['detail']


def test_hueco_de_suministros_anterior_a_rf64_se_pone_al_dia_en_el_cruce(client):
    """004:RF-64 — un hueco guardado antes de la RF-64 conserva como elegido un libro de
    clientes (usuario, 2026-10-23: la carpeta 4.-clientesimportantes subida en «Suministros»
    dejó «Cruzar clientes» activo y cada pulsación tardaba 32 s en fallar sin aviso en el
    hueco). El primer cruce que lo descubre deja el hueco sin elección y con su aviso."""
    clientes = {'Resumen': [['SUMINISTRO', 'EA_TOTAL', 'ERI_TOTAL', 'POT_MAX'], ['9011', 1.0, 1.0, 1.0]],
                'detalle': [['SUMINISTRO', 'SED'], ['9011', 'E1'], ['9012', 'E2']]}
    wid = _wid(client)
    _subir(client, wid, 'suministros', clientes, '0926clientesImportantes.xlsx')
    _subir(client, wid, 'clientes', clientes, 'ci.xlsx')
    ws = client.app.state.store.get(wid)
    with ws.lock:
        meta = ws.demanda['suministros']
        meta.update(seleccion='0926clientesImportantes.xlsx', libros=['0926clientesImportantes.xlsx'],
                    avisos=[])
        ws.save()

    cruce = client.post(f'/api/workspaces/{wid}/demanda/clientes/cruzar', json={})

    assert cruce.status_code == 400
    meta = client.get(f'/api/workspaces/{wid}').json()['demanda']['suministros']
    assert meta['seleccion'] is None and meta['libros'] == []
    assert any('Clientes importantes' in a for a in meta['avisos'])
    assert any('factor de escala' in a for a in meta['avisos'])


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
    # 025:RF-4: también el año de su carpeta (aquí ninguna), nunca la ruta absoluta.
    assert all(set(x) == {'nombre', 'anio', 'mes', 'origen_mes', 'activo', 'avisos'}
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


# ---------------------------------------------------------------- spec 021: central térmica
def _libros_con_central(client, wid):
    """A1 con una central en su troncal: CG (generación), CL (llegada) y CS (salida) en el
    libro como «alimentadores» que no son de la red, igual que CTBarra en Electro Dunas."""
    medidores = {'h': [['codigo alimentador', 'Medidor'], ['A1', 'M1'], ['A2', 'M3'],
                       ['CTB', 'CG'], ['CTSET', 'CL'], ['CTCARGA', 'CS']]}
    filas = {k: [['Local Time', 'kW tot', 'kVAR tot']] for k in ('M1', 'CG', 'CL', 'CS')}
    for i in range(12):
        t = T0 + timedelta(minutes=15 * i)
        arriba, abajo, g = 800.0 + i, 5000.0 + 100 * i, 0.0 if i % 3 == 0 else 6000.0
        llegada = g - abajo
        filas['M1'].append([t, arriba - llegada, 10.0])
        filas['CG'].append([t, g, -5.0])
        filas['CL'].append([t, llegada, -3.0])
        filas['CS'].append([t, abajo, 8.0])
    _subir(client, wid, 'medidores', medidores)
    _subir(client, wid, 'cabecera', filas)


def test_medidores_que_no_son_de_la_red(client):
    """021:RF-26 — se ofrecen los medidores cuyo alimentador no es de la red, sin mirar su
    nombre: A1 y A2 son de la red (los del proyecto), CTB, CTSET y CTCARGA no."""
    wid = _wid(client)
    _libros_con_central(client, wid)
    r = client.get(f'/api/workspaces/{wid}/demanda/medidores-externos', params={'red': ['A1', 'A2']})
    assert r.status_code == 200, r.text
    assert [m['medidor'] for m in r.json()['medidores']] == ['CG', 'CL', 'CS']


def test_perfil_propone_la_central(client, tmp_path, monkeypatch):
    """021:RF-27 — la central que guarda el perfil local se propone ya rellena."""
    from igea_dgs.perfil_empresa import VARIABLE_RUTA

    perfil = tmp_path / 'perfil.json'
    perfil.write_text(json.dumps({'centrales_termicas': {
        'A1': {'generacion': 'CG', 'llegada': 'CL', 'salida': 'CS'}}}), encoding='utf-8')
    monkeypatch.setenv(VARIABLE_RUTA, str(perfil))
    wid = _wid(client)
    _libros_con_central(client, wid)
    r = client.get(f'/api/workspaces/{wid}/demanda/medidores-externos', params={'red': ['A1']}).json()
    assert r['centrales_perfil'] == {'A1': {'generacion': 'CG', 'llegada': 'CL', 'salida': 'CS', 'nodo': ''}}
    assert r['aviso_perfil'] is None


def test_maxima_con_central_de_la_ultima_busqueda(client):
    """021:RF-25, 021:RF-33, 021:RF-34 — con los tres medidores de la central buscados junto a la
    cabecera, la máxima es la de la demanda (aguas arriba + aguas abajo), con cada zona."""
    wid = _wid(client)
    _libros_con_central(client, wid)
    estado = _buscar(client, wid, medidores=('M1', 'CG', 'CL', 'CS'))
    r = client.get(f'/api/workspaces/{wid}/demanda/cabecera/{estado["id"]}/central', params={
        'alimentador': 'A1', 'cabecera': 'M1', 'generacion': 'CG', 'llegada': 'CL', 'salida': 'CS'})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['error'] is None and d['fecha'] == '2026-07-01 02:45:00'
    assert d['demanda_kw'] == pytest.approx(811.0 + 6100.0)
    assert (d['arriba_kw'], d['abajo_kw'], d['generacion_kw']) == (811.0, 6100.0, 6000.0)
    # La de cabecera, con la central parada: el último registro con g = 0 (i = 9).
    assert d['maxima_cabecera']['fecha'] == '2026-07-01 02:15:00'


def test_maxima_con_central_sin_su_curva_es_404(client):
    """021:RF-25 — sin buscar los medidores de la central, se pide buscarlos."""
    wid = _wid(client)
    _libros_con_central(client, wid)
    estado = _buscar(client, wid, medidores=('M1',))
    r = client.get(f'/api/workspaces/{wid}/demanda/cabecera/{estado["id"]}/central', params={
        'alimentador': 'A1', 'cabecera': 'M1', 'generacion': 'CG', 'llegada': 'CL', 'salida': 'CS'})
    assert r.status_code == 404 and 'CG' in r.json()['detail']


def test_curva_de_la_demanda_con_central(client):
    """021:RF-47, 021:RF-48 — la curva de la demanda calculada, con la forma de la de un
    medidor y la máxima de demanda (el objetivo) marcada; por tramo también."""
    wid = _wid(client)
    _libros_con_central(client, wid)
    estado = _buscar(client, wid, medidores=('M1', 'CG', 'CL', 'CS'))
    params = {'alimentador': 'A1', 'cabecera': 'M1', 'generacion': 'CG', 'llegada': 'CL',
              'salida': 'CS'}
    url = f'/api/workspaces/{wid}/demanda/cabecera/{estado["id"]}/central/curva'
    r = client.get(url, params=params)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['medidor'] == 'Demanda A1' and d['total'] == 12
    assert d['maxima'] == {'fecha': '2026-07-01T02:45:00', 'kw': pytest.approx(6911.0)}
    assert d['puntos'][0][1] == pytest.approx(800.0 + 5000.0)
    tramo = client.get(url, params={**params, 'desde': '2026-07-01T01:00:00',
                                    'hasta': '2026-07-01T02:00:00'}).json()
    assert tramo['total'] == 5


def test_maxima_con_mes_e_instante(client):
    """013:RF-11, 021:RF-50, 021:RF-51 — la búsqueda con un instante da el registro de esa fecha
    y hora en cada medidor, y la central lo usa también."""
    wid = _wid(client)
    _libros_con_central(client, wid)
    job = client.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json={
        'medidores': [{'alimentador': 'A1', 'medidor': m} for m in ('M1', 'CG', 'CL', 'CS')],
        'instante': '2026-07-01T01:00:00'})
    estado = esperar_trabajo(client, job.json())
    assert estado['status'] == 'done', estado
    assert estado['result']['instante'] == '2026-07-01 01:00:00'
    assert {r['fecha'] for r in estado['result']['resultados']} == {'2026-07-01 01:00:00'}
    d = client.get(f'/api/workspaces/{wid}/demanda/cabecera/{estado["id"]}/central', params={
        'alimentador': 'A1', 'cabecera': 'M1', 'generacion': 'CG', 'llegada': 'CL',
        'salida': 'CS'}).json()
    assert d['fecha'] == '2026-07-01 01:00:00' and d['abajo_kw'] == 5400.0
    mal = client.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json={
        'medidores': [{'alimentador': 'A1', 'medidor': 'M1'}], 'periodo': '2026-13'})
    assert mal.status_code == 422


# --------------------------------------------------------------- 022:RF-37 a RF-46
def _libros_por_barra(client, wid, monkeypatch, kv_alta=220, pico_alta=None, escala_alta=1.0,
                      hueco_m3=None):
    """SET X con dos transformadores (B-X1T1 y B-X1T2) y una central en su barra (CT_X), con
    A1 y A2; SET Y sin medidor de barra, con B1. La barra da su máxima en el registro 3 y
    los alimentadores la suya en otros. B-X6T1 es la de alta: de 220 kV no cuenta; de 60 kV
    con su punta en ``pico_alta`` da el instante a toda la SET X (022:RF-84)."""
    from igea_dgs.estructura import estructura_de_dict
    from igea_dgs.web import services

    e = estructura_de_dict({'zonales': [{'nombre': 'Z', 'sets': [
        {'codigo': 'SET X', 'nombre': 'Equis', 'siglas': ['X'], 'alimentadores': ['A1', 'A2', 'A3']},
        {'codigo': 'SET Y', 'nombre': 'Ye', 'alimentadores': ['B1']}]}]})
    monkeypatch.setattr(services, 'estructura_del_espacio', lambda _ws: e)
    monkeypatch.setattr(services, '_kv_alimentadores', lambda _ws: {})
    medidores = {'h': [['codigo alimentador', 'Medidor', 'Nivel Tension', 'siglas'],
                       ['A1', 'M1', 10, 'X'], ['A2', 'M3', 10, 'X'], ['B1', 'M4', 10, 'Y'],
                       ['A3', 'M5', 10, 'X'],
                       ['Barra', 'B-X1T1', 10, 'X'], ['Barra', 'B-X1T2', 10, 'X'],
                       ['Barra', 'B-X6T1', kv_alta, 'X'], ['Barra CT', 'CT_X', 10, 'X']]}
    filas = {k: [['Local Time', 'kW tot', 'kVAR tot']]
             for k in ('M1', 'M3', 'M4', 'M5', 'B-X1T1', 'B-X1T2', 'B-X6T1', 'CT_X')}
    for i in range(8):
        t = T0 + timedelta(minutes=15 * i)
        pico = 500.0 if i == 3 else 0.0
        filas['M1'].append([t, 100.0 + 10 * i, 5.0])          # su máxima, el registro 7
        if i != hueco_m3:
            filas['M3'].append([t, 300.0 - 10 * i, 5.0])      # la suya, el 0
        filas['M4'].append([t, 50.0 + i, 1.0])
        if i != 3:
            filas['M5'].append([t, 20.0, 1.0])     # sin el registro de la barra
        filas['B-X1T1'].append([t, 200.0 + pico, 20.0])
        filas['B-X1T2'].append([t, 150.0 + i, 15.0])
        filas['B-X6T1'].append([t, (9999.0 if i == pico_alta else 1000.0) * escala_alta, 1.0])
        filas['CT_X'].append([t, 40.0 + i, -2.0])
    _subir(client, wid, 'medidores', medidores)
    _subir(client, wid, 'cabecera', filas)


def test_maxima_por_barra_y_sus_alimentadores_en_esa_fecha(client, monkeypatch):
    """022:RF-37, 022:RF-39, 022:RF-40, 022:RF-41, 022:RF-41c, 022:RF-42, 022:RF-43, 022:RF-44 — la
    máxima de la barra de SET X es la de la suma de sus dos transformadores (registro 3); A1
    y A2 se buscan en esa fecha y hora, no en su máxima; B1, sin medidor de barra, en la
    suya; el de 220 kV no cuenta; la central de la barra, con su medida en ese registro."""
    wid = _wid(client)
    _libros_por_barra(client, wid, monkeypatch)
    job = client.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json={
        'medidores': [{'alimentador': a, 'medidor': m}
                      for a, m in (('A1', 'M1'), ('A2', 'M3'), ('B1', 'M4'), ('A3', 'M5'))],
        'por_barra': True})
    estado = esperar_trabajo(client, job.json())
    assert estado['status'] == 'done', estado
    res = estado['result']
    t3 = (T0 + timedelta(minutes=45)).isoformat(sep=' ')
    [b] = res['barras']
    assert b['clave'] == 'SET X 10 kV' and b['medidores'] == ['B-X1T1', 'B-X1T2']
    assert b['fecha'] == t3 and b['kw'] == pytest.approx(700.0 + 153.0)
    assert b['centrales'] == [{'medidor': 'CT_X', 'kw': 43.0, 'kvar': -2.0}]
    fechas = {r['medidor']: r['fecha'] for r in res['resultados']}
    assert fechas['M1'] == fechas['M3'] == t3
    assert fechas['M4'] == (T0 + timedelta(minutes=15 * 7)).isoformat(sep=' ')
    kw = {r['medidor']: r['kw'] for r in res['resultados']}
    assert kw['M1'] == pytest.approx(130.0) and kw['M3'] == pytest.approx(270.0)
    m5 = next(r for r in res['resultados'] if r['medidor'] == 'M5')
    assert m5['error'] and 'sin registro' in m5['error'], 'sin el registro de la barra, se dice'


def test_central_en_un_tramo_no_va_a_la_barra(client, monkeypatch):
    """022:RF-88 — la web lista CT_X con su SET y los alimentadores de esa SET; dicha en el
    tramo de A1, no va a la barra y se mide con A1 en el instante de la de 60 kV."""
    wid = _wid(client)
    _libros_por_barra(client, wid, monkeypatch, kv_alta=60, pico_alta=5)
    r = client.get(f'/api/workspaces/{wid}/demanda/centrales')
    assert r.status_code == 200, r.text
    [c] = r.json()['centrales']
    assert c['medidor'] == 'CT_X' and c['set'] == 'SET X' and c['alimentadores'] == ['A1', 'A2', 'A3']
    job = client.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json={
        'medidores': [{'alimentador': a, 'medidor': m} for a, m in (('A1', 'M1'), ('A2', 'M3'))],
        'por_barra': True, 'centrales_tramo': {'CT_X': 'A1'}})
    estado = esperar_trabajo(client, job.json())
    assert estado['status'] == 'done', estado
    res = estado['result']
    t5 = (T0 + timedelta(minutes=75)).isoformat(sep=' ')
    assert all(b['centrales'] == [] for b in res['barras']), 'en el tramo, no en la barra'
    ct = next(x for x in res['resultados'] if x['medidor'] == 'CT_X')
    assert ct['alimentador'] == 'Central A1' and ct['fecha'] == t5 and ct['kw'] == pytest.approx(45.0)
    assert any('CT_X' in a and '022:RF-88' in a for a in res['avisos'])
    # Una central en el tramo de un alimentador que no es del sistema pedido no entra.
    job = client.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json={
        'medidores': [{'alimentador': 'B1', 'medidor': 'M4'}],
        'por_barra': True, 'centrales_tramo': {'CT_X': 'A1'}})
    res = esperar_trabajo(client, job.json())['result']
    assert not any(x['medidor'] == 'CT_X' for x in res['resultados'])
    assert all('A1' not in b['alimentadores'] for b in res['barras'])


def test_maxima_de_la_barra_de_60_kv_da_el_instante_a_toda_la_set(client, monkeypatch):
    """022:RF-84, 022:RF-86 — la máxima de B-X6T1 (60 kV) en el registro 5 fija el instante:
    la barra de 10 kV de SET X se lee en el 5 (su suma ahí, no su máxima del 3), con su
    central en ese registro, y A1 y A2 se calibran en el 5; B1, de una SET sin 60 kV, con
    su propia máxima."""
    wid = _wid(client)
    _libros_por_barra(client, wid, monkeypatch, kv_alta=60, pico_alta=5)
    job = client.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json={
        'medidores': [{'alimentador': a, 'medidor': m}
                      for a, m in (('A1', 'M1'), ('A2', 'M3'), ('B1', 'M4'))],
        'por_barra': True})
    estado = esperar_trabajo(client, job.json())
    assert estado['status'] == 'done', estado
    res = estado['result']
    t5 = (T0 + timedelta(minutes=75)).isoformat(sep=' ')
    por = {b['clave']: b for b in res['barras']}
    alta = por['SET X 60 kV']
    assert alta['alta'] and alta['fecha'] == t5 and alta['kw'] == pytest.approx(9999.0)
    media = por['SET X 10 kV']
    assert media['de_alta'] == 'SET X 60 kV' and media['fecha'] == t5
    assert media['kw'] == pytest.approx(200.0 + 155.0), 'la suma en el registro de la de 60 kV'
    assert media['alimentadores'] == ['A1', 'A2']
    assert media['centrales'] == [{'medidor': 'CT_X', 'kw': 45.0, 'kvar': -2.0}]
    fechas = {r['medidor']: r['fecha'] for r in res['resultados']}
    assert fechas['M1'] == fechas['M3'] == t5
    assert fechas['M4'] == (T0 + timedelta(minutes=15 * 7)).isoformat(sep=' ')
    kw = {r['medidor']: r['kw'] for r in res['resultados']}
    assert kw['M1'] == pytest.approx(150.0) and kw['M3'] == pytest.approx(250.0)
    assert not any('022:RF-89' in a for a in res['avisos']), '9 999 kW > 310 kW de su media'


def test_instante_de_60_kv_con_registro_en_todos_sus_alimentadores(client, monkeypatch):
    """022:RF-91 — la punta de B-X6T1 (registro 5) no está en M3 (A2): el instante es la
    mayor de la barra entre los registros que tienen A1 y A2, y se dice; A2 se calibra."""
    wid = _wid(client)
    _libros_por_barra(client, wid, monkeypatch, kv_alta=60, pico_alta=5, hueco_m3=5)
    job = client.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json={
        'medidores': [{'alimentador': a, 'medidor': m} for a, m in (('A1', 'M1'), ('A2', 'M3'))],
        'por_barra': True})
    estado = esperar_trabajo(client, job.json())
    assert estado['status'] == 'done', estado
    res = estado['result']
    t5 = (T0 + timedelta(minutes=75)).isoformat(sep=' ')
    alta = next(b for b in res['barras'] if b['alta'])
    assert alta['fecha'] != t5 and alta['kw'] == pytest.approx(1000.0)
    assert any('022:RF-91' in a for a in res['avisos'])
    m3 = next(r for r in res['resultados'] if r['medidor'] == 'M3')
    assert not m3['error'] and m3['fecha'] == alta['fecha']


def test_barra_de_60_kv_menor_que_su_media_se_avisa(client, monkeypatch):
    """022:RF-89 — una barra de 60 kV que marca menos que sus barras de media (otra unidad,
    como CHNB6T1 en MW) se avisa, y su instante se usa igual."""
    wid = _wid(client)
    _libros_por_barra(client, wid, monkeypatch, kv_alta=60, pico_alta=5, escala_alta=0.001)
    job = client.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json={
        'medidores': [{'alimentador': 'A1', 'medidor': 'M1'}], 'por_barra': True})
    estado = esperar_trabajo(client, job.json())
    assert estado['status'] == 'done', estado
    res = estado['result']
    t5 = (T0 + timedelta(minutes=75)).isoformat(sep=' ')
    assert next(b for b in res['barras'] if b['alta'])['fecha'] == t5
    assert any('SET X 60 kV' in a and '022:RF-89' in a for a in res['avisos'])
