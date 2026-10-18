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
p.add_argument('--plan', action='append'); p.add_argument('--output-json', action='append')
p.add_argument('--simular', action='store_true'); p.add_argument('--cancel-file')
a = p.parse_args()
# Como el guion real: la primera línea sale con DIgSILENT ya conectado (005:RF-21).
print('Conectado a DIgSILENT como prueba.', flush=True)
# 021:RF-54: un proceso con todos los planes del proyecto.
for ruta_plan, ruta_salida in zip(a.plan, a.output_json):
  plan = json.loads(Path(ruta_plan).read_text(encoding='utf-8'))
  informe = {'modo': 'simular' if a.simular else 'aplicar', 'cuadrado': not a.simular,
             'recibido': plan}
  if not a.simular:
      informe.update(sed=[{'sed': 'S1', 'despues': {'kw': 40.0, 'kvar': 9.0}}],
                     escenario='Sin proyecto', escenarios=[{'escenario': 'Sin proyecto'}])
  if plan['project'] == 'SOBRE':
      # Spec 020: una fija sobrecargada con propuesta (S1) y otra sin ella (S2).
      informe['fijas_sobre_su_transformador'] = [
          {'sed': 'S1', 'carga_pct': 306.0, 'transformadores': [{'transformador': 'TR_S1'}],
           'propuesta': {'kva': 400, 'unidades': 1, 'tipo_nuevo': 'TR_400kVA_X_10-380V_DYN11'}},
          {'sed': 'S2', 'carga_pct': 150.0, 'transformadores': [],
           'propuesta': {'kva': None, 'motivo': 'la SED no tiene transformador en DIgSILENT'}}]
      if plan.get('transformadores'):
          informe['transformadores_implementados'] = {'cambios': plan['transformadores'],
                                                      'omitidas': []}
          informe['fijas_sobre_su_transformador'] = informe['fijas_sobre_su_transformador'][1:]
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
  Path(ruta_salida).write_text(json.dumps(informe), encoding='utf-8')
  informe_listo = True
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
        seds = [Sed('E1', 200.0), Sed('E2', 0.0)]

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
    assert estado['result']['informe']['recibido']['kva_entrada'] == {'E1': 200.0}
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
    # Con la central térmica de cada alimentador (spec 021, RF-25).
    assert ('<AjusteCabecera project={project} maxima={ultimo} feeders={feeders} '
            'desconectados={desconectados}\n        centrales={') in demanda
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
    # 015:RF-59 / 015:RF-60: clientes sobre su transformador (desde la 020, al principio del
    # resultado) y bancos instalados.
    assert 'piden más que su potencia instalada' in ajuste
    assert 'Bancos de condensadores instalados en el proyecto' in ajuste
    assert 'fijas_sobre_su_transformador?: SedSobrecargada[]' in tipos and 'bancos?: {' in tipos
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
    """008:RF-10 / 008:RF-16 / 021:RF-54 — un plan por alimentador, todos en una sola
    ejecución del guion (calibrados a la vez), con un informe por alimentador."""
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
    """008:RF-14, 021:RF-57 — el error de un alimentador queda en su informe y el otro se ajusta."""
    wid, job = _maxima_dos(client)
    token = _plan(client, wid, job, project='FALLA_A1').json()['token']
    estado = esperar_trabajo(client, client.post(
        f'/api/workspaces/{wid}/demanda/ajuste/{token}/aplicar').json())
    assert estado['status'] == 'done', estado
    a1, a2 = estado['result']['informes']
    assert 'ElmFeeder' in a1['error'] and a1['feeder'] == 'A1'
    assert 'error' not in a2 and a2['recibido']['feeder'] == 'A2'


def test_cancelar_termina_el_proyecto(client):
    """021:RF-58 (cambia 008:RF-15) — los dos alimentadores van en una sola ejecución:
    cancelar la termina y los dos quedan cancelados con su informe."""
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
    assert a1['cancelado'] and a2['cancelado'] and 'recibido' in a2


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
    informe = {'cuadrado': True, 'escenario': 'Sin proyecto',
               'escenarios': [{'escenario': 'Sin proyecto'}], 'sed': [
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


# --------------------------------------------------------------------------- spec 020
def test_el_plan_lleva_las_fichas_de_transformadores_del_perfil(client, tmp_path, monkeypatch):
    """020:RF-6 / 020:RF-10 — con el perfil de Electro Dunas el plan lleva sus tablas de fichas;
    sin perfil, ninguna (el guion lo dice sin propuesta)."""
    import json as _json

    from igea_dgs.perfil_empresa import VARIABLE_RUTA

    wid, job = _maxima(client)
    monkeypatch.setenv(VARIABLE_RUTA, str(tmp_path / 'no_existe.json'))
    token = _plan(client, wid, job).json()['token']
    ws = client.app.state.store.get(wid)
    plan = json.loads(Path(ws.cargas_planes[token]['path']).read_text(encoding='utf-8'))
    assert plan['transformadores_sed'] is None
    perfil = tmp_path / 'perfil_empresa.json'
    perfil.write_text(_json.dumps({'perfil': 'electro_dunas'}), encoding='utf-8')
    monkeypatch.setenv(VARIABLE_RUTA, str(perfil))
    token = _plan(client, wid, job).json()['token']
    plan = json.loads(Path(ws.cargas_planes[token]['path']).read_text(encoding='utf-8'))
    assert plan['transformadores_sed']['umbral_carga_pct'] == 80
    assert len(plan['transformadores_sed']['tablas']) == 2


def _simulado(client, proyecto='SOBRE'):
    wid, job = _maxima(client)
    token = client.post(f'/api/workspaces/{wid}/demanda/ajuste/plan',
                        json={'project': proyecto, 'job_id': job}).json()['token']
    estado = esperar_trabajo(client, client.post(
        f'/api/workspaces/{wid}/demanda/ajuste/{token}/simular').json())
    assert estado['status'] == 'done', estado
    return wid, token


def test_implementar_transformadores_en_el_carril_y_recalibra(client):
    """020:RF-15 / 020:RF-25 / 020:RF-28 — el botón lanza un trabajo de DIgSILENT con la propuesta
    del último ajuste (no la del navegador), que aplica y recalibra con el mismo plan; la
    calibración queda registrada como la del alimentador."""
    wid, token = _simulado(client)

    r = client.post(f'/api/workspaces/{wid}/demanda/ajuste/{token}/transformadores',
                    json={'feeder': 'A1', 'sed': ['S1']})

    assert r.status_code == 202 and r.json()['lane'] == 'powerfactory'
    assert r.json()['kind'] == 'ajuste_transformadores'
    estado = esperar_trabajo(client, r.json())
    assert estado['status'] == 'done', estado
    informe = estado['result']['informe']
    recibido = informe['recibido']
    assert informe['modo'] == 'aplicar' and recibido['variacion'].startswith('Ajuste_A1_')
    (c,) = recibido['transformadores']
    assert c == {'sed': 'S1', 'transformador': 'TR_S1',
                 'propuesta': {'kva': 400, 'unidades': 1,
                               'tipo_nuevo': 'TR_400kVA_X_10-380V_DYN11'}}
    assert informe['transformadores_implementados']['cambios'] == [c]
    ws = client.app.state.store.get(wid)
    assert ws.calibraciones['SOBRE']['A1']['sed'] == {'S1': [40.0, 9.0]}
    assert (ws.out_dir / f'ajuste_cabecera_aplicacion_{token}.json').is_file()


@pytest.mark.parametrize('sed, texto', [([], 'al menos una SED'), (['S2'], 'S2'),
                                         (['S9'], 'S9')])
def test_sin_sed_o_sin_propuesta_no_se_encola(client, sed, texto):
    """020:RF-13 / 020:RF-14 — sin SED marcadas, o con una sin propuesta, se dice en el acto y no
    hay trabajo."""
    wid, token = _simulado(client)
    r = client.post(f'/api/workspaces/{wid}/demanda/ajuste/{token}/transformadores',
                    json={'feeder': 'A1', 'sed': sed})
    assert r.status_code == 400 and texto in r.text


def test_implementar_sin_ajuste_previo_se_rechaza(client):
    """020:RF-13 — la propuesta sale del ajuste: sin simular ni aplicar no hay qué implementar."""
    wid, job = _maxima(client)
    token = client.post(f'/api/workspaces/{wid}/demanda/ajuste/plan',
                        json={'project': 'SOBRE', 'job_id': job}).json()['token']
    r = client.post(f'/api/workspaces/{wid}/demanda/ajuste/{token}/transformadores',
                    json={'feeder': 'A1', 'sed': ['S1']})
    assert r.status_code == 400 and 'simule o aplique' in r.text


def test_la_web_avisa_de_las_sed_sobrecargadas_y_propone_transformadores():
    """020:RF-3 / 020:RF-4 / 020:RF-9 / 020:RF-13 / 020:RF-14 — PA217, 2026-10-16: SE30940 al 955 % solo
    se veía en un desplegable. Ahora va al principio del resultado, dice si es la causa
    probable, enseña la propuesta por SED con su ficha y una casilla marcada, y el botón
    queda desactivado sin casillas."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1] / 'frontend' / 'src'
    ajuste = (raiz / 'components' / 'AjusteCabecera.tsx').read_text(encoding='utf-8')
    tipos = (raiz / 'types.ts').read_text(encoding='utf-8')
    api = (raiz / 'api.ts').read_text(encoding='utf-8')
    cargas = (raiz / 'components' / 'CargasTab.tsx').read_text(encoding='utf-8')
    # RF-3: al principio del resultado, antes del texto de la simulación y del de fallo.
    pos = ajuste.index('<SedSobrecargadas inf={inf} token={token} />')
    assert pos < ajuste.index('Nada se ha escrito en el proyecto')
    assert pos < ajuste.index('La validación física en DIgSILENT no pasa')
    # RF-4: la causa probable.
    assert 'inf.sobrecarga_causa_probable' in ajuste and 'Es la causa probable' in ajuste
    assert 'sobrecarga_causa_probable?: boolean' in tipos
    # RF-9: la propuesta con su ficha y la carga prevista.
    for texto in ('Propuesta', 'Po / Pc (W)', 'Io / uk (%)', 'Carga prevista', 'p!.norma',
                  'Sin propuesta: {p?.motivo'):
        assert texto in ajuste, texto
    assert 'tipo_nuevo?: string' in tipos and 'carga_pct_prevista?: number' in tipos
    # RF-13: una casilla por SED con propuesta, todas marcadas al principio.
    assert 'new Set(conPropuesta.map((x) => x.sed))' in ajuste
    assert 'type="checkbox"' in ajuste and 'Implementar transformadores' in ajuste
    # RF-14: el botón sin casillas, desactivado.
    assert "!marcadas.size ? 'Marque al menos una SED.'" in ajuste
    assert 'disabled={Boolean(motivoBoton)}' in ajuste
    # RF-15, RF-28: un trabajo; su resultado se ve y hace de base.
    assert 'api.ajusteTransformadores(ws.id, token, inf.feeder, [...marcadas])' in ajuste
    assert '/transformadores`' in api
    assert "j.kind === 'ajuste_transformadores'" in ajuste
    assert cargas.count("j.kind === 'ajuste_transformadores'") == 2


def test_la_web_dice_lo_que_dejaron_los_transformadores():
    """020:RF-24 / 020:RF-26 / 020:RF-32 — antes y después por SED y si la recalibración salió válida."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1] / 'frontend' / 'src'
    ajuste = (raiz / 'components' / 'AjusteCabecera.tsx').read_text(encoding='utf-8')
    assert '<TransformadoresImplementados inf={inf} />' in ajuste
    assert 'La calibración salió válida con ellos.' in ajuste
    assert 'Se quedan, pero no salió: ${r.motivos.join' in ajuste
    assert 'falta calibrar' in ajuste


# ---------------------------------------------------------------- spec 021: central térmica
CENTRAL = {'generacion': 'CG', 'llegada': 'CL', 'salida': 'CS', 'nodo': 'B5'}


def _maxima_con_central(client):
    """A1 con su central: los tres medidores en el mismo trabajo de la máxima (021:RF-25)."""
    from test_demanda_medida_web import _libros_con_central

    wid = client.post('/api/workspaces').json()['id']
    _libros_con_central(client, wid)
    job = client.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json={'medidores': [
        {'alimentador': 'A1', 'medidor': 'M1'}] + [
        {'alimentador': 'Central A1', 'medidor': m} for m in ('CG', 'CL', 'CS')]}).json()
    estado = esperar_trabajo(client, job)
    assert estado['status'] == 'done', estado
    return wid, job['id']


def _recibido(client, wid, token):
    trabajo = client.post(f'/api/workspaces/{wid}/demanda/ajuste/{token}/simular')
    estado = esperar_trabajo(client, trabajo.json())
    assert estado['status'] == 'done', estado
    return estado['result']['informe']['recibido']


def test_el_plan_lleva_la_central_y_su_maxima_de_demanda(client):
    """021:RF-25, 021:RF-33, 021:RF-35 — con la central declarada, el plan lleva su barra, sus
    medidores y la máxima de demanda (zonas y generación), no la de cabecera."""
    wid, job = _maxima_con_central(client)
    r = _plan(client, wid, job, medidores=['M1'], centrales={'A1': CENTRAL})
    assert r.status_code == 200, r.text
    plan = _recibido(client, wid, r.json()['token'])
    c = plan['central']
    assert c['nodo'] == 'B5' and c['medidores'] == {'generacion': 'CG', 'llegada': 'CL', 'salida': 'CS'}
    assert c['maxima']['fecha'] == '2026-07-01 02:45:00'
    assert (c['maxima']['arriba_kw'], c['maxima']['abajo_kw']) == (811.0, 6100.0)
    assert c['maxima']['generacion_kw'] == 6000.0


def test_sin_la_barra_de_la_central_no_hay_plan(client):
    """021:RF-25 — sin la barra de la central en DIgSILENT, se pide."""
    wid, job = _maxima_con_central(client)
    r = _plan(client, wid, job, medidores=['M1'], centrales={'A1': {**CENTRAL, 'nodo': ''}})
    assert r.status_code == 400 and 'barra de la central' in r.json()['detail']


def test_con_el_balance_roto_se_calibra_sin_la_central(client):
    """021:RF-30 — si los medidores no cuadran el balance de la barra, se avisa y el plan
    va sin la central."""
    wid, job = _maxima_con_central(client)
    r = _plan(client, wid, job, medidores=['M1'], centrales={'A1': {**CENTRAL, 'llegada': 'CS'}})
    assert r.status_code == 200, r.text
    assert any('central no usada' in a and 'balance' in a for a in r.json()['avisos'])
    assert 'central' not in _recibido(client, wid, r.json()['token'])


def test_sin_central_el_plan_no_cambia(client):
    """021:RF-46 — sin centrales declaradas, el plan es el de siempre."""
    wid, job = _maxima(client)
    assert 'central' not in _recibido(client, wid, _plan(client, wid, job).json()['token'])


def test_plan_coincidente_con_la_cabecera_negativa(client):
    """021:RF-50, 021:RF-51 — en el registro coincidente la cabecera de A1 es negativa (la
    central exporta hacia la SET, como NA205 el 2026-07-23 10:00): el plan sigue, con la
    demanda del alimentador como objetivo y las zonas de ese registro."""
    from test_demanda_medida_web import _libros_con_central

    wid = client.post('/api/workspaces').json()['id']
    _libros_con_central(client, wid)
    job = client.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json={
        'medidores': [{'alimentador': 'A1', 'medidor': 'M1'}] + [
            {'alimentador': 'Central A1', 'medidor': m} for m in ('CG', 'CL', 'CS')],
        'instante': '2026-07-01T00:15:00'}).json()
    estado = esperar_trabajo(client, job)
    fila = next(r for r in estado['result']['resultados'] if r['medidor'] == 'M1')
    assert fila['kw'] < 0, 'la cabecera exporta en ese registro'
    r = _plan(client, wid, job['id'], medidores=['M1'], centrales={'A1': CENTRAL})
    assert r.status_code == 200, r.text
    plan = _recibido(client, wid, r.json()['token'])
    assert plan['objetivo']['kw'] == pytest.approx(801.0 + 5100.0)
    assert plan['central']['maxima']['coincidente'] is True
    assert plan['central']['maxima']['fecha'] == '2026-07-01 00:15:00'


def test_tension_en_la_fuente_va_en_el_plan(client):
    """021:RF-61, 021:RF-63 — la tensión en la fuente que indica el operador va en el plan;
    sin ella, None; fuera de 0,9 a 1,1 pu, se rechaza."""
    wid, job = _maxima(client)
    token = _plan(client, wid, job, tension_fuente_pu=1.05).json()['token']
    assert _recibido(client, wid, token)['tension_fuente_pu'] == 1.05
    assert _recibido(client, wid, _plan(client, wid, job).json()['token'])['tension_fuente_pu'] is None
    assert _plan(client, wid, job, tension_fuente_pu=1.2).status_code == 422


def test_poner_los_bancos_que_falten_va_en_el_plan(client, monkeypatch):
    """021:RF-64, 021:RF-65 — la casilla va en el plan con el tamaño por tensión del
    perfil; sin marcarla, el plan no lo pide."""
    monkeypatch.setattr(services, 'datos_perfil', lambda: {'calibracion': {
        'bancos_kvar_por_tension': {'10': 300, '22.9': 450}}}, raising=False)
    monkeypatch.setattr('igea_dgs.perfil_empresa.datos_perfil', lambda: {'calibracion': {
        'bancos_kvar_por_tension': {'10': 300, '22.9': 450}}})
    wid, job = _maxima(client)
    plan = _recibido(client, wid, _plan(client, wid, job, completar_bancos=True).json()['token'])
    assert plan['completar_bancos'] is True
    assert plan['bancos_kvar_por_tension'] == {'10.0': 300.0, '22.9': 450.0}
    plan = _recibido(client, wid, _plan(client, wid, job).json()['token'])
    assert plan['completar_bancos'] is False and plan['bancos_kvar_por_tension'] == {}


def test_solo_se_registra_la_calibracion_guardada(tmp_path):
    """014:RF-10, 015:RF-49 — una calibración cuyo escenario no se guardó (no pasó la
    validación física) no se registra: en NA205 (2026-10-17) dejó 93 cargas «cambiadas a
    mano» en la siguiente."""
    from igea_dgs.web.workspace import Workspace

    ws = Workspace(id='w', root=tmp_path / 'ws')
    sed = [{'sed': 'SE1', 'despues': {'kw': 100.0, 'kvar': 20.0}}]
    services._guardar_calibracion(ws, 'P', 'A1', {'cuadrado': False, 'status': 'FALLO_VALIDACION_NATIVA',
                                                  'escenario': 'Sin proyecto', 'sed': sed})
    assert 'A1' not in ws.calibraciones.get('P', {})
    services._guardar_calibracion(ws, 'P', 'A1', {
        'cuadrado': True, 'sed': sed,
        'decision_carga_nativa': {'status': 'YA_CARGADO_VALIDADO'}})
    assert ws.calibraciones['P']['A1']['sed'] == {'SE1': [100.0, 20.0]}


def test_el_plan_lleva_la_barra_de_set_de_cada_alimentador(client, monkeypatch):
    """022:RF-41, 022:RF-41b, 022:RF-44 — con la máxima por barra, el plan de cada
    alimentador lleva su barra de SET (medida, fecha y central) y su objetivo es el de esa
    fecha; el que no tiene barra con medidor, ninguna."""
    from test_demanda_medida_web import _libros_por_barra

    wid = client.post('/api/workspaces').json()['id']
    _libros_por_barra(client, wid, monkeypatch)
    job = client.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json={
        'medidores': [{'alimentador': a, 'medidor': m} for a, m in (('A1', 'M1'), ('A2', 'M3'), ('B1', 'M4'))],
        'por_barra': True}).json()
    estado = esperar_trabajo(client, job)
    assert estado['status'] == 'done', estado
    r = _plan(client, wid, job['id'], medidores=['M1', 'M3', 'M4'])
    assert r.status_code == 200, r.text
    token = r.json()['token']
    trabajo = client.post(f'/api/workspaces/{wid}/demanda/ajuste/{token}/simular').json()
    informes = esperar_trabajo(client, trabajo)['result']['informes']
    planes = {i['recibido']['feeder']: i['recibido'] for i in informes}
    assert planes['A1']['barra_set']['clave'] == planes['A2']['barra_set']['clave'] == 'SET X 10 kV'
    assert planes['A1']['barra_set']['centrales'][0]['medidor'] == 'CT_X'
    assert planes['A1']['objetivo']['fecha'] == planes['A1']['barra_set']['fecha']
    assert planes['B1']['barra_set'] is None


def test_proyecto_por_sistema_calibra_todos_y_dice_los_sin_medidor(client):
    """022:RF-52 / 022:RF-53 / 022:RF-54 — en un proyecto convertido por sistema eléctrico,
    los alimentadores con medidor se calibran a la vez y los que no tienen se dicen en el
    plan y en el resultado (Nasca, 2026-10-18: 15 de 17 sin medidor)."""
    wid, job = _maxima_dos(client)
    ws = client.app.state.store.get(wid)
    ws.groups['SISTEMA_X'] = {'tipo': 'sistema', 'feeders': ['A1', 'A2', 'B9'], 'status': 'ok'}
    ws.pf_projects['SISTEMA_X'] = 'P'
    sistema = client.get(f'/api/workspaces/{wid}/demanda/sistema', params={'project': 'P'}).json()
    assert sistema['sistema']['grupo'] == 'SISTEMA_X'
    assert sistema['sistema']['alimentadores'] == ['A1', 'A2', 'B9']
    assert client.get(f'/api/workspaces/{wid}/demanda/sistema',
                      params={'project': 'OTRO'}).json() == {'sistema': None}
    body = _plan(client, wid, job).json()
    assert body['feeders'] == ['A1', 'A2']
    assert body['sistema']['calibrados'] == ['A1', 'A2']
    assert body['sistema']['sin_medidor'] == ['B9']
    assert any('B9' in a and '022:RF-53' in a for a in body['avisos'])
    estado = esperar_trabajo(client, client.post(
        f"/api/workspaces/{wid}/demanda/ajuste/{body['token']}/aplicar").json())
    assert estado['status'] == 'done', estado
    assert estado['result']['sistema']['sin_medidor'] == ['B9']


def test_medida_por_encima_de_lo_que_da_la_red_no_se_calibra(client, monkeypatch):
    """022:RF-55 — un alimentador cuyo medidor da más que sus fijas y su kVA instalado por el
    FP no se calibra; con varios, se dice y se calibran los demás (Chincha, 2026-10-18:
    TM106, 3 133 kW con unos 230 kVA)."""
    def kva(_ws, alimentador):
        return ({'S1': 50.0}, '') if alimentador == 'A1' else ({'S2': 900.0}, '')

    monkeypatch.setattr(services, '_kva_de_la_entrada', kva)
    assert services._capacidad_de_la_red({'S1': 50.0, 'S2': 100.0}, {}, 0.98) == pytest.approx(147.0)
    assert services._capacidad_de_la_red({}, {}, 0.98) is None
    wid, job = _maxima(client)
    r = _plan(client, wid, job)
    assert r.status_code == 400 and '022:RF-55' in r.json()['detail']
    wid, job = _maxima_dos(client)
    body = _plan(client, wid, job).json()
    assert body['feeders'] == ['A2']
    assert any(a.startswith('A1: su medidor da') and '022:RF-55' in a for a in body['avisos'])


def test_transformadores_de_varios_alimentadores_en_un_trabajo(client):
    """022:RF-62 — ``por_alimentador`` lleva las SED de cada alimentador y se recalibra una
    sola vez; un alimentador sin nombre se rechaza."""
    wid, token = _simulado(client)
    r = client.post(f'/api/workspaces/{wid}/demanda/ajuste/{token}/transformadores',
                    json={'por_alimentador': {'': ['S1']}})
    assert r.status_code == 422
    r = client.post(f'/api/workspaces/{wid}/demanda/ajuste/{token}/transformadores',
                    json={'por_alimentador': {'A1': ['S1']}})
    assert r.status_code == 202, r.text
    estado = esperar_trabajo(client, r.json())
    assert estado['status'] == 'done', estado
    assert [c['sed'] for c in estado['result']['informe']['recibido']['transformadores']] == ['S1']


def test_kva_del_alimentador_reconstruido(client, monkeypatch, tmp_path):
    """022:RF-63 — en un proyecto por sistema reconstruido, el kVA de cada alimentador es el
    de las SED que le asigna el DGS: A1 recibe S2 de A2 y ya puede dar su medida (TM106 y
    TM104 en Chincha, 2026-10-18)."""
    kva = {'A1': {'S1': 50.0}, 'A2': {'S2': 900.0, 'S3': 10.0}}
    monkeypatch.setattr(services, '_kva_de_la_entrada', lambda _ws, f: (dict(kva.get(f, {})), ''))
    wid, job = _maxima(client)
    ws = client.app.state.store.get(wid)
    (tmp_path / 'S_manifest.json').write_text(json.dumps({'estructura': {'reconstrucciones': [
        {'alimentador': 'A1', 'donante': 'A2', 'cargas_pasadas': 1}]}}), encoding='utf-8')
    (tmp_path / 'S_meta.json').write_text(json.dumps({'assignments': [
        {'class_name': 'ElmSubstat', 'substation': 'S1', 'feeder': 'A1'},
        {'class_name': 'ElmSubstat', 'substation': 'S2', 'feeder': 'A1'},
        {'class_name': 'ElmSubstat', 'substation': 'S3', 'feeder': 'A2'}]}), encoding='utf-8')
    ws.groups['S'] = {'tipo': 'sistema', 'feeders': ['A1', 'A2'], 'status': 'ok',
                      'dgs': str(tmp_path / 'S.dgs'), 'feeder_metadata': str(tmp_path / 'S_meta.json')}
    ws.pf_projects['S'] = 'P'
    assert services._kva_reconstruido(ws, 'P', 'A1', kva['A1']) == (
        {'S1': 50.0, 'S2': 900.0}, {'A1', 'A2'})
    assert services._kva_reconstruido(ws, 'P', 'A2', kva['A2']) == ({'S3': 10.0}, {'A1', 'A2'})
    assert services._kva_reconstruido(ws, 'OTRO', 'A1', kva['A1']) == ({'S1': 50.0}, set())
    # El donante que lo cedió todo no puede dar nada: su medida no se calibra (TM104).
    assert services._capacidad_de_la_red({}, {}, 0.98, reconstruido=True) == 0.0
    # Sus fijas del libro de suministros ya no son suyas si su SED pasó al otro.
    fija = type('F', (), {'kw': 500.0})()
    assert services._capacidad_de_la_red({}, {'S9': fija}, 0.98, reconstruido=True) == 0.0
    assert services._capacidad_de_la_red({'S9': 10.0}, {'S9': fija}, 0.98, reconstruido=True) == 500.0
    assert services._capacidad_de_la_red({}, {}, 0.98) is None
    body = _plan(client, wid, job).json()
    assert body.get('feeders') == ['A1'], body
