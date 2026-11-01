"""Spec 035: la tabla de clientes cruzados dice lo que el ajuste escribirá, en el instante de la máxima."""
from __future__ import annotations

import io
from pathlib import Path

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx2')
pytest.importorskip('python_calamine')
openpyxl = pytest.importorskip('openpyxl')

from fastapi.testclient import TestClient  # noqa: E402

from convertersmartgrid.ajuste_cabecera import Objetivo, derivacion_cliente, fijas_de  # noqa: E402
from convertersmartgrid.perfil_empresa import datos_perfil, factor_potencia_cargas  # noqa: E402
from convertersmartgrid.web.app import create_app  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]


def _xlsx(hojas):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nombre, filas in hojas.items():
        h = wb.create_sheet(nombre)
        for f in filas:
            h.append(f)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _hoja_15min(pico: int):
    filas = [['SUMINISTRO', 'FECHA', 'HORA', 'EA', 'ERI', 'POT']]
    for k in range(24):
        ea = 100.0 if k == pico else 10.0 + k
        filas.append(['11', '01/07/2026', f'{k // 4:02d}:{15 * (k % 4):02d}', ea,
                      7.5 if k == pico else 1.0 + k / 10, ea * 4])
    return filas


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as c:
        yield c


def _subir(client, wid, tipo, hojas, nombre):
    r = client.post(f'/api/workspaces/{wid}/demanda/{tipo}', files=[('files', (nombre, _xlsx(hojas)))])
    assert r.status_code == 200, r.text


def test_la_tabla_dice_la_p_y_la_q_del_instante_de_la_maxima_y_el_ajuste_escribe_esas(client):
    """035:RF-1, 035:RF-2, 035:RF-3, 035:RF-4 — con la máxima de su alimentador, cada cliente
    con su registro de esa fecha y hora (no el de su POT); el que no tiene hoja, con su EA/ERI
    del mes, dicho; y la SED fija suma exactamente lo que muestran sus filas."""
    wid = client.post('/api/workspaces').json()['id']
    _subir(client, wid, 'suministros', {'s': [['Suministro', 'Suministro Act', 'SED', 'RADIAL'],
                                              [11, 9011, 'E1', 'A1'], [12, 9012, 'E1', 'A1'],
                                              [13, 9013, 'E2', 'B1']]}, 'sum.xlsx')
    pico = 9
    _subir(client, wid, 'clientes', {
        'resumen': [['x'], ['Nis', 'EA', 'ERI', 'Pot'], [11, 900.0, 300.0, 400.0],
                    [12, 500.0, 100.0, 50.0], [13, 10.0, 1.0, 5.0]],
        'maestro_lib': [['numero_suministro', 'nombre_hoja_exportacion'], ['11', 'cli11']],
        'cli11': _hoja_15min(pico)}, 'ci.xlsx')
    k = 2                                   # 00:30, la máxima de A1: no es la de la POT de 11
    maxima = {'fecha': '2026-07-01T00:30:00', 'kw': 1000.0, 'kvar': 250.0, 'fp': None}
    r = client.post(f'/api/workspaces/{wid}/demanda/clientes/cruzar',
                    json={'alimentadores': ['A1'], 'maximas': {'A1': maxima}})
    assert r.status_code == 200, r.text
    cruce = r.json()
    assert cruce['maximas'] == {'A1': '2026-07-01 00:30:00'}
    filas = {c['codigo']: c for c in cruce['cruzados']}
    assert set(filas) == {'11', '12'}, 'solo los del alimentador por su radial'
    f11, f12 = filas['11'], filas['12']
    # RF-1: el registro de 00:30, no el de su POT (pico).
    assert f11['fecha_valores'] == '01/07/2026 00:30' and f11['metodo'] == 'REGISTRO_DEL_INSTANTE'
    assert f11['p_kw'] == pytest.approx((10.0 + k) * 4) and f11['q_kvar'] == pytest.approx((1.0 + k / 10) * 4)
    # RF-3: sin hoja, su EA/ERI del mes (o el mínimo del perfil, como el ajuste), dicho.
    assert f12['metodo'] == 'ERI/EA' and f12['fecha_valores'] is None
    objetivo = Objetivo(kw=1000.0, kvar=250.0, medidor='', alimentador='A1', fecha=maxima['fecha'])
    fp_min = factor_potencia_cargas(datos_perfil(), 'factor_potencia_minimo_fijas')
    esperado = derivacion_cliente(f12, objetivo.tan_phi, objetivo.fp, fp_min)
    assert f12['p_kw'] == pytest.approx(esperado['p_kw']) and f12['q_kvar'] == pytest.approx(esperado['q_kvar'])
    # RF-4: lo que el ajuste escribe en E1 es la suma de las filas que se ven.
    fija = fijas_de([f11, f12], objetivo, fp_min)['E1']
    assert fija.kw == pytest.approx(f11['p_kw'] + f12['p_kw'])
    assert fija.kvar == pytest.approx(f11['q_kvar'] + f12['q_kvar'])


def test_la_web_manda_la_maxima_y_la_tabla_muestra_lo_que_se_escribe():
    """035:RF-1, 035:RF-2 — el front cruza con la máxima de cada alimentador marcado y la tabla
    enseña P (kW), Q (kvar), el registro y de dónde salen, y lo que suman las fijas."""
    demanda = (RAIZ / 'frontend' / 'src' / 'components' / 'DemandaMedida.tsx').read_text(encoding='utf-8')
    api = (RAIZ / 'frontend' / 'src' / 'api.ts').read_text(encoding='utf-8')
    app = (RAIZ / 'src' / 'convertersmartgrid' / 'web' / 'app.py').read_text(encoding='utf-8')
    assert 'maximas: dict[str, dict[str, Any]]' in app and 'maximas=body.maximas' in app
    assert '...(maximas ? { maximas } : {})' in api
    assert "feeders.includes(m.alimentador)" in demanda and 'fecha: m.fecha, kw: m.kw, kvar: m.kvar' in demanda
    for pieza in ('>P (kW)</th>', '>Q (kvar)</th>', 'c.fecha_valores', 'ORIGEN_VALORES', 'factor de escala 1'):
        assert pieza in demanda, pieza


def test_el_mes_anterior_solo_si_falta_el_de_la_maxima():
    """035:RF-17 — el libro del mes de la máxima si existe; si no, el anterior más cercano;
    sin anterior, ninguno (sus SED por kVA)."""
    from convertersmartgrid.web.services import mes_anterior_con_libro

    catalogo = [{'mes': '2026-08', 'activo': True}, {'mes': '2026-09', 'activo': True},
                {'mes': '2026-06', 'activo': False}, {'mes': '2025-12', 'activo': True}]
    assert mes_anterior_con_libro(catalogo, '2026-10') == '2026-09'
    assert mes_anterior_con_libro(catalogo, '2026-01') == '2025-12'
    assert mes_anterior_con_libro(catalogo, '2026-07') == '2025-12', 'los inactivos no cuentan'
    assert mes_anterior_con_libro(catalogo, '2025-11') is None


def test_el_plan_y_la_tabla_dicen_el_libro_del_mes_anterior():
    """035:RF-17, 035:RF-18 — solo cuando falta el del mes: el plan cruza con el libro elegido y
    no da el mes distinto por error; plan, tabla e informe lo dicen con su libro y su mes."""
    fuente = (RAIZ / 'src' / 'convertersmartgrid' / 'web' / 'services.py').read_text(encoding='utf-8')
    activo = fuente[fuente.index('def periodo_clientes_activo'):fuente.index('def mes_anterior_con_libro')]
    assert 'not any(\n            str(item.get(\'mes\') or \'\').strip() == periodo for item in active)' in activo
    assert "status='CLIENT_PERIOD_PREVIOUS'" in activo and 'el mes anterior más cercano con libro' in activo
    assert "otro = maximum_period != client_period.period and not previo" in fuente
    assert "periodo=client_period.period," in fuente
    tabla = fuente[fuente.index('def _clientes_en_sus_maximas'):fuente.index('def demanda_excel')]
    assert "evidencia.status == 'CLIENT_PERIOD_PREVIOUS'" in tabla and 'mes = evidencia.period' in tabla


def _hoja_dia(dia: str, pico: int):
    """Hoja de 15 minutos de un día: EA de 10 + k y su pico en ``pico`` (POT 400 kW)."""
    filas = [['SUMINISTRO', 'FECHA', 'HORA', 'EA', 'ERI', 'POT']]
    for k in range(24):
        ea = 100.0 if k == pico else 10.0 + k
        filas.append(['x', dia, f'{k // 4:02d}:{15 * (k % 4):02d}', ea,
                      7.5 if k == pico else 1.0 + k / 10, ea * 4])
    return filas


def _dos_criterios(client):
    """A1 con 11 (hoja del día de la máxima), 14 (hoja de otro día) y 12 (sin hoja)."""
    wid = client.post('/api/workspaces').json()['id']
    _subir(client, wid, 'suministros', {'s': [['Suministro', 'Suministro Act', 'SED', 'RADIAL'],
                                              [11, 9011, 'E1', 'A1'], [12, 9012, 'E1', 'A1'],
                                              [14, 9014, 'E2', 'A1']]}, 'sum.xlsx')
    _subir(client, wid, 'clientes', {
        'resumen': [['x'], ['Nis', 'EA', 'ERI', 'Pot'], [11, 900.0, 300.0, 400.0],
                    [12, 500.0, 100.0, 50.0], [14, 900.0, 300.0, 400.0]],
        'maestro_lib': [['numero_suministro', 'nombre_hoja_exportacion'], ['11', 'cli11'], ['14', 'cli14']],
        'cli11': _hoja_dia('01/07/2026', 9), 'cli14': _hoja_dia('02/07/2026', 9)}, 'ci.xlsx')
    maxima = {'fecha': '2026-07-01T00:30:00', 'kw': 1000.0, 'kvar': 250.0, 'fp': None}

    def cruzar(**kw):
        r = client.post(f'/api/workspaces/{wid}/demanda/clientes/cruzar',
                        json={'alimentadores': ['A1'], 'maximas': {'A1': maxima}, **kw})
        assert r.status_code == 200, r.text
        return r.json()
    cruzar.wid, cruzar.maxima = wid, maxima
    return cruzar


def test_por_defecto_las_fijas_son_coincidentes_y_la_que_no_tiene_el_instante_no_toma_otro(client):
    """039:RF-1, 039:RF-3, 039:RF-4 — sin elegir, el criterio es «coincidente»: cada fija con su
    EA × 4 y ERI × 4 del instante de la máxima; la que tiene hoja pero no ese registro no toma
    el de su POT, y se dice con el periodo que daría la misma fecha. La que no tiene hoja va
    con su EA/ERI del mes con los dos criterios y no se marca."""
    cruce = _dos_criterios(client)()
    assert cruce['criterio'] == 'coincidente'
    filas = {c['codigo']: c for c in cruce['cruzados']}
    assert filas['11']['metodo'] == 'REGISTRO_DEL_INSTANTE' and filas['11']['p_kw'] == pytest.approx(12 * 4)
    assert filas['14'].get('fecha_valores') is None and filas['14']['metodo'] != 'REGISTRO_DEL_INSTANTE'
    assert '01/07/2026 00:30' in filas['14']['sin_coincidente'] and '2026-07' in filas['14']['sin_coincidente']
    assert filas['12']['metodo'] == 'ERI/EA' and not filas['12'].get('sin_coincidente')
    assert cruce['no_coincidentes'] == [filas['14']['sin_coincidente']]


def test_con_maximo_del_mes_cada_fija_va_con_su_pot_y_el_eri_de_ese_registro(client):
    """039:RF-1, 039:RF-2 — con «máximo del mes», cada fija con la POT máxima de su hoja y el
    ERI × 4 de ese mismo registro, aunque la hoja tenga el instante de la máxima."""
    cruce = _dos_criterios(client)(criterio='maximo_mes')
    assert cruce['criterio'] == 'maximo_mes' and cruce['no_coincidentes'] == []
    filas = {c['codigo']: c for c in cruce['cruzados']}
    for codigo, dia in (('11', '01/07/2026'), ('14', '02/07/2026')):
        f = filas[codigo]
        assert f['fecha_valores'] == f'{dia} 02:15' and f['metodo'].startswith('ERI_DEL_REGISTRO')
        assert f['p_kw'] == pytest.approx(400.0) and f['q_kvar'] == pytest.approx(7.5 * 4)


def test_un_criterio_que_no_existe_se_rechaza(client):
    """039:RF-1 — solo «coincidente» o «maximo_mes»."""
    wid = client.post('/api/workspaces').json()['id']
    r = client.post(f'/api/workspaces/{wid}/demanda/clientes/cruzar', json={'criterio': 'promedio'})
    assert r.status_code == 422


def test_comparar_los_criterios_con_la_cabecera_y_la_red_simulada(client):
    """039:RF-5, 035:RF-28 — un trabajo que no abre DIgSILENT da, por fija, P y Q con su registro
    en los dos criterios; sus sumas (sin la que no tiene el registro del instante); la cabecera
    de la máxima; la P y la Q de la red y de los bancos de la última calibración; y con cada
    criterio, si la medida de cabecera es coherente."""
    from convertersmartgrid.web import services
    from apoyo import esperar_trabajo

    cruzar = _dos_criterios(client)
    ws = client.app.state.store.get(cruzar.wid)
    informe = {'sed': [{'sed': 'E1', 'despues': {'kw': 60.0, 'kvar': 20.0}},
                       {'sed': 'E3', 'despues': {'kw': 500.0, 'kvar': 100.0}}],
               'escenarios': [{'escenario': 'Sin proyecto'}], 'cabecera': {'kw': 1000.0, 'kvar': 90.0},
               'cuadre_q': {'bancos_kvar': 300.0}}
    services._guardar_calibracion(ws, 'P', 'A1', informe)
    r = client.post(f'/api/workspaces/{cruzar.wid}/demanda/clientes/comparar',
                    json={'project': 'P', 'alimentadores': ['A1'], 'maximas': {'A1': cruzar.maxima}})
    assert r.status_code == 202, r.text
    estado = esperar_trabajo(client, r.json())
    assert estado['status'] == 'done', estado
    a1 = estado['result']['alimentadores'][0]
    fijas = {f['codigo']: f for f in a1['fijas']}
    assert fijas['11']['coincidente']['fecha'] == '01/07/2026 00:30'
    assert fijas['11']['maximo_mes']['fecha'] == '01/07/2026 02:15'
    assert fijas['14']['coincidente']['sin_coincidente'] and fijas['14']['maximo_mes']['p_kw'] == pytest.approx(400.0)
    s = a1['sumas']
    assert s['coincidente']['sin_registro'] == 1
    assert s['coincidente']['p_kw'] == pytest.approx(48.0 + fijas['12']['coincidente']['p_kw'])
    assert s['maximo_mes']['p_kw'] == pytest.approx(800.0 + fijas['12']['maximo_mes']['p_kw'])
    assert a1['cabecera'] == {'fecha': '2026-07-01T00:30:00', 'kw': 1000.0, 'kvar': 250.0}
    red = a1['red']
    assert red['cargas_kvar'] == pytest.approx(120.0) and red['red_y_bancos_kvar'] == pytest.approx(-30.0)
    assert red['bancos_kvar'] == pytest.approx(300.0)
    assert red['red_kw'] == pytest.approx(1000.0 - 560.0)
    # 035:RF-28: con cada criterio, la Q de cabecera alcanzable con las escaladas entre FP 1 y su
    # mínimo, y si la medida (250 kvar) cae ahí; nunca una «Q para las escaladas» negativa.
    for criterio in ('coincidente', 'maximo_mes'):
        c = a1['coherencia'][criterio]
        assert c['escaladas_kw'] == pytest.approx(max(0.0, 1000.0 - s[criterio]['p_kw'] - 440.0))
        assert c['q_fp1_kvar'] == pytest.approx(s[criterio]['q_kvar'] - 30.0)
        assert c['q_fp_minimo_kvar'] >= c['q_fp1_kvar']
        dentro = c['q_fp1_kvar'] - 2.5 <= 250.0 <= c['q_fp_minimo_kvar'] + 2.5
        assert c['coherente'] is dentro and (c['lado'] is None) is dentro
    # Sin máxima no hay con qué comparar.
    assert client.post(f'/api/workspaces/{cruzar.wid}/demanda/clientes/comparar',
                       json={'project': 'P'}).status_code == 422


def test_una_calibracion_guardada_sin_cabecera_toma_la_red_de_su_informe_en_disco(client):
    """039:RF-5 — las calibraciones guardadas antes de llevar la cabecera simulada dan la Q de la
    red con su informe de aplicación en disco, del mismo caso."""
    import json

    from convertersmartgrid.web import services
    from apoyo import esperar_trabajo

    cruzar = _dos_criterios(client)
    ws = client.app.state.store.get(cruzar.wid)
    ws.calibraciones = {'P': {'A1': {'nombre': 'la calibración vieja', 'sed': {'E1': [60.0, 20.0]},
                                     'caso': 'Sin proyecto', 'recalibracion': 0}}}
    ws.out_dir.mkdir(parents=True, exist_ok=True)
    (ws.out_dir / 'ajuste_cabecera_aplicacion_tok.json').write_text(json.dumps({
        'project': 'P', 'feeder': 'A1', 'caso': 'Sin proyecto', 'cabecera': {'kw': 1000.0, 'kvar': 50.0},
        'sed': [{'sed': 'E1', 'despues': {'kw': 60.0, 'kvar': 20.0}},
                {'sed': 'E3', 'despues': {'kw': 500.0, 'kvar': 70.0}}],
        'cuadre_q': {'bancos_kvar': 150.0}}), encoding='utf-8')
    r = client.post(f'/api/workspaces/{cruzar.wid}/demanda/clientes/comparar',
                    json={'project': 'P', 'alimentadores': ['A1'], 'maximas': {'A1': cruzar.maxima}})
    red = esperar_trabajo(client, r.json())['result']['alimentadores'][0]['red']
    assert red['red_y_bancos_kvar'] == pytest.approx(50.0 - 90.0) and red['bancos_kvar'] == pytest.approx(150.0)
    assert 'ajuste_cabecera_aplicacion_tok.json' in red['calibracion']
