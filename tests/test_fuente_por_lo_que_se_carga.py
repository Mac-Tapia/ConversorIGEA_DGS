"""Spec 059: la fuente es la del fichero que se carga, nunca una por defecto.

El 2026-11-01 la web abrió un espacio vacío como «Tres TXT de CYMDIST» cuando el operador
trabajaba con el VNR-GIS de Electro Oriente. Estas pruebas fijan que ningún espacio nace con
fuente, que la fuente sale de lo cargado y que cada fichero va a su casilla por su contenido.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

pytest.importorskip('fastapi')

from fastapi.testclient import TestClient

from convertersmartgrid.identify import (
    CARGA, EQUIPOS, FUENTE_MDB, FUENTE_TXT, FUENTE_VNR, RED, fuente_de,
)

RED_TXT = '[NODE]\nFORMAT_NODE=NodeID,X,Y\nN1,0,0\n[SECTION]\nFORMAT_SECTION=SectionID\n'
CARGA_TXT = '[CUSTOMER LOADS]\nFORMAT_CUSTOMERLOADS=SectionID\nS1\n'
EQUIPOS_TXT = '[CONDUCTOR]\nFORMAT_CONDUCTOR=ID\nC1\n'


def _access(path: Path) -> Path:
    # La cabecera de una base Jet: 4 bytes y «Standard Jet DB»; el resto no importa aquí.
    path.write_bytes(b'\x00\x01\x00\x00Standard Jet DB\x00' + b'\x00' * 64)
    return path


def _zip_vnr(path: Path) -> Path:
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('tramos.geojson', '{"type": "FeatureCollection", "features": []}')
    return path


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from convertersmartgrid.web.app import create_app

    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'no-front'))
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as value:
        yield value


def _nuevo(client) -> dict:
    r = client.post('/api/workspaces')
    assert r.status_code == 201, r.text
    return r.json()


def test_el_fichero_dice_su_fuente(tmp_path):
    """059:RF-3: TXT por sus tablas, Access por su cabecera, VNR-GIS por su formato."""
    (tmp_path / 'a.txt').write_text(RED_TXT, encoding='utf-8')
    (tmp_path / 'b.dat').write_text(CARGA_TXT, encoding='utf-8')
    (tmp_path / 'c').write_text(EQUIPOS_TXT, encoding='utf-8')
    assert fuente_de(tmp_path / 'a.txt').fuente == FUENTE_TXT
    assert fuente_de(tmp_path / 'a.txt').tipo == RED
    assert fuente_de(tmp_path / 'b.dat').tipo == CARGA
    assert fuente_de(tmp_path / 'c').tipo == EQUIPOS
    # Una base Access con extensión de texto sigue siendo Access: manda el contenido.
    assert fuente_de(_access(tmp_path / 'base.txt')).fuente == FUENTE_MDB
    assert fuente_de(_zip_vnr(tmp_path / 'vnr.zip')).fuente == FUENTE_VNR
    # Un .txt que no es de CYMDIST no pasa por VNR-GIS por su extensión.
    (tmp_path / 'notas.txt').write_text('hola\n', encoding='utf-8')
    desconocido = fuente_de(tmp_path / 'notas.txt')
    assert desconocido.fuente == '' and 'notas.txt' in desconocido.motivo


def test_espacio_nuevo_sin_fuente(client):
    """059:RF-1: sin nada cargado no hay fuente, y lo pendiente pide la fuente sin suponer una."""
    ws = _nuevo(client)
    assert ws['options']['input_mode'] is None
    assert len(ws['missing_inputs']) == 1
    pendiente = ws['missing_inputs'][0]
    assert 'TXT' in pendiente and 'Access' in pendiente and 'VNR-GIS' in pendiente


def test_al_abrir_la_fuente_sale_de_las_entradas(tmp_path):
    """059:RF-2: guardado como «txt» con solo un paquete VNR-GIS abre como VNR-GIS; sin
    entradas, sin fuente."""
    from convertersmartgrid.web.workspace import Workspace

    paquete = _zip_vnr(tmp_path / 'p.zip')
    root = tmp_path / 'esp'
    root.mkdir()
    (root / 'workspace.json').write_text(json.dumps({
        'id': 'esp', 'options': {'input_mode': 'txt'},
        'inputs': {'vnr_package': {'path': str(paquete), 'name': 'p.zip'}},
    }), encoding='utf-8')
    assert Workspace.load(root).options['input_mode'] == 'vnr'
    (root / 'workspace.json').write_text(json.dumps({
        'id': 'esp', 'options': {'input_mode': 'txt'}, 'inputs': {},
    }), encoding='utf-8')
    assert Workspace.load(root).options['input_mode'] is None


def test_zona_comun_asigna_por_contenido(client):
    """059:RF-3: los tres TXT van a sus casillas sin importar el nombre, y la fuente queda TXT."""
    wid = _nuevo(client)['id']
    files = [('files', (n, t.encode('utf-8'), 'text/plain')) for n, t in (
        ('uno.txt', EQUIPOS_TXT), ('dos.txt', RED_TXT), ('tres.txt', CARGA_TXT))]
    r = client.post(f'/api/workspaces/{wid}/inputs-auto', files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert {a['slot'] for a in body['assigned']} == {'red', 'loads', 'equipment'}
    assert body['workspace']['options']['input_mode'] == 'txt'


def test_la_zona_txt_no_mezcla_fuentes(client, tmp_path):
    """059:RF-4: en la zona de los TXT, una base Access no se asigna: va en su propia entrada."""
    wid = _nuevo(client)['id']
    base = _access(tmp_path / 'red.mdb').read_bytes()
    files = [('files', ('red.txt', RED_TXT.encode('utf-8'), 'text/plain')),
             ('files', ('red.mdb', base, 'application/octet-stream'))]
    body = client.post(f'/api/workspaces/{wid}/inputs-auto', files=files).json()
    assert [a['slot'] for a in body['assigned']] == ['red']
    assert 'Base Access' in body['unassigned'][0]['reason']
    assert body['workspace']['options']['input_mode'] == 'txt'


def test_casilla_vnr_fija_la_fuente(client, tmp_path):
    """059:RF-3: un paquete en la casilla de VNR-GIS deja la fuente en VNR-GIS."""
    wid = _nuevo(client)['id']
    paquete = _zip_vnr(tmp_path / 'ELOR.zip')
    r = client.post(f'/api/workspaces/{wid}/inputs/vnr_package/path', json={'path': str(paquete)})
    assert r.status_code == 200, r.text
    assert r.json()['workspace']['options']['input_mode'] == 'vnr'


def test_casilla_rechaza_otra_fuente(client, tmp_path):
    """059:RF-3: una base Access en la casilla RED se rechaza: cada casilla, su fuente."""
    wid = _nuevo(client)['id']
    base = _access(tmp_path / 'b.mdb').read_bytes()
    r = client.post(f'/api/workspaces/{wid}/inputs/red',
                    files={'file': ('red.txt', base, 'application/octet-stream')})
    assert r.status_code == 400
    assert 'base Access' in r.json()['detail']


def test_sin_fuente_no_se_carga(client):
    """059:RF-7: pedir la carga sin fuente dice que falta cargarla, no «modo desconocido»."""
    wid = _nuevo(client)['id']
    r = client.post(f'/api/workspaces/{wid}/load')
    assert r.status_code == 400
    detalle = r.json()['detail']
    assert 'fuente' in detalle and 'desconocido' not in detalle


def test_la_web_no_marca_fuente_y_recupera_el_espacio():
    """059:RF-5 y 059:RF-6: el modo admite «sin fuente» y la clave anterior del navegador se migra.

    Las tres entradas siguen separadas (InputsPanel); sin fuente ninguna aparece marcada porque
    cada botón se marca solo si su modo es el del espacio. La web se prueba en el navegador real.
    """
    raiz = Path(__file__).resolve().parents[1] / 'frontend' / 'src'
    # El tipo sale del contrato generado de la API (065), no de una declaración a mano en types.ts.
    assert 'input_mode: ("txt" | "mdb" | "vnr") | null;' in (raiz / 'api' / 'esquema.ts').read_text(encoding='utf-8')
    boot = (raiz / 'useWorkspace.ts').read_text(encoding='utf-8')
    assert 'STORAGE_KEY_ANTERIOR' in boot and 'removeItem(STORAGE_KEY_ANTERIOR)' in boot


def test_la_copia_sql_no_es_un_paquete_de_capas(tmp_path):
    """059:RF-8: la copia de SQL Server (cabecera MTF «TAPE», sin extensión) da su empresa por
    ConfigBD.config y, sin él, ningún error."""
    from convertersmartgrid.web.source_scope import inspect_package_scope

    copia = tmp_path / 'ELOR25_V2'
    copia.write_bytes(b'TAPE' + b'\x00' * 64)
    scope = inspect_package_scope(copia)
    assert scope.companies == () and not scope.ambiguous
    (tmp_path / 'ConfigBD.config').write_text(
        '<Configuracion><valores><CodEmpresa>XYZ</CodEmpresa><nombreBD>XYZ_VNR</nombreBD>'
        '</valores></Configuracion>', encoding='utf-8')
    scope = inspect_package_scope(copia)
    assert scope.selected_company == 'XYZ' and scope.selected_period == 'XYZ_VNR'
