"""Spec 026, RF-47 (T21), con el gobierno del equipo de la 065: antes de escribir un entregable, el equipo del asistente
(fuentes, física, coste y riesgo) da su dictamen sobre lo que ya calcularon las corridas custodiadas (067:RF-1 a RF-5),
nunca de un cálculo nuevo, y se enseña con la confirmación; con «riesgo», el asistente no escribe: lo enseña y pregunta.
Un modelo nunca concede autoridad.

Las corridas son sintéticas (proyecto «P1», fuente «fuente-a»): se custodian con ``custodiar_trabajo``, la misma función
que usa la web al terminar un trabajo, sobre un espacio en ``tmp_path``.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from convertersmartgrid.aplicacion.asistente import almacen
from convertersmartgrid.aplicacion.asistente.equipo import GobiernoEquipo, PermisoDenegado, inventario_equipo
from convertersmartgrid.aplicacion.asistente.plan import Plan


@pytest.fixture(autouse=True)
def almacenamiento(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))


def _espacio(tmp_path):
    return SimpleNamespace(id='espacio-a', root=tmp_path / 'ws', out_dir=tmp_path / 'ws' / 'salida',
                           loaded_source_fingerprint='fuente-a', loaded_source_mode='txt', pf_project_bindings={})


def _corrida(ws, ident, kind, status, resultado, entregable=None):
    """Una corrida terminada, custodiada como la custodia la web."""
    from convertersmartgrid.aplicacion.asistente.evidencias_web import custodiar_trabajo

    ws.out_dir.mkdir(parents=True, exist_ok=True)
    if entregable:
        (ws.out_dir / entregable).write_bytes(b'informe sintetico')
    aviso = custodiar_trabajo(ws, {'id': ident, 'kind': kind, 'title': f'{kind} de P1', 'status': status,
                                   'result': {'project': 'P1', **resultado, **({'informe': entregable} if entregable else {})}})
    assert aviso is None, aviso


def _evidencia(ws):
    from convertersmartgrid.aplicacion.asistente.evidencias_web import evidencias_del_contexto

    return evidencias_del_contexto(ws.out_dir, 'P1', 'fuente-a')


def _gobierno(ws, tarea='pide'):
    plan = Plan('plan-a', 'haz el pide de P1', tarea, True, 'trabajo', datos={'proyecto': 'P1'})
    return plan, GobiernoEquipo.desde_plan(ws, plan)


def _dictaminar(gobierno, ws):
    assert hasattr(gobierno, 'dictaminar'), 'el gobierno del equipo no da dictamen antes de escribir un entregable'
    return gobierno.dictaminar(_evidencia(ws), {'proyecto': 'P1', 'fuente': 'fuente-a'})


def test_026_rf47_sin_corridas_cada_rol_pide_revisar_y_se_ensena_con_la_confirmacion(tmp_path):
    """026:RF-47 — sin corridas que lo sostengan, los cuatro roles dicen «revisar» con su motivo; no bloquea, y el
    dictamen va en lo que ve el operador antes de confirmar."""
    ws = _espacio(tmp_path)
    plan, gobierno = _gobierno(ws)
    dictamen = _dictaminar(gobierno, ws)
    assert [d['rol'] for d in dictamen['dictamenes']] == ['fuentes', 'fisica', 'coste', 'riesgo']
    assert dictamen['decision'] == 'revisar' and all(d['decision'] == 'revisar' for d in dictamen['dictamenes'])
    assert all('ninguna corrida custodiada de P1' in d['motivos'][0] for d in dictamen['dictamenes'])
    assert dictamen['calculo_nuevo'] is False and dictamen['modelo_concede_autoridad'] is False
    assert dictamen['autoriza_ejecucion'] is False
    assert gobierno.publico()['dictamen'] == dictamen
    gobierno.confirmar(plan)
    assert gobierno.publico()['permiso_efectivo'] is True


def test_026_rf47_corridas_sanas_dan_favorable_con_su_evidencia_y_sin_tocar_nada(tmp_path):
    """026:RF-47 — de lo ya calculado: la corrida custodiada y su entregable intacto sostienen lo que se escribe; el
    dictamen solo lee (los ficheros del espacio no cambian) y cita la corrida."""
    ws = _espacio(tmp_path)
    _corrida(ws, 'e1', 'estudios', 'done', {'converge': True, 'costo_total': 1250.0}, entregable='estudio_P1.xlsx')
    antes = {p: p.read_bytes() for p in ws.out_dir.rglob('*') if p.is_file()}
    _plan, gobierno = _gobierno(ws)
    dictamen = _dictaminar(gobierno, ws)
    assert dictamen['decision'] == 'favorable', dictamen
    assert dictamen['evidencia_ids'] and all(d['evidencia_ids'] == dictamen['evidencia_ids'] for d in dictamen['dictamenes'])
    assert {p: p.read_bytes() for p in ws.out_dir.rglob('*') if p.is_file()} == antes, 'el dictamen escribió algo'


@pytest.mark.parametrize('caso, rol', [('no_converge', 'fisica'), ('entregable_cambiado', 'fuentes'),
                                       ('coste_imposible', 'coste'), ('sin_servicio', 'riesgo')])
def test_026_rf47_con_riesgo_no_escribe_lo_ensena_y_pregunta(tmp_path, caso, rol):
    """026:RF-47 / 065:RF-22 — una corrida que no convergió, un entregable que cambió después de su corrida, un coste
    imposible o cargas sin servicio: el rol que lo ve dice «riesgo», y aunque el operador confirme, el gobierno no deja
    escribir: el motivo es la pregunta al operador."""
    ws = _espacio(tmp_path)
    resultado = {'converge': True, 'costo_total': 900.0}
    if caso == 'no_converge':
        _corrida(ws, 'e1', 'estudios', 'no_converge', {'converge': False})
    elif caso == 'entregable_cambiado':
        _corrida(ws, 'e1', 'informe_estudio', 'done', resultado, entregable='informe_P1.docx')
        (ws.out_dir / 'informe_P1.docx').write_bytes(b'otro texto')
    elif caso == 'coste_imposible':
        _corrida(ws, 'e1', 'obras_aplicar', 'done', {'converge': True, 'costo_total': -5.0})
    else:
        _corrida(ws, 'e1', 'transferencia', 'done', {'converge': True, 'cargas_sin_servicio': 3})
    plan, gobierno = _gobierno(ws)
    dictamen = _dictaminar(gobierno, ws)
    assert dictamen['decision'] == 'riesgo', dictamen
    assert next(d for d in dictamen['dictamenes'] if d['rol'] == rol)['decision'] == 'riesgo'
    assert '¿' in dictamen['pregunta'] and 'no se escribe' in dictamen['pregunta']
    gobierno.confirmar(plan)
    publico = gobierno.publico()
    assert publico['permiso_efectivo'] is False and publico['motivo'] == dictamen['pregunta']
    with pytest.raises(PermisoDenegado, match='riesgo'):
        with gobierno.accion():
            pytest.fail('con riesgo no debía empezar la escritura')
    with pytest.raises(PermisoDenegado, match='riesgo'):
        gobierno.autorizar_peticion('POST', '/pide', {})
    assert almacen.leer('equipo_acciones')[-1]['estado'] == 'rechazada'


def test_026_rf47_la_corrida_que_se_rehizo_sustituye_a_la_que_fallo(tmp_path):
    """026:RF-47 — de cada clase de trabajo vale la más reciente: un estudio que no convergió y se rehízo bien ya no
    es riesgo."""
    import time

    ws = _espacio(tmp_path)
    _corrida(ws, 'e1', 'estudios', 'no_converge', {'converge': False})
    time.sleep(0.01)
    _corrida(ws, 'e2', 'estudios', 'done', {'converge': True})
    _plan, gobierno = _gobierno(ws)
    assert _dictaminar(gobierno, ws)['decision'] == 'favorable'


def test_026_rf47_solo_los_entregables_y_el_dictamen_viaja_con_el_plan_guardado(tmp_path):
    """026:RF-47 / 067:RF-12 — una tarea sin entregable no lleva dictamen; el de un plan guardado vuelve con él tras un
    reinicio, y el inventario del equipo dice la regla."""
    ws = _espacio(tmp_path)
    _corrida(ws, 'e1', 'estudios', 'no_converge', {'converge': False})
    _p, sin_entregable = _gobierno(ws, tarea='convertir')
    assert _dictaminar(sin_entregable, ws) is None and sin_entregable.publico()['dictamen'] is None
    plan, gobierno = _gobierno(ws)
    dictamen = _dictaminar(gobierno, ws)
    vuelto = GobiernoEquipo.restaurar(ws, plan, extras={}, sello=gobierno.sello())
    assert vuelto.dictamen == dictamen and vuelto.publico()['permiso_efectivo'] is False
    regla = inventario_equipo().get('dictamen_antes_de_entregable') or {}
    assert regla.get('riesgo_bloquea') is True and regla.get('modelo_concede_autoridad') is False
    assert {'pide', 'informe_estudio', 'pit_expediente', 'vad_empresa_modelo', 'vnr_estudio'} <= set(regla['tareas'])


def test_026_rf47_la_web_ensena_el_dictamen_y_la_pregunta_en_el_plan(tmp_path):
    """026:RF-47 — al proponer el plan, la web pide el dictamen con las corridas del espacio: va en su razonamiento, y
    con «riesgo», la pregunta en sus avisos."""
    from convertersmartgrid.presentacion.web import services

    assert hasattr(services, '_asistente_dictamen'), 'la web no pide el dictamen del equipo al proponer el plan'
    ws = _espacio(tmp_path)
    _corrida(ws, 'e1', 'estudios', 'no_converge', {'converge': False})
    plan, gobierno = _gobierno(ws)
    dictamen = services._asistente_dictamen(ws, plan, gobierno)
    assert dictamen['decision'] == 'riesgo' and plan.avisos == [dictamen['pregunta']]
    assert dictamen['resumen'] in plan.razonamiento and gobierno.dictamen == dictamen
