"""El cableado de la nube en la web real (spec 109, T8; 109:RF-4, RF-19): parche del integrador sobre ``web/app.py`` y
``web/api_contract.py``. Sin red: ``create_app`` sin ``config/nube.json`` y el proveedor simulado donde hace falta.
"""
from __future__ import annotations

import pytest

from nube_simulada import NubeSimulada, montar_web_nube, sin_sockets  # noqa: F401

pytest.importorskip('fastapi')
from fastapi.testclient import TestClient  # noqa: E402

pytestmark = pytest.mark.usefixtures('sin_sockets')


def test_la_web_real_monta_las_rutas_de_la_nube(tmp_path, monkeypatch):
    """109:RF-19 — la web real responde a la nube; sin ``config/nube.json`` dice que falta registrarla y no falla."""
    from convertersmartgrid.web.app import create_app

    monkeypatch.setenv('CSG_NUBE_CONFIG', str(tmp_path / 'no_existe' / 'nube.json'))
    with TestClient(create_app(tmp_path / 'web')) as web:
        rutas = {getattr(r, 'path', '') for r in web.app.routes}
        for ruta in ('/api/nube/proveedores', '/api/workspaces/{wid}/nube/cuentas', '/api/workspaces/{wid}/nube/importar',
                     '/nube/retorno'):
            assert ruta in rutas, f'falta {ruta} en la web real'
        r = web.get('/api/nube/proveedores')
        assert r.status_code == 200, r.text
        assert all(not p['se_puede_conectar'] and 'config/nube.json' in p['motivo'] for p in r.json()['proveedores'])
        # El retorno va fuera de /api/: sin código vuelve a la web, nunca al index.html de la SPA ni con un 404.
        retorno = web.get('/nube/retorno', follow_redirects=False)
        assert retorno.status_code == 303 and retorno.headers['location'] == '/?nube=cancelada'


def test_una_casilla_de_la_nube_cabe_en_el_contrato_del_espacio(tmp_path):
    """109:RF-4 — con una entrada de origen «nube», ``GET /api/workspaces/{wid}`` responde con su contrato (sin 500)."""
    from convertersmartgrid.web.api_contract import DemandaRespuesta, EntradaRespuesta

    assert 'nube' in EntradaRespuesta.model_fields['origin'].annotation.__args__
    assert 'nube' in DemandaRespuesta.model_fields['origin'].annotation.__args__
    with montar_web_nube(tmp_path) as web:
        wid = web.espacio()
        web.conectar(wid, 'google')
        fid = web.sim.crear('google', 'RED.txt', b'contenido de prueba')
        r = web.nube.post(f'/api/workspaces/{wid}/nube/importar',
                          json={'proveedor': 'google', 'ids': [fid], 'casilla': 'red'})
        assert r.status_code == 202, r.text
        assert web.esperar(r.json())['status'] in ('done', 'failed')
        espacio = web.real.get(f'/api/workspaces/{wid}')
        assert espacio.status_code == 200, espacio.text
        entrada = espacio.json()['inputs'].get('red')
        assert entrada is None or entrada['origin'] == 'nube'


@pytest.mark.parametrize('ruta', ['/nube/importar', '/nube/publicar', '/nube/compartir', '/api/nube/proveedores',
                                  '/nube/google/conectar', '/api/workspaces/w1/nube/vinculos/v/aceptar'])
def test_el_asistente_no_pide_la_nube_ni_con_el_plan_confirmado(ruta):
    """109:RF-15 — `autorizar_peticion` corta cualquier ruta de la nube aunque el plan esté listo y confirmado."""
    from convertersmartgrid.asistente.equipo import GobiernoEquipo, PermisoDenegado
    from convertersmartgrid.asistente.tareas import TAREAS

    gobierno = object.__new__(GobiernoEquipo)
    gobierno.rol, gobierno.tarea, gobierno.listo, gobierno.confirmado, gobierno.lectura = (
        'operador', next(iter(TAREAS)), True, True, False)
    with pytest.raises(PermisoDenegado, match='nube'):
        gobierno.autorizar_peticion('POST', ruta, {'json': {}})
