"""«Verificar el Caso base» desde la web (spec 015, T5)."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx2')

from fastapi.testclient import TestClient  # noqa: E402

from apoyo import esperar_trabajo  # noqa: E402
from convertersmartgrid.web import services  # noqa: E402
from convertersmartgrid.web.app import create_app  # noqa: E402

# Imita a la aceptación sobre un proyecto existente: deja el informe con el «Caso base»
# y el vínculo. PE104 no converge.
ACEPTACION_FALSA = textwrap.dedent('''
    import argparse, json
    from pathlib import Path
    from convertersmartgrid.powerfactory_binding import PowerFactoryProjectBinding
    p = argparse.ArgumentParser()
    for a in ('--existing-project', '--source-dgs', '--manifest', '--output-json', '--source-fingerprint'):
        p.add_argument(a)
    a, _resto = p.parse_known_args()
    if a.existing_project == 'BORRADO':
        # Lo que escribe la aceptación real cuando el proyecto ya no está (018:RF-16).
        Path(a.output_json).write_text(json.dumps({
            'status': 'NO_VERIFICADO', 'project': 'BORRADO', 'proyecto_ausente': True,
            'error': "No existe el proyecto 'BORRADO' en la carpeta 'F' ni en la raíz."}), encoding='utf-8')
        raise SystemExit(2)
    feeder = Path(a.source_dgs).stem
    ok = feeder != 'PE104'
    caso = {'status': 'VERIFICADO' if ok else 'NO_VERIFICADO',
            'comprobaciones': {'gps_barras': {'pass': True, 'fallos': []},
                               'flujo': {'pass': ok, 'fallos': [] if ok else ['no converge']}},
            'avisos': ['TR_A: corregido con el archivo original (kv_baja 0.22 → 0.38)']}
    binding = PowerFactoryProjectBinding(
        project=a.existing_project, folder='F', source_run_id='run', source_mode='mdb',
        source_fingerprint=a.source_fingerprint, feeders=(feeder,),
        dgs_sha256={feeder: 'd' * 64}, native_inventory_sha256='n' * 64,
        native_reread={'status': 'x', 'caso_base': {feeder: {
            'status': caso['status'], 'fallos': [] if ok else ['flujo'],
            'comprobaciones': {'flujo': ok}}}})
    Path(a.output_json).write_text(json.dumps({'caso_base': caso,
                                               'project_binding': binding.as_dict()}),
                                   encoding='utf-8')
    raise SystemExit(0 if ok else 2)
''')


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    guion = tmp_path / 'aceptacion_falsa.py'
    guion.write_text(ACEPTACION_FALSA, encoding='utf-8')
    monkeypatch.setattr(services, '_require_pf', lambda: (tmp_path, sys.executable))
    monkeypatch.setattr(services, '_script', lambda _nombre: guion)
    monkeypatch.setattr(services, 'pf_subprocess_env', lambda _d: None)

    def jobs(ws, feeders):
        out = []
        for f in feeders:
            dgs = Path(ws.out_dir) / f'{f}.dgs'
            dgs.parent.mkdir(parents=True, exist_ok=True)
            dgs.write_text('', encoding='utf-8')
            geo = None if f == 'SINGEO' else dgs.with_name(f'{f}_geography.json')
            out.append((f, dgs, geo))
        return out, []

    monkeypatch.setattr(services, 'dgs_jobs', jobs)
    monkeypatch.setattr(services, 'check_powerfactory_source_run', lambda ws, fs, **_kw: {
        'source_run_id': 'run', 'source_mode': 'mdb', 'source_fingerprint': 'f' * 64,
        'targets': [{'target': f} for f in fs]})
    with TestClient(create_app(tmp_path / 'web')) as c:
        yield c


def _proyecto_aceptado(client, wid):
    """Un proyecto ya importado y aceptado en este espacio, con su fuente activa.

    Verificar exige ese vínculo (018:RF-5): antes, la primera verificación creaba el vínculo
    con la fuente activa, sin comprobar de qué proyecto se trataba. La aceptación real lo
    graba al importar; aquí se graba directamente para no repetir la importación.
    """
    from convertersmartgrid.powerfactory_binding import PowerFactoryProjectBinding, record_project_binding

    ws = client.app.state.store.get(wid)
    ws.active_run_id = ws.loaded_run_id = 'run'
    ws.loaded_source_mode = 'mdb'
    ws.loaded_source_fingerprint = 'f' * 64
    record_project_binding(ws, PowerFactoryProjectBinding(
        project='P', folder='F', source_run_id='run', source_mode='mdb',
        source_fingerprint='f' * 64, feeders=('CA101', 'PE104', 'SINGEO'),
        dgs_sha256={}, native_inventory_sha256='n' * 64,
        native_reread={'status': 'VERIFICADO_PERSISTENCIA'}, accepted_at=0.0,
    ))


def test_verificar_el_caso_base_es_un_trabajo_y_guarda_cada_estado(client):
    """015:RF-9, 015:RF-14 - se verifica alimentador a alimentador, se puede repetir y el
    vínculo guarda el estado de cada uno sin borrar el de los demás."""
    wid = client.post('/api/workspaces').json()['id']
    _proyecto_aceptado(client, wid)
    url = f'/api/workspaces/{wid}/powerfactory/caso-base'
    assert client.post(url, json={'project': ' ', 'feeders': ['CA101']}).status_code == 422
    for feeders in (['CA101'], ['PE104', 'SINGEO']):
        trabajo = client.post(url, json={'project': 'P', 'feeders': feeders})
        assert trabajo.status_code == 202 and trabajo.json()['lane'] == 'powerfactory'
        estado = esperar_trabajo(client, trabajo.json())
        assert estado['status'] == 'done', estado
    resultado = {x['feeder']: x for x in estado['result']['feeders']}
    assert resultado['PE104']['status'] == 'NO_VERIFICADO'
    assert resultado['PE104']['comprobaciones']['flujo']['pass'] is False
    # Sin geografía no hay con qué comparar el GPS (015:RF-1).
    assert resultado['SINGEO']['status'] == 'NO_VERIFICADO'
    assert 'georreferenciación' in resultado['SINGEO']['motivo']
    ws = client.app.state.store.get(wid)
    estados = ws.pf_project_bindings['P']['native_reread']['caso_base']
    assert estados['CA101']['status'] == 'VERIFICADO'
    assert estados['PE104']['status'] == 'NO_VERIFICADO'
    assert set(ws.pf_project_bindings['P']['feeders']) == {'CA101', 'PE104', 'SINGEO'}


def test_018_rf16_un_proyecto_que_ya_no_esta_dice_el_motivo(client):
    """018:RF-16 — PE10 de prueba (2026-11-10): decía «código 2 sin informe» de un proyecto borrado en DIgSILENT."""
    from convertersmartgrid.powerfactory_binding import PowerFactoryProjectBinding, record_project_binding

    wid = client.post('/api/workspaces').json()['id']
    _proyecto_aceptado(client, wid)
    record_project_binding(client.app.state.store.get(wid), PowerFactoryProjectBinding(
        project='BORRADO', folder='F', source_run_id='run', source_mode='mdb', source_fingerprint='f' * 64,
        feeders=('CA101',), dgs_sha256={}, native_inventory_sha256='n' * 64,
        native_reread={'status': 'VERIFICADO_PERSISTENCIA'}, accepted_at=0.0))
    trabajo = client.post(f'/api/workspaces/{wid}/powerfactory/caso-base',
                          json={'project': 'BORRADO', 'feeders': ['CA101']})
    fila = esperar_trabajo(client, trabajo.json())['result']['feeders'][0]
    assert fila['status'] == 'NO_VERIFICADO' and fila['proyecto_ausente'] is True
    assert 'No existe el proyecto' in fila['motivo'] and 'sin informe' not in fila['motivo']


def test_verificar_el_caso_base_no_corre_el_flujo(client, monkeypatch):
    """015:RF-39 - la web verifica un proyecto ya importado sin pedir el flujo."""
    ordenes = []
    from convertersmartgrid.web import jobs

    real = jobs.JobContext.run_process

    def registra(self, cmd, **kw):
        ordenes.append(cmd)
        return real(self, cmd, **kw)

    monkeypatch.setattr(jobs.JobContext, 'run_process', registra)
    wid = client.post('/api/workspaces').json()['id']
    _proyecto_aceptado(client, wid)
    trabajo = client.post(f'/api/workspaces/{wid}/powerfactory/caso-base',
                          json={'project': 'P', 'feeders': ['CA101']})
    assert esperar_trabajo(client, trabajo.json())['status'] == 'done'
    assert ordenes and all('--run-load-flow' not in c and '--existing-project' in c for c in ordenes)


def test_018_rf10_usar_la_fuente_del_vinculo_es_un_trabajo_del_motor(client):
    """018:RF-10 — la ruta encola un trabajo en el carril del motor (cambia la ejecución
    activa); sin aceptación registrada falla con su causa, sin tocar el espacio."""
    wid = client.post('/api/workspaces').json()['id']
    url = f'/api/workspaces/{wid}/powerfactory/adoptar-fuente'
    assert client.post(url, json={'project': ' '}).status_code == 422
    trabajo = client.post(url, json={'project': 'NUNCA_ACEPTADO'})
    assert trabajo.status_code == 202 and trabajo.json()['lane'] == 'engine'
    estado = esperar_trabajo(client, trabajo.json())
    assert estado['status'] == 'failed' and 'PROJECT_BINDING_MISSING' in estado['error']
    assert client.app.state.store.get(wid).active_run_id is None


def test_018_rf13_la_lista_guardada_se_sirve_sin_abrir_digsilent(client):
    """018:RF-13 — tras reiniciar la web, la pestaña recupera la última lista leída con el
    vínculo recalculado, sin lanzar ningún trabajo."""
    wid = client.post('/api/workspaces').json()['id']
    vacia = client.get(f'/api/workspaces/{wid}/powerfactory/projects').json()
    assert vacia['projects'] == []
    _proyecto_aceptado(client, wid)
    ws = client.app.state.store.get(wid)
    ws.pf_inventory = {'folder': 'F', 'projects': [
        {'name': 'P', 'path': 'P', 'feeders': ['CA101']},
        {'name': 'OTRO', 'path': 'OTRO', 'feeders': ['X1']}]}
    proyectos = {p['path']: p for p in
                 client.get(f'/api/workspaces/{wid}/powerfactory/projects').json()['projects']}
    assert proyectos['P']['binding_blocked_code'] is None
    assert proyectos['OTRO']['binding_blocked_code'] == 'PROJECT_BINDING_MISSING'
    assert not client.app.state.jobs.active(wid)


def test_018_rf13_espacio_nuevo_parte_de_la_ultima_lectura_de_la_misma_carpeta(client, monkeypatch):
    """018:RF-13 — un espacio nuevo, sin lectura propia, toma la más reciente de otro espacio
    con la misma carpeta de DIgSILENT; la de otra carpeta no se usa."""
    monkeypatch.setattr(services, 'carpeta_pf', lambda: 'F')
    store = client.app.state.store
    for nombre, carpeta, cuando in (('vieja', 'F', 1.0), ('nueva', 'F', 2.0), ('otra', 'G', 3.0)):
        ws = store.get(client.post('/api/workspaces').json()['id'])
        ws.pf_inventory = {'folder': carpeta, 'projects': [
            {'name': nombre, 'path': nombre, 'feeders': ['CA101'], 'native_reread_at': cuando}]}
        ws.save()
    wid = client.post('/api/workspaces').json()['id']
    proyectos = client.get(f'/api/workspaces/{wid}/powerfactory/projects').json()['projects']
    assert [p['path'] for p in proyectos] == ['nueva']
    assert store.get(wid).pf_inventory['folder'] == 'F'


def _lecturas(client, monkeypatch, *lecturas):
    """Espacios con su lectura de la carpeta F: ``(proyecto, alimentadores, cuándo)``."""
    monkeypatch.setattr(services, 'carpeta_pf', lambda: 'F')
    store = client.app.state.store
    ids = []
    for nombre, feeders, cuando in lecturas:
        ws = store.get(client.post('/api/workspaces').json()['id'])
        ws.pf_inventory = {'folder': 'F', 'projects': [
            {'name': nombre, 'path': nombre, 'feeders': feeders, 'native_reread_at': cuando}]}
        ws.save()
        ids.append(ws.id)
    return ids


def test_018_rf13_una_lectura_propia_vieja_cede_ante_una_mas_nueva_de_la_carpeta(client, monkeypatch):
    """018:RF-13 — la carpeta de DIgSILENT es común: la lectura propia del 8 de noviembre ofrecía
    20261105-124711_CSG_TXT_CA101_CHN102, ya borrado al importar la versión del día 9, y el ajuste fallaba con
    «no existe el proyecto» (2026-11-13). Manda la lectura más reciente, sea de este espacio o de otro."""
    vieja, _nueva = _lecturas(client, monkeypatch, ('ANTES', ['CA101', 'CHN102'], 1.0),
                              ('cualquier nombre', ['CA101', 'CHN102'], 2.0))
    proyectos = client.get(f'/api/workspaces/{vieja}/powerfactory/projects').json()['projects']
    assert [p['path'] for p in proyectos] == ['cualquier nombre']


def test_018_rf13_un_proyecto_que_desaparecio_se_rechaza_antes_de_abrir_digsilent(client, monkeypatch):
    """018:RF-13 — si el proyecto pedido estaba en una lectura anterior de la carpeta y falta en la más reciente, la
    acción se rechaza antes de encolar y propone el de sus mismos alimentadores, sea cual sea su nombre. Uno que
    no sale en ninguna lectura (recién importado) no se bloquea."""
    vieja, nueva = _lecturas(client, monkeypatch, ('ANTES', ['CA101', 'CHN102'], 1.0),
                             ('cualquier nombre', ['CA101', 'CHN102', 'X1'], 2.0))
    store = client.app.state.store
    # La lectura más reciente trae también el exacto: va primero, antes del que lleva uno más.
    store.get(nueva).pf_inventory['projects'].append(
        {'name': 'zz exacto', 'path': 'zz exacto', 'feeders': ['CHN102', 'CA101'], 'native_reread_at': 2.0})
    store.get(nueva).save()
    ws = store.get(vieja)
    with pytest.raises(services.UserError, match=r"ANTES.*ya no está.*está: zz exacto, cualquier nombre"):
        services.native_action_context(ws, 'ANTES', ['CA101'], 'ajuste')
    assert services.proyecto_desaparecido(ws, 'RECIEN_IMPORTADO') is None
    assert services.proyecto_desaparecido(ws, 'cualquier nombre') is None


def test_018_rf13_sin_fecha_posterior_ni_en_otra_carpeta_no_se_rechaza(client, monkeypatch):
    """018:RF-13 con 018:RF-19 — no se declara inexistente un proyecto por la lectura de otra carpeta de DIgSILENT,
    ni con fechas iguales, ni con lecturas sin fecha de relectura: la acción sigue."""
    store = client.app.state.store
    vieja, _igual = _lecturas(client, monkeypatch, ('ANTES', ['CA101'], 5.0), ('OTRO', ['CA101'], 5.0))
    assert services.proyecto_desaparecido(store.get(vieja), 'ANTES') is None          # misma fecha
    otra = store.get(client.post('/api/workspaces').json()['id'])
    otra.pf_inventory = {'folder': 'G', 'projects': [{'name': 'OTRO', 'path': 'OTRO', 'feeders': ['CA101'],
                                                      'native_reread_at': 9.0}]}
    otra.save()
    assert services.proyecto_desaparecido(store.get(vieja), 'ANTES') is None          # otra carpeta
    sin_fecha = store.get(client.post('/api/workspaces').json()['id'])
    sin_fecha.pf_inventory = {'folder': 'F', 'projects': [{'name': 'NUEVO', 'path': 'NUEVO', 'feeders': ['CA101']}]}
    sin_fecha.save()
    assert services.proyecto_desaparecido(store.get(vieja), 'ANTES') is None          # sin fecha


def test_007_rf40_el_ultimo_ajuste_aplicado_sale_del_disco(client):
    """007:RF-40 — caso real CA101 (2026-10-15): tras reiniciar la web la base del ajuste se
    perdía con los trabajos; se rehace con los informes de la última aplicación del proyecto."""
    import json
    import os

    wid = client.post('/api/workspaces').json()['id']
    ws = client.app.state.store.get(wid)
    ws.out_dir.mkdir(parents=True, exist_ok=True)
    for nombre, project, feeder, cuando in (
            ('ajuste_cabecera_aplicacion_viejo.json', 'P', 'CA101', 1_000),
            ('ajuste_cabecera_aplicacion_nuevo_1.json', 'P', 'CA101', 2_000),
            ('ajuste_cabecera_aplicacion_nuevo_2.json', 'P', 'PE104', 2_000),
            ('ajuste_cabecera_aplicacion_otro.json', 'Q', 'CA101', 3_000),
            ('ajuste_cabecera_simulacion_sim.json', 'P', 'CA101', 4_000)):
        path = ws.out_dir / nombre
        path.write_text(json.dumps({'project': project, 'feeder': feeder, 'modo': 'aplicar',
                                    'escenario': 'Sin proyecto', 'cuadrado': True}), encoding='utf-8')
        os.utime(path, (cuando, cuando))
    ajuste = client.get(f'/api/workspaces/{wid}/demanda/ajuste/ultimo',
                        params={'project': 'P'}).json()['ajuste']
    assert ajuste['id'] == 'disco:nuevo' and ajuste['feeders'] == ['CA101', 'PE104']
    base = services.base_del_ajuste(ajuste, 'P')
    assert [f for f in base['feeders']] == ['CA101', 'PE104']
    assert client.get(f'/api/workspaces/{wid}/demanda/ajuste/ultimo',
                      params={'project': 'NINGUNO'}).json()['ajuste'] is None
