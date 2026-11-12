"""Spec 089: el pronóstico de demanda en un módulo, desde los libros que haya hasta el backtest por método."""
from __future__ import annotations

import math
import os
import random
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from openpyxl import Workbook

from convertersmartgrid import pronostico_demanda as pd_
from convertersmartgrid.demanda_medida import Cabecera, curvas_de_clientes
from convertersmartgrid.digital_twin.pronostico import CLASES
from convertersmartgrid.digital_twin.temporal_entrenamiento import cargar_cabeceras

RAIZ = Path(__file__).resolve().parents[1]
PASO = timedelta(minutes=15)
T0 = datetime(2026, 1, 1, 0, 15)
SEMILLA = int(os.environ.get('CSG_SCALE_SEED') or random.SystemRandom().randrange(10**6))


def _forma(t: datetime) -> float:
    """Demanda con día, noche y fin de semana."""
    return (1.0 + .5 * math.sin(2 * math.pi * (t.hour * 60 + t.minute) / 1440)) * (.6 if t.weekday() >= 5 else 1.0)


def _serie(dias: float, base: float = 100.0, inicio: datetime = T0, ruido: int = 0, q: float = .3):
    rng = np.random.default_rng(ruido)
    salida = []
    for i in range(int(dias * 96)):
        t = inicio + PASO * i
        p = base * _forma(t) * (1 + .01 * rng.standard_normal())
        salida.append((t, float(p), float(p * q)))
    return salida


def _libro_cabecera(ruta: Path, hojas: dict[str, list]) -> Path:
    wb = Workbook()
    wb.remove(wb.active)
    for nombre, curva in hojas.items():
        h = wb.create_sheet(nombre)
        h.append(['Local Time', 'kW tot', 'kVAR tot'])
        for t, p, q in curva:
            h.append([t, p, q])
    ruta.parent.mkdir(parents=True, exist_ok=True)
    wb.save(ruta)
    return ruta


def _equivalencia(ruta: Path, filas: list[tuple]) -> Path:
    wb = Workbook()
    h = wb.active
    h.title = 'alimentador_medidor'
    h.append(['codigo alimentador', 'Medidor', 'Nivel Tension', 'SET'])
    for f in filas:
        h.append(list(f))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    wb.save(ruta)
    return ruta


def _libro_clientes(ruta: Path, clientes: dict[str, list]) -> Path:
    """Disposición moderna, con maestro."""
    wb = Workbook()
    m = wb.active
    m.title = 'maestro_lib'
    m.append(['numero_suministro', 'nombre_hoja_exportacion'])
    r = wb.create_sheet('resumen')
    r.append(['Nis', 'EA', 'ERI', 'POT'])
    for codigo, curva in clientes.items():
        m.append([codigo, f'h{codigo}'])
        r.append([codigo, 1.0, 1.0, max(p for _t, p, _q in curva)])
        h = wb.create_sheet(f'h{codigo}')
        h.append(['SUMINISTRO', 'FECHA', 'HORA', 'EA', 'ERI', 'POT'])
        for t, p, q in curva:
            h.append([codigo, t.strftime('%d/%m/%Y'), t.strftime('%H:%M'), p / 4, q / 4, p])
    ruta.parent.mkdir(parents=True, exist_ok=True)
    wb.save(ruta)
    return ruta


def _libro_dia_hora(ruta: Path, clientes: dict[str, int], *, hora_final: str = '24:00') -> Path:
    """Disposición antigua: sin maestro, con el código en la cabecera de cada hoja y «día, hora»."""
    wb = Workbook()
    r = wb.active
    r.title = 'resumen'
    r.append(['Nis', 'EA', 'ERI', 'POT'])
    for codigo, dias in clientes.items():
        r.append([codigo, 1.0, 1.0, 40.0])
        h = wb.create_sheet(f'cliente{codigo}')
        h.append(['', '', '', '', '', codigo])
        h.append(['', '', '', '', '', 'EA', 'ERI', 'ERC', '', 'EA', 'ERI', 'ERC', 'Pot'])
        h.append(['día', 'hora', 'f', 'p', '', 1, 1, 0, '', 1, 1, 0, 1])
        for d in range(1, dias + 1):
            for k in range(1, 97):
                texto = hora_final if k == 96 else f'{k * 15 // 60:02d}:{k * 15 % 60:02d}'
                h.append([d, texto, 1, 1, '', 999.0, 999.0, 0, '', 10.0, 2.0, 0, 40.0])
    ruta.parent.mkdir(parents=True, exist_ok=True)
    wb.save(ruta)
    return ruta


def _suministros(ruta: Path, filas: list[tuple]) -> Path:
    wb = Workbook()
    h = wb.active
    h.append(['Suministro', 'Suministro Act', 'SED', 'Radial'])
    for f in filas:
        h.append(list(f))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    wb.save(ruta)
    return ruta


def _fuentes(tmp_path: Path, *, dias=20, clientes=True) -> pd_.Fuentes:
    _libro_cabecera(tmp_path / 'cab/2026/s.xlsx', {'M1': _serie(dias), 'M2': _serie(dias, 50.0, ruido=1), 'B1': _serie(dias, 500.0)})
    eq = _equivalencia(tmp_path / 'eq.xlsx', [('A1', 'M1', 10.0, 'S1'), ('A2', 'M2', 22.9, 'S1'), ('Barra10KV', 'B1', 10.0, 'S1')])
    if not clientes:
        return pd_.Fuentes(cabecera=tmp_path / 'cab', equivalencia=eq)
    _libro_clientes(tmp_path / 'cli/2026/0126clientes.xlsx', {'111': _serie(dias, 30.0, q=.2)})
    sumi = _suministros(tmp_path / 'sum.xlsx', [('111', '111', 'S9', 'A1')])
    return pd_.Fuentes(cabecera=tmp_path / 'cab', equivalencia=eq, clientes=tmp_path / 'cli', suministros=sumi)


def _objetivo(d, clase, ident, magnitud='kW'):
    return next(o for o in d.objetivos if o.clase == clase and o.ident == ident and o.magnitud == magnitud)


# ------------------------------------------------------------------------- datos vivos
def test_descubre_los_libros_de_la_carpeta_y_el_mes_nuevo_entra_solo(tmp_path):
    """089:RF-1, 089:RF-2, 089:RF-3 — un libro más en la carpeta alarga la serie, sin tocar nada más."""
    rng = random.Random(SEMILLA)
    dias = rng.randint(3, 8)
    f = _fuentes(tmp_path, dias=dias, clientes=False)
    antes = _objetivo(pd_.armar_dataset(f), 'cabecera', 'A1')
    siguiente = T0 + PASO * (dias * 96)
    _libro_cabecera(tmp_path / 'cab/2026/mes_nuevo.xlsx', {'M1': _serie(5, inicio=siguiente)})
    despues = _objetivo(pd_.armar_dataset(f), 'cabecera', 'A1')
    assert max(t for t, _ in despues.curva) == siguiente + PASO * (5 * 96 - 1) > max(t for t, _ in antes.curva)
    assert min(t for t, _ in despues.curva) == T0


def test_dice_los_libros_y_el_ultimo_dato(tmp_path):
    """089:RF-4, 089:RF-5 — el informe dice qué se leyó y hasta cuándo llega cada clase."""
    d = pd_.armar_dataset(_fuentes(tmp_path, dias=4))
    nombres = {x['libro'] for x in d.libros}
    assert {'s.xlsx', '0126clientes.xlsx'} <= nombres
    assert all(x['bytes'] > 0 and x['modificado'] for x in d.libros)
    assert d.ultimo_dato['cabecera'].startswith('2026-01-05')
    assert d.ultimo_dato['cliente'].startswith('2026-01-05')


# ------------------------------------------------------------------------- equivalencia
def test_clases_de_la_equivalencia(tmp_path):
    """089:RF-6, 089:RF-7, 089:RF-8, 089:RF-9 — por el código y la tensión, sin SET de una empresa."""
    eq = _equivalencia(tmp_path / 'e.xlsx', [('A1', 'M1', 10.0, 'X'), ('A2', 'M2', 22.9, 'X'), ('Barra60KV', 'B', 60.0, 'X'),
                                             ('Barra10KV', 'C', 10.0, 'X'), ('L-1', 'L1', 60.0, 'X'), ('Cli', 'K', 220.0, 'CL')])
    puntos, _ = pd_.equivalencias(eq)
    clases = {p.codigo: p.clase for p in puntos}
    assert clases == {'A1': 'alimentador', 'A2': 'alimentador', 'Barra60KV': 'barra', 'Barra10KV': 'barra',
                      'L-1': 'transmision', 'Cli': 'transmision'}
    assert next(p for p in puntos if p.codigo == 'A1').medidores == ('M1',)


@pytest.mark.parametrize('fila,motivo', [(('A1', 'M1', None, 'X'), 'tensión'), (('A1', None, 10.0, 'X'), 'medidor')])
def test_fila_incompleta_se_aparta(tmp_path, fila, motivo):
    """089:RF-10 — una fila sin tensión o sin medidor no se supone: se dice."""
    puntos, apartados = pd_.equivalencias(_equivalencia(tmp_path / 'e.xlsx', [fila]))
    assert not puntos and motivo in apartados[0]['motivo']


def test_objetivos_solo_de_alimentadores(tmp_path):
    """089:RF-11, 089:RF-6 — la barra no es objetivo, y el objetivo lleva el código del alimentador."""
    d = pd_.armar_dataset(_fuentes(tmp_path, dias=4, clientes=False))
    assert {o.ident for o in d.objetivos if o.clase == 'cabecera'} == {'A1', 'A2'}


def test_varios_medidores_se_suman_en_los_instantes_comunes(tmp_path):
    """089:RF-12 — dos medidores de un alimentador son una sola serie."""
    a, b = _serie(3, 10.0), _serie(2, 20.0, ruido=1)
    _libro_cabecera(tmp_path / 'cab/s.xlsx', {'M1': a, 'M2': b})
    eq = _equivalencia(tmp_path / 'e.xlsx', [('A1', 'M1 Y M2', 10.0, 'X')])
    o = _objetivo(pd_.armar_dataset(pd_.Fuentes(cabecera=tmp_path / 'cab', equivalencia=eq)), 'cabecera', 'A1')
    assert len(o.curva) == len(b)
    assert o.curva[0][1] == pytest.approx(a[0][1] + b[0][1])


def _libro_central(ruta: Path) -> Path:
    n = 24
    cab = [(T0 + PASO * i, 300.0 if i % 2 else -100.0, 1.0) for i in range(n)]
    lle = [(T0 + PASO * i, 400.0 if i % 2 else 200.0, 1.0) for i in range(n)]
    sal = [(t, 400.0 - p, 1.0) for t, p, _q in lle]
    gen = [(t, 400.0, 1.0) for t, _p, _q in lle]
    return _libro_cabecera(ruta, {'CAB': cab, 'GEN': gen, 'LLE': lle, 'SAL': sal})


def test_con_central_se_juzga_la_demanda(tmp_path):
    """089:RF-13, 089:RF-21 — el medidor va en ambos sentidos, pero la demanda con su central no."""
    libro = _libro_central(tmp_path / 'c.xlsx')
    objetivos, apartados = pd_.objetivos_de_cabecera(
        [libro], [('A1', 'CAB')], centrales={'A1': {'generacion': 'GEN', 'llegada': 'LLE', 'salida': 'SAL'}})
    assert not apartados
    assert objetivos[0].fuente['central_descontada'] is True
    assert all(v > 0 for _t, v in objetivos[0].curva)


# ------------------------------------------------------------------------- clientes
def test_lee_la_disposicion_dia_hora_con_el_mes_del_libro(tmp_path):
    """089:RF-14 — kW = EA × 4 del último grupo, con el mes que dice el libro."""
    ruta = _libro_dia_hora(tmp_path / '0226.xlsx', {'181': 2})
    curvas, _ = curvas_de_clientes(ruta, mes='2026-02')
    t, kw, kvar = curvas['181'][0]
    assert t == datetime(2026, 2, 1, 0, 15) and kw == 40.0 and kvar == 8.0
    assert len(curvas['181']) == 192


def test_sin_el_mes_no_se_supone_la_disposicion_antigua(tmp_path):
    """089:RF-14 — sin saber el mes, «día 3» no es una fecha: el libro sigue sin curvas."""
    assert curvas_de_clientes(_libro_dia_hora(tmp_path / 'x.xlsx', {'181': 1}))[0] == {}


@pytest.mark.parametrize('final', ['24:00', '00:00'])
def test_el_ultimo_registro_del_dia_es_del_dia_siguiente(tmp_path, final):
    """089:RF-15 — «24:00» y el «00:00» final del día son la medianoche siguiente, sin retroceder."""
    curvas, _ = curvas_de_clientes(_libro_dia_hora(tmp_path / 'x.xlsx', {'181': 2}, hora_final=final), mes='2026-02')
    ts = [t for t, _p, _q in curvas['181']]
    assert ts[95] == datetime(2026, 2, 2, 0, 0)
    assert all(b - a == PASO for a, b in zip(ts, ts[1:]))


def test_el_ultimo_registro_del_mes_cae_en_el_mes_siguiente(tmp_path):
    """089:RF-15 — el libro real acaba con «día 1, 00:00» tras el último día: no es el principio de ese mes.

    Sin esto, 255 de los clientes reales se apartaban por un registro contradictorio que no existía.
    """
    wb = Workbook()
    r = wb.active
    r.title = 'resumen'
    r.append(['Nis', 'EA', 'ERI', 'POT'])
    r.append(['181', 1.0, 1.0, 40.0])
    h = wb.create_sheet('c')
    h.append(['', '', '', '', '', '181'])
    h.append(['', '', '', '', '', 'EA', 'ERI', 'ERC', '', 'EA', 'ERI', 'ERC', 'Pot'])
    h.append(['día', 'hora', 'f', 'p', '', 1, 1, 0, '', 1, 1, 0, 1])
    for d, texto in ((1, '00:15'), (1, '23:45'), (2, '00:00'), (2, '00:15'), (31, '23:45'), (1, '00:00')):
        h.append([d, texto, 1, 1, '', 9.0, 9.0, 0, '', float(d), 2.0, 0, 40.0])
    wb.save(tmp_path / 'x.xlsx')
    ts = [t for t, _p, _q in curvas_de_clientes(tmp_path / 'x.xlsx', mes='2026-01')[0]['181']]
    assert ts[2] == datetime(2026, 1, 2, 0, 0) and ts[-1] == datetime(2026, 2, 1, 0, 0)
    assert len(set(ts)) == len(ts)


def test_canal_sin_hoja_no_pierde_ni_duplica_el_alimentador(tmp_path):
    """089:RF-12 — «M_V18 Y M_V19» con una sola hoja es un medidor: ni se aparta ni se suma dos veces."""
    curva = _serie(3)
    _libro_cabecera(tmp_path / 'cab/s.xlsx', {'IN1_V18': curva})
    eq = _equivalencia(tmp_path / 'e.xlsx', [('A1', 'IN1_V18 Y IN1_V19', 10.0, 'X')])
    d = pd_.armar_dataset(pd_.Fuentes(cabecera=tmp_path / 'cab', equivalencia=eq))
    assert not d.apartados
    o = _objetivo(d, 'cabecera', 'A1')
    assert o.curva[0][1] == pytest.approx(curva[0][1])


def test_medidor_que_falta_de_verdad_aparta_el_alimentador(tmp_path):
    """089:RF-12 — sin uno de sus dos medidores, la suma se quedaría corta: se dice."""
    _libro_cabecera(tmp_path / 'cab/s.xlsx', {'M1': _serie(3)})
    eq = _equivalencia(tmp_path / 'e.xlsx', [('A1', 'M1 Y M2', 10.0, 'X')])
    d = pd_.armar_dataset(pd_.Fuentes(cabecera=tmp_path / 'cab', equivalencia=eq))
    assert not d.objetivos and 'M2' in d.apartados[0]['motivo']


def test_veinticuatro_horas_en_la_disposicion_moderna(tmp_path):
    """089:RF-15 — también en la moderna: esos registros se perdían contados como sin fecha."""
    wb = Workbook()
    m = wb.active
    m.title = 'maestro_lib'
    m.append(['numero_suministro', 'nombre_hoja_exportacion'])
    m.append(['7', 'h7'])
    h = wb.create_sheet('h7')
    h.append(['FECHA', 'HORA', 'EA', 'ERI', 'POT'])
    h.append(['31/01/2026', '24:00', 1.0, 1.0, 4.0])
    wb.save(tmp_path / 'm.xlsx')
    assert curvas_de_clientes(tmp_path / 'm.xlsx')[0]['7'][0][0] == datetime(2026, 2, 1, 0, 0)


def test_codigos_renumerados_son_un_solo_cliente(tmp_path):
    """089:RF-16 — enero con el código anterior, febrero con el actual: una sola serie con el actual."""
    _libro_cabecera(tmp_path / 'cab/s.xlsx', {'M1': _serie(40)})
    _libro_clientes(tmp_path / 'cli/2026/0126c.xlsx', {'900': _serie(31, 30.0)})
    _libro_clientes(tmp_path / 'cli/2026/0226c.xlsx', {'100': _serie(5, 30.0, inicio=T0 + timedelta(days=31))})
    f = pd_.Fuentes(cabecera=tmp_path / 'cab', equivalencia=_equivalencia(tmp_path / 'e.xlsx', [('A1', 'M1', 10.0, 'X')]),
                    clientes=tmp_path / 'cli', suministros=_suministros(tmp_path / 's.xlsx', [('900', '100', 'S', 'A1')]))
    d = pd_.armar_dataset(f)
    assert {o.ident for o in d.objetivos if o.clase == 'cliente'} == {'100'}
    assert len(_objetivo(d, 'cliente', '100').curva) == 36 * 96


def test_cliente_con_su_alimentador(tmp_path):
    """089:RF-17 — el libro de suministros dice a qué alimentador pertenece."""
    d = pd_.armar_dataset(_fuentes(tmp_path, dias=3))
    assert _objetivo(d, 'cliente', '111').fuente['alimentador'] == 'A1'


# ------------------------------------------------------------------------- limpieza
def test_sentido_de_serie():
    """089:RF-18, 089:RF-20 — los dos umbrales, sobre los registros distintos de cero."""
    assert pd_.sentido_de_serie(np.array([-1.0] * 95 + [1.0] * 5)) == 'invertido'
    assert pd_.sentido_de_serie(np.array([-1.0] * 94 + [1.0] * 6)) == 'ambos'
    assert pd_.sentido_de_serie(np.array([-1.0] * 6 + [1.0] * 94)) == 'ambos'
    assert pd_.sentido_de_serie(np.array([-1.0] * 5 + [1.0] * 95)) == 'normal'
    assert pd_.sentido_de_serie(np.array([-1.0] * 19 + [1.0] + [0.0] * 1000)) == 'invertido'
    assert pd_.sentido_de_serie(np.zeros(4)) == 'normal'


def test_serie_invertida_entra_en_positivo_y_se_anota(tmp_path):
    """089:RF-18, 089:RF-19 — P y Q se invierten en el objetivo, y la procedencia lo dice."""
    libro = _libro_cabecera(tmp_path / 'c.xlsx', {'M1': [(t, -p, -q) for t, p, q in _serie(1)]})
    objetivos, apartados = pd_.objetivos_de_cabecera([libro], [('A1', 'M1')])
    assert not apartados
    p = next(o for o in objetivos if o.magnitud == 'kW')
    q = next(o for o in objetivos if o.magnitud == 'kVAR')
    assert all(v > 0 for _t, v in p.curva) and all(v > 0 for _t, v in q.curva)
    assert p.fuente['sentido_invertido'] is True


def test_serie_normal_no_se_anota_como_invertida(tmp_path):
    """089:RF-19 — una serie en su sentido no se marca."""
    objetivos, _ = pd_.objetivos_de_cabecera([_libro_cabecera(tmp_path / 'c.xlsx', {'M1': _serie(1)})], [('A1', 'M1')])
    assert objetivos[0].fuente['sentido_invertido'] is False


def test_serie_en_ambos_sentidos_se_aparta_con_motivo(tmp_path):
    """089:RF-20 — generación y demanda no se aprenden como una sola serie."""
    curva = [(t, p if i % 2 else -p, q) for i, (t, p, q) in enumerate(_serie(1))]
    objetivos, apartados = pd_.objetivos_de_cabecera([_libro_cabecera(tmp_path / 'c.xlsx', {'M1': curva})], [('A1', 'M1')])
    assert not objetivos and 'ambos sentidos' in apartados[0]['motivo']


def test_cargar_cabeceras_sigue_la_misma_regla(tmp_path):
    """089:RF-18, 089:RF-20 — el otro camino que prepara cabecera para entrenar invierte y omite igual."""
    t0 = datetime(2026, 3, 6, 18, 0)
    hojas = {'INV': lambda _i: -5.0, 'NOR': lambda _i: 5.0, 'AMB': lambda i: 5.0 if i % 2 else -5.0}
    wb = Workbook()
    wb.remove(wb.active)
    for nombre, kw in hojas.items():
        ws = wb.create_sheet(nombre)
        ws.append(['Local Time', 'kW tot'])
        for i in range(8):
            ws.append([t0 + PASO * i, kw(i)])
    wb.save(tmp_path / 'c.xlsx')
    series, procedencia = cargar_cabeceras(tmp_path / 'c.xlsx', zona_horaria='America/Lima')
    assert set(series) == {'INV', 'NOR'} and series['INV'] == [5.0] * 8
    assert procedencia['hojas_omitidas'] == ['AMB'] and procedencia['invertidas'] == ['INV']


def test_quita_el_medidor_congelado_y_lo_cuenta(tmp_path):
    """089:RF-22, 089:RF-26, 089:RF-27 — 16 registros iguales salen, sin rellenarlos, y 15 no."""
    base = _serie(20)
    for i in range(1000, 1016):
        base[i] = (base[i][0], 77.0, 1.0)
    for i in range(1200, 1215):
        base[i] = (base[i][0], 88.0, 1.0)
    limpia, informe = pd_.limpiar_curva(base, 'cabecera')
    instantes = {t for t, _p, _q in limpia}
    assert base[1000][0] not in instantes and base[1015][0] not in instantes and base[1200][0] in instantes
    assert informe['congelado'] == 16
    assert len(limpia) == len(base) - informe['congelado'] - informe['atipico'] - informe['cero']


def test_quita_los_ceros_de_cabecera_y_conserva_los_de_cliente(tmp_path):
    """089:RF-23 — un corte no es demanda en cabecera; un cliente parado sí consume cero."""
    base = _serie(10)
    base[50] = (base[50][0], 0.0, 0.0)
    assert pd_.limpiar_curva(base, 'cabecera')[1]['cero'] == 1
    limpia, informe = pd_.limpiar_curva(base, 'cliente')
    assert informe['cero'] == 0 and base[50][0] in {t for t, _p, _q in limpia}


def test_quita_el_atipico_aislado_sin_mirar_el_futuro(tmp_path):
    """089:RF-24 — el pico aislado sale; un escalón sostenido es otro nivel y se queda casi entero."""
    base = _serie(20)
    base[1500] = (base[1500][0], 50_000.0, 1.0)
    limpia, informe = pd_.limpiar_curva(base, 'cabecera')
    assert base[1500][0] not in {t for t, _p, _q in limpia} and informe['atipico'] >= 1
    # Es causal: lo que venga después no cambia qué se marcó antes.
    corta, _ = pd_.limpiar_curva(base[:1400], 'cabecera')
    assert {t for t, _p, _q in corta} == {t for t, _p, _q in limpia if t < base[1400][0]}
    escalon = _serie(20)
    escalon[1000:] = [(t, p * 3, q) for t, p, q in escalon[1000:]]
    _, inf = pd_.limpiar_curva(escalon, 'cabecera')
    assert inf['atipico'] < .05 * len(escalon)


def test_serie_no_operativa_se_aparta(tmp_path):
    """089:RF-25 — un alimentador casi todo en cero no se entrena, y se dice que no opera."""
    curva = [(t, 0.0 if i > 96 else p, 0.0) for i, (t, p, _q) in enumerate(_serie(4))]
    _libro_cabecera(tmp_path / 'cab/s.xlsx', {'M1': curva})
    f = pd_.Fuentes(cabecera=tmp_path / 'cab', equivalencia=_equivalencia(tmp_path / 'e.xlsx', [('A1', 'M1', 10.0, 'X')]))
    d = pd_.armar_dataset(f)
    assert not d.objetivos
    assert 'no operativ' in d.apartados[0]['motivo']


def test_los_informes_de_limpieza_llegan_a_la_procedencia(tmp_path):
    """089:RF-27 — cada objetivo dice qué se le quitó."""
    d = pd_.armar_dataset(_fuentes(tmp_path, dias=10))
    assert set(_objetivo(d, 'cabecera', 'A1').fuente['limpieza']) >= {'congelado', 'cero', 'atipico'}


def test_la_calibracion_conserva_su_curva(tmp_path):
    """089:RF-28 — la lectura común no invierte ni limpia: eso ocurre solo en el dataset."""
    curva = [(t, -p, -q) for t, p, q in _serie(2)]
    curva[10] = (curva[10][0], 0.0, 0.0)
    libro = _libro_cabecera(tmp_path / 'c.xlsx', {'M1': curva})
    pd_.objetivos_de_cabecera([libro], [('A1', 'M1')])
    r = Cabecera([libro]).maxima('M1')
    assert len(r.curva) == len(curva) and r.curva[0][1] < 0 and r.curva[10][1] == 0.0


# ------------------------------------------------------------------------- clases
def test_tres_clases_con_kw_y_kvar(tmp_path):
    """089:RF-29 — cabecera, cliente y escaladas, cada una con sus dos magnitudes."""
    d = pd_.armar_dataset(_fuentes(tmp_path, dias=4))
    assert {'cabecera', 'cliente', 'escaladas'} <= set(CLASES)
    for clase, ident in (('cabecera', 'A1'), ('cliente', '111'), ('escaladas', 'A1')):
        assert _objetivo(d, clase, ident, 'kW') and _objetivo(d, clase, ident, 'kVAR')


def test_escaladas_son_la_cabecera_menos_las_fijas(tmp_path):
    """089:RF-30, 089:RF-33 — instante a instante, y su Q avisa de que lleva los bancos."""
    d = pd_.armar_dataset(_fuentes(tmp_path, dias=3))
    cab, cli = dict(_objetivo(d, 'cabecera', 'A1').curva), dict(_objetivo(d, 'cliente', '111').curva)
    esc = _objetivo(d, 'escaladas', 'A1')
    t, v = esc.curva[5]
    assert v == pytest.approx(cab[t] - cli[t])
    assert _objetivo(d, 'escaladas', 'A1', 'kVAR').fuente['incluye_bancos'] is True


def test_alimentador_sin_fijas_tiene_escaladas_iguales_a_su_cabecera(tmp_path):
    """089:RF-30 — sin clientes fijos, todo el alimentador es escaladas."""
    d = pd_.armar_dataset(_fuentes(tmp_path, dias=3))
    assert _objetivo(d, 'escaladas', 'A2').curva == _objetivo(d, 'cabecera', 'A2').curva


def test_resto_negativo_queda_en_cero():
    """089:RF-31 — un alimentador dedicado da un resto con ruido: una escalada no es generación."""
    cab = [(T0, 100.0, 10.0), (T0 + PASO, 100.0, 10.0)]
    cli = [(T0, 120.0, 1.0), (T0 + PASO, 40.0, 1.0)]
    curva = pd_.escaladas_de(cab, [cli])
    assert [p for _t, p, _q in curva] == [0.0, 60.0]


def test_cliente_sin_dato_deja_el_instante_sin_escaladas():
    """089:RF-32 — falta el dato: no se resta cero; 089:RF-81 — antes del primer dato de los libros no hay escaladas."""
    ts = [T0 + PASO * i for i in range(5)]
    cab = [(t, 100.0, 10.0) for t in ts]
    cli = [(ts[1], 10.0, 1.0), (ts[3], 10.0, 1.0)]
    curva = dict((t, p) for t, p, _q in pd_.escaladas_de(cab, [cli]))
    assert curva == {ts[1]: 90.0, ts[3]: 90.0}


def test_dice_el_desfase_sin_corregirlo():
    """089:RF-34 — relojes separados 30 minutos: se avisa, y la curva sigue igual."""
    rng = np.random.default_rng(SEMILLA)
    cambios = np.cumsum(rng.standard_normal(2000))
    cab = [(T0 + PASO * i, 500.0 + float(v), 0.0) for i, v in enumerate(cambios)]
    cli = [(T0 + PASO * (i + 2), 100.0 + float(v), 0.0) for i, v in enumerate(cambios)]
    assert pd_.desfase_de_relojes(cab, cli) == 2
    assert pd_.desfase_de_relojes(cab, cab) == 0


# ------------------------------------------------------------------------- apoyo
def test_apoyo_solo_antes_de_la_base(tmp_path):
    """089:RF-35, 089:RF-37 — el apoyo alarga hacia atrás, y la base manda en lo común."""
    anterior = T0 - timedelta(days=30)
    apoyo = _serie(32, inicio=anterior)
    base = _serie(10)
    curva, info = pd_.apoyar(base, apoyo)
    assert curva[0][0] == anterior and info['usado'] is True
    assert dict((t, p) for t, p, _q in curva)[T0] == base[0][1]
    assert info['inicio_base'] == T0


def test_apoyo_que_no_coincide_se_rechaza():
    """089:RF-36 — otro medidor con el mismo nombre no se mezcla, y se dice."""
    base = _serie(10)
    apoyo = [(t, p * 1.5, q) for t, p, q in _serie(20, inicio=T0 - timedelta(days=10))]
    curva, info = pd_.apoyar(base, apoyo)
    assert curva == base and info['usado'] is False and 'difiere' in info['motivo']


def test_el_dataset_usa_el_apoyo_y_lo_anota(tmp_path):
    """089:RF-35 — con carpeta de apoyo, la serie empieza antes, y el objetivo sabe dónde empieza la base."""
    f = _fuentes(tmp_path, dias=10, clientes=False)
    _libro_cabecera(tmp_path / 'apoyo/2025.xlsx', {'M1': _serie(12, inicio=T0 - timedelta(days=2))})
    d = pd_.armar_dataset(pd_.Fuentes(cabecera=f.cabecera, equivalencia=f.equivalencia, apoyo=tmp_path / 'apoyo'))
    o = _objetivo(d, 'cabecera', 'A1')
    assert min(t for t, _ in o.curva) == T0 - timedelta(days=2)
    assert o.fuente['inicio_base'] == T0.isoformat()


# ------------------------------------------------------------------------- métodos
def _objetivo_simple(dias=120, base=100.0, **kw):
    from convertersmartgrid.digital_twin.pronostico import Objetivo

    curva = [(t, p) for t, p, _q in _serie(dias, base, **kw)]
    return Objetivo('cabecera', 'A1', 'kW', 'kW', curva, {'inicio_base': curva[0][0].isoformat()})


def test_compiten_los_tres_metodos_en_los_mismos_origenes():
    """089:RF-38, 089:RF-40 — con 28 días por defecto, y cada uno con WAPE, RMSE relativo y sesgo."""
    r = pd_.backtest_objetivo(_objetivo_simple())
    assert {'semanal', 'perfil_calendario', 'perfil_anclado'} <= set(r['seleccion'])
    assert r['horizonte_dias'] == 28
    assert set(r['prueba']['semanal']) >= {'wape', 'rmse_relativo', 'sesgo'}


def test_predecir_no_mira_el_futuro():
    """089:RF-39 — cambiar lo posterior al origen no cambia la predicción."""
    o = _objetivo_simple(60)
    t = np.array([x for x, _ in o.curva], dtype='datetime64[ns]')
    y = np.array([v for _, v in o.curva])
    corte = 40 * 96
    futuro = t[corte:corte + 96]
    for metodo in ('semanal', 'perfil_calendario', 'perfil_anclado'):
        a = pd_.predecir(metodo, t[:corte], y[:corte], futuro)
        y2 = y.copy()
        y2[corte:] *= 50
        assert a == pytest.approx(pd_.predecir(metodo, t[:corte], y2[:corte], futuro))
    # Y los huecos del horizonte no entran en el error.
    m = pd_.medir(np.array([1.0, np.nan, 3.0]), np.array([1.0, 100.0, 3.0]))
    assert m['wape'] == 0.0


def test_la_eleccion_y_la_prueba_estan_separadas():
    """089:RF-41, 089:RF-42 — se elige sin el último origen, y su error es el que se informa."""
    r = pd_.backtest_objetivo(_objetivo_simple(), origenes=3)
    assert len(r['origenes_seleccion']) == 2 and r['origen_prueba'] > max(r['origenes_seleccion'])
    assert r['metodo'] == min(r['seleccion'], key=r['seleccion'].get)
    assert r['error_prueba'] == r['prueba'][r['metodo']]


def test_gana_el_nivel_reciente_cuando_la_demanda_cambia_de_nivel():
    """089:RF-38, 089:RF-41 — con un escalón, el perfil anclado a lo reciente debe batir al calendario."""
    from convertersmartgrid.digital_twin.pronostico import Objetivo

    curva = [(t, p * (2.0 if i > 30 * 96 else 1.0)) for i, (t, p, _q) in enumerate(_serie(200))]
    r = pd_.backtest_objetivo(Objetivo('cabecera', 'A1', 'kW', 'kW', curva, {'inicio_base': curva[0][0].isoformat()}))
    assert r['seleccion']['perfil_anclado'] < .5


def test_el_informe_se_puede_escribir_con_una_serie_sin_energia(tmp_path):
    """089:RF-40 — un cliente en cero da un WAPE sin definir: el informe lo deja vacío y sigue siendo JSON."""
    import json

    from convertersmartgrid.digital_twin.pronostico import Objetivo

    curva = [(t, 0.0) for t, _p, _q in _serie(120)]
    d = pd_.Dataset([Objetivo('cliente', 'K', 'kW', 'kW', curva, {})], [], [], {})
    informe = json.loads(json.dumps(pd_.backtest(d), allow_nan=False))
    assert informe['resultados'][0]['status'] == 'HISTORIA_INSUFICIENTE'


def test_historia_insuficiente():
    """089:RF-43 — sin dos orígenes completos no se elige un método: se dice."""
    r = pd_.backtest_objetivo(_objetivo_simple(40))
    assert r['status'] == 'HISTORIA_INSUFICIENTE'


def test_no_evalua_sobre_el_apoyo():
    """089:RF-37 — los orígenes de evaluación caen dentro de la serie base."""
    from convertersmartgrid.digital_twin.pronostico import Objetivo

    curva = [(t, p) for t, p, _q in _serie(150)]
    inicio = curva[60 * 96][0]
    o = Objetivo('cabecera', 'A1', 'kW', 'kW', curva, {'inicio_base': inicio.isoformat()})
    r = pd_.backtest_objetivo(o, origenes=9)
    assert all(datetime.fromisoformat(x) >= inicio for x in r['origenes_seleccion'])


def _exogenas(tmp_path, *, norma='DS 1'):
    c = tmp_path / 'exo'
    c.mkdir(exist_ok=True)
    (c / 'feriados.csv').write_text(f'fecha,no_laborable,norma\n2026-03-04,True,{norma}\n2026-03-05,False,\n', encoding='utf-8')
    filas = ['fecha_hora,temperatura_c']
    for i in range(150 * 96):
        t = T0 + PASO * i
        filas.append(f'{t.isoformat(sep=" ")},{20 + 5 * math.sin(2 * math.pi * t.hour / 24)}')
    (c / 'temp.csv').write_text('\n'.join(filas), encoding='utf-8')
    return c


def test_no_laborable_como_domingo(tmp_path):
    """089:RF-44 — un miércoles feriado se predice con la forma del domingo."""
    exo = pd_.leer_exogenas(_exogenas(tmp_path))
    o = _objetivo_simple(60)
    t = np.array([x for x, _ in o.curva], dtype='datetime64[ns]')
    y = np.array([v for _, v in o.curva])
    corte = int((np.datetime64('2026-03-01') - t[0]) / np.timedelta64(15, 'm'))
    futuro = np.array([np.datetime64('2026-03-04T12:00'), np.datetime64('2026-03-05T12:00')], dtype='datetime64[ns]')
    p = pd_.predecir('semanal', t[:corte], y[:corte], futuro, exo)
    assert p[0] == pytest.approx(.6 * p[1], rel=.05)


def test_no_laborable_sin_norma_se_dice(tmp_path):
    """089:RF-45 — no se descarta, pero queda dicho para revisarlo."""
    assert pd_.leer_exogenas(_exogenas(tmp_path, norma='')).sin_norma == [date(2026, 3, 4)]


def test_temperatura_con_climatologia_anterior_al_origen(tmp_path):
    """089:RF-46, 089:RF-47 — cambiar la temperatura medida futura no cambia la predicción."""
    exo = pd_.leer_exogenas(_exogenas(tmp_path))
    o = _objetivo_simple(90)
    t = np.array([x for x, _ in o.curva], dtype='datetime64[ns]')
    y = np.array([v for _, v in o.curva])
    corte = 60 * 96
    fut = t[corte:corte + 96]
    a = pd_.predecir('anclado_temperatura', t[:corte], y[:corte], fut, exo)
    alterada = pd_.Exogenas(exo.no_laborables, {k: (v + 100 if np.datetime64(k) >= t[corte] else v) for k, v in exo.temperatura.items()}, exo.sin_norma)
    assert a == pytest.approx(pd_.predecir('anclado_temperatura', t[:corte], y[:corte], fut, alterada))


def test_temperatura_solo_si_mejora_y_se_dice(tmp_path):
    """089:RF-48, 089:RF-49 — sobre una serie que no depende de ella, no entra, y queda la comparación."""
    r = pd_.backtest_objetivo(_objetivo_simple(), exogenas=pd_.leer_exogenas(_exogenas(tmp_path)))
    assert r['temperatura']['usada'] is (r['temperatura']['mejora_wape'] >= .01)
    assert ('anclado_temperatura' in r['seleccion']) is r['temperatura']['usada']


def test_emite_cuantiles_y_marca(tmp_path):
    """089:RF-50, 089:RF-51 — cada fila con su contrato, y el intervalo desde el error de elección."""
    filas = pd_.pronosticar(_objetivo_simple(), pd_.backtest_objetivo(_objetivo_simple()), dias=2)
    assert len(filas) == 2 * 96
    f = filas[0]
    assert f['marca'] == 'pronostico' and f['clase'] == 'cabecera' and f['unit'] == 'kW' and f['method']
    assert f['q05'] <= f['q50'] <= f['q95'] and f['target'] == 'cabecera:A1:kW'
    assert f['emission_time'] and f['forecast_time'] and f['horizon_steps'] == 1


def test_sin_datos_de_una_empresa_en_el_modulo():
    """089:RF-52 — ni medidores, ni libros, ni meses, ni años."""
    texto = (RAIZ / 'src/convertersmartgrid/pronostico_demanda.py').read_text(encoding='utf-8')
    codigo = re.sub(r'""".*?"""|#.*', '', texto, flags=re.S)
    assert not re.search(r'CHB2T1|L-?\d{4}|PA\d{3}|AL\d{3}|Pisco|Electro|\b20(2[3-9])\b', codigo)


# ------------------------------------------------------------------------- medición real
def _reales():
    carpeta = os.environ.get('CSG_DEMANDA_DIR')
    if not carpeta:
        pytest.skip('CSG_DEMANDA_DIR no definida')
    return Path(carpeta)


def test_libro_real_dia_hora():
    """089:RF-14 — los libros antiguos de 2026 dan curvas de 15 minutos, con EA × 4 igual a POT."""
    b = _reales()
    ruta = next((b / '4.-clientesimportantes/2026').glob('0126*'), None)
    if ruta is None:
        pytest.skip('sin ese libro en CSG_DEMANDA_DIR')
    curvas, _ = curvas_de_clientes(ruta, mes='2026-01')
    assert len(curvas) > 200
    ts = [t for t, _p, _q in next(iter(curvas.values()))]
    assert sum(b_ - a == PASO for a, b_ in zip(ts, ts[1:])) > .99 * (len(ts) - 1)


def test_el_resumen_pondera_por_energia():
    """089:RF-53 — un alimentador casi dedicado, con resto casi cero, no pesa como uno grande."""
    from convertersmartgrid.digital_twin.pronostico import Objetivo

    grande = _objetivo_simple(120, 1000.0)
    curva = [(t, 1e-3 * (1 + (i % 7))) for i, (t, _v) in enumerate(grande.curva)]
    pequeno = Objetivo('cabecera', 'A2', 'kW', 'kW', curva, {})
    resumen = pd_.backtest(pd_.Dataset([grande, pequeno], [], [], {}))['resumen']['cabecera|kW']
    individual = pd_.backtest_objetivo(grande)['error_prueba']['wape']
    assert resumen['wape_ponderado']['elegido'] == pytest.approx(individual, rel=.01)


def test_el_sentido_se_juzga_por_lo_reciente(tmp_path):
    """089:RF-54 — un alimentador que iba al revés hasta hace meses es de demanda; lo antiguo contrario sale y se cuenta."""
    curva = [(t, -p if i < 100 * 96 else p, q) for i, (t, p, q) in enumerate(_serie(200))]
    objetivos, apartados = pd_.objetivos_de_cabecera([_libro_cabecera(tmp_path / 'c.xlsx', {'M1': curva})], [('A1', 'M1')])
    assert not apartados
    p = next(o for o in objetivos if o.magnitud == 'kW')
    assert all(v > 0 for _t, v in p.curva) and len(p.curva) == 100 * 96
    assert p.fuente['registros_contrarios'] == 100 * 96


def test_flujo_doble_reciente_sigue_apartado(tmp_path):
    """089:RF-20, 089:RF-54 — una batería que hoy va en los dos sentidos no es demanda."""
    curva = [(t, p if i % 2 else -p, q) for i, (t, p, q) in enumerate(_serie(90))]
    objetivos, apartados = pd_.objetivos_de_cabecera([_libro_cabecera(tmp_path / 'c.xlsx', {'M1': curva})], [('A1', 'M1')])
    assert not objetivos and 'ambos sentidos' in apartados[0]['motivo']


def test_apoyo_de_clientes_solo_antes_de_la_base(tmp_path):
    """089:RF-55 — el libro de un año anterior alarga al cliente, con su código actual, sin evaluarse sobre él."""
    f = _fuentes(tmp_path, dias=5)
    anterior = T0 - timedelta(days=20)
    _libro_clientes(tmp_path / 'cli_apoyo/2025/1225c.xlsx', {'111': _serie(20, 30.0, inicio=anterior, q=.2)})
    d = pd_.armar_dataset(pd_.Fuentes(cabecera=f.cabecera, equivalencia=f.equivalencia, clientes=f.clientes, suministros=f.suministros,
                                      apoyo_clientes=tmp_path / 'cli_apoyo'))
    o = _objetivo(d, 'cliente', '111')
    assert min(t for t, _ in o.curva) == anterior
    assert o.fuente['inicio_base'] == T0.isoformat()


def test_mes_a_medias_se_mide_sobre_lo_observado():
    """089:RF-40 — un mes recién cargado con días sin dato no cuenta esos días como error."""
    from convertersmartgrid.digital_twin.pronostico import Objetivo

    curva = [(t, p) for i, (t, p, _q) in enumerate(_serie(120)) if not 110 * 96 <= i < 115 * 96]
    r = pd_.backtest_objetivo(Objetivo('cabecera', 'A1', 'kW', 'kW', curva, {}))
    assert r['status'] == 'EVALUADO' and r['error_prueba']['n'] == 28 * 96 - 5 * 96


def test_cliente_nuevo_no_frena_a_su_alimentador(tmp_path):
    """089:RF-43 — con pocas semanas se aparta como historia insuficiente, y las escaladas siguen."""
    _libro_cabecera(tmp_path / 'cab/s.xlsx', {'M1': _serie(120)})
    nuevo = T0 + timedelta(days=110)
    # El libro de otro cliente da la cobertura desde el principio: si el nuevo fuese el único, antes no habría con qué restar (RF-81).
    _libro_clientes(tmp_path / 'cli/2026/0126c.xlsx', {'6': _serie(120, 5.0)})
    _libro_clientes(tmp_path / 'cli/2026/0426c.xlsx', {'5': _serie(10, 10.0, inicio=nuevo)})
    f = pd_.Fuentes(cabecera=tmp_path / 'cab', equivalencia=_equivalencia(tmp_path / 'e.xlsx', [('A1', 'M1', 10.0, 'X')]),
                    clientes=tmp_path / 'cli', suministros=_suministros(tmp_path / 's.xlsx', [('5', '5', 'S', 'A1'), ('6', '6', 'S', 'A1')]))
    d = pd_.armar_dataset(f)
    assert pd_.backtest_objetivo(_objetivo(d, 'cliente', '5'))['status'] == 'HISTORIA_INSUFICIENTE'
    assert pd_.backtest_objetivo(_objetivo(d, 'escaladas', 'A1'))['status'] == 'EVALUADO'


def test_maniobra_corta_no_es_un_nivel_nuevo():
    """089:RF-38 — tres días con carga transferida no mueven la predicción de los perfiles, que usan medianas."""
    t = np.array([x for x, _p, _q in _serie(120)], dtype='datetime64[ns]')
    y = np.array([p for _t, p, _q in _serie(120)])
    con = y.copy()
    con[-3 * 96:] *= 3
    futuro = pd_._malla(t[-1], t[-1] + np.timedelta64(7, 'D'))
    for m in ('semanal', 'perfil_calendario'):
        assert np.median(np.abs(pd_.predecir(m, t, con, futuro) / pd_.predecir(m, t, y, futuro) - 1)) < .15


# ------------------------------------------------------------------------- modelos
class _Falso:
    """Predice la forma real con un factor: deja probar la competición sin GPU."""

    requiere_gpu = False

    def __init__(self, factor=1.0, falla=False, **_kw):
        self.factor, self.falla = factor, falla
        self.vistos = []

    def ajustar(self, objetivos, hasta, horizonte, exogenas, semilla):
        if self.falla:
            raise RuntimeError('CUDA out of memory')
        self.vistos.append(max(t for o in objetivos for t, _ in o.curva if np.datetime64(t) <= hasta))

    def predecir_todos(self, objetivos, hasta, horizonte, exogenas):
        salida = {}
        for o in objetivos:
            futuro = pd_._malla(hasta, hasta + np.timedelta64(horizonte * 15, 'm'))
            salida[o.nombre] = np.array([_forma(x.astype('datetime64[s]').item()) * 100.0 * self.factor for x in futuro])
        return salida


def _objetivos_ml(n=2):
    from convertersmartgrid.digital_twin.pronostico import Objetivo

    return [Objetivo('cabecera', f'A{i}', 'kW', 'kW', [(t, p) for t, p, _q in _serie(200, ruido=i)], {}) for i in range(n)]


def test_competicion_con_puerta_y_mismos_origenes():
    """089:RF-56, 089:RF-59, 089:RF-60, 089:RF-63 — el mal modelo no pasa, y cada ajuste ve solo lo anterior."""
    creados = {}

    def fabrica(nombre, **_kw):
        creados[nombre] = _Falso(1.0 if nombre == 'bueno' else 1.5)
        return creados[nombre]

    r = pd_.backtest_modelos(_objetivos_ml(), ['bueno', 'malo'], horizonte_dias=7, origenes=3, fabrica=fabrica)
    assert r['modelos']['bueno']['status'] == 'EVALUADO'
    assert r['modelos']['malo']['supera_puerta'] is False
    origenes = sorted(np.datetime64(x) for x in r['origenes'])
    assert len(origenes) == 3 and all(np.datetime64(t) <= origenes[-1] for t in creados['bueno'].vistos)
    assert set(r['perfiles']) == {'semanal', 'perfil_calendario', 'perfil_anclado'}


def test_si_ninguno_pasa_gana_el_perfil_y_se_dice():
    """089:RF-66 — un modelo potente que no bate al perfil no entra."""
    r = pd_.backtest_modelos(_objetivos_ml(), ['malo'], horizonte_dias=7, origenes=3, fabrica=lambda n, **k: _Falso(1.5))
    assert r['ganador'] is None and 'perfil' in r['motivo']


def test_modelo_que_falla_no_frena_a_los_demas():
    """089:RF-61 — sin memoria en la GPU queda con su motivo, y siguen los demás."""
    r = pd_.backtest_modelos(_objetivos_ml(), ['roto', 'bueno'], horizonte_dias=7, origenes=3,
                             fabrica=lambda n, **k: _Falso(1.0, falla=n == 'roto'))
    assert r['modelos']['roto']['status'] == 'ERROR_ENTORNO' and 'memory' in r['modelos']['roto']['motivo']
    assert r['modelos']['bueno']['status'] == 'EVALUADO'


def test_puerta_de_maxima_y_cobertura():
    """089:RF-64, 089:RF-65, 089:RF-67 — la puerta dice cada condición, y el error se abre por horizonte."""
    r = pd_.backtest_modelos(_objetivos_ml(), ['bueno'], horizonte_dias=7, origenes=3, fabrica=lambda n, **k: _Falso(1.0))
    m = r['modelos']['bueno']
    assert {'wape', 'maxima', 'cobertura'} <= set(m['puerta'])
    assert set(m['wape_por_horizonte']) == {'1d', '7d'}


def test_conjunto_compite_como_un_candidato():
    """089:RF-69 — la media de los mejores por elección pasa por la misma puerta."""
    r = pd_.backtest_modelos(_objetivos_ml(), ['a', 'b'], horizonte_dias=7, origenes=3,
                             fabrica=lambda n, **k: _Falso(.9 if n == 'a' else 1.1))
    assert 'conjunto' in r['modelos'] and 'supera_puerta' in r['modelos']['conjunto']


def test_correccion_sobre_el_perfil_con_covariables():
    """089:RF-57, 089:RF-58 — aprende el resto sobre el perfil, a 15 minutos, con huecos enmascarados y lo conocido."""
    from convertersmartgrid.digital_twin.pronostico import Objetivo

    curva = [(t, p) for i, (t, p, _q) in enumerate(_serie(60)) if i != 500]
    o = Objetivo('cabecera', 'A', 'kW', 'kW', curva, {})
    t = pd_.tabla_de_entrenamiento([o], np.datetime64(curva[-1][0]), None)
    assert {'unique_id', 'ds', 'y', 'available_mask', *pd_.COVARIABLES_ML} <= set(t.columns)
    assert t['available_mask'].sum() == len(curva) and (t['available_mask'] == 0).sum() == 1
    pasos = t['ds'].diff().dropna().unique()
    assert len(pasos) == 1 and pasos[0] == np.timedelta64(15, 'm')
    assert abs(t['y'].median()) < .5


def test_dataset_guardado_se_reabre_igual(tmp_path):
    """089:RF-68 — con su huella: entrenar no vuelve a leer los libros, y la misma entrada da la misma huella."""
    d = pd_.armar_dataset(_fuentes(tmp_path, dias=3))
    huella = pd_.guardar_dataset(d, tmp_path / 'ds')
    otro = pd_.abrir_dataset(tmp_path / 'ds')
    assert otro.huella == huella
    assert {o.nombre for o in otro.objetivos} == {o.nombre for o in d.objetivos}
    a, b = _objetivo(d, 'cabecera', 'A1'), _objetivo(otro, 'cabecera', 'A1')
    assert a.curva == b.curva and b.fuente['medidor'] == 'M1'
    assert pd_.guardar_dataset(otro, tmp_path / 'ds2') == huella


def test_lightgbm_directo_real():
    """089:RF-56, 089:RF-57, 089:RF-59 — entrena en CPU y predice todo el horizonte."""
    objs = _objetivos_ml()
    hasta = np.datetime64(objs[0].curva[150 * 96][0])
    m = pd_.fabrica_modelo('lightgbm', pasos=30, semilla=1)
    m.ajustar(objs, hasta, 96, None, 1)
    p = m.predecir_todos(objs, hasta, 96, None)
    assert p[objs[0].nombre].shape == (96,) and np.isfinite(p[objs[0].nombre]).all()
    assert m.requiere_gpu is False


def test_nombres_de_los_candidatos():
    """089:RF-56 — los once están, y un nombre desconocido se rechaza."""
    assert len(pd_.CANDIDATOS) == 11 and 'lightgbm' in pd_.CANDIDATOS
    with pytest.raises(ValueError):
        pd_.fabrica_modelo('otro')


@pytest.mark.parametrize('nombre', ['nhits', 'nbeatsx', 'patchtst', 'tide', 'bitcn', 'gru'])
def test_red_real_en_gpu(nombre):
    """089:RF-56, 089:RF-57, 089:RF-62 — cada red entrena y predice en CUDA con máscara y covariables."""
    objs = _objetivos_ml()
    hasta = np.datetime64(objs[0].curva[150 * 96][0])
    m = pd_.fabrica_modelo(nombre, pasos=2, semilla=1, lote=4, contexto_dias=2)
    m.ajustar(objs, hasta, 96, None, 1)
    p = m.predecir_todos(objs, hasta, 96, None)
    assert p[objs[0].nombre].shape == (96,) and np.isfinite(p[objs[0].nombre]).all()


def test_curvas_compactas(tmp_path):
    """089:RF-70 — cada objetivo guarda sus registros en arreglos: con años de 15 minutos y cientos de series, los objetos agotaban la memoria."""
    d = pd_.armar_dataset(_fuentes(tmp_path, dias=3))
    for o in d.objetivos:
        assert isinstance(o.curva, pd_.CurvaCompacta)
    o = _objetivo(d, 'cabecera', 'A1')
    assert o.curva.bytes_por_registro <= 16
    t, v = o.curva[0]
    assert isinstance(t, datetime) and isinstance(v, float)
    assert list(o.curva)[:1] == [o.curva[0]] and o.curva == list(o.curva)
    assert o.curva[-1] == list(o.curva)[-1]
    c = pd_.CurvaCompacta(np.array(['2026-01-01T00:15'], dtype='datetime64[ns]'), np.array([1.0]), np.array([np.nan]))
    assert c[0] == (datetime(2026, 1, 1, 0, 15), 1.0, None)


def test_cliente_en_varios_libros_con_arreglos(tmp_path):
    """089:RF-70, 046:RF-12 — unir meses no cambia nada: lo repetido igual se une, y lo contradictorio se aparta."""
    a = _serie(3, 30.0)
    b = _serie(2, 30.0, inicio=a[-1][0])
    b[0] = a[-1]
    r1 = _libro_clientes(tmp_path / 'u1.xlsx', {'7': a})
    r2 = _libro_clientes(tmp_path / 'u2.xlsx', {'7': b})
    objetivos, apartados = pd_.objetivos_de_clientes([r1, r2])
    assert not apartados and len(next(o for o in objetivos if o.magnitud == 'kW').curva) == len(a) + len(b) - 1
    malo = [(a[-1][0], 999.0, 1.0)]
    r3 = _libro_clientes(tmp_path / 'u3.xlsx', {'7': malo})
    objetivos, apartados = pd_.objetivos_de_clientes([r1, r3])
    assert not objetivos and 'otro valor' in apartados[0]['motivo']


# ------------------------------------------------------------------------- hallazgos de la revisión independiente
def test_el_anclado_ancla_tras_un_escalon():
    """089:RF-71 — con +40 % hace 60 días, el anclado da el nivel nuevo: antes daba el viejo, igual que el calendario."""
    from convertersmartgrid.digital_twin.pronostico import Objetivo

    curva = [(t, p * (1.4 if i > 120 * 96 else 1.0)) for i, (t, p, _q) in enumerate(_serie(200))]
    t = np.array([x for x, _ in curva], dtype='datetime64[ns]')
    y = np.array([v for _, v in curva])
    corte = 181 * 96                 # empieza un mes sin historia: la forma cae a todo el año, con el nivel viejo
    futuro = t[corte:corte + 96 * 7]
    p = pd_.predecir('perfil_anclado', t[:corte], y[:corte], futuro)
    assert pd_.medir(y[corte:corte + 96 * 7], p)['wape'] < .05
    assert Objetivo


def test_el_anclado_con_q_que_cruza_cero_no_se_dispara():
    """089:RF-71 — donde la referencia ronda cero, un cociente da cualquier cosa: se ancla sumando."""
    t = np.array([x for x, _p, _q in _serie(120)], dtype='datetime64[ns]')
    y = 5.0 * np.sin(2 * np.pi * np.arange(len(t)) / 96)
    p = pd_.predecir('perfil_anclado', t[:100 * 96], y[:100 * 96], t[100 * 96:101 * 96])
    assert np.abs(p).max() < 20


def test_cliente_atrasado_deja_sin_escaladas_los_ultimos_instantes():
    """089:RF-32 — cabecera hasta octubre y clientes hasta septiembre: no se le regala la carga fija a las escaladas."""
    ts = [T0 + PASO * i for i in range(10)]
    cab = [(t, 1000.0, 0.0) for t in ts]
    cli = [(t, 700.0, 0.0) for t in ts[:6]]
    assert [p for _t, p, _q in pd_.escaladas_de(cab, [cli])] == [300.0] * 6


def test_cliente_retirado_hace_tiempo_ya_no_se_resta():
    """089:RF-72 — frente al último dato de todos los clientes, el que acabó hace más de 45 días se dio de baja."""
    ts = [T0 + timedelta(days=i) for i in range(100)]
    cab = [(t, 1000.0, 0.0) for t in ts]
    retirado = [(t, 700.0, 0.0) for t in ts[:20]]
    salida = pd_.escaladas_de(cab, [retirado], ultimo_clientes=ts[-1])
    assert len(salida) == 100 and salida[-1][1] == 1000.0 and salida[0][1] == 300.0


def test_sin_clientes_no_hay_escaladas_falsas(tmp_path):
    """089:RF-73 — sin clientes o sin suministros no se puede restar: no se dan escaladas iguales a la cabecera."""
    d = pd_.armar_dataset(_fuentes(tmp_path, dias=3, clientes=False))
    assert not [o for o in d.objetivos if o.clase == 'escaladas']


def test_cliente_contradictorio_sigue_restando(tmp_path):
    """089:RF-74 — apartarlo como objetivo no quita su carga del alimentador."""
    _libro_cabecera(tmp_path / 'cab/s.xlsx', {'M1': _serie(5, 100.0)})
    a = _serie(5, 30.0)
    _libro_clientes(tmp_path / 'cli/2026/0126c.xlsx', {'9': a})
    _libro_clientes(tmp_path / 'cli/2026/0226d.xlsx', {'9': [(a[0][0], 31.0, 1.0)]})
    f = pd_.Fuentes(cabecera=tmp_path / 'cab', equivalencia=_equivalencia(tmp_path / 'e.xlsx', [('A1', 'M1', 10.0, 'X')]),
                    clientes=tmp_path / 'cli', suministros=_suministros(tmp_path / 's.xlsx', [('9', '9', 'S', 'A1')]))
    d = pd_.armar_dataset(f)
    cab, esc = dict(_objetivo(d, 'cabecera', 'A1').curva), dict(_objetivo(d, 'escaladas', 'A1').curva)
    t = a[5][0]
    assert esc[t] < cab[t] - 1


def test_libro_nuevo_roto_se_dice(tmp_path):
    """089:RF-75 — el mes que no se puede abrir no se calla: la serie acabaría antes sin explicación."""
    f = _fuentes(tmp_path, dias=3, clientes=False)
    (tmp_path / 'cab/2026/roto.xlsx').write_bytes(b'no soy un libro')
    d = pd_.armar_dataset(f)
    assert any('roto.xlsx' in a for a in d.avisos)


def test_suma_cortada_se_dice(tmp_path):
    """089:RF-76 — un medidor que falta en el mes nuevo corta la suma: se dice hasta dónde llega."""
    _libro_cabecera(tmp_path / 'cab/s.xlsx', {'M1': _serie(10), 'M2': _serie(5)})
    eq = _equivalencia(tmp_path / 'e.xlsx', [('A1', 'M1 Y M2', 10.0, 'X')])
    d = pd_.armar_dataset(pd_.Fuentes(cabecera=tmp_path / 'cab', equivalencia=eq))
    assert any('A1' in a and 'hasta' in a for a in d.avisos)


def test_canal_con_nombre_distinto_entre_meses(tmp_path):
    """089:RF-77 — «IN1_V18» en un libro e «IN1» en otro son el mismo punto: no son medidores sin instantes comunes."""
    _libro_cabecera(tmp_path / 'cab/a.xlsx', {'IN1_V18': _serie(3)})
    _libro_cabecera(tmp_path / 'cab/b.xlsx', {'IN1': _serie(3, inicio=T0 + timedelta(days=3))})
    eq = _equivalencia(tmp_path / 'e.xlsx', [('A1', 'IN1_V18 Y IN1_V19', 10.0, 'X')])
    d = pd_.armar_dataset(pd_.Fuentes(cabecera=tmp_path / 'cab', equivalencia=eq))
    assert len(_objetivo(d, 'cabecera', 'A1').curva) == 6 * 96


def test_central_con_balance_roto_no_se_descuenta(tmp_path):
    """089:RF-78 — si el balance no cuadra, no se entrena con otra serie sin avisar."""
    n = 24
    cab = [(T0 + PASO * i, 300.0, 1.0) for i in range(n)]
    gen = [(T0 + PASO * i, 5000.0, 1.0) for i in range(n)]
    lle = [(T0 + PASO * i, 10.0, 1.0) for i in range(n)]
    sal = [(T0 + PASO * i, 20.0, 1.0) for i in range(n)]
    libro = _libro_cabecera(tmp_path / 'c.xlsx', {'CAB': cab, 'GEN': gen, 'LLE': lle, 'SAL': sal})
    objetivos, apartados = pd_.objetivos_de_cabecera([libro], [('A1', 'CAB')], centrales={'A1': {'generacion': 'GEN', 'llegada': 'LLE', 'salida': 'SAL'}})
    assert not objetivos and 'balance' in apartados[0]['motivo']


def test_cualquier_fallo_de_un_modelo_no_aborta(tmp_path):
    """089:RF-61 — la librería lanza Exception a secas: un modelo roto no se lleva las horas de los demás."""
    class Roto(_Falso):
        def ajustar(self, *a):
            raise Exception('fallo interno')

    r = pd_.backtest_modelos(_objetivos_ml(), ['roto', 'bueno'], horizonte_dias=7, origenes=3, fabrica=lambda n, **k: Roto() if n == 'roto' else _Falso())
    assert r['modelos']['roto']['status'] == 'ERROR_ENTORNO' and r['modelos']['bueno']['status'] == 'EVALUADO'


def test_fila_repetida_no_dispara_las_fechas(tmp_path):
    """089:RF-79 — una fila duplicada se cuenta y sale: antes hacía avanzar un día por fila hasta 2027."""
    wb = Workbook()
    r = wb.active
    r.title = 'resumen'
    r.append(['Nis', 'EA', 'ERI', 'POT'])
    r.append(['181', 1.0, 1.0, 40.0])
    h = wb.create_sheet('c')
    h.append(['', '', '', '', '', '181'])
    h.append(['', '', '', '', '', 'EA', 'ERI', 'ERC', '', 'EA', 'ERI', 'ERC', 'Pot'])
    h.append(['día', 'hora', 'f', 'p', '', 1, 1, 0, '', 1, 1, 0, 1])
    for d, texto in ((2, '10:00'), (2, '10:00'), (2, '10:15'), (2, '10:30')):
        h.append([d, texto, 1, 1, '', 9.0, 9.0, 0, '', 1.0, 2.0, 0, 40.0])
    wb.save(tmp_path / 'x.xlsx')
    curvas, avisos = curvas_de_clientes(tmp_path / 'x.xlsx', mes='2026-01')
    assert [t for t, _p, _q in curvas['181']] == [datetime(2026, 1, 2, 10, 0), datetime(2026, 1, 2, 10, 15), datetime(2026, 1, 2, 10, 30)]
    assert any('1 registro' in a for a in avisos)


def test_huella_alterada_se_rechaza(tmp_path):
    """089:RF-68 — un Parquet cambiado o vacío no pasa por el dataset guardado."""
    import pandas as pd

    d = pd_.armar_dataset(_fuentes(tmp_path, dias=3))
    pd_.guardar_dataset(d, tmp_path / 'ds')
    t = pd.read_parquet(tmp_path / 'ds/objetivos.parquet')
    t.loc[0, 'v'] = 999.0
    t.to_parquet(tmp_path / 'ds/objetivos.parquet')
    with pytest.raises(ValueError, match='huella'):
        pd_.abrir_dataset(tmp_path / 'ds')


def test_calendario_con_bom_de_excel(tmp_path):
    """089:RF-44 — un CSV guardado desde Excel lleva BOM: el calendario no puede quedar vacío sin avisar."""
    c = tmp_path / 'exo'
    c.mkdir()
    (c / 'f.csv').write_bytes('﻿fecha,no_laborable,norma\n2026-03-04,True,DS 1\n'.encode('utf-8'))
    assert pd_.leer_exogenas(c).no_laborables == {date(2026, 3, 4)}


def test_una_ventana_sin_dato_no_anula_la_eleccion():
    """089:RF-80 — 28 días sin medida en un origen no vuelven infinito a todos los métodos: se elige con los demás."""
    from convertersmartgrid.digital_twin.pronostico import Objetivo

    serie = _serie(200)
    curva = [(t, p * (2.0 if i > 170 * 96 else 1.0)) for i, (t, p, _q) in enumerate(serie) if not (110 * 96 <= i < 146 * 96)]
    r = pd_.backtest_objetivo(Objetivo('cabecera', 'A', 'kW', 'kW', curva, {}), origenes=4)
    assert r['status'] == 'EVALUADO' and all(math.isfinite(v) for v in r['seleccion'].values())


def test_atipico_no_recorta_un_escalon_ni_arranques_de_cliente():
    """089:RF-24 — como mucho 2 seguidos en cabecera, y a un cliente solo lo imposible frente a su máximo reciente."""
    base = _serie(30)
    escalon = base[:1500] + [(t, p * 5, q) for t, p, q in base[1500:]]
    _, informe = pd_.limpiar_curva(escalon, 'cabecera')
    limpia, _ = pd_.limpiar_curva(escalon, 'cabecera')
    assert base[1502][0] in {t for t, _p, _q in limpia}
    arranca = [(t, (250.0 if i % 96 < 20 and i > 1000 else 100.0) + i % 3, 1.0) for i, (t, _p, _q) in enumerate(base)]
    assert pd_.limpiar_curva(arranca, 'cliente')[1]['atipico'] == 0
    desborde = list(arranca)
    desborde[1500] = (desborde[1500][0], 32765.0, 1.0)
    assert pd_.limpiar_curva(desborde, 'cliente')[1]['atipico'] == 1


def test_una_hoja_de_cada_libro_una_sola_lectura(tmp_path):
    """089:RF-1 — la misma hoja en varios libros no multiplica las lecturas."""
    a = _libro_cabecera(tmp_path / 'c/a.xlsx', {'M1': _serie(1)})
    _libro_cabecera(tmp_path / 'c/b.xlsx', {'M1': _serie(1, inicio=T0 + timedelta(days=1))})
    curvas, _ = pd_.curvas_de_cabecera([a.parent])
    assert len(curvas) == 1 and len(curvas['M1']['curva']) == 2 * 96


def _dias(n, inicio=T0):
    return [inicio + timedelta(days=i) for i in range(n)]


def test_antes_de_haber_libros_de_clientes_no_hay_escaladas():
    """089:RF-81 — PA217: cabecera desde 2023 y libros desde 2025; dar la cabecera como escaladas es un nivel falso."""
    ts = _dias(100)
    cab = [(t, 1000.0, 0.0) for t in ts]
    cli = [(t, 700.0, 0.0) for t in ts[50:]]
    assert [t for t, _p, _q in pd_.escaladas_de(cab, [cli], primero_clientes=ts[50])] == ts[50:]


def test_cliente_que_aparece_sin_escalon_ya_estaba():
    """089:RF-82 — PE102: la cabecera sigue plana cuando empieza su libro; la carga ya estaba, faltaba el dato."""
    ts = _dias(100)
    cab = [(t, 1000.0, 0.0) for t in ts]
    cli = [(t, 700.0, 0.0) for t in ts[50:]]
    salida = pd_.escaladas_de(cab, [cli], primero_clientes=ts[0])
    assert [t for t, _p, _q in salida] == ts[50:] and {p for _t, p, _q in salida} == {300.0}


def test_cliente_nuevo_de_verdad_conserva_la_historia():
    """089:RF-83 — la cabecera sube lo que consume: es una conexión real y antes las escaladas eran toda la cabecera."""
    ts = _dias(100)
    cab = [(t, 300.0 if i < 50 else 1000.0, 0.0) for i, t in enumerate(ts)]
    cli = [(t, 700.0, 0.0) for t in ts[50:]]
    salida = pd_.escaladas_de(cab, [cli], primero_clientes=ts[0])
    assert len(salida) == 100 and {p for _t, p, _q in salida} == {300.0}


def test_cliente_pequeno_sin_escalon_no_borra_la_historia():
    """089:RF-84 — su escalón no se distingue del ruido, y el error de no restarlo antes es pequeño."""
    ts = _dias(100)
    cab = [(t, 1000.0, 0.0) for t in ts]
    cli = [(t, 100.0, 0.0) for t in ts[90:]]
    assert len(pd_.escaladas_de(cab, [cli], primero_clientes=ts[0])) == 100


def test_escala_del_mase_con_el_ingenuo_de_la_semana():
    """089:RF-85 — error medio de repetir lo de hace una semana; los huecos no se emparejan con otro instante."""
    t = np.datetime64('2026-01-01T00:15') + np.arange(96 * 21) * np.timedelta64(15, 'm')
    y = np.arange(96 * 21, dtype=float)
    assert pd_.escala_estacional(t, y) == pytest.approx(672.0)
    sin = np.r_[0:96 * 7, 96 * 14:96 * 21]               # falta la segunda semana: la tercera no tiene con qué compararse
    assert pd_.escala_estacional(t[sin], y[sin]) is None


def test_mase_no_definido_con_una_serie_que_se_repite_exacta():
    """089:RF-86 — con escala cero, el cociente no significa nada: se dice que no hay MASE, no se da infinito."""
    t = np.datetime64('2026-01-01T00:15') + np.arange(96 * 21) * np.timedelta64(15, 'm')
    y = np.tile(np.arange(96 * 7, dtype=float), 3)
    assert pd_.escala_estacional(t, y) is None
    assert pd_.medir(y[:4], y[:4] + 1, escala=None)['mase'] is None


def test_el_mase_no_mira_el_futuro():
    """089:RF-87 — la escala sale de la historia de cada origen: cambiar lo posterior no la toca."""
    serie = _serie(200)
    curva = [(t, p) for t, p, _q in serie]
    from convertersmartgrid.digital_twin.pronostico import Objetivo

    a = pd_.backtest_objetivo(Objetivo('cabecera', 'A', 'kW', 'kW', curva, {}), origenes=3)
    cambiada = [(t, p * (50.0 if i > len(curva) - 96 * 28 else 1.0)) for i, (t, p) in enumerate(curva)]
    b = pd_.backtest_objetivo(Objetivo('cabecera', 'A', 'kW', 'kW', cambiada, {}), origenes=3)
    assert a['prueba']['semanal']['escala_mase'] == pytest.approx(b['prueba']['semanal']['escala_mase'])
    assert a['prueba']['semanal']['mase'] != pytest.approx(b['prueba']['semanal']['mase'])


def test_el_resumen_da_el_mase_por_clase():
    """089:RF-88 — mediana por método, sin que un objetivo sin MASE la rompa."""
    from convertersmartgrid.digital_twin.pronostico import Objetivo

    r = pd_.backtest(pd_.Dataset(objetivos=[Objetivo('cabecera', 'A', 'kW', 'kW', [(t, p) for t, p, _q in _serie(200)], {})], apartados=[], libros=[], ultimo_dato={}), origenes=3)
    assert r['resumen']['cabecera|kW']['mase_prueba']['semanal'] > 0


def test_las_redes_toman_una_ventana_por_dia():
    """089:RF-91 — una ventana de entrenamiento por día y no por registro: con 28 días de contexto y de horizonte, N-HiTS pidió
    285 GiB en la cabecera real (2026-11-12)."""
    objs = _objetivos_ml()
    hasta = np.datetime64(objs[0].curva[150 * 96][0])
    m = pd_.fabrica_modelo('nhits', pasos=2, semilla=1, lote=4, contexto_dias=2)
    m.ajustar(objs, hasta, 96, None, 1)
    assert pd_.PASO_VENTANAS == 96 and m.nf.models[0].step_size == pd_.PASO_VENTANAS


def test_tope_de_lote_y_escalado_por_red():
    """089:RF-92, 089:RF-93 — TFT entrena con lote 1 aunque se pida más, e iTransformer sin el escalado de la librería (2026-11-12:
    TFT no cupo en la GPU con lote 4 e iTransformer dio «Loss is NaN» en la cabecera real)."""
    objs = _objetivos_ml()
    hasta = np.datetime64(objs[0].curva[150 * 96][0])
    assert pd_.fabrica_modelo('tft', pasos=2, lote=16).lote == 1
    assert pd_.fabrica_modelo('nhits', pasos=2, lote=16).lote == 16
    m = pd_.fabrica_modelo('itransformer', pasos=2, semilla=1, lote=4, contexto_dias=2)
    m.ajustar(objs, hasta, 96, None, 1)
    assert m.nf.models[0].scaler.scaler_type == 'identity'
    assert pd_.fabrica_modelo('nhits', pasos=2).lote == 64
    p = m.predecir_todos(objs, hasta, 96, None)
    assert np.isfinite(p[objs[0].nombre]).all()
