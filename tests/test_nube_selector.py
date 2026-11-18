"""El selector de ficheros de la nube (spec 109, T18; 109:RF-1, 109:RF-3 y aclaración de 109:RF-2).

El navegador recibe solo el token de acceso transitorio, de alcance de leer; nunca el de refresco ni el secreto.
"""
from __future__ import annotations

import pytest

from nube_simulada import CONFIG_PRUEBA, montar_web_nube, sin_sockets  # noqa: F401

pytestmark = pytest.mark.usefixtures('sin_sockets')
SECRETO = 'GOCSPX-secreto-del-selector-109'
CONFIG = {'google': {**CONFIG_PRUEBA['google'], 'secreto': SECRETO, 'clave_api': 'AIza-clave-publica-109',
                     'id_aplicacion': '123456789'},
          'microsoft': CONFIG_PRUEBA['microsoft']}


@pytest.mark.parametrize('proveedor', ['google', 'microsoft'])
def test_el_token_del_selector_nunca_lleva_el_refresco_ni_el_secreto(tmp_path, proveedor):
    """109:RF-2 — solo el token de acceso, con no-store; ni refresh_token, ni el de refresco del cofre, ni el secreto."""
    from convertersmartgrid.adaptadores import nube_cofre

    with montar_web_nube(tmp_path, config=CONFIG) as web:
        wid = web.espacio()
        web.conectar(wid, proveedor, publicar=True)
        r = web.nube.post(f'/api/workspaces/{wid}/nube/{proveedor}/selector/token')
        assert r.status_code == 200, r.text
        assert r.headers['cache-control'] == 'no-store'
        datos = r.json()
        assert datos['token_acceso'] in web.sim.acceso and 0 < datos['caduca_en_s'] <= 3600
        refresco = nube_cofre.leer(wid, proveedor, raiz=tmp_path / 'cofre').refresco
        for prohibido in ('refresh_token', 'refresco', 'secreto', 'client_secret', refresco, SECRETO,
                          *web.sim.refresco):
            assert prohibido not in r.text, prohibido
        if proveedor == 'google':
            assert datos['clave_api'] == 'AIza-clave-publica-109' and datos['id_aplicacion'] == '123456789'
            assert 'drive.file' in datos['alcance']
        else:
            assert datos['alcance'].split() == ['Files.Read'], 'el selector no lleva el permiso de escritura'


def test_el_token_del_selector_solo_desde_el_navegador_y_con_la_cuenta_conectada(tmp_path):
    """109:RF-2, 109:RF-15 — sin cuenta conectada no hay token; con el token de un programa, tampoco."""
    with montar_web_nube(tmp_path, config=CONFIG) as web:
        wid = web.espacio()
        r = web.nube.post(f'/api/workspaces/{wid}/nube/google/selector/token')
        assert r.status_code >= 400 and 'conéctela' in r.json()['detail']
        web.conectar(wid, 'google')
        r = web.nube.post(f'/api/workspaces/{wid}/nube/google/selector/token', headers={'X-CSG-Token': 'x'})
        assert r.status_code == 403


@pytest.mark.parametrize('proveedor', ['google', 'microsoft'])
@pytest.mark.parametrize('modo', ['ficheros', 'carpeta'])
def test_la_pagina_del_selector_no_lleva_ni_guarda_el_token(tmp_path, proveedor, modo):
    """109:RF-1, 109:RF-3 — página propia con su CSP y nonce; sin token dentro y sin almacenamiento del navegador."""
    with montar_web_nube(tmp_path, config=CONFIG) as web:
        wid = web.espacio()
        web.conectar(wid, proveedor)
        r = web.nube.get(f'/nube/selector/{proveedor}', params={'espacio': wid, 'modo': modo})
        assert r.status_code == 200 and r.headers['content-type'].startswith('text/html')
        csp = r.headers['content-security-policy']
        assert "default-src 'none'" in csp and "'nonce-" in csp and 'unsafe-eval' not in csp
        assert r.headers['cache-control'] == 'no-store' and r.headers['referrer-policy'] == 'no-referrer'
        for prohibido in ('localStorage', 'sessionStorage', 'indexedDB', 'document.cookie', SECRETO,
                          *web.sim.acceso, *web.sim.refresco):
            assert prohibido not in r.text, prohibido
        assert 'postMessage' in r.text and 'location.origin' in r.text
        assert f'/selector/token' in r.text


def test_la_pagina_del_selector_de_otro_espacio_o_proveedor_no_existe(tmp_path):
    """109:RF-3 — un espacio inexistente o un proveedor desconocido no dan página."""
    with montar_web_nube(tmp_path, config=CONFIG) as web:
        assert web.nube.get('/nube/selector/google', params={'espacio': 'noexiste'}).status_code == 404
        wid = web.espacio()
        assert web.nube.get('/nube/selector/dropbox', params={'espacio': wid}).status_code == 404


# --------------------------------------------------------------------------- lo que pide la 110
