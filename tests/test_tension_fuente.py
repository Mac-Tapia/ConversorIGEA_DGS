"""Spec 021, RF-71 a RF-85: la tensión medida en la cabecera, en la tabla de la máxima y en la fuente.

El usuario, el 2026-11-12, con la tabla «2.2 · Máxima de cabecera» de PA217 (L-PA235, 9 537,88 kW el
2026-03-03 10:00): «quiero que en esta tabla se extraiga la tensión del mismo instante de la columna
VLL avg mean y esa tensión se suba a la fuente en pu en DIgSILENT». Libros sintéticos sorteados: ningún
libro de una empresa; DIgSILENT no se ejecuta (P11), el guion se prueba con dobles.
"""
from __future__ import annotations

import inspect
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip('python_calamine')
openpyxl = pytest.importorskip('openpyxl')

from apoyo import cargar_herramienta, esperar_trabajo  # noqa: E402
from convertersmartgrid import demanda_medida as dm  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 3, 1)


def _libro(path: Path, hojas: dict[str, list[list]]) -> Path:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nombre, filas in hojas.items():
        h = wb.create_sheet(nombre)
        for f in filas:
            h.append(f)
    wb.save(path)
    return path


def _serie(semilla: int, n: int, titulos: list[str], tension) -> tuple[list[list], int]:
    """Hoja con ``n`` registros de 15 min y la máxima en un registro sorteado; ``tension(i)`` da las
    celdas de tensión de cada registro, en el orden de ``titulos[3:]``."""
    rng = random.Random(semilla)
    pico = rng.randrange(n)
    filas = [titulos]
    for i in range(n):
        kw = 9537.88 if i == pico else rng.uniform(2000.0, 9000.0)
        filas.append([T0 + timedelta(minutes=15 * i), kw, rng.uniform(100.0, 2600.0), *tension(i)])
    return filas, pico


def _maxima(tmp_path, filas, alias=dm.ALIAS, **kw) -> dm.MaximaCabecera:
    libro = _libro(tmp_path / 'cabecera.xlsx', {'MED': filas})
    return dm.maximas([libro], [('A1', 'MED')], alias=alias, **kw)[0]


# ----------------------------------------------------------------- T22: el lector

@pytest.mark.parametrize('semilla', [3, 17, 2026])
def test_vll_avg_mean_del_mismo_registro_en_voltios(tmp_path, semilla):
    """021:RF-71, 021:RF-74, 021:RF-75 — la tensión es la de «Vll avg mean» del registro del kW máximo,
    no la de otro; en V con 22,9 kV nominales, 23 536,27 V son 23,536 kV y 1,0278 pu."""
    rng = random.Random(semilla)
    n = rng.randint(40, 200)
    valores = [rng.uniform(22000.0, 23900.0) for _ in range(n)]
    filas, pico = _serie(semilla, n, ['Local Time', 'kW tot', 'kVAR tot', 'Vll ab mean', 'Vll avg mean',
                                      'Vll bc mean', 'Vll ca mean'],
                         lambda i: [valores[i] - 50.0, valores[i], valores[i] + 20.0, valores[i] + 30.0])
    valores[pico] = 23536.27
    filas[pico + 1][4] = 23536.27
    r = _maxima(tmp_path, filas)
    assert r.kw == pytest.approx(9537.88) and r.fecha == (T0 + timedelta(minutes=15 * pico)).isoformat(sep=' ')
    assert r.tension == pytest.approx(23536.27) and r.tension_columna == 'Vll avg mean'
    dm.poner_tension(r, 22.9)
    assert r.tension_kv == pytest.approx(23.53627)
    assert round(r.tension_pu, 4) == 1.0278 and r.tension_nominal_kv == 22.9
    assert r.tension_aviso is None
    assert 'tension' not in r.columnas            # no es una magnitud de la hoja (RF-25, RF-44)


def test_solo_las_de_linea_en_kv_dan_su_promedio(tmp_path):
    """021:RF-71, 021:RF-74 — una hoja de barra sin la media («Vll ab», «Vll bc», «Vll ca», sin «mean»)
    da el promedio de las tres de ese registro; en kV con 10 kV nominales se queda en kV."""
    filas, pico = _serie(5, 30, ['Local Time', 'kW tot', 'kVAR tot', 'Vll ab', 'Vll bc', 'Vll ca'],
                         lambda i: [10.1, 10.2, 10.3 + i / 1000.0])
    r = dm.poner_tension(_maxima(tmp_path, filas), 10.0)
    assert r.tension == pytest.approx((10.1 + 10.2 + 10.3 + pico / 1000.0) / 3)
    assert r.tension_columna == 'promedio de Vll ab, Vll bc, Vll ca'
    assert r.tension_kv == pytest.approx(r.tension) and r.tension_pu == pytest.approx(r.tension / 10.0)


def test_con_una_vacia_promedia_las_que_tienen_valor(tmp_path):
    """021:RF-71 — un cero o un vacío no es una tensión: no baja el promedio."""
    filas = [['Local Time', 'kW tot', 'Vll ab mean', 'Vll bc mean', 'Vll ca mean'],
             [T0, 100.0, 23000.0, '', 0.0]]
    r = _maxima(tmp_path, filas)
    assert r.tension == pytest.approx(23000.0) and r.tension_columna == 'promedio de Vll ab mean'


def test_sin_tension_se_dice_por_que(tmp_path):
    """021:RF-73 — sin columnas de tensión, sin tensión y con su motivo; con la columna vacía en el
    registro de la máxima, otro motivo. El kW no lleva ningún aviso nuevo."""
    r = _maxima(tmp_path, [['Local Time', 'kW tot', 'kVAR tot'], [T0, 100.0, 5.0]])
    assert r.tension is None and 'no trae «Vll avg»' in r.tension_aviso and not r.avisos
    filas = [['Local Time', 'kW tot', 'Vll avg mean'], [T0, 100.0, ''], [T0 + timedelta(minutes=15), 50.0, 23000.0]]
    r = _maxima(tmp_path, filas)
    assert r.tension is None and 'la columna está vacía' in r.tension_aviso
    assert dm.poner_tension(r, 22.9).tension_kv is None


def test_alias_de_la_empresa(tmp_path):
    """021:RF-72 — una empresa que llama a su tensión de otra forma la declara en su JSON de alias."""
    ruta = tmp_path / 'alias.json'
    ruta.write_text(json.dumps({'tension': ['U linea prom']}), encoding='utf-8')
    alias = dm.cargar_alias(ruta)
    filas = [['Local Time', 'kW tot', 'U linea prom'], [T0, 100.0, 10.05]]
    assert _maxima(tmp_path, filas).tension is None              # sin su alias no se reconoce
    assert _maxima(tmp_path, filas, alias=alias).tension == pytest.approx(10.05)


def test_unidad_por_la_nominal(tmp_path):
    """021:RF-74, 021:RF-76 — el secundario (380 con 22,9 kV) no se toma; sin nominal, 23 536 es V y se
    da en kV sin pu, y se dice; un valor menor que 1 000 sin nominal se toma como kV, y se dice."""
    assert dm.tension_en_kv(23536.27, 22.9) == (pytest.approx(23.53627), None)
    assert dm.tension_en_kv(10.3, 10.0) == (10.3, None)
    kv, aviso = dm.tension_en_kv(380.0, 22.9)
    assert kv is None and 'secundario' in aviso
    r = dm.poner_tension(_maxima(tmp_path, [['Local Time', 'kW tot', 'Vll avg'], [T0, 1.0, 23536.27]]), None)
    assert r.tension_kv == pytest.approx(23.53627) and r.tension_pu is None and 'no se da en pu' in r.tension_aviso
    kv, aviso = dm.tension_en_kv(22.7, None)
    assert kv == 22.7 and 'tomada como kV' in aviso


def test_hoja_partida_sigue_siendo_de_una_magnitud(tmp_path):
    """021:RF-71 — la tensión no cuenta como magnitud: la hoja del kW con tensión y la del kVAR se unen
    por fecha como antes (004:RF-25), y la tensión es la del registro del kW máximo."""
    kw = [['Local Time', 'kW tot', 'Vll avg mean']] + [[T0 + timedelta(minutes=15 * i), 100.0 + i, 22900.0 + i]
                                                        for i in range(6)]
    kvar = [['Local Time', 'kVAR tot']] + [[T0 + timedelta(minutes=15 * i), 10.0 + i] for i in range(6)]
    libro = _libro(tmp_path / 'c.xlsx', {'MED_kW': kw, 'MED_kVAR': kvar})
    [r] = dm.maximas([libro], [('A1', 'MED')])
    assert r.kw == 105.0 and r.kvar == 15.0 and r.tension == 22905.0


def test_en_el_instante_la_tension_de_ese_registro(tmp_path):
    """021:RF-71 — con un instante común (021:RF-50), la tensión es la de ese registro, no la de la máxima."""
    filas = [['Local Time', 'kW tot', 'Vll avg mean']] + [[T0 + timedelta(minutes=15 * i), 100.0 + i, 23000.0 + i]
                                                           for i in range(5)]
    r = _maxima(tmp_path, filas, instante=T0 + timedelta(minutes=15))
    assert r.kw == 101.0 and r.tension == 23001.0


def test_tension_de_la_barra_en_su_instante():
    """021:RF-78 — la media de los medidores de la barra que la miden en ese instante; el que da el
    secundario (380) o no tiene registro no entra y se dice."""
    t = datetime(2026, 3, 3, 10)
    uno = dm.MaximaCabecera(medidor='B-T1', tensiones={t: (23400.0, 'Vll avg mean')})
    dos = dm.MaximaCabecera(medidor='B-T2', tensiones={t: (23600.0, 'promedio de Vll ab, Vll bc, Vll ca')})
    sec = dm.MaximaCabecera(medidor='B-T3', tensiones={t: (380.0, 'promedio de Vll ab, Vll bc, Vll ca')})
    nada = dm.MaximaCabecera(medidor='B-T4')
    x = dm.tension_de_barra([uno, dos, sec, nada], t, 22.9)
    assert x['tension_kv'] == pytest.approx(23.5) and x['tension_pu'] == pytest.approx(23.5 / 22.9)
    assert x['tension_medidores'] == ['B-T1', 'B-T2']
    assert any('B-T3' in a and 'secundario' in a for a in x['tension_avisos'])
    assert any(a.startswith('B-T4: sin tensión') for a in x['tension_avisos'])
    assert dm.tension_de_barra([nada], t, 22.9)['tension_kv'] is None


def test_maxima_por_barra_lleva_la_tension(tmp_path):
    """021:RF-78 — en la máxima por barra de SET, cada barra con su tensión en su fecha y hora."""
    t = [T0 + timedelta(minutes=15 * i) for i in range(4)]
    hojas = {'B1': [['Local Time', 'kW tot', 'kVAR tot', 'Vll ab', 'Vll bc', 'Vll ca']]
                   + [[f, 1000.0 + i, 10.0, 22950.0 + i, 22960.0 + i, 22970.0 + i] for i, f in enumerate(t)],
             'L1': [['Local Time', 'kW tot', 'Vll avg mean']] + [[f, 400.0 + i, 23000.0] for i, f in enumerate(t)]}
    libro = _libro(tmp_path / 'c.xlsx', hojas)
    barra = dm.BarraMedida(clave='SET1 22,9 kV', set_codigo='SET1', kv=22.9, medidores=['B1'], alimentadores=['A1'])
    res, info, _avisos, _de_barra, _inst = dm.maximas_por_barra([libro], dm.ALIAS, [barra], [('A1', 'L1')], None, [])
    [b] = info
    assert b['fecha'] == t[3].isoformat(sep=' ')
    assert b['tension_kv'] == pytest.approx(22.963) and b['tension_medidores'] == ['B1']
    assert res[0].tension == 23000.0


# ----------------------------------------------------------------- reglas de la consigna

MEDIDA = {'origen': 'medida', 'kv': 23.53627, 'pu': 23.53627 / 22.9, 'nominal_kv': 22.9,
          'fecha': '2026-03-03 10:00:00', 'medidor': 'L-PA235', 'columna': 'Vll avg mean'}


def test_la_fuente_toma_la_de_su_barra_de_set_si_la_mide():
    """021:RF-85 — por SET o por sistema, la de la barra de media de su SET; sin ella (o en la de alta),
    la de su cabecera; con error, ninguna."""
    fila = {'alimentador': 'pa217', 'medidor': 'L-PA235', 'fecha': '2026-03-03 10:00:00', 'tension_kv': 23.536,
            'tension_pu': 1.0278, 'tension_nominal_kv': 22.9, 'tension_columna': 'Vll avg mean'}
    barra = {'clave': 'PA 22,9 kV', 'alta': False, 'kv': 22.9, 'alimentadores': ['PA217'], 'fecha': '2026-03-03 10:00:00',
             'tension_kv': 23.2, 'tension_pu': 23.2 / 22.9, 'tension_medidores': ['B-PA2T2'], 'tension_columna': 'x'}
    alta = {**barra, 'alta': True, 'tension_kv': 61.0}
    assert dm.tension_medida_de_la_fuente(fila, [alta, barra])['kv'] == 23.2
    assert 'B-PA2T2' in dm.tension_medida_de_la_fuente(fila, [barra])['barra']
    assert dm.tension_medida_de_la_fuente(fila, [alta])['medidor'] == 'L-PA235'
    assert dm.tension_medida_de_la_fuente(fila, None)['kv'] == 23.536
    assert dm.tension_medida_de_la_fuente({**fila, 'error': 'x'}, None) is None


def test_consigna_medida_por_defecto_y_la_del_operador_manda():
    """021:RF-79, 021:RF-80, 021:RF-82, 021:RF-84 — sin tocar, la medida; el operador manda (otro valor
    o vacío); si escribe la misma, sigue siendo la medida; fuera de 0,90–1,10, no sola; sin medida, nada."""
    assert dm.consigna_de_la_fuente(MEDIDA, del_operador=False, pu_operador=None) == (MEDIDA, None)
    assert dm.consigna_de_la_fuente(MEDIDA, del_operador=True, pu_operador=1.05) == (
        {'origen': 'operador', 'pu': 1.05}, None)
    assert dm.consigna_de_la_fuente(MEDIDA, del_operador=True, pu_operador=None) == (None, None)
    t, _ = dm.consigna_de_la_fuente(MEDIDA, del_operador=True, pu_operador=1.0278)
    assert t['origen'] == 'medida' and t['pu'] == 1.0278 and t['medidor'] == 'L-PA235'
    t, aviso = dm.consigna_de_la_fuente({**MEDIDA, 'pu': 1.12}, del_operador=False, pu_operador=None)
    assert t is None and 'no se aplica sola' in aviso and '021:RF-82' in aviso
    assert dm.consigna_de_la_fuente(None, del_operador=False, pu_operador=None) == (None, None)


def test_origen_de_la_tension():
    """021:RF-83 — el texto dice la fecha, el medidor, la columna y los kV, o que fue el operador."""
    texto = dm.origen_de_la_tension(MEDIDA)
    assert texto.startswith('medida a las 2026-03-03 10:00:00 en L-PA235 (Vll avg mean), 23.536 kV')
    assert dm.origen_de_la_tension({'origen': 'operador', 'pu': 1.05}).startswith('indicada por el operador')
    assert 'queda como está' in dm.origen_de_la_tension(None)


def test_excel_con_la_tension_al_final(tmp_path):
    """021:RF-77 — el Excel «Descargar máxima y clientes» lleva «V (kV)» y «V (pu)», al final para que
    las columnas de siempre no cambien de letra."""
    fila = {'alimentador': 'PA217', 'medidor': 'L-PA235', 'kw': 9537.88, 'tension_kv': 23.536, 'tension_pu': 1.0278}
    ruta = dm.escribir_excel(tmp_path / 'x.xlsx', cabecera=[fila])
    hoja = openpyxl.load_workbook(ruta)['Cabecera']
    titulos = [c.value for c in hoja[1]]
    assert titulos[:2] == ['Alimentador', 'Medidor'] and titulos.index('Avisos') < titulos.index('V (kV)')
    valores = dict(zip(titulos, [c.value for c in hoja[2]]))
    assert valores['V (kV)'] == 23.536 and valores['V (pu)'] == 1.0278


# ----------------------------------------------------------------- T23 y T24: la web

pytest.importorskip('fastapi')
pytest.importorskip('httpx2')
from test_ajuste_cabecera_web import _plan, _recibido, client  # noqa: E402,F401
from test_demanda_medida_web import _xlsx  # noqa: E402
from convertersmartgrid.web import services  # noqa: E402

CON_TENSION = {'M1': [['Local Time', 'kVAR tot', 'kW tot', 'Vll avg mean']]
               + [[datetime(2026, 7, 1) + timedelta(minutes=15 * i), 10.0, 100.0 + i, 23000.0 + 67.0 * i]
                  for i in range(8)]}


def _maxima_con_tension(client, monkeypatch, nominal, hojas=CON_TENSION):
    monkeypatch.setattr(services, '_kv_alimentadores', lambda _ws: nominal)
    wid = client.post('/api/workspaces').json()['id']
    r = client.post(f'/api/workspaces/{wid}/demanda/cabecera', files=[('files', ('SISTEMA A.xlsx', _xlsx(hojas)))])
    assert r.status_code == 200, r.text
    job = client.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar',
                      json={'medidores': [{'alimentador': 'A1', 'medidor': 'M1'}]}).json()
    estado = esperar_trabajo(client, job)
    assert estado['status'] == 'done', estado
    return wid, job['id'], estado['result']['resultados'][0]


def test_api_de_la_maxima_da_kv_pu_y_la_tension_de_la_fuente(client, monkeypatch):
    """021:RF-75, 021:RF-77, 021:RF-79 — la API da la tensión del registro del kW máximo en kV y en pu
    de la nominal del alimentador en la conversión, y la que iría a su fuente."""
    _wid, _job, r = _maxima_con_tension(client, monkeypatch, {'A1': 22.9})
    assert r['kw'] == 107.0 and r['tension'] == 23469.0 and r['tension_columna'] == 'Vll avg mean'
    assert r['tension_kv'] == pytest.approx(23.469) and r['tension_pu'] == pytest.approx(23.469 / 22.9)
    assert r['tension_fuente']['origen'] == 'medida' and r['tension_fuente']['medidor'] == 'M1'
    assert 'tensiones' not in r and 'curva' not in r


def test_api_sin_nominal_da_kv_y_lo_dice(client, monkeypatch):
    """021:RF-76 — un alimentador que no está en la conversión: kV sin pu, con su motivo."""
    _wid, _job, r = _maxima_con_tension(client, monkeypatch, {})
    assert r['tension_kv'] == pytest.approx(23.469) and r['tension_pu'] is None
    assert 'no se da en pu' in r['tension_aviso']


def test_el_plan_lleva_la_medida_por_defecto(client, monkeypatch):
    """021:RF-79, 021:RF-83 — sin tocar el campo, el plan lleva la tensión medida, con su kV para que
    DIgSILENT la pase a pu con su red externa, y el resumen dice de dónde sale."""
    wid, job, _r = _maxima_con_tension(client, monkeypatch, {'A1': 22.9})
    r = _plan(client, wid, job)
    assert r.status_code == 200, r.text
    [ajuste] = r.json()['ajustes']
    assert ajuste['tension_fuente']['origen'] == 'medida'
    assert ajuste['tension_fuente_origen'].startswith('medida a las 2026-07-01 01:45:00 en M1 (Vll avg mean)')
    plan = _recibido(client, wid, r.json()['token'])
    assert plan['tension_fuente_pu'] == pytest.approx(23.469 / 22.9)
    assert plan['tension_fuente']['kv'] == pytest.approx(23.469)


def test_el_operador_manda_en_el_plan(client, monkeypatch):
    """021:RF-80, 021:RF-61 — lo que escribe el operador manda: otro valor, o vacío (la fuente queda);
    la tensión de todos (``tension_fuente_pu``) sigue valiendo; fuera de 0,9–1,1, 422."""
    wid, job, _r = _maxima_con_tension(client, monkeypatch, {'A1': 22.9})
    plan = _recibido(client, wid, _plan(client, wid, job, tensiones_fuente={'A1': 1.03}).json()['token'])
    assert plan['tension_fuente'] == {'origen': 'operador', 'pu': 1.03}
    plan = _recibido(client, wid, _plan(client, wid, job, tensiones_fuente={'A1': None}).json()['token'])
    assert plan['tension_fuente'] is None and plan['tension_fuente_pu'] is None
    plan = _recibido(client, wid, _plan(client, wid, job, tension_fuente_pu=1.05).json()['token'])
    assert plan['tension_fuente'] == {'origen': 'operador', 'pu': 1.05}
    assert _plan(client, wid, job, tensiones_fuente={'A1': 1.2}).status_code == 422


def test_fuera_de_la_banda_no_se_aplica_sola(client, monkeypatch):
    """021:RF-82 — con 21 kV nominales, 23,469 kV son 1,118 pu: no va sola a la fuente y se avisa."""
    wid, job, _r = _maxima_con_tension(client, monkeypatch, {'A1': 21.0})
    r = _plan(client, wid, job).json()
    assert r['ajustes'][0]['tension_fuente'] is None
    assert any('no se aplica sola' in a for a in r['avisos'])


def test_sin_tension_medida_el_plan_como_antes(client, monkeypatch):
    """021:RF-84, 021:RF-63 — sin tensión en el libro, el plan no pone consigna."""
    hojas = {'M1': [['Local Time', 'kVAR tot', 'kW tot']] + [[datetime(2026, 7, 1), 10.0, 100.0]]}
    wid, job, _r = _maxima_con_tension(client, monkeypatch, {'A1': 22.9}, hojas)
    plan = _recibido(client, wid, _plan(client, wid, job).json()['token'])
    assert plan['tension_fuente'] is None and plan['tension_fuente_pu'] is None


# ----------------------------------------------------------------- T24: el guion

@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('ajuste_cabecera_pf.py', 'tension_fuente_guion', tools_en_path=True)


class _Barra(SimpleNamespace):
    def GetFullName(self):
        return self.loc_name


def _xnet(nombre, barra):
    return SimpleNamespace(loc_name=nombre, usetp=1.0, bus1=SimpleNamespace(cterm=barra))


def test_consigna_en_pu_con_la_nominal_de_su_red_externa(guion):
    """021:RF-75, 021:RF-82 — la medida en kV se pasa a pu con la ``uknom`` de la barra de la red
    externa; la del operador va tal cual; fuera de la banda, no se pone y se dice."""
    assert guion.consigna_en_pu(MEDIDA, 22.9) == (1.0278, None)
    assert guion.consigna_en_pu({**MEDIDA, 'pu': None}, 22.9) == (1.0278, None)
    assert guion.consigna_en_pu({**MEDIDA, 'pu': None}, None)[0] is None
    assert guion.consigna_en_pu({'origen': 'operador', 'pu': 1.05}, 10.0) == (1.05, None)
    pu, aviso = guion.consigna_en_pu(MEDIDA, 20.0)
    assert pu is None and '021:RF-82' in aviso
    assert guion.tension_del_plan({'tension_fuente_pu': 1.02}) == {'origen': 'operador', 'pu': 1.02}
    assert guion.tension_del_plan({'tension_fuente_pu': None}) is None


def test_cada_fuente_con_la_suya(guion):
    """021:RF-81 — dos alimentadores con fuentes distintas, cada una con la suya; una fuente de dos con
    medidas distintas, su promedio y se dice; una que no es de ninguno queda como está."""
    b1, b2, b3 = _Barra(loc_name='B1', uknom=22.9), _Barra(loc_name='B2', uknom=10.0), _Barra(loc_name='B3', uknom=10.0)
    tensiones = {'PA217': MEDIDA, 'PA131': {**MEDIDA, 'kv': 10.2, 'nominal_kv': 10.0, 'pu': 1.02},
                 'PA132': {**MEDIDA, 'kv': 10.4, 'nominal_kv': 10.0, 'pu': 1.04}}
    consigna = guion.consigna_por_fuente(tensiones, {'PA217': 'B1', 'PA131': 'B2', 'PA132': 'B2'})
    assert consigna(_xnet('X1', b1))[0] == 1.0278
    pu, origen = consigna(_xnet('X2', b2))
    assert pu == 1.03 and 'PA131: medida a las' in origen and 'PA132' in origen
    assert consigna(_xnet('X3', b3)) == (None, None)
    assert any('promedio' in a for a in consigna.avisos) and any('X3' in a for a in consigna.avisos)
    # Un solo valor para todos (el del operador, RF-61): también la fuente que no casa.
    todas = guion.consigna_por_fuente({'PA217': {'origen': 'operador', 'pu': 1.05}}, {'PA217': None})
    assert todas(_xnet('X3', b3))[0] == 1.05


def test_escribe_la_consigna_y_su_origen_en_la_tabla_de_cambios(guion):
    """021:RF-83, 021:RF-81 — cada red externa con la suya en los casos, y la tabla de cambios dice de
    dónde salió; los dos caminos de la calibración usan la consigna por fuente."""
    class Caso(SimpleNamespace):
        def Activate(self):
            app.activo = self

    class Esc:
        def Save(self):
            pass

    b1, b2 = _Barra(loc_name='B1', uknom=22.9), _Barra(loc_name='B2', uknom=10.0)
    redes = {r: [_xnet('X1', b1), _xnet('X2', b2)] for r in ('sin', 'con')}
    app = SimpleNamespace(activo=None)
    app.GetCalcRelevantObjects = lambda _f: redes[app.activo.rol]
    app.GetActiveScenario = lambda: Esc()
    consigna = guion.consigna_por_fuente({'PA217': MEDIDA}, {'PA217': 'B1'})
    cambios = guion.fijar_consigna_de_la_fuente(app, consigna, [Caso(rol='sin'), Caso(rol='con')])
    assert [x.usetp for x in redes['sin']] == [1.0278, 1.0] == [x.usetp for x in redes['con']]
    [cambio] = cambios
    assert cambio['fuente'] == 'X1' and cambio['origen'].startswith('PA217: medida a las 2026-03-03 10:00:00')
    [fila] = guion.cambios_en_la_red({'consigna_fuente': cambios})
    assert fila['nuevo']['potencia'] == 1.0278 and 'medida a las' in fila['motivo']
    fuente = inspect.getsource(guion)
    assert fuente.count('consigna_por_fuente(') == 3 and fuente.count("['tension_fuente'] = {**") == 2


# ----------------------------------------------------------------- T23 y T24: el front

DEMANDA = (RAIZ / 'frontend/src/features/powerfactory/DemandaMedida.tsx').read_text(encoding='utf-8')
AJUSTE = (RAIZ / 'frontend/src/features/powerfactory/AjusteCabecera.tsx').read_text(encoding='utf-8')


def test_front_columnas_de_tension():
    """021:RF-77, 021:RF-78 — «V (kV)» y «V (pu)» en la tabla de la máxima y en la de barras de SET."""
    assert DEMANDA.count('>V (kV)</th>') == 2 and DEMANDA.count('V (pu)</th>') == 2
    assert 'fmtNum(r.tension_kv, 3)' in DEMANDA and 'fmtNum(r.tension_pu, 4)' in DEMANDA
    assert 'fmtNum(b.tension_kv, 3)' in DEMANDA and 'colSpan={8}' in DEMANDA


def test_front_campo_de_la_fuente_relleno_con_la_medida():
    """021:RF-79, 021:RF-80, 021:RF-83 — un campo por alimentador, relleno con la medida y su nota; a la
    API van solo los que tocó el operador; el informe dice qué tensión se puso y de dónde salió."""
    assert "tensionInicial(medida)" in AJUSTE and 'notaDeLaMedida(f.medida)' in AJUSTE
    assert 'tensiones_fuente: tensionesFuente' in AJUSTE and 'tension_fuente_pu: uFuente' not in AJUSTE
    assert 'Tensión en la fuente{fuentes.length > 1' in AJUSTE and 'volver a la medida' in AJUSTE
    assert 'inf.tension_fuente.texto' in AJUSTE and 'x.tension_fuente_origen' in AJUSTE
