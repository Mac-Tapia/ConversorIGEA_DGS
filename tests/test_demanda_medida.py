"""Spec 004, demanda medida: lectura de los cuatro libros sin datos reales.

Los libros se escriben aquí con openpyxl (``.xlsx``); el lector es el mismo para ``.xls``
y ``.xlsb`` (python-calamine). Las columnas se sortean de orden, como en la medición
real, donde cada medidor las exporta en otro orden. Con ``IGEA_DEMANDA_DIR`` (la carpeta
con las cuatro subcarpetas de la distribuidora) corren además las de datos reales; los
valores no se imprimen: son datos de la distribuidora (P9).
"""
from __future__ import annotations

import os
import random
from datetime import datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip('python_calamine')
openpyxl = pytest.importorskip('openpyxl')

from igea_dgs import demanda_medida as dm  # noqa: E402

SEMILLA = int(os.environ.get('IGEA_SCALE_SEED', random.randrange(1 << 30)))
INICIO = datetime(2026, 7, 1)


def _libro(path: Path, hojas: dict[str, list[list]]) -> Path:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nombre, filas in hojas.items():
        hoja = wb.create_sheet(nombre)
        for fila in filas:
            hoja.append(fila)
    wb.save(path)
    return path


def _medicion(rng, n: int, columnas: dict[str, str], pico: int | None = None,
              vacios: float = 0.0) -> tuple[list[list], dict]:
    """Hoja de medición con columnas en orden sorteado. Devuelve las filas y el pico."""
    nombres = list(columnas.values())
    rng.shuffle(nombres)
    cab = ['Local Time', 'Timestamp'] + nombres
    filas = [cab]
    pico = rng.randrange(n) if pico is None else pico
    esperado = {}
    for i in range(n):
        kw = 5000.0 if i == pico else round(rng.uniform(100, 4000), 1)
        kvar = round(kw * rng.uniform(-0.3, 0.5), 1)
        kva = (kw ** 2 + kvar ** 2) ** 0.5
        valores = {'kw': kw, 'kvar': kvar, 'kva': kva, 'fp_pct': 100 * kw / kva}
        fila = {columnas.get('kw'): kw, columnas.get('kvar'): kvar, columnas.get('kva'): kva,
                columnas.get('fp'): valores['fp_pct']}
        if i != pico and rng.random() < vacios:
            fila[columnas['kw']] = None if rng.random() < 0.5 else 'n/d'
        t = INICIO + timedelta(minutes=15 * i)
        filas.append([t, t] + [fila.get(c) for c in nombres])
        if i == pico:
            esperado = {'fecha': t, **valores}
    return filas, esperado


# =========================================================================== medidores
def test_medidores_del_alimentador(tmp_path):
    """004:RF-22 — el alimentador escrito devuelve cada medidor que le asigna el libro."""
    libro = _libro(tmp_path / 'm.xlsx', {'alimentador_medidor': [
        [None, None, None],
        ['codigo alimentador', 'Medidor', 'Nivel Tension'],
        ['A101', 'M-AB1', 10], ['a 101', 'M-AB2', 10], ['A102', 'M-XY9', 22.9], ['A101', 'M-AB1', 10],
    ]})
    meds = dm.leer_medidores(libro)
    assert dm.medidores_de(meds, 'A101') == ['M-AB1', 'M-AB2']
    assert dm.medidores_de(meds, 'A102') == ['M-XY9']


def test_celda_con_dos_medidores_se_parte(tmp_path):
    """004:RF-22 — «A Y B» en la celda del medidor son dos medidores, como en el libro real."""
    libro = _libro(tmp_path / 'm.xlsx', {'h': [['Alimentador', 'Medidor'], ['A1', 'IN1_V18 Y IN1_V119'],
                                               ['A2', 'M1, M2']]})
    meds = dm.leer_medidores(libro)
    assert dm.medidores_de(meds, 'A1') == ['IN1_V18', 'IN1_V119']
    assert dm.medidores_de(meds, 'A2') == ['M1', 'M2']


def test_hojas_completas_con_sufijo(tmp_path):
    """004:RF-24 / RF-32 — sin hoja con su nombre: la única hoja completa con su código se
    usa con aviso; si hay varias, se pide escribir la que se quiere y esa casa."""
    rng = random.Random(SEMILLA)
    pe, esperado = _medicion(rng, 20, {'kw': 'kW tot', 'kvar': 'kVAR tot'})
    tm, _ = _medicion(rng, 20, {'kw': 'kW tot', 'kvar': 'kVAR tot'})
    _libro(tmp_path / 'uno.xlsx', {'L-1_PE': pe})
    res = dm.maximas([tmp_path / 'uno.xlsx'], [('', 'L-1')])[0]
    assert res.kw == esperado['kw'] and res.avisos
    _libro(tmp_path / 'dos.xlsx', {'L-1_PE': pe, 'L-1_TM': tm})
    res = dm.maximas([tmp_path / 'dos.xlsx'], [('', 'L-1')])[0]
    assert 'L-1_PE' in res.error and 'L-1_TM' in res.error
    assert dm.maximas([tmp_path / 'dos.xlsx'], [('', 'L-1_PE')])[0].kw == esperado['kw']


def test_alimentador_sin_medidor_devuelve_vacio(tmp_path):
    """004:RF-23 — un alimentador que no está no inventa medidores: la web pide escribirlo."""
    libro = _libro(tmp_path / 'm.xlsx', {'h': [['Alimentador', 'Medidor'], ['A1', 'M1']]})
    assert dm.medidores_de(dm.leer_medidores(libro), 'NO_ESTA') == []


# =========================================================================== cabecera
def test_hoja_del_medidor_por_codigo_normalizado(tmp_path):
    """004:RF-24 — la hoja se busca en todos los libros, sin mayúsculas, espacios ni separadores."""
    rng = random.Random(SEMILLA)
    filas, esperado = _medicion(rng, 50, {'kw': 'kW tot', 'kvar': 'kVAR tot', 'kva': 'kVA tot'})
    _libro(tmp_path / 'SISTEMA A.xlsx', {'Otro-1': filas})
    _libro(tmp_path / 'SISTEMA B.xlsx', {'Info': [['x']], 'm ab_12': filas})
    res = dm.maximas([tmp_path], [('A1', 'M-AB12')])[0]
    assert res.error is None, res
    assert (res.libro, res.hojas) == ('SISTEMA B.xlsx', ['m ab_12'])
    assert res.kw == esperado['kw']


def test_prefijo_no_confunde_x1_con_x10(tmp_path):
    """004:RF-24 — ``X1`` no encuentra la hoja ``X10``: el sufijo va tras un separador."""
    rng = random.Random(SEMILLA)
    filas, _ = _medicion(rng, 10, {'kw': 'kW tot'})
    _libro(tmp_path / 'c.xlsx', {'X10': filas})
    assert dm.maximas([tmp_path / 'c.xlsx'], [('', 'X1')])[0].error


def test_medidor_partido_en_hojas_se_une_por_fecha(tmp_path):
    """004:RF-25 — una hoja por magnitud (``<medidor>_<sufijo>``) se une por fecha y hora."""
    rng = random.Random(SEMILLA)
    completo, esperado = _medicion(rng, 80, {'kw': 'kW tot', 'kvar': 'kVAR tot', 'kva': 'kVA tot'})
    cab = completo[0]
    partes = {}
    for suf, col in (('v19', 'kW tot'), ('v20', 'kVAR tot'), ('v9', 'kVA tot')):
        k = cab.index(col)
        filas = [[r[0], r[1], r[k]] for r in completo]
        cuerpo = filas[1:]
        rng.shuffle(cuerpo)                         # cada hoja en su propio orden
        partes[f'M7_{suf}'] = [filas[0]] + cuerpo
    _libro(tmp_path / 'c.xlsx', {**partes, 'M70': completo})
    res = dm.maximas([tmp_path / 'c.xlsx'], [('', 'M7')])[0]
    assert res.error is None, res
    assert sorted(res.hojas) == ['M7_v19', 'M7_v20', 'M7_v9']
    assert res.fecha == esperado['fecha'].isoformat(sep=' ')
    assert (res.kw, res.kvar) == (esperado['kw'], esperado['kvar'])
    assert res.kva == pytest.approx(esperado['kva'])


def test_la_maxima_a_medianoche_conserva_su_hora(tmp_path):
    """004:RF-25, RF-28 — python-calamine lee el registro de las 00:00 como fecha sin hora
    (``date``) y los demás con hora: la máxima a medianoche salía «2026-07-01» y, partida
    en hojas, no casaba con la misma fecha y hora de las otras. Con las semillas 116, 183,
    299 y 309 la prueba sorteada caía justo ahí y fallaba solo a veces."""
    rng = random.Random(SEMILLA)
    completo, esperado = _medicion(rng, 40, {'kw': 'kW tot', 'kvar': 'kVAR tot', 'kva': 'kVA tot'},
                                   pico=0)
    assert esperado['fecha'] == INICIO
    cab = completo[0]
    partes = {}
    for suf, col in (('v19', 'kW tot'), ('v20', 'kVAR tot'), ('v9', 'kVA tot')):
        k = cab.index(col)
        partes[f'M7_{suf}'] = [[r[0], r[1], r[k]] for r in completo]
    _libro(tmp_path / 'c.xlsx', {'M8': completo, **partes})
    for medidor in ('M8', 'M7'):
        res = dm.maximas([tmp_path / 'c.xlsx'], [('', medidor)])[0]
        assert res.error is None, res
        assert res.fecha == '2026-07-01 00:00:00', medidor
        assert (res.kw, res.kvar) == (esperado['kw'], esperado['kvar'])


def test_hoja_con_su_nombre_sin_kw_usa_sus_partes(tmp_path):
    """004:RF-25 — como en Ica: la hoja del medidor trae otras magnitudes y el kW está en
    una parte ``<medidor>_<sufijo>``."""
    rng = random.Random(SEMILLA)
    completo, esperado = _medicion(rng, 30, {'kw': 'kW tot', 'kvar': 'kVAR tot'})
    k_kw, k_kvar = completo[0].index('kW tot'), completo[0].index('kVAR tot')
    hojas = {
        'M5': [[r[0], r[1], r[k_kvar] if i else 'I a'] for i, r in enumerate(completo)],
        'M5_v19': [[r[0], r[1], r[k_kw]] for r in completo],
        'M5_v20': [[r[0], r[1], r[k_kvar]] for r in completo],
    }
    _libro(tmp_path / 'c.xlsx', hojas)
    res = dm.maximas([tmp_path / 'c.xlsx'], [('', 'M5')])[0]
    assert res.error is None, res
    assert sorted(res.hojas) == ['M5_v19', 'M5_v20']
    assert (res.kw, res.kvar) == (esperado['kw'], esperado['kvar'])
    assert res.columnas['fp'] == 'calculado con kW y kVA'


def _canales(rng, base: str, n: int = 60) -> tuple[dict[str, list[list]], dict]:
    """Medidor partido en canales como IN111 de Ica: kW, kVAR, kVA y una corriente, cada
    uno en su hoja ``<base>_V<n>`` y en su propio orden."""
    completo, esperado = _medicion(rng, n, {'kw': 'kW tot', 'kvar': 'kVAR tot', 'kva': 'kVA tot'})
    cab = completo[0]
    hojas = {}
    for canal, col in (('V18', 'kW tot'), ('V19', 'kVAR tot'), ('V20', 'kVA tot'), ('V9', None)):
        k = cab.index(col) if col else None
        filas = [[r[0], r[1], (r[k] if k is not None else 1.0)] for r in completo[1:]]
        rng.shuffle(filas)
        hojas[f'{base}_{canal}'] = [['Local Time', 'Timestamp', col or 'I a']] + filas
    return hojas, esperado


def test_canal_del_kw_toma_el_kvar_de_su_hoja_hermana(tmp_path):
    """004:RF-44 — ``IN1_V18`` solo trae kW: el kVAR y el kVA salen de ``IN1_V19`` e
    ``IN1_V20`` en la fecha del kW máximo, no de sus propios máximos."""
    rng = random.Random(SEMILLA)
    hojas, esperado = _canales(rng, 'IN1')
    otro, _ = _canales(rng, 'IN10')                 # IN10_V19 no es hermana de IN1_V18
    _libro(tmp_path / 'c.xlsx', {**hojas, **otro})
    res = dm.maximas([tmp_path / 'c.xlsx'], [('A1', 'IN1_V18')])[0]
    assert res.error is None, res
    assert sorted(res.hojas) == ['IN1_V18', 'IN1_V19', 'IN1_V20']
    assert res.fecha == esperado['fecha'].isoformat(sep=' ')
    assert (res.kw, res.kvar) == (esperado['kw'], esperado['kvar'])
    assert res.kva == pytest.approx(esperado['kva']) and not res.kva_calculado
    assert res.fp_calculado and res.avisos


def test_kvar_en_dos_hojas_hermanas_no_se_elige(tmp_path):
    """004:RF-44 — si dos hojas dan el kVAR, no se toma ninguna y se avisa."""
    rng = random.Random(SEMILLA)
    hojas, esperado = _canales(rng, 'IN1')
    hojas['IN1_V29'] = hojas['IN1_V19']
    _libro(tmp_path / 'c.xlsx', hojas)
    res = dm.maximas([tmp_path / 'c.xlsx'], [('', 'IN1_V18')])[0]
    assert res.kw == esperado['kw'] and res.kvar is None
    assert any('IN1_V29' in a for a in res.avisos)


def test_base_del_medidor_necesita_un_digito():
    """004:RF-44 — ``L-6613`` no tiene por base ``L``: juntaría medidores distintos."""
    assert dm.base_del_medidor('IN111_V18') == 'IN111'
    assert dm.base_del_medidor('L-6613_PE') == 'L-6613'
    assert dm.base_del_medidor('L-6613') is None
    assert dm.base_del_medidor('M7') is None


def test_canal_sin_hoja_se_une_al_medidor_que_ya_lo_da(tmp_path):
    """004:RF-45 — «IN1_V18 Y IN1_V119»: V119 no tiene hoja y es canal de IN1; sale una
    sola fila, con aviso, en cualquier orden. Pedido solo, se lee como IN1."""
    rng = random.Random(SEMILLA)
    hojas, esperado = _canales(rng, 'IN1')
    _libro(tmp_path / 'c.xlsx', hojas)
    for orden in (['IN1_V18', 'IN1_V119'], ['IN1_V119', 'IN1_V18']):
        res = dm.maximas([tmp_path / 'c.xlsx'], [('A1', m) for m in orden])
        assert [r.medidor for r in res] == ['IN1_V18'], res
        assert res[0].kvar == esperado['kvar']
        assert any('IN1_V119' in a for a in res[0].avisos)
    solo = dm.maximas([tmp_path / 'c.xlsx'], [('A1', 'IN1_V119')])[0]
    assert solo.error is None and solo.canal_de == 'IN1'
    assert (solo.kw, solo.kvar) == (esperado['kw'], esperado['kvar'])
    # Un canal de un medidor que no está sigue siendo un error (RF-32).
    assert dm.maximas([tmp_path / 'c.xlsx'], [('A1', 'IN9_V119')])[0].error


@pytest.mark.parametrize('variante', [
    {'kw': 'kW tot', 'kvar': 'kVAR tot', 'kva': 'kVA tot', 'fp': 'PF lag mean'},
    {'kw': 'kW tot mean', 'kvar': 'kVAR tot mean', 'kva': 'kVA tot mean', 'fp': 'PF lead mean'},
    {'kw': 'KW_TOT', 'kvar': 'kvar tot', 'kva': 'Pot Aparente', 'fp': 'Factor de Potencia'},
])
def test_columnas_por_nombre_en_cualquier_posicion(tmp_path, variante):
    """004:RF-26 — cada variante de nombre y cualquier orden de columnas."""
    rng = random.Random(SEMILLA)
    filas, esperado = _medicion(rng, 60, variante)
    _libro(tmp_path / 'c.xlsx', {'MED1': filas})
    res = dm.maximas([tmp_path / 'c.xlsx'], [('', 'MED1')])[0]
    assert res.error is None, res
    assert set(res.columnas) == {'kw', 'kvar', 'kva', 'fp'}
    assert res.kw == esperado['kw'], f'semilla {SEMILLA}'


def test_kw_maximo_con_su_fecha_y_el_resto_del_mismo_registro(tmp_path):
    """004:RF-27 / RF-28 — kW máximo y su fecha; kVAR, kVA y FP del mismo registro.

    Los demás registros tienen kVAR y kVA mayores que los del pico en muchos casos: si
    el lector buscara el máximo de cada columna, la prueba fallaría.
    """
    filas = [['kVA tot', 'Local Time', 'kW tot', 'PF lag mean', 'kVAR tot']]
    for i in range(30):
        t = INICIO + timedelta(minutes=15 * i)
        if i == 17:
            filas.append([1000.0, t, 900.0, 90.0, 436.0])
        else:
            filas.append([5000.0, t, 100.0 + i, 50.0, 4000.0])
    _libro(tmp_path / 'c.xlsx', {'M1': filas})
    res = dm.maximas([tmp_path / 'c.xlsx'], [('', 'M1')])[0]
    assert res.fecha == (INICIO + timedelta(minutes=15 * 17)).isoformat(sep=' ')
    assert (res.kw, res.kvar, res.kva) == (900.0, 436.0, 1000.0)
    assert res.fp == pytest.approx(0.90)
    assert not res.kva_calculado and not res.fp_calculado


def test_fp_en_porcentaje_pasa_a_decimal_con_su_signo():
    """004:RF-28 — ``PF lag/lead mean`` vienen en %: se dan en tanto por uno, con su signo."""
    assert dm.fp_decimal(98.5) == pytest.approx(0.985)
    assert dm.fp_decimal(-97.0) == pytest.approx(-0.97)
    assert dm.fp_decimal(0.93) == 0.93
    assert dm.fp_decimal(-0.93) == -0.93
    assert dm.fp_decimal(355.0) is None, 'más de ±100 no es un FP: se calcula'


def test_varios_medidores_por_separado_sin_sumar(tmp_path):
    """004:RF-29 — un alimentador con varios medidores: un resultado por medidor."""
    rng = random.Random(SEMILLA)
    hojas, esperados = {}, {}
    for m in ('MA', 'MB', 'MC'):
        hojas[m], esperados[m] = _medicion(rng, 40, {'kw': 'kW tot', 'kvar': 'kVAR tot'})
    _libro(tmp_path / 'c.xlsx', hojas)
    res = dm.maximas([tmp_path / 'c.xlsx'], [('A1', m) for m in hojas])
    assert [r.medidor for r in res] == ['MA', 'MB', 'MC']
    assert [r.kw for r in res] == [esperados[m]['kw'] for m in hojas]
    assert all(r.alimentador == 'A1' for r in res)


def test_kva_y_fp_calculados_y_marcados(tmp_path):
    """004:RF-30 — sin kVA ni FP en el registro, se calculan con kW y kVAR y se marcan."""
    filas = [['Local Time', 'kW tot', 'kVAR tot', 'PF sign tot us'],
             [INICIO, 300.0, -400.0, 355.0], [INICIO + timedelta(minutes=15), 10.0, 1.0, 99.0]]
    _libro(tmp_path / 'c.xlsx', {'M1': filas})
    res = dm.maximas([tmp_path / 'c.xlsx'], [('', 'M1')])[0]
    assert res.kva == pytest.approx(500.0) and res.kva_calculado
    assert res.fp == pytest.approx(-0.6) and res.fp_calculado, 'kVAR capacitivo: FP negativo'


def test_registros_vacios_o_no_numericos_no_son_maximo(tmp_path):
    """004:RF-31 — una celda de kW vacía o con texto no cuenta; tampoco filas sin datos."""
    rng = random.Random(SEMILLA)
    filas, esperado = _medicion(rng, 120, {'kw': 'kW tot', 'kvar': 'kVAR tot'}, vacios=0.3)
    filas.insert(1, [INICIO - timedelta(days=1), None, 'ERROR', None])
    _libro(tmp_path / 'c.xlsx', {'M1': filas})
    res = dm.maximas([tmp_path / 'c.xlsx'], [('', 'M1')])[0]
    assert res.kw == esperado['kw'], f'semilla {SEMILLA}'


def test_empate_toma_el_primero_en_el_tiempo(tmp_path):
    """004:RF-27 — dos registros con el mismo kW máximo: el anterior en el tiempo."""
    t1, t2 = INICIO + timedelta(hours=5), INICIO + timedelta(hours=1)
    _libro(tmp_path / 'c.xlsx', {'M1': [['Local Time', 'kW tot'], [t1, 50.0], [t2, 50.0], [INICIO, 1.0]]})
    assert dm.maximas([tmp_path / 'c.xlsx'], [('', 'M1')])[0].fecha == t2.isoformat(sep=' ')


def test_local_time_solo_fecha_usa_timestamp(tmp_path):
    """004:RF-27 — si «Local Time» trae solo el día, la hora sale de «Timestamp»."""
    t = INICIO + timedelta(hours=19, minutes=45)
    _libro(tmp_path / 'c.xlsx', {'M1': [['Local Time', 'Timestamp', 'kW tot'],
                                        [t.date(), t, 70.0], [INICIO.date(), INICIO, 1.0]]})
    assert dm.maximas([tmp_path / 'c.xlsx'], [('', 'M1')])[0].fecha == t.isoformat(sep=' ')


def test_medidor_no_hallado_o_sin_kw_sigue_con_los_demas(tmp_path):
    """004:RF-32 — medidor ausente o sin columna de kW: error con libro y hoja, y se sigue."""
    rng = random.Random(SEMILLA)
    buena, esperado = _medicion(rng, 20, {'kw': 'kW tot'})
    _libro(tmp_path / 'c.xlsx', {'SINKW': [['Local Time', 'kVAR tot'], [INICIO, 3.0]], 'OK': buena})
    res = dm.maximas([tmp_path / 'c.xlsx'], [('', 'NADA'), ('', 'SINKW'), ('', 'OK')])
    assert 'NADA' in res[0].error
    assert 'c.xlsx' in res[1].error and 'SINKW' in res[1].error and 'kW' in res[1].error
    assert res[2].kw == esperado['kw']


def test_cancelar_entre_medidores(tmp_path):
    """004:RF-32 — cancelar no deja un medidor a medias: se para antes del siguiente."""
    rng = random.Random(SEMILLA)
    hojas = {m: _medicion(rng, 10, {'kw': 'kW tot'})[0] for m in ('A', 'B', 'C')}
    _libro(tmp_path / 'c.xlsx', hojas)
    vistos = []
    res = dm.maximas([tmp_path / 'c.xlsx'], [('', m) for m in hojas],
                     cancelado=lambda: len(vistos) >= 1, progreso=lambda *a: vistos.append(a))
    assert [r.medidor for r in res] == ['A']


def test_alias_de_la_empresa(tmp_path):
    """004:RF-26 — una cabecera propia de una empresa entra por el JSON de alias (P13)."""
    (tmp_path / 'alias.json').write_text('{"kw": ["Demanda Activa"]}', encoding='utf-8')
    alias = dm.cargar_alias(tmp_path / 'alias.json')
    _libro(tmp_path / 'c.xlsx', {'M1': [['Fecha', 'Demanda Activa'], [INICIO, 12.0]]})
    assert dm.maximas([tmp_path / 'c.xlsx'], [('', 'M1')])[0].error
    assert dm.maximas([tmp_path / 'c.xlsx'], [('', 'M1')], alias=alias)[0].kw == 12.0
    (tmp_path / 'malo.json').write_text('{"kwh": ["x"]}', encoding='utf-8')
    with pytest.raises(dm.DemandaError, match='kwh'):
        dm.cargar_alias(tmp_path / 'malo.json')


# =========================================================================== curva
def test_curva_del_registro_en_orden_y_fuera_de_to_dict(tmp_path):
    """006:RF-31 — la búsqueda de la máxima conserva la curva de kW y kVAR, ordenada por
    fecha, sin meterla en el resultado que viaja al navegador."""
    rng = random.Random(SEMILLA)
    n = rng.randrange(50, 300)
    filas, esperado = _medicion(rng, n, {'kw': 'kW tot', 'kvar': 'kVAR tot'})
    cab, cuerpo = filas[0], filas[1:]
    rng.shuffle(cuerpo)
    _libro(tmp_path / 'c.xlsx', {'M1': [cab] + cuerpo})
    res = dm.maximas([tmp_path / 'c.xlsx'], [('', 'M1')])[0]
    assert len(res.curva) == n and res.fuera_de_curva == 0, f'semilla {SEMILLA}'
    fechas = [p[0] for p in res.curva]
    assert fechas == sorted(fechas)
    pico = next(p for p in res.curva if p[0] == esperado['fecha'])
    assert pico[1] == esperado['kw'] and pico[2] == esperado['kvar']
    d = res.to_dict()
    assert 'curva' not in d and d['fuera_de_curva'] == 0


def test_curva_deja_fuera_registros_sin_fecha_o_sin_kw(tmp_path):
    """006:RF-37 — registros sin fecha o con kW no numérico quedan fuera y se cuentan."""
    rng = random.Random(SEMILLA)
    n = rng.randrange(40, 200)
    filas, _esperado = _medicion(rng, n, {'kw': 'kW tot', 'kvar': 'kVAR tot'}, vacios=0.3)
    k = filas[0].index('kW tot')
    malos_kw = sum(1 for f in filas[1:] if not isinstance(f[k], float))
    filas.append([None, None] + [7.0] * (len(filas[0]) - 2))      # sin fecha
    _libro(tmp_path / 'c.xlsx', {'M1': filas})
    res = dm.maximas([tmp_path / 'c.xlsx'], [('', 'M1')])[0]
    assert len(res.curva) == n - malos_kw, f'semilla {SEMILLA}'
    assert res.fuera_de_curva == malos_kw + 1


def _curva_sorteada(rng, n: int) -> tuple[list, int]:
    pico = rng.randrange(n)
    curva = [(INICIO + timedelta(minutes=15 * i), 9999.0 if i == pico else rng.uniform(0, 5000),
              rng.uniform(-100, 100)) for i in range(n)]
    return curva, pico


def test_reducir_curva_conserva_la_maxima_y_no_pasa_del_tope():
    """006:RF-39 — la curva reducida no pasa del tope, sigue en orden y la máxima nunca
    desaparece, esté donde esté."""
    rng = random.Random(SEMILLA)
    for _ in range(20):
        n = rng.randrange(1, 40000)
        tope = rng.choice([2, 10, 500, 2000])
        curva, pico = _curva_sorteada(rng, n)
        red = dm.reducir_curva(curva, max_puntos=tope)
        assert len(red) <= max(tope, 2) and len(red) <= n, f'semilla {SEMILLA}, n={n}, tope={tope}'
        assert curva[pico] in red, f'semilla {SEMILLA}, n={n}, tope={tope}'
        assert [p[0] for p in red] == sorted(p[0] for p in red)
        if n <= tope:
            assert red == curva


def test_reducir_curva_por_tramo():
    """006:RF-39 — con desde y hasta, solo el tramo, con sus extremos incluidos."""
    rng = random.Random(SEMILLA)
    curva, _pico = _curva_sorteada(rng, 1000)
    desde, hasta = curva[100][0], curva[299][0]
    red = dm.reducir_curva(curva, desde, hasta, max_puntos=5000)
    assert red == curva[100:300]
    assert dm.reducir_curva(curva, hasta, desde) == []
def _suministros(tmp_path) -> Path:
    return _libro(tmp_path / 'ML.xlsx', {'Hoja1': [
        ['Suministro', 'Suministro Act', 'Cliente', 'Generador', 'VAD', 'SED', 'RADIAL', 'Concesión'],
        [11, 9011, 'C1', '', '', 'E100', 'A101', ''],
        [12, 9012, 'C2', '', '', 'E200', 'A102', ''],
        [13, '0009013', 'C3', '', '', '', 'A103', ''],
        [14.0, 9014.0, 'C4', '', '', 'E400', '', ''],
    ]})


def test_suministros(tmp_path):
    """004:RF-33 — código actual, anterior, SED y radial de cada suministro."""
    filas, avisos = dm.leer_suministros(_suministros(tmp_path))
    assert not avisos
    assert [(s.actual, s.anterior, s.sed, s.radial) for s in filas][:2] == [
        ('9011', '11', 'E100', 'A101'), ('9012', '12', 'E200', 'A102')]


FORMATO_ANTIGUO = {'portada': [['x']], 'resumen': [
    ['Clientes importantes'],
    ['Bitácora', 'Ítem', 'Suministrador', 'Inicio', 'Nis', 'EA', 'ERI', 'ERC', 'Pot', 'MDHP'],
    ['', 1, 'X', '', 11, 1000.5, 200.0, 0, 350.0, 1],
    ['', 2, 'X', '', 9012, 2000.0, 300.0, 0, 400.0, 1],
    ['', 3, 'X', '', 99999, 10.0, 1.0, 0, 5.0, 1],
    ['', 4, 'X', '', 13, 10.0, 1.0, 0, 5.0, 1],
    ['', 5, 'X', '', 11, 1.0, 1.0, 0, 1.0, 1],
]}
FORMATO_NUEVO = {'Resumen': [
    ['Clientes importantes'], [], [],
    ['SUMINISTRO', 'COD_CL', 'CLIENTE', 'SUMINISTRADOR', 'ALIMENTADOR', 'EA_TOTAL', 'ERI_TOTAL',
     'ERC_TOTAL', 'POT_MAX', 'POT_HP', 'POT_FP', 'POT_COINCIDENTE'],
    ['9011', 'c', 'C1', 'X', 'A101', 1500.0, 250.0, 0, 360.0, 300.0, 200.0, 280.0],
    [14, 'c', 'C4', 'X', '', 50.0, 5.0, 0, 20.0, 10.0, 10.0, 10.0],
]}


def test_mes_del_nombre_sale_del_patron_del_perfil():
    """013:RF-3 — el código interpreta los grupos del patrón recibido, no un nombre de
    Electro Dunas incrustado."""
    patron = r'^(?P<mes>0[1-9]|1[0-2])(?P<anio>\d{2})clientesImportantes\.(xlsb|xlsx)$'
    assert dm.mes_de_nombre('0126clientesImportantes.xlsb', patron) == '2026-01'
    assert dm.mes_de_nombre('0726clientesImportantes.xlsx', patron) == '2026-07'
    assert dm.mes_de_nombre('clientes-julio.xlsx', patron) is None
    assert dm.mes_de_nombre('1326clientesImportantes.xlsx', patron) is None


def test_catalogo_acepta_extensiones_y_no_abre_nombres_resueltos(tmp_path, monkeypatch):
    """013:RF-1 / 013:RF-2 / 013:RF-3 — un nombre resuelto basta para catalogar los
    formatos admitidos; abrir esos libros de gran tamaño sería una regresión."""
    patron = r'^(?P<mes>0[1-9]|1[0-2])(?P<anio>\d{2})clientes\.(xls|xlsx|xlsb|xlsm)$'
    nombres = ['0126clientes.xls', '0226clientes.xlsx', '0326clientes.xlsb',
               '0426clientes.xlsm']
    for nombre in nombres:
        (tmp_path / nombre).write_bytes(b'no hace falta abrir')
    monkeypatch.setattr(dm, '_abrir', lambda _p: pytest.fail('no debía abrir el libro'))

    catalogo = dm.catalogar_libros_clientes(tmp_path, patron, {}, dm.ALIAS)

    assert [(x.nombre, x.mes, x.origen_mes, x.activo) for x in catalogo] == [
        ('0126clientes.xls', '2026-01', 'nombre', True),
        ('0226clientes.xlsx', '2026-02', 'nombre', True),
        ('0326clientes.xlsb', '2026-03', 'nombre', True),
        ('0426clientes.xlsm', '2026-04', 'nombre', True),
    ]


def test_catalogo_busca_fecha_interna_solo_si_da_un_mes_inequivoco(tmp_path):
    """013:RF-4 — una fecha interna única asigna mes; cero o varios meses dejan el libro
    pendiente de decisión humana."""
    _libro(tmp_path / 'unico.xlsx', {'Resumen': [
        ['Nis', 'Fecha', 'EA'], [11, datetime(2026, 5, 2), 10],
        [12, datetime(2026, 5, 31), 20],
    ]})
    _libro(tmp_path / 'ambiguo.xlsx', {'Resumen': [
        ['Nis', 'Periodo', 'EA'], [11, datetime(2026, 5, 31), 10],
        [12, datetime(2026, 6, 1), 20],
    ]})
    _libro(tmp_path / 'sin-fecha.xlsx', {'Resumen': [
        ['Nis', 'EA'], [11, 10],
    ]})

    por_nombre = {x.nombre: x for x in dm.catalogar_libros_clientes(tmp_path, None, {}, dm.ALIAS)}

    assert (por_nombre['unico.xlsx'].mes, por_nombre['unico.xlsx'].origen_mes,
            por_nombre['unico.xlsx'].activo) == ('2026-05', 'contenido', True)
    assert (por_nombre['ambiguo.xlsx'].mes, por_nombre['ambiguo.xlsx'].origen_mes,
            por_nombre['ambiguo.xlsx'].activo) == (None, 'sin_mes', False)
    assert (por_nombre['sin-fecha.xlsx'].mes, por_nombre['sin-fecha.xlsx'].origen_mes,
            por_nombre['sin-fecha.xlsx'].activo) == (None, 'sin_mes', False)


def test_asignacion_manual_manda_sobre_nombre_y_contenido(tmp_path, monkeypatch):
    """013:RF-4 — la decisión explícita del operador no se sustituye por inferencias."""
    path = tmp_path / '0126clientesImportantes.xlsx'
    path.write_bytes(b'no abrir')
    patron = r'^(?P<mes>\d{2})(?P<anio>\d{2})clientesImportantes\.xlsx$'
    monkeypatch.setattr(dm, '_abrir', lambda _p: pytest.fail('la asignación manual era suficiente'))

    catalogo = dm.catalogar_libros_clientes(tmp_path, patron, {path.name: '2026-07'}, dm.ALIAS)

    assert len(catalogo) == 1
    assert (catalogo[0].mes, catalogo[0].origen_mes, catalogo[0].activo) == (
        '2026-07', 'manual', True)


def test_duplicado_mensual_usa_el_mas_reciente_y_avisa_ambos(tmp_path, monkeypatch):
    """013:RF-5 — dos libros del mismo mes no se mezclan: gana el `mtime_ns` mayor y la
    elección queda visible en ambos registros."""
    antiguo = tmp_path / '0126clientesImportantes.xlsb'
    nuevo = tmp_path / '0126clientesImportantes.xlsx'
    antiguo.write_bytes(b'antiguo')
    nuevo.write_bytes(b'nuevo')
    os.utime(antiguo, ns=(1_000_000_000, 1_000_000_000))
    os.utime(nuevo, ns=(2_000_000_000, 2_000_000_000))
    patron = r'^(?P<mes>\d{2})(?P<anio>\d{2})clientesImportantes\.(xlsb|xlsx)$'
    monkeypatch.setattr(dm, '_abrir', lambda _p: pytest.fail('el nombre resuelve el mes'))

    catalogo = dm.catalogar_libros_clientes(tmp_path, patron, {}, dm.ALIAS)
    por_nombre = {x.nombre: x for x in catalogo}

    assert not por_nombre[antiguo.name].activo
    assert por_nombre[nuevo.name].activo
    assert all(antiguo.name in ' '.join(x.avisos) and nuevo.name in ' '.join(x.avisos)
               for x in catalogo)


@pytest.mark.parametrize('formato', ['antiguo', 'nuevo'])
def test_clientes_importantes_en_los_dos_formatos(tmp_path, formato):
    """004:RF-34 — hoja resumen, cabecera en otra fila y columnas por nombre."""
    hojas = FORMATO_ANTIGUO if formato == 'antiguo' else FORMATO_NUEVO
    clientes, _avisos = dm.leer_clientes(_libro(tmp_path / 'ci.xlsx', hojas))
    primero = clientes[0]
    if formato == 'antiguo':
        assert (primero.codigo, primero.ea, primero.eri, primero.pot) == ('11', 1000.5, 200.0, 350.0)
    else:
        assert (primero.codigo, primero.ea, primero.eri, primero.pot) == ('9011', 1500.0, 250.0, 360.0)


def test_cliente_repetido_se_avisa(tmp_path):
    """004:RF-34 — un Nis repetido en la hoja resumen se usa una vez y se avisa."""
    clientes, avisos = dm.leer_clientes(_libro(tmp_path / 'ci.xlsx', FORMATO_ANTIGUO))
    assert [c.codigo for c in clientes].count('11') == 1
    assert any('repetido' in a for a in avisos)


def test_cruce_por_codigo_actual_y_si_no_por_el_anterior(tmp_path):
    """004:RF-35 / RF-36 — cruza por «Suministro Act» o «Suministro» y dice por cuál."""
    sums, _ = dm.leer_suministros(_suministros(tmp_path))
    clientes, _ = dm.leer_clientes(_libro(tmp_path / 'ci.xlsx', FORMATO_ANTIGUO))
    cruzados, aparte = dm.cruzar(clientes, sums)
    por = {c.codigo: c for c in cruzados}
    assert (por['11'].cruzado_por, por['11'].sed, por['11'].radial) == ('anterior', 'E100', 'A101')
    assert (por['9012'].cruzado_por, por['9012'].sed) == ('actual', 'E200')
    assert por['11'].ea == 1000.5 and por['11'].pot == 350.0
    nuevos, _ = dm.leer_clientes(_libro(tmp_path / 'cn.xlsx', FORMATO_NUEVO))
    cruzados, _ = dm.cruzar(nuevos, sums)
    assert {c.codigo: c.cruzado_por for c in cruzados} == {'9011': 'actual', '14': 'anterior'}


def test_clientes_sin_filtrar_por_alimentador(tmp_path):
    """004:RF-36 — se cruzan todos los clientes del libro, de cualquier radial."""
    sums, _ = dm.leer_suministros(_suministros(tmp_path))
    clientes, _ = dm.leer_clientes(_libro(tmp_path / 'ci.xlsx', FORMATO_ANTIGUO))
    cruzados, _ = dm.cruzar(clientes, sums)
    assert {c.radial for c in cruzados} == {'A101', 'A102'}


def test_no_cruzados_con_motivo(tmp_path):
    """004:RF-37 — sin suministro, o con suministro sin SED: aparte y con el motivo."""
    sums, _ = dm.leer_suministros(_suministros(tmp_path))
    clientes, _ = dm.leer_clientes(_libro(tmp_path / 'ci.xlsx', FORMATO_ANTIGUO))
    _cruzados, aparte = dm.cruzar(clientes, sums)
    motivos = {c.codigo: c.motivo for c in aparte}
    assert 'no está en el libro de suministros' in motivos['99999']
    assert 'sin SED' in motivos['13'] or 'no tiene SED' in motivos['13']


def test_codigos_numero_o_texto_son_el_mismo():
    """004:RF-35 — ``1234.0``, ``'1234'`` y ``'001234'`` cruzan; los alfanuméricos sin separadores."""
    assert dm.clave_codigo(1234.0) == dm.clave_codigo('1234') == dm.clave_codigo(' 001234')
    assert dm.clave_codigo('M-AB 12') == dm.clave_codigo('m_ab12')


def test_excel_de_salida(tmp_path):
    """004:RF-38 — un libro con la cabecera, los clientes cruzados y los no cruzados."""
    destino = dm.escribir_excel(
        tmp_path / 'salida.xlsx',
        cabecera=[{'alimentador': 'A1', 'medidor': 'M1', 'kw': 5.0, 'hojas': ['M1'], 'fp_calculado': True}],
        clientes=[{'codigo': '11', 'sed': 'E1', 'ea': 3.0}],
        no_cruzados=[{'codigo': '99', 'motivo': 'no está'}],
    )
    wb = openpyxl.load_workbook(destino)
    assert wb.sheetnames == ['Cabecera', 'Clientes', 'No cruzados']
    assert wb['Cabecera']['F2'].value == 5.0 and wb['Cabecera']['K2'].value == 'sí'
    assert wb['Clientes']['E2'].value == 'E1'
    assert wb['No cruzados']['J2'].value == 'no está'


# =========================================================================== datos reales
REAL = os.environ.get('IGEA_DEMANDA_DIR', '').strip()
real = pytest.mark.skipif(not REAL or not Path(REAL).is_dir(),
                          reason='IGEA_DEMANDA_DIR no apunta a la carpeta de la distribuidora')


def _sub(prefijo: str) -> Path:
    return next(p for p in Path(REAL).iterdir() if p.is_dir() and p.name.startswith(prefijo))


@real
def test_real_casi_todos_los_medidores_tienen_su_maxima():
    """004:RF-24 a RF-28 — con los libros reales, los medidores del libro dan su máxima."""
    meds = dm.leer_medidores(next(_sub('1.').iterdir()))
    alimentadores = list(dict.fromkeys(m.alimentador for m in meds))
    pares = [(a, m) for a in alimentadores for m in dm.medidores_de(meds, a)]
    res = dm.maximas([_sub('2.')], pares)
    ok = [r for r in res if r.error is None]
    assert len(ok) >= 0.9 * len(res), f'{len(ok)} de {len(res)} con máxima'
    for r in ok:
        assert r.fecha and r.kw is not None
        assert r.fp is None or -1 <= r.fp <= 1


@real
def test_real_los_dos_formatos_de_clientes_cruzan():
    """004:RF-34 a RF-37 — cada libro de clientes cruza casi entero con el de suministros."""
    sums, _ = dm.leer_suministros(next(_sub('3.').iterdir()))
    for libro in sorted(_sub('4.').iterdir()):
        clientes, _ = dm.leer_clientes(libro)
        cruzados, aparte = dm.cruzar(clientes, sums)
        assert len(cruzados) + len(aparte) == len(clientes)
        assert len(cruzados) >= 0.5 * len(clientes), libro.name
        assert {c.cruzado_por for c in cruzados} <= {'actual', 'anterior'}


# =========================================================================== central térmica
def _central(rng, n: int = 400, *, signo_llegada: int = 1, signo_salida: int = 1,
             raros: int = 0, parada_en: int | None = None, desfase: int = 0):
    """Cuatro curvas ``(fecha, kW, kVAR)`` de un alimentador con una central en serie en su
    troncal, como NA205: aguas arriba entre la SET y la central, aguas abajo tras ella.

    Flujos que salen de la barra de la central, positivos: generación = salida + llegada.
    El medidor exporta la llegada o la salida con ``signo_*``; ``raros`` registros llevan
    una transferencia de carga aguas arriba (un salto que no es demanda); con
    ``parada_en`` la central está parada (consumo de auxiliares) en ese registro.
    """
    cab, gen, lle, sal, esperado = [], [], [], [], {}
    raro = set(rng.sample(range(n), raros)) if raros else set()
    mejor = None
    for i in range(n):
        t = INICIO + timedelta(minutes=15 * i)
        arriba = round(rng.uniform(600, 1100), 1) + (6000.0 if i in raro else 0.0)
        abajo = round(rng.uniform(5000, 9500), 1)
        # Se sortea siempre: saltarse el sorteo con la central parada cambiaba el resto de
        # la serie y la máxima pasaba a otro registro (fallaba con 86 de 300 semillas).
        g = round(rng.uniform(0, 9600), 1)
        if i == parada_en:
            g = -110.0
        qa, qb, qg = round(arriba * 0.3, 1), round(abajo * 0.2, 1), round(-0.06 * g, 1)
        llegada, q_lle = g - abajo, qg - qb
        cab.append((t, arriba - llegada, qa - q_lle))
        gen.append((t, g, qg))
        lle.append((t + timedelta(minutes=15 * desfase), signo_llegada * llegada,
                    signo_llegada * q_lle))
        sal.append((t, signo_salida * abajo, signo_salida * qb))
        if i not in raro and (mejor is None or arriba + abajo > mejor[0]):
            mejor = (arriba + abajo, t, arriba, abajo, g)
    esperado = {'fecha': mejor[1], 'demanda': mejor[0], 'arriba': mejor[2],
                'abajo': mejor[3], 'generacion': mejor[4]}
    return cab, gen, lle, sal, esperado


def test_central_deduce_los_signos_por_el_balance():
    """021:RF-28, RF-29 — sea cual sea el signo con que el medidor exporta la llegada y
    la salida, el balance de la barra (generación = salida + llegada) los delata."""
    for sl, ss in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        rng = random.Random(SEMILLA)
        cab, gen, lle, sal, esp = _central(rng, signo_llegada=sl, signo_salida=ss)
        r = dm.demanda_con_central(cab, gen, lle, sal)
        assert r.error is None, r
        assert (r.signo_llegada, r.signo_salida) == (sl, ss)
        assert r.desbalance_mediana_kw == pytest.approx(0.0, abs=1e-6)


def test_central_sin_balance_no_calibra():
    """021:RF-30 — si ninguna combinación cuadra el balance, se dice su mediana y no se usa."""
    rng = random.Random(SEMILLA)
    cab, gen, lle, sal, _ = _central(rng)
    lle = [(t, rng.uniform(-9000, 9000), q) for t, _kw, q in lle]
    r = dm.demanda_con_central(cab, gen, lle, sal)
    assert r.error and 'balance' in r.error and 'mediana' in r.error
    assert r.desbalance_mediana_kw > 0.05 * r.generacion_max_kw


def test_central_zonas_y_maxima_de_demanda():
    """021:RF-31, RF-33, RF-34 — aguas arriba = cabecera + llegada, aguas abajo = salida;
    el objetivo es el registro de mayor demanda, con cada zona, la generación, la
    cabecera y la máxima de cabecera de antes."""
    rng = random.Random(SEMILLA)
    cab, gen, lle, sal, esp = _central(rng, signo_llegada=-1)
    r = dm.demanda_con_central(cab, gen, lle, sal)
    assert r.error is None, r
    assert r.fecha == esp['fecha'].isoformat(sep=' ')
    assert r.demanda_kw == pytest.approx(esp['demanda'])
    assert (r.arriba_kw, r.abajo_kw) == (pytest.approx(esp['arriba']), pytest.approx(esp['abajo']))
    assert r.generacion_kw == pytest.approx(esp['generacion'])
    fila = next(p for p in cab if p[0] == esp['fecha'])
    assert r.cabecera_kw == pytest.approx(fila[1])
    pico = max(cab, key=lambda p: p[1])
    assert r.maxima_cabecera == {'fecha': pico[0].isoformat(sep=' '), 'kw': pico[1]}
    assert r.arriba_kvar is not None and r.abajo_kvar is not None and r.generacion_kvar is not None
    d = r.to_dict()
    assert d['demanda_kw'] == r.demanda_kw and d['signo_llegada'] == -1


def test_central_descarta_los_registros_raros_de_aguas_arriba():
    """021:RF-32 — una transferencia de carga aguas arriba (un salto de 6 MW) no es la
    máxima: se descarta por estar a más de 3 rangos intercuartílicos y se cuenta."""
    rng = random.Random(SEMILLA)
    cab, gen, lle, sal, esp = _central(rng, raros=5)
    r = dm.demanda_con_central(cab, gen, lle, sal)
    assert r.descartados == 5
    assert r.fecha == esp['fecha'].isoformat(sep=' ')


def test_central_parada_en_la_maxima():
    """021 (casos límite) — con la central parada en el registro objetivo se usa lo medido
    (sus auxiliares), sin dejar de calibrar por zonas."""
    rng = random.Random(SEMILLA)
    cab, gen, lle, sal, _ = _central(rng, n=50)
    # El registro de mayor demanda, con la central parada.
    i = max(range(50), key=lambda k: (cab[k][1] + (lle[k][1])) + sal[k][1])
    rng = random.Random(SEMILLA)
    cab, gen, lle, sal, esp = _central(rng, n=50, parada_en=i)
    r = dm.demanda_con_central(cab, gen, lle, sal)
    assert r.error is None and r.fecha == esp['fecha'].isoformat(sep=' ')
    assert r.generacion_kw == -110.0


def test_central_solo_con_los_registros_comunes():
    """021 (casos límite) — fechas que no casan entre los cuatro medidores no se usan."""
    rng = random.Random(SEMILLA)
    cab, gen, lle, sal, _ = _central(rng, n=100, desfase=10)
    r = dm.demanda_con_central(cab, gen, lle, sal)
    assert r.registros_comunes == 90
    assert r.registros_cabecera == 100


@real
def test_real_na205_con_su_central():
    """021:RF-28 a RF-34 — NA205 con la central de Nasca: CT_BH4 NA (generación), CTNA_BH2
    (llegada desde la SET) y CTNA_BH1 (salida a la carga). La máxima de demanda es la del
    2026-08-20 16:45, con la central generando, no la de cabecera con ella parada."""
    cab = dm.Cabecera([_sub('2.')])
    curvas = {m: cab.maxima(m).curva for m in ('NA205', 'CT_BH4 NA', 'CTNA_BH2', 'CTNA_BH1')}
    r = dm.demanda_con_central(curvas['NA205'], curvas['CT_BH4 NA'], curvas['CTNA_BH2'],
                               curvas['CTNA_BH1'])
    assert r.error is None, r
    assert (r.signo_llegada, r.signo_salida) == (1, 1)
    assert r.fecha == '2026-08-20 16:45:00'
    assert r.generacion_kw > 9000 and r.descartados > 0
    assert r.maxima_cabecera['fecha'].startswith('2026-08-21')
