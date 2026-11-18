"""El selector único por entrada (spec 109, T19; 109:RF-21 a RF-24): un fichero de la nube elegido en cualquier entrada
de la web se guarda como copia fija y vuelve al navegador para entrar por la subida propia de esa entrada. Sin red: el
proveedor simulado de ``nube_simulada``.
"""
from __future__ import annotations

import hashlib

import pytest

from nube_simulada import montar_web_nube, sin_sockets  # noqa: F401

pytest.importorskip('fastapi')

pytestmark = pytest.mark.usefixtures('sin_sockets')

CONTENIDO = b'periodo;kw\n2026-08;120\n'


def _importar_entrada(web, wid, ids, entrada='estudios'):
    r = web.nube.post(f'/api/workspaces/{wid}/nube/importar', json={'proveedor': 'google', 'ids': ids,
                                                                     'entrada': entrada})
    assert r.status_code == 202, r.text
    return web.esperar(r.json())


def test_la_copia_de_una_entrada_vuelve_con_sus_bytes_y_no_se_asigna(tmp_path):
    """109:RF-22, RF-3 — importar para una entrada guarda la copia fija, no toca las casillas ni los libros y la
    devuelve tal cual, con su huella, para que entre por la subida propia de esa entrada."""
    with montar_web_nube(tmp_path) as web:
        wid = web.espacio()
        web.conectar(wid, 'google')
        fid = web.sim.crear('google', 'medicion agosto.csv', CONTENIDO)
        hecho = _importar_entrada(web, wid, [fid])
        assert hecho['status'] == 'done', hecho
        copia = hecho['result']['copias'][0]
        assert copia['sha256'] == hashlib.sha256(CONTENIDO).hexdigest() and copia['nombre'] == 'medicion agosto.csv'
        assert hecho['result']['destino'] == {'entrada': 'estudios'}
        entradas = web.real.get(f'/api/workspaces/{wid}').json().get('inputs') or {}
        assert not any((e or {}).get('origin') == 'nube' for e in entradas.values()), 'una entrada no asigna casillas'
        r = web.nube.get(f"/api/workspaces/{wid}/nube/copias/{copia['sha256']}")
        assert r.status_code == 200, r.text
        assert r.content == CONTENIDO
        assert 'medicion' in r.headers['content-disposition']
        # 109:RF-7: la copia queda vinculada a su entrada, para avisar de una revisión nueva.
        vinculos = web.nube.get(f'/api/workspaces/{wid}/nube/vinculos').json()['vinculos']
        assert [v['destino'] for v in vinculos] == [{'entrada': 'estudios'}]


def test_una_entrada_admite_varios_ficheros_de_la_nube(tmp_path):
    """109:RF-22 — una entrada múltiple (los antecedentes de un estudio) trae cada fichero con su copia."""
    with montar_web_nube(tmp_path) as web:
        wid = web.espacio()
        web.conectar(wid, 'google')
        ids = [web.sim.crear('google', f'anexo_{i}.pdf', b'%PDF-1.4 ' + bytes([i])) for i in range(3)]
        hecho = _importar_entrada(web, wid, ids)
        assert hecho['status'] == 'done', hecho
        assert sorted(c['nombre'] for c in hecho['result']['copias']) == ['anexo_0.pdf', 'anexo_1.pdf', 'anexo_2.pdf']


@pytest.mark.parametrize('cuerpo', [{'casilla': 'red', 'entrada': 'estudios'}, {'libro': 'clientes', 'entrada': 'x'},
                                    {'entrada': ''}, {'entrada': '../fuera'}])
def test_la_entrada_va_sola_y_con_un_nombre_simple(tmp_path, cuerpo):
    """109:RF-22 — el destino es una casilla, un libro o una entrada, uno solo; el nombre de la entrada no es una ruta."""
    with montar_web_nube(tmp_path) as web:
        wid = web.espacio()
        web.conectar(wid, 'google')
        fid = web.sim.crear('google', 'a.csv', CONTENIDO)
        r = web.nube.post(f'/api/workspaces/{wid}/nube/importar', json={'proveedor': 'google', 'ids': [fid], **cuerpo})
        assert r.status_code == 422, r.text


@pytest.mark.parametrize('huella', ['no-es-una-huella', 'a' * 64, '..%2F..%2Fworkspace.json'])
def test_solo_se_devuelve_una_copia_que_existe_en_su_carpeta(tmp_path, huella):
    """109:RF-22 — la descarga de una copia solo sirve copias guardadas: una huella mal formada o ajena da 404."""
    with montar_web_nube(tmp_path) as web:
        wid = web.espacio()
        r = web.nube.get(f'/api/workspaces/{wid}/nube/copias/{huella}')
        assert r.status_code == 404, r.text


def test_una_salida_suelta_se_publica_sola(tmp_path):
    """109:RF-24, RF-9 — publicar una salida (un informe) mete en el ZIP cerrado solo ese fichero, por su ruta exacta en
    la salida; la selección por alimentador sigue igual."""
    import types
    import uuid
    import zipfile

    from convertersmartgrid.presentacion.web.operaciones_lentas import preparar_zip, retirar_zip

    salida = tmp_path / 'salida'
    for rel in ('informes/estudio.docx', 'informes/otro.docx', 'F1.dgs', 'F1_resumen.json', 'F10.dgs'):
        (salida / rel).parent.mkdir(parents=True, exist_ok=True)
        (salida / rel).write_bytes(rel.encode())

    def zip_de(seleccion):
        ctx = types.SimpleNamespace(job=types.SimpleNamespace(id=uuid.uuid4().hex), check_cancel=lambda: None,
                                    progress=lambda *_a: None)
        try:
            hecho = preparar_zip('ws-prueba', salida, seleccion, ctx)
        except ValueError as exc:     # «No hay ficheros de salida…»: la selección no casó con ninguno
            return [], str(exc)
        try:
            with zipfile.ZipFile(ctx.job._archivo_zip) as z:
                return sorted(z.namelist()), hecho['nombre']
        finally:
            retirar_zip(ctx.job._archivo_zip, ctx.job.id, 'ws-prueba')

    assert zip_de(('informes/estudio.docx',)) == (['informes/estudio.docx'], 'convertersmartgrid_estudio.docx.zip')
    assert zip_de(('F1',))[0] == ['F1.dgs', 'F1_resumen.json']


def test_el_campo_unico_filtra_por_tipo_y_guarda_la_salida():
    """109:RF-21, 109:RF-23, 109:RF-24 — la lógica del campo único (sus orígenes y el filtro de tipo con su aviso) y la de
    «Guardar en…» se prueban en node (frontend/test/selectorUnico.test.mjs); aquí se corren para que la suite de Python
    las cubra también, como test_frontend_rutas con las del frontend."""
    import shutil
    import subprocess
    from pathlib import Path

    frontend = Path(__file__).resolve().parents[1] / 'frontend'
    if shutil.which('node') is None or not (frontend / 'node_modules').is_dir():
        pytest.skip('Falta Node.js o `npm ci` en frontend: la prueba del campo único no se puede ejecutar.')
    r = subprocess.run(['node', '--test', 'test/selectorUnico.test.mjs'], cwd=frontend, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=300)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    assert 'fail 0' in r.stdout and 'pass 0' not in r.stdout, r.stdout[-1000:]


def test_un_programa_no_descarga_las_copias_de_la_nube(tmp_path):
    """109:RF-15, RF-22 — solo la sesión del navegador trae una copia; con el token de la web, 403."""
    from convertersmartgrid.dominio.sesion_web import CABECERA_TOKEN

    with montar_web_nube(tmp_path) as web:
        wid = web.espacio()
        web.conectar(wid, 'google')
        fid = web.sim.crear('google', 'a.csv', CONTENIDO)
        copia = _importar_entrada(web, wid, [fid])['result']['copias'][0]
        r = web.nube.get(f"/api/workspaces/{wid}/nube/copias/{copia['sha256']}", headers={CABECERA_TOKEN: 'x'})
        assert r.status_code == 403, r.text
