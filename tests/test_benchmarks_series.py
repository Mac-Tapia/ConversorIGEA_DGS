"""Spec 112: series de demanda desidentificadas del dataset del 089 (112:RF-2, RF-3, RF-11).

Las series del benchmark salen del dataset del 089 sin tocarlo: cada objetivo recibe un identificador del mapa de
seudónimos, sus valores se multiplican por una escala sorteada (WAPE y MASE no dependen de la escala) y sus fechas se
desplazan semanas completas, que conservan la hora y el día de la semana. Los feriados y la temperatura viajan como
columnas de la fila, para que el calendario real no haga falta ni se pueda deducir. Las series de aquí son sintéticas,
generadas en la prueba; ningún método lanza GPU.
"""
from __future__ import annotations

import importlib.util

import csv
import hashlib
import math
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from convertersmartgrid.adaptadores.digital_twin.pronostico import Objetivo
from convertersmartgrid.adaptadores.pronostico_demanda import METODOS, CurvaCompacta, Dataset, Exogenas

INICIO = datetime(2025, 3, 3)      # un lunes cualquiera
DIAS = 126


def _serie(semilla: int, base_kw: float, *, industrial: bool = False):
    r = np.random.default_rng(semilla)
    t = np.arange(np.datetime64(INICIO), np.datetime64(INICIO + timedelta(days=DIAS)), np.timedelta64(15, 'm'))
    h = (t - t.astype('datetime64[D]')).astype('timedelta64[m]').astype(float) / 60.0
    dia = ((t.astype('datetime64[D]').astype(int) + 3) % 7)       # 0 = lunes
    forma = 1.0 + 0.35 * np.sin((h - 6) / 24 * 2 * np.pi) - 0.15 * (dia >= 5)
    if industrial:     # patrón único: turnos cuadrados de una planta
        forma = np.where((h >= 7) & (h < 19) & (dia < 6), 1.0, 0.25)
    return t, base_kw * forma * (1 + 0.03 * r.standard_normal(len(t)))


def _dataset(semilla: int = 5) -> Dataset:
    objetivos = []
    for k, (clase, ident, base, ind) in enumerate([
        ('cabecera', 'ZX101', 3200.0, False),
        ('cabecera', 'ZX102', 1800.0, False),
        ('cliente', 'QW55001', 7400.0, True),
    ]):
        t, v = _serie(semilla + k, base, industrial=ind)
        objetivos.append(Objetivo(clase, ident, 'kW', 'kW', CurvaCompacta(t, v),
                                  {'inicio_base': str(INICIO.date()), 'potencia_contratada_kw': base * 1.3,
                                   'libro': 'Libro de clientes de la gerencia norte.xlsx'}))
    feriados = {date(2025, 4, 17), date(2025, 4, 18), date(2025, 5, 1)}
    temperatura = {INICIO + timedelta(hours=i): 20 + 6 * math.sin(i / 24 * 2 * math.pi) for i in range(DIAS * 24)}
    return Dataset(objetivos, [], [], {}, Exogenas(feriados, temperatura, []), 'huella-sintetica')


def _escribir(dataset: Dataset, destino: Path, semilla: int = 77):
    from convertersmartgrid.adaptadores.benchmarks import series as S
    from convertersmartgrid.dominio.benchmarks.seudonimos import Mapa
    mapa = Mapa(semilla)
    S.registrar(dataset, mapa)
    mapa.congelar()
    return mapa, S.escribir(dataset, destino, mapa, semilla=semilla)


def _filas(ruta: Path) -> list[dict[str, str]]:
    with ruta.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def test_identificadores_nuevos_y_nada_del_origen(tmp_path):
    """112:RF-2, RF-11 — cada objetivo lleva un seudónimo; ni sus códigos, ni el libro, ni la potencia contratada salen."""
    ds = _dataset()
    mapa, informe = _escribir(ds, tmp_path / 'b')
    texto = '\n'.join(p.read_text(encoding='utf-8') for p in (tmp_path / 'b').iterdir())
    for o in ds.objetivos:
        assert o.ident not in texto
    assert 'gerencia' not in texto and 'potencia_contratada' not in texto
    assert str(INICIO.date()) not in texto
    assert sorted(p.name for p in (tmp_path / 'b').iterdir()) == sorted(informe.ficheros)
    objetivos = _filas(tmp_path / 'b' / 'series_objetivos.csv')
    assert {o['clase'] for o in objetivos} == {'cabecera', 'cliente'}
    assert all(o['ident'].startswith('B') for o in objetivos)
    assert mapa('alimentador', 'ZX101') in {o['ident'] for o in objetivos}


def test_semanas_completas_y_escala_sorteada(tmp_path):
    """112:RF-3, RF-11 — las fechas avanzan semanas completas (≥ 104 y fuera del intervalo original); la forma queda."""
    ds = _dataset()
    mapa, _ = _escribir(ds, tmp_path / 'b')
    filas = _filas(tmp_path / 'b' / 'series.csv')
    original = ds.objetivos[0]
    nombre = f"cabecera:{mapa('alimentador', original.ident)}:kW"
    propias = [f for f in filas if f['objetivo'] == nombre]
    assert len(propias) == len(original.curva.t)
    t0 = datetime.fromisoformat(propias[0]['t'])
    delta = t0 - original.curva.t[0].astype('datetime64[s]').astype(datetime)
    assert delta.days % 7 == 0 and delta.seconds == 0 and delta.days // 7 >= 104
    assert t0 > original.curva.t[-1].astype('datetime64[s]').astype(datetime)
    v = np.array([float(f['v']) for f in propias])
    razon = v / original.curva.columnas[0]
    assert 0.5 <= razon.mean() <= 2.0 and np.allclose(razon, razon.mean(), rtol=1e-5)


def test_feriados_y_temperatura_como_columnas(tmp_path):
    """112:RF-11 — el feriado viaja desplazado en su fila, con la temperatura; el calendario real no hace falta."""
    ds = _dataset()
    _escribir(ds, tmp_path / 'b')
    filas = _filas(tmp_path / 'b' / 'series.csv')
    assert {'objetivo', 't', 'v', 'no_laborable', 'temperatura_c'} <= set(filas[0])
    dias_feriado = {f['t'][:10] for f in filas if f['no_laborable'] == '1'}
    assert len(dias_feriado) == len(ds.exogenas.no_laborables)
    for d in dias_feriado:
        assert date.fromisoformat(d).weekday() in {date(2025, 4, 17).weekday(), date(2025, 4, 18).weekday(),
                                                   date(2025, 5, 1).weekday()}
    assert any(f['temperatura_c'] for f in filas)


def test_la_potencia_queda_en_bandas(tmp_path):
    """112:RF-2, RF-11 — una carga industrial de patrón único no lleva su potencia: solo su banda."""
    ds = _dataset()
    _escribir(ds, tmp_path / 'b')
    objetivos = {o['clase']: o for o in _filas(tmp_path / 'b' / 'series_objetivos.csv')}
    assert objetivos['cliente']['banda'] == '> 5 MVA'
    assert {o['banda'] for o in _filas(tmp_path / 'b' / 'series_objetivos.csv')} <= {'< 1 MVA', '1–5 MVA', '> 5 MVA'}


def test_csv_determinista(tmp_path):
    """112:RF-11 — mismo dataset y misma semilla, mismos bytes; con otra semilla, otras escalas y otras fechas."""
    ds = _dataset()

    def huella(carpeta):
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(carpeta.iterdir())}

    _escribir(ds, tmp_path / 'a', semilla=3)
    _escribir(ds, tmp_path / 'b', semilla=3)
    _escribir(ds, tmp_path / 'c', semilla=4)
    assert huella(tmp_path / 'a') == huella(tmp_path / 'b')
    assert huella(tmp_path / 'a')['series.csv'] != huella(tmp_path / 'c')['series.csv']


def test_las_metricas_de_base_se_reproducen(tmp_path):
    """112:RF-11, RF-3 — WAPE y MASE de cada método de base, en el original y en el benchmark, dentro del 1 %."""
    from convertersmartgrid.adaptadores.benchmarks.reproduccion import reproducir_series
    ds = _dataset()
    mapa, _ = _escribir(ds, tmp_path / 'b')
    rep = reproducir_series(ds, tmp_path / 'b', mapa=mapa)
    assert rep.reproduce, [m.texto() for m in rep.motivos]
    assert rep.tolerancia.metrica_rel == 0.01
    assert len(rep.metricas_original) == len(ds.objetivos)
    for nombre, m in rep.metricas_original.items():
        assert set(METODOS) <= set(m['prueba']), nombre
        assert 'wape' in m['prueba']['semanal'] and 'mase' in m['prueba']['semanal']
    assert not {o.ident for o in ds.objetivos} & {n.split(':')[1] for n in rep.metricas_original}


def test_series_leidas_del_benchmark(tmp_path):
    """112:RF-11 — lo escrito se vuelve a leer como objetivos y exógenas del 089, sin el calendario real."""
    from convertersmartgrid.adaptadores.benchmarks import series as S
    ds = _dataset()
    _escribir(ds, tmp_path / 'b')
    objetivos, exogenas = S.leer(tmp_path / 'b')
    assert len(objetivos) == len(ds.objetivos)
    assert len(exogenas.no_laborables) == len(ds.exogenas.no_laborables)
    assert len(exogenas.temperatura) > 0
    assert all(isinstance(o.curva, CurvaCompacta) for o in objetivos)


def test_desde_la_carpeta_del_089_sin_modificarla(tmp_path):
    """112:RF-11 — se lee lo que emite el 089 (``abrir_dataset``) y su carpeta queda igual, byte a byte."""
    from convertersmartgrid.adaptadores.benchmarks import series as S
    from convertersmartgrid.adaptadores.pronostico_demanda import guardar_dataset
    ds = _dataset()
    ds.exogenas = None
    carpeta = tmp_path / '089'
    guardar_dataset(ds, carpeta)
    antes = {p.name: p.read_bytes() for p in carpeta.iterdir()}
    leido, huella = S.abrir_089(carpeta)
    assert len(leido.objetivos) == len(ds.objetivos) and huella == leido.huella
    assert {p.name: p.read_bytes() for p in carpeta.iterdir()} == antes




def test_manifiesto_con_las_series_del_089(tmp_path):
    """112:RF-5, RF-11 — con el dataset del 089, el manifiesto lleva su huella y las métricas de base de los dos lados."""
    assert importlib.util.find_spec('convertersmartgrid.adaptadores.benchmarks.manifiesto'), 'falta convertersmartgrid.adaptadores.benchmarks.manifiesto'
    pytest.importorskip('pyarrow')
    pytest.importorskip('pandapower')
    import json

    from convertersmartgrid.adaptadores.benchmarks import generar_benchmark
    from convertersmartgrid.adaptadores.pronostico_demanda import guardar_dataset
    from synthetic_export import ExportSpec, write_export
    ds = _dataset()
    ds.exogenas = None
    guardar_dataset(ds, tmp_path / '089')
    trio = write_export(ExportSpec(feeders=2, seed=8, layout='reducido'), tmp_path / 'origen')
    m = generar_benchmark(*trio, tmp_path / 'bench', semilla=6_002_118_440_073_551_901, raiz=tmp_path / 'local',
                          dataset_089=tmp_path / '089')
    assert m['origen']['huella_089'] == json.loads((tmp_path / '089' / 'dataset.json').read_text(encoding='utf-8'))['huella']
    assert {'series.csv', 'series_objetivos.csv'} <= set(m['ficheros'])
    serie = m['metricas_referencia']['series']
    assert set(serie) == {'original', 'benchmark'} and len(serie['original']) == len(ds.objetivos)
    assert m['tolerancia']['metrica_rel'] == 0.01
