"""Las salidas del VAD y del PIT se descargan por la ruta de ficheros de la web (108:RF-26, 107:RF-1).

El VAD escribe en ``vad/`` y el PIT en ``expedientes_pit/``, en la raíz del espacio, y sus paneles nombran cada salida
con la ruta desde esa raíz; la ruta de ficheros solo miraba «salida/» y daba 404. Lo vio el recorrido en navegador real
del VAD (108 T30, frontend/test/e2e/f06_vad_linea.e2e.mjs). Lo demás de la raíz sigue sin servirse.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convertersmartgrid.presentacion.web import services


@pytest.fixture
def web(tmp_path, monkeypatch):
    from convertersmartgrid.presentacion.web.app import create_app

    for nombre, valor in (('CSG_ASISTENTE_DATA', tmp_path / 'asistente'), ('CSG_TWIN_DATA', tmp_path / 'gemelo'),
                          ('CSG_WEB_FRONTEND', tmp_path / 'sin_front'), ('CSG_ML_GPU_LOCK', tmp_path / 'gpu.lock')):
        monkeypatch.setenv(nombre, str(valor))
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (None, None))
    app = create_app(tmp_path / 'web')
    with TestClient(app) as cliente:
        wid = cliente.post('/api/workspaces').json()['id']
        yield cliente, wid, Path(app.state.store.get(wid).root)


def _escribe(raiz: Path, rel: str, contenido: bytes) -> None:
    ruta = raiz / rel
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)


@pytest.mark.parametrize('rel', [
    'vad/estudio-g1-2041-2045/informe_definitivo/01_Informe_de_los_Resultados_Relevantes.docx',
    'vad/estudio-g1-2041-2045/tablas_resultados.xlsx',
    'expedientes_pit/AD01/diagnostico_de_trabajo.json',
])
def test_108_rf26_107_rf1_las_salidas_del_vad_y_del_pit_se_descargan(web, rel):
    cliente, wid, raiz = web
    _escribe(raiz, rel, b'contenido de la salida')
    r = cliente.get(f'/api/workspaces/{wid}/files/{rel}', params={'download': '1'})
    assert r.status_code == 200, f'{rel}: {r.status_code} {r.text[:120]}'
    assert r.content == b'contenido de la salida'
    assert Path(rel).name in r.headers.get('content-disposition', '')


def test_108_rf26_lo_demas_de_la_raiz_no_se_sirve_ni_se_sale_de_su_carpeta(web):
    cliente, wid, raiz = web
    _escribe(raiz, 'entradas/libro_de_la_empresa.xlsx', b'entrada del operador')
    _escribe(raiz, 'secreto.txt', b'fuera')
    for rel in ('entradas/libro_de_la_empresa.xlsx', 'secreto.txt', 'vad/../secreto.txt', 'vad/%2e%2e/secreto.txt',
                'expedientes_pit/../entradas/libro_de_la_empresa.xlsx'):
        r = cliente.get(f'/api/workspaces/{wid}/files/{rel}')
        assert r.status_code in (400, 404), f'{rel} no debería servirse: {r.status_code}'
        assert r.content not in (b'entrada del operador', b'fuera')


def test_108_rf26_la_salida_de_siempre_sigue_igual(web):
    """Lo de «salida/» se sigue sirviendo primero: un fichero con la misma ruta en «salida/» gana al de la raíz."""
    cliente, wid, raiz = web
    _escribe(raiz, 'salida/vad/x.txt', b'de salida')
    _escribe(raiz, 'vad/x.txt', b'de la raiz')
    r = cliente.get(f'/api/workspaces/{wid}/files/vad/x.txt')
    assert r.status_code == 200 and r.content == b'de salida'
