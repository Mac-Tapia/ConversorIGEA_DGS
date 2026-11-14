"""Spec 017: el informe de estudio desde la web, con lo que guardaron los estudios."""
from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

import docx
import pytest

pytest.importorskip('fastapi')

from fastapi.testclient import TestClient  # noqa: E402

from apoyo import esperar_trabajo  # noqa: E402
from convertersmartgrid.web.app import create_app  # noqa: E402


def _medida(vmin, kvar_perdidas=55.0):
    return {'converge': True, 'barras': [['CAB', 1.0], ['N1', vmin]], 'elementos': [['L1', 'ElmLne', 60.0]],
            'vm_min': vmin, 'vm_min_barra': 'N1', 'vm_max': 1.0, 'vm_max_barra': 'CAB', 'mas_cargado': 'L1',
            'cargabilidad_max': 60.0, 'cabecera_kw': 6000.0, 'cabecera_kvar': 3000.0, 'perdidas_kw': 300.0,
            'perdidas_kvar': kvar_perdidas,
            'vm_min_fases': {'A': [vmin, 'N1'], 'B': [vmin + 0.01, 'N1'], 'C': [vmin + 0.02, 'N1']}}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    modelo = docx.Document()
    modelo.sections[0].header.add_table(1, 1, width=modelo.sections[0].page_width).cell(0, 0).text = \
        'INFORME TECNICO Nº :\nGT-019-PR'
    modelo.add_paragraph('Texto del modelo: AGROINDUSTRIAS DEL MODELO.')
    modelo.save(tmp_path / 'modelo.docx')
    perfil = tmp_path / 'perfil_empresa.json'
    perfil.write_text(json.dumps({'informes': {
        'modelo_estudio': str(tmp_path / 'modelo.docx'),
        'modelo_factibilidad': str(tmp_path / 'modelo.docx'), 'bandas_tension_pct': [95, 105],
        'bandas_cargabilidad_pct': [80, 100], 'cabecera': {'numero': 'INFORME TECNICO'}, 'norma': 'NTCSE'}}),
        encoding='utf-8')
    monkeypatch.setenv('CSG_PERFIL_EMPRESA', str(perfil))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as c:
        yield c


def _espacio(client, tmp_path, *, con=True) -> tuple[str, Path]:
    wid = client.post('/api/workspaces').json()['id']
    salida = tmp_path / 'web' / wid / 'salida'
    salida.mkdir(parents=True, exist_ok=True)
    (salida / 'estudio_sin_flujo_desequilibrado_a.json').write_text(
        json.dumps({'medidas': {'AL01': _medida(0.90)}}), encoding='utf-8')
    time.sleep(0.01)
    if con:
        (salida / 'estudio_con_flujo_desequilibrado_b.json').write_text(
            json.dumps({'medidas': {'AL01': _medida(0.96)}}), encoding='utf-8')
    return wid, salida


FORMULARIO = {'alimentador': 'AL01', 'fecha': '2026-10-15', 'lugar': 'Ica', 'numero': 'GT-300-PR',
              'asunto': 'CAÍDA DE TENSIÓN DEL CLIENTE X', 'destinatario': 'ING. Z',
              'antecedentes': ['El cliente X reclama baja tensión.'],
              'limites': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}}


def test_informe_de_estudio_desde_los_estudios_guardados(client, tmp_path):
    """017:RF-1b, 017:RF-26, 017:RF-29, 017:RF-30 — el Word sale de los estudios de los dos casos y del formulario."""
    wid, salida = _espacio(client, tmp_path)
    obra = {'clase': 'condensador', 'alimentador': 'AL01', 'casos': ['Con proyecto'], 'barra': 'N7',
            'q_kvar': 300}
    r = client.post(f'/api/workspaces/{wid}/obras', json=obra)
    if r.status_code != 201:  # la validación de obras pide la red de DIgSILENT: se guarda a mano
        datos = json.loads((tmp_path / 'web' / wid / 'workspace.json').read_text(encoding='utf-8'))
        datos['obras'] = [obra]
        (tmp_path / 'web' / wid / 'workspace.json').write_text(json.dumps(datos), encoding='utf-8')
    job = client.post(f'/api/workspaces/{wid}/informes/estudio', json=FORMULARIO)
    assert job.status_code == 202
    fin = esperar_trabajo(client, job.json())
    assert fin['status'] == 'done', fin
    resultado = fin['result']
    informe = salida / resultado['informe']
    texto = '\n'.join(p.text for p in docx.Document(informe).paragraphs)
    assert 'CAÍDA DE TENSIÓN DEL CLIENTE X' in texto and 'El cliente X reclama baja tensión.' in texto
    assert 'AGROINDUSTRIAS DEL MODELO' not in texto and 'Sin proyecto' not in texto
    assert '0,900 p.u.' in texto
    assert resultado['estudios'][0] == 'estudio_sin_flujo_desequilibrado_a.json'


def test_sin_estudios_de_sin_proyecto_lo_dice(client, tmp_path):
    """017:RF-29 — sin el flujo de «Sin proyecto» guardado, el trabajo dice qué estudio falta."""
    wid = client.post('/api/workspaces').json()['id']
    fin = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/informes/estudio', json=FORMULARIO).json())
    assert fin['status'] == 'failed' and 'estudio de flujo' in (fin['error'] or '')


def _carga_aplicada(client, wid: str, salida: Path, *, hoja: str = 'formulario') -> None:
    """Lo que deja el paso 3 al aplicar una carga nueva: su informe y su plan."""
    for rol in ('sin', 'con'):
        fichero = next(salida.glob(f'estudio_{rol}_*.json'))
        datos = json.loads(fichero.read_text(encoding='utf-8'))
        datos['project'] = 'PRY'
        if rol == 'con':
            datos['medidas']['AL01']['barras'].append(['B_NUEVA', 0.97])
        fichero.write_text(json.dumps(datos), encoding='utf-8')
    (salida / 'cargas_pf_aplicacion_tok1.json').write_text(json.dumps({
        'project': 'PRY', 'cargas': [{'sed': 'SN1', 'alimentador': 'AL01', 'barra': 'B_NUEVA',
                                      'variacion': 'CN_SN1', 'distancia_m': 120.0}]}), encoding='utf-8')
    planes = salida.parent / 'planes'
    planes.mkdir(parents=True, exist_ok=True)
    (planes / 'cargas_pf_tok1.json').write_text(json.dumps({'nuevas': [
        {'sed': 'SN1', 'hoja': hoja, 'alimentador': 'AL01', 'kw': 800.0, 'kvar': 300.0, 'kva_instalado': 1000}]}),
        encoding='utf-8')


#: Sin DIgSILENT: escribe con los flujos ya guardados (063:RF-1 lo hace en el botón).
FACTIBILIDAD = {'project': 'PRY', 'alimentador': 'AL01', 'sed': 'SN1', 'fecha': '2026-10-15',
                'preparar_casos': False,
                'asunto': 'FACTIBILIDAD DE SUMINISTRO', 'factor_carga': 0.6,
                'limites': FORMULARIO['limites'],
                'solicitud': {'cliente': 'EMPRESA X', 'ubicacion': 'Fundo Y, Ica', 'tipo_solicitud': 'factibilidad',
                              'potencia_kw': 800, 'fecha_solicitud': '2026-09-01', 'set_nombre': 'SET Z',
                              'tension_kv': 10, 'transformador': '25 MVA 60/10 kV', 'expediente': 'EXP-1',
                              'en_concesion': True},
                'perdidas_reconocidas': {'reconocido_kw_pct': 5, 'reconocido_kwh_pct': 4, 'precio_compra': 0.2},
                'transformador_set': {'kv': 10, 'sin_pct': 70, 'con_pct': 74, 'caso': '2026'}}


def test_contexto_dice_lo_que_ya_guardo_la_web(client, tmp_path):
    """017:RF-75, 017:RF-89, 017:RF-104 — estudios, cargas aplicadas e informes, sin DIgSILENT."""
    wid, salida = _espacio(client, tmp_path)
    _carga_aplicada(client, wid, salida)
    r = client.get(f'/api/workspaces/{wid}/informes', params={'project': 'PRY', 'feeder': ['AL01']})
    assert r.status_code == 200, r.text
    ctx = r.json()
    assert ctx['faltan'] == {'factibilidad': [], 'estudio': []}
    assert ctx['estudios']['sin']['alimentadores'] == {'AL01': True}
    assert [(c['sed'], c['barra'], c['sola'], c['kw']) for c in ctx['cargas']] == [('SN1', 'B_NUEVA', True, 800.0)]
    otro = client.get(f'/api/workspaces/{wid}/informes', params={'project': 'OTRO', 'feeder': ['AL01']}).json()
    assert otro['cargas'] == [] and otro['estudios']['sin'] is None, 'los flujos de otro proyecto no valen'


def test_informe_de_factibilidad_con_lo_aplicado(client, tmp_path):
    """017:RF-47, 017:RF-52, 017:RF-53, 017:RF-59, 017:RF-71 — punto de diseño en la barra
    de la carga y veredicto con el transformador escrito por el operador."""
    wid, salida = _espacio(client, tmp_path)
    _carga_aplicada(client, wid, salida)
    job = client.post(f'/api/workspaces/{wid}/informes/factibilidad', json=FACTIBILIDAD)
    assert job.status_code == 202, job.text
    fin = esperar_trabajo(client, job.json())
    assert fin['status'] == 'done', fin
    res = fin['result']
    assert res['factible'] is True and res['excesos'] == []
    assert res['punto_diseno']['u_pu'] == 0.97 and round(res['punto_diseno']['kv_ll'], 2) == 9.7
    texto = '\n'.join(p.text for p in docx.Document(salida / res['informe']).paragraphs)
    assert 'EMPRESA X' in texto and 'B_NUEVA' in texto
    generados = client.get(f'/api/workspaces/{wid}/informes', params={'project': 'PRY'}).json()['generados']
    assert [(g['tipo'], g['docx']) for g in generados] == [('factibilidad', res['informe'])]


def test_factibilidad_rechaza_carga_en_bloque_y_formulario_incompleto(client, tmp_path):
    """017:RF-47, 017:RF-96 — antes de empezar: una carga del libro no vale y la solicitud
    sin cliente se rechaza con el campo."""
    wid, salida = _espacio(client, tmp_path)
    _carga_aplicada(client, wid, salida, hoja='Hoja1')
    r = client.post(f'/api/workspaces/{wid}/informes/factibilidad', json=FACTIBILIDAD)
    assert r.status_code == 400 and 'en bloque' in r.json()['detail']
    incompleto = {**FACTIBILIDAD, 'solicitud': {**FACTIBILIDAD['solicitud'], 'cliente': ''}}
    assert client.post(f'/api/workspaces/{wid}/informes/factibilidad', json=incompleto).status_code == 422


def test_formulario_se_conserva_al_reiniciar(client, tmp_path):
    """017:RF-82 — lo escrito en 4.4 vuelve con el contexto, también tras reiniciar la web."""
    wid, _ = _espacio(client, tmp_path)
    datos = {'cab': {'asunto': 'MI ASUNTO'}, 'antecedentes': 'Texto largo.'}
    r = client.put(f'/api/workspaces/{wid}/informes/formulario',
                   json={'project': 'PRY', 'tipo': 'estudio', 'datos': datos})
    assert r.status_code == 200, r.text
    assert client.put(f'/api/workspaces/{wid}/informes/formulario',
                      json={'project': 'PRY', 'tipo': 'otro', 'datos': {}}).status_code == 422
    with TestClient(create_app(tmp_path / 'web')) as otra:
        ctx = otra.get(f'/api/workspaces/{wid}/informes', params={'project': 'PRY'}).json()
    assert ctx['formularios'] == {'estudio': datos}


def test_libro_de_perdidas_se_lee_y_entra_en_el_informe(client, tmp_path, monkeypatch):
    """017:RF-62, 017:RF-93, 017:RF-94 — el libro subido da lo reconocido del alimentador y
    el informe lo usa si no se escribió a mano; sin columnas en el perfil, dice cuáles faltan."""
    import io

    import openpyxl

    wid, salida = _espacio(client, tmp_path)
    _carga_aplicada(client, wid, salida)
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = 'Perdidas'
    hoja.append(['Alimentador', 'Sistema', 'Pérd kW', 'Pérd kWh', 'Precio'])
    hoja.append(['AL01', 'ICA URBANO', 5.1, 4.2, 0.25])
    contenido = io.BytesIO()
    libro.save(contenido)
    r = client.post(f'/api/workspaces/{wid}/informes/perdidas',
                    files={'file': ('perdidas.xlsx', contenido.getvalue())})
    assert r.status_code == 200, r.text
    sin_perfil = client.get(f'/api/workspaces/{wid}/informes', params={'project': 'PRY', 'feeder': ['AL01']})
    assert 'libro_perdidas' in sin_perfil.json()['libro_perdidas']['error']

    perfil = Path(tmp_path / 'perfil_empresa.json')
    datos = json.loads(perfil.read_text(encoding='utf-8'))
    datos['informes']['libro_perdidas'] = {
        'hoja': 'Perdidas', 'columnas': {'alimentador': 'Alimentador', 'sistema_electrico': 'Sistema',
                                         'reconocido_kw_pct': 'Pérd kW', 'reconocido_kwh_pct': 'Pérd kWh'},
        'precio_compra': {'columna': 'Precio'}}
    perfil.write_text(json.dumps(datos), encoding='utf-8')
    ctx = client.get(f'/api/workspaces/{wid}/informes', params={'project': 'PRY', 'feeder': ['AL01']}).json()
    lectura = ctx['libro_perdidas']['lecturas']['AL01']
    assert (lectura['sistema_electrico'], lectura['reconocido_kwh_pct'], lectura['precio_compra']) == \
        ('ICA URBANO', 4.2, 0.25)

    sin_mano = {**FACTIBILIDAD, 'perdidas_reconocidas': {}}
    fin = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/informes/factibilidad', json=sin_mano).json())
    assert fin['status'] == 'done', fin
    resumen = json.loads((salida / fin['result']['json']).read_text(encoding='utf-8'))
    assert resumen['libro']['sistema_electrico'] == 'ICA URBANO'
    assert resumen['perdidas']['actual']['no_reconocida_soles'] is not None


def test_libro_de_perdidas_por_ruta_del_servidor_y_quitarlo(client, tmp_path):
    """017:RF-93 — el libro se indica por su ruta solo en un servidor local, se rechaza si no
    es un libro Excel, y se quita del espacio."""
    import openpyxl

    libro = tmp_path / 'perdidas.xlsx'
    openpyxl.Workbook().save(libro)
    wid, _ = _espacio(client, tmp_path)
    r = client.post(f'/api/workspaces/{wid}/informes/perdidas/path', json={'path': str(libro)})
    assert r.status_code == 403, 'sin saber dónde escucha, las rutas del servidor están cerradas'
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as local:
        assert local.post(f'/api/workspaces/{wid}/informes/perdidas/path',
                          json={'path': str(tmp_path / 'no_existe.xlsx')}).status_code == 400
        txt = tmp_path / 'perdidas.txt'
        txt.write_text('x', encoding='utf-8')
        assert local.post(f'/api/workspaces/{wid}/informes/perdidas/path',
                          json={'path': str(txt)}).status_code == 400
        r = local.post(f'/api/workspaces/{wid}/informes/perdidas/path', json={'path': str(libro)})
        assert r.status_code == 200 and r.json() == {'name': 'perdidas.xlsx', 'origin': 'server'}
        r = local.delete(f'/api/workspaces/{wid}/informes/perdidas')
        assert r.status_code == 200, r.text
        ctx = local.get(f'/api/workspaces/{wid}/informes', params={'project': 'PRY'}).json()
        assert not (ctx.get('libro_perdidas') or {}).get('name')


def test_cargas_del_proyecto_de_transmision_en_el_carril_de_digsilent(client, tmp_path, monkeypatch):
    """017:RF-26, 017:RF-95 — listar las cargas de barra del proyecto de transmisión es un
    trabajo del carril de DIgSILENT con el proyecto pedido; su error llega al operador."""
    from convertersmartgrid.web import services

    wid, salida = _espacio(client, tmp_path)
    planes = []

    def guion(_ws, _ctx, script, plan, **kw):
        planes.append((script, plan, kw.get('args')))
        if plan['project'] == 'MAL':
            return 1, {'error': 'No está el proyecto MAL.'}, salida / 'l.json'
        return 0, {'cargas': [{'nombre': 'LCarga10', 'trafo': 'TR1'}], 'casos': ['2026_D']}, salida / 'l.json'

    monkeypatch.setattr(services, '_guion_pf', guion)
    job = client.post(f'/api/workspaces/{wid}/informes/transformador/cargas', json={'transmision': 'TX1'})
    assert job.status_code == 202 and job.json()['lane'] == 'powerfactory'
    fin = esperar_trabajo(client, job.json())
    assert fin['status'] == 'done', fin
    assert planes[0][0] == 'transformador_set_pf.py' and planes[0][2] == ('--listar',)
    assert fin['result']['project'] == 'TX1' and fin['result']['casos'] == ['2026_D']
    mal = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/informes/transformador/cargas',
                                              json={'transmision': 'MAL'}).json())
    assert mal['status'] == 'failed' and 'MAL' in json.dumps(mal, ensure_ascii=False)


def test_transformador_con_el_delta_de_los_flujos_guardados(client, tmp_path, monkeypatch):
    """017:RF-65, 017:RF-67, 017:RF-67b — el Δ de cabecera «Con − Sin» de 4.2 va al guion de
    transmisión; nada se vuelve a simular en el proyecto del alimentador."""
    from convertersmartgrid.web import services

    wid, salida = _espacio(client, tmp_path)
    con = next(salida.glob('estudio_con_*.json'))
    datos = json.loads(con.read_text(encoding='utf-8'))
    datos['medidas']['AL01'].update(cabecera_kw=6800.0, cabecera_kvar=3300.0)
    con.write_text(json.dumps(datos), encoding='utf-8')
    planes = []

    def guion(_ws, _ctx, script, plan, **_kw):
        planes.append((script, plan))
        t = {'nombre': 'TR1', 'kv': 10.0, 'lado': 'buslv'}
        return 0, {'caso': plan.get('caso'), 'sin': {'converge': True, 'trafos': [{**t, 'devanado_pct': 40.0}]},
                   'con': {'converge': True, 'trafos': [{**t, 'devanado_pct': 45.0}]}, 'restituida': True}, \
            salida / 'trafo.json'

    monkeypatch.setattr(services, '_guion_pf', guion)
    job = client.post(f'/api/workspaces/{wid}/informes/transformador',
                      json={'project': '', 'alimentador': 'AL01', 'carga': 'LElCarmen10', 'caso': '2026_D',
                            'transmision': 'AD08'})
    assert job.status_code == 422, 'el proyecto del alimentador es obligatorio'
    job = client.post(f'/api/workspaces/{wid}/informes/transformador',
                      json={'project': 'PRY', 'alimentador': 'AL01', 'carga': 'LElCarmen10', 'caso': '2026_D',
                            'transmision': 'AD08'})
    fin = esperar_trabajo(client, job.json())
    assert fin['status'] == 'done', fin
    script, plan = planes[0]
    assert script == 'transformador_set_pf.py' and plan['project'] == 'AD08'
    assert (plan['delta_kw'], plan['delta_kvar']) == (800.0, 300.0)
    assert fin['result']['devanado'] == {'kv': 10.0, 'sin_pct': 40.0, 'con_pct': 45.0}


def test_informe_de_estudio_con_las_obras_ya_aplicadas(client, tmp_path):
    """017:RF-35 / 019:RF-12 — CA101, 2026-10-15: al aplicarse una obra sale de la lista del
    espacio, y el informe salía solo con el estado actual. Ahora toma las obras aplicadas
    cuya variación está activa en el flujo de «Con proyecto», con la consigna de cabecera
    como etapa de regulación."""
    from convertersmartgrid.web import services

    wid, salida = _espacio(client, tmp_path)
    con = salida / 'estudio_con_flujo_desequilibrado_b.json'
    con.write_text(json.dumps({'medidas': {'AL01': _medida(0.99)},
                               'obras_activas': ['Obra_seccion_AL01', 'Obra_consigna_AL01']}),
                   encoding='utf-8')
    ws = client.app.state.store.get(wid)
    services.registrar_obra_aplicada(ws, '', 'Obra_seccion_AL01', {
        'id': 'x', 'clase': 'seccion', 'alimentador': 'AL01', 'casos': ['Con proyecto'],
        'tramos': ['L1'], 'tipo': {'nombre': 'AA12003D', 'clase': 'TypLne'}, 'km': 6.58})
    services.registrar_obra_aplicada(ws, '', 'Obra_consigna_AL01', {
        'clase': 'consigna', 'alimentador': 'AL01', 'casos': ['Con proyecto'], 'consigna_pu': 1.05})
    services.registrar_obra_aplicada(ws, '', 'Obra_vieja_AL01', {
        'clase': 'condensador', 'alimentador': 'AL01', 'casos': ['Con proyecto'], 'barra': 'BARRA_VIEJA',
        'q_kvar': 300})
    ws.save()
    fin = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/informes/estudio',
                                              json=FORMULARIO).json())
    assert fin['status'] == 'done', fin
    assert fin['result']['etapa'] == 'conductor'
    texto = '\n'.join(p.text for p in docx.Document(salida / fin['result']['informe']).paragraphs)
    assert 'AA12003D' in texto and '1,05 p.u.' in texto
    assert 'BARRA_VIEJA' not in texto, 'una obra cuya variación no está activa no entra'


def test_informe_de_estudio_con_las_imagenes_del_flujo(client, tmp_path):
    """017:RF-11b — sin imágenes del formulario, el informe las dibuja con la geografía y los
    resultados de cada caso, y ya no quedan huecos de imagen."""
    from test_mapa_informe import GEO

    wid, salida = _espacio(client, tmp_path)
    for nombre, u in (('estudio_sin_flujo_desequilibrado_a.json', 0.90),
                      ('estudio_con_flujo_desequilibrado_b.json', 0.99)):
        (salida / nombre).write_text(json.dumps({
            'medidas': {'AL01': _medida(u)}, 'geo': {'AL01': GEO},
            'obras_activas': ['Obra_consigna_AL01']}), encoding='utf-8')
    from convertersmartgrid.web import services

    ws = client.app.state.store.get(wid)
    services.registrar_obra_aplicada(ws, '', 'Obra_consigna_AL01', {
        'clase': 'consigna', 'alimentador': 'AL01', 'casos': ['Con proyecto'], 'consigna_pu': 1.05})
    ws.save()
    fin = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/informes/estudio',
                                              json=FORMULARIO).json())
    assert fin['status'] == 'done', fin.get('error')
    assert not [h for h in fin['result']['huecos'] if h.startswith('imagen')], fin['result']['huecos']
    documento = docx.Document(salida / fin['result']['informe'])
    assert len(documento.inline_shapes) >= 6


def test_vista_previa_de_la_ubicacion_sin_digsilent(client, tmp_path):
    """017:RF-124 — antes de generar, la vista previa dibuja la ubicación del cliente con la
    geografía del último flujo de «Con proyecto», sin DIgSILENT; sin ese flujo lo dice."""
    from test_mapa_informe import GEO

    wid, salida = _espacio(client, tmp_path)
    _carga_aplicada(client, wid, salida)
    pedido = {'project': 'PRY', 'alimentador': 'AL01', 'sed': 'SN1', 'cliente': 'EMPRESA X',
              'potencia_kw': 800, 'codigo_punto': 'E-39533'}
    sin_geo = client.post(f'/api/workspaces/{wid}/informes/ubicacion', json=pedido)
    assert sin_geo.status_code == 400 and 'Con proyecto' in sin_geo.json()['detail']
    con = next(salida.glob('estudio_con_*.json'))
    datos = json.loads(con.read_text(encoding='utf-8'))
    datos['geo'] = {'AL01': {**GEO, 'barras': GEO['barras'] + [['B_NUEVA', -14.012, -75.688, 0.97, 10.0]]}}
    con.write_text(json.dumps(datos), encoding='utf-8')
    r = client.post(f'/api/workspaces/{wid}/informes/ubicacion', json=pedido)
    assert r.status_code == 200, r.text
    vista = r.json()
    assert vista['fichero'].endswith('.png') and (salida / vista['fichero']).stat().st_size > 1000
    assert 'EMPRESA X' in vista['rotulo'] and 'E-39533' in vista['rotulo']


def test_area_de_concesion_la_confirma_el_operador(client, tmp_path):
    """017:RF-125 — el informe dice si el predio está en el área de concesión según lo que
    confirma el operador en 4.4.2; sin confirmar, queda señalado para él."""
    wid, salida = _espacio(client, tmp_path)
    _carga_aplicada(client, wid, salida)
    textos = {}
    for valor in (True, None):
        formulario = {**FACTIBILIDAD, 'solicitud': {**FACTIBILIDAD['solicitud'], 'en_concesion': valor}}
        fin = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/informes/factibilidad',
                                                  json=formulario).json())
        assert fin['status'] == 'done', fin.get('error')
        textos[valor] = '\n'.join(p.text for p in docx.Document(salida / fin['result']['informe']).paragraphs)
    assert 'se encuentra dentro del área de concesión' in textos[True]
    assert 'A CONFIRMAR POR EL OPERADOR' in textos[None]


def test_estado_actual_sin_proyecto_y_proyectado_con_proyecto(client, tmp_path):
    """017:RF-48 / 017:RF-49 / 017:RF-51 — el estado actual sale del flujo de «Sin proyecto», el
    proyectado del de «Con proyecto» con la carga del informe, y la solicitud del formulario."""
    wid, salida = _espacio(client, tmp_path)
    _carga_aplicada(client, wid, salida)
    fin = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/informes/factibilidad',
                                              json=FACTIBILIDAD).json())
    assert fin['status'] == 'done', fin.get('error')
    res = fin['result']
    assert res['estudios'] == ['estudio_sin_flujo_desequilibrado_a.json', 'estudio_con_flujo_desequilibrado_b.json']
    assert res['carga']['sed'] == 'SN1' and res['punto_diseno']['u_pu'] == 0.97     # la barra en «Con»
    texto = '\n'.join(p.text for p in docx.Document(salida / res['informe']).paragraphs)
    for dato in ('EMPRESA X', 'Fundo Y, Ica', '800 kW', '1 de septiembre de 2026', 'SET Z', 'EXP-1'):
        assert dato in texto, dato


def test_progreso_por_pasos_huecos_y_descargas(client, tmp_path):
    """017:RF-97 / 017:RF-102 / 017:RF-103 — el informe avanza por pasos con su detalle en el
    Registro, lista sus huecos con el motivo y deja descargar el Word y su JSON."""
    wid, salida = _espacio(client, tmp_path)
    _carga_aplicada(client, wid, salida)
    sin_trafo = {**FACTIBILIDAD, 'transformador_set': {'kv': None, 'sin_pct': None, 'con_pct': None, 'caso': ''}}
    fin = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/informes/factibilidad',
                                              json=sin_trafo).json())
    assert fin['status'] == 'done', fin.get('error')
    lineas = [(e.get('data') or {}).get('text') or '' for e in client.get(f'/api/workspaces/{wid}/events').json()]
    assert any('Informe: imágenes' in x for x in lineas) and any('Informe: listo' in x for x in lineas)
    assert fin['progress'] and fin['progress']['index'] == fin['progress']['total']
    huecos = fin['result']['huecos']
    assert huecos and all(isinstance(h, str) and h.strip() for h in huecos)
    for clave in ('informe', 'json'):
        r = client.get(f"/api/workspaces/{wid}/files/{fin['result'][clave]}?download=1")
        assert r.status_code == 200 and len(r.content) > 100, clave


def test_rotulo_de_la_carga_nueva_en_las_imagenes():
    """017:RF-109 / 017:RF-117 — el cliente nuevo se rotula «Carga-{nombre}-{kW} kW-Cod {código}»."""
    from convertersmartgrid.mapa_informe import rotulo_de_carga

    assert rotulo_de_carga('EMPRESA X', 800.0, 'E-39533') == 'Carga-EMPRESA X-800 kW-Cod E-39533'
    assert rotulo_de_carga('B', 1250.5, 'N1') == 'Carga-B-1250.5 kW-Cod N1'


def test_asunto_propuesto_con_el_tipo_y_los_alimentadores():
    """017:RF-80 — el asunto propuesto lleva el tipo de informe y los alimentadores."""
    from convertersmartgrid.informes import asunto_propuesto

    assert asunto_propuesto('estudio', ['CA101', 'CA102']) == 'ESTUDIO ELÉCTRICO DE LOS ALIMENTADORES CA101, CA102'
    assert asunto_propuesto('factibilidad', ['SM218'], 'INKA BERRIES') == \
        'FACTIBILIDAD Y PUNTO DE DISEÑO - INKA BERRIES (SM218)'


def test_sin_modelo_ni_limites_en_el_perfil_lo_dice_el_contexto(client, tmp_path, monkeypatch):
    """017:RF-76 / 017:RF-81 / 017:RF-90 / 086:RF-31 — sin el modelo de un tipo, el contexto dice que va
    la plantilla neutra; sin banda ni umbral, los deja vacíos para pedirlos; sin cargas nuevas
    aplicadas en el proyecto, no hay ninguna que elegir."""
    perfil = tmp_path / 'perfil_sin_factibilidad.json'
    perfil.write_text(json.dumps({'informes': {'modelo_estudio': str(tmp_path / 'modelo.docx'),
                                               'cabecera': {'numero': 'INFORME TECNICO'}}}), encoding='utf-8')
    monkeypatch.setenv('CSG_PERFIL_EMPRESA', str(perfil))
    wid, _salida = _espacio(client, tmp_path)
    ctx = client.get(f'/api/workspaces/{wid}/informes', params={'project': 'PRY', 'feeder': ['AL01']}).json()
    assert ctx['faltan']['factibilidad'] == [] and ctx['plantilla_neutra']['factibilidad'] is True
    assert ctx['faltan']['estudio'] == [] and ctx['plantilla_neutra']['estudio'] is False
    assert all(ctx['limites'].get(k) is None for k in ('tension_min_pu', 'tension_max_pu', 'cargabilidad_max_pct'))
    assert ctx['cargas'] == []


def test_sin_proyecto_no_convergido_avisa_y_deja_generar(client, tmp_path, monkeypatch):
    """017:RF-1 / 017:RF-28 / 017:RF-78 — con el último flujo de «Sin proyecto» sin converger, el
    contexto lo marca, el informe se genera y lo dice en su sección; nada pasa por DIgSILENT,
    así que el proyecto queda como estaba."""
    from convertersmartgrid.web import services

    def sin_digsilent(*_a, **_k):
        raise AssertionError('el informe no debe abrir DIgSILENT')

    monkeypatch.setattr(services, '_require_pf', sin_digsilent)
    wid, salida = _espacio(client, tmp_path)
    fichero = salida / 'estudio_sin_flujo_desequilibrado_a.json'
    medida = {**_medida(0.90), 'converge': False}
    fichero.write_text(json.dumps({'medidas': {'AL01': medida}}), encoding='utf-8')
    ctx = client.get(f'/api/workspaces/{wid}/informes', params={'project': '', 'feeder': ['AL01']}).json()
    assert ctx['estudios']['sin']['alimentadores'] == {'AL01': False}
    fin = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/informes/estudio', json=FORMULARIO).json())
    assert fin['status'] == 'done', fin.get('error')
    texto = '\n'.join(p.text for p in docx.Document(salida / fin['result']['informe']).paragraphs)
    assert 'no converge' in texto


def test_sin_caso_con_proyecto_dice_que_paso_lo_crea(client, tmp_path):
    """017:RF-77 — sin el flujo de «Con proyecto» el contexto no lo trae y la factibilidad no se
    genera: dice que hay que ejecutar el estudio de flujo en 4.2."""
    wid, salida = _espacio(client, tmp_path, con=False)
    (salida / 'estudio_con_flujo_desequilibrado_b.json').write_text(
        json.dumps({'medidas': {'AL01': _medida(0.96)}}), encoding='utf-8')
    _carga_aplicada(client, wid, salida)
    (salida / 'estudio_con_flujo_desequilibrado_b.json').unlink()
    ctx = client.get(f'/api/workspaces/{wid}/informes', params={'project': 'PRY', 'feeder': ['AL01']}).json()
    assert ctx['estudios']['con'] is None
    fin = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/informes/factibilidad',
                                              json=FACTIBILIDAD).json())
    assert fin['status'] == 'failed' and 'Con proyecto' in (fin['error'] or '')


def test_resumen_y_miniaturas_al_terminar(client, tmp_path):
    """017:RF-100 / 017:RF-101 — el JSON del informe trae lo que la página resume por caso y
    etapa (tensión mínima, cargabilidad, pérdidas, si cumple, la recomendada), y cada imagen
    que devuelve el trabajo se sirve para su miniatura."""
    from test_mapa_informe import GEO

    wid, salida = _espacio(client, tmp_path)
    for nombre, u in (('estudio_sin_flujo_desequilibrado_a.json', 0.90),
                      ('estudio_con_flujo_desequilibrado_b.json', 0.99)):
        (salida / nombre).write_text(json.dumps({
            'medidas': {'AL01': _medida(u)}, 'geo': {'AL01': GEO},
            'obras_activas': ['Obra_consigna_AL01']}), encoding='utf-8')
    from convertersmartgrid.web import services

    ws = client.app.state.store.get(wid)
    services.registrar_obra_aplicada(ws, '', 'Obra_consigna_AL01', {
        'clase': 'consigna', 'alimentador': 'AL01', 'casos': ['Con proyecto'], 'consigna_pu': 1.05})
    ws.save()
    fin = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/informes/estudio',
                                              json=FORMULARIO).json())
    assert fin['status'] == 'done', fin.get('error')
    res = fin['result']
    datos = client.get(f"/api/workspaces/{wid}/files/{res['json']}").json()
    assert datos['actual']['converge'] and datos['actual']['cargabilidad_max']['valor'] == 60.0
    assert datos['actual']['perdidas']['kw'] == 300.0 and datos['actual']['tension_min']
    assert datos['etapas'] and datos['recomendada'] == datos['etapas'][0]['clave']
    assert datos['cumplen'][datos['recomendada']] is True
    assert len(res['imagenes']) >= 6
    for im in res['imagenes']:
        r = client.get(f"/api/workspaces/{wid}/files/{im['fichero']}")
        assert r.status_code == 200 and r.content[:8] == b'\x89PNG\r\n\x1a\n', im


def test_el_boton_prepara_los_casos_y_corre_los_flujos_en_el_mismo_trabajo(client, tmp_path, monkeypatch):
    """063:RF-1, 063:RF-2, 063:RF-6, 063:RF-7 — sin pasar antes por 4.2: el mismo trabajo prepara
    los casos y corre los flujos (equilibrado y desequilibrado) del alimentador, y el informe toma
    «Cargas nuevas» como el estado proyectado sin obras."""
    from convertersmartgrid.web import services

    # La comprobación previa en DIgSILENT (017:RF-124) tiene sus propias pruebas; aquí, la carga está igual.
    monkeypatch.setattr(services, 'comprobar_carga_en_digsilent', lambda *_a, **_k: ([], None))
    wid, salida = _espacio(client, tmp_path)
    _carga_aplicada(client, wid, salida)
    llamadas = []

    def plan(ws, project, feeders, estudios, ajuste, *a, **k):
        llamadas.append(('plan', project, list(feeders), list(estudios)))
        return {'token': 'tk'}

    def ejecutar(ws, ctx, token):
        llamadas.append(('ejecutar', token))
        # Lo que dejan los estudios: los tres casos, el de «Cargas nuevas» con la carga y sin obras.
        for rol, vmin in (('cargas', 0.93), ('con', 0.96)):
            (salida / f'estudio_{rol}_flujo_desequilibrado_tk.json').write_text(
                json.dumps({'medidas': {'AL01': _medida(vmin)}}), encoding='utf-8')
            time.sleep(0.01)
        return {}

    monkeypatch.setattr(services, 'estudios_plan', plan)
    monkeypatch.setattr(services, 'estudios_ejecutar', ejecutar)
    monkeypatch.setattr(services, 'ajuste_aplicado_en_disco', lambda ws, project, *a: {'id': 'disco:x'})
    fin = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/informes/factibilidad',
                                              json={**FACTIBILIDAD, 'preparar_casos': True}).json())
    assert fin['status'] == 'done', fin.get('error')
    assert llamadas == [('plan', 'PRY', ['AL01'], ['flujo', 'flujo_desequilibrado']), ('ejecutar', 'tk')]
    assert fin['lane'] == 'powerfactory', 'prepara en DIgSILENT: va a su carril (063:RF-1)'
    assert fin['result']['estudios'][1] == 'estudio_con_flujo_desequilibrado_tk.json'
    resumen = json.loads((salida / fin['result']['json']).read_text(encoding='utf-8'))
    assert json.dumps(resumen, ensure_ascii=False).count('Cargas nuevas') >= 1, 'el estado sin obras entra'


def test_ampliacion_nis_y_ficha_llegan_del_formulario_al_word(client, tmp_path):
    """063:RF-14, 063:RF-17, 063:RF-18 — la potencia previa, el NIS y la Pcc y UTM de la ficha
    viajan de la web al Word; antes la API no los aceptaba y el informe no los decía."""
    wid, salida = _espacio(client, tmp_path)
    _carga_aplicada(client, wid, salida)
    cuerpo = {**FACTIBILIDAD,
              'solicitud': {**FACTIBILIDAD['solicitud'], 'potencia_kw': 800, 'potencia_actual_kw': 300,
                            'nis': '123456789', 'codigo_ficha': 'F-77'},
              'punto_ficha': {'pcc_mva': 48.5, 'utm_x': 410000.5, 'utm_y': 8400000.25}}
    fin = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/informes/factibilidad', json=cuerpo).json())
    assert fin['status'] == 'done', fin.get('error')
    assert fin['lane'] == 'engine', 'solo escribir no ocupa el carril de DIgSILENT'
    documento = docx.Document(salida / fin['result']['informe'])
    texto = '\n'.join(p.text for p in documento.paragraphs)
    celdas = ' '.join(c.text for t in documento.tables for fila in t.rows for c in fila.cells)
    assert 'Ampliación de 300 kW a 800 kW (+500 kW)' in texto
    assert 'NIS 123456789' in texto
    assert '48.5' in celdas and '410000.5' in celdas


def test_islas_y_baja_tension_no_deciden_el_informe():
    """063:RF-43, 063:RF-44 — SM218: los nodos 8674 y 8675 a 0 p.u. y la baja de una SED a 0,887 dejaban
    no factible una red cuya media tensión cumple."""
    from convertersmartgrid.estudios_pf import Limites
    from convertersmartgrid.informes import Caso

    medida = {**_medida(0.96), 'barras': [['CAB', 1.0], ['N1', 0.96], ['ISLA', 0.0], ['SED_BT', 0.887]],
              'sin_tension': ['ISLA'], 'barras_mt': ['CAB', 'N1', 'ISLA']}
    limites = Limites(tension_min_pu=0.95, tension_max_pu=1.05, cargabilidad_max_pct=100.0)
    assert Caso.desde_medida('Con', medida, limites).nodos_fuera == 0
    # Una medida guardada antes no lo dice: se juzgan todas, como hasta ahora.
    viejo = {k: v for k, v in medida.items() if k not in ('sin_tension', 'barras_mt')}
    assert Caso.desde_medida('Con', viejo, limites).nodos_fuera == 2


def test_el_desequilibrado_que_no_cuadra_no_entra_en_el_informe(tmp_path):
    """063:RF-45 — SM218: 11 873 kW frente a 9 284 kW, con cuellos del 185 % que no existen. Si cuadra,
    se prefiere el desequilibrado (017:RF-17)."""
    from convertersmartgrid.web import services

    ws = SimpleNamespace(out_dir=tmp_path)
    (tmp_path / 'estudio_sin_flujo_desequilibrado_a.json').write_text(
        json.dumps({'medidas': {'AL01': _medida(0.90)}}), encoding='utf-8')
    (tmp_path / 'estudio_sin_flujo_b.json').write_text(
        json.dumps({'medidas': {'AL01': {**_medida(0.97), 'cabecera_kw': 6050.0}}}), encoding='utf-8')
    cuadra = services._ultimo_estudio(ws, 'sin')
    assert cuadra['_fichero'] == 'estudio_sin_flujo_desequilibrado_a.json' and not cuadra.get('_aviso_flujo')
    (tmp_path / 'estudio_sin_flujo_desequilibrado_a.json').write_text(
        json.dumps({'medidas': {'AL01': {**_medida(0.90), 'cabecera_kw': 7800.0}}}), encoding='utf-8')
    no = services._ultimo_estudio(ws, 'sin')
    assert no['_fichero'] == 'estudio_sin_flujo_b.json' and 'no cuadra' in no['_aviso_flujo']
    assert no['medidas']['AL01']['vm_min_fases'] is None


def test_transformador_opcional_no_impide_concluir(client, tmp_path):
    """063:RF-46 — sin calcular el transformador de la SET: fuera del informe, sin hueco ni exceso."""
    wid, salida = _espacio(client, tmp_path)
    _carga_aplicada(client, wid, salida)
    cuerpo = {k: v for k, v in FACTIBILIDAD.items() if k != 'transformador_set'}
    fin = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/informes/factibilidad', json=cuerpo).json())
    assert fin['status'] == 'done', fin.get('error')
    res = fin['result']
    assert not any('transformador de la SET' in x for x in [*res['huecos'], *res['excesos']]), res


def test_imagenes_de_cargas_nuevas_salen_de_su_flujo(tmp_path, monkeypatch):
    """063:RF-47 — T7 en SM218: el flujo estaba y el informe decía «imagen ... sin obras» como hueco."""
    from convertersmartgrid import mapa_informe
    from convertersmartgrid.web import services

    dibujados = []

    def dibuja(geo, carpeta, nombre, *, estado, **_k):
        dibujados.append((geo, estado))
        return {'tension': carpeta / f'{nombre}_t.png', 'cargabilidad': carpeta / f'{nombre}_c.png'}

    monkeypatch.setattr(mapa_informe, 'imagenes_del_estado', dibuja)
    monkeypatch.setattr(mapa_informe, 'ubicacion_del_cliente', lambda *_a, **_k: tmp_path / 'u.png')
    ws = SimpleNamespace(out_dir=tmp_path)
    config = SimpleNamespace(bandas_tension_pct=(), bandas_cargabilidad_pct=())
    carga = {'alimentador': 'AL01', 'sed': 'S1', 'barra': 'B1'}
    solicitud = SimpleNamespace(cliente='X', potencia_kw=100.0, transformador='', set_nombre='')
    estudio = lambda g: {'geo': {'AL01': g}}
    salida = services._imagenes_factibilidad(ws, None, config, estudio('sin'), estudio('con'), carga, solicitud, 'C',
                                             None, cargas=estudio('car'))
    assert ('car', 'estado proyectado sin obras') in dibujados
    assert set(salida['cargas']) >= {'tension', 'cargabilidad'}
    # Un estudio sin «Cargas nuevas» sigue dibujando los otros dos.
    dibujados.clear()
    salida = services._imagenes_factibilidad(ws, None, config, estudio('sin'), estudio('con'), carga, solicitud, 'C', None)
    assert 'cargas' not in salida and len(dibujados) == 2


def test_cliente_de_otra_carga_se_dice_y_queda_como_hueco(client, tmp_path, monkeypatch):
    """063:RF-49 — T7 en SM218: la carga de INKA'S BERRIES salió con la solicitud de Minera Santa María."""
    from convertersmartgrid import informes
    from convertersmartgrid.informes import cliente_ajeno

    assert cliente_ajeno("AMPC INKA'S BERRIES S.A.C.", 'Minera Santa María S.A.C.')
    assert not cliente_ajeno("AMPC INKA'S BERRIES S.A.C.", 'Incas Berries S.A.C.')
    assert not cliente_ajeno('SN1', 'Minera Santa María S.A.C.'), 'un código no dice de quién es'
    assert not cliente_ajeno("AMPC INKA'S BERRIES S.A.C.", '')

    wid, salida = _espacio(client, tmp_path)
    _carga_aplicada(client, wid, salida)
    url, cuerpo = f'/api/workspaces/{wid}/informes/factibilidad', FACTIBILIDAD
    limpio = esperar_trabajo(client, client.post(url, json=cuerpo).json())
    assert not any('no parece el de la carga' in h for h in limpio['result']['huecos'])
    monkeypatch.setattr(informes, 'cliente_ajeno', lambda *_a: True)
    fin = esperar_trabajo(client, client.post(url, json=cuerpo).json())
    assert any('no parece el de la carga' in h for h in fin['result']['huecos']), fin['result']['huecos']


def test_obras_del_informe_solo_las_activas_de_ese_proyecto_y_alimentador():
    """063:RF-53 — una obra de otro proyecto, de otro alimentador o apagada no se atribuye a esta carga."""
    from convertersmartgrid.web import services

    banco = {'clase': 'condensador', 'alimentador': 'AL01', 'barra': 'N8904', 'q_kvar': 450.0}
    ws = SimpleNamespace(obras_aplicadas=[
        {'project': 'PRY', 'variacion': 'Obra_a', 'obra': banco},
        {'project': 'OTRO', 'variacion': 'Obra_a', 'obra': {**banco, 'barra': 'OTRO_PROYECTO'}},
        {'project': 'PRY', 'variacion': 'Obra_a2', 'obra': {**banco, 'barra': 'APAGADA'}},
        {'project': 'PRY', 'variacion': 'Obra_b', 'obra': {**banco, 'alimentador': 'AL02', 'barra': 'OTRO_ALIM'}},
    ])
    obras = services._obras_del_informe(ws, 'PRY', 'AL01', {}, {'obras_activas': ['Obra_a', 'Obra_b']})
    assert [o['nodo'] for o in obras] == ['N8904'] and obras[0]['tipo'] == 'banco' and obras[0]['kvar'] == 450.0
