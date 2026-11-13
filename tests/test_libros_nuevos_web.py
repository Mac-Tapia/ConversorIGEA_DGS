"""Spec 104 en la web: los libros nuevos se reconocen, se verifican y se avisan solos.

Libros sintéticos pequeños, con nombres que no son de ninguna empresa salvo la forma «MMAA»; ningún dato real.
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
from pathlib import Path

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
    aplicacion = create_app(tmp_path / 'web', host='127.0.0.1')
    # Cada libro en este proceso: el spawn por libro solo lo necesitan las pruebas que terminan uno a mitad (RF-33).
    aplicacion.state.libros_nuevos.en_proceso = False
    return aplicacion


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


def _esperar_fondo(client, timeout: float = 60.0) -> None:
    vigilancia = client.app.state.libros_nuevos
    limite = time.monotonic() + timeout
    while vigilancia.ocupado():
        assert time.monotonic() < limite, 'el carril de fondo no terminó'
        time.sleep(0.05)


def _revisar(client, wid, ruta='revisar'):
    """104:RF-30: la revisión no devuelve un trabajo de la cola; se espera al carril de fondo."""
    r = client.post(f'/api/workspaces/{wid}/demanda/libros-nuevos/{ruta}')
    assert r.status_code == 200, r.text
    assert 'job' not in r.json()
    _esperar_fondo(client)
    return r.json()['lanzada']


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
    assert _revisar(client, wid) is False                                  # RF-6: el índice publicado es la base
    _libro_clientes(cli / '2026/1026clientes.xlsx', {'111': _mes_completo(2026, 10, 20., ruido=7),
                                                     '222': _mes_completo(2026, 10, 30., ruido=8),
                                                     '333': _mes_completo(2026, 10, 9., ruido=9)})
    assert _revisar(client, wid) is True
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
    assert _revisar(client, wid) is False                                  # RF-21: la misma foto no vuelve a avisar
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


def _operador_ocupado(app, wid):
    """Un trabajo del operador en el motor que dura hasta que se suelte."""
    soltar = threading.Event()
    job = app.state.jobs.submit(wid, 'prueba', 'Trabajo del operador', lambda ctx: soltar.wait(60), lane='engine')
    return job, soltar


def test_con_el_motor_ocupado_se_espera(app, client, tmp_path):
    """104:RF-4, 104:RF-30 — con un trabajo del operador en el motor, la revisión espera en el carril de fondo sin
    encolar nada, y se hace sola al quedar libre."""
    wid, cli = _espacio_con_septiembre(client, tmp_path)
    _libro_clientes(cli / '2026/1026clientes.xlsx', {'111': _mes_completo(2026, 10, ruido=3)})
    _job, soltar = _operador_ocupado(app, wid)
    r = client.post(f'/api/workspaces/{wid}/demanda/libros-nuevos/revisar').json()
    assert r['lanzada'] is True and r['estado']['fondo']['estado'] == 'en_espera'
    time.sleep(1.0)
    assert not client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()['avisos']
    assert [j.kind for j in app.state.jobs.list(wid) if j.status not in ('done', 'cancelled')] == ['prueba']
    soltar.set()
    _esperar_fondo(client)
    textos = [a['texto'] for a in client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()['avisos']]
    assert any(t.startswith('Llegó octubre 2026') for t in textos), textos


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
    vigilancia.revisar = lambda ws, **k: (time.sleep(1.0), vistos.append(ws.id), original(ws, **k))[-1]
    inicio = time.monotonic()
    assert client.get(f'/api/workspaces/{wid}').status_code == 200
    assert time.monotonic() - inicio < 1.0
    limite = time.monotonic() + 30
    while time.monotonic() < limite and not vistos:
        time.sleep(0.1)
    assert vistos == [wid]


def _esperar_dataset(client, wid, estado: str, timeout: float = 60.0) -> dict:
    limite = time.monotonic() + timeout
    while True:
        dataset = client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()['dataset'] or {}
        if dataset.get('estado') == estado:
            return dataset
        assert time.monotonic() < limite, dataset
        time.sleep(0.05)


def test_el_dataset_se_regenera_solo_sin_entrenar(app, client, tmp_path, monkeypatch):
    """104:RF-22, 104:RF-23, 104:RF-24 — con cabecera y medidores, el mes nuevo regenera el dataset con su huella y
    su perfil; ningún modelo se entrena."""
    wid, cli = _espacio_con_septiembre(client, tmp_path)
    _libro_cabecera(tmp_path / 'cab/2026/s.xlsx', {'M1': _serie(60, 200.0, inicio=_mes_completo(2026, 9)[0][0])})
    _asignar(client, wid, 'cabecera', tmp_path / 'cab')
    r = client.post(f'/api/workspaces/{wid}/demanda/cabecera/indexar')
    assert esperar_trabajo(client, r.json())['status'] == 'done'
    _asignar(client, wid, 'medidores', _equivalencia(tmp_path / 'eq.xlsx', [('A1', 'M1', 10.0, 'S1')]))
    app.state.libros_nuevos.en_fondo = False
    monkeypatch.setenv('CSG_DATASET_REPOSO_MIN', '0')
    _libro_clientes(cli / '2026/1026clientes.xlsx', {'111': _mes_completo(2026, 10, 20., ruido=7)})
    _revisar(client, wid)
    dataset = _esperar_dataset(client, wid, 'al_dia')
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
    assert _revisar(client, wid) is True
    textos = [a['texto'] for a in client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()['avisos']]
    assert any(t.startswith('Llegó mayo 2026 de clientes importantes') for t in textos)
    assert _revisar(client, wid) is False


# --------------------------------------------------------------------------- carril de fondo (104:RF-30 a RF-39)
def _hijos_de_fondo():
    import psutil

    return [h for h in psutil.Process().children(recursive=True) if h.is_running()]


def test_el_operador_arranca_enseguida_y_el_fondo_cede_sin_perder_lo_hecho(app, client, tmp_path, monkeypatch):
    """104:RF-30, 104:RF-32, 104:RF-33 — con la verificación de un libro en marcha (lenta, en su proceso), un trabajo
    del operador lanzado desde la web arranca enseguida, el proceso de fondo se termina en menos de 2 s, y al quedar
    libre el motor se verifica el libro sin volver a reindexar."""
    from convertersmartgrid.web import libros_nuevos as wl
    from convertersmartgrid.web import services

    wid, cli = _espacio_con_septiembre(client, tmp_path)
    _libro_clientes(cli / '2026/1026clientes.xlsx', {'111': _mes_completo(2026, 10, ruido=3)})
    vigilancia = app.state.libros_nuevos
    vigilancia.en_proceso = True
    original = wl.VigilanciaLibros._verificacion_de_clientes
    lento = {'si': True}

    def verificacion(self, ws, rel):
        return (time.sleep, 120) if lento['si'] else original(self, ws, rel)
    monkeypatch.setattr(wl.VigilanciaLibros, '_verificacion_de_clientes', verificacion)
    reindexados = []
    indexar = services.demanda_clientes_indexar
    monkeypatch.setattr(services, 'demanda_clientes_indexar',
                        lambda ws, ctx, **k: reindexados.append('ejecutar' in k) or indexar(ws, ctx, **k))
    assert client.post(f'/api/workspaces/{wid}/demanda/libros-nuevos/revisar').json()['lanzada'] is True
    limite = time.monotonic() + 60
    while 'Verificando' not in str(vigilancia.estado(app.state.store.get(wid))['fondo'].get('texto')):
        assert time.monotonic() < limite
        time.sleep(0.05)
    time.sleep(2.0)                                   # el proceso de fondo ya duerme dentro del «libro»
    lento['si'] = False
    hijos = _hijos_de_fondo()
    assert hijos, 'la verificación no corre en un proceso aparte'
    inicio = time.monotonic()
    job = client.post(f'/api/workspaces/{wid}/demanda/clientes/indexar').json()
    while client.get(f'/api/jobs/{job["id"]}').json()['status'] == 'queued':
        assert time.monotonic() - inicio < 2.0, 'el trabajo del operador quedó en cola'
        time.sleep(0.02)
    arranque = time.monotonic() - inicio
    while vigilancia.estado(app.state.store.get(wid))['fondo']['estado'] != 'en_espera':
        assert time.monotonic() - inicio < 2.0, 'el carril de fondo no cedió'
        time.sleep(0.02)
    cedio = time.monotonic() - inicio
    while any(h.is_running() for h in hijos):
        assert time.monotonic() - inicio < 2.0, 'el proceso del libro sigue vivo'
        time.sleep(0.02)
    print(f'arranque del operador {arranque:.2f} s, cesión {cedio:.2f} s')
    assert esperar_trabajo(client, job)['status'] == 'done'
    _esperar_fondo(client)
    textos = [a['texto'] for a in client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()['avisos']]
    assert any(t.startswith('Llegó octubre 2026') for t in textos), textos
    assert reindexados.count(True) == 1               # RF-32: lo hecho (el índice) no se repitió al reanudar
    assert not client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()['fondo']['por_verificar']


def test_cortar_un_libro_tarda_menos_de_2_s_y_el_proceso_va_en_prioridad_baja(app):
    """104:RF-32, 104:RF-33 — terminar a mitad de un libro no espera a que acabe (cancelar tardó 40 s el 2026-11-12),
    el proceso de fondo corre en prioridad baja y apagar la web no espera al carril."""
    from convertersmartgrid.web.fondo import Cedido, ejecutar_en_proceso, prioridad_del_proceso

    assert ejecutar_en_proceso(prioridad_del_proceso, ceder=lambda: False) == 'baja'
    corte = threading.Event()
    resultado = {}

    def correr():
        try:
            ejecutar_en_proceso(time.sleep, 120, ceder=corte.is_set)
        except Cedido:
            resultado['cedido'] = time.monotonic()
    hilo = threading.Thread(target=correr)
    hilo.start()
    time.sleep(3.0)                                  # el hijo ya está dentro de la «lectura»
    hijos = _hijos_de_fondo()
    inicio = time.monotonic()
    corte.set()
    hilo.join(timeout=10)
    assert resultado['cedido'] - inicio < 2.0, resultado['cedido'] - inicio
    assert hijos and not any(h.is_running() for h in hijos)
    inicio = time.monotonic()
    app.state.libros_nuevos.parar()
    assert time.monotonic() - inicio < 2.0


def test_primera_revision_sin_indice_solo_toma_la_foto(app, client, tmp_path, monkeypatch):
    """104:RF-34, 104:RF-35 — sin foto ni índice anteriores no se abre ningún libro; después solo se verifica el que
    llega, y «Verificar todos ahora» verifica todos."""
    from convertersmartgrid import demanda_medida as dm
    from convertersmartgrid import libros_nuevos as ln

    wid = client.post('/api/workspaces').json()['id']
    cli = tmp_path / 'clientes'
    for mes in (6, 7, 8, 9):
        _libro_clientes(cli / f'2026/{mes:02d}26clientes.xlsx', {'111': _mes_completo(2026, mes, ruido=mes)})
    _libro_cabecera(tmp_path / 'cab/2026/s.xlsx', {'M1': _serie(3, 200.0, inicio=_mes_completo(2026, 9)[0][0])})
    _asignar(client, wid, 'clientes', cli)
    _asignar(client, wid, 'cabecera', tmp_path / 'cab')
    aperturas = []
    for modulo, nombre in ((dm, 'abrir_libro'), (ln, 'abrir_libro'), (ln, 'curvas_de_clientes')):
        real = getattr(modulo, nombre)
        monkeypatch.setattr(modulo, nombre, lambda *a, _r=real, **k: aperturas.append(a[0]) or _r(*a, **k))
    verificados = []
    real_v = ln.verificar_libro_clientes
    monkeypatch.setattr(ln, 'verificar_libro_clientes',
                        lambda p, *a, **k: verificados.append(Path(p).name) or real_v(p, *a, **k))
    assert _revisar(client, wid) is False
    assert aperturas == [] and verificados == []
    estado = client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()
    assert estado['avisos'] == [] and estado['fondo']['por_verificar'] == 0
    registro = ' '.join(e['data'].get('text', '') for e in client.get(f'/api/workspaces/{wid}/events').json()
                        if e['type'] == 'log')
    assert 'tomados como base, sin abrirlos' in registro
    _libro_clientes(cli / '2026/1026clientes.xlsx', {'111': _mes_completo(2026, 10, ruido=10)})
    assert _revisar(client, wid) is True
    assert verificados == ['1026clientes.xlsx']
    verificados.clear()
    assert _revisar(client, wid, 'verificar-todos') is True
    assert sorted(verificados) == sorted(f'{m:02d}26clientes.xlsx' for m in (6, 7, 8, 9, 10))
    textos = [a['texto'] for a in client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()['avisos']]
    assert any('s.xlsx' in t for t in textos), textos  # la cabecera también se verificó


def test_el_dataset_no_se_regenera_con_el_motor_ocupado_y_dice_cuando(app, client, tmp_path, monkeypatch):
    """104:RF-36, 104:RF-37, 104:RF-38 — desactualizado, el dataset espera al reposo del motor y lo dice; si el
    operador lanza algo mientras se regenera, su proceso se termina y vuelve a desactualizado."""
    from convertersmartgrid.web import libros_nuevos as wl

    wid, cli = _espacio_con_septiembre(client, tmp_path)
    _libro_cabecera(tmp_path / 'cab/2026/s.xlsx', {'M1': _serie(60, 200.0, inicio=_mes_completo(2026, 9)[0][0])})
    _asignar(client, wid, 'cabecera', tmp_path / 'cab')
    r = client.post(f'/api/workspaces/{wid}/demanda/cabecera/indexar')
    assert esperar_trabajo(client, r.json())['status'] == 'done'
    _asignar(client, wid, 'medidores', _equivalencia(tmp_path / 'eq.xlsx', [('A1', 'M1', 10.0, 'S1')]))
    # Con el reposo de 5 min por defecto y el motor libre: desactualizado, con la hora prevista.
    _libro_clientes(cli / '2026/1026clientes.xlsx', {'111': _mes_completo(2026, 10, 20., ruido=7)})
    _revisar(client, wid)
    dataset = client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()['dataset']
    assert dataset['estado'] == 'desactualizado' and dataset['espera'] == 'reposo' and dataset['reposo_min'] == 5
    assert dataset['previsto'] > time.time() + 200
    # Motor ocupado y reposo cumplido: tampoco.
    monkeypatch.setenv('CSG_DATASET_REPOSO_MIN', '0')
    _job, soltar = _operador_ocupado(app, wid)
    time.sleep(1.0)
    dataset = client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()['dataset']
    assert dataset['estado'] == 'desactualizado' and dataset['espera'] == 'motor_ocupado', dataset
    # Libre: arranca en su proceso (aquí, uno que duerme); el operador lanza otro trabajo y el proceso se termina.
    lanzados = []
    real = wl.ProcesoFondo
    monkeypatch.setattr(wl, 'ProcesoFondo', lambda *a, **k: lanzados.append(real(time.sleep, 120)) or lanzados[-1])
    soltar.set()
    assert _esperar_dataset(client, wid, 'regenerando')
    limite = time.monotonic() + 30           # «regenerando» se publica justo antes de lanzar el proceso
    while not lanzados:
        assert time.monotonic() < limite
        time.sleep(0.02)
    _job, soltar = _operador_ocupado(app, wid)
    inicio = time.monotonic()
    dataset = _esperar_dataset(client, wid, 'desactualizado', timeout=5)
    assert time.monotonic() - inicio < 2.0 and dataset.get('interrumpido')
    assert not lanzados[0].vivo()
    soltar.set()


def test_cada_cambio_del_fondo_se_publica_en_los_eventos(app, client, tmp_path):
    """104:RF-31, 104:RF-39 — el carril de fondo publica su estado en los eventos del espacio, con el que la web relee;
    la revisión no deja ningún trabajo en la cola."""
    wid, cli = _espacio_con_septiembre(client, tmp_path)
    _libro_clientes(cli / '2026/1026clientes.xlsx', {'111': _mes_completo(2026, 10, ruido=3)})
    _revisar(client, wid)
    eventos = [e for e in client.get(f'/api/workspaces/{wid}/events').json() if e['type'] == 'libros_nuevos']
    estados = [e['data']['fondo']['estado'] for e in eventos]
    assert 'revisando' in estados and estados[-1] == 'libre', estados
    assert {j['kind'] for j in client.get(f'/api/workspaces/{wid}').json()['jobs']} == {'demanda_clientes_index'}


def test_solo_espacios_recientes_y_sin_leer_los_que_no_estan_abiertos(app, client, tmp_path, monkeypatch):
    """104:RF-40, 104:RF-41, 104:RF-32 — la revisión periódica no recorre los espacios viejos, de un espacio cerrado solo
    mira la foto, y del abierto lee los libros sin encolar nada en el motor común: el «Cargar / listar» de otro espacio
    arranca enseguida (2026-11-12: quedó en cola detrás de la revisión de otro espacio)."""
    from convertersmartgrid import libros_nuevos as ln

    vigilancia = app.state.libros_nuevos
    espacios = {}
    for nombre in ('abierto', 'cerrado', 'viejo'):
        wid, cli = _espacio_con_septiembre(client, tmp_path / nombre)
        _libro_clientes(cli / '2026/1026clientes.xlsx', {'111': _mes_completo(2026, 10, ruido=3)})
        espacios[nombre] = wid
    lista = app.state.store.list
    monkeypatch.setattr(app.state.store, 'list', lambda: [
        {**f, 'modified_at': 0.0} if f['id'] == espacios['viejo'] else f for f in lista()])
    leidos = []
    real = ln.verificar_clientes_de_fuente
    monkeypatch.setattr(ln, 'verificar_clientes_de_fuente', lambda raiz, *a, **k: leidos.append(str(raiz)) or real(raiz, *a, **k))
    vigilancia.pagina(espacios['abierto'], +1)
    vigilancia.revisar_todos()
    _esperar_fondo(client)
    assert leidos == [str(tmp_path / 'abierto' / 'clientes')]
    cerrado = client.get(f"/api/workspaces/{espacios['cerrado']}/demanda/libros-nuevos").json()
    assert cerrado['avisos'] == [] and cerrado['fondo']['estado'] == 'al_abrir'
    assert 'se leen al abrir el espacio' in cerrado['fondo']['texto']
    viejo = client.get(f"/api/workspaces/{espacios['viejo']}/demanda/libros-nuevos").json()
    assert viejo['ultima_revision'] is None and viejo['fondo']['estado'] == 'libre'
    assert not [j for j in app.state.jobs.list() if j.kind == 'libros_nuevos']
    # Al abrir el cerrado, sus libros se leen; nada de esto pasa por la cola del motor.
    vigilancia.pagina(espacios['cerrado'], +1)
    vigilancia.revisar_todos()
    _esperar_fondo(client)
    assert str(tmp_path / 'cerrado' / 'clientes') in leidos
    vigilancia.pagina(espacios['abierto'], -1)
    vigilancia.pagina(espacios['cerrado'], -1)


# --------------------------------------------------------------------------- dataset interrumpido (104:RF-42 a RF-46)
def _espacio_con_dataset(client, tmp_path):
    """Un espacio con cabecera, medidores y un mes nuevo de clientes: el dataset queda desactualizado al revisarlo."""
    wid, cli = _espacio_con_septiembre(client, tmp_path)
    _libro_cabecera(tmp_path / 'cab/2026/s.xlsx', {'M1': _serie(60, 200.0, inicio=_mes_completo(2026, 9)[0][0])})
    _asignar(client, wid, 'cabecera', tmp_path / 'cab')
    r = client.post(f'/api/workspaces/{wid}/demanda/cabecera/indexar')
    assert esperar_trabajo(client, r.json())['status'] == 'done'
    _asignar(client, wid, 'medidores', _equivalencia(tmp_path / 'eq.xlsx', [('A1', 'M1', 10.0, 'S1')]))
    _libro_clientes(cli / '2026/1026clientes.xlsx', {'111': _mes_completo(2026, 10, 20., ruido=7)})
    return wid


def _estado_guardado(app, wid) -> dict:
    from convertersmartgrid import libros_nuevos as ln
    from convertersmartgrid.web import libros_nuevos as wl

    return ln.leer_estado(wl.carpeta_estado(app.state.store.get(wid)))


def _poner_regenerando(app, wid, **dataset):
    """El estado que dejó en disco una web que se cerró de golpe con el dataset a medias (el del 2026-11-12)."""
    from convertersmartgrid import libros_nuevos as ln
    from convertersmartgrid.web import libros_nuevos as wl

    carpeta = wl.carpeta_estado(app.state.store.get(wid))
    estado = ln.leer_estado(carpeta)
    estado['dataset'] = {'estado': 'regenerando', 'libros_nuevos': ['clientes/2026/1026clientes.xlsx'], **dataset}
    ln.guardar_estado(carpeta, estado)


def _proceso_muerto() -> dict:
    """La identidad (pid y hora de arranque) de un proceso que ya terminó."""
    import subprocess
    import sys

    import psutil

    hijo = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(0.5)'])
    inicio = psutil.Process(hijo.pid).create_time()
    hijo.wait(timeout=30)
    return {'pid': hijo.pid, 'inicio': inicio}


def _avisos_del_dataset(client, wid) -> list[dict]:
    return [a for a in client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()['avisos']
            if a['tipo'] == 'dataset']


def _esperar_lanzado(lanzados) -> None:
    limite = time.monotonic() + 30           # «regenerando» se publica justo antes de lanzar el proceso
    while not lanzados:
        assert time.monotonic() < limite, 'no se lanzó el proceso del dataset'
        time.sleep(0.02)


def test_regenerando_sin_proceso_vivo_se_ve_interrumpido_y_se_retoma(app, client, tmp_path, monkeypatch):
    """104:RF-42, 104:RF-43, 104:RF-44 — el 2026-11-12 la web se cerró de golpe 47 min después de lanzar el dataset;
    la siguiente lo dejó en «regenerando» más de 11 h porque solo miraba los «desactualizado». Ahora, al leer el estado,
    un «regenerando» sin proceso vivo (sin identidad, como el real, o con un pid que ya terminó) pasa a interrumpido, se
    avisa en el paso de la demanda y la revisión lo retoma."""
    wid = _espacio_con_dataset(client, tmp_path)
    hace_11_h = time.time() - 11 * 3600
    _poner_regenerando(app, wid, inicio=hace_11_h, desde=hace_11_h)             # sin identidad: el estado heredado
    dataset = client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()['dataset']
    assert dataset['estado'] == 'desactualizado' and dataset['interrumpido'], dataset
    assert 'sin proceso vivo' in dataset['motivo_interrupcion']
    avisos = _avisos_del_dataset(client, wid)
    assert len(avisos) == 1 and 'quedó interrumpida' in avisos[0]['texto'] and 'se retoma' in avisos[0]['texto']
    # Con el pid de un proceso que ya terminó, lo mismo; el aviso no se repite por cada lectura.
    _poner_regenerando(app, wid, inicio=time.time(), proceso=_proceso_muerto())
    for _ in range(3):
        assert client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()['dataset']['estado'] == 'desactualizado'
    assert len(_avisos_del_dataset(client, wid)) == 2
    # Se retoma: la revisión lo regenera en el reposo y queda al día.
    app.state.libros_nuevos.en_fondo = False
    monkeypatch.setenv('CSG_DATASET_REPOSO_MIN', '0')
    _revisar(client, wid)
    assert _esperar_dataset(client, wid, 'al_dia')['libros_incluidos'] == ['clientes/2026/1026clientes.xlsx']


def test_regenerando_con_su_proceso_vivo_no_se_toca(app, client, tmp_path):
    """104:RF-42 — un «regenerando» cuyo proceso sigue vivo (otra web con los mismos datos) no se marca interrumpido ni
    se le envía ninguna señal; al terminar ese proceso, sí."""
    import subprocess
    import sys

    import psutil

    wid = _espacio_con_dataset(client, tmp_path)
    hijo = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    try:
        _poner_regenerando(app, wid, inicio=time.time(),
                           proceso={'pid': hijo.pid, 'inicio': psutil.Process(hijo.pid).create_time()})
        assert client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()['dataset']['estado'] == 'regenerando'
        assert hijo.poll() is None and not _avisos_del_dataset(client, wid)
    finally:
        hijo.kill()
        hijo.wait(timeout=30)
    assert client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()['dataset']['estado'] == 'desactualizado'


def test_el_dataset_que_pasa_su_plazo_se_termina_y_se_avisa(app, client, tmp_path, monkeypatch):
    """104:RF-42, 104:RF-45 — al lanzarse guarda la identidad de su proceso y de la web; el proceso propio que lleva más
    de su plazo (`CSG_DATASET_PLAZO_MIN`) sin terminar se termina, el dataset vuelve a desactualizado con el motivo y
    se avisa."""
    from convertersmartgrid.web import libros_nuevos as wl

    wid = _espacio_con_dataset(client, tmp_path)
    lanzados = []
    real = wl.ProcesoFondo
    monkeypatch.setattr(wl, 'ProcesoFondo', lambda *a, **k: lanzados.append(real(time.sleep, 120)) or lanzados[-1])
    monkeypatch.setenv('CSG_DATASET_REPOSO_MIN', '0')
    monkeypatch.setenv('CSG_DATASET_PLAZO_MIN', '0.05')                       # 3 s
    client.post(f'/api/workspaces/{wid}/demanda/libros-nuevos/revisar')
    _esperar_lanzado(lanzados)
    limite = time.monotonic() + 10
    while 'proceso' not in (_estado_guardado(app, wid).get('dataset') or {}):
        assert time.monotonic() < limite, 'el dataset no guardó la identidad de su proceso'
        time.sleep(0.05)
    guardado = _estado_guardado(app, wid)['dataset']
    assert guardado['proceso']['pid'] == lanzados[0].proc.pid and guardado['servidor']['pid'] == os.getpid()
    dataset = _esperar_dataset(client, wid, 'desactualizado', timeout=30)
    assert 'plazo' in dataset['motivo_interrupcion']
    assert not lanzados[0].vivo()
    assert any('plazo' in a['texto'] for a in _avisos_del_dataset(client, wid))
    app.state.libros_nuevos.parar()


def test_al_cerrar_la_web_y_al_arrancar_el_dataset_no_queda_regenerando(app, client, tmp_path, monkeypatch):
    """104:RF-46 — al apagarse, la web deja interrumpido el dataset que regeneraba; y al arrancar, aun con la vigilancia
    apagada (`CSG_LIBROS_NUEVOS=0`, como el 2026-11-12), revisa los «regenerando» de los espacios recientes."""
    from convertersmartgrid.web import libros_nuevos as wl

    wid = _espacio_con_dataset(client, tmp_path)
    lanzados = []
    real = wl.ProcesoFondo
    monkeypatch.setattr(wl, 'ProcesoFondo', lambda *a, **k: lanzados.append(real(time.sleep, 120)) or lanzados[-1])
    monkeypatch.setenv('CSG_DATASET_REPOSO_MIN', '0')
    client.post(f'/api/workspaces/{wid}/demanda/libros-nuevos/revisar')
    _esperar_lanzado(lanzados)
    vigilancia = app.state.libros_nuevos
    vigilancia.parar()
    assert not lanzados[0].vivo()
    dataset = _estado_guardado(app, wid)['dataset']
    assert dataset['estado'] == 'desactualizado' and 'se cerró la web' in dataset['motivo_interrupcion'], dataset
    # Arranque con la vigilancia apagada: el estado heredado se revisa igual, sin leer ningún libro.
    _poner_regenerando(app, wid, inicio=time.time() - 3600)
    nueva = wl.VigilanciaLibros(app.state.store, app.state.jobs, en_fondo=False)
    assert not nueva.activa
    detener = asyncio.Event()
    detener.set()
    asyncio.run(nueva.vigilar(detener))
    dataset = _estado_guardado(app, wid)['dataset']
    assert dataset['estado'] == 'desactualizado' and dataset['interrumpido'], dataset


# --------------------------------------------------------------------------- libros apartados y formatos (104:RF-47, 089:RF-110)
def test_libro_apartado_y_formato_salen_como_aviso_y_la_regla_se_confirma_una_vez(app, client, tmp_path, monkeypatch):
    """104:RF-47, 089:RF-109, 089:RF-110 — el 2026-11-12 dos libros quedaron fuera del dataset y solo constaban en la
    cuenta de «motivos_apartados». Ahora cada libro apartado y cada formato leído por su contenido salen como aviso de
    los libros de demanda, con su nombre; el operador confirma la columna que faltaba y la regla queda guardada."""
    from convertersmartgrid import demanda_medida as dm
    from test_libros_formas import _libro_desconocido, _libro_sin_textos

    wid = _espacio_con_dataset(client, tmp_path)
    cli = tmp_path / 'clientes'
    _libro_desconocido(cli / '2026/0726raro.xlsx')
    _libro_sin_textos(cli / '2026/0826sin.xlsx', {111: 31})
    app.state.libros_nuevos.en_fondo = False
    monkeypatch.setenv('CSG_DATASET_REPOSO_MIN', '0')
    _revisar(client, wid)
    _esperar_dataset(client, wid, 'al_dia')
    avisos = client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()['avisos']
    apartado = [a for a in avisos if a['tipo'] == 'apartado']
    assert [a['libro'] for a in apartado] == ['0726raro.xlsx'] and 'formato no reconocido' in apartado[0]['texto']
    formato = [a for a in avisos if a['tipo'] == 'formato' and a['libro'] == '0826sin.xlsx']
    assert len(formato) == 1 and 'le falta ERI' in formato[0]['texto']
    huella = dm.huella_de_aviso(formato[0]['texto'])
    # Una huella que no es la del aviso se rechaza antes de tocar nada.
    assert client.post(f'/api/workspaces/{wid}/demanda/clientes/formatos',
                       json={'huella': 'zz', 'columnas': {'eri': 'K'}}).status_code == 422
    r = client.post(f'/api/workspaces/{wid}/demanda/clientes/formatos', json={'huella': huella, 'columnas': {'eri': 'K'}})
    assert r.status_code == 200, r.text
    assert app.state.store.get(wid).demanda['clientes']['formatos'] == {huella: {'eri': 10}}
    # La regla se aplica sola: el dataset se regenera y el aviso del formato ya no pide nada.
    _esperar_fondo(client)
    _esperar_dataset(client, wid, 'al_dia')
    avisos = client.get(f'/api/workspaces/{wid}/demanda/libros-nuevos').json()['avisos']
    assert any(a['tipo'] == 'formato' and 'regla confirmada' in a['texto'] for a in avisos)
    assert client.post(f'/api/workspaces/{wid}/demanda/clientes/formatos',
                       json={'huella': huella, 'columnas': {'nada': 'K'}}).status_code == 400
