"""Spec 104 en la web: los libros nuevos se reconocen, se verifican y se avisan solos.

Libros sintéticos pequeños, con nombres que no son de ninguna empresa salvo la forma «MMAA»; ningún dato real.
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('python_calamine')

from fastapi.testclient import TestClient  # noqa: E402

from apoyo import esperar_trabajo  # noqa: E402
from convertersmartgrid.web.app import create_app  # noqa: E402
from test_libros_nuevos import _copia_al_mes, _mes_completo  # noqa: E402
from test_pronostico_demanda import _equivalencia, _libro_cabecera, _libro_clientes, _serie, _suministros  # noqa: E402


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    return create_app(tmp_path / 'web', host='127.0.0.1')


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


def _asignar(client, wid, tipo, path):
    r = client.post(f'/api/workspaces/{wid}/demanda/{tipo}/path', json={'path': str(path)})
    assert r.status_code == 200, r.text


def _indexar_clientes(client, wid):
    r = client.post(f'/api/workspaces/{wid}/demanda/clientes/indexar')
    assert esperar_trabajo(client, r.json())['status'] == 'done'


def _revisar(client, wid):
    r = client.post(f'/api/workspaces/{wid}/demanda/libros-nuevos/revisar')
    assert r.status_code == 200, r.text
    job = r.json()['job']
    if job is not None:
        assert job['lane'] == 'engine' and job['kind'] == 'libros_nuevos'
        assert esperar_trabajo(client, job)['status'] == 'done'
    return job


def _espacio_con_septiembre(client, tmp_path):
    wid = client.post('/api/workspaces').json()['id']
    cli = tmp_path / 'clientes'
    _libro_clientes(cli / '2026/0926clientes.xlsx',
                    {c: _mes_completo(2026, 9, 20., ruido=i) for i, c in enumerate(('111', '222'))})
    _asignar(client, wid, 'clientes', cli)
    _indexar_clientes(client, wid)
    sumi = _suministros(tmp_path / 'suministros/0926 Clientes_spl.xlsx', [('111', '111', 'S1', 'A1'), ('222', '222', 'S1', 'A1')])
    _asignar(client, wid, 'suministros', sumi)
    return wid, cli


def test_libro_nuevo_se_reconoce_verifica_y_avisa(client, tmp_path):
    """104:RF-1, 104:RF-5, 104:RF-6, 104:RF-20, 104:RF-21 — lo ya indexado no es nuevo; el libro de octubre que llega
    se indexa, se verifica y se avisa con el texto de la revisión manual; no se repite; se da por visto."""
    wid, cli = _espacio_con_septiembre(client, tmp_path)
    assert _revisar(client, wid) is None                                   # RF-6: el índice publicado es la base
    _libro_clientes(cli / '2026/1026clientes.xlsx', {'111': _mes_completo(2026, 10, 20., ruido=7),
                                                     '222': _mes_completo(2026, 10, 30., ruido=8),
                                                     '333': _mes_completo(2026, 10, 9., ruido=9)})
    assert _revisar(client, wid) is not None
    meta = client.get(f'/api/workspaces/{wid}').json()['demanda']['clientes']
    assert {x['nombre']: x['mes'] for x in meta['catalogo']}['2026/1026clientes.xlsx'] == '2026-10'
    estado = client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()
    textos = [a['texto'] for a in estado['avisos']]
    assert ('Llegó octubre 2026 de clientes importantes: 3 clientes, completo (31 días), 1 nuevos sin suministro: 333; '
            'falta el libro de suministros de octubre') in textos, textos
    registro = ' '.join(e['data'].get('text', '') for e in client.get(f'/api/workspaces/{wid}/events').json()
                        if e['type'] == 'log')
    assert 'Llegó octubre 2026 de clientes importantes' in registro
    assert estado['dataset']['estado'] == 'desactualizado'                 # RF-22, sin cabecera no se regenera
    assert estado['dataset']['libros_nuevos'] == ['clientes/2026/1026clientes.xlsx']
    assert _revisar(client, wid) is None                                   # RF-21: la misma foto no vuelve a avisar
    aviso = estado['avisos'][0]['id']
    r = client.post(f'/api/workspaces/{wid}/demanda/libros-nuevos/avisos/{aviso}/visto')
    assert aviso not in [a['id'] for a in r.json()['avisos']]


def test_libro_que_repite_el_mes_anterior_queda_inactivo(client, tmp_path):
    """104:RF-15, 104:RF-16, 104:RF-20 — el libro copiado se avisa y queda fuera del índice, también al reindexar a mano."""
    wid, cli = _espacio_con_septiembre(client, tmp_path)
    sep = {c: _mes_completo(2026, 9, 20., ruido=i) for i, c in enumerate(('111', '222'))}
    _libro_clientes(cli / '2026/1026clientes.xlsx', {c: _copia_al_mes(v, 2026, 10) for c, v in sep.items()})
    _revisar(client, wid)
    textos = [a['texto'] for a in client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()['avisos']]
    assert ('Octubre 2026 de clientes importantes repite los valores de septiembre 2026: pida el libro correcto; '
            'mientras, octubre no se usa para la máxima ni para el pronóstico.') in textos, textos
    for _vez in range(2):
        fila = next(x for x in client.get(f'/api/workspaces/{wid}').json()['demanda']['clientes']['catalogo']
                    if x['nombre'] == '2026/1026clientes.xlsx')
        assert fila['activo'] is False and any('repite' in a for a in fila['avisos'])
        _indexar_clientes(client, wid)


def test_con_el_motor_ocupado_se_espera(app, client, tmp_path, monkeypatch):
    """104:RF-4 — con un trabajo del motor en el espacio, el reconocimiento no se encola."""
    wid, cli = _espacio_con_septiembre(client, tmp_path)
    _libro_clientes(cli / '2026/1026clientes.xlsx', {'111': _mes_completo(2026, 10, ruido=3)})
    jobs = app.state.jobs
    ocupado = type('J', (), {'lane': 'engine'})()
    monkeypatch.setattr(jobs, 'active', lambda _wid: [ocupado])
    assert app.state.libros_nuevos.revisar(app.state.store.get(wid)) is None
    monkeypatch.undo()
    assert _revisar(client, wid) is not None


def test_intervalo_configurable_y_apagado(monkeypatch):
    """104:RF-2 — 10 minutos por defecto; la variable lo cambia y 0 apaga la revisión periódica."""
    from convertersmartgrid.web import libros_nuevos as wl

    monkeypatch.delenv(wl.VARIABLE_INTERVALO, raising=False)
    assert wl.intervalo_min() == 10.0
    monkeypatch.setenv(wl.VARIABLE_INTERVALO, '2.5')
    assert wl.intervalo_min() == 2.5
    monkeypatch.setenv(wl.VARIABLE_INTERVALO, '0')
    llamadas = []
    v = wl.VigilanciaLibros(type('S', (), {'list': lambda self: llamadas.append(1) or []})(), None)
    v.activa = True
    asyncio.run(asyncio.wait_for(v.vigilar(asyncio.Event()), timeout=5))   # una pasada al arrancar y termina
    assert llamadas == [1]


def test_al_abrir_el_espacio_se_revisa_sin_esperar(app, client, tmp_path):
    """104:RF-1, 104:RF-3 — abrir el espacio lanza la revisión en otro hilo; la página responde enseguida."""
    wid, cli = _espacio_con_septiembre(client, tmp_path)
    _libro_clientes(cli / '2026/1026clientes.xlsx', {'111': _mes_completo(2026, 10, ruido=3)})
    vigilancia = app.state.libros_nuevos
    vigilancia.activa = True
    vistos = []
    original = vigilancia.revisar
    vigilancia.revisar = lambda ws: (time.sleep(1.0), vistos.append(ws.id), original(ws))[-1]
    inicio = time.monotonic()
    assert client.get(f'/api/workspaces/{wid}').status_code == 200
    assert time.monotonic() - inicio < 1.0
    limite = time.monotonic() + 30
    while time.monotonic() < limite and not vistos:
        time.sleep(0.1)
    assert vistos == [wid]


def test_el_dataset_se_regenera_solo_sin_entrenar(app, client, tmp_path):
    """104:RF-22, 104:RF-23, 104:RF-24 — con cabecera y medidores, el mes nuevo regenera el dataset con su huella y
    su perfil; ningún modelo se entrena."""
    wid, cli = _espacio_con_septiembre(client, tmp_path)
    _libro_cabecera(tmp_path / 'cab/2026/s.xlsx', {'M1': _serie(60, 200.0, inicio=_mes_completo(2026, 9)[0][0])})
    _asignar(client, wid, 'cabecera', tmp_path / 'cab')
    r = client.post(f'/api/workspaces/{wid}/demanda/cabecera/indexar')
    assert esperar_trabajo(client, r.json())['status'] == 'done'
    _asignar(client, wid, 'medidores', _equivalencia(tmp_path / 'eq.xlsx', [('A1', 'M1', 10.0, 'S1')]))
    app.state.libros_nuevos.en_fondo = False
    _libro_clientes(cli / '2026/1026clientes.xlsx', {'111': _mes_completo(2026, 10, 20., ruido=7)})
    _revisar(client, wid)
    dataset = client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()['dataset']
    assert dataset['estado'] == 'al_dia', dataset
    assert dataset['libros_incluidos'] == ['clientes/2026/1026clientes.xlsx'] and len(dataset['huella']) == 64
    assert {x['clase'] for x in dataset['por_clase']} >= {'cabecera', 'cliente'}
    carpeta = app.state.store.get(wid).out_dir / 'pronostico' / 'dataset'
    assert (carpeta / 'perfil.json').is_file() and (carpeta / 'dataset.json').is_file()
    assert not any(p.suffix in {'.pt', '.ckpt'} for p in carpeta.rglob('*'))
    assert not os.environ.get('CSG_LIBROS_NUEVOS')                       # las pruebas no vigilan solas


def test_tope_de_libros_verificados_y_el_resto_en_la_siguiente(client, tmp_path):
    """104:RF-19 — tres por reconocimiento, del mes más reciente al más antiguo; el resto se dice y entra en la siguiente."""
    wid, cli = _espacio_con_septiembre(client, tmp_path)
    for mes in (5, 6, 7, 8):
        _libro_clientes(cli / f'2026/{mes:02d}26clientes.xlsx', {'111': _mes_completo(2026, mes, ruido=mes)})
    _revisar(client, wid)
    textos = [a['texto'] for a in client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()['avisos']]
    assert [t.split(':')[0] for t in textos if t.startswith('Llegó')] == [
        'Llegó agosto 2026 de clientes importantes', 'Llegó julio 2026 de clientes importantes',
        'Llegó junio 2026 de clientes importantes']
    assert any(t.startswith('Quedan 1 libros sin verificar (2026/0526clientes.xlsx)') for t in textos), textos
    assert _revisar(client, wid) is not None
    textos = [a['texto'] for a in client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()['avisos']]
    assert any(t.startswith('Llegó mayo 2026 de clientes importantes') for t in textos)
    assert _revisar(client, wid) is None
