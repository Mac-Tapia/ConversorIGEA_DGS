"""Spec 086, T10: cada informe ligado a la corrida de estudios que lo generó, por alimentador.

El informe tomaba el último fichero por fecha: si «Con proyecto» fallaba, se cancelaba o agotaba su
límite, salía con el flujo de una corrida anterior y nada lo decía. DIgSILENT no se ejecuta aquí:
``_guion_pf`` es un doble que deja lo mismo que deja el guion, y lo que no termina no deja nada.
"""
from __future__ import annotations

import json
import threading
import uuid
from types import SimpleNamespace

import docx
import pytest

pytest.importorskip('fastapi')

from test_informe_web import FACTIBILIDAD, FORMULARIO, _medida, client  # noqa: E402,F401

from apoyo import esperar_trabajo  # noqa: E402
from convertersmartgrid.informe_docx import exportar_pdf  # noqa: E402
from convertersmartgrid.web import services  # noqa: E402
from convertersmartgrid.web.services import UserError  # noqa: E402

LIMITES = {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100.0}
OBRA = {'clase': 'condensador', 'alimentador': 'AL01', 'casos': ['Con proyecto'], 'barra': 'N7', 'q_kvar': 300}


def _espacio(client):  # noqa: F811
    wid = client.post('/api/workspaces').json()['id']
    ws = client.app.state.store.get(wid)
    ws.out_dir.mkdir(parents=True, exist_ok=True)
    ws.plans_dir.mkdir(parents=True, exist_ok=True)
    return wid, ws


def _carga_aplicada(ws) -> None:
    """Lo que deja el paso 3 al aplicar la carga nueva del informe de factibilidad."""
    (ws.out_dir / 'cargas_pf_aplicacion_tok1.json').write_text(json.dumps({
        'project': 'PRY', 'cargas': [{'sed': 'SN1', 'alimentador': 'AL01', 'barra': 'B_NUEVA',
                                      'variacion': 'CN_SN1', 'distancia_m': 120.0}]}), encoding='utf-8')
    (ws.plans_dir / 'cargas_pf_tok1.json').write_text(json.dumps({'nuevas': [
        {'sed': 'SN1', 'hoja': 'formulario', 'alimentador': 'AL01', 'kw': 800.0, 'kvar': 300.0,
         'kva_instalado': 1000}]}), encoding='utf-8')


def _doble_del_guion(ws, comportamiento, feeders, *, vmin=None, gemelo=True, barras_de=None):
    """``comportamiento(rol, estudio, ctx)`` decide; sin decisión, el guion termina bien y deja su informe."""
    vmin = vmin or {'sin': 0.90, 'cargas': 0.93, 'con': 0.99}

    def guion(_ws, ctx, script, plan, *, nombre, **_kw):
        report = ws.out_dir / f'{nombre}_{uuid.uuid4().hex[:12]}.json'
        if script == 'casos_pf.py':
            return 0, {'feeders': feeders, 'casos': {'con': {'estudiable': True}, 'cargas': {'estudiable': True}}}, report
        rol, estudio = plan['caso'], plan['estudio']
        forzado = comportamiento(rol, estudio, ctx)
        if forzado is not None:
            if isinstance(forzado, Exception):
                raise forzado
            return forzado.get('rc', 1), forzado, report                  # lo que no termina no deja informe
        barras = {f: {**_medida(vmin[rol]), 'barras': [['CAB', 1.0], ['N1', vmin[rol]], ['B_NUEVA', vmin[rol]]]}
                  for f in feeders}
        if barras_de:
            lista = [[n, u] for n, u in barras_de[rol].items()]
            peor = min(barras_de[rol], key=barras_de[rol].get)
            barras = {f: {**barras[f], 'barras': lista, 'vm_min': barras_de[rol][peor], 'vm_min_barra': peor,
                          'vm_min_fases': None} for f in feeders}
        informe = {'project': plan['project'], 'caso': rol, 'estudio': estudio, 'avisos': [], 'medidas': barras,
                   'obras_activas': ['V_OBRA'] if rol == 'con' else []}
        report.write_text(json.dumps(informe), encoding='utf-8')
        return 0, informe, report

    return guion


def _correr(ws, monkeypatch, feeders=('AL01',), comportamiento=lambda *_a: None, *, cancel=None, **kw):
    token = uuid.uuid4().hex[:12]
    ruta = ws.plans_dir / f'estudios_{token}.json'
    ruta.write_text(json.dumps({
        'project': 'PRY', 'folder': None, 'feeders': list(feeders), 'base': [], 'anio_casos': None,
        'native_action_context': {}, 'estudios': ['flujo_desequilibrado', 'flujo'], 'objetivos': {},
        'tolerancia': 0.01, 'limites': LIMITES, 'limite_s': 60, 'opciones': {}, 'libro': None, 'clases_equipo': []}),
        encoding='utf-8')
    ws.cargas_planes[token] = {'kind': 'estudios', 'path': str(ruta), 'project': 'PRY', 'feeders': list(feeders)}
    monkeypatch.setattr(services, '_guion_pf', _doble_del_guion(ws, comportamiento, list(feeders), **kw))
    monkeypatch.setattr(services, '_gemelo', lambda *_a, **_k: None)
    ctx = SimpleNamespace(log=lambda _m: None, progress=lambda *_a: None, cancel=cancel or threading.Event())
    return token, services.estudios_ejecutar(ws, ctx, token)


def _formulario(**extra):
    return {**FORMULARIO, 'project': 'PRY', **extra}


def _falla_con(modo):
    def comportamiento(rol, _estudio, ctx):
        if rol != 'con':
            return None
        if modo == 'agotado':
            return {'no_terminado': True, 'error': 'no terminó en su límite de 60 s', 'rc': 124}
        if modo == 'error':
            return {'error': 'el guion terminó con el código 1 sin dejar informe: vea el Registro.', 'rc': 1}
        if modo == 'motor':
            return UserError('No se pudo conectar con DIgSILENT. Ábralo y reintente.')
        raise AssertionError(modo)
    return comportamiento


def _segunda_corrida(ws, monkeypatch, modo):
    """La segunda corrida, la que debe mandar, con «Con proyecto» sin datos."""
    if modo == 'cancelado':
        cancel = threading.Event()

        def cancelar_tras_sin(rol, estudio, _ctx):
            if rol == 'sin' and estudio == 'flujo':
                cancel.set()

        return _correr(ws, monkeypatch, comportamiento=cancelar_tras_sin, cancel=cancel)[0]
    if modo == 'motor':
        with pytest.raises(UserError):
            _correr(ws, monkeypatch, comportamiento=_falla_con(modo))
        return None
    return _correr(ws, monkeypatch, comportamiento=_falla_con(modo))[0]


MODOS = ['agotado', 'cancelado', 'error', 'motor']


@pytest.mark.parametrize('modo', MODOS)
def test_estudio_con_proyecto_sin_terminar_no_usa_la_corrida_anterior(client, monkeypatch, modo):  # noqa: F811
    """086:RF-11, 086:RF-12 — con «Con proyecto» fallido, cancelado o agotado, el informe sale, sin el
    flujo viejo, con su aviso en el Word y en la web, y ligado a su corrida."""
    _wid, ws = _espacio(client)
    ws.obras = [OBRA]
    _viejo, primera = _correr(ws, monkeypatch)
    ficheros_viejos = {e['report'] for e in primera['estudios']}
    token = _segunda_corrida(ws, monkeypatch, modo)

    res = services.informe_estudio(ws, None, _formulario())

    assert not ficheros_viejos & set(res['estudios']), res['estudios']
    if token is not None:
        assert res['corrida'] == token
    resumen = json.loads((ws.out_dir / res['json']).read_text(encoding='utf-8'))
    assert resumen['etapas'] == [] and resumen['corrida'] == res['corrida']
    assert any('estado proyectado' in h for h in res['huecos']), res['huecos']
    texto = '\n'.join(p.text for p in docx.Document(ws.out_dir / res['informe']).paragraphs)
    assert 'AVISO' in texto and 'estado proyectado' in texto and 'Con proyecto' not in texto and 'RF-' not in texto


def test_estudio_con_la_web_caida_a_media_corrida(client, monkeypatch):  # noqa: F811
    """086:RF-12 — si la web muere a media corrida no queda más que lo escrito al empezar: el informe
    pedido entonces no toma la anterior, porque esa corrida ya está registrada."""
    _wid, ws = _espacio(client)
    ws.obras = [OBRA]
    _viejo, primera = _correr(ws, monkeypatch)
    ficheros_viejos = {e['report'] for e in primera['estudios']}
    visto = {}

    def en_con(rol, _estudio, _ctx):
        if rol == 'con' and not visto:
            visto['res'] = services.informe_estudio(ws, None, _formulario())
        return None

    _correr(ws, monkeypatch, comportamiento=en_con)
    res = visto['res']
    assert not ficheros_viejos & set(res['estudios'])
    assert any('no terminó' in h for h in res['huecos']), res['huecos']


def _si112(ws, monkeypatch, con, cargas=None):
    """SI112 (2026-11-04): con la obra la carga queda en norma y un ramal sigue a 0,9449 p.u., límite 0,95."""
    sin = {'CAB': 1.0, 'RAMAL': 0.9452}
    monkeypatch.setattr(services, '_tolerancia_pu_del_perfil', lambda: 0.005)
    _correr(ws, monkeypatch, barras_de={'sin': sin, 'con': con, 'cargas': cargas or {**con, 'B_NUEVA': 0.93}})


def test_la_tolerancia_es_la_de_la_escalera_y_sin_ella_no_se_disculpa_nada(monkeypatch):
    """086:RF-48 — la del perfil, para juzgar como la escalera; sin ella, 0: nunca un «previo» de más."""
    from convertersmartgrid import perfil_empresa

    monkeypatch.setattr(perfil_empresa, 'datos_perfil', lambda: {'escalera': {'tolerancia_pu': 0.005}})
    assert services._tolerancia_pu_del_perfil() == 0.005
    monkeypatch.setattr(perfil_empresa, 'datos_perfil', lambda: {})
    assert services._tolerancia_pu_del_perfil() == 0.0


def test_factibilidad_por_la_web_lista_el_deficit_previo(client, monkeypatch):  # noqa: F811
    """086:RF-48, 086:RF-50 — por el servicio: sale de lo que guardan los estudios, sin volver a DIgSILENT, y la
    web recibe «factible» con el matiz; la barra de la carga no se confunde con un déficit."""
    _wid, ws = _espacio(client)
    _carga_aplicada(ws)
    ws.obras_aplicadas = [{'project': 'PRY', 'variacion': 'V_OBRA', 'obra': OBRA}]
    _si112(ws, monkeypatch, {'CAB': 1.0, 'RAMAL': 0.9449, 'B_NUEVA': 0.963})

    res = services.informe_factibilidad(ws, None, FACTIBILIDAD)

    assert res['factible'] and res['queda_deficit'], res
    assert res['conclusion_conexion']['clave'] == 'con_obras_deficit'
    assert any('Déficit previo, fuera de esta obra: RAMAL a 0,9449 p.u.' in t for t in res['textos_bajo_limite'])
    assert not any('B_NUEVA' in t for t in res['textos_bajo_limite'])
    assert not any('RF-' in t for t in res['textos_bajo_limite'])
    generado = next(g for g in services._informes_generados(ws) if g['docx'] == res['informe'])
    assert generado['queda_deficit']


def test_factibilidad_por_la_web_con_la_barra_de_la_carga_baja_no_pasa(client, monkeypatch):  # noqa: F811
    """086:RF-49 — la carga nueva bajo el límite es cosa de la carga, aunque no tenga comparación."""
    _wid, ws = _espacio(client)
    _carga_aplicada(ws)
    ws.obras_aplicadas = [{'project': 'PRY', 'variacion': 'V_OBRA', 'obra': OBRA}]
    _si112(ws, monkeypatch, {'CAB': 1.0, 'RAMAL': 0.9449, 'B_NUEVA': 0.94})

    res = services.informe_factibilidad(ws, None, FACTIBILIDAD)

    assert not res['factible'] and res['conclusion_conexion']['clave'] == 'obras_insuficientes'
    assert any(t.startswith('Lo que causa la carga o la obra: B_NUEVA') for t in res['textos_bajo_limite'])


def test_factibilidad_por_la_web_sin_barras_bajas_dice_factible_a_secas(client, monkeypatch):  # noqa: F811
    """086:RF-50 — sin barras bajas, como siempre."""
    _wid, ws = _espacio(client)
    _carga_aplicada(ws)
    ws.obras_aplicadas = [{'project': 'PRY', 'variacion': 'V_OBRA', 'obra': OBRA}]
    _si112(ws, monkeypatch, {'CAB': 1.0, 'RAMAL': 0.96, 'B_NUEVA': 0.97}, {'CAB': 1.0, 'RAMAL': 0.93, 'B_NUEVA': 0.93})

    res = services.informe_factibilidad(ws, None, FACTIBILIDAD)

    assert res['factible'] and not res['queda_deficit'] and res['textos_bajo_limite'] == []
    assert res['conclusion_conexion']['clave'] == 'con_obras'


def test_estudio_por_la_web_lista_el_deficit_previo(client, monkeypatch):  # noqa: F811
    """086:RF-49 — el informe de estudio, con lo que guardan sus flujos."""
    _wid, ws = _espacio(client)
    ws.obras = [OBRA]
    _si112(ws, monkeypatch, {'CAB': 1.0, 'RAMAL': 0.9449})
    res = services.informe_estudio(ws, None, _formulario())
    assert any('Déficit previo, fuera de esta obra: RAMAL' in t for t in res['textos_bajo_limite'])


@pytest.mark.parametrize('modo', ['agotado', 'cancelado', 'error'])
def test_factibilidad_con_obras_sin_terminar_nunca_factible(client, monkeypatch, modo):  # noqa: F811
    """086:RF-12 — con «Con proyecto» sin datos y obras por evaluar no hay un «factible» falso: el flujo
    anterior decía que sí; el informe se entrega diciendo qué falta."""
    _wid, ws = _espacio(client)
    _carga_aplicada(ws)
    ws.obras_aplicadas = [{'project': 'PRY', 'variacion': 'V_OBRA', 'obra': OBRA}]
    _viejo, primera = _correr(ws, monkeypatch)
    ficheros_viejos = {e['report'] for e in primera['estudios']}
    token = _segunda_corrida(ws, monkeypatch, modo)

    res = services.informe_factibilidad(ws, None, FACTIBILIDAD)

    assert not ficheros_viejos & set(res['estudios']), (res['factible'], res['estudios'])
    assert res['corrida'] == token and not res['factible'] and res['punto_diseno'] is None
    assert any('estado proyectado' in h for h in res['huecos']), res['huecos']
    resumen = json.loads((ws.out_dir / res['json']).read_text(encoding='utf-8'))
    assert resumen['corrida'] == token and not resumen['proyectado']['converge']


def test_sin_proyecto_sin_terminar_tampoco_usa_la_anterior(client, monkeypatch):  # noqa: F811
    """086:RF-12 — el estado actual de esta corrida no llegó: se dice, y no se rellena con el anterior."""
    _wid, ws = _espacio(client)
    _viejo, primera = _correr(ws, monkeypatch)
    ficheros_viejos = {e['report'] for e in primera['estudios']}
    _correr(ws, monkeypatch, comportamiento=lambda rol, _e, _c: (
        {'no_terminado': True, 'error': 'no terminó en su límite de 60 s', 'rc': 124} if rol == 'sin' else None))
    res = services.informe_estudio(ws, None, _formulario())
    assert not ficheros_viejos & set(res['estudios'])
    assert any('estado actual' in h for h in res['huecos']), res['huecos']
    assert not json.loads((ws.out_dir / res['json']).read_text(encoding='utf-8'))['actual']['converge']


def test_el_desequilibrado_no_se_mezcla_con_el_de_otra_corrida(client, monkeypatch):  # noqa: F811
    """086:RF-11 — en esta corrida el desequilibrado no terminó: se usa su equilibrado y se dice; el
    desequilibrado de la anterior, más bonito, no entra."""
    _wid, ws = _espacio(client)
    ws.obras = [OBRA]
    _correr(ws, monkeypatch)
    token, resultado = _correr(ws, monkeypatch, comportamiento=lambda rol, e, _c: (
        {'no_terminado': True, 'error': 'no terminó en su límite de 60 s', 'rc': 124}
        if rol == 'con' and e == 'flujo_desequilibrado' else None))
    res = services.informe_estudio(ws, None, _formulario())
    equilibrado = next(e['report'] for e in resultado['estudios'] if e['caso'] == 'Con proyecto' and e['estudio'] == 'flujo')
    assert res['corrida'] == token and equilibrado in res['estudios']
    assert any('desequilibrado' in h and 'estado proyectado' in h for h in res['huecos']), res['huecos']


def test_regla_del_desequilibrado_que_no_cuadra_dentro_de_la_corrida(client, monkeypatch):  # noqa: F811
    """063:RF-45, 086:RF-11 — ligar el flujo a la corrida conserva la regla de la cabecera: más de un 2 %
    de diferencia y entra el equilibrado, con su aviso."""
    _wid, ws = _espacio(client)
    token, _r = _correr(ws, monkeypatch)
    fichero = next(ws.out_dir.glob('estudio_sin_flujo_desequilibrado_*.json'))
    datos = json.loads(fichero.read_text(encoding='utf-8'))
    datos['medidas']['AL01']['cabecera_kw'] = 7000.0
    fichero.write_text(json.dumps(datos), encoding='utf-8')
    elegido = services._ultimo_estudio(ws, 'sin', 'PRY', 'AL01')
    assert 'desequilibrado' not in elegido['_fichero'] and 'no cuadra' in elegido['_aviso_flujo']
    assert elegido['_corrida'] == token


def test_informe_del_alimentador_pedido_no_de_la_ultima_corrida(client, monkeypatch):  # noqa: F811
    """086:RF-11 — se estudió AL01 y después AL02: el informe de AL01 sale de su corrida, no falla por
    mirar la última sin ver el alimentador."""
    _wid, ws = _espacio(client)
    token, primera = _correr(ws, monkeypatch, ('AL01',))
    _correr(ws, monkeypatch, ('AL02',))
    res = services.informe_estudio(ws, None, _formulario())
    assert res['corrida'] == token and res['estudios'][0] in {e['report'] for e in primera['estudios']}


def test_una_corrida_sin_flujos_no_deja_sin_datos_al_informe(client, monkeypatch):  # noqa: F811
    """086:RF-11 — una corrida posterior que solo pidió contingencias no tiene nada que decir de los flujos."""
    _wid, ws = _espacio(client)
    token, _r = _correr(ws, monkeypatch)
    otra = {'token': 'solo_contingencias', 'project': 'PRY', 'feeders': ['AL01'], 'pedidos': ['contingencias'],
            'inicio': 10 ** 30, 'estado': 'terminada', 'estudios': []}
    services._guardar_corrida(ws, otra)
    assert services.informe_estudio(ws, None, _formulario())['corrida'] == token


def test_sin_registro_de_corrida_mira_el_alimentador_y_lo_dice(client, tmp_path):  # noqa: F811
    """086:RF-11, 086:RF-12 — los flujos guardados antes de esta spec no tienen corrida: se usa el último
    del alimentador, no el último de todos, y el informe dice que no está ligado a ninguna."""
    import time

    _wid, ws = _espacio(client)
    (ws.out_dir / 'estudio_sin_flujo_desequilibrado_a.json').write_text(
        json.dumps({'project': 'PRY', 'medidas': {'AL01': _medida(0.90)}}), encoding='utf-8')
    time.sleep(0.02)
    (ws.out_dir / 'estudio_sin_flujo_desequilibrado_b.json').write_text(
        json.dumps({'project': 'PRY', 'medidas': {'AL02': _medida(0.91)}}), encoding='utf-8')
    (ws.out_dir / 'estudio_sin_flujo_desequilibrado_roto.json').write_text('{"medidas": {"AL', encoding='utf-8')
    res = services.informe_estudio(ws, None, _formulario())
    assert res['estudios'] == ['estudio_sin_flujo_desequilibrado_a.json'] and res['corrida'] is None
    assert any('ninguna corrida' in h for h in res['huecos']), res['huecos']


def test_sin_ningun_flujo_lo_sigue_pidiendo(client):  # noqa: F811
    """086:RF-12 — sin corrida ni flujos no hay nada que entregar: se pide ejecutarlos."""
    _wid, ws = _espacio(client)
    with pytest.raises(UserError, match='flujo'):
        services.informe_estudio(ws, None, _formulario())


def test_el_boton_liga_el_informe_a_la_corrida_que_acaba_de_lanzar(client, monkeypatch):  # noqa: F811
    """086:RF-11 — el botón de 4.4 prepara y escribe en el mismo trabajo: su informe es de esa corrida."""
    wid, ws = _espacio(client)
    _carga_aplicada(ws)
    _correr(ws, monkeypatch)
    preparados = {}
    ejecutar = services.estudios_ejecutar

    def plan(_ws, *_a, **_k):
        token = uuid.uuid4().hex[:12]
        ruta = ws.plans_dir / f'estudios_{token}.json'
        ruta.write_text(json.dumps({
            'project': 'PRY', 'folder': None, 'feeders': ['AL01'], 'base': [], 'anio_casos': None,
            'native_action_context': {}, 'estudios': ['flujo'], 'objetivos': {}, 'tolerancia': 0.01,
            'limites': LIMITES, 'limite_s': 60, 'opciones': {}, 'libro': None, 'clases_equipo': []}), encoding='utf-8')
        ws.cargas_planes[token] = {'kind': 'estudios', 'path': str(ruta), 'project': 'PRY', 'feeders': ['AL01']}
        preparados['token'] = token
        return {'token': token}

    monkeypatch.setattr(services, 'estudios_plan', plan)
    monkeypatch.setattr(services, 'estudios_ejecutar', ejecutar)
    monkeypatch.setattr(services, 'ajuste_aplicado_en_disco', lambda *_a: {'id': 'disco:x'})
    fin = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/informes/factibilidad',
                                              json={**FACTIBILIDAD, 'preparar_casos': True}).json())
    assert fin['status'] == 'done', fin.get('error')
    assert fin['result']['corrida'] == preparados['token']


def test_el_contexto_dice_la_misma_corrida_que_el_informe(client, monkeypatch):  # noqa: F811
    """086:RF-11, 086:RF-12 — el formulario no enseña como disponible el flujo viejo que el informe ya no usará."""
    _wid, ws = _espacio(client)
    _correr(ws, monkeypatch, ('AL01', 'AL02'))
    token, _r = _correr(ws, monkeypatch, ('AL01',), _falla_con('agotado'))
    ctx = services.informes_contexto(ws, 'PRY', ['AL01', 'AL02'])
    # AL01: su última corrida no tiene «Con proyecto»; AL02 conserva la suya, que sí terminó.
    assert ctx['estudios']['con']['alimentadores'] == {'AL02': True}
    assert ctx['estudios']['sin']['alimentadores'] == {'AL01': True, 'AL02': True}
    assert any(a['alimentador'] == 'AL01' and a['corrida'] == token and 'estado proyectado' in a['texto']
               for a in ctx['avisos_corrida']), ctx['avisos_corrida']


def test_el_resultado_de_los_estudios_nombra_su_corrida(client, monkeypatch):  # noqa: F811
    """086:RF-11 — el trabajo devuelve el token y deja su registro aunque un estudio no termine."""
    _wid, ws = _espacio(client)
    token, resultado = _correr(ws, monkeypatch, comportamiento=_falla_con('agotado'))
    assert resultado['token'] == token
    registro = json.loads((ws.out_dir / f'estudios_corrida_{token}.json').read_text(encoding='utf-8'))
    assert registro['estado'] == 'terminada' and registro['feeders'] == ['AL01']
    con = [e for e in registro['estudios'] if e['rol'] == 'con']
    assert con and all(e['no_terminado'] for e in con)


def test_pdf_con_un_apostrofo_en_la_ruta(tmp_path):
    """086:RF-12 — una carpeta con apóstrofo rompía la orden de Word y el PDF no salía: en PowerShell se dobla."""
    carpeta = tmp_path / "INKA'S"
    carpeta.mkdir()
    ordenes = []

    def correr(orden):
        ordenes.append(orden)
        return SimpleNamespace(returncode=1, stdout='', stderr='')

    exportar_pdf(carpeta / 'x.docx', ejecutar=correr)
    assert "INKA''S" in ordenes[0] and "INKA'S" not in ordenes[0]
