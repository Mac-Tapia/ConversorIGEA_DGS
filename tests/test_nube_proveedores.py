"""Los adaptadores de Google Drive y OneDrive sobre el proveedor simulado (spec 109, T6; 109:RF-3, RF-5, RF-6, RF-16).

La paginación se sortea con una semilla (P2: ningún tamaño fijo); ``CSG_SCALE_SEED`` repite un sorteo que falló. Los
módulos de la nube se piden con ``_nube``: si aún no existen, la prueba cae por aserción y no por
``ModuleNotFoundError``.
"""
from __future__ import annotations

import importlib
import importlib.util
import io
import json
import os
import random

import pytest

from nube_simulada import CONFIG_PRUEBA, NubeSimulada, quickxor, sin_sockets  # noqa: F401

pytestmark = pytest.mark.usefixtures('sin_sockets')
SEMILLA = int(os.environ.get('CSG_SCALE_SEED') or random.SystemRandom().randrange(1 << 30))


def _nube(modulo: str):
    """``convertersmartgrid.adaptadores.nube.<modulo>``, con una aserción que dice cuál falta (109, T6)."""
    ruta = 'convertersmartgrid.adaptadores'
    for parte in ('nube', modulo):
        ruta += '.' + parte
        assert importlib.util.find_spec(ruta) is not None, f'falta el módulo {ruta} (109, T6)'
    return importlib.import_module(ruta)


def _errores():
    return _nube('proveedor')


def _proveedor(sim, nombre, esperas=None, **kw):
    token = sim.dar_token(nombre)
    clase = _nube('google_drive').GoogleDrive if nombre == 'google' else _nube('onedrive').OneDrive
    hosts = _nube('google_drive').HOSTS if nombre == 'google' else _nube('onedrive').HOSTS
    t = _nube('http').Transporte(hosts, autorizacion=lambda _r: token, adaptador=sim,
                                 dormir=(esperas.append if esperas is not None else (lambda _s: None)))
    return clase(t, **kw)


@pytest.mark.parametrize('nombre', ['google', 'microsoft'])
def test_metadatos_con_revision_y_huella(nombre):
    """109:RF-3, RF-7 — revisión (headRevisionId o cTag), tamaño y huella del contenido."""
    sim = NubeSimulada()
    datos = random.Random(SEMILLA).randbytes(1234)
    fid = sim.crear(nombre, 'RED.txt', datos)
    p = _proveedor(sim, nombre)
    a = p.metadatos(fid)
    assert a.tamano == len(datos) and a.nombre == 'RED.txt' and a.huellas['sha256']
    sim.modificar(fid, datos + b'x')
    assert p.metadatos(fid).revision != a.revision
    if nombre == 'microsoft':
        assert a.huellas['quickxor'] == quickxor(datos)


@pytest.mark.parametrize('nombre', ['google', 'microsoft'])
def test_listado_paginado_sorteado_sin_duplicados(nombre):
    """109:RF-3 — cientos de ficheros, páginas de tamaño sorteado: aparecen todos y ninguno dos veces."""
    rng = random.Random(SEMILLA)
    total, tam = rng.randrange(120, 420), rng.randrange(7, 60)
    sim = NubeSimulada()
    carpeta = sim.crear(nombre, 'Mediciones', carpeta=True)
    creados = {sim.crear(nombre, f'libro_{i}.xlsx', b'x', padre=carpeta) for i in range(total)}
    p = _proveedor(sim, nombre, tam_pagina=tam)
    vistos, siguiente, paginas = [], None, 0
    while True:
        pagina = p.listar(carpeta, siguiente)
        vistos += [i.id for i in pagina.items]
        paginas += 1
        siguiente = pagina.siguiente
        if not siguiente:
            break
    assert sorted(vistos) == sorted(creados), f'semilla {SEMILLA}'
    assert len(vistos) == len(set(vistos)) and paginas == -(-total // tam), f'semilla {SEMILLA}'


def test_next_link_ajeno_de_onedrive_se_rechaza():
    """109:RF-16 — un @odata.nextLink a otro host no se sigue."""
    sim = NubeSimulada()
    sim.next_link_ajeno = True
    carpeta = sim.crear('microsoft', 'C', carpeta=True)
    for i in range(5):
        sim.crear('microsoft', f'{i}.txt', b'x', padre=carpeta)
    p = _proveedor(sim, 'microsoft', tam_pagina=2)
    pagina = p.listar(carpeta)
    with pytest.raises(_errores().HostNoPermitido):
        p.listar(carpeta, pagina.siguiente)


def test_descarga_de_onedrive_a_otro_host_se_rechaza():
    """109:RF-16 — la @microsoft.graph.downloadUrl se compara con los hosts antes de pedirla."""
    sim = NubeSimulada()
    fid = sim.crear('microsoft', 'a.txt', b'hola')
    sim.host_descarga = 'descargas.malo.example.net'
    p = _proveedor(sim, 'microsoft')
    with pytest.raises(_errores().HostNoPermitido):
        p.descargar(p.metadatos(fid), io.BytesIO())


@pytest.mark.parametrize('nombre', ['google', 'microsoft'])
def test_descarga_por_rangos(nombre):
    """109:RF-6 — la descarga se reanuda desde un byte, con Range."""
    rng = random.Random(SEMILLA)
    datos = rng.randbytes(rng.randrange(2000, 7000))
    desde = rng.randrange(1, len(datos) - 1)
    sim = NubeSimulada()
    fid = sim.crear(nombre, 'a.bin', datos)
    p = _proveedor(sim, nombre)
    destino = io.BytesIO()
    assert p.descargar(p.metadatos(fid), destino, desde=desde) == len(datos) - desde
    assert destino.getvalue() == datos[desde:], f'semilla {SEMILLA}'


def test_hoja_nativa_de_google_se_exporta_a_xlsx():
    """109:RF-5 — la hoja nativa se exporta a XLSX y se anotan los dos formatos."""
    sim = NubeSimulada()
    fid = sim.crear('google', 'Cabecera 2026', nativo=True, exportado=b'PK\x03\x04hoja exportada')
    p = _proveedor(sim, 'google')
    item = p.metadatos(fid)
    assert item.nativo and item.tamano is None
    destino = io.BytesIO()
    origen, exportado = p.exportar(item, destino)
    assert origen == 'application/vnd.google-apps.spreadsheet'
    assert exportado == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    assert destino.getvalue() == b'PK\x03\x04hoja exportada'


@pytest.mark.parametrize('nombre', ['google', 'microsoft'])
def test_fallos_401_403_404_y_429(nombre):
    """109:RF-6 — 401 caducado, 403 y 404 con su causa, y 429 esperando su Retry-After."""
    sim = NubeSimulada()
    fid = sim.crear(nombre, 'a.txt', b'hola')
    esperas: list[float] = []
    p = _proveedor(sim, nombre, esperas)
    sim.fallar(429, contiene=fid, cabeceras={'Retry-After': '3'})
    assert p.metadatos(fid).id == fid and esperas == [3.0]
    sim.fallar(403, contiene=fid)
    with pytest.raises(_errores().SinAcceso):
        p.metadatos(fid)
    with pytest.raises(_errores().NoEncontrado):
        p.metadatos('no-existe')
    sim.fallar(429, contiene=fid, veces=10)
    with pytest.raises(_errores().Limitado):
        p.metadatos(fid)
    sim.fallos.clear()          # los 429 que sobran tras agotar los reintentos no deben tapar el 401
    sim.revocar_todo()
    with pytest.raises(_errores().PermisoCaducado):
        p.metadatos(fid)


@pytest.mark.parametrize('nombre', ['google', 'microsoft'])
def test_token_revocado_a_mitad_de_la_descarga(nombre):
    """109:RF-6 — revocado a mitad: la descarga se corta y lo siguiente dice que el permiso caducó."""
    sim = NubeSimulada()
    fid = sim.crear(nombre, 'a.bin', random.Random(SEMILLA).randbytes(5000))
    p = _proveedor(sim, nombre)
    item = p.metadatos(fid)
    sim.revoca_a_mitad.add(fid)
    with pytest.raises(_errores().DescargaCortada):
        p.descargar(item, io.BytesIO())
    with pytest.raises(_errores().PermisoCaducado):
        p.metadatos(fid)


@pytest.mark.parametrize('nombre', ['google', 'microsoft'])
def test_las_cuentas_dan_el_adaptador_del_espacio_con_su_token(tmp_path, nombre):
    """109:RF-16, RF-17 — ``Cuentas.proveedor`` da el adaptador del espacio con la lista de hosts de su API y el token
    de acceso que renueva el cofre; otro espacio sin cuenta no lo obtiene (P13)."""
    cuentas_mod = _nube('cuentas')
    assert hasattr(cuentas_mod, 'HOSTS_API'), 'falta cuentas.HOSTS_API (T6)'
    assert hasattr(cuentas_mod.Cuentas, 'proveedor'), 'falta Cuentas.proveedor (T6)'
    sim = NubeSimulada()
    config = tmp_path / 'config' / 'nube.json'
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps(CONFIG_PRUEBA), encoding='utf-8')
    cuentas = cuentas_mod.Cuentas(config=config, cofre=tmp_path / 'cofre', adaptador=sim, dormir=lambda _s: None)
    url = cuentas.iniciar('espacio_a', nombre)
    q = sim.autorizar(url)
    cuentas.completar(q['state'], q['code'])
    fid = sim.crear(nombre, 'RED.txt', b'contenido')
    prov = cuentas.proveedor('espacio_a', nombre)
    assert prov.nombre == nombre and prov.metadatos(fid).nombre == 'RED.txt'
    assert prov.t.hosts is cuentas_mod.HOSTS_API[nombre]
    with pytest.raises(_errores().PermisoCaducado):
        cuentas.proveedor('espacio_b', nombre).metadatos(fid)


@pytest.mark.parametrize('nombre', ['google', 'microsoft'])
def test_la_api_de_un_proveedor_no_admite_los_hosts_del_otro(nombre):
    """109:RF-16 — la lista de hosts de cada adaptador es la de su API: ni el otro proveedor ni un host parecido."""
    hosts = (_nube('google_drive') if nombre == 'google' else _nube('onedrive')).HOSTS
    otro = 'graph.microsoft.com' if nombre == 'google' else 'www.googleapis.com'
    assert not hosts.admite(otro)
    assert not hosts.admite('www.googleapis.com.malo.example.net') and not hosts.admite('sharepoint.com')
