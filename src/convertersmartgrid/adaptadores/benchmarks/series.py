"""Benchmark de series: los objetivos del 089 desidentificados (112:RF-2, RF-3, RF-11).

Del dataset del 089 solo se lee lo que emite (``abrir_dataset``): este módulo no lo modifica. Cada objetivo recibe un
identificador del mapa de seudónimos, sus valores se multiplican por una escala sorteada en ``[0,5, 2]`` —WAPE y MASE no
dependen de la escala— y las fechas avanzan un número sorteado de semanas completas, que conserva la hora y el día de la
semana. El desplazamiento supera siempre el intervalo del origen: ninguna fecha publicada cae dentro de él.

Los feriados, la temperatura y el mes de calendario que usa el 089 viajan como columnas de cada fila (``no_laborable``,
``temperatura_c``, ``mes``): el calendario real no hace falta para repetir el backtest y no se puede deducir de las
fechas. El mes hace falta porque el desplazamiento de semanas no lo conserva y «perfil_calendario» agrupa por él. La potencia contratada y
el resto de la procedencia (libros, avisos) no salen; de cada objetivo solo queda su banda de potencia.

CSV con formato numérico fijo: los mismos bytes en cualquier entorno (Parquet guarda la versión de su escritor).
"""
from __future__ import annotations

import csv
import io
import math
import random
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np

from ..digital_twin.pronostico import Objetivo
from ..pronostico_demanda import CurvaCompacta, Dataset, Exogenas, abrir_dataset
from ...dominio.benchmarks.seudonimos import Mapa

SERIES = 'series.csv'
OBJETIVOS = 'series_objetivos.csv'
FICHEROS = (SERIES, OBJETIVOS)
COLUMNAS_SERIE = ('objetivo', 't', 'v', 'no_laborable', 'temperatura_c', 'mes')
COLUMNAS_OBJETIVO = ('objetivo', 'clase', 'ident', 'magnitud', 'unidad', 'banda', 'inicio_base')
#: Tipo de seudónimo de cada clase del 089: la cabecera es un alimentador; el resto, un cliente.
TIPO_DE_CLASE = {'cabecera': 'alimentador', 'cliente': 'cliente'}
#: Semanas mínimas del desplazamiento (plan de la 112): dos años, que no dejan reconocer la estación por la fecha.
SEMANAS_MINIMAS = 104
ESCALA_MIN, ESCALA_MAX = 0.5, 2.0


def _tipo(clase: str) -> str:
    return TIPO_DE_CLASE.get(clase, 'medidor')


def abrir_089(carpeta: Path | str) -> tuple[Dataset, str]:
    """El dataset que emitió el 089, con su huella comprobada por el propio 089. No se escribe nada en su carpeta."""
    ds = abrir_dataset(carpeta)
    return ds, ds.huella


def registrar(dataset: Dataset, mapa: Mapa) -> None:
    """Apunta en el mapa el identificador de cada objetivo (el de la red y el de las series comparten mapa)."""
    for o in dataset.objetivos:
        mapa.registrar(_tipo(o.clase), o.ident)


def nombre_publicado(o: Objetivo, mapa: Mapa) -> str:
    """El nombre del objetivo en el benchmark: el del 089 (clase:ident:magnitud) con el seudónimo."""
    return f'{o.clase}:{mapa(_tipo(o.clase), o.ident)}:{o.magnitud}'


def banda(maximo_kw_o_kva: float) -> str:
    """La potencia solo en bandas: una carga industrial de patrón único no lleva su potencia (plan de la 112)."""
    if maximo_kw_o_kva < 1000:
        return '< 1 MVA'
    return '1–5 MVA' if maximo_kw_o_kva <= 5000 else '> 5 MVA'


def arreglos(o: Objetivo) -> tuple[np.ndarray, np.ndarray]:
    if isinstance(o.curva, CurvaCompacta):
        return o.curva.t, o.curva.columnas[0]
    orden = sorted(o.curva, key=lambda f: f[0])
    return (np.array([t for t, _v in orden], dtype='datetime64[ns]'),
            np.array([v for _t, v in orden], dtype=float))


def _intervalo(dataset: Dataset) -> tuple[np.datetime64, np.datetime64] | None:
    extremos = [(t[0], t[-1]) for t, _ in map(arreglos, dataset.objetivos) if len(t)]
    if not extremos:
        return None
    return min(a for a, _ in extremos), max(b for _, b in extremos)


def desplazamiento_semanas(dataset: Dataset, semilla: int) -> int:
    """Semanas completas sorteadas, ≥ 104 y más que todo el intervalo del origen: lo publicado cae fuera de él."""
    intervalo = _intervalo(dataset)
    largo = 0 if intervalo is None else int((intervalo[1] - intervalo[0]) / np.timedelta64(7, 'D')) + 1
    return max(SEMANAS_MINIMAS, largo + 1) + random.Random(f'{int(semilla)}:semanas').randint(0, 52)


def escala(semilla: int, nombre_seudonimo: str) -> float:
    return random.Random(f'{int(semilla)}:escala:{nombre_seudonimo}').uniform(ESCALA_MIN, ESCALA_MAX)


@dataclass
class InformeSeries:
    ficheros: list[str]
    objetivos: int
    filas: int


def _iso(t: np.datetime64) -> str:
    return str(np.datetime64(t, 's')).replace(' ', 'T')


def escribir(dataset: Dataset, destino: Path | str, mapa: Mapa, *, semilla: int) -> InformeSeries:
    """Escribe ``series.csv`` y ``series_objetivos.csv``. El desplazamiento y las escalas no se escriben."""
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    delta = np.timedelta64(7 * desplazamiento_semanas(dataset, semilla), 'D')
    exo = dataset.exogenas or Exogenas()
    feriados = {np.datetime64(d, 'D') for d in exo.no_laborables}
    temperatura = {np.datetime64(t, 's'): v for t, v in exo.temperatura.items()}
    salida = io.StringIO(newline='')
    w = csv.writer(salida, lineterminator='\n')
    w.writerow(COLUMNAS_SERIE)
    indice = io.StringIO(newline='')
    wi = csv.writer(indice, lineterminator='\n')
    wi.writerow(COLUMNAS_OBJETIVO)
    filas = 0
    nombres = []
    for o in dataset.objetivos:
        nombres.append((nombre_publicado(o, mapa), o, str(mapa(_tipo(o.clase), o.ident))))
    for nombre, o, ident in sorted(nombres, key=lambda x: x[0]):
        t, y = arreglos(o)
        k = escala(semilla, nombre)
        finitos = np.abs(y[np.isfinite(y)])
        inicio = o.fuente.get('inicio_base') if isinstance(o.fuente, dict) else None
        inicio_nuevo = _iso(np.datetime64(inicio) + delta)[:10] if inicio else ''
        wi.writerow((nombre, o.clase, ident, o.magnitud, o.unidad,
                     banda(float(finitos.max()) if len(finitos) else 0.0), inicio_nuevo))
        for ti, yi in zip(t, y):
            ts = np.datetime64(ti, 's')
            v = '' if not math.isfinite(yi) else f'{yi * k:.6f}'
            temp = temperatura.get(ts)
            w.writerow((nombre, _iso(ts + delta), v, '1' if np.datetime64(ts, 'D') in feriados else '0',
                        '' if temp is None else f'{temp:.3f}', str(ts.astype(object).month)))
            filas += 1
    (destino / SERIES).write_text(salida.getvalue(), encoding='utf-8', newline='')
    (destino / OBJETIVOS).write_text(indice.getvalue(), encoding='utf-8', newline='')
    return InformeSeries(list(FICHEROS), len(nombres), filas)


def leer(carpeta: Path | str) -> tuple[list[Objetivo], Exogenas]:
    """Los objetivos y las exógenas del benchmark, en la forma del 089, para repetir su backtest."""
    carpeta = Path(carpeta)
    with (carpeta / OBJETIVOS).open(encoding='utf-8', newline='') as f:
        meta = {r['objetivo']: r for r in csv.DictReader(f)}
    tiempos: dict[str, list[str]] = {n: [] for n in meta}
    valores: dict[str, list[float]] = {n: [] for n in meta}
    feriados: set[date] = set()
    temperatura: dict[datetime, float] = {}
    meses: dict[date, int] = {}
    with (carpeta / SERIES).open(encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f):
            tiempos[r['objetivo']].append(r['t'])
            valores[r['objetivo']].append(float(r['v']) if r['v'] else float('nan'))
            if r['no_laborable'] == '1':
                feriados.add(date.fromisoformat(r['t'][:10]))
            if r['temperatura_c']:
                temperatura[datetime.fromisoformat(r['t'])] = float(r['temperatura_c'])
            if r.get('mes'):
                meses[date.fromisoformat(r['t'][:10])] = int(r['mes'])
    objetivos = []
    for nombre, m in meta.items():
        fuente = {'inicio_base': m['inicio_base']} if m['inicio_base'] else {}
        curva = CurvaCompacta(np.array(tiempos[nombre], dtype='datetime64[ns]'), np.array(valores[nombre]))
        objetivos.append(Objetivo(m['clase'], m['ident'], m['magnitud'], m['unidad'], curva, fuente))
    return objetivos, Exogenas(feriados, temperatura, [], meses)
