"""Spec 111, T13: la API del plano de la red (``web/plano_api.py``, ``registrar_rutas_plano``).

Rutas sobre una aplicación FastAPI con una fuente de prueba: exports sintéticos sorteados con las dos disposiciones,
convertidos por la vía de siempre, y la geografía en el disco como la deja la conversión. Sin DIgSILENT: el guion es un
doble que contesta con los nombres de la identidad del plano. Toda regla eléctrica vive en el servidor (111:RF-15).
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import random
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip('pandapower')

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from convertersmartgrid.estudios_pf import LIMITES_POR_DEFECTO  # noqa: E402
from convertersmartgrid.geography import build_geography, geography_to_dict  # noqa: E402
from convertersmartgrid.model import build_feeder_model  # noqa: E402
from convertersmartgrid.plano_red import identidad  # noqa: E402
from synthetic_export import CRS_SINTETICO, ExportSpec, load_export  # noqa: E402

LAYOUTS = ('reducido', 'completo')
BASE = '/api/workspaces/w1/plano'


def _api():
    assert importlib.util.find_spec('convertersmartgrid.web.plano_api') is not None, 'falta web/plano_api.py'
    modulo = importlib.import_module('convertersmartgrid.web.plano_api')
    assert hasattr(modulo, 'registrar_rutas_plano'), 'plano_api no da registrar_rutas_plano'
    return modulo


class Fuente:
    """La fuente de la web, con un export sintético: modelo, geografía en disco, licencia y vínculo a elegir."""

    def __init__(self, ds, modelos, *, licencia=False, vinculado=False):
        self.ds, self.modelos, self.lic, self.vinc = ds, modelos, licencia, vinculado
        self.planes: list[dict] = []

    def alimentadores(self, ws):
        return sorted(self.modelos)

    def modelo(self, ws, alimentador):
        return self.modelos[alimentador]

    def ruta_geografia(self, ws, alimentador):
        ruta = Path(ws.out_dir) / f'{alimentador}_geography.json'
        return ruta if ruta.is_file() else None

    def licencia(self):
        return self.lic

    def vinculo(self, ws, project, alimentadores):
        binding = {'project': project, 'folder': 'Carpeta', 'source_run_id': ws.active_run_id,
                   'source_mode': 'txt', 'source_fingerprint': 'f'}
        return binding, self.vinc

    def limites(self):
        return LIMITES_POR_DEFECTO

    def perfil(self):
        return {}

    def guion(self, ws, ctx, plan):
        """El doble de ``tools/variacion_plano_pf.py``: contesta con los nombres de la identidad del plano."""
        self.planes.append(plan)
        ident = identidad(self.modelos[plan['feeders'][0]])
        barras = [[e['nombre_pf'], -14.0, -75.7, 0.99, 10.0] for e in ident['elementos'] if e['tipo'] == 'barra']
        tramos = [[e['nombre_pf'], [[-14.0, -75.7], [-14.0, -75.69]], 61.0] for e in ident['elementos']
                  if e['tipo'] == 'tramo']
        return {'motor': 'DIgSILENT', 'convergio': True, 'mensajes': [], 'geo': {'barras': barras, 'tramos': tramos}}


def _montar(tmp_path, layout='reducido', **opciones):
    seed = random.SystemRandom().randrange(1, 2 ** 31)
    spec = ExportSpec(feeders=random.Random(seed).randint(2, 4), seed=seed, layout=layout, sections_per_feeder=6,
                      switches_per_feeder=2)
    ds = load_export(spec, tmp_path / f'export_{seed}')
    ws = SimpleNamespace(id='w1', root=tmp_path / 'espacio', out_dir=tmp_path / 'espacio' / 'out',
                         plans_dir=tmp_path / 'espacio' / 'planes', active_run_id=f'run-{seed}')
    ws.out_dir.mkdir(parents=True)
    modelos = {}
    for net in ds.feeder_ids():
        m = build_feeder_model(ds, net, strict=True, include_geography=True)
        modelos[m.name] = m
        geo = geography_to_dict(build_geography(ds, m, source_crs=CRS_SINTETICO), m)
        (ws.out_dir / f'{m.name}_geography.json').write_text(json.dumps(geo), encoding='utf-8')
    fuente = Fuente(ds, modelos, **opciones)
    trabajos: list[dict] = []

    def submit(ws_, kind, title, fn, lane='engine'):
        resultado = fn(SimpleNamespace(log=lambda *_a, **_k: None, progress=lambda *_a, **_k: None))
        trabajo = {'id': f'j{len(trabajos)}', 'kind': kind, 'title': title, 'workspace_id': 'w1', 'lane': lane,
                   'status': 'done', 'progress': None, 'result': resultado, 'error': None, 'created_at': 0.0,
                   'started_at': 0.0, 'finished_at': 0.0, 'cancel_requested': False}
        trabajos.append(trabajo)
        return trabajo

    app = FastAPI()
    _api().registrar_rutas_plano(app, ws_or_404=lambda wid: ws, submit=submit, fuente=fuente)
    alimentador = max(modelos, key=lambda a: len(modelos[a].lines))
    return TestClient(app), ws, fuente, trabajos, alimentador, seed


def _abrir(cliente, alimentador, caso='Caso A'):
    plano = cliente.get(BASE, params={'alimentador': alimentador}).json()
    revision = plano['vistas'][0]['revision']
    r = cliente.post(f'{BASE}/variaciones', json={'alimentador': alimentador, 'caso': caso, 'revision': revision})
    assert r.status_code == 200, r.text
    return plano['vistas'][0], r.json()


@pytest.mark.parametrize('layout', LAYOUTS)
def test_111_rf2_la_vista_lleva_los_codigos_y_todos_los_vertices_de_la_fuente(tmp_path, layout):
    """111:RF-1, RF-2 — la vista de la API tiene los vértices del manifiesto, enteros, y el código de cada elemento."""
    cliente, ws, _f, _t, alimentador, seed = _montar(tmp_path, layout)
    r = cliente.get(BASE, params={'alimentador': alimentador})
    assert r.status_code == 200, (seed, r.text)
    datos = r.json()
    geo = json.loads((ws.out_dir / f'{alimentador}_geography.json').read_text(encoding='utf-8'))
    vista = datos['vistas'][0]
    assert vista['alimentador'] == alimentador and len(vista['revision']) == 64
    for t in vista['tramos']:
        assert t['vertices'] == [[p['lat'], p['lon']] for p in geo['lines'][t['codigo']]['path']], seed
    assert datos['motor']['motor'] == 'abierto' and datos['fondo']['encendido'] in (True, False)
    assert set(datos['alimentadores']) == {alimentador}


def test_111_rf4_una_maniobra_se_guarda_como_variacion_y_la_fuente_no_cambia(tmp_path):
    """111:RF-4, RF-15 — la API valida y versiona la maniobra; la geografía de la fuente queda con la misma huella."""
    cliente, ws, _f, _t, alimentador, seed = _montar(tmp_path)
    ruta = ws.out_dir / f'{alimentador}_geography.json'
    antes = hashlib.sha256(ruta.read_bytes()).hexdigest()
    vista, v = _abrir(cliente, alimentador)
    m = vista['maniobras'][0]
    nuevo = 'abierto' if m['estado'] == 'cerrado' else 'cerrado'
    r = cliente.patch(f'{BASE}/variaciones/{v["id"]}', json={'version': v['version'],
                                                            'edicion': {'tipo': 'maniobra', 'codigo': m['codigo'],
                                                                        'estado': nuevo}})
    assert r.status_code == 200, (seed, r.text)
    assert r.json()['version'] == 1 and r.json()['ediciones'][0]['estado'] == nuevo
    assert hashlib.sha256(ruta.read_bytes()).hexdigest() == antes
    assert cliente.get(f'{BASE}/variaciones/{v["id"]}').json()['version'] == 1


def test_111_rf15_una_edicion_imposible_es_422_con_su_motivo(tmp_path):
    """111:RF-15, RF-8 — la regla vive en la API: una maniobra que no existe o un equipo sin parámetros es 422."""
    cliente, _ws, _f, _t, alimentador, _seed = _montar(tmp_path)
    vista, v = _abrir(cliente, alimentador)
    r = cliente.patch(f'{BASE}/variaciones/{v["id"]}', json={'version': 0, 'edicion': {
        'tipo': 'maniobra', 'codigo': 'NO-EXISTE', 'estado': 'abierto'}})
    assert r.status_code == 422 and 'NO-EXISTE' in r.json()['detail']
    r = cliente.patch(f'{BASE}/variaciones/{v["id"]}', json={'version': 0, 'edicion': {
        'tipo': 'equipo', 'codigo': 'EQ-1', 'clase': 'seccionador', 'tramo': vista['tramos'][0]['codigo']}})
    assert r.status_code == 422 and 'tensión' in r.json()['detail'] and 'fases' in r.json()['detail']


def test_111_rf4_version_vieja_o_revision_cambiada_es_409(tmp_path):
    """111:RF-4 — con una versión vieja, 409; si la red cambió, 409 y la variación queda marcada y no se estudia."""
    cliente, ws, _f, _t, alimentador, _seed = _montar(tmp_path)
    vista, v = _abrir(cliente, alimentador)
    m = vista['maniobras'][0]
    edicion = {'tipo': 'maniobra', 'codigo': m['codigo'], 'estado': 'abierto'}
    assert cliente.patch(f'{BASE}/variaciones/{v["id"]}', json={'version': 0, 'edicion': edicion}).status_code == 200
    assert cliente.patch(f'{BASE}/variaciones/{v["id"]}', json={'version': 0, 'edicion': edicion}).status_code == 409
    ruta = ws.out_dir / f'{alimentador}_geography.json'
    geo = json.loads(ruta.read_text(encoding='utf-8'))
    geo['otra_revision'] = True
    ruta.write_text(json.dumps(geo), encoding='utf-8')
    r = cliente.patch(f'{BASE}/variaciones/{v["id"]}', json={'version': 1, 'edicion': edicion})
    assert r.status_code == 409
    assert cliente.get(f'{BASE}/variaciones/{v["id"]}').json()['revision_cambiada'] is True
    assert cliente.post(f'{BASE}/variaciones/{v["id"]}/estudiar', json={}).status_code == 409
    r = cliente.post(f'{BASE}/variaciones', json={'alimentador': alimentador, 'caso': 'X', 'revision': v['revision']})
    assert r.status_code == 409


def test_111_rf9_deshacer_rehacer_y_confirmar_por_la_api(tmp_path):
    """111:RF-9 — deshacer y rehacer hasta confirmar; confirmada, ya no se edita."""
    cliente, _ws, _f, _t, alimentador, _seed = _montar(tmp_path)
    vista, v = _abrir(cliente, alimentador)
    m = vista['maniobras'][0]
    v = cliente.patch(f'{BASE}/variaciones/{v["id"]}', json={'version': 0, 'edicion': {
        'tipo': 'maniobra', 'codigo': m['codigo'], 'estado': 'abierto'}}).json()
    v = cliente.post(f'{BASE}/variaciones/{v["id"]}/deshacer', json={'version': v['version']}).json()
    assert v['ediciones'] == [] and len(v['deshechas']) == 1
    v = cliente.post(f'{BASE}/variaciones/{v["id"]}/rehacer', json={'version': v['version']}).json()
    assert len(v['ediciones']) == 1 and v['deshechas'] == []
    v = cliente.post(f'{BASE}/variaciones/{v["id"]}/confirmar', json={'version': v['version']}).json()
    assert v['estado'] == 'confirmada'
    r = cliente.post(f'{BASE}/variaciones/{v["id"]}/deshacer', json={'version': v['version']})
    assert r.status_code == 422


def test_111_rf7_el_ajuste_es_una_propuesta_que_no_cambia_nada(tmp_path):
    """111:RF-7 — la propuesta de ajuste da el nodo y la distancia, y la variación sigue igual."""
    cliente, _ws, _f, _t, alimentador, seed = _montar(tmp_path)
    vista, v = _abrir(cliente, alimentador)
    barra = next((b for b in vista['barras'] if b['lat'] is not None), None)
    assert barra is not None, f'la red sorteada no tiene una barra con coordenadas: semilla={seed}'
    r = cliente.post(f'{BASE}/variaciones/{v["id"]}/ajuste', json={'punto': [barra['lat'], barra['lon']]})
    assert r.status_code == 200, r.text
    assert r.json()['nodo'] is not None and r.json()['distancia_m'] == pytest.approx(0.0, abs=1e-6)
    assert cliente.get(f'{BASE}/variaciones/{v["id"]}').json()['version'] == 0


@pytest.mark.parametrize('layout', LAYOUTS)
def test_111_rf17_sin_licencia_se_estudia_con_el_motor_abierto_en_su_carril(tmp_path, layout):
    """111:RF-17, RF-18, RF-10 — sin licencia, trabajo en el carril del motor y capas que dicen el motor abierto."""
    cliente, _ws, _f, trabajos, alimentador, seed = _montar(tmp_path, layout)
    _vista, v = _abrir(cliente, alimentador)
    r = cliente.post(f'{BASE}/variaciones/{v["id"]}/estudiar', json={'project': 'P'})
    assert r.status_code == 202 and trabajos[-1]['lane'] == 'engine'
    capas = cliente.get(f'{BASE}/resultados', params={'variacion': v['id']}).json()
    assert capas['pintable'], (seed, capas)
    assert capas['motor'] == 'abierto' and capas['capas']['tension']['leyenda']['motor'] == 'abierto'
    assert all(e['motor'] == 'abierto' for e in capas['capas']['cargabilidad']['elementos'])


def test_111_rf17_con_licencia_y_vinculo_se_estudia_en_digsilent(tmp_path):
    """111:RF-17, RF-18, RF-4 — con licencia y el proyecto vinculado, carril de DIgSILENT, plan firmado y nombres de
    la identidad; las capas dicen DIgSILENT."""
    cliente, _ws, fuente, trabajos, alimentador, _seed = _montar(tmp_path, licencia=True, vinculado=True)
    vista, v = _abrir(cliente, alimentador)
    m = vista['maniobras'][0]
    v = cliente.patch(f'{BASE}/variaciones/{v["id"]}', json={'version': 0, 'edicion': {
        'tipo': 'maniobra', 'codigo': m['codigo'], 'estado': 'abierto'}}).json()
    r = cliente.post(f'{BASE}/variaciones/{v["id"]}/estudiar', json={'project': 'P'})
    assert r.status_code == 202 and trabajos[-1]['lane'] == 'powerfactory'
    plan = fuente.planes[-1]
    assert plan['native_action_context']['action'] == 'plano' and plan['feeders'] == [alimentador]
    assert plan['ediciones'][0]['nombre_pf'] == m['nombre_pf'] and plan['variacion']['version'] == v['version']
    capas = cliente.get(f'{BASE}/resultados', params={'variacion': v['id']}).json()
    assert capas['pintable'] and capas['motor'] == 'DIgSILENT'


def test_111_rf17_con_licencia_y_sin_vinculo_no_va_a_digsilent(tmp_path):
    """111:RF-17 — con licencia pero sin el proyecto vinculado a la red cargada, el motor abierto, y se dice."""
    cliente, _ws, fuente, trabajos, alimentador, _seed = _montar(tmp_path, licencia=True, vinculado=False)
    _vista, v = _abrir(cliente, alimentador)
    assert cliente.post(f'{BASE}/variaciones/{v["id"]}/estudiar', json={'project': 'P'}).status_code == 202
    assert trabajos[-1]['lane'] == 'engine' and fuente.planes == []


def test_111_rf19_comparar_dos_casos_de_motores_distintos_por_la_api(tmp_path):
    """111:RF-12, RF-19 — dos variaciones estudiadas con motores distintos se comparan y la API lo dice."""
    cliente, _ws, fuente, _t, alimentador, _seed = _montar(tmp_path)
    _vista, a = _abrir(cliente, alimentador, 'Caso A')
    cliente.post(f'{BASE}/variaciones/{a["id"]}/estudiar', json={})
    fuente.lic = fuente.vinc = True
    _vista, b = _abrir(cliente, alimentador, 'Caso B')
    cliente.post(f'{BASE}/variaciones/{b["id"]}/estudiar', json={'project': 'P'})
    r = cliente.get(f'{BASE}/comparar', params={'a': a['id'], 'b': b['id']})
    assert r.status_code == 200, r.text
    c = r.json()
    assert c['comparable'] and c['mismo_motor'] is False and c['aviso_motores']
    assert c['elementos'] and {e['magnitud'] for e in c['elementos']} >= {'tension', 'cargabilidad'}


def test_111_rf11_un_resultado_de_otra_revision_no_se_pinta(tmp_path):
    """111:RF-11 — si la red cambió después del estudio, el resultado no se pinta y se dice por qué."""
    cliente, ws, _f, _t, alimentador, _seed = _montar(tmp_path)
    _vista, v = _abrir(cliente, alimentador)
    cliente.post(f'{BASE}/variaciones/{v["id"]}/estudiar', json={})
    ruta = ws.out_dir / f'{alimentador}_geography.json'
    ruta.write_text(ruta.read_text(encoding='utf-8') + ' ', encoding='utf-8')
    capas = cliente.get(f'{BASE}/resultados', params={'variacion': v['id']}).json()
    assert capas['pintable'] is False and 'revisión' in capas['motivo']


def test_111_rf4_sin_estudio_o_variacion_desconocida_se_dice(tmp_path):
    """111:RF-4, RF-15 — un identificador mal formado es 422; una variación sin estudiar no tiene resultados (404)."""
    cliente, _ws, _f, _t, alimentador, _seed = _montar(tmp_path)
    _vista, v = _abrir(cliente, alimentador)
    assert cliente.get(f'{BASE}/variaciones/..%2Fx').status_code in (404, 422)
    assert cliente.get(f'{BASE}/variaciones/zzzz').status_code == 422
    assert cliente.get(f'{BASE}/resultados', params={'variacion': v['id']}).status_code == 404


def test_111_rf16_las_rutas_del_plano_se_anaden_sin_quitar_ninguna(tmp_path):
    """111:RF-16 — montar el plano en la aplicación real no quita ni cambia ninguna ruta de antes."""
    from convertersmartgrid.web.app import create_app

    app = create_app(tmp_path / 'web')
    antes = {(r.path, tuple(sorted(getattr(r, 'methods', None) or ()))) for r in app.routes
             if getattr(r, 'path', None)}
    _api().registrar_rutas_plano(app, ws_or_404=lambda wid: None, submit=lambda *a, **k: None)
    despues = {(r.path, tuple(sorted(getattr(r, 'methods', None) or ()))) for r in app.routes
             if getattr(r, 'path', None)}
    assert antes <= despues
    assert all(p.startswith('/api/workspaces/{wid}/plano') for p, _m in despues - antes)
    assert {p for p, _m in despues if p.startswith('/api/workspaces/{wid}/plano')} >= {
        '/api/workspaces/{wid}/plano', '/api/workspaces/{wid}/plano/variaciones',
        '/api/workspaces/{wid}/plano/resultados', '/api/workspaces/{wid}/plano/comparar'}


def test_111_rf4_las_variaciones_del_alimentador_salen_del_servidor(tmp_path):
    """111:RF-4, RF-12 — lo guardado vive en el servidor: ``GET …/variaciones`` da las del alimentador y cuáles tienen
    estudio, sin depender de lo que recuerde el navegador."""
    cliente, _ws, _f, _t, alimentador, _seed = _montar(tmp_path)
    _vista, a = _abrir(cliente, alimentador, 'Caso A')
    _vista, b = _abrir(cliente, alimentador, 'Caso B')
    cliente.post(f'{BASE}/variaciones/{a["id"]}/estudiar', json={})
    r = cliente.get(f'{BASE}/variaciones', params={'alimentador': alimentador})
    assert r.status_code == 200, r.text
    datos = r.json()
    assert {v['id'] for v in datos['variaciones']} == {a['id'], b['id']}
    assert datos['estudiadas'] == [a['id']]
    otro = cliente.get(f'{BASE}/variaciones', params={'alimentador': 'NO-ES-DE-ESTE-ESPACIO'}).json()
    assert otro == {'variaciones': [], 'estudiadas': []}
