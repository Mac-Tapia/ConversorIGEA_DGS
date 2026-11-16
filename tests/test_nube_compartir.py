"""Compartir un expediente publicado (spec 109, T11; 109:RF-10, RF-11, RF-12, RF-20)."""
from __future__ import annotations

import io
import zipfile

import pytest

from nube_simulada import montar_web_nube, sin_sockets  # noqa: F401
from synthetic_export import ExportSpec, write_export

pytestmark = pytest.mark.usefixtures('sin_sockets')


def _office(texto: str) -> bytes:
    """Un .docx mínimo de verdad (Office Open XML), como los informes."""
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types/>')
        z.writestr('word/document.xml', f'<w:document>{texto}</w:document>')
    return b.getvalue()


def _salida():
    """``convertersmartgrid.adaptadores.salida.nube``, con una aserción si aún no existe (109, T10 y T11)."""
    import importlib
    import importlib.util

    for ruta in ('convertersmartgrid.adaptadores.salida', 'convertersmartgrid.adaptadores.salida.nube'):
        assert importlib.util.find_spec(ruta) is not None, f'falta el módulo {ruta} (109, T10)'
    return importlib.import_module('convertersmartgrid.adaptadores.salida.nube')


def _publicado(web, tmp_path, proveedor='google', crudos=False):
    wid = web.espacio()
    web.conectar(wid, proveedor, publicar=True)
    salida = web.store.get(wid).out_dir / 'expediente'
    salida.mkdir(parents=True)
    (salida / 'informe.docx').write_bytes(_office('Informe de factibilidad'))
    (salida / 'resumen.md').write_text('Resumen.\n', encoding='utf-8')
    if crudos:
        from convertersmartgrid.identify import _FIRMAS_ACCESS

        red, _c, _e = write_export(ExportSpec(feeders=2, seed=109), tmp_path / 'export')
        # Renombrados: se reconocen por el contenido, no por el nombre.
        (salida / 'anexo_1.pdf').write_bytes(red.read_bytes())
        (salida / 'tabla_resumen.xlsx').write_bytes(b'\x00\x01\x00\x00' + _FIRMAS_ACCESS[0] + b'\x00' * 200)
        vnr = io.BytesIO()
        with zipfile.ZipFile(vnr, 'w') as z:
            z.writestr('BT/tramos.shp', b's' * 64)
            z.writestr('BT/tramos.dbf', b'd' * 64)
        (salida / 'mapa_de_la_zona.docx').write_bytes(vnr.getvalue())
    carpeta = web.sim.crear(proveedor, 'Expedientes', carpeta=True)
    cuerpo = {'proveedor': proveedor, 'carpeta_destino': carpeta, 'nombre': 'Expediente', 'salida': 'expediente'}
    previa = web.nube.post(f'/api/workspaces/{wid}/nube/publicar/previa', json=cuerpo)
    assert previa.status_code == 200, previa.text
    token = previa.json()['confirmacion']
    estado = web.esperar(web.nube.post(f'/api/workspaces/{wid}/nube/publicar',
                                       json={**cuerpo, 'confirmacion': token}).json())
    assert estado['status'] == 'done', estado
    return wid, estado['result']['recibo']


def _previa(web, wid, publicacion, destinatarios, publico=False):
    r = web.nube.post(f'/api/workspaces/{wid}/nube/compartir/previa',
                      json={'publicacion': publicacion, 'destinatarios': destinatarios, 'publico': publico})
    assert r.status_code == 200, r.text
    return r.json()


def _compartir(web, wid, publicacion, destinatarios, confirmacion, **kw):
    return web.nube.post(f'/api/workspaces/{wid}/nube/compartir', json={
        'publicacion': publicacion, 'destinatarios': destinatarios, 'confirmacion': confirmacion, **kw})


@pytest.mark.parametrize('proveedor', ['google', 'microsoft'])
def test_solo_lectura_a_los_nombrados_tras_ver_quien_tendra_acceso(tmp_path, proveedor):
    """109:RF-10, RF-12 — la previa dice quién tendrá acceso; se concede solo lectura y queda un recibo por permiso."""
    with montar_web_nube(tmp_path) as web:
        wid, recibo = _publicado(web, tmp_path, proveedor)
        quienes = ['revisor@osinergmin.example', 'Ingeniera@consultora.example', 'revisor@osinergmin.example']
        previa = _previa(web, wid, recibo['clave'], quienes)
        assert [a['destinatario'] for a in previa['acceso']] == quienes[:2]
        assert {a['rol'] for a in previa['acceso']} == {'lectura'} and previa['bloqueo'] == []
        assert previa['publico'] is False and previa['aviso_publico'] is None
        r = _compartir(web, wid, recibo['clave'], quienes, previa['confirmacion'])
        assert r.status_code == 202, r.text
        estado = web.esperar(r.json())
        assert estado['status'] == 'done', estado
        permisos = web.sim.ficheros[recibo['id_remoto']].permisos
        assert len(permisos) == 2
        if proveedor == 'google':
            assert {(p['role'], p['type']) for p in permisos} == {('reader', 'user')}
        else:
            assert all(p['roles'] == ['read'] and p['requireSignIn'] is True for p in permisos)
        recibos = [x for x in web.nube.get(f'/api/workspaces/{wid}/nube/recibos').json()['recibos']
                   if x['tipo'] == 'permiso']
        assert sorted(x['destinatarios'][0] for x in recibos) == sorted(quienes[:2])
        assert all(x['id_remoto'] and x['hora'] and x['paquete'] == recibo['paquete'] for x in recibos)
        repetida = _compartir(web, wid, recibo['clave'], quienes, previa['confirmacion'])
        assert repetida.status_code == 400, 'la confirmación es de un solo uso'


def test_cualquiera_con_el_enlace_solo_con_autorizacion_expresa(tmp_path):
    """109:RF-11 — el enlace público se rechaza sin la autorización del envío; con ella, aviso y recibo."""
    with montar_web_nube(tmp_path) as web:
        wid, recibo = _publicado(web, tmp_path)
        previa = _previa(web, wid, recibo['clave'], [], publico=True)
        assert previa['aviso_publico'] and previa['acceso'][-1]['destinatario'] == 'cualquiera con el enlace'
        r = _compartir(web, wid, recibo['clave'], [], previa['confirmacion'], publico=True)
        assert r.status_code == 400 and 'autorización' in r.json()['detail']
        assert not web.sim.ficheros[recibo['id_remoto']].permisos
        previa = _previa(web, wid, recibo['clave'], [], publico=True)
        r = _compartir(web, wid, recibo['clave'], [], previa['confirmacion'], publico=True,
                       autorizo_enlace_publico=True)
        estado = web.esperar(r.json())
        assert estado['status'] == 'done' and estado['result']['permisos'][0]['enlace']
        assert web.sim.ficheros[recibo['id_remoto']].permisos[0]['type'] == 'anyone'


def test_lo_enviado_tiene_que_ser_lo_confirmado(tmp_path):
    """109:RF-10 — otra lista de destinatarios que la de la previa no se envía."""
    with montar_web_nube(tmp_path) as web:
        wid, recibo = _publicado(web, tmp_path)
        previa = _previa(web, wid, recibo['clave'], ['a@ejemplo.org'])
        r = _compartir(web, wid, recibo['clave'], ['a@ejemplo.org', 'intruso@ajeno.example'], previa['confirmacion'])
        assert r.status_code == 400 and not web.sim.ficheros[recibo['id_remoto']].permisos


@pytest.mark.parametrize('correo', ['no-es-correo', 'a@b', 'x@y.example, z@w.example'])
def test_destinatarios_que_no_son_correos_se_rechazan(tmp_path, correo):
    """109:RF-10 — cada destinatario, un correo concreto."""
    with montar_web_nube(tmp_path) as web:
        wid, recibo = _publicado(web, tmp_path)
        r = web.nube.post(f'/api/workspaces/{wid}/nube/compartir/previa',
                          json={'publicacion': recibo['clave'], 'destinatarios': [correo]})
        assert r.status_code == 400


def test_datos_crudos_renombrados_impiden_compartir_y_se_nombran(tmp_path):
    """109:RF-20 — TXT de CYMDIST, MDB y VNR renombrados dentro del expediente: se nombran y no se concede nada."""
    s = _salida()
    Rechazo, compartir, leer_paquete = s.Rechazo, s.compartir, s.leer_paquete

    with montar_web_nube(tmp_path) as web:
        wid, recibo = _publicado(web, tmp_path, crudos=True)
        previa = _previa(web, wid, recibo['clave'], ['revisor@osinergmin.example'])
        assert sorted(previa['bloqueo']) == ['anexo_1.pdf', 'mapa_de_la_zona.docx', 'tabla_resumen.xlsx']
        assert previa['confirmacion'] is None and 'informe.docx' not in previa['bloqueo']
        ws = web.store.get(wid)
        paquete = leer_paquete(ws.root / 'nube' / 'paquetes', recibo['paquete'])
        with pytest.raises(Rechazo, match='anexo_1.pdf'):
            compartir(web.cuentas.proveedor(wid, 'google'), paquete, recibo, ['revisor@osinergmin.example'],
                      ws.root / 'nube' / 'recibos', publico=False, autorizo_enlace_publico=False, wid=wid)
        assert not web.sim.ficheros[recibo['id_remoto']].permisos
