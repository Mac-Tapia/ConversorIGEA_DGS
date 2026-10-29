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

from igea_dgs.ajuste_cabecera import Objetivo, derivacion_cliente, fijas_de  # noqa: E402
from igea_dgs.perfil_empresa import datos_perfil, factor_potencia_cargas  # noqa: E402
from igea_dgs.web.app import create_app  # noqa: E402

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
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
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
    app = (RAIZ / 'src' / 'igea_dgs' / 'web' / 'app.py').read_text(encoding='utf-8')
    assert 'maximas: dict[str, dict[str, Any]]' in app and 'maximas=body.maximas' in app
    assert '...(maximas ? { maximas } : {})' in api
    assert "feeders.includes(m.alimentador)" in demanda and 'fecha: m.fecha, kw: m.kw, kvar: m.kvar' in demanda
    for pieza in ('>P (kW)</th>', '>Q (kvar)</th>', 'c.fecha_valores', 'ORIGEN_VALORES', 'factor de escala 1'):
        assert pieza in demanda, pieza


def test_el_mes_anterior_solo_si_falta_el_de_la_maxima():
    """035:RF-17 — el libro del mes de la máxima si existe; si no, el anterior más cercano;
    sin anterior, ninguno (sus SED por kVA)."""
    from igea_dgs.web.services import mes_anterior_con_libro

    catalogo = [{'mes': '2026-08', 'activo': True}, {'mes': '2026-09', 'activo': True},
                {'mes': '2026-06', 'activo': False}, {'mes': '2025-12', 'activo': True}]
    assert mes_anterior_con_libro(catalogo, '2026-10') == '2026-09'
    assert mes_anterior_con_libro(catalogo, '2026-01') == '2025-12'
    assert mes_anterior_con_libro(catalogo, '2026-07') == '2025-12', 'los inactivos no cuentan'
    assert mes_anterior_con_libro(catalogo, '2025-11') is None


def test_el_plan_y_la_tabla_dicen_el_libro_del_mes_anterior():
    """035:RF-17, 035:RF-18 — solo cuando falta el del mes: el plan cruza con el libro elegido y
    no da el mes distinto por error; plan, tabla e informe lo dicen con su libro y su mes."""
    fuente = (RAIZ / 'src' / 'igea_dgs' / 'web' / 'services.py').read_text(encoding='utf-8')
    activo = fuente[fuente.index('def periodo_clientes_activo'):fuente.index('def mes_anterior_con_libro')]
    assert 'not any(\n            str(item.get(\'mes\') or \'\').strip() == periodo for item in active)' in activo
    assert "status='CLIENT_PERIOD_PREVIOUS'" in activo and 'el mes anterior más cercano con libro' in activo
    assert "otro = maximum_period != client_period.period and not previo" in fuente
    assert "periodo=client_period.period," in fuente
    tabla = fuente[fuente.index('def _clientes_en_sus_maximas'):fuente.index('def demanda_excel')]
    assert "evidencia.status == 'CLIENT_PERIOD_PREVIOUS'" in tabla and 'mes = evidencia.period' in tabla
