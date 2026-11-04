"""Spec 073: el número de bancos lo define la tensión en las ventanas de valle.

Usuario, 2026-11-02: «eso lo debe definir las demandas en ventanas de valle donde podría ocurrir
sobretensiones». Curvas sorteadas, sin tamaños ni nombres fijos; la red del oráculo es la de
``test_optimizacion_oraculo``; DIgSILENT, el doble ``fake_pf``.
"""
from __future__ import annotations

import math
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from convertersmartgrid import valle as vl

INICIO = datetime(2026, 3, 1)
PASO = timedelta(minutes=15)


def _forma(t: datetime) -> float:
    """Una forma diaria: de madrugada baja, de tarde alta."""
    return 0.65 + 0.35 * math.sin(2 * math.pi * (t.hour + t.minute / 60 - 9) / 24)


def _curva(rng: random.Random, dias: int, *, kw=None, fp=0.97, por_dia=None, inicio=INICIO, ruido=0.005):
    """Curva de 15 minutos con ruido; ``por_dia``: el nivel de cada día."""
    kw = kw if kw is not None else rng.uniform(800, 9000)
    por_dia = por_dia or [rng.uniform(0.985, 1.015) for _ in range(dias)]
    out = []
    for d in range(dias):
        for i in range(96):
            t = inicio + timedelta(days=d) + i * PASO
            p = kw * _forma(t) * por_dia[d] * rng.uniform(1 - ruido, 1 + ruido)
            out.append((t, p, p * math.tan(math.acos(fp))))
    return out


def _con_valle(rng, dias, desde, largo, *, profundidad=0.7, ruido_dia=0.01):
    """Niveles diarios con un periodo de menor energía de ``desde`` a ``desde + largo``."""
    return [(profundidad if desde <= d < desde + largo else 1.0) * rng.uniform(1 - ruido_dia, 1 + ruido_dia)
            for d in range(dias)]


def _sorteo_de_valle(rng):
    dias = rng.randint(60, 365)
    largo = rng.randint(10, dias // 2)
    desde = rng.randint(8, dias - largo - 8)
    return dias, desde, largo


def _dia(n, inicio=INICIO):
    return (inicio + timedelta(days=n)).date()


@pytest.mark.parametrize('semilla', range(6))
def test_ventana_inicio_y_duracion_salen_de_los_registros(semilla):
    """073:RF-1, 073:RF-2, 073:RF-4, 073:RF-9, 073:RF-35, 073:RF-36 — con medidores, días y valle
    sorteados, la ventana cae en el periodo de menor energía sin dar su duración; el punto para el
    flujo es su registro menor, con kW y kVAR de ese instante; misma entrada, mismo valle."""
    rng = random.Random(semilla)
    dias, desde, largo = _sorteo_de_valle(rng)
    por_dia = _con_valle(rng, dias, desde, largo)
    medidores = {f'M{i}': _curva(rng, dias, por_dia=por_dia) for i in range(rng.randint(1, 4))}
    v = vl.valle_de_alcance('alimentador', medidores, vl.Ajustes())
    assert v.comprobado and v.ventana
    assert abs((v.ventana['inicio'] - _dia(desde)).days) <= 2 and abs((v.ventana['fin'] - _dia(desde + largo - 1)).days) <= 2
    assert v.ventana['duracion_dias'] == (v.ventana['fin'] - v.ventana['inicio']).days + 1
    assert v.ventana['kwh_dia_dentro'] < 0.8 * v.ventana['kwh_dia_fuera']
    assert v.ventana['optimizacion']['semilla'] is None and v.ventana['optimizacion']['ventanas_evaluadas'] > 0
    por: dict = {}
    for c in medidores.values():
        for t, kw, q in c:
            a, b = por.get(t, (0.0, 0.0))
            por[t] = (a + kw, b + q)
    dentro = [t for t in por if v.ventana['inicio'] <= t.date() <= v.ventana['fin']]
    t = min(dentro, key=lambda x: (por[x][0], x))
    assert v.instante['fecha'] == t and v.instante['kw'] == pytest.approx(por[t][0])
    assert v.instante['kvar'] == pytest.approx(por[t][1])
    desordenadas = {k: rng.sample(c, len(c)) for k, c in medidores.items()}
    assert vl.valle_de_alcance('alimentador', desordenadas, vl.Ajustes()) == v


def _exacta_a_mano(fechas, kwh, cobertura):
    """La misma función objetivo, sin sumas acumuladas, para contrastar el óptimo (073:RF-35)."""
    y, sigma = vl._serie_de_busqueda(fechas, kwh)
    d = len(y)
    beta = 2 * math.log(d)
    mejor = None
    for i in range(d):
        for j in range(i + vl.CICLO_SEMANAL - 1, d):
            n = j - i + 1
            span = (fechas[j] - fechas[i]).days + 1
            if d - n < vl.CICLO_SEMANAL or span - n > (1 - cobertura) * span:
                continue
            dentro, fuera = y[i:j + 1], y[:i] + y[j + 1:]
            md, mf = sum(dentro) / n, sum(fuera) / len(fuera)
            if md >= mf:
                continue
            c = sum((x - md) ** 2 for x in dentro) + sum((x - mf) ** 2 for x in fuera) + beta * sigma ** 2 * d / n
            if mejor is None or c < mejor[0] - 1e-9:
                mejor = (c, fechas[i], fechas[j])
    return mejor


@pytest.mark.parametrize('semilla', range(5))
def test_ventana_la_busqueda_da_el_optimo_exacto(semilla):
    """073:RF-35 — el mínimo es el del recorrido directo de la función objetivo, en series sorteadas."""
    rng = random.Random(semilla)
    dias = rng.randint(40, 90)
    desde, largo = rng.randint(7, 20), rng.randint(7, 20)
    kwh = [1000.0 * x for x in _con_valle(rng, dias, desde, largo, profundidad=rng.uniform(0.6, 0.9))]
    fechas = [_dia(i) for i in range(dias)]
    r = vl.optimizar_ventana(fechas, kwh, cobertura=0.9)
    c, ini, fin = _exacta_a_mano(fechas, kwh, 0.9)
    assert (r['inicio'], r['fin']) == (ini, fin) and r['optimizacion']['objetivo'] == pytest.approx(c)
    assert r == vl.optimizar_ventana(fechas, kwh, cobertura=0.9)


@pytest.mark.parametrize('semilla', range(5))
def test_ventana_un_dia_raro_no_gana(semilla):
    """073:RF-35 — un día muy bajo pero solo, ni con valle ni sin él, no es el periodo de menor energía."""
    rng = random.Random(semilla)
    dias = rng.randint(90, 365)
    kwh = [1000.0 * rng.uniform(0.99, 1.01) for _ in range(dias)]
    kwh[rng.randrange(dias)] = 300.0
    fechas = [_dia(i) for i in range(dias)]
    assert vl.optimizar_ventana(fechas, kwh, cobertura=0.9) is None
    desde, largo = 20, rng.randint(15, 40)
    for i in range(desde, desde + largo):
        kwh[i] *= 0.75
    r = vl.optimizar_ventana(fechas, kwh, cobertura=0.9)
    assert r['duracion_dias'] >= 10 and r['inicio'] >= _dia(desde - 2) and r['fin'] <= _dia(desde + largo + 2)


@pytest.mark.parametrize('semilla', range(5))
def test_ventana_sin_periodo_diferenciado_lo_dice(semilla):
    """073:RF-37 — solo ruido o solo el ciclo semanal: no se inventa un periodo; se usa el registro menor."""
    rng = random.Random(semilla)
    dias = rng.randint(60, 300)
    fechas = [_dia(i) for i in range(dias)]
    plano = [1000.0 * rng.uniform(0.98, 1.02) for _ in range(dias)]
    assert vl.optimizar_ventana(fechas, plano, cobertura=0.9) is None
    domingos = [x * (0.6 if f.weekday() == 6 else 1.0) for x, f in zip(plano, fechas, strict=True)]
    assert vl.optimizar_ventana(fechas, domingos, cobertura=0.9) is None
    curva = _curva(rng, 30, kw=2000.0)
    v = vl.valle_de_alcance('alimentador', {'M': curva}, vl.Ajustes())
    assert v.comprobado and v.ventana is None and v.instante['fecha'] == min(curva, key=lambda x: (x[1], x[0]))[0]
    assert any('073:RF-37' in a for a in v.avisos)
    pocos = vl.valle_de_alcance('alimentador', {'M': _curva(rng, 10, kw=500.0)}, vl.Ajustes())
    assert pocos.ventana is None and any('no alcanzan' in a for a in pocos.avisos)


def test_ventana_es_energia_no_kva():
    """073:RF-1 — un periodo de poca energía con mucha Q es valle; uno de poca Q con su energía, no."""
    rng = random.Random(1)
    dias = 120
    filas = []
    for d in range(dias):
        for i in range(96):
            t = INICIO + timedelta(days=d) + i * PASO
            kw = 1000.0 * rng.uniform(0.99, 1.01) * (0.7 if 30 <= d < 50 else 1.0)
            q = 900.0 if 30 <= d < 50 else (50.0 if 80 <= d < 100 else 300.0)
            filas.append((t, kw, q))
    v = vl.valle_de_alcance('alimentador', {'M': filas}, vl.Ajustes())
    assert abs((v.ventana['inicio'] - _dia(30)).days) <= 1 and abs((v.ventana['fin'] - _dia(49)).days) <= 1


def test_ventana_suma_de_kvar_con_signo_contrario():
    """073:RF-4 — con la Q de un medidor capacitiva, el kVAR del punto es la suma con su signo."""
    t = INICIO
    a = [(t + i * PASO, 100.0 + i, 80.0) for i in range(96 * 3)]
    b = [(t + i * PASO, 100.0 + i, -80.0) for i in range(96 * 3)]
    v = vl.valle_de_alcance('set', {'T1': a, 'T2': b}, vl.Ajustes())
    assert v.instante['kvar'] == pytest.approx(0.0)
    assert v.instante['kw'] == pytest.approx(200.0)
    assert v.alcance == 'set'


def test_ventana_un_registro_menor_fuera_del_valle_se_dice():
    """073:RF-3 — si el registro menor queda fuera del valle, se dice, con su fecha y su valor."""
    rng = random.Random(4)
    curva = _curva(rng, 120, kw=1000.0, por_dia=_con_valle(rng, 120, 40, 30, profundidad=0.8))
    i = next(j for j, x in enumerate(curva) if x[0] == INICIO + timedelta(days=90, hours=3))
    curva[i] = (curva[i][0], 0.36 * curva[i][1], 0.36 * curva[i][2])
    curva[i + 1] = (curva[i + 1][0], 0.36 * curva[i + 1][1], 0.36 * curva[i + 1][2])
    v = vl.valle_de_alcance('alimentador', {'M': curva}, vl.Ajustes())
    assert v.ventana['inicio'] <= _dia(45) <= v.ventana['fin'] and v.instante['fecha'] != curva[i][0]
    assert any('073:RF-1' in a and 'fuera del valle' in a for a in v.avisos)


def test_ventana_un_hueco_de_un_medidor_no_es_valle():
    """073:RF-5 — un medidor sin ese registro bajaría la suma: ese instante no cuenta."""
    rng = random.Random(4)
    por_dia = _con_valle(rng, 90, 30, 20)
    a, b = _curva(rng, 90, kw=1000.0, por_dia=por_dia), _curva(rng, 90, kw=1000.0, por_dia=por_dia)
    limpio = vl.valle_de_alcance('alimentador', {'A': a, 'B': b}, vl.Ajustes())
    hueco = {INICIO + timedelta(days=35, hours=3) + i * PASO for i in range(3)}
    b = [x for x in b if x[0] not in hueco]
    v = vl.valle_de_alcance('alimentador', {'A': a, 'B': b}, vl.Ajustes())
    assert v.instante['fecha'] not in hueco and v.apartados['hueco']['registros'] == len(hueco)
    assert (v.ventana['inicio'], v.ventana['fin']) == (limpio.ventana['inicio'], limpio.ventana['fin'])


@pytest.mark.parametrize('motivo', ['cero', 'signo', 'congelado', 'duplicado', 'franja', 'aislada'])
def test_ventana_dato_dudoso_no_define_el_valle(motivo):
    """073:RF-6 — un cero, un signo contrario, un medidor congelado, un duplicado que no cuadra, una
    salida de servicio o un disparo de un registro se apartan con su motivo y no son el valle."""
    rng = random.Random(11)
    curva = _curva(rng, 100, kw=2000.0, por_dia=_con_valle(rng, 100, 30, 25))
    limpio = vl.valle_de_alcance('alimentador', {'M': curva}, vl.Ajustes())
    i0 = next(i for i, x in enumerate(curva) if x[0] == INICIO + timedelta(days=70, hours=11))
    if motivo == 'cero':
        curva[i0] = (curva[i0][0], 0.0, 0.0)
    elif motivo == 'signo':
        curva[i0] = (curva[i0][0], -curva[i0][1], curva[i0][2])
    elif motivo == 'congelado':
        valor = 0.4 * curva[i0][1]
        for j in range(12):
            curva[i0 + j] = (curva[i0 + j][0], valor, 0.1 * valor)
    elif motivo == 'duplicado':
        curva.insert(i0 + 1, (curva[i0][0], 1.0, 0.1))
    elif motivo == 'franja':
        for j in range(16):            # una salida de servicio de horas: residuales que no llegan a cero
            curva[i0 + j] = (curva[i0 + j][0], 12.0 + j, 1.0)
    elif motivo == 'aislada':
        curva[i0] = (curva[i0][0], 0.45 * curva[i0][1], 0.45 * curva[i0][2])
    v = vl.valle_de_alcance('alimentador', {'M': curva}, vl.Ajustes())
    assert (v.ventana['inicio'], v.ventana['fin']) == (limpio.ventana['inicio'], limpio.ventana['fin']), v.apartados
    assert v.instante['fecha'] == limpio.instante['fecha'] and v.apartados[motivo]['registros'] >= 1
    assert v.apartados[motivo]['motivo'] and 'demanda' not in v.apartados[motivo]['motivo']   # 073:RF-41


def test_ventana_dias_enteros_en_cero_no_son_el_valle():
    """073:RF-6, 073:RF-7 — días fuera de servicio, en cero, son lo que menos energía tendrían; se apartan
    y el valle es el periodo de energía real."""
    rng = random.Random(14)
    curva = _curva(rng, 150, kw=1500.0, por_dia=_con_valle(rng, 150, 90, 30))
    curva = [(t, 0.0, 0.0) if _dia(20) <= t.date() <= _dia(40) else (t, kw, q) for t, kw, q in curva]
    v = vl.valle_de_alcance('alimentador', {'M': curva}, vl.Ajustes())
    assert v.apartados['cero']['registros'] == 21 * 96
    assert abs((v.ventana['inicio'] - _dia(90)).days) <= 2 and v.instante['kw'] > 0


def test_ventana_el_valle_de_cada_noche_no_se_aparta():
    """073:RF-6 — la noche baja todas las noches: su franja también baja, y no es una salida."""
    rng = random.Random(21)
    curva = [(t, kw * (0.15 if 2 <= t.hour < 5 else 1.0), q * (0.15 if 2 <= t.hour < 5 else 1.0))
             for t, kw, q in _curva(rng, 40, kw=3000.0, por_dia=_con_valle(rng, 40, 10, 12))]
    v = vl.valle_de_alcance('alimentador', {'M': curva}, vl.Ajustes())
    assert 2 <= v.instante['fecha'].hour < 5
    assert 'franja' not in v.apartados and 'aislada' not in v.apartados


def test_ventana_convencion_de_signo_al_reves_no_es_error():
    """073:RF-6 — un medidor que exporta en negativo se toma con el signo de su mediana."""
    curva = [(t, -kw, q) for t, kw, q in _curva(random.Random(5), 8, kw=1000.0)]
    v = vl.valle_de_alcance('alimentador', {'M': curva}, vl.Ajustes())
    assert v.comprobado and v.instante['kw'] > 0 and 'signo' not in v.apartados


def test_ventana_cruza_un_dia_sin_datos_solo_si_le_quedan_bastantes():
    """073:RF-7 — un día sin datos no cuenta; una ventana larga lo cruza y dice cuántos tiene con dato."""
    rng = random.Random(31)
    curva = _curva(rng, 200, kw=1000.0, por_dia=_con_valle(rng, 200, 60, 60))
    roto = _dia(90)
    un_dia = [x for x in curva if x[0].date() != roto]
    v = vl.valle_de_alcance('alimentador', {'M': un_dia}, vl.Ajustes())
    assert v.ventana['inicio'] < roto < v.ventana['fin']
    assert v.ventana['dias_con_dato'] == v.ventana['duracion_dias'] - 1
    # Sin un tercio de sus días, ya no cabe en la cobertura: la ventana no los salta.
    rotos = {_dia(60 + i) for i in range(0, 60, 3)}
    v = vl.valle_de_alcance('alimentador', {'M': [x for x in curva if x[0].date() not in rotos]}, vl.Ajustes())
    assert v.ventana is None or v.ventana['dias_con_dato'] >= 0.9 * v.ventana['duracion_dias']


def test_ventana_medidor_con_pocos_registros_sale_de_la_suma_y_se_dice():
    """073:RF-8 — Chincha, julio de 2026: 801 de 2 976 registros de una barra de 8 kW dejaban sin
    instantes a todas; ese medidor sale y se nombra."""
    rng = random.Random(41)
    bueno = _curva(rng, 20, kw=5000.0)
    malo = rng.sample(_curva(rng, 20, kw=8.0), 400)
    v = vl.valle_de_alcance('sistema', {'BUENO': bueno, 'MALO': malo}, vl.Ajustes())
    assert v.excluidos == ['MALO'] and any('MALO' in a for a in v.avisos)
    assert v.registros >= 0.9 * len(bueno)


def test_ventana_sin_ningun_instante_valido_no_revienta():
    """073:RF-10 — sin instante válido, el valle sin comprobar con su motivo."""
    curva = [(INICIO + i * PASO, 0.0, 0.0) for i in range(96 * 3)]
    for entrada in ({'M': curva}, {'M': []}, {}):
        v = vl.valle_de_alcance('alimentador', entrada, vl.Ajustes())
        assert not v.comprobado and v.instante is None and v.motivo


def test_ventana_por_periodo():
    """073:RF-2 — con ``periodo`` (025:RF-7), solo los registros de ese mes o año."""
    curva = _curva(random.Random(2), 60)
    v = vl.valle_de_alcance('alimentador', {'M': curva}, vl.Ajustes(), periodo='2026-04')
    assert v.instante['fecha'].month == 4 and v.anios == [2026]


def test_ventana_kvar_ausente_se_dice():
    """073:RF-4 — un medidor sin kVAR da el valle en energía igual, dicho; un dato sin Q no se inventa."""
    curva = [(t, kw, None) for t, kw, _q in _curva(random.Random(6), 5, kw=700.0)]
    v = vl.valle_de_alcance('alimentador', {'M': curva}, vl.Ajustes())
    assert v.comprobado and v.instante['kvar'] is None
    assert any('kVAR' in a for a in v.avisos)


def test_ventana_varios_anios_sin_mezclar_y_si_coinciden():
    """073:RF-38 — cada año por su cuenta: el crecimiento no hace del año más antiguo el valle; usa el
    último, dice los años y si coinciden en la época."""
    rng = random.Random(51)
    a1, a2, a3 = datetime(2024, 1, 1), datetime(2025, 1, 1), datetime(2026, 1, 1)
    def anio(inicio, kw, desde):
        dias = (datetime(inicio.year + 1, 1, 1) - inicio).days
        return _curva(rng, dias, kw=kw, inicio=inicio, por_dia=_con_valle(rng, dias, desde, 40))
    misma = anio(a1, 1000.0, 150) + anio(a2, 1400.0, 155) + anio(a3, 1900.0, 150)
    v = vl.valle_de_alcance('alimentador', {'M': misma}, vl.Ajustes())
    assert v.anios == [2024, 2025, 2026] and [x['anio'] for x in v.ventanas] == [2024, 2025, 2026]
    assert v.coinciden is True and v.ventana['anio'] == 2026 and v.instante['fecha'].year == 2026
    assert all(abs(x['duracion_dias'] - 40) <= 4 for x in v.ventanas)
    otra = anio(a1, 1000.0, 30) + anio(a2, 1400.0, 250)
    v = vl.valle_de_alcance('alimentador', {'M': otra}, vl.Ajustes())
    assert v.coinciden is False and any('NO coinciden' in a for a in v.avisos)
    r = vl.puntos_de_valle(v, {'M': {'alimentador': 'F', 'kw': 2000.0, 'kvar': 500.0}})
    assert r['anios'] == [2024, 2025] and r['coinciden'] is False and len(r['ventanas']) == 2


def test_ventana_tan_baja_que_puede_ser_una_transferencia_se_dice():
    """073:RF-36 — una ventana de meses muy por debajo del resto puede ser una transferencia: se avisa."""
    rng = random.Random(62)
    v = vl.valle_de_alcance('alimentador', {'M': _curva(rng, 200, kw=900.0, por_dia=_con_valle(rng, 200, 50, 90, profundidad=0.3))},
                            vl.Ajustes())
    assert v.ventana and any('transferencia' in a for a in v.avisos)


def test_ventana_que_toca_el_borde_se_dice():
    """073:RF-36 — si el valle toca el principio o el final de los registros, puede seguir fuera de ellos."""
    rng = random.Random(61)
    v = vl.valle_de_alcance('alimentador', {'M': _curva(rng, 100, kw=900.0, por_dia=_con_valle(rng, 100, 0, 25))}, vl.Ajustes())
    assert v.ventana and any('borde' in a for a in v.avisos)


def test_ventana_lee_con_los_lectores_de_demanda_medida(tmp_path):
    """073:RF-11 — el valle de un libro de cabecera, por ``demanda_medida.maximas``."""
    openpyxl = pytest.importorskip('openpyxl')
    rng = random.Random(9)
    curva = _curva(rng, 40, kw=1500.0, por_dia=_con_valle(rng, 40, 12, 14))
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = 'MED1'
    hoja.append(['Local Time', 'kW', 'kVAR', 'kVA'])
    for t, kw, q in curva:
        hoja.append([t, kw, q, math.hypot(kw, q)])
    ruta = tmp_path / 'cabecera.xlsx'
    libro.save(ruta)
    curvas, avisos = vl.curvas_medidas([ruta], [('F1', 'MED1')])
    assert avisos == [] and len(curvas['MED1']) == len(curva)
    v = vl.valle_de_alcance('alimentador', curvas, vl.Ajustes())
    assert abs((v.ventana['inicio'] - _dia(12)).days) <= 2
    vacio, avisos = vl.curvas_medidas([ruta], [('F1', 'NO_ESTA')])
    assert vacio == {} and any('NO_ESTA' in a for a in avisos)


REAL = os.environ.get('CSG_DEMANDA_DIR', '').strip()


def _una_fila_real(nombre, kind, v, curvas):
    """Una línea para el informe de la prueba (con ``-s``), en cifras; no se guarda nada."""
    total = sum(len(c) for c in curvas)
    apartado = sum(x['registros'] for x in v.apartados.values())
    if not v.ventanas:
        return f'{kind};{nombre};sin ventana;;;;{v.anios};{100 * apartado / max(total, 1):.1f}'
    w = v.ventana
    return (f"{kind};{nombre};{w['inicio']};{w['fin']};{w['duracion_dias']};"
            f"{w['kwh_dia_dentro'] / w['kwh_dia_fuera']:.2f};{v.anios};{100 * apartado / max(total, 1):.1f};{v.coinciden}")


@pytest.mark.skipif(not REAL or not Path(REAL).is_dir(), reason='CSG_DEMANDA_DIR no apunta a la carpeta de la distribuidora')
def test_ventana_real_con_la_medicion_de_la_distribuidora():
    """073:RF-2, 073:RF-6, 073:RF-11, 073:RF-35 — con medición real, por objetivo, inicio, fin y duración
    salen de los registros, el punto no es un cero y lo apartado se nombra. ``CSG_VALLE_OBJETIVOS`` dice
    cuántos alimentadores lee, para la medición completa; nada de esos datos se guarda."""
    from convertersmartgrid import demanda_medida as dm

    def sub(prefijo):
        return next(p for p in Path(REAL).iterdir() if p.is_dir() and p.name.startswith(prefijo))

    libro = next(sub('1.').iterdir())
    meds = dm.leer_medidores(libro)
    pares = [(a, dm.medidores_de(meds, a)[0]) for a in dict.fromkeys(m.alimentador for m in meds)
             if dm.medidores_de(meds, a)]
    pares = pares[:int(os.environ.get('CSG_VALLE_OBJETIVOS', 3))]
    cabecera = dm.Cabecera([sub('2.')])
    curvas, _avisos = vl.curvas_medidas([sub('2.')], pares, cabecera=cabecera)
    assert curvas
    vistos, aj = 0, vl.Ajustes()
    print('\nobjetivo;nombre;inicio;fin;dias;dentro/fuera;anios;%apartado;coinciden')
    for alim, medidor in pares:
        if medidor not in curvas:
            continue
        v = vl.valle_de_alcance('alimentador', {medidor: curvas[medidor]}, aj)
        print(_una_fila_real(alim, 'alimentador', v, [curvas[medidor]]))
        if v.comprobado:
            vistos += 1
            assert v.instante['kw'] > 0
    assert vistos
    # El sistema: todos los leídos sumados; un medidor con pocos registros sale y se dice.
    v = vl.valle_de_alcance('sistema', curvas, aj)
    print(_una_fila_real(f'{len(curvas)} alimentadores', 'conjunto', v, curvas.values()))
    assert v.comprobado


def test_ventana_universal_sin_cifras_de_una_empresa():
    """073:RF-34, 073:RF-41 — el módulo no lleva nombres de empresa, tamaños de banco ni duración, ni
    llama demanda al valle en lo que muestra; el perfil solo afina la penalización."""
    texto = Path(vl.__file__).read_text(encoding='utf-8').lower()
    for prohibido in ('electro', 'dunas', 'epsg', '450', '300 kvar', 'dias_ventana', 'factor_cargas_nuevas'):
        assert prohibido not in texto, prohibido
    assert not hasattr(vl.ajustes_de({'valle': {'dias_ventana': 9}}), 'dias_ventana')
    assert vl.ajustes_de({'valle': {'penalizacion': 3.0}}).penalizacion == 3.0
    with pytest.raises(vl.ValleError):
        vl.ajustes_de({'valle': {'penalizacion': -1}})
    rng = random.Random(13)
    curva = _curva(rng, 120, por_dia=_con_valle(rng, 120, 40, 30))
    v = vl.valle_de_alcance('alimentador', {'M': curva}, vl.Ajustes())
    assert not any('demanda' in a.lower() for a in v.avisos)
    assert 'demanda' not in vl.frase_valle({}) and 'demanda' not in vl.frase_valle(
        {'valle': True, 'valle_u_max': 1.0, 'valle_nodo': 'B', 'valle_fecha': 'x'})


# =========================================================================== escalera y oráculo
from test_optimizacion_oraculo import (
    NUEVA,
    TIPOS,
    _exacto,
    _grafo,
    _id,
    _p,
)

from convertersmartgrid import escalera_optima as eo
from convertersmartgrid import optimizacion_oraculo as oo


def _banco(n: int, kvar: float = 450.0, barra: str = 'B') -> dict:
    return {'clase': 'condensador', 'barra': barra, 'q_kvar': kvar * n, 'escalones': n}


def _puntos(factor_p: float, factor_q: float | None = None) -> dict:
    """Un punto de valle como los da ``puntos_de_valle``."""
    return {'comprobado': True, 'motivo': '', 'avisos': [], 'pronostico': None,
            'puntos': [{'etiqueta': 'mínimo del valle', 'fecha': '2026-03-08 03:15:00', 'kw': 100.0, 'kvar': 30.0,
                        'factor_p': factor_p, 'factor_q': factor_p if factor_q is None else factor_q,
                        'factores': {'F1': factor_p}, 'origen': 'medicion'}]}


def _red_con_margen():
    """Red donde la máxima aguanta dos bancos y el valle no: X alta y carga pequeña."""
    nueva = {**NUEVA, 'p_mw': 0.1, 'q_mvar': 0.02}
    return oo.Oraculo(_grafo(r=2.0, x=3.0, nueva_mw=0.1), [nueva], tipos=TIPOS)


def _fila(nombre, e, costo=100.0, escalones=('bancos',)):
    return {'nombre': nombre, 'escalones': escalones, 'costo': {'costo_anual': costo}, **e}


def test_sobretension_en_valle_se_cuela_por_la_fraccion():
    """073:RF-17, 073:RF-18 — el caso «la máxima cumple con bancos y el valle no». Sin el valle, la
    fracción de sorteos deja pasar el único instante de demanda baja y la variante se elige; con él, no."""
    ora, p = _red_con_margen(), _p(tension_max_pu=1.04)
    obras = [_banco(2)]
    factores = [1.0] * 19 + [0.05]                       # un instante de valle entre veinte sorteos
    sin_valle = ora.evaluar(obras, 1, p, factores)
    assert sin_valle['maxima'] and sin_valle['fraccion'] >= p.cumplimiento        # se cuela
    assert eo.elegir([_fila('2 bancos', sin_valle)], p)['elegida'] == '2 bancos'
    con_valle = ora.evaluar(obras, 1, p, factores, valle=_puntos(0.05))
    assert con_valle['maxima'] and con_valle['fraccion'] >= p.cumplimiento        # la máxima sigue cumpliendo
    assert con_valle['valle'] is False and con_valle['valle_u_max'] > p.tension_max_pu
    assert con_valle['valle_nodo'] == 'B' and con_valle['valle_fecha'] == '2026-03-08 03:15:00'
    r = eo.elegir([_fila('2 bancos', con_valle)], p)
    assert r['elegida'] is None and 'sin_confirmar_sorteos' not in r
    assert 'en valle' in r['tabla'][0]['motivo'] and '073:RF-17' in r['tabla'][0]['motivo']


def test_escalera_elegir_no_compensa_con_la_regla_de_la_maxima():
    """073:RF-18 — 063:RF-33 elige lo que cumple con la máxima aunque los sorteos no lo confirmen;
    lo que no cumple en valle no entra ahí, y la escalera sube al escalón siguiente."""
    p = _p()
    malo = {'maxima': True, 'fraccion': 0.5, 'valle': False, 'valle_motivos': ['B sube']}
    assert eo.elegir([_fila('banco', malo)], p)['elegida'] is None
    terna = {'maxima': True, 'fraccion': 1.0, 'valle': True}
    r = eo.elegir([_fila('banco', {**malo, 'fraccion': 1.0}), _fila('terna', terna, 900.0, ('terna',))], p)
    assert r['elegida'] == 'terna'
    assert r['aviso_valle'] and 'banco' in r['aviso_valle'] and 'por pasos' in r['aviso_valle']   # 073:RF-20, 073:RF-27


def test_escalera_sin_valle_no_bloquea_y_queda_marcada():
    """073:RF-24, 073:RF-31 — sin medición nada se bloquea, pero la variante dice «no comprobado en
    valle», también la elegida."""
    p = _p()
    r = eo.elegir([_fila('banco', {'maxima': True, 'fraccion': 1.0})], p)
    assert r['elegida'] == 'banco' and r['sin_comprobar_valle'] is True
    assert 'no comprobado en valle' in r['tabla'][0]['motivo']
    # 073:RF-40: bancos y proyectos: una terna tampoco queda dada por buena en valle.
    terna = eo.elegir([_fila('terna', {'maxima': True, 'fraccion': 1.0}, escalones=('terna',))], p)
    assert terna['sin_comprobar_valle'] is True and 'no comprobado en valle' in terna['tabla'][0]['motivo']
    sin_obra = eo.elegir([_fila('nada', {'maxima': True, 'fraccion': 1.0}, escalones=())], p)
    assert 'sin_comprobar_valle' not in sin_obra


def test_escalera_toda_obra_se_comprueba_en_valle():
    """073:RF-40 — una sección o una terna que no cumple en valle tampoco se elige, y el oráculo mide
    también las que no son bancos."""
    p = _p()
    r = eo.elegir([_fila('seccion', {'maxima': True, 'fraccion': 1.0, 'valle': False, 'valle_motivos': ['B sube']},
                         escalones=('seccion',)),
                   _fila('terna', {'maxima': True, 'fraccion': 1.0, 'valle': True}, 900.0, ('terna',))], p)
    assert r['elegida'] == 'terna' and 'en valle' in r['tabla'][0]['motivo']
    ora = oo.Oraculo(_grafo(), [{**NUEVA, 'alimentador': 'F1'}], tipos=TIPOS)
    e = ora.evaluar([{'clase': 'terna', 'tramos': ['T1', 'T2']}], 1, p, alimentador='F1', valle=_puntos(0.2))
    assert e['valle'] is True and e['valle_u_max'] is not None
    set_nueva = ora.con_set_nueva([{'entrada': 'T2', 'nodo': 'B', 'distancia_km': 0.5, 'r_ohm_km': 0.5, 'x_ohm_km': 0.4,
                                    'inom_ka': 0.3}], 10.0)
    assert set_nueva.evaluar([], 1, p, valle=_puntos(0.2))['valle_casos']


@pytest.mark.parametrize('semilla', range(5))
def test_escalera_modulos_como_el_flujo_exacto(semilla):
    """073:RF-19, 073:RF-34 — el número de módulos es el mayor que no pasa del límite superior en el
    flujo exacto, con tamaño de banco, red y límite sorteados: ninguna cifra en el código."""
    rng = random.Random(semilla)
    kvar = rng.choice([150.0, 300.0, 450.0, 600.0])
    x = rng.uniform(1.0, 4.0)
    hi = rng.uniform(1.01, 1.06)
    ora = oo.Oraculo(_grafo(r=1.0, x=x, nueva_mw=0.0), [], tipos=TIPOS)
    p = _p(tension_max_pu=hi, tolerancia_pu=0.0)
    r = oo.modulos_en_valle(ora, ['B'], kvar, _puntos(1.0), p)
    g, b = _grafo(r=1.0, x=x, nueva_mw=0.0), _id('B', 'ElmTerm')
    esperado = 0
    while _exacto(g, b, extra_q_mvar=kvar * (esperado + 1) / 1000) <= hi:
        esperado += 1
    assert r['modulos'] == esperado and r['comprobado'] and not r['por_tope']
    assert r['u_max'] is None or r['u_max'] <= hi + 1e-9


def test_escalera_modulos_con_tope_del_perfil_y_sin_efecto_no_cuelgan():
    """073:RF-19 — con ``escalera.modulos_max`` el tope es el suyo; sin efecto del banco, para y lo dice."""
    ora = oo.Oraculo(_grafo(nueva_mw=0.0), [], tipos=TIPOS)
    p = _p(tension_max_pu=5.0)
    r = oo.modulos_en_valle(ora, ['B'], 150.0, _puntos(1.0), p, tope=3)
    assert r['modulos'] == 3 and r['por_tope']
    sin_efecto = oo.modulos_en_valle(ora, ['NO_ESTA'], 150.0, _puntos(1.0), p)
    assert sin_efecto['modulos'] == 0 and sin_efecto['aviso']
    nada = oo.modulos_en_valle(ora, ['B'], 150.0, {'comprobado': False, 'puntos': [], 'motivo': 'sin medición'}, p)
    assert nada['modulos'] is None and not nada['comprobado'] and nada['motivo'] == 'sin medición'


def _troncal():
    return [{'nombre': f'T{i}', 'largo_m': 1000.0, 'corriente_a': 50.0} for i in range(3)]


CARGA = [{'barra': 'B', 'existe': True, 'indice_troncal': 2}]


@pytest.mark.parametrize('n', [0, 1, 3, 5])
def test_escalera_variantes_de_1_al_tope_mas_una_de_evidencia(n):
    """073:RF-19, 073:RF-20 — se prueban de 1 a N módulos, y N + 1 solo, sin combinar, para ver que el
    valle lo rechaza; el módulo es el de la tensión; N es el del valle, no una cifra."""
    p = _p(con_regulador=False)
    vs, avisos = eo.variantes('F1', 22.9, _troncal(), CARGA, [], p, banco_kvar=450, modulos_valle=n)
    bancos = [v for v in vs if v.escalones == ('bancos',)]
    assert [o['escalones'] for v in bancos for o in v.obras] == list(range(1, n + 2))
    assert all(o['q_kvar'] == 450 * o['escalones'] for v in bancos for o in v.obras)
    assert [v.solo_evidencia for v in bancos] == [False] * n + [True]
    combinadas = [v for v in vs if 'bancos' in v.escalones and len(v.escalones) > 1]
    assert all(o['escalones'] <= n for v in combinadas for o in v.obras if o['clase'] == 'condensador')
    assert bool(combinadas) == bool(n)
    assert any(f'{n} módulos' in a or 'ningún módulo' in a for a in avisos)
    # Sin consigna: el banco por pasos existe como obra, pero la escalera no lo genera (073:RF-27).
    assert not any(o.get('consigna_pu') for v in vs for o in v.obras if o['clase'] == 'condensador')


def test_escalera_con_tope_del_perfil_no_prueba_de_mas():
    """073:RF-19 — si el número lo limita ``escalera.modulos_max``, no se prueba uno más."""
    vs, _ = eo.variantes('F1', 22.9, _troncal(), CARGA, [], _p(con_regulador=False), banco_kvar=450, modulos_valle=2,
                         evidencia=False)
    assert [o['escalones'] for v in vs if v.escalones == ('bancos',) for o in v.obras] == [1, 2]


def test_escalera_sin_valle_los_modulos_del_perfil_o_la_regla_anterior():
    """073:RF-24 — sin valle, ``escalera.modulos_max`` o los de antes, sin bloquear."""
    def modulos(p):
        vs, _ = eo.variantes('F1', 10.0, _troncal(), CARGA, [], p, banco_kvar=300)
        return [o['escalones'] for v in vs if v.escalones == ('bancos',) for o in v.obras]
    assert modulos(_p(con_regulador=False)) == list(range(1, eo.MODULOS_SIN_VALLE + 1))
    assert modulos(_p(con_regulador=False, modulos_max=4)) == [1, 2, 3, 4]
    perfil = {'escalera': {'cumplimiento': 0.9, 'sorteos': 3, 'tolerancia_pu': 0.01, 'tolerancia_carga_pct': 1,
                           'modulos_max': 6},
              'planificacion': {'tasa_regulada': 0.1, 'vida_util_anios': 20},
              'estudios': {'tension_min_pu': 0.9, 'tension_max_pu': 1.1, 'cargabilidad_max_pct': 100}}
    assert eo.parametros(perfil).modulos_max == 6
    del perfil['escalera']['modulos_max']
    assert eo.parametros(perfil).modulos_max is None


def test_escalera_el_kvar_de_valle_con_su_propio_factor():
    """073:RF-22 — el kW y el kVAR del registro, cada uno con su factor: un valle capacitivo no es la
    máxima a escala. El resultado es el del flujo del grafo con esas potencias."""
    g = _grafo(nueva_mw=0.0)
    ora = oo.Oraculo(g, [], tipos=TIPOS)
    b = _id('B', 'ElmTerm')
    m = ora.medir([], 0, 0.3, factor_q=-0.2)
    hecho = {'nodos': {n: {**d, 'p_mw': d['p_mw'] * 0.3, 'q_mvar': d['q_mvar'] * -0.2} for n, d in g['nodos'].items()},
             'ramas': g['ramas']}
    assert m.u['B'] == pytest.approx(_exacto(hecho, b), abs=1e-9)
    assert ora.medir([], 0, 0.3).u['B'] == pytest.approx(ora.medir([], 0, 0.3, factor_q=0.3).u['B'], abs=1e-12)


def test_escalera_las_cargas_nuevas_en_valle_en_los_dos_casos():
    """073:RF-23, 073:RF-39 — sin las cargas nuevas, el peor caso, y con ellas; cumple solo si cumple en
    los dos, y lo medido dice ambos. Ninguna opción del perfil lo decide."""
    ora = _red_con_margen()
    apagada = ora.medir([], 1, 0.05, factor_nuevas=0.0).u['B']
    assert apagada == pytest.approx(ora.medir([], 0, 0.05).u['B'], abs=1e-12)
    assert ora.medir([], 1, 0.05, factor_nuevas=1.0).u['B'] < apagada
    assert not hasattr(vl.Ajustes(), 'factor_cargas_nuevas')
    # Con 2 bancos: a 1,04 no pasa sin la carga, pero sí con ella.
    e = ora.evaluar([_banco(2)], 1, _p(tension_max_pu=1.04), valle=_puntos(0.05))
    casos = e['valle_casos']
    assert e['valle'] is False and casos['sin_cargas']['cumple'] is False
    assert casos['con_cargas']['u_max'] < casos['sin_cargas']['u_max'] == e['valle_u_max']
    assert 'sin cargas nuevas' in vl.frase_valle(e) and 'con cargas nuevas' in vl.frase_valle(e)
    # Sin cargas activas, un solo caso.
    assert set(ora.evaluar([_banco(1)], 0, _p(), valle=_puntos(0.05))['valle_casos']) == {'sin_cargas'}


def _espacio_valle():
    return oo.Espacio('F1', barras=['B'], banco_kvar=450.0, modulos_max=6,
                      tramos=[{'nombre': 'T1', 'largo_m': 2000.0}, {'nombre': 'T2', 'largo_m': 2000.0}], secciones=[])


def test_escalera_busqueda_de_k_y_eleccion_con_el_valle():
    """073:RF-17, 073:RF-21 — buscar_k y elegir_para_k juzgan también en valle: lo que solo cabe con
    bancos que el valle rechaza no se da por bueno, y la tabla dice la tensión de cada una."""
    pytest.importorskip('optuna')
    # Con la máxima hacen falta dos bancos o una terna; el valle solo admite uno.
    p = _p(tension_max_pu=1.01)
    valle = _puntos(0.2)
    nueva = [{**NUEVA, 'alimentador': 'F1'}]
    ora = oo.Oraculo(_grafo(), nueva, tipos=TIPOS)
    assert oo.modulos_en_valle(ora, ['B'], 450.0, valle, p)['modulos'] == 1
    bancos = [eo.Variante(f'{n} bancos', ('bancos',), [{**_banco(n), 'alimentador': 'F1'}], {'bancos': float(n)})
              for n in (1, 2)]
    terna = eo.Variante('terna', ('terna',), [{'clase': 'terna', 'alimentador': 'F1', 'tramos': ['T1', 'T2']}],
                        {'terna': 4.0})
    alim = oo.Alimentador('F1', [*bancos, terna], lambda v, _k: sum({'bancos': 10.0, 'terna': 500.0}[e] for e in v.escalones),
                          _espacio_valle())
    assert ora.evaluar(bancos[1].obras, 1, p, alimentador='F1')['maxima']        # sin valle, valdría
    assert oo.buscar_k(ora, [oo.Alimentador('F1', bancos, alim.costo)], p)[0] == 1
    assert oo.buscar_k(ora, [oo.Alimentador('F1', bancos, alim.costo)], p, valle=valle)[0] == 0
    r = oo.elegir_para_k(ora, [alim], 1, p, valle=valle, evaluaciones_bayes=30, permutaciones=4, semilla=1)['F1']
    assert r['elegida'] == 'terna'
    filas = {t['nombre']: t for t in r['tabla']}
    assert filas['2 bancos']['valle'] is False and filas['2 bancos']['maxima']
    assert filas['1 bancos']['valle'] is True and filas['1 bancos']['valle_u_max'] <= p.tension_max_pu

    # Ni la bayesiana ni el frente de Pareto dan una combinación con más bancos de los que aguanta.
    def _bancos_de(nombre):
        return next((int(t.split('×')[0]) for t in nombre.split(' + ') if '×' in t), 0)
    assert r['bayesiana']['variante'] is None or _bancos_de(r['bayesiana']['variante']) <= 1
    assert all(_bancos_de(f['variante']) <= 1 for f in r['pareto']['frente'])
    assert r['shapley'] is not None


def test_escalera_punto_con_el_factor_de_cada_uno():
    """073:RF-22, 073:RF-1 — de la medición al punto: factor de P y de Q sobre la máxima, por alimentador
    y del conjunto; un solo punto, el mínimo del valle."""
    rng = random.Random(77)
    por_dia = _con_valle(rng, 60, 20, 15)
    a, b = _curva(rng, 60, kw=1000.0, por_dia=por_dia), _curva(rng, 60, kw=3000.0, por_dia=por_dia)
    maximas = {'MA': {'alimentador': 'F1', 'kw': 1200.0, 'kvar': 300.0},
               'MB': {'alimentador': 'F2', 'kw': 3500.0, 'kvar': 800.0}}
    v = vl.valle_de_alcance('alimentador', {'MA': a, 'MB': b}, vl.Ajustes())
    r = vl.puntos_de_valle(v, maximas)
    assert r['comprobado'] and len(r['puntos']) == 1 and r['puntos'][0]['etiqueta'].startswith('mínimo del valle')
    assert r['ventanas'][0]['duracion_dias'] == v.ventana['duracion_dias']
    pt = r['puntos'][0]
    assert pt['factor_p'] == pytest.approx(v.instante['kw'] / 4700.0)
    assert pt['factor_q'] == pytest.approx(v.instante['kvar'] / 1100.0)
    por = v.instante['por_medidor']
    assert pt['factores'] == {'F1': pytest.approx(por['MA'][0] / 1200.0), 'F2': pytest.approx(por['MB'][0] / 3500.0)}
    assert pt['origen'] == 'medicion' and isinstance(pt['fecha'], str)
    import json
    json.dumps(r)                                        # viaja en el plan del guion


def test_informe_frase_con_nodo_y_fecha_o_no_comprobado():
    """073:RF-30, 073:RF-31 — la tensión máxima en valle con su nodo y su fecha; sin medición, «no
    comprobado en valle» con el motivo, y nunca la palabra «cumple»."""
    bien = vl.frase_valle({'valle': True, 'valle_u_max': 1.0432, 'valle_nodo': 'B7', 'valle_fecha': '2026-03-08 03:15:00'})
    assert bien == 'tensión máxima en valle de 1,043 p.u. en B7 el 2026-03-08 03:15:00'
    mal = vl.frase_valle({'valle': False, 'valle_u_max': 1.07, 'valle_nodo': 'B7', 'valle_fecha': 'x'})
    assert '1,070' in mal and 'no admisible' in mal
    ambos = vl.frase_valle({'valle': True, 'valle_u_max': 1.04, 'valle_nodo': 'B7', 'valle_fecha': 'x', 'valle_casos': {
        'sin_cargas': {'cumple': True, 'u_max': 1.04, 'nodo': 'B7', 'fecha': 'x'},
        'con_cargas': {'cumple': True, 'u_max': 1.01, 'nodo': 'B2', 'fecha': 'x'}}})
    assert 'sin cargas nuevas 1,040 p.u. en B7; con cargas nuevas 1,010 p.u. en B2' in ambos    # 073:RF-39
    for fila in (None, {}, {'valle': None}, {'valle': None, 'valle_sin_comprobar': 'sin medición'}):
        frase = vl.frase_valle(fila)
        assert frase.startswith('no comprobado en valle') and 'cumple' not in frase
    assert 'sin medición' in vl.frase_valle({'valle_sin_comprobar': 'sin medición'})


def test_escalera_puntos_con_un_medidor_fuera_de_la_suma():
    """073:RF-8, 073:RF-22 — el alimentador de un medidor fuera de la suma baja con el conjunto, no se
    queda en su máxima, que bajaría la tensión del valle sin medirlo."""
    rng = random.Random(41)
    bueno, malo = _curva(rng, 20, kw=5000.0), rng.sample(_curva(rng, 20, kw=8.0), 400)
    v = vl.valle_de_alcance('sistema', {'BUENO': bueno, 'MALO': malo}, vl.Ajustes())
    maximas = {'BUENO': {'alimentador': 'F1', 'kw': 6000.0, 'kvar': 1000.0}, 'MALO': {'alimentador': 'F2', 'kw': 10.0, 'kvar': 1.0}}
    (pt,) = vl.puntos_de_valle(v, maximas)['puntos']
    assert pt['factores']['F2'] == pt['factor_p'] == pytest.approx(v.instante['kw'] / 6000.0)


def test_escalera_puntos_sin_medicion_o_sin_la_maxima():
    """073:RF-24 — sin valle medido o sin la máxima para comparar, sin puntos y con el motivo."""
    aj = vl.Ajustes()
    nada = vl.puntos_de_valle(vl.Valle(alcance='set', motivo='sin medición'), {})
    assert not nada['comprobado'] and nada['puntos'] == [] and nada['motivo'] == 'sin medición'
    v = vl.valle_de_alcance('set', {'M': _curva(random.Random(3), 5)}, aj)
    sin_max = vl.puntos_de_valle(v, {'M': {'alimentador': 'F', 'kw': None, 'kvar': None}})
    assert not sin_max['comprobado'] and sin_max['puntos'] == [] and 'máxima' in sin_max['motivo']


def test_pronostico_no_sustituye_a_la_medicion():
    """073:RF-33 — un pronóstico de valle viaja como dato; sin medición sigue sin comprobarse, y con
    medición los puntos son los medidos."""
    aj = vl.Ajustes()
    pron = {'anio': 2030, 'kva': 123.0, 'fecha': '2030-02-01 03:00:00'}
    sin = vl.puntos_de_valle(vl.Valle(alcance='set', motivo='sin medición'), {}, pronostico=pron)
    assert not sin['comprobado'] and sin['puntos'] == [] and sin['pronostico'] == pron
    assert vl.frase_valle(oo.Oraculo(_grafo(), []).en_valle([], 0, _p(), sin)).startswith('no comprobado en valle')
    v = vl.valle_de_alcance('set', {'M': _curva(random.Random(3), 5)}, aj)
    con = vl.puntos_de_valle(v, {'M': {'alimentador': 'F', 'kw': 2000.0, 'kvar': 500.0}}, pronostico=pron)
    assert con['comprobado'] and all(x['origen'] == 'medicion' for x in con['puntos']) and con['pronostico'] == pron


# =========================================================================== calibración a valle
def _red_calibrada_con_casos():
    from test_casos_por_anio import _red_calibrada

    return _red_calibrada(escenario=True)


@pytest.fixture
def casos_pf():
    from test_casos_pf import casos_pf as modulo

    return modulo


def test_calibracion_caso_y_escenario_propios_sin_tocar_la_maxima(casos_pf):
    """073:RF-13, 073:RF-14 — «Valle <año>» es copia de «Sin proyecto <año>», con su marca y su
    escenario; el caso, el escenario y las cargas de la máxima no cambian; repetir no crea otro."""
    app, _base = _red_calibrada_con_casos()
    anio = random.Random().randint(2020, 2040)
    informe, rc = casos_pf.preparar_sin(app, {'project': 'P', 'feeders': ['F1'], 'caso_base_sin_verificar': {},
                                              'anio_casos': anio})
    assert rc == 0, informe
    sin = casos_pf.caso(app, 'sin', anio)
    activo = app.GetActiveStudyCase()
    sin.Activate()
    esc_sin = app.GetActiveScenario()
    activo.Activate()
    antes = {c.loc_name for c in app.carpetas['study'].GetContents('*.IntCase')}
    r = casos_pf.caso_valle(app, sin, anio)
    assert r['caso'] == f'Valle {anio}' == vl.nombre_caso_valle(anio) and r['creado'] and r['escenario'] == f'Valle {anio}'
    assert app.GetActiveStudyCase() is activo
    caso = next(c for c in app.carpetas['study'].GetContents('*.IntCase') if c.loc_name == f'Valle {anio}')
    assert casos_pf.rol_de(caso) == f'valle@{anio}'
    assert {c.loc_name for c in app.carpetas['study'].GetContents('*.IntCase')} == antes | {f'Valle {anio}'}
    # La máxima sigue con su escenario, y «Valle» no le quita el rol a nadie.
    sin.Activate()
    assert app.GetActiveScenario() is esc_sin and esc_sin.loc_name != f'Valle {anio}'
    caso.Activate()
    assert app.GetActiveScenario().loc_name == f'Valle {anio}' and app.GetActiveScenario() is not esc_sin
    activo.Activate()
    assert casos_pf.casos_del_proyecto(app, anio)['sin'] is sin
    assert 'valle' not in casos_pf.casos_del_proyecto(app, anio)
    otra = casos_pf.caso_valle(app, sin, anio)
    assert not otra['creado'] and otra['caso'] == f'Valle {anio}'


def test_calibracion_caso_ajeno_no_se_toca(casos_pf):
    """073:RF-15 — un caso con ese nombre que el sistema no creó no se toca, y se dice."""
    app, _base = _red_calibrada_con_casos()
    sin = casos_pf.caso(app, 'sin')
    ajeno = app.carpetas['study'].CreateObject('IntCase', vl.nombre_caso_valle(None))
    r = casos_pf.caso_valle(app, sin, None)
    assert r['caso'] is None and any('no creó el sistema' in a for a in r['avisos'])
    assert casos_pf.rol_de(ajeno) is None


def test_calibracion_plan_con_la_maquina_de_siempre(tmp_path):
    """073:RF-16, 073:RF-14 — el plan toma de los libros el registro del instante de valle por
    ``demanda_medida`` y da el objetivo de ``ajuste_cabecera``; pide las fijas coincidentes con esa
    hora, no el máximo del mes, y no se puede confundir con la calibración de la máxima."""
    openpyxl = pytest.importorskip('openpyxl')
    curva = _curva(random.Random(19), 7, kw=1800.0)
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = 'MED1'
    hoja.append(['Local Time', 'kW', 'kVAR', 'kVA'])
    for t, kw, q in curva:
        hoja.append([t, kw, q, math.hypot(kw, q)])
    ruta = tmp_path / 'cabecera.xlsx'
    libro.save(ruta)
    curvas, _av = vl.curvas_medidas([ruta], [('F1', 'MED1')])
    v = vl.valle_de_alcance('alimentador', curvas, vl.Ajustes())
    filas = vl.filas_de_calibracion([ruta], [('F1', 'MED1')], v.instante['fecha'])
    plan = vl.plan_calibracion_valle(v, filas, 2026)
    assert plan['caso'] == plan['escenario'] == 'Valle 2026' and plan['copia_de'] == 'Sin proyecto 2026'
    assert plan['instante'] == v.instante['fecha'].isoformat(sep=' ')
    assert plan['criterio_fijas'] == 'coincidente' and plan['ejecutable'] is False and plan['pendiente']
    (obj,) = plan['objetivos']
    assert obj['kw'] == pytest.approx(v.instante['kw']) and obj['kvar'] == pytest.approx(v.instante['kvar'])
    assert obj['alimentador'] == 'F1' and obj['fecha'] == plan['instante']
    assert vl.plan_calibracion_valle(vl.Valle(alcance='set', motivo='sin medición'), [], None)['motivo'] == 'sin medición'
    assert vl.nombre_caso_valle(None) == 'Valle'


# =========================================================================== guion de la evaluación
def _guion():
    from test_obras_pf_guion import guion as modulo

    return modulo


def _evaluar_en_valle(monkeypatch, puntos, *, u_valle=1.09, barra='B1', actual_cumple=False, barras_cargas=()):
    """``evaluar`` con el flujo sustituido: en el escenario de valle, la barra sube a ``u_valle`` si
    la variante lleva banco. Lo que se pone en juego es el guion, no el doble."""
    from test_obras_pf_guion import PERFIL_ESCALERA, _calibrada_con_escenario, _plan

    from convertersmartgrid import escalera_optima

    g = _guion()
    app, alims = _calibrada_con_escenario(random.Random(13))
    estado = {'obra': None, 'valle': False, 'escalados': []}

    def aplicar(_app, sub):
        estado['obra'] = sub['obras'][0]['clase']
        return {'obras': [{'variacion': None}]}, 0

    def medir(_app, _alims, _feeders):
        u = u_valle if estado['valle'] and estado['obra'] == 'condensador' else 1.0
        return {'converge': True, 'u': {barra: u}, 'carga': {}, 'perdidas_kw': 10.0}

    class Sorteo:
        def __init__(self, *_a):
            pass

        def __enter__(self):
            return self

        def escalar(self, factores, factor_nuevas=None):
            estado['escalados'].append((dict(factores), factor_nuevas))
            estado['valle'] = factor_nuevas is not None

        def __exit__(self, *_e):
            estado['valle'] = False
            return False

    monkeypatch.setattr(g, 'aplicar', aplicar)
    monkeypatch.setattr(g, 'medida_para_criterio', medir)
    monkeypatch.setattr(g, '_Sorteo', Sorteo)
    if not actual_cumple:
        original = escalera_optima.cumple
        def cumple(sin, con, barras, p):
            # «Con proyecto» sin obra no cumple, como con las cargas nuevas (025:RF-74).
            if estado['obra'] is None and not estado['valle']:
                return False, ['sin obra']
            return original(sin, con, barras, p)
        monkeypatch.setattr(escalera_optima, 'cumple', cumple)
    f = alims[0]
    variantes = [{'nombre': 'bancos', 'obras': [{'clase': 'condensador', 'alimentador': f, 'casos': ['Con proyecto'],
                                                 'barra': barra, 'q_kvar': 300.0, 'escalones': 1}], 'costo_base': 1.0},
                 {'nombre': 'terna', 'obras': [{'clase': 'terna', 'alimentador': f, 'casos': ['Con proyecto'],
                                                'tramos': ['L1']}], 'costo_base': 50.0}]
    perfil = {**PERFIL_ESCALERA, 'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}}
    plan = _plan(alims, variantes=variantes, sorteos=[{'factores': {a: 0.9 for a in alims}}], barras_cargas=list(barras_cargas),
                 parametros=perfil, costo_por_kw_perdido=1.0, valle=puntos)
    informe, codigo = g.evaluar(app, plan)
    assert codigo == 0, informe
    return informe, estado


def test_guion_en_valle_rechaza_el_banco_y_no_lo_sortea(monkeypatch):
    """073:RF-25, 073:RF-30 — cada variante se mide en el punto de valle, con su tensión, nodo y fecha; la
    del banco no se sortea por muy barata que sea, y gana la siguiente."""
    informe, estado = _evaluar_en_valle(monkeypatch, _puntos(0.2))
    filas = {v['nombre']: v for v in informe['variantes']}
    assert filas['bancos']['maxima'] and filas['bancos']['valle'] is False
    assert filas['bancos']['valle_u_max'] == 1.09 and filas['bancos']['valle_nodo'] == 'B1'
    assert filas['bancos']['valle_fecha'] == '2026-03-08 03:15:00'
    assert filas['bancos']['fraccion'] is None and 'en valle' in filas['bancos']['sin_sortear']
    assert filas['terna']['valle'] is True and filas['terna']['fraccion'] == 1.0
    assert ({'F1': 0.2}, 0.0) in estado['escalados']
    assert set(filas['bancos']['valle_casos']) == {'sin_cargas'}


def test_guion_en_valle_mide_sin_y_con_las_cargas_nuevas(monkeypatch):
    """073:RF-39 — con cargas nuevas en juego, cada variante se mide con ellas apagadas y a su potencia."""
    informe, estado = _evaluar_en_valle(monkeypatch, _puntos(0.2), barras_cargas=['B1'], u_valle=1.0)
    assert ({'F1': 0.2}, 0.0) in estado['escalados'] and ({'F1': 0.2}, 1.0) in estado['escalados']
    assert set(informe['variantes'][0]['valle_casos']) == {'sin_cargas', 'con_cargas'}


def test_guion_sin_puntos_de_valle_no_mide_ni_inventa(monkeypatch):
    """073:RF-24, 073:RF-25 — sin puntos el guion no escala nada para el valle ni dice que cumple."""
    informe, estado = _evaluar_en_valle(monkeypatch, {'comprobado': False, 'puntos': [], 'motivo': 'sin medición'})
    assert all(f is None for _x, f in estado['escalados'])
    assert all('valle' not in v for v in informe['variantes'])
    assert informe['variantes'][0]['fraccion'] == 1.0


def test_guion_ya_cumple_y_en_valle_no_se_dice(monkeypatch):
    """073:RF-26 — lo que ya tiene «Con proyecto» cumple con la máxima; su resultado en valle va en el informe."""
    informe, _ = _evaluar_en_valle(monkeypatch, _puntos(0.2), actual_cumple=True, u_valle=1.0)
    assert informe['ya_cumple']['valle'] is True and informe['ya_cumple']['valle_fecha'] == '2026-03-08 03:15:00'


def test_guion_el_escenario_temporal_escala_y_no_deja_nada():
    """073:RF-25 — en el doble: las existentes por su factor, las nuevas por el suyo, y al salir vuelven
    el escenario del caso y los factores de escala, sin otro escenario en el proyecto."""
    from test_obras_pf_guion import _calibrada_con_escenario

    g = _guion()
    app, alims = _calibrada_con_escenario(random.Random(7))
    casos = g.casos_del_proyecto(app, None)
    casos['con'].Activate()
    feeder_alims = g.Alimentadores(app, app.proyecto, alims)
    cargas = [c for f in alims for c in g._cargas_de(feeder_alims, f)]
    nueva, existentes = cargas[0], {c.loc_name for c in cargas[1:]}
    escenario = app.GetActiveScenario()
    antes_esc = list(app.GetProjectFolder('scen', 1).GetContents('*.IntScenario'))
    antes = {id(c): float(getattr(c, 'scale0', 1.0) or 0.0) for c in cargas}
    with g._Sorteo(app, feeder_alims, alims, existentes) as s:
        s.escalar({f: 0.25 for f in alims}, 0.0)
        assert app.GetActiveScenario() is not escenario
        assert nueva.scale0 == 0.0
        assert all(c.scale0 == pytest.approx(antes[id(c)] * 0.25) for c in cargas[1:])
    assert app.GetActiveScenario() is escenario
    assert list(app.GetProjectFolder('scen', 1).GetContents('*.IntScenario')) == antes_esc
    assert all(float(getattr(c, 'scale0', 1.0) or 0.0) == antes[id(c)] for c in cargas)


# =========================================================================== PIDE
def _pide(**extra):
    from test_pide_web import COSTOS, INFORME, PLAN

    from convertersmartgrid.pide_economia import propuesta_pide

    return propuesta_pide(INFORME, PLAN, costos=COSTOS, bancos_kvar={10.0: 300.0}, **extra)


def test_pide_sin_modulos_en_valle_toma_la_alternativa_siguiente():
    """073:RF-28 — donde el valle no admite ningún módulo, la caída de tensión pasa a la alternativa
    siguiente de su causa, en vez de proponer el banco."""
    p = _pide(valle={'F1': {'comprobado': True, 'modulos': 0, 'valle': False, 'valle_u_max': 1.07, 'valle_nodo': 'B9',
                            'valle_fecha': '2026-03-08 03:15:00'}})
    alternativas = {o['alternativa'] for o in p['obras']}
    assert 'bancos' not in alternativas and 'nueva_terna' in alternativas
    assert any('073:RF-28' in a for a in p['avisos'])


def test_pide_causa_sin_otra_alternativa_queda_descartada_con_su_motivo():
    """073:RF-28 — el factor de potencia solo se resuelve con bancos: la obra queda descartada, sin obra
    que construir y con su motivo, y no suma a la cartera."""
    from test_pide_web import COSTOS, PLAN
    from test_pide_web import _p as problema

    from convertersmartgrid.pide_economia import propuesta_pide

    informe = {'anios': [{'anio': 0, 'cabeceras_kw': {'F1': 900.0}, 'problemas': [
        problema('factor_de_potencia', 'B3', 0.91, 10.0)]}]}
    p = propuesta_pide(informe, PLAN, costos=COSTOS, bancos_kvar={10.0: 300.0},
                       valle={'F1': {'comprobado': True, 'modulos': 0}})
    (obra,) = p['obras']
    assert obra['alternativa'] == 'bancos' and obra['obra_011'] is None
    assert 'valle' in obra['descartada'] and '073:RF-28' in obra['motivo_sin_obra']


@pytest.mark.parametrize('n', [1, 2, 7])
def test_pide_no_propone_mas_modulos_de_los_que_admite(n):
    """073:RF-29 — el banco va con un módulo como hasta ahora, nunca más de los que admite el valle, y
    dice cuántos admite y su tensión con nodo y fecha."""
    p = _pide(valle={'F1': {'comprobado': True, 'modulos': n, 'valle': True, 'valle_u_max': 1.03, 'valle_nodo': 'B9',
                            'valle_fecha': '2026-03-08 03:15:00'}})
    banco = next(o for o in p['obras'] if o['alternativa'] == 'bancos')
    assert banco['obra_011']['escalones'] <= n and banco['valle']['modulos_admisibles'] == n
    assert '1,030' in banco['valle']['texto'] and 'B9' in banco['valle']['texto']


def test_pide_sin_valle_no_bloquea_y_lo_dice():
    """073:RF-24, 073:RF-31 — sin valle el banco sigue, marcado como no comprobado, y la propuesta
    avisa; las obras que no son bancos no llevan la marca."""
    p = _pide()
    banco = next(o for o in p['obras'] if o['alternativa'] == 'bancos')
    assert banco['valle']['texto'].startswith('no comprobado en valle') and banco['valle']['modulos_admisibles'] is None
    assert any('no comprobado en valle' in a for a in p['avisos'])
    # 073:RF-40: bancos y proyectos: las demás obras tampoco quedan dadas por buenas.
    assert all(o['valle']['texto'].startswith('no comprobado en valle') for o in p['obras'])


def test_pide_otra_obra_que_no_cumple_en_valle_queda_descartada():
    """073:RF-40 — una obra medida que no cumple en valle queda descartada con su motivo; la que cumple
    lo dice con su tensión."""
    p = _pide(valle={'F1': {'comprobado': True, 'modulos': 2, 'valle': True, 'valle_u_max': 1.0, 'valle_nodo': 'B', 'valle_fecha': 'x',
                            'por_alternativa': {'cambio_seccion': {'valle': False, 'valle_u_max': 1.09, 'valle_nodo': 'B',
                                                                   'valle_fecha': 'x'},
                                                'nueva_terna': {'valle': False, 'valle_u_max': 1.09, 'valle_nodo': 'B', 'valle_fecha': 'x'}}}})
    terna = next(o for o in p['obras'] if o['alternativa'] in ('cambio_seccion', 'nueva_terna'))
    assert 'en valle' in terna['descartada'] and terna['obra_011'] is None and '1,090' in terna['valle']['texto']
    assert next(o for o in p['obras'] if o['alternativa'] == 'bancos')['descartada'] is None


# =========================================================================== servicio e informe
def _escalera(tmp_path, monkeypatch, evaluar, **kw):
    import threading

    from test_casos_por_anio import _escalera_falsa

    salida = _escalera_falsa(tmp_path, monkeypatch, evaluar, {'bancos': 9000, 'nueva_terna': 40000, 'cambio_seccion': 30000},
                             **kw)
    services, _ws, ctx = salida[:3]
    ctx.cancel = threading.Event()
    monkeypatch.setattr(services, '_libros_de_cabecera', lambda *_a: [])
    return salida


def _curva_de_servicio(medidor='M1'):
    rng = random.Random(3)
    return {medidor: _curva(rng, 60, kw=1000.0, por_dia=_con_valle(rng, 60, 20, 15))}


def test_informe_la_tabla_de_la_escalera_lleva_el_valle(tmp_path, monkeypatch):
    """073:RF-30, 073:RF-17 — la evaluación recibe los puntos de la medición; cada alternativa de la
    tabla dice su tensión, nodo y fecha, y se elige la que cumple también en valle."""
    def evaluar(nombre):
        banco = nombre.startswith('bancos') and '+' not in nombre
        return {'nombre': nombre, 'maxima': True, 'fraccion': 1.0, 'perdidas_kw': 10.0, 'motivos': [],
                'valle': not banco, 'valle_motivos': ['B4 sube'] if banco else [], 'valle_u_max': 1.08 if banco else 1.01,
                'valle_nodo': 'B4', 'valle_fecha': '2026-03-05 03:00:00',
                'valle_casos': {'sin_cargas': {'cumple': not banco, 'u_max': 1.08, 'nodo': 'B4', 'fecha': 'x'}}}

    services, ws, ctx, planes, aplicadas, _apartadas = _escalera(tmp_path, monkeypatch, evaluar)
    monkeypatch.setattr(vl, 'curvas_medidas', lambda *_a, **_k: (_curva_de_servicio(), []))
    r = services.obras_escalera(ws, ctx, 'P', ['F1'], anio_casos=2026)
    (_a, ev), = [x for x in planes if '--evaluar' in x[0]]
    assert ev['valle']['comprobado'] and ev['valle']['puntos'][0]['factores']['F1'] > 0
    (f1,) = r['alimentadores']
    assert not f1['elegida'].startswith('bancos') and aplicadas
    fila = next(t for t in f1['tabla'] if t['nombre'].startswith('bancos'))
    assert fila['valle'] is False and fila['valle_u_max'] == 1.08 and '1,080' in fila['valle_texto']
    assert fila['valle_casos']['sin_cargas']['u_max'] == 1.08 and 'sin cargas nuevas' in fila['valle_texto']
    assert r['valle']['ventanas'][0]['duracion_dias'] > 0                         # 073:RF-36
    assert any('073:RF-20' in a for a in f1['avisos'])
    assert services.valle_de_la_obra(ws, 'P', 'F1')['valle'] is True


def test_informe_sin_medicion_la_escalera_no_se_bloquea_y_lo_dice(tmp_path, monkeypatch):
    """073:RF-24, 073:RF-31 — sin libros para el valle se elige igual, con «no comprobado en valle»."""
    def evaluar(nombre):
        return {'nombre': nombre, 'maxima': nombre.startswith('bancos'), 'fraccion': 1.0, 'perdidas_kw': 10.0, 'motivos': []}

    services, ws, ctx, _planes, aplicadas, _apartadas = _escalera(tmp_path, monkeypatch, evaluar)
    monkeypatch.setattr(vl, 'curvas_medidas', lambda *_a, **_k: ({}, ['M1: sin curva para el valle']))
    r = services.obras_escalera(ws, ctx, 'P', ['F1'], anio_casos=2026)
    (f1,) = r['alimentadores']
    assert f1['elegida'].startswith('bancos') and aplicadas
    assert any('no comprobado en valle' in a for a in f1['avisos'])
    fila = next(t for t in f1['tabla'] if t['nombre'] == f1['elegida'])
    assert fila['valle'] is None and fila['valle_texto'].startswith('no comprobado en valle')
    assert fila['motivo'] == 'no comprobado en valle'
    assert services.valle_de_la_obra(ws, 'P', 'F1')['valle'] is None
    assert services.valle_de_la_obra(ws, 'OTRO', 'F1') is None


def test_informe_alimentador_con_central_queda_sin_comprobar(tmp_path, monkeypatch):
    """073:RF-12 — con central, su cabecera no es su demanda: sin comprobar y dicho, sin leer el valle."""
    from convertersmartgrid.web import services
    from convertersmartgrid.web.workspace import Workspace

    def leer(*_a, **_k):
        raise AssertionError('no se lee el valle de un alimentador con central')

    monkeypatch.setattr(vl, 'curvas_medidas', leer)
    monkeypatch.setattr(services, '_libros_de_cabecera', lambda *_a: [])

    class Ctx:
        class cancel:
            is_set = staticmethod(lambda: False)

        def log(self, *_a):
            pass

    r = services._valle_del_proyecto(Workspace(id='w', root=tmp_path), Ctx(), 2026, ['F1'],
                                     {'F1': {'kw': 1.0, 'medidor': 'M'}}, {}, ['F1'])
    assert not r['comprobado'] and r['puntos'] == [] and 'central' in r['motivo'] and 'F1' in r['motivo']


def test_informe_de_estudio_dice_la_tension_en_valle_de_cada_alternativa_con_bancos(tmp_path):
    """073:RF-32, 073:RF-31, 073:RF-40 — la sección de cada alternativa con obras, bancos o no, dice su
    tensión en valle o «no comprobado en valle»."""
    from dataclasses import replace

    from docx import Document
    from test_informe_docx import _caso as caso_docx
    from test_informe_docx import _config, _estudio

    from convertersmartgrid.informe_docx import escribir_informe_estudio
    from convertersmartgrid.informes import Etapa

    def texto(etapas):
        destino = tmp_path / 'i.docx'
        escribir_informe_estudio(_config(tmp_path), destino, _estudio(tmp_path, etapas=etapas))
        return '\n'.join(x.text for x in Document(destino).paragraphs)

    base = Etapa('bancos_nuevos', caso=caso_docx('Con proyecto', 0.96),
                 obras=({'tipo': 'banco', 'nodo': 'N15', 'kvar': 300},), anio=2027)
    sin = texto([base])
    assert 'No comprobado en valle' in sin
    con = texto([replace(base, valle={'valle': True, 'valle_u_max': 1.031, 'valle_nodo': 'N15',
                                      'valle_fecha': '2026-03-08 03:15:00'})])
    assert 'Tensión máxima en valle de 1,031 p.u. en N15 el 2026-03-08 03:15:00' in con
    assert 'o comprobado en valle' not in con
    conductor = Etapa('conductor', caso=caso_docx('Con proyecto', 0.96),
                      obras=({'tipo': 'conductor', 'conductor': 'AA 120', 'km': 1.5},), anio=2027)
    assert 'No comprobado en valle' in texto([conductor])
    assert texto([base, conductor]).count('o comprobado en valle') >= 2


def test_informe_de_factibilidad_tambien_lo_dice(tmp_path):
    """073:RF-32, 073:RF-31 — las obras evaluadas de un informe de factibilidad, igual."""
    from docx import Document
    from test_informe_docx import _config, _factibilidad

    from convertersmartgrid.informe_docx import escribir_informe_factibilidad

    obra = ({'tipo': 'banco', 'nodo': 'N15', 'kvar': 300},)
    destino = tmp_path / 'f.docx'
    escribir_informe_factibilidad(_config(tmp_path), destino, _factibilidad(tmp_path, obras=obra))
    assert 'o comprobado en valle' in '\n'.join(x.text for x in Document(destino).paragraphs)
    valle = {'valle': True, 'valle_u_max': 1.02, 'valle_nodo': 'N15', 'valle_fecha': '2026-03-08 03:15:00'}
    escribir_informe_factibilidad(_config(tmp_path), destino, _factibilidad(tmp_path, obras=obra, valle=valle))
    assert 'ensión máxima en valle de 1,020 p.u. en N15' in '\n'.join(x.text for x in Document(destino).paragraphs)


def _con_central(rng, dias, valle, generando):
    """Cabecera, generación, llegada y salida de un alimentador con central en su troncal.

    La demanda (aguas arriba más aguas abajo) tiene su valle en ``valle``; la central genera de más en
    ``generando``, y su cabecera baja allí sin que baje la demanda. Balance de la barra: generación =
    salida + llegada, con los flujos que salen de ella positivos (021:RF-29).
    """
    desde, largo = valle
    por_dia = _con_valle(rng, dias, desde, largo)
    arriba = _curva(rng, dias, kw=rng.uniform(2000, 4000), por_dia=por_dia, ruido=0)
    abajo = _curva(rng, dias, kw=rng.uniform(1000, 2000), por_dia=por_dia, ruido=0)
    g0, g1 = generando
    cab, gen, lle, sal = [], [], [], []
    for (t, pa, qa), (_t, pb, qb) in zip(arriba, abajo):
        d = (t - INICIO).days
        g = (0.45 if g0 <= d < g1 else 0.05) * (pa + pb)
        llegada = g - pb
        cab.append((t, pa - llegada, qa))
        gen.append((t, g, 0.0))
        lle.append((t, llegada, 0.0))
        sal.append((t, pb, qb))
    return cab, gen, lle, sal


@pytest.mark.parametrize('semilla', range(3))
def test_alimentador_con_central_da_su_valle_por_la_demanda_no_por_la_cabecera(semilla):
    """073:RF-12 — T9: con los medidores de la central, el valle sale de la curva de demanda (021:RF-47), en
    el periodo de menor demanda, y no donde la central hace bajar la cabecera."""
    rng = random.Random(semilla)
    dias = rng.randint(90, 150)
    valle = (rng.randint(55, dias - 30), rng.randint(12, 20))
    generando = (rng.randint(5, 15), rng.randint(30, 45))
    cab, gen, lle, sal = _con_central(rng, dias, valle, generando)
    curvas = {'CAB': cab, 'GEN': gen, 'LLE': lle, 'SAL': sal}
    central = {'generacion': 'GEN', 'llegada': 'LLE', 'salida': 'SAL'}

    demanda, motivo = vl.curva_con_central(curvas, 'CAB', central)
    assert motivo is None and demanda
    de_la_demanda = vl.valle_de_alcance('alimentador', {'CAB': demanda}, vl.Ajustes())
    de_la_cabecera = vl.valle_de_alcance('alimentador', {'CAB': cab}, vl.Ajustes())
    assert de_la_demanda.comprobado and de_la_demanda.ventana
    assert abs((de_la_demanda.ventana['inicio'] - _dia(valle[0])).days) <= 2
    assert abs((de_la_demanda.ventana['fin'] - _dia(valle[0] + valle[1] - 1)).days) <= 2
    # La cabecera sola lo pondría donde genera la central: por eso no se usa.
    assert de_la_cabecera.ventana and de_la_cabecera.ventana['fin'] < _dia(valle[0])


def test_alimentador_con_central_sin_un_medidor_queda_sin_comprobar_con_su_motivo():
    """073:RF-12 — sin la curva de un medidor de la central, sin comprobar y dicho; nunca un error."""
    rng = random.Random(7)
    cab, gen, lle, _sal = _con_central(rng, 60, (30, 10), (5, 15))
    demanda, motivo = vl.curva_con_central({'CAB': cab, 'GEN': gen, 'LLE': lle}, 'CAB',
                                           {'generacion': 'GEN', 'llegada': 'LLE', 'salida': 'SAL'})
    assert demanda == [] and 'SAL' in motivo


def test_el_proyecto_con_central_declarada_toma_el_valle_de_su_demanda(tmp_path, monkeypatch):
    """073:RF-12 — T9: con la central del perfil (021:RF-27), `_valle_del_proyecto` lee sus tres medidores y
    da el punto de valle de la demanda, con el aviso; sin ella, sin comprobar (prueba de arriba)."""
    from convertersmartgrid.web import services
    from convertersmartgrid.web.workspace import Workspace

    rng = random.Random(3)
    cab, gen, lle, sal = _con_central(rng, 120, (80, 15), (10, 40))
    pedidos = []

    def leer(_libros, pares, **_k):
        pedidos.extend(m for _a, m in pares)
        return {'CAB': cab, 'GEN': gen, 'LLE': lle, 'SAL': sal}, []

    monkeypatch.setattr(vl, 'curvas_medidas', leer)
    monkeypatch.setattr(services, '_libros_de_cabecera', lambda *_a: [])

    class Ctx:
        class cancel:
            is_set = staticmethod(lambda: False)

        def log(self, *_a):
            pass

    perfil = {'centrales_termicas': {'F1': {'generacion': 'GEN', 'llegada': 'LLE', 'salida': 'SAL'}}}
    r = services._valle_del_proyecto(Workspace(id='w', root=tmp_path), Ctx(), 2026, ['F1'],
                                     {'F1': {'kw': 6000.0, 'kvar': 1500.0, 'medidor': 'CAB'}}, perfil, ['F1'])
    assert sorted(pedidos) == ['CAB', 'GEN', 'LLE', 'SAL']
    assert r['comprobado'] and r['puntos'], r['motivo']
    assert any('073:RF-12' in a for a in r['avisos'])
    fecha = datetime.fromisoformat(str(r['puntos'][0]['fecha'])).date()
    assert _dia(78) <= fecha <= _dia(97)


def test_las_alternativas_se_piden_se_guardan_y_al_aplicar_no_se_vuelve_a_sortear(tmp_path, monkeypatch):
    """042:RF-55, 042:RF-58, 042:RF-59 — evaluar pide 3 y las guarda para el informe; aplicar la elegida no sortea."""
    def evaluar(nombre):
        return {'nombre': nombre, 'maxima': True, 'fraccion': 1.0, 'perdidas_kw': 10.0, 'motivos': []}

    services, ws, ctx, planes, _aplicadas, _apartadas = _escalera(tmp_path, monkeypatch, evaluar)
    monkeypatch.setattr(vl, 'curvas_medidas', lambda *_a, **_k: (_curva_de_servicio(), []))
    r = services.obras_escalera(ws, ctx, 'P', ['F1'], anio_casos=2026, aplicar=False, basta_una=True, por_alternativas=True)
    (_a, ev), = [x for x in planes if '--evaluar' in x[0]]
    assert ev['alternativas'] == 3 and ev['sorteos'] and all('escalones' in v for v in ev['variantes'])
    (f1,) = r['alimentadores']
    assert 1 <= len(f1['alternativas']) <= 3
    costos = [a['costo_anual'] for a in f1['alternativas']]
    assert costos == sorted(costos) and sum(a['elegida'] for a in f1['alternativas']) == 1
    assert services.alternativas_de_la_escalera(ws, 'P') == {'F1': f1['alternativas']}
    assert services.alternativas_de_la_escalera(ws, 'P', ['OTRO']) == {}
    planes.clear()
    services.obras_escalera(ws, ctx, 'P', ['F1'], anio_casos=2026, aplicar=True, basta_una=True, solo={'F1': f1['elegida']})
    aplicar = [x for x in planes if '--evaluar' in x[0]]
    assert all(not ev['sorteos'] and 'alternativas' not in ev for _a, ev in aplicar)


def test_la_obra_del_deficit_previo_va_aparte_y_sin_sorteos(tmp_path, monkeypatch):
    """042:RF-64, 042:RF-65 — su objetivo son esas barras, se mide con la máxima y se guarda con su etiqueta, sin aplicarse."""
    def evaluar(nombre):
        return {'nombre': nombre, 'maxima': True, 'fraccion': 1.0, 'perdidas_kw': 10.0, 'motivos': []}

    services, ws, ctx, planes, aplicadas, _apartadas = _escalera(tmp_path, monkeypatch, evaluar)
    monkeypatch.setattr(vl, 'curvas_medidas', lambda *_a, **_k: (_curva_de_servicio(), []))
    r = services.obras_escalera(ws, ctx, 'P', ['F1'], anio_casos=2026, aplicar=False, basta_una=True, por_alternativas=True,
                                previas={'F1': ['F1_B4', 'F1_B2']}, etiqueta_previas='déficit previo')
    (_a, ev), = [x for x in planes if '--evaluar' in x[0]]
    assert 'valle' in ev                                                        # 042:RF-69: también se mide en valle
    assert ev['barras_cargas'] == ['F1_B4', 'F1_B2'] and ev['sorteos'] == [] and not aplicadas
    (f1,) = r['alimentadores']
    assert f1['alternativas'] and all(a['fraccion'] is None for a in f1['alternativas'])
    guardadas = services.alternativas_de_la_escalera(ws, 'P')
    assert list(guardadas) == ['F1 · déficit previo']


def test_si_ninguna_corrige_el_deficit_lo_dice_con_su_motivo(tmp_path, monkeypatch):
    """042:RF-66 — nunca sin respuesta: la más cercana y lo que queda."""
    def evaluar(nombre):
        return {'nombre': nombre, 'maxima': False, 'fraccion': None, 'perdidas_kw': 10.0, 'motivos': ['F1_B4 a 0,91 p.u.']}

    services, ws, ctx, _planes, _aplicadas, _apartadas = _escalera(tmp_path, monkeypatch, evaluar)
    monkeypatch.setattr(vl, 'curvas_medidas', lambda *_a, **_k: (_curva_de_servicio(), []))
    r = services.obras_escalera(ws, ctx, 'P', ['F1'], anio_casos=2026, aplicar=False, basta_una=True, por_alternativas=True,
                                previas={'F1': ['F1_B4']}, etiqueta_previas='déficit previo')
    (alt,) = r['alimentadores'][0]['alternativas']
    assert alt['nombre'].startswith('ninguna obra corrige; la más cercana:') and 'F1_B4 a 0,91' in alt['nombre']
    assert alt['costo_anual'] is None
    r = services.obras_escalera(ws, ctx, 'P', ['F1'], anio_casos=2026, aplicar=False, basta_una=True, por_alternativas=True,
                                previas={'F1': ['SIN_CAMINO']}, etiqueta_previas='déficit previo')
    assert 'no hay variante' in r['alimentadores'][0]['alternativas'][0]['nombre']


def test_la_evaluacion_proyecta_con_la_tasa_de_largo_plazo_y_dice_la_medida(tmp_path, monkeypatch):
    """042:RF-86 — el plan lleva la de largo plazo aunque la medida sea mucho mayor, y el aviso dice las dos."""
    def evaluar(nombre):
        return {'nombre': nombre, 'maxima': True, 'fraccion': 1.0, 'perdidas_kw': 10.0, 'motivos': []}

    services, ws, ctx, planes, _aplicadas, _apartadas = _escalera(tmp_path, monkeypatch, evaluar)
    monkeypatch.setattr(vl, 'curvas_medidas', lambda *_a, **_k: (_curva_de_servicio(), []))
    monkeypatch.setattr(services, '_tasa_del_alimentador', lambda *_a: 0.165)
    r = services.obras_escalera(ws, ctx, 'P', ['F1'], anio_casos=2026, aplicar=False, basta_una=True, por_alternativas=True)
    (_a, ev), = [x for x in planes if '--evaluar' in x[0]]
    assert ev['horizonte']['tasa'] < 0.1
    assert any('042:RF-86' in a and '16.50' in a for a in r['alimentadores'][0]['avisos'])
