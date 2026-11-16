"""Spec 110, T9: create_app sirve las rutas del correo con las cuentas de la 109 (cableado pactado con el integrador)."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from correo_simulado import sin_red  # noqa: F401
from test_correo_web import ORIGEN, RUTAS_CORREO, _rutas_correo


@pytest.fixture(autouse=True)
def _sin_red(sin_red, monkeypatch, tmp_path):  # noqa: F811
    # Ni el config/nube.json ni el cofre de la máquina: los de esta prueba, vacíos (109:RF-18, RF-19).
    monkeypatch.setenv('CSG_NUBE_CONFIG', str(tmp_path / 'sin_config' / 'nube.json'))
    yield


def test_create_app_sirve_el_correo_y_sin_cuentas_de_la_109_no_envia(tmp_path, monkeypatch):
    """110:RF-1, RF-5, RF-7 — create_app monta las rutas; sin cuentas conectadas el envío se rechaza sin abrir la red."""
    from apoyo import esperar_trabajo
    from test_informe_docx import _config, _factibilidad

    from convertersmartgrid.informe_docx import escribir_informe_factibilidad
    from convertersmartgrid.web.app import create_app

    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    app = create_app(tmp_path / 'web')
    assert _rutas_correo(app) == RUTAS_CORREO
    with TestClient(app) as c:
        wid = c.post('/api/workspaces').json()['id']
        ws = app.state.store.get(wid)
        Path(ws.out_dir).mkdir(parents=True, exist_ok=True)
        destino = Path(ws.out_dir) / 'informe_factibilidad_AL02_X.docx'
        escribir_informe_factibilidad(_config(tmp_path), destino, _factibilidad(tmp_path))
        v = c.post(f'/api/workspaces/{wid}/correo/vista-previa', headers=ORIGEN,
                   json={'informe': destino.name, 'cuenta': 'operador@empresa-a.test', 'proveedor': 'google',
                         'para': ['cliente@otra.test'], 'adjuntar': ['docx']})
        assert v.status_code == 200, v.text
        r = c.post(f'/api/workspaces/{wid}/correo/{v.json()["borrador"]}/confirmar', headers=ORIGEN,
                   json={'firma': v.json()['firma']})
        assert r.status_code == 200, r.text
        assert r.json()['trabajo']['lane'] == 'correo'
        assert esperar_trabajo(c, r.json()['trabajo'])['status'] == 'done'
        recibo = c.get(f'/api/workspaces/{wid}/correo/envios/{r.json()["clave"]}').json()
        assert recibo['estado'] == 'rechazado' and 'conect' in recibo['motivo']
        hist = c.get(f'/api/workspaces/{wid}/correo/historial', params={'informe': destino.name}).json()
        assert [e['clave'] for e in hist['envios']] == [r.json()['clave']]
        assert 'cliente@otra.test' not in r.json()['trabajo']['title']


    assert 'Sin cuenta conectada: configure config/nube.json' in recibo['motivo']


def test_create_app_usa_las_cuentas_de_la_109(tmp_path, monkeypatch):
    """110:RF-2, RF-10 — el envío pide el token y el permiso de lectura a los adaptadores de la 109, no a ``SinCuentas``."""
    import importlib.util

    assert importlib.util.find_spec('convertersmartgrid.correo.de_la_109'), 'falta convertersmartgrid.correo.de_la_109'
    from convertersmartgrid.correo import de_la_109
    from convertersmartgrid.web import correo_api
    from convertersmartgrid.web.app import create_app

    pedidos = []
    monkeypatch.setattr(correo_api, 'registrar_rutas_correo',
                        lambda app, **kw: pedidos.append(kw))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    create_app(tmp_path / 'web')
    assert len(pedidos) == 1
    ws = type('Ws', (), {'id': 'w1'})()
    assert isinstance(pedidos[0]['credenciales_de'](ws), de_la_109.CredencialesDeLa109)
    assert isinstance(pedidos[0]['compartidor_de'](ws), de_la_109.CompartidorDeLa109)
    assert pedidos[0]['credenciales_de'](ws).wid == 'w1'


def test_la_nube_y_el_correo_comparten_una_sola_cuentas(tmp_path, monkeypatch):
    """110:RF-2 y 109:RF-1 — una cuenta por proveedor: la web monta la nube y el correo con la MISMA ``Cuentas`` (Google =
    Drive + Gmail; Microsoft = OneDrive + Outlook), y no dos con su caché de tokens y sus ``state`` por separado."""
    from convertersmartgrid.adaptadores.nube.cuentas import Cuentas
    from convertersmartgrid.web import correo_api, nube_api
    from convertersmartgrid.web.app import create_app

    correo, nube = [], []
    monkeypatch.setattr(correo_api, 'registrar_rutas_correo', lambda app, **kw: correo.append(kw))
    monkeypatch.setattr(nube_api, 'registrar_rutas_nube', lambda app, **kw: nube.append(kw))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    create_app(tmp_path / 'web')
    assert len(correo) == 1 and len(nube) == 1
    ws = type('Ws', (), {'id': 'w1'})()
    cuentas = nube[0].get('cuentas')
    assert isinstance(cuentas, Cuentas), 'la nube debe recibir la Cuentas de la web, no crear la suya'
    assert correo[0]['credenciales_de'](ws).cuentas is cuentas, 'el correo usa otra Cuentas que la nube'
    assert correo[0]['compartidor_de'](ws).cuentas is cuentas, 'el compartir del correo usa otra Cuentas que la nube'
