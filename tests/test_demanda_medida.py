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


# =========================================================================== clientes
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
