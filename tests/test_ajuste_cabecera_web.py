"""Spec 006: la API del ajuste a la máxima de cabecera (plan y trabajo de DIgSILENT).

El guion de DIgSILENT se sustituye por uno falso que devuelve el plan recibido: aquí se
prueba qué manda la web (objetivo, clientes, kVA de respaldo) y que corre en el carril
``powerfactory``. El guion de verdad se prueba en ``test_ajuste_cabecera_guion.py``.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx2')
pytest.importorskip('python_calamine')
pytest.importorskip('openpyxl')

from fastapi.testclient import TestClient  # noqa: E402

from apoyo import esperar_trabajo  # noqa: E402
from igea_dgs.web import services  # noqa: E402
from igea_dgs.web.app import create_app  # noqa: E402
from test_demanda_medida_web import CABECERA, CLIENTES, _subir, _xlsx  # noqa: E402

GUION_FALSO = '''
import argparse, json
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('--plan'); p.add_argument('--output-json'); p.add_argument('--simular', action='store_true')
p.add_argument('--cancel-file')
a = p.parse_args()
# Como el guion real: la primera línea sale con DIgSILENT ya conectado (005:RF-21).
print('Conectado a DIgSILENT como prueba.', flush=True)
plan = json.loads(Path(a.plan).read_text(encoding='utf-8'))
informe = {'modo': 'simular' if a.simular else 'aplicar', 'cuadrado': not a.simular,
           'recibido': plan}
if not a.simular:
    informe.update(sed=[{'sed': 'S1', 'despues': {'kw': 40.0, 'kvar': 9.0}}],
                   escenario='Sin proyecto')
if plan['project'] == 'SIN_KVA':
    informe = {'error': '1 SED sin potencia instalada: S9. Corríjalas antes de ajustar.'}
if plan['project'] == 'FALLA_A1' and plan['feeder'] == 'A1':
    informe = {'error': 'A1 no tiene ElmFeeder con cabecera en el proyecto.'}
if plan['project'] == 'ESPERAR_CANCELACION':
    import time
    limite = time.time() + 20
    while not Path(a.cancel_file).exists() and time.time() < limite:
        time.sleep(0.05)
    informe['cancelado'] = True
Path(a.output_json).write_text(json.dumps(informe), encoding='utf-8')
'''

SUMINISTROS = {'s': [['Suministro', 'Suministro Act', 'SED', 'RADIAL'], [11, 9011, 'E1', 'A1'],
                     [12, 9012, 'E2', 'A2']]}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from igea_dgs.demanda_medida import ClientPeriodEvidence
    from igea_dgs.powerfactory_binding import PowerFactoryProjectBinding

    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    guion = tmp_path / 'ajuste_falso.py'
    guion.write_text(GUION_FALSO, encoding='utf-8')
    monkeypatch.setattr(services, '_require_pf', lambda: (tmp_path, sys.executable))
    monkeypatch.setattr(services, '_script', lambda _nombre: guion)
    monkeypatch.setattr(services, 'pf_subprocess_env', lambda _d: None)
    # Spec 015: el «Caso base» de cada alimentador, verificado.
    monkeypatch.setattr('igea_dgs.powerfactory_binding.caso_base_verificado',
                        lambda _ws, _project, _feeders: {})
    monkeypatch.setattr(
        'igea_dgs.powerfactory_binding.require_project_binding',
        lambda _ws, project, feeders: PowerFactoryProjectBinding(
            project=project, folder='Conversor IGEA-DGS', source_run_id='legacy-test-run',
            source_mode='txt', source_fingerprint='f' * 64, feeders=tuple(feeders),
            dgs_sha256={f: 'd' * 64 for f in feeders}, native_inventory_sha256='n' * 64,
            native_reread={'status': 'VERIFICADO_PERSISTENCIA'}, accepted_at=1.0,
        ),
    )
    monkeypatch.setattr(
        services, 'periodo_clientes_activo',
        lambda ws: ClientPeriodEvidence(
            status='CLIENT_PERIOD_VERIFIED' if ws.demanda.get('clientes') else 'NO_CLIENT_BOOK',
            period='2026-07' if ws.demanda.get('clientes') else None,
            file='clientes-prueba.xlsx' if ws.demanda.get('clientes') else None,
            sheet='resumen', fingerprint='c' * 64 if ws.demanda.get('clientes') else None,
            period_origin='fixture' if ws.demanda.get('clientes') else None,
            warning=None if ws.demanda.get('clientes') else
            'Sin libro de clientes importantes: todas las SED se escalan por kVA.',
        ),
    )
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as c:
        yield c


def _maxima(client, medidores=(('A1', 'M1'),)):
    """Espacio con la cabecera subida y la máxima buscada; devuelve (wid, trabajo)."""
    wid = client.post('/api/workspaces').json()['id']
    r = client.post(f'/api/workspaces/{wid}/demanda/cabecera',
                    files=[('files', ('SISTEMA A.xlsx', _xlsx(CABECERA)))])
    assert r.status_code == 200
    job = client.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json={'medidores': [
        {'alimentador': a, 'medidor': m} for a, m in medidores]}).json()
    estado = esperar_trabajo(client, job)
    assert estado['status'] == 'done', estado
    return wid, job['id']


def _plan(client, wid, job_id, **kw):
    body = {'project': 'P', 'job_id': job_id, **kw}
    return client.post(f'/api/workspaces/{wid}/demanda/ajuste/plan', json=body)


def test_objetivo_es_la_maxima_de_la_tabla(client):
    """006:RF-1 — el objetivo es el kW y el kVAR que dio el trabajo de la máxima."""
    wid, job = _maxima(client)
    r = _plan(client, wid, job)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['feeder'] == 'A1'
    assert body['objetivo']['kw'] == 107.0 and body['objetivo']['kvar'] == 10.0
    assert body['tolerancia'] == 0.01
    assert any('suministros' in a for a in body['avisos'])
    assert any('fuente canónica activa' in a.lower() for a in body['avisos'])


def test_varios_medidores_hay_que_elegir(client):
    """006:RF-2 — con varios medidores no se ajusta hasta elegir el de la cabecera."""
    wid, job = _maxima(client, (('A1', 'M1'), ('A1', 'M2')))
    r = _plan(client, wid, job)
    assert r.status_code == 400 and 'elija el medidor' in r.json()['detail']
    r = _plan(client, wid, job, medidor='M1')
    assert r.status_code == 200 and r.json()['objetivo']['kw'] == 107.0
    # M2 solo trae kW: sin kVAR ni FP no hay objetivo (RF-3).
    assert _plan(client, wid, job, medidor='M2').status_code == 400


def test_medidor_sin_maxima_no_se_ajusta(client):
    """006:RF-3 — un medidor sin máxima no da objetivo."""
    wid, job = _maxima(client, (('A1', 'NO'),))
    r = _plan(client, wid, job)
    assert r.status_code == 400 and 'NO' in r.json()['detail']


def test_trabajo_ajeno_o_inexistente(client):
    """006:RF-1 — solo la máxima buscada en este espacio."""
    wid, job = _maxima(client)
    otro = client.post('/api/workspaces').json()['id']
    assert _plan(client, otro, job).status_code == 404
    assert _plan(client, wid, 'no-existe').status_code == 404


@pytest.mark.parametrize('tol', [0.0, 0.0005, 0.2, -1])
def test_tolerancia_fuera_de_rango(client, tol):
    """006:RF-11 — la tolerancia va del 0,1 % al 10 %; fuera de eso, 422."""
    wid, job = _maxima(client)
    assert _plan(client, wid, job, tolerancia=tol).status_code == 422


def test_clientes_del_alimentador_van_al_plan(client):
    """006:RF-5 — el plan lleva los clientes cruzados de ese alimentador, no los demás."""
    wid, job = _maxima(client)
    _subir(client, wid, 'suministros', SUMINISTROS)
    _subir(client, wid, 'clientes', CLIENTES)
    body = _plan(client, wid, job).json()
    assert body['n_clientes'] == 1
    trabajo = client.post(f"/api/workspaces/{wid}/demanda/ajuste/{body['token']}/simular").json()
    plan = esperar_trabajo(client, trabajo)['result']['informe']['recibido']
    assert [c['codigo'] for c in plan['clientes']] == ['11']


def test_el_plan_lleva_el_fp_de_las_escaladas_del_perfil(client, tmp_path, monkeypatch):
    """015:RF-53 / 015:RF-54 / 015:RF-55 / 015:RF-57 — con el perfil de Electro Dunas el plan
    lleva 0,98 para las escaladas y las fijas siguen con su EA/ERI; sin perfil, nada; con
    un valor imposible no se prepara y se dice cuál."""
    import json as _json

    from igea_dgs.perfil_empresa import VARIABLE_RUTA

    wid, job = _maxima(client)
    _subir(client, wid, 'suministros', SUMINISTROS)
    _subir(client, wid, 'clientes', CLIENTES)

    def plan_recibido():
        token = _plan(client, wid, job).json()['token']
        trabajo = client.post(f'/api/workspaces/{wid}/demanda/ajuste/{token}/simular').json()
        return esperar_trabajo(client, trabajo)['result']['informe']['recibido']

    assert plan_recibido()['factor_potencia_cargas'] is None
    perfil = tmp_path / 'perfil_empresa.json'
    perfil.write_text(_json.dumps({'perfil': 'electro_dunas'}), encoding='utf-8')
    monkeypatch.setenv(VARIABLE_RUTA, str(perfil))
    plan = plan_recibido()
    assert plan['factor_potencia_cargas'] == 0.98
    assert all(d['metodo'] == 'ERI/EA' for f in plan['fixed_load_evidence']
               for d in f['derivaciones']), 'las fijas siguen con su EA/ERI'
    perfil.write_text(_json.dumps({'calibracion': {'factor_potencia_cargas': 1.5}}),
                      encoding='utf-8')
    r = _plan(client, wid, job)
    assert r.status_code >= 400 and 'factor_potencia_cargas' in r.text and '1.5' in r.text


def test_clientes_desmarcados_van_aparte(client):
    """006:RF-26 — el Nis desmarcado no suma a su SED: va al plan en ``desconectados``."""
    wid, job = _maxima(client)
    _subir(client, wid, 'suministros', SUMINISTROS)
    _subir(client, wid, 'clientes', CLIENTES)
    body = _plan(client, wid, job, desconectados=['11']).json()
    assert body['ajustes'][0]['n_clientes'] == 0 and body['ajustes'][0]['n_desconectados'] == 1
    trabajo = client.post(f"/api/workspaces/{wid}/demanda/ajuste/{body['token']}/simular").json()
    plan = esperar_trabajo(client, trabajo)['result']['informe']['recibido']
    assert plan['clientes'] == [] and [c['sed'] for c in plan['desconectados']] == ['E1']


def test_simular_y_aplicar_en_el_carril_de_powerfactory(client):
    """006:RF-19 / 006:RF-20 — trabajos del carril powerfactory con el plan preparado."""
    wid, job = _maxima(client)
    token = _plan(client, wid, job, tolerancia=0.02).json()['token']
    for accion, modo in (('simular', 'simular'), ('aplicar', 'aplicar')):
        trabajo = client.post(f'/api/workspaces/{wid}/demanda/ajuste/{token}/{accion}')
        assert trabajo.status_code == 202 and trabajo.json()['lane'] == 'powerfactory'
        estado = esperar_trabajo(client, trabajo.json())
        assert estado['status'] == 'done', estado
        informe = estado['result']['informe']
        assert informe['modo'] == modo
        assert informe['recibido']['tolerancia'] == 0.02
        assert informe['recibido']['variacion'].startswith('Ajuste_A1_')


def test_error_del_guion_llega_al_operador(client):
    """006:RF-24 — una SED sin kVA: el trabajo falla con el mensaje del guion."""
    wid, job = _maxima(client)
    token = client.post(f'/api/workspaces/{wid}/demanda/ajuste/plan',
                        json={'project': 'SIN_KVA', 'job_id': job}).json()['token']
    estado = esperar_trabajo(client, client.post(
        f'/api/workspaces/{wid}/demanda/ajuste/{token}/aplicar').json())
    assert estado['status'] == 'failed' and 'S9' in estado['error']


def test_plan_del_ajuste_no_sirve_para_cargas(client):
    """006:RF-19 — el token del ajuste no lanza el guion de cargas."""
    wid, job = _maxima(client)
    token = _plan(client, wid, job).json()['token']
    r = client.post(f'/api/workspaces/{wid}/lote/{token}/apply')
    assert r.status_code == 400
    assert client.post(f'/api/workspaces/{wid}/demanda/ajuste/zzz/aplicar').status_code == 404


def test_kva_de_respaldo_desde_la_entrada(client, monkeypatch):
    """006:RF-10 — con la entrada cargada, el plan lleva el kVA de cada SED del modelo."""

    class Sed:
        def __init__(self, code, kva):
            self.code, self.design_kva = code, kva

    class Modelo:
        seds = [Sed('E1', 100.0), Sed('E2', 0.0)]

    class Dataset:
        def feeder_ids(self):
            return ['a-1', 'B2']

    wid, job = _maxima(client)
    store = client.app.state.store
    store.get(wid).dataset = Dataset()
    vistos = []
    monkeypatch.setattr(services, 'build_model',
                        lambda ws, feeder, geography=None: vistos.append(feeder) or Modelo())
    token = _plan(client, wid, job).json()['token']
    estado = esperar_trabajo(client, client.post(
        f'/api/workspaces/{wid}/demanda/ajuste/{token}/simular').json())
    assert vistos == ['a-1'], 'el código del libro casa con el de la entrada sin guiones'
    assert estado['result']['informe']['recibido']['kva_entrada'] == {'E1': 100.0}
    assert json.dumps(estado['result']['informe'])


def test_ajuste_en_la_seccion_de_demanda_medida():
    """006:RF-23 — el ajuste va en «Demanda medida», con el proyecto de la pestaña de
    cargas y la máxima buscada. La interfaz no tiene pruebas de navegador: se comprueba
    en el código que la conexión existe."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'components'
    cargas = (src / 'CargasTab.tsx').read_text(encoding='utf-8')
    demanda = (src / 'DemandaMedida.tsx').read_text(encoding='utf-8')
    ajuste = (src / 'AjusteCabecera.tsx').read_text(encoding='utf-8')
    # Spec 008, RF-7: con los alimentadores marcados en el paso 2.
    assert '<DemandaMedida project={project} feeders={order} />' in cargas
    assert ('<AjusteCabecera project={project} maxima={ultimo} feeders={feeders} '
            'desconectados={desconectados} />') in demanda
    assert 'api.ajustePlan' in ajuste and 'job_id: maxima.id' in ajuste


def test_la_web_muestra_la_validacion_fisica_y_el_balance():
    """015:RF-49 / 015:RF-50 / 015:RF-51 — CA101, 2026-10-15: con FALLO_VALIDACION_NATIVA la
    caja decía «No cumple el 1 %: null. El escenario queda con el último reparto», cuando
    las cargas se habían revertido. Ahora dice que no se grabó nada y enseña el balance
    físico (escrito frente a consumido) y las cargas que no consumen lo suyo."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1] / 'frontend' / 'src'
    ajuste = (raiz / 'components' / 'AjusteCabecera.tsx').read_text(encoding='utf-8')
    tipos = (raiz / 'types.ts').read_text(encoding='utf-8')
    assert "'FALLO_VALIDACION_NATIVA'" in tipos
    assert 'validacion_posterior_nativa?: ValidacionNativa' in tipos
    assert "inf.status === 'FALLO_VALIDACION_NATIVA' || inf.calibracion_revertida" in ajuste
    assert '{!simular && !revertida && (' in ajuste, 'sin «el escenario queda con…» si se revirtió'
    assert 'no se grabó nada' in ajuste
    assert '<BalanceFisico b={validacion.balance} />' in ajuste
    assert 'Consumido en el flujo (kW)' in ajuste and 'Causa probable: {b.causa_probable}' in ajuste
    assert "f.tipo === 'CONSUMO_DISTINTO_DE_LO_ESCRITO'" in ajuste
    assert '<ConsumoDistintoLista cargas={consumoDistinto.cargas} />' in ajuste
    # Los fallos de la validación (con «detalle») no se listan como escrituras rechazadas.
    assert '(inf.fallos ?? []).filter((x) => !x.detalle)' in ajuste
    # 015:RF-66: los bancos a su máxima capacidad, con sus escalones.
    assert 'puesto(s) a su máxima capacidad' in ajuste and 'bancos_puestos_a_maxima?:' in tipos
    # 015:RF-63: los clientes compensados, con FP real y corregido.
    assert 'Clientes fijos compensados por su banco propio' in ajuste
    assert 'FP real (EA/ERI)' in ajuste and 'fijas_compensadas?: {' in tipos
    # 015:RF-59 / 015:RF-60: clientes sobre su transformador y bancos instalados.
    assert 'Clientes que piden más que el transformador de su SED' in ajuste
    assert 'Bancos de condensadores instalados en el proyecto' in ajuste
    assert 'fijas_sobre_su_transformador?: {' in tipos and 'bancos?: {' in tipos
    # 015:RF-56: de dónde sale el factor de potencia de fijas y escaladas.
    assert 'fijas: string; escaladas: number | null; escaladas_origen: string;' in tipos
    # 015:RF-44: el reparto de las escaladas por potencia instalada se dice.
    assert 'repartidas por ${inf.factor_potencia_cargas.escaladas_reparto}' in ajuste
    assert 'Fijas: {inf.factor_potencia_cargas.fijas} · Escaladas:' in ajuste


def test_casilla_por_cliente_marcada_por_defecto():
    """006:RF-25 — la tabla del cruce tiene una casilla por cliente antes del Nis; empieza
    marcada (nadie desconectado) y lo desmarcado llega al plan del ajuste."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'components'
    demanda = (src / 'DemandaMedida.tsx').read_text(encoding='utf-8')
    ajuste = (src / 'AjusteCabecera.tsx').read_text(encoding='utf-8')
    assert '<th>Conectado</th><th>Nis / Suministro</th>' in demanda
    assert 'checked={!desconectados.has(c.codigo)}' in demanda
    assert 'setDesconectados(new Set())' in demanda, 'un cruce nuevo empieza todo marcado'
    assert 'desconectados: [...desconectados]' in ajuste


# ----------------------------------------------------------------- spec 008
# Dos alimentadores, cada uno con su medidor de cabecera con kW y kVAR.
CABECERA_DOS = {
    'M1': CABECERA['M1'],
    'M3': [['Local Time', 'kVAR tot', 'kW tot']] + [[r[0], 20.0, 200.0 + i] for i, r in enumerate(CABECERA['M1'][1:])],
}


def _maxima_dos(client, medidores=(('A1', 'M1'), ('A2', 'M3'))):
    wid = client.post('/api/workspaces').json()['id']
    r = client.post(f'/api/workspaces/{wid}/demanda/cabecera',
                    files=[('files', ('SISTEMA B.xlsx', _xlsx(CABECERA_DOS)))])
    assert r.status_code == 200, r.text
    job = client.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json={'medidores': [
        {'alimentador': a, 'medidor': m} for a, m in medidores]}).json()
    assert esperar_trabajo(client, job)['status'] == 'done'
    return wid, job['id']


def test_varios_alimentadores_en_un_trabajo(client):
    """008:RF-10 / 008:RF-12 / 008:RF-16 — un plan por alimentador, ajustados uno tras otro en
    un solo trabajo, cada uno en su variación, con un informe por alimentador."""
    wid, job = _maxima_dos(client)
    r = _plan(client, wid, job)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['feeders'] == ['A1', 'A2']
    assert [a['objetivo']['medidor'] for a in body['ajustes']] == ['M1', 'M3']
    trabajo = client.post(f"/api/workspaces/{wid}/demanda/ajuste/{body['token']}/aplicar").json()
    assert trabajo['title'].startswith('Ajustar 2 alim.')
    estado = esperar_trabajo(client, trabajo)
    assert estado['status'] == 'done', estado
    informes = estado['result']['informes']
    assert [i['recibido']['feeder'] for i in informes] == ['A1', 'A2']
    variaciones = [i['recibido']['variacion'] for i in informes]
    assert variaciones[0].startswith('Ajuste_A1_') and variaciones[1].startswith('Ajuste_A2_')
    assert len(estado['result']['reports']) == 2


def test_orden_y_eleccion_de_los_medidores(client):
    """008:RF-12 / 008:RF-13 — ``medidores`` fija cuáles y en qué orden; dos medidores de un
    mismo alimentador piden elegir."""
    wid, job = _maxima_dos(client)
    body = _plan(client, wid, job, medidores=['M3', 'M1']).json()
    assert body['feeders'] == ['A2', 'A1']
    assert _plan(client, wid, job, medidores=['M3']).json()['feeders'] == ['A2']
    assert _plan(client, wid, job, medidores=['M9']).status_code == 400
    wid, job = _maxima_dos(client, (('A1', 'M1'), ('A1', 'M3')))
    r = _plan(client, wid, job)
    assert r.status_code == 400 and 'A1 tiene M1, M3' in r.json()['detail']
    assert _plan(client, wid, job, medidores=['M3']).json()['feeders'] == ['A1']


def test_un_medidor_sin_maxima_no_para_los_demas(client):
    """008:RF-14 — con varios alimentadores, el que no tiene objetivo se avisa y se ajustan los demás."""
    wid, job = _maxima_dos(client, (('A1', 'M1'), ('A2', 'NO')))
    body = _plan(client, wid, job).json()
    assert body['feeders'] == ['A1']
    assert any(a.startswith('A2: no se ajusta') for a in body['avisos'])


def test_un_ajuste_que_falla_no_para_el_siguiente(client):
    """008:RF-14 — el error de un alimentador queda en su informe y el siguiente se ajusta."""
    wid, job = _maxima_dos(client)
    token = _plan(client, wid, job, project='FALLA_A1').json()['token']
    estado = esperar_trabajo(client, client.post(
        f'/api/workspaces/{wid}/demanda/ajuste/{token}/aplicar').json())
    assert estado['status'] == 'done', estado
    a1, a2 = estado['result']['informes']
    assert 'ElmFeeder' in a1['error'] and a1['feeder'] == 'A1'
    assert 'error' not in a2 and a2['recibido']['feeder'] == 'A2'


def test_cancelar_no_empieza_otro_alimentador(client):
    """008:RF-15 — cancelar termina el alimentador en curso y no empieza el siguiente."""
    import time

    wid, job = _maxima_dos(client)
    token = _plan(client, wid, job, project='ESPERAR_CANCELACION').json()['token']
    trabajo = client.post(f'/api/workspaces/{wid}/demanda/ajuste/{token}/aplicar').json()
    limite = time.time() + 20
    # Se cancela con el guion ya conectado: antes de conectar no hay alimentador en curso
    # que terminar y cancelar lo corta sin más (005:RF-21).
    def conectado() -> bool:
        return any('Conectado a DIgSILENT' in (e['data'].get('text') or '')
                   for e in client.get(f'/api/workspaces/{wid}/events').json())

    while time.time() < limite and not conectado():
        time.sleep(0.05)
    time.sleep(0.5)
    client.post(f"/api/jobs/{trabajo['id']}/cancel")
    estado = esperar_trabajo(client, trabajo)
    assert estado['status'] == 'cancelled'
    a1, a2 = estado['result']['informes']
    assert a1['cancelado'] and 'recibido' in a1, 'A1 terminó con su informe'
    assert a2['no_empezado'] and a2['feeder'] == 'A2'


def test_sin_caso_base_verificado_no_se_calibra(client, monkeypatch):
    """015:RF-13, 015:RF-15 — un alimentador sin «Caso base» verificado no se calibra; con
    varios, los demás sí, y el que queda fuera se dice."""
    monkeypatch.setattr('igea_dgs.powerfactory_binding.caso_base_verificado',
                        lambda _ws, _project, feeders: {f: ['flujo'] for f in feeders if f == 'A1'})
    wid, job = _maxima(client)
    r = _plan(client, wid, job)
    assert r.status_code == 400 and 'no está verificado' in r.json()['detail']
    wid, job = _maxima_dos(client)
    r = _plan(client, wid, job, medidores=['M3', 'M1'])
    assert r.status_code == 200, r.text
    assert r.json()['feeders'] == ['A2']
    assert any('A1' in a and 'no está verificado' in a for a in r.json()['avisos'])


def test_la_calibracion_aplicada_queda_en_el_espacio_y_viaja_en_el_plan(client):
    """014:RF-10 / 015:RF-26 — la demanda que dejó la calibración se guarda en el espacio y
    el plan siguiente la manda al guion, para ver lo que el operador cambió a mano."""
    wid, job = _maxima(client)
    token = _plan(client, wid, job).json()['token']
    estado = esperar_trabajo(client, client.post(
        f'/api/workspaces/{wid}/demanda/ajuste/{token}/aplicar').json())
    assert estado['status'] == 'done', estado
    ws = client.app.state.store.get(wid)
    guardada = ws.calibraciones['P']['A1']
    assert guardada['sed'] == {'S1': [40.0, 9.0]} and guardada['escenario'] == 'Sin proyecto'
    assert 'fijas' in guardada, '015:RF-65: las fijas con su FP real y corregido, para el informe'
    token = _plan(client, wid, job).json()['token']
    plan = json.loads(Path(ws.cargas_planes[token]['path']).read_text(encoding='utf-8'))
    assert plan['ultima_calibracion']['sed'] == {'S1': [40.0, 9.0]}
    assert plan['caso_base_sin_verificar'] == {}


@pytest.mark.parametrize('proyecto', ['P', 'FALLA_A1'])
def test_calibrar_no_cambia_el_estado_del_caso_base(client, proyecto):
    """015:RF-22, 015:RF-24 — ni una calibración que cuadra ni una que falla cambian el
    estado verificado del «Caso base» en el vínculo."""
    wid, job = _maxima(client)
    ws = client.app.state.store.get(wid)
    vinculo = {'project': proyecto, 'feeders': ['A1'], 'native_reread': {
        'status': 'VERIFICADO_PERSISTENCIA',
        'caso_base': {'A1': {'status': 'VERIFICADO', 'fallos': []}}}}
    ws.pf_project_bindings[proyecto] = json.loads(json.dumps(vinculo))
    token = _plan(client, wid, job, project=proyecto).json()['token']
    esperar_trabajo(client, client.post(
        f'/api/workspaces/{wid}/demanda/ajuste/{token}/aplicar').json())
    assert ws.pf_project_bindings[proyecto] == vinculo


def test_la_calibracion_guarda_las_fijas_con_fp_real_y_corregido(tmp_path):
    """015:RF-65 — lo que la calibración deja en el espacio para el informe: por cliente, el FP
    real de su EA/ERI y el corregido, y si se supone compensado por su banco propio."""
    from igea_dgs.web.workspace import Workspace

    ws = Workspace(id='w', root=tmp_path / 'ws')
    informe = {'cuadrado': True, 'escenario': 'Sin proyecto', 'sed': [
        {'sed': 'SE1', 'despues': {'kw': 100.0, 'kvar': 20.3}, 'derivaciones': [
            {'cliente': 'C1', 'p_kw': 100.0, 'q_kvar': 20.3, 'fp': 0.98,
             'compensado': {'fp_ea_eri': 0.43, 'fp_escrito': 0.98, 'q_ea_eri_kvar': 210.0,
                            'q_escrita_kvar': 20.3}}]},
        {'sed': 'SE2', 'despues': {'kw': 50.0, 'kvar': 5.0}, 'derivaciones': []}]}
    services._guardar_calibracion(ws, 'P', 'A1', informe)
    (fija,) = ws.calibraciones['P']['A1']['fijas']
    assert fija == {'sed': 'SE1', 'cliente': 'C1', 'p_kw': 100.0, 'fp_real': 0.43,
                    'fp_corregido': 0.98, 'q_real_kvar': 210.0, 'q_kvar': 20.3,
                    'compensado': True}
