"""Spec 081: un flujo «convergido» que no sirve, un trabajo «done» que no quedó bien y un «Caso base» que cambió."""
from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

from convertersmartgrid.asistente import almacen
from convertersmartgrid.asistente.vigilancia import revisar_calidad
from convertersmartgrid.comprobacion_flujo import (
    comparar_huellas, comprobar_tras_flujo, huella_de_caso, revisar_huellas, veredicto_calibracion, veredicto_importacion,
)
from convertersmartgrid.powerfactory_binding import fusionar_caso_base
from convertersmartgrid.powerfactory_metadata import CASO_BASE_CALIBRABLE, classify_convergence, estado_caso_base, estado_flujo
from convertersmartgrid.web import services
from convertersmartgrid.web.jobs import CON_RESULTADO, FINISHED, NO_CONVERGE, PARCIAL, JobManager

RAIZ = Path(__file__).resolve().parents[1]
BUENO = {'load_flow': {'requested': True, 'pass': True, 'return_code': 0, 'ldf_valid': True}}
SIN_SERVIR = {'limpio': False, 'barras_bt_a_cero': 1, 'cargas_sin_consumo': 1, 'lista_barras': ['BT1'], 'lista_cargas': ['S1']}


def _barra(nombre, kv, u):
    return {'nombre': nombre, 'uknom_kv': kv, 'u_pu': u}


def _carga(nombre, barra, p, c, servicio=True):
    return {'nombre': nombre, 'barra': barra, 'programada_mw': p, 'consumo_mw': c, 'en_servicio': servicio}


def test_barra_de_baja_con_carga_a_cero():
    """081:RF-11 — el fallo real: la barra de baja de una SED a 0 p.u., con el flujo «convergido». Sin resultado cuenta."""
    t = comprobar_tras_flujo([_barra('BT1', .23, 0.0), _barra('BT2', .23, None), _barra('BT3', .23, .98),
                              _barra('MT1', 10., 0.0), _barra('BT4', .23, 0.0)],
                             [_carga('S1', 'BT1', .01, .01), _carga('S2', 'BT2', .01, .01), _carga('S3', 'BT3', .01, .01),
                              _carga('S4', 'MT1', .01, .01)])
    assert t['barras_bt_a_cero'] == 2 and t['lista_barras'] == ['BT1', 'BT2'] and not t['limpio']


def test_carga_que_no_consume():
    """081:RF-12 — una carga en servicio con demanda y sin consumo; la de cero o fuera de servicio no cuenta."""
    t = comprobar_tras_flujo([], [_carga('S1', 'B', .01, 0.0), _carga('S2', 'B', .01, None), _carga('S3', 'B', .01, -.01),
                                  _carga('S4', 'B', 0.0, 0.0), _carga('S5', 'B', .01, 0.0, False)])
    assert t['cargas_sin_consumo'] == 2 and t['lista_cargas'] == ['S1', 'S2'] and not t['limpio']
    assert comprobar_tras_flujo([_barra('BT', .23, .97)], [_carga('S', 'BT', .01, .01)])['limpio']


def test_flujo_sin_servir_no_sale_limpio():
    """081:RF-14 — DIgSILENT convergió y se dice; pero no limpio, con el conteo."""
    flujo = estado_flujo({**BUENO, 'tras_flujo': SIN_SERVIR})
    assert flujo['estado'] == 'converge' and flujo['limpio'] is False and '1 barra' in flujo['motivo'] and '1 carga' in flujo['motivo']
    assert estado_flujo(BUENO)['limpio'] is True
    # Sin lectura no se inventa nada, y sin converger tampoco es limpio.
    assert estado_flujo({**BUENO, 'tras_flujo': {'sin_lectura': True, 'limpio': True}})['limpio'] is True
    assert estado_flujo({'load_flow': {'requested': True, 'return_code': 1}})['limpio'] is False


def test_caso_base_limpio_y_sin_servir():
    """081:RF-15, 081:RF-30 — no se llama VERIFICADO, y calibra: el flujo no bloquea."""
    assert estado_caso_base(True, 'converge', limpio=False) == 'CONVERGE_SIN_SERVIR'
    assert estado_caso_base(True, 'converge') == 'VERIFICADO' and estado_caso_base(False, 'converge', limpio=False) == 'NO_VERIFICADO'
    assert 'CONVERGE_SIN_SERVIR' in CASO_BASE_CALIBRABLE and {'NO_CONVERGE', 'SIN_DATO_DE_FLUJO'} < set(CASO_BASE_CALIBRABLE)
    fuente = (RAIZ / 'frontend/src/components/CargasTab.tsx').read_text(encoding='utf-8')
    assert "'CONVERGE_SIN_SERVIR', 'NO_CONVERGE', 'SIN_DATO_DE_FLUJO'];" in fuente and 'Converge sin servir todo' in fuente


def test_el_limpio_se_arrastra_al_volver_a_verificar():
    """081:RF-15 — volver a verificar no corre el flujo: lo no servido sigue valiendo hasta el siguiente."""
    from convertersmartgrid.powerfactory_binding import PowerFactoryProjectBinding

    previo = {'source_fingerprint': 'f', 'feeders': ['A'], 'dgs_sha256': {},
              'native_reread': {'caso_base': {'A': {'status': 'CONVERGE_SIN_SERVIR', 'comprobaciones': {'gps': True, 'flujo': True},
                                                  'flujo': {'estado': 'converge', 'limpio': False}, 'fallos': []}}}}
    nuevo = PowerFactoryProjectBinding(project='P', folder='', source_run_id='r', source_mode='txt', source_fingerprint='f',
                                       feeders=('A',), dgs_sha256={}, native_inventory_sha256='n',
                                       native_reread={'caso_base': {'A': {'status': 'SIN_DATO_DE_FLUJO', 'comprobaciones': {'gps': True}, 'fallos': []}}},
                                       accepted_at=0.0)
    assert fusionar_caso_base(previo, nuevo).native_reread['caso_base']['A']['status'] == 'CONVERGE_SIN_SERVIR'


def test_importacion_limpio_no_dice_ok(tmp_path, monkeypatch):
    """081:RF-16 — ni «OK» ni fallo; queda importado, y el proyecto se guarda igual."""
    from test_senales_de_convergencia import _importar

    r, ws, target, _logs = _importar(tmp_path, monkeypatch, {**BUENO, 'tras_flujo': SIN_SERVIR})
    assert (r['ok'], r['failed'], r['sin_aceptar']) == (0, 0, 1)
    assert r['lines'][0].startswith(f'IMPORTADO_CON_CARGAS_SIN_SERVIR {target}') and ws.pf_projects[target] == 'P'
    assert r['estado_trabajo'] == 'no_converge'


def test_clasificacion_con_correcciones_limpio():
    """081:RF-32 — lo reconstruido se llama así: ni original, ni tapado por una revisión."""
    reread = {'feeder_metadata': True, 'comldf_executed': True, 'comldf_valid': True}
    base = {'source_verification': {'status': 'VERIFIED_BEFORE_MUTATION'}, 'effective_reread': reread,
            'rollback': {'status': 'NOT_REQUIRED'}}
    assert classify_convergence({**base, **BUENO}) == 'CONVERGED_ORIGINAL'
    lf = {**BUENO['load_flow'], 'resolucion': {'anotaciones': [{'elemento': 'acoplador A'}], 'queda': []}}
    assert classify_convergence({**base, 'load_flow': lf}) == 'CONVERGED_RECONSTRUCTED'
    assert estado_flujo({'load_flow': lf})['correcciones'] == [{'elemento': 'acoplador A'}]


# ---------------------------------------------------------------- estado del trabajo

def _inf(feeder, status, **extra):
    return {'feeder': feeder, 'status': status, **extra}


def test_trabajo_calibracion_con_alguno_sin_converger_es_parcial():
    """081:RF-17, 081:RF-19 — el fallo real: «done» con alimentadores NO_CONVERGE. Sale la lista, con su motivo."""
    v = veredicto_calibracion([_inf('A', 'OK'), _inf('B', 'NO_CONVERGE', motivo='isla sin fuente'),
                               _inf('C', 'VIOLACION_FISICA', avisos=['no cumple']), _inf('D', None, error='sin plan')])
    assert v['estado_trabajo'] == 'parcial'
    assert v['pendientes'] == [{'alimentador': 'B', 'estado': 'NO_CONVERGE', 'motivo': 'isla sin fuente'},
                               {'alimentador': 'C', 'estado': 'VIOLACION_FISICA', 'motivo': 'no cumple'},
                               {'alimentador': 'D', 'estado': 'ERROR', 'motivo': 'sin plan'}]


def test_trabajo_calibracion_sin_ninguno_es_no_converge():
    """081:RF-18 — ninguno quedó bien; si solo no cumplen la tolerancia pero convergen, es parcial."""
    assert veredicto_calibracion([_inf('A', 'NO_CONVERGE')])['estado_trabajo'] == 'no_converge'
    assert veredicto_calibracion([_inf('A', 'VIOLACION_FISICA')])['estado_trabajo'] == 'parcial'
    assert veredicto_calibracion([_inf('A', 'OK'), _inf('B', 'AVISO_KVAR')]) == {'estado_trabajo': 'done', 'pendientes': []}


def _terminar(resultado):
    eventos = []
    jobs = JobManager(lambda *a: eventos.append(a))
    job = jobs.submit('ws', 'ajuste_aplicar', 'Calibración', lambda _ctx: resultado, lane='engine')
    limite = time.monotonic() + 10
    while job.status not in FINISHED and time.monotonic() < limite:
        time.sleep(.01)
    jobs.shutdown(1)
    return job


def test_trabajo_termina_con_su_estado_y_su_resultado():
    """081:RF-20, 081:RF-23 — terminó y conserva todo; los trabajos de siempre siguen en «done»."""
    r = {'informes': [1], 'estado_trabajo': 'parcial', 'pendientes': [{'alimentador': 'B'}]}
    job = _terminar(r)
    assert job.status == PARCIAL and job.result == r and job.finished_at is not None and job.error is None
    assert _terminar({'estado_trabajo': 'no_converge'}).status == NO_CONVERGE
    assert _terminar({'estado_trabajo': 'otro'}).status == 'done' and _terminar({'status': 'ok'}).status == 'done'
    assert _terminar(None).status == 'done'
    assert {PARCIAL, NO_CONVERGE} < set(CON_RESULTADO) and set(CON_RESULTADO) < set(FINISHED)
    # Los que esperan a un trabajo lo ven terminado: si no, esperaban horas.
    for fichero in ('tools/sistema_web.py', 'src/convertersmartgrid/asistente/ejecutor.py'):
        assert "'parcial', 'no_converge', 'failed', 'cancelled'" in (RAIZ / fichero).read_text(encoding='utf-8')
    fuente = (RAIZ / 'frontend/src/useWorkspace.ts').read_text(encoding='utf-8')
    assert "'done', 'parcial', 'no_converge', 'failed', 'cancelled'" in fuente


def test_trabajo_parcial_avisa_la_vigilancia():
    """081:RF-23 — la vigilancia lo dice con la lista, y el error de la lista no se pierde."""
    t = {'id': 'x', 'kind': 'ajuste_aplicar', 'title': 'Calibración', 'status': 'parcial', 'lane': 'powerfactory',
         'result': {'pendientes': [{'alimentador': 'B', 'estado': 'NO_CONVERGE'}]}}
    avisos = {a.clave: a for a in revisar_calidad([t])}
    assert avisos['parcial:x'].nivel == 'error' and 'B NO_CONVERGE' in avisos['parcial:x'].texto


def test_trabajo_interfaz_lo_dice():
    """081:RF-24 — el título y la calibración. Solo vigila la fuente: verlo en el navegador es la T13."""
    app = (RAIZ / 'frontend/src/App.tsx').read_text(encoding='utf-8')
    assert "' — parcial'" in app and "' — no converge'" in app and 'r?.pendientes' in app
    ajuste = (RAIZ / 'frontend/src/components/AjusteCabecera.tsx').read_text(encoding='utf-8')
    assert 'resultado?.pendientes' in ajuste and 'Calibración parcial' in ajuste and 'caso_base_cambio' in ajuste


def test_trabajo_importacion_dice_su_estado():
    """081:RF-22 — con alguno sin aceptar, parcial; con ninguno aceptado, no_converge; todo bien, como siempre."""
    assert veredicto_importacion(2, 0, 0) == {'estado_trabajo': 'done'}
    assert veredicto_importacion(2, 0, 1) == {'estado_trabajo': 'parcial'} == veredicto_importacion(1, 1, 0)
    assert veredicto_importacion(0, 1, 2) == {'estado_trabajo': 'no_converge'}


def test_trabajo_recalibrar_con_fallos_es_parcial(tmp_path):
    """081:RF-21 — el código 1 de ``sistema_web`` deja de ser «done»; la lista viene de su resumen, y sin él sigue parcial."""
    ruta = tmp_path / 'r.json'
    assert services._verdad_del_sistema(ruta, 0) == {'estado_trabajo': 'done', 'pendientes': []}
    assert services._verdad_del_sistema(ruta, 1) == {'estado_trabajo': 'parcial', 'pendientes': []}
    ruta.write_text(json.dumps({'estado_trabajo': 'no_converge', 'pendientes': [{'alimentador': 'A'}]}), encoding='utf-8')
    assert services._verdad_del_sistema(ruta, 1) == {'estado_trabajo': 'no_converge', 'pendientes': [{'alimentador': 'A'}]}
    ruta.write_text(json.dumps({'estado_trabajo': 'done'}), encoding='utf-8')
    assert services._verdad_del_sistema(ruta, 1)['estado_trabajo'] == 'parcial'


def test_trabajo_sistema_web_lo_sigue_y_deja_el_resumen(tmp_path):
    """081:RF-20, 081:RF-21 — el guion sigue con un parcial y deja la lista a quien lo lanzó."""
    from apoyo import cargar_herramienta

    w = cargar_herramienta('sistema_web.py', 'sistema_web_081')
    assert w._terminado({'status': 'parcial'}) and w._terminado({'status': 'no_converge'}) and not w._terminado({'status': 'failed'})
    ruta = tmp_path / 'r.json'
    w._RESUMEN[:] = [ruta]
    try:
        w._escribir_resumen({'status': 'parcial', 'result': {'pendientes': [{'alimentador': 'A'}]}})
    finally:
        w._RESUMEN[:] = []
    assert json.loads(ruta.read_text(encoding='utf-8')) == {'estado_trabajo': 'parcial', 'pendientes': [{'alimentador': 'A'}]}


# ---------------------------------------------------------------- huella del «Caso base»

CARGAS = [{'nombre': 'S1', 'p_kw': 10.0, 'q_kvar': 2.0, 'escala': 1.0, 'en_servicio': True},
          {'nombre': 'S2', 'p_kw': 20.0, 'q_kvar': 4.0, 'escala': 1.0, 'en_servicio': True}]
FLUJO = {'converge': True, 'return_code': 0, 'kw': 30.2}


def test_huella_misma_si_nada_cambia():
    """081:RF-33 — su flujo y sus cargas, determinista y sin depender del orden."""
    a = huella_de_caso(CARGAS, FLUJO)
    assert a == huella_de_caso(reversed(CARGAS), FLUJO) and set(a) == {'cargas', 'flujo', 'sha256'}
    assert comparar_huellas(a, huella_de_caso(CARGAS, FLUJO)) == {'cambio': False, 'cambios': [], 'volver': []}
    assert revisar_huellas([{'caso_base_huella': {'antes': a, 'despues': a}}, {}]) is None


def test_huella_que_cambio_dice_que_y_como_volver():
    """081:RF-34, 081:RF-35 — el fallo real: dejó de converger tras calibrar; se dice qué cambió y hay plan para volver."""
    antes = huella_de_caso(CARGAS, FLUJO)
    despues = huella_de_caso([{**CARGAS[0], 'p_kw': 15.0}, CARGAS[1]], {'converge': False, 'return_code': 1})
    c = comparar_huellas(antes, despues)
    assert c['cambio'] and c['cambios'][0].startswith('flujo:') and any('carga S1' in x for x in c['cambios'])
    assert c['volver'] == [{'carga': 'S1', 'p_kw': 10.0, 'q_kvar': 2.0, 'escala': 1.0, 'en_servicio': True}]
    g = revisar_huellas([{'caso_base_huella': {'antes': antes, 'despues': despues}}])
    assert g['nivel'] == 'grave' and 'FALLO GRAVE' in g['texto'] and 'carga S1' in g['texto'] and g['volver']


def test_huella_que_cambio_no_para_y_sale_parcial():
    """081:RF-36 — el trabajo termina en parcial con todo lo calibrado, y lo dice la vigilancia."""
    antes = huella_de_caso(CARGAS, FLUJO)
    despues = huella_de_caso(CARGAS[:1], FLUJO)
    logs: list[str] = []
    v = services._verdad_de_la_calibracion(SimpleNamespace(log=logs.append),
                                           [{'feeder': 'A', 'status': 'OK', 'caso_base_huella': {'antes': antes, 'despues': despues}}])
    assert v['estado_trabajo'] == 'parcial' and v['pendientes'] == [] and v['caso_base_cambio']['nivel'] == 'grave'
    assert any('FALLO GRAVE' in x for x in logs)
    t = {'id': 'x', 'kind': 'k', 'title': 'Calibración', 'status': 'parcial', 'lane': 'powerfactory', 'result': v}
    assert 'caso_base:x' in {a.clave for a in revisar_calidad([t])}
    assert services._verdad_de_la_calibracion(SimpleNamespace(log=logs.append), [{'feeder': 'A', 'status': 'OK'}])['estado_trabajo'] == 'done'


def test_almacen_no_hace_falta_para_el_contrato(tmp_path, monkeypatch):
    """081:RF-13 — estas lecturas no escriben nada: ni en DIgSILENT, ni en el registro."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    comprobar_tras_flujo([_barra('BT', .23, 0.)], [_carga('S', 'BT', .01, 0.)])
    comparar_huellas(huella_de_caso(CARGAS, FLUJO), huella_de_caso(CARGAS[:1], FLUJO))
    assert list(tmp_path.iterdir()) == [] and almacen.leer('avisos') == []
