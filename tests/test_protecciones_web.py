"""Spec 049, T3: el estudio de protecciones en la API web.

El guion de DIgSILENT es un falso que devuelve capacidades completas y tiempos de cada falla:
lo que se prueba es qué dice la web con ellos y, sobre todo, qué dice cuando falta algo.
"""
from __future__ import annotations

import json
import random

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx2')

from fastapi.testclient import TestClient  # noqa: E402

from apoyo import esperar_trabajo, vincular_proyecto  # noqa: E402
from apoyo_pf_web import guion_falso  # noqa: E402,F401
from convertersmartgrid import datos_empresa as de  # noqa: E402
from convertersmartgrid import estudios_pf, protecciones as pr  # noqa: E402
from convertersmartgrid.web.app import create_app  # noqa: E402

FEEDERS = ['A1', 'A2']

GUION = r'''
import argparse, json
from pathlib import Path
p = argparse.ArgumentParser()
for opcion in ('--plan', '--output-json', '--cancel-file'):
    p.add_argument(opcion)
p.add_argument('--capacidades', action='store_true')
a = p.parse_args()
plan = json.loads(Path(a.plan).read_text(encoding='utf-8'))
if a.capacidades:
    informe = {'project': plan['project'], 'modo': 'capacidades', 'version': '24.0.1', 'caso': 'Sin proyecto',
               'avisos': [], 'recibido': plan,
               'comandos': {'ComShc': {'existe': True, 'ejecuta': plan['ejecutar_ordenes'] or None,
                                       'metodos': {'GetFaultType': True},
                                       'atributos': {a: True for a in ('shcobj', 'iopt_shc', 'Rf', 'Xf', 'iopt_allbus')}},
                            'ComShctrace': {'existe': True, 'ejecuta': None, 'metodos': {m: True for m in (
                                'ExecuteInitialStep', 'ExecuteNextStep', 'NextStepAvailable', 'GetDeviceTime',
                                'GetTrippedDevices', 'GetStartedDevices')}}},
               'clases': {'ElmRelay': {'cuantos': 1}, 'RelFuse': {'cuantos': 2}},
               'generacion': [{'nombre': 'Externa', 'clase': 'ElmXnet', 'en_servicio': True}]}
else:
    fallas = []
    for f in plan['fallas']:
        devs = [{'id': d['id'], 'tiempo_s': 0.1 if d['id'] in f['protegen'] else 0.6, 'corriente_a': 2000.0,
                 'estado': 'disparo' if d['id'] in f['protegen'] else 'arranco'} for d in plan['dispositivos']]
        fallas.append({**f, 'estado': 'evaluada', 'dispositivos': devs, 'secuencia': []})
    informe = {'project': plan['project'], 'modo': 'fallas', 'fallas': fallas, 'recibido': plan}
Path(a.output_json).write_text(json.dumps(informe), encoding='utf-8')
'''


@pytest.fixture()
def client(tmp_path, monkeypatch, guion_falso):
    (guion_falso / 'falso_protecciones_pf.py').write_text(GUION, encoding='utf-8')
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    monkeypatch.setenv('CSG_PERFIL_EMPRESA', str(tmp_path / 'no_hay_perfil.json'))
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as c:
        yield c


def _espacio(client):
    wid = client.post('/api/workspaces').json()['id']
    vincular_proyecto(client, wid, 'P', FEEDERS)
    return wid


def _libro(client, wid, rng):
    """Un relé que respalda a dos fusibles, en el libro de la empresa del proyecto."""
    fusibles = [{'id': f'FU{i}', 'cubiculo': f'C{i}', 'clase': 'fusible', 'fabricante': 'X', 'modelo': 'K',
                 'curva': 'K', 'arranque': 10.0, 'unidad_arranque': 'A', 'poder_corte_ka': 8.0, 'fuente': 'ficha',
                 'origen': 'l.xlsx'} for i in (1, 2)]
    rele = {'id': 'R1', 'cubiculo': 'C0', 'clase': 'rele', 'fabricante': 'X', 'modelo': 'Y', 'curva': 'IEC NI',
            'arranque': round(rng.uniform(50, 200), 1), 'unidad_arranque': 'A', 'dial': 0.1, 'unidad_dial': 'dial',
            'poder_corte_ka': 20.0, 'fuente': 'ficha', 'respalda_a': ['FU1', 'FU2'], 'origen': 'l.xlsx'}
    ws = client.app.state.store.get(wid)
    ws.datos_empresa['P'] = {'nombre': 'l.xlsx', 'cargado': '2026-11-06T00:00:00',
                             'libro': de.Libro(nombre='l.xlsx', protecciones=[rele, *fusibles]).a_dict()}
    ws.save()


def _perfil(tmp_path, monkeypatch, cti):
    ruta = tmp_path / 'perfil.json'
    ruta.write_text(json.dumps({'protecciones': {'cti_s': cti, 'factor_sensibilidad': 1.5,
                                                 'margen_poder_corte': 1.0}}), encoding='utf-8')
    monkeypatch.setenv('CSG_PERFIL_EMPRESA', str(ruta))


def _impedancia_real(monkeypatch):
    """La única entrada que ninguna fuente trae real hoy: se da por buena solo en esta prueba."""
    original = estudios_pf.inventario_de_protecciones

    def con_impedancia(*a, **k):
        return {**original(*a, **k), 'impedancia_real': True}

    monkeypatch.setattr(estudios_pf, 'inventario_de_protecciones', con_impedancia)


def _fallas():
    return [{'id': f'B{i}_3f', 'tipo': 'trifasica', 'ubicacion': f'B{i}', 'r_ohm': 0, 'x_ohm': 0,
             'protegen': [f'FU{i}']} for i in (1, 2)]


def test_web_muestra_dato_faltante(client):
    """049:RF-2, 049:RF-10 — sin libro, sin capacidades ni criterios, la web dice bloqueado con
    cada ausencia, avisa de que un flujo convergente no es selectividad y no encola nada."""
    wid = _espacio(client)
    r = client.get(f'/api/workspaces/{wid}/pf/protecciones', params={'project': 'P'})
    assert r.status_code == 200, r.text
    estado = r.json()
    d = estado['disponibilidad']
    assert d['disponible'] is False
    assert any('dispositivos de protección' in f for f in d['faltan'])
    assert any('cortocircuito' in f for f in d['faltan'])
    assert any('protecciones.cti_s' in f for f in d['faltan'])
    assert any('Comprobar capacidades' in b for b in d['bloqueos'])
    assert 'selectividad' in estado['aviso'] and 'converja' in estado['aviso']
    assert estado['evaluaciones'] == {} and estado['capacidades'] is None
    r = client.post(f'/api/workspaces/{wid}/pf/protecciones/ejecutar',
                    json={'project': 'P', 'feeders': FEEDERS, 'caso': 'Sin proyecto', 'periodo': '2026-07',
                          'fallas': _fallas()})
    assert r.status_code == 400 and 'bloqueado' in r.json()['detail'] and 'protecciones.cti_s' in r.json()['detail']
    assert client.app.state.jobs.active(wid) == []
    catalogo = client.get(f'/api/workspaces/{wid}/pf/estudios', params={'project': 'P'}).json()
    fila = next(o for o in catalogo['no_ofrecidos'] if o['clave'] == 'protecciones')
    assert any('cti_s' in f for f in fila['falta'])
    # Una falla mal planteada no llega ni al servicio.
    r = client.post(f'/api/workspaces/{wid}/pf/protecciones/ejecutar',
                    json={'project': 'P', 'feeders': FEEDERS, 'caso': 'Sin proyecto', 'periodo': '2026-07',
                          'fallas': [{**_fallas()[0], 'r_ohm': -1}]})
    assert r.status_code == 422


def test_capacidades_se_comprueban_como_trabajo(client):
    """049:RF-1 — comprobar las capacidades es un trabajo del carril de DIgSILENT con el contexto
    firmado; lo que deja se guarda con el proyecto y deja de bloquear lo que comprobó."""
    wid = _espacio(client)
    job = client.post(f'/api/workspaces/{wid}/pf/protecciones/capacidades',
                      json={'project': 'P', 'feeders': FEEDERS, 'ejecutar_ordenes': True})
    assert job.status_code == 202, job.text
    fin = esperar_trabajo(client, job.json())
    assert fin['status'] == 'done', fin
    recibido = fin['result']['informe']['recibido']
    assert recibido['native_action_context']['action'] == 'protecciones' and recibido['ejecutar_ordenes'] is True
    estado = client.get(f'/api/workspaces/{wid}/pf/protecciones', params={'project': 'P'}).json()
    assert estado['capacidades']['version'] == '24.0.1'
    assert estado['capacidades']['dispositivos'] == {'ElmRelay': 1, 'RelFuse': 2}
    assert not any('Comprobar capacidades' in b for b in estado['disponibilidad']['bloqueos'])
    assert estado['disponibilidad']['disponible'] is False          # sin libro ni criterios, sigue bloqueado


@pytest.mark.parametrize('semilla', [3, 41])
def test_fallas_y_coordinacion_desde_la_web(client, tmp_path, monkeypatch, semilla):
    """049:RF-4, 049:RF-5, 049:RF-7, 049:RF-10 — con todo comprobado, las fallas van al guion con
    su plan y la evaluación se publica con su estado, márgenes y lo no evaluado; un CTI mayor que
    el margen da «no cumple» aunque las fallas se calculen."""
    rng = random.Random(semilla)
    wid = _espacio(client)
    _libro(client, wid, rng)
    _impedancia_real(monkeypatch)
    _perfil(tmp_path, monkeypatch, cti=0.3)
    fin = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/pf/protecciones/capacidades', json={
        'project': 'P', 'feeders': FEEDERS, 'ejecutar_ordenes': True}).json())
    assert fin['status'] == 'done', fin
    estado = client.get(f'/api/workspaces/{wid}/pf/protecciones', params={'project': 'P'}).json()
    assert estado['disponibilidad']['disponible'], estado['disponibilidad']
    cuerpo = {'project': 'P', 'feeders': FEEDERS, 'caso': 'Sin proyecto', 'periodo': '2026-07', 'fallas': _fallas()}
    r = client.post(f'/api/workspaces/{wid}/pf/protecciones/ejecutar', json={**cuerpo, 'caso': 'Con proyecto'})
    assert r.status_code == 400 and 'Sin proyecto' in r.json()['detail']
    fin = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/pf/protecciones/ejecutar', json=cuerpo).json())
    assert fin['status'] == 'done', fin
    plan = fin['result']['informe']['recibido']
    assert plan['schema'] == pr.ESQUEMA_PLAN and plan['rol'] == 'sin_proyecto'
    assert plan['aportes'] == [{'nombre': 'Externa', 'clase': 'ElmXnet', 'en_servicio': True}]
    e = fin['result']['evaluacion']
    # El falso da la corriente de cada dispositivo: todo cumple, con 0,5 s de margen en cada pareja.
    assert e['estado'] == pr.CUMPLE, e
    assert [m['margen_s'] for m in e['margenes']] == pytest.approx([0.5] * len(_fallas()))
    assert set(fin['result']['ficheros']) == {'json', 'tiempos', 'margenes', 'violaciones'}
    publicado = client.get(f'/api/workspaces/{wid}/pf/protecciones', params={'project': 'P'}).json()
    assert publicado['evaluaciones']['sin_proyecto']['estado'] == pr.CUMPLE
    assert publicado['aviso'] == pr.AVISO_SELECTIVIDAD
    # Con un CTI que el margen no alcanza, la misma corrida no cumple.
    _perfil(tmp_path, monkeypatch, cti=0.8)
    fin = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/pf/protecciones/ejecutar', json=cuerpo).json())
    assert fin['result']['evaluacion']['estado'] == pr.NO_CUMPLE
    assert {v['tipo'] for v in fin['result']['evaluacion']['violaciones']} == {'cti'}
