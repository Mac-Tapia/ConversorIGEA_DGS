"""Vínculos y versiones de lo importado de la nube (spec 109, T9; 109:RF-7, RF-8, RF-17)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nube_simulada import montar_web_nube, sin_sockets  # noqa: F401
from synthetic_export import ExportSpec, write_export

pytestmark = pytest.mark.usefixtures('sin_sockets')


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _importado(web, tmp_path, proveedor='google'):
    red, _carga, _equipo = write_export(ExportSpec(feeders=2, seed=109), tmp_path / 'export')
    wid = web.espacio()
    web.conectar(wid, proveedor)
    fid = web.sim.crear(proveedor, red.name, red.read_bytes())
    r = web.nube.post(f'/api/workspaces/{wid}/nube/importar', json={'proveedor': proveedor, 'ids': [fid],
                                                                     'casilla': 'red'})
    assert web.esperar(r.json())['status'] == 'done'
    r = web.nube.get(f'/api/workspaces/{wid}/nube/vinculos')
    assert r.status_code == 200, f'falta la ruta de los vínculos (T9): {r.text}'
    vinculo = r.json()['vinculos'][0]
    return wid, fid, red, vinculo


def _versiones(web, wid) -> list[dict]:
    estado = web.esperar(web.nube.post(f'/api/workspaces/{wid}/nube/versiones').json())
    assert estado['status'] == 'done', estado
    r = web.nube.get(f'/api/workspaces/{wid}/nube/vinculos')
    assert r.status_code == 200, r.text
    return r.json()['vinculos']


@pytest.mark.parametrize('proveedor', ['google', 'microsoft'])
def test_revision_nueva_avisa_compara_y_entra_solo_con_confirmacion(tmp_path, proveedor):
    """109:RF-7, 109:RF-8 — aviso de revisión nueva, comparación con la vigente y aceptación solo confirmada."""
    with montar_web_nube(tmp_path) as web:
        wid, fid, red, vinculo = _importado(web, tmp_path, proveedor)
        assert vinculo['destino'] == {'casilla': 'red'} and vinculo['estado'] == 'al_dia'
        assert _versiones(web, wid)[0]['estado'] == 'al_dia'
        ws = web.store.get(wid)
        anterior = Path(ws.inputs['red']['path'])
        sha_anterior = _sha(anterior)
        # Lo hecho con la versión anterior (un estudio, un dataset, una calibración) apunta a su copia y su huella.
        hechos = {n: {'copia': str(anterior), 'sha256': sha_anterior} for n in ('estudio', 'dataset', 'calibracion')}
        web.sim.modificar(fid, red.read_bytes() + b'\nLINEA NUEVA DEL OPERADOR\n')
        v = _versiones(web, wid)[0]
        assert v['estado'] == 'nueva' and v['nueva']['revision'] != v['vigente']['revision']
        assert Path(web.store.get(wid).inputs['red']['path']) == anterior, 'la nueva no entra sola'
        estado = web.esperar(web.nube.post(f"/api/workspaces/{wid}/nube/vinculos/{v['id']}/traer").json())
        assert estado['status'] == 'done', estado
        comparacion = estado['result']['comparacion']
        assert comparacion['iguales'] is False and comparacion['lineas']['anadidas'] >= 1
        assert comparacion['anterior']['sha256'] == sha_anterior
        assert Path(web.store.get(wid).inputs['red']['path']) == anterior
        r = web.nube.post(f"/api/workspaces/{wid}/nube/vinculos/{v['id']}/aceptar", json={'confirmar': False})
        assert r.status_code == 400 and 'confirmación' in r.json()['detail']
        r = web.nube.post(f"/api/workspaces/{wid}/nube/vinculos/{v['id']}/aceptar", json={'confirmar': True})
        assert r.status_code == 200, r.text
        nueva = Path(web.store.get(wid).inputs['red']['path'])
        assert nueva != anterior and _sha(nueva) == comparacion['nueva']['sha256']
        for nombre, hecho in hechos.items():
            assert _sha(Path(hecho['copia'])) == hecho['sha256'], f'el {nombre} perdió su copia'
        assert r.json()['historial'][-1]['sha256'] == sha_anterior


@pytest.mark.parametrize('corte', ['salida_apagada', 'sin_conexion'])
def test_sin_conexion_dice_que_no_pudo_comprobar_y_lo_importado_sigue(tmp_path, monkeypatch, corte):
    """109:RF-17 — sin red o con la salida apagada: «no se pudo comprobar» y la copia sigue asignada e intacta."""
    with montar_web_nube(tmp_path) as web:
        wid, fid, _red, _v = _importado(web, tmp_path)
        ruta = Path(web.store.get(wid).inputs['red']['path'])
        sha = _sha(ruta)
        if corte == 'salida_apagada':
            monkeypatch.setenv('CSG_SALIDA_NUBE', '0')
        else:
            web.sim.fallar(503, veces=100)
        v = _versiones(web, wid)[0]
        assert v['estado'] == 'sin_comprobar' and 'No se pudo comprobar' in v['motivo']
        assert Path(web.store.get(wid).inputs['red']['path']) == ruta and _sha(ruta) == sha
        vinculos = json.loads((web.store.get(wid).root / 'nube' / 'vinculos.json').read_text(encoding='utf-8'))
        assert vinculos[v['id']]['vigente']['sha256'] == sha


def test_un_vinculo_que_no_existe_da_404_y_las_respuestas_tienen_su_forma(tmp_path):
    """109:RF-8 — aceptar o traer un vínculo ajeno da 404; el OpenAPI declara la forma de los vínculos."""
    with montar_web_nube(tmp_path) as web:
        wid = web.espacio()
        assert web.nube.get(f'/api/workspaces/{wid}/nube/vinculos').json() == {'vinculos': []}
        r = web.nube.post(f'/api/workspaces/{wid}/nube/vinculos/no-existe/aceptar', json={'confirmar': True})
        assert r.status_code == 404, r.text
        assert web.nube.post(f'/api/workspaces/{wid}/nube/vinculos/no-existe/traer').status_code == 404
        rutas = web.nube.get('/openapi.json').json()['paths']
        esquema = rutas['/api/workspaces/{wid}/nube/vinculos']['get']['responses']['200']['content']
        assert '$ref' in esquema['application/json']['schema']
