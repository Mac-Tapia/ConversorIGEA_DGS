"""Spec 070, T17 a T20: el asistente hace lo de las specs 107 a 112 por sus rutas de la web (RF-79).

``-k pit`` (T17): el diagnóstico y el expediente del PIT. La orden nombra el libro de la red y la proyección; el asistente
los sube al espacio por ``/api/pit/entradas``, pide el trabajo del carril engine y lo sigue hasta su resultado.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from datos_pit import perfil_b

from convertersmartgrid.aplicacion.asistente import tareas
from convertersmartgrid.aplicacion.asistente.interprete import _por_frase_literal
from convertersmartgrid.presentacion.web import services

PIT = ('pit_diagnostico', 'pit_expediente')


def test_070_rf79_pit_dos_tareas_que_escriben_y_se_reconocen_por_su_frase():
    """070:RF-79, 070:RF-84 — el diagnóstico y el expediente del PIT están en el catálogo, escriben en el espacio (esperan
    la confirmación del operador) y se reconocen por su frase mientras el modelo en uso no las conozca."""
    assert set(PIT) <= set(tareas.TAREAS) and set(PIT) <= set(getattr(tareas, 'TAREAS_107_112', ()))
    for tarea in PIT:
        assert tareas.EFECTOS[tarea] == (tareas.ESCRIBE,) and tareas.TAREAS[tarea].escribe, tarea
    assert _por_frase_literal('haz el diagnóstico del PIT del área AD-04 de 2027 a 2031', None) == 'pit_diagnostico'
    assert _por_frase_literal('diagnostica el plan de inversiones en transmisión', None) == 'pit_diagnostico'
    assert _por_frase_literal('arma el expediente del PIT de 2027 a 2031', None) == 'pit_expediente'


# ------------------------------------------------------------------ la web real
def _ficheros(tmp_path: Path, caso: dict) -> tuple[Path, Path]:
    """El libro de la red y la proyección del caso, fuera del espacio, como los tendría el operador."""
    claves = sorted({k for e in caso['elementos'] for k in e})
    wb = openpyxl.Workbook()
    hoja = wb.active
    hoja.title = 'Red'
    hoja.append(claves)
    for e in caso['elementos']:
        hoja.append([', '.join(e[k]) if isinstance(e.get(k), list) else e.get(k) for k in claves])
    carpeta = tmp_path / 'del_operador'
    carpeta.mkdir()
    red, proyeccion = carpeta / 'red.xlsx', carpeta / 'proyeccion.json'
    wb.save(red)
    proyeccion.write_text(json.dumps(caso['proyeccion']), encoding='utf-8')
    return red, proyeccion


@pytest.fixture
def web(tmp_path, monkeypatch):
    import convertersmartgrid.dominio.perfil_empresa as perfil_empresa
    from convertersmartgrid.presentacion.web.app import create_app

    caso = perfil_b(15)
    claves = sorted({k for e in caso['elementos'] for k in e})
    perfil = {**caso['perfil']}
    perfil['pit'] = {**perfil['pit'], 'libro_red': {'hoja': 'Red', 'columnas': {k: k for k in claves}},
                     'limites': {'tension_min_pu': 0.9, 'tension_max_pu': 1.1, 'cargabilidad_max_pct': 100}}
    monkeypatch.setattr(perfil_empresa, 'datos_perfil', lambda *a, **k: perfil)
    for nombre, valor in (('CSG_ASISTENTE_DATA', tmp_path / 'asistente'), ('CSG_TWIN_DATA', tmp_path / 'gemelo'),
                          ('CSG_WEB_FRONTEND', tmp_path / 'sin_front'), ('CSG_ML_GPU_LOCK', tmp_path / 'gpu.lock')):
        monkeypatch.setenv(nombre, str(valor))
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (None, None))     # sin modelo: la frase literal
    services._ASISTENTE_PLANES.clear()
    app = create_app(tmp_path / 'web')
    with TestClient(app) as cliente:
        app.state.asistente_http = cliente
        yield cliente, app, caso
    services._ASISTENTE_PLANES.clear()


def _esperar(cliente, trabajo: dict) -> dict:
    limite = time.monotonic() + 120
    while time.monotonic() < limite:
        r = cliente.get(f"/api/jobs/{trabajo['id']}").json()
        if r['status'] in ('done', 'failed', 'cancelled', 'parcial'):
            return r
        time.sleep(0.05)
    pytest.fail('la cola no terminó')


def _orden(cliente, wid: str, texto: str) -> dict:
    r = cliente.post(f'/api/workspaces/{wid}/asistente/orden', json={'texto': texto})
    assert r.status_code == 202, r.text
    fin = _esperar(cliente, r.json())
    assert fin['status'] == 'done', fin.get('error')
    return fin['result']['plan']


def test_070_rf79_pit_sin_ficheros_ni_area_lo_dice_el_plan(web):
    """070:RF-79 — sin el libro, la proyección ni el área (el perfil tiene dos), el plan dice qué falta y no se ofrece."""
    cliente, _app, caso = web
    wid = cliente.post('/api/workspaces').json()['id']
    plan = _orden(cliente, wid, 'haz el diagnóstico del PIT')
    assert plan['tarea'] == 'pit_diagnostico' and not plan['listo']
    faltan = ' '.join(plan['faltan'])
    assert 'libro de la red' in faltan and 'proyección' in faltan and 'años' in faltan and caso['area'] in faltan


def test_070_rf79_pit_el_diagnostico_sube_los_ficheros_y_sigue_su_trabajo(web, tmp_path):
    """070:RF-79 — la orden con el área, los años y los dos ficheros: el plan espera la confirmación; confirmado, sube
    los ficheros al espacio por la ruta del PIT, pide el diagnóstico al carril engine y deja su resultado."""
    cliente, app, caso = web
    red, proyeccion = _ficheros(tmp_path, caso)
    wid = cliente.post('/api/workspaces').json()['id']
    desde, hasta = caso['anios'][0], caso['anios'][1]
    plan = _orden(cliente, wid, f'haz el diagnóstico del PIT del área {caso["area"]} de {desde} a {hasta} '
                                f'con "{red}" y "{proyeccion}"')
    assert plan['tarea'] == 'pit_diagnostico' and plan['listo'], plan['faltan']
    assert plan['espera_confirmacion'], 'escribe en el espacio: espera al operador'
    r = cliente.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar")
    assert r.status_code == 202, r.text
    fin = _esperar(cliente, r.json())
    assert fin['status'] == 'done', fin.get('error')
    raiz = Path(app.state.store.get(wid).root)
    assert (raiz / 'entradas_pit' / 'red.xlsx').read_bytes() == red.read_bytes()
    assert (raiz / 'entradas_pit' / 'proyeccion.json').read_bytes() == proyeccion.read_bytes()
    assert (raiz / 'expedientes_pit' / caso['area'] / 'diagnostico_de_trabajo.json').is_file()
    assert fin['result']['texto'].startswith('Diagnóstico del PIT')
    assert [p['estado'] for p in fin['result']['pasos']] == ['done']


def test_070_rf79_pit_la_ruta_de_entradas_solo_admite_libros_y_json(web):
    """070:RF-79 — /api/pit/entradas deja los ficheros en el espacio y rechaza lo que no es un libro o un JSON."""
    cliente, app, _caso = web
    wid = cliente.post('/api/workspaces').json()['id']
    malo = cliente.post('/api/pit/entradas', data={'workspace_id': wid},
                        files=[('files', ('orden.exe', b'MZ', 'application/octet-stream'))])
    assert malo.status_code == 422 and 'orden.exe' in malo.json()['detail']
    bueno = cliente.post('/api/pit/entradas', data={'workspace_id': wid},
                         files=[('files', ('../fuera.json', b'{}', 'application/json'))])
    assert bueno.status_code == 200 and bueno.json()['rutas'] == ['entradas_pit/fuera.json']
    assert (Path(app.state.store.get(wid).root) / 'entradas_pit' / 'fuera.json').is_file()


# ------------------------------------------------------------------ VAD (T18)
VAD = ('vad_crear_estudio', 'vad_empresa_modelo')


def test_070_rf86_vad_dos_tareas_que_escriben_y_se_reconocen_por_su_frase():
    """070:RF-79, 070:RF-86 — crear el estudio del VAD y armar su empresa modelo están en el catálogo, escriben (esperan
    la confirmación) y se reconocen por su frase."""
    assert set(VAD) <= set(tareas.TAREAS) and set(VAD) <= set(getattr(tareas, 'TAREAS_107_112', ()))
    for tarea in VAD:
        assert tareas.EFECTOS[tarea] == (tareas.ESCRIBE,) and tareas.TAREAS[tarea].escribe, tarea
    assert _por_frase_literal('crea el estudio del VAD del grupo 1 para 2041-2045', None) == 'vad_crear_estudio'
    assert _por_frase_literal('arma la empresa modelo con "D:/caso"', None) == 'vad_empresa_modelo'


@pytest.fixture
def web_vad(tmp_path, monkeypatch):
    import convertersmartgrid.dominio.perfil_empresa as perfil_empresa
    from convertersmartgrid.presentacion.web.app import create_app

    monkeypatch.setattr(perfil_empresa, 'cargar_perfil',
                        lambda *a, **k: perfil_empresa.PerfilEmpresa(nombre='Distribuidora Sintética Norte'))
    for nombre, valor in (('CSG_ASISTENTE_DATA', tmp_path / 'asistente'), ('CSG_TWIN_DATA', tmp_path / 'gemelo'),
                          ('CSG_WEB_FRONTEND', tmp_path / 'sin_front'), ('CSG_ML_GPU_LOCK', tmp_path / 'gpu.lock')):
        monkeypatch.setenv(nombre, str(valor))
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (None, None))
    services._ASISTENTE_PLANES.clear()
    app = create_app(tmp_path / 'web')
    with TestClient(app) as cliente:
        app.state.asistente_http = cliente
        yield cliente, app
    services._ASISTENTE_PLANES.clear()


def _caso_vad(tmp_path: Path) -> Path:
    caso = tmp_path / 'caso_vad'
    caso.mkdir()
    (caso / 'a.json').write_text(json.dumps({}), encoding='utf-8')
    (caso / 'sistemas.json').write_text(json.dumps({'sistemas': {'SX1': {'anexo2': 'a.json'}, 'SX2': {}}}),
                                        encoding='utf-8')
    return caso


def _confirmar(cliente, wid: str, plan: dict) -> dict:
    r = cliente.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar")
    assert r.status_code == 202, r.text
    fin = _esperar(cliente, r.json())
    assert fin['status'] == 'done', fin.get('error')
    return fin['result']


def test_070_rf86_vad_crear_el_estudio_y_armar_la_empresa_modelo_por_la_web(web_vad, tmp_path):
    """070:RF-79, 070:RF-86 — «crea el estudio del VAD del grupo 1 para 2041-2045» lo crea con el único TdR del registro;
    «arma la empresa modelo con …» sube el caso por la ruta del VAD y deja el manifiesto, sistema por sistema."""
    cliente, app = web_vad
    wid = cliente.post('/api/workspaces').json()['id']
    plan = _orden(cliente, wid, 'crea el estudio del VAD del grupo 1 para 2041-2045')
    assert plan['tarea'] == 'vad_crear_estudio' and plan['listo'] and plan['espera_confirmacion'], plan['faltan']
    creado = _confirmar(cliente, wid, plan)
    assert creado['texto'].startswith('Estudio del VAD')
    estudios = cliente.get(f'/api/workspaces/{wid}/vad/estudios').json()['estudios']
    assert [(e['grupo'], e['periodo'], e['version_tdr']) for e in estudios] == [(1, '2041-2045', 'rcd-174-2025-os-cd')]

    caso = _caso_vad(tmp_path)
    plan = _orden(cliente, wid, f'arma la empresa modelo con "{caso}"')
    assert plan['tarea'] == 'vad_empresa_modelo' and plan['listo'], plan['faltan']
    hecho = _confirmar(cliente, wid, plan)
    raiz = Path(app.state.store.get(wid).root) / 'vad' / estudios[0]['id']
    m = json.loads((raiz / 'manifiesto.json').read_text(encoding='utf-8'))
    assert m['terminado'] and m['sistemas']['SX1']['pasos']['anexo2']['huecos'] and m['sistemas']['SX2']['sin_entrada']
    assert (raiz / 'caso' / 'sistemas.json').is_file() and (raiz / 'caso' / 'a.json').is_file()
    assert 'Empresa modelo armada' in hecho['texto']


def test_070_rf86_vad_el_caso_se_comprueba_antes_de_encolar(web_vad):
    """070:RF-86 — un nombre que no vale (reservado de Windows o con espacios), un caso sin sistemas.json o que nombra un
    fichero que no se subió se rechazan con 422 antes de encolar; sin estudio, 404."""
    cliente, _app = web_vad
    wid = cliente.post('/api/workspaces').json()['id']
    creado = cliente.post(f'/api/workspaces/{wid}/vad/estudios',
                          json={'grupo': 1, 'periodo': '2041-2045', 'version_tdr': 'rcd-174-2025-os-cd'})
    assert creado.status_code == 200, creado.text
    ruta = f"/api/workspaces/{wid}/vad/{creado.json()['id']}/armar"
    sistemas = json.dumps({'sistemas': {'SX1': {'anexo2': 'falta.json'}}}).encode()
    for ficheros, esperado in (([('files', ('CON.json', b'{}', 'application/json'))], 'CON.json'),
                               ([('files', ('a b.json', b'{}', 'application/json'))], 'a b.json'),
                               ([('files', ('a.json', b'{}', 'application/json'))], 'sistemas.json'),
                               ([('files', ('sistemas.json', sistemas, 'application/json'))], 'falta.json')):
        r = cliente.post(ruta, files=ficheros)
        assert r.status_code == 422 and esperado in r.json()['detail'], r.text
    sin_estudio = cliente.post(f'/api/workspaces/{wid}/vad/no-existe/armar',
                               files=[('files', ('sistemas.json', b'{}', 'application/json'))])
    assert sin_estudio.status_code == 404


# ------------------------------------------------------------------ plano (T19)
def test_070_rf79_plano_la_maniobra_se_reconoce_y_escribe_con_licencia():
    """070:RF-79, 070:RF-84 — abrir o cerrar una maniobra en el plano está en el catálogo, escribe y puede usar la
    licencia (espera la confirmación) y se reconoce por su frase; «para transferir la carga» sigue siendo de
    `transferencia`, que el modelo conoce."""
    assert 'plano_maniobra' in tareas.TAREAS and 'plano_maniobra' in getattr(tareas, 'TAREAS_107_112', ())
    assert set(tareas.EFECTOS['plano_maniobra']) == {tareas.ESCRIBE, tareas.LICENCIA}
    assert _por_frase_literal('abre el seccionador S-104 del alimentador AL01 y estúdialo', None) == 'plano_maniobra'
    assert _por_frase_literal('abre el seccionador S1 para transferir la carga de AL01 a AL02', None) is None


def test_070_rf79_plano_la_orden_da_la_maniobra_el_estado_y_el_caso():
    """070:RF-79 — de la orden salen la maniobra, abrir o cerrar y el caso; sin ellos, el plan dice qué falta."""
    from types import SimpleNamespace

    from convertersmartgrid.presentacion.web import asistente_operacion as ao

    assert hasattr(ao, '_plano'), 'falta lo que saca de la orden la maniobra, el estado y el caso'
    plan = SimpleNamespace(texto='abre el seccionador S-104 de AL01, caso «Máxima 2027», y estúdialo',
                           datos={'alimentadores': ['AL01']}, faltan=[])
    extras: dict = {}
    ao._plano(plan, extras)
    assert not plan.faltan and extras['plano'] == {'alimentador': 'AL01', 'maniobra': 'S-104', 'estado': 'abierto',
                                                   'caso': 'Máxima 2027'}
    vacio = SimpleNamespace(texto='haz algo en el plano', datos={'alimentadores': ['AL01', 'AL02']}, faltan=[])
    ao._plano(vacio, {})
    assert len(vacio.faltan) == 3


def test_070_rf79_plano_abre_una_variacion_cambia_la_maniobra_y_la_estudia(tmp_path):
    """070:RF-79 — los pasos del asistente, por las rutas del plano: la vista y su revisión, una variación, la maniobra
    (la fuente y la geografía no cambian) y el estudio en el carril del motor sin licencia, con capas que se pintan."""
    pytest.importorskip('pandapower')
    from test_plano_api import BASE, _montar

    from convertersmartgrid.aplicacion.asistente.ejecutor import ClienteWeb, PasoFallido, ejecutar, pasos

    assert 'plano_maniobra' in tareas.TAREAS, 'falta la tarea del plano'
    cliente, ws, _fuente, trabajos, alimentador, seed = _montar(tmp_path)
    cliente.app.add_api_route('/api/jobs/{jid}', lambda jid: next(t for t in trabajos if t['id'] == jid))
    geografia = (ws.out_dir / f'{alimentador}_geography.json').read_bytes()
    vista = cliente.get(BASE, params={'alimentador': alimentador}).json()['vistas'][0]
    m = vista['maniobras'][0]
    nuevo = 'abierto' if m['estado'] == 'cerrado' else 'cerrado'
    extras = {'plano': {'alimentador': alimentador, 'maniobra': m['codigo'], 'estado': nuevo, 'caso': 'Caso base'}}
    r = ejecutar(pasos('plano_maniobra', {'proyecto': 'P'}, extras), ClienteWeb(cliente, 'http://testserver', 'w1'))
    assert r['completo'], (seed, r)
    assert trabajos[-1]['kind'] == 'plano_estudiar' and trabajos[-1]['lane'] == 'engine'
    v = cliente.get(f'{BASE}/variaciones', params={'alimentador': alimentador}).json()['variaciones']
    assert [e for e in v[0]['ediciones'] if e['tipo'] == 'maniobra'] == [
        {'tipo': 'maniobra', 'codigo': m['codigo'], 'estado': nuevo, 'antes': m['estado']}], (seed, v)
    assert cliente.get(f'{BASE}/resultados', params={'variacion': v[0]['id']}).json()['pintable'], seed
    assert (ws.out_dir / f'{alimentador}_geography.json').read_bytes() == geografia, 'la fuente no cambia'
    falsa = {'plano': {**extras['plano'], 'maniobra': 'NO-EXISTE'}}
    with pytest.raises(PasoFallido, match=m['codigo']):
        ejecutar(pasos('plano_maniobra', {}, falsa), ClienteWeb(cliente, 'http://testserver', 'w1'))


# ------------------------------------------------------------------ benchmarks (T20)
def test_070_rf79_benchmark_la_tarea_es_su_herramienta_y_se_reconoce():
    """070:RF-79, 070:RF-84 — el benchmark de la 112 es una tarea de proceso con su herramienta de tools/, escribe
    (espera la confirmación) y se reconoce por su frase."""
    assert 'benchmark_anonimo' in tareas.TAREAS, 'falta la tarea del benchmark'
    t = tareas.TAREAS['benchmark_anonimo']
    assert t.modo == 'proceso' and t.funcion == 'benchmark_anonimo' and t.escribe
    assert tareas.EFECTOS['benchmark_anonimo'] == (tareas.ESCRIBE,)
    assert _por_frase_literal('genera el benchmark anonimizado de la red', None) == 'benchmark_anonimo'
    assert _por_frase_literal('consulta los datos de la red', None) != 'benchmark_anonimo'


def test_070_rf79_benchmark_sin_la_fuente_txt_lo_dice_el_plan_y_con_ella_corre_su_herramienta(tmp_path):
    """070:RF-79, 112:RF-1 — sin RED, CARGA y EQUIPOS en el espacio el plan dice qué falta; con ellos, el trabajo corre
    tools/benchmark_anonimo.py en local con esos ficheros, y «no se emite» (código 2) se dice como tal."""
    from types import SimpleNamespace

    from convertersmartgrid.presentacion.web import asistente_operacion as ao

    assert hasattr(ao, '_benchmark') and hasattr(services, '_asistente_benchmark'), 'falta el benchmark del asistente'
    rutas = {}
    ws = SimpleNamespace(input_path=lambda s: rutas.get(s, ''), out_dir=tmp_path / 'out')
    plan = SimpleNamespace(faltan=[], id='p1', tarea='benchmark_anonimo')
    ao._benchmark(ws, plan)
    assert plan.faltan and all(n in plan.faltan[0] for n in ('RED', 'CARGA', 'EQUIPOS'))
    for slot in ('red', 'loads', 'equipment'):
        rutas[slot] = str(tmp_path / f'{slot}.txt')
        Path(rutas[slot]).write_text('x', encoding='utf-8')
    plan.faltan.clear()
    ao._benchmark(ws, plan)
    assert not plan.faltan
    ordenes, codigo = [], [0]
    ctx = SimpleNamespace(job=SimpleNamespace(id='j7'), run_process=lambda cmd, **kw: ordenes.append(cmd) or codigo[0])
    r = services._asistente_benchmark(ws, ctx, plan)
    cmd = ordenes[-1]
    assert Path(cmd[1]).name == 'benchmark_anonimo.py' and cmd[cmd.index('--red') + 1] == rutas['red']
    assert cmd[cmd.index('--destino') + 1] == r['destino'] and r['codigo'] == 0 and 'uso local' in r['texto']
    codigo[0] = 2
    with pytest.raises(services.UserError, match='No se emite'):
        services._asistente_benchmark(ws, ctx, plan)


def test_070_rf79_pit_la_subida_rechaza_nombres_reservados_y_raros(web):
    """070:RF-79 (lección A8 del 2026-11-16) — /api/pit/entradas no deja entrar en el espacio un nombre reservado de
    Windows (CON, NUL, COM1…) ni uno con caracteres que no sean letras, dígitos, «-» o «_»."""
    cliente, _app, _caso = web
    wid = cliente.post('/api/workspaces').json()['id']
    for nombre in ('CON.json', 'nul.xlsx', 'a b.json', 'red;rm.xlsx'):
        r = cliente.post('/api/pit/entradas', data={'workspace_id': wid},
                         files=[('files', (nombre, b'{}', 'application/json'))])
        assert r.status_code == 422 and nombre in r.json()['detail'], (nombre, r.text)
