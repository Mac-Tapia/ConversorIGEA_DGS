"""004:RF-112 a RF-115, 028:RF-43 y RF-44: la máxima de diseño es la sostenida de una hora, con el pico de 15 min,
el promedio y el factor de carga como referencia, y lo que se carga es lo que muestra la tabla.

Datos ficticios: medidores ``M1``, ``M2`` y alimentadores ``A1``, ``A2``; ningún nombre ni código real.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from convertersmartgrid.aplicacion import demanda_medida as dm
from convertersmartgrid.dominio.ajuste_cabecera import objetivo_de

T0 = datetime(2026, 7, 1)
Q = timedelta(minutes=15)


def _c(res, nombre):
    """Un campo de la fila; sin él, vacío: sobre d6582a8e la prueba falla por aserción, no por AttributeError."""
    d = res.to_dict() if hasattr(res, 'to_dict') else res
    return d.get(nombre) or {}


def _registros(kws, paso=Q, kvar=None, v=None):
    out = []
    for i, kw in enumerate(kws):
        valores = {'kw': kw, 'kvar': (kvar(i) if kvar else None if kw is None else kw * 0.3)}
        if v is not None:
            valores['v'] = v(i)
        out.append(dm.Registro(T0 + i * paso, valores))
    return out


def _serie_con_pico_aislado():
    """Base de 100 kW; un registro suelto de 900 kW (una transferencia) y una hora seguida de 400 kW."""
    kws = [100.0] * 60
    kws[10] = 900.0
    for i in range(40, 44):
        kws[i] = 400.0
    return kws


def test_pico_aislado_no_fija_la_maxima_y_queda_como_referencia():
    """004:RF-112 — la mayor media de una hora, con la fecha y hora de su último registro; el pico, aparte."""
    res = dm.maxima_de_registros(_registros(_serie_con_pico_aislado()), dm.MaximaCabecera('M1', 'A1'))
    assert res.error is None
    assert res.fecha == (T0 + 43 * Q).isoformat(sep=' ')
    assert res.kw == pytest.approx(400.0) and res.kvar == pytest.approx(120.0)
    assert _c(res, 'ventana') == {'inicio': (T0 + 40 * Q).isoformat(sep=' '), 'fin': res.fecha, 'registros': 4, 'minutos': 15}
    assert _c(res, 'pico') == {'fecha': (T0 + 10 * Q).isoformat(sep=' '), 'kw': 900.0, 'minutos': 15}
    assert _c(res, 'sostenida').get('fecha') == res.fecha and _c(res, 'sostenida').get('kw') == pytest.approx(400.0)
    assert _c(res, 'sostenida').get('sostenida') is True and _c(res, 'sostenida').get('registros') == 4


def test_promedio_sin_ceros_ni_vacios_y_factor_de_carga():
    """004:RF-113, 004:RF-114 — el promedio deja fuera los ceros y los vacíos; el factor, entre la sostenida."""
    kws = _serie_con_pico_aislado() + [0.0, 0.0, None]
    res = dm.maxima_de_registros(_registros(kws), dm.MaximaCabecera('M1', 'A1'))
    validos = [k for k in kws if k]
    assert _c(res, 'registros_promedio') == len(validos) == 60
    assert res.promedio_kw == pytest.approx(sum(validos) / 60)
    assert res.factor_carga == pytest.approx(res.promedio_kw / 400.0)
    assert res.factor_carga_pico == pytest.approx(res.promedio_kw / 900.0)


def test_libro_horario_la_hora_es_el_registro():
    """004:RF-112 — con registros de una hora la ventana es un registro: la sostenida es el mayor, sin aviso."""
    res = dm.maxima_de_registros(_registros([10.0, 50.0, 20.0], paso=timedelta(hours=1)), dm.MaximaCabecera('M1'))
    assert res.kw == 50.0 and res.fecha == (T0 + timedelta(hours=1)).isoformat(sep=' ')
    assert _c(res, 'ventana').get('registros') == 1 and not res.avisos


def test_sin_una_hora_seguida_toma_el_registro_y_lo_dice():
    """004:RF-112 — con huecos que no dejan ninguna hora entera, el mayor registro, y se avisa."""
    regs = [dm.Registro(T0 + timedelta(minutes=m), {'kw': kw}) for m, kw in ((0, 5.0), (15, 9.0), (45, 7.0), (60, 6.0), (90, 4.0))]
    res = dm.maxima_de_registros(regs, dm.MaximaCabecera('M1'))
    assert res.kw == 9.0 and _c(res, 'ventana').get('registros') == 1
    assert any('sin una hora seguida' in a for a in res.avisos)


def test_periodo_elige_la_hora_del_mes():
    """004:RF-112 con 013:RF-11 — la hora sostenida del mes elegido; la del periodo entero, también sostenida."""
    regs = _registros([100.0] * 8)
    regs += [dm.Registro(datetime(2026, 8, 1) + i * Q, {'kw': kw}) for i, kw in enumerate([400.0] * 4 + [100.0] * 4)]
    res = dm.maxima_de_registros(regs, dm.MaximaCabecera('M1'), periodo='2026-07')
    assert res.kw == pytest.approx(100.0) and res.fecha.startswith('2026-07-01')
    assert res.maxima_periodo['mes'] == '2026-08' and res.maxima_periodo['kw'] == pytest.approx(400.0)


def test_en_un_instante_se_carga_la_hora_de_ese_instante_y_la_propia_es_referencia():
    """004:RF-115 — con un instante común, la media de la hora que termina en él; la propia y el pico, aparte."""
    kws = _serie_con_pico_aislado()
    instante = T0 + 25 * Q
    res = dm.maxima_de_registros(_registros(kws, v=lambda i: 22.9 + i / 1000), dm.MaximaCabecera('M1', 'A1'),
                                 periodo='2026-07', instante=instante)
    assert res.fecha == instante.isoformat(sep=' ') and res.kw == pytest.approx(100.0)
    assert res.tension == pytest.approx(22.9 + (22 + 23 + 24 + 25) / 4000)
    assert _c(res, 'sostenida').get('fecha') == (T0 + 43 * Q).isoformat(sep=' ') and _c(res, 'sostenida').get('kw') == pytest.approx(400.0)
    assert _c(res, 'pico').get('kw') == 900.0


@pytest.mark.parametrize('instante', [None, T0 + 25 * Q])
def test_lo_que_se_carga_es_lo_que_muestra_la_fila(instante):
    """028:RF-44 — el objetivo de la calibración sale de kw, kvar y fecha de la fila, nunca de sus referencias."""
    res = dm.maxima_de_registros(_registros(_serie_con_pico_aislado()), dm.MaximaCabecera('M1', 'A1'),
                                 instante=instante)
    fila = res.to_dict()
    obj = objetivo_de(fila)
    assert (obj.kw, obj.kvar, obj.fecha) == (pytest.approx(fila['kw']), pytest.approx(fila['kvar']), fila['fecha'])
    assert _c(fila, 'pico').get('kw') == 900.0 and obj.kw != 900.0, 'el pico va aparte y no es lo que se carga'
    assert _c(fila, 'ventana').get('registros') == 4, 'se carga la media de una hora'
    if instante is not None:
        assert obj.fecha == instante.isoformat(sep=' ') and obj.kw != pytest.approx(_c(fila, 'sostenida').get('kw'))


def test_instante_coincidente_por_la_hora_seguida_de_la_suma():
    """004:RF-112 con 028:RF-28 — un registro suelto en la suma no fija el instante común."""
    a1 = [(T0 + i * Q, kw, 0.0) for i, kw in enumerate(_serie_con_pico_aislado())]
    a2 = [(T0 + i * Q, 50.0, 0.0) for i in range(60)]
    conjunto = dm.instante_coincidente({'A1': a1, 'A2': a2}, {})
    assert conjunto['fecha'] == T0 + 43 * Q
    assert conjunto['por_alimentador'] == {'A1': pytest.approx(400.0), 'A2': pytest.approx(50.0)}
    assert conjunto['total_kw'] == pytest.approx(450.0)


def test_maxima_de_barra_y_su_valor_por_la_hora_seguida():
    """004:RF-112 con 022:RF-39, RF-84 — la barra también por su hora sostenida, y su valor en un instante."""
    t1 = [(T0 + i * Q, kw, 1.0) for i, kw in enumerate(_serie_con_pico_aislado())]
    t2 = [(T0 + i * Q, 10.0, 1.0) for i in range(60)]
    mx = dm.maxima_de_barra([t1, t2])
    assert mx['fecha'] == T0 + 43 * Q and mx['kw'] == pytest.approx(410.0) and mx['kvar'] == pytest.approx(2.0)
    en = dm.valor_de_barra_en([t1, t2], T0 + 10 * Q)
    assert en['kw'] == pytest.approx((900.0 + 300.0) / 4 + 10.0) and en['registros'] == 4


def test_instante_del_sistema_por_la_hora_seguida():
    """004:RF-112 con 028:RF-31 — el instante del sistema eléctrico tampoco lo fija un registro suelto."""
    alta = [(T0 + i * Q, kw, 0.0) for i, kw in enumerate(_serie_con_pico_aislado())]
    comun = dm.instante_de_barras_de_alta({'B 60 kV': [alta]})
    assert comun['fecha'] == T0 + 43 * Q and comun['total_kw'] == pytest.approx(400.0)


def test_maximas_propias_del_desplegable_son_sostenidas():
    """004:RF-112 con 028:RF-32 — la opción de la máxima de cada cabecera es la misma sostenida de la tabla."""
    curva = [(T0 + i * Q, kw, 0.0) for i, kw in enumerate(_serie_con_pico_aislado())]
    assert hasattr(dm, 'sostenida_de_curva'), 'falta la máxima sostenida de una curva'
    hallada = dm.sostenida_de_curva(curva)
    assert hallada == {'fecha': T0 + 43 * Q, 'kw': pytest.approx(400.0), 'sostenida': True}


# =========================================================================== web: lo que se carga es la tabla
@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from convertersmartgrid.presentacion.web.app import create_app

    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as c:
        yield c


def _xlsx(hojas):
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nombre, filas in hojas.items():
        h = wb.create_sheet(nombre)
        for f in filas:
            h.append(f)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _kw_a1(i):
    return 900.0 if i == 10 else 400.0 if 40 <= i <= 43 else 100.0


def _kw_a2(i):
    return 300.0 if 70 <= i <= 73 else 50.0


def _subir_libros(client, wid):
    medidores = {'h': [['codigo alimentador', 'Medidor', 'Nivel Tension', 'siglas'], ['A1', 'M1', 10, 'X'],
                       ['A2', 'M3', 10, 'X'], ['Barra', 'B-X6T1', 60, 'X']]}
    filas = {k: [['Local Time', 'kW tot', 'kVAR tot']] for k in ('M1', 'M3', 'B-X6T1')}
    for i in range(96):
        t = T0 + i * Q
        filas['M1'].append([t, _kw_a1(i), 10.0])
        filas['M3'].append([t, _kw_a2(i), 5.0])
        filas['B-X6T1'].append([t, _kw_a1(i) + _kw_a2(i), 15.0])
    for tipo, hojas in (('medidores', medidores), ('cabecera', filas)):
        r = client.post(f'/api/workspaces/{wid}/demanda/{tipo}', files=[('files', ('libro.xlsx', _xlsx(hojas)))])
        assert r.status_code == 200, r.text


def _buscar(client, wid, **cuerpo):
    from apoyo import esperar_trabajo

    pares = [{'alimentador': a, 'medidor': m} for a, m in (('A1', 'M1'), ('A2', 'M3'))]
    estado = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar',
                                                 json={'medidores': pares, **cuerpo}).json())
    assert estado['status'] == 'done', estado
    return estado['result']


def _cargado(fila):
    """Lo que el plan del ajuste toma de la fila: ``ajuste_plan`` pasa cada fila a ``objetivo_de`` (006:RF-1)."""
    obj = objetivo_de(fila)
    return obj.fecha, obj.kw, obj.kvar


def test_modo_coincidente_carga_el_instante_comun_de_la_tabla(client):
    """028:RF-44 — coincidente: todos en el mismo instante, el de la hora seguida de mayor suma; se carga eso."""
    wid = client.post('/api/workspaces').json()['id']
    _subir_libros(client, wid)
    res = _buscar(client, wid, coincidente=True)
    comun = (T0 + 43 * Q).isoformat(sep=' ')
    assert res.get('ambito') == 'coincidente' and res['instante'] == comun
    filas = {r['alimentador']: r for r in res['resultados']}
    assert {r['fecha'] for r in filas.values()} == {comun}
    assert _cargado(filas['A1']) == (comun, pytest.approx(400.0), pytest.approx(10.0))
    assert _cargado(filas['A2']) == (comun, pytest.approx(50.0), pytest.approx(5.0))
    # La propia y el pico, solo referencia: no son lo que se carga.
    assert _c(filas['A2'], 'sostenida').get('kw') == pytest.approx(300.0) and _c(filas['A2'], 'sostenida').get('fecha') != comun
    assert _c(filas['A1'], 'pico').get('kw') == 900.0
    assert res['coincidente']['total_kw'] == pytest.approx(sum(r['kw'] for r in filas.values()))


def test_modo_no_coincidente_carga_la_maxima_sostenida_de_cada_uno(client):
    """028:RF-44 — no coincidente: cada alimentador su máxima sostenida, con su fecha; se carga eso."""
    wid = client.post('/api/workspaces').json()['id']
    _subir_libros(client, wid)
    res = _buscar(client, wid)
    assert res.get('ambito') == 'propia'
    filas = {r['alimentador']: r for r in res['resultados']}
    assert _cargado(filas['A1']) == ((T0 + 43 * Q).isoformat(sep=' '), pytest.approx(400.0), pytest.approx(10.0))
    assert _cargado(filas['A2']) == ((T0 + 73 * Q).isoformat(sep=' '), pytest.approx(300.0), pytest.approx(5.0))
    for r in filas.values():
        assert (r['fecha'], r['kw']) == (_c(r, 'sostenida').get('fecha'), pytest.approx(_c(r, 'sostenida').get('kw')))
    propias = {x['alimentador']: x for x in res['maximas_propias']}
    assert propias['A1']['fecha'] == filas['A1']['fecha'] and propias['A1']['kw'] == pytest.approx(400.0)


def test_modo_sistema_carga_el_instante_del_sistema(client, monkeypatch):
    """028:RF-43, RF-44 — sistema eléctrico: un único instante de sus barras de 60 kV para todos, sin mezclar."""
    from convertersmartgrid.dominio.estructura import estructura_de_dict
    from convertersmartgrid.presentacion.web import services

    e = estructura_de_dict({'zonales': [{'nombre': 'Z', 'sets': [
        {'codigo': 'SET X', 'nombre': 'Equis', 'siglas': ['X'], 'alimentadores': ['A1', 'A2']}]}]})
    monkeypatch.setattr(services, 'estructura_del_espacio', lambda _ws: e)
    monkeypatch.setattr(services, '_kv_alimentadores', lambda _ws: {})
    wid = client.post('/api/workspaces').json()['id']
    _subir_libros(client, wid)
    res = _buscar(client, wid, por_barra=True, sistema_60kv=True)
    comun = (T0 + 43 * Q).isoformat(sep=' ')
    assert res.get('ambito') == 'sistema' and res['sistema_60kv']['fecha'] == comun
    filas = {r['alimentador']: r for r in res['resultados']}
    assert {r['fecha'] for r in filas.values()} == {comun}
    assert _cargado(filas['A1'])[:2] == (comun, pytest.approx(400.0))
    assert _cargado(filas['A2'])[:2] == (comun, pytest.approx(50.0))
    assert _c(filas['A2'], 'sostenida').get('fecha') == (T0 + 73 * Q).isoformat(sep=' ')
