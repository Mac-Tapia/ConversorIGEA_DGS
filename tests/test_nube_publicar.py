"""Publicar un expediente cerrado en la nube del operador (spec 109, T10; 109:RF-9, RF-12, RF-13)."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest

from nube_simulada import montar_web_nube, sin_sockets  # noqa: F401

pytestmark = pytest.mark.usefixtures('sin_sockets')


def _salida():
    """``convertersmartgrid.adaptadores.salida.nube``, con una aserción si aún no existe (109, T10 y T11)."""
    import importlib
    import importlib.util

    for ruta in ('convertersmartgrid.adaptadores.salida', 'convertersmartgrid.adaptadores.salida.nube'):
        assert importlib.util.find_spec(ruta) is not None, f'falta el módulo {ruta} (109, T10)'
    return importlib.import_module('convertersmartgrid.adaptadores.salida.nube')


def _expediente(web, wid):
    salida = web.store.get(wid).out_dir / 'expediente_pide'
    (salida / 'anexos').mkdir(parents=True)
    (salida / 'informe_pide.docx').write_bytes(b'PK\x03\x04 informe del PIDE')
    (salida / 'anexos' / 'cuadro_obras.xlsx').write_bytes(b'PK\x03\x04 cuadro de obras')
    (salida / 'resumen.md').write_text('Resumen ejecutivo del estudio.\n', encoding='utf-8')
    return 'expediente_pide'


def _publicar(web, wid, proveedor, carpeta, nombre='Expediente PIDE 2027', salida='expediente_pide'):
    cuerpo = {'proveedor': proveedor, 'carpeta_destino': carpeta, 'nombre': nombre, 'salida': salida}
    previa = web.nube.post(f'/api/workspaces/{wid}/nube/publicar/previa', json=cuerpo)
    assert previa.status_code == 200, previa.text
    assert previa.json()['sobrescribe'] is False and previa.json()['ficheros'] == 3
    r = web.nube.post(f'/api/workspaces/{wid}/nube/publicar',
                      json={**cuerpo, 'confirmacion': previa.json()['confirmacion']})
    assert r.status_code == 202, r.text
    return web.esperar(r.json())


def _preparado(web, proveedor, **kw):
    wid = web.espacio()
    web.conectar(wid, proveedor, publicar=True)
    _expediente(web, wid)
    carpeta = web.sim.crear(proveedor, 'Expedientes', carpeta=True, **kw)
    return wid, carpeta


@pytest.mark.parametrize('proveedor', ['google', 'microsoft'])
def test_publica_el_paquete_cerrado_con_su_manifiesto_y_su_recibo(tmp_path, proveedor):
    """109:RF-9, 109:RF-12 — ZIP y manifiesto de huellas en la carpeta elegida; recibo con paquete, destino y hora."""
    with montar_web_nube(tmp_path) as web:
        wid, carpeta = _preparado(web, proveedor)
        estado = _publicar(web, wid, proveedor, carpeta)
        assert estado['status'] == 'done', estado
        recibo = estado['result']['recibo']
        subidos = {f.nombre: f for f in web.sim.hijos(carpeta)}
        assert set(subidos) == {'Expediente PIDE 2027.zip', 'Expediente PIDE 2027.manifiesto.json'}
        zip_remoto = subidos['Expediente PIDE 2027.zip'].contenido
        manifiesto = json.loads(subidos['Expediente PIDE 2027.manifiesto.json'].contenido)
        assert manifiesto['zip']['sha256'] == hashlib.sha256(zip_remoto).hexdigest() == recibo['sha256']
        with zipfile.ZipFile(io.BytesIO(zip_remoto)) as z:
            for entrada in manifiesto['entradas']:
                assert hashlib.sha256(z.read(entrada['ruta'])).hexdigest() == entrada['sha256']
        assert {e['ruta'] for e in manifiesto['entradas']} == {'informe_pide.docx', 'anexos/cuadro_obras.xlsx',
                                                              'resumen.md'}
        for campo in ('paquete', 'destino', 'hora', 'id_remoto', 'proveedor', 'clave'):
            assert recibo[campo], campo
        assert recibo['destino'] == carpeta and recibo['id_remoto'] == subidos['Expediente PIDE 2027.zip'].id
        lista = web.nube.get(f'/api/workspaces/{wid}/nube/recibos').json()['recibos']
        assert [r['clave'] for r in lista] == [recibo['clave']]


@pytest.mark.parametrize('proveedor', ['google', 'microsoft'])
def test_reintento_tras_un_corte_entre_la_subida_y_el_recibo(tmp_path, monkeypatch, proveedor):
    """109:RF-13 — la subida llegó y el recibo no: el reintento devuelve el recibo sin subir otra vez."""
    salida = _salida()

    original = salida.publicar_duradero
    fallos = []

    def corte(ruta, contenido):
        if ruta.name.startswith('publicacion-') and not fallos:
            fallos.append(ruta)
            raise OSError('corte de luz simulado al escribir el recibo')
        return original(ruta, contenido)

    monkeypatch.setattr(salida, 'publicar_duradero', corte)
    with montar_web_nube(tmp_path) as web:
        wid, carpeta = _preparado(web, proveedor)
        assert _publicar(web, wid, proveedor, carpeta)['status'] == 'failed'
        subidas = web.sim.subidas_completadas
        assert subidas == 2 and not list((web.store.get(wid).root / 'nube' / 'recibos').glob('*.json'))
        estado = _publicar(web, wid, proveedor, carpeta)
        assert estado['status'] == 'done', estado
        assert web.sim.subidas_completadas == subidas, 'el reintento volvió a subir'
        assert estado['result']['recibo']['subido_ahora'] is False
        assert len(web.sim.hijos(carpeta)) == 2
        again = _publicar(web, wid, proveedor, carpeta)
        assert again['result']['recibo']['reintento'] is True and web.sim.subidas_completadas == subidas


@pytest.mark.parametrize('proveedor', ['google', 'microsoft'])
def test_un_nombre_ya_existente_no_se_pisa(tmp_path, proveedor):
    """109:RF-9 — ya hay un «Expediente PIDE 2027.zip» distinto: no se sobrescribe ni queda recibo."""
    with montar_web_nube(tmp_path) as web:
        wid, carpeta = _preparado(web, proveedor)
        otro = web.sim.crear(proveedor, 'Expediente PIDE 2027.zip', b'el del colega', padre=carpeta)
        estado = _publicar(web, wid, proveedor, carpeta)
        assert estado['status'] == 'failed' and 'no se pisa' in estado['error']
        assert web.sim.ficheros[otro].contenido == b'el del colega' and len(web.sim.hijos(carpeta)) == 1
        assert not list((web.store.get(wid).root / 'nube' / 'recibos').glob('*.json'))


@pytest.mark.parametrize('proveedor', ['google', 'microsoft'])
def test_carpeta_de_solo_lectura_da_su_causa_y_no_deja_recibo(tmp_path, proveedor):
    """109:RF-9, 109:RF-12 — un archivo compartido de solo lectura: la causa, nada subido y ningún recibo."""
    with montar_web_nube(tmp_path) as web:
        wid, carpeta = _preparado(web, proveedor, solo_lectura=True)
        estado = _publicar(web, wid, proveedor, carpeta)
        assert estado['status'] == 'failed' and 'permiso' in estado['error']
        assert not web.sim.hijos(carpeta)
        assert not list((web.store.get(wid).root / 'nube' / 'recibos').glob('*.json'))


def test_subida_cortada_se_reanuda(tmp_path):
    """109:RF-9 — una subida cortada a mitad se reanuda desde lo que el proveedor ya tiene."""
    with montar_web_nube(tmp_path) as web:
        wid, carpeta = _preparado(web, 'google')
        web.sim.corta_subida_tras = 40
        estado = _publicar(web, wid, 'google', carpeta)
        assert estado['status'] == 'done', estado
        zip_remoto = next(f for f in web.sim.hijos(carpeta) if f.nombre.endswith('.zip')).contenido
        assert hashlib.sha256(zip_remoto).hexdigest() == estado['result']['recibo']['sha256']


def test_onedrive_sin_permiso_de_escritura_pide_volver_a_conectar(tmp_path):
    """109:RF-1, RF-9 — conectado solo para leer, publicar en OneDrive pide el permiso de escritura."""
    with montar_web_nube(tmp_path) as web:
        wid = web.espacio()
        web.conectar(wid, 'microsoft')
        _expediente(web, wid)
        carpeta = web.sim.crear('microsoft', 'Expedientes', carpeta=True)
        estado = _publicar(web, wid, 'microsoft', carpeta)
        assert estado['status'] == 'failed' and 'escritura' in estado['error'] and not web.sim.hijos(carpeta)


def test_publicar_sin_la_confirmacion_de_la_previa_se_rechaza(tmp_path):
    """109:RF-9, RF-15 — sin la confirmación de un solo uso de la previa, o repetida, no se publica."""
    with montar_web_nube(tmp_path) as web:
        wid, carpeta = _preparado(web, 'google')
        cuerpo = {'proveedor': 'google', 'carpeta_destino': carpeta, 'nombre': 'X', 'salida': 'expediente_pide'}
        r = web.nube.post(f'/api/workspaces/{wid}/nube/publicar', json={**cuerpo, 'confirmacion': 'inventada'})
        assert r.status_code == 400 and 'confirmación' in r.json()['detail']
        previa = web.nube.post(f'/api/workspaces/{wid}/nube/publicar/previa', json=cuerpo)
        assert previa.status_code == 200, previa.text
        token = previa.json()['confirmacion']
        otro = {**cuerpo, 'nombre': 'Otro nombre', 'confirmacion': token}
        assert web.nube.post(f'/api/workspaces/{wid}/nube/publicar', json=otro).status_code == 400
        assert not web.sim.hijos(carpeta)


@pytest.mark.parametrize('publicar', [False, True])
def test_las_cuentas_dicen_los_permisos_concedidos(tmp_path, publicar):
    """109:RF-1, RF-9 — `…/nube/cuentas` dice qué concedió cada cuenta: la web pide escribir solo si hace falta."""
    with montar_web_nube(tmp_path) as web:
        wid = web.espacio()
        web.conectar(wid, 'microsoft', publicar=publicar)
        r = web.nube.get(f'/api/workspaces/{wid}/nube/cuentas')
        assert r.status_code == 200, r.text
        cuenta = next(c for c in r.json()['cuentas'] if c['nombre'] == 'microsoft')
        assert 'permisos_concedidos' in cuenta, f'las cuentas no dicen sus permisos: {cuenta}'
        assert ('Files.ReadWrite' in cuenta['permisos_concedidos']) is publicar
        assert cuenta['puede_publicar'] is publicar and cuenta['puede_enviar'] is False
        google = next(c for c in r.json()['cuentas'] if c['nombre'] == 'google')
        assert google['conectada'] is False and google['permisos_concedidos'] is None
