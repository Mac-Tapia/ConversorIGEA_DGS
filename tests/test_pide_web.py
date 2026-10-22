"""Spec 024, T14: propuesta del PIDE, obras propias y decisiones del operador, desde la web."""
from __future__ import annotations

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx2')

from fastapi.testclient import TestClient

from igea_dgs.digital_twin.buffer import BuferEpisodios
from igea_dgs.pide_economia import propuesta_pide
from igea_dgs.web import services
from igea_dgs.web.app import create_app

PLAN = {'tasa_regulada': 0.12, 'tasa_privada': 0.12, 'vida_util_anios': 30, 'horizonte_anios': 20,
        'anios_pide': [4, 5, 6, 7], 'anios_horizonte': [4, 8], 'crecimiento_demanda_anual': 0.04,
        'pesos_art_15_3': {'subsanacion_calidad': 1, 'crecimiento_demanda': 1},
        'tarifas': {'MT3': {'energia_punta_kwh': 0.32, 'energia_fuera_punta_kwh': 0.28}}}
COSTOS = {'bancos': {'costo_unitario': 3500, 'unidad': 'Und', 'obras': 2, 'denominacion': 'Banco 300 kvar'},
          'nueva_terna': {'costo_unitario': 40000, 'unidad': 'Und', 'obras': 1, 'denominacion': 'Terna'}}


def _p(causa, elemento, valor, kv, alim='F1', tipo='tension'):
    return {'tipo': tipo, 'elemento': elemento, 'valor': valor, 'limite': 0.95, 'causa': causa,
            'evidencia': 'e', 'kv': kv, 'alimentador': alim}


INFORME = {'anios': [
    {'anio': 0, 'cabeceras_kw': {'F1': 1000.0}, 'vm_min': 0.90, 'problemas': [
        _p('caida_de_tension', 'B9', 0.90, 10.0), _p('caida_de_tension', 'B5', 0.93, 10.0),
        _p('caida_de_tension', 'S1_BT', 0.91, 0.38)]},
    {'anio': 4, 'cabeceras_kw': {'F1': 1170.0}, 'vm_min': 0.88, 'problemas': [
        _p('caida_de_tension', 'B9', 0.88, 10.0),
        _p('conductor_insuficiente', 'F1_L2.ElmLne', 104.0, None, tipo='cargabilidad')]}]}


def test_propuesta_del_pide_desde_el_diagnostico():
    """024:RF-45 / 024:RF-52 / 024:RF-59 / 024:RF-62 — del diagnóstico año a año a obras con su año,
    rubro, costo del CAPEX, prioridad y la obra que la construye; la caída en baja va a la
    SED; el banco va en la barra de media más baja."""
    p = propuesta_pide(INFORME, PLAN, costos=COSTOS, bancos_kvar={10.0: 300.0, 22.9: 450.0})
    por_alt = {o['alternativa']: o for o in p['obras']}
    banco = por_alt['bancos']
    assert banco['obra_011'] == {'clase': 'condensador', 'alimentador': 'F1', 'barra': 'B9',
                                 'q_kvar': 300.0, 'escalones': 1, 'casos': ['Con proyecto']}
    assert banco['anio'] == 4 and banco['rubro'] == 'mejoramiento' and banco['ci'] == 3500
    assert banco['caracter'] == 'general'
    assert por_alt['nueva_sed']['obra_011'] is None and por_alt['nueva_sed']['motivo_sin_obra']
    assert sorted(o['prioridad'] for o in p['obras']) == list(range(1, len(p['obras']) + 1))
    assert p['formatos']['F09 Evaluación económica'] and p['formatos']['F12 Propuesta proyecto']


def test_sin_capex_se_dice():
    """024:RF-55 — sin libro CAPEX las obras van sin costo y se avisa."""
    p = propuesta_pide(INFORME, PLAN, costos={}, bancos_kvar=None)
    assert any('CAPEX' in a for a in p['avisos'])
    assert all(o['ci'] == 0 for o in p['obras'])
    assert next(o for o in p['obras'] if o['alternativa'] == 'bancos')['obra_011'] is None


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as c:
        yield c


def test_pide_simula_y_aplica_solo_lo_que_funciona(client, monkeypatch, tmp_path):
    """024:RF-46 / 024:RF-47 / 024:RF-47b / 024:RF-47c / 024:RF-63 — las obras propias se simulan antes;
    solo las buenas se aplican solas en «Con proyecto» con su variación para deshacerlas; la
    que falla en la simulación queda con su motivo; se escriben los formatos."""
    wid = client.post('/api/workspaces', json={'name': 'pide'}).json()['id']
    ws = client.app.state.store.get(wid)
    perfil = {'planificacion': PLAN, 'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05,
                                                  'cargabilidad_max_pct': 100},
              'informes': {'norma': 'NTCSE'},
              'calibracion': {'bancos_kvar_por_tension': {'10': 300}}}
    monkeypatch.setattr(services, 'native_action_context',
                        lambda _ws, project, feeders, action: {'feeders': ['F1'], 'project': project})
    monkeypatch.setattr('igea_dgs.perfil_empresa.datos_perfil', lambda *a, **k: perfil)
    monkeypatch.setattr('igea_dgs.perfil_empresa.estructura_empresa', lambda *a, **k: None)
    informe = {'anios': [dict(INFORME['anios'][0], problemas=INFORME['anios'][0]['problemas']
                              + [_p('caida_de_tension', 'C3', 0.92, 10.0, alim='F2')]),
                         INFORME['anios'][1]]}
    monkeypatch.setattr(services, '_guion_pf', lambda *a, **k: (0, informe, tmp_path / 'pide.json'))
    llamadas = []

    def obras(_ws, _ctx, project, feeders, ids, otro, *, simular):
        llamadas.append((simular, list(ids)))
        por_id = {o['id']: o for o in _ws.obras}
        if simular:   # el banco de F2 falla en la simulación
            return {'informe': {'obras': [{'obra': i + 1, 'error': 'no converge' if por_id[x]['alimentador'] == 'F2' else None}
                                          for i, x in enumerate(ids)]}}
        return {'informe': {'obras': [{'obra': i + 1, 'variacion': f'IGEA obra {i + 1}'} for i in range(len(ids))]}}

    monkeypatch.setattr(services, 'obras_ejecutar', obras)

    class Ctx:
        def log(self, _m):
            pass

    r = services.pide_ejecutar(ws, Ctx(), 'P', ['F1'])
    assert [(s, len(i)) for s, i in llamadas] == [(True, 2), (False, 1)]
    assert [x['alternativa'] for x in r['implementadas']] == ['bancos']
    assert 'IGEA obra 1' in r['implementadas'][0]['aviso']
    f2 = next(o for o in r['obras'] if o['alimentador'] == 'F2')
    assert 'simulación' in f2['motivo_sin_obra']
    assert not any(o['alimentador'] == 'F2' for o in ws.obras)
    # Nunca en el «Caso base» ni en «Sin proyecto», donde está lo manual del operador.
    assert all(o['obra_011']['casos'] == ['Con proyecto'] for o in r['obras'] if o['obra_011'])
    assert (ws.out_dir / r['formatos']).is_file()


def test_decisiones_del_operador(client):
    """024:RF-48 — la decisión sobre una propuesta queda registrada para aprender; solo
    aceptada, rechazada o modificada."""
    wid = client.post('/api/workspaces', json={'name': 'd'}).json()['id']
    r = client.post(f'/api/workspaces/{wid}/pide/decision',
                    json={'project': 'P', 'codigo': 'AL01', 'decision': 'rechazada', 'comentario': 'caro'})
    assert r.status_code == 200 and r.json()['decision'] == 'rechazada'
    assert BuferEpisodios().decisiones()[-1]['codigo'] == 'AL01'
    assert client.post(f'/api/workspaces/{wid}/pide/decision',
                       json={'project': 'P', 'codigo': 'X', 'decision': 'quizas'}).status_code >= 400
