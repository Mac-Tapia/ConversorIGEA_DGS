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
from igea_dgs.web import services  # noqa: E402
from igea_dgs.web.app import create_app  # noqa: E402

# Imita a la aceptación sobre un proyecto existente: deja el informe con el «Caso base»
# y el vínculo. PE104 no converge.
ACEPTACION_FALSA = textwrap.dedent('''
    import argparse, json
    from pathlib import Path
    from igea_dgs.powerfactory_binding import PowerFactoryProjectBinding
    p = argparse.ArgumentParser()
    for a in ('--existing-project', '--source-dgs', '--manifest', '--output-json', '--source-fingerprint'):
        p.add_argument(a)
    a, _resto = p.parse_known_args()
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
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
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
    monkeypatch.setattr(services, 'check_powerfactory_source_run', lambda ws, fs: {
        'source_run_id': 'run', 'source_mode': 'mdb', 'source_fingerprint': 'f' * 64,
        'targets': [{'target': f} for f in fs]})
    with TestClient(create_app(tmp_path / 'web')) as c:
        yield c


def test_verificar_el_caso_base_es_un_trabajo_y_guarda_cada_estado(client):
    """015:RF-9, 015:RF-14 — se verifica alimentador a alimentador, se puede repetir y el
    vínculo guarda el estado de cada uno sin borrar el de los demás."""
    wid = client.post('/api/workspaces').json()['id']
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
    assert set(ws.pf_project_bindings['P']['feeders']) == {'CA101', 'PE104'}


def test_verificar_el_caso_base_no_corre_el_flujo(client, monkeypatch):
    """015:RF-39 — la web verifica un proyecto ya importado sin pedir el flujo."""
    ordenes = []
    from igea_dgs.web import jobs

    real = jobs.JobContext.run_process

    def registra(self, cmd, **kw):
        ordenes.append(cmd)
        return real(self, cmd, **kw)

    monkeypatch.setattr(jobs.JobContext, 'run_process', registra)
    wid = client.post('/api/workspaces').json()['id']
    trabajo = client.post(f'/api/workspaces/{wid}/powerfactory/caso-base',
                          json={'project': 'P', 'feeders': ['CA101']})
    assert esperar_trabajo(client, trabajo.json())['status'] == 'done'
    assert ordenes and all('--run-load-flow' not in c and '--existing-project' in c for c in ordenes)

