"""Spec 051: medición de cabecera en libro ancho (una columna por alimentador) y máximas mensuales.

Los libros se arman aquí con la forma de los de Electro Oriente (perfiles del PIDE 2026 y la
tabla de máximas de Iquitos), con números sorteados; los reales se leen por la herramienta.
"""
from __future__ import annotations

import os
import random
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from openpyxl import Workbook

from convertersmartgrid import cabecera_ancha as ca
from convertersmartgrid import demanda_medida as dm

SEMILLA = int(os.environ.get('CSG_SCALE_SEED', random.randrange(1 << 30)))
RAIZ = Path(__file__).resolve().parents[1]


def _perfil(ruta: Path, rng: random.Random, codigos: list[str], dias: int = 2) -> dict:
    """Un perfil como «01-PERFIL CARGA ENE 2024»: hojas de activa y reactiva, fecha y hora en dos
    columnas (en la reactiva, con la cabecera al revés), el último código repetido al final y
    «CAPACITIVA» sobre la reactiva del primero."""
    wb = Workbook()
    wb.remove(wb.active)
    esperado: dict = {c: {} for c in codigos}
    for hoja, k in (('SIS_ACTIVA', 0), ('SIS_REACTIVA', 1)):
        ws = wb.create_sheet(hoja)
        ws.append(['POTENCIA ' + ('REACTIVA' if k else 'ACTIVA')]
                  + [None] * (len(codigos) + 1))
        ws.append(['ELECTRO X', None] + (['CAPACITIVA'] if k else [None]) + [None] * len(codigos))
        cab = ['HORA', 'FECHA'] if k else ['FECHA', 'HORA']
        ws.append(cab + codigos + [codigos[-1]])
        inicio = datetime(2024, 1, 1)
        for n in range(1, dias * 96 + 1):
            t = inicio + timedelta(minutes=15 * n)
            dia = (t - timedelta(minutes=1)).date()             # «24:00» es del día anterior
            hora = '24:00:00' if t.hour == 0 and t.minute == 0 else t.strftime('%H:%M:%S')
            valores = [round(rng.uniform(10, 900), 3) for _ in codigos]
            ws.append([f'{dia:%Y-%m-%d} 00:00', hora] + valores + [99999.0])
            for c, v in zip(codigos, valores):
                signo = -1.0 if (k and c == codigos[0]) else 1.0
                esperado[c].setdefault(t, [None, None])[k] = v * signo
    wb.save(ruta)
    return esperado


def test_lee_el_libro_ancho_por_codigo(tmp_path):
    """051:RF-1, 051:RF-2, 051:RF-3, 051:RF-4, 051:RF-5 — cada código pedido, su serie por
    instante; magnitud por la hoja; fecha y hora en dos columnas en cualquier orden y «24:00»
    al día siguiente; «CAPACITIVA» da reactiva negativa; el código repetido toma la primera."""
    rng = random.Random(SEMILLA)
    codigos = [f'AB{rng.randint(100, 999)}{i}' for i in range(rng.randint(2, 5))]
    esperado = _perfil(tmp_path / 'perfil.xlsx', rng, codigos)
    pedidos = rng.sample(codigos, rng.randint(1, len(codigos)))
    lectura = ca.leer_ancho([tmp_path], pedidos + ['NOESTA1'])
    for c in pedidos:
        assert lectura.series[c] == pytest.approx(esperado[c]), SEMILLA
    assert lectura.faltan(pedidos + ['NOESTA1']) == ['NOESTA1']
    if codigos[0] in pedidos:
        assert any('capacitiva' in a and codigos[0] in a for a in lectura.avisos)
    if codigos[-1] in pedidos:
        assert any('2 veces' in a for a in lectura.avisos)
    assert ca.instante('2024-03-31 00:00', '24:00:00') == datetime(2024, 4, 1)
    assert ca.instante('00:15:00', '2024-03-31 00:00') == datetime(2024, 3, 31, 0, 15)


def test_hoja_sin_magnitud_no_se_lee(tmp_path):
    """051:RF-2 — una hoja con códigos y fecha pero sin decir activa o reactiva se anota y no
    se lee."""
    wb = Workbook()
    ws = wb.active
    ws.title = 'DATOS'
    ws.append(['FECHA', 'HORA', 'AB1'])
    ws.append(['2024-01-01 00:00', '00:15:00', 5.0])
    wb.save(tmp_path / 'x.xlsx')
    lectura = ca.leer_ancho([tmp_path / 'x.xlsx'], ['AB1'])
    assert not lectura.series and '051:RF-2' in lectura.avisos[0]


def _maximas(ruta: Path, rng: random.Random, salidas: list[str]) -> dict:
    """Como «MAX DEMANDAS POR ALIMENTADORES IQUITOS»: una hoja por año con meses en columnas y,
    debajo, otra tabla que repite las salidas con sus capacidades."""
    wb = Workbook()
    wb.remove(wb.active)
    esperado: dict = {}
    for anio in (2021, 2022):
        ws = wb.create_sheet(str(anio))
        ws.append([anio, anio, 'MAXIMAS DEMANDAS POR ALIMENTADOR (MW)'])
        ws.append([])
        ws.append(['SALIDA', 'SECCION', 'CAPACIDAD', 'ENE', 'FEB', 'MARZ', 'ABRI', 'MAYO', 'JUNIO',
                   'JULIO', 'AGT', 'SET', 'OCT', 'NOV', 'DIC'])
        for s in salidas:
            meses = [round(rng.uniform(1, 9), 2) if rng.random() < 0.7 else None for _ in range(12)]
            ws.append([s, 'Cond. Al', 6] + meses)
            for m, v in enumerate(meses, start=1):
                if v is not None:
                    esperado.setdefault(s, {})[datetime(anio, m, 1)] = [v * 1000, None]
        for s in salidas:
            ws.append([s, 'Cond. Al', 388, 10, 0.9, 6041.16])
    wb.save(ruta)
    return esperado


def test_maximas_mensuales_en_kw_sin_reactiva(tmp_path):
    """051:RF-9 — la máxima de cada mes como registro del día 1 en kW (la tabla dice MW), sin
    reactiva y anotado; la tabla de capacidades de debajo no pisa los valores."""
    rng = random.Random(SEMILLA)
    salidas = [f'R{i}' for i in range(1, rng.randint(3, 8))]
    esperado = _maximas(tmp_path / 'max.xlsx', rng, salidas)
    pedida = rng.choice(salidas)
    lectura = ca.leer_maximas_mensuales([tmp_path / 'max.xlsx'], [pedida])
    assert lectura.series.get(pedida, {}) == pytest.approx(esperado.get(pedida, {})), SEMILLA
    assert pedida in lectura.mensuales and any('051:RF-9' in a for a in lectura.avisos)


def test_sin_unidad_se_pide(tmp_path):
    """051:RF-9 — si la tabla no dice MW ni kW, se pide la unidad: no se supone."""
    wb = Workbook()
    ws = wb.active
    ws.title = '2022'
    ws.append(['SALIDA', 'ENE', 'FEB', 'MAR'])
    ws.append(['R5', 4.92, 4.8, 4.7])
    wb.save(tmp_path / 'm.xlsx')
    with pytest.raises(dm.DemandaError, match='MW o kW'):
        ca.leer_maximas_mensuales([tmp_path / 'm.xlsx'], ['R5'])
    lectura = ca.leer_maximas_mensuales([tmp_path / 'm.xlsx'], ['R5'], unidad='mw')
    assert lectura.series['R5'][datetime(2022, 1, 1)] == [4920.0, None]


def test_lo_escrito_lo_lee_la_calibracion(tmp_path):
    """051:RF-6, 051:RF-10 — un libro por año con una hoja por código y el de medidores, que el
    lector de la calibración lee sin cambios; el nombre en DIgSILENT y el código de la medición
    pueden ser distintos (R205 se mide como R5)."""
    rng = random.Random(SEMILLA)
    codigos = ['NJ202', 'JA102']
    esperado = _perfil(tmp_path / 'perfil.xlsx', rng, codigos)
    lectura = ca.leer_ancho([tmp_path / 'perfil.xlsx'], codigos)
    salida = tmp_path / 'espacio'
    escritos = ca.escribir(lectura, salida, {'ALIM_A': 'NJ202', 'ALIM_B': 'JA102'})
    assert {p.name for p in escritos} >= {'cabecera_2024.xlsx', 'medidores.xlsx'}
    medidores = dm.leer_medidores(salida / 'medidores.xlsx')
    assert {(m.alimentador, m.medidor) for m in medidores} == {('ALIM_A', 'NJ202'), ('ALIM_B', 'JA102')}
    assert (salida / '2024' / 'cabecera_2024.xlsx').is_file(), 'una subcarpeta por año (025:RF-1)'
    (r,) = dm.maximas([salida / '2024' / 'cabecera_2024.xlsx'], [('ALIM_A', 'NJ202')], periodo='2024')
    assert r.error is None
    mayor = max(v[0] for t, v in esperado['NJ202'].items() if t.year == 2024)
    assert r.kw == pytest.approx(mayor)


def test_no_se_escribe_en_referencia(tmp_path):
    """051:RF-7 — los libros normalizados nunca van a referencia/."""
    with pytest.raises(dm.DemandaError, match='referencia'):
        ca.escribir(ca.Lectura(), tmp_path / 'referencia' / 'x', {})


def test_la_herramienta_responde(tmp_path):
    """051:RF-8 — la herramienta de línea de órdenes, con ``--help`` y con un libro sintético."""
    rng = random.Random(SEMILLA)
    _perfil(tmp_path / 'perfil.xlsx', rng, ['AB100', 'AB200'])
    guion = RAIZ / 'tools' / 'cabecera_ancha.py'
    ayuda = subprocess.run([sys.executable, str(guion), '--help'], capture_output=True, text=True)
    assert ayuda.returncode == 0 and 'spec 051' in ayuda.stdout
    hecho = subprocess.run([sys.executable, str(guion), '--ancho', str(tmp_path / 'perfil.xlsx'),
                            '--alimentador', 'F1=AB100', '--salida', str(tmp_path / 'out')],
                           capture_output=True, text=True)
    assert hecho.returncode == 0, hecho.stdout + hecho.stderr
    assert (tmp_path / 'out' / 'medidores.xlsx').is_file()


def test_fp_del_usuario_para_una_medicion_sin_reactiva(tmp_path):
    """051:RF-11 — R5 solo trae máximas en MW: con el FP que da el usuario (0,98) el libro lleva
    la columna FP y la calibración saca de él la Q, kW·tan(acos 0,98); un FP fuera de (0, 1] se
    rechaza."""
    import math

    from convertersmartgrid.ajuste_cabecera import objetivo_de

    rng = random.Random(SEMILLA)
    _maximas(tmp_path / 'max.xlsx', rng, ['R5'])
    lectura = ca.leer_maximas_mensuales([tmp_path / 'max.xlsx'], ['R5'])
    salida = tmp_path / 'espacio'
    ca.escribir(lectura, salida, {'L14243': 'R5'}, {'R5': 0.98})
    anio, kw = max(((t.year, v[0]) for t, v in lectura.series['R5'].items()), key=lambda x: x[1])
    (r,) = dm.maximas([salida / str(anio) / f'cabecera_{anio}.xlsx'], [('L14243', 'R5')], periodo=str(anio))
    assert r.error is None and r.kw == pytest.approx(kw), SEMILLA
    objetivo = objetivo_de(r.to_dict())
    assert objetivo.kvar == pytest.approx(kw * math.tan(math.acos(0.98)), rel=1e-6)
    with pytest.raises(dm.DemandaError, match='entre 0 y 1'):
        ca.escribir(lectura, tmp_path / 'otro', {'L14243': 'R5'}, {'R5': 1.2})
